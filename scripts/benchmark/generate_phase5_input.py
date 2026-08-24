# pyright: reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Generate deterministic incremental Phase 5 performance workloads."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from scipy.ndimage import gaussian_filter

PhaseFiveProfile = Literal["sparse", "normal", "extended"]

_PROFILES: tuple[PhaseFiveProfile, ...] = (
    "sparse",
    "normal",
    "extended",
)
_PROFILE_INDEX = {profile: index for index, profile in enumerate(_PROFILES)}
_NOISE_RMS = 0.0002
_BACKGROUND = -0.0001
_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))
_BEAM_MAJOR_SIGMA_PIXELS = 10.0 / _FWHM_PER_SIGMA
_BEAM_MINOR_SIGMA_PIXELS = 8.0 / _FWHM_PER_SIGMA
_MINIMUM_SIZE = 32


def _parse_args() -> argparse.Namespace:
    """Parse one deterministic Phase 5 workload request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--profile", required=True, choices=_PROFILES)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _population_count(size: int, profile: PhaseFiveProfile) -> int:
    """Return a bounded population for one morphology profile."""
    if profile == "sparse":
        return 1
    if profile == "normal":
        return max(4, size * size // 750_000)
    return max(3, size * size // 1_500_000)


def _centres(
    size: int,
    count: int,
    *,
    margin: int,
) -> tuple[tuple[int, int], ...]:
    """Return deterministic well-separated source centres."""
    grid_side = int(np.ceil(np.sqrt(count)))
    bounded_margin = min(margin, max(4, size // 4))
    coordinates = np.linspace(
        bounded_margin,
        size - bounded_margin - 1,
        grid_side,
        dtype=np.float64,
    )
    return tuple(
        (round(y), round(x)) for y in coordinates for x in coordinates
    )[:count]


def _add_gaussian(
    values: npt.NDArray[np.float64],
    *,
    centre_yx: tuple[float, float],
    amplitude: float,
    sigma_yx: tuple[float, float],
    truncation_sigma: float = 4.0,
) -> None:
    """Add one bounded Gaussian without an image-sized source temporary."""
    centre_y, centre_x = centre_yx
    sigma_y, sigma_x = sigma_yx
    radius_y = int(np.ceil(truncation_sigma * sigma_y))
    radius_x = int(np.ceil(truncation_sigma * sigma_x))
    y_start = max(0, int(np.floor(centre_y)) - radius_y)
    y_stop = min(values.shape[0], int(np.floor(centre_y)) + radius_y + 1)
    x_start = max(0, int(np.floor(centre_x)) - radius_x)
    x_stop = min(values.shape[1], int(np.floor(centre_x)) + radius_x + 1)
    y, x = np.mgrid[y_start:y_stop, x_start:x_stop]
    values[y_start:y_stop, x_start:x_stop] += amplitude * np.exp(
        -0.5
        * (
            np.square((y - centre_y) / sigma_y)
            + np.square((x - centre_x) / sigma_x)
        )
    )


def _add_profile_sources(
    values: npt.NDArray[np.float64],
    profile: PhaseFiveProfile,
) -> None:
    """Add compact or extended morphology to the common noise field."""
    if profile == "extended":
        centres = _centres(
            values.shape[0],
            _population_count(values.shape[0], profile),
            margin=75,
        )
        for index, centre in enumerate(centres):
            scale = 3.0 + 0.5 * (index % 3)
            _add_gaussian(
                values,
                centre_yx=centre,
                amplitude=_NOISE_RMS * (4.0 + 0.25 * (index % 2)),
                sigma_yx=(
                    _BEAM_MAJOR_SIGMA_PIXELS * scale,
                    _BEAM_MINOR_SIGMA_PIXELS * scale,
                ),
            )
        return
    centres = _centres(
        values.shape[0],
        _population_count(values.shape[0], profile),
        margin=16,
    )
    for index, centre in enumerate(centres):
        _add_gaussian(
            values,
            centre_yx=centre,
            amplitude=_NOISE_RMS * (12.0 + 3.0 * (index % 3)),
            sigma_yx=(
                _BEAM_MAJOR_SIGMA_PIXELS,
                _BEAM_MINOR_SIGMA_PIXELS,
            ),
        )


def _generate_correlated_noise(
    size: int,
    generator: np.random.Generator,
) -> npt.NDArray[np.float64]:
    """Generate beam-correlated noise with the declared marginal RMS."""
    white = generator.normal(size=(size, size)).astype(np.float64)
    correlated = np.asarray(
        gaussian_filter(
            white,
            sigma=(
                _BEAM_MAJOR_SIGMA_PIXELS / np.sqrt(2.0),
                _BEAM_MINOR_SIGMA_PIXELS / np.sqrt(2.0),
            ),
            mode="reflect",
        ),
        dtype=np.float64,
    )
    correlated -= float(np.mean(correlated, dtype=np.float64))
    standard_deviation = float(np.std(correlated, dtype=np.float64))
    if not np.isfinite(standard_deviation) or standard_deviation <= 0.0:
        raise ValueError("generated Phase 5 noise has no finite variance")
    correlated *= _NOISE_RMS / standard_deviation
    return correlated


def _generate_values(
    size: int,
    profile: PhaseFiveProfile | str,
) -> npt.NDArray[np.float64]:
    """Return one deterministic performance-only multiscale field."""
    if size < _MINIMUM_SIZE:
        raise ValueError("Phase 5 benchmark size must be at least 32")
    if profile not in _PROFILES:
        raise ValueError(f"unsupported Phase 5 profile: {profile}")
    typed_profile = profile
    generator = np.random.default_rng(
        20260824 + size * 10 + _PROFILE_INDEX[typed_profile]
    )
    values = _BACKGROUND + _generate_correlated_noise(size, generator)
    _add_profile_sources(values, typed_profile)
    return values


def _generate_input(
    path: Path,
    *,
    size: int,
    profile: PhaseFiveProfile | str,
) -> None:
    """Write one celestial FITS image with fixed beam and WCS metadata."""
    values = _generate_values(size, profile)
    hdu = fits.PrimaryHDU(values)
    hdu.header["BUNIT"] = "Jy/beam"
    hdu.header["BMAJ"] = 0.01
    hdu.header["BMIN"] = 0.008
    hdu.header["BPA"] = 0.0
    hdu.header["RESTFRQ"] = 150_000_000.0
    hdu.header["CTYPE1"] = "RA---SIN"
    hdu.header["CTYPE2"] = "DEC--SIN"
    hdu.header["CUNIT1"] = "deg"
    hdu.header["CUNIT2"] = "deg"
    hdu.header["CDELT1"] = -0.001
    hdu.header["CDELT2"] = 0.001
    hdu.header["CRPIX1"] = 1.0
    hdu.header["CRPIX2"] = 1.0
    hdu.header["CRVAL1"] = 180.0
    hdu.header["CRVAL2"] = -30.0
    hdu.header["HBGPROF"] = str(profile)
    hdu.writeto(path, checksum=True, overwrite=True)


def _sha256(path: Path) -> str:
    """Return one generated input's byte identity."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Generate one input while refusing accidental replacement."""
    args = _parse_args()
    if args.output.exists() and not args.overwrite:
        raise ValueError(f"benchmark input already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _generate_input(args.output, size=args.size, profile=args.profile)
    print(f"sha256:{_sha256(args.output)}")


if __name__ == "__main__":
    main()
