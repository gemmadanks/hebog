# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Materialize governed synthetic datasets as radio-image FITS files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import numpy as np
from astropy.io import fits

from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.validation.datasets import (
    DatasetRecord,
    generate_synthetic_image,
    load_dataset_manifest,
)


def _celestial_linear_transform(
    dataset: DatasetRecord,
) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
    """Map pixel offsets to the synthetic celestial intermediate plane."""
    scale_x, scale_y = dataset.wcs.pixel_scale_degrees_xy
    rotation_radians = np.deg2rad(
        dataset.wcs.rotation_degrees_counterclockwise
    )
    cosine = float(np.cos(rotation_radians))
    sine = float(np.sin(rotation_radians))
    return np.asarray(
        [
            [scale_x * cosine, -scale_y * sine],
            [scale_x * sine, scale_y * cosine],
        ],
        dtype=np.float64,
    )


def _beam_header_values(dataset: DatasetRecord) -> tuple[float, float, float]:
    """Transform generator-v2 pixel-plane beam truth to celestial values."""
    scale_x, scale_y = dataset.wcs.pixel_scale_degrees_xy
    if dataset.recipe.generator_version == 1:
        return (
            dataset.beam.major_fwhm_pixels * abs(scale_x),
            dataset.beam.minor_fwhm_pixels * abs(scale_y),
            dataset.beam.position_angle_degrees,
        )

    beam_angle = np.deg2rad(dataset.beam.position_angle_degrees)
    beam_rotation = np.asarray(
        [
            [np.cos(beam_angle), -np.sin(beam_angle)],
            [np.sin(beam_angle), np.cos(beam_angle)],
        ],
        dtype=np.float64,
    )
    pixel_covariance = (
        beam_rotation
        @ np.diag(
            np.square(
                [
                    dataset.beam.major_fwhm_pixels,
                    dataset.beam.minor_fwhm_pixels,
                ]
            )
        )
        @ beam_rotation.T
    )
    linear_transform = _celestial_linear_transform(dataset)
    sky_covariance = linear_transform @ pixel_covariance @ linear_transform.T
    eigenvalues, eigenvectors = np.linalg.eigh(sky_covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    position_angle = (
        np.rad2deg(np.arctan2(major_vector[0], major_vector[1])) % 180.0
    )
    return (
        float(np.sqrt(eigenvalues[major_index])),
        float(np.sqrt(eigenvalues[minor_index])),
        float(position_angle),
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


def synthetic_fits_header(dataset: DatasetRecord) -> fits.Header:
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
    rotation_radians = np.deg2rad(
        dataset.wcs.rotation_degrees_counterclockwise
    )
    if rotation_radians != 0.0:
        cosine = float(np.cos(rotation_radians))
        sine = float(np.sin(rotation_radians))
        header["PC1_1"] = cosine
        header["PC1_2"] = -scale_y * sine / scale_x
        header["PC2_1"] = scale_x * sine / scale_y
        header["PC2_2"] = cosine
    beam_major, beam_minor, beam_position_angle = _beam_header_values(dataset)
    header["BMAJ"] = beam_major
    header["BMIN"] = beam_minor
    header["BPA"] = beam_position_angle
    header["RESTFRQ"] = 150_000_000.0
    header["HEBOGDS"] = dataset.identifier
    header["HEBOGRCP"] = dataset.recipe_sha256
    return header


def synthetic_image_metadata(dataset: DatasetRecord) -> ImageMetadata:
    """Return production metadata for one governed synthetic image."""
    header = synthetic_fits_header(dataset)
    return ImageMetadata(
        shape_yx=dataset.recipe.shape_yx,
        unit="Jy/beam",
        beam=RestoringBeam(
            major_fwhm_degrees=cast(float, header["BMAJ"]),
            minor_fwhm_degrees=cast(float, header["BMIN"]),
            position_angle_degrees=cast(float, header["BPA"]),
        ),
        celestial_wcs=CelestialWcs(
            fits_header=cast(
                str,
                header.tostring(
                    sep="\n",
                    endcard=False,
                    padding=False,
                ),
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=cast(float, header["RESTFRQ"]),
    )


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
    hdu = fits.PrimaryHDU(data=data, header=synthetic_fits_header(dataset))
    hdu.add_checksum(when="hebog deterministic dataset recipe")
    hdu.writeto(
        output_path,
        overwrite=overwrite,
    )
    return hashlib.sha256(output_path.read_bytes()).hexdigest()
