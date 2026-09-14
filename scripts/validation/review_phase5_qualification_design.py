"""Audit the untouched Phase 5 qualification design without opening it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hebog.validation.phase_five_readiness import (
    audit_phase_five_qualification_design,
)


def _parse_args() -> argparse.Namespace:
    """Parse the reviewed manifest, power record, and write-once output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--power-review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Write one canonical pre-opening design audit."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite qualification audit: {arguments.output}"
        )
    document = audit_phase_five_qualification_design(
        arguments.manifest,
        arguments.power_review,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
