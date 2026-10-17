# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Reconstructed source and component catalogues of the composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import fsum, sqrt
from typing import Literal, cast

from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.astrometry import (
    local_tangent_plane_transforms_from_wcs,
    restoring_beams_in_icrs,
    transform_compact_fit_at_tangent,
)
from hebog.algorithms.component_measurement import ComponentMeasurements
from hebog.data_models.astrometry import LocalTangentPlaneTransform
from hebog.data_models.fitting import ValidCompactGaussianFit
from hebog.data_models.images import RestoringBeam
from hebog.data_models.measurement_diagnostics import (
    AssociationDecisionDiagnostics,
    AssociationMergeEvidence,
    MeasurementDisposition,
    SourcePositionDiagnostics,
)
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    SourceAssociationResult,
)
from hebog.science.catalogue_rows import CatalogueSource
from hebog.science.segment_rows import catalogue_ellipse


@dataclass(frozen=True, slots=True)
class AssociatedMomentCatalogues:
    """Binding source rows plus retained immutable component diagnostics."""

    component_catalogue: tuple[CatalogueSource, ...]
    source_catalogue: tuple[CatalogueSource, ...]
    association: SourceAssociationResult
    measurement_dispositions: tuple[MeasurementDisposition, ...] = ()


def source_label_by_owner(
    association: SourceAssociationResult,
) -> dict[int, int]:
    """Map each immutable component owner to its canonical source label."""
    records_by_id = {
        item.component_id: item for item in association.components
    }
    return {
        records_by_id[component_id].label_value: source_label
        for source_label, membership in enumerate(
            association.memberships, start=1
        )
        for component_id in membership.component_ids
    }


def local_rms_by_object_id(
    association: SourceAssociationResult,
    *,
    component_local_rms: Mapping[int, float],
    source_local_rms: Mapping[int, float],
) -> dict[str, float]:
    """Name each measured owner's local noise by its catalogue identity.

    The row passes measure noise per label, because that is what the plane
    they read carries: components by their measurement label and sources by
    their canonical source label, which is the membership's position here.
    An owner whose support carries no usable estimate is absent, exactly as
    it is in the mappings this joins.
    """
    by_object_id = {
        record.component_id: component_local_rms[record.label_value]
        for record in association.components
        if record.label_value in component_local_rms
    }
    by_object_id.update(
        (membership.source_id, source_local_rms[source_label])
        for source_label, membership in enumerate(
            association.memberships, start=1
        )
        if source_label in source_local_rms
    )
    return by_object_id


def _fitted_component_row(
    index: int,
    fitted: ValidCompactGaussianFit,
    beam: RestoringBeam,
    tangent: LocalTangentPlaneTransform,
) -> CatalogueSource:
    """Publish native model measurements, not threshold-truncated moments.

    ``beam`` and ``tangent`` are this fit's own local geometry, which the
    caller derives for every fit in one conversion; see
    :func:`~hebog.algorithms.astrometry.local_tangent_plane_transforms_from_wcs`.
    """
    sky = transform_compact_fit_at_tangent(fitted, beam, tangent)
    return CatalogueSource(
        identifier=f"hebog-segment-{index}",
        right_ascension_degrees=sky.position.right_ascension_degrees,
        declination_degrees=sky.position.declination_degrees,
        right_ascension_error_degrees=sky.position.right_ascension_error_degrees,
        declination_error_degrees=sky.position.declination_error_degrees,
        peak_flux_jy_per_beam=sky.fitted_flux.peak_flux_jy_per_beam,
        integrated_flux_jy=sky.fitted_flux.integrated_flux_jy,
        peak_flux_error_jy_per_beam=sky.fitted_flux.peak_flux_error_jy_per_beam,
        integrated_flux_error_jy=sky.fitted_flux.integrated_flux_error_jy,
        fitted_shape=catalogue_ellipse(sky.fitted_shape),
        deconvolved_shape=None
        if sky.deconvolved_shape is None
        else catalogue_ellipse(sky.deconvolved_shape),
        deconvolved_major_fwhm_degrees=sky.deconvolved_major_fwhm_degrees,
        deconvolution_status=sky.deconvolution_status,
        quality_flags=tuple(
            sorted({*sky.quality_flags, "original-pixel-gaussian-model"})
        ),
    )


def _apply_component_measurements(
    sources: tuple[CatalogueSource, ...],
    measurements: ComponentMeasurements | None,
    header: fits.Header,
) -> tuple[tuple[CatalogueSource, ...], set[int]]:
    """Substitute original-pixel fits and identify compact model groups."""
    if measurements is None:
        return sources, set()
    # Parse the header once: each WCS parse repeats Astropy header fixes.
    wcs = WCS(header, relax=True).celestial
    native_beam = RestoringBeam(
        cast(float, header["BMAJ"]),
        cast(float, header["BMIN"]),
        cast(float, header.get("BPA", 0.0)),
    )
    fitted_rows = tuple(
        (index, fitted)
        for index, fitted in measurements.fits
        if isinstance(fitted, ValidCompactGaussianFit)
    )
    # One conversion for every fit. Astropy pays its frame machinery per
    # call, so transforming each centroid on its own costs more here than
    # the rest of the catalogue together.
    positions = tuple(
        fitted.parameters.centroid_xy for _, fitted in fitted_rows
    )
    replacements = {
        f"hebog-segment-{index}": _fitted_component_row(
            index, fitted, beam, tangent
        )
        for (index, fitted), beam, tangent in zip(
            fitted_rows,
            restoring_beams_in_icrs(native_beam, wcs, positions),
            local_tangent_plane_transforms_from_wcs(wcs, positions),
            strict=True,
        )
    }
    return (
        tuple(
            sorted(
                {
                    **{row.identifier: row for row in sources},
                    **replacements,
                }.values(),
                key=lambda row: row.identifier,
            )
        ),
        {index for group in measurements.compact_groups for index in group},
    )


def _measurement_dispositions(
    association: SourceAssociationResult,
    measurements: ComponentMeasurements,
    sources: tuple[CatalogueSource, ...],
    source_positions: dict[str, SourcePositionDiagnostics],
    hierarchy: SourceAssociationResult,
) -> tuple[MeasurementDisposition, ...]:
    """Retain all detections, even when no valid measured row exists."""
    by_label = dict(measurements.fits)
    hierarchy_groups = {
        component: membership.source_id
        for membership in hierarchy.memberships
        for component in membership.component_ids
    }
    compact_groups = {
        index: f"compact-{min(group)}"
        for group in (
            measurements.proposed_compact_groups or measurements.compact_groups
        )
        for index in group
    }
    extended_groups = {
        index: f"extended-{min(group)}"
        for group in measurements.extended_groups
        for index in group
    }
    dispositions = []
    for record in association.components:
        fitted = by_label.get(record.label_value)
        measured = isinstance(fitted, ValidCompactGaussianFit)
        reason = (
            None
            if measured
            else (
                fitted.reason if fitted is not None else "parent-work-deferred"
            )
        )
        deferred = reason in {"joint-fit-work-limit", "parent-work-deferred"}
        dispositions.append(
            MeasurementDisposition(
                object_kind="component",
                object_id=record.component_id,
                status="measured"
                if measured
                else ("deferred" if deferred else "unavailable"),
                estimator="original-pixel-gaussian-model"
                if measured
                else None,
                reason=reason,
                fit_diagnostics=getattr(fitted, "diagnostics", None),
                fit_covariance_available=(fitted.uncertainty is not None)
                if isinstance(fitted, ValidCompactGaussianFit)
                else None,
                association_diagnostics=AssociationDecisionDiagnostics(
                    hierarchy_group_id=hierarchy_groups[record.component_id],
                    compact_model_group_id=compact_groups.get(
                        record.label_value
                    ),
                    extended_group_id=extended_groups.get(record.label_value),
                    decision="extended-morphology"
                    if record.label_value in extended_groups
                    else (
                        "compact-model"
                        if record.label_value in compact_groups
                        else "independent-component"
                    ),
                ),
            )
        )
    by_id = {row.identifier: row for row in sources}
    component_ids = {
        row.label_value: row.component_id for row in association.components
    }
    evidence_by_source: dict[str, list[AssociationMergeEvidence]] = {}
    owner_by_component = {
        identifier: membership.source_id
        for membership in association.memberships
        for identifier in membership.component_ids
    }
    for evidence in measurements.grouping_evidence:
        members = tuple(
            sorted(component_ids[index] for index in evidence.component_labels)
        )
        owners = {owner_by_component[member] for member in members}
        if len(owners) != 1:
            raise ValueError("merge evidence disagrees with source membership")
        evidence_by_source.setdefault(owners.pop(), []).append(
            AssociationMergeEvidence(
                reason=evidence.reason,
                scale_ids=evidence.scale_ids,
                member_component_ids=members,
                protected_component_ids=tuple(
                    sorted(
                        component_ids[index]
                        for index in evidence.protected_labels
                    )
                ),
            )
        )
    for membership in association.memberships:
        row = by_id.get(membership.source_id)
        dispositions.append(
            MeasurementDisposition(
                object_kind="source",
                object_id=membership.source_id,
                status="unavailable" if row is None else "measured",
                estimator=_source_estimator(row),
                reason="non-positive-or-unavailable-signed-measurement"
                if row is None
                else None,
                member_component_ids=membership.component_ids,
                position_diagnostics=source_positions.get(
                    membership.source_id
                ),
                association_evidence=tuple(
                    evidence_by_source.get(membership.source_id, ())
                ),
            )
        )
    return tuple(
        sorted(
            dispositions, key=lambda item: (item.object_kind, item.object_id)
        )
    )


def _source_estimator(
    row: CatalogueSource | None,
) -> (
    Literal["source-owned-signed-aperture", "summed-fitted-component-flux"]
    | None
):
    """Name the estimator that produced a published source's flux.

    A continuum source's flux is the sum of its fitted components, except
    where it has none and falls back to the aperture it was measured in.
    The disposition records which, because the two describe different
    quantities: the aperture is observable flux, the sum integrates each
    fitted model over the whole plane.
    """
    if row is None:
        return None
    if "aperture-flux-without-fitted-component" in row.quality_flags:
        return "source-owned-signed-aperture"
    return "summed-fitted-component-flux"


def _summed_fitted_component_flux(
    components: tuple[CatalogueSource, ...],
) -> tuple[float, float | None]:
    """Return a source's summed fitted flux and its uncertainty.

    PyBDSF defines a source's total flux as the sum of its Gaussians, and
    Rapthor's photometry check compares Hebog against catalogues built that
    way, so the continuum source flux follows the same definition.

    The uncertainty is the quadrature sum, which treats the component fits as
    independent. It is published only when every component publishes one,
    because a partial sum would understate the total.
    """
    total = fsum(component.integrated_flux_jy for component in components)
    errors = [component.integrated_flux_error_jy for component in components]
    if any(error is None for error in errors):
        return total, None
    return total, sqrt(fsum(error * error for error in errors if error))


def _publishable_source_row(
    source: CatalogueSource | None,
    *,
    fitted: bool,
    require_signed_aperture: bool,
) -> CatalogueSource | None:
    """Return the measured row a source can publish, or ``None``.

    A row whose aperture summed to zero or below, as one can where
    neighbours' wings raise the background, carries the positive part of
    its owned pixels instead. A fitted source's flux is its summed fit, so
    only its aperture column goes unmeasured. Without a fit the aperture is
    the flux, and that positive-only sum is no substitute for it.
    """
    if (
        source is None
        or not require_signed_aperture
        or "exact-owner-positive-residual-flux" not in source.quality_flags
    ):
        return source
    if not fitted:
        return None
    return replace(
        source,
        association_integrated_flux_jy=None,
        quality_flags=tuple(
            sorted(
                set(source.quality_flags)
                - {
                    "exact-owner-positive-residual-flux",
                    "positive-exact-owner-flux",
                }
            )
        ),
    )


# Flags an aperture row carries for its centroid and its absent shape, which
# a source that publishes its one Gaussian's model no longer describes.
_APERTURE_POSITION_AND_SHAPE_FLAGS = frozenset(
    {
        "position-denoised",
        "position-signed-original",
        "position-uncertainty-unavailable",
        "shape-unavailable",
        "resolution-unavailable",
    }
)


def _one_gaussian_source_row(
    source: CatalogueSource, gaussian: CatalogueSource
) -> CatalogueSource:
    """Publish a source of one fitted Gaussian as that Gaussian.

    PyBDSF publishes such a source as its Gaussian, and Rapthor cuts on its
    position errors and deconvolved size. The fit's errors describe the
    fit's position, not the centroid, which can lie several of them away,
    so the source takes the whole model: position, errors, peak and the
    fitted and deconvolved shape, with the flags that qualify them. It keeps
    its own identity, aperture and flux, which for one Gaussian is already
    the fit's; the centroid stays in the position diagnostics.
    """
    return replace(
        source,
        right_ascension_degrees=gaussian.right_ascension_degrees,
        declination_degrees=gaussian.declination_degrees,
        right_ascension_error_degrees=gaussian.right_ascension_error_degrees,
        declination_error_degrees=gaussian.declination_error_degrees,
        peak_flux_jy_per_beam=gaussian.peak_flux_jy_per_beam,
        peak_flux_error_jy_per_beam=gaussian.peak_flux_error_jy_per_beam,
        fitted_shape=gaussian.fitted_shape,
        deconvolved_shape=gaussian.deconvolved_shape,
        deconvolved_major_fwhm_degrees=gaussian.deconvolved_major_fwhm_degrees,
        deconvolution_status=gaussian.deconvolution_status,
        quality_flags=tuple(
            sorted(
                (
                    set(source.quality_flags)
                    - _APERTURE_POSITION_AND_SHAPE_FLAGS
                )
                | (set(gaussian.quality_flags) - {"detection-component"})
            )
        ),
    )


def _reconstructed_source_rows(
    measured_sources: tuple[CatalogueSource, ...],
    components: tuple[CatalogueSource, ...],
    membership_by_label: dict[int, CatalogueSourceMembership],
    association: SourceAssociationResult,
    *,
    require_signed_aperture: bool,
) -> tuple[CatalogueSource, ...]:
    """Choose each source's own estimator, independently of auxiliary rows.

    A source of one fitted component publishes that Gaussian; any other
    publishes its aperture row with no claimed shape.
    """
    measured_by_label: dict[int, CatalogueSource] = {}
    for row in measured_sources:
        prefix = "hebog-segment-"
        if not row.identifier.startswith(prefix):
            raise ValueError("measured source identity is malformed")
        measured_by_label[int(row.identifier[len(prefix) :])] = row
    by_id = {row.identifier: row for row in components}
    output = []
    for source_label, membership in membership_by_label.items():
        fitted_members = tuple(
            component
            for component_id in membership.component_ids
            for component in (by_id.get(component_id),)
            if component is not None
            and "original-pixel-gaussian-model" in component.quality_flags
        )
        source = _publishable_source_row(
            measured_by_label.get(source_label),
            fitted=bool(fitted_members),
            require_signed_aperture=require_signed_aperture,
        )
        if source is None:
            continue
        if require_signed_aperture and (
            "original-pixel-gaussian-model" not in source.quality_flags
        ):
            # Threshold-support moments are descriptors, not fitted or
            # beam-deconvolved shapes of an irregular astrophysical source.
            source = replace(
                source,
                fitted_shape=None,
                deconvolved_shape=None,
                deconvolved_major_fwhm_degrees=None,
                deconvolution_status="unavailable",
                quality_flags=tuple(
                    sorted(
                        (
                            set(source.quality_flags)
                            - {
                                "segment-moment-equivalent-shape",
                                "resolved",
                                "unresolved",
                                "major-axis-only",
                                "marginal-deconvolution",
                            }
                        )
                        | {"shape-unavailable", "resolution-unavailable"}
                    )
                ),
            )
        flags = {*source.quality_flags, "reconstructed-catalogue-source"}
        # A component's fitted estimator and uncertainties do not describe
        # a source-owned aperture. Retain them with their component context;
        # only a source of one Gaussian takes them as its own, below.
        flags.update(
            f"member-{flag}"
            for component_id in membership.component_ids
            for component in (by_id.get(component_id),)
            if component is not None
            for flag in component.quality_flags
        )
        if any(
            component_id in association.ambiguous_component_ids
            for component_id in membership.component_ids
        ):
            flags.add("ambiguous-multiscale-parent")
        integrated_flux_jy = source.integrated_flux_jy
        integrated_flux_error_jy = source.integrated_flux_error_jy
        if require_signed_aperture:
            if fitted_members:
                integrated_flux_jy, integrated_flux_error_jy = (
                    _summed_fitted_component_flux(fitted_members)
                )
            else:
                flags.add("aperture-flux-without-fitted-component")
        row = replace(
            source,
            identifier=membership.source_id,
            island_identifier=membership.source_id,
            component_count=len(membership.component_ids),
            integrated_flux_jy=integrated_flux_jy,
            integrated_flux_error_jy=integrated_flux_error_jy,
            quality_flags=tuple(sorted(flags)),
        )
        # A source of several components, or of one fitted and others not,
        # keeps its aperture row: task 21 measures what that costs Rapthor's
        # agreement before the rule is extended.
        if len(membership.component_ids) == 1 and len(fitted_members) == 1:
            row = _one_gaussian_source_row(row, fitted_members[0])
        output.append(row)
    return tuple(sorted(output, key=lambda item: item.identifier))


def build_hebog_reconstructed_source_catalogues(  # noqa: PLR0913
    header: fits.Header,
    *,
    component_measurements: ComponentMeasurements | None = None,
    association: SourceAssociationResult,
    hierarchy: SourceAssociationResult,
    component_rows: tuple[CatalogueSource, ...],
    source_rows: tuple[CatalogueSource, ...],
    source_positions: Mapping[int, SourcePositionDiagnostics],
) -> AssociatedMomentCatalogues:
    """Assemble each common-parent catalogue source exactly once.

    Direct seed labels define hierarchy identity. Recovered measurement labels
    define masks and apertures. Immutable component measurements remain
    diagnostic. Binding source rows are measured from a source-label plane
    before aperture expansion, so every observable pixel belongs to at most one
    source aperture.

    This assembles records only: every row was measured by the stage that held
    the window it was measured in, and every plane the rows describe was
    checked by the core that wrote it — direct ownership against the
    measurement plane and the validity beside it, source ownership against the
    memberships the cores were given.
    """
    component_sources, _ = _apply_component_measurements(
        component_rows,
        component_measurements,
        header,
    )
    stable_components = _stable_component_catalogue(
        component_sources,
        association,
    )
    membership_by_label = dict(enumerate(association.memberships, start=1))
    output = _reconstructed_source_rows(
        source_rows,
        stable_components,
        membership_by_label,
        association,
        require_signed_aperture=component_measurements is not None,
    )
    if component_measurements is None and len(output) != len(
        association.memberships
    ):
        raise ValueError(
            "reconstructed source has no measurable catalogue row"
        )
    return AssociatedMomentCatalogues(
        component_catalogue=stable_components
        if component_measurements is None
        else tuple(
            row
            for row in stable_components
            if "original-pixel-gaussian-model" in row.quality_flags
        ),
        source_catalogue=output,
        association=association,
        measurement_dispositions=()
        if component_measurements is None
        else (
            _measurement_dispositions(
                association,
                component_measurements,
                tuple(output),
                {
                    membership.source_id: source_positions[label]
                    for label, membership in membership_by_label.items()
                    if label in source_positions
                },
                hierarchy,
            )
        ),
    )


def _stable_component_catalogue(
    sources: tuple[CatalogueSource, ...],
    association: SourceAssociationResult,
) -> tuple[CatalogueSource, ...]:
    """Replace task-local label identities with stable component identities."""
    by_label_identifier = {
        f"hebog-segment-{record.label_value}": record.component_id
        for record in association.components
    }
    output = tuple(
        replace(
            source,
            identifier=by_label_identifier[source.identifier],
            island_identifier=by_label_identifier[source.identifier],
            quality_flags=tuple(
                sorted({*source.quality_flags, "detection-component"})
            ),
        )
        for source in sources
    )
    return tuple(sorted(output, key=lambda item: item.identifier))
