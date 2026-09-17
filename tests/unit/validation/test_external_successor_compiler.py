# pyright: reportMissingTypeStubs=false
"""Tests for the prospective external-comparison compiler kernel."""

from __future__ import annotations

import numpy as np
import pytest

from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
    measure_continuum_image,
    native_support_objects,
)
from hebog.validation.observable_truth import (
    measure_observable_truth,
    observable_truth_integrated_flux_jy,
)


def _truth(
    identifier: str,
    label: int,
    centre_xy: tuple[float, float],
    flux: float,
) -> ContinuumTruthObject:
    return ContinuumTruthObject(
        identifier=identifier,
        support_label=label,
        centre_xy=centre_xy,
        integrated_flux_jy=flux,
        catalogue_role="astronomical-source",
        strata=("morphology-diffuse",),
    )


def _candidate(
    identifier: str,
    label: int,
    centre_xy: tuple[float, float],
    flux: float,
) -> ContinuumCatalogueObject:
    return ContinuumCatalogueObject(
        identifier=identifier,
        support_label=label,
        centre_xy=centre_xy,
        integrated_flux_jy=flux,
    )


def test_observable_truth_flux_excludes_masked_and_off_image_signal() -> None:
    """Edge truth is normalized to the valid pixels a finder can observe."""
    signal = np.asarray(
        (
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
        ),
        dtype=np.float64,
    )
    valid = np.asarray(
        (
            (False, True, True),
            (False, True, False),
        ),
        dtype=np.bool_,
    )

    actual = observable_truth_integrated_flux_jy(
        signal,
        valid,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )

    beam_area_pixels = 2.0 * np.pi / (8.0 * np.log(2.0)) * 2.0
    assert actual == pytest.approx((2.0 + 3.0 + 5.0) / beam_area_pixels)


def test_observable_truth_flux_rejects_unmeasurable_domains() -> None:
    """Prospective truth cannot silently publish a zero or invalid flux."""
    with pytest.raises(ValueError, match="aligned two-dimensional"):
        observable_truth_integrated_flux_jy(
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 1), dtype=np.bool_),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="positive observable"):
        observable_truth_integrated_flux_jy(
            -np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.bool_),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="beam axes"):
        observable_truth_integrated_flux_jy(
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.bool_),
            beam_major_fwhm_pixels=float("nan"),
            beam_minor_fwhm_pixels=1.0,
        )


def test_observable_truth_uses_one_valid_domain_for_position_and_support() -> (
    None
):
    """Flux, centroid, and support metadata share the observable domain."""
    signal = np.asarray(
        (
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
        ),
        dtype=np.float64,
    )
    declared_support = np.asarray(
        (
            (True, True, False),
            (True, True, False),
        ),
        dtype=np.bool_,
    )
    valid = np.asarray(
        (
            (False, True, True),
            (False, True, False),
        ),
        dtype=np.bool_,
    )

    measurement = measure_observable_truth(
        signal,
        declared_support,
        valid,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )

    beam_area_pixels = np.pi / (2.0 * np.log(2.0))
    assert measurement.integrated_flux_jy == pytest.approx(
        (2.0 + 3.0 + 5.0) / beam_area_pixels
    )
    assert measurement.centroid_xy == pytest.approx((1.0, 5.0 / 7.0))
    assert measurement.declared_support_pixel_count == 4
    assert measurement.observable_support_pixel_count == 2
    assert measurement.observable_support_fraction == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("declared_support", "valid", "message"),
    (
        (
            np.ones((2, 2), dtype=np.int32),
            np.ones((2, 2), dtype=np.bool_),
            "boolean support",
        ),
        (
            np.zeros((2, 2), dtype=np.bool_),
            np.ones((2, 2), dtype=np.bool_),
            "declared support",
        ),
        (
            np.ones((2, 2), dtype=np.bool_),
            np.zeros((2, 2), dtype=np.bool_),
            "observable support",
        ),
    ),
)
def test_observable_truth_rejects_invalid_support_domains(
    declared_support: np.ndarray,
    valid: np.ndarray,
    message: str,
) -> None:
    """Truth support metadata cannot be empty, mistyped, or unobservable."""
    with pytest.raises(ValueError, match=message):
        measure_observable_truth(
            np.ones((2, 2), dtype=np.float64),
            declared_support,
            valid,
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )


def test_observable_truth_rejects_invalid_signal_and_support_flux() -> None:
    """Centroid truth requires a 2-D signal and positive support weights."""
    with pytest.raises(ValueError, match="aligned two-dimensional"):
        measure_observable_truth(
            np.ones((2, 2, 1), dtype=np.float64),
            np.ones((2, 2), dtype=np.bool_),
            np.ones((2, 2), dtype=np.bool_),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="support must have positive"):
        measure_observable_truth(
            np.asarray(((-1.0, -1.0), (3.0, 3.0)), dtype=np.float64),
            np.asarray(((True, True), (False, False)), dtype=np.bool_),
            np.ones((2, 2), dtype=np.bool_),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )


def test_native_support_objects_include_fitless_labels() -> None:
    """Every positive native label receives one topology-only object."""
    labels = np.asarray(
        (
            (0, 4, 4, 0, 0),
            (0, 4, 4, 9, 9),
            (0, 0, 0, 9, 9),
        ),
        dtype=np.int32,
    )

    supports = native_support_objects(labels)

    assert tuple(item.identifier for item in supports) == (
        "support-4",
        "support-9",
    )
    assert tuple(item.support_label for item in supports) == (4, 9)
    assert supports[0].centre_xy == pytest.approx((1.5, 0.5))
    assert supports[1].centre_xy == pytest.approx((3.5, 1.5))


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"identifier": ""}, "identifier"),
        ({"support_label": 0}, "support label"),
        ({"centre_xy": (np.nan, 0.0)}, "centre"),
        ({"integrated_flux_jy": 0.0}, "flux"),
    ),
)
def test_catalogue_objects_reject_nonphysical_fields(
    changes: dict[str, object],
    message: str,
) -> None:
    """Successor records cannot encode an invented measurement."""
    values: dict[str, object] = {
        "identifier": "source-1",
        "support_label": 1,
        "centre_xy": (1.0, 1.0),
        "integrated_flux_jy": 1.0,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        ContinuumCatalogueObject(**values)  # type: ignore[arg-type]


def test_truth_strata_must_be_canonical() -> None:
    """Duplicate or unsorted stratum identities cannot change endpoints."""
    with pytest.raises(ValueError, match="strata must be canonical"):
        ContinuumTruthObject(
            identifier="truth-1",
            support_label=1,
            centre_xy=(1.0, 1.0),
            integrated_flux_jy=1.0,
            catalogue_role="astronomical-source",
            strata=("z", "a", "z"),
        )


def test_truth_role_must_be_supported() -> None:
    """A runtime-invalid role cannot silently change endpoint membership."""
    with pytest.raises(ValueError, match="catalogue role is unsupported"):
        ContinuumTruthObject(
            identifier="truth-1",
            support_label=1,
            centre_xy=(1.0, 1.0),
            integrated_flux_jy=1.0,
            catalogue_role="unknown",  # type: ignore[arg-type]
            strata=("morphology-diffuse",),
        )


@pytest.mark.parametrize(
    "labels",
    (
        np.asarray((0, 1), dtype=np.int32),
        np.asarray(((0.0, 1.0),), dtype=np.float64),
        np.asarray(((0, -1),), dtype=np.int32),
    ),
)
def test_native_supports_reject_invalid_label_planes(
    labels: np.ndarray,
) -> None:
    """Topology objects require exact non-negative integer planes."""
    with pytest.raises(ValueError, match="candidate label plane"):
        native_support_objects(labels)


def test_mask_only_support_participates_in_split_topology() -> None:
    """A fitless half of one detection split remains in the denominator."""
    truth_labels = np.zeros((5, 7), dtype=np.int32)
    truth_labels[1:3, 1:5] = 1
    candidate_labels = np.zeros_like(truth_labels)
    candidate_labels[1:3, 1:3] = 1
    candidate_labels[1:3, 3:5] = 2
    truth = (_truth("truth-1", 1, (2.5, 1.5), 2.0),)
    catalogue = (_candidate("source-1", 1, (1.5, 1.5), 2.0),)

    metrics = measure_continuum_image(
        truth,
        catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 1.0
    assert metrics["reliability"]["overall"] == 1.0
    assert metrics["mask-recall"]["overall"] == 1.0
    assert metrics["split-fraction"]["overall"] == 1.0


def test_mask_only_support_does_not_invent_catalogue_measurements() -> None:
    """Label-only recovery stays absent from catalogue and flux metrics."""
    truth_labels = np.zeros((6, 8), dtype=np.int32)
    truth_labels[1:3, 1:3] = 1
    truth_labels[3:5, 5:7] = 2
    candidate_labels = truth_labels.copy()
    truth = (
        _truth("truth-1", 1, (1.5, 1.5), 2.0),
        _truth("truth-2", 2, (5.5, 3.5), 3.0),
    )
    catalogue = (_candidate("source-1", 1, (1.5, 1.5), 2.0),)

    metrics = measure_continuum_image(
        truth,
        catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 0.5
    assert metrics["reliability"]["overall"] == 1.0
    assert metrics["integrated-flux-median"]["overall"] == (0.0,)
    assert metrics["mask-recall"]["overall"] == 1.0


def test_mask_only_detection_without_any_row_stays_explicit() -> None:
    """A label-only detection has mask recovery but unavailable measurement."""
    labels = np.zeros((4, 4), dtype=np.int32)
    labels[1:3, 1:3] = 1
    truth = (_truth("truth-1", 1, (1.5, 1.5), 2.0),)

    metrics = measure_continuum_image(
        truth,
        (),
        truth_label_plane=labels,
        candidate_label_plane=labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 0.0
    assert metrics["reliability"]["overall"] == 0.0
    assert metrics["integrated-flux-median"]["overall"] == ()
    assert metrics["mask-recall"]["overall"] == 1.0


def test_artifact_match_is_excluded_from_conditional_measurements() -> None:
    """Artifact topology cannot create an astronomical flux observation."""
    labels = np.zeros((4, 4), dtype=np.int32)
    labels[1:3, 1:3] = 1
    truth = (
        ContinuumTruthObject(
            identifier="artifact-1",
            support_label=1,
            centre_xy=(1.5, 1.5),
            integrated_flux_jy=2.0,
            catalogue_role="artifact",
            strata=("morphology-artifact",),
        ),
    )

    metrics = measure_continuum_image(
        truth,
        (_candidate("candidate-1", 1, (1.5, 1.5), 2.0),),
        truth_label_plane=labels,
        candidate_label_plane=labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 1.0
    assert metrics["integrated-flux-median"]["overall"] == ()


def test_measurement_rejects_incomplete_or_misaligned_inputs() -> None:
    """The successor rejects missing truth and broken plane identity."""
    labels = np.asarray(((1, 1), (0, 0)), dtype=np.int32)
    truth = (_truth("truth-1", 1, (0.5, 0.0), 1.0),)

    with pytest.raises(ValueError, match="truth must not be empty"):
        measure_continuum_image(
            (),
            (),
            truth_label_plane=labels,
            candidate_label_plane=labels,
            beam_fwhm_pixels=2.0,
        )
    with pytest.raises(ValueError, match="must share shape"):
        measure_continuum_image(
            truth,
            (),
            truth_label_plane=labels,
            candidate_label_plane=np.zeros((3, 3), dtype=np.int32),
            beam_fwhm_pixels=2.0,
        )
    with pytest.raises(ValueError, match="absent from native labels"):
        measure_continuum_image(
            truth,
            (_candidate("source-2", 2, (0.5, 0.0), 1.0),),
            truth_label_plane=labels,
            candidate_label_plane=labels,
            beam_fwhm_pixels=2.0,
        )
