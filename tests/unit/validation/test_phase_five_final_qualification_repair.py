"""Fail-closed contracts for the final-qualification evaluation repair."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_COMPILER_RELATIVE = (
    "scripts/validation/compile_phase5_final_qualification_repair.py"
)
_EVALUATOR_RELATIVE = (
    "scripts/validation/evaluate_phase5_final_qualification_repair.py"
)
_FROZEN_COMPILER_RELATIVE = (
    "scripts/validation/compile_phase5_final_qualification_campaign.py"
)
_CAMPAIGN_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-comparison/campaign.json"
)
_ANALYSIS_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-analysis.json"
)
_DECISION_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-decision.json"
)


def _script(relative_path: str) -> dict[str, Any]:
    """Load one validation script without calling its entry point."""
    return runpy.run_path(str(_ROOT / relative_path))


def _identity(root: Path, relative_path: str, value: str) -> dict[str, str]:
    """Create one synthetic checksum-bound identity."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _authorization(root: Path) -> tuple[Path, dict[str, Any]]:
    """Create an exact synthetic future execution authorization."""
    identities = {
        "campaign": _identity(root, _CAMPAIGN_RELATIVE, "campaign\n"),
        "repair_compiler": _identity(
            root, _COMPILER_RELATIVE, "repair compiler\n"
        ),
        "repair_evaluator": _identity(
            root, _EVALUATOR_RELATIVE, "repair evaluator\n"
        ),
        "repair_identity_review": _identity(
            root,
            "config/contracts/"
            "phase-5-final-qualification-evaluation-repair-review.json",
            "repair review\n",
        ),
    }
    review_sha256 = identities["repair_identity_review"]["sha256"]
    document: dict[str, Any] = {
        "campaign": {
            **identities["campaign"],
            "request_sha256": "e" * 64,
        },
        "campaign_reexecution_authorized": False,
        "compilation_authorized": True,
        "cutover_authorized": False,
        "decision_id": (
            "phase-5-final-qualification-evaluation-repair-decision"
        ),
        "evaluation_authorized": True,
        "execution_authorized": True,
        "named_review": {
            "approval": f"I approve repair review {review_sha256}",
            "reviewer": "Gemma Danks",
        },
        "optimization_authorized": False,
        "outputs": {
            "analysis_path": _ANALYSIS_RELATIVE,
            "analysis_state": "absent",
            "decision_path": _DECISION_RELATIVE,
            "decision_state": "absent",
        },
        "release_authorized": False,
        "repair_compiler": identities["repair_compiler"],
        "repair_evaluator": identities["repair_evaluator"],
        "repair_identity_review": identities["repair_identity_review"],
        "rescoring_authorized": False,
        "schema_version": 1,
        "science_or_gates_changed": False,
        "status": "reviewed-before-final-qualification-evaluation-repair",
        "tuning_authorized": False,
    }
    path = root / "authorization.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, document


def test_repair_implementation_decision_records_only_approved_scope() -> None:
    """Named approval permits implementation and identity freezing only."""
    path = (
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-evaluation-repair-implementation-"
        "decision.json"
    )
    decision = json.loads(path.read_text(encoding="utf-8"))

    assert decision["status"] == (
        "reviewed-before-evaluation-repair-implementation"
    )
    assert decision["pre_review"]["sha256"] == (
        "8cff6163c4f0ebc3325b0c9c801e099e198ae8bb43b070618e2e0a914e546917"
    )
    assert decision["campaign"]["sha256"] == (
        "4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08"
    )
    boundary = decision["authorization_boundary"]
    assert boundary.pop("implementation_authorized") is True
    assert set(boundary.values()) == {False}
    assert (
        file_sha256(_ROOT / decision["pre_review"]["path"])
        == (decision["pre_review"]["sha256"])
    )


def test_repair_configures_the_actual_inherited_json_seam() -> None:
    """The JSON adapter that failed now loads the final approved decision."""
    repair = _script(_COMPILER_RELATIVE)
    terminal = repair["configure_repaired_terminal"]()
    verifier_globals = terminal["verify_terminal_campaign"].__globals__
    json_loader = verifier_globals["_json_object"]
    helpers = json_loader.__globals__["_HELPERS"]

    assert helpers["load_post_failure_execution_decision"].__name__ == (
        "load_final_qualification_execution_decision"
    )
    decision = json_loader(
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-execution-decision.json"
    )
    assert decision["decision_id"] == "phase-5-external-execution-decision"
    assert decision["execution_authorized"] is True
    with pytest.raises(ValueError, match="final qualification"):
        helpers["load_post_failure_execution_decision"](
            _ROOT / "config/contracts/"
            "phase-5-external-recovery-execution-decision.json"
        )
    registry = verifier_globals["load_endpoint_registry"](
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-endpoint-registry.json",
        _ROOT / "scripts/validation/"
        "compile_phase5_final_qualification_campaign.py",
    )
    assert registry["closed_compact_evidence_only"] is True
    request_model = verifier_globals["CampaignRequest"]
    assert (
        request_model.model_fields["image_count"].annotation == Literal[1688]
    )
    assert request_model.model_fields["run_count"].annotation == Literal[8440]
    assert (
        file_sha256(_ROOT / _FROZEN_COMPILER_RELATIVE)
        == "c2b7f3ac3b072ba1c250cd27c917495cab3ba517cfb86a9102d06c763b66b165"
    )


def test_repair_authorization_is_exact_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper rejects changed science, reruns, or a changed program."""
    repair = _script(_COMPILER_RELATIVE)
    path, document = _authorization(tmp_path)
    monkeypatch.setitem(
        repair["load_repair_authorization"].__globals__,
        "_CAMPAIGN_SHA256",
        document["campaign"]["sha256"],
    )
    monkeypatch.setitem(
        repair["load_repair_authorization"].__globals__,
        "_CAMPAIGN_REQUEST_SHA256",
        document["campaign"]["request_sha256"],
    )

    loaded = repair["load_repair_authorization"](
        path,
        tmp_path / _COMPILER_RELATIVE,
        tmp_path / _EVALUATOR_RELATIVE,
        tmp_path,
    )
    assert loaded == document

    for key in (
        "campaign_reexecution_authorized",
        "optimization_authorized",
        "rescoring_authorized",
        "science_or_gates_changed",
        "tuning_authorized",
    ):
        changed = dict(document)
        changed[key] = True
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match="not exactly authorized"):
            repair["load_repair_authorization"](
                path,
                tmp_path / _COMPILER_RELATIVE,
                tmp_path / _EVALUATOR_RELATIVE,
                tmp_path,
            )
    analysis = tmp_path / _ANALYSIS_RELATIVE
    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text("unexpected output\n", encoding="utf-8")
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(FileExistsError, match="must both be absent"):
        repair["load_repair_authorization"](
            path,
            tmp_path / _COMPILER_RELATIVE,
            tmp_path / _EVALUATOR_RELATIVE,
            tmp_path,
        )
    analysis.unlink()
    path.write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / _COMPILER_RELATIVE).write_text(
        "changed repair compiler\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="checksum changed"):
        repair["load_repair_authorization"](
            path,
            tmp_path / _COMPILER_RELATIVE,
            tmp_path / _EVALUATOR_RELATIVE,
            tmp_path,
        )


def test_repair_compiler_delegates_to_the_frozen_science_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper changes the loader seam but adds no science compiler."""
    repair = _script(_COMPILER_RELATIVE)
    observed: dict[str, Any] = {}
    original_configuration = object()
    monkeypatch.setitem(
        globals(), "_configured_terminal", original_configuration
    )

    def frozen_compile(
        campaign_path: Path,
        registry_path: Path,
        compiler_path: Path,
    ) -> dict[str, Any]:
        observed.update(
            {
                "campaign_path": campaign_path,
                "registry_path": registry_path,
                "compiler_path": compiler_path,
                "configuration": globals()["_configured_terminal"],
            }
        )
        return {"analysis_id": "phase-5-final-qualification-terminal-science"}

    monkeypatch.setitem(
        repair["compile_repaired_analysis"].__globals__,
        "_FROZEN_COMPILE",
        frozen_compile,
    )
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}\n", encoding="utf-8")
    campaign_path = tmp_path / "campaign.json"
    result = repair["compile_repaired_analysis"](
        campaign_path,
        authorization_path,
        {"repair_identity_review": {"sha256": "r" * 64}},
    )

    assert observed["campaign_path"] == campaign_path
    assert observed["registry_path"] == (
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-endpoint-registry.json"
    )
    assert observed["compiler_path"] == _ROOT / _FROZEN_COMPILER_RELATIVE
    assert observed["configuration"] is repair["configure_repaired_terminal"]
    assert globals()["_configured_terminal"] is original_configuration
    assert result["evaluation_repair"]["science_or_gates_changed"] is False


def test_repair_analysis_requires_exact_provenance(tmp_path: Path) -> None:
    """The evaluator admits only the authorized repair compiler output."""
    evaluator = _script(_EVALUATOR_RELATIVE)
    authorization_path, authorization = _authorization(tmp_path)
    authorization_sha256 = hashlib.sha256(
        authorization_path.read_bytes()
    ).hexdigest()
    analysis = {
        "analysis_id": "phase-5-final-qualification-terminal-science",
        "campaign_sha256": authorization["campaign"]["sha256"],
        "evaluation_repair": {
            "authorization_sha256": authorization_sha256,
            "compatibility_change": (
                "install-final-loaders-at-inherited-compatibility-seam"
            ),
            "frozen_compiler_sha256": (
                "c2b7f3ac3b072ba1c250cd27c917495cab3ba517cfb86a9102d06c763b66b165"
            ),
            "frozen_evaluator_sha256": (
                "558e29574287aef6bee348fb37c329b7dab2f115ff42c481d3a1019d3f713560"
            ),
            "repair_compiler_sha256": authorization["repair_compiler"][
                "sha256"
            ],
            "repair_identity_review_sha256": authorization[
                "repair_identity_review"
            ]["sha256"],
            "science_or_gates_changed": False,
        },
    }
    path = tmp_path / _ANALYSIS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis), encoding="utf-8")
    loaded = evaluator["load_repaired_analysis"](
        path, authorization_path, authorization
    )
    assert loaded == analysis

    changed = cast(dict[str, Any], analysis["evaluation_repair"])
    changed["repair_compiler_sha256"] = "f" * 64
    path.write_text(json.dumps(analysis), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance changed"):
        evaluator["load_repaired_analysis"](
            path,
            authorization_path,
            authorization,
        )


def test_repair_evaluator_delegates_unchanged_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The repair evaluator calls the frozen decision function unchanged."""
    evaluator = _script(_EVALUATOR_RELATIVE)
    observed: list[tuple[object, object, object]] = []
    expected = (object(), (object(),), "pass")

    def frozen_evaluate(
        analysis: object, contract: object, registry: object
    ) -> tuple[object, tuple[object, ...], str]:
        observed.append((analysis, contract, registry))
        return expected

    monkeypatch.setitem(
        evaluator["evaluate_repaired_analysis"].__globals__["_FROZEN"],
        "evaluate_final_qualification_analysis",
        frozen_evaluate,
    )
    analysis: dict[str, Any] = {}
    contract: dict[str, Any] = {}
    registry: dict[str, Any] = {}

    result = evaluator["evaluate_repaired_analysis"](
        analysis, contract, registry
    )

    assert result == expected
    assert observed == [(analysis, contract, registry)]


def test_repair_identity_review_is_non_executable_and_exact() -> None:
    """The exact identity review remains non-executable by itself."""
    path = (
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-evaluation-repair-review.json"
    )
    review = json.loads(path.read_text(encoding="utf-8"))

    assert review["status"] == (
        "ready-for-named-final-qualification-evaluation-repair-approval"
    )
    assert review["implementation"]["commit"] == (
        "b6ce3cdd49d3e51f2d1437cea3d4d4a4d79d056c"
    )
    assert review["implementation"]["tree"] == (
        "fa7e1a07897acea92689f1eeab3b052ac3ca0147"
    )
    assert review["campaign"]["sha256"] == (
        "4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08"
    )
    assert set(review["authorization"].values()) == {
        False,
        None,
        (
            "config/contracts/phase-5-final-qualification-evaluation-"
            "repair-decision.json"
        ),
    }
    assert set(review["scientific_scope"].values()) == {False}
    original_review = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-final-qualification-identity-review.json"
        ).read_text(encoding="utf-8")
    )
    assert review["runtime_images"] == original_review["runtime_images"]
    identities = [
        review["implementation"]["pre_review"],
        review["implementation"]["implementation_decision"],
        review["implementation"]["repair_compiler"],
        review["implementation"]["repair_evaluator"],
        *review["frozen_composition"]["identity_artifacts"],
    ]
    for identity in identities:
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]
    assert (
        file_sha256(_ROOT / review["campaign"]["path"])
        == (review["campaign"]["sha256"])
    )
    assert not (_ROOT / review["outputs"]["analysis_path"]).exists()
    assert not (_ROOT / review["outputs"]["decision_path"]).exists()


def test_repair_decision_records_exact_named_authorization() -> None:
    """The approved decision opens only one compilation and evaluation."""
    path = (
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-evaluation-repair-decision.json"
    )
    decision = json.loads(path.read_text(encoding="utf-8"))

    assert decision["status"] == (
        "reviewed-before-final-qualification-evaluation-repair"
    )
    assert decision["execution_authorized"] is True
    assert decision["compilation_authorized"] is True
    assert decision["evaluation_authorized"] is True
    for key in (
        "campaign_reexecution_authorized",
        "optimization_authorized",
        "rescoring_authorized",
        "science_or_gates_changed",
        "tuning_authorized",
        "cutover_authorized",
        "release_authorized",
    ):
        assert decision[key] is False
    assert decision["repair_identity_review"]["sha256"] == (
        "b69b2eaa4b7d00b12314e0a7d753c22843778111ac4f0d1214dc3e1a790e2305"
    )
    assert (
        file_sha256(_ROOT / decision["repair_identity_review"]["path"])
        == decision["repair_identity_review"]["sha256"]
    )
    assert decision["named_review"]["user_response"] == (
        "I approve, please continue."
    )
