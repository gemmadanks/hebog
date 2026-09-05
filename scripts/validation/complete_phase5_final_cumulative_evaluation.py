#!/usr/bin/env python3
"""Verify sealed products and complete the final cumulative evaluation."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_science_contract import (
    load_prospective_endpoint_registry,
)

_ROOT = Path(__file__).parents[2]
_PARENT_COMPLETION = (
    _ROOT
    / "scripts/validation/complete_phase5_prospective_paired_evaluation.py"
)
_PARENT_COMPLETION_SHA256 = (
    "76ecc0ee13e2fa05d3da07cb3be77a808e306771c6ca445357eafef97edb0391"
)
_PARENT_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
)
_PARENT_EVALUATOR_SHA256 = (
    "39a568bada625b751931aff649e4e815c5ed70f68809d902a52ce93cfeaec62a"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_final_cumulative_current.py"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_SOURCE_REQUEST = Path(
    "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_POPULATION = Path(
    "config/contracts/phase-5-prospective-paired-population.json"
)
_CURRENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-final-cumulative-current-0b9e132"
)
_INCUMBENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-prospective-paired-incumbent-authentic-85d5807"
)
_RECONSTRUCTION_RECORD = Path(
    "benchmark-results/phase-5/"
    "prospective-paired-incumbent-reconstruction.json"
)
_PRODUCT_SEAL = Path(
    "benchmark-results/phase-5/final-cumulative-current-product-set.json"
)
_HISTORICAL_TERMINAL = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-"
    "public-finder-publication-scale-persistence.json"
)
_PRE_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-pre-review.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-final-cumulative-evaluation-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-final-cumulative-evaluation-implementation-"
    "decision.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-final-cumulative-evaluation-execution-"
    "decision.json"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/final-cumulative-current-decision.json"
)
_CURRENT_REVISION = "0b9e13299f3fbbd42af0dea4f70155a802a8441d"
_CURRENT_SOURCE_TREE_SHA256 = (
    "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_CURRENT_PRODUCT_SET_SHA256 = (
    "195a5a36be790ba3c9a2e5753eddb38c04c19c545a9875ba2c8acf9b7fce9ea1"
)
_CURRENT_PRODUCT_SEAL_SHA256 = (
    "2ece0d4632a4a353db8df70274679ce4d0ca6e3501d7799aaf6afac99813a194"
)
_CURRENT_PRODUCT_SEAL_CANONICAL_SHA256 = (
    "98d00be4b8b098e248392c92f69e2ca48fec1dafac0e2d2bdbbd90b47d71b00c"
)
_CURRENT_REPLAY_IDENTITY_SHA256 = (
    "c713cc6d21395bdad493113aa1dcf0e43c5de653f55b862cb964335abb98cab1"
)
_CURRENT_REPLAY_DECISION_SHA256 = (
    "2a0d45ec551955a39762e44303b2f0685265f440f98fb35d25d64115f788a0aa"
)
_INCUMBENT_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_INCUMBENT_SOURCE_TREE_SHA256 = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_INCUMBENT_CONFIGURATION_SHA256 = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
)
_INCUMBENT_RECONSTRUCTION_PRODUCT_SET_SHA256 = (
    "ea12ce032d06c37cfeb70dcfd16d288bd68bc1ef19c010b8491b9ff66ae406e8"
)
_INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256 = (
    "8dbc9dff20c861b1f93f11781d079226a7ef68475838909496086229ddc9fe5d"
)
_RECONSTRUCTION_RECORD_SHA256 = (
    "b302967f26ac5947e3c942598a428527cce1d4fa3373ed6eaeb6d204eb8dc040"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_SOURCE_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_POPULATION_SHA256 = (
    "0bd3e6a6e505f8fb307a108d90e932f6b3f16ae5fc6c654ab4c82de14f483687"
)
_HISTORICAL_TERMINAL_SHA256 = (
    "a9c6ed280308f863b149ad4d8dd7db59b8581cfa51cd585c004d4b69844881c8"
)
_PRE_REVIEW_SHA256 = (
    "57365335a4b7b119bb4dec8f0ea857481bf2d8d80f1162e60f555a258276b815"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_REFERENCE_RUN_COUNT = 9600
_EXPECTED_SMOKE_SUMMARY_COUNT = 4
_AUTHORIZATION = {
    "candidate_execution_authorized": False,
    "cutover_authorized": False,
    "evaluation_authorized": True,
    "fresh_qualification_authorized": False,
    "optimization_authorized": False,
    "pybdsf_execution_authorized": False,
    "release_authorized": False,
    "rescoring_authorized": False,
    "scientific_change_authorized": False,
    "threshold_or_margin_tuning_authorized": False,
    "viewed_data_execution_authorized": False,
}


def _object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, Any], value)


def _resolved(root: Path, path: Path) -> Path:
    """Resolve a repository-relative evidence path."""
    return path if path.is_absolute() else root / path


def _require_invocation(arguments: argparse.Namespace) -> None:
    """Require the exact evaluation-only paths and absent output."""
    expected = {
        "repository_root": _ROOT,
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "source_request": _SOURCE_REQUEST,
        "population": _POPULATION,
        "current_scratch": _CURRENT_SCRATCH,
        "incumbent_scratch": _INCUMBENT_SCRATCH,
        "reconstruction_record": _RECONSTRUCTION_RECORD,
        "product_seal": _PRODUCT_SEAL,
        "output": _OUTPUT,
    }
    for name, value in expected.items():
        if getattr(arguments, name, None) != value:
            raise ValueError(f"final cumulative evaluation {name} changed")
    if _resolved(arguments.repository_root, arguments.output).exists():
        raise FileExistsError("final cumulative evaluation output exists")


def _verify_product_seal(arguments: argparse.Namespace) -> dict[str, Any]:
    """Verify the atomic current-product handoff before any compilation."""
    path = _resolved(arguments.repository_root, arguments.product_seal)
    if file_sha256(path) != _CURRENT_PRODUCT_SEAL_SHA256:
        raise ValueError("final cumulative product seal changed")
    record = _object(path, label="final cumulative product seal")
    canonical = record.pop("record_canonical_sha256", None)
    required = {
        "status": "complete",
        "candidate_execution_count": _EXPECTED_INPUT_COUNT,
        "candidate_revision": _CURRENT_REVISION,
        "candidate_source_tree_sha256": _CURRENT_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _CURRENT_CONFIGURATION_SHA256,
        "candidate_product_set_sha256": _CURRENT_PRODUCT_SET_SHA256,
        "identity_review_sha256": _CURRENT_REPLAY_IDENTITY_SHA256,
        "execution_decision_sha256": _CURRENT_REPLAY_DECISION_SHA256,
        "pybdsf_execution_count": 0,
        "reference_run_count": _EXPECTED_REFERENCE_RUN_COUNT,
    }
    if (
        canonical != _CURRENT_PRODUCT_SEAL_CANONICAL_SHA256
        or canonical != canonical_sha256(record)
        or any(record.get(key) != value for key, value in required.items())
    ):
        raise ValueError("final cumulative product seal is malformed")
    return record


def _load_parent_completion() -> dict[str, Any]:
    """Retarget the complete historical product verifier to this candidate."""
    if file_sha256(_PARENT_COMPLETION) != _PARENT_COMPLETION_SHA256:
        raise ValueError("final cumulative parent completion changed")
    parent = runpy.run_path(str(_PARENT_COMPLETION))
    verify = parent.get("verify_products")
    if not callable(verify):
        raise ValueError("final cumulative product verifier seam changed")
    globals_ = verify.__globals__
    globals_.update(
        {
            "_ROOT": _ROOT,
            "_EVALUATOR": _EVALUATOR,
            "_EVALUATOR_SHA256": file_sha256(_EVALUATOR),
            "_CURRENT_REVISION": _CURRENT_REVISION,
            "_CURRENT_SOURCE_TREE_SHA256": _CURRENT_SOURCE_TREE_SHA256,
            "_CURRENT_CONFIGURATION_SHA256": (_CURRENT_CONFIGURATION_SHA256),
            "_CURRENT_PRODUCT_SET_SHA256": _CURRENT_PRODUCT_SET_SHA256,
            "_CURRENT_SCRATCH": _CURRENT_SCRATCH,
            "_OUTPUT": _OUTPUT,
        }
    )
    return globals_


def _expected_parent_products() -> dict[str, object]:
    """Return the complete product identities required from the verifier."""
    return {
        "candidate_execution_started": False,
        "current_configuration_sha256": _CURRENT_CONFIGURATION_SHA256,
        "current_product_set_sha256": _CURRENT_PRODUCT_SET_SHA256,
        "current_revision": _CURRENT_REVISION,
        "current_source_tree_sha256": _CURRENT_SOURCE_TREE_SHA256,
        "evaluator_sha256": file_sha256(_EVALUATOR),
        "incumbent_configuration_sha256": _INCUMBENT_CONFIGURATION_SHA256,
        "incumbent_product_set_sha256": (
            _INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256
        ),
        "incumbent_reconstruction_product_set_sha256": (
            _INCUMBENT_RECONSTRUCTION_PRODUCT_SET_SHA256
        ),
        "incumbent_revision": _INCUMBENT_REVISION,
        "incumbent_source_tree_sha256": _INCUMBENT_SOURCE_TREE_SHA256,
        "input_count_per_candidate": _EXPECTED_INPUT_COUNT,
        "reconstruction_record_sha256": _RECONSTRUCTION_RECORD_SHA256,
        "reference_run_count": _EXPECTED_REFERENCE_RUN_COUNT,
        "status": "pass",
    }


def expected_verified_products() -> dict[str, object]:
    """Return every static product and program identity for freezing."""
    return {
        **_expected_parent_products(),
        "candidate_product_seal_sha256": _CURRENT_PRODUCT_SEAL_SHA256,
        "candidate_product_seal_record_canonical_sha256": (
            _CURRENT_PRODUCT_SEAL_CANONICAL_SHA256
        ),
        "parent_completion_sha256": _PARENT_COMPLETION_SHA256,
        "parent_evaluator_sha256": _PARENT_EVALUATOR_SHA256,
    }


def verify_products(arguments: argparse.Namespace) -> dict[str, object]:
    """Verify both 2,400-product sets and all retained reference runs."""
    _require_invocation(arguments)
    _verify_product_seal(arguments)
    parent = _load_parent_completion()
    observed = cast(dict[str, object], parent["verify_products"](arguments))
    if observed != _expected_parent_products():
        raise ValueError("final cumulative verified product identity changed")
    return expected_verified_products()


def _namespace(value: object) -> object:
    """Convert retained JSON records to attribute-bearing smoke fixtures."""
    if isinstance(value, dict):
        return SimpleNamespace(
            **{key: _namespace(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_namespace(item) for item in value)
    return value


def run_bounded_terminal_smoke(directory: Path) -> dict[str, object]:
    """Exercise decision, retention, tail dispatch, and atomic publication."""
    if file_sha256(_HISTORICAL_TERMINAL) != _HISTORICAL_TERMINAL_SHA256:
        raise ValueError("final cumulative smoke fixture changed")
    evaluator = runpy.run_path(str(_EVALUATOR))["load_final_evaluator"]()
    terminal = _object(_HISTORICAL_TERMINAL, label="terminal smoke fixture")
    continuum = cast(
        tuple[Any, ...],
        _namespace(terminal["prospective_continuum_analysis"]),
    )
    incumbent = tuple(
        SimpleNamespace(
            **{
                **vars(endpoint),
                "comparisons": (
                    endpoint.comparisons
                    if endpoint.comparisons
                    else (
                        SimpleNamespace(
                            reference_id="pinned-pybdsf-master",
                            status="success",
                            observed_paired_standard_deviation=0.0,
                            positive_regression=0.0,
                            upper_confidence_limit=0.0,
                        ),
                    )
                ),
            }
        )
        for endpoint in continuum
    )
    decision = cast(
        dict[str, object],
        evaluator["compile_prospective_decision"](
            registry=load_prospective_endpoint_registry(
                evaluator["_REGISTRY"]
            ),
            current_continuum=continuum,
            incumbent_paired_continuum=incumbent,
            continuum_objectives=(),
            compact=terminal["prospective_compact"],
            compact_product_identity_equal=True,
            planning_deviation_by_family={},
            safety_results=dict.fromkeys(
                (
                    "finite-measurements",
                    "product-validity",
                    "schema-and-provenance-integrity",
                    "serial-and-existing-dask-determinism",
                    "write-once-publication",
                ),
                True,
            ),
        ),
    )
    summaries = {
        (finder, "smoke-input"): {
            "finder_id": finder,
            "input_id": "smoke-input",
        }
        for finder in (
            "current-hebog",
            "incumbent-hebog",
            "pinned-pybdsf-master",
            "released-pybdsf",
        )
    }
    retained = evaluator["_endpoint_summary_record"](
        summaries, expected_inputs=1
    )
    if (
        retained.get("summary_count") != _EXPECTED_SMOKE_SUMMARY_COUNT
        or not callable(evaluator.get("_truth_linked_tail_record"))
        or evaluator.get("_truth_linked_tail_record")
        is evaluator.get("_PREVIOUS_TRUTH_LINKED_TAIL_RECORD")
    ):
        raise ValueError("final cumulative terminal tail seam changed")
    record = {
        **decision,
        "terminal_publication_status": "pass",
    }
    output = directory / "final-cumulative-terminal-smoke.json"
    evaluator["_publish"](output, record)
    if _object(output, label="terminal smoke output") != record:
        raise ValueError("final cumulative terminal publication changed")
    try:
        evaluator["_publish"](output, record)
    except FileExistsError:
        pass
    else:
        raise ValueError("final cumulative terminal output is not write-once")
    return cast(dict[str, object], record)


def expected_bounded_smoke() -> dict[str, object]:
    """Run the bounded smoke in an isolated temporary directory."""
    with TemporaryDirectory(prefix="hebog-final-cumulative-smoke-") as value:
        return run_bounded_terminal_smoke(Path(value))


def bounded_smoke_summary(record: dict[str, object]) -> dict[str, object]:
    """Return the compact terminal-path evidence retained in contracts."""
    return {
        "all_required_endpoints_pass": record["all_required_endpoints_pass"],
        "comparison_status_counts": record["comparison_status_counts"],
        "cumulative_science_regression_ready": record[
            "cumulative_science_regression_ready"
        ],
        "record_canonical_sha256": canonical_sha256(record),
        "section_counts": record["section_counts"],
        "status": record["status"],
        "terminal_publication_status": record["terminal_publication_status"],
    }


def _expected_execution(
    verified: dict[str, object], smoke: dict[str, object]
) -> dict[str, object]:
    """Return the exact evaluation-only execution identity."""
    return {
        "bounded_smoke_canonical_sha256": canonical_sha256(smoke),
        "candidate_executions": 0,
        "completion_program_sha256": file_sha256(Path(__file__)),
        "current_scratch": str(_CURRENT_SCRATCH),
        "evaluation_program_sha256": file_sha256(_EVALUATOR),
        "incumbent_scratch": str(_INCUMBENT_SCRATCH),
        "output": str(_OUTPUT),
        "pybdsf_executions": 0,
        "reference_executions": 0,
        "verified_products": verified,
    }


def _git_revision() -> str:
    """Require a clean immutable evaluation checkout."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("final cumulative evaluation requires clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _verify_bindings(bindings: object, *, label: str) -> None:
    """Verify every frozen repository file binding by exact bytes."""
    if not isinstance(bindings, dict) or not bindings:
        raise PermissionError(f"final cumulative {label} bindings changed")
    for name, value in bindings.items():
        if not isinstance(value, dict):
            raise PermissionError(
                f"final cumulative {label} binding {name} changed"
            )
        path = value.get("path")
        sha256 = value.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(sha256, str)
            or file_sha256(_ROOT / path) != sha256
        ):
            raise PermissionError(
                f"final cumulative {label} binding {name} changed"
            )


def _validate_authority(
    verified: dict[str, object], smoke: dict[str, object]
) -> None:
    """Require exact separated identity and one-use evaluation authority."""
    identity = _object(_ROOT / _IDENTITY, label="final cumulative identity")
    implementation = _object(
        _ROOT / _IMPLEMENTATION, label="final cumulative implementation"
    )
    decision = _object(
        _ROOT / _EXECUTION_DECISION,
        label="final cumulative execution decision",
    )
    expected = _expected_execution(verified, smoke)
    implementation_binding = identity.get("implementation")
    decision_identity = decision.get("identity_review")
    if (
        file_sha256(_ROOT / _PRE_REVIEW) != _PRE_REVIEW_SHA256
        or not isinstance(implementation_binding, dict)
        or implementation_binding.get("path") != str(_IMPLEMENTATION)
        or implementation_binding.get("sha256")
        != canonical_sha256(implementation)
        or identity.get("status") != "frozen-non-executable"
        or identity.get("authorization")
        != dict.fromkeys(_AUTHORIZATION, False)
        or identity.get("verified_products") != verified
        or identity.get("bounded_terminal_smoke")
        != bounded_smoke_summary(smoke)
        or identity.get("expected_execution") != expected
        or identity.get("expected_execution_sha256")
        != canonical_sha256(expected)
        or decision.get("status")
        != "authorized-for-one-final-cumulative-evaluation"
        or decision.get("authorization") != _AUTHORIZATION
        or not isinstance(decision_identity, dict)
        or decision_identity.get("path") != str(_IDENTITY)
        or decision_identity.get("sha256") != canonical_sha256(identity)
        or decision.get("identity_review_sha256") != canonical_sha256(identity)
        or decision.get("expected_execution_sha256")
        != canonical_sha256(expected)
    ):
        raise PermissionError("final cumulative evaluation is not authorized")
    _verify_bindings(identity.get("program_bindings"), label="program")
    _verify_bindings(identity.get("fixture_bindings"), label="fixture")
    _git_revision()


def _evaluator_command(arguments: argparse.Namespace) -> list[str]:
    """Return the exact evaluation-only subprocess command."""
    return [
        sys.executable,
        str(_EVALUATOR),
        "--repository-root",
        str(arguments.repository_root),
        "--reference-reconstruction",
        str(arguments.reference_reconstruction),
        "--source-request",
        str(arguments.source_request),
        "--population",
        str(arguments.population),
        "--current-scratch",
        str(arguments.current_scratch),
        "--incumbent-scratch",
        str(arguments.incumbent_scratch),
        "--output",
        str(arguments.output),
    ]


def run_authorized_evaluation(arguments: argparse.Namespace) -> None:
    """Verify once, require authority, then run only the evaluator."""
    verified = verify_products(arguments)
    smoke = expected_bounded_smoke()
    _validate_authority(verified, smoke)
    subprocess.run(_evaluator_command(arguments), cwd=_ROOT, check=True)
    if not _resolved(_ROOT, arguments.output).is_file():
        raise ValueError("final cumulative evaluation did not publish output")


def _parse_args() -> argparse.Namespace:
    """Parse the fixed evaluation, verification, or bounded smoke command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument(
        "--reference-reconstruction",
        type=Path,
        default=_REFERENCE_RECONSTRUCTION,
    )
    parser.add_argument("--source-request", type=Path, default=_SOURCE_REQUEST)
    parser.add_argument("--population", type=Path, default=_POPULATION)
    parser.add_argument(
        "--current-scratch", type=Path, default=_CURRENT_SCRATCH
    )
    parser.add_argument(
        "--incumbent-scratch", type=Path, default=_INCUMBENT_SCRATCH
    )
    parser.add_argument(
        "--reconstruction-record",
        type=Path,
        default=_RECONSTRUCTION_RECORD,
    )
    parser.add_argument("--product-seal", type=Path, default=_PRODUCT_SEAL)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the bounded smoke, complete verification, or exact evaluation."""
    arguments = _parse_args()
    if arguments.smoke_only:
        print(
            json.dumps(
                bounded_smoke_summary(expected_bounded_smoke()),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    if arguments.verify_only:
        print(
            json.dumps(
                verify_products(arguments),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_authorized_evaluation(arguments)


if __name__ == "__main__":
    main()
