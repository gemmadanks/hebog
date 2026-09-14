#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify or run only the frozen source-parent cumulative replay."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import (
    ExternalRuntimeIdentity,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.public_finder_correction import (
    build_public_finder_source_reconstruction_continuum_products,
    public_finder_source_hierarchy_parent_construction_configuration,
)

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_"
    "reconstruction_cumulative_regressions.py"
)
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_CORRECTION_CONTRACT = (
    _ROOT / "config/contracts/phase-5-public-finder-correction.json"
)
_SOURCE_RECONSTRUCTION_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "pre-review.json"
)
_SOURCE_RECONSTRUCTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "implementation-decision.json"
)
_ROOT_CAUSE_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "root-cause-pre-review.json"
)
_ROOT_CAUSE_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "root-cause-repair-implementation-decision.json"
)
_PARENT_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-pre-review.json"
)
_PARENT_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_ORIGINAL_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-review.json"
)
_ORIGINAL_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-execution-decision.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-repair-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-repair-execution-decision.json"
)
_REPAIR_FAILURE = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-execution-failure.json"
)
_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-repair-pre-review.json"
)
_REPAIR_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-cumulative-replay-repair-implementation-decision.json"
)
_MULTISCALE_PROGRAM = _ROOT / "src/hebog/algorithms/multiscale_association.py"
_HIERARCHY_PROGRAM = _ROOT / "src/hebog/algorithms/source_association.py"
_SUPPORT_PROGRAM = _ROOT / "src/hebog/algorithms/extended_measurement.py"
_MEASUREMENT_PROGRAM = _ROOT / "src/hebog/validation/products.py"
_CANDIDATE_PROGRAM = _ROOT / "src/hebog/validation/public_finder_correction.py"
_EVALUATOR_PROGRAM = (
    _ROOT / "src/hebog/validation/source_association_evaluation_repair.py"
)

_CANDIDATE_REVISION = "5f2b09880dc10feb6ffaec50ffcf3c807a093416"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "a7ef1887bcaeb15abf48722d45de33f81d8be65d58fde19861bf0ece90b4dba8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "88634678d7b24c9d9d47a5ba714c66fcc627c8a201b9639b133e326cd1c72484"
)
_CONSUMED_WRAPPER_SHA256 = (
    "3ff495e373c366be37532cccb4a600fab8423137caad45e246dde55698d67413"
)
_SOURCE_RECONSTRUCTION_PRE_REVIEW_SHA256 = (
    "528f18a661bb2391018c458a29aace2757762e58107650e6ae01d05adc85347f"
)
_SOURCE_RECONSTRUCTION_DECISION_SHA256 = (
    "634ae2c753457f8e6c4b0181d6daa252b5a522c31057755ef4b765fec7972ab6"
)
_ROOT_CAUSE_PRE_REVIEW_SHA256 = (
    "fe9ca88d455720c5d375812875c3067e98ecc3e1ee05ead71d1c3dd0b568f979"
)
_ROOT_CAUSE_DECISION_SHA256 = (
    "8296c4ce30b8d28790e1c45b43582df1ba58737d5d7b3a7b29a5fb2766ad897b"
)
_PARENT_PRE_REVIEW_SHA256 = (
    "77669f1288287ca7ef5981a59de0ba4585500a504af5fba33642f5a02e2ff469"
)
_PARENT_IMPLEMENTATION_DECISION_SHA256 = (
    "04b94b1c2c1bc8458970c679177ee5daa8455f77e2e90e980e5da7897bbb448b"
)
_REPAIR_FAILURE_SHA256 = (
    "9ddf370eb4a224aed071104ab91c7a5ad5ca8fdd28370875be3eaf6dd4f2b672"
)
_REPAIR_PRE_REVIEW_SHA256 = (
    "e492110f55005d833a833d474745ac2a957aa456541bedf9dfbc0cd52b4a00f9"
)
_REPAIR_IMPLEMENTATION_DECISION_SHA256 = (
    "8df4301b2ef687905f91a8103cb9ce9cac7327a581f46d4f60d06760989da5d4"
)
_ORIGINAL_IDENTITY_REVIEW_SHA256 = (
    "e615da0027a1cbb8bd0ab60f2b32cd09f37ccd49cf6a3e420a1ca9e8427a837e"
)
_ORIGINAL_EXECUTION_DECISION_SHA256 = (
    "78c274ccf8c14fc0dd4deff1a2e791eb64ad154100af8db8ef0f72795ff40d9f"
)
_READINESS_SHA256 = (
    "318d6d6c612b7c043963de2b70556031d47c3b04b15de8ce8daca7bd23fcd386"
)
_MULTISCALE_PROGRAM_SHA256 = (
    "be31b737b7835afaf718821c0584d668aa0878bb2950a667876296f731ac2a97"
)
_HIERARCHY_PROGRAM_SHA256 = (
    "04e73bb5c59ee6ebf69309bbcad938c810eed68c3b339b51bda2b95ff51a89dd"
)
_SUPPORT_PROGRAM_SHA256 = (
    "6964fcfe067128eef01d8fb4b655e9ef9a6053e845236f03a0f534bae8635604"
)
_MEASUREMENT_PROGRAM_SHA256 = (
    "210d683af1cfbfc2a20dfe232740930feb38edd14de715e54592757df6fde812"
)
_CANDIDATE_PROGRAM_SHA256 = (
    "92ee690b1333b28ccf0a09659480e19086e6eb4f9f39c8961e0b26c334cc21bd"
)
_EVALUATOR_PROGRAM_SHA256 = (
    "b46167deff074d48540a88949ef6fcf86b474aa6a1c7806b357e919cc497eb49"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_COMPATIBILITY_CONTAINER_DIGEST = (
    "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1"
)
_COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
)
_PROSPECTIVE_REFERENCE_PATH = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_PROSPECTIVE_OUTPUT_PATH = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-"
    "public-finder-source-hierarchy-parent-construction.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-hierarchy-"
    "parent-construction-5f2b098"
)
_PROSPECTIVE_BASELINE_PATH = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_PROHIBITED_AUTHORIZATIONS = (
    "campaign_execution_authorized",
    "cutover_authorized",
    "fresh_qualification_authorized",
    "optimization_authorized",
    "public_development_execution_authorized",
    "release_authorized",
    "rescoring_authorized",
    "threshold_or_photometric_tuning_authorized",
    "viewed_data_execution_authorized",
)


def _load_json(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} not authorized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} not authorized")
    return cast(dict[str, object], value)


def _load_consumed_wrapper() -> dict[str, Any]:
    """Load the exact predecessor without executing its entry point."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed source-reconstruction wrapper changed")
    return runpy.run_path(str(_CONSUMED_WRAPPER))


def _load_source_association_composition() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any]
]:
    """Descend through both predecessor overlays to the frozen replay."""
    source_reconstruction = _load_consumed_wrapper()
    measurement_repair = cast(
        dict[str, Any], source_reconstruction["_load_consumed_wrapper"]()
    )
    source_association = cast(
        dict[str, Any], measurement_repair["_load_consumed_wrapper"]()
    )
    current = cast(
        dict[str, Any], source_association["_load_current_wrapper"]()
    )
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    return source_association, current, frozen


def _candidate_configuration_sha256() -> str:
    """Return the approved parent-construction configuration identity."""
    configuration = (
        public_finder_source_hierarchy_parent_construction_configuration(
            _BASE_REVIEW,
            _CORRECTION_CONTRACT,
            _SOURCE_RECONSTRUCTION_PRE_REVIEW,
            _SOURCE_RECONSTRUCTION_DECISION,
            _ROOT_CAUSE_PRE_REVIEW,
            _ROOT_CAUSE_DECISION,
            _PARENT_PRE_REVIEW,
            _PARENT_IMPLEMENTATION_DECISION,
        )
    )
    identity = canonical_sha256(configuration)
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("parent-construction configuration changed")
    return identity


def _candidate_runtime_identity(revision: str) -> ExternalRuntimeIdentity:
    """Bind the parent overlay to unchanged runtime dependencies."""
    if revision != _CANDIDATE_REVISION:
        raise ValueError("parent-construction candidate revision changed")
    return ExternalRuntimeIdentity(
        name="hebog-source-overlay",
        version="0.6.0",
        source_revision=revision,
        container_image_digest=_COMPATIBILITY_CONTAINER_DIGEST,
        dependency_inventory_sha256=(
            _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
        ),
    )


def _install_parent_construction_static_seams(
    frozen: dict[str, Any],
) -> None:
    """Install the exact predecessor plus the new candidate identity."""
    consumed = _load_consumed_wrapper()
    consumed["_install_source_reconstruction_static_seams"](frozen)
    frozen["_CANDIDATE_REVISION"] = _CANDIDATE_REVISION
    frozen["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"] = (
        _CLOSED_BASELINE_SHA256
    )
    frozen["_candidate_configuration_sha256"] = _candidate_configuration_sha256
    frozen["_candidate_runtime_identity"] = _candidate_runtime_identity
    writer_globals = frozen["_write_continuum_products"].__globals__
    writer_globals["build_post_correction_continuum_products"] = (
        build_public_finder_source_reconstruction_continuum_products
    )


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Reinstall parent-construction seams in each spawned worker."""
    _, _, frozen = _load_source_association_composition()
    _install_parent_construction_static_seams(frozen)
    return cast(str, frozen["_generate_candidate_product"](task))


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require the one prospective write-once namespace."""
    expected = {
        "reference_reconstruction": _PROSPECTIVE_REFERENCE_PATH,
        "output": _PROSPECTIVE_OUTPUT_PATH,
        "scratch": _PROSPECTIVE_SCRATCH_PATH,
        "closed_component_baseline_ledger": _PROSPECTIVE_BASELINE_PATH,
        "workers": 2,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(f"cumulative replay {field} identity changed")


def _git_revision() -> str:
    """Return the clean wrapper checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("parent-construction replay requires clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _validate_readiness() -> None:
    """Require final readiness to name only this prospective evidence."""
    if file_sha256(_READINESS) != _READINESS_SHA256:
        raise ValueError("parent-construction readiness identity changed")
    document = _load_json(_READINESS, label="readiness contract")
    values = document.get("required_evidence")
    if not isinstance(values, list):
        raise ValueError("parent-construction readiness identity changed")
    evidence = {
        item.get("evidence_id"): item
        for item in values
        if isinstance(item, dict)
    }
    required = (
        evidence.get(
            "public-finder-source-hierarchy-parent-construction-cumulative-"
            "regression"
        ),
        evidence.get(
            "public-finder-source-hierarchy-parent-construction-held-out-"
            "qualification"
        ),
    )
    for item in required:
        if not isinstance(item, dict):
            raise ValueError("parent-construction readiness identity changed")
        fields = item.get("required_fields")
        if not isinstance(fields, dict) or (
            fields.get("candidate_revision") != _CANDIDATE_REVISION
            or fields.get("candidate_source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
            or fields.get("candidate_configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
        ):
            raise ValueError("parent-construction readiness identity changed")


def _validate_implementation_decision(document: dict[str, object]) -> None:
    """Require fixture authority and reject transfer to execution."""
    if document.get("status") != (
        "authorized-for-fixture-only-parent-construction"
    ):
        raise ValueError("parent construction implementation not authorized")
    authorization = document.get("authorization")
    if not isinstance(authorization, dict) or (
        authorization.get("parent_construction_implementation_authorized")
        is not True
        or authorization.get("fixture_only_validation_authorized") is not True
        or authorization.get("candidate_identity_freeze_authorized")
        is not True
        or authorization.get("replay_identity_freeze_authorized") is not True
        or authorization.get("cumulative_replay_authorized") is not False
    ):
        raise ValueError("parent construction authorization changed")
    if any(
        authorization.get(field) is not False
        for field in _PROHIBITED_AUTHORIZATIONS
    ):
        raise ValueError("parent construction authorization changed")


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify candidate, programs, retained evidence, and absent outputs."""
    _require_exact_invocation(arguments)
    revision = _git_revision()
    if source_tree_sha256(_ROOT) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("parent-construction source tree changed")
    if _candidate_configuration_sha256() != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("parent-construction configuration changed")
    for path, expected, label in (
        (_CONSUMED_WRAPPER, _CONSUMED_WRAPPER_SHA256, "consumed wrapper"),
        (
            _SOURCE_RECONSTRUCTION_PRE_REVIEW,
            _SOURCE_RECONSTRUCTION_PRE_REVIEW_SHA256,
            "source-reconstruction pre-review",
        ),
        (
            _SOURCE_RECONSTRUCTION_DECISION,
            _SOURCE_RECONSTRUCTION_DECISION_SHA256,
            "source-reconstruction decision",
        ),
        (_ROOT_CAUSE_PRE_REVIEW, _ROOT_CAUSE_PRE_REVIEW_SHA256, "root cause"),
        (_ROOT_CAUSE_DECISION, _ROOT_CAUSE_DECISION_SHA256, "root decision"),
        (_PARENT_PRE_REVIEW, _PARENT_PRE_REVIEW_SHA256, "parent pre-review"),
        (
            _PARENT_IMPLEMENTATION_DECISION,
            _PARENT_IMPLEMENTATION_DECISION_SHA256,
            "parent decision",
        ),
        (_REPAIR_FAILURE, _REPAIR_FAILURE_SHA256, "repair failure"),
        (
            _REPAIR_PRE_REVIEW,
            _REPAIR_PRE_REVIEW_SHA256,
            "repair pre-review",
        ),
        (
            _REPAIR_IMPLEMENTATION_DECISION,
            _REPAIR_IMPLEMENTATION_DECISION_SHA256,
            "repair implementation decision",
        ),
        (
            _ORIGINAL_IDENTITY_REVIEW,
            _ORIGINAL_IDENTITY_REVIEW_SHA256,
            "original identity review",
        ),
        (
            _ORIGINAL_EXECUTION_DECISION,
            _ORIGINAL_EXECUTION_DECISION_SHA256,
            "original execution decision",
        ),
        (_READINESS, _READINESS_SHA256, "readiness"),
        (_MULTISCALE_PROGRAM, _MULTISCALE_PROGRAM_SHA256, "multiscale"),
        (_HIERARCHY_PROGRAM, _HIERARCHY_PROGRAM_SHA256, "hierarchy"),
        (_SUPPORT_PROGRAM, _SUPPORT_PROGRAM_SHA256, "support"),
        (_MEASUREMENT_PROGRAM, _MEASUREMENT_PROGRAM_SHA256, "measurement"),
        (_CANDIDATE_PROGRAM, _CANDIDATE_PROGRAM_SHA256, "candidate"),
        (_EVALUATOR_PROGRAM, _EVALUATOR_PROGRAM_SHA256, "evaluator"),
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
            raise ValueError(f"parent-construction {label} identity changed")
    _validate_readiness()
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("parent-construction write-once namespace exists")
    return revision


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Delegate complete retained-reference verification without science."""
    return _load_consumed_wrapper()["_verify_reference_reconstruction"](
        arguments
    )


def verify_parent_construction_replay_composition(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Verify all identities and references without creating replay state."""
    decision = _load_json(
        implementation_decision_path,
        label="parent-construction implementation",
    )
    _validate_implementation_decision(decision)
    execution_revision = _require_common_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
    source_association, _, frozen = _load_source_association_composition()
    if not callable(
        source_association.get("_install_source_association_composition")
    ) or not callable(frozen.get("main")):
        raise ValueError("parent-construction execution composition changed")
    _install_parent_construction_static_seams(frozen)
    if not callable(frozen.get("_generate_candidate_product")):
        raise ValueError("parent-construction candidate composition changed")
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "cumulative_replay_started": False,
        "execution_checkout_revision": execution_revision,
        "execution_delegation_verified": True,
        "output_absent": not arguments.output.exists(),
        "readiness_sha256": _READINESS_SHA256,
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "scratch_absent": not arguments.scratch.exists(),
        "status": "pass",
        "verified_input_count": len(verified.inputs),
        "verified_reference_run_count": len(verified.runs),
    }


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity a later exact approval must bind."""
    fields = cast(
        dict[str, object],
        _load_consumed_wrapper()["_expected_execution_fields"](arguments),
    )
    fields.update(
        {
            "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "candidate_revision": _CANDIDATE_REVISION,
            "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            "consumed_source_reconstruction_wrapper_sha256": (
                _CONSUMED_WRAPPER_SHA256
            ),
            "source_reconstruction_root_cause_pre_review_sha256": (
                _ROOT_CAUSE_PRE_REVIEW_SHA256
            ),
            "source_reconstruction_root_cause_decision_sha256": (
                _ROOT_CAUSE_DECISION_SHA256
            ),
            "source_hierarchy_parent_construction_pre_review_sha256": (
                _PARENT_PRE_REVIEW_SHA256
            ),
            (
                "source_hierarchy_parent_construction_implementation_"
                "decision_sha256"
            ): _PARENT_IMPLEMENTATION_DECISION_SHA256,
            "parent_construction_replay_failure_sha256": (
                _REPAIR_FAILURE_SHA256
            ),
            "original_parent_construction_replay_identity_review_sha256": (
                _ORIGINAL_IDENTITY_REVIEW_SHA256
            ),
            "original_parent_construction_execution_decision_sha256": (
                _ORIGINAL_EXECUTION_DECISION_SHA256
            ),
            "parent_construction_replay_repair_pre_review_sha256": (
                _REPAIR_PRE_REVIEW_SHA256
            ),
            (
                "parent_construction_replay_repair_implementation_"
                "decision_sha256"
            ): _REPAIR_IMPLEMENTATION_DECISION_SHA256,
            "source_reconstruction_hierarchy_program_sha256": (
                _HIERARCHY_PROGRAM_SHA256
            ),
            "source_reconstruction_measurement_program_sha256": (
                _MEASUREMENT_PROGRAM_SHA256
            ),
            "source_reconstruction_candidate_program_sha256": (
                _CANDIDATE_PROGRAM_SHA256
            ),
            "readiness_contract_sha256": _READINESS_SHA256,
            "reference_reconstruction_sha256": (
                _REFERENCE_RECONSTRUCTION_SHA256
            ),
            "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
            "reference_reconstruction_path": str(
                arguments.reference_reconstruction
            ),
            "output_path": str(arguments.output),
            "scratch_path": str(arguments.scratch),
            "closed_baseline_path": str(
                arguments.closed_component_baseline_ledger
            ),
            "workers": arguments.workers,
            "wrapper_sha256": file_sha256(Path(__file__)),
        }
    )
    return fields


def _authorize_replay(
    arguments: argparse.Namespace,
    execution_decision_path: Path,
) -> dict[str, object]:
    """Require a future exact review and named one-replay approval."""
    if not execution_decision_path.is_file():
        raise ValueError(
            "parent-construction cumulative replay not authorized"
        )
    decision = _load_json(
        execution_decision_path,
        label="parent-construction cumulative replay",
    )
    if (
        decision.get("execution_authorized") is not True
        or decision.get("cumulative_replay_authorized") is not True
    ):
        raise ValueError(
            "parent-construction cumulative replay not authorized"
        )
    expected_execution_sha256 = canonical_sha256(
        _expected_execution_fields(arguments)
    )
    if decision.get("expected_execution_sha256") != (
        expected_execution_sha256
    ):
        raise ValueError("cumulative replay execution identity changed")
    prohibited = decision.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or prohibited != dict.fromkeys(
        _PROHIBITED_AUTHORIZATIONS, False
    ):
        raise ValueError("parent-construction authorization changed")
    original_decision = decision.get("original_execution_decision")
    if not isinstance(original_decision, dict) or original_decision != {
        "path": str(_ORIGINAL_EXECUTION_DECISION.relative_to(_ROOT)),
        "sha256": _ORIGINAL_EXECUTION_DECISION_SHA256,
    }:
        raise ValueError("original replay authorization changed")
    review = decision.get("parent_construction_replay_repair_review")
    if not isinstance(review, dict) or review.get("path") != str(
        _IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError("parent-construction identity review changed")
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or not _IDENTITY_REVIEW.is_file()
        or file_sha256(_IDENTITY_REVIEW) != review_sha256
    ):
        raise ValueError("parent-construction identity review changed")
    execution_revision = _require_common_identities(arguments)
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_source_overlay_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "execution_checkout_revision": execution_revision,
        "execution_decision_sha256": file_sha256(execution_decision_path),
        "identity_review_sha256": review_sha256,
        "original_execution_decision_sha256": (
            _ORIGINAL_EXECUTION_DECISION_SHA256
        ),
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def run_authorized_replay(
    arguments: argparse.Namespace,
    *,
    execution_decision_path: Path,
) -> None:
    """Delegate exactly once only after a later named approval."""
    provenance = _authorize_replay(arguments, execution_decision_path)
    verified = _verify_reference_reconstruction(arguments)
    source_association, current, frozen = (
        _load_source_association_composition()
    )
    source_association["_install_source_association_composition"](
        current,
        frozen,
        provenance,
        verified_reference=verified,
    )
    _install_parent_construction_static_seams(frozen)
    frozen["_generate_candidate_product"] = _generate_candidate_product
    frozen["_parse_args"] = lambda: arguments
    frozen["main"]()


def _parse_args() -> argparse.Namespace:
    """Parse the one prospective exact replay invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--closed-component-baseline-ledger", required=True, type=Path
    )
    arguments = parser.parse_args()
    arguments.campaign = None
    return arguments


def main() -> None:
    """Run only after a future exact replay approval exists."""
    run_authorized_replay(
        _parse_args(), execution_decision_path=_EXECUTION_DECISION
    )


if __name__ == "__main__":
    main()
