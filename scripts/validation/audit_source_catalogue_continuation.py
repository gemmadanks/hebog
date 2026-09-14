"""Exhaustively audit R6 reuse without starting or rescoring a finder."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any

from scripts.validation import source_catalogue_replay_plan as original
from scripts.validation.source_catalogue_continuation_inventory import (
    collect_completed_evaluations,
    verify_capture_seal,
    verify_retained_dask,
)

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import (
    canonical_sha256,
    source_tree_sha256,
)


def _verify_provenance(
    plan: dict[str, Any],
    review: dict[str, Any],
    repair: dict[str, Any],
    root: Path,
) -> None:
    """Keep the original finder separate from the current evaluation code."""
    historical = Path(plan["execution_root"])
    if (
        original.repository_revision(historical) != plan["execution_revision"]
        or source_tree_sha256(historical)
        != plan["candidate"]["source_tree_sha256"]
        or canonical_sha256(plan["configuration"])
        != plan["candidate"]["configuration_sha256"]
        or plan["candidate"] != repair["retained_candidate"]
        or repair["status"] != "frozen-non-executable"
        or any(repair["authorizations"].values())
        or any(
            plan[key] != value
            for key, value in review["execution"].items()
            if key != "plan_sha256"
        )
    ):
        raise ValueError("original candidate or repair provenance changed")
    if (
        dependency_inventory_sha256()
        != plan["runtime"]["dependency_inventory_sha256"]
        or platform.python_version() != plan["runtime"]["python"]
    ):
        raise ValueError("retained evaluation runtime changed")
    _verify_programs(review, repair, historical, root)
    for relative, value in plan["metadata"].items():
        if original.binding(Path(value["path"])) != value or (
            relative.startswith(("config/", "scripts/", "src/"))
            and original.binding(historical / relative)["sha256"]
            != value["sha256"]
        ):
            raise ValueError("immutable evaluation metadata changed")
    for relative, digest in original.EXPECTED_FILES.items():
        if plan["metadata"][relative]["sha256"] != digest:
            raise ValueError("closed evidence identity changed")


def _verify_programs(
    review: dict[str, Any],
    repair: dict[str, Any],
    historical: Path,
    root: Path,
) -> None:
    """Verify the old producer, amended adapter and unchanged late engine."""
    for relative, digest in review["program_sha256"].items():
        if original.binding(historical / relative)["sha256"] != digest:
            raise ValueError("original execution program changed")
    for relative, digest in repair["implementation_file_sha256"].items():
        # Documentation is historically bound, but is not imported by the
        # evaluator. Only executable/scientific identities must still match.
        if relative.startswith(("src/", "scripts/", "config/")) and (
            original.binding(root / relative)["sha256"] != digest
        ):
            raise ValueError("approved evaluator repair changed")
    for name in (
        "run_source_catalogue_cumulative_replay.py",
        "source_catalogue_campaign_evidence.py",
    ):
        relative = "scripts/validation/" + name
        if (
            original.binding(root / relative)["sha256"]
            != review["program_sha256"][relative]
        ):
            raise ValueError("retained late statistical rules changed")


def audit_retained_replay(
    plan_binding: dict[str, str],
    original_review_binding: dict[str, str],
    repair_review_binding: dict[str, str],
    repository_root: Path,
) -> dict[str, Any]:
    """Bind the original capture and approved repair to an explicit census."""
    auditor_programs = [
        original.binding(Path(__file__)),
        original.binding(
            Path(__file__).with_name(
                "source_catalogue_continuation_inventory.py"
            )
        ),
    ]
    plan = original.read_bound(plan_binding)
    review = original.read_bound(original_review_binding)
    repair = original.read_bound(repair_review_binding)
    if review["plan_sha256"] != plan_binding["sha256"] or review[
        "plan_canonical_sha256"
    ] != canonical_sha256(plan):
        raise ValueError("original reviewed plan changed")
    _verify_provenance(plan, review, repair, repository_root)
    historical = Path(plan["execution_root"])
    original.verify_census(plan)
    original.verify_task_metadata(plan, historical)
    original.verify_historical_producer(plan, historical)
    original.verify_reference_identities(
        historical,
        original.read_bound(plan["metadata"][original.REQUEST]),
        Path(
            plan["metadata"][original.REFERENCE + "/recovery.json"]["path"]
        ).parent,
    )
    for value in plan["retained_references"].values():
        original.native_artifacts(Path(value["path"]), value["sha256"])
    for task in plan["tasks"]:
        value = task["input_manifest"]
        original.native_artifacts(Path(value["path"]), value["sha256"])
    expected = repair["expected_retained_evidence"]
    scratch = Path(plan["scratch"])
    seal_binding = {
        "path": str(scratch / "capture-seal.json"),
        "sha256": expected["capture_seal_sha256"],
    }
    dask_binding = {
        "path": str(scratch / "dask-comparisons.json"),
        "sha256": expected["dask_comparisons_sha256"],
    }
    seal = original.read_bound(seal_binding)
    authority_binding = seal["launch"]["authorization"]
    authority = original.read_bound(authority_binding)
    failure_binding = original.binding(scratch / "process-failure.json")
    failure = original.read_bound(failure_binding)
    if (
        authority["plan_sha256"] != plan_binding["sha256"]
        or authority["identity_review_sha256"]
        != original_review_binding["sha256"]
        or authority["expected_execution_sha256"]
        != review["expected_execution_sha256"]
        or failure["stage"] != "evaluation"
        or failure["launch"] != seal["launch"]
    ):
        raise ValueError("historical launch or process failure changed")
    output = Path(plan["output"])
    if output.exists() or output.is_symlink():
        raise FileExistsError(
            "R6 already has an atomic terminal; do not rescore"
        )
    pairs = verify_capture_seal(plan, plan_binding, seal_binding)
    verify_retained_dask(plan, pairs, dask_binding)
    inventory = collect_completed_evaluations(pairs)
    if any(
        inventory[key] != expected[key]
        for key in (
            "complete_input_count",
            "complete_finder_record_count",
            "complete_marker_set_sha256",
        )
    ):
        raise ValueError("reviewed reusable evaluation census changed")
    if any(
        original.binding(Path(row["path"])) != row for row in auditor_programs
    ):
        raise ValueError("audit program changed during verification")
    return {
        "schema_version": 1,
        "status": "verified-non-executable-inventory",
        "finder_execution_started": False,
        "evaluation_started": False,
        "retry_authorized": False,
        "candidate": plan["candidate"],
        "incumbent": plan["incumbent"],
        "original_plan": plan_binding,
        "original_review": original_review_binding,
        "repair_review": repair_review_binding,
        "consumed_original_authority": authority_binding,
        "original_process_failure": failure_binding,
        "capture_seal": seal_binding,
        "dask_comparisons": dask_binding,
        "capture_pair_count": len(pairs),
        "reference_run_count": len(plan["retained_references"]),
        "retained_dask_comparison_count": len(plan["dask_input_ids"]),
        "new_finder_executions": 0,
        "new_dask_comparisons": 0,
        "new_evaluations": 0,
        "auditor_programs": auditor_programs,
        **inventory,
    }


def main() -> None:
    """Print the no-write audit, optionally sealing its separate inventory."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "original-review", "repair-review"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--inventory", type=Path)
    arguments = parser.parse_args()
    bindings = [
        {
            "path": str(getattr(arguments, name).absolute()),
            "sha256": getattr(arguments, name + "_sha256"),
        }
        for name in ("plan", "original_review", "repair_review")
    ]
    record = audit_retained_replay(
        *bindings, repository_root=Path(__file__).resolve().parents[2]
    )
    if arguments.inventory is not None:
        output = arguments.inventory.resolve()
        plan = original.read_bound(bindings[0])
        if (
            any(
                output.is_relative_to(Path(plan[key]).resolve())
                for key in ("scratch", "execution_root", "historical_root")
            )
            or output == Path(plan["output"]).resolve()
        ):
            raise ValueError(
                "inventory must not occupy a preserved R6 namespace"
            )
        _atomic_json(arguments.inventory, record)
    print(
        json.dumps(
            {
                key: value
                for key, value in record.items()
                if key
                not in {
                    "complete_markers",
                    "completed_evaluations",
                    "pending_input_ids",
                    "partial_files",
                }
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
