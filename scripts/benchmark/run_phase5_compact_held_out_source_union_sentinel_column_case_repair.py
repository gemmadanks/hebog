#!/usr/bin/env python3
"""Retry the source-union sentinel with the PyBDSF column case repaired."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
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
from typing import Any

from hebog.executors import SerialExecutor
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_parent: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_source_union_sentinel"
)
_PARENT_RUNNER = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_sentinel.py"
)
_PARENT_RUNNER_SHA256 = (
    "697230c1d0612bb5ec3873511a5dc0ad233ff36fc93d9bcb72ac4eb402198f96"
)
_PARENT_CHILD = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_pybdsf.py"
)
_PARENT_CHILD_SHA256 = (
    "ec9ae57014f6a79c167d3a012627477fd48f66623eb65d714609989840698db2"
)
_PARENT_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-identity-review.json"
)
_PARENT_IDENTITY_SHA256 = (
    "7d133492cce629bac299bcfb3220ed1a72fc19d10ea3c05665f277253d481df7"
)
_FAILED_DECISION = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-execution-decision.json"
)
_FAILED_DECISION_SHA256 = (
    "a767b7180398a891f28f466b4a17ec69178dc8915127f0ccb893994b52913cee"
)
_FAILED_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/compact-held-out-source-union-sentinel.json"
)
_FAILED_OUTPUT_SHA256 = (
    "331e36a5afee90e799a281186000ae1c760f46388fd2662514eba379503a4b9f"
)
_REPAIRED_CHILD = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_pybdsf_column_case_repair.py"
)
_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-column-case-repair-identity-review.json"
)
_SCRATCH = Path(
    "/private/tmp/"
    "hebog-phase5-compact-held-out-source-union-sentinel-column-case-repair"
)
_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-column-case-repair.json"
)


def _require_failed_lineage() -> None:
    """Bind the exact failed attempt and unchanged parent programs."""
    expected = (
        (_PARENT_RUNNER, _PARENT_RUNNER_SHA256, "parent runner"),
        (_PARENT_CHILD, _PARENT_CHILD_SHA256, "parent PyBDSF child"),
        (_PARENT_IDENTITY, _PARENT_IDENTITY_SHA256, "parent identity"),
        (_FAILED_DECISION, _FAILED_DECISION_SHA256, "failed decision"),
        (_FAILED_OUTPUT, _FAILED_OUTPUT_SHA256, "failed terminal"),
    )
    for path, digest, name in expected:
        if not path.is_file() or file_sha256(path) != digest:
            raise ValueError(f"source-union sentinel {name} changed")


def _pybdsf_command_column_case_safe(**arguments: object) -> tuple[str, ...]:
    """Select only the isolated child with the exact native schema."""
    parent_child = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf.py"
    )
    repaired_child = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf_column_case_repair.py"
    )
    return tuple(
        repaired_child if item == parent_child else item
        for item in _parent._pybdsf_command(**arguments)
    )


def _run_pybdsf_column_case_safe(  # noqa: PLR0913
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
    """Run the unchanged comparator through the repaired child boundary."""
    started = monotonic()
    completed = subprocess.run(
        _pybdsf_command_column_case_safe(
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
    result = _parent._json_object(case_root / "pybdsf/result.json")
    return _parent._compile_projection(
        dataset=dataset,
        recipe=recipe,
        projection=_parent._load_pybdsf_projection(case_root / "pybdsf"),
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


def _pair_worker_column_case_safe(  # noqa: PLR0913, PLR0917
    dataset_document: dict[str, object],
    recipe_document: dict[str, object],
    repository_root: str,
    scratch: str,
    execution_decision: str,
    identity_review: str,
    podman_executable: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one unchanged pair with only the comparator schema repaired."""
    dataset = DatasetRecord.model_validate(dataset_document)
    recipe = SyntheticRecipe.model_validate(recipe_document)
    root = Path(repository_root)
    review = _parent.load_phase_five_corrective_a_review(
        root / "config/contracts/phase-5-corrective-a-review.json"
    )
    input_id = f"{dataset.identifier}-seed-{recipe.seed}"
    with TemporaryDirectory(prefix=f".{input_id}.", dir=scratch) as raw:
        case_root = Path(raw)
        input_path = case_root / "input.fits"
        _parent._write_input(input_path, dataset, recipe)
        current = _parent._run_hebog(
            dataset=dataset,
            recipe=recipe,
            input_path=input_path,
            output=case_root / "hebog",
            executor=SerialExecutor(),
            review=review,
        )
        reference = _run_pybdsf_column_case_safe(
            dataset=dataset,
            recipe=recipe,
            case_root=case_root,
            execution_decision=Path(execution_decision),
            identity_review=Path(identity_review),
            repository_root=root,
            podman_executable=podman_executable,
            review=review,
        )
    return current, reference


@contextmanager
def _configured_parent() -> Generator[None]:
    """Install only the repaired comparator execution seams."""
    original_pybdsf = _parent._run_pybdsf
    original_pair = _parent._pair_worker
    _parent._run_pybdsf = _run_pybdsf_column_case_safe
    _parent._pair_worker = _pair_worker_column_case_safe
    try:
        yield
    finally:
        _parent._run_pybdsf = original_pybdsf
        _parent._pair_worker = original_pair


def verify_no_write(arguments: argparse.Namespace) -> dict[str, object]:
    """Validate the parent contract and exact failed lineage without work."""
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
        "failed_terminal_sha256": _FAILED_OUTPUT_SHA256,
        "repaired_child_sha256": file_sha256(_REPAIRED_CHILD),
    }


def _parse_args() -> argparse.Namespace:
    """Parse the replacement preflight or one-use execution inputs."""
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
    """Preflight or consume the one-use comparator schema repair."""
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
