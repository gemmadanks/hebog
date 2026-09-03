#!/usr/bin/env python3
"""Evaluate sealed paired products with source-union tail dispatch."""

from __future__ import annotations

import argparse
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_tail_repair.py"
)
_PARENT_PREPARER = (
    _ROOT / "scripts/validation/prepare_phase5_prospective_paired_evidence.py"
)
_PREPARER = (
    _ROOT / "scripts/validation/"
    "prepare_phase5_prospective_paired_source_union_evidence.py"
)
_SOURCE_UNION_TAIL = (
    _ROOT / "scripts/validation/"
    "repair_phase5_prospective_paired_source_union_tail.py"
)
_PARENT_EVALUATOR_SHA256 = (
    "1974101dd6d4c577ec402191093f3af65f4a67ef7adb6dfb2f2a85e13e2fa8a0"
)
_PREPARER_SHA256 = (
    "b4c8f8eafb3c961f7696cd49c90e72aa52a81df13eb58980522b562212f0ce79"
)
_SOURCE_UNION_TAIL_SHA256 = (
    "18c8d43b32e28b22e64b9a9baa69e35ab32dd9582735da30a6791578eea27237"
)


def _verify_programs() -> None:
    """Fail closed unless the parent and repaired preparer are exact."""
    evidence = (
        (_PARENT_EVALUATOR, _PARENT_EVALUATOR_SHA256, "parent evaluator"),
        (_PREPARER, _PREPARER_SHA256, "source-union preparer"),
        (
            _SOURCE_UNION_TAIL,
            _SOURCE_UNION_TAIL_SHA256,
            "source-union tail",
        ),
    )
    for path, expected, label in evidence:
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"prospective paired {label} changed")


def load_topology_repaired_evaluator() -> dict[str, Any]:
    """Load the tail-repaired evaluator and bind its repaired preparer."""
    _verify_programs()
    parent_overlay = runpy.run_path(str(_PARENT_EVALUATOR))
    parent = cast(dict[str, Any], parent_overlay["load_repaired_evaluator"]())
    if Path(parent["_PREPARER"]).resolve() != _PARENT_PREPARER.resolve():
        raise ValueError("prospective paired preparer seam changed")
    repair = runpy.run_path(str(_SOURCE_UNION_TAIL))
    parent_tail = parent["_truth_linked_tail_record"]

    def source_union_truth_linked_tail_record(**arguments: Any) -> object:
        return repair["truth_linked_tail_record"](
            parent_tail=parent_tail, **arguments
        )

    parent["_PREPARER"] = _PREPARER
    parent["_PREVIOUS_TRUTH_LINKED_TAIL_RECORD"] = parent_tail
    parent["_truth_linked_tail_record"] = source_union_truth_linked_tail_record
    parent["__file__"] = str(Path(__file__).resolve())
    return parent


def verify_truth_linked_tail(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Exercise the exact real-product tail without publishing a decision."""
    evaluator = load_topology_repaired_evaluator()
    root = arguments.repository_root.resolve()
    materializer = evaluator["_load_materializer"]()
    smoke = runpy.run_path(str(evaluator["_SMOKE_EVALUATOR"]))
    preparer = runpy.run_path(str(_PREPARER))
    identifiers = materializer["_selected_inputs"](
        arguments.source_request, arguments.population
    )
    verified, _ = materializer["_verified_reference"](
        root, arguments.reference_reconstruction
    )
    verified = smoke["_subset_verified"](verified, identifiers)
    current_revision = evaluator["_CURRENT_REVISION"]
    current_configuration = materializer["_current_configuration"](root)
    current_source_tree = materializer["source_tree_sha256"](root)
    if (
        current_configuration != evaluator["_CURRENT_CONFIGURATION_SHA256"]
        or current_source_tree != evaluator["_CURRENT_SOURCE_TREE_SHA256"]
    ):
        raise ValueError("prospective current scientific identity changed")
    frozen = materializer["_current_composition"](
        root,
        revision=current_revision,
        configuration=current_configuration,
    )
    compiler_globals, historical_registry = smoke["_compiler"](frozen)
    current = smoke["_candidate_view"](
        frozen,
        verified,
        arguments.current_scratch,
        configuration=current_configuration,
        revision=current_revision,
        compiler_globals=compiler_globals,
    )
    terminal_parent = runpy.run_path(
        str(root / materializer["_TERMINAL_PARENT_WRAPPER"])
    )
    previous_identity = frozen["_candidate_runtime_identity"]
    frozen["_candidate_runtime_identity"] = terminal_parent[
        "_candidate_runtime_identity"
    ]
    try:
        incumbent = smoke["_candidate_view"](
            frozen,
            verified,
            arguments.incumbent_scratch,
            configuration=terminal_parent["_CANDIDATE_CONFIGURATION_SHA256"],
            revision=terminal_parent["_CANDIDATE_REVISION"],
            compiler_globals=compiler_globals,
        )
    finally:
        frozen["_candidate_runtime_identity"] = previous_identity
    with smoke["_mask_measurement_separation_evaluation"]():
        frozen["_install_prospective_compiler"](
            compiler_globals, current, current_configuration
        )
        smoke["_install_mask_separated_compiler"](
            compiler_globals,
            measurement_configuration=current_configuration,
        )
        tail = cast(
            Mapping[str, object],
            evaluator["_truth_linked_tail_record"](
                current=current,
                incumbent=incumbent,
                compiler_globals=compiler_globals,
                historical_registry=historical_registry,
                repository_root=root,
                source_request=arguments.source_request,
                smoke=smoke,
                preparer=preparer,
            ),
        )
    if (
        tail.get("array_planes_retained") is not False
        or tail.get("promotion_effect") != "none-diagnostic-only"
        or not isinstance(tail.get("summaries_sha256"), str)
    ):
        raise ValueError("truth-linked tail verification is malformed")
    return {
        "array_planes_retained": False,
        "finder_counts": tail.get("finder_counts"),
        "promotion_effect": "none-diagnostic-only",
        "status": "pass",
        "summaries_sha256": tail["summaries_sha256"],
        "summary_count": tail.get("summary_count"),
        "unique_input_count": tail.get("unique_input_count"),
    }


def main() -> None:
    """Run the topology-repaired evaluator with the unchanged CLI."""
    load_topology_repaired_evaluator()["main"]()


if __name__ == "__main__":
    main()
