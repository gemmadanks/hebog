"""Dask-aware radio-continuum source finding for SKA SDP pipelines."""

from importlib.metadata import PackageNotFoundError, version

from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest, SourceFinderResult
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    UnsupportedSourceFinderConfigurationError,
    find_sources,
)

try:
    __version__ = version("hebog")
except PackageNotFoundError:
    __version__ = "0.6.0"

__all__ = [
    "InvalidSourceFinderInputError",
    "SourceFinderConfig",
    "SourceFinderError",
    "SourceFinderImageTooLargeError",
    "SourceFinderOutputExistsError",
    "SourceFinderRequest",
    "SourceFinderResult",
    "UnsupportedSourceFinderConfigurationError",
    "__version__",
    "find_sources",
]
