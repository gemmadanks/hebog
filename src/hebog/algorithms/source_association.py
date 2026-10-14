# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Conservative deterministic grouping of immutable detection components."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from hebog.algorithms.component_records import (
    stable_id,
    validated_component_planes,
)
from hebog.algorithms.feature_envelopes import (
    FeatureOverlaps,
    HierarchyOverlaps,
    summarize_hierarchy_overlaps,
)
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    ScaleDetections,
    associate_adjacent_scale_detections,
)
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)

_IMAGE_DIMENSIONS = 2
_SOURCE_NAMESPACE = b"phase-5-associated-source-v1\0"
_MINIMUM_SOURCE_MEMBERS = 2
_MINIMUM_CYCLE_DEGREE = 2
_MINIMUM_ADJACENT_PLANES = 2


def _source_id(component_ids: tuple[str, ...]) -> str:
    """Derive one source identity from sorted stable component membership."""
    return stable_id(
        _SOURCE_NAMESPACE,
        "source-associated",
        component_ids,
    )


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
    labels, _, valid = validated_component_planes(
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
