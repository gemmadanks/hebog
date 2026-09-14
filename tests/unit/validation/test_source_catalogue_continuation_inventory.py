"""Synthetic-only admission checks for a no-rescoring R6 continuation."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownLambdaType=false

from __future__ import annotations

import importlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import canonical_sha256

inventory: Any = importlib.import_module(
    "scripts.validation.source_catalogue_continuation_inventory"
)
identity: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
)
audit: Any = importlib.import_module(
    "scripts.validation.audit_source_catalogue_continuation"
)


def _signed(record: dict[str, Any]) -> dict[str, Any]:
    return {**record, "record_sha256": canonical_sha256(record)}


def _pair(root: Path, identifier: str, lane: str = "compact-blend") -> Any:
    captures = {}
    finders = [
        "current-hebog",
        "incumbent-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
    ]
    if lane == "compact-blend":
        finders.append("aegean")
    for finder in finders:
        path = root / identifier / finder / "capture.json"
        _atomic_json(path, {"input_id": identifier})
        captures[finder] = identity.binding(path)
    return {
        "input_id": identifier,
        "lane": lane,
        "evaluation_directory": str(root / identifier / "evaluation"),
        "captures": captures,
    }


def _complete(pair: Any, **changes: Any) -> Path:
    directory = Path(pair["evaluation_directory"])
    records = []
    for finder, capture in pair["captures"].items():
        record = {
            "schema_version": 1,
            "input_id": pair["input_id"],
            "finder_id": finder,
            "lane": pair["lane"],
            "capture": capture,
        }
        if pair["lane"] == "continuum":
            record["source_diagnostics"] = _signed(
                {
                    "schema_version": 1,
                    "input_id": pair["input_id"],
                    "finder_id": finder,
                    "source_records": [{"support_label": 1}],
                }
            )
        record.update(changes)
        path = directory / f"{finder}.json"
        _atomic_json(path, _signed(record))
        records.append(identity.binding(path))
    marker = directory / "complete.json"
    _atomic_json(marker, {"input_id": pair["input_id"], "records": records})
    return marker


def test_completed_records_are_reused_byte_for_byte(tmp_path: Path) -> None:
    pairs = [
        _pair(tmp_path, "compact"),
        _pair(tmp_path, "extended", "continuum"),
    ]
    markers = [_complete(pair) for pair in pairs]
    before = {
        path: path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    result = inventory.collect_completed_evaluations(pairs)
    assert result["complete_input_count"] == 2
    assert result["complete_finder_record_count"] == 9
    assert result["pending_input_ids"] == []
    assert result["complete_markers"] == [
        identity.binding(path) for path in sorted(markers)
    ]
    assert result["complete_marker_set_sha256"] == canonical_sha256(
        result["complete_markers"]
    )
    assert {
        path: path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_missing_and_partial_directories_are_not_completed(
    tmp_path: Path,
) -> None:
    pairs = [_pair(tmp_path, "absent"), _pair(tmp_path, "partial")]
    partial = Path(pairs[1]["evaluation_directory"]) / "current-hebog.json"
    _atomic_json(partial, {"incomplete": True})
    result = inventory.collect_completed_evaluations(pairs)
    assert result["complete_input_count"] == 0
    assert result["pending_input_ids"] == ["absent", "partial"]
    assert result["partial_files"] == [identity.binding(partial)]


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"lane": "continuum"},
        {"input_id": "other"},
        {"finder_id": "other"},
        {"capture": {"path": "other", "sha256": "0" * 64}},
    ],
)
def test_mismatched_completed_record_blocks_reuse(
    tmp_path: Path, changes: Any
) -> None:
    pair = _pair(tmp_path, "fixture")
    _complete(pair, **changes)
    with pytest.raises(ValueError, match=r"identity|census|schema"):
        inventory.collect_completed_evaluations([pair])


def test_corrupt_completed_record_is_not_reclassified_pending(
    tmp_path: Path,
) -> None:
    pair = _pair(tmp_path, "fixture")
    _complete(pair)
    path = Path(pair["evaluation_directory"]) / "current-hebog.json"
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match=r"changed|bytes"):
        inventory.collect_completed_evaluations([pair])


def _native(path: Path, **metadata: Any) -> dict[str, str]:
    payload = path.parent / "native.json"
    _atomic_json(payload, {"payload": True})
    artifact = {
        "role": "image",
        "relative_path": payload.name,
        "sha256": identity.binding(payload)["sha256"],
        "byte_count": payload.stat().st_size,
    }
    _atomic_json(path, {**metadata, "artifacts": [artifact]})
    return identity.binding(path)


def _captured_fixture(root: Path) -> Any:
    scratch = root / "scratch"
    directory = scratch / "pairs" / "fixture"
    current_dir = directory / "current"
    _atomic_json(current_dir / "plane.json", {"plane": True})
    product = current_dir / "plane.json"
    artifact = {
        "path": product.name,
        "sha256": identity.binding(product)["sha256"],
        "byte_count": product.stat().st_size,
    }
    input_binding = _native(root / "input" / "input.json")
    input_record = identity.read_bound(input_binding)
    current = _signed(
        {
            "schema_version": 1,
            "input_id": "fixture",
            "finder_id": "current-hebog",
            "configuration_sha256": "config",
            "input_sha256": input_record["artifacts"][0]["sha256"],
            "planes": {"publication": artifact},
            "catalogues": {"sources": artifact},
        }
    )
    _atomic_json(current_dir / "capture.json", current)
    incumbent = _native(
        directory / "incumbent" / "complete.json",
        input_id="fixture",
        configuration_sha256="incumbent-config",
        source_tree_sha256="incumbent-source",
    )
    task = {
        "input_id": "fixture",
        "lane": "continuum",
        "input_manifest": input_binding,
        "output_directory": str(directory),
        "captures": {},
    }
    plan = {
        "tasks": [task],
        "scratch": str(scratch),
        "candidate": {"configuration_sha256": "config"},
        "incumbent": {
            "configuration_sha256": "incumbent-config",
            "source_tree_sha256": "incumbent-source",
        },
        "execution_revision": "original-revision",
        "dask_input_ids": ["fixture"],
    }
    _atomic_json(root / "plan.json", plan)
    plan_binding = identity.binding(root / "plan.json")
    pair = {
        **task,
        "evaluation_directory": str(directory / "evaluation"),
        "captures": {
            "current-hebog": identity.binding(current_dir / "capture.json"),
            "incumbent-hebog": incumbent,
        },
    }
    _atomic_json(directory / "pair.json", pair)
    pairs = [identity.binding(directory / "pair.json")]
    _atomic_json(
        scratch / "capture-seal.json",
        {
            "pairs": pairs,
            "pair_set_sha256": canonical_sha256(pairs),
            "launch": {
                "plan": plan_binding,
                "execution_revision": "original-revision",
            },
        },
    )
    return (
        plan,
        plan_binding,
        identity.binding(scratch / "capture-seal.json"),
        pair,
    )


def test_sealed_native_captures_are_hash_verified_without_execution(
    tmp_path: Path,
) -> None:
    plan, plan_binding, seal, pair = _captured_fixture(tmp_path)
    assert inventory.verify_capture_seal(plan, plan_binding, seal) == [pair]
    product = (
        Path(pair["captures"]["current-hebog"]["path"]).parent / "plane.json"
    )
    product.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="artifact"):
        inventory.verify_capture_seal(plan, plan_binding, seal)


@pytest.mark.parametrize(
    "defect",
    [
        "set-digest",
        "launch",
        "census",
        "pair-path",
        "pair-task",
        "current-config",
        "incumbent-source",
    ],
)
def test_capture_substitution_blocks_admission(
    tmp_path: Path, defect: str
) -> None:
    plan, plan_binding, seal_binding, pair = _captured_fixture(tmp_path)
    seal = identity.read_bound(seal_binding)
    if defect == "set-digest":
        seal["pair_set_sha256"] = "wrong"
    elif defect == "launch":
        seal["launch"]["plan"] = {"path": "wrong", "sha256": "wrong"}
    elif defect == "census":
        seal["pairs"] *= 2
    else:
        if defect == "pair-path":
            path = tmp_path / "outside-pair.json"
            _atomic_json(path, pair)
        else:
            path = Path(seal["pairs"][0]["path"])
            if defect == "pair-task":
                pair["lane"] = "compact-blend"
            else:
                finder = (
                    "current-hebog"
                    if defect == "current-config"
                    else "incumbent-hebog"
                )
                capture_path = Path(pair["captures"][finder]["path"])
                record = json.loads(capture_path.read_bytes())
                record[
                    "configuration_sha256"
                    if finder == "current-hebog"
                    else "source_tree_sha256"
                ] = "wrong"
                if finder == "current-hebog":
                    record = _signed(
                        {
                            k: v
                            for k, v in record.items()
                            if k != "record_sha256"
                        }
                    )
                capture_path.write_text(json.dumps(record))
                pair["captures"][finder] = identity.binding(capture_path)
            path.write_text(json.dumps(pair))
        seal["pairs"] = [identity.binding(path)]
    if defect != "set-digest":
        seal["pair_set_sha256"] = canonical_sha256(seal["pairs"])
    Path(seal_binding["path"]).write_text(json.dumps(seal))
    with pytest.raises(ValueError, match=r"changed|census|identity"):
        inventory.verify_capture_seal(
            plan, plan_binding, identity.binding(Path(seal_binding["path"]))
        )


def test_retained_dask_recomputes_hashes_not_finders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, _, _, pair = _captured_fixture(tmp_path)
    calls = []

    def science_hash(path: Path) -> str:
        calls.append(path)
        return "s" * 64

    # The hash seam reads retained bytes; no executor is created by admission.
    monkeypatch.setattr(
        inventory, "capture_science_sha256", science_hash, raising=False
    )
    path = tmp_path / "dask.json"
    record = {
        "comparisons": [
            {
                "input_id": "fixture",
                "pass": True,
                "serial_science_sha256": "s" * 64,
                "dask_science_sha256": "s" * 64,
                "capture": pair["captures"]["current-hebog"],
            }
        ]
    }
    _atomic_json(path, record)
    inventory.verify_retained_dask(plan, [pair], identity.binding(path))
    assert len(calls) == 2
    record["comparisons"][0]["dask_science_sha256"] = "wrong"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Dask"):
        inventory.verify_retained_dask(plan, [pair], identity.binding(path))


def test_exhaustive_audit_refuses_a_substituted_original_plan(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plan.json"
    _atomic_json(path, {"plan": "original"})
    original = identity.binding(path)
    path.write_text('{"plan":"different"}')
    with pytest.raises(ValueError, match="changed"):
        audit.audit_retained_replay(original, {}, {}, tmp_path)


def _provenance_fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    historical = root / "historical"
    historical.mkdir()
    current = root / "current"
    current.mkdir()
    programs = {}
    for name in (
        "run_source_catalogue_cumulative_replay.py",
        "source_catalogue_campaign_evidence.py",
    ):
        relative = "scripts/validation/" + name
        for directory in (historical, current):
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('"""Inert fixture program."""\n')
        programs[relative] = identity.binding(historical / relative)["sha256"]
    metadata_path = historical / "config.py"
    metadata_path.write_text("FROZEN_VALUE = 1\n")
    candidate = {
        "revision": "original",
        "source_tree_sha256": "original-source",
        "configuration_sha256": canonical_sha256({}),
    }
    plan = {
        "execution_root": str(historical),
        "execution_revision": "original",
        "candidate": candidate,
        "configuration": {},
        "metadata": {"config.py": identity.binding(metadata_path)},
        "runtime": {
            "python": "fixture",
            "dependency_inventory_sha256": "fixture-deps",
        },
    }
    review = {
        "execution": {"candidate": candidate},
        "program_sha256": programs,
    }
    repair = {
        "status": "frozen-non-executable",
        "authorizations": {"retry": False},
        "retained_candidate": candidate.copy(),
        "implementation_file_sha256": programs.copy(),
    }
    monkeypatch.setattr(
        identity, "repository_revision", lambda _root: "original"
    )
    monkeypatch.setattr(
        audit, "source_tree_sha256", lambda _root: "original-source"
    )
    monkeypatch.setattr(audit.platform, "python_version", lambda: "fixture")
    monkeypatch.setattr(
        audit, "dependency_inventory_sha256", lambda: "fixture-deps"
    )
    monkeypatch.setattr(identity, "EXPECTED_FILES", {})
    return plan, review, repair, current


def test_provenance_metadata_need_not_be_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _provenance_fixture(tmp_path, monkeypatch)
    audit._verify_provenance(*fixture)


def test_external_evidence_uses_frozen_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, review, repair, root = _provenance_fixture(tmp_path, monkeypatch)
    external = tmp_path / "closed.json"
    _atomic_json(external, {"closed": True})
    relative = "benchmark-results/closed.json"
    plan["metadata"][relative] = identity.binding(external)
    plan["metadata"]["logical-file-name.json"] = identity.binding(external)
    monkeypatch.setattr(
        identity,
        "EXPECTED_FILES",
        {relative: identity.binding(external)["sha256"]},
    )
    audit._verify_provenance(plan, review, repair, root)


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate-pair",
        "directory-link",
        "directory-file",
        "marker-input",
        "outside-record",
        "boolean-schema",
        "diagnostic-digest",
        "diagnostic-schema",
        "diagnostic-finder",
        "diagnostic-input",
        "unavailable-support",
        "zero-support",
    ],
)
def test_reuse_rejects_invalid_namespaces_and_historical_schemas(
    tmp_path: Path, defect: str
) -> None:
    pair = _pair(tmp_path, "fixture", "continuum")
    directory = Path(pair["evaluation_directory"])
    if defect == "duplicate-pair":
        with pytest.raises(ValueError, match="duplicated"):
            inventory.collect_completed_evaluations([pair, pair])
        return
    if defect == "directory-link":
        target = tmp_path / "target"
        target.mkdir()
        directory.symlink_to(target, target_is_directory=True)
    elif defect == "directory-file":
        directory.write_text("not a directory")
    else:
        marker = _complete(pair)
        completed = json.loads(marker.read_bytes())
        path = Path(completed["records"][0]["path"])
        record = json.loads(path.read_bytes())
        if defect == "marker-input":
            completed["input_id"] = "different"
        elif defect == "outside-record":
            outside = tmp_path / "outside.json"
            outside.write_bytes(path.read_bytes())
            completed["records"][0] = identity.binding(outside)
        else:
            diagnostic = record["source_diagnostics"]
            if defect == "boolean-schema":
                record["schema_version"] = True
            elif defect in {
                "diagnostic-schema",
                "diagnostic-finder",
                "diagnostic-input",
            }:
                key, value = {
                    "diagnostic-schema": ("schema_version", 2),
                    "diagnostic-finder": ("finder_id", "other"),
                    "diagnostic-input": ("input_id", "other"),
                }[defect]
                diagnostic[key] = value
            elif defect in {"unavailable-support", "zero-support"}:
                diagnostic["source_records"][0]["support_label"] = (
                    None if defect == "unavailable-support" else 0
                )
            if defect == "diagnostic-digest":
                diagnostic["record_sha256"] = "wrong"
            else:
                record["source_diagnostics"] = _signed(
                    {
                        key: value
                        for key, value in diagnostic.items()
                        if key != "record_sha256"
                    }
                )
            path.write_text(
                json.dumps(
                    _signed(
                        {
                            key: value
                            for key, value in record.items()
                            if key != "record_sha256"
                        }
                    )
                )
            )
            completed["records"][0] = identity.binding(path)
        marker.write_text(json.dumps(completed))
    with pytest.raises(ValueError):
        inventory.collect_completed_evaluations([pair])


@pytest.mark.parametrize(
    "defect",
    [
        "candidate",
        "authorization",
        "runtime",
        "python",
        "old-program",
        "repair-program",
        "late-engine",
        "metadata",
        "closed-evidence",
    ],
)
def test_provenance_rejects_candidate_and_evaluator_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    plan, review, repair, root = _provenance_fixture(tmp_path, monkeypatch)
    relative = next(iter(review["program_sha256"]))
    if defect == "candidate":
        repair["retained_candidate"]["revision"] = "new-notebook"
    elif defect == "authorization":
        repair["authorizations"]["retry"] = True
    elif defect == "runtime":
        plan["runtime"]["dependency_inventory_sha256"] = "wrong"
    elif defect == "python":
        plan["runtime"]["python"] = "wrong"
    elif defect == "old-program":
        (Path(plan["execution_root"]) / relative).write_text("changed")
    elif defect == "repair-program":
        (root / relative).write_text("changed")
    elif defect == "late-engine":
        repair["implementation_file_sha256"] = {}
        (root / relative).write_text("changed")
    elif defect == "metadata":
        plan["metadata"]["config.py"]["sha256"] = "wrong"
    else:
        monkeypatch.setattr(identity, "EXPECTED_FILES", {"config.py": "wrong"})
    with pytest.raises(ValueError, match="changed"):
        audit._verify_provenance(plan, review, repair, root)


def _audit_fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    plan, _, seal_binding, pair = _captured_fixture(root)
    plan.update(
        metadata={
            identity.REQUEST: pair["input_manifest"],
            identity.REFERENCE + "/recovery.json": pair["input_manifest"],
        },
        execution_root=str(root / "original"),
        historical_root=str(root / "incumbent"),
        retained_references={"reference": pair["captures"]["incumbent-hebog"]},
        output=str(root / "terminal.json"),
    )
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan))
    plan_binding = identity.binding(plan_path)
    review_path = root / "review.json"
    review = {
        "plan_sha256": plan_binding["sha256"],
        "plan_canonical_sha256": canonical_sha256(plan),
        "expected_execution_sha256": "expected",
    }
    _atomic_json(review_path, review)
    review_binding = identity.binding(review_path)
    authority = {
        "plan_sha256": plan_binding["sha256"],
        "identity_review_sha256": review_binding["sha256"],
        "expected_execution_sha256": "expected",
    }
    _atomic_json(root / "authority.json", authority)
    seal = identity.read_bound(seal_binding)
    seal["launch"].update(
        plan=plan_binding,
        authorization=identity.binding(root / "authority.json"),
    )
    Path(seal_binding["path"]).write_text(json.dumps(seal))
    _atomic_json(
        Path(plan["scratch"]) / "process-failure.json",
        {"stage": "evaluation", "launch": seal["launch"]},
    )
    _complete(pair)
    complete = inventory.collect_completed_evaluations([pair])
    dask_path = Path(plan["scratch"]) / "dask-comparisons.json"
    _atomic_json(
        dask_path,
        {
            "comparisons": [
                {
                    "input_id": "fixture",
                    "pass": True,
                    "serial_science_sha256": "s",
                    "dask_science_sha256": "s",
                    "capture": pair["captures"]["current-hebog"],
                }
            ]
        },
    )
    repair_path = root / "repair.json"
    _atomic_json(
        repair_path,
        {
            "expected_retained_evidence": {
                "capture_seal_sha256": identity.binding(
                    Path(seal_binding["path"])
                )["sha256"],
                "dask_comparisons_sha256": identity.binding(dask_path)[
                    "sha256"
                ],
                **{
                    key: complete[key]
                    for key in (
                        "complete_input_count",
                        "complete_finder_record_count",
                        "complete_marker_set_sha256",
                    )
                },
            }
        },
    )
    calls = []
    monkeypatch.setattr(
        audit, "_verify_provenance", lambda *_args: calls.append("provenance")
    )
    for name in (
        "verify_census",
        "verify_task_metadata",
        "verify_historical_producer",
        "verify_reference_identities",
    ):
        monkeypatch.setattr(
            identity, name, lambda *_args, name=name: calls.append(name)
        )
    monkeypatch.setattr(inventory, "capture_science_sha256", lambda _path: "s")
    return plan_binding, review_binding, identity.binding(repair_path), calls


def test_full_inventory_is_non_executable_and_preserves_original_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, review, repair, calls = _audit_fixture(tmp_path, monkeypatch)
    before = {
        path: path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    result = audit.audit_retained_replay(plan, review, repair, tmp_path)
    assert calls == [
        "provenance",
        "verify_census",
        "verify_task_metadata",
        "verify_historical_producer",
        "verify_reference_identities",
    ]
    assert result["status"] == "verified-non-executable-inventory"
    assert result["candidate"] == identity.read_bound(plan)["candidate"]
    assert result["capture_pair_count"] == 1
    assert result["reference_run_count"] == 1
    assert result["retained_dask_comparison_count"] == 1
    assert result["complete_input_count"] == 1
    assert result["retry_authorized"] is False
    assert (
        result["new_finder_executions"]
        == result["new_dask_comparisons"]
        == result["new_evaluations"]
        == 0
    )
    assert {
        path: path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize(
    "defect", ["review-plan", "failure", "terminal", "count"]
)
def test_full_inventory_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    plan, review, repair, _ = _audit_fixture(tmp_path, monkeypatch)
    if defect == "review-plan":
        path = Path(review["path"])
        record = identity.read_bound(review)
        record["plan_sha256"] = "wrong"
        path.write_text(json.dumps(record))
        review = identity.binding(path)
    elif defect == "failure":
        path = (
            Path(identity.read_bound(plan)["scratch"]) / "process-failure.json"
        )
        record = json.loads(path.read_bytes())
        record["stage"] = "capture"
        path.write_text(json.dumps(record))
    elif defect == "terminal":
        Path(identity.read_bound(plan)["output"]).write_text("closed")
    else:
        path = Path(repair["path"])
        record = identity.read_bound(repair)
        record["expected_retained_evidence"]["complete_input_count"] = 2
        path.write_text(json.dumps(record))
        repair = identity.binding(path)
    with pytest.raises((ValueError, FileExistsError)):
        audit.audit_retained_replay(plan, review, repair, tmp_path)


@pytest.mark.parametrize(
    "destination", ["none", "separate", "scratch", "terminal"]
)
def test_cli_has_no_execution_option_and_only_writes_separate_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    destination: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan, review, repair, _ = _audit_fixture(tmp_path, monkeypatch)
    argv = ["audit"]
    for name, value in (
        ("plan", plan),
        ("original-review", review),
        ("repair-review", repair),
    ):
        argv.extend(
            [
                "--" + name,
                value["path"],
                "--" + name + "-sha256",
                value["sha256"],
            ]
        )
    output = tmp_path / "inventory.json"
    if destination == "scratch":
        output = Path(identity.read_bound(plan)["scratch"]) / "inventory.json"
    elif destination == "terminal":
        output = Path(identity.read_bound(plan)["output"])
    if destination != "none":
        argv.extend(["--inventory", str(output)])
    monkeypatch.setattr(sys, "argv", argv)
    if destination in {"scratch", "terminal"}:
        with pytest.raises(ValueError, match="namespace"):
            audit.main()
        assert not output.exists()
    else:
        audit.main()
        assert (
            json.loads(capsys.readouterr().out)["evaluation_started"] is False
        )
        assert output.exists() is (destination == "separate")
        if destination == "separate":
            with pytest.raises(FileExistsError):
                audit.main()


def test_empty_failed_directory_is_recorded_for_preservation(
    tmp_path: Path,
) -> None:
    pair = _pair(tmp_path, "fixture")
    directory = Path(pair["evaluation_directory"])
    directory.mkdir()
    result = inventory.collect_completed_evaluations([pair])
    assert result["partial_directories"] == [str(directory)]
    assert result["partial_files"] == []
    assert result["pending_input_ids"] == ["fixture"]


def test_capture_cannot_relocate_native_products(tmp_path: Path) -> None:
    plan, plan_binding, seal_binding, pair = _captured_fixture(tmp_path)
    seal = identity.read_bound(seal_binding)
    pair["captures"]["current-hebog"]["path"] = str(
        tmp_path / "different.json"
    )
    pair_path = Path(seal["pairs"][0]["path"])
    pair_path.write_text(json.dumps(pair))
    seal["pairs"] = [identity.binding(pair_path)]
    seal["pair_set_sha256"] = canonical_sha256(seal["pairs"])
    Path(seal_binding["path"]).write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="capture path"):
        inventory.verify_capture_seal(
            plan, plan_binding, identity.binding(Path(seal_binding["path"]))
        )


def test_duplicate_dask_comparison_does_not_replace_missing_input(
    tmp_path: Path,
) -> None:
    plan, _, _, pair = _captured_fixture(tmp_path)
    path = tmp_path / "dask.json"
    _atomic_json(
        path,
        {"comparisons": [{"input_id": "fixture"}, {"input_id": "fixture"}]},
    )
    with pytest.raises(ValueError, match="Dask census"):
        inventory.verify_retained_dask(plan, [pair], identity.binding(path))


def test_cli_entry_point_only_advertises_an_audit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["audit", "--help"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(audit.__file__, run_name="__main__")
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "--inventory" in help_text
    assert "--execute" not in help_text


def test_audit_does_not_bind_new_program_bytes_after_it_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, review, repair, _ = _audit_fixture(tmp_path, monkeypatch)
    collect = audit.collect_completed_evaluations
    original_binding = identity.binding
    changed = False

    def substituted_binding(path: Path) -> Any:
        value = original_binding(path)
        if changed and path == Path(audit.__file__):
            return {**value, "sha256": "changed-during-audit"}
        return value

    def collect_then_edit(pairs: Any) -> Any:
        nonlocal changed
        result = collect(pairs)
        changed = True
        return result

    monkeypatch.setattr(identity, "binding", substituted_binding)
    monkeypatch.setattr(
        audit, "collect_completed_evaluations", collect_then_edit
    )
    with pytest.raises(ValueError, match="audit program"):
        audit.audit_retained_replay(plan, review, repair, tmp_path)
