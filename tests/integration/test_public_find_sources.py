# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Installed-library contract for the public FITS-to-products facade."""

from __future__ import annotations

import ast
import gc
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy import units
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from conftest import (
    SubstituteBackgroundRms,
    product_hashes,
    published_plane,
)
from distributed import Client, LocalCluster, get_task_stream
from pytest_mock import MockerFixture
from scipy import ndimage

import hebog
from hebog import (
    SourceFinderConfig,
    SourceFinderRequest,
    SourceFinderResult,
    public_api,
)
from hebog.algorithms import fitting as fitting_algorithm
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models import PublicSourceFindingDiagnostics, WideObjectCounts
from hebog.executors import (
    DaskExecutor,
    Executor,
    SerialExecutor,
    TaskRequirement,
)
from hebog.io import (
    FitsImageSource,
    read_catalogue_fits_product,
    read_diagnostics_product,
)
from hebog.io.zarr import ZarrProductSink
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    UnsupportedSourceFinderConfigurationError,
)
from hebog.science import continuum
from hebog.science.models import TiledComponentFits
from hebog.stages import detection as detection_stage
from hebog.stages.background import BackgroundRmsGrids
from hebog.validation.datasets import (
    generate_synthetic_window,
    load_dataset_manifest,
)
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.public_measurement_projection import (
    project_public_measurements,
)

Input = TypeVar("Input")
Output = TypeVar("Output")

_QUICK_CHECK_DATASETS = (
    Path(__file__).resolve().parents[2]
    / "config/datasets/quick-science-check.json"
)


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
def test_a_measured_source_without_an_island_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """A measured source with no island is refused, never silently dropped.

    Support publication keeps a retained pixel for every admitted owner, so
    only a broken composition can leave a measured source without an island;
    the fixture prunes half the mask and its island map by hand to build one.
    """
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 25) ** 2 + (yy - 32) ** 2) / 8)
    signal += 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    _write_image(tmp_path / "image.fits", signal)
    original = public_api._analyse_image  # pyright: ignore[reportPrivateUsage]

    def analysis(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        assert result.terminal is not None
        mask = _published_mask(result).copy()
        mask[:, :48] = False
        return _pruned_products(result, mask, tmp_path / "pruned.zarr")

    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )
    monkeypatch.setattr(public_api, "_analyse_image", analysis)

    with pytest.raises(SourceFinderError, match="reaches no island"):
        hebog.find_sources(_request(tmp_path), _config(), SerialExecutor())
    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_a_compact_detection_below_the_boundary_floor_is_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """A narrow-beam source between 5 and 6 sigma keeps its row and island.

    A 5.9-sigma point source in a 3.4-pixel beam, half a pixel off a pixel
    centre, floods eight pixels at 3 sigma in two rows: no 3x3 block for the
    mask opening and no pixel at the 6-sigma boundary floor. Refinement once
    removed all of its support, so it was fitted and measured but had no
    island, row or mask pixel, as on the SKA-Mid SDC1 cut-outs. It is
    published like the 20-sigma source beside it.
    """
    shape_yx = (48, 80)
    yy, xx = np.mgrid[: shape_yx[0], : shape_yx[1]]
    beam_pixels = 3.4
    sigma = beam_pixels / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    signal = np.zeros(shape_yx, dtype=np.float64)
    for (y, x), peak in (((24.0, 20.0), 20.0), ((24.0, 56.5), 5.9)):
        signal += peak * np.exp(
            -((yy - y) ** 2 + (xx - x) ** 2) / (2.0 * sigma**2)
        )
    header = _header(shape_yx)
    header["BMAJ"] = header["BMIN"] = beam_pixels / 3600.0
    fits.PrimaryHDU(data=signal, header=header).writeto(
        tmp_path / "image.fits"
    )
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
    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    faint = signal[:, 40:] >= 3.0
    assert np.count_nonzero(faint) == 8
    assert signal[:, 40:].max() < 6.0
    assert not ndimage.binary_opening(faint, np.ones((3, 3))).any()
    assert result.source_count == result.island_count == 2
    assert result.gaussian_component_count == 2
    np.testing.assert_array_equal(mask[:, 40:], faint)
    assert min(
        row.flux.peak_flux_jy_per_beam for row in catalogue.gaussian_components
    ) == pytest.approx(5.9, rel=0.05)
    assert all(
        entry.catalogue_row_published
        for entry in diagnostics.measurement_dispositions
        if entry.status == "measured"
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
def test_a_measured_gaussian_without_an_island_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """A published source's Gaussian with no island is refused, not dropped.

    A component outside the retained mask takes its parent owner's islands,
    so only a broken composition leaves one with none; the fixture prunes
    one of a ring's six components from the mask and island map by hand.
    The source keeps islands through the other five, so only the Gaussian
    check can catch it.
    """
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

    with pytest.raises(SourceFinderError, match="Gaussian reaches no island"):
        hebog.find_sources(_request(tmp_path), _config(), SerialExecutor())
    assert not (tmp_path / "products").exists()


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
def test_projection_accepts_a_source_standing_on_a_shared_island(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """A source with no mask pixel of its own may stand on a shared island.

    A component deblended onto a brighter one's rim, outside its retained
    support, is published on its parent's island. The projection accepts a
    source whose own pixels are absent while another source holds pixels of
    the island it names, and refuses once no source holds any.
    """
    path = tmp_path / "image.fits"
    yy, xx = np.mgrid[:65, :65]
    signal = np.asarray(
        sum(
            peak * np.exp(-((xx - cx) ** 2 + (yy - 32) ** 2) / 8)
            for peak, cx in ((10, 28), (9.5, 35))
        ),
        dtype=np.float64,
    )
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
    assert len(catalogue.sources) == 2
    assert len({row.island_id for row in catalogue.sources}) == 1
    first_owner = terminal.source_association.components[0].label_value

    projection = project_public_measurements(
        terminal,
        catalogue,
        mask & (owners != first_owner),
        header,
        owner_labels=owners,
    )

    assert len(projection.sources) == 2
    assert not np.any(projection.source_union_labels[owners == first_owner])
    with pytest.raises(ValueError, match="no published support"):
        project_public_measurements(
            terminal,
            catalogue,
            mask & (owners == 0),
            header,
            owner_labels=owners,
        )


@pytest.mark.integration
def test_a_compact_source_beside_a_brighter_broad_one_gets_a_gaussian(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """A deep pass between two peaks gives the fainter its own Gaussian.

    Halfway between them the broad source alone outshines the compact one,
    so a saddle judged on the line equidistant from the peaks merged the
    pair, and the compact source's flux was left unmodelled in its
    neighbour's fit.
    """
    yy, xx = np.mgrid[:81, :81]
    injected = ((30.0, 40.0), (51.0, 40.0))
    beam_sigma_pixels = 4.0 / np.sqrt(8.0 * np.log(2.0))
    signal = np.asarray(
        190.0 * np.exp(-((xx - 30) ** 2 + (yy - 40) ** 2) / (2.0 * 7.0**2))
        + 39.0
        * np.exp(
            -((xx - 51) ** 2 + (yy - 40) ** 2) / (2.0 * beam_sigma_pixels**2)
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

    components = read_catalogue_fits_product(
        result.catalogue
    ).gaussian_components
    positions = np.asarray(
        WCS(_header(signal.shape)).celestial.all_world2pix(
            [
                (
                    row.position.right_ascension_degrees,
                    row.position.declination_degrees,
                )
                for row in components
            ],
            0,
        )
    )
    assert result.island_count == 1
    assert len(components) == len(injected)
    for x, y in injected:
        assert np.min(np.hypot(positions[:, 0] - x, positions[:, 1] - y)) < 1


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
    # One published pixel owned by a component the association never named.
    unknown_owner = owners.copy()
    unknown_owner.flat[np.flatnonzero(mask)[0]] = owners.max() + 1
    for invalid_owners, invalid_mask in (
        (owners, mask[:-1]),
        (owners, ~mask),
        (-owners, mask),
        (owners.astype(np.float64), mask),
        (unknown_owner, mask),
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
    """The public result keeps detection but does not invent positive flux.

    The line segment gets no fitted Gaussian, so its aperture is its only
    flux: when that sums below zero the source has nothing to publish. The
    negative context alternates by 10% from pixel to pixel: a constant one
    is a block of one repeated value, invalid input that no aperture sums.
    """
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    context = negative_context * (1.0 + 0.1 * ((xx + yy) % 2))
    signal[20:45, 2:30] = context[20:45, 2:30]
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
    measured_components = {
        entry.object_id
        for entry in diagnostics.measurement_dispositions
        if entry.object_kind == "component" and entry.status == "measured"
    }
    assert not any(
        component in measured_components
        for entry in missing
        for component in entry.member_component_ids
    )
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
@pytest.mark.parametrize("profile", ("continuum", "compact"))
def test_fitted_source_publishes_when_its_aperture_sums_below_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """A source whose Gaussian fits is published whatever its aperture sums.

    The compact source at (20, 32) lies in a residual plateau at -1, as the
    gaps of a crowded field lie below a background its sources' wings raise,
    so the signed sum over its aperture is negative while its Gaussian
    converges. Its flux is the fitted flux, so the aperture cannot veto it;
    the aperture column is left empty instead.
    """
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    signal[20:45, 2:40] = -1.0
    signal += 8 * np.exp(-((xx - 20) ** 2 + (yy - 32) ** 2) / 8)
    _write_image(tmp_path / "image.fits", signal)
    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            signal, np.zeros_like(signal), np.ones_like(signal)
        ),
    )

    result = hebog.find_sources(
        _request(tmp_path), _config(profile=profile), SerialExecutor()
    )

    catalogue = read_catalogue_fits_product(result.catalogue)
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert len(catalogue.sources) == len(catalogue.gaussian_components) == 2
    assert not any(
        entry.status == "unavailable"
        for entry in diagnostics.measurement_dispositions
        if entry.object_kind == "source"
    )
    world = WCS(_header(signal.shape)).celestial
    gaussian = min(
        catalogue.gaussian_components,
        key=lambda row: float(
            np.hypot(
                *np.subtract(
                    world.all_world2pix(
                        row.position.right_ascension_degrees,
                        row.position.declination_degrees,
                        0,
                    ),
                    (20.0, 32.0),
                )
            )
        ),
    )
    source = next(
        row for row in catalogue.sources if row.source_id == gaussian.source_id
    )
    assert source.flux.integrated_flux_jy == pytest.approx(
        gaussian.flux.integrated_flux_jy
    )
    assert source.association_aperture_integrated_flux_jy is None
    assert not {
        "exact-owner-positive-residual-flux",
        "positive-exact-owner-flux",
    } & set(source.quality_flags)
    if profile == "continuum":
        assert "association-aperture-nonpositive" in source.quality_flags
        disposition = next(
            entry
            for entry in diagnostics.measurement_dispositions
            if entry.object_id == source.source_id
        )
        assert disposition.estimator == "summed-fitted-component-flux"
        # The case exercises the rule only while the aperture is negative.
        assert disposition.position_diagnostics is not None
        aperture = disposition.position_diagnostics.aperture_signed_flux_jy
        assert aperture is not None
        assert aperture < 0.0


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
    assert diagnostics.wide_object_counts == WideObjectCounts()
    assert diagnostics.profile == "continuum"
    assert diagnostics.configuration_qualification == "development-unqualified"
    assert diagnostics.provenance.input_sha256
    assert diagnostics.provenance.scientific_composition_sha256


@pytest.mark.integration
def test_public_wide_object_counts_record_every_round_decided_from_cores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one-pixel read budget puts every object on the wide paths, unchanged.

    No window fits a one-pixel budget, so each round decides every object
    from its cores: the ring's four lobes are four publication owners and
    four islands, one support component, and five segment rows (four
    components and one source), while no fit parent is deferred. The
    catalogue, dispositions, mask and RMS equal the windowed run's. A
    one-pixel compact bound then refuses the ring's one fit parent, so it is
    fitted island by island, and refuses each of its four islands too, so
    four fit parents are deferred: each island publishes its own source, so
    the support components and the source rows number four and the segment
    rows eight.
    """
    _write_image(tmp_path / "image.fits", _ring_image())
    reference = hebog.find_sources(
        _request(tmp_path, output_name="reference"),
        _config(),
        SerialExecutor(),
    )
    monkeypatch.setattr(public_api, "_OWNER_BATCH_READ_PIXELS", 1)

    result = hebog.find_sources(
        _request(tmp_path, output_name="wide"), _config(), SerialExecutor()
    )

    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.wide_object_counts == WideObjectCounts(
        publication_owners=4,
        support_components=1,
        deferred_fit_parents=0,
        islands=4,
        segments=5,
    )
    assert (diagnostics.island_count, diagnostics.source_count) == (4, 1)
    assert diagnostics.gaussian_component_count == 4
    expected_diagnostics = read_diagnostics_product(reference.diagnostics)
    assert isinstance(expected_diagnostics, PublicSourceFindingDiagnostics)
    assert (
        diagnostics.measurement_dispositions
        == expected_diagnostics.measurement_dispositions
    )
    catalogue = read_catalogue_fits_product(result.catalogue)
    expected_catalogue = read_catalogue_fits_product(reference.catalogue)
    assert catalogue.islands == expected_catalogue.islands
    assert catalogue.sources == expected_catalogue.sources
    assert (
        catalogue.gaussian_components == expected_catalogue.gaussian_components
    )
    for product in ("mask_path", "rms_path"):
        np.testing.assert_array_equal(
            fits.getdata(getattr(result, product)),
            fits.getdata(getattr(reference, product)),
            product,
        )

    reviewed_deblend = continuum.compact_deblend_config

    def one_pixel_deblend_bound(config: SourceFinderConfig) -> Any:
        return replace(
            reviewed_deblend(config), maximum_compact_bounds_pixels=1
        )

    monkeypatch.setattr(
        continuum, "compact_deblend_config", one_pixel_deblend_bound
    )
    deferred = hebog.find_sources(
        _request(tmp_path, output_name="deferred"),
        _config(),
        SerialExecutor(),
    )

    deferred_diagnostics = read_diagnostics_product(deferred.diagnostics)
    assert isinstance(deferred_diagnostics, PublicSourceFindingDiagnostics)
    assert deferred_diagnostics.wide_object_counts == WideObjectCounts(
        publication_owners=4,
        support_components=4,
        deferred_fit_parents=4,
        islands=4,
        segments=8,
    )
    assert deferred_diagnostics.deferred_deblend_parent_count > 0
    assert deferred_diagnostics.gaussian_component_count == 0
    assert deferred_diagnostics.source_count == 4


@pytest.mark.integration
def test_public_wide_object_counts_map_each_round_to_its_own_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each round's wide count reaches its own diagnostics field.

    Distinct sentinels replace the count each publishing round reports, so a
    swapped or dropped count would show in the payload. The two segment
    rounds, component rows and source rows, are the one field that sums.
    """
    _write_image(tmp_path / "image.fits", _ring_image())
    support_labels = public_api.publish_support_labels
    source_planes = public_api.publish_source_planes
    component_fits = public_api.publish_component_fits
    detection_islands = public_api.publish_detection_islands
    segment_rows = public_api.publish_segment_rows
    segment_sentinels = {"component-rows": 50, "source-rows": 7}

    def owners(*args: Any, **kwargs: Any) -> tuple[int, int, ZarrProductSink]:
        accepted, _, sink = support_labels(*args, **kwargs)
        return accepted, 11, sink

    def components(
        *args: Any, **kwargs: Any
    ) -> tuple[ZarrProductSink, ZarrProductSink, int]:
        labels, support, _ = source_planes(*args, **kwargs)
        return labels, support, 22

    def parents(
        *args: Any, **kwargs: Any
    ) -> tuple[TiledComponentFits, ZarrProductSink]:
        fitted, sink = component_fits(*args, **kwargs)
        return replace(fitted, wide_parent_count=33), sink

    def islands(*args: Any, **kwargs: Any) -> tuple[Any, Any, int]:
        rows, island_ids_by_owner, _ = detection_islands(*args, **kwargs)
        return rows, island_ids_by_owner, 44

    def segments(*args: Any, **kwargs: Any) -> tuple[Any, Any, Any, int]:
        rows, local_rms, positions, _ = segment_rows(*args, **kwargs)
        return (
            rows,
            local_rms,
            positions,
            segment_sentinels[kwargs["sink_name"]],
        )

    monkeypatch.setattr(public_api, "publish_support_labels", owners)
    monkeypatch.setattr(public_api, "publish_source_planes", components)
    monkeypatch.setattr(public_api, "publish_component_fits", parents)
    monkeypatch.setattr(public_api, "publish_detection_islands", islands)
    monkeypatch.setattr(public_api, "publish_segment_rows", segments)

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.wide_object_counts == WideObjectCounts(
        publication_owners=11,
        support_components=22,
        deferred_fit_parents=33,
        islands=44,
        segments=57,
    )


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
    """Empty science remains successful without inventing sources or RMS.

    Three finite pixels are fewer than any background window needs, so no
    pixel has an estimate, which is the all-NaN image's case.
    """
    three_finite_pixels = np.full(shape, np.nan)
    three_finite_pixels.flat[:: three_finite_pixels.size // 3] = 1.0
    for name, values, expected_rms_status in (
        ("blank", np.zeros(shape), "unavailable"),
        ("all-nan", np.full(shape, np.nan), "unavailable"),
        ("constant-negative", np.full(shape, -2.0), "unavailable"),
        ("three-finite-pixels", three_finite_pixels, "unavailable"),
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
def test_zero_padding_beside_noise_is_blanked_and_publishes_no_zero_noise(
    tmp_path: Path,
) -> None:
    """A constant region is invalid up to its last pixel, as NaN padding is.

    150 zero-valued columns beside noise published an RMS of exactly zero
    on 82,956 pixels and under 1e-6 on 3,703 more, under a valid status.
    The zeros are now outside the image: the RMS is NaN over every one of
    them, and the sources in the noise are measured as before.
    """
    shape = (600, 600)
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    image = np.random.default_rng(7).normal(0.0, 1e-4, shape)
    for y, x in ((450, 300), (300, 160)):
        image += 8e-4 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 5.78)
    image[:, :150] = 0.0
    _write_image(tmp_path / "image.fits", image.astype(np.float32))

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    rms = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    assert result.rms.scientific_status == "valid"
    assert np.isnan(rms[:, :150]).all()
    assert np.isfinite(rms[:, 150:]).all()
    assert rms[:, 150:].min() > 5e-5
    assert result.source_count == 2


@pytest.mark.integration
@pytest.mark.parametrize(
    "region", ("zeros-between-nan-rows", "one-value-dithered-by-rounding")
)
def test_valid_pixels_without_noise_publish_no_noise_of_their_own(
    tmp_path: Path,
    region: str,
) -> None:
    """Pixels that no square of one value holds can still carry no noise.

    Zero rows between NaN rows, and one value dithered by a unit of single
    precision from pixel to pixel, hold no 3x3 square of one value, so they
    are valid. A window whose only valid samples they are has a spread of
    zero, or under single precision's resolution at its largest value, the
    noise floor: it is unavailable, so those pixels take the estimate of the
    nearest window that measures noise, and no RMS of zero or of rounding
    (about 6e-8 here) is published. The nearest such window mixes the
    region with the noise beside it and reads a lower noise than the noise
    (as low as 2e-5 beside the dithered value), as at any sharp step in the
    noise; the floor is not meant to change that.
    """
    image = np.random.default_rng(11).normal(0.0, 1.0, (200, 240))
    if region == "zeros-between-nan-rows":
        image[:, :150] = 0.0
        image[::2, :150] = np.nan
    else:
        one = np.float32(1.0)
        rounding = np.nextafter(one, np.float32(2.0))
        image[:, :150] = np.where(
            np.indices((200, 150)).sum(axis=0) % 2, rounding, one
        )
    _write_image(tmp_path / "image.fits", image.astype(np.float32))

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    rms = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    assert result.rms.scientific_status == "valid"
    np.testing.assert_array_equal(np.isfinite(rms), np.isfinite(image))
    assert rms[np.isfinite(rms)].min() > 1e-5


@pytest.mark.integration
def test_pixels_no_background_window_can_measure_leave_noise_unavailable(
    tmp_path: Path,
) -> None:
    """Six finite pixels fill one fine noise window but no coarse one.

    A 160-pixel image has 40-pixel coarse windows every 13 pixels, and none
    holds the six samples the statistic needs, so no pixel has a background.
    The 35-pixel fine window that does hold them lends the image no noise of
    its own: the estimate is unavailable as a whole, as for an all-NaN image.
    """
    values = np.full((160, 160), np.nan)
    for value, pixel in enumerate(
        ((7, 7), (7, 41), (41, 7), (41, 41), (24, 24), (24, 26)), start=1
    ):
        values[pixel] = float(value)
    _write_image(tmp_path / "image.fits", values)

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    assert result.rms.scientific_status == "unavailable"
    assert result.source_count == 0
    assert result.island_count == 0
    published = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    assert np.all(np.isnan(published))


def _crowded_field(
    shape_yx: tuple[int, int],
    spacing_pixels: float,
) -> tuple[npt.NDArray[np.float64], tuple[tuple[int, int], ...]]:
    """Return unit white noise under a beam-shaped source every spacing.

    Peaks are log-uniform from 10 to 100 times the noise on a grid jittered
    by up to a quarter of its spacing; each source is stamped six beam
    sigmas out. Each source's peak pixel, or the image pixel nearest it for a
    source jittered past the far edge, is returned in ``(y, x)`` order.
    """
    jitter = spacing_pixels / 4.0
    beam_sigma_pixels = 4.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    stamp_radius = int(np.ceil(6.0 * beam_sigma_pixels))
    generator = np.random.default_rng(36)
    image = generator.normal(0.0, 1.0, shape_yx)
    peaks: list[tuple[int, int]] = []
    centres_y = np.arange(spacing_pixels / 2.0, shape_yx[0], spacing_pixels)
    centres_x = np.arange(spacing_pixels / 2.0, shape_yx[1], spacing_pixels)
    for y_centre in centres_y:
        for x_centre in centres_x:
            y = y_centre + generator.uniform(-jitter, jitter)
            x = x_centre + generator.uniform(-jitter, jitter)
            peak = np.exp(generator.uniform(np.log(10.0), np.log(100.0)))
            y_start = max(0, round(y) - stamp_radius)
            x_start = max(0, round(x) - stamp_radius)
            y_pixels, x_pixels = np.mgrid[
                y_start : round(y) + stamp_radius + 1,
                x_start : round(x) + stamp_radius + 1,
            ]
            stamp = peak * np.exp(
                -((x_pixels - x) ** 2 + (y_pixels - y) ** 2)
                / (2.0 * beam_sigma_pixels**2)
            )
            target = image[
                y_start : y_start + stamp.shape[0],
                x_start : x_start + stamp.shape[1],
            ]
            target += stamp[: target.shape[0], : target.shape[1]]
            peaks.append(
                (
                    min(round(y), shape_yx[0] - 1),
                    min(round(x), shape_yx[1] - 1),
                )
            )
    return image, tuple(peaks)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("shape_yx", "spacing_pixels"),
    (((160, 224), 20.0), ((300, 300), 28.0), ((600, 600), 20.0)),
)
def test_a_field_too_crowded_for_source_free_noise_is_measured(
    tmp_path: Path,
    shape_yx: tuple[int, int],
    spacing_pixels: float,
) -> None:
    """A field too crowded to protect is measured with unprotected noise.

    At these spacings no 35-pixel fine window lies 17 pixels clear of every
    island, so the local noise keeps no sample and the sigma-clipped coarse
    estimate stands unprotected. Below 600 pixels a side the coarse estimate
    is source-protected too: at 160 by 224 protection keeps no pixel, and at
    300 square it keeps eight, whose estimate would put the noise at a third
    of its true value. Such fields used to be refused because the estimate no
    longer covered the image.
    """
    image, peaks = _crowded_field(shape_yx, spacing_pixels)
    _write_image(tmp_path / "image.fits", image)

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    assert result.rms.scientific_status == "valid"
    rms = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    assert np.all(rms > 0.0)
    assert abs(float(np.median(rms)) - 1.0) < 0.15
    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    assert all(mask[peak] for peak in peaks)
    assert result.island_count == len(peaks)


@pytest.mark.integration
@pytest.mark.parametrize("shape_yx", ((160, 224), (600, 600)))
def test_a_crowded_field_is_fitted_island_by_island(
    tmp_path: Path,
    shape_yx: tuple[int, int],
) -> None:
    """A fit parent too large to fit whole is fitted one island at a time.

    With a source every 20 pixels every eight-pixel fit context touches its
    neighbours', so one parent holds the whole field: at 160 by 224 its 88
    components exceed one joint fit's 16, and at 600 square its window
    exceeds the compact read bound. Fitted whole it deferred every component,
    and with no compact model to subtract, association joined the islands.
    """
    image, peaks = _crowded_field(shape_yx, 20.0)
    _write_image(tmp_path / "image.fits", image)

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert not any(
        entry.status == "deferred"
        for entry in diagnostics.measurement_dispositions
    )
    assert result.island_count == len(peaks)
    assert result.source_count == len(peaks)
    assert result.gaussian_component_count == len(peaks)


def _correlated_crowded_field(
    size: int, spacing: int
) -> tuple[
    npt.NDArray[np.float32], fits.Header, list[tuple[float, float, bool]]
]:
    """Return a square crowded field in beam-correlated noise.

    The noise, beam and header are the quick check's ``quick-dense-field``
    recipe at ``size`` pixels a side. A source sits every ``spacing``
    pixels, jittered by up to a third of it, with peak SNR log-uniform from
    5 to 300; one in ten is resolved, with a major sigma of 4 to 9 pixels.
    Each injected source is returned as ``(x, y, resolved)``. The image is
    not that recipe's, so the header drops its dataset provenance cards.
    """
    (dataset,) = (
        record
        for record in load_dataset_manifest(_QUICK_CHECK_DATASETS).datasets
        if record.identifier == "quick-dense-field"
    )
    recipe = dataset.recipe.model_copy(
        update={"sources": (), "shape_yx": (size, size)}
    )
    dataset = dataset.model_copy(
        update={
            "wcs": dataset.wcs.model_copy(
                update={"reference_pixel_xy": (size / 2, size / 2)}
            )
        }
    )
    image = generate_synthetic_window(
        recipe, y_start=0, y_stop=size, x_start=0, x_stop=size
    )
    generator = np.random.default_rng(20260926)
    sources: list[tuple[float, float, bool]] = []
    for y_centre in np.arange(spacing / 2, size, spacing):
        for x_centre in np.arange(spacing / 2, size, spacing):
            y = y_centre + generator.uniform(-spacing / 3, spacing / 3)
            x = x_centre + generator.uniform(-spacing / 3, spacing / 3)
            peak = recipe.noise_rms * np.exp(
                generator.uniform(np.log(5.0), np.log(300.0))
            )
            resolved = bool(generator.uniform() < 0.1)
            if resolved:
                major = generator.uniform(4.0, 9.0)
                minor = generator.uniform(2.5, major)
                angle = generator.uniform(0.0, np.pi)
            else:
                major, minor, angle = 2.1233045007200477, 1.6986436005760381, 0
            reach = int(np.ceil(6 * major))
            y0, y1 = max(0, int(y) - reach), min(size, int(y) + reach + 1)
            x0, x1 = max(0, int(x) - reach), min(size, int(x) + reach + 1)
            dy = np.arange(y0, y1)[:, np.newaxis] - y
            dx = np.arange(x0, x1)[np.newaxis, :] - x
            along = np.cos(angle) * dx + np.sin(angle) * dy
            across = -np.sin(angle) * dx + np.cos(angle) * dy
            image[y0:y1, x0:x1] += peak * np.exp(
                -0.5 * ((along / major) ** 2 + (across / minor) ** 2)
            )
            sources.append((x, y, resolved))
    header = synthetic_fits_header(dataset)
    del header["HEBOGDS"]
    del header["HEBOGRCP"]
    return image.astype(np.float32), header, sources


@pytest.mark.integration
@pytest.mark.parametrize(
    ("size", "spacing", "islands", "fitted_compact", "compact_joins"),
    (
        (256, 24, 105, 80, set[frozenset[int]]()),
        (512, 32, 233, 190, {frozenset({76, 77})}),
    ),
)
def test_compact_sources_in_a_crowded_correlated_field_stay_separate(  # noqa: PLR0913, PLR0917
    tmp_path: Path,
    size: int,
    spacing: int,
    islands: int,
    fitted_compact: int,
    compact_joins: set[frozenset[int]],
) -> None:
    """Noise, crowding and chance alignments do not join compact neighbours.

    In beam-correlated noise with a source every 24 or 32 pixels, coherent
    3-sigma noise features of either sign lie in most fit windows, and the
    sources' wings raise the sigma-clipped background into a negative
    plateau between them. A residual feature fails a compact model only if
    it is positive, holds a detection-threshold seed and touches the model's
    own support, and then fails only the compact groups it touches, not the
    whole fit parent. The coarse support joins the field into one region
    with many holes, about which resolved sources far apart can lie
    tangentially by chance; a loop holds only arcs on its hole's rim, so no
    loop forms. No fitted compact source then shares a source with another
    injected source, with one exception: in the 512-pixel field resolved
    source 60 lies on the wing of the much brighter resolved source 76 with
    no peak of its own, so it gets no component, and its residual joins the
    compact source 77 beside 76 to it; without source 60 the two stay apart.
    (Compact source 61, beside them, shared their island and source until
    plan task 63 raised the noise there to the coarse estimate, which splits
    it off.) Residual and arc evidence still join a few resolved
    sources. The test exempts them and that one group, and fails once
    either exemption no longer matches.
    """
    image, header, injected = _correlated_crowded_field(size, spacing)
    fits.PrimaryHDU(image[np.newaxis, np.newaxis], header=header).writeto(
        tmp_path / "image.fits"
    )

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    assert result.island_count == islands
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert not any(
        evidence.reason == "resolved-loop"
        for entry in diagnostics.measurement_dispositions
        for evidence in entry.association_evidence
    )
    components = read_catalogue_fits_product(
        result.catalogue
    ).gaussian_components
    positions = np.asarray(
        WCS(header).celestial.all_world2pix(
            [
                (
                    row.position.right_ascension_degrees,
                    row.position.declination_degrees,
                )
                for row in components
            ],
            0,
        )
    )
    truth = np.asarray([(x, y) for x, y, _ in injected])
    distances = np.hypot(
        positions[:, np.newaxis, 0] - truth[np.newaxis, :, 0],
        positions[:, np.newaxis, 1] - truth[np.newaxis, :, 1],
    )
    nearest = distances.argmin(axis=1)
    beam_major_pixels = 5.0
    injected_by_source: dict[str, set[int]] = {}
    for row, index, distance in zip(
        components, nearest, distances.min(axis=1), strict=True
    ):
        if distance <= beam_major_pixels:
            injected_by_source.setdefault(row.source_id, set()).add(int(index))
    compact = {
        index
        for index, (_, _, resolved) in enumerate(injected)
        if not resolved
    }
    found = {
        index for indexes in injected_by_source.values() for index in indexes
    }
    joined = [
        frozenset(indexes)
        for indexes in injected_by_source.values()
        if len(indexes) > 1
    ]
    # Most compact sources are fitted, so the check below is not vacuous;
    # the faintest and those inside a resolved neighbour are not.
    assert len(found & compact) >= fitted_compact
    assert {group for group in joined if group & compact} == compact_joins
    # The resolved exemption still matches: resolved sources remain joined.
    assert any(not group & compact for group in joined)


_QUIET_STRIP_COLUMNS = 40
_CROWDED_FIELD_NOISE_JY_PER_BEAM = 1e-4


def _write_quiet_strip_field(directory: Path) -> npt.NDArray[np.float32]:
    """Write the quick check's crowded field with a quiet strip.

    The left 40 columns, sources included, are scaled by 0.2, so the noise
    steps from 2e-5 to 1e-4 Jy/beam at column 40. The written plane is
    returned.
    """
    (dataset,) = (
        record
        for record in load_dataset_manifest(_QUICK_CHECK_DATASETS).datasets
        if record.identifier == "quick-crowded-field"
    )
    height, width = dataset.recipe.shape_yx
    image = generate_synthetic_window(
        dataset.recipe, y_start=0, y_stop=height, x_start=0, x_stop=width
    ).astype(np.float32)
    image[:, :_QUIET_STRIP_COLUMNS] *= np.float32(0.2)
    header = synthetic_fits_header(dataset)
    del header["HEBOGDS"]
    del header["HEBOGRCP"]
    fits.PrimaryHDU(image[np.newaxis, np.newaxis], header=header).writeto(
        directory / "image.fits"
    )
    return image


@pytest.fixture(scope="module")
def quiet_strip_field(
    tmp_path_factory: pytest.TempPathFactory,
) -> _SerialReference:
    """Publish the crowded field with a quiet strip, serially."""
    directory = tmp_path_factory.mktemp("quiet-strip")
    _write_quiet_strip_field(directory)
    config = _config()
    result = hebog.find_sources(_request(directory), config, SerialExecutor())
    return _SerialReference(directory / "image.fits", config, result)


@pytest.mark.integration
def test_a_crowded_field_with_a_quiet_strip_restores_a_split_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substituted_background_rms: SubstituteBackgroundRms,
) -> None:
    """The quick check's crowded field, its left 40 columns scaled by 0.2.

    Support refinement labelled a recovered pixel of one owner's own flood
    with the neighbouring owner nearest to it, so the restore round saw the
    owner whole while publication split it into its body and a pixel two
    rows below, and the bridge round stopped the run with a bare
    ``ValueError`` (plan task 61). The owner is now restored, and its tail
    joins that pixel to the body in the published mask.

    The field reached that round through the noise it published before plan
    task 63: about a third of the noise beside the strip. That estimate is
    stood in for here, by column, so the round is still reached; on the code
    before task 61 it gives the same refusal.
    """
    image = np.asarray(_write_quiet_strip_field(tmp_path), dtype=np.float64)
    columns = np.arange(image.shape[1])
    collapsed_rms = np.where(
        columns < _QUIET_STRIP_COLUMNS,
        2e-5,
        np.where(columns < 199, 3.4477e-5, _CROWDED_FIELD_NOISE_JY_PER_BEAM),
    )
    monkeypatch.setattr(
        public_api,
        "_estimate_background_rms",
        substituted_background_rms(
            image,
            np.zeros_like(image),
            np.array(np.broadcast_to(collapsed_rms, image.shape)),
        ),
    )

    result = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )

    mask = np.asarray(fits.getdata(result.mask_path), dtype=np.bool_)
    islands, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=np.ones((3, 3), dtype=np.int8)),
    )
    # The refused owner's body, and the pixel its tail ends on.
    body, tail_end = islands[372, 42], islands[382, 42]
    assert body > 0
    assert tail_end == body


@pytest.mark.integration
def test_the_rms_beside_a_noise_step_reads_the_noise_there(
    quiet_strip_field: _SerialReference,
) -> None:
    """The noise beside a quiet strip is published as that noise.

    Nearly every fine window of this field's bright-region grid touches
    protected support. A few came clean inside the quiet strip, and every
    other cell took the nearest of them, so columns 40 to 198 published
    3.4e-5 Jy/beam where the noise is 1e-4, and the field 1,364 sources,
    484 of them in columns 40 to 199 against 155 unscaled (plan task 63).
    """
    result = quiet_strip_field.result
    noise = _CROWDED_FIELD_NOISE_JY_PER_BEAM

    rms = np.asarray(fits.getdata(result.rms.path), dtype=np.float64)
    beside = rms[:, _QUIET_STRIP_COLUMNS:199]
    celestial = WCS(fits.getheader(quiet_strip_field.image_path)).celestial
    columns = np.array(
        [
            celestial.world_to_pixel_values(
                row.position.right_ascension_degrees,
                row.position.declination_degrees,
            )[0]
            for row in read_catalogue_fits_product(result.catalogue).sources
        ]
    )

    assert np.median(beside) == pytest.approx(noise, rel=0.1)
    assert np.percentile(beside, 5) >= 0.7 * noise
    assert np.min(beside) >= 0.5 * noise
    # 155 sources lie in these columns of the unscaled field, 996 in all.
    assert (
        np.count_nonzero((columns >= _QUIET_STRIP_COLUMNS) & (columns < 200))
        <= 175
    )
    assert result.source_count <= 1050


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


@dataclass(frozen=True, slots=True)
class _SerialReference:
    """One shared input and the products a serial run published from it.

    ``fit_outcome`` names the fitting failure injected into that run, which
    a run compared with it must inject too.
    """

    image_path: Path
    config: SourceFinderConfig
    result: SourceFinderResult
    fit_outcome: str = "normal"


def _run_on_small_tiles(
    reference: _SerialReference,
    output_directory: Path,
    executor: Executor,
    monkeypatch: pytest.MonkeyPatch,
) -> SourceFinderResult:
    """Run the reference's input again, on 97-by-111 background tiles."""
    monkeypatch.setattr(public_api, "_TILE_SHAPE_YX", (97, 111))
    return hebog.find_sources(
        SourceFinderRequest(
            reference.image_path, output_directory, reference.result.run_id
        ),
        reference.config,
        executor,
    )


@pytest.fixture(
    scope="module",
    params=tuple(
        pytest.param(
            (shape, island_sigma, include_source),
            id=f"{shape[0]}x{shape[1]}-island{island_sigma:g}-"
            + ("source" if include_source else "noise"),
        )
        for shape in ((149, 181), (150, 181), (256, 301))
        for island_sigma in (75.0, 80.0)
        for include_source in (False, True)
    ),
)
def high_threshold_reference(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> _SerialReference:
    """Publish one high-threshold control serially on the default tiles."""
    shape, island_sigma, include_source = cast(
        tuple[tuple[int, int], float, bool], request.param
    )
    directory = tmp_path_factory.mktemp("high-threshold")
    _write_image(
        directory / "image.fits",
        _high_threshold_image(shape, include_source=include_source),
    )
    config = SourceFinderConfig(100.0, island_sigma, 7)
    result = hebog.find_sources(
        _request(directory, output_name="serial"), config, SerialExecutor()
    )
    assert result.source_count == int(include_source)
    assert result.gaussian_component_count == int(include_source)
    return _SerialReference(directory / "image.fits", config, result)


@pytest.mark.integration
def test_custom_thresholds_publish_the_serial_products_under_every_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    high_threshold_reference: _SerialReference,
    each_executor: Executor,
) -> None:
    """Private threshold reconciliation cannot depend on executor or tiles."""
    tiled = _run_on_small_tiles(
        high_threshold_reference,
        tmp_path / "products",
        each_executor,
        monkeypatch,
    )

    assert product_hashes(tiled) == product_hashes(
        high_threshold_reference.result
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
        match=r"BUNIT=Jy/beam, not Jy$",
    ):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_public_preview_rejects_inputs_beyond_qualified_envelope(
    tmp_path: Path,
) -> None:
    """The finder never extrapolates past the qualified envelope."""
    _write_image(tmp_path / "image.fits", np.zeros((2, 15403)))

    with pytest.raises(SourceFinderImageTooLargeError, match="15402"):
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
    _write_image(tmp_path / "image.fits", np.zeros((2, 15402)))

    result = hebog.find_sources(
        _request(tmp_path), _config(), _RecordingExecutor()
    )

    assert result.source_count == 0


def _inject_fit_outcome(
    monkeypatch: pytest.MonkeyPatch, fit_outcome: str
) -> None:
    """Make every Gaussian fit fail the named way, or leave fitting alone."""
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


def _executor_case_image(image_kind: str) -> np.ndarray:
    """Return the shell, the ellipse or the coarse-protection field."""
    if image_kind == "ellipse":
        yy, xx = np.mgrid[:49, :65]
        image = 100 * np.exp(
            -0.5 * (((xx - 32.3) / 6) ** 2 + ((yy - 24.1) / 2) ** 2)
        )
        return image + np.random.default_rng(2409).normal(0, 0.3, image.shape)
    if image_kind == "coarse-protection":
        yy, xx = np.mgrid[:256, :384]
        radius_squared = (yy - 128) ** 2 + (xx - 192) ** 2
        # Noise correlated over the header's 4-pixel beam, as in a radio
        # image. On white noise the broad halo deblends into more components
        # than one joint fit admits, so no fit, and no injected failure, runs.
        noise = ndimage.gaussian_filter(
            np.random.default_rng(620).normal(size=xx.shape),
            4.0 / np.sqrt(8.0 * np.log(2.0)),
        )
        image = -2 + xx / 1024 + noise / np.std(noise)
        image += 12 * np.exp(-radius_squared / (2 * 20**2))
        return image + 1000 * np.exp(-radius_squared / (2 * 2**2))
    return _ring_image()


def _require_injected_fit_outcome(
    result: SourceFinderResult, fit_outcome: str
) -> None:
    """Require the diagnostics to record the injected fitting failure."""
    if fit_outcome == "normal":
        return
    expected_reason = (
        "fit-linear-algebra-failure"
        if fit_outcome == "linear-algebra-failure"
        else "fit-model-inadequate"
    )
    diagnostic = read_diagnostics_product(result.diagnostics_path)
    assert isinstance(diagnostic, PublicSourceFindingDiagnostics)
    assert any(
        row.reason == expected_reason and not row.catalogue_row_published
        for row in diagnostic.measurement_dispositions
    )
    assert result.source_count > 0
    if fit_outcome == "inadequate-fallback":
        # One coarse-protection fit is inadequate without the fault, so
        # the injected rejection is also checked where each fit records it.
        assert any(
            row.fit_diagnostics is not None
            and row.fit_diagnostics.fallback_reason
            == "free-model-invalid-result"
            for row in diagnostic.measurement_dispositions
        )


@pytest.fixture(
    scope="module",
    params=tuple(
        pytest.param(case, id="-".join(case))
        for case in (
            ("shell", "normal"),
            ("shell", "linear-algebra-failure"),
            ("ellipse", "inadequate-fallback"),
            ("coarse-protection", "normal"),
            ("coarse-protection", "linear-algebra-failure"),
            ("coarse-protection", "inadequate-fallback"),
        )
    ),
)
def fitted_reference(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> _SerialReference:
    """Publish one fitted field serially on the default tiles."""
    image_kind, fit_outcome = cast(tuple[str, str], request.param)
    directory = tmp_path_factory.mktemp(image_kind)
    _write_image(directory / "image.fits", _executor_case_image(image_kind))
    with pytest.MonkeyPatch.context() as monkeypatch:
        _inject_fit_outcome(monkeypatch, fit_outcome)
        result = hebog.find_sources(
            _request(directory, output_name="serial"),
            _config(),
            SerialExecutor(),
        )
    _require_injected_fit_outcome(result, fit_outcome)
    return _SerialReference(
        directory / "image.fits", _config(), result, fit_outcome
    )


@pytest.mark.integration
def test_every_executor_on_other_tiles_publishes_the_serial_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fitted_reference: _SerialReference,
    each_executor: Executor,
) -> None:
    """Caller-owned execution policy cannot alter any scientific bytes."""
    _inject_fit_outcome(monkeypatch, fitted_reference.fit_outcome)

    tiled = _run_on_small_tiles(
        fitted_reference, tmp_path / "products", each_executor, monkeypatch
    )

    assert product_hashes(tiled) == product_hashes(fitted_reference.result)


@pytest.mark.integration
def test_dask_process_workers_publish_the_serial_products(
    tmp_path: Path,
) -> None:
    """Every task crosses a process boundary and no product byte changes.

    Each worker is its own Python process, so every task's arguments and
    result are pickled on the way there and back, which in-process workers
    never do: a value that does not survive that exactly, such as an Astropy
    ``WCS`` rebuilt from a header it reformats, would change the products.
    The field has a fitted bright source on a broad halo, local-noise
    refinement and six background tiles.
    """
    _write_image(
        tmp_path / "image.fits", _executor_case_image("coarse-protection")
    )
    serial = hebog.find_sources(
        _request(tmp_path, output_name="serial"), _config(), SerialExecutor()
    )
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=True,
        # A random port, so parallel test workers never contend for one.
        dashboard_address=":0",
    )
    with cluster, Client(cluster, timeout="60s") as client:
        worker_processes = cast(dict[str, int], client.run(os.getpid))
        task_stream = get_task_stream(client=client)
        with task_stream:
            processes = hebog.find_sources(
                _request(tmp_path, output_name="processes"),
                _config(),
                DaskExecutor(client),
            )

    assert os.getpid() not in worker_processes.values()
    task_workers = {cast(str, task["worker"]) for task in task_stream.data}
    assert task_workers
    assert task_workers <= set(worker_processes)
    assert product_hashes(processes) == product_hashes(serial)


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
    _write_image(tmp_path / "image.fits", np.zeros((2, 15403)))

    def forbidden_hash(_path: Path) -> str:
        pytest.fail("oversized input was hashed")

    monkeypatch.setattr(public_api, "_file_sha256", forbidden_hash)

    with pytest.raises(SourceFinderImageTooLargeError, match="15402"):
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


@pytest.mark.integration
def test_a_failed_header_read_is_an_invalid_input_naming_the_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure outside header validation still names the input file.

    Header-contract refusals carry the reader's own reason; anything else
    that fails while the header is read, such as the device under an open
    file, falls back to naming the file.
    """
    _write_image(tmp_path / "image.fits", np.zeros((8, 8)))

    def unreadable(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected read failure")

    monkeypatch.setattr(public_api.FitsImageSource, "metadata", unreadable)

    with pytest.raises(
        InvalidSourceFinderInputError,
        match=r"invalid FITS source-finder input: .*image\.fits$",
    ):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


class _AnalysisStartedError(Exception):
    """The run passed every admission check and reached the executor."""


class _StoppingExecutor(SerialExecutor):
    """Executor double that ends a run at its first submitted work."""

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[Output]:
        """Stop the run instead of executing anything."""
        del function, batches, requirement
        raise _AnalysisStartedError


def _write_empty_image(
    path: Path, shape_yx: tuple[int, int], *, beam_pixels: float = 4.0
) -> None:
    """Write blank sky with one-arcsecond pixels and a circular beam."""
    header = _header(shape_yx)
    header["BMAJ"] = header["BMIN"] = beam_pixels / 3600.0
    fits.PrimaryHDU(
        data=np.zeros(shape_yx, dtype=np.float32), header=header
    ).writeto(path)


@pytest.mark.integration
@pytest.mark.parametrize("profile", ("continuum", "compact"))
@pytest.mark.parametrize(
    "shape_yx", ((400, 2600), (2600, 400), (599, 1670), (149, 7000))
)
def test_a_narrow_image_over_the_bounded_read_is_refused_before_analysis(
    tmp_path: Path, shape_yx: tuple[int, int], profile: str
) -> None:
    """Given an image under 600 pixels wide with over a million pixels,
    when the finder is asked for either profile,
    then it states the rule and analyses nothing.

    The background meshes cannot shrink to a strip that narrow, and one
    estimate for the whole image may read at most a million pixels.
    """
    _write_empty_image(tmp_path / "image.fits", shape_yx)
    executor = _RecordingExecutor()

    with pytest.raises(
        SourceFinderImageTooLargeError,
        match=(
            "at most 1,000,000 pixels in an image whose shorter side is "
            f"under 600 pixels, not {shape_yx[0]} by {shape_yx[1]}"
        ),
    ):
        hebog.find_sources(
            _request(tmp_path), _config(profile=profile), executor
        )

    assert executor.batch_counts == []
    assert not (tmp_path / "products").exists()


@pytest.mark.integration
@pytest.mark.parametrize("profile", ("continuum", "compact"))
@pytest.mark.parametrize("shape_yx", ((599, 1669), (600, 1700), (149, 6700)))
def test_an_image_on_the_admitted_side_of_the_narrow_rule_is_analysed(
    tmp_path: Path, shape_yx: tuple[int, int], profile: str
) -> None:
    """The rule refuses nothing the stages can serve: a narrow image of at
    most a million pixels, and any image at least 600 pixels wide.
    """
    _write_empty_image(tmp_path / "image.fits", shape_yx)

    with pytest.raises(_AnalysisStartedError):
        hebog.find_sources(
            _request(tmp_path), _config(profile=profile), _StoppingExecutor()
        )


@pytest.mark.integration
@pytest.mark.parametrize("profile", ("continuum", "compact"))
@pytest.mark.parametrize(
    ("shape_yx", "beam_pixels"),
    (
        # Just past the limit, and the width at which the limit used to be.
        ((64, 64), 10.5),
        # A thousandth of a pixel past it, the precision of the comparison.
        ((64, 64), 10.001),
        ((1100, 1100), 22.0),
        # The width at which local-noise refinement failed mid-run.
        ((1100, 1100), 26.0),
        # A beam given in arcseconds where the header means degrees.
        ((64, 64), 14_400.0),
    ),
)
def test_a_beam_wider_than_10_pixels_is_refused_before_analysis(
    tmp_path: Path,
    shape_yx: tuple[int, int],
    beam_pixels: float,
    profile: str,
) -> None:
    """Given a restoring beam wider than 10 pixels,
    when the finder is asked for either profile,
    then it states the limit and its measured reason and builds nothing.

    The meshes are fixed in pixels, and on injected sources the continuum
    profile misses some at 12 pixels of beam.
    """
    _write_empty_image(
        tmp_path / "image.fits", shape_yx, beam_pixels=beam_pixels
    )
    executor = _RecordingExecutor()

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match=(
            "a restoring beam of at most 10 pixels FWHM, "
            f"not {beam_pixels:g}: its background and noise meshes are fixed "
            "in pixels, and on injected sources they miss sources from 12 "
            "pixels of beam"
        ),
    ):
        hebog.find_sources(
            _request(tmp_path), _config(profile=profile), executor
        )

    assert executor.batch_counts == []
    assert not (tmp_path / "products").exists()


@pytest.mark.integration
@pytest.mark.parametrize("profile", ("continuum", "compact"))
@pytest.mark.parametrize("shape_yx", ((64, 64), (1100, 1100)))
@pytest.mark.parametrize("beam_pixels", (10.0, 10.0004))
def test_a_beam_at_the_limit_is_analysed(
    tmp_path: Path,
    shape_yx: tuple[int, int],
    profile: str,
    beam_pixels: float,
) -> None:
    """The stated limit is the widest admitted beam, not the first refused.

    The width is compared to a thousandth of a pixel: the WCS Jacobian it
    comes through rounds differently by platform, and a beam stated as
    exactly 10 pixels read 10.000001 on Linux in the beam study's geometry.
    """
    _write_empty_image(
        tmp_path / "image.fits", shape_yx, beam_pixels=beam_pixels
    )

    with pytest.raises(_AnalysisStartedError):
        hebog.find_sources(
            _request(tmp_path), _config(profile=profile), _StoppingExecutor()
        )


@pytest.mark.integration
def test_a_beam_with_no_size_in_pixels_is_refused_before_analysis(
    tmp_path: Path,
) -> None:
    """A pixel scale of nearly zero gives the beam no finite pixel width."""
    header = _header((64, 64))
    header["CDELT1"], header["CDELT2"] = -1e-12, 1e-12
    fits.PrimaryHDU(data=np.zeros((64, 64)), header=header).writeto(
        tmp_path / "image.fits"
    )
    executor = _RecordingExecutor()

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError, match="restoring beam"
    ):
        hebog.find_sources(_request(tmp_path), _config(), executor)

    assert executor.batch_counts == []


@pytest.mark.integration
@pytest.mark.filterwarnings("ignore:File may have been truncated")
def test_a_truncated_image_is_refused_before_analysis(tmp_path: Path) -> None:
    """A file that ends early is an invalid input, not a failed read."""
    image = tmp_path / "image.fits"
    _write_image(image, _ring_image())
    image.write_bytes(image.read_bytes()[:-2880])
    executor = _RecordingExecutor()

    with pytest.raises(InvalidSourceFinderInputError, match="is truncated"):
        hebog.find_sources(_request(tmp_path), _config(), executor)

    assert executor.batch_counts == []
    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_scaled_integer_pixels_publish_the_sources_of_the_same_floats(
    tmp_path: Path,
) -> None:
    """Given an image stored as 16-bit integers with BSCALE and BZERO,
    when the finder runs,
    then it publishes what it publishes for the same values as floats.
    """
    scale, zero = 2e-3, 30.0
    stored = np.round((_ring_image() - zero) / scale).astype(np.int16)
    _write_image(tmp_path / "image.fits", zero + scale * stored)
    fits.PrimaryHDU(data=stored, header=_header(stored.shape)).writeto(
        tmp_path / "integers.fits"
    )
    with fits.open(
        tmp_path / "integers.fits",
        mode="update",
        do_not_scale_image_data=True,
    ) as hdus:
        cast(Any, hdus[0]).header.update(BSCALE=scale, BZERO=zero)

    floats = hebog.find_sources(
        _request(tmp_path), _config(), SerialExecutor()
    )
    integers = hebog.find_sources(
        SourceFinderRequest(
            tmp_path / "integers.fits",
            tmp_path / "integer-products",
            "public-contract",
        ),
        _config(),
        SerialExecutor(),
    )

    float_sources = read_catalogue_fits_product(floats.catalogue).sources
    integer_sources = read_catalogue_fits_product(integers.catalogue).sources
    assert len(float_sources) > 0
    assert len(integer_sources) == len(float_sources)
    for integer_source, float_source in zip(
        integer_sources, float_sources, strict=True
    ):
        assert integer_source.position.right_ascension_degrees == (
            pytest.approx(
                float_source.position.right_ascension_degrees, abs=1e-7
            )
        )
        assert integer_source.flux.integrated_flux_jy == pytest.approx(
            float_source.flux.integrated_flux_jy, rel=1e-4
        )


@pytest.mark.integration
def test_numpy_configuration_values_publish_under_the_plain_identity(
    tmp_path: Path,
) -> None:
    """Thresholds computed with NumPy are the configuration they equal.

    The run records a hash of its configuration, which once failed on a
    NumPy scalar only after the whole analysis had finished.
    """
    _write_image(tmp_path / "image.fits", _ring_image())

    result = hebog.find_sources(
        _request(tmp_path),
        SourceFinderConfig(
            np.float32(5.0),  # type: ignore[arg-type]
            np.float64(3.0),
            np.int64(7),  # type: ignore[arg-type]
        ),
        SerialExecutor(),
    )

    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.provenance.configuration_sha256 == (
        public_api._canonical_sha256(  # pyright: ignore[reportPrivateUsage]
            {
                "detection_threshold_sigma": 5.0,
                "island_threshold_sigma": 3.0,
                "minimum_island_pixels": 7,
                "maximum_island_pixels": None,
                "profile": "continuum",
            }
        )
    )


@pytest.mark.integration
def test_an_identity_that_cannot_be_computed_stops_the_run_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every provenance identity is known before the first pixel is read."""
    _write_image(tmp_path / "image.fits", _ring_image())

    def unidentified() -> str:
        raise SourceFinderError("cannot identify scientific module")

    monkeypatch.setattr(
        public_api, "_scientific_composition_sha256", unidentified
    )
    executor = _RecordingExecutor()

    with pytest.raises(SourceFinderError, match="cannot identify"):
        hebog.find_sources(_request(tmp_path), _config(), executor)

    assert executor.batch_counts == []
    assert not (tmp_path / "products").exists()


@pytest.mark.integration
@pytest.mark.parametrize("profile", ("continuum", "compact"))
def test_every_module_a_run_loads_is_bound_or_named_exempt(
    tmp_path: Path, profile: str
) -> None:
    """The composition hash covers what a real run executes.

    The unit tests derive the hash's module list from import statements, so
    a module loaded by name at run time would escape them. A run in a fresh
    interpreter must load no Hebog module that is neither bound nor exempt;
    the resource package it loads by name is bound file by file.
    """
    _write_image(tmp_path / "image.fits", _ring_image())
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "import hebog\n"
        "from hebog.executors import SerialExecutor\n"
        "root = Path(sys.argv[1])\n"
        "hebog.find_sources(\n"
        "    hebog.SourceFinderRequest(\n"
        "        root / 'image.fits', root / 'products', 'modules'\n"
        "    ),\n"
        "    hebog.SourceFinderConfig(5.0, 3.0, 7, profile=sys.argv[2]),\n"
        "    SerialExecutor(),\n"
        ")\n"
        "print(sorted(name for name in sys.modules\n"
        "    if name.split('.')[0] == 'hebog'))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), profile],
        check=True,
        capture_output=True,
        text=True,
    )
    loaded = set(ast.literal_eval(completed.stdout.splitlines()[-1]))
    resources = public_api._SCIENTIFIC_RESOURCES  # pyright: ignore[reportPrivateUsage]
    bound = set(public_api._SCIENTIFIC_MODULES)  # pyright: ignore[reportPrivateUsage]
    exempt = set(public_api._UNBOUND_MODULES)  # pyright: ignore[reportPrivateUsage]

    assert resources in loaded
    assert loaded - {resources} <= bound | exempt
    assert "hebog.public_science" in loaded


def _write_refused_image(path: Path, refusal: str) -> None:
    """Write an image the finder refuses at one stage of its admission."""
    if refusal == "narrow":
        _write_empty_image(path, (400, 2600))
        return
    header = _header((8, 8))
    if refusal == "missing-unit":
        del header["BUNIT"]
    elif refusal == "frame":
        header["CTYPE1"], header["CTYPE2"] = "GLON-TAN", "GLAT-TAN"
        del header["RADESYS"]
    fits.PrimaryHDU(data=np.zeros((8, 8)), header=header).writeto(path)
    if refusal == "truncated":
        path.write_bytes(path.read_bytes()[:-2880])


@pytest.mark.integration
@pytest.mark.filterwarnings("ignore:File may have been truncated")
@pytest.mark.parametrize(
    "refusal", ("missing-unit", "truncated", "frame", "narrow", "unhashable")
)
def test_a_refused_input_is_released_before_the_error_reaches_the_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    refusal: str,
) -> None:
    """Given an input the finder refuses, at any stage of its admission,
    when the error reaches the caller,
    then the finder holds the file open no longer.

    Windows will not move or delete a file that is still open, so a caller
    could not set a refused input aside while handling the error.
    """
    image = tmp_path / "image.fits"
    _write_refused_image(image, refusal)
    if refusal == "unhashable":

        def unreadable(_path: Path) -> str:
            raise OSError("injected read failure")

        monkeypatch.setattr(public_api, "_file_sha256", unreadable)
    # An earlier test's source, once collected, would close through the spy.
    gc.collect()
    close = mocker.spy(FitsImageSource, "close")

    # Holding the error keeps the finder's frame, and so its source, alive:
    # a close seen here is the finder's own and not the collector's.
    with pytest.raises(SourceFinderError) as refused:
        hebog.find_sources(_request(tmp_path), _config(), SerialExecutor())

    assert close.call_count == 1
    assert refused.value is not None
    image.unlink()
