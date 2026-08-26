"""Contracts for the unopened final Phase 5 qualification composition."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from pydantic import BaseModel

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_PROTOCOL_SCRIPT = (
    _ROOT / "scripts/validation/phase5_final_qualification_protocol.py"
)


def _helpers() -> dict[str, Any]:
    """Load the final qualification protocol boundary."""
    return runpy.run_path(str(_PROTOCOL_SCRIPT))


def test_final_qualification_protocol_binds_only_unopened_continuum() -> None:
    """The final one-look has one fresh lane and no new compact run."""
    helpers = _helpers()
    population = helpers["load_final_qualification_population"](
        _ROOT / "config/contracts/phase-5-final-qualification-population.json"
    )
    protocol = helpers["load_final_qualification_protocol"](
        _ROOT / "config/contracts/phase-5-final-qualification-comparison.json"
    )

    assert population["population"]["image_count"] == 1688
    assert (
        population["compact_evidence"]["fresh_compact_lane_required"] is False
    )
    assert [
        (item.lane, item.image_count) for item in protocol.populations
    ] == [("continuum", 1688)]
    assert protocol.execution_authorized is False
    assert protocol.qualification_opened is False


def test_final_qualification_approved_decision_binds_four_runtimes() -> None:
    """Named approval binds the unchanged exact runtime review."""
    helpers = _helpers()
    decision = helpers["load_final_qualification_execution_decision"](
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-execution-decision.json"
    )
    review = helpers["load_final_qualification_identity_review"](
        _ROOT
        / "config/contracts/phase-5-final-qualification-identity-review.json"
    )

    assert decision.execution_authorized is True
    assert decision.identity_review_sha256 == (
        "42ad623779c381ae69532af1cdc3e9063f7229154f28209e2c1da36199280197"
    )
    assert decision.qualification_opened is False
    assert decision.pybdsf_ncores == 4
    assert decision.execution_concurrency == 2
    assert [item["finder_id"] for item in review["runtime_images"]] == [
        "hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
    ]
    assert review["population"] == {
        "binding_run_count": 5064,
        "continuum_image_count": 1688,
        "image_count": 1688,
        "terminal_run_count": 8440,
    }
    assert review["execution_authorized"] is False
    assert len(review["identity_artifacts"]) == 16
    assert (
        file_sha256(
            _ROOT / "config/contracts/"
            "phase-5-final-qualification-identity-review.json"
        )
        == "42ad623779c381ae69532af1cdc3e9063f7229154f28209e2c1da36199280197"
    )


def test_final_qualification_models_replace_only_population_literals() -> None:
    """The generic request/result shapes admit only 1,688 and 8,440."""
    helpers = _helpers()

    class HistoricalModel(BaseModel):
        image_count: int
        run_count: int

    model = helpers["final_qualification_campaign_model"](HistoricalModel)
    assert model(image_count=1688, run_count=8440).image_count == 1688
    with pytest.raises(ValueError):
        model(image_count=2488, run_count=12440)


def test_final_qualification_verifier_accepts_exact_named_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an approval bound to the frozen review can open preflight."""
    helpers = _helpers()
    source = (
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-execution-decision.json"
    )
    document = json.loads(source.read_text(encoding="utf-8"))
    review_sha256 = "a" * 64
    named_review = (
        "Gemma Danks approved final Phase 5 qualification one-look execution "
        f"bound to identity review sha256:{review_sha256} and its exact four "
        "runtime identities"
    )
    document.update(
        {
            "decision": "authorize-one-terminal-final-qualification",
            "execution_authorized": True,
            "identity_review_sha256": review_sha256,
            "named_review": named_review,
            "next_action": (
                "run-complete-no-write-preflight-before-terminal-execution"
            ),
            "status": "reviewed-before-qualification-output",
        }
    )
    target = tmp_path / source.relative_to(_ROOT)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(document), encoding="utf-8")
    hashes = {
        document["identity_review_path"]: review_sha256,
        "config/contracts/phase-5-final-qualification-comparison.json": (
            document["protocol_sha256"]
        ),
        **{
            item["relative_path"]: item["sha256"]
            for item in document["runners"]
        },
    }

    def frozen_sha256(path: Path) -> str:
        return hashes[str(path.relative_to(tmp_path))]

    loader = helpers["load_final_qualification_execution_decision"]
    monkeypatch.setitem(loader.__globals__, "file_sha256", frozen_sha256)

    def approved_review(_path: Path) -> dict[str, str]:
        return {"status": "ready-for-named-execution-approval"}

    monkeypatch.setitem(
        loader.__globals__,
        "load_final_qualification_identity_review",
        approved_review,
    )
    decision = loader(target)
    assert decision.execution_authorized is True
    assert decision.identity_review_sha256 == review_sha256
    assert decision.named_review == named_review


def test_final_qualification_registry_binds_program_composition() -> None:
    """The runner, compiler, evaluator, and candidate seam are immutable."""
    helpers = _helpers()
    registry_path = (
        _ROOT
        / "config/contracts/phase-5-final-qualification-endpoint-registry.json"
    )
    registry = helpers["load_final_qualification_endpoint_registry"](
        registry_path
    )

    assert registry["continuum_manifest_sha256"] == (
        "7c67127e828a92bc100299cf9ffecd13851e485c4be9e95866e2d0827ebb80df"
    )
    assert registry["closed_compact_evidence_only"] is True
    for path_key, sha_key in (
        ("launcher_path", "launcher_sha256"),
        ("compiler_path", "compiler_sha256"),
        ("protocol_verifier_path", "protocol_verifier_sha256"),
        ("compiler_accelerator_path", "compiler_accelerator_sha256"),
        ("candidate_adapter_path", "candidate_adapter_sha256"),
    ):
        assert (
            file_sha256(_ROOT / cast(str, registry[path_key]))
            == registry[sha_key]
        )


def test_final_qualification_programs_load_without_opening_science(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approved preflight delegates once without opening science in-unit."""
    compiler = runpy.run_path(
        str(
            _ROOT / "scripts/validation/"
            "compile_phase5_final_qualification_campaign.py"
        )
    )
    registry_path = (
        _ROOT
        / "config/contracts/phase-5-final-qualification-endpoint-registry.json"
    )
    registry = compiler["load_final_qualification_composition"](
        registry_path,
        _ROOT
        / "scripts/validation/compile_phase5_final_qualification_campaign.py",
    )
    assert registry["closed_compact_evidence_only"] is True
    assert compiler["_closed_compact_evidence"]()["status"] == "pass"

    evaluator = runpy.run_path(
        str(
            _ROOT / "scripts/validation/"
            "evaluate_phase5_final_qualification_decision.py"
        )
    )
    contract = evaluator["load_final_qualification_evaluation_contract"](
        _ROOT / "config/contracts/phase-5-final-qualification-evaluation.json",
        _ROOT / "scripts/validation/"
        "evaluate_phase5_final_qualification_decision.py",
    )
    assert contract["population"] == {
        "binding_run_count": 5064,
        "compact_blend_image_count": 0,
        "continuum_image_count": 1688,
        "image_count": 1688,
        "terminal_run_count": 8440,
    }
    assert len(contract["endpoint_power_priors"]) == 226

    launcher = runpy.run_path(
        str(
            _ROOT
            / "scripts/benchmark/run_phase5_final_qualification_campaign.py"
        )
    )
    terminal = launcher["_configure_terminal_launcher"](registry_path)
    request_model = terminal["_run"].__globals__["CampaignRequest"]
    assert (
        request_model.model_fields["image_count"].annotation == Literal[1688]
    )
    assert request_model.model_fields["run_count"].annotation == Literal[8440]
    assert (
        request_model.model_fields["execution_concurrency"].annotation
        == Literal[2]
    )
    observed: list[Any] = []

    def run_preflight(arguments: Any) -> None:
        observed.append(arguments)

    def configured_preflight(_path: Path) -> dict[str, Any]:
        return {"_run": run_preflight}

    preflight = launcher["preflight_final_qualification"]
    monkeypatch.setitem(
        preflight.__globals__,
        "_configure_terminal_launcher",
        configured_preflight,
    )
    preflight(
        repository_root=_ROOT,
        output=tmp_path / "must-not-exist",
        images={
            "hebog": "unused",
            "released-pybdsf": "unused",
            "pinned-pybdsf-master": "unused",
            "aegean": "unused",
        },
    )
    assert len(observed) == 1
    assert observed[0].preflight_only is True
    assert observed[0].resume is False
    assert not (tmp_path / "must-not-exist").exists()


def test_final_qualification_evaluation_repair_pre_review_is_closed() -> None:
    """The repair proposal binds failure evidence but authorizes no action."""
    path = (
        _ROOT / "config/contracts/"
        "phase-5-final-qualification-evaluation-repair-pre-review.json"
    )
    review = json.loads(path.read_text(encoding="utf-8"))

    assert review["review_id"] == (
        "phase-5-final-qualification-evaluation-repair-pre-review"
    )
    assert review["status"] == ("ready-for-named-repair-implementation-review")
    assert review["authorization_boundary"] == {
        "campaign_reexecution_authorized": False,
        "compilation_authorized": False,
        "evaluation_authorized": False,
        "implementation_authorized": False,
        "named_review": None,
        "optimization_authorized": False,
        "requested_scope": (
            "implement-evaluation-only-repair-and-freeze-exact-identities-"
            "no-science-access"
        ),
        "rescoring_authorized": False,
        "tuning_authorized": False,
    }
    assert review["evidence"] == {
        "campaign": {
            "image_count": 1688,
            "path": (
                "benchmark-results/phase-5/"
                "final-qualification-comparison/campaign.json"
            ),
            "request_sha256": (
                "eebb6d793b0ee4532db2393bf06468df53dbc9521092cc8fb6e2340be7194726"
            ),
            "run_count": 8440,
            "sha256": (
                "4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08"
            ),
            "status": "terminal-raw-results-sealed",
        },
        "outputs": {
            "analysis_path": (
                "benchmark-results/phase-5/final-qualification-analysis.json"
            ),
            "analysis_state": "absent",
            "decision_path": (
                "benchmark-results/phase-5/final-qualification-decision.json"
            ),
            "decision_state": "absent",
        },
    }
    assert review["failure"]["scientific_products_read"] is False
    assert review["failure"]["write_once_output_created"] is False
    assert set(review["scientific_scope"].values()) == {False}
    for identity in review["frozen_composition"].values():
        if "path" not in identity:
            continue
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]
