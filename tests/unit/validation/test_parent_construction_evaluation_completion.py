# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
"""Contracts for parent-construction existing-product evaluation."""

from __future__ import annotations

import json
import runpy
from dataclasses import asdict
from pathlib import Path
from types import FunctionType, SimpleNamespace
from typing import Any

import pytest

from hebog.data_models.source_association import SourceAssociationResult
from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.external_recovery_compiler import (
    RecoveryContinuumImageCompiler,
)
from hebog.validation.external_runners import file_sha256
from hebog.validation.parent_construction_association_evaluation import (
    ParentConstructionContinuumImageCompiler,
)

_ROOT = Path(__file__).parents[3]
_SCRIPT = (
    _ROOT / "scripts/validation/complete_phase5_parent_construction_"
    "evaluation.py"
)


def _namespace() -> dict[str, Any]:
    """Load the completion wrapper without running its entry point."""
    return runpy.run_path(str(_SCRIPT))


def _write_association_terminal(
    namespace: dict[str, Any],
    root: Path,
    scratch: Path,
    input_ids: tuple[str, ...],
) -> None:
    """Write one small exact terminal fixture and bind its identities."""
    namespace = namespace["_verify_association_reconstruction"].__globals__
    associations = root / "associations"
    associations.mkdir(parents=True)
    markers: list[dict[str, object]] = []
    association = asdict(
        SourceAssociationResult(components=(), edges=(), memberships=())
    )
    for input_id in input_ids:
        preserved = scratch / "products" / input_id / "complete.json"
        preserved.parent.mkdir(parents=True)
        preserved.write_bytes(input_id.encode())
        directory = associations / input_id
        directory.mkdir()
        association_path = directory / "source_association.json"
        association_path.write_bytes(
            namespace["_canonical_json_bytes"](association)
        )
        marker: dict[str, object] = {
            "candidate_configuration_sha256": namespace[
                "_CANDIDATE_CONFIGURATION_SHA256"
            ],
            "candidate_revision": namespace["_CANDIDATE_REVISION"],
            "candidate_source_tree_sha256": namespace[
                "_CANDIDATE_SOURCE_TREE_SHA256"
            ],
            "input_id": input_id,
            "preserved_complete_sha256": file_sha256(preserved),
            "reconstruction_program_sha256": namespace[
                "_RECONSTRUCTION_PROGRAM_SHA256"
            ],
            "schema_version": 1,
            "source_association_sha256": file_sha256(association_path),
        }
        (directory / "complete.json").write_bytes(
            namespace["_canonical_json_bytes"](marker)
        )
        markers.append(marker)
    association_product_set = canonical_sha256(markers)
    namespace["_ASSOCIATION_PRODUCT_SET_SHA256"] = association_product_set
    recovery = {
        "association_count": len(input_ids),
        "association_product_set_sha256": association_product_set,
        "candidate_configuration_sha256": namespace[
            "_CANDIDATE_CONFIGURATION_SHA256"
        ],
        "candidate_product_set_sha256": namespace[
            "_CANDIDATE_PRODUCT_SET_SHA256"
        ],
        "candidate_revision": namespace["_CANDIDATE_REVISION"],
        "candidate_source_tree_sha256": namespace[
            "_CANDIDATE_SOURCE_TREE_SHA256"
        ],
        "closed_baseline_sha256": namespace["_CLOSED_BASELINE_SHA256"],
        "decision_sha256": namespace["_RECONSTRUCTION_DECISION_SHA256"],
        "failure_sha256": namespace["_FAILURE_SHA256"],
        "implementation_decision_sha256": namespace[
            "_REPAIR_IMPLEMENTATION_DECISION_SHA256"
        ],
        "parent_wrapper_sha256": namespace["_PARENT_WRAPPER_SHA256"],
        "pre_review_sha256": namespace["_REPAIR_PRE_REVIEW_SHA256"],
        "reference_reconstruction_sha256": namespace[
            "_REFERENCE_RECONSTRUCTION_SHA256"
        ],
        "reconstruction_program_sha256": namespace[
            "_RECONSTRUCTION_PROGRAM_SHA256"
        ],
        "schema_version": 1,
        "status": "sealed",
    }
    recovery_path = root / "recovery.json"
    recovery_path.write_bytes(namespace["_canonical_json_bytes"](recovery))
    namespace["_RECONSTRUCTION_RECOVERY_SHA256"] = file_sha256(recovery_path)
    (root / "progress.log").write_text(
        "".join(f"{input_id}\n" for input_id in input_ids),
        encoding="utf-8",
    )


def test_sealed_association_terminal_is_verified_without_science(
    tmp_path: Path,
) -> None:
    """Every sidecar remains bound to its preserved complete marker."""
    namespace = _namespace()
    terminal = tmp_path / "terminal"
    scratch = tmp_path / "scratch"
    input_ids = ("continuum-1", "continuum-2")
    _write_association_terminal(namespace, terminal, scratch, input_ids)

    identity = namespace["_verify_association_reconstruction"](
        terminal,
        input_ids,
        scratch=scratch,
        expected_count=2,
    )

    verifier_globals = namespace[
        "_verify_association_reconstruction"
    ].__globals__
    assert identity == verifier_globals["_ASSOCIATION_PRODUCT_SET_SHA256"]
    sidecar = terminal / "associations/continuum-1/source_association.json"
    sidecar.write_bytes(b"changed")
    with pytest.raises(ValueError, match="shard changed"):
        namespace["_verify_association_reconstruction"](
            terminal,
            input_ids,
            scratch=scratch,
            expected_count=2,
        )


def test_completion_seam_forbids_candidate_execution(tmp_path: Path) -> None:
    """Existing-product evaluation verifies tasks but cannot generate one."""
    namespace = _namespace()
    frozen: dict[str, Any] = {
        "_completed_candidate": lambda *_args, **_kwargs: True,
        "_canonical_json_bytes": namespace["_canonical_json_bytes"],
    }
    namespace["_install_completion_only"](
        frozen,
        provenance={"completion": "fixture"},
        expected_count=1,
        scratch=tmp_path,
    )
    task = {
        "input_id": "one",
        "output_directory": str(tmp_path / "products/one"),
        "configuration_sha256": namespace["_CANDIDATE_CONFIGURATION_SHA256"],
        "source_tree_sha256": namespace["_CANDIDATE_SOURCE_TREE_SHA256"],
    }

    frozen["_run_candidate_tasks"](
        (task,), workers=2, progress_path=tmp_path / "progress.log"
    )
    with pytest.raises(RuntimeError, match="forbids candidate execution"):
        frozen["_generate_candidate_product"](task)
    ledger = json.loads(
        frozen["_canonical_json_bytes"](
            {"ledger_id": "phase-5-cumulative-regression-ledger"}
        )
    )
    assert ledger["evaluation_completion_provenance"] == {
        "completion": "fixture"
    }


def test_sidecar_compiler_layers_after_frozen_recovery_seams() -> None:
    """Only the Continuum compiler is replaced after historical setup."""
    namespace = _namespace()
    calls: list[str] = []

    def original(
        compiler: dict[str, Any],
        *,
        expected_candidate_configuration_sha256: str,
    ) -> None:
        compiler["_candidate_objects"] = lambda *_args, **_kwargs: ()
        compiler["measure_continuum_image"] = lambda *_args, **_kwargs: {}
        compiler["_continuum_image_observations"] = (
            RecoveryContinuumImageCompiler(compiler)
        )
        calls.append(expected_candidate_configuration_sha256)

    def prospective() -> None:
        return None

    installer_globals: dict[str, Any] = {
        "install_recovery_compiler_seams": original
    }
    prospective_view = FunctionType(prospective.__code__, installer_globals)
    frozen = {"_install_prospective_compiler": prospective_view}
    namespace["_install_evaluation_compiler"](frozen)
    compiler: dict[str, Any] = {}

    installer_globals["install_recovery_compiler_seams"](
        compiler,
        expected_candidate_configuration_sha256="configuration",
    )

    assert calls == ["configuration"]
    installed = compiler["_continuum_image_observations"]
    assert isinstance(installed, ParentConstructionContinuumImageCompiler)
    run = SimpleNamespace(request=SimpleNamespace(input_id="continuum-1"))
    assert installed._association_path(run) == (
        namespace["_ASSOCIATION_RECONSTRUCTION"]
        / "associations/continuum-1/source_association.json"
    )


def test_execution_validation_rejects_candidate_authority() -> None:
    """A later decision cannot broaden evaluation into candidate work."""
    namespace = _namespace()
    decision = {
        "status": (
            "reviewed-before-parent-construction-evaluation-completion"
        ),
        "existing_product_completion_authorized": True,
        "compilation_authorized": True,
        "evaluation_authorized": True,
        "candidate_execution_authorized": True,
    }

    with pytest.raises(ValueError, match="not authorized"):
        namespace["_validate_execution_decision"](decision, {}, {})
