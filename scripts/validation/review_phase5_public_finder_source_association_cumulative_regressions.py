#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run only an authorized source-association cumulative replay."""

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
    build_public_finder_correction_continuum_products,
    public_finder_source_association_candidate_configuration,
)

_ROOT = Path(__file__).parents[2]
_CURRENT_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_correction_cumulative_regressions.py"
)
_HISTORICAL_REPLAY = (
    _ROOT / "scripts/validation/review_phase5_cumulative_regressions.py"
)
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_CORRECTION_CONTRACT = (
    _ROOT / "config/contracts/phase-5-public-finder-correction.json"
)
_SOURCE_ASSOCIATION_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "pre-review.json"
)
_SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "implementation-decision.json"
)
_SOURCE_ASSOCIATION_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "identity-review.json"
)
_COMPOSITION_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-replay-"
    "composition-pre-review.json"
)
_COMPOSITION_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-replay-"
    "composition-implementation-decision.json"
)
_EXECUTION_IDENTITY_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-source-association-cumulative-"
    "replay-review.json"
)
_EXECUTION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-source-association-cumulative-"
    "replay-execution-decision.json"
)
_COMPILER = (
    _ROOT
    / "scripts/validation/compile_phase5_external_post_failure_campaign.py"
)
_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
)
_REFERENCE_VERIFIER = (
    _ROOT / "scripts/validation/reconstruct_phase5_viewed_references.py"
)
_ENDPOINT_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-external-post-failure-endpoint-registry.json"
)
_EVALUATION_CONTRACT = (
    _ROOT / "config/contracts/phase-5-external-post-failure-evaluation.json"
)
_VIEWED_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_RUNTIME_IDENTITY_REGISTRY = (
    _ROOT / "config/contracts/phase-5-public-finder-correction-reference-"
    "reconstruction-decision.json"
)
_DEPENDENCY_LOCK = _ROOT / "uv.lock"

_CANDIDATE_REVISION = "26e639ace9d39b039eb7c3114427277c91809591"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "34fecf302e7c6a9722dd15b8d843d316a4e4e7a1be3df2610a2d45b0a5dfb893"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
)
_CURRENT_WRAPPER_SHA256 = (
    "04a3a54335c93b6abfa71c71ba2e4771ae48dfc38bc3587a673fa2683fa780ac"
)
_HISTORICAL_REPLAY_SHA256 = (
    "5d41d31ee79cd0d6d203cd774267fd504d06fe7662768486f99c31a7902b8a3f"
)
_BASE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_CORRECTION_CONTRACT_SHA256 = (
    "f0ddd4d5cb8c3c5542d1de761f6fde0644ec7cf051d5fb1dc7482ed3b96ff524"
)
_SOURCE_ASSOCIATION_PRE_REVIEW_SHA256 = (
    "9af42348896e0449e007fe2318648f66122313d600137f8f5ec525ebaec1cc3c"
)
_SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION_SHA256 = (
    "6a495cfcb54ec01e5a7290b6c28edf7b7fffe89f88318c5b6f3e135e70a15553"
)
_SOURCE_ASSOCIATION_IDENTITY_REVIEW_SHA256 = (
    "c58eec6e1492196b40b859bd31aa3b8c55de51f8a7fc53a95bc5db9ecc19e263"
)
_COMPOSITION_PRE_REVIEW_SHA256 = (
    "a2e13e1126ce7733949dca570116c8b9cb73eb8128226bedcd9ee214f44e32a3"
)
_COMPOSITION_IMPLEMENTATION_DECISION_SHA256 = (
    "37931ad39389a8da5c3a66251405cef92aed68e806a49b0ae78c86d582990da6"
)
_COMPILER_SHA256 = (
    "e442f6586993d95a942a80af4e45fbf5b50448b434d5c0a244d78fb333b679b8"
)
_EVALUATOR_SHA256 = (
    "7612746bda483c82d0e7e72a7f49bb8283f8ae6c03d26bd18508184dbda7169a"
)
_REFERENCE_VERIFIER_SHA256 = (
    "81faad486ddb306e175a7ddd8c1c281a2e498cd30bb60f3e43c7b6e791cd0126"
)
_ENDPOINT_REGISTRY_SHA256 = (
    "2d7a646b6206bd127b1e470b16d1fe35ebc3f238835eafdc6c77d8a82b79ef1c"
)
_EVALUATION_CONTRACT_SHA256 = (
    "45901f8ca4526fdc1007d26d891e409306565e749bad2b959181a9929ff73016"
)
_VIEWED_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_RUNTIME_IDENTITY_REGISTRY_SHA256 = (
    "cc22c7736fab3a3e6c1e84e3e3426e952df40651706e0b69d1dd2da8bfc5b660"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_REFERENCE_PRODUCER_SOURCE_TREE_SHA256 = (
    "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_DEPENDENCY_LOCK_SHA256 = (
    "c81a9831ec545b2d7797e1c0951ad46e0e23337b97866ced0ae27e290dfd71ff"
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
    "benchmark-results/phase-5/"
    "cumulative-regression-ledger-public-finder-source-association.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-association-26e639a"
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
_SHA256_HEX_LENGTH = 64


def _load_current_wrapper() -> dict[str, Any]:
    """Load the checksum-bound consumed wrapper without executing it."""
    if file_sha256(_CURRENT_WRAPPER) != _CURRENT_WRAPPER_SHA256:
        raise ValueError("current correction wrapper identity changed")
    return runpy.run_path(str(_CURRENT_WRAPPER))


def _candidate_configuration_sha256() -> str:
    """Return the exact approved source-association composition."""
    configuration = public_finder_source_association_candidate_configuration(
        _BASE_REVIEW,
        _CORRECTION_CONTRACT,
        _SOURCE_ASSOCIATION_PRE_REVIEW,
        _SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION,
    )
    identity = canonical_sha256(configuration)
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError(
            "candidate source-association configuration identity changed"
        )
    return identity


def _candidate_runtime_identity(revision: str) -> ExternalRuntimeIdentity:
    """Record the new source overlay over unchanged dependencies."""
    if revision != _CANDIDATE_REVISION:
        raise ValueError("candidate source overlay revision changed")
    return ExternalRuntimeIdentity(
        name="hebog-source-overlay",
        version="0.6.0",
        source_revision=revision,
        container_image_digest=_COMPATIBILITY_CONTAINER_DIGEST,
        dependency_inventory_sha256=(
            _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
        ),
    )


def _install_static_science_seams(frozen: dict[str, Any]) -> None:
    """Replace only candidate identity and the approved Continuum builder."""
    frozen["_CANDIDATE_REVISION"] = _CANDIDATE_REVISION
    frozen["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"] = (
        _CLOSED_BASELINE_SHA256
    )
    frozen["_candidate_configuration_sha256"] = _candidate_configuration_sha256
    frozen["_candidate_runtime_identity"] = _candidate_runtime_identity
    writer_globals = frozen["_write_continuum_products"].__globals__
    writer_globals["build_post_correction_continuum_products"] = (
        build_public_finder_correction_continuum_products
    )


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Install the source-association seams in each spawned worker."""
    current = _load_current_wrapper()
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    _install_static_science_seams(frozen)
    return cast(str, frozen["_generate_candidate_product"](task))


def _install_source_association_composition(
    current: dict[str, Any],
    frozen: dict[str, Any],
    provenance: dict[str, object],
    *,
    verified_reference: Any | None = None,
) -> None:
    """Layer only source-association candidate seams over the repair."""
    current["_install_repair_composition"](
        frozen,
        provenance,
        verified_reference=verified_reference,
    )
    _install_static_science_seams(frozen)
    frozen["_generate_candidate_product"] = _generate_candidate_product


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity a future replay approval must bind."""
    return {
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "base_review_sha256": _BASE_REVIEW_SHA256,
        "correction_contract_sha256": _CORRECTION_CONTRACT_SHA256,
        "source_association_pre_review_sha256": (
            _SOURCE_ASSOCIATION_PRE_REVIEW_SHA256
        ),
        "source_association_implementation_decision_sha256": (
            _SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION_SHA256
        ),
        "source_association_identity_review_sha256": (
            _SOURCE_ASSOCIATION_IDENTITY_REVIEW_SHA256
        ),
        "composition_pre_review_sha256": _COMPOSITION_PRE_REVIEW_SHA256,
        "composition_implementation_decision_sha256": (
            _COMPOSITION_IMPLEMENTATION_DECISION_SHA256
        ),
        "current_wrapper_sha256": _CURRENT_WRAPPER_SHA256,
        "historical_replay_sha256": _HISTORICAL_REPLAY_SHA256,
        "compiler_sha256": _COMPILER_SHA256,
        "evaluator_sha256": _EVALUATOR_SHA256,
        "reference_verifier_sha256": _REFERENCE_VERIFIER_SHA256,
        "endpoint_registry_sha256": _ENDPOINT_REGISTRY_SHA256,
        "evaluation_contract_sha256": _EVALUATION_CONTRACT_SHA256,
        "viewed_request_sha256": _VIEWED_REQUEST_SHA256,
        "runtime_identity_registry_sha256": (
            _RUNTIME_IDENTITY_REGISTRY_SHA256
        ),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "reference_reconstruction_producer_source_tree_sha256": (
            _REFERENCE_PRODUCER_SOURCE_TREE_SHA256
        ),
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "dependency_lock_sha256": _DEPENDENCY_LOCK_SHA256,
        "compatibility_container_digest": _COMPATIBILITY_CONTAINER_DIGEST,
        "compatibility_dependency_inventory_sha256": (
            _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
        ),
        "wrapper_sha256": file_sha256(Path(__file__)),
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "output_path": str(arguments.output),
        "scratch_path": str(arguments.scratch),
        "closed_baseline_path": str(
            arguments.closed_component_baseline_ledger
        ),
        "workers": arguments.workers,
    }


def _validate_execution_decision(
    document: dict[str, object],
    arguments: argparse.Namespace,
) -> None:
    """Reject every unapproved or drifted future execution field."""
    if document.get("status") != (
        "reviewed-before-public-finder-source-association-cumulative-replay"
    ):
        raise ValueError("source-association cumulative replay not authorized")
    if (
        document.get("execution_authorized") is not True
        or document.get("cumulative_replay_authorized") is not True
    ):
        raise ValueError("source-association cumulative replay not authorized")
    for field, value in _expected_execution_fields(arguments).items():
        if document.get(field) != value:
            raise ValueError(f"cumulative replay {field} identity changed")
    prohibited_value = document.get("prohibited_authorizations")
    prohibited = (
        cast(dict[object, object], prohibited_value)
        if isinstance(prohibited_value, dict)
        else None
    )
    if prohibited is None or set(prohibited) != set(
        _PROHIBITED_AUTHORIZATIONS
    ):
        raise ValueError("cumulative replay authorization boundary changed")
    if any(prohibited.values()):
        raise ValueError("cumulative replay authorization boundary changed")
    review_value = document.get("source_association_replay_identity_review")
    review = (
        cast(dict[object, object], review_value)
        if isinstance(review_value, dict)
        else None
    )
    if review is None or review.get("path") != str(
        _EXECUTION_IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError("cumulative replay identity review changed")
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or len(review_sha256) != _SHA256_HEX_LENGTH
    ):
        raise ValueError("cumulative replay identity review changed")


def _git_revision() -> str:
    """Require a clean checkout and return its exact revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("cumulative replay requires a clean source checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=_ROOT,
        text=True,
    ).strip()


def _require_file_identity(path: Path, expected: str, label: str) -> None:
    """Require one exact existing evidence, contract, or program file."""
    if not path.is_file() or file_sha256(path) != expected:
        raise ValueError(f"cumulative replay {label} identity changed")


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Keep fixture/no-write and future execution paths identical."""
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


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify candidate, evidence, runtime, and write-once state."""
    _require_exact_invocation(arguments)
    execution_revision = _git_revision()
    if source_tree_sha256(_ROOT) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("cumulative replay candidate source tree changed")
    if _candidate_configuration_sha256() != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("cumulative replay candidate configuration changed")
    for path, expected, label in (
        (_BASE_REVIEW, _BASE_REVIEW_SHA256, "base review"),
        (
            _CORRECTION_CONTRACT,
            _CORRECTION_CONTRACT_SHA256,
            "correction contract",
        ),
        (
            _SOURCE_ASSOCIATION_PRE_REVIEW,
            _SOURCE_ASSOCIATION_PRE_REVIEW_SHA256,
            "source-association pre-review",
        ),
        (
            _SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION,
            _SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION_SHA256,
            "source-association implementation decision",
        ),
        (
            _SOURCE_ASSOCIATION_IDENTITY_REVIEW,
            _SOURCE_ASSOCIATION_IDENTITY_REVIEW_SHA256,
            "source-association identity review",
        ),
        (
            _COMPOSITION_PRE_REVIEW,
            _COMPOSITION_PRE_REVIEW_SHA256,
            "composition pre-review",
        ),
        (
            _COMPOSITION_IMPLEMENTATION_DECISION,
            _COMPOSITION_IMPLEMENTATION_DECISION_SHA256,
            "composition implementation decision",
        ),
        (_CURRENT_WRAPPER, _CURRENT_WRAPPER_SHA256, "current wrapper"),
        (
            _HISTORICAL_REPLAY,
            _HISTORICAL_REPLAY_SHA256,
            "historical replay",
        ),
        (_COMPILER, _COMPILER_SHA256, "compiler"),
        (_EVALUATOR, _EVALUATOR_SHA256, "evaluator"),
        (
            _REFERENCE_VERIFIER,
            _REFERENCE_VERIFIER_SHA256,
            "reference verifier",
        ),
        (_ENDPOINT_REGISTRY, _ENDPOINT_REGISTRY_SHA256, "endpoint registry"),
        (
            _EVALUATION_CONTRACT,
            _EVALUATION_CONTRACT_SHA256,
            "evaluation contract",
        ),
        (_VIEWED_REQUEST, _VIEWED_REQUEST_SHA256, "viewed request"),
        (
            _RUNTIME_IDENTITY_REGISTRY,
            _RUNTIME_IDENTITY_REGISTRY_SHA256,
            "runtime identity registry",
        ),
        (_DEPENDENCY_LOCK, _DEPENDENCY_LOCK_SHA256, "dependency lock"),
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
        _require_file_identity(path, expected, label)
    _load_current_wrapper()
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("cumulative replay write-once output state changed")
    return execution_revision


def _implementation_scope() -> dict[str, object]:
    """Return the exact named non-executable implementation scope."""
    return {
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "current_wrapper_sha256": _CURRENT_WRAPPER_SHA256,
        "prospective_output_path": str(_PROSPECTIVE_OUTPUT_PATH),
        "prospective_scratch_path": str(_PROSPECTIVE_SCRATCH_PATH),
        "reconstructed_reference_path": str(_PROSPECTIVE_REFERENCE_PATH),
        "reconstructed_reference_terminal_sha256": (
            _REFERENCE_RECONSTRUCTION_SHA256
        ),
        "required_result": (
            "validated-non-executable-wrapper-and-replacement-identity-review"
        ),
        "workers": 2,
    }


def _validate_implementation_decision(
    document: dict[str, object],
    _arguments: argparse.Namespace,
) -> None:
    """Validate implementation authority without opening replay authority."""
    if document.get("status") != (
        "authorized-for-source-association-replay-wrapper-implementation-and-"
        "no-write-validation"
    ):
        raise ValueError(
            "source-association wrapper implementation not authorized"
        )
    expected_authorization = {
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
        "release_authorized": False,
        "rescoring_authorized": False,
        "tuning_authorized": False,
        "viewed_data_execution_authorized": False,
    }
    if document.get("authorization") != expected_authorization:
        raise ValueError("source-association implementation boundary changed")
    if document.get("pre_review") != {
        "path": str(_COMPOSITION_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": _COMPOSITION_PRE_REVIEW_SHA256,
    }:
        raise ValueError("source-association pre-review identity changed")
    if (
        document.get("candidate")
        != {
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        }
        or document.get("scope") != _implementation_scope()
    ):
        raise ValueError("source-association implementation scope changed")


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Delegate complete reconstruction verification to the bound wrapper."""
    current = _load_current_wrapper()
    return current["_verify_reference_reconstruction"](arguments)


def verify_source_association_replay_composition(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Run the approved complete no-write wrapper verification."""
    if not implementation_decision_path.is_file():
        raise ValueError(
            "source-association wrapper implementation not authorized"
        )
    value = json.loads(
        implementation_decision_path.read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise ValueError(
            "source-association wrapper implementation not authorized"
        )
    _validate_implementation_decision(
        cast(dict[str, object], value),
        arguments,
    )
    execution_revision = _require_common_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
    return {
        "status": "pass",
        "execution_checkout_revision": execution_revision,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "verified_input_count": len(verified.inputs),
        "verified_reference_run_count": len(verified.runs),
        "output_absent": not arguments.output.exists(),
        "scratch_absent": not arguments.scratch.exists(),
        "cumulative_replay_started": False,
    }


def _authorize_replay(
    arguments: argparse.Namespace,
    execution_decision_path: Path,
) -> dict[str, object]:
    """Validate a future exact approval before scientific input access."""
    if not execution_decision_path.is_file():
        raise ValueError("source-association cumulative replay not authorized")
    value = json.loads(execution_decision_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source-association cumulative replay not authorized")
    document = cast(dict[str, object], value)
    _validate_execution_decision(document, arguments)
    execution_revision = _require_common_identities(arguments)
    review = cast(
        dict[str, str], document["source_association_replay_identity_review"]
    )
    _require_file_identity(
        _EXECUTION_IDENTITY_REVIEW,
        review["sha256"],
        "source-association replay identity review",
    )
    return {
        "candidate_source_overlay_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "source_association_pre_review_sha256": (
            _SOURCE_ASSOCIATION_PRE_REVIEW_SHA256
        ),
        "source_association_implementation_decision_sha256": (
            _SOURCE_ASSOCIATION_IMPLEMENTATION_DECISION_SHA256
        ),
        "source_association_identity_review_sha256": (
            _SOURCE_ASSOCIATION_IDENTITY_REVIEW_SHA256
        ),
        "composition_pre_review_sha256": _COMPOSITION_PRE_REVIEW_SHA256,
        "composition_implementation_decision_sha256": (
            _COMPOSITION_IMPLEMENTATION_DECISION_SHA256
        ),
        "current_wrapper_sha256": _CURRENT_WRAPPER_SHA256,
        "wrapper_sha256": file_sha256(Path(__file__)),
        "source_association_replay_identity_review_sha256": review["sha256"],
        "execution_decision_sha256": file_sha256(execution_decision_path),
        "execution_checkout_revision": execution_revision,
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "runtime_binding": {
            "source_role": "exact-candidate-source-overlay",
            "container_role": "inherited-compatibility-dependency-reference",
            "source_association_baked_into_container": False,
            "container_digest": _COMPATIBILITY_CONTAINER_DIGEST,
            "dependency_inventory_sha256": (
                _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
            ),
        },
    }


def run_authorized_replay(
    arguments: argparse.Namespace,
    *,
    execution_decision_path: Path,
) -> None:
    """Delegate once after a future exact named replay approval."""
    provenance = _authorize_replay(arguments, execution_decision_path)
    verified_reference = _verify_reference_reconstruction(arguments)
    current = _load_current_wrapper()
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    _install_source_association_composition(
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
