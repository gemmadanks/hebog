#!/usr/bin/env python3
"""Evaluate the prospective mask-origin and sibling-pair smoke."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

_BASE_EVALUATOR = (
    "scripts/validation/evaluate_phase5_prospective_publication_snr_smoke.py"
)
_MATERIALIZER = (
    "scripts/validation/"
    "materialize_phase5_prospective_mask_origin_sibling_pair_products.py"
)


def _base(root: Path) -> dict[str, Any]:
    """Load the exact smoke evaluator with the new producer identity."""
    evaluator = runpy.run_path(str(root / _BASE_EVALUATOR))
    base = cast(Callable[[Path], dict[str, Any]], evaluator["_base"])(root)
    entrypoint = cast(Callable[[], None], base["main"])
    entrypoint.__globals__["_MATERIALIZER"] = _MATERIALIZER
    base["_MATERIALIZER"] = _MATERIALIZER
    return base


def main() -> None:
    """Run the frozen evaluator with the composed producer identity."""
    root = Path(__file__).resolve().parents[2]
    evaluator = _base(root)
    entrypoint = cast(Callable[[], None], evaluator["main"])
    entrypoint.__globals__["__file__"] = str(Path(__file__).resolve())
    entrypoint()


if __name__ == "__main__":
    main()
