#!/usr/bin/env python3
"""Retry the compact sentinel with valid empty PyBDSF output retained."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.executors import SerialExecutor
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe
from hebog.validation.external_runners import file_sha256
from hebog.validation.products import (
    load_fits_plane,
    load_pybdsf_gaussian_catalogue,
)

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_zero: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_sentinel_zero_count_repair"
)
_parent: Any = _zero._parent
_ZERO_RUNNER = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_sentinel_zero_count_repair.py"
)
_ZERO_RUNNER_SHA256 = (
    "8a2e8dc19d40b6f5b2d038f386cecb58fdf2a34bea1b105bff3ffb80cc0307d6"
)
_ZERO_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-zero-count-repair-review.json"
)
_ZERO_IDENTITY_SHA256 = (
    "ad9e2b1c99cffed9f83ac8c567502b418146f6556118d06245eab22a584b068b"
)
_FAILED_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-zero-count-repair-"
    "execution-decision.json"
)
_FAILED_DECISION_SHA256 = (
    "a2d56d69828fea2d105b0db3fa24390eca0ed7c8f3f3fd3a6460caa6a894283a"
)
_FAILED_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/"
    "compact-held-out-sentinel-zero-count-repair.json"
)
_FAILED_OUTPUT_SHA256 = (
    "38438265deac6599ecc80e5ecf034980589df0f761ec48a07dc25e9bf36d6322"
)
_PARENT_CHILD = (
    _ROOT / "scripts/benchmark/run_phase5_compact_held_out_pybdsf.py"
)
_PARENT_CHILD_SHA256 = (
    "a2280496bd92634928ce8740b6cc7c4fa8a842c204f5bc0b6b4c45df4a23fc82"
)
_REPAIRED_CHILD = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_pybdsf_empty_repair.py"
)
_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-pybdsf-empty-repair-review.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-compact-held-out-sentinel-pybdsf-empty-repair"
)
_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/"
    "compact-held-out-sentinel-pybdsf-empty-repair.json"
)


def _require_failed_lineage() -> None:
    """Bind every unchanged wrapper and preserved terminal failure."""
    _zero._require_failed_lineage()
    expected = (
        (_ZERO_RUNNER, _ZERO_RUNNER_SHA256, "zero-count runner"),
        (_ZERO_IDENTITY, _ZERO_IDENTITY_SHA256, "zero-count identity"),
        (_FAILED_DECISION, _FAILED_DECISION_SHA256, "failed decision"),
        (_FAILED_OUTPUT, _FAILED_OUTPUT_SHA256, "failed terminal output"),
        (_PARENT_CHILD, _PARENT_CHILD_SHA256, "parent PyBDSF child"),
    )
    for path, digest, name in expected:
        if not path.is_file() or file_sha256(path) != digest:
            raise ValueError(f"compact sentinel {name} changed")


def _pybdsf_command_empty_safe(**arguments: object) -> tuple[str, ...]:
    """Select only the repaired child while preserving runtime arguments."""
    parent_child = (
        "/repository/scripts/benchmark/run_phase5_compact_held_out_pybdsf.py"
    )
    repaired_child = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_pybdsf_empty_repair.py"
    )
    return tuple(
        repaired_child if item == parent_child else item
        for item in _parent._pybdsf_command(**arguments)
    )


def _load_pybdsf_catalogue_empty_safe(
    output: Path,
    catalogue_count: object,
    labels: np.ndarray[Any, Any],
) -> tuple[object, ...]:
    """Load a catalogue or retain an exact zero-row/zero-label result."""
    if catalogue_count == 0:
        if np.any(labels > 0):
            raise ValueError(
                "empty PyBDSF catalogue has positive native labels"
            )
        return ()
    catalogue = cast(
        tuple[object, ...],
        load_pybdsf_gaussian_catalogue(output / "gaussian-catalogue.fits"),
    )
    if catalogue_count != len(catalogue):
        raise ValueError("released PyBDSF Gaussian population changed")
    return catalogue


def _run_pybdsf_empty_safe(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    case_root: Path,
    execution_decision: Path,
    identity_review: Path,
    repository_root: Path,
    podman_executable: str,
    review: Any,
) -> dict[str, object]:
    """Compile a schema-free catalogue only with zero native support."""
    started = monotonic()
    completed = subprocess.run(
        _pybdsf_command_empty_safe(
            repository_root=repository_root,
            case_root=case_root,
            execution_decision=execution_decision,
            identity_review=identity_review,
            podman_executable=podman_executable,
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "released PyBDSF child failed: " + completed.stderr[-2000:]
        )
    output = case_root / "pybdsf"
    result = _parent._json_object(output / "result.json")
    if (
        result.get("status") != "success"
        or result.get("container_digest") != _parent._PYBDSF_DIGEST
    ):
        raise ValueError("released PyBDSF result identity changed")
    labels = np.asarray(
        load_fits_plane(output / "island-labels.fits"), dtype=np.int32
    )
    catalogue = _load_pybdsf_catalogue_empty_safe(
        output,
        result.get("catalogue_count"),
        labels,
    )
    return _parent.compile_finder_summary(
        dataset=dataset,
        recipe=recipe,
        finder_id="released-pybdsf",
        catalogue=catalogue,
        label_plane=labels,
        header=cast(fits.Header, fits.getheader(case_root / "input.fits")),
        review=review,
        elapsed_seconds=monotonic() - started,
        candidate_revision=None,
        runtime_identity={
            "container_digest": _parent._PYBDSF_DIGEST,
            "dependency_inventory_sha256": result[
                "dependency_inventory_sha256"
            ],
            "version": result["version"],
        },
    )


def _pair_worker_pybdsf_empty_safe(  # noqa: PLR0913, PLR0917
    dataset_document: dict[str, object],
    recipe_document: dict[str, object],
    repository_root: str,
    scratch: str,
    execution_decision: str,
    identity_review: str,
    podman_executable: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one unchanged pair with every evaluator repair installed."""
    dataset = DatasetRecord.model_validate(dataset_document)
    recipe = SyntheticRecipe.model_validate(recipe_document)
    review = _parent.load_phase_five_corrective_a_review(
        Path(repository_root)
        / "config/contracts/phase-5-corrective-a-review.json"
    )
    input_id = f"{dataset.identifier}-seed-{recipe.seed}"
    with TemporaryDirectory(prefix=f".{input_id}.", dir=scratch) as raw:
        case_root = Path(raw)
        input_path = case_root / "input.fits"
        _parent._write_input(input_path, dataset, recipe)
        hebog_summary = _zero._run_hebog_zero_count_safe(
            dataset=dataset,
            recipe=recipe,
            input_path=input_path,
            output=case_root / "hebog",
            executor=SerialExecutor(),
            review=review,
        )
        pybdsf_summary = _run_pybdsf_empty_safe(
            dataset=dataset,
            recipe=recipe,
            case_root=case_root,
            execution_decision=Path(execution_decision),
            identity_review=Path(identity_review),
            repository_root=Path(repository_root),
            podman_executable=podman_executable,
            review=review,
        )
    return hebog_summary, pybdsf_summary


@contextmanager
def _configured_parent() -> Generator[None]:
    """Install the complete evaluator-only repair temporarily."""
    original_hebog = _parent._run_hebog
    original_pybdsf = _parent._run_pybdsf
    original_pair = _parent._pair_worker
    _parent._run_hebog = _zero._run_hebog_zero_count_safe
    _parent._run_pybdsf = _run_pybdsf_empty_safe
    _parent._pair_worker = _pair_worker_pybdsf_empty_safe
    try:
        yield
    finally:
        _parent._run_hebog = original_hebog
        _parent._run_pybdsf = original_pybdsf
        _parent._pair_worker = original_pair


def verify_no_write(arguments: argparse.Namespace) -> dict[str, object]:
    """Run the complete parent preflight plus every failed lineage."""
    _require_failed_lineage()
    verified = _parent.verify_no_write(
        repository_root=arguments.repository_root,
        manifest_path=arguments.manifest,
        identity_path=arguments.identity_review,
        scratch=arguments.scratch,
        output=arguments.output,
        minimum_free_disk_gib=8,
        podman_executable=arguments.podman_executable,
    )
    return {
        **verified,
        "failed_output_sha256": _FAILED_OUTPUT_SHA256,
        "repaired_pybdsf_child_sha256": file_sha256(_REPAIRED_CHILD),
        "zero_count_identity_sha256": _ZERO_IDENTITY_SHA256,
        "zero_count_runner_sha256": _ZERO_RUNNER_SHA256,
    }


def _parse_args() -> argparse.Namespace:
    """Parse the final repair preflight or one-use execution paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--manifest", type=Path, default=_parent._MANIFEST)
    parser.add_argument("--identity-review", type=Path, default=_IDENTITY)
    parser.add_argument("--execution-decision", type=Path)
    parser.add_argument("--scratch", type=Path, default=_SCRATCH)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dask-scheduler-address")
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Preflight or execute the approved PyBDSF empty-result retry."""
    arguments = _parse_args()
    verified = verify_no_write(arguments)
    if arguments.preflight_only:
        print(json.dumps(verified, sort_keys=True))
        return
    identity = _parent.verify_execution_authority(arguments)
    with _configured_parent():
        _parent.execute(arguments, identity)


if __name__ == "__main__":
    main()
