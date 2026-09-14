#!/usr/bin/env python3
"""Run the source-union child with counts derived from native ``gaul``."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_prior: Any = importlib.import_module(
    "scripts.benchmark."
    "run_phase5_compact_held_out_source_union_pybdsf_column_case_repair"
)
_parent: Any = _prior._parent


def _with_derived_gaussian_counts(
    source_table: np.ndarray, gaussian_table: np.ndarray
) -> np.ndarray:
    """Add the non-exported source count from exact Gaussian membership."""
    _parent._required_columns(
        source_table,
        {"Isl_id", "Source_id", "RA", "DEC", "Total_flux"},
    )
    _parent._required_columns(
        gaussian_table,
        {"Isl_id", "Source_id"},
    )
    if "N_gaus" in (source_table.dtype.names or ()):
        return source_table
    augmented = np.empty(
        source_table.shape,
        dtype=[*source_table.dtype.descr, ("N_gaus", "<i8")],
    )
    for name in source_table.dtype.names or ():
        augmented[name] = source_table[name]
    for index, row in enumerate(source_table):
        matches = (gaussian_table["Isl_id"] == row["Isl_id"]) & (
            gaussian_table["Source_id"] == row["Source_id"]
        )
        augmented["N_gaus"][index] = int(np.count_nonzero(matches))
    return augmented


def projection_from_catalogue_tables(
    *,
    source_table: np.ndarray,
    gaussian_table: np.ndarray,
    native_island_labels: object,
    header: fits.Header,
) -> object:
    """Project native tables without assuming an exported count column."""
    if source_table.size == 0 and gaussian_table.size == 0:
        return _prior.projection_from_catalogue_tables(
            source_table=source_table,
            gaussian_table=gaussian_table,
            native_island_labels=native_island_labels,
            header=header,
        )
    return _prior.projection_from_catalogue_tables(
        source_table=_with_derived_gaussian_counts(
            source_table, gaussian_table
        ),
        gaussian_table=gaussian_table,
        native_island_labels=native_island_labels,
        header=header,
    )


@contextmanager
def _configured_parent() -> Generator[None]:
    """Install only the exact exported-schema correction."""
    original = _parent.projection_from_catalogue_tables
    _parent.projection_from_catalogue_tables = projection_from_catalogue_tables
    try:
        yield
    finally:
        _parent.projection_from_catalogue_tables = original


def main() -> None:
    """Run the unchanged child with exact grouped-Gaussian counts."""
    arguments = _parent._parse_args()
    with _configured_parent():
        _parent.run(
            input_path=Path(arguments.input),
            output=Path(arguments.output),
            execution_decision=Path(arguments.execution_decision),
            identity_review=Path(arguments.identity_review),
            container_digest=arguments.container_digest,
        )


if __name__ == "__main__":
    main()
