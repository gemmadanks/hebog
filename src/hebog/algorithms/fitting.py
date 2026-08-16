# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded fit-all compact Gaussian reference using SciPy least squares."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import ceil, floor, isfinite, pi, sqrt
from typing import Literal, TypeAlias, cast

import numpy as np
import numpy.typing as npt
from scipy.linalg import solve_triangular
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares
from scipy.signal import fftconvolve
from scipy.special import ndtr

from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.measurement import (
    CompactMomentInput,
    fitted_gaussian_integrated_flux_jy,
)
from hebog.config import CompactGaussianFitConfig
from hebog.data_models.fitting import (
    AssociationAperturePhotometry,
    CompactGaussianFitResult,
    FailedCompactGaussianFit,
    FittedGaussianPixelParameters,
    GaussianComponentFit,
    GaussianFitDiagnostics,
    GaussianFitUncertainty,
    GaussianPositionEstimate,
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
from hebog.data_models.partitioning import ImageBounds

_NOISE_CORRELATION_TRUNCATION_SIGMA = 4.0
_TRUNCATED_MOMENT_RESIDUAL_TOLERANCE = 1e-6
_FREE_PARAMETER_NAMES = (
    "amplitude",
    "centroid-x",
    "centroid-y",
    "sigma-first",
    "sigma-second",
    "position-angle",
    "background",
)
_FREE_FIXED_BACKGROUND_PARAMETER_NAMES = _FREE_PARAMETER_NAMES[:-1]
_CONSTRAINED_PARAMETER_NAMES = (
    "amplitude",
    "centroid-x",
    "centroid-y",
    "background",
)
_CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES = _CONSTRAINED_PARAMETER_NAMES[
    :-1
]
_CENTROID_CONSTRAINED_PARAMETER_NAMES = (
    "amplitude",
    "forced-centroid-x",
    "forced-centroid-y",
    "sigma-first",
    "sigma-second",
    "position-angle",
    "background",
)
_CENTROID_CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES = (
    _CENTROID_CONSTRAINED_PARAMETER_NAMES[:-1]
)
_ModelIdentity: TypeAlias = Literal[
    "free-elliptical",
    "beam-constrained",
    "centroid-constrained-elliptical",
]
_FallbackReason: TypeAlias = Literal[
    "free-model-bound-contact",
    "free-model-ill-conditioned",
    "free-model-not-significantly-extended",
    "free-model-non-convergence",
    "free-model-invalid-result",
]
_PointEstimatorIdentity: TypeAlias = Literal[
    "diagonal-weighted",
    "correlated-gls",
]
_PointEstimatorFallback: TypeAlias = Literal[
    "correlation-model-unavailable",
    "correlation-factorization-failed",
    "retained-region-exceeds-gls-limit",
]
_ApertureModel: TypeAlias = Literal["restoring-beam", "selected-fit"]


@dataclass(frozen=True, slots=True)
class _FitEvidence:
    """Arrays needed to diagnose one bounded optimizer result."""

    parameters: npt.NDArray[np.float64]
    lower_bounds: npt.NDArray[np.float64]
    upper_bounds: npt.NDArray[np.float64]
    jacobian: npt.NDArray[np.float64]
    x: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]
    weighted_residual: npt.NDArray[np.float64]
    parameter_names: tuple[str, ...]
    model_identity: _ModelIdentity
    full_parameters: npt.NDArray[np.float64]
    fallback_reason: _FallbackReason | None
    point_estimator: _PointEstimatorIdentity
    point_estimator_fallback_reason: _PointEstimatorFallback | None


@dataclass(frozen=True, slots=True)
class _FitSamples:
    """Finite retained pixels and immutable scientific fit context."""

    x: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]
    values: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    geometry: CompactMeasurementGeometry
    config: CompactGaussianFitConfig
    residual_transform: Callable[
        [npt.NDArray[np.float64]], npt.NDArray[np.float64]
    ]
    point_estimator: _PointEstimatorIdentity
    point_estimator_fallback_reason: _PointEstimatorFallback | None


@dataclass(frozen=True, slots=True)
class _ModelSpec:
    """One bounded nested Gaussian parameterization."""

    identity: _ModelIdentity
    parameter_names: tuple[str, ...]
    initial: npt.NDArray[np.float64]
    lower: npt.NDArray[np.float64]
    upper: npt.NDArray[np.float64]
    expand: Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]]
    full_parameter_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _FitCandidate:
    """One optimizer candidate with covariance and explicit evidence."""

    success: bool
    optimizer_parameters: npt.NDArray[np.float64]
    full_parameters: npt.NDArray[np.float64]
    jacobian: npt.NDArray[np.float64]
    covariance: npt.NDArray[np.float64] | None
    diagnostics: GaussianFitDiagnostics


@dataclass(frozen=True, slots=True)
class _FitPublicationContext:
    """Inputs shared while publishing one selected fit candidate."""

    compact: CompactMomentInput
    region: DeblendedRegion
    moment: ValidMomentMeasurement
    geometry: CompactMeasurementGeometry
    config: CompactGaussianFitConfig


@dataclass(frozen=True, slots=True)
class _ApertureGeometry:
    """One candidate aperture model evaluated on the retained image grid."""

    model: _ApertureModel
    squared_radius: npt.NDArray[np.float64]
    weights: npt.NDArray[np.float64]
    total_weight: float


def _local_rms_at_centroid(
    compact: CompactMomentInput,
    centroid_xy: tuple[float, float],
) -> float:
    """Bilinearly sample local RMS, extending edge-pixel values by 0.5 px."""
    x, y = centroid_xy
    array_bounds = getattr(compact, "array_bounds", compact.island.bounds)
    local_coordinates = np.asarray(
        [
            [y - array_bounds.y_start],
            [x - array_bounds.x_start],
        ],
        dtype=np.float64,
    )
    valid_rms = np.isfinite(compact.rms) & (compact.rms > 0.0)
    weighted_rms = map_coordinates(
        np.where(valid_rms, compact.rms, 0.0),
        local_coordinates,
        order=1,
        mode="nearest",
        prefilter=False,
    )[0]
    retained_weight = map_coordinates(
        valid_rms.astype(np.float64),
        local_coordinates,
        order=1,
        mode="nearest",
        prefilter=False,
    )[0]
    if not isfinite(retained_weight) or retained_weight <= 0.0:
        return float("nan")
    return float(weighted_rms / retained_weight)


def _gaussian_values(
    parameters: npt.NDArray[np.float64],
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Evaluate one rotated elliptical Gaussian without a background term."""
    (
        amplitude,
        center_x,
        center_y,
        sigma_first,
        sigma_second,
        theta,
        background_offset,
    ) = parameters
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
    return np.asarray(
        background_offset + amplitude * np.exp(exponent),
        dtype=np.float64,
    )


def _gaussian_parameter_jacobian(
    parameters: npt.NDArray[np.float64],
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Return the exact model derivative for all seven parameters."""
    (
        amplitude,
        center_x,
        center_y,
        sigma_first,
        sigma_second,
        theta,
        _,
    ) = parameters
    x_offset = x - center_x
    y_offset = y - center_y
    cosine = np.cos(theta)
    sine = np.sin(theta)
    first_offset = cosine * x_offset + sine * y_offset
    second_offset = -sine * x_offset + cosine * y_offset
    inverse_first_variance = 1.0 / sigma_first**2
    inverse_second_variance = 1.0 / sigma_second**2
    profile = np.exp(
        -0.5
        * (
            np.square(first_offset) * inverse_first_variance
            + np.square(second_offset) * inverse_second_variance
        )
    )
    scaled_profile = amplitude * profile
    return np.column_stack(
        (
            profile,
            scaled_profile
            * (
                first_offset * cosine * inverse_first_variance
                - second_offset * sine * inverse_second_variance
            ),
            scaled_profile
            * (
                first_offset * sine * inverse_first_variance
                + second_offset * cosine * inverse_second_variance
            ),
            scaled_profile * np.square(first_offset) / sigma_first**3,
            scaled_profile * np.square(second_offset) / sigma_second**3,
            scaled_profile
            * first_offset
            * second_offset
            * (inverse_second_variance - inverse_first_variance),
            np.ones_like(profile),
        )
    )


def _diagnostics(
    *,
    converged: bool,
    function_evaluations: int,
    evidence: _FitEvidence,
) -> GaussianFitDiagnostics:
    """Build deterministic optimizer diagnostics from final residuals."""
    parameters = evidence.parameters
    lower_bounds = evidence.lower_bounds
    upper_bounds = evidence.upper_bounds
    jacobian = evidence.jacobian
    x = evidence.x
    y = evidence.y
    weighted_residual = evidence.weighted_residual
    chi_squared = float(np.sum(np.square(weighted_residual), dtype=np.float64))
    degrees_of_freedom = weighted_residual.size - parameters.size
    bound_widths = upper_bounds - lower_bounds
    relative_bound_distances = (
        np.minimum(
            parameters - lower_bounds,
            upper_bounds - parameters,
        )
        / bound_widths
    )
    at_bound = np.isclose(
        parameters,
        lower_bounds,
        rtol=0.0,
        atol=1e-10,
    ) | np.isclose(
        parameters,
        upper_bounds,
        rtol=0.0,
        atol=1e-10,
    )
    column_norms = np.linalg.norm(jacobian, axis=0)
    information_condition = (
        float(
            np.linalg.cond(
                (jacobian / column_norms).T @ (jacobian / column_norms)
            )
        )
        if np.all(column_norms > 0)
        else float("inf")
    )
    amplitude, _, _, sigma_first, sigma_second, _, background = (
        evidence.full_parameters
    )
    sampled_model_sum = float(
        np.sum(
            _gaussian_values(evidence.full_parameters, x, y) - background,
            dtype=np.float64,
        )
    )
    total_model_sum = float(amplitude * 2.0 * pi * sigma_first * sigma_second)
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
        parameters_at_bound=bool(np.any(at_bound)),
        model_identity=evidence.model_identity,
        bound_parameters=tuple(
            name
            for name, selected in zip(
                evidence.parameter_names, at_bound, strict=True
            )
            if selected
        ),
        relative_bound_distances=tuple(
            (name, float(max(0.0, distance)))
            for name, distance in zip(
                evidence.parameter_names,
                relative_bound_distances,
                strict=True,
            )
        ),
        minimum_relative_bound_distance=float(
            np.min(relative_bound_distances)
        ),
        information_condition_number=(
            information_condition if isfinite(information_condition) else None
        ),
        visible_model_fraction=float(
            np.clip(sampled_model_sum / total_model_sum, 0.0, 1.0)
        ),
        retained_pixel_count=weighted_residual.size,
        retained_bounds_yx=(
            int(np.min(y)),
            int(np.max(y)) + 1,
            int(np.min(x)),
            int(np.max(x)) + 1,
        ),
        fallback_reason=evidence.fallback_reason,
        point_estimator=evidence.point_estimator,
        point_estimator_fallback_reason=(
            evidence.point_estimator_fallback_reason
        ),
    )


def _noise_correlation_kernel(
    covariance_values: tuple[float, float, float],
) -> npt.NDArray[np.float64]:
    """Sample the unit-peak Gaussian pixel-noise correlation function."""
    covariance_xx, covariance_xy, covariance_yy = covariance_values
    covariance = np.asarray(
        [
            [covariance_xx, covariance_xy],
            [covariance_xy, covariance_yy],
        ],
        dtype=np.float64,
    )
    inverse_covariance = np.asarray(
        np.linalg.inv(covariance),
        dtype=np.float64,
    )
    halo = int(
        np.ceil(
            _NOISE_CORRELATION_TRUNCATION_SIGMA
            * np.sqrt(float(np.max(np.linalg.eigvalsh(covariance))))
        )
    )
    offsets = np.arange(-halo, halo + 1, dtype=np.float64)
    y_grid, x_grid = np.meshgrid(offsets, offsets, indexing="ij")
    coordinates = np.stack((x_grid, y_grid), axis=-1)
    exponent = np.einsum(
        "...i,ij,...j->...",
        coordinates,
        inverse_covariance,
        coordinates,
        optimize=True,
    )
    return np.asarray(np.exp(-0.5 * exponent), dtype=np.float64)


def _correlated_parameter_covariance(
    jacobian: npt.NDArray[np.float64],
    coordinates_xy: npt.NDArray[np.float64],
    correlation_covariance: tuple[float, float, float],
) -> npt.NDArray[np.float64]:
    """Return the OLS sandwich covariance under Gaussian pixel correlation."""
    information_inverse = np.linalg.inv(jacobian.T @ jacobian)
    x_coordinates = np.asarray(coordinates_xy[:, 0], dtype=np.int64)
    y_coordinates = np.asarray(coordinates_xy[:, 1], dtype=np.int64)
    x_local = x_coordinates - int(np.min(x_coordinates))
    y_local = y_coordinates - int(np.min(y_coordinates))
    grid_shape = (
        int(np.max(y_local)) + 1,
        int(np.max(x_local)) + 1,
    )
    kernel = _noise_correlation_kernel(correlation_covariance)
    grid = np.zeros((*grid_shape, jacobian.shape[1]), dtype=np.float64)
    grid[y_local, x_local, :] = jacobian
    correlated_grid = fftconvolve(
        grid,
        kernel[:, :, np.newaxis],
        mode="same",
        axes=(0, 1),
    )
    correlated_jacobian = correlated_grid[y_local, x_local, :]
    meat = jacobian.T @ correlated_jacobian
    return np.asarray(
        information_inverse @ meat @ information_inverse,
        dtype=np.float64,
    )


def _parameter_covariance(
    jacobian: npt.NDArray[np.float64],
    coordinates_xy: npt.NDArray[np.float64],
    geometry: CompactMeasurementGeometry,
    *,
    correlated_point_estimator: bool,
) -> npt.NDArray[np.float64] | None:
    """Return bounded-model covariance, or absence for singular information."""
    information = jacobian.T @ jacobian
    if np.linalg.matrix_rank(information) != jacobian.shape[1]:
        return None
    correlation = geometry.noise_correlation_covariance_pixels_squared
    return np.asarray(
        np.linalg.inv(information)
        if correlation is None or correlated_point_estimator
        else _correlated_parameter_covariance(
            jacobian,
            coordinates_xy,
            correlation,
        ),
        dtype=np.float64,
    )


def _formal_uncertainty(  # noqa: PLR0913
    optimizer_parameters: npt.NDArray[np.float64],
    full_parameters: npt.NDArray[np.float64],
    covariance: npt.NDArray[np.float64] | None,
    geometry: CompactMeasurementGeometry,
    *,
    model_identity: _ModelIdentity,
    axes_swapped: bool,
    integrated_flux_bias_correction_sigma: float,
) -> GaussianFitUncertainty | None:
    """Return position/flux errors for one free or beam-constrained model."""
    if covariance is None:
        return None
    amplitude, _, _, sigma_first, sigma_second, _, _ = full_parameters
    integrated = fitted_gaussian_integrated_flux_jy(
        amplitude_jy_per_beam=float(amplitude),
        major_sigma_pixels=float(sigma_first),
        minor_sigma_pixels=float(sigma_second),
        geometry=geometry,
    )
    gradient = np.zeros(optimizer_parameters.size, dtype=np.float64)
    gradient[0] = integrated / amplitude
    if model_identity != "beam-constrained":
        gradient[3] = integrated / sigma_first
        gradient[4] = integrated / sigma_second
    integrated_variance = float(gradient @ covariance @ gradient)
    amplitude_integrated_covariance = float(covariance[0] @ gradient)
    variances = (
        float(covariance[0, 0]),
        float(covariance[1, 1]),
        float(covariance[2, 2]),
        integrated_variance,
    )
    if any(not isfinite(value) or value <= 0 for value in variances):
        return None
    shape_parameter_covariance = None
    if model_identity != "beam-constrained":
        shape_indices = np.asarray((3, 4, 5), dtype=np.int64)
        shape_covariance = np.asarray(
            covariance[np.ix_(shape_indices, shape_indices)],
            dtype=np.float64,
        )
        if axes_swapped:
            ordering = np.asarray((1, 0, 2), dtype=np.int64)
            shape_covariance = shape_covariance[np.ix_(ordering, ordering)]
        if (
            np.all(np.isfinite(shape_covariance))
            and np.all(np.diag(shape_covariance) > 0)
            and float(np.min(np.linalg.eigvalsh(shape_covariance)))
            >= -np.finfo(np.float64).eps
        ):
            shape_parameter_covariance = (
                float(shape_covariance[0, 0]),
                float(shape_covariance[0, 1]),
                float(shape_covariance[0, 2]),
                float(shape_covariance[1, 1]),
                float(shape_covariance[1, 2]),
                float(shape_covariance[2, 2]),
            )
    return GaussianFitUncertainty(
        amplitude_error_jy_per_beam=float(np.sqrt(variances[0])),
        centroid_covariance_xx_pixels_squared=variances[1],
        centroid_covariance_xy_pixels_squared=float(covariance[1, 2]),
        centroid_covariance_yy_pixels_squared=variances[2],
        integrated_flux_error_jy=float(np.sqrt(variances[3])),
        integrated_flux_bias_correction_sigma=(
            integrated_flux_bias_correction_sigma
        ),
        amplitude_integrated_flux_covariance_jy_squared_per_beam=(
            amplitude_integrated_covariance
        ),
        shape_parameter_covariance=shape_parameter_covariance,
    )


def _beam_shape(
    covariance_values: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Return ordered sigma axes and angle from pixel beam covariance."""
    covariance_xx, covariance_xy, covariance_yy = covariance_values
    covariance = np.asarray(
        [
            [covariance_xx, covariance_xy],
            [covariance_xy, covariance_yy],
        ],
        dtype=np.float64,
    )
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    return (
        float(np.sqrt(eigenvalues[major_index])),
        float(np.sqrt(eigenvalues[minor_index])),
        float(np.arctan2(major_vector[1], major_vector[0])),
    )


def _point_estimator_transform(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
) -> tuple[
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
    _PointEstimatorIdentity,
    _PointEstimatorFallback | None,
]:
    """Build one bounded standard-residual transform for point estimation."""

    def identity(
        residual: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        return np.asarray(residual, dtype=np.float64)

    if config.point_estimator == "diagonal-weighted":
        return identity, "diagonal-weighted", None
    correlation = geometry.noise_correlation_covariance_pixels_squared
    if correlation is None:
        return identity, "diagonal-weighted", "correlation-model-unavailable"
    if x.size > config.maximum_gls_pixels:
        return (
            identity,
            "diagonal-weighted",
            "retained-region-exceeds-gls-limit",
        )
    covariance_xx, covariance_xy, covariance_yy = correlation
    inverse = np.linalg.inv(
        np.asarray(
            [
                [covariance_xx, covariance_xy],
                [covariance_xy, covariance_yy],
            ],
            dtype=np.float64,
        )
    )
    coordinates = np.column_stack((x, y))
    offsets = coordinates[:, np.newaxis, :] - coordinates[np.newaxis, :, :]
    exponent = np.einsum(
        "...i,ij,...j->...",
        offsets,
        inverse,
        offsets,
        optimize=True,
    )
    correlation_matrix = np.asarray(
        np.exp(-0.5 * exponent),
        dtype=np.float64,
    )
    try:
        factor = np.linalg.cholesky(correlation_matrix)
    except np.linalg.LinAlgError:
        try:
            factor = np.linalg.cholesky(
                correlation_matrix
                + 1e-10 * np.eye(correlation_matrix.shape[0])
            )
        except np.linalg.LinAlgError:
            return (
                identity,
                "diagonal-weighted",
                "correlation-factorization-failed",
            )

    def whiten(
        residual: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        return np.asarray(
            solve_triangular(
                factor,
                residual,
                lower=True,
                check_finite=False,
            ),
            dtype=np.float64,
        )

    return whiten, "correlated-gls", None


def _fit_samples_from_mask(
    compact: CompactMomentInput,
    fit_pixels: npt.NDArray[np.bool_],
    array_bounds: ImageBounds,
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
) -> _FitSamples:
    """Build one immutable sample set from an explicit support mask."""
    y_local, x_local = np.nonzero(fit_pixels)
    x = np.asarray(x_local + array_bounds.x_start, dtype=np.float64)
    y = np.asarray(y_local + array_bounds.y_start, dtype=np.float64)
    values = np.asarray(
        compact.physical_residual[fit_pixels], dtype=np.float64
    )
    rms = np.asarray(compact.rms[fit_pixels], dtype=np.float64)
    residual_transform, point_estimator, estimator_fallback = (
        _point_estimator_transform(x, y, geometry, config)
    )
    return _FitSamples(
        x=x,
        y=y,
        values=values,
        rms=rms,
        geometry=geometry,
        config=config,
        residual_transform=residual_transform,
        point_estimator=point_estimator,
        point_estimator_fallback_reason=estimator_fallback,
    )


def _fit_candidate(
    samples: _FitSamples,
    spec: _ModelSpec,
    *,
    fallback_reason: _FallbackReason | None,
) -> _FitCandidate:
    """Optimize one nested model and retain all selection evidence."""

    def weighted_residual(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        full_parameters = spec.expand(parameters)
        standard_residual = (
            _gaussian_values(full_parameters, samples.x, samples.y)
            - samples.values
        ) / samples.rms
        return samples.residual_transform(standard_residual)

    def weighted_jacobian(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        full_parameters = spec.expand(parameters)
        model_jacobian = _gaussian_parameter_jacobian(
            full_parameters,
            samples.x,
            samples.y,
        )[:, spec.full_parameter_indices]
        standard_jacobian = model_jacobian / samples.rms[:, np.newaxis]
        return samples.residual_transform(standard_jacobian)

    result = least_squares(
        weighted_residual,
        spec.initial,
        jac=weighted_jacobian,  # pyright: ignore[reportArgumentType]
        bounds=(spec.lower, spec.upper),
        method="trf",
        x_scale="jac",
        ftol=samples.config.convergence_tolerance,
        xtol=samples.config.convergence_tolerance,
        gtol=samples.config.convergence_tolerance,
        max_nfev=samples.config.maximum_function_evaluations,
    )
    optimizer_parameters = np.asarray(result.x, dtype=np.float64)
    full_parameters = spec.expand(optimizer_parameters)
    jacobian = np.asarray(result.jac, dtype=np.float64)
    diagnostics = _diagnostics(
        converged=bool(result.success),
        function_evaluations=int(result.nfev),
        evidence=_FitEvidence(
            parameters=optimizer_parameters,
            lower_bounds=spec.lower,
            upper_bounds=spec.upper,
            jacobian=jacobian,
            x=samples.x,
            y=samples.y,
            weighted_residual=weighted_residual(optimizer_parameters),
            parameter_names=spec.parameter_names,
            model_identity=spec.identity,
            full_parameters=full_parameters,
            fallback_reason=fallback_reason,
            point_estimator=samples.point_estimator,
            point_estimator_fallback_reason=(
                samples.point_estimator_fallback_reason
            ),
        ),
    )
    covariance = _parameter_covariance(
        jacobian,
        np.column_stack((samples.x, samples.y)),
        samples.geometry,
        correlated_point_estimator=(
            samples.point_estimator == "correlated-gls"
        ),
    )
    return _FitCandidate(
        success=bool(result.success),
        optimizer_parameters=optimizer_parameters,
        full_parameters=full_parameters,
        jacobian=jacobian,
        covariance=covariance,
        diagnostics=diagnostics,
    )


def _numerically_valid(
    candidate: _FitCandidate,
    config: CompactGaussianFitConfig,
) -> bool:
    """Check finite positive Gaussian parameters and reviewed axis ratio."""
    amplitude, _, _, sigma_first, sigma_second, _, _ = (
        candidate.full_parameters
    )
    return bool(
        np.all(np.isfinite(candidate.full_parameters))
        and amplitude > 0
        and sigma_second > 0
        and sigma_first / sigma_second <= config.maximum_axis_ratio
    )


def _identifiable(
    candidate: _FitCandidate,
    config: CompactGaussianFitConfig,
) -> bool:
    """Reject non-periodic bound contact and ill-conditioned information."""
    physical_bound_parameters = set(candidate.diagnostics.bound_parameters) - {
        "forced-centroid-x",
        "forced-centroid-y",
        "position-angle",
    }
    condition = candidate.diagnostics.information_condition_number
    return (
        not physical_bound_parameters
        and condition is not None
        and condition <= config.maximum_information_condition_number
    )


def _has_physical_bound_contact(candidate: _FitCandidate) -> bool:
    """Return whether a selected scientific parameter touches its bound."""
    ignored = {"forced-centroid-x", "forced-centroid-y", "position-angle"}
    return bool(set(candidate.diagnostics.bound_parameters) - ignored)


def _stable_centroid_retry_template(
    candidate: _FitCandidate,
    config: CompactGaussianFitConfig,
) -> bool:
    """Accept a converged template whose only ridge is its free centroid."""
    if not candidate.success or not _numerically_valid(candidate, config):
        return False
    physical_bounds = set(candidate.diagnostics.bound_parameters) - {
        "position-angle"
    }
    condition = candidate.diagnostics.information_condition_number
    return (
        physical_bounds <= {"centroid-x", "centroid-y"}
        and condition is not None
        and condition <= config.maximum_information_condition_number
    )


def _with_rejected_model(
    selected: _FitCandidate,
    rejected: _FitCandidate,
) -> _FitCandidate:
    """Attach the alternative model's identity and exact bound evidence."""
    return replace(
        selected,
        diagnostics=replace(
            selected.diagnostics,
            rejected_model_identity=rejected.diagnostics.model_identity,
            rejected_model_bound_parameters=(
                rejected.diagnostics.bound_parameters
            ),
        ),
    )


def _significantly_extended(
    candidate: _FitCandidate,
    beam_covariance: tuple[float, float, float],
    *,
    significance_sigma: float,
) -> bool:
    """Apply the reviewed data-only log-area extension significance rule."""
    covariance = candidate.covariance
    if covariance is None:
        return False
    _, _, _, sigma_first, sigma_second, _, _ = candidate.full_parameters
    beam_xx, beam_xy, beam_yy = beam_covariance
    beam_sigma_product = np.sqrt(beam_xx * beam_yy - beam_xy * beam_xy)
    log_area_ratio = float(
        np.log(sigma_first * sigma_second / beam_sigma_product)
    )
    gradient = np.zeros(candidate.optimizer_parameters.size, dtype=np.float64)
    gradient[3] = 1.0 / sigma_first
    gradient[4] = 1.0 / sigma_second
    log_area_variance = float(gradient @ covariance @ gradient)
    return bool(
        isfinite(log_area_variance)
        and log_area_variance > 0
        and log_area_ratio > significance_sigma * np.sqrt(log_area_variance)
    )


def _free_fallback_reason(
    candidate: _FitCandidate,
    beam_covariance: tuple[float, float, float],
    config: CompactGaussianFitConfig,
) -> _FallbackReason | None:
    """Return why the free model cannot own the published measurement."""
    if not candidate.success:
        return "free-model-non-convergence"
    if not _numerically_valid(candidate, config):
        return "free-model-invalid-result"
    physical_bound_parameters = set(candidate.diagnostics.bound_parameters) - {
        "forced-centroid-x",
        "forced-centroid-y",
        "position-angle",
    }
    if physical_bound_parameters:
        return "free-model-bound-contact"
    if not _identifiable(candidate, config):
        return "free-model-ill-conditioned"
    if not _significantly_extended(
        candidate,
        beam_covariance,
        significance_sigma=config.extension_significance_sigma,
    ):
        return "free-model-not-significantly-extended"
    return None


def _free_preferred_by_bic(
    free: _FitCandidate,
    constrained: _FitCandidate,
    samples: _FitSamples,
) -> bool:
    """Compare nested models using beam-count-scaled Bayesian information."""
    if (
        not constrained.success
        or not _numerically_valid(constrained, samples.config)
        or not _identifiable(constrained, samples.config)
    ):
        return False
    retained_count = free.diagnostics.retained_pixel_count
    if samples.point_estimator == "correlated-gls":
        independent_samples = float(retained_count)
    else:
        beam_area_pixels = (
            samples.geometry.restoring_beam_solid_angle_steradians
            / samples.geometry.pixel_solid_angle_steradians
        )
        independent_samples = max(retained_count / beam_area_pixels, 2.0)
    chi_squared_scale = independent_samples / retained_count

    def bic(candidate: _FitCandidate) -> float:
        return (
            candidate.diagnostics.chi_squared * chi_squared_scale
            + candidate.optimizer_parameters.size * np.log(independent_samples)
        )

    return bic(free) < bic(constrained)


def _free_model_spec(
    *,
    identity: Literal["free-elliptical"],
    initial: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
    fixed_background: bool,
) -> _ModelSpec:
    """Build one free elliptical model with explicit background policy."""
    free_indices = np.arange(6 if fixed_background else 7, dtype=np.int64)

    def expand(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        if fixed_background:
            return np.asarray([*parameters, 0.0], dtype=np.float64)
        return np.asarray(parameters, dtype=np.float64)

    return _ModelSpec(
        identity=identity,
        parameter_names=(
            _FREE_FIXED_BACKGROUND_PARAMETER_NAMES
            if fixed_background
            else _FREE_PARAMETER_NAMES
        ),
        initial=initial[free_indices],
        lower=lower[free_indices],
        upper=upper[free_indices],
        expand=expand,
        full_parameter_indices=tuple(int(item) for item in free_indices),
    )


def _upper_truncated_normal_location(
    observed_mean: float,
    observed_variance: float,
    upper_bound: float,
    maximum_sigma: float,
) -> float | None:
    """Invert the first two moments of a one-sided truncated normal."""
    if observed_variance <= 0 or observed_mean >= upper_bound:
        return None
    observed_sigma = sqrt(observed_variance)

    def residual(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        location, sigma = parameters
        standardized_bound = (upper_bound - location) / sigma
        density = np.exp(-0.5 * standardized_bound**2) / sqrt(2.0 * pi)
        probability = float(ndtr(standardized_bound))
        if probability <= np.finfo(np.float64).tiny:
            return np.asarray((np.inf, np.inf), dtype=np.float64)
        ratio = density / probability
        expected_mean = location - sigma * ratio
        expected_variance = sigma**2 * (
            1.0 - standardized_bound * ratio - ratio**2
        )
        return np.asarray(
            (
                expected_mean - observed_mean,
                expected_variance - observed_variance,
            ),
            dtype=np.float64,
        )

    initial_sigma = min(maximum_sigma, max(observed_sigma * 1.5, 0.2))
    result = least_squares(
        residual,
        np.asarray(
            (
                min(upper_bound, observed_mean + observed_sigma),
                initial_sigma,
            ),
            dtype=np.float64,
        ),
        bounds=(
            np.asarray((observed_mean, 0.2), dtype=np.float64),
            np.asarray((upper_bound, maximum_sigma), dtype=np.float64),
        ),
        method="trf",
        max_nfev=100,
    )
    if (
        not result.success
        or np.max(np.abs(residual(result.x)))
        > _TRUNCATED_MOMENT_RESIDUAL_TOLERANCE
    ):
        return None
    return float(result.x[0])


def _truncated_moment_centroid(
    moment: ValidMomentMeasurement,
    candidate: _FitCandidate,
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
    config: CompactGaussianFitConfig,
) -> tuple[float, float] | None:
    """Correct moment coordinates whose context likelihood hits an edge."""
    initializer = moment.initializer
    corrected = list(initializer.centroid_xy)
    definitions = (
        (
            "centroid-x",
            initializer.centroid_xy[0],
            initializer.covariance_xx_pixels_squared,
            1,
        ),
        (
            "centroid-y",
            initializer.centroid_xy[1],
            initializer.covariance_yy_pixels_squared,
            2,
        ),
    )
    bound_parameters = set(candidate.diagnostics.bound_parameters)
    corrected_any = False
    for name, observed, variance, parameter_index in definitions:
        if name not in bound_parameters:
            corrected[parameter_index - 1] = float(
                candidate.full_parameters[parameter_index]
            )
            continue
        at_lower = np.isclose(
            candidate.full_parameters[parameter_index],
            lower[parameter_index],
            rtol=0.0,
            atol=1e-10,
        )
        if at_lower:
            location = _upper_truncated_normal_location(
                -observed,
                variance,
                -float(lower[parameter_index]),
                config.maximum_sigma_pixels,
            )
            location = None if location is None else -location
        else:
            location = _upper_truncated_normal_location(
                observed,
                variance,
                float(upper[parameter_index]),
                config.maximum_sigma_pixels,
            )
        if location is None:
            return None
        corrected[parameter_index - 1] = location
        corrected_any = True
    return (
        (float(corrected[0]), float(corrected[1])) if corrected_any else None
    )


def _context_position_estimate(  # noqa: PLR0913
    compact: CompactMomentInput,
    region: DeblendedRegion,
    moment: ValidMomentMeasurement,
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
    *,
    initial: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
    fixed_background: bool,
    array_bounds: ImageBounds,
) -> GaussianPositionEstimate | None:
    """Fit a full-context centroid independently of owned morphology."""
    if config.position_estimator != "bounded-context-free":
        return None
    labels = np.asarray(compact.region_labels)
    context_pixels = np.asarray(compact.valid_pixels) & (
        (labels == 0) | (labels == region.region_label)
    )
    samples = _fit_samples_from_mask(
        compact,
        context_pixels,
        array_bounds,
        geometry,
        config,
    )
    candidate = _fit_candidate(
        samples,
        _free_model_spec(
            identity="free-elliptical",
            initial=initial,
            lower=lower,
            upper=upper,
            fixed_background=fixed_background,
        ),
        fallback_reason=None,
    )
    covariance = candidate.covariance
    if not candidate.success or covariance is None:
        return None
    centroid = _truncated_moment_centroid(
        moment,
        candidate,
        lower,
        upper,
        config,
    )
    estimator: Literal[
        "bounded-context-free",
        "bounded-context-truncation-refit",
    ] = "bounded-context-free"
    if centroid is not None:
        retry_initial = np.asarray(initial, dtype=np.float64).copy()
        retry_lower = np.asarray(lower, dtype=np.float64).copy()
        retry_upper = np.asarray(upper, dtype=np.float64).copy()
        retry_initial[1:3] = centroid
        margin = max(config.center_margin_pixels, 0.5)
        retry_lower[1:3] = np.minimum(
            retry_lower[1:3] - margin,
            np.asarray(centroid, dtype=np.float64) - margin,
        )
        retry_upper[1:3] = np.maximum(
            retry_upper[1:3] + margin,
            np.asarray(centroid, dtype=np.float64) + margin,
        )
        retry = _fit_candidate(
            samples,
            _free_model_spec(
                identity="free-elliptical",
                initial=retry_initial,
                lower=retry_lower,
                upper=retry_upper,
                fixed_background=fixed_background,
            ),
            fallback_reason=None,
        )
        if (
            not retry.success
            or retry.covariance is None
            or not _numerically_valid(retry, config)
            or not _identifiable(retry, config)
        ):
            return None
        candidate = retry
        covariance = retry.covariance
        centroid = (
            float(retry.full_parameters[1]),
            float(retry.full_parameters[2]),
        )
        estimator = "bounded-context-truncation-refit"
    else:
        if not _numerically_valid(candidate, config) or not _identifiable(
            candidate,
            config,
        ):
            return None
        centroid = (
            float(candidate.full_parameters[1]),
            float(candidate.full_parameters[2]),
        )
    try:
        return GaussianPositionEstimate(
            centroid_xy=centroid,
            covariance_xx_pixels_squared=float(covariance[1, 1]),
            covariance_xy_pixels_squared=float(covariance[1, 2]),
            covariance_yy_pixels_squared=float(covariance[2, 2]),
            estimator=estimator,
        )
    except ValueError:
        return None


def _centroid_constrained_retry(  # noqa: PLR0913
    samples: _FitSamples,
    *,
    free: _FitCandidate,
    constrained: _FitCandidate,
    fallback_reason: _FallbackReason,
    retry_centroid_xy: tuple[float, float] | None,
    initial: npt.NDArray[np.float64],
    lower: npt.NDArray[np.float64],
    upper: npt.NDArray[np.float64],
    fixed_background: bool,
) -> _FitCandidate | None:
    """Retry an unidentifiable free shape at a stable template centroid."""
    if fallback_reason not in {
        "free-model-bound-contact",
        "free-model-ill-conditioned",
    }:
        return None
    config = samples.config
    if not _stable_centroid_retry_template(constrained, config):
        return None
    constrained_parameters = constrained.full_parameters
    forced_center_tolerance = 1e-7
    retry_center = np.asarray(
        retry_centroid_xy if retry_centroid_xy is not None else initial[1:3],
        dtype=np.float64,
    )
    center_x, center_y = retry_center
    forced_initial = np.asarray(
        [
            constrained_parameters[0],
            center_x,
            center_y,
            initial[3],
            initial[4],
            initial[5],
            constrained_parameters[6],
        ],
        dtype=np.float64,
    )
    forced_lower = np.asarray(lower, dtype=np.float64).copy()
    forced_upper = np.asarray(upper, dtype=np.float64).copy()
    forced_lower[1:3] = retry_center - forced_center_tolerance
    forced_upper[1:3] = retry_center + forced_center_tolerance
    free_indices = np.arange(6 if fixed_background else 7, dtype=np.int64)

    def expand(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        if fixed_background:
            return np.asarray([*parameters, 0.0], dtype=np.float64)
        return np.asarray(parameters, dtype=np.float64)

    forced = _fit_candidate(
        samples,
        _ModelSpec(
            identity="centroid-constrained-elliptical",
            parameter_names=(
                _CENTROID_CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES
                if fixed_background
                else _CENTROID_CONSTRAINED_PARAMETER_NAMES
            ),
            initial=forced_initial[free_indices],
            lower=forced_lower[free_indices],
            upper=forced_upper[free_indices],
            expand=expand,
            full_parameter_indices=tuple(int(item) for item in free_indices),
        ),
        fallback_reason=fallback_reason,
    )
    beam_covariance = samples.geometry.restoring_beam_covariance_pixels_squared
    assert beam_covariance is not None
    forced_reason = _free_fallback_reason(
        forced,
        beam_covariance,
        config,
    )
    if forced_reason is None or (
        forced_reason == "free-model-not-significantly-extended"
        and (
            not _identifiable(constrained, config)
            or _free_preferred_by_bic(forced, constrained, samples)
        )
    ):
        return _with_rejected_model(forced, free)
    return None


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


def _valid_fit_result(
    context: _FitPublicationContext,
    candidate: _FitCandidate,
    position_estimate: GaussianPositionEstimate | None = None,
) -> ValidCompactGaussianFit:
    """Publish one scientifically selected nested-model candidate."""
    compact = context.compact
    geometry = context.geometry
    (
        amplitude,
        center_x,
        center_y,
        sigma_first,
        sigma_second,
        theta,
        _,
    ) = candidate.full_parameters
    axes_swapped = sigma_second > sigma_first
    if axes_swapped:
        sigma_first, sigma_second = sigma_second, sigma_first
        theta += 0.5 * pi
    local_rms = _local_rms_at_centroid(
        compact,
        (float(center_x), float(center_y)),
    )
    local_rms_region_mean_fallback = not isfinite(local_rms) or local_rms <= 0
    if local_rms_region_mean_fallback:
        local_rms = context.moment.photometry.local_rms_jy_per_beam
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
        local_rms_jy_per_beam=local_rms,
    )
    uncertainty = _formal_uncertainty(
        candidate.optimizer_parameters,
        candidate.full_parameters,
        candidate.covariance,
        geometry,
        model_identity=candidate.diagnostics.model_identity,
        axes_swapped=axes_swapped,
        integrated_flux_bias_correction_sigma=(
            context.config.integrated_flux_bias_correction_sigma
        ),
    )
    flags = tuple(
        flag
        for flag, selected in (
            ("fit-at-bound", _has_physical_bound_contact(candidate)),
            (
                "beam-constrained-fit",
                candidate.diagnostics.model_identity == "beam-constrained",
            ),
            (
                "centroid-constrained-fit",
                candidate.diagnostics.model_identity
                == "centroid-constrained-elliptical",
            ),
            (
                candidate.diagnostics.fallback_reason or "",
                candidate.diagnostics.fallback_reason is not None,
            ),
            ("uncertainty-unavailable", uncertainty is None),
            (
                "formal-independent-pixel-errors",
                uncertainty is not None
                and geometry.noise_correlation_covariance_pixels_squared
                is None,
            ),
            (
                "correlated-noise-sandwich-errors",
                uncertainty is not None
                and geometry.noise_correlation_covariance_pixels_squared
                is not None
                and candidate.diagnostics.point_estimator
                == "diagonal-weighted",
            ),
            (
                "correlated-noise-gls-errors",
                uncertainty is not None
                and candidate.diagnostics.point_estimator == "correlated-gls",
            ),
            (
                "correlated-gls-fallback",
                candidate.diagnostics.point_estimator_fallback_reason
                is not None,
            ),
            ("bounded-context-position", position_estimate is not None),
            (
                "local-rms-region-mean-fallback",
                local_rms_region_mean_fallback,
            ),
        )
        if selected
    )
    return ValidCompactGaussianFit(
        moment=context.moment,
        parameters=fitted_parameters,
        uncertainty=uncertainty,
        diagnostics=candidate.diagnostics,
        quality_flags=flags,
        position_estimate=position_estimate,
        association_aperture=_association_aperture_photometry(
            compact,
            context.region,
            candidate,
            geometry,
            context.config,
        ),
    )


def _association_aperture_photometry(
    compact: CompactMomentInput,
    region: DeblendedRegion,
    candidate: _FitCandidate,
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
) -> AssociationAperturePhotometry | None:
    """Select a bounded low-variance aperture that contains the fit model."""
    (
        _,
        center_x,
        center_y,
        sigma_first,
        sigma_second,
        theta,
        _,
    ) = candidate.full_parameters
    major = np.asarray([np.cos(theta), np.sin(theta)], dtype=np.float64)
    minor = np.asarray([-np.sin(theta), np.cos(theta)], dtype=np.float64)
    fitted_covariance = sigma_first**2 * np.outer(
        major, major
    ) + sigma_second**2 * np.outer(minor, minor)
    radius_sigma = config.association_aperture_radius_sigma
    array_bounds = getattr(compact, "array_bounds", compact.island.bounds)
    local_y, local_x = np.indices(
        compact.physical_residual.shape,
        dtype=np.float64,
    )
    offsets = np.stack(
        (
            local_x + array_bounds.x_start - center_x,
            local_y + array_bounds.y_start - center_y,
        ),
        axis=-1,
    )
    fitted = _aperture_geometry(
        offsets,
        model="selected-fit",
        center_xy=(float(center_x), float(center_y)),
        covariance=fitted_covariance,
    )
    labels = np.asarray(compact.region_labels)
    admitted = np.asarray(compact.valid_pixels) & (
        (labels == 0) | (labels == region.region_label)
    )
    selected_geometry = fitted
    beam_covariance_values = geometry.restoring_beam_covariance_pixels_squared
    if beam_covariance_values is not None:
        covariance_xx, covariance_xy, covariance_yy = beam_covariance_values
        beam_covariance = np.asarray(
            [
                [covariance_xx, covariance_xy],
                [covariance_xy, covariance_yy],
            ],
            dtype=np.float64,
        )
        beam = _aperture_geometry(
            offsets,
            model="restoring-beam",
            center_xy=(float(center_x), float(center_y)),
            covariance=beam_covariance,
        )
        beam_support = admitted & (
            beam.squared_radius <= radius_sigma * radius_sigma
        )
        fitted_fraction_in_beam = float(
            np.sum(fitted.weights[beam_support], dtype=np.float64)
            / fitted.total_weight
        )
        if (
            fitted_fraction_in_beam
            >= config.association_aperture_minimum_fixed_beam_model_fraction
        ):
            selected_geometry = beam
    selected = admitted & (
        selected_geometry.squared_radius <= radius_sigma * radius_sigma
    )
    retained_pixel_count = int(np.count_nonzero(selected))
    if retained_pixel_count == 0:
        return None
    visible_model_weight = float(
        np.sum(selected_geometry.weights[selected], dtype=np.float64)
    )
    visible_model_fraction = float(
        visible_model_weight / selected_geometry.total_weight
    )
    selected_brightness = float(
        np.sum(
            np.asarray(compact.physical_residual)[selected], dtype=np.float64
        )
    )
    integrated_flux = (
        selected_brightness / visible_model_weight
        if selected_geometry.model == "restoring-beam"
        else selected_brightness
        * geometry.pixel_solid_angle_steradians
        / geometry.restoring_beam_solid_angle_steradians
        / visible_model_fraction
    )
    if (
        not isfinite(visible_model_fraction)
        or not 0 < visible_model_fraction <= 1
        or not isfinite(integrated_flux)
        or integrated_flux <= 0
    ):
        return None
    return AssociationAperturePhotometry(
        radius_sigma=radius_sigma,
        integrated_flux_jy=integrated_flux,
        visible_model_fraction=visible_model_fraction,
        retained_pixel_count=retained_pixel_count,
        aperture_model=selected_geometry.model,
    )


def _aperture_geometry(
    offsets: npt.NDArray[np.float64],
    *,
    model: _ApertureModel,
    center_xy: tuple[float, float],
    covariance: npt.NDArray[np.float64],
) -> _ApertureGeometry:
    """Evaluate one Gaussian aperture model on the image and full lattice."""
    inverse_covariance = np.asarray(
        np.linalg.inv(covariance),
        dtype=np.float64,
    )
    squared_radius = np.einsum(
        "...i,ij,...j->...",
        offsets,
        inverse_covariance,
        offsets,
        optimize=True,
    )
    return _ApertureGeometry(
        model=model,
        squared_radius=squared_radius,
        weights=np.exp(-0.5 * squared_radius),
        total_weight=_discrete_aperture_model_weight(
            center_xy=center_xy,
            covariance=covariance,
            inverse_covariance=inverse_covariance,
            radius_sigma=8.0,
        ),
    )


def _discrete_aperture_model_weight(
    *,
    center_xy: tuple[float, float],
    covariance: npt.NDArray[np.float64],
    inverse_covariance: npt.NDArray[np.float64],
    radius_sigma: float,
) -> float:
    """Integrate a Gaussian model over a bounded complete pixel lattice."""
    center_x, center_y = center_xy
    extent_x = radius_sigma * sqrt(float(covariance[0, 0]))
    extent_y = radius_sigma * sqrt(float(covariance[1, 1]))
    aperture_x = np.arange(
        floor(center_x - extent_x),
        ceil(center_x + extent_x) + 1,
        dtype=np.float64,
    )
    aperture_y = np.arange(
        floor(center_y - extent_y),
        ceil(center_y + extent_y) + 1,
        dtype=np.float64,
    )
    grid_x, grid_y = np.meshgrid(aperture_x, aperture_y)
    offsets = np.stack((grid_x - center_x, grid_y - center_y), axis=-1)
    squared_radius = np.einsum(
        "...i,ij,...j->...",
        offsets,
        inverse_covariance,
        offsets,
        optimize=True,
    )
    selected = squared_radius <= radius_sigma * radius_sigma
    return float(
        np.sum(np.exp(-0.5 * squared_radius[selected]), dtype=np.float64)
    )


def _free_compatibility_result(
    context: _FitPublicationContext,
    candidate: _FitCandidate,
    position_estimate: GaussianPositionEstimate | None = None,
) -> CompactGaussianFitResult:
    """Publish legacy free fitting when explicit beam shape is unavailable."""
    moment = context.moment
    if not candidate.success:
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-non-convergence",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-non-convergence",),
        )
    if not _numerically_valid(candidate, context.config):
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-invalid-result",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-invalid-result",),
        )
    return _valid_fit_result(context, candidate, position_estimate)


def _selected_fit_result(
    context: _FitPublicationContext,
    candidate: _FitCandidate,
    position_estimate: GaussianPositionEstimate | None = None,
    component_candidate: _FitCandidate | None = None,
) -> CompactGaussianFitResult:
    """Publish or explicitly fail one scientifically selected candidate."""
    moment = context.moment
    fallback_reason = candidate.diagnostics.fallback_reason
    flags = (fallback_reason,) if fallback_reason is not None else ()
    if not candidate.success:
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-non-convergence",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-non-convergence", *flags),
        )
    if not _numerically_valid(candidate, context.config) or not _identifiable(
        candidate, context.config
    ):
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-invalid-result",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-invalid-result", *flags),
        )
    selected = _valid_fit_result(context, candidate, position_estimate)
    if component_candidate is None:
        return selected
    if (
        not component_candidate.success
        or not _numerically_valid(component_candidate, context.config)
        or not _identifiable(component_candidate, context.config)
    ):
        return selected
    component = _valid_fit_result(context, component_candidate)
    return replace(
        selected,
        gaussian_component_fit=GaussianComponentFit(
            parameters=component.parameters,
            uncertainty=component.uncertainty,
            diagnostics=component.diagnostics,
            quality_flags=component.quality_flags,
        ),
    )


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
    publication = _FitPublicationContext(
        compact=compact,
        region=region,
        moment=valid_moment,
        geometry=geometry,
        config=config,
    )
    labels = np.asarray(compact.region_labels)
    membership = labels == region.region_label
    support = (
        membership
        if config.pixel_support == "owned-region"
        else membership | (labels == 0)
    )
    fit_pixels = np.asarray(compact.valid_pixels) & support
    array_bounds = getattr(compact, "array_bounds", compact.island.bounds)
    samples = _fit_samples_from_mask(
        compact,
        fit_pixels,
        array_bounds,
        geometry,
        config,
    )
    values = samples.values
    rms = samples.rms
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
            0.0,
        ],
        dtype=np.float64,
    )
    lower = np.asarray(
        [
            np.finfo(np.float64).tiny,
            max(
                region.bounds.x_start - 0.5 - config.center_margin_pixels,
                array_bounds.x_start - 0.5,
            ),
            max(
                region.bounds.y_start - 0.5 - config.center_margin_pixels,
                array_bounds.y_start - 0.5,
            ),
            config.minimum_sigma_pixels,
            config.minimum_sigma_pixels,
            -pi,
            -config.maximum_background_offset_sigma * float(np.median(rms)),
        ],
        dtype=np.float64,
    )
    upper = np.asarray(
        [
            max(values) * config.maximum_amplitude_factor,
            min(
                region.bounds.x_stop - 0.5 + config.center_margin_pixels,
                array_bounds.x_stop - 0.5,
            ),
            min(
                region.bounds.y_stop - 0.5 + config.center_margin_pixels,
                array_bounds.y_stop - 0.5,
            ),
            config.maximum_sigma_pixels,
            config.maximum_sigma_pixels,
            pi,
            config.maximum_background_offset_sigma * float(np.median(rms)),
        ],
        dtype=np.float64,
    )

    fixed_background = config.background_model == "fixed-zero"

    free = _fit_candidate(
        samples,
        _free_model_spec(
            identity="free-elliptical",
            initial=initial,
            lower=lower,
            upper=upper,
            fixed_background=fixed_background,
        ),
        fallback_reason=None,
    )
    position_estimate = _context_position_estimate(
        compact,
        region,
        valid_moment,
        geometry,
        config,
        initial=initial,
        lower=lower,
        upper=upper,
        fixed_background=fixed_background,
        array_bounds=array_bounds,
    )
    beam_covariance = geometry.restoring_beam_covariance_pixels_squared
    if config.model_selection == "free-only" or beam_covariance is None:
        return _free_compatibility_result(
            publication,
            free,
            position_estimate,
        )

    fallback_reason = _free_fallback_reason(free, beam_covariance, config)
    if fallback_reason is None:
        return _selected_fit_result(
            publication,
            free,
            position_estimate,
        )

    beam_major, beam_minor, beam_theta = _beam_shape(beam_covariance)

    def expand_constrained(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        amplitude, center_x, center_y = parameters[:3]
        background = 0.0 if fixed_background else parameters[3]
        return np.asarray(
            [
                amplitude,
                center_x,
                center_y,
                beam_major,
                beam_minor,
                beam_theta,
                background,
            ],
            dtype=np.float64,
        )

    constrained_indices = np.asarray(
        [0, 1, 2] if fixed_background else [0, 1, 2, 6],
        dtype=np.int64,
    )
    constrained = _fit_candidate(
        samples,
        _ModelSpec(
            identity="beam-constrained",
            parameter_names=(
                _CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES
                if fixed_background
                else _CONSTRAINED_PARAMETER_NAMES
            ),
            initial=initial[constrained_indices],
            lower=lower[constrained_indices],
            upper=upper[constrained_indices],
            expand=expand_constrained,
            full_parameter_indices=tuple(
                int(item) for item in constrained_indices
            ),
        ),
        fallback_reason=fallback_reason,
    )
    forced = _centroid_constrained_retry(
        samples,
        free=free,
        constrained=constrained,
        fallback_reason=fallback_reason,
        retry_centroid_xy=_truncated_moment_centroid(
            valid_moment,
            free,
            lower,
            upper,
            config,
        ),
        initial=initial,
        lower=lower,
        upper=upper,
        fixed_background=fixed_background,
    )
    constrained_failed = (
        not constrained.success
        or not _numerically_valid(constrained, config)
        or not _identifiable(constrained, config)
    )
    retain_free = fallback_reason == (
        "free-model-not-significantly-extended"
    ) and (
        constrained_failed
        or _free_preferred_by_bic(free, constrained, samples)
    )
    selected = (
        forced
        if forced is not None
        else _with_rejected_model(free, constrained)
        if retain_free
        else _with_rejected_model(constrained, free)
    )
    component_candidate = (
        free
        if fallback_reason == "free-model-not-significantly-extended"
        and selected.diagnostics.model_identity != "free-elliptical"
        and _significantly_extended(
            free,
            beam_covariance,
            significance_sigma=(config.component_extension_significance_sigma),
        )
        else None
    )
    return _selected_fit_result(
        publication,
        selected,
        position_estimate,
        component_candidate,
    )
