#!/usr/bin/env python3
"""Run one PyBDSF leg through the frozen post-correction boundary."""

from __future__ import annotations

import runpy
from pathlib import Path

from hebog.validation import external_runners


def main() -> None:
    """Install post-correction loaders and invoke the unchanged runner."""
    root = Path(__file__).parents[2]
    helpers = runpy.run_path(
        str(
            root / "scripts/validation/"
            "phase5_external_post_correction_protocol.py"
        )
    )
    external_runners.load_phase_five_external_comparison_protocol = helpers[
        "load_post_correction_protocol"
    ]
    external_runners.load_phase_five_external_execution_decision = helpers[
        "load_post_correction_execution_decision"
    ]
    for finder_id in ("released-pybdsf", "pinned-pybdsf-master"):
        external_runners._RUNNER_PATHS[  # pyright: ignore[reportPrivateUsage]
            finder_id
        ] = "scripts/benchmark/run_phase5_external_post_correction_pybdsf.py"
    terminal = runpy.run_path(
        str(root / "scripts/benchmark/run_phase5_external_pybdsf.py")
    )
    terminal["main"].__globals__["__file__"] = str(Path(__file__))
    terminal["main"]()


if __name__ == "__main__":
    main()
