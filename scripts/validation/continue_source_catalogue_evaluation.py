"""Complete missing R6 evaluations without recapturing or rescoring inputs."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.validation.run_source_catalogue_cumulative_replay import (
    _run_stage,
    aggregate_records,
)
from scripts.validation.source_catalogue_campaign_evidence import (
    load_image_records,
)
from scripts.validation.source_catalogue_campaign_execution import (
    evaluate_pair,
)
from scripts.validation.source_catalogue_continuation_inventory import (
    collect_completed_evaluations,
)
from scripts.validation.source_catalogue_continuation_plan import (
    verify_authorization,
    verify_execution_code,
    verify_preflight,
)
from scripts.validation.source_catalogue_replay_plan import binding, read_bound

from hebog.validation.diagnostic_retention import (
    _atomic_json,
    _verify_record_digest,
)
from hebog.validation.external_runners import file_sha256

_AMENDED_DIAGNOSTIC_SCHEMA = 2


def prepare_evaluations(
    inventory: dict[str, Any], scratch: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Admit exact retained completions and isolate only missing tasks."""
    pairs = [
        read_bound(value)
        for value in read_bound(inventory["capture_seal"])["pairs"]
    ]
    if len(pairs) != inventory["capture_pair_count"]:
        raise ValueError("retained capture census changed")
    retained = collect_completed_evaluations(pairs)
    if any(retained[key] != inventory[key] for key in retained):
        raise ValueError("retained evaluation inventory changed")
    tasks: list[dict[str, Any]] = []
    pending = set(inventory["pending_input_ids"])
    for pair in sorted(pairs, key=lambda row: row["input_id"]):
        identifier = pair["input_id"]
        if (
            not identifier
            or Path(identifier).name != identifier
            or (identifier in {".", ".."})
        ):
            raise ValueError("input identifier must be one path component")
        if identifier in pending:
            tasks.append(
                {
                    **pair,
                    "evaluation_directory": str(
                        scratch / "evaluations" / identifier
                    ),
                }
            )
    return pairs, tasks


def verify_new_records(
    tasks: list[dict[str, Any]], evaluated: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Require durable, complete amended records from each missing input."""
    indexed = {task["input_id"]: task for task in tasks}
    if len(indexed) != len(tasks) or sorted(
        row["input_id"] for row in evaluated
    ) != sorted(indexed):
        raise ValueError("new evaluation census changed")
    markers: list[dict[str, str]] = []
    for row in evaluated:
        task = indexed[row["input_id"]]
        directory = Path(task["evaluation_directory"])
        marker = binding(directory / "complete.json")
        if read_bound(marker) != row or {
            entry["path"] for entry in row["records"]
        } != {
            str(directory / f"{finder}.json") for finder in task["captures"]
        }:
            raise ValueError("new evaluation completion or paths changed")
        records = load_image_records(
            row["records"],
            [(task["input_id"], finder) for finder in task["captures"]],
        )
        for record in records:
            if (
                type(record["schema_version"]) is not int
                or record["schema_version"] != 1
                or record["lane"] != task["lane"]
                or record["capture"] != task["captures"][record["finder_id"]]
            ):
                raise ValueError("new record schema or capture changed")
            if task["lane"] == "continuum":
                diagnostic = record["source_diagnostics"]
                _verify_record_digest(diagnostic)
                if (
                    type(diagnostic["schema_version"]) is not int
                    or diagnostic["schema_version"]
                    != _AMENDED_DIAGNOSTIC_SCHEMA
                    or diagnostic["input_id"] != task["input_id"]
                    or diagnostic["finder_id"] != record["finder_id"]
                    or any(
                        source["support_label"] is not None
                        and (
                            type(source["support_label"]) is not int
                            or source["support_label"] <= 0
                        )
                        for source in diagnostic["source_records"]
                    )
                ):
                    raise ValueError("amended source diagnostic changed")
        markers.append(marker)
    return sorted(markers, key=lambda row: row["path"])


def evaluate_missing_pair(task: dict[str, Any]) -> dict[str, Any]:
    """Validate each durable input immediately inside its spawned worker."""
    completed = evaluate_pair(task)
    verify_new_records([task], [completed])
    return completed


def run_continuation(
    plan: dict[str, Any], launch: dict[str, Any]
) -> dict[str, Any]:
    """Publish durable combined evidence before the unchanged late engine."""
    scratch = Path(plan["scratch"])
    output = Path(plan["output"])
    if any(path.exists() or path.is_symlink() for path in (scratch, output)):
        raise FileExistsError("continuation namespace already consumed")
    verify_execution_code(plan)
    inventory = read_bound(plan["inventory"])
    pairs, tasks = prepare_evaluations(inventory, scratch)
    original_plan = read_bound(inventory["original_plan"])
    dask = read_bound(inventory["dask_comparisons"])["comparisons"]
    scratch.mkdir(parents=True, exist_ok=False)
    _atomic_json(scratch / "launch.json", launch)
    started = datetime.now(UTC).isoformat()
    stage = "evaluation"
    try:
        with (scratch / "progress.log").open("x", encoding="utf-8") as log:
            new = _run_stage(stage, tasks, evaluate_missing_pair, log)
            markers = verify_new_records(tasks, new)
            prepare_evaluations(read_bound(plan["inventory"]), scratch)
            evaluated = sorted(
                [*inventory["completed_evaluations"], *new],
                key=lambda row: row["input_id"],
            )
            seal_path = scratch / "evaluation-seal.json"
            _atomic_json(
                seal_path,
                {
                    "schema_version": 1,
                    "launch": launch,
                    "inventory": plan["inventory"],
                    "images": evaluated,
                    "complete_markers": [
                        *inventory["complete_markers"],
                        *markers,
                    ],
                    "reused_input_count": inventory["complete_input_count"],
                    "new_input_count": len(new),
                },
            )
            seal_binding = binding(seal_path)
            stage = "aggregation"
            log.write(f"{datetime.now(UTC).isoformat()} stage=aggregation\n")
            log.flush()
            decision = aggregate_records(original_plan, pairs, evaluated, dask)
            stage = "publication"
            verify_execution_code(plan)
            read_bound(seal_binding)
            verify_new_records(tasks, new)
            prepare_evaluations(read_bound(plan["inventory"]), scratch)
            read_bound(inventory["original_plan"])
            read_bound(inventory["dask_comparisons"])
            terminal = {
                "schema_version": 1,
                "campaign": "phase-5-source-catalogue-repair-cumulative",
                "evidence_role": "regression",
                "fresh_qualification": False,
                "candidate": original_plan["candidate"],
                "incumbent": original_plan["incumbent"],
                "launch": launch,
                "inventory": plan["inventory"],
                "capture_seal": inventory["capture_seal"],
                "evaluation_seal": seal_binding,
                "dask_comparisons": inventory["dask_comparisons"],
                "reused_input_evaluations": inventory["complete_input_count"],
                "new_input_evaluations": len(new),
                "new_candidate_executions": 0,
                "new_incumbent_executions": 0,
                "new_pybdsf_executions": 0,
                "new_dask_comparisons": 0,
                "started_at": started,
                "completed_at": datetime.now(UTC).isoformat(),
                "result": decision,
            }
            _atomic_json(output, terminal)
            return terminal
    except BaseException as error:
        _atomic_json(
            scratch / "process-failure.json",
            {
                "stage": stage,
                "exception_type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "launch": launch,
                "recorded_at": datetime.now(UTC).isoformat(),
                "retained_evidence_preserved": True,
            },
        )
        raise


def main() -> None:
    """Require exhaustive admission and separate exact execution authority."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "identity-review"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authorization-sha256")
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    plan_binding = {
        "path": str(arguments.plan.resolve()),
        "sha256": arguments.plan_sha256,
    }
    review_binding = {
        "path": str(arguments.identity_review.resolve()),
        "sha256": arguments.identity_review_sha256,
    }
    plan = read_bound(plan_binding)
    if arguments.preflight_only:
        verify_preflight(plan, review_binding)
        print(
            json.dumps(
                {
                    "status": "preflight-pass",
                    "finder_execution_started": False,
                    "evaluation_started": False,
                    "plan": plan_binding,
                    "identity_review": review_binding,
                }
            )
        )
        return
    if (
        arguments.authorization is None
        or arguments.authorization_sha256 is None
    ):
        raise PermissionError("exact continuation authorization required")
    authority_binding = {
        "path": str(arguments.authorization.resolve()),
        "sha256": arguments.authorization_sha256,
    }
    verify_authorization(plan_binding, review_binding, authority_binding)
    verify_preflight(plan, review_binding)
    read_bound(plan_binding)
    verify_authorization(plan_binding, review_binding, authority_binding)
    terminal = run_continuation(
        plan,
        {
            "plan": plan_binding,
            "identity_review": review_binding,
            "authorization": authority_binding,
            "python_executable": sys.executable,
        },
    )
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
