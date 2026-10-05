# pyright: reportAttributeAccessIssue=false
# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contract tests for bounded FITS image input."""

from __future__ import annotations

import gc
import pickle
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

from hebog.data_models import SuppliedImageMetadata
from hebog.data_models.images import ImageMetadata
from hebog.io import (
    FitsImageSource,
    ImageBounds,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
    celestial_wcs_from_metadata,
)
from hebog.io import fits as fits_module


def _write_image(
    path: Path,
    data: np.ndarray,
    *,
    unit: str | None = "Jy/beam",
    include_wcs: bool = True,
    reference_frequency_hz: float | None = 150_000_000.0,
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
            r"non-singleton leading axes, untyped \(NAXIS3 = 2\)",
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
    ],
)
def test_rejects_missing_or_invalid_restoring_beam(
    tmp_path: Path,
    keyword: str,
    value: float | None,
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
def test_rejects_a_frame_astropy_cannot_name(tmp_path: Path) -> None:
    """A geocentric apparent frame is named rather than read as ICRS."""
    path = tmp_path / "apparent.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        hdus[0].header["RADESYS"] = "GAPPT"

    with pytest.raises(
        InvalidFitsImageError, match="cannot name, RADESYS 'GAPPT'"
    ):
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
@pytest.mark.parametrize("frequency", [None, 0.0, -150_000_000.0])
def test_rejects_missing_or_invalid_reference_frequency(
    tmp_path: Path,
    frequency: float | None,
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


@pytest.mark.integration
def test_supplied_reference_frequency_fills_a_header_without_one(
    tmp_path: Path,
) -> None:
    """LOFAR-HD mosaics carry a beam but no frequency keyword or axis."""
    path = tmp_path / "no-frequency.fits"
    _write_image(
        path,
        np.zeros((2, 2), dtype=np.float32),
        reference_frequency_hz=None,
    )

    metadata = FitsImageSource(
        path, SuppliedImageMetadata(reference_frequency_hz=144_000_000.0)
    ).metadata()

    assert metadata.reference_frequency_hz == 144_000_000.0


@pytest.mark.integration
@pytest.mark.parametrize(
    ("removed", "supplied"),
    [
        (("BPA",), SuppliedImageMetadata(beam_position_angle_degrees=0.0)),
        (
            ("BMAJ", "BMIN", "BPA"),
            SuppliedImageMetadata(
                beam_major_fwhm_degrees=0.01,
                beam_minor_fwhm_degrees=0.008,
                beam_position_angle_degrees=0.0,
            ),
        ),
    ],
)
def test_supplied_beam_values_fill_only_missing_keywords(
    tmp_path: Path,
    removed: tuple[str, ...],
    supplied: SuppliedImageMetadata,
) -> None:
    """SDC1 images give BMAJ and BMIN but omit BPA."""
    path = tmp_path / "partial-beam.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        for keyword in removed:
            del hdus[0].header[keyword]

    beam = FitsImageSource(path, supplied).metadata().beam

    assert beam.major_fwhm_degrees == 0.01
    assert beam.minor_fwhm_degrees == 0.008
    assert beam.position_angle_degrees == 0.0


@pytest.mark.integration
@pytest.mark.parametrize(
    ("data", "reference_frequency_hz", "supplied", "message"),
    [
        (
            np.zeros((2, 2), dtype=np.float32),
            150_000_000.0,
            SuppliedImageMetadata(reference_frequency_hz=150_000_000.0),
            "reference frequency",
        ),
        (
            np.zeros((1, 1, 2, 2), dtype=np.float32),
            None,
            SuppliedImageMetadata(reference_frequency_hz=150_000_000.0),
            "reference frequency",
        ),
        (
            np.zeros((2, 2), dtype=np.float32),
            150_000_000.0,
            SuppliedImageMetadata(beam_position_angle_degrees=20.0),
            "BPA",
        ),
        (
            np.zeros((2, 2), dtype=np.float32),
            150_000_000.0,
            SuppliedImageMetadata(brightness_unit="Jy/beam"),
            "supplied BUNIT duplicates",
        ),
    ],
)
def test_supplying_a_value_the_header_provides_is_rejected(
    tmp_path: Path,
    data: np.ndarray,
    reference_frequency_hz: float | None,
    supplied: SuppliedImageMetadata,
    message: str,
) -> None:
    """Supplied metadata never silently overrides the image's own header."""
    path = tmp_path / "complete-header.fits"
    _write_image(path, data, reference_frequency_hz=reference_frequency_hz)

    with pytest.raises(InvalidFitsImageError, match=message):
        FitsImageSource(path, supplied).metadata()


@pytest.mark.integration
@pytest.mark.parametrize("header_unit", [None, " "])
@pytest.mark.parametrize(
    ("supplied_unit", "unit"), [("JY/BEAM", "Jy/beam"), ("Jy/beam", "Jy/beam")]
)
def test_supplied_unit_fills_a_missing_or_blank_bunit(
    tmp_path: Path,
    header_unit: str | None,
    supplied_unit: str,
    unit: str,
) -> None:
    """SKA SDP exports and ddf-pipeline mosaics write no BUNIT."""
    path = tmp_path / "no-unit.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32), unit=header_unit)

    metadata = FitsImageSource(
        path, SuppliedImageMetadata(brightness_unit=supplied_unit)
    ).metadata()

    assert metadata.unit == unit


@pytest.mark.integration
def test_a_supplied_unit_meets_the_header_unit_rules(tmp_path: Path) -> None:
    """A supplied unit is parsed exactly as a header BUNIT would be."""
    path = tmp_path / "no-unit.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32), unit=None)

    with pytest.raises(
        InvalidFitsImageError,
        match="supplied brightness unit 'bananas' is not a unit",
    ):
        FitsImageSource(
            path, SuppliedImageMetadata(brightness_unit="bananas")
        ).metadata()


@pytest.mark.integration
def test_a_non_text_bunit_is_rejected(tmp_path: Path) -> None:
    """A numeric BUNIT is malformed rather than missing."""
    path = tmp_path / "numeric-unit.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32), unit=None)
    with fits.open(path, mode="update") as hdus:
        hdus[0].header["BUNIT"] = 1.0

    with pytest.raises(InvalidFitsImageError, match=r"invalid BUNIT 1\.0"):
        FitsImageSource(path).metadata()


def _write_stokes_plane(
    path: Path, *, crval: float, crpix: float = 1.0, cdelt: float = 1.0
) -> None:
    """Write one plane whose fourth axis is a single Stokes parameter."""
    _write_image(path, np.zeros((1, 1, 2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        header = hdus[0].header
        header["CRVAL4"], header["CRPIX4"], header["CDELT4"] = (
            crval,
            crpix,
            cdelt,
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("crval", "crpix", "cdelt"),
    [
        (1.0, 1.0, 1.0),
        (0.0, 0.0, 1.0),
        (1.0, 1.0, -1.0),
        # The world transform's own rounding still reads as a code.
        (1.0000000001, 1.0, 1.0),
    ],
)
def test_a_stokes_i_plane_is_read(
    tmp_path: Path, crval: float, crpix: float, cdelt: float
) -> None:
    """The parameter is the axis's world value at the plane, however coded."""
    path = tmp_path / "stokes-i.fits"
    _write_stokes_plane(path, crval=crval, crpix=crpix, cdelt=cdelt)

    assert FitsImageSource(path).metadata().shape_yx == (2, 2)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("crval", "crpix", "cdelt", "name"),
    [
        (2.0, 1.0, 1.0, "Q"),
        (4.0, 1.0, 1.0, "V"),
        (-5.0, 1.0, -1.0, "XX"),
        # SKA SDP data models encode the parameter in CRPIX, not CRVAL.
        (1.0, -5.0, -1.0, "XX"),
        (-2.0, 1.0, -1.0, "LL"),
        (9.0, 1.0, 1.0, "code 9"),
    ],
)
def test_a_plane_other_than_stokes_i_is_refused(
    tmp_path: Path, crval: float, crpix: float, cdelt: float, name: str
) -> None:
    """Polarised and instrumental planes are not total intensity."""
    path = tmp_path / "polarised.fits"
    _write_stokes_plane(path, crval=crval, crpix=crpix, cdelt=cdelt)

    with pytest.raises(UnsupportedFitsImageError, match=f"Stokes {name},"):
        FitsImageSource(path).metadata()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("crval", "crpix", "cdelt", "value"),
    [(1.4, 1.0, 1.0, "1.4"), (1e308, -1.0, 1e308, "inf")],
)
def test_a_stokes_value_that_is_no_parameter_code_is_refused(
    tmp_path: Path, crval: float, crpix: float, cdelt: float, value: str
) -> None:
    """A fractional or overflowing value is malformed, not near Stokes I."""
    path = tmp_path / "malformed-stokes.fits"
    _write_stokes_plane(path, crval=crval, crpix=crpix, cdelt=cdelt)

    with pytest.raises(
        InvalidFitsImageError,
        match=f"Stokes axis value of {value}, which is not a Stokes",
    ) as refusal:
        FitsImageSource(path).metadata()

    assert not isinstance(refusal.value, UnsupportedFitsImageError)


@pytest.mark.integration
@pytest.mark.parametrize(
    "rotation",
    [
        {"CROTA2": 30.0},
        {"CROTA1": 0.0, "CROTA2": 30.0},
        {"CROTA1": 30.0, "CROTA2": 30.0},
        {"CROTA2": 0.0, "PC1_1": 1.0, "PC2_2": 1.0},
    ],
)
def test_a_rotation_stated_once_is_read(
    tmp_path: Path, rotation: dict[str, float]
) -> None:
    """AIPS, Obit and OSKAR state CROTA so that it has one reading."""
    path = tmp_path / "rotated.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        hdus[0].header.update(rotation)

    metadata = FitsImageSource(path).metadata()

    pixel_to_sky = np.asarray(
        celestial_wcs_from_metadata(metadata).wcs.get_pc(), dtype=np.float64
    )
    angle = rotation.get("CROTA2", 0.0)
    np.testing.assert_allclose(
        pixel_to_sky[0, 1] / pixel_to_sky[0, 0], np.tan(np.radians(angle))
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("rotation", "message"),
    [
        ({"CROTA1": 30.0}, r"CROTA1 = 30\) differently from .*CROTA2 = 0"),
        (
            {"CROTA1": 10.0, "CROTA2": 30.0},
            r"CROTA1 = 10\) differently from .*CROTA2 = 30",
        ),
        ({"CROTA2": 30.0, "PC1_1": 1.0}, "both CROTA2 and a PC or CD"),
        ({"CROTA2": 30.0, "CD1_1": -0.001}, "both CROTA2 and a PC or CD"),
        ({"CROTA2": 30.0, "PC001001": 1.0}, "both CROTA2 and a PC or CD"),
        # wcslib ignores text and logical values, so none can be a rotation.
        ({"CROTA2": "thirty"}, "CROTA2 card that is not a finite number"),
        ({"CROTA1": "nan"}, "CROTA1 card that is not a finite number, 'nan'"),
        ({"CROTA2": "30"}, "CROTA2 card that is not a finite number, '30'"),
        ({"CROTA2": True}, "CROTA2 card that is not a finite number, True"),
    ],
)
def test_a_rotation_the_wcs_standard_would_drop_is_refused(
    tmp_path: Path, rotation: dict[str, float | str], message: str
) -> None:
    """Astropy silently ignores these, which would misplace every source."""
    path = tmp_path / "ambiguous-rotation.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        hdus[0].header.update(rotation)

    with warnings.catch_warnings():
        # Astropy warns that the AIPS-era PC spelling is deprecated.
        warnings.simplefilter("ignore")
        with pytest.raises(InvalidFitsImageError, match=message):
            FitsImageSource(path).metadata()


@pytest.mark.integration
def test_beam_keywords_still_missing_after_supply_are_rejected(
    tmp_path: Path,
) -> None:
    """Supplying one beam value does not excuse another missing value."""
    path = tmp_path / "no-beam.fits"
    _write_image(path, np.zeros((2, 2), dtype=np.float32))
    with fits.open(path, mode="update") as hdus:
        del hdus[0].header["BMIN"]
        del hdus[0].header["BPA"]

    with pytest.raises(InvalidFitsImageError, match="restoring beam"):
        FitsImageSource(
            path, SuppliedImageMetadata(beam_position_angle_degrees=0.0)
        ).metadata()


@pytest.mark.integration
def test_supplied_metadata_travels_with_a_serialized_source(
    tmp_path: Path,
) -> None:
    """Executor workers re-read metadata, so they need the supplied values."""
    path = tmp_path / "worker.fits"
    _write_image(
        path,
        np.arange(4, dtype=np.float32).reshape(2, 2),
        reference_frequency_hz=None,
    )
    source = FitsImageSource(
        path, SuppliedImageMetadata(reference_frequency_hz=144_000_000.0)
    )

    restored = pickle.loads(pickle.dumps(source))
    window = restored.read_window(ImageBounds(0, 2, 0, 2))

    assert restored.metadata().reference_frequency_hz == 144_000_000.0
    np.testing.assert_array_equal(window.values, [[0, 1], [2, 3]])


@pytest.mark.integration
def test_header_and_wcs_are_validated_once_per_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Many bounded reads share one validation of the same file.

    Tiled stages read hundreds of windows per image, and re-parsing the
    header and rebuilding both WCS objects for each of them cost more than
    reading the pixels.
    """
    path = tmp_path / "repeat.fits"
    _write_image(path, np.arange(64, dtype=np.float32).reshape(8, 8))
    validations = 0
    original = fits_module._metadata

    def counted(*arguments: Any, **keywords: Any) -> ImageMetadata:
        nonlocal validations
        validations += 1
        return original(*arguments, **keywords)

    monkeypatch.setattr(fits_module, "_metadata", counted)
    source = FitsImageSource(path)

    first = source.metadata()
    for start in range(4):
        source.read_window(ImageBounds(start, start + 2, 0, 2))
    again = source.metadata()

    assert validations == 1
    assert again == first


@pytest.mark.integration
def test_a_serialized_source_validates_the_file_itself(
    tmp_path: Path,
) -> None:
    """A cached validation must not travel to a worker as stale metadata.

    The file a worker opens is the authority on its own contents, so the
    restored source reads and validates it again.
    """
    path = tmp_path / "worker-validation.fits"
    _write_image(path, np.arange(4, dtype=np.float32).reshape(2, 2))
    source = FitsImageSource(path)
    source.metadata()

    payload = pickle.dumps(source)
    restored = pickle.loads(payload)

    assert not any(
        isinstance(value, ImageMetadata)
        for value in restored.__dict__.values()
    )
    assert restored.metadata() == source.metadata()


@pytest.mark.integration
def test_windows_share_one_open_file_per_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opening and parsing a FITS header costs more than reading pixels."""
    path = tmp_path / "reuse.fits"
    _write_image(path, np.arange(64, dtype=np.float32).reshape(8, 8))
    opens = 0
    original = fits.open

    def counted(*arguments: Any, **keywords: Any) -> Any:
        nonlocal opens
        opens += 1
        return original(*arguments, **keywords)

    monkeypatch.setattr(fits_module.fits, "open", counted)
    source = FitsImageSource(path)

    windows = [
        source.read_window(ImageBounds(start, start + 2, 0, 2))
        for start in range(4)
    ]

    assert opens == 1
    np.testing.assert_array_equal(windows[1].values, [[8, 9], [16, 17]])


@pytest.mark.integration
def test_threads_read_their_own_windows_correctly(tmp_path: Path) -> None:
    """Worker threads share a source, so they must not share a file cursor."""
    path = tmp_path / "threaded.fits"
    values = np.arange(4096, dtype=np.float32).reshape(64, 64)
    _write_image(path, values)
    source = FitsImageSource(path)
    requests = [
        ImageBounds(y, y + 8, x, x + 8)
        for y in range(0, 64, 8)
        for x in range(0, 64, 8)
    ] * 4

    with ThreadPoolExecutor(max_workers=8) as pool:
        windows = list(pool.map(source.read_window, requests))

    for bounds, window in zip(requests, windows, strict=True):
        np.testing.assert_array_equal(
            window.values,
            values[
                bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
            ],
        )


@pytest.mark.integration
def test_closing_a_source_releases_its_files_and_it_reads_again(
    tmp_path: Path,
) -> None:
    """A caller may release files without giving up the source."""
    path = tmp_path / "closed.fits"
    _write_image(path, np.arange(16, dtype=np.float32).reshape(4, 4))
    source = FitsImageSource(path)
    first = source.read_window(ImageBounds(0, 2, 0, 2))

    source.close()
    second = source.read_window(ImageBounds(0, 2, 0, 2))

    np.testing.assert_array_equal(second.values, first.values)


@pytest.mark.integration
def test_dropping_a_source_leaves_no_open_file(tmp_path: Path) -> None:
    """Holding a file open must not mean leaking it.

    A caller that simply drops a source, as scripts and workers do, would
    otherwise leave the file to the garbage collector and Python would
    report an unclosed file.
    """
    path = tmp_path / "dropped.fits"
    _write_image(path, np.arange(16, dtype=np.float32).reshape(4, 4))
    source = FitsImageSource(path)
    source.read_window(ImageBounds(0, 2, 0, 2))

    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
        del source
        gc.collect()

    assert [
        str(item.message) for item in log if item.category is ResourceWarning
    ] == []


@pytest.mark.integration
def test_closing_releases_files_opened_on_other_threads(
    tmp_path: Path,
) -> None:
    """Worker threads each open the file, and one close must free them all."""
    path = tmp_path / "threads.fits"
    _write_image(path, np.arange(16, dtype=np.float32).reshape(4, 4))
    source = FitsImageSource(path)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(
            pool.map(
                source.read_window,
                [ImageBounds(0, 2, 0, 2)] * 12,
            )
        )

    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
        source.close()
        gc.collect()

    assert [
        str(item.message) for item in log if item.category is ResourceWarning
    ] == []
    np.testing.assert_array_equal(
        source.read_window(ImageBounds(0, 2, 0, 2)).values, [[0, 1], [4, 5]]
    )
