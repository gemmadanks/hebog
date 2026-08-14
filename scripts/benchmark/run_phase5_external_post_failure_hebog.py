#!/usr/bin/env python3
"""Run one Hebog leg through the approved post-failure boundary."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from hebog.validation import external_runners


def main() -> None:
    """Install prospective loaders and science around the terminal runner."""
    root = Path(__file__).parents[2]
    helpers = runpy.run_path(
        str(
            root / "scripts/validation/"
            "phase5_external_post_failure_protocol.py"
        )
    )
    external_runners.load_phase_five_external_comparison_protocol = helpers[
        "load_post_failure_protocol"
    ]
    external_runners.load_phase_five_external_execution_decision = helpers[
        "load_post_failure_execution_decision"
    ]
    candidate = runpy.run_path(
        str(root / "scripts/benchmark/run_phase5_post_failure_hebog.py")
    )
    terminal = runpy.run_path(
        str(root / "scripts/benchmark/run_phase5_external_hebog.py")
    )
    run_continuum = terminal["_run_continuum_products"]
    evaluate = run_continuum.__globals__[
        "evaluate_external_candidate_detection"
    ]

    def corrected_detection(
        *args: object,
        **kwargs: object,
    ) -> Any:
        return candidate["_cleaned_detection"](
            evaluate,
            *args,
            **kwargs,
        )

    run_continuum.__globals__["evaluate_external_candidate_detection"] = (
        corrected_detection
    )
    external_runners._RUNNER_PATHS[  # pyright: ignore[reportPrivateUsage]
        "hebog"
    ] = "scripts/benchmark/run_phase5_external_post_failure_hebog.py"
    terminal["main"].__globals__["__file__"] = str(Path(__file__))
    terminal["main"]()


if __name__ == "__main__":
    main()
