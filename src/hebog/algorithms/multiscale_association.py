"""Deterministic bounded association of exact multiscale supports."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise

import numpy as np
import numpy.typing as npt

from hebog.data_models.multiscale import (
    CrossScaleAssociation,
    ScaleDetection,
)

_ASSOCIATION_ID_NAMESPACE = b"phase-5-cross-scale-association-v1\0"
_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class ScaleDetectionPlane:
    """One bounded exact-support label plane and its local label records.

    ``detections[index - 1]`` describes pixels labelled ``index``. Labels are
    deliberately local and may change with partition or task order; stable
    detection identities determine every published association.
    """

    scale_order: int
    component_labels: npt.NDArray[np.int32]
    detections: tuple[ScaleDetection, ...]
    origin_yx: tuple[int, int] = (0, 0)

    def __post_init__(self) -> None:
        """Copy the bounded labels into immutable canonical storage."""
        if self.scale_order < 1:
            raise ValueError("scale order must be positive")
        labels = np.asarray(self.component_labels)
        if labels.ndim != _IMAGE_DIMENSIONS:
            raise ValueError("scale component labels must be two-dimensional")
        if not np.issubdtype(labels.dtype, np.integer):
            raise ValueError("scale component labels must be integers")
        if min(self.origin_yx) < 0:
            raise ValueError("scale component origin must be non-negative")
        if bool(np.any(labels < 0)):
            raise ValueError("scale component labels must be non-negative")
        if int(np.max(labels, initial=0)) > np.iinfo(np.int32).max:
            raise ValueError("scale component labels must fit signed 32-bit")
        canonical = np.asarray(labels, dtype=np.int32).copy()
        canonical.setflags(write=False)
        object.__setattr__(self, "component_labels", canonical)


def _label_bounds(
    labels: npt.NDArray[np.int32],
    *,
    label_count: int,
    origin_yx: tuple[int, int],
) -> tuple[tuple[int, int, int, int], ...]:
    """Return global half-open bounds through one vectorized label scan."""
    y_pixels, x_pixels = np.nonzero(labels)
    label_values = labels[y_pixels, x_pixels]
    y_minimum = np.full(label_count + 1, labels.shape[0], dtype=np.int64)
    y_maximum = np.full(label_count + 1, -1, dtype=np.int64)
    x_minimum = np.full(label_count + 1, labels.shape[1], dtype=np.int64)
    x_maximum = np.full(label_count + 1, -1, dtype=np.int64)
    np.minimum.at(y_minimum, label_values, y_pixels)
    np.maximum.at(y_maximum, label_values, y_pixels)
    np.minimum.at(x_minimum, label_values, x_pixels)
    np.maximum.at(x_maximum, label_values, x_pixels)
    y_origin, x_origin = origin_yx
    return tuple(
        (
            int(y_minimum[label_value]) + y_origin,
            int(y_maximum[label_value]) + y_origin + 1,
            int(x_minimum[label_value]) + x_origin,
            int(x_maximum[label_value]) + x_origin + 1,
        )
        for label_value in range(1, label_count + 1)
    )


def _validate_plane(plane: ScaleDetectionPlane) -> None:
    """Require exact local labels to agree with stable detection metadata."""
    labels = plane.component_labels
    maximum_label = int(np.max(labels, initial=0))
    if maximum_label != len(plane.detections):
        raise ValueError(
            "scale component labels must cover every detection exactly once"
        )
    counts = np.bincount(
        labels.ravel(),
        minlength=len(plane.detections) + 1,
    )
    bounds = _label_bounds(
        labels,
        label_count=len(plane.detections),
        origin_yx=plane.origin_yx,
    )
    y_origin, x_origin = plane.origin_yx
    for label_value, (detection, observed_bounds) in enumerate(
        zip(plane.detections, bounds, strict=True),
        start=1,
    ):
        if detection.scale_order != plane.scale_order:
            raise ValueError("detection scale order must match its plane")
        if int(counts[label_value]) != detection.support_pixel_count:
            raise ValueError(
                "detection support pixel count must match exact labels"
            )
        if observed_bounds != detection.bounds_yx:
            raise ValueError("detection bounds must match exact labels")
        y_pixel, x_pixel = detection.canonical_pixel_yx
        local_pixel = (y_pixel - y_origin, x_pixel - x_origin)
        if (
            min(local_pixel) < 0
            or local_pixel[0] >= labels.shape[0]
            or local_pixel[1] >= labels.shape[1]
            or labels[local_pixel] != label_value
        ):
            raise ValueError(
                "detection canonical pixel must belong to its exact support"
            )


def _representative_key(detection: ScaleDetection) -> tuple[object, ...]:
    """Return the reviewed science-first deterministic selection order."""
    return (
        -detection.peak_signal_to_noise,
        -detection.peak_response_jy_per_beam,
        -detection.valid_support_fraction,
        detection.scale_order,
        detection.canonical_pixel_yx,
        detection.detection_id,
    )


def _association_id(detection_ids: tuple[str, ...]) -> str:
    """Derive a stable identity from canonical contributing identities."""
    digest = sha256()
    digest.update(_ASSOCIATION_ID_NAMESPACE)
    for detection_id in detection_ids:
        digest.update(detection_id.encode("ascii"))
        digest.update(b"\0")
    return f"scale-association-{digest.hexdigest()}"


class _DisjointDetections:
    """Small deterministic union-find over bounded detection identities."""

    def __init__(self, detection_ids: tuple[str, ...]) -> None:
        self._parent = {
            detection_id: detection_id for detection_id in detection_ids
        }

    def find(self, detection_id: str) -> str:
        """Return and compress the canonical component root."""
        while self._parent[detection_id] != detection_id:
            self._parent[detection_id] = self._parent[
                self._parent[detection_id]
            ]
            detection_id = self._parent[detection_id]
        return detection_id

    def union(self, first_id: str, second_id: str) -> None:
        """Join two components under the lexically lower stable root."""
        first_root = self.find(first_id)
        second_root = self.find(second_id)
        if first_root != second_root:
            lower, upper = sorted((first_root, second_root))
            self._parent[upper] = lower

    def groups(self) -> tuple[tuple[str, ...], ...]:
        """Return canonical connected identity groups."""
        grouped_ids: dict[str, list[str]] = {}
        for detection_id in sorted(self._parent):
            grouped_ids.setdefault(self.find(detection_id), []).append(
                detection_id
            )
        return tuple(tuple(items) for items in grouped_ids.values())


def _validated_inputs(
    planes: tuple[ScaleDetectionPlane, ...],
) -> tuple[
    tuple[ScaleDetectionPlane, ...],
    dict[str, ScaleDetection],
]:
    """Validate aligned bounded planes and collect unique stable records."""
    ordered_planes = tuple(sorted(planes, key=lambda item: item.scale_order))
    scale_orders = tuple(item.scale_order for item in ordered_planes)
    if len(set(scale_orders)) != len(scale_orders):
        raise ValueError("scale detection plane orders must be unique")
    shape = ordered_planes[0].component_labels.shape
    origin = ordered_planes[0].origin_yx
    if any(item.component_labels.shape != shape for item in ordered_planes):
        raise ValueError("scale detection planes must have the same shape")
    if any(item.origin_yx != origin for item in ordered_planes):
        raise ValueError("scale detection planes must have the same origin")

    detections_by_id: dict[str, ScaleDetection] = {}
    for plane in ordered_planes:
        _validate_plane(plane)
        for detection in plane.detections:
            if detection.detection_id in detections_by_id:
                raise ValueError("detection IDs must be unique across scales")
            detections_by_id[detection.detection_id] = detection
    return ordered_planes, detections_by_id


def _join_adjacent_overlaps(
    planes: tuple[ScaleDetectionPlane, ...],
    components: _DisjointDetections,
) -> None:
    """Add vectorized exact-support edges between adjacent scale planes."""
    for first, second in pairwise(planes):
        if second.scale_order != first.scale_order + 1:
            continue
        first_labels = first.component_labels
        second_labels = second.component_labels
        overlap = (first_labels > 0) & (second_labels > 0)
        if not bool(np.any(overlap)):
            continue
        label_pairs = np.unique(
            np.column_stack((first_labels[overlap], second_labels[overlap])),
            axis=0,
        )
        for first_label, second_label in label_pairs:
            components.union(
                first.detections[int(first_label) - 1].detection_id,
                second.detections[int(second_label) - 1].detection_id,
            )


def _build_association(
    detection_ids: tuple[str, ...],
    detections_by_id: dict[str, ScaleDetection],
) -> CrossScaleAssociation:
    """Build one immutable association from a connected identity group."""
    detections = tuple(
        detections_by_id[detection_id] for detection_id in detection_ids
    )
    selected = min(detections, key=_representative_key)
    return CrossScaleAssociation(
        association_id=_association_id(detection_ids),
        scale_detection_ids=detection_ids,
        compact_source_ids=(),
        selected_scale_detection_id=selected.detection_id,
        contributing_scale_orders=tuple(
            sorted({detection.scale_order for detection in detections})
        ),
        relationship="extended-only",
    )


def associate_adjacent_scale_detections(
    planes: tuple[ScaleDetectionPlane, ...],
) -> tuple[CrossScaleAssociation, ...]:
    """Associate exact supports only across adjacent configured scales.

    The kernel operates on bounded label planes. It creates vectorized overlap
    edges between adjacent scales and reduces their connected components to
    stable associations. Same-scale fragments can therefore join only through
    an accepted adjacent-scale path. Compact context is a later Step 4 stage.
    """
    if not planes:
        return ()
    ordered_planes, detections_by_id = _validated_inputs(planes)
    if not detections_by_id:
        return ()
    components = _DisjointDetections(tuple(detections_by_id))
    _join_adjacent_overlaps(ordered_planes, components)
    associations = tuple(
        _build_association(detection_ids, detections_by_id)
        for detection_ids in components.groups()
    )
    return tuple(sorted(associations, key=lambda item: item.association_id))
