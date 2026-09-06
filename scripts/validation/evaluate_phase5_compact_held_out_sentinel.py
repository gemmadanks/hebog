#!/usr/bin/env python3
"""Evaluate the compact sentinel without pooling across risk cells."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from math import isfinite
from typing import Literal, cast

import numpy as np

Direction = Literal["higher", "lower"]
_DASK_COMPARISON_COUNT = 12
_METRICS: dict[str, tuple[Direction, float, str]] = {
    "completeness": ("higher", 0.02, "scalar"),
    "reliability": ("higher", 0.02, "scalar"),
    "integrated-flux-median": ("lower", 0.05, "median"),
    "integrated-flux-p95": ("lower", 0.05, "p95"),
    "absolute-mean-offset-x": ("lower", 0.05, "absolute-mean"),
    "absolute-mean-offset-y": ("lower", 0.05, "absolute-mean"),
    "position-median": ("lower", 0.05, "median"),
    "position-p95": ("lower", 0.05, "p95"),
    "duplicate-fraction": ("lower", 0.01, "scalar"),
    "mask-precision": ("higher", 0.05, "scalar"),
    "mask-recall": ("higher", 0.05, "scalar"),
    "mask-iou": ("higher", 0.05, "scalar"),
    "split-fraction": ("lower", 0.02, "scalar"),
    "merge-fraction": ("lower", 0.02, "scalar"),
}


def _image_value(value: object, statistic: str) -> float | None:
    """Reduce one image's sufficient statistic without hiding absence."""
    if statistic == "scalar":
        if not isinstance(value, (float, int)):
            raise ValueError("scalar sentinel metric is malformed")
        result = float(value)
    else:
        if not isinstance(value, list):
            raise ValueError("conditional sentinel metric is malformed")
        if not value:
            return None
        values = np.asarray(value, dtype=np.float64)
        if statistic == "median":
            result = float(np.median(values))
        elif statistic == "p95":
            result = float(np.percentile(values, 95.0))
        else:
            result = abs(float(np.mean(values)))
    if not isfinite(result):
        raise ValueError("sentinel metric is not finite")
    return result


def _cell_metric(
    summaries: Sequence[dict[str, object]], metric: str
) -> float | None:
    """Return the median of four independent image-level values."""
    statistic = _METRICS[metric][2]
    values = []
    for summary in summaries:
        metrics = summary.get("metrics")
        if not isinstance(metrics, dict) or metric not in metrics:
            raise ValueError(f"sentinel metric is absent: {metric}")
        value = _image_value(metrics[metric], statistic)
        if value is not None:
            values.append(value)
    if not values:
        return None
    return float(np.median(np.asarray(values, dtype=np.float64)))


def _dask_equal(item: object) -> bool:
    """Accept only explicit structured Serial/Dask equality evidence."""
    return isinstance(item, dict) and item.get("equal") is True


def evaluate_summaries(  # noqa: C901, PLR0912
    summaries: list[dict[str, object]],
    *,
    expected_cell_ids: tuple[str, ...],
    realizations_per_cell: int,
    dask_comparisons: Sequence[object],
) -> dict[str, object]:
    """Apply every cell-level parity gate with no cross-cell compensation."""
    if realizations_per_cell < 1:
        raise ValueError("sentinel realization count must be positive")
    if len(set(expected_cell_ids)) != len(expected_cell_ids):
        raise ValueError("sentinel cell identities must be unique")
    if len(dask_comparisons) != _DASK_COMPARISON_COUNT or not all(
        _dask_equal(item) for item in dask_comparisons
    ):
        raise ValueError("all 12 existing-Dask comparisons must equal Serial")
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for summary in summaries:
        cell = summary.get("cell_id")
        finder = summary.get("finder_id")
        if not isinstance(cell, str) or finder not in {
            "current-hebog",
            "released-pybdsf",
        }:
            raise ValueError("sentinel summary cell or finder is invalid")
        if summary.get("product_valid") is not True:
            raise ValueError("sentinel finder product is invalid")
        if summary.get("ownership_valid", True) is not True:
            raise ValueError("sentinel finder ownership is invalid")
        grouped[(cell, cast(str, finder))].append(summary)
    expected_keys = {
        (cell, finder)
        for cell in expected_cell_ids
        for finder in ("current-hebog", "released-pybdsf")
    }
    if set(grouped) != expected_keys:
        raise ValueError("sentinel cell/finder population is incomplete")
    decisions: list[dict[str, object]] = []
    for cell in sorted(expected_cell_ids):
        left = grouped[(cell, "current-hebog")]
        right = grouped[(cell, "released-pybdsf")]
        left_seeds = {item.get("seed") for item in left}
        right_seeds = {item.get("seed") for item in right}
        if (
            len(left) != realizations_per_cell
            or len(right) != realizations_per_cell
            or left_seeds != right_seeds
            or len(left_seeds) != realizations_per_cell
        ):
            raise ValueError("sentinel paired realization population changed")
        failures: list[str] = []
        metric_rows: dict[str, object] = {}
        for metric, (direction, margin, _statistic) in _METRICS.items():
            candidate = _cell_metric(left, metric)
            reference = _cell_metric(right, metric)
            if candidate is None or reference is None:
                failures.append(f"{metric}-unavailable")
                metric_rows[metric] = {
                    "candidate_cell_median": candidate,
                    "released_pybdsf_cell_median": reference,
                    "positive_regression": None,
                    "practical_regression_margin": margin,
                    "passed": False,
                }
                continue
            regression = (
                reference - candidate
                if direction == "higher"
                else candidate - reference
            )
            passed = regression <= margin
            if not passed:
                failures.append(f"{metric}-pybdsf-parity")
            metric_rows[metric] = {
                "candidate_cell_median": candidate,
                "released_pybdsf_cell_median": reference,
                "positive_regression": regression,
                "practical_regression_margin": margin,
                "passed": passed,
            }
        decisions.append(
            {
                "cell_id": cell,
                "failure_reasons": failures,
                "metrics": metric_rows,
                "passed": not failures,
            }
        )
    passed = all(item["passed"] for item in decisions)
    return {
        "absolute_objectives": "report-only",
        "cell_decisions": decisions,
        "dask_comparison_count": len(dask_comparisons),
        "failure_reasons": [
            f"{item['cell_id']}:{reason}"
            for item in decisions
            for reason in cast(list[str], item["failure_reasons"])
        ],
        "passed": passed,
        "pooling_used": False,
        "schema_version": 1,
        "status": "pass" if passed else "fail",
    }


if __name__ == "__main__":
    raise SystemExit(
        "The compact evaluator is invoked by the checksum-bound runner."
    )
