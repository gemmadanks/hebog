#!/usr/bin/env python3
"""Evaluate the final candidate through the reviewed topology evaluator."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
)
_PARENT_EVALUATOR_SHA256 = (
    "39a568bada625b751931aff649e4e815c5ed70f68809d902a52ce93cfeaec62a"
)
_CURRENT_REVISION = "0b9e13299f3fbbd42af0dea4f70155a802a8441d"
_CURRENT_SOURCE_TREE_SHA256 = (
    "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)


def load_final_evaluator() -> dict[str, Any]:
    """Retarget only the current identity in the reviewed evaluator stack."""
    if file_sha256(_PARENT_EVALUATOR) != _PARENT_EVALUATOR_SHA256:
        raise ValueError("final cumulative parent evaluator changed")
    overlay = runpy.run_path(str(_PARENT_EVALUATOR))
    load = overlay.get("load_topology_repaired_evaluator")
    if not callable(load):
        raise ValueError("final cumulative topology evaluator seam changed")
    evaluator = cast(dict[str, Any], load())
    if (
        not callable(evaluator.get("main"))
        or not callable(evaluator.get("_truth_linked_tail_record"))
        or not callable(evaluator.get("compile_prospective_decision"))
    ):
        raise ValueError("final cumulative evaluator contract changed")
    evaluator["_CURRENT_REVISION"] = _CURRENT_REVISION
    evaluator["_CURRENT_SOURCE_TREE_SHA256"] = _CURRENT_SOURCE_TREE_SHA256
    evaluator["_CURRENT_CONFIGURATION_SHA256"] = _CURRENT_CONFIGURATION_SHA256
    evaluator["__file__"] = str(Path(__file__).resolve())
    return evaluator


# The inherited product verifier intentionally loads evaluator scripts with
# ``runpy`` and dispatches these two raw module seams before scientific
# compilation.  Keep the thin identity overlay usable through that exact
# boundary as well as through ``load_final_evaluator``.
_PRODUCT_VERIFIER_EVALUATOR = load_final_evaluator()
_SMOKE_EVALUATOR = cast(Path, _PRODUCT_VERIFIER_EVALUATOR["_SMOKE_EVALUATOR"])
_load_materializer = _PRODUCT_VERIFIER_EVALUATOR["_load_materializer"]


def main() -> None:
    """Run the exact evaluation with the unchanged parent CLI."""
    load_final_evaluator()["main"]()


if __name__ == "__main__":
    main()
