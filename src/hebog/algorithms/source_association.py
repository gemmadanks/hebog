# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Conservative deterministic grouping of immutable detection components."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import combinations
from math import isfinite
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected_component_labels

from hebog.algorithms.label_groups import label_windows
from hebog.algorithms.multiscale import residual_atrous_scale_halos_pixels
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    ScaleDetections,
    adjacent_scale_overlap_edges,
    associate_adjacent_scale_detections,
)
from hebog.data_models.partitioning import ImageBounds
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationEdge,
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)

_COMPONENT_NAMESPACE = b"phase-5-detection-component-v1\0"
_SOURCE_NAMESPACE = b"phase-5-associated-source-v1\0"
_IMAGE_DIMENSIONS = 2
_MINIMUM_SHAPE_PIXELS = 3
_MINIMUM_SOURCE_MEMBERS = 2
_MINIMUM_CYCLE_DEGREE = 2
_MINIMUM_ADJACENT_PLANES = 2
_GAUSSIAN_FWHM_FACTOR = 2.0 * np.sqrt(2.0 * np.log(2.0))


def _stable_id(namespace: bytes, prefix: str, values: tuple[str, ...]) -> str:
    """Hash canonical identity fields into one stable domain identifier."""
    digest = sha256(namespace)
    for value in values:
        digest.update(value.encode("ascii"))
        digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()}"


def _component_id(canonical_pixel_yx: tuple[int, int]) -> str:
    """Derive identity from the component's global canonical owner pixel."""
    return _stable_id(
        _COMPONENT_NAMESPACE,
        "component-detection",
        tuple(str(value) for value in canonical_pixel_yx),
    )


def _source_id(component_ids: tuple[str, ...]) -> str:
    """Derive one source identity from sorted stable component membership."""
    return _stable_id(
        _SOURCE_NAMESPACE,
        "source-associated",
        component_ids,
    )


def _validated_planes(
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
    labels, signal, valid = _validated_planes(
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


def _validated_association_inputs(  # noqa: PLR0913
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    island_threshold_sigma: float,
) -> tuple[
    npt.NDArray[np.int64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
]:
    """Validate complete records and aligned frozen graph evidence."""
    labels, snr, valid = _validated_planes(
        component_labels,
        combined_snr,
        valid_pixels,
    )
    significant = np.asarray(significant_multiscale_support)
    if (
        significant.ndim != _IMAGE_DIMENSIONS
        or significant.shape != labels.shape
        or significant.dtype != np.bool_
    ):
        raise ValueError(
            "significant multiscale support must be one aligned boolean plane"
        )
    if (
        isinstance(island_threshold_sigma, bool)
        or not isfinite(island_threshold_sigma)
        or island_threshold_sigma <= 0.0
    ):
        raise ValueError("island threshold sigma must be finite and positive")
    label_values = tuple(
        sorted(int(value) for value in np.unique(labels) if value > 0)
    )
    record_labels = tuple(sorted(item.label_value for item in records))
    record_ids = tuple(item.component_id for item in records)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("component record IDs must be unique")
    if not records or record_labels != label_values:
        raise ValueError("component records must cover every positive label")
    return labels, significant, snr, valid


def _parent_support_by_label(
    records: tuple[DetectionComponentRecord, ...],
    labels: npt.NDArray[np.int64],
    significant: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
) -> dict[int, int]:
    """Map each owner to its undilated eight-connected parent support."""
    parent_labels, _ = cast(
        tuple[npt.NDArray[np.int64], int],
        connected_component_labels(
            ((labels > 0) | significant) & valid,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    output: dict[int, int] = {}
    for record in records:
        local_pixels = np.column_stack(
            np.nonzero(labels == record.label_value)
        )
        output[record.label_value] = int(parent_labels[tuple(local_pixels[0])])
    return output


def _line_pixels(
    first_yx: tuple[float, float],
    second_yx: tuple[float, float],
) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
    """Return deterministic nearest pixels on one straight centroid segment."""
    span = max(
        abs(second_yx[0] - first_yx[0]),
        abs(second_yx[1] - first_yx[1]),
    )
    sample_count = max(2, int(np.ceil(span)) + 1)
    y_pixels = np.rint(
        np.linspace(first_yx[0], second_yx[0], sample_count)
    ).astype(np.intp)
    x_pixels = np.rint(
        np.linspace(first_yx[1], second_yx[1], sample_count)
    ).astype(np.intp)
    return y_pixels, x_pixels


def _directional_fwhm_pixels(
    record: DetectionComponentRecord,
    unit_yx: npt.NDArray[np.float64],
) -> float | None:
    """Project one reviewed component covariance onto the joining line."""
    covariance = record.covariance_pixels_squared
    if covariance is None:
        return None
    values = np.asarray(covariance, dtype=np.float64)
    variance = float(unit_yx @ values @ unit_yx)
    if not isfinite(variance) or variance <= 0.0:
        return None
    return float(_GAUSSIAN_FWHM_FACTOR * np.sqrt(variance))


def _association_edge(  # noqa: PLR0911, PLR0913
    first: DetectionComponentRecord,
    second: DetectionComponentRecord,
    *,
    parent_support: dict[int, int],
    snr: npt.NDArray[np.float64],
    valid: npt.NDArray[np.bool_],
    origin_yx: tuple[int, int],
    island_threshold_sigma: float,
) -> SourceAssociationEdge | None:
    """Return one edge only when every frozen pair requirement passes."""
    if parent_support[first.label_value] != parent_support[second.label_value]:
        return None
    delta = np.subtract(
        second.centroid_yx, first.centroid_yx, dtype=np.float64
    )
    separation = float(np.linalg.norm(delta))
    if not isfinite(separation) or separation <= 0.0:
        return None
    unit_yx = np.asarray(delta / separation, dtype=np.float64)
    first_fwhm = _directional_fwhm_pixels(first, unit_yx)
    second_fwhm = _directional_fwhm_pixels(second, unit_yx)
    if first_fwhm is None or second_fwhm is None:
        return None
    maximum_separation = 0.5 * (first_fwhm + second_fwhm)
    normalized_separation = separation / maximum_separation
    if normalized_separation > 1.0:
        return None
    local_first = (
        first.centroid_yx[0] - origin_yx[0],
        first.centroid_yx[1] - origin_yx[1],
    )
    local_second = (
        second.centroid_yx[0] - origin_yx[0],
        second.centroid_yx[1] - origin_yx[1],
    )
    y_pixels, x_pixels = _line_pixels(local_first, local_second)
    if (
        bool(np.any(y_pixels < 0))
        or bool(np.any(x_pixels < 0))
        or bool(np.any(y_pixels >= snr.shape[0]))
        or bool(np.any(x_pixels >= snr.shape[1]))
        or not bool(np.all(valid[y_pixels, x_pixels]))
    ):
        return None
    line_snr = snr[y_pixels, x_pixels]
    if not bool(np.all(np.isfinite(line_snr))):
        return None
    saddle_margin = float(np.min(line_snr) - island_threshold_sigma)
    if saddle_margin < 0.0:
        return None
    first_id, second_id = sorted((first.component_id, second.component_id))
    return SourceAssociationEdge(
        first_component_id=first_id,
        second_component_id=second_id,
        saddle_margin_sigma=saddle_margin,
        normalized_separation=normalized_separation,
    )


def _canonical_edges(
    edges: tuple[SourceAssociationEdge, ...],
) -> tuple[SourceAssociationEdge, ...]:
    """Deduplicate exact executor evidence and reject disagreement."""
    by_key: dict[tuple[str, str], SourceAssociationEdge] = {}
    for edge in edges:
        key = (edge.first_component_id, edge.second_component_id)
        existing = by_key.setdefault(key, edge)
        if existing != edge:
            raise ValueError("duplicate association edges disagree")
    return tuple(by_key[key] for key in sorted(by_key))


def reduce_source_associations(
    records: tuple[DetectionComponentRecord, ...],
    edges: tuple[SourceAssociationEdge, ...],
) -> SourceAssociationResult:
    """Reduce pair evidence with deterministic complete-link agglomeration."""
    ordered_records = tuple(
        sorted(records, key=lambda item: item.component_id)
    )
    component_ids = tuple(item.component_id for item in ordered_records)
    if len(set(component_ids)) != len(component_ids):
        raise ValueError("component record IDs must be unique")
    canonical_edges = _canonical_edges(edges)
    known_edges = {
        (edge.first_component_id, edge.second_component_id)
        for edge in canonical_edges
    }
    if any(
        component_id not in set(component_ids)
        for edge in canonical_edges
        for component_id in (
            edge.first_component_id,
            edge.second_component_id,
        )
    ):
        raise ValueError("association edge names an unknown component")
    groups: list[set[str]] = [{component_id} for component_id in component_ids]
    science_order = sorted(
        canonical_edges,
        key=lambda item: (
            -item.saddle_margin_sigma,
            item.normalized_separation,
            item.first_component_id,
            item.second_component_id,
        ),
    )
    for edge in science_order:
        first_group = next(
            group for group in groups if edge.first_component_id in group
        )
        second_group = next(
            group for group in groups if edge.second_component_id in group
        )
        if first_group is second_group:
            continue
        if all(
            tuple(sorted((first_id, second_id))) in known_edges
            for first_id in first_group
            for second_id in second_group
        ):
            first_group.update(second_group)
            groups.remove(second_group)
    memberships = tuple(
        sorted(
            (
                CatalogueSourceMembership(
                    source_id=_source_id(tuple(sorted(group))),
                    component_ids=tuple(sorted(group)),
                )
                for group in groups
            ),
            key=lambda item: item.source_id,
        )
    )
    return SourceAssociationResult(
        components=ordered_records,
        edges=canonical_edges,
        memberships=memberships,
    )


def associate_detection_components(  # noqa: PLR0913
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    island_threshold_sigma: float,
    origin_yx: tuple[int, int] = (0, 0),
) -> SourceAssociationResult:
    """Build undilated pair evidence and reduce it to source memberships."""
    if len(origin_yx) != _IMAGE_DIMENSIONS or min(origin_yx) < 0:
        raise ValueError("association origin must contain non-negative y-x")
    labels, significant, snr, valid = _validated_association_inputs(
        records,
        component_labels,
        significant_multiscale_support,
        combined_snr,
        valid_pixels,
        island_threshold_sigma=island_threshold_sigma,
    )
    parent_support = _parent_support_by_label(
        records,
        labels,
        significant,
        valid,
    )
    edges = tuple(
        edge
        for first, second in combinations(records, 2)
        if (
            edge := _association_edge(
                first,
                second,
                parent_support=parent_support,
                snr=snr,
                valid=valid,
                origin_yx=origin_yx,
                island_threshold_sigma=island_threshold_sigma,
            )
        )
        is not None
    )
    return reduce_source_associations(records, edges)


def _hierarchy_inputs(
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    scale_detection_planes: tuple[ScaleDetectionPlane, ...],
    valid_pixels: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.int64],
    tuple[ScaleDetectionPlane, ...],
    npt.NDArray[np.bool_],
]:
    """Validate direct owners and their aligned scale-feature hierarchy."""
    labels, _, valid = _validated_planes(
        component_labels,
        np.zeros(np.asarray(component_labels).shape, dtype=np.float64),
        valid_pixels,
    )
    label_values = tuple(
        sorted(int(value) for value in np.unique(labels) if value > 0)
    )
    if tuple(sorted(item.label_value for item in records)) != label_values:
        raise ValueError("component records must cover every positive label")
    component_ids = tuple(item.component_id for item in records)
    if len(set(component_ids)) != len(component_ids):
        raise ValueError("component record IDs must be unique")
    ordered = tuple(
        sorted(scale_detection_planes, key=lambda item: item.scale_order)
    )
    if not ordered:
        raise ValueError("source hierarchy requires scale detection planes")
    # The existing association call is the canonical complete validation of
    # plane labels, records, origins, and adjacent scale ordering.
    associate_adjacent_scale_detections(ordered)
    if any(item.component_labels.shape != labels.shape for item in ordered):
        raise ValueError("source hierarchy planes must share one shape")
    if any(item.origin_yx != ordered[0].origin_yx for item in ordered):
        raise ValueError("source hierarchy planes must share one origin")
    if any(
        bool(np.any((item.component_labels > 0) & ~valid)) for item in ordered
    ):
        raise ValueError(
            "source hierarchy scale support must be scientifically valid"
        )
    return labels, ordered, valid


def _feature_by_id(
    planes: tuple[ScaleDetections, ...],
) -> dict[str, tuple[int, int]]:
    """Map stable feature identities to scale order and local label."""
    return {
        detection.detection_id: (plane.scale_order, label_value)
        for plane in planes
        for label_value, detection in enumerate(plane.detections, start=1)
    }


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


def _unambiguous_lineage(
    feature_id: str,
    parents_by_id: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], bool]:
    """Return one feature-to-root lineage or fail closed on a branch."""
    visited: set[str] = set()
    current = feature_id
    lineage: list[str] = []
    while current in parents_by_id:
        if current in visited:
            raise ValueError("source hierarchy contains a parent cycle")
        visited.add(current)
        lineage.append(current)
        parents = parents_by_id[current]
        if len(parents) != 1:
            return (), True
        current = parents[0]
    lineage.append(current)
    return tuple(lineage), False


def _nearest_common_feature(
    lineages: tuple[tuple[str, ...], ...],
    feature_index: Mapping[str, tuple[int, int]],
) -> str | None:
    """Return the finest feature shared by every unique lineage."""
    if not lineages:
        return None
    common = set(lineages[0]).intersection(*lineages[1:])
    if not common:
        return None
    return min(common, key=lambda item: (feature_index[item][0], item))


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
class _HierarchyAttachments:
    """Internal attachment paths and their fail-closed census."""

    features_by_component: Mapping[str, tuple[str, ...]]
    lineages_by_component: Mapping[str, tuple[str, ...]]
    ambiguous_component_ids: frozenset[str]
    unattached_count: int
    multiple_attachment_count: int
    branched_lineage_count: int
    no_common_convergence_count: int


@dataclass(frozen=True, slots=True)
class _FeatureEnvelope:
    """One bounded B3-footprint envelope around exact feature support."""

    feature_id: str
    bounds_yx: tuple[int, int, int, int]
    support: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class _ScaleAwareParentEvidence:
    """Accepted scale-aware parent groups and their compact census."""

    groups: tuple[frozenset[str], ...]
    candidate_count: int
    rejected_ambiguity_count: int
    per_scale_candidate_counts: tuple[tuple[int, int], ...]
    accepted_candidate_occurrences: tuple[tuple[frozenset[str], int], ...]
    self_corroborated_groups: frozenset[frozenset[str]] = frozenset()
    feature_influence_candidate_count: int = 0


@dataclass(frozen=True, slots=True)
class _ScaleAwareInputs:
    """Aligned immutable inputs used by scale-aware parent construction."""

    records: tuple[DetectionComponentRecord, ...]
    planes: tuple[ScaleDetections, ...]
    overlaps: HierarchyOverlaps
    attachments: _HierarchyAttachments
    parents_by_id: Mapping[str, tuple[str, ...]]
    feature_index: Mapping[str, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class _FeatureInfluenceIndex:
    """Precomputed identity maps for persistent influence candidates."""

    children_by_parent: Mapping[str, frozenset[str]]
    feature_overlaps: Mapping[str, FeatureOverlaps]
    resolved_component_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ConnectedSupportEvidence:
    """Connected persistent-support corroboration groups and census."""

    groups: tuple[frozenset[str], ...]
    candidate_count: int
    rejected_ambiguity_count: int = 0


@dataclass(frozen=True, slots=True)
class _TerminalFeaturePersistence:
    """Bounded terminal-feature persistence and rejection census."""

    persistent_feature_ids: frozenset[str]
    exact_feature_count: int
    displaced_candidate_count: int
    displaced_accepted_count: int
    missing_child_count: int
    ambiguous_child_count: int
    missing_feature_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class _TerminalCycleEvidence:
    """Terminal cycles whose constituent features persist individually."""

    groups: tuple[frozenset[str], ...]
    candidate_count: int
    rejected_count: int
    accepted_parent_count: int = 0
    exact_feature_count: int = 0
    displaced_candidate_count: int = 0
    displaced_accepted_count: int = 0
    missing_child_count: int = 0
    ambiguous_child_count: int = 0
    conflict_count: int = 0
    pre_eligibility_candidate_count: int = 0
    unseeded_candidate_count: int = 0
    unseeded_persistent_accepted_count: int = 0
    unseeded_persistence_rejected_count: int = 0
    missing_child_resilience_candidate_count: int = 0
    missing_child_resilience_parent_count: int = 0
    missing_child_resilience_rejected_count: int = 0
    missing_child_resilience_groups: tuple[frozenset[str], ...] = ()


def _hierarchy_attachments(
    records: tuple[DetectionComponentRecord, ...],
    finest_features_by_component: Mapping[str, tuple[str, ...]],
    parents_by_id: Mapping[str, tuple[str, ...]],
    feature_index: Mapping[str, tuple[int, int]],
) -> _HierarchyAttachments:
    """Attach direct owners to unique feature lineages."""
    features_by_component: dict[str, tuple[str, ...]] = {}
    lineages_by_component: dict[str, tuple[str, ...]] = {}
    ambiguous: set[str] = set()
    unattached_count = 0
    multiple_attachment_count = 0
    branched_lineage_count = 0
    no_common_convergence_count = 0
    for record in sorted(records, key=lambda item: item.component_id):
        attachments = finest_features_by_component[record.component_id]
        features_by_component[record.component_id] = attachments
        if not attachments:
            unattached_count += 1
            continue
        multiple_attachment_count += len(attachments) > 1
        lineages_and_flags = tuple(
            _unambiguous_lineage(attachment, parents_by_id)
            for attachment in attachments
        )
        if any(is_ambiguous for _, is_ambiguous in lineages_and_flags):
            ambiguous.add(record.component_id)
            branched_lineage_count += 1
            continue
        lineages = tuple(lineage for lineage, _ in lineages_and_flags)
        if len(lineages) == 1:
            lineages_by_component[record.component_id] = lineages[0]
            continue
        convergence = _nearest_common_feature(lineages, feature_index)
        if convergence is None:
            ambiguous.add(record.component_id)
            no_common_convergence_count += 1
            continue
        first_lineage = lineages[0]
        lineages_by_component[record.component_id] = first_lineage[
            first_lineage.index(convergence) :
        ]
    return _HierarchyAttachments(
        features_by_component=features_by_component,
        lineages_by_component=lineages_by_component,
        ambiguous_component_ids=frozenset(ambiguous),
        unattached_count=unattached_count,
        multiple_attachment_count=multiple_attachment_count,
        branched_lineage_count=branched_lineage_count,
        no_common_convergence_count=no_common_convergence_count,
    )


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


def scale_feature_influence_component_ids(
    envelope_seed: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
    component_labels: npt.NDArray[np.int64],
    *,
    scale_order: int,
    component_id_by_label: Mapping[int, str],
) -> frozenset[str]:
    """Return owners within the symmetric reviewed B3 influence support.

    Every array covers the influence box that
    :func:`scale_feature_influence_bounds` returns, with the envelope support
    already placed at its offset inside ``envelope_seed``.
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
        component_id_by_label[int(label_value)]
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


def _cycle_supported_feature_groups(
    adjacency: Mapping[str, set[str]],
) -> tuple[frozenset[str], ...]:
    """Return connected two-core groups, rejecting pairs and chain bridges."""
    remaining = set(adjacency)
    degrees = {
        feature_id: len(neighbours)
        for feature_id, neighbours in adjacency.items()
    }
    queue = deque(
        sorted(
            feature_id
            for feature_id, degree in degrees.items()
            if degree < _MINIMUM_CYCLE_DEGREE
        )
    )
    while queue:
        feature_id = queue.popleft()
        remaining.remove(feature_id)
        for neighbour in sorted(adjacency[feature_id] & remaining):
            degrees[neighbour] -= 1
            if degrees[neighbour] == 1:
                queue.append(neighbour)
    groups: list[frozenset[str]] = []
    unseen = set(remaining)
    while unseen:
        start = min(unseen)
        pending = [start]
        group: set[str] = set()
        while pending:
            feature_id = pending.pop()
            if feature_id not in unseen:
                continue
            unseen.remove(feature_id)
            group.add(feature_id)
            pending.extend(
                sorted(adjacency[feature_id] & unseen, reverse=True)
            )
        groups.append(frozenset(group))
    return tuple(sorted(groups, key=lambda item: tuple(sorted(item))))


def _isolated_sibling_feature_pairs(
    adjacency: Mapping[str, set[str]],
) -> tuple[frozenset[str], ...]:
    """Return mutually unique two-feature envelope relationships.

    Each admitted feature overlaps exactly the other member. Chains,
    crossings, crowded cliques, and one-sided ambiguity therefore fail closed
    before direct-component membership is considered.
    """
    pairs = {
        frozenset((feature_id, next(iter(neighbours))))
        for feature_id, neighbours in adjacency.items()
        if len(neighbours) == 1 and len(adjacency[next(iter(neighbours))]) == 1
    }
    return tuple(sorted(pairs, key=lambda item: tuple(sorted(item))))


def _components_for_feature_group(
    feature_ids: frozenset[str],
    attachments: _HierarchyAttachments,
) -> frozenset[str]:
    """Map one feature group to unambiguous attached direct components."""
    return frozenset(
        component_id
        for component_id, lineage in attachments.lineages_by_component.items()
        if component_id not in attachments.ambiguous_component_ids
        and not feature_ids.isdisjoint(lineage)
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
    return scale_feature_influence_component_ids(
        seed,
        valid[window],
        labels[window],
        scale_order=plane.scale_order,
        component_id_by_label=component_id_by_label,
    )


def _feature_influence_index(
    inputs: _ScaleAwareInputs,
) -> _FeatureInfluenceIndex:
    """Build the bounded lookup maps used by every feature candidate."""
    mutable_children: dict[str, set[str]] = {}
    for child_id, parent_ids in inputs.parents_by_id.items():
        for parent_id in parent_ids:
            mutable_children.setdefault(parent_id, set()).add(child_id)
    return _FeatureInfluenceIndex(
        children_by_parent={
            parent_id: frozenset(child_ids)
            for parent_id, child_ids in mutable_children.items()
        },
        feature_overlaps=inputs.overlaps.by_id(),
        resolved_component_ids=frozenset(
            set(inputs.attachments.lineages_by_component)
            - set(inputs.attachments.ambiguous_component_ids)
        ),
    )


def _feature_influence_candidate(
    inputs: _ScaleAwareInputs,
    index: _FeatureInfluenceIndex,
    feature: FeatureOverlaps,
) -> frozenset[str] | None:
    """Return one exact persistent-anchor plus displaced-owner pair."""
    child_ids = index.children_by_parent.get(feature.feature_id, frozenset())
    if len(child_ids) != 1:
        return None
    child_id = next(iter(child_ids))
    if inputs.parents_by_id.get(child_id) != (feature.feature_id,):
        return None
    exact_ids = feature.exact_component_ids
    child_exact_ids = index.feature_overlaps[child_id].exact_component_ids
    if len(exact_ids) != 1 or child_exact_ids != exact_ids:
        return None
    influenced_ids = feature.influence_component_ids
    if len(influenced_ids) != _MINIMUM_SOURCE_MEMBERS:
        return None
    displaced_ids = influenced_ids - exact_ids
    if len(displaced_ids) != 1 or not displaced_ids.isdisjoint(
        index.resolved_component_ids
    ):
        return None
    return influenced_ids


def _persistent_feature_influence_groups(
    inputs: _ScaleAwareInputs,
) -> dict[int, tuple[frozenset[str], ...]]:
    """Recover one displaced owner from a uniquely persistent feature.

    A feature and its sole mutually unique child must intersect the same one
    immutable direct owner.  At the parent scale, their symmetric fixed B3
    influence may contain exactly one additional owner, and that displaced
    owner must not already have an unambiguous lineage.  Component-level
    mutual uniqueness rejects chains and crowded alternatives.
    """
    index = _feature_influence_index(inputs)
    output: dict[int, tuple[frozenset[str], ...]] = {}
    for plane in inputs.planes:
        proposals = {
            group
            for feature in inputs.overlaps.features
            if feature.scale_order == plane.scale_order
            and feature.has_envelope
            and (group := _feature_influence_candidate(inputs, index, feature))
            is not None
        }
        groups_by_component: dict[str, set[frozenset[str]]] = {}
        for group in proposals:
            for component_id in group:
                groups_by_component.setdefault(component_id, set()).add(group)
        output[plane.scale_order] = tuple(
            sorted(
                (
                    group
                    for group in proposals
                    if all(
                        groups_by_component[component_id] == {group}
                        for component_id in group
                    )
                ),
                key=lambda item: tuple(sorted(item)),
            )
        )
    return output


def _scale_aware_parent_evidence(
    inputs: _ScaleAwareInputs,
) -> _ScaleAwareParentEvidence:
    """Construct persistent cycle or isolated-sibling parent evidence."""
    influence_candidates_by_scale = _persistent_feature_influence_groups(
        inputs,
    )
    candidates_by_scale: dict[int, tuple[frozenset[str], ...]] = {}
    for plane in inputs.planes:
        exact_groups = {
            component_ids
            for detection in plane.detections
            if len(
                component_ids := _components_for_feature_group(
                    frozenset((detection.detection_id,)),
                    inputs.attachments,
                )
            )
            >= _MINIMUM_SOURCE_MEMBERS
        }
        adjacency = inputs.overlaps.adjacency(
            frozenset(detection.detection_id for detection in plane.detections)
        )
        envelope_groups = _isolated_sibling_feature_pairs(adjacency)
        if len(plane.detections) >= _MINIMUM_CYCLE_DEGREE + 1:
            envelope_groups += _cycle_supported_feature_groups(adjacency)
        envelope_component_groups = {
            component_ids
            for feature_group in envelope_groups
            if len(
                component_ids := _components_for_feature_group(
                    feature_group,
                    inputs.attachments,
                )
            )
            >= _MINIMUM_SOURCE_MEMBERS
        }
        candidates_by_scale[plane.scale_order] = tuple(
            sorted(
                exact_groups
                | envelope_component_groups
                | set(influence_candidates_by_scale[plane.scale_order]),
                key=lambda item: tuple(sorted(item)),
            )
        )
    persistent_groups: set[frozenset[str]] = set()
    candidate_keys_by_scale = {
        scale_order: set(candidates)
        for scale_order, candidates in candidates_by_scale.items()
    }
    for scale_order, candidates in candidate_keys_by_scale.items():
        persistent_groups.update(
            candidates & candidate_keys_by_scale.get(scale_order + 1, set())
        )
    influence_groups = frozenset(
        group
        for candidates in influence_candidates_by_scale.values()
        for group in candidates
    )
    persistent_groups.update(influence_groups)
    candidate_count = sum(len(items) for items in candidates_by_scale.values())
    candidate_occurrences = Counter(
        group
        for candidates in candidates_by_scale.values()
        for group in candidates
    )
    overlapping_components = {
        component_id
        for component_id, count in Counter(
            component_id
            for group in persistent_groups
            for component_id in group
        ).items()
        if count > 1
    }
    accepted_groups = tuple(
        sorted(
            (
                group
                for group in persistent_groups
                if group.isdisjoint(overlapping_components)
            ),
            key=lambda item: tuple(sorted(item)),
        )
    )
    accepted_candidates = sum(
        candidate_occurrences[group] for group in accepted_groups
    )
    return _ScaleAwareParentEvidence(
        groups=accepted_groups,
        candidate_count=candidate_count,
        rejected_ambiguity_count=candidate_count - accepted_candidates,
        per_scale_candidate_counts=tuple(
            (plane.scale_order, len(candidates_by_scale[plane.scale_order]))
            for plane in inputs.planes
        ),
        accepted_candidate_occurrences=tuple(
            (group, candidate_occurrences[group]) for group in accepted_groups
        ),
        self_corroborated_groups=frozenset(accepted_groups) & influence_groups,
        feature_influence_candidate_count=sum(
            len(groups) for groups in influence_candidates_by_scale.values()
        ),
    )


def _validated_significant_support(
    value: npt.ArrayLike | None,
    labels: npt.NDArray[np.int64],
    valid: npt.NDArray[np.bool_],
) -> npt.NDArray[np.bool_]:
    """Return aligned persistent support or a fail-closed empty plane."""
    if value is None:
        return np.zeros(labels.shape, dtype=np.bool_)
    support = np.asarray(value)
    if (
        support.ndim != _IMAGE_DIMENSIONS
        or support.shape != labels.shape
        or support.dtype != np.bool_
    ):
        raise ValueError(
            "significant multiscale support must be one aligned boolean plane"
        )
    if bool(np.any(support & ~valid)):
        raise ValueError(
            "significant multiscale support must be scientifically valid"
        )
    return np.asarray(support, dtype=np.bool_)


def _connected_support_evidence(
    support_component_by_component: Mapping[str, int],
    ambiguous_component_ids: frozenset[str],
) -> _ConnectedSupportEvidence:
    """Group direct owners sharing connected persistent emission support."""
    component_ids_by_parent: dict[int, set[str]] = {}
    for component_id, support_component in sorted(
        support_component_by_component.items()
    ):
        component_ids_by_parent.setdefault(support_component, set()).add(
            component_id
        )
    candidates = tuple(
        sorted(
            (
                frozenset(component_ids)
                for component_ids in component_ids_by_parent.values()
                if len(component_ids) >= _MINIMUM_SOURCE_MEMBERS
            ),
            key=lambda item: tuple(sorted(item)),
        )
    )
    groups = tuple(
        group
        for group in candidates
        if group.isdisjoint(ambiguous_component_ids)
    )
    return _ConnectedSupportEvidence(
        groups=groups,
        candidate_count=len(candidates),
        rejected_ambiguity_count=len(candidates) - len(groups),
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


def _support_components_of(
    overlaps: HierarchyOverlaps,
    plane: ScaleDetections,
) -> dict[str, int]:
    """Return the one support component each scale's features occupy."""
    by_id = overlaps.by_id()
    return {
        detection.detection_id: by_id[detection.detection_id].support_component
        for detection in plane.detections
        if by_id[detection.detection_id].support_component > 0
    }


def _terminal_feature_persistence(
    planes: tuple[ScaleDetections, ...],
    overlaps: HierarchyOverlaps,
    parent_edges: tuple[tuple[str, str], ...],
    candidate_feature_ids: frozenset[str],
) -> _TerminalFeaturePersistence:
    """Corroborate exact or mutually unique displaced terminal children."""
    terminal = planes[-1]
    terminal_ids = {item.detection_id for item in terminal.detections}
    exact_feature_ids = frozenset(
        parent_id
        for _, parent_id in parent_edges
        if parent_id in candidate_feature_ids
    )
    missing_exact = candidate_feature_ids - exact_feature_ids
    if (
        not missing_exact
        or len(planes) < _MINIMUM_ADJACENT_PLANES
        or terminal.scale_order != planes[-2].scale_order + 1
    ):
        return _TerminalFeaturePersistence(
            persistent_feature_ids=exact_feature_ids,
            exact_feature_count=len(exact_feature_ids),
            displaced_candidate_count=0,
            displaced_accepted_count=0,
            missing_child_count=len(missing_exact),
            ambiguous_child_count=0,
            missing_feature_ids=missing_exact,
        )

    preceding = planes[-2]
    exact_child_ids = {
        child_id
        for child_id, parent_id in parent_edges
        if parent_id in terminal_ids
    }
    by_id = overlaps.by_id()
    preceding_components = _support_components_of(overlaps, preceding)
    terminal_components = _support_components_of(overlaps, terminal)
    preceding_envelopes = frozenset(
        detection.detection_id
        for detection in preceding.detections
        if detection.detection_id not in exact_child_ids
        and by_id[detection.detection_id].has_envelope
    )
    terminal_envelopes = frozenset(
        detection.detection_id
        for detection in terminal.detections
        if detection.detection_id in missing_exact
        and by_id[detection.detection_id].has_envelope
    )
    candidates_by_parent: dict[str, set[str]] = {
        feature_id: set() for feature_id in missing_exact
    }
    parents_by_child: dict[str, set[str]] = {}
    for parent_id in sorted(missing_exact):
        if (
            parent_id not in terminal_envelopes
        ):  # pragma: no cover - every reviewed scale has a B3 footprint
            raise ValueError("terminal feature must carry a B3 envelope")
        parent_component = terminal_components.get(parent_id)
        if parent_component is None:
            continue
        for child_id in sorted(preceding_envelopes):
            if preceding_components.get(child_id) != parent_component or (
                frozenset((child_id, parent_id)) not in overlaps.envelope_edges
            ):
                continue
            candidates_by_parent[parent_id].add(child_id)
            parents_by_child.setdefault(child_id, set()).add(parent_id)
    accepted_parent_ids = frozenset(
        parent_id
        for parent_id, child_ids in candidates_by_parent.items()
        if len(child_ids) == 1
        and len(parents_by_child[next(iter(child_ids))]) == 1
    )
    missing_ids = {
        parent_id
        for parent_id, child_ids in candidates_by_parent.items()
        if not child_ids
    }
    ambiguous_ids = missing_exact - accepted_parent_ids - missing_ids
    return _TerminalFeaturePersistence(
        persistent_feature_ids=exact_feature_ids | accepted_parent_ids,
        exact_feature_count=len(exact_feature_ids),
        displaced_candidate_count=sum(
            len(child_ids) for child_ids in candidates_by_parent.values()
        ),
        displaced_accepted_count=len(accepted_parent_ids),
        missing_child_count=len(missing_ids),
        ambiguous_child_count=len(ambiguous_ids),
        missing_feature_ids=frozenset(missing_ids),
    )


def _resilient_missing_child_cycle_groups(
    candidate_feature_groups: list[frozenset[str]],
    persistence: _TerminalFeaturePersistence,
    attachments: _HierarchyAttachments,
    terminal: ScaleDetections,
    overlaps: HierarchyOverlaps,
) -> tuple[tuple[frozenset[str], ...], int, int]:
    """Admit one missing owned child only in an exclusive source graph."""
    component_groups = tuple(
        _components_for_feature_group(group, attachments)
        for group in candidate_feature_groups
    )
    component_occurrences = Counter(
        component_id for group in component_groups for component_id in group
    )
    support_components = _support_components_of(overlaps, terminal)
    accepted: list[frozenset[str]] = []
    candidate_count = 0
    rejected_count = 0
    for feature_group, component_group in zip(
        candidate_feature_groups,
        component_groups,
        strict=True,
    ):
        missing = feature_group - persistence.persistent_feature_ids
        if len(missing) != 1:
            continue
        missing_feature = next(iter(missing))
        if missing_feature not in persistence.missing_feature_ids:
            continue
        candidate_count += 1
        missing_owners = _components_for_feature_group(
            frozenset((missing_feature,)),
            attachments,
        )
        feature_support_components = {
            support_components.get(feature_id, 0)
            for feature_id in feature_group
        }
        exclusive_components = all(
            component_occurrences[component_id] == 1
            for component_id in component_group
        )
        if (
            len(missing_owners) == 1
            and exclusive_components
            and len(feature_support_components) == 1
            and 0 not in feature_support_components
        ):
            accepted.append(feature_group)
        else:
            rejected_count += 1
    return tuple(accepted), candidate_count, rejected_count


def _terminal_cycle_evidence(
    planes: tuple[ScaleDetections, ...],
    overlaps: HierarchyOverlaps,
    attachments: _HierarchyAttachments,
    parent_edges: tuple[tuple[str, str], ...],
) -> _TerminalCycleEvidence:
    """Construct terminal cycles only from bounded persistent features."""
    terminal = planes[-1]
    feature_groups = (
        _cycle_supported_feature_groups(
            overlaps.adjacency(
                frozenset(
                    detection.detection_id for detection in terminal.detections
                )
            )
        )
        if len(terminal.detections) >= _MINIMUM_CYCLE_DEGREE + 1
        else ()
    )
    candidates: set[frozenset[str]] = set()
    candidate_feature_groups: list[frozenset[str]] = []
    unseeded_candidate_groups: list[frozenset[str]] = []
    for feature_group in feature_groups:
        component_ids = _components_for_feature_group(
            feature_group,
            attachments,
        )
        if len(component_ids) < _MINIMUM_CYCLE_DEGREE + 1:
            continue
        candidates.add(component_ids)
        candidate_feature_groups.append(feature_group)
        if any(
            not _components_for_feature_group(
                frozenset((feature_id,)),
                attachments,
            )
            for feature_id in feature_group
        ):
            unseeded_candidate_groups.append(feature_group)
    relevant_feature_ids = (
        frozenset().union(*candidate_feature_groups)
        if (candidate_feature_groups)
        else frozenset()
    )
    persistence = _terminal_feature_persistence(
        planes,
        overlaps,
        parent_edges,
        relevant_feature_ids,
    )
    persistent_feature_groups = tuple(
        feature_group
        for feature_group in candidate_feature_groups
        if feature_group.issubset(persistence.persistent_feature_ids)
    )
    (
        resilient_feature_groups,
        resilience_candidate_count,
        resilience_rejected_count,
    ) = _resilient_missing_child_cycle_groups(
        candidate_feature_groups,
        persistence,
        attachments,
        terminal,
        overlaps,
    )
    accepted_feature_groups = tuple(
        dict.fromkeys((*persistent_feature_groups, *resilient_feature_groups))
    )
    accepted = {
        _components_for_feature_group(feature_group, attachments)
        for feature_group in accepted_feature_groups
    }
    resilient_groups = tuple(
        _components_for_feature_group(feature_group, attachments)
        for feature_group in resilient_feature_groups
    )
    accepted_feature_group_set = set(accepted_feature_groups)
    unseeded_accepted_count = sum(
        feature_group in accepted_feature_group_set
        for feature_group in unseeded_candidate_groups
    )
    ordered = tuple(sorted(accepted, key=lambda item: tuple(sorted(item))))
    return _TerminalCycleEvidence(
        groups=ordered,
        candidate_count=len(candidates),
        rejected_count=len(candidates - accepted),
        exact_feature_count=persistence.exact_feature_count,
        displaced_candidate_count=persistence.displaced_candidate_count,
        displaced_accepted_count=persistence.displaced_accepted_count,
        missing_child_count=persistence.missing_child_count,
        ambiguous_child_count=persistence.ambiguous_child_count,
        pre_eligibility_candidate_count=len(feature_groups),
        unseeded_candidate_count=len(unseeded_candidate_groups),
        unseeded_persistent_accepted_count=unseeded_accepted_count,
        unseeded_persistence_rejected_count=(
            len(unseeded_candidate_groups) - unseeded_accepted_count
        ),
        missing_child_resilience_candidate_count=resilience_candidate_count,
        missing_child_resilience_parent_count=len(resilient_feature_groups),
        missing_child_resilience_rejected_count=resilience_rejected_count,
        missing_child_resilience_groups=resilient_groups,
    )


def _filter_scale_aware_parents_by_connected_support(
    evidence: _ScaleAwareParentEvidence,
    connected_support: _ConnectedSupportEvidence,
) -> _ScaleAwareParentEvidence:
    """Forbid geometry-only parent groups without persistent signal."""
    retained = tuple(
        group
        for group in evidence.groups
        if group in evidence.self_corroborated_groups
        or any(group.issubset(parent) for parent in connected_support.groups)
    )
    discarded = set(evidence.groups) - set(retained)
    discarded_occurrences = sum(
        count
        for group, count in evidence.accepted_candidate_occurrences
        if group in discarded
    )
    return _ScaleAwareParentEvidence(
        groups=retained,
        candidate_count=evidence.candidate_count,
        rejected_ambiguity_count=(
            evidence.rejected_ambiguity_count + discarded_occurrences
        ),
        per_scale_candidate_counts=evidence.per_scale_candidate_counts,
        accepted_candidate_occurrences=tuple(
            (group, count)
            for group, count in evidence.accepted_candidate_occurrences
            if group in retained
        ),
        self_corroborated_groups=evidence.self_corroborated_groups
        & frozenset(retained),
        feature_influence_candidate_count=(
            evidence.feature_influence_candidate_count
        ),
    )


def _hierarchy_groups(
    records: tuple[DetectionComponentRecord, ...],
    attachments: _HierarchyAttachments,
    feature_index: Mapping[str, tuple[int, int]],
    parents_by_id: Mapping[str, tuple[str, ...]],
) -> tuple[frozenset[str], ...]:
    """Group owners at their first corroborated shared feature."""
    groups: list[frozenset[str]] = []
    unassigned = {
        record.component_id
        for record in records
        if record.component_id not in attachments.ambiguous_component_ids
    }
    for feature_id in sorted(
        feature_index,
        key=lambda item: (feature_index[item][0], item),
    ):
        members = {
            component_id
            for component_id in unassigned
            if feature_id
            in attachments.lineages_by_component.get(component_id, ())
        }
        if len(members) < _MINIMUM_SOURCE_MEMBERS:
            continue
        corroborated = feature_id in parents_by_id or all(
            attachments.features_by_component[component_id] == (feature_id,)
            for component_id in members
        )
        if not corroborated:
            continue
        groups.append(frozenset(members))
        unassigned.difference_update(members)
    groups.extend(frozenset((component_id,)) for component_id in unassigned)
    groups.extend(
        frozenset((component_id,))
        for component_id in attachments.ambiguous_component_ids
    )
    return tuple(groups)


def _apply_scale_aware_parent_groups(
    exact_groups: tuple[frozenset[str], ...],
    evidence: _ScaleAwareParentEvidence,
) -> tuple[tuple[frozenset[str], ...], _ScaleAwareParentEvidence]:
    """Reconcile parents with exact groups before membership and telemetry."""
    singleton_ids = {
        next(iter(group)) for group in exact_groups if len(group) == 1
    }
    accepted = tuple(
        group for group in evidence.groups if group.issubset(singleton_ids)
    )
    discarded = set(evidence.groups) - set(accepted)
    discarded_occurrences = sum(
        count
        for group, count in evidence.accepted_candidate_occurrences
        if group in discarded
    )
    applied_evidence = _ScaleAwareParentEvidence(
        groups=accepted,
        candidate_count=evidence.candidate_count,
        rejected_ambiguity_count=(
            evidence.rejected_ambiguity_count + discarded_occurrences
        ),
        per_scale_candidate_counts=evidence.per_scale_candidate_counts,
        accepted_candidate_occurrences=tuple(
            (group, count)
            for group, count in evidence.accepted_candidate_occurrences
            if group in accepted
        ),
        self_corroborated_groups=evidence.self_corroborated_groups
        & frozenset(accepted),
        feature_influence_candidate_count=(
            evidence.feature_influence_candidate_count
        ),
    )
    grouped_ids = set().union(*accepted) if accepted else set()
    groups = (
        tuple(
            group
            for group in exact_groups
            if len(group) > 1 or group.isdisjoint(grouped_ids)
        )
        + accepted
    )
    return groups, applied_evidence


def _apply_terminal_cycle_groups(
    groups: tuple[frozenset[str], ...],
    evidence: _TerminalCycleEvidence,
) -> tuple[tuple[frozenset[str], ...], _TerminalCycleEvidence]:
    """Apply whole terminal-cycle parents without splitting exact groups."""
    current = list(groups)
    accepted_count = 0
    accepted_parents: set[frozenset[str]] = set()
    rejected_count = evidence.rejected_count
    for parent in evidence.groups:
        intersecting = [
            group for group in current if not group.isdisjoint(parent)
        ]
        if any(not group.issubset(parent) for group in intersecting):
            rejected_count += 1
            continue
        current = [group for group in current if group not in intersecting]
        current.append(parent)
        accepted_parents.add(parent)
        accepted_count += 1
    resilience_parent_count = sum(
        parent in accepted_parents
        for parent in evidence.missing_child_resilience_groups
    )
    return (
        tuple(current),
        _TerminalCycleEvidence(
            groups=evidence.groups,
            candidate_count=evidence.candidate_count,
            rejected_count=rejected_count,
            accepted_parent_count=accepted_count,
            exact_feature_count=evidence.exact_feature_count,
            displaced_candidate_count=evidence.displaced_candidate_count,
            displaced_accepted_count=evidence.displaced_accepted_count,
            missing_child_count=evidence.missing_child_count,
            ambiguous_child_count=evidence.ambiguous_child_count,
            conflict_count=rejected_count - evidence.rejected_count,
            pre_eligibility_candidate_count=(
                evidence.pre_eligibility_candidate_count
            ),
            unseeded_candidate_count=evidence.unseeded_candidate_count,
            unseeded_persistent_accepted_count=(
                evidence.unseeded_persistent_accepted_count
            ),
            unseeded_persistence_rejected_count=(
                evidence.unseeded_persistence_rejected_count
            ),
            missing_child_resilience_candidate_count=(
                evidence.missing_child_resilience_candidate_count
            ),
            missing_child_resilience_parent_count=(resilience_parent_count),
            missing_child_resilience_rejected_count=(
                evidence.missing_child_resilience_candidate_count
                - resilience_parent_count
            ),
            missing_child_resilience_groups=(
                evidence.missing_child_resilience_groups
            ),
        ),
    )


def _source_memberships(
    groups: tuple[frozenset[str], ...],
) -> tuple[CatalogueSourceMembership, ...]:
    """Return canonical stable source records for exact groups."""
    return tuple(
        sorted(
            (
                CatalogueSourceMembership(
                    source_id=_source_id(tuple(sorted(group))),
                    component_ids=tuple(sorted(group)),
                )
                for group in groups
            ),
            key=lambda item: item.source_id,
        )
    )


def constrain_source_memberships(
    association: SourceAssociationResult,
    measured_groups: tuple[frozenset[int], ...],
) -> SourceAssociationResult:
    """Apply compact-model or resolved-morphology evidence before publication.

    Unconstrained components remain separate. A hierarchy is a proposal, not
    positive evidence that a failed or deferred fit belongs to its neighbours.
    Explicit compact or resolved-morphology groups retain their membership.
    """
    by_label = {
        item.label_value: item.component_id for item in association.components
    }
    labels = [value for group in measured_groups for value in group]
    if any(not group for group in measured_groups) or len(labels) != len(
        set(labels)
    ):
        raise ValueError("compact model groups must be nonempty and disjoint")
    if not set(labels) <= by_label.keys():
        raise ValueError("compact model group has an unknown component label")
    constrained = {
        by_label[value] for group in measured_groups for value in group
    }
    groups = tuple(
        frozenset((item.component_id,))
        for item in association.components
        if item.component_id not in constrained
    ) + tuple(
        frozenset(by_label[value] for value in group)
        for group in measured_groups
    )
    memberships = _source_memberships(groups)
    diagnostics = association.hierarchy_diagnostics
    if diagnostics is not None:
        diagnostics = replace(
            diagnostics,
            catalogue_source_count=len(memberships),
            membership_size_histogram=tuple(
                sorted(
                    Counter(
                        len(item.component_ids) for item in memberships
                    ).items()
                )
            ),
            unique_convergence_count=sum(
                len(item.component_ids) > 1 for item in memberships
            ),
        )
    return replace(
        association,
        memberships=memberships,
        ambiguous_component_ids=tuple(
            value
            for value in association.ambiguous_component_ids
            if value not in constrained
        ),
        hierarchy_diagnostics=diagnostics,
    )


def _hierarchy_diagnostics(  # noqa: PLR0913, PLR0917
    memberships: tuple[CatalogueSourceMembership, ...],
    planes: tuple[ScaleDetections, ...],
    parent_edges: tuple[tuple[str, str], ...],
    attachments: _HierarchyAttachments,
    scale_aware_parents: _ScaleAwareParentEvidence,
    connected_support: _ConnectedSupportEvidence,
    terminal_cycles: _TerminalCycleEvidence,
) -> SourceHierarchyDiagnostics:
    """Build compact deterministic activation evidence."""
    histogram = Counter(len(item.component_ids) for item in memberships)
    return SourceHierarchyDiagnostics(
        direct_component_count=sum(
            len(item.component_ids) for item in memberships
        ),
        catalogue_source_count=len(memberships),
        membership_size_histogram=tuple(sorted(histogram.items())),
        unattached_component_count=attachments.unattached_count,
        multiple_finest_feature_attachment_count=(
            attachments.multiple_attachment_count
        ),
        branched_lineage_count=attachments.branched_lineage_count,
        no_common_convergence_count=(attachments.no_common_convergence_count),
        unique_convergence_count=sum(
            len(item.component_ids) > 1 for item in memberships
        ),
        per_scale_feature_counts=tuple(
            (plane.scale_order, len(plane.detections)) for plane in planes
        ),
        adjacent_scale_parent_edge_count=len(parent_edges),
        scale_aware_parent_candidate_count=(
            scale_aware_parents.candidate_count
        ),
        persistent_parent_count=len(scale_aware_parents.groups),
        rejected_parent_ambiguity_count=(
            scale_aware_parents.rejected_ambiguity_count
        ),
        per_scale_parent_candidate_counts=(
            scale_aware_parents.per_scale_candidate_counts
        ),
        connected_support_candidate_count=(connected_support.candidate_count),
        rejected_connected_support_ambiguity_count=(
            connected_support.rejected_ambiguity_count
        ),
        terminal_cycle_candidate_count=terminal_cycles.candidate_count,
        terminal_cycle_parent_count=terminal_cycles.accepted_parent_count,
        rejected_terminal_cycle_count=terminal_cycles.rejected_count,
        terminal_persistence_exact_feature_count=(
            terminal_cycles.exact_feature_count
        ),
        terminal_persistence_displaced_candidate_count=(
            terminal_cycles.displaced_candidate_count
        ),
        terminal_persistence_displaced_accepted_count=(
            terminal_cycles.displaced_accepted_count
        ),
        terminal_persistence_missing_child_count=(
            terminal_cycles.missing_child_count
        ),
        terminal_persistence_ambiguous_child_count=(
            terminal_cycles.ambiguous_child_count
        ),
        terminal_persistence_conflict_count=terminal_cycles.conflict_count,
        terminal_cycle_pre_eligibility_candidate_count=(
            terminal_cycles.pre_eligibility_candidate_count
        ),
        terminal_cycle_unseeded_candidate_count=(
            terminal_cycles.unseeded_candidate_count
        ),
        terminal_cycle_unseeded_persistent_accepted_count=(
            terminal_cycles.unseeded_persistent_accepted_count
        ),
        terminal_cycle_unseeded_persistence_rejected_count=(
            terminal_cycles.unseeded_persistence_rejected_count
        ),
        persistent_feature_influence_candidate_count=(
            scale_aware_parents.feature_influence_candidate_count
        ),
        persistent_feature_influence_parent_count=len(
            scale_aware_parents.self_corroborated_groups
        ),
        terminal_cycle_missing_child_resilience_candidate_count=(
            terminal_cycles.missing_child_resilience_candidate_count
        ),
        terminal_cycle_missing_child_resilience_parent_count=(
            terminal_cycles.missing_child_resilience_parent_count
        ),
        terminal_cycle_missing_child_resilience_rejected_count=(
            terminal_cycles.missing_child_resilience_rejected_count
        ),
    )


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


def associate_components_by_multiscale_hierarchy(
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    scale_detection_planes: tuple[ScaleDetectionPlane, ...],
    valid_pixels: npt.ArrayLike,
    *,
    significant_multiscale_support: npt.ArrayLike | None = None,
) -> SourceAssociationResult:
    """Partition direct owners at a corroborated common scale feature.

    Direct component labels are immutable. Each owner attaches to the finest
    exact undilated scale features it intersects, then follows only unique
    adjacent-scale overlap parents. Owners group at their finest shared
    feature only when that feature persists to a parent, or when every owner
    directly attaches to the same feature. When exact sibling lineages remain
    separate, connected significant multiscale support may corroborate a
    persistent mutually unique pair or non-terminal cycle, but cannot create
    source membership by itself.
    A mutually unique adjacent-scale feature may also recover exactly one
    unresolved displaced owner when the parent and child share one direct
    anchor and two applications of the same fixed B3 footprint contain only
    that anchor and the displaced owner. This persistent feature evidence is
    self-corroborating, but it remains subject to whole-group reconciliation
    and cannot split or partially overlap an established source.
    At the last retained scale, a cycle may construct a parent when its
    constituent features have exact or mutually unique displaced children. One
    directly owned feature may lack a child without vetoing an otherwise
    persistent whole-source graph, but only when every feature shares one
    retained support component and no direct member has a competing cycle.
    A persistent feature without a direct owner may corroborate cycle geometry
    but cannot join catalogue membership, which still requires at least three
    immutable direct components. Displaced and missing-child evidence cannot
    create cycles or membership. Partial overlap with an exact group, missing
    support, branching, or conflicting convergence fails closed.
    """
    labels, planes, valid = _hierarchy_inputs(
        records,
        component_labels,
        scale_detection_planes,
        valid_pixels,
    )
    significant = _validated_significant_support(
        significant_multiscale_support,
        labels,
        valid,
    )
    return associate_from_hierarchy_overlaps(
        records,
        planes,
        summarize_hierarchy_overlaps(
            records, labels, planes, valid, significant
        ),
    )


def associate_from_hierarchy_overlaps(
    records: tuple[DetectionComponentRecord, ...],
    planes: tuple[ScaleDetections, ...],
    overlaps: HierarchyOverlaps,
) -> SourceAssociationResult:
    """Decide source membership from reduced pixel facts alone.

    Every pixel question has already been answered by the tile cores and the
    per-feature windows that produced ``overlaps``, so this step is record
    logic and cannot depend on tile geometry or completion order.
    """
    feature_index = _feature_by_id(planes)
    parent_edges = overlaps.parent_edges
    parent_sets: dict[str, set[str]] = {}
    for child_id, parent_id in parent_edges:
        child_scale = feature_index[child_id][0]
        parent_scale = feature_index[parent_id][0]
        if parent_scale != child_scale + 1:
            raise ValueError("source hierarchy parent scales must be adjacent")
        parent_sets.setdefault(child_id, set()).add(parent_id)
    parents_by_id = {
        child_id: tuple(sorted(parent_ids))
        for child_id, parent_ids in parent_sets.items()
    }

    attachments = _hierarchy_attachments(
        records,
        overlaps.finest_features_by_component,
        parents_by_id,
        feature_index,
    )
    scale_aware_parents = _scale_aware_parent_evidence(
        _ScaleAwareInputs(
            records=records,
            planes=planes,
            overlaps=overlaps,
            attachments=attachments,
            parents_by_id=parents_by_id,
            feature_index=feature_index,
        )
    )
    connected_support = _connected_support_evidence(
        overlaps.support_component_by_component,
        attachments.ambiguous_component_ids,
    )
    terminal_cycles = _terminal_cycle_evidence(
        planes,
        overlaps,
        attachments,
        parent_edges,
    )
    scale_aware_parents = _filter_scale_aware_parents_by_connected_support(
        scale_aware_parents,
        connected_support,
    )
    exact_groups = _hierarchy_groups(
        records,
        attachments,
        feature_index,
        parents_by_id,
    )
    groups, applied_scale_aware_parents = _apply_scale_aware_parent_groups(
        exact_groups,
        scale_aware_parents,
    )
    groups, applied_terminal_cycles = _apply_terminal_cycle_groups(
        groups,
        terminal_cycles,
    )
    memberships = _source_memberships(groups)
    return SourceAssociationResult(
        components=tuple(sorted(records, key=lambda item: item.component_id)),
        edges=(),
        memberships=memberships,
        ambiguous_component_ids=tuple(
            sorted(attachments.ambiguous_component_ids)
        ),
        hierarchy_diagnostics=_hierarchy_diagnostics(
            memberships,
            planes,
            parent_edges,
            attachments,
            applied_scale_aware_parents,
            connected_support,
            applied_terminal_cycles,
        ),
    )
