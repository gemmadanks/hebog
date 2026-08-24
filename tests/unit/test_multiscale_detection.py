"""Analytic contracts for promoted residual multiscale segmentation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    PreparedScaleInputs,
    ResidualAtrousResult,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    detect_residual_multiscale_islands,
)
from hebog.config import ResidualMultiscaleDetectionConfig


def _config() -> ResidualMultiscaleDetectionConfig:
    """Return the promoted 5/3-sigma segmentation policy."""
    return ResidualMultiscaleDetectionConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_scale_support_fraction=0.5,
        minimum_island_area_beams=1.0,
    )


def _response(
    order: int,
    values: np.ndarray,
    *,
    support: np.ndarray | None = None,
    valid: np.ndarray | None = None,
) -> ScaleFilterResponse:
    """Build one calibrated synthetic scale response."""
    shape = values.shape
    return ScaleFilterResponse(
        scale_order=order,
        nominal_scale_beam_fwhm=float(2 ** (order - 1)),
        response_jy_per_beam=values,
        effective_rms_jy_per_beam=np.ones(shape, dtype=np.float64),
        valid_support_fraction=(
            np.ones(shape, dtype=np.float64) if support is None else support
        ),
        scientifically_valid=(
            np.ones(shape, dtype=np.bool_) if valid is None else valid
        ),
    )


def _inputs(
    direct_snr: np.ndarray,
    *,
    valid: np.ndarray | None = None,
) -> PreparedScaleInputs:
    """Use unit RMS so the residual plane is also direct SNR."""
    shape = direct_snr.shape
    return PreparedScaleInputs(
        residual_jy_per_beam=direct_snr,
        rms_jy_per_beam=np.ones(shape, dtype=np.float64),
        scientifically_valid=(
            np.ones(shape, dtype=np.bool_) if valid is None else valid
        ),
    )


def _filter_bank(
    responses: tuple[ScaleFilterResponse, ...],
) -> ScaleFilterBankResult:
    """Build the matched-filter seed-aid result."""
    return ScaleFilterBankResult(
        family="beam-aware-matched-filter",
        responses=responses,
        convolution_count=9,
        temporary_plane_count=7,
        maximum_workspace_bytes=1,
    )


def _atrous(
    responses: tuple[ScaleFilterResponse, ...],
) -> ResidualAtrousResult:
    """Build the residual B3 result consumed by segmentation."""
    shape = responses[0].response_jy_per_beam.shape
    return ResidualAtrousResult(
        family="residual-b3-atrous",
        responses=responses,
        reconstructed_signal_jy_per_beam=np.zeros(shape, dtype=np.float64),
        coarse_smoothing_jy_per_beam=np.zeros(shape, dtype=np.float64),
        scientifically_valid=np.ones(shape, dtype=np.bool_),
        convolution_count=12,
        temporary_plane_count=7,
        maximum_workspace_bytes=1,
    )


def _responses(
    values: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    support: np.ndarray | None = None,
    valid: np.ndarray | None = None,
) -> tuple[ScaleFilterResponse, ...]:
    """Build the canonical three-scale response sequence."""
    return tuple(
        _response(order, plane, support=support, valid=valid)
        for order, plane in enumerate(values, start=1)
    )


def test_multiscale_detection_uses_eight_connected_residual_growth() -> None:
    """One persistent scale seed owns diagonal 3-sigma residual support."""
    shape = (7, 7)
    direct = np.zeros(shape, dtype=np.float64)
    direct[2, 2] = 3.2
    direct[3, 3] = 3.4
    direct[4, 4] = 3.1
    seeded = np.zeros(shape, dtype=np.float64)
    seeded[2, 2] = 5.2
    zero = np.zeros(shape, dtype=np.float64)

    result = detect_residual_multiscale_islands(
        _inputs(direct),
        _filter_bank(_responses((zero, zero, zero))),
        _atrous(_responses((seeded, seeded, zero))),
        BeamShapePixels(1.0, 1.0, 0.0),
        _config(),
    )

    assert result.component_count == 1
    assert result.retained_mask[2, 2]
    assert result.retained_mask[3, 3]
    assert result.retained_mask[4, 4]
    assert result.component_labels[2, 2] == result.component_labels[4, 4]
    assert result.minimum_island_pixels == 2
    assert not result.combined_snr.flags.writeable
    assert not result.retained_mask.flags.writeable
    assert not result.component_labels.flags.writeable


def test_multiscale_detection_requires_area_or_direct_detection_seed() -> None:
    """A scale-only speck is rejected while a direct 5-sigma pixel survives."""
    shape = (7, 7)
    direct = np.zeros(shape, dtype=np.float64)
    direct[1, 1] = 3.2
    direct[5, 5] = 5.2
    seeded = np.zeros(shape, dtype=np.float64)
    seeded[1, 1] = 5.2
    zero = np.zeros(shape, dtype=np.float64)

    result = detect_residual_multiscale_islands(
        _inputs(direct),
        _filter_bank(_responses((zero, zero, zero))),
        _atrous(_responses((seeded, seeded, zero))),
        BeamShapePixels(2.0, 2.0, 0.0),
        _config(),
    )

    assert result.minimum_island_pixels == 5
    assert not result.retained_mask[1, 1]
    assert result.retained_mask[5, 5]
    assert result.component_count == 1


def test_multiscale_detection_freezes_edge_support_and_invalid_pixels() -> (
    None
):
    """Half-support edges pass; lower support and invalid pixels do not."""
    shape = (7, 7)
    direct = np.zeros(shape, dtype=np.float64)
    direct[2, :2] = 3.2
    direct[5, 4:6] = 3.2
    direct[0, 6] = 10.0
    valid = np.ones(shape, dtype=np.bool_)
    valid[0, 6] = False
    support = np.ones(shape, dtype=np.float64)
    support[2, 0] = 0.5
    support[5, 4] = np.nextafter(0.5, 0.0)
    valid_response = valid.copy()
    seeded = np.zeros(shape, dtype=np.float64)
    seeded[2, 0] = 5.2
    seeded[5, 4] = 5.2
    seeded[0, 6] = 10.0
    zero = np.zeros(shape, dtype=np.float64)
    atrous = _responses(
        (seeded, seeded, zero),
        support=support,
        valid=valid_response,
    )

    result = detect_residual_multiscale_islands(
        _inputs(direct, valid=valid),
        _filter_bank(_responses((zero, zero, zero), valid=valid_response)),
        _atrous(atrous),
        BeamShapePixels(1.0, 1.0, 0.0),
        _config(),
    )

    assert result.retained_mask[2, :2].all()
    assert not result.retained_mask[5, 4:6].any()
    assert not result.retained_mask[0, 6]
    assert np.isneginf(result.combined_snr[0, 6])


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"minimum_scale_support_fraction": 0.0}, "support fraction"),
        ({"minimum_scale_support_fraction": 1.1}, "support fraction"),
        ({"minimum_island_area_beams": np.nan}, "island area"),
        ({"minimum_island_area_beams": 0.0}, "island area"),
        ({"detection_threshold_sigma": np.nan}, "thresholds"),
        ({"island_threshold_sigma": 5.0}, "thresholds"),
        ({"connectivity": "four-neighbour"}, "eight-neighbour"),
        ({"persistence": "any-scale"}, "adjacent-scales"),
        ({"seed_growth": "scale-response"}, "original residual"),
        ({"subarea_island_policy": "reject"}, "direct detection"),
        ({"edge_support": "zero-pad"}, "normalized"),
        ({"invalid_pixels": "fill-zero"}, "excluded"),
    ],
)
def test_multiscale_detection_config_rejects_unreviewed_rules(
    replacement: dict[str, object],
    message: str,
) -> None:
    """Scientific topology cannot drift through an unreviewed option."""
    arguments: dict[str, object] = {
        "detection_threshold_sigma": 5.0,
        "island_threshold_sigma": 3.0,
        "minimum_scale_support_fraction": 0.5,
        "minimum_island_area_beams": 1.0,
    }
    arguments.update(replacement)

    with pytest.raises(ValueError, match=message):
        ResidualMultiscaleDetectionConfig(**arguments)  # type: ignore[arg-type]


def test_multiscale_detection_rejects_misaligned_planes() -> None:
    """Every prepared and scale plane must share one tile geometry."""
    shape = (3, 3)
    zero = np.zeros(shape, dtype=np.float64)
    responses = _responses((zero, zero, zero))
    prepared = _inputs(zero)
    beam = BeamShapePixels(1.0, 1.0, 0.0)

    with pytest.raises(ValueError, match=r"prepared.*same shape"):
        detect_residual_multiscale_islands(
            replace(
                prepared,
                rms_jy_per_beam=np.ones((2, 3), dtype=np.float64),
            ),
            _filter_bank(responses),
            _atrous(responses),
            beam,
            _config(),
        )

    short = np.zeros((2, 3), dtype=np.float64)
    with pytest.raises(ValueError, match=r"responses.*residual shape"):
        detect_residual_multiscale_islands(
            prepared,
            _filter_bank((_response(1, short),)),
            _atrous(responses),
            beam,
            _config(),
        )


def test_multiscale_detection_rejects_unreviewed_filter_families() -> None:
    """The matched seed aid and residual-B3 representation stay explicit."""
    shape = (3, 3)
    zero = np.zeros(shape, dtype=np.float64)
    responses = _responses((zero, zero, zero))
    matched = _filter_bank(responses)
    atrous = _atrous(responses)
    arguments = (
        _inputs(zero),
        matched,
        atrous,
        BeamShapePixels(1.0, 1.0, 0.0),
    )

    with pytest.raises(ValueError, match=r"seed aid.*matched filter"):
        detect_residual_multiscale_islands(
            arguments[0],
            replace(matched, family="undecimated-wavelet"),
            arguments[2],
            arguments[3],
            _config(),
        )
    with pytest.raises(ValueError, match=r"representation.*residual B3"):
        detect_residual_multiscale_islands(
            arguments[0],
            arguments[1],
            replace(atrous, family="not-b3"),
            arguments[3],
            _config(),
        )
