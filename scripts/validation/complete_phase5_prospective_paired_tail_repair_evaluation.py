#!/usr/bin/env python3
"""Complete paired evaluation with the reviewed tail-only repair."""

from __future__ import annotations

import argparse
import inspect
import json
import runpy
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[2]
_PARENT_COMPLETION = (
    _ROOT
    / "scripts/validation/complete_phase5_prospective_paired_evaluation.py"
)
_PARENT_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_prospective_paired_cumulative.py"
)
_REPAIRED_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_tail_repair.py"
)
_TAIL_REPAIR = (
    _ROOT
    / "scripts/validation/repair_phase5_prospective_paired_tail_diagnostics.py"
)
_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-tail-diagnostic-repair-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-tail-diagnostic-repair-implementation-"
    "decision.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-tail-diagnostic-repair-identity-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-tail-diagnostic-repair-execution-decision.json"
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
    "/private/tmp/hebog-phase5-prospective-paired-current-937737d"
)
_INCUMBENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-prospective-paired-incumbent-authentic-85d5807"
)
_RECONSTRUCTION_RECORD = Path(
    "benchmark-results/phase-5/"
    "prospective-paired-incumbent-reconstruction.json"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/prospective-paired-cumulative-decision.json"
)
_PARENT_COMPLETION_SHA256 = (
    "76ecc0ee13e2fa05d3da07cb3be77a808e306771c6ca445357eafef97edb0391"
)
_PARENT_EVALUATOR_SHA256 = (
    "44d7d6475832becfdf02d475a4654de05284fd2320080a8a28734e39d9aeee51"
)
_REPAIRED_EVALUATOR_SHA256 = (
    "1974101dd6d4c577ec402191093f3af65f4a67ef7adb6dfb2f2a85e13e2fa8a0"
)
_TAIL_REPAIR_SHA256 = (
    "54e592071cbab516ddccfa0edc28c4fe2b7e5cfcdfe9de997307e1231cc70703"
)
_REPAIR_PRE_REVIEW_SHA256 = (
    "e1130b9b6b8825ab22e8f74f71f9429f98fdbf803312d45a54d0ec36647fb932"
)
_FAILED_IDENTITY_REVIEW_SHA256 = (
    "75d460489a296bb87540954d37639080243a1c807e7532cb27626f3e105221ad"
)
_FAILED_EXECUTION_DECISION_SHA256 = (
    "4624d6d9daea442f6bfec1a7fe8ed34d42c738db623488ee88da13560fc16a06"
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
_SHA1_HEX_LENGTH = 40
_PROHIBITED_AUTHORIZATIONS = (
    "candidate_execution_authorized",
    "cutover_authorized",
    "fresh_qualification_authorized",
    "optimization_authorized",
    "release_authorized",
    "rescoring_authorized",
    "scientific_change_authorized",
    "threshold_or_margin_tuning_authorized",
    "viewed_data_execution_authorized",
)


def _load_json(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, object], value)


def _require_import_origin() -> None:
    """Require Hebog imports to come from this checkout."""
    source = inspect.getsourcefile(file_sha256)
    expected = _ROOT / "src/hebog/validation/external_runners.py"
    if source is None or Path(source).resolve() != expected.resolve():
        raise ValueError("tail-repair completion Hebog import origin changed")


def _verify_repair_evidence() -> None:
    """Bind the frozen parent, repair review, and repair programs."""
    _require_import_origin()
    evidence = (
        (
            _PARENT_COMPLETION,
            _PARENT_COMPLETION_SHA256,
            "parent completion",
        ),
        (_PARENT_EVALUATOR, _PARENT_EVALUATOR_SHA256, "parent evaluator"),
        (
            _REPAIRED_EVALUATOR,
            _REPAIRED_EVALUATOR_SHA256,
            "repaired evaluator",
        ),
        (_TAIL_REPAIR, _TAIL_REPAIR_SHA256, "tail repair"),
        (
            _REPAIR_PRE_REVIEW,
            _REPAIR_PRE_REVIEW_SHA256,
            "repair pre-review",
        ),
    )
    for path, expected, label in evidence:
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"paired evaluation {label} changed")


def _load_parent_completion() -> dict[str, Any]:
    """Load the unchanged product verifier after checking its identity."""
    if file_sha256(_PARENT_COMPLETION) != _PARENT_COMPLETION_SHA256:
        raise ValueError("paired evaluation parent completion changed")
    return runpy.run_path(str(_PARENT_COMPLETION))


def _load_repaired_evaluator() -> dict[str, Any]:
    """Load and exercise the exact evaluator overlay seams."""
    overlay = runpy.run_path(str(_REPAIRED_EVALUATOR))
    evaluator = overlay["load_repaired_evaluator"]()
    if (
        not callable(evaluator.get("main"))
        or not callable(evaluator.get("_truth_linked_tail_record"))
        or not callable(evaluator.get("_ORIGINAL_TRUTH_LINKED_TAIL_RECORD"))
        or evaluator["_truth_linked_tail_record"]
        is evaluator["_ORIGINAL_TRUTH_LINKED_TAIL_RECORD"]
    ):
        raise ValueError("paired evaluation tail repair seam changed")
    return evaluator


def verify_products(arguments: argparse.Namespace) -> dict[str, object]:
    """Rehash every sealed input and verify the repaired evaluator seam."""
    _verify_repair_evidence()
    parent = _load_parent_completion()
    verified = dict(parent["verify_products"](arguments))
    parent_evaluator = verified.pop("evaluator_sha256", None)
    if parent_evaluator != _PARENT_EVALUATOR_SHA256:
        raise ValueError("paired evaluation parent product proof changed")
    _load_repaired_evaluator()
    return {
        **verified,
        "evaluator_sha256": _REPAIRED_EVALUATOR_SHA256,
        "parent_completion_sha256": _PARENT_COMPLETION_SHA256,
        "parent_evaluator_sha256": _PARENT_EVALUATOR_SHA256,
        "repair_pre_review_sha256": _REPAIR_PRE_REVIEW_SHA256,
        "tail_repair_sha256": _TAIL_REPAIR_SHA256,
    }


def _git_revision() -> str:
    """Return the clean immutable completion checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("tail-repair completion requires a clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _require_implementation_ancestor(
    implementation_revision: object, execution_revision: str
) -> str:
    """Require the reviewed repair in the clean execution history."""
    if (
        not isinstance(implementation_revision, str)
        or len(implementation_revision) != _SHA1_HEX_LENGTH
        or subprocess.run(
            (
                "git",
                "merge-base",
                "--is-ancestor",
                implementation_revision,
                execution_revision,
            ),
            cwd=_ROOT,
            check=False,
            capture_output=True,
        ).returncode
        != 0
    ):
        raise ValueError("tail-repair implementation revision changed")
    return implementation_revision


def _expected_execution_fields(
    arguments: argparse.Namespace,
    verified: Mapping[str, object],
    *,
    implementation_revision: str,
) -> dict[str, object]:
    """Return every identity covered by a future one-use authority."""
    return {
        **dict(verified),
        "completion_program_sha256": file_sha256(Path(__file__).resolve()),
        "current_scratch": str(arguments.current_scratch),
        "failed_execution_decision_sha256": (
            _FAILED_EXECUTION_DECISION_SHA256
        ),
        "failed_identity_review_sha256": _FAILED_IDENTITY_REVIEW_SHA256,
        "implementation_decision_sha256": file_sha256(
            _IMPLEMENTATION_DECISION
        ),
        "implementation_revision": implementation_revision,
        "incumbent_scratch": str(arguments.incumbent_scratch),
        "output_path": str(arguments.output),
        "population_sha256": _POPULATION_SHA256,
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "source_request_sha256": _SOURCE_REQUEST_SHA256,
    }


def _validate_authority(
    arguments: argparse.Namespace, verified: Mapping[str, object]
) -> None:
    """Require a future exact one-use evaluation-only decision."""
    review = _load_json(_IDENTITY_REVIEW, label="tail-repair identity review")
    decision = _load_json(
        _EXECUTION_DECISION, label="tail-repair execution decision"
    )
    review_sha256 = file_sha256(_IDENTITY_REVIEW)
    revision = _git_revision()
    implementation_revision = _require_implementation_ancestor(
        review.get("implementation_revision"), revision
    )
    expected_execution = canonical_sha256(
        _expected_execution_fields(
            arguments,
            verified,
            implementation_revision=implementation_revision,
        )
    )
    if (
        review.get("status") != "ready-for-exact-paired-tail-repair-evaluation"
        or review.get("verified_products") != dict(verified)
        or review.get("expected_execution_sha256") != expected_execution
        or review.get("authorization")
        != dict.fromkeys(
            (
                "candidate_execution_authorized",
                "cutover_authorized",
                "evaluation_authorized",
                "fresh_qualification_authorized",
                "optimization_authorized",
                "release_authorized",
                "rescoring_authorized",
                "scientific_change_authorized",
                "threshold_or_margin_tuning_authorized",
                "viewed_data_execution_authorized",
            ),
            False,
        )
        or decision.get("status")
        != "authorized-for-one-exact-paired-tail-repair-evaluation"
        or decision.get("evaluation_authorized") is not True
        or decision.get("expected_execution_sha256") != expected_execution
        or decision.get("identity_review")
        != {
            "path": str(_IDENTITY_REVIEW.relative_to(_ROOT)),
            "sha256": review_sha256,
        }
        or decision.get("prohibited_authorizations")
        != dict.fromkeys(_PROHIBITED_AUTHORIZATIONS, False)
    ):
        raise ValueError("paired tail-repair evaluation is not authorized")


def _evaluator_command(arguments: argparse.Namespace) -> list[str]:
    """Return the repaired evaluation-only command."""
    return [
        sys.executable,
        str(_REPAIRED_EVALUATOR),
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


def run_authorized_completion(arguments: argparse.Namespace) -> None:
    """Run only the repaired evaluator after complete product verification."""
    verified = verify_products(arguments)
    _validate_authority(arguments, verified)
    subprocess.run(_evaluator_command(arguments), cwd=_ROOT, check=True)
    if not arguments.output.is_file():
        raise ValueError("paired evaluation did not publish its atomic output")


def _parse_args() -> argparse.Namespace:
    """Parse one fixed no-write check or evaluation-only completion."""
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
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify without writes or consume a future exact authority."""
    arguments = _parse_args()
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
    run_authorized_completion(arguments)


if __name__ == "__main__":
    main()
