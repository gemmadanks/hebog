#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile one sealed Step 2C-PF campaign through its reviewed composition.

The terminal compiler remains byte-for-byte immutable.  This entry point
reuses its campaign verification, compact engine, endpoint aggregation, and
inference while replacing only the continuum catalogue/native-support
boundary with the independently tested successor kernel.
"""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from typing import Any, Sequence, cast

import numpy.typing as npt
from astropy.io import fits

from hebog.validation.external_successor_compiler import (
    continuum_catalogue_objects,
    measure_continuum_image,
)

_ROOT = Path(__file__).parents[2]
_TERMINAL_COMPILER_PATH = (
    _ROOT / "scripts/validation/compile_phase5_external_campaign.py"
)
_SUCCESSOR_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-successor-endpoint-registry.json"
)
_TERMINAL = runpy.run_path(str(_TERMINAL_COMPILER_PATH))
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_successor_protocol.py")
)


def _candidate_objects(
    catalogue: Sequence[Any],
    labels: npt.NDArray[Any],
    *,
    finder_id: str,
    header: fits.Header,
) -> tuple[Any, ...]:
    """Admit native supports without inventing missing catalogue rows."""
    return continuum_catalogue_objects(
        catalogue,
        labels,
        finder_id=cast(Any, finder_id),
        header=header,
    )


def load_successor_composition(
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Validate the composed registry and unchanged endpoint policy."""
    registry = _HELPERS["load_successor_endpoint_registry"](registry_path)
    if registry["compiler_path"] != (
        "scripts/validation/compile_phase5_external_successor_campaign.py"
    ):
        raise ValueError("successor compiler registry path changed")
    if registry["compiler_sha256"] != _HELPERS["file_sha256"](compiler_path):
        raise ValueError("successor compiler registry checksum changed")

    closed_path = (
        compiler_path.parents[2]
        / "config/contracts/phase-5-external-endpoint-registry.json"
    )
    closed = _HELPERS["json_object"](closed_path)
    normalized = dict(registry)
    for key in (
        "successor_registry_id",
        "successor_composition",
        "closed_campaign_reuse_authorized",
    ):
        normalized.pop(key, None)
    for path_key, sha_key in (
        ("protocol_path", "protocol_sha256"),
        ("continuum_manifest_path", "continuum_manifest_sha256"),
        ("compact_manifest_path", "compact_manifest_sha256"),
        ("compiler_path", "compiler_sha256"),
        ("execution_decision_path", "execution_decision_sha256"),
        ("launcher_path", "launcher_sha256"),
    ):
        normalized[path_key] = closed[path_key]
        normalized[sha_key] = closed[sha_key]
    if normalized != closed:
        raise ValueError("successor endpoint or scientific policy changed")
    return registry


def _configured_terminal() -> dict[str, Any]:
    """Install the two reviewed successor science seams."""
    globals_ = _TERMINAL["compile_terminal_analysis"].__globals__
    globals_["load_endpoint_registry"] = load_successor_composition
    globals_["_candidate_objects"] = _candidate_objects
    globals_["measure_continuum_image"] = measure_continuum_image
    return _TERMINAL


def compile_successor_analysis(
    campaign_path: Path,
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Compile one successor campaign without reopening old evidence."""
    terminal = _configured_terminal()
    analysis = terminal["compile_terminal_analysis"](
        campaign_path,
        registry_path,
        compiler_path,
    )
    analysis["analysis_id"] = "phase-5-external-successor-terminal-science"
    analysis["closed_campaign_reuse_authorized"] = False
    analysis["successor_science_kernel_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/external_successor_compiler.py"
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
    parser.add_argument(
        "--registry", type=Path, default=_SUCCESSOR_REGISTRY_PATH
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Compile the terminal successor campaign exactly once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite successor analysis: {arguments.output}"
        )
    analysis = compile_successor_analysis(
        arguments.campaign,
        arguments.registry,
        Path(__file__),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
