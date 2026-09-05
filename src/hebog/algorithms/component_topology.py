# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Bounded component topology within connected detection islands."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import find_objects

from hebog.algorithms.deblending import (
    CompactIslandPixels,
    deblend_compact_island,
)
from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactDeblendConfig
from hebog.data_models.partitioning import ImageBounds

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class DeblendedComponentTopology:
    """Component owners plus explicit bounded-deblending disposition."""

    direct_component_labels: npt.NDArray[np.int32]
    measurement_component_labels: npt.NDArray[np.int32]
    deblended_parent_count: int
    deferred_parent_count: int


def _validated_inputs(
    normalized_residual: npt.ArrayLike,
    direct_component_labels: npt.ArrayLike,
    measurement_component_labels: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.int64],
    npt.NDArray[np.int64],
    npt.NDArray[np.bool_],
]:
    """Return aligned component planes with exact parent ownership."""
    normalized = np.asarray(normalized_residual, dtype=np.float64)
    direct = np.asarray(direct_component_labels)
    measurement = np.asarray(measurement_component_labels)
    valid = np.asarray(valid_pixels)
    if (
        normalized.ndim != _IMAGE_DIMENSIONS
        or direct.ndim != _IMAGE_DIMENSIONS
        or measurement.ndim != _IMAGE_DIMENSIONS
        or valid.ndim != _IMAGE_DIMENSIONS
        or direct.shape != normalized.shape
        or measurement.shape != normalized.shape
        or valid.shape != normalized.shape
    ):
        raise ValueError("component topology planes must be aligned and 2-D")
    if not np.issubdtype(direct.dtype, np.integer) or not np.issubdtype(
        measurement.dtype,
        np.integer,
    ):
        raise TypeError("component topology labels must be integer planes")
    if valid.dtype != np.bool_:
        raise TypeError("component topology validity must be boolean")
    direct = np.asarray(direct, dtype=np.int64)
    measurement = np.asarray(measurement, dtype=np.int64)
    if np.any(direct < 0) or np.any(measurement < 0):
        raise ValueError("component topology labels must be non-negative")
    direct_support = direct > 0
    measurement_support = measurement > 0
    if np.any(direct_support & ~measurement_support) or np.any(
        direct_support & (direct != measurement)
    ):
        raise ValueError(
            "direct component ownership must be an exact subset of "
            "measurement ownership"
        )
    if set(np.unique(direct[direct_support])) != set(
        np.unique(measurement[measurement_support])
    ):
        raise ValueError("direct and measurement parent identities must match")
    if np.any(measurement_support & ~valid):
        raise ValueError("component measurement ownership must be valid")
    if not np.all(np.isfinite(normalized[direct_support])):
        raise ValueError("direct component residuals must be finite")
    return normalized, direct, measurement, valid


def _parent_records(
    labels: npt.NDArray[np.int64],
) -> tuple[tuple[int, ImageBounds, tuple[slice, slice], tuple[int, int]], ...]:
    """Return bounded parent records ordered by global first pixel."""
    positive_labels = np.unique(labels[labels > 0])
    if positive_labels.size == 0:
        return ()
    ranked = np.zeros(labels.shape, dtype=np.int32)
    positive = labels > 0
    ranked[positive] = np.asarray(
        np.searchsorted(positive_labels, labels[positive]) + 1,
        dtype=np.int32,
    )
    records: list[
        tuple[int, ImageBounds, tuple[slice, slice], tuple[int, int]]
    ] = []
    object_slices = cast(
        list[tuple[slice, slice] | None],
        find_objects(ranked),
    )
    for label, slices in zip(
        positive_labels,
        object_slices,
        strict=True,
    ):
        if slices is None:  # pragma: no cover - dense ranks are exhaustive
            raise ValueError("component topology parent bounds are absent")
        y_slice, x_slice = slices
        if any(
            value is None
            for value in (
                y_slice.start,
                y_slice.stop,
                x_slice.start,
                x_slice.stop,
            )
        ):  # pragma: no cover - SciPy returns concrete object bounds
            raise ValueError("component topology parent bounds are incomplete")
        assert y_slice.start is not None
        assert y_slice.stop is not None
        assert x_slice.start is not None
        assert x_slice.stop is not None
        bounds = ImageBounds(
            int(y_slice.start),
            int(y_slice.stop),
            int(x_slice.start),
            int(x_slice.stop),
        )
        membership = labels[slices] == label
        first_local = np.argwhere(membership)[0]
        first = (
            bounds.y_start + int(first_local[0]),
            bounds.x_start + int(first_local[1]),
        )
        records.append((int(label), bounds, slices, first))
    return tuple(sorted(records, key=lambda item: item[3]))


def _assign_parent_measurement_support(
    direct_labels: npt.NDArray[np.int32],
    measurement_support: npt.NDArray[np.bool_],
    valid_pixels: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Partition one parent's complete support among deblended seeds."""
    height, width = direct_labels.shape
    assigned = assign_seeded_multiscale_support(
        direct_labels,
        measurement_support,
        valid_pixels,
        beam_major_fwhm_pixels=1.0,
        recovery_radius_beams=hypot(height, width) + 1.0,
    )
    if not np.array_equal(assigned > 0, measurement_support):
        raise ValueError(
            "measurement parent support must remain connected to a direct "
            "component seed"
        )
    return assigned


def deblend_component_topology(
    normalized_residual: npt.ArrayLike,
    direct_component_labels: npt.ArrayLike,
    measurement_component_labels: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    config: CompactDeblendConfig,
) -> DeblendedComponentTopology:
    """Deblend admitted parents while preserving their complete support.

    Direct connected islands remain the parent/support topology. Within each
    admitted parent, the reviewed compact watershed defines Gaussian-component
    ownership. Measurement pixels keep their original parent membership and
    are assigned to the nearest new direct seed with canonical tie-breaking.
    Parents above either hard compact-work bound remain one explicit deferred
    component; this bounded helper never drops their science.
    """
    normalized, direct, measurement, valid = _validated_inputs(
        normalized_residual,
        direct_component_labels,
        measurement_component_labels,
        valid_pixels,
    )
    output_direct = np.zeros(direct.shape, dtype=np.int32)
    output_measurement = np.zeros(measurement.shape, dtype=np.int32)
    next_label = 1
    deblended_parent_count = 0
    deferred_parent_count = 0
    image_height, image_width = direct.shape
    measurement_records = {
        label: (bounds, slices)
        for label, bounds, slices, _ in _parent_records(measurement)
    }
    for parent_label, bounds, slices, first_pixel in _parent_records(direct):
        measurement_bounds, measurement_slices = measurement_records[
            parent_label
        ]
        local_direct = direct[slices] == parent_label
        local_measurement = measurement[measurement_slices] == parent_label
        bounds_pixels = bounds.shape_yx[0] * bounds.shape_yx[1]
        direct_pixels = int(np.count_nonzero(local_direct))
        if (
            direct_pixels > config.maximum_compact_island_pixels
            or bounds_pixels > config.maximum_compact_bounds_pixels
        ):
            direct_output = output_direct[slices]
            direct_output[local_direct] = next_label
            measurement_output = output_measurement[measurement_slices]
            measurement_output[local_measurement] = next_label
            next_label += 1
            deferred_parent_count += 1
            continue
        local_normalized = normalized[slices]
        peak_linear = int(
            np.argmax(np.where(local_direct, local_normalized, -np.inf))
        )
        peak_local = np.unravel_index(peak_linear, local_direct.shape)
        result = deblend_compact_island(
            CompactIslandPixels(
                island=DetectedIsland(
                    island_id=f"component-parent-{parent_label:08d}",
                    global_label=parent_label,
                    pixel_count=direct_pixels,
                    bounds=bounds,
                    peak_signal_to_noise=float(local_normalized[peak_local]),
                    peak_position_yx=(
                        bounds.y_start + int(peak_local[0]),
                        bounds.x_start + int(peak_local[1]),
                    ),
                    first_pixel_yx=first_pixel,
                    touches_image_edge=(
                        bounds.y_start == 0
                        or bounds.x_start == 0
                        or bounds.y_stop == image_height
                        or bounds.x_stop == image_width
                    ),
                ),
                normalized_residual=local_normalized,
                island_membership=local_direct,
            ),
            config,
            marker_partition="nearest-marker",
        )
        local_labels = np.where(
            result.region_labels > 0,
            result.region_labels + next_label - 1,
            0,
        ).astype(np.int32, copy=False)
        output_direct[slices] += local_labels
        if len(result.regions) == 1:
            measurement_output = output_measurement[measurement_slices]
            measurement_output[local_measurement] = next_label
        else:
            measurement_seed_labels = np.zeros(
                measurement_bounds.shape_yx,
                dtype=np.int32,
            )
            seed_slices = (
                slice(
                    bounds.y_start - measurement_bounds.y_start,
                    bounds.y_stop - measurement_bounds.y_start,
                ),
                slice(
                    bounds.x_start - measurement_bounds.x_start,
                    bounds.x_stop - measurement_bounds.x_start,
                ),
            )
            measurement_seed_labels[seed_slices] = local_labels
            assigned = _assign_parent_measurement_support(
                measurement_seed_labels,
                local_measurement,
                valid[measurement_slices],
            )
            output_measurement[measurement_slices] += assigned
            deblended_parent_count += 1
        next_label += len(result.regions)
    if not np.array_equal(output_direct > 0, direct > 0):
        raise ValueError("component deblending changed direct support")
    if not np.array_equal(output_measurement > 0, measurement > 0):
        raise ValueError("component deblending changed measurement support")
    output_identities = set(np.unique(output_direct[output_direct > 0]))
    if output_identities != set(
        np.unique(output_measurement[output_measurement > 0])
    ):
        raise ValueError("deblended component identities are inconsistent")
    output_direct.setflags(write=False)
    output_measurement.setflags(write=False)
    return DeblendedComponentTopology(
        direct_component_labels=output_direct,
        measurement_component_labels=output_measurement,
        deblended_parent_count=deblended_parent_count,
        deferred_parent_count=deferred_parent_count,
    )
