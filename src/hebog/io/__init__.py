"""Image and product input/output boundaries."""

from hebog.data_models.partitioning import ImageBounds
from hebog.io.base import ImageMetadata, ImageSource, ImageWindow
from hebog.io.fits import (
    FitsImageSource,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
    celestial_wcs_from_metadata,
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
    "FitsImageSource",
    "ImageBounds",
    "ImageMetadata",
    "ImageSource",
    "ImageWindow",
    "InvalidFitsImageError",
    "InvalidProductChunkError",
    "InvalidProductGenerationError",
    "ProductChunkConflictError",
    "ProductChunkError",
    "ProductGenerationConflictError",
    "ProductGenerationError",
    "UnsupportedFitsImageError",
    "ZarrProductSink",
    "celestial_wcs_from_metadata",
]
