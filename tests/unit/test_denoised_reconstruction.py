"""Signed wavelet denoising retains the coarse emission, not its negative."""

import numpy as np
import pytest

from hebog.algorithms import multiscale


def _transform(signal: np.ndarray) -> multiscale.ResidualAtrousResult:
    valid = np.ones(signal.shape, dtype=np.bool_)
    beam = multiscale.BeamShapePixels(4.0, 3.0, 20.0)
    return multiscale.evaluate_residual_atrous(
        multiscale.prepare_scale_filter_inputs(
            signal, valid, np.zeros_like(signal), np.ones_like(signal)
        ),
        multiscale.build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=0.5,
    )


def test_zero_shrinkage_recovers_original_not_unsharp_image() -> None:
    yy, xx = np.mgrid[:65, :71]
    signal = 7 * np.exp(-((xx - 35) ** 2 + (yy - 32) ** 2) / 30) - 2
    transformed = _transform(signal)
    reconstructed = multiscale.reconstruct_denoised_atrous(
        transformed, significance_sigma=0.0
    )
    valid = transformed.scientifically_valid
    np.testing.assert_allclose(
        reconstructed[valid], signal[valid], rtol=0, atol=1e-14
    )
    assert np.all(np.isnan(reconstructed[~valid]))
    assert not reconstructed.flags.writeable


@pytest.mark.parametrize("sign", (-1, 1))
def test_shrinkage_is_sign_symmetric_and_keeps_coarse_brightness(
    sign: int,
) -> None:
    yy, xx = np.mgrid[:65, :71]
    signal = sign * (2.0 + 0.1 * np.cos(xx) * np.sin(yy))
    transformed = _transform(signal)
    reconstructed = multiscale.reconstruct_denoised_atrous(
        transformed, significance_sigma=3.0
    )
    np.testing.assert_allclose(
        reconstructed,
        transformed.coarse_smoothing_jy_per_beam,
        rtol=0,
        atol=1e-14,
    )
    assert np.mean(reconstructed[transformed.scientifically_valid]) == (
        pytest.approx(sign * 2, abs=0.01)
    )


@pytest.mark.parametrize("sigma", (-1.0, np.nan, np.inf))
def test_invalid_shrinkage_fails_closed(sigma: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        multiscale.reconstruct_denoised_atrous(
            _transform(np.ones((25, 25))), significance_sigma=sigma
        )
