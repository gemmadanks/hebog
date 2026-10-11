# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Compare one sector's Hebog and PyBDSF products in Rapthor's dual-run mode.

In dual-run mode Rapthor runs both finders on one sector, each under its
own output root, and keeps both product sets until it selects one.
:func:`compare_sector_products` reads the four files each finder wrote and
reports how they differ, bound to the exact bytes of all eight and to
Hebog's provenance. It reads both sets and changes neither.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import numpy as np
import numpy.typing as npt
from astropy import units
from astropy.coordinates import SkyCoord, match_coordinates_sky
from astropy.io import fits
from astropy.table import Table
from pydantic import BaseModel, ConfigDict

from hebog.adapters.rapthor import RapthorSourceFindingResult
from hebog.adapters.rapthor_catalogue import read_rapthor_catalogue_fits
from hebog.data_models import (
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
)
from hebog.io import read_diagnostics_product

# The RMS maps are compared on every sixteenth pixel of each axis, which
# holds a 20,000-pixel sector's sample to 1.6 million pixels.
_RMS_SAMPLE_STEP = 16
# Rows of a mask counted at once: 128 rows of a 20,000-pixel plane.
_MASK_BLOCK_ROWS = 128


@dataclass(frozen=True, slots=True)
class RapthorSectorProducts:
    """The four files Rapthor's filter step reads for one sector."""

    source_catalog_path: Path
    true_sky_rms_path: Path
    flat_noise_rms_path: Path
    mask_path: Path

    @classmethod
    def named(
        cls, output_root: Path, true_sky_image_path: Path
    ) -> RapthorSectorProducts:
        """Name them as Rapthor's PyBDSF step names them from its root."""
        directory = output_root.parent
        stem = output_root.name
        return cls(
            source_catalog_path=directory / f"{stem}.source_catalog.fits",
            true_sky_rms_path=directory / f"{stem}.true_sky_rms.fits",
            flat_noise_rms_path=directory / f"{stem}.flat_noise_rms.fits",
            mask_path=directory / f"{true_sky_image_path.name}.mask.fits",
        )

    @classmethod
    def of(cls, result: RapthorSourceFindingResult) -> RapthorSectorProducts:
        """Return the four files one Hebog run wrote."""
        return cls(
            source_catalog_path=result.source_catalog_path,
            true_sky_rms_path=result.true_sky_rms_path,
            flat_noise_rms_path=result.flat_noise_rms_path,
            mask_path=result.mask_path,
        )

    def paths(self) -> tuple[Path, Path, Path, Path]:
        """Return the catalogue, the two RMS maps and the mask, in order."""
        return (
            self.source_catalog_path,
            self.true_sky_rms_path,
            self.flat_noise_rms_path,
            self.mask_path,
        )


class ProductIdentity(BaseModel):
    """One product file's path and the exact bytes it held."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    byte_count: int
    sha256: str


class FinderProducts(BaseModel):
    """One finder's four files for the sector, and its source count."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_catalog: ProductIdentity
    true_sky_rms: ProductIdentity
    flat_noise_rms: ProductIdentity
    mask: ProductIdentity
    source_count: int


class RapthorDualRunReport(BaseModel):
    """How one sector's Hebog and PyBDSF products differ.

    Sources match when each is the other's nearest within
    ``match_radius_arcsec``, half the restoring beam's major axis. The flux
    ratio is Hebog's ``Total_flux`` over PyBDSF's, the median over matched
    sources; each RMS ratio is Hebog's over PyBDSF's, the median over pixels
    of a regular 16-pixel grid where both are finite and positive. A ratio
    with nothing to compare is ``None``. The mask counts are of nonzero
    pixels.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    hebog: FinderProducts
    pybdsf: FinderProducts
    hebog_provenance: PublicSourceFindingProvenance
    match_radius_arcsec: float
    matched_source_count: int
    median_total_flux_ratio: float | None
    true_sky_rms_median_ratio: float | None
    flat_noise_rms_median_ratio: float | None
    hebog_mask_pixel_count: int
    pybdsf_mask_pixel_count: int
    shared_mask_pixel_count: int
    schema_version: Literal[1] = 1


def compare_sector_products(
    hebog: RapthorSourceFindingResult,
    pybdsf: RapthorSectorProducts,
    report_path: Path,
) -> RapthorDualRunReport:
    """Report how one sector's Hebog and PyBDSF products differ.

    The report is written to ``report_path`` in one rename and returned.
    Both product sets are only read, so Rapthor can still select either.

    Raises:
        ValueError: If the two finders' RMS maps or masks are on different
            pixel grids, or Hebog's bundle holds no public diagnostics.
    """
    hebog_products = RapthorSectorProducts.of(hebog)
    diagnostics = read_diagnostics_product(
        hebog.products_directory / "diagnostics.json"
    )
    if not isinstance(diagnostics, PublicSourceFindingDiagnostics):
        raise ValueError("Hebog's bundle holds no public diagnostics")
    hebog_sources = _sources(
        read_rapthor_catalogue_fits(hebog_products.source_catalog_path)
    )
    pybdsf_sources = _sources(
        Table.read(pybdsf.source_catalog_path, format="fits", hdu=1)
    )
    radius_arcsec = (
        float(fits.getheader(hebog_products.true_sky_rms_path)["BMAJ"])
        * 3600.0
        / 2.0
    )
    matched = _mutual_matches(hebog_sources, pybdsf_sources, radius_arcsec)
    hebog_mask, pybdsf_mask, shared_mask = _mask_pixel_counts(
        hebog_products.mask_path, pybdsf.mask_path
    )
    report = RapthorDualRunReport(
        hebog=_finder_products(hebog_products, len(hebog_sources[0])),
        pybdsf=_finder_products(pybdsf, len(pybdsf_sources[0])),
        hebog_provenance=diagnostics.provenance,
        match_radius_arcsec=radius_arcsec,
        matched_source_count=len(matched[0]),
        median_total_flux_ratio=_median_ratio(
            hebog_sources[2][matched[0]], pybdsf_sources[2][matched[1]]
        ),
        true_sky_rms_median_ratio=_rms_median_ratio(
            hebog_products.true_sky_rms_path, pybdsf.true_sky_rms_path
        ),
        flat_noise_rms_median_ratio=_rms_median_ratio(
            hebog_products.flat_noise_rms_path, pybdsf.flat_noise_rms_path
        ),
        hebog_mask_pixel_count=hebog_mask,
        pybdsf_mask_pixel_count=pybdsf_mask,
        shared_mask_pixel_count=shared_mask,
    )
    temporary = report_path.with_name(f".{report_path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        temporary.replace(report_path)
    finally:
        temporary.unlink(missing_ok=True)
    return report


def _identity(path: Path) -> ProductIdentity:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(block)
            digest.update(block)
    return ProductIdentity(
        path=path.as_posix(), byte_count=byte_count, sha256=digest.hexdigest()
    )


def _finder_products(
    products: RapthorSectorProducts, source_count: int
) -> FinderProducts:
    return FinderProducts(
        source_catalog=_identity(products.source_catalog_path),
        true_sky_rms=_identity(products.true_sky_rms_path),
        flat_noise_rms=_identity(products.flat_noise_rms_path),
        mask=_identity(products.mask_path),
        source_count=source_count,
    )


Sources = tuple[
    npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]
]


def _sources(table: Table) -> Sources:
    """Return a catalogue's right ascensions, declinations and fluxes."""
    return (
        np.asarray(table["RA"], dtype=np.float64),
        np.asarray(table["DEC"], dtype=np.float64),
        np.asarray(table["Total_flux"], dtype=np.float64),
    )


def _mutual_matches(
    first: Sources, second: Sources, radius_arcsec: float
) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
    """Return the row pairs that are each other's nearest within a radius."""
    if len(first[0]) == 0 or len(second[0]) == 0:
        empty = np.empty(0, dtype=np.intp)
        return empty, empty
    first_positions = SkyCoord(first[0], first[1], unit=units.deg)
    second_positions = SkyCoord(second[0], second[1], unit=units.deg)
    nearest, separation, _ = match_coordinates_sky(
        first_positions, second_positions
    )
    reverse, _, _ = match_coordinates_sky(second_positions, first_positions)
    rows = np.arange(len(first[0]))
    mutual = (np.asarray(reverse)[np.asarray(nearest)] == rows) & (
        np.asarray(separation.to_value(units.arcsec)) <= radius_arcsec
    )
    return rows[mutual], np.asarray(nearest, dtype=np.intp)[mutual]


def _median_ratio(
    numerator: npt.NDArray[np.float64], denominator: npt.NDArray[np.float64]
) -> float | None:
    """Return the median ratio over values finite and positive in both."""
    usable = (
        np.isfinite(numerator)
        & np.isfinite(denominator)
        & (numerator > 0)
        & (denominator > 0)
    )
    if not usable.any():
        return None
    return float(np.median(numerator[usable] / denominator[usable]))


def _plane(data: Any) -> Any:
    """Return the image plane of a FITS array with leading axes of one."""
    return data[(0,) * (data.ndim - 2)]


def _rms_median_ratio(hebog: Path, pybdsf: Path) -> float | None:
    """Compare two RMS maps on a regular grid of their pixels."""
    with (
        fits.open(hebog, memmap=True) as hebog_image,
        fits.open(pybdsf, memmap=True) as pybdsf_image,
    ):
        hebog_plane = _plane(hebog_image[0].data)
        pybdsf_plane = _plane(pybdsf_image[0].data)
        if hebog_plane.shape != pybdsf_plane.shape:
            raise ValueError(
                "the two finders' RMS maps are on different pixel grids: "
                f"{hebog_plane.shape} and {pybdsf_plane.shape}"
            )
        grid = (
            slice(None, None, _RMS_SAMPLE_STEP),
            slice(None, None, _RMS_SAMPLE_STEP),
        )
        return _median_ratio(
            np.asarray(hebog_plane[grid], dtype=np.float64).ravel(),
            np.asarray(pybdsf_plane[grid], dtype=np.float64).ravel(),
        )


def _mask_rows(plane: Any) -> Iterator[npt.NDArray[np.bool_]]:
    for start in range(0, plane.shape[0], _MASK_BLOCK_ROWS):
        yield np.asarray(plane[start : start + _MASK_BLOCK_ROWS]) != 0


def _mask_pixel_counts(hebog: Path, pybdsf: Path) -> tuple[int, int, int]:
    """Count each mask's island pixels and those both hold, by row blocks."""
    with (
        fits.open(hebog, memmap=True) as hebog_image,
        fits.open(pybdsf, memmap=True) as pybdsf_image,
    ):
        hebog_plane = _plane(hebog_image[0].data)
        pybdsf_plane = _plane(pybdsf_image[0].data)
        if hebog_plane.shape != pybdsf_plane.shape:
            raise ValueError(
                "the two finders' masks are on different pixel grids: "
                f"{hebog_plane.shape} and {pybdsf_plane.shape}"
            )
        counts = [0, 0, 0]
        for hebog_rows, pybdsf_rows in zip(
            _mask_rows(hebog_plane), _mask_rows(pybdsf_plane), strict=True
        ):
            counts[0] += int(np.count_nonzero(hebog_rows))
            counts[1] += int(np.count_nonzero(pybdsf_rows))
            counts[2] += int(np.count_nonzero(hebog_rows & pybdsf_rows))
    return counts[0], counts[1], counts[2]
