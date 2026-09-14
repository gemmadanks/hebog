#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile one sealed recovery campaign through the approved composition."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_recovery_compiler import (
    install_recovery_compiler_seams,
)

_ROOT = Path(__file__).parents[2]
_REGISTRY_PATH = (
    _ROOT / "config/contracts/phase-5-external-recovery-endpoint-registry.json"
)
_PROTOCOL_PATH = (
    _ROOT / "config/contracts/phase-5-external-recovery-comparison.json"
)
_DECISION_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-recovery-execution-decision.json"
)
_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_recovery_protocol.py")
)
_COMPAT_HELPERS = dict(_HELPERS)
_COMPAT_HELPERS.update(
    {
        "load_post_failure_protocol": _HELPERS["load_recovery_protocol"],
        "load_post_failure_execution_decision": _HELPERS[
            "load_recovery_execution_decision"
        ],
        "load_post_failure_endpoint_registry": _HELPERS[
            "load_recovery_endpoint_registry"
        ],
        "post_failure_campaign_request_model": _HELPERS[
            "recovery_campaign_request_model"
        ],
        "post_failure_terminal_result_model": _HELPERS[
            "recovery_terminal_result_model"
        ],
    }
)
_BASE = runpy.run_path(
    str(
        _ROOT
        / "scripts/validation/compile_phase5_external_post_failure_campaign.py"
    )
)
_BASE_CONFIGURE = _BASE["_configured_terminal"]
_BASE_COMPILE = _BASE["compile_post_failure_analysis"]


def load_recovery_composition(
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Validate the recovery registry and exact compiler identity."""
    registry = _HELPERS["load_recovery_endpoint_registry"](registry_path)
    expected = (
        "scripts/validation/compile_phase5_external_recovery_campaign.py"
    )
    if registry["compiler_path"] != expected:
        raise ValueError("recovery compiler registry path changed")
    if registry["compiler_sha256"] != _HELPERS["file_sha256"](compiler_path):
        raise ValueError("recovery compiler registry checksum changed")
    return cast(dict[str, Any], registry)


def _configured_terminal() -> dict[str, Any]:
    """Install recovery identities, scale, and proven compiler seams."""
    globals_ = _BASE_CONFIGURE.__globals__
    globals_.update(
        {
            "_REGISTRY_PATH": _REGISTRY_PATH,
            "_PROTOCOL_PATH": _PROTOCOL_PATH,
            "_DECISION_PATH": _DECISION_PATH,
            "_CONTINUUM_IMAGE_COUNT": 1688,
            "_HELPERS": _COMPAT_HELPERS,
        }
    )
    terminal = _BASE_CONFIGURE()
    terminal_globals = terminal["compile_terminal_analysis"].__globals__
    terminal_globals["load_endpoint_registry"] = load_recovery_composition
    terminal_globals["CampaignRequest"] = _HELPERS[
        "recovery_campaign_request_model"
    ](terminal_globals["CampaignRequest"])
    terminal_globals["TerminalCampaignResult"] = _HELPERS[
        "recovery_terminal_result_model"
    ](terminal_globals["TerminalCampaignResult"])
    install_recovery_compiler_seams(
        terminal_globals,
        expected_candidate_configuration_sha256=_CONFIGURATION_SHA256,
    )
    return cast(dict[str, Any], terminal)


def compile_recovery_analysis(
    campaign_path: Path,
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Compile the complete fresh campaign without reopening history."""
    base_globals = _BASE_COMPILE.__globals__
    base_globals.update(
        {
            "_configured_terminal": _configured_terminal,
            "_CONTINUUM_IMAGE_COUNT": 1688,
            "_HELPERS": _COMPAT_HELPERS,
        }
    )
    analysis = _BASE_COMPILE(campaign_path, registry_path, compiler_path)
    analysis["analysis_id"] = "phase-5-external-recovery-terminal-science"
    return cast(dict[str, Any], analysis)


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
    """Compile the recovery campaign exactly once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite recovery analysis: {arguments.output}"
        )
    analysis = compile_recovery_analysis(
        arguments.campaign,
        arguments.registry,
        Path(__file__),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
