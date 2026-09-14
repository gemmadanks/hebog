"""Source-catalogue validation with explicitly unavailable derived support.

Keep the historical successor compiler byte-identical. Reuse its scientific
matching, metric arithmetic and strata; amend only the catalogue admission
boundary. No finder or closed campaign execution is performed here.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TypeAlias, cast

import numpy.typing as npt

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


def measure_source_catalogue_image(
    truth: tuple[frozen.ContinuumTruthObject, ...],
    catalogue: tuple[SourceCatalogueRow, ...],
    *,
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    beam_fwhm_pixels: float,
) -> dict[str, dict[str, frozen.MetricValue]]:
    """Apply unchanged metric rules, retaining every native catalogue row."""
    if not truth:
        raise ValueError("successor continuum truth must not be empty")
    truth_labels = frozen._label_plane(
        truth_label_plane, name="truth label plane"
    )
    candidate_labels = frozen._label_plane(
        candidate_label_plane, name="candidate label plane"
    )
    if truth_labels.shape != candidate_labels.shape:
        raise ValueError("truth and candidate label planes must share shape")
    native_supports = frozen.native_support_objects(candidate_labels)
    native_labels = {row.support_label for row in native_supports}
    asserted = tuple(row for row in catalogue if row.support_label is not None)
    if not {row.support_label for row in asserted}.issubset(native_labels):
        raise ValueError(
            "catalogue support label is absent from native labels"
        )
    # The frozen arithmetic reads the same immutable observable fields and
    # passes support_label directly to AssociationObject, which already
    # accepts None. This nominal-type bridge changes no record or value.
    rows = cast(tuple[frozen.ContinuumCatalogueObject, ...], catalogue)
    supported = cast(tuple[frozen.ContinuumCatalogueObject, ...], asserted)
    associations = frozen._association_context(
        truth,
        rows,
        frozen._topology_support_objects(native_supports, supported),
        label_planes=(truth_labels, candidate_labels),
        beam_fwhm_pixels=beam_fwhm_pixels,
    )
    results: dict[str, dict[str, frozen.MetricValue]] = {
        metric: {} for metric in frozen._METRIC_FAMILIES
    }
    results["reliability"]["overall"] = (
        len(set(associations.primary.values())) / len(catalogue)
        if catalogue
        else 0.0
    )
    for metric, value in frozen._mask_metrics(
        truth_labels, candidate_labels
    ).items():
        results[metric]["overall"] = value
    for stratum in frozen._truth_strata(truth):
        frozen._populate_stratum_metrics(
            results,
            frozen._selected_truth(truth, stratum),
            stratum,
            associations,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )
    return results
