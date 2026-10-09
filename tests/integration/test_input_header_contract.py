# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""The input header contract, one imager or pipeline convention at a time.

Each case writes a small image whose header follows one convention as its
writer produces it (the writer sources are listed on the input header
contract page), then runs the public finder on it. An accepted header must
publish a catalogue whose one source lies where the header's own WCS puts the
injected pixel; a refused header must fail before any product exists, with an
error that names what is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy import units
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.data_models import (
    PublicSourceFindingDiagnostics,
    SuppliedImageMetadata,
)
from hebog.executors import SerialExecutor
from hebog.io import (
    FitsImageSource,
    celestial_wcs_from_metadata,
    read_catalogue_fits_product,
    read_diagnostics_product,
)
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    UnsupportedSourceFinderConfigurationError,
)

pytestmark = pytest.mark.integration
# Each header is written as its writer leaves it, so Astropy and wcslib report
# what they repair or read in it. The tests assert what the finder reads and
# refuses; these marks ignore only the reports a test's headers provoke.
_AIPS_ERA_SPELLINGS = pytest.mark.filterwarnings(
    "ignore:PC00:astropy.wcs.FITSFixedWarning",
    "ignore:PROJP:astropy.wcs.FITSFixedWarning",
)

_SHAPE_YX = (64, 64)
_SOURCE_YX = (37.0, 26.0)
_BEAM_DEGREES = 4.0 / 3600.0
_PIXEL_DEGREES = 1.0 / 3600.0
_FREQUENCY_HZ = 144_000_000.0
_BEAM = {"BMAJ": _BEAM_DEGREES, "BMIN": _BEAM_DEGREES, "BPA": 0.0}
_SUPPLIED_BEAM = SuppliedImageMetadata(
    beam_major_fwhm_degrees=_BEAM_DEGREES,
    beam_minor_fwhm_degrees=_BEAM_DEGREES,
    beam_position_angle_degrees=0.0,
)


def _celestial(projection: str = "SIN") -> dict[str, object]:
    """Return RA and Dec axes with one-arcsecond pixels, east to the left."""
    return {
        "CTYPE1": f"RA---{projection}",
        "CTYPE2": f"DEC--{projection}",
        "CRPIX1": _SHAPE_YX[1] / 2 + 1,
        "CRPIX2": _SHAPE_YX[0] / 2 + 1,
        "CRVAL1": 180.0,
        "CRVAL2": 45.0,
        "CDELT1": -_PIXEL_DEGREES,
        "CDELT2": _PIXEL_DEGREES,
        "CUNIT1": "deg",
        "CUNIT2": "deg",
    }


def _frequency_axis(axis: int, *, width_hz: float = 1.0) -> dict[str, object]:
    """Return a one-channel frequency axis at the reference frequency."""
    return {
        f"CTYPE{axis}": "FREQ",
        f"CRPIX{axis}": 1.0,
        f"CRVAL{axis}": _FREQUENCY_HZ,
        f"CDELT{axis}": width_hz,
        f"CUNIT{axis}": "Hz",
    }


def _stokes_axis(axis: int, code: float = 1.0) -> dict[str, object]:
    """Return a one-plane Stokes axis holding the given parameter code."""
    return {
        f"CTYPE{axis}": "STOKES",
        f"CRPIX{axis}": 1.0,
        f"CRVAL{axis}": code,
        f"CDELT{axis}": 1.0,
    }


@dataclass(frozen=True)
class _Convention:
    """One header convention and the leading axes its data carries."""

    cards: dict[str, object]
    leading_axes: tuple[int, ...] = ()
    supplied: SuppliedImageMetadata | None = None
    removed: tuple[str, ...] = ()


def _wsclean(stokes: float = 1.0) -> dict[str, object]:
    """WSClean: RA, Dec, FREQ, STOKES; ``EQUINOX`` without ``RADESYS``."""
    return {
        **_celestial(),
        **_frequency_axis(3, width_hz=48_000_000.0),
        **_stokes_axis(4, stokes),
        "BUNIT": "JY/BEAM",
        **_BEAM,
        "EQUINOX": 2000.0,
        "LONPOLE": 180.0,
        "SPECSYS": "TOPOCENT",
        "BTYPE": "Intensity",
        "ORIGIN": "WSClean",
    }


def _ddfacet() -> dict[str, object]:
    """DDFacet: Stokes before frequency, ``RADESYS`` and ``RESTFRQ``."""
    return {
        **_celestial(),
        **_stokes_axis(3),
        **_frequency_axis(4),
        "BUNIT": "Jy/beam",
        **_BEAM,
        "RADESYS": "ICRS",
        "RESTFRQ": _FREQUENCY_HZ,
        "SPECSYS": "TOPOCENT",
        "ORIGIN": "DDFacet",
    }


def _lotss_mosaic() -> dict[str, object]:
    """ddf-pipeline LoTSS mosaic header: two axes, complete keywords."""
    return {
        **_celestial(),
        "RADESYS": "ICRS",
        "EQUINOX": 2000.0,
        "RESTFRQ": _FREQUENCY_HZ,
        "BUNIT": "JY/BEAM",
        **_BEAM,
        "TELESCOP": "LOFAR",
    }


def _generic_mosaic() -> dict[str, object]:
    """ddf-pipeline ``mosaic.py``: one copied beam, no unit or frequency."""
    return {**_celestial(), **_BEAM, "ORIGIN": "ddf-pipeline"}


def _lofar_hd_mosaic() -> dict[str, object]:
    """LOFAR-HD mosaic: unit and beam, no frame or frequency keyword."""
    return {**_celestial(), "BUNIT": "JY/BEAM", **_BEAM}


def _oskar() -> dict[str, object]:
    """OSKAR imager: three axes, zero ``CROTA``, no beam or ``CUNIT``."""
    cards = {**_celestial(), **_frequency_axis(3)}
    for keyword in ("CUNIT1", "CUNIT2", "CUNIT3"):
        del cards[keyword]
    return {
        **cards,
        "CROTA1": 0.0,
        "CROTA2": 0.0,
        "CROTA3": 0.0,
        "BUNIT": "JY/BEAM",
        "EQUINOX": 2000.0,
        "OBSRA": 180.0,
        "OBSDEC": 45.0,
    }


def _ska_sdp() -> dict[str, object]:
    """SKA SDP data models: Stokes before frequency, no ``BUNIT``."""
    return {
        **_celestial(),
        **_stokes_axis(3),
        **_frequency_axis(4, width_hz=1_000_000.0),
        "RADESYS": "ICRS",
        **_BEAM,
    }


def _casa() -> dict[str, object]:
    """CASA ``exportfits``: a PC matrix, FK5 J2000 and ``RESTFRQ``."""
    return {
        **_celestial(),
        **_frequency_axis(3),
        **_stokes_axis(4),
        "PC1_1": 1.0,
        "PC1_2": 0.0,
        "PC2_1": 0.0,
        "PC2_2": 1.0,
        "RADESYS": "FK5",
        "EQUINOX": 2000.0,
        "RESTFRQ": _FREQUENCY_HZ,
        "SPECSYS": "LSRK",
        "BUNIT": "Jy/beam",
        **_BEAM,
        "BTYPE": "Intensity",
    }


def _aips_rotated() -> dict[str, object]:
    """AIPS and Obit style: the rotation on the latitude axis only."""
    return {**_lotss_mosaic(), "CROTA1": 0.0, "CROTA2": 30.0}


def _gleam_x_mosaic() -> dict[str, object]:
    """GLEAM-X DR1 mosaic: ZEA, ``EPOCH``, a non-standard ``FREQ`` keyword."""
    cards = {**_celestial("ZEA"), "BUNIT": "JY/BEAM", **_BEAM}
    for keyword in ("CUNIT1", "CUNIT2"):
        del cards[keyword]
    return {
        **cards,
        "CELLSCAL": "CONSTANT",
        "BTYPE": "intensity",
        "EPOCH": 2000.0,
        "ORIGIN": "Miriad fits",
        "FREQ": _FREQUENCY_HZ,
        "TELESCOP": "MWA",
    }


def _mightee() -> dict[str, object]:
    """MIGHTEE DR1: two axes, yet ``FREQ`` and ``STOKES`` axes declared."""
    return {
        **_celestial("TAN"),
        "CTYPE3": "FREQ",
        "CTYPE4": "STOKES",
        "CRVAL3": _FREQUENCY_HZ,
        "CRVAL4": 1.0,
        "CRPIX3": 1.0,
        "CRPIX4": 1.0,
        "CDELT3": 1.0,
        "CDELT4": 1.0,
        "CUNIT3": "Hz",
        "EQUINOX": 2000.0,
        "BUNIT": "Jy/beam",
        **_BEAM,
        "TELESCOP": "MeerKAT",
    }


def _sdc1_miriad() -> dict[str, object]:
    """SKA Data Challenge 1 (Miriad): ``EPOCH`` and no ``BPA``."""
    cards = {
        **_celestial(),
        **_frequency_axis(3, width_hz=420_000_000.0),
        **_stokes_axis(4),
        "BUNIT": "JY/BEAM",
        "EPOCH": 2000.0,
        **_BEAM,
    }
    del cards["BPA"]
    return cards


def _obit_mfimage() -> dict[str, object]:
    """Obit MFImage: a 16-plane ``SPECLNMF`` axis and a CLEAN-card beam."""
    cards = {**_celestial(), **_frequency_axis(3), **_stokes_axis(4)}
    cards["CTYPE3"] = "SPECLNMF"
    return {
        **cards,
        "CROTA1": 0.0,
        "CROTA2": 0.0,
        "EPOCH": 2000.0,
        "EQUINOX": 2000.0,
        "BUNIT": "JY/BEAM",
        "RESTFREQ": _FREQUENCY_HZ,
        "NTERM": 2,
        "NSPEC": 14,
        "CLEANBMJ": _BEAM_DEGREES,
        "CLEANBMN": _BEAM_DEGREES,
        "CLEANBPA": 0.0,
    }


def _galactic() -> dict[str, object]:
    """SMGPS-style Galactic longitude and latitude axes."""
    cards = _lotss_mosaic()
    del cards["RADESYS"], cards["EQUINOX"]
    return {**cards, "CTYPE1": "GLON-SIN", "CTYPE2": "GLAT-SIN"}


def _cd_matrix() -> dict[str, object]:
    """A ``CD`` matrix in place of ``CDELT``."""
    cards = _lotss_mosaic()
    del cards["CDELT1"], cards["CDELT2"]
    return {
        **cards,
        "CD1_1": -_PIXEL_DEGREES,
        "CD1_2": 0.0,
        "CD2_1": 0.0,
        "CD2_2": _PIXEL_DEGREES,
    }


def _ncp() -> dict[str, object]:
    """A slant orthographic (NCP) projection, with its ``PV`` parameters."""
    return {**_lotss_mosaic(), "PV2_1": 0.0, "PV2_2": 1.0, "LATPOLE": 45.0}


def _aips_era_projection() -> dict[str, object]:
    """NCP parameters as ``PROJP``, which wcslib still reads as ``PV``."""
    return {**_lotss_mosaic(), "PROJP1": 0.0, "PROJP2": 1.0}


def _aips_era_matrix() -> dict[str, object]:
    """A ``PC`` matrix in the AIPS-era spelling, which wcslib still reads."""
    return {**_lotss_mosaic(), "PC001001": 1.0, "PC002002": 1.0}


def _rest_frequency() -> dict[str, object]:
    """The frequency in ``RESTFREQ``, the older spelling of ``RESTFRQ``."""
    cards = _lotss_mosaic()
    del cards["RESTFRQ"]
    return {**cards, "RESTFREQ": _FREQUENCY_HZ}


_ACCEPTED: dict[str, tuple[_Convention, str]] = {
    "wsclean": (_Convention(_wsclean(), (1, 1)), "fk5"),
    "ddfacet": (_Convention(_ddfacet(), (1, 1)), "icrs"),
    "ddf-pipeline-lotss-mosaic": (_Convention(_lotss_mosaic()), "icrs"),
    "ddf-pipeline-generic-mosaic-supplied": (
        _Convention(
            _generic_mosaic(),
            supplied=SuppliedImageMetadata(
                reference_frequency_hz=_FREQUENCY_HZ,
                brightness_unit="Jy/beam",
            ),
        ),
        "icrs",
    ),
    "lofar-hd-mosaic-supplied": (
        _Convention(
            _lofar_hd_mosaic(),
            supplied=SuppliedImageMetadata(
                reference_frequency_hz=_FREQUENCY_HZ
            ),
        ),
        "icrs",
    ),
    "oskar-supplied": (
        _Convention(_oskar(), (1,), supplied=_SUPPLIED_BEAM),
        "fk5",
    ),
    "ska-sdp-supplied": (
        _Convention(
            _ska_sdp(),
            (1, 1),
            supplied=SuppliedImageMetadata(brightness_unit="Jy/beam"),
        ),
        "icrs",
    ),
    "casa": (_Convention(_casa(), (1, 1)), "fk5"),
    "aips-rotated": (_Convention(_aips_rotated()), "icrs"),
    "gleam-x-zea-supplied": (
        _Convention(
            _gleam_x_mosaic(),
            supplied=SuppliedImageMetadata(
                reference_frequency_hz=_FREQUENCY_HZ
            ),
        ),
        "fk5",
    ),
    "mightee-declared-axes": (_Convention(_mightee()), "fk5"),
    "sdc1-miriad-supplied": (
        _Convention(
            _sdc1_miriad(),
            (1, 1),
            supplied=SuppliedImageMetadata(beam_position_angle_degrees=0.0),
        ),
        "fk5",
    ),
}

_REFUSED: dict[str, tuple[_Convention, type[SourceFinderError], str]] = {
    "ddf-pipeline-generic-mosaic": (
        _Convention(_generic_mosaic()),
        InvalidSourceFinderInputError,
        "requires a non-empty BUNIT, or a supplied brightness unit",
    ),
    "lofar-hd-mosaic": (
        _Convention(_lofar_hd_mosaic()),
        InvalidSourceFinderInputError,
        "requires a reference frequency in a FREQ axis, RESTFRQ or RESTFREQ",
    ),
    "oskar": (
        _Convention(_oskar(), (1,)),
        InvalidSourceFinderInputError,
        "requires BMAJ, BMIN, and BPA restoring beam",
    ),
    "ska-sdp": (
        _Convention(_ska_sdp(), (1, 1)),
        InvalidSourceFinderInputError,
        "requires a non-empty BUNIT",
    ),
    "gleam-x-zea": (
        _Convention(_gleam_x_mosaic()),
        InvalidSourceFinderInputError,
        "requires a reference frequency",
    ),
    "sdc1-miriad": (
        _Convention(_sdc1_miriad(), (1, 1)),
        InvalidSourceFinderInputError,
        "requires BMAJ, BMIN, and BPA restoring beam",
    ),
    "obit-mfimage-cube": (
        _Convention(_obit_mfimage(), (1, 16)),
        InvalidSourceFinderInputError,
        r"non-singleton leading axes, SPECLNMF \(NAXIS3 = 16\)",
    ),
    "casa-per-plane-beams": (
        _Convention(
            {**_casa(), "CASAMBM": True},
            (1, 1),
            removed=("BMAJ", "BMIN", "BPA"),
        ),
        InvalidSourceFinderInputError,
        "requires BMAJ, BMIN, and BPA restoring beam",
    ),
    "wsclean-instrumental-xx": (
        _Convention(_wsclean(stokes=-5.0), (1, 1)),
        InvalidSourceFinderInputError,
        "plane is Stokes XX, and the public finder measures Stokes I only",
    ),
    "rotation-on-longitude-only": (
        _Convention({**_lotss_mosaic(), "CROTA1": 30.0}),
        InvalidSourceFinderInputError,
        r"longitude axis \(CROTA1 = 30\) differently from its latitude",
    ),
    "rotation-beside-a-matrix": (
        _Convention({**_casa(), "CROTA2": 30.0}, (1, 1)),
        InvalidSourceFinderInputError,
        "gives both CROTA2 and a PC or CD matrix",
    ),
    "ecliptic": (
        _Convention(
            {**_lotss_mosaic(), "CTYPE1": "ELON-SIN", "CTYPE2": "ELAT-SIN"}
        ),
        InvalidSourceFinderInputError,
        "ELON/ELAT celestial axes, and the finder reads RA/DEC or GLON/GLAT",
    ),
    "supergalactic": (
        _Convention(
            {**_lotss_mosaic(), "CTYPE1": "SLON-SIN", "CTYPE2": "SLAT-SIN"}
        ),
        InvalidSourceFinderInputError,
        "SLON/SLAT celestial axes",
    ),
    "ska-sdp-instrumental-xx": (
        # The SDP data models encode the parameter through CRPIX.
        _Convention(
            {**_ska_sdp(), "CRPIX3": -5.0, "CRVAL3": 1.0, "CDELT3": -1.0},
            (1, 1),
            supplied=SuppliedImageMetadata(brightness_unit="Jy/beam"),
        ),
        InvalidSourceFinderInputError,
        "plane is Stokes XX",
    ),
    "galactic": (
        _Convention(_galactic()),
        UnsupportedSourceFinderConfigurationError,
        "requires an ICRS or FK5 J2000 celestial WCS, not GALACTIC",
    ),
    "fk5-b1950": (
        _Convention({**_lotss_mosaic(), "RADESYS": "FK5", "EQUINOX": 1950.0}),
        UnsupportedSourceFinderConfigurationError,
        "not FK5, equinox 1950",
    ),
}

_WSCLEAN = _Convention(_wsclean(), (1, 1))
# Every numeric card the finder reads, each in a header it accepts.
_NUMBER_CARDS: dict[str, _Convention] = {
    **dict.fromkeys(
        (
            *(f"CRVAL{axis}" for axis in range(1, 5)),
            *(f"CRPIX{axis}" for axis in range(1, 5)),
            *(f"CDELT{axis}" for axis in range(1, 5)),
            "LONPOLE",
            "EQUINOX",
            "BMAJ",
            "BMIN",
            "BPA",
        ),
        _WSCLEAN,
    ),
    **dict.fromkeys(
        ("PC1_1", "PC1_2", "PC2_1", "PC2_2", "RESTFRQ"),
        _Convention(_casa(), (1, 1)),
    ),
    **dict.fromkeys(("CROTA1", "CROTA2"), _Convention(_aips_rotated())),
    **dict.fromkeys(
        ("CD1_1", "CD1_2", "CD2_1", "CD2_2"), _Convention(_cd_matrix())
    ),
    **dict.fromkeys(("PV2_1", "PV2_2", "LATPOLE"), _Convention(_ncp())),
    **dict.fromkeys(("PC001001", "PC002002"), _Convention(_aips_era_matrix())),
    **dict.fromkeys(("PROJP1", "PROJP2"), _Convention(_aips_era_projection())),
    "EPOCH": _Convention(
        _gleam_x_mosaic(),
        supplied=SuppliedImageMetadata(reference_frequency_hz=_FREQUENCY_HZ),
    ),
    "RESTFREQ": _Convention(_rest_frequency()),
}
# What fills each beam or frequency card when the header leaves it out.
_SUPPLIED_FOR = {
    "BMAJ": SuppliedImageMetadata(beam_major_fwhm_degrees=_BEAM_DEGREES),
    "BMIN": SuppliedImageMetadata(beam_minor_fwhm_degrees=_BEAM_DEGREES / 2),
    "BPA": SuppliedImageMetadata(beam_position_angle_degrees=0.0),
    "RESTFRQ": SuppliedImageMetadata(reference_frequency_hz=_FREQUENCY_HZ),
    "RESTFREQ": SuppliedImageMetadata(reference_frequency_hz=_FREQUENCY_HZ),
}
# The cards wcslib reads: one without a value takes the keyword's default.
_WCS_NUMBER_CARDS = {
    keyword: convention
    for keyword, convention in _NUMBER_CARDS.items()
    if keyword not in _SUPPLIED_FOR
}
# What a writer might leave where a card needs a number. Astropy and wcslib
# raise no error for any of them: wcslib warns and reads the keyword's
# default instead, and a logical beam or frequency is read as one.
_NOT_NUMBERS = {
    "not-a-number": "NAN",
    "infinity": "INF",
    "text": "'180.0'",
    "number-with-unit": "180.0 deg",
    "two-decimal-points": "1.8E+02.0",
    "overflow": "1.0E999",
    "logical": "T",
    "complex": "(1.0, 2.0)",
}


def _plane() -> npt.NDArray[np.float32]:
    """Return a bright beam-sized source on one-milliJansky noise."""
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    sigma = 4.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    radius_squared = (yy - _SOURCE_YX[0]) ** 2 + (xx - _SOURCE_YX[1]) ** 2
    source = 0.5 * np.exp(-radius_squared / (2.0 * sigma**2))
    noise = np.random.default_rng(14).normal(0.0, 1e-3, _SHAPE_YX)
    return np.asarray(source + noise, dtype=np.float32)


def _write(path: Path, convention: _Convention) -> None:
    """Write the shared plane under one convention's header."""
    header = fits.Header()
    for keyword, value in convention.cards.items():
        if keyword not in convention.removed:
            header[keyword] = value
    data = np.broadcast_to(_plane(), convention.leading_axes + _SHAPE_YX)
    fits.PrimaryHDU(data=np.ascontiguousarray(data), header=header).writeto(
        path
    )


def _overwrite_card(path: Path, keyword: str, card: str) -> None:
    """Overwrite one keyword's card in the file with another card.

    Astropy tidies or refuses a malformed card it is asked to write, so the
    card is replaced in the file's bytes.
    """
    content = bytearray(path.read_bytes())
    start = content.index(f"{keyword:<8}=".encode())
    assert start % 80 == 0
    content[start : start + 80] = card.ljust(80).encode()
    path.write_bytes(content)


def _replace_card(path: Path, keyword: str, value_text: str) -> None:
    """Overwrite one card's value in the file, as a writer left it."""
    _overwrite_card(path, keyword, f"{keyword:<8}= {value_text:>20}")


def _write_accepted(path: Path, convention: _Convention) -> None:
    """Write the shared plane under a header the reader accepts."""
    _write(path, convention)
    source = FitsImageSource(path, convention.supplied)
    source.metadata()
    source.close()


def _separation_arcsec(
    result: hebog.SourceFinderResult, header: fits.Header
) -> float:
    """Return how far the one published source lies from the injected one.

    The injected position is where the header's own WCS puts its pixel.
    """
    catalogue = read_catalogue_fits_product(result.catalogue)
    assert len(catalogue.sources) == 1
    pixel = WCS(header).celestial.pixel_to_world(_SOURCE_YX[1], _SOURCE_YX[0])
    expected = cast(SkyCoord, cast(SkyCoord, pixel).icrs)
    position = catalogue.sources[0].position
    published = SkyCoord(
        position.right_ascension_degrees * units.deg,
        position.declination_degrees * units.deg,
        frame="icrs",
    )
    separation = cast(Any, published.separation(expected))
    return float(separation.arcsec)


def _request(tmp_path: Path, convention: _Convention) -> SourceFinderRequest:
    """Return a request for the written image, with any supplied metadata."""
    return SourceFinderRequest(
        tmp_path / "image.fits",
        tmp_path / "products",
        "header-contract",
        supplied_metadata=convention.supplied,
    )


# MIGHTEE declares frequency and Stokes axes on a two-axis image.
@pytest.mark.filterwarnings(
    "ignore:The WCS transformation has more axes:astropy.wcs.FITSFixedWarning"
)
@pytest.mark.parametrize(
    ("convention", "frame"), _ACCEPTED.values(), ids=_ACCEPTED.keys()
)
def test_accepted_convention_publishes_its_source_where_its_wcs_puts_it(
    tmp_path: Path,
    convention: _Convention,
    frame: str,
) -> None:
    """The finder reads the frame, frequency and orientation as written."""
    _write(tmp_path / "image.fits", convention)

    result = hebog.find_sources(
        _request(tmp_path, convention),
        SourceFinderConfig(5.0, 3.0, 7),
        SerialExecutor(),
    )

    metadata = FitsImageSource(
        tmp_path / "image.fits", convention.supplied
    ).metadata()
    assert metadata.celestial_wcs.coordinate_frame == frame
    assert metadata.unit == "Jy/beam"
    catalogue = read_catalogue_fits_product(result.catalogue)
    assert catalogue.reference_frequency_hz == _FREQUENCY_HZ
    header = cast(fits.Header, fits.getheader(tmp_path / "image.fits"))
    assert _separation_arcsec(result, header) < 0.05
    diagnostics = read_diagnostics_product(result.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert diagnostics.provenance.supplied_image_metadata == (
        convention.supplied
    )


@pytest.mark.parametrize(
    ("convention", "error", "message"), _REFUSED.values(), ids=_REFUSED.keys()
)
def test_refused_convention_names_what_is_wrong_before_any_product(
    tmp_path: Path,
    convention: _Convention,
    error: type[SourceFinderError],
    message: str,
) -> None:
    """A refusal says which keyword or layout is at fault."""
    _write(tmp_path / "image.fits", convention)

    with pytest.raises(error, match=message):
        hebog.find_sources(
            _request(tmp_path, convention),
            SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()


@pytest.mark.parametrize(
    "value_text", _NOT_NUMBERS.values(), ids=_NOT_NUMBERS.keys()
)
@pytest.mark.parametrize(
    ("keyword", "convention"), _NUMBER_CARDS.items(), ids=_NUMBER_CARDS.keys()
)
@_AIPS_ERA_SPELLINGS
def test_a_card_that_is_not_a_number_is_refused_by_its_keyword(
    tmp_path: Path,
    keyword: str,
    convention: _Convention,
    value_text: str,
) -> None:
    """No numeric card is read as a default or as another number."""
    _write_accepted(tmp_path / "image.fits", convention)
    _replace_card(tmp_path / "image.fits", keyword, value_text)

    with pytest.raises(
        InvalidSourceFinderInputError,
        match=f"has a {keyword} card that is not a finite number",
    ):
        hebog.find_sources(
            _request(tmp_path, convention),
            SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()


@pytest.mark.parametrize(
    ("keyword", "convention"),
    _WCS_NUMBER_CARDS.items(),
    ids=_WCS_NUMBER_CARDS.keys(),
)
@_AIPS_ERA_SPELLINGS
def test_a_wcs_card_without_a_value_is_refused_by_its_keyword(
    tmp_path: Path,
    keyword: str,
    convention: _Convention,
) -> None:
    """A card left empty is not read as the keyword's default."""
    _write_accepted(tmp_path / "image.fits", convention)
    _replace_card(tmp_path / "image.fits", keyword, "")

    with pytest.raises(
        InvalidSourceFinderInputError,
        match=f"has a {keyword} card with no value",
    ):
        hebog.find_sources(
            _request(tmp_path, convention),
            SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()


@pytest.mark.parametrize(
    ("keyword", "supplied"), _SUPPLIED_FOR.items(), ids=_SUPPLIED_FOR.keys()
)
# wcslib reports a frequency card that has no value.
@pytest.mark.filterwarnings("ignore:RESTFRE?Q *=:astropy.wcs.FITSFixedWarning")
def test_a_beam_or_frequency_card_without_a_value_is_a_missing_keyword(
    tmp_path: Path,
    keyword: str,
    supplied: SuppliedImageMetadata,
) -> None:
    """An empty card is refused like an absent one, and supplied like one."""
    image = tmp_path / "image.fits"
    cards = _rest_frequency() if keyword == "RESTFREQ" else _lotss_mosaic()
    _write_accepted(image, _Convention(cards))
    _replace_card(image, keyword, "")

    with pytest.raises(InvalidSourceFinderInputError, match="requires"):
        hebog.find_sources(
            _request(tmp_path, _Convention(cards)),
            SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()
    # A value supplied for a card the header holds would be a duplicate.
    source = FitsImageSource(image, supplied)
    metadata = source.metadata()
    source.close()
    assert metadata.reference_frequency_hz == _FREQUENCY_HZ


@pytest.mark.parametrize(
    "value_text",
    ("180", "+180.0", "1.8E2", ".18E3", "1.8D2", "1.80000000000000D+02"),
)
def test_a_number_is_read_in_any_fits_spelling(
    tmp_path: Path, value_text: str
) -> None:
    """The rule refuses what is not a number, not how a number is written.

    wcslib stops reading a FITS ``D`` exponent at the letter, so on its own
    it would read the last two spellings as 1.8.
    """
    image = tmp_path / "image.fits"
    _write_accepted(image, _Convention(_lotss_mosaic()))
    _replace_card(image, "CRVAL1", value_text)

    source = FitsImageSource(image)
    celestial_wcs = celestial_wcs_from_metadata(source.metadata())
    header = source.header()
    source.close()

    assert celestial_wcs.wcs.crval[0] == 180.0
    assert WCS(header).wcs.crval[0] == 180.0


def test_the_finder_header_holds_each_number_exactly(tmp_path: Path) -> None:
    """A double-precision number reaches wcslib whole, and no card is lost.

    Astropy keeps 20 characters when it writes a number, three fewer than
    this pixel scale needs.
    """
    image = tmp_path / "image.fits"
    _write_accepted(image, _Convention(_lotss_mosaic()))
    _replace_card(image, "CDELT1", "-2.777777777777778E-04")

    source = FitsImageSource(image)
    header = source.header()
    source.close()

    assert WCS(header).wcs.cdelt[0] == -2.777777777777778e-04
    assert header["CDELT1"] == -2.777777777777778e-04
    written = cast(fits.Header, fits.getheader(image))
    assert list(header) == list(written)
    assert header["BUNIT"] == written["BUNIT"]


def test_the_finder_header_keeps_wcslib_reading_of_a_repeated_keyword(
    tmp_path: Path,
) -> None:
    """FITS leaves a repeated keyword undefined, and the reading stays put.

    Astropy reads the first card and wcslib the last; each card keeps its
    own value, so the transform is the one wcslib always built.
    """
    image = tmp_path / "image.fits"
    _write_accepted(image, _Convention(_lotss_mosaic()))
    _overwrite_card(image, "TELESCOP", "CRVAL1  =                 10.0")

    source = FitsImageSource(image)
    header = source.header()
    source.close()

    written = cast(fits.Header, fits.getheader(image))
    assert written["CRVAL1"] == 180.0
    assert WCS(header).wcs.crval[0] == WCS(written).wcs.crval[0] == 10.0


# Astropy reports the unquoted OBSERVER text in several verification warnings.
@pytest.mark.filterwarnings("ignore::astropy.io.fits.verify.VerifyWarning")
def test_the_finder_header_leaves_cards_wcslib_does_not_read_as_numbers(
    tmp_path: Path,
) -> None:
    """A ``HIERARCH`` or record-valued card is not turned into a number.

    Astropy reads ``HIERARCH CRVAL1`` as ``CRVAL1`` and a record-valued
    card as a float, and wcslib reads neither that way.
    """
    image = tmp_path / "image.fits"
    kept = {
        "ORIGIN": "HIERARCH CRVAL1 = 10.0",
        "CUNIT1": "HIERARCH ESO DET GAIN = 1.5D0",
        "TELESCOP": "DP1     = 'AXIS.1: 1.5'",
    }
    # ORIGIN is written first, so the HIERARCH card precedes the real one.
    _write_accepted(image, _Convention({"ORIGIN": "x", **_lotss_mosaic()}))
    for keyword, card in kept.items():
        _overwrite_card(image, keyword, card)
    # Unquoted text, which Astropy cannot parse, is no float either.
    _overwrite_card(image, "CUNIT2", "OBSERVER= J. Smith")

    source = FitsImageSource(image)
    header = source.header()
    source.close()

    assert "OBSERVER" in header
    assert WCS(header).wcs.crval[0] == 180.0
    header_text = header.tostring()
    assert all(card in header_text for card in kept.values())


def test_the_finder_header_is_the_caller_s_own(tmp_path: Path) -> None:
    """Changing a returned header changes no later reading of the file."""
    image = tmp_path / "image.fits"
    _write_accepted(image, _Convention(_lotss_mosaic()))

    source = FitsImageSource(image)
    header = source.header()
    header["BUNIT"] = "K"
    header["CRVAL1"] = 10.0
    reread = source.header()
    metadata = source.metadata()
    source.close()

    assert reread["BUNIT"] == "JY/BEAM"
    assert reread["CRVAL1"] == 180.0
    assert metadata.unit == "Jy/beam"


# wcslib reports that it sets DATE-OBS from MJD-OBS.
@pytest.mark.filterwarnings(
    "ignore:'datfix' made the change:astropy.wcs.FITSFixedWarning"
)
def test_numbers_with_d_exponents_publish_the_source_where_they_put_it(
    tmp_path: Path,
) -> None:
    """Given a header whose writer marked every number as double precision,
    when the finder runs,
    then the source, the frame and the frequency are read as written.

    Read by wcslib alone, a ``CRVAL1`` of ``1.8D+02`` is 1.8 degrees, a
    ``CDELT1`` of ``-2.8D-04`` is 2.8 degrees a pixel, a frequency-axis
    ``CRVAL3`` of ``1.44D+08`` is 1.44 Hz and an ``MJD-OBS`` of ``5.9D+04``
    is a day in 1858.
    """
    image = tmp_path / "image.fits"
    convention = _Convention({**_wsclean(), "MJD-OBS": 59000.0}, (1, 1))
    _write(image, convention)
    header = cast(fits.Header, fits.getheader(image))
    numbers = [
        keyword for keyword, host in _NUMBER_CARDS.items() if host is _WSCLEAN
    ]
    for keyword in (*numbers, "MJD-OBS"):
        number = cast(float, header[keyword])
        _replace_card(image, keyword, f"{number:.15E}".replace("E", "D"))

    result = hebog.find_sources(
        _request(tmp_path, convention),
        SourceFinderConfig(5.0, 3.0, 7),
        SerialExecutor(),
    )

    assert _separation_arcsec(result, header) < 0.05
    catalogue = read_catalogue_fits_product(result.catalogue)
    assert catalogue.reference_frequency_hz == _FREQUENCY_HZ
    source = FitsImageSource(image)
    assert source.metadata().celestial_wcs.coordinate_frame == "fk5"
    source.close()
    # wcslib reads the date too, and the image products carry it.
    assert fits.getheader(result.rms_path)["MJD-OBS"] == 59000.0


@pytest.mark.parametrize(
    ("keyword", "card", "convention"),
    [
        ("BUNIT", "BUNIT   = Jy/beam", _Convention(_lotss_mosaic())),
        # A cube is refused by naming its axes, which reads their CTYPE.
        ("CTYPE3", "CTYPE3  = FREQ", _Convention(_wsclean(), (1, 4))),
    ],
    ids=["unquoted-unit", "unquoted-axis-type"],
)
def test_text_astropy_cannot_parse_is_refused_by_its_keyword(
    tmp_path: Path, keyword: str, card: str, convention: _Convention
) -> None:
    """Text without its quotes is not a FITS value, and Astropy raises."""
    _write(tmp_path / "image.fits", convention)
    _overwrite_card(tmp_path / "image.fits", keyword, card)

    with pytest.raises(
        InvalidSourceFinderInputError,
        match=f"has a {keyword} card that cannot be parsed",
    ):
        hebog.find_sources(
            _request(tmp_path, convention),
            SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()


@pytest.mark.parametrize(
    ("keyword", "card"),
    [
        ("SIMPLE", "SIMPLE  =                    F"),
        ("BITPIX", "BITPIX  =                -32.0"),
        ("BITPIX", "BITPIX  = 'x'"),
        ("BITPIX", "BITPIX  =                    T"),
        ("BITPIX", "BITPIX  =                  -16"),
        ("NAXIS", "NAXIS   =                    3"),
        ("NAXIS", "NAXIS   =                  2.0"),
        ("NAXIS1", "NAXIS1  =                 64.0"),
        ("NAXIS1", "NAXIS1  = 'wide'"),
    ],
)
# Astropy reports the cards it cannot verify or decode, and leaves the file
# open when ``fits.open`` raises, so it is closed only when collected.
@pytest.mark.filterwarnings(
    "ignore::astropy.io.fits.verify.VerifyWarning",
    "ignore:non-ASCII characters are present:"
    "astropy.utils.exceptions.AstropyUserWarning",
    "ignore:Header block contains null bytes:"
    "astropy.utils.exceptions.AstropyUserWarning",
    "ignore:Exception ignored while finalizing file:"
    "pytest.PytestUnraisableExceptionWarning",
)
def test_a_structural_card_fits_does_not_allow_is_an_invalid_input(
    tmp_path: Path, keyword: str, card: str
) -> None:
    """Astropy raises whatever such a card first breaks; the finder's error
    is the one a caller handles for any file it cannot read.
    """
    convention = _Convention(_lotss_mosaic())
    _write(tmp_path / "image.fits", convention)
    _overwrite_card(tmp_path / "image.fits", keyword, card)

    with pytest.raises(
        InvalidSourceFinderInputError,
        match=r"cannot read FITS image|standard image|unreadable",
    ):
        hebog.find_sources(
            _request(tmp_path, convention),
            SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )

    assert not (tmp_path / "products").exists()


@pytest.mark.parametrize("keyword", ["RESTFRQ", "BMIN", "BPA"])
def test_a_repeated_keyword_astropy_reads_comes_from_its_first_card(
    tmp_path: Path, keyword: str
) -> None:
    """The limitation the contract states for the beam and ``RESTFRQ``."""
    image = tmp_path / "image.fits"
    _write_accepted(image, _Convention(_lotss_mosaic()))
    source = FitsImageSource(image)
    first = source.metadata()
    source.close()
    _overwrite_card(image, "TELESCOP", f"{keyword:<8}=               0.0001")

    source = FitsImageSource(image)
    repeated = source.metadata()
    source.close()

    assert repeated.beam == first.beam
    assert repeated.reference_frequency_hz == first.reference_frequency_hz


def test_a_repeated_frequency_axis_value_comes_from_its_last_card(
    tmp_path: Path,
) -> None:
    """The limitation the contract states for what wcslib reads."""
    image = tmp_path / "image.fits"
    _write_accepted(image, _WSCLEAN)
    _overwrite_card(image, "SPECSYS", "CRVAL3  =          200000000.0")

    source = FitsImageSource(image)
    frequency_hz = source.metadata().reference_frequency_hz
    source.close()

    assert frequency_hz == 200_000_000.0
