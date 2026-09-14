#!/usr/bin/env python3
"""Evaluate sealed paired products with repaired result-neutral diagnostics."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_prospective_paired_cumulative.py"
)
_TAIL_REPAIR = (
    _ROOT
    / "scripts/validation/repair_phase5_prospective_paired_tail_diagnostics.py"
)
_PARENT_EVALUATOR_SHA256 = (
    "44d7d6475832becfdf02d475a4654de05284fd2320080a8a28734e39d9aeee51"
)
_TAIL_REPAIR_SHA256 = (
    "54e592071cbab516ddccfa0edc28c4fe2b7e5cfcdfe9de997307e1231cc70703"
)


def _verify_programs() -> None:
    """Fail closed unless both reviewed program identities are exact."""
    evidence = (
        (
            _PARENT_EVALUATOR,
            _PARENT_EVALUATOR_SHA256,
            "parent evaluator",
        ),
        (_TAIL_REPAIR, _TAIL_REPAIR_SHA256, "tail repair"),
    )
    for path, expected, label in evidence:
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"prospective paired {label} changed")


def load_repaired_evaluator() -> dict[str, Any]:
    """Load the frozen evaluator and replace only its failed tail seam."""
    _verify_programs()
    loaded_parent = runpy.run_path(str(_PARENT_EVALUATOR))
    parent = loaded_parent["main"].__globals__
    repair = runpy.run_path(str(_TAIL_REPAIR))
    original = parent["_truth_linked_tail_record"]

    def repaired_truth_linked_tail_record(**arguments: Any) -> object:
        return repair["truth_linked_tail_record"](parent=parent, **arguments)

    parent["_ORIGINAL_TRUTH_LINKED_TAIL_RECORD"] = original
    parent["_truth_linked_tail_record"] = repaired_truth_linked_tail_record
    # The published record identifies this executable overlay, while the
    # completion contract separately binds the unchanged parent and repair.
    parent["__file__"] = str(Path(__file__).resolve())
    return parent


def main() -> None:
    """Run the repaired evaluator with its unchanged command contract."""
    load_repaired_evaluator()["main"]()


if __name__ == "__main__":
    main()
