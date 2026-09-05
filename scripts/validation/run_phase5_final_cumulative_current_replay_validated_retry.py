#!/usr/bin/env python3
"""Verify or run the validated final cumulative current-candidate stage."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib
import json
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_BASE_RUNNER = Path(
    "scripts/validation/run_phase5_final_cumulative_current_replay.py"
)
_PROCESS_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "preflight-efficiency-review-canonical.json"
)
_TYPE_CLEAN_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "type-clean-review-canonical.json"
)
_SINGLE_SCAN_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "single-scan-execution-review-canonical.json"
)
_JSON_FORMAT_REVIEW = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "json-format-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "validated-retry-type-clean-single-scan-canonical-"
    "implementation-decision.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "validated-retry-type-clean-single-scan-canonical-identity-review.json"
)
_EXECUTION_DECISION = Path(
    "config/contracts/phase-5-final-cumulative-current-replay-"
    "validated-retry-type-clean-single-scan-canonical-"
    "execution-decision.json"
)
_PROCESS_REVIEW_SHA256 = (
    "f67d74c05af40ff509562583bc7dca51fbb2d7dbc29bff581a03f20f4cf2ab39"
)
_TYPE_CLEAN_REVIEW_SHA256 = (
    "853fe3982fc6e098ab2a3b1e986a9853b0ebac57cbcee6a7f174033d119c62b1"
)
_SINGLE_SCAN_REVIEW_SHA256 = (
    "8d4848d265aaf07bb858856d05c984dc8a33b128b0f6d3e67d73f9b322c5dffa"
)
_JSON_FORMAT_REVIEW_SHA256 = (
    "ab96bacf3625aa5942a51080affeb7ea3d31687aaaff5a4dbcf74e2fe20decc6"
)
_SUPERSEDED_IDENTITY_SHA256 = (
    "4402239b2c2adc302c2c1a31fa4489eb7c2aca6cc072724e7630376a796285b0"
)
_SUPERSEDED_DECISION_SHA256 = (
    "3eee3b49165dc0df6c1aa81af80a03a34e05775a0178479ec789efe259881db3"
)
_PROGRAM_PATHS = {
    "base_runner": str(_BASE_RUNNER),
    "freezer": (
        "scripts/validation/"
        "freeze_phase5_final_cumulative_current_replay_validated_retry.py"
    ),
    "materializer": (
        "scripts/validation/materialize_phase5_prospective_paired_products.py"
    ),
    "runner": (
        "scripts/validation/"
        "run_phase5_final_cumulative_current_replay_validated_retry.py"
    ),
    "smoke_evaluator": (
        "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
    ),
    "topology_evaluator": (
        "scripts/validation/"
        "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
    ),
}
_FIXTURE_PATHS = {
    "current_replay": (
        "tests/unit/validation/"
        "test_final_cumulative_current_replay_validated_retry.py"
    ),
    "paired_materializer": (
        "tests/unit/validation/test_prospective_paired_cumulative_replay.py"
    ),
    "topology_completion": (
        "tests/unit/validation/"
        "test_prospective_paired_topology_repair_completion.py"
    ),
}


def _base() -> Any:
    """Load the frozen predecessor as a reusable execution composition."""
    return importlib.import_module(
        "scripts.validation.run_phase5_final_cumulative_current_replay"
    )


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, Any], value)


def _process_payload(value: tuple[str, str, str]) -> str:
    """Return a bounded digest through the real spawned module boundary."""
    return canonical_sha256(value)


def _verify_process_payload(value: tuple[str, str, str]) -> str:
    """Exercise one importable spawned-process target without science."""
    if _process_payload(value) != canonical_sha256(value):
        raise ValueError("validated cumulative local process seam changed")
    module = importlib.import_module(
        "scripts.validation."
        "run_phase5_final_cumulative_current_replay_validated_retry"
    )
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as executor:
        observed = executor.submit(module._process_payload, value).result()
    if observed != canonical_sha256(value):
        raise ValueError("validated cumulative spawned-process seam changed")
    return "spawn-pass"


def _verify_process_review(root: Path) -> None:
    """Require the exact no-science predecessor supersession record."""
    if file_sha256(root / _PROCESS_REVIEW) != _PROCESS_REVIEW_SHA256:
        raise ValueError("validated cumulative process review changed")
    review = _load_json(root / _PROCESS_REVIEW, label="process review")
    superseded = cast(
        dict[str, str], review.get("superseded_unexecuted_records")
    )
    if (
        review.get("status")
        != "approved-process-only-preflight-efficiency-repair"
        or cast(dict[str, object], review["diagnosis"]).get(
            "candidate_execution_started"
        )
        is not False
        or superseded.get("identity_review_sha256")
        != _SUPERSEDED_IDENTITY_SHA256
        or superseded.get("execution_decision_sha256")
        != _SUPERSEDED_DECISION_SHA256
    ):
        raise ValueError("validated cumulative process review is not closed")
    if file_sha256(root / _TYPE_CLEAN_REVIEW) != _TYPE_CLEAN_REVIEW_SHA256:
        raise ValueError("validated cumulative type-clean review changed")
    type_review = _load_json(
        root / _TYPE_CLEAN_REVIEW, label="type-clean review"
    )
    if (
        type_review.get("status")
        != "approved-process-only-fixture-type-repair"
        or cast(dict[str, object], type_review["diagnosis"]).get(
            "candidate_execution_started"
        )
        is not False
    ):
        raise ValueError(
            "validated cumulative type-clean review is not closed"
        )
    if file_sha256(root / _SINGLE_SCAN_REVIEW) != _SINGLE_SCAN_REVIEW_SHA256:
        raise ValueError("validated cumulative single-scan review changed")
    scan_review = _load_json(
        root / _SINGLE_SCAN_REVIEW, label="single-scan review"
    )
    if (
        scan_review.get("status")
        != "approved-process-only-single-scan-execution-repair"
        or cast(dict[str, object], scan_review["diagnosis"]).get(
            "candidate_execution_started"
        )
        is not False
    ):
        raise ValueError(
            "validated cumulative single-scan review is not closed"
        )
    if file_sha256(root / _JSON_FORMAT_REVIEW) != _JSON_FORMAT_REVIEW_SHA256:
        raise ValueError("validated cumulative JSON-format review changed")
    format_review = _load_json(
        root / _JSON_FORMAT_REVIEW, label="JSON-format review"
    )
    if (
        format_review.get("status")
        != "approved-provenance-only-json-format-rebinding"
        or cast(dict[str, object], format_review["diagnosis"]).get(
            "candidate_execution_started"
        )
        is not False
    ):
        raise ValueError(
            "validated cumulative JSON-format review is not closed"
        )


def _verify_identity(root: Path) -> dict[str, Any]:
    """Verify the successor candidate, programs, fixtures, and execution."""
    base = _base()
    identity = _load_json(root / _IDENTITY, label="identity review")
    if (
        identity.get("status") != "frozen-non-executable"
        or set(cast(dict[str, object], identity["authorization"]).values())
        != {False}
        or identity.get("candidate")
        != {
            "configuration_sha256": base._CANDIDATE_CONFIGURATION_SHA256,
            "revision": base._CANDIDATE_REVISION,
            "source_tree_sha256": base._CANDIDATE_SOURCE_TREE_SHA256,
        }
        or identity.get("expected_execution") != base._expected_execution()
        or identity.get("expected_execution_sha256")
        != canonical_sha256(base._expected_execution())
        or identity.get("process_review")
        != {
            "path": str(_PROCESS_REVIEW),
            "sha256": _PROCESS_REVIEW_SHA256,
        }
        or identity.get("type_clean_review")
        != {
            "path": str(_TYPE_CLEAN_REVIEW),
            "sha256": _TYPE_CLEAN_REVIEW_SHA256,
        }
        or identity.get("single_scan_review")
        != {
            "path": str(_SINGLE_SCAN_REVIEW),
            "sha256": _SINGLE_SCAN_REVIEW_SHA256,
        }
        or identity.get("json_format_review")
        != {
            "path": str(_JSON_FORMAT_REVIEW),
            "sha256": _JSON_FORMAT_REVIEW_SHA256,
        }
    ):
        raise ValueError("validated cumulative identity changed")
    for key, paths in (
        ("program_bindings", _PROGRAM_PATHS),
        ("fixture_bindings", _FIXTURE_PATHS),
    ):
        bindings = cast(dict[str, dict[str, str]], identity.get(key))
        if set(bindings) != set(paths):
            raise ValueError(f"validated cumulative {key} set changed")
        for name, relative in paths.items():
            if bindings[name] != {
                "path": relative,
                "sha256": file_sha256(root / relative),
            }:
                raise ValueError(f"validated cumulative {key} changed")
    implementation = cast(dict[str, str], identity["implementation"])
    if implementation != {
        "path": str(_IMPLEMENTATION),
        "sha256": file_sha256(root / _IMPLEMENTATION),
    }:
        raise ValueError("validated cumulative implementation changed")
    return identity


def _verified_candidate_tasks(
    root: Path, scratch: Path
) -> tuple[dict[str, Any], ...]:
    """Build tasks through the one complete retained-reference verifier."""
    base = _base()
    module = base._materializer_module()
    arguments = base._materializer_arguments(root, scratch)
    return cast(tuple[dict[str, Any], ...], module._candidate_tasks(arguments))


def _verified_plan(
    *,
    repository_root: Path,
    scratch: Path,
    output: Path,
    enforce_execution_root: bool = True,
    verify_process_pool: bool = False,
) -> tuple[dict[str, object], tuple[dict[str, Any], ...]]:
    """Verify all tasks and references once and return the bound plan."""
    base = _base()
    root = repository_root.resolve()
    if scratch.exists() or output.exists():
        raise FileExistsError("validated cumulative namespace must be absent")
    if enforce_execution_root and root != base._EXECUTION_ROOT.resolve():
        raise ValueError("validated cumulative execution root changed")
    if (
        scratch.resolve() != base._SCRATCH.resolve()
        or output.resolve() != (root / base._OUTPUT).resolve()
    ):
        raise ValueError("validated cumulative execution path changed")
    if source_tree_sha256(root) != base._CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("validated cumulative candidate source changed")
    base._verify_static_evidence(root)
    _verify_process_review(root)
    identity = _verify_identity(root)
    tasks = _verified_candidate_tasks(root, scratch)
    task_identities = {
        (
            task["candidate_revision"],
            task["source_tree_sha256"],
            task["configuration_sha256"],
        )
        for task in tasks
    }
    expected_identity = (
        base._CANDIDATE_REVISION,
        base._CANDIDATE_SOURCE_TREE_SHA256,
        base._CANDIDATE_CONFIGURATION_SHA256,
    )
    if len(tasks) != base._EXPECTED_INPUT_COUNT or task_identities != {
        expected_identity
    }:
        raise ValueError("validated cumulative task identity changed")
    process_status = "not-requested"
    if verify_process_pool:
        process_status = _verify_process_payload(expected_identity)
    verification: dict[str, object] = {
        "candidate_execution_started": False,
        "candidate_task_count": len(tasks),
        "expected_execution_sha256": identity["expected_execution_sha256"],
        "identity_review_sha256": file_sha256(root / _IDENTITY),
        "process_payload_status": process_status,
        "reference_run_count": base._EXPECTED_REFERENCE_RUN_COUNT,
        "reference_verification_count": 1,
        "status": "pass",
    }
    return verification, tasks


def verify_no_write(
    *,
    repository_root: Path,
    scratch: Path,
    output: Path,
    enforce_execution_root: bool = True,
    verify_process_pool: bool = False,
) -> dict[str, object]:
    """Verify all tasks and references once without creating products."""
    verification, _ = _verified_plan(
        repository_root=repository_root,
        scratch=scratch,
        output=output,
        enforce_execution_root=enforce_execution_root,
        verify_process_pool=verify_process_pool,
    )
    return verification


def _require_authority(root: Path) -> None:
    """Require the exact one-use validated execution decision."""
    base = _base()
    decision = _load_json(
        root / _EXECUTION_DECISION, label="execution decision"
    )
    if (
        decision.get("status")
        != "authorized-for-one-final-cumulative-current-replay"
        or decision.get("authorization") != base._EXPECTED_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != file_sha256(root / _IDENTITY)
        or decision.get("expected_execution_sha256")
        != canonical_sha256(base._expected_execution())
        or decision.get("process_review_sha256") != _PROCESS_REVIEW_SHA256
        or decision.get("type_clean_review_sha256")
        != _TYPE_CLEAN_REVIEW_SHA256
        or decision.get("single_scan_review_sha256")
        != _SINGLE_SCAN_REVIEW_SHA256
        or decision.get("json_format_review_sha256")
        != _JSON_FORMAT_REVIEW_SHA256
    ):
        raise PermissionError("validated cumulative replay authority changed")


def _materialize_verified_tasks(
    tasks: tuple[dict[str, Any], ...], scratch: Path, *, workers: int
) -> None:
    """Run one already-verified task plan through the proven process target."""
    base = _base()
    module = base._materializer_module()
    scratch.mkdir(parents=True, exist_ok=False)
    progress_path = scratch / "progress.log"
    with (
        progress_path.open("x", encoding="utf-8") as progress,
        ProcessPoolExecutor(max_workers=workers) as executor,
    ):
        futures = {
            executor.submit(module._generate_product, task) for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            input_id = future.result()
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{len(tasks)} input={input_id}\n"
            )
            progress.flush()


def run_authorized_replay(*, repository_root: Path, output: Path) -> None:
    """Materialize once, verify every product, and seal the product set."""
    base = _base()
    root = repository_root.resolve()
    _, tasks = _verified_plan(
        repository_root=root,
        scratch=base._SCRATCH,
        output=output,
        verify_process_pool=True,
    )
    _require_authority(root)
    _materialize_verified_tasks(
        tasks, base._SCRATCH, workers=base._EXPECTED_WORKERS
    )
    product_set = base._product_set_sha256(root)
    record: dict[str, object] = {
        "candidate_configuration_sha256": (
            base._CANDIDATE_CONFIGURATION_SHA256
        ),
        "candidate_execution_count": base._EXPECTED_INPUT_COUNT,
        "candidate_product_set_sha256": product_set,
        "candidate_revision": base._CANDIDATE_REVISION,
        "candidate_source_tree_sha256": base._CANDIDATE_SOURCE_TREE_SHA256,
        "execution_decision_sha256": file_sha256(root / _EXECUTION_DECISION),
        "identity_review_sha256": file_sha256(root / _IDENTITY),
        "json_format_review_sha256": _JSON_FORMAT_REVIEW_SHA256,
        "output_identity": str(base._OUTPUT),
        "process_review_sha256": _PROCESS_REVIEW_SHA256,
        "single_scan_review_sha256": _SINGLE_SCAN_REVIEW_SHA256,
        "type_clean_review_sha256": _TYPE_CLEAN_REVIEW_SHA256,
        "pybdsf_execution_count": 0,
        "reference_run_count": base._EXPECTED_REFERENCE_RUN_COUNT,
        "schema_version": 1,
        "status": "complete",
    }
    record["record_canonical_sha256"] = canonical_sha256(record)
    base._publish(output, record)
    print(output)
    print(f"candidate_product_set_sha256={product_set}")


def _parse_args() -> argparse.Namespace:
    """Parse the exact validated current-only invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", required=True, type=int)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify without writes or consume the exact one-use authority."""
    base = _base()
    arguments = _parse_args()
    if (
        arguments.workers != base._EXPECTED_WORKERS
        or arguments.scratch.resolve() != base._SCRATCH
    ):
        raise ValueError("validated cumulative execution shape changed")
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
