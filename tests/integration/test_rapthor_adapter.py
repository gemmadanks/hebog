# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""The Rapthor adapter runs one sector and names its products as Rapthor does.

Rapthor's PyBDSF step writes ``<root>.source_catalog.fits``, the two RMS
maps ``<root>.true_sky_rms.fits`` and ``<root>.flat_noise_rms.fits``, and
the island mask ``<true-sky image name>.mask.fits`` beside them, which
LSMTool's ``filter_sources`` clips and groups by. The adapter writes the
same files from one Hebog analysis of the sector's two images.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.adapters import rapthor
from hebog.adapters.rapthor import (
    RapthorBlankedImageError,
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
    find_sector_sources,
)
from hebog.adapters.rapthor_catalogue import (
    read_rapthor_catalogue_fits,
    write_rapthor_catalogue_fits,
)
from hebog.adapters.rapthor_comparison import (
    RapthorSectorProducts,
    compare_sector_products,
)
from hebog.data_models import (
    PublicSourceFindingDiagnostics,
    SourceFindingDiagnostics,
)
from hebog.executors import Executor, SerialExecutor
from hebog.io import (
    read_catalogue_fits_product,
    read_diagnostics_product,
    write_diagnostics_product,
)
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderOutputExistsError,
    find_sources,
)

pytestmark = pytest.mark.integration

_SHAPE_YX = (81, 97)
_BEAM_ARCSEC = 4.0


def _header(beam_arcsec: float = _BEAM_ARCSEC) -> fits.Header:
    """Return a WSClean-style header: celestial, then frequency and Stokes."""
    height, width = _SHAPE_YX
    header = fits.Header()
    header["BUNIT"] = "JY/BEAM"
    header["BMAJ"] = beam_arcsec / 3600.0
    header["BMIN"] = beam_arcsec / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = width / 2 + 1
    header["CRPIX2"] = height / 2 + 1
    header["CRVAL1"] = 242.75
    header["CRVAL2"] = 54.95
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["CTYPE3"] = "FREQ"
    header["CRPIX3"] = 1.0
    header["CRVAL3"] = 143_650_000.0
    header["CDELT3"] = 23_437_500.0
    header["CUNIT3"] = "Hz"
    header["CTYPE4"] = "STOKES"
    header["CRPIX4"] = 1.0
    header["CRVAL4"] = 1.0
    header["CDELT4"] = 1.0
    header["CUNIT4"] = ""
    return header


def _flat_noise_image() -> np.ndarray:
    """Return compact sources on flat noise, blanked outside the sector."""
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    image = np.random.default_rng(7).normal(0.0, 1.0, _SHAPE_YX)
    for y, x, peak in ((40, 30, 40.0), (25, 70, 20.0), (60, 60, 12.0)):
        image += peak * np.exp(
            -((x_pixels - x) ** 2 + (y_pixels - y) ** 2) / 4.0
        )
    # Rapthor blanks each image outside its sector polygon.
    image[:, :4] = np.nan
    return image


def _true_sky_image(flat_noise: np.ndarray) -> np.ndarray:
    """Divide by a smooth primary beam, so the noise grows outwards."""
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    centre_y, centre_x = (_SHAPE_YX[0] - 1) / 2, (_SHAPE_YX[1] - 1) / 2
    beam = np.exp(
        -((x_pixels - centre_x) ** 2 + (y_pixels - centre_y) ** 2)
        / (2.0 * 70.0**2)
    )
    return flat_noise / beam


def _write(path: Path, plane: np.ndarray, header: fits.Header) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(plane, dtype=np.float32)[np.newaxis, np.newaxis]
    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)
    return path


def _sector(
    directory: Path,
    *,
    true_sky: np.ndarray | None = None,
    flat_noise: np.ndarray | None = None,
    flat_noise_header: fits.Header | None = None,
) -> RapthorSourceFindingRequest:
    """Write one sector's images as WSClean names them, and request it."""
    flat_noise_plane = (
        _flat_noise_image() if flat_noise is None else flat_noise
    )
    true_sky_plane = (
        _true_sky_image(flat_noise_plane) if true_sky is None else true_sky
    )
    images = directory / "images"
    return RapthorSourceFindingRequest(
        true_sky_image_path=_write(
            images / "sector_1-MFS-image-pb.fits", true_sky_plane, _header()
        ),
        flat_noise_image_path=_write(
            images / "sector_1-MFS-image.fits",
            flat_noise_plane,
            _header() if flat_noise_header is None else flat_noise_header,
        ),
        output_root=directory / "pipeline" / "sector_1",
        run_id="image_1-sector_1",
    )


def _config() -> RapthorCompatibilityConfig:
    return RapthorCompatibilityConfig(threshpix=5.0, threshisl=3.0)


def _rapthor_names(request: RapthorSourceFindingRequest) -> tuple[Path, ...]:
    """Return the four files Rapthor's step reads, as Rapthor names them."""
    root = request.output_root
    return (
        root.parent / "sector_1.source_catalog.fits",
        root.parent / "sector_1.true_sky_rms.fits",
        root.parent / "sector_1.flat_noise_rms.fits",
        root.parent / "sector_1-MFS-image-pb.fits.mask.fits",
    )


def _product_bytes(result: RapthorSourceFindingResult) -> tuple[bytes, ...]:
    return tuple(
        path.read_bytes()
        for path in (
            result.source_catalog_path,
            result.true_sky_rms_path,
            result.flat_noise_rms_path,
            result.mask_path,
        )
    )


def test_one_run_writes_the_files_rapthor_reads_under_its_names(
    tmp_path: Path, each_executor: Executor
) -> None:
    """The catalogue, both RMS maps and the mask come from one analysis.

    The catalogue is the eight-column view of the public catalogue, the RMS
    maps are the published ones, and the mask has PyBDSF's four-axis
    layout, which LSMTool's mask clipping and grouping index. Every
    executor writes the same bytes as the serial reference.
    """
    request = _sector(tmp_path / "run")
    reference = find_sector_sources(
        _sector(tmp_path / "reference"), _config(), SerialExecutor()
    )

    result = find_sector_sources(request, _config(), each_executor)

    assert (
        result.source_catalog_path,
        result.true_sky_rms_path,
        result.flat_noise_rms_path,
        result.mask_path,
    ) == _rapthor_names(request)
    bundle = result.products_directory
    assert bundle == request.output_root.parent / "sector_1.hebog"
    diagnostics = read_diagnostics_product(bundle / "diagnostics.json")
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert result.source_count == diagnostics.source_count == 3
    assert result.island_count == diagnostics.island_count >= 1
    expected_catalogue = tmp_path / "expected-catalogue.fits"
    write_rapthor_catalogue_fits(
        expected_catalogue,
        read_catalogue_fits_product(bundle / "catalogue.fits"),
    )
    assert (
        result.source_catalog_path.read_bytes()
        == expected_catalogue.read_bytes()
    )
    assert (
        result.true_sky_rms_path.read_bytes()
        == (bundle / "rms.fits").read_bytes()
    )
    assert (
        result.flat_noise_rms_path.read_bytes()
        == (bundle / "flat-noise-rms.fits").read_bytes()
    )
    with (
        fits.open(result.mask_path) as mask,
        fits.open(bundle / "source-mask.fits") as published,
    ):
        assert mask[0].data.shape == (1, 1, *_SHAPE_YX)
        assert mask[0].data.dtype == np.dtype(">f4")
        np.testing.assert_array_equal(
            mask[0].data[0, 0], published[0].data.astype(np.float32)
        )
        assert mask[0].header["CTYPE3"] == "STOKES"
        assert mask[0].header["CTYPE4"] == "FREQ"
        corners = np.array([[0.0, 0.0], [96.0, 80.0]])
        np.testing.assert_allclose(
            WCS(mask[0].header).celestial.wcs_pix2world(corners, 0),
            WCS(_header()).celestial.wcs_pix2world(corners, 0),
        )
    assert _product_bytes(result) == _product_bytes(reference)


def test_rapthors_thresholds_and_pybdsf_minimum_island_reach_the_finder(
    tmp_path: Path,
) -> None:
    """``threshpix`` and ``threshisl`` are the finder's two thresholds.

    The 6-arcsec beam on 1-arcsec pixels covers 40.8 pixels, so PyBDSF's
    rule gives a minimum island of 13 pixels. The analysis is the one the
    finder runs with exactly those three numbers and Rapthor's default
    profile, ``compact`` with a zero background.
    """
    header = _header(beam_arcsec=6.0)
    flat_noise = _flat_noise_image()
    images = tmp_path / "images"
    request = RapthorSourceFindingRequest(
        true_sky_image_path=_write(
            images / "pb.fits", _true_sky_image(flat_noise), header
        ),
        flat_noise_image_path=_write(images / "flat.fits", flat_noise, header),
        output_root=tmp_path / "pipeline" / "sector_1",
        run_id="sector_1",
    )

    result = find_sector_sources(
        request,
        RapthorCompatibilityConfig(threshpix=6.0, threshisl=4.0),
        SerialExecutor(),
    )
    direct = find_sources(
        SourceFinderRequest(
            request.true_sky_image_path,
            tmp_path / "direct",
            "sector_1",
            flat_noise_image_path=request.flat_noise_image_path,
        ),
        SourceFinderConfig(6.0, 4.0, 13, profile="compact", background="zero"),
        SerialExecutor(),
    )

    adapted = read_diagnostics_product(
        result.products_directory / "diagnostics.json"
    )
    expected = read_diagnostics_product(direct.diagnostics)
    assert isinstance(adapted, PublicSourceFindingDiagnostics)
    assert isinstance(expected, PublicSourceFindingDiagnostics)
    assert adapted.provenance == expected.provenance


@pytest.mark.parametrize(
    ("blanked", "value"),
    [
        ("true-sky", np.nan),
        ("flat-noise", np.nan),
        # Imagers fill blanked regions with one value, which Hebog does not
        # measure, so an image of one value has no pixel to measure either.
        ("true-sky", 0.0),
    ],
)
def test_a_blanked_image_is_reported_as_pybdsf_reports_it(
    tmp_path: Path, blanked: str, value: float
) -> None:
    """Rapthor's step writes its empty products when PyBDSF's error comes.

    An image with no pixel to measure raises PyBDSF's ``RuntimeError``,
    which Rapthor's existing handler recognises, and no file under
    Rapthor's names is left for that handler to mistake for products.
    """
    nothing = np.full(_SHAPE_YX, value)
    flat_noise = _flat_noise_image()
    request = _sector(
        tmp_path,
        true_sky=(
            nothing if blanked == "true-sky" else _true_sky_image(flat_noise)
        ),
        flat_noise=nothing if blanked == "flat-noise" else flat_noise,
    )

    with pytest.raises(
        RuntimeError, match="All pixels in the image are blanked"
    ) as error:
        find_sector_sources(request, _config(), SerialExecutor())

    assert isinstance(error.value, RapthorBlankedImageError)
    assert not any(path.exists() for path in _rapthor_names(request))


def test_earlier_files_under_rapthors_names_never_outlive_a_failed_run(
    tmp_path: Path,
) -> None:
    """A refused sector leaves none of Rapthor's four files behind.

    Files an earlier run left under those names are removed before the
    analysis starts, so a fallback that writes only some of them cannot
    be mixed with Hebog's.
    """
    request = _sector(tmp_path)
    header = _header()
    del header["BMAJ"], header["BMIN"], header["BPA"]
    _write(request.true_sky_image_path, _flat_noise_image(), header)
    for path in _rapthor_names(request):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"an earlier run's product")

    with pytest.raises(InvalidSourceFinderInputError, match="BMAJ"):
        find_sector_sources(request, _config(), SerialExecutor())

    assert not any(path.exists() for path in _rapthor_names(request))


def test_images_whose_beams_give_different_minimum_islands_are_refused(
    tmp_path: Path,
) -> None:
    """Hebog applies one minimum island to both of a sector's images."""
    request = _sector(tmp_path, flat_noise_header=_header(beam_arcsec=6.0))

    with pytest.raises(InvalidSourceFinderInputError, match="minimum island"):
        find_sector_sources(request, _config(), SerialExecutor())

    assert not (tmp_path / "pipeline" / "sector_1.hebog").exists()


def test_a_products_directory_of_another_run_is_refused_and_kept(
    tmp_path: Path,
) -> None:
    """The adapter replaces Rapthor's files, never Hebog's bundle."""
    request = _sector(tmp_path)
    first = find_sector_sources(request, _config(), SerialExecutor())
    kept = sorted(path.name for path in first.products_directory.iterdir())

    with pytest.raises(SourceFinderOutputExistsError, match="already exists"):
        find_sector_sources(
            request,
            RapthorCompatibilityConfig(threshpix=6.0, threshisl=3.0),
            SerialExecutor(),
        )

    assert (
        sorted(path.name for path in first.products_directory.iterdir())
        == kept
    )
    assert not any(path.exists() for path in _rapthor_names(request))


def test_a_failure_while_writing_rapthors_files_removes_those_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rapthor's files appear together or not at all."""
    request = _sector(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(rapthor, "_write_island_mask", fail)

    with pytest.raises(OSError, match="disk full"):
        find_sector_sources(request, _config(), SerialExecutor())

    assert not any(path.exists() for path in _rapthor_names(request))
    assert (tmp_path / "pipeline" / "sector_1.hebog").is_dir()


def test_a_relative_output_root_names_absolute_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rapthor's records hold absolute paths, however the root was given."""
    absolute = _sector(tmp_path)
    monkeypatch.chdir(tmp_path)
    request = RapthorSourceFindingRequest(
        true_sky_image_path=Path("images/sector_1-MFS-image-pb.fits"),
        flat_noise_image_path=Path("images/sector_1-MFS-image.fits"),
        output_root=Path("pipeline/sector_1"),
        run_id=absolute.run_id,
    )

    result = find_sector_sources(request, _config(), SerialExecutor())

    assert result.source_catalog_path == _rapthor_names(absolute)[0]
    assert result.mask_path == _rapthor_names(absolute)[3]
    assert result.products_directory.is_absolute()


def _pybdsf_products(
    directory: Path,
    request: RapthorSourceFindingRequest,
    *,
    positions_deg: list[tuple[float, float]],
    rms: float,
    shape_yx: tuple[int, int] = _SHAPE_YX,
) -> RapthorSectorProducts:
    """Write a PyBDSF-style sector under its own root, as PyBDSF lays it out.

    The catalogue holds the columns the report reads; the RMS maps and the
    mask have PyBDSF's four axes, the mask's ones on the left half.
    """
    products = RapthorSectorProducts.named(
        directory / "sector_1", request.true_sky_image_path
    )
    directory.mkdir(parents=True, exist_ok=True)
    Table(
        {
            "Source_id": np.arange(len(positions_deg), dtype=np.int32),
            "RA": np.array([ra for ra, _ in positions_deg], dtype=float),
            "DEC": np.array([dec for _, dec in positions_deg], dtype=float),
            "Total_flux": np.full(len(positions_deg), 2.0),
        }
    ).write(products.source_catalog_path, format="fits")
    for path in (products.true_sky_rms_path, products.flat_noise_rms_path):
        fits.PrimaryHDU(
            np.full((1, 1, *shape_yx), rms, dtype=np.float32)
        ).writeto(path)
    mask = np.zeros((1, 1, *shape_yx), dtype=np.float32)
    mask[..., : shape_yx[1] // 2] = 1.0
    fits.PrimaryHDU(mask).writeto(products.mask_path)
    return products


def _catalogue_positions(path: Path) -> list[tuple[float, float]]:
    table = read_rapthor_catalogue_fits(path)
    right_ascensions = np.asarray(table["RA"], dtype=np.float64)
    declinations = np.asarray(table["DEC"], dtype=np.float64)
    return [
        (float(ra), float(dec))
        for ra, dec in zip(right_ascensions, declinations, strict=True)
    ]


def test_the_dual_run_report_matches_mutual_nearest_sources_in_half_a_beam(
    tmp_path: Path,
) -> None:
    """A source matches only its own nearest neighbour, and only nearby.

    PyBDSF's list holds each Hebog source, a second entry 0.5 arcsec from
    the first, which only one of the two can match, and one 1.5 arcsec
    from the second source, beyond half the 4-arcsec beam.
    """
    request = _sector(tmp_path / "run")
    hebog = find_sector_sources(request, _config(), SerialExecutor())
    found = _catalogue_positions(hebog.source_catalog_path)
    near = (found[0][0], found[0][1] + 0.5 / 3600.0)
    far = (found[1][0], found[1][1] + 2.5 / 3600.0)
    pybdsf = _pybdsf_products(
        tmp_path / "pybdsf",
        request,
        positions_deg=[found[0], near, far, found[2]],
        rms=2.0,
    )

    report = compare_sector_products(hebog, pybdsf, tmp_path / "report.json")

    assert report.match_radius_arcsec == pytest.approx(2.0)
    assert report.matched_source_count == 2
    assert report.pybdsf.source_count == 4
    assert report.pybdsf_mask_pixel_count == _SHAPE_YX[0] * (_SHAPE_YX[1] // 2)
    assert report.shared_mask_pixel_count <= report.hebog_mask_pixel_count


def test_the_dual_run_report_states_what_it_could_not_compare(
    tmp_path: Path,
) -> None:
    """With no source or no comparable RMS pixel, a ratio is ``None``."""
    request = _sector(tmp_path / "run")
    hebog = find_sector_sources(request, _config(), SerialExecutor())
    pybdsf = _pybdsf_products(
        tmp_path / "pybdsf", request, positions_deg=[], rms=np.nan
    )

    report = compare_sector_products(hebog, pybdsf, tmp_path / "report.json")

    assert report.matched_source_count == 0
    assert report.median_total_flux_ratio is None
    assert report.true_sky_rms_median_ratio is None
    assert report.flat_noise_rms_median_ratio is None


@pytest.mark.parametrize("product", ["rms", "mask"])
def test_the_dual_run_report_refuses_products_on_another_grid(
    tmp_path: Path, product: str
) -> None:
    """Pixel statistics need one grid, so different grids are refused."""
    request = _sector(tmp_path / "run")
    hebog = find_sector_sources(request, _config(), SerialExecutor())
    pybdsf = _pybdsf_products(
        tmp_path / "pybdsf",
        request,
        positions_deg=[],
        rms=1.0,
        shape_yx=(_SHAPE_YX[0], _SHAPE_YX[1] + 1),
    )
    if product == "mask":
        for path in (pybdsf.true_sky_rms_path, pybdsf.flat_noise_rms_path):
            shutil.copyfile(hebog.true_sky_rms_path, path)
    else:
        shutil.copyfile(hebog.mask_path, pybdsf.mask_path)

    with pytest.raises(
        ValueError, match=f"(?i){product}.* on different pixel grids"
    ):
        compare_sector_products(hebog, pybdsf, tmp_path / "report.json")

    assert not (tmp_path / "report.json").exists()


def test_the_dual_run_report_needs_hebogs_provenance(tmp_path: Path) -> None:
    """A bundle without public diagnostics cannot bind the report."""
    request = _sector(tmp_path / "run")
    hebog = find_sector_sources(request, _config(), SerialExecutor())
    pybdsf = _pybdsf_products(
        tmp_path / "pybdsf", request, positions_deg=[], rms=1.0
    )
    diagnostics = hebog.products_directory / "diagnostics.json"
    diagnostics.unlink()
    write_diagnostics_product(
        diagnostics,
        SourceFindingDiagnostics(
            run_id=request.run_id,
            source_count=0,
            gaussian_component_count=0,
            island_count=0,
            rms_scientific_status="valid",
        ),
    )
    unchanged = _contents(pybdsf.paths())

    with pytest.raises(ValueError, match="no public diagnostics"):
        compare_sector_products(hebog, pybdsf, tmp_path / "report.json")

    assert _contents(pybdsf.paths()) == unchanged
    assert not (tmp_path / "report.json").exists()


def _contents(paths: tuple[Path, ...]) -> tuple[bytes, ...]:
    return tuple(path.read_bytes() for path in paths)
