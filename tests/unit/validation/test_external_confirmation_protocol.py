# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the fresh Phase 5 confirmation campaign."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest

from hebog.validation.datasets import DatasetManifest, iter_dataset_recipes

_ROOT = Path(__file__).parents[3]


def _script(relative_path: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    return runpy.run_path(str(_ROOT / relative_path))


def test_confirmation_loaders_bind_approved_powered_population() -> None:
    """The approved campaign exposes only 1,400 globally new images."""
    module = _script(
        "scripts/validation/phase5_external_confirmation_protocol.py"
    )
    protocol = module["load_confirmation_protocol"](
        _ROOT
        / "config/contracts/phase-5-external-confirmation-comparison.json"
    )
    decision = module["load_confirmation_execution_decision"](
        _ROOT / "config/contracts/"
        "phase-5-external-confirmation-execution-decision.json"
    )
    freeze = json.loads(
        (
            _ROOT
            / "config/contracts/phase-5-external-confirmation-population.json"
        ).read_text(encoding="utf-8")
    )

    assert tuple(item.image_count for item in protocol.populations) == (
        600,
        800,
    )
    assert decision.execution_authorized is True
    assert decision.execution_concurrency == 2
    assert decision.pybdsf_ncores == 4
    assert decision.preflight_review_sha256 == (
        "4d5cb1eb28f7d62d0982ec7ee109ff846741fdd199ab62c279ab7d39a6e848f2"
    )
    assert freeze["population_audit"]["seed_disjoint"] is True
    assert freeze["population_audit"]["historical_seed_count"] == 10453
    assert freeze["power_audit"]["combined_familywise_power_lower_bound"] > 0.9


def test_confirmation_seeds_are_disjoint_from_all_other_manifests() -> None:
    """Neither lane reuses predecessor or any earlier dataset seed."""
    confirmation: set[int] = set()
    historical: set[int] = set()
    for path in sorted((_ROOT / "config/datasets").glob("*.json")):
        manifest = DatasetManifest.model_validate_json(path.read_bytes())
        seeds = {
            recipe.seed
            for dataset in manifest.datasets
            for recipe in iter_dataset_recipes(dataset)
        }
        if manifest.manifest_id.startswith("phase-5-external-confirmation-"):
            assert not confirmation.intersection(seeds)
            confirmation.update(seeds)
        else:
            historical.update(seeds)

    assert len(confirmation) == 1400
    assert confirmation.isdisjoint(historical)


def test_confirmation_registry_binds_accelerated_composition() -> None:
    """Every prospective program and accelerator is checksum-bound."""
    module = _script(
        "scripts/validation/phase5_external_confirmation_protocol.py"
    )
    registry = module["load_confirmation_endpoint_registry"](
        _ROOT / "config/contracts/"
        "phase-5-external-confirmation-endpoint-registry.json"
    )

    assert registry["compiler_path"] == (
        "scripts/validation/compile_phase5_external_confirmation_campaign.py"
    )
    assert registry["launcher_path"] == (
        "scripts/benchmark/run_phase5_external_confirmation_campaign.py"
    )
    assert registry["compiler_accelerator_path"] == (
        "src/hebog/validation/external_campaign_compilation.py"
    )
    assert registry["expanded_continuum_counts"] == {
        "binding": 143,
        "report_only": 15,
        "total": 158,
    }


def test_confirmation_evaluation_inherits_every_gate() -> None:
    """The evaluator changes identities, not thresholds or failure policy."""
    module = _script(
        "scripts/validation/evaluate_phase5_external_confirmation_decision.py"
    )
    contract = module["load_confirmation_evaluation_contract"](
        _ROOT
        / "config/contracts/phase-5-external-confirmation-evaluation.json",
        _ROOT / "scripts/validation/"
        "evaluate_phase5_external_confirmation_decision.py",
    )

    assert contract["failure_policy"] == (
        "absolute-first-retain-denominator-incomplete-reference-fails-closed"
    )
    assert contract["population"] == {
        "binding_run_count": 5000,
        "compact_blend_image_count": 800,
        "continuum_image_count": 600,
        "image_count": 1400,
        "terminal_run_count": 7000,
    }
    assert contract["one_look_rule"] == (
        "one-terminal-look-no-tuning-rescoring-reconfirmation-or-adaptive-"
        "sample-size"
    )


def test_confirmation_launcher_rejects_pending_before_container_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Pending review cannot inspect an image or create private staging."""
    module = _script(
        "scripts/benchmark/run_phase5_external_confirmation_campaign.py"
    )

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("container inspection must remain closed")

    monkeypatch.setitem(
        module["_HELPERS"],
        "load_confirmation_execution_decision",
        lambda _path: SimpleNamespace(execution_authorized=False),
    )
    monkeypatch.setattr(module["_TERMINAL"]["subprocess"], "run", unexpected)

    with pytest.raises(ValueError, match="execution is not authorized"):
        module["preflight_confirmation_campaign"](
            repository_root=_ROOT,
            output=tmp_path / "campaign",
            images={
                "hebog": "unused",
                "released-pybdsf": "unused",
                "pinned-pybdsf-master": "unused",
                "aegean": "unused",
            },
        )
    assert not (tmp_path / "campaign").exists()


def test_confirmation_approval_requires_the_exact_preflight_review() -> None:
    """Named authorization cannot point at a changed or unmentioned review."""
    module = _script(
        "scripts/validation/phase5_external_confirmation_protocol.py"
    )
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-external-confirmation-preflight-review.json"
    )
    review_sha256 = module["file_sha256"](review_path)
    document = {
        "preflight_review_sha256": review_sha256,
        "named_review": f"Gemma Danks approved {review_sha256}",
    }

    assert (
        module["confirmation_preflight_review_sha256"](
            document,
            _ROOT,
            pending=False,
        )
        == review_sha256
    )
    with pytest.raises(ValueError, match="approved confirmation review"):
        module["confirmation_preflight_review_sha256"](
            {**document, "named_review": "review hash omitted"},
            _ROOT,
            pending=False,
        )
    with pytest.raises(ValueError, match="pending confirmation review"):
        module["confirmation_preflight_review_sha256"](
            document,
            _ROOT,
            pending=True,
        )


def test_confirmation_compiler_installs_bounded_accelerators() -> None:
    """Only the prospective compiler view receives the exact accelerators."""
    module = _script(
        "scripts/validation/compile_phase5_external_confirmation_campaign.py"
    )
    terminal = module["_configured_terminal"]()
    compiler_globals = terminal["compile_terminal_analysis"].__globals__

    assert type(
        compiler_globals["_continuum_image_observations"]
    ).__name__ == ("SharedContinuumImageCompiler")
    assert (
        compiler_globals["measure_continuum_image"]
        .__globals__["native_support_objects"]
        .__name__
        == "linear_native_support_objects"
    )
    assert get_args(
        compiler_globals["CampaignRequest"]
        .model_fields["execution_concurrency"]
        .annotation
    ) == (2,)


def test_confirmation_historical_programs_remain_immutable() -> None:
    """The new composition cannot rewrite any closed campaign authority."""
    expected = {
        "scripts/benchmark/run_phase5_external_campaign.py": (
            "9eb832e96c862327467ae700db8e7b59165f14f05c823f1783ccf696ecd2125c"
        ),
        "scripts/benchmark/run_phase5_external_successor_campaign.py": (
            "3490f920d4d3c5420b8e14bcc7baaeb0a826e821fce7ca3ac022729e8172c5c6"
        ),
        "scripts/validation/compile_phase5_external_campaign.py": (
            "7a0558916ac003b71a781337dc710c99c359899c4d77f88486c1c206916b43f6"
        ),
        "scripts/validation/compile_phase5_external_successor_campaign.py": (
            "2fd78b605a293165adf3df041074cae6e12144a7240dcdd915011ce45e9a77a2"
        ),
    }
    module = _script(
        "scripts/validation/phase5_external_confirmation_protocol.py"
    )

    assert {
        path: module["file_sha256"](_ROOT / path) for path in expected
    } == expected


def test_confirmation_runtime_probe_preserves_exact_resource_lanes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The non-scientific probe exercises only the reviewed CPU pairings."""
    module = _script(
        "scripts/validation/preflight_phase5_external_confirmation_runtime.py"
    )
    observed: list[tuple[str, int]] = []

    def probe_command(
        _podman: str,
        image: str,
        *,
        cpu_count: int,
    ) -> tuple[str, ...]:
        observed.append((image, cpu_count))
        return (image, str(cpu_count))

    def probe_run(finder_id: str, _command: tuple[str, ...]) -> object:
        return module["Probe"](finder_id, 1.0, "0" * 64)

    globals_ = module["run_matrix"].__globals__
    monkeypatch.setitem(globals_, "_command", probe_command)
    monkeypatch.setitem(globals_, "_run", probe_run)

    result = module["run_matrix"](
        {
            "hebog": "hebog-image",
            "released-pybdsf": "release-image",
            "pinned-pybdsf-master": "master-image",
            "aegean": "aegean-image",
        },
        podman="podman",
    )

    assert result["status"] == ("pass-non-scientific-two-lane-resource-probe")
    assert result["scientific_evidence"] is False
    assert {item for item in observed if item[1] == 4} == {
        ("release-image", 4),
        ("master-image", 4),
    }
    assert {item for item in observed if item[1] == 1} == {
        ("hebog-image", 1),
        ("aegean-image", 1),
    }
