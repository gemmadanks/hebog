"""Contracts for global Phase 5 combined catalogue identities."""

from __future__ import annotations

from hashlib import sha256

import pytest

from hebog.algorithms.combined_identity import derive_combined_identities
from hebog.data_models.multiscale import (
    CombinedIslandIdentity,
    CompactExtendedContextEdge,
    CompactSourceSupport,
    CrossScaleAssociation,
    ExtendedSourceIdentity,
)

_ISLAND_NAMESPACE = b"phase-5-combined-island-v1\0"
_SOURCE_NAMESPACE = b"phase-5-extended-source-v1\0"


def _compact_source(
    source_id: str,
    island_id: str,
    *,
    component_ids: tuple[str, ...] = (),
    pixel: tuple[int, int] = (1, 1),
) -> CompactSourceSupport:
    """Build one compact identity input with minimal exact support metadata."""
    y_pixel, x_pixel = pixel
    return CompactSourceSupport(
        source_id=source_id,
        island_id=island_id,
        support_pixel_count=1,
        bounds_yx=(y_pixel, y_pixel + 1, x_pixel, x_pixel + 1),
        reference_position_yx=(float(y_pixel), float(x_pixel)),
        gaussian_component_ids=component_ids,
    )


def _association(
    name: str,
    *,
    compact_source_ids: tuple[str, ...] = (),
    relationship: str = "extended-only",
) -> CrossScaleAssociation:
    """Build one already reconciled extended association."""
    detection_id = f"scale-detection-{name}"
    return CrossScaleAssociation.model_validate(
        {
            "association_id": f"scale-association-{name}",
            "scale_detection_ids": (detection_id,),
            "compact_source_ids": compact_source_ids,
            "selected_scale_detection_id": detection_id,
            "contributing_scale_orders": (1,),
            "relationship": relationship,
        }
    )


def _edge(
    name: str,
    source_id: str,
    *,
    relationship: str = "overlaps-compact-support",
) -> CompactExtendedContextEdge:
    """Build one compact/extended context edge."""
    return CompactExtendedContextEdge.model_validate(
        {
            "association_id": f"scale-association-{name}",
            "compact_source_id": source_id,
            "relationship": relationship,
        }
    )


def _identity(
    namespace: bytes,
    prefix: str,
    sections: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    """Calculate the frozen canonical identity construction."""
    digest = sha256(namespace)
    for section_name, identifiers in sections:
        digest.update(section_name.encode("ascii"))
        digest.update(b"\0")
        for identifier in identifiers:
            digest.update(identifier.encode("ascii"))
            digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()}"


def _extended_source_id(association_id: str) -> str:
    """Return the expected one-source-per-association identity."""
    return _identity(
        _SOURCE_NAMESPACE,
        "source-extended",
        (("association", (association_id,)),),
    )


def test_compact_only_identities_remain_exactly_unchanged() -> None:
    """No multiscale context cannot renumber Phase 4 catalogue objects."""
    compact_sources = (
        _compact_source(
            "source-compact-alpha",
            "island-compact",
            component_ids=("gaussian-compact-alpha",),
        ),
        _compact_source(
            "source-compact-beta",
            "island-compact",
            component_ids=("gaussian-compact-beta",),
            pixel=(1, 2),
        ),
    )

    result = derive_combined_identities(compact_sources, (), ())

    assert result.extended_sources == ()
    assert result.islands == (
        CombinedIslandIdentity(
            island_id="island-compact",
            compact_island_ids=("island-compact",),
            compact_source_ids=(
                "source-compact-alpha",
                "source-compact-beta",
            ),
            association_ids=(),
            extended_source_ids=(),
            gaussian_component_ids=(
                "gaussian-compact-alpha",
                "gaussian-compact-beta",
            ),
        ),
    )


def test_empty_inputs_produce_an_empty_identity_result() -> None:
    """An empty completed image has no synthetic island or source identity."""
    result = derive_combined_identities((), (), ())

    assert result.islands == ()
    assert result.extended_sources == ()


def test_extended_only_association_has_stable_source_and_no_gaussian() -> None:
    """Irregular emission is one source row without a fabricated component."""
    association = _association("diffuse")
    expected_source_id = _extended_source_id(association.association_id)
    expected_island_id = _identity(
        _ISLAND_NAMESPACE,
        "combined-island",
        (
            ("compact-island", ()),
            ("association", (association.association_id,)),
        ),
    )

    result = derive_combined_identities((), (association,), ())

    assert result.islands == (
        CombinedIslandIdentity(
            island_id=expected_island_id,
            compact_island_ids=(),
            compact_source_ids=(),
            association_ids=(association.association_id,),
            extended_source_ids=(expected_source_id,),
            gaussian_component_ids=(),
        ),
    )
    assert result.extended_sources == (
        ExtendedSourceIdentity(
            association_id=association.association_id,
            island_id=expected_island_id,
            source_id=expected_source_id,
            gaussian_component_ids=(),
        ),
    )


def test_mixed_island_retains_compact_and_adds_extended() -> None:
    """Context changes grouping, never existing compact object identities."""
    compact_sources = (
        _compact_source(
            "source-compact-alpha",
            "island-compact",
            component_ids=("gaussian-compact-alpha",),
        ),
        _compact_source(
            "source-compact-beta",
            "island-compact",
            component_ids=("gaussian-compact-beta",),
            pixel=(1, 2),
        ),
    )
    association = _association(
        "diffuse",
        compact_source_ids=(
            "source-compact-alpha",
            "source-compact-beta",
        ),
        relationship="contains-compact-support",
    )
    edges = (
        _edge(
            "diffuse",
            "source-compact-alpha",
            relationship="contains-compact-support",
        ),
        _edge(
            "diffuse",
            "source-compact-beta",
            relationship="contains-compact-support",
        ),
    )

    result = derive_combined_identities(
        compact_sources,
        (association,),
        edges,
    )

    island = result.islands[0]
    assert island.island_id != "island-compact"
    assert island.compact_island_ids == ("island-compact",)
    assert island.compact_source_ids == (
        "source-compact-alpha",
        "source-compact-beta",
    )
    assert island.gaussian_component_ids == (
        "gaussian-compact-alpha",
        "gaussian-compact-beta",
    )
    assert island.association_ids == (association.association_id,)
    assert island.extended_source_ids == (
        _extended_source_id(association.association_id),
    )


def test_one_compact_island_can_join_several_extended_sources() -> None:
    """A shared compact neighbour groups but does not merge associations."""
    compact = _compact_source("source-core", "island-core")
    associations = tuple(
        _association(
            name,
            compact_source_ids=(compact.source_id,),
            relationship="overlaps-compact-support",
        )
        for name in ("left", "right")
    )
    edges = tuple(_edge(name, compact.source_id) for name in ("left", "right"))

    result = derive_combined_identities((compact,), associations, edges)

    assert len(result.islands) == 1
    island = result.islands[0]
    assert island.association_ids == tuple(
        sorted(item.association_id for item in associations)
    )
    assert len(island.extended_source_ids) == 2
    assert len(set(island.extended_source_ids)) == 2
    assert len(result.extended_sources) == 2


def test_one_extended_source_can_join_several_compact_islands() -> None:
    """Many compact contexts form one combined island without source merges."""
    compact_sources = (
        _compact_source("source-left", "island-left"),
        _compact_source("source-right", "island-right", pixel=(1, 3)),
    )
    association = _association(
        "bridge",
        compact_source_ids=("source-left", "source-right"),
        relationship="overlaps-compact-support",
    )
    edges = (
        _edge("bridge", "source-left"),
        _edge("bridge", "source-right"),
    )

    result = derive_combined_identities(
        compact_sources,
        (association,),
        edges,
    )

    assert len(result.islands) == 1
    assert result.islands[0].compact_island_ids == (
        "island-left",
        "island-right",
    )
    assert result.islands[0].compact_source_ids == (
        "source-left",
        "source-right",
    )


def test_disconnected_context_components_receive_separate_identities() -> None:
    """Only graph connectivity, not global proximity, forms islands."""
    compact_sources = (
        _compact_source("source-alpha", "island-alpha"),
        _compact_source("source-beta", "island-beta", pixel=(5, 5)),
    )
    association = _association(
        "alpha",
        compact_source_ids=("source-alpha",),
        relationship="overlaps-compact-support",
    )

    result = derive_combined_identities(
        compact_sources,
        (association,),
        (_edge("alpha", "source-alpha"),),
    )

    assert len(result.islands) == 2
    assert {item.compact_island_ids for item in result.islands} == {
        ("island-alpha",),
        ("island-beta",),
    }
    isolated = next(
        item
        for item in result.islands
        if item.compact_island_ids == ("island-beta",)
    )
    assert isolated.island_id == "island-beta"
    assert isolated.association_ids == ()


def test_identity_derivation_is_invariant_to_every_input_order() -> None:
    """Task and shard order cannot enter a published identity."""
    compact_sources = (
        _compact_source(
            "source-alpha",
            "island-shared",
            component_ids=("gaussian-alpha",),
        ),
        _compact_source(
            "source-beta",
            "island-shared",
            component_ids=("gaussian-beta",),
            pixel=(1, 2),
        ),
    )
    association = _association(
        "shared",
        compact_source_ids=("source-alpha", "source-beta"),
        relationship="overlaps-compact-support",
    )
    edges = (
        _edge("shared", "source-alpha"),
        _edge("shared", "source-beta"),
    )

    forward = derive_combined_identities(
        compact_sources,
        (association,),
        edges,
    )
    reverse = derive_combined_identities(
        tuple(reversed(compact_sources)),
        (association,),
        tuple(reversed(edges)),
    )

    assert reverse == forward


def test_extended_source_identity_is_independent_of_island_context() -> None:
    """Spatial neighbours cannot relabel the extended source itself."""
    isolated = _association("stable")
    contextualized = isolated.model_copy(
        update={
            "compact_source_ids": ("source-core",),
            "relationship": "overlaps-compact-support",
        }
    )
    without_context = derive_combined_identities((), (isolated,), ())
    with_context = derive_combined_identities(
        (_compact_source("source-core", "island-core"),),
        (contextualized,),
        (_edge("stable", "source-core"),),
    )

    assert (
        with_context.extended_sources[0].source_id
        == without_context.extended_sources[0].source_id
    )
    assert (
        with_context.extended_sources[0].island_id
        != without_context.extended_sources[0].island_id
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("duplicate-source", "compact source IDs must be unique"),
        ("duplicate-component", "Gaussian component IDs must be unique"),
        ("duplicate-association", "association IDs must be unique"),
        ("duplicate-edge", "context edges must be unique"),
        ("association-unknown-source", "association names an unknown"),
        ("unknown-source", "unknown compact source"),
        ("unknown-association", "unknown association"),
        ("missing-edge", "compact source identities must match context edges"),
        ("relationship", "relationship must match context edges"),
    ],
)
def test_invalid_identity_provenance_fails_closed(
    change: str,
    message: str,
) -> None:
    """Stable hashes cannot hide missing or contradictory graph evidence."""
    source = _compact_source(
        "source-core",
        "island-core",
        component_ids=("gaussian-core",),
    )
    other = _compact_source(
        "source-other",
        "island-other",
        component_ids=("gaussian-other",),
    )
    association = _association(
        "diffuse",
        compact_source_ids=(source.source_id,),
        relationship="overlaps-compact-support",
    )
    edge = _edge("diffuse", source.source_id)
    sources = (source, other)
    associations = (association,)
    edges = (edge,)

    if change == "duplicate-source":
        sources = (source, source)
    elif change == "duplicate-component":
        other = other.model_copy(
            update={"gaussian_component_ids": ("gaussian-core",)}
        )
        sources = (source, other)
    elif change == "duplicate-association":
        associations = (association, association)
    elif change == "duplicate-edge":
        edges = (edge, edge)
    elif change == "association-unknown-source":
        association = association.model_copy(
            update={"compact_source_ids": ("source-unknown",)}
        )
        associations = (association,)
    elif change == "unknown-source":
        edges = (_edge("diffuse", "source-unknown"),)
    elif change == "unknown-association":
        edges = (_edge("unknown", source.source_id),)
    elif change == "missing-edge":
        edges = ()
    elif change == "relationship":
        association = association.model_copy(
            update={"relationship": "contains-compact-support"}
        )
        associations = (association,)

    with pytest.raises(ValueError, match=message):
        derive_combined_identities(sources, associations, edges)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "island_id": "combined-island-alpha",
                "compact_island_ids": (),
                "compact_source_ids": (),
                "association_ids": (),
                "extended_source_ids": (),
                "gaussian_component_ids": (),
            },
            "requires a compact island or association",
        ),
        (
            {
                "island_id": "combined-island-alpha",
                "compact_island_ids": ("island-beta", "island-alpha"),
                "compact_source_ids": ("source-alpha",),
                "association_ids": (),
                "extended_source_ids": (),
                "gaussian_component_ids": (),
            },
            "canonical",
        ),
        (
            {
                "island_id": "combined-island-alpha",
                "compact_island_ids": ("island-alpha",),
                "compact_source_ids": ("source-alpha",),
                "association_ids": ("scale-association-alpha",),
                "extended_source_ids": (),
                "gaussian_component_ids": (),
            },
            "one extended source per association",
        ),
        (
            {
                "island_id": "combined-island-alpha",
                "compact_island_ids": ("island-alpha",),
                "compact_source_ids": (),
                "association_ids": (),
                "extended_source_ids": (),
                "gaussian_component_ids": (),
            },
            "island and source membership must both be present",
        ),
        (
            {
                "island_id": "combined-island-alpha",
                "compact_island_ids": (),
                "compact_source_ids": (),
                "association_ids": ("scale-association-alpha",),
                "extended_source_ids": ("source-extended-alpha",),
                "gaussian_component_ids": ("gaussian-fabricated",),
            },
            "Gaussian components require retained compact sources",
        ),
    ],
)
def test_combined_island_identity_rejects_inconsistent_membership(
    payload: dict[str, object],
    message: str,
) -> None:
    """The identity record cannot serialize an incomplete graph component."""
    with pytest.raises(ValueError, match=message):
        CombinedIslandIdentity.model_validate(payload)


def test_extended_identity_forbids_gaussian_compatibility_components() -> None:
    """An irregular extended row cannot masquerade as a Gaussian fit."""
    with pytest.raises(ValueError, match="at most 0 items"):
        ExtendedSourceIdentity(
            association_id="scale-association-alpha",
            island_id="combined-island-alpha",
            source_id="source-extended-alpha",
            gaussian_component_ids=("gaussian-fabricated",),
        )


def test_compact_support_requires_canonical_component_identities() -> None:
    """Retained Phase 4 Gaussian IDs cannot be reordered or duplicated."""
    with pytest.raises(ValueError, match="unique and canonical"):
        _compact_source(
            "source-compact",
            "island-compact",
            component_ids=("gaussian-beta", "gaussian-alpha"),
        )


def test_compact_support_requires_explicit_component_provenance() -> None:
    """A future caller cannot silently omit retained compact components."""
    with pytest.raises(ValueError, match="Field required"):
        CompactSourceSupport.model_validate(
            {
                "source_id": "source-compact",
                "island_id": "island-compact",
                "support_pixel_count": 1,
                "bounds_yx": (0, 1, 0, 1),
                "reference_position_yx": (0.0, 0.0),
            }
        )
