# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
"""Contracts for parent-construction existing-product evaluation."""

from __future__ import annotations

import json
import runpy
import subprocess
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-completion-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-completion-execution-decision.json"
)


def _namespace() -> dict[str, Any]:
    """Load the completion wrapper without running its entry point."""
    return runpy.run_path(str(_SCRIPT))


def _committed_file_sha256(revision: str, path: str) -> str:
    """Hash one file from the implementation revision named by review."""
    content = subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return sha256(content).hexdigest()


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
    """The sidecar compiler follows the real closure-backed installer."""
    namespace = _namespace()
    calls: list[str] = []

    def base_installer(
        compiler: dict[str, Any],
        prospective: object,
        configuration_sha256: str,
    ) -> None:
        compiler["_candidate_objects"] = lambda *_args, **_kwargs: ()
        compiler["measure_continuum_image"] = lambda *_args, **_kwargs: {}
        compiler["_continuum_image_observations"] = (
            RecoveryContinuumImageCompiler(compiler)
        )
        calls.append(f"base:{configuration_sha256}:{prospective!s}")

    def closure_installer(predecessor: Any) -> Any:
        def install(
            compiler: dict[str, Any],
            prospective: object,
            configuration_sha256: str,
        ) -> None:
            predecessor(compiler, prospective, configuration_sha256)
            calls.append("source-reconstruction")

        return install

    frozen = {
        "_install_prospective_compiler": closure_installer(base_installer)
    }
    namespace["_install_evaluation_compiler"](frozen)
    compiler: dict[str, Any] = {}

    frozen["_install_prospective_compiler"](
        compiler,
        "prospective",
        "configuration",
    )

    assert calls == [
        "base:configuration:prospective",
        "source-reconstruction",
    ]
    installed = compiler["_continuum_image_observations"]
    assert isinstance(installed, ParentConstructionContinuumImageCompiler)
    run = SimpleNamespace(request=SimpleNamespace(input_id="continuum-1"))
    assert installed._association_path(run) == (
        namespace["_ASSOCIATION_RECONSTRUCTION"]
        / "associations/continuum-1/source_association.json"
    )


def test_real_parent_compiler_installer_is_wrapped_as_a_closure() -> None:
    """The exact frozen predecessor composition is accepted unchanged."""
    namespace = _namespace()
    parent = namespace["_load_parent_wrapper"]()
    _, _, frozen = parent["_load_source_association_composition"]()
    parent["_install_parent_construction_static_seams"](frozen)
    predecessor = frozen["_install_prospective_compiler"]

    assert predecessor.__closure__ is not None
    namespace["_install_evaluation_compiler"](frozen)

    installed = frozen["_install_prospective_compiler"]
    assert installed is not predecessor
    assert predecessor in tuple(
        cell.cell_contents for cell in installed.__closure__ or ()
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


def test_identity_review_freezes_only_non_executable_completion() -> None:
    """The review binds exact evidence without authorizing evaluation."""
    review: dict[str, Any] = json.loads(_REVIEW.read_text(encoding="utf-8"))

    assert review["status"] == (
        "reviewed-before-parent-construction-evaluation-completion"
    )
    implementation = cast(dict[str, Any], review["implementation"])
    revision = cast(str, implementation["commit"])
    assert revision == "1ce8ddedda8ae6d2715f1c70618bab065e532007"
    for identity in implementation.values():
        if not isinstance(identity, dict):
            continue
        identity_record = cast(dict[str, Any], identity)
        path = identity_record.get("path")
        expected = identity_record.get("sha256")
        if isinstance(path, str):
            assert isinstance(expected, str)
            assert _committed_file_sha256(revision, path) == expected
    verified = cast(dict[str, Any], review["verified_composition"])
    assert verified["candidate_product_count"] == 2400
    assert verified["candidate_product_set_sha256"] == (
        "b81cb3d47d7db5ac45c66893445bd5d25711af88372566bbe979a6bce9a0fc87"
    )
    assert verified["association_product_set_sha256"] == (
        "e1f16373f47119c71d64e3aa90639403dd1e978d84e68f4fd507e20527a27e90"
    )
    assert verified["reference_run_count"] == 9600
    assert verified["output_absent"] is True
    assert verified["candidate_execution_started"] is False
    assert verified["compilation_started"] is False
    assert verified["evaluation_started"] is False
    assert review["candidate_execution_authorized"] is False
    assert review["compilation_authorized"] is False
    assert review["evaluation_authorized"] is False
    assert not any(review["prohibited_authorizations"].values())


def test_execution_decision_authorizes_only_evaluation_completion() -> None:
    """The named approval opens compilation, never candidate execution."""
    review: dict[str, Any] = json.loads(_REVIEW.read_text(encoding="utf-8"))
    decision: dict[str, Any] = json.loads(
        _EXECUTION_DECISION.read_text(encoding="utf-8")
    )

    assert decision["status"] == review["status"]
    assert decision["identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    verified = cast(dict[str, Any], review["verified_composition"])
    for field in (
        "association_product_set_sha256",
        "association_reconstruction_recovery_sha256",
        "candidate_product_set_sha256",
        "completion_program_sha256",
        "evaluation_overlay_sha256",
        "parent_wrapper_sha256",
    ):
        assert decision[field] == verified[field]
    assert decision["existing_product_completion_authorized"] is True
    assert decision["compilation_authorized"] is True
    assert decision["evaluation_authorized"] is True
    assert decision["candidate_execution_authorized"] is False
    assert not any(decision["prohibited_authorizations"].values())
