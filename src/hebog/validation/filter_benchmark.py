# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Prepare the inputs of a matched benchmark of Rapthor's filter step.

Plan task 23 times Rapthor's complete ``filter_skymodel`` step, Hebog's
native task against Rapthor's PyBDSF subprocess, on one sector in one
container. :func:`write_sector_inputs` turns one real image into the files
that step reads: the flat-noise and true-sky images in WSClean's four-axis
layout, the sector polygon, and WSClean-style true-sky and apparent
component lists.

Rapthor's WSClean cleans to 1 sigma only inside the previous cycle's island
mask (``-fits-mask``), so the component lists hold one point component on
every island pixel: at least ``island_sigma`` above the median and
8-connected to a pixel at least ``peak_sigma`` above it, sigma being the
image's clipped noise rather than either finder's. One image serves as both
of Rapthor's images, so the apparent fluxes equal the true ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.io import FitsImageSource
from hebog.validation.lsmtool_filter import sector_vertices, sky_model_text
from hebog.validation.rapthor_agreement import emission_pixels

FloatArray = npt.NDArray[np.float64]

FLAT_NOISE_IMAGE = "sector_1-MFS-image.fits"
"""WSClean's name for a sector's primary-beam-uncorrected image."""
TRUE_SKY_IMAGE = "sector_1-MFS-image-pb.fits"
"""WSClean's name for a sector's primary-beam-corrected image."""
APPARENT_SKY_MODEL = "sector_1-sources.txt"
"""WSClean's name for a sector's apparent component list."""
TRUE_SKY_MODEL = "sector_1-sources-pb.txt"
"""WSClean's name for a sector's primary-beam-corrected component list."""
VERTICES = "sector_1_vertices.npy"
"""Rapthor's name for a sector's polygon."""


@dataclass(frozen=True, slots=True)
class SectorInputs:
    """The files Rapthor's filter step reads for one sector."""

    directory: Path
    component_count: int
    shape_yx: tuple[int, int]

    @property
    def flat_noise_image_path(self) -> Path:
        """Return the flat-noise image."""
        return self.directory / FLAT_NOISE_IMAGE

    @property
    def true_sky_image_path(self) -> Path:
        """Return the true-sky image."""
        return self.directory / TRUE_SKY_IMAGE

    @property
    def apparent_sky_model_path(self) -> Path:
        """Return the apparent component list."""
        return self.directory / APPARENT_SKY_MODEL

    @property
    def true_sky_model_path(self) -> Path:
        """Return the true-sky component list."""
        return self.directory / TRUE_SKY_MODEL

    @property
    def vertices_path(self) -> Path:
        """Return the sector polygon."""
        return self.directory / VERTICES


def wsclean_layout_hdu(
    plane: npt.NDArray[np.floating], header: fits.Header, frequency_hz: float
) -> fits.PrimaryHDU:
    """Return one plane on WSClean's axes: RA, Dec, frequency and Stokes.

    The celestial axes, beam and brightness unit come from ``header``.
    """
    layout = WCS(header).celestial.to_header()
    layout.update(
        {
            "CTYPE3": "FREQ",
            "CRPIX3": 1.0,
            "CRVAL3": frequency_hz,
            "CDELT3": 1.0,
            "CUNIT3": "Hz",
            "CTYPE4": "STOKES",
            "CRPIX4": 1.0,
            "CRVAL4": 1.0,
            "CDELT4": 1.0,
        }
    )
    for keyword in ("BMAJ", "BMIN", "BPA", "BUNIT"):
        layout[keyword] = header[keyword]
    return fits.PrimaryHDU(
        data=np.asarray(plane)[np.newaxis, np.newaxis], header=layout
    )


def write_sector_inputs(
    image_path: Path,
    directory: Path,
    *,
    island_sigma: float,
    peak_sigma: float,
    margin_fraction: float,
) -> SectorInputs:
    """Write one sector's filter-step inputs from a real image.

    The polygon is the image inset by ``margin_fraction`` of each side.
    """
    metadata = FitsImageSource(image_path).metadata()
    with fits.open(image_path, mode="readonly") as hdus:
        header = hdus[0].header
        plane = np.asarray(hdus[0].data).squeeze()
    islands, fluxes = emission_pixels(
        plane.astype(np.float64),
        floor_sigma=island_sigma,
        seed_sigma=peak_sigma,
    )
    inputs = SectorInputs(
        directory=directory,
        component_count=len(islands),
        shape_yx=metadata.shape_yx,
    )
    directory.mkdir(parents=True, exist_ok=True)
    hdu = wsclean_layout_hdu(plane, header, metadata.reference_frequency_hz)
    hdu.writeto(inputs.flat_noise_image_path)
    hdu.writeto(inputs.true_sky_image_path)
    celestial = WCS(header).celestial
    positions = celestial.wcs_pix2world(
        np.column_stack([islands.columns, islands.rows]).astype(np.float64), 0
    )
    text = sky_model_text(
        [f"s{index}c0" for index in range(len(islands))],
        positions,
        fluxes.tolist(),
        metadata.reference_frequency_hz,
    )
    inputs.true_sky_model_path.write_text(text, encoding="utf-8")
    inputs.apparent_sky_model_path.write_text(text, encoding="utf-8")
    np.save(
        inputs.vertices_path,
        sector_vertices(celestial, metadata.shape_yx, margin_fraction),
    )
    return inputs
