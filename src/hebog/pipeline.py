"""Scheduler-independent public source-finding API."""

from __future__ import annotations

from numbers import Integral
from pathlib import Path

from hebog.config import SourceFinderConfig
from hebog.data_models import (
    SourceFinderRequest,
    SourceFinderResult,
    SuppliedImageMetadata,
)
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


def expected_source_count(
    image_path: Path,
    *,
    detection_threshold_sigma: float,
    supplied_metadata: SuppliedImageMetadata | None = None,
) -> int:
    """Return an upper estimate of the sources ``find_sources`` publishes.

    Pass it to :func:`analysis_memory_bytes`. A deconvolution model's
    component list is no such estimate: it holds many components for each
    source. A published source peaks at least the detection threshold times
    the local noise above the background, so the estimate counts the pixels
    that are the highest of their 3x3 neighbourhood and at least
    ``detection_threshold_sigma`` times the noise above the median of their
    512-pixel block. A block's noise is its valid pixels' 3-sigma-clipped
    standard deviation, or the median of every block's if that is lower, so
    neither the bright sources in a block nor a primary-beam correction's
    noisier edges hide faint sources. A noise peak counts as a source would,
    so the estimate errs high; on plan task 77's 21 cases it bounded every
    published source count, at 1.0 to 21 times it: 1.1 to 1.9 times on the
    LOFAR and simulated SKA fields, and most where noise peaks sit on one
    wide source. The image is read twice in bounded blocks, so no
    image-sized array is held. An image ``find_sources`` refuses is
    refused in the same way before any pixel is read.

    Args:
        image_path: The FITS image ``find_sources`` will analyse.
        detection_threshold_sigma: The detection threshold the analysis
            will use, ``SourceFinderConfig.detection_threshold_sigma``.
        supplied_metadata: Values the header lacks, as the request gives
            them.

    Returns:
        The number of such peaks; 0 for an image with no measurable noise.

    Raises:
        ValueError: If the threshold is not finite and positive.
        InvalidSourceFinderInputError: If the image cannot be read as a
            FITS continuum image.
        UnsupportedSourceFinderConfigurationError: If ``find_sources``
            refuses the image's unit, frame or beam sampling.
        SourceFinderImageTooLargeError: If the image exceeds the size
            envelope ``find_sources`` admits.
    """
    from hebog.public_api import (  # noqa: PLC0415
        expected_source_count as _expected_source_count,
    )

    return _expected_source_count(
        image_path,
        detection_threshold_sigma=detection_threshold_sigma,
        supplied_metadata=supplied_metadata,
    )


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
            will hold, such as :func:`expected_source_count` makes from the
            image; the reservation is too small if more are found.

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
