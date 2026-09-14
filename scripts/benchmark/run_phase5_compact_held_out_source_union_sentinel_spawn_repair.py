#!/usr/bin/env python3
"""Retry the source-union sentinel with spawn-safe worker dispatch."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
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
from typing import Any

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_failed: Any = importlib.import_module(
    "scripts.benchmark."
    "run_phase5_compact_held_out_source_union_sentinel_"
    "gaussian_count_repair"
)
_worker: Any = importlib.import_module(
    "scripts.benchmark.phase5_compact_held_out_source_union_spawn_repair"
)
_parent: Any = _failed._parent
_FAILED_RUNNER = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_sentinel_"
    "gaussian_count_repair.py"
)
_FAILED_RUNNER_SHA256 = (
    "e96bdef1c0adfbc214180f759b4418e4fc9cb4e6c22651ce93f45f01612fddb4"
)
_FAILED_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-gaussian-count-repair-"
    "identity-review.json"
)
_FAILED_IDENTITY_SHA256 = (
    "07e0e8ecb0e34d9fdb38dde6be942c579f6dca2e21c18e308ecc6035ae0083d3"
)
_FAILED_DECISION = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-gaussian-count-repair-"
    "execution-decision.json"
)
_FAILED_DECISION_SHA256 = (
    "242e1d3dbfb160e89df9f70587b437c91c5626eae8bbe76331e4b84e6b4d0577"
)
_FAILED_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-gaussian-count-repair.json"
)
_FAILED_OUTPUT_SHA256 = (
    "a6a119feba1047cf197286c51daaf731b4b88520f58402cb383c9b8a5ad8c0ea"
)
_HELPER = _ROOT / (
    "scripts/benchmark/phase5_compact_held_out_source_union_spawn_repair.py"
)
_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-spawn-repair-"
    "identity-review.json"
)
_SCRATCH = Path(
    "/private/tmp/"
    "hebog-phase5-compact-held-out-source-union-sentinel-spawn-repair"
)
_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-spawn-repair.json"
)


def _require_failed_lineage() -> None:
    """Bind the consumed spawn-unsafe attempt and all predecessors."""
    _failed._require_failed_lineage()
    expected = (
        (_FAILED_RUNNER, _FAILED_RUNNER_SHA256, "failed runner"),
        (_FAILED_IDENTITY, _FAILED_IDENTITY_SHA256, "failed identity"),
        (_FAILED_DECISION, _FAILED_DECISION_SHA256, "failed decision"),
        (_FAILED_OUTPUT, _FAILED_OUTPUT_SHA256, "failed terminal"),
    )
    for path, digest, name in expected:
        if not path.is_file() or file_sha256(path) != digest:
            raise ValueError(f"source-union spawn-repair {name} changed")


@contextmanager
def _configured_parent() -> Generator[None]:
    """Submit only the explicitly importable repaired pair worker."""
    original_pair = _parent._pair_worker
    _parent._pair_worker = _worker.pair_worker
    try:
        yield
    finally:
        _parent._pair_worker = original_pair


def verify_no_write(arguments: argparse.Namespace) -> dict[str, object]:
    """Validate the unchanged contract and exact failed lineage."""
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
        "spawn_worker_sha256": file_sha256(_HELPER),
    }


def _parse_args() -> argparse.Namespace:
    """Parse the spawn-safe replacement preflight or execution inputs."""
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
    """Preflight or consume the exact spawn-process repair."""
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
