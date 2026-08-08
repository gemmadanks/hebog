"""Analytic tests for Phase 5 serial scale-filter candidates."""

from __future__ import annotations

from typing import cast

import numpy as np
import pytest

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    FilterFamily,
    ResidualAtrousResult,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    build_residual_atrous_plan,
    build_scale_filter_bank,
    evaluate_residual_atrous,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
    reconstruct_significant_atrous,
)

_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
_FAMILIES: tuple[FilterFamily, ...] = (
    "beam-aware-matched-filter",
    "undecimated-wavelet",
)


def _beam() -> BeamShapePixels:
    """Return the Phase 5 development restoring beam."""
    return BeamShapePixels(
        major_fwhm_pixels=5.0,
        minor_fwhm_pixels=3.5,
        position_angle_degrees=20.0,
    )


@pytest.mark.parametrize(
    ("major", "minor", "angle", "message"),
    [
        (np.nan, 3.5, 20.0, "finite"),
        (5.0, 0.0, 20.0, "positive"),
        (3.5, 5.0, 20.0, "minor axis"),
    ],
)
def test_beam_shape_rejects_invalid_geometry(
    major: float,
    minor: float,
    angle: float,
    message: str,
) -> None:
    """Beam metadata cannot make filter geometry undefined."""
    with pytest.raises(ValueError, match=message):
        BeamShapePixels(major, minor, angle)


def _unit_flux_gaussian(
    shape_yx: tuple[int, int],
    *,
    centre_xy: tuple[float, float],
    scale_beams: float,
) -> np.ndarray:
    """Return one beam-aligned Gaussian with unit integrated flux."""
    y_grid, x_grid = np.indices(shape_yx, dtype=np.float64)
    x_offset = x_grid - centre_xy[0]
    y_offset = y_grid - centre_xy[1]
    angle = np.deg2rad(_beam().position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    major_offset = cosine * x_offset + sine * y_offset
    minor_offset = -sine * x_offset + cosine * y_offset
    major_sigma = _beam().major_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA
    minor_sigma = _beam().minor_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA
    peak_jy_per_beam = 1.0 / scale_beams**2
    return np.asarray(
        peak_jy_per_beam
        * np.exp(
            -0.5
            * (
                np.square(major_offset / major_sigma)
                + np.square(minor_offset / minor_sigma)
            )
        ),
        dtype=np.float64,
    )


def _evaluate(
    image: np.ndarray,
    *,
    family: FilterFamily,
    valid: np.ndarray | None = None,
    background: np.ndarray | None = None,
    minimum_support_fraction: float = 0.5,
) -> ScaleFilterBankResult:
    """Evaluate one candidate with explicit prepared Phase 2 products."""
    shape = image.shape
    bank = build_scale_filter_bank(
        _beam(),
        family=family,
        scales=((1, 1.0), (2, 2.0), (3, 4.0)),
        truncation_sigma=4.0,
        noise_correlation=_beam(),
    )
    prepared = prepare_scale_filter_inputs(
        image,
        np.ones(shape, dtype=np.bool_) if valid is None else valid,
        np.zeros(shape, dtype=np.float64)
        if background is None
        else background,
        np.full(shape, 0.01, dtype=np.float64),
    )
    return evaluate_scale_filter_bank(
        prepared,
        bank,
        minimum_support_fraction=minimum_support_fraction,
    )


@pytest.mark.parametrize("family", _FAMILIES)
@pytest.mark.parametrize(
    ("response_index", "scale_beams"),
    [(0, 1.0), (1, 2.0), (2, 4.0)],
)
def test_nominal_gaussian_has_unit_integrated_flux_response(
    family: FilterFamily,
    response_index: int,
    scale_beams: float,
) -> None:
    """Every candidate implements the frozen scale normalization."""
    centre = (64.0, 64.0)
    image = _unit_flux_gaussian(
        (129, 129),
        centre_xy=centre,
        scale_beams=scale_beams,
    )

    result = _evaluate(image, family=family)
    response = result.responses[response_index]

    assert response.response_jy_per_beam[64, 64] == pytest.approx(
        1.0,
        rel=2e-12,
        abs=2e-12,
    )
    assert response.scientifically_valid[64, 64]
    assert response.valid_support_fraction[64, 64] == pytest.approx(1.0)


@pytest.mark.parametrize("family", _FAMILIES)
def test_prepared_constant_and_affine_backgrounds_have_zero_response(
    family: FilterFamily,
) -> None:
    """The serial oracle reuses, rather than re-estimates, Phase 2 products."""
    y_grid, x_grid = np.indices((65, 67), dtype=np.float64)
    background = 3.0 + 0.02 * x_grid - 0.03 * y_grid

    result = _evaluate(
        background.copy(),
        family=family,
        background=background,
    )

    for response in result.responses:
        np.testing.assert_allclose(
            response.response_jy_per_beam[response.scientifically_valid],
            0.0,
            rtol=0.0,
            atol=1e-13,
        )


@pytest.mark.parametrize("family", _FAMILIES)
def test_masked_and_nan_support_is_renormalized_or_unavailable(
    family: FilterFamily,
) -> None:
    """Renormalize missing support or fail when it is insufficient."""
    centre = (48.0, 48.0)
    image = _unit_flux_gaussian(
        (97, 97),
        centre_xy=centre,
        scale_beams=2.0,
    )
    valid = np.ones(image.shape, dtype=np.bool_)
    valid[:, :47] = False
    image[~valid] = np.nan

    accepted = _evaluate(
        image,
        family=family,
        valid=valid,
        minimum_support_fraction=0.5,
    ).responses[1]
    refused = _evaluate(
        image,
        family=family,
        valid=valid,
        minimum_support_fraction=0.8,
    ).responses[1]

    assert accepted.scientifically_valid[48, 48]
    assert accepted.response_jy_per_beam[48, 48] == pytest.approx(
        1.0,
        rel=0.1,
    )
    assert 0.5 <= accepted.valid_support_fraction[48, 48] < 0.8
    assert not refused.scientifically_valid[48, 48]
    assert np.isnan(refused.response_jy_per_beam[48, 48])


@pytest.mark.parametrize("family", _FAMILIES)
def test_image_edge_response_is_corrected_when_support_is_sufficient(
    family: FilterFamily,
) -> None:
    """A clipped symmetric source retains flux and visible-support metadata."""
    image = _unit_flux_gaussian(
        (129, 129),
        centre_xy=(2.0, 64.0),
        scale_beams=4.0,
    )

    response = _evaluate(
        image,
        family=family,
        minimum_support_fraction=0.5,
    ).responses[2]

    assert response.scientifically_valid[64, 2]
    assert response.response_jy_per_beam[64, 2] == pytest.approx(
        1.0,
        rel=0.08,
    )
    assert 0.5 <= response.valid_support_fraction[64, 2] < 0.8


@pytest.mark.parametrize("family", _FAMILIES)
def test_separated_compact_sources_remain_two_scale_one_peaks(
    family: FilterFamily,
) -> None:
    """The smallest configured scale does not blend separated compact truth."""
    first_x = 42
    second_x = 62
    image = _unit_flux_gaussian(
        (105, 105),
        centre_xy=(float(first_x), 52.0),
        scale_beams=1.0,
    )
    image += _unit_flux_gaussian(
        image.shape,
        centre_xy=(float(second_x), 52.0),
        scale_beams=1.0,
    )

    response = _evaluate(image, family=family).responses[0]

    assert response.response_jy_per_beam[52, first_x] > 0.95
    assert response.response_jy_per_beam[52, second_x] > 0.95
    assert response.response_jy_per_beam[52, 52] < 0.25


def test_filter_plans_freeze_halos_dtype_noise_and_convolution_reuse() -> None:
    """Candidate structural costs and correlated-noise gains are explicit."""
    matched = build_scale_filter_bank(
        _beam(),
        family="beam-aware-matched-filter",
        scales=((1, 1.0), (2, 2.0), (3, 4.0)),
        truncation_sigma=4.0,
        noise_correlation=_beam(),
    )
    wavelet = build_scale_filter_bank(
        _beam(),
        family="undecimated-wavelet",
        scales=((1, 1.0), (2, 2.0), (3, 4.0)),
        truncation_sigma=4.0,
        noise_correlation=_beam(),
    )

    assert tuple(item.halo_pixels for item in matched.filters) == (9, 17, 34)
    assert wavelet.maximum_halo_pixels > matched.maximum_halo_pixels
    assert matched.dtype == "float64"
    assert wavelet.dtype == "float64"
    assert matched.convolution_count_per_evaluation == 9
    assert wavelet.convolution_count_per_evaluation == 11
    assert all(
        item.correlated_noise_gain > item.independent_noise_gain
        for item in matched.filters
    )
    assert max(item.truncation_fraction for item in matched.filters) <= np.exp(
        -8.0
    )
    assert all(
        not item.response_kernel.flags.writeable for item in matched.filters
    )


@pytest.mark.parametrize(
    ("scales", "message"),
    [
        ((), "at least one scale"),
        (((0, 1.0),), "orders must be positive"),
        (((2, 1.0), (1, 2.0)), "orders must be positive"),
        (((1, 1.0), (1, 2.0)), "orders must be positive"),
        (((1, 0.0),), "widths must be finite"),
        (((1, np.nan),), "widths must be finite"),
        (((1, 2.0), (2, 1.0)), "widths must be increasing"),
        (((1, 1.0), (2, 1.0)), "widths must be increasing"),
    ],
)
def test_filter_bank_rejects_noncanonical_scales(
    scales: tuple[tuple[int, float], ...],
    message: str,
) -> None:
    """Scale order and widths are stable cache and ownership identities."""
    with pytest.raises(ValueError, match=message):
        build_scale_filter_bank(
            _beam(),
            family="beam-aware-matched-filter",
            scales=scales,
        )


@pytest.mark.parametrize("truncation_sigma", [np.nan, 2.9, 8.1])
def test_filter_bank_rejects_unbounded_truncation(
    truncation_sigma: float,
) -> None:
    """Kernel support remains within the reviewed finite truncation range."""
    with pytest.raises(ValueError, match=r"within.*3, 8"):
        build_scale_filter_bank(
            _beam(),
            family="beam-aware-matched-filter",
            scales=((1, 1.0),),
            truncation_sigma=truncation_sigma,
        )


def test_filter_bank_rejects_unsupported_family() -> None:
    """Only the two governed Phase 5 candidates are accepted."""
    with pytest.raises(ValueError, match="unsupported"):
        build_scale_filter_bank(
            _beam(),
            family=cast(FilterFamily, "boxcar"),
            scales=((1, 1.0),),
        )


@pytest.mark.parametrize("family", _FAMILIES)
def test_serial_scale_filter_outputs_are_float64_and_read_only(
    family: FilterFamily,
) -> None:
    """One-tile outputs cannot be mutated or precision-downgraded silently."""
    image = np.zeros((33, 35), dtype=np.float32)

    result = _evaluate(image, family=family)

    assert result.temporary_plane_count >= 5
    assert result.maximum_workspace_bytes > image.nbytes
    for response in result.responses:
        assert response.response_jy_per_beam.dtype == np.float64
        assert response.effective_rms_jy_per_beam.dtype == np.float64
        assert not response.response_jy_per_beam.flags.writeable
        assert not response.effective_rms_jy_per_beam.flags.writeable


def test_residual_atrous_plan_freezes_standard_b3_bounds() -> None:
    """The corrective transform uses the reviewed sparse dyadic B3 plan."""
    plan = build_residual_atrous_plan(_beam(), noise_correlation=_beam())

    np.testing.assert_allclose(
        plan.base_kernel,
        np.asarray([1.0, 4.0, 6.0, 4.0, 1.0]) / 16.0,
    )
    assert plan.scale_dilations_pixels == (1, 2, 4)
    assert plan.scale_halo_pixels == (2, 6, 14)
    assert plan.maximum_halo_pixels == 14
    assert plan.convolution_count_per_evaluation == 12
    assert plan.temporary_plane_count == 7
    assert all(item.correlated_noise_gain > 0 for item in plan.scales)


def test_residual_atrous_preserves_affine_background_and_telescopes() -> None:
    """Adjacent smoothings cancel affine signal and reconstruct exactly."""
    y_grid, x_grid = np.indices((65, 67), dtype=np.float64)
    image = 3.0 + 0.02 * x_grid - 0.03 * y_grid
    prepared = prepare_scale_filter_inputs(
        image,
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape, dtype=np.float64),
        np.full(image.shape, 0.01, dtype=np.float64),
    )

    result = evaluate_residual_atrous(
        prepared,
        build_residual_atrous_plan(_beam(), noise_correlation=_beam()),
        minimum_support_fraction=0.5,
    )

    interior = np.s_[14:-14, 14:-14]
    for response in result.responses:
        np.testing.assert_allclose(
            response.response_jy_per_beam[interior],
            0.0,
            atol=2e-14,
        )
    np.testing.assert_allclose(
        result.reconstructed_signal_jy_per_beam[interior]
        + result.coarse_smoothing_jy_per_beam[interior],
        prepared.residual_jy_per_beam[interior],
        atol=2e-14,
    )


def test_residual_atrous_normalizes_mask_support_and_excludes_compact() -> (
    None
):
    """Invalid and accepted compact pixels do not enter smoothing."""
    image = _unit_flux_gaussian(
        (65, 65), centre_xy=(32.0, 32.0), scale_beams=1.0
    )
    valid = np.ones(image.shape, dtype=np.bool_)
    valid[:, :31] = False
    image[~valid] = np.nan
    compact = np.zeros(image.shape, dtype=np.bool_)
    compact[30:35, 30:35] = True
    prepared = prepare_scale_filter_inputs(
        image,
        valid,
        np.zeros(image.shape, dtype=np.float64),
        np.full(image.shape, 0.01, dtype=np.float64),
    )

    result = evaluate_residual_atrous(
        prepared,
        build_residual_atrous_plan(_beam(), noise_correlation=_beam()),
        minimum_support_fraction=0.5,
        accepted_compact_mask=compact,
    )

    assert not result.scientifically_valid[32, 32]
    assert np.isnan(result.responses[0].response_jy_per_beam[32, 32])
    assert result.responses[0].valid_support_fraction[32, 35] >= 0.5
    assert all(
        not response.response_jy_per_beam.flags.writeable
        for response in result.responses
    )


def test_residual_atrous_subtracts_an_accepted_compact_model() -> None:
    """A supplied compact model is removed before residual coefficients."""
    image = _unit_flux_gaussian(
        (65, 65), centre_xy=(32.0, 32.0), scale_beams=1.0
    )
    prepared = prepare_scale_filter_inputs(
        image,
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape, dtype=np.float64),
        np.full(image.shape, 0.01, dtype=np.float64),
    )
    plan = build_residual_atrous_plan(_beam(), noise_correlation=_beam())

    result = evaluate_residual_atrous(
        prepared,
        plan,
        minimum_support_fraction=0.5,
        accepted_compact_model=image,
    )

    for response in result.responses:
        np.testing.assert_allclose(
            response.response_jy_per_beam[response.scientifically_valid],
            0.0,
            atol=1e-15,
        )
    with pytest.raises(ValueError, match="subtracted or excluded"):
        evaluate_residual_atrous(
            prepared,
            plan,
            minimum_support_fraction=0.5,
            accepted_compact_model=image,
            accepted_compact_mask=np.zeros(image.shape, dtype=np.bool_),
        )


def test_residual_atrous_reconstruction_requires_adjacent_scale_support() -> (
    None
):
    """An isolated coefficient cannot become reconstructed source signal."""
    shape = (5, 5)

    def response(order: int, values: np.ndarray) -> ScaleFilterResponse:
        return ScaleFilterResponse(
            scale_order=order,
            nominal_scale_beam_fwhm=float(2 ** (order - 1)),
            response_jy_per_beam=values,
            effective_rms_jy_per_beam=np.ones(shape, dtype=np.float64),
            valid_support_fraction=np.ones(shape, dtype=np.float64),
            scientifically_valid=np.ones(shape, dtype=np.bool_),
        )

    first = np.zeros(shape, dtype=np.float64)
    second = np.zeros(shape, dtype=np.float64)
    third = np.zeros(shape, dtype=np.float64)
    first[2, 2:4] = (5.0, 3.5)
    second[2, 2:4] = (5.2, 3.2)
    third[1, 1] = 6.0
    result = ResidualAtrousResult(
        family="residual-b3-atrous",
        responses=(
            response(1, first),
            response(2, second),
            response(3, third),
        ),
        reconstructed_signal_jy_per_beam=np.zeros(shape, dtype=np.float64),
        coarse_smoothing_jy_per_beam=np.zeros(shape, dtype=np.float64),
        scientifically_valid=np.ones(shape, dtype=np.bool_),
        convolution_count=12,
        temporary_plane_count=7,
        maximum_workspace_bytes=1,
    )

    reconstruction = reconstruct_significant_atrous(
        result,
        detection_sigma=5.0,
        island_sigma=3.0,
    )

    assert reconstruction.support_mask[2, 2:4].all()
    assert reconstruction.signal_jy_per_beam[2, 2] == pytest.approx(10.2)
    assert reconstruction.signal_jy_per_beam[2, 3] == pytest.approx(6.7)
    assert not reconstruction.support_mask[1, 1]
    assert reconstruction.signal_jy_per_beam[1, 1] == 0.0
    with pytest.raises(ValueError, match="detection_sigma"):
        reconstruct_significant_atrous(
            result,
            detection_sigma=3.0,
            island_sigma=3.0,
        )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"valid_pixels": np.ones((4, 5), dtype=np.bool_)}, "same shape"),
        ({"background": np.zeros((4, 5))}, "same shape"),
        ({"rms": np.ones((4, 5))}, "same shape"),
        ({"valid_pixels": np.ones((5, 5), dtype=np.int8)}, "boolean"),
        ({"valid_pixels": np.ones((25,), dtype=np.bool_)}, "two-dimensional"),
        ({"image": np.ones((25,))}, "two-dimensional"),
        ({"image": np.ones((5, 5), dtype=np.bool_)}, "real numeric"),
        ({"image": np.ones((5, 5), dtype=np.complex128)}, "real numeric"),
    ],
)
def test_serial_scale_filter_rejects_invalid_array_contracts(
    replacement: dict[str, np.ndarray],
    message: str,
) -> None:
    """The oracle rejects broadcasting and invalid validity metadata."""
    arguments = {
        "image": np.ones((5, 5)),
        "valid_pixels": np.ones((5, 5), dtype=np.bool_),
        "background": np.zeros((5, 5)),
        "rms": np.ones((5, 5)),
    }
    arguments.update(replacement)
    bank = build_scale_filter_bank(
        _beam(),
        family="beam-aware-matched-filter",
        scales=((1, 1.0),),
    )

    with pytest.raises((TypeError, ValueError), match=message):
        prepared = prepare_scale_filter_inputs(**arguments)
        evaluate_scale_filter_bank(
            prepared,
            bank,
            minimum_support_fraction=0.5,
        )


@pytest.mark.parametrize("minimum_support_fraction", [np.nan, 0.0, 1.1])
def test_serial_scale_filter_rejects_invalid_support_threshold(
    minimum_support_fraction: float,
) -> None:
    """Support availability uses a finite fractional threshold."""
    prepared = prepare_scale_filter_inputs(
        np.ones((5, 5)),
        np.ones((5, 5), dtype=np.bool_),
        np.zeros((5, 5)),
        np.ones((5, 5)),
    )
    bank = build_scale_filter_bank(
        _beam(),
        family="beam-aware-matched-filter",
        scales=((1, 1.0),),
    )

    with pytest.raises(ValueError, match="within"):
        evaluate_scale_filter_bank(
            prepared,
            bank,
            minimum_support_fraction=minimum_support_fraction,
        )
