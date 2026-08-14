"""Prospective Phase 5 post-failure power-planning tests."""

from __future__ import annotations

from copy import deepcopy
from math import inf

import pytest

import hebog.validation.phase_five_post_failure_power as power_module
from hebog.validation.phase_five_post_failure_power import (
    build_paired_power_priors,
    conservative_familywise_power,
    minimum_realization_count,
    prospective_joint_power,
)


def _closed_analysis() -> dict[str, object]:
    return {
        "continuum_endpoints": [
            {
                "endpoint_id": "continuum--duplicate-fraction--overall",
                "metric_family": "duplicate-fraction",
                "comparisons": [
                    {
                        "reference_id": "released-pybdsf",
                        "status": "success",
                        "positive_regression": -0.08,
                        "observed_paired_standard_deviation": 0.20,
                    },
                    {
                        "reference_id": "pinned-pybdsf-master",
                        "status": "success",
                        "positive_regression": 0.004,
                        "observed_paired_standard_deviation": 0.01,
                    },
                ],
            },
            {
                "endpoint_id": "continuum--position-median--overall",
                "metric_family": "position-median",
                "comparisons": [],
            },
        ]
    }


def _planning_assumptions() -> tuple[dict[str, object], ...]:
    return (
        {
            "metric_family": "duplicate-fraction",
            "planning_paired_standard_deviation": 0.03,
            "practical_regression_margin": 0.01,
        },
        {
            "metric_family": "position-median",
            "planning_paired_standard_deviation": 0.15,
            "practical_regression_margin": 0.05,
        },
    )


def test_build_priors_uses_endpoint_variance_and_shrinks_prior_advantage() -> (
    None
):
    """Closed evidence supplies guarded, endpoint-specific planning priors."""
    priors = build_paired_power_priors(
        _closed_analysis(),
        _planning_assumptions(),
        variance_inflation=1.25,
        advantage_retention=0.5,
    )

    assert len(priors) == 2
    released, master = priors
    assert released.planning_paired_standard_deviation == pytest.approx(0.25)
    assert released.planning_expected_regression == pytest.approx(-0.04)
    assert master.planning_paired_standard_deviation == pytest.approx(0.03)
    assert master.planning_expected_regression == 0.0


def test_build_priors_fails_closed_on_unavailable_comparison() -> None:
    """A planning audit cannot silently omit a binding comparison."""
    analysis = _closed_analysis()
    endpoint = analysis["continuum_endpoints"][0]  # type: ignore[index]
    endpoint["comparisons"][0]["status"] = "unavailable"  # type: ignore[index]

    with pytest.raises(
        ValueError,
        match="closed paired comparison is unavailable",
    ):
        build_paired_power_priors(
            analysis,
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


@pytest.mark.parametrize(
    "analysis",
    [
        {"continuum_endpoints": None},
        {"continuum_endpoints": ["not-an-endpoint"]},
    ],
)
def test_build_priors_rejects_malformed_evidence(
    analysis: dict[str, object],
) -> None:
    """Malformed closed evidence cannot become a planning population."""
    with pytest.raises(ValueError):
        build_paired_power_priors(
            analysis,
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


@pytest.mark.parametrize(
    "assumptions",
    [
        ({"practical_regression_margin": 0.01},),
        (
            {
                "metric_family": "duplicate-fraction",
                "planning_paired_standard_deviation": 0.03,
                "practical_regression_margin": 0.01,
            },
            {
                "metric_family": "duplicate-fraction",
                "planning_paired_standard_deviation": 0.04,
                "practical_regression_margin": 0.01,
            },
        ),
        (
            {
                "metric_family": "duplicate-fraction",
                "planning_paired_standard_deviation": "small",
                "practical_regression_margin": 0.01,
            },
        ),
        (
            {
                "metric_family": "duplicate-fraction",
                "planning_paired_standard_deviation": inf,
                "practical_regression_margin": 0.01,
            },
        ),
        (
            {
                "metric_family": "duplicate-fraction",
                "planning_paired_standard_deviation": 0.03,
                "practical_regression_margin": 0.0,
            },
        ),
    ],
)
def test_build_priors_rejects_invalid_family_policies(
    assumptions: tuple[dict[str, object], ...],
) -> None:
    """Every paired family needs one finite positive floor and margin."""
    with pytest.raises(ValueError):
        build_paired_power_priors(
            _closed_analysis(),
            assumptions,
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint_id", None),
        ("metric_family", None),
    ],
)
def test_build_priors_requires_endpoint_identity(
    field: str,
    value: object,
) -> None:
    """Planning priors remain attributable to one exact endpoint."""
    analysis = deepcopy(_closed_analysis())
    endpoint = analysis["continuum_endpoints"][0]  # type: ignore[index]
    endpoint[field] = value  # type: ignore[index]

    with pytest.raises(ValueError):
        build_paired_power_priors(
            analysis,
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


def test_build_priors_rejects_missing_policy_and_duplicate_comparison() -> (
    None
):
    """No binding comparison can be ungoverned or counted twice."""
    with pytest.raises(ValueError, match="lacks a family policy"):
        build_paired_power_priors(
            _closed_analysis(),
            _planning_assumptions()[1:],
            variance_inflation=1.25,
            advantage_retention=0.5,
        )

    analysis = deepcopy(_closed_analysis())
    endpoint = analysis["continuum_endpoints"][0]  # type: ignore[index]
    comparison = endpoint["comparisons"][0]  # type: ignore[index]
    endpoint["comparisons"].append(comparison)  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicated"):
        build_paired_power_priors(
            analysis,
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


def test_build_priors_rejects_invalid_comparison_values() -> None:
    """A comparison needs a named reference and non-negative dispersion."""
    analysis = deepcopy(_closed_analysis())
    endpoint = analysis["continuum_endpoints"][0]  # type: ignore[index]
    comparison = endpoint["comparisons"][0]  # type: ignore[index]
    comparison["reference_id"] = None  # type: ignore[index]
    with pytest.raises(ValueError, match="name a reference"):
        build_paired_power_priors(
            analysis,
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )

    analysis = deepcopy(_closed_analysis())
    endpoint = analysis["continuum_endpoints"][0]  # type: ignore[index]
    comparison = endpoint["comparisons"][0]  # type: ignore[index]
    comparison["observed_paired_standard_deviation"] = -0.01  # type: ignore[index]
    with pytest.raises(ValueError, match="non-negative"):
        build_paired_power_priors(
            analysis,
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


def test_build_priors_requires_at_least_one_paired_comparison() -> None:
    """Report-only endpoints cannot establish paired design power."""
    with pytest.raises(ValueError, match="no paired comparisons"):
        build_paired_power_priors(
            {"continuum_endpoints": []},
            _planning_assumptions(),
            variance_inflation=1.25,
            advantage_retention=0.5,
        )


def test_joint_power_search_recomputes_conservative_union_bound() -> None:
    """The chosen count is the first count meeting the joint power target."""
    priors = build_paired_power_priors(
        _closed_analysis(),
        _planning_assumptions(),
        variance_inflation=1.25,
        advantage_retention=0.5,
    )
    compact_power = 0.96
    target = 0.90

    count = minimum_realization_count(
        priors,
        compact_familywise_power=compact_power,
        minimum_joint_power=target,
    )
    continuum = conservative_familywise_power(priors, count)
    joint = prospective_joint_power(continuum, compact_power)

    assert joint >= target
    if count > 1:
        previous = conservative_familywise_power(priors, count - 1)
        assert prospective_joint_power(previous, compact_power) < target


def test_power_functions_reject_invalid_populations() -> None:
    """Power bounds fail closed on empty, invalid, or impossible designs."""
    priors = build_paired_power_priors(
        _closed_analysis(),
        _planning_assumptions(),
        variance_inflation=1.25,
        advantage_retention=0.5,
    )
    with pytest.raises(ValueError, match="positive integer"):
        conservative_familywise_power(priors, 0)
    with pytest.raises(ValueError, match="at least one prior"):
        conservative_familywise_power((), 10)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        prospective_joint_power(1.1, 0.9)
    with pytest.raises(ValueError, match=r"\(0, 1\]"):
        minimum_realization_count(
            priors,
            compact_familywise_power=0.96,
            minimum_joint_power=0.0,
        )
    with pytest.raises(ValueError, match="cannot support"):
        minimum_realization_count(
            priors,
            compact_familywise_power=0.89,
            minimum_joint_power=0.90,
        )


def test_power_search_fails_when_bound_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The count search has an explicit finite failure boundary."""
    priors = build_paired_power_priors(
        _closed_analysis(),
        _planning_assumptions(),
        variance_inflation=1.25,
        advantage_retention=0.5,
    )
    monkeypatch.setattr(power_module, "_MAXIMUM_REALIZATION_COUNT", 1)

    with pytest.raises(ValueError, match="exceeds the planning search"):
        minimum_realization_count(
            priors,
            compact_familywise_power=0.96,
            minimum_joint_power=0.90,
        )


@pytest.mark.parametrize(
    ("variance_inflation", "advantage_retention"),
    [(1.0, 0.5), (1.25, -0.01), (1.25, 1.01)],
)
def test_build_priors_rejects_unguarded_planning_controls(
    variance_inflation: float,
    advantage_retention: float,
) -> None:
    """The review cannot deflate variance or extrapolate prior advantages."""
    with pytest.raises(ValueError):
        build_paired_power_priors(
            _closed_analysis(),
            _planning_assumptions(),
            variance_inflation=variance_inflation,
            advantage_retention=advantage_retention,
        )
