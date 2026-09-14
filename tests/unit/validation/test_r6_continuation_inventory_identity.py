"""A portable identity test must not need the ignored campaign directory."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

_ROOT = Path(__file__).parents[3]


def test_inventory_freeze_is_non_executable_and_historically_verifiable() -> (
    None
):
    review = json.loads(
        (
            _ROOT
            / "config/contracts"
            / "phase-5-r6-continuation-inventory-identity-review.json"
        ).read_bytes()
    )
    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    assert review["execution_identity"] is None
    assert review["finder_execution_started"] is False
    counts = review["retained_evidence"]
    assert counts["capture_pair_count"] == 2400
    assert counts["reference_run_count"] == 9600
    assert counts["dask_comparison_count"] == 12
    assert counts["complete_input_count"] == 808
    assert counts["complete_finder_record_count"] == 4032
    assert counts["pending_input_count"] == 1592
    assert counts["partial_directory_count"] == 2
    assert counts["partial_file_count"] == 0
    assert (
        counts["complete_input_count"] + counts["pending_input_count"]
        == counts["capture_pair_count"]
    )
    assert len(review["inventory"]["sha256"]) == 64
    for relative, expected in review["auditor_program_sha256"].items():
        recorded = subprocess.check_output(
            ("git", "show", f"{review['implementation_revision']}:{relative}"),
            cwd=_ROOT,
        )
        assert hashlib.sha256(recorded).hexdigest() == expected
