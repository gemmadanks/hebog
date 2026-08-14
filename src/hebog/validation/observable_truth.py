"""Prospective observable-domain truth measurements."""

from __future__ import annotations

from math import isfinite

import numpy as np
import numpy.typing as npt

_IMAGE_DIMENSIONS = 2


def observable_truth_integrated_flux_jy(
    signal_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
) -> float:
    """Integrate injected truth only where a finder can observe it.

    This prospective boundary prevents an edge- or mask-truncated source from
    being compared with flux outside the valid image domain.
    """
    signal = np.asarray(signal_jy_per_beam, dtype=np.float64)
    valid = np.asarray(valid_pixels)
    if (
        signal.ndim != _IMAGE_DIMENSIONS
        or valid.ndim != _IMAGE_DIMENSIONS
        or signal.shape != valid.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError(
            "truth signal and valid pixels must be aligned two-dimensional "
            "planes"
        )
    if (
        not isfinite(beam_major_fwhm_pixels)
        or not isfinite(beam_minor_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0.0
        or beam_minor_fwhm_pixels <= 0.0
    ):
        raise ValueError("truth beam axes must be finite and positive")
    observable_brightness = float(
        np.sum(signal[valid & np.isfinite(signal)], dtype=np.float64)
    )
    if not isfinite(observable_brightness) or observable_brightness <= 0.0:
        raise ValueError("truth must have positive observable flux")
    beam_area_pixels = (
        np.pi
        * beam_major_fwhm_pixels
        * beam_minor_fwhm_pixels
        / (4.0 * np.log(2.0))
    )
    return observable_brightness / beam_area_pixels
