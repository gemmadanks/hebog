# pyright: reportMissingTypeStubs=false
"""Contracts for the prospective publication-scale-persistence repair."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
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

_ROOT = Path(__file__).parents[3]
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-publication-scale-persistence-pre-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-publication-scale-persistence-implementation-"
    "decision.json"
)
_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_publication_scale_persistence_products.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_publication_scale_persistence_smoke.py"
)
_DECISION_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"


def _historical_sha256(relative_path: str) -> str:
    """Hash one program at the revision that froze this decision."""
    contents = subprocess.run(
        ("git", "show", f"{_DECISION_REVISION}:{relative_path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(contents).hexdigest()


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


def test_pre_review_explains_failure_and_fixed_tradeoff_rule() -> None:
    """The correction is bound to the exact failure without gate tuning."""
    review = json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))

    assert review["binding_evidence"]["terminal_smoke_sha256"] == (
        "3280088263f12ae6e63b1f81cc77c71d0b0e2f86539be7ea8459823b61886993"
    )
    assert review["causal_review"]["observed_failure"]["endpoint_id"] == (
        "continuum--mask-precision--overall"
    )
    assert review["candidate_rule"]["policy_id"] == (
        "adjacent-scale-persistent-publication-with-owner-bridges-v1"
    )
    assert review["governed_tradeoff_rule"]["prohibitions"].startswith(
        "No threshold"
    )
    assert not review["authorization"]["threshold_or_margin_tuning_authorized"]


def test_configuration_binds_policy_and_exact_reviews() -> None:
    """The configuration cannot omit its predecessor or governed records."""
    repaired = public_finder_publication_scale_persistence_configuration(
        {"compact": {"mode": "fixed"}, "continuum": {"mode": "fixed"}},
        _PRE_REVIEW,
        _DECISION,
    )

    assert repaired["compact"] == {"mode": "fixed"}
    continuum = cast(dict[str, object], repaired["continuum"])
    assert continuum["publication_scale_persistence_policy"] == (
        "adjacent-scale-persistent-publication-with-owner-bridges-v1"
    )
    assert continuum["publication_scale_persistence_pre_review_sha256"] == (
        file_sha256(_PRE_REVIEW)
    )
    with pytest.raises(TypeError, match="must contain dictionaries"):
        public_finder_publication_scale_persistence_configuration(
            {"compact": {}, "continuum": "invalid"},
            _PRE_REVIEW,
            _DECISION,
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


def test_materializer_activates_the_actual_final_writer() -> None:
    """Every runpy layer resolves the new builder at product publication."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    frozen = wrapper["_current_composition"](
        _ROOT,
        revision="candidate-revision",
        configuration="candidate-configuration",
    )

    writer = frozen["_write_continuum_products"]
    separated_writer = writer.__globals__[  # pyright: ignore[reportFunctionMemberAccess]
        "_write_mask_separated_continuum_products"
    ]
    assert (
        separated_writer.__globals__[  # pyright: ignore[reportFunctionMemberAccess]
            "build_public_finder_source_reconstruction_continuum_products"
        ]
        is build_publication_scale_persistence_continuum_products
    )


def test_evaluator_dispatches_only_the_replacement_materializer() -> None:
    """The write-once evaluator cannot select a predecessor producer."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    base = evaluator["_base"](_ROOT)
    expected = (
        "scripts/validation/"
        "materialize_phase5_prospective_publication_scale_persistence_"
        "products.py"
    )

    assert base["_MATERIALIZER"] == expected
    assert base["main"].__globals__["_MATERIALIZER"] == expected


def test_implementation_decision_binds_exact_review_and_programs() -> None:
    """Every prospective byte is frozen before scientific execution."""
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_PRE_REVIEW),
    }
    for identity in decision["implementation"]:
        assert _historical_sha256(identity["path"]) == identity["sha256"]
