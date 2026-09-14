#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run the final Phase 5 qualification exactly once after approval."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = "config/contracts/phase-5-final-qualification-comparison.json"
_DECISION_PATH = (
    "config/contracts/phase-5-final-qualification-execution-decision.json"
)
_REGISTRY_PATH = (
    "config/contracts/phase-5-final-qualification-endpoint-registry.json"
)
_BASE_REVIEW_PATH = "config/contracts/phase-5-corrective-a-review.json"
_RUNNER_PATHS = {
    "hebog": "scripts/benchmark/run_phase5_final_qualification_hebog.py",
    "released-pybdsf": (
        "scripts/benchmark/run_phase5_final_qualification_pybdsf.py"
    ),
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_final_qualification_pybdsf.py"
    ),
    "aegean": "scripts/benchmark/run_phase5_final_qualification_aegean.py",
}
_MATERIALIZE_CODE = (
    "import runpy,sys; from pathlib import Path; "
    "m=runpy.run_path('/repository/scripts/validation/"
    "phase5_final_qualification_protocol.py'); "
    "import hebog.validation.materialization as h; "
    "h.load_phase_five_external_comparison_protocol="
    "m['load_final_qualification_protocol']; "
    "h.materialize_external_realization(Path(sys.argv[1]), Path(sys.argv[2]), "
    "sys.argv[3], int(sys.argv[4]), Path(sys.argv[5]))"
)
_IMAGE_COUNT = 1688
_RUN_COUNT = 8440
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_final_qualification_protocol.py")
)
_COMPAT_HELPERS = dict(_HELPERS)
_COMPAT_HELPERS.update(
    {
        "load_post_failure_protocol": _HELPERS[
            "load_final_qualification_protocol"
        ],
        "load_post_failure_execution_decision": _HELPERS[
            "load_final_qualification_execution_decision"
        ],
        "load_post_failure_endpoint_registry": _HELPERS[
            "load_final_qualification_endpoint_registry"
        ],
    }
)
_BASE = runpy.run_path(
    str(
        _ROOT
        / "scripts/benchmark/run_phase5_external_post_failure_campaign.py"
    )
)
_TERMINAL = _BASE["_TERMINAL"]


def _configure_terminal_launcher(registry_path: Path) -> dict[str, Any]:
    """Install only final identities and the approved population scale."""
    terminal = _TERMINAL
    original_validate = terminal["_validate_decision_bindings"]
    base_globals = _BASE["_configure_terminal_launcher"].__globals__
    base_globals.update(
        {
            "_PROTOCOL_PATH": _PROTOCOL_PATH,
            "_DECISION_PATH": _DECISION_PATH,
            "_REGISTRY_PATH": _REGISTRY_PATH,
            "_RUNNER_PATHS": dict(_RUNNER_PATHS),
            "_MATERIALIZE_CODE": _MATERIALIZE_CODE,
            "_IMAGE_COUNT": _IMAGE_COUNT,
            "_RUN_COUNT": _RUN_COUNT,
            "_HELPERS": _COMPAT_HELPERS,
            "scaled_campaign_model": _HELPERS[
                "final_qualification_campaign_model"
            ],
            "__file__": str(Path(__file__)),
        }
    )
    configured = _BASE["_configure_terminal_launcher"](registry_path)
    globals_ = configured["_run"].__globals__
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
        """Bind the final launcher before unchanged campaign mechanics."""
        registry = _HELPERS["load_final_qualification_endpoint_registry"](
            registry_path
        )
        if launcher_path.resolve() != Path(__file__).resolve():
            raise ValueError("unexpected final qualification launcher path")
        expected = (
            "scripts/benchmark/run_phase5_final_qualification_campaign.py"
        )
        if registry["launcher_path"] != expected:
            raise ValueError("final qualification launcher path changed")
        if registry["launcher_sha256"] != _HELPERS["file_sha256"](
            launcher_path
        ):
            raise ValueError("final qualification launcher checksum changed")
        return original_validate(
            repository_root,
            protocol_path,
            decision_path,
            base_review_path,
            terminal_launcher,
        )

    globals_["_validate_decision_bindings"] = validate_decision_bindings
    return cast(dict[str, Any], configured)


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
    return _BASE["_arguments"](
        repository_root=repository_root,
        output=output,
        images=images,
        resume=resume,
        preflight_only=preflight_only,
        podman_executable=podman_executable,
    )


def preflight_final_qualification(
    *,
    repository_root: Path,
    output: Path,
    images: dict[str, str],
    podman_executable: str = "podman",
) -> None:
    """Run the no-write preflight only after named authorization."""
    decision = _HELPERS["load_final_qualification_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError("final qualification execution is not authorized")
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
    """Parse one final qualification invocation."""
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
    """Reject pending state, then delegate one complete qualification."""
    parsed = _parse_args()
    repository_root = cast(Path, parsed.repository_root).resolve()
    decision = _HELPERS["load_final_qualification_execution_decision"](
        repository_root / _DECISION_PATH
    )
    if not decision.execution_authorized:
        raise ValueError("final qualification execution is not authorized")
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
