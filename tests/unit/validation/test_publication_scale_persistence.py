# pyright: reportMissingTypeStubs=false
"""Contracts for the prospective publication-scale-persistence repair."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.multiscale_association import build_scale_detection_plane
from hebog.validation.external_runners import file_sha256
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_campaign_science import (
    PostCampaignCandidateProducts,
)
from hebog.validation.publication_scale_persistence import (
    build_publication_scale_persistence_continuum_products,
    evaluate_publication_scale_persistence_candidate_products,
    public_finder_publication_scale_persistence_configuration,
)


def _scale_plane(
    support: np.ndarray[Any, np.dtype[np.bool_]],
    *,
    order: int,
) -> Any:
    """Build one exact analytic scale plane."""
    response = np.where(support, 1.0, 0.0)
    return build_scale_detection_plane(
        support,
        response,
        np.where(support, 8.0, 0.0),
        np.ones(support.shape, dtype=np.bool_),
        scale_order=order,
        nominal_scale_beam_fwhm=float(2 ** (order - 1)),
    )


def _candidate() -> PostCampaignCandidateProducts:
    """Return one candidate with persistent core and one-scale protrusion."""
    labels = np.zeros((11, 15), dtype=np.int32)
    labels[3:8, 3:9] = 4
    labels[5, 9:13] = 4
    detection = ThresholdFilterResult(
        combined_snr=np.where(labels > 0, 4.0, 0.0),
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
    )
    fine = np.zeros(labels.shape, dtype=np.bool_)
    fine[4:7, 4:8] = True
    fine[5, 9:13] = True
    coarse = np.zeros(labels.shape, dtype=np.bool_)
    coarse[4:7, 4:8] = True
    position = np.where(labels > 0, 1.0, 0.0)
    position.setflags(write=False)
    return PostCampaignCandidateProducts(
        detection=detection,
        direct_component_labels=labels,
        measurement_component_labels=labels,
        position_signal_jy_per_beam=position,
        significant_multiscale_support=fine | coarse,
        scale_detection_planes=(
            _scale_plane(fine, order=1),
            _scale_plane(coarse, order=2),
        ),
    )


def test_configuration_binds_policy_and_exact_reviews(tmp_path: Path) -> None:
    """The configuration cannot omit its predecessor or governed records."""
    pre_review = tmp_path / "pre-review.json"
    decision = tmp_path / "decision.json"
    pre_review.write_text("pre-review\n", encoding="utf-8")
    decision.write_text("decision\n", encoding="utf-8")
    repaired = public_finder_publication_scale_persistence_configuration(
        {"compact": {"mode": "fixed"}, "continuum": {"mode": "fixed"}},
        pre_review,
        decision,
    )

    assert repaired["compact"] == {"mode": "fixed"}
    continuum = cast(dict[str, object], repaired["continuum"])
    assert continuum["publication_scale_persistence_policy"] == (
        "adjacent-scale-persistent-publication-with-owner-bridges-v1"
    )
    assert continuum["publication_scale_persistence_pre_review_sha256"] == (
        file_sha256(pre_review)
    )
    assert continuum[
        "publication_scale_persistence_implementation_decision_sha256"
    ] == file_sha256(decision)
    with pytest.raises(TypeError, match="must contain dictionaries"):
        public_finder_publication_scale_persistence_configuration(
            {"compact": {}, "continuum": "invalid"},
            pre_review,
            decision,
        )


def test_evaluator_uses_persistence_without_changing_owner(
    mocker: MockerFixture,
) -> None:
    """The repair removes a one-scale protrusion and retains owner identity."""
    candidate = _candidate()
    mocker.patch(
        "hebog.validation.publication_scale_persistence."
        "evaluate_mask_origin_sibling_pair_candidate_products",
        return_value=candidate,
    )
    image = np.where(candidate.measurement_component_labels > 0, 4.0, 0.0)

    result = evaluate_publication_scale_persistence_candidate_products(
        image,
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape),
        np.ones(image.shape),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=cast(Any, SimpleNamespace()),
    )

    assert np.all(result.detection.component_labels[4:7, 4:8] == 4)
    assert np.all(result.detection.component_labels[5, 9:13] == 0)
    assert result.measurement_component_labels is (
        candidate.measurement_component_labels
    )
    assert result.direct_component_labels is candidate.direct_component_labels


def test_evaluator_accepts_direct_measurement_boundary_tie(
    mocker: MockerFixture,
) -> None:
    """Publication refinement receives the authoritative boundary owner."""
    direct = np.zeros((9, 13), dtype=np.int32)
    direct[2:7, 1:4] = 1
    direct[4, 4:7] = 1
    direct[2:7, 8:11] = 2
    significant = np.zeros(direct.shape, dtype=np.bool_)
    significant[4, 7] = True
    measurement = direct.copy()
    measurement[4, 7] = 1
    predecessor = PostCampaignCandidateProducts(
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
        return_value=predecessor,
    )

    result = evaluate_publication_scale_persistence_candidate_products(
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
    assert np.all((publication == 0) | (publication == measurement))


def test_builder_preserves_catalogue_measurement_inputs(
    mocker: MockerFixture,
) -> None:
    """Publication support cannot replace catalogue measurement ownership."""
    candidate = _candidate()
    mocker.patch(
        "hebog.validation.publication_scale_persistence."
        "evaluate_publication_scale_persistence_candidate_products",
        return_value=candidate,
    )
    association = object()
    catalogue_builder = mocker.patch(
        "hebog.validation.publication_scale_persistence."
        "build_hebog_reconstructed_source_catalogues",
        return_value=SimpleNamespace(
            source_catalogue=("source",),
            component_catalogue=("component",),
            association=association,
        ),
    )
    image = np.ones(candidate.detection.component_labels.shape)

    result = build_publication_scale_persistence_continuum_products(
        image,
        np.zeros(image.shape),
        np.ones(image.shape),
        fits.Header(),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=cast(Any, SimpleNamespace()),
    )

    assert result.source_association is association
    assert catalogue_builder.call_args.args[3] is (
        candidate.measurement_component_labels
    )
    assert catalogue_builder.call_args.args[4] is (
        candidate.direct_component_labels
    )


def test_evaluator_and_builder_reject_malformed_planes(
    mocker: MockerFixture,
) -> None:
    """The boundary fails closed on dimensional, validity, and RMS drift."""
    candidate = _candidate()
    mocker.patch(
        "hebog.validation.publication_scale_persistence."
        "evaluate_mask_origin_sibling_pair_candidate_products",
        return_value=candidate,
    )
    image = np.ones(candidate.detection.component_labels.shape)
    with pytest.raises(ValueError, match="aligned real"):
        evaluate_publication_scale_persistence_candidate_products(
            image[0],
            np.ones(image.shape, dtype=np.bool_),
            np.zeros(image.shape),
            np.ones(image.shape),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )
    with pytest.raises(ValueError, match="aligned boolean"):
        evaluate_publication_scale_persistence_candidate_products(
            image,
            np.ones(image.shape, dtype=np.int8),
            np.zeros(image.shape),
            np.ones(image.shape),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )
    background = np.zeros(image.shape)
    background[0, 0] = np.nan
    with pytest.raises(ValueError, match="validity differs"):
        build_publication_scale_persistence_continuum_products(
            image,
            background,
            np.ones(image.shape),
            fits.Header(),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )
