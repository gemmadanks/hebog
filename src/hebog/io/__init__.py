"""FITS and catalogue input/output boundaries."""

from hebog.io.base import (
    ImageBounds,
    ImageMetadata,
    ImageSource,
    ImageWindow,
)
from hebog.io.fits import (
    FitsImageSource,
    InvalidFitsImageError,
    UnsupportedFitsImageError,
)

__all__ = [
    "FitsImageSource",
    "ImageBounds",
    "ImageMetadata",
    "ImageSource",
    "ImageWindow",
    "InvalidFitsImageError",
    "UnsupportedFitsImageError",
]
