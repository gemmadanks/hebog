#!/usr/bin/env python3
"""Build the non-executable compact held-out sentinel root-cause review."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from math import isfinite
from pathlib import Path
from statistics import median
from typing import Any, cast

import numpy as np

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).resolve().parents[2]
_TERMINAL = _ROOT / (
    "benchmark-results/phase-5/"
    "compact-held-out-sentinel-pybdsf-empty-repair.json"
)
_TERMINAL_FILE_SHA256 = (
    "f542c7dbdc98bb3023efda4604d453b654c6da7bf61e5892fe528c5e601820aa"
)
_TERMINAL_CANONICAL_SHA256 = (
    "00e292ef79504d54e63c464e9a7591902e113aad4aeb102c19fba3b374726602"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-compact-held-out-sentinel-pybdsf-empty-repair"
)
_SUMMARY_SET_CANONICAL_SHA256 = (
    "4965e408701b15badf3025614b8f071f124947ff5146533e201b63834ae1db1f"
)
_OUTPUT = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-sentinel-root-cause-pre-review.json"
)
_CANDIDATE = {
    "configuration_sha256": (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    ),
    "revision": "95cfc76ded56556dc3ad6894410962d34f0d5604",
    "source_tree_sha256": (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    ),
}
_PYBDSF_DIGEST = (
    "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198"
)
_EXPECTED_INPUTS = 168
_EXPECTED_CELLS = 42
_EXPECTED_FINDER_ROWS = 2
_BINDINGS = {
    "identity_review": (
        _ROOT / "config/contracts/"
        "phase-5-compact-held-out-sentinel-pybdsf-empty-repair-review.json",
        "b67d877624bc87b2b8b3d09ad6c5f2e42fe573fac1bcdb7aa9c79810c6a5a329",
    ),
    "execution_decision": (
        _ROOT / "config/contracts/"
        "phase-5-compact-held-out-sentinel-pybdsf-empty-repair-"
        "execution-decision.json",
        "6516d6ef373f91a1969d9c456392ba70e2cca77cfa93a710a01872f920741cd9",
    ),
    "hebog_component_runner": (
        _ROOT / "scripts/benchmark/"
        "run_phase5_compact_held_out_sentinel_identity_repair.py",
        "37afb35dab47c4885df509fa57ac150733aa793d6afaf5fae2d0f4dc329847ec",
    ),
    "terminal_runner": (
        _ROOT / "scripts/benchmark/"
        "run_phase5_compact_held_out_sentinel_pybdsf_empty_repair.py",
        "1ec3181c969ad203826eddf8a3f0e21e7640cb37eb56a9a1edac85080ffa02da",
    ),
    "summary_compiler": (
        _ROOT / "scripts/validation/"
        "compile_phase5_compact_held_out_sentinel.py",
        "7286fbd4e7e5afbe86c87456e52cf490ae7150e41ccf1dfd57b9e9d69ab47aa2",
    ),
    "cell_evaluator": (
        _ROOT / "scripts/validation/"
        "evaluate_phase5_compact_held_out_sentinel.py",
        "6f2a05fbc1fbe66781f72554b53b94e83d6754b0809043c214d36493f8e83bfd",
    ),
    "endpoint_compiler": (
        _ROOT / "src/hebog/validation/external_successor_compiler.py",
        "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55",
    ),
    "catalogue_loader": (
        _ROOT / "src/hebog/validation/products.py",
        "c5f64f35a6d7a72a3256d075e20b621081938ea7fa97525e1b887a74d4374fe7",
    ),
    "public_science": (
        _ROOT / "src/hebog/public_science.py",
        "42ab6f8d4512914c882d9a69f0bcbbe7b093c4720fd52686142306935fafc128",
    ),
}
_HIGHER_IS_BETTER = {
    "completeness",
    "mask-iou",
    "mask-precision",
    "mask-recall",
    "reliability",
}
_IMAGE_DIAGNOSTIC_METRICS = {
    "integrated-flux-median": ("median", 0.05),
    "position-median": ("median", 0.05),
    "reliability": ("scalar", 0.02),
    "split-fraction": ("scalar", 0.02),
}
_MASK_METRICS = {"mask-iou", "mask-precision", "mask-recall"}


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object with a clear failure."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _require_bindings() -> dict[str, dict[str, str]]:
    """Verify and describe every implementation input used by the review."""
    records: dict[str, dict[str, str]] = {}
    for label, (path, expected) in _BINDINGS.items():
        if file_sha256(path) != expected:
            raise ValueError(f"compact sentinel {label} identity changed")
        records[label] = {
            "path": str(path.relative_to(_ROOT)),
            "sha256": expected,
        }
    return records


def _load_terminal() -> dict[str, Any]:
    """Load and fail-closed bind the exact scientific terminal."""
    if file_sha256(_TERMINAL) != _TERMINAL_FILE_SHA256:
        raise ValueError("compact sentinel terminal identity changed")
    terminal = _json_object(_TERMINAL, label="compact sentinel terminal")
    if canonical_sha256(terminal) != _TERMINAL_CANONICAL_SHA256:
        raise ValueError("compact sentinel terminal content changed")
    if (
        terminal.get("status") != "fail"
        or terminal.get("passed") is not False
        or terminal.get("input_count") != _EXPECTED_INPUTS
        or terminal.get("candidate")
        != {"entrypoint": "hebog.find_sources", **_CANDIDATE}
        or terminal.get("pybdsf_container_digest") != _PYBDSF_DIGEST
        or terminal.get("pooling_used") is not False
    ):
        raise ValueError("compact sentinel terminal contract changed")
    decisions = terminal.get("cell_decisions")
    if not isinstance(decisions, list) or len(decisions) != _EXPECTED_CELLS:
        raise ValueError("compact sentinel cell population changed")
    return terminal


def _load_pairs() -> tuple[  # noqa: C901
    list[dict[str, dict[str, Any]]], str
]:
    """Load all exact array-free pairs and bind their preserved file set."""
    summary_root = _SCRATCH / "summaries"
    paths = tuple(sorted(summary_root.glob("*.json")))
    if len(paths) != _EXPECTED_INPUTS:
        raise ValueError(
            "compact root-cause review requires 168 pair summaries"
        )
    pairs: list[dict[str, dict[str, Any]]] = []
    records: list[dict[str, str]] = []
    input_ids: set[str] = set()
    for path in paths:
        value: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or len(value) != _EXPECTED_FINDER_ROWS:
            raise ValueError("compact pair summary must contain two finders")
        rows: dict[str, dict[str, Any]] = {}
        for untyped in value:
            if not isinstance(untyped, dict):
                raise ValueError("compact finder summary must be an object")
            row = cast(dict[str, Any], untyped)
            finder = row.get("finder_id")
            if finder not in {"current-hebog", "released-pybdsf"}:
                raise ValueError("compact pair finder identity changed")
            if (
                row.get("product_valid") is not True
                or row.get("ownership_valid") is not True
            ):
                raise ValueError("compact pair contains an invalid product")
            rows[cast(str, finder)] = row
        if set(rows) != {"current-hebog", "released-pybdsf"}:
            raise ValueError("compact pair finder population changed")
        if rows["current-hebog"].get("input_id") != rows[
            "released-pybdsf"
        ].get("input_id"):
            raise ValueError("compact pair input identities disagree")
        input_id = rows["current-hebog"].get("input_id")
        if not isinstance(input_id, str) or input_id in input_ids:
            raise ValueError("compact pair input identity is invalid")
        input_ids.add(input_id)
        pairs.append(rows)
        records.append(
            {
                "path": path.name,
                "sha256": file_sha256(path),
            }
        )
    digest = canonical_sha256(records)
    if digest != _SUMMARY_SET_CANONICAL_SHA256:
        raise ValueError("compact pair summary file set changed")
    return pairs, digest


def _count_relation(left: int, right: int) -> str:
    """Name one exact integer-count relation."""
    if left > right:
        return "greater"
    if left < right:
        return "less"
    return "equal"


def _representation_counts(
    pairs: list[dict[str, dict[str, Any]]],
) -> dict[str, object]:
    """Expose how catalogue rows relate to each native topology domain."""
    output: dict[str, object] = {}
    for finder in ("current-hebog", "released-pybdsf"):
        rows = [pair[finder] for pair in pairs]
        differences = [
            int(row["catalogue_count"]) - int(row["native_support_count"])
            for row in rows
        ]
        output[finder.replace("-", "_")] = {
            "catalogue_equals_native_support_images": sum(
                difference == 0 for difference in differences
            ),
            "catalogue_exceeds_native_support_images": sum(
                difference > 0 for difference in differences
            ),
            "maximum_catalogue_rows_per_native_support_excess": max(
                differences
            ),
        }
        relation = Counter(
            _count_relation(
                int(row["catalogue_count"]), int(row["truth_group_count"])
            )
            for row in rows
        )
        output[f"{finder.replace('-', '_')}_catalogue_vs_truth_groups"] = {
            "equal": relation["equal"],
            "greater": relation["greater"],
            "less": relation["less"],
        }
        catalogue_counts = sorted(int(row["catalogue_count"]) for row in rows)
        support_counts = sorted(
            int(row["native_support_count"]) for row in rows
        )
        output[f"{finder.replace('-', '_')}_count_distribution"] = {
            "catalogue_minimum_median_maximum": [
                catalogue_counts[0],
                median(catalogue_counts),
                catalogue_counts[-1],
            ],
            "native_support_minimum_median_maximum": [
                support_counts[0],
                median(support_counts),
                support_counts[-1],
            ],
        }
    return output


def _image_value(
    row: dict[str, Any], metric: str, statistic: str
) -> float | None:
    """Reduce one metric exactly as the frozen evaluator did."""
    metrics = row.get("metrics")
    if not isinstance(metrics, dict) or metric not in metrics:
        raise ValueError(f"compact pair metric is absent: {metric}")
    value = metrics[metric]
    if statistic == "scalar":
        if not isinstance(value, (float, int)):
            raise ValueError("compact scalar metric is malformed")
        result = float(value)
    else:
        if not isinstance(value, list):
            raise ValueError("compact conditional metric is malformed")
        if not value:
            return None
        result = float(np.median(np.asarray(value, dtype=np.float64)))
    if not isfinite(result):
        raise ValueError("compact pair metric is not finite")
    return result


def _adverse_movements(
    pairs: list[dict[str, dict[str, Any]]],
) -> dict[str, object]:
    """Retain descriptive image evidence without changing a frozen decision."""
    output: dict[str, object] = {}
    for metric, (statistic, margin) in _IMAGE_DIAGNOSTIC_METRICS.items():
        adverse: list[dict[str, dict[str, Any]]] = []
        measurable = 0
        for pair in pairs:
            candidate = _image_value(pair["current-hebog"], metric, statistic)
            reference = _image_value(
                pair["released-pybdsf"], metric, statistic
            )
            if candidate is None or reference is None:
                continue
            measurable += 1
            regression = (
                reference - candidate
                if metric in _HIGHER_IS_BETTER
                else candidate - reference
            )
            if regression > margin:
                adverse.append(pair)
        row: dict[str, object] = {
            "adverse_images": len(adverse),
            "measurable_images": measurable,
        }
        if metric == "split-fraction":
            row = {
                "adverse_images": len(adverse),
                "current_hebog_has_more_native_supports": sum(
                    int(pair["current-hebog"]["native_support_count"])
                    > int(pair["released-pybdsf"]["native_support_count"])
                    for pair in adverse
                ),
                "pybdsf_gaussian_rows_share_native_support": sum(
                    int(pair["released-pybdsf"]["catalogue_count"])
                    > int(pair["released-pybdsf"]["native_support_count"])
                    for pair in adverse
                ),
            }
        else:
            row["hebog_catalogue_exceeds_truth_groups"] = sum(
                int(pair["current-hebog"]["catalogue_count"])
                > int(pair["current-hebog"]["truth_group_count"])
                for pair in adverse
            )
            row["pybdsf_gaussian_rows_share_native_support"] = sum(
                int(pair["released-pybdsf"]["catalogue_count"])
                > int(pair["released-pybdsf"]["native_support_count"])
                for pair in adverse
            )
        output[metric] = row
    return output


def _failure_evidence(  # noqa: C901, PLR0912
    terminal: dict[str, Any],
) -> dict[str, object]:
    """Account for every frozen cell and endpoint failure."""
    decisions = cast(list[dict[str, Any]], terminal["cell_decisions"])
    metric_failures: Counter[str] = Counter()
    family_cells: Counter[str] = Counter()
    family_failures: Counter[str] = Counter()
    trigger_evidence: dict[str, dict[str, int]] = {
        trigger: {"cells": 0, "failed_cells": 0, "failed_endpoints": 0}
        for trigger in ("above", "below", "boundary")
    }
    for decision in decisions:
        cell_id = cast(str, decision["cell_id"])
        if cell_id.startswith("compact-"):
            family = "compact"
        elif cell_id.startswith("curved-filament-"):
            family = "curved_filament"
        elif cell_id.startswith("mixed-compact-extended-"):
            family = "mixed_compact_extended"
        elif cell_id.startswith("shell-"):
            family = "shell"
        else:
            raise ValueError("compact sentinel family is unknown")
        family_cells[family] += 1
        if decision.get("passed") is not True:
            family_failures[family] += 1
        metrics = decision.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("compact sentinel cell metrics are absent")
        failed_in_cell = 0
        for metric, untyped in metrics.items():
            if not isinstance(untyped, dict):
                raise ValueError("compact sentinel metric decision is invalid")
            if untyped.get("passed") is not True:
                metric_failures[metric] += 1
                failed_in_cell += 1
        if family != "compact":
            trigger = cell_id.rsplit("-", maxsplit=1)[-1]
            if trigger not in trigger_evidence:
                raise ValueError("compact sentinel trigger stratum is unknown")
            trigger_evidence[trigger]["cells"] += 1
            trigger_evidence[trigger]["failed_cells"] += int(
                decision.get("passed") is not True
            )
            trigger_evidence[trigger]["failed_endpoints"] += failed_in_cell
    return {
        "endpoint_failures": dict(sorted(metric_failures.items())),
        "family_cells": {
            family: {
                "cells": family_cells[family],
                "failed_cells": family_failures[family],
            }
            for family in sorted(family_cells)
        },
        "trigger_strata": trigger_evidence,
    }


def build_review() -> dict[str, object]:
    """Construct the exact prospective, non-executable root-cause review."""
    terminal = _load_terminal()
    pairs, summary_digest = _load_pairs()
    bindings = _require_bindings()
    failure_evidence = _failure_evidence(terminal)
    endpoint_failures = cast(
        dict[str, int], failure_evidence["endpoint_failures"]
    )
    failed_endpoints = sum(endpoint_failures.values())
    mask_failures = sum(
        endpoint_failures.get(metric, 0) for metric in _MASK_METRICS
    )
    adverse = _adverse_movements(pairs)
    flux = cast(dict[str, int], adverse["integrated-flux-median"])
    position = cast(dict[str, int], adverse["position-median"])
    return {
        "authorization": {
            "candidate_execution_authorized": False,
            "cumulative_replay_authorized": False,
            "cutover_authorized": False,
            "evaluator_alignment_implementation_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "pybdsf_execution_authorized": False,
            "release_authorized": False,
            "rescoring_authorized": False,
            "source_finding_change_authorized": False,
            "tuning_authorized": False,
            "viewed_data_execution_authorized": False,
        },
        "binding_context": {
            "array_free_pair_summaries": {
                "file_count": len(pairs),
                "file_set_canonical_sha256": summary_digest,
                "input_count": len(pairs),
                "scratch": str(_SCRATCH),
            },
            "candidate": _CANDIDATE,
            "comparator": {
                "container_digest": _PYBDSF_DIGEST,
                "finder_id": "released-pybdsf",
                "version": "1.14.1",
            },
            "program_and_governance_bindings": bindings,
            "terminal_decision": {
                "canonical_sha256": _TERMINAL_CANONICAL_SHA256,
                "file_sha256": _TERMINAL_FILE_SHA256,
                "path": str(_TERMINAL.relative_to(_ROOT)),
                "status": "fail",
            },
        },
        "causal_findings": {
            "adaptive_background_trigger": {
                "classification": "excluded-as-primary-cause",
                "evidence": failure_evidence["trigger_strata"],
                "root_cause": (
                    "Below-trigger controls fail 11 of 12 extended cells with "
                    "58 failed endpoints, essentially the same burden as "
                    "boundary (10/12, 58) and above (9/12, 55). The dominant "
                    "failure therefore predates adaptive activation."
                ),
            },
            "binary_support": {
                "classification": "independent-like-semantics-candidate-risk",
                "evidence": {
                    "failed_mask_iou_cells": endpoint_failures["mask-iou"],
                    "failed_mask_precision_cells": endpoint_failures[
                        "mask-precision"
                    ],
                    "failed_mask_recall_cells": endpoint_failures[
                        "mask-recall"
                    ],
                },
                "root_cause": (
                    "Binary truth-versus-positive-support metrics do not "
                    "depend on catalogue or native label values. Their six "
                    "failures remain scientifically interpretable and cannot "
                    "be waived by the evaluator defect."
                ),
            },
            "catalogue_and_topology_level": {
                "classification": "confirmed-like-semantics-evaluator-defect",
                "evidence": {
                    "implementation": (
                        "The frozen Hebog wrapper compiles "
                        "component_catalogue against "
                        "measurement_component_labels. The frozen PyBDSF "
                        "wrapper compiles Gaussian rows against native island "
                        "labels."
                    ),
                    "representation_counts": _representation_counts(pairs),
                    "split_image_diagnostic": adverse["split-fraction"],
                },
                "root_cause": (
                    "The evaluator treated component labels, island labels, "
                    "Gaussian rows, and source truth groups as one topology "
                    "domain. Hebog exposes one native owner per component, "
                    "whereas multiple PyBDSF Gaussian rows share one island. "
                    "Split, merge, and duplicate outcomes are therefore not "
                    "like-semantics comparisons."
                ),
            },
            "integrated_flux": {
                "classification": (
                    "confirmed-source-versus-component-flux-aggregation-defect-"
                    "with-residual-science-risk"
                ),
                "evidence": {
                    "adverse_images": flux["adverse_images"],
                    "adverse_images_without_hebog_component_excess": (
                        flux["adverse_images"]
                        - flux["hebog_catalogue_exceeds_truth_groups"]
                    ),
                    "implementation": (
                        "The endpoint compiler prefers "
                        "association_integrated_flux_jy. PyBDSF Gaussian rows "
                        "carry flux summed over (Isl_id, Source_id), while "
                        "the Hebog component rows used by the sentinel retain "
                        "individual component measurements."
                    ),
                },
                "root_cause": (
                    "Whole truth-source flux was compared to grouped source "
                    "flux for PyBDSF but to one component flux for Hebog. "
                    "Fourteen adverse images have no Hebog component-count "
                    "excess, so source-level alignment must precede a "
                    "separate fixture diagnosis of any remaining photometry "
                    "defect."
                ),
            },
            "position_and_reliability": {
                "classification": (
                    "confirmed-source-versus-component-observable-defect-with-"
                    "residual-science-risk"
                ),
                "evidence": {
                    "position_adverse_images": position["adverse_images"],
                    "position_adverse_images_without_hebog_component_excess": (
                        position["adverse_images"]
                        - position["hebog_catalogue_exceeds_truth_groups"]
                    ),
                    "reliability_image_diagnostic": adverse["reliability"],
                },
                "root_cause": (
                    "One component centre and one component row were scored "
                    "against an associated truth source. Legitimate component "
                    "multiplicity can look like position error or "
                    "false-source unreliability. Ten position-adverse images "
                    "lack a Hebog component excess, so a residual astrometry "
                    "risk remains."
                ),
            },
        },
        "failure_accounting": {
            "failed_cell_count": sum(
                item["failed_cells"]
                for item in cast(
                    dict[str, dict[str, int]], failure_evidence["family_cells"]
                ).values()
            ),
            "failed_endpoint_count": failed_endpoints,
            "label_invariant_mask_endpoint_failures": mask_failures,
            "retrospective_rescore_permitted": False,
            "source_representation_sensitive_endpoint_failures": (
                failed_endpoints - mask_failures
            ),
            "terminal_result_remains_fail": True,
        },
        "governance": {
            "historical_result": (
                "The exact 168-image terminal remains immutable fail "
                "evidence; the viewed summaries may support diagnosis only."
            ),
            "interpretation_limit": (
                "The 180 representation-sensitive endpoint failures cannot "
                "support a scientific parity or inferiority conclusion until "
                "source-level semantics are aligned. This does not imply that "
                "they would pass after alignment."
            ),
            "phase_5_status": (
                "open and blocked from readiness closeout until a new "
                "seed-disjoint like-semantics sentinel passes"
            ),
        },
        "paired_evidence": {
            "endpoint_failures": endpoint_failures,
            "family_outcomes": failure_evidence["family_cells"],
            "image_level_adverse_movements": adverse,
            "input_count": len(pairs),
            "representation_counts": _representation_counts(pairs),
            "trigger_outcomes": failure_evidence["trigger_strata"],
        },
        "recommended_correction": {
            "array_free_retention": (
                "Retain separate source and component counts, owner IDs, "
                "source-union memberships, per-source flux/centre, "
                "per-component flux/centre, and an explicit topology-domain "
                "name."
            ),
            "binary_support_lane": (
                "retain direct truth-versus-positive-support mask metrics as "
                "binding"
            ),
            "binding_source_lane": {
                "hebog_catalogue": "terminal associated-source catalogue",
                "pybdsf_catalogue": (
                    "rows grouped by native PyBDSF source identity"
                ),
                "topology": "source-union ownership for both finders",
                "metrics": [
                    "completeness",
                    "reliability",
                    "source integrated flux",
                    "source position",
                    "split",
                    "merge",
                    "duplicate",
                ],
            },
            "component_diagnostic_lane": {
                "binding": False,
                "catalogues": (
                    "Hebog components versus PyBDSF Gaussian components"
                ),
                "flux": (
                    "individual integrated_flux_jy only; never grouped "
                    "association flux"
                ),
                "topology": (
                    "report no split/merge parity unless both finders expose "
                    "like component-owner planes"
                ),
            },
            "science_change_policy": (
                "Do not change source finding from this viewed result. Align "
                "and validate the evaluator on fixtures first; propose a "
                "separate scientific repair only for a reproduced residual."
            ),
        },
        "required_next_decision": (
            "named-approval-of-this-exact-review-for-test-first-fixture-only-"
            "sentinel-evaluator-alignment"
        ),
        "required_sequence": [
            "preserve-the-failed-terminal-and-168-viewed-pairs-unchanged",
            "implement-source-and-component-semantic-separation-test-first",
            "reproduce-mask-and-residual-flux-position-risks-on-fixtures-only",
            "validate-array-free-retention-and-serial-dask-invariance",
            "freeze-new-seed-disjoint-sentinel-identities-only-after-all-fixtures-pass",
            "obtain-separate-exact-approval-before-any-new-execution",
            "keep-phase-5-open-until-a-new-like-semantics-sentinel-passes",
        ],
        "review_id": (
            "phase-5-compact-held-out-sentinel-root-cause-pre-review"
        ),
        "reviewed_on": "2026-09-07",
        "schema_version": 1,
        "status": "ready-for-named-sentinel-evaluator-alignment-review",
        "test_first_matrix": [
            "one-extended-truth-multiple-components",
            "pybdsf-multiple-gaussians-one-source",
            "hebog-multi-component-source-union",
            "three-peak-connected-compact-source",
            "grouped-source-versus-individual-component-flux",
            "source-centroid-versus-component-centroid",
            "source-reliability-with-legitimate-component-multiplicity",
            "like-domain-topology-labels",
            "mask-metrics-invariant-to-positive-relabeling",
            "single-component-flux-and-position-residual",
            "below-trigger-extended-control",
            "serial-existing-dask-invariance",
        ],
    }


def write_review(path: Path, review: dict[str, object]) -> None:
    """Write one finite canonical review without overwriting evidence."""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite review: {path}")
    document = json.dumps(
        review,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document + "\n", encoding="utf-8")


def _parse_arguments() -> argparse.Namespace:
    """Parse the bounded root-cause review command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Build, verify, or write the exact non-executable review."""
    arguments = _parse_arguments()
    review = build_review()
    if arguments.verify_only:
        existing = _json_object(arguments.output, label="checked-in review")
        if existing != review:
            raise ValueError("checked-in compact root-cause review changed")
        print(canonical_sha256(review))
        return
    write_review(arguments.output, review)
    print(canonical_sha256(review))


if __name__ == "__main__":
    main()
