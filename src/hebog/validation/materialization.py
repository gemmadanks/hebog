# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Materialize governed synthetic datasets as radio-image FITS files."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from astropy.io import fits

from hebog.validation.datasets import (
    DatasetRecord,
    generate_synthetic_image,
    load_dataset_manifest,
)


def _dataset_by_id(manifest_path: Path, dataset_id: str) -> DatasetRecord:
    """Resolve one unique checked-in dataset record."""
    manifest = load_dataset_manifest(manifest_path)
    matches = tuple(
        dataset
        for dataset in manifest.datasets
        if dataset.identifier == dataset_id
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected one dataset named {dataset_id!r}, found {len(matches)}"
        )
    return matches[0]


def _fits_header(dataset: DatasetRecord) -> fits.Header:
    """Translate canonical manifest metadata to a four-axis FITS header."""
    header = fits.Header()
    reference_x, reference_y = dataset.wcs.reference_pixel_xy
    sky_ra, sky_dec = dataset.wcs.reference_sky_degrees
    scale_x, scale_y = dataset.wcs.pixel_scale_degrees_xy
    header["BUNIT"] = "Jy/beam"
    header["RADESYS"] = "ICRS"
    header["EQUINOX"] = 2000.0
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CTYPE3"] = "FREQ"
    header["CTYPE4"] = "STOKES"
    header["CRPIX1"] = reference_x + 1.0
    header["CRPIX2"] = reference_y + 1.0
    header["CRPIX3"] = 1.0
    header["CRPIX4"] = 1.0
    header["CRVAL1"] = sky_ra
    header["CRVAL2"] = sky_dec
    header["CRVAL3"] = 150_000_000.0
    header["CRVAL4"] = 1.0
    header["CDELT1"] = scale_x
    header["CDELT2"] = scale_y
    header["CDELT3"] = 1_000_000.0
    header["CDELT4"] = 1.0
    header["BMAJ"] = dataset.beam.major_fwhm_pixels * abs(scale_x)
    header["BMIN"] = dataset.beam.minor_fwhm_pixels * abs(scale_y)
    header["BPA"] = dataset.beam.position_angle_degrees
    header["RESTFRQ"] = 150_000_000.0
    header["HEBOGDS"] = dataset.identifier
    header["HEBOGRCP"] = dataset.recipe_sha256
    return header


def materialize_dataset(
    manifest_path: Path,
    dataset_id: str,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> str:
    """Write one bounded deterministic recipe and return its file SHA-256."""
    dataset = _dataset_by_id(manifest_path, dataset_id)
    image = generate_synthetic_image(dataset.recipe)
    data = np.asarray(image[np.newaxis, np.newaxis, :, :], dtype=np.float32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(data=data, header=_fits_header(dataset))
    hdu.add_checksum(when="hebog deterministic dataset recipe")
    hdu.writeto(
        output_path,
        overwrite=overwrite,
    )
    return hashlib.sha256(output_path.read_bytes()).hexdigest()
