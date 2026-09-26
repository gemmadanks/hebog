# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Owner connectivity decided from tile cores, exactly.

The support pass asks two questions of every owner that no bounded
neighbourhood answers: whether cleanup splits its refined support, and which
earlier published regions bridge the parts of its persistent support. Both
are about the connected components of one label's pixels, and a component
of one label connects only through pixels of that label, so the island
reconciliation, which joins any two touching mask pixels, cannot answer
them for owners that touch each other.

These functions answer them for an owner too wide to read at once. Each core
labels its own same-label components and keeps only their labels and the
component on each core-edge pixel; components join where they meet across
the edges of the cores that were observed; and the decisions are taken over
the joined components, exactly as
:func:`~hebog.algorithms.extended_measurement.owner_support_is_split` and
:func:`~hebog.algorithms.extended_measurement.preserve_owner_publication_bridges`
take them over a window holding the whole owner.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as connected_component_labels

from hebog.algorithms.label_groups import label_extents
from hebog.algorithms.labelling import TileBoundaryLabels
from hebog.data_models.partitioning import TilePartition

type ComponentKey = tuple[str, int]
"""One core's tile identifier and a component number local to that core."""

_EIGHT_CONNECTED = np.ones((3, 3), dtype=np.int8)
_MINIMUM_BRIDGE_TOUCH_COUNT = 2


@dataclass(frozen=True, slots=True)
class LabelComponentSummary:
    """One core's components, reduced to their labels and edge pixels.

    ``labels[k - 1]`` is the label component ``k`` carries, and ``edges``
    holds the component on every pixel of the core's four edges, 0 where
    there is none. That is all a join across cores needs.
    """

    partition: TilePartition
    labels: tuple[int, ...]
    edges: TileBoundaryLabels

    def component_keys(self) -> tuple[ComponentKey, ...]:
        """Name every component this core holds."""
        tile_id = self.partition.tile_id
        return tuple(
            (tile_id, local) for local in range(1, len(self.labels) + 1)
        )


@dataclass(frozen=True, slots=True)
class LabelComponents:
    """One core's same-label eight-connected components.

    ``components`` numbers them from one: label by label in ascending order,
    and in raster order within a label, so a core always numbers the same
    plane the same way. ``labels[k - 1]`` is the label of component ``k``.
    """

    partition: TilePartition
    components: npt.NDArray[np.int32]
    labels: tuple[int, ...]

    def summary(self) -> LabelComponentSummary:
        """Return the labels and edge pixels, which is all a join needs."""
        components = self.components
        return LabelComponentSummary(
            partition=self.partition,
            labels=self.labels,
            edges=TileBoundaryLabels(
                top=components[0, :].copy(),
                bottom=components[-1, :].copy(),
                left=components[:, 0].copy(),
                right=components[:, -1].copy(),
            ),
        )

    def label_of(self) -> npt.NDArray[np.int64]:
        """Return a lookup from component number to label, 0 for none."""
        return np.asarray((0, *self.labels), dtype=np.int64)


def label_components(
    label_core: npt.NDArray[np.int32],
    partition: TilePartition,
) -> LabelComponents:
    """Label every same-label eight-connected component of one core.

    Each label is labelled inside its own bounds, so the cost follows the
    labels' extents rather than the core times the number of labels.

    Raises:
        ValueError: If the plane is not the partition's core shape.
    """
    plane = np.asarray(label_core, dtype=np.int32)
    if plane.shape != partition.core_bounds.shape_yx:
        raise ValueError("owner labels must cover the partition's core")
    components = np.zeros(plane.shape, dtype=np.int32)
    labels: list[int] = []
    extents = label_extents(plane)
    for value, y_start, y_stop, x_start, x_stop in zip(
        extents.values,
        extents.y_start,
        extents.y_stop,
        extents.x_start,
        extents.x_stop,
        strict=True,
    ):
        window = (
            slice(int(y_start), int(y_stop)),
            slice(int(x_start), int(x_stop)),
        )
        local, count = cast(
            "tuple[npt.NDArray[np.int32], int]",
            connected_component_labels(
                plane[window] == value, structure=_EIGHT_CONNECTED
            ),
        )
        components[window] = np.where(
            local > 0, local + len(labels), components[window]
        )
        labels.extend([int(value)] * count)
    return LabelComponents(
        partition=partition,
        components=components,
        labels=tuple(labels),
    )


def _edge(edges: TileBoundaryLabels, side: str) -> npt.NDArray[np.int32]:
    """Return the components along one named edge of a core."""
    return {
        "top": edges.top,
        "bottom": edges.bottom,
        "left": edges.left,
        "right": edges.right,
    }[side]


# A neighbour along a side meets every edge pixel with the three facing it;
# a diagonal neighbour meets one corner pixel with its own.
_SIDES = (
    ((0, 1), "right", "left"),
    ((0, -1), "left", "right"),
    ((1, 0), "bottom", "top"),
    ((-1, 0), "top", "bottom"),
)
_CORNERS = (
    ((1, 1), ("bottom", -1), ("top", 0)),
    ((1, -1), ("bottom", 0), ("top", -1)),
    ((-1, 1), ("top", -1), ("bottom", 0)),
    ((-1, -1), ("top", 0), ("bottom", -1)),
)


def _facing_pairs(
    first: LabelComponentSummary,
    first_edge: npt.NDArray[np.int32],
    second: LabelComponentSummary,
    second_edge: npt.NDArray[np.int32],
    offsets: tuple[int, ...],
) -> set[tuple[ComponentKey, ComponentKey]]:
    """Pair the same-label components on two facing edges."""
    first_labels = np.asarray((0, *first.labels), dtype=np.int64)
    second_labels = np.asarray((0, *second.labels), dtype=np.int64)
    pairs: set[tuple[ComponentKey, ComponentKey]] = set()
    for offset in offsets:
        if offset > 0:
            left, right = first_edge[:-offset], second_edge[offset:]
        elif offset < 0:
            left, right = first_edge[-offset:], second_edge[:offset]
        else:
            left, right = first_edge, second_edge
        touching = (
            (left > 0)
            & (right > 0)
            & (first_labels[left] == second_labels[right])
        )
        if not bool(np.any(touching)):
            continue
        for mine, theirs in np.unique(
            np.column_stack((left[touching], right[touching])), axis=0
        ):
            pairs.add(
                (
                    (first.partition.tile_id, int(mine)),
                    (second.partition.tile_id, int(theirs)),
                )
            )
    return pairs


def touching_across_cores(
    first: Sequence[LabelComponentSummary],
    second: Sequence[LabelComponentSummary],
) -> frozenset[tuple[ComponentKey, ComponentKey]]:
    """Return pairs of same-label components that touch across a core edge.

    The first component of each pair comes from ``first`` and the second
    from a neighbouring core of ``second``, in any direction, so the pairs
    between two planes are all found once and those within one plane twice.
    Only the cores given are consulted: a core that holds none of the labels
    need not be observed at all.
    """
    by_index = {
        (summary.partition.tile_y_index, summary.partition.tile_x_index): (
            summary
        )
        for summary in second
    }
    pairs: set[tuple[ComponentKey, ComponentKey]] = set()
    for summary in first:
        y_index = summary.partition.tile_y_index
        x_index = summary.partition.tile_x_index
        for (dy, dx), mine, theirs in _SIDES:
            neighbour = by_index.get((y_index + dy, x_index + dx))
            if neighbour is not None:
                pairs |= _facing_pairs(
                    summary,
                    _edge(summary.edges, mine),
                    neighbour,
                    _edge(neighbour.edges, theirs),
                    (-1, 0, 1),
                )
        for (dy, dx), (mine, own_corner), (theirs, facing) in _CORNERS:
            neighbour = by_index.get((y_index + dy, x_index + dx))
            if neighbour is not None:
                pairs |= _facing_pairs(
                    summary,
                    _edge(summary.edges, mine)[[own_corner]],
                    neighbour,
                    _edge(neighbour.edges, theirs)[[facing]],
                    (0,),
                )
    return frozenset(pairs)


def touching_within_core(
    first: LabelComponents,
    second: LabelComponents,
) -> frozenset[tuple[int, int]]:
    """Return pairs of same-label components of two planes that touch.

    Both planes cover one core, and a pixel touches its eight neighbours.
    """
    height, width = first.components.shape
    first_labels = first.label_of()
    second_labels = second.label_of()
    padded = np.pad(second.components, 1)
    first_owners = first_labels[first.components]
    pairs: set[tuple[int, int]] = set()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            neighbour = padded[
                1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width
            ]
            touching = (
                (first.components > 0)
                & (neighbour > 0)
                & (first_owners == second_labels[neighbour])
            )
            if not bool(np.any(touching)):
                continue
            pairs.update(
                (int(mine), int(theirs))
                for mine, theirs in np.unique(
                    np.column_stack(
                        (first.components[touching], neighbour[touching])
                    ),
                    axis=0,
                )
            )
    return frozenset(pairs)


def join_components[Key: Hashable](
    keys: Iterable[Key],
    touching: Iterable[tuple[Key, Key]],
) -> dict[Key, Key]:
    """Return every component's root once each touching pair is joined.

    Two components share a root exactly when a chain of touching pairs links
    them; which member is the root does not matter, only that it is shared.
    """
    parent: dict[Key, Key] = {key: key for key in keys}

    def root(key: Key) -> Key:
        """Follow one key to its root, compressing the path."""
        top = key
        while parent[top] != top:
            top = parent[top]
        while parent[key] != top:
            parent[key], key = top, parent[key]
        return top

    for first, second in touching:
        first_root, second_root = root(first), root(second)
        if first_root != second_root:
            parent[second_root] = first_root
    return {key: root(key) for key in parent}


@dataclass(frozen=True, slots=True)
class _Joined:
    """Every component's root, and the roots each label holds."""

    roots: dict[ComponentKey, ComponentKey]
    by_label: dict[int, set[ComponentKey]]


def _joined(summaries: Sequence[LabelComponentSummary]) -> _Joined:
    """Join one plane's components across the edges of the given cores."""
    roots = join_components(
        (key for summary in summaries for key in summary.component_keys()),
        touching_across_cores(summaries, summaries),
    )
    by_label: dict[int, set[ComponentKey]] = {}
    for summary in summaries:
        for key, label_value in zip(
            summary.component_keys(), summary.labels, strict=True
        ):
            by_label.setdefault(label_value, set()).add(roots[key])
    return _Joined(roots=roots, by_label=by_label)


def split_owners(
    summaries: Sequence[LabelComponentSummary],
) -> frozenset[int]:
    """Return the labels whose pixels fall into several joined components.

    The cores must hold every pixel of each label they carry. This is
    :func:`~hebog.algorithms.extended_measurement.owner_support_is_split`
    for every label at once.
    """
    return frozenset(
        label_value
        for label_value, roots in _joined(summaries).by_label.items()
        if len(roots) > 1
    )


@dataclass(frozen=True, slots=True)
class OwnerBridgePlanes:
    """One core's base and candidate components for the owners it holds.

    The base is each owner's persistent support; the candidates are its
    previously published pixels outside that support. They stay on the
    task that labelled them.
    """

    base: LabelComponents
    candidates: LabelComponents


@dataclass(frozen=True, slots=True)
class OwnerBridgeCore:
    """What one core observed of the owners' bridge question, safe to return.

    ``touching`` pairs the candidate and base components that touch inside
    the core, and ``base_holding_previous`` names the base components holding
    a previously published pixel of their owner.
    """

    base: LabelComponentSummary
    candidates: LabelComponentSummary
    touching: tuple[tuple[int, int], ...]
    base_holding_previous: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class OwnerBridgeShare:
    """The components one core adds to their owners or clears from them."""

    added: tuple[int, ...]
    cleared: tuple[int, ...]


def owner_bridge_planes(
    persistent_core: npt.NDArray[np.int32],
    previous_core: npt.NDArray[np.int32],
    owners: Iterable[int],
    partition: TilePartition,
) -> OwnerBridgePlanes:
    """Label one core's base and candidate components for chosen owners.

    ``persistent_core`` is the persistent support the bridge rule refines
    and ``previous_core`` the earlier publication, both over one core. An
    owner's published pixel carries that owner or nothing in the persistent
    plane, so its candidates are its published pixels the plane leaves empty.
    """
    chosen = np.asarray(sorted(owners), dtype=np.int64)
    persistent = np.asarray(persistent_core, dtype=np.int32)
    previous = np.asarray(previous_core, dtype=np.int32)
    return OwnerBridgePlanes(
        base=label_components(
            np.where(np.isin(persistent, chosen), persistent, 0).astype(
                np.int32, copy=False
            ),
            partition,
        ),
        candidates=label_components(
            np.where(
                np.isin(previous, chosen) & (persistent == 0), previous, 0
            ).astype(np.int32, copy=False),
            partition,
        ),
    )


def observe_owner_bridges(
    planes: OwnerBridgePlanes,
    previous_core: npt.NDArray[np.int32],
) -> OwnerBridgeCore:
    """Reduce one core's bridge components to what a decision needs."""
    base = planes.base.components
    holding = (base > 0) & (
        np.asarray(previous_core) == planes.base.label_of()[base]
    )
    return OwnerBridgeCore(
        base=planes.base.summary(),
        candidates=planes.candidates.summary(),
        touching=tuple(
            sorted(touching_within_core(planes.candidates, planes.base))
        ),
        base_holding_previous=tuple(
            int(local) for local in np.unique(base[holding])
        ),
    )


def decide_owner_bridges(
    cores: Sequence[OwnerBridgeCore],
) -> tuple[dict[str, OwnerBridgeShare], frozenset[int]]:
    """Apply the owner bridge rule over joined components, owner by owner.

    A candidate touching two parts of its owner's base bridges them. If the
    base and its bridges are connected they are published; otherwise the
    part holding the owner's earlier pixels is kept, with every candidate it
    holds, and every other part is cleared. That is
    :func:`~hebog.algorithms.extended_measurement.preserve_owner_publication_bridges`,
    whose connected components here are the joined base and candidate
    components and the touching pairs between them: two candidates never
    touch, and neither do two base parts, or each would be one component.

    Returns:
        Each core's share of the decisions, for the cores that change, and
        the owners whose support changes.

    Raises:
        ValueError: If an owner's earlier pixels lie in several parts that
            nothing reconnects, which the window rule refuses too.
    """
    bases = _joined(tuple(core.base for core in cores))
    candidates = _joined(tuple(core.candidates for core in cores))
    touched = _touched(cores, bases.roots, candidates.roots)
    holding = {
        bases.roots[(core.base.partition.tile_id, local)]
        for core in cores
        for local in core.base_holding_previous
    }
    added: set[ComponentKey] = set()
    cleared: set[ComponentKey] = set()
    changed: set[int] = set()
    for owner, owner_bases in sorted(bases.by_label.items()):
        owner_added, owner_cleared = _decide_owner(
            owner_bases,
            candidates.by_label.get(owner, set()),
            touched,
            holding,
        )
        added |= owner_added
        cleared |= owner_cleared
        if owner_added or owner_cleared:
            changed.add(owner)
    return (
        _shares(cores, bases.roots, candidates.roots, added, cleared),
        frozenset(changed),
    )


def _touched(
    cores: Sequence[OwnerBridgeCore],
    base_roots: dict[ComponentKey, ComponentKey],
    candidate_roots: dict[ComponentKey, ComponentKey],
) -> dict[ComponentKey, set[ComponentKey]]:
    """Name the base parts each joined candidate touches, in any core."""
    pairs = {
        (candidate_roots[first], base_roots[second])
        for first, second in touching_across_cores(
            tuple(core.candidates for core in cores),
            tuple(core.base for core in cores),
        )
    }
    for core in cores:
        tile_id = core.base.partition.tile_id
        pairs.update(
            (candidate_roots[(tile_id, first)], base_roots[(tile_id, second)])
            for first, second in core.touching
        )
    touched: dict[ComponentKey, set[ComponentKey]] = {}
    for candidate, base in pairs:
        touched.setdefault(candidate, set()).add(base)
    return touched


def _shares(
    cores: Sequence[OwnerBridgeCore],
    base_roots: dict[ComponentKey, ComponentKey],
    candidate_roots: dict[ComponentKey, ComponentKey],
    added: set[ComponentKey],
    cleared: set[ComponentKey],
) -> dict[str, OwnerBridgeShare]:
    """Translate joined decisions back into each core's own components."""
    shares: dict[str, OwnerBridgeShare] = {}
    for core in cores:
        share = OwnerBridgeShare(
            added=tuple(
                key[1]
                for key in core.candidates.component_keys()
                if candidate_roots[key] in added
            ),
            cleared=tuple(
                key[1]
                for key in core.base.component_keys()
                if base_roots[key] in cleared
            ),
        )
        if share.added or share.cleared:
            shares[core.base.partition.tile_id] = share
    return shares


def _decide_owner(
    bases: set[ComponentKey],
    candidates: set[ComponentKey],
    touched: dict[ComponentKey, set[ComponentKey]],
    holding: set[ComponentKey],
) -> tuple[set[ComponentKey], set[ComponentKey]]:
    """Return one owner's added candidates and cleared base components.

    The window rule, when the base and its bridges are not connected, first
    restores the whole earlier support and only then keeps one part. The
    restoration can never reconnect them, because a candidate touching two
    parts would already be a bridge and two candidates never touch, so the
    rule goes straight to the part holding the owner's earlier pixels.
    """
    bridges = {
        candidate
        for candidate in candidates
        if len(touched.get(candidate, set()) & bases)
        >= _MINIMUM_BRIDGE_TOUCH_COUNT
    }
    if len(set(_parts(bases, bridges, touched).values())) <= 1:
        return bridges, set()
    parts = _parts(bases, candidates, touched)
    kept = {parts[("candidate", *candidate)] for candidate in candidates} | {
        parts[("base", *base)] for base in bases & holding
    }
    if len(kept) != 1:
        raise ValueError("previous publication ownership must be connected")
    part = kept.pop()
    return (
        {
            candidate
            for candidate in candidates
            if parts[("candidate", *candidate)] == part
        },
        {base for base in bases if parts[("base", *base)] != part},
    )


def _parts(
    bases: set[ComponentKey],
    candidates: set[ComponentKey],
    touched: dict[ComponentKey, set[ComponentKey]],
) -> dict[tuple[str, str, int], tuple[str, str, int]]:
    """Join base parts and the given candidates into connected parts.

    A base and a candidate component can share a key, so each is tagged
    with the plane it comes from.
    """
    return join_components(
        (
            *(("base", *base) for base in bases),
            *(("candidate", *candidate) for candidate in candidates),
        ),
        (
            (("candidate", *candidate), ("base", *base))
            for candidate in candidates
            for base in touched.get(candidate, set()) & bases
        ),
    )


def apply_owner_bridges(
    final_core: npt.NDArray[np.int32],
    planes: OwnerBridgePlanes,
    share: OwnerBridgeShare,
) -> None:
    """Write one core's share of the bridge decisions, in place.

    ``planes`` must be the ones this core observed, labelled from the same
    planes with the same owners, so their component numbers are the ones the
    decision names.
    """
    candidates = planes.candidates.components
    added = np.isin(candidates, share.added)
    final_core[added] = planes.candidates.label_of()[candidates[added]]
    final_core[np.isin(planes.base.components, share.cleared)] = 0
