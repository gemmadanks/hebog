#!/usr/bin/env python3
"""Apply frozen sentinel gates only after source-level semantic validation."""

from __future__ import annotations

import runpy
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT = (
    _ROOT / "scripts/validation/evaluate_phase5_compact_held_out_sentinel.py"
)
_PARENT_SHA256 = (
    "6f2a05fbc1fbe66781f72554b53b94e83d6754b0809043c214d36493f8e83bfd"
)
_ALIGNMENT = _ROOT / "scripts/validation/compact_sentinel_alignment.py"


@lru_cache(maxsize=1)
def _parent_evaluator() -> Any:
    """Load the exact frozen gate evaluator without invoking its CLI."""
    if file_sha256(_PARENT) != _PARENT_SHA256:
        raise ValueError("compact sentinel parent evaluator changed")
    program = runpy.run_path(str(_PARENT))
    evaluate = program.get("evaluate_summaries")
    if not callable(evaluate):
        raise ValueError("compact sentinel parent evaluator seam changed")
    return evaluate


@lru_cache(maxsize=1)
def _summary_validator() -> Any:
    """Load the sibling semantic validator without importing scripts."""
    program = runpy.run_path(str(_ALIGNMENT))
    validate = program.get("validate_aligned_summary")
    if not callable(validate):
        raise ValueError("compact sentinel alignment seam changed")
    return validate


def evaluate_summaries(
    summaries: list[dict[str, object]],
    *,
    expected_cell_ids: tuple[str, ...],
    realizations_per_cell: int,
    dask_comparisons: Sequence[object],
) -> dict[str, object]:
    """Validate like semantics, then apply the unchanged frozen gates."""
    validate = _summary_validator()
    for summary in summaries:
        validate(cast(dict[str, Any], summary))
    evaluate = _parent_evaluator()
    return cast(
        dict[str, object],
        evaluate(
            summaries,
            expected_cell_ids=expected_cell_ids,
            realizations_per_cell=realizations_per_cell,
            dask_comparisons=dask_comparisons,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(
        "The aligned evaluator is invoked only by a separately "
        "authorized runner."
    )
