# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic tests for the fit-all compact Gaussian reference."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest
from astropy.modeling import fitting, models

from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.fitting import fit_compact_gaussian
from hebog.algorithms.measurement import measure_compact_moments
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    FailedCompactGaussianFit,
    UnavailableCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.measurement import CompactMeasurementGeometry
from hebog.data_models.partitioning import ImageBounds


@dataclass(frozen=True, slots=True)
class _FitInput:
    """Exact one-region input accepted by moment and fitting kernels."""

    island: DetectedIsland
    array_bounds: ImageBounds
    regions: tuple[DeblendedRegion, ...]
    physical_residual: np.ndarray
    rms: np.ndarray
    valid_pixels: np.ndarray
    region_labels: np.ndarray


def _geometry() -> CompactMeasurementGeometry:
    return CompactMeasurementGeometry(
        pixel_solid_angle_steradians=1.0,
        restoring_beam_solid_angle_steradians=8.0,
    )


def _moment_config() -> CompactMomentConfig:
    return CompactMomentConfig(
        minimum_shape_pixels=3,
        covariance_relative_tolerance=1e-12,
    )


def _fit_config(**changes: object) -> CompactGaussianFitConfig:
    values: dict[str, object] = {
        "minimum_fit_pixels": 7,
        "maximum_function_evaluations": 300,
        "minimum_sigma_pixels": 0.2,
        "maximum_sigma_pixels": 20.0,
        "maximum_amplitude_factor": 5.0,
        "center_margin_pixels": 1.0,
        "convergence_tolerance": 1e-10,
        "maximum_axis_ratio": 20.0,
        "maximum_background_offset_sigma": 3.0,
        "context_margin_pixels": 8,
    }
    values.update(changes)
    return CompactGaussianFitConfig(**values)  # type: ignore[arg-type]


def _gaussian_input(  # noqa: PLR0913
    *,
    amplitude: float = 3.0,
    centroid_xy: tuple[float, float] = (28.3, 17.6),
    sigma_axes: tuple[float, float] = (2.4, 1.3),
    angle_degrees: float = 32.0,
    shape_yx: tuple[int, int] = (17, 19),
    origin_yx: tuple[int, int] = (10, 20),
    rms_value: float = 0.05,
) -> _FitInput:
    """Construct one exact bounded analytic Gaussian region."""
    y_start, x_start = origin_yx
    y, x = np.indices(shape_yx, dtype=np.float64)
    x += x_start
    y += y_start
    theta = np.deg2rad(angle_degrees)
    x_offset = x - centroid_xy[0]
    y_offset = y - centroid_xy[1]
    major_offset = np.cos(theta) * x_offset + np.sin(theta) * y_offset
    minor_offset = -np.sin(theta) * x_offset + np.cos(theta) * y_offset
    residual = amplitude * np.exp(
        -0.5
        * (
            np.square(major_offset / sigma_axes[0])
            + np.square(minor_offset / sigma_axes[1])
        )
    )
    labels = np.ones(shape_yx, dtype=np.int32)
    bounds = ImageBounds(
        y_start,
        y_start + shape_yx[0],
        x_start,
        x_start + shape_yx[1],
    )
    peak = np.unravel_index(np.argmax(residual), residual.shape)
    island = DetectedIsland(
        island_id="island-00001",
        global_label=1,
        pixel_count=residual.size,
        bounds=bounds,
        peak_signal_to_noise=float(residual[peak] / rms_value),
        peak_position_yx=(
            y_start + int(peak[0]),
            x_start + int(peak[1]),
        ),
        first_pixel_yx=(y_start, x_start),
        touches_image_edge=False,
    )
    region = DeblendedRegion(
        region_id="island-00001-region-00001",
        region_label=1,
        island_id=island.island_id,
        pixel_count=residual.size,
        bounds=bounds,
        peak_signal_to_noise=island.peak_signal_to_noise,
        peak_position_yx=island.peak_position_yx,
        first_pixel_yx=island.first_pixel_yx,
    )
    return _FitInput(
        island=island,
        array_bounds=bounds,
        regions=(region,),
        physical_residual=np.asarray(residual, dtype=np.float64),
        rms=np.full(shape_yx, rms_value, dtype=np.float64),
        valid_pixels=np.ones(shape_yx, dtype=np.bool_),
        region_labels=labels,
    )


def _fit(
    compact: _FitInput,
    config: CompactGaussianFitConfig | None = None,
    geometry: CompactMeasurementGeometry | None = None,
):
    selected_geometry = geometry or _geometry()
    measurements = measure_compact_moments(
        compact,
        selected_geometry,
        _moment_config(),
    )
    return fit_compact_gaussian(
        compact,
        compact.regions[0],
        measurements[1],
        selected_geometry,
        config or _fit_config(),
    )


def test_scipy_fit_recovers_noiseless_subpixel_gaussian() -> None:
    """The selected fit-all path recovers all six Gaussian parameters."""
    result = _fit(_gaussian_input())

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.parameters.amplitude_jy_per_beam == pytest.approx(
        3.0, rel=1e-7
    )
    assert result.parameters.centroid_xy == pytest.approx(
        (28.3, 17.6), abs=1e-7
    )
    assert result.parameters.major_sigma_pixels == pytest.approx(2.4, rel=1e-7)
    assert result.parameters.minor_sigma_pixels == pytest.approx(1.3, rel=1e-7)
    assert result.parameters.major_axis_angle_degrees == pytest.approx(
        32.0, abs=1e-6
    )
    assert result.parameters.integrated_flux_jy == pytest.approx(
        3.0 * 2.0 * np.pi * 2.4 * 1.3 / 8.0,
        rel=1e-7,
    )
    assert result.parameters.local_rms_jy_per_beam == 0.05
    assert result.diagnostics.converged
    assert result.diagnostics.function_evaluations <= 300
    assert result.diagnostics.reduced_chi_squared == pytest.approx(
        0.0, abs=1e-15
    )


def test_fit_is_translation_and_positive_scaling_equivariant() -> None:
    """Global origin and brightness units do not change fitted shape."""
    first = _fit(
        _gaussian_input(
            amplitude=2.0,
            centroid_xy=(8.4, 7.2),
            origin_yx=(0, 0),
        )
    )
    second = _fit(
        _gaussian_input(
            amplitude=20.0,
            centroid_xy=(108.4, 207.2),
            origin_yx=(200, 100),
            rms_value=0.5,
        )
    )

    assert isinstance(first, ValidCompactGaussianFit)
    assert isinstance(second, ValidCompactGaussianFit)
    assert second.parameters.amplitude_jy_per_beam == pytest.approx(
        10.0 * first.parameters.amplitude_jy_per_beam
    )
    assert second.parameters.centroid_xy == pytest.approx((108.4, 207.2))
    assert second.parameters.major_sigma_pixels == pytest.approx(
        first.parameters.major_sigma_pixels
    )
    assert second.parameters.minor_sigma_pixels == pytest.approx(
        first.parameters.minor_sigma_pixels
    )


def test_formal_errors_account_for_correlated_noise() -> None:
    """A reviewed correlation model adjusts covariance, not fitted values."""
    compact = _gaussian_input()
    independent = _fit(compact)
    correlated = _fit(
        compact,
        geometry=CompactMeasurementGeometry(
            pixel_solid_angle_steradians=1.0,
            restoring_beam_solid_angle_steradians=8.0,
            noise_correlation_covariance_pixels_squared=(4.0, 0.0, 4.0),
        ),
    )

    assert isinstance(independent, ValidCompactGaussianFit)
    assert isinstance(correlated, ValidCompactGaussianFit)
    assert independent.uncertainty is not None
    assert correlated.uncertainty is not None
    assert correlated.parameters == independent.parameters
    assert "formal-independent-pixel-errors" in independent.quality_flags
    assert "correlated-noise-sandwich-errors" in correlated.quality_flags
    assert correlated.uncertainty.amplitude_error_jy_per_beam > (
        independent.uncertainty.amplitude_error_jy_per_beam
    )
    assert (
        correlated.uncertainty.centroid_covariance_xx_pixels_squared
        > independent.uncertainty.centroid_covariance_xx_pixels_squared
    )
    assert correlated.uncertainty.integrated_flux_error_jy > (
        independent.uncertainty.integrated_flux_error_jy
    )


def test_fit_bilinearly_samples_rms_at_the_fitted_centroid() -> None:
    """Component noise uses the contract's sub-pixel local RMS value."""
    compact = _gaussian_input(centroid_xy=(28.25, 17.5))
    local_y, local_x = np.indices(compact.rms.shape, dtype=np.float64)
    compact.rms[:] = 0.01 + 0.001 * local_x + 0.002 * local_y

    result = _fit(compact)

    assert isinstance(result, ValidCompactGaussianFit)
    expected = 0.01 + 0.001 * 8.25 + 0.002 * 7.5
    assert result.parameters.local_rms_jy_per_beam == pytest.approx(expected)


def test_context_fit_samples_rms_relative_to_the_retained_array() -> None:
    """Expanded fit context does not shift the local-RMS coordinate frame."""
    compact = _gaussian_input(centroid_xy=(28.25, 17.5))
    margin = 8
    expanded_shape = (
        compact.physical_residual.shape[0] + 2 * margin,
        compact.physical_residual.shape[1] + 2 * margin,
    )
    residual = np.zeros(expanded_shape, dtype=np.float64)
    labels = np.zeros(expanded_shape, dtype=np.int32)
    core = (
        slice(margin, -margin),
        slice(margin, -margin),
    )
    residual[core] = compact.physical_residual
    labels[core] = compact.region_labels
    local_y, local_x = np.indices(expanded_shape, dtype=np.float64)
    rms = 0.01 + 0.001 * local_x + 0.002 * local_y
    expanded = replace(
        compact,
        array_bounds=ImageBounds(
            compact.island.bounds.y_start - margin,
            compact.island.bounds.y_stop + margin,
            compact.island.bounds.x_start - margin,
            compact.island.bounds.x_stop + margin,
        ),
        physical_residual=residual,
        rms=np.asarray(rms, dtype=np.float64),
        valid_pixels=np.ones(expanded_shape, dtype=np.bool_),
        region_labels=labels,
    )

    result = _fit(expanded)

    assert isinstance(result, ValidCompactGaussianFit)
    expected = 0.01 + 0.001 * 16.25 + 0.002 * 15.5
    assert result.parameters.local_rms_jy_per_beam == pytest.approx(expected)


def test_scipy_selection_agrees_with_independent_astropy_model() -> None:
    """SciPy and Astropy recover the same governed analytic Gaussian."""
    compact = _gaussian_input(angle_degrees=121.0)
    selected = _fit(compact)
    y, x = np.indices(compact.physical_residual.shape, dtype=np.float64)
    x += compact.island.bounds.x_start
    y += compact.island.bounds.y_start
    astropy_model = models.Gaussian2D(
        amplitude=2.8,
        x_mean=28.0,
        y_mean=18.0,
        x_stddev=2.2,
        y_stddev=1.2,
        theta=np.deg2rad(120.0),
        bounds={
            "amplitude": (0.1, 15.0),
            "x_mean": (19.0, 40.0),
            "y_mean": (9.0, 28.0),
            "x_stddev": (0.2, 20.0),
            "y_stddev": (0.2, 20.0),
            "theta": (-np.pi, np.pi),
        },
    )
    astropy_fit = fitting.TRFLSQFitter()(
        astropy_model, x, y, compact.physical_residual
    )

    assert isinstance(selected, ValidCompactGaussianFit)
    assert float(astropy_fit.amplitude.value) == pytest.approx(
        selected.parameters.amplitude_jy_per_beam,
        rel=1e-6,
    )
    assert (
        float(astropy_fit.x_mean.value),
        float(astropy_fit.y_mean.value),
    ) == (pytest.approx(selected.parameters.centroid_xy, abs=1e-6))


def test_iteration_limit_returns_typed_failure_with_initializer() -> None:
    """Non-convergence preserves the moment initializer and diagnostics."""
    compact = _gaussian_input()

    result = _fit(
        compact,
        _fit_config(maximum_function_evaluations=1),
    )

    assert isinstance(result, FailedCompactGaussianFit)
    assert result.reason == "fit-non-convergence"
    assert all(np.isfinite(result.moment.initializer.centroid_xy))
    assert result.diagnostics.function_evaluations == 1
    assert result.quality_flags == ("fit-non-convergence",)


def test_underdetermined_measurement_is_not_fitted() -> None:
    """A target below the fit population returns an explicit unavailability."""
    compact = _gaussian_input(shape_yx=(2, 3), origin_yx=(16, 25))

    result = _fit(compact)

    assert isinstance(result, UnavailableCompactGaussianFit)
    assert result.reason == "underdetermined-region"
    assert result.quality_flags == ("fit-unavailable",)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"minimum_fit_pixels": 6}, "minimum_fit_pixels"),
        ({"maximum_function_evaluations": 0}, "function_evaluations"),
        ({"minimum_sigma_pixels": 0.0}, "sigma"),
        ({"maximum_sigma_pixels": 0.1}, "sigma"),
        ({"maximum_amplitude_factor": 1.0}, "amplitude"),
        ({"center_margin_pixels": -1.0}, "center_margin"),
        ({"convergence_tolerance": 0.0}, "convergence"),
        ({"maximum_axis_ratio": 1.0}, "axis_ratio"),
        ({"maximum_background_offset_sigma": 0.0}, "background_offset"),
        ({"context_margin_pixels": -1}, "context_margin"),
    ],
)
def test_fit_policy_rejects_invalid_bounds(
    changes: dict[str, object],
    message: str,
) -> None:
    """Every numerical and work bound is explicit and validated."""
    with pytest.raises(ValueError, match=message):
        _fit_config(**changes)
