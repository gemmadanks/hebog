# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Scale-feature envelopes and the overlap summary association decides on.

The association stage builds the same summary tile by tile from these
envelopes; :func:`summarize_hierarchy_overlaps` builds it from whole planes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected_component_labels

from hebog.algorithms.multiscale import residual_atrous_scale_halos_pixels
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    adjacent_scale_overlap_edges,
)
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.source_association import (
    DetectionComponentRecord,
)


def _attached_finest_features(
    record: DetectionComponentRecord,
    labels: npt.NDArray[np.int64],
    planes: tuple[ScaleDetectionPlane, ...],
) -> tuple[str, ...]:
    """Return every finest-scale feature intersecting one direct owner."""
    owner = labels == record.label_value
    for plane in planes:
        feature_labels = tuple(
            sorted(
                int(value)
                for value in np.unique(plane.component_labels[owner])
                if value > 0
            )
        )
        if not feature_labels:
            continue
        return tuple(
            plane.detections[label_value - 1].detection_id
            for label_value in feature_labels
        )
    return ()


@dataclass(frozen=True, slots=True)
class FeatureOverlaps:
    """Every pixel fact the hierarchy decision needs about one feature.

    The feature is the object of this work: each field is derived inside the
    feature's own exact bounds plus the reviewed B3 footprint, so one task can
    produce it without seeing the plane around it.
    """

    feature_id: str
    scale_order: int
    exact_component_ids: frozenset[str]
    has_envelope: bool
    influence_component_ids: frozenset[str]
    support_component: int


@dataclass(frozen=True, slots=True)
class HierarchyOverlaps:
    """Every pixel fact the source hierarchy decision needs.

    Each field is a reduction that a tile core or one feature's window can
    produce and that merges associatively, so the decision that consumes it
    is pure record logic and cannot depend on tile geometry.
    ``support_component`` is zero where a feature is not wholly inside one
    retained support component. ``influence_component_ids`` is filled only
    for the features :func:`influence_candidate_feature_ids` admits, and
    ``envelope_edges`` only for the scale pairs
    :func:`envelope_pair_is_needed` admits, because no decision reads the
    rest and deriving them is pixel work.
    """

    features: tuple[FeatureOverlaps, ...]
    finest_features_by_component: Mapping[str, tuple[str, ...]]
    parent_edges: tuple[tuple[str, str], ...]
    support_component_by_component: Mapping[str, int]
    envelope_edges: frozenset[frozenset[str]]

    def by_id(self) -> dict[str, FeatureOverlaps]:
        """Index the feature overlaps by their stable identities."""
        return {item.feature_id: item for item in self.features}

    def adjacency(self, feature_ids: frozenset[str]) -> dict[str, set[str]]:
        """Return the envelope overlap graph over the named features."""
        enveloped = {
            item.feature_id
            for item in self.features
            if item.has_envelope and item.feature_id in feature_ids
        }
        adjacency: dict[str, set[str]] = {
            feature_id: set() for feature_id in enveloped
        }
        for edge in self.envelope_edges:
            first, second = sorted(edge)
            if first in enveloped and second in enveloped:
                adjacency[first].add(second)
                adjacency[second].add(first)
        return adjacency


@dataclass(frozen=True, slots=True)
class _FeatureEnvelope:
    """One bounded B3-footprint envelope around exact feature support."""

    feature_id: str
    bounds_yx: tuple[int, int, int, int]
    support: npt.NDArray[np.bool_]


def scale_feature_envelope_bounds(
    feature_bounds: ImageBounds,
    *,
    scale_order: int,
    image_shape_yx: tuple[int, int],
) -> ImageBounds | None:
    """Return one feature's B3 envelope box, or absence beyond the footprint.

    The box follows from the feature's own bounds, so a driver knows it from
    records alone and one task can evaluate the envelope inside it.
    """
    halos = residual_atrous_scale_halos_pixels()
    if scale_order > len(halos):
        return None
    radius = halos[scale_order - 1]
    return ImageBounds(
        max(0, feature_bounds.y_start - radius),
        min(image_shape_yx[0], feature_bounds.y_stop + radius),
        max(0, feature_bounds.x_start - radius),
        min(image_shape_yx[1], feature_bounds.x_stop + radius),
    )


def scale_feature_envelope_support(
    exact_support: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
    *,
    scale_order: int,
) -> npt.NDArray[np.bool_]:
    """Dilate one feature's exact support over its own envelope window.

    Both arrays cover the envelope box that
    :func:`scale_feature_envelope_bounds` returns.
    """
    radius = residual_atrous_scale_halos_pixels()[scale_order - 1]
    return np.asarray(
        binary_dilation(
            exact_support,
            structure=np.ones((3, 3), dtype=np.bool_),
            iterations=radius,
            mask=valid,
        ),
        dtype=np.bool_,
    )


def scale_feature_influence_bounds(
    envelope_bounds: ImageBounds,
    *,
    scale_order: int,
    image_shape_yx: tuple[int, int],
) -> ImageBounds:
    """Return the symmetric reviewed B3 influence box of one envelope."""
    radius = residual_atrous_scale_halos_pixels()[scale_order - 1]
    return ImageBounds(
        max(0, envelope_bounds.y_start - radius),
        min(image_shape_yx[0], envelope_bounds.y_stop + radius),
        max(0, envelope_bounds.x_start - radius),
        min(image_shape_yx[1], envelope_bounds.x_stop + radius),
    )


def scale_feature_influence_component_labels(
    envelope_seed: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
    component_labels: npt.NDArray[np.int64],
    *,
    scale_order: int,
) -> frozenset[int]:
    """Return the owner labels within the symmetric reviewed B3 influence.

    Every array covers the influence box that
    :func:`scale_feature_influence_bounds` returns, with the envelope support
    already placed at its offset inside ``envelope_seed``. The labels are
    those of ``component_labels``; the caller names their components.
    """
    radius = residual_atrous_scale_halos_pixels()[scale_order - 1]
    influence = np.asarray(
        binary_dilation(
            envelope_seed,
            structure=np.ones((3, 3), dtype=np.bool_),
            iterations=radius,
            mask=valid,
        ),
        dtype=np.bool_,
    )
    return frozenset(
        int(label_value)
        for label_value in np.unique(component_labels[influence])
        if int(label_value) > 0
    )


def scale_feature_envelopes_overlap(
    first_support: npt.NDArray[np.bool_],
    first_bounds: ImageBounds,
    second_support: npt.NDArray[np.bool_],
    second_bounds: ImageBounds,
) -> bool:
    """Return whether two bounded envelopes share a supported pixel."""
    y0 = max(first_bounds.y_start, second_bounds.y_start)
    y1 = min(first_bounds.y_stop, second_bounds.y_stop)
    x0 = max(first_bounds.x_start, second_bounds.x_start)
    x1 = min(first_bounds.x_stop, second_bounds.x_stop)
    if y0 >= y1 or x0 >= x1:
        return False
    return bool(
        np.any(
            first_support[
                y0 - first_bounds.y_start : y1 - first_bounds.y_start,
                x0 - first_bounds.x_start : x1 - first_bounds.x_start,
            ]
            & second_support[
                y0 - second_bounds.y_start : y1 - second_bounds.y_start,
                x0 - second_bounds.x_start : x1 - second_bounds.x_start,
            ]
        )
    )


def _feature_envelopes(
    plane: ScaleDetectionPlane,
    valid: npt.NDArray[np.bool_],
) -> tuple[_FeatureEnvelope, ...]:
    """Derive bounded valid envelopes from the fixed B3 filter footprint."""
    origin_y, origin_x = plane.origin_yx
    height, width = plane.component_labels.shape
    envelopes: list[_FeatureEnvelope] = []
    for label_value, detection in enumerate(plane.detections, start=1):
        global_y0, global_y1, global_x0, global_x1 = detection.bounds_yx
        box = scale_feature_envelope_bounds(
            ImageBounds(
                global_y0 - origin_y,
                global_y1 - origin_y,
                global_x0 - origin_x,
                global_x1 - origin_x,
            ),
            scale_order=plane.scale_order,
            image_shape_yx=(height, width),
        )
        if box is None:
            return ()
        window = np.s_[box.y_start : box.y_stop, box.x_start : box.x_stop]
        envelope = scale_feature_envelope_support(
            np.asarray(plane.component_labels[window] == label_value),
            valid[window],
            scale_order=plane.scale_order,
        )
        envelope.setflags(write=False)
        envelopes.append(
            _FeatureEnvelope(
                feature_id=detection.detection_id,
                bounds_yx=(box.y_start, box.y_stop, box.x_start, box.x_stop),
                support=envelope,
            )
        )
    return tuple(envelopes)


def _envelopes_overlap(
    first: _FeatureEnvelope,
    second: _FeatureEnvelope,
) -> bool:
    """Return whether box-overlapping bounded envelopes share support."""
    return scale_feature_envelopes_overlap(
        first.support,
        ImageBounds(*first.bounds_yx),
        second.support,
        ImageBounds(*second.bounds_yx),
    )


def _feature_exact_component_ids(
    plane: ScaleDetectionPlane,
    feature_label: int,
    labels: npt.NDArray[np.int64],
    component_id_by_label: Mapping[int, str],
) -> frozenset[str]:
    """Return direct owners intersecting one exact scale feature."""
    return frozenset(
        component_id_by_label[int(label_value)]
        for label_value in np.unique(
            labels[plane.component_labels == feature_label]
        )
        if int(label_value) > 0
    )


def _feature_influence_component_ids(
    plane: ScaleDetectionPlane,
    envelope: _FeatureEnvelope,
    labels: npt.NDArray[np.int64],
    valid: npt.NDArray[np.bool_],
    component_id_by_label: Mapping[int, str],
) -> frozenset[str]:
    """Return owners within the symmetric reviewed B3 influence support."""
    y0, y1, x0, x1 = envelope.bounds_yx
    envelope_bounds = ImageBounds(y0, y1, x0, x1)
    box = scale_feature_influence_bounds(
        envelope_bounds,
        scale_order=plane.scale_order,
        image_shape_yx=(labels.shape[0], labels.shape[1]),
    )
    seed = np.zeros(box.shape_yx, dtype=np.bool_)
    seed[
        y0 - box.y_start : y1 - box.y_start,
        x0 - box.x_start : x1 - box.x_start,
    ] = envelope.support
    window = np.s_[box.y_start : box.y_stop, box.x_start : box.x_stop]
    return frozenset(
        component_id_by_label[label_value]
        for label_value in scale_feature_influence_component_labels(
            seed,
            valid[window],
            labels[window],
            scale_order=plane.scale_order,
        )
    )


def _feature_support_components(
    plane: ScaleDetectionPlane,
    support_component_labels: npt.NDArray[np.int64],
) -> dict[str, int]:
    """Map features wholly contained by one retained support component."""
    components: dict[str, int] = {}
    for label_value, detection in enumerate(plane.detections, start=1):
        values = np.unique(
            support_component_labels[plane.component_labels == label_value]
        )
        if values.size == 1 and int(values[0]) > 0:
            components[detection.detection_id] = int(values[0])
    return components


def _connected_support_components(
    records: tuple[DetectionComponentRecord, ...],
    labels: npt.NDArray[np.int64],
    significant: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
) -> tuple[npt.NDArray[np.int64], dict[str, int]]:
    """Label retained support and name the component each owner occupies."""
    support_labels, _ = cast(
        tuple[npt.NDArray[np.int64], int],
        connected_component_labels(
            ((labels > 0) | significant) & valid,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    support_labels = np.asarray(support_labels, dtype=np.int64)
    support_labels.setflags(write=False)
    by_component: dict[str, int] = {}
    for record in records:
        occupied = tuple(
            sorted(
                int(value)
                for value in np.unique(
                    support_labels[labels == record.label_value]
                )
                if value > 0
            )
        )
        if len(occupied) != 1:
            raise ValueError(
                "each direct component must occupy one connected support "
                "parent"
            )
        by_component[record.component_id] = occupied[0]
    return support_labels, by_component


def influence_candidate_feature_ids(
    exact_component_ids: Mapping[str, frozenset[str]],
    parent_edges: tuple[tuple[str, str], ...],
) -> frozenset[str]:
    """Return the features whose B3 influence a decision can ever read.

    :func:`_feature_influence_candidate` rejects every other feature on
    record evidence alone, so deriving their influence would be pixel work
    nothing consumes.
    """
    parents: dict[str, set[str]] = {}
    children: dict[str, set[str]] = {}
    for child_id, parent_id in parent_edges:
        parents.setdefault(child_id, set()).add(parent_id)
        children.setdefault(parent_id, set()).add(child_id)
    candidates: set[str] = set()
    for feature_id, child_ids in children.items():
        if len(child_ids) != 1:
            continue
        child_id = next(iter(child_ids))
        exact = exact_component_ids.get(feature_id, frozenset())
        if (
            parents.get(child_id) != {feature_id}
            or len(exact) != 1
            or exact_component_ids.get(child_id, frozenset()) != exact
        ):
            continue
        candidates.add(feature_id)
    return frozenset(candidates)


def envelope_pair_is_needed(
    first_scale_order: int,
    second_scale_order: int,
    *,
    terminal_scale_order: int,
) -> bool:
    """Return whether any decision asks about this pair of scales.

    Within-scale overlap builds each scale's adjacency graph, and the last
    two scales are paired once to corroborate a displaced terminal child.
    No other combination is read.
    """
    if first_scale_order == second_scale_order:
        return True
    return {first_scale_order, second_scale_order} == {
        terminal_scale_order - 1,
        terminal_scale_order,
    }


def summarize_hierarchy_overlaps(
    records: tuple[DetectionComponentRecord, ...],
    labels: npt.NDArray[np.int64],
    planes: tuple[ScaleDetectionPlane, ...],
    valid: npt.NDArray[np.bool_],
    significant: npt.NDArray[np.bool_],
) -> HierarchyOverlaps:
    """Derive every pixel fact the hierarchy decision needs, whole-plane.

    This is the serial oracle for the tiled rounds: each field is the same
    reduction a tile core or one feature's window produces, evaluated here
    over complete planes.
    """
    component_id_by_label = {
        record.label_value: record.component_id for record in records
    }
    support_labels, support_by_component = _connected_support_components(
        records, labels, significant, valid
    )
    envelopes = tuple(
        envelope
        for plane in planes
        for envelope in _feature_envelopes(plane, valid)
    )
    enveloped = {envelope.feature_id: envelope for envelope in envelopes}
    scale_by_feature: dict[str, int] = {}
    exact_by_feature: dict[str, frozenset[str]] = {}
    support_by_feature: dict[str, int] = {}
    plane_by_feature: dict[str, tuple[ScaleDetectionPlane, int]] = {}
    for plane in planes:
        supports = _feature_support_components(plane, support_labels)
        for feature_label, detection in enumerate(plane.detections, start=1):
            feature_id = detection.detection_id
            scale_by_feature[feature_id] = plane.scale_order
            plane_by_feature[feature_id] = (plane, feature_label)
            exact_by_feature[feature_id] = _feature_exact_component_ids(
                plane, feature_label, labels, component_id_by_label
            )
            support_by_feature[feature_id] = supports.get(feature_id, 0)
    parent_edges = adjacent_scale_overlap_edges(planes)
    influence_candidates = influence_candidate_feature_ids(
        exact_by_feature, parent_edges
    )
    return HierarchyOverlaps(
        features=tuple(
            FeatureOverlaps(
                feature_id=feature_id,
                scale_order=scale_by_feature[feature_id],
                exact_component_ids=exact_by_feature[feature_id],
                has_envelope=feature_id in enveloped,
                influence_component_ids=_feature_influence_component_ids(
                    plane_by_feature[feature_id][0],
                    enveloped[feature_id],
                    labels,
                    valid,
                    component_id_by_label,
                )
                if feature_id in influence_candidates
                and feature_id in enveloped
                else frozenset(),
                support_component=support_by_feature[feature_id],
            )
            for feature_id in scale_by_feature
        ),
        finest_features_by_component={
            record.component_id: _attached_finest_features(
                record, labels, planes
            )
            for record in records
        },
        parent_edges=parent_edges,
        support_component_by_component=support_by_component,
        envelope_edges=_envelope_overlap_edges(
            envelopes,
            scale_by_feature,
            terminal_scale_order=planes[-1].scale_order,
        ),
    )


def _envelope_overlap_edges(
    envelopes: tuple[_FeatureEnvelope, ...],
    scale_by_feature: Mapping[str, int],
    *,
    terminal_scale_order: int,
) -> frozenset[frozenset[str]]:
    """Return one unordered pair per overlapping pair a decision reads."""
    edges: set[frozenset[str]] = set()
    active: list[_FeatureEnvelope] = []
    for envelope in sorted(
        envelopes, key=lambda item: (item.bounds_yx[0], item.feature_id)
    ):
        y0 = envelope.bounds_yx[0]
        active = [item for item in active if item.bounds_yx[1] > y0]
        for other in active:
            if not envelope_pair_is_needed(
                scale_by_feature[other.feature_id],
                scale_by_feature[envelope.feature_id],
                terminal_scale_order=terminal_scale_order,
            ) or not _envelopes_overlap(other, envelope):
                continue
            edges.add(frozenset((other.feature_id, envelope.feature_id)))
        active.append(envelope)
    return frozenset(edges)
