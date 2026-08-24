"""Atomic materialization of final compact-plus-extended products."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt

from hebog.algorithms.combined_products import (
    build_combined_diagnostics,
    combine_source_filtering_mask_blocks,
)
from hebog.data_models.catalogue_construction import (
    CompletedCombinedCatalogue,
)
from hebog.data_models.images import ImageMetadata
from hebog.data_models.source_finding import (
    MaterializedProduct,
    SourceFinderResult,
)
from hebog.io.fits import celestial_wcs_from_metadata
from hebog.io.materialization import (
    FitsProductImageSource,
    ProductMaterializationError,
    write_catalogue_fits_product,
    write_diagnostics_product,
    write_mask_fits_product,
)


@dataclass(frozen=True, slots=True)
class CombinedProductPaths:
    """Destinations for internal and Rapthor-compatible final products."""

    catalogue: Path
    mask: Path
    diagnostics: Path
    rapthor_catalogue: Path

    def __post_init__(self) -> None:
        """Require distinct destinations before any product is written."""
        paths = (
            self.catalogue,
            self.mask,
            self.diagnostics,
            self.rapthor_catalogue,
        )
        if len(set(paths)) != len(paths):
            raise ValueError("combined product paths must be distinct")


@dataclass(frozen=True, slots=True)
class MaterializedCombinedProducts:
    """Pipeline-neutral result plus the separate Rapthor catalogue view."""

    result: SourceFinderResult
    rapthor_catalogue: MaterializedProduct


def _metadata_matches(
    expected: ImageMetadata,
    actual: ImageMetadata,
) -> bool:
    """Compare physical metadata after FITS header normalization."""
    if (
        expected.shape_yx != actual.shape_yx
        or expected.unit != actual.unit
        or expected.beam != actual.beam
        or expected.reference_frequency_hz != actual.reference_frequency_hz
        or expected.celestial_wcs.coordinate_frame
        != actual.celestial_wcs.coordinate_frame
    ):
        return False
    height, width = expected.shape_yx
    pixels = np.asarray(
        (
            (0.0, 0.0),
            (float(width - 1), 0.0),
            (0.0, float(height - 1)),
            (float(width - 1), float(height - 1)),
            ((width - 1) / 2.0, (height - 1) / 2.0),
        ),
        dtype=np.float64,
    )
    expected_world = np.asarray(
        cast(Any, celestial_wcs_from_metadata(expected)).all_pix2world(
            pixels,
            0,
        ),
        dtype=np.float64,
    )
    actual_world = np.asarray(
        cast(Any, celestial_wcs_from_metadata(actual)).all_pix2world(
            pixels,
            0,
        ),
        dtype=np.float64,
    )
    return bool(
        np.allclose(expected_world, actual_world, rtol=0.0, atol=1e-12)
    )


def materialize_combined_products(  # noqa: PLR0913
    combined: CompletedCombinedCatalogue,
    *,
    metadata: ImageMetadata,
    rms_product: MaterializedProduct,
    compact_mask_row_blocks: Iterable[npt.ArrayLike],
    extended_mask_row_blocks: Iterable[npt.ArrayLike] | None,
    paths: CombinedProductPaths,
    run_id: str,
    wall_seconds: float,
) -> MaterializedCombinedProducts:
    """Publish a complete final product set using bounded mask row blocks."""
    from hebog.adapters.rapthor_catalogue import (  # noqa: PLC0415
        write_rapthor_catalogue_fits,
    )

    rms_source = FitsProductImageSource(rms_product)
    if not _metadata_matches(metadata, rms_source.metadata()):
        raise ProductMaterializationError(
            "combined products must reuse an RMS plane with exact metadata"
        )
    if rms_product.path in {
        paths.catalogue,
        paths.mask,
        paths.diagnostics,
        paths.rapthor_catalogue,
    }:
        raise ProductMaterializationError(
            "combined product paths must not replace the existing RMS plane"
        )
    accepted_extended_count = sum(
        len(disposition.association_ids)
        for disposition in combined.terminal_state.state.dispositions
        if disposition.status == "accepted-multiscale"
    )
    if combined.compact_only_preserved:
        if combined.source_provenance:
            raise ProductMaterializationError(
                "compact-only output cannot carry extended provenance"
            )
        if extended_mask_row_blocks is not None:
            raise ProductMaterializationError(
                "compact-only output cannot carry an extended mask"
            )
    elif len(combined.source_provenance) != accepted_extended_count:
        raise ProductMaterializationError(
            "continuum output provenance must cover accepted associations"
        )
    elif extended_mask_row_blocks is None:
        raise ProductMaterializationError(
            "continuum output requires extended accepted-support masks"
        )

    catalogue_product = write_catalogue_fits_product(
        paths.catalogue,
        combined.catalogue,
    )
    mask_product = write_mask_fits_product(
        paths.mask,
        metadata,
        combine_source_filtering_mask_blocks(
            compact_mask_row_blocks,
            extended_mask_row_blocks,
        ),
    )
    diagnostics = build_combined_diagnostics(
        run_id=run_id,
        combined=combined,
        rms_scientific_status=rms_product.scientific_status,
    )
    diagnostics_product = write_diagnostics_product(
        paths.diagnostics,
        diagnostics,
    )
    rapthor_catalogue = write_rapthor_catalogue_fits(
        paths.rapthor_catalogue,
        combined.catalogue,
    )
    catalogue = combined.catalogue
    result = SourceFinderResult(
        run_id=run_id,
        catalogue=catalogue_product,
        rms=rms_product,
        mask=mask_product,
        diagnostics=diagnostics_product,
        source_count=len(catalogue.sources),
        gaussian_component_count=len(catalogue.gaussian_components),
        island_count=len(catalogue.islands),
        wall_seconds=wall_seconds,
    )
    return MaterializedCombinedProducts(
        result=result,
        rapthor_catalogue=rapthor_catalogue,
    )
