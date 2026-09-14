#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Apply the reviewed recovery evaluator identity amendment exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_FROZEN_EVALUATOR_RELATIVE = (
    "scripts/validation/evaluate_phase5_external_recovery_decision.py"
)
_FROZEN_EVALUATOR_PATH = _ROOT / _FROZEN_EVALUATOR_RELATIVE
_FROZEN = runpy.run_path(str(_FROZEN_EVALUATOR_PATH))
_BASE_EVALUATE = _FROZEN["_BASE_EVALUATE"]
_AMENDED_EVALUATOR_RELATIVE = (
    "scripts/validation/evaluate_phase5_external_recovery_amendment.py"
)
_AMENDMENT_REVIEW_RELATIVE = (
    "config/contracts/"
    "phase-5-external-recovery-evaluation-amendment-review.json"
)
_ANALYSIS_RELATIVE = (
    "benchmark-results/phase-5/external-recovery-analysis.json"
)
_FROZEN_CONTRACT_RELATIVE = (
    "config/contracts/phase-5-external-recovery-evaluation.json"
)
_OUTPUT_RELATIVE = "benchmark-results/phase-5/external-recovery-decision.json"


def file_sha256(path: Path) -> str:
    """Hash one evidence artifact without retaining it in memory."""
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
    root: Path,
    identity: object,
    *,
    description: str,
) -> Path:
    """Resolve and verify one exact amendment dependency."""
    if not isinstance(identity, dict):
        raise ValueError(f"{description} identity is incomplete")
    relative_path = identity.get("path")
    expected_sha256 = identity.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(
        expected_sha256, str
    ):
        raise ValueError(f"{description} identity is incomplete")
    path = root / relative_path
    if file_sha256(path) != expected_sha256:
        raise ValueError(f"{description} checksum changed")
    return path


def load_amendment_authorization(
    path: Path,
    evaluator_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate named authorization and every preserved evidence identity."""
    document = json_object(path)
    required = frozenset(
        {
            "amendment_review",
            "analysis",
            "analysis_recompilation_authorized",
            "campaign_reexecution_authorized",
            "decision_id",
            "evaluator",
            "execution_authorized",
            "frozen_contract",
            "frozen_evaluator",
            "named_review",
            "output_path",
            "schema_version",
            "science_or_gates_changed",
            "status",
        }
    )
    if frozenset(document) != required:
        raise ValueError("evaluation amendment authorization fields changed")
    evaluator = cast(dict[str, Any], document.get("evaluator"))
    named_review = cast(dict[str, Any], document.get("named_review"))
    review = cast(dict[str, Any], document.get("amendment_review"))
    if (
        document.get("schema_version") != 1
        or document.get("decision_id")
        != "phase-5-external-recovery-evaluation-amendment-decision"
        or document.get("status")
        != "reviewed-before-recovery-evaluation-amendment"
        or document.get("execution_authorized") is not True
        or document.get("campaign_reexecution_authorized") is not False
        or document.get("analysis_recompilation_authorized") is not False
        or document.get("science_or_gates_changed") is not False
        or document.get("output_path") != _OUTPUT_RELATIVE
        or evaluator.get("path") != _AMENDED_EVALUATOR_RELATIVE
        or evaluator.get("sha256") != file_sha256(evaluator_path)
        or named_review.get("reviewer") != "Gemma Danks"
        or not isinstance(named_review.get("approval"), str)
        or review.get("sha256") not in named_review.get("approval", "")
    ):
        raise ValueError("evaluation amendment is not exactly authorized")
    for key, description in (
        ("amendment_review", "evaluation amendment review"),
        ("analysis", "sealed recovery analysis"),
        ("evaluator", "amended recovery evaluator"),
        ("frozen_contract", "frozen recovery evaluation contract"),
        ("frozen_evaluator", "frozen recovery evaluator"),
    ):
        _bound_path(repository_root, document[key], description=description)
    expected_paths = {
        "amendment_review": _AMENDMENT_REVIEW_RELATIVE,
        "analysis": _ANALYSIS_RELATIVE,
        "evaluator": _AMENDED_EVALUATOR_RELATIVE,
        "frozen_contract": _FROZEN_CONTRACT_RELATIVE,
        "frozen_evaluator": _FROZEN_EVALUATOR_RELATIVE,
    }
    if any(
        cast(dict[str, Any], document[key]).get("path") != expected
        for key, expected in expected_paths.items()
    ):
        raise ValueError("evaluation amendment dependency path changed")
    return document


def evaluate_amended_recovery_analysis(
    analysis: dict[str, Any],
    contract: dict[str, Any],
    registry: dict[str, Any],
    inherited_accelerator: dict[str, Any],
) -> tuple[Any, tuple[Any, ...], str]:
    """Adapt only the inherited accelerator identity before exact scoring."""
    if (
        analysis.get("analysis_id")
        != "phase-5-external-recovery-terminal-science"
    ):
        raise ValueError("recovery compiled analysis identity changed")
    if analysis.get("compiler_accelerator_sha256") != (
        inherited_accelerator.get("sha256")
    ):
        raise ValueError(
            "analysis compiler accelerator differs from inherited identity"
        )
    compatible_analysis = dict(analysis)
    compatible_analysis["analysis_id"] = (
        "phase-5-external-post-correction-terminal-science"
    )
    compatible_contract = dict(contract)
    compatible_contract["compiler_accelerator"] = inherited_accelerator
    return cast(
        tuple[Any, tuple[Any, ...], str],
        _BASE_EVALUATE(
            compatible_analysis,
            compatible_contract,
            registry,
        ),
    )


def _parse_args() -> argparse.Namespace:
    """Parse the named authorization decision path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Evaluate the existing analysis only after exact renewed approval."""
    arguments = _parse_args()
    authorization = load_amendment_authorization(
        arguments.authorization,
        Path(__file__),
        _ROOT,
    )
    output = _ROOT / cast(str, authorization["output_path"])
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite recovery decision: {output}"
        )
    frozen_contract_path = _bound_path(
        _ROOT,
        authorization["frozen_contract"],
        description="frozen recovery evaluation contract",
    )
    frozen_evaluator_path = _bound_path(
        _ROOT,
        authorization["frozen_evaluator"],
        description="frozen recovery evaluator",
    )
    analysis_path = _bound_path(
        _ROOT,
        authorization["analysis"],
        description="sealed recovery analysis",
    )
    contract = _FROZEN["load_recovery_evaluation_contract"](
        frozen_contract_path,
        frozen_evaluator_path,
    )
    base_path = _ROOT / cast(str, contract["base_evaluation_path"])
    base = _FROZEN["_BASE"]["load_post_correction_evaluation_contract"](
        base_path,
        _FROZEN["_BASE_PATH"],
    )
    inherited_accelerator = base.get("compiler_accelerator")
    if not isinstance(inherited_accelerator, dict):
        raise ValueError("inherited compiler accelerator is incomplete")
    analysis = json_object(analysis_path)
    registry_identity = cast(dict[str, Any], contract["endpoint_registry"])
    registry = _FROZEN["_HELPERS"]["load_recovery_endpoint_registry"](
        _ROOT / cast(str, registry_identity["path"])
    )
    combined, endpoints, compact_status = evaluate_amended_recovery_analysis(
        analysis,
        contract,
        registry,
        inherited_accelerator,
    )
    review = cast(dict[str, Any], authorization["amendment_review"])
    decision = {
        "schema_version": 1,
        "decision_id": "phase-5-external-recovery-terminal-decision",
        "status": combined.status,
        "analysis_sha256": file_sha256(analysis_path),
        "contract_sha256": file_sha256(frozen_contract_path),
        "evaluation_amendment": {
            "authorization_sha256": file_sha256(arguments.authorization),
            "evaluator_sha256": file_sha256(Path(__file__)),
            "review_sha256": review["sha256"],
        },
        "campaign": asdict(combined),
        "continuum_endpoints": [asdict(item) for item in endpoints],
        "compact_status": compact_status,
        "closed_campaign_reuse_authorized": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(
            (
                json.dumps(
                    decision,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        )


if __name__ == "__main__":
    main()
