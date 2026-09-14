#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run the complete Step 2C-PF successor comparison exactly once.

This entry point composes the reviewed terminal launcher with successor-only
protocol loaders and paths.  Pending authorization is rejected before local
container inspection, input materialization, or private staging.
"""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = "config/contracts/phase-5-external-successor-comparison.json"
_DECISION_PATH = (
    "config/contracts/phase-5-external-successor-execution-decision.json"
)
_REGISTRY_PATH = (
    "config/contracts/phase-5-external-successor-endpoint-registry.json"
)
_BASE_REVIEW_PATH = "config/contracts/phase-5-corrective-a-review.json"
_RUNNER_PATHS = {
    "hebog": "scripts/benchmark/run_phase5_external_successor_hebog.py",
    "released-pybdsf": (
        "scripts/benchmark/run_phase5_external_successor_pybdsf.py"
    ),
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_external_successor_pybdsf.py"
    ),
    "aegean": "scripts/benchmark/run_phase5_external_successor_aegean.py",
}
_MATERIALIZE_CODE = (
    "import runpy,sys; from pathlib import Path; "
    "m=runpy.run_path('/repository/scripts/validation/"
    "phase5_external_successor_protocol.py'); "
    "import hebog.validation.materialization as h; "
    "h.load_phase_five_external_comparison_protocol="
    "m['load_successor_protocol']; "
    "h.materialize_external_realization(Path(sys.argv[1]), Path(sys.argv[2]), "
    "sys.argv[3], int(sys.argv[4]), Path(sys.argv[5]))"
)

_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_successor_protocol.py")
)
_TERMINAL = runpy.run_path(
    str(_ROOT / "scripts/benchmark/run_phase5_external_campaign.py")
)


def _configure_terminal_launcher(registry_path: Path) -> dict[str, Any]:
    """Install the validated successor seams into the closed launcher."""
    helpers = _HELPERS
    terminal = _TERMINAL
    globals_ = terminal["_run"].__globals__
    globals_["load_phase_five_external_comparison_protocol"] = helpers[
        "load_successor_protocol"
    ]
    globals_["load_phase_five_external_execution_decision"] = helpers[
        "load_successor_execution_decision"
    ]
    globals_["_RUNNER_PATHS"] = dict(_RUNNER_PATHS)
    globals_["_MATERIALIZE_CODE"] = _MATERIALIZE_CODE
    globals_["__file__"] = str(Path(__file__))

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
        """Verify the wrapper registry before delegating closed mechanics."""
        registry = helpers["load_successor_endpoint_registry"](registry_path)
        if launcher_path.resolve() != Path(__file__).resolve():
            raise ValueError("unexpected successor campaign launcher path")
        if registry["launcher_path"] != (
            "scripts/benchmark/run_phase5_external_successor_campaign.py"
        ):
            raise ValueError("successor launcher registry path changed")
        if registry["launcher_sha256"] != helpers["file_sha256"](
            launcher_path
        ):
            raise ValueError("successor launcher checksum changed")
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
    return terminal


def materializer_container_command(
    request: Any,
    campaign_input: Any,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> tuple[str, ...]:
    """Build one successor-governed materialization command."""
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
    """Build one isolated successor runner command."""
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


def _arguments(  # noqa: PLR0913
    *,
    repository_root: Path,
    output: Path,
    images: dict[str, str],
    resume: bool,
    preflight_only: bool,
    podman_executable: str,
) -> argparse.Namespace:
    """Build the exact argument namespace consumed by the terminal launcher."""
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


def preflight_successor_campaign(
    *,
    repository_root: Path,
    output: Path,
    images: dict[str, str],
    podman_executable: str = "podman",
) -> None:
    """Run the complete no-write preflight after named authorization only."""
    decision = _HELPERS["load_successor_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError(
            "successor external comparison execution is not authorized"
        )
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
    """Parse one successor campaign invocation."""
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
    """Reject pending state, then delegate one complete successor campaign."""
    parsed = _parse_args()
    repository_root = cast(Path, parsed.repository_root).resolve()
    decision = _HELPERS["load_successor_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError(
            "successor external comparison execution is not authorized"
        )
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
