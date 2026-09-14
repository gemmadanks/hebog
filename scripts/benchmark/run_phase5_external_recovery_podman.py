#!/usr/bin/env python3
"""Delegate to Podman with the exact recovery source-path amendment."""

from __future__ import annotations

import os
import sys

_HEBOG_IMAGE = (
    "sha256:e519dc15b846dec7ac00a6cada7684d0c0b2615490dd6688ac4c6cdf5f3021ca"
)
_HEBOG_RUNNER = (
    "/repository/scripts/benchmark/run_phase5_external_recovery_hebog.py"
)
_SOURCE_ENVIRONMENT = "PYTHONPATH=/repository/src"


def amend_podman_arguments(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """Expose approved source only to the failed recovery Hebog runner."""
    if (
        not arguments
        or arguments[0] != "run"
        or _HEBOG_IMAGE not in arguments
        or _HEBOG_RUNNER not in arguments
    ):
        return arguments
    if any(
        argument.startswith(("PYTHONPATH=", "--env=PYTHONPATH="))
        for argument in arguments
    ):
        raise ValueError("recovery source environment is ambiguous")
    image_index = arguments.index(_HEBOG_IMAGE)
    amended = (
        *arguments[:image_index],
        "--env",
        _SOURCE_ENVIRONMENT,
        *arguments[image_index:],
    )
    return amended


def main() -> None:
    """Replace this exact process with the real Podman executable."""
    arguments = amend_podman_arguments(tuple(sys.argv[1:]))
    os.execvp("podman", ("podman", *arguments))


if __name__ == "__main__":
    main()
