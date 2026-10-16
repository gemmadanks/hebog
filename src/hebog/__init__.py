"""A scalable radio-continuum source finder."""

from importlib.metadata import PackageNotFoundError, version

from hebog.config import SourceFinderConfig
from hebog.data_models import (
    SourceFinderRequest,
    SourceFinderResult,
    SuppliedImageMetadata,
)
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    SourceFinderStagingWarning,
    UnsupportedSourceFinderConfigurationError,
    analysis_memory_bytes,
    expected_source_count,
    find_sources,
)

try:
    __version__ = version("hebog")
except PackageNotFoundError:
    __version__ = "0.21.0"

__all__ = [
    "InvalidSourceFinderInputError",
    "SourceFinderConfig",
    "SourceFinderError",
    "SourceFinderImageTooLargeError",
    "SourceFinderOutputExistsError",
    "SourceFinderRequest",
    "SourceFinderResult",
    "SourceFinderStagingWarning",
    "SuppliedImageMetadata",
    "UnsupportedSourceFinderConfigurationError",
    "__version__",
    "analysis_memory_bytes",
    "expected_source_count",
    "find_sources",
]
