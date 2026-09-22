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
    build_segment_row,
    moment_shape_fields_at,
    segment_moment,
    unavailable_moment_shape_fields,
)
from hebog.science.models import CatalogueSource

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
    """Published apertures, the rows they measure, and scalar evidence."""

    generation: ProductGenerationManifest
    rows: tuple[CatalogueSource, ...]
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
    """The bounds each core observes for every label it holds."""

    observed: tuple[tuple[int, ImageBounds], ...]


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
    """The rows and diagnostics one batch of segments produced."""

    rows: tuple[tuple[int, CatalogueSource], ...]
    diagnostics: tuple[tuple[int, SourcePositionDiagnostics], ...]
    maximum_segment_read_pixels: int


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
    bounds: ImageBounds,
) -> tuple[tuple[int, ImageBounds], ...]:
    """Return the global bounds each label occupies inside one core."""
    return tuple(
        (
            index + 1,
            ImageBounds(
                bounds.y_start + window[0].start,
                bounds.y_start + window[0].stop,
                bounds.x_start + window[1].start,
                bounds.x_start + window[1].stop,
            ),
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
        observed: list[tuple[int, ImageBounds]] = []
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
                        core,
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


def _batch_bounds(segments: list[_Segment]) -> ImageBounds:
    """Return the one read that serves every segment in a batch."""
    bounds = segments[0].bounds
    for segment in segments[1:]:
        bounds = _union(bounds, segment.bounds)
    return bounds


def _row_batches(
    segments: tuple[_Segment, ...],
    *,
    maximum_objects_per_batch: int,
    maximum_batch_read_pixels: int,
) -> tuple[_RowBatch, ...]:
    """Group segments so one read serves several, within both budgets."""
    ordered = sorted(
        segments, key=lambda item: (item.bounds.y_start, item.bounds.x_start)
    )
    batches: list[_RowBatch] = []
    grouped: list[_Segment] = []
    for item in ordered:
        candidate = [*grouped, item]
        if grouped and (
            len(candidate) > maximum_objects_per_batch
            or int(np.prod(_batch_bounds(candidate).shape_yx))
            > maximum_batch_read_pixels
        ):
            batches.append(
                _RowBatch(
                    segments=tuple(grouped),
                    read_bounds=_batch_bounds(grouped),
                )
            )
            grouped = [item]
            continue
        grouped = candidate
    if grouped:
        batches.append(
            _RowBatch(
                segments=tuple(grouped), read_bounds=_batch_bounds(grouped)
            )
        )
    return tuple(batches)


@dataclass(frozen=True, slots=True)
class _RowRead:
    """One batch's planes, read once and cropped per segment."""

    bounds: ImageBounds
    background: npt.NDArray[np.float64]
    residual: npt.NDArray[np.float64]
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
    """One segment's row and the moment its shape still needs transforming."""

    label_value: int
    row: CatalogueSource
    moment: tuple[tuple[float, float], npt.NDArray[np.float64]] | None


def _measure_segment(  # noqa: PLR0913
    segment: _Segment,
    read: _RowRead,
    *,
    celestial_wcs: Any,
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
    row = build_segment_row(
        read.residual[crop],
        read.position_signal[crop],
        read.valid[crop],
        read.centroids[crop],
        read.apertures[crop],
        read.background[crop],
        celestial_wcs,
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
    for item in measured:
        geometry = None if item.moment is None else next(geometries, None)
        fields = (
            unavailable_moment_shape_fields()
            if item.moment is None or geometry is None
            else moment_shape_fields_at(
                item.moment, transform=geometry[0], beam_icrs=geometry[1]
            )
        )
        fields["quality_flags"] = tuple(
            sorted({*item.row.quality_flags, *tuple(fields["quality_flags"])})  # type: ignore[misc]
        )
        rows.append((item.label_value, replace(item.row, **fields)))  # type: ignore[arg-type]
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
                    celestial_wcs=celestial_wcs,
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
            diagnostics=tuple(sorted(diagnostics.items())),
            maximum_segment_read_pixels=int(
                np.prod(batch.read_bounds.shape_yx)
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
        (background_rms_source, ("background",)),
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
        for label_value, bounds in result.observed:
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
    task per batch of segments measures their rows and moment shapes.

    ``wcs_header_text`` is the caller's own header as
    :meth:`astropy.io.fits.Header.tostring` writes it, not a ``WCS``; see
    :func:`~hebog.algorithms.astrometry.celestial_wcs_from_header_text`.
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
    row_batches = _row_batches(
        segments,
        maximum_objects_per_batch=config.maximum_objects_per_batch,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
    )
    row_results: tuple[_RowBatchResult, ...] = ()
    if row_batches:
        row_results = tuple(
            executor.map_batches(
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
            )
        )
        if not row_results:
            raise ValueError("executor returned no segment row results")
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
        position_diagnostics=dict(
            sorted(
                item for result in row_results for item in result.diagnostics
            )
        ),
        segment_count=len(segments),
        measured_segment_count=len(rows),
        partition_count=len(manifest.tiles),
        executor_task_count=2 * len(core_batches) + len(row_batches),
        maximum_graph_width=max(len(core_batches), len(row_batches)),
        maximum_segment_read_pixels=max(
            (result.maximum_segment_read_pixels for result in row_results),
            default=0,
        ),
    )
