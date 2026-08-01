# pyright: reportMissingTypeStubs=false
"""End-to-end contracts from completed Zarr generations to final FITS."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hebog.data_models import (
    CelestialWcs,
    ImageBounds,
    ImageMetadata,
    PartitionManifest,
    ProductChunk,
    RestoringBeam,
)
from hebog.io import (
    FitsProductImageSource,
    ZarrProductSink,
    write_mask_fits_product,
    write_rms_fits_product,
)

pytestmark = pytest.mark.integration


def _metadata(shape_yx: tuple[int, int]) -> ImageMetadata:
    """Return minimal physical metadata for one test image."""
    return ImageMetadata(
        shape_yx=shape_yx,
        unit="Jy/beam",
        beam=RestoringBeam(
            major_fwhm_degrees=0.01,
            minor_fwhm_degrees=0.008,
            position_angle_degrees=20.0,
        ),
        celestial_wcs=CelestialWcs(
            fits_header=(
                "WCSAXES =                    2\n"
                "CRPIX1  =                  1.0\n"
                "CRPIX2  =                  1.0\n"
                "CDELT1  =               -0.001\n"
                "CDELT2  =                0.001\n"
                "CUNIT1  = 'deg     '\n"
                "CUNIT2  = 'deg     '\n"
                "CTYPE1  = 'RA---SIN'\n"
                "CTYPE2  = 'DEC--SIN'\n"
                "CRVAL1  =                180.0\n"
                "CRVAL2  =                -30.0\n"
                "LONPOLE =                180.0\n"
                "LATPOLE =                -30.0\n"
                "MJDREF  =                  0.0\n"
                "RADESYS = 'ICRS    '"
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )


def _completed_products(
    root: Path,
    *,
    tile_core_shape_yx: tuple[int, int],
) -> tuple[ZarrProductSink, np.ndarray, np.ndarray]:
    """Publish deterministic RMS and mask chunks for one partition shape."""
    shape_yx = (5, 7)
    manifest = PartitionManifest.create(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=tile_core_shape_yx,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(root, manifest, generation_id="final-products")
    rms = np.arange(1, 1 + np.prod(shape_yx), dtype=np.float64).reshape(
        shape_yx
    )
    rms[0, 0] = np.nan
    mask = np.indices(shape_yx).sum(axis=0) % 2 == 0
    chunks: list[ProductChunk] = []
    for product_name, dtype in (
        ("rms", np.dtype("<f8")),
        ("mask", np.dtype(np.bool_)),
    ):
        sink.initialize_product(product_name=product_name, dtype=dtype)
        plane = rms if product_name == "rms" else mask
        for tile in manifest.tiles:
            bounds = tile.core_bounds
            values = np.ascontiguousarray(
                plane[
                    bounds.y_start : bounds.y_stop,
                    bounds.x_start : bounds.x_stop,
                ]
            )
            chunks.append(
                sink.write_chunk(
                    product_name=product_name,
                    tile=tile,
                    values=values,
                )
            )
    sink.publish_generation(
        product_names=("mask", "rms"),
        chunks=chunks,
    )
    return sink, rms, mask


@pytest.mark.parametrize("tile_core_shape_yx", [(8, 8), (3, 4)])
def test_completed_zarr_generation_streams_to_exact_final_fits_products(
    tmp_path: Path,
    tile_core_shape_yx: tuple[int, int],
) -> None:
    """One-tile and many-tile storage produce identical bounded products."""
    sink, expected_rms, expected_mask = _completed_products(
        tmp_path / "run.zarr",
        tile_core_shape_yx=tile_core_shape_yx,
    )
    metadata = _metadata(expected_rms.shape)
    row_budget = (
        min(tile_core_shape_yx[0], expected_rms.shape[0])
        * expected_rms.shape[1]
        * expected_rms.dtype.itemsize
    )

    rms_product = write_rms_fits_product(
        tmp_path / "rms.fits",
        metadata,
        sink.iter_completed_row_blocks(
            "rms",
            max_block_bytes=row_budget,
        ),
        dtype=expected_rms.dtype,
        scientific_status="valid",
    )
    mask_product = write_mask_fits_product(
        tmp_path / "mask.fits",
        metadata,
        sink.iter_completed_row_blocks(
            "mask",
            max_block_bytes=row_budget,
        ),
    )

    bounds = ImageBounds(0, expected_rms.shape[0], 0, expected_rms.shape[1])
    actual_rms = FitsProductImageSource(rms_product).read_window(bounds)
    actual_mask = FitsProductImageSource(mask_product).read_window(bounds)
    np.testing.assert_array_equal(actual_rms.values, expected_rms)
    np.testing.assert_array_equal(
        actual_rms.valid_pixels, np.isfinite(expected_rms)
    )
    np.testing.assert_array_equal(
        actual_mask.values.astype(np.bool_), expected_mask
    )
