#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile one sealed confirmation campaign through exact accelerators."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_campaign_compilation import (
    install_continuum_accelerators,
)

_ROOT = Path(__file__).parents[2]
_SUCCESSOR_COMPILER_PATH = (
    _ROOT / "scripts/validation/compile_phase5_external_successor_campaign.py"
)
_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-confirmation-endpoint-registry.json"
)
_PROTOCOL_PATH = (
    _ROOT / "config/contracts/phase-5-external-confirmation-comparison.json"
)
_DECISION_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-confirmation-execution-decision.json"
)
_SUCCESSOR = runpy.run_path(str(_SUCCESSOR_COMPILER_PATH))
_TERMINAL = _SUCCESSOR["_TERMINAL"]
_TERMINAL_JSON_OBJECT = _TERMINAL["_json_object"]
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_confirmation_protocol.py")
)


def _confirmation_json_object(path: Path) -> dict[str, Any]:
    """Return confirmation views used by the closed verifier."""
    if path.resolve() == _PROTOCOL_PATH.resolve():
        protocol = _HELPERS["load_confirmation_protocol"](path)
        return cast(dict[str, Any], protocol.model_dump(mode="json"))
    document = cast(dict[str, Any], _TERMINAL_JSON_OBJECT(path))
    if path.resolve() != _DECISION_PATH.resolve():
        return document
    decision = _HELPERS["load_confirmation_execution_decision"](path)
    if decision.execution_authorized is not True:
        raise ValueError("confirmation execution decision is not approved")
    return {
        **document,
        "decision_id": "phase-5-external-execution-decision",
        "decision": "authorize-one-terminal-external-comparison",
    }


def load_confirmation_composition(
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Validate the confirmation registry and unchanged endpoint policy."""
    registry = _HELPERS["load_confirmation_endpoint_registry"](registry_path)
    if registry["compiler_path"] != (
        "scripts/validation/compile_phase5_external_confirmation_campaign.py"
    ):
        raise ValueError("confirmation compiler registry path changed")
    if registry["compiler_sha256"] != _HELPERS["file_sha256"](compiler_path):
        raise ValueError("confirmation compiler registry checksum changed")
    return cast(dict[str, Any], registry)


def _configured_terminal() -> dict[str, Any]:
    """Install confirmed science and result-neutral compiler seams."""
    terminal = _SUCCESSOR["_configured_terminal"]()
    globals_ = terminal["compile_terminal_analysis"].__globals__
    globals_["_json_object"] = _confirmation_json_object
    globals_["load_endpoint_registry"] = load_confirmation_composition
    install_continuum_accelerators(globals_)
    return cast(dict[str, Any], terminal)


def compile_confirmation_analysis(
    campaign_path: Path,
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Compile one complete confirmation campaign without reopening history."""
    terminal = _configured_terminal()
    analysis = terminal["compile_terminal_analysis"](
        campaign_path,
        registry_path,
        compiler_path,
    )
    analysis["analysis_id"] = "phase-5-external-confirmation-terminal-science"
    analysis["closed_campaign_reuse_authorized"] = False
    analysis["successor_science_kernel_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/external_successor_compiler.py"
    )
    analysis["compiler_accelerator_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/external_campaign_compilation.py"
    )
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
    """Compile the confirmation campaign exactly once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite confirmation analysis: {arguments.output}"
        )
    analysis = compile_confirmation_analysis(
        arguments.campaign,
        arguments.registry,
        Path(__file__),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
