"""Scheduler-independent public source-finding API."""

from __future__ import annotations

from numbers import Integral

from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest, SourceFinderResult
from hebog.executors import Executor

# What one analysis holds in the process that runs it, as traced between its
# tasks with Hebog's modules imported: a fixed part, the records the passes
# keep for every published source, and a little per pixel. A least-squares
# fit over the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the
# dense ELAIS-N1 central 5,000 pixels, with and without a flat-noise image,
# gave 142 MiB, 42.4 KB a source and 0.17 bytes a pixel; these constants lie
# above every one of those runs (plan task 17).
_ANALYSIS_TRACED_BASE_BYTES = 152 * 1024 * 1024
_ANALYSIS_TRACED_BYTES_PER_SOURCE = 44 * 1024
_ANALYSIS_TRACED_PIXELS_PER_BYTE = 4
_HEADROOM_NUMERATOR, _HEADROOM_DENOMINATOR = 5, 4


class SourceFinderError(Exception):
    """Base class for failures at the public source-finding boundary."""


class SourceFinderOutputExistsError(SourceFinderError):
    """The output destination exists without this request's products."""


class InvalidSourceFinderInputError(SourceFinderError):
    """The requested input cannot be read as a supported FITS image."""


class UnsupportedSourceFinderConfigurationError(SourceFinderError):
    """The requested science cannot be executed by the public pipeline."""


class SourceFinderImageTooLargeError(SourceFinderError):
    """An input exceeds the public finder's bounded image-size envelope."""


class SourceFinderStagingWarning(UserWarning):
    """An earlier run left a hidden staging directory beside the output.

    A run that is killed cannot remove its staging directory. The next run
    to the same output removes one whose owner has provably stopped and
    leaves any other in place; it reports each with this warning.
    """


def find_sources(
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    executor: Executor,
) -> SourceFinderResult:
    """Analyse one supported FITS image and atomically publish its products.

    When the output already holds the products of a finished run of the
    same request, with the same run ID, inputs, configuration and science,
    they are returned without analysing the image again. A failed run
    raises only once no task it submitted is still running, and removes
    everything it staged. A killed run leaves a hidden staging directory,
    which the next run to the same output removes once its owner has
    provably stopped or reports with a ``SourceFinderStagingWarning``.

    The implementation is imported only when called so importing the public
    scheduler-independent API never loads a concrete I/O or scheduler layer.
    """
    from hebog.public_api import find_sources as _find_sources  # noqa: PLC0415

    return _find_sources(request, config, executor)


def analysis_memory_bytes(
    image_shape_yx: tuple[int, int], *, expected_sources: int
) -> int:
    """Return the memory one analysis holds in the process that runs it.

    ``find_sources`` keeps Hebog's modules, the records each pass returns
    for every source, and the products it publishes in the process that
    calls it, so what it holds grows with the sources it finds rather than
    with the image. Its tasks are not counted: each declares its own memory
    to the executor, which a ``DaskExecutor`` attaches to the task under
    the caller's memory resource. Reserve this amount for the task that
    calls ``find_sources``, for example under the same Dask resource. With
    a ``SerialExecutor`` or ``ThreadExecutor`` the tasks run in the calling
    process, so the memory they are admitted comes on top. A request with a
    flat-noise image is covered.

    Args:
        image_shape_yx: The input image's height and width in pixels.
        expected_sources: An upper estimate of the sources the catalogue
            will hold, such as a sky model's count for the field; the
            reservation is too small if more are found.

    Returns:
        A fixed amount, an amount per expected source and a byte for every
        four pixels, with a quarter of headroom, in bytes.

    Raises:
        ValueError: If a dimension is not a positive integer or the source
            count is not a non-negative integer.

    Examples:
        >>> analysis_memory_bytes(
        ...     (3_000, 4_000), expected_sources=10
        ... ) == analysis_memory_bytes((4_000, 3_000), expected_sources=10)
        True
    """
    for side in image_shape_yx:
        if (
            isinstance(side, bool)
            or not isinstance(side, Integral)
            or side < 1
        ):
            raise ValueError("image dimensions must be positive integers")
    if (
        isinstance(expected_sources, bool)
        or not isinstance(expected_sources, Integral)
        or expected_sources < 0
    ):
        raise ValueError("expected_sources must be a non-negative integer")
    height, width = image_shape_yx
    traced = (
        _ANALYSIS_TRACED_BASE_BYTES
        + _ANALYSIS_TRACED_BYTES_PER_SOURCE * int(expected_sources)
        + int(height) * int(width) // _ANALYSIS_TRACED_PIXELS_PER_BYTE
    )
    return -(-traced * _HEADROOM_NUMERATOR // _HEADROOM_DENOMINATOR)
