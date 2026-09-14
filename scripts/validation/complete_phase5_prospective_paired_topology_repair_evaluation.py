#!/usr/bin/env python3
"""Verify and complete the paired source-union topology repair."""

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
    _ROOT / "scripts/validation/"
    "complete_phase5_prospective_paired_tail_repair_evaluation.py"
)
_PARENT_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_tail_repair.py"
)
_REPAIRED_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
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
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-source-union-topology-repair-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-source-union-topology-repair-implementation-"
    "decision.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-source-union-topology-repair-identity-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-source-union-topology-repair-execution-"
    "decision.json"
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
    "4c90af3b355347df1cf2b3045e246a87c3e7e8f5e4f6354e3d38390ebd345cb4"
)
_PARENT_EVALUATOR_SHA256 = (
    "1974101dd6d4c577ec402191093f3af65f4a67ef7adb6dfb2f2a85e13e2fa8a0"
)
_REPAIRED_EVALUATOR_SHA256 = (
    "39a568bada625b751931aff649e4e815c5ed70f68809d902a52ce93cfeaec62a"
)
_PARENT_PREPARER_SHA256 = (
    "54f1416d544c7cc4dd84591dcf22e2ced21c24722286cea55e6b1e1d3c72ba77"
)
_PREPARER_SHA256 = (
    "b4c8f8eafb3c961f7696cd49c90e72aa52a81df13eb58980522b562212f0ce79"
)
_SOURCE_UNION_TAIL_SHA256 = (
    "18c8d43b32e28b22e64b9a9baa69e35ab32dd9582735da30a6791578eea27237"
)
_PRE_REVIEW_SHA256 = (
    "51f74baaf6ff5bdc8619cd9e3782586f596d39a210b76138d01e14fd23e4b99c"
)
_FAILED_IDENTITY_REVIEW_SHA256 = (
    "5572148d6604f52988fe256beb0ec1e2046c305f2e0d3a2d50c0ee862f2f9585"
)
_FAILED_EXECUTION_DECISION_SHA256 = (
    "3de3f6fc228b4d2c0c85e3cfb0a60938ab74858e8e617f5fefa8af409cf56423"
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
        raise ValueError("topology-repair completion import origin changed")


def _verify_repair_evidence() -> None:
    """Bind the exact parent, repair programs, and pre-review."""
    _require_import_origin()
    evidence = (
        (_PARENT_COMPLETION, _PARENT_COMPLETION_SHA256, "parent completion"),
        (_PARENT_EVALUATOR, _PARENT_EVALUATOR_SHA256, "parent evaluator"),
        (
            _REPAIRED_EVALUATOR,
            _REPAIRED_EVALUATOR_SHA256,
            "repaired evaluator",
        ),
        (_PARENT_PREPARER, _PARENT_PREPARER_SHA256, "parent preparer"),
        (_PREPARER, _PREPARER_SHA256, "source-union preparer"),
        (_SOURCE_UNION_TAIL, _SOURCE_UNION_TAIL_SHA256, "source-union tail"),
        (_PRE_REVIEW, _PRE_REVIEW_SHA256, "repair pre-review"),
    )
    for path, expected, label in evidence:
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"paired topology {label} changed")


def _load_parent_completion() -> dict[str, Any]:
    """Load the complete unchanged product verifier."""
    _verify_repair_evidence()
    return runpy.run_path(str(_PARENT_COMPLETION))


def _load_repaired_evaluator() -> dict[str, Any]:
    """Load and verify the source-union evaluator overlay."""
    overlay = runpy.run_path(str(_REPAIRED_EVALUATOR))
    evaluator = overlay["load_topology_repaired_evaluator"]()
    if not callable(evaluator.get("main")):
        raise ValueError("paired topology evaluator seam changed")
    return cast(dict[str, Any], evaluator)


def verify_products(arguments: argparse.Namespace) -> dict[str, object]:
    """Rehash all preserved evidence and verify every repaired seam."""
    parent = _load_parent_completion()
    verified = dict(parent["verify_products"](arguments))
    if verified.get("evaluator_sha256") != _PARENT_EVALUATOR_SHA256:
        raise ValueError("paired topology parent product proof changed")
    _load_repaired_evaluator()
    return {
        **verified,
        "evaluator_sha256": _REPAIRED_EVALUATOR_SHA256,
        "source_union_preparer_sha256": _PREPARER_SHA256,
        "source_union_tail_sha256": _SOURCE_UNION_TAIL_SHA256,
        "topology_parent_completion_sha256": _PARENT_COMPLETION_SHA256,
        "topology_parent_evaluator_sha256": _PARENT_EVALUATOR_SHA256,
        "topology_repair_pre_review_sha256": _PRE_REVIEW_SHA256,
    }


def verify_tail(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Run the exact real-product diagnostic tail without publication."""
    overlay = runpy.run_path(str(_REPAIRED_EVALUATOR))
    return cast(
        dict[str, object], overlay["verify_truth_linked_tail"](arguments)
    )


def _git_revision() -> str:
    """Return the clean immutable completion checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError(
            "topology-repair completion requires a clean checkout"
        )
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _require_implementation_ancestor(
    implementation_revision: object, execution_revision: str
) -> str:
    """Require the reviewed implementation in the execution history."""
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
        raise ValueError("topology-repair implementation revision changed")
    return implementation_revision


def _expected_execution_fields(
    arguments: argparse.Namespace,
    verified: Mapping[str, object],
    tail: Mapping[str, object],
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
        "tail_verification": dict(tail),
    }


def _validate_authority(
    arguments: argparse.Namespace,
    verified: Mapping[str, object],
    tail: Mapping[str, object],
) -> None:
    """Require a new exact one-use evaluation-only decision."""
    review = _load_json(_IDENTITY_REVIEW, label="topology repair review")
    decision = _load_json(
        _EXECUTION_DECISION, label="topology repair decision"
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
            tail,
            implementation_revision=implementation_revision,
        )
    )
    if (
        review.get("status")
        != "ready-for-exact-paired-topology-repair-evaluation"
        or review.get("verified_products") != dict(verified)
        or review.get("tail_verification") != dict(tail)
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
        != "authorized-for-one-exact-paired-topology-repair-evaluation"
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
        raise ValueError("paired topology-repair evaluation is not authorized")


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
    """Run only the evaluator after full product and tail verification."""
    verified = verify_products(arguments)
    tail = verify_tail(arguments)
    _validate_authority(arguments, verified, tail)
    subprocess.run(_evaluator_command(arguments), cwd=_ROOT, check=True)
    if not arguments.output.is_file():
        raise ValueError("paired evaluation did not publish its atomic output")


def _parse_args() -> argparse.Namespace:
    """Parse fixed no-write checks or one authorized completion."""
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
    parser.add_argument("--verify-tail", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify without writes or consume a future exact authority."""
    arguments = _parse_args()
    if arguments.verify_only:
        record: dict[str, object] = {
            "products": verify_products(arguments),
        }
        if arguments.verify_tail:
            record["truth_linked_tail"] = verify_tail(arguments)
        print(json.dumps(record, allow_nan=False, indent=2, sort_keys=True))
        return
    run_authorized_completion(arguments)


if __name__ == "__main__":
    main()
