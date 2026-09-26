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


@dataclass(frozen=True, slots=True)
class ParentComponentMembership:
    """One parent's deblended components, in that parent's own windows.

    The labels are local to the parent, numbered from one in the order the
    reviewed watershed produced them. A caller that deblends one parent per
    task offsets them by the components every earlier parent produced, which
    is what :func:`deblend_component_topology` does in one pass.
    """

    component_count: int
    direct_labels: npt.NDArray[np.int32]
    measurement_labels: npt.NDArray[np.int32]
    deblended: bool
    deferred: bool


def _one_parent_component(
    direct_membership: npt.NDArray[np.bool_],
    measurement_membership: npt.NDArray[np.bool_],
    *,
    direct_bounds: ImageBounds,
    measurement_labels: npt.NDArray[np.int32],
    deferred: bool,
) -> ParentComponentMembership:
    """Publish one admitted parent unchanged as a single component."""
    direct_labels = np.zeros(direct_bounds.shape_yx, dtype=np.int32)
    direct_labels[direct_membership] = 1
    measurement_labels[measurement_membership] = 1
    return ParentComponentMembership(
        component_count=1,
        direct_labels=direct_labels,
        measurement_labels=measurement_labels,
        deblended=False,
        deferred=deferred,
    )


def parent_is_deferred(
    direct_bounds: ImageBounds,
    direct_pixel_count: int,
    config: CompactDeblendConfig,
) -> bool:
    """Return whether a parent passes either hard compact-work bound.

    Such a parent stays one explicit deferred component. That decision needs
    only the parent's bounds and size, and publishing it needs none of its
    pixels, so no task has to read a deferred parent's window.

    Examples:
        >>> bounds = CompactDeblendConfig(5.0, 2, 1.0, 7, 100, 250, 250, 250)
        >>> parent_is_deferred(ImageBounds(0, 10, 0, 10), 60, bounds)
        False
        >>> parent_is_deferred(ImageBounds(0, 3, 0, 90), 60, bounds)
        True
        >>> parent_is_deferred(ImageBounds(0, 10, 0, 10), 101, bounds)
        True
    """
    height, width = direct_bounds.shape_yx
    return (
        direct_pixel_count > config.maximum_compact_island_pixels
        or height * width > config.maximum_compact_bounds_pixels
    )


def deblend_parent_components(  # noqa: PLR0913
    normalized_window: npt.NDArray[np.float64],
    direct_membership: npt.NDArray[np.bool_],
    measurement_membership: npt.NDArray[np.bool_],
    valid_window: npt.NDArray[np.bool_],
    *,
    parent_label: int,
    direct_bounds: ImageBounds,
    measurement_bounds: ImageBounds,
    image_shape_yx: tuple[int, int],
    first_pixel_yx: tuple[int, int],
    config: CompactDeblendConfig,
) -> ParentComponentMembership:
    """Deblend one admitted parent inside the windows that hold it.

    Every decision needs the parent's complete support and nothing beyond it,
    so one task can evaluate one parent exactly. A parent above either hard
    compact-work bound stays one explicit deferred component rather than
    losing its science, and so does a parent whose peak never reaches the
    detection threshold.
    """
    image_height, image_width = image_shape_yx
    measurement_labels = np.zeros(
        measurement_bounds.shape_yx,
        dtype=np.int32,
    )
    direct_pixels = int(np.count_nonzero(direct_membership))
    if parent_is_deferred(direct_bounds, direct_pixels, config):
        return _one_parent_component(
            direct_membership,
            measurement_membership,
            direct_bounds=direct_bounds,
            measurement_labels=measurement_labels,
            deferred=True,
        )
    peak_linear = int(
        np.argmax(np.where(direct_membership, normalized_window, -np.inf))
    )
    peak_local = np.unravel_index(peak_linear, direct_membership.shape)
    if (
        float(normalized_window[peak_local])
        <= config.minimum_peak_signal_to_noise
    ):
        return _one_parent_component(
            direct_membership,
            measurement_membership,
            direct_bounds=direct_bounds,
            measurement_labels=measurement_labels,
            deferred=False,
        )
    result = deblend_compact_island(
        CompactIslandPixels(
            island=DetectedIsland(
                island_id=f"component-parent-{parent_label:08d}",
                global_label=parent_label,
                pixel_count=direct_pixels,
                bounds=direct_bounds,
                peak_signal_to_noise=float(normalized_window[peak_local]),
                peak_position_yx=(
                    direct_bounds.y_start + int(peak_local[0]),
                    direct_bounds.x_start + int(peak_local[1]),
                ),
                first_pixel_yx=first_pixel_yx,
                touches_image_edge=(
                    direct_bounds.y_start == 0
                    or direct_bounds.x_start == 0
                    or direct_bounds.y_stop == image_height
                    or direct_bounds.x_stop == image_width
                ),
            ),
            normalized_residual=normalized_window,
            island_membership=direct_membership,
        ),
        config,
        marker_partition="nearest-marker",
    )
    direct_labels = np.asarray(result.region_labels, dtype=np.int32)
    if len(result.regions) == 1:
        measurement_labels[measurement_membership] = 1
        return ParentComponentMembership(
            component_count=1,
            direct_labels=direct_labels,
            measurement_labels=measurement_labels,
            deblended=False,
            deferred=False,
        )
    seed_labels = np.zeros(measurement_bounds.shape_yx, dtype=np.int32)
    seed_labels[
        slice(
            direct_bounds.y_start - measurement_bounds.y_start,
            direct_bounds.y_stop - measurement_bounds.y_start,
        ),
        slice(
            direct_bounds.x_start - measurement_bounds.x_start,
            direct_bounds.x_stop - measurement_bounds.x_start,
        ),
    ] = direct_labels
    measurement_labels += _assign_parent_measurement_support(
        seed_labels,
        measurement_membership,
        valid_window,
    )
    return ParentComponentMembership(
        component_count=len(result.regions),
        direct_labels=direct_labels,
        measurement_labels=measurement_labels,
        deblended=True,
        deferred=False,
    )


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
    measurement_records = {
        label: (bounds, slices)
        for label, bounds, slices, _ in _parent_records(measurement)
    }
    for parent_label, bounds, slices, first_pixel in _parent_records(direct):
        measurement_bounds, measurement_slices = measurement_records[
            parent_label
        ]
        membership = deblend_parent_components(
            normalized[slices],
            direct[slices] == parent_label,
            measurement[measurement_slices] == parent_label,
            valid[measurement_slices],
            parent_label=parent_label,
            direct_bounds=bounds,
            measurement_bounds=measurement_bounds,
            image_shape_yx=direct.shape,
            first_pixel_yx=first_pixel,
            config=config,
        )
        output_direct[slices] += np.where(
            membership.direct_labels > 0,
            membership.direct_labels + next_label - 1,
            0,
        ).astype(np.int32, copy=False)
        output_measurement[measurement_slices] += np.where(
            membership.measurement_labels > 0,
            membership.measurement_labels + next_label - 1,
            0,
        ).astype(np.int32, copy=False)
        next_label += membership.component_count
        deblended_parent_count += int(membership.deblended)
        deferred_parent_count += int(membership.deferred)
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
