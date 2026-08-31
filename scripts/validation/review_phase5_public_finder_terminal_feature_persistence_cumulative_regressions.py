#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify or run only the frozen terminal-feature persistence replay."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_runners import (
    ExternalRuntimeIdentity,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.public_finder_correction import (
    public_finder_terminal_feature_persistence_configuration,
)
from hebog.validation.terminal_feature_persistence_evaluation import (
    aggregate_terminal_feature_persistence,
    install_terminal_feature_persistence_evaluation,
    load_source_association,
)

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
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
_TERMINAL_FEATURE_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-pre-review.json"
)
_TERMINAL_FEATURE_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-implementation-decision.json"
)
_PARENT_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_READINESS = (
    _ROOT / "config/contracts/phase-5-terminal-feature-persistence-"
    "readiness.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-cumulative-replay-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-terminal-feature-"
    "persistence-cumulative-replay-execution-decision.json"
)
_CANDIDATE_PROGRAM = _ROOT / "src/hebog/validation/public_finder_correction.py"
_EVALUATOR_PROGRAM = (
    _ROOT / "src/hebog/validation/terminal_feature_persistence_evaluation.py"
)

_CANDIDATE_REVISION = "3d080f78da09ada6753a4e5df898e1d5daa59597"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "a25d22d80f4e639e4543ee058acade6feda15105f6325dc909e69fcfb8f03924"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2d6ab6bbdd06f109f9703fb0b49f489933ddc00b391f681253693b38d0f4b1de"
)
_CONSUMED_WRAPPER_SHA256 = (
    "2c40315ffe821008b249a57b5e8c012b0f6526ae8aacab5a9bbdb35bdeac2f21"
)
_TERMINAL_FEATURE_PRE_REVIEW_SHA256 = (
    "e416f7d81ac8345f2ac0ac982980e9e37299886309af2468380a7a463beafc38"
)
_TERMINAL_FEATURE_IMPLEMENTATION_DECISION_SHA256 = (
    "5ad7d29980420ba0b5bb65739344f77de504ac8b43c122111d605563f70d48dc"
)
_CANDIDATE_PROGRAM_SHA256 = (
    "c0cb13b9de789f53a9ecadf50803ab60266cd142cae394a26860714d92a4945d"
)
_EVALUATOR_PROGRAM_SHA256 = (
    "1cb62c0028288bd3149b325eb4c56c25f4535dcd5e5b38ac509e232ea8c21b02"
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
_PARENT_READINESS_SHA256 = (
    "fb295c16b5a67618b242891dc048c4290b88ff8ceaecf81a7ad409b015f8c137"
)
_READINESS_SHA256 = (
    "da135898ed3cbada89ca32c4d2f5c1cd8f11f82a896f7d2197da6e444b3208fd"
)
_PROSPECTIVE_REFERENCE_PATH = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_PROSPECTIVE_OUTPUT_PATH = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-"
    "public-finder-terminal-feature-persistence.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-terminal-feature-persistence-"
    "3d080f7"
)
_PROSPECTIVE_BASELINE_PATH = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_CONTINUUM_COUNT = 1600
_EXPECTED_READINESS_EVIDENCE_COUNT = 2
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
    """Load the exact terminal-parent predecessor without executing it."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed terminal-parent wrapper changed")
    return runpy.run_path(str(_CONSUMED_WRAPPER))


def _load_source_association_composition() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any]
]:
    """Use the predecessor's complete reviewed composition descent."""
    return cast(
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
        _load_consumed_wrapper()["_load_source_association_composition"](),
    )


def _candidate_configuration_sha256() -> str:
    """Return the exact terminal-feature persistence configuration."""
    configuration = public_finder_terminal_feature_persistence_configuration(
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
        _TERMINAL_FEATURE_PRE_REVIEW,
        _TERMINAL_FEATURE_IMPLEMENTATION_DECISION,
    )
    identity = canonical_sha256(configuration)
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("terminal-feature persistence configuration changed")
    return identity


def _candidate_runtime_identity(revision: str) -> ExternalRuntimeIdentity:
    """Bind the source overlay to unchanged compatibility dependencies."""
    if revision != _CANDIDATE_REVISION:
        raise ValueError("terminal-feature persistence revision changed")
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
    """Resolve the exact safe association sidecar named by one run."""
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


def _marker_sidecar(directory: Path) -> Path | None:
    """Verify one exact product marker and return its optional sidecar."""
    marker = _load_json(directory / "complete.json", label="candidate marker")
    if (
        marker.get("input_id") != directory.name
        or marker.get("configuration_sha256")
        != _CANDIDATE_CONFIGURATION_SHA256
        or marker.get("source_tree_sha256") != _CANDIDATE_SOURCE_TREE_SHA256
    ):
        raise ValueError("terminal persistence product identity changed")
    records = marker.get("artifacts")
    if not isinstance(records, list):
        raise ValueError("terminal persistence artifacts are malformed")
    matches: list[Path] = []
    for value in records:
        if not isinstance(value, dict):
            raise ValueError("terminal persistence artifact is malformed")
        record = cast(Mapping[str, object], value)
        if record.get("role") != "source-association-json":
            continue
        relative_value = record.get("relative_path")
        if not isinstance(relative_value, str):
            raise ValueError("terminal persistence sidecar path is malformed")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("terminal persistence sidecar path is unsafe")
        path = directory / relative
        byte_count = record.get("byte_count")
        sha256 = record.get("sha256")
        if (
            type(byte_count) is not int
            or not isinstance(sha256, str)
            or not path.is_file()
            or path.stat().st_size != byte_count
            or file_sha256(path) != sha256
        ):
            raise ValueError("terminal persistence sidecar identity changed")
        matches.append(path)
    if len(matches) > 1:
        raise ValueError("candidate marker contains duplicate associations")
    return matches[0] if matches else None


def _aggregate_completed_sidecars(scratch: Path) -> dict[str, int]:
    """Reduce exactly 1,600 sidecars from 2,400 verified products."""
    products = scratch / "products"
    if not products.is_dir():
        raise ValueError("terminal persistence products are absent")
    entries = tuple(sorted(products.iterdir()))
    if len(entries) != _EXPECTED_INPUT_COUNT or any(
        not path.is_dir() for path in entries
    ):
        raise ValueError("terminal persistence product count differs")
    sidecars = tuple(
        sidecar
        for directory in entries
        if (sidecar := _marker_sidecar(directory)) is not None
    )
    return aggregate_terminal_feature_persistence(
        sidecars,
        expected_image_count=_EXPECTED_CONTINUUM_COUNT,
    )


def _install_terminal_feature_persistence_static_seams(
    frozen: dict[str, Any],
) -> None:
    """Install the candidate, census validation, and bounded ledger record."""
    consumed = _load_consumed_wrapper()
    consumed["_install_terminal_parent_static_seams"](frozen)
    frozen["_CANDIDATE_REVISION"] = _CANDIDATE_REVISION
    frozen["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"] = (
        _CLOSED_BASELINE_SHA256
    )
    frozen["_candidate_configuration_sha256"] = _candidate_configuration_sha256
    frozen["_candidate_runtime_identity"] = _candidate_runtime_identity

    original_writer = frozen["_write_continuum_products"]

    def _write_terminal_feature_persistence_products(
        *args: object, **kwargs: object
    ) -> dict[str, Path]:
        paths = cast(dict[str, Path], original_writer(*args, **kwargs))
        sidecar = paths.get("source-association-json")
        if sidecar is None:
            raise ValueError("candidate source association is unavailable")
        load_source_association(sidecar)
        return paths

    original_installer = frozen["_install_prospective_compiler"]

    def _install_terminal_feature_persistence_compiler(
        compiler_globals: dict[str, Any],
        prospective: Any,
        configuration_sha256: str,
    ) -> None:
        original_installer(compiler_globals, prospective, configuration_sha256)
        install_terminal_feature_persistence_evaluation(
            compiler_globals,
            association_path=_association_artifact_path,
        )

    original_serializer = cast(
        Callable[[object], bytes], frozen["_canonical_json_bytes"]
    )

    def _serialize_terminal_feature_persistence(value: object) -> bytes:
        document = value
        if isinstance(value, dict) and value.get("ledger_id") == (
            "phase-5-cumulative-regression-ledger"
        ):
            document = {
                **value,
                "terminal_feature_persistence_diagnostics": (
                    _aggregate_completed_sidecars(_PROSPECTIVE_SCRATCH_PATH)
                ),
                "terminal_feature_persistence_provenance": {
                    "evaluator_program_sha256": _EVALUATOR_PROGRAM_SHA256,
                    "implementation_decision_sha256": (
                        _TERMINAL_FEATURE_IMPLEMENTATION_DECISION_SHA256
                    ),
                    "pre_review_sha256": (_TERMINAL_FEATURE_PRE_REVIEW_SHA256),
                },
            }
        return original_serializer(document)

    frozen["_write_continuum_products"] = (
        _write_terminal_feature_persistence_products
    )
    frozen["_install_prospective_compiler"] = (
        _install_terminal_feature_persistence_compiler
    )
    frozen["_canonical_json_bytes"] = _serialize_terminal_feature_persistence


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Reinstall the exact candidate composition in each spawned worker."""
    _, _, frozen = _load_source_association_composition()
    _install_terminal_feature_persistence_static_seams(frozen)
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
            raise ValueError(f"terminal-feature replay {field} changed")


def _git_revision() -> str:
    """Return the clean composition checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("terminal-feature replay requires clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _validate_readiness() -> None:
    """Require the prospective overlay to bind only this candidate."""
    if file_sha256(_READINESS) != _READINESS_SHA256:
        raise ValueError("terminal-feature readiness identity changed")
    document = _load_json(_READINESS, label="readiness overlay")
    parent = document.get("parent_readiness")
    evidence = document.get("required_evidence")
    authorization = document.get("authorization")
    expected_evidence = {
        "public-finder-terminal-feature-persistence-cumulative-regression": (
            _PROSPECTIVE_OUTPUT_PATH
        ),
        "public-finder-terminal-feature-persistence-held-out-qualification": (
            Path(
                "benchmark-results/phase-5/public-finder-terminal-feature-"
                "persistence-qualification-decision.json"
            )
        ),
    }
    if (
        document.get("status") != "frozen-non-executable-overlay"
        or not isinstance(authorization, dict)
        or not authorization
        or any(authorization.values())
        or not isinstance(parent, dict)
        or parent.get("path") != str(_PARENT_READINESS.relative_to(_ROOT))
        or parent.get("sha256") != _PARENT_READINESS_SHA256
        or not isinstance(evidence, list)
        or len(evidence) != _EXPECTED_READINESS_EVIDENCE_COUNT
    ):
        raise ValueError("terminal-feature readiness identity changed")
    actual_evidence: dict[object, object] = {}
    for value in evidence:
        if not isinstance(value, dict):
            raise ValueError("terminal-feature readiness identity changed")
        actual_evidence[value.get("evidence_id")] = value.get("path")
        fields = value.get("required_fields")
        if not isinstance(fields, dict) or (
            fields.get("candidate_revision") != _CANDIDATE_REVISION
            or fields.get("candidate_source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
            or fields.get("candidate_configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
        ):
            raise ValueError("terminal-feature readiness identity changed")
    if actual_evidence != {
        evidence_id: str(path)
        for evidence_id, path in expected_evidence.items()
    }:
        raise ValueError("terminal-feature readiness identity changed")


def _validate_implementation_decision(document: dict[str, object]) -> None:
    """Require implementation authority without treating it as execution."""
    if document.get("status") != (
        "authorized-for-terminal-feature-persistence-composition"
    ):
        raise ValueError("terminal-feature persistence not authorized")
    authorization = document.get("authorization")
    if not isinstance(authorization, dict) or (
        authorization.get(
            "terminal_feature_persistence_implementation_authorized"
        )
        is not True
        or authorization.get("fixture_validation_authorized") is not True
        or authorization.get("candidate_identity_freeze_authorized")
        is not True
        or authorization.get("replay_identity_freeze_authorized") is not True
        or authorization.get("cumulative_replay_authorized") is not False
        or authorization.get("viewed_data_execution_authorized") is not False
    ):
        raise ValueError("terminal-feature persistence authorization changed")


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify candidate, programs, retained evidence, and absent outputs."""
    _require_exact_invocation(arguments)
    revision = _git_revision()
    if source_tree_sha256(_ROOT) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("terminal-feature source tree changed")
    if _candidate_configuration_sha256() != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("terminal-feature configuration changed")
    for path, expected, label in (
        (_CONSUMED_WRAPPER, _CONSUMED_WRAPPER_SHA256, "consumed wrapper"),
        (
            _TERMINAL_FEATURE_PRE_REVIEW,
            _TERMINAL_FEATURE_PRE_REVIEW_SHA256,
            "pre-review",
        ),
        (
            _TERMINAL_FEATURE_IMPLEMENTATION_DECISION,
            _TERMINAL_FEATURE_IMPLEMENTATION_DECISION_SHA256,
            "implementation decision",
        ),
        (_READINESS, _READINESS_SHA256, "readiness"),
        (
            _PARENT_READINESS,
            _PARENT_READINESS_SHA256,
            "parent readiness",
        ),
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
            raise ValueError(f"terminal-feature {label} identity changed")
    _validate_readiness()
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("terminal-feature write-once namespace exists")
    return revision


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Delegate complete retained-reference verification without science."""
    return _load_consumed_wrapper()["_verify_reference_reconstruction"](
        arguments
    )


def verify_terminal_feature_persistence_replay_composition(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Verify every identity and executable seam without replay state."""
    decision = _load_json(
        implementation_decision_path,
        label="terminal-feature implementation",
    )
    _validate_implementation_decision(decision)
    execution_revision = _require_common_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
    source_association, _, frozen = _load_source_association_composition()
    if not callable(
        source_association.get("_install_source_association_composition")
    ) or not callable(frozen.get("main")):
        raise ValueError("terminal-feature execution composition changed")
    _install_terminal_feature_persistence_static_seams(frozen)
    if (
        frozen["_write_continuum_products"].__name__
        != "_write_terminal_feature_persistence_products"
        or frozen["_install_prospective_compiler"].__name__
        != "_install_terminal_feature_persistence_compiler"
        or frozen["_canonical_json_bytes"].__name__
        != "_serialize_terminal_feature_persistence"
        or not callable(frozen.get("_generate_candidate_product"))
    ):
        raise ValueError("terminal-feature executable seams changed")
    return {
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
        "status": "pass",
        "terminal_persistence_census_aggregation_verified": True,
        "terminal_persistence_evaluator_installation_verified": True,
        "terminal_persistence_sidecar_validation_verified": True,
        "verified_input_count": len(verified.inputs),
        "verified_reference_run_count": len(verified.runs),
    }


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity a future exact replay approval must bind."""
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
            _TERMINAL_FEATURE_IMPLEMENTATION_DECISION_SHA256
        ),
        "output_path": str(arguments.output),
        "pre_review_sha256": _TERMINAL_FEATURE_PRE_REVIEW_SHA256,
        "readiness_sha256": _READINESS_SHA256,
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "reference_reconstruction_sha256": _REFERENCE_RECONSTRUCTION_SHA256,
        "scratch_path": str(arguments.scratch),
        "workers": arguments.workers,
        "wrapper_sha256": file_sha256(Path(__file__)),
    }


def _authorize_replay(
    arguments: argparse.Namespace,
    execution_decision_path: Path,
) -> dict[str, object]:
    """Require a future exact review and one-replay approval."""
    if not execution_decision_path.is_file():
        raise ValueError("terminal-feature cumulative replay not authorized")
    decision = _load_json(
        execution_decision_path,
        label="terminal-feature cumulative replay",
    )
    if (
        decision.get("execution_authorized") is not True
        or decision.get("cumulative_replay_authorized") is not True
        or decision.get("status")
        != "authorized-for-one-terminal-feature-cumulative-replay"
    ):
        raise ValueError("terminal-feature cumulative replay not authorized")
    expected = canonical_sha256(_expected_execution_fields(arguments))
    if decision.get("expected_execution_sha256") != expected:
        raise ValueError("terminal-feature execution identity changed")
    prohibited = decision.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or prohibited != dict.fromkeys(
        _PROHIBITED_AUTHORIZATIONS, False
    ):
        raise ValueError("terminal-feature authorization changed")
    review = decision.get("identity_review")
    if not isinstance(review, dict) or review.get("path") != str(
        _IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError("terminal-feature identity review changed")
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or not _IDENTITY_REVIEW.is_file()
        or file_sha256(_IDENTITY_REVIEW) != review_sha256
    ):
        raise ValueError("terminal-feature identity review changed")
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
    """Delegate exactly once only after a future decision passes."""
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
    _install_terminal_feature_persistence_static_seams(frozen)
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
    """Remain closed until a separately approved exact decision exists."""
    run_authorized_replay(
        _parse_args(), execution_decision_path=_EXECUTION_DECISION
    )


if __name__ == "__main__":
    main()
