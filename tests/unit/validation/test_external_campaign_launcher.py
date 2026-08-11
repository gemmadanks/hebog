# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
"""Tests for the sealed Phase 5 external-comparison campaign launcher."""

from __future__ import annotations

import json
import runpy
import subprocess
from argparse import Namespace
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from hebog.validation.contracts import (
    load_phase_five_external_comparison_protocol,
    load_phase_five_external_execution_decision,
)

_ROOT = Path(__file__).parents[3]
_PROTOCOL = _ROOT / "config/contracts/phase-5-external-comparison.json"
_DECISION = _ROOT / "config/contracts/phase-5-external-execution-decision.json"
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_LAUNCHER = _ROOT / "scripts/benchmark/run_phase5_external_campaign.py"


def _namespace() -> dict[str, Any]:
    """Load the campaign launcher without invoking its CLI."""
    return runpy.run_path(str(_LAUNCHER))


@pytest.fixture(scope="module")
def authorized_decision_path() -> Iterator[Path]:
    """Write a repository-local authorized decision for structural tests."""
    pending = load_phase_five_external_execution_decision(_DECISION)
    decision_type = type(pending)
    decision = decision_type.model_validate(
        {
            **pending.model_dump(mode="json"),
            "status": "reviewed-before-external-output",
            "named_review": "unit-test authorization",
            "decision": "authorize-one-terminal-external-comparison",
            "execution_authorized": True,
            "next_action": (
                "execute-complete-frozen-comparison-once-without-opening-"
                "partial-results"
            ),
        }
    )
    with TemporaryDirectory(prefix=".phase5-test-", dir=_ROOT) as directory:
        decision_path = Path(directory) / "decision.json"
        decision_path.write_text(
            decision.model_dump_json(indent=2),
            encoding="utf-8",
        )
        yield decision_path


@pytest.fixture(scope="module")
def campaign_request(authorized_decision_path: Path) -> object:
    """Build the complete frozen request once for structural tests."""
    namespace = _namespace()
    protocol = load_phase_five_external_comparison_protocol(_PROTOCOL)
    decision = load_phase_five_external_execution_decision(
        authorized_decision_path
    )
    container_type = namespace["CampaignContainerImage"]
    references = {item.finder_id: item for item in protocol.references}
    containers = {
        "hebog": container_type(
            finder_id="hebog",
            image="localhost/hebog:test",
            image_id="1" * 64,
            digest=decision.hebog_container_image_digest,
            operating_system="linux",
            architecture="arm64",
        ),
        **{
            finder_id: container_type(
                finder_id=finder_id,
                image=f"localhost/{finder_id}:test",
                image_id=str(index) * 64,
                digest=reference.container_image_digest,
                operating_system="linux",
                architecture="arm64",
            )
            for index, (finder_id, reference) in enumerate(
                references.items(),
                start=2,
            )
        },
    }
    return namespace["build_campaign_request"](
        repository_root=_ROOT,
        protocol_path=_PROTOCOL,
        decision_path=authorized_decision_path,
        base_review_path=_BASE_REVIEW,
        launcher_path=_LAUNCHER,
        containers=containers,
    )


def test_pending_decision_blocks_campaign_preflight() -> None:
    """The active technical review cannot create an authorized request."""
    with pytest.raises(ValueError, match="execution is not authorized"):
        _namespace()["_validate_decision_bindings"](
            _ROOT,
            _PROTOCOL,
            _DECISION,
            _BASE_REVIEW,
            _LAUNCHER,
        )


def test_frozen_leg_matrix_excludes_unsupported_products() -> None:
    """Each lane runs exactly its applicable binding and diagnostic legs."""
    matrix = _namespace()["frozen_leg_matrix"]

    assert tuple(
        (item.finder_id, item.mode) for item in matrix("continuum")
    ) == (
        ("hebog", "candidate"),
        ("released-pybdsf", "operational"),
        ("released-pybdsf", "controlled-background"),
        ("pinned-pybdsf-master", "operational"),
        ("pinned-pybdsf-master", "controlled-background"),
    )
    assert tuple(
        (item.finder_id, item.mode) for item in matrix("compact-blend")
    ) == (
        ("hebog", "candidate"),
        ("released-pybdsf", "operational"),
        ("pinned-pybdsf-master", "operational"),
        ("aegean", "operational"),
        ("aegean", "controlled-background"),
    )


def test_campaign_request_freezes_every_realization_and_leg(
    campaign_request: Any,
) -> None:
    """The terminal request covers 1,400 inputs and exactly 7,000 runs."""
    assert campaign_request.image_count == 1400
    assert campaign_request.run_count == 7000
    assert len(campaign_request.inputs) == 1400
    assert len(campaign_request.runs) == 7000
    assert len({item.input_id for item in campaign_request.inputs}) == 1400
    assert len({item.run_id for item in campaign_request.runs}) == 7000
    assert {item.lane for item in campaign_request.inputs} == {
        "continuum",
        "compact-blend",
    }


def test_container_commands_bind_mounts_modes_and_four_cores(
    tmp_path: Path,
    campaign_request: Any,
) -> None:
    """Commands expose only the committed repository and private campaign."""
    namespace = _namespace()
    command = namespace["runner_container_command"]
    continuum_pybdsf = next(
        item
        for item in campaign_request.runs
        if item.lane == "continuum"
        and item.finder_id == "released-pybdsf"
        and item.mode == "controlled-background"
    )
    compact_aegean = next(
        item
        for item in campaign_request.runs
        if item.lane == "compact-blend"
        and item.finder_id == "aegean"
        and item.mode == "controlled-background"
    )
    materializer_command = namespace["materializer_container_command"](
        campaign_request,
        campaign_request.inputs[0],
        repository_root=_ROOT,
        staging_root=tmp_path,
        podman_executable="podman",
    )

    pybdsf_command = command(
        campaign_request,
        continuum_pybdsf,
        repository_root=_ROOT,
        staging_root=tmp_path,
        podman_executable="podman",
    )
    aegean_command = command(
        campaign_request,
        compact_aegean,
        repository_root=_ROOT,
        staging_root=tmp_path,
        podman_executable="podman",
    )

    assert "--network=none" in pybdsf_command
    assert f"{_ROOT}:/repository:ro" in pybdsf_command
    assert f"{tmp_path}:/campaign:rw" in pybdsf_command
    immutable_image = f"sha256:{campaign_request.containers[1].image_id}"
    assert immutable_image in pybdsf_command
    assert pybdsf_command[pybdsf_command.index(immutable_image) + 1] == (
        "/repository/scripts/benchmark/run_phase5_external_pybdsf.py"
    )
    assert campaign_request.containers[1].image not in pybdsf_command
    assert pybdsf_command[pybdsf_command.index("--ncores") + 1] == "4"
    assert pybdsf_command[pybdsf_command.index("--mode") + 1] == (
        "controlled-background"
    )
    assert "--finder-id" not in aegean_command
    assert aegean_command[aegean_command.index("--mode") + 1] == (
        "controlled-background"
    )
    assert "PYTHONPATH=/repository/src" not in materializer_command
    assert "-c" in materializer_command
    assert materializer_command[-1].startswith("/campaign/inputs/")


def test_container_inspection_is_typed_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local image inspection neither pulls nor accepts ambiguous output."""
    namespace = _namespace()
    inspected = {
        "Id": "sha256:" + "1" * 64,
        "Digest": "sha256:" + "2" * 64,
        "Os": "linux",
        "Architecture": "arm64",
    }
    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("podman",),
            returncode=0,
            stdout=json.dumps([inspected]),
            stderr="",
        ),
    )

    container = namespace["inspect_container_image"](
        "localhost/hebog:test",
        "hebog",
        podman_executable="podman",
    )

    assert container.image_id == "1" * 64
    assert container.digest == "sha256:" + "2" * 64

    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("podman",),
            returncode=125,
            stdout="",
            stderr="image missing",
        ),
    )
    with pytest.raises(RuntimeError, match="image missing"):
        namespace["inspect_container_image"](
            "missing",
            "hebog",
            podman_executable="podman",
        )


def test_private_staging_refuses_overwrite_and_requires_explicit_resume(
    tmp_path: Path,
    campaign_request: Any,
) -> None:
    """Only the exact request may resume an unpublished campaign."""
    namespace = _namespace()
    output = tmp_path / "terminal-campaign"
    prepare = namespace["prepare_private_staging"]

    staging = prepare(output, campaign_request, resume=False)
    assert staging.name.startswith(".terminal-campaign.")
    assert not output.exists()
    with pytest.raises(FileExistsError, match="private staging"):
        prepare(output, campaign_request, resume=False)
    assert prepare(output, campaign_request, resume=True) == staging

    request_path = staging / "campaign-request.json"
    document = json.loads(request_path.read_text(encoding="utf-8"))
    document["run_count"] -= 1
    request_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match=r"request|canonical"):
        prepare(output, campaign_request, resume=True)


def test_completeness_check_reports_missing_and_unexpected_paths() -> None:
    """A terminal campaign cannot publish with a partial or extra matrix."""
    require_complete = _namespace()["require_exact_path_set"]

    require_complete(
        expected=("results/a/result.json", "results/b/result.json"),
        observed=("results/b/result.json", "results/a/result.json"),
        product="run result",
    )
    with pytest.raises(ValueError, match="missing run result"):
        require_complete(
            expected=("results/a/result.json", "results/b/result.json"),
            observed=("results/a/result.json",),
            product="run result",
        )
    with pytest.raises(ValueError, match="unexpected run result"):
        require_complete(
            expected=("results/a/result.json",),
            observed=("results/a/result.json", "results/c/result.json"),
            product="run result",
        )


def test_publication_rejects_private_temporary_remnants(
    tmp_path: Path,
) -> None:
    """Interrupted atomic output remains private pending explicit review."""
    namespace = _namespace()
    temporary = tmp_path / "results" / "lane" / ".candidate-abandoned"
    temporary.mkdir(parents=True)

    with pytest.raises(ValueError, match="private temporary path"):
        namespace["require_no_private_temporary_paths"](tmp_path)


def test_terminal_manifest_is_idempotent_after_rename_interruption(
    tmp_path: Path,
    campaign_request: Any,
) -> None:
    """Resume accepts only the exact sealed manifest written before rename."""
    namespace = _namespace()
    summary_type = namespace["CampaignRunSummary"]
    state_type = namespace["CampaignOpenState"]
    summaries = tuple(
        summary_type(
            run_id=run.run_id,
            input_id=run.input_id,
            finder_id=run.finder_id,
            mode=run.mode,
            status="success",
            result_relative_path=f"{run.relative_directory}/result.json",
            result_sha256="1" * 64,
        )
        for run in campaign_request.runs
    )
    state = state_type(
        schema_version=1,
        status="private-staging-open",
        request_sha256=namespace["_request_sha256"](campaign_request),
        execution_decision_sha256=(campaign_request.execution_decision_sha256),
        opened_at=datetime.now(UTC),
    )
    result_path = tmp_path / "campaign.json"
    seal = namespace["_seal_terminal_manifest"]

    first = seal(campaign_request, state, summaries, result_path)
    initial_bytes = result_path.read_bytes()
    second = seal(campaign_request, state, summaries, result_path)

    assert second == first
    assert result_path.read_bytes() == initial_bytes

    document = json.loads(result_path.read_text(encoding="utf-8"))
    document["request_sha256"] = "2" * 64
    result_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="differs on resume"):
        seal(campaign_request, state, summaries, result_path)

    invalid_state = state.model_copy(update={"request_sha256": "3" * 64})
    with pytest.raises(ValueError, match="opening state differs"):
        seal(campaign_request, invalid_state, summaries, result_path)


def test_infrastructure_failure_is_logged_without_becoming_finder_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container-start failure remains resumable infrastructure state."""
    namespace = _namespace()
    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("podman",),
            returncode=125,
            stdout="",
            stderr="runtime unavailable",
        ),
    )

    for _ in range(2):
        with pytest.raises(RuntimeError, match="infrastructure failed"):
            namespace["_invoke_container"](
                ("podman", "run", "image"),
                staging_root=tmp_path,
                identity="one-run",
            )

    logs = sorted((tmp_path / "infrastructure-logs").glob("*.json"))
    assert [path.name for path in logs] == [
        "one-run-attempt-001.json",
        "one-run-attempt-002.json",
    ]
    assert "runtime unavailable" in logs[0].read_text(encoding="utf-8")


def test_terminal_publication_refuses_a_partial_matrix(
    tmp_path: Path,
    campaign_request: Any,
) -> None:
    """No campaign manifest or public directory appears for missing legs."""
    namespace = _namespace()
    staging = tmp_path / ".private"
    staging.mkdir()
    output = tmp_path / "terminal"

    with pytest.raises(ValueError, match="missing common input"):
        namespace["finalize_terminal_campaign"](
            campaign_request,
            protocol=load_phase_five_external_comparison_protocol(_PROTOCOL),
            decision=load_phase_five_external_execution_decision(_DECISION),
            staging_root=staging,
            output_directory=output,
        )

    assert not output.exists()
    assert not (staging / "campaign.json").exists()


def test_preflight_only_never_opens_private_staging(
    tmp_path: Path,
    campaign_request: Any,
    authorized_decision_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The real CLI preflight builds all 7,000 legs without writing state."""
    namespace = _namespace()
    output = tmp_path / "terminal"
    arguments = Namespace(
        repository_root=_ROOT,
        protocol=_PROTOCOL,
        execution_decision=authorized_decision_path,
        base_review=_BASE_REVIEW,
        hebog_image="localhost/hebog:test",
        released_pybdsf_image="localhost/released-pybdsf:test",
        master_pybdsf_image="localhost/pinned-pybdsf-master:test",
        aegean_image="localhost/aegean:test",
        output=output,
        resume=False,
        preflight_only=True,
        podman_executable="podman",
    )
    containers = {item.finder_id: item for item in campaign_request.containers}

    def inspect_image(
        command: list[str],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        container = next(
            item for item in containers.values() if item.image == command[-1]
        )
        document = {
            "Id": f"sha256:{container.image_id}",
            "Digest": container.digest,
            "Os": container.operating_system,
            "Architecture": container.architecture,
        }
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps([document]),
            stderr="",
        )

    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        inspect_image,
    )

    namespace["_run"](arguments)

    assert "images=1400 runs=7000" in capsys.readouterr().out
    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.staging"))
