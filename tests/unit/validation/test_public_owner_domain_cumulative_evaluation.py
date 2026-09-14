"""Contracts for the version-8 cumulative evaluation-only completion."""

from __future__ import annotations

import argparse
import importlib
import json
import runpy
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_public_owner_domain_cumulative.py"
)
_COMPLETION = (
    _ROOT / "scripts/validation/"
    "complete_phase5_public_owner_domain_cumulative_evaluation.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_public_owner_domain_cumulative_evaluation.py"
)
_PREFIX = "phase-5-public-owner-domain-cumulative-evaluation"
_IMPLEMENTATION = (
    _ROOT / f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_IDENTITY = _ROOT / f"config/contracts/{_PREFIX}-identity-review.json"
_DECISION = _ROOT / f"config/contracts/{_PREFIX}-execution-decision.json"
_CANDIDATE = {
    "configuration_sha256": (
        "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
    ),
    "product_set_sha256": (
        "f43cb2741e3d66a51bd71baccc6f090199af02eb0784d08cb4295613f17758ed"
    ),
    "revision": "95cfc76ded56556dc3ad6894410962d34f0d5604",
    "source_tree_sha256": (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    ),
}
VerifierFixture = tuple[
    dict[str, Any], argparse.Namespace, list[argparse.Namespace]
]


def _completion() -> Any:
    """Import the scoped evaluation-only completion."""
    return importlib.import_module(
        "scripts.validation."
        "complete_phase5_public_owner_domain_cumulative_evaluation"
    )


def _arguments(module: Any, output: Path) -> argparse.Namespace:
    """Build one exact evaluation-only invocation."""
    return argparse.Namespace(
        repository_root=_ROOT,
        reference_reconstruction=module._REFERENCE_RECONSTRUCTION,
        source_request=module._SOURCE_REQUEST,
        population=module._POPULATION,
        current_scratch=module._CURRENT_SCRATCH,
        incumbent_scratch=module._INCUMBENT_SCRATCH,
        reconstruction_record=module._RECONSTRUCTION_RECORD,
        product_seal=module._PRODUCT_SEAL,
        output=output,
        verify_only=True,
        smoke_only=False,
    )


@pytest.fixture
def isolated_product_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[VerifierFixture]:
    """Exercise real seal/namespace guards without live campaign products."""
    module = _completion()
    arguments = _arguments(module, module._OUTPUT)
    arguments.repository_root = tmp_path
    arguments.current_scratch = tmp_path / "current"
    arguments.incumbent_scratch = tmp_path / "incumbent"
    calls: list[argparse.Namespace] = []
    with (
        module._configured_completion() as parent,
        monkeypatch.context() as bindings,
    ):
        bindings.setitem(parent, "_ROOT", tmp_path)
        bindings.setitem(parent, "_CURRENT_SCRATCH", arguments.current_scratch)
        bindings.setitem(
            parent, "_INCUMBENT_SCRATCH", arguments.incumbent_scratch
        )
        seal = {
            "status": "complete",
            "candidate_execution_count": parent["_EXPECTED_INPUT_COUNT"],
            "candidate_revision": parent["_CURRENT_REVISION"],
            "candidate_source_tree_sha256": (
                parent["_CURRENT_SOURCE_TREE_SHA256"]
            ),
            "candidate_configuration_sha256": (
                parent["_CURRENT_CONFIGURATION_SHA256"]
            ),
            "candidate_product_set_sha256": (
                parent["_CURRENT_PRODUCT_SET_SHA256"]
            ),
            "identity_review_sha256": parent[
                "_CURRENT_REPLAY_IDENTITY_SHA256"
            ],
            "execution_decision_sha256": (
                parent["_CURRENT_REPLAY_DECISION_SHA256"]
            ),
            "pybdsf_execution_count": 0,
            "reference_run_count": parent["_EXPECTED_REFERENCE_RUN_COUNT"],
        }
        canonical = canonical_sha256(seal)
        seal["record_canonical_sha256"] = canonical
        seal_path = tmp_path / arguments.product_seal
        seal_path.parent.mkdir(parents=True)
        seal_path.write_text(json.dumps(seal), encoding="utf-8")
        bindings.setitem(
            parent, "_CURRENT_PRODUCT_SEAL_SHA256", file_sha256(seal_path)
        )
        bindings.setitem(
            parent, "_CURRENT_PRODUCT_SEAL_CANONICAL_SHA256", canonical
        )

        def verify_products(value: argparse.Namespace) -> dict[str, object]:
            calls.append(value)
            return parent["_expected_parent_products"]()

        bindings.setitem(
            parent,
            "_load_parent_completion",
            lambda: {"verify_products": verify_products},
        )
        yield parent, arguments, calls


def test_evaluator_changes_only_the_current_candidate_identity() -> None:
    """The reviewed terminal compiler remains the exact parent."""
    overlay = runpy.run_path(str(_EVALUATOR))
    evaluator = overlay["load_public_owner_domain_evaluator"]()

    assert (
        file_sha256(overlay["_PARENT_EVALUATOR"])
        == overlay["_PARENT_EVALUATOR_SHA256"]
    )
    assert evaluator["_CURRENT_REVISION"] == _CANDIDATE["revision"]
    assert (
        evaluator["_CURRENT_SOURCE_TREE_SHA256"]
        == _CANDIDATE["source_tree_sha256"]
    )
    assert (
        evaluator["_CURRENT_CONFIGURATION_SHA256"]
        == _CANDIDATE["configuration_sha256"]
    )
    assert callable(evaluator["compile_prospective_decision"])
    assert callable(evaluator["_truth_linked_tail_record"])
    assert Path(evaluator["__file__"]).resolve() == _EVALUATOR.resolve()
    assert callable(overlay.get("_compile_incumbent_pair"))
    assert callable(overlay.get("compile_prospective_decision"))
    assert callable(overlay.get("main"))


def test_completion_retargets_only_current_products_and_output() -> None:
    """The completion reuses references without candidate execution."""
    module = _completion()
    verified = module.expected_verified_products()
    # Composition uses the reviewed smoke summary, not its local terminal.
    identity = json.loads(_IDENTITY.read_text(encoding="utf-8"))
    smoke = identity["bounded_terminal_smoke"]
    expected_execution = module._expected_execution(verified, smoke)
    command = module._evaluator_command(_arguments(module, module._OUTPUT))

    assert (
        Path(
            "/private/tmp/hebog-phase5-public-owner-domain-cumulative-95cfc76"
        )
        == module._CURRENT_SCRATCH
    )
    assert (
        Path(
            "benchmark-results/phase-5/"
            "public-owner-domain-cumulative-product-set.json"
        )
        == module._PRODUCT_SEAL
    )
    assert verified["current_revision"] == _CANDIDATE["revision"]
    assert (
        verified["current_source_tree_sha256"]
        == _CANDIDATE["source_tree_sha256"]
    )
    assert (
        verified["current_product_set_sha256"]
        == _CANDIDATE["product_set_sha256"]
    )
    identity = json.loads(_IDENTITY.read_text(encoding="utf-8"))
    assert verified == identity["verified_products"]
    assert expected_execution["completion_program_sha256"] == file_sha256(
        _COMPLETION
    )
    assert command[1] == str(_EVALUATOR)
    assert "materialize" not in " ".join(command)
    assert command[-2:] == ["--output", str(module._OUTPUT)]


def test_product_verifier_binds_seal_and_complete_parent_rehash(
    isolated_product_verifier: VerifierFixture,
) -> None:
    """The atomic seal gates the inherited complete product verifier."""
    parent, arguments, calls = isolated_product_verifier

    verified = parent["verify_products"](arguments)

    assert calls == [arguments]
    assert verified == parent["expected_verified_products"]()
    assert verified["candidate_product_seal_sha256"] == file_sha256(
        arguments.repository_root / arguments.product_seal
    )
    assert not (arguments.repository_root / arguments.output).exists()


@pytest.mark.parametrize("output_kind", ["file", "directory"])
def test_product_verifier_preserves_existing_output(
    isolated_product_verifier: VerifierFixture, output_kind: str
) -> None:
    """Existing terminals stop verification and remain untouched."""
    parent, arguments, calls = isolated_product_verifier
    output = arguments.repository_root / arguments.output
    if output_kind == "file":
        output.write_bytes(b"preserved terminal")
    else:
        output.mkdir()

    with pytest.raises(FileExistsError, match="evaluation output exists"):
        parent["verify_products"](arguments)

    assert calls == []
    if output_kind == "file":
        assert output.read_bytes() == b"preserved terminal"
    else:
        assert output.is_dir()
        assert list(output.iterdir()) == []


@pytest.mark.parametrize("valid_checksum", [False, True])
def test_product_verifier_rejects_changed_seal_before_parent(
    isolated_product_verifier: VerifierFixture,
    monkeypatch: pytest.MonkeyPatch,
    valid_checksum: bool,
) -> None:
    """Both byte tampering and a correctly hashed wrong count fail closed."""
    parent, arguments, calls = isolated_product_verifier
    path = arguments.repository_root / arguments.product_seal
    seal = json.loads(path.read_text(encoding="utf-8"))
    seal.pop("record_canonical_sha256")
    seal["candidate_execution_count"] -= 1
    seal["record_canonical_sha256"] = canonical_sha256(seal)
    path.write_text(json.dumps(seal), encoding="utf-8")
    with monkeypatch.context() as bindings:
        if valid_checksum:
            bindings.setitem(
                parent, "_CURRENT_PRODUCT_SEAL_SHA256", file_sha256(path)
            )
            bindings.setitem(
                parent,
                "_CURRENT_PRODUCT_SEAL_CANONICAL_SHA256",
                seal["record_canonical_sha256"],
            )
        message = "seal is malformed" if valid_checksum else "seal changed"
        with pytest.raises(ValueError, match=message):
            parent["verify_products"](arguments)

    assert calls == []


def test_product_verifier_rejects_changed_output_path(
    isolated_product_verifier: VerifierFixture,
) -> None:
    """An isolated fixture still enforces the exact invocation identity."""
    parent, arguments, calls = isolated_product_verifier
    arguments.output = Path("different-output.json")

    with pytest.raises(ValueError, match="evaluation output changed"):
        parent["verify_products"](arguments)

    assert calls == []


@pytest.mark.integration
@pytest.mark.requires_data
def test_bounded_smoke_reaches_all_terminal_seams(tmp_path: Path) -> None:
    """A short smoke covers decision, tail, and write-once publication."""
    module = _completion()

    record = module.run_bounded_terminal_smoke(tmp_path)

    assert record["status"] == "pass"
    assert record["all_required_endpoints_pass"] is True
    assert record["cumulative_science_regression_ready"] is True
    assert record["section_counts"] == {
        "aegean_parity": 143,
        "binding_safety": 5,
        "incumbent_retention": 368,
        "longer_term_absolute_objectives": 15,
        "pybdsf_parity": 676,
    }
    assert record["terminal_publication_status"] == "pass"


def test_scoped_completion_restores_the_historical_parent() -> None:
    """Version-8 bindings cannot contaminate the closed evaluation module."""
    historical = importlib.import_module(
        "scripts.validation.complete_phase5_final_cumulative_evaluation"
    )
    previous_revision = historical._CURRENT_REVISION
    module = _completion()

    module.expected_verified_products()

    assert previous_revision == historical._CURRENT_REVISION


def test_freezer_records_are_non_executable_then_one_use() -> None:
    """Scientific identity remains separate from evaluation authority."""
    identity = json.loads(_IDENTITY.read_text(encoding="utf-8"))
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert decision["status"] == (
        "authorized-for-one-final-cumulative-evaluation"
    )
    assert decision["identity_review_sha256"] == canonical_sha256(identity)
    assert decision["authorization"]["evaluation_authorized"] is True
    assert {
        value
        for key, value in decision["authorization"].items()
        if key != "evaluation_authorized"
    } == {False}


@pytest.mark.integration
@pytest.mark.requires_data
def test_freezer_writes_once(tmp_path: Path) -> None:
    """Current fixture identities are recorded without changing closed ones."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freezer["freeze_records"](arguments)
    implementation, identity, decision = (
        json.loads((tmp_path / path.relative_to(_ROOT)).read_text("utf-8"))
        for path in (_IMPLEMENTATION, _IDENTITY, _DECISION)
    )
    for record in (implementation, identity):
        for binding in record["fixture_bindings"].values():
            assert binding["sha256"] == file_sha256(_ROOT / binding["path"])
    reviewed = json.loads(_IDENTITY.read_text(encoding="utf-8"))
    assert identity["program_bindings"] == reviewed["program_bindings"]
    assert identity["expected_execution"] == reviewed["expected_execution"]
    assert identity["implementation"]["sha256"] == canonical_sha256(
        implementation
    )
    assert decision["identity_review_sha256"] == canonical_sha256(identity)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)


@pytest.mark.integration
@pytest.mark.requires_data
def test_freezer_direct_cli_resolves_repository_modules(
    tmp_path: Path,
) -> None:
    """Direct execution must not depend on pytest's import path."""
    result = subprocess.run(
        (
            sys.executable,
            str(_FREEZER),
            "--repository-root",
            str(_ROOT),
            "--output-root",
            str(tmp_path),
        ),
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
