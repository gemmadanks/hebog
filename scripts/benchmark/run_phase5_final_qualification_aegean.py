#!/usr/bin/env python3
"""Retain the closed Aegean scope in the final qualification boundary."""

from __future__ import annotations

import argparse


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finder")
    parser.add_argument("--lane")
    return parser.parse_known_args()[0]


def main() -> None:
    """Fail closed because final Aegean evidence is already immutable."""
    arguments = _parse_args()
    if arguments.finder == "aegean" or arguments.lane is not None:
        raise ValueError(
            "final qualification has no fresh Aegean run; its applicable "
            "compact scope is bound as closed evidence"
        )
    raise ValueError("final qualification Aegean runner is non-executable")


if __name__ == "__main__":
    main()
