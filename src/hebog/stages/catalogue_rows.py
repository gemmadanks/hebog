# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Scheduler-facing rounds that measure one catalogue row per segment.

ADR-008's source-row round measures each segment inside the window holding
its exact support and its expanded aperture. Only the aperture expansion
crosses a segment's own bounds, and it reaches no further than the reviewed
radius, so the cores write it under that halo and every row after it is
bounded by the segment it describes. No round reduces anything globally.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from functools import partial
from numbers import Integral
from typing import Any, Literal, Protocol

import numpy as np
import numpy.typing as npt

from hebog.algorithms.astrometry import (
    celestial_wcs_from_header_text,
    local_tangent_plane_transforms_from_wcs,
    restoring_beams_in_icrs,
)
from hebog.algorithms.extended_measurement import (
    SegmentWindow,
    expand_detected_segment_labels,
    expand_source_measurement_labels,
)
from hebog.algorithms.label_groups import label_windows
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.images import RestoringBeam
from hebog.data_models.measurement_diagnostics import (
    SourcePositionDiagnostics,
)
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.executors.base import Executor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.science.catalogues import (
    SegmentPixels,
    SegmentRowMeasurement,
    measure_segment_row,
    measure_segment_row_pixels,
    moment_shape_fields_at,
    segment_local_rms,
    segment_local_rms_pixels,
    segment_moment,
    segment_moment_pixels,
    segment_row_at,
    unavailable_moment_shape_fields,
)
from hebog.science.models import CatalogueSource
from hebog.stages.batching import (
    batch_object_windows,
    map_round,
    read_pixels,
)

_PRODUCT_NAMES = ("aperture-labels",)


def segment_row_product_names() -> tuple[str, ...]:
    """Return the canonical published segment-row product set."""
    return _PRODUCT_NAMES


class _WindowReadable(Protocol):
    """Read bounded global image windows without scheduler state."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


class _CompletedProductSource(Protocol):
    """Read checksum-validated windows from one published generation."""

    @property
    def manifest(self) -> PartitionManifest:
        """Return the canonical partition the generation was written on."""
        ...

    def access_session(self) -> AbstractContextManager[None]:
        """Hold one bounded read session open for a batch of windows."""
        ...

    def read_generation(self) -> ProductGenerationManifest:
        """Return the published generation this source reads."""
        ...

    def read_completed_window(
        self,
        product_name: str,
        bounds: ImageBounds,
    ) -> npt.NDArray[np.generic]:
        """Read one checksum-validated bounded window."""
        ...


@dataclass(frozen=True, slots=True)
class SegmentRowStageConfig:
    """Reviewed row policy and the bounded task limits."""

    label_product_name: str
    centroid_product_name: str
    aperture_radius_pixels: int
    aperture_tie_policy: Literal["nearest-support", "canonical-source"]
    beam_area_pixels: float
    denoised_position_maximum_peak_to_mean_ratio: float
    with_position_diagnostics: bool
    maximum_tiles_per_batch: int
    maximum_objects_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before any product is initialized."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_objects_per_batch", self.maximum_objects_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.aperture_radius_pixels, bool)
            or not isinstance(self.aperture_radius_pixels, Integral)
            or self.aperture_radius_pixels < 0
        ):
            raise ValueError(
                "aperture_radius_pixels must be a non-negative integer"
            )
        if self.aperture_tie_policy not in {
            "nearest-support",
            "canonical-source",
        }:
            raise ValueError("segment aperture tie policy is unsupported")


@dataclass(frozen=True, slots=True)
class SegmentRowStageResult:
    """Published apertures, the rows they measure, and scalar evidence.

    ``local_rms_by_label`` holds the median local noise over each segment's
    exact owned support, for every segment the rounds observed rather than
    only the measurable ones: a catalogue row that no row measured can still
    be published from a fitted model, and it quotes the same noise.
    """

    generation: ProductGenerationManifest
    rows: tuple[CatalogueSource, ...]
    local_rms_by_label: Mapping[int, float]
    position_diagnostics: Mapping[int, SourcePositionDiagnostics]
    segment_count: int
    measured_segment_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_segment_read_pixels: int


@dataclass(frozen=True, slots=True)
class _CoreBatch:
    """One bounded coarse executor task over several cores."""

    partitions: tuple[TilePartition, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.partitions:
            raise ValueError("segment core batch must not be empty")


@dataclass(frozen=True, slots=True)
class _ApertureBatchResult:
    """Persisted aperture chunk identities from one bounded task."""

    product_chunks: tuple[ProductChunk, ...]


@dataclass(frozen=True, slots=True)
class _WindowBatchResult:
    """The bounds each core observes for every label it holds, and where."""

    observed: tuple[tuple[int, ImageBounds, str], ...]


@dataclass(frozen=True, slots=True)
class _Segment:
    """One segment and the window that measures it."""

    label_value: int
    bounds: ImageBounds


@dataclass(frozen=True, slots=True)
class _RowBatch:
    """One bounded coarse executor task over several segments."""

    segments: tuple[_Segment, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.segments:
            raise ValueError("segment row batch must not be empty")


@dataclass(frozen=True, slots=True)
class _RowBatchResult:
    """The rows, noise and diagnostics one batch of segments produced."""

    rows: tuple[tuple[int, CatalogueSource], ...]
    local_rms: tuple[tuple[int, float], ...]
    diagnostics: tuple[tuple[int, SourcePositionDiagnostics], ...]
    maximum_segment_read_pixels: int


@dataclass(frozen=True, slots=True)
class _WideSegmentCore:
    """One core and the wide segments it holds a part of."""

    partition: TilePartition
    label_values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _WideSegmentBatch:
    """One bounded coarse executor task over the cores of wide segments."""

    cores: tuple[_WideSegmentCore, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.cores:
            raise ValueError("wide segment batch must not be empty")


@dataclass(frozen=True, slots=True)
class _SegmentPiece:
    """One wide segment's pixels in one core, in raster order.

    A pixel is here when the segment holds it in its seeded ownership, its
    measured support or its aperture. ``raster_indices`` are global
    ``y * width + x`` positions, so pieces from several cores sort back into
    the order one window presents them in.
    """

    label_value: int
    raster_indices: npt.NDArray[np.int64]
    residual: npt.NDArray[np.float64]
    position_signal: npt.NDArray[np.float64]
    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    valid: npt.NDArray[np.bool_]
    owned: npt.NDArray[np.bool_]
    labelled: npt.NDArray[np.bool_]
    aperture: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class _WideSegmentResult:
    """The wide segments' pixels one batch of cores held."""

    pieces: tuple[_SegmentPiece, ...]
    tile_ids: tuple[str, ...]
    maximum_core_read_pixels: int


def _core_batches(
    partitions: tuple[TilePartition, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_CoreBatch, ...]:
    """Group cores into bounded coarse tasks."""
    return tuple(
        _CoreBatch(
            partitions=tuple(
                partitions[start : start + maximum_tiles_per_batch]
            )
        )
        for start in range(0, len(partitions), maximum_tiles_per_batch)
    )


def _measurable_window(
    bounds: ImageBounds,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
]:
    """Read one window's background, residual and measurable pixels."""
    window = source.read_window(bounds)
    if window.bounds != bounds:
        raise ValueError("image source returned different segment bounds")
    background = np.asarray(
        background_rms_source.read_completed_window("background", bounds),
        dtype=np.float64,
    )
    valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    residual = np.asarray(window.values, dtype=np.float64) - background
    return background, residual, valid


def _publish_apertures(  # noqa: PLR0913
    batch: _CoreBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    label_source: _CompletedProductSource,
    config: SegmentRowStageConfig,
    image_shape_yx: tuple[int, int],
    sink: ZarrProductSink,
) -> _ApertureBatchResult:
    """Expand each core's segment apertures under the reviewed radius.

    An aperture reaches no further than the radius, so every seed that can
    own a core pixel lies inside the core read plus that halo, and the tie
    towards the smaller canonical label is decided the same way in a window
    as it is over the plane.
    """
    expand = (
        expand_source_measurement_labels
        if config.aperture_tie_policy == "canonical-source"
        else expand_detected_segment_labels
    )
    with (
        background_rms_source.access_session(),
        detection_source.access_session(),
        label_source.access_session(),
        sink.access_session(),
    ):
        chunks: list[ProductChunk] = []
        for partition in batch.partitions:
            core = partition.core_bounds
            read = core.expanded(config.aperture_radius_pixels, image_shape_yx)
            _, residual, valid = _measurable_window(
                read,
                source=source,
                background_rms_source=background_rms_source,
                detection_source=detection_source,
            )
            apertures = expand(
                np.asarray(
                    label_source.read_completed_window(
                        config.label_product_name,
                        read,
                    ),
                    dtype=np.int32,
                ),
                valid & np.isfinite(residual),
                radius_pixels=config.aperture_radius_pixels,
            )
            chunks.append(
                sink.write_chunk(
                    product_name="aperture-labels",
                    tile=partition,
                    values=np.asarray(
                        apertures[_crop(read, core)], dtype=np.int32
                    ),
                )
            )
        return _ApertureBatchResult(product_chunks=tuple(chunks))


def _crop(read: ImageBounds, window: ImageBounds) -> tuple[slice, slice]:
    """Return the slices selecting one window inside a wider read."""
    return (
        slice(window.y_start - read.y_start, window.y_stop - read.y_start),
        slice(window.x_start - read.x_start, window.x_stop - read.x_start),
    )


def _label_bounds(
    labels: npt.NDArray[np.int32],
    partition: TilePartition,
) -> tuple[tuple[int, ImageBounds, str], ...]:
    """Return the global bounds each label occupies inside one core."""
    bounds = partition.core_bounds
    return tuple(
        (
            index + 1,
            ImageBounds(
                bounds.y_start + window[0].start,
                bounds.y_start + window[0].stop,
                bounds.x_start + window[1].start,
                bounds.x_start + window[1].stop,
            ),
            partition.tile_id,
        )
        for index, window in enumerate(label_windows(labels))
        if window is not None
    )


def _scan_windows(
    batch: _CoreBatch,
    *,
    label_source: _CompletedProductSource,
    aperture_source: _CompletedProductSource,
    label_product_name: str,
) -> _WindowBatchResult:
    """Observe the bounds each core holds for its segments and apertures."""
    with label_source.access_session(), aperture_source.access_session():
        observed: list[tuple[int, ImageBounds, str]] = []
        for partition in batch.partitions:
            core = partition.core_bounds
            for product_source, product_name in (
                (label_source, label_product_name),
                (aperture_source, "aperture-labels"),
            ):
                observed.extend(
                    _label_bounds(
                        np.asarray(
                            product_source.read_completed_window(
                                product_name, core
                            ),
                            dtype=np.int32,
                        ),
                        partition,
                    )
                )
        return _WindowBatchResult(observed=tuple(observed))


def _union(first: ImageBounds | None, second: ImageBounds) -> ImageBounds:
    """Return the smallest bound holding both observations."""
    if first is None:
        return second
    return ImageBounds(
        min(first.y_start, second.y_start),
        max(first.y_stop, second.y_stop),
        min(first.x_start, second.x_start),
        max(first.x_stop, second.x_stop),
    )


def _row_batches(
    segments: tuple[_Segment, ...],
    *,
    maximum_objects_per_batch: int,
    maximum_batch_read_pixels: int,
) -> tuple[_RowBatch, ...]:
    """Group segments so one read serves several, within both budgets.

    Raises:
        ValueError: If one segment's own window exceeds the read budget. No
            admission bounds a segment's area, so such a segment is measured
            from its cores instead.
    """
    return tuple(
        _RowBatch(segments=batch.objects, read_bounds=batch.read_bounds)
        for batch in batch_object_windows(
            sorted(
                segments,
                key=lambda item: (item.bounds.y_start, item.bounds.x_start),
            ),
            window=lambda segment: segment.bounds,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            maximum_objects_per_batch=maximum_objects_per_batch,
        )
    )


@dataclass(frozen=True, slots=True)
class _RowRead:
    """One batch's planes, read once and cropped per segment."""

    bounds: ImageBounds
    background: npt.NDArray[np.float64]
    residual: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    valid: npt.NDArray[np.bool_]
    position_signal: npt.NDArray[np.float64]
    labels: npt.NDArray[np.int64]
    centroids: npt.NDArray[np.int64]
    apertures: npt.NDArray[np.int32]


def _read_rows(  # noqa: PLR0913
    bounds: ImageBounds,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    label_source: _CompletedProductSource,
    centroid_source: _CompletedProductSource,
    aperture_source: _CompletedProductSource,
    position_source: _CompletedProductSource,
    config: SegmentRowStageConfig,
) -> _RowRead:
    """Read every plane one batch of segments needs, once."""
    background, residual, valid = _measurable_window(
        bounds,
        source=source,
        background_rms_source=background_rms_source,
        detection_source=detection_source,
    )
    labels = np.asarray(
        label_source.read_completed_window(config.label_product_name, bounds),
        dtype=np.int64,
    )
    return _RowRead(
        bounds=bounds,
        background=background,
        residual=residual,
        rms=np.asarray(
            background_rms_source.read_completed_window("rms", bounds),
            dtype=np.float64,
        ),
        valid=valid,
        position_signal=np.asarray(
            position_source.read_completed_window("position-signal", bounds),
            dtype=np.float64,
        ),
        labels=labels,
        centroids=labels
        if centroid_source is label_source
        and config.centroid_product_name == config.label_product_name
        else np.asarray(
            centroid_source.read_completed_window(
                config.centroid_product_name, bounds
            ),
            dtype=np.int64,
        ),
        apertures=np.asarray(
            aperture_source.read_completed_window("aperture-labels", bounds),
            dtype=np.int32,
        ),
    )


@dataclass(frozen=True, slots=True)
class _MeasuredSegment:
    """One segment's measurements, before either is given a sky position."""

    label_value: int
    row: SegmentRowMeasurement
    moment: tuple[tuple[float, float], npt.NDArray[np.float64]] | None


def _measure_segment(
    segment: _Segment,
    read: _RowRead,
    *,
    config: SegmentRowStageConfig,
    image_shape_yx: tuple[int, int],
    diagnostics: dict[int, SourcePositionDiagnostics] | None,
) -> _MeasuredSegment | None:
    """Measure one segment's row and moment inside its own window."""
    crop = _crop(read.bounds, segment.bounds)
    window = SegmentWindow(
        origin_yx=(segment.bounds.y_start, segment.bounds.x_start),
        plane_shape_yx=image_shape_yx,
    )
    row = measure_segment_row(
        read.residual[crop],
        read.position_signal[crop],
        read.valid[crop],
        read.centroids[crop],
        read.apertures[crop],
        read.background[crop],
        label_value=segment.label_value,
        window=window,
        beam_area_pixels=config.beam_area_pixels,
        denoised_position_maximum_peak_to_mean_ratio=(
            config.denoised_position_maximum_peak_to_mean_ratio
        ),
        position_diagnostics=diagnostics,
    )
    if row is None:
        return None
    return _MeasuredSegment(
        label_value=segment.label_value,
        row=row,
        moment=segment_moment(
            read.residual[crop],
            (read.labels[crop] == segment.label_value) & read.valid[crop],
            window,
        ),
    )


def _shaped_rows(
    measured: Sequence[_MeasuredSegment],
    *,
    celestial_wcs: Any,
    beam: RestoringBeam,
) -> tuple[tuple[int, CatalogueSource], ...]:
    """Give every measured segment its shape, transforming them together.

    A moment's local geometry belongs at its own centroid, and Astropy pays
    its frame machinery per call rather than per position, so one conversion
    for the batch costs what one segment used to. A geometry the WCS cannot
    provide is a property of that WCS, not of one segment, so every shape in
    the batch is then unavailable, exactly as measuring them one at a time
    would report.
    """
    if not measured:
        return ()
    # One conversion for every row coordinate, and one for every moment's
    # local geometry. Astropy pays its frame machinery per call rather than
    # per position, so a batch costs what one segment used to.
    sky = celestial_wcs.pixel_to_world(
        np.asarray(
            [item.row.centroid_xy[0] for item in measured],
            dtype=np.float64,
        ),
        np.asarray(
            [item.row.centroid_xy[1] for item in measured],
            dtype=np.float64,
        ),
    ).icrs
    right_ascension = sky.ra.deg
    declination = sky.dec.deg
    positions = tuple(
        item.moment[0] for item in measured if item.moment is not None
    )
    try:
        transforms = local_tangent_plane_transforms_from_wcs(
            celestial_wcs, positions
        )
        beams = restoring_beams_in_icrs(beam, celestial_wcs, positions)
    except (TypeError, ValueError):
        transforms, beams = (), ()
    geometries = iter(zip(transforms, beams, strict=True))
    rows: list[tuple[int, CatalogueSource]] = []
    for index, item in enumerate(measured):
        row = segment_row_at(
            item.row,
            right_ascension_degrees=float(right_ascension[index]),
            declination_degrees=float(declination[index]),
        )
        geometry = None if item.moment is None else next(geometries, None)
        fields = (
            unavailable_moment_shape_fields()
            if item.moment is None or geometry is None
            else moment_shape_fields_at(
                item.moment, transform=geometry[0], beam_icrs=geometry[1]
            )
        )
        fields["quality_flags"] = tuple(
            sorted({*row.quality_flags, *tuple(fields["quality_flags"])})  # type: ignore[misc]
        )
        rows.append((item.label_value, replace(row, **fields)))  # type: ignore[arg-type]
    return tuple(rows)


def _row_batch(  # noqa: PLR0913
    batch: _RowBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    label_source: _CompletedProductSource,
    centroid_source: _CompletedProductSource,
    aperture_source: _CompletedProductSource,
    position_source: _CompletedProductSource,
    config: SegmentRowStageConfig,
    wcs_header_text: str,
    beam: RestoringBeam,
    image_shape_yx: tuple[int, int],
) -> _RowBatchResult:
    """Measure every segment of one batch inside its own window."""
    celestial_wcs = celestial_wcs_from_header_text(wcs_header_text)
    with (
        background_rms_source.access_session(),
        detection_source.access_session(),
        label_source.access_session(),
        centroid_source.access_session(),
        aperture_source.access_session(),
        position_source.access_session(),
    ):
        read = _read_rows(
            batch.read_bounds,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            label_source=label_source,
            centroid_source=centroid_source,
            aperture_source=aperture_source,
            position_source=position_source,
            config=config,
        )
        diagnostics: dict[int, SourcePositionDiagnostics] = {}
        measured = [
            item
            for item in (
                _measure_segment(
                    segment,
                    read,
                    config=config,
                    image_shape_yx=image_shape_yx,
                    diagnostics=(
                        diagnostics
                        if config.with_position_diagnostics
                        else None
                    ),
                )
                for segment in batch.segments
            )
            if item is not None
        ]
        return _RowBatchResult(
            rows=_shaped_rows(
                measured, celestial_wcs=celestial_wcs, beam=beam
            ),
            local_rms=_batch_local_rms(batch, read),
            diagnostics=tuple(sorted(diagnostics.items())),
            maximum_segment_read_pixels=int(
                np.prod(batch.read_bounds.shape_yx)
            ),
        )


def _batch_local_rms(
    batch: _RowBatch,
    read: _RowRead,
) -> tuple[tuple[int, float], ...]:
    """Measure the local noise every segment of one batch owns.

    The noise belongs to the segment's own seeded ownership, which is the
    centroid plane rather than the measured support the label plane carries,
    and the read already holds both. A segment owning no usable estimate
    reports none instead of a fabricated value.
    """
    measured: list[tuple[int, float]] = []
    for segment in batch.segments:
        crop = _crop(read.bounds, segment.bounds)
        local_rms = segment_local_rms(
            read.rms[crop],
            read.centroids[crop],
            label_value=segment.label_value,
        )
        if local_rms is not None:
            measured.append((segment.label_value, local_rms))
    return tuple(measured)


def _wide_segment_batches(
    segments: tuple[_Segment, ...],
    results: tuple[_WindowBatchResult, ...],
    manifest: PartitionManifest,
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_WideSegmentBatch, ...]:
    """Name each core holding part of a wide segment, and which segments.

    The scan observed each label in its measured support or its aperture in
    exactly these cores, which is every pixel a row reads.
    """
    wide = frozenset(segment.label_value for segment in segments)
    labels_by_tile: dict[str, set[int]] = {}
    for result in results:
        for label_value, _, tile_id in result.observed:
            if label_value in wide:
                labels_by_tile.setdefault(tile_id, set()).add(label_value)
    cores = tuple(
        _WideSegmentCore(
            partition=partition,
            label_values=tuple(sorted(labels_by_tile[partition.tile_id])),
        )
        for partition in manifest.tiles
        if partition.tile_id in labels_by_tile
    )
    return tuple(
        _WideSegmentBatch(cores=cores[start : start + maximum_tiles_per_batch])
        for start in range(0, len(cores), maximum_tiles_per_batch)
    )


def _gather_wide_segments(  # noqa: PLR0913
    batch: _WideSegmentBatch,
    *,
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    label_source: _CompletedProductSource,
    centroid_source: _CompletedProductSource,
    aperture_source: _CompletedProductSource,
    position_source: _CompletedProductSource,
    config: SegmentRowStageConfig,
    image_width: int,
) -> _WideSegmentResult:
    """Return each wide segment's pixels from the cores that hold them.

    Every plane a row reads is read over the core alone, and each segment
    keeps the pixels it owns, holds in its measured support or holds in its
    aperture, which are all the pixels its row, moment and noise visit.
    """
    with (
        background_rms_source.access_session(),
        detection_source.access_session(),
        label_source.access_session(),
        centroid_source.access_session(),
        aperture_source.access_session(),
        position_source.access_session(),
    ):
        pieces: list[_SegmentPiece] = []
        maximum_read_pixels = 0
        for core in batch.cores:
            bounds = core.partition.core_bounds
            read = _read_rows(
                bounds,
                source=source,
                background_rms_source=background_rms_source,
                detection_source=detection_source,
                label_source=label_source,
                centroid_source=centroid_source,
                aperture_source=aperture_source,
                position_source=position_source,
                config=config,
            )
            for label_value in core.label_values:
                owned = read.centroids == label_value
                labelled = read.labels == label_value
                aperture = read.apertures == label_value
                member = owned | labelled | aperture
                rows, columns = np.nonzero(member)
                pieces.append(
                    _SegmentPiece(
                        label_value=label_value,
                        raster_indices=(
                            (rows.astype(np.int64) + bounds.y_start)
                            * image_width
                            + columns
                            + bounds.x_start
                        ),
                        residual=read.residual[member],
                        position_signal=read.position_signal[member],
                        background=read.background[member],
                        rms=read.rms[member],
                        valid=read.valid[member],
                        owned=owned[member],
                        labelled=labelled[member],
                        aperture=aperture[member],
                    )
                )
            maximum_read_pixels = max(maximum_read_pixels, read_pixels(bounds))
        return _WideSegmentResult(
            pieces=tuple(pieces),
            tile_ids=tuple(core.partition.tile_id for core in batch.cores),
            maximum_core_read_pixels=maximum_read_pixels,
        )


def _joined_piece(parts: list[_SegmentPiece]) -> _SegmentPiece:
    """Join one segment's pieces and restore raster order."""
    raster_indices = np.concatenate([part.raster_indices for part in parts])
    order = np.argsort(raster_indices, kind="stable")
    return _SegmentPiece(
        label_value=parts[0].label_value,
        raster_indices=raster_indices[order],
        residual=np.concatenate([part.residual for part in parts])[order],
        position_signal=np.concatenate(
            [part.position_signal for part in parts]
        )[order],
        background=np.concatenate([part.background for part in parts])[order],
        rms=np.concatenate([part.rms for part in parts])[order],
        valid=np.concatenate([part.valid for part in parts])[order],
        owned=np.concatenate([part.owned for part in parts])[order],
        labelled=np.concatenate([part.labelled for part in parts])[order],
        aperture=np.concatenate([part.aperture for part in parts])[order],
    )


def _wide_rows(  # noqa: PLR0913
    batches: tuple[_WideSegmentBatch, ...],
    results: tuple[_WideSegmentResult, ...],
    *,
    config: SegmentRowStageConfig,
    image_shape_yx: tuple[int, int],
    wcs_header_text: str,
    beam: RestoringBeam,
) -> _RowBatchResult:
    """Measure every wide segment from the pixels its cores returned.

    The pixels are put back in raster order, which is the order a window
    over the segment presents them in, so the row, the moment and the local
    noise are the ones that window would measure, bit for bit.

    Raises:
        ValueError: If a core that holds a wide segment did not answer,
            which would measure its row from part of its pixels.
    """
    requested = {
        core.partition.tile_id for batch in batches for core in batch.cores
    }
    answered = {tile_id for result in results for tile_id in result.tile_ids}
    if answered != requested:
        raise ValueError("every core holding a wide segment must answer")
    parts: dict[int, list[_SegmentPiece]] = {}
    for result in results:
        for piece in result.pieces:
            parts.setdefault(piece.label_value, []).append(piece)
    diagnostics: dict[int, SourcePositionDiagnostics] = {}
    measured: list[_MeasuredSegment] = []
    local_rms: list[tuple[int, float]] = []
    for label_value, pieces in sorted(parts.items()):
        piece = _joined_piece(pieces)
        y_pixels, x_pixels = np.divmod(piece.raster_indices, image_shape_yx[1])
        noise = segment_local_rms_pixels(piece.rms[piece.owned])
        if noise is not None:
            local_rms.append((label_value, noise))
        row = measure_segment_row_pixels(
            SegmentPixels(
                y=y_pixels,
                x=x_pixels,
                residual=piece.residual,
                position_signal=piece.position_signal,
                background=piece.background,
                valid=piece.valid,
                owned=piece.owned,
                aperture=piece.aperture,
            ),
            label_value=label_value,
            plane_shape_yx=image_shape_yx,
            beam_area_pixels=config.beam_area_pixels,
            denoised_position_maximum_peak_to_mean_ratio=(
                config.denoised_position_maximum_peak_to_mean_ratio
            ),
            position_diagnostics=(
                diagnostics if config.with_position_diagnostics else None
            ),
        )
        if row is None:
            continue
        support = piece.labelled & piece.valid
        measured.append(
            _MeasuredSegment(
                label_value=label_value,
                row=row,
                moment=segment_moment_pixels(
                    y_pixels[support],
                    x_pixels[support],
                    piece.residual[support],
                ),
            )
        )
    return _RowBatchResult(
        rows=_shaped_rows(
            measured,
            celestial_wcs=celestial_wcs_from_header_text(wcs_header_text),
            beam=beam,
        )
        if measured
        else (),
        local_rms=tuple(local_rms),
        diagnostics=tuple(sorted(diagnostics.items())),
        maximum_segment_read_pixels=max(
            (result.maximum_core_read_pixels for result in results),
            default=0,
        ),
    )


def _require_row_inputs(  # noqa: PLR0913, PLR0917
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    label_source: _CompletedProductSource,
    centroid_source: _CompletedProductSource,
    position_source: _CompletedProductSource,
    manifest: PartitionManifest,
    config: SegmentRowStageConfig,
) -> None:
    """Check every identity before any round is submitted."""
    if manifest.halo_yx != (0, 0):
        raise ValueError("segment apertures write cores without a halo")
    for product_source, names in (
        (background_rms_source, ("background", "rms")),
        (detection_source, ("valid-pixels",)),
        (position_source, ("position-signal",)),
        (label_source, (config.label_product_name,)),
        (centroid_source, (config.centroid_product_name,)),
    ):
        if product_source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the segment image shape"
            )
        if not set(names).issubset(
            product_source.read_generation().product_names
        ):
            raise ValueError(
                "published generations must carry every segment plane read"
            )


def _segments(
    results: tuple[_WindowBatchResult, ...],
) -> tuple[_Segment, ...]:
    """Merge every core's observation into one window per segment."""
    merged: dict[int, ImageBounds] = {}
    for result in results:
        for label_value, bounds, _ in result.observed:
            merged[label_value] = _union(merged.get(label_value), bounds)
    return tuple(
        _Segment(label_value=label_value, bounds=bounds)
        for label_value, bounds in sorted(merged.items())
    )


def run_segment_row_stage(  # noqa: PLR0913, PLR0917
    source: _WindowReadable,
    background_rms_source: _CompletedProductSource,
    detection_source: _CompletedProductSource,
    label_source: _CompletedProductSource,
    centroid_source: _CompletedProductSource,
    position_source: _CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: SegmentRowStageConfig,
    wcs_header_text: str,
    beam: RestoringBeam,
    executor: Executor,
    sink: ZarrProductSink,
) -> SegmentRowStageResult:
    """Measure one catalogue row per segment, inside the window holding it.

    Three rounds and one global reduction fewer than every other object
    round: the cores write the expanded apertures under the reviewed radius,
    they then observe the bounds each segment and aperture occupies, and one
    task per batch of segments measures their rows, moment shapes and the
    local noise over the support they own.

    ``wcs_header_text`` is the caller's own header as
    :meth:`astropy.io.fits.Header.tostring` writes it, not a ``WCS``; see
    :func:`~hebog.algorithms.astrometry.celestial_wcs_from_header_text`.

    A segment whose window exceeds ``maximum_batch_read_pixels`` is never
    read whole. The cores holding it return the pixels its row visits, and
    the row is measured from them restored to raster order, which is the row
    its window would give.
    """
    if sink.manifest != manifest:
        raise ValueError("segment row sink must use the stage manifest")
    _require_row_inputs(
        background_rms_source,
        detection_source,
        label_source,
        centroid_source,
        position_source,
        manifest,
        config,
    )
    core_batches = _core_batches(
        manifest.tiles,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    sink.initialize_product(
        product_name="aperture-labels",
        dtype=np.dtype("<i4"),
    )
    aperture_results = tuple(
        executor.map_batches(
            partial(
                _publish_apertures,
                source=source,
                background_rms_source=background_rms_source,
                detection_source=detection_source,
                label_source=label_source,
                config=config,
                image_shape_yx=manifest.image_shape_yx,
                sink=sink,
            ),
            core_batches,
        )
    )
    if not aperture_results:
        raise ValueError("executor returned no segment aperture results")
    generation = sink.publish_generation(
        product_names=_PRODUCT_NAMES,
        chunks=(
            chunk
            for result in aperture_results
            for chunk in result.product_chunks
        ),
    )
    window_results = tuple(
        executor.map_batches(
            partial(
                _scan_windows,
                label_source=label_source,
                aperture_source=sink,
                label_product_name=config.label_product_name,
            ),
            core_batches,
        )
    )
    if not window_results:
        raise ValueError("executor returned no segment window results")
    segments = _segments(window_results)
    budget = config.maximum_batch_read_pixels
    row_batches = _row_batches(
        tuple(
            segment
            for segment in segments
            if read_pixels(segment.bounds) <= budget
        ),
        maximum_objects_per_batch=config.maximum_objects_per_batch,
        maximum_batch_read_pixels=budget,
    )
    row_results = map_round(
        executor,
        partial(
            _row_batch,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            label_source=label_source,
            centroid_source=centroid_source,
            aperture_source=sink,
            position_source=position_source,
            config=config,
            wcs_header_text=wcs_header_text,
            beam=beam,
            image_shape_yx=manifest.image_shape_yx,
        ),
        row_batches,
        round_name="segment row",
    )
    wide_batches = _wide_segment_batches(
        tuple(
            segment
            for segment in segments
            if read_pixels(segment.bounds) > budget
        ),
        window_results,
        manifest,
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    wide_results = map_round(
        executor,
        partial(
            _gather_wide_segments,
            source=source,
            background_rms_source=background_rms_source,
            detection_source=detection_source,
            label_source=label_source,
            centroid_source=centroid_source,
            aperture_source=sink,
            position_source=position_source,
            config=config,
            image_width=manifest.image_shape_yx[1],
        ),
        wide_batches,
        round_name="wide segment",
    )
    row_results = (
        *row_results,
        _wide_rows(
            wide_batches,
            wide_results,
            config=config,
            image_shape_yx=manifest.image_shape_yx,
            wcs_header_text=wcs_header_text,
            beam=beam,
        ),
    )
    rows = tuple(
        row
        for _, row in sorted(
            (item for result in row_results for item in result.rows),
            key=lambda item: item[0],
        )
    )
    return SegmentRowStageResult(
        generation=generation,
        rows=rows,
        local_rms_by_label=dict(
            sorted(item for result in row_results for item in result.local_rms)
        ),
        position_diagnostics=dict(
            sorted(
                item for result in row_results for item in result.diagnostics
            )
        ),
        segment_count=len(segments),
        measured_segment_count=len(rows),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            2 * len(core_batches) + len(row_batches) + len(wide_batches)
        ),
        maximum_graph_width=max(
            len(core_batches), len(row_batches), len(wide_batches)
        ),
        maximum_segment_read_pixels=max(
            (result.maximum_segment_read_pixels for result in row_results),
            default=0,
        ),
    )
