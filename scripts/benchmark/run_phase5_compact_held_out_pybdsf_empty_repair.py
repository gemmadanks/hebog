#!/usr/bin/env python3
"""Run PyBDSF while retaining its valid no-island catalogue."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_parent: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_pybdsf"
)
_original_loader = _parent.load_pybdsf_gaussian_catalogue


def _load_zero_row_safe(path: Path) -> tuple[object, ...]:
    """Retain PyBDSF's schema-free table only when it has zero rows."""
    table = np.asarray(fits.getdata(path, ext=1))
    if len(table) == 0:
        return ()
    return cast(tuple[object, ...], _original_loader(path))


def _validate_empty_support(
    catalogue: tuple[object, ...], labels: np.ndarray[Any, Any]
) -> None:
    """Require a schema-free empty catalogue to have no native island."""
    if not catalogue and np.any(np.asarray(labels) > 0):
        raise ValueError("empty PyBDSF catalogue has positive native labels")


def run(**arguments: object) -> None:
    """Run the frozen child with its zero-row reader temporarily repaired."""
    original = _parent.load_pybdsf_gaussian_catalogue
    _parent.load_pybdsf_gaussian_catalogue = _load_zero_row_safe
    try:
        _parent.run(**arguments)
    finally:
        _parent.load_pybdsf_gaussian_catalogue = original
    output = cast(Path, arguments["output"])
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    if result["catalogue_count"] == 0:
        labels = np.asarray(
            fits.getdata(output / "island-labels.fits"), dtype=np.int32
        )
        _validate_empty_support((), labels)


if __name__ == "__main__":
    parsed = _parent._parse_args()
    run(
        input_path=parsed.input,
        output=parsed.output,
        execution_decision=parsed.execution_decision,
        identity_review=parsed.identity_review,
        container_digest=parsed.container_digest,
    )
