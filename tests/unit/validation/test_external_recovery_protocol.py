"""Contracts for the approved Phase 5 external recovery freeze."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.datasets import DatasetManifest, iter_dataset_recipes
from hebog.validation.post_correction_recovery import (
    build_post_correction_continuum_products,
    post_correction_candidate_configuration_sha256,
)

_ROOT = Path(__file__).parents[3]


def _script(relative_path: str) -> dict[str, Any]:
    """Load one validation script without invoking its CLI."""
    return runpy.run_path(str(_ROOT / relative_path))


def _seeds(document: dict[str, object]) -> set[int]:
    """Return every realization seed in one manifest document."""
    manifest = DatasetManifest.model_validate(document)
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def test_recovery_freezer_builds_approved_fresh_population() -> None:
    """The named freeze creates only the powered seed-disjoint design."""
    namespace = _script(
        "scripts/validation/freeze_phase5_external_recovery_population.py"
    )

    continuum, compact, freeze = namespace["build_recovery_documents"](
        repository_root=_ROOT,
        continuum_template_path=(
            _ROOT
            / "config/datasets/phase-5-external-post-correction-continuum.json"
        ),
        compact_template_path=(
            _ROOT / "config/datasets/"
            "phase-5-external-post-correction-compact-blend.json"
        ),
        power_review_path=(
            _ROOT
            / "benchmark-results/phase-5/viewed-recovery-power-review.json"
        ),
    )
    continuum_seeds = _seeds(continuum)
    compact_seeds = _seeds(compact)
    historical: set[int] = set()
    for path in sorted((_ROOT / "config/datasets").glob("*.json")):
        if "phase-5-external-recovery-" in path.name:
            continue
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        historical.update(
            recipe.seed
            for dataset in manifest.datasets
            for recipe in iter_dataset_recipes(dataset)
        )

    assert len(continuum_seeds) == 1688
    assert len(compact_seeds) == 800
    assert continuum_seeds.isdisjoint(compact_seeds)
    assert historical.isdisjoint(continuum_seeds | compact_seeds)
    assert freeze["candidate"] == {
        "revision": "c184acf7f55f936442285835b4601a6ac193fe2a",
        "source_tree_sha256": (
            "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
        ),
        "configuration_sha256": (
            "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
        ),
    }
    assert freeze["scientific_approval"] == {
        "reviewer": "Gemma Danks",
        "approved_on": "2026-08-22",
        "scope": "recovery-scientific-freeze-only-no-execution",
    }
    assert freeze["power_audit"]["paired_comparison_count"] == 226
    assert freeze["power_audit"]["selected_continuum_realization_count"] == (
        1688
    )
    assert freeze["execution_authorized"] is False
    assert freeze["finder_output_generated"] is False
    assert freeze["finder_output_opened"] is False
    expected = (
        (
            continuum,
            _ROOT / "config/datasets/phase-5-external-recovery-continuum.json",
        ),
        (
            compact,
            _ROOT
            / "config/datasets/phase-5-external-recovery-compact-blend.json",
        ),
        (
            freeze,
            _ROOT
            / "config/contracts/phase-5-external-recovery-population.json",
        ),
    )
    for document, path in expected:
        encoded = (
            json.dumps(
                document,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        assert path.read_text(encoding="utf-8") == encoded


def test_frozen_recovery_chain_is_exact_and_pending() -> None:
    """Every approved identity is frozen without opening the one-look."""
    helpers = _script(
        "scripts/validation/phase5_external_recovery_protocol.py"
    )
    population = helpers["load_recovery_population"](
        _ROOT / "config/contracts/phase-5-external-recovery-population.json"
    )
    protocol = helpers["load_recovery_protocol"](
        _ROOT / "config/contracts/phase-5-external-recovery-comparison.json"
    )
    decision = helpers["load_recovery_execution_decision"](
        _ROOT
        / "config/contracts/phase-5-external-recovery-execution-decision.json"
    )
    registry = helpers["load_recovery_endpoint_registry"](
        _ROOT
        / "config/contracts/phase-5-external-recovery-endpoint-registry.json"
    )
    review_path = (
        _ROOT
        / "config/contracts/phase-5-external-recovery-identity-review.json"
    )
    review = helpers["load_recovery_identity_review"](review_path)

    assert population["population_audit"]["seed_disjoint"] is True
    assert tuple(item.image_count for item in protocol.populations) == (
        1688,
        800,
    )
    assert decision.execution_authorized is False
    assert decision.identity_review_sha256 == "pending"
    assert registry["candidate_adapter_path"] == (
        "src/hebog/validation/post_correction_recovery.py"
    )
    assert registry["compiler_accelerator_path"] == (
        "src/hebog/validation/external_recovery_compiler.py"
    )
    assert review["execution_authorized"] is False
    assert review["scientific_products_opened"] is False
    assert len(review["runtime_images"]) == 4
    assert len(review["identity_artifacts"]) == 17
    assert hashlib.sha256(review_path.read_bytes()).hexdigest() == (
        "5bdf4f46f33fc47d1fed787ec29cf56147fe03b49bf9d33442980edeca70c13a"
    )


def test_recovery_runner_and_compiler_install_proven_composition(
    monkeypatch: Any,
) -> None:
    """Fresh execution cannot fall back to the obsolete composition."""
    runner = _script("scripts/benchmark/run_phase5_external_recovery_hebog.py")
    assert (
        runner["_run_recovery_continuum_products"].__globals__[
            "build_post_correction_continuum_products"
        ]
        is build_post_correction_continuum_products
    )
    assert post_correction_candidate_configuration_sha256(
        _ROOT / "config/contracts/phase-5-corrective-a-review.json"
    ) == ("0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94")
    compiler = _script(
        "scripts/validation/compile_phase5_external_recovery_campaign.py"
    )
    observed: dict[str, object] = {}

    def install(terminal_globals: dict[str, object], **kwargs: object) -> None:
        observed["terminal_globals"] = terminal_globals
        observed.update(kwargs)

    monkeypatch.setitem(
        compiler["_configured_terminal"].__globals__,
        "install_recovery_compiler_seams",
        install,
    )
    compiler["_configured_terminal"]()

    assert observed["expected_candidate_configuration_sha256"] == (
        "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
    )
    assert isinstance(observed["terminal_globals"], dict)


def test_recovery_evaluator_binds_powered_population() -> None:
    """The frozen evaluator retains all powered endpoint priors."""
    evaluator = _script(
        "scripts/validation/evaluate_phase5_external_recovery_decision.py"
    )
    contract = evaluator["load_recovery_evaluation_contract"](
        _ROOT / "config/contracts/phase-5-external-recovery-evaluation.json",
        _ROOT
        / "scripts/validation/evaluate_phase5_external_recovery_decision.py",
    )

    assert contract["population"] == {
        "image_count": 2488,
        "terminal_run_count": 12440,
        "binding_run_count": 8264,
        "continuum_image_count": 1688,
        "compact_blend_image_count": 800,
    }
    assert len(contract["endpoint_power_priors"]) == 226


def test_recovery_launcher_rejects_pending_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freezing identities does not authorize preflight or execution."""
    launcher = _script(
        "scripts/benchmark/run_phase5_external_recovery_campaign.py"
    )
    output = tmp_path / "campaign"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_phase5_external_recovery_campaign.py",
            "--hebog-image",
            "hebog",
            "--released-pybdsf-image",
            "released",
            "--master-pybdsf-image",
            "master",
            "--aegean-image",
            "aegean",
            "--output",
            str(output),
        ],
    )

    with pytest.raises(ValueError, match="execution is not authorized"):
        launcher["main"]()

    assert not output.exists()
