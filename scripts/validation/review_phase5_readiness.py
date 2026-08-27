#!/usr/bin/env python3
"""Prepare or finalize the write-once Phase 5 readiness record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hebog.validation.phase_five_release_readiness import (
    finalize_phase_five_readiness,
    prepare_phase_five_readiness_review,
)


def _parse_args() -> argparse.Namespace:
    """Parse the two explicit readiness lifecycle operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--contract", required=True, type=Path)
    prepare.add_argument("--repository-root", type=Path, default=Path.cwd())
    prepare.add_argument("--output", required=True, type=Path)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--review-packet", required=True, type=Path)
    finalize.add_argument(
        "--radio-astronomy-acceptance", required=True, type=Path
    )
    finalize.add_argument("--engineering-acceptance", required=True, type=Path)
    finalize.add_argument("--repository-root", type=Path, default=Path.cwd())
    finalize.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _write_once(path: Path, document: dict[str, object]) -> None:
    """Publish canonical JSON without replacing reviewed bytes."""
    if path.exists():
        message = f"refusing to overwrite readiness output: {path}"
        raise FileExistsError(message)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(
            (
                json.dumps(
                    document,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        )


def main() -> None:
    """Execute exactly one explicit readiness lifecycle operation."""
    arguments = _parse_args()
    if arguments.command == "prepare":
        document = prepare_phase_five_readiness_review(
            arguments.contract,
            repository_root=arguments.repository_root,
        )
    else:
        document = finalize_phase_five_readiness(
            arguments.review_packet,
            acceptance_paths=(
                arguments.radio_astronomy_acceptance,
                arguments.engineering_acceptance,
            ),
            repository_root=arguments.repository_root,
        )
    _write_once(arguments.output, document)


if __name__ == "__main__":
    main()
