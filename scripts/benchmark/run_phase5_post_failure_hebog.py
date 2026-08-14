#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Run the prospective post-confirmation Hebog science boundary."""

from __future__ import annotations

import runpy
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from hebog.algorithms.extended_measurement import (
    clean_detected_segment_labels,
)
from hebog.validation import external_runners


def _cleaned_detection(
    evaluate: Any,
    *args: object,
    **kwargs: object,
) -> Any:
    """Apply the reviewed sub-beam cleanup to one frozen detection result."""
    detection = evaluate(*args, **kwargs)
    component_labels = clean_detected_segment_labels(
        detection.component_labels
    )
    return replace(
        detection,
        retained_mask=component_labels > 0,
        component_labels=component_labels,
        component_count=int(np.count_nonzero(np.unique(component_labels) > 0)),
    )


def main() -> None:
    """Install only prospective science seams around the historical runner."""
    root = Path(__file__).parents[2]
    runner_path = root / "scripts/benchmark/run_phase5_external_hebog.py"
    terminal = runpy.run_path(str(runner_path))
    run_continuum = terminal["_run_continuum_products"]
    evaluate = run_continuum.__globals__[
        "evaluate_external_candidate_detection"
    ]

    def corrected_detection(
        *args: object,
        **kwargs: object,
    ) -> Any:
        return _cleaned_detection(
            evaluate,
            *args,
            **kwargs,
        )

    run_continuum.__globals__["evaluate_external_candidate_detection"] = (
        corrected_detection
    )
    external_runners._RUNNER_PATHS["hebog"] = (
        "scripts/benchmark/run_phase5_post_failure_hebog.py"
    )
    terminal["main"].__globals__["__file__"] = str(Path(__file__))
    terminal["main"]()


if __name__ == "__main__":
    main()
