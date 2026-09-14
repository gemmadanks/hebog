"""Image and product input/output boundaries."""

from hebog.data_models.partitioning import ImageBounds
from hebog.io.base import ImageMetadata, ImageSource, ImageWindow
from hebog.io.combined import (
    CombinedProductPaths,
    MaterializedCombinedProducts,
    materialize_combined_products,
)
from hebog.io.fits import (
    FitsImageSource,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
    celestial_wcs_from_metadata,
)
from hebog.io.materialization import (
    FitsProductImageSource,
    InvalidMaterializedProductError,
    MaterializedProductConflictError,
    ProductMaterializationError,
    UnsupportedMaterializedProductError,
    read_catalogue_fits_product,
    read_diagnostics_product,
    write_catalogue_fits_product,
    write_diagnostics_product,
    write_mask_fits_product,
    write_rms_fits_product,
)
from hebog.io.zarr import (
    InvalidProductChunkError,
    InvalidProductGenerationError,
    ProductChunkConflictError,
    ProductChunkError,
    ProductGenerationConflictError,
    ProductGenerationError,
    ZarrProductSink,
)

__all__ = [
    "CombinedProductPaths",
    "FitsImageSource",
    "FitsProductImageSource",
    "ImageBounds",
    "ImageMetadata",
    "ImageSource",
    "ImageWindow",
    "InvalidFitsImageError",
    "InvalidMaterializedProductError",
    "InvalidProductChunkError",
    "InvalidProductGenerationError",
    "MaterializedCombinedProducts",
    "MaterializedProductConflictError",
    "ProductChunkConflictError",
    "ProductChunkError",
    "ProductGenerationConflictError",
    "ProductGenerationError",
    "ProductMaterializationError",
    "UnsupportedFitsImageError",
    "UnsupportedMaterializedProductError",
    "ZarrProductSink",
    "celestial_wcs_from_metadata",
    "materialize_combined_products",
    "read_catalogue_fits_product",
    "read_diagnostics_product",
    "write_catalogue_fits_product",
    "write_diagnostics_product",
    "write_mask_fits_product",
    "write_rms_fits_product",
]
