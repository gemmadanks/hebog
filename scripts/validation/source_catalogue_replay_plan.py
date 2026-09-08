"""Freeze and verify the R6 population without executing any finder."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
import os
import platform
import runpy
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.validation.source_catalogue_campaign_evidence import (
    load_cumulative_policy,
)
from scripts.validation.source_catalogue_input_evaluation import (
    evaluation_context,
    native_artifacts,
)

import hebog
from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.datasets import recipe_sha256
from hebog.validation.evidence import (
    CampaignImplementationIdentity,
    SoftwareIdentity,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

REVIEW = (
    "config/contracts/phase-5-source-catalogue-repair-identity-review.json"
)
POPULATION = "config/contracts/phase-5-prospective-paired-population.json"
REGISTRY = (
    "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
REQUEST = (
    "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
REFERENCE = (
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
BASELINE = (
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
EXPECTED_FILES = {
    POPULATION: (
        "0bd3e6a6e505f8fb307a108d90e932f6b3f16ae5fc6c654ab4c82de14f483687"
    ),
    REQUEST: (
        "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
    ),
    REFERENCE + "/recovery.json": (
        "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
    ),
    BASELINE: (
        "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
    ),
}
INCUMBENT = {
    "revision": "85d580713664b962ae256a98b065849cf8eb9283",
    "source_tree_sha256": (
        "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
    ),
    "configuration_sha256": (
        "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
    ),
    "execution_revision": "c1614c2e1b7f8a47877c20a97bb732541ae039d2",
}
INPUT_COUNT = 2400
REFERENCE_COUNT = 9600
DASK_COUNT = 12


def select_dask_inputs(tasks: list[dict[str, Any]]) -> list[str]:
    """Cover all five datasets before adding result-neutral extra repeats."""
    ordered = sorted(
        tasks,
        key=lambda row: (
            hashlib.sha256(row["input_id"].encode()).hexdigest(),
            row["input_id"],
        ),
    )
    selected: list[str] = []
    for dataset in sorted({row["dataset_identifier"] for row in tasks}):
        selected.extend(
            [
                row["input_id"]
                for row in ordered
                if row["dataset_identifier"] == dataset
            ][:2]
        )
    # The population has five datasets: two each, plus two global extras.
    selected.extend(
        [
            row["input_id"]
            for row in ordered
            if row["input_id"] not in selected
        ][: DASK_COUNT - len(selected)]
    )
    return selected


def binding(path: Path) -> dict[str, str]:
    """Bind one existing immutable document by its exact bytes."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required regular file absent: {path}")
    return {"path": str(path), "sha256": file_sha256(path)}


def read_bound(value: dict[str, str]) -> dict[str, Any]:
    """Reject substituted documents before parsing them."""
    path = Path(value["path"])
    if binding(path) != value:
        raise ValueError("bound document changed")
    return json.loads(path.read_bytes())


def repository_revision(root: Path) -> str:
    """Require a clean tracked checkout; ignored evidence is not code."""
    if subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=no"), cwd=root
    ):
        raise ValueError("execution checkout has tracked changes")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=root, text=True
    ).strip()


def selected_inputs(
    request: dict[str, Any], population: dict[str, Any]
) -> list[dict[str, Any]]:
    """Preserve the original hash-ordered, result-neutral 2,400-image set."""
    selection = population["selection"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in request["inputs"]:
        grouped.setdefault(
            (row["lane"], row["dataset_identifier"]), []
        ).append(row)
    selected: list[dict[str, Any]] = []
    for (lane, _dataset), values in sorted(grouped.items()):
        count = (
            selection["compact_count"]
            if lane == "compact-blend"
            else selection["continuum_count_per_dataset"]
        )
        selected.extend(
            sorted(
                values,
                key=lambda row: (
                    hashlib.sha256(row["input_id"].encode()).hexdigest(),
                    row["input_id"],
                ),
            )[:count]
        )
    identifiers = sorted(row["input_id"] for row in selected)
    if (
        len(identifiers) != INPUT_COUNT
        or len(set(identifiers)) != INPUT_COUNT
        or canonical_sha256(identifiers)
        != selection["selected_input_set_canonical_sha256"]
    ):
        raise ValueError("frozen R6 population changed")
    return selected


def verify_reference_identities(
    root: Path,
    request: dict[str, Any],
    retained_root: Path,
) -> None:
    """Bind the exact original ordered product sets, not newly chosen bytes."""
    verifier = runpy.run_path(
        str(
            root / "scripts/validation/reconstruct_phase5_viewed_references.py"
        )
    )
    terminal = json.loads((retained_root / "recovery.json").read_bytes())
    if terminal["request_sha256"] != file_sha256(
        retained_root / "recovery-request.json"
    ):
        raise ValueError("reference reconstruction request changed")
    for key, identities in (
        (
            "input_bundle_set_sha256",
            tuple(
                (
                    row["input_id"],
                    retained_root / row["relative_directory"] / "input.json",
                )
                for row in request["inputs"]
            ),
        ),
        (
            "reference_result_set_sha256",
            tuple(
                (
                    row["run_id"],
                    retained_root / row["relative_directory"] / "result.json",
                )
                for row in request["runs"]
                if row["finder_id"] != "hebog"
            ),
        ),
    ):
        if verifier["_identity_set_sha256"](identities) != terminal[key]:
            raise ValueError("sealed reference product set changed")


def implementation_identities(
    candidate: dict[str, str],
    operational: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retain real native software identities, including the incumbent."""
    identities: list[dict[str, Any]] = []
    for finder, revision in (
        ("current-hebog", candidate),
        ("incumbent-hebog", INCUMBENT),
    ):
        identities.append(
            CampaignImplementationIdentity(
                identifier=finder,
                role="candidate" if finder == "current-hebog" else "reference",
                execution_configuration_sha256=revision[
                    "configuration_sha256"
                ],
                software=SoftwareIdentity(
                    name="hebog",
                    commit_sha=revision["revision"],
                    source_tree_sha256=revision["source_tree_sha256"],
                    dependency_inventory_sha256=dependency_inventory_sha256(),
                ),
            ).model_dump(mode="json")
        )
    references = {
        finder: value
        for rows in operational.values()
        for finder, value in rows.items()
    }
    for finder, value in sorted(references.items()):
        result = read_bound(value)
        runtime = result["runtime"]
        identities.append(
            CampaignImplementationIdentity(
                identifier=finder,
                role="reference",
                execution_configuration_sha256=result["configuration_sha256"],
                software=SoftwareIdentity(
                    name=runtime["name"],
                    version=runtime["version"],
                    commit_sha=runtime["source_revision"],
                    container_image_digest=runtime["container_image_digest"],
                    dependency_inventory_sha256=runtime[
                        "dependency_inventory_sha256"
                    ],
                ),
            ).model_dump(mode="json")
        )
    return identities


def build_replay_plan(  # noqa: PLR0913
    root: Path,
    *,
    evidence_root: Path,
    execution_root: Path,
    historical_root: Path,
    scratch: Path,
    output: Path,
    admission: dict[str, Any],
) -> dict[str, Any]:
    """Compose a non-executable exact plan from retained metadata only."""
    for relative, expected in EXPECTED_FILES.items():
        if file_sha256(evidence_root / relative) != expected:
            raise ValueError(f"frozen input identity changed: {relative}")
    review = json.loads((root / REVIEW).read_bytes())
    if (
        source_tree_sha256(root)
        != review["algorithm_candidate"]["source_tree_sha256"]
    ):
        raise ValueError("repaired source identity changed")
    request = json.loads((evidence_root / REQUEST).read_bytes())
    population = json.loads((root / POPULATION).read_bytes())
    inputs = selected_inputs(request, population)
    retained_root = evidence_root / REFERENCE
    verify_reference_identities(root, request, retained_root)
    if (
        repository_revision(historical_root) != INCUMBENT["execution_revision"]
        or source_tree_sha256(historical_root)
        != INCUMBENT["source_tree_sha256"]
    ):
        raise ValueError("historical incumbent checkout changed")
    reference_bindings = {
        row["run_id"]: binding(
            retained_root / row["relative_directory"] / "result.json"
        )
        for row in request["runs"]
        if row["finder_id"] != "hebog"
    }
    operational: dict[str, dict[str, Any]] = {}
    for row in request["runs"]:
        if row["mode"] == "operational":
            operational.setdefault(row["input_id"], {})[row["finder_id"]] = (
                reference_bindings[row["run_id"]]
            )
    policy, protocol = load_cumulative_policy(root)
    context = evaluation_context(root)
    tasks: list[dict[str, Any]] = []
    for row in inputs:
        input_manifest = (
            retained_root / row["relative_directory"] / "input.json"
        )
        inputs_record = json.loads(input_manifest.read_bytes())
        paths = {
            artifact["role"]: str(
                input_manifest.parent / artifact["relative_path"]
            )
            for artifact in inputs_record["artifacts"]
        }
        tasks.append(
            {
                **{
                    key: row[key]
                    for key in (
                        "input_id",
                        "lane",
                        "dataset_identifier",
                        "seed",
                        "recipe_sha256",
                    )
                },
                "root": str(execution_root),
                "configuration": review["configuration"],
                "output_directory": str(scratch / "pairs" / row["input_id"]),
                "input_manifest": binding(input_manifest),
                "captures": operational[row["input_id"]],
                "historical_task": {
                    "historical_root": str(historical_root),
                    "input_id": row["input_id"],
                    "lane": row["lane"],
                    "seed": row["seed"],
                    "dataset_identifier": row["dataset_identifier"],
                    "image_path": paths["image"],
                    "mean_path": paths["mean"],
                    "rms_path": paths["rms"],
                    "configuration_sha256": INCUMBENT["configuration_sha256"],
                    "source_tree_sha256": INCUMBENT["source_tree_sha256"],
                },
            }
        )
        if (row["dataset_identifier"], row["seed"]) not in context["recipes"]:
            raise ValueError("recipe is absent from the frozen population")
    # Selection is fixed before any changed-candidate measurement is read.
    dask_input_ids = select_dask_inputs(tasks)
    retained_paths = [*EXPECTED_FILES, REVIEW, REGISTRY]
    retained_paths.extend(
        value
        for key, value in policy.items()
        if key.endswith("_path") and isinstance(value, str)
    )
    metadata = {
        relative: binding(evidence_root / relative)
        for relative in sorted(set(retained_paths))
    }
    return {
        "schema_version": 1,
        "status": "frozen-non-executable",
        "finder_execution_started": False,
        "execution_revision": repository_revision(root),
        "execution_root": str(execution_root),
        "scratch": str(scratch),
        "output": str(output),
        "admission": admission,
        "candidate": review["algorithm_candidate"],
        "incumbent": INCUMBENT,
        "historical_root": str(historical_root),
        "implementations": implementation_identities(
            review["algorithm_candidate"], operational
        ),
        "configuration": review["configuration"],
        "metadata": metadata,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependency_inventory_sha256": dependency_inventory_sha256(),
        },
        "workers": 2,
        "candidate_serial_executions": 2400,
        "incumbent_executions": 2400,
        "pybdsf_executions": 0,
        "existing_dask_comparisons": 12,
        "dask_input_ids": dask_input_ids,
        "reference_run_count": 9600,
        "retained_references": reference_bindings,
        "bootstrap_resamples": protocol["bootstrap_resamples"],
        "bootstrap_seed": protocol["bootstrap_seed"],
        "power_rationale": (
            "Unchanged prospective population and planning assumptions; "
            "actual confidence intervals are binding. No prior uncertainty "
            "waiver transfers."
        ),
        "tasks": tasks,
    }


def verify_code_identity(plan: dict[str, Any], root: Path) -> None:
    """Require the exact immutable implementation, source and environment."""
    if (
        plan["status"] != "frozen-non-executable"
        or plan["finder_execution_started"] is not False
    ):
        raise ValueError("R6 plan is not an unopened frozen plan")
    if (
        root.resolve() != Path(plan["execution_root"]).resolve()
        or repository_revision(root) != plan["execution_revision"]
        or not Path(hebog.__file__).resolve().is_relative_to(root / "src")
    ):
        raise ValueError("R6 immutable execution checkout changed")
    if source_tree_sha256(root) != plan["candidate"]["source_tree_sha256"]:
        raise ValueError("R6 candidate science changed")
    if (
        canonical_sha256(plan["configuration"])
        != plan["candidate"]["configuration_sha256"]
    ):
        raise ValueError("R6 candidate configuration changed")
    if (
        dependency_inventory_sha256()
        != plan["runtime"]["dependency_inventory_sha256"]
        or platform.python_version() != plan["runtime"]["python"]
    ):
        raise ValueError("R6 runtime changed")


def verify_census(plan: dict[str, Any]) -> None:
    """Require every planned input, comparator and existing-Dask repeat."""
    counts = Counter(task["lane"] for task in plan["tasks"])
    if (
        counts != {"compact-blend": 800, "continuum": 1600}
        or len({task["input_id"] for task in plan["tasks"]}) != INPUT_COUNT
    ):
        raise ValueError("R6 task census changed")
    expected_counts = {
        "workers": 2,
        "candidate_serial_executions": 2400,
        "incumbent_executions": 2400,
        "pybdsf_executions": 0,
        "existing_dask_comparisons": 12,
        "reference_run_count": 9600,
        "bootstrap_resamples": 50000,
        "bootstrap_seed": 20260810,
    }
    if any(
        type(plan[key]) is not int or plan[key] != value
        for key, value in expected_counts.items()
    ):
        raise ValueError("R6 execution shape changed")
    if (
        len(plan["retained_references"]) != REFERENCE_COUNT
        or len(set(plan["dask_input_ids"])) != DASK_COUNT
        or not set(plan["dask_input_ids"])
        <= {task["input_id"] for task in plan["tasks"]}
    ):
        raise ValueError("R6 reference or Dask census changed")
    if plan["dask_input_ids"] != select_dask_inputs(plan["tasks"]):
        raise ValueError("R6 Dask population selection changed")


def verify_historical_producer(plan: dict[str, Any], root: Path) -> None:
    """Probe historical imports and frozen producer hashes without a run."""
    historical = Path(plan["historical_root"])
    if (
        repository_revision(historical) != INCUMBENT["execution_revision"]
        or source_tree_sha256(historical) != INCUMBENT["source_tree_sha256"]
    ):
        raise ValueError("R6 historical incumbent checkout changed")
    helper = (
        root
        / "scripts/validation"
        / "reconstruct_phase5_prospective_paired_incumbent.py"
    )
    subprocess.run(
        (
            sys.executable,
            "-c",
            "import runpy,sys; from pathlib import Path; "
            "worker=runpy.run_path(sys.argv[1]); "
            "worker['_historical_wrapper'](Path(sys.argv[2]))",
            str(helper),
            str(historical),
        ),
        cwd=historical,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(historical / "src"),
        },
        check=True,
        capture_output=True,
    )


def verify_task_metadata(plan: dict[str, Any], root: Path) -> None:
    """Check every execution task against its frozen analytic recipe."""
    context = evaluation_context(root)
    retained = list(plan["retained_references"].values())
    for task in plan["tasks"]:
        recipe_key = task["dataset_identifier"], task["seed"]
        if (
            recipe_key not in context["recipes"]
            or recipe_sha256(context["recipes"][recipe_key])
            != task["recipe_sha256"]
        ):
            raise ValueError("R6 task recipe changed")
        if (
            task["root"] != plan["execution_root"]
            or task["configuration"] != plan["configuration"]
            or task["output_directory"]
            != str(Path(plan["scratch"]) / "pairs" / task["input_id"])
        ):
            raise ValueError(
                "R6 task execution paths or configuration changed"
            )
        record = read_bound(task["input_manifest"])
        if any(
            record[key] != task[key]
            for key in ("dataset_identifier", "seed", "recipe_sha256")
        ):
            raise ValueError("R6 task input identity changed")
        finders = {"released-pybdsf", "pinned-pybdsf-master"}
        if task["lane"] == "compact-blend":
            finders.add("aegean")
        if set(task["captures"]) != finders or any(
            value not in retained for value in task["captures"].values()
        ):
            raise ValueError("R6 task retained finder census changed")


def verify_replay_plan(plan: dict[str, Any], root: Path) -> None:
    """Exhaustively verify code, identity, census and raw files, no writes."""
    verify_code_identity(plan, root)
    verify_census(plan)
    verify_task_metadata(plan, root)
    verify_historical_producer(plan, root)
    for value in plan["metadata"].values():
        if binding(Path(value["path"])) != value:
            raise ValueError("R6 retained metadata changed")
    if any(
        Path(plan[key]).exists() or Path(plan[key]).is_symlink()
        for key in ("scratch", "output")
    ):
        raise FileExistsError("R6 output or consumed scratch already exists")
    for value in plan["retained_references"].values():
        native_artifacts(Path(value["path"]), value["sha256"])
    for task in plan["tasks"]:
        native_artifacts(
            Path(task["input_manifest"]["path"]),
            task["input_manifest"]["sha256"],
        )
    if (
        shutil.disk_usage(Path(plan["scratch"]).parent).free
        < plan["admission"]["required_free_bytes"]
    ):
        raise ValueError("R6 disk admission failed")
