"""Image and product input/output boundaries."""

from hebog.data_models.partitioning import ImageBounds
from hebog.io.base import ImageMetadata, ImageSource, ImageWindow, ProductSink
from hebog.io.chunks import (
    FilesystemProductSink,
    InvalidProductChunkError,
    ProductChunkConflictError,
    ProductChunkError,
)
from hebog.io.fits import (
    FitsImageSource,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
    celestial_wcs_from_metadata,
)
from hebog.io.zarr import InvalidZarrProductChunkError, ZarrProductSink

__all__ = [
    "FilesystemProductSink",
    "FitsImageSource",
    "ImageBounds",
    "ImageMetadata",
    "ImageSource",
    "ImageWindow",
    "InvalidFitsImageError",
    "InvalidProductChunkError",
    "InvalidZarrProductChunkError",
    "ProductChunkConflictError",
    "ProductChunkError",
    "ProductSink",
    "UnsupportedFitsImageError",
    "ZarrProductSink",
    "celestial_wcs_from_metadata",
]
