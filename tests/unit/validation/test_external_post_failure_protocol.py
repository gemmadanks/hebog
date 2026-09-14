# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the approved Phase 5 post-failure evidence."""

from __future__ import annotations

import json
import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest

from hebog.validation.datasets import DatasetManifest, iter_dataset_recipes
from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).parents[3]


def _script(relative_path: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    return runpy.run_path(str(_ROOT / relative_path))


def _approved_pre_review_fixture() -> dict[str, object]:
    """Reconstruct the builder input from its checked-in frozen contract."""
    frozen = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-external-post-failure-population.json"
        ).read_text(encoding="utf-8")
    )
    audit = frozen["power_audit"]
    return {
        "review_id": "phase-5-post-failure-power-pre-review",
        "planning_method": audit["method"],
        "population": {
            "compact_realization_count": audit["compact_realization_count"],
            "continuum_geometry_count": audit["continuum_geometry_count"],
            "continuum_realizations_per_geometry": audit[
                "continuum_realizations_per_geometry"
            ],
            "minimum_continuum_realization_count": audit[
                "minimum_continuum_realization_count"
            ],
            "selected_continuum_realization_count": audit[
                "continuum_realization_count"
            ],
        },
        "power": {
            "combined_familywise_power_lower_bound": audit[
                "combined_familywise_power_lower_bound"
            ],
            "compact_familywise_power_lower_bound": audit[
                "compact_familywise_power_lower_bound"
            ],
            "continuum_familywise_power_lower_bound": audit[
                "continuum_familywise_power_lower_bound"
            ],
            "minimum_joint_power": audit["minimum_joint_power"],
        },
        "variance_rule": {
            "assumption_failure": audit["assumption_failure"],
            "family_floor_retained": audit["family_variance_floor_retained"],
            "inflation": audit["variance_inflation"],
        },
        "expected_regression_rule": {
            "retained_fraction_of_favourable_closed_difference": audit[
                "advantage_retention"
            ]
        },
        "paired_assumptions": audit["paired_assumptions"],
    }


def test_cumulative_ledger_marks_only_like_basis_pass_losses() -> None:
    """A status history stays visible without inventing a regression."""
    module = _script(
        "scripts/validation/review_phase5_cumulative_regressions.py"
    )
    transitions = module["_transition_rows"](
        {"kept": "pass", "lost": "pass", "gained": "fail"},
        {"kept": "pass", "lost": "fail", "gained": "pass"},
        left_id="closed",
        right_id="current",
        comparable=True,
    )

    assert [item["endpoint_id"] for item in transitions] == [
        "gained",
        "lost",
    ]
    assert all(item["like_semantics_and_population"] for item in transitions)
    assert module["_regressions"](
        {"kept": "pass", "lost": "pass", "already-failed": "fail"},
        {"kept": "pass", "lost": "underpowered", "already-failed": "pass"},
    ) == ("lost",)


def test_cumulative_candidate_identity_binds_component_threshold() -> None:
    """The replay identity changes with the explicit whole-model policy."""
    module = _script(
        "scripts/validation/review_phase5_cumulative_regressions.py"
    )
    configuration = module["post_correction_candidate_configuration"](
        module["_BASE_REVIEW_PATH"]
    )["compact"]

    assert configuration["fitting"][
        "component_extension_significance_sigma"
    ] == pytest.approx(1.5)
    assert configuration["fitting"][
        "integrated_flux_bias_correction_sigma"
    ] == pytest.approx(0.075)
    assert len(module["_candidate_configuration_sha256"]()) == 64


def test_cumulative_readiness_separates_science_from_power_follow_up() -> None:
    """Favourable underpowered pairs trigger power planning, not retuning."""
    module = _script(
        "scripts/validation/review_phase5_cumulative_regressions.py"
    )
    decisions = (
        SimpleNamespace(status="pass", absolute_passed=True),
        SimpleNamespace(status="underpowered", absolute_passed=True),
    )

    status, science_ready = module["_cumulative_readiness"](
        compact_status="pass",
        continuum_decisions=decisions,
        compact_regressions=(),
        continuum_regressions=(),
    )

    assert status == "pass-pending-power-review"
    assert science_ready is True
    assert module["_cumulative_readiness"](
        compact_status="pass",
        continuum_decisions=(
            SimpleNamespace(status="fail", absolute_passed=False),
        ),
        compact_regressions=(),
        continuum_regressions=(),
    ) == ("fail", False)


def test_cumulative_replay_reuses_only_exact_closed_component_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expensive closed compile may be reused only by bound identity."""
    module = _script(
        "scripts/validation/review_phase5_cumulative_regressions.py"
    )
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"sealed_campaign_sha256":"campaign",'
        '"catalogue_semantics":"fitted-gaussian-component",'
        '"closed_post_failure_component_baseline":{"status":"pass"}}\n'
    )
    loader = module["_load_closed_component_baseline"]
    monkeypatch.setitem(
        loader.__globals__,
        "file_sha256",
        lambda _path: module["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"],
    )

    baseline, sha256 = loader(path, campaign_sha256="campaign")

    assert baseline == {"status": "pass"}
    assert sha256 == module["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"]
    with pytest.raises(ValueError, match="campaign identity"):
        loader(path, campaign_sha256="different")


def test_post_correction_power_review_adds_a_balanced_safety_buffer() -> None:
    """The next one-look is not sized exactly at the theoretical boundary."""
    module = _script(
        "scripts/validation/review_phase5_post_correction_power.py"
    )

    assert module["_selected_realization_count"](1000) == 1600
    assert module["_selected_realization_count"](1550) == 1708
    assert module["_selected_realization_count"](1600) == 1760
    with pytest.raises(ValueError, match="positive"):
        module["_selected_realization_count"](0)
    assert (
        module["_sha256"](
            _ROOT
            / "config/contracts/phase-5-external-confirmation-population.json"
        )
        == module["_CONFIRMATION_POPULATION_SHA256"]
    )
    assert (
        module["_sha256"](
            _ROOT
            / "config/contracts/phase-5-external-post-failure-population.json"
        )
        == module["_POST_FAILURE_POPULATION_SHA256"]
    )


def test_recovery_power_review_separates_candidate_and_replay_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Power review binds the candidate without relabelling its wrapper."""
    module = _script(
        "scripts/validation/review_phase5_post_correction_power.py"
    )
    candidate_revision = "c" * 40
    replay_revision = "d" * 40
    source_sha256 = "e" * 64
    configuration_sha256 = "f" * 64
    campaign_sha256 = "1" * 64
    reference_sha256 = "2" * 64
    baseline_sha256 = "3" * 64
    endpoint = {"endpoint_id": "continuum--metric--overall"}
    decision = {
        "candidate_revision": candidate_revision,
        "candidate_source_tree_sha256": source_sha256,
        "candidate_configuration_sha256": configuration_sha256,
        "original_campaign_sha256": campaign_sha256,
    }
    ledger = {
        "status": "pass-pending-power-review",
        "cumulative_science_regression_ready": True,
        "like_semantics_compact_regressions": [],
        "like_semantics_continuum_regressions": [],
        "candidate_revision": candidate_revision,
        "replay_execution_revision": replay_revision,
        "candidate_source_tree_sha256": source_sha256,
        "candidate_configuration_sha256": configuration_sha256,
        "sealed_campaign_sha256": campaign_sha256,
        "reference_reconstruction_sha256": reference_sha256,
        "closed_component_baseline_ledger_sha256": baseline_sha256,
        "prospective_continuum_analysis": [endpoint],
    }
    validate = module["_validate_ledger"]
    evidence = module["_RecoveryEvidenceIdentities"](
        campaign_sha256=campaign_sha256,
        reference_reconstruction_sha256=reference_sha256,
        closed_baseline_sha256=baseline_sha256,
    )
    monkeypatch.setitem(
        validate.__globals__,
        "source_tree_sha256",
        lambda _root: source_sha256,
    )

    endpoints = validate(
        ledger,
        root=_ROOT,
        recovery_decision=decision,
        evidence=evidence,
    )

    assert endpoints == [endpoint]
    assert ledger["candidate_revision"] != ledger["replay_execution_revision"]
    changed = dict(ledger, candidate_revision="a" * 40)
    with pytest.raises(ValueError, match="approved recovery decision"):
        validate(
            changed,
            root=_ROOT,
            recovery_decision=decision,
            evidence=evidence,
        )
    identity_failures = (
        ("sealed_campaign_sha256", "9" * 64, "sealed campaign"),
        (
            "reference_reconstruction_sha256",
            "9" * 64,
            "reference reconstruction",
        ),
        (
            "closed_component_baseline_ledger_sha256",
            "9" * 64,
            "closed component baseline",
        ),
        ("replay_execution_revision", "not-a-revision", "replay execution"),
    )
    for key, changed_value, message in identity_failures:
        with pytest.raises(ValueError, match=message):
            validate(
                dict(ledger, **{key: changed_value}),
                root=_ROOT,
                recovery_decision=decision,
                evidence=evidence,
            )
    monkeypatch.setitem(
        validate.__globals__,
        "source_tree_sha256",
        lambda _root: "9" * 64,
    )
    with pytest.raises(ValueError, match="candidate source identity"):
        validate(
            ledger,
            root=_ROOT,
            recovery_decision=decision,
            evidence=evidence,
        )


def test_cumulative_replay_separates_closed_and_candidate_source_ids() -> None:
    """Closed verification cannot mistake the prospective tree for history."""
    module = _script(
        "scripts/validation/review_phase5_cumulative_regressions.py"
    )
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )

    module["_install_historical_source_view"]({"_HELPERS": helpers})

    loader_globals = helpers["load_post_failure_population"].__globals__
    assert (
        loader_globals["source_tree_sha256"](_ROOT)
        == helpers["_SOURCE_TREE_SHA256"]
    )
    assert source_tree_sha256(_ROOT) != helpers["_SOURCE_TREE_SHA256"]


def test_post_failure_population_builder_freezes_approved_design(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approved 1,600/800 design retains every exact paired prior."""
    module = _script(
        "scripts/validation/freeze_phase5_external_post_failure_population.py"
    )
    pre_review_path = tmp_path / "post-failure-power-pre-review.json"
    pre_review_path.write_bytes(
        module["_json_bytes"](_approved_pre_review_fixture())
    )
    globals_ = module["build_post_failure_documents"].__globals__
    monkeypatch.setitem(globals_, "_PRE_REVIEW_PATH", str(pre_review_path))
    monkeypatch.setitem(
        globals_,
        "_PRE_REVIEW_SHA256",
        globals_["file_sha256"](pre_review_path),
    )
    monkeypatch.setitem(
        globals_,
        "source_tree_sha256",
        lambda _root: module["_CANDIDATE_SOURCE_TREE_SHA256"],
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
    assert (
        freeze["power_audit"]
        == json.loads(
            (
                _ROOT / "config/contracts/"
                "phase-5-external-post-failure-population.json"
            ).read_text(encoding="utf-8")
        )["power_audit"]
    )
    assert freeze["power_audit"]["minimum_continuum_realization_count"] == (
        1550
    )
    assert freeze["power_audit"]["combined_familywise_power_lower_bound"] > 0.9
    assert freeze["source_binding"]["candidate_commit"] == (
        "63e4b5886a3f5acb75125d258f5b71c13ca4eeaf"
    )
    assert freeze["execution_authorized"] is False


def test_post_failure_protocol_binds_approved_population(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fresh protocol binds the separately approved terminal look."""
    module = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    globals_ = module["load_post_failure_population"].__globals__
    monkeypatch.setitem(
        globals_,
        "source_tree_sha256",
        lambda _root: module["_SOURCE_TREE_SHA256"],
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
    assert {
        item.finder_id: item.container_image_digest
        for item in protocol.references
    } == {
        "released-pybdsf": (
            "sha256:c6dca91f0b32fd217460a5a2332e42a99fe68e6f1c11431af092e6be53e98bb8"
        ),
        "pinned-pybdsf-master": (
            "sha256:81fc680669bbf92dcac9b68be8d7a18e6b30a0826b0e2e7b63c05f81f1f304ca"
        ),
        "aegean": (
            "sha256:738591844996e672e8679a5f4b9233a1bd7bc06698af4aef69b4efff7f3b1551"
        ),
    }
    assert decision.hebog_container_image_digest == (
        "sha256:4341ec7946b737613178d407af5e26a2ec28e7aca6ffe40bf90abf879aeb9061"
    )
    assert decision.execution_authorized is True
    assert decision.preflight_review_sha256 == (
        "835abe1c116c92fe45c3aa9960d70e8d4d4782b9beb5c7d3ce616b10d14410cd"
    )
    assert decision.preflight_review_sha256 in decision.named_review
    assert decision.pybdsf_ncores == 4
    assert decision.execution_concurrency == 2
    assert decision.source_tree_sha256 != source_tree_sha256(_ROOT)


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


def test_post_failure_registry_and_evaluation_bind_exact_priors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compiler/evaluator chain retains all gates and exact priors."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    globals_ = helpers["load_post_failure_population"].__globals__
    monkeypatch.setitem(
        globals_,
        "source_tree_sha256",
        lambda _root: helpers["_SOURCE_TREE_SHA256"],
    )
    registry = helpers["load_post_failure_endpoint_registry"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-endpoint-registry.json"
    )
    evaluator = _script(
        "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
    )
    evaluator_helpers = evaluator["_HELPERS"]
    evaluator_globals = evaluator_helpers[
        "load_post_failure_population"
    ].__globals__
    monkeypatch.setitem(
        evaluator_globals,
        "source_tree_sha256",
        lambda _root: evaluator_helpers["_SOURCE_TREE_SHA256"],
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


def test_storage_ready_review_can_be_approved() -> None:
    """The exact review becomes approvable only above the storage floor."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-preflight-review.json"
    )
    review = helpers["load_post_failure_preflight_review"](review_path)
    review_sha256 = helpers["file_sha256"](review_path)

    assert review["storage"]["passed"] is True
    assert review["named_execution_approval_recommended"] is True
    assert (
        helpers["post_failure_preflight_review_sha256"](
            {
                "preflight_review_sha256": review_sha256,
                "named_review": f"Gemma Danks approved {review_sha256}",
            },
            _ROOT,
            pending=False,
        )
        == review_sha256
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
    review["storage"]["observed_available_gib"] = 30.0
    review["storage"]["observed_available_kib"] = 31_457_280
    globals_ = helpers["load_post_failure_preflight_review"].__globals__
    monkeypatch.setitem(globals_, "json_object", lambda _path: review)

    with pytest.raises(ValueError, match="storage observation"):
        helpers["load_post_failure_preflight_review"](review_path)


def test_preflight_review_rejects_changed_runtime_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Named approval cannot bind a substituted runtime image."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-preflight-review.json"
    )
    review = deepcopy(helpers["json_object"](review_path))
    review["runtime_images"][0]["digest"] = f"sha256:{'0' * 64}"
    globals_ = helpers["load_post_failure_preflight_review"].__globals__
    monkeypatch.setitem(globals_, "json_object", lambda _path: review)

    with pytest.raises(ValueError, match="runtime image identity"):
        helpers["load_post_failure_preflight_review"](review_path)


def test_preflight_review_retains_pending_authorization_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval-dependent files may change without changing the review."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-preflight-review.json"
    )
    approval_dependent = {
        "config/contracts/phase-5-external-post-failure-execution-decision.json",
        "config/contracts/phase-5-external-post-failure-endpoint-registry.json",
        "config/contracts/phase-5-external-post-failure-evaluation.json",
    }
    original_sha256 = helpers["file_sha256"]

    def transitioned_sha256(path: Path) -> str:
        if path.relative_to(_ROOT).as_posix() in approval_dependent:
            return "0" * 64
        return original_sha256(path)

    globals_ = helpers["load_post_failure_preflight_review"].__globals__
    monkeypatch.setitem(globals_, "file_sha256", transitioned_sha256)
    monkeypatch.setitem(
        globals_,
        "authorization_has_transitioned",
        lambda _root: True,
    )

    review = helpers["load_post_failure_preflight_review"](review_path)

    assert review["status"] == "ready-for-named-execution-approval"


def test_preflight_review_rejects_authorization_drift_while_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval-dependent files remain exact before the transition."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-failure-preflight-review.json"
    )
    review = deepcopy(helpers["json_object"](review_path))
    decision_identity = next(
        item
        for item in review["identity_artifacts"]
        if item["relative_path"].endswith("execution-decision.json")
    )
    decision_identity["sha256"] = "0" * 64
    globals_ = helpers["load_post_failure_preflight_review"].__globals__
    monkeypatch.setitem(globals_, "json_object", lambda _path: review)
    monkeypatch.setitem(
        globals_,
        "authorization_has_transitioned",
        lambda _root: False,
    )

    with pytest.raises(ValueError, match="preflight artifact changed"):
        helpers["load_post_failure_preflight_review"](review_path)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("awaiting-named-execution-approval", False),
        ("reviewed-before-external-output", True),
    ],
)
def test_authorization_transition_recognizes_only_governed_states(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected: bool,
) -> None:
    """The cycle breaker distinguishes the two valid decision states."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    globals_ = helpers["authorization_has_transitioned"].__globals__
    monkeypatch.setattr(
        globals_["json"],
        "loads",
        lambda _value: {"status": status},
    )

    assert helpers["authorization_has_transitioned"](_ROOT) is expected


@pytest.mark.parametrize("decision", [[], {"status": "invalid"}])
def test_authorization_transition_rejects_invalid_state(
    monkeypatch: pytest.MonkeyPatch,
    decision: object,
) -> None:
    """Malformed or unknown decision states cannot bypass review checks."""
    helpers = _script(
        "scripts/validation/phase5_external_post_failure_protocol.py"
    )
    globals_ = helpers["authorization_has_transitioned"].__globals__
    monkeypatch.setattr(
        globals_["json"],
        "loads",
        lambda _value: decision,
    )

    with pytest.raises(ValueError, match="authorization state"):
        helpers["authorization_has_transitioned"](_ROOT)


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


def test_post_failure_request_matrix_has_exact_scaled_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest expansion yields 2,400 inputs and 12,000 governed runs."""
    launcher = _script(
        "scripts/benchmark/run_phase5_external_post_failure_campaign.py"
    )
    helpers = launcher["_HELPERS"]
    globals_ = helpers["load_post_failure_population"].__globals__
    monkeypatch.setitem(
        globals_,
        "source_tree_sha256",
        lambda _root: helpers["_SOURCE_TREE_SHA256"],
    )
    protocol = helpers["load_post_failure_protocol"](
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
