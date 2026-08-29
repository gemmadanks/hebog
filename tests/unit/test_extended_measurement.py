"""Tests for standard-practice irregular extended-position measurement."""

from __future__ import annotations

from typing import cast

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
    clean_detected_segment_labels,
    expand_detected_segment_labels,
    measure_detected_segment_position,
    refine_multiscale_segment_labels,
)


def test_seeded_multiscale_ownership_cannot_merge_a_diffuse_bridge() -> None:
    """Two direct seeds stay distinct even when scale support joins them."""
    seeds = np.zeros((9, 13), dtype=np.int32)
    seeds[4, 2] = 9
    seeds[4, 10] = 3
    significant = np.zeros(seeds.shape, dtype=np.bool_)
    significant[3:6, 2:11] = True
    valid = np.ones(seeds.shape, dtype=np.bool_)

    owned = assign_seeded_multiscale_support(
        seeds,
        significant,
        valid,
        beam_major_fwhm_pixels=16.0,
    )

    assert owned[4, 2] == 9
    assert owned[4, 10] == 3
    assert owned[4, 6] == 9
    assert set(np.unique(owned)) == {0, 3, 9}


def test_seeded_multiscale_ownership_recovers_wings_without_new_identity() -> (
    None
):
    """One direct seed receives bounded wings and no synthetic source."""
    seeds = np.zeros((9, 9), dtype=np.int32)
    seeds[4, 4] = 7
    significant = np.zeros(seeds.shape, dtype=np.bool_)
    significant[2:7, 2:7] = True
    valid = np.ones(seeds.shape, dtype=np.bool_)
    valid[4, 6] = False

    owned = assign_seeded_multiscale_support(
        seeds,
        significant,
        valid,
        beam_major_fwhm_pixels=4.0,
    )

    assert set(np.unique(owned)) == {0, 7}
    assert owned[2, 4] == 7
    assert owned[4, 6] == 0
    assert owned[2, 2] == 0


def test_seeded_ownership_excludes_disconnected_nearby_support() -> None:
    """A nearby significant island needs an eight-connected seed path."""
    seeds = np.zeros((9, 9), dtype=np.int32)
    seeds[4, 2] = 7
    significant = np.zeros(seeds.shape, dtype=np.bool_)
    significant[4, 2:5] = True
    significant[3:6, 6:8] = True

    owned = assign_seeded_multiscale_support(
        seeds,
        significant,
        np.ones(seeds.shape, dtype=np.bool_),
        beam_major_fwhm_pixels=12.0,
    )

    assert np.all(owned[3:6, 6:8] == 0)
    assert np.all(owned[4, 2:5] == 7)


def test_seeded_multiscale_ownership_cannot_cross_invalid_gap() -> None:
    """Invalid pixels break reconstructed support connectivity."""
    seeds = np.zeros((7, 9), dtype=np.int32)
    seeds[3, 1] = 4
    significant = np.zeros(seeds.shape, dtype=np.bool_)
    significant[3, 1:8] = True
    valid = np.ones(seeds.shape, dtype=np.bool_)
    valid[:, 4] = False

    owned = assign_seeded_multiscale_support(
        seeds,
        significant,
        valid,
        beam_major_fwhm_pixels=20.0,
    )

    assert np.all(owned[:, 5:] == 0)
    assert owned[3, 3] == 4
    assert owned[3, 1] == 4


def test_seeded_multiscale_ownership_clips_cleanly_at_image_edge() -> None:
    """An edge seed owns only finite in-image support within the radius."""
    seeds = np.zeros((4, 4), dtype=np.int32)
    seeds[0, 0] = 5
    support = np.ones(seeds.shape, dtype=np.bool_)

    owned = assign_seeded_multiscale_support(
        seeds,
        support,
        np.ones(seeds.shape, dtype=np.bool_),
        beam_major_fwhm_pixels=4.0,
    )

    assert owned[0, 0] == 5
    assert owned[0, 2] == 5
    assert owned[2, 0] == 5
    assert owned[2, 2] == 0


def test_seeded_multiscale_tie_uses_global_seed_identity_not_label_value() -> (
    None
):
    """Relabelling task-local integers cannot change a bisector owner."""
    significant = np.zeros((5, 7), dtype=np.bool_)
    significant[2, 1:6] = True
    valid = np.ones(significant.shape, dtype=np.bool_)

    first = np.zeros(significant.shape, dtype=np.int32)
    first[2, 1] = 40
    first[2, 5] = 2
    second = np.zeros(significant.shape, dtype=np.int32)
    second[2, 1] = 3
    second[2, 5] = 80

    first_owned = assign_seeded_multiscale_support(
        first,
        significant,
        valid,
        beam_major_fwhm_pixels=8.0,
    )
    second_owned = assign_seeded_multiscale_support(
        second,
        significant,
        valid,
        beam_major_fwhm_pixels=8.0,
    )

    assert first_owned[2, 3] == 40
    assert second_owned[2, 3] == 3
    np.testing.assert_array_equal(
        first_owned == first_owned[2, 1],
        second_owned == second_owned[2, 1],
    )


def test_seeded_multiscale_tie_considers_every_equidistant_seed() -> None:
    """A high-order lattice tie still selects the first global identity."""
    seeds = np.zeros((13, 13), dtype=np.int32)
    centre_yx = (6, 6)
    offsets = (
        (-5, 0),
        (-4, -3),
        (-4, 3),
        (-3, -4),
        (-3, 4),
        (0, -5),
        (0, 5),
        (3, -4),
        (3, 4),
        (4, -3),
        (4, 3),
        (5, 0),
    )
    for index, (offset_y, offset_x) in enumerate(offsets, start=1):
        seeds[
            centre_yx[0] + offset_y,
            centre_yx[1] + offset_x,
        ] = 100 - index
    significant = np.ones(seeds.shape, dtype=np.bool_)

    owned = assign_seeded_multiscale_support(
        seeds,
        significant,
        np.ones(seeds.shape, dtype=np.bool_),
        beam_major_fwhm_pixels=10.0,
    )

    assert owned[centre_yx] == seeds[1, 6]


def test_seeded_multiscale_tie_uses_carried_global_reference() -> None:
    """A tile-local first pixel cannot replace the frozen global owner."""
    labels = np.zeros((3, 7), dtype=np.int32)
    labels[1, 1] = 40
    labels[1, 5] = 2
    significant = np.zeros(labels.shape, dtype=np.bool_)
    significant[1, 1:6] = True

    owned = assign_seeded_multiscale_support(
        labels,
        significant,
        np.ones(labels.shape, dtype=np.bool_),
        beam_major_fwhm_pixels=8.0,
        canonical_seed_references_yx={40: (10, 10), 2: (0, 20)},
    )

    assert owned[1, 3] == 2


def test_seeded_multiscale_ownership_rejects_invalid_contracts() -> None:
    """Ownership never infers alignment, validity, beam, or radius."""
    labels = np.zeros((3, 3), dtype=np.int32)
    labels[1, 1] = 1
    support = np.ones(labels.shape, dtype=np.bool_)
    valid = np.ones(labels.shape, dtype=np.bool_)

    with pytest.raises(ValueError, match="significant multiscale support"):
        assign_seeded_multiscale_support(
            labels,
            support[:-1],
            valid,
            beam_major_fwhm_pixels=2.0,
        )
    with pytest.raises(ValueError, match="valid pixels"):
        assign_seeded_multiscale_support(
            labels,
            support,
            valid.astype(np.int8),
            beam_major_fwhm_pixels=2.0,
        )
    invalid_seed = valid.copy()
    invalid_seed[1, 1] = False
    with pytest.raises(ValueError, match="seed pixels"):
        assign_seeded_multiscale_support(
            labels,
            support,
            invalid_seed,
            beam_major_fwhm_pixels=2.0,
        )
    with pytest.raises(ValueError, match="beam major"):
        assign_seeded_multiscale_support(
            labels,
            support,
            valid,
            beam_major_fwhm_pixels=np.nan,
        )
    with pytest.raises(ValueError, match="recovery radius"):
        assign_seeded_multiscale_support(
            labels,
            support,
            valid,
            beam_major_fwhm_pixels=2.0,
            recovery_radius_beams=-0.1,
        )

    with pytest.raises(ValueError, match="every local owner"):
        assign_seeded_multiscale_support(
            labels,
            support,
            valid,
            beam_major_fwhm_pixels=2.0,
            canonical_seed_references_yx={},
        )

    with pytest.raises(ValueError, match="non-negative"):
        assign_seeded_multiscale_support(
            labels,
            support,
            valid,
            beam_major_fwhm_pixels=2.0,
            canonical_seed_references_yx={1: (-1, 0)},
        )

    two_labels = labels.copy()
    two_labels[0, 0] = 2
    with pytest.raises(ValueError, match="must be unique"):
        assign_seeded_multiscale_support(
            two_labels,
            support,
            valid,
            beam_major_fwhm_pixels=2.0,
            canonical_seed_references_yx={1: (0, 0), 2: (0, 0)},
        )

    empty = assign_seeded_multiscale_support(
        np.zeros(labels.shape, dtype=np.int32),
        support,
        valid,
        beam_major_fwhm_pixels=2.0,
    )
    no_candidates = assign_seeded_multiscale_support(
        labels,
        np.zeros(labels.shape, dtype=np.bool_),
        valid,
        beam_major_fwhm_pixels=2.0,
    )
    assert not empty.any()
    np.testing.assert_array_equal(no_candidates, labels)


def test_segment_cleanup_removes_only_sub_beam_protrusions() -> None:
    """A three-pixel opening removes one-pixel noise without relabelling."""
    labels = np.zeros((9, 11), dtype=np.int32)
    labels[2:7, 2:7] = 4
    labels[4, 7:10] = 4
    labels[2:7, 8:11] = 9

    cleaned = clean_detected_segment_labels(labels)

    assert np.all(cleaned[2:7, 2:7] == 4)
    assert np.all(cleaned[2:7, 8:11] == 9)
    assert np.all(cleaned[4, 7:8] == 0)
    assert set(np.unique(cleaned)) == {0, 4, 9}


def test_multiscale_refinement_uses_scale_support() -> None:
    """Dense, high-SNR, and adjacent-scale pixels define final support."""
    labels = np.zeros((11, 13), dtype=np.int32)
    labels[3:8, 2:7] = 4
    labels[5, 7:10] = 4
    labels[3:8, 10:13] = 9
    combined_snr = np.zeros(labels.shape, dtype=np.float64)
    combined_snr[labels > 0] = 4.0
    combined_snr[5, 7] = 6.0
    reconstruction = np.zeros(labels.shape, dtype=np.bool_)
    reconstruction[4:7, 7:10] = True

    refined = refine_multiscale_segment_labels(
        labels,
        combined_snr,
        reconstruction,
        beam_major_fwhm_pixels=4.0,
    )

    assert np.all(refined[4:7, 3:6] == 4)
    assert np.all(refined[4:7, 10:12] == 9)
    assert refined[3, 2] == 0
    assert refined[5, 7] == 4
    assert refined[4, 8] == 4
    assert refined[4, 9] == 9
    assert refined[3, 7] == 0
    assert set(np.unique(refined)) == {0, 4, 9}


def test_multiscale_refinement_rejects_ambiguous_evidence() -> None:
    """Refinement requires aligned calibrated planes and a finite beam."""
    labels = np.ones((5, 5), dtype=np.int32)
    snr = np.ones((5, 5), dtype=np.float64)
    support = np.ones((5, 5), dtype=np.bool_)

    with pytest.raises(ValueError, match="aligned"):
        refine_multiscale_segment_labels(
            labels,
            snr[:-1],
            support,
            beam_major_fwhm_pixels=3.0,
        )
    with pytest.raises(ValueError, match="boolean"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support.astype(np.int8),
            beam_major_fwhm_pixels=3.0,
        )
    with pytest.raises(ValueError, match="positive"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=np.nan,
        )
    with pytest.raises(ValueError, match="neighbors"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            core_minimum_neighbors=True,
        )
    with pytest.raises(ValueError, match="neighbors"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            core_minimum_neighbors=10,
        )
    with pytest.raises(ValueError, match="neighbors"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            core_minimum_neighbors=5.5,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="boundary minimum"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            boundary_minimum_snr=0.0,
        )
    with pytest.raises(ValueError, match="recovery radius"):
        refine_multiscale_segment_labels(
            labels,
            snr,
            support,
            beam_major_fwhm_pixels=3.0,
            recovery_radius_beams=-0.1,
        )

    empty = refine_multiscale_segment_labels(
        np.zeros(labels.shape, dtype=np.int32),
        snr,
        support,
        beam_major_fwhm_pixels=3.0,
    )
    assert not empty.any()


def test_expanded_segment_labels_assign_overlap_to_nearest_support() -> None:
    """Measurement apertures are bounded, valid, and never double-counted."""
    labels = np.zeros((7, 9), dtype=np.int32)
    labels[3, 2] = 3
    labels[3, 6] = 8
    valid = np.ones(labels.shape, dtype=np.bool_)
    valid[3, 4] = False

    expanded = expand_detected_segment_labels(
        labels,
        valid,
        radius_pixels=2,
    )

    assert expanded[3, 2] == 3
    assert expanded[3, 6] == 8
    assert expanded[3, 3] == 3
    assert expanded[3, 5] == 8
    assert expanded[3, 4] == 0
    assert expanded[0, 0] == 0


def test_segment_label_transforms_reject_ambiguous_planes() -> None:
    """Morphology and aperture ownership require exact label contracts."""
    with pytest.raises(ValueError, match="integer label"):
        clean_detected_segment_labels(np.ones((3, 3), dtype=np.float64))
    negative = np.zeros((3, 3), dtype=np.int32)
    negative[1, 1] = -1
    with pytest.raises(ValueError, match="non-negative"):
        clean_detected_segment_labels(negative)
    with pytest.raises(ValueError, match="aligned"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((2, 3), dtype=np.bool_),
            radius_pixels=2,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((3, 3), dtype=np.bool_),
            radius_pixels=-1,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((3, 3), dtype=np.bool_),
            radius_pixels=True,
        )
    with pytest.raises(ValueError, match="aligned"):
        expand_detected_segment_labels(
            np.ones((3, 3), dtype=np.int32),
            np.ones((3, 3), dtype=np.int8),
            radius_pixels=1,
        )

    empty = expand_detected_segment_labels(
        np.zeros((3, 3), dtype=np.int32),
        np.ones((3, 3), dtype=np.bool_),
        radius_pixels=1,
    )
    assert not empty.any()


def test_detected_segment_position_uses_only_original_supported_pixels() -> (
    None
):
    """The catalogue centroid and peak share the exact accepted segment."""
    signal = np.asarray(
        (
            (100.0, 1.0, 0.0),
            (0.0, 2.0, 3.0),
            (0.0, 0.0, 3.0),
        )
    )
    support = np.asarray(
        (
            (False, True, False),
            (False, True, True),
            (False, False, True),
        )
    )

    estimate = measure_detected_segment_position(signal, support)

    assert estimate.available is True
    assert estimate.centroid_xy == pytest.approx((5.0 / 3.0, 11.0 / 9.0))
    assert estimate.peak_position_xy == (2, 1)
    assert estimate.support_pixel_count == 4
    assert estimate.integrated_weight == pytest.approx(9.0)
    assert estimate.unavailable_reason is None


def test_detected_segment_peak_ties_use_row_major_first() -> None:
    """Equal maxima have deterministic global y-then-x ownership."""
    signal = np.asarray(((0.0, 4.0), (4.0, 0.0)))
    support = np.ones(signal.shape, dtype=np.bool_)

    estimate = measure_detected_segment_position(signal, support)

    assert estimate.peak_position_xy == (1, 0)


def test_detected_segment_position_reports_typed_unavailability() -> None:
    """Empty and non-positive segments do not emit invented coordinates."""
    signal = np.ones((2, 2), dtype=np.float64)

    empty = measure_detected_segment_position(
        signal, np.zeros(signal.shape, dtype=np.bool_)
    )
    nonpositive = measure_detected_segment_position(
        -signal, np.ones(signal.shape, dtype=np.bool_)
    )

    assert empty.available is False
    assert empty.centroid_xy is None
    assert empty.peak_position_xy is None
    assert empty.unavailable_reason == "empty-finite-support"
    assert nonpositive.available is False
    assert nonpositive.unavailable_reason == "nonpositive-segment-flux"


def test_detected_segment_position_rejects_bad_array_contract() -> None:
    """Only aligned two-dimensional numeric pixels enter the estimator."""
    with pytest.raises(ValueError, match="aligned two-dimensional"):
        measure_detected_segment_position(
            np.ones((2, 2)), np.ones((2, 1), dtype=np.bool_)
        )
    with pytest.raises(ValueError, match="boolean"):
        measure_detected_segment_position(
            np.ones((2, 2)),
            cast(
                npt.NDArray[np.bool_],
                np.ones((2, 2), dtype=np.int64),
            ),
        )
