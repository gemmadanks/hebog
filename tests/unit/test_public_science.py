"""Unit contracts for configurable public scientific composition."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from hebog import public_science
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


def _header(shape: tuple[int, int]) -> fits.Header:
    """Return one valid one-arcsecond celestial fixture header."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = shape[1]
    header["NAXIS2"] = shape[0]
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = (shape[1] + 1) / 2
    header["CRPIX2"] = (shape[0] + 1) / 2
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 5.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    return header


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


def test_configured_builder_deblends_components_before_catalogue_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public composition cannot bypass compact component topology."""
    normalized = np.zeros((11, 12), dtype=np.float64)
    normalized[2:9, 2:10] = np.array([6.0, 5.0, 4.0, 3.0, 3.0, 4.0, 5.0, 9.0])
    direct = np.where(normalized >= 3.0, 17, 0).astype(np.int32)
    measurement = direct.copy()
    measurement[1:10, 1:11] = 17
    products = _products(direct, measurement_labels=measurement)
    captured: dict[str, np.ndarray] = {}

    def return_products(
        *_args: object,
        **_kwargs: object,
    ) -> PostCampaignCandidateProducts:
        return products

    monkeypatch.setattr(
        public_science,
        "evaluate_publication_scale_persistence_candidate_products",
        return_products,
    )

    def capture_catalogues(
        image: np.ndarray,
        background: np.ndarray,
        valid: np.ndarray,
        measurement_labels: np.ndarray,
        direct_labels: np.ndarray,
        *args: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        del image, background, valid, args, kwargs
        captured["measurement"] = measurement_labels
        captured["direct"] = direct_labels
        return SimpleNamespace(
            source_catalogue=(),
            component_catalogue=(),
            association=object(),
        )

    monkeypatch.setattr(
        public_science,
        "build_hebog_reconstructed_source_catalogues",
        capture_catalogues,
    )
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )

    result = build_configured_continuum_products(
        normalized,
        np.zeros(normalized.shape, dtype=np.float64),
        np.ones(normalized.shape, dtype=np.float64),
        fits.Header(),
        beam=BeamShapePixels(5.0, 4.0, 0.0),
        review=review,
        config=SourceFinderConfig(5.0, 3.0, 7),
    )

    assert result is not None
    assert set(np.unique(captured["direct"])) == {0, 1, 2}
    assert set(np.unique(captured["measurement"])) == {0, 1, 2}
    np.testing.assert_array_equal(captured["direct"] > 0, direct > 0)
    np.testing.assert_array_equal(
        captured["measurement"] > 0,
        measurement > 0,
    )


def test_configured_builder_publishes_components_and_associated_source() -> (
    None
):
    """A connected two-peak island has two components in one source."""
    yy, xx = np.mgrid[:65, :65]
    normalized = 10.0 * np.exp(
        -((yy - 32) ** 2 + (xx - 29) ** 2) / 8.0
    ) + 9.5 * np.exp(-((yy - 32) ** 2 + (xx - 36) ** 2) / 8.0)
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )

    result = build_configured_continuum_products(
        normalized,
        np.zeros(normalized.shape, dtype=np.float64),
        np.ones(normalized.shape, dtype=np.float64),
        _header(normalized.shape),
        beam=BeamShapePixels(5.0, 4.0, 0.0),
        review=review,
        config=SourceFinderConfig(5.0, 3.0, 7),
    )

    assert result is not None
    assert result.detection.component_count == 1
    assert len(result.component_catalogue) == 2
    assert len(result.catalogue) == 1
    assert result.catalogue[0].component_count == 2
    assert result.deblended_parent_count == 1
    assert result.deferred_deblend_parent_count == 0
    assert tuple(
        len(membership.component_ids)
        for membership in result.source_association.memberships
    ) == (2,)


def test_configured_builder_retains_three_components_in_one_parent() -> None:
    """Multi-peak topology is not limited to a pairwise special case."""
    yy, xx = np.mgrid[:65, :65]
    normalized = np.zeros(yy.shape, dtype=np.float64)
    for amplitude, x_center in ((10.0, 25), (9.5, 32), (9.0, 39)):
        normalized += amplitude * np.exp(
            -((yy - 32) ** 2 + (xx - x_center) ** 2) / 8.0
        )
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )

    result = build_configured_continuum_products(
        normalized,
        np.zeros(normalized.shape, dtype=np.float64),
        np.ones(normalized.shape, dtype=np.float64),
        _header(normalized.shape),
        beam=BeamShapePixels(5.0, 4.0, 0.0),
        review=review,
        config=SourceFinderConfig(5.0, 3.0, 7),
    )

    assert result is not None
    assert result.detection.component_count == 1
    assert len(result.component_catalogue) == 3
    assert len(result.catalogue) == 1
    assert result.catalogue[0].component_count == 3
    assert result.deblended_parent_count == 1
    assert result.deferred_deblend_parent_count == 0
    assert tuple(
        len(membership.component_ids)
        for membership in result.source_association.memberships
    ) == (3,)
