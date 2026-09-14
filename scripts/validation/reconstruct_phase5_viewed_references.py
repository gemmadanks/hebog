#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Reconstruct reference products for the complete viewed Phase 5 replay.

This is a restartable development-evidence operation. It deliberately omits
Hebog: the cumulative review generates the approved candidate through the
shared recovery adapter. The terminal reconstruction is not a fresh campaign
and cannot authorize one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from hebog.validation.campaign_parallel import (
    finder_resource_lanes,
    run_parallel_lanes,
)
from hebog.validation.external_runners import (
    file_sha256,
    load_external_run_result,
    source_tree_sha256,
)
from hebog.validation.materialization import load_external_input_bundle

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = (
    _ROOT / "config/contracts/phase-5-external-post-failure-comparison.json"
)
_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-viewed-recovery-execution-decision.json"
)
_ORIGINAL_ROOT = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison"
)
_ORIGINAL_REQUEST_PATH = _ORIGINAL_ROOT / "campaign-request.json"
_ORIGINAL_CAMPAIGN_PATH = _ORIGINAL_ROOT / "campaign.json"
_ORIGINAL_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_ORIGINAL_CAMPAIGN_SHA256 = (
    "c16dc486464e09dd729f4a90eb1d586bfd6c2eecc04bda1a41b3b209c2ae091a"
)
_MATERIALIZE_CODE = (
    "import runpy,sys; from pathlib import Path; "
    "m=runpy.run_path('/repository/scripts/validation/"
    "phase5_external_post_failure_protocol.py'); "
    "g=m['load_post_failure_population'].__globals__; "
    "g['source_tree_sha256']=lambda _root:m['_SOURCE_TREE_SHA256']; "
    "import hebog.validation.materialization as h; "
    "h.load_phase_five_external_comparison_protocol="
    "m['load_post_failure_protocol']; "
    "h.materialize_external_realization(Path(sys.argv[1]),Path(sys.argv[2]),"
    "sys.argv[3],int(sys.argv[4]),Path(sys.argv[5]))"
)
_RUNNER_PATHS = {
    "released-pybdsf": (
        "scripts/benchmark/run_phase5_viewed_recovery_pybdsf.py"
    ),
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_viewed_recovery_pybdsf.py"
    ),
    "aegean": "scripts/benchmark/run_phase5_viewed_recovery_aegean.py",
}
_IMAGE_COUNT = 2400
_ORIGINAL_RUN_COUNT = 12000
_REFERENCE_RUN_COUNT = 9600
_MINIMUM_AVAILABLE_GIB = 120.0


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _git_revision() -> str:
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("viewed recovery requires a clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _namespace(document: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**document)


def _load_original_request() -> SimpleNamespace:
    if file_sha256(_ORIGINAL_REQUEST_PATH) != _ORIGINAL_REQUEST_SHA256:
        raise ValueError("original viewed request identity changed")
    if file_sha256(_ORIGINAL_CAMPAIGN_PATH) != _ORIGINAL_CAMPAIGN_SHA256:
        raise ValueError("original viewed campaign identity changed")
    document = _json_object(_ORIGINAL_REQUEST_PATH)
    inputs = tuple(_namespace(item) for item in document["inputs"])
    runs = tuple(_namespace(item) for item in document["runs"])
    if (
        document.get("image_count") != _IMAGE_COUNT
        or document.get("run_count") != _ORIGINAL_RUN_COUNT
        or len(inputs) != _IMAGE_COUNT
        or len(runs) != _ORIGINAL_RUN_COUNT
    ):
        raise ValueError("original viewed population changed")
    return SimpleNamespace(**{**document, "inputs": inputs, "runs": runs})


def _reference_runs(runs: tuple[Any, ...]) -> tuple[Any, ...]:
    """Exclude the obsolete historical candidate from reconstruction."""
    return tuple(run for run in runs if run.finder_id != "hebog")


def _helpers() -> dict[str, Any]:
    return runpy.run_path(
        str(_ROOT / "scripts/validation/phase5_viewed_recovery_protocol.py")
    )


def _inspect_image(image: str, podman: str) -> dict[str, str]:
    completed = subprocess.run(
        (podman, "image", "inspect", image),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(f"cannot inspect recovery image {image!r}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError("unexpected recovery image inspection")
    item = cast(dict[str, Any], payload[0])
    return {
        "image": image,
        "image_id": str(item["Id"]).removeprefix("sha256:"),
        "digest": str(item["Digest"]),
        "operating_system": str(item["Os"]),
        "architecture": str(item["Architecture"]),
    }


def _resolved_images(
    images: dict[str, str], podman: str, decision: dict[str, Any]
) -> dict[str, dict[str, str]]:
    configured = {
        cast(str, item["finder_id"]): item
        for item in (
            *cast(list[dict[str, Any]], decision["reference_runtimes"]),
            cast(dict[str, Any], decision["materializer_runtime"]),
        )
    }
    resolved = {
        finder: _inspect_image(image, podman)
        for finder, image in images.items()
    }
    if set(resolved) != set(configured):
        raise ValueError("viewed recovery image set changed")
    for finder, runtime in resolved.items():
        expected = configured[finder]
        if (
            runtime["image_id"] != expected["image_id"]
            or runtime["digest"] != expected["digest"]
            or runtime["operating_system"] != "linux"
            or runtime["architecture"] != "arm64"
        ):
            raise ValueError(f"viewed recovery runtime changed: {finder}")
    return resolved


def _container_prefix(
    runtime: dict[str, str],
    *,
    staging: Path,
    podman: str,
    expose_source: bool,
) -> list[str]:
    command = [
        podman,
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{_ROOT.resolve()}:/repository:ro",
        "--volume",
        f"{staging.resolve()}:/recovery:rw",
        "--workdir",
        "/repository",
        "--entrypoint",
        "python3",
    ]
    if expose_source:
        command.extend(("--env", "PYTHONPATH=/repository/src"))
    command.append(f"sha256:{runtime['image_id']}")
    return command


def _materialize_command(
    campaign_input: Any,
    runtime: dict[str, str],
    *,
    staging: Path,
    podman: str,
) -> tuple[str, ...]:
    command = _container_prefix(
        runtime,
        staging=staging,
        podman=podman,
        expose_source=False,
    )
    command.extend(
        (
            "-c",
            _MATERIALIZE_CODE,
            f"/repository/{_PROTOCOL_PATH.relative_to(_ROOT)}",
            f"/repository/{campaign_input.manifest_relative_path}",
            campaign_input.dataset_identifier,
            str(campaign_input.seed),
            f"/recovery/{campaign_input.relative_directory}",
        )
    )
    return tuple(command)


def _runner_command(
    run: Any,
    campaign_input: Any,
    runtime: dict[str, str],
    *,
    staging: Path,
    podman: str,
) -> tuple[str, ...]:
    command = _container_prefix(
        runtime,
        staging=staging,
        podman=podman,
        expose_source=True,
    )
    command.extend(
        (
            f"/repository/{_RUNNER_PATHS[run.finder_id]}",
            "--protocol",
            f"/repository/{_PROTOCOL_PATH.relative_to(_ROOT)}",
            "--execution-decision",
            f"/repository/{_DECISION_PATH.relative_to(_ROOT)}",
            "--input",
            f"/recovery/{campaign_input.relative_directory}/input.json",
        )
    )
    if run.finder_id in {
        "released-pybdsf",
        "pinned-pybdsf-master",
    }:
        command.extend(
            (
                "--finder-id",
                run.finder_id,
                "--mode",
                run.mode,
                "--ncores",
                "4",
            )
        )
    else:
        command.extend(("--mode", run.mode))
    command.extend(
        (
            "--container-image-digest",
            runtime["digest"],
            "--output",
            f"/recovery/{run.relative_directory}",
        )
    )
    return tuple(command)


def _infrastructure_log(
    staging: Path,
    identity: str,
    command: tuple[str, ...],
    completed: subprocess.CompletedProcess[str],
) -> Path:
    directory = staging / "infrastructure-logs"
    directory.mkdir(exist_ok=True)
    path = directory / f"{identity}.json"
    path.write_bytes(
        _canonical_json_bytes(
            {
                "command": list(command),
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
    )
    return path


def _invoke(staging: Path, identity: str, command: tuple[str, ...]) -> None:
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True
    )
    if completed.returncode:
        path = _infrastructure_log(staging, identity, command, completed)
        raise RuntimeError(f"recovery infrastructure failed; see {path}")


def _verify_input(
    staging: Path, campaign_input: Any, *, protocol_sha256: str
) -> Path:
    path = staging / campaign_input.relative_directory / "input.json"
    bundle = load_external_input_bundle(path, verify_artifacts=True)
    if (
        bundle.protocol_sha256 != protocol_sha256
        or bundle.manifest_sha256 != campaign_input.manifest_sha256
        or bundle.dataset_identifier != campaign_input.dataset_identifier
        or bundle.seed != campaign_input.seed
        or bundle.recipe_sha256 != campaign_input.recipe_sha256
    ):
        raise ValueError("viewed recovery input identity changed")
    return path


def _expected_reference(protocol: Any, finder_id: str) -> Any:
    return next(
        item for item in protocol.references if item.finder_id == finder_id
    )


def _verify_run(  # noqa: PLR0913
    staging: Path,
    run: Any,
    campaign_input: Any,
    *,
    protocol: Any,
    protocol_sha256: str,
    decision_sha256: str,
) -> Path:
    path = staging / run.relative_directory / "result.json"
    result = load_external_run_result(path, verify_artifacts=True)
    input_path = staging / campaign_input.relative_directory / "input.json"
    reference = _expected_reference(protocol, run.finder_id)
    if (
        result.protocol_sha256 != protocol_sha256
        or result.execution_decision_sha256 != decision_sha256
        or result.input_bundle_sha256 != file_sha256(input_path)
        or result.finder_id != run.finder_id
        or result.mode != run.mode
        or result.runtime.source_revision != reference.source_revision
        or result.runtime.container_image_digest
        != reference.container_image_digest
        or result.runtime.dependency_inventory_sha256
        != reference.dependency_inventory_sha256
    ):
        raise ValueError(f"viewed recovery run identity changed: {run.run_id}")
    return path


def _materialize_inputs(
    request: Any,
    runtime: dict[str, str],
    *,
    staging: Path,
    podman: str,
    progress: Any,
) -> None:
    for index, campaign_input in enumerate(request.inputs, start=1):
        path = staging / campaign_input.relative_directory / "input.json"
        if path.exists():
            _verify_input(
                staging,
                campaign_input,
                protocol_sha256=request.protocol_sha256,
            )
        else:
            if path.parent.exists():
                raise ValueError("incomplete viewed recovery input")
            _invoke(
                staging,
                f"materialize-{campaign_input.input_id}",
                _materialize_command(
                    campaign_input,
                    runtime,
                    staging=staging,
                    podman=podman,
                ),
            )
            _verify_input(
                staging,
                campaign_input,
                protocol_sha256=request.protocol_sha256,
            )
        if index % 25 == 0 or index == _IMAGE_COUNT:
            message = f"verified-inputs={index}/{_IMAGE_COUNT}"
            print(message, flush=True)
            progress.write(f"{datetime.now(UTC).isoformat()} {message}\n")
            progress.flush()


def _execute_reference_runs(  # noqa: PLR0913
    request: Any,
    runtimes: dict[str, dict[str, str]],
    *,
    protocol: Any,
    decision_sha256: str,
    staging: Path,
    podman: str,
    progress: Any,
) -> None:
    inputs = {item.input_id: item for item in request.inputs}
    runs = _reference_runs(request.runs)
    if len(runs) != _REFERENCE_RUN_COUNT:
        raise ValueError("viewed recovery reference matrix changed")

    def execute(run: Any) -> None:
        directory = staging / run.relative_directory
        result_path = directory / "result.json"
        campaign_input = inputs[run.input_id]
        if not result_path.exists():
            if directory.exists():
                raise ValueError("incomplete viewed recovery result")
            _invoke(
                staging,
                run.run_id,
                _runner_command(
                    run,
                    campaign_input,
                    runtimes[run.finder_id],
                    staging=staging,
                    podman=podman,
                ),
            )
        _verify_run(
            staging,
            run,
            campaign_input,
            protocol=protocol,
            protocol_sha256=request.protocol_sha256,
            decision_sha256=decision_sha256,
        )

    def report(completed: int) -> None:
        if completed % 25 == 0 or completed == _REFERENCE_RUN_COUNT:
            message = (
                f"verified-reference-runs={completed}/{_REFERENCE_RUN_COUNT}"
            )
            print(message, flush=True)
            progress.write(f"{datetime.now(UTC).isoformat()} {message}\n")
            progress.flush()

    completed = run_parallel_lanes(
        finder_resource_lanes(runs), execute, on_complete=report
    )
    if completed != _REFERENCE_RUN_COUNT:
        raise RuntimeError("viewed recovery stopped before completion")


def _identity_set_sha256(paths: tuple[tuple[str, Path], ...]) -> str:
    return _canonical_sha256(
        [
            {"identifier": identifier, "sha256": file_sha256(path)}
            for identifier, path in paths
        ]
    )


def _request_document(
    *,
    decision: dict[str, Any],
    runtimes: dict[str, dict[str, str]],
    checkout_revision: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "recovery_id": "phase-5-viewed-reference-reconstruction",
        "status": "approved-private-development-recovery",
        "original_campaign_sha256": _ORIGINAL_CAMPAIGN_SHA256,
        "original_request_sha256": _ORIGINAL_REQUEST_SHA256,
        "protocol_sha256": file_sha256(_PROTOCOL_PATH),
        "execution_decision_sha256": file_sha256(_DECISION_PATH),
        "candidate_revision": decision["candidate_revision"],
        "candidate_source_tree_sha256": source_tree_sha256(_ROOT),
        "execution_checkout_revision": checkout_revision,
        "images": runtimes,
        "image_count": _IMAGE_COUNT,
        "reference_run_count": _REFERENCE_RUN_COUNT,
        "candidate_runs_executed": 0,
        "fresh_campaign_execution_authorized": False,
        "one_look_opened": False,
        "step_three_authorized": False,
    }


def _prepare_staging(
    output: Path,
    request_document: dict[str, Any],
    *,
    resume: bool,
) -> Path:
    if output.exists():
        raise FileExistsError(f"viewed recovery output exists: {output}")
    staging = output.parent / (
        f".{output.name}.{request_document['execution_decision_sha256'][:12]}.staging"
    )
    path = staging / "recovery-request.json"
    expected = _canonical_json_bytes(request_document)
    if resume:
        if not path.is_file() or path.read_bytes() != expected:
            raise ValueError("viewed recovery resume identity changed")
        return staging
    if staging.exists():
        raise FileExistsError(f"viewed recovery staging exists: {staging}")
    staging.mkdir(parents=True)
    path.write_bytes(expected)
    (staging / "recovery-open-state.json").write_bytes(
        _canonical_json_bytes(
            {
                "schema_version": 1,
                "request_sha256": hashlib.sha256(expected).hexdigest(),
                "opened_at": datetime.now(UTC).isoformat(),
                "fresh_campaign_execution_authorized": False,
            }
        )
    )
    return staging


def _seal(staging: Path, output: Path, request: Any) -> Path:
    inputs = tuple(
        (
            item.input_id,
            staging / item.relative_directory / "input.json",
        )
        for item in request.inputs
    )
    runs = tuple(
        (
            item.run_id,
            staging / item.relative_directory / "result.json",
        )
        for item in _reference_runs(request.runs)
    )
    terminal = {
        "schema_version": 1,
        "recovery_id": "phase-5-viewed-reference-reconstruction",
        "status": "sealed-viewed-development-reference-evidence",
        "request_sha256": file_sha256(staging / "recovery-request.json"),
        "original_campaign_sha256": _ORIGINAL_CAMPAIGN_SHA256,
        "original_request_sha256": _ORIGINAL_REQUEST_SHA256,
        "input_count": len(inputs),
        "reference_run_count": len(runs),
        "input_bundle_set_sha256": _identity_set_sha256(inputs),
        "reference_result_set_sha256": _identity_set_sha256(runs),
        "completed_at": datetime.now(UTC).isoformat(),
        "candidate_runs_executed": 0,
        "fresh_campaign_execution_authorized": False,
        "one_look_opened": False,
        "step_three_authorized": False,
    }
    path = staging / "recovery.json"
    path.write_bytes(_canonical_json_bytes(terminal))
    staging.rename(output)
    return output / path.name


def verify_viewed_reference_reconstruction(
    root: Path,
    *,
    original_request: Any,
    verified_run_type: Any,
) -> Any:
    """Verify terminal recovery bytes and expose a compiler-compatible view."""
    helpers = _helpers()
    protocol = helpers["load_viewed_recovery_protocol"](_PROTOCOL_PATH)
    helpers["load_viewed_recovery_execution_decision"](_DECISION_PATH)
    terminal = _json_object(root / "recovery.json")
    request_document = _json_object(root / "recovery-request.json")
    if (
        terminal.get("status")
        != "sealed-viewed-development-reference-evidence"
        or terminal.get("request_sha256")
        != file_sha256(root / "recovery-request.json")
        or terminal.get("original_campaign_sha256")
        != _ORIGINAL_CAMPAIGN_SHA256
        or terminal.get("original_request_sha256") != _ORIGINAL_REQUEST_SHA256
        or terminal.get("input_count") != _IMAGE_COUNT
        or terminal.get("reference_run_count") != _REFERENCE_RUN_COUNT
        or terminal.get("candidate_runs_executed") != 0
        or terminal.get("fresh_campaign_execution_authorized") is not False
        or request_document.get("candidate_source_tree_sha256")
        != source_tree_sha256(_ROOT)
    ):
        raise ValueError("viewed reference reconstruction identity changed")
    inputs: dict[str, tuple[Any, Path]] = {}
    input_identities: list[tuple[str, Path]] = []
    for campaign_input in original_request.inputs:
        path = root / campaign_input.relative_directory / "input.json"
        bundle = load_external_input_bundle(path, verify_artifacts=True)
        if (
            bundle.protocol_sha256 != file_sha256(_PROTOCOL_PATH)
            or bundle.manifest_sha256 != campaign_input.manifest_sha256
            or bundle.dataset_identifier != campaign_input.dataset_identifier
            or bundle.seed != campaign_input.seed
            or bundle.recipe_sha256 != campaign_input.recipe_sha256
        ):
            raise ValueError("viewed recovery input changed")
        inputs[campaign_input.input_id] = (bundle, path)
        input_identities.append((campaign_input.input_id, path))
    runs: dict[tuple[str, str, str], Any] = {}
    run_identities: list[tuple[str, Path]] = []
    input_by_id = {item.input_id: item for item in original_request.inputs}
    decision_sha256 = file_sha256(_DECISION_PATH)
    for run in _reference_runs(original_request.runs):
        campaign_input = input_by_id[run.input_id]
        path = _verify_run(
            root,
            run,
            campaign_input,
            protocol=protocol,
            protocol_sha256=file_sha256(_PROTOCOL_PATH),
            decision_sha256=decision_sha256,
        )
        result = load_external_run_result(path, verify_artifacts=False)
        runs[(run.input_id, run.finder_id, run.mode)] = verified_run_type(
            request=run, result=result, directory=path.parent
        )
        run_identities.append((run.run_id, path))
    if terminal["input_bundle_set_sha256"] != _identity_set_sha256(
        tuple(input_identities)
    ):
        raise ValueError("viewed recovery input set changed")
    if terminal["reference_result_set_sha256"] != _identity_set_sha256(
        tuple(run_identities)
    ):
        raise ValueError("viewed recovery result set changed")
    return SimpleNamespace(
        root=root,
        request=original_request,
        terminal=SimpleNamespace(
            completed_at=datetime.fromisoformat(
                cast(str, terminal["completed_at"])
            )
        ),
        campaign_sha256=_ORIGINAL_CAMPAIGN_SHA256,
        reference_reconstruction_sha256=file_sha256(root / "recovery.json"),
        inputs=inputs,
        runs=runs,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--materializer-image", required=True)
    parser.add_argument("--released-pybdsf-image", required=True)
    parser.add_argument("--master-pybdsf-image", required=True)
    parser.add_argument("--aegean-image", required=True)
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = _parse_args()
    helpers = _helpers()
    protocol = helpers["load_viewed_recovery_protocol"](_PROTOCOL_PATH)
    helpers["load_viewed_recovery_execution_decision"](_DECISION_PATH)
    decision_document = _json_object(_DECISION_PATH)
    request = _load_original_request()
    images = {
        "hebog": arguments.materializer_image,
        "released-pybdsf": arguments.released_pybdsf_image,
        "pinned-pybdsf-master": arguments.master_pybdsf_image,
        "aegean": arguments.aegean_image,
    }
    runtimes = _resolved_images(
        images, arguments.podman_executable, decision_document
    )
    checkout_revision = _git_revision()
    request_document = _request_document(
        decision=decision_document,
        runtimes=runtimes,
        checkout_revision=checkout_revision,
    )
    if arguments.preflight_only:
        if arguments.output.exists():
            raise FileExistsError("viewed recovery output already exists")
        available_gib = shutil.disk_usage(arguments.output.parent).free / 2**30
        if available_gib < _MINIMUM_AVAILABLE_GIB:
            raise ValueError("viewed recovery requires 120 GiB available")
        print("viewed recovery preflight passed")
        return
    staging = _prepare_staging(
        arguments.output, request_document, resume=arguments.resume
    )
    with (staging / "progress.log").open("a", encoding="utf-8") as progress:
        _materialize_inputs(
            request,
            runtimes["hebog"],
            staging=staging,
            podman=arguments.podman_executable,
            progress=progress,
        )
        _execute_reference_runs(
            request,
            runtimes,
            protocol=protocol,
            decision_sha256=file_sha256(_DECISION_PATH),
            staging=staging,
            podman=arguments.podman_executable,
            progress=progress,
        )
    print(_seal(staging, arguments.output, request))


if __name__ == "__main__":
    main()
