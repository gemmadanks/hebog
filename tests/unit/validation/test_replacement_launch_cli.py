"""The CLI cannot bypass admission, consume authority early or hide failure."""

from __future__ import annotations

import importlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
cli: Any = importlib.import_module(
    "scripts.validation.run_source_catalogue_replacement_replay"
)
binding = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
).binding


@pytest.fixture
def invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    plan_path = tmp_path / "plan.json"
    review_path = tmp_path / "review.json"
    authority_path = tmp_path / "decision.json"
    output = tmp_path / "terminal.json"
    plan = {"output": str(output), "execution_revision": "fixture"}
    plan_path.write_text(json.dumps(plan))
    review = {
        "plan": binding(plan_path),
        "expected_execution_sha256": cli.canonical_sha256(plan),
        "status": "frozen-non-executable",
        "authorizations": {"execution": False},
    }
    review_path.write_text(json.dumps(review))
    authority = {
        "status": "authorized-for-one-current-only-replacement-replay",
        "plan_sha256": binding(plan_path)["sha256"],
        "identity_review_sha256": binding(review_path)["sha256"],
        "expected_execution_sha256": cli.canonical_sha256(plan),
        "execution_count": 1,
    }
    authority_path.write_text(json.dumps(authority))
    arguments = [
        "replay",
        "--plan",
        str(plan_path),
        "--plan-sha256",
        binding(plan_path)["sha256"],
        "--identity-review",
        str(review_path),
        "--identity-review-sha256",
        binding(review_path)["sha256"],
    ]
    authorization_args = [
        "--authorization",
        str(authority_path),
        "--authorization-sha256",
        binding(authority_path)["sha256"],
    ]
    calls: list[str] = []

    def preflight(actual: Any, root: Path) -> None:
        assert actual == plan
        assert root == _ROOT.resolve()
        calls.append("preflight")

    def run(actual: Any, launch: Any) -> Any:
        assert actual == plan and calls == ["preflight"]
        assert launch["plan"] == binding(plan_path)
        assert launch["identity_review"] == binding(review_path)
        assert launch["authorization"] == binding(authority_path)
        assert launch["expected_execution_sha256"] == cli.canonical_sha256(
            plan
        )
        calls.append("capture")
        terminal = {"result": {"status": "fail"}}
        output.write_text(json.dumps(terminal))
        return terminal

    monkeypatch.setattr(cli, "verify_preflight", preflight)
    monkeypatch.setattr(cli, "run_replacement", run)
    return {
        "arguments": arguments,
        "authorization": authorization_args,
        "calls": calls,
        "plan": plan_path,
        "review": review_path,
        "decision": authority_path,
        "output": output,
    }


def test_preflight_only_never_requests_execution_authority_or_writes(
    invocation: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setattr(
        sys, "argv", [*invocation["arguments"], "--preflight-only"]
    )
    cli.main()
    message = json.loads(capsys.readouterr().out)
    assert message["finder_execution_started"] is False
    assert message["status"] == "preflight-pass"
    assert invocation["calls"] == ["preflight"]
    assert not invocation["output"].exists()


@pytest.mark.parametrize("omit", ("both", "path", "hash"))
def test_launch_requires_both_authorization_arguments_before_preflight(
    invocation: Any,
    monkeypatch: pytest.MonkeyPatch,
    omit: str,
) -> None:
    args: list[str] = invocation["authorization"]
    extras: list[str] = (
        [] if omit == "both" else args[2:] if omit == "path" else args[:2]
    )
    monkeypatch.setattr(sys, "argv", [*invocation["arguments"], *extras])
    with pytest.raises(PermissionError, match="one-use"):
        cli.main()
    assert not invocation["calls"]


@pytest.mark.parametrize("stage", ("before", "after"))
@pytest.mark.parametrize("document", ("plan", "review", "decision"))
def test_launch_rejects_bound_file_changes_even_during_long_preflight(
    invocation: Any,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    document: str,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            *invocation["arguments"],
            *invocation["authorization"],
        ],
    )

    def change(*_args: Any) -> None:
        invocation[document].write_text("{}")

    if stage == "before":
        change()
    else:
        monkeypatch.setattr(cli, "verify_preflight", change)
    with pytest.raises(ValueError, match="bound document"):
        cli.main()
    assert "capture" not in invocation["calls"]
    assert not invocation["output"].exists()


def test_completed_scientific_failure_is_reported_not_retried(
    invocation: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            *invocation["arguments"],
            *invocation["authorization"],
        ],
    )
    cli.main()
    message = json.loads(capsys.readouterr().out)
    assert message["status"] == "fail"
    assert message["sha256"] == binding(invocation["output"])["sha256"]
    assert invocation["calls"] == ["preflight", "capture"]


@pytest.mark.parametrize("stage", ("preflight", "execution"))
def test_process_error_propagates_without_automatic_retry(
    invocation: Any,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            *invocation["arguments"],
            *invocation["authorization"],
        ],
    )

    def fail(*_args: Any) -> None:
        raise RuntimeError("injected " + stage)

    monkeypatch.setattr(
        cli,
        "verify_preflight" if stage == "preflight" else "run_replacement",
        fail,
    )
    with pytest.raises(RuntimeError, match=stage):
        cli.main()
    assert "capture" not in invocation["calls"]
    assert not invocation["output"].exists()


def test_module_help_exits_without_execution() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.validation.run_source_catalogue_replacement_replay",
            "--help",
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--preflight-only" in result.stdout


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan", {}),
        ("expected_execution_sha256", "0" * 64),
        ("status", "authorized"),
        ("authorizations", {"execution": True}),
    ],
)
def test_cli_review_semantics_are_not_implied_by_a_valid_hash(
    invocation: Any,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    path = invocation["review"]
    review = json.loads(path.read_bytes())
    review[field] = value
    path.write_text(json.dumps(review))
    arguments = [*invocation["arguments"], "--preflight-only"]
    arguments[arguments.index("--identity-review-sha256") + 1] = binding(path)[
        "sha256"
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(ValueError, match="review changed"):
        cli.main()
    assert not invocation["calls"]


def test_entrypoint_help_has_no_execution_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["replay", "--help"])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(cli.__file__, run_name="__main__")
    assert error.value.code == 0
