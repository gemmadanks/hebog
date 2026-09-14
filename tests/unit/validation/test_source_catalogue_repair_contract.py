"""Prospective repair authority preserves the failed scientific evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_ROOT = Path(__file__).parents[3]


def test_repair_contract_binds_review_without_executable_identity() -> None:
    """R0 binds selected remedies, not permission to bypass later gates."""
    review = json.loads(
        (
            _ROOT
            / "config/contracts/phase-5-source-catalogue-repair-contract.json"
        ).read_text(encoding="utf-8")
    )
    assert review["status"] == "prospective-repair-contract"
    assert review["execution_identity"] is None
    assert review["finder_execution_started"] is False
    for field in ("contract", "audit"):
        binding = review[field]
        assert (
            hashlib.sha256((_ROOT / binding["path"]).read_bytes()).hexdigest()
            == binding["sha256"]
        )
    assert review["closed_terminal_sha256"] == (
        "ca03240db8452d84479139e848c0467815fdac9cea02168283fe69f52be8b63a"
    )
    assert "development-cumulative-fresh-evidence-order" in review["preserve"]
    assert "viewed-qualification-tuning-or-rescoring" in review["forbidden"]
    assert "weakening-gates" in review["forbidden"]
