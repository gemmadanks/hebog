# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Prospective Phase 5 scientific smoke-lane tests."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.validation import parent_construction_association_evaluation
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_runners import file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpoint,
    ProspectiveEndpointCounts,
    ProspectiveEndpointRegistry,
)
from hebog.validation.prospective_science_smoke import (
    evaluate_prospective_science_smoke,
    select_prospective_smoke_inputs,
)
from hebog.validation.source_association_evaluation_repair import (
    associated_source_identifier,
    detection_component_identifier,
)

_ROOT = Path(__file__).parents[3]
_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_POPULATION = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-smoke-population.json"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
)
_EVALUATION_REPAIR_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-mask-measurement-evaluation-"
    "repair-implementation-decision.json"
)
_MEASUREMENT_PERSISTENCE_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-measurement-label-"
    "persistence-implementation-decision.json"
)
_MEASUREMENT_PERSISTENCE_EVALUATION_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-measurement-label-"
    "persistence-evaluation-decision.json"
)
_MIXED_SCHEMA_REPAIR_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-prospective-measurement-label-mixed-"
    "schema-evaluation-repair-pre-review.json"
)
_MIXED_SCHEMA_REPAIR_DECISION = (
    _ROOT / "config/contracts/phase-5-prospective-measurement-label-mixed-"
    "schema-evaluation-repair-implementation-decision.json"
)


def _mask_separated_case() -> tuple[
    tuple[CatalogueSource, ...], SourceAssociationResult
]:
    component_id = detection_component_identifier((2, 3))
    source_id = associated_source_identifier((component_id,))
    source = CatalogueSource(
        identifier=source_id,
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=2.0,
        association_integrated_flux_jy=2.0,
        island_identifier=source_id,
        component_count=1,
    )
    association = SourceAssociationResult(
        components=(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=7,
                canonical_pixel_yx=(2, 3),
                centroid_yx=(2.0, 3.0),
                covariance_pixels_squared=None,
            ),
        ),
        edges=(),
        memberships=(
            CatalogueSourceMembership(
                source_id=source_id,
                component_ids=(component_id,),
            ),
        ),
    )
    return (source,), association


def _registry() -> ProspectiveEndpointRegistry:
    endpoint = ProspectiveEndpoint(
        endpoint_id="continuum--reliability--overall",
        lane="continuum",
        metric_family="reliability",
        stratum="overall",
        role="binding",
        desirable_direction="higher-is-better",
        unit="fraction",
        population="accepted catalogue sources",
        statistic="rate",
        value_kind="scalar",
        comparators=("incumbent-hebog", "released-pybdsf"),
        practical_regression_margins={
            "incumbent-hebog": 0.02,
            "released-pybdsf": 0.02,
        },
        cross_finder_applicability="all-listed-comparators-binding",
        missing_output_outcome=(
            "candidate-fail-comparator-underpowered-global-fail"
        ),
        absolute_policy="report-not-compatibility-blocker",
    )
    # Construct without the full-registry cardinality validator for a focused
    # evaluator unit test. The frozen production registry has separate tests.
    return ProspectiveEndpointRegistry.model_construct(
        schema_version=1,
        registry_id="phase-5-prospective-science-endpoint-registry",
        status="frozen-before-candidate-results",
        source_bindings=(),
        counts=ProspectiveEndpointCounts(
            total_endpoints=1,
            compact_binding_endpoints=0,
            continuum_binding_endpoints=1,
            continuum_objective_endpoints=0,
            pybdsf_endpoints_per_reference=1,
            aegean_endpoints=0,
            incumbent_retention_endpoints=1,
            total_coprimary_comparisons=2,
        ),
        endpoints=(endpoint,),
    )


def _endpoint(reference_id: str, upper: float) -> SimpleNamespace:
    comparison = SimpleNamespace(
        reference_id=reference_id,
        status="success",
        positive_regression=0.005,
        upper_confidence_limit=upper,
        observed_paired_standard_deviation=0.03,
    )
    return SimpleNamespace(
        endpoint_id="continuum--reliability--overall",
        candidate_status="success",
        comparisons=(comparison,),
    )


def test_frozen_smoke_selection_is_reproducible_and_balanced() -> None:
    """The result-neutral rule resolves the exact same 128 inputs."""
    selected = select_prospective_smoke_inputs(
        _REQUEST,
        _POPULATION,
    )

    assert len(selected) == 128
    assert len({item for item in selected if "compact-blend" in item}) == 64
    continuum = [item for item in selected if "continuum" in item]
    assert len(continuum) == 64
    assert {
        dataset: sum(dataset in item for item in continuum)
        for dataset in (
            "continuum-1",
            "continuum-2",
            "continuum-3",
            "continuum-4",
        )
    } == {
        "continuum-1": 16,
        "continuum-2": 16,
        "continuum-3": 16,
        "continuum-4": 16,
    }


def test_smoke_passes_with_activation_identity_and_no_confirmed_loss() -> None:
    """Underpowered diagnostics may continue; failures may not."""
    record = evaluate_prospective_science_smoke(
        registry=_registry(),
        current_continuum=(_endpoint("released-pybdsf", 0.025),),
        incumbent_paired_continuum=(_endpoint("pinned-pybdsf-master", 0.015),),
        planning_deviation_by_family={"reliability": 0.08},
        compact_product_identity_equal=True,
        terminal_cycle_aggregate={
            "terminal_cycle_unseeded_persistent_accepted_count": 2
        },
    )

    assert record["status"] == "pass"
    assert record["promotion_evidence"] is False
    assert record["continuum_status_counts"] == {
        "pass": 1,
        "underpowered": 1,
    }


def test_smoke_fails_on_confirmed_regression_or_absent_activation() -> None:
    """Material regression and a dormant correction both stop a replay."""
    record = evaluate_prospective_science_smoke(
        registry=_registry(),
        current_continuum=(_endpoint("released-pybdsf", 0.03),),
        incumbent_paired_continuum=(
            SimpleNamespace(
                endpoint_id="continuum--reliability--overall",
                candidate_status="success",
                comparisons=(
                    SimpleNamespace(
                        reference_id="pinned-pybdsf-master",
                        status="success",
                        positive_regression=0.03,
                        upper_confidence_limit=0.04,
                        observed_paired_standard_deviation=0.03,
                    ),
                ),
            ),
        ),
        planning_deviation_by_family={"reliability": 0.08},
        compact_product_identity_equal=True,
        terminal_cycle_aggregate={
            "terminal_cycle_unseeded_persistent_accepted_count": 0
        },
    )

    assert record["status"] == "fail"
    assert record["terminal_failure_count"] == 1


@pytest.mark.parametrize(
    ("population_value", "message"),
    [
        ([], "population is malformed"),
        ({}, "selection is incomplete"),
    ],
)
def test_smoke_selector_rejects_malformed_population(
    tmp_path: Path, population_value: object, message: str
) -> None:
    """Malformed population metadata fails before any result selection."""
    population = tmp_path / "population.json"
    population.write_text(json.dumps(population_value), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        select_prospective_smoke_inputs(_REQUEST, population)


def test_smoke_selector_rejects_request_or_count_drift(tmp_path: Path) -> None:
    """Source bytes, sample sizes, and selected identities remain frozen."""
    population = json.loads(_POPULATION.read_text(encoding="utf-8"))
    population["source_request"]["sha256"] = "changed"
    changed_source = tmp_path / "changed-source.json"
    changed_source.write_text(json.dumps(population), encoding="utf-8")
    with pytest.raises(ValueError, match="source request changed"):
        select_prospective_smoke_inputs(_REQUEST, changed_source)

    population = json.loads(_POPULATION.read_text(encoding="utf-8"))
    population["selection"]["compact_count"] = 0
    changed_count = tmp_path / "changed-count.json"
    changed_count.write_text(json.dumps(population), encoding="utf-8")
    with pytest.raises(ValueError, match="selection count is invalid"):
        select_prospective_smoke_inputs(_REQUEST, changed_count)

    population["selection"]["compact_count"] = 64
    population["selection"]["selected_input_count"] = 127
    changed_set = tmp_path / "changed-set.json"
    changed_set.write_text(json.dumps(population), encoding="utf-8")
    with pytest.raises(ValueError, match="selected input set changed"):
        select_prospective_smoke_inputs(_REQUEST, changed_set)


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (None, "source inputs are absent"),
        (["bad"], "source input is malformed"),
        ([{"lane": "continuum"}], "source identity is malformed"),
    ],
)
def test_smoke_selector_rejects_malformed_request_inputs(
    tmp_path: Path, inputs: object, message: str
) -> None:
    """Selection never guesses malformed request identities."""
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"inputs": inputs}), encoding="utf-8")
    population = json.loads(_POPULATION.read_text(encoding="utf-8"))
    population["source_request"]["sha256"] = file_sha256(request)
    population_path = tmp_path / "population.json"
    population_path.write_text(json.dumps(population), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        select_prospective_smoke_inputs(request, population_path)


def test_smoke_rejects_duplicated_or_missing_compiled_endpoints() -> None:
    """Compiled endpoint coverage is exact before decisions are attempted."""
    endpoint = _endpoint("released-pybdsf", 0.01)
    with pytest.raises(ValueError, match="endpoint is duplicated"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(endpoint, endpoint),
            incumbent_paired_continuum=(
                _endpoint("pinned-pybdsf-master", 0.01),
            ),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )
    with pytest.raises(ValueError, match="endpoint is absent"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(),
            incumbent_paired_continuum=(),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )


def test_smoke_rejects_malformed_or_duplicated_comparisons() -> None:
    """Reference comparisons must be tuple-shaped and uniquely identified."""
    malformed = SimpleNamespace(
        endpoint_id="continuum--reliability--overall",
        candidate_status="success",
        comparisons=[],
    )
    with pytest.raises(ValueError, match="comparisons are malformed"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(malformed,),
            incumbent_paired_continuum=(malformed,),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )
    comparison = _endpoint("released-pybdsf", 0.01)
    duplicated = SimpleNamespace(
        endpoint_id=comparison.endpoint_id,
        candidate_status="success",
        comparisons=(comparison.comparisons[0], comparison.comparisons[0]),
    )
    with pytest.raises(ValueError, match="comparison is duplicated"):
        evaluate_prospective_science_smoke(
            registry=_registry(),
            current_continuum=(duplicated,),
            incumbent_paired_continuum=(duplicated,),
            planning_deviation_by_family={"reliability": 0.08},
            compact_product_identity_equal=True,
            terminal_cycle_aggregate={
                "terminal_cycle_unseeded_persistent_accepted_count": 1
            },
        )


def test_mask_separated_support_allows_measurement_only_component() -> None:
    """A measured source may have no pixel in the refined published mask."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    catalogue, association = _mask_separated_case()

    support = evaluator["_mask_separated_support_labels"](
        catalogue,
        np.zeros((5, 5), dtype=np.int32),
        association,
    )

    assert support == {catalogue[0].identifier: (7,)}


def test_mask_separated_support_rejects_unclaimed_published_label() -> None:
    """The refined publication mask cannot invent association ownership."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    catalogue, association = _mask_separated_case()
    published = np.zeros((5, 5), dtype=np.int32)
    published[1, 1] = 9

    with pytest.raises(ValueError, match="partition native supports"):
        evaluator["_mask_separated_support_labels"](
            catalogue,
            published,
            association,
        )


def test_mask_separation_overlay_is_bounded_and_exception_safe() -> None:
    """The evaluator restores the frozen compiler seam after any outcome."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    original = (
        parent_construction_association_evaluation._recorded_support_labels
    )

    with (
        pytest.raises(RuntimeError, match="stop"),
        evaluator["_mask_measurement_separation_evaluation"](),
    ):
        assert (
            parent_construction_association_evaluation._recorded_support_labels
            is evaluator["_mask_separated_support_labels"]
        )
        raise RuntimeError("stop")

    assert (
        parent_construction_association_evaluation._recorded_support_labels
        is original
    )


def test_mask_separation_evaluation_repair_binds_exact_evidence() -> None:
    """The consumed repair retains its exact products and failed program."""
    decision = json.loads(
        _EVALUATION_REPAIR_DECISION.read_text(encoding="utf-8")
    )
    pre_review = decision["pre_review"]
    evaluator = decision["evaluator"]
    persistence_review = json.loads(
        (
            _ROOT / "config/contracts/phase-5-prospective-measurement-label-"
            "persistence-pre-review.json"
        ).read_text(encoding="utf-8")
    )

    assert decision["authorization"]["candidate_execution_authorized"] is False
    assert decision["authorization"]["evaluation_only_completion_authorized"]
    assert file_sha256(_ROOT / pre_review["path"]) == pre_review["sha256"]
    assert (
        persistence_review["binding_failure"]["failed_evaluator_sha256"]
        == (evaluator["sha256"])
    )
    assert decision["exact_preserved_evidence"] == {
        "candidate_configuration_sha256": (
            "24663a15309a0b1236ddccfc1491145229a9441c3510c351f8e20cd7c29a7a06"
        ),
        "candidate_product_set_canonical_sha256": (
            "02a17815187fcce129fdb931f977bf14815e6d614d8e9bcfde5ed50808ac4f5c"
        ),
        "candidate_revision": "b8d57a6fa9d710b210ef047403f8fc873a334fef",
        "candidate_source_tree_sha256": (
            "53ef45860749f40dfa3ac2629609512d624fc556c2c0fa665aa134cf62f8b320"
        ),
        "incumbent_product_set_canonical_sha256": (
            "1c76f7392156edb57195580ee5ff930dd66594d854cc43421c5dffbad006ec27"
        ),
        "selected_input_count": 128,
    }


def test_mask_separated_compiler_uses_measurement_support_only_for_sources(
    tmp_path: Path,
) -> None:
    """Published-mask metrics stay separate from source-union support."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    catalogue, _association = _mask_separated_case()
    associated = SimpleNamespace(
        identifier=catalogue[0].identifier,
        support_labels=(7,),
        centre_xy=(3.0, 2.0),
        integrated_flux_jy=2.0,
    )
    measurement_path = tmp_path / "measurement_labels.fits"
    measurement = np.zeros((5, 5), dtype=np.int32)
    measurement[2, 3] = 7
    fits.PrimaryHDU(measurement[np.newaxis, np.newaxis]).writeto(
        measurement_path
    )
    run = SimpleNamespace(
        directory=tmp_path,
        result=SimpleNamespace(
            status="success",
            finder_id="hebog",
            artifacts=(
                SimpleNamespace(
                    role="measurement-labels-fits",
                    relative_path=measurement_path.name,
                ),
            ),
        ),
    )
    published = np.zeros((5, 5), dtype=np.int64)

    def delegate(*_args: object, **_kwargs: object) -> object:
        synthetic, labels = evaluator[
            "source_association_evaluation_repair"
        ]._synthetic_source_labels((associated,), published)
        return synthetic, labels

    compiler = evaluator["_MaskSeparatedContinuumCompiler"](
        delegate,
        measurement_configuration="current-configuration",
    )
    run.result.configuration_sha256 = "current-configuration"
    synthetic, labels = compiler(None, None, run)

    assert labels == {catalogue[0].identifier: 1}
    assert synthetic[2, 3] == 1
    assert not np.any(synthetic[published > 0])


def test_mask_separated_compiler_delegates_historical_hebog_schema() -> None:
    """Only current products require the new measurement-label artifact."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    run = SimpleNamespace(
        result=SimpleNamespace(
            status="success",
            finder_id="hebog",
            configuration_sha256="historical-configuration",
            artifacts=(),
        )
    )
    delegated: list[object] = []

    def delegate(*args: object, **_kwargs: object) -> str:
        delegated.extend(args)
        return "historical"

    compiler = evaluator["_MaskSeparatedContinuumCompiler"](
        delegate,
        measurement_configuration="current-configuration",
    )

    assert compiler(None, None, run) == "historical"
    assert delegated[-1] is run


def test_mask_separated_compiler_rejects_current_schema_without_plane() -> (
    None
):
    """A repaired current product cannot silently lose measurement support."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    run = SimpleNamespace(
        result=SimpleNamespace(
            status="success",
            finder_id="hebog",
            configuration_sha256="current-configuration",
            artifacts=(),
        )
    )

    def delegate(*_args: object, **_kwargs: object) -> None:
        return None

    compiler = evaluator["_MaskSeparatedContinuumCompiler"](
        delegate,
        measurement_configuration="current-configuration",
    )

    with pytest.raises(ValueError, match="exactly one measurement label"):
        compiler(None, None, run)


def test_measurement_label_persistence_binds_exact_replacement_smoke() -> None:
    """The replacement smoke cannot drift from its reviewed candidate."""
    decision = json.loads(
        _MEASUREMENT_PERSISTENCE_DECISION.read_text(encoding="utf-8")
    )

    assert decision["candidate"] == {
        "configuration_sha256": (
            "24663a15309a0b1236ddccfc1491145229a9441c3510c351f8e20cd7c29a7a06"
        ),
        "revision": "a9df2c827dfa85992d8ee7732c7f9cf327019053",
        "source_tree_sha256": (
            "89eb014c1072db95cc905eac66afb63bab75e8083b224eb6c691923c7ce84add"
        ),
    }
    assert (
        file_sha256(_ROOT / decision["pre_review"]["path"])
        == (decision["pre_review"]["sha256"])
    )
    repair_review = json.loads(
        _MIXED_SCHEMA_REPAIR_PRE_REVIEW.read_text(encoding="utf-8")
    )

    def historical_bytes(relative_path: str) -> bytes:
        return subprocess.run(
            (
                "git",
                "show",
                f"{decision['candidate']['revision']}:{relative_path}",
            ),
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout

    for program in decision["implementation"]:
        if program["path"].endswith(
            "evaluate_phase5_prospective_science_smoke.py"
        ):
            assert (
                program["sha256"]
                == repair_review["binding_failure"]["failed_evaluator_sha256"]
            )
        else:
            assert (
                hashlib.sha256(historical_bytes(program["path"])).hexdigest()
                == program["sha256"]
            )
    full_replay_key = (
        "full_cumulative_replay_authorized_only_after_replacement_smoke_passes"
    )
    assert decision["authorization"] == {
        "fresh_qualification_authorized": False,
        full_replay_key: True,
        "release_authorized": False,
        "replacement_smoke_materialization_authorized": True,
        "replacement_smoke_evaluation_authorized": True,
        "rescoring_closed_evidence_authorized": False,
        "threshold_or_margin_tuning_authorized": False,
    }


def test_measurement_label_evaluation_binds_both_sealed_product_sets() -> None:
    """The one evaluator run cannot drift from either sealed product set."""
    decision = json.loads(
        _MEASUREMENT_PERSISTENCE_EVALUATION_DECISION.read_text(
            encoding="utf-8"
        )
    )

    assert decision["candidate"]["product_set_canonical_sha256"] == (
        "2b32ad121677aa2d0a57db806697a0b2f572a019a424f32fb8cb08667aedb705"
    )
    assert decision["incumbent"]["product_set_canonical_sha256"] == (
        "1c76f7392156edb57195580ee5ff930dd66594d854cc43421c5dffbad006ec27"
    )
    repair_review = json.loads(
        _MIXED_SCHEMA_REPAIR_PRE_REVIEW.read_text(encoding="utf-8")
    )
    for key in ("implementation_decision", "population"):
        assert (
            file_sha256(_ROOT / decision[key]["path"])
            == (decision[key]["sha256"])
        )
    assert (
        decision["evaluator"]["sha256"]
        == repair_review["binding_failure"]["failed_evaluator_sha256"]
    )
    assert decision["authorization"]["evaluation_once_authorized"] is True
    assert decision["authorization"]["candidate_execution_authorized"] is False


def test_mixed_schema_repair_binds_exact_evaluator_and_products() -> None:
    """The evaluator retry retains both products and dispatch identities."""
    decision = json.loads(
        _MIXED_SCHEMA_REPAIR_DECISION.read_text(encoding="utf-8")
    )

    for key in ("evaluator", "pre_review", "prior_evaluation_decision"):
        assert (
            file_sha256(_ROOT / decision[key]["path"])
            == (decision[key]["sha256"])
        )
    assert decision["candidate"]["product_set_canonical_sha256"] == (
        "2b32ad121677aa2d0a57db806697a0b2f572a019a424f32fb8cb08667aedb705"
    )
    assert decision["incumbent"]["product_set_canonical_sha256"] == (
        "1c76f7392156edb57195580ee5ff930dd66594d854cc43421c5dffbad006ec27"
    )
    assert (
        decision["authorization"][
            "evaluation_retry_authorized_for_exact_sealed_products"
        ]
        is True
    )
    assert decision["authorization"]["candidate_execution_authorized"] is False
