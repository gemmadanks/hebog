"""Staged replacement orchestration; the CLI owner must admit an exact plan.

There is deliberately no launch entry point in this preparation module.
Resource admission and a new one-use execution decision remain separate.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.validation.run_source_catalogue_cumulative_replay import (
    _run_stage,
    aggregate_records,
    compare_existing_dask,
)
from scripts.validation.source_catalogue_replacement_execution import (
    capture_replacement,
    combine_records,
    evaluate_replacement,
)
from scripts.validation.source_catalogue_replay_plan import binding, read_bound

from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import canonical_sha256


def run_replacement(
    plan: dict[str, Any], launch: dict[str, Any]
) -> dict[str, Any]:
    """Retain each completed stage and reuse comparator records unchanged."""
    scratch = Path(plan["scratch"])
    scratch.mkdir(parents=True, exist_ok=False)
    _atomic_json(scratch / "launch.json", launch)
    started = datetime.now(UTC)
    stage = "capture"
    try:
        with (scratch / "progress.log").open(
            "x", encoding="utf-8"
        ) as progress:
            captures = _run_stage(
                stage, plan["tasks"], capture_replacement, progress
            )
            pairs = [read_bound(value) for value in captures]
            if sorted(row["input_id"] for row in pairs) != sorted(
                row["input_id"] for row in plan["tasks"]
            ):
                raise ValueError("replacement capture census changed")
            captures.sort(key=lambda row: row["path"])
            _atomic_json(
                scratch / "capture-seal.json",
                {
                    "launch": launch,
                    "pairs": captures,
                    "pair_set_sha256": canonical_sha256(captures),
                },
            )
            stage = "dask"
            comparisons = compare_existing_dask(plan, pairs, progress)
            stage = "evaluation"
            evaluated = _run_stage(
                stage, pairs, evaluate_replacement, progress
            )
            _atomic_json(
                scratch / "current-evaluation-seal.json",
                {
                    "images": sorted(
                        evaluated, key=lambda row: row["input_id"]
                    ),
                    "launch": launch,
                },
            )
            stage = "reuse"
            combined = combine_records(
                pairs, evaluated, plan["retained_records"]
            )
            _atomic_json(
                scratch / "evaluation-seal.json",
                {
                    "images": combined,
                    "launch": launch,
                    "retained_record_set_sha256": canonical_sha256(
                        plan["retained_records"]
                    ),
                },
            )
            stage = "aggregation"
            progress.write(
                f"{datetime.now(UTC).isoformat()} stage=aggregation started\n"
            )
            progress.flush()
            decision = aggregate_records(plan, pairs, combined, comparisons)
            terminal = {
                "schema_version": 1,
                "campaign": (
                    "phase-5-public-catalogue-v11-replacement-cumulative"
                ),
                "evidence_role": "regression",
                "fresh_qualification": False,
                "candidate": plan["candidate"],
                "incumbent": plan["incumbent"],
                "launch": launch,
                "capture_seal": binding(scratch / "capture-seal.json"),
                "current_evaluation_seal": binding(
                    scratch / "current-evaluation-seal.json"
                ),
                "evaluation_seal": binding(scratch / "evaluation-seal.json"),
                "dask_comparisons": binding(scratch / "dask-comparisons.json"),
                "candidate_serial_executions": len(pairs),
                "incumbent_executions": 0,
                "pybdsf_executions": 0,
                "aegean_executions": 0,
                "reused_comparator_records": len(plan["retained_records"]),
                "started_at": started.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "result": decision,
            }
            _atomic_json(Path(plan["output"]), terminal)
            return terminal
    except Exception as error:
        _atomic_json(
            scratch / "process-failure.json",
            {
                "stage": stage,
                "exception_type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "launch": launch,
                "recorded_at": datetime.now(UTC).isoformat(),
                "candidate_products_preserved": True,
            },
        )
        raise
