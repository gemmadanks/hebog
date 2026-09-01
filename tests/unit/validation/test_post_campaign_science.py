"""Tests for prospective corrections after the closed Phase 5 campaign."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_campaign_science import (
    diagnose_compact_component_realization,
    evaluate_post_campaign_candidate_detection,
    evaluate_post_campaign_candidate_products,
    evaluate_public_finder_correction_candidate_products,
    refine_external_candidate_detection,
)


def test_external_detection_refinement_updates_all_product_fields() -> None:
    """A refined label plane remains one internally consistent result."""
    labels = np.zeros((9, 9), dtype=np.int32)
    labels[2:7, 2:7] = 3
    labels[4, 7] = 3
    combined_snr = np.full(labels.shape, 4.0)
    support = np.zeros(labels.shape, dtype=np.bool_)
    support[3:6, 7] = True
    detection = ThresholdFilterResult(
        combined_snr=combined_snr,
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
    )

    refined = refine_external_candidate_detection(
        detection,
        support,
        BeamShapePixels(
            major_fwhm_pixels=4.0,
            minor_fwhm_pixels=3.0,
            position_angle_degrees=0.0,
        ),
    )

    np.testing.assert_array_equal(
        refined.retained_mask,
        refined.component_labels > 0,
    )
    assert refined.component_count == 1
    assert refined.component_labels[3, 7] == 3
    assert refined.component_labels[2, 7] == 0


def test_candidate_products_reuse_atrous_detection_and_position_signal(
    mocker: MockerFixture,
) -> None:
    """The prospective boundary connects one transform to both products."""
    labels = np.zeros((7, 7), dtype=np.int32)
    labels[1:6, 1:6] = 2
    detection = ThresholdFilterResult(
        combined_snr=np.full(labels.shape, 6.0),
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
    )
    position_signal = np.full(labels.shape, 0.5)
    atrous = SimpleNamespace(reconstructed_signal_jy_per_beam=position_signal)
    reconstruction = SimpleNamespace(
        support_mask=np.ones(labels.shape, dtype=np.bool_)
    )
    direct_signal = np.full(labels.shape, 1.5)
    scale_planes = (cast(Any, SimpleNamespace(scale_order=1)),)
    mocker.patch(
        "hebog.validation.post_campaign_science.prepare_scale_filter_inputs",
        return_value=SimpleNamespace(
            residual_jy_per_beam=direct_signal,
            scientifically_valid=np.ones(labels.shape, dtype=np.bool_),
        ),
    )
    build_planes = mocker.patch(
        "hebog.validation.post_campaign_science."
        "_retained_scale_detection_planes",
        return_value=scale_planes,
    )
    corrective = mocker.patch(
        "hebog.validation.post_campaign_science._corrective_results",
        return_value=(object(), atrous, detection),
    )
    reconstruct = mocker.patch(
        "hebog.validation.post_campaign_science."
        "reconstruct_significant_atrous",
        return_value=reconstruction,
    )
    review = SimpleNamespace(
        matrix=SimpleNamespace(
            detection_sigma=5.0,
            island_sigma=3.0,
            support_fraction_bounds=(0.5, 1.0),
        )
    )
    beam = BeamShapePixels(4.0, 3.0, 0.0)

    products = evaluate_post_campaign_candidate_products(
        np.ones(labels.shape),
        np.ones(labels.shape, dtype=np.bool_),
        np.zeros(labels.shape),
        np.ones(labels.shape),
        beam=beam,
        review=review,  # type: ignore[arg-type]
    )

    np.testing.assert_array_equal(
        products.position_signal_jy_per_beam,
        direct_signal + position_signal,
    )
    assert products.detection.component_count == 1
    np.testing.assert_array_equal(
        products.direct_component_labels,
        detection.component_labels,
    )
    assert not products.direct_component_labels.flags.writeable
    assert products.scale_detection_planes is scale_planes
    assert corrective.call_args.kwargs["family"] == "residual-b3-atrous"
    assert reconstruct.call_args.kwargs == {
        "detection_sigma": 5.0,
        "island_sigma": 3.0,
        "minimum_support_fraction": review.matrix.support_fraction_bounds[0],
    }
    assert build_planes.call_count == 1


def test_public_correction_owns_bridge_from_pre_union_direct_seeds(
    mocker: MockerFixture,
) -> None:
    """The prospective path cannot inherit the historical connected union."""
    labels = np.zeros((7, 11), dtype=np.int32)
    labels[3, 1] = 9
    labels[3, 9] = 2
    combined_snr = np.full(labels.shape, 6.0)
    support = np.zeros(labels.shape, dtype=np.bool_)
    support[3, 1:10] = True
    direct_detection = SimpleNamespace(
        combined_snr=combined_snr,
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=2,
        reconstruction=SimpleNamespace(support_mask=support),
    )
    direct_signal = np.full(labels.shape, 1.0)
    prepared = SimpleNamespace(
        residual_jy_per_beam=direct_signal,
        scientifically_valid=np.ones(labels.shape, dtype=np.bool_),
    )
    atrous = SimpleNamespace(
        reconstructed_signal_jy_per_beam=np.full(labels.shape, 0.5)
    )
    scale_planes = (cast(Any, SimpleNamespace(scale_order=1)),)
    mocker.patch(
        "hebog.validation.post_campaign_science.prepare_scale_filter_inputs",
        return_value=prepared,
    )
    mocker.patch(
        "hebog.validation.post_campaign_science._corrective_results",
        return_value=(object(), atrous, object()),
    )
    mocker.patch(
        "hebog.validation.post_campaign_science."
        "_retained_scale_detection_planes",
        return_value=scale_planes,
    )
    detect = mocker.patch(
        "hebog.validation.post_campaign_science."
        "detect_residual_multiscale_islands",
        return_value=direct_detection,
    )
    review = SimpleNamespace(
        matrix=SimpleNamespace(
            detection_sigma=5.0,
            island_sigma=3.0,
            support_fraction_bounds=(0.5, 1.0),
        ),
        corrections=SimpleNamespace(minimum_island_area_beams=0.25),
    )

    products = evaluate_public_finder_correction_candidate_products(
        np.ones(labels.shape),
        np.ones(labels.shape, dtype=np.bool_),
        np.zeros(labels.shape),
        np.ones(labels.shape),
        beam=BeamShapePixels(16.0, 12.0, 0.0),
        review=review,  # type: ignore[arg-type]
    )

    assert products.detection.component_count == 2
    assert products.detection.component_labels[3, 1] == 9
    assert products.detection.component_labels[3, 9] == 2
    assert products.detection.component_labels[3, 5] == 9
    np.testing.assert_array_equal(
        products.direct_component_labels,
        direct_detection.component_labels,
    )
    assert not products.direct_component_labels.flags.writeable
    assert products.scale_detection_planes is scale_planes
    assert detect.call_count == 1


def test_public_correction_refines_direct_low_snr_protrusions(
    mocker: MockerFixture,
) -> None:
    """Seed ownership is followed by the reviewed sparse-boundary filter."""
    labels = np.zeros((9, 11), dtype=np.int32)
    labels[2:7, 2:7] = 4
    labels[4, 7:10] = 4
    support = np.zeros(labels.shape, dtype=np.bool_)
    support[2:7, 2:7] = True
    direct_detection = SimpleNamespace(
        combined_snr=np.where(labels > 0, 4.0, 0.0),
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
        reconstruction=SimpleNamespace(support_mask=support),
    )
    prepared = SimpleNamespace(
        residual_jy_per_beam=np.ones(labels.shape),
        scientifically_valid=np.ones(labels.shape, dtype=np.bool_),
    )
    atrous = SimpleNamespace(
        reconstructed_signal_jy_per_beam=np.zeros(labels.shape)
    )
    mocker.patch(
        "hebog.validation.post_campaign_science.prepare_scale_filter_inputs",
        return_value=prepared,
    )
    mocker.patch(
        "hebog.validation.post_campaign_science._corrective_results",
        return_value=(object(), atrous, object()),
    )
    mocker.patch(
        "hebog.validation.post_campaign_science."
        "detect_residual_multiscale_islands",
        return_value=direct_detection,
    )
    mocker.patch(
        "hebog.validation.post_campaign_science."
        "_retained_scale_detection_planes",
        return_value=(),
    )
    review = SimpleNamespace(
        matrix=SimpleNamespace(
            detection_sigma=5.0,
            island_sigma=3.0,
            support_fraction_bounds=(0.5, 1.0),
        ),
        corrections=SimpleNamespace(minimum_island_area_beams=0.25),
    )

    products = evaluate_public_finder_correction_candidate_products(
        np.ones(labels.shape),
        np.ones(labels.shape, dtype=np.bool_),
        np.zeros(labels.shape),
        np.ones(labels.shape),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=review,  # type: ignore[arg-type]
    )

    assert np.all(products.detection.component_labels[2:7, 2:7] == 4)
    assert not products.detection.component_labels[4, 7:10].any()
    assert np.all(products.direct_component_labels[2:7, 2:7] == 4)
    assert not products.direct_component_labels[4, 7:10].any()


def test_candidate_products_require_atrous_evidence(
    mocker: MockerFixture,
) -> None:
    """A comparator-only result cannot enter the corrected candidate."""
    labels = np.ones((3, 3), dtype=np.int32)
    detection = ThresholdFilterResult(
        combined_snr=np.ones(labels.shape),
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
    )
    mocker.patch(
        "hebog.validation.post_campaign_science.prepare_scale_filter_inputs",
        return_value=object(),
    )
    mocker.patch(
        "hebog.validation.post_campaign_science._corrective_results",
        return_value=(object(), None, detection),
    )
    review = SimpleNamespace(
        matrix=SimpleNamespace(detection_sigma=5.0, island_sigma=3.0)
    )

    with pytest.raises(RuntimeError, match="requires residual B3"):
        evaluate_post_campaign_candidate_products(
            np.ones(labels.shape),
            np.ones(labels.shape, dtype=np.bool_),
            np.zeros(labels.shape),
            np.ones(labels.shape),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=review,  # type: ignore[arg-type]
        )


def test_public_correction_requires_atrous_evidence(
    mocker: MockerFixture,
) -> None:
    """Seed ownership cannot proceed without the reviewed B3 evidence."""
    mocker.patch(
        "hebog.validation.post_campaign_science.prepare_scale_filter_inputs",
        return_value=object(),
    )
    mocker.patch(
        "hebog.validation.post_campaign_science._corrective_results",
        return_value=(object(), None, object()),
    )
    review = SimpleNamespace(matrix=SimpleNamespace())

    with pytest.raises(RuntimeError, match="public-finder correction"):
        evaluate_public_finder_correction_candidate_products(
            np.ones((3, 3)),
            np.ones((3, 3), dtype=np.bool_),
            np.zeros((3, 3)),
            np.ones((3, 3)),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=review,  # type: ignore[arg-type]
        )


def test_detection_view_returns_only_connected_detection(
    mocker: MockerFixture,
) -> None:
    """Detection-only diagnostics reuse the complete product evaluation."""
    detection = object()
    evaluate = mocker.patch(
        "hebog.validation.post_campaign_science."
        "evaluate_post_campaign_candidate_products",
        return_value=SimpleNamespace(detection=detection),
    )

    result = evaluate_post_campaign_candidate_detection(
        np.ones((2, 2)),
        np.ones((2, 2), dtype=np.bool_),
        np.zeros((2, 2)),
        np.ones((2, 2)),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=cast(Any, SimpleNamespace()),
    )

    assert result is detection
    assert evaluate.call_count == 1


def test_compact_diagnostic_always_requests_component_semantics(
    mocker: MockerFixture,
) -> None:
    """Future compilers cannot apply Rapthor source canonicalization."""
    sentinel = object()
    diagnose = mocker.patch(
        "hebog.validation.post_campaign_science."
        "diagnose_phase_four_realization",
        return_value=sentinel,
    )

    result = diagnose_compact_component_realization(
        cast(Any, SimpleNamespace()),
        cast(Any, SimpleNamespace()),
        (),
        implementation_identifier="hebog",
        outlier_thresholds=cast(Any, SimpleNamespace()),
        position_angle_minimum_axis_ratio=1.1,
    )

    assert result is sentinel
    _, kwargs = diagnose.call_args
    assert kwargs["catalogue_semantics"] == "fitted-gaussian-component"
