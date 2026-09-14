# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic tests for the fit-all compact Gaussian reference."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import pytest
from astropy.modeling import fitting, models
from scipy.special import ndtr
from scipy.stats import chi2

from hebog.algorithms import fitting as fitting_algorithm
from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.fitting import (
    fit_compact_gaussian,
    fit_compact_gaussian_mixture,
)
from hebog.algorithms.measurement import measure_compact_moments
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    AssociationAperturePhotometry,
    CompactGaussianFitResult,
    FailedCompactGaussianFit,
    GaussianPositionEstimate,
    UnavailableCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.measurement import (
    CompactMeasurementGeometry,
    UnavailableMomentMeasurement,
    ValidMomentMeasurement,
)
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


def _beam_geometry() -> CompactMeasurementGeometry:
    """Return a self-consistent elliptical restoring beam in pixel space."""
    major_sigma = 1.6
    minor_sigma = 8.0 / (2.0 * np.pi * major_sigma)
    angle = np.deg2rad(20.0)
    major = np.asarray([np.cos(angle), np.sin(angle)])
    minor = np.asarray([-np.sin(angle), np.cos(angle)])
    covariance = major_sigma**2 * np.outer(
        major, major
    ) + minor_sigma**2 * np.outer(minor, minor)
    covariance_values = (
        float(covariance[0, 0]),
        float(covariance[0, 1]),
        float(covariance[1, 1]),
    )
    return CompactMeasurementGeometry(
        pixel_solid_angle_steradians=1.0,
        restoring_beam_solid_angle_steradians=8.0,
        restoring_beam_covariance_pixels_squared=covariance_values,
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


def test_gaussian_parameter_jacobian_matches_central_difference() -> None:
    """The production optimizer uses the exact rotated-Gaussian gradient."""
    parameters = np.asarray(
        (0.012, 3.2, -1.4, 2.7, 1.3, 0.37, -0.0002),
        dtype=np.float64,
    )
    x = np.asarray((-2.0, 0.5, 2.7, 4.3), dtype=np.float64)
    y = np.asarray((-3.1, -0.2, 1.8, 3.0), dtype=np.float64)
    actual = fitting_algorithm._gaussian_parameter_jacobian(parameters, x, y)
    finite = np.empty_like(actual)
    step = 1e-6
    for index in range(parameters.size):
        offset = np.zeros(parameters.size, dtype=np.float64)
        offset[index] = step
        finite[:, index] = (
            fitting_algorithm._gaussian_values(parameters + offset, x, y)
            - fitting_algorithm._gaussian_values(parameters - offset, x, y)
        ) / (2.0 * step)

    np.testing.assert_allclose(actual, finite, rtol=1e-6, atol=1e-9)


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


def _joint_input() -> _FitInput:
    """Overlapping ellipses with immutable initialization owners."""
    first = _gaussian_input(
        amplitude=10.0,
        centroid_xy=(12.0, 12.0),
        sigma_axes=(2.0, 1.5),
        angle_degrees=0.0,
        shape_yx=(25, 33),
        origin_yx=(0, 0),
        rms_value=1.0,
    )
    second = _gaussian_input(
        amplitude=7.0,
        centroid_xy=(19.0, 12.0),
        sigma_axes=(2.0, 1.5),
        angle_degrees=0.0,
        shape_yx=(25, 33),
        origin_yx=(0, 0),
        rms_value=1.0,
    )
    signal = first.physical_residual + second.physical_residual
    _, xx = np.mgrid[: signal.shape[0], : signal.shape[1]]
    labels = np.where(signal >= 3.0, np.where(xx <= 15, 1, 2), 0).astype(
        np.int32
    )
    regions = []
    for index in (1, 2):
        support = labels == index
        ys, xs = np.nonzero(support)
        peak = np.unravel_index(
            np.argmax(np.where(support, signal, -np.inf)), signal.shape
        )
        regions.append(
            replace(
                first.regions[0],
                region_id=f"component-{index}",
                region_label=index,
                pixel_count=int(support.sum()),
                bounds=ImageBounds(
                    int(ys.min()),
                    int(ys.max() + 1),
                    int(xs.min()),
                    int(xs.max() + 1),
                ),
                peak_position_yx=(int(peak[0]), int(peak[1])),
                peak_signal_to_noise=float(signal[peak]),
                first_pixel_yx=(int(ys[0]), int(xs[0])),
            )
        )
    return replace(
        first,
        island=replace(
            first.island, pixel_count=int(np.count_nonzero(labels))
        ),
        physical_residual=signal,
        regions=tuple(regions),
        region_labels=labels,
    )


def test_joint_fit_separates_neighbour_flux_and_keeps_marginal_errors() -> (
    None
):
    """Fit all neighbours simultaneously, including below-threshold wings."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    fits = fit_compact_gaussian_mixture(
        compact, moments, geometry, _fit_config(background_model="fixed-zero")
    )
    for fitted, amplitude, center in zip(
        fits, (10.0, 7.0), (12.0, 19.0), strict=True
    ):
        assert isinstance(fitted, ValidCompactGaussianFit)
        assert fitted.parameters.centroid_xy == pytest.approx(
            (center, 12.0), abs=1e-6
        )
        assert fitted.parameters.integrated_flux_jy == pytest.approx(
            amplitude * 2 * np.pi * 3 / 8, rel=1e-6
        )
        assert fitted.uncertainty is not None
        assert fitted.uncertainty.integrated_flux_error_jy > 0.0
        assert (
            fitted.diagnostics.degrees_of_freedom
            == compact.physical_residual.size - 12
        )
        assert fitted.association_aperture is None
        assert "joint-gaussian-fit" in fitted.quality_flags


@pytest.mark.parametrize("scale", (1e-9, 1.0, 1e9))
@pytest.mark.parametrize("correlated", (False, True))
def test_parameter_covariance_is_invariant_to_parameter_units(
    scale: float, correlated: bool
) -> None:
    """Identifiability cannot depend on using Jy versus another flux unit."""
    jacobian = np.tile(np.eye(3), (3, 1))
    jacobian[:, 0] *= scale
    coordinates = np.column_stack((np.arange(9, dtype=float), np.zeros(9)))
    geometry = replace(
        _geometry(),
        noise_correlation_covariance_pixels_squared=(1.0, 0.0, 1.0)
        if correlated
        else None,
    )
    expected = fitting_algorithm._parameter_covariance(
        np.tile(np.eye(3), (3, 1)),
        coordinates,
        geometry,
        correlated_point_estimator=False,
    )
    actual = fitting_algorithm._parameter_covariance(
        jacobian, coordinates, geometry, correlated_point_estimator=False
    )
    assert actual is not None
    assert expected is not None
    units = np.array((scale, 1.0, 1.0))
    np.testing.assert_allclose(
        actual * units[:, None] * units[None, :], expected, rtol=1e-12
    )


@pytest.mark.parametrize("invalid_column", (0.0, float("nan"), float("inf")))
def test_unavailable_information_cannot_fabricate_a_covariance(
    invalid_column: float,
) -> None:
    """Zero or non-finite information has neither condition nor uncertainty."""
    jacobian = np.eye(3)
    jacobian[:, 0] = invalid_column
    coordinates = np.column_stack((np.arange(3, dtype=float), np.zeros(3)))
    assert fitting_algorithm._information_condition(jacobian) is None
    assert (
        fitting_algorithm._parameter_covariance(
            jacobian, coordinates, _geometry(), correlated_point_estimator=True
        )
        is None
    )


def test_joint_unidentifiable_information_cannot_publish_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Well-conditioned marginal blocks do not identify a singular mixture."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]

    def unavailable_covariance(*_args: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(
        fitting_algorithm, "_parameter_covariance", unavailable_covariance
    )
    fitted = fit_compact_gaussian_mixture(
        compact, moments, geometry, _fit_config(background_model="fixed-zero")
    )
    assert len(fitted) == len(compact.regions)
    assert all(
        isinstance(item, FailedCompactGaussianFit)
        and item.reason == "fit-invalid-result"
        for item in fitted
    )


def test_joint_condition_cannot_be_replaced_by_marginal_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identifiable individual blocks can hide a nearly degenerate mixture."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    solver = fitting_algorithm.least_squares

    def ill_conditioned(*args: Any, **kwargs: Any) -> Any:
        result = solver(*args, **kwargs)
        jacobian = np.eye(*result.jac.shape)
        jacobian[:, -1] = jacobian[:, 0] + 1e-5 * jacobian[:, -1]
        result.jac = jacobian
        return result

    monkeypatch.setattr(fitting_algorithm, "least_squares", ill_conditioned)
    fitted = fit_compact_gaussian_mixture(
        compact, moments, geometry, _fit_config(background_model="fixed-zero")
    )
    assert all(isinstance(item, FailedCompactGaussianFit) for item in fitted)


@pytest.mark.parametrize("scale", (1e-9, 1.0, 1e9))
@pytest.mark.parametrize("distance", (5e-11, 1e-5))
def test_fit_bound_diagnostics_are_parameter_scale_invariant(
    scale: float, distance: float
) -> None:
    """Bound proximity uses dimensionless distance, not Jy or pixel units."""
    lower = np.array((0.0, 0.0, 0.0, 0.1, 0.1, -np.pi))
    upper = np.array((10.0, 20.0, 20.0, 10.0, 10.0, np.pi))
    parameters = np.array((10.0 * distance, 10.0, 10.0, 2.0, 1.5, 0.0))
    lower[0] *= scale
    upper[0] *= scale
    parameters[0] *= scale
    diagnostics = fitting_algorithm._diagnostics(
        converged=True,
        function_evaluations=1,
        evidence=fitting_algorithm._FitEvidence(
            parameters=parameters,
            lower_bounds=lower,
            upper_bounds=upper,
            jacobian=np.tile(np.eye(6), (2, 1)),
            x=np.arange(12, dtype=float),
            y=np.arange(12, dtype=float),
            weighted_residual=np.zeros(12),
            parameter_names=fitting_algorithm._FREE_FIXED_BACKGROUND_PARAMETER_NAMES,
            model_identity="free-elliptical",
            full_parameters=np.append(parameters, 0.0),
            fallback_reason=None,
            point_estimator="diagonal-weighted",
            point_estimator_fallback_reason=None,
        ),
    )
    assert ("amplitude" in diagnostics.bound_parameters) == (distance < 1e-10)
    assert dict(diagnostics.relative_bound_distances)["amplitude"] == (
        pytest.approx(distance)
    )


@pytest.mark.parametrize("joint", (False, True))
def test_joint_solver_honours_beam_or_free_policy(joint: bool) -> None:
    """Exact beam sources must not acquire six free shape parameters."""
    if joint:
        compact = _joint_input()
        geometry = CompactMeasurementGeometry(
            pixel_solid_angle_steradians=1.0,
            restoring_beam_solid_angle_steradians=6 * np.pi,
            restoring_beam_covariance_pixels_squared=(4.0, 0.0, 2.25),
        )
    else:
        compact = _gaussian_input(
            amplitude=0.5,
            sigma_axes=(1.6, 8 / (2 * np.pi * 1.6)),
            angle_degrees=20.0,
        )
        geometry = _beam_geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    fits = fit_compact_gaussian_mixture(
        compact,
        moments,
        geometry,
        _fit_config(
            background_model="fixed-zero", model_selection="beam-or-free"
        ),
    )
    for fitted in fits:
        assert isinstance(fitted, ValidCompactGaussianFit)
        assert fitted.diagnostics.model_identity == "beam-constrained"
        assert fitted.diagnostics.rejected_model_identity == "free-elliptical"
        assert fitted.uncertainty is not None
        assert fitted.uncertainty.integrated_flux_error_jy > 0


def test_joint_owned_region_gls_ignores_adequacy_context() -> None:
    """A large halo must not change the declared fit sample domain."""
    compact = _joint_input()
    geometry = replace(
        _geometry(),
        noise_correlation_covariance_pixels_squared=(1.0, 0.0, 1.0),
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    config = _fit_config(
        background_model="fixed-zero",
        pixel_support="owned-region",
        point_estimator="correlated-gls",
    )
    expected_pixels = int(np.count_nonzero(compact.region_labels))
    fits = fit_compact_gaussian_mixture(compact, moments, geometry, config)
    for fitted in fits:
        assert isinstance(fitted, ValidCompactGaussianFit)
        assert fitted.diagnostics.retained_pixel_count == expected_pixels
        assert fitted.diagnostics.point_estimator == "correlated-gls"
        assert fitted.diagnostics.point_estimator_fallback_reason is None
    changed = replace(
        compact,
        physical_residual=np.where(
            compact.region_labels > 0, compact.physical_residual, -1000.0
        ),
    )
    assert (
        fit_compact_gaussian_mixture(changed, moments, geometry, config)
        == fits
    )


@pytest.mark.parametrize("recover_mixed_information", (False, True))
def test_joint_mixed_model_selection_is_order_invariant(
    monkeypatch: pytest.MonkeyPatch, recover_mixed_information: bool
) -> None:
    """A resolved neighbour keeps its shape beside a beam-constrained row."""
    compact = _joint_input()
    yy, xx = np.mgrid[:25, :33]
    signal = 50 * np.exp(
        -0.5 * (((xx - 12) / 2) ** 2 + ((yy - 12) / 1.5) ** 2)
    )
    signal += 50 * np.exp(
        -0.5 * (((xx - 19) / 3.2) ** 2 + ((yy - 12) / 2.2) ** 2)
    )
    compact = replace(compact, physical_residual=signal)
    geometry = replace(
        _geometry(), restoring_beam_covariance_pixels_squared=(4.0, 0.0, 2.25)
    )
    config = _fit_config(
        background_model="fixed-zero", model_selection="beam-or-free"
    )
    if recover_mixed_information:
        original = fitting_algorithm._parameter_covariance
        mixed_calls = 0

        def unavailable_optimizer_information(
            jacobian: np.ndarray, *args: Any, **kwargs: Any
        ) -> np.ndarray | None:
            nonlocal mixed_calls
            if jacobian.shape[1] == 9:
                mixed_calls += 1
                if mixed_calls % 2 == 1:
                    return None
            return original(jacobian, *args, **kwargs)

        monkeypatch.setattr(
            fitting_algorithm,
            "_parameter_covariance",
            unavailable_optimizer_information,
        )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    fitted = fit_compact_gaussian_mixture(compact, moments, geometry, config)
    reversed_fits = fit_compact_gaussian_mixture(
        replace(compact, regions=compact.regions[::-1]),
        moments[::-1],
        geometry,
        config,
    )[::-1]
    for first, second, identity, axes in zip(
        fitted,
        reversed_fits,
        ("beam-constrained", "free-elliptical"),
        ((2.0, 1.5), (3.2, 2.2)),
        strict=True,
    ):
        assert isinstance(first, ValidCompactGaussianFit)
        assert isinstance(second, ValidCompactGaussianFit)
        assert (
            first.diagnostics.model_identity
            == second.diagnostics.model_identity
            == identity
        )
        assert first.diagnostics.degrees_of_freedom == signal.size - 9
        assert first.parameters.centroid_xy == pytest.approx(
            second.parameters.centroid_xy, abs=1e-6
        )
        assert (
            first.parameters.major_sigma_pixels,
            first.parameters.minor_sigma_pixels,
        ) == pytest.approx(axes, abs=1e-5)
        assert first.uncertainty is not None
        assert second.uncertainty is not None
        if recover_mixed_information:
            assert first.diagnostics.covariance_parameterization == (
                "cartesian-precision"
            )
        assert first.uncertainty.integrated_flux_error_jy == pytest.approx(
            second.uncertainty.integrated_flux_error_jy, rel=1e-5
        )


def test_failed_beam_alternative_keeps_a_valid_joint_free_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unsuccessful alternative cannot invalidate the valid free model."""
    compact = _joint_input()
    geometry = replace(
        _geometry(), restoring_beam_covariance_pixels_squared=(4.0, 0.0, 2.25)
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    original = fitting_algorithm.least_squares
    calls = 0

    def failed_alternative(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 2:
            result.success = False
        return result

    monkeypatch.setattr(fitting_algorithm, "least_squares", failed_alternative)
    results = fit_compact_gaussian_mixture(
        compact,
        moments,
        geometry,
        _fit_config(
            background_model="fixed-zero", model_selection="beam-or-free"
        ),
    )
    assert calls == 2
    assert all(
        isinstance(result, ValidCompactGaussianFit)
        and result.diagnostics.model_identity == "free-elliptical"
        for result in results
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "center", ((1.0, 1.0), (15.0, 1.0), (1.0, 13.0), (15.0, 13.0))
)
def test_joint_corner_covariance_matches_correlated_noise_ensemble(
    center: tuple[float, float],
) -> None:
    """Calibrate joint marginal errors on independent masked corner noise.

    The 99.9% chi-square variance interval is a numerical calibration guard,
    not the campaign's classification threshold or qualification confidence.
    No detection-selected pixels or campaign seeds enter this experiment.
    """
    compact = _gaussian_input(
        amplitude=3.0,
        centroid_xy=center,
        shape_yx=(15, 17),
        origin_yx=(0, 0),
        rms_value=0.12,
    )
    valid = compact.valid_pixels.copy()
    valid[::5, ::7] = False
    compact = replace(
        compact,
        valid_pixels=valid,
        region_labels=valid.astype(np.int32),
        regions=(replace(compact.regions[0], pixel_count=int(valid.sum())),),
        island=replace(compact.island, pixel_count=int(valid.sum())),
    )
    geometry = replace(
        _beam_geometry(),
        noise_correlation_covariance_pixels_squared=(1.0, 0.0, 1.0),
    )
    yy, xx = np.nonzero(valid)
    coordinates = np.column_stack((xx, yy))
    distances = coordinates[:, None, :] - coordinates[None, :, :]
    correlation = np.exp(-0.5 * np.sum(distances**2, axis=2))
    factor = np.linalg.cholesky(correlation)
    generator = np.random.default_rng(8_491_277)
    standardized = []
    # Fix a positive initialization independently of each noise draw. This
    # isolates covariance calibration from detection/truncation selection.
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    for _ in range(48):
        noisy = compact.physical_residual.copy()
        noisy[valid] += 0.12 * (factor @ generator.normal(size=len(xx)))
        observed = replace(compact, physical_residual=noisy)
        (fitted,) = fit_compact_gaussian_mixture(
            observed,
            moments,
            geometry,
            _fit_config(
                background_model="fixed-zero",
                pixel_support="owned-region",
                point_estimator="correlated-gls",
            ),
        )
        assert isinstance(fitted, ValidCompactGaussianFit)
        assert fitted.uncertainty is not None
        assert fitted.diagnostics.point_estimator == "correlated-gls"
        errors = fitted.uncertainty
        assert errors.shape_parameter_covariance is not None
        measured = np.array(
            (
                *fitted.parameters.centroid_xy,
                fitted.parameters.major_sigma_pixels,
                fitted.parameters.minor_sigma_pixels,
            )
        )
        variances = np.array(
            (
                errors.centroid_covariance_xx_pixels_squared,
                errors.centroid_covariance_yy_pixels_squared,
                errors.shape_parameter_covariance[0],
                errors.shape_parameter_covariance[3],
            )
        )
        standardized.append(
            (measured - (*center, 2.4, 1.3)) / np.sqrt(variances)
        )
    residuals = np.asarray(standardized)
    bounds = chi2.ppf((0.0005, 0.9995), 47) / 47
    variance = np.var(residuals, axis=0, ddof=1)
    assert np.all((variance >= bounds[0]) & (variance <= bounds[1])), variance
    assert np.all(np.abs(np.mean(residuals, axis=0)) < 0.6)


@pytest.mark.parametrize("axes", ((2.0, 2.0), (2.4, 1.3)))
def test_precision_shape_jacobian_matches_finite_differences(
    axes: tuple[float, float],
) -> None:
    """The circular-safe information basis differentiates the same model."""
    theta = 0.4
    rotation = np.array(
        ((np.cos(theta), -np.sin(theta)), (np.sin(theta), np.cos(theta)))
    )
    precision = rotation @ np.diag(1 / np.square(axes)) @ rotation.T
    parameters = np.array((10.0, 3.0, 4.0, *axes, theta, 0.0))
    cartesian = np.array(
        (10.0, 3.0, 4.0, precision[0, 0], precision[0, 1], precision[1, 1])
    )
    x, y = np.array((1.0, 2.0, 4.0, 7.0)), np.array((2.0, 3.0, 5.0, 6.0))

    def model(values: np.ndarray) -> np.ndarray:
        amplitude, cx, cy, qxx, qxy, qyy = values
        dx, dy = x - cx, y - cy
        return amplitude * np.exp(
            -0.5 * (qxx * dx**2 + 2 * qxy * dx * dy + qyy * dy**2)
        )

    jacobian = fitting_algorithm._precision_shape_jacobian(parameters, x, y)
    for column in range(6):
        step = np.eye(6)[column] * 1e-6
        np.testing.assert_allclose(
            jacobian[:, column],
            (model(cartesian + step) - model(cartesian - step)) / 2e-6,
            rtol=1e-6,
            atol=1e-8,
        )


@pytest.mark.parametrize("turn", (-360.0, -180.0, 180.0, 360.0))
def test_joint_initial_orientation_is_periodic(turn: float) -> None:
    """An eigenvector sign or full turn cannot create an optimizer wall."""
    compact = _gaussian_input(sigma_axes=(2.4, 1.3), angle_degrees=157.0)
    geometry = _geometry()
    moment = measure_compact_moments(compact, geometry, _moment_config())[1]
    assert isinstance(moment, ValidMomentMeasurement)
    shifted = replace(
        moment,
        initializer=replace(
            moment.initializer,
            major_axis_angle_degrees=moment.initializer.major_axis_angle_degrees
            + turn,
        ),
    )
    fitted = fit_compact_gaussian_mixture(
        compact,
        (shifted,),
        geometry,
        _fit_config(background_model="fixed-zero"),
    )[0]
    assert isinstance(fitted, ValidCompactGaussianFit)
    assert fitted.parameters.major_axis_angle_degrees % 180 == pytest.approx(
        157.0, abs=1e-5
    )
    assert fitted.parameters.major_sigma_pixels == pytest.approx(2.4, rel=1e-5)
    assert fitted.parameters.minor_sigma_pixels == pytest.approx(1.3, rel=1e-5)
    assert "position-angle" not in fitted.diagnostics.bound_parameters


def test_joint_gaussian_jacobian_matches_independent_finite_difference() -> (
    None
):
    """Each neighbour contributes its own six exact model derivatives."""
    params = np.array(
        (10, 1, 2, 2, 1.5, 0.3, 7, 4, 2, 2.3, 1.8, -0.2), dtype=float
    )
    x, y = (
        np.array((0, 1, 3, 4), dtype=float),
        np.array((2, 0, 1, 3), dtype=float),
    )
    actual = fitting_algorithm._mixture_jacobian(params, x, y)
    for index in range(params.size):
        step = np.zeros_like(params)
        step[index] = 1e-6
        derivative = (
            fitting_algorithm._mixture_model(params + step, x, y)
            - fitting_algorithm._mixture_model(params - step, x, y)
        ) / 2e-6
        np.testing.assert_allclose(
            actual[:, index], derivative, atol=1e-8, rtol=1e-6
        )


@pytest.mark.parametrize(
    "limits", ({"maximum_parameters": 6}, {"maximum_jacobian_elements": 100})
)
def test_joint_fit_admits_work_before_allocating_optimizer(
    limits: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large parent fits have an explicit unavailable result, not an OOM."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("optimizer must not start for unadmitted work")

    monkeypatch.setattr(fitting_algorithm, "least_squares", forbidden)
    fits = fit_compact_gaussian_mixture(
        compact,
        moments,
        geometry,
        _fit_config(background_model="fixed-zero"),
        **limits,
    )
    assert all(
        isinstance(fitted, UnavailableCompactGaussianFit)
        and fitted.reason == "joint-fit-work-limit"
        for fitted in fits
    )


def test_joint_iteration_limit_preserves_typed_failure() -> None:
    """A partial joint solve cannot publish apparent converged components."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    fits = fit_compact_gaussian_mixture(
        compact,
        moments,
        geometry,
        _fit_config(
            background_model="fixed-zero", maximum_function_evaluations=1
        ),
    )
    assert all(
        isinstance(fitted, FailedCompactGaussianFit)
        and fitted.reason == "fit-non-convergence"
        for fitted in fits
    )


@pytest.mark.parametrize(
    "failure_site",
    ("least_squares", "_parameter_covariance", "_publish_mixture_component"),
)
def test_joint_linear_algebra_failure_preserves_every_component(
    failure_site: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted numerical solve has no invented fit diagnostics."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise np.linalg.LinAlgError("SVD did not converge for slice = 0.")

    monkeypatch.setattr(fitting_algorithm, failure_site, fail)
    fitted = fit_compact_gaussian_mixture(
        compact,
        tuple(reversed(moments)),
        geometry,
        _fit_config(background_model="fixed-zero"),
    )
    assert len(fitted) == len(moments)
    for result, moment in zip(fitted, moments, strict=True):
        assert isinstance(result, FailedCompactGaussianFit)
        assert result.moment is moment
        assert result.reason == "fit-linear-algebra-failure"
        assert result.diagnostics is None
        assert "joint-gaussian-fit" in result.quality_flags
        assert "fit-failed" in result.quality_flags


@pytest.mark.parametrize("exception", (ValueError, TypeError, RuntimeError))
def test_joint_solver_does_not_hide_programming_errors(
    exception: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only numerical linear-algebra failure is an expected fit outcome."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise exception("unexpected implementation error")

    monkeypatch.setattr(fitting_algorithm, "least_squares", fail)
    with pytest.raises(exception, match="unexpected implementation error"):
        fit_compact_gaussian_mixture(
            compact,
            moments,
            geometry,
            _fit_config(background_model="fixed-zero"),
        )


def test_joint_fit_does_not_ignore_an_unmeasurable_neighbour() -> None:
    """Dropping an unfitted neighbour would bias every surviving model."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    missing = UnavailableMomentMeasurement(
        moments[1].target, "non-positive-measurement"
    )
    fitted = fit_compact_gaussian_mixture(
        compact,
        (moments[0], missing),
        geometry,
        _fit_config(background_model="fixed-zero"),
    )
    assert isinstance(fitted[0], UnavailableCompactGaussianFit)
    assert fitted[0].reason == "joint-peer-unavailable"
    assert isinstance(fitted[1], UnavailableCompactGaussianFit)
    assert fitted[1].reason == "non-positive-measurement"


def test_joint_empty_and_invalid_invocations_fail_before_fitting() -> None:
    """Joint work requires an exact component census and fixed background."""
    compact = _joint_input()
    geometry = _geometry()
    config = _fit_config(background_model="fixed-zero")
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    assert (
        fit_compact_gaussian_mixture(
            replace(compact, regions=()), (), geometry, config
        )
        == ()
    )
    for wrong in (moments[:1], (moments[0], moments[0])):
        with pytest.raises(ValueError, match="exactly once"):
            fit_compact_gaussian_mixture(compact, wrong, geometry, config)
    for limits in (
        {"maximum_parameters": 5},
        {"maximum_jacobian_elements": 0},
        {"maximum_parameters": float("nan")},
        {"maximum_jacobian_elements": float("inf")},
        {"maximum_parameters": 96.5},
        {"maximum_jacobian_elements": True},
    ):
        with pytest.raises(ValueError, match="work limits"):
            fit_compact_gaussian_mixture(
                compact,
                moments,
                geometry,
                config,
                **limits,  # pyright: ignore[reportArgumentType]
            )
    with pytest.raises(ValueError, match="fixed-zero"):
        fit_compact_gaussian_mixture(
            compact,
            moments,
            geometry,
            replace(config, background_model="fitted-offset"),
        )


def test_joint_context_requires_more_pixels_than_parameters() -> None:
    """Loss of valid fit samples cannot produce an underdetermined model."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    valid = np.zeros_like(compact.valid_pixels)
    valid.ravel()[:12] = True
    fitted = fit_compact_gaussian_mixture(
        replace(compact, valid_pixels=valid),
        moments,
        geometry,
        _fit_config(background_model="fixed-zero"),
    )
    assert all(
        isinstance(item, UnavailableCompactGaussianFit)
        and item.reason == "underdetermined-region"
        for item in fitted
    )


@pytest.mark.parametrize("seed", (11, 29, 47))
def test_joint_measurements_with_varying_noise_invalids_and_signed_context(
    seed: int,
) -> None:
    """Original-pixel noise is not rectified or hidden by positive support."""
    compact = _joint_input()
    geometry = _geometry()
    _yy, xx = np.indices(compact.physical_residual.shape)
    rms = np.asarray(0.25 + 0.005 * xx, dtype=np.float64)
    signal = compact.physical_residual + rms * np.random.default_rng(
        seed
    ).standard_normal(rms.shape)
    valid = np.ones_like(signal, dtype=np.bool_)
    valid[2:4, 5:7] = False
    signal[~valid] = np.nan
    compact = replace(
        compact, physical_residual=signal, rms=rms, valid_pixels=valid
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    fitted = fit_compact_gaussian_mixture(
        compact,
        tuple(reversed(moments)),
        geometry,
        _fit_config(background_model="fixed-zero"),
    )
    assert np.any(signal[valid] < 0)
    for result, amplitude, center in zip(
        fitted, (10.0, 7.0), (12.0, 19.0), strict=True
    ):
        assert isinstance(result, ValidCompactGaussianFit)
        assert result.uncertainty is not None
        expected_flux = amplitude * 2 * np.pi * 3 / 8
        assert abs(result.parameters.integrated_flux_jy - expected_flux) <= (
            3 * result.uncertainty.integrated_flux_error_jy
        )
        np.testing.assert_allclose(
            result.parameters.centroid_xy, (center, 12.0), atol=0.5, rtol=0
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


def test_fit_centroid_cannot_leave_the_sampled_image_footprint() -> None:
    """A truncated external profile records the specific boundary ridge."""
    compact = _gaussian_input(
        centroid_xy=(160.0, 256.5),
        shape_yx=(8, 21),
        origin_yx=(248, 150),
    )

    result = _fit(compact)

    assert isinstance(result, FailedCompactGaussianFit)
    assert result.reason == "fit-invalid-result"
    assert result.diagnostics is not None
    assert result.moment is not None
    assert result.diagnostics.parameters_at_bound
    assert result.diagnostics.model_identity == "free-elliptical"
    assert "centroid-y" in result.diagnostics.bound_parameters
    assert result.diagnostics.minimum_relative_bound_distance == pytest.approx(
        0.0, abs=1e-8
    )
    bound_distances = dict(result.diagnostics.relative_bound_distances)
    assert set(bound_distances) == {
        "amplitude",
        "background",
        "centroid-x",
        "centroid-y",
        "position-angle",
        "sigma-first",
        "sigma-second",
    }
    assert bound_distances["centroid-y"] == pytest.approx(0.0, abs=1e-8)
    assert result.diagnostics.information_condition_number is not None
    assert np.isfinite(result.diagnostics.information_condition_number)
    assert result.diagnostics.visible_model_fraction is not None
    assert 0.0 < result.diagnostics.visible_model_fraction < 1.0
    assert result.diagnostics.retained_pixel_count == (
        compact.physical_residual.size
    )
    assert result.diagnostics.retained_bounds_yx == (248, 256, 150, 171)


@pytest.mark.parametrize(
    "centroid_xy",
    (
        (0.75, 8.0),
        (17.25, 8.0),
        (8.0, 0.75),
        (8.0, 15.25),
        (0.75, 0.75),
        (17.25, 0.75),
        (0.75, 15.25),
        (17.25, 15.25),
    ),
)
def test_beam_shaped_edge_and_corner_sources_use_constrained_fit(
    centroid_xy: tuple[float, float],
) -> None:
    """Low-information truncation cannot create a free-shape edge ridge."""
    geometry = _beam_geometry()
    covariance = geometry.restoring_beam_covariance_pixels_squared
    assert covariance is not None
    matrix = np.asarray(
        [[covariance[0], covariance[1]], [covariance[1], covariance[2]]]
    )
    eigenvalues = np.linalg.eigvalsh(matrix)
    axes = tuple(np.sqrt(eigenvalues[::-1]))
    compact = _gaussian_input(
        amplitude=0.5,
        centroid_xy=centroid_xy,
        sigma_axes=axes,
        angle_degrees=20.0,
        shape_yx=(17, 19),
        origin_yx=(0, 0),
    )

    result = _fit(
        compact,
        config=_fit_config(model_selection="beam-or-free"),
        geometry=geometry,
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "beam-constrained"
    assert result.diagnostics.fallback_reason == (
        "free-model-not-significantly-extended"
    )
    assert result.parameters.centroid_xy == pytest.approx(
        centroid_xy, abs=1e-6
    )
    assert result.parameters.major_sigma_pixels == pytest.approx(axes[0])
    assert result.parameters.minor_sigma_pixels == pytest.approx(axes[1])
    assert not result.diagnostics.parameters_at_bound
    assert "beam-constrained-fit" in result.quality_flags
    assert result.gaussian_component_fit is None
    assert isinstance(
        result.association_aperture,
        AssociationAperturePhotometry,
    )
    assert result.association_aperture.radius_sigma == 3.0
    assert result.association_aperture.integrated_flux_jy == pytest.approx(
        0.5,
        rel=1e-6,
    )
    assert 0.0 < result.association_aperture.visible_model_fraction <= 1.0


def test_component_uses_lower_significance_whole_ellipse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Marginal component evidence retains every parameter from one fit."""
    observed_thresholds: list[float] = []

    def significant_at_component_threshold(
        candidate: object,
        beam_covariance: object,
        *,
        significance_sigma: float,
    ) -> bool:
        del candidate, beam_covariance
        observed_thresholds.append(significance_sigma)
        return significance_sigma <= 2.0

    monkeypatch.setattr(
        fitting_algorithm,
        "_significantly_extended",
        significant_at_component_threshold,
    )

    def never_preferred(*_args: object) -> bool:
        return False

    monkeypatch.setattr(
        fitting_algorithm,
        "_free_preferred_by_bic",
        never_preferred,
    )
    result = _fit(
        _gaussian_input(sigma_axes=(1.7, 0.8)),
        config=_fit_config(
            model_selection="beam-or-free",
            extension_significance_sigma=5.0,
            component_extension_significance_sigma=2.0,
        ),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "beam-constrained"
    assert result.gaussian_component_fit is not None
    assert result.gaussian_component_fit.diagnostics.model_identity == (
        "free-elliptical"
    )
    assert observed_thresholds == [5.0, 2.0]


def test_integrated_flux_bias_calibration_is_component_specific() -> None:
    """Calibration records a fitted-total correction without changing fit."""
    compact = _gaussian_input(amplitude=5.0, sigma_axes=(3.8, 2.4))
    baseline = _fit(
        compact,
        config=_fit_config(integrated_flux_bias_correction_sigma=0.0),
        geometry=_beam_geometry(),
    )
    calibrated = _fit(
        compact,
        config=_fit_config(integrated_flux_bias_correction_sigma=0.075),
        geometry=_beam_geometry(),
    )

    assert isinstance(baseline, ValidCompactGaussianFit)
    assert isinstance(calibrated, ValidCompactGaussianFit)
    assert baseline.parameters == calibrated.parameters
    assert baseline.uncertainty is not None
    assert calibrated.uncertainty is not None
    assert calibrated.uncertainty.integrated_flux_error_jy == pytest.approx(
        baseline.uncertainty.integrated_flux_error_jy
    )
    assert baseline.uncertainty.integrated_flux_bias_correction_sigma == 0.0
    assert calibrated.uncertainty.integrated_flux_bias_correction_sigma == (
        pytest.approx(0.075)
    )
    assert (
        calibrated.uncertainty.amplitude_error_jy_per_beam
        == baseline.uncertainty.amplitude_error_jy_per_beam
    )
    assert (
        calibrated.uncertainty.shape_parameter_covariance
        == baseline.uncertainty.shape_parameter_covariance
    )


def test_clear_extended_source_retains_free_elliptical_fit() -> None:
    """A high-information extension remains free rather than beam-forced."""
    compact = _gaussian_input(amplitude=5.0, sigma_axes=(3.8, 2.4))

    result = _fit(
        compact,
        config=_fit_config(model_selection="beam-or-free"),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"
    assert result.diagnostics.fallback_reason is None
    assert result.parameters.major_sigma_pixels == pytest.approx(3.8)
    assert result.parameters.minor_sigma_pixels == pytest.approx(2.4)


@pytest.mark.parametrize(
    ("pair_angle_degrees", "aperture_model"),
    (
        (20.0, "restoring-beam"),
        (65.0, "selected-fit"),
        (110.0, "selected-fit"),
    ),
)
def test_association_aperture_recovers_rotated_blend_total_flux(
    pair_angle_degrees: float,
    aperture_model: str,
) -> None:
    """Association flux follows the observed blend, not a fixed beam mask."""
    geometry = _beam_geometry()
    beam_covariance = geometry.restoring_beam_covariance_pixels_squared
    assert beam_covariance is not None
    covariance = np.asarray(
        [
            [beam_covariance[0], beam_covariance[1]],
            [beam_covariance[1], beam_covariance[2]],
        ]
    )
    beam_axes = tuple(np.sqrt(np.linalg.eigvalsh(covariance)[::-1]))
    center_xy = (20.0, 20.0)
    separation_pixels = 2.5
    angle = np.deg2rad(pair_angle_degrees)
    offset_xy = (
        0.5 * separation_pixels * np.cos(angle),
        0.5 * separation_pixels * np.sin(angle),
    )
    shared = {
        "sigma_axes": beam_axes,
        "angle_degrees": 20.0,
        "shape_yx": (41, 41),
        "origin_yx": (0, 0),
        "rms_value": 0.01,
    }
    first = _gaussian_input(
        amplitude=1.0,
        centroid_xy=(
            center_xy[0] - offset_xy[0],
            center_xy[1] - offset_xy[1],
        ),
        **shared,  # type: ignore[arg-type]
    )
    second = _gaussian_input(
        amplitude=0.8,
        centroid_xy=(
            center_xy[0] + offset_xy[0],
            center_xy[1] + offset_xy[1],
        ),
        **shared,  # type: ignore[arg-type]
    )
    blend = replace(
        first,
        physical_residual=first.physical_residual + second.physical_residual,
    )

    result = _fit(
        blend,
        config=_fit_config(
            background_model="fixed-zero",
            pixel_support="owned-region",
            model_selection="beam-or-free",
        ),
        geometry=geometry,
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"
    assert result.association_aperture is not None
    assert result.association_aperture.aperture_model == aperture_model
    assert result.association_aperture.integrated_flux_jy == pytest.approx(
        1.8,
        rel=0.02,
    )


def test_association_aperture_omits_unusable_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty or non-positive aperture support remains explicit absence."""
    original = fitting_algorithm._association_aperture_photometry
    omitted: list[AssociationAperturePhotometry | None] = []

    def probe(
        compact: _FitInput,
        region: DeblendedRegion,
        candidate: fitting_algorithm._FitCandidate,
        geometry: CompactMeasurementGeometry,
        config: CompactGaussianFitConfig,
    ) -> AssociationAperturePhotometry | None:
        omitted.append(
            original(
                replace(
                    compact,
                    valid_pixels=np.zeros_like(compact.valid_pixels),
                ),
                region,
                candidate,
                geometry,
                config,
            )
        )
        omitted.append(
            original(
                replace(
                    compact,
                    physical_residual=-np.abs(compact.physical_residual),
                ),
                region,
                candidate,
                geometry,
                config,
            )
        )
        return original(
            compact,
            region,
            candidate,
            geometry,
            config,
        )

    monkeypatch.setattr(
        fitting_algorithm,
        "_association_aperture_photometry",
        probe,
    )

    result = _fit(_gaussian_input(), geometry=_beam_geometry())

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.association_aperture is not None
    assert omitted == [None, None]


def test_valid_free_fit_survives_failed_smaller_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed alternative cannot turn a valid measurement into omission."""
    geometry = _beam_geometry()
    covariance = geometry.restoring_beam_covariance_pixels_squared
    assert covariance is not None
    matrix = np.asarray(
        [[covariance[0], covariance[1]], [covariance[1], covariance[2]]]
    )
    axes = tuple(np.sqrt(np.linalg.eigvalsh(matrix)[::-1]))
    compact = _gaussian_input(
        amplitude=0.5,
        sigma_axes=axes,
        angle_degrees=20.0,
    )
    original = fitting_algorithm._fit_candidate
    calls = 0

    def fail_smaller_model(*args: object, **kwargs: object):
        nonlocal calls
        candidate = original(*args, **kwargs)  # type: ignore[arg-type]
        calls += 1
        if calls == 2:
            return replace(
                candidate,
                success=False,
                diagnostics=replace(candidate.diagnostics, converged=False),
            )
        return candidate

    monkeypatch.setattr(
        fitting_algorithm,
        "_fit_candidate",
        fail_smaller_model,
    )

    result = _fit(
        compact,
        config=_fit_config(model_selection="beam-or-free"),
        geometry=geometry,
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"
    assert result.diagnostics.rejected_model_identity == "beam-constrained"


def test_fixed_background_is_an_explicit_smaller_model() -> None:
    """Residual maps may omit a redundant fitted local offset parameter."""
    compact = _gaussian_input(amplitude=5.0, sigma_axes=(3.8, 2.4))

    result = _fit(
        compact,
        config=_fit_config(
            background_model="fixed-zero",
            model_selection="beam-or-free",
        ),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"
    assert "background" not in dict(
        result.diagnostics.relative_bound_distances
    )
    assert result.diagnostics.degrees_of_freedom == (
        compact.physical_residual.size - 6
    )


def test_bound_contact_is_not_published_as_an_ordinary_free_fit() -> None:
    """A physical-bound ridge must fall back or fail explicitly."""
    compact = _gaussian_input(
        centroid_xy=(160.0, 256.5),
        shape_yx=(8, 21),
        origin_yx=(248, 150),
    )

    result = _fit(
        compact,
        config=_fit_config(model_selection="beam-or-free"),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == (
        "centroid-constrained-elliptical"
    )
    assert result.diagnostics.fallback_reason == "free-model-bound-contact"
    assert result.diagnostics.rejected_model_identity == "free-elliptical"
    assert "centroid-y" in result.diagnostics.rejected_model_bound_parameters
    assert "centroid-constrained-fit" in result.quality_flags
    assert "fit-at-bound" not in result.quality_flags


@pytest.mark.parametrize("joint", (False, True))
@pytest.mark.parametrize("center_y", (8.0, 10.0, 15.0))
@pytest.mark.parametrize("model_selection", ("free-only", "beam-or-free"))
def test_free_only_does_not_bypass_physical_fit_admission(
    joint: bool, center_y: float, model_selection: str
) -> None:
    """Converged off-image ridges fail the same gate without a beam model."""
    compact = _gaussian_input(
        amplitude=100,
        centroid_xy=(10, center_y),
        shape_yx=(8, 21),
        origin_yx=(0, 0),
        rms_value=1,
    )
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    config = _fit_config(
        background_model="fixed-zero", model_selection=model_selection
    )
    result = (
        fit_compact_gaussian_mixture(compact, moments, geometry, config)[0]
        if joint
        else fit_compact_gaussian(
            compact, compact.regions[0], moments[0], geometry, config
        )
    )
    assert isinstance(result, FailedCompactGaussianFit)
    assert result.reason == "fit-invalid-result"
    assert result.moment == moments[0]
    assert result.diagnostics is not None
    assert result.diagnostics.converged
    condition = result.diagnostics.information_condition_number
    assert condition is not None
    assert (
        "centroid-y" in result.diagnostics.bound_parameters
        or condition > config.maximum_information_condition_number
    )


def test_centroid_retry_survives_edge_bound_contact_in_both_models() -> None:
    """A noisy image edge cannot prevent the existing stable-centroid retry."""
    compact = _gaussian_input(
        amplitude=0.1,
        centroid_xy=(254.0, 252.0),
        sigma_axes=(3.8, 2.4),
        angle_degrees=20.0,
        shape_yx=(12, 12),
        origin_yx=(244, 244),
        rms_value=0.05,
    )
    residual = compact.physical_residual.copy()
    residual[8:11, -1] += 0.05
    geometry = _beam_geometry()
    geometry = replace(
        geometry,
        noise_correlation_covariance_pixels_squared=(
            geometry.restoring_beam_covariance_pixels_squared
        ),
    )

    result = _fit(
        replace(compact, physical_residual=residual),
        config=_fit_config(
            model_selection="beam-or-free",
            point_estimator="correlated-gls",
        ),
        geometry=geometry,
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == (
        "centroid-constrained-elliptical"
    )
    assert result.diagnostics.fallback_reason == "free-model-bound-contact"
    assert result.diagnostics.rejected_model_identity == "free-elliptical"
    assert set(result.diagnostics.bound_parameters) == {
        "forced-centroid-x",
        "forced-centroid-y",
    }
    assert result.diagnostics.point_estimator == "correlated-gls"
    assert "centroid-constrained-fit" in result.quality_flags
    assert "fit-at-bound" not in result.quality_flags
    assert abs(result.parameters.centroid_xy[0] - 254.0) < (
        abs(result.moment.initializer.centroid_xy[0] - 254.0) - 0.1
    )


def test_default_model_selection_preserves_the_free_fit_oracle() -> None:
    """Ordinary callers retain the established free-elliptical estimator."""
    assert _fit_config().model_selection == "free-only"
    result = _fit(
        _gaussian_input(amplitude=0.5, sigma_axes=(1.9, 1.2)),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"
    assert result.position_estimate is None


def test_bounded_context_position_is_separate_from_owned_morphology() -> None:
    """The explicit campaign policy publishes an independent centroid."""
    result = _fit(
        _gaussian_input(amplitude=0.5, sigma_axes=(1.9, 1.2)),
        config=_fit_config(position_estimator="bounded-context-free"),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.position_estimate is not None
    assert result.position_estimate.estimator == "bounded-context-free"
    assert "bounded-context-position" in result.quality_flags
    assert "beam-constrained-fit" not in result.quality_flags


@pytest.mark.parametrize(
    ("centroid_xy", "origin_yx", "edge_column"),
    (
        ((254.0, 252.0), (244, 244), -1),
        ((1.0, 252.0), (244, 0), 0),
    ),
)
@pytest.mark.parametrize("model_selection", ("free-only", "beam-or-free"))
def test_truncated_context_position_refits_centroid_and_covariance(
    centroid_xy: tuple[float, float],
    origin_yx: tuple[int, int],
    edge_column: int,
    model_selection: str,
) -> None:
    """An edge correction publishes covariance from its own likelihood fit."""
    compact = _gaussian_input(
        amplitude=0.1,
        centroid_xy=centroid_xy,
        sigma_axes=(3.8, 2.4),
        angle_degrees=20.0,
        shape_yx=(12, 12),
        origin_yx=origin_yx,
        rms_value=0.05,
    )
    residual = compact.physical_residual.copy()
    residual[8:11, edge_column] += 0.05

    result = _fit(
        replace(compact, physical_residual=residual),
        config=_fit_config(
            position_estimator="bounded-context-free",
            model_selection=model_selection,
        ),
        geometry=_beam_geometry(),
    )

    if model_selection == "free-only":
        # A separately recovered position cannot make a bound-pinned whole
        # Gaussian valid. The beam-selected path below retains its existing
        # independently fitted truncation covariance.
        assert isinstance(result, FailedCompactGaussianFit)
        assert result.reason == "fit-invalid-result"
        assert result.diagnostics is not None
        assert result.diagnostics.parameters_at_bound
        return
    assert isinstance(result, ValidCompactGaussianFit)
    assert result.position_estimate is not None
    assert result.position_estimate.estimator == (
        "bounded-context-truncation-refit"
    )
    covariance = np.asarray(
        (
            (
                result.position_estimate.covariance_xx_pixels_squared,
                result.position_estimate.covariance_xy_pixels_squared,
            ),
            (
                result.position_estimate.covariance_xy_pixels_squared,
                result.position_estimate.covariance_yy_pixels_squared,
            ),
        )
    )
    assert np.all(np.linalg.eigvalsh(covariance) > 0)


def test_truncated_normal_moments_recover_edge_centroid() -> None:
    """The analytic fallback inverts a known one-sided normal truncation."""
    location = 254.0
    sigma = 2.5
    upper = 255.5
    standardized = (upper - location) / sigma
    density = np.exp(-0.5 * standardized**2) / np.sqrt(2.0 * np.pi)
    ratio = density / ndtr(standardized)
    observed_mean = location - sigma * ratio
    observed_variance = sigma**2 * (1.0 - standardized * ratio - ratio**2)

    recovered = fitting_algorithm._upper_truncated_normal_location(
        observed_mean,
        observed_variance,
        upper,
        30.0,
    )

    assert recovered == pytest.approx(location, abs=1e-6)


@pytest.mark.parametrize(
    ("observed_mean", "observed_variance"),
    ((1.0, 0.0), (2.0, 1.0)),
)
def test_truncated_normal_moments_reject_invalid_observations(
    observed_mean: float,
    observed_variance: float,
) -> None:
    """Moment inversion fails closed for degenerate or out-of-bound input."""
    assert (
        fitting_algorithm._upper_truncated_normal_location(
            observed_mean,
            observed_variance,
            1.5,
            30.0,
        )
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"centroid_xy": (float("nan"), 1.0)},
        {"covariance_xx_pixels_squared": 0.0},
        {"covariance_xy_pixels_squared": 2.0},
    ],
)
def test_position_estimate_rejects_invalid_evidence(
    changes: dict[str, object],
) -> None:
    """Position-only evidence requires finite positive covariance."""
    values: dict[str, object] = {
        "centroid_xy": (1.0, 2.0),
        "covariance_xx_pixels_squared": 1.0,
        "covariance_xy_pixels_squared": 0.0,
        "covariance_yy_pixels_squared": 1.0,
    }
    values.update(changes)

    with pytest.raises(ValueError, match="position estimate"):
        GaussianPositionEstimate(**values)  # type: ignore[arg-type]


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
    assert independent.uncertainty.shape_parameter_covariance is not None
    assert correlated.uncertainty.shape_parameter_covariance is not None
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


def test_correlated_gls_changes_point_estimate_and_formal_error_policy() -> (
    None
):
    """Small-region GLS whitens both residuals and the fitted Jacobian."""
    compact = _gaussian_input()
    y, x = np.indices(compact.physical_residual.shape, dtype=np.float64)
    noisy = replace(
        compact,
        physical_residual=(
            compact.physical_residual
            + 0.005 * (1.0 + np.sin(0.25 * x + 0.4 * y))
        ),
    )
    geometry = CompactMeasurementGeometry(
        pixel_solid_angle_steradians=1.0,
        restoring_beam_solid_angle_steradians=8.0,
        noise_correlation_covariance_pixels_squared=(4.0, 0.5, 2.0),
    )

    diagonal = _fit(noisy, geometry=geometry)
    generalized = _fit(
        noisy,
        config=_fit_config(point_estimator="correlated-gls"),
        geometry=geometry,
    )

    assert isinstance(diagonal, ValidCompactGaussianFit)
    assert isinstance(generalized, ValidCompactGaussianFit)
    assert generalized.parameters.centroid_xy != pytest.approx(
        diagonal.parameters.centroid_xy,
        abs=1e-8,
    )
    assert generalized.diagnostics.point_estimator == "correlated-gls"
    assert "correlated-noise-gls-errors" in generalized.quality_flags
    assert "correlated-noise-sandwich-errors" not in generalized.quality_flags


def test_correlated_gls_falls_back_before_dense_work_exceeds_bound() -> None:
    """Large retained regions keep an explicit bounded diagonal fallback."""
    geometry = CompactMeasurementGeometry(
        pixel_solid_angle_steradians=1.0,
        restoring_beam_solid_angle_steradians=8.0,
        noise_correlation_covariance_pixels_squared=(4.0, 0.0, 2.0),
    )

    result = _fit(
        _gaussian_input(),
        config=_fit_config(
            point_estimator="correlated-gls",
            maximum_gls_pixels=100,
        ),
        geometry=geometry,
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.point_estimator == "diagonal-weighted"
    assert result.diagnostics.point_estimator_fallback_reason == (
        "retained-region-exceeds-gls-limit"
    )
    assert "correlated-gls-fallback" in result.quality_flags


@pytest.mark.parametrize("joint", (False, True))
@pytest.mark.parametrize("sigma", (2.0, 4.0))
@pytest.mark.parametrize("perturbation", ("none", "mixed-noise", "envelope"))
def test_oversampled_likelihood_uses_explicit_stable_fallback(
    joint: bool, sigma: float, perturbation: str
) -> None:
    """Roundoff-singular noise cannot be silently turned into exact GLS.

    Independent subpixel truth, not a cropped public image: the weak ripple
    has power absent from the declared smooth covariance; the envelope is
    a one-percent, slightly asymmetric departure from a single Gaussian.
    Fix a positive initialization from truth to isolate likelihood stability
    from noise-dependent moment availability and detection selection.
    """
    compact = _gaussian_input(
        amplitude=100.0,
        centroid_xy=(10.3, 9.7),
        sigma_axes=(1.1 * sigma, sigma),
        shape_yx=(21, 21),
        origin_yx=(0, 0),
        rms_value=1.0,
    )
    geometry = replace(
        _geometry(),
        noise_correlation_covariance_pixels_squared=(sigma**2, 0, sigma**2),
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    y, x = np.indices(compact.physical_residual.shape, dtype=float)
    if perturbation == "mixed-noise":
        offset = 0.05 * (np.sin(2 * x + 0.3 * y) + np.cos(1.3 * y))
    elif perturbation == "envelope":
        offset = np.exp(-((x - 12) ** 2 + (y - 9) ** 2) / 60)
    else:
        offset = np.zeros_like(x)
    observed = replace(
        compact, physical_residual=compact.physical_residual + offset
    )
    config = _fit_config(
        background_model="fixed-zero", pixel_support="owned-region"
    )

    def fit(
        point_estimator: Literal["diagonal-weighted", "correlated-gls"],
    ) -> CompactGaussianFitResult:
        selected = replace(config, point_estimator=point_estimator)
        if joint:
            return fit_compact_gaussian_mixture(
                observed, moments, geometry, selected
            )[0]
        return fit_compact_gaussian(
            observed, observed.regions[0], moments[0], geometry, selected
        )

    expected = fit("diagonal-weighted")
    actual = fit("correlated-gls")

    assert isinstance(expected, ValidCompactGaussianFit)
    assert isinstance(actual, ValidCompactGaussianFit)
    assert actual.diagnostics.point_estimator == "diagonal-weighted"
    assert actual.diagnostics.point_estimator_fallback_reason in {
        "correlation-factorization-failed",
        "correlation-ill-conditioned",
    }
    assert "correlated-gls-fallback" in actual.quality_flags
    assert "correlated-noise-sandwich-errors" in actual.quality_flags
    assert "correlated-noise-gls-errors" not in actual.quality_flags
    assert actual.parameters == expected.parameters
    assert actual.uncertainty == expected.uncertainty
    assert actual.uncertainty is not None
    # The source is bright and the added mismatch is at most one RMS. These
    # are broad fixture sanity bounds, not catalogue acceptance thresholds.
    np.testing.assert_allclose(
        actual.parameters.centroid_xy, (10.3, 9.7), atol=0.1
    )
    assert actual.parameters.amplitude_jy_per_beam == pytest.approx(
        100, rel=0.02
    )
    assert actual.parameters.major_sigma_pixels == pytest.approx(
        1.1 * sigma, rel=0.02
    )
    assert actual.parameters.minor_sigma_pixels == pytest.approx(
        sigma, rel=0.02
    )


def test_singular_correlation_is_not_replaced_by_unreviewed_white_noise() -> (
    None
):
    """An unfactorizable declared covariance has an explicit fallback."""
    transform, estimator, reason = (
        fitting_algorithm._point_estimator_transform(
            np.zeros(2),
            np.zeros(2),
            replace(
                _geometry(),
                noise_correlation_covariance_pixels_squared=(1.0, 0.0, 1.0),
            ),
            _fit_config(point_estimator="correlated-gls"),
        )
    )

    assert estimator == "diagonal-weighted"
    assert reason == "correlation-factorization-failed"
    residual = np.asarray((1.0, -1.0))
    np.testing.assert_array_equal(transform(residual), residual)


@pytest.mark.parametrize(
    ("reciprocal_factor", "info", "expected_reason"),
    (
        (0.0, 0, "correlation-ill-conditioned"),
        (1.0, 0, "correlation-ill-conditioned"),
        (2.0, 0, None),
        (float("nan"), 0, "correlation-conditioning-failed"),
        (float("inf"), 0, "correlation-conditioning-failed"),
        (2.0, -1, "correlation-conditioning-failed"),
    ),
)
def test_gls_numerical_resolution_boundary_and_estimation_failure(
    monkeypatch: pytest.MonkeyPatch,
    reciprocal_factor: float,
    info: int,
    expected_reason: str | None,
) -> None:
    """Fail closed at dimension-scaled roundoff, or if estimation fails."""
    tolerance = 2 * np.finfo(np.float64).eps

    def estimate(
        _factor: np.ndarray, _norm: float, **_kwargs: object
    ) -> tuple[float, int]:
        return reciprocal_factor * tolerance, info

    monkeypatch.setattr(fitting_algorithm, "dpocon", estimate)
    transform, estimator, reason = (
        fitting_algorithm._point_estimator_transform(
            np.asarray((0.0, 1.0)),
            np.zeros(2),
            replace(
                _geometry(),
                noise_correlation_covariance_pixels_squared=(1.0, 0.0, 1.0),
            ),
            _fit_config(point_estimator="correlated-gls"),
        )
    )
    assert reason == expected_reason
    assert estimator == (
        "correlated-gls" if reason is None else "diagonal-weighted"
    )
    residual = np.eye(2)
    if reason is not None:
        np.testing.assert_array_equal(transform(residual), residual)
    else:
        correlation = np.asarray(((1.0, np.exp(-0.5)), (np.exp(-0.5), 1.0)))
        expected = np.linalg.solve(np.linalg.cholesky(correlation), residual)
        np.testing.assert_allclose(transform(residual), expected)


@pytest.mark.slow
def test_unresolved_gls_fallback_retains_correlated_error_calibration() -> (
    None
):
    """The fallback's covariance describes smooth noise, not white noise.

    This independent ensemble uses the existing 99.9% variance-calibration
    guard, not a fitted acceptance threshold or qualification population.
    """
    compact = _gaussian_input(
        amplitude=100.0,
        centroid_xy=(10.3, 9.7),
        sigma_axes=(3.3, 3.0),
        shape_yx=(21, 21),
        origin_yx=(0, 0),
        rms_value=1.0,
    )
    geometry = replace(
        _geometry(), noise_correlation_covariance_pixels_squared=(4, 0, 4)
    )
    yy, xx = np.indices((21, 21))
    coordinates = np.column_stack((xx.ravel(), yy.ravel()))
    distances = coordinates[:, None, :] - coordinates[None, :, :]
    correlation = np.exp(-0.5 * np.sum(distances**2, axis=2) / 4)
    eigenvalues, eigenvectors = np.linalg.eigh(correlation)
    tolerance = eigenvalues[-1] * len(eigenvalues) * np.finfo(float).eps
    assert eigenvalues[0] >= -tolerance
    # Draw from the analytic PSD covariance; remove only negative roundoff,
    # never add a white-noise floor to make a Cholesky factor exist.
    factor = eigenvectors * np.sqrt(np.maximum(eigenvalues, 0))
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    config = _fit_config(
        background_model="fixed-zero",
        pixel_support="owned-region",
        point_estimator="correlated-gls",
    )
    generator = np.random.default_rng(8_491_278)
    standardized = []
    for _ in range(48):
        observed = replace(
            compact,
            physical_residual=(
                compact.physical_residual
                + (factor @ generator.normal(size=441)).reshape((21, 21))
            ),
        )
        (result,) = fit_compact_gaussian_mixture(
            observed, moments, geometry, config
        )
        assert isinstance(result, ValidCompactGaussianFit)
        assert result.diagnostics.point_estimator == "diagonal-weighted"
        assert result.uncertainty is not None
        errors = result.uncertainty
        estimated = np.asarray(
            (
                *result.parameters.centroid_xy,
                result.parameters.amplitude_jy_per_beam,
            )
        )
        variance = np.asarray(
            (
                errors.centroid_covariance_xx_pixels_squared,
                errors.centroid_covariance_yy_pixels_squared,
                errors.amplitude_error_jy_per_beam**2,
            )
        )
        standardized.append(
            (estimated - (10.3, 9.7, 100.0)) / np.sqrt(variance)
        )
    observed_variance = np.var(standardized, axis=0, ddof=1)
    lower, upper = chi2.ppf((0.0005, 0.9995), df=47) / 47
    assert np.all((observed_variance >= lower) & (observed_variance <= upper))


def test_fit_bilinearly_samples_rms_at_the_fitted_centroid() -> None:
    """Component noise uses the contract's sub-pixel local RMS value."""
    compact = _gaussian_input(centroid_xy=(28.25, 17.5))
    local_y, local_x = np.indices(compact.rms.shape, dtype=np.float64)
    compact.rms[:] = 0.01 + 0.001 * local_x + 0.002 * local_y

    result = _fit(compact)

    assert isinstance(result, ValidCompactGaussianFit)
    expected = 0.01 + 0.001 * 8.25 + 0.002 * 7.5
    assert result.parameters.local_rms_jy_per_beam == pytest.approx(expected)


def test_local_rms_interpolation_renormalizes_masked_neighbours() -> None:
    """One invalid interpolation neighbour cannot erase valid local noise."""
    compact = _gaussian_input(centroid_xy=(28.25, 17.5))
    local_y, local_x = np.indices(compact.rms.shape, dtype=np.float64)
    compact.rms[:] = 0.01 + 0.001 * local_x + 0.002 * local_y
    compact.rms[:, 9:] = np.nan

    actual = fitting_algorithm._local_rms_at_centroid(
        compact,
        (28.25, 17.5),
    )

    expected = 0.01 + 0.001 * 8.0 + 0.002 * 7.5
    assert actual == pytest.approx(expected)


def test_local_rms_interpolation_preserves_explicit_unavailability() -> None:
    """No valid interpolation support remains a typed unavailable fit input."""
    compact = _gaussian_input(centroid_xy=(28.25, 17.5))
    compact.rms[:] = np.nan

    actual = fitting_algorithm._local_rms_at_centroid(
        compact,
        (28.25, 17.5),
    )

    assert np.isnan(actual)


def test_fit_uses_owned_region_rms_when_centroid_rms_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing centroid sample retains measured region noise explicitly."""
    compact = _gaussian_input()
    expected = float(
        np.mean(
            compact.rms[np.asarray(compact.region_labels) == 1],
            dtype=np.float64,
        )
    )

    def unavailable_local_rms(
        _compact: object,
        _centroid: tuple[float, float],
    ) -> float:
        return float("nan")

    monkeypatch.setattr(
        fitting_algorithm,
        "_local_rms_at_centroid",
        unavailable_local_rms,
    )

    result = _fit(compact)

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.parameters.local_rms_jy_per_beam == pytest.approx(expected)
    assert "local-rms-region-mean-fallback" in result.quality_flags


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


def test_owned_region_support_excludes_unlabelled_context() -> None:
    """The owned-support ablation must not fit neighbouring background."""
    compact = _gaussian_input(centroid_xy=(28.25, 17.5))
    margin = 4
    shape = (
        compact.physical_residual.shape[0] + 2 * margin,
        compact.physical_residual.shape[1] + 2 * margin,
    )
    residual = np.full(shape, 100.0, dtype=np.float64)
    labels = np.zeros(shape, dtype=np.int32)
    core = (slice(margin, -margin), slice(margin, -margin))
    residual[core] = compact.physical_residual
    labels[core] = compact.region_labels
    expanded = replace(
        compact,
        array_bounds=ImageBounds(
            compact.array_bounds.y_start - margin,
            compact.array_bounds.y_stop + margin,
            compact.array_bounds.x_start - margin,
            compact.array_bounds.x_stop + margin,
        ),
        physical_residual=residual,
        rms=np.full(shape, 0.05, dtype=np.float64),
        valid_pixels=np.ones(shape, dtype=np.bool_),
        region_labels=labels,
    )

    result = _fit(
        expanded,
        _fit_config(pixel_support="owned-region"),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.parameters.centroid_xy == pytest.approx(
        (28.25, 17.5), abs=1e-6
    )
    assert result.diagnostics.retained_pixel_count == int(
        np.count_nonzero(expanded.region_labels == 1)
    )


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


def _bright_fit_scene(scene: str) -> tuple[_FitInput, _FitInput, Any]:
    """Build the independent analytic initialization and observed scene."""
    center = (1.3, 9.7) if scene == "edge" else (10.3, 9.7)
    compact = _gaussian_input(
        amplitude=100.0,
        centroid_xy=center,
        sigma_axes=(2.6, 1.8),
        angle_degrees=31,
        shape_yx=(21, 21),
        origin_yx=(0, 0),
        rms_value=1,
    )
    oracle: Any = models.Gaussian2D(100, *center, 2.6, 1.8, np.deg2rad(31))
    if scene == "overlap":
        compact = _joint_input()
        compact = replace(
            compact, physical_residual=10 * compact.physical_residual
        )
        oracle = models.Gaussian2D(100, 12, 12, 2, 1.5, 0)
        oracle += models.Gaussian2D(70, 19, 12, 2, 1.5, 0)
    y, x = np.indices(compact.physical_residual.shape, dtype=float)
    observed = compact.physical_residual.copy()
    if scene == "asymmetric":
        observed += 8 * np.exp(-((x - 12) ** 2 / 24 + (y - 11) ** 2 / 10))
    if scene == "compact-on-diffuse":
        observed += 5 * np.exp(-((x - 11) ** 2 + (y - 10) ** 2) / 200)
    rms = 1 + 0.02 * x
    # A small bounded, deterministic perturbation exercises a nonzero
    # residual without selecting a favourable random realization.
    observed += 0.05 * rms * (np.sin(2 * x + 0.3 * y) + np.cos(1.3 * y))
    valid = compact.valid_pixels.copy()
    if scene in {"masked", "masked-centre"}:
        if scene == "masked-centre":
            valid[9:12, 9:12] = False
        else:
            valid[8:11, 11:13] = False
        observed[~valid] = np.nan
        labels = np.where(valid, compact.region_labels, 0).astype(np.int32)
        compact = replace(
            compact,
            region_labels=labels,
            island=replace(compact.island, pixel_count=int(valid.sum())),
            regions=(
                replace(compact.regions[0], pixel_count=int(valid.sum())),
            ),
        )
    # Isolate fit acceptance: initialize from positive analytic signal, as
    # production does from positive support, while fitting signed pixels.
    initialization = replace(compact, valid_pixels=valid, rms=rms)
    compact = replace(
        compact, physical_residual=observed, rms=rms, valid_pixels=valid
    )
    return compact, initialization, oracle


@pytest.mark.parametrize(
    ("scene", "joint"),
    (
        ("asymmetric", False),
        ("asymmetric", True),
        ("masked", False),
        ("masked", True),
        ("masked-centre", False),
        ("masked-centre", True),
        ("compact-on-diffuse", False),
        ("compact-on-diffuse", True),
        ("edge", False),
        ("edge", True),
        ("overlap", True),
    ),
)
def test_complete_bright_gaussians_agree_with_independent_model(
    scene: str, joint: bool
) -> None:
    """Compare entire ellipses, not just positions, on independent scenes.

    For the asymmetric source this checks the best Gaussian approximation,
    not that a Gaussian describes all of its light. An independently
    parameterized Astropy model fits the same valid original pixels and RMS;
    it does not use Hebog's fitted parameters as its initializer.
    """

    compact, initialization, oracle = _bright_fit_scene(scene)
    y, x = np.indices(compact.physical_residual.shape, dtype=float)
    observed, rms, valid = (
        compact.physical_residual,
        compact.rms,
        compact.valid_pixels,
    )
    geometry = replace(
        _beam_geometry(),
        noise_correlation_covariance_pixels_squared=(4, 0, 4),
    )
    moments = measure_compact_moments(
        initialization, geometry, _moment_config()
    )[1:]
    config = _fit_config(
        background_model="fixed-zero",
        model_selection="beam-or-free",
        point_estimator="correlated-gls",
    )
    if joint:
        selected = fit_compact_gaussian_mixture(
            compact, moments, geometry, config
        )
    else:
        selected = (
            fit_compact_gaussian(
                compact, compact.regions[0], moments[0], geometry, config
            ),
        )
    oracle_fit = fitting.TRFLSQFitter()(
        oracle,
        x[valid],
        y[valid],
        observed[valid],
        weights=1 / rms[valid],
        maxiter=300,
        acc=1e-10,
    )
    expected_models = (
        (oracle_fit[0], oracle_fit[1]) if scene == "overlap" else (oracle_fit,)
    )
    model_values = np.zeros_like(x)
    for actual, expected in zip(selected, expected_models, strict=True):
        assert isinstance(actual, ValidCompactGaussianFit)
        assert actual.diagnostics.model_identity == "free-elliptical"
        assert actual.diagnostics.point_estimator == "diagonal-weighted"
        assert actual.uncertainty is not None
        assert "correlated-noise-sandwich-errors" in actual.quality_flags
        component = actual.gaussian_component_fit
        parameters = (
            actual.parameters if component is None else component.parameters
        )
        assert parameters.centroid_xy == pytest.approx(
            (expected.x_mean.value, expected.y_mean.value), abs=1e-5
        )
        assert parameters.amplitude_jy_per_beam == pytest.approx(
            expected.amplitude.value, rel=1e-5
        )
        assert parameters.integrated_flux_jy == pytest.approx(
            expected.amplitude.value
            * 2
            * np.pi
            * expected.x_stddev.value
            * expected.y_stddev.value
            / 8,
            rel=1e-5,
        )
        actual_model = models.Gaussian2D(
            parameters.amplitude_jy_per_beam,
            *parameters.centroid_xy,
            parameters.major_sigma_pixels,
            parameters.minor_sigma_pixels,
            np.deg2rad(parameters.major_axis_angle_degrees),
        )
        # Comparing all sampled model pixels also catches axis/angle mixing
        # that a centroid or total-flux comparison alone cannot detect.
        np.testing.assert_allclose(
            actual_model(x, y), expected(x, y), rtol=1e-4, atol=1e-5
        )
        model_values += actual_model(x, y)
    chi_squared = float(
        np.sum(((model_values - observed)[valid] / rms[valid]) ** 2)
    )
    assert isinstance(selected[0], ValidCompactGaussianFit)
    assert selected[0].diagnostics.chi_squared == pytest.approx(
        chi_squared, rel=1e-8
    )


@pytest.mark.parametrize("joint", (False, True))
@pytest.mark.parametrize("initial_angle_offset", (0.0, 90.0))
@pytest.mark.parametrize("maximum_axis_ratio", (2.0, 4.0))
def test_axis_ratio_admission_is_independent_of_optimizer_axis_order(
    joint: bool,
    initial_angle_offset: float,
    maximum_axis_ratio: float,
) -> None:
    """A rotated initializer cannot bypass the physical ellipse ratio gate."""
    compact = _gaussian_input(
        amplitude=100.0,
        sigma_axes=(3.0, 1.0),
        angle_degrees=23.0,
    )
    geometry = _geometry()
    moment = measure_compact_moments(compact, geometry, _moment_config())[1]
    assert isinstance(moment, ValidMomentMeasurement)
    moment = replace(
        moment,
        initializer=replace(
            moment.initializer,
            major_axis_angle_degrees=(
                moment.initializer.major_axis_angle_degrees
                + initial_angle_offset
            ),
        ),
    )
    config = _fit_config(
        background_model="fixed-zero",
        maximum_axis_ratio=maximum_axis_ratio,
    )
    if joint:
        result = fit_compact_gaussian_mixture(
            compact, (moment,), geometry, config
        )[0]
    else:
        result = fit_compact_gaussian(
            compact, compact.regions[0], moment, geometry, config
        )

    if maximum_axis_ratio < 3:
        assert isinstance(result, FailedCompactGaussianFit)
        assert result.reason == "fit-invalid-result"
        assert result.moment == moment
    else:
        assert isinstance(result, ValidCompactGaussianFit)
        parameters = result.parameters
        assert parameters.centroid_xy == pytest.approx((28.3, 17.6))
        assert parameters.amplitude_jy_per_beam == pytest.approx(100)
        assert parameters.major_sigma_pixels == pytest.approx(3)
        assert parameters.minor_sigma_pixels == pytest.approx(1)
        assert parameters.major_axis_angle_degrees == pytest.approx(23)
        assert parameters.integrated_flux_jy == pytest.approx(
            100 * 2 * np.pi * 3 / 8
        )


@pytest.mark.parametrize(
    ("amplitude", "axes", "expected"),
    (
        (1.0, (2.0, 1.0), True),
        (1.0, (1.0, 2.0), True),
        (1.0, (2.01, 1.0), False),
        (1.0, (1.0, 2.01), False),
        (1.0, (0.0, 1.0), False),
        (1.0, (-1.0, 1.0), False),
        (1.0, (1.0, 0.0), False),
        (1.0, (1.0, -1.0), False),
        (0.0, (1.0, 1.0), False),
        (-1.0, (1.0, 1.0), False),
        (float("nan"), (1.0, 1.0), False),
        (1.0, (float("inf"), 1.0), False),
    ),
)
def test_numerical_ellipse_validity_boundaries(
    amplitude: float, axes: tuple[float, float], expected: bool
) -> None:
    """Check positivity, finiteness and both sides of the exact ratio gate."""
    fit = _fit(_gaussian_input())
    assert isinstance(fit, ValidCompactGaussianFit)
    parameters = np.asarray((amplitude, 0, 0, *axes, 0, 0), dtype=float)
    candidate = fitting_algorithm._FitCandidate(
        success=True,
        optimizer_parameters=parameters,
        full_parameters=parameters,
        jacobian=np.eye(7),
        covariance=np.eye(7),
        diagnostics=fit.diagnostics,
    )
    assert (
        fitting_algorithm._numerically_valid(
            candidate, _fit_config(maximum_axis_ratio=2)
        )
        is expected
    )


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
    assert result.diagnostics is not None
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
        ({"radius_sigma": float("nan")}, "radius"),
        ({"integrated_flux_jy": 0.0}, "flux"),
        ({"integrated_flux_jy": float("inf")}, "flux"),
        ({"visible_model_fraction": 0.0}, "fraction"),
        ({"visible_model_fraction": 1.01}, "fraction"),
        ({"retained_pixel_count": 0}, "pixel count"),
        ({"aperture_model": "unknown"}, "model"),
    ],
)
def test_aperture_photometry_rejects_invalid_evidence(
    changes: dict[str, object],
    message: str,
) -> None:
    """Published aperture evidence remains finite and physically bounded."""
    values: dict[str, object] = {
        "radius_sigma": 3.0,
        "integrated_flux_jy": 0.5,
        "visible_model_fraction": 0.8,
        "retained_pixel_count": 20,
        "aperture_model": "selected-fit",
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        AssociationAperturePhotometry(**values)  # type: ignore[arg-type]


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
        ({"extension_significance_sigma": 0.0}, "extension_significance"),
        (
            {"component_extension_significance_sigma": 0.0},
            "component_extension_significance",
        ),
        (
            {"integrated_flux_bias_correction_sigma": -0.01},
            "integrated_flux_bias_correction_sigma",
        ),
        (
            {"integrated_flux_bias_correction_sigma": 0.5},
            "integrated_flux_bias_correction_sigma",
        ),
        (
            {
                "extension_significance_sigma": 2.0,
                "component_extension_significance_sigma": 3.0,
            },
            "cannot exceed extension_significance",
        ),
        (
            {"maximum_information_condition_number": 1.0},
            "information_condition",
        ),
        ({"pixel_support": "unknown"}, "pixel_support"),
        ({"background_model": "unknown"}, "background_model"),
        ({"point_estimator": "unknown"}, "point_estimator"),
        ({"model_selection": "unknown"}, "model_selection"),
        ({"position_estimator": "unknown"}, "position_estimator"),
        ({"maximum_gls_pixels": 6}, "maximum_gls_pixels"),
        (
            {"association_aperture_radius_sigma": 0.0},
            "association_aperture_radius_sigma",
        ),
        (
            {"association_aperture_minimum_fixed_beam_model_fraction": 1.0},
            "minimum fixed-beam model fraction",
        ),
        (
            {"association_aperture_minimum_fixed_beam_model_fraction": 0.0},
            "minimum fixed-beam model fraction",
        ),
    ],
)
def test_fit_policy_rejects_invalid_bounds(
    changes: dict[str, object],
    message: str,
) -> None:
    """Every numerical and work bound is explicit and validated."""
    with pytest.raises(ValueError, match=message):
        _fit_config(**changes)
