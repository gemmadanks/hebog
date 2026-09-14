#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile final qualification without reopening compact evidence."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-final-qualification-endpoint-registry.json"
)
_PROTOCOL_PATH = (
    _ROOT / "config/contracts/phase-5-final-qualification-comparison.json"
)
_DECISION_PATH = (
    _ROOT
    / "config/contracts/phase-5-final-qualification-execution-decision.json"
)
_POPULATION_PATH = (
    _ROOT / "config/contracts/phase-5-final-qualification-population.json"
)
_CONTINUUM_IMAGE_COUNT = 1688
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_final_qualification_protocol.py")
)
_COMPAT_HELPERS = dict(_HELPERS)
_COMPAT_HELPERS.update(
    {
        "load_post_failure_protocol": _HELPERS[
            "load_final_qualification_protocol"
        ],
        "load_post_failure_execution_decision": _HELPERS[
            "load_final_qualification_execution_decision"
        ],
        "load_post_failure_endpoint_registry": _HELPERS[
            "load_final_qualification_endpoint_registry"
        ],
        "load_recovery_protocol": _HELPERS[
            "load_final_qualification_protocol"
        ],
        "load_recovery_execution_decision": _HELPERS[
            "load_final_qualification_execution_decision"
        ],
        "load_recovery_endpoint_registry": _HELPERS[
            "load_final_qualification_endpoint_registry"
        ],
        "recovery_campaign_request_model": _HELPERS[
            "final_qualification_campaign_model"
        ],
        "recovery_terminal_result_model": _HELPERS[
            "final_qualification_campaign_model"
        ],
    }
)
_BASE = runpy.run_path(
    str(
        _ROOT
        / "scripts/validation/compile_phase5_external_recovery_campaign.py"
    )
)


def load_final_qualification_composition(
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Validate the final registry and exact compiler identity."""
    registry = _HELPERS["load_final_qualification_endpoint_registry"](
        registry_path
    )
    expected = (
        "scripts/validation/compile_phase5_final_qualification_campaign.py"
    )
    if registry["compiler_path"] != expected:
        raise ValueError("final qualification compiler path changed")
    if registry["compiler_sha256"] != _HELPERS["file_sha256"](compiler_path):
        raise ValueError("final qualification compiler checksum changed")
    return cast(dict[str, Any], registry)


def _configured_terminal() -> dict[str, Any]:
    """Install final identities and the proven recovery science seams."""
    globals_ = _BASE["_configured_terminal"].__globals__
    globals_.update(
        {
            "_REGISTRY_PATH": _REGISTRY_PATH,
            "_PROTOCOL_PATH": _PROTOCOL_PATH,
            "_DECISION_PATH": _DECISION_PATH,
            "_CONTINUUM_IMAGE_COUNT": _CONTINUUM_IMAGE_COUNT,
            "_HELPERS": _COMPAT_HELPERS,
            "load_recovery_composition": load_final_qualification_composition,
        }
    )
    terminal = _BASE["_configured_terminal"]()
    terminal_globals = terminal["verify_terminal_campaign"].__globals__
    terminal_globals["load_endpoint_registry"] = (
        load_final_qualification_composition
    )
    terminal_globals["CampaignRequest"] = _HELPERS[
        "final_qualification_campaign_model"
    ](terminal_globals["CampaignRequest"])
    terminal_globals["TerminalCampaignResult"] = _HELPERS[
        "final_qualification_campaign_model"
    ](terminal_globals["TerminalCampaignResult"])
    return cast(dict[str, Any], terminal)


def _closed_compact_evidence() -> dict[str, Any]:
    """Validate, but never pool or rescore, both passing compact records."""
    population = _HELPERS["load_final_qualification_population"](
        _POPULATION_PATH
    )
    records: list[dict[str, Any]] = []
    for identity in population["compact_evidence"]["records"]:
        path = _ROOT / identity["path"]
        decision = _HELPERS["json_object"](path)
        if decision.get("passed") is not True:
            raise ValueError("closed compact evidence no longer passes")
        records.append(
            {
                **identity,
                "run_id": decision.get("run_id"),
                "failure_reason_count": len(
                    decision.get("failure_reasons", [])
                ),
            }
        )
    return {
        "status": "pass",
        "policy": "bound-without-pooling-or-rescoring",
        "records": records,
    }


def compile_final_qualification_analysis(
    campaign_path: Path,
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Compile fresh Continuum science and bind closed compact evidence."""
    terminal = _configured_terminal()
    registry = load_final_qualification_composition(
        registry_path, compiler_path
    )
    verified = terminal["verify_terminal_campaign"](
        campaign_path,
        registry,
        compiler_path.parents[2],
    )
    continuum, diagnostics = terminal["compile_continuum_campaign"](
        verified,
        registry,
        compiler_path.parents[2],
    )
    binding_runs = tuple(
        run
        for run in verified.request.runs
        if run.mode in {"candidate", "operational"}
    )
    successful_binding = sum(
        verified.runs[(run.input_id, run.finder_id, run.mode)].result.status
        == "success"
        for run in binding_runs
    )
    expected_ids = tuple(
        item.endpoint_id
        for item in terminal["expand_continuum_endpoint_specs"](registry)
        if item.binding
    )
    truth_compiler = terminal["_post_failure_truth_compiler"]
    truth_records = truth_compiler.records
    if len(truth_records) != _CONTINUUM_IMAGE_COUNT:
        raise ValueError("observable truth support population is incomplete")
    return {
        "schema_version": 1,
        "analysis_id": "phase-5-final-qualification-terminal-science",
        "status": "compiled-terminal-science",
        "compiled_at": datetime.now(UTC).isoformat(),
        "compiler_sha256": _HELPERS["file_sha256"](compiler_path),
        "endpoint_registry_sha256": _HELPERS["file_sha256"](registry_path),
        "campaign_sha256": verified.campaign_sha256,
        "request_sha256": verified.terminal.request_sha256,
        "protocol_sha256": verified.terminal.protocol_sha256,
        "execution_decision_sha256": (
            verified.terminal.execution_decision_sha256
        ),
        "population_audit": {
            "image_count": verified.terminal.image_count,
            "continuum_image_count": _CONTINUUM_IMAGE_COUNT,
            "terminal_run_count": verified.terminal.run_count,
            "binding_run_count": len(binding_runs),
            "successful_binding_run_count": successful_binding,
            "failed_binding_run_count": len(binding_runs) - successful_binding,
            "unavailable_binding_run_count": 0,
            "unexpected_run_count": 0,
            "fresh_compact_run_count": 0,
        },
        "expected_continuum_endpoint_ids": list(expected_ids),
        "continuum_endpoints": [asdict(item) for item in continuum],
        "continuum_diagnostics": [asdict(item) for item in diagnostics],
        "closed_compact_evidence": _closed_compact_evidence(),
        "observable_truth_support": truth_records,
        "scientific_outcomes_before_runtime": True,
        "cutover_authorized": False,
        "qualification_opened": True,
    }


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite deterministic evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _parse_args() -> argparse.Namespace:
    """Parse sealed campaign, registry, and write-once output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=_REGISTRY_PATH)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Compile the final qualification exactly once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite final analysis: {arguments.output}"
        )
    analysis = compile_final_qualification_analysis(
        arguments.campaign,
        arguments.registry,
        Path(__file__),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
