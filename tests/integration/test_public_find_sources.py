# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Installed-library contract for the public FITS-to-products facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar

import numpy as np
import pytest
from astropy.io import fits
from distributed import Client, LocalCluster

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest, public_api
from hebog.data_models import PublicSourceFindingDiagnostics
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io import read_catalogue_fits_product, read_diagnostics_product
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    UnsupportedSourceFinderConfigurationError,
)

Input = TypeVar("Input")
Output = TypeVar("Output")


class _RecordingExecutor:
    """Ordered executor double proving the public facade uses its caller."""

    def __init__(self) -> None:
        self.batch_counts: list[int] = []

    def map_batches(
        self,
        function: Callable[[Input], Output],
        batches: Iterable[Input],
    ) -> list[Output]:
        """Execute in order while retaining each submitted batch count."""
        items = tuple(batches)
        self.batch_counts.append(len(items))
        return [function(item) for item in items]


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
    assert result.island_count == 1
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
    assert len(catalogue.gaussian_components) == 4
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.source_count == 1
    assert diagnostics.profile == "continuum"
    assert diagnostics.provenance.input_sha256
    assert diagnostics.provenance.scientific_composition_sha256


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


@pytest.mark.integration
def test_blank_and_all_nan_inputs_publish_honest_empty_products(
    tmp_path: Path,
) -> None:
    """Empty science remains successful without inventing sources or RMS."""
    for name, values, expected_rms_status in (
        ("blank", np.zeros((32, 48)), "unavailable"),
        ("all-nan", np.full((32, 48), np.nan), "unavailable"),
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


@pytest.mark.integration
def test_publication_fails_closed_for_existing_output_and_unfrozen_config(
    tmp_path: Path,
) -> None:
    """The facade rejects ambiguous output ownership and scientific drift."""
    _write_image(tmp_path / "image.fits", _ring_image())
    output = tmp_path / "products"
    output.mkdir()
    sentinel = output / "owned.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(SourceFinderOutputExistsError, match="already exists"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())
    assert sentinel.read_text(encoding="utf-8") == "preserve"

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match="frozen Phase 5",
    ):
        hebog.find_sources(
            _request(tmp_path, output_name="unfrozen"),
            SourceFinderConfig(6.0, 3.0, 7),
            _RecordingExecutor(),
        )
    assert not (tmp_path / "unfrozen").exists()

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match="frozen Phase 5",
    ):
        hebog.find_sources(
            _request(tmp_path, output_name="maximum-cut"),
            SourceFinderConfig(5.0, 3.0, 7, maximum_island_pixels=100),
            _RecordingExecutor(),
        )
    assert not (tmp_path / "maximum-cut").exists()


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
    """Phase 5 never extrapolates its in-memory science past 1024 square."""
    _write_image(tmp_path / "image.fits", np.zeros((2, 1025)))

    with pytest.raises(SourceFinderImageTooLargeError, match="1024"):
        hebog.find_sources(_request(tmp_path), _config(), _RecordingExecutor())

    assert not (tmp_path / "products").exists()


@pytest.mark.integration
def test_serial_and_existing_dask_publish_identical_scientific_products(
    tmp_path: Path,
) -> None:
    """Caller-owned execution policy cannot alter any scientific bytes."""
    _write_image(tmp_path / "image.fits", _ring_image())
    serial = hebog.find_sources(
        _request(tmp_path, output_name="serial"),
        _config(),
        SerialExecutor(),
    )
    cluster = LocalCluster(
        n_workers=1,
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
