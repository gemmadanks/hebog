"""Synthetic launch contracts must reject drift before any finder work."""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))
admission: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replacement_admission"
)
MINIMUM_BYTES = 74_710_430_800


def _write(path: Path, value: Any) -> dict[str, str]:
    path.write_text(json.dumps(value))
    return admission.binding(path)


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Small metadata only: no ignored campaign directories or finder."""
    root = tmp_path / "checkout"
    root.mkdir()
    candidate = {
        "revision": "a" * 40,
        "source_tree_sha256": "b" * 64,
        "configuration_sha256": admission.canonical_sha256({"fixture": 1}),
    }
    runtime = {
        "python": admission.platform.python_version(),
        "platform": admission.platform.platform(),
        "dependency_inventory_sha256": "c" * 64,
    }
    implementations = [
        {
            "identifier": finder,
            "role": "candidate" if finder == "current-hebog" else "reference",
            "execution_configuration_sha256": "d" * 64,
            "software": {
                "name": "hebog",
                "commit_sha": "e" * 40,
                "source_tree_sha256": "f" * 64,
                "dependency_inventory_sha256": "0" * 64,
            },
        }
        for finder in (
            "current-hebog",
            "incumbent-hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
            "aegean",
        )
    ]
    dask_ids = [f"i-{index}" for index in range(12)]
    original = {
        "implementations": implementations,
        "scratch": str(tmp_path / "old-products"),
        "execution_root": str(tmp_path / "old-checkout"),
        "historical_root": str(tmp_path / "old-history"),
        "dask_input_ids": dask_ids,
    }
    original_binding = _write(tmp_path / "original.json", original)
    inventory = _write(
        tmp_path / "inventory.json", {"original_plan": original_binding}
    )
    closed = _write(tmp_path / "closed.json", {"inventory": inventory})
    capture = _write(tmp_path / "capture.json", {})
    evaluation = _write(tmp_path / "evaluation.json", {"images": []})
    inputs = _write(tmp_path / "input.json", {"artifacts": []})
    document = tmp_path / "science.md"
    document.write_text("# Scientific contract, not JSON\n")
    review = _write(
        tmp_path / "candidate.json",
        {
            "algorithm_candidate": candidate,
            "scientific_composition_sha256": "1" * 64,
            "frozen_documents": {},
        },
    )
    cost = _write(tmp_path / "cost.json", {"fixture": "cost"})
    retained = [{"fixture": index} for index in range(8000)]
    tasks = [
        {
            "input_id": f"i-{index}",
            "lane": "compact-blend" if index < 800 else "continuum",
            "input_manifest": inputs,
        }
        for index in range(2400)
    ]
    snapshot = {
        "candidate": candidate,
        "incumbent": {"revision": "old"},
        "configuration": {"fixture": 1},
        "scientific_composition_sha256": "1" * 64,
        "tasks": tasks,
        "scratch": str(tmp_path / "new-products"),
        "execution_root": str(root),
        "output": str(root / "benchmark-results/decision.json"),
        "dask_input_ids": dask_ids,
        "existing_dask_comparisons": 12,
        "workers": 2,
        "candidate_serial_executions": 2400,
        "incumbent_executions": 0,
        "pybdsf_executions": 0,
        "aegean_executions": 0,
        "retained_references": {str(i): inputs for i in range(9600)},
        "metadata": {"document": admission.binding(document)},
        "bootstrap_resamples": 50000,
        "bootstrap_seed": 20260810,
        "retained_records": retained,
        "retained_record_set_sha256": admission.canonical_sha256(retained),
        "bindings": {
            "comparisons": 1187,
            "safety_checks": 5,
            "required_all_pass": True,
        },
        "runtime": runtime,
        "candidate_review": review,
        "closed_terminal": closed,
        "closed_capture_seal": capture,
        "closed_evaluation_seal": evaluation,
        "status": "prepared-not-execution-admitted",
        "authorizations": {"execution": False},
        "execution_identity": None,
        "cost_probe": cost,
        "admission": {"provisional_required_free_bytes": MINIMUM_BYTES},
    }
    preparation = _write(tmp_path / "preparation.json", snapshot)
    resource = {
        "status": "resource-admitted",
        "candidate": candidate,
        "preparation": preparation,
        "cost_probe": cost,
        "runtime": runtime,
        "required_free_bytes": MINIMUM_BYTES,
        "observed_free_bytes": MINIMUM_BYTES,
        "evidence": [cost],
    }
    resources = _write(tmp_path / "resources.json", resource)
    monkeypatch.setattr(admission, "PREPARATION_SHA256", preparation["sha256"])
    monkeypatch.setattr(
        admission, "repository_revision", Mock(return_value="rev")
    )
    monkeypatch.setattr(
        admission, "program_hashes", Mock(return_value={"p": "hash"})
    )
    return SimpleNamespace(
        root=root,
        snapshot=snapshot,
        resource=resource,
        preparation=preparation,
        resources=resources,
        original=original,
        tasks=tasks,
        retained=retained,
    )


def test_v15_preparation_binding_is_not_the_old_candidate() -> None:
    assert admission.PREPARATION_SHA256 == (
        "9bddfbabe37c69363e05afc8d29ccc11dbaed15a156c7406cc0146473b47134b"
    )


def test_plan_updates_only_current_software_and_detaches_metadata(
    prepared: Any,
) -> None:
    before = copy.deepcopy(prepared.original)
    plan = admission.build_plan(
        prepared.preparation, prepared.resources, prepared.root
    )
    assert plan["implementations"][1:] == before["implementations"][1:]
    current = plan["implementations"][0]
    assert current["software"]["dependency_inventory_sha256"] == "c" * 64
    assert current["software"]["commit_sha"] == "a" * 40
    assert plan["status"] == "frozen-non-executable"
    assert not any(plan["authorizations"].values())
    assert plan["execution_identity"] is None
    assert plan["cost_probe"] == prepared.snapshot["cost_probe"]
    assert plan["required_free_bytes"] == MINIMUM_BYTES
    assert plan["program_sha256"] == {"p": "hash"}
    plan["tasks"].clear()
    assert len(prepared.snapshot["tasks"]) == 2400
    assert prepared.original == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("required_free_bytes", 68 * 1024**3),
        ("required_free_bytes", float(MINIMUM_BYTES)),
        ("required_free_bytes", True),
        ("observed_free_bytes", MINIMUM_BYTES - 1),
        ("observed_free_bytes", float(MINIMUM_BYTES)),
        ("status", "not-admitted"),
        ("candidate", {}),
        ("preparation", {}),
        ("cost_probe", {}),
        ("runtime", {}),
        ("evidence", []),
    ],
)
def test_resource_record_cannot_weaken_the_new_budget(
    prepared: Any,
    field: str,
    value: Any,
) -> None:
    prepared.resource[field] = value
    changed = _write(Path(prepared.resources["path"]), prepared.resource)
    with pytest.raises(ValueError, match="resource"):
        admission.build_plan(prepared.preparation, changed, prepared.root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "authorized"),
        ("authorizations", {"execution": True}),
        ("execution_identity", "old"),
        ("workers", 1),
        ("candidate_serial_executions", 2399),
        ("existing_dask_comparisons", 11),
        ("incumbent_executions", 1),
        ("pybdsf_executions", 1),
        ("aegean_executions", 1),
        ("bootstrap_resamples", 100),
        ("bootstrap_seed", 1),
        ("bindings", {}),
        ("dask_input_ids", ["foreign"] * 12),
    ],
)
def test_preparation_retains_full_non_executable_scientific_contract(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    prepared.snapshot[field] = value
    changed = _write(Path(prepared.preparation["path"]), prepared.snapshot)
    monkeypatch.setattr(admission, "PREPARATION_SHA256", changed["sha256"])
    prepared.resource["preparation"] = changed
    resources = _write(Path(prepared.resources["path"]), prepared.resource)
    with pytest.raises(ValueError, match=r"preparation|census|contract"):
        admission.build_plan(changed, resources, prepared.root)


def _audit_fixture(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], list[str]]:
    plan = admission.build_plan(
        prepared.preparation, prepared.resources, prepared.root
    )
    calls: list[str] = []

    def code(*_args: Any) -> None:
        calls.append("code")

    def artifact(*_args: Any) -> None:
        calls.append("artifact")

    monkeypatch.setattr(admission, "verify_execution_code", code)
    monkeypatch.setattr(admission, "native_artifacts", artifact)
    monkeypatch.setattr(
        admission, "verify_capture_seal", Mock(return_value=prepared.tasks)
    )
    monkeypatch.setattr(
        admission, "retained_inventory", Mock(return_value=prepared.retained)
    )
    monkeypatch.setattr(
        admission, "replacement_tasks", Mock(return_value=prepared.tasks)
    )
    monkeypatch.setattr(
        admission.shutil,
        "disk_usage",
        Mock(return_value=SimpleNamespace(free=MINIMUM_BYTES)),
    )
    return plan, calls


def test_exhaustive_preflight_hashes_markdown_without_parsing_it(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, calls = _audit_fixture(prepared, monkeypatch)
    before = sorted(str(path) for path in prepared.root.parent.rglob("*"))
    admission.verify_preflight(plan, prepared.root)
    assert calls.count("artifact") == 9600 + 2400
    assert calls.count("code") == 2
    assert (
        sorted(str(path) for path in prepared.root.parent.rglob("*")) == before
    )
    assert not Path(plan["scratch"]).exists()


@pytest.mark.parametrize("late", (False, True))
def test_preflight_rechecks_free_space_after_exhaustive_reads(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
    late: bool,
) -> None:
    plan, calls = _audit_fixture(prepared, monkeypatch)
    spaces = (
        [MINIMUM_BYTES, MINIMUM_BYTES - 1] if late else [MINIMUM_BYTES - 1]
    )
    monkeypatch.setattr(
        admission.shutil,
        "disk_usage",
        Mock(side_effect=[SimpleNamespace(free=value) for value in spaces]),
    )
    with pytest.raises(ValueError, match="disk"):
        admission.verify_preflight(plan, prepared.root)
    assert calls.count("artifact") == (12000 if late else 0)


@pytest.mark.parametrize("target", ("capture", "retained", "tasks"))
def test_preflight_rejects_incomplete_authenticated_censuses(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    plan, _ = _audit_fixture(prepared, monkeypatch)
    name, result = {
        "capture": ("verify_capture_seal", prepared.tasks[:-1]),
        "retained": ("retained_inventory", prepared.retained[:-1]),
        "tasks": ("replacement_tasks", prepared.tasks[:-1]),
    }[target]
    monkeypatch.setattr(admission, name, Mock(return_value=result))
    with pytest.raises(ValueError, match=r"census|inventory"):
        admission.verify_preflight(plan, prepared.root)


def _rebind(prepared: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    prepared.preparation = _write(
        Path(prepared.preparation["path"]), prepared.snapshot
    )
    monkeypatch.setattr(
        admission, "PREPARATION_SHA256", prepared.preparation["sha256"]
    )
    prepared.resource["preparation"] = prepared.preparation
    prepared.resources = _write(
        Path(prepared.resources["path"]), prepared.resource
    )


@pytest.mark.parametrize(
    "changed",
    (
        "preparation",
        "resource-evidence",
        "dask-selection",
        "metadata",
        "candidate",
        "configuration",
        "composition",
        "document",
        "record-digest",
    ),
)
def test_exhaustive_admission_rejects_each_identity_boundary(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    if changed == "preparation":
        prepared.preparation["sha256"] = "0" * 64
    elif changed == "resource-evidence":
        prepared.resource["evidence"].append(
            {**prepared.snapshot["metadata"]["document"], "sha256": "0" * 64}
        )
    elif changed == "dask-selection":
        prepared.snapshot["dask_input_ids"] = [f"i-{i}" for i in range(12, 24)]
    elif changed in {"candidate", "composition", "document"}:
        review = admission.read_bound(prepared.snapshot["candidate_review"])
        if changed == "document":
            path = prepared.root / "frozen.md"
            path.write_text("changed")
        review.update(
            {
                "candidate": {"algorithm_candidate": {}},
                "composition": {"scientific_composition_sha256": "0" * 64},
                "document": {
                    "frozen_documents": {
                        "doc": {"path": "frozen.md", "sha256": "0" * 64}
                    }
                },
            }[changed]
        )
        prepared.snapshot["candidate_review"] = _write(
            Path(prepared.snapshot["candidate_review"]["path"]), review
        )
    elif changed == "configuration":
        prepared.snapshot["configuration"] = {"changed": 1}
    elif changed == "record-digest":
        prepared.snapshot["retained_record_set_sha256"] = "0" * 64
    if changed != "preparation":
        _rebind(prepared, monkeypatch)
    with pytest.raises(ValueError, match=r"changed|contract"):
        plan, _ = _audit_fixture(prepared, monkeypatch)
        if changed == "metadata":
            Path(plan["metadata"]["document"]["path"]).write_text("changed")
        admission.verify_preflight(plan, prepared.root)


def test_preflight_rejects_modified_plan(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _ = _audit_fixture(prepared, monkeypatch)
    plan["bootstrap_seed"] = 1
    with pytest.raises(ValueError, match="frozen plan changed"):
        admission.verify_preflight(plan, prepared.root)


def test_scientific_document_can_be_plain_text_and_remains_unchanged(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = prepared.root / "contract.md"
    path.write_text("# Frozen scientific document\n")
    review = admission.read_bound(prepared.snapshot["candidate_review"])
    review["frozen_documents"] = {
        "doc": {
            "path": "contract.md",
            "sha256": admission.binding(path)["sha256"],
        }
    }
    prepared.snapshot["candidate_review"] = _write(
        Path(prepared.snapshot["candidate_review"]["path"]), review
    )
    _rebind(prepared, monkeypatch)
    plan, _ = _audit_fixture(prepared, monkeypatch)
    admission.verify_preflight(plan, prepared.root)
    assert path.read_text() == "# Frozen scientific document\n"


@pytest.mark.parametrize(
    "changed",
    (
        "tasks",
        "duplicate",
        "lane",
        "references",
        "records",
        "dask-count",
        "dask-duplicate",
        "boolean-count",
    ),
)
def test_population_cannot_be_truncated_or_duplicated(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    snapshot = prepared.snapshot
    if changed == "tasks":
        snapshot["tasks"].pop()
    elif changed == "duplicate":
        snapshot["tasks"][1] = snapshot["tasks"][0]
    elif changed == "lane":
        snapshot["tasks"][0]["lane"] = "continuum"
    elif changed == "references":
        snapshot["retained_references"].pop("0")
    elif changed == "records":
        snapshot["retained_records"].pop()
    elif changed == "dask-count":
        snapshot["dask_input_ids"].pop()
    elif changed == "dask-duplicate":
        snapshot["dask_input_ids"][1] = snapshot["dask_input_ids"][0]
    else:
        snapshot["incumbent_executions"] = False
    _rebind(prepared, monkeypatch)
    with pytest.raises(ValueError, match="census"):
        admission.build_plan(
            prepared.preparation, prepared.resources, prepared.root
        )


@pytest.mark.parametrize("changed", ("code", "namespace", "input"))
def test_late_audit_drift_prevents_launch(
    prepared: Any,
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    plan, calls = _audit_fixture(prepared, monkeypatch)
    if changed == "code":

        def code(*_args: Any) -> None:
            if "code" in calls:
                raise ValueError("code changed during audit")
            calls.append("code")

        monkeypatch.setattr(admission, "verify_execution_code", code)
    elif changed == "namespace":

        def retained(*_args: Any) -> Any:
            Path(plan["scratch"]).mkdir()
            return prepared.retained

        monkeypatch.setattr(admission, "retained_inventory", retained)
    else:

        def broken_input(*_args: Any) -> None:
            raise ValueError("input artifact changed")

        monkeypatch.setattr(admission, "native_artifacts", broken_input)
    with pytest.raises((ValueError, FileExistsError)):
        admission.verify_preflight(plan, prepared.root)
    assert not Path(plan["output"]).exists()
