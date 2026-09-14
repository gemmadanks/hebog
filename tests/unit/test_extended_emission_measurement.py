"""Analytic contracts for bounded original-pixel extended measurement."""

from __future__ import annotations

from dataclasses import fields, replace

import numpy as np
import pytest

from hebog.algorithms.extended_measurement import (
    ExtendedEmissionTilePlanes,
    ExtendedEmissionTileTarget,
    combine_extended_emission_partials,
    measure_extended_emission_tile,
)
from hebog.config import ExtendedEmissionMeasurementConfig
from hebog.data_models.measurement import (
    ExtendedEmissionPhotometry,
    ExtendedEmissionTarget,
    ExtendedMeasurementGeometry,
    ExtendedMeasurementTruncation,
    ExtendedMomentShape,
    MeasuredExtendedEmission,
    UnavailableExtendedEmission,
)
from hebog.data_models.partitioning import ImageBounds, TilePartition


def _geometry() -> ExtendedMeasurementGeometry:
    """Return one deterministic pixel/beam conversion."""
    return ExtendedMeasurementGeometry(
        pixel_solid_angle_steradians=1.0,
        restoring_beam_solid_angle_steradians=4.0,
        restoring_beam_major_fwhm_pixels=2.0,
        restoring_beam_minor_fwhm_pixels=1.5,
        restoring_beam_position_angle_degrees=20.0,
    )


def _config() -> ExtendedEmissionMeasurementConfig:
    """Return the governed aperture and numerical availability policy."""
    return ExtendedEmissionMeasurementConfig(
        aperture_radius_beams=1.5,
        maximum_task_pixels=128,
        minimum_shape_pixels=3,
        covariance_relative_tolerance=1e-12,
        denoised_position_maximum_peak_to_mean_ratio=3.0,
    )


def _targets() -> tuple[ExtendedEmissionTarget, ExtendedEmissionTarget]:
    """Return two distinct exact supports sharing one measurement tile."""
    return (
        ExtendedEmissionTarget(
            object_kind="deferred-island",
            object_id="island-00001",
            parent_island_id="island-00001",
            support_pixel_count=4,
            bounds=ImageBounds(1, 3, 1, 3),
        ),
        ExtendedEmissionTarget(
            object_kind="deferred-island",
            object_id="island-00002",
            parent_island_id="island-00002",
            support_pixel_count=4,
            bounds=ImageBounds(1, 3, 5, 7),
        ),
    )


def _tile_inputs() -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    TilePartition,
]:
    """Build original pixels plus exact and nearest-owned support labels."""
    residual = np.ones((4, 8), dtype=np.float64)
    residual[1:3, 1:3] = ((2.0, 4.0), (3.0, 5.0))
    residual[1:3, 5:7] = ((4.0, 6.0), (5.0, 7.0))
    background = np.full(residual.shape, 2.0, dtype=np.float64)
    rms = np.full(residual.shape, 0.5, dtype=np.float64)
    valid = np.ones(residual.shape, dtype=np.bool_)
    valid[0, 0] = False
    support = np.zeros(residual.shape, dtype=np.int32)
    support[1:3, 1:3] = 1
    support[1:3, 5:7] = 2
    aperture = np.zeros(residual.shape, dtype=np.int32)
    aperture[:, :4] = 1
    aperture[:, 4:] = 2
    bounds = ImageBounds(0, 4, 0, 8)
    return (
        residual,
        background,
        rms,
        valid,
        support,
        aperture,
        TilePartition(0, 0, bounds, bounds),
    )


def test_extended_measurement_uses_original_pixels_and_unique_apertures() -> (
    None
):
    """Flux, position, shape, background, uncertainty, and truncation agree."""
    first, second = _targets()
    (
        residual,
        background,
        rms,
        valid,
        support,
        aperture,
        partition,
    ) = _tile_inputs()
    partials = measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(
            residual,
            background,
            rms,
            valid,
            support,
            aperture,
        ),
        partition,
        (
            ExtendedEmissionTileTarget(1, first),
            ExtendedEmissionTileTarget(2, second),
        ),
    )

    measured = combine_extended_emission_partials(
        (first, second),
        partials,
        _geometry(),
        _config(),
        image_shape_yx=residual.shape,
    )

    assert all(isinstance(item, MeasuredExtendedEmission) for item in measured)
    first_result = measured[0]
    assert isinstance(first_result, MeasuredExtendedEmission)
    assert first_result.photometry.integrated_flux_jy == pytest.approx(6.25)
    assert first_result.photometry.mean_background_jy_per_beam == 2.0
    assert first_result.photometry.local_rms_jy_per_beam == 0.5
    assert first_result.photometry.aperture_pixel_count == 16
    assert first_result.photometry.observable_aperture_pixel_count == 15
    assert first_result.photometry.integrated_flux_error_jy == pytest.approx(
        np.sqrt(15.0 / 16.0)
    )
    assert first_result.centroid_xy == pytest.approx((23.0 / 14.0, 11.0 / 7.0))
    assert first_result.peak_position_xy == (2, 2)
    assert first_result.shape is not None
    assert first_result.shape_status == "available"
    assert first_result.flux_uncertainty_status == (
        "available-correlated-beam-approximation"
    )
    assert first_result.position_uncertainty_status == (
        "unavailable-support-selection-not-propagated"
    )
    assert first_result.position_weight_kind == "direct-original-residual"
    assert first_result.shape_uncertainty_status == (
        "unavailable-support-selection-not-propagated"
    )
    assert first_result.truncation.status == "image-edge-and-invalid-pixels"
    assert (
        first_result.truncation.observable_aperture_fraction
        == pytest.approx(15.0 / 16.0)
    )
    assert (
        sum(
            item.photometry.aperture_pixel_count
            for item in measured
            if isinstance(item, MeasuredExtendedEmission)
        )
        == residual.size
    )
    assert not any(
        isinstance(getattr(partial, field.name), np.ndarray)
        for partial in partials
        for field in fields(partial)
    )


def test_extended_measurement_reports_typed_unavailability() -> None:
    """A non-positive signed support never receives invented measurements."""
    first, _ = _targets()
    residual = -np.ones((2, 2), dtype=np.float64)
    background = np.zeros_like(residual)
    rms = np.ones_like(residual)
    valid = np.ones(residual.shape, dtype=np.bool_)
    labels = np.ones(residual.shape, dtype=np.int32)
    bounds = ImageBounds(1, 3, 1, 3)
    target = replace(first, bounds=bounds)
    partition = TilePartition(0, 0, bounds, bounds)

    partials = measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(
            residual,
            background,
            rms,
            valid,
            labels,
            labels,
        ),
        partition,
        (ExtendedEmissionTileTarget(1, target),),
    )
    result = combine_extended_emission_partials(
        (target,),
        partials,
        _geometry(),
        _config(),
        image_shape_yx=(5, 5),
    )[0]

    assert isinstance(result, UnavailableExtendedEmission)
    assert result.reason == "non-positive-support-flux"
    assert result.centroid_xy is None
    assert result.integrated_flux_jy is None
    assert result.truncation.status == "image-edge"


def test_extended_measurement_distinguishes_shape_and_flux_availability() -> (
    None
):
    """Shape failure preserves photometry while flux failures omit it."""
    first, _ = _targets()
    inputs = _tile_inputs()
    first_support = np.where(inputs[4] == 1, 1, 0).astype(np.int32)
    first_aperture = np.where(inputs[5] == 1, 1, 0).astype(np.int32)
    partial = measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(
            *inputs[:4],
            first_support,
            first_aperture,
        ),
        inputs[6],
        (ExtendedEmissionTileTarget(1, first),),
    )[0]
    underdetermined = combine_extended_emission_partials(
        (first,),
        (partial,),
        _geometry(),
        replace(_config(), minimum_shape_pixels=5),
        image_shape_yx=inputs[0].shape,
    )[0]
    invalid = combine_extended_emission_partials(
        (first,),
        (replace(partial, invalid_support_pixel_count=1),),
        _geometry(),
        _config(),
        image_shape_yx=inputs[0].shape,
    )[0]
    negative_aperture = combine_extended_emission_partials(
        (first,),
        (replace(partial, aperture_signal_sum_jy_per_beam=-1.0),),
        _geometry(),
        _config(),
        image_shape_yx=inputs[0].shape,
    )[0]

    assert isinstance(underdetermined, MeasuredExtendedEmission)
    assert underdetermined.shape is None
    assert underdetermined.shape_status == "unavailable"
    assert underdetermined.shape_unavailable_reason == (
        "underdetermined-support"
    )
    assert isinstance(invalid, UnavailableExtendedEmission)
    assert invalid.reason == "non-finite-support"
    assert isinstance(negative_aperture, UnavailableExtendedEmission)
    assert negative_aperture.reason == "non-positive-aperture-flux"

    residual = np.ones((1, 3), dtype=np.float64)
    labels = np.ones(residual.shape, dtype=np.int32)
    valid = np.ones(residual.shape, dtype=np.bool_)
    bounds = ImageBounds(2, 3, 1, 4)
    target = ExtendedEmissionTarget(
        object_kind="multiscale-detection",
        object_id="scale-detection-00001",
        parent_island_id=None,
        support_pixel_count=3,
        bounds=bounds,
    )
    collinear = measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(
            residual,
            np.zeros_like(residual),
            np.ones_like(residual),
            valid,
            labels,
            labels,
        ),
        TilePartition(0, 0, bounds, bounds),
        (ExtendedEmissionTileTarget(1, target),),
    )
    singular = combine_extended_emission_partials(
        (target,),
        collinear,
        _geometry(),
        _config(),
        image_shape_yx=(5, 5),
    )[0]
    assert isinstance(singular, MeasuredExtendedEmission)
    assert singular.shape is None
    assert singular.shape_unavailable_reason == "singular-covariance"


def test_extended_tile_contracts_fail_closed_on_misaligned_ownership() -> None:
    """Ambiguous arrays, labels, targets, and aggregates are rejected."""
    first, second = _targets()
    inputs = _tile_inputs()
    planes = ExtendedEmissionTilePlanes(*inputs[:6])
    partition = inputs[6]
    targets = (
        ExtendedEmissionTileTarget(1, first),
        ExtendedEmissionTileTarget(2, second),
    )

    with pytest.raises(ValueError, match="two-dimensional core"):
        measure_extended_emission_tile(
            replace(planes, residual_jy_per_beam=inputs[0][:-1]),
            partition,
            targets,
        )
    with pytest.raises(TypeError, match="float64"):
        measure_extended_emission_tile(
            replace(planes, residual_jy_per_beam=inputs[0].astype(np.float32)),
            partition,
            targets,
        )
    with pytest.raises(TypeError, match="boolean"):
        measure_extended_emission_tile(
            replace(planes, valid_pixels=inputs[3].astype(np.int8)),
            partition,
            targets,
        )
    with pytest.raises(TypeError, match="int32"):
        measure_extended_emission_tile(
            replace(planes, support_labels=inputs[4].astype(np.int64)),
            partition,
            targets,
        )
    with pytest.raises(ValueError, match="regularized position signal"):
        measure_extended_emission_tile(
            replace(
                planes,
                regularized_position_signal_jy_per_beam=inputs[0][:-1],
            ),
            partition,
            targets,
        )
    with pytest.raises(TypeError, match="regularized position signal"):
        measure_extended_emission_tile(
            replace(
                planes,
                regularized_position_signal_jy_per_beam=inputs[0].astype(
                    np.float32
                ),
            ),
            partition,
            targets,
        )
    negative = np.array(inputs[4], copy=True)
    negative[0, 0] = -1
    with pytest.raises(ValueError, match="non-negative"):
        measure_extended_emission_tile(
            replace(planes, support_labels=negative),
            partition,
            targets,
        )
    missing_owner = np.array(inputs[5], copy=True)
    missing_owner[1, 1] = 0
    with pytest.raises(ValueError, match="retain aperture ownership"):
        measure_extended_emission_tile(
            replace(planes, aperture_labels=missing_owner),
            partition,
            targets,
        )
    unknown = np.array(inputs[5], copy=True)
    unknown[0, 0] = 3
    with pytest.raises(ValueError, match="unknown target"):
        measure_extended_emission_tile(
            replace(planes, aperture_labels=unknown),
            partition,
            targets,
        )
    with pytest.raises(ValueError, match="unique and canonical"):
        measure_extended_emission_tile(
            planes,
            partition,
            tuple(reversed(targets)),
        )

    partials = measure_extended_emission_tile(planes, partition, targets)
    with pytest.raises(ValueError, match="unique and canonical"):
        combine_extended_emission_partials(
            tuple(reversed((first, second))),
            partials,
            _geometry(),
            _config(),
            image_shape_yx=inputs[0].shape,
        )
    with pytest.raises(ValueError, match="unknown target"):
        combine_extended_emission_partials(
            (first,),
            (replace(partials[0], target=second),),
            _geometry(),
            _config(),
            image_shape_yx=inputs[0].shape,
        )
    with pytest.raises(ValueError, match="no measurement partials"):
        combine_extended_emission_partials(
            (first,),
            (),
            _geometry(),
            _config(),
            image_shape_yx=inputs[0].shape,
        )
    with pytest.raises(ValueError, match="target support"):
        combine_extended_emission_partials(
            (first,),
            (replace(partials[0], support_pixel_count=3),),
            _geometry(),
            _config(),
            image_shape_yx=inputs[0].shape,
        )


def test_extended_measurement_records_reject_inconsistent_evidence() -> None:
    """Public measurement records fail closed on invalid scientific state."""
    target = replace(
        _targets()[0],
        object_kind="multiscale-detection",
        object_id="scale-detection-00001",
        parent_island_id=None,
    )
    truncation = ExtendedMeasurementTruncation("none", 1.0)
    photometry = ExtendedEmissionPhotometry(
        peak_brightness_jy_per_beam=5.0,
        integrated_flux_jy=2.0,
        integrated_flux_error_jy=0.2,
        local_rms_jy_per_beam=0.5,
        mean_background_jy_per_beam=0.0,
        aperture_pixel_count=10,
        observable_aperture_pixel_count=10,
    )
    shape = ExtendedMomentShape(1.0, 0.0, 0.5, 2.0, 1.0, 20.0)
    measured = MeasuredExtendedEmission(
        target=target,
        photometry=photometry,
        centroid_xy=(2.0, 2.0),
        peak_position_xy=(2, 2),
        shape=shape,
        shape_status="available",
        shape_unavailable_reason=None,
        truncation=truncation,
        position_weight_kind="direct-original-residual",
    )

    with pytest.raises(ValueError, match="finite and positive"):
        replace(_geometry(), pixel_solid_angle_steradians=0.0)
    with pytest.raises(ValueError, match="minor axis"):
        replace(_geometry(), restoring_beam_minor_fwhm_pixels=3.0)
    with pytest.raises(ValueError, match="position angle"):
        replace(_geometry(), restoring_beam_position_angle_degrees=180.0)
    with pytest.raises(ValueError, match="object ID"):
        replace(target, object_id="")
    with pytest.raises(ValueError, match="object kind"):
        replace(target, object_kind="unsupported")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="parent island"):
        replace(target, parent_island_id="")
    with pytest.raises(ValueError, match="fit inside"):
        replace(target, support_pixel_count=5)
    with pytest.raises(ValueError, match=r"in \[0, 1\]"):
        ExtendedMeasurementTruncation("invalid-pixels", np.nan)
    with pytest.raises(ValueError, match="status must match"):
        ExtendedMeasurementTruncation("none", 0.5)
    with pytest.raises(ValueError, match="must be positive"):
        replace(photometry, integrated_flux_jy=0.0)
    with pytest.raises(ValueError, match="error must be finite"):
        replace(photometry, integrated_flux_error_jy=-1.0)
    with pytest.raises(ValueError, match="background must be finite"):
        replace(photometry, mean_background_jy_per_beam=np.inf)
    with pytest.raises(ValueError, match="count must fit"):
        replace(photometry, observable_aperture_pixel_count=11)
    with pytest.raises(ValueError, match="values must be finite"):
        replace(shape, covariance_xy_pixels_squared=np.nan)
    with pytest.raises(ValueError, match="covariance must be positive"):
        replace(shape, covariance_xy_pixels_squared=1.0)
    with pytest.raises(ValueError, match="axes must be positive"):
        replace(shape, major_fwhm_pixels=0.5)
    with pytest.raises(ValueError, match="position angle"):
        replace(shape, position_angle_degrees=-1.0)
    with pytest.raises(ValueError, match="centroid"):
        replace(measured, centroid_xy=(-1.0, 2.0))
    with pytest.raises(ValueError, match="peak position"):
        replace(measured, peak_position_xy=(-1, 2))
    with pytest.raises(ValueError, match="status must match"):
        replace(measured, shape_status="unavailable")
    with pytest.raises(ValueError, match="reason must match"):
        replace(measured, shape_unavailable_reason="singular-covariance")


def test_extended_partial_and_aggregate_edge_contracts() -> None:
    """Scalar partials reject corruption and retain typed edge outcomes."""
    first, _ = _targets()
    inputs = _tile_inputs()
    support = np.where(inputs[4] == 1, 1, 0).astype(np.int32)
    aperture = np.where(inputs[5] == 1, 1, 0).astype(np.int32)
    partial = measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(*inputs[:4], support, aperture),
        inputs[6],
        (ExtendedEmissionTileTarget(1, first),),
    )[0]

    with pytest.raises(ValueError, match="label must be positive"):
        ExtendedEmissionTileTarget(0, first)
    with pytest.raises(ValueError, match="counts must be non-negative"):
        replace(partial, aperture_pixel_count=-1)
    with pytest.raises(ValueError, match="invalid support count"):
        replace(partial, invalid_support_pixel_count=5)
    with pytest.raises(ValueError, match="observable aperture"):
        replace(partial, observable_aperture_pixel_count=17)
    with pytest.raises(ValueError, match="peak availability"):
        replace(partial, peak_position_yx=None)
    with pytest.raises(ValueError, match="regularized-position count"):
        replace(partial, invalid_regularized_support_pixel_count=5)
    with pytest.raises(ValueError, match="regularized-position partial peak"):
        replace(partial, regularized_peak_signal_jy_per_beam=1.0)
    with pytest.raises(ValueError, match="unrequested regularized-position"):
        replace(partial, regularized_support_weight=1.0)
    with pytest.raises(ValueError, match="no in-image"):
        combine_extended_emission_partials(
            (first,),
            (
                replace(
                    partial,
                    aperture_pixel_count=0,
                    observable_aperture_pixel_count=0,
                ),
            ),
            _geometry(),
            _config(),
            image_shape_yx=inputs[0].shape,
        )
    with pytest.raises(ValueError, match="image shape"):
        combine_extended_emission_partials(
            (first,),
            (partial,),
            _geometry(),
            _config(),
            image_shape_yx=(0, 8),
        )
    first_half = replace(partial, support_pixel_count=2)
    second_half = replace(
        partial,
        support_pixel_count=2,
        regularized_position_requested=True,
    )
    with pytest.raises(ValueError, match="regularized position provenance"):
        combine_extended_emission_partials(
            (first,),
            (first_half, second_half),
            _geometry(),
            _config(),
            image_shape_yx=inputs[0].shape,
        )

    invalid_planes = ExtendedEmissionTilePlanes(
        inputs[0],
        inputs[1],
        inputs[2],
        np.zeros(inputs[3].shape, dtype=np.bool_),
        support,
        aperture,
    )
    invalid_partial = measure_extended_emission_tile(
        invalid_planes,
        inputs[6],
        (ExtendedEmissionTileTarget(1, first),),
    )
    unavailable = combine_extended_emission_partials(
        (first,),
        invalid_partial,
        _geometry(),
        _config(),
        image_shape_yx=inputs[0].shape,
    )[0]
    assert isinstance(unavailable, UnavailableExtendedEmission)
    assert unavailable.reason == "non-finite-support"
    assert unavailable.truncation.status == "image-edge-and-invalid-pixels"


def test_isotropic_extended_support_has_canonical_zero_position_angle() -> (
    None
):
    """A rotationally symmetric support uses the canonical zero angle."""
    target = _targets()[0]
    residual = np.ones((2, 2), dtype=np.float64)
    labels = np.ones(residual.shape, dtype=np.int32)
    bounds = ImageBounds(1, 3, 1, 3)
    partials = measure_extended_emission_tile(
        ExtendedEmissionTilePlanes(
            residual,
            np.zeros_like(residual),
            np.ones_like(residual),
            np.ones(residual.shape, dtype=np.bool_),
            labels,
            labels,
        ),
        TilePartition(0, 0, bounds, bounds),
        (ExtendedEmissionTileTarget(1, target),),
    )
    result = combine_extended_emission_partials(
        (target,),
        partials,
        _geometry(),
        _config(),
        image_shape_yx=(5, 5),
    )[0]
    assert isinstance(result, MeasuredExtendedEmission)
    assert result.shape is not None
    assert result.shape.position_angle_degrees == 0.0


def test_regularized_position_weights_retain_safeguards() -> None:
    """Diffuse positions use scale signal; compact or invalid cases do not."""
    target = replace(
        _targets()[0],
        object_kind="multiscale-detection",
        object_id="scale-detection-00002",
        parent_island_id=None,
    )
    bounds = ImageBounds(1, 3, 1, 3)
    partition = TilePartition(0, 0, bounds, bounds)
    labels = np.ones((2, 2), dtype=np.int32)
    valid = np.ones((2, 2), dtype=np.bool_)
    regularized = np.array(((1.0, 1.0), (1.0, 9.0)), dtype=np.float64)

    def measure(
        residual: np.ndarray,
        position_signal: np.ndarray,
    ) -> MeasuredExtendedEmission:
        partials = measure_extended_emission_tile(
            ExtendedEmissionTilePlanes(
                residual,
                np.zeros_like(residual),
                np.ones_like(residual),
                valid,
                labels,
                labels,
                position_signal,
            ),
            partition,
            (ExtendedEmissionTileTarget(1, target),),
        )
        result = combine_extended_emission_partials(
            (target,),
            partials,
            _geometry(),
            _config(),
            image_shape_yx=(5, 5),
        )[0]
        assert isinstance(result, MeasuredExtendedEmission)
        return result

    diffuse = measure(np.ones((2, 2), dtype=np.float64), regularized)
    assert diffuse.position_weight_kind == (
        "regularized-direct-plus-multiscale"
    )
    assert diffuse.centroid_xy == pytest.approx((11.0 / 6.0, 11.0 / 6.0))
    assert diffuse.peak_position_xy == (2, 2)

    compact = measure(
        np.array(((20.0, 1.0), (1.0, 1.0)), dtype=np.float64),
        regularized,
    )
    assert compact.position_weight_kind == "direct-original-residual"
    assert compact.peak_position_xy == (1, 1)

    invalid_regularized = np.array(regularized, copy=True)
    invalid_regularized[0, 0] = np.nan
    fallback = measure(
        np.ones((2, 2), dtype=np.float64),
        invalid_regularized,
    )
    assert fallback.position_weight_kind == "direct-original-residual"
    assert fallback.centroid_xy == (1.5, 1.5)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"aperture_radius_beams": 0.0}, "aperture_radius_beams"),
        ({"maximum_task_pixels": True}, "maximum_task_pixels"),
        ({"minimum_shape_pixels": 2}, "minimum_shape_pixels"),
        ({"covariance_relative_tolerance": 1.0}, "tolerance"),
        (
            {"denoised_position_maximum_peak_to_mean_ratio": 1.0},
            "peak_to_mean_ratio",
        ),
    ],
)
def test_extended_measurement_config_rejects_ambiguous_policy(
    update: dict[str, object],
    message: str,
) -> None:
    """Scientific and memory bounds must be explicit and finite."""
    values: dict[str, object] = {
        "aperture_radius_beams": 1.5,
        "maximum_task_pixels": 128,
        "minimum_shape_pixels": 3,
        "covariance_relative_tolerance": 1e-12,
        "denoised_position_maximum_peak_to_mean_ratio": 3.0,
    }
    values.update(update)
    with pytest.raises(ValueError, match=message):
        ExtendedEmissionMeasurementConfig(**values)  # type: ignore[arg-type]
