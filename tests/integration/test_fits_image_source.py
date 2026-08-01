# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contract tests for bounded FITS image input."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from hebog.io import (
    FitsImageSource,
    ImageBounds,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
    celestial_wcs_from_metadata,
)


def _write_image(
    path: Path,
    data: np.ndarray,
    *,
    unit: str | None = "Jy/beam",
    include_wcs: bool = True,
    reference_frequency_hz: float | str | None = 150_000_000.0,
) -> None:
    """Write a small radio-image fixture without hiding its axis layout."""
    header = fits.Header()
    if unit is not None:
        header["BUNIT"] = unit
    header["BMAJ"] = 0.01
    header["BMIN"] = 0.008
    header["BPA"] = 20.0
    if include_wcs:
        header["RADESYS"] = "ICRS"
        header["CTYPE1"] = "RA---SIN"
        header["CTYPE2"] = "DEC--SIN"
        header["CRPIX1"] = 1.0
        header["CRPIX2"] = 1.0
        header["CRVAL1"] = 180.0
        header["CRVAL2"] = -30.0
        header["CDELT1"] = -0.001
        header["CDELT2"] = 0.001
        header["CUNIT1"] = "deg"
        header["CUNIT2"] = "deg"
        if data.ndim == 4:
            header["CTYPE3"] = "FREQ"
            header["CTYPE4"] = "STOKES"
            header["CRPIX3"] = 1.0
            header["CRPIX4"] = 1.0
            header["CRVAL3"] = 150_000_000.0
            header["CRVAL4"] = 1.0
            header["CDELT3"] = 1_000_000.0
            header["CDELT4"] = 1.0
            header["CUNIT3"] = "Hz"
    if reference_frequency_hz is not None:
        header["RESTFRQ"] = reference_frequency_hz
    fits.PrimaryHDU(data=data, header=header).writeto(path)


@pytest.mark.integration
def test_reads_only_the_requested_global_window(tmp_path: Path) -> None:
    """A singleton-axis radio image returns one owned bounded array."""
    plane = np.arange(30, dtype=np.float32).reshape(5, 6)
    path = tmp_path / "image.fits"
    _write_image(path, plane[np.newaxis, np.newaxis, :, :])
    source = FitsImageSource(path)
    bounds = ImageBounds(y_start=1, y_stop=4, x_start=2, x_stop=6)

    metadata = source.metadata()
    window = source.read_window(bounds)

    assert metadata.shape_yx == (5, 6)
    assert metadata.unit == "Jy/beam"
    assert metadata.beam.major_fwhm_degrees == 0.01
    assert metadata.beam.minor_fwhm_degrees == 0.008
    assert metadata.beam.position_angle_degrees == 20.0
    assert metadata.reference_frequency_hz == 150_000_000.0
    assert metadata.celestial_wcs.coordinate_frame == "icrs"
    assert window.bounds == bounds
    assert bounds.shape_yx == (3, 4)
    np.testing.assert_array_equal(window.values, plane[1:4, 2:6])
    np.testing.assert_array_equal(window.valid_pixels, True)
    assert window.values.dtype == np.dtype(np.float64)
    assert not window.values.flags.writeable
    assert not window.valid_pixels.flags.writeable

    celestial_wcs = celestial_wcs_from_metadata(metadata)
    right_ascension, declination = celestial_wcs.pixel_to_world_values(0, 0)
    assert right_ascension == pytest.approx(180.0)
    assert declination == pytest.approx(-30.0)


@pytest.mark.integration
def test_reads_multiple_bounded_windows_in_one_ordered_batch(
    tmp_path: Path,
) -> None:
    """Dense compact batches can reuse one validated FITS open."""
    plane = np.arange(30, dtype=np.float32).reshape(5, 6)
    path = tmp_path / "image.fits"
    _write_image(path, plane)
    source = FitsImageSource(path)
    bounds = (ImageBounds(0, 2, 0, 3), ImageBounds(3, 5, 4, 6))

    windows = source.read_windows(bounds)

    assert tuple(window.bounds for window in windows) == bounds
    np.testing.assert_array_equal(windows[0].values, plane[0:2, 0:3])
    np.testing.assert_array_equal(windows[1].values, plane[3:5, 4:6])
    assert source.read_windows(()) == ()


@pytest.mark.integration
@pytest.mark.parametrize("unit", ["JY/BEAM", "JYBEAM-1"])
def test_canonicalizes_wsclean_uppercase_jy_per_beam_unit(
    tmp_path: Path,
    unit: str,
) -> None:
    """Production WSClean BUNIT spelling maps to the canonical image unit."""
    path = tmp_path / "wsclean-image.fits"
    _write_image(path, np.ones((2, 3), dtype=np.float32), unit=unit)

    metadata = FitsImageSource(path).metadata()

    assert metadata.unit == "Jy/beam"


@pytest.mark.integration
def test_accepts_a_two_dimensional_non_square_image(tmp_path: Path) -> None:
    """Two-dimensional FITS data keeps its y/x axes even when one is short."""
    plane = np.arange(5, dtype=np.float64).reshape(1, 5)
    path = tmp_path / "non-square.fits"
    _write_image(path, plane)
    source = FitsImageSource(path)

    window = source.read_window(
        ImageBounds(y_start=0, y_stop=1, x_start=1, x_stop=4)
    )

    assert source.metadata().shape_yx == (1, 5)
    np.testing.assert_array_equal(window.values, plane[:, 1:4])


@pytest.mark.integration
def test_marks_non_finite_pixels_invalid_without_replacing_them(
    tmp_path: Path,
) -> None:
    """NaN and infinity remain visible while validity is explicit."""
    plane = np.array([[1.0, np.nan], [np.inf, -2.0]], dtype=np.float32)
    path = tmp_path / "masked.fits"
    _write_image(path, plane)

    window = FitsImageSource(path).read_window(
        ImageBounds(y_start=0, y_stop=2, x_start=0, x_stop=2)
    )

    np.testing.assert_array_equal(
        window.valid_pixels,
        np.array([[True, False], [False, True]]),
    )
    assert np.isnan(window.values[0, 1])
    assert np.isposinf(window.values[1, 0])


@pytest.mark.integration
def test_accepts_an_all_invalid_but_structured_plane(tmp_path: Path) -> None:
    """An all-NaN observation is empty science, not malformed FITS."""
    path = tmp_path / "all-invalid.fits"
    _write_image(path, np.full((2, 3), np.nan, dtype=np.float32))

    window = FitsImageSource(path).read_window(
        ImageBounds(y_start=0, y_stop=2, x_start=0, x_stop=3)
    )

    assert not np.any(window.valid_pixels)


@pytest.mark.integration
@pytest.mark.parametrize(
    "bounds",
    [
        ImageBounds(y_start=0, y_stop=2, x_start=0, x_stop=4),
        ImageBounds(y_start=0, y_stop=3, x_start=0, x_stop=3),
    ],
)
def test_rejects_a_window_outside_the_logical_plane(
    tmp_path: Path,
    bounds: ImageBounds,
) -> None:
    """A caller cannot accidentally read beyond global image coordinates."""
    path = tmp_path / "image.fits"
    _write_image(path, np.zeros((2, 3), dtype=np.float32))

    with pytest.raises(ValueError, match="inside image shape") as error:
        FitsImageSource(path).read_window(bounds)

    assert not isinstance(error.value, InvalidFitsImageError)


@pytest.mark.integration
@pytest.mark.parametrize(
    "bounds",
    [
        (-1, 1, 0, 1),
        (0, 0, 0, 1),
        (0, 1, 2, 1),
    ],
)
def test_rejects_invalid_half_open_bounds(
    bounds: tuple[int, int, int, int],
) -> None:
    """Window coordinates must be non-negative and non-empty."""
    with pytest.raises(ValueError, match="bounds"):
        ImageBounds(*bounds)


@pytest.mark.integration
def test_rejects_a_corrupt_fits_file(tmp_path: Path) -> None:
    """Malformed bytes fail with the stable image-source error."""
    path = tmp_path / "corrupt.fits"
    path.write_bytes(b"not a FITS image")

    with pytest.raises(InvalidFitsImageError, match="cannot read FITS image"):
        FitsImageSource(path).metadata()


@pytest.mark.integration
def test_rejects_an_image_without_pixel_data(tmp_path: Path) -> None:
    """A header-only primary HDU is not a scientific image input."""
    path = tmp_path / "empty.fits"
    fits.PrimaryHDU().writeto(path)

    with pytest.raises(InvalidFitsImageError, match="contains no image data"):
        FitsImageSource(path).metadata()


@pytest.mark.integration
def test_rejects_a_zero_sized_image_plane(tmp_path: Path) -> None:
    """An image HDU with no logical pixels is structurally invalid."""
    path = tmp_path / "zero-sized.fits"
    _write_image(path, np.zeros((0, 3), dtype=np.float32))

    with pytest.raises(InvalidFitsImageError, match="must be non-empty"):
        FitsImageSource(path).metadata()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("data", "message"),
    [
        (np.zeros(4, dtype=np.float32), "at least two axes"),
        (
            np.zeros((2, 3, 4), dtype=np.float32),
            "non-singleton leading axes",
        ),
    ],
)
def test_rejects_unsupported_image_axes(
    tmp_path: Path,
    data: np.ndarray,
    message: str,
) -> None:
    """Vectors and channel cubes require other explicit contracts."""
    path = tmp_path / "unsupported.fits"
    _write_image(path, data)

    with pytest.raises(
        UnsupportedFitsImageError,
        match=message,
    ):
        FitsImageSource(path).metadata()


@pytest.mark.integration
def test_rejects_a_missing_or_invalid_brightness_unit(tmp_path: Path) -> None:
    """Scientific image units must never be guessed from filenames."""
    missing = tmp_path / "missing-unit.fits"
    blank = tmp_path / "blank-unit.fits"
    invalid = tmp_path / "invalid-unit.fits"
    _write_image(missing, np.zeros((2, 2), dtype=np.float32), unit=None)
    _write_image(blank, np.zeros((2, 2), dtype=np.float32), unit=" ")
    _write_image(invalid, np.zeros((2, 2), dtype=np.float32), unit="bananas")

    with pytest.raises(InvalidFitsImageError, match="BUNIT"):
        FitsImageSource(missing).metadata()
    with pytest.raises(InvalidFitsImageError, match="BUNIT"):
        FitsImageSource(blank).metadata()
    with pytest.raises(InvalidFitsImageError, match="BUNIT"):
        FitsImageSource(invalid).metadata()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("BMAJ", None),
        ("BMIN", None),
        ("BPA", None),
        ("BMAJ", 0.0),
        ("BMIN", 0.02),
        ("BPA", "nan"),
    ],
)
def test_rejects_missing_or_invalid_restoring_beam(
    tmp_path: Path,
    keyword: str,
    value: float | str | None,
) -> None:
    """Beam geometry is required and cannot be inferred from the image name."""
    path = tmp_path / f"beam-{keyword}.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        if value is None:
            del hdus[0].header[keyword]
        else:
            hdus[0].header[keyword] = value

    with pytest.raises(InvalidFitsImageError, match="restoring beam"):
        FitsImageSource(path).metadata()


@pytest.mark.integration
def test_rejects_missing_celestial_wcs(tmp_path: Path) -> None:
    """Pixel-only images cannot produce a scientifically located catalogue."""
    path = tmp_path / "no-wcs.fits"
    _write_image(
        path,
        np.zeros((2, 2), dtype=np.float32),
        include_wcs=False,
    )

    with pytest.raises(InvalidFitsImageError, match="celestial WCS"):
        FitsImageSource(path).metadata()


@pytest.mark.integration
def test_uses_a_frequency_axis_when_rest_frequency_is_absent(
    tmp_path: Path,
) -> None:
    """Observatory FITS variants may carry reference frequency in WCS."""
    path = tmp_path / "frequency-axis.fits"
    _write_image(
        path,
        np.zeros((1, 1, 2, 2), dtype=np.float32),
        reference_frequency_hz=None,
    )

    metadata = FitsImageSource(path).metadata()

    assert metadata.reference_frequency_hz == 150_000_000.0


@pytest.mark.integration
@pytest.mark.parametrize("frequency", [None, 0.0, "nan", "not-a-number"])
def test_rejects_missing_or_invalid_reference_frequency(
    tmp_path: Path,
    frequency: float | str | None,
) -> None:
    """Frequency-dependent measurements require an explicit positive value."""
    path = tmp_path / "bad-frequency.fits"
    _write_image(
        path,
        np.zeros((2, 2), dtype=np.float32),
        reference_frequency_hz=frequency,
    )

    with pytest.raises(InvalidFitsImageError, match="reference frequency"):
        FitsImageSource(path).metadata()
