# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded joint compact Gaussian fitting with SciPy least squares."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import pairwise
from math import ceil, floor, isfinite, pi, sqrt
from typing import Literal, TypeAlias, cast

import numpy as np
import numpy.typing as npt
from scipy.linalg import solve_triangular
from scipy.linalg.lapack import dpocon  # type: ignore[attr-defined]
from scipy.ndimage import map_coordinates
from scipy.optimize import OptimizeResult, least_squares

from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.fft import fftconvolve
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
from hebog.data_models.partitioning import ImageBounds

_NOISE_CORRELATION_TRUNCATION_SIGMA = 4.0
_RELATIVE_BOUND_CONTACT_TOLERANCE = 1e-10
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
MAXIMUM_JOINT_FIT_PARAMETERS = 96
"""Free parameters one joint fit admits: sixteen fixed-background ellipses."""
MAXIMUM_JOINT_FIT_JACOBIAN_ELEMENTS = 1_000_000
"""Parameters times fitted pixels one joint fit admits."""
_CONSTRAINED_PARAMETER_NAMES = (
    "amplitude",
    "centroid-x",
    "centroid-y",
    "background",
)
_CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES = _CONSTRAINED_PARAMETER_NAMES[
    :-1
]
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
    "correlation-conditioning-failed",
    "correlation-ill-conditioned",
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


def _information_condition(jacobian: np.ndarray) -> float | None:
    """Condition the complete information matrix in dimensionless units."""
    norms = np.linalg.norm(jacobian, axis=0)
    if not np.all(np.isfinite(norms) & (norms > 0.0)):
        return None
    normalized = jacobian / norms
    condition = float(np.linalg.cond(normalized.T @ normalized))
    return condition if isfinite(condition) else None


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
    # Bound contact must not depend on flux units or a tile's global origin.
    # Use the same dimensionless distance retained in public diagnostics.
    at_bound = relative_bound_distances <= _RELATIVE_BOUND_CONTACT_TOLERANCE
    at_bound |= np.asarray(
        [
            name.startswith("forced-centroid-")
            for name in evidence.parameter_names
        ]
    )
    information_condition = _information_condition(jacobian)
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
        information_condition_number=information_condition,
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
    norms = np.linalg.norm(jacobian, axis=0)
    if not np.all(np.isfinite(norms) & (norms > 0.0)):
        return None
    normalized = jacobian / norms
    information = normalized.T @ normalized
    if np.linalg.matrix_rank(information) != jacobian.shape[1]:
        return None
    correlation = geometry.noise_correlation_covariance_pixels_squared
    scaled_covariance = np.asarray(
        np.linalg.inv(information)
        if correlation is None or correlated_point_estimator
        else _correlated_parameter_covariance(
            normalized,
            coordinates_xy,
            correlation,
        ),
        dtype=np.float64,
    )
    return scaled_covariance / norms[:, None] / norms[None, :]


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


def _resolved_correlation_factor(
    correlation_matrix: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64] | None, _PointEstimatorFallback | None]:
    """Factor only a correlation matrix resolved above float64 roundoff."""
    try:
        factor = np.linalg.cholesky(correlation_matrix)
    except np.linalg.LinAlgError:
        return None, "correlation-factorization-failed"
    # Factorization alone does not establish numerical invertibility. An
    # oversampled smooth covariance can lose rank at float64 roundoff even
    # when Cholesky succeeds. Do not add an unmeasured white-noise floor to
    # make its inverse usable. The dimension-scaled roundoff criterion is
    # independent of the observed residual, fitted position and brightness.
    # LAPACK estimates the inverse norm from the existing factor in O(n^2)
    # work, without a second factorization or a dense inverse.
    reciprocal_condition, info = dpocon(
        factor, float(np.linalg.norm(correlation_matrix, 1)), uplo="L"
    )
    if info != 0 or not np.isfinite(reciprocal_condition):
        return None, "correlation-conditioning-failed"
    tolerance = correlation_matrix.shape[0] * np.finfo(np.float64).eps
    if reciprocal_condition <= tolerance:
        return None, "correlation-ill-conditioned"
    return cast(npt.NDArray[np.float64], factor), None


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
    factor, failure = _resolved_correlation_factor(correlation_matrix)
    if factor is None:
        return identity, "diagonal-weighted", failure

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
        and sigma_first > 0
        and sigma_second > 0
        # Optimizer axes are interchangeable under a quarter-turn rotation.
        and max(sigma_first, sigma_second) / min(sigma_first, sigma_second)
        <= config.maximum_axis_ratio
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
    *,
    free_parameter_count: int,
    constrained_parameter_count: int,
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

    def bic(candidate: _FitCandidate, parameter_count: int) -> float:
        return candidate.diagnostics.chi_squared * chi_squared_scale + (
            parameter_count * np.log(independent_samples)
        )

    return bic(free, free_parameter_count) < bic(
        constrained, constrained_parameter_count
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


def _valid_fit_result(
    context: _FitPublicationContext,
    candidate: _FitCandidate,
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


def _selected_fit_result(
    context: _FitPublicationContext,
    candidate: _FitCandidate,
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
    return _valid_fit_result(context, candidate)


def _mixture_initial_bounds(
    moment: ValidMomentMeasurement,
    region: DeblendedRegion,
    samples: _FitSamples,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reuse the free Gaussian parameterization on one owned seed."""
    config = samples.config
    initial = moment.initializer
    lower = np.asarray(
        (
            np.finfo(np.float64).tiny,
            max(
                region.bounds.x_start - 0.5 - config.center_margin_pixels,
                samples.x.min() - 0.5,
            ),
            max(
                region.bounds.y_start - 0.5 - config.center_margin_pixels,
                samples.y.min() - 0.5,
            ),
            config.minimum_sigma_pixels,
            config.minimum_sigma_pixels,
            -pi,
        ),
        dtype=np.float64,
    )
    upper = np.asarray(
        (
            samples.values.max() * config.maximum_amplitude_factor,
            min(
                region.bounds.x_stop - 0.5 + config.center_margin_pixels,
                samples.x.max() + 0.5,
            ),
            min(
                region.bounds.y_stop - 0.5 + config.center_margin_pixels,
                samples.y.max() + 0.5,
            ),
            config.maximum_sigma_pixels,
            config.maximum_sigma_pixels,
            pi,
        ),
        dtype=np.float64,
    )
    parameters = np.asarray(
        (
            initial.amplitude_jy_per_beam,
            *initial.centroid_xy,
            initial.major_sigma_pixels,
            initial.minor_sigma_pixels,
            np.deg2rad(initial.major_axis_angle_degrees),
        ),
        dtype=np.float64,
    )
    # Orientation is periodic, not a physical acceptance boundary. Centre
    # the same full-turn interval on the moment initializer so an eigenvector
    # sign cannot place the optimizer directly against an artificial limit.
    lower[5], upper[5] = parameters[5] - pi, parameters[5] + pi
    return np.clip(parameters, lower, upper), lower, upper


def _mixture_model(
    parameters: np.ndarray, x: np.ndarray, y: np.ndarray
) -> np.ndarray:
    """Sum component models; background has already been subtracted once."""
    return np.sum(
        [
            _gaussian_values(np.append(row, 0.0), x, y)
            for row in parameters.reshape(-1, 6)
        ],
        axis=0,
    )


def _mixture_jacobian(
    parameters: np.ndarray, x: np.ndarray, y: np.ndarray
) -> np.ndarray:
    """Reuse the analytic Gaussian derivative for one joint solve."""
    return np.concatenate(
        [
            _gaussian_parameter_jacobian(np.append(row, 0.0), x, y)[:, :6]
            for row in parameters.reshape(-1, 6)
        ],
        axis=1,
    )


def _precision_shape_jacobian(
    parameters: np.ndarray, x: np.ndarray, y: np.ndarray
) -> np.ndarray:
    """Differentiate a Gaussian in Cartesian inverse-covariance coordinates.

    Unlike an ellipse angle, Qxx/Qxy/Qyy remain identifiable at a circle.
    This changes only the information basis, not the fitted emission model.
    """
    model = _gaussian_values(parameters, x, y)
    dx, dy = x - parameters[1], y - parameters[2]
    return np.column_stack(
        (
            _gaussian_parameter_jacobian(parameters, x, y)[:, :3],
            -0.5 * model * dx**2,
            -model * dx * dy,
            -0.5 * model * dy**2,
        )
    )


def _precision_to_ellipse_differential(parameters: np.ndarray) -> np.ndarray:
    """Transform identifiable flux/position/area errors into native units.

    At a numerical circle the angle derivative is undefined. Its zero row
    is an internal unavailable marker: `_formal_uncertainty` rejects that
    shape covariance, while the invariant area and position errors survive.
    Ordered-axis/angle errors are never published as zero uncertainties.
    """
    first, second, theta = parameters[3:6]
    cosine, sine = np.cos(theta), np.sin(theta)
    transform = np.eye(6)
    transform[3:, 3:] = 0
    transform[3, 3:] = (
        -0.5 * first**3 * np.array((cosine**2, 2 * cosine * sine, sine**2))
    )
    transform[4, 3:] = (
        -0.5 * second**3 * np.array((sine**2, -2 * cosine * sine, cosine**2))
    )
    gap = 1 / first**2 - 1 / second**2
    # This is a numerical-coordinate singularity, not a resolved threshold.
    if abs(gap) > np.sqrt(np.finfo(float).eps) * max(
        1 / first**2, 1 / second**2
    ):
        transform[5, 3:] = (
            np.array((-cosine * sine, cosine**2 - sine**2, cosine * sine))
            / gap
        )
    return transform


def _recover_joint_shape_information(
    samples: _FitSamples,
    candidates: tuple[_FitCandidate, ...],
) -> tuple[_FitCandidate, ...]:
    """Recover angular-coordinate singularities without masking true blends."""
    blocks = tuple(
        _precision_shape_jacobian(
            candidate.full_parameters, samples.x, samples.y
        )
        if candidate.optimizer_parameters.size
        == len(_FREE_FIXED_BACKGROUND_PARAMETER_NAMES)
        else candidate.jacobian
        for candidate in candidates
    )
    # Only free blocks need re-whitening; constrained blocks already use the
    # exact objective's transformed Jacobian.
    weighted = tuple(
        samples.residual_transform(block / samples.rms[:, None])
        if candidate.optimizer_parameters.size
        == len(_FREE_FIXED_BACKGROUND_PARAMETER_NAMES)
        else block
        for candidate, block in zip(candidates, blocks, strict=True)
    )
    covariance = _parameter_covariance(
        np.column_stack(weighted),
        np.column_stack((samples.x, samples.y)),
        samples.geometry,
        correlated_point_estimator=samples.point_estimator == "correlated-gls",
    )
    if covariance is None:
        # Marginal blocks can be full rank while the complete mixture is
        # singular. Neither ellipse nor Cartesian coordinates identified it.
        return tuple(
            replace(
                candidate,
                diagnostics=replace(
                    candidate.diagnostics, information_condition_number=None
                ),
            )
            for candidate in candidates
        )
    condition = _information_condition(np.column_stack(weighted))
    output = []
    start = 0
    for candidate in candidates:
        stop = start + candidate.optimizer_parameters.size
        marginal = covariance[start:stop, start:stop]
        if stop - start == len(_FREE_FIXED_BACKGROUND_PARAMETER_NAMES):
            transform = _precision_to_ellipse_differential(
                candidate.full_parameters
            )
            marginal = transform @ marginal @ transform.T
        output.append(
            replace(
                candidate,
                covariance=marginal,
                diagnostics=replace(
                    candidate.diagnostics,
                    information_condition_number=condition,
                    covariance_parameterization="cartesian-precision",
                ),
            )
        )
        start = stop
    return tuple(output)


def _mixture_component_candidate(  # noqa: PLR0913, PLR0917
    samples: _FitSamples,
    result: OptimizeResult,
    covariance: np.ndarray | None,
    initial_bounds: tuple[np.ndarray, np.ndarray, np.ndarray],
    block: slice,
    full_parameters: np.ndarray,
    fallback_reason: _FallbackReason | None,
) -> _FitCandidate:
    """Keep marginal parameters and errors from the same joint solution."""
    optimizer = result
    parameters = np.asarray(optimizer.x[block], dtype=np.float64)
    _, lower, upper = initial_bounds
    constrained = parameters.size == len(
        _CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES
    )
    diagnostics = _diagnostics(
        converged=bool(optimizer.success),
        function_evaluations=int(optimizer.nfev),
        evidence=_FitEvidence(
            parameters=parameters,
            lower_bounds=lower[: parameters.size],
            upper_bounds=upper[: parameters.size],
            jacobian=np.asarray(optimizer.jac[:, block]),
            x=samples.x,
            y=samples.y,
            weighted_residual=np.asarray(optimizer.fun),
            parameter_names=(
                _CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES
                if constrained
                else _FREE_FIXED_BACKGROUND_PARAMETER_NAMES
            ),
            model_identity="beam-constrained"
            if constrained
            else "free-elliptical",
            full_parameters=full_parameters,
            fallback_reason=fallback_reason,
            point_estimator=samples.point_estimator,
            point_estimator_fallback_reason=samples.point_estimator_fallback_reason,
        ),
    )
    degrees_of_freedom = samples.x.size - optimizer.x.size
    diagnostics = replace(
        diagnostics,
        degrees_of_freedom=int(degrees_of_freedom),
        reduced_chi_squared=(
            diagnostics.chi_squared / degrees_of_freedom
            if degrees_of_freedom > 0
            else None
        ),
    )
    return _FitCandidate(
        success=bool(optimizer.success),
        optimizer_parameters=parameters,
        full_parameters=full_parameters,
        jacobian=np.asarray(optimizer.jac[:, block]),
        covariance=None if covariance is None else covariance[block, block],
        diagnostics=diagnostics,
    )


def _publish_mixture_component(
    context: _FitPublicationContext, candidate: _FitCandidate
) -> CompactGaussianFitResult:
    """Do not mix parameters, covariance or flux from competing joint fits."""
    fitted = _selected_fit_result(context, candidate)
    if not isinstance(fitted, ValidCompactGaussianFit):
        return replace(
            fitted, quality_flags=(*fitted.quality_flags, "joint-gaussian-fit")
        )
    return replace(
        fitted,
        quality_flags=tuple(
            sorted({*fitted.quality_flags, "joint-gaussian-fit"})
        ),
        # A neighbour-contaminated per-component aperture is not joint flux.
        association_aperture=None,
    )


def joint_fit_admits(
    component_count: int,
    pixel_count: int,
    *,
    maximum_parameters: int = MAXIMUM_JOINT_FIT_PARAMETERS,
    maximum_jacobian_elements: int = MAXIMUM_JOINT_FIT_JACOBIAN_ELEMENTS,
) -> bool:
    """Return whether one joint fit admits this many components and pixels.

    The work is a Jacobian of six parameters per component by the fitted
    pixels, refused before it is allocated. With ``owned-region`` pixel
    support the fitted pixels are the components' own, so a caller that
    counts those can apply this rule before any fit runs.
    """
    parameter_count = len(_FREE_FIXED_BACKGROUND_PARAMETER_NAMES) * (
        component_count
    )
    return (
        parameter_count <= maximum_parameters
        and parameter_count * pixel_count <= maximum_jacobian_elements
    )


def fit_compact_gaussian_mixture(  # noqa: PLR0913
    compact: CompactMomentInput,
    moments: tuple[CompactMomentMeasurement, ...],
    geometry: CompactMeasurementGeometry,
    config: CompactGaussianFitConfig,
    *,
    maximum_parameters: int = MAXIMUM_JOINT_FIT_PARAMETERS,
    maximum_jacobian_elements: int = MAXIMUM_JOINT_FIT_JACOBIAN_ELEMENTS,
) -> tuple[CompactGaussianFitResult, ...]:
    """Fit bounded neighbouring components jointly on original pixels.

    This extends the existing free-ellipse solver, derivative, noise transform
    and covariance machinery. It does not add components or change detection.
    Callers supply one bounded parent plus context, excluding foreign owners.
    Work admission precedes allocation of the joint Jacobian. The background
    is fixed at the caller's independently estimated background map.
    """
    if config.background_model != "fixed-zero":
        raise ValueError(
            "joint compact fitting requires fixed-zero background"
        )
    if (
        type(maximum_parameters) is not int
        or type(maximum_jacobian_elements) is not int
        or maximum_parameters < len(_FREE_FIXED_BACKGROUND_PARAMETER_NAMES)
        or maximum_jacobian_elements < 1
    ):
        raise ValueError(
            "joint fit work limits must be positive and admit six parameters"
        )
    by_id = {moment.target.object_id: moment for moment in moments}
    if len(by_id) != len(moments) or set(by_id) != {
        region.region_id for region in compact.regions
    }:
        raise ValueError(
            "joint moments must identify every component exactly once"
        )
    ordered = tuple(by_id[region.region_id] for region in compact.regions)
    if not ordered:
        return ()
    available = tuple(_unavailable_fit(moment, config) for moment in ordered)
    if any(item is not None for item in available):
        return tuple(
            absent
            if absent is not None
            else UnavailableCompactGaussianFit(
                moment=moment,
                reason="joint-peer-unavailable",
                quality_flags=("fit-unavailable", "joint-peer-unavailable"),
            )
            for moment, absent in zip(ordered, available, strict=True)
        )
    valid = (
        np.asarray(compact.valid_pixels)
        & np.isfinite(compact.physical_residual)
        & np.isfinite(compact.rms)
        & (compact.rms > 0.0)
    )
    # Likelihood support is independent of the much larger adequacy halo.
    # All neighbours contribute their complete models at every retained
    # pixel; an ownership boundary never truncates an individual Gaussian.
    if config.pixel_support == "owned-region":
        valid &= np.isin(
            compact.region_labels,
            tuple(region.region_label for region in compact.regions),
        )
    parameter_count = len(_FREE_FIXED_BACKGROUND_PARAMETER_NAMES) * len(
        ordered
    )
    pixel_count = int(np.count_nonzero(valid))
    if not joint_fit_admits(
        len(ordered),
        pixel_count,
        maximum_parameters=maximum_parameters,
        maximum_jacobian_elements=maximum_jacobian_elements,
    ):
        return tuple(
            UnavailableCompactGaussianFit(
                moment=moment,
                reason="joint-fit-work-limit",
                quality_flags=("fit-unavailable", "joint-fit-work-limit"),
            )
            for moment in ordered
        )
    if pixel_count <= parameter_count:
        return tuple(
            UnavailableCompactGaussianFit(
                moment=moment,
                reason="underdetermined-region",
                quality_flags=("fit-unavailable",),
            )
            for moment in ordered
        )
    bounds = getattr(compact, "array_bounds", compact.island.bounds)
    samples = _fit_samples_from_mask(compact, valid, bounds, geometry, config)
    contexts = tuple(
        _FitPublicationContext(
            compact,
            region,
            cast(ValidMomentMeasurement, moment),
            geometry,
            config,
        )
        for region, moment in zip(compact.regions, ordered, strict=True)
    )
    initial_bounds = tuple(
        _mixture_initial_bounds(context.moment, context.region, samples)
        for context in contexts
    )
    return _solve_joint_components(samples, contexts, initial_bounds)


def _solve_joint_components(
    samples: _FitSamples,
    contexts: tuple[_FitPublicationContext, ...],
    initial_bounds: tuple[tuple[np.ndarray, np.ndarray, np.ndarray], ...],
) -> tuple[CompactGaussianFitResult, ...]:
    """Solve admitted joint work and publish all neighbours atomically."""
    try:
        free = _joint_candidates(
            samples, initial_bounds, (None,) * len(contexts)
        )
        selected = _select_joint_candidates(samples, initial_bounds, free)
        return tuple(
            _publish_mixture_component(context, candidate)
            for context, candidate in zip(contexts, selected, strict=True)
        )
    except np.linalg.LinAlgError:
        # Joint parameters and covariance are coupled. Never salvage only
        # a subset of neighbours after a numerical decomposition failure.
        return tuple(
            FailedCompactGaussianFit(
                moment=context.moment,
                reason="fit-linear-algebra-failure",
                diagnostics=None,
                quality_flags=("joint-gaussian-fit", "fit-failed"),
            )
            for context in contexts
        )


def _select_joint_candidates(
    samples: _FitSamples,
    initial_bounds: tuple[tuple[np.ndarray, np.ndarray, np.ndarray], ...],
    free: tuple[_FitCandidate, ...],
) -> tuple[_FitCandidate, ...]:
    """Compare coherent nested joint models with the existing evidence rule.

    Significantly extended neighbours keep free shapes in both models. Other
    components share one beam-constrained alternative, so selection is
    permutation invariant and requires at most two bounded joint solves.
    The BIC counts every fitted parameter once and the joint residual once.
    """
    beam = samples.geometry.restoring_beam_covariance_pixels_squared
    if samples.config.model_selection == "free-only" or beam is None:
        return free
    reasons: tuple[_FallbackReason | None, ...] = tuple(
        _free_fallback_reason(item, beam, samples.config) for item in free
    )
    if not any(reasons):
        return free
    constrained = _joint_candidates(samples, initial_bounds, reasons)
    constrained_failed = any(
        not item.success
        or not _numerically_valid(item, samples.config)
        or not _identifiable(item, samples.config)
        for item in constrained
    )
    # A failed or physically invalid free model cannot win on goodness of
    # fit. Insignificant extension alone may retain it on the existing BIC.
    retain_free = all(
        reason in (None, "free-model-not-significantly-extended")
        for reason in reasons
    ) and (
        constrained_failed
        or _free_preferred_by_bic(
            free[0],
            constrained[0],
            samples,
            free_parameter_count=sum(
                item.optimizer_parameters.size for item in free
            ),
            constrained_parameter_count=sum(
                item.optimizer_parameters.size for item in constrained
            ),
        )
    )
    selected, rejected = (
        (free, constrained) if retain_free else (constrained, free)
    )
    return tuple(
        _with_rejected_model(chosen, other)
        for chosen, other in zip(selected, rejected, strict=True)
    )


def _joint_candidates(
    samples: _FitSamples,
    initial_bounds: tuple[tuple[np.ndarray, np.ndarray, np.ndarray], ...],
    reasons: tuple[_FallbackReason | None, ...],
) -> tuple[_FitCandidate, ...]:
    """Solve one nested joint model and retain its marginal covariance."""
    config = samples.config
    geometry = samples.geometry
    sizes = tuple(3 if reason else 6 for reason in reasons)
    offsets = np.cumsum((0, *sizes))
    blocks = tuple(
        slice(int(start), int(stop)) for start, stop in pairwise(offsets)
    )
    beam = geometry.restoring_beam_covariance_pixels_squared
    # No constrained block is constructed without a physical beam. The
    # empty shape is unused by every free block, including free-only fits.
    beam_shape = _beam_shape(beam) if beam is not None else ()
    full_indices = np.concatenate(
        [
            np.arange(6 * index, 6 * index + size)
            for index, size in enumerate(sizes)
        ]
    )
    initial, lower, upper = (
        np.concatenate(
            [
                values[index][:size]
                for values, size in zip(initial_bounds, sizes, strict=True)
            ]
        )
        for index in range(3)
    )

    def expand(parameters: np.ndarray) -> np.ndarray:
        return np.concatenate(
            [
                np.concatenate((parameters[block], beam_shape))
                if size == len(_CONSTRAINED_FIXED_BACKGROUND_PARAMETER_NAMES)
                else parameters[block]
                for block, size in zip(blocks, sizes, strict=True)
            ]
        )

    def residual(parameters: np.ndarray) -> np.ndarray:
        return samples.residual_transform(
            (
                _mixture_model(expand(parameters), samples.x, samples.y)
                - samples.values
            )
            / samples.rms
        )

    def jacobian(parameters: np.ndarray) -> np.ndarray:
        return samples.residual_transform(
            _mixture_jacobian(expand(parameters), samples.x, samples.y)[
                :, full_indices
            ]
            / samples.rms[:, None]
        )

    result = least_squares(
        residual,
        initial,
        jac=jacobian,  # pyright: ignore[reportArgumentType]
        bounds=(lower, upper),
        method="trf",
        x_scale="jac",
        ftol=config.convergence_tolerance,
        xtol=config.convergence_tolerance,
        gtol=config.convergence_tolerance,
        max_nfev=config.maximum_function_evaluations,
    )
    covariance = _parameter_covariance(
        np.asarray(result.jac),
        np.column_stack((samples.x, samples.y)),
        geometry,
        correlated_point_estimator=(
            samples.point_estimator == "correlated-gls"
        ),
    )
    full = expand(np.asarray(result.x)).reshape(-1, 6)
    candidates = tuple(
        _mixture_component_candidate(
            samples,
            result,
            covariance,
            initial_bounds[index],
            blocks[index],
            np.append(full[index], 0.0),
            reasons[index],
        )
        for index in range(len(initial_bounds))
    )
    if covariance is None:
        return _recover_joint_shape_information(samples, candidates)
    condition = _information_condition(np.asarray(result.jac))
    return tuple(
        replace(
            candidate,
            diagnostics=replace(
                candidate.diagnostics, information_condition_number=condition
            ),
        )
        for candidate in candidates
    )
