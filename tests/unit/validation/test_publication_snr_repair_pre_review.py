"""Contracts for the prospective publication-SNR repair."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-publication-snr-repair-"
    "pre-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-publication-snr-repair-"
    "implementation-decision.json"
)


def _load(path: Path) -> dict[str, Any]:
    """Load one governed publication-SNR record."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_review_binds_exact_failed_smoke_and_no_tuning_boundary() -> None:
    """The repair cannot drift from the terminal diagnostic evidence."""
    review = _load(_REVIEW)

    assert review["schema_version"] == 1
    assert review["status"] == "reviewed-before-replacement-results"
    assert review["binding_evidence"]["prospective_smoke_sha256"] == (
        "07f51256f241a43bc146b5d82aa3ce8c275ecbd47b6e470db650a194cbd3df16"
    )
    assert review["causal_findings"]["confirmed_failures"] == {
        "duplicate_fraction": 4,
        "mask_precision": 2,
        "split_fraction": 2,
        "total": 8,
    }
    assert (
        review["fixed_scientific_boundary"]["new_thresholds_or_margins"]
        is False
    )
    assert (
        review["authorization"]["threshold_or_margin_tuning_authorized"]
        is False
    )


def test_review_separates_mask_cause_from_unresolved_topology() -> None:
    """One mask correction cannot silently alter source association."""
    findings = _load(_REVIEW)["causal_findings"]

    assert findings["mask_precision"]["scope"] == (
        "publication mask statistic only"
    )
    assert "zero edges" in findings["source_topology"]["evidence"]
    assert (
        "relaxing the conservative pair association graph"
        in (findings["rejected_repairs"])
    )


def test_decision_binds_exact_review_and_implementation() -> None:
    """Execution identity includes the scientific review and source files."""
    decision = _load(_DECISION)
    implementations = {
        item["path"]: item["sha256"] for item in decision["implementation"]
    }

    assert decision["pre_review"]["sha256"] == file_sha256(_REVIEW)
    for path, expected in implementations.items():
        assert file_sha256(_ROOT / path) == expected
    assert decision["fixed_scientific_policy"] == {
        "catalogue_and_measurement_change": False,
        "detection_or_island_threshold_change": False,
        "publication_snr_policy": (
            "direct-original-pixel-snr-published-boundary-v1"
        ),
        "publication_statistic": (
            "scientifically valid residual_jy_per_beam divided by positive "
            "rms_jy_per_beam"
        ),
        "recovered_minimum_snr": "review.matrix.island_sigma",
    }


def test_decision_keeps_full_replay_fail_closed() -> None:
    """Only a zero-failure replacement smoke can open the full replay."""
    authorization = _load(_DECISION)["authorization"]

    assert authorization["replacement_smoke_authorized"]
    assert authorization[
        "full_cumulative_replay_authorized_only_after_replacement_smoke_passes"
    ]
    assert authorization["fresh_qualification_authorized"] is False
    assert authorization["release_authorized"] is False
    assert authorization["rescoring_closed_evidence_authorized"] is False
