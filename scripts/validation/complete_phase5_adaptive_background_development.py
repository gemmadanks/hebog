#!/usr/bin/env python3
"""Complete the adaptive-background lane from preserved serial results."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    AdaptiveExecutorComparison,
    build_adaptive_runtime_identity,
    evaluate_adaptive_development,
    installed_adaptive_runtime_identity,
)
from hebog.validation.datasets import DatasetManifest
from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).resolve().parents[2]
_PARENT_RUNNER = (
    _ROOT / "scripts/validation/run_phase5_adaptive_background_development.py"
)
_PARENT = runpy.run_path(str(_PARENT_RUNNER))
_MANIFEST = (
    _ROOT
    / "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_ORIGINAL_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-identity-review.json"
)
_ORIGINAL_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-execution-decision.json"
)
_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-completion-repair-pre-review.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-completion-identity-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-completion-execution-decision.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
)
_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/"
    "adaptive-background-development-decision.json"
)
_EXPECTED_INPUTS = 144
_EXPECTED_DASK = 12
_REQUIRED_TASK_FILES = {
    "candidate-products/catalogue.fits",
    "candidate-products/diagnostics.json",
    "candidate-products/rms.fits",
    "candidate-products/source-mask.fits",
    "coarse-work/detection.zarr/.hebog/completed-generation-v1.json",
    "coarse-work/detection.zarr/background/zarr.json",
    "coarse-work/detection.zarr/rms/zarr.json",
    "coarse-work/detection.zarr/source-filtering-mask/zarr.json",
    "coarse-work/detection.zarr/zarr.json",
    "image.fits",
    "observation.json",
}
_EXPECTED_AUTHORIZATION = {
    "candidate_execution_authorized": False,
    "coarse_control_execution_authorized": False,
    "cutover_authorized": False,
    "development_lane_completion_authorized": True,
    "existing_dask_comparison_execution_authorized": True,
    "fresh_qualification_authorized": False,
    "optimization_authorized": False,
    "pybdsf_execution_authorized": False,
    "release_authorized": False,
    "replay_authorized": False,
    "rescoring_authorized": False,
    "source_finding_change_authorized": False,
    "threshold_or_margin_tuning_authorized": False,
    "viewed_data_execution_authorized": False,
}


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one JSON object with a useful fail-closed error."""
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _load_observation(path: Path) -> AdaptiveDevelopmentObservation:
    """Parse the worker's persisted JSON under strict model semantics."""
    try:
        return AdaptiveDevelopmentObservation.model_validate_json(
            path.read_bytes()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise ValueError(f"invalid adaptive observation: {path}") from error


def _expected_completion() -> dict[str, object]:
    """Return the only prospective recovery execution shape."""
    return {
        "candidate_execution_count": 0,
        "coarse_control_execution_count": 0,
        "existing_dask_comparison_execution_count": _EXPECTED_DASK,
        "input_count": _EXPECTED_INPUTS,
        "output": str(_OUTPUT.relative_to(_ROOT)),
        "scratch": str(_SCRATCH),
        "workers": 2,
    }


def _tasks(manifest: DatasetManifest) -> tuple[Any, ...]:
    """Build the exact original task population."""
    return cast(tuple[Any, ...], _PARENT["_tasks"](manifest))


def _validate_observation(
    observation: AdaptiveDevelopmentObservation,
    task: Any,
) -> None:
    """Require persisted identity and metadata to match its frozen task."""
    if (
        observation.input_id != task.input_id
        or observation.cell_id != task.cell.cell_id
        or observation.seed != task.recipe.seed
        or observation.trigger_cohort != task.cell.trigger_cohort
    ):
        raise ValueError("adaptive observation identity or metadata changed")


def _product_inventory(
    scratch: Path,
    tasks: tuple[Any, ...],
) -> tuple[tuple[dict[str, object], ...], int]:
    """Hash every preserved file without interpreting scientific values."""
    expected_ids = {cast(str, task.input_id) for task in tasks}
    if (
        len(tasks) != _EXPECTED_INPUTS
        or not scratch.is_dir()
        or {item.name for item in scratch.iterdir()}
        != {*expected_ids, "progress.log"}
    ):
        raise ValueError("adaptive preserved result set is incomplete")
    progress = scratch / "progress.log"
    if not progress.is_file() or progress.read_bytes():
        raise ValueError("adaptive failed-run progress boundary changed")

    inventory: list[dict[str, object]] = []
    for task in tasks:
        directory = scratch / cast(str, task.input_id)
        if not directory.is_dir() or (directory / "dask-products").exists():
            raise ValueError("adaptive preserved task boundary changed")
        relative_files = {
            str(path.relative_to(directory))
            for path in directory.rglob("*")
            if path.is_file()
        }
        if not relative_files >= _REQUIRED_TASK_FILES:
            raise ValueError(
                "adaptive preserved task artifacts are incomplete"
            )
        for path in sorted(
            (item for item in directory.rglob("*") if item.is_file()),
            key=lambda item: str(item.relative_to(scratch)),
        ):
            if path.is_symlink():
                raise ValueError("adaptive preserved products cannot be links")
            inventory.append(
                {
                    "byte_count": path.stat().st_size,
                    "path": str(path.relative_to(scratch)),
                    "sha256": file_sha256(path),
                }
            )
    return tuple(inventory), len(inventory)


def _verified_observations(
    scratch: Path,
    tasks: tuple[Any, ...],
) -> tuple[AdaptiveDevelopmentObservation, ...]:
    """Validate all preserved JSON records in frozen task order."""
    observations: list[AdaptiveDevelopmentObservation] = []
    for task in tasks:
        observation = _load_observation(
            scratch / cast(str, task.input_id) / "observation.json"
        )
        _validate_observation(observation, task)
        observations.append(observation)
    return tuple(observations)


def inspect_preserved_results(
    scratch: Path,
    manifest_path: Path,
) -> dict[str, object]:
    """Return an identity-only description of the completed serial work."""
    manifest = DatasetManifest.model_validate_json(manifest_path.read_bytes())
    tasks = _tasks(manifest)
    inventory, artifact_count = _product_inventory(scratch, tasks)
    observations = _verified_observations(scratch, tasks)
    return {
        "artifact_count": artifact_count,
        "input_count": len(observations),
        "product_set_sha256": canonical_sha256(inventory),
        "progress_line_count": 0,
        "scratch": str(scratch),
    }


def _verify_original_authority() -> None:
    """Bind the failed run to its frozen identity and consumed approval."""
    identity = _json_object(_ORIGINAL_IDENTITY, label="original identity")
    decision = _json_object(
        _ORIGINAL_EXECUTION_DECISION,
        label="original execution decision",
    )
    _PARENT["_verify_upstream_identities"](_ROOT)
    _PARENT["_verify_frozen_identity"](
        _ROOT,
        identity,
        _MANIFEST,
    )
    if (
        decision.get("status") != "authorized-for-one-development-lane"
        or decision.get("identity_review_sha256")
        != file_sha256(_ORIGINAL_IDENTITY)
        or decision.get("expected_execution_sha256")
        != identity.get("expected_execution_sha256")
    ):
        raise ValueError("original adaptive execution authority changed")


def _verify_paths(arguments: argparse.Namespace) -> None:
    """Require the exact write-once completion paths and worker count."""
    expected_paths = {
        "identity_review": _IDENTITY_REVIEW,
        "manifest": _MANIFEST,
        "original_execution_decision": _ORIGINAL_EXECUTION_DECISION,
        "original_identity": _ORIGINAL_IDENTITY,
        "output": _OUTPUT,
        "repair_pre_review": _REPAIR_PRE_REVIEW,
        "repository_root": _ROOT,
        "scratch": _SCRATCH,
    }
    for field, expected in expected_paths.items():
        actual = cast(Path, getattr(arguments, field)).resolve()
        if actual != expected.resolve():
            raise ValueError(f"adaptive completion {field} changed")
    if arguments.workers != 2:  # noqa: PLR2004
        raise ValueError("adaptive completion requires exactly two workers")
    if arguments.output.exists():
        raise FileExistsError("adaptive terminal decision already exists")


def _verify_completion_identity(identity: Mapping[str, object]) -> None:
    """Require a non-executable identity bound to the recovery programs."""
    authorization = cast(
        Mapping[str, object], identity.get("authorization", {})
    )
    if (
        identity.get("status") != "frozen-non-executable"
        or set(authorization.values()) != {False}
        or identity.get("expected_completion") != _expected_completion()
        or identity.get("expected_execution_sha256")
        != canonical_sha256(_expected_completion())
    ):
        raise ValueError("adaptive completion identity is not frozen")
    original_identity = _json_object(
        _ORIGINAL_IDENTITY,
        label="original identity",
    )
    if identity.get("candidate") != original_identity.get("candidate"):
        raise ValueError("adaptive completion candidate identity changed")

    bindings = cast(Mapping[str, object], identity.get("program_bindings", {}))
    expected_bindings = {
        "completion": Path(__file__).resolve(),
        "parent_runner": _PARENT_RUNNER,
    }
    if set(bindings) != set(expected_bindings):
        raise ValueError("adaptive completion program bindings changed")
    for name, path in expected_bindings.items():
        binding = cast(Mapping[str, object], bindings[name])
        if binding.get("path") != str(path.relative_to(_ROOT)) or binding.get(
            "sha256"
        ) != file_sha256(path):
            raise ValueError("adaptive completion program identity changed")


def verify_completion(arguments: argparse.Namespace) -> dict[str, object]:
    """Verify exact preserved work and recovery bindings without execution."""
    _verify_paths(arguments)
    _verify_original_authority()
    review = _json_object(_REPAIR_PRE_REVIEW, label="repair pre-review")
    identity = _json_object(_IDENTITY_REVIEW, label="completion identity")
    if review.get("status") != "frozen-for-human-review":
        raise ValueError("adaptive completion repair review changed")
    _verify_completion_identity(identity)

    preserved = inspect_preserved_results(
        arguments.scratch, arguments.manifest
    )
    if identity.get("preserved_results") != preserved:
        raise ValueError("adaptive preserved product identity changed")
    if identity.get("runtime") != build_adaptive_runtime_identity(_ROOT):
        raise ValueError("adaptive completion runtime identity changed")
    expected_original = {
        "execution_decision_sha256": file_sha256(_ORIGINAL_EXECUTION_DECISION),
        "identity_review_sha256": file_sha256(_ORIGINAL_IDENTITY),
        "manifest_sha256": file_sha256(_MANIFEST),
        "repair_pre_review_sha256": file_sha256(_REPAIR_PRE_REVIEW),
    }
    if identity.get("original_lane") != expected_original:
        raise ValueError("adaptive original lane provenance changed")
    return {
        "candidate_execution_count": 0,
        "coarse_control_execution_count": 0,
        "existing_dask_comparison_execution_count": _EXPECTED_DASK,
        "identity_review_sha256": file_sha256(_IDENTITY_REVIEW),
        "preserved_results": preserved,
        "status": "pass",
    }


def _verify_execution_authority(
    arguments: argparse.Namespace,
    verified: Mapping[str, object],
) -> dict[str, Any]:
    """Require a new exact approval after the first authority was consumed."""
    decision_path = arguments.execution_decision
    if decision_path is None:
        raise PermissionError("exact adaptive completion approval is required")
    if decision_path.resolve() != _EXECUTION_DECISION.resolve():
        raise PermissionError("adaptive completion decision path changed")
    decision = _json_object(
        decision_path, label="completion execution decision"
    )
    if (
        decision.get("status")
        != "authorized-for-one-development-lane-completion"
        or decision.get("authorization") != _EXPECTED_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != verified.get("identity_review_sha256")
        or decision.get("expected_execution_sha256")
        != canonical_sha256(_expected_completion())
    ):
        raise PermissionError("exact adaptive completion authority is invalid")
    return decision


def _executor_comparisons(
    tasks: tuple[Any, ...],
    observations: tuple[AdaptiveDevelopmentObservation, ...],
    scratch: Path,
    executor: Any,
) -> tuple[AdaptiveExecutorComparison, ...]:
    """Run only the frozen 12-item existing-Dask comparison subset."""
    observations_by_id = {item.input_id: item for item in observations}
    dask_tasks = tuple(
        task
        for task in tasks
        if task.cell.trigger_cohort == "above"
        and task.recipe.seed == task.cell.noise_seeds[0]
    )
    if len(dask_tasks) != _EXPECTED_DASK:
        raise ValueError("adaptive Dask invariance population changed")
    return tuple(
        cast(
            AdaptiveExecutorComparison,
            _PARENT["_dask_comparison"](
                task,
                observations_by_id[cast(str, task.input_id)],
                scratch,
                executor,
            ),
        )
        for task in dask_tasks
    )


def _verify_existing_dask_runtime(
    client: Any,
    expected: object,
    workers: int,
) -> None:
    """Require exactly two caller-owned workers with the frozen runtime."""
    identities: object = client.run(installed_adaptive_runtime_identity)
    if (
        not isinstance(identities, dict)
        or len(identities) != workers
        or any(value != expected for value in identities.values())
    ):
        raise ValueError("adaptive completion Dask runtime identity changed")


def _execute(
    arguments: argparse.Namespace,
    verified: Mapping[str, object],
) -> None:
    """Run only the missing Dask comparisons and publish one decision."""
    if not arguments.dask_scheduler:
        raise ValueError("existing Dask scheduler address is required")
    manifest = DatasetManifest.model_validate_json(
        arguments.manifest.read_bytes()
    )
    tasks = _tasks(manifest)
    observations = _verified_observations(arguments.scratch, tasks)

    from distributed import Client  # noqa: PLC0415

    from hebog.executors import DaskExecutor  # noqa: PLC0415

    original_identity = _json_object(
        arguments.original_identity,
        label="original identity",
    )
    installed_runtime = cast(
        Mapping[str, object], original_identity["runtime"]
    ).get("installed")
    with Client(arguments.dask_scheduler, set_as_default=False) as client:
        _verify_existing_dask_runtime(
            client,
            installed_runtime,
            arguments.workers,
        )
        executor = DaskExecutor(client)
        comparisons = _executor_comparisons(
            tasks,
            observations,
            arguments.scratch,
            executor,
        )
    decision = evaluate_adaptive_development(observations, comparisons)
    decision["provenance"] = {
        "completion_execution_decision_sha256": file_sha256(
            arguments.execution_decision
        ),
        "completion_identity_review_sha256": verified[
            "identity_review_sha256"
        ],
        "completion_program_sha256": file_sha256(Path(__file__)),
        "original_execution_decision_sha256": file_sha256(
            arguments.original_execution_decision
        ),
        "original_identity_review_sha256": file_sha256(
            arguments.original_identity
        ),
        "preserved_product_set_sha256": cast(
            Mapping[str, object], verified["preserved_results"]
        )["product_set_sha256"],
        "repair_pre_review_sha256": file_sha256(arguments.repair_pre_review),
    }
    _PARENT["_atomic_write"](arguments.output, decision)


def main() -> None:
    """Verify the recovery or consume one exact completion approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--manifest", type=Path, default=_MANIFEST)
    parser.add_argument(
        "--original-identity", type=Path, default=_ORIGINAL_IDENTITY
    )
    parser.add_argument(
        "--original-execution-decision",
        type=Path,
        default=_ORIGINAL_EXECUTION_DECISION,
    )
    parser.add_argument(
        "--repair-pre-review", type=Path, default=_REPAIR_PRE_REVIEW
    )
    parser.add_argument(
        "--identity-review", type=Path, default=_IDENTITY_REVIEW
    )
    parser.add_argument("--execution-decision", type=Path)
    parser.add_argument("--scratch", type=Path, default=_SCRATCH)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dask-scheduler")
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    verified = verify_completion(arguments)
    if arguments.verify_only:
        print(json.dumps(verified, allow_nan=False, sort_keys=True))
        return
    _verify_execution_authority(arguments, verified)
    _execute(arguments, verified)


if __name__ == "__main__":
    main()
