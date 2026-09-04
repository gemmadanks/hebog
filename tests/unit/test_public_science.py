"""Unit contracts for configurable public scientific composition."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.public_science import (
    _aligned_plane,
    _execution_review,
    _retain_configured_islands,
    build_configured_continuum_products,
)
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_campaign_science import (
    PostCampaignCandidateProducts,
)

_ROOT = Path(__file__).parents[2]


def _config(
    *,
    minimum_island_pixels: int = 1,
    maximum_island_pixels: int | None = None,
) -> SourceFinderConfig:
    """Return one valid caller-owned configuration."""
    return SourceFinderConfig(
        detection_threshold_sigma=8.0,
        island_threshold_sigma=6.0,
        minimum_island_pixels=minimum_island_pixels,
        maximum_island_pixels=maximum_island_pixels,
    )


def _products(
    direct_labels: np.ndarray,
    *,
    measurement_labels: np.ndarray | None = None,
) -> PostCampaignCandidateProducts:
    """Build minimal terminal products around exact label planes."""
    direct = np.asarray(direct_labels, dtype=np.int32)
    measurement = np.asarray(
        direct if measurement_labels is None else measurement_labels,
        dtype=np.int32,
    )
    return PostCampaignCandidateProducts(
        detection=ThresholdFilterResult(
            combined_snr=np.ones(direct.shape, dtype=np.float64),
            retained_mask=np.asarray(measurement > 0, dtype=np.bool_),
            component_labels=measurement,
            component_count=int(np.count_nonzero(np.unique(measurement) > 0)),
        ),
        direct_component_labels=direct,
        measurement_component_labels=measurement,
        position_signal_jy_per_beam=np.ones(direct.shape, dtype=np.float64),
        significant_multiscale_support=np.asarray(
            measurement > 0,
            dtype=np.bool_,
        ),
        scale_detection_planes=(),
    )


def test_execution_review_changes_only_runtime_thresholds() -> None:
    """Caller sigma values do not mutate the frozen review record."""
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )

    execution = _execution_review(review, _config())

    assert (review.matrix.detection_sigma, review.matrix.island_sigma) == (
        5.0,
        3.0,
    )
    assert (
        execution.matrix.detection_sigma,
        execution.matrix.island_sigma,
    ) == (8.0, 6.0)
    assert execution.corrections is review.corrections


def test_island_limits_filter_every_terminal_identity_plane() -> None:
    """Minimum and maximum limits retain only accepted direct islands."""
    products = _products(np.array([[1, 1, 0], [2, 2, 2]], dtype=np.int32))

    retained = _retain_configured_islands(
        products,
        _config(minimum_island_pixels=2, maximum_island_pixels=2),
    )

    assert retained is not None
    expected = np.array([[1, 1, 0], [0, 0, 0]], dtype=np.int32)
    np.testing.assert_array_equal(retained.direct_component_labels, expected)
    np.testing.assert_array_equal(
        retained.measurement_component_labels,
        expected,
    )
    np.testing.assert_array_equal(
        retained.detection.component_labels,
        expected,
    )
    assert retained.detection.component_count == 1
    assert not retained.detection.component_labels.flags.writeable


def test_island_limits_can_select_an_empty_catalogue() -> None:
    """An island-size cut may honestly remove every detected component."""
    products = _products(np.array([[1, 1, 0]], dtype=np.int32))

    assert (
        _retain_configured_islands(
            products,
            _config(minimum_island_pixels=3),
        )
        is None
    )


def test_island_filter_rejects_inconsistent_label_identity() -> None:
    """Measurement labels cannot introduce an unknown direct component."""
    products = _products(
        np.array([[1, 1, 0]], dtype=np.int32),
        measurement_labels=np.array([[1, 3, 0]], dtype=np.int32),
    )

    with pytest.raises(ValueError, match="labels are inconsistent"):
        _retain_configured_islands(products, _config())


@pytest.mark.parametrize(
    "values, shape",
    [
        (np.ones((2, 2), dtype=np.complex128), None),
        (np.ones((2, 2), dtype=np.float64), (3, 2)),
    ],
)
def test_aligned_plane_rejects_invalid_public_science_inputs(
    values: np.ndarray,
    shape: tuple[int, int] | None,
) -> None:
    """The adapter fails closed on complex or misaligned planes."""
    with pytest.raises(ValueError, match="aligned real two-dimensional"):
        _aligned_plane(values, name="test", shape=shape)


def test_configured_builder_rejects_inconsistent_finite_support() -> None:
    """Finite image pixels require finite background and RMS values."""
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )
    image = np.ones((2, 2), dtype=np.float64)
    background = np.zeros((2, 2), dtype=np.float64)
    background[0, 0] = np.nan

    with pytest.raises(ValueError, match="validity differs from image"):
        build_configured_continuum_products(
            image,
            background,
            np.ones((2, 2), dtype=np.float64),
            fits.Header(),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=review,
            config=_config(),
        )
