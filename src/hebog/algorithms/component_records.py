# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Stable records of the detection components sources are built from."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from math import isfinite

import numpy as np
import numpy.typing as npt

from hebog.algorithms.label_groups import label_windows
from hebog.data_models.source_association import (
    DetectionComponentRecord,
)

_COMPONENT_NAMESPACE = b"phase-5-detection-component-v1\0"
_IMAGE_DIMENSIONS = 2
_MINIMUM_SHAPE_PIXELS = 3


def stable_id(namespace: bytes, prefix: str, values: tuple[str, ...]) -> str:
    """Hash canonical identity fields into one stable domain identifier."""
    digest = sha256(namespace)
    for value in values:
        digest.update(value.encode("ascii"))
        digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()}"


def _component_id(canonical_pixel_yx: tuple[int, int]) -> str:
    """Derive identity from the component's global canonical owner pixel."""
    return stable_id(
        _COMPONENT_NAMESPACE,
        "component-detection",
        tuple(str(value) for value in canonical_pixel_yx),
    )


def validated_component_planes(
    component_labels: npt.ArrayLike,
    association_signal: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.int64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
]:
    """Return aligned component, signal, and validity planes."""
    label_values = np.asarray(component_labels)
    signal_values = np.asarray(association_signal)
    valid = np.asarray(valid_pixels)
    if (
        label_values.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(label_values.dtype, np.integer)
        or bool(np.any(label_values < 0))
    ):
        raise ValueError(
            "component labels must be a non-negative integer plane"
        )
    if (
        signal_values.ndim != _IMAGE_DIMENSIONS
        or signal_values.shape != label_values.shape
        or not np.issubdtype(signal_values.dtype, np.number)
        or np.iscomplexobj(signal_values)
    ):
        raise ValueError("association signal must be one aligned real plane")
    if (
        valid.ndim != _IMAGE_DIMENSIONS
        or valid.shape != label_values.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError("valid pixels must be one aligned boolean plane")
    if bool(np.any((label_values > 0) & ~valid)):
        raise ValueError("component owner pixels must be scientifically valid")
    return (
        np.asarray(label_values, dtype=np.int64),
        np.asarray(signal_values, dtype=np.float64),
        np.asarray(valid, dtype=np.bool_),
    )


def _positive_moment_geometry(
    y_pixels: npt.NDArray[np.int64],
    x_pixels: npt.NDArray[np.int64],
    signal: npt.NDArray[np.float64],
) -> tuple[
    tuple[float, float],
    tuple[tuple[float, float], tuple[float, float]] | None,
]:
    """Return positive-signal centroid and exact-support covariance.

    The arrays hold one component's support pixels in raster order, with
    global coordinates, so the geometry depends on where the component lies
    in the image and not on the plane, window or cores it was read from.
    """
    positive = np.isfinite(signal) & (signal > 0.0)
    if not bool(np.any(positive)):
        return (float(np.mean(y_pixels)), float(np.mean(x_pixels))), None
    weights = signal[positive]
    weight = float(np.sum(weights, dtype=np.float64))
    y_positive = y_pixels[positive]
    x_positive = x_pixels[positive]
    centroid_y = float(np.sum(y_positive * weights, dtype=np.float64) / weight)
    centroid_x = float(np.sum(x_positive * weights, dtype=np.float64) / weight)
    centroid = (centroid_y, centroid_x)
    if weights.size < _MINIMUM_SHAPE_PIXELS:
        return centroid, None
    delta_y = y_positive - centroid_y
    delta_x = x_positive - centroid_x
    yy = float(np.sum(weights * delta_y * delta_y) / weight)
    yx = float(np.sum(weights * delta_y * delta_x) / weight)
    xx = float(np.sum(weights * delta_x * delta_x) / weight)
    if (
        not all(isfinite(value) for value in (yy, yx, xx))
        or yy <= 0.0
        or xx <= 0.0
        or yy * xx - yx * yx <= 0.0
    ):
        return centroid, None
    return centroid, ((yy, yx), (yx, xx))


def _component_record(
    label_value: int,
    y_pixels: npt.NDArray[np.int64],
    x_pixels: npt.NDArray[np.int64],
    signal: npt.NDArray[np.float64],
    *,
    canonical_reference_yx: tuple[int, int] | None,
) -> DetectionComponentRecord:
    """Describe one component from its support pixels, in raster order.

    Without a caller's canonical reference, the component is named by its
    first pixel, which raster order makes the same pixel wherever it is read.
    """
    reference = (
        (int(y_pixels[0]), int(x_pixels[0]))
        if canonical_reference_yx is None
        else canonical_reference_yx
    )
    if min(reference) < 0:
        raise ValueError("canonical component references must be positive")
    centroid, covariance = _positive_moment_geometry(
        y_pixels, x_pixels, signal
    )
    return DetectionComponentRecord(
        component_id=_component_id(reference),
        label_value=label_value,
        canonical_pixel_yx=reference,
        centroid_yx=centroid,
        covariance_pixels_squared=covariance,
    )


def build_detection_component_records(
    component_labels: npt.ArrayLike,
    association_signal: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    origin_yx: tuple[int, int] = (0, 0),
    canonical_component_references_yx: (
        Mapping[int, tuple[int, int]] | None
    ) = None,
) -> tuple[DetectionComponentRecord, ...]:
    """Build stable component records from immutable exact owner support."""
    if len(origin_yx) != _IMAGE_DIMENSIONS or min(origin_yx) < 0:
        raise ValueError("component origin must contain non-negative y-x")
    labels, signal, valid = validated_component_planes(
        component_labels,
        association_signal,
        valid_pixels,
    )
    records: list[DetectionComponentRecord] = []
    # One pass gives every component its window, so the geometry below
    # costs each component's own pixels instead of the whole plane.
    component_windows = label_windows(labels)
    for label_value in sorted(
        int(value) for value in np.unique(labels) if value > 0
    ):
        crop = component_windows[label_value - 1]
        if crop is None:
            raise ValueError("component labels must own at least one pixel")
        support = (labels[crop] == label_value) & valid[crop]
        local_y, local_x = np.nonzero(support)
        records.append(
            _component_record(
                label_value,
                local_y + (origin_yx[0] + crop[0].start),
                local_x + (origin_yx[1] + crop[1].start),
                signal[crop][support],
                canonical_reference_yx=(
                    None
                    if canonical_component_references_yx is None
                    else canonical_component_references_yx.get(label_value)
                ),
            )
        )
    return tuple(sorted(records, key=lambda item: item.canonical_pixel_yx))


def build_detection_component_record(
    label_value: int,
    raster_indices: npt.NDArray[np.int64],
    association_signal: npt.NDArray[np.float64],
    *,
    image_width: int,
) -> DetectionComponentRecord:
    """Describe one component from its own valid support pixels.

    ``raster_indices`` are global ``y * image_width + x`` positions in
    ascending raster order, and ``association_signal`` is aligned with them.
    A component too wide to read at once arrives as pixels from each core
    that holds it; restored to raster order, they are exactly the pixels a
    window over it presents, so this is the record
    :func:`build_detection_component_records` builds there, bit for bit.

    Raises:
        ValueError: If the component has no pixel, the arrays disagree, or
            the pixels are not in strictly ascending raster order.
    """
    indices = np.asarray(raster_indices, dtype=np.int64)
    signal = np.asarray(association_signal, dtype=np.float64)
    if indices.ndim != 1 or indices.shape != signal.shape or not indices.size:
        raise ValueError(
            "component pixels must be non-empty and aligned with their signal"
        )
    if bool(np.any(np.diff(indices) <= 0)):
        raise ValueError("component pixels must be in ascending raster order")
    y_pixels, x_pixels = np.divmod(indices, image_width)
    return _component_record(
        label_value,
        y_pixels,
        x_pixels,
        signal,
        canonical_reference_yx=None,
    )
