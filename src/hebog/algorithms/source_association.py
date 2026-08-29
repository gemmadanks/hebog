# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Conservative deterministic grouping of immutable detection components."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as connected_component_labels

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
) -> tuple[npt.NDArray[np.int64], tuple[ScaleDetectionPlane, ...]]:
    """Validate direct owners and their aligned scale-feature hierarchy."""
    labels, _, _ = _validated_planes(
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
    return labels, ordered


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


def _hierarchy_diagnostics(
    records: tuple[DetectionComponentRecord, ...],
    memberships: tuple[CatalogueSourceMembership, ...],
    planes: tuple[ScaleDetectionPlane, ...],
    parent_edges: tuple[tuple[str, str], ...],
    attachments: _HierarchyAttachments,
) -> SourceHierarchyDiagnostics:
    """Build compact deterministic activation evidence."""
    histogram = Counter(len(item.component_ids) for item in memberships)
    return SourceHierarchyDiagnostics(
        direct_component_count=len(records),
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
    )


def associate_components_by_multiscale_hierarchy(
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    scale_detection_planes: tuple[ScaleDetectionPlane, ...],
    valid_pixels: npt.ArrayLike,
) -> SourceAssociationResult:
    """Partition direct owners at a corroborated common scale feature.

    Direct component labels are immutable. Each owner attaches to the finest
    exact undilated scale features it intersects, then follows only unique
    adjacent-scale overlap parents. Owners group at their finest shared
    feature only when that feature persists to a parent, or when every owner
    directly attaches to the same feature. Missing, branched, or unconverged
    lineage remains a flagged singleton.
    """
    labels, planes = _hierarchy_inputs(
        records,
        component_labels,
        scale_detection_planes,
        valid_pixels,
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
    memberships = _source_memberships(
        _hierarchy_groups(
            records,
            attachments,
            feature_index,
            parents_by_id,
        )
    )
    return SourceAssociationResult(
        components=tuple(sorted(records, key=lambda item: item.component_id)),
        edges=(),
        memberships=memberships,
        ambiguous_component_ids=tuple(
            sorted(attachments.ambiguous_component_ids)
        ),
        hierarchy_diagnostics=_hierarchy_diagnostics(
            records,
            memberships,
            planes,
            parent_edges,
            attachments,
        ),
    )
