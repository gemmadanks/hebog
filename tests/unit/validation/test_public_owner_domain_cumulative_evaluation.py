"""Contracts for the version-8 cumulative evaluation-only completion."""

from __future__ import annotations

import argparse
import importlib
import json
import runpy
import subprocess
import sys
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
_PRODUCT_SEAL = (
    _ROOT / "benchmark-results/phase-5/"
    "public-owner-domain-cumulative-product-set.json"
)
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
    smoke = module.expected_bounded_smoke()
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
    assert verified["candidate_product_seal_sha256"] == file_sha256(
        _PRODUCT_SEAL
    )
    assert expected_execution["completion_program_sha256"] == file_sha256(
        _COMPLETION
    )
    assert command[1] == str(_EVALUATOR)
    assert "materialize" not in " ".join(command)
    assert command[-2:] == ["--output", str(module._OUTPUT)]


def test_product_verifier_binds_seal_and_complete_parent_rehash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The atomic seal gates the inherited complete product verifier."""
    module = _completion()
    arguments = _arguments(module, module._OUTPUT)
    calls: list[argparse.Namespace] = []

    def verify_products(value: argparse.Namespace) -> dict[str, object]:
        calls.append(value)
        return module._expected_parent_products()

    with module._configured_completion() as parent:
        monkeypatch.setitem(
            parent,
            "_load_parent_completion",
            lambda: {"verify_products": verify_products},
        )
        verified = parent["verify_products"](arguments)

    assert calls == [arguments]
    assert verified == module.expected_verified_products()


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


def test_freezer_writes_once(tmp_path: Path) -> None:
    """The exact replacement records reproduce without overwrite."""
    freezer = runpy.run_path(str(_FREEZER))
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    freezer["freeze_records"](arguments)
    for expected in (_IMPLEMENTATION, _IDENTITY, _DECISION):
        generated = tmp_path / expected.relative_to(_ROOT)
        assert generated.read_bytes() == expected.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)


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
