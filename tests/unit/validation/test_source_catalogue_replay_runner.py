"""R6 authority and late-failure tests use only temporary fixture records."""

# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import importlib
import io
import json
import runpy
import sys
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
runner: Any = importlib.import_module(
    "scripts.validation.run_source_catalogue_cumulative_replay"
)


@pytest.mark.parametrize("defect", (None, "status", "plan", "execution_count"))
def test_only_exact_one_use_authority_permits_the_run(
    defect: str | None,
) -> None:
    plan = {"path": "fixture-plan.json", "sha256": "a" * 64}
    authorization = {
        "status": "authorized-for-one-source-catalogue-cumulative-replay",
        "plan_sha256": plan["sha256"],
        "execution_count": 1,
    }
    if defect == "status":
        authorization["status"] = "not-authorized"
    elif defect == "plan":
        authorization["plan_sha256"] = "b" * 64
    elif defect == "execution_count":
        authorization["execution_count"] = 2
    if defect is None:
        runner.verify_authorization(plan, authorization)
    else:
        with pytest.raises(PermissionError, match="one-use"):
            runner.verify_authorization(plan, authorization)


@pytest.mark.parametrize(
    "failure_stage", (None, "capture", "evaluation", "aggregation", "census")
)
def test_late_errors_preserve_every_completed_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str | None,
) -> None:
    scratch = tmp_path / "scratch"
    plan: dict[str, Any] = {
        "scratch": str(scratch),
        "output": str(tmp_path / "terminal.json"),
        "tasks": [{"input_id": "fixture"}],
        "candidate": {"identity": "current"},
        "incumbent": {"identity": "historical"},
    }

    def stage(name: str, *_args: Any) -> list[dict[str, Any]]:
        if failure_stage == name:
            raise RuntimeError(f"injected {name}")
        if name == "capture":
            pair = scratch / "pair.json"
            pair.write_text(
                json.dumps(
                    {
                        "input_id": "wrong"
                        if failure_stage == "census"
                        else "fixture",
                        "captures": {},
                    }
                )
            )
            return [{"path": str(pair), "sha256": file_sha256(pair)}]
        return [{"input_id": "fixture", "records": []}]

    def dask(*_args: Any) -> list[Any]:
        (scratch / "dask-comparisons.json").write_text("{}\n")
        return []

    def aggregate(*_args: Any) -> dict[str, Any]:
        if failure_stage == "aggregation":
            raise RuntimeError("injected aggregation")
        return {"status": "fail", "all_required_endpoints_pass": False}

    monkeypatch.setattr(runner, "_run_stage", stage)
    monkeypatch.setattr(runner, "compare_existing_dask", dask)
    monkeypatch.setattr(runner, "aggregate_records", aggregate)
    if failure_stage is not None:
        with pytest.raises((RuntimeError, ValueError)):
            runner.run_replay(plan, {"fixture": True})
        assert not Path(plan["output"]).exists()
        failure = json.loads((scratch / "process-failure.json").read_bytes())
        assert failure["candidate_products_preserved"] is True
        if failure_stage in ("evaluation", "aggregation"):
            assert (scratch / "capture-seal.json").is_file()
        if failure_stage == "aggregation":
            assert (scratch / "evaluation-seal.json").is_file()
    else:
        terminal = runner.run_replay(plan, {"fixture": True})
        assert terminal["evidence_role"] == "regression"
        assert terminal["fresh_qualification"] is False
        assert terminal["result"]["status"] == "fail"
        assert not terminal["result"]["all_required_endpoints_pass"]
        assert json.loads(Path(plan["output"]).read_bytes()) == terminal
    with pytest.raises(FileExistsError):
        runner.run_replay(plan, {"fixture": True})


@pytest.mark.parametrize("dask_pass", (False, True))
def test_aggregation_keeps_the_complete_confidence_and_safety_policy(
    monkeypatch: pytest.MonkeyPatch,
    dask_pass: bool,
) -> None:
    plan: dict[str, Any] = {
        "execution_root": str(_ROOT),
        "implementations": [],
        "existing_dask_comparisons": 12,
    }
    expected = ({"input_id": "fixture", "finder_id": "current-hebog"},)
    monkeypatch.setattr(
        runner.evidence,
        "load_image_records",
        lambda _entries, keys: (
            expected if keys == [("fixture", "current-hebog")] else None
        ),
    )
    monkeypatch.setattr(
        runner.evidence,
        "compile_compact_records",
        lambda *_args, **kwargs: {"count": kwargs["expected_image_count"]},
    )
    monkeypatch.setattr(
        runner.evidence.evaluate_phase5_prospective_paired_cumulative,
        "_planning_deviations",
        lambda _root: {"frozen": 1.0},
    )

    def decision(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["records"] == expected
        assert kwargs["compact_decisions"] == {"count": 800}
        assert kwargs["expected_continuum_count"] == 1600
        assert kwargs["resamples"] == 50000
        assert kwargs["seed"] == 20260810
        assert kwargs["planning_deviations"] == {"frozen": 1.0}
        assert (
            kwargs["safety_results"]["serial-and-existing-dask-determinism"]
            is dask_pass
        )
        return {"passed": dask_pass}

    monkeypatch.setattr(
        runner.evidence, "compile_cumulative_decision", decision
    )
    result = runner.aggregate_records(
        plan,
        [{"input_id": "fixture", "captures": {"current-hebog": {}}}],
        [{"records": []}],
        [{"pass": dask_pass}] * 12,
    )
    assert result == {"passed": dask_pass}


@pytest.mark.parametrize(
    "mode",
    (
        "preflight",
        "execute",
        "missing-authority",
        "missing-authority-hash",
        "threads",
    ),
)
def test_cli_does_not_execute_without_exact_authority_and_thread_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "terminal.json"
    plan_path.write_text(
        json.dumps({"execution_revision": "a" * 40, "output": str(output)})
    )
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps(
            {
                "status": (
                    "authorized-for-one-source-catalogue-cumulative-replay"
                ),
                "execution_count": 1,
                "plan_sha256": file_sha256(plan_path),
            }
        )
    )
    args = [
        "runner",
        "--plan",
        str(plan_path),
        "--plan-sha256",
        file_sha256(plan_path),
    ]
    if mode == "preflight":
        args.append("--preflight-only")
    elif mode != "missing-authority":
        args.extend(["--authorization", str(authority)])
        if mode != "missing-authority-hash":
            args.extend(["--authorization-sha256", file_sha256(authority)])
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(runner, "verify_replay_plan", lambda *_args: None)
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMBA_NUM_THREADS",
    ):
        monkeypatch.setenv(key, "1")
    if mode == "threads":
        monkeypatch.setenv("NUMBA_NUM_THREADS", "2")
    calls: list[Any] = []

    def run(plan: dict[str, Any], launch: dict[str, Any]) -> dict[str, Any]:
        calls.append(launch)
        assert plan["execution_revision"] == launch["execution_revision"]
        output.write_text("{}\n")
        return {"result": {"status": "fail"}}

    monkeypatch.setattr(runner, "run_replay", run)
    if mode in ("missing-authority", "missing-authority-hash", "threads"):
        with pytest.raises((PermissionError, ValueError)):
            runner.main()
        assert not calls
    else:
        runner.main()
        document = json.loads(capsys.readouterr().out)
        if mode == "preflight":
            assert document["finder_execution_started"] is False
            assert not calls
        else:
            assert document["status"] == "fail"
            assert len(calls) == 1


def test_module_entrypoint_help_has_no_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["runner", "--help"])
    monkeypatch.delitem(
        sys.modules,
        "scripts.validation.run_source_catalogue_cumulative_replay",
    )
    with pytest.raises(SystemExit) as result:
        runpy.run_module(
            "scripts.validation.run_source_catalogue_cumulative_replay",
            run_name="__main__",
        )
    assert result.value.code == 0


def test_worker_failure_cancels_unstarted_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutdown: list[dict[str, bool]] = []
    future: Future[dict[str, Any]] = Future()
    future.set_exception(RuntimeError("injected worker error"))

    class Pool:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> Pool:
            return self

        def __exit__(self, *_args: Any) -> None:
            self.shutdown(wait=True, cancel_futures=False)

        def submit(self, *_args: Any) -> Future[dict[str, Any]]:
            return future

        def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
            shutdown.append({"wait": wait, "cancel_futures": cancel_futures})

    monkeypatch.setattr(runner, "ProcessPoolExecutor", Pool)
    with pytest.raises(RuntimeError, match="injected worker error"):
        runner._run_stage("capture", [{}], lambda row: row, io.StringIO())
    assert shutdown == [{"wait": True, "cancel_futures": True}]
