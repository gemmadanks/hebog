# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Catalogue construction for the installed scientific composition."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.astrometry import (
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform_from_wcs,
    moment_equivalent_gaussian_shape,
    restoring_beam_in_icrs,
    transform_compact_fit_at_tangent,
)
from hebog.algorithms.component_measurement import ComponentMeasurements
from hebog.algorithms.extended_measurement import (
    DetectedSegmentPosition,
    assign_persistent_source_support,
    expand_detected_segment_labels,
    expand_source_measurement_labels,
    measure_detected_segment_position,
)
from hebog.algorithms.multiscale_association import (
    ScaleDetectionPlane,
    persistent_adjacent_scale_support,
)
from hebog.algorithms.source_association import (
    associate_components_by_multiscale_hierarchy,
    build_detection_component_records,
    constrain_source_memberships,
)
from hebog.data_models.catalogues import GaussianShape
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
from hebog.science.models import CatalogueEllipse, CatalogueSource

_PLANE_DIMENSIONS = 2
_MINIMUM_MOMENT_PIXELS = 3


def _validated_hebog_segment_planes(
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int64],
]:
    """Return aligned residual, validity, and exact segment labels."""
    image = np.asarray(image_jy_per_beam, dtype=np.float64)
    background = np.asarray(background_jy_per_beam, dtype=np.float64)
    valid = np.asarray(valid_pixels, dtype=np.bool_)
    label_values = np.asarray(component_labels)
    if label_values.ndim != _PLANE_DIMENSIONS or not np.issubdtype(
        label_values.dtype,
        np.integer,
    ):
        raise ValueError(
            "component labels must be a two-dimensional integer array"
        )
    if np.any(label_values < 0):
        raise ValueError("component labels must be non-negative")
    if image.shape != background.shape or image.shape != valid.shape:
        raise ValueError("Hebog segment planes must share one shape")
    if label_values.shape != image.shape:
        raise ValueError("Hebog segment labels must match the image")
    return (
        np.where(valid, image - background, np.nan),
        valid,
        np.asarray(label_values, dtype=np.int64),
    )


def _validated_position_signal(
    position_signal_jy_per_beam: npt.ArrayLike | None,
    *,
    shape: tuple[int, ...],
    valid_pixels: npt.NDArray[np.bool_],
) -> npt.NDArray[np.float64] | None:
    """Return one optional aligned real denoised measurement plane."""
    if position_signal_jy_per_beam is None:
        return None
    position_values = np.asarray(position_signal_jy_per_beam)
    if (
        position_values.ndim != _PLANE_DIMENSIONS
        or position_values.shape != shape
        or not np.issubdtype(position_values.dtype, np.number)
        or np.issubdtype(position_values.dtype, np.complexfloating)
    ):
        raise ValueError(
            "Hebog segment position signal must be an aligned real "
            "two-dimensional plane"
        )
    return np.where(
        valid_pixels,
        np.asarray(position_values, dtype=np.float64),
        np.nan,
    )


def _segment_position(
    residual: npt.NDArray[np.float64],
    denoised_position_signal: npt.NDArray[np.float64] | None,
    support: npt.NDArray[np.bool_],
    *,
    maximum_peak_to_mean_ratio: float,
) -> DetectedSegmentPosition:
    """Select original or denoised weights from measured concentration."""
    selected = residual
    if denoised_position_signal is not None:
        direct_weights = residual[support]
        if direct_weights.size:
            direct_mean = float(np.mean(direct_weights, dtype=np.float64))
            peak_to_mean = (
                float(np.max(direct_weights)) / direct_mean
                if np.isfinite(direct_mean) and direct_mean > 0.0
                else np.inf
            )
            if peak_to_mean <= maximum_peak_to_mean_ratio:
                selected = denoised_position_signal
    estimate = measure_detected_segment_position(selected, support)
    if not estimate.available and denoised_position_signal is not None:
        alternative = (
            residual
            if selected is denoised_position_signal
            else denoised_position_signal
        )
        selected = alternative
        estimate = measure_detected_segment_position(selected, support)
    return replace(
        estimate,
        weighting="denoised"
        if selected is denoised_position_signal
        else "signed-original",
    )


def _validated_centroid_labels(
    position_labels: npt.ArrayLike | None,
    aperture_labels: npt.NDArray[np.int64],
) -> npt.NDArray[np.int64]:
    """A position domain cannot invent owners outside the flux domain."""
    if position_labels is None:
        return aperture_labels
    values = np.asarray(position_labels)
    if (
        values.shape != aperture_labels.shape
        or not np.issubdtype(values.dtype, np.integer)
        or np.any(values < 0)
    ):
        raise ValueError(
            "position labels must be aligned non-negative integers"
        )
    if np.any((values > 0) & (values != aperture_labels)):
        raise ValueError(
            "position ownership must be a subset of aperture ownership"
        )
    return np.asarray(values, dtype=np.int64)


def _position_attribution(  # noqa: PLR0913, PLR0917
    residual: npt.NDArray[np.float64],
    position_signal: npt.NDArray[np.float64] | None,
    support: npt.NDArray[np.bool_],
    measurement_support: npt.NDArray[np.bool_],
    background: npt.ArrayLike,
    estimate: DetectedSegmentPosition,
    integrated_flux: float,
) -> SourcePositionDiagnostics:
    """Retain both centroid estimators and their distinct flux domain."""
    original = measure_detected_segment_position(residual, support)
    denoised = (
        measure_detected_segment_position(position_signal, support)
        if position_signal is not None
        else None
    )
    background_values = np.asarray(background)[measurement_support]
    signed_weight = float(np.sum(residual[support], dtype=np.float64))
    return SourcePositionDiagnostics(
        signed_original_xy=original.centroid_xy,
        denoised_xy=None if denoised is None else denoised.centroid_xy,
        selected_xy=estimate.centroid_xy,
        selection_reason="concentration-then-availability:"
        + estimate.weighting,
        unavailable_reason=estimate.unavailable_reason,
        position_pixel_count=int(np.count_nonzero(support)),
        aperture_pixel_count=int(np.count_nonzero(measurement_support)),
        position_signed_weight=signed_weight
        if np.isfinite(signed_weight)
        else None,
        aperture_signed_flux_jy=integrated_flux
        if np.isfinite(integrated_flux)
        else None,
        aperture_background_mean=float(np.mean(background_values))
        if background_values.size
        else None,
    )


def build_hebog_segment_catalogue(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
    aperture_tie_policy: Literal[
        "nearest-support", "canonical-source"
    ] = "nearest-support",
    position_labels: npt.ArrayLike | None = None,
    position_diagnostics: dict[int, SourcePositionDiagnostics] | None = None,
) -> tuple[CatalogueSource, ...]:
    """Measure catalogue rows for physically measurable blind segments.

    Labels remain the authoritative record of every accepted detection.
    Expanded-aperture photometry is preferred. When surrounding negative
    residuals make that aperture non-positive, the accepted owner's positive
    exact support provides an explicitly flagged conservative fallback.
    """
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
    )
    if (
        not np.isfinite(beam_major_fwhm_pixels)
        or not np.isfinite(beam_minor_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0.0
        or beam_minor_fwhm_pixels <= 0.0
    ):
        raise ValueError("Hebog segment beam axes must be positive")
    if (
        not np.isfinite(measurement_aperture_radius_beams)
        or measurement_aperture_radius_beams <= 0.0
    ):
        raise ValueError(
            "Hebog segment measurement aperture radius must be positive"
        )
    if (
        not np.isfinite(denoised_position_maximum_peak_to_mean_ratio)
        or denoised_position_maximum_peak_to_mean_ratio <= 1.0
    ):
        raise ValueError(
            "Hebog segment denoised-position peak-to-mean ratio must exceed 1"
        )
    if aperture_tie_policy not in {"nearest-support", "canonical-source"}:
        raise ValueError("Hebog segment aperture tie policy is unsupported")
    position_signal = _validated_position_signal(
        position_signal_jy_per_beam,
        shape=residual.shape,
        valid_pixels=valid,
    )
    centroid_labels = _validated_centroid_labels(position_labels, labels)
    aperture_builder = (
        expand_source_measurement_labels
        if aperture_tie_policy == "canonical-source"
        else expand_detected_segment_labels
    )
    measurement_labels = aperture_builder(
        labels,
        valid & np.isfinite(residual),
        radius_pixels=ceil(
            measurement_aperture_radius_beams * beam_major_fwhm_pixels
        ),
    )
    beam_area_pixels = (
        2.0
        * np.pi
        / (8.0 * np.log(2.0))
        * beam_major_fwhm_pixels
        * beam_minor_fwhm_pixels
    )
    celestial_wcs = WCS(header, relax=True).celestial
    output: list[CatalogueSource] = []
    for label_value in sorted(
        int(item) for item in np.unique(labels) if item > 0
    ):
        support = (
            (centroid_labels == label_value) & valid & np.isfinite(residual)
        )
        estimate = _segment_position(
            residual,
            position_signal,
            support,
            maximum_peak_to_mean_ratio=(
                denoised_position_maximum_peak_to_mean_ratio
            ),
        )
        measurement_support = measurement_labels == label_value
        integrated_weight = float(
            np.sum(residual[measurement_support], dtype=np.float64)
        )
        if position_diagnostics is not None:
            position_diagnostics[label_value] = _position_attribution(
                residual,
                position_signal,
                support,
                measurement_support,
                background_jy_per_beam,
                estimate,
                integrated_weight / beam_area_pixels,
            )
        if not estimate.available or estimate.centroid_xy is None:
            continue
        quality_flags: tuple[str, ...] = ()
        if not np.isfinite(integrated_weight) or integrated_weight <= 0.0:
            exact_positive_support = support & (residual > 0.0)
            integrated_weight = float(
                np.sum(
                    residual[exact_positive_support],
                    dtype=np.float64,
                )
            )
            quality_flags = (
                "association-aperture-nonpositive",
                "exact-owner-positive-residual-flux",
            )
        if not np.isfinite(integrated_weight) or integrated_weight <= 0.0:
            continue
        integrated_flux = integrated_weight / beam_area_pixels
        peak_flux = float(np.max(residual[support]))
        position = cast(
            Any, celestial_wcs.pixel_to_world(*estimate.centroid_xy)
        ).icrs
        identifier = f"hebog-segment-{label_value}"
        output.append(
            CatalogueSource(
                identifier=identifier,
                right_ascension_degrees=float(position.ra.deg),
                declination_degrees=float(position.dec.deg),
                peak_flux_jy_per_beam=peak_flux,
                integrated_flux_jy=integrated_flux,
                association_integrated_flux_jy=integrated_flux,
                deconvolution_status="unavailable",
                island_identifier=identifier,
                component_count=1,
                quality_flags=tuple(
                    sorted(
                        {
                            *quality_flags,
                            f"position-{estimate.weighting}",
                            "positive-exact-owner-flux"
                            if "exact-owner-positive-residual-flux"
                            in quality_flags
                            else "source-owned-signed-aperture",
                            "aperture-flux-uncertainty-unavailable",
                            "position-uncertainty-unavailable",
                        }
                    )
                ),
            )
        )
    return tuple(output)


def _catalogue_ellipse(shape: GaussianShape) -> CatalogueEllipse:
    """Translate one validated Gaussian-like shape into catalogue units."""
    return CatalogueEllipse(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=shape.position_angle_degrees,
        major_fwhm_error_degrees=shape.major_fwhm_error_degrees,
        minor_fwhm_error_degrees=shape.minor_fwhm_error_degrees,
        position_angle_error_degrees=shape.position_angle_error_degrees,
    )


def _segment_pixel_moment_covariance(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
) -> tuple[tuple[float, float], npt.NDArray[np.float64]] | None:
    """Return a positive centroid and exact-support covariance."""
    positive = (
        support
        & np.isfinite(residual_jy_per_beam)
        & (residual_jy_per_beam > 0.0)
    )
    if int(np.count_nonzero(positive)) < _MINIMUM_MOMENT_PIXELS:
        return None
    weights = residual_jy_per_beam[positive]
    weight = float(np.sum(weights, dtype=np.float64))
    if not np.isfinite(weight) or weight <= 0.0:
        return None
    y_pixels, x_pixels = np.nonzero(positive)
    centroid_x = float(np.sum(x_pixels * weights, dtype=np.float64) / weight)
    centroid_y = float(np.sum(y_pixels * weights, dtype=np.float64) / weight)
    delta_x = x_pixels - centroid_x
    delta_y = y_pixels - centroid_y
    covariance = np.asarray(
        (
            (
                np.sum(weights * delta_x * delta_x, dtype=np.float64) / weight,
                np.sum(weights * delta_x * delta_y, dtype=np.float64) / weight,
            ),
            (
                np.sum(weights * delta_x * delta_y, dtype=np.float64) / weight,
                np.sum(weights * delta_y * delta_y, dtype=np.float64) / weight,
            ),
        ),
        dtype=np.float64,
    )
    if (
        not np.all(np.isfinite(covariance))
        or float(np.linalg.det(covariance)) <= 0.0
    ):
        return None
    return (centroid_x, centroid_y), covariance


def _moment_shape_fields(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    celestial_wcs: WCS,
    beam: RestoringBeam,
) -> dict[str, object]:
    """Return catalogue fields for one moment-equivalent owner shape."""
    moment = _segment_pixel_moment_covariance(
        residual_jy_per_beam,
        support,
    )
    provenance = "segment-moment-equivalent-shape"
    if moment is None:
        return {
            "fitted_shape": None,
            "deconvolved_shape": None,
            "deconvolved_major_fwhm_degrees": None,
            "deconvolution_status": "unavailable",
            "quality_flags": (provenance, "shape-unavailable"),
        }
    centroid_xy, covariance = moment
    try:
        transform = local_tangent_plane_transform_from_wcs(
            celestial_wcs,
            centroid_xy,
        )
        fitted = moment_equivalent_gaussian_shape(covariance, transform)
        deconvolution = deconvolve_gaussian_shapes(
            fitted,
            restoring_beam_in_icrs(beam, celestial_wcs, centroid_xy),
            relative_tolerance=1e-10,
        )
    except (TypeError, ValueError, np.linalg.LinAlgError):
        return {
            "fitted_shape": None,
            "deconvolved_shape": None,
            "deconvolved_major_fwhm_degrees": None,
            "deconvolution_status": "unavailable",
            "quality_flags": (provenance, "shape-unavailable"),
        }
    flags = {provenance}
    if deconvolution.status in {"major-axis-only", "unresolved"}:
        flags.update(deconvolution.quality_flags)
    return {
        "fitted_shape": _catalogue_ellipse(fitted),
        "deconvolved_shape": (
            _catalogue_ellipse(deconvolution.shape)
            if deconvolution.shape is not None
            else None
        ),
        "deconvolved_major_fwhm_degrees": (
            deconvolution.major_axis_fwhm_degrees
        ),
        "deconvolution_status": deconvolution.status,
        "quality_flags": tuple(sorted(flags)),
    }


def build_hebog_segment_moment_catalogue(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
    aperture_tie_policy: Literal[
        "nearest-support", "canonical-source"
    ] = "nearest-support",
    position_labels: npt.ArrayLike | None = None,
    position_diagnostics: dict[int, SourcePositionDiagnostics] | None = None,
) -> tuple[CatalogueSource, ...]:
    """Publish exact-support moment shapes without changing photometry."""
    sources = build_hebog_segment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
        aperture_tie_policy=aperture_tie_policy,
        position_labels=position_labels,
        position_diagnostics=position_diagnostics,
    )
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        component_labels,
    )
    celestial_wcs = WCS(header, relax=True).celestial
    try:
        beam = RestoringBeam(
            major_fwhm_degrees=cast(float, header["BMAJ"]),
            minor_fwhm_degrees=cast(float, header["BMIN"]),
            position_angle_degrees=cast(float, header["BPA"]),
        )
    except (KeyError, TypeError, ValueError):
        return tuple(
            replace(
                source,
                quality_flags=(
                    "segment-moment-equivalent-shape",
                    "shape-unavailable",
                ),
            )
            for source in sources
        )
    by_identifier = {source.identifier: source for source in sources}
    output: list[CatalogueSource] = []
    for label_value in sorted(
        int(item) for item in np.unique(labels) if item > 0
    ):
        identifier = f"hebog-segment-{label_value}"
        source = by_identifier.get(identifier)
        if source is None:
            continue
        support = (labels == label_value) & valid
        shape_fields = _moment_shape_fields(
            residual,
            support,
            celestial_wcs,
            beam,
        )
        shape_fields["quality_flags"] = tuple(
            sorted(
                {
                    *source.quality_flags,
                    *cast(tuple[str, ...], shape_fields["quality_flags"]),
                }
            )
        )
        output.append(
            replace(
                source,
                **shape_fields,  # type: ignore[arg-type]
            )
        )
    return tuple(output)


@dataclass(frozen=True, slots=True)
class AssociatedMomentCatalogues:
    """Binding source rows plus retained immutable component diagnostics."""

    component_catalogue: tuple[CatalogueSource, ...]
    source_catalogue: tuple[CatalogueSource, ...]
    association: SourceAssociationResult
    measurement_dispositions: tuple[MeasurementDisposition, ...] = ()
    support_stages: tuple[tuple[str, npt.NDArray[np.bool_]], ...] = ()


def _source_label_plane(
    labels: npt.NDArray[np.int64],
    association: SourceAssociationResult,
) -> tuple[
    npt.NDArray[np.int32],
    dict[int, CatalogueSourceMembership],
]:
    """Map immutable component owners to canonical source-local labels."""
    records_by_id = {
        item.component_id: item for item in association.components
    }
    output = np.zeros(labels.shape, dtype=np.int32)
    memberships_by_label: dict[int, CatalogueSourceMembership] = {}
    for source_label, membership in enumerate(
        association.memberships,
        start=1,
    ):
        component_labels = tuple(
            records_by_id[component_id].label_value
            for component_id in membership.component_ids
        )
        output[np.isin(labels, component_labels)] = source_label
        memberships_by_label[source_label] = membership
    if np.any((labels > 0) & (output == 0)):
        raise ValueError("source memberships must own every component pixel")
    return output, memberships_by_label


def _fitted_component_row(
    index: int,
    fitted: ValidCompactGaussianFit,
    header: fits.Header,
) -> CatalogueSource:
    """Publish native model measurements, not threshold-truncated moments."""
    beam = RestoringBeam(
        cast(float, header["BMAJ"]),
        cast(float, header["BMIN"]),
        cast(float, header.get("BPA", 0.0)),
    )
    wcs = WCS(header, relax=True).celestial
    position = fitted.parameters.centroid_xy
    tangent = local_tangent_plane_transform_from_wcs(wcs, position)
    beam = restoring_beam_in_icrs(beam, wcs, position)
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
        fitted_shape=_catalogue_ellipse(sky.fitted_shape),
        deconvolved_shape=None
        if sky.deconvolved_shape is None
        else _catalogue_ellipse(sky.deconvolved_shape),
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
    replacements = {
        f"hebog-segment-{index}": _fitted_component_row(index, fitted, header)
        for index, fitted in measurements.fits
        if isinstance(fitted, ValidCompactGaussianFit)
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
                estimator=None
                if row is None
                else "source-owned-signed-aperture",
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


def _reconstructed_source_rows(
    measured_sources: tuple[CatalogueSource, ...],
    components: tuple[CatalogueSource, ...],
    membership_by_label: dict[int, CatalogueSourceMembership],
    association: SourceAssociationResult,
    *,
    require_signed_aperture: bool,
) -> tuple[CatalogueSource, ...]:
    """Choose each source's own estimator, independently of auxiliary rows."""
    measured_by_label: dict[int, CatalogueSource] = {}
    for row in measured_sources:
        prefix = "hebog-segment-"
        if not row.identifier.startswith(prefix):
            raise ValueError("measured source identity is malformed")
        measured_by_label[int(row.identifier[len(prefix) :])] = row
    by_id = {row.identifier: row for row in components}
    output = []
    for source_label, membership in membership_by_label.items():
        source = measured_by_label.get(source_label)
        # Source photometry always belongs to its observable aperture.
        # A native Gaussian integrates unobserved sky and describes a
        # different quantity even when its source has only one component.
        if source is None or (
            require_signed_aperture
            and ("exact-owner-positive-residual-flux" in source.quality_flags)
        ):
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
                            }
                        )
                        | {"shape-unavailable", "resolution-unavailable"}
                    )
                ),
            )
        flags = {*source.quality_flags, "reconstructed-catalogue-source"}
        # A component's fitted estimator and uncertainties do not describe
        # a source-owned aperture. Retain them with their component context.
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
        output.append(
            replace(
                source,
                identifier=membership.source_id,
                island_identifier=membership.source_id,
                component_count=len(membership.component_ids),
                quality_flags=tuple(sorted(flags)),
            )
        )
    return tuple(sorted(output, key=lambda item: item.identifier))


def build_hebog_reconstructed_source_catalogues(  # noqa: PLR0913, PLR0917
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    measurement_component_labels: npt.ArrayLike,
    direct_component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    scale_detection_planes: tuple[ScaleDetectionPlane, ...],
    header: fits.Header,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
    measurement_aperture_radius_beams: float = 4.0,
    position_signal_jy_per_beam: npt.ArrayLike | None = None,
    denoised_position_maximum_peak_to_mean_ratio: float = 3.0,
    component_measurements: ComponentMeasurements | None = None,
) -> AssociatedMomentCatalogues:
    """Measure each common-parent catalogue source exactly once.

    Direct seed labels define hierarchy identity. Recovered measurement labels
    define masks and apertures. Immutable component measurements remain
    diagnostic. Binding source rows are measured from a source-label plane
    before aperture expansion, so every observable pixel belongs to at most one
    source aperture.
    """
    residual, valid, labels = _validated_hebog_segment_planes(
        image_jy_per_beam,
        background_jy_per_beam,
        valid_pixels,
        measurement_component_labels,
    )
    direct = np.asarray(direct_component_labels)
    if (
        direct.ndim != labels.ndim
        or direct.shape != labels.shape
        or not np.issubdtype(direct.dtype, np.integer)
        or bool(np.any(direct < 0))
    ):
        raise ValueError(
            "direct component labels must be one aligned non-negative "
            "integer plane"
        )
    direct = np.asarray(direct, dtype=np.int64)
    if bool(np.any((direct > 0) & (~valid | (labels != direct)))):
        raise ValueError(
            "direct component ownership must be a valid subset of "
            "measurement ownership"
        )
    if set(np.unique(direct[direct > 0])) != set(
        np.unique(labels[labels > 0])
    ):
        raise ValueError(
            "direct and measurement component identities must match"
        )
    component_sources = build_hebog_segment_moment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid,
        labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
    )
    records = build_detection_component_records(direct, residual, valid)
    component_sources, _ = _apply_component_measurements(
        component_sources,
        component_measurements,
        header,
    )
    association = associate_components_by_multiscale_hierarchy(
        records,
        direct,
        scale_detection_planes,
        valid,
        significant_multiscale_support=significant_multiscale_support,
    )
    hierarchy = association
    if component_measurements is not None:
        association = constrain_source_memberships(
            association,
            (
                *component_measurements.compact_groups,
                *component_measurements.extended_groups,
            ),
        )
    stable_components = _stable_component_catalogue(
        component_sources,
        association,
    )
    source_labels, membership_by_label = _source_label_plane(
        labels,
        association,
    )
    persistent_support = persistent_adjacent_scale_support(
        scale_detection_planes
    )
    if (
        component_measurements is not None
        and component_measurements.measurement_support is not None
    ):
        persistent_support = (
            persistent_support | component_measurements.measurement_support
        )
    source_measurement_labels = assign_persistent_source_support(
        source_labels,
        persistent_support,
        valid,
    )
    source_positions: dict[int, SourcePositionDiagnostics] = {}
    measured_sources = build_hebog_segment_moment_catalogue(
        image_jy_per_beam,
        background_jy_per_beam,
        valid,
        source_measurement_labels,
        header,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        measurement_aperture_radius_beams=measurement_aperture_radius_beams,
        position_signal_jy_per_beam=position_signal_jy_per_beam,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
        aperture_tie_policy="canonical-source",
        # Measurement-only wings extend flux, not source-position support.
        position_labels=source_labels,
        position_diagnostics=source_positions,
    )
    output = _reconstructed_source_rows(
        measured_sources,
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
    support_stages = (
        (
            ("persistent", persistent_support),
            ("source-union", source_labels > 0),
            ("source-owned-persistent", source_measurement_labels > 0),
            (
                "source-measurement",
                expand_source_measurement_labels(
                    source_measurement_labels,
                    valid,
                    radius_pixels=ceil(
                        measurement_aperture_radius_beams
                        * beam_major_fwhm_pixels
                    ),
                )
                > 0,
            ),
        )
        if component_measurements is not None
        else ()
    )
    for _, mask in support_stages:
        mask.setflags(write=False)
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
        support_stages=support_stages,
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
