#!/usr/bin/env python3
"""Retry the compact sentinel with valid empty results retained."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.data_models import SourceFinderRequest
from hebog.executors import Executor, SerialExecutor
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PRIOR_RUNNER = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_sentinel_identity_repair.py"
)
_PRIOR_RUNNER_SHA256 = (
    "37afb35dab47c4885df509fa57ac150733aa793d6afaf5fae2d0f4dc329847ec"
)
_PRIOR_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-identity-repair-review.json"
)
_PRIOR_IDENTITY_SHA256 = (
    "3b22cb480544e243d0eebf220662e78e273b86ef405a9027ad247eee60d956a1"
)
_FAILED_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-identity-repair-execution-decision.json"
)
_FAILED_DECISION_SHA256 = (
    "0b4856f8347ed95b2763fd174b84eaf511a7304ba0abcc5aa00c0673799f5ee2"
)
_FAILED_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/"
    "compact-held-out-sentinel-identity-repair.json"
)
_FAILED_OUTPUT_SHA256 = (
    "441f312f09884357b50a3167a767db583028a2bbbc369d1a34bdec6c1d236c46"
)
_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-empty-result-repair-review.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-compact-held-out-sentinel-empty-result-repair"
)
_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/"
    "compact-held-out-sentinel-empty-result-repair.json"
)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_prior: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_sentinel_identity_repair"
)
_parent: Any = _prior._parent


def _require_failed_lineage() -> None:
    """Bind both unchanged runners and both preserved failed terminals."""
    _prior._require_failed_lineage()
    expected = (
        (_PRIOR_RUNNER, _PRIOR_RUNNER_SHA256, "prior repair runner"),
        (_PRIOR_IDENTITY, _PRIOR_IDENTITY_SHA256, "prior repair identity"),
        (_FAILED_DECISION, _FAILED_DECISION_SHA256, "failed decision"),
        (_FAILED_OUTPUT, _FAILED_OUTPUT_SHA256, "failed terminal output"),
    )
    for path, digest, name in expected:
        if not path.is_file() or file_sha256(path) != digest:
            raise ValueError(f"compact sentinel {name} changed")


def _run_hebog_empty_safe(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    input_path: Path,
    output: Path,
    executor: Executor,
    review: Any,
) -> dict[str, object]:
    """Compile exact public components while retaining valid empty science."""
    started = monotonic()
    run_id = f"sentinel-{dataset.identifier}-{recipe.seed}"
    with _parent._captured_science() as captured:
        result = _parent.hebog.find_sources(
            SourceFinderRequest(input_path, output, run_id),
            _parent._CONFIG,
            executor,
        )
    if len(captured) != 1:
        raise ValueError("public Hebog terminal products are unavailable")
    products = captured[0]
    terminal = products.terminal
    if terminal is None:
        counts = (
            result.source_count,
            result.gaussian_component_count,
            result.island_count,
        )
        if counts != (0, 0, 0):
            raise ValueError(
                "public Hebog terminal is absent but public counts are not "
                "empty"
            )
        rms = np.asarray(products.rms)
        if rms.shape != recipe.shape_yx:
            raise ValueError("public Hebog empty-result RMS shape changed")
        if np.any(np.isfinite(rms) & (rms > 0)):
            raise ValueError(
                "public Hebog terminal is absent while RMS remains "
                "scientifically usable"
            )
        catalogue = ()
        labels = np.zeros(recipe.shape_yx, dtype=np.int32)
    else:
        catalogue = tuple(terminal.component_catalogue)
        if result.gaussian_component_count != len(catalogue):
            raise ValueError("public Hebog Gaussian population changed")
        catalogue = _prior._repair.link_stable_component_ownership(
            catalogue,
            terminal.source_association.components,
            terminal.measurement_component_labels,
        )
        labels = terminal.measurement_component_labels
    return _parent.compile_finder_summary(
        dataset=dataset,
        recipe=recipe,
        finder_id="current-hebog",
        catalogue=catalogue,
        label_plane=labels,
        header=cast(fits.Header, fits.getheader(input_path)),
        review=review,
        elapsed_seconds=monotonic() - started,
        candidate_revision=_parent._CANDIDATE_REVISION,
        runtime_identity={
            "configuration_sha256": (_parent._CANDIDATE_CONFIGURATION_SHA256),
            "source_tree_sha256": _parent._CANDIDATE_SOURCE_TREE_SHA256,
        },
    )


def _pair_worker_empty_safe(  # noqa: PLR0913, PLR0917
    dataset_document: dict[str, object],
    recipe_document: dict[str, object],
    repository_root: str,
    scratch: str,
    execution_decision: str,
    identity_review: str,
    podman_executable: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one unchanged pair with both evaluator repairs installed."""
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
        hebog_summary = _run_hebog_empty_safe(
            dataset=dataset,
            recipe=recipe,
            input_path=input_path,
            output=case_root / "hebog",
            executor=SerialExecutor(),
            review=review,
        )
        pybdsf_summary = _parent._run_pybdsf(
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
    original_pair = _parent._pair_worker
    _parent._run_hebog = _run_hebog_empty_safe
    _parent._pair_worker = _pair_worker_empty_safe
    try:
        yield
    finally:
        _parent._run_hebog = original_hebog
        _parent._pair_worker = original_pair


def verify_no_write(arguments: argparse.Namespace) -> dict[str, object]:
    """Run the complete parent preflight plus both failed lineages."""
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
        "prior_identity_sha256": _PRIOR_IDENTITY_SHA256,
        "prior_runner_sha256": _PRIOR_RUNNER_SHA256,
    }


def _parse_args() -> argparse.Namespace:
    """Parse the replacement preflight or one-use execution paths."""
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
    """Preflight or execute the single approved empty-result retry."""
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
