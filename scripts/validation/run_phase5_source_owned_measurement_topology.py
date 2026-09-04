#!/usr/bin/env python3
"""Verify or execute the combined adaptive measurement/topology lane."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import pickle
import runpy
from collections.abc import Generator
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np

from hebog import public_api
from hebog.algorithms.extended_measurement import (
    assign_persistent_source_support,
    expand_source_measurement_labels,
)
from hebog.algorithms.multiscale_association import (
    persistent_adjacent_scale_support,
)
from hebog.algorithms.source_association import (
    _apply_terminal_cycle_groups,
    _TerminalCycleEvidence,
)
from hebog.validation import products as validation_products
from hebog.validation.adaptive_background_development import (
    AdaptiveDevelopmentCell,
)
from hebog.validation.adaptive_background_diagnostics import (
    attribute_source_measurement_support,
    attribute_truth_support,
)
from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    AdaptiveExecutorComparison,
    AdaptiveScienceSummary,
    build_adaptive_runtime_identity,
    source_signal_and_truth,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT_REVIEW = Path(
    "config/contracts/phase-5-coarse-measurement-and-topology-pre-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "026e490f1c97b32e0b4940a1af9985b32c33f0debd9b1ffb11f0ac4b826e2d15"
)
_ANALYSIS_CONFIG_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "analysis-config-repair-pre-review.json"
)
_ANALYSIS_CONFIG_REPAIR_REVIEW_SHA256 = (
    "ff687012274695b4e410b643c2e012306c116e438e83186ba824f920c2914a02"
)
_PREDECESSOR_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "process-repair-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "40a9f99f817fbc39ef38ddc9f3bfc6c748040957c7ccf3b1d783ada6ab2691d2"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "analysis-config-repair-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "analysis-config-repair-execution-decision.json"
)
_MANIFEST = Path(
    "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_MANIFEST_SHA256 = (
    "77203f85930a99ffbb5490f93db7073cab434b42c8350d6da864625efd09946b"
)
_PARENT_RUNNER = Path(
    "scripts/validation/run_phase5_adaptive_background_development.py"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-source-owned-measurement-topology-"
    "analysis-config-repair-c28343f"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/"
    "source-owned-measurement-topology-development-decision.json"
)
_CANDIDATE_REVISION = "c28343fb85ae9bd0d1d927701564f93fbe51b659"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "8235e9bcca0e184d1a1597a3dce1f91e9389795370b61f68734b3ee5002b220f"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_EXPECTED_INPUTS = 144
_EXPECTED_DASK = 12
_ATTRIBUTION_SCHEMA_VERSION = 2
_PROGRAM_BINDING_PATHS = {
    "attribution": "src/hebog/validation/adaptive_background_diagnostics.py",
    "background_algorithm": "src/hebog/algorithms/background.py",
    "background_stage": "src/hebog/stages/background.py",
    "detection_stage": "src/hebog/stages/detection.py",
    "freezer": (
        "scripts/validation/freeze_phase5_source_owned_measurement_topology.py"
    ),
    "lane_evaluator": "src/hebog/validation/adaptive_background_lane.py",
    "measurement_algorithm": "src/hebog/algorithms/extended_measurement.py",
    "measurement_composition": "src/hebog/validation/products.py",
    "parent_runner": str(_PARENT_RUNNER),
    "process_repair_freezer": (
        "scripts/validation/"
        "freeze_phase5_source_owned_measurement_topology_process_repair.py"
    ),
    "analysis_config_repair_freezer": (
        "scripts/validation/"
        "freeze_phase5_source_owned_measurement_topology_analysis_config_repair.py"
    ),
    "runner": (
        "scripts/validation/run_phase5_source_owned_measurement_topology.py"
    ),
    "source_association": "src/hebog/algorithms/source_association.py",
    "source_association_model": (
        "src/hebog/data_models/source_association.py"
    ),
}
_FIXTURE_BINDING_PATHS = {
    "adaptive_attribution": (
        "tests/unit/validation/test_adaptive_background_correction.py"
    ),
    "combined_lane": (
        "tests/unit/validation/test_source_owned_measurement_topology_lane.py"
    ),
    "executor_invariance": (
        "tests/integration/test_public_finder_correction_execution.py"
    ),
    "measurement": "tests/unit/test_extended_measurement.py",
    "public_composition": (
        "tests/unit/validation/test_public_finder_correction.py"
    ),
    "source_measurement": (
        "tests/unit/validation/test_reconstructed_source_measurement.py"
    ),
    "topology": "tests/unit/test_source_reconstruction.py",
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
_HIERARCHY_FIELDS = (
    "catalogue_source_count",
    "direct_component_count",
    "persistent_feature_influence_candidate_count",
    "persistent_feature_influence_parent_count",
    "rejected_terminal_cycle_count",
    "terminal_cycle_candidate_count",
    "terminal_cycle_missing_child_resilience_candidate_count",
    "terminal_cycle_missing_child_resilience_parent_count",
    "terminal_cycle_missing_child_resilience_rejected_count",
    "terminal_cycle_parent_count",
    "terminal_persistence_ambiguous_child_count",
    "terminal_persistence_conflict_count",
    "terminal_persistence_displaced_accepted_count",
    "terminal_persistence_displaced_candidate_count",
    "terminal_persistence_missing_child_count",
)

_PARENT = runpy.run_path(str(Path(__file__).parents[2] / _PARENT_RUNNER))
_parent_tasks = _PARENT["_tasks"]
_parent_candidate_products = _PARENT["_candidate_products"]
_parent_coarse_products = _PARENT["_coarse_products"]
_parent_run_serial_task = _PARENT["_run_serial_task"]
_parent_public_config = _PARENT["_public_config"]
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


def _source_stage_attribution(  # noqa: PLR0913
    *,
    source_seed_labels: np.ndarray,
    persistent_support: np.ndarray,
    source_owned_labels: np.ndarray,
    source_measurement_labels: np.ndarray,
    publication_support: np.ndarray,
    hierarchy_diagnostics: Any | None,
) -> dict[str, int]:
    """Return array-free source measurement and topology attribution."""
    record = attribute_source_measurement_support(
        source_seed_labels,
        persistent_support,
        source_owned_labels,
        source_measurement_labels,
        publication_support,
    ).to_record()
    if hierarchy_diagnostics is not None:
        record.update(
            {
                f"hierarchy_{field}": int(
                    getattr(hierarchy_diagnostics, field)
                )
                for field in _HIERARCHY_FIELDS
            }
        )
    return record


@contextmanager
def _captured_science() -> Generator[dict[str, Any]]:
    """Capture image-sized science only until it becomes bounded scalars."""
    from hebog import public_science  # noqa: PLC0415

    captured: dict[str, Any] = {}
    original_analysis = public_api._analyse_image
    original_detection = public_api.run_detection_stage
    original_catalogues = (
        public_science.build_hebog_reconstructed_source_catalogues
    )

    def detection(*args: Any, **kwargs: Any) -> Any:
        result = original_detection(*args, **kwargs)
        captured["detection"] = result
        return result

    def catalogues(*args: Any, **kwargs: Any) -> Any:
        result = original_catalogues(*args, **kwargs)
        image = np.asarray(args[0])
        valid = np.asarray(args[2], dtype=np.bool_)
        component_labels = np.asarray(args[3])
        planes = args[6]
        source_seeds, _ = validation_products._source_label_plane(
            component_labels,
            result.association,
        )
        persistent = persistent_adjacent_scale_support(planes)
        owned = assign_persistent_source_support(
            source_seeds,
            persistent,
            valid,
        )
        measurement = expand_source_measurement_labels(
            owned,
            valid & np.isfinite(image),
            radius_pixels=ceil(
                float(kwargs["measurement_aperture_radius_beams"])
                * float(kwargs["beam_major_fwhm_pixels"])
            ),
        )
        captured["detection_support"] = np.asarray(
            (np.asarray(args[4]) > 0) | np.asarray(args[5], dtype=np.bool_),
            dtype=np.bool_,
        )
        captured["measurement_support"] = np.asarray(
            measurement > 0,
            dtype=np.bool_,
        )
        captured["source_stage_inputs"] = (
            source_seeds,
            persistent,
            owned,
            measurement,
            result.association.hierarchy_diagnostics,
        )
        return result

    def analysis(*args: Any, **kwargs: Any) -> Any:
        if "config" not in kwargs:
            request = args[0] if args else None
            if not str(getattr(request, "run_id", "")).startswith("coarse-"):
                raise ValueError(
                    "analysis config omitted outside legacy coarse control"
                )
            kwargs = {**kwargs, "config": _parent_public_config()}
        result = original_analysis(*args, **kwargs)
        terminal = result.terminal
        source_inputs = captured.pop("source_stage_inputs", None)
        if terminal is not None and source_inputs is not None:
            publication = np.asarray(
                terminal.detection.retained_mask,
                dtype=np.bool_,
            )
            captured["publication_support"] = publication
            (
                source_seeds,
                persistent,
                owned,
                measurement,
                hierarchy_diagnostics,
            ) = source_inputs
            captured["source_stage"] = _source_stage_attribution(
                source_seed_labels=source_seeds,
                persistent_support=persistent,
                source_owned_labels=owned,
                source_measurement_labels=measurement,
                publication_support=publication,
                hierarchy_diagnostics=hierarchy_diagnostics,
            )
        captured["products"] = result
        return result

    public_api.run_detection_stage = detection
    public_api._analyse_image = analysis
    public_science.build_hebog_reconstructed_source_catalogues = catalogues
    try:
        yield captured
    finally:
        public_science.build_hebog_reconstructed_source_catalogues = (
            original_catalogues
        )
        public_api.run_detection_stage = original_detection
        public_api._analyse_image = original_analysis


def _candidate_products(*args: Any, **kwargs: Any) -> Any:
    """Run one candidate while reducing transient stage attribution."""
    with _captured_science() as captured:
        result = _parent_candidate_products(*args, **kwargs)
    required = {"detection", "detection_support", "source_stage"}
    if not required.issubset(captured):
        raise ValueError(
            "combined candidate attribution capture is incomplete"
        )
    _captured_candidate.clear()
    _captured_candidate.update(captured)
    return result


def _coarse_products(*args: Any, **kwargs: Any) -> Any:
    """Run one coarse control while retaining its transient support."""
    with _captured_science() as captured:
        result = _parent_coarse_products(*args, **kwargs)
    if "detection_support" not in captured:
        raise ValueError("combined coarse attribution capture is incomplete")
    _captured_coarse.clear()
    _captured_coarse.update(captured)
    return result


_parent_run_serial_task.__globals__["_candidate_products"] = (
    _candidate_products
)
_parent_run_serial_task.__globals__["_coarse_products"] = _coarse_products


def _protection_counts(detection: Any) -> dict[str, int]:
    """Return bounded source-protection counters."""
    grids = detection.background_rms_grids
    return {
        "protected_pixel_count": int(grids.adaptive_protected_pixel_count),
        "protected_window_count": int(grids.adaptive_protected_window_count),
    }


def _attribution_record(truth: np.ndarray) -> dict[str, int]:
    """Reduce one paired execution to bounded stage-local counts."""
    record = attribute_truth_support(
        np.asarray(truth, dtype=np.bool_),
        _captured_coarse["detection_support"],
        _captured_candidate["detection_support"],
        _captured_candidate["measurement_support"],
        _captured_candidate["publication_support"],
    ).to_record()
    record.update(_protection_counts(_captured_candidate["detection"]))
    record.update(cast(dict[str, int], _captured_candidate["source_stage"]))
    return record


def _run_serial_task(task: Any, scratch: Path) -> dict[str, Any]:
    """Run one pair and retain only bounded attribution beside products."""
    _captured_candidate.clear()
    _captured_coarse.clear()
    payload = _parent_run_serial_task(task, scratch)
    _, truth, _ = source_signal_and_truth(task.recipe)
    record = {
        "schema_version": _ATTRIBUTION_SCHEMA_VERSION,
        "input_id": task.input_id,
        **_attribution_record(truth),
    }
    (scratch / task.input_id / "attribution.json").write_text(
        json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"attribution": record, "observation": payload}


def _serial_task_payload(task: Any) -> dict[str, object]:
    """Remove the run-path-only task class before process serialization."""
    return {
        "cell": asdict(task.cell),
        "dataset": task.dataset.model_dump(mode="json"),
        "input_id": task.input_id,
        "recipe": task.recipe.model_dump(mode="json"),
    }


def _task_from_payload(payload: dict[str, Any]) -> SimpleNamespace:
    """Reconstruct one exact task from importable validated records."""
    expected_fields = {"cell", "dataset", "input_id", "recipe"}
    if set(payload) != expected_fields or not isinstance(
        payload["input_id"], str
    ):
        raise ValueError("combined process task payload is malformed")
    cell_fields = payload["cell"]
    if not isinstance(cell_fields, dict):
        raise ValueError("combined process task cell is malformed")
    return SimpleNamespace(
        cell=AdaptiveDevelopmentCell(**cell_fields),
        dataset=DatasetRecord.model_validate(payload["dataset"]),
        input_id=payload["input_id"],
        recipe=SyntheticRecipe.model_validate(payload["recipe"]),
    )


def _run_serial_payload(
    payload: dict[str, Any],
    scratch: Path,
) -> dict[str, Any]:
    """Run one process-safe serialized task through the exact serial path."""
    return _run_serial_task(_task_from_payload(payload), scratch)


def _process_payload_sha256(payload: dict[str, Any]) -> str:
    """Reconstruct and reserialize one task without running science."""
    return canonical_sha256(_serial_task_payload(_task_from_payload(payload)))


def _verify_process_payload(
    payload: dict[str, Any],
    *,
    spawn_process: bool,
) -> str:
    """Verify pickle and, for exact CLI preflight, a real worker boundary."""
    restored = pickle.loads(pickle.dumps(payload))
    expected = canonical_sha256(payload)
    if _process_payload_sha256(restored) != expected:
        raise ValueError("combined process payload round trip changed")
    if not spawn_process:
        return "pickle-pass"
    with ProcessPoolExecutor(max_workers=1) as executor:
        observed = executor.submit(
            _process_payload_sha256,
            restored,
        ).result()
    if observed != expected:
        raise ValueError("combined spawned process payload changed")
    return "spawn-pass"


def _science_sha256(
    summary: AdaptiveScienceSummary,
    positions: tuple[tuple[float, float], ...],
    activation_intersects_truth: bool,
    protection_counts: dict[str, int],
    source_stage: dict[str, int],
) -> str:
    """Hash exact science and executor-invariant bounded diagnostics."""
    return canonical_sha256(
        {
            "adaptive": summary.model_dump(mode="json"),
            "adaptive_activation_intersects_truth": (
                activation_intersects_truth
            ),
            "adaptive_candidate_positions_yx": positions,
            "source_protection": protection_counts,
            "source_stage": source_stage,
        }
    )


def _source_fields(record: dict[str, Any]) -> dict[str, int]:
    """Select exact candidate-owned source-stage diagnostics."""
    return {
        key: cast(int, value)
        for key, value in record.items()
        if key.startswith(("source_", "hierarchy_"))
        or key
        in {
            "competing_support_component_count",
            "measurement_only_pixel_count",
            "measurement_publication_overlap_count",
            "persistent_support_pixel_count",
            "publication_only_pixel_count",
            "publication_pixel_count",
        }
    }


def _dask_comparison(
    task: Any,
    serial: AdaptiveDevelopmentObservation,
    serial_attribution: dict[str, Any],
    scratch: Path,
    executor: Any,
) -> AdaptiveExecutorComparison:
    """Repeat one candidate on an existing scheduler and compare exactly."""
    input_path = scratch / task.input_id / "image.fits"
    summary, positions = _candidate_products(
        task,
        input_path,
        scratch / task.input_id / "dask-products",
        executor,
    )
    _, truth, _ = source_signal_and_truth(task.recipe)
    dask_intersects = _parent_activation_intersects_truth(positions, truth)
    serial_counts = {
        "protected_pixel_count": cast(
            int, serial_attribution["protected_pixel_count"]
        ),
        "protected_window_count": cast(
            int, serial_attribution["protected_window_count"]
        ),
    }
    return AdaptiveExecutorComparison(
        input_id=task.input_id,
        serial_science_sha256=_science_sha256(
            serial.adaptive,
            serial.adaptive_candidate_positions_yx,
            serial.adaptive_activation_intersects_truth,
            serial_counts,
            _source_fields(serial_attribution),
        ),
        existing_dask_science_sha256=_science_sha256(
            summary,
            positions,
            dask_intersects,
            _protection_counts(_captured_candidate["detection"]),
            cast(dict[str, int], _captured_candidate["source_stage"]),
        ),
    )


def _attribution_summary(
    records: tuple[dict[str, Any], ...],
) -> dict[str, object]:
    """Aggregate one canonical bounded attribution record per input."""
    if len(records) != _EXPECTED_INPUTS:
        raise ValueError("combined attribution requires exactly 144 records")
    if len({record.get("input_id") for record in records}) != len(records):
        raise ValueError("combined attribution record is duplicated")
    numeric_fields = tuple(
        sorted(
            key
            for key, value in records[0].items()
            if key not in {"input_id", "schema_version"}
            and isinstance(value, int)
            and not isinstance(value, bool)
        )
    )
    expected_keys = {*numeric_fields, "input_id", "schema_version"}
    if any(
        set(record) != expected_keys
        or record.get("schema_version") != _ATTRIBUTION_SCHEMA_VERSION
        or any(isinstance(value, np.ndarray) for value in record.values())
        for record in records
    ):
        raise ValueError("combined attribution schema changed")
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
    """Return the exact future execution shape."""
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


def _verify_programs(repository_root: Path, identity: dict[str, Any]) -> None:
    """Verify the implementation record and every executable program."""
    implementation = _object_field(
        identity,
        "implementation_decision",
        label="combined implementation binding",
    )
    if implementation.get("path") != str(_IMPLEMENTATION) or file_sha256(
        repository_root / _IMPLEMENTATION
    ) != implementation.get("sha256"):
        raise ValueError("combined implementation decision changed")
    bindings = _object_field(identity, "program_bindings", label="programs")
    if set(bindings) != set(_PROGRAM_BINDING_PATHS):
        raise ValueError("combined program set changed")
    for name, expected_path in _PROGRAM_BINDING_PATHS.items():
        binding = bindings.get(name)
        if (
            not isinstance(binding, dict)
            or binding.get("path") != expected_path
        ):
            raise ValueError("combined program binding is malformed")
        if file_sha256(repository_root / expected_path) != binding.get(
            "sha256"
        ):
            raise ValueError("combined program changed")
    fixture_bindings = _object_field(
        identity,
        "fixture_bindings",
        label="fixtures",
    )
    if set(fixture_bindings) != set(_FIXTURE_BINDING_PATHS):
        raise ValueError("combined fixture set changed")
    for name, expected_path in _FIXTURE_BINDING_PATHS.items():
        binding = fixture_bindings.get(name)
        if (
            not isinstance(binding, dict)
            or binding.get("path") != expected_path
        ):
            raise ValueError("combined fixture binding is malformed")
        if file_sha256(repository_root / expected_path) != binding.get(
            "sha256"
        ):
            raise ValueError("combined fixture changed")


def _verify_public_identity(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the exact current public composition and candidate."""
    binding = _object_field(
        identity,
        "public_identity",
        label="combined public identity binding",
    )
    if binding.get("path") != str(_PUBLIC_IDENTITY) or file_sha256(
        repository_root / _PUBLIC_IDENTITY
    ) != binding.get("sha256"):
        raise ValueError("combined public identity changed")
    review = _json_object(
        repository_root / _PUBLIC_IDENTITY,
        label="combined public identity",
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
        raise ValueError("combined public candidate changed")
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
                raise ValueError("combined public source changed")


def _verify_analysis_config_repair_identity(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify both failed invocations and the config-only successor."""
    if (
        file_sha256(repository_root / _ANALYSIS_CONFIG_REPAIR_REVIEW)
        != _ANALYSIS_CONFIG_REPAIR_REVIEW_SHA256
    ):
        raise ValueError("combined config-repair review identity changed")
    authorization = _object_field(
        identity,
        "authorization",
        label="combined authorization",
    )
    if identity.get("status") != "frozen-non-executable" or set(
        authorization.values()
    ) != {False}:
        raise ValueError("combined authorization changed")
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "entrypoint": "hebog.find_sources",
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if identity.get("candidate") != expected_candidate:
        raise ValueError("combined candidate changed")
    predecessor = _object_field(
        identity,
        "predecessor_identity",
        label="combined predecessor identity",
    )
    if (
        predecessor.get("path") != str(_PREDECESSOR_IDENTITY)
        or predecessor.get("sha256") != _PREDECESSOR_IDENTITY_SHA256
        or file_sha256(repository_root / _PREDECESSOR_IDENTITY)
        != _PREDECESSOR_IDENTITY_SHA256
    ):
        raise ValueError("combined predecessor identity changed")
    repair = _object_field(
        identity,
        "analysis_config_repair",
        label="combined analysis config repair",
    )
    if repair.get("review") != {
        "path": str(_ANALYSIS_CONFIG_REPAIR_REVIEW),
        "sha256": _ANALYSIS_CONFIG_REPAIR_REVIEW_SHA256,
    }:
        raise ValueError("combined config-repair binding changed")


def _verify_frozen_identity(
    repository_root: Path,
    manifest_path: Path,
    identity: dict[str, Any],
) -> None:
    """Verify candidate, programs, population, runtime, and no authority."""
    if file_sha256(repository_root / _ROOT_REVIEW) != _ROOT_REVIEW_SHA256:
        raise ValueError("combined root-cause review identity changed")
    _verify_analysis_config_repair_identity(repository_root, identity)
    if source_tree_sha256(repository_root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("combined source tree changed")
    _verify_public_identity(repository_root, identity)
    _verify_programs(repository_root, identity)
    population = _object_field(identity, "population", label="population")
    if (
        manifest_path.resolve() != (repository_root / _MANIFEST).resolve()
        or file_sha256(manifest_path) != _MANIFEST_SHA256
        or population.get("manifest_sha256") != _MANIFEST_SHA256
    ):
        raise ValueError("combined population changed")
    if identity.get("runtime") != build_adaptive_runtime_identity(
        repository_root
    ):
        raise ValueError("combined runtime changed")
    expected = _expected_execution()
    if identity.get("expected_execution") != expected or identity.get(
        "expected_execution_sha256"
    ) != canonical_sha256(expected):
        raise ValueError("combined execution shape changed")


def _verify_fixture_seams() -> str:
    """Exercise exact bounded measurement and reconciliation seams."""
    seeds = np.asarray([[1, 0, 0, 2]], dtype=np.int32)
    persistent = np.asarray([[True, True, True, True]])
    valid = np.ones(seeds.shape, dtype=np.bool_)
    owned = assign_persistent_source_support(seeds, persistent, valid)
    measurement = expand_source_measurement_labels(
        owned,
        valid,
        radius_pixels=1,
    )
    parent = frozenset(("component-a", "component-b", "component-c"))
    groups, evidence = _apply_terminal_cycle_groups(
        tuple(frozenset((item,)) for item in sorted(parent)),
        _TerminalCycleEvidence(
            groups=(parent,),
            candidate_count=1,
            rejected_count=0,
            missing_child_resilience_candidate_count=1,
            missing_child_resilience_parent_count=1,
            missing_child_resilience_groups=(parent,),
        ),
    )
    attribution = _source_stage_attribution(
        source_seed_labels=seeds,
        persistent_support=persistent,
        source_owned_labels=owned,
        source_measurement_labels=measurement,
        publication_support=np.asarray(seeds > 0),
        hierarchy_diagnostics=None,
    )
    if (
        groups != (parent,)
        or evidence.accepted_parent_count != 1
        or evidence.missing_child_resilience_parent_count != 1
        or attribution["source_unowned_persistent_pixel_count"] != 0
    ):
        raise ValueError("combined fixture seam verification failed")
    return canonical_sha256(
        {
            "attribution": attribution,
            "measurement_labels": measurement.tolist(),
            "owned_labels": owned.tolist(),
            "parent": sorted(parent),
        }
    )


def verify_no_write(  # noqa: PLR0913
    *,
    repository_root: Path,
    manifest_path: Path,
    identity_path: Path,
    scratch: Path,
    output: Path,
    enforce_execution_paths: bool = True,
    verify_process_pool: bool = False,
) -> dict[str, object]:
    """Verify every planned execution and exact seam without starting it."""
    if scratch.exists() or output.exists():
        raise FileExistsError("combined lane namespace must be absent")
    if enforce_execution_paths and (
        manifest_path.resolve() != (repository_root / _MANIFEST).resolve()
        or identity_path.resolve() != (repository_root / _IDENTITY).resolve()
        or scratch.resolve() != _SCRATCH.resolve()
        or output.resolve() != (repository_root / _OUTPUT).resolve()
    ):
        raise ValueError("combined execution path changed")
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
        raise ValueError("combined execution count changed")
    process_payload_status = _verify_process_payload(
        _serial_task_payload(tasks[0]),
        spawn_process=verify_process_pool,
    )
    return {
        "status": "pass",
        "attribution_schema_version": _ATTRIBUTION_SCHEMA_VERSION,
        "candidate_execution_count": len(tasks),
        "coarse_control_execution_count": len(tasks),
        "existing_dask_execution_count": len(dask_tasks),
        "candidate_execution_started": False,
        "fixture_seam_status": "pass",
        "fixture_seam_sha256": _verify_fixture_seams(),
        "identity_review_sha256": file_sha256(identity_path),
        "manifest_sha256": file_sha256(manifest_path),
        "process_payload_status": process_payload_status,
    }


def _verify_execution_authority(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Require a separate exact one-use execution decision."""
    if arguments.workers != 2:  # noqa: PLR2004
        raise PermissionError("combined lane requires exactly two workers")
    root = arguments.repository_root.resolve()
    if arguments.execution_decision is None:
        raise PermissionError("an exact execution decision is required")
    expected_paths = {
        "decision": (arguments.execution_decision, root / _EXECUTION_DECISION),
        "identity": (arguments.identity_review, root / _IDENTITY),
        "manifest": (arguments.manifest, root / _MANIFEST),
        "output": (arguments.output, root / _OUTPUT),
        "scratch": (arguments.scratch, _SCRATCH),
    }
    if any(
        supplied.resolve() != expected.resolve()
        for supplied, expected in expected_paths.values()
    ):
        raise PermissionError("combined execution path changed")
    decision = _json_object(
        arguments.execution_decision,
        label="combined execution decision",
    )
    authorization = _object_field(decision, "authorization", label="authority")
    expected_sha256 = canonical_sha256(_expected_execution())
    identity = _json_object(arguments.identity_review, label="identity review")
    if (
        decision.get("status") != "authorized-for-one-development-lane"
        or authorization != _EXPECTED_EXECUTION_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != file_sha256(arguments.identity_review)
        or decision.get("expected_execution_sha256") != expected_sha256
        or identity.get("expected_execution_sha256") != expected_sha256
    ):
        raise PermissionError("exact combined execution authority is invalid")
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
            executor.submit(
                _run_serial_payload,
                _serial_task_payload(task),
                arguments.scratch,
            ): task
            for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            observation = AdaptiveDevelopmentObservation.model_validate_json(
                json.dumps(result["observation"], allow_nan=False)
            )
            record = cast(dict[str, Any], result["attribution"])
            if record.get("input_id") != observation.input_id:
                raise ValueError("combined attribution input identity changed")
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
    """Verify frozen identities or consume one later exact approval."""
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
        raise ValueError("combined lane workers must be positive")
    verification = verify_no_write(
        repository_root=arguments.repository_root,
        manifest_path=arguments.manifest,
        identity_path=arguments.identity_review,
        scratch=arguments.scratch,
        output=arguments.output,
        verify_process_pool=True,
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
