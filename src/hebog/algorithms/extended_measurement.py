# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Pure measurement kernels for irregular extended emission."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import atan2, ceil, degrees, fsum, hypot, isfinite, log, sqrt
from numbers import Integral
from typing import Literal, Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import (
    binary_dilation,
    binary_opening,
    convolve,
    distance_transform_edt,
)
from scipy.ndimage import (
    label as connected_component_labels,
)
from scipy.spatial import (
    cKDTree,  # pyright: ignore[reportAttributeAccessIssue]
)

from hebog.config import ExtendedEmissionMeasurementConfig
from hebog.data_models.measurement import (
    ExtendedEmissionMeasurementResult,
    ExtendedEmissionPhotometry,
    ExtendedEmissionTarget,
    ExtendedMeasurementGeometry,
    ExtendedMeasurementTruncation,
    ExtendedMomentShape,
    MeasuredExtendedEmission,
    UnavailableExtendedEmission,
)
from hebog.data_models.partitioning import TilePartition

SegmentPositionUnavailableReason = Literal[
    "empty-finite-support",
    "nonpositive-segment-flux",
]
_IMAGE_DIMENSIONS = 2
_SUB_BEAM_OPENING_WIDTH_PIXELS = 3
_MULTISCALE_CORE_MINIMUM_NEIGHBORS = 5
_MULTISCALE_BOUNDARY_MINIMUM_SNR = 6.0
_MULTISCALE_RECOVERY_RADIUS_BEAMS = 0.5
_NEIGHBORHOOD_PIXEL_COUNT = 9
_FWHM_FROM_SIGMA = 2.0 * sqrt(2.0 * log(2.0))


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
    """Return the halo covering opening and multiscale support recovery."""
    opening_radius_pixels = _SUB_BEAM_OPENING_WIDTH_PIXELS // 2
    return max(
        opening_radius_pixels,
        multiscale_recovery_radius_pixels(
            beam_major_fwhm_pixels,
            recovery_radius_beams=recovery_radius_beams,
        ),
    )


def extended_measurement_halo_pixels(
    config: ExtendedEmissionMeasurementConfig,
    *,
    beam_major_fwhm_pixels: float,
) -> int:
    """Return the configured nearest-owned photometry radius in pixels."""
    if (
        isinstance(beam_major_fwhm_pixels, bool)
        or not isfinite(beam_major_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0
    ):
        raise ValueError("beam major FWHM must be finite and positive")
    return ceil(config.aperture_radius_beams * beam_major_fwhm_pixels)


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


def refine_multiscale_segment_labels(  # noqa: PLR0913
    component_labels: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    core_minimum_neighbors: int = _MULTISCALE_CORE_MINIMUM_NEIGHBORS,
    boundary_minimum_snr: float = _MULTISCALE_BOUNDARY_MINIMUM_SNR,
    recovery_radius_beams: float = _MULTISCALE_RECOVERY_RADIUS_BEAMS,
) -> npt.NDArray[np.int32]:
    """Refine noisy flood boundaries with calibrated multiscale evidence.

    Dense opened support remains without an additional significance test.
    Sparse boundary pixels remain only at high combined S/N, while adjacent
    significant à trous support may recover coherent emission omitted by the
    original-pixel flood. Recovered pixels inherit the nearest original
    segment identity, preserving deterministic ownership without merging or
    relabelling sources.
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
    recovery_radius_pixels = multiscale_recovery_radius_pixels(
        beam_major_fwhm_pixels,
        recovery_radius_beams=recovery_radius_beams,
    )
    cleaned = clean_detected_segment_labels(labels)
    cleaned_support = cleaned > 0
    if not np.any(cleaned_support):
        return cleaned
    neighbor_count = convolve(
        cleaned_support.astype(np.int8),
        np.ones((3, 3), dtype=np.int8),
        mode="constant",
        cval=0,
    )
    dense_core = cleaned_support & (neighbor_count >= core_minimum_neighbors)
    high_confidence_boundary = cleaned_support & (
        np.asarray(snr, dtype=np.float64) >= boundary_minimum_snr
    )
    nearby = (
        binary_dilation(cleaned_support, iterations=recovery_radius_pixels)
        if recovery_radius_pixels > 0
        else cleaned_support
    )
    recovered = multiscale_support & nearby
    retained = dense_core | high_confidence_boundary | recovered
    _, nearest_indices = cast(
        tuple[npt.NDArray[np.float64], npt.NDArray[np.int32]],
        distance_transform_edt(
            ~cleaned_support,
            return_distances=True,
            return_indices=True,
        ),
    )
    nearest_labels = cleaned[tuple(nearest_indices)]
    return np.where(retained, nearest_labels, 0).astype(np.int32, copy=False)


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
) -> npt.NDArray[np.int32]:
    """Attach bounded multiscale support without merging direct seed owners.

    Positive input labels are authoritative direct-residual source identities.
    Eligible support is assigned to the nearest exact seed pixel. Equal
    distances use the owner whose globally row-major seed reference appears
    first, independently of task-local label integers or completion order.
    Tiled callers must pass the global reference pixel of every owner present
    in the tile; a complete-plane call can derive those references directly.
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
    connected_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(
            ((labels > 0) | significant) & valid,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
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


def measure_detected_segment_position(
    signal_jy_per_beam: npt.NDArray[np.float64],
    support_mask: npt.NDArray[np.bool_],
) -> DetectedSegmentPosition:
    """Measure a signed-flux centroid and peak on exact source support.

    The inputs are original background-subtracted pixels and the accepted
    catalogue segment. No measurement-only growth or morphology model is
    applied. Equal peak values use NumPy's first flat maximum, which is
    deterministic row-major ``y`` then ``x`` order.

    Args:
        signal_jy_per_beam: Two-dimensional original-pixel signal plane.
        support_mask: Boolean pixels owned by this source segment.

    Returns:
        A position estimate or a typed unavailable result.

    Raises:
        ValueError: If arrays are not aligned two-dimensional planes or the
            support array is not boolean.
    """
    if (
        signal_jy_per_beam.ndim != _IMAGE_DIMENSIONS
        or support_mask.ndim != _IMAGE_DIMENSIONS
        or signal_jy_per_beam.shape != support_mask.shape
    ):
        raise ValueError(
            "segment signal and support must be aligned two-dimensional planes"
        )
    if support_mask.dtype != np.bool_:
        raise ValueError("segment support must have boolean dtype")
    finite_support = support_mask & np.isfinite(signal_jy_per_beam)
    support_pixel_count = int(np.count_nonzero(finite_support))
    if support_pixel_count == 0:
        return _unavailable_position(
            "empty-finite-support",
            support_pixel_count=0,
            integrated_weight=0.0,
        )
    weights = signal_jy_per_beam[finite_support]
    integrated_weight = float(np.sum(weights, dtype=np.float64))
    if not np.isfinite(integrated_weight) or integrated_weight <= 0:
        return _unavailable_position(
            "nonpositive-segment-flux",
            support_pixel_count=support_pixel_count,
            integrated_weight=integrated_weight,
        )
    y_pixels, x_pixels = np.nonzero(finite_support)
    centroid_xy = (
        float(
            np.sum(x_pixels * weights, dtype=np.float64) / integrated_weight
        ),
        float(
            np.sum(y_pixels * weights, dtype=np.float64) / integrated_weight
        ),
    )
    peak_flat_index = int(
        np.argmax(np.where(finite_support, signal_jy_per_beam, -np.inf))
    )
    peak_y, peak_x = np.unravel_index(
        peak_flat_index, signal_jy_per_beam.shape
    )
    return DetectedSegmentPosition(
        available=True,
        centroid_xy=centroid_xy,
        peak_position_xy=(int(peak_x), int(peak_y)),
        support_pixel_count=support_pixel_count,
        integrated_weight=integrated_weight,
        unavailable_reason=None,
    )


@dataclass(frozen=True, slots=True)
class ExtendedEmissionTileTarget:
    """One task-local positive label bound to a global measurement target."""

    local_label: int
    target: ExtendedEmissionTarget

    def __post_init__(self) -> None:
        """Require a positive task-local label."""
        if (
            isinstance(self.local_label, bool)
            or not isinstance(self.local_label, Integral)
            or self.local_label < 1
        ):
            raise ValueError("extended tile target label must be positive")


@dataclass(frozen=True, slots=True)
class ExtendedEmissionTilePartial:
    """Array-free sufficient statistics from one non-overlapping tile core."""

    target: ExtendedEmissionTarget
    support_pixel_count: int
    invalid_support_pixel_count: int
    support_weight: float
    support_x_weight: float
    support_y_weight: float
    support_xx_weight: float
    support_xy_weight: float
    support_yy_weight: float
    peak_brightness_jy_per_beam: float | None
    peak_position_yx: tuple[int, int] | None
    regularized_position_requested: bool
    invalid_regularized_support_pixel_count: int
    regularized_support_weight: float
    regularized_support_x_weight: float
    regularized_support_y_weight: float
    regularized_peak_signal_jy_per_beam: float | None
    regularized_peak_position_yx: tuple[int, int] | None
    aperture_pixel_count: int
    observable_aperture_pixel_count: int
    aperture_signal_sum_jy_per_beam: float
    aperture_background_sum_jy_per_beam: float
    aperture_rms_squared_sum: float

    def __post_init__(self) -> None:
        """Require non-negative counts and paired peak availability."""
        counts = (
            self.support_pixel_count,
            self.invalid_support_pixel_count,
            self.invalid_regularized_support_pixel_count,
            self.aperture_pixel_count,
            self.observable_aperture_pixel_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("extended partial counts must be non-negative")
        if self.invalid_support_pixel_count > self.support_pixel_count:
            raise ValueError("invalid support count exceeds exact support")
        if (
            self.invalid_regularized_support_pixel_count
            > self.support_pixel_count
        ):
            raise ValueError(
                "invalid regularized-position count exceeds exact support"
            )
        if self.observable_aperture_pixel_count > self.aperture_pixel_count:
            raise ValueError("observable aperture count exceeds its aperture")
        if (self.peak_brightness_jy_per_beam is None) != (
            self.peak_position_yx is None
        ):
            raise ValueError("extended partial peak availability disagrees")
        if (self.regularized_peak_signal_jy_per_beam is None) != (
            self.regularized_peak_position_yx is None
        ):
            raise ValueError(
                "regularized-position partial peak availability disagrees"
            )
        if not self.regularized_position_requested and (
            self.invalid_regularized_support_pixel_count
            or self.regularized_support_weight
            or self.regularized_support_x_weight
            or self.regularized_support_y_weight
            or self.regularized_peak_signal_jy_per_beam is not None
        ):
            raise ValueError(
                "unrequested regularized-position evidence must be empty"
            )


@dataclass(frozen=True, slots=True)
class ExtendedEmissionTilePlanes:
    """Worker-local original pixels and aligned ownership label cores."""

    residual_jy_per_beam: npt.ArrayLike
    background_jy_per_beam: npt.ArrayLike
    rms_jy_per_beam: npt.ArrayLike
    valid_pixels: npt.ArrayLike
    support_labels: npt.ArrayLike
    aperture_labels: npt.ArrayLike
    regularized_position_signal_jy_per_beam: npt.ArrayLike | None = None


def _validated_extended_tile_arrays(
    planes: ExtendedEmissionTilePlanes,
    partition: TilePartition,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
    npt.NDArray[np.int32],
    npt.NDArray[np.float64] | None,
]:
    """Validate aligned worker-owned original-pixel measurement planes."""
    residual = np.asarray(planes.residual_jy_per_beam)
    background = np.asarray(planes.background_jy_per_beam)
    rms = np.asarray(planes.rms_jy_per_beam)
    valid = np.asarray(planes.valid_pixels)
    support = np.asarray(planes.support_labels)
    aperture = np.asarray(planes.aperture_labels)
    arrays = (residual, background, rms, valid, support, aperture)
    if any(array.ndim != _IMAGE_DIMENSIONS for array in arrays) or any(
        array.shape != partition.core_bounds.shape_yx for array in arrays
    ):
        raise ValueError(
            "extended measurement planes must match the two-dimensional core"
        )
    if any(
        array.dtype != np.dtype(np.float64)
        for array in (residual, background, rms)
    ):
        raise TypeError("extended physical measurement planes must be float64")
    if valid.dtype != np.dtype(np.bool_):
        raise TypeError("extended measurement validity must be boolean")
    if any(array.dtype != np.dtype(np.int32) for array in (support, aperture)):
        raise TypeError("extended measurement labels must be int32")
    if np.any(support < 0) or np.any(aperture < 0):
        raise ValueError("extended measurement labels must be non-negative")
    if np.any((support > 0) & (support != aperture)):
        raise ValueError(
            "extended exact support must retain aperture ownership"
        )
    regularized: npt.NDArray[np.float64] | None = None
    if planes.regularized_position_signal_jy_per_beam is not None:
        position_values = np.asarray(
            planes.regularized_position_signal_jy_per_beam
        )
        if position_values.ndim != _IMAGE_DIMENSIONS or (
            position_values.shape != partition.core_bounds.shape_yx
        ):
            raise ValueError(
                "regularized position signal must match the task core"
            )
        if position_values.dtype != np.dtype(np.float64):
            raise TypeError("regularized position signal must be float64")
        regularized = position_values
    return residual, background, rms, valid, support, aperture, regularized


def _regularized_position_statistics(
    signal: npt.NDArray[np.float64] | None,
    exact_support: npt.NDArray[np.bool_],
    observable_support: npt.NDArray[np.bool_],
    coordinate_grids_xy: tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ],
    origin_yx: tuple[int, int],
) -> tuple[
    int,
    float,
    float,
    float,
    float | None,
    tuple[int, int] | None,
]:
    """Reduce one optional regularized position plane to scalar evidence."""
    if signal is None:
        return 0, 0.0, 0.0, 0.0, None, None
    x_grid, y_grid = coordinate_grids_xy
    support = observable_support & np.isfinite(signal)
    values = signal[support]
    invalid_count = int(np.count_nonzero(exact_support & ~support))
    weight = float(np.sum(values, dtype=np.float64))
    x_weight = float(np.sum(x_grid[support] * values, dtype=np.float64))
    y_weight = float(np.sum(y_grid[support] * values, dtype=np.float64))
    if not values.size:
        return invalid_count, weight, x_weight, y_weight, None, None
    peak_flat = int(np.argmax(np.where(support, signal, -np.inf)))
    peak_y, peak_x = np.unravel_index(peak_flat, signal.shape)
    origin_y, origin_x = origin_yx
    return (
        invalid_count,
        weight,
        x_weight,
        y_weight,
        float(signal[peak_y, peak_x]),
        (int(peak_y) + origin_y, int(peak_x) + origin_x),
    )


def measure_extended_emission_tile(
    planes: ExtendedEmissionTilePlanes,
    partition: TilePartition,
    targets: tuple[ExtendedEmissionTileTarget, ...],
) -> tuple[ExtendedEmissionTilePartial, ...]:
    """Reduce one bounded core to array-free extended-source statistics."""
    residual, background, rms, valid, support, aperture, regularized = (
        _validated_extended_tile_arrays(
            planes,
            partition,
        )
    )
    ordered = tuple(sorted(targets, key=lambda item: item.local_label))
    local_labels = tuple(item.local_label for item in ordered)
    object_ids = tuple(item.target.object_id for item in ordered)
    if (
        targets != ordered
        or len(set(local_labels)) != len(local_labels)
        or len(set(object_ids)) != len(object_ids)
    ):
        raise ValueError("extended tile targets must be unique and canonical")
    known_labels = set(local_labels)
    observed_labels = {int(value) for value in np.unique(aperture)} - {0}
    if not observed_labels.issubset(known_labels):
        raise ValueError("extended aperture contains an unknown target label")

    bounds = partition.core_bounds
    coordinate_grids = np.indices(support.shape, dtype=np.float64)
    y_grid = np.asarray(coordinate_grids[0], dtype=np.float64)
    x_grid = np.asarray(coordinate_grids[1], dtype=np.float64)
    x_grid += bounds.x_start
    y_grid += bounds.y_start
    scientifically_valid = (
        valid
        & np.isfinite(residual)
        & np.isfinite(background)
        & np.isfinite(rms)
        & (rms > 0)
    )
    partials: list[ExtendedEmissionTilePartial] = []
    for item in ordered:
        exact = support == item.local_label
        owned_aperture = aperture == item.local_label
        if not np.any(exact) and not np.any(owned_aperture):
            continue
        observable_support = exact & scientifically_valid
        observable_aperture = owned_aperture & scientifically_valid
        support_values = residual[observable_support]
        support_x = x_grid[observable_support]
        support_y = y_grid[observable_support]
        if support_values.size:
            peak_flat = int(
                np.argmax(np.where(observable_support, residual, -np.inf))
            )
            peak_y, peak_x = np.unravel_index(peak_flat, residual.shape)
            peak_value: float | None = float(residual[peak_y, peak_x])
            peak_position: tuple[int, int] | None = (
                int(peak_y) + bounds.y_start,
                int(peak_x) + bounds.x_start,
            )
        else:
            peak_value = None
            peak_position = None
        (
            regularized_invalid_count,
            regularized_weight,
            regularized_x_weight,
            regularized_y_weight,
            regularized_peak_value,
            regularized_peak_position,
        ) = _regularized_position_statistics(
            regularized,
            exact,
            observable_support,
            (x_grid, y_grid),
            (bounds.y_start, bounds.x_start),
        )
        partials.append(
            ExtendedEmissionTilePartial(
                target=item.target,
                support_pixel_count=int(np.count_nonzero(exact)),
                invalid_support_pixel_count=int(
                    np.count_nonzero(exact & ~scientifically_valid)
                ),
                support_weight=float(np.sum(support_values, dtype=np.float64)),
                support_x_weight=float(
                    np.sum(support_x * support_values, dtype=np.float64)
                ),
                support_y_weight=float(
                    np.sum(support_y * support_values, dtype=np.float64)
                ),
                support_xx_weight=float(
                    np.sum(
                        support_x * support_x * support_values,
                        dtype=np.float64,
                    )
                ),
                support_xy_weight=float(
                    np.sum(
                        support_x * support_y * support_values,
                        dtype=np.float64,
                    )
                ),
                support_yy_weight=float(
                    np.sum(
                        support_y * support_y * support_values,
                        dtype=np.float64,
                    )
                ),
                peak_brightness_jy_per_beam=peak_value,
                peak_position_yx=peak_position,
                regularized_position_requested=regularized is not None,
                invalid_regularized_support_pixel_count=(
                    regularized_invalid_count
                ),
                regularized_support_weight=regularized_weight,
                regularized_support_x_weight=regularized_x_weight,
                regularized_support_y_weight=regularized_y_weight,
                regularized_peak_signal_jy_per_beam=(regularized_peak_value),
                regularized_peak_position_yx=regularized_peak_position,
                aperture_pixel_count=int(np.count_nonzero(owned_aperture)),
                observable_aperture_pixel_count=int(
                    np.count_nonzero(observable_aperture)
                ),
                aperture_signal_sum_jy_per_beam=float(
                    np.sum(residual[observable_aperture], dtype=np.float64)
                ),
                aperture_background_sum_jy_per_beam=float(
                    np.sum(background[observable_aperture], dtype=np.float64)
                ),
                aperture_rms_squared_sum=float(
                    np.sum(rms[observable_aperture] ** 2, dtype=np.float64)
                ),
            )
        )
    return tuple(partials)


def _truncation(
    target: ExtendedEmissionTarget,
    *,
    aperture_pixel_count: int,
    observable_aperture_pixel_count: int,
    aperture_radius_pixels: int,
    image_shape_yx: tuple[int, int],
) -> ExtendedMeasurementTruncation:
    """Return explicit edge and invalid-pixel aperture truncation."""
    if aperture_pixel_count < 1:
        raise ValueError(
            "extended target has no in-image measurement aperture"
        )
    fraction = observable_aperture_pixel_count / aperture_pixel_count
    edge = (
        target.bounds.y_start < aperture_radius_pixels
        or target.bounds.x_start < aperture_radius_pixels
        or image_shape_yx[0] - target.bounds.y_stop < aperture_radius_pixels
        or image_shape_yx[1] - target.bounds.x_stop < aperture_radius_pixels
    )
    invalid = observable_aperture_pixel_count < aperture_pixel_count
    status: Literal[
        "none",
        "image-edge",
        "invalid-pixels",
        "image-edge-and-invalid-pixels",
    ]
    if edge and invalid:
        status = "image-edge-and-invalid-pixels"
    elif edge:
        status = "image-edge"
    elif invalid:
        status = "invalid-pixels"
    else:
        status = "none"
    return ExtendedMeasurementTruncation(
        status=status,
        observable_aperture_fraction=fraction,
    )


def _unavailable_extended(
    target: ExtendedEmissionTarget,
    reason: Literal[
        "non-finite-support",
        "non-positive-support-flux",
        "non-positive-aperture-flux",
    ],
    truncation: ExtendedMeasurementTruncation,
) -> UnavailableExtendedEmission:
    """Construct one typed unavailable original-pixel result."""
    return UnavailableExtendedEmission(
        target=target,
        reason=reason,
        truncation=truncation,
    )


def _extended_shape(
    *,
    covariance_xx: float,
    covariance_xy: float,
    covariance_yy: float,
    config: ExtendedEmissionMeasurementConfig,
) -> tuple[
    ExtendedMomentShape | None,
    Literal["underdetermined-support", "singular-covariance"] | None,
]:
    """Return one positive-definite moment ellipse or an explicit reason."""
    trace = covariance_xx + covariance_yy
    discriminant = hypot(covariance_xx - covariance_yy, 2 * covariance_xy)
    major_variance = 0.5 * (trace + discriminant)
    minor_variance = 0.5 * (trace - discriminant)
    if (
        not all(
            isfinite(value)
            for value in (
                covariance_xx,
                covariance_xy,
                covariance_yy,
                major_variance,
                minor_variance,
            )
        )
        or major_variance <= 0
        or minor_variance
        <= config.covariance_relative_tolerance * major_variance
    ):
        return None, "singular-covariance"
    if discriminant <= config.covariance_relative_tolerance * trace:
        angle = 0.0
    else:
        angle = (
            degrees(
                0.5 * atan2(2 * covariance_xy, covariance_xx - covariance_yy)
            )
            % 180.0
        )
    return (
        ExtendedMomentShape(
            covariance_xx_pixels_squared=covariance_xx,
            covariance_xy_pixels_squared=covariance_xy,
            covariance_yy_pixels_squared=covariance_yy,
            major_fwhm_pixels=_FWHM_FROM_SIGMA * sqrt(major_variance),
            minor_fwhm_pixels=_FWHM_FROM_SIGMA * sqrt(minor_variance),
            position_angle_degrees=angle,
        ),
        None,
    )


@dataclass(frozen=True, slots=True)
class _ExtendedEmissionAggregate:
    """Canonical scalar totals for one complete extended target."""

    target: ExtendedEmissionTarget
    support_pixel_count: int
    invalid_support_pixel_count: int
    support_weight: float
    support_x_weight: float
    support_y_weight: float
    support_xx_weight: float
    support_xy_weight: float
    support_yy_weight: float
    peak_brightness_jy_per_beam: float
    peak_position_yx: tuple[int, int]
    regularized_position_requested: bool
    invalid_regularized_support_pixel_count: int
    regularized_support_weight: float
    regularized_support_x_weight: float
    regularized_support_y_weight: float
    regularized_peak_signal_jy_per_beam: float
    regularized_peak_position_yx: tuple[int, int]
    aperture_pixel_count: int
    observable_aperture_pixel_count: int
    aperture_signal_sum_jy_per_beam: float
    aperture_background_sum_jy_per_beam: float
    aperture_rms_squared_sum: float


def _aggregate_extended_target(
    target: ExtendedEmissionTarget,
    partials: list[ExtendedEmissionTilePartial],
) -> _ExtendedEmissionAggregate:
    """Combine one target's scalar partials in deterministic task order."""
    if not partials:
        raise ValueError("extended target has no measurement partials")
    support_count = sum(item.support_pixel_count for item in partials)
    if support_count != target.support_pixel_count:
        raise ValueError("extended partials disagree with target support")
    peaks = tuple(
        (item.peak_brightness_jy_per_beam, item.peak_position_yx)
        for item in partials
        if item.peak_brightness_jy_per_beam is not None
        and item.peak_position_yx is not None
    )
    if not peaks:
        peak_value, peak_position = -np.inf, (-1, -1)
    else:
        selected_value, selected_position = min(
            peaks,
            key=lambda item: (
                -item[0],
                item[1],
            ),
        )
        peak_value = selected_value
        peak_position = selected_position
    regularized_peaks = tuple(
        (
            item.regularized_peak_signal_jy_per_beam,
            item.regularized_peak_position_yx,
        )
        for item in partials
        if item.regularized_peak_signal_jy_per_beam is not None
        and item.regularized_peak_position_yx is not None
    )
    if not regularized_peaks:
        regularized_peak_value = -np.inf
        regularized_peak_position = (-1, -1)
    else:
        regularized_peak_value, regularized_peak_position = min(
            regularized_peaks,
            key=lambda item: (-item[0], item[1]),
        )
    regularized_requested = {
        item.regularized_position_requested for item in partials
    }
    if len(regularized_requested) != 1:
        raise ValueError(
            "extended partials disagree on regularized position provenance"
        )
    return _ExtendedEmissionAggregate(
        target=target,
        support_pixel_count=support_count,
        invalid_support_pixel_count=sum(
            item.invalid_support_pixel_count for item in partials
        ),
        support_weight=fsum(item.support_weight for item in partials),
        support_x_weight=fsum(item.support_x_weight for item in partials),
        support_y_weight=fsum(item.support_y_weight for item in partials),
        support_xx_weight=fsum(item.support_xx_weight for item in partials),
        support_xy_weight=fsum(item.support_xy_weight for item in partials),
        support_yy_weight=fsum(item.support_yy_weight for item in partials),
        peak_brightness_jy_per_beam=peak_value,
        peak_position_yx=peak_position,
        regularized_position_requested=regularized_requested.pop(),
        invalid_regularized_support_pixel_count=sum(
            item.invalid_regularized_support_pixel_count for item in partials
        ),
        regularized_support_weight=fsum(
            item.regularized_support_weight for item in partials
        ),
        regularized_support_x_weight=fsum(
            item.regularized_support_x_weight for item in partials
        ),
        regularized_support_y_weight=fsum(
            item.regularized_support_y_weight for item in partials
        ),
        regularized_peak_signal_jy_per_beam=regularized_peak_value,
        regularized_peak_position_yx=regularized_peak_position,
        aperture_pixel_count=sum(
            item.aperture_pixel_count for item in partials
        ),
        observable_aperture_pixel_count=sum(
            item.observable_aperture_pixel_count for item in partials
        ),
        aperture_signal_sum_jy_per_beam=fsum(
            item.aperture_signal_sum_jy_per_beam for item in partials
        ),
        aperture_background_sum_jy_per_beam=fsum(
            item.aperture_background_sum_jy_per_beam for item in partials
        ),
        aperture_rms_squared_sum=fsum(
            item.aperture_rms_squared_sum for item in partials
        ),
    )


def _aggregate_shape(
    aggregate: _ExtendedEmissionAggregate,
    *,
    centroid_xy: tuple[float, float],
    config: ExtendedEmissionMeasurementConfig,
) -> tuple[
    ExtendedMomentShape | None,
    Literal["underdetermined-support", "singular-covariance"] | None,
]:
    """Derive one exact-support moment ellipse from scalar totals."""
    if aggregate.support_pixel_count < config.minimum_shape_pixels:
        return None, "underdetermined-support"
    centroid_x, centroid_y = centroid_xy
    return _extended_shape(
        covariance_xx=(
            aggregate.support_xx_weight / aggregate.support_weight
            - centroid_x**2
        ),
        covariance_xy=(
            aggregate.support_xy_weight / aggregate.support_weight
            - centroid_x * centroid_y
        ),
        covariance_yy=(
            aggregate.support_yy_weight / aggregate.support_weight
            - centroid_y**2
        ),
        config=config,
    )


def _selected_position(
    aggregate: _ExtendedEmissionAggregate,
    config: ExtendedEmissionMeasurementConfig,
) -> tuple[
    tuple[float, float],
    tuple[int, int],
    Literal[
        "direct-original-residual",
        "regularized-direct-plus-multiscale",
    ],
]:
    """Apply the reviewed compact-concentration safeguard and fallback."""
    direct_centroid = (
        aggregate.support_x_weight / aggregate.support_weight,
        aggregate.support_y_weight / aggregate.support_weight,
    )
    direct_mean = aggregate.support_weight / aggregate.support_pixel_count
    concentration = (
        aggregate.peak_brightness_jy_per_beam / direct_mean
        if isfinite(direct_mean) and direct_mean > 0
        else np.inf
    )
    regularized_available = (
        aggregate.regularized_position_requested
        and not aggregate.invalid_regularized_support_pixel_count
        and isfinite(aggregate.regularized_support_weight)
        and aggregate.regularized_support_weight > 0
        and isfinite(aggregate.regularized_peak_signal_jy_per_beam)
    )
    if (
        regularized_available
        and concentration
        <= config.denoised_position_maximum_peak_to_mean_ratio
    ):
        return (
            (
                aggregate.regularized_support_x_weight
                / aggregate.regularized_support_weight,
                aggregate.regularized_support_y_weight
                / aggregate.regularized_support_weight,
            ),
            aggregate.regularized_peak_position_yx,
            "regularized-direct-plus-multiscale",
        )
    return (
        direct_centroid,
        aggregate.peak_position_yx,
        "direct-original-residual",
    )


def _measurement_from_aggregate(
    aggregate: _ExtendedEmissionAggregate,
    geometry: ExtendedMeasurementGeometry,
    config: ExtendedEmissionMeasurementConfig,
    *,
    image_shape_yx: tuple[int, int],
) -> ExtendedEmissionMeasurementResult:
    """Apply availability semantics to one complete scalar aggregate."""
    radius_pixels = extended_measurement_halo_pixels(
        config,
        beam_major_fwhm_pixels=(geometry.restoring_beam_major_fwhm_pixels),
    )
    truncation = _truncation(
        aggregate.target,
        aperture_pixel_count=aggregate.aperture_pixel_count,
        observable_aperture_pixel_count=(
            aggregate.observable_aperture_pixel_count
        ),
        aperture_radius_pixels=radius_pixels,
        image_shape_yx=image_shape_yx,
    )
    if aggregate.invalid_support_pixel_count:
        return _unavailable_extended(
            aggregate.target,
            "non-finite-support",
            truncation,
        )
    if not isfinite(aggregate.support_weight) or aggregate.support_weight <= 0:
        return _unavailable_extended(
            aggregate.target,
            "non-positive-support-flux",
            truncation,
        )
    if (
        aggregate.observable_aperture_pixel_count < 1
        or not isfinite(aggregate.aperture_signal_sum_jy_per_beam)
        or aggregate.aperture_signal_sum_jy_per_beam <= 0
    ):
        return _unavailable_extended(
            aggregate.target,
            "non-positive-aperture-flux",
            truncation,
        )
    shape_centroid = (
        aggregate.support_x_weight / aggregate.support_weight,
        aggregate.support_y_weight / aggregate.support_weight,
    )
    shape, shape_reason = _aggregate_shape(
        aggregate,
        centroid_xy=shape_centroid,
        config=config,
    )
    centroid, position_peak_yx, position_weight_kind = _selected_position(
        aggregate,
        config,
    )
    observable_count = aggregate.observable_aperture_pixel_count
    ratio = geometry.pixel_to_beam_area_ratio
    return MeasuredExtendedEmission(
        target=aggregate.target,
        photometry=ExtendedEmissionPhotometry(
            peak_brightness_jy_per_beam=(
                aggregate.peak_brightness_jy_per_beam
            ),
            integrated_flux_jy=(
                aggregate.aperture_signal_sum_jy_per_beam * ratio
            ),
            integrated_flux_error_jy=sqrt(
                max(0.0, ratio * aggregate.aperture_rms_squared_sum)
            ),
            local_rms_jy_per_beam=sqrt(
                aggregate.aperture_rms_squared_sum / observable_count
            ),
            mean_background_jy_per_beam=(
                aggregate.aperture_background_sum_jy_per_beam
                / observable_count
            ),
            aperture_pixel_count=aggregate.aperture_pixel_count,
            observable_aperture_pixel_count=observable_count,
        ),
        centroid_xy=centroid,
        peak_position_xy=(
            position_peak_yx[1],
            position_peak_yx[0],
        ),
        shape=shape,
        shape_status="available" if shape is not None else "unavailable",
        shape_unavailable_reason=shape_reason,
        truncation=truncation,
        position_weight_kind=position_weight_kind,
    )


def combine_extended_emission_partials(
    targets: tuple[ExtendedEmissionTarget, ...],
    partials: tuple[ExtendedEmissionTilePartial, ...],
    geometry: ExtendedMeasurementGeometry,
    config: ExtendedEmissionMeasurementConfig,
    *,
    image_shape_yx: tuple[int, int],
) -> tuple[ExtendedEmissionMeasurementResult, ...]:
    """Combine bounded tile statistics into canonical extended measurements."""
    if min(image_shape_yx) < 1:
        raise ValueError("extended measurement image shape must be positive")
    if targets != tuple(
        sorted(targets, key=lambda item: item.object_id)
    ) or len({target.object_id for target in targets}) != len(targets):
        raise ValueError(
            "extended measurement targets must be unique and canonical"
        )
    targets_by_id = {target.object_id: target for target in targets}
    grouped: dict[str, list[ExtendedEmissionTilePartial]] = {
        target.object_id: [] for target in targets
    }
    for partial in partials:
        expected = targets_by_id.get(partial.target.object_id)
        if expected is None or partial.target != expected:
            raise ValueError("extended partial belongs to an unknown target")
        grouped[partial.target.object_id].append(partial)
    return tuple(
        _measurement_from_aggregate(
            _aggregate_extended_target(target, grouped[target.object_id]),
            geometry,
            config,
            image_shape_yx=image_shape_yx,
        )
        for target in targets
    )
