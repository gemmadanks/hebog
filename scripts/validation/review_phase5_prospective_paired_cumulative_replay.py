#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify or run the frozen prospective current/incumbent paired replay."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.prospective_science_contract import (
    load_prospective_endpoint_registry,
)

_ROOT = Path(__file__).parents[2]
_CURRENT_ROOT = _ROOT
_INCUMBENT_ROOT = Path(
    "/private/tmp/hebog-phase5-prospective-incumbent-85d5807"
)
_CURRENT_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CURRENT_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_INCUMBENT_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_INCUMBENT_SOURCE_TREE_SHA256 = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_INCUMBENT_CONFIGURATION_SHA256 = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_SOURCE_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_REGISTRY_SHA256 = (
    "095354bce2f34ae257574f9168770a194f1f5b00024db0ec5bcafdafba006a7e"
)
_DECISION_CONTRACT_SHA256 = (
    "f70f321397618b9f63d3dd03d650a5bbc73f8aad5e5fa91f15a198a99bdb38f9"
)
_APPROVED_REVIEW_SHA256 = (
    "77bd4b82cc7526b5e6f1b276ea16c887428c92f1c18126071405de69a07dce82"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_REFERENCE_RUN_COUNT = 9600
_EXPECTED_COMPARISON_COUNT = 1187
_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_paired_products.py"
)
_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_prospective_paired_cumulative.py"
)
_PREPARER = (
    _ROOT / "scripts/validation/prepare_phase5_prospective_paired_evidence.py"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-evidence-"
    "implementation-decision.json"
)
_APPROVED_REVIEW = (
    _ROOT / "config/contracts/phase-5-publication-scale-persistence-"
    "root-cause-pre-review.json"
)
_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_DECISION_CONTRACT = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-decision-contract.json"
)
_POPULATION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-population.json"
)
_POWER_AUDIT = (
    _ROOT / "config/contracts/phase-5-prospective-paired-power-audit.json"
)
_TAIL_SENTINELS = (
    _ROOT / "config/contracts/phase-5-prospective-paired-tail-sentinels.json"
)
_SOURCE_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_CONTINUUM_MANIFEST = (
    _ROOT / "config/datasets/phase-5-external-post-failure-continuum.json"
)
_SMOKE = (
    _ROOT / "benchmark-results/phase-5/"
    "prospective-science-smoke-publication-scale-persistence.json"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_CURRENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-prospective-paired-current-937737d"
)
_INCUMBENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-prospective-paired-incumbent-85d5807"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/prospective-paired-cumulative-decision.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-paired-cumulative-replay-"
    "execution-decision.json"
)
_PROHIBITED_AUTHORIZATIONS = (
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


def _load_materializer() -> dict[str, Any]:
    """Load the exact publication candidate over the generalized CLI."""
    prospective = runpy.run_path(str(_MATERIALIZER))
    materializer = cast(
        dict[str, Any], prospective["_load_materializer"](_ROOT)
    )
    materializer["_candidate_tasks"] = prospective["_candidate_tasks"]
    return materializer


def _git_revision(root: Path) -> str:
    """Return one immutable candidate checkout revision."""
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=root, text=True
    ).strip()


def _require_candidate_root(
    root: Path,
    *,
    revision: str | None,
    source_tree: str,
    label: str,
) -> None:
    """Verify one exact candidate checkout without altering it."""
    if not root.is_dir() or (
        revision is not None and _git_revision(root) != revision
    ):
        raise ValueError(f"{label} revision changed")
    if source_tree_sha256(root) != source_tree:
        raise ValueError(f"{label} source tree changed")


def _require_invocation(arguments: argparse.Namespace) -> None:
    """Require one prospective namespace before any write can begin."""
    expected = {
        "current_root": _CURRENT_ROOT,
        "incumbent_root": _INCUMBENT_ROOT,
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "current_scratch": _CURRENT_SCRATCH,
        "incumbent_scratch": _INCUMBENT_SCRATCH,
        "output": _OUTPUT,
        "workers": 2,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(f"prospective paired replay {field} changed")


def _verify_static_contracts() -> dict[str, str]:
    """Verify immutable science inputs and approved implementation scope."""
    expected = (
        (_APPROVED_REVIEW, _APPROVED_REVIEW_SHA256, "approved review"),
        (_REGISTRY, _REGISTRY_SHA256, "endpoint registry"),
        (
            _DECISION_CONTRACT,
            _DECISION_CONTRACT_SHA256,
            "decision contract",
        ),
        (_SOURCE_REQUEST, _SOURCE_REQUEST_SHA256, "source request"),
    )
    for path, sha256, label in expected:
        if not path.is_file() or file_sha256(path) != sha256:
            raise ValueError(f"prospective paired {label} changed")
    decision = _load_json(
        _IMPLEMENTATION_DECISION, label="implementation decision"
    )
    authorization = decision.get("authorization")
    if (
        decision.get("approved_review_sha256") != _APPROVED_REVIEW_SHA256
        or not isinstance(authorization, dict)
        or authorization.get("implementation_authorized") is not True
        or any(
            value is not False
            for key, value in authorization.items()
            if key != "implementation_authorized"
        )
    ):
        raise ValueError("prospective paired implementation scope changed")
    return {
        "decision_contract_sha256": _DECISION_CONTRACT_SHA256,
        "endpoint_registry_sha256": _REGISTRY_SHA256,
        "implementation_decision_sha256": file_sha256(
            _IMPLEMENTATION_DECISION
        ),
        "population_sha256": file_sha256(_POPULATION),
        "power_audit_sha256": file_sha256(_POWER_AUDIT),
        "tail_sentinels_sha256": file_sha256(_TAIL_SENTINELS),
    }


def _verify_population_and_power() -> dict[str, object]:
    """Reproduce exact input, sentinel, and endpoint power identities."""
    materializer = _load_materializer()
    identifiers = materializer["_selected_inputs"](
        _SOURCE_REQUEST, _POPULATION
    )
    if len(identifiers) != _EXPECTED_INPUT_COUNT:
        raise ValueError("prospective paired input count changed")
    preparer = runpy.run_path(str(_PREPARER))
    sentinels = _load_json(_TAIL_SENTINELS, label="tail sentinels")
    reproduced = preparer["select_result_neutral_tail_sentinels"](
        request=_load_json(_SOURCE_REQUEST, label="source request"),
        continuum_manifest=_load_json(
            _CONTINUUM_MANIFEST, label="Continuum manifest"
        ),
        count_per_dataset_and_sentinel=sentinels[
            "count_per_dataset_and_sentinel"
        ],
    )
    if reproduced["membership_sha256"] != sentinels.get("membership_sha256"):
        raise ValueError("prospective paired tail sentinels changed")
    power = preparer["build_aligned_prospective_power_audit"](
        registry=load_prospective_endpoint_registry(_REGISTRY),
        external_protocol=_load_json(
            _ROOT / "config/contracts/phase-5-external-comparison.json",
            label="external protocol",
        ),
        smoke_record=_load_json(_SMOKE, label="prospective smoke"),
    )
    frozen_power = _load_json(_POWER_AUDIT, label="power audit")
    for key, value in power.items():
        if frozen_power.get(key) != value:
            raise ValueError("prospective paired power design changed")
    if (
        power.get("status") != "pass"
        or power.get("comparison_count") != _EXPECTED_COMPARISON_COUNT
    ):
        raise ValueError("prospective paired design is not adequately powered")
    return {
        "comparison_count": power["comparison_count"],
        "input_count": len(identifiers),
        "sentinel_membership_count": reproduced["membership_count"],
        "sentinel_unique_input_count": reproduced["unique_input_count"],
    }


def _materializer_arguments(
    arguments: argparse.Namespace,
    *,
    mode: str,
) -> SimpleNamespace:
    """Build one exact no-write producer invocation."""
    return SimpleNamespace(
        repository_root=(
            arguments.current_root
            if mode == "current"
            else arguments.incumbent_root
        ),
        tooling_root=_ROOT,
        reference_reconstruction=arguments.reference_reconstruction,
        source_request=_SOURCE_REQUEST,
        population=_POPULATION,
        scratch=(
            arguments.current_scratch
            if mode == "current"
            else arguments.incumbent_scratch
        ),
        candidate_mode=mode,
        candidate_revision=(_CURRENT_REVISION if mode == "current" else None),
        candidate_source_tree_sha256=(
            _CURRENT_SOURCE_TREE_SHA256 if mode == "current" else None
        ),
        candidate_configuration_sha256=(
            _CURRENT_CONFIGURATION_SHA256 if mode == "current" else None
        ),
        workers=arguments.workers,
    )


def _verify_candidate_tasks(
    arguments: argparse.Namespace,
    *,
    mode: str,
    revision: str,
    source_tree: str,
    configuration: str,
) -> int:
    """Exercise the exact future producer without creating candidate data."""
    materializer = _load_materializer()
    invocation = _materializer_arguments(arguments, mode=mode)
    tasks = materializer["_candidate_tasks"](invocation)
    if len(tasks) != _EXPECTED_INPUT_COUNT:
        raise ValueError(f"prospective paired {mode} task count changed")
    identities = {
        (
            task.get("candidate_revision"),
            task.get("source_tree_sha256"),
            task.get("configuration_sha256"),
        )
        for task in tasks
    }
    if identities != {(revision, source_tree, configuration)}:
        raise ValueError(f"prospective paired {mode} task identity changed")
    return len(tasks)


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity a future one-replay decision must bind."""
    return {
        "comparison_count": _EXPECTED_COMPARISON_COUNT,
        "current_configuration_sha256": _CURRENT_CONFIGURATION_SHA256,
        "current_revision": _CURRENT_REVISION,
        "current_root": str(arguments.current_root),
        "current_scratch": str(arguments.current_scratch),
        "current_source_tree_sha256": _CURRENT_SOURCE_TREE_SHA256,
        "decision_contract_sha256": _DECISION_CONTRACT_SHA256,
        "endpoint_registry_sha256": _REGISTRY_SHA256,
        "evaluator_sha256": file_sha256(_EVALUATOR),
        "incumbent_configuration_sha256": (_INCUMBENT_CONFIGURATION_SHA256),
        "incumbent_revision": _INCUMBENT_REVISION,
        "incumbent_root": str(arguments.incumbent_root),
        "incumbent_scratch": str(arguments.incumbent_scratch),
        "incumbent_source_tree_sha256": _INCUMBENT_SOURCE_TREE_SHA256,
        "input_count_per_candidate": _EXPECTED_INPUT_COUNT,
        "materializer_sha256": file_sha256(_MATERIALIZER),
        "output_path": str(arguments.output),
        "population_sha256": file_sha256(_POPULATION),
        "power_audit_sha256": file_sha256(_POWER_AUDIT),
        "preparer_sha256": file_sha256(_PREPARER),
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "tail_sentinels_sha256": file_sha256(_TAIL_SENTINELS),
        "workers": arguments.workers,
        "wrapper_sha256": file_sha256(Path(__file__).resolve()),
    }


def verify_replay(arguments: argparse.Namespace) -> dict[str, object]:
    """Run the complete no-write paired producer and evaluator preflight."""
    _require_invocation(arguments)
    if (
        arguments.current_scratch.exists()
        or arguments.incumbent_scratch.exists()
        or arguments.output.exists()
    ):
        raise ValueError("prospective paired write-once state changed")
    _require_candidate_root(
        arguments.current_root,
        revision=None,
        source_tree=_CURRENT_SOURCE_TREE_SHA256,
        label="current candidate",
    )
    _require_candidate_root(
        arguments.incumbent_root,
        revision=_INCUMBENT_REVISION,
        source_tree=_INCUMBENT_SOURCE_TREE_SHA256,
        label="incumbent candidate",
    )
    reference = arguments.reference_reconstruction / "recovery.json"
    if (
        not reference.is_file()
        or file_sha256(reference) != _REFERENCE_RECONSTRUCTION_SHA256
    ):
        raise ValueError("prospective paired reference reconstruction changed")
    static = _verify_static_contracts()
    design = _verify_population_and_power()
    current_tasks = _verify_candidate_tasks(
        arguments,
        mode="current",
        revision=_CURRENT_REVISION,
        source_tree=_CURRENT_SOURCE_TREE_SHA256,
        configuration=_CURRENT_CONFIGURATION_SHA256,
    )
    incumbent_tasks = _verify_candidate_tasks(
        arguments,
        mode="incumbent",
        revision=_INCUMBENT_REVISION,
        source_tree=_INCUMBENT_SOURCE_TREE_SHA256,
        configuration=_INCUMBENT_CONFIGURATION_SHA256,
    )
    evaluator = runpy.run_path(str(_EVALUATOR))
    preparer = runpy.run_path(str(_PREPARER))
    if not callable(evaluator.get("compile_prospective_decision")) or not all(
        callable(preparer.get(name))
        for name in (
            "build_truth_linked_continuum_summary",
            "evaluate_prospective_cumulative_evidence",
            "select_result_neutral_tail_sentinels",
        )
    ):
        raise ValueError("prospective paired evaluator seam changed")
    return {
        **static,
        **design,
        "current_task_count": current_tasks,
        "incumbent_task_count": incumbent_tasks,
        "output_absent": not arguments.output.exists(),
        "scratch_absent": (
            not arguments.current_scratch.exists()
            and not arguments.incumbent_scratch.exists()
        ),
        "reference_run_count": _EXPECTED_REFERENCE_RUN_COUNT,
        "status": "pass",
        "candidate_execution_started": False,
        "expected_execution_sha256": canonical_sha256(
            _expected_execution_fields(arguments)
        ),
    }


def _future_commands(arguments: argparse.Namespace) -> tuple[list[str], ...]:
    """Return the exact sequential producer and atomic evaluator commands."""
    common = [
        sys.executable,
        str(_MATERIALIZER),
        "--tooling-root",
        str(_ROOT),
        "--reference-reconstruction",
        str(arguments.reference_reconstruction),
        "--source-request",
        str(_SOURCE_REQUEST),
        "--population",
        str(_POPULATION),
        "--workers",
        str(arguments.workers),
    ]
    current = [
        *common,
        "--repository-root",
        str(arguments.current_root),
        "--scratch",
        str(arguments.current_scratch),
        "--candidate-mode",
        "current",
        "--candidate-revision",
        _CURRENT_REVISION,
        "--candidate-source-tree-sha256",
        _CURRENT_SOURCE_TREE_SHA256,
        "--candidate-configuration-sha256",
        _CURRENT_CONFIGURATION_SHA256,
    ]
    incumbent = [
        *common,
        "--repository-root",
        str(arguments.incumbent_root),
        "--scratch",
        str(arguments.incumbent_scratch),
        "--candidate-mode",
        "incumbent",
    ]
    evaluator = [
        sys.executable,
        str(_EVALUATOR),
        "--repository-root",
        str(arguments.current_root),
        "--reference-reconstruction",
        str(arguments.reference_reconstruction),
        "--source-request",
        str(_SOURCE_REQUEST),
        "--population",
        str(_POPULATION),
        "--current-scratch",
        str(arguments.current_scratch),
        "--incumbent-scratch",
        str(arguments.incumbent_scratch),
        "--output",
        str(arguments.output),
    ]
    return current, incumbent, evaluator


def _require_execution_authority(arguments: argparse.Namespace) -> None:
    """Require a separate exact decision that does not yet exist."""
    decision = _load_json(_EXECUTION_DECISION, label="execution decision")
    if (
        decision.get("status")
        != "authorized-for-one-prospective-paired-cumulative-replay"
        or decision.get("execution_authorized") is not True
        or decision.get("cumulative_replay_authorized") is not True
        or decision.get("evaluation_authorized") is not True
        or decision.get("expected_execution_sha256")
        != canonical_sha256(_expected_execution_fields(arguments))
        or decision.get("prohibited_authorizations")
        != dict.fromkeys(_PROHIBITED_AUTHORIZATIONS, False)
    ):
        raise ValueError("prospective paired replay is not authorized")


def run_authorized_replay(arguments: argparse.Namespace) -> None:
    """Run the exact pair only after a future checksum-bound decision."""
    verify_replay(arguments)
    _require_execution_authority(arguments)
    for command in _future_commands(arguments):
        subprocess.run(command, cwd=_ROOT, check=True)


def _parse_args() -> argparse.Namespace:
    """Parse the one prospective paired replay invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", required=True, type=Path)
    parser.add_argument("--incumbent-root", required=True, type=Path)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--current-scratch", required=True, type=Path)
    parser.add_argument("--incumbent-scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify without writes or require separate authority before replay."""
    arguments = _parse_args()
    if arguments.verify_only:
        print(json.dumps(verify_replay(arguments), sort_keys=True))
        return
    run_authorized_replay(arguments)


if __name__ == "__main__":
    main()
