"""Failure-safe materialization of final compact-plus-extended products."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass, fields
from pathlib import Path
from tempfile import TemporaryDirectory
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
    MaterializedProductConflictError,
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
        """Resolve aliases and require distinct filesystem destinations."""
        for field in fields(self):
            object.__setattr__(
                self, field.name, getattr(self, field.name).resolve()
            )
        paths = (
            self.catalogue,
            self.mask,
            self.diagnostics,
            self.rapthor_catalogue,
        )
        if len(set(paths)) != len(paths) or any(
            _same_file(path, other)
            for index, path in enumerate(paths)
            for other in paths[:index]
        ):
            raise ValueError("combined product paths must be distinct")


@dataclass(frozen=True, slots=True)
class MaterializedCombinedProducts:
    """Pipeline-neutral result plus the separate Rapthor catalogue view."""

    result: SourceFinderResult
    rapthor_catalogue: MaterializedProduct


def _same_file(first: Path, second: Path) -> bool:
    """Compare existing inodes, including aliases through hard links."""
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


def _staging_path(destination: Path, staging: ExitStack) -> Path:
    """Keep each staged file on its destination filesystem."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    directory = staging.enter_context(
        TemporaryDirectory(prefix=".hebog-combined-", dir=destination.parent)
    )
    return Path(directory) / destination.name


def _remove_created_product(
    destination: Path, identity: tuple[int, int]
) -> None:
    """Rollback only our published inode, never a replacement by a caller."""
    try:
        current = destination.lstat()
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == identity:
        destination.unlink()


def _publish_products(
    products: tuple[MaterializedProduct, ...],
    destinations: tuple[Path, ...],
    rollback: ExitStack,
) -> None:
    """Publish without clobbering existing files; roll back caught failures."""
    for product, destination in zip(products, destinations, strict=True):
        identity = product.path.stat()
        try:
            destination.hardlink_to(product.path)
        except FileExistsError:
            with destination.open("rb") as handle:
                matches = (
                    destination.stat().st_size == product.byte_count
                    and hashlib.file_digest(handle, "sha256").hexdigest()
                    == product.content_sha256
                )
            if not matches:
                raise MaterializedProductConflictError(
                    "destination contains different product bytes: "
                    f"{destination}"
                ) from None
        else:
            rollback.callback(
                _remove_created_product,
                destination,
                (identity.st_dev, identity.st_ino),
            )


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
    """Stage all products and roll back newly published files on failure.

    Destinations may span directories and filesystems. Hard-link publication
    requires filesystem support and never replaces existing bytes. The set is
    not crash-atomic or simultaneously visible across all destinations; a
    successful return is the completion boundary. RMS is only read and reused.
    """
    from hebog.adapters.rapthor_catalogue import (  # noqa: PLC0415
        write_rapthor_catalogue_fits,
    )

    rms_source = FitsProductImageSource(rms_product)
    if not _metadata_matches(metadata, rms_source.metadata()):
        raise ProductMaterializationError(
            "combined products must reuse an RMS plane with exact metadata"
        )
    destinations = (
        paths.catalogue,
        paths.mask,
        paths.diagnostics,
        paths.rapthor_catalogue,
    )
    if rms_product.path.resolve() in destinations or any(
        _same_file(rms_product.path, path) for path in destinations
    ):
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

    diagnostics = build_combined_diagnostics(
        run_id=run_id,
        combined=combined,
        rms_scientific_status=rms_product.scientific_status,
    )
    catalogue = combined.catalogue
    with ExitStack() as rollback:
        with ExitStack() as staging:
            catalogue_product = write_catalogue_fits_product(
                _staging_path(paths.catalogue, staging), catalogue
            )
            mask_product = write_mask_fits_product(
                _staging_path(paths.mask, staging),
                metadata,
                combine_source_filtering_mask_blocks(
                    compact_mask_row_blocks, extended_mask_row_blocks
                ),
            )
            diagnostics_product = write_diagnostics_product(
                _staging_path(paths.diagnostics, staging), diagnostics
            )
            rapthor_catalogue = write_rapthor_catalogue_fits(
                _staging_path(paths.rapthor_catalogue, staging), catalogue
            )
            staged_products = (
                catalogue_product,
                mask_product,
                diagnostics_product,
                rapthor_catalogue,
            )
            final_products = tuple(
                product.model_copy(update={"path": destination})
                for product, destination in zip(
                    staged_products, destinations, strict=True
                )
            )
            result = SourceFinderResult(
                run_id=run_id,
                catalogue=final_products[0],
                rms=rms_product,
                mask=final_products[1],
                diagnostics=final_products[2],
                source_count=len(catalogue.sources),
                gaussian_component_count=len(catalogue.gaussian_components),
                island_count=len(catalogue.islands),
                wall_seconds=wall_seconds,
            )
            _publish_products(staged_products, destinations, rollback)
            materialized = MaterializedCombinedProducts(
                result=result, rapthor_catalogue=final_products[3]
            )
        rollback.pop_all()
    return materialized
