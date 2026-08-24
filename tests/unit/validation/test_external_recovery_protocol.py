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
_RECOVERY_REVIEW_SHA256 = (
    "8aaaca742f782f94cbcccbcc53a0a396459ccc5902e46c519a675933a79d6c63"
)


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


def test_frozen_recovery_chain_is_exact_and_authorized() -> None:
    """Named approval authorizes only the exact unopened one-look."""
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
    assert decision.execution_authorized is True
    assert decision.identity_review_sha256 == _RECOVERY_REVIEW_SHA256
    assert decision.named_review == (
        "Gemma Danks, 2026-08-22, approved corrected Phase 5 recovery "
        "one-look execution bound to identity review sha256:"
        f"{_RECOVERY_REVIEW_SHA256} and its unchanged exact four runtime "
        "identities"
    )
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
    assert (
        hashlib.sha256(review_path.read_bytes()).hexdigest()
        == _RECOVERY_REVIEW_SHA256
    )


def test_recovery_verifier_accepts_exact_named_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frozen verifier can transition without changing its own identity."""
    helpers = _script(
        "scripts/validation/phase5_external_recovery_protocol.py"
    )
    decision_path = (
        _ROOT
        / "config/contracts/phase-5-external-recovery-execution-decision.json"
    )
    document = json.loads(decision_path.read_text(encoding="utf-8"))
    review_sha256 = _RECOVERY_REVIEW_SHA256
    named_review = (
        "Gemma Danks, 2026-08-22, approved Phase 5 recovery one-look "
        f"execution bound to identity review sha256:{review_sha256} and its "
        "exact four runtime identities"
    )
    document.update(
        {
            "decision": "authorize-one-terminal-recovery-comparison",
            "execution_authorized": True,
            "identity_review_sha256": review_sha256,
            "named_review": named_review,
            "next_action": (
                "run-complete-no-write-preflight-before-terminal-execution"
            ),
            "status": "reviewed-before-external-output",
        }
    )
    temporary_decision = (
        tmp_path
        / "config/contracts/phase-5-external-recovery-execution-decision.json"
    )
    temporary_decision.parent.mkdir(parents=True)
    temporary_decision.write_text(json.dumps(document), encoding="utf-8")
    expected_hashes = {
        document["identity_review_path"]: review_sha256,
        "config/contracts/phase-5-external-recovery-comparison.json": (
            document["protocol_sha256"]
        ),
        **{
            item["relative_path"]: item["sha256"]
            for item in document["runners"]
        },
    }

    def frozen_sha256(path: Path) -> str:
        return expected_hashes[str(path.relative_to(tmp_path))]

    loader = helpers["load_recovery_execution_decision"]
    monkeypatch.setitem(loader.__globals__, "file_sha256", frozen_sha256)

    def approved_review(_path: Path) -> dict[str, str]:
        return {"status": "ready-for-named-execution-approval"}

    monkeypatch.setitem(
        loader.__globals__,
        "load_recovery_identity_review",
        approved_review,
    )

    decision = loader(temporary_decision)

    assert decision.execution_authorized is True
    assert decision.identity_review_sha256 == review_sha256
    assert decision.named_review == named_review


def test_recovery_review_preserves_pre_authorization_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval changes only the three authorization-dependent artifacts."""
    helpers = _script(
        "scripts/validation/phase5_external_recovery_protocol.py"
    )
    review_path = (
        _ROOT
        / "config/contracts/phase-5-external-recovery-identity-review.json"
    )
    decision_path = (
        _ROOT
        / "config/contracts/phase-5-external-recovery-execution-decision.json"
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["status"] = "reviewed-before-external-output"
    temporary_review = tmp_path / review_path.relative_to(_ROOT)
    temporary_decision = tmp_path / decision_path.relative_to(_ROOT)
    temporary_review.parent.mkdir(parents=True)
    temporary_review.write_text(json.dumps(review), encoding="utf-8")
    temporary_decision.write_text(json.dumps(decision), encoding="utf-8")
    frozen = {
        item["relative_path"]: item["sha256"]
        for item in review["identity_artifacts"]
    }
    authorization_dependent = {
        "config/contracts/phase-5-external-recovery-execution-decision.json",
        "config/contracts/phase-5-external-recovery-endpoint-registry.json",
        "config/contracts/phase-5-external-recovery-evaluation.json",
    }

    def frozen_sha256(path: Path) -> str:
        relative = str(path.relative_to(tmp_path))
        assert relative not in authorization_dependent
        return frozen[relative]

    loader = helpers["load_recovery_identity_review"]
    monkeypatch.setitem(loader.__globals__, "file_sha256", frozen_sha256)

    loaded = loader(temporary_review)

    assert loaded["review_id"] == review["review_id"]


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


def test_recovery_podman_wrapper_exposes_only_approved_hebog_source() -> None:
    """The resume amendment changes only the failed Hebog invocation."""
    wrapper = _script(
        "scripts/benchmark/run_phase5_external_recovery_podman.py"
    )
    image = (
        "sha256:e519dc15b846dec7ac00a6cada7684d0"
        "c0b2615490dd6688ac4c6cdf5f3021ca"
    )
    runner = (
        "/repository/scripts/benchmark/run_phase5_external_recovery_hebog.py"
    )
    base = (
        "run",
        "--rm",
        "--network=none",
        "--entrypoint",
        "python3",
        image,
        runner,
    )

    assert wrapper["amend_podman_arguments"](base) == (
        *base[:-2],
        "--env",
        "PYTHONPATH=/repository/src",
        *base[-2:],
    )
    assert wrapper["amend_podman_arguments"](
        (*base[:-1], "/repository/scripts/materialize.py")
    ) == (*base[:-1], "/repository/scripts/materialize.py")
    assert wrapper["amend_podman_arguments"](
        (*base[:-2], "sha256:" + "4" * 64, runner)
    ) == (*base[:-2], "sha256:" + "4" * 64, runner)
    assert wrapper["amend_podman_arguments"](("image", "inspect", image)) == (
        "image",
        "inspect",
        image,
    )
    with pytest.raises(
        ValueError,
        match="recovery source environment is ambiguous",
    ):
        wrapper["amend_podman_arguments"](
            (
                *base[:-2],
                "--env",
                "PYTHONPATH=/unexpected",
                *base[-2:],
            )
        )


def test_existing_campaign_resume_review_binds_exact_pending_amendment() -> (
    None
):
    """The source-path repair cannot authorize itself or drift science."""
    review_path = (
        _ROOT / "config/contracts/phase-5-external-recovery-resume-review.json"
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    delegate_path = _ROOT / review["correction"]["delegate_path"]

    assert review["status"] == (
        "ready-for-named-existing-campaign-resume-approval"
    )
    assert review["authorization"]["execution_authorized"] is False
    assert review["authorization"]["named_review"] is None
    assert review["existing_campaign"] == {
        "completed_hebog_result_count": 0,
        "completed_result_count": 1,
        "execution_decision_sha256": (
            "7a44ba52eb3e5daac1c40a234e80f422608e81d379587e06239c591c265f7e50"
        ),
        "input_count": 2488,
        "open_state_sha256": (
            "f322a07ca3c33697e9d72990ad45f0a53d74c7648975e6fdb34a44b6be09eb99"
        ),
        "public_terminal_manifest": "absent",
        "request_sha256": (
            "4c53dc39a7f02673a7c316cb814d8947f161eb417f192b077c1aa8b241093230"
        ),
        "run_count": 12440,
        "staging_directory": (
            "benchmark-results/phase-5/.external-recovery-comparison."
            "phase5-external-7a44ba52eb3e.staging"
        ),
        "terminal_directory": (
            "benchmark-results/phase-5/external-recovery-comparison"
        ),
    }
    assert review["failure"]["candidate_execution_started"] is False
    assert review["frozen_science"] == {
        "candidate_revision": "c184acf7f55f936442285835b4601a6ac193fe2a",
        "candidate_source_tree_sha256": (
            "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
        ),
        "configuration_sha256": (
            "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
        ),
        "inputs_changed": False,
        "population_changed": False,
        "runtime_images_changed": False,
        "science_or_gates_changed": False,
    }
    assert (
        hashlib.sha256(delegate_path.read_bytes()).hexdigest()
        == (review["correction"]["delegate_sha256"])
    )


def test_existing_campaign_resume_decision_binds_exact_approval() -> None:
    """Named approval permits only the preserved campaign to resume."""
    decision = json.loads(
        (
            _ROOT
            / "config/contracts/phase-5-external-recovery-resume-decision.json"
        ).read_text(encoding="utf-8")
    )
    review_path = _ROOT / decision["resume_review"]["path"]
    delegate_path = _ROOT / decision["delegate"]["path"]

    assert hashlib.sha256(review_path.read_bytes()).hexdigest() == (
        "a8d30ee956567af0688d8d66cff9058ba57bad8b7be66cee39c5049a88cbc95a"
    )
    assert decision["resume_review"]["sha256"] == (
        "a8d30ee956567af0688d8d66cff9058ba57bad8b7be66cee39c5049a88cbc95a"
    )
    assert decision["status"] == "reviewed-before-existing-campaign-resume"
    assert decision["execution_authorized"] is True
    assert decision["second_campaign_authorized"] is False
    assert decision["scientific_changes_authorized"] is False
    assert decision["delegate"]["commit"] == (
        "c88e7c25a95a665773d1ec0f46a1842cbd3b3356"
    )
    assert (
        hashlib.sha256(delegate_path.read_bytes()).hexdigest()
        == (decision["delegate"]["sha256"])
    )
    assert decision["existing_campaign"]["request_sha256"] == (
        "4c53dc39a7f02673a7c316cb814d8947f161eb417f192b077c1aa8b241093230"
    )
    assert decision["existing_campaign"]["remaining_run_count"] == 12439
    assert decision["named_review"]["reviewer"] == "Gemma Danks"
    assert (
        "does not authorize a second campaign"
        in (decision["named_review"]["approval"])
    )


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


def test_recovery_evaluation_amendment_preserves_both_accelerators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The amendment keeps recovery provenance and base compatibility."""
    amendment = _script(
        "scripts/validation/evaluate_phase5_external_recovery_amendment.py"
    )
    recovery_accelerator = {"sha256": "recovery-seam"}
    inherited_accelerator = {"sha256": "recorded-base-accelerator"}
    contract = {"compiler_accelerator": recovery_accelerator}
    observed: dict[str, Any] = {}

    def evaluate(
        analysis: dict[str, Any],
        compatible_contract: dict[str, Any],
        registry: dict[str, Any],
    ) -> tuple[str, tuple[()], str]:
        observed["analysis"] = analysis
        observed["contract"] = compatible_contract
        observed["registry"] = registry
        return "combined", (), "compact"

    monkeypatch.setitem(
        amendment["evaluate_amended_recovery_analysis"].__globals__,
        "_BASE_EVALUATE",
        evaluate,
    )
    result = amendment["evaluate_amended_recovery_analysis"](
        {
            "analysis_id": "phase-5-external-recovery-terminal-science",
            "compiler_accelerator_sha256": "recorded-base-accelerator",
        },
        contract,
        {"registry": "unchanged"},
        inherited_accelerator,
    )

    assert result == ("combined", (), "compact")
    assert observed["analysis"]["analysis_id"] == (
        "phase-5-external-post-correction-terminal-science"
    )
    assert observed["contract"]["compiler_accelerator"] == (
        inherited_accelerator
    )
    assert observed["registry"] == {"registry": "unchanged"}
    assert contract["compiler_accelerator"] == recovery_accelerator

    with pytest.raises(
        ValueError,
        match="analysis compiler accelerator differs from inherited identity",
    ):
        amendment["evaluate_amended_recovery_analysis"](
            {
                "analysis_id": "phase-5-external-recovery-terminal-science",
                "compiler_accelerator_sha256": "different",
            },
            contract,
            {},
            inherited_accelerator,
        )


def test_recovery_evaluation_amendment_requires_exact_authorization(
    tmp_path: Path,
) -> None:
    """The amended evaluator cannot authorize itself or another campaign."""
    amendment = _script(
        "scripts/validation/evaluate_phase5_external_recovery_amendment.py"
    )
    identities: dict[str, dict[str, str]] = {}
    analysis_relative = (
        "benchmark-results/phase-5/external-recovery-analysis.json"
    )
    paths = {
        "amendment_review": (
            "config/contracts/"
            "phase-5-external-recovery-evaluation-amendment-review.json"
        ),
        "analysis": analysis_relative,
        "evaluator": (
            "scripts/validation/evaluate_phase5_external_recovery_amendment.py"
        ),
        "frozen_contract": (
            "config/contracts/phase-5-external-recovery-evaluation.json"
        ),
        "frozen_evaluator": (
            "scripts/validation/evaluate_phase5_external_recovery_decision.py"
        ),
    }
    for key, relative in paths.items():
        artifact = tmp_path / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"{key}\n", encoding="utf-8")
        identities[key] = {
            "path": relative,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    review_sha256 = identities["amendment_review"]["sha256"]
    authorization = {
        "amendment_review": identities["amendment_review"],
        "analysis": identities["analysis"],
        "analysis_recompilation_authorized": False,
        "campaign_reexecution_authorized": False,
        "decision_id": (
            "phase-5-external-recovery-evaluation-amendment-decision"
        ),
        "evaluator": identities["evaluator"],
        "execution_authorized": True,
        "frozen_contract": identities["frozen_contract"],
        "frozen_evaluator": identities["frozen_evaluator"],
        "named_review": {
            "approval": f"I approve review {review_sha256}",
            "reviewer": "Gemma Danks",
        },
        "output_path": (
            "benchmark-results/phase-5/external-recovery-decision.json"
        ),
        "schema_version": 1,
        "science_or_gates_changed": False,
        "status": "reviewed-before-recovery-evaluation-amendment",
    }
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(authorization),
        encoding="utf-8",
    )

    loaded = amendment["load_amendment_authorization"](
        authorization_path,
        tmp_path / paths["evaluator"],
        tmp_path,
    )

    assert loaded == authorization
    authorization["campaign_reexecution_authorized"] = True
    authorization_path.write_text(
        json.dumps(authorization),
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="evaluation amendment is not exactly authorized",
    ):
        amendment["load_amendment_authorization"](
            authorization_path,
            tmp_path / paths["evaluator"],
            tmp_path,
        )


def test_recovery_launcher_accepts_exact_authorized_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approved launcher reaches unchanged campaign mechanics."""
    launcher = _script(
        "scripts/benchmark/run_phase5_external_recovery_campaign.py"
    )
    output = tmp_path / "campaign"
    observed: dict[str, Any] = {}

    def configured(registry_path: Path) -> dict[str, Any]:
        observed["registry_path"] = registry_path

        def run(arguments: object) -> None:
            observed["arguments"] = arguments

        return {"_run": run}

    main_globals = launcher["main"].__globals__
    monkeypatch.setitem(
        main_globals,
        "_configure_terminal_launcher",
        configured,
    )

    def arguments(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    monkeypatch.setitem(
        main_globals,
        "_arguments",
        arguments,
    )
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

    launcher["main"]()

    arguments = observed["arguments"]
    assert isinstance(arguments, dict)
    assert arguments["output"] == output
    assert arguments["images"] == {
        "hebog": "hebog",
        "released-pybdsf": "released",
        "pinned-pybdsf-master": "master",
        "aegean": "aegean",
    }
    assert not output.exists()
