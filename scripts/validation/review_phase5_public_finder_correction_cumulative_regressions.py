#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Run only an authorized public-finder correction cumulative replay."""

from __future__ import annotations

import argparse
import importlib
import json
import runpy
import subprocess
import sys
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
    public_finder_correction_candidate_configuration,
)

_ROOT = Path(__file__).parents[2]
_FROZEN_REPLAY = (
    _ROOT / "scripts/validation/review_phase5_cumulative_regressions.py"
)
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_CORRECTION_CONTRACT = (
    _ROOT / "config/contracts/phase-5-public-finder-correction.json"
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
_IMPLEMENTATION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "repair-implementation-decision.json"
)
_REPAIR_IDENTITY_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "repair-review.json"
)
_REFERENCE_REPAIR_PRE_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "reference-provenance-repair-pre-review.json"
)
_REFERENCE_REPAIR_IMPLEMENTATION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "reference-provenance-repair-implementation-decision.json"
)
_REFERENCE_REPAIR_IDENTITY_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "reference-provenance-repair-review.json"
)
_EXECUTION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "reference-provenance-repair-execution-decision.json"
)
_DEPENDENCY_LOCK = _ROOT / "uv.lock"
_CANDIDATE_REVISION = "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "2de6564e78f1a3664dd3fb18f696c747bfc3350fdd894164c4fafb07528d1ba9"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "65c8876dcdb484bd5a82b3520e065ea6bf33cf24cfdd33b592c6c859231c62f0"
)
_CORRECTION_CONTRACT_SHA256 = (
    "f0ddd4d5cb8c3c5542d1de761f6fde0644ec7cf051d5fb1dc7482ed3b96ff524"
)
_BASE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
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
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_DEPENDENCY_LOCK_SHA256 = (
    "c81a9831ec545b2d7797e1c0951ad46e0e23337b97866ced0ae27e290dfd71ff"
)
_FROZEN_REPLAY_SHA256 = (
    "5d41d31ee79cd0d6d203cd774267fd504d06fe7662768486f99c31a7902b8a3f"
)
_IMPLEMENTATION_DECISION_SHA256 = (
    "83d14670abac952ce0d0e873cc8c3bdd37b971dddcbfc285c07594184863c75e"
)
_REPAIR_IDENTITY_REVIEW_SHA256 = (
    "5e5bf04abfb11fe0833fdaefec23291ad7a2ee32c52b1fd68687d4f3fadb7cd5"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "69c66e0b87c08a7b6b99e6d252c3a798d9133622b7903e8d746dd9c0f0f4f42d"
)
_REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256 = (
    "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
)
_REFERENCE_REPAIR_PRE_REVIEW_SHA256 = (
    "d169ab9a8f040a78ac5995de6ae488444b42270895e103c7ce9dd67671ece02d"
)
_REFERENCE_REPAIR_IMPLEMENTATION_DECISION_SHA256 = (
    "76477b31d8fb1392be45c97d60fa30f5e2e29c36dd2c8e88966f3eb311a6f352"
)
_COMPATIBILITY_CONTAINER_DIGEST = (
    "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1"
)
_COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
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
)
_SHA256_HEX_LENGTH = 64


def _load_frozen_replay() -> dict[str, Any]:
    """Load the checksum-bound historical machinery without executing it."""
    if file_sha256(_FROZEN_REPLAY) != _FROZEN_REPLAY_SHA256:
        raise ValueError("frozen cumulative replay identity changed")
    root = str(_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    module = importlib.import_module(
        "scripts.validation.review_phase5_cumulative_regressions"
    )
    module = importlib.reload(module)
    if Path(cast(str, module.__file__)).resolve() != _FROZEN_REPLAY.resolve():
        raise ValueError("frozen cumulative replay path changed")
    return vars(module)


def _candidate_configuration_sha256() -> str:
    """Return the exact approved public-finder correction composition."""
    configuration = public_finder_correction_candidate_configuration(
        _BASE_REVIEW,
        _CORRECTION_CONTRACT,
    )
    identity = canonical_sha256(configuration)
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("candidate correction configuration identity changed")
    return identity


def _candidate_runtime_identity(revision: str) -> ExternalRuntimeIdentity:
    """Separate the source overlay from its inherited dependency runtime."""
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
    """Install only the approved candidate identity and Continuum builder."""
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


def _historical_reconstruction_source_tree(_root: Path) -> str:
    """Return the immutable source identity that produced the references."""
    return _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256


def _install_reference_producer_view(
    reconstruction: dict[str, Any],
) -> None:
    """Scope the historical producer identity to both verifier checks."""
    verifier = reconstruction.get("verify_viewed_reference_reconstruction")
    if not callable(verifier) or not hasattr(verifier, "__globals__"):
        raise ValueError("reference reconstruction verifier seam changed")
    verifier_globals = verifier.__globals__
    original_helpers = verifier_globals.get("_helpers")
    if not callable(original_helpers):
        raise ValueError("reference reconstruction helper seam changed")

    def helpers() -> dict[str, Any]:
        namespace_value = original_helpers()
        if not isinstance(namespace_value, dict):
            raise ValueError("reference reconstruction helper seam changed")
        namespace = cast(dict[str, Any], namespace_value)
        loader = namespace.get("load_viewed_recovery_execution_decision")
        if not callable(loader) or not hasattr(loader, "__globals__"):
            raise ValueError("reference reconstruction helper seam changed")
        loader_globals = loader.__globals__
        loader_globals["source_tree_sha256"] = (
            _historical_reconstruction_source_tree
        )
        return namespace

    verifier_globals["_helpers"] = helpers
    verifier_globals["source_tree_sha256"] = (
        _historical_reconstruction_source_tree
    )


class _ReferenceProducerRunpy:
    """Delegate runpy while exposing one already verified reference view."""

    def __init__(self, delegate: Any, verified: Any | None) -> None:
        self._delegate = delegate
        self._verified = verified

    def run_path(
        self,
        path_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Patch only the frozen reconstruction verifier namespace."""
        namespace_value = self._delegate.run_path(
            path_name,
            *args,
            **kwargs,
        )
        if not isinstance(namespace_value, dict):
            raise ValueError("frozen runpy namespace changed")
        namespace = cast(dict[str, Any], namespace_value)
        if Path(path_name).resolve() != _REFERENCE_VERIFIER.resolve():
            return namespace
        _install_reference_producer_view(namespace)
        if self._verified is not None:
            verified = self._verified

            def return_verified(*_args: Any, **_kwargs: Any) -> Any:
                return verified

            namespace["verify_viewed_reference_reconstruction"] = (
                return_verified
            )
        return namespace


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Install the correction seams in each spawned candidate worker."""
    frozen = _load_frozen_replay()
    _install_static_science_seams(frozen)
    return cast(str, frozen["_generate_candidate_product"](task))


def _install_repair_composition(
    frozen: dict[str, Any],
    provenance: dict[str, object],
    *,
    verified_reference: Any | None = None,
) -> None:
    """Compose the approved repair around unchanged frozen machinery."""
    _install_static_science_seams(frozen)
    frozen["_generate_candidate_product"] = _generate_candidate_product
    frozen["runpy"] = _ReferenceProducerRunpy(
        frozen["runpy"],
        verified_reference,
    )
    original_serializer = frozen["_canonical_json_bytes"]

    def serialize(value: object) -> bytes:
        document = value
        mapping = (
            cast(dict[object, object], value)
            if isinstance(value, dict)
            else None
        )
        if mapping is not None and mapping.get("ledger_id") == (
            "phase-5-cumulative-regression-ledger"
        ):
            document = {
                **mapping,
                "replay_repair_provenance": provenance,
            }
        return cast(bytes, original_serializer(document))

    frozen["_canonical_json_bytes"] = serialize


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity a future named approval must bind."""
    return {
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "correction_contract_sha256": _CORRECTION_CONTRACT_SHA256,
        "base_review_sha256": _BASE_REVIEW_SHA256,
        "compiler_sha256": _COMPILER_SHA256,
        "evaluator_sha256": _EVALUATOR_SHA256,
        "reference_verifier_sha256": _REFERENCE_VERIFIER_SHA256,
        "endpoint_registry_sha256": _ENDPOINT_REGISTRY_SHA256,
        "evaluation_contract_sha256": _EVALUATION_CONTRACT_SHA256,
        "viewed_request_sha256": _VIEWED_REQUEST_SHA256,
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "dependency_lock_sha256": _DEPENDENCY_LOCK_SHA256,
        "historical_replay_sha256": _FROZEN_REPLAY_SHA256,
        "implementation_decision_sha256": _IMPLEMENTATION_DECISION_SHA256,
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "reference_reconstruction_producer_source_tree_sha256": (
            _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256
        ),
        "reference_repair_pre_review_sha256": (
            _REFERENCE_REPAIR_PRE_REVIEW_SHA256
        ),
        "reference_repair_implementation_decision_sha256": (
            _REFERENCE_REPAIR_IMPLEMENTATION_DECISION_SHA256
        ),
        "compatibility_container_digest": _COMPATIBILITY_CONTAINER_DIGEST,
        "compatibility_dependency_inventory_sha256": (
            _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
        ),
        "wrapper_sha256": file_sha256(Path(__file__)),
        "output_path": str(arguments.output),
        "scratch_path": str(arguments.scratch),
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "closed_baseline_path": str(
            arguments.closed_component_baseline_ledger
        ),
        "workers": arguments.workers,
    }


def _validate_execution_decision(
    document: dict[str, object],
    arguments: argparse.Namespace,
) -> None:
    """Reject every unapproved or drifted execution field."""
    if document.get("status") != (
        "reviewed-before-public-finder-correction-cumulative-replay"
    ):
        raise ValueError("cumulative replay is not authorized")
    if (
        document.get("execution_authorized") is not True
        or document.get("cumulative_replay_authorized") is not True
    ):
        raise ValueError("cumulative replay is not authorized")
    expected = _expected_execution_fields(arguments)
    for field, value in expected.items():
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
    review_value = document.get("reference_repair_identity_review")
    review = (
        cast(dict[object, object], review_value)
        if isinstance(review_value, dict)
        else None
    )
    if review is None or review.get("path") != str(
        _REFERENCE_REPAIR_IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError(
            "cumulative replay reference repair review identity changed"
        )
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or len(review_sha256) != _SHA256_HEX_LENGTH
    ):
        raise ValueError(
            "cumulative replay reference repair review identity changed"
        )


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
    """Require one exact existing evidence or program file."""
    if not path.is_file() or file_sha256(path) != expected:
        raise ValueError(f"cumulative replay {label} identity changed")


def _require_common_replay_identities(
    arguments: argparse.Namespace,
) -> str:
    """Verify every shared source, program, evidence, and write-once bound."""
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
        (_DEPENDENCY_LOCK, _DEPENDENCY_LOCK_SHA256, "dependency lock"),
        (
            _IMPLEMENTATION_DECISION,
            _IMPLEMENTATION_DECISION_SHA256,
            "implementation decision",
        ),
        (
            _REPAIR_IDENTITY_REVIEW,
            _REPAIR_IDENTITY_REVIEW_SHA256,
            "predecessor repair review",
        ),
        (
            _REFERENCE_REPAIR_PRE_REVIEW,
            _REFERENCE_REPAIR_PRE_REVIEW_SHA256,
            "reference repair pre-review",
        ),
        (
            _REFERENCE_REPAIR_IMPLEMENTATION_DECISION,
            _REFERENCE_REPAIR_IMPLEMENTATION_DECISION_SHA256,
            "reference repair implementation decision",
        ),
        (_FROZEN_REPLAY, _FROZEN_REPLAY_SHA256, "historical program"),
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
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("cumulative replay write-once output state changed")
    return execution_revision


def _validate_reference_repair_implementation_decision(
    document: dict[str, object],
    arguments: argparse.Namespace,
) -> None:
    """Validate the named repair approval without authorizing a replay."""
    if document.get("status") != (
        "reviewed-before-reference-provenance-repair-implementation"
    ):
        raise ValueError("reference provenance repair is not authorized")
    authorization_value = document.get("authorization")
    authorization = (
        cast(dict[object, object], authorization_value)
        if isinstance(authorization_value, dict)
        else None
    )
    expected_authorization = {
        "campaign_execution_authorized": False,
        "complete_no_write_reference_verification_authorized": True,
        "cumulative_replay_authorized": False,
        "cutover_authorized": False,
        "fresh_qualification_authorized": False,
        "identity_freeze_authorized": True,
        "implementation_authorized": True,
        "optimization_authorized": False,
        "public_development_execution_authorized": False,
        "release_authorized": False,
        "rescoring_authorized": False,
        "tuning_authorized": False,
    }
    if authorization != expected_authorization:
        raise ValueError("reference provenance repair boundary changed")
    pre_review = document.get("pre_review")
    if pre_review != {
        "path": str(_REFERENCE_REPAIR_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": _REFERENCE_REPAIR_PRE_REVIEW_SHA256,
    }:
        raise ValueError("reference provenance repair pre-review changed")
    scope_value = document.get("scope")
    scope = (
        cast(dict[object, object], scope_value)
        if isinstance(scope_value, dict)
        else None
    )
    if scope is None or (
        scope.get("candidate_source_tree_sha256")
        != _CANDIDATE_SOURCE_TREE_SHA256
        or scope.get("historical_reconstruction_producer_source_tree_sha256")
        != _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256
        or scope.get("prospective_scratch_path") != str(arguments.scratch)
        or scope.get("required_result")
        != "validated-non-executable-repair-and-replacement-identity-review"
    ):
        raise ValueError("reference provenance repair scope changed")


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Fully verify sealed references under their producer source identity."""
    frozen = _load_frozen_replay()
    compiler = runpy.run_path(str(_COMPILER))
    frozen["_install_historical_source_view"](compiler)
    terminal = compiler["_configured_terminal"]()
    compiler_globals = terminal["compile_terminal_analysis"].__globals__
    request_model = compiler_globals["CampaignRequest"]
    original_request = request_model.model_validate_json(
        _VIEWED_REQUEST.read_text(encoding="utf-8")
    )
    reconstruction = runpy.run_path(str(_REFERENCE_VERIFIER))
    _install_reference_producer_view(reconstruction)
    return reconstruction["verify_viewed_reference_reconstruction"](
        arguments.reference_reconstruction,
        original_request=original_request,
        verified_run_type=compiler_globals["VerifiedRun"],
    )


def verify_reference_repair(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Run the authorized complete no-write reference verification."""
    if not implementation_decision_path.is_file():
        raise ValueError("reference provenance repair is not authorized")
    value = json.loads(
        implementation_decision_path.read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise ValueError("reference provenance repair is not authorized")
    _validate_reference_repair_implementation_decision(
        cast(dict[str, object], value),
        arguments,
    )
    execution_revision = _require_common_replay_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
    return {
        "status": "pass",
        "execution_checkout_revision": execution_revision,
        "candidate_consumer_source_tree_sha256": (
            _CANDIDATE_SOURCE_TREE_SHA256
        ),
        "reference_producer_source_tree_sha256": (
            _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256
        ),
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "verified_input_count": len(verified.inputs),
        "verified_reference_run_count": len(verified.runs),
    }


def _authorize_replay(
    arguments: argparse.Namespace,
    execution_decision_path: Path,
) -> dict[str, object]:
    """Validate authorization and identities before scientific input access."""
    if not execution_decision_path.is_file():
        raise ValueError("cumulative replay is not authorized")
    document_value = json.loads(
        execution_decision_path.read_text(encoding="utf-8")
    )
    if not isinstance(document_value, dict):
        raise ValueError("cumulative replay is not authorized")
    document = cast(dict[str, object], document_value)
    _validate_execution_decision(document, arguments)
    execution_revision = _require_common_replay_identities(arguments)
    review = cast(dict[str, str], document["reference_repair_identity_review"])
    _require_file_identity(
        _REFERENCE_REPAIR_IDENTITY_REVIEW,
        review["sha256"],
        "reference repair review",
    )
    return {
        "candidate_source_overlay_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "correction_contract_sha256": _CORRECTION_CONTRACT_SHA256,
        "base_review_sha256": _BASE_REVIEW_SHA256,
        "compiler_sha256": _COMPILER_SHA256,
        "evaluator_sha256": _EVALUATOR_SHA256,
        "reference_verifier_sha256": _REFERENCE_VERIFIER_SHA256,
        "endpoint_registry_sha256": _ENDPOINT_REGISTRY_SHA256,
        "evaluation_contract_sha256": _EVALUATION_CONTRACT_SHA256,
        "viewed_request_sha256": _VIEWED_REQUEST_SHA256,
        "dependency_lock_sha256": _DEPENDENCY_LOCK_SHA256,
        "historical_replay_sha256": _FROZEN_REPLAY_SHA256,
        "wrapper_sha256": file_sha256(Path(__file__)),
        "reference_repair_identity_review_sha256": review["sha256"],
        "reference_repair_pre_review_sha256": (
            _REFERENCE_REPAIR_PRE_REVIEW_SHA256
        ),
        "reference_repair_implementation_decision_sha256": (
            _REFERENCE_REPAIR_IMPLEMENTATION_DECISION_SHA256
        ),
        "reference_reconstruction_producer_source_tree_sha256": (
            _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256
        ),
        "execution_decision_sha256": file_sha256(execution_decision_path),
        "execution_checkout_revision": execution_revision,
        "runtime_binding": {
            "source_role": "exact-candidate-source-overlay",
            "container_role": "inherited-compatibility-dependency-reference",
            "correction_baked_into_container": False,
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
    """Delegate once to the frozen replay after complete authorization."""
    provenance = _authorize_replay(arguments, execution_decision_path)
    verified_reference = _verify_reference_reconstruction(arguments)
    frozen = _load_frozen_replay()
    _install_repair_composition(
        frozen,
        provenance,
        verified_reference=verified_reference,
    )
    frozen["_parse_args"] = lambda: arguments
    frozen["main"]()


def _parse_args() -> argparse.Namespace:
    """Parse one exact reconstructed-reference replay invocation."""
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
    """Run the replay only after a future exact named approval."""
    run_authorized_replay(
        _parse_args(),
        execution_decision_path=_EXECUTION_DECISION,
    )


if __name__ == "__main__":
    main()
