"""Tests for the frozen Phase 5 raw-product science compiler."""

from __future__ import annotations

import runpy
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import pytest

from hebog.validation.datasets import DatasetRole, load_dataset_manifest

_ROOT = Path(__file__).parents[3]
_COMPILER = _ROOT / "scripts/validation/compile_phase5_external_campaign.py"
_REGISTRY = _ROOT / "config/contracts/phase-5-external-endpoint-registry.json"
_PROTOCOL = _ROOT / "config/contracts/phase-5-external-comparison.json"
_DECISION = _ROOT / "config/contracts/phase-5-external-execution-decision.json"
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_LAUNCHER = _ROOT / "scripts/benchmark/run_phase5_external_campaign.py"
_COMPACT_MANIFEST = (
    _ROOT / "config/datasets/phase-5-external-compact-blend.json"
)


@pytest.fixture(scope="module")
def compiler() -> dict[str, Any]:
    """Load the compiler without invoking its command-line entry point."""
    return runpy.run_path(str(_COMPILER))


@pytest.fixture(scope="module")
def registry(compiler: dict[str, Any]) -> dict[str, Any]:
    """Load and validate the prospective endpoint population."""
    return compiler["load_endpoint_registry"](_REGISTRY, _COMPILER)


@pytest.fixture(scope="module")
def approved_campaign_request(
    compiler: dict[str, Any],
) -> Iterator[tuple[Any, Path]]:
    """Build the unopened approved request without inspecting containers."""
    launcher = compiler["_LAUNCHER"]
    protocol = compiler["_json_object"](_PROTOCOL)
    pending = compiler["_json_object"](_DECISION)
    decision = {
        **pending,
        "status": "reviewed-before-external-output",
        "named_review": "unit-test authorization",
        "decision": "authorize-one-terminal-external-comparison",
        "execution_authorized": True,
        "source_tree_sha256": launcher["source_tree_sha256"](_ROOT),
        "runners": [
            {
                **runner,
                "sha256": launcher["file_sha256"](
                    _ROOT / runner["relative_path"]
                ),
            }
            for runner in pending["runners"]
        ],
        "next_action": (
            "execute-complete-frozen-comparison-once-without-opening-"
            "partial-results"
        ),
    }
    container_type = launcher["CampaignContainerImage"]
    references = {item["finder_id"]: item for item in protocol["references"]}
    containers = {
        "hebog": container_type(
            finder_id="hebog",
            image="localhost/hebog:test",
            image_id="1" * 64,
            digest=decision["hebog_container_image_digest"],
            operating_system="linux",
            architecture="arm64",
        ),
        **{
            finder_id: container_type(
                finder_id=finder_id,
                image=f"localhost/{finder_id}:test",
                image_id=str(index) * 64,
                digest=reference["container_image_digest"],
                operating_system="linux",
                architecture="arm64",
            )
            for index, (finder_id, reference) in enumerate(
                references.items(), start=2
            )
        },
    }
    decision_type = launcher["PhaseFiveExternalExecutionDecision"]
    validated = decision_type.model_validate(decision)
    with TemporaryDirectory(prefix=".phase5-test-", dir=_ROOT) as directory:
        decision_path = Path(directory) / "decision.json"
        decision_path.write_text(
            validated.model_dump_json(indent=2),
            encoding="utf-8",
        )
        yield (
            launcher["build_campaign_request"](
                repository_root=_ROOT,
                protocol_path=_PROTOCOL,
                decision_path=decision_path,
                base_review_path=_BASE_REVIEW,
                launcher_path=_LAUNCHER,
                containers=containers,
            ),
            decision_path,
        )


def test_registry_expands_exact_binding_and_diagnostic_populations(
    compiler: dict[str, Any], registry: dict[str, Any]
) -> None:
    """Irregular median is report-only while both axis bounds are binding."""
    specifications = compiler["expand_continuum_endpoint_specs"](registry)
    binding = tuple(item for item in specifications if item.binding)
    diagnostic = tuple(item for item in specifications if not item.binding)

    assert len(binding) == 143
    assert len(diagnostic) == 15
    assert len({item.endpoint_id for item in specifications}) == 158
    assert {
        item.metric_family
        for item in binding
        if item.position_population == "irregular-segment"
    } == {
        "absolute-mean-offset-x",
        "absolute-mean-offset-y",
        "position-p95",
    }
    assert {
        item.metric_family
        for item in diagnostic
        if item.position_population == "irregular-segment"
    } == {"position-median"}


def test_registry_limits_aegean_to_products_it_supplies(
    compiler: dict[str, Any], registry: dict[str, Any]
) -> None:
    """Aegean fitted metrics bind but absent deconvolution does not."""
    compact = registry["compact"]
    applicable = set(compact["aegean_applicable_metric_ids"])
    endpoint_keys = compiler["_derived_compact_endpoint_keys"](registry, _ROOT)
    aegean_keys = tuple(key for key in endpoint_keys if key[0] in applicable)

    assert "median-position" in applicable
    assert "percentile-95-integrated-flux" in applicable
    assert "median-fitted-axis" in applicable
    assert "deconvolution-classification-availability" not in applicable
    assert "uncertainty-normalized-bias" not in applicable
    assert len(endpoint_keys) == 225
    assert len(aegean_keys) == 143
    assert len(set(endpoint_keys)) == 225


def test_phase_four_interval_view_retains_a_validated_role(
    compiler: dict[str, Any],
) -> None:
    """The analysis-only view must satisfy Phase 4R's role identity check."""
    source = load_dataset_manifest(_COMPACT_MANIFEST).datasets[0]

    interval_view = compiler["_phase_four_interval_dataset"](source)

    assert source.role is DatasetRole.REGRESSION
    assert interval_view.role is DatasetRole.QUALIFICATION


def test_compiler_accepts_only_the_approved_campaign_request(
    compiler: dict[str, Any],
    registry: dict[str, Any],
    approved_campaign_request: tuple[Any, Path],
) -> None:
    """Protocol equality cannot substitute for approved execution identity."""
    validate = compiler["_validate_campaign_request_identity"]
    request, decision_path = approved_campaign_request
    authorized_registry = {
        **registry,
        "execution_decision_path": decision_path.relative_to(_ROOT).as_posix(),
        "execution_decision_sha256": compiler["_file_sha256"](decision_path),
    }

    validate(request, authorized_registry, _ROOT)

    changed_launcher = request.model_copy(update={"launcher_sha256": "0" * 64})
    with pytest.raises(ValueError, match="request identity"):
        validate(changed_launcher, authorized_registry, _ROOT)

    first_input = request.inputs[0].model_copy(
        update={"manifest_sha256": "0" * 64}
    )
    changed_inputs = request.model_copy(
        update={"inputs": (first_input, *request.inputs[1:])}
    )
    with pytest.raises(ValueError, match="input manifest"):
        validate(changed_inputs, authorized_registry, _ROOT)


def test_whole_image_compiler_preserves_direction_and_pairing(
    compiler: dict[str, Any],
) -> None:
    """Point differences and observed SD use aligned image contributions."""
    spec = compiler["ContinuumEndpointSpec"](
        endpoint_id="continuum--completeness--overall",
        metric_family="completeness",
        stratum="overall",
        value_kind="image-scalar",
        statistic="mean",
        position_population="not-applicable",
        binding=True,
    )
    observations = compiler["EndpointObservation"]
    candidate = tuple(
        observations(image_key=f"image-{index}", values=(value,))
        for index, value in enumerate((0.90, 0.95, 1.00))
    )
    reference = tuple(
        observations(image_key=f"image-{index}", values=(value,))
        for index, value in enumerate((0.88, 0.94, 0.99))
    )

    result = compiler["compile_reference_comparison"](
        spec,
        candidate,
        reference,
        reference_id="released-pybdsf",
        desirable_direction="higher-is-better",
        resamples=200,
        seed=17,
    )

    assert result.status == "success"
    assert result.reference_value == pytest.approx(np.mean((0.88, 0.94, 0.99)))
    assert result.positive_regression == pytest.approx(-0.04 / 3.0)
    assert result.observed_paired_standard_deviation == pytest.approx(
        np.std((-0.02, -0.01, -0.01), ddof=1)
    )
    assert result.upper_confidence_limit is not None


def test_vectorized_cluster_resampling_matches_ragged_serial_statistic(
    compiler: dict[str, Any],
) -> None:
    """Padded batches preserve the readable pooled-cluster definition."""
    spec = compiler["ContinuumEndpointSpec"](
        endpoint_id="continuum--position-p95--overall",
        metric_family="position-p95",
        stratum="overall",
        value_kind="group-values",
        statistic="percentile-95",
        position_population="irregular-segment",
        binding=True,
    )
    observation = compiler["EndpointObservation"]
    candidate = (
        observation(image_key="image-0", values=(0.1, 0.2)),
        observation(image_key="image-1", values=()),
        observation(image_key="image-2", values=(0.3,)),
    )
    reference = (
        observation(image_key="image-0", values=(0.12, 0.22)),
        observation(image_key="image-1", values=()),
        observation(image_key="image-2", values=(0.28, 0.31)),
    )
    indices = np.asarray(((0, 2, 0), (2, 0, 2)), dtype=np.int64)

    observed = compiler["_paired_statistic"](
        spec,
        candidate,
        reference,
        "lower-is-better",
    )(indices)
    expected = np.asarray(
        [
            compiler["_regression"](
                compiler["_aggregate_observations"](spec, candidate, row),
                compiler["_aggregate_observations"](spec, reference, row),
                "lower-is-better",
            )
            for row in indices
        ]
    )

    np.testing.assert_allclose(observed, expected, rtol=0.0, atol=0.0)


def test_failed_image_retains_denominator_and_makes_endpoint_unavailable(
    compiler: dict[str, Any],
) -> None:
    """A failed finder image is never removed from a scientific population."""
    spec = compiler["ContinuumEndpointSpec"](
        endpoint_id="continuum--mask-iou--overall",
        metric_family="mask-iou",
        stratum="overall",
        value_kind="image-scalar",
        statistic="mean",
        position_population="not-applicable",
        binding=True,
    )
    observation = compiler["EndpointObservation"]
    candidate = (
        observation(image_key="image-1", values=(0.9,)),
        observation(
            image_key="image-2",
            status="failed",
            reason="finder failed",
        ),
    )

    compiled = compiler["compile_continuum_endpoint"](
        spec,
        candidate,
        {},
        expected_image_count=2,
        desirable_direction="higher-is-better",
        absolute_decision_statistic="point-estimate",
        resamples=200,
        seed=19,
    )

    assert compiled.image_count == 2
    assert compiled.candidate_status == "failed"
    assert compiled.candidate_value is None
    assert compiled.reason == "finder failed"


def test_conditional_measurement_keeps_empty_images_without_inventing_values(
    compiler: dict[str, Any],
) -> None:
    """Completeness owns misses while conditional flux keeps image clusters."""
    spec = compiler["ContinuumEndpointSpec"](
        endpoint_id="continuum--integrated-flux-median--overall",
        metric_family="integrated-flux-median",
        stratum="overall",
        value_kind="group-values",
        statistic="median",
        position_population="not-applicable",
        binding=True,
    )
    observation = compiler["EndpointObservation"]
    candidate = tuple(
        observation(
            image_key=f"image-{index:02d}",
            values=() if index == 0 else (0.08 + index / 1_000,),
        )
        for index in range(20)
    )
    reference = tuple(
        observation(
            image_key=f"image-{index:02d}",
            values=() if index == 0 else (0.09 + index / 1_000,),
        )
        for index in range(20)
    )

    compiled = compiler["compile_continuum_endpoint"](
        spec,
        candidate,
        {"released-pybdsf": reference},
        expected_image_count=20,
        desirable_direction="lower-is-better",
        absolute_decision_statistic="point-estimate",
        resamples=300,
        seed=29,
    )

    assert compiled.image_count == 20
    assert compiled.candidate_status == "success"
    assert compiled.candidate_value == pytest.approx(0.09)
    assert compiled.comparisons[0].status == "success"


def test_clustered_axis_bound_is_separate_from_paired_point_statistic(
    compiler: dict[str, Any],
) -> None:
    """Signed bias uses a confidence bound without changing pairing."""
    spec = compiler["ContinuumEndpointSpec"](
        endpoint_id="continuum--absolute-mean-offset-x--overall",
        metric_family="absolute-mean-offset-x",
        stratum="overall",
        value_kind="signed-group-values",
        statistic="absolute-mean",
        position_population="irregular-segment",
        binding=True,
        paired=False,
    )
    observation = compiler["EndpointObservation"]
    candidate = (
        observation(image_key="image-1", values=(-0.02, 0.01)),
        observation(image_key="image-2", values=(0.03, 0.02)),
        observation(image_key="image-3", values=(-0.01, 0.00)),
    )

    compiled = compiler["compile_continuum_endpoint"](
        spec,
        candidate,
        {},
        expected_image_count=3,
        desirable_direction="lower-is-better",
        absolute_decision_statistic=(
            "one-sided-95-percent-upper-confidence-limit"
        ),
        resamples=300,
        seed=23,
    )

    assert compiled.candidate_value == pytest.approx(0.005)
    assert compiled.absolute_decision_value is not None
    assert compiled.absolute_decision_value >= compiled.candidate_value
    assert compiled.comparisons == ()


def test_compact_binding_filters_only_predeclared_aegean_keys(
    compiler: dict[str, Any], registry: dict[str, Any]
) -> None:
    """Unavailable Aegean-only product families cannot open new endpoints."""
    decision: dict[str, Any] = {
        "implementation_outcomes": [
            {
                "implementation_identifier": "hebog",
                "failed_seeds": [],
                "policy": "qualification-fails",
            },
            {
                "implementation_identifier": "aegean",
                "failed_seeds": [],
                "policy": "record-and-continue",
            },
        ],
        "metric_decisions": [
            {
                "metric_id": "median-position",
                "stratum": "overall",
                "reference_identifier": "aegean",
                "status": "pass",
            },
            {
                "metric_id": "uncertainty-normalized-bias",
                "stratum": "overall",
                "reference_identifier": "aegean",
                "status": "indeterminate",
            },
        ],
    }

    selected = compiler["select_aegean_binding_decisions"](decision, registry)

    assert tuple(item["metric_id"] for item in selected) == (
        "median-position",
    )


def test_truth_first_measurement_separates_catalogue_duplicates_from_splits(
    compiler: dict[str, Any],
) -> None:
    """Rows sharing one support are duplicates, not extra support islands."""
    truth_type = compiler["ContinuumTruthObject"]
    candidate_type = compiler["ContinuumCandidateObject"]
    truth_labels = np.zeros((12, 12), dtype=np.int32)
    truth_labels[2:5, 2:5] = 1
    truth_labels[7:10, 7:10] = 2
    candidate_labels = truth_labels.copy()
    truth = (
        truth_type(
            identifier="truth-a",
            support_label=1,
            centre_xy=(3.0, 3.0),
            integrated_flux_jy=1.0,
            catalogue_role="astronomical-source",
            strata=("morphology-diffuse",),
        ),
        truth_type(
            identifier="truth-b",
            support_label=2,
            centre_xy=(8.0, 8.0),
            integrated_flux_jy=2.0,
            catalogue_role="astronomical-source",
            strata=("morphology-shell",),
        ),
    )
    candidates = (
        candidate_type(
            identifier="candidate-a",
            support_label=1,
            centre_xy=(3.0, 3.0),
            integrated_flux_jy=1.0,
        ),
        candidate_type(
            identifier="candidate-a-duplicate",
            support_label=1,
            centre_xy=(3.1, 3.0),
            integrated_flux_jy=1.0,
        ),
        candidate_type(
            identifier="candidate-b",
            support_label=2,
            centre_xy=(8.0, 8.0),
            integrated_flux_jy=2.0,
        ),
    )

    measurements = compiler["measure_continuum_image"](
        truth,
        candidates,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=4.0,
    )

    assert measurements["completeness"]["overall"] == pytest.approx(1.0)
    assert measurements["reliability"]["overall"] == pytest.approx(2 / 3)
    assert measurements["duplicate-fraction"]["overall"] == pytest.approx(0.5)
    assert measurements["split-fraction"]["overall"] == pytest.approx(0.0)
    assert measurements["merge-fraction"]["overall"] == pytest.approx(0.0)
    assert measurements["mask-iou"]["overall"] == pytest.approx(1.0)
    assert measurements["integrated-flux-median"]["overall"] == (
        pytest.approx(0.0),
        pytest.approx(0.0),
    )


def test_truth_first_measurement_retains_secondary_support_topology(
    compiler: dict[str, Any],
) -> None:
    """A second overlapping support is a split even when not primary."""
    truth_type = compiler["ContinuumTruthObject"]
    candidate_type = compiler["ContinuumCandidateObject"]
    truth_labels = np.zeros((12, 12), dtype=np.int32)
    truth_labels[3:9, 3:9] = 1
    candidate_labels = np.zeros_like(truth_labels)
    candidate_labels[3:6, 3:9] = 1
    candidate_labels[6:9, 3:9] = 2
    truth = (
        truth_type(
            identifier="truth",
            support_label=1,
            centre_xy=(5.5, 5.5),
            integrated_flux_jy=1.0,
            catalogue_role="astronomical-source",
            strata=("morphology-diffuse",),
        ),
    )
    candidates = (
        candidate_type(
            identifier="candidate-one",
            support_label=1,
            centre_xy=(5.5, 4.0),
            integrated_flux_jy=0.5,
        ),
        candidate_type(
            identifier="candidate-two",
            support_label=2,
            centre_xy=(5.5, 7.0),
            integrated_flux_jy=0.5,
        ),
    )

    measurements = compiler["measure_continuum_image"](
        truth,
        candidates,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=4.0,
    )

    assert measurements["split-fraction"]["overall"] == pytest.approx(1.0)
    assert measurements["duplicate-fraction"]["overall"] == pytest.approx(1.0)
