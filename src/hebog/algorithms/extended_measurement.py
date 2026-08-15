# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Pure measurement kernels for irregular extended emission."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from numbers import Integral
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import (
    binary_dilation,
    binary_opening,
    convolve,
    distance_transform_edt,
)

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
    if not isfinite(beam_major_fwhm_pixels) or beam_major_fwhm_pixels <= 0:
        raise ValueError("beam major FWHM must be finite and positive")
    if (
        isinstance(core_minimum_neighbors, bool)
        or not isinstance(core_minimum_neighbors, Integral)
        or not 1 <= core_minimum_neighbors <= _NEIGHBORHOOD_PIXEL_COUNT
    ):
        raise ValueError("core minimum neighbors must be an integer in [1, 9]")
    if not isfinite(boundary_minimum_snr) or boundary_minimum_snr <= 0:
        raise ValueError("boundary minimum SNR must be finite and positive")
    if not isfinite(recovery_radius_beams) or recovery_radius_beams < 0:
        raise ValueError("recovery radius must be finite and non-negative")
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
    recovery_radius_pixels = ceil(
        recovery_radius_beams * beam_major_fwhm_pixels
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
