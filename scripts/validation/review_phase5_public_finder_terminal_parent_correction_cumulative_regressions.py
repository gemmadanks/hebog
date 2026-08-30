#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify or run only the frozen terminal-parent cumulative replay."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import (
    ExternalRuntimeIdentity,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.parent_construction_association_evaluation import (
    install_parent_construction_association_evaluation,
    source_association_from_json,
)
from hebog.validation.public_finder_correction import (
    build_public_finder_source_reconstruction_continuum_products,
    public_finder_terminal_parent_correction_configuration,
)

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_hierarchy_"
    "parent_construction_cumulative_regressions.py"
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
_TERMINAL_PARENT_REVIEW = (
    _ROOT / "docs/reference/phase-5-public-finder-persistent-support-parent-"
    "correction.md"
)
_TERMINAL_PARENT_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-parent-"
    "correction-implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-parent-"
    "correction-cumulative-replay-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-parent-"
    "correction-cumulative-replay-execution-decision.json"
)
_CANDIDATE_PROGRAM = _ROOT / "src/hebog/validation/public_finder_correction.py"
_EVALUATOR_PROGRAM = (
    _ROOT / "src/hebog/validation/"
    "parent_construction_association_evaluation.py"
)

_CANDIDATE_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
)
_CONSUMED_WRAPPER_SHA256 = (
    "053fc6479d75a9f11e97cc2ec6f7de41610c5c03083bd81ce01ca47ef104c8d7"
)
_TERMINAL_PARENT_REVIEW_SHA256 = (
    "fe528316afbdde27fbdf481aeac57dfc8b6146b2addf56e7880e1447717531c0"
)
_TERMINAL_PARENT_IMPLEMENTATION_DECISION_SHA256 = (
    "88083eb3de4ab595b2f8519d1a896f65cf83161ce7abe96a87c575fd9692d26c"
)
_READINESS_SHA256 = (
    "fb295c16b5a67618b242891dc048c4290b88ff8ceaecf81a7ad409b015f8c137"
)
_CANDIDATE_PROGRAM_SHA256 = (
    "1e9483fc033f6e78987b90aafb8a67302071a53e622376d368d229c2cbcee3c0"
)
_EVALUATOR_PROGRAM_SHA256 = (
    "74d16cc49f65bf5a353acc67a830dd2d175b8be2635062cca64581cfaa966962"
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
    "public-finder-terminal-parent-correction.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-terminal-parent-"
    "correction-85d5807"
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
    """Load the exact historical parent wrapper without executing it."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed parent-construction wrapper changed")
    return runpy.run_path(str(_CONSUMED_WRAPPER))


def _load_source_association_composition() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any]
]:
    """Use the predecessor's already-reviewed overlay descent."""
    return cast(
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
        _load_consumed_wrapper()["_load_source_association_composition"](),
    )


def _candidate_configuration_sha256() -> str:
    """Return the exact terminal-parent candidate configuration identity."""
    configuration = public_finder_terminal_parent_correction_configuration(
        _BASE_REVIEW,
        _CORRECTION_CONTRACT,
        _SOURCE_RECONSTRUCTION_PRE_REVIEW,
        _SOURCE_RECONSTRUCTION_DECISION,
        _ROOT_CAUSE_PRE_REVIEW,
        _ROOT_CAUSE_DECISION,
        _PARENT_PRE_REVIEW,
        _PARENT_IMPLEMENTATION_DECISION,
        _TERMINAL_PARENT_REVIEW,
        _TERMINAL_PARENT_IMPLEMENTATION_DECISION,
    )
    identity = canonical_sha256(configuration)
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("terminal-parent configuration changed")
    return identity


def _candidate_runtime_identity(revision: str) -> ExternalRuntimeIdentity:
    """Bind the corrected source overlay to unchanged runtime dependencies."""
    if revision != _CANDIDATE_REVISION:
        raise ValueError("terminal-parent candidate revision changed")
    return ExternalRuntimeIdentity(
        name="hebog-source-overlay",
        version="0.6.0",
        source_revision=revision,
        container_image_digest=_COMPATIBILITY_CONTAINER_DIGEST,
        dependency_inventory_sha256=(
            _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
        ),
    )


def _association_artifact_path(run: Any) -> Path:
    """Resolve exactly one safe association sidecar from a candidate run."""
    matches = tuple(
        artifact
        for artifact in run.result.artifacts
        if getattr(artifact, "role", None) == "source-association-json"
    )
    if len(matches) != 1:
        raise ValueError("candidate run must contain exactly one association")
    relative = Path(cast(str, matches[0].relative_path))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("candidate association path must be relative")
    return cast(Path, run.directory) / relative


def _install_terminal_parent_static_seams(frozen: dict[str, Any]) -> None:
    """Install the corrected candidate, sidecar writer, and evaluator."""
    consumed = _load_consumed_wrapper()
    consumed["_install_parent_construction_static_seams"](frozen)
    frozen["_CANDIDATE_REVISION"] = _CANDIDATE_REVISION
    frozen["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"] = (
        _CLOSED_BASELINE_SHA256
    )
    frozen["_candidate_configuration_sha256"] = _candidate_configuration_sha256
    frozen["_candidate_runtime_identity"] = _candidate_runtime_identity

    original_writer = frozen["_write_continuum_products"]
    writer_globals = original_writer.__globals__

    def _write_terminal_continuum_products(
        *args: object, **kwargs: object
    ) -> dict[str, Path]:
        captured: list[object] = []

        def capture_products(
            *builder_args: object, **builder_kwargs: object
        ) -> object:
            builder = cast(
                Callable[..., Any],
                build_public_finder_source_reconstruction_continuum_products,
            )
            products = builder(*builder_args, **builder_kwargs)
            captured.append(products)
            return products

        sentinel = object()
        previous = writer_globals.get(
            "build_post_correction_continuum_products", sentinel
        )
        writer_globals["build_post_correction_continuum_products"] = (
            capture_products
        )
        try:
            paths = cast(dict[str, Path], original_writer(*args, **kwargs))
        finally:
            if previous is sentinel:
                writer_globals.pop(
                    "build_post_correction_continuum_products", None
                )
            else:
                writer_globals["build_post_correction_continuum_products"] = (
                    previous
                )
        if len(captured) != 1:
            raise ValueError("candidate writer must build exactly one product")
        association = getattr(captured[0], "source_association", None)
        if association is None:
            raise ValueError("candidate source association is unavailable")
        document = asdict(association)
        payload = frozen["_canonical_json_bytes"](document)
        source_association_from_json(json.loads(payload))
        output = cast(Path, kwargs["output"])
        sidecar = output / "source_association.json"
        with sidecar.open("xb") as stream:
            stream.write(payload)
        return {**paths, "source-association-json": sidecar}

    original_installer = frozen["_install_prospective_compiler"]

    def _install_terminal_parent_compiler(
        compiler_globals: dict[str, Any],
        prospective: Any,
        configuration_sha256: str,
    ) -> None:
        original_installer(compiler_globals, prospective, configuration_sha256)
        install_parent_construction_association_evaluation(
            compiler_globals,
            association_path=_association_artifact_path,
        )

    frozen["_write_continuum_products"] = _write_terminal_continuum_products
    frozen["_install_prospective_compiler"] = _install_terminal_parent_compiler


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Reinstall the exact terminal composition in each spawned worker."""
    _, _, frozen = _load_source_association_composition()
    _install_terminal_parent_static_seams(frozen)
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
            raise ValueError(f"terminal-parent replay {field} changed")


def _git_revision() -> str:
    """Return the clean wrapper checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("terminal-parent replay requires clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _validate_readiness() -> None:
    """Require readiness to name only the corrected prospective evidence."""
    if file_sha256(_READINESS) != _READINESS_SHA256:
        raise ValueError("terminal-parent readiness identity changed")
    document = _load_json(_READINESS, label="readiness contract")
    values = document.get("required_evidence")
    if not isinstance(values, list):
        raise ValueError("terminal-parent readiness identity changed")
    evidence = {
        item.get("evidence_id"): item
        for item in values
        if isinstance(item, dict)
    }
    for evidence_id in (
        "public-finder-terminal-parent-correction-cumulative-regression",
        "public-finder-terminal-parent-correction-held-out-qualification",
    ):
        item = evidence.get(evidence_id)
        fields = (
            item.get("required_fields") if isinstance(item, dict) else None
        )
        if not isinstance(fields, dict) or (
            fields.get("candidate_revision") != _CANDIDATE_REVISION
            or fields.get("candidate_source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
            or fields.get("candidate_configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
        ):
            raise ValueError("terminal-parent readiness identity changed")


def _validate_implementation_decision(document: dict[str, object]) -> None:
    """Require composition authority without treating it as execution."""
    if document.get("status") != (
        "authorized-for-terminal-parent-correction-composition"
    ):
        raise ValueError("terminal-parent correction not authorized")
    authorization = document.get("authorization")
    if not isinstance(authorization, dict) or (
        authorization.get(
            "terminal_parent_correction_implementation_authorized"
        )
        is not True
        or authorization.get("fixture_validation_authorized") is not True
        or authorization.get("candidate_identity_freeze_authorized")
        is not True
        or authorization.get("replay_identity_freeze_authorized") is not True
        or authorization.get("cumulative_replay_authorized") is not False
    ):
        raise ValueError("terminal-parent correction authorization changed")


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify candidate, programs, retained evidence, and absent outputs."""
    _require_exact_invocation(arguments)
    revision = _git_revision()
    if source_tree_sha256(_ROOT) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("terminal-parent source tree changed")
    if _candidate_configuration_sha256() != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("terminal-parent configuration changed")
    for path, expected, label in (
        (_CONSUMED_WRAPPER, _CONSUMED_WRAPPER_SHA256, "consumed wrapper"),
        (_TERMINAL_PARENT_REVIEW, _TERMINAL_PARENT_REVIEW_SHA256, "review"),
        (
            _TERMINAL_PARENT_IMPLEMENTATION_DECISION,
            _TERMINAL_PARENT_IMPLEMENTATION_DECISION_SHA256,
            "implementation decision",
        ),
        (_READINESS, _READINESS_SHA256, "readiness"),
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
            raise ValueError(f"terminal-parent {label} identity changed")
    _validate_readiness()
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("terminal-parent write-once namespace exists")
    return revision


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Delegate complete retained-reference verification without science."""
    return _load_consumed_wrapper()["_verify_reference_reconstruction"](
        arguments
    )


def verify_terminal_parent_replay_composition(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Verify every identity and executable seam without replay state."""
    decision = _load_json(
        implementation_decision_path,
        label="terminal-parent implementation",
    )
    _validate_implementation_decision(decision)
    execution_revision = _require_common_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
    source_association, _, frozen = _load_source_association_composition()
    if not callable(
        source_association.get("_install_source_association_composition")
    ) or not callable(frozen.get("main")):
        raise ValueError("terminal-parent execution composition changed")
    _install_terminal_parent_static_seams(frozen)
    if (
        frozen["_write_continuum_products"].__name__
        != "_write_terminal_continuum_products"
        or frozen["_install_prospective_compiler"].__name__
        != "_install_terminal_parent_compiler"
        or not callable(frozen.get("_generate_candidate_product"))
    ):
        raise ValueError("terminal-parent executable seams changed")
    return {
        "association_sidecar_persistence_verified": True,
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "cumulative_replay_started": False,
        "execution_checkout_revision": execution_revision,
        "output_absent": not arguments.output.exists(),
        "readiness_sha256": _READINESS_SHA256,
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "scratch_absent": not arguments.scratch.exists(),
        "sidecar_aware_evaluator_installation_verified": True,
        "status": "pass",
        "verified_input_count": len(verified.inputs),
        "verified_reference_run_count": len(verified.runs),
    }


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity the exact execution approval binds."""
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "closed_baseline_path": str(
            arguments.closed_component_baseline_ledger
        ),
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "evaluator_program_sha256": _EVALUATOR_PROGRAM_SHA256,
        "implementation_decision_sha256": (
            _TERMINAL_PARENT_IMPLEMENTATION_DECISION_SHA256
        ),
        "output_path": str(arguments.output),
        "readiness_sha256": _READINESS_SHA256,
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "scratch_path": str(arguments.scratch),
        "terminal_parent_review_sha256": _TERMINAL_PARENT_REVIEW_SHA256,
        "workers": arguments.workers,
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def _authorize_replay(
    arguments: argparse.Namespace,
    execution_decision_path: Path,
) -> dict[str, object]:
    """Require the exact review and named one-replay approval."""
    if not execution_decision_path.is_file():
        raise ValueError("terminal-parent cumulative replay not authorized")
    decision = _load_json(
        execution_decision_path,
        label="terminal-parent cumulative replay",
    )
    if (
        decision.get("execution_authorized") is not True
        or decision.get("cumulative_replay_authorized") is not True
        or decision.get("status")
        != "authorized-for-one-terminal-parent-cumulative-replay"
    ):
        raise ValueError("terminal-parent cumulative replay not authorized")
    expected = canonical_sha256(_expected_execution_fields(arguments))
    if decision.get("expected_execution_sha256") != expected:
        raise ValueError("terminal-parent execution identity changed")
    prohibited = decision.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or prohibited != dict.fromkeys(
        _PROHIBITED_AUTHORIZATIONS, False
    ):
        raise ValueError("terminal-parent authorization changed")
    review = decision.get("identity_review")
    if not isinstance(review, dict) or review.get("path") != str(
        _IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError("terminal-parent identity review changed")
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or not _IDENTITY_REVIEW.is_file()
        or file_sha256(_IDENTITY_REVIEW) != review_sha256
    ):
        raise ValueError("terminal-parent identity review changed")
    execution_revision = _require_common_identities(arguments)
    return {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_source_overlay_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "execution_checkout_revision": execution_revision,
        "execution_decision_sha256": file_sha256(execution_decision_path),
        "identity_review_sha256": review_sha256,
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def run_authorized_replay(
    arguments: argparse.Namespace,
    *,
    execution_decision_path: Path,
) -> None:
    """Delegate exactly once after the exact decision passes."""
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
    _install_terminal_parent_static_seams(frozen)
    frozen["_generate_candidate_product"] = _generate_candidate_product
    frozen["_parse_args"] = lambda: arguments
    frozen["main"]()


def _parse_args() -> argparse.Namespace:
    """Parse the one exact prospective replay invocation."""
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
    """Run only after the exact replay decision exists."""
    run_authorized_replay(
        _parse_args(), execution_decision_path=_EXECUTION_DECISION
    )


if __name__ == "__main__":
    main()
