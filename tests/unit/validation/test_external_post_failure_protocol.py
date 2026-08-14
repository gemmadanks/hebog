# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the approved Phase 5 post-failure evidence."""

from __future__ import annotations

import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest

from hebog.validation.datasets import DatasetManifest, iter_dataset_recipes

_ROOT = Path(__file__).parents[3]


def _script(relative_path: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    return runpy.run_path(str(_ROOT / relative_path))


def test_post_failure_population_builder_freezes_approved_design() -> None:
    """The approved 1,600/800 design retains every exact paired prior."""
    module = _script(
        "scripts/validation/freeze_phase5_external_post_failure_population.py"
    )

    continuum, compact, freeze = module["build_post_failure_documents"](
        repository_root=_ROOT,
        continuum_template_path=(
            _ROOT / "config/datasets/"
            "phase-5-external-confirmation-continuum.json"
        ),
        compact_template_path=(
            _ROOT / "config/datasets/"
            "phase-5-external-confirmation-compact-blend.json"
        ),
    )

    continuum_manifest = DatasetManifest.model_validate(continuum)
    compact_manifest = DatasetManifest.model_validate(compact)
    continuum_seeds = {
        recipe.seed
        for dataset in continuum_manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }
    compact_seeds = {
        recipe.seed
        for dataset in compact_manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }
    assert len(continuum_seeds) == 1600
    assert len(compact_seeds) == 800
    assert continuum_seeds.isdisjoint(compact_seeds)
    assert freeze["population_audit"]["seed_disjoint"] is True
    assert len(freeze["power_audit"]["paired_assumptions"]) == 226
    assert freeze["power_audit"]["minimum_continuum_realization_count"] == (
        1550
    )
    assert freeze["power_audit"]["combined_familywise_power_lower_bound"] > 0.9
    assert freeze["source_binding"]["candidate_commit"] == (
        "63e4b5886a3f5acb75125d258f5b71c13ca4eeaf"
    )
    assert freeze["execution_authorized"] is False


def test_post_failure_protocol_binds_pending_population() -> None:
    """The fresh protocol is valid while its one-look remains closed."""
    module = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    protocol = module["load_post_failure_protocol"](
        _ROOT
        / "config/contracts/phase-5-external-post-failure-comparison.json"
    )
    decision = module["load_post_failure_execution_decision"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-execution-decision.json"
    )

    assert tuple(item.image_count for item in protocol.populations) == (
        1600,
        800,
    )
    assert decision.execution_authorized is False
    assert decision.preflight_review_sha256 == "pending"
    assert decision.pybdsf_ncores == 4
    assert decision.execution_concurrency == 2


def test_post_failure_seeds_are_disjoint_from_all_history() -> None:
    """Neither fresh lane reuses any predecessor dataset seed."""
    post_failure: set[int] = set()
    historical: set[int] = set()
    for path in sorted((_ROOT / "config/datasets").glob("*.json")):
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        seeds = {
            recipe.seed
            for dataset in manifest.datasets
            for recipe in iter_dataset_recipes(dataset)
        }
        if manifest.manifest_id.startswith("phase-5-external-post-failure-"):
            assert not post_failure.intersection(seeds)
            post_failure.update(seeds)
        else:
            historical.update(seeds)

    assert len(post_failure) == 2400
    assert post_failure.isdisjoint(historical)


def test_post_failure_registry_and_evaluation_bind_exact_priors() -> None:
    """The compiler/evaluator chain retains all gates and exact priors."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    registry = helpers["load_post_failure_endpoint_registry"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-endpoint-registry.json"
    )
    evaluator = _script(
        "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
    )
    contract = evaluator["load_post_failure_evaluation_contract"](
        _ROOT
        / "config/contracts/phase-5-external-post-failure-evaluation.json",
        _ROOT / "scripts/validation/"
        "evaluate_phase5_external_post_failure_decision.py",
    )

    assert registry["expanded_continuum_counts"] == {
        "binding": 143,
        "report_only": 15,
        "total": 158,
    }
    assert contract["population"] == {
        "image_count": 2400,
        "terminal_run_count": 12000,
        "binding_run_count": 8000,
        "continuum_image_count": 1600,
        "compact_blend_image_count": 800,
    }
    assert len(contract["endpoint_power_priors"]) == 226
    assert contract["failure_policy"] == (
        "absolute-first-retain-denominator-incomplete-reference-fails-closed"
    )
    assert contract["one_look_rule"] == (
        "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
    )


def test_storage_blocked_review_cannot_be_approved() -> None:
    """Identity readiness cannot override the predeclared storage floor."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-preflight-review.json"
    )
    review = helpers["load_post_failure_preflight_review"](review_path)
    review_sha256 = helpers["file_sha256"](review_path)

    assert review["storage"]["passed"] is False
    assert review["named_execution_approval_recommended"] is False
    with pytest.raises(ValueError, match="approved post-failure review"):
        helpers["post_failure_preflight_review_sha256"](
            {
                "preflight_review_sha256": review_sha256,
                "named_review": f"Gemma Danks approved {review_sha256}",
            },
            _ROOT,
            pending=False,
        )


def test_preflight_review_recomputes_storage_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declared readiness cannot contradict the recorded free-space values."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-preflight-review.json"
    )
    review = deepcopy(helpers["json_object"](review_path))
    review["status"] = "ready-for-named-execution-approval"
    review["storage"]["passed"] = True
    review["named_execution_approval_recommended"] = True
    globals_ = helpers["load_post_failure_preflight_review"].__globals__
    monkeypatch.setitem(globals_, "json_object", lambda _path: review)

    with pytest.raises(ValueError, match="storage observation"):
        helpers["load_post_failure_preflight_review"](review_path)


def test_post_failure_launcher_rejects_pending_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Pending authorization cannot inspect images or create staging."""
    module = _script(
        "scripts/benchmark/run_phase5_external_post_failure_campaign.py"
    )

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("container inspection must remain closed")

    monkeypatch.setitem(
        module["_HELPERS"],
        "load_post_failure_execution_decision",
        lambda _path: SimpleNamespace(execution_authorized=False),
    )
    monkeypatch.setattr(module["_TERMINAL"]["subprocess"], "run", unexpected)

    with pytest.raises(ValueError, match="execution is not authorized"):
        module["preflight_post_failure_campaign"](
            repository_root=_ROOT,
            output=tmp_path / "campaign",
            images={
                "hebog": "unused",
                "released-pybdsf": "unused",
                "pinned-pybdsf-master": "unused",
                "aegean": "unused",
            },
        )
    assert not (tmp_path / "campaign").exists()


def test_post_failure_request_matrix_has_exact_scaled_counts() -> None:
    """Manifest expansion yields 2,400 inputs and 12,000 governed runs."""
    launcher = _script(
        "scripts/benchmark/run_phase5_external_post_failure_campaign.py"
    )
    protocol = launcher["_HELPERS"]["load_post_failure_protocol"](
        _ROOT
        / "config/contracts/phase-5-external-post-failure-comparison.json"
    )

    inputs, runs = launcher["_TERMINAL"]["_population_requests"](
        _ROOT,
        protocol,
    )

    assert len(inputs) == 2400
    assert len(runs) == 12000
    assert sum(item.mode in {"candidate", "operational"} for item in runs) == (
        8000
    )


def test_post_failure_compiler_installs_scaled_truth_composition() -> None:
    """The compiler parses new counts and owns observable truth metadata."""
    module = _script(
        "scripts/validation/compile_phase5_external_post_failure_campaign.py"
    )
    terminal = module["_configured_terminal"]()
    globals_ = terminal["compile_terminal_analysis"].__globals__

    assert get_args(
        globals_["CampaignRequest"].model_fields["image_count"].annotation
    ) == (2400,)
    assert get_args(
        globals_["TerminalCampaignResult"].model_fields["run_count"].annotation
    ) == (12000,)
    assert type(globals_["_truth_objects"]).__name__ == (
        "ObservableTruthCompiler"
    )
    assert type(globals_["_continuum_image_observations"]).__name__ == (
        "SharedContinuumImageCompiler"
    )


def test_endpoint_specific_evaluator_applies_each_reference_bound() -> None:
    """One loose bound cannot conceal another reference's excess variance."""
    module = _script(
        "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
    )
    terminal = module["_TERMINAL"]
    evidence = terminal["EndpointEvidence"](
        endpoint_id="continuum--mask-iou--overall",
        lane="continuum",
        metric_family="mask-iou",
        stratum="overall",
        position_population="not-applicable",
        image_count=1600,
        candidate_status="success",
        candidate_value=0.9,
        absolute_decision_value=0.9,
        comparisons=(
            terminal["ReferenceComparisonEvidence"](
                reference_id="released-pybdsf",
                status="success",
                reference_value=0.9,
                positive_regression=0.0,
                upper_confidence_limit=0.01,
                observed_paired_standard_deviation=0.2,
            ),
            terminal["ReferenceComparisonEvidence"](
                reference_id="pinned-pybdsf-master",
                status="success",
                reference_value=0.9,
                positive_regression=0.0,
                upper_confidence_limit=0.01,
                observed_paired_standard_deviation=0.2,
            ),
        ),
    )
    policy = terminal["EndpointPolicy"](
        lane="continuum",
        metric_family="mask-iou",
        position_population="not-applicable",
        expected_image_count=1600,
        desirable_direction="higher-is-better",
        absolute_relation="at-least",
        absolute_limit=0.8,
        absolute_decision_statistic="point-estimate",
        practical_regression_margin=0.05,
        planning_paired_standard_deviation=0.15,
        binding_references=(
            "released-pybdsf",
            "pinned-pybdsf-master",
        ),
    )
    evaluator = module["EndpointSpecificEvaluator"](
        [
            {
                "endpoint_id": evidence.endpoint_id,
                "reference_id": "released-pybdsf",
                "metric_family": "mask-iou",
                "practical_regression_margin": 0.05,
                "planning_paired_standard_deviation": 0.25,
            },
            {
                "endpoint_id": evidence.endpoint_id,
                "reference_id": "pinned-pybdsf-master",
                "metric_family": "mask-iou",
                "practical_regression_margin": 0.05,
                "planning_paired_standard_deviation": 0.15,
            },
        ]
    )

    decision = evaluator(evidence, policy)

    assert decision.status == "underpowered"
    assert tuple(item.status for item in decision.comparisons) == (
        "pass",
        "underpowered",
    )
    assert tuple(
        item.planning_paired_standard_deviation
        for item in decision.comparisons
    ) == (0.25, 0.15)
