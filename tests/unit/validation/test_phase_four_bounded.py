"""Tests for memory-bounded Phase 4 evidence evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.phase_four_bounded import (
    canonical_evidence_file_sha256,
    file_sha256,
)


def test_canonical_evidence_file_hash_ignores_presentation_whitespace(
    tmp_path: Path,
) -> None:
    """Streaming hashes retain JSON whitespace inside string literals."""
    payload = {
        "escaped": 'a \\"quoted\\" value',
        "nested": [1, 2.5, {"space": "kept here"}],
    }
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert canonical_evidence_file_sha256(path) == canonical_sha256(payload)
    assert file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_evidence_file_hash_rejects_an_incomplete_string(
    tmp_path: Path,
) -> None:
    """A truncated canonical document cannot acquire a trusted digest."""
    path = tmp_path / "truncated.json"
    path.write_text('{"value": "unfinished', encoding="utf-8")

    with pytest.raises(ValueError, match="ends inside a string"):
        canonical_evidence_file_sha256(path)
