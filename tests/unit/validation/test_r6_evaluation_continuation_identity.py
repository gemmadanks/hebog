"""Verify the exact continuation freeze without local campaign products."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[3]
_CONTRACTS = _ROOT / "config/contracts"
_REVIEW = (
    _CONTRACTS / "phase-5-r6-evaluation-continuation-identity-review.json"
)


def test_continuation_binds_historical_code_not_current_notebook_results() -> (
    None
):
    review = json.loads(_REVIEW.read_bytes())
    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    assert review["validation"]["scientific_execution_started"] is False
    archive = subprocess.check_output(
        ("git", "archive", review["implementation_revision"]), cwd=_ROOT
    )
    records: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as historical:
        for member in historical.getmembers():
            if member.isfile():
                stream = historical.extractfile(member)
                assert stream is not None
                records[member.name] = stream.read()
    programs = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in records.items()
        if name.startswith("scripts/validation/") and name.endswith(".py")
    }
    assert len(programs) == review["program_count"]
    assert canonical_sha256(programs) == review["program_set_sha256"]
    for name, expected in review["entry_point_sha256"].items():
        assert programs[name] == expected
    source = hashlib.sha256()
    for name in sorted(records):
        if name.startswith("src/hebog/") and name.endswith(".py"):
            source.update(name.encode() + b"\0" + records[name] + b"\0")
    assert source.hexdigest() == review["evaluator_source_tree_sha256"]
    repair = json.loads(
        (
            _CONTRACTS
            / "phase-5-r6-unavailable-source-support-identity-review.json"
        ).read_bytes()
    )
    assert review["candidate"] == repair["retained_candidate"]
    assert (
        review["candidate"]["source_tree_sha256"]
        != review["evaluator_source_tree_sha256"]
    )


def test_continuation_decision_authorizes_only_missing_evaluations() -> None:
    review = json.loads(_REVIEW.read_bytes())
    decision = json.loads(
        (
            _CONTRACTS
            / "phase-5-r6-evaluation-continuation-execution-decision.json"
        ).read_bytes()
    )
    assert decision["status"] == (
        "authorized-for-one-r6-evaluation-only-continuation"
    )
    assert decision["execution_count"] == 1
    assert (
        decision["identity_review_sha256"]
        == hashlib.sha256(_REVIEW.read_bytes()).hexdigest()
    )
    assert (
        review["plan_canonical_sha256"]
        == review["expected_execution_sha256"]
        == decision["expected_execution_sha256"]
    )
    for key in (
        "plan_sha256",
        "candidate",
        "incumbent",
        "scratch",
        "output",
        "workers",
        "new_input_evaluations",
        "reused_input_evaluations",
        "new_finder_executions",
        "new_dask_comparisons",
        "required_free_bytes",
        "approved_amendment_sha256",
    ):
        assert decision[key] == review[key]
    assert decision["workers"] == 2
    assert decision["new_finder_executions"] == 0
    assert decision["new_dask_comparisons"] == 0
    assert decision["new_input_evaluations"] == 1592
    assert decision["reused_input_evaluations"] == 808
    assert review["frozen_science"]["binding_comparison_count"] == 1187
    assert review["frozen_science"]["safety_check_count"] == 5
    assert review["frozen_science"]["completed_record_rescoring"] is False
