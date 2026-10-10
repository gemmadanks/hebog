# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Deterministic bounded association of exact multiscale supports."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as connected_component_labels

from hebog.algorithms.label_groups import (
    LabelledPixelGroups,
    group_labelled_pixels,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.multiscale import (
    CrossScaleAssociation,
    ScaleDetection,
)

_ASSOCIATION_ID_NAMESPACE = b"phase-5-cross-scale-association-v1\0"
_DETECTION_ID_NAMESPACE = b"phase-5-scale-detection-v1\0"
_IMAGE_DIMENSIONS = 2
_MINIMUM_PERSISTENT_SCALE_COUNT = 2


def persistent_seeded_scale_support(  # noqa: PLR0913
    scale_snrs: tuple[npt.NDArray[np.float64], ...],
    scale_responses: tuple[npt.NDArray[np.float64], ...],
    valid: npt.NDArray[np.bool_],
    *,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
) -> npt.NDArray[np.bool_]:
    """Apply one seeded adjacent-scale rule to non-publication support.

    Callers pair each noise-calibrated SNR with the same beam-aware filtered
    response in Jy/beam, not the unfiltered residual. Source-protected
    statistics and source-owned photometry can reuse this support without
    admitting new catalogue detections or changing a published mask.
    """
    planes: list[ScaleDetectionPlane] = []
    for order, (snr, response) in enumerate(
        zip(scale_snrs, scale_responses, strict=True), start=1
    ):
        labels, count = cast(
            tuple[npt.NDArray[np.int32], int],
            connected_component_labels(
                valid & (snr >= island_sigma), np.ones((3, 3))
            ),
        )
        sizes = np.bincount(labels.ravel(), minlength=count + 1)
        seeded = np.unique(labels[valid & (snr >= detection_sigma)])
        accepted = np.zeros(count + 1, dtype=np.bool_)
        accepted[seeded] = sizes[seeded] >= minimum_pixels
        accepted[0] = False
        planes.append(
            build_scale_detection_plane(
                accepted[labels],
                response,
                snr,
                valid,
                scale_order=order,
                nominal_scale_beam_fwhm=float(2 ** (order - 1)),
            )
        )
    return persistent_adjacent_scale_support(tuple(planes))


class ScaleDetections(Protocol):
    """One scale's stable feature records, with or without its labels.

    Every hierarchy decision reads identities, bounds and responses, never
    the label plane, so a pass that has already reconciled its features can
    supply :class:`ScaleDetectionRecords` and hold no image-sized array.
    """

    @property
    def scale_order(self) -> int:
        """Return the configured scale these features belong to."""
        ...

    @property
    def detections(self) -> tuple[ScaleDetection, ...]:
        """Return the features, ordered by their canonical first pixel."""
        ...


@dataclass(frozen=True, slots=True)
class ScaleDetectionRecords:
    """One scale's features, without the plane that labelled them."""

    scale_order: int
    detections: tuple[ScaleDetection, ...]

    def __post_init__(self) -> None:
        """Reject an unconfigured scale before any decision reads it."""
        if self.scale_order < 1:
            raise ValueError("scale order must be positive")


def scale_detections_from_islands(
    islands: tuple[DetectedIsland, ...],
    *,
    scale_order: int,
    nominal_scale_beam_fwhm: float,
) -> ScaleDetectionRecords:
    """Describe one scale's features from its reconciled islands alone.

    A tiled pass reduces each feature's extent, canonical pixel and peak
    response while its filter response is still in the task's memory, so a
    later pass names the same features without labelling a plane again.
    """
    return ScaleDetectionRecords(
        scale_order=scale_order,
        detections=tuple(
            ScaleDetection(
                detection_id=scale_detection_id(
                    scale_order, island.first_pixel_yx
                ),
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=nominal_scale_beam_fwhm,
                support_pixel_count=island.pixel_count,
                valid_support_fraction=1.0,
                bounds_yx=(
                    island.bounds.y_start,
                    island.bounds.y_stop,
                    island.bounds.x_start,
                    island.bounds.x_stop,
                ),
                canonical_pixel_yx=island.first_pixel_yx,
                peak_response_jy_per_beam=_island_peak_response(island),
                peak_signal_to_noise=island.peak_signal_to_noise,
                touches_image_edge=island.touches_image_edge,
            )
            for island in islands
        ),
    )


def _island_peak_response(island: DetectedIsland) -> float:
    """Return one island's peak response, or fail closed on its absence."""
    response = island.peak_response_jy_per_beam
    if response is None:
        raise ValueError(
            "scale detection records require a reduced peak response"
        )
    return response


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


def scale_detection_id(
    scale_order: int,
    canonical_pixel_yx: tuple[int, int],
) -> str:
    """Derive one stable feature identity from scale and global owner pixel.

    A later pass names the same features from the reconciled island records
    alone, so this identity is part of the published contract rather than an
    internal detail of the plane builder.
    """
    digest = sha256(_DETECTION_ID_NAMESPACE)
    for value in (scale_order, *canonical_pixel_yx):
        digest.update(str(value).encode("ascii"))
        digest.update(b"\0")
    return f"scale-detection-{digest.hexdigest()}"


def build_scale_detection_plane(  # noqa: PLR0913
    significant_support: npt.ArrayLike,
    response_jy_per_beam: npt.ArrayLike,
    signal_to_noise: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    scale_order: int,
    nominal_scale_beam_fwhm: float,
    origin_yx: tuple[int, int] = (0, 0),
) -> ScaleDetectionPlane:
    """Build stable exact features from one reviewed significant scale mask."""
    support = np.asarray(significant_support)
    response = np.asarray(response_jy_per_beam)
    snr = np.asarray(signal_to_noise)
    valid = np.asarray(valid_pixels)
    if support.ndim != _IMAGE_DIMENSIONS or support.dtype != np.bool_:
        raise ValueError("significant scale support must be a boolean plane")
    if valid.shape != support.shape or valid.dtype != np.bool_:
        raise ValueError("scale validity must be one aligned boolean plane")
    if any(
        array.shape != support.shape
        or not np.issubdtype(array.dtype, np.number)
        or np.iscomplexobj(array)
        for array in (response, snr)
    ):
        raise ValueError("scale response and SNR must be aligned real planes")
    if np.any(support & ~valid):
        raise ValueError("scale support must be scientifically valid")
    if (
        isinstance(scale_order, bool)
        or scale_order < 1
        or not isfinite(nominal_scale_beam_fwhm)
        or nominal_scale_beam_fwhm <= 0.0
        or len(origin_yx) != _IMAGE_DIMENSIONS
        or min(origin_yx) < 0
    ):
        raise ValueError("scale metadata must be positive and canonical")
    labels, count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(
            support,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    groups = group_labelled_pixels(labels, label_count=count)
    feature_response = np.asarray(response, dtype=np.float64).reshape(-1)[
        groups.flat_positions
    ]
    feature_snr = np.asarray(snr, dtype=np.float64).reshape(-1)[
        groups.flat_positions
    ]
    if (
        not bool(np.all(np.isfinite(feature_response)))
        or not bool(np.all(np.isfinite(feature_snr)))
        or bool(np.any(groups.maximum(feature_response) <= 0.0))
    ):
        raise ValueError(
            "significant scale features require finite positive response"
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=np.asarray(labels, dtype=np.int32),
        detections=_scale_detections(
            groups,
            count=count,
            peak_response_jy_per_beam=groups.maximum(feature_response),
            peak_signal_to_noise=groups.maximum(feature_snr),
            support_shape_yx=support.shape,
            origin_yx=origin_yx,
            scale_order=scale_order,
            nominal_scale_beam_fwhm=nominal_scale_beam_fwhm,
        ),
        origin_yx=origin_yx,
    )


def _scale_detections(  # noqa: PLR0913
    groups: LabelledPixelGroups,
    *,
    count: int,
    peak_response_jy_per_beam: npt.NDArray[np.float64],
    peak_signal_to_noise: npt.NDArray[np.float64],
    support_shape_yx: tuple[int, int],
    origin_yx: tuple[int, int],
    scale_order: int,
    nominal_scale_beam_fwhm: float,
) -> tuple[ScaleDetection, ...]:
    """Describe each labelled feature from its reduced pixel group."""
    y_origin, x_origin = origin_yx
    height, width = support_shape_yx
    minimum_y, maximum_y = groups.minimum(groups.y), groups.maximum(groups.y)
    minimum_x, maximum_x = groups.minimum(groups.x), groups.maximum(groups.x)
    canonical_pixels = tuple(
        (
            int(groups.first_y[index]) + y_origin,
            int(groups.first_x[index]) + x_origin,
        )
        for index in range(count)
    )
    return tuple(
        ScaleDetection(
            detection_id=scale_detection_id(scale_order, canonical),
            parent_island_id=None,
            scale_order=scale_order,
            nominal_scale_beam_fwhm=nominal_scale_beam_fwhm,
            support_pixel_count=int(groups.sizes[index]),
            valid_support_fraction=1.0,
            bounds_yx=(
                int(minimum_y[index]) + y_origin,
                int(maximum_y[index]) + y_origin + 1,
                int(minimum_x[index]) + x_origin,
                int(maximum_x[index]) + x_origin + 1,
            ),
            canonical_pixel_yx=canonical,
            peak_response_jy_per_beam=float(peak_response_jy_per_beam[index]),
            peak_signal_to_noise=float(peak_signal_to_noise[index]),
            touches_image_edge=bool(
                minimum_y[index] == 0
                or minimum_x[index] == 0
                or maximum_y[index] == height - 1
                or maximum_x[index] == width - 1
            ),
        )
        for index, canonical in enumerate(canonical_pixels)
    )


def build_scale_detection_plane_from_islands(
    significant_support: npt.ArrayLike,
    islands: tuple[DetectedIsland, ...],
    *,
    scale_order: int,
    nominal_scale_beam_fwhm: float,
) -> ScaleDetectionPlane:
    """Describe one scale from its stored support and reconciled islands.

    A tiled pass reduces each feature's peak response and signal to noise
    while the filter response is still in the task's memory, so a later pass
    can describe the same features from the stored support mask alone. The
    reconciled islands are ordered by their globally row-major canonical
    pixel, which is the order ``scipy.ndimage.label`` assigns to the same
    mask, so the labelling here reproduces the tiled global labels exactly.
    """
    support = np.asarray(significant_support)
    if support.ndim != _IMAGE_DIMENSIONS or support.dtype != np.bool_:
        raise ValueError("significant scale support must be a boolean plane")
    labels, count = cast(
        tuple[npt.NDArray[np.int32], int],
        connected_component_labels(
            support,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    if count != len(islands):
        raise ValueError(
            "reconciled scale islands must describe the stored support once"
        )
    groups = group_labelled_pixels(labels, label_count=count)
    canonical = tuple(
        (int(groups.first_y[index]), int(groups.first_x[index]))
        for index in range(count)
    )
    if any(
        island.global_label != index + 1
        or island.first_pixel_yx != canonical[index]
        or island.pixel_count != int(groups.sizes[index])
        for index, island in enumerate(islands)
    ):
        raise ValueError(
            "reconciled scale islands must match the stored support exactly"
        )
    peak_response = np.asarray(
        [island.peak_response_jy_per_beam for island in islands],
        dtype=np.float64,
    )
    peak_snr = np.asarray(
        [island.peak_signal_to_noise for island in islands],
        dtype=np.float64,
    )
    if (
        not bool(np.all(np.isfinite(peak_response)))
        or not bool(np.all(np.isfinite(peak_snr)))
        or bool(np.any(peak_response <= 0.0))
    ):
        raise ValueError(
            "significant scale features require finite positive response"
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=np.asarray(labels, dtype=np.int32),
        detections=_scale_detections(
            groups,
            count=count,
            peak_response_jy_per_beam=peak_response,
            peak_signal_to_noise=peak_snr,
            support_shape_yx=support.shape,
            origin_yx=(0, 0),
            scale_order=scale_order,
            nominal_scale_beam_fwhm=nominal_scale_beam_fwhm,
        ),
    )


def _label_bounds(
    labels: npt.NDArray[np.int32],
    *,
    label_count: int,
    origin_yx: tuple[int, int],
) -> tuple[tuple[int, int, int, int], ...]:
    """Return global half-open bounds through one vectorized label scan.

    A label without pixels cannot be described, and every caller has already
    required its labels to cover each record exactly once, so an empty
    label raises rather than returning inverted bounds.
    """
    groups = group_labelled_pixels(labels, label_count=label_count)
    minimum_y, maximum_y = groups.minimum(groups.y), groups.maximum(groups.y)
    minimum_x, maximum_x = groups.minimum(groups.x), groups.maximum(groups.x)
    y_origin, x_origin = origin_yx
    return tuple(
        (
            int(minimum_y[index]) + y_origin,
            int(maximum_y[index]) + y_origin + 1,
            int(minimum_x[index]) + x_origin,
            int(maximum_x[index]) + x_origin + 1,
        )
        for index in range(label_count)
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
    for first_id, second_id in adjacent_scale_overlap_edges(planes):
        components.union(first_id, second_id)


def adjacent_scale_overlap_edges(
    planes: tuple[ScaleDetectionPlane, ...],
) -> tuple[tuple[str, str], ...]:
    """Return canonical fine-to-coarse exact-overlap hierarchy edges.

    This is the same bounded overlap evidence used by
    :func:`associate_adjacent_scale_detections`, exposed so a catalogue-source
    hierarchy can retain parent direction without constructing another graph
    implementation.
    """
    if not planes:
        return ()
    ordered_planes, _ = _validated_inputs(planes)
    edges: set[tuple[str, str]] = set()
    for first, second in pairwise(ordered_planes):
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
            edges.add(
                (
                    first.detections[int(first_label) - 1].detection_id,
                    second.detections[int(second_label) - 1].detection_id,
                )
            )
    return tuple(sorted(edges))


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
        selected_scale_detection_id=selected.detection_id,
        contributing_scale_orders=tuple(
            sorted({detection.scale_order for detection in detections})
        ),
    )


def associate_adjacent_scale_detections(
    planes: tuple[ScaleDetectionPlane, ...],
) -> tuple[CrossScaleAssociation, ...]:
    """Associate exact supports only across adjacent configured scales.

    The kernel operates on bounded label planes. It creates vectorized overlap
    edges between adjacent scales and reduces their connected components to
    stable associations. Same-scale fragments can therefore join only through
    an accepted adjacent-scale path.
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


def persistent_adjacent_scale_support(
    planes: tuple[ScaleDetectionPlane, ...],
) -> npt.NDArray[np.bool_]:
    """Return exact support whose features persist across adjacent scales."""
    if not planes:
        raise ValueError("persistent support requires a scale detection plane")
    ordered_planes, _ = _validated_inputs(planes)
    retained = persistent_scale_labels(
        ordered_planes,
        adjacent_scale_overlap_edges(ordered_planes),
    )
    support = np.zeros(
        ordered_planes[0].component_labels.shape,
        dtype=np.bool_,
    )
    for plane in ordered_planes:
        support |= persistent_scale_support_window(
            plane.component_labels,
            retained[plane.scale_order],
        )
    support.setflags(write=False)
    return support


def persistent_scale_labels(
    scales: tuple[ScaleDetections, ...],
    parent_edges: tuple[tuple[str, str], ...],
) -> dict[int, tuple[int, ...]]:
    """Return each scale's labels whose feature persists to a neighbour.

    Persistence is decided from the reduced adjacent-scale overlap edges and
    the feature records alone, so it holds no plane.
    """
    detections_by_id = {
        detection.detection_id: detection
        for scale in scales
        for detection in scale.detections
    }
    components = _DisjointDetections(tuple(detections_by_id))
    for child_id, parent_id in parent_edges:
        components.union(child_id, parent_id)
    persistent_ids = {
        detection_id
        for detection_ids in components.groups()
        for association in (
            _build_association(detection_ids, detections_by_id),
        )
        if (
            len(association.contributing_scale_orders)
            >= _MINIMUM_PERSISTENT_SCALE_COUNT
        )
        for detection_id in association.scale_detection_ids
    }
    return {
        scale.scale_order: tuple(
            index
            for index, detection in enumerate(scale.detections, start=1)
            if detection.detection_id in persistent_ids
        )
        for scale in scales
    }


def persistent_scale_support_window(
    labels: npt.NDArray[np.int32],
    retained_labels: tuple[int, ...],
) -> npt.NDArray[np.bool_]:
    """Return the pixels of one window that one scale's retained labels own."""
    if not retained_labels:
        return np.zeros(labels.shape, dtype=np.bool_)
    return np.asarray(
        np.isin(labels, np.asarray(retained_labels, dtype=np.int32)),
        dtype=np.bool_,
    )
