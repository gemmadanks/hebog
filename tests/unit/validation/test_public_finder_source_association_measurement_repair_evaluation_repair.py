"""Contracts for completing the preserved measurement-repair replay."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import FunctionType
from typing import Any, cast

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_SCRIPT = (
    _ROOT / "scripts/validation/complete_phase5_public_finder_source_"
    "association_measurement_repair_evaluation.py"
)
_FAILURE = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-cumulative-replay-execution-failure.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-evaluation-repair-pre-review.json"
)
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-evaluation-repair-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-evaluation-repair-execution-decision.json"
)


def _namespace() -> dict[str, Any]:
    return runpy.run_path(str(_SCRIPT))


def _write_product(
    namespace: dict[str, Any],
    root: Path,
    *,
    input_id: str,
    lane: str,
) -> None:
    directory = root / "products" / input_id
    directory.mkdir(parents=True)
    roles = (
        (
            "segment-catalogue-json",
            "segment-labels-fits",
            "segment-mask-fits",
        )
        if lane == "continuum"
        else ("compact-catalogue-json",)
    )
    artifacts: list[dict[str, object]] = []
    for index, role in enumerate(roles):
        path = directory / f"artifact-{index}.bin"
        path.write_bytes(f"{input_id}-{role}".encode())
        artifacts.append(
            {
                "role": role,
                "relative_path": path.name,
                "byte_count": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    marker = {
        "schema_version": 1,
        "input_id": input_id,
        "configuration_sha256": namespace["_CANDIDATE_CONFIGURATION_SHA256"],
        "source_tree_sha256": namespace["_CANDIDATE_SOURCE_TREE_SHA256"],
        "artifacts": artifacts,
    }
    (directory / "complete.json").write_bytes(
        namespace["_canonical_json_bytes"](marker)
    )


def _scratch(
    namespace: dict[str, Any],
    path: Path,
) -> tuple[tuple[str, str], ...]:
    expected = (("continuum-1", "continuum"), ("compact-1", "compact"))
    for input_id, lane in expected:
        _write_product(
            namespace,
            path,
            input_id=input_id,
            lane=lane,
        )
    (path / "progress.log").write_text(
        "2026-08-28T00:00:00+00:00 completed=1/2 input=continuum-1\n"
        "2026-08-28T00:00:01+00:00 completed=2/2 input=compact-1\n",
        encoding="utf-8",
    )
    return expected


def test_existing_products_are_verified_without_science_access(
    tmp_path: Path,
) -> None:
    """Admit only canonical markers and exact artifact bytes."""
    namespace = _namespace()
    expected = _scratch(namespace, tmp_path)

    first = namespace["verify_existing_candidate_products"](
        tmp_path,
        expected,
        expected_count=2,
    )
    second = namespace["verify_existing_candidate_products"](
        tmp_path,
        tuple(reversed(expected)),
        expected_count=2,
    )

    assert first != second
    assert len(first) == 64


def test_existing_product_verification_rejects_artifact_drift(
    tmp_path: Path,
) -> None:
    """A changed byte prevents reuse of the preserved candidate shard."""
    namespace = _namespace()
    expected = _scratch(namespace, tmp_path)
    artifact = tmp_path / "products/continuum-1/artifact-0.bin"
    artifact.write_bytes(b"changed")

    with pytest.raises(ValueError, match="artifact identity changed"):
        namespace["verify_existing_candidate_products"](
            tmp_path,
            expected,
            expected_count=2,
        )


def test_completion_seam_forbids_candidate_submission(tmp_path: Path) -> None:
    """Compilation completion can verify shards but cannot generate one."""
    namespace = _namespace()

    def completed_candidate(*_args: object, **_kwargs: object) -> bool:
        return True

    frozen: dict[str, Any] = {
        "_completed_candidate": completed_candidate,
        "_canonical_json_bytes": namespace["_canonical_json_bytes"],
    }
    namespace["_install_completion_only"](
        frozen,
        provenance={"repair": "fixture"},
        expected_count=2,
        scratch=tmp_path,
    )
    tasks = (
        {
            "input_id": "one",
            "output_directory": str(tmp_path / "products/one"),
            "configuration_sha256": namespace[
                "_CANDIDATE_CONFIGURATION_SHA256"
            ],
            "source_tree_sha256": namespace["_CANDIDATE_SOURCE_TREE_SHA256"],
        },
        {
            "input_id": "two",
            "output_directory": str(tmp_path / "products/two"),
            "configuration_sha256": namespace[
                "_CANDIDATE_CONFIGURATION_SHA256"
            ],
            "source_tree_sha256": namespace["_CANDIDATE_SOURCE_TREE_SHA256"],
        },
    )

    frozen["_run_candidate_tasks"](
        tasks,
        workers=2,
        progress_path=tmp_path / "progress.log",
    )
    with pytest.raises(RuntimeError, match="forbids candidate execution"):
        frozen["_generate_candidate_product"](tasks[0])
    ledger = json.loads(
        frozen["_canonical_json_bytes"](
            {"ledger_id": "phase-5-cumulative-regression-ledger"}
        )
    )
    assert ledger["evaluation_repair_provenance"] == {"repair": "fixture"}


def test_compiler_repair_layers_after_the_frozen_recovery_seams() -> None:
    """The new interpretation is installed only after the closed compiler."""
    namespace = _namespace()
    calls: list[str] = []

    def original(
        compiler: dict[str, Any],
        *,
        expected_candidate_configuration_sha256: str,
    ) -> None:
        def candidate_objects() -> tuple[object, ...]:
            return ()

        def measure_image() -> dict[object, object]:
            return {}

        calls.append(expected_candidate_configuration_sha256)
        compiler["_candidate_objects"] = candidate_objects
        compiler["measure_continuum_image"] = measure_image

    def prospective() -> None:
        return None

    installer_globals: dict[str, Any] = {
        "install_recovery_compiler_seams": original,
    }
    prospective_view = FunctionType(
        prospective.__code__,
        installer_globals,
    )
    frozen = {"_install_prospective_compiler": prospective_view}

    namespace["_install_evaluation_compiler_repair"](frozen)
    compiler: dict[str, Any] = {}
    installer_globals["install_recovery_compiler_seams"](
        compiler,
        expected_candidate_configuration_sha256="configuration",
    )

    assert calls == ["configuration"]
    assert compiler["_candidate_objects"].__module__ == (
        "hebog.validation.source_association_evaluation_repair"
    )
    assert compiler["measure_continuum_image"].__module__ == (
        "hebog.validation.source_association_evaluation_repair"
    )


def test_repair_contract_preserves_consumed_authorization_boundary() -> None:
    """Implementation does not transfer the failed replay authority."""
    failure = json.loads(_FAILURE.read_text(encoding="utf-8"))
    pre_review = json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))

    assert failure["observed_execution"]["candidate_product_count"] == 2400
    assert failure["observed_execution"]["atomic_ledger_state"] == "absent"
    assert failure["transfer_policy"] == {
        "original_replay_authorization_consumed": True,
        "original_execution_decision_reusable": False,
        "existing_candidate_products_reusable_after_exact_verification": True,
        "new_evaluation_adapter_requires_new_identity": True,
    }
    authority = pre_review["authorization_boundary"]
    assert authority["implementation_authorized"] is True
    assert (
        authority["existing_scratch_no_write_verification_authorized"] is True
    )
    assert authority["candidate_execution_authorized"] is False
    assert authority["compilation_authorized"] is False
    assert authority["evaluation_authorized"] is False
    assert authority["cumulative_replay_rerun_authorized"] is False


def test_identity_review_freezes_only_non_executable_completion() -> None:
    """The verified product set is bound without transferring authority."""
    review: dict[str, Any] = json.loads(_REVIEW.read_text(encoding="utf-8"))

    assert review["status"] == (
        "reviewed-before-measurement-repair-evaluation-completion"
    )
    assert review["implementation"]["commit"] == (
        "ea3279d6cea50af26d5e5c25aa7904a238718456"
    )
    implementation: dict[str, Any] = review["implementation"]
    assert isinstance(implementation, dict)
    for identity in implementation.values():
        if not isinstance(identity, dict):
            continue
        identity_record = cast(dict[str, Any], identity)
        path = identity_record.get("path")
        sha256 = identity_record.get("sha256")
        if not isinstance(path, str):
            continue
        assert isinstance(sha256, str)
        assert file_sha256(_ROOT / path) == sha256
    verified = review["verified_composition"]
    assert verified["candidate_product_count"] == 2400
    assert verified["candidate_product_set_sha256"] == (
        "dbc317fa98638d96ebecac26d98014a953defc96ed48a741f42f48954daa48ab"
    )
    assert verified["reference_run_count"] == 9600
    assert verified["output_absent"] is True
    assert verified["candidate_execution_started"] is False
    assert verified["compilation_started"] is False
    assert verified["evaluation_started"] is False
    assert review["candidate_execution_authorized"] is False
    assert review["compilation_resume_authorized"] is False
    assert review["evaluation_authorized"] is False
    assert not any(review["prohibited_authorizations"].values())


def test_execution_decision_authorizes_only_existing_product_completion() -> (
    None
):
    """The named approval opens compilation and evaluation, not execution."""
    review: dict[str, Any] = json.loads(_REVIEW.read_text(encoding="utf-8"))
    decision: dict[str, Any] = json.loads(
        _EXECUTION_DECISION.read_text(encoding="utf-8")
    )

    assert decision["status"] == review["status"]
    assert decision["identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    verified = review["verified_composition"]
    for field in (
        "candidate_product_set_sha256",
        "completion_program_sha256",
        "source_association_program_sha256",
        "historical_support_matcher_sha256",
        "historical_successor_compiler_sha256",
        "evaluation_repair_adapter_sha256",
    ):
        assert decision[field] == verified[field]
    assert decision["existing_product_completion_authorized"] is True
    assert decision["compilation_resume_authorized"] is True
    assert decision["evaluation_authorized"] is True
    assert decision["candidate_execution_authorized"] is False
    assert not any(decision["prohibited_authorizations"].values())
