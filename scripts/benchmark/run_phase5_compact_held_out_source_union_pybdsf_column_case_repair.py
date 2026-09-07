#!/usr/bin/env python3
"""Run the source-union PyBDSF child with its exact ``N_gaus`` schema."""

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
from astropy.wcs import WCS

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_parent: Any = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_source_union_pybdsf"
)


def projection_from_catalogue_tables(
    *,
    source_table: np.ndarray,
    gaussian_table: np.ndarray,
    native_island_labels: object,
    header: fits.Header,
) -> object:
    """Project native tables using PyBDSF's exact ``N_gaus`` spelling."""
    if source_table.size == 0 and gaussian_table.size == 0:
        return _parent.projection_from_catalogue_tables(
            source_table=source_table,
            gaussian_table=gaussian_table,
            native_island_labels=native_island_labels,
            header=header,
        )
    _parent._required_columns(
        source_table,
        {"Isl_id", "Source_id", "N_gaus", "RA", "DEC", "Total_flux"},
    )
    _parent._required_columns(
        gaussian_table,
        {
            "Gaus_id",
            "Isl_id",
            "Source_id",
            "RA",
            "DEC",
            "Total_flux",
            "Peak_flux",
            "Maj",
            "Min",
            "PA",
        },
    )
    celestial = WCS(header, relax=True).celestial
    sources = tuple(
        _parent.PyBdsfSourceRow(
            island_id=int(row["Isl_id"]),
            source_id=int(row["Source_id"]),
            centre_xy=_parent._pixel_centre(row, celestial),
            integrated_flux_jy=float(row["Total_flux"]),
            gaussian_count=int(row["N_gaus"]),
        )
        for row in source_table
    )
    gaussians: list[object] = []
    for row in gaussian_table:
        centre = _parent._pixel_centre(row, celestial)
        gaussians.append(
            _parent.PyBdsfGaussianRow(
                identifier=(
                    f"pybdsf-island-{int(row['Isl_id'])}-source-"
                    f"{int(row['Source_id'])}-gaussian-"
                    f"{int(row['Gaus_id'])}"
                ),
                island_id=int(row["Isl_id"]),
                source_id=int(row["Source_id"]),
                centre_xy=centre,
                integrated_flux_jy=float(row["Total_flux"]),
                peak_flux_jy_per_beam=float(row["Peak_flux"]),
                covariance_pixels_squared=_parent._pixel_covariance(
                    row, celestial, centre
                ),
            )
        )
    return _parent.derive_pybdsf_source_model_dominance(
        source_rows=sources,
        gaussian_rows=tuple(gaussians),
        native_island_labels=native_island_labels,
    )


@contextmanager
def _configured_parent() -> Generator[None]:
    """Install only the exact source-count column correction."""
    original = _parent.projection_from_catalogue_tables
    _parent.projection_from_catalogue_tables = projection_from_catalogue_tables
    try:
        yield
    finally:
        _parent.projection_from_catalogue_tables = original


def main() -> None:
    """Run the unchanged child with the column-case repair installed."""
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
