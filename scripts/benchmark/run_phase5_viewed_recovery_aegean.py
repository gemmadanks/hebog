#!/usr/bin/env python3
"""Run an Aegean leg for the approved viewed-development recovery."""

from __future__ import annotations

import runpy
from pathlib import Path

from hebog.validation import external_runners


def main() -> None:
    """Install recovery identities and invoke the unchanged runner."""
    root = Path(__file__).parents[2]
    helpers = runpy.run_path(
        str(root / "scripts/validation/phase5_viewed_recovery_protocol.py")
    )
    external_runners.load_phase_five_external_comparison_protocol = helpers[
        "load_viewed_recovery_protocol"
    ]
    external_runners.load_phase_five_external_execution_decision = helpers[
        "load_viewed_recovery_execution_decision"
    ]
    external_runners._RUNNER_PATHS[  # pyright: ignore[reportPrivateUsage]
        "aegean"
    ] = "scripts/benchmark/run_phase5_viewed_recovery_aegean.py"
    terminal = runpy.run_path(
        str(root / "scripts/benchmark/run_phase5_external_aegean.py")
    )
    terminal["main"].__globals__["__file__"] = str(Path(__file__))
    terminal["main"]()


if __name__ == "__main__":
    main()
