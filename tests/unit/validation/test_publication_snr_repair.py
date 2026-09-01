# pyright: reportMissingTypeStubs=false
"""Behaviour tests for the prospective publication-S/N repair."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.publication_snr_repair import (
    build_publication_snr_repaired_continuum_products,
    evaluate_publication_snr_repaired_candidate_products,
    public_finder_publication_snr_repair_configuration,
)


def test_configuration_requires_compact_and_continuum_mappings(
    tmp_path: Any,
) -> None:
    """Malformed predecessor identities fail before hashing evidence."""
    with pytest.raises(TypeError, match="must contain dictionaries"):
        public_finder_publication_snr_repair_configuration(
            {"compact": {}, "continuum": "not-a-mapping"},
            tmp_path / "missing-review.json",
            tmp_path / "missing-decision.json",
        )


@pytest.mark.parametrize(
    ("values", "message"),
    (
        (np.ones((2, 2), dtype=np.complex128), "aligned real"),
        (np.ones(2), "aligned real"),
    ),
)
def test_repaired_evaluator_rejects_invalid_image_planes(
    mocker: MockerFixture,
    values: np.ndarray[Any, Any],
    message: str,
) -> None:
    """Publication statistics accept only aligned real image planes."""
    mocker.patch(
        "hebog.validation.publication_snr_repair."
        "evaluate_public_finder_correction_candidate_products",
        return_value=object(),
    )
    with pytest.raises(ValueError, match=message):
        evaluate_publication_snr_repaired_candidate_products(
            values,
            np.ones((2, 2), dtype=np.bool_),
            np.zeros((2, 2)),
            np.ones((2, 2)),
            beam=BeamShapePixels(2.0, 1.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )


@pytest.mark.parametrize(
    "valid",
    (
        np.ones((3, 2), dtype=np.bool_),
        np.ones((2, 2), dtype=np.uint8),
    ),
)
def test_repaired_evaluator_requires_aligned_boolean_validity(
    mocker: MockerFixture,
    valid: np.ndarray[Any, Any],
) -> None:
    """Validity cannot be reshaped or coerced after predecessor evaluation."""
    labels = np.ones((2, 2), dtype=np.int32)
    products = SimpleNamespace(
        measurement_component_labels=labels,
        significant_multiscale_support=np.ones(labels.shape, dtype=np.bool_),
    )
    mocker.patch(
        "hebog.validation.publication_snr_repair."
        "evaluate_public_finder_correction_candidate_products",
        return_value=products,
    )

    with pytest.raises(ValueError, match="aligned boolean"):
        evaluate_publication_snr_repaired_candidate_products(
            np.ones(labels.shape),
            valid,
            np.zeros(labels.shape),
            np.ones(labels.shape),
            beam=BeamShapePixels(2.0, 1.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )


def test_continuum_builder_composes_repaired_mask_with_source_catalogues(
    mocker: MockerFixture,
) -> None:
    """The overlay changes support but reuses source measurement."""
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
        "hebog.validation.publication_snr_repair."
        "evaluate_publication_snr_repaired_candidate_products",
        return_value=candidate,
    )
    association = object()
    build_catalogues = mocker.patch(
        "hebog.validation.publication_snr_repair."
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
    header = fits.Header()
    beam = BeamShapePixels(2.0, 1.0, 0.0)
    review = cast(Any, SimpleNamespace())

    result = build_publication_snr_repaired_continuum_products(
        image,
        background,
        rms,
        header,
        beam=beam,
        review=review,
    )

    assert result.detection is detection
    assert result.catalogue == ("source",)
    assert result.component_catalogue == ("component",)
    assert result.source_association is association
    assert result.valid_pixels.flags.writeable is False
    evaluate.assert_called_once()
    assert evaluate.call_args.args[:4] == (
        image,
        result.valid_pixels,
        background,
        rms,
    )
    build_catalogues.assert_called_once()
    assert (
        build_catalogues.call_args.kwargs["measurement_aperture_radius_beams"]
        == 1.5
    )


def test_continuum_builder_rejects_mean_rms_validity_mismatch() -> None:
    """A finite image pixel cannot silently lose its scientific context."""
    image = np.ones((2, 2))
    background = np.zeros((2, 2))
    background[0, 0] = np.nan

    with pytest.raises(ValueError, match="validity differs from image"):
        build_publication_snr_repaired_continuum_products(
            image,
            background,
            np.ones((2, 2)),
            fits.Header(),
            beam=BeamShapePixels(2.0, 1.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )
