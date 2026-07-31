# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
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
)


def _write_image(
    path: Path,
    data: np.ndarray,
    *,
    unit: str | None = "Jy/beam",
) -> None:
    """Write a small radio-image fixture without hiding its axis layout."""
    header = fits.Header()
    if unit is not None:
        header["BUNIT"] = unit
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
    assert window.bounds == bounds
    assert bounds.shape_yx == (3, 4)
    np.testing.assert_array_equal(window.values, plane[1:4, 2:6])
    np.testing.assert_array_equal(window.valid_pixels, True)
    assert window.values.dtype == np.dtype(np.float64)
    assert not window.values.flags.writeable
    assert not window.valid_pixels.flags.writeable


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
