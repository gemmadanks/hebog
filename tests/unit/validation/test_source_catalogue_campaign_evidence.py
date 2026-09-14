"""Private-data-independent regressions for cumulative retained evidence."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownLambdaType=false

from __future__ import annotations

import importlib
import json
import runpy
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hebog.validation.evidence import (
    CampaignImplementationIdentity,
    SoftwareIdentity,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpointRegistry,
)

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
evidence: Any = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_evidence"
)
worker: Any = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_worker"
)


def _registry() -> ProspectiveEndpointRegistry:
    return ProspectiveEndpointRegistry.model_validate_json(
        (
            _ROOT
            / "config/contracts"
            / "phase-5-prospective-science-endpoint-registry.json"
        ).read_bytes()
    )


def _historical() -> dict[str, Any]:
    return json.loads(
        (
            _ROOT / "config/contracts/phase-5-external-endpoint-registry.json"
        ).read_bytes()
    )


def test_cumulative_policy_keeps_population_and_confidence() -> None:
    policy, protocol = evidence.load_cumulative_policy(_ROOT)
    assert policy["compact_manifest_path"].endswith(
        "phase-5-external-post-failure-compact-blend.json"
    )
    assert policy["continuum_manifest_path"].endswith(
        "phase-5-external-post-failure-continuum.json"
    )
    assert protocol["bootstrap_resamples"] == 50000
    assert protocol["bootstrap_seed"] == 20260810


def _record(**updates: Any) -> dict[str, Any]:
    record = {"input_id": "fixture", "finder_id": "current-hebog", **updates}
    return {**record, "record_sha256": canonical_sha256(record)}


def test_continuum_record_keeps_truth_and_public_mask_domains() -> None:
    fixture = runpy.run_path(
        str(Path(__file__).with_name("test_source_measurement_evidence.py"))
    )["source_evidence_fixture"]
    specs = evidence.compiler.expand_continuum_endpoint_specs(_historical())
    for finder, flux, error in (
        ("current-hebog", 10.0, 0.0),
        ("released-pybdsf", 6.0, 0.4),
        ("incumbent-hebog", 8.0, 0.2),
    ):
        batch = fixture(finder=finder, flux=flux)
        # This unowned region must penalize the binary public mask even
        # though it is not a modelled or catalogued source.
        mask = batch.published_support_mask.copy()
        mask[20, 20:27] = True
        diagnostic = replace(
            batch.diagnostics,
            stage_masks={"publication": mask},
            truth=tuple(
                replace(
                    row,
                    strata=tuple(
                        sorted(
                            {
                                spec.stratum
                                for spec in specs
                                if spec.stratum != "overall"
                            }
                        )
                    ),
                )
                for row in batch.diagnostics.truth
            ),
        )
        record = worker.compile_continuum_record(diagnostic, mask, specs)
        values = record["continuum_observations"]
        flux_key = next(
            s.endpoint_id
            for s in specs
            if s.metric_family == "integrated-flux-p95"
            and s.stratum == "overall"
        )
        mask_key = next(
            s.endpoint_id for s in specs if s.metric_family == "mask-iou"
        )
        assert values[flux_key]["values"] == pytest.approx([error])
        assert values[mask_key]["values"] == [0.5]
        assert (
            record["source_diagnostics"]["truth_records"][0][
                "integrated_flux_jy"
            ]
            == 10.0
        )
        assert record["finder_id"] == finder
        assert record["record_sha256"] == canonical_sha256(
            {k: v for k, v in record.items() if k != "record_sha256"}
        )
    with pytest.raises(ValueError, match="publication"):
        worker.compile_continuum_record(diagnostic, np.zeros_like(mask), specs)


def test_retention_survives_late_failure_without_overwrite(
    tmp_path: Path,
) -> None:
    path = tmp_path / "image.json"
    digest = evidence.retain_image_record(path, _record())
    # A later aggregation error must not erase the already durable record.
    with pytest.raises(ValueError, match="census"):
        evidence.load_image_records(
            [{"path": str(path), "sha256": digest}],
            [("fixture", "current-hebog"), ("missing", "current-hebog")],
        )
    assert file_sha256(path) == digest
    with pytest.raises(FileExistsError):
        evidence.retain_image_record(path, _record())
    with pytest.raises(ValueError, match="bytes"):
        evidence.load_image_records(
            [{"path": str(path), "sha256": "0" * 64}],
            [("fixture", "current-hebog")],
        )
    assert evidence.load_image_records(
        [{"path": str(path), "sha256": digest}],
        [("fixture", "current-hebog")],
    ) == (_record(),)
    with pytest.raises(ValueError, match="requires input"):
        evidence.retain_image_record(path, _record(input_id=""))


@pytest.mark.parametrize("defect", ("endpoints", "image"))
def test_observation_identity_cannot_change(defect: str) -> None:
    specs = evidence.compiler.expand_continuum_endpoint_specs(_historical())
    values = {
        spec.endpoint_id: {
            "image_key": "fixture",
            "values": [1.0],
            "status": "success",
            "reason": None,
        }
        for spec in specs
    }
    if defect == "endpoints":
        values.pop(specs[0].endpoint_id)
    else:
        values[specs[0].endpoint_id]["image_key"] = "wrong-image"
    with pytest.raises(ValueError, match="identit"):
        evidence.continuum_observations(
            [
                {"lane": "compact-blend"},
                _record(lane="continuum", continuum_observations=values),
            ],
            specs,
        )


def test_duplicate_compact_comparison_is_rejected() -> None:
    row = {
        "reference_identifier": "incumbent-hebog",
        "metric_id": "a",
        "stratum": "overall",
    }
    with pytest.raises(ValueError, match="duplicated"):
        evidence.compact_comparison_rows(_registry(), [row, row])


@pytest.mark.slow
def test_compact_late_engine_uses_real_retained_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixtures = runpy.run_path(
        str(Path(__file__).with_name("test_phase_four_decision.py"))
    )
    campaign, dataset, _, _, _ = fixtures["_synthetic_campaign_inputs"]()
    finders = (
        "current-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
        "incumbent-hebog",
    )
    identities = tuple(
        campaign.implementations[0].model_copy(
            update={
                "identifier": finder,
                "role": "candidate"
                if finder == "current-hebog"
                else "reference",
            }
        )
        for finder in finders
    )
    records = [
        {
            "lane": "compact-blend",
            "compact_diagnostic": fixtures["_successful_realization"](
                finder, recipe.seed, dataset
            ).model_dump(mode="json"),
        }
        for finder in finders
        for recipe in evidence.compiler.iter_dataset_recipes(dataset)
    ]
    monkeypatch.setattr(
        evidence.compiler,
        "_dataset_maps",
        lambda _path: ({dataset.identifier: dataset}, {}),
    )
    result = evidence.compile_compact_records(
        records,
        _historical(),
        repository_root=_ROOT,
        implementations=identities,
        captured_at=datetime(2026, 9, 8, tzinfo=UTC),
        expected_image_count=3,
    )
    assert len(result) == 2
    assert {
        row["reference_identifier"]
        for view in result
        for row in view["metric_decisions"]
    } == set(finders[1:])
    assert all(view["metric_decisions"] for view in result)
    with pytest.raises(ValueError, match="realization census"):
        evidence.compile_compact_records(
            records[:-1],
            _historical(),
            repository_root=_ROOT,
            implementations=identities,
            captured_at=datetime(2026, 9, 8, tzinfo=UTC),
            expected_image_count=3,
        )
    monkeypatch.setattr(
        evidence.compiler, "_dataset_maps", lambda _path: ({}, {})
    )
    with pytest.raises(ValueError, match="dataset census"):
        evidence.compile_compact_records(
            records,
            _historical(),
            repository_root=_ROOT,
            implementations=identities,
            captured_at=datetime(2026, 9, 8, tzinfo=UTC),
            expected_image_count=3,
        )


def test_incumbent_comparisons_are_measured_not_structural_zeros() -> None:
    registry = _registry()
    endpoint = next(row for row in registry.endpoints if row.lane == "compact")
    rows = evidence.compact_comparison_rows(
        registry,
        [
            {
                "reference_identifier": "incumbent-hebog",
                "metric_id": endpoint.metric_family,
                "stratum": endpoint.stratum,
                "candidate_value": 0.5,
                "reference_value": 1.0,
                "positive_regression": 0.5,
                "upper_confidence_limit": 0.6,
            }
        ],
    )
    incumbent = next(
        row
        for row in rows
        if row["endpoint_id"] == endpoint.endpoint_id
        and row["comparator_id"] == "incumbent-hebog"
    )
    assert incumbent["positive_regression"] == 0.5
    assert incumbent["upper_confidence_limit"] == 0.6
    missing = next(row for row in rows if row["comparator_id"] == "aegean")
    assert missing["comparator_available"] is False
    assert missing["upper_confidence_limit"] is None


@pytest.mark.parametrize("successful", (False, True))
def test_compact_records_accept_arbitrary_completion_order(
    monkeypatch: pytest.MonkeyPatch,
    successful: bool,
) -> None:
    """The strict campaign model must receive seed/finder-canonical rows."""
    finders = (
        "current-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
        "incumbent-hebog",
    )
    identities = tuple(
        CampaignImplementationIdentity(
            identifier=finder,
            role="candidate" if finder == "current-hebog" else "reference",
            execution_configuration_sha256="1" * 64,
            software=SoftwareIdentity(
                name=finder,
                version="fixture",
                dependency_inventory_sha256="2" * 64,
            ),
        )
        for finder in finders
    )
    records: list[dict[str, Any]] = [
        {
            "lane": "compact-blend",
            "compact_diagnostic": {
                "implementation_identifier": finder,
                "seed": seed,
                "status": "failure",
                "failure": {
                    "stage": "fixture",
                    "exception_type": "RuntimeError",
                    "message": "injected failure",
                    "traceback_sha256": "a" * 64,
                },
            },
        }
        for finder in reversed(finders)
        for seed in (2, 1)
    ]
    if successful:
        for record in records:
            row = record["compact_diagnostic"]
            record["compact_diagnostic"] = {
                "implementation_identifier": row["implementation_identifier"],
                "seed": row["seed"],
                "status": "success",
                "candidate_count": 0,
                "source_pairs": [],
                "association_pairs": [],
            }

    class Decision:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"metric_decisions": []}

    observed: list[tuple[str, ...]] = []

    def decide(campaign: Any, *_args: Any, **_kwargs: Any) -> Decision:
        observed.append(
            tuple(row.identifier for row in campaign.implementations)
        )
        return Decision()

    monkeypatch.setattr(
        evidence.compiler, "evaluate_phase_four_recovery", decide
    )
    result = evidence.compile_compact_records(
        records,
        _historical(),
        repository_root=_ROOT,
        implementations=identities,
        captured_at=datetime(2026, 9, 8, tzinfo=UTC),
        expected_image_count=2,
    )
    assert len(result) == 2
    assert observed[-1] == ("current-hebog", "aegean", "incumbent-hebog")


@pytest.mark.parametrize("missing_dataset", (False, True))
def test_compact_census_failure_precedes_statistics(
    monkeypatch: pytest.MonkeyPatch, missing_dataset: bool
) -> None:
    if missing_dataset:
        monkeypatch.setattr(
            evidence.compiler, "_dataset_maps", lambda _path: ({}, {})
        )
    with pytest.raises(ValueError, match="census changed"):
        evidence.compile_compact_records(
            [],
            _historical(),
            repository_root=_ROOT,
            implementations=(),
            captured_at=datetime(2026, 9, 8, tzinfo=UTC),
            expected_image_count=2,
        )


def test_missing_comparison_cannot_publish_a_passing_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evidence, "compile_continuum_records", lambda *_a, **_k: ([], [])
    )
    monkeypatch.setattr(evidence, "compact_comparison_rows", lambda *_a: [])
    with pytest.raises(ValueError, match="comparison census changed"):
        evidence.compile_cumulative_decision(
            records=[],
            registry=_registry(),
            historical_registry=_historical(),
            compact_decisions=[],
            safety_results={},
            expected_continuum_count=1600,
            resamples=50000,
            seed=20260810,
            planning_deviations={},
        )


@pytest.mark.parametrize("bad_incumbent", (False, True))
def test_all_cumulative_comparisons_reach_terminal(
    bad_incumbent: bool,
) -> None:
    """Exercise the real late confidence and 1,187-way decision seams."""
    registry = _registry()
    historical = _historical()
    specs = evidence.compiler.expand_continuum_endpoint_specs(historical)
    records = []
    for finder in (
        "current-hebog",
        "incumbent-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
    ):
        records.extend(
            _record(
                input_id=f"fixture-{image}",
                finder_id=finder,
                lane="continuum",
                continuum_observations={
                    spec.endpoint_id: {
                        "image_key": f"fixture-{image}",
                        "values": [0.5],
                        "status": "success",
                        "reason": None,
                    }
                    for spec in specs
                },
            )
            for image in range(4)
        )
    compact = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "compact":
            continue
        for comparator in endpoint.comparators:
            regression = (
                1.0
                if bad_incumbent and comparator == "incumbent-hebog"
                else 0.0
            )
            compact.append(
                {
                    "reference_identifier": comparator,
                    "metric_id": endpoint.metric_family,
                    "stratum": endpoint.stratum,
                    "candidate_value": 0.5,
                    "reference_value": 0.5,
                    "positive_regression": regression,
                    "upper_confidence_limit": regression,
                }
            )
    decision = evidence.compile_cumulative_decision(
        records=records,
        registry=registry,
        historical_registry=historical,
        compact_decisions=[{"metric_decisions": compact}],
        safety_results=dict.fromkeys(
            (
                "finite-measurements",
                "product-validity",
                "schema-and-provenance-integrity",
                "serial-and-existing-dask-determinism",
                "write-once-publication",
            ),
            True,
        ),
        expected_continuum_count=4,
        resamples=64,
        seed=1234,
        planning_deviations={},
    )
    assert decision["status"] == ("fail" if bad_incumbent else "pass")
    assert decision["all_required_endpoints_pass"] is not bad_incumbent
    assert sum(decision["comparison_status_counts"].values()) == 1187
    assert decision["structural_incumbent_equality_used"] is False
