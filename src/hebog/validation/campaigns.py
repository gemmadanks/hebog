"""Reproducible Phase 4 same-image campaign diagnostics and assembly."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np

from hebog.algorithms.astrometry import (
    compact_geometry_at_pixel,
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform,
)
from hebog.algorithms.measurement import fitted_gaussian_integrated_flux_jy
from hebog.data_models.catalogues import GaussianShape
from hebog.validation.comparison import (
    CatalogueEllipse,
    CatalogueOutlierThresholds,
    CatalogueSource,
    compare_catalogues,
)
from hebog.validation.datasets import (
    AssociationTruthGroup,
    DatasetRecord,
    SyntheticRecipe,
    SyntheticSource,
)
from hebog.validation.diagnostics import source_pair_diagnostics
from hebog.validation.evidence import (
    AssociationPairDiagnostic,
    CampaignImplementationEvidence,
    CampaignRealizationDiagnostic,
    EvidenceStatus,
    ScientificCampaignEvidence,
    SourcePairDiagnostic,
)
from hebog.validation.materialization import synthetic_image_metadata

_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))
_MINIMUM_CAMPAIGN_IMPLEMENTATIONS = 2


@dataclass(frozen=True, slots=True)
class _DiagnosticPolicy:
    """Comparison quantities shared by source-level diagnostic rows."""

    outlier_thresholds: CatalogueOutlierThresholds
    beam_fwhm_degrees: float
    maximum_separation_beams: float
    position_angle_minimum_axis_ratio: float


def _ellipse_from_pixel_covariance(
    covariance: np.ndarray,
    jacobian_degrees_per_pixel: np.ndarray,
) -> CatalogueEllipse:
    """Transform an analytic pixel covariance into a sky ellipse."""
    sky_covariance = (
        jacobian_degrees_per_pixel @ covariance @ jacobian_degrees_per_pixel.T
    )
    eigenvalues, eigenvectors = np.linalg.eigh(sky_covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    position_angle = (
        0.0
        if np.isclose(
            eigenvalues[major_index],
            eigenvalues[minor_index],
            rtol=1e-12,
        )
        else float(
            np.rad2deg(np.arctan2(major_vector[0], major_vector[1])) % 180.0
        )
    )
    return CatalogueEllipse(
        major_fwhm_degrees=float(
            np.sqrt(eigenvalues[major_index]) * _FWHM_PER_SIGMA
        ),
        minor_fwhm_degrees=float(
            np.sqrt(eigenvalues[minor_index]) * _FWHM_PER_SIGMA
        ),
        position_angle_degrees=position_angle,
    )


def phase_four_truth_source(
    source: SyntheticSource,
    dataset: DatasetRecord,
    *,
    identifier: str,
) -> CatalogueSource:
    """Transform one analytic emitter to the canonical Phase 4 truth view."""
    metadata = synthetic_image_metadata(dataset)
    centroid_xy = (source.x_pixel, source.y_pixel)
    transform = local_tangent_plane_transform(metadata, centroid_xy)
    angle = np.deg2rad(source.rotation_degrees_counterclockwise_from_x)
    major = np.asarray([np.cos(angle), np.sin(angle)])
    minor = np.asarray([-np.sin(angle), np.cos(angle)])
    pixel_covariance = source.major_sigma_pixels**2 * np.outer(
        major,
        major,
    ) + source.minor_sigma_pixels**2 * np.outer(minor, minor)
    fitted = _ellipse_from_pixel_covariance(
        pixel_covariance,
        np.asarray(transform.jacobian_degrees_per_pixel),
    )
    fitted_shape = GaussianShape(
        major_fwhm_degrees=fitted.major_fwhm_degrees,
        minor_fwhm_degrees=fitted.minor_fwhm_degrees,
        position_angle_degrees=fitted.position_angle_degrees,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    deconvolution = deconvolve_gaussian_shapes(
        fitted_shape,
        metadata.beam,
        relative_tolerance=1e-10,
    )
    deconvolved = (
        CatalogueEllipse(
            major_fwhm_degrees=deconvolution.shape.major_fwhm_degrees,
            minor_fwhm_degrees=deconvolution.shape.minor_fwhm_degrees,
            position_angle_degrees=(
                deconvolution.shape.position_angle_degrees
            ),
        )
        if deconvolution.shape is not None
        else None
    )
    deconvolved_major = deconvolution.major_axis_fwhm_degrees
    geometry = compact_geometry_at_pixel(metadata, centroid_xy)
    free_integrated_flux = fitted_gaussian_integrated_flux_jy(
        amplitude_jy_per_beam=source.peak_flux_jy_per_beam,
        major_sigma_pixels=source.major_sigma_pixels,
        minor_sigma_pixels=source.minor_sigma_pixels,
        geometry=geometry,
    )
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=transform.position.right_ascension_degrees,
        declination_degrees=transform.position.declination_degrees,
        peak_flux_jy_per_beam=source.peak_flux_jy_per_beam,
        integrated_flux_jy=(
            source.peak_flux_jy_per_beam
            if deconvolution.status == "unresolved"
            else free_integrated_flux
        ),
        fitted_shape=fitted,
        deconvolved_shape=deconvolved,
        deconvolved_major_fwhm_degrees=deconvolved_major,
        deconvolution_status=deconvolution.status,
        island_identifier=identifier,
        component_count=1,
        quality_flags=(
            deconvolution.quality_flags
            if deconvolution.status in {"major-axis-only", "unresolved"}
            else ()
        ),
    )


def canonicalize_phase_four_catalogue(
    sources: Sequence[CatalogueSource],
) -> tuple[CatalogueSource, ...]:
    """Apply Rapthor's unresolved peak-as-total compatibility convention."""
    return tuple(
        replace(
            source,
            integrated_flux_jy=source.peak_flux_jy_per_beam,
            integrated_flux_error_jy=source.peak_flux_error_jy_per_beam,
        )
        if source.deconvolution_status == "unresolved"
        else source
        for source in sources
    )


def _association_truth_source(
    group: AssociationTruthGroup,
    recipe: SyntheticRecipe,
    dataset: DatasetRecord,
) -> CatalogueSource:
    """Return matching truth for one observable association group."""
    if group.resolution_class == "individually-resolvable":
        truth = phase_four_truth_source(
            recipe.sources[group.source_indices[0]],
            dataset,
            identifier=group.identifier,
        )
        point_indices = next(
            (
                stratum.source_indices
                for stratum in dataset.classification_strata
                if stratum.identifier == "shape-unresolved"
            ),
            (),
        )
        if group.source_indices[0] in point_indices:
            return replace(
                truth,
                integrated_flux_jy=truth.peak_flux_jy_per_beam,
                deconvolved_shape=None,
                deconvolved_major_fwhm_degrees=None,
                deconvolution_status="unresolved",
                quality_flags=("unresolved",),
            )
        return truth
    metadata = synthetic_image_metadata(dataset)
    transform = local_tangent_plane_transform(
        metadata,
        group.reference_position_xy,
    )
    geometry = compact_geometry_at_pixel(
        metadata,
        group.reference_position_xy,
    )
    integrated_flux = (
        group.reference_integrated_brightness_jy_pixels_per_beam
        * geometry.pixel_solid_angle_steradians
        / geometry.restoring_beam_solid_angle_steradians
    )
    return CatalogueSource(
        identifier=group.identifier,
        right_ascension_degrees=transform.position.right_ascension_degrees,
        declination_degrees=transform.position.declination_degrees,
        peak_flux_jy_per_beam=integrated_flux,
        integrated_flux_jy=integrated_flux,
        deconvolution_status="unavailable",
        island_identifier=group.identifier,
        component_count=len(group.source_indices),
    )


def _group_strata(
    dataset: DatasetRecord,
    group: AssociationTruthGroup,
) -> tuple[str, ...]:
    """Return canonical group-level scientific strata."""
    return tuple(
        sorted(
            {
                group.resolution_class,
                *(
                    stratum.identifier
                    for stratum in dataset.association_group_strata
                    if group.identifier in stratum.group_identifiers
                ),
            }
        )
    )


def _source_strata(
    dataset: DatasetRecord,
    group: AssociationTruthGroup,
) -> tuple[str, ...]:
    """Return all canonical source-level scientific strata."""
    source_index = group.source_indices[0]
    return tuple(
        sorted(
            {
                group.resolution_class,
                *(
                    stratum.identifier
                    for stratum in dataset.canonical_source_strata()
                    if source_index in stratum.source_indices
                ),
            }
        )
    )


def _association_diagnostics(
    dataset: DatasetRecord,
    truth: Sequence[CatalogueSource],
    candidate: Sequence[CatalogueSource],
    policy: _DiagnosticPolicy,
) -> tuple[
    tuple[AssociationPairDiagnostic, ...],
    dict[str, str],
]:
    """Match all observable truth groups and retain every decision."""
    association_candidate = tuple(
        replace(
            source,
            integrated_flux_jy=source.association_integrated_flux_jy,
        )
        if source.association_integrated_flux_jy is not None
        else source
        for source in candidate
    )
    report = compare_catalogues(
        truth,
        association_candidate,
        beam_fwhm_degrees=policy.beam_fwhm_degrees,
        maximum_separation_beams=policy.maximum_separation_beams,
        position_angle_minimum_axis_ratio=(
            policy.position_angle_minimum_axis_ratio
        ),
    )
    groups = {
        group.identifier: group for group in dataset.association_truth_groups
    }
    matches = {match.reference_identifier: match for match in report.matches}
    rows: list[AssociationPairDiagnostic] = []
    matched_candidates: dict[str, str] = {}
    for truth_source in truth:
        group = groups[truth_source.identifier]
        match = matches.get(truth_source.identifier)
        if match is None:
            rows.append(
                AssociationPairDiagnostic(
                    decision="unmatched-truth-group",
                    truth_group_identifier=group.identifier,
                    resolution_class=group.resolution_class,
                    truth_strata=_group_strata(dataset, group),
                )
            )
            continue
        matched_candidates[group.identifier] = match.candidate_identifier
        rows.append(
            AssociationPairDiagnostic(
                decision="matched",
                truth_group_identifier=group.identifier,
                candidate_identifier=match.candidate_identifier,
                resolution_class=group.resolution_class,
                truth_strata=_group_strata(dataset, group),
                separation_beam_fwhm=match.separation_beam_fwhm,
                integrated_flux_fractional_difference=(
                    match.integrated_flux_fractional_difference
                ),
            )
        )
    candidate_by_identifier = {
        source.identifier: source for source in association_candidate
    }
    rows.extend(
        AssociationPairDiagnostic(
            decision="unmatched-candidate",
            candidate_identifier=identifier,
        )
        for identifier in report.unmatched_candidate_identifiers
        if identifier in candidate_by_identifier
    )
    return tuple(rows), matched_candidates


def _source_diagnostics(
    dataset: DatasetRecord,
    truth_by_group: dict[str, CatalogueSource],
    candidate_by_identifier: dict[str, CatalogueSource],
    matched_candidates: dict[str, str],
    policy: _DiagnosticPolicy,
) -> tuple[SourcePairDiagnostic, ...]:
    """Diagnose individually resolvable associations without rematching."""
    rows: list[SourcePairDiagnostic] = []
    marginal_groups = {
        group.identifier
        for group in dataset.association_truth_groups
        if group.source_indices[0]
        in next(
            (
                stratum.source_indices
                for stratum in dataset.classification_strata
                if stratum.identifier == "shape-marginal-resolved"
            ),
            (),
        )
    }
    for group in dataset.association_truth_groups:
        if group.resolution_class != "individually-resolvable":
            continue
        truth_source = truth_by_group[group.identifier]
        candidate_identifier = matched_candidates.get(group.identifier)
        paired_candidate = (
            ()
            if candidate_identifier is None
            else (candidate_by_identifier[candidate_identifier],)
        )
        report = compare_catalogues(
            (truth_source,),
            paired_candidate,
            beam_fwhm_degrees=policy.beam_fwhm_degrees,
            maximum_separation_beams=policy.maximum_separation_beams,
            outlier_thresholds=policy.outlier_thresholds,
            position_angle_minimum_axis_ratio=(
                policy.position_angle_minimum_axis_ratio
            ),
        )
        rows.extend(
            source_pair_diagnostics(
                (truth_source,),
                paired_candidate,
                report,
                truth_strata_by_identifier={
                    group.identifier: _source_strata(dataset, group)
                },
                ungated_catastrophic_metrics_by_truth_identifier=(
                    {
                        group.identifier: frozenset({"integrated-flux"}),
                    }
                    if group.identifier in marginal_groups
                    else {}
                ),
                position_angle_minimum_axis_ratio=(
                    policy.position_angle_minimum_axis_ratio
                ),
            )
        )
    return tuple(rows)


def diagnose_phase_four_realization(  # noqa: PLR0913
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    candidate: Sequence[CatalogueSource],
    *,
    implementation_identifier: str,
    outlier_thresholds: CatalogueOutlierThresholds,
    position_angle_minimum_axis_ratio: float,
    maximum_separation_beams: float = 0.5,
) -> CampaignRealizationDiagnostic:
    """Build complete source and group diagnostics for one shared image."""
    raw_candidate = tuple(candidate)
    canonical_candidate = canonicalize_phase_four_catalogue(raw_candidate)
    metadata = synthetic_image_metadata(dataset)
    truth = tuple(
        _association_truth_source(group, recipe, dataset)
        for group in dataset.association_truth_groups
    )
    truth_by_group = {source.identifier: source for source in truth}
    candidate_by_identifier = {
        source.identifier: source for source in canonical_candidate
    }
    policy = _DiagnosticPolicy(
        outlier_thresholds=outlier_thresholds,
        beam_fwhm_degrees=metadata.beam.major_fwhm_degrees,
        maximum_separation_beams=maximum_separation_beams,
        position_angle_minimum_axis_ratio=position_angle_minimum_axis_ratio,
    )
    association_rows, matched_candidates = _association_diagnostics(
        dataset,
        truth,
        raw_candidate,
        policy,
    )
    source_rows = _source_diagnostics(
        dataset,
        truth_by_group,
        candidate_by_identifier,
        matched_candidates,
        policy,
    )
    return CampaignRealizationDiagnostic(
        implementation_identifier=implementation_identifier,
        seed=recipe.seed,
        status="success",
        candidate_count=len(raw_candidate),
        association_pairs=association_rows,
        source_pairs=source_rows,
    )


def compile_scientific_campaign(
    *,
    run_id: str,
    shards: Sequence[CampaignImplementationEvidence],
    captured_at: datetime | None = None,
) -> ScientificCampaignEvidence:
    """Merge isolated candidate and reference shards into paired evidence."""
    if len(shards) < _MINIMUM_CAMPAIGN_IMPLEMENTATIONS:
        raise ValueError("campaign compilation requires at least two shards")
    first = shards[0]
    if first.implementation.role != "candidate":
        raise ValueError("candidate implementation shard must be first")
    for shard in shards[1:]:
        if (
            shard.dataset != first.dataset
            or shard.configuration_sha256 != first.configuration_sha256
            or shard.comparison_protocol_sha256
            != first.comparison_protocol_sha256
        ):
            raise ValueError("campaign shard provenance differs")
        if tuple(item.seed for item in shard.realizations) != tuple(
            item.seed for item in first.realizations
        ):
            raise ValueError("campaign shard seeds differ")
    status = (
        EvidenceStatus.REVIEWED
        if all(shard.status is EvidenceStatus.REVIEWED for shard in shards)
        else EvidenceStatus.EXPLORATORY
    )
    realization_by_implementation = {
        shard.implementation.identifier: {
            realization.seed: realization for realization in shard.realizations
        }
        for shard in shards
    }
    implementations = tuple(shard.implementation for shard in shards)
    realizations = tuple(
        realization_by_implementation[implementation.identifier][seed]
        for seed in (item.seed for item in first.realizations)
        for implementation in implementations
    )
    return ScientificCampaignEvidence(
        schema_version=1,
        evidence_type="scientific-campaign",
        run_id=run_id,
        captured_at=captured_at or max(shard.captured_at for shard in shards),
        status=status,
        dataset=first.dataset,
        configuration_sha256=first.configuration_sha256,
        comparison_protocol_sha256=first.comparison_protocol_sha256,
        implementations=implementations,
        realizations=realizations,
    )
