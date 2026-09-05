#!/usr/bin/env python3
"""Evaluate the version-8 public candidate with the reviewed compiler."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_final_cumulative_current.py"
)
_PARENT_EVALUATOR_SHA256 = (
    "399171f1397b2c7dc84b20042d24018a01131106be65822a04aed067aa2b77f4"
)
_CURRENT_REVISION = "95cfc76ded56556dc3ad6894410962d34f0d5604"
_CURRENT_SOURCE_TREE_SHA256 = (
    "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)


def load_public_owner_domain_evaluator() -> dict[str, Any]:
    """Retarget only the current identity in the reviewed evaluator stack."""
    if file_sha256(_PARENT_EVALUATOR) != _PARENT_EVALUATOR_SHA256:
        raise ValueError("public owner-domain parent evaluator changed")
    overlay = runpy.run_path(str(_PARENT_EVALUATOR))
    load = overlay.get("load_final_evaluator")
    if not callable(load):
        raise ValueError("public owner-domain evaluator seam changed")
    evaluator = cast(dict[str, Any], load())
    if (
        not callable(evaluator.get("main"))
        or not callable(evaluator.get("_truth_linked_tail_record"))
        or not callable(evaluator.get("compile_prospective_decision"))
    ):
        raise ValueError("public owner-domain evaluator contract changed")
    evaluator["_CURRENT_REVISION"] = _CURRENT_REVISION
    evaluator["_CURRENT_SOURCE_TREE_SHA256"] = _CURRENT_SOURCE_TREE_SHA256
    evaluator["_CURRENT_CONFIGURATION_SHA256"] = _CURRENT_CONFIGURATION_SHA256
    evaluator["__file__"] = str(Path(__file__).resolve())
    return evaluator


def load_final_evaluator() -> dict[str, Any]:
    """Expose the stable completion seam used by the parent wrapper."""
    return load_public_owner_domain_evaluator()


_PRODUCT_VERIFIER_EVALUATOR = load_public_owner_domain_evaluator()
_SMOKE_EVALUATOR = cast(Path, _PRODUCT_VERIFIER_EVALUATOR["_SMOKE_EVALUATOR"])
_load_materializer = _PRODUCT_VERIFIER_EVALUATOR["_load_materializer"]
_compile_incumbent_pair = _PRODUCT_VERIFIER_EVALUATOR[
    "_compile_incumbent_pair"
]
compile_prospective_decision = _PRODUCT_VERIFIER_EVALUATOR[
    "compile_prospective_decision"
]


def main() -> None:
    """Run the exact evaluation with the unchanged inherited CLI."""
    load_public_owner_domain_evaluator()["main"]()


if __name__ == "__main__":
    main()
