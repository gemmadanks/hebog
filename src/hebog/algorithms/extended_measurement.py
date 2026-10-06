# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Pure measurement kernels for irregular extended emission."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from math import ceil, isfinite
from numbers import Integral
from typing import Literal, Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import (
    binary_dilation,
    binary_opening,
    convolve,
    distance_transform_edt,
    find_objects,
    maximum_filter,
)
from scipy.ndimage import (
    label as connected_component_labels,
)
from scipy.spatial import (
    cKDTree,  # pyright: ignore[reportAttributeAccessIssue]
)

from hebog.algorithms.label_groups import label_windows

SegmentPositionUnavailableReason = Literal[
    "empty-finite-support",
    "nonpositive-segment-flux",
    "ill-conditioned-segment-position",
]
_IMAGE_DIMENSIONS = 2
_SUB_BEAM_OPENING_WIDTH_PIXELS = 3
# A 3x3 binary opening erodes then dilates, so one pixel's opened value
# depends on the input two pixels away, and the 3x3 dense-core count
# reaches one pixel beyond that.
_OPENING_INFLUENCE_PIXELS = _SUB_BEAM_OPENING_WIDTH_PIXELS - 1
_DENSE_CORE_INFLUENCE_PIXELS = _OPENING_INFLUENCE_PIXELS + 1
_MULTISCALE_CORE_MINIMUM_NEIGHBORS = 5
_MULTISCALE_BOUNDARY_MINIMUM_SNR = 6.0
_MULTISCALE_RECOVERY_RADIUS_BEAMS = 0.5
_NEIGHBORHOOD_PIXEL_COUNT = 9
_MINIMUM_BRIDGE_TOUCH_COUNT = 2


class _NearestSeedTree(Protocol):
    """Narrow typed boundary around SciPy's optional-stub KD tree."""

    def query(
        self,
        points: npt.NDArray[np.int64],
        *,
        k: int,
    ) -> tuple[npt.ArrayLike, npt.ArrayLike]:
        """Return distances and point indices for each query row."""
        ...


def multiscale_recovery_radius_pixels(
    beam_major_fwhm_pixels: float,
    *,
    recovery_radius_beams: float = _MULTISCALE_RECOVERY_RADIUS_BEAMS,
) -> int:
    """Return the reviewed coherent-support recovery radius in pixels."""
    if (
        isinstance(beam_major_fwhm_pixels, bool)
        or not isfinite(beam_major_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0
    ):
        raise ValueError("beam major FWHM must be finite and positive")
    if (
        isinstance(recovery_radius_beams, bool)
        or not isfinite(recovery_radius_beams)
        or recovery_radius_beams < 0
    ):
        raise ValueError("recovery radius must be finite and non-negative")
    return ceil(recovery_radius_beams * beam_major_fwhm_pixels)


def segment_refinement_halo_pixels(
    beam_major_fwhm_pixels: float,
    *,
    recovery_radius_beams: float = _MULTISCALE_RECOVERY_RADIUS_BEAMS,
) -> int:
    """Return the halo covering opening and multiscale support recovery.

    The two radii add rather than compete: a pixel recovered at the recovery
    radius takes its identity from opened support, which must itself be
    correct that far out. The dense-core count sets the floor when the
    recovery radius is small.
    """
    return max(
        _DENSE_CORE_INFLUENCE_PIXELS,
        multiscale_recovery_radius_pixels(
            beam_major_fwhm_pixels,
            recovery_radius_beams=recovery_radius_beams,
        )
        + _OPENING_INFLUENCE_PIXELS,
    )


def _segment_label_plane(
    component_labels: npt.ArrayLike,
) -> npt.NDArray[np.int64]:
    """Return one exact non-negative integer segment-label plane."""
    values = np.asarray(component_labels)
    if values.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        values.dtype,
        np.integer,
    ):
        raise ValueError(
            "component labels must be a two-dimensional integer label plane"
        )
    if np.any(values < 0):
        raise ValueError("component labels must be non-negative")
    return np.asarray(values, dtype=np.int64)


def clean_detected_segment_labels(
    component_labels: npt.ArrayLike,
) -> npt.NDArray[np.int32]:
    """Remove sub-beam protrusions while preserving segment identities.

    A three-by-three binary opening is deliberately smaller than the sampled
    restoring beams supported by the source-finder contracts. It suppresses
    single-pixel flood-threshold excursions without growing, merging, or
    relabelling accepted emission.
    """
    labels = _segment_label_plane(component_labels)
    retained = binary_opening(
        labels > 0,
        structure=np.ones(
            (
                _SUB_BEAM_OPENING_WIDTH_PIXELS,
                _SUB_BEAM_OPENING_WIDTH_PIXELS,
            ),
            dtype=np.bool_,
        ),
    )
    return np.where(retained, labels, 0).astype(np.int32, copy=False)


def _owner_windows(
    original_labels: npt.NDArray[np.int64],
    refined_labels: npt.NDArray[np.int32],
) -> dict[int, tuple[slice, slice] | None]:
    """Return the window holding each owner in both label planes."""
    original_windows = label_windows(original_labels)
    refined_windows = label_windows(refined_labels)
    owners: dict[int, tuple[slice, slice] | None] = {}
    for label_value in np.unique(original_labels):
        value = int(label_value)
        if value <= 0:
            continue
        crops = [
            windows[value - 1]
            for windows in (original_windows, refined_windows)
            if value <= len(windows) and windows[value - 1] is not None
        ]
        owners[value] = (
            None
            if not crops
            else (
                slice(
                    min(crop[0].start for crop in crops if crop is not None),
                    max(crop[0].stop for crop in crops if crop is not None),
                ),
                slice(
                    min(crop[1].start for crop in crops if crop is not None),
                    max(crop[1].stop for crop in crops if crop is not None),
                ),
            )
        )
    return owners


def owner_support_needs_restore(
    refined_window: npt.NDArray[np.int32],
    *,
    label_value: int,
) -> bool:
    """Return whether cleanup split one owner's refined support or removed it.

    Refinement may trim an owner's flood, but it must leave one connected
    part: an owner it splits, or one it removes entirely, such as a compact
    detection between the detection threshold and the boundary floor whose
    footprint holds no full opening element, keeps its original support.

    The window must hold the owner's original and refined support completely;
    connectivity cannot be decided from a part of it. Callers that evaluate
    one owner per task use this decision, and the plane-wide
    :func:`restore_segment_owners` applies it to every owner.
    """
    _, component_count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(
            np.asarray(refined_window) == label_value,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    return component_count != 1


def apply_owner_restores(
    original_labels: npt.ArrayLike,
    refined_labels: npt.ArrayLike,
    restored_owners: Collection[int],
) -> npt.NDArray[np.int32]:
    """Restore the original support of every owner cleanup splits or removes.

    The decision is one boolean per owner, so a tile applies it to its own
    core without seeing the owner's whole window.
    """
    original = np.asarray(original_labels)
    refined = np.asarray(refined_labels, dtype=np.int32).copy()
    if not restored_owners:
        return refined
    restored = np.isin(
        original,
        np.asarray(sorted(restored_owners), dtype=original.dtype),
    )
    np.copyto(refined, original.astype(np.int32, copy=False), where=restored)
    return refined


def restore_segment_owners(
    original_labels: npt.NDArray[np.int64],
    refined_labels: npt.NDArray[np.int32],
) -> npt.NDArray[np.int32]:
    """Restore a direct owner only when cleanup would split or remove it.

    Each owner is examined in the window holding both its original and its
    refined support, instead of over the whole plane. Refinement recovers
    multiscale emission, so an owner can reach pixels its original support
    never covered, and those pixels decide whether cleanup split it.
    """
    connected = np.asarray(refined_labels, dtype=np.int32).copy()
    windows = _owner_windows(original_labels, connected)
    for label_value in np.unique(original_labels):
        if label_value <= 0:
            continue
        crop = windows[int(label_value)]
        if crop is None:
            continue
        if owner_support_needs_restore(
            connected[crop],
            label_value=int(label_value),
        ):
            connected[crop][original_labels[crop] == label_value] = label_value
    return connected


def _dense_label_ranks(
    labels: npt.NDArray[np.int64],
) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.int64]]:
    """Return compact positive ranks and their original label values."""
    positive_values = np.unique(labels[labels > 0])
    ranked = np.zeros(labels.shape, dtype=np.int32)
    positive = labels > 0
    ranked[positive] = np.asarray(
        np.searchsorted(positive_values, labels[positive]) + 1,
        dtype=np.int32,
    )
    return ranked, positive_values


def preserve_owner_publication_bridges(
    previous_window: npt.ArrayLike,
    refined_window: npt.ArrayLike,
    *,
    label_value: int,
) -> npt.NDArray[np.int32]:
    """Keep only the previous regions that connect one owner's support.

    The window must hold the owner completely; connectivity cannot be decided
    from a part of it. A bridge is a previously published region touching two
    retained parts of the same owner. When the owner still falls apart, its
    whole previous support is restored, and a part that remains disconnected
    from the previous support is dropped rather than published separately.
    When refinement retained nothing of the owner, its whole previous support
    is restored too, so no published owner loses all of its support.
    """
    structure = np.ones((3, 3), dtype=np.int8)
    previous = np.asarray(previous_window) == label_value
    local = np.asarray(refined_window, dtype=np.int32).copy()
    base_components, base_count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(local == label_value, structure=structure),
    )
    if base_count == 0:
        _, previous_count = cast(
            tuple[npt.NDArray[np.int32], int],
            connected_component_labels(previous, structure=structure),
        )
        if previous_count > 1:
            raise ValueError(
                "previous publication ownership must be connected"
            )
        local[previous] = label_value
        return local
    candidates, candidate_count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(
            previous & (local == 0),
            structure=structure,
        ),
    )
    for candidate_value in range(1, candidate_count + 1):
        candidate = candidates == candidate_value
        dilated_candidate = np.asarray(
            binary_dilation(candidate, structure=structure),
            dtype=np.bool_,
        )
        touching = np.unique(base_components[dilated_candidate])
        if np.count_nonzero(touching > 0) >= _MINIMUM_BRIDGE_TOUCH_COUNT:
            local[candidate] = label_value
    final_components, final_count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(local == label_value, structure=structure),
    )
    if final_count > 1:
        local[previous] = label_value
        final_components, final_count = cast(
            tuple[npt.NDArray[np.int32], int],
            connected_component_labels(
                local == label_value,
                structure=structure,
            ),
        )
    if final_count > 1:
        previous_components = np.unique(final_components[previous])
        previous_components = previous_components[previous_components > 0]
        if previous_components.size != 1:
            raise ValueError(
                "previous publication ownership must be connected"
            )
        local[
            (final_components > 0)
            & (final_components != previous_components[0])
        ] = 0
    return local


def publication_owner_windows(
    owner_labels: npt.NDArray[np.int64],
) -> tuple[tuple[int, tuple[slice, slice]], ...]:
    """Return each owner's label and the window holding its support."""
    ranked, label_values = _dense_label_ranks(owner_labels)
    return tuple(
        (int(label_value), bounds)
        for label_value, bounds in zip(
            label_values,
            find_objects(ranked),
            strict=True,
        )
        if bounds is not None
    )


def _preserve_publication_bridges(
    owner_labels: npt.NDArray[np.int64],
    previous_labels: npt.NDArray[np.int64],
    refined_labels: npt.NDArray[np.int32],
) -> npt.NDArray[np.int32]:
    """Apply the owner bridge rule to every owner of a complete plane."""
    connected = np.asarray(refined_labels, dtype=np.int32).copy()
    for label_value, bounds in publication_owner_windows(owner_labels):
        connected[bounds] = preserve_owner_publication_bridges(
            previous_labels[bounds],
            connected[bounds],
            label_value=label_value,
        )
    connected.setflags(write=False)
    return connected


def refine_persistent_publication_support(
    component_labels: npt.ArrayLike,
    publication_labels: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    persistent_scale_support: npt.ArrayLike,
    *,
    published_owner_values: npt.ArrayLike | None = None,
) -> npt.NDArray[np.int32]:
    """Retain owner support corroborated across adjacent scales, per pixel.

    Dense opened support and independently strong original-image boundaries
    remain unchanged. Sparse recovered pixels remain only when their exact
    scale feature participates in an adjacent-scale association.

    Whether an owner is published *anywhere* decides whether its persistent
    support is restored, which no bounded neighbourhood can answer. Tiled
    callers pass ``published_owner_values``, the owners published over the
    whole image; a complete-plane call derives them.
    """
    owners = _segment_label_plane(component_labels)
    previous = _segment_label_plane(publication_labels)
    snr = np.asarray(combined_snr)
    persistent = np.asarray(persistent_scale_support)
    if previous.shape != owners.shape:
        raise ValueError(
            "component and publication labels must be aligned label planes"
        )
    if np.any((previous > 0) & (previous != owners)):
        raise ValueError(
            "publication ownership must agree with component ownership"
        )
    if (
        snr.ndim != _IMAGE_DIMENSIONS
        or snr.shape != owners.shape
        or not np.issubdtype(snr.dtype, np.number)
        or np.iscomplexobj(snr)
    ):
        raise ValueError(
            "component labels and combined SNR must be aligned real "
            "two-dimensional planes"
        )
    if persistent.shape != owners.shape or persistent.dtype != np.bool_:
        raise ValueError(
            "persistent scale support must be one aligned boolean plane"
        )
    cleaned_support = clean_detected_segment_labels(owners) > 0
    neighbor_count = convolve(
        cleaned_support.astype(np.int8),
        np.ones((3, 3), dtype=np.int8),
        mode="constant",
        cval=0,
    )
    dense_core = cleaned_support & (
        neighbor_count >= _MULTISCALE_CORE_MINIMUM_NEIGHBORS
    )
    high_confidence_boundary = (owners > 0) & (
        np.asarray(snr, dtype=np.float64) >= _MULTISCALE_BOUNDARY_MINIMUM_SNR
    )
    previously_published = previous > 0
    retained = previously_published & (
        dense_core | high_confidence_boundary | persistent
    )
    published_owners = (
        np.unique(previous[previous > 0])
        if published_owner_values is None
        else np.asarray(published_owner_values)
    )
    restored_persistent = persistent & np.isin(owners, published_owners)
    return np.where(retained | restored_persistent, owners, 0).astype(
        np.int32,
        copy=False,
    )


def refine_persistent_publication_labels(
    component_labels: npt.ArrayLike,
    publication_labels: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    persistent_scale_support: npt.ArrayLike,
) -> npt.NDArray[np.int32]:
    """Publish connected owner support corroborated across adjacent scales.

    Previously published low-confidence regions are retained only when they
    connect two retained parts of the same owner, or when nothing else of
    that owner is retained; no new threshold or ownership is introduced.
    """
    owners = _segment_label_plane(component_labels)
    return _preserve_publication_bridges(
        owners,
        _segment_label_plane(publication_labels),
        refine_persistent_publication_support(
            component_labels,
            publication_labels,
            combined_snr,
            persistent_scale_support,
        ),
    )


def refine_multiscale_segment_support(  # noqa: PLR0913
    component_labels: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    core_minimum_neighbors: int = _MULTISCALE_CORE_MINIMUM_NEIGHBORS,
    boundary_minimum_snr: float = _MULTISCALE_BOUNDARY_MINIMUM_SNR,
    recovery_radius_beams: float = _MULTISCALE_RECOVERY_RADIUS_BEAMS,
    recovered_minimum_snr: float | None = None,
) -> npt.NDArray[np.int32]:
    """Refine noisy flood boundaries with calibrated multiscale evidence.

    Dense opened support remains without an additional significance test.
    Sparse boundary pixels remain only at high combined S/N, while adjacent
    significant à trous support may recover coherent emission omitted by the
    original-pixel flood. When ``recovered_minimum_snr`` is supplied, recovered
    support must also meet that original-pixel S/N floor. Recovered pixels
    inherit the nearest original segment identity, preserving deterministic
    ownership without merging or relabelling sources.

    Every decision here is bounded by the opening and recovery radii, so a
    tile evaluates its own core exactly. Whether cleanup split or removed an
    owner is not: :func:`restore_segment_owners` decides that per owner, and
    :func:`refine_multiscale_segment_labels` composes the two.
    """
    labels = _segment_label_plane(component_labels)
    snr = np.asarray(combined_snr)
    multiscale_support = np.asarray(significant_multiscale_support)
    if (
        snr.ndim != _IMAGE_DIMENSIONS
        or snr.shape != labels.shape
        or not np.issubdtype(snr.dtype, np.number)
        or np.issubdtype(snr.dtype, np.complexfloating)
    ):
        raise ValueError(
            "component labels and combined SNR must be aligned real "
            "two-dimensional planes"
        )
    if (
        multiscale_support.ndim != _IMAGE_DIMENSIONS
        or multiscale_support.shape != labels.shape
    ):
        raise ValueError(
            "component labels and multiscale support must be aligned "
            "two-dimensional planes"
        )
    if multiscale_support.dtype != np.bool_:
        raise ValueError("significant multiscale support must be boolean")
    if (
        isinstance(core_minimum_neighbors, bool)
        or not isinstance(core_minimum_neighbors, Integral)
        or not 1 <= core_minimum_neighbors <= _NEIGHBORHOOD_PIXEL_COUNT
    ):
        raise ValueError("core minimum neighbors must be an integer in [1, 9]")
    if not isfinite(boundary_minimum_snr) or boundary_minimum_snr <= 0:
        raise ValueError("boundary minimum SNR must be finite and positive")
    if recovered_minimum_snr is not None and (
        isinstance(recovered_minimum_snr, bool)
        or not isfinite(recovered_minimum_snr)
        or recovered_minimum_snr <= 0
    ):
        raise ValueError(
            "recovered minimum SNR must be finite and positive when supplied"
        )
    recovery_radius_pixels = multiscale_recovery_radius_pixels(
        beam_major_fwhm_pixels,
        recovery_radius_beams=recovery_radius_beams,
    )
    original_support = labels > 0
    high_confidence_boundary = original_support & (
        np.asarray(snr, dtype=np.float64) >= boundary_minimum_snr
    )
    cleaned = clean_detected_segment_labels(labels)
    cleaned_support = cleaned > 0
    if not np.any(cleaned_support):
        return np.where(high_confidence_boundary, labels, 0).astype(
            np.int32, copy=False
        )
    neighbor_count = convolve(
        cleaned_support.astype(np.int8),
        np.ones((3, 3), dtype=np.int8),
        mode="constant",
        cval=0,
    )
    dense_core = cleaned_support & (neighbor_count >= core_minimum_neighbors)
    nearby = (
        binary_dilation(cleaned_support, iterations=recovery_radius_pixels)
        if recovery_radius_pixels > 0
        else cleaned_support
    )
    recovered = multiscale_support & nearby
    if recovered_minimum_snr is not None:
        recovered &= np.asarray(snr, dtype=np.float64) >= recovered_minimum_snr
    _, nearest_indices = cast(
        tuple[npt.NDArray[np.float64], npt.NDArray[np.int32]],
        distance_transform_edt(
            ~cleaned_support,
            return_distances=True,
            return_indices=True,
        ),
    )
    nearest_labels = cleaned[tuple(nearest_indices)]
    refined = np.where(dense_core | recovered, nearest_labels, 0)
    return np.where(high_confidence_boundary, labels, refined).astype(
        np.int32,
        copy=False,
    )


def refine_multiscale_segment_labels(  # noqa: PLR0913
    component_labels: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    core_minimum_neighbors: int = _MULTISCALE_CORE_MINIMUM_NEIGHBORS,
    boundary_minimum_snr: float = _MULTISCALE_BOUNDARY_MINIMUM_SNR,
    recovery_radius_beams: float = _MULTISCALE_RECOVERY_RADIUS_BEAMS,
    recovered_minimum_snr: float | None = None,
) -> npt.NDArray[np.int32]:
    """Refine segment support, restoring owners cleanup splits or removes."""
    labels = _segment_label_plane(component_labels)
    return restore_segment_owners(
        labels,
        refine_multiscale_segment_support(
            component_labels,
            combined_snr,
            significant_multiscale_support,
            beam_major_fwhm_pixels=beam_major_fwhm_pixels,
            core_minimum_neighbors=core_minimum_neighbors,
            boundary_minimum_snr=boundary_minimum_snr,
            recovery_radius_beams=recovery_radius_beams,
            recovered_minimum_snr=recovered_minimum_snr,
        ),
    )


def _canonical_seed_ranks(
    seed_labels: npt.NDArray[np.int64],
    canonical_seed_references_yx: Mapping[int, tuple[int, int]] | None,
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """Return each seed pixel's owner rank and labels ordered globally."""
    flat_labels = seed_labels.ravel()
    flat_positions = np.flatnonzero(flat_labels > 0)
    positive_labels = flat_labels[flat_positions]
    unique_labels, inverse = np.unique(positive_labels, return_inverse=True)
    if canonical_seed_references_yx is None:
        first_positions = np.full(
            unique_labels.size,
            flat_labels.size,
            dtype=np.int64,
        )
        np.minimum.at(first_positions, inverse, flat_positions)
        canonical_order = np.argsort(first_positions, kind="stable")
    else:
        expected_labels = {int(label) for label in unique_labels}
        if not expected_labels.issubset(canonical_seed_references_yx):
            raise ValueError(
                "canonical seed references must identify every local owner"
            )
        references: list[tuple[int, int]] = []
        for label in unique_labels:
            reference = canonical_seed_references_yx[int(label)]
            if len(reference) != _IMAGE_DIMENSIONS or any(
                (
                    isinstance(coordinate, bool)
                    or not isinstance(coordinate, Integral)
                    or coordinate < 0
                )
                for coordinate in reference
            ):
                raise ValueError(
                    "canonical seed references must be non-negative y-x "
                    "integer pairs"
                )
            references.append(reference)
        if len(set(references)) != len(references):
            raise ValueError("canonical seed references must be unique")
        canonical_order = np.lexsort(
            (
                np.asarray([item[1] for item in references]),
                np.asarray([item[0] for item in references]),
            )
        )
    rank_by_unique = np.empty(unique_labels.size, dtype=np.int64)
    rank_by_unique[canonical_order] = np.arange(unique_labels.size)
    return rank_by_unique[inverse], unique_labels[canonical_order]


def _nearest_canonical_seed_ranks(
    tree: _NearestSeedTree,
    candidate_points_yx: npt.NDArray[np.int64],
    seed_ranks: npt.NDArray[np.int64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64]]:
    """Find exact nearest owners with global-identity tie resolution."""
    seed_count = seed_ranks.size
    neighbor_count = min(8, seed_count)
    distances, indices = tree.query(candidate_points_yx, k=neighbor_count)
    distances = np.asarray(distances, dtype=np.float64).reshape(
        candidate_points_yx.shape[0], neighbor_count
    )
    indices = np.asarray(indices, dtype=np.int64).reshape(
        candidate_points_yx.shape[0], neighbor_count
    )
    minimum_distances = distances[:, 0]
    tied = np.isclose(
        distances,
        minimum_distances[:, np.newaxis],
        rtol=0.0,
        atol=np.finfo(np.float64).eps * 16.0,
    )
    sentinel = np.iinfo(np.int64).max
    owner_ranks = np.min(
        np.where(tied, seed_ranks[indices], sentinel),
        axis=1,
    )
    pending = (
        tied[:, -1]
        if neighbor_count < seed_count
        else np.zeros(candidate_points_yx.shape[0], dtype=np.bool_)
    )
    while np.any(pending):
        neighbor_count = min(seed_count, neighbor_count * 2)
        pending_indices = np.flatnonzero(pending)
        pending_distances, pending_neighbors = tree.query(
            candidate_points_yx[pending_indices],
            k=neighbor_count,
        )
        pending_distances = np.asarray(
            pending_distances, dtype=np.float64
        ).reshape(pending_indices.size, neighbor_count)
        pending_neighbors = np.asarray(
            pending_neighbors, dtype=np.int64
        ).reshape(pending_indices.size, neighbor_count)
        pending_ties = np.isclose(
            pending_distances,
            minimum_distances[pending_indices, np.newaxis],
            rtol=0.0,
            atol=np.finfo(np.float64).eps * 16.0,
        )
        owner_ranks[pending_indices] = np.min(
            np.where(
                pending_ties,
                seed_ranks[pending_neighbors],
                sentinel,
            ),
            axis=1,
        )
        pending[:] = False
        if neighbor_count < seed_count:
            pending[pending_indices] = pending_ties[:, -1]
    return minimum_distances, owner_ranks


def _support_components(
    support_component_labels: npt.ArrayLike | None,
    *,
    eligible_support: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Return the support components a caller supplied, or derive them."""
    if support_component_labels is None:
        derived, _ = cast(
            tuple[npt.NDArray[np.int32], int],
            connected_component_labels(
                eligible_support,
                structure=np.ones((3, 3), dtype=np.int8),
            ),
        )
        return derived
    components = np.asarray(support_component_labels)
    if (
        components.shape != eligible_support.shape
        or not np.issubdtype(components.dtype, np.integer)
        or bool(np.any(components < 0))
    ):
        raise ValueError(
            "support components must be one aligned non-negative label plane"
        )
    if bool(np.any((components > 0) != eligible_support)):
        raise ValueError(
            "support components must label exactly the eligible support"
        )
    return np.asarray(components, dtype=np.int32)


def assign_seeded_multiscale_support(  # noqa: PLR0913
    component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    recovery_radius_beams: float = _MULTISCALE_RECOVERY_RADIUS_BEAMS,
    canonical_seed_references_yx: (
        Mapping[int, tuple[int, int]] | None
    ) = None,
    support_component_labels: npt.ArrayLike | None = None,
) -> npt.NDArray[np.int32]:
    """Attach bounded multiscale support without merging direct seed owners.

    Positive input labels are authoritative direct-residual source identities.
    Eligible support is assigned to the nearest exact seed pixel of its own
    support component. Equal distances use the owner whose globally row-major
    seed reference appears first, independently of task-local label integers
    or completion order.

    Tiled callers must pass the global reference pixel of every owner present
    in the tile, and ``support_component_labels``: the globally reconciled
    eight-connected components of ``(labels > 0 | significant) & valid``. That
    connectivity is not bounded by any halo, so a tile that labelled its own
    read would separate support a longer path joins. A complete-plane call may
    omit both and have them derived here.
    """
    labels = _segment_label_plane(component_labels)
    significant = np.asarray(significant_multiscale_support)
    valid = np.asarray(valid_pixels)
    if (
        significant.ndim != _IMAGE_DIMENSIONS
        or significant.shape != labels.shape
        or significant.dtype != np.bool_
    ):
        raise ValueError(
            "component labels and significant multiscale support must be "
            "aligned boolean two-dimensional planes"
        )
    if (
        valid.ndim != _IMAGE_DIMENSIONS
        or valid.shape != labels.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError(
            "component labels and valid pixels must be aligned boolean "
            "two-dimensional planes"
        )
    if np.any((labels > 0) & ~valid):
        raise ValueError("direct seed pixels must be scientifically valid")
    if (
        isinstance(beam_major_fwhm_pixels, bool)
        or not isfinite(beam_major_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0.0
    ):
        raise ValueError("beam major FWHM must be finite and positive")
    if (
        isinstance(recovery_radius_beams, bool)
        or not isfinite(recovery_radius_beams)
        or recovery_radius_beams < 0.0
    ):
        raise ValueError("recovery radius must be finite and non-negative")
    output = np.asarray(labels, dtype=np.int32).copy()
    seed_points = np.column_stack(np.nonzero(labels > 0))
    if not seed_points.size:
        return output
    connected_labels = _support_components(
        support_component_labels,
        eligible_support=((labels > 0) | significant) & valid,
    )
    candidate_points = np.column_stack(
        np.nonzero(significant & valid & (labels == 0))
    )
    if not candidate_points.size:
        return output
    seed_ranks, labels_by_rank = _canonical_seed_ranks(
        labels,
        canonical_seed_references_yx,
    )
    seed_components = connected_labels[seed_points[:, 0], seed_points[:, 1]]
    candidate_components = connected_labels[
        candidate_points[:, 0], candidate_points[:, 1]
    ]
    maximum_distance = recovery_radius_beams * beam_major_fwhm_pixels
    for component in sorted({int(value) for value in seed_components}):
        local_seed = seed_components == component
        local_candidate = candidate_components == component
        if not np.any(local_candidate):
            continue
        points = np.asarray(candidate_points[local_candidate], dtype=np.int64)
        distances, owner_ranks = _nearest_canonical_seed_ranks(
            cast(_NearestSeedTree, cKDTree(seed_points[local_seed])),
            points,
            seed_ranks[local_seed],
        )
        eligible = distances <= maximum_distance
        eligible_points = points[eligible]
        output[eligible_points[:, 0], eligible_points[:, 1]] = labels_by_rank[
            owner_ranks[eligible]
        ].astype(np.int32, copy=False)
    return output


def assign_persistent_source_support(
    source_labels: npt.ArrayLike,
    persistent_multiscale_support: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
) -> npt.NDArray[np.int32]:
    """Assign connected persistent support to canonical source owners once.

    Source labels are the already accepted catalogue-source partition. Exact
    persistent support connected to at least one source seed extends that
    source's measurement seed. Where support is connected to multiple sources,
    the nearest immutable source pixel owns it; exact distance ties use the
    smaller source label, whose ordering is derived from canonical source IDs.
    Disconnected, invalid, and non-persistent pixels cannot enter the result.
    """
    labels = _segment_label_plane(source_labels)
    persistent = np.asarray(persistent_multiscale_support)
    valid = np.asarray(valid_pixels)
    if (
        persistent.ndim != _IMAGE_DIMENSIONS
        or persistent.shape != labels.shape
        or persistent.dtype != np.bool_
    ):
        raise ValueError(
            "source labels and persistent multiscale support must be aligned "
            "boolean two-dimensional planes"
        )
    if (
        valid.ndim != _IMAGE_DIMENSIONS
        or valid.shape != labels.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError(
            "source labels and valid pixels must be aligned boolean "
            "two-dimensional planes"
        )
    if np.any((labels > 0) & ~valid):
        raise ValueError("source seed pixels must be scientifically valid")
    if np.any(persistent & ~valid):
        raise ValueError(
            "persistent source support must be scientifically valid"
        )
    output = np.asarray(labels, dtype=np.int32).copy()
    if not np.any(labels > 0) or not np.any(persistent & (labels == 0)):
        return output
    connected_labels, count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(
            (labels > 0) | persistent,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    for component in range(1, count + 1):
        assign_connected_source_support(
            output,
            persistent,
            np.asarray(connected_labels == component),
        )
    return output


def assign_connected_source_support(
    source_labels: npt.NDArray[np.int32],
    persistent: npt.NDArray[np.bool_],
    component: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Assign one connected support component to its nearest source seeds.

    Every array covers the window that holds this component. Candidates are
    the component's persistent pixels that no source seeds; the nearest
    immutable source pixel owns each, and an exact distance tie goes to the
    smaller source label, whose order follows the canonical source IDs.
    ``source_labels`` is written in place and returned.
    """
    seed_points = np.column_stack(np.nonzero(component & (source_labels > 0)))
    candidate_points = np.column_stack(
        np.nonzero(component & persistent & (source_labels == 0))
    )
    if not seed_points.size or not candidate_points.size:
        return source_labels
    points = np.asarray(candidate_points, dtype=np.int64)
    owners = nearest_source_seed_labels(
        np.asarray(seed_points, dtype=np.int64),
        np.asarray(
            source_labels[seed_points[:, 0], seed_points[:, 1]],
            dtype=np.int64,
        ),
        points,
    )
    source_labels[points[:, 0], points[:, 1]] = owners.astype(
        np.int32, copy=False
    )
    return source_labels


def nearest_source_seed_labels(
    seed_points_yx: npt.NDArray[np.int64],
    seed_labels: npt.NDArray[np.int64],
    candidate_points_yx: npt.NDArray[np.int64],
) -> npt.NDArray[np.int64]:
    """Return the label of each candidate pixel's nearest source seed.

    The points are ``(y, x)`` pixel coordinates in any one frame, and an
    exact distance tie goes to the smaller source label, whose order follows
    the canonical source IDs. One candidate's owner depends only on the
    seeds, so a component too wide to read at once is assigned exactly by
    each core that holds its candidates, from the seeds that can own them.

    Raises:
        ValueError: If there is no seed, or the arrays disagree.
    """
    if (
        seed_points_yx.ndim != _IMAGE_DIMENSIONS
        or seed_points_yx.shape[1:] != (_IMAGE_DIMENSIONS,)
        or not seed_points_yx.shape[0]
        or seed_labels.shape != seed_points_yx.shape[:1]
        or candidate_points_yx.ndim != _IMAGE_DIMENSIONS
        or candidate_points_yx.shape[1:] != (_IMAGE_DIMENSIONS,)
    ):
        raise ValueError(
            "source seeds must be non-empty, aligned (y, x) points"
        )
    _, owners = _nearest_canonical_seed_ranks(
        cast(_NearestSeedTree, cKDTree(seed_points_yx)),
        candidate_points_yx,
        seed_labels,
    )
    return owners


def expand_source_measurement_labels(
    source_labels: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    radius_pixels: int,
) -> npt.NDArray[np.int32]:
    """Expand source apertures with canonical source-identity tie breaking."""
    labels = _segment_label_plane(source_labels)
    valid = np.asarray(valid_pixels)
    if (
        valid.ndim != _IMAGE_DIMENSIONS
        or valid.shape != labels.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError(
            "source labels and valid pixels must be aligned boolean "
            "two-dimensional planes"
        )
    if isinstance(radius_pixels, bool) or radius_pixels < 0:
        raise ValueError("radius_pixels must be a non-negative integer")
    output = np.asarray(labels, dtype=np.int32).copy()
    seed_points = np.column_stack(np.nonzero(labels > 0))
    if not seed_points.size or radius_pixels == 0:
        return output
    # Only a pixel within the radius of some seed can survive the distance
    # test below, so the reachable band is the candidate set. Querying every
    # unlabelled pixel instead costs 128 bytes of nearest-neighbour state
    # each, which is the plane's area rather than the sources' extent.
    reachable = maximum_filter(
        labels > 0,
        size=2 * radius_pixels + 1,
        mode="constant",
        cval=False,
    )
    candidate_points = np.column_stack(
        np.nonzero(valid & (labels == 0) & reachable)
    )
    if not candidate_points.size:
        return output
    canonical_labels = np.asarray(
        sorted(int(value) for value in np.unique(labels) if value > 0),
        dtype=np.int32,
    )
    ranks_by_label = {
        int(label): rank for rank, label in enumerate(canonical_labels)
    }
    seed_ranks = np.asarray(
        [ranks_by_label[int(labels[tuple(point)])] for point in seed_points],
        dtype=np.int64,
    )
    distances, owner_ranks = _nearest_canonical_seed_ranks(
        cast(_NearestSeedTree, cKDTree(seed_points)),
        np.asarray(candidate_points, dtype=np.int64),
        seed_ranks,
    )
    eligible = distances <= radius_pixels
    points = candidate_points[eligible]
    output[points[:, 0], points[:, 1]] = canonical_labels[
        owner_ranks[eligible]
    ]
    return output


def expand_detected_segment_labels(
    component_labels: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    radius_pixels: int,
) -> npt.NDArray[np.int32]:
    """Build unique nearest-segment apertures on observable pixels.

    Expansion recovers original-pixel source wings omitted by the detection
    threshold. The input is one bounded measurement plane or tile. Where
    apertures overlap, each pixel belongs to its nearest accepted support, so
    close segments cannot double-count flux.
    """
    labels = _segment_label_plane(component_labels)
    valid = np.asarray(valid_pixels)
    if (
        valid.ndim != _IMAGE_DIMENSIONS
        or valid.shape != labels.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError(
            "component labels and valid pixels must be aligned "
            "two-dimensional planes"
        )
    if isinstance(radius_pixels, bool) or radius_pixels < 0:
        raise ValueError("radius_pixels must be a non-negative integer")
    if not np.any(labels > 0):
        return np.zeros(labels.shape, dtype=np.int32)
    distances, nearest_indices = cast(
        tuple[
            npt.NDArray[np.float64],
            npt.NDArray[np.int32],
        ],
        distance_transform_edt(
            labels == 0,
            return_distances=True,
            return_indices=True,
        ),
    )
    nearest_labels = labels[tuple(nearest_indices)]
    expanded = np.where(
        (distances <= radius_pixels) & valid,
        nearest_labels,
        0,
    )
    return np.asarray(expanded, dtype=np.int32)


@dataclass(frozen=True, slots=True)
class DetectedSegmentPosition:
    """Flux centroid and peak tied to one accepted detection segment."""

    available: bool
    centroid_xy: tuple[float, float] | None
    peak_position_xy: tuple[int, int] | None
    support_pixel_count: int
    integrated_weight: float
    unavailable_reason: SegmentPositionUnavailableReason | None
    weighting: Literal["signed-original", "denoised"] = "signed-original"


def _unavailable_position(
    reason: SegmentPositionUnavailableReason,
    *,
    support_pixel_count: int,
    integrated_weight: float,
) -> DetectedSegmentPosition:
    """Return explicit unavailability without inventing a coordinate."""
    return DetectedSegmentPosition(
        available=False,
        centroid_xy=None,
        peak_position_xy=None,
        support_pixel_count=support_pixel_count,
        integrated_weight=integrated_weight,
        unavailable_reason=reason,
    )


@dataclass(frozen=True, slots=True)
class SegmentWindow:
    """Where one measured window sits inside its image plane.

    Measuring a segment over the whole plane costs image size for every
    segment. A window lets a caller pass only the pixels around one segment
    while keeping every reported position in the plane's pixel frame.
    """

    origin_yx: tuple[int, int]
    plane_shape_yx: tuple[int, int]

    def require_holds(self, shape_yx: tuple[int, int]) -> None:
        """Reject a window that does not fit its plane.

        Raises:
            ValueError: If the origin is negative or the window leaves the
                plane.
        """
        if min(self.origin_yx) < 0:
            raise ValueError("segment window origin must be non-negative")
        if any(
            origin + extent > plane
            for origin, extent, plane in zip(
                self.origin_yx, shape_yx, self.plane_shape_yx, strict=True
            )
        ):
            raise ValueError("segment window must stay inside its plane")


def measure_segment_position_pixels(
    y_pixels: npt.NDArray[np.int64],
    x_pixels: npt.NDArray[np.int64],
    signal_jy_per_beam: npt.NDArray[np.float64],
    *,
    plane_shape_yx: tuple[int, int],
) -> DetectedSegmentPosition:
    """Measure a signed-flux centroid and peak from support pixels alone.

    The arrays hold one segment's support pixels in raster order, with
    coordinates in the plane's pixel frame. A segment too wide to read at
    once is measured from the pixels its cores return, and the result is
    the one a window holding the whole segment would give, bit for bit:
    every sum and the first maximum visit the same pixels in the same order.
    """
    finite = np.isfinite(signal_jy_per_beam)
    support_pixel_count = int(np.count_nonzero(finite))
    if support_pixel_count == 0:
        return _unavailable_position(
            "empty-finite-support",
            support_pixel_count=0,
            integrated_weight=0.0,
        )
    weights = signal_jy_per_beam[finite]
    integrated_weight = float(np.sum(weights, dtype=np.float64))
    if not np.isfinite(integrated_weight) or integrated_weight <= 0:
        return _unavailable_position(
            "nonpositive-segment-flux",
            support_pixel_count=support_pixel_count,
            integrated_weight=integrated_weight,
        )
    conditioning = float(np.sum(np.abs(weights))) / integrated_weight
    epsilon = np.finfo(np.float64).eps
    if not np.isfinite(conditioning) or conditioning * epsilon > np.sqrt(
        epsilon
    ):
        return _unavailable_position(
            "ill-conditioned-segment-position",
            support_pixel_count=support_pixel_count,
            integrated_weight=integrated_weight,
        )
    # The coordinates are already in the plane's pixel frame, so which
    # window, if any, the pixels came from changes nothing in the sums.
    y_support = y_pixels[finite]
    x_support = x_pixels[finite]
    centroid_xy = (
        float(
            np.sum(x_support * weights, dtype=np.float64) / integrated_weight
        ),
        float(
            np.sum(y_support * weights, dtype=np.float64) / integrated_weight
        ),
    )
    # Signed cancellation can give a finite but physically unusable centroid.
    # Test the support rectangle, not mask membership: a shell's centre can
    # legitimately lie in its hole. Do not clamp the result to a bright pixel.
    roundoff = (
        epsilon * support_pixel_count * conditioning * max(plane_shape_yx)
    )
    if not (
        x_support.min() - roundoff
        <= centroid_xy[0]
        <= x_support.max() + roundoff
        and y_support.min() - roundoff
        <= centroid_xy[1]
        <= y_support.max() + roundoff
    ):
        return _unavailable_position(
            "ill-conditioned-segment-position",
            support_pixel_count=support_pixel_count,
            integrated_weight=integrated_weight,
        )
    # Raster order makes the first maximum the row-major first one.
    peak = int(np.argmax(weights))
    return DetectedSegmentPosition(
        available=True,
        centroid_xy=centroid_xy,
        peak_position_xy=(int(x_support[peak]), int(y_support[peak])),
        support_pixel_count=support_pixel_count,
        integrated_weight=integrated_weight,
        unavailable_reason=None,
    )
