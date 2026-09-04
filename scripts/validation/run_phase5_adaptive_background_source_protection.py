#!/usr/bin/env python3
"""Verify or execute the source-protected adaptive-background lane."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
from collections.abc import Generator
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from hebog import public_api
from hebog.validation.adaptive_background_diagnostics import (
    attribute_truth_support,
)
from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    AdaptiveExecutorComparison,
    AdaptiveScienceSummary,
    build_adaptive_runtime_identity,
    source_signal_and_truth,
)
from hebog.validation.datasets import DatasetManifest
from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-adaptive-background-root-cause-pre-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "8e00269924b50c1b52188beefcb177e50d9035e25a69755d5d2d31ddead3d902"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-implementation-decision.json"
)
_MANIFEST = Path(
    "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_MANIFEST_SHA256 = (
    "77203f85930a99ffbb5490f93db7073cab434b42c8350d6da864625efd09946b"
)
_IDENTITY = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/"
    "phase-5-adaptive-background-source-protection-execution-decision.json"
)
_PARENT_RUNNER = Path(
    "scripts/validation/run_phase5_adaptive_background_development.py"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-source-protection-7ebde58"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/"
    "adaptive-background-source-protection-development-decision.json"
)
_CANDIDATE_REVISION = "7ebde589c82e153e0f7d475a8469c120138be4da"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_EXPECTED_INPUTS = 144
_EXPECTED_DASK = 12
_ATTRIBUTION_SCHEMA_VERSION = 1
_PROGRAM_BINDING_PATHS = {
    "attribution": "src/hebog/validation/adaptive_background_diagnostics.py",
    "background_algorithm": "src/hebog/algorithms/background.py",
    "background_stage": "src/hebog/stages/background.py",
    "detection_stage": "src/hebog/stages/detection.py",
    "freezer": (
        "scripts/validation/"
        "freeze_phase5_adaptive_background_source_protection.py"
    ),
    "lane_evaluator": "src/hebog/validation/adaptive_background_lane.py",
    "parent_runner": str(_PARENT_RUNNER),
    "runner": (
        "scripts/validation/"
        "run_phase5_adaptive_background_source_protection.py"
    ),
}
_EXPECTED_EXECUTION_AUTHORIZATION = {
    "candidate_execution_authorized": True,
    "coarse_control_execution_authorized": True,
    "cutover_authorized": False,
    "development_lane_execution_authorized": True,
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

_PARENT = runpy.run_path(str(Path(__file__).parents[2] / _PARENT_RUNNER))
_parent_tasks = _PARENT["_tasks"]
_parent_candidate_products = _PARENT["_candidate_products"]
_parent_coarse_products = _PARENT["_coarse_products"]
_parent_run_serial_task = _PARENT["_run_serial_task"]
_parent_evaluate = _PARENT["evaluate_adaptive_development"]
_parent_activation_intersects_truth = _PARENT["_activation_intersects_truth"]
_parent_verify_existing_dask_runtime = _PARENT["_verify_existing_dask_runtime"]
_parent_atomic_write = _PARENT["_atomic_write"]

_captured_candidate: dict[str, Any] = {}
_captured_coarse: dict[str, Any] = {}


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _object_field(
    value: dict[str, Any], field: str, *, label: str
) -> dict[str, Any]:
    """Return one required nested JSON object."""
    nested: object = value.get(field)
    if not isinstance(nested, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], nested)


@contextmanager
def _captured_science() -> Generator[dict[str, Any]]:
    """Capture transient science only long enough to reduce it to scalars."""
    captured: dict[str, Any] = {}
    original_analysis = public_api._analyse_image
    original_detection = public_api.run_detection_stage

    def detection(*args: Any, **kwargs: Any) -> Any:
        result = original_detection(*args, **kwargs)
        captured["detection"] = result
        return result

    def analysis(*args: Any, **kwargs: Any) -> Any:
        result = original_analysis(*args, **kwargs)
        captured["products"] = result
        return result

    public_api.run_detection_stage = detection
    public_api._analyse_image = analysis
    try:
        yield captured
    finally:
        public_api.run_detection_stage = original_detection
        public_api._analyse_image = original_analysis


def _candidate_products(*args: Any, **kwargs: Any) -> Any:
    """Run the parent candidate and retain transient attribution inputs."""
    with _captured_science() as captured:
        result = _parent_candidate_products(*args, **kwargs)
    if "products" not in captured or "detection" not in captured:
        raise ValueError("candidate attribution capture is incomplete")
    _captured_candidate.clear()
    _captured_candidate.update(captured)
    return result


def _coarse_products(*args: Any, **kwargs: Any) -> Any:
    """Run the parent control and retain transient attribution inputs."""
    with _captured_science() as captured:
        result = _parent_coarse_products(*args, **kwargs)
    if "products" not in captured:
        raise ValueError("coarse attribution capture is incomplete")
    _captured_coarse.clear()
    _captured_coarse.update(captured)
    return result


_parent_run_serial_task.__globals__["_candidate_products"] = (
    _candidate_products
)
_parent_run_serial_task.__globals__["_coarse_products"] = _coarse_products


def _detection_support(products: Any) -> np.ndarray:
    """Return direct-or-multiscale support from one terminal product."""
    terminal = getattr(products, "terminal", None)
    if terminal is None:
        raise ValueError("adaptive attribution terminal products are absent")
    return np.asarray(
        (terminal.direct_component_labels > 0)
        | terminal.significant_multiscale_support,
        dtype=np.bool_,
    )


def _attribution_record(
    *,
    truth: np.ndarray,
    coarse_products: Any,
    candidate_products: Any,
    candidate_detection: Any,
) -> dict[str, int]:
    """Reduce one execution pair to bounded stage-local counts."""
    coarse_support = _detection_support(coarse_products)
    adaptive_support = _detection_support(candidate_products)
    terminal = candidate_products.terminal
    measurement_support = np.asarray(
        terminal.measurement_component_labels > 0,
        dtype=np.bool_,
    )
    publication_support = np.asarray(
        terminal.detection.retained_mask,
        dtype=np.bool_,
    )
    record = attribute_truth_support(
        np.asarray(truth, dtype=np.bool_),
        coarse_support,
        adaptive_support,
        measurement_support,
        publication_support,
    ).to_record()
    grids = candidate_detection.background_rms_grids
    record.update(
        {
            "protected_pixel_count": int(grids.adaptive_protected_pixel_count),
            "protected_window_count": int(
                grids.adaptive_protected_window_count
            ),
        }
    )
    return record


def _run_serial_task(task: Any, scratch: Path) -> dict[str, Any]:
    """Run one parent observation and add an array-free attribution sidecar."""
    _captured_candidate.clear()
    _captured_coarse.clear()
    payload = _parent_run_serial_task(task, scratch)
    _, truth, _ = source_signal_and_truth(task.recipe)
    record = _attribution_record(
        truth=truth,
        coarse_products=_captured_coarse.get("products"),
        candidate_products=_captured_candidate.get("products"),
        candidate_detection=_captured_candidate.get("detection"),
    )
    sidecar = {
        "schema_version": _ATTRIBUTION_SCHEMA_VERSION,
        "input_id": task.input_id,
        **record,
    }
    (scratch / task.input_id / "attribution.json").write_text(
        json.dumps(sidecar, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"attribution": sidecar, "observation": payload}


def _protection_counts(detection: Any) -> dict[str, int]:
    """Return the source-protection counters used in executor comparison."""
    grids = detection.background_rms_grids
    return {
        "protected_pixel_count": int(grids.adaptive_protected_pixel_count),
        "protected_window_count": int(grids.adaptive_protected_window_count),
    }


def _science_sha256(
    summary: AdaptiveScienceSummary,
    positions: tuple[tuple[float, float], ...],
    activation_intersects_truth: bool,
    protection_counts: dict[str, int],
) -> str:
    """Hash science and protection telemetry, excluding runtime metadata."""
    return canonical_sha256(
        {
            "adaptive": summary.model_dump(mode="json"),
            "adaptive_activation_intersects_truth": (
                activation_intersects_truth
            ),
            "adaptive_candidate_positions_yx": positions,
            "source_protection": protection_counts,
        }
    )


def _dask_comparison(
    task: Any,
    serial: AdaptiveDevelopmentObservation,
    serial_attribution: dict[str, Any],
    scratch: Path,
    executor: Any,
) -> AdaptiveExecutorComparison:
    """Repeat one candidate on an existing scheduler and compare exactly."""
    input_path = scratch / task.input_id / "image.fits"
    with _captured_science() as captured:
        summary, positions = _parent_candidate_products(
            task,
            input_path,
            scratch / task.input_id / "dask-products",
            executor,
        )
    detection = captured.get("detection")
    if detection is None:
        raise ValueError("Dask source-protection capture is incomplete")
    _, truth, _ = source_signal_and_truth(task.recipe)
    dask_intersects = _parent_activation_intersects_truth(positions, truth)
    serial_counts = {
        "protected_pixel_count": serial_attribution["protected_pixel_count"],
        "protected_window_count": serial_attribution["protected_window_count"],
    }
    return AdaptiveExecutorComparison(
        input_id=task.input_id,
        serial_science_sha256=_science_sha256(
            serial.adaptive,
            serial.adaptive_candidate_positions_yx,
            serial.adaptive_activation_intersects_truth,
            serial_counts,
        ),
        existing_dask_science_sha256=_science_sha256(
            summary,
            positions,
            dask_intersects,
            _protection_counts(detection),
        ),
    )


def _attribution_summary(
    records: tuple[dict[str, Any], ...],
) -> dict[str, object]:
    """Aggregate bounded non-binding attribution without losing provenance."""
    if len(records) != _EXPECTED_INPUTS:
        raise ValueError("adaptive attribution requires exactly 144 records")
    if len({record.get("input_id") for record in records}) != len(records):
        raise ValueError("adaptive attribution record is duplicated")
    numeric_fields = tuple(
        sorted(
            key
            for key, value in records[0].items()
            if key not in {"input_id", "schema_version"}
            and isinstance(value, int)
            and not isinstance(value, bool)
        )
    )
    if any(
        record.get("schema_version") != _ATTRIBUTION_SCHEMA_VERSION
        or tuple(
            sorted(
                key
                for key, value in record.items()
                if key not in {"input_id", "schema_version"}
                and isinstance(value, int)
                and not isinstance(value, bool)
            )
        )
        != numeric_fields
        for record in records
    ):
        raise ValueError("adaptive attribution schema changed")
    return {
        "schema_version": _ATTRIBUTION_SCHEMA_VERSION,
        "status": "non-binding-diagnostic",
        "record_count": len(records),
        "record_set_sha256": canonical_sha256(records),
        "totals": {
            field: sum(cast(int, record[field]) for record in records)
            for field in numeric_fields
        },
        "records": records,
    }


def _expected_execution() -> dict[str, object]:
    """Return the exact path-independent future execution shape."""
    return {
        "candidate_executions": _EXPECTED_INPUTS,
        "coarse_control_executions": _EXPECTED_INPUTS,
        "existing_dask_executions": _EXPECTED_DASK,
        "existing_dask_scheduler": "caller-owned-runtime-address",
        "identity_review": str(_IDENTITY),
        "manifest": str(_MANIFEST),
        "output": str(_OUTPUT),
        "scratch": str(_SCRATCH),
        "workers": 2,
    }


def _verify_public_identity(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the exact current public science and source-protection policy."""
    binding = _object_field(
        identity,
        "public_identity",
        label="adaptive source-protection public identity binding",
    )
    if binding.get("path") != str(_PUBLIC_IDENTITY) or file_sha256(
        repository_root / _PUBLIC_IDENTITY
    ) != binding.get("sha256"):
        raise ValueError("adaptive source-protection public identity changed")
    review = _json_object(
        repository_root / _PUBLIC_IDENTITY,
        label="adaptive source-protection public identity",
    )
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if (
        review.get("status") != "frozen-non-executable"
        or review.get("algorithm_candidate") != expected_candidate
        or review.get("scientific_composition") != public_api._COMPOSITION_NAME
        or review.get("scientific_composition_sha256")
        != public_api._scientific_composition_sha256()
    ):
        raise ValueError("adaptive source-protection public candidate changed")
    for field in ("interface_file_sha256", "scientific_module_sha256"):
        values = _object_field(review, field, label=field)
        for identifier, expected_sha256 in values.items():
            path = (
                repository_root / identifier
                if field == "interface_file_sha256"
                else repository_root
                / Path("src", *identifier.split(".")).with_suffix(".py")
            )
            if file_sha256(path) != expected_sha256:
                raise ValueError("adaptive source-protection source changed")


def _verify_frozen_identity(
    repository_root: Path,
    manifest_path: Path,
    identity: dict[str, Any],
) -> None:
    """Verify candidate, programs, population, runtime, and no authority."""
    if file_sha256(repository_root / _ROOT_REVIEW) != _ROOT_REVIEW_SHA256:
        raise ValueError("adaptive root-cause review identity changed")
    authorization = _object_field(
        identity,
        "authorization",
        label="adaptive source-protection authorization",
    )
    if identity.get("status") != "frozen-non-executable" or set(
        authorization.values()
    ) != {False}:
        raise ValueError("adaptive source-protection authorization changed")
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "entrypoint": "hebog.find_sources",
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if identity.get("candidate") != expected_candidate:
        raise ValueError("adaptive source-protection candidate changed")
    _verify_public_identity(repository_root, identity)
    _verify_programs(repository_root, identity)
    _verify_population_runtime(repository_root, manifest_path, identity)


def _verify_programs(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the implementation decision and every executable program."""
    implementation = _object_field(
        identity,
        "implementation_decision",
        label="adaptive source-protection implementation binding",
    )
    if implementation.get("path") != str(_IMPLEMENTATION) or file_sha256(
        repository_root / _IMPLEMENTATION
    ) != implementation.get("sha256"):
        raise ValueError("adaptive source-protection implementation changed")
    bindings = _object_field(identity, "program_bindings", label="programs")
    if set(bindings) != set(_PROGRAM_BINDING_PATHS):
        raise ValueError("adaptive source-protection program set changed")
    for name, expected_path in _PROGRAM_BINDING_PATHS.items():
        binding = bindings.get(name)
        if (
            not isinstance(binding, dict)
            or binding.get("path") != expected_path
        ):
            raise ValueError("adaptive source-protection program malformed")
        if file_sha256(repository_root / expected_path) != binding.get(
            "sha256"
        ):
            raise ValueError("adaptive source-protection program changed")


def _verify_population_runtime(
    repository_root: Path,
    manifest_path: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the fixed population, environment, and execution shape."""
    population = _object_field(identity, "population", label="population")
    if (
        manifest_path.resolve() != (repository_root / _MANIFEST).resolve()
        or file_sha256(manifest_path) != _MANIFEST_SHA256
        or population.get("manifest_sha256") != _MANIFEST_SHA256
    ):
        raise ValueError("adaptive source-protection population changed")
    if identity.get("runtime") != build_adaptive_runtime_identity(
        repository_root
    ):
        raise ValueError("adaptive source-protection runtime changed")
    expected = _expected_execution()
    if identity.get("expected_execution") != expected or identity.get(
        "expected_execution_sha256"
    ) != canonical_sha256(expected):
        raise ValueError("adaptive source-protection execution shape changed")


def verify_no_write(  # noqa: PLR0913
    *,
    repository_root: Path,
    manifest_path: Path,
    identity_path: Path,
    scratch: Path,
    output: Path,
    enforce_execution_paths: bool = True,
) -> dict[str, object]:
    """Verify all 300 planned executions without starting science."""
    if scratch.exists() or output.exists():
        raise FileExistsError(
            "adaptive source-protection namespace must be absent"
        )
    if enforce_execution_paths and (
        manifest_path.resolve() != (repository_root / _MANIFEST).resolve()
        or identity_path.resolve() != (repository_root / _IDENTITY).resolve()
        or scratch.resolve() != _SCRATCH.resolve()
        or output.resolve() != (repository_root / _OUTPUT).resolve()
    ):
        raise ValueError("adaptive source-protection execution path changed")
    identity = _json_object(identity_path, label="identity review")
    _verify_frozen_identity(repository_root, manifest_path, identity)
    manifest = DatasetManifest.model_validate_json(manifest_path.read_bytes())
    tasks = _parent_tasks(manifest)
    dask_tasks = tuple(
        task
        for task in tasks
        if task.cell.trigger_cohort == "above"
        and task.recipe.seed == task.cell.noise_seeds[0]
    )
    if len(tasks) != _EXPECTED_INPUTS or len(dask_tasks) != _EXPECTED_DASK:
        raise ValueError("adaptive source-protection execution count changed")
    return {
        "status": "pass",
        "attribution_schema_version": _ATTRIBUTION_SCHEMA_VERSION,
        "candidate_execution_count": len(tasks),
        "coarse_control_execution_count": len(tasks),
        "existing_dask_execution_count": len(dask_tasks),
        "candidate_execution_started": False,
        "identity_review_sha256": file_sha256(identity_path),
        "manifest_sha256": file_sha256(manifest_path),
    }


def _verify_execution_authority(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Require a separate exact one-use execution decision."""
    if arguments.workers != 2:  # noqa: PLR2004
        raise PermissionError(
            "adaptive source-protection lane requires exactly two workers"
        )
    root = arguments.repository_root.resolve()
    expected_paths = {
        "decision": (arguments.execution_decision, root / _EXECUTION_DECISION),
        "identity": (arguments.identity_review, root / _IDENTITY),
        "manifest": (arguments.manifest, root / _MANIFEST),
        "output": (arguments.output, root / _OUTPUT),
        "scratch": (arguments.scratch, _SCRATCH),
    }
    if arguments.execution_decision is None:
        raise PermissionError("an exact execution decision is required")
    if any(
        supplied.resolve() != expected.resolve()
        for supplied, expected in expected_paths.values()
    ):
        raise PermissionError(
            "adaptive source-protection execution path changed"
        )
    decision = _json_object(
        arguments.execution_decision,
        label="adaptive source-protection execution decision",
    )
    authorization = _object_field(decision, "authorization", label="authority")
    expected_execution_sha256 = canonical_sha256(_expected_execution())
    identity = _json_object(arguments.identity_review, label="identity review")
    if (
        decision.get("status") != "authorized-for-one-development-lane"
        or authorization != _EXPECTED_EXECUTION_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != file_sha256(arguments.identity_review)
        or decision.get("expected_execution_sha256")
        != expected_execution_sha256
        or identity.get("expected_execution_sha256")
        != expected_execution_sha256
    ):
        raise PermissionError(
            "exact adaptive source-protection execution authority is invalid"
        )
    return decision


def _execute(arguments: argparse.Namespace, tasks: tuple[Any, ...]) -> None:
    """Execute one separately approved lane and atomically publish it."""
    if not arguments.dask_scheduler:
        raise ValueError("existing Dask scheduler address is required")
    arguments.scratch.mkdir(parents=True, exist_ok=False)
    observations: dict[str, AdaptiveDevelopmentObservation] = {}
    attribution: dict[str, dict[str, Any]] = {}
    progress_path = arguments.scratch / "progress.log"
    with (
        progress_path.open("x", encoding="utf-8") as progress,
        ProcessPoolExecutor(max_workers=arguments.workers) as executor,
    ):
        futures = {
            executor.submit(_run_serial_task, task, arguments.scratch): task
            for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            observation = AdaptiveDevelopmentObservation.model_validate_json(
                json.dumps(result["observation"], allow_nan=False)
            )
            record = cast(dict[str, Any], result["attribution"])
            if record.get("input_id") != observation.input_id:
                raise ValueError("adaptive attribution input identity changed")
            observations[observation.input_id] = observation
            attribution[observation.input_id] = record
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{len(tasks)} "
                f"input={observation.input_id}\n"
            )
            progress.flush()
    ordered = tuple(observations[task.input_id] for task in tasks)
    ordered_attribution = tuple(attribution[task.input_id] for task in tasks)
    dask_tasks = tuple(
        task
        for task in tasks
        if task.cell.trigger_cohort == "above"
        and task.recipe.seed == task.cell.noise_seeds[0]
    )
    from distributed import Client  # noqa: PLC0415

    from hebog.executors import DaskExecutor  # noqa: PLC0415

    identity = _json_object(arguments.identity_review, label="identity review")
    runtime = _object_field(identity, "runtime", label="runtime")
    with Client(arguments.dask_scheduler, set_as_default=False) as client:
        _parent_verify_existing_dask_runtime(client, runtime.get("installed"))
        executor = DaskExecutor(client)
        comparisons = tuple(
            _dask_comparison(
                task,
                observations[task.input_id],
                attribution[task.input_id],
                arguments.scratch,
                executor,
            )
            for task in dask_tasks
        )
    decision = _parent_evaluate(ordered, comparisons)
    decision["attribution_diagnostics"] = _attribution_summary(
        ordered_attribution
    )
    decision["provenance"] = {
        "execution_decision_sha256": file_sha256(arguments.execution_decision),
        "identity_review_sha256": file_sha256(arguments.identity_review),
        "manifest_sha256": file_sha256(arguments.manifest),
    }
    _parent_atomic_write(arguments.output, decision)


def main() -> None:
    """Verify frozen identities or consume one future exact approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--identity-review", required=True, type=Path)
    parser.add_argument("--execution-decision", type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dask-scheduler")
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.repository_root = arguments.repository_root.resolve()
    if arguments.workers < 1:
        raise ValueError("adaptive source-protection workers must be positive")
    verification = verify_no_write(
        repository_root=arguments.repository_root,
        manifest_path=arguments.manifest,
        identity_path=arguments.identity_review,
        scratch=arguments.scratch,
        output=arguments.output,
    )
    if arguments.verify_only:
        print(json.dumps(verification, allow_nan=False, sort_keys=True))
        return
    _verify_execution_authority(arguments)
    manifest = DatasetManifest.model_validate_json(
        arguments.manifest.read_bytes()
    )
    _execute(arguments, _parent_tasks(manifest))


if __name__ == "__main__":
    main()
