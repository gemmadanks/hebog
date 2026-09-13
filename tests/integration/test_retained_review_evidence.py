"""Exact artifact checks require the separately retained campaign evidence.

Portable unit tests verify the checked-in review bindings without these files.
This explicit data lane fails, rather than skips, if requested evidence is
missing or changed; it never recreates or rescores a scientific result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hebog.validation.external_runners import file_sha256

pytestmark = [pytest.mark.integration, pytest.mark.requires_data]
_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("review_name", "digest_field"),
    (
        ("phase-5-adaptive-background-root-cause-pre-review.json", "sha256"),
        (
            "phase-5-compact-held-out-sentinel-root-cause-pre-review.json",
            "file_sha256",
        ),
    ),
)
def test_retained_terminal_matches_its_frozen_review(
    review_name: str, digest_field: str
) -> None:
    """Retained terminal bytes remain bound to the exact historical review."""
    review = json.loads(
        (_ROOT / "config/contracts" / review_name).read_text(encoding="utf-8")
    )
    terminal = review["binding_context"]["terminal_decision"]
    assert file_sha256(_ROOT / terminal["path"]) == terminal[digest_field]
