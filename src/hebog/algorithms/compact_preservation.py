"""Fail-closed preservation of completed Phase 4 compact catalogues."""

from __future__ import annotations

from collections.abc import Sequence

from hebog.data_models.catalogue_construction import CompletedCompactCatalogue
from hebog.data_models.multiscale import CrossScaleAssociation


class CompactAssociationDecisionRequiredError(ValueError):
    """Multiscale evidence requires the governed Step 4 association path."""


def preserve_unassociated_compact_catalogue(
    compact_catalogue: CompletedCompactCatalogue,
    *,
    associations: Sequence[CrossScaleAssociation],
) -> CompletedCompactCatalogue:
    """Return the exact compact result when scale evidence is independent.

    Only an ``extended-only`` association with no compact source identities is
    provably unable to change a Phase 4 compact association. Every other
    relationship fails closed until the Step 4 ownership and publication
    rules have made an explicit decision.
    """
    decision_required = tuple(
        association.association_id
        for association in associations
        if association.relationship != "extended-only"
        or association.compact_source_ids
    )
    if decision_required:
        association_ids = ", ".join(sorted(set(decision_required)))
        raise CompactAssociationDecisionRequiredError(
            "Step 4 association decision required for multiscale "
            f"association(s): {association_ids}"
        )
    return compact_catalogue
