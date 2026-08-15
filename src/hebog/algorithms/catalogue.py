# pyright: reportMissingTypeStubs=false
"""Deterministic compact association and bounded catalogue construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from astropy.wcs import WCS

from hebog.algorithms.astrometry import (
    celestial_wcs_from_metadata,
    compact_geometry_at_pixel,
    local_tangent_plane_transform,
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
    FluxMeasurement,
    GaussianComponent,
    Island,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.fitting import (
    CompactIslandFitResult,
    FailedCompactGaussianFit,
    UnavailableCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import ImageMetadata
from hebog.data_models.measurement import (
    ShapeUnavailableMomentMeasurement,
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
    celestial_wcs: WCS,
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
    geometry = compact_geometry_at_pixel(
        metadata,
        position_xy,
        celestial_wcs=celestial_wcs,
    )
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


def _associated_records(  # noqa: PLR0913
    fit: ValidCompactGaussianFit,
    metadata: ImageMetadata,
    celestial_wcs: WCS,
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
        celestial_wcs=celestial_wcs,
    )
    component_pixel_fit = fit
    if fit.gaussian_component_fit is not None:
        component_fit = fit.gaussian_component_fit
        component_pixel_fit = replace(
            fit,
            parameters=component_fit.parameters,
            uncertainty=component_fit.uncertainty,
            diagnostics=component_fit.diagnostics,
            quality_flags=component_fit.quality_flags,
            association_aperture=None,
            gaussian_component_fit=None,
        )
    transformed_component = transform_compact_gaussian_fit(
        component_pixel_fit,
        metadata,
        deconvolution_relative_tolerance=deconvolution_relative_tolerance,
        extension_significance_sigma=extension_significance_sigma,
        deconvolution_axis_significance_sigma=(
            deconvolution_axis_significance_sigma
        ),
        celestial_wcs=celestial_wcs,
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
        position=transformed_component.position,
        flux=transformed_component.fitted_flux,
        spectral_model=spectrum,
        fitted_shape=transformed_component.fitted_shape,
        deconvolved_shape=transformed_component.deconvolved_shape,
        deconvolved_major_fwhm_degrees=(
            transformed_component.deconvolved_major_fwhm_degrees
        ),
        quality_flags=transformed_component.quality_flags,
    )
    return source, component


def _moment_source_record(
    fit: FailedCompactGaussianFit | UnavailableCompactGaussianFit,
    metadata: ImageMetadata,
    celestial_wcs: WCS,
) -> SourceCandidate:
    """Retain measured region photometry when no Gaussian is publishable."""
    moment = fit.moment
    if isinstance(moment, ValidMomentMeasurement):
        position_xy = moment.initializer.centroid_xy
    elif isinstance(moment, ShapeUnavailableMomentMeasurement):
        position_xy = (
            float(moment.photometry.peak_position_xy[0]),
            float(moment.photometry.peak_position_xy[1]),
        )
    else:
        raise ValueError("moment source requires finite region photometry")
    transform = local_tangent_plane_transform(
        metadata,
        position_xy,
        celestial_wcs=celestial_wcs,
    )
    region_id = moment.target.object_id
    return SourceCandidate(
        source_id=f"source-{region_id}",
        island_id=moment.target.island_id,
        position=transform.position,
        flux=FluxMeasurement(
            peak_flux_jy_per_beam=(
                moment.photometry.peak_brightness_jy_per_beam
            ),
            peak_flux_error_jy_per_beam=None,
            integrated_flux_jy=(
                moment.photometry.owned_pixel_integrated_flux_jy
            ),
            integrated_flux_error_jy=None,
            local_rms_jy_per_beam=(moment.photometry.local_rms_jy_per_beam),
        ),
        spectral_model=SpectralModel(
            kind="reference-frequency-only",
            reference_frequency_hz=metadata.reference_frequency_hz,
            coefficients=(),
        ),
        fitted_shape=None,
        deconvolved_shape=None,
        quality_flags=tuple(
            sorted(
                {
                    *fit.quality_flags,
                    fit.reason,
                    "fitted-shape-unavailable",
                    "moment-measurement",
                }
            )
        ),
    )


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
    celestial_wcs = celestial_wcs_from_metadata(metadata)
    for result in results:
        island = _island_record(result, metadata, celestial_wcs)
        if isinstance(island, CompactCatalogueOmission):
            omissions.append(island)
        else:
            islands.append(island)
        for fit in result.region_fits:
            if not isinstance(fit, ValidCompactGaussianFit):
                if isinstance(fit.moment, UnavailableMomentMeasurement):
                    omissions.append(
                        CompactCatalogueOmission(
                            object_id=fit.moment.target.object_id,
                            reason=fit.reason,
                        )
                    )
                else:
                    sources.append(
                        _moment_source_record(fit, metadata, celestial_wcs)
                    )
                continue
            source, component = _associated_records(
                fit,
                metadata,
                celestial_wcs,
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
