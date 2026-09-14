"""Shared test fixtures for Hebog."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip POSIX-bound sealed-record reconstruction on Windows only."""
    if os.name != "nt":
        return
    marker = pytest.mark.skip(
        reason=(
            "sealed historical record binds POSIX path spelling; "
            "the exact reconstruction remains covered by Linux CI"
        )
    )
    for item in items:
        if item.get_closest_marker("posix_frozen_record") is not None:
            item.add_marker(marker)


@pytest.fixture(scope="session")
def frozen_campaign_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Verify closed reviews against their pre-repair files, without data.

    This is an inert source snapshot, not an execution checkout. Current
    scientific tests import the installed candidate; historical preflights
    only inspect this tree's exact frozen identities. Ignored campaign
    outputs are absent and no real output namespace is inspected or changed.
    """
    root = Path(__file__).parents[1]
    revision = "ab7cb09ae2cc56cf9442295e7e4c2f0136e74c4f"
    archived = subprocess.run(
        ("git", "archive", "--format=tar", revision),
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    snapshot = tmp_path_factory.mktemp("frozen-campaign-source")
    with tarfile.open(fileobj=io.BytesIO(archived), mode="r:") as archive:
        archive.extractall(snapshot, filter="data")
    return snapshot


@pytest.fixture(scope="session")
def frozen_public_configuration(frozen_campaign_root: Path) -> str:
    """Check frozen identity with its own source imports, without science."""
    result = subprocess.run(
        (
            sys.executable,
            "-c",
            "from scripts.benchmark.run_phase5_public_finder_hebog import "
            "public_hebog_configuration_sha256; "
            "print(public_hebog_configuration_sha256())",
        ),
        cwd=frozen_campaign_root,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (str(frozen_campaign_root / "src"), str(frozen_campaign_root))
            ),
        },
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
