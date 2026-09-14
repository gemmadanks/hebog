#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Complete evaluation from the preserved measurement-repair products."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import file_sha256
from hebog.validation.source_association_evaluation_repair import (
    install_source_association_evaluation_repair,
)

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_source_association_measurement_repair_"
    "cumulative_regressions.py"
)
_FAILURE = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-execution-failure.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-evaluation-repair-pre-review.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-evaluation-repair-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-evaluation-repair-execution-decision.json"
)
_EVALUATION_REPAIR_ADAPTER = (
    _ROOT / "src/hebog/validation/source_association_evaluation_repair.py"
)
_FAILED_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-execution-decision.json"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_CLOSED_BASELINE = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-public-finder-"
    "source-association-measurement-repair.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-association-"
    "measurement-repair-6184a32"
)
_CANDIDATE_REVISION = "6184a32648eee637f0aca03ab2ec0249bd0510f0"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "517d56e19a5d58eb386d96bdb181d36afb574ad018222f870cc8434c398044ff"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
)
_CONSUMED_WRAPPER_SHA256 = (
    "79e8252cd06cca4959b794af231b6078c80a34f996ff5184ed7c8f4994029084"
)
_FAILED_EXECUTION_DECISION_SHA256 = (
    "5ddc524a4014cadcf4f7df9745dedc963589b6ea7462c686a6b0adcb412a323b"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_INPUT_COUNT = 2400
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
    """Return the clean repair checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("evaluation repair requires a clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=_ROOT,
        text=True,
    ).strip()


def _verified_artifacts(
    directory: Path,
    marker: Mapping[str, object],
    *,
    lane: str,
) -> None:
    """Hash every declared shard artifact and reject extras or role drift."""
    artifacts = marker.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("candidate product artifacts are malformed")
    expected_roles = (
        {
            "segment-catalogue-json",
            "segment-labels-fits",
            "segment-mask-fits",
        }
        if lane == "continuum"
        else {"compact-catalogue-json"}
    )
    roles: set[str] = set()
    names = {"complete.json"}
    for value in artifacts:
        if not isinstance(value, dict):
            raise ValueError("candidate product artifacts are malformed")
        role = value.get("role")
        relative_path = value.get("relative_path")
        if (
            not isinstance(role, str)
            or not isinstance(relative_path, str)
            or Path(relative_path).name != relative_path
        ):
            raise ValueError("candidate product artifacts are malformed")
        path = directory / relative_path
        if (
            not path.is_file()
            or value.get("byte_count") != path.stat().st_size
            or value.get("sha256") != file_sha256(path)
        ):
            raise ValueError("candidate product artifact identity changed")
        roles.add(role)
        names.add(relative_path)
    actual_names = {item.name for item in directory.iterdir()}
    if roles != expected_roles or actual_names != names:
        raise ValueError("candidate product artifact set changed")


def verify_existing_candidate_products(
    scratch: Path,
    expected_inputs: Sequence[tuple[str, str]],
    *,
    expected_count: int = _INPUT_COUNT,
) -> str:
    """Verify every complete shard without opening scientific contents."""
    if len(expected_inputs) != expected_count or len(
        {item[0] for item in expected_inputs}
    ) != len(expected_inputs):
        raise ValueError("candidate product population changed")
    products = scratch / "products"
    progress = scratch / "progress.log"
    if (
        not products.is_dir()
        or not progress.is_file()
        or {item.name for item in scratch.iterdir()}
        != {"products", "progress.log"}
    ):
        raise ValueError("candidate scratch layout changed")
    expected_ids = {item[0] for item in expected_inputs}
    if {item.name for item in products.iterdir()} != expected_ids:
        raise ValueError("candidate product population changed")

    markers: list[dict[str, object]] = []
    for input_id, lane in expected_inputs:
        directory = products / input_id
        marker_path = directory / "complete.json"
        marker = _json_object(marker_path, label="candidate complete marker")
        if (
            marker.get("schema_version") != 1
            or marker.get("input_id") != input_id
            or marker.get("configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
            or marker.get("source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
        ):
            raise ValueError("candidate product identity changed")
        if marker_path.read_bytes() != _canonical_json_bytes(marker):
            raise ValueError("candidate complete marker is not canonical")
        _verified_artifacts(directory, marker, lane=lane)
        markers.append(marker)

    lines = progress.read_text(encoding="utf-8").splitlines()
    completed_inputs = {
        line.rsplit(" input=", maxsplit=1)[1]
        for line in lines
        if " input=" in line
    }
    if len(lines) != expected_count or completed_inputs != expected_ids:
        raise ValueError("candidate progress record is incomplete")
    return canonical_sha256(markers)


def _load_consumed_wrapper() -> dict[str, Any]:
    """Load the exact failed wrapper without running its main entry point."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed measurement-repair wrapper changed")
    return runpy.run_path(str(_CONSUMED_WRAPPER))


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require the preserved scratch and original write-once namespace."""
    expected = {
        "campaign": None,
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "closed_component_baseline_ledger": _CLOSED_BASELINE,
        "output": _OUTPUT,
        "scratch": _SCRATCH,
        "workers": _WORKERS,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(f"evaluation repair {field} identity changed")


def verify_evaluation_repair_composition(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Verify references and preserved products without compiling science."""
    _require_exact_invocation(arguments)
    if arguments.output.exists():
        raise ValueError("evaluation repair output already exists")
    if (
        file_sha256(_FAILED_EXECUTION_DECISION)
        != _FAILED_EXECUTION_DECISION_SHA256
        or file_sha256(arguments.closed_component_baseline_ledger)
        != _CLOSED_BASELINE_SHA256
    ):
        raise ValueError("failed replay evidence identity changed")
    failure = _json_object(_FAILURE, label="execution failure")
    pre_review = _json_object(_PRE_REVIEW, label="repair pre-review")
    if failure.get("status") != (
        "failed-after-candidate-products-before-atomic-ledger"
    ) or pre_review.get("status") != (
        "implementation-authorized-by-explicit-user-fix-request"
    ):
        raise ValueError("evaluation repair boundary changed")
    consumed = _load_consumed_wrapper()
    verified = consumed["_verify_reference_reconstruction"](arguments)
    expected_inputs = tuple(
        (item.input_id, item.lane) for item in verified.request.inputs
    )
    product_set_sha256 = verify_existing_candidate_products(
        arguments.scratch,
        expected_inputs,
    )
    if (
        len(verified.inputs) != _INPUT_COUNT
        or len(verified.runs) != _REFERENCE_RUN_COUNT
        or verified.reference_reconstruction_sha256
        != _REFERENCE_RECONSTRUCTION_SHA256
    ):
        raise ValueError("reconstructed reference identity changed")
    return {
        "status": "pass",
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_product_count": len(expected_inputs),
        "candidate_product_set_sha256": product_set_sha256,
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "reference_run_count": len(verified.runs),
        "failed_execution_decision_sha256": (
            _FAILED_EXECUTION_DECISION_SHA256
        ),
        "failure_sha256": file_sha256(_FAILURE),
        "pre_review_sha256": file_sha256(_PRE_REVIEW),
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "completion_program_sha256": file_sha256(Path(__file__)),
        "source_association_program_sha256": file_sha256(
            _ROOT / "src/hebog/algorithms/source_association.py"
        ),
        "historical_support_matcher_sha256": file_sha256(
            _ROOT / "src/hebog/validation/external_comparison.py"
        ),
        "historical_successor_compiler_sha256": file_sha256(
            _ROOT / "src/hebog/validation/external_successor_compiler.py"
        ),
        "evaluation_repair_adapter_sha256": file_sha256(
            _EVALUATION_REPAIR_ADAPTER
        ),
        "output_absent": True,
        "candidate_execution_started": False,
        "compilation_started": False,
        "evaluation_started": False,
    }


def _validate_execution_decision(
    decision: Mapping[str, object],
    review: Mapping[str, object],
    verified: Mapping[str, object],
) -> None:
    """Require one exact completion approval and no broader authority."""
    if (
        decision.get("status")
        != "reviewed-before-measurement-repair-evaluation-completion"
        or decision.get("compilation_resume_authorized") is not True
        or decision.get("evaluation_authorized") is not True
    ):
        raise ValueError("evaluation repair completion is not authorized")
    prohibited = decision.get("prohibited_authorizations")
    if (
        not isinstance(prohibited, dict)
        or set(prohibited) != set(_PROHIBITED_AUTHORIZATIONS)
        or any(prohibited.values())
    ):
        raise ValueError("evaluation repair authorization boundary changed")
    identity = decision.get("identity_review")
    if not isinstance(identity, dict) or identity != {
        "path": str(_IDENTITY_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_IDENTITY_REVIEW),
    }:
        raise ValueError("evaluation repair identity review changed")
    if (
        review.get("status")
        != "reviewed-before-measurement-repair-evaluation-completion"
        or review.get("compilation_resume_authorized") is not False
        or review.get("candidate_execution_authorized") is not False
        or review.get("verified_composition") != dict(verified)
    ):
        raise ValueError("evaluation repair verified composition changed")
    for field in (
        "candidate_product_set_sha256",
        "completion_program_sha256",
        "source_association_program_sha256",
        "historical_support_matcher_sha256",
        "historical_successor_compiler_sha256",
        "evaluation_repair_adapter_sha256",
    ):
        if decision.get(field) != verified[field]:
            raise ValueError(f"evaluation repair {field} changed")


def _install_completion_only(
    frozen: dict[str, Any],
    *,
    provenance: Mapping[str, object],
    expected_count: int = _INPUT_COUNT,
    scratch: Path = _SCRATCH,
) -> None:
    """Forbid candidate submission and admit only verified complete shards."""

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
            raise ValueError("evaluation repair task identity changed")
        for task in tasks:
            if not completed(
                Path(cast(str, task["output_directory"])),
                input_id=cast(str, task["input_id"]),
                configuration_sha256=cast(str, task["configuration_sha256"]),
                source_sha256=cast(str, task["source_tree_sha256"]),
            ):
                raise ValueError("candidate product identity changed")

    def candidate_execution_forbidden(_task: dict[str, object]) -> str:
        raise RuntimeError("evaluation repair forbids candidate execution")

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
                "evaluation_repair_provenance": dict(provenance),
            }
        return cast(bytes, original_serializer(document))

    frozen["_canonical_json_bytes"] = serialize


def _install_evaluation_compiler_repair(frozen: dict[str, Any]) -> None:
    """Layer the new adapter after the frozen recovery compiler seams."""
    prospective_installer = frozen.get("_install_prospective_compiler")
    if not callable(prospective_installer) or not hasattr(
        prospective_installer,
        "__globals__",
    ):
        raise ValueError("evaluation repair compiler seam changed")
    installer_globals = prospective_installer.__globals__
    original = installer_globals.get("install_recovery_compiler_seams")
    if not callable(original):
        raise ValueError("evaluation repair compiler seam changed")

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
        install_source_association_evaluation_repair(compiler_globals)

    installer_globals["install_recovery_compiler_seams"] = install
    frozen["install_recovery_compiler_seams"] = install


def run_authorized_completion(arguments: argparse.Namespace) -> None:
    """Compile and evaluate once without executing any candidate product."""
    _git_revision()
    verified_composition = verify_evaluation_repair_composition(arguments)
    review = _json_object(_IDENTITY_REVIEW, label="repair identity review")
    decision = _json_object(
        _EXECUTION_DECISION,
        label="repair execution decision",
    )
    _validate_execution_decision(decision, review, verified_composition)
    consumed = _load_consumed_wrapper()
    verified_reference = consumed["_verify_reference_reconstruction"](
        arguments
    )
    source_association = consumed["_load_consumed_wrapper"]()
    current = cast(
        dict[str, Any], source_association["_load_current_wrapper"]()
    )
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    provenance = {
        **verified_composition,
        "identity_review_sha256": file_sha256(_IDENTITY_REVIEW),
        "execution_decision_sha256": file_sha256(_EXECUTION_DECISION),
        "repair_execution_revision": _git_revision(),
    }
    consumed["_install_measurement_repair_composition"](
        source_association,
        current,
        frozen,
        provenance,
        verified_reference=verified_reference,
    )
    _install_evaluation_compiler_repair(frozen)
    _install_completion_only(frozen, provenance=provenance)
    frozen["_parse_args"] = lambda: arguments
    frozen["main"]()


def _parse_args() -> argparse.Namespace:
    """Parse the one fixed existing-product completion namespace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-reconstruction",
        type=Path,
        default=_REFERENCE_RECONSTRUCTION,
    )
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--scratch", type=Path, default=_SCRATCH)
    parser.add_argument(
        "--closed-component-baseline-ledger",
        type=Path,
        default=_CLOSED_BASELINE,
    )
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.workers = _WORKERS
    arguments.campaign = None
    return arguments


def main() -> None:
    """Run only after an exact evaluation-repair approval exists."""
    arguments = _parse_args()
    if arguments.verify_only:
        print(
            json.dumps(
                verify_evaluation_repair_composition(arguments),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_authorized_completion(arguments)


if __name__ == "__main__":
    main()
