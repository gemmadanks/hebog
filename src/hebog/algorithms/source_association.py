# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Conservative deterministic grouping of immutable detection components."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected_component_labels

from hebog.algorithms.multiscale import residual_atrous_scale_halos_pixels
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    adjacent_scale_overlap_edges,
    associate_adjacent_scale_detections,
)
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
    signal: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    *,
    origin_yx: tuple[int, int],
) -> tuple[
    tuple[float, float],
    tuple[tuple[float, float], tuple[float, float]] | None,
]:
    """Return positive-signal centroid and exact-support covariance."""
    positive = support & np.isfinite(signal) & (signal > 0.0)
    if not bool(np.any(positive)):
        y_pixels, x_pixels = np.nonzero(support)
        return (
            float(np.mean(y_pixels)) + origin_yx[0],
            float(np.mean(x_pixels)) + origin_yx[1],
        ), None
    weights = signal[positive]
    weight = float(np.sum(weights, dtype=np.float64))
    y_pixels, x_pixels = np.nonzero(positive)
    centroid_y = float(np.sum(y_pixels * weights, dtype=np.float64) / weight)
    centroid_x = float(np.sum(x_pixels * weights, dtype=np.float64) / weight)
    centroid = (
        centroid_y + origin_yx[0],
        centroid_x + origin_yx[1],
    )
    if weights.size < _MINIMUM_SHAPE_PIXELS:
        return centroid, None
    delta_y = y_pixels - centroid_y
    delta_x = x_pixels - centroid_x
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
    for label_value in sorted(
        int(value) for value in np.unique(labels) if value > 0
    ):
        support = (labels == label_value) & valid
        local_pixels = np.column_stack(np.nonzero(support))
        first_local = tuple(int(value) for value in local_pixels[0])
        derived_reference = (
            first_local[0] + origin_yx[0],
            first_local[1] + origin_yx[1],
        )
        canonical_reference = (
            canonical_component_references_yx.get(
                label_value,
                derived_reference,
            )
            if canonical_component_references_yx is not None
            else derived_reference
        )
        if min(canonical_reference) < 0:
            raise ValueError("canonical component references must be positive")
        centroid, covariance = _positive_moment_geometry(
            signal,
            support,
            origin_yx=origin_yx,
        )
        records.append(
            DetectionComponentRecord(
                component_id=_component_id(canonical_reference),
                label_value=label_value,
                canonical_pixel_yx=canonical_reference,
                centroid_yx=centroid,
                covariance_pixels_squared=covariance,
            )
        )
    return tuple(sorted(records, key=lambda item: item.canonical_pixel_yx))


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
    planes: tuple[ScaleDetectionPlane, ...],
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
    labels: npt.NDArray[np.int64]
    planes: tuple[ScaleDetectionPlane, ...]
    valid: npt.NDArray[np.bool_]
    attachments: _HierarchyAttachments
    parents_by_id: Mapping[str, tuple[str, ...]]
    feature_index: Mapping[str, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class _FeatureInfluenceIndex:
    """Precomputed identity maps for persistent influence candidates."""

    component_id_by_label: Mapping[int, str]
    children_by_parent: Mapping[str, frozenset[str]]
    plane_by_scale: Mapping[int, ScaleDetectionPlane]
    resolved_component_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ConnectedSupportEvidence:
    """Connected persistent-support corroboration groups and census."""

    groups: tuple[frozenset[str], ...]
    candidate_count: int
    support_component_labels: npt.NDArray[np.int64]
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


def _hierarchy_attachments(
    records: tuple[DetectionComponentRecord, ...],
    labels: npt.NDArray[np.int64],
    planes: tuple[ScaleDetectionPlane, ...],
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
        attachments = _attached_finest_features(record, labels, planes)
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


def _feature_envelopes(
    plane: ScaleDetectionPlane,
    valid: npt.NDArray[np.bool_],
) -> tuple[_FeatureEnvelope, ...]:
    """Derive bounded valid envelopes from the fixed B3 filter footprint."""
    halos = residual_atrous_scale_halos_pixels()
    if plane.scale_order > len(halos):
        return ()
    radius = halos[plane.scale_order - 1]
    origin_y, origin_x = plane.origin_yx
    height, width = plane.component_labels.shape
    envelopes: list[_FeatureEnvelope] = []
    for label_value, detection in enumerate(plane.detections, start=1):
        global_y0, global_y1, global_x0, global_x1 = detection.bounds_yx
        exact_y0 = global_y0 - origin_y
        exact_y1 = global_y1 - origin_y
        exact_x0 = global_x0 - origin_x
        exact_x1 = global_x1 - origin_x
        y0 = max(0, exact_y0 - radius)
        y1 = min(height, exact_y1 + radius)
        x0 = max(0, exact_x0 - radius)
        x1 = min(width, exact_x1 + radius)
        seed = np.zeros((y1 - y0, x1 - x0), dtype=np.bool_)
        seed[
            exact_y0 - y0 : exact_y1 - y0,
            exact_x0 - x0 : exact_x1 - x0,
        ] = (
            plane.component_labels[
                exact_y0:exact_y1,
                exact_x0:exact_x1,
            ]
            == label_value
        )
        envelope = np.asarray(
            binary_dilation(
                seed,
                structure=np.ones((3, 3), dtype=np.bool_),
                iterations=radius,
                mask=valid[y0:y1, x0:x1],
            ),
            dtype=np.bool_,
        )
        envelope.setflags(write=False)
        envelopes.append(
            _FeatureEnvelope(
                feature_id=detection.detection_id,
                bounds_yx=(y0, y1, x0, x1),
                support=envelope,
            )
        )
    return tuple(envelopes)


def _envelopes_overlap(
    first: _FeatureEnvelope,
    second: _FeatureEnvelope,
) -> bool:
    """Return whether box-overlapping bounded envelopes share support."""
    first_y0, first_y1, first_x0, first_x1 = first.bounds_yx
    second_y0, second_y1, second_x0, second_x1 = second.bounds_yx
    y0 = max(first_y0, second_y0)
    y1 = min(first_y1, second_y1)
    x0 = max(first_x0, second_x0)
    x1 = min(first_x1, second_x1)
    if y0 >= y1 or x0 >= x1:
        return False
    return bool(
        np.any(
            first.support[
                y0 - first_y0 : y1 - first_y0,
                x0 - first_x0 : x1 - first_x0,
            ]
            & second.support[
                y0 - second_y0 : y1 - second_y0,
                x0 - second_x0 : x1 - second_x0,
            ]
        )
    )


def _envelope_adjacency(
    envelopes: tuple[_FeatureEnvelope, ...],
) -> dict[str, set[str]]:
    """Build a deterministic sweep-line overlap graph for bounded envelopes."""
    adjacency: dict[str, set[str]] = {
        item.feature_id: set() for item in envelopes
    }
    active: list[_FeatureEnvelope] = []
    for envelope in sorted(
        envelopes,
        key=lambda item: (item.bounds_yx[0], item.feature_id),
    ):
        y0 = envelope.bounds_yx[0]
        active = [item for item in active if item.bounds_yx[1] > y0]
        for other in active:
            if (
                other.bounds_yx[2] >= envelope.bounds_yx[3]
                or envelope.bounds_yx[2] >= other.bounds_yx[3]
                or not _envelopes_overlap(other, envelope)
            ):
                continue
            adjacency[other.feature_id].add(envelope.feature_id)
            adjacency[envelope.feature_id].add(other.feature_id)
        active.append(envelope)
    return adjacency


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
    halos = residual_atrous_scale_halos_pixels()
    # The caller supplies only envelopes returned by _feature_envelopes,
    # which omits scales without a reviewed B3 footprint.
    radius = halos[plane.scale_order - 1]
    y0, y1, x0, x1 = envelope.bounds_yx
    expanded_y0 = max(0, y0 - radius)
    expanded_y1 = min(labels.shape[0], y1 + radius)
    expanded_x0 = max(0, x0 - radius)
    expanded_x1 = min(labels.shape[1], x1 + radius)
    seed = np.zeros(
        (expanded_y1 - expanded_y0, expanded_x1 - expanded_x0),
        dtype=np.bool_,
    )
    seed[
        y0 - expanded_y0 : y1 - expanded_y0,
        x0 - expanded_x0 : x1 - expanded_x0,
    ] = envelope.support
    influence = np.asarray(
        binary_dilation(
            seed,
            structure=np.ones((3, 3), dtype=np.bool_),
            iterations=radius,
            mask=valid[
                expanded_y0:expanded_y1,
                expanded_x0:expanded_x1,
            ],
        ),
        dtype=np.bool_,
    )
    influenced_labels = np.unique(
        labels[
            expanded_y0:expanded_y1,
            expanded_x0:expanded_x1,
        ][influence]
    )
    return frozenset(
        component_id_by_label[int(label_value)]
        for label_value in influenced_labels
        if int(label_value) > 0
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
        component_id_by_label={
            record.label_value: record.component_id
            for record in inputs.records
        },
        children_by_parent={
            parent_id: frozenset(child_ids)
            for parent_id, child_ids in mutable_children.items()
        },
        plane_by_scale={plane.scale_order: plane for plane in inputs.planes},
        resolved_component_ids=frozenset(
            set(inputs.attachments.lineages_by_component)
            - set(inputs.attachments.ambiguous_component_ids)
        ),
    )


def _feature_influence_candidate(
    inputs: _ScaleAwareInputs,
    index: _FeatureInfluenceIndex,
    plane: ScaleDetectionPlane,
    feature_label: int,
    envelope: _FeatureEnvelope,
) -> frozenset[str] | None:
    """Return one exact persistent-anchor plus displaced-owner pair."""
    child_ids = index.children_by_parent.get(envelope.feature_id, frozenset())
    if len(child_ids) != 1:
        return None
    child_id = next(iter(child_ids))
    if inputs.parents_by_id.get(child_id) != (envelope.feature_id,):
        return None
    exact_ids = _feature_exact_component_ids(
        plane,
        feature_label,
        inputs.labels,
        index.component_id_by_label,
    )
    child_scale, child_label = inputs.feature_index[child_id]
    child_exact_ids = _feature_exact_component_ids(
        index.plane_by_scale[child_scale],
        child_label,
        inputs.labels,
        index.component_id_by_label,
    )
    if len(exact_ids) != 1 or child_exact_ids != exact_ids:
        return None
    influenced_ids = _feature_influence_component_ids(
        plane,
        envelope,
        inputs.labels,
        inputs.valid,
        index.component_id_by_label,
    )
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
            for feature_label, envelope in enumerate(
                _feature_envelopes(plane, inputs.valid), start=1
            )
            if (
                group := _feature_influence_candidate(
                    inputs,
                    index,
                    plane,
                    feature_label,
                    envelope,
                )
            )
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
        adjacency = _envelope_adjacency(
            _feature_envelopes(plane, inputs.valid)
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
    records: tuple[DetectionComponentRecord, ...],
    labels: npt.NDArray[np.int64],
    significant: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
    ambiguous_component_ids: frozenset[str],
) -> _ConnectedSupportEvidence:
    """Group direct owners sharing connected persistent emission support."""
    parent_labels, _ = cast(
        tuple[npt.NDArray[np.int64], int],
        connected_component_labels(
            ((labels > 0) | significant) & valid,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    parent_labels = np.asarray(parent_labels, dtype=np.int64)
    parent_labels.setflags(write=False)
    component_ids_by_parent: dict[int, set[str]] = {}
    for record in records:
        parents = tuple(
            sorted(
                int(value)
                for value in np.unique(
                    parent_labels[labels == record.label_value]
                )
                if value > 0
            )
        )
        if len(parents) != 1:
            raise ValueError(
                "each direct component must occupy one connected support "
                "parent"
            )
        component_ids_by_parent.setdefault(parents[0], set()).add(
            record.component_id
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
        support_component_labels=parent_labels,
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


def _terminal_feature_persistence(
    planes: tuple[ScaleDetectionPlane, ...],
    valid: npt.NDArray[np.bool_],
    support_component_labels: npt.NDArray[np.int64],
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
        )

    preceding = planes[-2]
    exact_child_ids = {
        child_id
        for child_id, parent_id in parent_edges
        if parent_id in terminal_ids
    }
    preceding_components = _feature_support_components(
        preceding,
        support_component_labels,
    )
    terminal_components = _feature_support_components(
        terminal,
        support_component_labels,
    )
    preceding_envelopes = {
        item.feature_id: item
        for item in _feature_envelopes(preceding, valid)
        if item.feature_id not in exact_child_ids
    }
    terminal_envelopes = {
        item.feature_id: item
        for item in _feature_envelopes(terminal, valid)
        if item.feature_id in missing_exact
    }
    candidates_by_parent: dict[str, set[str]] = {
        feature_id: set() for feature_id in missing_exact
    }
    parents_by_child: dict[str, set[str]] = {}
    for parent_id in sorted(missing_exact):
        parent_envelope = terminal_envelopes[parent_id]
        parent_component = terminal_components.get(parent_id)
        if parent_component is None:
            continue
        for child_id, child_envelope in preceding_envelopes.items():
            if preceding_components.get(
                child_id
            ) != parent_component or not _envelopes_overlap(
                child_envelope, parent_envelope
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
    )


def _terminal_cycle_evidence(
    planes: tuple[ScaleDetectionPlane, ...],
    valid: npt.NDArray[np.bool_],
    attachments: _HierarchyAttachments,
    parent_edges: tuple[tuple[str, str], ...],
    support_component_labels: npt.NDArray[np.int64],
) -> _TerminalCycleEvidence:
    """Construct terminal cycles only from bounded persistent features."""
    terminal = planes[-1]
    feature_groups = (
        _cycle_supported_feature_groups(
            _envelope_adjacency(_feature_envelopes(terminal, valid))
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
        valid,
        support_component_labels,
        parent_edges,
        relevant_feature_ids,
    )
    accepted_feature_groups = tuple(
        feature_group
        for feature_group in candidate_feature_groups
        if feature_group.issubset(persistence.persistent_feature_ids)
    )
    accepted = {
        _components_for_feature_group(feature_group, attachments)
        for feature_group in accepted_feature_groups
    }
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
        accepted_count += 1
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


def _hierarchy_diagnostics(  # noqa: PLR0913, PLR0917
    memberships: tuple[CatalogueSourceMembership, ...],
    planes: tuple[ScaleDetectionPlane, ...],
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
    )


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
    At the last retained scale, a cycle may construct a parent only when every
    constituent feature has an exact child at the preceding scale or one
    mutually unique displaced child corroborated by overlapping fixed B3
    envelopes in the same retained significant-support component. A persistent
    feature without a direct owner may corroborate cycle geometry but cannot
    join catalogue membership, which still requires at least three immutable
    direct components. Displaced evidence cannot create cycles or membership.
    Partial overlap with an exact group, missing support, branching, or
    conflicting convergence fails closed.
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
    feature_index = _feature_by_id(planes)
    parent_edges = adjacent_scale_overlap_edges(planes)
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
        labels,
        planes,
        parents_by_id,
        feature_index,
    )
    scale_aware_parents = _scale_aware_parent_evidence(
        _ScaleAwareInputs(
            records=records,
            labels=labels,
            planes=planes,
            valid=valid,
            attachments=attachments,
            parents_by_id=parents_by_id,
            feature_index=feature_index,
        )
    )
    connected_support = _connected_support_evidence(
        records,
        labels,
        significant,
        valid,
        attachments.ambiguous_component_ids,
    )
    terminal_cycles = _terminal_cycle_evidence(
        planes,
        valid,
        attachments,
        parent_edges,
        connected_support.support_component_labels,
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
