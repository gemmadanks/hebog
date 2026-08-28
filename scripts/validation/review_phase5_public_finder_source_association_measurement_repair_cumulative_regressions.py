#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run only a future authorized measurement-repair cumulative replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_source_association_cumulative_regressions.py"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-replay-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-replay-implementation-decision.json"
)
_READINESS_CONTRACT = _ROOT / "config/contracts/phase-5-readiness.json"
_MEASUREMENT_REPAIR = _ROOT / "src/hebog/validation/products.py"
_EXECUTION_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-execution-decision.json"
)

_CANDIDATE_REVISION = "6184a32648eee637f0aca03ab2ec0249bd0510f0"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "517d56e19a5d58eb386d96bdb181d36afb574ad018222f870cc8434c398044ff"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
)
_MEASUREMENT_REPAIR_SHA256 = (
    "a3c53daac3dbae03bd6b3f62488cd46de541d79d9c6c903d34ce7951334d690b"
)
_CONSUMED_WRAPPER_SHA256 = (
    "bfc1d6d0d255b9fd7e7b43f910e9c2665d9083de572bce7b64afee66c473f357"
)
_PRE_REVIEW_SHA256 = (
    "7687839f4c65c0a6d549d42b0ddeacd8c6954912389071605d696394307c653d"
)
_IMPLEMENTATION_DECISION_SHA256 = (
    "b9d48850a2447e888ef7eb923143dad31c41d5867694b536cbbec441bd590d1e"
)
_READINESS_CONTRACT_SHA256 = (
    "cef14d0130b264ddfc5e4277455820cae5436aa578b0ddb798a103ce9421321f"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_PROSPECTIVE_REFERENCE_PATH = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_PROSPECTIVE_OUTPUT_PATH = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-public-finder-"
    "source-association-measurement-repair.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-association-"
    "measurement-repair-6184a32"
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
    "tuning_authorized",
    "viewed_data_execution_authorized",
)
_IMPLEMENTATION_AUTHORIZATION = {
    "campaign_execution_authorized": False,
    "complete_no_write_reference_verification_authorized": True,
    "cumulative_replay_authorized": False,
    "cutover_authorized": False,
    "fixture_no_write_validation_authorized": True,
    "fresh_qualification_authorized": False,
    "identity_freeze_authorized": True,
    "implementation_authorized": True,
    "optimization_authorized": False,
    "public_development_execution_authorized": False,
    "readiness_contract_implementation_authorized": True,
    "release_authorized": False,
    "rescoring_authorized": False,
    "tuning_authorized": False,
    "viewed_data_execution_authorized": False,
    "wrapper_implementation_authorized": True,
}
_SHA256_HEX_LENGTH = 64


def _load_json(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} not authorized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} not authorized")
    return cast(dict[str, object], value)


def _load_consumed_wrapper() -> dict[str, Any]:
    """Load and rebind the exact consumed source-association wrapper."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed wrapper identity changed")
    consumed = runpy.run_path(str(_CONSUMED_WRAPPER))
    bindings = {
        "_CANDIDATE_REVISION": _CANDIDATE_REVISION,
        "_CANDIDATE_SOURCE_TREE_SHA256": (_CANDIDATE_SOURCE_TREE_SHA256),
        "_CANDIDATE_CONFIGURATION_SHA256": (_CANDIDATE_CONFIGURATION_SHA256),
        "_COMPOSITION_PRE_REVIEW": _PRE_REVIEW,
        "_COMPOSITION_PRE_REVIEW_SHA256": _PRE_REVIEW_SHA256,
        "_COMPOSITION_IMPLEMENTATION_DECISION": (_IMPLEMENTATION_DECISION),
        "_COMPOSITION_IMPLEMENTATION_DECISION_SHA256": (
            _IMPLEMENTATION_DECISION_SHA256
        ),
        "_EXECUTION_IDENTITY_REVIEW": _EXECUTION_IDENTITY_REVIEW,
        "_EXECUTION_DECISION": _EXECUTION_DECISION,
        "_PROSPECTIVE_OUTPUT_PATH": _PROSPECTIVE_OUTPUT_PATH,
        "_PROSPECTIVE_SCRATCH_PATH": _PROSPECTIVE_SCRATCH_PATH,
        "_generate_candidate_product": _generate_candidate_product,
    }
    consumed.update(bindings)
    consumed["_install_source_association_composition"].__globals__.update(
        bindings
    )
    return consumed


def _candidate_configuration_sha256() -> str:
    """Return the unchanged approved source-association configuration."""
    value = cast(
        str,
        _load_consumed_wrapper()["_candidate_configuration_sha256"](),
    )
    if value != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("candidate configuration identity changed")
    return value


def _candidate_runtime_identity(revision: str) -> Any:
    """Return the inherited runtime bound to the repaired source revision."""
    return _load_consumed_wrapper()["_candidate_runtime_identity"](revision)


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Reinstall the repaired candidate in every spawned worker."""
    consumed = _load_consumed_wrapper()
    current = cast(dict[str, Any], consumed["_load_current_wrapper"]())
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    consumed["_install_static_science_seams"](frozen)
    return cast(str, frozen["_generate_candidate_product"](task))


def _install_measurement_repair_composition(
    consumed: dict[str, Any],
    current: dict[str, Any],
    frozen: dict[str, Any],
    provenance: dict[str, object],
    *,
    verified_reference: Any | None = None,
) -> None:
    """Layer only the repaired candidate over the consumed composition."""
    consumed["_install_source_association_composition"](
        current,
        frozen,
        provenance,
        verified_reference=verified_reference,
    )
    frozen["_generate_candidate_product"] = _generate_candidate_product


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require the one prospective write-once replay namespace."""
    _load_consumed_wrapper()["_require_exact_invocation"](arguments)


def _committed_file_sha256(revision: str, path: str) -> str:
    """Hash one file from the exact candidate revision."""
    value = subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(value).hexdigest()


def _validate_readiness_contract() -> None:
    """Require the prospective candidate and evidence paths before replay."""
    if file_sha256(_READINESS_CONTRACT) != _READINESS_CONTRACT_SHA256:
        raise ValueError("readiness contract identity changed")
    document = _load_json(_READINESS_CONTRACT, label="readiness contract")
    evidence_value = document.get("required_evidence")
    if not isinstance(evidence_value, list):
        raise ValueError("readiness contract identity changed")
    evidence = {
        item.get("evidence_id"): item
        for item in evidence_value
        if isinstance(item, dict)
    }
    cumulative = evidence.get(
        "public-finder-source-association-measurement-repair-"
        "cumulative-regression"
    )
    qualification = evidence.get(
        "public-finder-source-association-measurement-repair-"
        "held-out-qualification"
    )
    if not isinstance(cumulative, dict) or not isinstance(qualification, dict):
        raise ValueError("readiness contract identity changed")
    for requirement in (cumulative, qualification):
        fields = requirement.get("required_fields")
        if (
            not isinstance(fields, dict)
            or fields.get("candidate_revision") != _CANDIDATE_REVISION
        ):
            raise ValueError("readiness contract identity changed")
        if (
            fields.get("candidate_source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
            or fields.get("candidate_configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
        ):
            raise ValueError("readiness contract identity changed")


def _expected_implementation_scope() -> dict[str, object]:
    """Return the exact approved non-executable implementation scope."""
    return {
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "prospective_output_path": str(_PROSPECTIVE_OUTPUT_PATH),
        "prospective_scratch_path": str(_PROSPECTIVE_SCRATCH_PATH),
        "reconstructed_reference_path": str(_PROSPECTIVE_REFERENCE_PATH),
        "reconstructed_reference_terminal_sha256": (
            _REFERENCE_RECONSTRUCTION_SHA256
        ),
        "required_result": (
            "validated-non-executable-measurement-repair-wrapper-readiness-"
            "and-replacement-identity-review"
        ),
        "workers": 2,
    }


def _validate_implementation_decision(document: dict[str, object]) -> None:
    """Validate the exact approval without opening replay authority."""
    if document.get("status") != (
        "authorized-for-measurement-repair-wrapper-readiness-implementation-"
        "and-no-write-validation"
    ):
        raise ValueError("measurement-repair implementation not authorized")
    if document.get("authorization") != _IMPLEMENTATION_AUTHORIZATION:
        raise ValueError("measurement-repair authorization boundary changed")
    if document.get("pre_review") != {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": _PRE_REVIEW_SHA256,
    }:
        raise ValueError("measurement-repair pre-review identity changed")
    if document.get("candidate") != {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "measurement_repair_sha256": _MEASUREMENT_REPAIR_SHA256,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }:
        raise ValueError("measurement-repair candidate identity changed")
    if document.get("scope") != _expected_implementation_scope():
        raise ValueError("measurement-repair implementation scope changed")
    readiness = document.get("readiness")
    if not isinstance(readiness, dict) or readiness != {
        "contract_path": str(_READINESS_CONTRACT.relative_to(_ROOT)),
        "previous_sha256": (
            "bb0719fb17b36c2506073958b3012c237f029a6e54091057151f2c248fdb7540"
        ),
        "required_cumulative_evidence_id": (
            "public-finder-source-association-measurement-repair-"
            "cumulative-regression"
        ),
        "required_qualification_evidence_id": (
            "public-finder-source-association-measurement-repair-"
            "held-out-qualification"
        ),
        "status": "prospectively-rebound-before-replay",
    }:
        raise ValueError("measurement-repair readiness scope changed")


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify the consumed composition and every replacement identity."""
    consumed = _load_consumed_wrapper()
    revision = cast(str, consumed["_require_common_identities"](arguments))
    if file_sha256(_MEASUREMENT_REPAIR) != _MEASUREMENT_REPAIR_SHA256:
        raise ValueError("measurement-repair program identity changed")
    if (
        _committed_file_sha256(
            _CANDIDATE_REVISION,
            "src/hebog/validation/products.py",
        )
        != _MEASUREMENT_REPAIR_SHA256
    ):
        raise ValueError("measurement-repair candidate identity changed")
    _validate_readiness_contract()
    return revision


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Delegate complete verification to the consumed frozen machinery."""
    return _load_consumed_wrapper()["_verify_reference_reconstruction"](
        arguments
    )


def verify_measurement_repair_replay_composition(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Run fixture or complete verification without creating replay state."""
    decision = _load_json(
        implementation_decision_path,
        label="measurement-repair implementation",
    )
    _validate_implementation_decision(decision)
    execution_revision = _require_common_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
    return {
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "cumulative_replay_started": False,
        "execution_checkout_revision": execution_revision,
        "measurement_repair_sha256": _MEASUREMENT_REPAIR_SHA256,
        "output_absent": not arguments.output.exists(),
        "readiness_contract_sha256": _READINESS_CONTRACT_SHA256,
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
    """Return every identity a later one-replay approval must bind."""
    consumed = _load_consumed_wrapper()
    fields = cast(
        dict[str, object],
        consumed["_expected_execution_fields"](arguments),
    )
    fields.update(
        {
            "consumed_source_association_wrapper_sha256": (
                _CONSUMED_WRAPPER_SHA256
            ),
            "measurement_repair_implementation_decision_sha256": (
                _IMPLEMENTATION_DECISION_SHA256
            ),
            "measurement_repair_pre_review_sha256": _PRE_REVIEW_SHA256,
            "measurement_repair_sha256": _MEASUREMENT_REPAIR_SHA256,
            "readiness_contract_sha256": _READINESS_CONTRACT_SHA256,
            "wrapper_sha256": file_sha256(Path(__file__)),
        }
    )
    return fields


def _validate_execution_decision(
    document: dict[str, object],
    arguments: argparse.Namespace,
) -> None:
    """Reject every absent, unapproved, or drifted execution field."""
    if document.get("status") != (
        "reviewed-before-public-finder-source-association-measurement-repair-"
        "cumulative-replay"
    ):
        raise ValueError("measurement-repair cumulative replay not authorized")
    if (
        document.get("execution_authorized") is not True
        or document.get("cumulative_replay_authorized") is not True
    ):
        raise ValueError("measurement-repair cumulative replay not authorized")
    for field, value in _expected_execution_fields(arguments).items():
        if document.get(field) != value:
            raise ValueError(f"cumulative replay {field} identity changed")
    prohibited = document.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or set(prohibited) != set(
        _PROHIBITED_AUTHORIZATIONS
    ):
        raise ValueError("cumulative replay authorization boundary changed")
    if any(prohibited.values()):
        raise ValueError("cumulative replay authorization boundary changed")
    review = document.get("measurement_repair_replay_identity_review")
    if not isinstance(review, dict) or review.get("path") != str(
        _EXECUTION_IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError("cumulative replay identity review changed")
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or len(review_sha256) != _SHA256_HEX_LENGTH
    ):
        raise ValueError("cumulative replay identity review changed")


def _authorize_replay(
    arguments: argparse.Namespace,
    execution_decision_path: Path,
) -> dict[str, object]:
    """Validate a future separate exact approval before science access."""
    document = _load_json(
        execution_decision_path,
        label="measurement-repair cumulative replay",
    )
    _validate_execution_decision(document, arguments)
    execution_revision = _require_common_identities(arguments)
    review = cast(
        dict[str, str], document["measurement_repair_replay_identity_review"]
    )
    if (
        not _EXECUTION_IDENTITY_REVIEW.is_file()
        or file_sha256(_EXECUTION_IDENTITY_REVIEW) != review["sha256"]
    ):
        raise ValueError("cumulative replay identity review changed")
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_source_overlay_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "execution_checkout_revision": execution_revision,
        "execution_decision_sha256": file_sha256(execution_decision_path),
        "measurement_repair_identity_review_sha256": review["sha256"],
        "measurement_repair_sha256": _MEASUREMENT_REPAIR_SHA256,
        "readiness_contract_sha256": _READINESS_CONTRACT_SHA256,
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def run_authorized_replay(
    arguments: argparse.Namespace,
    *,
    execution_decision_path: Path,
) -> None:
    """Delegate once only after a later exact replay approval."""
    provenance = _authorize_replay(arguments, execution_decision_path)
    verified_reference = _verify_reference_reconstruction(arguments)
    consumed = _load_consumed_wrapper()
    current = cast(dict[str, Any], consumed["_load_current_wrapper"]())
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    _install_measurement_repair_composition(
        consumed,
        current,
        frozen,
        provenance,
        verified_reference=verified_reference,
    )
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
        "--closed-component-baseline-ledger",
        required=True,
        type=Path,
    )
    arguments = parser.parse_args()
    arguments.campaign = None
    return arguments


def main() -> None:
    """Run only after a future exact replay approval exists."""
    run_authorized_replay(
        _parse_args(),
        execution_decision_path=_EXECUTION_DECISION,
    )


if __name__ == "__main__":
    main()
