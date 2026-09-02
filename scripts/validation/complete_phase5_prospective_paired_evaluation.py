#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Complete the prospective paired evaluation from verified products."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[2]
_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_prospective_paired_cumulative.py"
)
_RECONSTRUCTION_PROGRAM = (
    _ROOT / "scripts/validation/"
    "reconstruct_phase5_prospective_paired_incumbent.py"
)
_ORIGINAL_REPLAY_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-paired-cumulative-replay-"
    "identity-review.json"
)
_ORIGINAL_REPLAY_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-cumulative-replay-"
    "execution-decision.json"
)
_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-paired-incumbent-"
    "provenance-repair-pre-review.json"
)
_REPAIR_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-incumbent-"
    "provenance-repair-implementation-decision.json"
)
_RECONSTRUCTION_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-paired-incumbent-"
    "reconstruction-identity-review.json"
)
_RECONSTRUCTION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-incumbent-"
    "reconstruction-execution-decision.json"
)
_COMPLETION_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-paired-evaluation-"
    "completion-pre-review.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-paired-evaluation-"
    "completion-identity-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-evaluation-"
    "completion-execution-decision.json"
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
_CURRENT_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CURRENT_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_CURRENT_PRODUCT_SET_SHA256 = (
    "6bcb2959c56173d1a930eb14b3a794727649defc1b52dc1d9d70cd041d401014"
)
_INCUMBENT_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_INCUMBENT_SOURCE_TREE_SHA256 = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_INCUMBENT_CONFIGURATION_SHA256 = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
)
_EVALUATOR_SHA256 = (
    "44d7d6475832becfdf02d475a4654de05284fd2320080a8a28734e39d9aeee51"
)
_RECONSTRUCTION_PROGRAM_SHA256 = (
    "79d59cb8d54867f797bb9fa473e8767bfa46d9ff99cb42a4d3bb38eb9d8efebc"
)
_ORIGINAL_REPLAY_REVIEW_SHA256 = (
    "4f5211ed16e2ea2cf844c1e48269f64de53b8aa62614483b29e2ee4f255d04fa"
)
_ORIGINAL_REPLAY_DECISION_SHA256 = (
    "f91e2124a8ae744746882f70835988de7e58b75db90e11a47c1f31cfc8f6f2e7"
)
_REPAIR_PRE_REVIEW_SHA256 = (
    "5fbafa4e3d4f215d6668a7f3ac2fda27e7da52d4341ead266b9c2f72342a5bb5"
)
_REPAIR_IMPLEMENTATION_DECISION_SHA256 = (
    "97391a8d5d92765a05f616b10f13f4b40ff3bb21b8d7e63ffca34cc775b6d617"
)
_RECONSTRUCTION_REVIEW_SHA256 = (
    "ed96831164cd4fa54feb344cea6740814ea8063b7876378a05f9e889efb247b6"
)
_RECONSTRUCTION_DECISION_SHA256 = (
    "10e7f0980ce70be6fedef0a84c06d736b24c054838df8464216ed2aa419f3f38"
)
_COMPLETION_PRE_REVIEW_SHA256 = (
    "84a496bd88a6686b5cc31099e35b4897e2477b21fe11c18e06670704d1a8f066"
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
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_REFERENCE_RUN_COUNT = 9600
_SHA256_HEX_LENGTH = 64
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


def _require_invocation(arguments: argparse.Namespace) -> None:
    """Require the one fixed evaluation-only namespace."""
    expected = {
        "repository_root": _ROOT,
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "source_request": _SOURCE_REQUEST,
        "population": _POPULATION,
        "current_scratch": _CURRENT_SCRATCH,
        "incumbent_scratch": _INCUMBENT_SCRATCH,
        "reconstruction_record": _RECONSTRUCTION_RECORD,
        "output": _OUTPUT,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(f"paired evaluation completion {field} changed")
    if arguments.output.exists():
        raise FileExistsError("paired evaluation output already exists")


def _verify_static_evidence(arguments: argparse.Namespace) -> None:
    """Verify every program, decision, population, and reference identity."""
    evidence = (
        (_EVALUATOR, _EVALUATOR_SHA256, "paired evaluator"),
        (
            _RECONSTRUCTION_PROGRAM,
            _RECONSTRUCTION_PROGRAM_SHA256,
            "reconstruction program",
        ),
        (
            _ORIGINAL_REPLAY_REVIEW,
            _ORIGINAL_REPLAY_REVIEW_SHA256,
            "original replay review",
        ),
        (
            _ORIGINAL_REPLAY_DECISION,
            _ORIGINAL_REPLAY_DECISION_SHA256,
            "original replay decision",
        ),
        (
            _REPAIR_PRE_REVIEW,
            _REPAIR_PRE_REVIEW_SHA256,
            "repair pre-review",
        ),
        (
            _REPAIR_IMPLEMENTATION_DECISION,
            _REPAIR_IMPLEMENTATION_DECISION_SHA256,
            "repair implementation decision",
        ),
        (
            _RECONSTRUCTION_REVIEW,
            _RECONSTRUCTION_REVIEW_SHA256,
            "reconstruction review",
        ),
        (
            _RECONSTRUCTION_DECISION,
            _RECONSTRUCTION_DECISION_SHA256,
            "reconstruction decision",
        ),
        (
            _COMPLETION_PRE_REVIEW,
            _COMPLETION_PRE_REVIEW_SHA256,
            "completion pre-review",
        ),
        (
            arguments.reference_reconstruction / "recovery.json",
            _REFERENCE_RECONSTRUCTION_SHA256,
            "reference reconstruction",
        ),
        (arguments.source_request, _SOURCE_REQUEST_SHA256, "source request"),
        (arguments.population, _POPULATION_SHA256, "paired population"),
    )
    for path, expected, label in evidence:
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"paired evaluation {label} changed")


def _verify_reconstruction_record(arguments: argparse.Namespace) -> str:
    """Verify the complete authentic incumbent recovery record."""
    record = _load_json(
        arguments.reconstruction_record, label="incumbent reconstruction"
    )
    canonical = record.pop("record_canonical_sha256", None)
    if canonical != canonical_sha256(record):
        raise ValueError("incumbent reconstruction canonical identity changed")
    required = {
        "status": "complete",
        "candidate_revision": _INCUMBENT_REVISION,
        "candidate_source_tree_sha256": _INCUMBENT_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": _INCUMBENT_CONFIGURATION_SHA256,
        "execution_decision_sha256": _RECONSTRUCTION_DECISION_SHA256,
        "reconstruction_program_sha256": _RECONSTRUCTION_PROGRAM_SHA256,
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "population_sha256": _POPULATION_SHA256,
        "input_count": _EXPECTED_INPUT_COUNT,
        "compact_product_count": 800,
        "continuum_product_count": 1600,
        "current_candidate_execution_started": False,
        "scientific_policy_changed": False,
    }
    if any(record.get(key) != value for key, value in required.items()):
        raise ValueError("incumbent reconstruction identity changed")
    product_set = record.get("product_set_sha256")
    if (
        not isinstance(product_set, str)
        or len(product_set) != _SHA256_HEX_LENGTH
    ):
        raise ValueError("incumbent reconstruction product identity is absent")
    return product_set


def verify_products(arguments: argparse.Namespace) -> dict[str, object]:
    """Rehash both completed product sets without compiling science."""
    _require_invocation(arguments)
    _verify_static_evidence(arguments)
    incumbent_expected = _verify_reconstruction_record(arguments)
    evaluator = runpy.run_path(str(_EVALUATOR))
    materializer = evaluator["_load_materializer"]()
    smoke = runpy.run_path(str(evaluator["_SMOKE_EVALUATOR"]))
    identifiers = materializer["_selected_inputs"](
        arguments.source_request, arguments.population
    )
    verified, _ = materializer["_verified_reference"](
        arguments.repository_root, arguments.reference_reconstruction
    )
    if (
        len(identifiers) != _EXPECTED_INPUT_COUNT
        or len(verified.runs) != _EXPECTED_REFERENCE_RUN_COUNT
    ):
        raise ValueError("paired evaluation population changed")
    current_product_set = smoke["_verify_product_set"](
        identifiers,
        arguments.current_scratch,
        configuration=_CURRENT_CONFIGURATION_SHA256,
        source_tree=_CURRENT_SOURCE_TREE_SHA256,
    )
    incumbent_product_set = smoke["_verify_product_set"](
        identifiers,
        arguments.incumbent_scratch,
        configuration=_INCUMBENT_CONFIGURATION_SHA256,
        source_tree=_INCUMBENT_SOURCE_TREE_SHA256,
    )
    if (
        current_product_set != _CURRENT_PRODUCT_SET_SHA256
        or incumbent_product_set != incumbent_expected
    ):
        raise ValueError("paired evaluation product-set identity changed")
    if not all(
        callable(evaluator.get(name))
        for name in (
            "_compile_incumbent_pair",
            "compile_prospective_decision",
            "main",
        )
    ):
        raise ValueError("paired evaluation compiler seam changed")
    return {
        "current_configuration_sha256": _CURRENT_CONFIGURATION_SHA256,
        "current_product_set_sha256": current_product_set,
        "current_revision": _CURRENT_REVISION,
        "current_source_tree_sha256": _CURRENT_SOURCE_TREE_SHA256,
        "evaluator_sha256": _EVALUATOR_SHA256,
        "incumbent_configuration_sha256": (_INCUMBENT_CONFIGURATION_SHA256),
        "incumbent_product_set_sha256": incumbent_product_set,
        "incumbent_revision": _INCUMBENT_REVISION,
        "incumbent_source_tree_sha256": _INCUMBENT_SOURCE_TREE_SHA256,
        "input_count_per_candidate": len(identifiers),
        "reconstruction_record_sha256": file_sha256(
            arguments.reconstruction_record
        ),
        "reference_run_count": len(verified.runs),
        "status": "pass",
        "candidate_execution_started": False,
    }


def _git_revision() -> str:
    """Return the clean immutable evaluation checkout revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("paired evaluation requires a clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _expected_execution_fields(
    arguments: argparse.Namespace,
    verified: Mapping[str, object],
    *,
    identity_review_sha256: str,
    implementation_revision: str,
) -> dict[str, object]:
    """Return every identity covered by the one-use completion authority."""
    return {
        **dict(verified),
        "completion_program_sha256": file_sha256(Path(__file__).resolve()),
        "current_scratch": str(arguments.current_scratch),
        "identity_review_sha256": identity_review_sha256,
        "implementation_revision": implementation_revision,
        "incumbent_scratch": str(arguments.incumbent_scratch),
        "output_path": str(arguments.output),
        "population_sha256": _POPULATION_SHA256,
        "reconstruction_decision_sha256": (_RECONSTRUCTION_DECISION_SHA256),
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "source_request_sha256": _SOURCE_REQUEST_SHA256,
    }


def _validate_authority(
    arguments: argparse.Namespace, verified: Mapping[str, object]
) -> None:
    """Require the exact review and one-use evaluation-only decision."""
    review = _load_json(_IDENTITY_REVIEW, label="completion identity review")
    decision = _load_json(
        _EXECUTION_DECISION, label="completion execution decision"
    )
    review_sha256 = file_sha256(_IDENTITY_REVIEW)
    revision = _git_revision()
    expected_execution = canonical_sha256(
        _expected_execution_fields(
            arguments,
            verified,
            identity_review_sha256=review_sha256,
            implementation_revision=revision,
        )
    )
    if (
        review.get("status") != "ready-for-exact-evaluation-only-completion"
        or review.get("implementation_revision") != revision
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
        != "authorized-for-one-exact-evaluation-only-completion"
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
        raise ValueError("paired evaluation completion is not authorized")


def _evaluator_command(arguments: argparse.Namespace) -> list[str]:
    """Return the exact unchanged evaluator command."""
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


def run_authorized_completion(arguments: argparse.Namespace) -> None:
    """Run only the exact evaluator after complete product verification."""
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
    """Verify without writes or consume the exact evaluation authority."""
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
