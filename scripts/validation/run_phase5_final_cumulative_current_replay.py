#!/usr/bin/env python3
"""Verify or run the final Phase 5 cumulative current-candidate stage."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib
import json
import multiprocessing
import os
import runpy
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_EXECUTION_ROOT = Path(
    "/private/tmp/hebog-phase5-final-cumulative-current-replay"
)
_SCRATCH = Path("/private/tmp/hebog-phase5-final-cumulative-current-0b9e132")
_OUTPUT = Path(
    "benchmark-results/phase-5/final-cumulative-current-product-set.json"
)
_PRE_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-pre-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "execution-decision.json"
)
_MATERIALIZER = Path(
    "scripts/validation/materialize_phase5_prospective_paired_products.py"
)
_SMOKE_EVALUATOR = Path(
    "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
)
_TOPOLOGY_EVALUATOR = Path(
    "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
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
_FAST_TERMINAL = Path(
    "benchmark-results/phase-5/"
    "source-support-linkage-replication-development-decision.json"
)
_INCUMBENT_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "prospective-paired-incumbent-reconstruction.json"
)
_CLOSED_BASELINE = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_CANDIDATE_REVISION = "0b9e13299f3fbbd42af0dea4f70155a802a8441d"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "11307db0059739d473288dd2ed647970cce43b69e874632e1d1f14ee0ed032df"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_PRE_REVIEW_SHA256 = (
    "57365335a4b7b119bb4dec8f0ea857481bf2d8d80f1162e60f555a258276b815"
)
_FAST_TERMINAL_SHA256 = (
    "0978d4a3653ce9bd4b1244ea1125142400607d04c330758ee3b4a495f4193eae"
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
_INCUMBENT_RECONSTRUCTION_SHA256 = (
    "b302967f26ac5947e3c942598a428527cce1d4fa3373ed6eaeb6d204eb8dc040"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_REFERENCE_RUN_COUNT = 9600
_EXPECTED_WORKERS = 2
_PROGRAM_PATHS = {
    "freezer": (
        "scripts/validation/freeze_phase5_final_cumulative_current_replay.py"
    ),
    "materializer": str(_MATERIALIZER),
    "runner": str(
        Path(
            "scripts/validation/run_phase5_final_cumulative_current_replay.py"
        )
    ),
    "smoke_evaluator": str(_SMOKE_EVALUATOR),
    "topology_evaluator": str(_TOPOLOGY_EVALUATOR),
}
_FIXTURE_PATHS = {
    "current_replay": (
        "tests/unit/validation/test_final_cumulative_current_replay.py"
    ),
    "paired_materializer": (
        "tests/unit/validation/test_prospective_paired_cumulative_replay.py"
    ),
    "topology_completion": (
        "tests/unit/validation/"
        "test_prospective_paired_topology_repair_completion.py"
    ),
}
_EXPECTED_AUTHORIZATION = {
    "candidate_execution_authorized": True,
    "cumulative_replay_authorized": True,
    "evaluation_authorized": False,
    "fresh_qualification_authorized": False,
    "pybdsf_execution_authorized": False,
    "release_authorized": False,
    "rescoring_authorized": False,
    "scientific_change_authorized": False,
    "threshold_or_margin_tuning_authorized": False,
    "viewed_data_execution_authorized": False,
}


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, Any], value)


def _materializer_module() -> Any:
    """Import the process-safe prospective paired materializer."""
    return importlib.import_module(
        "scripts.validation.materialize_phase5_prospective_paired_products"
    )


def _materializer_arguments(root: Path, scratch: Path) -> SimpleNamespace:
    """Build the exact current-only product invocation."""
    return SimpleNamespace(
        repository_root=root,
        tooling_root=root,
        reference_reconstruction=root / _REFERENCE_RECONSTRUCTION,
        source_request=root / _SOURCE_REQUEST,
        population=root / _POPULATION,
        scratch=scratch,
        candidate_mode="current",
        candidate_revision=_CANDIDATE_REVISION,
        candidate_source_tree_sha256=_CANDIDATE_SOURCE_TREE_SHA256,
        candidate_configuration_sha256=_CANDIDATE_CONFIGURATION_SHA256,
        workers=_EXPECTED_WORKERS,
    )


def _expected_execution() -> dict[str, object]:
    """Return the exact current-candidate replay shape."""
    return {
        "candidate_executions": _EXPECTED_INPUT_COUNT,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "execution_root": str(_EXECUTION_ROOT),
        "output": str(_OUTPUT),
        "pybdsf_executions": 0,
        "reference_run_count": _EXPECTED_REFERENCE_RUN_COUNT,
        "scratch": str(_SCRATCH),
        "workers": _EXPECTED_WORKERS,
    }


def _process_payload(value: tuple[str, str, str]) -> str:
    """Return a bounded digest through the real spawned module boundary."""
    return canonical_sha256(value)


def _verify_process_payload(value: tuple[str, str, str]) -> str:
    """Exercise one importable spawned-process target without science."""
    if _process_payload(value) != canonical_sha256(value):
        raise ValueError("final cumulative local process seam changed")
    module = importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as executor:
        observed = executor.submit(module._process_payload, value).result()
    if observed != canonical_sha256(value):
        raise ValueError("final cumulative spawned-process seam changed")
    return "spawn-pass"


def _verify_static_evidence(root: Path) -> None:
    """Verify every retained input needed by this and the next stage."""
    expected = (
        (_PRE_REVIEW, _PRE_REVIEW_SHA256, "pre-review"),
        (_FAST_TERMINAL, _FAST_TERMINAL_SHA256, "fast terminal"),
        (
            _REFERENCE_RECONSTRUCTION / "recovery.json",
            _REFERENCE_RECONSTRUCTION_SHA256,
            "reference reconstruction",
        ),
        (_SOURCE_REQUEST, _SOURCE_REQUEST_SHA256, "source request"),
        (_POPULATION, _POPULATION_SHA256, "population"),
        (
            _INCUMBENT_RECONSTRUCTION,
            _INCUMBENT_RECONSTRUCTION_SHA256,
            "incumbent reconstruction",
        ),
        (_CLOSED_BASELINE, _CLOSED_BASELINE_SHA256, "closed baseline"),
    )
    for relative, expected_sha256, label in expected:
        if file_sha256(root / relative) != expected_sha256:
            raise ValueError(f"final cumulative {label} changed")
    terminal = _load_json(root / _FAST_TERMINAL, label="fast terminal")
    if (
        terminal.get("status") != "pass"
        or terminal.get("failed_geometry_count") != 0
        or terminal.get("executor_invariance_passed") is not True
        or terminal.get("trigger_seam_passed") is not True
    ):
        raise ValueError("final cumulative fast gate is not closed")


def _verify_identity(root: Path) -> dict[str, Any]:
    """Verify the frozen candidate, programs, fixtures, and execution."""
    identity = _load_json(root / _IDENTITY, label="identity review")
    if (
        identity.get("status") != "frozen-non-executable"
        or set(cast(dict[str, object], identity["authorization"]).values())
        != {False}
        or identity.get("candidate")
        != {
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        }
        or identity.get("expected_execution") != _expected_execution()
        or identity.get("expected_execution_sha256")
        != canonical_sha256(_expected_execution())
    ):
        raise ValueError("final cumulative identity changed")
    for key, paths in (
        ("program_bindings", _PROGRAM_PATHS),
        ("fixture_bindings", _FIXTURE_PATHS),
    ):
        bindings = cast(dict[str, dict[str, str]], identity.get(key))
        if set(bindings) != set(paths):
            raise ValueError(f"final cumulative {key} set changed")
        for name, relative in paths.items():
            if bindings[name] != {
                "path": relative,
                "sha256": file_sha256(root / relative),
            }:
                raise ValueError(f"final cumulative {key} changed")
    implementation = cast(dict[str, str], identity["implementation"])
    if implementation != {
        "path": str(_IMPLEMENTATION),
        "sha256": file_sha256(root / _IMPLEMENTATION),
    }:
        raise ValueError("final cumulative implementation changed")
    return identity


def verify_no_write(
    *,
    repository_root: Path,
    scratch: Path,
    output: Path,
    enforce_execution_root: bool = True,
    verify_process_pool: bool = False,
) -> dict[str, object]:
    """Verify all 2,400 tasks and 9,600 references without creating data."""
    root = repository_root.resolve()
    if scratch.exists() or output.exists():
        raise FileExistsError("final cumulative namespace must be absent")
    if enforce_execution_root and root != _EXECUTION_ROOT.resolve():
        raise ValueError("final cumulative execution root changed")
    if (
        scratch.resolve() != _SCRATCH.resolve()
        or output.resolve() != (root / _OUTPUT).resolve()
    ):
        raise ValueError("final cumulative execution path changed")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("final cumulative candidate source changed")
    _verify_static_evidence(root)
    identity = _verify_identity(root)
    module = _materializer_module()
    arguments = _materializer_arguments(root, scratch)
    tasks = cast(
        tuple[dict[str, Any], ...], module._candidate_tasks(arguments)
    )
    task_identities = {
        (
            task["candidate_revision"],
            task["source_tree_sha256"],
            task["configuration_sha256"],
        )
        for task in tasks
    }
    if len(tasks) != _EXPECTED_INPUT_COUNT or task_identities != {
        (
            _CANDIDATE_REVISION,
            _CANDIDATE_SOURCE_TREE_SHA256,
            _CANDIDATE_CONFIGURATION_SHA256,
        )
    }:
        raise ValueError("final cumulative task identity changed")
    materializer = module._load_materializer(root)
    verified, _ = materializer["_verified_reference"](
        root, root / _REFERENCE_RECONSTRUCTION
    )
    if len(verified.runs) != _EXPECTED_REFERENCE_RUN_COUNT:
        raise ValueError("final cumulative reference population changed")
    process_status = "not-requested"
    if verify_process_pool:
        process_status = _verify_process_payload(next(iter(task_identities)))
    return {
        "candidate_execution_started": False,
        "candidate_task_count": len(tasks),
        "expected_execution_sha256": identity["expected_execution_sha256"],
        "identity_review_sha256": file_sha256(root / _IDENTITY),
        "process_payload_status": process_status,
        "reference_run_count": len(verified.runs),
        "status": "pass",
    }


def _require_authority(root: Path) -> None:
    """Require the exact one-use current-candidate execution decision."""
    decision = _load_json(
        root / _EXECUTION_DECISION, label="execution decision"
    )
    if (
        decision.get("status")
        != "authorized-for-one-final-cumulative-current-replay"
        or decision.get("authorization") != _EXPECTED_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != file_sha256(root / _IDENTITY)
        or decision.get("expected_execution_sha256")
        != canonical_sha256(_expected_execution())
    ):
        raise PermissionError("final cumulative replay authority changed")


def _materializer_command(root: Path) -> list[str]:
    """Return the exact proven current-only producer command."""
    return [
        sys.executable,
        str(root / _MATERIALIZER),
        "--repository-root",
        str(root),
        "--tooling-root",
        str(root),
        "--reference-reconstruction",
        str(root / _REFERENCE_RECONSTRUCTION),
        "--source-request",
        str(root / _SOURCE_REQUEST),
        "--population",
        str(root / _POPULATION),
        "--scratch",
        str(_SCRATCH),
        "--candidate-mode",
        "current",
        "--candidate-revision",
        _CANDIDATE_REVISION,
        "--candidate-source-tree-sha256",
        _CANDIDATE_SOURCE_TREE_SHA256,
        "--candidate-configuration-sha256",
        _CANDIDATE_CONFIGURATION_SHA256,
        "--workers",
        str(_EXPECTED_WORKERS),
    ]


def _product_set_sha256(root: Path) -> str:
    """Verify and seal all current products through the proven reader."""
    module = _materializer_module()
    materializer = module._load_materializer(root)
    identifiers = materializer["_selected_inputs"](
        root / _SOURCE_REQUEST, root / _POPULATION
    )
    smoke = runpy.run_path(str(root / _SMOKE_EVALUATOR))
    return cast(
        str,
        smoke["_verify_product_set"](
            identifiers,
            _SCRATCH,
            configuration=_CANDIDATE_CONFIGURATION_SHA256,
            source_tree=_CANDIDATE_SOURCE_TREE_SHA256,
        ),
    )


def _publish(path: Path, record: dict[str, object]) -> None:
    """Atomically publish one finite write-once product-set seal."""
    payload = (
        json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_authorized_replay(*, repository_root: Path, output: Path) -> None:
    """Materialize once, verify every product, and atomically seal the set."""
    root = repository_root.resolve()
    verify_no_write(
        repository_root=root,
        scratch=_SCRATCH,
        output=output,
        verify_process_pool=True,
    )
    _require_authority(root)
    subprocess.run(_materializer_command(root), cwd=root, check=True)
    product_set = _product_set_sha256(root)
    record: dict[str, object] = {
        "candidate_configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "candidate_execution_count": _EXPECTED_INPUT_COUNT,
        "candidate_product_set_sha256": product_set,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "execution_decision_sha256": file_sha256(root / _EXECUTION_DECISION),
        "identity_review_sha256": file_sha256(root / _IDENTITY),
        "output_identity": str(_OUTPUT),
        "pybdsf_execution_count": 0,
        "reference_run_count": _EXPECTED_REFERENCE_RUN_COUNT,
        "schema_version": 1,
        "status": "complete",
    }
    record["record_canonical_sha256"] = canonical_sha256(record)
    _publish(output, record)
    print(output)
    print(f"candidate_product_set_sha256={product_set}")


def _parse_args() -> argparse.Namespace:
    """Parse the exact current-only replay invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", required=True, type=int)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify without writes or consume the exact one-use authority."""
    arguments = _parse_args()
    if (
        arguments.workers != _EXPECTED_WORKERS
        or arguments.scratch.resolve() != _SCRATCH
    ):
        raise ValueError("final cumulative execution shape changed")
    if arguments.verify_only:
        print(
            json.dumps(
                verify_no_write(
                    repository_root=arguments.repository_root,
                    scratch=arguments.scratch,
                    output=arguments.output,
                    verify_process_pool=True,
                ),
                sort_keys=True,
            )
        )
        return
    run_authorized_replay(
        repository_root=arguments.repository_root,
        output=arguments.output,
    )


if __name__ == "__main__":
    main()
