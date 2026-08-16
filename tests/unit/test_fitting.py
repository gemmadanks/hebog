# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Analytic tests for the fit-all compact Gaussian reference."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest
from astropy.modeling import fitting, models
from scipy.special import ndtr

from hebog.algorithms import fitting as fitting_algorithm
from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.fitting import fit_compact_gaussian
from hebog.algorithms.measurement import measure_compact_moments
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    AssociationAperturePhotometry,
    FailedCompactGaussianFit,
    GaussianPositionEstimate,
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

    assert isinstance(result, ValidCompactGaussianFit)
    assert result.parameters.centroid_xy[1] <= 255.5
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
def test_truncated_context_position_refits_centroid_and_covariance(
    centroid_xy: tuple[float, float],
    origin_yx: tuple[int, int],
    edge_column: int,
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
        config=_fit_config(position_estimator="bounded-context-free"),
        geometry=_beam_geometry(),
    )

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
