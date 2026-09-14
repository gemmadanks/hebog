#!/usr/bin/env python3
"""Retry the compact sentinel with exact stable-identity linkage repaired."""

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

from astropy.io import fits

from hebog.data_models import SourceFinderRequest
from hebog.executors import Executor, SerialExecutor
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT_PATH = (
    _ROOT / "scripts/benchmark/run_phase5_compact_held_out_sentinel.py"
)
_PARENT_SHA256 = (
    "a29823c1341bd44ab2fcaaa6990dc19e25b47f669c6dddecf78d9e1af956d3b2"
)
_PARENT_IDENTITY = (
    _ROOT
    / "config/contracts/phase-5-compact-held-out-sentinel-identity-review.json"
)
_PARENT_IDENTITY_SHA256 = (
    "d879c65e70dd0d280d237f4d28212ceccee45069aed967ad5c038fc7155f4cb2"
)
_FAILED_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-execution-decision.json"
)
_FAILED_DECISION_SHA256 = (
    "8a3c4270b1d7eff39870dc5d86aa87465303cb5ec7769f935d10e9b3d2d73291"
)
_FAILED_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/compact-held-out-sentinel.json"
)
_FAILED_OUTPUT_SHA256 = (
    "965454ea9db83d6cc95e4b50553c4bafc2d10d816fa873a64f47759af20acb4d"
)
_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-compact-held-out-sentinel-identity-repair-review.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-compact-held-out-sentinel-identity-repair"
)
_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/"
    "compact-held-out-sentinel-identity-repair.json"
)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_parent: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_sentinel"
)
_repair: Any = importlib.import_module(
    "scripts.validation.repair_phase5_compact_sentinel_identity"
)


def _require_failed_lineage() -> None:
    """Bind the unchanged parent and its preserved fail-closed result."""
    expected = (
        (_PARENT_PATH, _PARENT_SHA256, "parent runner"),
        (_PARENT_IDENTITY, _PARENT_IDENTITY_SHA256, "parent identity"),
        (_FAILED_DECISION, _FAILED_DECISION_SHA256, "failed decision"),
        (_FAILED_OUTPUT, _FAILED_OUTPUT_SHA256, "failed terminal output"),
    )
    for path, digest, name in expected:
        if not path.is_file() or file_sha256(path) != digest:
            raise ValueError(f"compact sentinel {name} changed")


def _run_hebog_repaired(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    input_path: Path,
    output: Path,
    executor: Executor,
    review: Any,
) -> dict[str, object]:
    """Compile public components through their stable ownership records."""
    started = monotonic()
    run_id = f"sentinel-{dataset.identifier}-{recipe.seed}"
    with _parent._captured_science() as captured:
        result = _parent.hebog.find_sources(
            SourceFinderRequest(input_path, output, run_id),
            _parent._CONFIG,
            executor,
        )
    if len(captured) != 1 or captured[0].terminal is None:
        raise ValueError("public Hebog terminal products are unavailable")
    terminal = captured[0].terminal
    catalogue = tuple(terminal.component_catalogue)
    if result.gaussian_component_count != len(catalogue):
        raise ValueError("public Hebog Gaussian population changed")
    linked = _repair.link_stable_component_ownership(
        catalogue,
        terminal.source_association.components,
        terminal.measurement_component_labels,
    )
    return _parent.compile_finder_summary(
        dataset=dataset,
        recipe=recipe,
        finder_id="current-hebog",
        catalogue=linked,
        label_plane=terminal.measurement_component_labels,
        header=cast(fits.Header, fits.getheader(input_path)),
        review=review,
        elapsed_seconds=monotonic() - started,
        candidate_revision=_parent._CANDIDATE_REVISION,
        runtime_identity={
            "configuration_sha256": (_parent._CANDIDATE_CONFIGURATION_SHA256),
            "source_tree_sha256": _parent._CANDIDATE_SOURCE_TREE_SHA256,
        },
    )


def _pair_worker_repaired(  # noqa: PLR0913, PLR0917
    dataset_document: dict[str, object],
    recipe_document: dict[str, object],
    repository_root: str,
    scratch: str,
    execution_decision: str,
    identity_review: str,
    podman_executable: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one unchanged pair with repaired Hebog identity compilation."""
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
        hebog_summary = _run_hebog_repaired(
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
    """Install only the two stable-identity execution seams temporarily."""
    original_hebog = _parent._run_hebog
    original_pair = _parent._pair_worker
    _parent._run_hebog = _run_hebog_repaired
    _parent._pair_worker = _pair_worker_repaired
    try:
        yield
    finally:
        _parent._run_hebog = original_hebog
        _parent._pair_worker = original_pair


def verify_no_write(arguments: argparse.Namespace) -> dict[str, object]:
    """Run the complete parent preflight plus failed-lineage validation."""
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
        "parent_identity_sha256": _PARENT_IDENTITY_SHA256,
        "parent_runner_sha256": _PARENT_SHA256,
        "repair_helper_sha256": file_sha256(Path(_repair.__file__ or "")),
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
    """Preflight or execute the single approved unchanged sentinel retry."""
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
