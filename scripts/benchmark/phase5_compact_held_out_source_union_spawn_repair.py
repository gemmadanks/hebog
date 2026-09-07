"""Importable worker seam for the source-union sentinel spawn repair."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any

from hebog.executors import SerialExecutor
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe

_parent: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_source_union_sentinel"
)


def selected_pybdsf_child() -> str:
    """Return the child path selected independently in every process."""
    return (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_"
        "pybdsf_gaussian_count_repair.py"
    )


def _pybdsf_command_spawn_safe(**arguments: object) -> tuple[str, ...]:
    """Build the comparator command with an explicit repaired child."""
    parent_child = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf.py"
    )
    repaired_child = selected_pybdsf_child()
    return tuple(
        repaired_child if item == parent_child else item
        for item in _parent._pybdsf_command(**arguments)
    )


def _run_pybdsf_spawn_safe(  # noqa: PLR0913
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
    """Run the comparator without relying on inherited mutable globals."""
    started = monotonic()
    completed = subprocess.run(
        _pybdsf_command_spawn_safe(
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


def pair_worker(  # noqa: PLR0913, PLR0917
    dataset_document: dict[str, object],
    recipe_document: dict[str, object],
    repository_root: str,
    scratch: str,
    execution_decision: str,
    identity_review: str,
    podman_executable: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one pair from a stable module importable by spawned workers."""
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
        reference = _run_pybdsf_spawn_safe(
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
