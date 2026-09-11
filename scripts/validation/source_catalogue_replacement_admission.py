"""Exact, isolated admission for a current-only replacement replay."""

from __future__ import annotations

import copy
import os
import platform
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.validation.source_catalogue_continuation_inventory import (
    verify_capture_seal,
)
from scripts.validation.source_catalogue_continuation_plan import (
    program_hashes,
)
from scripts.validation.source_catalogue_replacement_inventory import (
    replacement_tasks,
    retained_inventory,
)
from scripts.validation.source_catalogue_replay_plan import (
    DASK_COUNT,
    INPUT_COUNT,
    REFERENCE_COUNT,
    binding,
    native_artifacts,
    read_bound,
    repository_revision,
)

import hebog
from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.evidence import CampaignImplementationIdentity
from hebog.validation.external_runners import (
    canonical_sha256,
    source_tree_sha256,
)

PREPARATION_SHA256 = (
    "a1c60497ac6a93b86e37460d24a9956a9eb743139481b048e22c47ca5ae8765c"
)
RETAINED_COUNT = 8000
THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMBA_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def replacement_implementations(
    original: list[dict[str, Any]],
    candidate: dict[str, str],
    dependency_sha256: str,
) -> list[dict[str, Any]]:
    """Bind the new candidate without relabeling any retained reference."""
    expected = {
        "current-hebog",
        "incumbent-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
    }
    identifiers = [row["identifier"] for row in original]
    if len(identifiers) != len(expected) or set(identifiers) != expected:
        raise ValueError("replacement implementation census changed")
    result = copy.deepcopy(original)
    for row in result:
        if row["identifier"] == "current-hebog":
            row["execution_configuration_sha256"] = candidate[
                "configuration_sha256"
            ]
            row["software"]["commit_sha"] = candidate["revision"]
            row["software"]["source_tree_sha256"] = candidate[
                "source_tree_sha256"
            ]
            row["software"]["dependency_inventory_sha256"] = dependency_sha256
        CampaignImplementationIdentity.model_validate(row)
    return result


def verify_census(prepared: dict[str, Any]) -> None:
    """Preserve the reviewed population, resource count and binding gates."""
    counts = {
        "workers": 2,
        "candidate_serial_executions": 2400,
        "existing_dask_comparisons": 12,
        "incumbent_executions": 0,
        "pybdsf_executions": 0,
        "aegean_executions": 0,
        "bootstrap_resamples": 50000,
        "bootstrap_seed": 20260810,
    }
    identifiers = [row["input_id"] for row in prepared["tasks"]]
    if (
        any(
            type(prepared.get(key)) is not int or prepared[key] != count
            for key, count in counts.items()
        )
        or len(identifiers) != INPUT_COUNT
        or len(set(identifiers)) != INPUT_COUNT
        or Counter(row["lane"] for row in prepared["tasks"])
        != {"compact-blend": 800, "continuum": 1600}
        or len(prepared["retained_references"]) != REFERENCE_COUNT
        or len(prepared["retained_records"]) != RETAINED_COUNT
        or len(prepared["dask_input_ids"]) != DASK_COUNT
        or len(set(prepared["dask_input_ids"])) != DASK_COUNT
        or not set(prepared["dask_input_ids"]).issubset(identifiers)
        or prepared["bindings"]
        != {"comparisons": 1187, "safety_checks": 5, "required_all_pass": True}
    ):
        raise ValueError("replacement census or binding contract changed")


def _verify_resources(
    prepared: dict[str, Any],
    preparation: dict[str, str],
    resources: dict[str, Any],
) -> None:
    """Bind a sufficient measured reserve to the exact candidate and probe."""
    required = resources.get("required_free_bytes")
    observed = resources.get("observed_free_bytes")
    if (
        resources.get("status") != "resource-admitted"
        or resources.get("candidate") != prepared["candidate"]
        or resources.get("preparation") != preparation
        or resources.get("cost_probe") != prepared["cost_probe"]
        or resources.get("runtime") != prepared["runtime"]
        or type(required) is not int
        or required < prepared["admission"]["provisional_required_free_bytes"]
        or type(observed) is not int
        or observed < required
        or prepared["cost_probe"] not in resources.get("evidence", [])
    ):
        raise ValueError("replacement resource admission changed")
    for value in resources["evidence"]:
        if binding(Path(value["path"])) != value:
            raise ValueError("replacement resource evidence changed")


def build_plan(
    preparation_binding: dict[str, str],
    resource_binding: dict[str, str],
    root: Path,
) -> dict[str, Any]:
    """Derive an exact plan without transferring historical authority."""
    if preparation_binding["sha256"] != PREPARATION_SHA256:
        raise ValueError("replacement preparation identity changed")
    prepared = read_bound(preparation_binding)
    if (
        prepared["status"] != "prepared-not-execution-admitted"
        or any(prepared["authorizations"].values())
        or prepared["execution_identity"] is not None
    ):
        raise ValueError("replacement preparation is not non-executable")
    verify_census(prepared)
    resources = read_bound(resource_binding)
    _verify_resources(prepared, preparation_binding, resources)
    closed = read_bound(prepared["closed_terminal"])
    inventory = read_bound(closed["inventory"])
    original = read_bound(inventory["original_plan"])
    if prepared["dask_input_ids"] != original["dask_input_ids"]:
        raise ValueError("replacement Dask selection contract changed")
    # Copy only the execution contract, not historical execution authority.
    keys = (
        "candidate",
        "incumbent",
        "configuration",
        "scientific_composition_sha256",
        "tasks",
        "scratch",
        "execution_root",
        "output",
        "dask_input_ids",
        "existing_dask_comparisons",
        "workers",
        "candidate_serial_executions",
        "incumbent_executions",
        "pybdsf_executions",
        "aegean_executions",
        "retained_references",
        "metadata",
        "bootstrap_resamples",
        "bootstrap_seed",
        "retained_records",
        "retained_record_set_sha256",
        "bindings",
        "runtime",
        "candidate_review",
        "closed_terminal",
        "closed_capture_seal",
        "closed_evaluation_seal",
    )
    plan = copy.deepcopy({key: prepared[key] for key in keys})
    plan.update(
        schema_version=1,
        status="frozen-non-executable",
        authorizations=copy.deepcopy(prepared["authorizations"]),
        execution_identity=None,
        preparation=preparation_binding,
        resource_admission=resource_binding,
        required_free_bytes=resources["required_free_bytes"],
        cost_probe=prepared["cost_probe"],
        protected_roots=[
            original[key]
            for key in ("scratch", "execution_root", "historical_root")
        ],
        execution_revision=repository_revision(root),
        program_sha256=program_hashes(root),
        implementations=replacement_implementations(
            original["implementations"],
            prepared["candidate"],
            prepared["runtime"]["dependency_inventory_sha256"],
        ),
    )
    return plan


def verify_namespace(plan: dict[str, Any]) -> None:
    """Reject occupied paths, symlinks and overlapping code/product roots."""
    root = Path(plan["execution_root"])
    scratch = Path(plan["scratch"])
    output = Path(plan["output"])
    if (
        any(
            not path.is_absolute() or path.resolve() != path
            for path in (root, scratch, output)
        )
        or scratch.is_relative_to(root)
        or root.is_relative_to(scratch)
        or not output.is_relative_to(root / "benchmark-results")
        or any(
            path.is_relative_to(Path(protected).resolve())
            or Path(protected).resolve().is_relative_to(path)
            for path in (root, scratch)
            for protected in plan["protected_roots"]
        )
    ):
        raise ValueError("replacement namespace isolation changed")
    if any(path.exists() or path.is_symlink() for path in (scratch, output)):
        raise FileExistsError("replacement namespace already consumed")


def verify_execution_code(plan: dict[str, Any], root: Path) -> None:
    """Check the committed program closure and actual imported science."""
    if (
        root != Path(plan["execution_root"])
        or repository_revision(root) != plan["execution_revision"]
        or source_tree_sha256(root) != plan["candidate"]["source_tree_sha256"]
        or program_hashes(root) != plan["program_sha256"]
        or not Path(hebog.__file__).resolve().is_relative_to(root / "src")
    ):
        raise ValueError("replacement immutable code or imports changed")
    if (
        platform.python_version() != plan["runtime"]["python"]
        or platform.platform() != plan["runtime"]["platform"]
        or dependency_inventory_sha256()
        != plan["runtime"]["dependency_inventory_sha256"]
        or any(os.environ.get(name) != "1" for name in THREAD_VARIABLES)
    ):
        raise ValueError("replacement runtime or thread budget changed")


def verify_preflight(plan: dict[str, Any], root: Path) -> None:
    """Verify all input/evidence bytes before allowing a namespace claim."""
    verify_execution_code(plan, root)
    verify_namespace(plan)
    if plan != build_plan(
        plan["preparation"], plan["resource_admission"], root
    ):
        raise ValueError("replacement frozen plan changed")
    resources = read_bound(plan["resource_admission"])
    if (
        shutil.disk_usage(Path(plan["scratch"]).parent).free
        < resources["required_free_bytes"]
    ):
        raise ValueError("replacement disk admission failed")
    _verify_scientific_bindings(plan, root)
    _verify_retained_inputs(plan, root)
    verify_execution_code(plan, root)
    verify_namespace(plan)
    if (
        shutil.disk_usage(Path(plan["scratch"]).parent).free
        < resources["required_free_bytes"]
    ):
        raise ValueError("replacement disk admission failed")


def _verify_scientific_bindings(plan: dict[str, Any], root: Path) -> None:
    """Authenticate scientific identities and mixed JSON/text provenance."""
    review = read_bound(plan["candidate_review"])
    if (
        review["algorithm_candidate"] != plan["candidate"]
        or canonical_sha256(plan["configuration"])
        != plan["candidate"]["configuration_sha256"]
        or review["scientific_composition_sha256"]
        != plan["scientific_composition_sha256"]
    ):
        raise ValueError("replacement scientific identity changed")
    for value in review["frozen_documents"].values():
        if binding(root / value["path"])["sha256"] != value["sha256"]:
            raise ValueError("replacement scientific document changed")
    for value in plan["metadata"].values():
        if binding(Path(value["path"])) != value:
            raise ValueError("replacement metadata changed")


def _verify_retained_inputs(plan: dict[str, Any], root: Path) -> None:
    """Hash the full frozen census without rerunning or rescoring any row."""
    closed = read_bound(plan["closed_terminal"])
    inventory = read_bound(closed["inventory"])
    original = read_bound(inventory["original_plan"])
    for index, value in enumerate(plan["retained_references"].values(), 1):
        native_artifacts(Path(value["path"]), value["sha256"])
        if index % 2400 == 0:
            print(
                f"Preflight: {index}/9600 reference runs verified", flush=True
            )
    for task in plan["tasks"]:
        value = task["input_manifest"]
        native_artifacts(Path(value["path"]), value["sha256"])
    print("Preflight: 2400 input bundles verified", flush=True)
    pairs = verify_capture_seal(
        original, inventory["original_plan"], plan["closed_capture_seal"]
    )
    if len(pairs) != INPUT_COUNT:
        raise ValueError("replacement capture census changed")
    retained = retained_inventory(
        pairs, read_bound(plan["closed_evaluation_seal"])["images"]
    )
    if (
        retained != plan["retained_records"]
        or canonical_sha256(retained) != plan["retained_record_set_sha256"]
        or replacement_tasks(
            pairs,
            root=root,
            scratch=Path(plan["scratch"]),
            configuration=plan["configuration"],
        )
        != plan["tasks"]
    ):
        raise ValueError("replacement capture or reusable inventory changed")
    print(
        "Preflight: 2400 capture pairs and 8000 reusable records verified",
        flush=True,
    )


def verify_authority(
    plan_binding: dict[str, str],
    review_binding: dict[str, str],
    expected: str,
    decision: dict[str, Any],
) -> None:
    """Require a fresh decision bound to this exact plan and review."""
    if (
        decision.get("status")
        != "authorized-for-one-current-only-replacement-replay"
        or decision.get("plan_sha256") != plan_binding["sha256"]
        or decision.get("identity_review_sha256") != review_binding["sha256"]
        or decision.get("expected_execution_sha256") != expected
        or type(decision.get("execution_count")) is not int
        or decision["execution_count"] != 1
    ):
        raise PermissionError("replacement exact one-use authority changed")
