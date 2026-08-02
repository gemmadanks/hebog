# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded fit-all compact Gaussian reference using SciPy least squares."""

from __future__ import annotations

from math import isfinite, pi
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares

from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.measurement import (
    CompactMomentInput,
    fitted_gaussian_integrated_flux_jy,
)
from hebog.config import CompactGaussianFitConfig
from hebog.data_models.fitting import (
    CompactGaussianFitResult,
    FailedCompactGaussianFit,
    FittedGaussianPixelParameters,
    GaussianFitDiagnostics,
    GaussianFitUncertainty,
    UnavailableCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.measurement import (
    CompactMeasurementGeometry,
    CompactMomentMeasurement,
    ShapeUnavailableMomentMeasurement,
    UnavailableMomentMeasurement,
    ValidMomentMeasurement,
)

_PARAMETER_COUNT = 6


def _local_rms_at_centroid(
    compact: CompactMomentInput,
    centroid_xy: tuple[float, float],
) -> float:
    """Bilinearly sample local RMS, extending edge-pixel values by 0.5 px."""
    x, y = centroid_xy
    local_coordinates = np.asarray(
        [
            [y - compact.island.bounds.y_start],
            [x - compact.island.bounds.x_start],
        ],
        dtype=np.float64,
    )
    return float(
        map_coordinates(
            compact.rms,
            local_coordinates,
            order=1,
            mode="nearest",
            prefilter=False,
        )[0]
    )


def _gaussian_values(
    parameters: npt.NDArray[np.float64],
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Evaluate one rotated elliptical Gaussian without a background term."""
    amplitude, center_x, center_y, sigma_first, sigma_second, theta = (
        parameters
    )
    x_offset = x - center_x
    y_offset = y - center_y
    cosine = np.cos(theta)
    sine = np.sin(theta)
    first_offset = cosine * x_offset + sine * y_offset
    second_offset = -sine * x_offset + cosine * y_offset
    exponent = -0.5 * (
        np.square(first_offset / sigma_first)
        + np.square(second_offset / sigma_second)
    )
    return np.asarray(amplitude * np.exp(exponent), dtype=np.float64)


def _diagnostics(
    *,
    converged: bool,
    function_evaluations: int,
    weighted_residual: npt.NDArray[np.float64],
    parameters_at_bound: bool,
) -> GaussianFitDiagnostics:
    """Build deterministic optimizer diagnostics from final residuals."""
    chi_squared = float(np.sum(np.square(weighted_residual), dtype=np.float64))
    degrees_of_freedom = weighted_residual.size - _PARAMETER_COUNT
    return GaussianFitDiagnostics(
        converged=converged,
        function_evaluations=function_evaluations,
        chi_squared=chi_squared,
        degrees_of_freedom=degrees_of_freedom,
        reduced_chi_squared=(
            chi_squared / degrees_of_freedom
            if degrees_of_freedom > 0
            else None
        ),
        parameters_at_bound=parameters_at_bound,
    )


def _formal_uncertainty(
    jacobian: npt.NDArray[np.float64],
    parameters: npt.NDArray[np.float64],
    geometry: CompactMeasurementGeometry,
) -> GaussianFitUncertainty | None:
    """Return covariance, or absence for singular information."""
    information = jacobian.T @ jacobian
    if np.linalg.matrix_rank(information) != _PARAMETER_COUNT:
        return None
    covariance = np.linalg.inv(information)
    amplitude, _, _, sigma_first, sigma_second, _ = parameters
    integrated = fitted_gaussian_integrated_flux_jy(
        amplitude_jy_per_beam=float(amplitude),
        major_sigma_pixels=float(sigma_first),
        minor_sigma_pixels=float(sigma_second),
        geometry=geometry,
    )
    gradient = np.asarray(
        [
            integrated / amplitude,
            0.0,
            0.0,
            integrated / sigma_first,
            integrated / sigma_second,
            0.0,
        ],
        dtype=np.float64,
    )
    integrated_variance = float(gradient @ covariance @ gradient)
    variances = (
        float(covariance[0, 0]),
        float(covariance[1, 1]),
        float(covariance[2, 2]),
        integrated_variance,
    )
    if any(not isfinite(value) or value <= 0 for value in variances):
        return None
    return GaussianFitUncertainty(
        amplitude_error_jy_per_beam=float(np.sqrt(variances[0])),
        centroid_covariance_xx_pixels_squared=variances[1],
        centroid_covariance_xy_pixels_squared=float(covariance[1, 2]),
        centroid_covariance_yy_pixels_squared=variances[2],
        integrated_flux_error_jy=float(np.sqrt(variances[3])),
    )


def _unavailable_fit(
    moment: CompactMomentMeasurement,
    config: CompactGaussianFitConfig,
) -> UnavailableCompactGaussianFit | None:
    """Translate invalid moments and too-small fits to explicit absence."""
    if isinstance(moment, UnavailableMomentMeasurement):
        return UnavailableCompactGaussianFit(
            moment=moment,
            reason=moment.reason,
            quality_flags=("fit-unavailable",),
        )
    if isinstance(moment, ShapeUnavailableMomentMeasurement):
        return UnavailableCompactGaussianFit(
            moment=moment,
            reason=moment.reason,
            quality_flags=("fit-unavailable",),
        )
    if moment.target.pixel_count < config.minimum_fit_pixels:
        return UnavailableCompactGaussianFit(
            moment=moment,
            reason="underdetermined-region",
            quality_flags=("fit-unavailable",),
        )
    return None


def fit_compact_gaussian(
    compact: CompactMomentInput,
    region: DeblendedRegion,
    moment: CompactMomentMeasurement,
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
) -> CompactGaussianFitResult:
    """Fit every eligible exact region with bounded SciPy TRF least squares."""
    unavailable = _unavailable_fit(moment, config)
    if unavailable is not None:
        return unavailable
    valid_moment = cast(ValidMomentMeasurement, moment)
    if (
        valid_moment.target.object_kind != "deblended-region"
        or valid_moment.target.object_id != region.region_id
    ):
        raise ValueError("fit moment does not identify the requested region")
    membership = np.asarray(compact.region_labels) == region.region_label
    y_local, x_local = np.nonzero(membership)
    x = np.asarray(
        x_local + compact.island.bounds.x_start,
        dtype=np.float64,
    )
    y = np.asarray(
        y_local + compact.island.bounds.y_start,
        dtype=np.float64,
    )
    values = np.asarray(
        compact.physical_residual[membership], dtype=np.float64
    )
    rms = np.asarray(compact.rms[membership], dtype=np.float64)
    initializer = valid_moment.initializer
    initial = np.asarray(
        [
            initializer.amplitude_jy_per_beam,
            initializer.centroid_xy[0],
            initializer.centroid_xy[1],
            np.clip(
                initializer.major_sigma_pixels,
                config.minimum_sigma_pixels,
                config.maximum_sigma_pixels,
            ),
            np.clip(
                initializer.minor_sigma_pixels,
                config.minimum_sigma_pixels,
                config.maximum_sigma_pixels,
            ),
            np.deg2rad(initializer.major_axis_angle_degrees),
        ],
        dtype=np.float64,
    )
    lower = np.asarray(
        [
            np.finfo(np.float64).tiny,
            region.bounds.x_start - 0.5 - config.center_margin_pixels,
            region.bounds.y_start - 0.5 - config.center_margin_pixels,
            config.minimum_sigma_pixels,
            config.minimum_sigma_pixels,
            -pi,
        ],
        dtype=np.float64,
    )
    upper = np.asarray(
        [
            max(values) * config.maximum_amplitude_factor,
            region.bounds.x_stop - 0.5 + config.center_margin_pixels,
            region.bounds.y_stop - 0.5 + config.center_margin_pixels,
            config.maximum_sigma_pixels,
            config.maximum_sigma_pixels,
            pi,
        ],
        dtype=np.float64,
    )

    def weighted_residual(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        return (_gaussian_values(parameters, x, y) - values) / rms

    result = least_squares(
        weighted_residual,
        initial,
        bounds=(lower, upper),
        method="trf",
        x_scale="jac",
        ftol=config.convergence_tolerance,
        xtol=config.convergence_tolerance,
        gtol=config.convergence_tolerance,
        max_nfev=config.maximum_function_evaluations,
    )
    parameters = np.asarray(result.x, dtype=np.float64)
    at_bound = bool(
        np.any(np.isclose(parameters, lower, rtol=0.0, atol=1e-10))
        or np.any(np.isclose(parameters, upper, rtol=0.0, atol=1e-10))
    )
    diagnostics = _diagnostics(
        converged=bool(result.success),
        function_evaluations=int(result.nfev),
        weighted_residual=weighted_residual(parameters),
        parameters_at_bound=at_bound,
    )
    if not result.success:
        return FailedCompactGaussianFit(
            moment=valid_moment,
            reason="fit-non-convergence",
            diagnostics=diagnostics,
            quality_flags=("fit-non-convergence",),
        )
    amplitude, center_x, center_y, sigma_first, sigma_second, theta = (
        parameters
    )
    if sigma_second > sigma_first:
        sigma_first, sigma_second = sigma_second, sigma_first
        theta += 0.5 * pi
    axis_ratio = sigma_first / sigma_second
    if (
        not np.all(np.isfinite(parameters))
        or amplitude <= 0
        or sigma_second <= 0
        or axis_ratio > config.maximum_axis_ratio
    ):
        return FailedCompactGaussianFit(
            moment=valid_moment,
            reason="fit-invalid-result",
            diagnostics=diagnostics,
            quality_flags=("fit-invalid-result",),
        )
    fitted_parameters = FittedGaussianPixelParameters(
        amplitude_jy_per_beam=float(amplitude),
        centroid_xy=(float(center_x), float(center_y)),
        major_sigma_pixels=float(sigma_first),
        minor_sigma_pixels=float(sigma_second),
        major_axis_angle_degrees=float(np.rad2deg(theta) % 180.0),
        integrated_flux_jy=fitted_gaussian_integrated_flux_jy(
            amplitude_jy_per_beam=float(amplitude),
            major_sigma_pixels=float(sigma_first),
            minor_sigma_pixels=float(sigma_second),
            geometry=geometry,
        ),
        local_rms_jy_per_beam=_local_rms_at_centroid(
            compact,
            (float(center_x), float(center_y)),
        ),
    )
    uncertainty = _formal_uncertainty(
        np.asarray(result.jac, dtype=np.float64),
        parameters,
        geometry,
    )
    flags = tuple(
        flag
        for flag, selected in (
            ("fit-at-bound", at_bound),
            ("uncertainty-unavailable", uncertainty is None),
        )
        if selected
    )
    return ValidCompactGaussianFit(
        moment=valid_moment,
        parameters=fitted_parameters,
        uncertainty=uncertainty,
        diagnostics=diagnostics,
        quality_flags=flags,
    )
