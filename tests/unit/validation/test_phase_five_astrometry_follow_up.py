"""Tests for the Phase 5 detected-segment position follow-up."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hebog.validation.contracts import (
    load_phase_five_astrometry_follow_up_review,
    load_phase_five_corrective_a_review,
)
from hebog.validation.datasets import load_dataset_manifest
from hebog.validation.phase_five_astrometry_follow_up import (
    ExtendedPositionObservation,
    cluster_bootstrap_absolute_mean,
    compile_astrometry_follow_up_development,
    evaluate_astrometry_follow_up_image,
)

_ROOT = Path(__file__).parents[3]
_DEVELOPMENT = (
    _ROOT / "config/datasets/phase-5-astrometry-follow-up-development.json"
)
_PROTOCOL = _ROOT / "config/contracts/phase-5-astrometry-follow-up-review.json"
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_ASTRONOMICAL_STRATA = tuple(
    stratum
    for stratum in load_phase_five_astrometry_follow_up_review(
        _PROTOCOL
    ).governed_strata
    if stratum != "morphology-artifact"
)


def _observation(
    *,
    seed: int,
    group: str,
    offset_xy: tuple[float, float],
    available: bool = True,
    governed_strata: tuple[str, ...] = _ASTRONOMICAL_STRATA,
) -> ExtendedPositionObservation:
    """Build one minimal compiler row in beam coordinates."""
    radial = (offset_xy[0] ** 2 + offset_xy[1] ** 2) ** 0.5
    return ExtendedPositionObservation(
        dataset_identifier="follow-up-development",
        seed=seed,
        group_identifier=group,
        morphology="shell" if group == "shell" else "curved-filament",
        scale_orders=(2, 3),
        available=available,
        centroid_xy=(10.0, 11.0) if available else None,
        peak_position_xy=(10, 11) if available else None,
        reference_position_xy=(10.0, 11.0),
        offset_xy_beams=offset_xy if available else None,
        radial_error_beams=radial if available else None,
        former_target_error_beams=radial + 0.05 if available else None,
        unavailable_reason=None if available else "nonpositive-segment-flux",
        governed_strata=governed_strata,
    )


def test_absolute_mean_bootstrap_resamples_whole_images() -> None:
    """Signed-axis inference retains every group in a sampled image."""
    estimate, upper = cluster_bootstrap_absolute_mean(
        values=(0.0, 0.0, 0.2, 0.2),
        image_keys=("a", "a", "b", "b"),
        resamples=10_000,
        seed=20260809,
        confidence_level=0.95,
    )

    assert estimate == pytest.approx(0.1)
    assert upper == pytest.approx(0.2)


def test_follow_up_compiler_requires_all_bias_and_repeatability_gates() -> (
    None
):
    """One transparent candidate passes only by conjunction over strata."""
    protocol = load_phase_five_astrometry_follow_up_review(_PROTOCOL)
    observations = tuple(
        _observation(seed=seed, group=group, offset_xy=offset)
        for seed, offset in ((1, (0.02, -0.01)), (2, (-0.02, 0.01)))
        for group in ("curve", "shell")
    )

    summary = compile_astrometry_follow_up_development(observations, protocol)

    assert summary.image_count == 2
    assert summary.group_count == 4
    assert summary.endpoints
    assert all(item.passed for item in summary.endpoints)
    assert {item.metric for item in summary.endpoints} == {
        "availability",
        "absolute-mean-offset-x",
        "absolute-mean-offset-y",
        "radial-percentile-95",
    }
    assert summary.eligible_for_human_review is True
    assert summary.confirmation_execution_authorized is False
    assert summary.diagnostics

    unavailable = replace(observations[0], available=False)
    rejected = compile_astrometry_follow_up_development(
        (unavailable, *observations[1:]), protocol
    )
    assert any(
        item.metric == "availability" and not item.passed
        for item in rejected.endpoints
    )
    assert rejected.eligible_for_human_review is False


def test_follow_up_compiler_rejects_empty_or_catastrophic_rows() -> None:
    """A tail failure cannot be compensated by small unbiased positions."""
    protocol = load_phase_five_astrometry_follow_up_review(_PROTOCOL)
    observations = (
        _observation(seed=1, group="curve", offset_xy=(0.0, 0.0)),
        _observation(seed=2, group="curve", offset_xy=(0.8, 0.0)),
    )

    summary = compile_astrometry_follow_up_development(observations, protocol)

    assert any(
        item.metric == "radial-percentile-95" and not item.passed
        for item in summary.endpoints
    )
    assert summary.eligible_for_human_review is False
    with pytest.raises(ValueError, match="must not be empty"):
        compile_astrometry_follow_up_development((), protocol)


def test_follow_up_compiler_rejects_a_missing_governed_stratum() -> None:
    """A wholly absent astronomical stratum cannot disappear from review."""
    protocol = load_phase_five_astrometry_follow_up_review(_PROTOCOL)
    observation = _observation(
        seed=1,
        group="curve",
        offset_xy=(0.0, 0.0),
        governed_strata=("morphology-curved-filament",),
    )

    with pytest.raises(ValueError, match="missing governed strata"):
        compile_astrometry_follow_up_development((observation,), protocol)


def test_fresh_follow_up_image_uses_segment_centroid_and_separate_peak() -> (
    None
):
    """One real review image preserves B3 detection and explicit products."""
    dataset = load_dataset_manifest(_DEVELOPMENT).datasets[0]
    base_review = load_phase_five_corrective_a_review(_BASE_REVIEW)

    observations = evaluate_astrometry_follow_up_image(
        dataset,
        recipe_index=0,
        base_review=base_review,
    )

    assert {item.morphology for item in observations} >= {
        "curved-filament",
        "diffuse",
        "filament",
        "mixed-compact-extended",
        "shell",
    }
    assert all(item.available for item in observations)
    assert all(item.centroid_xy is not None for item in observations)
    assert all(item.peak_position_xy is not None for item in observations)
    assert all(item.offset_xy_beams is not None for item in observations)
    assert all(item.radial_error_beams is not None for item in observations)
    assert all(
        item.former_target_error_beams is not None for item in observations
    )
