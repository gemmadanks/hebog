"""Power planning for the final Phase 5 retention confirmation."""

from __future__ import annotations

from math import isclose

import pytest

from hebog.validation.prospective_retention_extension import (
    StratifiedBootstrapEstimate,
    balanced_confirmation_power,
    minimum_balanced_confirmation_count,
    stratified_percentile_regression,
)


def _paired_rows() -> tuple[
    dict[str, tuple[tuple[float, ...], ...]],
    dict[str, tuple[tuple[float, ...], ...]],
]:
    candidate = {
        "geometry-a": ((1.0,), (1.1,), (1.2,), (1.3,)),
        "geometry-b": ((3.0,), (3.1,), (3.2,), (3.3,)),
    }
    incumbent = {
        "geometry-a": ((0.99,), (1.09,), (1.19,), (1.29,)),
        "geometry-b": ((2.99,), (3.09,), (3.19,), (3.29,)),
    }
    return candidate, incumbent


def test_stratified_bootstrap_preserves_fixed_geometry_counts() -> None:
    """Planning resamples images within, never between, design strata."""
    candidate, incumbent = _paired_rows()

    estimate = stratified_percentile_regression(
        endpoint_id="continuum--position-p95--shell",
        candidate_by_stratum=candidate,
        incumbent_by_stratum=incumbent,
        percentile=95.0,
        resamples=2_000,
        seed=20260904,
    )

    assert estimate.stratum_counts == (
        ("geometry-a", 4),
        ("geometry-b", 4),
    )
    assert estimate.realization_count == 8
    assert estimate.positive_regression == pytest.approx(0.01)
    assert estimate.bootstrap_standard_error > 0.0
    assert estimate.bootstrap_upper_sensitivity >= (
        estimate.positive_regression
    )


def test_stratified_bootstrap_is_deterministic() -> None:
    """The fixed seed gives one reproducible planning estimate."""
    candidate, incumbent = _paired_rows()
    keywords = {
        "endpoint_id": "continuum--position-p95--shell",
        "candidate_by_stratum": candidate,
        "incumbent_by_stratum": incumbent,
        "percentile": 95.0,
        "resamples": 1_000,
        "seed": 17,
    }

    first = stratified_percentile_regression(**keywords)  # type: ignore[arg-type]
    second = stratified_percentile_regression(**keywords)  # type: ignore[arg-type]

    assert first == second


@pytest.mark.parametrize(
    ("candidate", "incumbent", "message"),
    [
        ({}, {}, "at least one stratum"),
        (
            {"a": ((1.0,), (2.0,))},
            {"b": ((1.0,), (2.0,))},
            "stratum identities",
        ),
        (
            {"a": ((1.0,), (2.0,))},
            {"a": ((1.0,),)},
            "paired realization counts",
        ),
        (
            {"a": ((1.0,), ())},
            {"a": ((1.0,), (2.0,))},
            "finite non-empty values",
        ),
    ],
)
def test_stratified_bootstrap_rejects_invalid_pairing(
    candidate: dict[str, tuple[tuple[float, ...], ...]],
    incumbent: dict[str, tuple[tuple[float, ...], ...]],
    message: str,
) -> None:
    """Malformed or unpaired evidence cannot determine qualification size."""
    with pytest.raises(ValueError, match=message):
        stratified_percentile_regression(
            endpoint_id="endpoint",
            candidate_by_stratum=candidate,
            incumbent_by_stratum=incumbent,
            percentile=95.0,
            resamples=1_000,
            seed=1,
        )


def test_minimum_count_meets_joint_power_and_previous_count_does_not() -> None:
    """The balanced search returns the first per-stratum count that passes."""
    candidate, incumbent = _paired_rows()
    first = stratified_percentile_regression(
        endpoint_id="shell",
        candidate_by_stratum=candidate,
        incumbent_by_stratum=incumbent,
        percentile=95.0,
        resamples=2_000,
        seed=2,
    )
    second = stratified_percentile_regression(
        endpoint_id="scale-4",
        candidate_by_stratum=candidate,
        incumbent_by_stratum=incumbent,
        percentile=95.0,
        resamples=2_000,
        seed=3,
    )

    plan = minimum_balanced_confirmation_count(
        (first, second),
        variance_inflation=1.25,
        confidence_level=0.95,
        minimum_joint_power=0.90,
    )

    assert plan.selected_count_per_stratum >= 2
    assert plan.joint_power_lower_bound >= 0.90
    assert len(plan.endpoint_powers) == 2
    assert all(item.power > 0.0 for item in plan.endpoint_powers)
    if plan.selected_count_per_stratum > 2:
        previous = minimum_balanced_confirmation_count(
            (first, second),
            variance_inflation=1.25,
            confidence_level=0.95,
            minimum_joint_power=0.90,
            maximum_count_per_stratum=plan.selected_count_per_stratum - 1,
            require_solution=False,
        )
        assert previous.joint_power_lower_bound < 0.90


def test_power_plan_retains_unfavourable_shift_and_inflates_variance() -> None:
    """Viewed evidence is guarded rather than assumed to improve next time."""
    candidate, incumbent = _paired_rows()
    estimate = stratified_percentile_regression(
        endpoint_id="shell",
        candidate_by_stratum=candidate,
        incumbent_by_stratum=incumbent,
        percentile=95.0,
        resamples=2_000,
        seed=4,
    )

    plan = minimum_balanced_confirmation_count(
        (estimate,),
        variance_inflation=1.25,
        confidence_level=0.95,
        minimum_joint_power=0.90,
    )
    endpoint = plan.endpoint_powers[0]

    assert endpoint.planning_expected_regression == pytest.approx(0.01)
    assert isclose(
        endpoint.planning_standard_error,
        1.25
        * estimate.bootstrap_standard_error
        * (estimate.realization_count / plan.selected_realization_count)
        ** 0.5,
    )


def test_power_plan_rejects_changed_margin_or_invalid_controls() -> None:
    """A follow-up cannot weaken its confidence or practical-loss policy."""
    candidate, incumbent = _paired_rows()
    estimate = stratified_percentile_regression(
        endpoint_id="shell",
        candidate_by_stratum=candidate,
        incumbent_by_stratum=incumbent,
        percentile=95.0,
        resamples=1_000,
        seed=5,
    )

    with pytest.raises(ValueError, match="margin"):
        minimum_balanced_confirmation_count(
            (estimate,),
            practical_regression_margin=0.0,
            variance_inflation=1.25,
            confidence_level=0.95,
            minimum_joint_power=0.90,
        )
    with pytest.raises(ValueError, match="inflation"):
        minimum_balanced_confirmation_count(
            (estimate,),
            variance_inflation=1.0,
            confidence_level=0.95,
            minimum_joint_power=0.90,
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"endpoint_id": ""}, "endpoint identity"),
        ({"percentile": 0.0}, "percentile"),
        ({"percentile": 100.0}, "percentile"),
        ({"resamples": 999}, "at least 1000"),
        ({"resamples": True}, "at least 1000"),
        ({"seed": -1}, "bootstrap seed"),
        ({"seed": True}, "bootstrap seed"),
    ],
)
def test_bootstrap_rejects_invalid_controls(
    override: dict[str, object], message: str
) -> None:
    """The nonlinear planning bootstrap accepts only reviewed controls."""
    candidate, incumbent = _paired_rows()
    keywords: dict[str, object] = {
        "endpoint_id": "shell",
        "candidate_by_stratum": candidate,
        "incumbent_by_stratum": incumbent,
        "percentile": 95.0,
        "resamples": 1_000,
        "seed": 7,
    }
    keywords.update(override)

    with pytest.raises(ValueError, match=message):
        stratified_percentile_regression(**keywords)  # type: ignore[arg-type]


def test_bootstrap_rejects_too_few_rows_and_point_mass() -> None:
    """Require independent replication and nonzero planning uncertainty."""
    with pytest.raises(ValueError, match="at least two"):
        stratified_percentile_regression(
            endpoint_id="shell",
            candidate_by_stratum={"a": ((1.0,),)},
            incumbent_by_stratum={"a": ((0.9,),)},
            percentile=95.0,
            resamples=1_000,
            seed=8,
        )
    with pytest.raises(ValueError, match="standard error must be positive"):
        stratified_percentile_regression(
            endpoint_id="shell",
            candidate_by_stratum={"a": ((1.0,), (1.0,))},
            incumbent_by_stratum={"a": ((1.0,), (1.0,))},
            percentile=95.0,
            resamples=1_000,
            seed=9,
        )


def _estimate_record(
    endpoint_id: str = "shell",
    *,
    counts: tuple[tuple[str, int], ...] = (("a", 4), ("b", 4)),
) -> StratifiedBootstrapEstimate:
    return StratifiedBootstrapEstimate(
        endpoint_id=endpoint_id,
        percentile=95.0,
        realization_count=sum(count for _, count in counts),
        stratum_counts=counts,
        positive_regression=0.01,
        bootstrap_standard_error=0.02,
        bootstrap_upper_sensitivity=0.04,
        resamples=50_000,
        seed=1,
    )


@pytest.mark.parametrize(
    ("keywords", "message"),
    [
        ({"estimates": ()}, "requires endpoint estimates"),
        ({"confidence_level": 0.5}, "confidence level"),
        ({"minimum_joint_power": 1.0}, "minimum joint power"),
        ({"selected_count_per_stratum": 1}, "at least two"),
    ],
)
def test_balanced_power_rejects_invalid_controls(
    keywords: dict[str, object], message: str
) -> None:
    """Confirmation power fails closed on incomplete design controls."""
    arguments: dict[str, object] = {
        "estimates": (_estimate_record(),),
        "selected_count_per_stratum": 10,
        "variance_inflation": 1.25,
        "confidence_level": 0.95,
        "minimum_joint_power": 0.90,
    }
    arguments.update(keywords)

    with pytest.raises(ValueError, match=message):
        balanced_confirmation_power(**arguments)  # type: ignore[arg-type]


def test_balanced_power_requires_common_balanced_unique_strata() -> None:
    """Endpoint patterns must describe one balanced qualification design."""
    controls = {
        "selected_count_per_stratum": 10,
        "variance_inflation": 1.25,
        "confidence_level": 0.95,
        "minimum_joint_power": 0.90,
    }
    with pytest.raises(ValueError, match="share exact strata"):
        balanced_confirmation_power(
            (
                _estimate_record(),
                _estimate_record("other", counts=(("a", 8),)),
            ),
            **controls,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="must be balanced"):
        balanced_confirmation_power(
            (_estimate_record(counts=(("a", 3), ("b", 5))),),
            **controls,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="must be unique"):
        balanced_confirmation_power(
            (_estimate_record(), _estimate_record()),
            **controls,  # type: ignore[arg-type]
        )


def test_minimum_search_rejects_boundary_and_unreachable_design() -> None:
    """The finite search boundary reports an explicit planning failure."""
    estimate = _estimate_record()
    controls = {
        "variance_inflation": 1.25,
        "confidence_level": 0.95,
        "minimum_joint_power": 0.90,
    }
    with pytest.raises(ValueError, match="maximum count"):
        minimum_balanced_confirmation_count(
            (estimate,),
            maximum_count_per_stratum=True,
            **controls,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="exceeds the planning search"):
        minimum_balanced_confirmation_count(
            (estimate,),
            maximum_count_per_stratum=2,
            **controls,  # type: ignore[arg-type]
        )
