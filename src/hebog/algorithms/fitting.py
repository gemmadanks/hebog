# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded fit-all compact Gaussian reference using SciPy least squares."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import isfinite, pi
from typing import Literal, TypeAlias, cast

import numpy as np
import numpy.typing as npt
from scipy.linalg import solve_triangular
from scipy.ndimage import correlate, map_coordinates
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

_NOISE_CORRELATION_TRUNCATION_SIGMA = 4.0
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


@dataclass(frozen=True, slots=True)
class _FitCandidate:
    """One optimizer candidate with covariance and explicit evidence."""

    success: bool
    optimizer_parameters: npt.NDArray[np.float64]
    full_parameters: npt.NDArray[np.float64]
    jacobian: npt.NDArray[np.float64]
    covariance: npt.NDArray[np.float64] | None
    diagnostics: GaussianFitDiagnostics


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
        np.linalg.inv(covariance),
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
    correlated_jacobian = np.empty_like(jacobian)
    for parameter_index in range(jacobian.shape[1]):
        grid = np.zeros(grid_shape, dtype=np.float64)
        grid[y_local, x_local] = jacobian[:, parameter_index]
        correlated_grid = correlate(grid, kernel, mode="constant", cval=0.0)
        correlated_jacobian[:, parameter_index] = correlated_grid[
            y_local,
            x_local,
        ]
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


def _formal_uncertainty(
    optimizer_parameters: npt.NDArray[np.float64],
    full_parameters: npt.NDArray[np.float64],
    covariance: npt.NDArray[np.float64] | None,
    geometry: CompactMeasurementGeometry,
    *,
    model_identity: _ModelIdentity,
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
    return GaussianFitUncertainty(
        amplitude_error_jy_per_beam=float(np.sqrt(variances[0])),
        centroid_covariance_xx_pixels_squared=variances[1],
        centroid_covariance_xy_pixels_squared=float(covariance[1, 2]),
        centroid_covariance_yy_pixels_squared=variances[2],
        integrated_flux_error_jy=float(np.sqrt(variances[3])),
        amplitude_integrated_flux_covariance_jy_squared_per_beam=(
            amplitude_integrated_covariance
        ),
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

    result = least_squares(
        weighted_residual,
        spec.initial,
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
    config: CompactGaussianFitConfig,
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
        and log_area_ratio
        > config.extension_significance_sigma * np.sqrt(log_area_variance)
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
    if not _significantly_extended(candidate, beam_covariance, config):
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


def _centroid_constrained_retry(  # noqa: PLR0913
    samples: _FitSamples,
    *,
    free: _FitCandidate,
    constrained: _FitCandidate,
    fallback_reason: _FallbackReason,
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
    if (
        not constrained.success
        or not _numerically_valid(constrained, config)
        or not _identifiable(constrained, config)
    ):
        return None
    constrained_parameters = constrained.full_parameters
    forced_center_tolerance = 1e-7
    forced_initial = np.asarray(
        [
            constrained_parameters[0],
            constrained_parameters[1],
            constrained_parameters[2],
            initial[3],
            initial[4],
            initial[5],
            constrained_parameters[6],
        ],
        dtype=np.float64,
    )
    forced_lower = np.asarray(lower, dtype=np.float64).copy()
    forced_upper = np.asarray(upper, dtype=np.float64).copy()
    forced_lower[1:3] = constrained_parameters[1:3] - forced_center_tolerance
    forced_upper[1:3] = constrained_parameters[1:3] + forced_center_tolerance
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
        and _free_preferred_by_bic(forced, constrained, samples)
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
    compact: CompactMomentInput,
    moment: ValidMomentMeasurement,
    candidate: _FitCandidate,
    geometry: CompactMeasurementGeometry,
) -> ValidCompactGaussianFit:
    """Publish one scientifically selected nested-model candidate."""
    (
        amplitude,
        center_x,
        center_y,
        sigma_first,
        sigma_second,
        theta,
        _,
    ) = candidate.full_parameters
    if sigma_second > sigma_first:
        sigma_first, sigma_second = sigma_second, sigma_first
        theta += 0.5 * pi
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
        candidate.optimizer_parameters,
        candidate.full_parameters,
        candidate.covariance,
        geometry,
        model_identity=candidate.diagnostics.model_identity,
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
        )
        if selected
    )
    return ValidCompactGaussianFit(
        moment=moment,
        parameters=fitted_parameters,
        uncertainty=uncertainty,
        diagnostics=candidate.diagnostics,
        quality_flags=flags,
    )


def _free_compatibility_result(
    compact: CompactMomentInput,
    moment: ValidMomentMeasurement,
    candidate: _FitCandidate,
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
) -> CompactGaussianFitResult:
    """Publish legacy free fitting when explicit beam shape is unavailable."""
    if not candidate.success:
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-non-convergence",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-non-convergence",),
        )
    if not _numerically_valid(candidate, config):
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-invalid-result",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-invalid-result",),
        )
    return _valid_fit_result(compact, moment, candidate, geometry)


def _selected_fit_result(
    compact: CompactMomentInput,
    moment: ValidMomentMeasurement,
    candidate: _FitCandidate,
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
) -> CompactGaussianFitResult:
    """Publish or explicitly fail one scientifically selected candidate."""
    fallback_reason = candidate.diagnostics.fallback_reason
    flags = (fallback_reason,) if fallback_reason is not None else ()
    if not candidate.success:
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-non-convergence",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-non-convergence", *flags),
        )
    if not _numerically_valid(candidate, config) or not _identifiable(
        candidate, config
    ):
        return FailedCompactGaussianFit(
            moment=moment,
            reason="fit-invalid-result",
            diagnostics=candidate.diagnostics,
            quality_flags=("fit-invalid-result", *flags),
        )
    return _valid_fit_result(compact, moment, candidate, geometry)


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
    labels = np.asarray(compact.region_labels)
    membership = labels == region.region_label
    support = (
        membership
        if config.pixel_support == "owned-region"
        else membership | (labels == 0)
    )
    fit_pixels = np.asarray(compact.valid_pixels) & support
    y_local, x_local = np.nonzero(fit_pixels)
    array_bounds = getattr(compact, "array_bounds", compact.island.bounds)
    x = np.asarray(
        x_local + array_bounds.x_start,
        dtype=np.float64,
    )
    y = np.asarray(
        y_local + array_bounds.y_start,
        dtype=np.float64,
    )
    values = np.asarray(
        compact.physical_residual[fit_pixels], dtype=np.float64
    )
    rms = np.asarray(compact.rms[fit_pixels], dtype=np.float64)
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

    residual_transform, point_estimator, estimator_fallback = (
        _point_estimator_transform(x, y, geometry, config)
    )
    samples = _FitSamples(
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
    fixed_background = config.background_model == "fixed-zero"
    free_indices = np.arange(6 if fixed_background else 7, dtype=np.int64)

    def expand_free(
        parameters: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        if fixed_background:
            return np.asarray([*parameters, 0.0], dtype=np.float64)
        return np.asarray(parameters, dtype=np.float64)

    free = _fit_candidate(
        samples,
        _ModelSpec(
            identity="free-elliptical",
            parameter_names=(
                _FREE_FIXED_BACKGROUND_PARAMETER_NAMES
                if fixed_background
                else _FREE_PARAMETER_NAMES
            ),
            initial=initial[free_indices],
            lower=lower[free_indices],
            upper=upper[free_indices],
            expand=expand_free,
        ),
        fallback_reason=None,
    )
    beam_covariance = geometry.restoring_beam_covariance_pixels_squared
    if config.model_selection == "free-only" or beam_covariance is None:
        return _free_compatibility_result(
            compact,
            valid_moment,
            free,
            geometry,
            config,
        )

    fallback_reason = _free_fallback_reason(free, beam_covariance, config)
    if fallback_reason is None:
        return _selected_fit_result(
            compact,
            valid_moment,
            free,
            geometry,
            config,
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
        ),
        fallback_reason=fallback_reason,
    )
    forced = _centroid_constrained_retry(
        samples,
        free=free,
        constrained=constrained,
        fallback_reason=fallback_reason,
        initial=initial,
        lower=lower,
        upper=upper,
        fixed_background=fixed_background,
    )
    if forced is not None:
        return _selected_fit_result(
            compact,
            valid_moment,
            forced,
            geometry,
            config,
        )
    if (
        fallback_reason == "free-model-not-significantly-extended"
        and _free_preferred_by_bic(free, constrained, samples)
    ):
        return _selected_fit_result(
            compact,
            valid_moment,
            _with_rejected_model(free, constrained),
            geometry,
            config,
        )
    return _selected_fit_result(
        compact,
        valid_moment,
        _with_rejected_model(constrained, free),
        geometry,
        config,
    )
