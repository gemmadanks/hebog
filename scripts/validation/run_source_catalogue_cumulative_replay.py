"""Execute one frozen R6 replay with durable capture and evaluation stages."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import traceback
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from scripts.validation import source_catalogue_campaign_evidence as evidence
from scripts.validation.source_catalogue_campaign_execution import (
    capture_pair,
    evaluate_pair,
)
from scripts.validation.source_catalogue_campaign_worker import (
    capture_current_image,
)
from scripts.validation.source_catalogue_input_evaluation import (
    native_artifacts,
)
from scripts.validation.source_catalogue_replay_plan import (
    REGISTRY,
    binding,
    read_bound,
    verify_replay_plan,
)
from scripts.validation.source_catalogue_retained_measurements import (
    capture_science_sha256,
)

from hebog.config import SourceFinderConfig
from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.evidence import CampaignImplementationIdentity
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpointRegistry,
)


def verify_authorization(
    plan_binding: dict[str, str],
    authority: dict[str, Any],
) -> None:
    """Require the exact one-use decision, not a reusable general flag."""
    if (
        authority.get("status")
        != "authorized-for-one-source-catalogue-cumulative-replay"
        or authority.get("plan_sha256") != plan_binding["sha256"]
        or type(authority.get("execution_count")) is not int
        or authority["execution_count"] != 1
    ):
        raise PermissionError("exact one-use R6 authority changed")


def _run_stage(
    stage: str,
    tasks: Sequence[dict[str, Any]],
    worker: Callable[[dict[str, Any]], dict[str, Any]],
    progress: TextIO,
) -> list[dict[str, Any]]:
    """Use exactly two importable spawned workers and report counts only."""
    completed = []
    pool = ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("spawn")
    )
    try:
        futures = [pool.submit(worker, task) for task in tasks]
        for future in as_completed(futures):
            completed.append(future.result())
            progress.write(
                f"{datetime.now(UTC).isoformat()} stage={stage} "
                f"completed={len(completed)}/{len(tasks)}\n"
            )
            progress.flush()
    finally:
        # Already-dispatched captures finish safely; cancel pending futures
        # after a worker error or interruption instead of draining the queue.
        pool.shutdown(wait=True, cancel_futures=True)
    return completed


def compare_existing_dask(
    plan: dict[str, Any],
    pairs: Sequence[dict[str, Any]],
    progress: TextIO,
) -> list[dict[str, Any]]:
    """The CLI owns the cluster; the library receives an existing client."""
    from distributed import Client, LocalCluster  # noqa: PLC0415

    from hebog.executors.dask import DaskExecutor  # noqa: PLC0415

    indexed = {row["input_id"]: row for row in pairs}
    comparisons = []
    with (
        LocalCluster(
            n_workers=2,
            threads_per_worker=1,
            processes=True,
            dashboard_address="127.0.0.1:0",
        ) as cluster,
        Client(cluster) as client,
    ):
        for identifier in plan["dask_input_ids"]:
            row = indexed[identifier]
            input_binding = row["input_manifest"]
            artifacts = native_artifacts(
                Path(input_binding["path"]), input_binding["sha256"]
            )
            output = Path(plan["scratch"]) / "dask" / identifier
            capture_current_image(
                artifacts["image"],
                output,
                input_id=identifier,
                config=SourceFinderConfig(**plan["configuration"]),
                executor=DaskExecutor(client),
            )
            serial_hash = capture_science_sha256(
                Path(row["captures"]["current-hebog"]["path"])
            )
            dask_hash = capture_science_sha256(output / "capture.json")
            comparisons.append(
                {
                    "input_id": identifier,
                    "serial_science_sha256": serial_hash,
                    "dask_science_sha256": dask_hash,
                    "pass": serial_hash == dask_hash,
                    "capture": binding(output / "capture.json"),
                }
            )
            progress.write(
                f"{datetime.now(UTC).isoformat()} stage=dask "
                f"completed={len(comparisons)}/{len(plan['dask_input_ids'])}\n"
            )
            progress.flush()
    _atomic_json(
        Path(plan["scratch"]) / "dask-comparisons.json",
        {"comparisons": comparisons},
    )
    return comparisons


def aggregate_records(
    plan: dict[str, Any],
    pairs: Sequence[dict[str, Any]],
    evaluated: Sequence[dict[str, Any]],
    dask: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Interpret independent truth metrics before any runtime reporting."""
    root = Path(plan["execution_root"])
    expected_keys = [
        (row["input_id"], finder)
        for row in pairs
        for finder in row["captures"]
    ]
    records = evidence.load_image_records(
        [entry for row in evaluated for entry in row["records"]], expected_keys
    )
    registry = ProspectiveEndpointRegistry.model_validate_json(
        (root / REGISTRY).read_bytes()
    )
    policy, protocol = evidence.load_cumulative_policy(root)
    compact = evidence.compile_compact_records(
        records,
        policy,
        repository_root=root,
        implementations=tuple(
            CampaignImplementationIdentity.model_validate_json(json.dumps(row))
            for row in plan["implementations"]
        ),
        captured_at=datetime.now(UTC),
        expected_image_count=800,
    )
    return evidence.compile_cumulative_decision(
        records=records,
        registry=registry,
        historical_registry=policy,
        compact_decisions=compact,
        safety_results={
            "finite-measurements": True,
            "product-validity": True,
            "schema-and-provenance-integrity": True,
            "serial-and-existing-dask-determinism": len(dask)
            == plan["existing_dask_comparisons"]
            and all(row["pass"] for row in dask),
            "write-once-publication": True,
        },
        expected_continuum_count=1600,
        resamples=protocol["bootstrap_resamples"],
        seed=protocol["bootstrap_seed"],
        planning_deviations=evidence.evaluate_phase5_prospective_paired_cumulative._planning_deviations(
            root
        ),
    )


def run_replay(
    plan: dict[str, Any],
    launch: dict[str, Any],
) -> dict[str, Any]:
    """Consume the scratch namespace once; never erase a completed stage."""
    scratch = Path(plan["scratch"])
    scratch.mkdir(parents=True, exist_ok=False)
    _atomic_json(scratch / "launch.json", launch)
    started = datetime.now(UTC)
    stage = "capture"
    try:
        with (scratch / "progress.log").open(
            "x", encoding="utf-8"
        ) as progress:
            captures = _run_stage(stage, plan["tasks"], capture_pair, progress)
            pairs = [read_bound(value) for value in captures]
            if sorted(row["input_id"] for row in pairs) != sorted(
                row["input_id"] for row in plan["tasks"]
            ):
                raise ValueError("captured pair census changed")
            captures.sort(key=lambda row: row["path"])
            seal = {
                "launch": launch,
                "pairs": captures,
                "pair_set_sha256": canonical_sha256(captures),
            }
            _atomic_json(scratch / "capture-seal.json", seal)
            stage = "dask"
            comparisons = compare_existing_dask(plan, pairs, progress)
            stage = "evaluation"
            evaluated = _run_stage(stage, pairs, evaluate_pair, progress)
            _atomic_json(
                scratch / "evaluation-seal.json",
                {
                    "images": sorted(
                        evaluated, key=lambda row: row["input_id"]
                    ),
                    "launch": launch,
                },
            )
            stage = "aggregation"
            progress.write(
                f"{datetime.now(UTC).isoformat()} stage=aggregation started\n"
            )
            progress.flush()
            decision = aggregate_records(plan, pairs, evaluated, comparisons)
            terminal = {
                "schema_version": 1,
                "campaign": "phase-5-source-catalogue-repair-cumulative",
                "evidence_role": "regression",
                "fresh_qualification": False,
                "compact_interval_mode": (
                    "Historical Phase 4 qualification-stage BCa engine; "
                    "the input population remains regression, not held-out."
                ),
                "candidate": plan["candidate"],
                "incumbent": plan["incumbent"],
                "launch": launch,
                "capture_seal": binding(scratch / "capture-seal.json"),
                "evaluation_seal": binding(scratch / "evaluation-seal.json"),
                "dask_comparisons": binding(scratch / "dask-comparisons.json"),
                "candidate_serial_executions": len(pairs),
                "incumbent_executions": len(pairs),
                "pybdsf_executions": 0,
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


def main() -> None:
    """Run an exact approved plan, or perform a complete no-write preflight."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authorization-sha256")
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    plan_binding = {
        "path": str(arguments.plan.resolve()),
        "sha256": arguments.plan_sha256,
    }
    plan = read_bound(plan_binding)
    root = Path(__file__).parents[2]
    verify_replay_plan(plan, root)
    if arguments.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight-pass",
                    "finder_execution_started": False,
                    "plan": plan_binding,
                }
            )
        )
        return
    if (
        arguments.authorization is None
        or arguments.authorization_sha256 is None
    ):
        raise PermissionError("exact one-use execution authorization required")
    authority_binding = {
        "path": str(arguments.authorization.resolve()),
        "sha256": arguments.authorization_sha256,
    }
    verify_authorization(plan_binding, read_bound(authority_binding))
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMBA_NUM_THREADS",
    ):
        if os.environ.get(key) != "1":
            raise ValueError(
                "R6 requires an explicit one-thread kernel budget"
            )
    launch = {
        "plan": plan_binding,
        "authorization": authority_binding,
        "execution_revision": plan["execution_revision"],
        "python_executable": sys.executable,
    }
    terminal = run_replay(plan, launch)
    print(
        json.dumps(
            {
                "output": plan["output"],
                "sha256": file_sha256(Path(plan["output"])),
                "status": terminal["result"]["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
