"""Tests for the beam-sampling study's layout, noise and summary helpers."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import itertools
import math
import runpy
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hebog import public_api
from hebog.science import configuration, continuum
from hebog.validation.datasets import generate_synthetic_image

_SCRIPT = (
    Path(__file__).parents[3]
    / "scripts"
    / "validation"
    / "measure_beam_sampling.py"
)
_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))


@pytest.fixture(scope="module")
def study() -> dict[str, Any]:
    """Load the script without invoking its command-line entry point."""
    return runpy.run_path(str(_SCRIPT))


def _layout(
    study: dict[str, Any], size: int, realization: int
) -> list[dict[str, float]]:
    layout: Callable[..., list[dict[str, float]]] = study["source_layout"]
    return layout(size, 22.0, realization=realization, seed=7)


@pytest.mark.parametrize(("size", "count"), [(256, 1), (512, 4), (1000, 25)])
def test_layout_keeps_sources_isolated_and_away_from_edges(
    study: dict[str, Any], size: int, count: int
) -> None:
    """At the widest beam, sources sit eight beams apart and four in."""
    sources = _layout(study, size, realization=0)

    assert len(sources) == count
    for source in sources:
        for axis in ("x_pixel", "y_pixel"):
            assert 104.0 <= source[axis] <= size - 1 - 104.0
        assert source["major_sigma_pixels"] == pytest.approx(
            22.0 / _FWHM_PER_SIGMA
        )
        assert source["minor_sigma_pixels"] == source["major_sigma_pixels"]
    for first, second in itertools.combinations(sources, 2):
        separation = math.hypot(
            first["x_pixel"] - second["x_pixel"],
            first["y_pixel"] - second["y_pixel"],
        )
        assert separation >= 176.0


@pytest.mark.parametrize(("size", "per_snr"), [(256, 1), (512, 4)])
def test_five_realizations_cover_every_snr_equally(
    study: dict[str, Any], size: int, per_snr: int
) -> None:
    """Shifting the SNR cycle fills every stratum on a small image too."""
    peaks = Counter(
        round(source["peak_flux_jy_per_beam"] / 1e-4, 6)
        for realization in range(5)
        for source in _layout(study, size, realization)
    )

    assert peaks == dict.fromkeys((5.0, 10.0, 30.0, 100.0, 300.0), per_snr)


def test_seed_is_shared_by_analyses_of_one_image(
    study: dict[str, Any],
) -> None:
    """Profiles and mesh variants see one image; realizations differ."""
    run: Callable[..., Any] = study["Run"]
    continuum_run = run(1000, 20.0, "correlated", 1, "continuum")
    scaled_compact = run(1000, 20.0, "correlated", 1, "compact", 8.0)

    assert continuum_run.seed == scaled_compact.seed
    assert (
        continuum_run.seed != run(1000, 20.0, "correlated", 2, "compact").seed
    )
    assert continuum_run.seed != run(1000, 20.0, "white", 1, "compact").seed
    assert continuum_run.key == "default/continuum/correlated/1000/20/1"
    assert scaled_compact.key == (
        "fine-scaled-above-8/compact/correlated/1000/20/1"
    )


@pytest.mark.parametrize(
    ("noise", "lower", "upper"),
    [("white", -0.02, 0.02), ("correlated", 0.9, 1.0)],
)
def test_noise_is_white_or_correlated_at_the_beam(
    study: dict[str, Any], noise: str, lower: float, upper: float
) -> None:
    """White noise is pixel-independent; correlated noise follows the beam."""
    run: Callable[..., Any] = study["Run"]
    dataset = study["dataset_record"](run(256, 8.0, noise, 0, "continuum"))
    image = generate_synthetic_image(
        dataset.recipe.model_copy(update={"sources": ()})
    )

    neighbour_correlation = np.corrcoef(
        image[:, :-1].ravel(), image[:, 1:].ravel()
    )[0, 1]
    assert lower <= neighbour_correlation <= upper
    assert float(np.std(image)) == pytest.approx(1e-4, rel=0.1)


def test_scaled_fine_mesh_scales_geometry_and_restores_it(
    study: dict[str, Any],
) -> None:
    """The diagnostic scales the fine mesh only, and only inside the block."""
    installed = configuration.source_finder_configs()[0].background_rms

    with study["scaled_fine_mesh"](2.0):
        scaled = configuration.source_finder_configs()[0].background_rms
        assert continuum.source_finder_configs is (
            configuration.source_finder_configs
        )

    assert installed.adaptive is not None
    assert scaled.adaptive is not None
    assert scaled.adaptive.grid.window_shape_yx == (70, 70)
    assert scaled.adaptive.grid.step_yx == (14, 14)
    assert scaled.adaptive.influence_radius_pixels == 150.0
    assert scaled.adaptive.transition_width_pixels == 40.0
    assert scaled.coarse == installed.coarse
    assert configuration.source_finder_configs()[0].background_rms == (
        installed
    )
    assert continuum.source_finder_configs()[0].background_rms == installed


def _beam_limit() -> float:
    """Return the finder's current beam limit in pixels."""
    return public_api._MAXIMUM_BEAM_FWHM_PIXELS


def test_lifted_beam_limit_replaces_the_limit_only_inside_the_block(
    study: dict[str, Any],
) -> None:
    """The measurement-only override is scoped, and None leaves the limit."""
    installed = _beam_limit()

    with study["lifted_beam_limit"](None):
        assert _beam_limit() == installed
    with study["lifted_beam_limit"](installed + 12.0):
        assert _beam_limit() == installed + 12.0

    assert _beam_limit() == installed


def test_a_run_beyond_the_beam_limit_is_refused_unless_the_limit_is_lifted(
    study: dict[str, Any], tmp_path: Path
) -> None:
    """Wide beams reach the stages only through the explicit override."""
    run: Callable[..., Any] = study["Run"]
    measure: Callable[..., dict[str, Any]] = study["measure"]
    installed = _beam_limit()
    beam = installed + 2.0

    refused = measure(run(256, beam, "correlated", 0, "compact"), tmp_path)
    lifted = measure(
        run(
            256,
            beam,
            "correlated",
            0,
            "compact",
            lifted_beam_limit_pixels=beam,
        ),
        tmp_path,
    )

    assert refused["status"] == "refused"
    assert f"at most {installed:g} pixels FWHM" in refused["error"]
    assert lifted["status"] == "success"
    assert _beam_limit() == installed


def _record(
    key: str, matched: list[bool], *, unmatched: int = 0
) -> dict[str, Any]:
    return {
        "key": key,
        "run": {"size": 1000, "beam_fwhm_pixels": 10.0},
        "status": "success",
        "unmatched_published_sources": unmatched,
        "median_rms_ratio": 1.0,
        "sources": [
            {
                "snr": snr,
                "matched": found,
                "rms_ratio": 1.0,
                **({"flux_ratio": 1.0, "offset_beams": 0.1} if found else {}),
            }
            for snr, found in zip(
                (5.0, 10.0, 30.0, 100.0, 300.0), matched, strict=True
            )
        ],
    }


def test_summary_counts_recovery_false_detections_and_refusals(
    study: dict[str, Any],
) -> None:
    """A cell pools its images; refusals count as images, not as sources."""
    cell = "default/continuum/correlated/1000/10"
    records = [
        _record(f"{cell}/0", [False, True, True, True, True], unmatched=2),
        _record(f"{cell}/1", [True, False, True, True, True]),
        {
            "key": f"{cell}/2",
            "run": {"size": 1000, "beam_fwhm_pixels": 10.0},
            "status": "refused",
        },
    ]

    summary = study["summarise"](records)[cell]

    bright = summary["snr_at_least_10"]
    assert (bright["recovered"], bright["sources"]) == (7, 8)
    assert bright["wilson_95"][0] < 7 / 8 < bright["wilson_95"][1]
    assert summary["by_snr"]["5"]["recovered"] == 1
    assert summary["by_snr"]["10"]["median_flux_ratio"] == 1.0
    assert (summary["images"], summary["refused"]) == (3, 1)
    assert summary["false_per_image"] == 1.0
    beams_per_image = 1000**2 / (math.pi / (4 * math.log(2)) * 10.0**2)
    assert summary["false_per_thousand_beams"] == pytest.approx(
        1000 * 2 / (2 * beams_per_image)
    )
