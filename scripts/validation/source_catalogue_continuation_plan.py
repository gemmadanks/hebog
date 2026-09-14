"""Freeze and admit an evaluation-only R6 continuation, never finder work."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from scripts.validation.audit_source_catalogue_continuation import (
    audit_retained_replay,
)
from scripts.validation.source_catalogue_replay_plan import (
    binding,
    read_bound,
    repository_revision,
)

import hebog
from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import (
    canonical_sha256,
    source_tree_sha256,
)

_ROOT = Path(__file__).resolve().parents[2]
_COUNTS = {
    "capture_pair_count": 2400,
    "reference_run_count": 9600,
    "retained_dask_comparison_count": 12,
    "complete_input_count": 808,
    "complete_finder_record_count": 4032,
}
_PENDING_COUNT = 1592
_THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMBA_NUM_THREADS",
)


def program_hashes(root: Path) -> dict[str, str]:
    """Bind the validation-program closure, including historical loaders."""
    return {
        str(path.relative_to(root)): binding(path)["sha256"]
        for path in sorted((root / "scripts/validation").rglob("*.py"))
    }


def build_plan(
    root: Path,
    inventory_binding: dict[str, str],
    inventory_review_binding: dict[str, str],
    scratch: Path,
) -> dict[str, Any]:
    """Freeze code, inventory and separate paths without executing work."""
    inventory = read_bound(inventory_binding)
    review = read_bound(inventory_review_binding)
    original = read_bound(inventory["original_plan"])
    if (
        review["status"] != "frozen-non-executable"
        or any(review["authorizations"].values())
        or review["inventory"]["sha256"] != inventory_binding["sha256"]
        or review["original_candidate"] != inventory["candidate"]
        or original["candidate"] != inventory["candidate"]
        or original["incumbent"] != inventory["incumbent"]
        or inventory["status"] != "verified-non-executable-inventory"
        or any(inventory[key] != count for key, count in _COUNTS.items())
        or len(inventory["pending_input_ids"]) != _PENDING_COUNT
    ):
        raise ValueError("frozen inventory review or census changed")
    return {
        "schema_version": 1,
        "status": "frozen-non-executable",
        "campaign": "phase-5-r6-evaluation-only-continuation",
        "inventory": inventory_binding,
        "inventory_identity_review": inventory_review_binding,
        "candidate": original["candidate"],
        "incumbent": original["incumbent"],
        "execution_root": str(root.resolve()),
        "execution_revision": repository_revision(root),
        "evaluator_source_tree_sha256": source_tree_sha256(root),
        "program_sha256": program_hashes(root),
        "runtime": original["runtime"],
        "workers": 2,
        "new_finder_executions": 0,
        "new_dask_comparisons": 0,
        "reused_input_evaluations": inventory["complete_input_count"],
        "new_input_evaluations": len(inventory["pending_input_ids"]),
        "scratch": str(scratch.absolute()),
        "output": original["output"],
        "required_free_bytes": 8 * 1024**3,
    }


def verify_execution_code(plan: dict[str, Any]) -> None:
    """Reject code, runtime or immutable-import substitution."""
    root = Path(plan["execution_root"])
    if (
        root != _ROOT
        or repository_revision(root) != plan["execution_revision"]
        or not Path(hebog.__file__).resolve().is_relative_to(root / "src")
        or source_tree_sha256(root) != plan["evaluator_source_tree_sha256"]
        or program_hashes(root) != plan["program_sha256"]
    ):
        raise ValueError("immutable continuation code or imports changed")
    if (
        platform.python_version() != plan["runtime"]["python"]
        or dependency_inventory_sha256()
        != plan["runtime"]["dependency_inventory_sha256"]
        or any(os.environ.get(key) != "1" for key in _THREAD_VARIABLES)
    ):
        raise ValueError("continuation runtime or one-thread budget changed")


def verify_namespace(plan: dict[str, Any], original: dict[str, Any]) -> None:
    """Keep the new write-once work away from every preserved namespace."""
    scratch = Path(plan["scratch"])
    output = Path(plan["output"])
    protected = [
        Path(original[key]).resolve()
        for key in ("scratch", "execution_root", "historical_root")
    ] + [
        Path(plan["execution_root"]).resolve(),
        Path(plan["inventory"]["path"]).resolve().parent,
    ]
    if (
        not scratch.is_absolute()
        or scratch.resolve() != scratch
        or any(
            scratch.is_relative_to(path) or path.is_relative_to(scratch)
            for path in protected
        )
        or output != Path(original["output"])
    ):
        raise ValueError("continuation must preserve original namespaces")
    if any(path.exists() or path.is_symlink() for path in (scratch, output)):
        raise FileExistsError("continuation namespace already consumed")
    if shutil.disk_usage(scratch.parent).free < plan["required_free_bytes"]:
        raise ValueError("continuation disk admission failed")


def verify_preflight(
    plan: dict[str, Any], review_binding: dict[str, str]
) -> None:
    """Repeat the exhaustive no-write audit under the new exact identity."""
    verify_execution_code(plan)
    review = read_bound(review_binding)
    if (
        review["status"] != "frozen-non-executable"
        or any(review["authorizations"].values())
        or review["expected_execution_sha256"] != canonical_sha256(plan)
        or review["plan_canonical_sha256"] != canonical_sha256(plan)
    ):
        raise ValueError("continuation identity review changed")
    inventory = read_bound(plan["inventory"])
    root = Path(plan["execution_root"])
    if plan != build_plan(
        root,
        plan["inventory"],
        plan["inventory_identity_review"],
        Path(plan["scratch"]),
    ):
        raise ValueError("continuation plan no longer binds its inventory")
    original = read_bound(inventory["original_plan"])
    verify_namespace(plan, original)
    fresh = audit_retained_replay(
        inventory["original_plan"],
        inventory["original_review"],
        inventory["repair_review"],
        repository_root=root,
    )
    # Auditor locations differ between immutable checkouts; their exact
    # original files and unchanged bytes are both verified, never ignored.
    for value in inventory["auditor_programs"]:
        if binding(Path(value["path"])) != value:
            raise ValueError("original inventory auditor changed")
    if [
        (Path(value["path"]).name, value["sha256"])
        for value in fresh["auditor_programs"]
    ] != [
        (Path(value["path"]).name, value["sha256"])
        for value in inventory["auditor_programs"]
    ] or {
        key: value for key, value in fresh.items() if key != "auditor_programs"
    } != {
        key: value
        for key, value in inventory.items()
        if key != "auditor_programs"
    }:
        raise ValueError("exhaustively verified inventory changed")
    verify_execution_code(plan)
    verify_namespace(plan, original)


def verify_authorization(
    plan_binding: dict[str, str],
    review_binding: dict[str, str],
    authorization_binding: dict[str, str],
) -> None:
    """Admit one exact evaluation-only execution, never original authority."""
    review = read_bound(review_binding)
    authority = read_bound(authorization_binding)
    if (
        authority.get("status")
        != "authorized-for-one-r6-evaluation-only-continuation"
        or type(authority.get("execution_count")) is not int
        or authority["execution_count"] != 1
        or authority.get("plan_sha256") != plan_binding["sha256"]
        or review["plan_sha256"] != plan_binding["sha256"]
        or authority.get("identity_review_sha256") != review_binding["sha256"]
        or authority.get("expected_execution_sha256")
        != review["expected_execution_sha256"]
    ):
        raise PermissionError(
            "exact one-use evaluation-only authority changed"
        )


def main() -> None:
    """Freeze a non-executable plan without admitting or executing it."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inventory", "inventory-review"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output-plan", type=Path, required=True)
    arguments = parser.parse_args()
    plan = build_plan(
        _ROOT,
        {
            "path": str(arguments.inventory.resolve()),
            "sha256": arguments.inventory_sha256,
        },
        {
            "path": str(arguments.inventory_review.resolve()),
            "sha256": arguments.inventory_review_sha256,
        },
        arguments.scratch,
    )
    original = read_bound(read_bound(plan["inventory"])["original_plan"])
    verify_namespace(plan, original)
    output = arguments.output_plan.resolve()
    if output == Path(plan["output"]) or any(
        output.is_relative_to(Path(value).resolve())
        for value in (
            original["scratch"],
            original["execution_root"],
            original["historical_root"],
            plan["scratch"],
        )
    ):
        raise ValueError("frozen plan must not occupy a preserved namespace")
    _atomic_json(output, plan)
    print(
        json.dumps(
            {
                "plan": binding(output),
                "expected_execution_sha256": canonical_sha256(plan),
                "status": "frozen-non-executable",
            }
        )
    )


if __name__ == "__main__":
    main()
