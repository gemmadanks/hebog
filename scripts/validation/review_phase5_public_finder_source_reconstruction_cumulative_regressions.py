#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify or run only the frozen source-reconstruction cumulative replay."""

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
    public_finder_source_reconstruction_candidate_configuration,
)
from hebog.validation.source_association_evaluation_repair import (
    continuum_catalogue_objects,
    measure_prospective_source_topology,
)

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT
    / "scripts/validation/review_phase5_public_finder_source_association_"
    "measurement_repair_cumulative_regressions.py"
)
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_CORRECTION_CONTRACT = (
    _ROOT / "config/contracts/phase-5-public-finder-correction.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "cumulative-replay-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-reconstruction-"
    "cumulative-replay-execution-decision.json"
)
_MULTISCALE_PROGRAM = _ROOT / "src/hebog/algorithms/multiscale_association.py"
_HIERARCHY_PROGRAM = _ROOT / "src/hebog/algorithms/source_association.py"
_SUPPORT_PROGRAM = _ROOT / "src/hebog/algorithms/extended_measurement.py"
_MEASUREMENT_PROGRAM = _ROOT / "src/hebog/validation/products.py"
_CANDIDATE_PROGRAM = _ROOT / "src/hebog/validation/public_finder_correction.py"
_EVALUATOR_PROGRAM = (
    _ROOT / "src/hebog/validation/source_association_evaluation_repair.py"
)

_CANDIDATE_REVISION = "42c75f44b71800ae5fa1e0ebe1669caa7da59f85"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "1b67c7f6f768d6f83becc853a1ebd45b3996164cd2b87fdc0f71b9a3299e6bf1"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "470e918db1a640d7393edc02de01fc57b50881b908bd6d5dac18a57709117bbb"
)
_CONSUMED_WRAPPER_SHA256 = (
    "79e8252cd06cca4959b794af231b6078c80a34f996ff5184ed7c8f4994029084"
)
_PRE_REVIEW_SHA256 = (
    "528f18a661bb2391018c458a29aace2757762e58107650e6ae01d05adc85347f"
)
_IMPLEMENTATION_DECISION_SHA256 = (
    "634ae2c753457f8e6c4b0181d6daa252b5a522c31057755ef4b765fec7972ab6"
)
_READINESS_SHA256 = (
    "c70c4c32fab67b0e95958ca0628201ae52139aaa55343a78e9172cf762d47e43"
)
_MULTISCALE_PROGRAM_SHA256 = (
    "be31b737b7835afaf718821c0584d668aa0878bb2950a667876296f731ac2a97"
)
_HIERARCHY_PROGRAM_SHA256 = (
    "60adc5f3be2e0bde41a5956107a35da7efa0994bacade011139581953b5e8ec9"
)
_SUPPORT_PROGRAM_SHA256 = (
    "6964fcfe067128eef01d8fb4b655e9ef9a6053e845236f03a0f534bae8635604"
)
_MEASUREMENT_PROGRAM_SHA256 = (
    "b4f024b41ac843f6084e6edb4c9173c9bd0b1b299a5c7f22c3d31789092f936d"
)
_CANDIDATE_PROGRAM_SHA256 = (
    "760a63e48d1e2952e33418e37f4207797d0ec5ddccdb5bab6d62587ef190223a"
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
    "public-finder-source-reconstruction.json"
)
_PROSPECTIVE_SCRATCH_PATH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-reconstruction-42c75f4"
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
    """Load the exact consumed wrapper without executing its entry point."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed wrapper identity changed")
    return runpy.run_path(str(_CONSUMED_WRAPPER))


def _candidate_configuration_sha256() -> str:
    """Return the approved source-reconstruction configuration identity."""
    configuration = (
        public_finder_source_reconstruction_candidate_configuration(
            _BASE_REVIEW,
            _CORRECTION_CONTRACT,
            _PRE_REVIEW,
            _IMPLEMENTATION_DECISION,
        )
    )
    identity = canonical_sha256(configuration)
    if identity != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("source-reconstruction configuration changed")
    return identity


def _candidate_runtime_identity(revision: str) -> ExternalRuntimeIdentity:
    """Bind the corrected source overlay to unchanged runtime dependencies."""
    if revision != _CANDIDATE_REVISION:
        raise ValueError("source-reconstruction candidate revision changed")
    return ExternalRuntimeIdentity(
        name="hebog-source-overlay",
        version="0.6.0",
        source_revision=revision,
        container_image_digest=_COMPATIBILITY_CONTAINER_DIGEST,
        dependency_inventory_sha256=(
            _COMPATIBILITY_DEPENDENCY_INVENTORY_SHA256
        ),
    )


def _binding_source_topology_metrics(
    truth: tuple[Any, ...],
    catalogue: tuple[Any, ...],
    *,
    truth_label_plane: Any,
    candidate_label_plane: Any,
    beam_fwhm_pixels: float,
) -> dict[str, dict[str, float | tuple[float, ...]]]:
    """Present source-union gates while retaining native diagnostics."""
    measured = measure_prospective_source_topology(
        truth,
        catalogue,
        truth_label_plane=truth_label_plane,
        candidate_label_plane=candidate_label_plane,
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    return measured.binding_metrics


def _install_prospective_source_topology(
    compiler_globals: dict[str, Any],
) -> None:
    """Replace only catalogue interpretation in the prospective compiler."""
    if not callable(
        compiler_globals.get("_candidate_objects")
    ) or not callable(compiler_globals.get("measure_continuum_image")):
        raise ValueError("prospective source-topology compiler seam changed")
    compiler_globals["_candidate_objects"] = continuum_catalogue_objects
    compiler_globals["measure_continuum_image"] = (
        _binding_source_topology_metrics
    )


def _install_source_reconstruction_static_seams(
    frozen: dict[str, Any],
) -> None:
    """Install candidate, Continuum builder, and prospective evaluator."""
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
    original_installer = frozen["_install_prospective_compiler"]

    def install(
        compiler_globals: dict[str, Any],
        prospective: Any,
        configuration_sha256: str,
    ) -> None:
        original_installer(
            compiler_globals,
            prospective,
            configuration_sha256,
        )
        _install_prospective_source_topology(compiler_globals)

    frozen["_install_prospective_compiler"] = install


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Reinstall corrected seams in every spawned candidate worker."""
    consumed = _load_consumed_wrapper()
    source_association = cast(
        dict[str, Any], consumed["_load_consumed_wrapper"]()
    )
    current = cast(
        dict[str, Any], source_association["_load_current_wrapper"]()
    )
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    _install_source_reconstruction_static_seams(frozen)
    return cast(str, frozen["_generate_candidate_product"](task))


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require the one prospective write-once replay namespace."""
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
        raise ValueError(
            "source-reconstruction replay requires clean checkout"
        )
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=_ROOT,
        text=True,
    ).strip()


def _validate_readiness() -> None:
    """Require final readiness to name the corrected future evidence."""
    if file_sha256(_READINESS) != _READINESS_SHA256:
        raise ValueError("source-reconstruction readiness identity changed")
    document = _load_json(_READINESS, label="readiness contract")
    values = document.get("required_evidence")
    if not isinstance(values, list):
        raise ValueError("source-reconstruction readiness identity changed")
    evidence = {
        item.get("evidence_id"): item
        for item in values
        if isinstance(item, dict)
    }
    required = (
        evidence.get(
            "public-finder-source-reconstruction-cumulative-regression"
        ),
        evidence.get(
            "public-finder-source-reconstruction-held-out-qualification"
        ),
    )
    for item in required:
        if not isinstance(item, dict):
            raise ValueError(
                "source-reconstruction readiness identity changed"
            )
        fields = item.get("required_fields")
        if (
            not isinstance(fields, dict)
            or fields.get("candidate_revision") != _CANDIDATE_REVISION
        ):
            raise ValueError(
                "source-reconstruction readiness identity changed"
            )
        if (
            fields.get("candidate_source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
            or fields.get("candidate_configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
        ):
            raise ValueError(
                "source-reconstruction readiness identity changed"
            )


def _validate_implementation_decision(document: dict[str, object]) -> None:
    """Require exact fixture-only authority and reject execution transfer."""
    if document.get("status") != (
        "authorized-for-source-reconstruction-implementation-and-fixture-only-"
        "validation"
    ):
        raise ValueError("source-reconstruction implementation not authorized")
    authorization = document.get("authorization")
    if not isinstance(authorization, dict):
        raise ValueError("source-reconstruction authorization changed")
    if (
        authorization.get("source_reconstruction_implementation_authorized")
        is not True
        or authorization.get("fixture_only_validation_authorized") is not True
        or authorization.get("candidate_identity_freeze_authorized")
        is not True
        or authorization.get("cumulative_replay_authorized") is not False
    ):
        raise ValueError("source-reconstruction authorization changed")
    if any(
        authorization.get(field) is not False
        for field in _PROHIBITED_AUTHORIZATIONS
    ):
        raise ValueError("source-reconstruction authorization changed")


def _require_common_identities(arguments: argparse.Namespace) -> str:
    """Verify candidate, programs, evidence, and absent write-once state."""
    _require_exact_invocation(arguments)
    revision = _git_revision()
    if source_tree_sha256(_ROOT) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("source-reconstruction source tree changed")
    if _candidate_configuration_sha256() != _CANDIDATE_CONFIGURATION_SHA256:
        raise ValueError("source-reconstruction configuration changed")
    for path, expected, label in (
        (_CONSUMED_WRAPPER, _CONSUMED_WRAPPER_SHA256, "consumed wrapper"),
        (_PRE_REVIEW, _PRE_REVIEW_SHA256, "pre-review"),
        (
            _IMPLEMENTATION_DECISION,
            _IMPLEMENTATION_DECISION_SHA256,
            "implementation decision",
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
            raise ValueError(f"source-reconstruction {label} identity changed")
    _validate_readiness()
    if arguments.output.exists() or arguments.scratch.exists():
        raise ValueError("source-reconstruction write-once namespace exists")
    return revision


def _verify_reference_reconstruction(arguments: argparse.Namespace) -> Any:
    """Delegate complete retained-reference verification without science."""
    return _load_consumed_wrapper()["_verify_reference_reconstruction"](
        arguments
    )


def verify_source_reconstruction_replay_composition(
    arguments: argparse.Namespace,
    *,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Verify all identities and references without creating replay state."""
    decision = _load_json(
        implementation_decision_path,
        label="source-reconstruction implementation",
    )
    _validate_implementation_decision(decision)
    execution_revision = _require_common_identities(arguments)
    verified = _verify_reference_reconstruction(arguments)
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
            "consumed_measurement_repair_wrapper_sha256": (
                _CONSUMED_WRAPPER_SHA256
            ),
            "source_reconstruction_pre_review_sha256": _PRE_REVIEW_SHA256,
            "source_reconstruction_implementation_decision_sha256": (
                _IMPLEMENTATION_DECISION_SHA256
            ),
            "source_reconstruction_multiscale_program_sha256": (
                _MULTISCALE_PROGRAM_SHA256
            ),
            "source_reconstruction_hierarchy_program_sha256": (
                _HIERARCHY_PROGRAM_SHA256
            ),
            "source_reconstruction_support_program_sha256": (
                _SUPPORT_PROGRAM_SHA256
            ),
            "source_reconstruction_measurement_program_sha256": (
                _MEASUREMENT_PROGRAM_SHA256
            ),
            "source_reconstruction_candidate_program_sha256": (
                _CANDIDATE_PROGRAM_SHA256
            ),
            "source_reconstruction_evaluator_program_sha256": (
                _EVALUATOR_PROGRAM_SHA256
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
            "source-reconstruction cumulative replay not authorized"
        )
    decision = _load_json(
        execution_decision_path,
        label="source-reconstruction cumulative replay",
    )
    if (
        decision.get("execution_authorized") is not True
        or decision.get("cumulative_replay_authorized") is not True
    ):
        raise ValueError(
            "source-reconstruction cumulative replay not authorized"
        )
    for field, expected in _expected_execution_fields(arguments).items():
        if decision.get(field) != expected:
            raise ValueError(f"cumulative replay {field} identity changed")
    prohibited = decision.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or prohibited != dict.fromkeys(
        _PROHIBITED_AUTHORIZATIONS,
        False,
    ):
        raise ValueError("source-reconstruction authorization changed")
    review = decision.get("source_reconstruction_replay_identity_review")
    if not isinstance(review, dict) or review.get("path") != str(
        _IDENTITY_REVIEW.relative_to(_ROOT)
    ):
        raise ValueError("source-reconstruction identity review changed")
    review_sha256 = review.get("sha256")
    if (
        not isinstance(review_sha256, str)
        or not _IDENTITY_REVIEW.is_file()
        or file_sha256(_IDENTITY_REVIEW) != review_sha256
    ):
        raise ValueError("source-reconstruction identity review changed")
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
    """Delegate exactly once only after a later named approval."""
    provenance = _authorize_replay(arguments, execution_decision_path)
    verified = _verify_reference_reconstruction(arguments)
    consumed = _load_consumed_wrapper()
    source_association = cast(
        dict[str, Any], consumed["_load_consumed_wrapper"]()
    )
    current = cast(
        dict[str, Any], source_association["_load_current_wrapper"]()
    )
    frozen = cast(dict[str, Any], current["_load_frozen_replay"]())
    source_association["_install_source_association_composition"](
        current,
        frozen,
        provenance,
        verified_reference=verified,
    )
    _install_source_reconstruction_static_seams(frozen)
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
