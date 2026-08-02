"""Dask-aware radio-continuum source finding for SKA SDP pipelines."""

from importlib.metadata import PackageNotFoundError, version

from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest, SourceFinderResult

try:
    __version__ = version("hebog")
except PackageNotFoundError:
    __version__ = "0.5.0"

__all__ = [
    "SourceFinderConfig",
    "SourceFinderRequest",
    "SourceFinderResult",
    "__version__",
]
