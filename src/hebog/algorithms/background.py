# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Robust serial background and RMS statistics for bounded window batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.stats import sigma_clip

from hebog.config import RmsWindowStatisticsConfig

_WINDOW_DIMENSIONS = 3
_STATISTIC_AXES = (-2, -1)


@dataclass(frozen=True, slots=True)
class RmsWindowStatistics:
    """Background and RMS estimates for a batch of independent windows."""

    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    available: npt.NDArray[np.bool_]
    valid_sample_count: npt.NDArray[np.int64]
    retained_sample_count: npt.NDArray[np.int64]


def _read_only(values: npt.NDArray[Any]) -> npt.NDArray[Any]:
    """Return an owned array that callers cannot mutate accidentally."""
    values.setflags(write=False)
    return values


def estimate_rms_window_statistics(
    windows: npt.NDArray[np.floating[Any]],
    valid_pixels: npt.NDArray[np.bool_],
    config: RmsWindowStatisticsConfig,
) -> RmsWindowStatistics:
    """Estimate robust background and RMS for a batch of 2-D windows.

    Non-finite or explicitly invalid pixels do not contribute. A window with
    too few retained samples has NaN estimates and ``available=False`` so a
    later interpolation stage can apply its documented fallback policy.
    """
    values = np.asarray(windows, dtype=np.float64)
    validity = np.asarray(valid_pixels, dtype=np.bool_)
    if values.ndim != _WINDOW_DIMENSIONS:
        raise ValueError(
            "RMS window values must be a three-dimensional "
            "(window, y, x) batch"
        )
    if min(values.shape) < 1:
        raise ValueError("RMS window batches and windows must be non-empty")
    if validity.shape != values.shape:
        raise ValueError(
            "RMS window values and valid pixels need the same shape"
        )

    effective_validity = validity & np.isfinite(values)
    valid_sample_count = np.count_nonzero(
        effective_validity,
        axis=_STATISTIC_AXES,
    ).astype(np.int64, copy=False)
    masked_values = np.ma.array(
        values,
        mask=~effective_validity,
        copy=True,
    )
    clipped = cast(
        np.ma.MaskedArray[Any, Any],
        sigma_clip(
            masked_values,
            sigma=config.clipping_sigma,
            maxiters=config.maximum_iterations,
            cenfunc="median",
            stdfunc="std",
            axis=_STATISTIC_AXES,
            masked=True,
            copy=True,
        ),
    )
    retained_sample_count = np.count_nonzero(
        ~np.ma.getmaskarray(clipped),
        axis=_STATISTIC_AXES,
    ).astype(np.int64, copy=False)
    available = retained_sample_count >= config.minimum_samples
    background = np.asarray(
        np.ma.median(clipped, axis=_STATISTIC_AXES).filled(np.nan),
        dtype=np.float64,
    )
    rms = np.asarray(
        np.ma.std(clipped, axis=_STATISTIC_AXES).filled(np.nan),
        dtype=np.float64,
    )
    background[~available] = np.nan
    rms[~available] = np.nan

    return RmsWindowStatistics(
        background=cast(npt.NDArray[np.float64], _read_only(background)),
        rms=cast(npt.NDArray[np.float64], _read_only(rms)),
        available=cast(npt.NDArray[np.bool_], _read_only(available)),
        valid_sample_count=cast(
            npt.NDArray[np.int64],
            _read_only(valid_sample_count),
        ),
        retained_sample_count=cast(
            npt.NDArray[np.int64],
            _read_only(retained_sample_count),
        ),
    )
