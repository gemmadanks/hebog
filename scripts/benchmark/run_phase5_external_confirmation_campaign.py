#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run the fresh Phase 5 confirmation comparison exactly once."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_parallel import (
    concurrent_campaign_request_model,
    finder_resource_lanes,
    run_parallel_lanes,
)

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = (
    "config/contracts/phase-5-external-confirmation-comparison.json"
)
_DECISION_PATH = (
    "config/contracts/phase-5-external-confirmation-execution-decision.json"
)
_REGISTRY_PATH = (
    "config/contracts/phase-5-external-confirmation-endpoint-registry.json"
)
_BASE_REVIEW_PATH = "config/contracts/phase-5-corrective-a-review.json"
_RUNNER_PATHS = {
    "hebog": "scripts/benchmark/run_phase5_external_confirmation_hebog.py",
    "released-pybdsf": (
        "scripts/benchmark/run_phase5_external_confirmation_pybdsf.py"
    ),
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_external_confirmation_pybdsf.py"
    ),
    "aegean": "scripts/benchmark/run_phase5_external_confirmation_aegean.py",
}
_MATERIALIZE_CODE = (
    "import runpy,sys; from pathlib import Path; "
    "m=runpy.run_path('/repository/scripts/validation/"
    "phase5_external_confirmation_protocol.py'); "
    "import hebog.validation.materialization as h; "
    "h.load_phase_five_external_comparison_protocol="
    "m['load_confirmation_protocol']; "
    "h.materialize_external_realization(Path(sys.argv[1]), Path(sys.argv[2]), "
    "sys.argv[3], int(sys.argv[4]), Path(sys.argv[5]))"
)
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_IMAGE_COUNT = 1400
_RUN_COUNT = 7000

_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_confirmation_protocol.py")
)
_TERMINAL = runpy.run_path(
    str(_ROOT / "scripts/benchmark/run_phase5_external_campaign.py")
)


def _confirmation_request_builder(
    terminal: dict[str, Any],
) -> Any:
    """Return a builder that differs only by the reviewed two-lane bound."""
    request_model = concurrent_campaign_request_model(
        terminal["CampaignRequest"]
    )

    def build_campaign_request(  # noqa: PLR0913
        *,
        repository_root: Path,
        protocol_path: Path,
        decision_path: Path,
        base_review_path: Path,
        launcher_path: Path,
        containers: dict[Any, Any],
    ) -> Any:
        root = repository_root.resolve()
        for path in (
            protocol_path,
            decision_path,
            base_review_path,
            launcher_path,
        ):
            terminal["_repository_relative"](root, path)
        protocol, decision = terminal["_run"].__globals__[
            "_validate_decision_bindings"
        ](
            root,
            protocol_path,
            decision_path,
            base_review_path,
            launcher_path,
        )
        ordered_containers = terminal["_validate_containers"](
            protocol,
            decision,
            containers,
        )
        inputs, runs = terminal["_population_requests"](root, protocol)
        if decision.pybdsf_ncores != _PYBDSF_NCORES:
            raise ValueError("campaign decision must retain four PyBDSF cores")
        if decision.execution_concurrency != _EXECUTION_CONCURRENCY:
            raise ValueError("confirmation execution must retain two lanes")
        if len(inputs) != _IMAGE_COUNT or len(runs) != _RUN_COUNT:
            raise ValueError("confirmation request matrix count changed")
        return request_model(
            schema_version=1,
            campaign_id="phase-5-external-source-finder-comparison",
            status="authorized-unopened-request",
            protocol_sha256=terminal["file_sha256"](protocol_path),
            execution_decision_sha256=terminal["file_sha256"](decision_path),
            candidate_review_sha256=terminal["file_sha256"](base_review_path),
            implementation_commit=decision.implementation_commit,
            source_tree_sha256=terminal["source_tree_sha256"](root),
            launcher_sha256=terminal["file_sha256"](launcher_path),
            materialization_runtime="approved-hebog-container",
            execution_concurrency=_EXECUTION_CONCURRENCY,
            pybdsf_ncores=_PYBDSF_NCORES,
            containers=ordered_containers,
            image_count=_IMAGE_COUNT,
            run_count=_RUN_COUNT,
            inputs=inputs,
            runs=runs,
            one_look_opened=False,
            step_three_authorized=False,
            optimization_authorized=False,
            qualification_opened=False,
        )

    return request_model, build_campaign_request


def _configure_terminal_launcher(registry_path: Path) -> dict[str, Any]:
    """Install the validated confirmation seams into closed mechanics."""
    helpers = _HELPERS
    terminal = _TERMINAL
    globals_ = terminal["_run"].__globals__
    globals_["load_phase_five_external_comparison_protocol"] = helpers[
        "load_confirmation_protocol"
    ]
    globals_["load_phase_five_external_execution_decision"] = helpers[
        "load_confirmation_execution_decision"
    ]
    globals_["_RUNNER_PATHS"] = dict(_RUNNER_PATHS)
    globals_["_MATERIALIZE_CODE"] = _MATERIALIZE_CODE
    globals_["__file__"] = str(Path(__file__))
    request_model, request_builder = _confirmation_request_builder(terminal)
    globals_["CampaignRequest"] = request_model
    globals_["build_campaign_request"] = request_builder

    terminal_validate = terminal["_validate_decision_bindings"]
    terminal_launcher = (
        _ROOT / "scripts/benchmark/run_phase5_external_campaign.py"
    )

    def validate_decision_bindings(
        repository_root: Path,
        protocol_path: Path,
        decision_path: Path,
        base_review_path: Path,
        launcher_path: Path,
    ) -> tuple[Any, Any]:
        registry = helpers["load_confirmation_endpoint_registry"](
            registry_path
        )
        if launcher_path.resolve() != Path(__file__).resolve():
            raise ValueError("unexpected confirmation campaign launcher path")
        if registry["launcher_path"] != (
            "scripts/benchmark/run_phase5_external_confirmation_campaign.py"
        ):
            raise ValueError("confirmation launcher registry path changed")
        if registry["launcher_sha256"] != helpers["file_sha256"](
            launcher_path
        ):
            raise ValueError("confirmation launcher checksum changed")
        return terminal_validate(
            repository_root,
            protocol_path,
            decision_path,
            base_review_path,
            terminal_launcher,
        )

    globals_["_validate_decision_bindings"] = validate_decision_bindings
    globals_["materializer_container_command"] = materializer_container_command
    globals_["runner_container_command"] = runner_container_command
    globals_["execute_campaign_runs"] = execute_confirmation_runs
    return terminal


def materializer_container_command(
    request: Any,
    campaign_input: Any,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> tuple[str, ...]:
    """Build one confirmation-governed materialization command."""
    container = _TERMINAL["_container_by_finder"](request, "hebog")
    command = _TERMINAL["_container_prefix"](
        container,
        repository_root=repository_root,
        staging_root=staging_root,
        podman_executable=podman_executable,
        expose_source=False,
    )
    command.extend(
        (
            "-c",
            _MATERIALIZE_CODE,
            f"/repository/{_PROTOCOL_PATH}",
            f"/repository/{campaign_input.manifest_relative_path}",
            campaign_input.dataset_identifier,
            str(campaign_input.seed),
            f"/campaign/{campaign_input.relative_directory}",
        )
    )
    return tuple(command)


def runner_container_command(
    request: Any,
    run: Any,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> tuple[str, ...]:
    """Build one isolated confirmation runner command."""
    campaign_input = {item.input_id: item for item in request.inputs}[
        run.input_id
    ]
    container = _TERMINAL["_container_by_finder"](request, run.finder_id)
    command = _TERMINAL["_container_prefix"](
        container,
        repository_root=repository_root,
        staging_root=staging_root,
        podman_executable=podman_executable,
        expose_source=run.finder_id != "hebog",
    )
    command.extend(
        (
            f"/repository/{_RUNNER_PATHS[run.finder_id]}",
            "--protocol",
            f"/repository/{_PROTOCOL_PATH}",
            "--execution-decision",
            f"/repository/{_DECISION_PATH}",
            "--input",
            f"/campaign/{campaign_input.relative_directory}/input.json",
        )
    )
    if run.finder_id == "hebog":
        command.extend(
            (
                "--base-review",
                f"/repository/{_BASE_REVIEW_PATH}",
                "--manifest",
                f"/repository/{campaign_input.manifest_relative_path}",
            )
        )
    elif run.finder_id in {
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
                str(request.pybdsf_ncores),
            )
        )
    else:
        command.extend(("--mode", run.mode))
    command.extend(
        (
            "--container-image-digest",
            container.digest,
            "--output",
            f"/campaign/{run.relative_directory}",
        )
    )
    return tuple(command)


def execute_confirmation_runs(  # noqa: PLR0913
    request: Any,
    *,
    protocol: Any,
    decision: Any,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> None:
    """Execute one serial PyBDSF lane beside one serial companion lane."""

    def execute(run: Any) -> None:
        directory = staging_root / run.relative_directory
        result_path = directory / "result.json"
        if result_path.exists():
            _TERMINAL["_verify_run"](
                request,
                run,
                protocol=protocol,
                decision=decision,
                staging_root=staging_root,
            )
            return
        if directory.exists():
            raise ValueError(f"incomplete campaign run directory: {directory}")
        command = runner_container_command(
            request,
            run,
            repository_root=repository_root,
            staging_root=staging_root,
            podman_executable=podman_executable,
        )
        _TERMINAL["_invoke_container"](
            command,
            staging_root=staging_root,
            identity=run.run_id,
        )
        _TERMINAL["_verify_run"](
            request,
            run,
            protocol=protocol,
            decision=decision,
            staging_root=staging_root,
        )

    def report(completed: int) -> None:
        if completed % 25 == 0 or completed == request.run_count:
            print(f"verified {completed}/{request.run_count} finder runs")

    lanes = finder_resource_lanes(request.runs)
    completed = run_parallel_lanes(lanes, execute, on_complete=report)
    if completed != request.run_count:
        raise RuntimeError("confirmation execution stopped before completion")


def _arguments(  # noqa: PLR0913
    *,
    repository_root: Path,
    output: Path,
    images: dict[str, str],
    resume: bool,
    preflight_only: bool,
    podman_executable: str,
) -> argparse.Namespace:
    """Build the exact namespace consumed by the terminal launcher."""
    return argparse.Namespace(
        repository_root=repository_root,
        protocol=repository_root / _PROTOCOL_PATH,
        execution_decision=repository_root / _DECISION_PATH,
        base_review=repository_root / _BASE_REVIEW_PATH,
        hebog_image=images["hebog"],
        released_pybdsf_image=images["released-pybdsf"],
        master_pybdsf_image=images["pinned-pybdsf-master"],
        aegean_image=images["aegean"],
        output=output,
        resume=resume,
        preflight_only=preflight_only,
        podman_executable=podman_executable,
    )


def preflight_confirmation_campaign(
    *,
    repository_root: Path,
    output: Path,
    images: dict[str, str],
    podman_executable: str = "podman",
) -> None:
    """Run the complete no-write preflight after named authorization."""
    decision = _HELPERS["load_confirmation_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError("confirmation execution is not authorized")
    terminal = _configure_terminal_launcher(repository_root / _REGISTRY_PATH)
    terminal["_run"](
        _arguments(
            repository_root=repository_root,
            output=output,
            images=images,
            resume=False,
            preflight_only=True,
            podman_executable=podman_executable,
        )
    )


def _parse_args() -> argparse.Namespace:
    """Parse one confirmation campaign invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--hebog-image", required=True)
    parser.add_argument("--released-pybdsf-image", required=True)
    parser.add_argument("--master-pybdsf-image", required=True)
    parser.add_argument("--aegean-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--podman-executable", default="podman")
    return parser.parse_args()


def main() -> None:
    """Reject pending state, then delegate one complete confirmation."""
    parsed = _parse_args()
    repository_root = cast(Path, parsed.repository_root).resolve()
    decision = _HELPERS["load_confirmation_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError("confirmation execution is not authorized")
    terminal = _configure_terminal_launcher(repository_root / _REGISTRY_PATH)
    terminal["_run"](
        _arguments(
            repository_root=repository_root,
            output=parsed.output,
            images={
                "hebog": parsed.hebog_image,
                "released-pybdsf": parsed.released_pybdsf_image,
                "pinned-pybdsf-master": parsed.master_pybdsf_image,
                "aegean": parsed.aegean_image,
            },
            resume=parsed.resume,
            preflight_only=parsed.preflight_only,
            podman_executable=parsed.podman_executable,
        )
    )


if __name__ == "__main__":
    main()
