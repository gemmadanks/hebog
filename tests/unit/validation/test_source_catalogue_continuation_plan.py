"""Portable exact-identity and no-write continuation preflight fixtures."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import canonical_sha256

sys.path.insert(0, str(Path(__file__).parents[3]))
admission: Any = importlib.import_module(
    "scripts.validation.source_catalogue_continuation_plan"
)
identity: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
)


def _bound(path: Path, value: Any) -> dict[str, str]:
    _atomic_json(path, value)
    return identity.binding(path)


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    root = tmp_path / "code"
    root.mkdir()
    monkeypatch.setattr(
        admission.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=16 * 1024**3),
    )
    old_root = tmp_path / "original-code"
    old_root.mkdir()
    original = _bound(
        tmp_path / "old-plan.json",
        {
            "candidate": {"revision": "original"},
            "incumbent": {"revision": "incumbent"},
            "execution_root": str(old_root),
            "historical_root": str(tmp_path / "incumbent-code"),
            "scratch": str(tmp_path / "old-scratch"),
            "output": str(tmp_path / "evidence/terminal.json"),
            "runtime": {
                "python": "fixture",
                "dependency_inventory_sha256": "x",
            },
        },
    )
    audit_file = tmp_path / "audit.py"
    audit_file.write_text("# frozen audit\n")
    inventory = {
        "status": "verified-non-executable-inventory",
        "candidate": {"revision": "original"},
        "incumbent": {"revision": "incumbent"},
        "original_plan": original,
        "original_review": _bound(tmp_path / "old-review.json", {}),
        "repair_review": _bound(tmp_path / "repair.json", {}),
        "capture_pair_count": 2400,
        "reference_run_count": 9600,
        "retained_dask_comparison_count": 12,
        "complete_input_count": 808,
        "complete_finder_record_count": 4032,
        "pending_input_ids": [f"input-{i}" for i in range(1592)],
        "auditor_programs": [identity.binding(audit_file)],
    }
    inventory_binding = _bound(tmp_path / "evidence/inventory.json", inventory)
    review_binding = _bound(
        tmp_path / "inventory-review.json",
        {
            "status": "frozen-non-executable",
            "authorizations": {"evaluation_retry": False},
            "inventory": inventory_binding,
            "original_candidate": inventory["candidate"],
        },
    )
    monkeypatch.setattr(
        admission, "repository_revision", lambda _: "revision", raising=False
    )
    monkeypatch.setattr(
        admission, "source_tree_sha256", lambda _: "package", raising=False
    )
    monkeypatch.setattr(
        admission,
        "program_hashes",
        lambda _: {"audit.py": "digest"},
        raising=False,
    )
    plan = admission.build_plan(
        root, inventory_binding, review_binding, tmp_path / "new-scratch"
    )
    return plan, inventory, root


def test_freeze_records_evaluator_not_notebook_as_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, inventory, root = _fixture(tmp_path, monkeypatch)
    assert plan["candidate"] == inventory["candidate"]
    assert plan["evaluator_source_tree_sha256"] == "package"
    assert plan["execution_revision"] == "revision"
    assert plan["execution_root"] == str(root)
    assert plan["workers"] == 2
    assert plan["new_input_evaluations"] == 1592
    assert plan["reused_input_evaluations"] == 808
    assert plan["new_finder_executions"] == 0
    assert plan["status"] == "frozen-non-executable"
    assert not Path(plan["scratch"]).exists()
    assert not Path(plan["output"]).exists()


@pytest.mark.parametrize(
    "defect",
    (
        None,
        "root",
        "revision",
        "imports",
        "source",
        "program",
        "python",
        "dependencies",
        "threads",
    ),
)
def test_immutable_execution_rejects_code_import_or_runtime_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str | None
) -> None:
    plan, _, root = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(admission, "_ROOT", root)
    monkeypatch.setattr(
        admission.hebog, "__file__", str(root / "src/hebog/__init__.py")
    )
    monkeypatch.setattr(
        admission.platform, "python_version", lambda: "fixture"
    )
    monkeypatch.setattr(admission, "dependency_inventory_sha256", lambda: "x")
    for key in admission._THREAD_VARIABLES:
        monkeypatch.setenv(key, "1")
    fields = {
        "revision": "execution_revision",
        "source": "evaluator_source_tree_sha256",
        "program": "program_sha256",
    }
    if defect in fields:
        plan[fields[defect]] = "other"
    elif defect == "root":
        monkeypatch.setattr(admission, "_ROOT", tmp_path)
    elif defect == "imports":
        monkeypatch.setattr(
            admission.hebog, "__file__", str(tmp_path / "outside.py")
        )
    elif defect == "python":
        plan["runtime"]["python"] = "other"
    elif defect == "dependencies":
        plan["runtime"]["dependency_inventory_sha256"] = "other"
    elif defect == "threads":
        monkeypatch.delenv("NUMBA_NUM_THREADS")
    if defect is None:
        admission.verify_execution_code(plan)
    else:
        with pytest.raises(ValueError, match=r"changed"):
            admission.verify_execution_code(plan)


@pytest.mark.parametrize(
    "defect",
    (
        None,
        "old-scratch",
        "ancestor",
        "code",
        "inventory",
        "relative",
        "symlink",
        "output",
        "consumed",
        "disk",
    ),
)
def test_namespace_admission_preserves_evidence_and_rejects_duplicate_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str | None
) -> None:
    plan, inventory, _ = _fixture(tmp_path, monkeypatch)
    original = identity.read_bound(inventory["original_plan"])
    monkeypatch.setattr(
        admission.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=16 * 1024**3),
    )
    destinations = {
        "old-scratch": original["scratch"] + "/new",
        "ancestor": str(tmp_path),
        "code": original["execution_root"] + "/new",
        "inventory": str(Path(plan["inventory"]["path"]).parent / "new"),
        "relative": "relative",
    }
    if defect in destinations:
        plan["scratch"] = destinations[defect]
    elif defect == "symlink":
        path = tmp_path / "alias"
        path.symlink_to(tmp_path / "target")
        plan["scratch"] = str(path / "new")
    elif defect == "output":
        plan["output"] = str(tmp_path / "other.json")
    elif defect == "consumed":
        Path(plan["scratch"]).mkdir()
    elif defect == "disk":
        monkeypatch.setattr(
            admission.shutil, "disk_usage", lambda _: SimpleNamespace(free=0)
        )
    if defect is None:
        admission.verify_namespace(plan, original)
    else:
        with pytest.raises((ValueError, FileExistsError)):
            admission.verify_namespace(plan, original)


@pytest.mark.parametrize(
    "change", (None, "plan", "review", "count", "status", "execution")
)
def test_exact_authority_is_separate_from_consumed_replay(
    tmp_path: Path, change: str | None
) -> None:
    plan = _bound(tmp_path / "plan.json", {"frozen": True})
    review = _bound(
        tmp_path / "review.json",
        {"plan_sha256": plan["sha256"], "expected_execution_sha256": "exact"},
    )
    decision = {
        "status": "authorized-for-one-r6-evaluation-only-continuation",
        "execution_count": 1,
        "plan_sha256": plan["sha256"],
        "identity_review_sha256": review["sha256"],
        "expected_execution_sha256": "exact",
    }
    if change == "plan":
        decision["plan_sha256"] = "other"
    elif change == "review":
        decision["identity_review_sha256"] = "other"
    elif change == "count":
        decision["execution_count"] = True
    elif change == "status":
        decision["status"] = (
            "authorized-for-one-source-catalogue-cumulative-replay"
        )
    elif change == "execution":
        decision["expected_execution_sha256"] = "other"
    authority = _bound(tmp_path / "decision.json", decision)
    if change is None:
        admission.verify_authorization(plan, review, authority)
    else:
        with pytest.raises(PermissionError, match="one-use"):
            admission.verify_authorization(plan, review, authority)


@pytest.mark.parametrize("changed", (False, True))
def test_preflight_repeats_full_inventory_without_scoring_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: bool
) -> None:
    plan, inventory, root = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(admission, "verify_execution_code", lambda _: None)
    monkeypatch.setattr(
        admission, "verify_namespace", lambda *_: None, raising=False
    )
    review = _bound(
        tmp_path / "continuation-review.json",
        {
            "status": "frozen-non-executable",
            "authorizations": {"evaluation_retry": False},
            "expected_execution_sha256": canonical_sha256(plan),
            "plan_canonical_sha256": canonical_sha256(plan),
        },
    )
    calls = []

    def audit(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return {**inventory, "complete_input_count": 0 if changed else 808}

    monkeypatch.setattr(
        admission, "audit_retained_replay", audit, raising=False
    )
    if changed:
        with pytest.raises(ValueError, match="inventory"):
            admission.verify_preflight(plan, review)
    else:
        admission.verify_preflight(plan, review)
    assert len(calls) == 1
    assert calls[0][1] == {"repository_root": root}
    assert not Path(plan["scratch"]).exists()
    assert not Path(plan["output"]).exists()


def test_freeze_cli_publishes_only_non_executable_plan_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan, inventory, root = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(admission, "_ROOT", root)
    output = tmp_path / "frozen-plan.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze",
            "--inventory",
            plan["inventory"]["path"],
            "--inventory-sha256",
            plan["inventory"]["sha256"],
            "--inventory-review",
            plan["inventory_identity_review"]["path"],
            "--inventory-review-sha256",
            plan["inventory_identity_review"]["sha256"],
            "--scratch",
            plan["scratch"],
            "--output-plan",
            str(output),
        ],
    )
    admission.main()
    assert json.loads(output.read_bytes()) == plan
    assert json.loads(capsys.readouterr().out)[
        "expected_execution_sha256"
    ] == canonical_sha256(plan)
    assert not Path(plan["scratch"]).exists()
    assert identity.read_bound(plan["inventory"]) == inventory
    with pytest.raises(FileExistsError):
        admission.main()
    arguments = list(sys.argv)
    arguments[-1] = plan["output"]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(ValueError, match="preserved namespace"):
        admission.main()
    assert not Path(plan["output"]).exists()


def test_program_closure_hashes_nested_sources_and_rejects_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scripts/validation/nested/tool.py"
    source.parent.mkdir(parents=True)
    source.write_text("# fixture\n")
    assert admission.program_hashes(tmp_path) == {
        str(Path("scripts/validation/nested/tool.py")): identity.binding(
            source
        )["sha256"]
    }
    source.with_name("alias.py").symlink_to(source)
    with pytest.raises(ValueError, match="regular file"):
        admission.program_hashes(tmp_path)


@pytest.mark.parametrize(
    "module",
    (
        "scripts.validation.source_catalogue_continuation_plan",
        "scripts.validation.continue_source_catalogue_evaluation",
    ),
)
def test_module_cli_help_does_not_read_or_execute_campaign(
    monkeypatch: pytest.MonkeyPatch,
    module: str,
) -> None:
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    path = importlib.import_module(module).__file__
    assert path is not None
    with pytest.raises(SystemExit) as error:
        runpy.run_path(path, run_name="__main__")
    assert error.value.code == 0


@pytest.mark.parametrize(
    "defect",
    (
        "review-status",
        "review-authority",
        "review-inventory",
        "review-candidate",
        "candidate",
        "incumbent",
        "inventory-status",
        "count",
        "pending",
    ),
)
def test_freeze_rejects_unreviewed_inventory_and_changed_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
) -> None:
    plan, inventory, root = _fixture(tmp_path, monkeypatch)
    original = identity.read_bound(inventory["original_plan"])
    review = identity.read_bound(plan["inventory_identity_review"])
    if defect in {"candidate", "incumbent"}:
        original[defect] = {"revision": "not-the-original"}
    elif defect == "inventory-status":
        inventory["status"] = "unreviewed"
    elif defect == "count":
        inventory["complete_input_count"] = 807
    elif defect == "pending":
        inventory["pending_input_ids"].pop()
    inventory["original_plan"] = _bound(
        tmp_path / "changed-original.json", original
    )
    inventory_binding = _bound(tmp_path / "changed-inventory.json", inventory)
    review["inventory"] = inventory_binding
    changes = {
        "review-status": ("status", "executable"),
        "review-authority": ("authorizations", {"evaluation_retry": True}),
        "review-inventory": ("inventory", {"sha256": "wrong"}),
        "review-candidate": ("original_candidate", {"revision": "other"}),
    }
    if defect in changes:
        field, value = changes[defect]
        review[field] = value
    review_binding = _bound(tmp_path / "changed-review.json", review)
    with pytest.raises(ValueError, match="inventory review or census"):
        admission.build_plan(
            root, inventory_binding, review_binding, Path(plan["scratch"])
        )


@pytest.mark.parametrize(
    "defect",
    (
        "review-status",
        "review-authority",
        "execution",
        "canonical",
        "plan",
        "auditor-bytes",
        "auditor-identity",
        "auditor-location",
    ),
)
def test_preflight_rejects_drift_but_admits_identical_immutable_auditor_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
) -> None:
    plan, inventory, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(admission, "verify_execution_code", lambda _: None)
    if defect == "plan":
        plan["workers"] = 3
    review = {
        "status": "frozen-non-executable",
        "authorizations": {"evaluation_retry": False},
        "expected_execution_sha256": canonical_sha256(plan),
        "plan_canonical_sha256": canonical_sha256(plan),
    }
    fields = {
        "review-status": "status",
        "execution": "expected_execution_sha256",
        "canonical": "plan_canonical_sha256",
    }
    if defect in fields:
        review[fields[defect]] = "changed"
    elif defect == "review-authority":
        review["authorizations"] = {"evaluation_retry": True}

    def audit(*_: Any, **_kwargs: Any) -> Any:
        fresh = json.loads(json.dumps(inventory))
        if defect == "auditor-bytes":
            Path(inventory["auditor_programs"][0]["path"]).write_text(
                "changed"
            )
        elif defect == "auditor-identity":
            fresh["auditor_programs"][0]["sha256"] = "other"
        elif defect == "auditor-location":
            path = tmp_path / "new-checkout/audit.py"
            path.parent.mkdir()
            path.write_text("# frozen audit\n")
            fresh["auditor_programs"] = [identity.binding(path)]
        return fresh

    monkeypatch.setattr(admission, "audit_retained_replay", audit)
    review_binding = _bound(tmp_path / "new-review.json", review)
    if defect == "auditor-location":
        admission.verify_preflight(plan, review_binding)
    else:
        with pytest.raises(ValueError, match=r"changed|inventory"):
            admission.verify_preflight(plan, review_binding)
