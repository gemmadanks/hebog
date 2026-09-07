"""Checkout requirements for tests of frozen historical identities."""

import subprocess
from pathlib import Path


def test_historical_identity_checks_require_complete_git_history() -> None:
    """A shallow boundary must not masquerade as a review's creation commit."""
    shallow = subprocess.run(
        ("git", "rev-parse", "--is-shallow-repository"),
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert shallow == "false", (
        "Historical identity verification requires complete Git history; "
        "configure actions/checkout with fetch-depth: 0."
    )
