# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Count an image's bright local maxima, an upper estimate of its sources.

A published source has a peak at least the detection threshold times the
local noise above the background, so the pixels that are the highest of
their 3x3 neighbourhood and that far above a block's median bound the
sources a run can publish. The image is taken in blocks of
:data:`BLOCK_PIXELS` a side, so the count needs no image-sized array; each
block's noise is its valid pixels' 3-sigma-clipped standard deviation,
lowered to the image's typical block noise where the block's is higher.

These kernels estimate memory before an analysis, not sources: a noise
peak counts as a source would, so the count errs high.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from astropy.stats import sigma_clipped_stats
from scipy import ndimage

BLOCK_PIXELS = 512
"""The side of a noise block, in pixels.

On the quick check's `varying-noise` case, 150-pixel blocks, the RMS box
Rapthor passes to PyBDSF, read faint sources' own emission as noise and
counted fewer peaks than the sources published; 512-pixel blocks bounded
the sources of every quick-check, agreement and benchmark case (plan
task 77).
"""
MINIMUM_BLOCK_SAMPLES = 64
"""Valid pixels a block needs before its own noise is measured."""
_CLIPPING_SIGMA = 3.0
_CLIPPING_ITERATIONS = 10


@dataclass(frozen=True, slots=True)
class BlockNoise:
    """A block's clipped median and standard deviation, in image units."""

    median: float
    sigma: float


def block_noise(
    values: npt.NDArray[np.float64], valid_pixels: npt.NDArray[np.bool_]
) -> BlockNoise | None:
    """Return a block's 3-sigma-clipped median and standard deviation.

    Returns ``None`` when fewer than :data:`MINIMUM_BLOCK_SAMPLES` pixels
    are valid or the clipped spread is not positive.
    """
    samples = values[valid_pixels]
    if samples.size < MINIMUM_BLOCK_SAMPLES:
        return None
    _, median, sigma = sigma_clipped_stats(
        samples, sigma=_CLIPPING_SIGMA, maxiters=_CLIPPING_ITERATIONS
    )
    if not (np.isfinite(sigma) and sigma > 0):
        return None
    return BlockNoise(median=float(median), sigma=float(sigma))


def reference_sigma(noises: Iterable[BlockNoise]) -> float | None:
    """Return the median of the blocks' noise, the image's typical noise.

    Returns ``None`` when no block measured its noise.
    """
    sigmas = [noise.sigma for noise in noises]
    return float(np.median(sigmas)) if sigmas else None


def peak_threshold(
    noise: BlockNoise, *, reference_sigma: float, detection_sigma: float
) -> float:
    """Return the value a block's peak must reach to count.

    It is the block's median plus ``detection_sigma`` times the lower of
    the block's noise and the image's typical noise: a block's spread is
    inflated by a bright source in it, or by a primary-beam correction's
    noisier edge, and the typical noise is too high for a quiet block.
    """
    return noise.median + detection_sigma * min(noise.sigma, reference_sigma)


def count_peaks(
    values: npt.NDArray[np.float64],
    valid_pixels: npt.NDArray[np.bool_],
    core: tuple[slice, slice],
    threshold: float,
) -> int:
    """Count the core's valid pixels that are 3x3 maxima at the threshold.

    A pixel counts when it is valid, no valid neighbour is higher and it is
    at least ``threshold``. The window around the core supplies the
    neighbours of its edge pixels; invalid pixels are no one's neighbour.
    Equal neighbours both count.
    """
    measured = np.where(valid_pixels, values, -np.inf)
    highest = ndimage.maximum_filter(
        measured, size=3, mode="constant", cval=-np.inf
    )
    peaks = valid_pixels & (measured == highest) & (measured >= threshold)
    return int(np.count_nonzero(peaks[core]))
