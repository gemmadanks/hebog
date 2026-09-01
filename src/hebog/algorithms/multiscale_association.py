# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Deterministic bounded association of exact multiscale supports."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from math import ceil, floor, isfinite
from numbers import Real
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected_component_labels

from hebog.data_models.multiscale import (
    CompactExtendedContextEdge,
    CompactSourceSupport,
    CrossScaleAssociation,
    ScaleDetection,
)

_ASSOCIATION_ID_NAMESPACE = b"phase-5-cross-scale-association-v1\0"
_DETECTION_ID_NAMESPACE = b"phase-5-scale-detection-v1\0"
_IMAGE_DIMENSIONS = 2
_COMPACT_CONTEXT_RADIUS_BEAMS = 0.5
_MINIMUM_PERSISTENT_SCALE_COUNT = 2


def compact_context_halo_pixels(beam_major_fwhm_pixels: float) -> int:
    """Return the reviewed half-major-beam context radius in pixels."""
    if (
        isinstance(beam_major_fwhm_pixels, bool)
        or not isinstance(beam_major_fwhm_pixels, Real)
        or not isfinite(beam_major_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0
    ):
        raise ValueError("beam major FWHM must be finite and positive")
    return ceil(_COMPACT_CONTEXT_RADIUS_BEAMS * beam_major_fwhm_pixels)


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


def _scale_detection_id(
    scale_order: int,
    canonical_pixel_yx: tuple[int, int],
) -> str:
    """Derive one stable feature identity from scale and global owner pixel."""
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
    detections: list[ScaleDetection] = []
    y_origin, x_origin = origin_yx
    for label_value in range(1, count + 1):
        local_y, local_x = np.nonzero(labels == label_value)
        feature_response = np.asarray(
            response[local_y, local_x],
            dtype=np.float64,
        )
        feature_snr = np.asarray(snr[local_y, local_x], dtype=np.float64)
        if (
            not np.all(np.isfinite(feature_response))
            or not np.all(np.isfinite(feature_snr))
            or float(np.max(feature_response)) <= 0.0
        ):
            raise ValueError(
                "significant scale features require finite positive response"
            )
        canonical = (
            int(local_y[0]) + y_origin,
            int(local_x[0]) + x_origin,
        )
        detections.append(
            ScaleDetection(
                detection_id=_scale_detection_id(scale_order, canonical),
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=nominal_scale_beam_fwhm,
                support_pixel_count=int(local_y.size),
                valid_support_fraction=1.0,
                bounds_yx=(
                    int(np.min(local_y)) + y_origin,
                    int(np.max(local_y)) + y_origin + 1,
                    int(np.min(local_x)) + x_origin,
                    int(np.max(local_x)) + x_origin + 1,
                ),
                canonical_pixel_yx=canonical,
                peak_response_jy_per_beam=float(np.max(feature_response)),
                peak_signal_to_noise=float(np.max(feature_snr)),
                touches_image_edge=bool(
                    np.any(local_y == 0)
                    or np.any(local_x == 0)
                    or np.any(local_y == support.shape[0] - 1)
                    or np.any(local_x == support.shape[1] - 1)
                ),
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=np.asarray(labels, dtype=np.int32),
        detections=tuple(detections),
        origin_yx=origin_yx,
    )


@dataclass(frozen=True, slots=True)
class CompactSourcePlane:
    """One bounded exact-support plane for accepted compact sources.

    ``sources[index - 1]`` describes pixels labelled ``index``. The source
    and its Phase 4 island identity are immutable inputs; this context stage
    may group them spatially but cannot merge or relabel them.
    """

    source_labels: npt.NDArray[np.int32]
    sources: tuple[CompactSourceSupport, ...]
    origin_yx: tuple[int, int] = (0, 0)

    def __post_init__(self) -> None:
        """Copy the bounded labels into immutable canonical storage."""
        labels = np.asarray(self.source_labels)
        if labels.ndim != _IMAGE_DIMENSIONS:
            raise ValueError("compact source labels must be two-dimensional")
        if not np.issubdtype(labels.dtype, np.integer):
            raise ValueError("compact source labels must be integers")
        if min(self.origin_yx) < 0:
            raise ValueError("compact source origin must be non-negative")
        if bool(np.any(labels < 0)):
            raise ValueError("compact source labels must be non-negative")
        if int(np.max(labels, initial=0)) > np.iinfo(np.int32).max:
            raise ValueError("compact source labels must fit signed 32-bit")
        canonical = np.asarray(labels, dtype=np.int32).copy()
        canonical.setflags(write=False)
        object.__setattr__(self, "source_labels", canonical)


@dataclass(frozen=True, slots=True)
class CompactContextResult:
    """Array-free many-to-many spatial context for Step 4 reconciliation."""

    associations: tuple[CrossScaleAssociation, ...]
    edges: tuple[CompactExtendedContextEdge, ...]


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


def _validate_compact_plane(plane: CompactSourcePlane) -> None:
    """Require exact compact labels to agree with accepted source metadata."""
    labels = plane.source_labels
    maximum_label = int(np.max(labels, initial=0))
    if maximum_label != len(plane.sources):
        raise ValueError(
            "compact source labels must cover every source exactly once"
        )
    source_ids = tuple(source.source_id for source in plane.sources)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("compact source IDs must be unique")
    counts = np.bincount(labels.ravel(), minlength=len(plane.sources) + 1)
    bounds = _label_bounds(
        labels,
        label_count=len(plane.sources),
        origin_yx=plane.origin_yx,
    )
    y_origin, x_origin = plane.origin_yx
    y_stop = y_origin + labels.shape[0]
    x_stop = x_origin + labels.shape[1]
    for label_value, (source, observed_bounds) in enumerate(
        zip(plane.sources, bounds, strict=True),
        start=1,
    ):
        if int(counts[label_value]) != source.support_pixel_count:
            raise ValueError(
                "compact support pixel count must match exact labels"
            )
        if observed_bounds != source.bounds_yx:
            raise ValueError("compact source bounds must match exact labels")
        reference_y, reference_x = source.reference_position_yx
        reference_pixel = (
            floor(reference_y + 0.5),
            floor(reference_x + 0.5),
        )
        if not (
            y_origin <= reference_pixel[0] < y_stop
            and x_origin <= reference_pixel[1] < x_stop
        ):
            raise ValueError(
                "compact reference position must be within its bounded plane"
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


def persistent_adjacent_scale_support(
    planes: tuple[ScaleDetectionPlane, ...],
) -> npt.NDArray[np.bool_]:
    """Return exact support whose features persist across adjacent scales."""
    if not planes:
        raise ValueError("persistent support requires a scale detection plane")
    ordered_planes, _ = _validated_inputs(planes)
    persistent_ids = {
        detection_id
        for association in associate_adjacent_scale_detections(ordered_planes)
        if (
            len(association.contributing_scale_orders)
            >= _MINIMUM_PERSISTENT_SCALE_COUNT
        )
        for detection_id in association.scale_detection_ids
    }
    support = np.zeros(
        ordered_planes[0].component_labels.shape,
        dtype=np.bool_,
    )
    for plane in ordered_planes:
        retained_labels = np.asarray(
            [
                index
                for index, detection in enumerate(plane.detections, start=1)
                if detection.detection_id in persistent_ids
            ],
            dtype=np.int32,
        )
        if retained_labels.size:
            support |= np.isin(plane.component_labels, retained_labels)
    support.setflags(write=False)
    return support


def _validate_uncontextualized_associations(
    associations: tuple[CrossScaleAssociation, ...],
    detections_by_id: dict[str, ScaleDetection],
) -> None:
    """Require a complete unambiguous pre-context association graph."""
    association_ids = tuple(item.association_id for item in associations)
    if len(set(association_ids)) != len(association_ids):
        raise ValueError("association IDs must be unique")
    claimed_detection_ids: list[str] = []
    for association in associations:
        if (
            association.relationship != "extended-only"
            or association.compact_source_ids
        ):
            raise ValueError(
                "compact-context inputs must be extended-only associations"
            )
        for detection_id in association.scale_detection_ids:
            if detection_id not in detections_by_id:
                raise ValueError(
                    "association names an unknown scale detection"
                )
            claimed_detection_ids.append(detection_id)
        expected_orders = tuple(
            sorted(
                {
                    detections_by_id[detection_id].scale_order
                    for detection_id in association.scale_detection_ids
                }
            )
        )
        if association.contributing_scale_orders != expected_orders:
            raise ValueError(
                "association contributing scale orders disagree with support"
            )
    if len(set(claimed_detection_ids)) != len(claimed_detection_ids):
        raise ValueError(
            "each scale detection must be claimed by one association"
        )
    if set(claimed_detection_ids) != set(detections_by_id):
        raise ValueError("associations must claim every scale detection")


def _validate_context_inputs(
    planes: tuple[ScaleDetectionPlane, ...],
    associations: tuple[CrossScaleAssociation, ...],
    compact_plane: CompactSourcePlane,
) -> tuple[
    tuple[ScaleDetectionPlane, ...],
    dict[str, ScaleDetection],
]:
    """Validate complete uncontextualized associations and aligned support."""
    _validate_compact_plane(compact_plane)
    if not planes:
        if associations:
            raise ValueError("associations require scale detection planes")
        return (), {}
    ordered_planes, detections_by_id = _validated_inputs(planes)
    first = ordered_planes[0]
    if compact_plane.source_labels.shape != first.component_labels.shape:
        raise ValueError(
            "compact and scale support planes must have same shape"
        )
    if compact_plane.origin_yx != first.origin_yx:
        raise ValueError(
            "compact and scale support planes must have same origin"
        )
    _validate_uncontextualized_associations(
        associations,
        detections_by_id,
    )
    return ordered_planes, detections_by_id


def _association_owner_labels(
    planes: tuple[ScaleDetectionPlane, ...],
    associations: tuple[CrossScaleAssociation, ...],
) -> tuple[npt.NDArray[np.int32], dict[str, int]]:
    """Build one bounded owner plane and reject cross-association conflicts."""
    ordered_associations = tuple(
        sorted(associations, key=lambda item: item.association_id)
    )
    association_labels = {
        association.association_id: label_value
        for label_value, association in enumerate(
            ordered_associations,
            start=1,
        )
    }
    detection_labels = {
        detection_id: association_labels[association.association_id]
        for association in ordered_associations
        for detection_id in association.scale_detection_ids
    }
    shape = planes[0].component_labels.shape
    owner_labels = np.zeros(shape, dtype=np.int32)
    for plane in planes:
        local_lookup = np.zeros(len(plane.detections) + 1, dtype=np.int32)
        for local_label, detection in enumerate(plane.detections, start=1):
            local_lookup[local_label] = detection_labels[
                detection.detection_id
            ]
        plane_owners = local_lookup[plane.component_labels]
        conflict = (
            (owner_labels > 0)
            & (plane_owners > 0)
            & (owner_labels != plane_owners)
        )
        if bool(np.any(conflict)):
            raise ValueError(
                "conflicting exact support ownership between associations"
            )
        unclaimed = (owner_labels == 0) & (plane_owners > 0)
        owner_labels[unclaimed] = plane_owners[unclaimed]
    owner_labels.setflags(write=False)
    return owner_labels, association_labels


def _reference_is_inside(
    source: CompactSourceSupport,
    support: npt.NDArray[np.bool_],
    *,
    origin_yx: tuple[int, int],
) -> bool:
    """Return whether the reference pixel centre lies on exact support."""
    reference_y, reference_x = source.reference_position_yx
    y_origin, x_origin = origin_yx
    local_y = floor(reference_y + 0.5) - y_origin
    local_x = floor(reference_x + 0.5) - x_origin
    return bool(support[local_y, local_x])


def _context_edges(
    association: CrossScaleAssociation,
    support: npt.NDArray[np.bool_],
    compact_plane: CompactSourcePlane,
    *,
    dilation_iterations: int,
) -> tuple[CompactExtendedContextEdge, ...]:
    """Return every exact or half-beam compact spatial edge."""
    context_support = cast(
        npt.NDArray[np.bool_],
        binary_dilation(support, iterations=dilation_iterations),
    )
    labels = compact_plane.source_labels
    candidate_labels = {
        int(label_value)
        for label_value in np.unique(labels[context_support & (labels > 0)])
    }
    for label_value, source in enumerate(compact_plane.sources, start=1):
        if _reference_is_inside(
            source,
            support,
            origin_yx=compact_plane.origin_yx,
        ):
            candidate_labels.add(label_value)
    edges: list[CompactExtendedContextEdge] = []
    for label_value in candidate_labels:
        source = compact_plane.sources[label_value - 1]
        relationship = (
            "contains-compact-support"
            if _reference_is_inside(
                source,
                support,
                origin_yx=compact_plane.origin_yx,
            )
            else "overlaps-compact-support"
        )
        edges.append(
            CompactExtendedContextEdge(
                association_id=association.association_id,
                compact_source_id=source.source_id,
                relationship=relationship,
            )
        )
    return tuple(sorted(edges, key=lambda item: item.compact_source_id))


def _apply_context(
    association: CrossScaleAssociation,
    edges: tuple[CompactExtendedContextEdge, ...],
) -> CrossScaleAssociation:
    """Annotate one association without changing either side's identity."""
    if not edges:
        return association
    source_ids = tuple(edge.compact_source_id for edge in edges)
    relationship = (
        "contains-compact-support"
        if all(
            edge.relationship == "contains-compact-support" for edge in edges
        )
        else "overlaps-compact-support"
    )
    return CrossScaleAssociation(
        association_id=association.association_id,
        scale_detection_ids=association.scale_detection_ids,
        compact_source_ids=source_ids,
        selected_scale_detection_id=association.selected_scale_detection_id,
        contributing_scale_orders=association.contributing_scale_orders,
        relationship=relationship,
    )


def associate_compact_source_context(
    planes: tuple[ScaleDetectionPlane, ...],
    associations: tuple[CrossScaleAssociation, ...],
    compact_plane: CompactSourcePlane,
    *,
    beam_major_fwhm_pixels: float,
) -> CompactContextResult:
    """Attach approved compact spatial context without merging source rows.

    Exact overlap and reference containment use the original bounded supports.
    Adjacency uses the same half-major-beam dilation reviewed for multiscale
    support recovery. The dilation creates graph evidence only: neither exact
    support nor compact/extended pixel ownership is changed.
    """
    dilation_iterations = compact_context_halo_pixels(beam_major_fwhm_pixels)
    ordered_planes, _ = _validate_context_inputs(
        planes,
        associations,
        compact_plane,
    )
    if not ordered_planes:
        return CompactContextResult(associations=(), edges=())
    owner_labels, association_labels = _association_owner_labels(
        ordered_planes,
        associations,
    )
    contextualized: list[CrossScaleAssociation] = []
    all_edges: list[CompactExtendedContextEdge] = []
    for association in sorted(
        associations,
        key=lambda item: item.association_id,
    ):
        edges = _context_edges(
            association,
            owner_labels == association_labels[association.association_id],
            compact_plane,
            dilation_iterations=dilation_iterations,
        )
        contextualized.append(_apply_context(association, edges))
        all_edges.extend(edges)
    return CompactContextResult(
        associations=tuple(contextualized),
        edges=tuple(
            sorted(
                all_edges,
                key=lambda item: (
                    item.association_id,
                    item.compact_source_id,
                ),
            )
        ),
    )
