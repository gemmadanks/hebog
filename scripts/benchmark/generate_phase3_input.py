# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Generate a deterministic compact-source Phase 3 benchmark FITS image."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.validation.evidence import WorkloadClass

_NOISE_RMS = 0.0002
_BACKGROUND = -0.0001
_MINIMUM_SIZE = 32
_WORKLOAD_INDEX = {
    WorkloadClass.EMPTY_SPARSE: 1,
    WorkloadClass.NORMAL: 2,
    WorkloadClass.DENSE_EXTENDED: 3,
}


def _parse_args() -> argparse.Namespace:
    """Parse one deterministic benchmark input request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument(
        "--workload-class",
        required=True,
        choices=tuple(item.value for item in WorkloadClass),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _source_count(size: int, workload: WorkloadClass) -> int:
    """Return a log-ladder compact-source population for one tier."""
    pixels = size * size
    if workload is WorkloadClass.EMPTY_SPARSE:
        return 1
    if workload is WorkloadClass.NORMAL:
        return max(4, pixels // 500_000)
    return max(16, pixels // 4096)


def _add_compact_sources(
    values: npt.NDArray[np.float64],
    *,
    source_count: int,
) -> None:
    """Add bounded Gaussian patches without one full plane per source."""
    size = values.shape[0]
    grid_side = int(np.ceil(np.sqrt(source_count)))
    coordinates = np.linspace(8, size - 9, grid_side, dtype=np.float64)
    source_index = 0
    offsets = np.arange(-8, 9, dtype=np.float64)
    y_offset, x_offset = np.meshgrid(offsets, offsets, indexing="ij")
    for y_position in coordinates:
        for x_position in coordinates:
            if source_index >= source_count:
                return
            y_centre = round(y_position)
            x_centre = round(x_position)
            sigma_y = 1.3 + 0.3 * (source_index % 4)
            sigma_x = 1.1 + 0.2 * (source_index % 3)
            amplitude = _NOISE_RMS * (8.0 + 4.0 * (source_index % 5))
            patch = amplitude * np.exp(
                -0.5
                * (
                    np.square(y_offset / sigma_y)
                    + np.square(x_offset / sigma_x)
                )
            )
            values[
                y_centre - 8 : y_centre + 9,
                x_centre - 8 : x_centre + 9,
            ] += patch
            source_index += 1


def _generate_values(
    size: int,
    workload: WorkloadClass | str,
) -> npt.NDArray[np.float64]:
    """Return one deterministic performance-only compact field."""
    normalized_workload = WorkloadClass(workload)
    if size < _MINIMUM_SIZE:
        raise ValueError("Phase 3 benchmark size must be at least 32")
    generator = np.random.default_rng(
        20260801 + size * 10 + _WORKLOAD_INDEX[normalized_workload]
    )
    values = generator.normal(
        loc=_BACKGROUND,
        scale=_NOISE_RMS,
        size=(size, size),
    ).astype(np.float64)
    _add_compact_sources(
        values,
        source_count=_source_count(size, normalized_workload),
    )
    return values


def _generate_input(
    path: Path,
    *,
    size: int,
    workload: WorkloadClass | str,
) -> None:
    """Write one deterministic celestial radio-image FITS input."""
    values = _generate_values(size, workload)
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
    hdu.writeto(path, checksum=True)


def _sha256(path: Path) -> str:
    """Return one generated FITS file's content identity."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Generate one input and print its exact identity."""
    args = _parse_args()
    if args.output.exists() and not args.overwrite:
        raise ValueError(f"benchmark input already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _generate_input(
        args.output,
        size=args.size,
        workload=args.workload_class,
    )
    print(f"sha256:{_sha256(args.output)}")


if __name__ == "__main__":
    main()
