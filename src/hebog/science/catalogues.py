# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Catalogue construction for the installed scientific composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import ceil, fsum, sqrt
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.astrometry import (
    deconvolve_gaussian_shapes,
    local_tangent_plane_transform_from_wcs,
    local_tangent_plane_transforms_from_wcs,
    moment_equivalent_gaussian_shape,
    restoring_beam_in_icrs,
    restoring_beams_in_icrs,
    transform_compact_fit_at_tangent,
)
from hebog.algorithms.component_measurement import ComponentMeasurements
from hebog.algorithms.extended_measurement import (
    DetectedSegmentPosition,
    SegmentWindow,
    connected_component_labels,
    expand_detected_segment_labels,
    expand_source_measurement_labels,
    measure_segment_position_pixels,
)
from hebog.algorithms.label_groups import label_windows
from hebog.data_models.astrometry import LocalTangentPlaneTransform
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
from hebog.science.models import (
    CatalogueEllipse,
    CatalogueIsland,
    CatalogueSource,
)

_PLANE_DIMENSIONS = 2
_MINIMUM_MOMENT_PIXELS = 3


def _validated_segment_labels(
    valid_pixels: npt.ArrayLike,
    component_labels: npt.ArrayLike,
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.int64]]:
    """Return validity and exact segment labels, checked against each other.

    A caller that measures nothing needs no image or background: the labels
    and the validity plane carry every shape this has to agree with.
    :func:`_validated_hebog_segment_planes` adds the residual and the planes
    it is computed from.
    """
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
    if label_values.shape != valid.shape:
        raise ValueError("Hebog segment labels must match the image")
    return valid, np.asarray(label_values, dtype=np.int64)


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
    valid, labels = _validated_segment_labels(valid_pixels, component_labels)
    image = np.asarray(image_jy_per_beam, dtype=np.float64)
    background = np.asarray(background_jy_per_beam, dtype=np.float64)
    if image.shape != background.shape or image.shape != valid.shape:
        raise ValueError("Hebog segment planes must share one shape")
    return np.where(valid, image - background, np.nan), valid, labels


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


def _segment_position(  # noqa: PLR0913
    y_pixels: npt.NDArray[np.int64],
    x_pixels: npt.NDArray[np.int64],
    residual: npt.NDArray[np.float64],
    denoised_position_signal: npt.NDArray[np.float64] | None,
    *,
    maximum_peak_to_mean_ratio: float,
    plane_shape_yx: tuple[int, int],
) -> DetectedSegmentPosition:
    """Select original or denoised weights from measured concentration.

    Every array holds the segment's support pixels in raster order, with
    coordinates in the image's pixel frame.
    """
    selected = residual
    if denoised_position_signal is not None and residual.size:
        direct_mean = float(np.mean(residual, dtype=np.float64))
        peak_to_mean = (
            float(np.max(residual)) / direct_mean
            if np.isfinite(direct_mean) and direct_mean > 0.0
            else np.inf
        )
        if peak_to_mean <= maximum_peak_to_mean_ratio:
            selected = denoised_position_signal
    estimate = measure_segment_position_pixels(
        y_pixels, x_pixels, selected, plane_shape_yx=plane_shape_yx
    )
    if not estimate.available and denoised_position_signal is not None:
        alternative = (
            residual
            if selected is denoised_position_signal
            else denoised_position_signal
        )
        selected = alternative
        estimate = measure_segment_position_pixels(
            y_pixels, x_pixels, selected, plane_shape_yx=plane_shape_yx
        )
    return replace(
        estimate,
        weighting="denoised"
        if selected is denoised_position_signal
        else "signed-original",
    )


def _label_window(
    windows: tuple[tuple[slice, slice] | None, ...], label_value: int
) -> tuple[slice, slice] | None:
    """Return one label's window, or ``None`` when it owns no pixel."""
    if label_value > len(windows):
        return None
    return windows[label_value - 1]


def _segment_crop(
    segment_windows: tuple[tuple[slice, slice] | None, ...],
    aperture_windows: tuple[tuple[slice, slice] | None, ...],
    label_value: int,
) -> tuple[slice, slice]:
    """Return the window holding one segment and its measurement aperture.

    A segment whose pixels are all invalid keeps no aperture, so the two
    windows are combined rather than assuming the aperture contains the
    segment.

    Raises:
        ValueError: If neither plane owns the label, which would leave the
            segment unmeasurable.
    """
    crops = [
        crop
        for crop in (
            _label_window(segment_windows, label_value),
            _label_window(aperture_windows, label_value),
        )
        if crop is not None
    ]
    if not crops:
        raise ValueError("Hebog segment labels must own at least one pixel")
    return (
        slice(
            min(crop[0].start for crop in crops),
            max(crop[0].stop for crop in crops),
        ),
        slice(
            min(crop[1].start for crop in crops),
            max(crop[1].stop for crop in crops),
        ),
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


def _position_attribution(
    pixels: SegmentPixels,
    support: npt.NDArray[np.bool_],
    estimate: DetectedSegmentPosition,
    integrated_flux: float,
    *,
    plane_shape_yx: tuple[int, int],
) -> SourcePositionDiagnostics:
    """Retain both centroid estimators and their distinct flux domain."""
    y_support = pixels.y[support]
    x_support = pixels.x[support]
    residual = pixels.residual[support]
    original = measure_segment_position_pixels(
        y_support, x_support, residual, plane_shape_yx=plane_shape_yx
    )
    denoised = (
        measure_segment_position_pixels(
            y_support,
            x_support,
            pixels.position_signal[support],
            plane_shape_yx=plane_shape_yx,
        )
        if pixels.position_signal is not None
        else None
    )
    background_values = pixels.background[pixels.aperture]
    signed_weight = float(np.sum(residual, dtype=np.float64))
    return SourcePositionDiagnostics(
        signed_original_xy=original.centroid_xy,
        denoised_xy=None if denoised is None else denoised.centroid_xy,
        selected_xy=estimate.centroid_xy,
        selection_reason="concentration-then-availability:"
        + estimate.weighting,
        unavailable_reason=estimate.unavailable_reason,
        position_pixel_count=int(np.count_nonzero(support)),
        aperture_pixel_count=int(np.count_nonzero(pixels.aperture)),
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
    background = np.asarray(background_jy_per_beam)
    # One pass gives every segment its aperture window, so the work below
    # costs each segment's own pixels instead of the whole image.
    aperture_windows = label_windows(measurement_labels)
    segment_windows = label_windows(labels)
    output: list[CatalogueSource] = []
    for label_value in sorted(
        int(item) for item in np.unique(labels) if item > 0
    ):
        crop = _segment_crop(segment_windows, aperture_windows, label_value)
        row = build_segment_row(
            residual[crop],
            None if position_signal is None else position_signal[crop],
            valid[crop],
            centroid_labels[crop],
            measurement_labels[crop],
            background[crop],
            celestial_wcs,
            label_value=label_value,
            window=SegmentWindow(
                origin_yx=(crop[0].start, crop[1].start),
                plane_shape_yx=residual.shape,
            ),
            beam_area_pixels=beam_area_pixels,
            denoised_position_maximum_peak_to_mean_ratio=(
                denoised_position_maximum_peak_to_mean_ratio
            ),
            position_diagnostics=position_diagnostics,
        )
        if row is not None:
            output.append(row)
    return tuple(output)


@dataclass(frozen=True, slots=True)
class SegmentRowMeasurement:
    """One segment's measured row, before its centroid has a sky position.

    ``centroid_xy`` is where the row's coordinate belongs, in the image's
    pixel frame, so a caller measuring many segments takes every centroid
    first and converts them together; see :func:`segment_row_at`.
    """

    label_value: int
    centroid_xy: tuple[float, float]
    peak_flux_jy_per_beam: float
    integrated_flux_jy: float
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SegmentPixels:
    """The pixels one segment's row reads, in raster order.

    A pixel is here when the segment holds it in its seeded ownership
    (``owned``) or in its expanded aperture (``aperture``); a caller may add
    others. Coordinates are in the image's pixel frame and every array is
    aligned with ``y``. Each reduction a row makes is over one of those two
    sets, so any such superset in raster order gives the same row: a window
    over the segment, or the pieces its cores return.
    """

    y: npt.NDArray[np.int64]
    x: npt.NDArray[np.int64]
    residual: npt.NDArray[np.float64]
    position_signal: npt.NDArray[np.float64] | None
    background: npt.NDArray[np.float64]
    valid: npt.NDArray[np.bool_]
    owned: npt.NDArray[np.bool_]
    aperture: npt.NDArray[np.bool_]


def measure_segment_row_pixels(  # noqa: PLR0913
    pixels: SegmentPixels,
    *,
    label_value: int,
    plane_shape_yx: tuple[int, int],
    beam_area_pixels: float,
    denoised_position_maximum_peak_to_mean_ratio: float,
    position_diagnostics: dict[int, SourcePositionDiagnostics] | None = None,
) -> SegmentRowMeasurement | None:
    """Measure one segment's catalogue row from its own pixels.

    This is the half that reads pixels, and it needs no WCS. Absence means
    the segment has no measurable row, not an error.
    """
    support = pixels.owned & pixels.valid & np.isfinite(pixels.residual)
    residual = pixels.residual[support]
    estimate = _segment_position(
        pixels.y[support],
        pixels.x[support],
        residual,
        None
        if pixels.position_signal is None
        else pixels.position_signal[support],
        maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
        plane_shape_yx=plane_shape_yx,
    )
    integrated_weight = float(
        np.sum(pixels.residual[pixels.aperture], dtype=np.float64)
    )
    # Emission this segment owns that no fitted model accounts for. A source
    # whose flux is the sum of its fits would otherwise lose it, because the
    # fits describe the compact parts and nothing describes the rest. This is
    # the residual after the models, not the residual outside their support:
    # a fit's support is the region it measured over, which covers emission
    # its model does not explain.
    if position_diagnostics is not None:
        position_diagnostics[label_value] = _position_attribution(
            pixels,
            support,
            estimate,
            integrated_weight / beam_area_pixels,
            plane_shape_yx=plane_shape_yx,
        )
    if not estimate.available or estimate.centroid_xy is None:
        return None
    quality_flags: tuple[str, ...] = ()
    if not np.isfinite(integrated_weight) or integrated_weight <= 0.0:
        integrated_weight = float(
            np.sum(residual[residual > 0.0], dtype=np.float64)
        )
        quality_flags = (
            "association-aperture-nonpositive",
            "exact-owner-positive-residual-flux",
        )
    if not np.isfinite(integrated_weight) or integrated_weight <= 0.0:
        return None
    return SegmentRowMeasurement(
        label_value=label_value,
        centroid_xy=estimate.centroid_xy,
        peak_flux_jy_per_beam=float(np.max(residual)),
        integrated_flux_jy=integrated_weight / beam_area_pixels,
        quality_flags=tuple(
            sorted(
                {
                    *quality_flags,
                    f"position-{estimate.weighting}",
                    "positive-exact-owner-flux"
                    if "exact-owner-positive-residual-flux" in quality_flags
                    else "source-owned-signed-aperture",
                    "aperture-flux-uncertainty-unavailable",
                    "position-uncertainty-unavailable",
                }
            )
        ),
    )


def measure_segment_row(  # noqa: PLR0913, PLR0917
    residual_window: npt.NDArray[np.float64],
    position_signal_window: npt.NDArray[np.float64] | None,
    valid_window: npt.NDArray[np.bool_],
    centroid_window: npt.NDArray[np.int64],
    aperture_window: npt.NDArray[np.int32],
    background_window: npt.NDArray[np.float64],
    *,
    label_value: int,
    window: SegmentWindow,
    beam_area_pixels: float,
    denoised_position_maximum_peak_to_mean_ratio: float,
    position_diagnostics: dict[int, SourcePositionDiagnostics] | None = None,
) -> SegmentRowMeasurement | None:
    """Measure one segment's catalogue row inside its own window.

    Every array covers that segment's exact support joined with its expanded
    aperture, which is the window :func:`_segment_crop` returns, so this work
    costs the segment's own pixels rather than the plane around it. The row
    is :func:`measure_segment_row_pixels` over the pixels of the window the
    segment owns or holds in its aperture.
    """
    owned = centroid_window == label_value
    aperture = aperture_window == label_value
    member = owned | aperture
    local_y, local_x = np.nonzero(member)
    return measure_segment_row_pixels(
        SegmentPixels(
            y=local_y + window.origin_yx[0],
            x=local_x + window.origin_yx[1],
            residual=residual_window[member],
            position_signal=None
            if position_signal_window is None
            else position_signal_window[member],
            background=np.asarray(background_window)[member],
            valid=valid_window[member],
            owned=owned[member],
            aperture=aperture[member],
        ),
        label_value=label_value,
        plane_shape_yx=window.plane_shape_yx,
        beam_area_pixels=beam_area_pixels,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
        position_diagnostics=position_diagnostics,
    )


def segment_row_at(
    measurement: SegmentRowMeasurement,
    *,
    right_ascension_degrees: float,
    declination_degrees: float,
) -> CatalogueSource:
    """Return one measured row at the sky position its centroid earns."""
    identifier = f"hebog-segment-{measurement.label_value}"
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=right_ascension_degrees,
        declination_degrees=declination_degrees,
        peak_flux_jy_per_beam=measurement.peak_flux_jy_per_beam,
        integrated_flux_jy=measurement.integrated_flux_jy,
        association_integrated_flux_jy=measurement.integrated_flux_jy,
        deconvolution_status="unavailable",
        island_identifier=identifier,
        component_count=1,
        quality_flags=measurement.quality_flags,
    )


def build_segment_row(  # noqa: PLR0913, PLR0917
    residual_window: npt.NDArray[np.float64],
    position_signal_window: npt.NDArray[np.float64] | None,
    valid_window: npt.NDArray[np.bool_],
    centroid_window: npt.NDArray[np.int64],
    aperture_window: npt.NDArray[np.int32],
    background_window: npt.NDArray[np.float64],
    celestial_wcs: WCS,
    *,
    label_value: int,
    window: SegmentWindow,
    beam_area_pixels: float,
    denoised_position_maximum_peak_to_mean_ratio: float,
    position_diagnostics: dict[int, SourcePositionDiagnostics] | None = None,
) -> CatalogueSource | None:
    """Measure and place one segment's row, one segment at a time.

    This is the readable reference for the batched path in
    :mod:`hebog.stages.catalogue_rows`, which converts every centroid of a
    batch together.
    """
    measurement = measure_segment_row(
        residual_window,
        position_signal_window,
        valid_window,
        centroid_window,
        aperture_window,
        background_window,
        label_value=label_value,
        window=window,
        beam_area_pixels=beam_area_pixels,
        denoised_position_maximum_peak_to_mean_ratio=(
            denoised_position_maximum_peak_to_mean_ratio
        ),
        position_diagnostics=position_diagnostics,
    )
    if measurement is None:
        return None
    position = cast(
        Any, celestial_wcs.pixel_to_world(*measurement.centroid_xy)
    ).icrs
    return segment_row_at(
        measurement,
        right_ascension_degrees=float(position.ra.deg),
        declination_degrees=float(position.dec.deg),
    )


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


def segment_moment_pixels(
    y_pixels: npt.NDArray[np.int64],
    x_pixels: npt.NDArray[np.int64],
    residual_jy_per_beam: npt.NDArray[np.float64],
) -> tuple[tuple[float, float], npt.NDArray[np.float64]] | None:
    """Return a positive centroid and covariance from support pixels alone.

    The arrays hold the segment's measured support in raster order, with
    coordinates in the image's pixel frame, so a segment too wide to read at
    once gives the moment its window would give, bit for bit.
    """
    positive = np.isfinite(residual_jy_per_beam) & (residual_jy_per_beam > 0.0)
    if int(np.count_nonzero(positive)) < _MINIMUM_MOMENT_PIXELS:
        return None
    weights = residual_jy_per_beam[positive]
    weight = float(np.sum(weights, dtype=np.float64))
    if not np.isfinite(weight) or weight <= 0.0:
        return None
    y_positive = y_pixels[positive]
    x_positive = x_pixels[positive]
    centroid_x = float(np.sum(x_positive * weights, dtype=np.float64) / weight)
    centroid_y = float(np.sum(y_positive * weights, dtype=np.float64) / weight)
    delta_x = x_positive - centroid_x
    delta_y = y_positive - centroid_y
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


def _segment_pixel_moment_covariance(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    *,
    window: SegmentWindow | None = None,
) -> tuple[tuple[float, float], npt.NDArray[np.float64]] | None:
    """Return a positive centroid and exact-support covariance.

    The planes may be one segment's window of the image; ``window`` then
    keeps the centroid in the image's pixel frame.
    """
    y_origin, x_origin = (0, 0) if window is None else window.origin_yx
    local_y, local_x = np.nonzero(support)
    return segment_moment_pixels(
        local_y + y_origin,
        local_x + x_origin,
        residual_jy_per_beam[support],
    )


_MOMENT_SHAPE_PROVENANCE = "segment-moment-equivalent-shape"


def unavailable_moment_shape_fields() -> dict[str, object]:
    """Return the fields of a segment whose shape cannot be measured."""
    return {
        "fitted_shape": None,
        "deconvolved_shape": None,
        "deconvolved_major_fwhm_degrees": None,
        "deconvolution_status": "unavailable",
        "quality_flags": (_MOMENT_SHAPE_PROVENANCE, "shape-unavailable"),
    }


def detection_island_identifier(first_pixel_yx: tuple[int, int]) -> str:
    """Name one detection island by the first pixel it owns.

    Raster order makes the first pixel canonical: it does not depend on how
    the mask was partitioned or in which order the tiles completed.

    Examples:
        >>> detection_island_identifier((12, 40))
        'island-detection-12-40'
    """
    return f"island-detection-{first_pixel_yx[0]}-{first_pixel_yx[1]}"


def measure_detection_island(
    residual_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    *,
    first_pixel_yx: tuple[int, int],
    beam_area_pixels: float,
) -> CatalogueIsland:
    """Summarise one island over the exact pixels its mask retains.

    Every array covers the window that holds the island, and ``support`` is
    that island alone: an island is mask connectivity, not owner support, so
    nothing here consults a label plane. The flux is the signed residual over
    those pixels, which is why an island row is reported without an
    uncertainty.

    Raises:
        ValueError: If the island retains no pixel in this window.
    """
    if not bool(np.any(support)):
        raise ValueError("detection island must retain at least one pixel")
    residual = residual_jy_per_beam[support]
    return CatalogueIsland(
        identifier=detection_island_identifier(first_pixel_yx),
        pixel_count=int(support.sum()),
        integrated_flux_jy=float(
            np.sum(residual, dtype=np.float64) / beam_area_pixels
        ),
        local_rms_jy_per_beam=float(np.median(rms_jy_per_beam[support])),
        mean_brightness_jy_per_beam=float(np.mean(residual)),
    )


@dataclass(frozen=True, slots=True)
class DetectionIslandCatalogue:
    """Every measured island and the islands each owner's support reaches."""

    islands: tuple[CatalogueIsland, ...]
    island_ids_by_owner: Mapping[int, tuple[str, ...]]


def build_detection_island_catalogue(
    residual_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    retained_mask: npt.NDArray[np.bool_],
    owner_labels: npt.NDArray[np.integer[Any]],
    *,
    beam_area_pixels: float,
) -> DetectionIslandCatalogue:
    """Measure every island of one complete retained mask, in raster order.

    This is the readable whole-plane reference for the tiled rounds in
    :mod:`hebog.stages.islands`, which label each core and reconcile the
    fragments instead of labelling the plane. Rows are ordered by the island's
    canonical first pixel, which is the order labelling a whole plane gives.

    ``owner_labels`` are the measurement labels of the components the
    catalogue publishes; an owner is linked to every island its retained
    support reaches, because published support can be split between islands.
    """
    labels = _connected_island_labels(retained_mask)
    windows = label_windows(labels)
    islands: list[CatalogueIsland] = []
    identifier_by_label: dict[int, str] = {}
    for label_value, crop in enumerate(windows, start=1):
        if crop is None:
            raise ValueError("detection islands must own at least one pixel")
        support = labels[crop] == label_value
        first = np.argwhere(support)[0]
        first_pixel_yx = (
            int(first[0]) + crop[0].start,
            int(first[1]) + crop[1].start,
        )
        island = measure_detection_island(
            residual_jy_per_beam[crop],
            rms_jy_per_beam[crop],
            support,
            first_pixel_yx=first_pixel_yx,
            beam_area_pixels=beam_area_pixels,
        )
        identifier_by_label[label_value] = island.identifier
        islands.append(island)
    return DetectionIslandCatalogue(
        islands=tuple(islands),
        island_ids_by_owner=island_ids_by_owner(
            _owner_island_pairs(labels, owner_labels, retained_mask),
            identifier_by_island_label=identifier_by_label,
        ),
    )


def _connected_island_labels(
    retained_mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Label one retained mask's eight-connected islands."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        connected_component_labels(
            retained_mask,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    return labels


def _owner_island_pairs(
    island_labels: npt.NDArray[np.int32],
    owner_labels: npt.NDArray[np.integer[Any]],
    retained_mask: npt.NDArray[np.bool_],
) -> tuple[tuple[int, int], ...]:
    """Observe which islands each owner's retained support reaches."""
    selected = retained_mask & (owner_labels > 0)
    if not bool(np.any(selected)):
        return ()
    pairs = np.unique(
        np.column_stack((owner_labels[selected], island_labels[selected])),
        axis=0,
    )
    return tuple((int(owner), int(island)) for owner, island in pairs)


def island_ids_by_owner(
    pairs: tuple[tuple[int, int], ...],
    *,
    identifier_by_island_label: Mapping[int, str],
) -> dict[int, tuple[str, ...]]:
    """Name the islands every owner reaches, from observed label pairs.

    The pairs come either from one whole plane or from the cores that
    observed them, so this join is the same in both compositions.
    """
    owners: dict[int, set[str]] = {}
    for owner, island_label in pairs:
        owners.setdefault(owner, set()).add(
            identifier_by_island_label[island_label]
        )
    return {
        owner: tuple(sorted(identifiers))
        for owner, identifiers in sorted(owners.items())
    }


def segment_local_rms(
    rms_jy_per_beam: npt.NDArray[np.float64],
    owner_window: npt.NDArray[np.integer[Any]],
    *,
    label_value: int,
) -> float | None:
    """Return the median local noise over one segment's exact owned support.

    ``owner_window`` is the segment's seeded ownership, not its expanded
    aperture: the noise a catalogue row quotes describes the pixels the
    segment itself owns. Both arrays cover the same window. A pixel whose
    estimate is not finite and positive carries no usable noise, and
    ``None`` means this segment owns no pixel that does.

    Examples:
        >>> import numpy as np
        >>> rms = np.array([[1.0, 3.0], [np.nan, 5.0]])
        >>> owners = np.array([[2, 2], [2, 0]])
        >>> segment_local_rms(rms, owners, label_value=2)
        2.0
        >>> segment_local_rms(rms, owners, label_value=1) is None
        True
    """
    return segment_local_rms_pixels(
        rms_jy_per_beam[owner_window == label_value]
    )


def segment_local_rms_pixels(
    rms_jy_per_beam: npt.NDArray[np.float64],
) -> float | None:
    """Return the median usable noise over one segment's owned pixels.

    The array holds the noise at the pixels the segment owns, so a segment
    too wide to read at once quotes the noise its window would give.
    """
    usable = np.isfinite(rms_jy_per_beam) & (rms_jy_per_beam > 0.0)
    if not bool(np.any(usable)):
        return None
    return float(np.median(rms_jy_per_beam[usable]))


def segment_moment(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    window: SegmentWindow | None = None,
) -> tuple[tuple[float, float], npt.NDArray[np.float64]] | None:
    """Return one segment's weighted centroid and covariance, or ``None``.

    This is the half of a moment shape that reads pixels. Its centroid is
    where the shape's local geometry belongs, so a caller measuring many
    segments takes every centroid first and transforms them together; see
    :func:`moment_shape_fields_at`.
    """
    return _segment_pixel_moment_covariance(
        residual_jy_per_beam,
        support,
        window=window,
    )


def moment_shape_fields_at(
    moment: tuple[tuple[float, float], npt.NDArray[np.float64]],
    *,
    transform: LocalTangentPlaneTransform,
    beam_icrs: RestoringBeam,
) -> dict[str, object]:
    """Return catalogue fields for one moment under its own local geometry.

    ``transform`` and ``beam_icrs`` belong to this moment's centroid. A
    moment the local geometry cannot describe is reported as unavailable,
    exactly as an unmeasurable one is.
    """
    _, covariance = moment
    try:
        fitted = moment_equivalent_gaussian_shape(covariance, transform)
        deconvolution = deconvolve_gaussian_shapes(
            fitted,
            beam_icrs,
            relative_tolerance=1e-10,
        )
    except (TypeError, ValueError, np.linalg.LinAlgError):
        return unavailable_moment_shape_fields()
    flags = {_MOMENT_SHAPE_PROVENANCE}
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


def _moment_shape_fields(
    residual_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    celestial_wcs: WCS,
    beam: RestoringBeam,
    window: SegmentWindow | None = None,
) -> dict[str, object]:
    """Return catalogue fields for one moment-equivalent owner shape.

    This measures and transforms one segment at a time, and is the readable
    reference for the batched path in :mod:`hebog.stages.catalogue_rows`.
    """
    moment = segment_moment(residual_jy_per_beam, support, window)
    if moment is None:
        return unavailable_moment_shape_fields()
    centroid_xy, _ = moment
    try:
        transform = local_tangent_plane_transform_from_wcs(
            celestial_wcs,
            centroid_xy,
        )
        beam_icrs = restoring_beam_in_icrs(beam, celestial_wcs, centroid_xy)
    except (TypeError, ValueError):
        return unavailable_moment_shape_fields()
    return moment_shape_fields_at(
        moment, transform=transform, beam_icrs=beam_icrs
    )


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
    segment_windows = label_windows(labels)
    output: list[CatalogueSource] = []
    for label_value in sorted(
        int(item) for item in np.unique(labels) if item > 0
    ):
        identifier = f"hebog-segment-{label_value}"
        source = by_identifier.get(identifier)
        if source is None:
            continue
        crop = _segment_crop(segment_windows, segment_windows, label_value)
        support = (labels[crop] == label_value) & valid[crop]
        shape_fields = _moment_shape_fields(
            residual[crop],
            support,
            celestial_wcs,
            beam,
            SegmentWindow(
                origin_yx=(crop[0].start, crop[1].start),
                plane_shape_yx=residual.shape,
            ),
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
        fitted_members = tuple(
            component
            for component_id in membership.component_ids
            for component in (by_id.get(component_id),)
            if component is not None
            and "original-pixel-gaussian-model" in component.quality_flags
        )
        integrated_flux_jy = source.integrated_flux_jy
        integrated_flux_error_jy = source.integrated_flux_error_jy
        if require_signed_aperture:
            if fitted_members:
                integrated_flux_jy, integrated_flux_error_jy = (
                    _summed_fitted_component_flux(fitted_members)
                )
            else:
                flags.add("aperture-flux-without-fitted-component")
        output.append(
            replace(
                source,
                identifier=membership.source_id,
                island_identifier=membership.source_id,
                component_count=len(membership.component_ids),
                integrated_flux_jy=integrated_flux_jy,
                integrated_flux_error_jy=integrated_flux_error_jy,
                quality_flags=tuple(sorted(flags)),
            )
        )
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
