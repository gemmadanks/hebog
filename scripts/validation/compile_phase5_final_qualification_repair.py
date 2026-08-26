#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Repair the final-qualification evaluation composition exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from pathlib import Path
from typing import Any, Literal, cast

_ROOT = Path(__file__).parents[2]
_FROZEN_COMPILER_RELATIVE = (
    "scripts/validation/compile_phase5_final_qualification_campaign.py"
)
_FROZEN_COMPILER_PATH = _ROOT / _FROZEN_COMPILER_RELATIVE
_FROZEN_COMPILER_SHA256 = (
    "c2b7f3ac3b072ba1c250cd27c917495cab3ba517cfb86a9102d06c763b66b165"
)
_FROZEN_EVALUATOR_RELATIVE = (
    "scripts/validation/evaluate_phase5_final_qualification_decision.py"
)
_FROZEN_EVALUATOR_SHA256 = (
    "558e29574287aef6bee348fb37c329b7dab2f115ff42c481d3a1019d3f713560"
)
_REPAIR_COMPILER_RELATIVE = (
    "scripts/validation/compile_phase5_final_qualification_repair.py"
)
_REPAIR_EVALUATOR_RELATIVE = (
    "scripts/validation/evaluate_phase5_final_qualification_repair.py"
)
_REPAIR_REVIEW_RELATIVE = (
    "config/contracts/"
    "phase-5-final-qualification-evaluation-repair-review.json"
)
_CAMPAIGN_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-comparison/campaign.json"
)
_CAMPAIGN_SHA256 = (
    "4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08"
)
_CAMPAIGN_REQUEST_SHA256 = (
    "eebb6d793b0ee4532db2393bf06468df53dbc9521092cc8fb6e2340be7194726"
)
_ANALYSIS_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-analysis.json"
)
_DECISION_RELATIVE = (
    "benchmark-results/phase-5/final-qualification-decision.json"
)
_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-final-qualification-endpoint-registry.json"
)
_FROZEN = runpy.run_path(str(_FROZEN_COMPILER_PATH))
_FROZEN_CONFIGURE = _FROZEN["_configured_terminal"]
_FROZEN_COMPILE = _FROZEN["compile_final_qualification_analysis"]


def file_sha256(path: Path) -> str:
    """Hash one identity without retaining the artifact in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_object(path: Path) -> dict[str, Any]:
    """Load one strict JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _bound_path(
    repository_root: Path,
    identity: object,
    *,
    expected_relative: str,
    description: str,
) -> Path:
    """Resolve and verify one exact repair dependency."""
    if not isinstance(identity, dict):
        raise ValueError(f"{description} identity is incomplete")
    if identity.get("path") != expected_relative or not isinstance(
        identity.get("sha256"), str
    ):
        raise ValueError(f"{description} identity is incomplete")
    path = repository_root / expected_relative
    if file_sha256(path) != identity["sha256"]:
        raise ValueError(f"{description} checksum changed")
    return path


def _output_paths(
    document: dict[str, Any], repository_root: Path
) -> tuple[Path, Path]:
    """Validate and resolve the two fixed write-once outputs."""
    outputs = document.get("outputs")
    if not isinstance(outputs, dict) or outputs != {
        "analysis_path": _ANALYSIS_RELATIVE,
        "analysis_state": "absent",
        "decision_path": _DECISION_RELATIVE,
        "decision_state": "absent",
    }:
        raise ValueError("evaluation repair outputs changed")
    return (
        repository_root / _ANALYSIS_RELATIVE,
        repository_root / _DECISION_RELATIVE,
    )


def load_repair_authorization(
    path: Path,
    compiler_path: Path,
    evaluator_path: Path,
    repository_root: Path,
    *,
    stage: Literal["compile", "evaluate"] = "compile",
) -> dict[str, Any]:
    """Validate exact authorization for one compile-and-evaluate sequence."""
    if stage not in {"compile", "evaluate"}:
        raise ValueError("evaluation repair stage changed")
    document = json_object(path)
    required = frozenset(
        {
            "campaign",
            "campaign_reexecution_authorized",
            "compilation_authorized",
            "cutover_authorized",
            "decision_id",
            "evaluation_authorized",
            "execution_authorized",
            "named_review",
            "optimization_authorized",
            "outputs",
            "release_authorized",
            "repair_compiler",
            "repair_evaluator",
            "repair_identity_review",
            "rescoring_authorized",
            "schema_version",
            "science_or_gates_changed",
            "status",
            "tuning_authorized",
        }
    )
    campaign = document.get("campaign")
    named_review = document.get("named_review")
    review = document.get("repair_identity_review")
    if (
        frozenset(document) != required
        or document.get("schema_version") != 1
        or document.get("decision_id")
        != "phase-5-final-qualification-evaluation-repair-decision"
        or document.get("status")
        != "reviewed-before-final-qualification-evaluation-repair"
        or document.get("execution_authorized") is not True
        or document.get("compilation_authorized") is not True
        or document.get("evaluation_authorized") is not True
        or document.get("campaign_reexecution_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("rescoring_authorized") is not False
        or document.get("science_or_gates_changed") is not False
        or document.get("tuning_authorized") is not False
        or document.get("cutover_authorized") is not False
        or document.get("release_authorized") is not False
        or not isinstance(campaign, dict)
        or campaign
        != {
            "path": _CAMPAIGN_RELATIVE,
            "request_sha256": _CAMPAIGN_REQUEST_SHA256,
            "sha256": _CAMPAIGN_SHA256,
        }
        or not isinstance(named_review, dict)
        or named_review.get("reviewer") != "Gemma Danks"
        or not isinstance(named_review.get("approval"), str)
        or not isinstance(review, dict)
        or review.get("sha256") not in named_review["approval"]
    ):
        raise ValueError("evaluation repair is not exactly authorized")
    _bound_path(
        repository_root,
        document["campaign"],
        expected_relative=_CAMPAIGN_RELATIVE,
        description="sealed final qualification campaign",
    )
    bound_compiler = _bound_path(
        repository_root,
        document["repair_compiler"],
        expected_relative=_REPAIR_COMPILER_RELATIVE,
        description="evaluation repair compiler",
    )
    bound_evaluator = _bound_path(
        repository_root,
        document["repair_evaluator"],
        expected_relative=_REPAIR_EVALUATOR_RELATIVE,
        description="evaluation repair evaluator",
    )
    _bound_path(
        repository_root,
        review,
        expected_relative=_REPAIR_REVIEW_RELATIVE,
        description="evaluation repair identity review",
    )
    if bound_compiler != compiler_path or bound_evaluator != evaluator_path:
        raise ValueError("evaluation repair program path changed")
    analysis_path, decision_path = _output_paths(document, repository_root)
    if stage == "compile" and (
        analysis_path.exists() or decision_path.exists()
    ):
        raise FileExistsError("evaluation repair outputs must both be absent")
    if stage == "evaluate" and (
        not analysis_path.is_file() or decision_path.exists()
    ):
        raise FileExistsError(
            "evaluation repair analysis must exist and decision be absent"
        )
    return document


def _final_compatibility_helpers() -> dict[str, Any]:
    """Map every inherited protocol and model alias to the final schema."""
    helpers = dict(_FROZEN["_HELPERS"])
    protocol_loader = helpers["load_final_qualification_protocol"]
    decision_loader = helpers["load_final_qualification_execution_decision"]
    registry_loader = helpers["load_final_qualification_endpoint_registry"]
    request_model = helpers["final_qualification_campaign_model"]
    helpers.update(
        {
            "load_post_failure_protocol": protocol_loader,
            "load_post_failure_execution_decision": decision_loader,
            "load_post_failure_endpoint_registry": registry_loader,
            "post_failure_campaign_request_model": request_model,
            "post_failure_terminal_result_model": request_model,
            "load_recovery_protocol": protocol_loader,
            "load_recovery_execution_decision": decision_loader,
            "load_recovery_endpoint_registry": registry_loader,
            "recovery_campaign_request_model": request_model,
            "recovery_terminal_result_model": request_model,
        }
    )
    return helpers


def configure_repaired_terminal() -> dict[str, Any]:
    """Install final loaders at the inherited compatibility seam."""
    recovery_configure = _FROZEN["_BASE"]["_configured_terminal"]
    recovery_globals = recovery_configure.__globals__
    final_globals = _FROZEN_CONFIGURE.__globals__
    compatibility = _final_compatibility_helpers()
    previous_recovery = recovery_globals["_COMPAT_HELPERS"]
    previous_final = final_globals["_COMPAT_HELPERS"]
    recovery_globals["_COMPAT_HELPERS"] = compatibility
    final_globals["_COMPAT_HELPERS"] = compatibility
    try:
        terminal = _FROZEN_CONFIGURE()
    finally:
        final_globals["_COMPAT_HELPERS"] = previous_final
        recovery_globals["_COMPAT_HELPERS"] = previous_recovery
    return cast(dict[str, Any], terminal)


def compile_repaired_analysis(
    campaign_path: Path,
    authorization_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    """Delegate unchanged science after repairing only the loader seam."""
    compile_globals = _FROZEN_COMPILE.__globals__
    previous = compile_globals["_configured_terminal"]
    compile_globals["_configured_terminal"] = configure_repaired_terminal
    try:
        analysis = _FROZEN_COMPILE(
            campaign_path,
            _REGISTRY_PATH,
            _FROZEN_COMPILER_PATH,
        )
    finally:
        compile_globals["_configured_terminal"] = previous
    review = cast(dict[str, Any], authorization["repair_identity_review"])
    analysis["evaluation_repair"] = {
        "authorization_sha256": file_sha256(authorization_path),
        "compatibility_change": (
            "install-final-loaders-at-inherited-compatibility-seam"
        ),
        "frozen_compiler_sha256": _FROZEN_COMPILER_SHA256,
        "frozen_evaluator_sha256": _FROZEN_EVALUATOR_SHA256,
        "repair_compiler_sha256": file_sha256(Path(__file__)),
        "repair_identity_review_sha256": review["sha256"],
        "science_or_gates_changed": False,
    }
    return cast(dict[str, Any], analysis)


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite deterministic evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _parse_args() -> argparse.Namespace:
    """Parse the separately approved repair authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Compile the existing campaign only after exact renewed approval."""
    arguments = _parse_args()
    authorization = load_repair_authorization(
        arguments.authorization,
        Path(__file__),
        _ROOT / _REPAIR_EVALUATOR_RELATIVE,
        _ROOT,
    )
    campaign = _bound_path(
        _ROOT,
        authorization["campaign"],
        expected_relative=_CAMPAIGN_RELATIVE,
        description="sealed final qualification campaign",
    )
    analysis = compile_repaired_analysis(
        campaign,
        arguments.authorization,
        authorization,
    )
    output = _ROOT / _ANALYSIS_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
