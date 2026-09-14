# pyright: reportMissingTypeStubs=false
"""Fail-closed construction of final Phase 5 catalogue products."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from itertools import zip_longest
from math import fsum, sqrt
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt

from hebog.algorithms.astrometry import (
    compact_geometry_at_pixel,
    local_tangent_plane_transform,
)
from hebog.algorithms.combined_identity import CombinedIdentityResult
from hebog.data_models.catalogue_construction import (
    CompletedCombinedCatalogue,
    CompletedCompactCatalogue,
)
from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianComponent,
    Island,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.images import ImageMetadata
from hebog.data_models.multiscale import (
    CombinedIslandDisposition,
    CombinedIslandIdentity,
    CompletedCombinedCatalogueState,
    CrossScaleAssociation,
    ExtendedEmissionMeasurement,
    ExtendedSourceIdentity,
)
from hebog.data_models.source_finding import (
    ContinuumSourceFindingDiagnostics,
    DiagnosticsProduct,
    SourceFindingDiagnostics,
    SourceScaleProvenance,
)


class CombinedProductConstructionError(ValueError):
    """Combined scientific evidence cannot form publishable products."""


_IMAGE_DIMENSIONS = 2


def _unique_by(
    records: Sequence[Any],
    *,
    field_name: str,
    record_name: str,
) -> dict[str, Any]:
    """Index records by one unique identity field."""
    indexed: dict[str, Any] = {}
    for record in records:
        identifier = str(getattr(record, field_name))
        if identifier in indexed:
            raise CombinedProductConstructionError(
                f"{record_name} identities must be unique"
            )
        indexed[identifier] = record
    return indexed


def _validate_terminal_identity(
    identity: CombinedIslandIdentity,
    disposition: CombinedIslandDisposition,
) -> bool:
    """Validate one terminal outcome and return whether it is published."""
    if disposition.status == "retained-compact":
        if (
            identity.association_ids
            or disposition.association_ids
            or disposition.source_ids != identity.compact_source_ids
        ):
            raise CombinedProductConstructionError(
                "retained compact terminal evidence disagrees with identity"
            )
        return True
    if disposition.status == "accepted-multiscale":
        if (
            not identity.association_ids
            or disposition.association_ids != identity.association_ids
            or disposition.source_ids != identity.compact_source_ids
        ):
            raise CombinedProductConstructionError(
                "accepted multiscale terminal evidence disagrees with identity"
            )
        return True
    if disposition.status == "rejected-artifact":
        if (
            not identity.association_ids
            or identity.compact_source_ids
            or disposition.association_ids != identity.association_ids
            or disposition.source_ids
        ):
            raise CombinedProductConstructionError(
                "rejected terminal evidence disagrees with artifact identity"
            )
        return False
    raise CombinedProductConstructionError(
        "completed state contains a failed terminal disposition"
    )


def _validate_composition(
    compact: CompletedCompactCatalogue,
    state: CompletedCombinedCatalogueState,
    identities: CombinedIdentityResult,
    associations: Sequence[CrossScaleAssociation],
    measurements: Sequence[ExtendedEmissionMeasurement],
) -> tuple[
    tuple[CombinedIslandIdentity, ...],
    dict[str, CrossScaleAssociation],
    dict[str, ExtendedEmissionMeasurement],
    dict[str, ExtendedSourceIdentity],
]:
    """Require exact compact, identity, terminal, and measurement closure."""
    catalogue = compact.catalogue
    if state.state.catalogue_id != catalogue.catalogue_id:
        raise CombinedProductConstructionError(
            "terminal catalogue identity differs from compact catalogue"
        )
    islands_by_id = _unique_by(
        identities.islands,
        field_name="island_id",
        record_name="combined island",
    )
    required_ids = {
        *state.state.accepted_island_ids,
        *state.state.deferred_island_ids,
    }
    if set(islands_by_id) != required_ids:
        raise CombinedProductConstructionError(
            "terminal island population differs from combined identities"
        )
    dispositions = _unique_by(
        state.state.dispositions,
        field_name="island_id",
        record_name="terminal disposition",
    )
    published = tuple(
        identity
        for identity in identities.islands
        if _validate_terminal_identity(
            identity,
            dispositions[identity.island_id],
        )
    )
    compact_island_ids = {
        island_id
        for identity in identities.islands
        for island_id in identity.compact_island_ids
    }
    compact_source_ids = {
        source_id
        for identity in identities.islands
        for source_id in identity.compact_source_ids
    }
    compact_component_ids = {
        component_id
        for identity in identities.islands
        for component_id in identity.gaussian_component_ids
    }
    if compact_island_ids != {item.island_id for item in catalogue.islands}:
        raise CombinedProductConstructionError(
            "combined identities do not cover the compact islands"
        )
    if compact_source_ids != {item.source_id for item in catalogue.sources}:
        raise CombinedProductConstructionError(
            "combined identities do not cover the compact sources"
        )
    if compact_component_ids != {
        item.gaussian_component_id for item in catalogue.gaussian_components
    }:
        raise CombinedProductConstructionError(
            "combined identities do not cover the compact components"
        )
    associations_by_id = _unique_by(
        associations,
        field_name="association_id",
        record_name="association",
    )
    identity_association_ids = {
        association_id
        for identity in identities.islands
        for association_id in identity.association_ids
    }
    if set(associations_by_id) != identity_association_ids:
        raise CombinedProductConstructionError(
            "association provenance differs from combined identities"
        )
    extended_sources_by_association = _unique_by(
        identities.extended_sources,
        field_name="association_id",
        record_name="extended source",
    )
    if set(extended_sources_by_association) != identity_association_ids:
        raise CombinedProductConstructionError(
            "extended source identities differ from associations"
        )
    accepted_association_ids = {
        association_id
        for identity in published
        for association_id in identity.association_ids
    }
    measurements_by_association = _unique_by(
        measurements,
        field_name="association_id",
        record_name="extended measurement",
    )
    if set(measurements_by_association) != accepted_association_ids:
        raise CombinedProductConstructionError(
            "extended measurement population differs from accepted "
            "associations"
        )
    return (
        published,
        associations_by_id,
        measurements_by_association,
        extended_sources_by_association,
    )


def _extended_source_record(
    identity: ExtendedSourceIdentity,
    measurement: ExtendedEmissionMeasurement,
    metadata: ImageMetadata,
) -> SourceCandidate:
    """Transform one irregular segment measurement to a source row."""
    transform = local_tangent_plane_transform(
        metadata,
        measurement.centroid_xy,
    )
    return SourceCandidate(
        source_id=identity.source_id,
        island_id=identity.island_id,
        position=transform.position,
        flux=FluxMeasurement(
            peak_flux_jy_per_beam=measurement.peak_flux_jy_per_beam,
            peak_flux_error_jy_per_beam=None,
            integrated_flux_jy=measurement.integrated_flux_jy,
            integrated_flux_error_jy=(measurement.integrated_flux_error_jy),
            local_rms_jy_per_beam=measurement.local_rms_jy_per_beam,
        ),
        spectral_model=SpectralModel(
            kind="reference-frequency-only",
            reference_frequency_hz=metadata.reference_frequency_hz,
            coefficients=(),
        ),
        fitted_shape=None,
        deconvolved_shape=None,
        deconvolved_major_fwhm_degrees=(
            measurement.major_extent_beams * metadata.beam.major_fwhm_degrees
        ),
        quality_flags=tuple(
            sorted(
                {
                    "extended-emission",
                    "major-axis-only",
                    "moment-measurement",
                    "position-uncertainty-unavailable",
                    "segment-moment-extent",
                }
            )
        ),
        association_aperture_integrated_flux_jy=(
            measurement.integrated_flux_jy
        ),
    )


def _source_provenance(
    identity: ExtendedSourceIdentity,
    association: CrossScaleAssociation,
    measurement: ExtendedEmissionMeasurement,
) -> SourceScaleProvenance:
    """Bind one extended source row to its exact scale/support evidence."""
    return SourceScaleProvenance(
        source_id=identity.source_id,
        island_id=identity.island_id,
        association_id=association.association_id,
        scale_detection_ids=association.scale_detection_ids,
        selected_scale_detection_id=(association.selected_scale_detection_id),
        contributing_scale_orders=association.contributing_scale_orders,
        relationship=association.relationship,
        support_pixel_count=measurement.support_pixel_count,
        visible_model_fraction=measurement.visible_model_fraction,
    )


def _combined_island_record(
    identity: CombinedIslandIdentity,
    *,
    compact_islands: dict[str, Island],
    measurements: dict[str, ExtendedEmissionMeasurement],
    metadata: ImageMetadata,
) -> Island:
    """Aggregate non-overlapping child measurements without double counts."""
    compact_children = tuple(
        compact_islands[island_id] for island_id in identity.compact_island_ids
    )
    extended_children = tuple(
        measurements[association_id]
        for association_id in identity.association_ids
    )
    pixel_counts = (
        *(item.pixel_count for item in compact_children),
        *(item.support_pixel_count for item in extended_children),
    )
    pixel_count = sum(pixel_counts)
    integrated_fluxes = (
        *(item.integrated_flux_jy for item in compact_children),
        *(item.integrated_flux_jy for item in extended_children),
    )
    flux_errors = (
        *(item.integrated_flux_error_jy for item in compact_children),
        *(item.integrated_flux_error_jy for item in extended_children),
    )
    rms_terms = (
        *(
            item.pixel_count * item.local_rms_jy_per_beam**2
            for item in compact_children
        ),
        *(
            item.support_pixel_count * item.local_rms_jy_per_beam**2
            for item in extended_children
        ),
    )
    brightness_sum = fsum(
        item.pixel_count * item.mean_brightness_jy_per_beam
        for item in compact_children
    )
    for item in extended_children:
        geometry = compact_geometry_at_pixel(metadata, item.centroid_xy)
        pixel_to_beam_area_ratio = (
            geometry.pixel_solid_angle_steradians
            / geometry.restoring_beam_solid_angle_steradians
        )
        brightness_sum += item.integrated_flux_jy / pixel_to_beam_area_ratio
    return Island(
        island_id=identity.island_id,
        pixel_count=pixel_count,
        integrated_flux_jy=fsum(integrated_fluxes),
        integrated_flux_error_jy=(
            sqrt(fsum(error**2 for error in flux_errors if error is not None))
            if all(error is not None for error in flux_errors)
            else None
        ),
        local_rms_jy_per_beam=sqrt(fsum(rms_terms) / pixel_count),
        mean_brightness_jy_per_beam=brightness_sum / pixel_count,
    )


def construct_combined_catalogue(  # noqa: PLR0913
    compact: CompletedCompactCatalogue,
    *,
    state: CompletedCombinedCatalogueState,
    identities: CombinedIdentityResult,
    associations: Sequence[CrossScaleAssociation],
    measurements: Sequence[ExtendedEmissionMeasurement],
    metadata: ImageMetadata,
) -> CompletedCombinedCatalogue:
    """Construct the complete catalogue or fail before any publication."""
    if metadata.unit != "Jy/beam":
        raise CombinedProductConstructionError(
            "combined catalogue requires image unit Jy/beam"
        )
    if (
        compact.catalogue.reference_frequency_hz
        != metadata.reference_frequency_hz
    ):
        raise CombinedProductConstructionError(
            "combined metadata reference frequency differs from catalogue"
        )
    (
        published,
        associations_by_id,
        measurements_by_association,
        extended_sources_by_association,
    ) = _validate_composition(
        compact,
        state,
        identities,
        associations,
        measurements,
    )
    compact_only_preserved = not associations
    if compact_only_preserved:
        return CompletedCombinedCatalogue(
            catalogue=compact.catalogue,
            terminal_state=state,
            source_provenance=(),
            compact_only_preserved=True,
        )
    compact_islands = {
        item.island_id: item for item in compact.catalogue.islands
    }
    combined_island_by_compact = {
        compact_island_id: identity.island_id
        for identity in published
        for compact_island_id in identity.compact_island_ids
    }
    retained_compact_source_ids = {
        source_id
        for identity in published
        for source_id in identity.compact_source_ids
    }
    sources = [
        SourceCandidate.model_validate(
            {
                **source.model_dump(mode="python"),
                "island_id": combined_island_by_compact[source.island_id],
            }
        )
        for source in compact.catalogue.sources
        if source.source_id in retained_compact_source_ids
    ]
    retained_component_ids = {
        component_id
        for identity in published
        for component_id in identity.gaussian_component_ids
    }
    components = [
        GaussianComponent.model_validate(
            {
                **component.model_dump(mode="python"),
                "island_id": combined_island_by_compact[component.island_id],
            }
        )
        for component in compact.catalogue.gaussian_components
        if component.gaussian_component_id in retained_component_ids
    ]
    provenance: list[SourceScaleProvenance] = []
    for identity in published:
        for association_id in identity.association_ids:
            source_identity = extended_sources_by_association[association_id]
            measurement = measurements_by_association[association_id]
            association = associations_by_id[association_id]
            sources.append(
                _extended_source_record(
                    source_identity,
                    measurement,
                    metadata,
                )
            )
            provenance.append(
                _source_provenance(
                    source_identity,
                    association,
                    measurement,
                )
            )
    catalogue = SourceCatalogue.create(
        catalogue_id=compact.catalogue.catalogue_id,
        coordinate_frame=compact.catalogue.coordinate_frame,
        position_epoch=compact.catalogue.position_epoch,
        reference_frequency_hz=compact.catalogue.reference_frequency_hz,
        islands=(
            _combined_island_record(
                identity,
                compact_islands=compact_islands,
                measurements=measurements_by_association,
                metadata=metadata,
            )
            for identity in published
        ),
        sources=sources,
        gaussian_components=components,
    )
    return CompletedCombinedCatalogue(
        catalogue=catalogue,
        terminal_state=state,
        source_provenance=tuple(
            sorted(provenance, key=lambda item: item.source_id)
        ),
        compact_only_preserved=False,
    )


def build_combined_diagnostics(
    *,
    run_id: str,
    combined: CompletedCombinedCatalogue,
    rms_scientific_status: Literal["valid", "unavailable"],
) -> DiagnosticsProduct:
    """Build byte-stable compact or provenance-rich continuum diagnostics."""
    catalogue = combined.catalogue
    if combined.compact_only_preserved:
        return SourceFindingDiagnostics(
            run_id=run_id,
            source_count=len(catalogue.sources),
            gaussian_component_count=len(catalogue.gaussian_components),
            island_count=len(catalogue.islands),
            rms_scientific_status=rms_scientific_status,
        )
    return ContinuumSourceFindingDiagnostics(
        run_id=run_id,
        source_count=len(catalogue.sources),
        gaussian_component_count=len(catalogue.gaussian_components),
        island_count=len(catalogue.islands),
        rms_scientific_status=rms_scientific_status,
        extended_source_count=len(combined.source_provenance),
        terminal_disposition_count=len(
            combined.terminal_state.state.dispositions
        ),
        source_provenance=combined.source_provenance,
    )


def _boolean_block(
    raw_block: npt.ArrayLike,
    *,
    role: str,
) -> npt.NDArray[np.bool_]:
    """Require one exact two-dimensional boolean row block."""
    block = np.asarray(raw_block)
    if block.ndim != _IMAGE_DIMENSIONS:
        raise ValueError(f"{role} mask block must be two-dimensional")
    if block.dtype != np.dtype(np.bool_):
        raise TypeError(f"{role} mask block must have boolean dtype")
    return block


def combine_source_filtering_mask_blocks(
    compact_blocks: Iterable[npt.ArrayLike],
    extended_blocks: Iterable[npt.ArrayLike] | None,
) -> Iterator[npt.NDArray[np.bool_]]:
    """Yield bounded compact masks or their aligned extended-support union."""
    if extended_blocks is None:
        for compact_raw in compact_blocks:
            yield _boolean_block(compact_raw, role="compact")
        return
    sentinel = object()
    for compact_raw, extended_raw in zip_longest(
        compact_blocks,
        extended_blocks,
        fillvalue=sentinel,
    ):
        if compact_raw is sentinel or extended_raw is sentinel:
            raise ValueError(
                "compact and extended masks must have the same number of "
                "blocks"
            )
        compact = _boolean_block(
            cast(npt.ArrayLike, compact_raw),
            role="compact",
        )
        extended = _boolean_block(
            cast(npt.ArrayLike, extended_raw),
            role="extended",
        )
        if compact.shape != extended.shape:
            raise ValueError(
                "compact and extended mask blocks must have matching shapes"
            )
        yield np.logical_or(compact, extended)
