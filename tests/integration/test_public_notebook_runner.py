# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportPrivateUsage=false
"""Synthetic end-to-end smoke for the notebook comparison Hebog runner."""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from conftest import PublishBackgroundRms

from hebog import public_api
from hebog.algorithms import fitting as fitting_algorithm
from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[2]
_RUNNER = runpy.run_path(
    str(_ROOT / "scripts/benchmark/run_notebook_hebog.py")
)


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


def _geometry_matrix_image() -> np.ndarray[Any, np.dtype[np.float64]]:
    """Combine edge, multi-peak, elongated, invalid, and sparse geometry."""
    height, width = 96, 128
    y_pixels, x_pixels = np.mgrid[:height, :width]
    image = np.random.default_rng(31).normal(0.0, 0.12, (height, width))

    def gaussian(
        amplitude: float,
        y_center: float,
        x_center: float,
        y_sigma: float = 2.0,
        x_sigma: float = 2.0,
    ) -> np.ndarray[Any, np.dtype[np.float64]]:
        return amplitude * np.exp(
            -0.5
            * (
                ((y_pixels - y_center) / y_sigma) ** 2
                + ((x_pixels - x_center) / x_sigma) ** 2
            )
        )

    image += gaussian(4.0, 1.5, 2.0)
    for amplitude, x_center in ((3.8, 45.0), (3.5, 51.0), (3.2, 57.0)):
        image += gaussian(amplitude, 46.0, x_center)
    for y_center, x_center in ((72.0, 92.0), (75.0, 97.0), (78.0, 102.0)):
        image += gaussian(3.0, y_center, x_center, 3.0, 5.0)
    image += gaussian(2.8, 88.0, 15.0)
    image[18:23, 104:112] = np.nan
    return np.asarray(image, dtype=np.float64)


@pytest.mark.integration
@pytest.mark.parametrize("frame", ("icrs", "fk5", "implicit-fk5"))
def test_exact_notebook_runner_completes_geometry_matrix(
    tmp_path: Path,
    frame: str,
) -> None:
    """The exact notebook path publishes aligned products for edge cases."""
    input_path = tmp_path / "input.fits"
    output = tmp_path / "result"
    image = _geometry_matrix_image()
    header = _header(image.shape)
    if frame != "icrs":
        header["CTYPE1"] = "RA---SIN"
        header["CTYPE2"] = "DEC--SIN"
        if frame == "implicit-fk5":
            del header["RADESYS"]
            header["EPOCH"] = 2000.0
        else:
            header["RADESYS"] = "FK5"
            header["EQUINOX"] = 1950.0
    fits.PrimaryHDU(image, header).writeto(input_path)

    result = cast(
        dict[str, object],
        _RUNNER["run_notebook_hebog"](
            input_path=input_path,
            output=output,
            case_id="synthetic-geometry-matrix",
            core=None,
        ),
    )

    publication = np.asarray(
        fits.getdata(output / "segment_labels.fits")
    ).squeeze()
    measurement = np.asarray(
        fits.getdata(output / "component_labels.fits")
    ).squeeze()
    terminal = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert terminal == result
    assert np.any(publication > 0)
    assert not np.any((publication > 0) & (measurement <= 0))
    assert terminal["source_count"] >= 1
    assert terminal["component_count"] >= 1
    assert terminal["measurement_dispositions"]
    components = {
        row["object_id"]: row
        for row in terminal["measurement_dispositions"]
        if row["object_kind"] == "component"
    }
    sources = [
        row
        for row in terminal["measurement_dispositions"]
        if row["object_kind"] == "source"
    ]
    assert {
        member for row in sources for member in row["member_component_ids"]
    } == components.keys()
    # Every component in this pixel-independent-noise matrix is measurable;
    # a beam-correlated point estimator once rejected most of them.
    assert all(row["status"] == "measured" for row in components.values())
    assert all(
        row["fit_diagnostics"]["point_estimator"] == "diagonal-weighted"
        for row in components.values()
    )
    assert (
        sum(row["catalogue_row_published"] for row in components.values())
        == terminal["component_count"]
    )
    assert (
        sum(
            row["catalogue_row_published"]
            for row in terminal["measurement_dispositions"]
        )
        == terminal["source_count"] + terminal["component_count"]
    )
    assert terminal["scientific_composition"] == public_api._COMPOSITION_NAME
    assert terminal["scientific_composition_sha256"] == (
        public_api._scientific_composition_sha256()
    )
    assert terminal["configuration_sha256"] == canonical_sha256(
        asdict(_RUNNER["_CONFIG"])
    )
    assert terminal["catalogue_semantics"]["coordinate_frame"] == "icrs"
    assert fits.getheader(output / "segment_mask.fits").get(
        "RADESYS"
    ) == header.get("RADESYS")


@pytest.mark.integration
@pytest.mark.parametrize("value", (0.0, np.nan))
def test_exact_notebook_runner_publishes_empty_and_all_nan(
    tmp_path: Path,
    value: float,
) -> None:
    """A valid source-free image is not a failed batch."""
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(np.full((32, 48), value), _header((32, 48))).writeto(path)
    result = _RUNNER["run_notebook_hebog"](
        input_path=path,
        output=tmp_path / "result",
        case_id="empty",
        core=None,
    )
    assert result["source_count"] == result["component_count"] == 0
    assert result["measurement_dispositions"] == []
    mask = cast(
        np.ndarray, fits.getdata(tmp_path / "result/segment_mask.fits")
    )
    assert not np.any(mask)


@pytest.mark.integration
@pytest.mark.parametrize("rotation", (0.0, 37.0, 90.0))
@pytest.mark.parametrize("frame", ("icrs", "fk5"))
def test_notebook_native_measurements_preserve_rotated_unequal_pixel_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rotation: float,
    frame: str,
    published_background_rms: PublishBackgroundRms,
) -> None:
    """Native flux, sky shape and errors survive the complete FITS boundary."""
    header = _header((96, 128))
    if frame == "fk5":
        header["RADESYS"] = "FK5"
        header["EQUINOX"] = 1950.0
        header["CTYPE1"] = "RA---SIN"
        header["CTYPE2"] = "DEC--SIN"
    header["BMAJ"] = 4 / 3600
    header["BMIN"] = 2 / 3600
    header["BPA"] = 23.0
    angle = np.deg2rad(rotation)
    transform = np.array(
        ((np.cos(angle), -np.sin(angle)), (np.sin(angle), np.cos(angle)))
    ) @ np.diag((-0.8, 1.3))
    del header["CDELT1"]
    del header["CDELT2"]
    for row in range(2):
        for column in range(2):
            header[f"CD{row + 1}_{column + 1}"] = transform[row, column] / 3600
    pa = np.deg2rad(23)
    axes = np.array(((np.sin(pa), np.cos(pa)), (np.cos(pa), -np.sin(pa))))
    sky_covariance = (
        axes @ np.diag(np.array((7.0, 4.0)) ** 2 / (8 * np.log(2))) @ axes.T
    )
    inverse = np.linalg.inv(transform)
    pixel_covariance = inverse @ sky_covariance @ inverse.T
    yy, xx = np.mgrid[:96, :128]
    centre = np.array((55.25, 35.75))
    offsets = np.stack((xx - centre[0], yy - centre[1]), axis=-1)
    image = 20 * np.exp(
        -0.5
        * np.einsum(
            "...i,ij,...j->...",
            offsets,
            np.linalg.inv(pixel_covariance),
            offsets,
        )
    )

    def analytic_background(
        *args: object,
        generation_id: str,
        **_kwargs: object,
    ):
        background = np.zeros_like(image)
        rms = np.ones_like(image)
        return (
            published_background_rms(
                cast(Path, args[4]), background, rms, generation_id
            ),
            background,
            rms,
        )

    monkeypatch.setattr(
        public_api, "_estimate_background_rms", analytic_background
    )
    path = tmp_path / "rotated.fits"
    fits.PrimaryHDU(image, header).writeto(path)
    result = _RUNNER["run_notebook_hebog"](
        input_path=path,
        output=tmp_path / "result",
        case_id="rotated",
        core=None,
    )
    assert result["source_count"] == result["component_count"] == 1
    component = result["all_measured_component_records"][0]
    assert component["integrated_flux_jy"] == pytest.approx(70, rel=0.005)
    shape = component["fitted_shape"]
    assert shape["major_fwhm_degrees"] * 3600 == pytest.approx(7, rel=0.005)
    assert shape["minor_fwhm_degrees"] * 3600 == pytest.approx(4, rel=0.005)
    native_center = cast(Any, WCS(header).celestial.pixel_to_world(*centre))
    direction = native_center.directional_offset_by(23 * u.deg, 1 * u.arcsec)
    expected_pa = native_center.icrs.position_angle(direction.icrs).deg % 180
    assert shape["position_angle_degrees"] == pytest.approx(
        expected_pa, abs=0.01
    )
    for key in (
        "major_fwhm_error_degrees",
        "minor_fwhm_error_degrees",
        "position_angle_error_degrees",
    ):
        assert np.isfinite(shape[key]) and shape[key] > 0
    assert component["deconvolution_status"] == "resolved"
    deconvolved = component["deconvolved_shape"]
    assert deconvolved["major_fwhm_degrees"] * 3600 == pytest.approx(
        np.sqrt(33), rel=0.005
    )
    assert deconvolved["minor_fwhm_degrees"] * 3600 == pytest.approx(
        np.sqrt(12), rel=0.005
    )
    # The scalar field is reserved for a major-axis-only resolution result.
    assert component["deconvolved_major_fwhm_degrees"] is None
    observed = cast(
        tuple[float, float],
        WCS(header).celestial.world_to_pixel(
            SkyCoord(
                component["right_ascension_degrees"],
                component["declination_degrees"],
                unit="deg",
                frame="icrs",
            )
        ),
    )
    np.testing.assert_allclose(observed, centre, atol=0.001)


@pytest.mark.integration
@pytest.mark.parametrize("frame", ("icrs", "fk5"))
@pytest.mark.parametrize("failure_mode", ("first", "all"))
def test_notebook_retains_numerical_fit_failures_without_aborting_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frame: str,
    failure_mode: str,
) -> None:
    """Unmeasured Gaussians remain visible without discarding other islands."""
    image = _geometry_matrix_image()
    header = _header(image.shape)
    if frame == "fk5":
        header["RADESYS"] = "FK5"
        header["EQUINOX"] = 1950.0
        header["CTYPE1"] = "RA---SIN"
        header["CTYPE2"] = "DEC--SIN"
    input_path = tmp_path / "input.fits"
    output = tmp_path / "result"
    fits.PrimaryHDU(image, header).writeto(input_path)
    original = cast(Callable[..., Any], fitting_algorithm.least_squares)
    calls = 0

    def solver(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if failure_mode == "all" or calls == 1:
            raise np.linalg.LinAlgError("SVD did not converge for slice = 0.")
        return original(*args, **kwargs)

    monkeypatch.setattr(fitting_algorithm, "least_squares", solver)
    with pytest.warns(
        RuntimeWarning, match="Gaussian components unavailable"
    ) as notices:
        _RUNNER["run_notebook_hebog"](
            input_path=input_path,
            output=output,
            case_id="synthetic-numerical-failure",
            core=None,
        )
    assert len(notices) == 1
    terminal = json.loads((output / "result.json").read_text())
    assert terminal["status"] == "success"  # Publication, not science parity.
    components = [
        row
        for row in terminal["measurement_dispositions"]
        if row["object_kind"] == "component"
    ]
    missing = [row for row in components if row["status"] == "unavailable"]
    assert missing
    assert {row["reason"] for row in missing} == {"fit-linear-algebra-failure"}
    assert all(not row["catalogue_row_published"] for row in missing)
    assert all(row["estimator"] is None for row in missing)
    published = [row for row in components if row["catalogue_row_published"]]
    assert terminal["component_count"] == len(published)
    assert bool(published) == (failure_mode == "first")
    assert calls > 1
    assert np.any(cast(np.ndarray, fits.getdata(output / "segment_mask.fits")))
