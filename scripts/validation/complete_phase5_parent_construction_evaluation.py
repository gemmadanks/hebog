#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Complete parent-construction evaluation from preserved products."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import file_sha256
from hebog.validation.parent_construction_association_evaluation import (
    install_parent_construction_association_evaluation,
)

_ROOT = Path(__file__).parents[2]
_PARENT_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_hierarchy_"
    "parent_construction_cumulative_regressions.py"
)
_RECONSTRUCTION_PROGRAM = (
    _ROOT / "scripts/validation/reconstruct_phase5_parent_construction_"
    "associations.py"
)
_EVALUATION_OVERLAY = (
    _ROOT
    / "src/hebog/validation/parent_construction_association_evaluation.py"
)
_FAILURE = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-provenance-failure.json"
)
_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-repair-pre-review.json"
)
_REPAIR_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-repair-implementation-decision.json"
)
_RECONSTRUCTION_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-reconstruction-review.json"
)
_RECONSTRUCTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-reconstruction-execution-"
    "decision.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-completion-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-completion-execution-decision.json"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_ASSOCIATION_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "parent-construction-association-provenance-reconstruction"
)
_CLOSED_BASELINE = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-public-finder-"
    "source-hierarchy-parent-construction.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-hierarchy-"
    "parent-construction-5f2b098"
)

_CANDIDATE_REVISION = "5f2b09880dc10feb6ffaec50ffcf3c807a093416"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "a7ef1887bcaeb15abf48722d45de33f81d8be65d58fde19861bf0ece90b4dba8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "88634678d7b24c9d9d47a5ba714c66fcc627c8a201b9639b133e326cd1c72484"
)
_CANDIDATE_PRODUCT_SET_SHA256 = (
    "b81cb3d47d7db5ac45c66893445bd5d25711af88372566bbe979a6bce9a0fc87"
)
_PARENT_WRAPPER_SHA256 = (
    "053fc6479d75a9f11e97cc2ec6f7de41610c5c03083bd81ce01ca47ef104c8d7"
)
_RECONSTRUCTION_PROGRAM_SHA256 = (
    "e8dd80cbc8d84fcaa8d3fb2703466c701dd5ad5dfc01ef64eaa43426b43c5f24"
)
_EVALUATION_OVERLAY_SHA256 = (
    "74d16cc49f65bf5a353acc67a830dd2d175b8be2635062cca64581cfaa966962"
)
_FAILURE_SHA256 = (
    "1a391c240a957f4a41684ce2d6c19cef9d6a210239592aef460e00e8e476355a"
)
_REPAIR_PRE_REVIEW_SHA256 = (
    "bfc1e594bd59b55a1fca18ac19e5d903685fe006943652fbe3e438630e12c6af"
)
_REPAIR_IMPLEMENTATION_DECISION_SHA256 = (
    "d15f87e47b33326c529b89ed7cad09530fbfafe5ed64d239cd0e13062bd0ceec"
)
_RECONSTRUCTION_REVIEW_SHA256 = (
    "691eaf8f35f5ff1688c52af6d448e3ba4df704529f6f50072fa6924903a59be4"
)
_RECONSTRUCTION_DECISION_SHA256 = (
    "34efd510166ca9922612e30895969159ff801c3d800f06ccafc463356679c596"
)
_RECONSTRUCTION_RECOVERY_SHA256 = (
    "78d43370101b39a9902f15a84209559b3759a893735fc84418fc34e30c84f2af"
)
_ASSOCIATION_PRODUCT_SET_SHA256 = (
    "e1f16373f47119c71d64e3aa90639403dd1e978d84e68f4fd507e20527a27e90"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_INPUT_COUNT = 2400
_CONTINUUM_COUNT = 1600
_REFERENCE_RUN_COUNT = 9600
_WORKERS = 2
_PROHIBITED_AUTHORIZATIONS = (
    "campaign_execution_authorized",
    "candidate_execution_authorized",
    "cumulative_replay_rerun_authorized",
    "cutover_authorized",
    "fresh_qualification_authorized",
    "optimization_authorized",
    "release_authorized",
    "rescoring_authorized",
    "tuning_authorized",
    "viewed_sdc1_hydra_execution_authorized",
)


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite deterministic evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _json_object(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object without accepting another shape."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _git_revision() -> str:
    """Return the clean completion checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("evaluation completion requires a clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _load_parent_wrapper() -> dict[str, Any]:
    """Load the exact parent wrapper without executing its entry point."""
    if file_sha256(_PARENT_WRAPPER) != _PARENT_WRAPPER_SHA256:
        raise ValueError("parent-construction wrapper changed")
    return runpy.run_path(str(_PARENT_WRAPPER))


def _load_reconstruction_program() -> dict[str, Any]:
    """Load the exact reconstruction verifier without executing it."""
    if file_sha256(_RECONSTRUCTION_PROGRAM) != _RECONSTRUCTION_PROGRAM_SHA256:
        raise ValueError("association reconstruction program changed")
    return runpy.run_path(str(_RECONSTRUCTION_PROGRAM))


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require only the preserved products and original output namespace."""
    expected = {
        "campaign": None,
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "association_reconstruction": _ASSOCIATION_RECONSTRUCTION,
        "closed_component_baseline_ledger": _CLOSED_BASELINE,
        "output": _OUTPUT,
        "scratch": _SCRATCH,
        "workers": _WORKERS,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(f"evaluation completion {field} changed")


def _verify_association_reconstruction(
    terminal: Path,
    continuum_ids: tuple[str, ...],
    *,
    scratch: Path,
    expected_count: int = _CONTINUUM_COUNT,
) -> str:
    """Verify every sealed sidecar and its preserved-product binding."""
    if len(continuum_ids) != expected_count or len(set(continuum_ids)) != len(
        continuum_ids
    ):
        raise ValueError("association reconstruction population changed")
    recovery_path = terminal / "recovery.json"
    progress_path = terminal / "progress.log"
    associations = terminal / "associations"
    if (
        not terminal.is_dir()
        or not associations.is_dir()
        or not progress_path.is_file()
        or file_sha256(recovery_path) != _RECONSTRUCTION_RECOVERY_SHA256
        or {item.name for item in terminal.iterdir()}
        != {"associations", "progress.log", "recovery.json"}
    ):
        raise ValueError("association reconstruction terminal changed")
    recovery = _json_object(recovery_path, label="reconstruction recovery")
    if recovery_path.read_bytes() != _canonical_json_bytes(recovery):
        raise ValueError(
            "association reconstruction recovery is not canonical"
        )
    expected_recovery = {
        "association_count": expected_count,
        "association_product_set_sha256": _ASSOCIATION_PRODUCT_SET_SHA256,
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_product_set_sha256": _CANDIDATE_PRODUCT_SET_SHA256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "decision_sha256": _RECONSTRUCTION_DECISION_SHA256,
        "failure_sha256": _FAILURE_SHA256,
        "implementation_decision_sha256": (
            _REPAIR_IMPLEMENTATION_DECISION_SHA256
        ),
        "parent_wrapper_sha256": _PARENT_WRAPPER_SHA256,
        "pre_review_sha256": _REPAIR_PRE_REVIEW_SHA256,
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "reconstruction_program_sha256": (_RECONSTRUCTION_PROGRAM_SHA256),
        "schema_version": 1,
        "status": "sealed",
    }
    if recovery != expected_recovery:
        raise ValueError("association reconstruction provenance changed")
    expected_ids = set(continuum_ids)
    if {item.name for item in associations.iterdir()} != expected_ids:
        raise ValueError("association reconstruction population changed")
    lines = progress_path.read_text(encoding="utf-8").splitlines()
    if len(lines) != expected_count or set(lines) != expected_ids:
        raise ValueError("association reconstruction progress changed")

    reconstruction = _load_reconstruction_program()
    markers: list[dict[str, object]] = []
    for input_id in continuum_ids:
        directory = associations / input_id
        preserved_complete_sha256 = file_sha256(
            scratch / "products" / input_id / "complete.json"
        )
        if not reconstruction["_verified_association_marker"](
            directory,
            input_id=input_id,
            preserved_complete_sha256=preserved_complete_sha256,
        ):
            raise ValueError("association reconstruction shard changed")
        markers.append(
            _json_object(
                directory / "complete.json",
                label="association complete marker",
            )
        )
    identity = canonical_sha256(markers)
    if identity != _ASSOCIATION_PRODUCT_SET_SHA256:
        raise ValueError("association reconstruction product set changed")
    return identity


def verify_evaluation_completion_composition(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Verify all preserved evidence without compiling science."""
    _require_exact_invocation(arguments)
    if arguments.output.exists():
        raise ValueError("evaluation completion output already exists")
    for path, expected, label in (
        (_FAILURE, _FAILURE_SHA256, "failure"),
        (_REPAIR_PRE_REVIEW, _REPAIR_PRE_REVIEW_SHA256, "repair review"),
        (
            _REPAIR_IMPLEMENTATION_DECISION,
            _REPAIR_IMPLEMENTATION_DECISION_SHA256,
            "repair decision",
        ),
        (
            _RECONSTRUCTION_REVIEW,
            _RECONSTRUCTION_REVIEW_SHA256,
            "reconstruction review",
        ),
        (
            _RECONSTRUCTION_DECISION,
            _RECONSTRUCTION_DECISION_SHA256,
            "reconstruction decision",
        ),
        (
            _EVALUATION_OVERLAY,
            _EVALUATION_OVERLAY_SHA256,
            "evaluation overlay",
        ),
        (
            arguments.reference_reconstruction / "recovery.json",
            _REFERENCE_RECONSTRUCTION_SHA256,
            "reference reconstruction",
        ),
        (
            arguments.closed_component_baseline_ledger,
            _CLOSED_BASELINE_SHA256,
            "closed baseline",
        ),
    ):
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"evaluation completion {label} changed")

    parent = _load_parent_wrapper()
    verified = parent["_verify_reference_reconstruction"](arguments)
    expected_inputs = tuple(
        (item.input_id, item.lane) for item in verified.request.inputs
    )
    reconstruction = _load_reconstruction_program()
    product_set_sha256 = reconstruction["_verify_preserved_products"](
        arguments.scratch,
        expected_inputs,
    )
    continuum_ids = tuple(
        input_id for input_id, lane in expected_inputs if lane == "continuum"
    )
    association_product_set_sha256 = _verify_association_reconstruction(
        arguments.association_reconstruction,
        continuum_ids,
        scratch=arguments.scratch,
    )
    if (
        len(verified.inputs) != _INPUT_COUNT
        or len(verified.runs) != _REFERENCE_RUN_COUNT
        or product_set_sha256 != _CANDIDATE_PRODUCT_SET_SHA256
        or verified.reference_reconstruction_sha256
        != _REFERENCE_RECONSTRUCTION_SHA256
    ):
        raise ValueError("evaluation completion evidence changed")
    _, _, frozen = parent["_load_source_association_composition"]()
    parent["_install_parent_construction_static_seams"](frozen)
    if not callable(frozen.get("main")) or not callable(
        frozen.get("_install_prospective_compiler")
    ):
        raise ValueError("evaluation completion composition changed")
    return {
        "association_product_set_sha256": (association_product_set_sha256),
        "association_reconstruction_recovery_sha256": (
            _RECONSTRUCTION_RECOVERY_SHA256
        ),
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_execution_started": False,
        "candidate_product_count": len(expected_inputs),
        "candidate_product_set_sha256": product_set_sha256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "compilation_started": False,
        "completion_program_sha256": file_sha256(Path(__file__)),
        "evaluation_overlay_sha256": _EVALUATION_OVERLAY_SHA256,
        "evaluation_started": False,
        "output_absent": True,
        "parent_wrapper_sha256": _PARENT_WRAPPER_SHA256,
        "reconstruction_decision_sha256": (_RECONSTRUCTION_DECISION_SHA256),
        "reconstruction_program_sha256": (_RECONSTRUCTION_PROGRAM_SHA256),
        "reconstruction_review_sha256": _RECONSTRUCTION_REVIEW_SHA256,
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "reference_run_count": len(verified.runs),
        "status": "pass",
    }


def _validate_execution_decision(
    decision: Mapping[str, object],
    review: Mapping[str, object],
    verified: Mapping[str, object],
) -> None:
    """Require one exact evaluation approval and no broader authority."""
    if (
        decision.get("status")
        != "reviewed-before-parent-construction-evaluation-completion"
        or decision.get("existing_product_completion_authorized") is not True
        or decision.get("compilation_authorized") is not True
        or decision.get("evaluation_authorized") is not True
        or decision.get("candidate_execution_authorized") is not False
    ):
        raise ValueError("evaluation completion is not authorized")
    prohibited = decision.get("prohibited_authorizations")
    if (
        not isinstance(prohibited, dict)
        or set(prohibited) != set(_PROHIBITED_AUTHORIZATIONS)
        or any(prohibited.values())
    ):
        raise ValueError("evaluation completion authority changed")
    identity = decision.get("identity_review")
    if not isinstance(identity, dict) or identity != {
        "path": str(_IDENTITY_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_IDENTITY_REVIEW),
    }:
        raise ValueError("evaluation completion identity review changed")
    if (
        review.get("status")
        != "reviewed-before-parent-construction-evaluation-completion"
        or review.get("compilation_authorized") is not False
        or review.get("evaluation_authorized") is not False
        or review.get("candidate_execution_authorized") is not False
        or review.get("verified_composition") != dict(verified)
    ):
        raise ValueError("evaluation completion composition changed")
    for field in (
        "association_product_set_sha256",
        "association_reconstruction_recovery_sha256",
        "candidate_product_set_sha256",
        "completion_program_sha256",
        "evaluation_overlay_sha256",
        "parent_wrapper_sha256",
    ):
        if decision.get(field) != verified[field]:
            raise ValueError(f"evaluation completion {field} changed")


def _install_completion_only(
    frozen: dict[str, Any],
    *,
    provenance: Mapping[str, object],
    expected_count: int = _INPUT_COUNT,
    scratch: Path = _SCRATCH,
) -> None:
    """Forbid candidate submission and admit only complete shards."""

    def candidate_source_tree(_root: Path) -> str:
        return _CANDIDATE_SOURCE_TREE_SHA256

    frozen["source_tree_sha256"] = candidate_source_tree
    completed = frozen["_completed_candidate"]

    def verify_tasks(
        tasks: tuple[dict[str, object], ...],
        *,
        workers: int,
        progress_path: Path,
    ) -> None:
        if (
            workers != _WORKERS
            or len(tasks) != expected_count
            or progress_path != scratch / "progress.log"
        ):
            raise ValueError("evaluation completion task identity changed")
        for task in tasks:
            if not completed(
                Path(cast(str, task["output_directory"])),
                input_id=cast(str, task["input_id"]),
                configuration_sha256=cast(str, task["configuration_sha256"]),
                source_sha256=cast(str, task["source_tree_sha256"]),
            ):
                raise ValueError("candidate product identity changed")

    def candidate_execution_forbidden(_task: dict[str, object]) -> str:
        raise RuntimeError("evaluation completion forbids candidate execution")

    frozen["_run_candidate_tasks"] = verify_tasks
    frozen["_generate_candidate_product"] = candidate_execution_forbidden
    original_serializer = frozen["_canonical_json_bytes"]

    def serialize(value: object) -> bytes:
        document = value
        if isinstance(value, dict) and value.get("ledger_id") == (
            "phase-5-cumulative-regression-ledger"
        ):
            document = {
                **value,
                "evaluation_completion_provenance": dict(provenance),
            }
        return cast(bytes, original_serializer(document))

    frozen["_canonical_json_bytes"] = serialize


def _install_evaluation_compiler(frozen: dict[str, Any]) -> None:
    """Layer the sidecar adapter after all frozen compiler seams."""
    prospective_installer = frozen.get("_install_prospective_compiler")
    if not callable(prospective_installer) or not hasattr(
        prospective_installer, "__globals__"
    ):
        raise ValueError("evaluation completion compiler seam changed")
    installer_globals = prospective_installer.__globals__
    original = installer_globals.get("install_recovery_compiler_seams")
    if not callable(original):
        raise ValueError("evaluation completion compiler seam changed")

    def install(
        compiler_globals: dict[str, Any],
        *,
        expected_candidate_configuration_sha256: str,
    ) -> None:
        original(
            compiler_globals,
            expected_candidate_configuration_sha256=(
                expected_candidate_configuration_sha256
            ),
        )

        def association_path(run: Any) -> Path:
            return (
                _ASSOCIATION_RECONSTRUCTION
                / "associations"
                / cast(str, run.request.input_id)
                / "source_association.json"
            )

        install_parent_construction_association_evaluation(
            compiler_globals,
            association_path=association_path,
        )

    installer_globals["install_recovery_compiler_seams"] = install
    frozen["install_recovery_compiler_seams"] = install


def run_authorized_completion(arguments: argparse.Namespace) -> None:
    """Compile and evaluate once without executing candidate products."""
    _git_revision()
    verified_composition = verify_evaluation_completion_composition(arguments)
    review = _json_object(_IDENTITY_REVIEW, label="completion identity review")
    decision = _json_object(
        _EXECUTION_DECISION, label="completion execution decision"
    )
    _validate_execution_decision(decision, review, verified_composition)
    parent = _load_parent_wrapper()
    verified_reference = parent["_verify_reference_reconstruction"](arguments)
    source_association, current, frozen = parent[
        "_load_source_association_composition"
    ]()
    provenance = {
        **verified_composition,
        "identity_review_sha256": file_sha256(_IDENTITY_REVIEW),
        "execution_decision_sha256": file_sha256(_EXECUTION_DECISION),
        "evaluation_completion_revision": _git_revision(),
    }
    source_association["_install_source_association_composition"](
        current,
        frozen,
        provenance,
        verified_reference=verified_reference,
    )
    parent["_install_parent_construction_static_seams"](frozen)
    _install_evaluation_compiler(frozen)
    _install_completion_only(frozen, provenance=provenance)
    frozen["_parse_args"] = lambda: arguments
    frozen["main"]()


def _parse_args() -> argparse.Namespace:
    """Parse the one fixed existing-product completion namespace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.campaign = None
    arguments.reference_reconstruction = _REFERENCE_RECONSTRUCTION
    arguments.association_reconstruction = _ASSOCIATION_RECONSTRUCTION
    arguments.closed_component_baseline_ledger = _CLOSED_BASELINE
    arguments.output = _OUTPUT
    arguments.scratch = _SCRATCH
    arguments.workers = _WORKERS
    return arguments


def main() -> None:
    """Verify now or complete only after a future exact approval."""
    arguments = _parse_args()
    if arguments.verify_only:
        print(
            json.dumps(
                verify_evaluation_completion_composition(arguments),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_authorized_completion(arguments)


if __name__ == "__main__":
    main()
