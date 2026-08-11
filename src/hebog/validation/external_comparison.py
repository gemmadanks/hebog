# pyright: reportUnknownArgumentType=false
"""Truth-first matching for the frozen external source-finder comparison.

This validation-only matcher deliberately differs from catalogue-to-catalogue
matching. It associates each finder independently with analytic truth,
maximizes match count, then support overlap, then centre proximity, and keeps
every eligible secondary edge so one-to-one assignment cannot hide topology
errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import hypot, isfinite
from typing import Literal, TypeAlias

import numpy as np
import numpy.typing as npt

_MINIMUM_EXTENDED_OVERLAP = Fraction(1, 10)
_COMPACT_MAXIMUM_DISTANCE_BEAMS = 0.5
_IMAGE_DIMENSIONS = 2
_LexicographicCost: TypeAlias = tuple[Fraction, float, int]


@dataclass(frozen=True, slots=True)
class AssociationObject:
    """One truth object or finder result in pixel-centred coordinates."""

    identifier: str
    object_class: Literal["compact", "extended"]
    centre_x_pixel: float
    centre_y_pixel: float
    support_label: int | None = None

    def __post_init__(self) -> None:
        """Require stable identity, finite position, and a positive label."""
        if not self.identifier:
            raise ValueError("association identifier must not be empty")
        if not isfinite(self.centre_x_pixel) or not isfinite(
            self.centre_y_pixel
        ):
            raise ValueError("association centre must be finite")
        if self.support_label is not None and self.support_label <= 0:
            raise ValueError("association support label must be positive")


@dataclass(frozen=True, slots=True)
class EligibleAssociation:
    """One retained truth-to-finder edge before primary assignment."""

    truth_identifier: str
    candidate_identifier: str
    minimum_support_overlap: float
    centre_distance_beams: float
    eligibility_reasons: tuple[
        Literal[
            "compact-half-beam-distance",
            "minimum-support-overlap",
            "centre-in-one-beam-dilation",
        ],
        ...,
    ]


@dataclass(frozen=True, slots=True)
class TruthAssociationReport:
    """Primary assignment plus the complete eligible topology graph."""

    primary_associations: tuple[EligibleAssociation, ...]
    eligible_associations: tuple[EligibleAssociation, ...]
    unmatched_truth_identifiers: tuple[str, ...]
    unmatched_candidate_identifiers: tuple[str, ...]
    split_truth_identifiers: tuple[str, ...]
    merge_candidate_identifiers: tuple[str, ...]


@dataclass(slots=True)
class _ResidualEdge:
    """One mutable residual-network edge for min-cost max-flow."""

    target: int
    reverse_index: int
    capacity: int
    cost: _LexicographicCost


def _add_cost(
    left: _LexicographicCost,
    right: _LexicographicCost,
) -> _LexicographicCost:
    """Add hierarchical matching objectives component by component."""
    return (
        left[0] + right[0],
        left[1] + right[1],
        left[2] + right[2],
    )


def _negative_cost(cost: _LexicographicCost) -> _LexicographicCost:
    """Return the exact reverse-edge objective."""
    return (-cost[0], -cost[1], -cost[2])


def _add_residual_edge(
    graph: list[list[_ResidualEdge]],
    source: int,
    target: int,
    cost: _LexicographicCost,
) -> _ResidualEdge:
    """Add one unit-capacity edge and its initially closed reverse."""
    forward = _ResidualEdge(
        target=target,
        reverse_index=len(graph[target]),
        capacity=1,
        cost=cost,
    )
    reverse = _ResidualEdge(
        target=source,
        reverse_index=len(graph[source]),
        capacity=0,
        cost=_negative_cost(cost),
    )
    graph[source].append(forward)
    graph[target].append(reverse)
    return forward


def _shortest_augmenting_path(
    graph: list[list[_ResidualEdge]],
    source: int,
    sink: int,
) -> tuple[tuple[int, int], ...] | None:
    """Find one lexicographically cheapest residual path with Bellman-Ford."""
    zero: _LexicographicCost = (Fraction(0), 0.0, 0)
    distances: list[_LexicographicCost | None] = [None] * len(graph)
    predecessors: list[tuple[int, int] | None] = [None] * len(graph)
    distances[source] = zero
    for _ in range(len(graph) - 1):
        changed = False
        for node, edges in enumerate(graph):
            distance = distances[node]
            if distance is None:
                continue
            changed |= _relax_residual_edges(
                node,
                edges,
                distance,
                distances,
                predecessors,
            )
        if not changed:
            break
    if distances[sink] is None:
        return None
    reversed_path: list[tuple[int, int]] = []
    node = sink
    while node != source:
        predecessor = predecessors[node]
        if predecessor is None:
            raise RuntimeError("residual path lacks a predecessor")
        reversed_path.append(predecessor)
        node = predecessor[0]
    return tuple(reversed(reversed_path))


def _relax_residual_edges(
    node: int,
    edges: list[_ResidualEdge],
    distance: _LexicographicCost,
    distances: list[_LexicographicCost | None],
    predecessors: list[tuple[int, int] | None],
) -> bool:
    """Relax every open edge from one Bellman-Ford node."""
    changed = False
    for edge_index, edge in enumerate(edges):
        if edge.capacity == 0:
            continue
        candidate = _add_cost(distance, edge.cost)
        predecessor = (node, edge_index)
        current_distance = distances[edge.target]
        current_predecessor = predecessors[edge.target]
        if current_distance is None or candidate < current_distance:
            distances[edge.target] = candidate
            predecessors[edge.target] = predecessor
            changed = True
        elif (
            candidate == current_distance
            and current_predecessor is not None
            and predecessor < current_predecessor
        ):
            predecessors[edge.target] = predecessor
            changed = True
    return changed


def _minimum_cost_maximum_assignment(
    truth_count: int,
    candidate_count: int,
    edges: tuple[tuple[int, int, Fraction, float], ...],
) -> set[tuple[int, int]]:
    """Solve the frozen cardinality/overlap/distance/stable-ID objectives."""
    source = 0
    first_truth = 1
    first_candidate = first_truth + truth_count
    sink = first_candidate + candidate_count
    graph: list[list[_ResidualEdge]] = [[] for _ in range(sink + 1)]
    zero: _LexicographicCost = (Fraction(0), 0.0, 0)
    for truth_index in range(truth_count):
        _add_residual_edge(graph, source, first_truth + truth_index, zero)
    for candidate_index in range(candidate_count):
        _add_residual_edge(
            graph,
            first_candidate + candidate_index,
            sink,
            zero,
        )
    forward_edges: dict[tuple[int, int], _ResidualEdge] = {}
    for stable_rank, (
        truth_index,
        candidate_index,
        overlap,
        distance,
    ) in enumerate(edges):
        stable_weight = 1 << (len(edges) - stable_rank - 1)
        forward_edges[(truth_index, candidate_index)] = _add_residual_edge(
            graph,
            first_truth + truth_index,
            first_candidate + candidate_index,
            (-overlap, distance, -stable_weight),
        )
    while True:
        path = _shortest_augmenting_path(graph, source, sink)
        if path is None:
            break
        for node, edge_index in path:
            edge = graph[node][edge_index]
            reverse = graph[edge.target][edge.reverse_index]
            edge.capacity -= 1
            reverse.capacity += 1
    return {
        identity
        for identity, edge in forward_edges.items()
        if edge.capacity == 0
    }


def _validated_label_plane(
    plane: npt.ArrayLike,
    *,
    name: str,
) -> npt.NDArray[np.int64]:
    """Require one non-negative integer support-label plane."""
    array = np.asarray(plane)
    if array.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        array.dtype,
        np.integer,
    ):
        raise ValueError(f"{name} must be a two-dimensional integer array")
    if np.any(array < 0):
        raise ValueError(f"{name} must contain non-negative labels")
    return np.asarray(array, dtype=np.int64)


def _support_mask(
    item: AssociationObject,
    plane: npt.NDArray[np.int64],
    *,
    role: str,
) -> npt.NDArray[np.bool_]:
    """Resolve one declared support label and reject an empty label."""
    label = item.support_label
    if label is None:
        return np.zeros(plane.shape, dtype=np.bool_)
    support = np.asarray(plane == label, dtype=np.bool_)
    if not np.any(support):
        raise ValueError(
            f"{role} {item.identifier!r} support label {label} is absent"
        )
    return support


def _extended_edge(
    candidate: AssociationObject,
    truth_support: npt.NDArray[np.bool_],
    candidate_support: npt.NDArray[np.bool_] | None,
    *,
    beam_fwhm_pixels: float,
) -> tuple[Fraction, tuple[str, ...]]:
    """Evaluate the two frozen extended-object eligibility clauses."""
    overlap = Fraction(0)
    reasons: list[str] = []
    if candidate_support is not None and np.any(candidate_support):
        intersection = int(np.count_nonzero(truth_support & candidate_support))
        smaller_area = min(
            int(np.count_nonzero(truth_support)),
            int(np.count_nonzero(candidate_support)),
        )
        overlap = Fraction(intersection, smaller_area)
        if overlap >= _MINIMUM_EXTENDED_OVERLAP:
            reasons.append("minimum-support-overlap")
    y_pixels, x_pixels = np.nonzero(truth_support)
    squared_distance = np.square(
        x_pixels - candidate.centre_x_pixel
    ) + np.square(y_pixels - candidate.centre_y_pixel)
    if float(np.min(squared_distance)) <= beam_fwhm_pixels**2:
        reasons.append("centre-in-one-beam-dilation")
    return overlap, tuple(reasons)


def _require_unique_identifiers(
    objects: tuple[AssociationObject, ...],
    *,
    role: str,
) -> None:
    """Keep stable-ID tie breaking well-defined."""
    identifiers = tuple(item.identifier for item in objects)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{role} identifiers must be unique")


def match_truth_to_finder(
    truth_objects: tuple[AssociationObject, ...],
    candidate_objects: tuple[AssociationObject, ...],
    *,
    beam_fwhm_pixels: float,
    truth_label_plane: npt.ArrayLike | None = None,
    candidate_label_plane: npt.ArrayLike | None = None,
) -> TruthAssociationReport:
    """Associate one finder independently with truth under Step 2C-P rules."""
    if not isfinite(beam_fwhm_pixels) or beam_fwhm_pixels <= 0:
        raise ValueError("beam FWHM must be finite and positive")
    truth = tuple(sorted(truth_objects, key=lambda item: item.identifier))
    candidates = tuple(
        sorted(candidate_objects, key=lambda item: item.identifier)
    )
    _require_unique_identifiers(truth, role="truth")
    _require_unique_identifiers(candidates, role="candidate")
    has_extended_truth = any(item.object_class == "extended" for item in truth)
    if has_extended_truth and truth_label_plane is None:
        raise ValueError("extended matching requires a truth label plane")
    truth_labels = (
        _validated_label_plane(truth_label_plane, name="truth label plane")
        if truth_label_plane is not None
        else None
    )
    candidate_labels = (
        _validated_label_plane(
            candidate_label_plane,
            name="candidate label plane",
        )
        if candidate_label_plane is not None
        else None
    )
    if (
        truth_labels is not None
        and candidate_labels is not None
        and truth_labels.shape != candidate_labels.shape
    ):
        raise ValueError(
            "truth and candidate label planes must have one shape"
        )

    retained: list[EligibleAssociation] = []
    solver_edges: list[tuple[int, int, Fraction, float]] = []
    for truth_index, truth_item in enumerate(truth):
        truth_support = None
        if truth_item.object_class == "extended":
            if truth_labels is None or truth_item.support_label is None:
                raise ValueError(
                    "extended truth "
                    f"{truth_item.identifier!r} requires support"
                )
            truth_support = _support_mask(
                truth_item,
                truth_labels,
                role="truth",
            )
        for candidate_index, candidate_item in enumerate(candidates):
            distance = (
                hypot(
                    candidate_item.centre_x_pixel - truth_item.centre_x_pixel,
                    candidate_item.centre_y_pixel - truth_item.centre_y_pixel,
                )
                / beam_fwhm_pixels
            )
            overlap = Fraction(0)
            if truth_item.object_class == "compact":
                reasons: tuple[str, ...] = (
                    ("compact-half-beam-distance",)
                    if distance <= _COMPACT_MAXIMUM_DISTANCE_BEAMS
                    else ()
                )
            else:
                assert truth_support is not None
                candidate_support = (
                    _support_mask(
                        candidate_item,
                        candidate_labels,
                        role="candidate",
                    )
                    if candidate_labels is not None
                    and candidate_item.support_label is not None
                    else None
                )
                overlap, reasons = _extended_edge(
                    candidate_item,
                    truth_support,
                    candidate_support,
                    beam_fwhm_pixels=beam_fwhm_pixels,
                )
            if not reasons:
                continue
            retained.append(
                EligibleAssociation(
                    truth_identifier=truth_item.identifier,
                    candidate_identifier=candidate_item.identifier,
                    minimum_support_overlap=float(overlap),
                    centre_distance_beams=distance,
                    eligibility_reasons=tuple(reasons),  # type: ignore[arg-type]
                )
            )
            solver_edges.append(
                (truth_index, candidate_index, overlap, distance)
            )
    primary_indices = _minimum_cost_maximum_assignment(
        len(truth),
        len(candidates),
        tuple(solver_edges),
    )
    retained_lookup = {
        (item.truth_identifier, item.candidate_identifier): item
        for item in retained
    }
    primary = tuple(
        retained_lookup[
            (
                truth[truth_index].identifier,
                candidates[candidate_index].identifier,
            )
        ]
        for truth_index, candidate_index in sorted(primary_indices)
    )
    matched_truth = {item.truth_identifier for item in primary}
    matched_candidates = {item.candidate_identifier for item in primary}
    truth_degrees = {
        item.identifier: sum(
            edge.truth_identifier == item.identifier for edge in retained
        )
        for item in truth
    }
    candidate_degrees = {
        item.identifier: sum(
            edge.candidate_identifier == item.identifier for edge in retained
        )
        for item in candidates
    }
    return TruthAssociationReport(
        primary_associations=primary,
        eligible_associations=tuple(
            sorted(
                retained,
                key=lambda item: (
                    item.truth_identifier,
                    item.candidate_identifier,
                ),
            )
        ),
        unmatched_truth_identifiers=tuple(
            item.identifier
            for item in truth
            if item.identifier not in matched_truth
        ),
        unmatched_candidate_identifiers=tuple(
            item.identifier
            for item in candidates
            if item.identifier not in matched_candidates
        ),
        split_truth_identifiers=tuple(
            identifier
            for identifier, degree in truth_degrees.items()
            if degree > 1
        ),
        merge_candidate_identifiers=tuple(
            identifier
            for identifier, degree in candidate_degrees.items()
            if degree > 1
        ),
    )
