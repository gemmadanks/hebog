"""Scheduler-safe compact catalogue shards and completion evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hebog.data_models.catalogues import (
    GaussianComponent,
    Island,
    SourceCandidate,
    SourceCatalogue,
)

_OmissionReason = Literal[
    "fit-non-convergence",
    "fit-invalid-result",
    "non-finite-owned-pixels",
    "non-positive-measurement",
    "singular-covariance",
    "underdetermined-region",
]


@dataclass(frozen=True, slots=True)
class CompactCatalogueOmission:
    """One compact object omitted from an explicitly incomplete result."""

    object_id: str
    reason: _OmissionReason


@dataclass(frozen=True, slots=True)
class CompactCatalogueShard:
    """One coarse task's bounded canonical catalogue rows."""

    islands: tuple[Island, ...]
    sources: tuple[SourceCandidate, ...]
    gaussian_components: tuple[GaussianComponent, ...]
    omissions: tuple[CompactCatalogueOmission, ...]

    @property
    def record_count(self) -> int:
        """Return the source population governing final catalogue admission."""
        return len(self.sources)


@dataclass(frozen=True, slots=True)
class CompactCatalogueReduction:
    """Canonical pairwise reduction and its bounded-fan-in evidence."""

    shard: CompactCatalogueShard
    input_shard_count: int
    reduction_depth: int
    maximum_input_shard_record_count: int


@dataclass(frozen=True, slots=True)
class CompletedCompactCatalogue:
    """One bounded complete in-memory catalogue plus reduction evidence."""

    catalogue: SourceCatalogue
    shard_count: int
    reduction_depth: int
    maximum_shard_record_count: int

    @property
    def source_count(self) -> int:
        """Return the completed source population."""
        return len(self.catalogue.sources)
