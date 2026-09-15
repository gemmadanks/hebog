# pyright: reportMissingTypeStubs=false
"""Contracts for the prospective mask-origin and sibling-pair candidate."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.external_runners import file_sha256
from hebog.validation.mask_origin_sibling_pair import (
    build_mask_origin_sibling_pair_continuum_products,
    evaluate_mask_origin_sibling_pair_candidate_products,
    public_finder_mask_origin_sibling_pair_configuration,
)
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_campaign_science import (
    PostCampaignCandidateProducts,
)


def test_configuration_binds_both_policies_and_exact_reviews(
    tmp_path: Path,
) -> None:
    """The candidate identity records both prospective scientific changes."""
    review = tmp_path / "review.json"
    decision = tmp_path / "decision.json"
    review.write_text("review\n", encoding="utf-8")
    decision.write_text("decision\n", encoding="utf-8")

    configuration = public_finder_mask_origin_sibling_pair_configuration(
        {"compact": {"unchanged": True}, "continuum": {"base": "exact"}},
        review,
        decision,
    )

    assert configuration["compact"] == {"unchanged": True}
    continuum = configuration["continuum"]
    assert isinstance(continuum, dict)
    assert continuum["base"] == "exact"
    assert continuum["publication_mask_origin_policy"] == (
        "immutable-direct-owner-publication-origin-v1"
    )
    assert continuum["persistent_sibling_pair_policy"] == (
        "adjacent-scale-mutually-unique-envelope-pair-with-connected-support-v1"
    )
    assert continuum["mask_origin_sibling_pair_pre_review_sha256"] == (
        file_sha256(review)
    )
    assert continuum[
        "mask_origin_sibling_pair_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_configuration_rejects_malformed_base(tmp_path: Path) -> None:
    """Malformed predecessor identities fail before evidence is hashed."""
    with pytest.raises(TypeError, match="must contain dictionaries"):
        public_finder_mask_origin_sibling_pair_configuration(
            {"compact": {}, "continuum": "invalid"},
            tmp_path / "review.json",
            tmp_path / "decision.json",
        )


def test_continuum_builder_preserves_measurement_catalogue_inputs(
    mocker: MockerFixture,
) -> None:
    """Publication origin does not replace association measurement support."""
    shape = (3, 4)
    labels = np.ones(shape, dtype=np.int32)
    detection = ThresholdFilterResult(
        combined_snr=np.ones(shape),
        retained_mask=np.ones(shape, dtype=np.bool_),
        component_labels=labels,
        component_count=1,
    )
    candidate = SimpleNamespace(
        detection=detection,
        measurement_component_labels=labels,
        direct_component_labels=labels,
        significant_multiscale_support=np.ones(shape, dtype=np.bool_),
        scale_detection_planes=(),
        position_signal_jy_per_beam=np.ones(shape),
    )
    evaluate = mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "evaluate_mask_origin_sibling_pair_candidate_products",
        return_value=candidate,
    )
    association = object()
    catalogue_builder = mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "build_hebog_reconstructed_source_catalogues",
        return_value=SimpleNamespace(
            source_catalogue=("source",),
            component_catalogue=("component",),
            association=association,
        ),
    )
    image = np.ones(shape)
    background = np.zeros(shape)
    rms = np.ones(shape)

    result = build_mask_origin_sibling_pair_continuum_products(
        image,
        background,
        rms,
        fits.Header(),
        beam=BeamShapePixels(2.0, 1.0, 0.0),
        review=cast(Any, SimpleNamespace()),
    )

    assert result.detection is detection
    assert result.measurement_component_labels is labels
    assert result.source_association is association
    assert result.valid_pixels.flags.writeable is False
    evaluate.assert_called_once()
    assert catalogue_builder.call_args.args[3] is labels
    assert catalogue_builder.call_args.args[4] is labels


def test_publication_footprint_inherits_authoritative_measurement_owner(
    mocker: MockerFixture,
) -> None:
    """A recovered tie pixel cannot disagree with measurement ownership."""
    direct = np.zeros((9, 13), dtype=np.int32)
    direct[2:7, 1:4] = 1
    direct[4, 4:7] = 1
    direct[2:7, 8:11] = 2
    significant = np.zeros(direct.shape, dtype=np.bool_)
    significant[4, 7] = True
    measurement = direct.copy()
    measurement[4, 7] = 1
    candidate = PostCampaignCandidateProducts(
        detection=ThresholdFilterResult(
            combined_snr=np.full(direct.shape, 4.0),
            retained_mask=measurement > 0,
            component_labels=measurement,
            component_count=2,
        ),
        direct_component_labels=direct,
        measurement_component_labels=measurement,
        position_signal_jy_per_beam=np.full(direct.shape, 4.0),
        significant_multiscale_support=significant,
        scale_detection_planes=(),
    )
    mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "evaluate_publication_snr_repaired_candidate_products",
        return_value=candidate,
    )

    result = evaluate_mask_origin_sibling_pair_candidate_products(
        np.full(direct.shape, 4.0),
        np.ones(direct.shape, dtype=np.bool_),
        np.zeros(direct.shape),
        np.ones(direct.shape),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=cast(
            Any,
            SimpleNamespace(matrix=SimpleNamespace(island_sigma=3.0)),
        ),
    )

    publication = result.detection.component_labels
    assert publication[4, 7] == 1
    assert np.all((publication == 0) | (publication == measurement))


def test_publication_excludes_disconnected_recovery_without_owner(
    mocker: MockerFixture,
) -> None:
    """Nearby disconnected scale support cannot become a publication pixel."""
    direct = np.zeros((7, 9), dtype=np.int32)
    direct[2:5, 1:4] = 1
    significant = np.zeros(direct.shape, dtype=np.bool_)
    significant[3, 5] = True
    candidate = PostCampaignCandidateProducts(
        detection=ThresholdFilterResult(
            combined_snr=np.where(direct > 0, 6.0, 0.0),
            retained_mask=direct > 0,
            component_labels=direct,
            component_count=1,
        ),
        direct_component_labels=direct,
        measurement_component_labels=direct,
        position_signal_jy_per_beam=np.zeros(direct.shape),
        significant_multiscale_support=significant,
        scale_detection_planes=(),
    )
    mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "evaluate_publication_snr_repaired_candidate_products",
        return_value=candidate,
    )

    result = evaluate_mask_origin_sibling_pair_candidate_products(
        np.full(direct.shape, 6.0),
        np.ones(direct.shape, dtype=np.bool_),
        np.zeros(direct.shape),
        np.ones(direct.shape),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=cast(
            Any,
            SimpleNamespace(matrix=SimpleNamespace(island_sigma=3.0)),
        ),
    )

    publication = result.detection.component_labels
    assert publication[3, 5] == 0
    assert np.all(publication[2:5, 1:4] == 1)
    assert np.all((publication == 0) | (publication == direct))


@pytest.mark.parametrize(
    ("shape", "direct_bounds", "recovered_pixels"),
    [
        ((7, 13), (0, 3, 0, 3), ((0, 4),)),
        ((7, 13), (4, 7, 10, 13), ((6, 8),)),
        ((6, 15), (0, 1, 5, 10), ((2, 7),)),
        ((15, 6), (5, 10, 0, 1), ((7, 2),)),
    ],
    ids=("top-left", "bottom-right", "thin-horizontal", "thin-vertical"),
)
def test_publication_owner_domain_holds_across_boundary_geometries(
    mocker: MockerFixture,
    shape: tuple[int, int],
    direct_bounds: tuple[int, int, int, int],
    recovered_pixels: tuple[tuple[int, int], ...],
) -> None:
    """Boundary geometries cannot publish unowned pixels."""
    y_start, y_stop, x_start, x_stop = direct_bounds
    direct = np.zeros(shape, dtype=np.int32)
    direct[y_start:y_stop, x_start:x_stop] = 7
    significant = np.zeros(shape, dtype=np.bool_)
    for y_pixel, x_pixel in recovered_pixels:
        significant[y_pixel, x_pixel] = True
    candidate = PostCampaignCandidateProducts(
        detection=ThresholdFilterResult(
            combined_snr=np.where(direct > 0, 6.0, 0.0),
            retained_mask=direct > 0,
            component_labels=direct,
            component_count=1,
        ),
        direct_component_labels=direct,
        measurement_component_labels=direct,
        position_signal_jy_per_beam=np.zeros(shape),
        significant_multiscale_support=significant,
        scale_detection_planes=(),
    )
    mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "evaluate_publication_snr_repaired_candidate_products",
        return_value=candidate,
    )

    result = evaluate_mask_origin_sibling_pair_candidate_products(
        np.full(shape, 6.0),
        np.ones(shape, dtype=np.bool_),
        np.zeros(shape),
        np.ones(shape),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=cast(
            Any,
            SimpleNamespace(matrix=SimpleNamespace(island_sigma=3.0)),
        ),
    )

    publication = result.detection.component_labels
    assert np.all((publication == 0) | (publication == direct))
    assert not np.any((publication > 0) & (direct == 0))


def test_publication_rejects_direct_support_without_measurement_owner(
    mocker: MockerFixture,
) -> None:
    """Malformed predecessor direct support cannot lose its owner."""
    direct = np.zeros((5, 5), dtype=np.int32)
    direct[2, 2] = 1
    empty = np.zeros(direct.shape, dtype=np.int32)
    candidate = PostCampaignCandidateProducts(
        detection=ThresholdFilterResult(
            combined_snr=np.zeros(direct.shape),
            retained_mask=empty > 0,
            component_labels=empty,
            component_count=0,
        ),
        direct_component_labels=direct,
        measurement_component_labels=empty,
        position_signal_jy_per_beam=np.zeros(direct.shape),
        significant_multiscale_support=np.zeros(
            direct.shape,
            dtype=np.bool_,
        ),
        scale_detection_planes=(),
    )
    mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "evaluate_publication_snr_repaired_candidate_products",
        return_value=candidate,
    )

    with pytest.raises(
        ValueError,
        match=(
            "direct support must be an exact subset of measurement ownership"
        ),
    ):
        evaluate_mask_origin_sibling_pair_candidate_products(
            np.full(direct.shape, 6.0),
            np.ones(direct.shape, dtype=np.bool_),
            np.zeros(direct.shape),
            np.ones(direct.shape),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(
                Any,
                SimpleNamespace(matrix=SimpleNamespace(island_sigma=3.0)),
            ),
        )


def test_continuum_builder_rejects_mean_rms_validity_mismatch() -> None:
    """A finite image pixel cannot silently lose its scientific context."""
    image = np.ones((2, 2))
    background = np.zeros((2, 2))
    background[0, 0] = np.nan

    with pytest.raises(ValueError, match="validity differs from image"):
        build_mask_origin_sibling_pair_continuum_products(
            image,
            background,
            np.ones((2, 2)),
            fits.Header(),
            beam=BeamShapePixels(2.0, 1.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )
