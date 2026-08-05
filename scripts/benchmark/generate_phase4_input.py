# pyright: reportUnknownArgumentType=false
"""Generate deterministic incremental Phase 4 performance workloads."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

PhaseFourProfile = Literal[
    "sparse",
    "normal",
    "dense",
    "blend-heavy",
    "fit-failure",
]

_PROFILES: tuple[PhaseFourProfile, ...] = (
    "sparse",
    "normal",
    "dense",
    "blend-heavy",
    "fit-failure",
)
_PROFILE_INDEX = {profile: index for index, profile in enumerate(_PROFILES)}
_NOISE_RMS = 0.0002
_BACKGROUND = -0.0001
_MINIMUM_SIZE = 32
_PATCH_RADIUS = 10


def _parse_args() -> argparse.Namespace:
    """Parse one deterministic Phase 4 workload request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--profile", required=True, choices=_PROFILES)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _population_count(size: int, profile: PhaseFourProfile) -> int:
    """Return a bounded population that spans setup- and fit-heavy work."""
    pixels = size * size
    if profile == "sparse":
        return 1
    if profile == "normal":
        return max(4, pixels // 500_000)
    if profile == "dense":
        return max(16, pixels // 100_000)
    return max(8, pixels // 150_000)


def _centres(size: int, count: int) -> tuple[tuple[int, int], ...]:
    """Return deterministic well-separated patch centres."""
    grid_side = int(np.ceil(np.sqrt(count)))
    margin = min(_PATCH_RADIUS + 3, max(4, size // 4))
    coordinates = np.linspace(
        margin,
        size - margin - 1,
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
) -> None:
    """Add one bounded Gaussian patch without an image-sized temporary."""
    size_y, size_x = values.shape
    centre_y, centre_x = centre_yx
    y_start = max(0, int(np.floor(centre_y)) - _PATCH_RADIUS)
    y_stop = min(size_y, int(np.floor(centre_y)) + _PATCH_RADIUS + 1)
    x_start = max(0, int(np.floor(centre_x)) - _PATCH_RADIUS)
    x_stop = min(size_x, int(np.floor(centre_x)) + _PATCH_RADIUS + 1)
    y, x = np.mgrid[y_start:y_stop, x_start:x_stop]
    sigma_y, sigma_x = sigma_yx
    values[y_start:y_stop, x_start:x_stop] += amplitude * np.exp(
        -0.5
        * (
            np.square((y - centre_y) / sigma_y)
            + np.square((x - centre_x) / sigma_x)
        )
    )


def _add_profile_sources(
    values: npt.NDArray[np.float64],
    profile: PhaseFourProfile,
) -> None:
    """Add compact, blended, or deliberately unfit morphology."""
    centres = _centres(
        values.shape[0],
        _population_count(values.shape[0], profile),
    )
    for index, (centre_y, centre_x) in enumerate(centres):
        amplitude = _NOISE_RMS * (12.0 + 3.0 * (index % 4))
        if profile == "blend-heavy":
            angle = np.deg2rad((index % 4) * 30.0)
            offset_y = 2.5 * np.sin(angle)
            offset_x = 2.5 * np.cos(angle)
            for sign, ratio in ((-1.0, 1.0), (1.0, 0.7)):
                _add_gaussian(
                    values,
                    centre_yx=(
                        centre_y + sign * offset_y,
                        centre_x + sign * offset_x,
                    ),
                    amplitude=amplitude * ratio,
                    sigma_yx=(3.4, 4.2),
                )
        elif profile == "fit-failure":
            x_start = max(0, centre_x - 3)
            x_stop = min(values.shape[1], centre_x + 4)
            values[centre_y, x_start:x_stop] += amplitude
        else:
            scale = 1.0 + 0.15 * (index % 3)
            _add_gaussian(
                values,
                centre_yx=(centre_y, centre_x),
                amplitude=amplitude,
                sigma_yx=(3.4 * scale, 4.2 * scale),
            )


def _generate_values(
    size: int,
    profile: PhaseFourProfile | str,
) -> npt.NDArray[np.float64]:
    """Return one deterministic performance-only compact field."""
    if size < _MINIMUM_SIZE:
        raise ValueError("Phase 4 benchmark size must be at least 32")
    normalized = profile
    if normalized not in _PROFILES:
        raise ValueError(f"unsupported Phase 4 profile: {profile}")
    typed_profile = cast(PhaseFourProfile, normalized)
    generator = np.random.default_rng(
        20260805 + size * 10 + _PROFILE_INDEX[typed_profile]
    )
    values = generator.normal(
        loc=_BACKGROUND,
        scale=_NOISE_RMS,
        size=(size, size),
    ).astype(np.float64)
    _add_profile_sources(values, typed_profile)
    return values


def _generate_input(
    path: Path,
    *,
    size: int,
    profile: PhaseFourProfile | str,
) -> None:
    """Write one celestial FITS image with fixed beam and WCS metadata."""
    values = _generate_values(size, profile)
    hdu = fits.PrimaryHDU(values)
    hdu.header["BUNIT"] = "Jy/beam"
    hdu.header["BMAJ"] = 0.01
    hdu.header["BMIN"] = 0.008
    hdu.header["BPA"] = 20.0
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
