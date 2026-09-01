#!/usr/bin/env python3
"""Evaluate the publication-SNR repair on exact sealed smoke products."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

_BASE_EVALUATOR = (
    "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
)
_MATERIALIZER = (
    "scripts/validation/"
    "materialize_phase5_prospective_publication_snr_products.py"
)


def _base(root: Path) -> dict[str, Any]:
    """Load the exact mixed-schema evaluator with the repaired producer."""
    evaluator = runpy.run_path(str(root / _BASE_EVALUATOR))
    evaluator["_MATERIALIZER"] = _MATERIALIZER
    return evaluator


def main() -> None:
    """Run the frozen evaluator with repaired producer identity."""
    root = Path(__file__).resolve().parents[2]
    evaluator = _base(root)
    evaluator["__file__"] = str(Path(__file__).resolve())
    evaluator["main"]()


if __name__ == "__main__":
    main()
