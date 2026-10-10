"""Rapthor's settings, records and PyBDSF's minimum island rule."""

from __future__ import annotations

import pickle
from dataclasses import fields, replace
from pathlib import Path

import pytest

from hebog.adapters.rapthor import (
    RapthorBlankedImageError,
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
    pybdsf_minimum_island_pixels,
)
from hebog.config import SourceFinderConfig
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam


def _request() -> RapthorSourceFindingRequest:
    return RapthorSourceFindingRequest(
        true_sky_image_path=Path("sector_1-MFS-image-pb.fits"),
        flat_noise_image_path=Path("sector_1-MFS-image.fits"),
        output_root=Path("pipelines/image_1/sector_1"),
        run_id="image_1-sector_1",
    )


def _result() -> RapthorSourceFindingResult:
    return RapthorSourceFindingResult(
        source_catalog_path=Path("sector_1.source_catalog.fits"),
        true_sky_rms_path=Path("sector_1.true_sky_rms.fits"),
        flat_noise_rms_path=Path("sector_1.flat_noise_rms.fits"),
        mask_path=Path("sector_1-MFS-image-pb.fits.mask.fits"),
        products_directory=Path("sector_1.hebog"),
        source_count=2,
        island_count=2,
        wall_seconds=3.0,
    )


def _metadata(
    beam_arcsec: tuple[float, float], pixel_arcsec: tuple[float, float]
) -> ImageMetadata:
    """Return metadata of a north-up image with the given beam and pixels."""
    header = "\n".join(
        (
            "CTYPE1  = 'RA---SIN'",
            "CTYPE2  = 'DEC--SIN'",
            "CRPIX1  = 50.0",
            "CRPIX2  = 50.0",
            "CRVAL1  = 242.75",
            "CRVAL2  = 54.95",
            f"CDELT1  = {-pixel_arcsec[0] / 3600.0!r}",
            f"CDELT2  = {pixel_arcsec[1] / 3600.0!r}",
            "CUNIT1  = 'deg'",
            "CUNIT2  = 'deg'",
            "RADESYS = 'ICRS'",
        )
    )
    return ImageMetadata(
        shape_yx=(100, 100),
        unit="Jy/beam",
        beam=RestoringBeam(
            major_fwhm_degrees=beam_arcsec[0] / 3600.0,
            minor_fwhm_degrees=beam_arcsec[1] / 3600.0,
            position_angle_degrees=0.0,
        ),
        celestial_wcs=CelestialWcs(
            fits_header=header, coordinate_frame="icrs"
        ),
        reference_frequency_hz=144e6,
    )


def test_rapthor_records_are_small_and_serializable() -> None:
    """A Prefect task can return the result and retry with the request."""
    request = _request()
    result = _result()

    assert request.schema_version == result.schema_version == 2
    assert pickle.loads(pickle.dumps(request)) == request
    assert pickle.loads(pickle.dumps(result)) == result


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 1}, "unsupported Rapthor request"),
        ({"run_id": ""}, "run_id must not be empty"),
    ],
)
def test_rapthor_request_rejects_invalid_metadata(
    changes: dict[str, object], message: str
) -> None:
    """Rapthor request metadata fails at the compatibility boundary."""
    with pytest.raises(ValueError, match=message):
        replace(_request(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 1}, "unsupported Rapthor result"),
        ({"source_count": -1}, "source_count cannot be negative"),
        ({"island_count": -1}, "island_count cannot be negative"),
        ({"wall_seconds": float("nan")}, "wall_seconds must be finite"),
        ({"wall_seconds": -1.0}, "wall_seconds must be finite"),
    ],
)
def test_rapthor_result_rejects_invalid_metadata(
    changes: dict[str, object], message: str
) -> None:
    """Rapthor result metadata fails at the compatibility boundary."""
    with pytest.raises(ValueError, match=message):
        replace(_result(), **changes)


def test_rapthor_settings_hold_only_what_the_finder_honours() -> None:
    """Rapthor's two thresholds, and Hebog's profile and background.

    The RMS boxes, the bright-source threshold and the multiscale depth are
    Hebog's reviewed science, and LSMTool's mask filter is LSMTool's, so
    the settings do not offer them.
    """
    config = RapthorCompatibilityConfig(threshpix=5.0, threshisl=4.0)

    assert {field.name for field in fields(config)} == {
        "threshpix",
        "threshisl",
        "profile",
        "background",
    }
    assert config.source_finder_config(minimum_island_pixels=9) == (
        SourceFinderConfig(5.0, 4.0, 9, profile="continuum")
    )
    assert RapthorCompatibilityConfig(
        5.0, 3.0, profile="compact", background="zero"
    ).source_finder_config(minimum_island_pixels=6) == SourceFinderConfig(
        5.0, 3.0, 6, profile="compact", background="zero"
    )


@pytest.mark.parametrize(
    ("threshpix", "threshisl", "message"),
    [
        (3.0, 5.0, "island_threshold_sigma must be lower"),
        (float("nan"), 3.0, "detection_threshold_sigma must be finite"),
    ],
)
def test_rapthor_settings_are_validated_when_made(
    threshpix: float, threshisl: float, message: str
) -> None:
    """A wrong threshold fails in Rapthor's task, not after the images load."""
    with pytest.raises(ValueError, match=message):
        RapthorCompatibilityConfig(threshpix, threshisl)


@pytest.mark.parametrize(
    ("beam_arcsec", "pixel_arcsec", "expected"),
    [
        # 1.1331 x 4 x 4 = 18.1 pixels: a third is 6.04, so 6.
        ((6.0, 6.0), (1.5, 1.5), 6),
        # 1.1331 x 2 x 2 = 4.5 pixels: a third is under the floor of six.
        ((3.0, 3.0), (1.5, 1.5), 6),
        # LoTSS-DR3: 9-arcsec beam, 1.5-arcsec pixels, 40.8 pixels, 13.
        ((9.0, 9.0), (1.5, 1.5), 13),
        # An elliptical beam on rectangular pixels: 1.1331 x 10 x 5, 18.
        ((20.0, 10.0), (2.0, 2.0), 18),
        ((20.0, 10.0), (2.0, 1.0), 37),
    ],
)
def test_the_minimum_island_follows_pybdsf_from_the_beam(
    beam_arcsec: tuple[float, float],
    pixel_arcsec: tuple[float, float],
    expected: int,
) -> None:
    """``max(6, int(beam area in pixels / 3))``, PyBDSF's ``minpix_isl``."""
    metadata = _metadata(beam_arcsec, pixel_arcsec)

    assert pybdsf_minimum_island_pixels(metadata) == expected


def test_a_blanked_image_is_reported_as_pybdsf_reports_it() -> None:
    """Rapthor's step recognises PyBDSF's error by its message."""
    error = RapthorBlankedImageError()

    assert isinstance(error, RuntimeError)
    assert "All pixels in the image are blanked" in str(error)
