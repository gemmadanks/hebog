"""Readable vectorized moment oracle for exact compact memberships."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite, log, pi, radians, sqrt
from typing import Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactMomentConfig
from hebog.data_models.measurement import (
    CompactMeasurementGeometry,
    CompactMomentMeasurement,
    GaussianMomentInitializer,
    MomentTarget,
    OwnedPixelPhotometry,
    ShapeUnavailableMomentMeasurement,
    UnavailableMomentMeasurement,
    ValidMomentMeasurement,
)

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class _MomentContext:
    """Aligned planes, geometry, and policy reused by target reductions."""

    residual: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    validity: npt.NDArray[np.bool_]
    origin_yx: tuple[int, int]
    geometry: CompactMeasurementGeometry
    config: CompactMomentConfig


class CompactMomentInput(Protocol):
    """Structural exact-label input kept inside one coarse worker task."""

    @property
    def island(self) -> DetectedIsland:
        """Return the reconciled parent island."""
        ...

    @property
    def regions(self) -> tuple[DeblendedRegion, ...]:
        """Return canonical deblended-region summaries."""
        ...

    @property
    def physical_residual(self) -> npt.NDArray[np.float64]:
        """Return the bounded physical residual plane."""
        ...

    @property
    def rms(self) -> npt.NDArray[np.float64]:
        """Return the aligned bounded RMS plane."""
        ...

    @property
    def valid_pixels(self) -> npt.NDArray[np.bool_]:
        """Return the aligned scientific-validity mask."""
        ...

    @property
    def region_labels(self) -> npt.NDArray[np.int32]:
        """Return exact zero-background deblended labels."""
        ...


def gaussian_beam_solid_angle_steradians(
    *,
    major_fwhm_degrees: float,
    minor_fwhm_degrees: float,
) -> float:
    """Return an elliptical Gaussian beam area from angular FWHM axes."""
    if (
        not isfinite(major_fwhm_degrees)
        or not isfinite(minor_fwhm_degrees)
        or major_fwhm_degrees <= 0
        or minor_fwhm_degrees <= 0
    ):
        raise ValueError("beam FWHM axes must be finite and positive")
    return (
        pi
        * radians(major_fwhm_degrees)
        * radians(minor_fwhm_degrees)
        / (4.0 * log(2.0))
    )


def fitted_gaussian_integrated_flux_jy(
    *,
    amplitude_jy_per_beam: float,
    major_sigma_pixels: float,
    minor_sigma_pixels: float,
    geometry: CompactMeasurementGeometry,
) -> float:
    """Convert one fitted Gaussian's infinite-plane area to integrated Jy."""
    values = (
        amplitude_jy_per_beam,
        major_sigma_pixels,
        minor_sigma_pixels,
    )
    if any(not isfinite(value) or value <= 0 for value in values):
        raise ValueError("Gaussian amplitude and sigma axes must be positive")
    gaussian_area_pixels = 2.0 * pi * major_sigma_pixels * minor_sigma_pixels
    return (
        amplitude_jy_per_beam
        * gaussian_area_pixels
        * geometry.pixel_solid_angle_steradians
        / geometry.restoring_beam_solid_angle_steradians
    )


def _validated_arrays(
    compact: CompactMomentInput,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
]:
    """Validate aligned exact labels without rejecting scientific failures."""
    residual = np.asarray(compact.physical_residual)
    rms = np.asarray(compact.rms)
    validity = np.asarray(compact.valid_pixels)
    labels = np.asarray(compact.region_labels)
    expected_shape = compact.island.bounds.shape_yx
    arrays = (residual, rms, validity, labels)
    if any(array.ndim != _IMAGE_DIMENSIONS for array in arrays):
        raise ValueError("compact moment arrays must be two-dimensional")
    if any(array.shape != expected_shape for array in arrays):
        raise ValueError("compact moment arrays must match island bounds")
    if residual.dtype != np.dtype(np.float64) or rms.dtype != np.dtype(
        np.float64
    ):
        raise TypeError("compact moment physical planes must be float64")
    if validity.dtype != np.dtype(np.bool_):
        raise TypeError("compact moment validity must be boolean")
    if labels.dtype != np.dtype(np.int32):
        raise TypeError("compact moment labels must be int32")
    return residual, rms, validity, labels


def _targets_and_masks(
    compact: CompactMomentInput,
    labels: npt.NDArray[np.int32],
) -> tuple[tuple[MomentTarget, npt.NDArray[np.bool_]], ...]:
    """Bind canonical identities to exact island and region membership."""
    island_membership = labels > 0
    if int(np.count_nonzero(island_membership)) != compact.island.pixel_count:
        raise ValueError("moment labels disagree with island pixel count")
    ordered_regions = tuple(
        sorted(compact.regions, key=lambda region: region.region_label)
    )
    if len({region.region_label for region in ordered_regions}) != len(
        ordered_regions
    ) or len({region.region_id for region in ordered_regions}) != len(
        ordered_regions
    ):
        raise ValueError("moment region labels and IDs must be unique")
    expected_labels = {region.region_label for region in ordered_regions}
    if set(np.unique(labels)) - {0} != expected_labels:
        raise ValueError("moment labels disagree with region summaries")
    targets: list[tuple[MomentTarget, npt.NDArray[np.bool_]]] = [
        (
            MomentTarget(
                object_kind="island",
                object_id=compact.island.island_id,
                island_id=compact.island.island_id,
                pixel_count=compact.island.pixel_count,
            ),
            island_membership,
        )
    ]
    for region in ordered_regions:
        membership = labels == region.region_label
        if (
            region.island_id != compact.island.island_id
            or int(np.count_nonzero(membership)) != region.pixel_count
        ):
            raise ValueError("moment region summary disagrees with labels")
        targets.append(
            (
                MomentTarget(
                    object_kind="deblended-region",
                    object_id=region.region_id,
                    island_id=region.island_id,
                    pixel_count=region.pixel_count,
                ),
                membership,
            )
        )
    return tuple(targets)


def _measure_target(
    target: MomentTarget,
    membership: npt.NDArray[np.bool_],
    context: _MomentContext,
) -> CompactMomentMeasurement:
    """Reduce one exact membership in canonical C pixel order."""
    flat_membership = np.flatnonzero(membership)
    flat_residual = np.ravel(context.residual, order="C")[flat_membership]
    flat_rms = np.ravel(context.rms, order="C")[flat_membership]
    flat_validity = np.ravel(context.validity, order="C")[flat_membership]
    if (
        not np.all(flat_validity)
        or not np.all(np.isfinite(flat_residual))
        or not np.all(np.isfinite(flat_rms))
    ):
        return UnavailableMomentMeasurement(
            target=target,
            reason="non-finite-owned-pixels",
        )
    total_brightness = float(np.sum(flat_residual, dtype=np.float64))
    if (
        np.any(flat_residual <= 0)
        or np.any(flat_rms <= 0)
        or not isfinite(total_brightness)
        or total_brightness <= 0
    ):
        return UnavailableMomentMeasurement(
            target=target,
            reason="non-positive-measurement",
        )

    local_y, local_x = np.unravel_index(
        flat_membership,
        context.residual.shape,
    )
    global_x = np.asarray(local_x, dtype=np.float64) + context.origin_yx[1]
    global_y = np.asarray(local_y, dtype=np.float64) + context.origin_yx[0]
    peak_index = int(np.argmax(flat_residual))
    photometry = OwnedPixelPhotometry(
        peak_brightness_jy_per_beam=float(flat_residual[peak_index]),
        peak_position_xy=(
            int(global_x[peak_index]),
            int(global_y[peak_index]),
        ),
        owned_pixel_integrated_flux_jy=(
            total_brightness
            * context.geometry.pixel_solid_angle_steradians
            / context.geometry.restoring_beam_solid_angle_steradians
        ),
        local_rms_jy_per_beam=float(np.mean(flat_rms, dtype=np.float64)),
        mean_brightness_jy_per_beam=(
            total_brightness / float(target.pixel_count)
        ),
    )
    if target.pixel_count < context.config.minimum_shape_pixels:
        return ShapeUnavailableMomentMeasurement(
            target=target,
            photometry=photometry,
            reason="underdetermined-region",
        )

    centroid_x = float(
        np.sum(global_x * flat_residual, dtype=np.float64) / total_brightness
    )
    centroid_y = float(
        np.sum(global_y * flat_residual, dtype=np.float64) / total_brightness
    )
    offset_x = global_x - centroid_x
    offset_y = global_y - centroid_y
    covariance_xx = float(
        np.sum(flat_residual * offset_x * offset_x, dtype=np.float64)
        / total_brightness
    )
    covariance_xy = float(
        np.sum(flat_residual * offset_x * offset_y, dtype=np.float64)
        / total_brightness
    )
    covariance_yy = float(
        np.sum(flat_residual * offset_y * offset_y, dtype=np.float64)
        / total_brightness
    )
    trace = covariance_xx + covariance_yy
    discriminant = hypot(
        covariance_xx - covariance_yy,
        2.0 * covariance_xy,
    )
    major_variance = 0.5 * (trace + discriminant)
    minor_variance = 0.5 * (trace - discriminant)
    if (
        not isfinite(major_variance)
        or not isfinite(minor_variance)
        or major_variance <= 0
        or minor_variance
        <= context.config.covariance_relative_tolerance * major_variance
    ):
        return ShapeUnavailableMomentMeasurement(
            target=target,
            photometry=photometry,
            reason="singular-covariance",
        )
    if discriminant <= context.config.covariance_relative_tolerance * trace:
        major_axis_angle = 0.0
    else:
        major_axis_angle = (
            degrees(
                0.5
                * atan2(
                    2.0 * covariance_xy,
                    covariance_xx - covariance_yy,
                )
            )
            % 180.0
        )
    return ValidMomentMeasurement(
        target=target,
        photometry=photometry,
        initializer=GaussianMomentInitializer(
            amplitude_jy_per_beam=photometry.peak_brightness_jy_per_beam,
            centroid_xy=(centroid_x, centroid_y),
            covariance_xx_pixels_squared=covariance_xx,
            covariance_xy_pixels_squared=covariance_xy,
            covariance_yy_pixels_squared=covariance_yy,
            major_sigma_pixels=sqrt(major_variance),
            minor_sigma_pixels=sqrt(minor_variance),
            major_axis_angle_degrees=major_axis_angle,
        ),
    )


def measure_compact_moments(
    compact: CompactMomentInput,
    geometry: CompactMeasurementGeometry,
    config: CompactMomentConfig,
) -> tuple[CompactMomentMeasurement, ...]:
    """Measure one island and its exact regions without pixel-wise loops."""
    residual, rms, validity, labels = _validated_arrays(compact)
    targets = _targets_and_masks(compact, labels)
    context = _MomentContext(
        residual=residual,
        rms=rms,
        validity=validity,
        origin_yx=(
            compact.island.bounds.y_start,
            compact.island.bounds.x_start,
        ),
        geometry=geometry,
        config=config,
    )
    return tuple(
        _measure_target(
            target,
            membership,
            context,
        )
        for target, membership in targets
    )
