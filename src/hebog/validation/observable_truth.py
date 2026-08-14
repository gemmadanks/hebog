"""Prospective observable-domain truth measurements."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import numpy.typing as npt

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class ObservableTruthMeasurement:
    """One truth group's measurements inside the valid image domain."""

    integrated_flux_jy: float
    centroid_xy: tuple[float, float]
    declared_support_pixel_count: int
    observable_support_pixel_count: int
    observable_support_fraction: float


def _aligned_boolean_plane(
    values: npt.ArrayLike,
    shape: tuple[int, ...],
    *,
    name: str,
) -> npt.NDArray[np.bool_]:
    """Return one exact boolean plane aligned with the truth signal."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or plane.shape != shape
        or plane.dtype != np.bool_
    ):
        raise ValueError(
            f"truth signal and {name} must be aligned two-dimensional "
            f"planes with a boolean support mask for {name}"
        )
    return plane


def _truth_signal_and_valid_pixels(
    signal_jy_per_beam: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    """Validate the common observable-domain truth planes."""
    signal = np.asarray(signal_jy_per_beam, dtype=np.float64)
    if signal.ndim != _IMAGE_DIMENSIONS:
        raise ValueError(
            "truth signal and valid pixels must be aligned two-dimensional "
            "planes"
        )
    valid = _aligned_boolean_plane(
        valid_pixels,
        signal.shape,
        name="valid pixels",
    )
    return signal, valid


def _beam_area_pixels(
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
) -> float:
    """Return one finite positive Gaussian restoring-beam area."""
    if (
        not isfinite(beam_major_fwhm_pixels)
        or not isfinite(beam_minor_fwhm_pixels)
        or beam_major_fwhm_pixels <= 0.0
        or beam_minor_fwhm_pixels <= 0.0
    ):
        raise ValueError("truth beam axes must be finite and positive")
    return (
        np.pi
        * beam_major_fwhm_pixels
        * beam_minor_fwhm_pixels
        / (4.0 * np.log(2.0))
    )


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
    signal, valid = _truth_signal_and_valid_pixels(
        signal_jy_per_beam,
        valid_pixels,
    )
    observable_brightness = float(
        np.sum(signal[valid & np.isfinite(signal)], dtype=np.float64)
    )
    if not isfinite(observable_brightness) or observable_brightness <= 0.0:
        raise ValueError("truth must have positive observable flux")
    beam_area_pixels = _beam_area_pixels(
        beam_major_fwhm_pixels,
        beam_minor_fwhm_pixels,
    )
    return observable_brightness / beam_area_pixels


def measure_observable_truth(
    signal_jy_per_beam: npt.ArrayLike,
    declared_support: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
) -> ObservableTruthMeasurement:
    """Measure flux, centroid, and support on one observable truth domain.

    Integrated flux retains all finite injected signal on valid pixels. The
    centroid and support metadata use the declared scientific support after
    intersection with that same valid domain. Neither boundary depends on a
    finder's detected mask.
    """
    signal, valid = _truth_signal_and_valid_pixels(
        signal_jy_per_beam,
        valid_pixels,
    )
    support = _aligned_boolean_plane(
        declared_support,
        signal.shape,
        name="declared support",
    )
    declared_count = int(np.count_nonzero(support))
    if declared_count == 0:
        raise ValueError("truth must have a non-empty declared support")
    observable_support = support & valid & np.isfinite(signal)
    observable_count = int(np.count_nonzero(observable_support))
    if observable_count == 0:
        raise ValueError("truth must have a non-empty observable support")
    support_weights = signal[observable_support]
    support_brightness = float(np.sum(support_weights, dtype=np.float64))
    if not isfinite(support_brightness) or support_brightness <= 0.0:
        raise ValueError("truth support must have positive observable flux")
    y_pixels, x_pixels = np.nonzero(observable_support)
    centroid = (
        float(
            np.sum(x_pixels * support_weights, dtype=np.float64)
            / support_brightness
        ),
        float(
            np.sum(y_pixels * support_weights, dtype=np.float64)
            / support_brightness
        ),
    )
    return ObservableTruthMeasurement(
        integrated_flux_jy=observable_truth_integrated_flux_jy(
            signal,
            valid,
            beam_major_fwhm_pixels=beam_major_fwhm_pixels,
            beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        ),
        centroid_xy=centroid,
        declared_support_pixel_count=declared_count,
        observable_support_pixel_count=observable_count,
        observable_support_fraction=observable_count / declared_count,
    )
