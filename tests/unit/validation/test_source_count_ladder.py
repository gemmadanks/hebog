# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
"""Noise-raised rungs of the source-count ladder."""

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from scipy.ndimage import gaussian_filter

from hebog.validation.execution_profile import load_profile_configuration
from hebog.validation.quick_check import ImageCase
from hebog.validation.source_count_ladder import (
    load_ladder_noise_configuration,
    raise_noise,
    robust_rms,
)

_ROOT = Path(__file__).parents[3]
_LADDER = _ROOT / "config/benchmarks/source-count-ladder.json"
_NOISE = _ROOT / "config/benchmarks/source-count-ladder-noise.json"
_BEAM_FWHM_PIXELS = 4.0


def _beam_noise(shape: tuple[int, ...], seed: int) -> npt.NDArray[np.float32]:
    """Return unit-RMS noise correlated over a 4-pixel beam."""
    white = np.random.default_rng(seed).standard_normal(shape)
    smoothed = gaussian_filter(white, sigma=_BEAM_FWHM_PIXELS / 2.3548)
    return (smoothed / smoothed.std()).astype(np.float32)


@pytest.mark.parametrize("factor", (1.5, 2.0, 4.0))
def test_raising_the_noise_multiplies_the_robust_rms(factor: float) -> None:
    """A noise-only image comes back with its RMS raised by the factor."""
    image = 3.0e-5 * _beam_noise((512, 512), seed=1)

    raised = raise_noise(
        image, factor=factor, beam_fwhm_pixels=_BEAM_FWHM_PIXELS, seed=7
    )

    assert robust_rms(raised) == pytest.approx(
        factor * robust_rms(image), rel=0.05
    )


def test_blank_pixels_stay_blank_and_leading_axes_are_kept() -> None:
    """A FITS plane with Stokes and frequency axes keeps its shape."""
    image = _beam_noise((1, 1, 128, 160), seed=2)
    image[..., :10, :] = np.nan

    raised = raise_noise(
        image, factor=2.0, beam_fwhm_pixels=_BEAM_FWHM_PIXELS, seed=7
    )

    assert raised.shape == image.shape
    assert raised.dtype == image.dtype
    assert np.array_equal(np.isnan(raised), np.isnan(image))


def test_the_seed_decides_the_added_noise() -> None:
    """One seed always adds the same noise, so a rung can be rebuilt."""
    image = _beam_noise((96, 96), seed=3)

    def raised(seed: int) -> npt.NDArray[np.float32]:
        return raise_noise(
            image, factor=3.0, beam_fwhm_pixels=_BEAM_FWHM_PIXELS, seed=seed
        )

    assert np.array_equal(raised(11), raised(11))
    assert not np.array_equal(raised(11), raised(12))


@pytest.mark.parametrize(
    ("factor", "fill", "message"),
    ((1.0, 0.0, "factor"), (2.0, np.nan, "finite")),
)
def test_raising_the_noise_refuses_what_it_cannot_raise(
    factor: float, fill: float, message: str
) -> None:
    """A factor of one adds nothing, and a blank image has no noise."""
    image = np.full((32, 32), fill, dtype=np.float32)

    with pytest.raises(ValueError, match=message):
        raise_noise(
            image, factor=factor, beam_fwhm_pixels=_BEAM_FWHM_PIXELS, seed=7
        )


def test_every_noise_rung_is_a_ladder_case_of_the_same_size() -> None:
    """The builder writes each rung where the ladder's case reads it."""
    noise = load_ladder_noise_configuration(_NOISE)
    cases = {
        item.case.case_id: item.case
        for item in load_profile_configuration(_LADDER).cases
    }

    base = cases[noise.base_case]
    assert isinstance(base, ImageCase) and base.window is not None
    assert base.window.size == 5000
    for rung in noise.rungs:
        case = cases[rung.case_id]
        assert isinstance(case, ImageCase)
        assert case.window is None
        assert case.image == (
            f"benchmark-results/source-count-ladder/{rung.case_id}.fits"
        )
    assert sorted(rung.noise_factor for rung in noise.rungs) == [
        1.5,
        2.0,
        3.0,
        4.0,
    ]


def _write_ladder(directory: Path) -> tuple[Path, Path]:
    """Write a small base image and a ladder of two rungs over it."""
    header = fits.Header()
    header["CTYPE1"], header["CTYPE2"] = "RA---SIN", "DEC--SIN"
    header["CRPIX1"] = header["CRPIX2"] = 65.0
    header["CRVAL1"], header["CRVAL2"] = 242.75, 55.0
    header["CDELT1"], header["CDELT2"] = -1.5 / 3600, 1.5 / 3600
    header["BMAJ"] = header["BMIN"] = 6.0 / 3600
    header["BPA"] = 0.0
    header["BUNIT"] = "Jy/beam"
    header["RESTFRQ"] = 144.0e6
    base = directory / "base.fits"
    fits.PrimaryHDU(
        data=3.0e-5 * _beam_noise((1, 1, 128, 128), seed=5), header=header
    ).writeto(base)
    rungs = {"small-noise-2x": 2.0, "small-noise-3x": 3.0}
    cases = [
        {
            "group": "real",
            "case": {
                "case_id": "small-base",
                "kind": "image",
                "image": str(base),
                "window": {"size": 96, "x_start": 16, "y_start": 16},
            },
        },
        *(
            {
                "group": "real",
                "case": {
                    "case_id": case_id,
                    "kind": "image",
                    "image": str(directory / "ladder" / f"{case_id}.fits"),
                },
            }
            for case_id in rungs
        ),
    ]
    ladder = directory / "ladder.json"
    ladder.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_manifest": "config/datasets/quick-science-check.json",
                "hebog": {
                    "detection_threshold_sigma": 5.0,
                    "island_threshold_sigma": 3.0,
                    "minimum_island_pixels": 7,
                    "profile": "continuum",
                },
                "cases": cases,
            }
        )
    )
    noise = directory / "noise.json"
    noise.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "base_case": "small-base",
                "seed": 9,
                "rungs": [
                    {"case_id": case_id, "noise_factor": factor}
                    for case_id, factor in rungs.items()
                ],
            }
        )
    )
    return ladder, noise


def test_the_builder_writes_every_rung_once_with_its_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rungs land where their cases read them, and a rerun keeps them."""
    ladder, noise = _write_ladder(tmp_path)
    builder = runpy.run_path(
        str(_ROOT / "scripts/benchmark/build_source_count_ladder.py")
    )
    main = cast(Callable[[], int], builder["main"])
    arguments = [
        "build_source_count_ladder.py",
        "--ladder",
        str(ladder),
        "--noise",
        str(noise),
        "--inputs-root",
        str(tmp_path / "inputs"),
    ]
    monkeypatch.setattr(sys, "argv", arguments)

    assert main() == 0
    written = {
        path.name: path.stat().st_mtime_ns
        for path in (tmp_path / "ladder").glob("*.fits")
    }
    assert main() == 0

    manifest = cast(
        dict[str, Any],
        json.loads((tmp_path / "ladder/manifest.json").read_text("utf-8")),
    )
    assert written == {
        path.name: path.stat().st_mtime_ns
        for path in (tmp_path / "ladder").glob("*.fits")
    }
    assert manifest["seed"] == 9
    assert manifest["beam_fwhm_pixels"] == pytest.approx(4.0)
    for rung in manifest["rungs"]:
        with fits.open(
            tmp_path / "ladder" / f"{rung['case_id']}.fits"
        ) as hdus:
            data = np.asarray(cast(Any, hdus[0]).data)
        assert data.shape == (1, 1, 96, 96)
        assert rung["robust_rms"] == pytest.approx(
            rung["noise_factor"] * manifest["base_robust_rms"], rel=0.1
        )
