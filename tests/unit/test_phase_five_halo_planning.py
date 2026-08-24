"""Contracts for reviewed Phase 5 stage halos and tile admission."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hebog.algorithms.extended_measurement import (
    extended_measurement_halo_pixels,
    segment_refinement_halo_pixels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    residual_atrous_scale_halos_pixels,
    scale_smoothing_halo_pixels,
)
from hebog.algorithms.multiscale_association import (
    compact_context_halo_pixels,
)
from hebog.algorithms.phase_five_execution import (
    derive_phase_five_halo_plan,
)
from hebog.config import ExtendedEmissionMeasurementConfig


def _beam() -> BeamShapePixels:
    """Return a representative five-pixel restoring beam."""
    return BeamShapePixels(5.0, 4.0, 20.0)


def _measurement_config() -> ExtendedEmissionMeasurementConfig:
    """Return the reviewed 1.5-beam measurement configuration."""
    return ExtendedEmissionMeasurementConfig(
        aperture_radius_beams=1.5,
        maximum_task_pixels=200_000,
        minimum_shape_pixels=3,
        covariance_relative_tolerance=1e-12,
        denoised_position_maximum_peak_to_mean_ratio=3.0,
    )


def test_halo_plan_derives_every_stage_from_implemented_science() -> None:
    """The reviewed core admits all image and record-only Phase 5 stages."""
    plan = derive_phase_five_halo_plan(
        _beam(),
        tile_core_shape_yx=(256, 256),
        maximum_task_pixels=200_000,
        measurement_config=_measurement_config(),
    )

    assert plan.tile_core_shape_yx == (256, 256)
    assert plan.maximum_halo_yx == (34, 34)
    assert plan.maximum_read_shape_yx == (324, 324)
    assert plan.maximum_read_pixel_count == 104_976
    assert tuple(stage.stage_name for stage in plan.stages) == (
        "matched-filter-seed",
        "residual-b3-atrous",
        "segment-labelling",
        "segment-refinement",
        "cross-scale-association",
        "compact-context",
        "extended-measurement",
        "combined-reconciliation",
        "product-materialization",
    )
    by_name = {stage.stage_name: stage for stage in plan.stages}
    assert by_name["matched-filter-seed"].scale_halos_pixels == (9, 17, 34)
    assert by_name["residual-b3-atrous"].scale_halos_pixels == (2, 6, 14)
    assert by_name["segment-refinement"].halo_yx == (3, 3)
    assert by_name["compact-context"].halo_yx == (3, 3)
    assert by_name["extended-measurement"].halo_yx == (8, 8)
    assert by_name["extended-measurement"].read_shape_yx == (272, 272)
    assert by_name["extended-measurement"].read_pixel_count == 73_984
    assert by_name["extended-measurement"].admission_limit_pixels == 200_000
    for name in (
        "segment-labelling",
        "cross-scale-association",
        "combined-reconciliation",
        "product-materialization",
    ):
        assert by_name[name].halo_yx == (0, 0)


def test_halo_plan_supports_rectangular_cores() -> None:
    """Worst-case reads preserve the two independent core dimensions."""
    plan = derive_phase_five_halo_plan(
        _beam(),
        tile_core_shape_yx=(320, 288),
        maximum_task_pixels=200_000,
        measurement_config=_measurement_config(),
    )

    assert plan.maximum_read_shape_yx == (388, 356)
    assert plan.maximum_read_pixel_count == 138_128


def test_allocation_free_halo_helpers_match_kernel_policies() -> None:
    """Planning and scientific kernels share the same exact radii."""
    assert tuple(
        scale_smoothing_halo_pixels(
            _beam(),
            width_beams=width,
            truncation_sigma=4.0,
        )
        for width in (1.0, 2.0, 4.0)
    ) == (9, 17, 34)
    assert residual_atrous_scale_halos_pixels() == (2, 6, 14)
    assert segment_refinement_halo_pixels(5.0) == 3
    assert compact_context_halo_pixels(5.0) == 3
    assert (
        extended_measurement_halo_pixels(
            _measurement_config(),
            beam_major_fwhm_pixels=5.0,
        )
        == 8
    )


@pytest.mark.parametrize(
    ("width_beams", "truncation_sigma", "message"),
    [
        (0.0, 4.0, "scale width"),
        (1.0, 2.0, "truncation_sigma"),
    ],
)
def test_scale_halo_helper_rejects_undefined_kernel(
    width_beams: float,
    truncation_sigma: float,
    message: str,
) -> None:
    """Allocation-free planning rejects invalid filter geometry."""
    with pytest.raises(ValueError, match=message):
        scale_smoothing_halo_pixels(
            _beam(),
            width_beams=width_beams,
            truncation_sigma=truncation_sigma,
        )


def test_measurement_halo_helper_rejects_invalid_beam() -> None:
    """Measurement planning cannot admit an undefined beam radius."""
    with pytest.raises(ValueError, match="beam major FWHM"):
        extended_measurement_halo_pixels(
            _measurement_config(),
            beam_major_fwhm_pixels=True,
        )


def test_halo_plan_rejects_core_that_cannot_contain_largest_halo() -> None:
    """The shared core must preserve the canonical quarter-core guardrail."""
    with pytest.raises(ValueError, match="below one quarter"):
        derive_phase_five_halo_plan(
            _beam(),
            tile_core_shape_yx=(128, 128),
            maximum_task_pixels=200_000,
            measurement_config=_measurement_config(),
        )


@pytest.mark.parametrize(
    "tile_core_shape_yx",
    [(256,), (True, 256), (0, 256), (1.5, 256)],
)
def test_halo_plan_rejects_invalid_core_shape(
    tile_core_shape_yx: tuple[object, ...],
) -> None:
    """Core geometry must be exactly two positive integral dimensions."""
    with pytest.raises(ValueError, match="tile_core_shape_yx"):
        derive_phase_five_halo_plan(
            _beam(),
            tile_core_shape_yx=tile_core_shape_yx,  # type: ignore[arg-type]
            maximum_task_pixels=200_000,
            measurement_config=_measurement_config(),
        )


def test_halo_plan_rejects_filter_read_over_global_task_cap() -> None:
    """The widest interior read is admitted before task allocation."""
    with pytest.raises(
        ValueError,
        match=r"matched-filter-seed.*104976.*100000",
    ):
        derive_phase_five_halo_plan(
            _beam(),
            tile_core_shape_yx=(256, 256),
            maximum_task_pixels=100_000,
            measurement_config=_measurement_config(),
        )


def test_halo_plan_rejects_measurement_read_over_its_stage_cap() -> None:
    """The measurement-specific cap governs its complete halo read."""
    with pytest.raises(
        ValueError,
        match=r"extended-measurement.*73984.*70000",
    ):
        derive_phase_five_halo_plan(
            _beam(),
            tile_core_shape_yx=(256, 256),
            maximum_task_pixels=200_000,
            measurement_config=replace(
                _measurement_config(),
                maximum_task_pixels=70_000,
            ),
        )


def test_halo_plan_rejects_nonreviewed_measurement_aperture() -> None:
    """The Rapthor profile cannot silently drift from 1.5 beam photometry."""
    with pytest.raises(ValueError, match=r"1\.5-beam aperture"):
        derive_phase_five_halo_plan(
            _beam(),
            tile_core_shape_yx=(256, 256),
            maximum_task_pixels=200_000,
            measurement_config=replace(
                _measurement_config(),
                aperture_radius_beams=2.0,
            ),
        )


@pytest.mark.parametrize("maximum_task_pixels", [True, 0, -1])
def test_halo_plan_rejects_invalid_global_task_cap(
    maximum_task_pixels: int,
) -> None:
    """The global task-pixel memory contract is explicit and positive."""
    with pytest.raises(ValueError, match="maximum_task_pixels"):
        derive_phase_five_halo_plan(
            _beam(),
            tile_core_shape_yx=(256, 256),
            maximum_task_pixels=maximum_task_pixels,
            measurement_config=_measurement_config(),
        )
