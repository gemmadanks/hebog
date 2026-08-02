"""Analytic and property tests for compact moment measurement."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.measurement import (
    fitted_gaussian_integrated_flux_jy,
    gaussian_beam_solid_angle_steradians,
    measure_compact_moments,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactMomentConfig
from hebog.data_models.measurement import (
    CompactMeasurementGeometry,
    ShapeUnavailableMomentMeasurement,
    UnavailableMomentMeasurement,
    ValidMomentMeasurement,
)
from hebog.data_models.partitioning import ImageBounds


@dataclass(frozen=True, slots=True)
class _MomentInput:
    """Minimal structural input accepted by the pure moment kernel."""

    island: DetectedIsland
    regions: tuple[DeblendedRegion, ...]
    physical_residual: np.ndarray
    rms: np.ndarray
    valid_pixels: np.ndarray
    region_labels: np.ndarray


def _config(**replacements: object) -> CompactMomentConfig:
    """Return one explicit moment numerical policy."""
    values: dict[str, object] = {
        "minimum_shape_pixels": 3,
        "covariance_relative_tolerance": 1e-12,
    }
    values.update(replacements)
    return CompactMomentConfig(**values)  # type: ignore[arg-type]


def _geometry() -> CompactMeasurementGeometry:
    """Use a simple, non-unit pixel-to-beam area ratio."""
    return CompactMeasurementGeometry(
        pixel_solid_angle_steradians=2.0,
        restoring_beam_solid_angle_steradians=5.0,
    )


def _input(
    residual: np.ndarray,
    labels: np.ndarray,
    *,
    rms: np.ndarray | None = None,
    valid_pixels: np.ndarray | None = None,
    origin_yx: tuple[int, int] = (10, 20),
) -> _MomentInput:
    """Construct consistent island and region summaries for exact labels."""
    residual = np.asarray(residual, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int32)
    y_start, x_start = origin_yx
    bounds = ImageBounds(
        y_start=y_start,
        y_stop=y_start + residual.shape[0],
        x_start=x_start,
        x_stop=x_start + residual.shape[1],
    )
    owned = labels > 0
    peak_local = np.unravel_index(
        np.argmax(np.where(owned, residual, -np.inf)),
        residual.shape,
    )
    first_local = np.argwhere(owned)[0]
    island = DetectedIsland(
        island_id="island-00001",
        global_label=1,
        pixel_count=int(np.count_nonzero(owned)),
        bounds=bounds,
        peak_signal_to_noise=10.0,
        peak_position_yx=(
            y_start + int(peak_local[0]),
            x_start + int(peak_local[1]),
        ),
        first_pixel_yx=(
            y_start + int(first_local[0]),
            x_start + int(first_local[1]),
        ),
        touches_image_edge=False,
    )
    regions: list[DeblendedRegion] = []
    for label in sorted(set(np.unique(labels)) - {0}):
        membership = labels == label
        local_positions = np.argwhere(membership)
        peak = np.unravel_index(
            np.argmax(np.where(membership, residual, -np.inf)),
            residual.shape,
        )
        regions.append(
            DeblendedRegion(
                region_id=f"{island.island_id}-region-{label:05d}",
                region_label=int(label),
                island_id=island.island_id,
                pixel_count=int(np.count_nonzero(membership)),
                bounds=ImageBounds(
                    y_start=y_start + int(np.min(local_positions[:, 0])),
                    y_stop=y_start + int(np.max(local_positions[:, 0])) + 1,
                    x_start=x_start + int(np.min(local_positions[:, 1])),
                    x_stop=x_start + int(np.max(local_positions[:, 1])) + 1,
                ),
                peak_signal_to_noise=10.0,
                peak_position_yx=(
                    y_start + int(peak[0]),
                    x_start + int(peak[1]),
                ),
                first_pixel_yx=(
                    y_start + int(local_positions[0, 0]),
                    x_start + int(local_positions[0, 1]),
                ),
            )
        )
    return _MomentInput(
        island=island,
        regions=tuple(regions),
        physical_residual=residual,
        rms=(
            np.full(residual.shape, 0.25, dtype=np.float64)
            if rms is None
            else np.asarray(rms, dtype=np.float64)
        ),
        valid_pixels=(
            np.ones(residual.shape, dtype=np.bool_)
            if valid_pixels is None
            else np.asarray(valid_pixels, dtype=np.bool_)
        ),
        region_labels=labels,
    )


def _valid_results(inputs: _MomentInput) -> tuple[ValidMomentMeasurement, ...]:
    """Measure and assert that every target has a complete initializer."""
    results = measure_compact_moments(inputs, _geometry(), _config())
    assert all(
        isinstance(result, ValidMomentMeasurement) for result in results
    )
    return results  # type: ignore[return-value]


def test_weighted_moments_and_photometry_have_analytic_values() -> None:
    """The serial oracle computes exact physical-plane moment meanings."""
    inputs = _input(
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        np.ones((2, 2), dtype=np.int32),
        rms=np.array([[0.1, 0.2], [0.3, 0.4]]),
    )

    island, region = _valid_results(inputs)

    assert island.target.object_kind == "island"
    assert region.target.object_kind == "deblended-region"
    assert island.photometry.peak_brightness_jy_per_beam == 4.0
    assert island.photometry.peak_position_xy == (21, 11)
    assert island.photometry.owned_pixel_integrated_flux_jy == 4.0
    assert island.photometry.local_rms_jy_per_beam == 0.25
    assert island.photometry.mean_brightness_jy_per_beam == 2.5
    assert island.initializer.amplitude_jy_per_beam == 4.0
    assert island.initializer.centroid_xy == pytest.approx((20.6, 10.7))
    assert island.initializer.covariance_xx_pixels_squared == pytest.approx(
        0.24
    )
    assert island.initializer.covariance_xy_pixels_squared == pytest.approx(
        -0.02
    )
    assert island.initializer.covariance_yy_pixels_squared == pytest.approx(
        0.21
    )


def test_exact_labels_exclude_unowned_pixels_and_separate_fluxes() -> None:
    """Island and region reductions use labels, never bounding rectangles."""
    inputs = _input(
        np.array([[1.0, 2.0, 1e9], [3.0, 4.0, 5.0]]),
        np.array([[1, 1, 0], [1, 2, 2]], dtype=np.int32),
        rms=np.array([[0.1, 0.2, np.nan], [0.3, 0.4, 0.6]]),
        valid_pixels=np.array(
            [[True, True, False], [True, True, True]], dtype=np.bool_
        ),
    )

    results = measure_compact_moments(inputs, _geometry(), _config())

    assert [result.target.object_kind for result in results] == [
        "island",
        "deblended-region",
        "deblended-region",
    ]
    assert [result.target.object_id for result in results] == [
        "island-00001",
        "island-00001-region-00001",
        "island-00001-region-00002",
    ]
    assert [
        result.photometry.owned_pixel_integrated_flux_jy
        for result in results
        if not isinstance(result, UnavailableMomentMeasurement)
    ] == pytest.approx([6.0, 2.4, 3.6])
    assert [
        result.photometry.local_rms_jy_per_beam
        for result in results
        if not isinstance(result, UnavailableMomentMeasurement)
    ] == pytest.approx([0.32, 0.2, 0.5])


@given(
    scale=st.floats(
        min_value=1e-6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
    y_offset=st.integers(min_value=0, max_value=10_000),
    x_offset=st.integers(min_value=0, max_value=10_000),
)
def test_positive_scaling_and_translation_preserve_shape(
    scale: float,
    y_offset: int,
    x_offset: int,
) -> None:
    """Brightness scaling and global translation obey moment invariants."""
    residual = np.array([[1.0, 2.0], [3.0, 4.0]])
    labels = np.ones((2, 2), dtype=np.int32)
    baseline = _valid_results(_input(residual, labels, origin_yx=(0, 0)))[0]
    transformed = _valid_results(
        _input(
            residual * scale,
            labels,
            rms=np.full((2, 2), 0.25 * scale),
            origin_yx=(y_offset, x_offset),
        )
    )[0]

    assert transformed.initializer.centroid_xy == pytest.approx(
        (
            baseline.initializer.centroid_xy[0] + x_offset,
            baseline.initializer.centroid_xy[1] + y_offset,
        )
    )
    assert transformed.initializer.major_sigma_pixels == pytest.approx(
        baseline.initializer.major_sigma_pixels
    )
    assert transformed.initializer.minor_sigma_pixels == pytest.approx(
        baseline.initializer.minor_sigma_pixels
    )
    assert transformed.initializer.major_axis_angle_degrees == pytest.approx(
        baseline.initializer.major_axis_angle_degrees
    )
    assert transformed.photometry.owned_pixel_integrated_flux_jy == (
        pytest.approx(
            baseline.photometry.owned_pixel_integrated_flux_jy * scale
        )
    )
    assert transformed.photometry.local_rms_jy_per_beam == pytest.approx(
        baseline.photometry.local_rms_jy_per_beam * scale
    )


def test_quarter_turn_rotates_the_pixel_major_axis() -> None:
    """Transposing a non-circular footprint rotates its moment axis by 90°."""
    residual = np.ones((3, 5), dtype=np.float64)
    horizontal = _valid_results(
        _input(residual, np.ones_like(residual, dtype=np.int32))
    )[0]
    vertical = _valid_results(
        _input(residual.T, np.ones_like(residual.T, dtype=np.int32))
    )[0]

    assert horizontal.initializer.major_axis_angle_degrees == pytest.approx(
        0.0
    )
    assert vertical.initializer.major_axis_angle_degrees == pytest.approx(90.0)
    assert vertical.initializer.major_sigma_pixels == pytest.approx(
        horizontal.initializer.major_sigma_pixels
    )
    assert vertical.initializer.minor_sigma_pixels == pytest.approx(
        horizontal.initializer.minor_sigma_pixels
    )


def test_circular_covariance_has_canonical_zero_pixel_angle() -> None:
    """A rotation-invariant moment ellipse does not expose numerical angle."""
    residual = np.ones((3, 3), dtype=np.float64)

    result = _valid_results(
        _input(residual, np.ones_like(residual, dtype=np.int32))
    )[0]

    assert result.initializer.major_sigma_pixels == pytest.approx(
        result.initializer.minor_sigma_pixels
    )
    assert result.initializer.major_axis_angle_degrees == 0.0


def test_reduction_is_independent_of_array_memory_order() -> None:
    """Canonical pixel order is identical for C- and F-order arrays."""
    residual = np.arange(1.0, 13.0).reshape(3, 4)
    labels = np.ones((3, 4), dtype=np.int32)
    c_order = _input(np.array(residual, order="C"), labels)
    f_order = _input(
        np.array(residual, order="F"),
        np.array(labels, order="F"),
    )

    assert measure_compact_moments(c_order, _geometry(), _config()) == (
        measure_compact_moments(f_order, _geometry(), _config())
    )


@pytest.mark.parametrize("plane", ["residual", "rms", "validity"])
def test_non_finite_owned_pixels_return_unavailable(plane: str) -> None:
    """Non-finite owned values produce a typed result without fake flux."""
    residual = np.ones((2, 2), dtype=np.float64)
    rms = np.ones((2, 2), dtype=np.float64)
    validity = np.ones((2, 2), dtype=np.bool_)
    if plane == "validity":
        validity[0, 0] = False
    else:
        (residual if plane == "residual" else rms)[0, 0] = np.nan
    inputs = _input(
        residual,
        np.ones((2, 2)),
        rms=rms,
        valid_pixels=validity,
    )

    results = measure_compact_moments(inputs, _geometry(), _config())

    assert all(
        isinstance(result, UnavailableMomentMeasurement)
        and result.reason == "non-finite-owned-pixels"
        for result in results
    )


@pytest.mark.parametrize(
    ("plane", "value"),
    [("residual", 0.0), ("residual", -1.0), ("rms", 0.0)],
)
def test_non_positive_measurement_returns_unavailable(
    plane: str,
    value: float,
) -> None:
    """A non-positive owned brightness never receives valid photometry."""
    residual = np.ones((2, 2), dtype=np.float64)
    rms = np.ones((2, 2), dtype=np.float64)
    (residual if plane == "residual" else rms)[0, 0] = value

    results = measure_compact_moments(
        _input(residual, np.ones((2, 2)), rms=rms),
        _geometry(),
        _config(),
    )

    assert all(
        isinstance(result, UnavailableMomentMeasurement)
        and result.reason == "non-positive-measurement"
        for result in results
    )


def test_underdetermined_region_preserves_photometry_without_shape() -> None:
    """Too few pixels retain flux but cannot invent a Gaussian ellipse."""
    inputs = _input(
        np.array([[1.0, 2.0]]),
        np.ones((1, 2), dtype=np.int32),
    )

    results = measure_compact_moments(inputs, _geometry(), _config())

    assert all(
        isinstance(result, ShapeUnavailableMomentMeasurement)
        and result.reason == "underdetermined-region"
        and result.photometry.owned_pixel_integrated_flux_jy
        == pytest.approx(1.2)
        for result in results
    )


def test_singular_covariance_preserves_photometry_without_shape() -> None:
    """Collinear owned pixels cannot be represented as a valid 2-D ellipse."""
    inputs = _input(
        np.ones((1, 3), dtype=np.float64),
        np.ones((1, 3), dtype=np.int32),
    )

    results = measure_compact_moments(inputs, _geometry(), _config())

    assert all(
        isinstance(result, ShapeUnavailableMomentMeasurement)
        and result.reason == "singular-covariance"
        for result in results
    )


def test_gaussian_and_owned_pixel_flux_conversions_are_distinct() -> None:
    """A fitted Gaussian area is not an island's finite pixel sum."""
    integrated = fitted_gaussian_integrated_flux_jy(
        amplitude_jy_per_beam=3.0,
        major_sigma_pixels=2.0,
        minor_sigma_pixels=1.0,
        geometry=_geometry(),
    )

    assert integrated == pytest.approx(3.0 * 4.0 * np.pi * 2.0 / 5.0)
    assert integrated != pytest.approx(3.0 * 2.0 / 5.0)


def test_gaussian_beam_area_uses_reviewed_fwhm_formula() -> None:
    """Restoring-beam solid angle follows pi*major*minor/(4 ln 2)."""
    area = gaussian_beam_solid_angle_steradians(
        major_fwhm_degrees=2.0,
        minor_fwhm_degrees=1.0,
    )

    assert area == pytest.approx(
        np.pi * np.deg2rad(2.0) * np.deg2rad(1.0) / (4.0 * np.log(2.0))
    )


@pytest.mark.parametrize(
    ("major", "minor"),
    [
        (float("nan"), 1.0),
        (1.0, float("inf")),
        (0.0, 1.0),
        (1.0, -1.0),
    ],
)
def test_rejects_invalid_gaussian_beam_axes(
    major: float,
    minor: float,
) -> None:
    """Beam conversion requires explicit finite positive FWHM axes."""
    with pytest.raises(ValueError, match="beam FWHM"):
        gaussian_beam_solid_angle_steradians(
            major_fwhm_degrees=major,
            minor_fwhm_degrees=minor,
        )


@pytest.mark.parametrize(
    ("amplitude", "major", "minor"),
    [
        (float("nan"), 1.0, 1.0),
        (1.0, float("inf"), 1.0),
        (1.0, 1.0, 0.0),
    ],
)
def test_rejects_invalid_fitted_gaussian_values(
    amplitude: float,
    major: float,
    minor: float,
) -> None:
    """Fitted flux conversion cannot manufacture area from invalid values."""
    with pytest.raises(ValueError, match="amplitude and sigma"):
        fitted_gaussian_integrated_flux_jy(
            amplitude_jy_per_beam=amplitude,
            major_sigma_pixels=major,
            minor_sigma_pixels=minor,
            geometry=_geometry(),
        )


@pytest.mark.parametrize(
    ("field", "replacement", "error", "message"),
    [
        ("physical_residual", np.ones(4), ValueError, "two-dimensional"),
        (
            "physical_residual",
            np.ones((1, 2), dtype=np.float64),
            ValueError,
            "match island bounds",
        ),
        (
            "physical_residual",
            np.ones((2, 2), dtype=np.float32),
            TypeError,
            "float64",
        ),
        (
            "rms",
            np.ones((2, 2), dtype=np.float32),
            TypeError,
            "float64",
        ),
        (
            "valid_pixels",
            np.ones((2, 2), dtype=np.int8),
            TypeError,
            "boolean",
        ),
        (
            "region_labels",
            np.ones((2, 2), dtype=np.int64),
            TypeError,
            "int32",
        ),
    ],
)
def test_rejects_misaligned_or_wrong_dtype_arrays(
    field: str,
    replacement: np.ndarray,
    error: type[Exception],
    message: str,
) -> None:
    """The pure boundary rejects arrays outside its exact typed contract."""
    inputs = _input(np.ones((2, 2)), np.ones((2, 2)))

    with pytest.raises(error, match=message):
        measure_compact_moments(
            replace(inputs, **{field: replacement}),
            _geometry(),
            _config(),
        )


def test_rejects_island_region_and_label_disagreements() -> None:
    """Compact identities and summaries remain bound to exact membership."""
    inputs = _input(np.ones((2, 2)), np.ones((2, 2)))
    wrong_island = replace(inputs.island, pixel_count=3)
    wrong_labels = np.full((2, 2), 2, dtype=np.int32)
    wrong_region = replace(inputs.regions[0], pixel_count=3)
    wrong_parent = replace(inputs.regions[0], island_id="different")

    for changed, message in (
        (replace(inputs, island=wrong_island), "island pixel count"),
        (replace(inputs, region_labels=wrong_labels), "region summaries"),
        (replace(inputs, regions=(wrong_region,)), "region summary"),
        (replace(inputs, regions=(wrong_parent,)), "region summary"),
    ):
        with pytest.raises(ValueError, match=message):
            measure_compact_moments(changed, _geometry(), _config())


def test_rejects_duplicate_region_labels_or_identities() -> None:
    """Every exact region has one unique canonical label and identity."""
    inputs = _input(
        np.ones((2, 2)),
        np.array([[1, 1], [2, 2]], dtype=np.int32),
    )
    duplicate_label = replace(
        inputs.regions[1],
        region_label=inputs.regions[0].region_label,
    )
    duplicate_id = replace(
        inputs.regions[1],
        region_id=inputs.regions[0].region_id,
    )

    for regions in (
        (inputs.regions[0], duplicate_label),
        (inputs.regions[0], duplicate_id),
    ):
        with pytest.raises(ValueError, match="unique"):
            measure_compact_moments(
                replace(inputs, regions=regions),
                _geometry(),
                _config(),
            )


@pytest.mark.parametrize(
    ("replacements", "message"),
    [
        ({"minimum_shape_pixels": True}, "minimum_shape_pixels"),
        ({"minimum_shape_pixels": 2}, "minimum_shape_pixels"),
        ({"covariance_relative_tolerance": 0.0}, "covariance"),
        ({"covariance_relative_tolerance": float("nan")}, "covariance"),
        ({"covariance_relative_tolerance": 1.0}, "covariance"),
    ],
)
def test_rejects_invalid_moment_policy(
    replacements: dict[str, object],
    message: str,
) -> None:
    """Shape availability thresholds are explicit and numerically bounded."""
    with pytest.raises(ValueError, match=message):
        _config(**replacements)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"pixel_solid_angle_steradians": 0.0}, "pixel"),
        ({"pixel_solid_angle_steradians": float("inf")}, "pixel"),
        ({"restoring_beam_solid_angle_steradians": -1.0}, "beam"),
    ],
)
def test_rejects_invalid_measurement_geometry(
    values: dict[str, float],
    message: str,
) -> None:
    """Flux conversion never infers or accepts invalid solid angles."""
    defaults = {
        "pixel_solid_angle_steradians": 2.0,
        "restoring_beam_solid_angle_steradians": 5.0,
    }
    defaults.update(values)
    with pytest.raises(ValueError, match=message):
        CompactMeasurementGeometry(**defaults)
