"""Deterministic compact association and bounded catalogue construction."""

from __future__ import annotations

from collections.abc import Sequence

from hebog.algorithms.astrometry import (
    compact_geometry_at_pixel,
    transform_compact_gaussian_fit,
)
from hebog.config import CompactCatalogueConfig
from hebog.data_models.catalogue_construction import (
    CompactCatalogueOmission,
    CompactCatalogueReduction,
    CompactCatalogueShard,
    CompletedCompactCatalogue,
)
from hebog.data_models.catalogues import (
    GaussianComponent,
    Island,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.fitting import (
    CompactIslandFitResult,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import ImageMetadata
from hebog.data_models.measurement import (
    UnavailableMomentMeasurement,
    ValidMomentMeasurement,
)


class IncompleteCompactCatalogueError(ValueError):
    """Compact records cannot form a scientifically complete catalogue."""


def _canonical_shard(
    *,
    islands: Sequence[Island],
    sources: Sequence[SourceCandidate],
    components: Sequence[GaussianComponent],
    omissions: Sequence[CompactCatalogueOmission],
) -> CompactCatalogueShard:
    """Return one shard in global identity order."""
    return CompactCatalogueShard(
        islands=tuple(sorted(islands, key=lambda item: item.island_id)),
        sources=tuple(sorted(sources, key=lambda item: item.source_id)),
        gaussian_components=tuple(
            sorted(components, key=lambda item: item.gaussian_component_id)
        ),
        omissions=tuple(sorted(omissions, key=lambda item: item.object_id)),
    )


def _merge_shards(
    left: CompactCatalogueShard,
    right: CompactCatalogueShard,
) -> CompactCatalogueShard:
    """Merge exactly two shards without completion-order semantics."""
    return _canonical_shard(
        islands=(*left.islands, *right.islands),
        sources=(*left.sources, *right.sources),
        components=(
            *left.gaussian_components,
            *right.gaussian_components,
        ),
        omissions=(*left.omissions, *right.omissions),
    )


def reduce_compact_catalogue_shards(
    shards: Sequence[CompactCatalogueShard],
) -> CompactCatalogueReduction:
    """Combine canonical shards through deterministic pairwise levels."""
    input_shards = tuple(shards)
    maximum_input_records = max(
        (shard.record_count for shard in input_shards),
        default=0,
    )
    level = list(input_shards)
    depth = 0
    while len(level) > 1:
        next_level: list[CompactCatalogueShard] = []
        for index in range(0, len(level), 2):
            if index + 1 == len(level):
                next_level.append(level[index])
            else:
                next_level.append(
                    _merge_shards(level[index], level[index + 1])
                )
        level = next_level
        depth += 1
    empty = _canonical_shard(
        islands=(),
        sources=(),
        components=(),
        omissions=(),
    )
    return CompactCatalogueReduction(
        shard=level[0] if level else empty,
        input_shard_count=len(input_shards),
        reduction_depth=depth,
        maximum_input_shard_record_count=maximum_input_records,
    )


def _island_record(
    result: CompactIslandFitResult,
    metadata: ImageMetadata,
) -> Island | CompactCatalogueOmission:
    """Recompute one island's area-dependent flux at its local WCS position."""
    measurement = result.island_measurement
    if isinstance(measurement, UnavailableMomentMeasurement):
        return CompactCatalogueOmission(
            object_id=measurement.target.object_id,
            reason=measurement.reason,
        )
    if isinstance(measurement, ValidMomentMeasurement):
        position_xy = measurement.initializer.centroid_xy
    else:
        position_xy = (
            float(measurement.photometry.peak_position_xy[0]),
            float(measurement.photometry.peak_position_xy[1]),
        )
    geometry = compact_geometry_at_pixel(metadata, position_xy)
    photometry = measurement.photometry
    total_brightness = photometry.mean_brightness_jy_per_beam * float(
        measurement.target.pixel_count
    )
    return Island(
        island_id=measurement.target.island_id,
        pixel_count=measurement.target.pixel_count,
        integrated_flux_jy=(
            total_brightness
            * geometry.pixel_solid_angle_steradians
            / geometry.restoring_beam_solid_angle_steradians
        ),
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=photometry.local_rms_jy_per_beam,
        mean_brightness_jy_per_beam=photometry.mean_brightness_jy_per_beam,
    )


def _associated_records(
    fit: ValidCompactGaussianFit,
    metadata: ImageMetadata,
    *,
    deconvolution_relative_tolerance: float,
    extension_significance_sigma: float,
    deconvolution_axis_significance_sigma: float,
) -> tuple[SourceCandidate, GaussianComponent]:
    """Apply the reviewed one-source/one-Gaussian compact association."""
    transformed = transform_compact_gaussian_fit(
        fit,
        metadata,
        deconvolution_relative_tolerance=deconvolution_relative_tolerance,
        extension_significance_sigma=extension_significance_sigma,
        deconvolution_axis_significance_sigma=(
            deconvolution_axis_significance_sigma
        ),
    )
    region_id = fit.moment.target.object_id
    source_id = f"source-{region_id}"
    gaussian_component_id = f"gaussian-{region_id}"
    spectrum = SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=metadata.reference_frequency_hz,
        coefficients=(),
    )
    source = SourceCandidate(
        source_id=source_id,
        island_id=fit.moment.target.island_id,
        position=transformed.position,
        flux=transformed.flux,
        spectral_model=spectrum,
        fitted_shape=transformed.fitted_shape,
        deconvolved_shape=transformed.deconvolved_shape,
        deconvolved_major_fwhm_degrees=(
            transformed.deconvolved_major_fwhm_degrees
        ),
        quality_flags=transformed.quality_flags,
        association_aperture_integrated_flux_jy=(
            fit.association_aperture.integrated_flux_jy
            if fit.association_aperture is not None
            else None
        ),
    )
    component = GaussianComponent(
        gaussian_component_id=gaussian_component_id,
        source_id=source_id,
        island_id=fit.moment.target.island_id,
        position=transformed.position,
        flux=transformed.flux,
        spectral_model=spectrum,
        fitted_shape=transformed.fitted_shape,
        deconvolved_shape=transformed.deconvolved_shape,
        deconvolved_major_fwhm_degrees=(
            transformed.deconvolved_major_fwhm_degrees
        ),
        quality_flags=transformed.quality_flags,
    )
    return source, component


def build_compact_catalogue_shard(
    results: Sequence[CompactIslandFitResult],
    metadata: ImageMetadata,
    *,
    deconvolution_relative_tolerance: float,
    extension_significance_sigma: float = 5.0,
    deconvolution_axis_significance_sigma: float = 5.0,
) -> CompactCatalogueShard:
    """Transform one coarse batch into a canonical scheduler-safe shard."""
    islands: list[Island] = []
    sources: list[SourceCandidate] = []
    components: list[GaussianComponent] = []
    omissions: list[CompactCatalogueOmission] = []
    for result in results:
        island = _island_record(result, metadata)
        if isinstance(island, CompactCatalogueOmission):
            omissions.append(island)
        else:
            islands.append(island)
        for fit in result.region_fits:
            if not isinstance(fit, ValidCompactGaussianFit):
                omissions.append(
                    CompactCatalogueOmission(
                        object_id=fit.moment.target.object_id,
                        reason=fit.reason,
                    )
                )
                continue
            source, component = _associated_records(
                fit,
                metadata,
                deconvolution_relative_tolerance=(
                    deconvolution_relative_tolerance
                ),
                extension_significance_sigma=extension_significance_sigma,
                deconvolution_axis_significance_sigma=(
                    deconvolution_axis_significance_sigma
                ),
            )
            sources.append(source)
            components.append(component)
    return _canonical_shard(
        islands=islands,
        sources=sources,
        components=components,
        omissions=omissions,
    )


def complete_compact_catalogue(  # noqa: PLR0913
    *,
    catalogue_id: str,
    metadata: ImageMetadata,
    shards: Sequence[CompactCatalogueShard],
    deferred_island_ids: Sequence[str],
    config: CompactCatalogueConfig,
    position_epoch: str = "J2000",
) -> CompletedCompactCatalogue:
    """Build one bounded catalogue, failing closed on every omission."""
    source_count = sum(shard.record_count for shard in shards)
    if source_count > config.maximum_catalogue_records:
        raise IncompleteCompactCatalogueError(
            "compact source population exceeds the in-memory record limit"
        )
    reduction = reduce_compact_catalogue_shards(shards)
    merged = reduction.shard
    omissions = merged.omissions
    if omissions:
        raise IncompleteCompactCatalogueError(
            f"compact result contains {len(omissions)} fit omission(s)"
        )
    if deferred_island_ids:
        raise IncompleteCompactCatalogueError(
            f"compact result contains {len(deferred_island_ids)} deferred "
            "island(s) owned by Phase 5"
        )
    catalogue = SourceCatalogue.create(
        catalogue_id=catalogue_id,
        coordinate_frame="icrs",
        position_epoch=position_epoch,
        reference_frequency_hz=metadata.reference_frequency_hz,
        islands=merged.islands,
        sources=merged.sources,
        gaussian_components=merged.gaussian_components,
    )
    return CompletedCompactCatalogue(
        catalogue=catalogue,
        shard_count=reduction.input_shard_count,
        reduction_depth=reduction.reduction_depth,
        maximum_shard_record_count=(
            reduction.maximum_input_shard_record_count
        ),
    )
