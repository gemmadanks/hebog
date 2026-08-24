"""Deterministic global identities for combined Phase 5 graph components."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from hebog.data_models.multiscale import (
    CombinedIslandIdentity,
    CompactExtendedContextEdge,
    CompactSourceSupport,
    CrossScaleAssociation,
    ExtendedSourceIdentity,
)

_COMBINED_ISLAND_NAMESPACE = b"phase-5-combined-island-v1\0"
_EXTENDED_SOURCE_NAMESPACE = b"phase-5-extended-source-v1\0"


@dataclass(frozen=True, slots=True)
class CombinedIdentityResult:
    """Array-free stable identities for all combined graph components."""

    islands: tuple[CombinedIslandIdentity, ...]
    extended_sources: tuple[ExtendedSourceIdentity, ...]


class _DisjointContextNodes:
    """Small deterministic union-find over namespaced graph nodes."""

    def __init__(self, nodes: tuple[str, ...]) -> None:
        self._parent = {node: node for node in nodes}

    def find(self, node: str) -> str:
        """Return and compress the canonical component root."""
        while self._parent[node] != node:
            self._parent[node] = self._parent[self._parent[node]]
            node = self._parent[node]
        return node

    def union(self, first_node: str, second_node: str) -> None:
        """Join two graph components under the lexical stable root."""
        first_root = self.find(first_node)
        second_root = self.find(second_node)
        if first_root != second_root:
            lower, upper = sorted((first_root, second_root))
            self._parent[upper] = lower

    def groups(self) -> tuple[tuple[str, ...], ...]:
        """Return canonical connected node groups."""
        grouped: dict[str, list[str]] = {}
        for node in sorted(self._parent):
            grouped.setdefault(self.find(node), []).append(node)
        return tuple(tuple(nodes) for nodes in grouped.values())


def _stable_identity(
    namespace: bytes,
    prefix: str,
    sections: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    """Hash canonical namespaced membership into one domain identifier."""
    digest = sha256(namespace)
    for section_name, identifiers in sections:
        digest.update(section_name.encode("ascii"))
        digest.update(b"\0")
        for identifier in identifiers:
            digest.update(identifier.encode("ascii"))
            digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()}"


def _extended_source_id(association_id: str) -> str:
    """Derive one stable irregular source identity per association."""
    return _stable_identity(
        _EXTENDED_SOURCE_NAMESPACE,
        "source-extended",
        (("association", (association_id,)),),
    )


def _combined_island_id(
    compact_island_ids: tuple[str, ...],
    association_ids: tuple[str, ...],
) -> str:
    """Preserve compact-only IDs or hash globally reconciled membership."""
    if not association_ids and len(compact_island_ids) == 1:
        return compact_island_ids[0]
    return _stable_identity(
        _COMBINED_ISLAND_NAMESPACE,
        "combined-island",
        (
            ("compact-island", compact_island_ids),
            ("association", association_ids),
        ),
    )


def _validate_compact_sources(
    compact_sources: tuple[CompactSourceSupport, ...],
) -> tuple[
    dict[str, CompactSourceSupport],
    dict[str, tuple[CompactSourceSupport, ...]],
]:
    """Require globally unique compact source and component identities."""
    sources_by_id: dict[str, CompactSourceSupport] = {}
    component_ids: set[str] = set()
    sources_by_island_lists: dict[str, list[CompactSourceSupport]] = {}
    for source in compact_sources:
        if source.source_id in sources_by_id:
            raise ValueError("compact source IDs must be unique")
        sources_by_id[source.source_id] = source
        for component_id in source.gaussian_component_ids:
            if component_id in component_ids:
                raise ValueError("Gaussian component IDs must be unique")
            component_ids.add(component_id)
        sources_by_island_lists.setdefault(source.island_id, []).append(source)
    sources_by_island = {
        island_id: tuple(sorted(sources, key=lambda item: item.source_id))
        for island_id, sources in sources_by_island_lists.items()
    }
    return sources_by_id, sources_by_island


def _validate_associations(
    associations: tuple[CrossScaleAssociation, ...],
    sources_by_id: dict[str, CompactSourceSupport],
) -> dict[str, CrossScaleAssociation]:
    """Require unique associations and known compact context identities."""
    associations_by_id: dict[str, CrossScaleAssociation] = {}
    for association in associations:
        if association.association_id in associations_by_id:
            raise ValueError("association IDs must be unique")
        if any(
            source_id not in sources_by_id
            for source_id in association.compact_source_ids
        ):
            raise ValueError("association names an unknown compact source")
        associations_by_id[association.association_id] = association
    return associations_by_id


def _expected_relationship(
    edges: tuple[CompactExtendedContextEdge, ...],
) -> str:
    """Reduce exact edge evidence to the association-level relationship."""
    if not edges:
        return "extended-only"
    if all(edge.relationship == "contains-compact-support" for edge in edges):
        return "contains-compact-support"
    return "overlaps-compact-support"


def _validate_edges(
    edges: tuple[CompactExtendedContextEdge, ...],
    *,
    sources_by_id: dict[str, CompactSourceSupport],
    associations_by_id: dict[str, CrossScaleAssociation],
) -> dict[str, tuple[CompactExtendedContextEdge, ...]]:
    """Require graph edges and association summaries to agree exactly."""
    edge_keys: set[tuple[str, str]] = set()
    edges_by_association_lists: dict[
        str,
        list[CompactExtendedContextEdge],
    ] = {}
    for edge in edges:
        key = (edge.association_id, edge.compact_source_id)
        if key in edge_keys:
            raise ValueError("context edges must be unique")
        edge_keys.add(key)
        if edge.association_id not in associations_by_id:
            raise ValueError("context edge names an unknown association")
        if edge.compact_source_id not in sources_by_id:
            raise ValueError("context edge names an unknown compact source")
        edges_by_association_lists.setdefault(edge.association_id, []).append(
            edge
        )
    edges_by_association = {
        association_id: tuple(
            sorted(items, key=lambda item: item.compact_source_id)
        )
        for association_id, items in edges_by_association_lists.items()
    }
    for association_id, association in associations_by_id.items():
        association_edges = edges_by_association.get(association_id, ())
        edge_source_ids = tuple(
            edge.compact_source_id for edge in association_edges
        )
        if association.compact_source_ids != edge_source_ids:
            raise ValueError(
                "association compact source identities must match "
                "context edges"
            )
        if association.relationship != _expected_relationship(
            association_edges
        ):
            raise ValueError(
                "association relationship must match context edges"
            )
    return edges_by_association


def _compact_node(island_id: str) -> str:
    """Namespace one retained Phase 4 island graph node."""
    return f"compact-island:{island_id}"


def _association_node(association_id: str) -> str:
    """Namespace one extended association graph node."""
    return f"association:{association_id}"


def _context_components(
    sources_by_id: dict[str, CompactSourceSupport],
    sources_by_island: dict[str, tuple[CompactSourceSupport, ...]],
    associations_by_id: dict[str, CrossScaleAssociation],
    edges_by_association: dict[
        str,
        tuple[CompactExtendedContextEdge, ...],
    ],
) -> tuple[tuple[str, ...], ...]:
    """Return connected compact-island and association node components."""
    nodes = tuple(
        sorted(
            (
                *(_compact_node(island_id) for island_id in sources_by_island),
                *(
                    _association_node(association_id)
                    for association_id in associations_by_id
                ),
            )
        )
    )
    components = _DisjointContextNodes(nodes)
    for association_id, edges in edges_by_association.items():
        association_node = _association_node(association_id)
        for edge in edges:
            compact_island_id = sources_by_id[edge.compact_source_id].island_id
            components.union(
                association_node,
                _compact_node(compact_island_id),
            )
    return components.groups()


def _build_component_identities(
    nodes: tuple[str, ...],
    *,
    sources_by_island: dict[str, tuple[CompactSourceSupport, ...]],
) -> tuple[CombinedIslandIdentity, tuple[ExtendedSourceIdentity, ...]]:
    """Build one combined island and its extended-source mapping."""
    compact_island_ids = tuple(
        sorted(
            node.removeprefix("compact-island:")
            for node in nodes
            if node.startswith("compact-island:")
        )
    )
    association_ids = tuple(
        sorted(
            node.removeprefix("association:")
            for node in nodes
            if node.startswith("association:")
        )
    )
    compact_sources = tuple(
        source
        for island_id in compact_island_ids
        for source in sources_by_island[island_id]
    )
    compact_source_ids = tuple(
        sorted(source.source_id for source in compact_sources)
    )
    gaussian_component_ids = tuple(
        sorted(
            component_id
            for source in compact_sources
            for component_id in source.gaussian_component_ids
        )
    )
    island_id = _combined_island_id(compact_island_ids, association_ids)
    extended_sources = tuple(
        ExtendedSourceIdentity(
            association_id=association_id,
            island_id=island_id,
            source_id=_extended_source_id(association_id),
            gaussian_component_ids=(),
        )
        for association_id in association_ids
    )
    island = CombinedIslandIdentity(
        island_id=island_id,
        compact_island_ids=compact_island_ids,
        compact_source_ids=compact_source_ids,
        association_ids=association_ids,
        extended_source_ids=tuple(
            sorted(source.source_id for source in extended_sources)
        ),
        gaussian_component_ids=gaussian_component_ids,
    )
    return island, extended_sources


def derive_combined_identities(
    compact_sources: tuple[CompactSourceSupport, ...],
    associations: tuple[CrossScaleAssociation, ...],
    edges: tuple[CompactExtendedContextEdge, ...],
) -> CombinedIdentityResult:
    """Derive global island/source identities from canonical graph membership.

    Compact-only identities and compact Gaussian components are retained
    exactly. Mixed and extended-only island identities hash complete graph
    membership. Each extended association receives one stable source identity
    and no Gaussian compatibility component because its irregular segment was
    not produced by a Gaussian fit.
    """
    sources_by_id, sources_by_island = _validate_compact_sources(
        compact_sources
    )
    associations_by_id = _validate_associations(
        associations,
        sources_by_id,
    )
    edges_by_association = _validate_edges(
        edges,
        sources_by_id=sources_by_id,
        associations_by_id=associations_by_id,
    )
    components = _context_components(
        sources_by_id,
        sources_by_island,
        associations_by_id,
        edges_by_association,
    )
    islands: list[CombinedIslandIdentity] = []
    extended_sources: list[ExtendedSourceIdentity] = []
    for nodes in components:
        island, component_sources = _build_component_identities(
            nodes,
            sources_by_island=sources_by_island,
        )
        islands.append(island)
        extended_sources.extend(component_sources)
    return CombinedIdentityResult(
        islands=tuple(sorted(islands, key=lambda item: item.island_id)),
        extended_sources=tuple(
            sorted(
                extended_sources,
                key=lambda item: item.association_id,
            )
        ),
    )
