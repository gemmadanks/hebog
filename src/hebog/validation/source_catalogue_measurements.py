"""Source-catalogue validation with explicitly unavailable derived support.

Keep the historical successor compiler byte-identical. Reuse its scientific
matching, metric arithmetic and strata; amend only the catalogue admission
boundary. No finder or closed campaign execution is performed here.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TypeAlias

from hebog.validation import external_successor_compiler as frozen


@dataclass(frozen=True, slots=True)
class SourceCatalogueMeasurement:
    """Native observables; ``None`` means no exclusive derived support.

    A positive label still asserts actual pixels. A missing label does not
    make the source's native position or flux unavailable.
    """

    identifier: str
    support_label: int | None
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Keep native identity and measurement validation unconditional."""
        if not self.identifier:
            raise ValueError("continuum object identifier must not be empty")
        if self.support_label is not None and self.support_label <= 0:
            raise ValueError("continuum support label must be positive")
        if not all(isfinite(value) for value in self.centre_xy):
            raise ValueError("continuum object centre must be finite")
        if (
            not isfinite(self.integrated_flux_jy)
            or self.integrated_flux_jy <= 0
        ):
            raise ValueError(
                "continuum object flux must be finite and positive"
            )


SourceCatalogueRow: TypeAlias = (
    frozen.ContinuumCatalogueObject | SourceCatalogueMeasurement
)
