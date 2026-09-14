#!/usr/bin/env python3
"""Run the fresh source-support-linkage repair replication lane."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np

from hebog.validation.adaptive_background_development import (
    build_adaptive_replication_matrix,
)
from hebog.validation.adaptive_background_lane import (
    build_adaptive_replication_manifest,
    evaluate_phase_five_adaptive_risk_replication,
    input_identifier,
    truth_linked_source_support_topology,
)
from hebog.validation.datasets import (
    DatasetManifest,
    iter_dataset_recipes,
)
from hebog.validation.external_runners import canonical_sha256

_REPOSITORY_ROOT = Path(__file__).parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))
_base_runner = importlib.import_module(
    "scripts.validation.run_phase5_source_owned_measurement_topology"
)

_BASE_RUNNER = Path(
    "scripts/validation/run_phase5_source_owned_measurement_topology.py"
)
_ROOT_REVIEW = Path(
    "config/contracts/phase-5-source-owned-source-support-linkage-"
    "terminal-root-cause-review.json"
)
_ROOT_REVIEW_SHA256 = (
    "25f6bf0f0f1a41964ba59e7030579d13487c633cbd09ba5948dad3b6e5915462"
)
_PREDECESSOR_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "binding-repair-identity-review.json"
)
_PREDECESSOR_IDENTITY_SHA256 = (
    "25fbd5c333a93d58adfaf819c30d1f5bb1f9e43d4d33a9d83df4b4d923066449"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "public-interface-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "validated-retry-implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "validated-retry-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "validated-retry-execution-decision.json"
)
_PROCESS_REPAIR_REVIEW = Path(
    "config/contracts/phase-5-source-support-linkage-replication-"
    "binding-repair-pre-review.json"
)
_PROCESS_REPAIR_REVIEW_SHA256 = (
    "d8163967a876ccaed188d9bcfe2c536d2642e3cba99ff573e7d26197d7e8a974"
)
_MANIFEST = Path(
    "config/contracts/phase-5-source-support-linkage-replication-manifest.json"
)
_MANIFEST_SHA256 = (
    "8d5394770e592ad925201bdead76bd6821986d19473935bcf54c61466e1a7cb9"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-source-support-linkage-replication-"
    "validated-retry-0b9e132"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/"
    "source-support-linkage-replication-development-decision.json"
)
_CANDIDATE_REVISION = "0b9e13299f3fbbd42af0dea4f70155a802a8441d"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_EXPECTED_INPUTS = 144
_EXPECTED_DASK = 12
_PROGRAM_BINDING_PATHS = {
    "attribution": ("src/hebog/validation/adaptive_background_diagnostics.py"),
    "background_algorithm": "src/hebog/algorithms/background.py",
    "background_stage": "src/hebog/stages/background.py",
    "base_runner": str(_BASE_RUNNER),
    "detection_stage": "src/hebog/stages/detection.py",
    "freezer": (
        "scripts/validation/"
        "freeze_phase5_source_support_linkage_replication_validated_retry.py"
    ),
    "lane_design": ("src/hebog/validation/adaptive_background_development.py"),
    "lane_evaluator": "src/hebog/validation/adaptive_background_lane.py",
    "measurement_algorithm": ("src/hebog/algorithms/extended_measurement.py"),
    "measurement_composition": "src/hebog/validation/products.py",
    "parent_runner": (
        "scripts/validation/run_phase5_adaptive_background_development.py"
    ),
    "runner": (
        "scripts/validation/run_phase5_source_support_linkage_replication.py"
    ),
    "source_association": "src/hebog/algorithms/source_association.py",
    "source_association_model": (
        "src/hebog/data_models/source_association.py"
    ),
}
_FIXTURE_BINDING_PATHS = {
    "adaptive_lane": (
        "tests/unit/validation/test_adaptive_background_lane.py"
    ),
    "combined_lane": (
        "tests/unit/validation/test_source_owned_measurement_topology_lane.py"
    ),
    "executor_invariance": (
        "tests/integration/test_public_finder_correction_execution.py"
    ),
    "footprint_guard_lane": (
        "tests/unit/validation/test_source_owned_footprint_guard_lane.py"
    ),
    "replication_lane": (
        "tests/unit/validation/test_source_support_linkage_replication_lane.py"
    ),
    "terminal_review": (
        "tests/unit/validation/test_source_support_linkage_terminal_review.py"
    ),
}

_BASE = vars(_base_runner)
_BASE_GLOBALS = cast(dict[str, Any], _BASE["verify_no_write"].__globals__)
_ORIGINALS_ATTRIBUTE = "_source_linkage_replication_overlay_originals"
if not hasattr(_base_runner, _ORIGINALS_ATTRIBUTE):
    setattr(
        _base_runner,
        _ORIGINALS_ATTRIBUTE,
        {
            "fixture_seams": _BASE_GLOBALS["_verify_fixture_seams"],
            "task_class": _BASE_GLOBALS["_PARENT"]["_tasks"].__globals__[
                "_DevelopmentTask"
            ],
        },
    )
_ORIGINALS = cast(dict[str, Any], getattr(_base_runner, _ORIGINALS_ATTRIBUTE))
_BASE_FIXTURE_SEAMS = _ORIGINALS["fixture_seams"]
_TASK_CLASS = _ORIGINALS["task_class"]


def _replication_tasks(manifest: DatasetManifest) -> tuple[Any, ...]:
    """Pair the exact replication manifest with its fresh matrix."""
    expected = build_adaptive_replication_manifest()
    if manifest != expected:
        raise ValueError("source-linkage replication manifest changed")
    matrix = build_adaptive_replication_matrix()
    tasks = tuple(
        _TASK_CLASS(
            cell=cell,
            dataset=dataset,
            recipe=recipe,
            input_id=input_identifier(cell, recipe.seed),
        )
        for cell, dataset in zip(matrix, manifest.datasets, strict=True)
        for recipe in iter_dataset_recipes(dataset)
    )
    if len(tasks) != _EXPECTED_INPUTS or len(
        {task.input_id for task in tasks}
    ) != len(tasks):
        raise ValueError("source-linkage replication population changed")
    return tasks


def _replication_fixture_seams() -> str:
    """Exercise the existing runner plus the prospective linkage boundary."""
    base_sha256 = cast(str, _BASE_FIXTURE_SEAMS())
    truth = np.ones((3, 7), dtype=np.bool_)
    labels = np.zeros(truth.shape, dtype=np.int32)
    labels[0, :2] = 1
    labels[1, :] = 2
    topology = truth_linked_source_support_topology(
        ("boundary-graze", "owned-fragment"),
        labels,
        {1: "boundary-graze", 2: "owned-fragment"},
        truth,
        minimum_truth_overlap_pixels=7,
    )
    if topology.truth_linked_source_indices != (
        1,
    ) or topology.unmatched_source_indices != (0,):
        raise ValueError("replication truth-linkage seam changed")
    return canonical_sha256(
        {
            "base_fixture_seam_sha256": base_sha256,
            "minimum_truth_overlap_pixels": 7,
            "truth_linked_source_indices": (
                topology.truth_linked_source_indices
            ),
            "unmatched_source_indices": topology.unmatched_source_indices,
        }
    )


_BASE_GLOBALS.update(
    {
        "_CANDIDATE_CONFIGURATION_SHA256": (_CANDIDATE_CONFIGURATION_SHA256),
        "_CANDIDATE_REVISION": _CANDIDATE_REVISION,
        "_CANDIDATE_SOURCE_TREE_SHA256": _CANDIDATE_SOURCE_TREE_SHA256,
        "_EXECUTION_DECISION": _EXECUTION_DECISION,
        "_FIXTURE_BINDING_PATHS": _FIXTURE_BINDING_PATHS,
        "_IDENTITY": _IDENTITY,
        "_IMPLEMENTATION": _IMPLEMENTATION,
        "_MANIFEST": _MANIFEST,
        "_MANIFEST_SHA256": _MANIFEST_SHA256,
        "_OUTPUT": _OUTPUT,
        "_PREDECESSOR_IDENTITY": _PREDECESSOR_IDENTITY,
        "_PREDECESSOR_IDENTITY_SHA256": _PREDECESSOR_IDENTITY_SHA256,
        "_PROCESS_REPAIR_REVIEW": _PROCESS_REPAIR_REVIEW,
        "_PROCESS_REPAIR_REVIEW_SHA256": _PROCESS_REPAIR_REVIEW_SHA256,
        "_PROGRAM_BINDING_PATHS": _PROGRAM_BINDING_PATHS,
        "_PUBLIC_IDENTITY": _PUBLIC_IDENTITY,
        "_ROOT_REVIEW": _ROOT_REVIEW,
        "_ROOT_REVIEW_SHA256": _ROOT_REVIEW_SHA256,
        "_SCRATCH": _SCRATCH,
        "_lane_evaluate": evaluate_phase_five_adaptive_risk_replication,
        "_parent_tasks": _replication_tasks,
        "_verify_fixture_seams": _replication_fixture_seams,
    }
)

_EXPECTED_EXECUTION_AUTHORIZATION = _BASE_GLOBALS[
    "_EXPECTED_EXECUTION_AUTHORIZATION"
]
verify_no_write = _BASE["verify_no_write"]
_expected_execution = _BASE["_expected_execution"]
_execute = _BASE["_execute"]
_verify_execution_authority = _BASE["_verify_execution_authority"]


def main() -> None:
    """Use the proven CLI after retargeting every frozen lane binding."""
    _BASE["main"]()


if __name__ == "__main__":
    main()
