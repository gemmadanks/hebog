#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run the approved fresh Phase 5 post-failure comparison exactly once."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, create_model

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = (
    "config/contracts/phase-5-external-post-failure-comparison.json"
)
_DECISION_PATH = (
    "config/contracts/phase-5-external-post-failure-execution-decision.json"
)
_REGISTRY_PATH = (
    "config/contracts/phase-5-external-post-failure-endpoint-registry.json"
)
_BASE_REVIEW_PATH = "config/contracts/phase-5-corrective-a-review.json"
_RUNNER_PATHS = {
    "hebog": "scripts/benchmark/run_phase5_external_post_failure_hebog.py",
    "released-pybdsf": (
        "scripts/benchmark/run_phase5_external_post_failure_pybdsf.py"
    ),
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_external_post_failure_pybdsf.py"
    ),
    "aegean": ("scripts/benchmark/run_phase5_external_post_failure_aegean.py"),
}
_MATERIALIZE_CODE = (
    "import runpy,sys; from pathlib import Path; "
    "m=runpy.run_path('/repository/scripts/validation/"
    "phase5_external_post_failure_protocol.py'); "
    "import hebog.validation.materialization as h; "
    "h.load_phase_five_external_comparison_protocol="
    "m['load_post_failure_protocol']; "
    "h.materialize_external_realization(Path(sys.argv[1]), Path(sys.argv[2]), "
    "sys.argv[3], int(sys.argv[4]), Path(sys.argv[5]))"
)
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_IMAGE_COUNT = 2400
_RUN_COUNT = 12000

_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_post_failure_protocol.py")
)
_CONFIRMATION = runpy.run_path(
    str(
        _ROOT
        / "scripts/benchmark/run_phase5_external_confirmation_campaign.py"
    )
)
_TERMINAL = _CONFIRMATION["_TERMINAL"]


def scaled_campaign_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Replace only the approved population literals on a campaign model."""
    return create_model(
        f"PostFailure{historical_model.__name__}",
        __base__=historical_model,
        image_count=(Literal[2400], ...),
        run_count=(Literal[12000], ...),
    )


def _configure_terminal_launcher(registry_path: Path) -> dict[str, Any]:
    """Install population, identity, and two-resource-lane seams."""
    confirmation_globals = _CONFIRMATION[
        "_confirmation_request_builder"
    ].__globals__
    confirmation_globals.update(
        {
            "_PROTOCOL_PATH": _PROTOCOL_PATH,
            "_DECISION_PATH": _DECISION_PATH,
            "_REGISTRY_PATH": _REGISTRY_PATH,
            "_RUNNER_PATHS": dict(_RUNNER_PATHS),
            "_MATERIALIZE_CODE": _MATERIALIZE_CODE,
            "_IMAGE_COUNT": _IMAGE_COUNT,
            "_RUN_COUNT": _RUN_COUNT,
            "_HELPERS": _HELPERS,
            "__file__": str(Path(__file__)),
        }
    )
    terminal = _TERMINAL
    globals_ = terminal["_run"].__globals__
    globals_["load_phase_five_external_comparison_protocol"] = _HELPERS[
        "load_post_failure_protocol"
    ]
    globals_["load_phase_five_external_execution_decision"] = _HELPERS[
        "load_post_failure_execution_decision"
    ]
    globals_["_RUNNER_PATHS"] = dict(_RUNNER_PATHS)
    globals_["_MATERIALIZE_CODE"] = _MATERIALIZE_CODE
    globals_["__file__"] = str(Path(__file__))
    scaled_request = scaled_campaign_model(terminal["CampaignRequest"])
    terminal["CampaignRequest"] = scaled_request
    globals_["CampaignRequest"] = scaled_request
    scaled_terminal = scaled_campaign_model(terminal["TerminalCampaignResult"])
    terminal["TerminalCampaignResult"] = scaled_terminal
    globals_["TerminalCampaignResult"] = scaled_terminal
    request_model, request_builder = _CONFIRMATION[
        "_confirmation_request_builder"
    ](terminal)
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
        registry = _HELPERS["load_post_failure_endpoint_registry"](
            registry_path
        )
        if launcher_path.resolve() != Path(__file__).resolve():
            raise ValueError("unexpected post-failure launcher path")
        if registry["launcher_path"] != (
            "scripts/benchmark/run_phase5_external_post_failure_campaign.py"
        ):
            raise ValueError("post-failure launcher registry path changed")
        if registry["launcher_sha256"] != _HELPERS["file_sha256"](
            launcher_path
        ):
            raise ValueError("post-failure launcher checksum changed")
        return terminal_validate(
            repository_root,
            protocol_path,
            decision_path,
            base_review_path,
            terminal_launcher,
        )

    globals_["_validate_decision_bindings"] = validate_decision_bindings
    globals_["materializer_container_command"] = _CONFIRMATION[
        "materializer_container_command"
    ]
    globals_["runner_container_command"] = _CONFIRMATION[
        "runner_container_command"
    ]
    globals_["execute_campaign_runs"] = _CONFIRMATION[
        "execute_confirmation_runs"
    ]
    return terminal


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
    return _CONFIRMATION["_arguments"](
        repository_root=repository_root,
        output=output,
        images=images,
        resume=resume,
        preflight_only=preflight_only,
        podman_executable=podman_executable,
    )


def preflight_post_failure_campaign(
    *,
    repository_root: Path,
    output: Path,
    images: dict[str, str],
    podman_executable: str = "podman",
) -> None:
    """Run the complete no-write preflight only after named authorization."""
    decision = _HELPERS["load_post_failure_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError("post-failure execution is not authorized")
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
    """Parse one post-failure campaign invocation."""
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
    """Reject pending state, then delegate one complete fresh campaign."""
    parsed = _parse_args()
    repository_root = cast(Path, parsed.repository_root).resolve()
    decision = _HELPERS["load_post_failure_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError("post-failure execution is not authorized")
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
