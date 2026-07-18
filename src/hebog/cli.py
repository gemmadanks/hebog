"""Command-line interface for Hebog."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from hebog import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="hebog",
        description="Dask-aware source finding for SKA SDP pipelines.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = create_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
