# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Raise a real image's noise to fill the source-count ladder.

The one-sector scaling plan measures both finders against the source count
at one image size. Real fields leave a gap between about 3,500 and 23,000
sources at 5,000 pixels a side, so the ladder's middle rungs raise the
noise of one deep window instead (decision of 20 October 2026): Gaussian
noise smoothed by the restoring beam, scaled so the window's robust RMS
grows by a set factor, drawn from a fixed seed. The sources, pixel scale,
beam and processing stay those of the real field; only the depth changes.
Nothing here runs at import.
"""

from __future__ import annotations

from math import sqrt
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field
from scipy.ndimage import gaussian_filter

# A Gaussian's full width at half maximum over its standard deviation.
_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * np.log(2.0))
# The median absolute deviation of Gaussian noise over its RMS.
_MAD_PER_RMS = 0.6744897501960817


class NoiseRung(BaseModel):
    """One rung: its case and how many times the base window's RMS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    noise_factor: float = Field(gt=1)


class LadderNoiseConfiguration(BaseModel):
    """The base window, the seed and the rungs raised from it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    base_case: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    seed: int = Field(ge=0)
    rungs: tuple[NoiseRung, ...] = Field(min_length=1)


def load_ladder_noise_configuration(path: Path) -> LadderNoiseConfiguration:
    """Read and validate the noise-raised rungs."""
    return LadderNoiseConfiguration.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def robust_rms(values: npt.NDArray[np.floating]) -> float:
    """Return the median absolute deviation of finite values, as an RMS.

    In a deep field the sources lift the plain RMS well above the noise;
    the median absolute deviation follows the noise.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError("an image with no finite pixel has no noise")
    return float(np.median(np.abs(finite - np.median(finite))) / _MAD_PER_RMS)


def raise_noise(
    values: npt.NDArray[np.float32],
    *,
    factor: float,
    beam_fwhm_pixels: float,
    seed: int,
) -> npt.NDArray[np.float32]:
    """Return ``values`` with their robust RMS raised ``factor`` times.

    White noise from ``seed`` is smoothed by a circular Gaussian of
    ``beam_fwhm_pixels``, the restoring beam's main lobe, scaled to unit
    RMS and added at ``sqrt(factor**2 - 1)`` times the image's robust RMS,
    so independent noise adds in quadrature to the original. The image's
    last two axes are its plane; blank (non-finite) pixels stay blank.

    Raises:
        ValueError: If ``factor`` is not above one or no pixel is finite.
    """
    if not factor > 1:
        raise ValueError("the noise factor must be above one")
    rms = robust_rms(values)
    white = np.random.default_rng(seed).standard_normal(values.shape[-2:])
    noise = gaussian_filter(white, sigma=beam_fwhm_pixels / _FWHM_PER_SIGMA)
    noise /= noise.std()
    added = (rms * sqrt(factor * factor - 1.0) * noise).astype(values.dtype)
    return values + added
