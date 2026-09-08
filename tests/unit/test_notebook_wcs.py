# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeStubs=false
"""Analytic non-ICRS notebook geometry, with no campaign data or execution."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from hebog import public_api
from hebog.algorithms import astrometry
from hebog.data_models import ImageBounds
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.validation import products, public_measurement_projection
from hebog.validation.comparison import CatalogueSource

_RUNNER = runpy.run_path(
    str(
        Path(__file__).parents[2]
        / "scripts/benchmark/run_phase5_public_finder_hebog.py"
    )
)


def _header(frame: str) -> fits.Header:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    wcs.wcs.crpix = [17, 13]
    wcs.wcs.crval = [359.99, 65]
    wcs.wcs.cdelt = [-0.8 / 3600, 1.3 / 3600]
    wcs.wcs.radesys = frame.upper()
    if frame == "fk5":
        wcs.wcs.equinox = 1950
    header = cast(fits.Header, wcs.to_header())
    header["BMAJ"] = 4 / 3600
    header["BMIN"] = 2 / 3600
    header["BPA"] = 23
    return header


@pytest.mark.parametrize("frame", ("icrs", "fk5"))
def test_background_beam_uses_native_frame_axes(frame: str) -> None:
    """Precession must rotate the beam and pixel basis together."""
    header = _header(frame)
    metadata = ImageMetadata(
        shape_yx=(25, 33),
        unit="Jy/beam",
        beam=RestoringBeam(4 / 3600, 2 / 3600, 23),
        celestial_wcs=CelestialWcs(
            fits_header=cast(str, header.tostring(sep="\n")),
            coordinate_frame=frame,
        ),
        reference_frequency_hz=150e6,
    )
    original = metadata.celestial_wcs.fits_header
    observed = public_api._beam_shape_pixels(metadata)
    pa = np.deg2rad(23)
    axes = np.array(((np.sin(pa), np.cos(pa)), (np.cos(pa), -np.sin(pa))))
    inverse = np.diag((-1 / 0.8, 1 / 1.3))
    expected = inverse @ axes @ np.diag((16, 4)) @ axes.T @ inverse.T
    angle = np.deg2rad(observed.position_angle_degrees)
    pixel_axes = np.array(
        ((np.cos(angle), -np.sin(angle)), (np.sin(angle), np.cos(angle)))
    )
    actual = (
        pixel_axes
        @ np.diag(
            (observed.major_fwhm_pixels**2, observed.minor_fwhm_pixels**2)
        )
        @ pixel_axes.T
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-6)
    assert metadata.celestial_wcs.fits_header == original
    if frame == "icrs":
        assert astrometry.compact_geometry_from_wcs(
            metadata.beam, WCS(header), (16, 12)
        ) == astrometry.compact_geometry_at_pixel(metadata, (16, 12))


@pytest.mark.parametrize("frame", ("icrs", "fk5"))
def test_source_aperture_positions_are_icrs(frame: str) -> None:
    """A signed source centroid uses the same frame as Gaussian rows."""
    header = _header(frame)
    image = np.zeros((25, 33))
    image[11:14, 15:18] = 5
    rows = products.build_hebog_segment_catalogue(
        image,
        np.zeros_like(image),
        np.ones_like(image, dtype=bool),
        (image > 0).astype(np.int32),
        header,
        beam_major_fwhm_pixels=4,
        beam_minor_fwhm_pixels=2,
    )
    expected = cast(Any, WCS(header).pixel_to_world(16, 12)).icrs
    observed = SkyCoord(
        rows[0].right_ascension_degrees,
        rows[0].declination_degrees,
        unit="deg",
        frame="icrs",
    )
    assert cast(float, observed.separation(expected).arcsec) < 1e-6
    if frame == "icrs":
        np.testing.assert_array_equal(
            (rows[0].right_ascension_degrees, rows[0].declination_degrees),
            cast(np.ndarray, WCS(header).all_pix2world([[16, 12]], 0))[0],
        )


@pytest.mark.parametrize("frame", ("icrs", "fk5"))
def test_core_and_truth_projection_transform_icrs_rows(frame: str) -> None:
    """A precessed row stays inside its true half-open pixel core."""
    header = _header(frame)
    expected = cast(Any, WCS(header).pixel_to_world(16.25, 12.75)).icrs
    row = CatalogueSource(
        identifier="source",
        right_ascension_degrees=expected.ra.deg,
        declination_degrees=expected.dec.deg,
        peak_flux_jy_per_beam=1,
        integrated_flux_jy=1,
    )
    assert _RUNNER["_core_catalogue"](
        (row,), header, ImageBounds(12, 13, 16, 17)
    ) == (row,)
    assert (
        _RUNNER["_core_catalogue"]((row,), header, ImageBounds(13, 14, 16, 17))
        == ()
    )
    projected = public_measurement_projection._rows(
        (row,), {"source": 1}, {"source"}, header
    )
    np.testing.assert_allclose(
        projected[0].centre_xy, (16.25, 12.75), atol=1e-6
    )


def test_native_beam_conversion_preserves_icrs_and_rejects_noncelestial() -> (
    None
):
    """The admitted ICRS path stays exact; invalid WCS is not relabelled."""
    beam = RestoringBeam(4 / 3600, 2 / 3600, 23)
    assert (
        astrometry.restoring_beam_in_icrs(beam, WCS(_header("icrs")), (16, 12))
        is beam
    )
    with pytest.raises(ValueError, match="celestial WCS"):
        astrometry.restoring_beam_in_icrs(beam, WCS(), (0, 0))
    galactic = WCS(naxis=2)
    galactic.wcs.ctype = ["GLON-TAN", "GLAT-TAN"]
    with pytest.raises(ValueError, match="ICRS or FK5"):
        astrometry.restoring_beam_in_icrs(beam, galactic, (0, 0))


@pytest.mark.parametrize("frame", ("icrs", "native", "unsupported"))
def test_notebook_plot_uses_each_catalogues_declared_frame(frame: str) -> None:
    """Hebog ICRS rows and native reference rows share the correct pixels."""
    path = (
        Path(__file__).parents[2]
        / "notebooks/campaign_source_finder_comparison.py"
    )
    tree = ast.parse(path.read_text())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_to_pixel_positions"
    )
    namespace: dict[str, Any] = {
        "np": np,
        "SkyCoord": SkyCoord,
        "WCS": WCS,
        "CatalogueSource": CatalogueSource,
    }
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]), str(path), "exec"
        ),
        namespace,
    )
    wcs = WCS(_header("fk5"))
    native = cast(Any, wcs.pixel_to_world(16.25, 12.75))
    sky = native.icrs if frame == "icrs" else native
    row = CatalogueSource(
        identifier="source",
        right_ascension_degrees=sky.ra.deg,
        declination_degrees=sky.dec.deg,
        peak_flux_jy_per_beam=1,
        integrated_flux_jy=1,
    )
    plotter = namespace["_to_pixel_positions"]
    if frame == "unsupported":
        with pytest.raises(ValueError, match="coordinate frame"):
            plotter(wcs, (row,), coordinate_frame=frame)
        return
    observed = plotter(wcs, (row,), coordinate_frame=frame)
    np.testing.assert_allclose(observed, ((16.25,), (12.75,)), atol=1e-6)
    assert plotter(wcs, (), coordinate_frame=frame) == ((), ())
