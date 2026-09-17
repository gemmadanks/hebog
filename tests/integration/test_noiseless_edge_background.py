"""Independent finite edge blends must survive adaptive source protection."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from distributed import Client

from hebog import find_sources
from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.validation.datasets import (
    BeamMetadata,
    DatasetRecord,
    DatasetRole,
    ExpectedImageStatistics,
    RedistributionStatus,
    SyntheticNoiseCorrelation,
    SyntheticRecipe,
    SyntheticSource,
    WcsMetadata,
    generate_synthetic_image,
    recipe_sha256,
)
from hebog.validation.materialization import synthetic_fits_header


def edge_blend_input(directory: Path, noise_rms: float) -> Path:
    """Recreate the 2026-09-11 development case, not a campaign input.

    Two touching Gaussians sit near the image edge in a 512-by-512 image with
    beam-correlated noise, a 5.4-by-3.6-pixel beam and a rotated SIN WCS.
    """
    recipe = SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=3,
        seed=2026981103,
        shape_yx=(512, 512),
        background=0.0,
        noise_rms=noise_rms,
        sources=tuple(
            SyntheticSource(
                x_pixel=38.0 + 7 * member,
                y_pixel=45.0 + 1.5 * member,
                peak_flux_jy_per_beam=0.004,
                major_sigma_pixels=2.3,
                minor_sigma_pixels=1.6,
                rotation_degrees_counterclockwise_from_x=31.0,
            )
            for member in range(2)
        ),
        noise_correlation=SyntheticNoiseCorrelation(
            major_fwhm_pixels=5.4,
            minor_fwhm_pixels=3.6,
            position_angle_degrees=31.0,
        ),
    )
    dataset = DatasetRecord(
        identifier="edge-blend",
        role=DatasetRole.DEVELOPMENT,
        purpose="Edge blend with and without available noise.",
        provenance="Deterministic analytic Gaussian pair.",
        redistribution=RedistributionStatus.GENERATED_LOCALLY,
        beam=BeamMetadata(
            major_fwhm_pixels=5.4,
            minor_fwhm_pixels=3.6,
            position_angle_degrees=31.0,
        ),
        wcs=WcsMetadata(
            reference_pixel_xy=(256.0, 256.0),
            reference_sky_degrees=(180.0, -30.0),
            pixel_scale_degrees_xy=(-0.0004, 0.0004),
            rotation_degrees_counterclockwise=23.0,
        ),
        expected_statistics=ExpectedImageStatistics(
            background_jy_per_beam=0.0,
            noise_rms_jy_per_beam=noise_rms,
            finite_fraction=1.0,
        ),
        recipe=recipe,
        recipe_sha256=recipe_sha256(recipe),
    )
    image = generate_synthetic_image(recipe)
    assert image.shape == (512, 512) and np.isfinite(image).all()
    path = directory / "edge-blend.fits"
    fits.PrimaryHDU(image, synthetic_fits_header(dataset)).writeto(path)
    return path


@pytest.mark.integration
@pytest.mark.parametrize("noise_rms", (0.0, 1e-4))
def test_edge_blend_public_capture_matches_existing_dask(
    tmp_path: Path, noise_rms: float
) -> None:
    """Noise availability and real noisy sources survive both executors."""
    path = edge_blend_input(tmp_path, noise_rms)
    result = find_sources(
        SourceFinderRequest(path, tmp_path / "products", "edge-blend"),
        SourceFinderConfig(5.0, 3.0, 7),
        SerialExecutor(),
    )
    if noise_rms == 0:
        assert result.rms.scientific_status == "unavailable"
        assert np.isnan(np.asarray(fits.getdata(result.rms.path))).all()
        assert result.source_count == result.gaussian_component_count == 0
    else:
        assert result.rms.scientific_status == "valid"
        assert np.all(np.asarray(fits.getdata(result.rms.path)) > 0)
        # V12 already associates this connected blend; both fitted peaks
        # must remain measured rather than turning into unavailable rows.
        assert result.source_count == 1
        assert result.gaussian_component_count == 2
        components = read_catalogue_fits_product(
            result.catalogue
        ).gaussian_components
        positions = SkyCoord(
            [row.position.right_ascension_degrees for row in components],
            [row.position.declination_degrees for row in components],
            unit="deg",
            frame="icrs",
        )
        fitted_xy = np.column_stack(
            cast(
                tuple[np.ndarray, np.ndarray],
                WCS(fits.getheader(path)).celestial.world_to_pixel(positions),
            )
        )
        np.testing.assert_allclose(
            fitted_xy[np.argsort(fitted_xy[:, 0])],
            ((38.0, 45.0), (45.0, 46.5)),
            rtol=0,
            atol=0.5,
        )

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        distributed = find_sources(
            SourceFinderRequest(path, tmp_path / "dask", "edge-blend"),
            SourceFinderConfig(5.0, 3.0, 7),
            DaskExecutor(client),
        )
    assert distributed.rms.scientific_status == result.rms.scientific_status
    assert distributed.source_count == result.source_count
    assert (
        distributed.gaussian_component_count == result.gaussian_component_count
    )
    np.testing.assert_array_equal(
        fits.getdata(result.rms.path), fits.getdata(distributed.rms.path)
    )
    np.testing.assert_array_equal(
        fits.getdata(result.mask_path), fits.getdata(distributed.mask_path)
    )
    assert read_catalogue_fits_product(result.catalogue) == (
        read_catalogue_fits_product(distributed.catalogue)
    )
