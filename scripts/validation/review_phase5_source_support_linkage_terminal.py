#!/usr/bin/env python3
"""Review the terminal source-support-linkage development-lane failure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256

_TERMINAL = Path(
    "benchmark-results/phase-5/source-owned-measurement-topology-"
    "source-support-linkage-development-decision.json"
)
_TERMINAL_SHA256 = (
    "ea44147e3f1e786e3f8f53084434da55c16b6d8b7021baa1eb12985f4a5138d6"
)
_TERMINAL_CANONICAL_SHA256 = (
    "c31e8811c2df86b9816586a6868c4c478ba48f937be764567fabf3464693400d"
)
_IDENTITY = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-process-repair-identity-review.json"
)
_IDENTITY_SHA256 = (
    "b4d7636484218377dd4125ba0079970d08fa2602f2caa3b8dd4a9f7c31c82d55"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-source-owned-measurement-topology-"
    "source-support-linkage-process-repair-execution-decision.json"
)
_EXECUTION_DECISION_SHA256 = (
    "86be6adce5219c42eadc07e68a73ad48408d740b4c2a26f6907740c02e79abc6"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-source-owned-measurement-topology-"
    "source-support-linkage-process-repair-2e25cdf"
)
_FORENSIC = Path(
    "/private/tmp/hebog-phase5-seed137-source-ownership-forensic-retry"
)
_FAILED_GEOMETRY = "mixed_compact_extended--beam-b--varying--scale-8--interior"
_FAILED_INPUT = (
    "mixed-compact-extended-beam-b-varying-scale-8-interior-boundary-"
    "seed-2026950137"
)
_MINIMUM_ISLAND_PIXELS = 7
_REPLICATION_FIRST_SEED = 2_026_952_001
_REPLICATION_LAST_SEED = 2_026_952_144
_EXPECTED_INPUTS = 144
_SEEDS_PER_CELL = 4
_EXPECTED_TAIL_FLUX_MOVEMENT = 0.053766446176525706
_EXPECTED_TAIL_LINKED_SOURCE_COUNT = 2
_EXPECTED_TAIL_CATALOGUE_SOURCE_COUNT = 5


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _document_bytes(value: object) -> bytes:
    """Return canonical checked-in JSON bytes."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def document_sha256(value: object) -> str:
    """Hash one canonical checked-in review document."""
    return hashlib.sha256(_document_bytes(value)).hexdigest()


def _paired(item: dict[str, Any]) -> dict[str, float]:
    """Return adverse candidate-minus-control movements for one input."""
    adaptive = cast(dict[str, Any], item["adaptive"])
    coarse = cast(dict[str, Any], item["coarse"])
    return {
        "completeness": float(coarse["completeness"])
        - float(adaptive["completeness"]),
        "flux": float(adaptive["integrated_flux_absolute_fractional_error"])
        - float(coarse["integrated_flux_absolute_fractional_error"]),
        "mask": float(coarse["mask_iou"]) - float(adaptive["mask_iou"]),
        "split": float(bool(adaptive["split"])) - float(bool(coarse["split"])),
        "support": float(coarse["support_recall"])
        - float(adaptive["support_recall"]),
    }


def _load_scratch() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load the exact complete array-free terminal namespace."""
    observations = [
        _json_object(path, label="observation")
        for path in sorted(_SCRATCH.glob("*/observation.json"))
    ]
    attributions = {
        value["input_id"]: value
        for value in (
            _json_object(path, label="attribution")
            for path in sorted(_SCRATCH.glob("*/attribution.json"))
        )
    }
    if (
        len(observations) != _EXPECTED_INPUTS
        or len(attributions) != _EXPECTED_INPUTS
        or {item["input_id"] for item in observations} != set(attributions)
    ):
        raise ValueError("terminal source-linkage scratch is incomplete")
    return observations, attributions


def _cell_medians(items: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Return paired medians separately for each four-seed trigger cell."""
    result: dict[str, dict[str, float]] = {}
    for cohort in ("below", "boundary", "above"):
        selected = [item for item in items if item["trigger_cohort"] == cohort]
        if len(selected) != _SEEDS_PER_CELL:
            raise ValueError("failed geometry trigger cell is incomplete")
        paired = [_paired(item) for item in selected]
        result[cohort] = {
            name: float(median(item[name] for item in paired))
            for name in paired[0]
        }
    return result


def _forensic_products() -> dict[str, dict[str, object]]:
    """Bind the bounded deterministic forensic reproduction products."""
    expected = {
        "catalogue": ("catalogue.fits", 31_680),
        "diagnostics": ("diagnostics.json", 802),
        "rms": ("rms.fits", 2_102_400),
        "source_mask": ("source-mask.fits", 267_840),
    }
    records: dict[str, dict[str, object]] = {}
    for name, (filename, size_bytes) in expected.items():
        path = _FORENSIC / filename
        if path.stat().st_size != size_bytes:
            raise ValueError("bounded forensic product identity changed")
        records[name] = {
            "path": str(path),
            "sha256": file_sha256(path),
            "size_bytes": size_bytes,
        }
    return records


def build_review(repository_root: Path) -> dict[str, object]:
    """Build the non-executable prospective repair review."""
    terminal_path = repository_root / _TERMINAL
    for path, expected, label in (
        (terminal_path, _TERMINAL_SHA256, "terminal decision"),
        (repository_root / _IDENTITY, _IDENTITY_SHA256, "identity review"),
        (
            repository_root / _EXECUTION_DECISION,
            _EXECUTION_DECISION_SHA256,
            "execution decision",
        ),
    ):
        if file_sha256(path) != expected:
            raise ValueError(f"{label} identity changed")
    terminal = _json_object(terminal_path, label="terminal decision")
    if canonical_sha256(terminal) != _TERMINAL_CANONICAL_SHA256:
        raise ValueError("terminal canonical identity changed")
    failed = [
        item
        for item in cast(list[dict[str, Any]], terminal["geometry_decisions"])
        if item["status"] == "fail"
    ]
    if (
        terminal["status"] != "fail"
        or terminal["failed_geometry_count"] != 1
        or len(failed) != 1
        or failed[0]["geometry_id"] != _FAILED_GEOMETRY
    ):
        raise ValueError("terminal scientific outcome changed")
    observations, attributions = _load_scratch()
    geometry = [
        item
        for item in observations
        if item["cell_id"].rsplit("--", maxsplit=1)[0] == _FAILED_GEOMETRY
    ]
    tail = next(item for item in geometry if item["input_id"] == _FAILED_INPUT)
    tail_paired = _paired(tail)
    attribution = attributions[_FAILED_INPUT]
    if (
        tail_paired["flux"] != _EXPECTED_TAIL_FLUX_MOVEMENT
        or tail_paired["split"] != 1.0
        or attribution["candidate_truth_linked_source_count"]
        != _EXPECTED_TAIL_LINKED_SOURCE_COUNT
        or attribution["hierarchy_catalogue_source_count"]
        != _EXPECTED_TAIL_CATALOGUE_SOURCE_COUNT
    ):
        raise ValueError("terminal tail evidence changed")
    return {
        "schema_version": 1,
        "review_id": (
            "phase-5-source-owned-source-support-linkage-terminal-"
            "root-cause-review"
        ),
        "reviewed_on": "2026-09-05",
        "status": "root-cause-complete-ready-for-prospective-replication",
        "authorization": {
            "candidate_execution_authorized": False,
            "cumulative_replay_authorized": False,
            "cutover_authorized": False,
            "development_lane_execution_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
            "rescoring_authorized": False,
            "source_finding_change_authorized": False,
            "viewed_data_execution_authorized": False,
        },
        "binding_context": {
            "candidate": {
                "configuration_sha256": (
                    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
                ),
                "revision": "2e25cdf8bb0fbd739bba330ff20d9f798f95bf44",
                "source_tree_sha256": (
                    "3da083b0a720fe0104fa51e135f224a2456b49bd49d85cd6a449fccb93805e8a"
                ),
            },
            "execution": {
                "immutable_checkout": (
                    "/private/tmp/hebog-phase5-source-support-linkage-"
                    "process-repair-lane-7d4a991"
                ),
                "execution_commit": (
                    "7d4a9918d1a69a071c51d54d4ca23ee0afca7f15"
                ),
                "identity_review_sha256": _IDENTITY_SHA256,
                "execution_decision_sha256": _EXECUTION_DECISION_SHA256,
                "scratch": str(_SCRATCH),
            },
            "terminal_decision": {
                "path": str(_TERMINAL),
                "sha256": _TERMINAL_SHA256,
                "canonical_sha256": _TERMINAL_CANONICAL_SHA256,
                "status": "fail",
                "input_count": 144,
                "failed_geometry_count": 1,
                "trigger_seam_passed": True,
                "executor_invariance_passed": True,
            },
        },
        "terminal_failure": {
            "geometry_id": _FAILED_GEOMETRY,
            "binding_failures": [
                "integrated-flux-paired-margin",
                "split-fraction-paired-margin",
            ],
            "only_adverse_input": _FAILED_INPUT,
            "tail_adverse_movements": tail_paired,
            "tail_support_gain": -tail_paired["support"],
            "paired_cell_medians": _cell_medians(geometry),
            "candidate_linkage": {
                "catalogue_source_count": attribution[
                    "candidate_catalogue_source_count"
                ],
                "truth_linked_source_count": attribution[
                    "candidate_truth_linked_source_count"
                ],
                "unmatched_source_count": attribution[
                    "candidate_unmatched_source_count"
                ],
            },
        },
        "causal_findings": {
            "truth_linkage_boundary_graze": {
                "classification": (
                    "confirmed-validation-only-fragmentation-false-positive"
                ),
                "evidence": (
                    "A bounded deterministic reproduction found that the "
                    "second linked row owns 49 direct pixels but only two "
                    "inside governed three-sigma truth support; the dominant "
                    "row owns 441 truth pixels. Any-intersection linkage made "
                    "that two-pixel boundary graze a split."
                ),
                "forensic_products": _forensic_products(),
                "process_contract": (
                    "Use the existing seven-pixel public minimum-island "
                    "support as the minimum truth overlap for a row to count "
                    "as a resolved fragment; keep every other row and its "
                    "flux as unmatched reliability evidence."
                ),
            },
            "single_realization_flux_tail": {
                "classification": (
                    "stochastic-boundary-tail-not-systematic-cell-regression"
                ),
                "evidence": (
                    "The same boundary realization worsened absolute flux "
                    "error by 0.053766 while improving support recall by "
                    "0.116412. The four-seed boundary-cell paired median "
                    "improves flux by 0.005116 and support by 0.051527; the "
                    "complete 12-image geometry paired median also improves "
                    "flux."
                ),
                "root_cause": (
                    "The historical fast gate bound to the maximum of every "
                    "individual noise realization, although its independent "
                    "development comparison unit is the four-seed trigger "
                    "cell. One near-threshold stochastic tail could therefore "
                    "override a safe paired cell distribution."
                ),
            },
            "source_photometry": {
                "classification": (
                    "known-broad-subthreshold-halo-limitation-not-actionable-"
                    "from-viewed-development-data"
                ),
                "evidence": (
                    "Nearby independently published rows collectively recover "
                    "more of the broad halo, but the conservative hierarchy "
                    "has no scale-aware parent evidence that would safely "
                    "distinguish them from unrelated close sources."
                ),
                "policy": (
                    "Do not add proximity-only merging, enlarge apertures, "
                    "add "
                    "scales, or tune thresholds from this viewed seed. Judge "
                    "adequacy prospectively against both PyBDSF references "
                    "and the selected Hebog incumbent."
                ),
            },
            "excluded_causes": (
                "Trigger activation, product validity, Serial/existing-Dask "
                "invariance, completeness, source-support ownership, and "
                "terminal-cycle logic all passed or were inactive."
            ),
        },
        "prospective_repair": {
            "source_finding_science_changed": False,
            "truth_linkage": {
                "minimum_truth_overlap_pixels": _MINIMUM_ISLAND_PIXELS,
                "basis": "existing-public-minimum-island-pixels",
            },
            "retention_statistic": (
                "maximum adverse paired median across the three separately "
                "reported four-seed trigger cells within each geometry"
            ),
            "tail_sentinel": (
                "retain maximum adverse single-realization movement for every "
                "metric as non-binding diagnostic evidence"
            ),
            "unchanged_numeric_margins": {
                "completeness": 0.02,
                "flux": 0.05,
                "mask": 0.05,
                "split": 0.02,
                "support": 0.05,
            },
            "systematic_regression_rule": (
                "A cell-median movement outside its unchanged margin remains "
                "binding; geometries and trigger cohorts are never pooled."
            ),
            "final_gate_unchanged": (
                "Every predeclared cumulative and held-out geometry must pass "
                "released PyBDSF, pinned-master PyBDSF, selected-Hebog "
                "retention, and hard safety checks."
            ),
        },
        "replication_population": {
            "role": "development",
            "input_count": 144,
            "cell_count": 36,
            "geometry_count": 12,
            "seeds_per_cell": 4,
            "first_seed": _REPLICATION_FIRST_SEED,
            "last_seed": _REPLICATION_LAST_SEED,
            "disjoint_from_viewed_development": True,
            "disjoint_from_frozen_qualification": True,
        },
        "required_sequence": [
            "preserve-terminal-failure-and-original-scratch-unchanged",
            "implement-seven-pixel-truth-linkage-and-cell-median-retention-test-first",
            "run-one-case-complete-process-smoke",
            "freeze-seed-disjoint-replication-manifest-program-and-one-use-authority",
            "run-144-image-replication-lane",
            "open-cumulative-dual-pybdsf-replay-only-if-replication-passes",
            "open-fresh-held-out-qualification-only-if-cumulative-parity-passes",
            "close-phase-5-only-after-public-engineering-and-independent-readiness-gates-pass",
        ],
        "no_retrospective_rescore": True,
        "required_next_decision": (
            "use-standing-user-authority-only-after-exact-replication-"
            "identities-and-complete-no-write-preflight-are-frozen"
        ),
    }


def write_review(path: Path, review: object) -> None:
    """Write one finite root-cause review without overwriting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_document_bytes(review))


def main() -> None:
    """Build and write the exact root-cause review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    review = build_review(arguments.repository_root.resolve())
    write_review(arguments.output, review)
    print(document_sha256(review))


if __name__ == "__main__":
    main()
