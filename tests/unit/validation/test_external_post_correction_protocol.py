# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the approved Phase 5 post-correction freeze."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.datasets import DatasetManifest, iter_dataset_recipes

_ROOT = Path(__file__).parents[3]


def _script(relative_path: str) -> dict[str, Any]:
    """Load one validation script without invoking its CLI."""
    return runpy.run_path(str(_ROOT / relative_path))


def _manifest(relative_path: str) -> DatasetManifest:
    """Load one frozen dataset manifest."""
    return DatasetManifest.model_validate_json(
        (_ROOT / relative_path).read_bytes()
    )


def _seeds(manifest: DatasetManifest) -> set[int]:
    """Return every independent image seed."""
    return {
        recipe.seed
        for dataset in manifest.datasets
        for recipe in iter_dataset_recipes(dataset)
    }


def test_post_correction_population_is_powered_and_globally_disjoint() -> None:
    """The approved 1,688/800 design freezes only unseen image seeds."""
    continuum = _manifest(
        "config/datasets/phase-5-external-post-correction-continuum.json"
    )
    compact = _manifest(
        "config/datasets/phase-5-external-post-correction-compact-blend.json"
    )
    continuum_seeds = _seeds(continuum)
    compact_seeds = _seeds(compact)

    assert len(continuum_seeds) == 1688
    assert len(compact_seeds) == 800
    assert continuum_seeds.isdisjoint(compact_seeds)
    historical: set[int] = set()
    for path in sorted((_ROOT / "config/datasets").glob("*.json")):
        if "post-correction" in path.name:
            continue
        seeds = _seeds(DatasetManifest.model_validate_json(path.read_bytes()))
        assert historical.isdisjoint(seeds)
        historical.update(seeds)
    assert historical.isdisjoint(continuum_seeds | compact_seeds)
    reserved_development = set(range(2026880001, 2026880201))
    for first_seed in (
        2026890001,
        2026891001,
        2026892001,
        2026893001,
    ):
        reserved_development.update(range(first_seed, first_seed + 20))
    assert reserved_development.isdisjoint(continuum_seeds | compact_seeds)


def test_post_correction_freeze_binds_approval_science_and_power() -> None:
    """The population contract retains the exact approved evidence."""
    helpers = _script(
        "scripts/validation/phase5_external_post_correction_protocol.py"
    )
    freeze = helpers["load_post_correction_population"](
        _ROOT
        / "config/contracts/phase-5-external-post-correction-population.json"
    )

    assert freeze["scientific_approval"] == {
        "reviewer": "Gemma Danks",
        "approved_on": "2026-08-16",
        "scope": (
            "candidate-and-powered-design-for-freezing-fresh-external-"
            "identities-only"
        ),
    }
    assert freeze["candidate"] == {
        "revision": "dfc3e25e635f4f6710558e483fa5a525ba904661",
        "source_tree_sha256": (
            "a549143b6475e75f7463c834e891c005a0660c2de9f4a0a3556c18bb9d39541d"
        ),
        "configuration_sha256": (
            "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
        ),
    }
    power = freeze["power_audit"]
    assert power["paired_comparison_count"] == 226
    assert power["minimum_continuum_realization_count"] == 1532
    assert power["selected_continuum_realization_count"] == 1688
    assert power["continuum_realizations_per_geometry"] == 422
    assert power["compact_realization_count"] == 800
    assert power["combined_familywise_power_lower_bound"] > 0.9
    assert freeze["execution_authorized"] is False


def test_post_correction_protocol_is_pending_and_exactly_scaled() -> None:
    """Corrected identities remain fail-closed pending renewed approval."""
    helpers = _script(
        "scripts/validation/phase5_external_post_correction_protocol.py"
    )
    protocol = helpers["load_post_correction_protocol"](
        _ROOT
        / "config/contracts/phase-5-external-post-correction-comparison.json"
    )
    decision = helpers["load_post_correction_execution_decision"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-correction-execution-decision.json"
    )

    assert tuple(item.image_count for item in protocol.populations) == (
        1688,
        800,
    )
    assert {
        item.finder_id: item.container_image_digest
        for item in protocol.references
    } == {
        "released-pybdsf": (
            "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198"
        ),
        "pinned-pybdsf-master": (
            "sha256:0e6d932416479bb7d7763fe2e025ea9fbbd0d0548a6f156b2cdd881766690c75"
        ),
        "aegean": (
            "sha256:dcac8e646ff5ea6d11d314c5c7a51fb0c3ca710165934ad2ddf0ac3f999131b0"
        ),
    }
    assert decision.execution_authorized is False
    assert decision.execution_concurrency == 2
    assert decision.pybdsf_ncores == 4
    assert decision.hebog_container_image_digest == (
        "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1"
    )
    assert decision.preflight_review_sha256 == "pending"
    assert decision.named_review == "pending"


def test_post_correction_review_binds_programs_and_four_runtimes() -> None:
    """The returned approval package is complete and result neutral."""
    helpers = _script(
        "scripts/validation/phase5_external_post_correction_protocol.py"
    )
    review = helpers["load_post_correction_preflight_review"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-correction-preflight-review.json"
    )

    assert review["status"] == "ready-for-named-execution-approval"
    assert review["execution_authorized"] is False
    assert review["scientific_products_opened"] is False
    assert review["population"] == {
        "binding_run_count": 8264,
        "compact_blend_image_count": 800,
        "continuum_image_count": 1688,
        "image_count": 2488,
        "terminal_run_count": 12440,
    }
    runtimes = {item["finder_id"]: item for item in review["runtime_images"]}
    assert set(runtimes) == {
        "hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
    }
    assert runtimes["hebog"]["source_tree_sha256"] == (
        "a549143b6475e75f7463c834e891c005a0660c2de9f4a0a3556c18bb9d39541d"
    )
    assert review["authorization"]["required_next_decision"] == (
        "named-one-look-approval-bound-to-this-review-and-four-runtimes"
    )
    assert review["storage"]["passed"] is True
    assert review["storage"]["observed_available_gib"] >= 126.0


def test_post_correction_compiler_and_evaluator_bind_powered_population() -> (
    None
):
    """Terminal composition retains the approved population and priors."""
    compiler = _script(
        "scripts/validation/compile_phase5_external_post_correction_campaign.py"
    )
    registry = compiler["load_post_correction_composition"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-correction-endpoint-registry.json",
        _ROOT / "scripts/validation/"
        "compile_phase5_external_post_correction_campaign.py",
    )
    evaluator = _script(
        "scripts/validation/evaluate_phase5_external_post_correction_decision.py"
    )
    contract = evaluator["load_post_correction_evaluation_contract"](
        _ROOT / "config/contracts/"
        "phase-5-external-post-correction-evaluation.json",
        _ROOT / "scripts/validation/"
        "evaluate_phase5_external_post_correction_decision.py",
    )

    assert registry["schema_version"] == 1
    assert contract["population"] == {
        "binding_run_count": 8264,
        "compact_blend_image_count": 800,
        "continuum_image_count": 1688,
        "image_count": 2488,
        "terminal_run_count": 12440,
    }
    assert len(contract["endpoint_power_priors"]) == 226


def test_post_correction_freezer_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frozen manifests cannot be regenerated over existing evidence."""
    namespace = _script(
        "scripts/validation/freeze_phase5_external_post_correction_population.py"
    )
    output = tmp_path / "continuum.json"
    output.write_text("already frozen\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "freeze_phase5_external_post_correction_population.py",
            "--continuum-output",
            str(output),
            "--compact-output",
            str(tmp_path / "compact.json"),
            "--freeze-output",
            str(tmp_path / "freeze.json"),
        ],
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        namespace["main"]()


def test_post_correction_review_json_is_canonical() -> None:
    """The approval package remains stable under strict JSON formatting."""
    path = (
        _ROOT / "config/contracts/"
        "phase-5-external-post-correction-preflight-review.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    expected = (
        json.dumps(
            document,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    assert path.read_text(encoding="utf-8") == expected
