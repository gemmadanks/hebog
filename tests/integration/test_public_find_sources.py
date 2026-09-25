# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Installed-library contract for the public FITS-to-products facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import numpy.typing as npt
import pytest
from astropy import units
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from conftest import SubstituteBackgroundRms, published_plane
from distributed import Client, LocalCluster

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest, public_api
from hebog.algorithms import fitting as fitting_algorithm
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models import PublicSourceFindingDiagnostics
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io import (
    FitsImageSource,
    read_catalogue_fits_product,
    read_diagnostics_product,
)
from hebog.io.zarr import ZarrProductSink
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    UnsupportedSourceFinderConfigurationError,
)
from hebog.stages import detection as detection_stage
from hebog.stages.background import BackgroundRmsGrids
from hebog.validation.public_measurement_projection import (
    project_public_measurements,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


@pytest.mark.integration
def test_public_workflow_retires_stale_coarse_anchors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A corrected pilot must reach readable products, not only refinement."""
    # Public coarse protection activates at 150 pixels on the shorter axis.
    yy, xx = np.mgrid[:160, :192]
    image = np.random.default_rng(130913).normal(0, 1, yy.shape)
    image += 100 * np.exp(-((xx - 64) ** 2 + (yy - 40) ** 2) / 8)
    image[32, 24] = 2.0
    path = tmp_path / "image.fits"
    _write_image(path, image)
    original = detection_stage.estimate_background_rms_grids

    def underestimated_pilot(*args: Any, **kwargs: Any) -> BackgroundRmsGrids:
        grids = original(*args, **kwargs)
        return replace(
            grids,
            coarse=replace(
                grids.coarse,
                background=np.zeros_like(grids.coarse.background),
                rms=np.full_like(grids.coarse.rms, 0.01),
            ),
        )

    monkeypatch.setattr(
        detection_stage, "estimate_background_rms_grids", underestimated_pilot
    )

    # Supply the bounded work packet at the escaped composition seam. The
    # intentionally biased cache is not a new image-wide detection policy.
    def initial_work_packet(
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[tuple[float, float], ...]:
        return ((32.0, 24.0), (40.0, 64.0))

    monkeypatch.setattr(
        detection_stage,
        "discover_adaptive_candidates",
        initial_work_packet,
    )
    result = hebog.find_sources(
        SourceFinderRequest(path, tmp_path / "products", "stale-pilot"),
        SourceFinderConfig(5, 3, 7),
        SerialExecutor(),
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    diagnostics = read_diagnostics_product(result.diagnostics)
    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    assert result.source_count == len(catalogue.sources) == 1
    assert diagnostics.rms_scientific_status == "valid"
    assert mask[40, 64] and not mask[32, 24]
    rms = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    assert np.all(np.isfinite(rms))


class _RecordingExecutor(SerialExecutor):
    """Ordered executor double proving the public facade uses its caller."""

    def __init__(self) -> None:
        """Record the batch count of every submitted map."""
        super().__init__()
        self.batch_counts: list[int] = []

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Execute in order while retaining each submitted batch count."""
        items = list(batches)
        self.batch_counts.append(len(items))
        return super().map_batches(function, items, requirement=requirement)


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    """Return one valid ICRS radio-continuum FITS header."""
    height, width = shape_yx
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = width / 2 + 1
    header["CRPIX2"] = height / 2 + 1
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    return header


def _ring_image() -> np.ndarray:
    """Return a small four-lobe shell exercising source association."""
    y_pixels, x_pixels = np.mgrid[:81, :81]
    x_offset = x_pixels - 40.0
    y_offset = y_pixels - 40.0
    radius = np.hypot(x_offset, y_offset)
    angle = np.arctan2(y_offset, x_offset)
    image = np.exp(-((radius - 10.0) ** 2) / 2.0)
    image *= 1.0 + 8.0 * np.clip(np.cos(4.0 * angle), 0.0, None)
    image += np.random.default_rng(42).normal(0.0, 0.5, image.shape)
    return np.asarray(image, dtype=np.float64)


def _write_image(path: Path, values: np.ndarray) -> None:
    """Write one two-dimensional supported public input."""
    fits.PrimaryHDU(data=values, header=_header(values.shape)).writeto(path)


def _config(*, profile: str = "continuum") -> SourceFinderConfig:
    """Return the frozen Phase 5 public scientific configuration."""
    return SourceFinderConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=7,
        profile=profile,  # type: ignore[arg-type]
    )


def _request(
    tmp_path: Path,
    *,
    output_name: str = "products",
    run_id: str = "public-contract",
) -> SourceFinderRequest:
    """Return one request for the shared input fixture."""
    return SourceFinderRequest(
        image_path=tmp_path / "image.fits",
        output_directory=tmp_path / output_name,
        run_id=run_id,
    )


def _published_mask(products: Any) -> npt.NDArray[np.bool_]:
    """Return the retained mask the driver streams as its mask product."""
    return published_plane(
        products.publication_source, "retained-mask", np.bool_
    )


def _owner_labels(products: Any) -> npt.NDArray[np.int32]:
    """Return the published component ownership a projection cannot infer."""
    return published_plane(
        products.component_source, "component-measurement-labels", np.int32
    )


def _published_mask_source(
    directory: Path,
    mask: npt.NDArray[np.bool_],
) -> ZarrProductSink:
    """Publish one pruned retained mask the way the support pass would."""
    manifest = plan_image_partitions(
        image_shape_yx=mask.shape,
        tile_core_shape_yx=mask.shape,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(directory, manifest, generation_id="pruned")
    sink.initialize_product(
        product_name="retained-mask", dtype=np.dtype(np.bool_)
    )
    chunks = [
        sink.write_chunk(
            product_name="retained-mask", tile=tile, values=mask[_core(tile)]
        )
        for tile in manifest.tiles
    ]
    sink.publish_generation(
        product_names=("retained-mask",), chunks=tuple(chunks)
    )
    return sink


def _core(tile: Any) -> tuple[slice, slice]:
    """Select one tile's core rows and columns from a complete plane."""
    bounds = tile.core_bounds
    return (
        slice(bounds.y_start, bounds.y_stop),
        slice(bounds.x_start, bounds.x_stop),
    )


def _pruned_products(
    products: Any,
    mask: npt.NDArray[np.bool_],
    directory: Path,
) -> Any:
    """Return the products a published mask this small would have produced.

    The island round measures the published retained mask, so a fixture that
    prunes that mask has to prune what the round measured from it: an owner
    with no retained pixel reaches no island, which is the case these tests
    exist for. The pruned plane is published in place of the support pass's
    own, because no step after the science holds a plane to edit.
    """
    terminal = products.terminal
    owners = _owner_labels(products)
    retained_owners = {
        int(value) for value in np.unique(owners[mask]) if value > 0
    }
    island_ids_by_owner = {
        owner: identifiers
        for owner, identifiers in terminal.island_ids_by_owner.items()
        if owner in retained_owners
    }
    named = {
        identifier
        for identifiers in island_ids_by_owner.values()
        for identifier in identifiers
    }
    return replace(
        products,
        publication_source=_published_mask_source(directory, mask),
        terminal=replace(
            terminal,
            islands=tuple(
                island
                for island in terminal.islands
                if island.identifier in named
            ),
            island_ids_by_owner=island_ids_by_owner,
        ),
    )


@pytest.mark.integration
def test_measurement_owner_without_published_support_has_no_public_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """Publication pruning must not create dangling island references."""
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 25) ** 2 + (yy - 32) ** 2) / 8)
    signal += 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    _write_image(tmp_path / "image.fits", signal)
    original = public_api._analyse_image  # pyright: ignore[reportPrivateUsage]
    retained = []

    def analysis(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        assert result.terminal is not None
        mask = _published_mask(result).copy()
        mask[:, :48] = False
        updated = _pruned_products(result, mask, tmp_path / "pruned.zarr")
        # The work directory goes with the run, so the ownership this
        # projection needs is read while its generation still exists.
        retained.append((updated.terminal, _owner_labels(result)))
        return updated

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    monkeypatch.setattr(public_api, "_analyse_image", analysis)
    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert result.source_count == result.gaussian_component_count == 1
    assert result.island_count == 1
    sources = [
        row
        for row in diagnostics.measurement_dispositions
        if row.object_kind == "source"
    ]
    assert len(sources) == 2
    assert sum(row.catalogue_row_published for row in sources) == 1
    assert all(row.status == "measured" for row in sources)
    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    terminal, owners = retained[0]
    projection = project_public_measurements(
        terminal,
        read_catalogue_fits_product(result.catalogue),
        mask,
        _header(signal.shape),
        owner_labels=owners,
    )
    assert len(projection.sources) == 1
    assert len(projection.measured_sources) == 2
    assert not np.any(projection.source_union_labels[:, :48])
    assert (
        sum(row.catalogue_row_published for row in projection.dispositions)
        == 2
    )


@pytest.mark.integration
@pytest.mark.parametrize("owner_pixels", (1, 7))
def test_public_degenerate_owner_does_not_abort_a_healthy_neighbour(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner_pixels: int,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """An admitted thin owner is retained without inventing a Gaussian."""
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    signal[32, 12 : 12 + owner_pixels] = 10.0
    _write_image(tmp_path / "image.fits", signal)

    original_catalogue = public_api._public_catalogue  # pyright: ignore[reportPrivateUsage]
    projections = []

    def projected_catalogue(
        products: Any, metadata: Any, *, run_id: str, profile: str
    ):
        catalogue = original_catalogue(
            products, metadata, run_id=run_id, profile=profile
        )
        projections.append(
            project_public_measurements(
                products.terminal,
                catalogue,
                _published_mask(products),
                _header(signal.shape),
                owner_labels=_owner_labels(products),
            )
        )
        return catalogue

    monkeypatch.setattr(public_api, "_public_catalogue", projected_catalogue)

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    result = hebog.find_sources(
        _request(tmp_path),
        SourceFinderConfig(5.0, 3.0, owner_pixels),
        SerialExecutor(),
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert len(catalogue.sources) == 2
    assert len(catalogue.gaussian_components) == 1
    unavailable = [
        entry
        for entry in diagnostics.measurement_dispositions
        if entry.object_kind == "component" and entry.status == "unavailable"
    ]
    assert len(unavailable) == 1
    assert unavailable[0].reason in {
        "underdetermined-region",
        "singular-covariance",
    }
    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    assert mask[32, 12 : 12 + owner_pixels].all()
    projection = projections[0]
    assert len(projection.sources) == 2
    assert len(projection.components) == 1
    assert len(projection.measured_sources) == 2
    assert len(projection.measured_components) == 1
    assert {row.identifier for row in projection.sources} == {
        row.source_id for row in catalogue.sources
    }
    assert np.array_equal(projection.publication_mask, mask)
    assert np.array_equal(projection.source_union_labels > 0, mask)
    assert (
        sum(row.catalogue_row_published for row in projection.dispositions)
        == 3
    )
    assert not projection.source_union_labels.flags.writeable


@pytest.mark.integration
def test_pruned_component_of_a_published_source_keeps_its_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """An extended source can remain published after one owner is pruned."""
    yy, xx = np.mgrid[:97, :97]
    radius = np.hypot(xx - 48, yy - 48)
    angle = np.arctan2(yy - 48, xx - 48)
    signal = (
        6
        * (1 + 0.6 * np.cos(6 * angle))
        * np.exp(-0.5 * ((radius - 18) / 2) ** 2)
    )
    _write_image(tmp_path / "image.fits", signal)
    original = public_api._analyse_image  # pyright: ignore[reportPrivateUsage]

    def prune_one_component(*args: Any, **kwargs: Any):
        products = original(*args, **kwargs)
        terminal = products.terminal
        assert terminal is not None
        assert len(terminal.catalogue) == 1
        assert len(terminal.component_catalogue) == 6
        removed = terminal.source_association.components[0].label_value
        mask = _published_mask(products) & (_owner_labels(products) != removed)
        return _pruned_products(products, mask, tmp_path / "pruned.zarr")

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    monkeypatch.setattr(public_api, "_analyse_image", prune_one_component)
    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )
    assert result.source_count == 1
    assert result.gaussian_component_count == 5
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    components = tuple(
        row
        for row in diagnostics.measurement_dispositions
        if row.object_kind == "component"
    )
    assert len(components) == 6
    assert all(row.status == "measured" for row in components)
    assert sum(row.catalogue_row_published for row in components) == 5


@pytest.mark.integration
def test_two_sources_share_one_actual_detection_island(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """Island counts describe connectivity, not the number of source rows."""
    yy, xx = np.mgrid[:65, :65]
    signal = np.asarray(
        sum(
            peak * np.exp(-((xx - cx) ** 2 + (yy - 32) ** 2) / 8)
            for peak, cx in ((10, 28), (9.5, 35))
        ),
        dtype=np.float64,
    )
    _write_image(tmp_path / "image.fits", signal)

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    assert result.source_count == result.gaussian_component_count == 2
    assert result.island_count == 1
    assert {source.island_id for source in catalogue.sources} == {
        catalogue.islands[0].island_id
    }
    assert catalogue.islands[0].pixel_count == np.count_nonzero(
        np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    )


@pytest.mark.integration
def test_current_projection_rejects_inconsistent_public_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """Malformed ownership, rows or dispositions cannot become parity input."""
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 48) ** 2 + (yy - 32) ** 2) / 8)
    path = tmp_path / "image.fits"
    _write_image(path, signal)

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    source = FitsImageSource(path)
    metadata = source.metadata()
    header = _header(signal.shape)
    products = public_api._analyse_image(  # pyright: ignore[reportPrivateUsage]
        _request(tmp_path),
        source,
        metadata,
        SerialExecutor(),
        tmp_path / "scratch",
        config=_config(),
        header=header,
    )
    terminal = products.terminal
    assert terminal is not None
    catalogue = public_api._public_catalogue(  # pyright: ignore[reportPrivateUsage]
        products, metadata, run_id="fixture", profile="continuum"
    )
    mask = _published_mask(products)
    owners = _owner_labels(products)
    assert len(catalogue.sources) == 1
    for invalid_mask in (mask.astype(np.int32), mask[np.newaxis]):
        with pytest.raises(ValueError, match="Boolean"):
            project_public_measurements(
                terminal, catalogue, invalid_mask, header, owner_labels=owners
            )
    with pytest.raises(ValueError, match="needs owner labels"):
        project_public_measurements(terminal, catalogue, mask, header)
    for invalid_owners, invalid_mask in (
        (owners, mask[:-1]),
        (owners, ~mask),
        (-owners, mask),
        (owners.astype(np.float64), mask),
    ):
        with pytest.raises(ValueError, match="ownership or publication"):
            project_public_measurements(
                terminal,
                catalogue,
                invalid_mask,
                header,
                owner_labels=invalid_owners,
            )
    for broken, message in (
        (replace(terminal, measurement_dispositions=()), "dispositions"),
        (replace(terminal, catalogue=()), "exact measurements"),
        (replace(terminal, component_catalogue=()), "exact measurements"),
        (
            replace(
                terminal,
                catalogue=(
                    replace(
                        terminal.catalogue[0],
                        right_ascension_degrees=0.0,
                        declination_degrees=30.0,
                    ),
                ),
            ),
            "position must be finite",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            project_public_measurements(
                broken, catalogue, mask, header, owner_labels=owners
            )
    changed = catalogue.model_copy(
        update={
            "sources": (
                catalogue.sources[0].model_copy(
                    update={"source_id": "wrong-source"}
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="memberships"):
        project_public_measurements(
            terminal, changed, mask, header, owner_labels=owners
        )
    # A retained measurement alone cannot stand in for published support.
    with pytest.raises(ValueError, match="no published support"):
        project_public_measurements(
            terminal,
            catalogue,
            np.zeros_like(mask),
            header,
            owner_labels=owners,
        )
    with pytest.raises(ValueError, match="absent terminal"):
        project_public_measurements(None, catalogue, mask, header)


@pytest.mark.integration
@pytest.mark.parametrize("negative_context", (-0.05, -1.0))
def test_signed_aperture_failure_never_becomes_positive_only_flux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    negative_context: float,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """The public result keeps detection but does not invent positive flux."""
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    signal[20:45, 2:30] = negative_context
    signal[32, 12:19] = 10.0
    _write_image(tmp_path / "image.fits", signal)

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    missing = [
        entry
        for entry in diagnostics.measurement_dispositions
        if entry.object_kind == "source" and entry.status == "unavailable"
    ]
    assert len(missing) == (1 if negative_context == -1 else 0)
    assert len(catalogue.sources) == (1 if negative_context == -1 else 2)
    assert result.island_count == 2
    assert np.asarray(fits.getdata(result.mask_path), dtype=bool)[
        32, 12:19
    ].all()
    assert not any(
        "exact-owner-positive-residual-flux" in row.quality_flags
        for row in catalogue.sources
    )


@pytest.mark.integration
def test_public_find_sources_materializes_the_qualified_continuum_view(
    tmp_path: Path,
) -> None:
    """The top-level call publishes a complete source-level product set."""
    _write_image(tmp_path / "image.fits", _ring_image())
    executor = _RecordingExecutor()

    result = hebog.find_sources(_request(tmp_path), _config(), executor)

    assert executor.batch_counts
    assert result.run_id == "public-contract"
    assert result.source_count == 1
    assert result.gaussian_component_count == 4
    assert result.island_count == 4
    assert result.wall_seconds >= 0.0
    assert result.catalogue_path == tmp_path / "products/catalogue.fits"
    assert result.rms_path == tmp_path / "products/rms.fits"
    assert result.mask_path == tmp_path / "products/source-mask.fits"
    assert result.diagnostics_path == tmp_path / "products/diagnostics.json"
    assert all(
        product.path.is_file()
        for product in (
            result.catalogue,
            result.rms,
            result.mask,
            result.diagnostics,
        )
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert len(catalogue.sources) == 1
    assert len(catalogue.sources[0].additional_island_ids) == 3
    assert len(catalogue.gaussian_components) == 4
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.source_count == 1
    assert diagnostics.deblended_parent_count == 0
    assert diagnostics.deferred_deblend_parent_count == 0
    assert diagnostics.profile == "continuum"
    assert diagnostics.configuration_qualification == "development-unqualified"
    assert diagnostics.provenance.input_sha256
    assert diagnostics.provenance.scientific_composition_sha256


@pytest.mark.integration
@pytest.mark.parametrize(
    "config",
    (
        SourceFinderConfig(5.0, 3.0, 7, profile="compact"),
        SourceFinderConfig(100.0, 80.0, 7, profile="compact"),
    ),
)
def test_continuum_mesh_repair_does_not_change_compact_background_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: SourceFinderConfig
) -> None:
    """Compact-only processing keeps its separately defined RMS policy."""
    from hebog.science.configuration import (  # noqa: PLC0415
        source_finder_configs,
    )

    original = source_finder_configs()[0].background_rms
    _write_image(tmp_path / "image.fits", np.zeros((256, 384)))
    source = FitsImageSource(tmp_path / "image.fits")

    def inspect_stage(*args: Any, **kwargs: Any) -> None:
        assert args[2].background_rms == original
        assert kwargs["multiscale_protection"] is None
        assert not kwargs["protect_coarse_source_support"]
        assert not kwargs["refine_local_noise"]
        raise RuntimeError("compact policy inspected")

    monkeypatch.setattr(public_api, "run_detection_stage", inspect_stage)
    with pytest.raises(RuntimeError, match="compact policy inspected"):
        public_api._estimate_background_rms(  # pyright: ignore[reportPrivateUsage]
            source,
            source.metadata(),
            config,
            SerialExecutor(),
            tmp_path / "work",
            generation_id="compact-policy",
        )


@pytest.mark.integration
def test_compact_profile_is_explicit_and_retains_component_sources(
    tmp_path: Path,
) -> None:
    """Compact mode reports components without claiming extended support."""
    _write_image(tmp_path / "image.fits", _ring_image())

    result = hebog.find_sources(
        _request(tmp_path, output_name="compact"),
        _config(profile="compact"),
        _RecordingExecutor(),
    )

    assert result.source_count == 4
    assert result.gaussian_component_count == 4
    assert result.island_count == 4
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.profile == "compact"
    assert diagnostics.profile_limitations == ("extended-emission-incomplete",)
    catalogue = read_catalogue_fits_product(result.catalogue)
    published_sources = tuple(
        entry
        for entry in diagnostics.measurement_dispositions
        if entry.object_kind == "source" and entry.catalogue_row_published
    )
    assert {entry.object_id for entry in published_sources} == {
        row.source_id for row in catalogue.sources
    }
    assert len(published_sources) == 4
    assert all(
        entry.member_component_ids == (entry.object_id,)
        for entry in published_sources
    )


@pytest.mark.integration
@pytest.mark.parametrize("shape", ((32, 48), (256, 384)))
def test_blank_and_all_nan_inputs_publish_honest_empty_products(
    tmp_path: Path,
    shape: tuple[int, int],
) -> None:
    """Empty science remains successful without inventing sources or RMS."""
    for name, values, expected_rms_status in (
        ("blank", np.zeros(shape), "unavailable"),
        ("all-nan", np.full(shape, np.nan), "unavailable"),
        ("constant-negative", np.full(shape, -2.0), "unavailable"),
    ):
        image_path = tmp_path / f"{name}.fits"
        _write_image(image_path, values)
        request = SourceFinderRequest(
            image_path=image_path,
            output_directory=tmp_path / name,
            run_id=name,
        )

        result = hebog.find_sources(request, _config(), _RecordingExecutor())

        assert result.source_count == 0
        assert result.gaussian_component_count == 0
        assert result.island_count == 0
        assert result.rms.scientific_status == expected_rms_status
        published = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
        assert published.shape == shape
        assert np.all(np.isnan(published))
        # No pass ran, so there is no published mask to stream: the product
        # is generated row block by row block and retains nothing.
        mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
        assert mask.shape == shape
        assert not np.any(mask)


@pytest.mark.integration
def test_published_rms_streams_the_estimate_across_many_tile_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """The RMS product carries the store's estimate row block by row block.

    The image spans three background tile rows and two tile columns and gives
    every tile its own value, so a row assembled from the wrong chunks, or in
    the wrong order, changes the published pixels.
    """
    yy, xx = np.mgrid[:300, :200]
    estimate = 1.0 + 0.5 * (yy // 128) + 0.25 * (xx // 128)
    signal = 40.0 * np.exp(-((xx - 150) ** 2 + (yy - 200) ** 2) / 8)
    _write_image(tmp_path / "image.fits", signal)
    zero_background = np.zeros_like(signal)

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(signal, zero_background, estimate),
    )

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    assert result.rms.scientific_status == "valid"
    published = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    np.testing.assert_array_equal(published, estimate)


@pytest.mark.integration
def test_catalogue_local_rms_reads_each_owner_own_store_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """Every published local RMS comes from that owner's own pixels.

    The two halves of this non-square image carry different noise, so a
    source or island that read a shifted or transposed window would publish
    its neighbour's RMS rather than its own.
    """
    yy, xx = np.mgrid[:96, :320]
    estimate = np.where(xx < 160, 1.0, 4.0).astype(np.float64)
    signal = 60.0 * np.exp(-((xx - 40) ** 2 + (yy - 48) ** 2) / 8)
    signal += 240.0 * np.exp(-((xx - 280) ** 2 + (yy - 48) ** 2) / 8)
    _write_image(tmp_path / "image.fits", signal)
    zero_background = np.zeros_like(signal)

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(signal, zero_background, estimate),
    )

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    catalogue = read_catalogue_fits_product(result.catalogue)
    assert result.source_count == 2
    assert sorted(
        row.flux.local_rms_jy_per_beam for row in catalogue.sources
    ) == [1.0, 4.0]
    assert sorted(
        row.flux.local_rms_jy_per_beam for row in catalogue.gaussian_components
    ) == [1.0, 4.0]
    assert sorted(
        island.local_rms_jy_per_beam for island in catalogue.islands
    ) == [1.0, 4.0]


@pytest.mark.integration
def test_pure_noise_publishes_no_source_through_the_whole_path(
    tmp_path: Path,
) -> None:
    """Noise with a usable RMS but no admitted owner still publishes.

    Blank and all-NaN inputs stop before the object rounds, so they never
    reach the source hierarchy. Noise does: it has a usable RMS and reaches
    the association with no direct component to describe, which is the case
    that has to skip the decision rather than fabricate one.
    """
    image_path = tmp_path / "noise.fits"
    _write_image(
        image_path,
        np.random.default_rng(20260920).normal(size=(96, 128)) * 0.01,
    )

    result = hebog.find_sources(
        SourceFinderRequest(
            image_path=image_path,
            output_directory=tmp_path / "noise",
            run_id="noise",
        ),
        _config(),
        _RecordingExecutor(),
    )

    assert result.rms.scientific_status != "unavailable"
    assert result.source_count == 0
    assert result.gaussian_component_count == 0
    assert result.island_count == 0


@pytest.mark.integration
def test_publication_fails_closed_for_existing_output(
    tmp_path: Path,
) -> None:
    """The facade rejects ambiguous output ownership without overwriting."""
    _write_image(tmp_path / "image.fits", _ring_image())
    output = tmp_path / "products"
    output.mkdir()
    sentinel = output / "owned.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(SourceFinderOutputExistsError, match="already exists"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())
    assert sentinel.read_text(encoding="utf-8") == "preserve"


@pytest.mark.integration
def test_custom_thresholds_change_science_and_are_marked_unqualified(
    tmp_path: Path,
) -> None:
    """Caller thresholds execute while qualification remains explicit."""
    _write_image(tmp_path / "image.fits", _ring_image())

    qualified = hebog.find_sources(
        _request(tmp_path, output_name="qualified"),
        _config(),
        _RecordingExecutor(),
    )
    custom = hebog.find_sources(
        _request(tmp_path, output_name="custom"),
        SourceFinderConfig(50.0, 25.0, 7),
        _RecordingExecutor(),
    )

    assert qualified.source_count == 1
    assert custom.source_count == 0
    qualified_diagnostics = read_diagnostics_product(qualified.diagnostics)
    custom_diagnostics = read_diagnostics_product(custom.diagnostics)
    assert isinstance(qualified_diagnostics, PublicSourceFindingDiagnostics)
    assert isinstance(custom_diagnostics, PublicSourceFindingDiagnostics)
    assert (
        qualified_diagnostics.configuration_qualification
        == "development-unqualified"
    )
    assert (
        custom_diagnostics.configuration_qualification == "custom-unqualified"
    )
    assert (
        qualified_diagnostics.provenance.configuration_sha256
        != custom_diagnostics.provenance.configuration_sha256
    )


def _high_threshold_image(
    shape: tuple[int, int], *, include_source: bool
) -> np.ndarray:
    """Return analytic noise-only or bright-source refinement controls."""
    image = np.random.default_rng(130913).normal(0, 1, shape)
    if include_source:
        yy, xx = np.indices(shape)
        image += 600 * np.exp(
            -((xx - shape[1] / 2) ** 2 + (yy - shape[0] / 2) ** 2) / 8
        )
    return image


@pytest.mark.integration
@pytest.mark.parametrize("size", (149, 150, 256))
@pytest.mark.parametrize("island_sigma", (74.0, 75.0, 80.0))
@pytest.mark.parametrize("include_source", (False, True))
def test_custom_thresholds_cross_private_refinement_and_mesh_boundaries(
    tmp_path: Path, size: int, island_sigma: float, include_source: bool
) -> None:
    """Valid public thresholds complete on both sides of private boundaries."""
    _write_image(
        tmp_path / "image.fits",
        _high_threshold_image((size, size), include_source=include_source),
    )
    result = hebog.find_sources(
        _request(tmp_path),
        SourceFinderConfig(100.0, island_sigma, 7),
        SerialExecutor(),
    )
    assert result.source_count == int(include_source)
    assert result.gaussian_component_count == int(include_source)
    catalogue = read_catalogue_fits_product(result.catalogue)
    assert len(catalogue.sources) == int(include_source)
    assert len(catalogue.gaussian_components) == int(include_source)
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.configuration_qualification == "custom-unqualified"


@pytest.mark.integration
@pytest.mark.parametrize("shape", ((149, 181), (150, 181), (256, 301)))
@pytest.mark.parametrize("island_sigma", (75.0, 80.0))
@pytest.mark.parametrize("include_source", (False, True))
def test_custom_threshold_products_agree_in_serial_and_tiled_existing_dask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape: tuple[int, int],
    island_sigma: float,
    include_source: bool,
) -> None:
    """Private threshold reconciliation cannot depend on executor or tiles."""
    _write_image(
        tmp_path / "image.fits",
        _high_threshold_image(shape, include_source=include_source),
    )
    config = SourceFinderConfig(100.0, island_sigma, 7)
    serial = hebog.find_sources(
        _request(tmp_path, output_name="serial"), config, SerialExecutor()
    )
    monkeypatch.setattr(public_api, "_TILE_SHAPE_YX", (97, 111))
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask = hebog.find_sources(
            _request(tmp_path, output_name="dask"),
            config,
            DaskExecutor(client),
        )
    assert serial.source_count == int(include_source)
    assert serial.gaussian_component_count == int(include_source)
    assert (
        serial.catalogue.content_sha256,
        serial.rms.content_sha256,
        serial.mask.content_sha256,
        serial.diagnostics.content_sha256,
    ) == (
        dask.catalogue.content_sha256,
        dask.rms.content_sha256,
        dask.mask.content_sha256,
        dask.diagnostics.content_sha256,
    )


@pytest.mark.integration
def test_custom_island_size_limits_are_operational(tmp_path: Path) -> None:
    """Caller pixel limits filter terminal components and remain explicit."""
    _write_image(tmp_path / "image.fits", _ring_image())

    result = hebog.find_sources(
        _request(tmp_path, output_name="size-limited"),
        SourceFinderConfig(
            5.0,
            3.0,
            1,
            maximum_island_pixels=1,
        ),
        _RecordingExecutor(),
    )

    assert result.source_count == 0
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.configuration_qualification == "custom-unqualified"


@pytest.mark.integration
def test_unsupported_public_unit_fails_before_publication(
    tmp_path: Path,
) -> None:
    """A readable but unevaluated physical unit is a configuration error."""
    header = _header((8, 8))
    header["BUNIT"] = "Jy"
    fits.PrimaryHDU(np.zeros((8, 8)), header).writeto(tmp_path / "image.fits")

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match="BUNIT=Jy/beam",
    ):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_public_preview_rejects_inputs_beyond_qualified_envelope(
    tmp_path: Path,
) -> None:
    """The finder never extrapolates past the qualified envelope."""
    _write_image(tmp_path / "image.fits", np.zeros((2, 3001)))

    with pytest.raises(SourceFinderImageTooLargeError, match="3000"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_public_preview_admits_the_largest_qualified_dimension(
    tmp_path: Path,
) -> None:
    """The documented limit is the largest admitted size, not the first
    refused one.

    The rejection above only pins the limit from outside: a limit one pixel
    too small would refuse a documented size and still pass it. This runs the
    boundary itself through the public path.
    """
    _write_image(tmp_path / "image.fits", np.zeros((2, 3000)))

    result = hebog.find_sources(
        _request(tmp_path), _config(), _RecordingExecutor()
    )

    assert result.source_count == 0


@pytest.mark.integration
@pytest.mark.parametrize(
    ("image_kind", "fit_outcome"),
    (
        ("shell", "normal"),
        ("shell", "linear-algebra-failure"),
        ("ellipse", "inadequate-fallback"),
        ("coarse-protection", "normal"),
        ("coarse-protection", "linear-algebra-failure"),
        ("coarse-protection", "inadequate-fallback"),
    ),
)
def test_serial_and_existing_dask_publish_identical_scientific_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fit_outcome: str,
    image_kind: str,
) -> None:
    """Caller-owned execution policy cannot alter any scientific bytes."""
    if fit_outcome == "linear-algebra-failure":

        def fail(*_args: object, **_kwargs: object) -> None:
            raise np.linalg.LinAlgError("SVD did not converge for slice = 0.")

        monkeypatch.setattr(fitting_algorithm, "least_squares", fail)
    elif fit_outcome == "inadequate-fallback":

        def invalid_free(*_args: object, **_kwargs: object) -> str:
            return "free-model-invalid-result"

        monkeypatch.setattr(
            fitting_algorithm, "_free_fallback_reason", invalid_free
        )
    image = _ring_image()
    if image_kind == "ellipse":
        yy, xx = np.mgrid[:49, :65]
        image = 100 * np.exp(
            -0.5 * (((xx - 32.3) / 6) ** 2 + ((yy - 24.1) / 2) ** 2)
        )
        image += np.random.default_rng(2409).normal(0, 0.3, image.shape)
    if image_kind == "coarse-protection":
        yy, xx = np.mgrid[:256, :384]
        radius_squared = (yy - 128) ** 2 + (xx - 192) ** 2
        image = (
            -2 + xx / 1024 + np.random.default_rng(620).normal(size=xx.shape)
        )
        image += 12 * np.exp(-radius_squared / (2 * 20**2))
        image += 1000 * np.exp(-radius_squared / (2 * 2**2))
    _write_image(tmp_path / "image.fits", image)
    serial = hebog.find_sources(
        _request(tmp_path, output_name="serial"),
        _config(),
        SerialExecutor(),
    )
    monkeypatch.setattr(public_api, "_TILE_SHAPE_YX", (97, 111))
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask = hebog.find_sources(
            _request(tmp_path, output_name="dask"),
            _config(),
            DaskExecutor(client),
        )

    assert (
        serial.catalogue.content_sha256,
        serial.rms.content_sha256,
        serial.mask.content_sha256,
        serial.diagnostics.content_sha256,
    ) == (
        dask.catalogue.content_sha256,
        dask.rms.content_sha256,
        dask.mask.content_sha256,
        dask.diagnostics.content_sha256,
    )
    if fit_outcome != "normal":
        expected_reason = (
            "fit-linear-algebra-failure"
            if fit_outcome == "linear-algebra-failure"
            else "fit-model-inadequate"
        )
        diagnostic = read_diagnostics_product(serial.diagnostics_path)
        assert isinstance(diagnostic, PublicSourceFindingDiagnostics)
        assert any(
            row.reason == expected_reason and not row.catalogue_row_published
            for row in diagnostic.measurement_dispositions
        )
        assert serial.source_count > 0


@pytest.mark.integration
def test_non_square_partial_invalid_edge_case_completes(
    tmp_path: Path,
) -> None:
    """Edge emission and invalid pixels preserve a complete product bundle."""
    y_pixels, x_pixels = np.mgrid[:48, :80]
    image = np.random.default_rng(19).normal(0.0, 0.2, (48, 80))
    image += 3.0 * np.exp(
        -0.5 * (((x_pixels - 2.0) / 2.0) ** 2 + ((y_pixels - 3.0) / 2.0) ** 2)
    )
    image[30:34, 50:56] = np.nan
    _write_image(tmp_path / "image.fits", image)

    result = hebog.find_sources(
        _request(tmp_path),
        _config(),
        _RecordingExecutor(),
    )

    assert result.mask_path.is_file()
    assert result.rms_path.is_file()


@pytest.mark.integration
@pytest.mark.parametrize("defect", ["unit", "beam", "wcs", "corrupt"])
def test_invalid_public_inputs_fail_before_publication(
    tmp_path: Path,
    defect: str,
) -> None:
    """Malformed or unsupported FITS inputs never leave successful output."""
    image_path = tmp_path / "image.fits"
    if defect == "corrupt":
        image_path.write_bytes(b"not a FITS file")
    else:
        header = _header((8, 8))
        if defect == "unit":
            del header["BUNIT"]
        elif defect == "beam":
            del header["BMAJ"]
        else:
            del header["CTYPE1"]
            del header["CTYPE2"]
        fits.PrimaryHDU(np.zeros((8, 8)), header).writeto(image_path)

    with pytest.raises(InvalidSourceFinderInputError, match="invalid FITS"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_interrupted_publication_can_retry_without_partial_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed unpublished write is cleaned and the same request can retry."""
    _write_image(tmp_path / "image.fits", _ring_image())
    original = public_api.write_mask_fits_product
    call_count = 0

    def fail_once(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("injected mask write failure")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(public_api, "write_mask_fits_product", fail_once)
    request = _request(tmp_path)
    with pytest.raises(OSError, match="injected"):
        hebog.find_sources(request, _config(), _RecordingExecutor())
    assert not request.output_directory.exists()

    result = hebog.find_sources(request, _config(), _RecordingExecutor())

    assert result.catalogue_path.is_file()
    assert request.output_directory.is_dir()


def _catalogue_positions(result: hebog.SourceFinderResult) -> np.ndarray:
    """Return published source positions in canonical row order."""
    catalogue = read_catalogue_fits_product(result.catalogue)
    return np.asarray(
        [
            (
                source.position.right_ascension_degrees,
                source.position.declination_degrees,
            )
            for source in catalogue.sources
        ],
        dtype=np.float64,
    )


@pytest.mark.integration
def test_isolated_sources_on_uncorrelated_noise_publish_their_components(
    tmp_path: Path,
) -> None:
    """Given beam-shaped sources at SNR 20 to 100 on pixel-independent noise,
    when Hebog measures them,
    then each source publishes one Gaussian component at the right position
    and peak, as pinned PyBDSF master does for the same image.

    A point estimator that assumes beam-correlated noise amplifies
    pixel-independent noise and published no component for most of these
    sources, or a grossly wrong one.
    """
    beam_sigma_pixels = 4.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    noise = 1e-3
    sources_xy = (
        (40.0, 40.0, 20.0),
        (120.0, 48.0, 50.0),
        (80.0, 120.0, 100.0),
    )
    yy, xx = np.mgrid[:160, :160]
    image = np.random.default_rng(20260916).normal(0.0, noise, yy.shape)
    for x, y, snr in sources_xy:
        image += (
            snr
            * noise
            * np.exp(
                -((xx - x) ** 2 + (yy - y) ** 2) / (2 * beam_sigma_pixels**2)
            )
        )
    path = tmp_path / "image.fits"
    _write_image(path, image)
    header = _header(image.shape)
    celestial = WCS(header).celestial

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    components = read_catalogue_fits_product(
        result.catalogue
    ).gaussian_components
    assert len(components) == len(sources_xy)
    published = sorted(
        (
            *celestial.world_to_pixel_values(
                row.position.right_ascension_degrees,
                row.position.declination_degrees,
            ),
            row.flux.peak_flux_jy_per_beam,
        )
        for row in components
    )
    for (x, y, peak), (true_x, true_y, snr) in zip(
        published, sorted(sources_xy), strict=True
    ):
        assert np.hypot(x - true_x, y - true_y) < 0.25 * 4.0
        assert peak == pytest.approx(snr * noise, rel=0.15)


@pytest.mark.integration
@pytest.mark.parametrize("declared", ("radesys-fk5", "implicit-equinox"))
def test_fk5_j2000_input_publishes_the_same_icrs_sky(
    tmp_path: Path,
    declared: str,
) -> None:
    """FK5 J2000 pixels are converted, not relabelled, into ICRS positions.

    Given one image whose FK5 J2000 reference point is the same sky direction
    as an ICRS reference image, the frame-tie rotation over the image is
    micro-arcseconds, so both runs publish the same ICRS sky. The FK5 and ICRS
    reference coordinates themselves differ by tens of milliarcseconds.
    """
    image = _ring_image()
    _write_image(tmp_path / "image.fits", image)
    reference = SkyCoord(180.0 * units.deg, -30.0 * units.deg, frame="icrs")
    fk5: Any = reference.transform_to("fk5")
    header = _header(image.shape)
    header["CRVAL1"] = fk5.ra.deg
    header["CRVAL2"] = fk5.dec.deg
    del header["RADESYS"]
    header["EQUINOX"] = 2000.0
    if declared == "radesys-fk5":
        header["RADESYS"] = "FK5"
    fits.PrimaryHDU(data=image, header=header).writeto(tmp_path / "fk5.fits")
    frame_tie: Any = reference.separation(
        SkyCoord(fk5.ra, fk5.dec, frame="icrs")
    )
    frame_tie_arcsec = float(frame_tie.to_value(units.arcsec))

    icrs_result = hebog.find_sources(
        _request(tmp_path, output_name="icrs"), _config(), SerialExecutor()
    )
    fk5_result = hebog.find_sources(
        SourceFinderRequest(
            image_path=tmp_path / "fk5.fits",
            output_directory=tmp_path / "fk5",
            run_id="public-contract",
        ),
        _config(),
        SerialExecutor(),
    )

    assert frame_tie_arcsec > 0.01
    icrs_positions = _catalogue_positions(icrs_result)
    fk5_positions = _catalogue_positions(fk5_result)
    assert icrs_positions.shape == fk5_positions.shape == (1, 2)
    separation_arcsec = np.asarray(
        SkyCoord(*icrs_positions.T, unit="deg", frame="icrs")
        .separation(SkyCoord(*fk5_positions.T, unit="deg", frame="icrs"))
        .to_value(units.arcsec),
        dtype=np.float64,
    )
    assert np.all(separation_arcsec < 1e-4)
    icrs_catalogue = read_catalogue_fits_product(icrs_result.catalogue)
    fk5_catalogue = read_catalogue_fits_product(fk5_result.catalogue)
    assert fk5_catalogue.coordinate_frame == "icrs"
    # The aperture is a pixel sum, so the frame tie cannot move it. The
    # source flux is its components' fitted integral, which depends on the
    # local tangent plane the tie does perturb, well below any scientific
    # significance.
    assert [
        source.association_aperture_integrated_flux_jy
        for source in fk5_catalogue.sources
    ] == pytest.approx(
        [
            source.association_aperture_integrated_flux_jy
            for source in icrs_catalogue.sources
        ],
        rel=1e-9,
    )
    assert [
        source.flux.integrated_flux_jy for source in fk5_catalogue.sources
    ] == pytest.approx(
        [source.flux.integrated_flux_jy for source in icrs_catalogue.sources],
        rel=1e-6,
    )


@pytest.mark.integration
@pytest.mark.parametrize("missing_card", ("absent", "undefined"))
def test_supplied_metadata_publishes_the_same_science_as_a_complete_header(
    tmp_path: Path,
    missing_card: str,
) -> None:
    """Given an image whose header omits frequency and beam angle,
    when the caller supplies the header's missing values,
    then Hebog publishes the same catalogue as for the complete header and
    records the supplied values in diagnostics.

    A keyword present with an undefined value is missing, just as an absent
    keyword is.
    """
    image = _ring_image()
    _write_image(tmp_path / "image.fits", image)
    header = _header(image.shape)
    del header["RESTFRQ"]
    if missing_card == "absent":
        del header["BPA"]
    else:
        header["BPA"] = None
    fits.PrimaryHDU(data=image, header=header).writeto(
        tmp_path / "sparse.fits"
    )
    supplied = hebog.SuppliedImageMetadata(
        reference_frequency_hz=150_000_000.0,
        beam_position_angle_degrees=0.0,
    )
    sparse_request = SourceFinderRequest(
        tmp_path / "sparse.fits",
        tmp_path / "sparse",
        "public-contract",
        supplied_metadata=supplied,
    )

    with pytest.raises(InvalidSourceFinderInputError, match="invalid FITS"):
        hebog.find_sources(
            replace(sparse_request, supplied_metadata=None),
            _config(),
            SerialExecutor(),
        )
    complete = hebog.find_sources(
        _request(tmp_path, output_name="complete"), _config(), SerialExecutor()
    )
    sparse = hebog.find_sources(sparse_request, _config(), SerialExecutor())

    complete_catalogue = read_catalogue_fits_product(complete.catalogue)
    sparse_catalogue = read_catalogue_fits_product(sparse.catalogue)
    assert sparse_catalogue.sources == complete_catalogue.sources
    assert (
        sparse_catalogue.gaussian_components
        == complete_catalogue.gaussian_components
    )
    assert sparse_catalogue.reference_frequency_hz == 150_000_000.0
    sparse_diagnostics = read_diagnostics_product(sparse.diagnostics)
    complete_diagnostics = read_diagnostics_product(complete.diagnostics)
    assert isinstance(sparse_diagnostics, PublicSourceFindingDiagnostics)
    assert isinstance(complete_diagnostics, PublicSourceFindingDiagnostics)
    assert sparse_diagnostics.provenance.supplied_image_metadata == supplied
    assert complete_diagnostics.provenance.supplied_image_metadata is None
    assert fits.getheader(sparse.rms_path)["BPA"] == 0.0


@pytest.mark.integration
@pytest.mark.parametrize(
    ("radesys", "equinox"),
    (("FK5", 1950.0), ("FK4", 1950.0), ("GALACTIC", None)),
)
def test_other_celestial_frames_fail_before_publication(
    tmp_path: Path,
    radesys: str,
    equinox: float | None,
) -> None:
    """Only ICRS and FK5 J2000 are inside the public input envelope."""
    header = _header((8, 8))
    if radesys == "GALACTIC":
        del header["RADESYS"]
        header["CTYPE1"] = "GLON-TAN"
        header["CTYPE2"] = "GLAT-TAN"
    else:
        header["RADESYS"] = radesys
        header["EQUINOX"] = equinox
    fits.PrimaryHDU(np.zeros((8, 8)), header).writeto(tmp_path / "image.fits")

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match="ICRS or FK5 J2000",
    ):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_relative_request_paths_are_bound_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workers never resolve request paths against their own directory."""
    _write_image(tmp_path / "image.fits", _ring_image())
    sources: list[Path] = []
    original = public_api.FitsImageSource

    def recording_source(
        path: Path,
        supplied_metadata: hebog.SuppliedImageMetadata | None = None,
    ) -> FitsImageSource:
        sources.append(path)
        return original(path, supplied_metadata)

    monkeypatch.setattr(public_api, "FitsImageSource", recording_source)
    monkeypatch.chdir(tmp_path)

    result = hebog.find_sources(
        SourceFinderRequest(
            image_path=Path("image.fits"),
            output_directory=Path("products"),
            run_id="relative",
        ),
        _config(),
        _RecordingExecutor(),
    )

    assert sources == [tmp_path / "image.fits"]
    assert result.catalogue_path == tmp_path / "products/catalogue.fits"
    assert result.catalogue_path.is_file()


@pytest.mark.integration
def test_oversized_input_is_rejected_before_it_is_hashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An inadmissible image costs a header read, not a full-file digest."""
    _write_image(tmp_path / "image.fits", np.zeros((2, 3001)))

    def forbidden_hash(_path: Path) -> str:
        pytest.fail("oversized input was hashed")

    monkeypatch.setattr(public_api, "_file_sha256", forbidden_hash)

    with pytest.raises(SourceFinderImageTooLargeError, match="3000"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())


@pytest.mark.integration
@pytest.mark.parametrize("occupant", ("empty", "populated", "file"))
def test_output_created_during_analysis_is_never_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    occupant: str,
) -> None:
    """A destination claimed by another writer mid-run is left untouched."""
    _write_image(tmp_path / "image.fits", _ring_image())
    request = _request(tmp_path)
    original = public_api._materialize_bundle  # pyright: ignore[reportPrivateUsage]

    def claim_output(*args: Any, **kwargs: Any) -> Any:
        output = request.output_directory
        if occupant == "file":
            output.write_text("preserve", encoding="utf-8")
        else:
            output.mkdir()
            if occupant == "populated":
                (output / "owned.txt").write_text("preserve", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(public_api, "_materialize_bundle", claim_output)

    with pytest.raises(SourceFinderOutputExistsError, match="already exists"):
        hebog.find_sources(request, _config(), _RecordingExecutor())

    output = request.output_directory
    if occupant == "file":
        assert output.read_text(encoding="utf-8") == "preserve"
    else:
        expected = ["owned.txt"] if occupant == "populated" else []
        assert sorted(path.name for path in output.iterdir()) == expected
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "image.fits",
        "products",
    ]


@pytest.mark.integration
def test_whole_pixel_beam_is_invariant_to_sub_milliarcsecond_reference_shift(
    tmp_path: Path,
) -> None:
    """Finite-difference round-off cannot move beam-scaled pixel extents.

    Given a four-pixel circular beam, a 0.7 mas reference-coordinate shift
    changes the WCS Jacobian only at round-off level. Aperture radii and
    kernel halos derived with ``ceil`` must not flip, so the published
    measurements are unchanged.
    """
    image = _ring_image()
    fluxes: list[list[float | None]] = []
    fitted: list[list[float]] = []
    for index, reference_ra in enumerate((180.0, 180.0 + 2e-7)):
        header = _header(image.shape)
        header["CRVAL1"] = reference_ra
        path = tmp_path / f"image-{index}.fits"
        fits.PrimaryHDU(data=image, header=header).writeto(path)
        beam = public_api._beam_shape_pixels(  # pyright: ignore[reportPrivateUsage]
            FitsImageSource(path).metadata()
        )
        assert (beam.major_fwhm_pixels, beam.minor_fwhm_pixels) == (4.0, 4.0)
        assert beam.position_angle_degrees == 0.0
        result = hebog.find_sources(
            SourceFinderRequest(
                image_path=path,
                output_directory=tmp_path / f"products-{index}",
                run_id="reference-shift",
            ),
            _config(),
            SerialExecutor(),
        )
        catalogue = read_catalogue_fits_product(result.catalogue)
        fluxes.append(
            [
                source.association_aperture_integrated_flux_jy
                for source in catalogue.sources
            ]
        )
        fitted.append(
            [source.flux.integrated_flux_jy for source in catalogue.sources]
        )

    # The aperture is the quantity the `ceil` radii decide, so it must be
    # exactly unchanged. The fitted flux varies continuously with the tangent
    # plane and moves only at the shift's own scale.
    assert fluxes[0] == pytest.approx(fluxes[1], rel=1e-9)
    assert fitted[0] == pytest.approx(fitted[1], rel=1e-6)


@pytest.mark.integration
@pytest.mark.parametrize("claimed", (True, False))
def test_publication_failure_is_classified_by_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    claimed: bool,
) -> None:
    """A claimed destination is an existing output; other errors propagate."""
    unpublished = tmp_path / "bundle"
    unpublished.mkdir()
    output = tmp_path / "products"
    failure = (
        FileExistsError("injected claim")
        if claimed
        else OSError("injected rename failure")
    )

    def failing_rename(_source: Path, _target: Path) -> None:
        raise failure

    monkeypatch.setattr(
        public_api, "rename_without_replacement", failing_rename
    )
    expected = SourceFinderOutputExistsError if claimed else OSError
    with pytest.raises(expected) as error:
        public_api._publish_bundle(unpublished, output)  # pyright: ignore[reportPrivateUsage]

    assert unpublished.is_dir()
    assert isinstance(error.value, SourceFinderOutputExistsError) is claimed


@pytest.mark.integration
def test_unreadable_input_digest_is_an_invalid_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read failure after header validation keeps the public error type."""
    _write_image(tmp_path / "image.fits", np.zeros((8, 8)))

    def unreadable(_path: Path) -> str:
        raise OSError("injected read failure")

    monkeypatch.setattr(public_api, "_file_sha256", unreadable)

    with pytest.raises(InvalidSourceFinderInputError, match="invalid FITS"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()
