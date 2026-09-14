"""Synthetic-only R6 continuation, preservation and late-failure contracts."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import canonical_sha256

sys.path.insert(0, str(Path(__file__).parents[3]))

runner: Any = importlib.import_module(
    "scripts.validation.continue_source_catalogue_evaluation"
)
retention: Any = importlib.import_module(
    "scripts.validation.source_catalogue_continuation_inventory"
)
identity: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
)


def _complete(pair: Any, schema: int = 1) -> dict[str, Any]:
    entries = []
    for finder, capture in pair["captures"].items():
        diagnostic = {
            "schema_version": schema,
            "input_id": pair["input_id"],
            "finder_id": finder,
            "source_records": [{"support_label": None if schema == 2 else 1}],
        }
        diagnostic["record_sha256"] = canonical_sha256(diagnostic)
        record = {
            "schema_version": 1,
            "input_id": pair["input_id"],
            "finder_id": finder,
            "lane": pair["lane"],
            "capture": capture,
            "source_diagnostics": diagnostic,
        }
        record["record_sha256"] = canonical_sha256(record)
        path = Path(pair["evaluation_directory"]) / f"{finder}.json"
        _atomic_json(path, record)
        entries.append(identity.binding(path))
    result = {"input_id": pair["input_id"], "records": entries}
    _atomic_json(Path(pair["evaluation_directory"]) / "complete.json", result)
    return result


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    original = tmp_path / "original"
    pairs = []
    bindings = []
    for identifier in ("done", "missing", "partial"):
        capture = original / identifier / "capture.json"
        _atomic_json(capture, {"native": identifier})
        pair = {
            "input_id": identifier,
            "root": str(original),
            "lane": "continuum",
            "captures": {"current-hebog": identity.binding(capture)},
            "evaluation_directory": str(original / identifier / "evaluation"),
        }
        path = original / identifier / "pair.json"
        _atomic_json(path, pair)
        bindings.append(identity.binding(path))
        pairs.append(pair)
    _complete(pairs[0])
    Path(pairs[2]["evaluation_directory"]).mkdir()
    inventory = retention.collect_completed_evaluations(pairs)
    seal = original / "capture-seal.json"
    _atomic_json(seal, {"pairs": bindings})
    dask = original / "dask.json"
    _atomic_json(dask, {"comparisons": [{"pass": True}]})
    old_plan = original / "plan.json"
    _atomic_json(
        old_plan,
        {"candidate": {"revision": "original"}, "incumbent": {}},
    )
    inventory.update(
        capture_seal=identity.binding(seal),
        dask_comparisons=identity.binding(dask),
        original_plan=identity.binding(old_plan),
        capture_pair_count=3,
        retained_dask_comparison_count=1,
    )
    path = tmp_path / "inventory.json"
    _atomic_json(path, inventory)
    return {
        "inventory": identity.binding(path),
        "scratch": str(tmp_path / "continuation"),
        "output": str(tmp_path / "terminal.json"),
    }, inventory


def test_only_missing_tasks_are_dispatched_outside_original_scratch(
    tmp_path: Path,
) -> None:
    plan, inventory = _fixture(tmp_path)
    pairs, tasks = runner.prepare_evaluations(inventory, Path(plan["scratch"]))
    assert len(pairs) == 3
    assert [row["input_id"] for row in tasks] == ["missing", "partial"]
    for task in tasks:
        original = next(
            pair for pair in pairs if pair["input_id"] == task["input_id"]
        )
        assert task == {
            **original,
            "evaluation_directory": str(
                Path(plan["scratch"]) / "evaluations" / task["input_id"]
            ),
        }
    assert not Path(plan["scratch"]).exists()


@pytest.mark.parametrize("change", ("pending", "completed", "marker"))
def test_reuse_changes_fail_instead_of_becoming_new_evaluation(
    tmp_path: Path, change: str
) -> None:
    plan, inventory = _fixture(tmp_path)
    if change == "pending":
        inventory["pending_input_ids"].append("done")
    elif change == "completed":
        inventory["completed_evaluations"] = []
    else:
        Path(inventory["complete_markers"][0]["path"]).write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        runner.prepare_evaluations(inventory, Path(plan["scratch"]))
    assert not Path(plan["scratch"]).exists()


@pytest.mark.parametrize("failure", (None, "evaluation", "aggregation"))
def test_durable_continuation_preserves_old_and_new_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    plan, inventory = _fixture(tmp_path)
    before = {
        path: path.read_bytes()
        for path in (tmp_path / "original").rglob("*")
        if path.is_file()
    }
    submitted = []

    def run_stage(stage: str, tasks: Any, worker: Any, progress: Any) -> Any:
        assert stage == "evaluation"
        assert worker is runner.evaluate_missing_pair
        submitted.extend(row["input_id"] for row in tasks)
        first = _complete(tasks[0], schema=2)
        if failure == "evaluation":
            raise RuntimeError("injected evaluation failure")
        progress.write("completed=2/2\n")
        return [_complete(tasks[1], schema=2), first]

    def aggregate(old_plan: Any, pairs: Any, rows: Any, dask: Any) -> Any:
        assert old_plan["candidate"]["revision"] == "original"
        assert len(pairs) == len(rows) == 3
        assert dask == [{"pass": True}]
        seal = json.loads(
            (Path(plan["scratch"]) / "evaluation-seal.json").read_bytes()
        )
        assert seal["images"] == rows
        assert seal["reused_input_count"] == 1
        assert seal["new_input_count"] == 2
        assert rows[0] == inventory["completed_evaluations"][0]
        if failure == "aggregation":
            raise RuntimeError("injected aggregation failure")
        # A completed scientific failure is a terminal, not a retry trigger.
        return {"status": "fail", "all_required_endpoints_pass": False}

    monkeypatch.setattr(runner, "_run_stage", run_stage, raising=False)
    monkeypatch.setattr(runner, "aggregate_records", aggregate, raising=False)
    monkeypatch.setattr(
        runner, "verify_execution_code", lambda *_: None, raising=False
    )
    if failure is None:
        result = runner.run_continuation(plan, {"fixture": True})
        assert result["result"]["status"] == "fail"
        assert result["new_candidate_executions"] == 0
        assert result["new_pybdsf_executions"] == 0
        assert result["reused_input_evaluations"] == 1
        assert result["new_input_evaluations"] == 2
        assert Path(plan["output"]).is_file()
    else:
        with pytest.raises(RuntimeError, match=f"injected {failure}"):
            runner.run_continuation(plan, {"fixture": True})
        assert not Path(plan["output"]).exists()
        failed = json.loads(
            (Path(plan["scratch"]) / "process-failure.json").read_bytes()
        )
        assert failed["stage"] == failure
    assert submitted == ["missing", "partial"]
    assert (
        Path(plan["scratch"]) / "evaluations/missing/complete.json"
    ).is_file()
    assert {
        path: path.read_bytes()
        for path in (tmp_path / "original").rglob("*")
        if path.is_file()
    } == before
    assert (tmp_path / "original/partial/evaluation").is_dir()
    with pytest.raises(FileExistsError):
        runner.run_continuation(plan, {"fixture": True})


@pytest.mark.parametrize("change", ("dask", "plan"))
def test_late_bound_metadata_mutation_blocks_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    plan, inventory = _fixture(tmp_path)
    monkeypatch.setattr(runner, "verify_execution_code", lambda *_: None)
    monkeypatch.setattr(
        runner,
        "_run_stage",
        lambda _stage, tasks, *_: [
            _complete(task, schema=2) for task in tasks
        ],
    )

    def aggregate(*_: Any) -> Any:
        key = "original_plan" if change == "plan" else "dask_comparisons"
        Path(inventory[key]["path"]).write_text("{}")
        return {"status": "pass"}

    monkeypatch.setattr(runner, "aggregate_records", aggregate)
    with pytest.raises(ValueError, match="changed"):
        runner.run_continuation(plan, {})
    assert not Path(plan["output"]).exists()
    assert (Path(plan["scratch"]) / "evaluation-seal.json").is_file()


@pytest.mark.parametrize(
    "mode",
    ("preflight", "execute", "no-authority", "no-hash", "bad-preflight"),
)
def test_cli_cannot_dispatch_without_exact_authority_and_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    plan_path = tmp_path / "plan.json"
    _atomic_json(plan_path, {"output": str(tmp_path / "terminal.json")})
    calls = []

    def preflight(*_: Any) -> None:
        calls.append("preflight")
        if mode == "bad-preflight":
            raise ValueError("preflight rejected")

    def execute(plan: Any, launch: Any) -> Any:
        calls.append("execute")
        assert "authorization" in launch
        _atomic_json(Path(plan["output"]), {"fixture": True})
        return {"result": {"status": "fail"}}

    monkeypatch.setattr(runner, "verify_preflight", preflight, raising=False)
    monkeypatch.setattr(
        runner,
        "verify_authorization",
        lambda *_: calls.append("authority"),
        raising=False,
    )
    monkeypatch.setattr(runner, "run_continuation", execute)
    arguments = [
        "continue",
        "--plan",
        str(plan_path),
        "--plan-sha256",
        identity.binding(plan_path)["sha256"],
        "--identity-review",
        str(tmp_path / "review.json"),
        "--identity-review-sha256",
        "frozen",
    ]
    if mode == "preflight":
        arguments.append("--preflight-only")
    if mode not in {"preflight", "no-authority"}:
        arguments.extend(["--authorization", str(tmp_path / "decision.json")])
    if mode not in {"preflight", "no-hash"}:
        arguments.extend(["--authorization-sha256", "authority"])
    monkeypatch.setattr(sys, "argv", arguments)
    if mode in {"no-authority", "no-hash"}:
        with pytest.raises(PermissionError, match="authorization"):
            runner.main()
        assert "execute" not in calls
    elif mode == "bad-preflight":
        with pytest.raises(ValueError, match="preflight rejected"):
            runner.main()
        assert "execute" not in calls
    else:
        runner.main()
        report = json.loads(capsys.readouterr().out)
        if mode == "execute":
            assert calls == ["authority", "preflight", "authority", "execute"]
            assert report["status"] == "fail"
        else:
            assert calls == ["preflight"]
            assert report["finder_execution_started"] is False
            assert report["evaluation_started"] is False


@pytest.mark.parametrize(
    "identifier", ("", ".", "..", "../outside", "/outside")
)
def test_unsafe_pending_identifier_cannot_escape_new_directory(
    tmp_path: Path,
    identifier: str,
) -> None:
    plan, inventory = _fixture(tmp_path)
    seal = identity.read_bound(inventory["capture_seal"])
    pairs = [identity.read_bound(value) for value in seal["pairs"]]
    pairs[1]["input_id"] = identifier
    path = Path(seal["pairs"][1]["path"])
    path.write_text(json.dumps(pairs[1]))
    seal["pairs"][1] = identity.binding(path)
    seal_path = Path(inventory["capture_seal"]["path"])
    seal_path.write_text(json.dumps(seal))
    inventory["capture_seal"] = identity.binding(seal_path)
    inventory.update(retention.collect_completed_evaluations(pairs))
    with pytest.raises(ValueError, match="one path component"):
        runner.prepare_evaluations(inventory, Path(plan["scratch"]))
    assert not Path(plan["scratch"]).exists()


def test_wrong_capture_count_is_not_a_smaller_population(
    tmp_path: Path,
) -> None:
    plan, inventory = _fixture(tmp_path)
    inventory["capture_pair_count"] = 2
    with pytest.raises(ValueError, match="capture census"):
        runner.prepare_evaluations(inventory, Path(plan["scratch"]))


def _replace_record(task: Any, result: Any, record: Any) -> None:
    record.pop("record_sha256", None)
    record["record_sha256"] = canonical_sha256(record)
    path = Path(result["records"][0]["path"])
    path.write_text(json.dumps(record))
    result["records"][0] = identity.binding(path)
    (Path(task["evaluation_directory"]) / "complete.json").write_text(
        json.dumps(result)
    )


@pytest.mark.parametrize(
    "field,value",
    (
        ("schema_version", True),
        ("schema_version", 2),
        ("lane", "compact-blend"),
        ("capture", {}),
    ),
)
def test_new_record_schema_lane_and_native_capture_remain_binding(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    plan, inventory = _fixture(tmp_path)
    _, tasks = runner.prepare_evaluations(inventory, Path(plan["scratch"]))
    result = _complete(tasks[0], schema=2)
    record = identity.read_bound(result["records"][0])
    record[field] = value
    _replace_record(tasks[0], result, record)
    with pytest.raises(ValueError, match="schema or capture"):
        runner.verify_new_records(tasks[:1], [result])


@pytest.mark.parametrize(
    "field,value",
    (
        ("schema_version", True),
        ("schema_version", 1),
        ("input_id", "other"),
        ("finder_id", "other"),
        ("support", 0),
        ("support", -1),
        ("support", False),
        ("support", "1"),
        ("support", 1),
        ("support", None),
    ),
)
def test_new_diagnostics_keep_the_explicit_unavailable_support_contract(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    plan, inventory = _fixture(tmp_path)
    _, tasks = runner.prepare_evaluations(inventory, Path(plan["scratch"]))
    result = _complete(tasks[0], schema=2)
    record = identity.read_bound(result["records"][0])
    diagnostic = record["source_diagnostics"]
    if field == "support":
        diagnostic["source_records"] = [{"support_label": value}]
    else:
        diagnostic[field] = value
    diagnostic.pop("record_sha256")
    diagnostic["record_sha256"] = canonical_sha256(diagnostic)
    _replace_record(tasks[0], result, record)
    if field == "support" and (
        value is None or (type(value) is int and value == 1)
    ):
        assert len(runner.verify_new_records(tasks[:1], [result])) == 1
    else:
        with pytest.raises(ValueError, match="amended source diagnostic"):
            runner.verify_new_records(tasks[:1], [result])


@pytest.mark.parametrize(
    "defect",
    (
        "duplicate-task",
        "duplicate-result",
        "missing",
        "marker",
        "path",
        "compact",
    ),
)
def test_new_evaluation_census_marker_and_path_validation(
    tmp_path: Path,
    defect: str,
) -> None:
    plan, inventory = _fixture(tmp_path)
    _, tasks = runner.prepare_evaluations(inventory, Path(plan["scratch"]))
    tasks = tasks[:1]
    if defect == "compact":
        tasks[0]["lane"] = "compact-blend"
    result = _complete(tasks[0], schema=2)
    results = [result]
    if defect == "duplicate-task":
        tasks *= 2
    elif defect == "duplicate-result":
        results *= 2
    elif defect == "missing":
        results = []
    elif defect == "marker":
        (Path(tasks[0]["evaluation_directory"]) / "complete.json").write_text(
            "{}"
        )
    elif defect == "path":
        result["records"][0]["path"] = str(tmp_path / "other.json")
        (Path(tasks[0]["evaluation_directory"]) / "complete.json").write_text(
            json.dumps(result)
        )
    if defect == "compact":
        assert runner.verify_new_records(tasks, results)
    else:
        with pytest.raises(ValueError, match=r"census|completion or paths"):
            runner.verify_new_records(tasks, results)


@pytest.mark.parametrize("valid", (False, True))
def test_worker_checks_each_completion_before_dispatch_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    plan, inventory = _fixture(tmp_path)
    _, tasks = runner.prepare_evaluations(inventory, Path(plan["scratch"]))

    def evaluate(task: Any) -> Any:
        return _complete(task, schema=2 if valid else 1)

    monkeypatch.setattr(runner, "evaluate_pair", evaluate)
    if valid:
        assert runner.evaluate_missing_pair(tasks[0])["input_id"] == "missing"
    else:
        with pytest.raises(ValueError, match="amended source diagnostic"):
            runner.evaluate_missing_pair(tasks[0])
    assert (Path(tasks[0]["evaluation_directory"]) / "complete.json").is_file()
