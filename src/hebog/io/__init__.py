"""FITS and catalogue input/output boundaries."""

from hebog.data_models.partitioning import ImageBounds
from hebog.io.base import ImageMetadata, ImageSource, ImageWindow
from hebog.io.fits import (
    FitsImageSource,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
    celestial_wcs_from_metadata,
)

__all__ = [
    "FitsImageSource",
    "ImageBounds",
    "ImageMetadata",
    "ImageSource",
    "ImageWindow",
    "InvalidFitsImageError",
    "UnsupportedFitsImageError",
    "celestial_wcs_from_metadata",
]
