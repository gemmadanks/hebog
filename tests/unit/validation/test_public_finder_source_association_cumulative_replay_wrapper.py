"""Contracts for the non-executable source-association replay wrapper."""

from __future__ import annotations

import json
import runpy
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_public_finder_source_association_cumulative_regressions.py"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-replay-"
    "composition-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-replay-"
    "composition-implementation-decision.json"
)
_OLD_EXECUTION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-correction-cumulative-replay-"
    "reference-provenance-repair-execution-decision.json"
)


def _arguments(tmp_path: Path) -> Namespace:
    """Return one prospective source-association replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=tmp_path / "references",
        output=tmp_path / "ledger.json",
        scratch=tmp_path / "scratch",
        workers=2,
        closed_component_baseline_ledger=tmp_path / "baseline.json",
    )


def _approved_arguments() -> Namespace:
    """Return the exact prospective no-write and replay invocation."""
    return Namespace(
        campaign=None,
        reference_reconstruction=Path(
            "benchmark-results/phase-5/"
            "viewed-reference-reconstruction-public-finder-correction"
        ),
        output=Path(
            "benchmark-results/phase-5/cumulative-regression-ledger-"
            "public-finder-source-association.json"
        ),
        scratch=Path(
            "/private/tmp/hebog-phase5-public-finder-source-association-"
            "26e639a"
        ),
        workers=2,
        closed_component_baseline_ledger=Path(
            "benchmark-results/phase-5/"
            "cumulative-regression-ledger-recovery.json"
        ),
    )


def _valid_execution_document(
    wrapper: dict[str, Any],
    arguments: Namespace,
) -> dict[str, object]:
    """Return one syntactically valid future execution document."""
    return {
        **wrapper["_expected_execution_fields"](arguments),
        "cumulative_replay_authorized": True,
        "execution_authorized": True,
        "prohibited_authorizations": dict.fromkeys(
            wrapper["_PROHIBITED_AUTHORIZATIONS"], False
        ),
        "source_association_replay_identity_review": {
            "path": str(
                wrapper["_EXECUTION_IDENTITY_REVIEW"].relative_to(_ROOT)
            ),
            "sha256": "f" * 64,
        },
        "status": (
            "reviewed-before-public-finder-source-association-cumulative-replay"
        ),
    }


def test_named_approval_authorizes_implementation_but_no_replay() -> None:
    """The exact decision permits fixture/no-write work only."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_PRE_REVIEW),
    }
    authorization = decision["authorization"]
    assert authorization["implementation_authorized"] is True
    assert authorization["fixture_no_write_validation_authorized"] is True
    assert (
        authorization["complete_no_write_reference_verification_authorized"]
        is True
    )
    assert authorization["identity_freeze_authorized"] is True
    assert authorization["cumulative_replay_authorized"] is False
    assert authorization["viewed_data_execution_authorized"] is False


def test_wrapper_selects_exact_source_association_candidate() -> None:
    """The wrapper binds the approved candidate and complete configuration."""
    wrapper = runpy.run_path(str(_WRAPPER))

    assert wrapper["_CANDIDATE_REVISION"] == (
        "26e639ace9d39b039eb7c3114427277c91809591"
    )
    assert wrapper["_CANDIDATE_SOURCE_TREE_SHA256"] == (
        "34fecf302e7c6a9722dd15b8d843d316a4e4e7a1be3df2610a2d45b0a5dfb893"
    )
    assert wrapper["_candidate_configuration_sha256"]() == (
        "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
    )
    runtime = wrapper["_candidate_runtime_identity"](
        wrapper["_CANDIDATE_REVISION"]
    )
    assert runtime.source_revision == wrapper["_CANDIDATE_REVISION"]


def test_candidate_identity_helpers_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checksum, configuration, and source-overlay drift are rejected."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_load_current_wrapper"].__globals__

    def wrong_file_sha256(_path: Path) -> str:
        return "0" * 64

    monkeypatch.setitem(globals_, "file_sha256", wrong_file_sha256)
    with pytest.raises(ValueError, match="wrapper identity changed"):
        wrapper["_load_current_wrapper"]()

    configuration_globals = wrapper[
        "_candidate_configuration_sha256"
    ].__globals__

    def wrong_configuration(_value: object) -> str:
        return "0" * 64

    monkeypatch.setitem(
        configuration_globals, "canonical_sha256", wrong_configuration
    )
    with pytest.raises(ValueError, match="configuration identity changed"):
        wrapper["_candidate_configuration_sha256"]()
    with pytest.raises(ValueError, match="source overlay revision changed"):
        wrapper["_candidate_runtime_identity"]("0" * 40)


def test_wrapper_overrides_only_candidate_science_seams() -> None:
    """Delegated compact, compiler, evaluator, and reference seams remain."""
    wrapper = runpy.run_path(str(_WRAPPER))
    current = wrapper["_load_current_wrapper"]()
    frozen = current["_load_frozen_replay"]()
    compact = frozen["_write_compact_products"]
    compiler = frozen["_COMPILER_PATH"]
    evaluator = frozen["_EVALUATOR_PATH"]

    wrapper["_install_source_association_composition"](
        current,
        frozen,
        {"execution_decision_sha256": "a" * 64},
    )

    assert frozen["_CANDIDATE_REVISION"] == wrapper["_CANDIDATE_REVISION"]
    assert (
        frozen["_candidate_configuration_sha256"]()
        == (wrapper["_CANDIDATE_CONFIGURATION_SHA256"])
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


def test_spawned_candidate_worker_installs_source_association_seams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spawned workers cannot restore the consumed correction candidate."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_generate_candidate_product"].__globals__
    writer_globals: dict[str, Any] = {
        "build_post_correction_continuum_products": object(),
    }
    exec("def write_continuum_products():\n    return None\n", writer_globals)
    frozen: dict[str, Any] = {
        "_write_continuum_products": writer_globals[
            "write_continuum_products"
        ],
    }

    def generate(_task: dict[str, object]) -> str:
        assert frozen["_CANDIDATE_REVISION"] == wrapper["_CANDIDATE_REVISION"]
        assert (
            frozen["_candidate_configuration_sha256"]()
            == (wrapper["_CANDIDATE_CONFIGURATION_SHA256"])
        )
        assert (
            writer_globals["build_post_correction_continuum_products"].__name__
            == "build_public_finder_correction_continuum_products"
        )
        return "candidate-product"

    frozen["_generate_candidate_product"] = generate

    def load_frozen() -> dict[str, Any]:
        return frozen

    current = {"_load_frozen_replay": load_frozen}

    def load_current() -> dict[str, Any]:
        return current

    monkeypatch.setitem(globals_, "_load_current_wrapper", load_current)

    assert wrapper["_generate_candidate_product"]({}) == "candidate-product"


@pytest.mark.parametrize(
    "field,value",
    (
        ("reference_reconstruction", Path("other-references")),
        ("output", Path("other-ledger.json")),
        ("scratch", Path("/private/tmp/other-scratch")),
        ("closed_component_baseline_ledger", Path("other-baseline.json")),
        ("workers", 1),
    ),
)
def test_wrapper_rejects_invocation_drift(field: str, value: object) -> None:
    """Population, paths, and worker count remain one exact composition."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _approved_arguments()
    setattr(arguments, field, value)

    with pytest.raises(ValueError, match="identity changed"):
        wrapper["_require_exact_invocation"](arguments)


def test_consumed_correction_authorization_cannot_transfer(
    tmp_path: Path,
) -> None:
    """The old decision cannot authorize a changed wrapper or output."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision = json.loads(_OLD_EXECUTION_DECISION.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match=r"not authorized|identity changed"):
        wrapper["_validate_execution_decision"](
            decision,
            _arguments(tmp_path),
        )


def test_wrapper_refuses_missing_execution_decision_before_loading(
    tmp_path: Path,
) -> None:
    """Implementation state cannot open replay machinery or references."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["run_authorized_replay"].__globals__
    called = False

    def forbidden() -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    globals_["_load_current_wrapper"] = forbidden
    with pytest.raises(ValueError, match="not authorized"):
        wrapper["run_authorized_replay"](
            _arguments(tmp_path),
            execution_decision_path=tmp_path / "missing.json",
        )
    assert called is False


def test_implementation_decision_is_exact_and_non_executable(
    tmp_path: Path,
) -> None:
    """No-write validation accepts only the named implementation scope."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    wrapper["_validate_implementation_decision"](
        decision,
        _arguments(tmp_path),
    )
    decision["candidate"]["configuration_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="scope changed"):
        wrapper["_validate_implementation_decision"](
            decision,
            _arguments(tmp_path),
        )


@pytest.mark.parametrize(
    "field,value,match",
    (
        ("status", "draft", "not authorized"),
        ("authorization", {}, "boundary changed"),
        ("pre_review", {}, "pre-review identity changed"),
    ),
)
def test_implementation_decision_rejects_boundary_drift(
    field: str,
    value: object,
    match: str,
    tmp_path: Path,
) -> None:
    """Every named implementation boundary fails closed when changed."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))
    decision[field] = value

    with pytest.raises(ValueError, match=match):
        wrapper["_validate_implementation_decision"](
            decision,
            _arguments(tmp_path),
        )


@pytest.mark.parametrize("document", (None, []))
def test_no_write_verification_rejects_missing_or_malformed_decision(
    document: object,
    tmp_path: Path,
) -> None:
    """No-write verification requires the exact implementation decision."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision_path = tmp_path / "decision.json"
    if document is not None:
        decision_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="not authorized"):
        wrapper["verify_source_association_replay_composition"](
            _arguments(tmp_path),
            implementation_decision_path=decision_path,
        )


def test_common_identity_preflight_and_write_once_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The common preflight verifies all identities before write-once state."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_require_common_identities"].__globals__
    reference = tmp_path / "references"
    output = tmp_path / "ledger.json"
    scratch = tmp_path / "scratch"
    baseline = tmp_path / "baseline.json"
    arguments = Namespace(
        campaign=None,
        reference_reconstruction=reference,
        output=output,
        scratch=scratch,
        workers=2,
        closed_component_baseline_ledger=baseline,
    )
    checked: list[str] = []

    def revision() -> str:
        return "1" * 40

    def source_identity(_root: Path) -> str:
        return wrapper["_CANDIDATE_SOURCE_TREE_SHA256"]

    def configuration_identity() -> str:
        return wrapper["_CANDIDATE_CONFIGURATION_SHA256"]

    def require_file(_path: Path, _expected: str, label: str) -> None:
        checked.append(label)

    def load_current() -> dict[str, Any]:
        return {}

    monkeypatch.setitem(globals_, "_PROSPECTIVE_REFERENCE_PATH", reference)
    monkeypatch.setitem(globals_, "_PROSPECTIVE_OUTPUT_PATH", output)
    monkeypatch.setitem(globals_, "_PROSPECTIVE_SCRATCH_PATH", scratch)
    monkeypatch.setitem(globals_, "_PROSPECTIVE_BASELINE_PATH", baseline)
    monkeypatch.setitem(globals_, "_git_revision", revision)
    monkeypatch.setitem(globals_, "source_tree_sha256", source_identity)
    monkeypatch.setitem(
        globals_, "_candidate_configuration_sha256", configuration_identity
    )
    monkeypatch.setitem(globals_, "_require_file_identity", require_file)
    monkeypatch.setitem(globals_, "_load_current_wrapper", load_current)

    assert wrapper["_require_common_identities"](arguments) == "1" * 40
    assert "reference reconstruction" in checked
    assert "closed baseline" in checked

    output.write_text("already published", encoding="utf-8")
    with pytest.raises(ValueError, match="write-once output state changed"):
        wrapper["_require_common_identities"](arguments)


def test_checkout_and_file_identity_guards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A dirty checkout or changed evidence file fails before execution."""
    wrapper = runpy.run_path(str(_WRAPPER))

    def clean_check_output(
        command: tuple[str, ...],
        *,
        cwd: Path,
        text: bool,
    ) -> str:
        assert cwd == wrapper["_ROOT"]
        assert text is True
        if command[1] == "status":
            return ""
        return "2" * 40 + "\n"

    monkeypatch.setattr("subprocess.check_output", clean_check_output)
    assert wrapper["_git_revision"]() == "2" * 40

    def dirty_check_output(
        command: tuple[str, ...],
        *,
        cwd: Path,
        text: bool,
    ) -> str:
        del cwd, text
        return " M src/hebog/example.py\n" if command[1] == "status" else ""

    monkeypatch.setattr("subprocess.check_output", dirty_check_output)
    with pytest.raises(ValueError, match="clean source checkout"):
        wrapper["_git_revision"]()

    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence identity changed"):
        wrapper["_require_file_identity"](
            evidence,
            "0" * 64,
            "evidence",
        )


def test_no_write_verification_orders_identity_before_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Complete reference verification follows the full identity preflight."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper[
        "verify_source_association_replay_composition"
    ].__globals__
    events: list[str] = []

    def common(_arguments: Namespace) -> str:
        events.append("identities")
        return "f" * 40

    def references(_arguments: Namespace) -> SimpleNamespace:
        events.append("references")
        return SimpleNamespace(
            inputs=(object(),) * 2400,
            runs=(object(),) * 9600,
            reference_reconstruction_sha256=(
                "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
            ),
        )

    monkeypatch.setitem(globals_, "_require_common_identities", common)
    monkeypatch.setitem(
        globals_, "_verify_reference_reconstruction", references
    )
    result = wrapper["verify_source_association_replay_composition"](
        _arguments(tmp_path),
        implementation_decision_path=_IMPLEMENTATION_DECISION,
    )

    assert events == ["identities", "references"]
    assert result["status"] == "pass"
    assert result["verified_input_count"] == 2400
    assert result["verified_reference_run_count"] == 9600
    assert result["cumulative_replay_started"] is False


def test_authorized_replay_verifies_references_before_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A future replay must verify references before installing or running."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["run_authorized_replay"].__globals__
    events: list[str] = []

    def main() -> None:
        events.append("main")

    frozen = {"main": main}

    def load_frozen() -> dict[str, Any]:
        return frozen

    current = {"_load_frozen_replay": load_frozen}

    def authorize(
        _arguments: Namespace,
        _decision_path: Path,
    ) -> dict[str, object]:
        events.append("authorize")
        return {}

    def verify(_arguments: Namespace) -> object:
        events.append("references")
        return object()

    def load_current() -> dict[str, Any]:
        events.append("current")
        return current

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
        "_load_current_wrapper",
        load_current,
    )

    def install(
        _current: dict[str, Any],
        _frozen: dict[str, Any],
        _provenance: dict[str, object],
        *,
        verified_reference: object,
    ) -> None:
        assert verified_reference is not None
        events.append("install")

    monkeypatch.setitem(
        globals_,
        "_install_source_association_composition",
        install,
    )
    wrapper["run_authorized_replay"](
        _arguments(tmp_path),
        execution_decision_path=tmp_path / "decision.json",
    )

    assert events == [
        "authorize",
        "references",
        "current",
        "install",
        "main",
    ]


@pytest.mark.parametrize(
    "field",
    (
        "candidate_revision",
        "candidate_source_tree_sha256",
        "candidate_configuration_sha256",
        "source_association_pre_review_sha256",
        "source_association_implementation_decision_sha256",
        "source_association_identity_review_sha256",
        "composition_pre_review_sha256",
        "composition_implementation_decision_sha256",
        "current_wrapper_sha256",
        "historical_replay_sha256",
        "reference_reconstruction_sha256",
        "reference_reconstruction_producer_source_tree_sha256",
        "closed_baseline_sha256",
        "compiler_sha256",
        "evaluator_sha256",
        "reference_verifier_sha256",
        "endpoint_registry_sha256",
        "evaluation_contract_sha256",
        "viewed_request_sha256",
        "runtime_identity_registry_sha256",
        "dependency_lock_sha256",
        "compatibility_container_digest",
        "compatibility_dependency_inventory_sha256",
        "wrapper_sha256",
        "reference_reconstruction_path",
        "output_path",
        "scratch_path",
        "closed_baseline_path",
        "workers",
    ),
)
def test_wrapper_rejects_execution_identity_drift(
    field: str,
    tmp_path: Path,
) -> None:
    """Every changed candidate or delegated identity fails closed."""
    wrapper = runpy.run_path(str(_WRAPPER))
    document = _valid_execution_document(wrapper, _arguments(tmp_path))
    document[field] = "0" * 64

    with pytest.raises(ValueError, match="identity changed"):
        wrapper["_validate_execution_decision"](
            document,
            _arguments(tmp_path),
        )


@pytest.mark.parametrize(
    "mutation,match",
    (
        (("status", "draft"), "not authorized"),
        (("execution_authorized", False), "not authorized"),
        (("prohibited_authorizations", None), "boundary changed"),
        (
            ("source_association_replay_identity_review", None),
            "review changed",
        ),
    ),
)
def test_execution_decision_rejects_authorization_boundary_drift(
    mutation: tuple[str, object],
    match: str,
    tmp_path: Path,
) -> None:
    """A future decision cannot weaken the named replay boundary."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _arguments(tmp_path)
    document = _valid_execution_document(wrapper, arguments)
    document[mutation[0]] = mutation[1]

    with pytest.raises(ValueError, match=match):
        wrapper["_validate_execution_decision"](document, arguments)


def test_execution_decision_rejects_true_prohibition_and_short_review(
    tmp_path: Path,
) -> None:
    """Prohibited authority and an unbound review digest remain rejected."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _arguments(tmp_path)
    document = _valid_execution_document(wrapper, arguments)
    prohibited = document["prohibited_authorizations"]
    assert isinstance(prohibited, dict)
    prohibited["tuning_authorized"] = True
    with pytest.raises(ValueError, match="boundary changed"):
        wrapper["_validate_execution_decision"](document, arguments)

    document = _valid_execution_document(wrapper, arguments)
    review = document["source_association_replay_identity_review"]
    assert isinstance(review, dict)
    review["sha256"] = "short"
    with pytest.raises(ValueError, match="review changed"):
        wrapper["_validate_execution_decision"](document, arguments)


@pytest.mark.parametrize("document", (None, []))
def test_future_authorization_rejects_missing_or_malformed_decision(
    document: object,
    tmp_path: Path,
) -> None:
    """Future replay authorization requires a complete object decision."""
    wrapper = runpy.run_path(str(_WRAPPER))
    decision_path = tmp_path / "execution.json"
    if document is not None:
        decision_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="not authorized"):
        wrapper["_authorize_replay"](_arguments(tmp_path), decision_path)


def test_future_authorization_returns_bound_provenance_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A syntactically valid fixture decision yields bound provenance only."""
    wrapper = runpy.run_path(str(_WRAPPER))
    globals_ = wrapper["_authorize_replay"].__globals__
    review_path = tmp_path / "review.json"
    decision_path = tmp_path / "execution.json"
    arguments = _arguments(tmp_path)
    monkeypatch.setitem(globals_, "_ROOT", tmp_path)
    monkeypatch.setitem(globals_, "_EXECUTION_IDENTITY_REVIEW", review_path)
    document = _valid_execution_document(wrapper, arguments)
    document["source_association_replay_identity_review"] = {
        "path": "review.json",
        "sha256": "f" * 64,
    }
    decision_path.write_text(json.dumps(document), encoding="utf-8")

    def common(_arguments: Namespace) -> str:
        return "3" * 40

    def require_file(_path: Path, _expected: str, _label: str) -> None:
        return None

    monkeypatch.setitem(globals_, "_require_common_identities", common)
    monkeypatch.setitem(globals_, "_require_file_identity", require_file)

    provenance = wrapper["_authorize_replay"](arguments, decision_path)
    assert provenance["execution_checkout_revision"] == "3" * 40
    assert provenance["source_association_replay_identity_review_sha256"] == (
        "f" * 64
    )
    runtime = provenance["runtime_binding"]
    assert isinstance(runtime, dict)
    assert runtime["source_association_baked_into_container"] is False
