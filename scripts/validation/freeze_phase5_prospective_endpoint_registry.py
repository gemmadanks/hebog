#!/usr/bin/env python3
"""Freeze the prospective Phase 5 all-check endpoint registry exactly once."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from hebog.validation.external_runners import file_sha256
from hebog.validation.prospective_science_contract import (
    build_prospective_endpoint_registry,
)

_ROOT = Path(__file__).parents[2]
_SOURCE_REGISTRY = Path(
    "config/contracts/phase-5-external-endpoint-registry.json"
)
_METRIC_REGISTRY = Path("config/contracts/phase-4r-metric-registry.json")
_INCUMBENT_LEDGER = Path(
    "benchmark-results/phase-5/"
    "cumulative-regression-ledger-public-finder-terminal-parent-correction.json"
)


def _json_object(path: Path) -> dict[str, object]:
    """Load one exact source document as a JSON object."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"source document must be an object: {path}")
    return cast(dict[str, object], document)


def _binding(path: Path) -> dict[str, str]:
    """Return the repository-relative path and byte digest for one source."""
    return {
        "path": path.as_posix(),
        "sha256": file_sha256(_ROOT / path),
    }


def main() -> None:
    """Build and publish the deterministic write-once registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        type=Path,
        help="new registry path; an existing file is never overwritten",
    )
    arguments = parser.parse_args()

    registry = build_prospective_endpoint_registry(
        source_registry=_json_object(_ROOT / _SOURCE_REGISTRY),
        metric_registry=_json_object(_ROOT / _METRIC_REGISTRY),
        incumbent_ledger=_json_object(_ROOT / _INCUMBENT_LEDGER),
        source_bindings=(
            _binding(_METRIC_REGISTRY),
            _binding(_SOURCE_REGISTRY),
            _binding(_INCUMBENT_LEDGER),
        ),
    )
    output = arguments.output
    if not output.is_absolute():
        output = _ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            registry.model_dump(mode="json"),
            stream,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
