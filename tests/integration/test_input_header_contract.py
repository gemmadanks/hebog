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
    read_catalogue_fits_product,
    read_diagnostics_product,
)
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    UnsupportedSourceFinderConfigurationError,
)

pytestmark = pytest.mark.integration

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
        "requires a reference frequency in RESTFRQ, RESTFREQ or a FREQ axis",
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


def _request(tmp_path: Path, convention: _Convention) -> SourceFinderRequest:
    """Return a request for the written image, with any supplied metadata."""
    return SourceFinderRequest(
        tmp_path / "image.fits",
        tmp_path / "products",
        "header-contract",
        supplied_metadata=convention.supplied,
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
    assert len(catalogue.sources) == 1
    header = cast(fits.Header, fits.getheader(tmp_path / "image.fits"))
    pixel = WCS(header).celestial.pixel_to_world(_SOURCE_YX[1], _SOURCE_YX[0])
    expected = cast(SkyCoord, cast(SkyCoord, pixel).icrs)
    position = catalogue.sources[0].position
    published = SkyCoord(
        position.right_ascension_degrees * units.deg,
        position.declination_degrees * units.deg,
        frame="icrs",
    )
    separation = cast(Any, published.separation(expected))
    assert float(separation.arcsec) < 0.05
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
