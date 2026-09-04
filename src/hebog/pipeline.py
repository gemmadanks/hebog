"""Scheduler-independent public source-finding API."""

from __future__ import annotations

from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest, SourceFinderResult
from hebog.executors import Executor


class SourceFinderError(Exception):
    """Base class for failures at the public source-finding boundary."""


class SourceFinderOutputExistsError(SourceFinderError):
    """The caller-owned output destination already exists."""


class InvalidSourceFinderInputError(SourceFinderError):
    """The requested input cannot be read as a supported FITS image."""


class UnsupportedSourceFinderConfigurationError(SourceFinderError):
    """The requested science differs from the qualified Phase 5 profile."""


class SourceFinderImageTooLargeError(SourceFinderError):
    """An input exceeds the bounded Phase 5 scientific-preview envelope."""


def find_sources(
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    executor: Executor,
) -> SourceFinderResult:
    """Analyse one supported FITS image and atomically publish its products.

    The implementation is imported only when called so importing the public
    scheduler-independent API never loads a concrete I/O or scheduler layer.
    """
    from hebog.public_api import find_sources as _find_sources  # noqa: PLC0415

    return _find_sources(request, config, executor)
