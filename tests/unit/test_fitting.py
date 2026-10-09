# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic tests for the compact Gaussian fitter."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Literal, get_args, get_type_hints

import numpy as np
import pytest
from astropy.modeling import fitting, models
from scipy.stats import chi2

from hebog.algorithms import fitting as fitting_algorithm
from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.fitting import fit_compact_gaussian_mixture
from hebog.algorithms.measurement import measure_compact_moments
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    CompactGaussianFitResult,
    FailedCompactGaussianFit,
    GaussianFitDiagnostics,
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
) -> CompactGaussianFitResult:
    """Fit the one region of ``compact`` as a joint fit of one component."""
    selected_geometry = geometry or _geometry()
    measurements = measure_compact_moments(
        compact,
        selected_geometry,
        _moment_config(),
    )
    return fit_compact_gaussian_mixture(
        compact,
        (measurements[1],),
        selected_geometry,
        config or _fit_config(),
    )[0]


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
        compact, moments, geometry, _fit_config()
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
        compact, moments, geometry, _fit_config()
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
        compact, moments, geometry, _fit_config()
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
        _fit_config(model_selection="beam-or-free"),
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
    config = _fit_config(model_selection="beam-or-free")
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
        _fit_config(model_selection="beam-or-free"),
    )
    assert calls == 2
    assert all(
        isinstance(result, ValidCompactGaussianFit)
        and result.diagnostics.model_identity == "free-elliptical"
        for result in results
    )


# A 2.48-pixel FWHM beam, as on the SDC1 cut-outs: barely Nyquist sampled.
_UNDERSAMPLED_BEAM_SIGMA = 2.48 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
_RESOLVED_AMPLITUDE = 20.0
_RESOLVED_SIGMA_AXES = (3.5, 2.0)
# Noise draws of `_degenerate_neighbour_input` in which the thin
# component's owned pixels cannot constrain its own width, so the joint
# free fit has no identifiable solution. In draws 1, 4 and 6 they can.
_DEGENERATE_DRAWS = (0, 2, 3, 5, 7, 8, 9, 10, 11)


def _labelled_region(
    labels: np.ndarray, label: int, signal: np.ndarray, island_id: str
) -> DeblendedRegion:
    """Describe one owned label as the deblender would."""
    support = labels == label
    ys, xs = np.nonzero(support)
    peak = np.unravel_index(
        np.argmax(np.where(support, signal, -np.inf)), signal.shape
    )
    return DeblendedRegion(
        region_id=f"component-{label}",
        region_label=label,
        island_id=island_id,
        pixel_count=int(support.sum()),
        bounds=ImageBounds(
            int(ys.min()), int(ys.max() + 1), int(xs.min()), int(xs.max() + 1)
        ),
        peak_signal_to_noise=float(signal[peak]),
        peak_position_yx=(int(peak[0]), int(peak[1])),
        first_pixel_yx=(int(ys[0]), int(xs[0])),
    )


def _degenerate_neighbour_input(
    seed: int, labels_kept: tuple[int, ...] = (1, 2)
) -> tuple[_FitInput, CompactMeasurementGeometry, CompactGaussianFitConfig]:
    """A resolved source beside a component that owns a one-pixel ridge.

    Component 1 is a 20-sigma Gaussian, sigma 3.5 by 2 pixels at 30
    degrees, owning its positive pixels above 3 sigma. Component 2 owns a
    one-pixel-wide column of nine positive pixels, five of them raised by
    6 sigma, and one pixel beside it: its own pixels sample it along a line,
    so they cannot constrain its width, as for the components that sent
    joint fits on the SDC1 cut-outs singular. Components named in
    ``labels_kept`` beyond these are added to the image: 3 is a 12-sigma
    point source well apart from both; 4 owns only the right flank of a
    15-sigma Gaussian of sigma 2.5 pixels centred 2 pixels left of its
    pixels, so its free centroid stops at the region's margin. The noise is
    white with unit RMS; ``seed`` draws it.
    """
    shape = (32, 40)
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    angle = np.deg2rad(30.0)
    along = np.cos(angle) * (xx - 14.0) + np.sin(angle) * (yy - 16.0)
    across = -np.sin(angle) * (xx - 14.0) + np.cos(angle) * (yy - 16.0)
    resolved = _RESOLVED_AMPLITUDE * np.exp(
        -0.5
        * (
            (along / _RESOLVED_SIGMA_AXES[0]) ** 2
            + (across / _RESOLVED_SIGMA_AXES[1]) ** 2
        )
    )
    image = resolved + np.random.default_rng(seed).normal(size=shape)
    ridge = np.zeros(shape, dtype=np.bool_)
    ridge[12:21, 26] = True
    ridge[19, 27] = True
    image[14:19, 26] += 6.0
    image[ridge] = np.abs(image[ridge]) + 0.5
    point = 12.0 * np.exp(
        -0.5
        * ((xx - 5.0) ** 2 + (yy - 6.0) ** 2)
        / _UNDERSAMPLED_BEAM_SIGMA**2
    )
    if 3 in labels_kept:
        image += point
    flank = 15.0 * np.exp(-0.5 * ((xx - 3.0) ** 2 + (yy - 26.0) ** 2) / 2.5**2)
    if 4 in labels_kept:
        image += flank
    labels = np.zeros(shape, dtype=np.int32)
    labels[(resolved > 3.0) & (image > 0.0)] = 1
    labels[ridge] = 2
    labels[(point > 3.0) & (image > 0.0)] = 3
    labels[(flank > 3.0) & (xx >= 5) & (image > 0.0)] = 4
    labels[~np.isin(labels, labels_kept)] = 0
    bounds = ImageBounds(0, shape[0], 0, shape[1])
    owned = labels > 0
    peak = np.unravel_index(np.argmax(np.where(owned, image, -np.inf)), shape)
    ys, xs = np.nonzero(owned)
    island = DetectedIsland(
        island_id="island-00001",
        global_label=1,
        pixel_count=int(owned.sum()),
        bounds=bounds,
        peak_signal_to_noise=float(image[peak]),
        peak_position_yx=(int(peak[0]), int(peak[1])),
        first_pixel_yx=(int(ys[0]), int(xs[0])),
        touches_image_edge=False,
    )
    compact = _FitInput(
        island=island,
        array_bounds=bounds,
        regions=tuple(
            _labelled_region(labels, label, image, island.island_id)
            for label in labels_kept
        ),
        physical_residual=image,
        rms=np.ones(shape, dtype=np.float64),
        valid_pixels=np.ones(shape, dtype=np.bool_),
        region_labels=labels,
    )
    beam_variance = _UNDERSAMPLED_BEAM_SIGMA**2
    geometry = CompactMeasurementGeometry(
        pixel_solid_angle_steradians=1.0,
        restoring_beam_solid_angle_steradians=2.0 * np.pi * beam_variance,
        restoring_beam_covariance_pixels_squared=(
            beam_variance,
            0.0,
            beam_variance,
        ),
    )
    # The installed component policy, with its 1.5-sigma extension test.
    config = _fit_config(
        maximum_sigma_pixels=30.0,
        maximum_axis_ratio=30.0,
        convergence_tolerance=1e-8,
        extension_significance_sigma=1.5,
        component_extension_significance_sigma=1.5,
        pixel_support="owned-region",
        model_selection="beam-or-free",
    )
    return compact, geometry, config


def _free_joint_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[float | None]:
    """Record the information condition of every joint free solve."""
    conditions: list[float | None] = []
    original = fitting_algorithm._joint_candidates

    def record(samples: Any, bounds: Any, reasons: Any) -> Any:
        candidates = original(samples, bounds, reasons)
        if not any(reasons):
            conditions.append(
                candidates[0].diagnostics.information_condition_number
            )
        return candidates

    monkeypatch.setattr(fitting_algorithm, "_joint_candidates", record)
    return conditions


@pytest.mark.parametrize("seed", _DEGENERATE_DRAWS)
def test_a_degenerate_component_keeps_its_resolved_neighbour_free(
    monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    """Only the component whose pixels cannot fix its shape takes the beam.

    The joint free fit has no identifiable solution because component 2
    collapses onto its ridge. The 20-sigma resolved neighbour keeps its own
    free ellipse, with its size and flux, and records no rejected model of
    its own; the ridge takes the beam, published or failed at a bound.
    """
    compact, geometry, config = _degenerate_neighbour_input(seed)
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    free_conditions = _free_joint_conditions(monkeypatch)

    resolved, degenerate = fit_compact_gaussian_mixture(
        compact, moments, geometry, config
    )

    condition = free_conditions[0]
    assert (
        condition is None
        or condition > config.maximum_information_condition_number
    )
    assert isinstance(resolved, ValidCompactGaussianFit)
    assert resolved.diagnostics.model_identity == "free-elliptical"
    assert resolved.diagnostics.fallback_reason is None
    published = resolved.diagnostics.information_condition_number
    assert published is not None
    assert published <= config.maximum_information_condition_number
    assert (
        resolved.parameters.major_sigma_pixels,
        resolved.parameters.minor_sigma_pixels,
    ) == pytest.approx(_RESOLVED_SIGMA_AXES, rel=0.05)
    true_flux = (
        _RESOLVED_AMPLITUDE
        * 2.0
        * np.pi
        * np.prod(_RESOLVED_SIGMA_AXES)
        / geometry.restoring_beam_solid_angle_steradians
    )
    assert resolved.parameters.integrated_flux_jy == pytest.approx(
        true_flux, rel=0.07
    )
    assert resolved.diagnostics.rejected_model_identity is None
    assert resolved.diagnostics.rejected_model_bound_parameters == ()
    if isinstance(degenerate, FailedCompactGaussianFit):
        assert degenerate.reason == "fit-invalid-result"
    diagnostics = _fit_diagnostics(degenerate)
    assert diagnostics.model_identity == "beam-constrained"
    assert diagnostics.fallback_reason == "free-model-ill-conditioned"
    assert diagnostics.rejected_model_identity == "free-elliptical"


def _fit_diagnostics(
    result: CompactGaussianFitResult,
) -> GaussianFitDiagnostics:
    """Return a fitted or failed result's diagnostics, which it must have."""
    assert not isinstance(result, UnavailableCompactGaussianFit)
    assert result.diagnostics is not None
    return result.diagnostics


def _fit_degenerate_neighbours(
    seed: int, *, reverse: bool = False
) -> tuple[CompactGaussianFitResult, ...]:
    """Fit `_degenerate_neighbour_input`, in region order or reversed."""
    compact, geometry, config = _degenerate_neighbour_input(seed)
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    if not reverse:
        return fit_compact_gaussian_mixture(compact, moments, geometry, config)
    return fit_compact_gaussian_mixture(
        replace(compact, regions=compact.regions[::-1]),
        moments[::-1],
        geometry,
        config,
    )[::-1]


@pytest.mark.parametrize("seed", _DEGENERATE_DRAWS[:3])
def test_a_repaired_joint_fit_does_not_depend_on_component_order(
    seed: int,
) -> None:
    """Listing the components the other way round repairs the same fit."""
    forward = _fit_degenerate_neighbours(seed)
    backward = _fit_degenerate_neighbours(seed, reverse=True)

    for first, second in zip(forward, backward, strict=True):
        assert type(first) is type(second)
        if isinstance(first, ValidCompactGaussianFit):
            assert isinstance(second, ValidCompactGaussianFit)
            assert first.diagnostics.model_identity == (
                second.diagnostics.model_identity
            )
            assert first.diagnostics.fallback_reason == (
                second.diagnostics.fallback_reason
            )
            assert first.parameters.centroid_xy == pytest.approx(
                second.parameters.centroid_xy, abs=1e-5
            )
            assert first.parameters.integrated_flux_jy == pytest.approx(
                second.parameters.integrated_flux_jy, rel=1e-5
            )


@pytest.mark.parametrize("seed", _DEGENERATE_DRAWS[:3])
def test_a_degenerate_single_component_still_takes_the_beam(
    monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    """With no neighbour to keep free, the component falls back as before."""
    compact, geometry, config = _degenerate_neighbour_input(
        seed, labels_kept=(2,)
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    free_conditions = _free_joint_conditions(monkeypatch)

    (fitted,) = fit_compact_gaussian_mixture(
        compact, moments, geometry, config
    )

    condition = free_conditions[0]
    assert (
        condition is None
        or condition > config.maximum_information_condition_number
    )
    diagnostics = _fit_diagnostics(fitted)
    assert diagnostics.model_identity == "beam-constrained"
    assert diagnostics.fallback_reason == "free-model-ill-conditioned"


@pytest.mark.parametrize("seed", (1, 4, 6))
@pytest.mark.parametrize("fixture", ("ridge", "pair", "mixed"))
def test_a_well_conditioned_joint_fit_keeps_the_existing_selection(
    monkeypatch: pytest.MonkeyPatch, seed: int, fixture: str
) -> None:
    """Only an unidentifiable joint free fit is repaired.

    In these draws the ridge's pixels do fix its shape, and the analytic
    pairs are well conditioned, so the nested free and beam models are
    compared as before, in at most two joint solves.
    """
    if fixture == "ridge":
        compact, geometry, config = _degenerate_neighbour_input(seed)
    else:
        compact = _joint_input()
        if fixture == "mixed":
            yy, xx = np.mgrid[:25, :33]
            compact = replace(
                compact,
                physical_residual=50
                * np.exp(
                    -0.5 * (((xx - 12) / 2) ** 2 + ((yy - 12) / 1.5) ** 2)
                )
                + 50
                * np.exp(
                    -0.5 * (((xx - 19) / 3.2) ** 2 + ((yy - 12) / 2.2) ** 2)
                ),
            )
        geometry = replace(
            _geometry(),
            restoring_beam_covariance_pixels_squared=(4.0, 0.0, 2.25),
        )
        config = _fit_config(model_selection="beam-or-free")
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    solves = 0
    original = fitting_algorithm.least_squares

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal solves
        solves += 1
        return original(*args, **kwargs)

    def no_repair(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a well-conditioned joint fit was repaired")

    monkeypatch.setattr(fitting_algorithm, "least_squares", counted)
    monkeypatch.setattr(
        fitting_algorithm, "_repair_degenerate_components", no_repair
    )

    fitted = fit_compact_gaussian_mixture(compact, moments, geometry, config)

    assert solves <= 2
    assert all(isinstance(item, ValidCompactGaussianFit) for item in fitted)


def test_a_repair_that_finds_nothing_falls_back_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No component to constrain sends every component to the beam at once.

    Here the joint covariance is unavailable although the information is
    well conditioned, so no component makes it singular and no refit is
    tried before the whole-fit fallback.
    """
    compact = _joint_input()
    geometry = replace(
        _geometry(), restoring_beam_covariance_pixels_squared=(4.0, 0.0, 2.25)
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    solves = 0
    original = fitting_algorithm.least_squares

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal solves
        solves += 1
        return original(*args, **kwargs)

    def unavailable_covariance(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(fitting_algorithm, "least_squares", counted)
    monkeypatch.setattr(
        fitting_algorithm, "_parameter_covariance", unavailable_covariance
    )

    fitted = fit_compact_gaussian_mixture(
        compact,
        moments,
        geometry,
        _fit_config(model_selection="beam-or-free"),
    )

    assert solves == 2
    assert all(
        isinstance(item, FailedCompactGaussianFit)
        and item.diagnostics is not None
        and item.diagnostics.model_identity == "beam-constrained"
        for item in fitted
    )


def _repaired_ridge_with(
    monkeypatch: pytest.MonkeyPatch, name: str, replacement: Any
) -> tuple[CompactGaussianFitResult, ...]:
    """Fit the first degenerate ridge draw with one kernel replaced."""
    monkeypatch.setattr(fitting_algorithm, name, replacement)
    return _fit_degenerate_neighbours(_DEGENERATE_DRAWS[0])


def test_a_repaired_neighbour_that_is_not_extended_takes_the_beam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refit's free components face the extension test.

    Judged not significantly extended in the refit, the neighbour takes
    the beam as it would beside a bound contact, under that reason rather
    than the degenerate component's.
    """

    def never_extended(*_args: Any, **_kwargs: Any) -> bool:
        return False

    resolved, degenerate = _repaired_ridge_with(
        monkeypatch, "_significantly_extended", never_extended
    )

    assert isinstance(resolved, ValidCompactGaussianFit)
    assert resolved.diagnostics.model_identity == "beam-constrained"
    assert resolved.diagnostics.fallback_reason == (
        "free-model-not-significantly-extended"
    )
    assert _fit_diagnostics(degenerate).fallback_reason == (
        "free-model-ill-conditioned"
    )


def test_an_unresolved_neighbour_takes_the_beam_beside_a_resolved_one() -> (
    None
):
    """Extension is judged once; the resolved neighbour stays free.

    A 12-sigma point source joins the resolved source and the ridge. Once
    the ridge takes the beam, the point source is not significantly
    extended in the refit, so it takes the beam too and the next refit,
    with only the resolved source free, is published.
    """
    compact, geometry, config = _degenerate_neighbour_input(
        _DEGENERATE_DRAWS[0], labels_kept=(1, 2, 3)
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]

    resolved, degenerate, point = fit_compact_gaussian_mixture(
        compact, moments, geometry, config
    )

    assert isinstance(resolved, ValidCompactGaussianFit)
    assert resolved.diagnostics.model_identity == "free-elliptical"
    assert isinstance(point, ValidCompactGaussianFit)
    assert point.diagnostics.model_identity == "beam-constrained"
    assert point.diagnostics.fallback_reason == (
        "free-model-not-significantly-extended"
    )
    assert _fit_diagnostics(degenerate).fallback_reason == (
        "free-model-ill-conditioned"
    )


@pytest.mark.parametrize(
    "failure", ("non-convergence", "invalid", "singular", "irreparable")
)
def test_a_refit_that_cannot_be_accepted_falls_back_for_every_component(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A refit that fails, or leaves nothing free, ends in the beam fallback.

    The refit keeping the resolved neighbour free is made to fail to
    converge, to put that neighbour at a bound, to be singular again
    through the free neighbour, or to be singular through the beam model
    itself, which constraining the neighbour cannot repair. In each case no
    component is left free, so both take the beam.
    """
    solver = fitting_algorithm.least_squares
    solves = 0

    def second_solve(*args: Any, **kwargs: Any) -> Any:
        nonlocal solves
        solves += 1
        result = solver(*args, **kwargs)
        if solves == 2 and failure == "non-convergence":
            result.success = False
        if solves == 2 and failure == "singular":
            result.jac[:, -1] = result.jac[:, 0]
        if solves == 2 and failure == "irreparable":
            result.jac[:, -1] = 0.0
        return result

    invalid = fitting_algorithm._invalid_free_reason

    def bound_in_refit(candidate: Any, config: Any) -> Any:
        if failure == "invalid" and solves == 2:
            return "free-model-bound-contact"
        return invalid(candidate, config)

    monkeypatch.setattr(fitting_algorithm, "least_squares", second_solve)
    fitted = _repaired_ridge_with(
        monkeypatch, "_invalid_free_reason", bound_in_refit
    )

    assert all(
        _fit_diagnostics(item).model_identity == "beam-constrained"
        for item in fitted
    )
    resolved_reason = (
        "free-model-bound-contact"
        if failure == "invalid"
        else "free-model-ill-conditioned"
    )
    assert tuple(
        _fit_diagnostics(item).fallback_reason for item in fitted
    ) == (
        resolved_reason,
        "free-model-ill-conditioned",
    )


def test_a_decomposition_failure_while_repairing_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refit's linear-algebra failure leaves the whole-fit fallback.

    The failure is not a failure of the joint fit itself, so every
    component takes the beam rather than failing with the decomposition.
    """
    solver = fitting_algorithm.least_squares
    solves = 0

    def second_solve_fails(*args: Any, **kwargs: Any) -> Any:
        nonlocal solves
        solves += 1
        if solves == 2:
            raise np.linalg.LinAlgError("SVD did not converge")
        return solver(*args, **kwargs)

    fitted = _repaired_ridge_with(
        monkeypatch, "least_squares", second_solve_fails
    )

    assert solves == 3
    assert all(
        _fit_diagnostics(item).model_identity == "beam-constrained"
        and _fit_diagnostics(item).fallback_reason
        == "free-model-ill-conditioned"
        for item in fitted
    )


@pytest.mark.parametrize("seed", (0, 3, 8))
def test_a_neighbour_at_a_bound_takes_the_beam_in_the_first_refit(
    monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    """A component already at a bound is constrained, not judged.

    The flank component's free centroid stops at its region's margin in the
    singular free fit, so the first refit gives it the beam together with
    the degenerate ridge, and one refit settles the fit.
    """
    compact, geometry, config = _degenerate_neighbour_input(
        seed, labels_kept=(1, 2, 4)
    )
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    free_conditions = _free_joint_conditions(monkeypatch)
    solver = fitting_algorithm.least_squares
    solves = 0

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal solves
        solves += 1
        return solver(*args, **kwargs)

    monkeypatch.setattr(fitting_algorithm, "least_squares", counted)

    resolved, ridge, flank = fit_compact_gaussian_mixture(
        compact, moments, geometry, config
    )

    condition = free_conditions[0]
    assert (
        condition is None
        or condition > config.maximum_information_condition_number
    )
    assert solves == 2
    assert isinstance(resolved, ValidCompactGaussianFit)
    assert resolved.diagnostics.model_identity == "free-elliptical"
    assert _fit_diagnostics(ridge).fallback_reason == (
        "free-model-ill-conditioned"
    )
    assert _fit_diagnostics(flank).model_identity == "beam-constrained"
    assert _fit_diagnostics(flank).fallback_reason == (
        "free-model-bound-contact"
    )


@pytest.mark.parametrize("seed", (2, 3, 8))
def test_a_degenerate_component_with_an_invalid_shape_keeps_that_reason(
    seed: int,
) -> None:
    """An invalid free solution takes the beam for that reason first.

    Under an axis-ratio limit of 2 the ridge's collapsed free ellipse is
    invalid as well as degenerate, so it is set aside as invalid before any
    search, and the resolved neighbour, alone well conditioned, stays free.
    """
    compact, geometry, config = _degenerate_neighbour_input(seed)
    config = replace(config, maximum_axis_ratio=2.0)
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]

    resolved, ridge = fit_compact_gaussian_mixture(
        compact, moments, geometry, config
    )

    assert isinstance(resolved, ValidCompactGaussianFit)
    assert resolved.diagnostics.model_identity == "free-elliptical"
    assert _fit_diagnostics(ridge).model_identity == "beam-constrained"
    assert _fit_diagnostics(ridge).fallback_reason == (
        "free-model-invalid-result"
    )


def _basis_candidates(*, round_component: bool) -> tuple[Any, tuple[Any, ...]]:
    """Return fit samples and two free candidates of one joint fit.

    The first is the 20-sigma source, exactly round when asked, so its
    optimizer angle column is zero; the second has collapsed onto the
    ridge, its minor sigma 0.2 pixels across a one-pixel-wide column. Each
    candidate carries its exact optimizer-basis Jacobian.
    """
    compact, geometry, config = _degenerate_neighbour_input(0)
    valid = compact.region_labels > 0
    samples = fitting_algorithm._fit_samples_from_mask(
        compact, valid, compact.array_bounds, geometry, config
    )
    rows = (
        (20.0, 14.0, 16.0, 3.0, 3.0 if round_component else 2.0, 0.5, 0.0),
        (6.5, 26.0, 16.0, 2.5, 0.2, 0.5 * np.pi, 0.0),
    )
    candidates = []
    for row in rows:
        full = np.asarray(row, dtype=np.float64)
        jacobian = samples.residual_transform(
            fitting_algorithm._gaussian_parameter_jacobian(
                full, samples.x, samples.y
            )[:, :6]
            / samples.rms[:, None]
        )
        candidates.append(
            fitting_algorithm._FitCandidate(
                success=True,
                optimizer_parameters=full[:6],
                full_parameters=full,
                jacobian=jacobian,
                covariance=None,
                diagnostics=GaussianFitDiagnostics(
                    converged=True,
                    function_evaluations=1,
                    chi_squared=1.0,
                    degrees_of_freedom=1,
                    reduced_chi_squared=1.0,
                    parameters_at_bound=False,
                ),
            )
        )
    return samples, tuple(candidates)


def test_a_round_component_is_judged_in_precision_coordinates() -> None:
    """A circle's undefined angle does not make its component degenerate.

    The optimizer basis holds a zero angle column for the round source, so
    judged there it would be left out too; with no identifiable optimizer
    information the search judges Cartesian precision coordinates, where
    only the collapsed ridge is degenerate.
    """
    samples, candidates = _basis_candidates(round_component=True)
    assert not np.any(candidates[0].jacobian[:, 5])

    degenerate = fitting_algorithm._degenerate_free_components(
        samples, candidates, (None, None), ((16, 14), (12, 26))
    )

    assert degenerate == frozenset({1})


@pytest.mark.parametrize(
    ("parameterization", "condition", "expected"),
    (
        ("optimizer", 1e12, frozenset({0})),
        ("cartesian-precision", 1e12, frozenset()),
        ("optimizer", None, frozenset()),
    ),
)
def test_the_degenerate_search_judges_the_basis_the_fit_was_judged_in(
    parameterization: Literal["optimizer", "cartesian-precision"],
    condition: float | None,
    expected: frozenset[int],
) -> None:
    """The search uses the basis that judged the joint fit ill conditioned.

    The source's optimizer Jacobian is made singular by repeating its
    amplitude column, while its exact Cartesian blocks, rebuilt from its
    parameters, are not. A condition the optimizer basis gave is judged
    there and finds the source; one recovered in precision coordinates, or
    none found in either basis, is judged in precision coordinates, where
    the ridge-free pair is identifiable.
    """
    samples, (source, _) = _basis_candidates(round_component=False)
    jacobian = source.jacobian.copy()
    jacobian[:, 1] = jacobian[:, 0]
    diagnostics = replace(
        source.diagnostics,
        covariance_parameterization=parameterization,
        information_condition_number=condition,
    )
    elongated = replace(source, jacobian=jacobian, diagnostics=diagnostics)
    other = replace(
        source,
        full_parameters=np.asarray(
            (8.0, 22.0, 20.0, 2.0, 1.5, 0.3, 0.0), dtype=np.float64
        ),
    )
    other = replace(
        other,
        jacobian=samples.residual_transform(
            fitting_algorithm._gaussian_parameter_jacobian(
                other.full_parameters, samples.x, samples.y
            )[:, :6]
            / samples.rms[:, None]
        ),
    )

    degenerate = fitting_algorithm._degenerate_free_components(
        samples, (elongated, other), (None, None), ((16, 14), (20, 22))
    )

    assert degenerate == expected


def _unit_information(jacobian: np.ndarray) -> np.ndarray:
    """Normalize columns as the joint fit does before conditioning."""
    return fitting_algorithm._normalized_information(jacobian)


def test_the_degenerate_search_leaves_out_the_singular_component() -> None:
    """A component whose own columns coincide is the one left out."""
    rng = np.random.default_rng(3)
    jacobian = rng.normal(size=(40, 6))
    jacobian[:, 3] = jacobian[:, 2]

    left_out = fitting_algorithm._degenerate_components(
        _unit_information(jacobian),
        (2, 2, 2),
        judged=frozenset({0, 1, 2}),
        removable=frozenset({0, 1, 2}),
        canonical_keys=((0, 0), (0, 1), (0, 2)),
        maximum_condition=1e8,
    )

    assert left_out == frozenset({1})


@pytest.mark.parametrize(
    "order", ((0, 1, 2), (1, 0, 2), (2, 1, 0), (1, 2, 0), (2, 0, 1))
)
def test_the_degenerate_search_breaks_ties_on_the_canonical_key(
    order: tuple[int, int, int],
) -> None:
    """Two components that duplicate each other: leave out the first named.

    Leaving out either restores the same condition number exactly, so the
    choice falls to the component whose canonical key sorts first, however
    the components are listed.
    """
    rng = np.random.default_rng(5)
    columns = rng.normal(size=(30, 3))
    columns[:, 1] = columns[:, 0]
    keys = ((7, 3), (2, 9), (4, 4))

    left_out = fitting_algorithm._degenerate_components(
        _unit_information(columns[:, list(order)]),
        (1, 1, 1),
        judged=frozenset({0, 1, 2}),
        removable=frozenset({0, 1, 2}),
        canonical_keys=tuple(keys[index] for index in order),
        maximum_condition=1e8,
    )

    assert left_out == frozenset({order.index(1)})


def _singular_components(
    rng: np.random.Generator, singular: tuple[int, ...]
) -> np.ndarray:
    """Return five three-column components; those named are each singular."""
    jacobian = rng.normal(size=(80, 15))
    for index in singular:
        jacobian[:, 3 * index + 1] = jacobian[:, 3 * index]
    return jacobian


@pytest.mark.parametrize("pair", ((1, 4), (0, 2), (3, 4)))
def test_the_degenerate_search_leaves_out_two_singular_components(
    pair: tuple[int, int],
) -> None:
    """Each of two components alone singular: both, and only both, go.

    With either left, the rest's condition number sits at the limit of
    double precision whichever other component is left out, so ranking on
    it alone left out healthy components in many draws, as on the crowded
    SDC1 cut-out; counting unidentified directions does not.
    """
    keys = ((0, 4), (0, 3), (0, 2), (0, 1), (0, 0))
    wrong = [
        seed
        for seed in range(200)
        if fitting_algorithm._degenerate_components(
            _unit_information(
                _singular_components(np.random.default_rng(seed), pair)
            ),
            (3, 3, 3, 3, 3),
            judged=frozenset(range(5)),
            removable=frozenset(range(5)),
            canonical_keys=keys,
            maximum_condition=1e8,
        )
        != frozenset(pair)
    ]

    assert wrong == []


def _permutation_problem(
    rng: np.random.Generator, *, tied: bool
) -> list[np.ndarray]:
    """Return the column blocks of three to seven components.

    A tied problem repeats one component's whole block as another's, so
    leaving out either leaves the same matrix; otherwise two to five
    columns repeat others, within or across components, so several
    directions are singular at once.
    """
    count = int(rng.integers(3, 8))
    widths = rng.integers(2, 4, size=count)
    jacobian = rng.normal(size=(60, int(widths.sum())))
    if tied:
        first, second = (int(item) for item in rng.choice(count, 2, False))
        widths[second] = widths[first]
        jacobian = rng.normal(size=(60, int(widths.sum())))
        starts = np.concatenate(((0,), np.cumsum(widths)[:-1]))
        jacobian[:, starts[second] : starts[second] + widths[second]] = (
            jacobian[:, starts[first] : starts[first] + widths[first]]
        )
    else:
        for _ in range(int(rng.integers(2, 6))):
            source, target = rng.choice(jacobian.shape[1], 2, False)
            jacobian[:, target] = jacobian[:, source]
    return np.split(jacobian, np.cumsum(widths)[:-1], axis=1)


@pytest.mark.parametrize("tied", (True, False))
def test_the_degenerate_search_does_not_depend_on_component_order(
    tied: bool,
) -> None:
    """Listing components in any order leaves out the same components.

    Over 300 seeded problems and three orders each: an exactly tied pair of
    components, whose choice rounding noise in the eigenvalues would
    otherwise decide, and several singular directions at once, where every
    trial's condition number is noise.
    """
    changed = []
    for seed in range(300):
        rng = np.random.default_rng(seed)
        blocks = _permutation_problem(rng, tied=tied)
        keys = tuple((int(key), 0) for key in rng.permutation(len(blocks)))

        def left_out(
            order: np.ndarray,
            blocks: list[np.ndarray] = blocks,
            keys: tuple[tuple[int, int], ...] = keys,
        ) -> frozenset[int] | None:
            found = fitting_algorithm._degenerate_components(
                _unit_information(
                    np.column_stack([blocks[index] for index in order])
                ),
                tuple(blocks[index].shape[1] for index in order),
                judged=frozenset(range(len(order))),
                removable=frozenset(range(len(order))),
                canonical_keys=tuple(keys[index] for index in order),
                maximum_condition=1e8,
            )
            return (
                None
                if found is None
                else frozenset(int(order[index]) for index in found)
            )

        reference = left_out(np.arange(len(blocks)))
        if any(
            left_out(rng.permutation(len(blocks))) != reference
            for _ in range(3)
        ):
            changed.append(seed)

    assert changed == []


def test_the_degenerate_search_cannot_remove_a_component_it_may_not() -> None:
    """A singularity in a component that must stay cannot be repaired."""
    rng = np.random.default_rng(7)
    jacobian = rng.normal(size=(40, 4))
    jacobian[:, 0] = 0.0

    assert (
        fitting_algorithm._degenerate_components(
            _unit_information(jacobian),
            (2, 2),
            judged=frozenset({0, 1}),
            removable=frozenset({1}),
            canonical_keys=((0, 0), (0, 1)),
            maximum_condition=1e8,
        )
        is None
    )


def test_the_degenerate_search_leaves_out_nothing_when_none_is_needed() -> (
    None
):
    """Judged components that are already identifiable stay as they are."""
    jacobian = np.random.default_rng(9).normal(size=(40, 4))

    assert (
        fitting_algorithm._degenerate_components(
            _unit_information(jacobian),
            (2, 2),
            judged=frozenset({0, 1}),
            removable=frozenset({0, 1}),
            canonical_keys=((0, 0), (0, 1)),
            maximum_condition=1e8,
        )
        == frozenset()
    )


@pytest.mark.parametrize("seed", range(20))
def test_the_degenerate_search_matches_deleting_the_left_out_columns(
    seed: int,
) -> None:
    """Identity padding judges each trial as the deleted submatrix does.

    A brute-force greedy search that deletes the left-out components'
    columns and decomposes what remains chooses the same components.
    """
    rng = np.random.default_rng(seed)
    counts = tuple(int(item) for item in rng.integers(1, 4, size=5))
    jacobian = rng.normal(size=(60, sum(counts)))
    for _ in range(2):
        first, second = rng.choice(sum(counts), size=2, replace=False)
        jacobian[:, second] = jacobian[:, first] + 1e-6 * rng.normal(size=60)
    information = _unit_information(jacobian)
    owners = np.repeat(np.arange(len(counts)), counts)
    keys = tuple((int(item), 0) for item in rng.permutation(len(counts)))

    def judgement(kept: set[int]) -> tuple[int, float]:
        """Rank as the search does: unidentified directions, then the
        condition number on a rounded log scale where there are none."""
        columns = np.flatnonzero(np.isin(owners, sorted(kept)))
        if columns.size == 0:
            return 0, 0.0
        values = np.linalg.eigvalsh(information[np.ix_(columns, columns)])
        unidentified = int(np.count_nonzero(values * 1e8 <= values[-1]))
        if unidentified:
            return unidentified, float("inf")
        return 0, round(float(np.log10(values[-1] / values[0])), 9)

    kept = set(range(len(counts)))
    expected: set[int] = set()
    while judgement(kept)[0]:
        chosen = min(
            kept, key=lambda index: (*judgement(kept - {index}), keys[index])
        )
        kept.remove(chosen)
        expected.add(chosen)

    assert fitting_algorithm._degenerate_components(
        information,
        counts,
        judged=frozenset(range(len(counts))),
        removable=frozenset(range(len(counts))),
        canonical_keys=keys,
        maximum_condition=1e8,
    ) == frozenset(expected)


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
        _fit_config(),
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
        _fit_config(),
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
        _fit_config(maximum_function_evaluations=1),
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
        _fit_config(),
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
            _fit_config(),
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
        _fit_config(),
    )
    assert isinstance(fitted[0], UnavailableCompactGaussianFit)
    assert fitted[0].reason == "joint-peer-unavailable"
    assert isinstance(fitted[1], UnavailableCompactGaussianFit)
    assert fitted[1].reason == "non-positive-measurement"


def test_joint_empty_and_invalid_invocations_fail_before_fitting() -> None:
    """Joint work requires an exact component census and bounded work."""
    compact = _joint_input()
    geometry = _geometry()
    config = _fit_config()
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


def test_default_fit_policy_is_one_the_joint_fitter_accepts() -> None:
    """The only fitter fixes the background, so the default policy fits."""
    compact = _joint_input()
    geometry = _geometry()
    moments = measure_compact_moments(compact, geometry, _moment_config())[1:]
    config = CompactGaussianFitConfig(7, 300, 0.2, 20.0, 5.0, 1.0, 1e-10, 20.0)

    fits = fit_compact_gaussian_mixture(compact, moments, geometry, config)

    assert len(fits) == 2
    assert all(isinstance(fitted, ValidCompactGaussianFit) for fitted in fits)


@pytest.mark.parametrize(
    ("record", "unread"),
    [
        (
            CompactGaussianFitConfig,
            {
                "background_model",
                "maximum_background_offset_sigma",
                "association_aperture_radius_sigma",
                "association_aperture_minimum_fixed_beam_model_fraction",
            },
        ),
        (ValidCompactGaussianFit, {"association_aperture"}),
    ],
)
def test_fit_records_hold_nothing_the_joint_fit_never_reads(
    record: type[object], unread: set[str]
) -> None:
    """A fitted background offset and a per-fit aperture have no reader."""
    assert unread.isdisjoint(
        field.name
        for field in fields(record)  # pyright: ignore[reportArgumentType]
    )


def test_no_fit_identifies_a_centroid_constrained_model() -> None:
    """The joint fit selects only a free or a beam-constrained ellipse."""
    hints = get_type_hints(GaussianFitDiagnostics)

    assert get_args(hints["model_identity"]) == (
        "free-elliptical",
        "beam-constrained",
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
        _fit_config(),
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
        _fit_config(),
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
    assert result.quality_flags == ("fit-invalid-result", "joint-gaussian-fit")
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
    assert result.diagnostics.rejected_model_identity == "free-elliptical"
    assert result.parameters.centroid_xy == pytest.approx(
        centroid_xy, abs=1e-6
    )
    assert result.parameters.major_sigma_pixels == pytest.approx(axes[0])
    assert result.parameters.minor_sigma_pixels == pytest.approx(axes[1])
    assert not result.diagnostics.parameters_at_bound
    assert "beam-constrained-fit" in result.quality_flags
    assert "joint-gaussian-fit" in result.quality_flags


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
    original = fitting_algorithm.least_squares
    calls = 0

    def fail_smaller_model(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 2:
            result.success = False
        return result

    monkeypatch.setattr(fitting_algorithm, "least_squares", fail_smaller_model)

    result = _fit(
        compact,
        config=_fit_config(model_selection="beam-or-free"),
        geometry=geometry,
    )

    assert calls == 2
    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"
    assert result.diagnostics.rejected_model_identity == "beam-constrained"


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
    assert result.diagnostics.model_identity == "beam-constrained"
    assert result.diagnostics.fallback_reason == "free-model-bound-contact"
    assert result.diagnostics.rejected_model_identity == "free-elliptical"
    assert "centroid-y" in result.diagnostics.rejected_model_bound_parameters
    assert "beam-constrained-fit" in result.quality_flags
    assert "fit-at-bound" not in result.quality_flags


def test_fixed_background_is_an_explicit_smaller_model() -> None:
    """Residual maps may omit a redundant fitted local offset parameter."""
    compact = _gaussian_input(amplitude=5.0, sigma_axes=(3.8, 2.4))

    result = _fit(
        compact,
        config=_fit_config(
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


@pytest.mark.parametrize("center_y", (8.0, 10.0, 15.0))
@pytest.mark.parametrize("model_selection", ("free-only", "beam-or-free"))
def test_free_only_does_not_bypass_physical_fit_admission(
    center_y: float, model_selection: str
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
    config = _fit_config(model_selection=model_selection)
    result = fit_compact_gaussian_mixture(compact, moments, geometry, config)[
        0
    ]
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


def test_default_model_selection_preserves_the_free_fit_oracle() -> None:
    """Ordinary callers retain the established free-elliptical estimator."""
    assert _fit_config().model_selection == "free-only"
    result = _fit(
        _gaussian_input(amplitude=0.5, sigma_axes=(1.9, 1.2)),
        geometry=_beam_geometry(),
    )

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.diagnostics.model_identity == "free-elliptical"


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


@pytest.mark.parametrize("sigma", (2.0, 4.0))
@pytest.mark.parametrize("perturbation", ("none", "mixed-noise", "envelope"))
def test_oversampled_likelihood_uses_explicit_stable_fallback(
    sigma: float, perturbation: str
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
    config = _fit_config(pixel_support="owned-region")

    def fit(
        point_estimator: Literal["diagonal-weighted", "correlated-gls"],
    ) -> CompactGaussianFitResult:
        selected = replace(config, point_estimator=point_estimator)
        return fit_compact_gaussian_mixture(
            observed, moments, geometry, selected
        )[0]

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
    "scene",
    (
        "asymmetric",
        "masked",
        "masked-centre",
        "compact-on-diffuse",
        "edge",
        "overlap",
    ),
)
def test_complete_bright_gaussians_agree_with_independent_model(
    scene: str,
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
        model_selection="beam-or-free",
        point_estimator="correlated-gls",
    )
    selected = fit_compact_gaussian_mixture(compact, moments, geometry, config)
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
        parameters = actual.parameters
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


@pytest.mark.parametrize("initial_angle_offset", (0.0, 90.0))
@pytest.mark.parametrize("maximum_axis_ratio", (2.0, 4.0))
def test_axis_ratio_admission_is_independent_of_optimizer_axis_order(
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
        maximum_axis_ratio=maximum_axis_ratio,
    )
    result = fit_compact_gaussian_mixture(
        compact, (moment,), geometry, config
    )[0]

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
    assert result.quality_flags == (
        "fit-non-convergence",
        "joint-gaussian-fit",
    )


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
        ({"point_estimator": "unknown"}, "point_estimator"),
        ({"model_selection": "unknown"}, "model_selection"),
        ({"maximum_gls_pixels": 6}, "maximum_gls_pixels"),
    ],
)
def test_fit_policy_rejects_invalid_bounds(
    changes: dict[str, object],
    message: str,
) -> None:
    """Every numerical and work bound is explicit and validated."""
    with pytest.raises(ValueError, match=message):
        _fit_config(**changes)
