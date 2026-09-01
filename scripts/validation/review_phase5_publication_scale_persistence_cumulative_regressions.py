#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify or run the frozen publication-scale-persistence replay."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.terminal_feature_persistence_evaluation import (
    aggregate_terminal_feature_persistence,
)

_ROOT = Path(__file__).parents[2]
_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_publication_scale_persistence_products.py"
)
_SMOKE_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_publication_scale_persistence_smoke.py"
)
_SMOKE = (
    _ROOT / "benchmark-results/phase-5/"
    "prospective-science-smoke-publication-scale-persistence.json"
)
_REFERENCE_VERIFIER = (
    _ROOT / "scripts/validation/reconstruct_phase5_viewed_references.py"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-cumulative-replay-reference-"
    "dispatch-repair-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-cumulative-replay-reference-"
    "dispatch-repair-execution-decision.json"
)
_ORIGINAL_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-cumulative-replay-execution-"
    "decision.json"
)

_CANDIDATE_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_CANDIDATE_PRODUCT_SET_SHA256 = (
    "86f703dc55601f0a8f496b6308585252bc154ce4721b696064d604751ca46b37"
)
_MATERIALIZER_SHA256 = (
    "40486cfbbe029b53aaeba74b4640b5851dd6bd15d2739d4d76f2ba5af406f7b1"
)
_SMOKE_EVALUATOR_SHA256 = (
    "f17aea97cbaf83c87a7e776e3eff9dd9d9eb78fda3fab10097af98c9a96af68d"
)
_SMOKE_SHA256 = (
    "9316882c606f66bcbf8937c4fc3f5aea331bb9ab9e8689953026016566bd9855"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256 = (
    "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
)
_ORIGINAL_EXECUTION_DECISION_SHA256 = (
    "65e9654902503c1bbbc67336853c85a1cea3800d3240f4e409cc900c0e9639d2"
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
    "publication-scale-persistence.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-publication-scale-persistence-"
    "937737d"
)
_PROSPECTIVE_BASELINE_PATH = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_CONTINUUM_COUNT = 1600
_PROHIBITED_AUTHORIZATIONS = (
    "cutover_authorized",
    "fresh_qualification_authorized",
    "optimization_authorized",
    "release_authorized",
    "rescoring_authorized",
    "threshold_or_photometric_tuning_authorized",
    "viewed_sdc1_hydra_execution_authorized",
)


def _load_json(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, object], value)


def _load_materializer() -> dict[str, Any]:
    """Load the exact smoke-proven candidate composition."""
    if file_sha256(_MATERIALIZER) != _MATERIALIZER_SHA256:
        raise ValueError("publication-scale-persistence materializer changed")
    return runpy.run_path(str(_MATERIALIZER))


def _candidate_configuration_sha256() -> str:
    """Return the exact smoke-proven configuration identity."""
    identity = cast(str, _load_materializer()["_current_configuration"](_ROOT))
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("publication-scale-persistence configuration changed")
    return identity


def _marker_association_path(directory: Path) -> Path | None:
    """Verify one completed product and return its association sidecar."""
    marker = _load_json(directory / "complete.json", label="candidate marker")
    if (
        marker.get("input_id") != directory.name
        or marker.get("configuration_sha256")
        != _CANDIDATE_CONFIGURATION_SHA256
        or marker.get("source_tree_sha256") != _CANDIDATE_SOURCE_TREE_SHA256
    ):
        raise ValueError("candidate product identity changed")
    artifacts = marker.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("candidate product artifacts are malformed")
    matches: list[Path] = []
    for value in artifacts:
        if not isinstance(value, dict):
            raise ValueError("candidate product artifact is malformed")
        artifact = cast(Mapping[str, object], value)
        if artifact.get("role") != "source-association-json":
            continue
        relative_value = artifact.get("relative_path")
        if not isinstance(relative_value, str):
            raise ValueError("candidate association path is malformed")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("candidate association path is unsafe")
        path = directory / relative
        byte_count = artifact.get("byte_count")
        sha256 = artifact.get("sha256")
        if (
            type(byte_count) is not int
            or not isinstance(sha256, str)
            or not path.is_file()
            or path.stat().st_size != byte_count
            or file_sha256(path) != sha256
        ):
            raise ValueError("candidate association identity changed")
        matches.append(path)
    if len(matches) > 1:
        raise ValueError("candidate product contains duplicate associations")
    return matches[0] if matches else None


def _aggregate_completed_sidecars(scratch: Path) -> dict[str, int]:
    """Aggregate only the exact new candidate's 1,600 sidecars."""
    products = scratch / "products"
    if not products.is_dir():
        raise ValueError("candidate products are absent")
    entries = tuple(sorted(products.iterdir()))
    if len(entries) != _EXPECTED_INPUT_COUNT or any(
        not path.is_dir() for path in entries
    ):
        raise ValueError("candidate product count differs")
    sidecars = tuple(
        sidecar
        for directory in entries
        if (sidecar := _marker_association_path(directory)) is not None
    )
    return aggregate_terminal_feature_persistence(
        sidecars,
        expected_image_count=_EXPECTED_CONTINUUM_COUNT,
    )


def _serialize_ledger(value: object) -> bytes:
    """Serialize finite evidence with exact prospective provenance."""
    document = value
    if isinstance(value, dict) and value.get("ledger_id") == (
        "phase-5-cumulative-regression-ledger"
    ):
        document = {
            **value,
            "publication_scale_persistence_provenance": {
                "candidate_smoke_sha256": _SMOKE_SHA256,
                "identity_review_sha256": file_sha256(_IDENTITY_REVIEW),
                "execution_decision_sha256": file_sha256(_EXECUTION_DECISION),
                "original_execution_decision_sha256": (
                    _ORIGINAL_EXECUTION_DECISION_SHA256
                ),
                "materializer_sha256": _MATERIALIZER_SHA256,
                "smoke_evaluator_sha256": _SMOKE_EVALUATOR_SHA256,
                "tradeoff_policy": (
                    "fixed-practical-margin-with-absolute-and-pybdsf-gates"
                ),
            },
            "terminal_feature_persistence_diagnostics": (
                _aggregate_completed_sidecars(_PROSPECTIVE_SCRATCH_PATH)
            ),
        }
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _current_composition() -> dict[str, Any]:
    """Build the exact candidate and replace the stale serializer seam."""
    materializer = _load_materializer()
    frozen = cast(
        dict[str, Any],
        materializer["_current_composition"](
            _ROOT,
            revision=_CANDIDATE_REVISION,
            configuration=_candidate_configuration_sha256(),
        ),
    )
    frozen["_canonical_json_bytes"] = _serialize_ledger
    frozen["_git_revision"] = _git_revision
    frozen["runpy"] = _ReferenceProducerRunpy(frozen["runpy"])
    return frozen


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Reinstall the exact candidate inside each spawned worker."""
    frozen = _current_composition()
    return cast(str, frozen["_generate_candidate_product"](task))


def _historical_reconstruction_source_tree(_root: Path) -> str:
    """Return the immutable source identity that produced the references."""
    return _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256


def _install_reference_producer_view(
    reconstruction: dict[str, Any],
) -> None:
    """Scope the historical identity to both retained-reference checks."""
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
        loader.__globals__["source_tree_sha256"] = (
            _historical_reconstruction_source_tree
        )
        return namespace

    verifier_globals["_helpers"] = helpers
    verifier_globals["source_tree_sha256"] = (
        _historical_reconstruction_source_tree
    )


class _ReferenceProducerRunpy:
    """Patch only the retained-reference verifier loaded by frozen code."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def run_path(
        self,
        path_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Load a namespace and scope producer identity when required."""
        namespace_value = self._delegate.run_path(
            path_name,
            *args,
            **kwargs,
        )
        if not isinstance(namespace_value, dict):
            raise ValueError("frozen runpy namespace changed")
        namespace = cast(dict[str, Any], namespace_value)
        if Path(path_name).resolve() == _REFERENCE_VERIFIER.resolve():
            _install_reference_producer_view(namespace)
        return namespace


def _verify_reference_dispatch_seams(frozen: dict[str, Any]) -> None:
    """Exercise both historical source checks without reading products."""
    reconstruction = frozen["runpy"].run_path(str(_REFERENCE_VERIFIER))
    verifier = reconstruction.get("verify_viewed_reference_reconstruction")
    if not callable(verifier) or not hasattr(verifier, "__globals__"):
        raise ValueError("reference reconstruction verifier seam changed")
    verifier_globals = verifier.__globals__
    helpers = verifier_globals["_helpers"]()
    loader = helpers["load_viewed_recovery_execution_decision"]
    observed = (
        verifier_globals["source_tree_sha256"](_ROOT),
        loader.__globals__["source_tree_sha256"](_ROOT),
    )
    if observed != (
        _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256,
        _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256,
    ):
        raise ValueError("reference reconstruction producer view changed")


def _git_revision() -> str:
    """Return the clean immutable execution revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError(
            "publication-scale-persistence replay requires clean source"
        )
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require the one reviewed two-worker write-once namespace."""
    expected = {
        "reference_reconstruction": _PROSPECTIVE_REFERENCE_PATH,
        "output": _PROSPECTIVE_OUTPUT_PATH,
        "scratch": _PROSPECTIVE_SCRATCH_PATH,
        "closed_component_baseline_ledger": _PROSPECTIVE_BASELINE_PATH,
        "workers": 2,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(
                f"publication-scale-persistence replay {field} changed"
            )


def _validate_smoke() -> None:
    """Require the exact terminal zero-failure smoke before full replay."""
    if file_sha256(_SMOKE) != _SMOKE_SHA256:
        raise ValueError("publication-scale-persistence smoke changed")
    smoke = _load_json(_SMOKE, label="publication-scale-persistence smoke")
    decisions = smoke.get("decisions")
    if (
        smoke.get("candidate_revision") != _CANDIDATE_REVISION
        or smoke.get("candidate_source_tree_sha256")
        != _CANDIDATE_SOURCE_TREE_SHA256
        or smoke.get("candidate_configuration_sha256")
        != _CANDIDATE_CONFIGURATION_SHA256
        or smoke.get("candidate_product_set_canonical_sha256")
        != _CANDIDATE_PRODUCT_SET_SHA256
        or smoke.get("terminal_failure_count") != 0
        or smoke.get("compact_product_identity_equal") is not True
        or not isinstance(decisions, list)
        or any(
            isinstance(value, dict) and value.get("status") == "fail"
            for value in decisions
        )
    ):
        raise ValueError(
            "publication-scale-persistence smoke did not open replay"
        )


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity authorized for one cumulative replay."""
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "candidate_smoke_sha256": _SMOKE_SHA256,
        "closed_baseline_path": str(
            arguments.closed_component_baseline_ledger
        ),
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "materializer_sha256": _MATERIALIZER_SHA256,
        "original_execution_decision_sha256": (
            _ORIGINAL_EXECUTION_DECISION_SHA256
        ),
        "output_path": str(arguments.output),
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "reference_reconstruction_sha256": _REFERENCE_RECONSTRUCTION_SHA256,
        "reference_reconstruction_producer_source_tree_sha256": (
            _REFERENCE_RECONSTRUCTION_PRODUCER_SOURCE_TREE_SHA256
        ),
        "scratch_path": str(arguments.scratch),
        "smoke_evaluator_sha256": _SMOKE_EVALUATOR_SHA256,
        "workers": arguments.workers,
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify exact candidate, evidence, paths, and absent write-once state."""
    _require_exact_invocation(arguments)
    revision = _git_revision()
    if source_tree_sha256(_ROOT) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("publication-scale-persistence source tree changed")
    if _candidate_configuration_sha256() != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("publication-scale-persistence configuration changed")
    for path, expected, label in (
        (_MATERIALIZER, _MATERIALIZER_SHA256, "materializer"),
        (_SMOKE_EVALUATOR, _SMOKE_EVALUATOR_SHA256, "smoke evaluator"),
        (_SMOKE, _SMOKE_SHA256, "smoke"),
        (
            _ORIGINAL_EXECUTION_DECISION,
            _ORIGINAL_EXECUTION_DECISION_SHA256,
            "original execution decision",
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
            raise ValueError(f"publication-scale-persistence {label} changed")
    _validate_smoke()
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("publication-scale-persistence output state changed")
    return revision


def verify_replay(arguments: argparse.Namespace) -> dict[str, object]:
    """Perform complete no-write verification including executable seams."""
    _require_reviewed_authority(arguments)
    execution_revision = _require_common_identities(arguments)
    verified, _ = _load_materializer()["_verified_reference"](
        _ROOT, arguments.reference_reconstruction
    )
    frozen = _current_composition()
    if (
        frozen["_write_continuum_products"].__name__ != "write_mask_separated"
        or frozen["_install_prospective_compiler"].__name__
        != "install_terminal_cycle"
        or frozen["_canonical_json_bytes"] is not _serialize_ledger
        or frozen["_git_revision"] is not _git_revision
        or not isinstance(frozen["runpy"], _ReferenceProducerRunpy)
        or not callable(frozen.get("_generate_candidate_product"))
    ):
        raise ValueError("publication-scale-persistence composition changed")
    _verify_reference_dispatch_seams(frozen)
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "execution_checkout_revision": execution_revision,
        "output_absent": not arguments.output.exists(),
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "scratch_absent": not arguments.scratch.exists(),
        "status": "pass",
        "verified_input_count": len(verified.inputs),
        "verified_reference_run_count": len(verified.runs),
    }


def _require_reviewed_authority(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Verify the review and user's exact authority without writes."""
    decision = _load_json(_EXECUTION_DECISION, label="execution decision")
    expected = canonical_sha256(_expected_execution_fields(arguments))
    if (
        decision.get("status")
        != "authorized-for-one-publication-scale-persistence-cumulative-replay"
        or decision.get("cumulative_replay_authorized") is not True
        or decision.get("execution_authorized") is not True
        or decision.get("expected_execution_sha256") != expected
        or decision.get("prohibited_authorizations")
        != dict.fromkeys(_PROHIBITED_AUTHORIZATIONS, False)
    ):
        raise ValueError("publication-scale-persistence replay not authorized")
    review = decision.get("identity_review")
    if (
        not isinstance(review, dict)
        or review.get("path") != str(_IDENTITY_REVIEW.relative_to(_ROOT))
        or review.get("sha256") != file_sha256(_IDENTITY_REVIEW)
    ):
        raise ValueError("publication-scale-persistence review changed")
    return {
        "execution_decision_sha256": file_sha256(_EXECUTION_DECISION),
        "identity_review_sha256": file_sha256(_IDENTITY_REVIEW),
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def _authorize_replay(arguments: argparse.Namespace) -> dict[str, object]:
    """Authorize only the exact reviewed replay after complete verification."""
    authority = _require_reviewed_authority(arguments)
    execution_revision = _require_common_identities(arguments)
    return {**authority, "execution_checkout_revision": execution_revision}


def run_authorized_replay(arguments: argparse.Namespace) -> None:
    """Execute and evaluate exactly one fully verified cumulative replay."""
    _authorize_replay(arguments)
    frozen = _current_composition()
    frozen["_generate_candidate_product"] = _generate_candidate_product
    frozen["_git_revision"] = _git_revision
    temporary = arguments.output.with_name(
        f".{arguments.output.name}.{uuid4().hex}.tmp"
    )
    execution_arguments = argparse.Namespace(**vars(arguments))
    execution_arguments.output = temporary
    frozen["_parse_args"] = lambda: execution_arguments
    frozen["main"]()
    os.link(temporary, arguments.output)
    temporary.unlink()


def _parse_args() -> argparse.Namespace:
    """Parse the exact prospective replay invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--closed-component-baseline-ledger", required=True, type=Path
    )
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.campaign = None
    return arguments


def main() -> None:
    """Verify without writes or execute the exact authorized replay."""
    arguments = _parse_args()
    if arguments.verify_only:
        print(json.dumps(verify_replay(arguments), sort_keys=True))
        return
    run_authorized_replay(arguments)


if __name__ == "__main__":
    main()
