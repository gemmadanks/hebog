#!/usr/bin/env python3
"""Retry the source-union sentinel with native counts reconstructed."""

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
_prior: Any = importlib.import_module(
    "scripts.benchmark."
    "run_phase5_compact_held_out_source_union_sentinel_column_case_repair"
)
_parent: Any = _prior._parent
_PRIOR_RUNNER = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_sentinel_"
    "column_case_repair.py"
)
_PRIOR_RUNNER_SHA256 = (
    "f8d44124a886e8935bf8626f5ce499f72d648f36c018de39002574b3b3d0833d"
)
_PRIOR_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-column-case-repair-"
    "identity-review.json"
)
_PRIOR_IDENTITY_SHA256 = (
    "524f6fd49ce26806ea86b94365ea3e362a85fc01fdcdbcba655806dc53f57381"
)
_FAILED_DECISION = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-column-case-repair-"
    "execution-decision.json"
)
_FAILED_DECISION_SHA256 = (
    "8f97ac646990652434c0d673cfe7f02f6b6ce2dc687367ff363e6a4add76d722"
)
_FAILED_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-column-case-repair.json"
)
_FAILED_OUTPUT_SHA256 = (
    "9d96a9ed36f580fe307e9992ca6f093f5fc0fe88bfbdc4361cf282bbe23e3bb5"
)
_REPAIRED_CHILD = _ROOT / (
    "scripts/benchmark/"
    "run_phase5_compact_held_out_source_union_pybdsf_"
    "gaussian_count_repair.py"
)
_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-gaussian-count-repair-"
    "identity-review.json"
)
_SCRATCH = Path(
    "/private/tmp/"
    "hebog-phase5-compact-held-out-source-union-sentinel-"
    "gaussian-count-repair"
)
_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-source-union-sentinel-gaussian-count-repair.json"
)


def _require_failed_lineage() -> None:
    """Bind both consumed attempts and every unchanged predecessor."""
    _prior._require_failed_lineage()
    expected = (
        (_PRIOR_RUNNER, _PRIOR_RUNNER_SHA256, "prior repair runner"),
        (_PRIOR_IDENTITY, _PRIOR_IDENTITY_SHA256, "prior repair identity"),
        (_FAILED_DECISION, _FAILED_DECISION_SHA256, "failed decision"),
        (_FAILED_OUTPUT, _FAILED_OUTPUT_SHA256, "failed terminal"),
    )
    for path, digest, name in expected:
        if not path.is_file() or file_sha256(path) != digest:
            raise ValueError(f"source-union Gaussian-count {name} changed")


def _pybdsf_command_gaussian_count_safe(
    **arguments: object,
) -> tuple[str, ...]:
    """Select only the isolated grouped-Gaussian count child."""
    parent_child = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf.py"
    )
    repaired_child = (
        "/repository/scripts/benchmark/"
        "run_phase5_compact_held_out_source_union_pybdsf_"
        "gaussian_count_repair.py"
    )
    return tuple(
        repaired_child if item == parent_child else item
        for item in _parent._pybdsf_command(**arguments)
    )


@contextmanager
def _configured_prior() -> Generator[None]:
    """Replace only the prior repair's comparator-child selector."""
    original = _prior._pybdsf_command_column_case_safe
    _prior._pybdsf_command_column_case_safe = (
        _pybdsf_command_gaussian_count_safe
    )
    try:
        yield
    finally:
        _prior._pybdsf_command_column_case_safe = original


def verify_no_write(arguments: argparse.Namespace) -> dict[str, object]:
    """Validate the unchanged parent contract and both failed attempts."""
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
    """Parse the second replacement preflight or execution inputs."""
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
    """Preflight or consume the exact grouped-Gaussian count repair."""
    arguments = _parse_args()
    verified = verify_no_write(arguments)
    if arguments.preflight_only:
        print(json.dumps(verified, sort_keys=True))
        return
    identity = _parent.verify_execution_authority(arguments)
    with _configured_prior(), _prior._configured_parent():
        _parent.execute(arguments, identity)


if __name__ == "__main__":
    main()
