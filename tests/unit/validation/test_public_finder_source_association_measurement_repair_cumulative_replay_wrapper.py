"""Contracts for the measurement-repair cumulative replay wrapper."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT
    / "scripts/validation/review_phase5_public_finder_source_association_"
    "measurement_repair_cumulative_regressions.py"
)
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_source_association_cumulative_regressions.py"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-replay-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-replay-implementation-decision.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_CANDIDATE_REVISION = "6184a32648eee637f0aca03ab2ec0249bd0510f0"
_CANDIDATE_SOURCE_TREE = (
    "517d56e19a5d58eb386d96bdb181d36afb574ad018222f870cc8434c398044ff"
)
_CONFIGURATION = (
    "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
)


def _arguments(tmp_path: Path) -> Namespace:
    """Return one fixture-only prospective invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=tmp_path / "references",
        output=tmp_path / "ledger.json",
        scratch=tmp_path / "scratch",
        workers=2,
        closed_component_baseline_ledger=tmp_path / "baseline.json",
    )


def _approved_arguments() -> Namespace:
    """Return the exact prospective replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-source-association-measurement-repair.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-association-"
            "measurement-repair-6184a32"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def _committed_file_sha256(revision: str, path: str) -> str:
    """Hash one exact committed file."""
    value = subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(value).hexdigest()


def test_approval_opens_implementation_and_identity_freeze_only() -> None:
    """The exact decision cannot be interpreted as replay authority."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_PRE_REVIEW),
    }
    authorization = decision["authorization"]
    assert authorization["implementation_authorized"] is True
    assert (
        authorization["readiness_contract_implementation_authorized"] is True
    )
    assert authorization["fixture_no_write_validation_authorized"] is True
    assert (
        authorization["complete_no_write_reference_verification_authorized"]
        is True
    )
    assert authorization["identity_freeze_authorized"] is True
    assert authorization["cumulative_replay_authorized"] is False
    assert authorization["viewed_data_execution_authorized"] is False


def test_readiness_is_prospectively_bound_to_the_repaired_candidate() -> None:
    """The final candidate and future paths are fixed before results open."""
    readiness = json.loads(_READINESS.read_text(encoding="utf-8"))
    evidence = {
        item["evidence_id"]: item for item in readiness["required_evidence"]
    }

    cumulative = evidence[
        "public-finder-source-association-measurement-repair-cumulative-regression"
    ]
    assert cumulative["path"].endswith(
        "cumulative-regression-ledger-public-finder-source-association-"
        "measurement-repair.json"
    )
    assert cumulative["required_fields"]["candidate_revision"] == (
        _CANDIDATE_REVISION
    )
    assert cumulative["required_fields"]["candidate_source_tree_sha256"] == (
        _CANDIDATE_SOURCE_TREE
    )
    assert cumulative["required_fields"]["candidate_configuration_sha256"] == (
        _CONFIGURATION
    )
    qualification = evidence[
        "public-finder-source-association-measurement-repair-held-out-qualification"
    ]
    assert qualification["path"].endswith(
        "public-finder-source-association-measurement-repair-"
        "qualification-decision.json"
    )
    assert qualification["required_fields"]["candidate_revision"] == (
        _CANDIDATE_REVISION
    )


def test_wrapper_binds_the_repair_over_the_consumed_composition() -> None:
    """Only candidate and prospective write-once identities are replaced."""
    wrapper = runpy.run_path(str(_WRAPPER))

    assert wrapper["_CANDIDATE_REVISION"] == _CANDIDATE_REVISION
    assert wrapper["_CANDIDATE_SOURCE_TREE_SHA256"] == _CANDIDATE_SOURCE_TREE
    assert wrapper["_CANDIDATE_CONFIGURATION_SHA256"] == _CONFIGURATION
    assert wrapper["_candidate_configuration_sha256"]() == _CONFIGURATION
    assert wrapper["_CONSUMED_WRAPPER_SHA256"] == file_sha256(
        _CONSUMED_WRAPPER
    )
    assert wrapper["_MEASUREMENT_REPAIR_SHA256"] == _committed_file_sha256(
        _CANDIDATE_REVISION,
        "src/hebog/validation/products.py",
    )
    consumed = wrapper["_load_consumed_wrapper"]()
    assert consumed["_CANDIDATE_REVISION"] == _CANDIDATE_REVISION
    assert consumed["_CANDIDATE_SOURCE_TREE_SHA256"] == (
        _CANDIDATE_SOURCE_TREE
    )
    assert consumed["_PROSPECTIVE_OUTPUT_PATH"] == (
        _approved_arguments().output
    )
    assert consumed["_PROSPECTIVE_SCRATCH_PATH"] == (
        _approved_arguments().scratch
    )


def test_consumed_wrapper_identity_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new layer cannot silently load a changed consumed program."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_load_consumed_wrapper"].__globals__

    def changed_sha256(_path: Path) -> str:
        return "0" * 64

    monkeypatch.setitem(globals_, "file_sha256", changed_sha256)

    with pytest.raises(ValueError, match="consumed wrapper identity changed"):
        wrapper["_load_consumed_wrapper"]()


def test_wrapper_preserves_delegated_science_and_execution_seams() -> None:
    """Compact, compiler, evaluator, and reference machinery are unchanged."""
    wrapper = runpy.run_path(str(_WRAPPER))
    consumed = wrapper["_load_consumed_wrapper"]()
    current = consumed["_load_current_wrapper"]()
    frozen = current["_load_frozen_replay"]()
    compact = frozen["_write_compact_products"]
    compiler = frozen["_COMPILER_PATH"]
    evaluator = frozen["_EVALUATOR_PATH"]

    wrapper["_install_measurement_repair_composition"](
        consumed,
        current,
        frozen,
        {"execution_decision_sha256": "a" * 64},
    )

    assert frozen["_CANDIDATE_REVISION"] == _CANDIDATE_REVISION
    assert frozen["_candidate_configuration_sha256"]() == _CONFIGURATION
    assert (
        frozen["_generate_candidate_product"]
        is wrapper["_generate_candidate_product"]
    )
    assert frozen["_write_compact_products"] is compact
    assert frozen["_COMPILER_PATH"] == compiler
    assert frozen["_EVALUATOR_PATH"] == evaluator


def test_spawned_worker_reinstalls_the_measurement_repair_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spawned worker cannot fall back to the consumed candidate revision."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_generate_candidate_product"].__globals__
    frozen: dict[str, Any] = {}

    def generate(_task: dict[str, object]) -> str:
        assert frozen["_CANDIDATE_REVISION"] == _CANDIDATE_REVISION
        return "candidate-product"

    frozen["_generate_candidate_product"] = generate
    current = {"_load_frozen_replay": lambda: frozen}

    def install_static(target: dict[str, Any]) -> None:
        target["_CANDIDATE_REVISION"] = _CANDIDATE_REVISION

    consumed = {
        "_load_current_wrapper": lambda: current,
        "_install_static_science_seams": install_static,
    }
    monkeypatch.setitem(globals_, "_load_consumed_wrapper", lambda: consumed)

    assert wrapper["_generate_candidate_product"]({}) == "candidate-product"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("reference_reconstruction", Path("other-references")),
        ("output", Path("other-ledger.json")),
        ("scratch", Path("/private/tmp/other-scratch")),
        ("closed_component_baseline_ledger", Path("other-baseline.json")),
        ("workers", 1),
    ),
)
def test_wrapper_rejects_invocation_drift(field: str, value: object) -> None:
    """Population, paths, and worker count remain exact."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    setattr(arguments, field, value)

    with pytest.raises(ValueError, match="identity changed"):
        wrapper["_require_exact_invocation"](arguments)


def test_fixture_verification_opens_no_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture validation returns identities without creating replay state."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper[
        "verify_measurement_repair_replay_composition"
    ].__globals__
    arguments = _arguments(tmp_path)

    def validate_decision(_document: dict[str, object]) -> None:
        return None

    def execution_revision(_arguments: Namespace) -> str:
        return "abc123"

    def verified_reference(_arguments: Namespace) -> SimpleNamespace:
        return SimpleNamespace(
            reference_reconstruction_sha256="b" * 64,
            inputs=tuple(range(4)),
            runs=tuple(range(16)),
        )

    monkeypatch.setitem(
        globals_, "_validate_implementation_decision", validate_decision
    )
    monkeypatch.setitem(
        globals_, "_require_common_identities", execution_revision
    )
    monkeypatch.setitem(
        globals_,
        "_verify_reference_reconstruction",
        verified_reference,
    )

    result = wrapper["verify_measurement_repair_replay_composition"](
        arguments,
        implementation_decision_path=_IMPLEMENTATION_DECISION,
    )

    assert result["status"] == "pass"
    assert result["cumulative_replay_started"] is False
    assert result["verified_input_count"] == 4
    assert result["verified_reference_run_count"] == 16
    assert not arguments.output.exists()
    assert not arguments.scratch.exists()


def test_replay_remains_closed_without_a_future_decision() -> None:
    """Implementation approval cannot be reused as execution approval."""
    wrapper = runpy.run_path(str(_WRAPPER))

    with pytest.raises(ValueError, match="cumulative replay not authorized"):
        wrapper["run_authorized_replay"](
            _approved_arguments(),
            execution_decision_path=Path("missing-execution-decision.json"),
        )
