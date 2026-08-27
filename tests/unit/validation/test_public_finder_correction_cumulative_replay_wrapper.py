"""Contracts for the non-executable correction cumulative-replay wrapper."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_correction_cumulative_regressions.py"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-repair-"
    "implementation-decision.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-repair-pre-review.json"
)
_REFERENCE_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-reference-"
    "provenance-repair-pre-review.json"
)
_REFERENCE_REPAIR_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-reference-"
    "provenance-repair-implementation-decision.json"
)
_REFERENCE_REPAIR_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-public-finder-correction-cumulative-replay-reference-"
    "provenance-repair-review.json"
)


def _arguments(tmp_path: Path) -> Namespace:
    """Return one prospective write-once replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=tmp_path / "references",
        output=tmp_path / "ledger.json",
        scratch=tmp_path / "scratch",
        workers=2,
        closed_component_baseline_ledger=tmp_path / "baseline.json",
    )


def _reference_repair_arguments(tmp_path: Path) -> Namespace:
    """Return the approved non-executable repair verification invocation."""
    arguments = _arguments(tmp_path)
    arguments.scratch = Path(
        "/private/tmp/hebog-phase5-public-finder-correction-reference-repair-"
        "b1d59e5"
    )
    return arguments


def _frozen_replay_arguments() -> Namespace:
    """Return the exact invocation frozen after reference verification."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-public-finder-correction.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-correction-"
            "reference-repair-b1d59e5"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def test_named_repair_approval_authorizes_no_replay() -> None:
    """Implementation approval cannot open the cumulative replay."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": (
            "config/contracts/phase-5-public-finder-correction-cumulative-"
            "replay-repair-pre-review.json"
        ),
        "sha256": (
            "e198df128900bf991c979764fc67dbda8a9b0a682be30f92bf70703122c1f162"
        ),
    }
    assert file_sha256(_PRE_REVIEW) == decision["pre_review"]["sha256"]
    assert decision["authorization"]["implementation_authorized"] is True
    assert decision["authorization"]["identity_freeze_authorized"] is True
    assert decision["authorization"]["cumulative_replay_authorized"] is False
    assert (
        decision["authorization"]["public_development_execution_authorized"]
        is False
    )


def test_named_reference_repair_approval_authorizes_no_replay() -> None:
    """The latest approval permits repair and no-write verification only."""
    decision = json.loads(
        _REFERENCE_REPAIR_IMPLEMENTATION_DECISION.read_text(encoding="utf-8")
    )

    assert decision["pre_review"] == {
        "path": str(_REFERENCE_REPAIR_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REFERENCE_REPAIR_PRE_REVIEW),
    }
    authorization = decision["authorization"]
    assert authorization["implementation_authorized"] is True
    assert authorization["identity_freeze_authorized"] is True
    assert (
        authorization["complete_no_write_reference_verification_authorized"]
        is True
    )
    assert authorization["cumulative_replay_authorized"] is False
    assert authorization["public_development_execution_authorized"] is False


def test_wrapper_binds_the_reconstructed_reference_terminal() -> None:
    """The replacement replay must consume only the newly sealed evidence."""
    wrapper = runpy.run_path(str(_WRAPPER))

    assert wrapper["_REFERENCE_RECONSTRUCTION_SHA256"] == (
        "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
    )


def test_reference_repair_review_freezes_no_execution_authority() -> None:
    """Verified identities remain inert until one exact named approval."""
    wrapper = runpy.run_path(str(_WRAPPER))
    review = json.loads(_REFERENCE_REPAIR_REVIEW.read_text(encoding="utf-8"))

    assert review["status"] == (
        "ready-for-named-public-finder-correction-cumulative-replay-approval"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["prospective_execution"] == wrapper[
        "_expected_execution_fields"
    ](_frozen_replay_arguments())
    implementation = review["implementation"]
    wrapper_record = implementation["wrapper"]
    content = subprocess.check_output(
        (
            "git",
            "show",
            f"{implementation['commit']}:{wrapper_record['path']}",
        ),
        cwd=_ROOT,
    )
    assert hashlib.sha256(content).hexdigest() == wrapper_record["sha256"]
    reconstruction = review["reconstruction"]
    completion = reconstruction["completion_review"]
    assert file_sha256(_ROOT / completion["path"]) == completion["sha256"]
    assert (
        file_sha256(_ROOT / reconstruction["path"] / "recovery.json")
        == reconstruction["recovery_sha256"]
    )
    verification = review["no_write_verification"]
    assert verification["status"] == "pass"
    assert verification["verified_input_count"] == 2400
    assert verification["verified_reference_run_count"] == 9600
    assert verification["output_absent"] is True
    assert verification["scratch_absent"] is True


def test_reference_repair_decision_matches_the_no_write_scope(
    tmp_path: Path,
) -> None:
    """The implementation decision validates only its prospective scratch."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision = json.loads(
        _REFERENCE_REPAIR_IMPLEMENTATION_DECISION.read_text(encoding="utf-8")
    )

    wrapper["_validate_reference_repair_implementation_decision"](
        decision,
        _reference_repair_arguments(tmp_path),
    )

    decision["scope"][
        "historical_reconstruction_producer_source_tree_sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="scope changed"):
        wrapper["_validate_reference_repair_implementation_decision"](
            decision,
            _reference_repair_arguments(tmp_path),
        )


def test_reference_producer_view_is_scoped_to_both_frozen_source_checks() -> (
    None
):
    """Historical producer identity must not replace candidate identity."""
    wrapper = runpy.run_path(str(_WRAPPER))

    def ambient_source(_root: object) -> str:
        return "ambient-consumer-source"

    protocol_globals: dict[str, Any] = {
        "source_tree_sha256": ambient_source,
    }
    exec(
        "def load_decision(_path):\n    return source_tree_sha256(None)\n",
        protocol_globals,
    )
    verifier_globals: dict[str, Any] = {
        "_helpers": lambda: {
            "load_viewed_recovery_execution_decision": protocol_globals[
                "load_decision"
            ]
        },
        "source_tree_sha256": ambient_source,
    }
    exec(
        "def verify():\n"
        "    producer = _helpers()[\n"
        "        'load_viewed_recovery_execution_decision'\n"
        "    ](None)\n"
        "    return producer, source_tree_sha256(None)\n",
        verifier_globals,
    )
    reconstruction = {
        **verifier_globals,
        "verify_viewed_reference_reconstruction": verifier_globals["verify"],
    }
    assert reconstruction is not reconstruction["verify"].__globals__

    wrapper["_install_reference_producer_view"](reconstruction)

    expected = (
        "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
    )
    assert reconstruction["verify"]() == (expected, expected)
    runtime = wrapper["_candidate_runtime_identity"](
        "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
    )
    assert runtime.source_revision == (
        "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
    )


def test_authorized_replay_verifies_references_before_frozen_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A verifier failure must occur before historical scratch creation."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["run_authorized_replay"].__globals__
    events: list[str] = []
    verified = object()
    frozen = {"main": lambda: events.append("main")}

    def authorize(
        _arguments: Namespace,
        _decision: Path,
    ) -> dict[str, object]:
        events.append("authorize")
        return {}

    def verify(_arguments: Namespace) -> object:
        events.append("verify")
        return verified

    def load() -> dict[str, Any]:
        events.append("load")
        return frozen

    monkeypatch.setitem(
        globals_,
        "_authorize_replay",
        authorize,
    )
    monkeypatch.setitem(
        globals_,
        "_verify_reference_reconstruction",
        verify,
    )
    monkeypatch.setitem(
        globals_,
        "_load_frozen_replay",
        load,
    )

    def install(
        _frozen: dict[str, Any],
        _provenance: dict[str, object],
        *,
        verified_reference: object,
    ) -> None:
        assert verified_reference is verified
        events.append("install")

    monkeypatch.setitem(globals_, "_install_repair_composition", install)

    wrapper["run_authorized_replay"](
        _arguments(tmp_path),
        execution_decision_path=tmp_path / "decision.json",
    )

    assert events == ["authorize", "verify", "load", "install", "main"]


def test_reference_runpy_reuses_verified_view_only_for_bound_script() -> None:
    """Other historical runpy consumers remain byte-for-byte delegated."""
    wrapper = runpy.run_path(str(_WRAPPER))
    verified = object()

    class Delegate:
        def run_path(
            self,
            path_name: str,
            *_args: Any,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            if (
                Path(path_name).resolve()
                != wrapper["_REFERENCE_VERIFIER"].resolve()
            ):
                return {"delegated_path": path_name}

            def load_decision(_path: object) -> str:
                return "unused"

            def ambient_source(_root: object) -> str:
                return "ambient"

            verifier_globals: dict[str, Any] = {
                "_helpers": lambda: {
                    "load_viewed_recovery_execution_decision": load_decision
                },
                "source_tree_sha256": ambient_source,
            }
            exec(
                "def verify_viewed_reference_reconstruction(*args, **kwargs):"
                "\n    return 'unverified'\n",
                verifier_globals,
            )
            return dict(verifier_globals)

    proxy = wrapper["_ReferenceProducerRunpy"](Delegate(), verified)
    other = proxy.run_path("scripts/validation/another_program.py")
    reconstruction = proxy.run_path(str(wrapper["_REFERENCE_VERIFIER"]))

    assert other == {"delegated_path": "scripts/validation/another_program.py"}
    assert (
        reconstruction["verify_viewed_reference_reconstruction"]() is verified
    )


def test_wrapper_installs_only_the_approved_candidate_seams() -> None:
    """The wrapper keeps frozen machinery but selects correction science."""
    wrapper = runpy.run_path(str(_WRAPPER))
    frozen = wrapper["_load_frozen_replay"]()
    compact = frozen["_write_compact_products"]
    compiler = frozen["_COMPILER_PATH"]
    evaluator = frozen["_EVALUATOR_PATH"]
    provenance = {"execution_decision_sha256": "a" * 64}

    wrapper["_install_repair_composition"](frozen, provenance)

    assert frozen["_CANDIDATE_REVISION"] == (
        "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
    )
    assert frozen["_candidate_configuration_sha256"]() == (
        "65c8876dcdb484bd5a82b3520e065ea6bf33cf24cfdd33b592c6c859231c62f0"
    )
    writer_globals = frozen["_write_continuum_products"].__globals__
    assert (
        writer_globals["build_post_correction_continuum_products"].__name__
        == "build_public_finder_correction_continuum_products"
    )
    assert frozen["_write_compact_products"] is compact
    assert frozen["_COMPILER_PATH"] == compiler
    assert frozen["_EVALUATOR_PATH"] == evaluator
    assert frozen["_CLOSED_COMPONENT_BASELINE_LEDGER_SHA256"] == (
        "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
    )
    runtime = frozen["_candidate_runtime_identity"](
        frozen["_CANDIDATE_REVISION"]
    )
    assert runtime.name == "hebog-source-overlay"
    assert runtime.source_revision == frozen["_CANDIDATE_REVISION"]
    assert runtime.container_image_digest == (
        "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1"
    )


def test_wrapper_loads_frozen_program_without_ambient_repository_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed-package test environment still loads the bound script."""
    wrapper = runpy.run_path(str(_WRAPPER))
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry != str(_ROOT)],
    )

    frozen = wrapper["_load_frozen_replay"]()

    assert frozen["_CANDIDATE_REVISION"] == (
        "c184acf7f55f936442285835b4601a6ac193fe2a"
    )


def test_wrapper_adds_explicit_overlay_provenance_only_to_ledger() -> None:
    """Legacy marker serialization stays exact while the ledger is honest."""
    wrapper = runpy.run_path(str(_WRAPPER))
    frozen = wrapper["_load_frozen_replay"]()
    provenance = {
        "candidate_source_overlay_revision": (
            "b1d59e5aaf778a5fed4ea662afeba2ee100424ff"
        )
    }
    wrapper["_install_repair_composition"](frozen, provenance)
    serialize = frozen["_canonical_json_bytes"]

    marker = json.loads(serialize({"schema_version": 1}))
    ledger = json.loads(
        serialize(
            {
                "ledger_id": "phase-5-cumulative-regression-ledger",
                "schema_version": 1,
            }
        )
    )

    assert "replay_repair_provenance" not in marker
    assert ledger["replay_repair_provenance"] == provenance


def test_wrapper_refuses_absent_execution_decision_before_loading_replay(
    tmp_path: Path,
) -> None:
    """Implementation state fails before a source manifest can be opened."""
    wrapper = runpy.run_path(str(_WRAPPER))
    called = False

    def forbidden() -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    wrapper["run_authorized_replay"].__globals__["_load_frozen_replay"] = (
        forbidden
    )

    with pytest.raises(ValueError, match="not authorized"):
        wrapper["run_authorized_replay"](
            _arguments(tmp_path),
            execution_decision_path=tmp_path / "missing.json",
        )

    assert called is False


@pytest.mark.parametrize(
    "field",
    (
        "candidate_revision",
        "candidate_source_tree_sha256",
        "candidate_configuration_sha256",
        "base_review_sha256",
        "closed_baseline_sha256",
        "compiler_sha256",
        "correction_contract_sha256",
        "dependency_lock_sha256",
        "endpoint_registry_sha256",
        "evaluation_contract_sha256",
        "evaluator_sha256",
        "reference_reconstruction_sha256",
        "reference_reconstruction_producer_source_tree_sha256",
        "reference_repair_implementation_decision_sha256",
        "reference_repair_pre_review_sha256",
        "reference_verifier_sha256",
        "viewed_request_sha256",
    ),
)
def test_wrapper_rejects_identity_drift(field: str, tmp_path: Path) -> None:
    """Every approved science and environment identity fails closed."""
    wrapper = runpy.run_path(str(_WRAPPER))
    document = {
        **wrapper["_expected_execution_fields"](_arguments(tmp_path)),
        "cumulative_replay_authorized": True,
        "execution_authorized": True,
        "prohibited_authorizations": {
            "campaign_execution_authorized": False,
            "cutover_authorized": False,
            "fresh_qualification_authorized": False,
            "optimization_authorized": False,
            "public_development_execution_authorized": False,
            "release_authorized": False,
            "rescoring_authorized": False,
            "tuning_authorized": False,
        },
        "repair_identity_review": {
            "path": "config/contracts/pending-review.json",
            "sha256": "f" * 64,
        },
        "status": "reviewed-before-public-finder-correction-cumulative-replay",
    }
    document[field] = "0" * 64

    with pytest.raises(ValueError, match="identity changed"):
        wrapper["_validate_execution_decision"](
            document,
            _arguments(tmp_path),
        )
