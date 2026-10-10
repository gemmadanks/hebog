# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""The stage sequence ``find_sources`` runs, and the runner of each stage.

Each runner plans its stage's tile grid, opens the generation the stage
publishes and runs the stage through the caller's executor.
``run_stages`` estimates the background and RMS and then calls
``run_stages_from_background``, which runs every later stage in order on
a published background and RMS; a caller that already holds one starts
there instead of estimating it again. The sequence returns the generations
and the records the terminal catalogues are built from, and builds no
catalogue: ``hebog.public_science`` does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import prod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np
from astropy.io import fits

from hebog.algorithms.component_measurement import (
    reconcile_component_measurements,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import BackgroundRmsConfig, SourceFinderConfig
from hebog.data_models import ImageBounds, WideObjectCounts
from hebog.data_models.images import ImageMetadata, RestoringBeam
from hebog.executors import Executor
from hebog.io import ZarrProductSink
from hebog.io.base import WindowReadable
from hebog.science.continuum import retained_scale_detections
from hebog.stages.detection import run_detection_stage

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from hebog.algorithms.component_measurement import ComponentMeasurements
    from hebog.algorithms.multiscale_association import ScaleDetections
    from hebog.algorithms.source_association import HierarchyOverlaps
    from hebog.data_models.measurement_diagnostics import (
        SourcePositionDiagnostics,
    )
    from hebog.data_models.source_association import (
        DetectionComponentRecord,
        SourceAssociationResult,
    )
    from hebog.science.catalogue_rows import CatalogueSource
    from hebog.science.models import (
        CatalogueIsland,
        TiledComponentFits,
        TiledComponentTopology,
        TiledMultiscaleDetection,
    )
    from hebog.science.profile import ContinuumScienceProfile

_TILE_SHAPE_YX = (128, 128)
ADMITTED_TILE_CORE_PIXELS = 2048
"""Smallest tile core the scalability contract admits, in pixels."""
_SUPPORT_TILES_PER_BATCH = 4
_OWNER_BATCH_READ_PIXELS = 4 * 1024 * 1024
# One storage chunk holds a whole tile core, so a batch that reads a window
# decodes and revalidates every chunk the window touches, whatever fraction of
# it the objects occupy. Small batches therefore pay that decode many times
# over: sixteen objects a batch decoded 4.06 GiB for a 4 MB crowded image,
# against 0.74 GiB at 256, which is where the saving flattens. The read budget
# below still bounds the window a batch may hold.
_OWNER_OBJECTS_PER_BATCH = 256
_DENOISED_POSITION_PEAK_TO_MEAN_RATIO = 3.0
_ENVELOPE_PAIRS_PER_BATCH = 256


@dataclass(frozen=True, slots=True)
class PublishedStageRecords:
    """The records the stages published, from which the catalogues are built.

    They are the inputs of the terminal composition,
    ``hebog.public_science.build_configured_continuum_products``, under the
    same names, except that ``accepted_island_count`` is its
    ``component_count``.
    """

    accepted_island_count: int
    topology: TiledComponentTopology
    measurements: ComponentMeasurements
    association: SourceAssociationResult
    hierarchy: SourceAssociationResult
    component_rows: tuple[CatalogueSource, ...]
    source_rows: tuple[CatalogueSource, ...]
    source_positions: Mapping[int, SourcePositionDiagnostics]
    component_local_rms: Mapping[int, float]
    source_local_rms: Mapping[int, float]
    islands: tuple[CatalogueIsland, ...]
    island_ids_by_owner: Mapping[int, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class PublishedStages:
    """What the stages after the background and RMS published.

    The generations are named for the planes a later caller reads from
    them: ``publication_source`` holds the support labels and the retained
    mask, ``component_source`` the component labels, ``fit_source`` the
    persistent measurement support, ``hierarchy_source`` the retained
    scale support, and the two source generations the source labels and
    the support each source owns.
    """

    detection_source: ZarrProductSink
    support_source: ZarrProductSink
    publication_source: ZarrProductSink
    component_source: ZarrProductSink
    fit_source: ZarrProductSink
    hierarchy_source: ZarrProductSink
    source_label_source: ZarrProductSink
    source_support_source: ZarrProductSink
    multiscale: TiledMultiscaleDetection
    records: PublishedStageRecords
    wide_object_counts: WideObjectCounts


@dataclass(frozen=True, slots=True)
class StageSequenceResult:
    """The background and RMS generation and what the later stages published.

    ``published`` is ``None`` when no pixel has a usable local noise
    estimate: the sequence then stops after the background and RMS, and
    ``rms_scientific_status`` is ``unavailable``.
    """

    background_rms_source: ZarrProductSink
    rms_scientific_status: Literal["valid", "unavailable"]
    published: PublishedStages | None


def restoring_beam_from_header(header: fits.Header) -> RestoringBeam:
    """Return the restoring beam a header states, in degrees.

    A header without ``BPA`` states a beam at position angle zero.
    """
    return RestoringBeam(
        cast(float, header["BMAJ"]),
        cast(float, header["BMIN"]),
        cast(float, header["BPA"]) if "BPA" in header else 0.0,
    )


def _public_background_config(
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
    *,
    source_finder: SourceFinderConfig,
) -> BackgroundRmsConfig:
    """Reconcile refinement seeds and spatial meshes with public inputs."""
    adaptive = config.adaptive
    if adaptive is not None and (
        source_finder.island_threshold_sigma
        >= adaptive.candidate_threshold_sigma
    ):
        # Protected seeds must exceed the public support-growth threshold.
        # The validated caller detection threshold already has that ordering.
        config = replace(
            config,
            adaptive=replace(
                adaptive,
                candidate_threshold_sigma=source_finder.detection_threshold_sigma,
            ),
        )
    limiting_dimension = min(image_shape_yx)
    largest_window = max(config.coarse.window_shape_yx)
    if limiting_dimension < largest_window:
        return config
    fraction = min(
        1.0,
        config.maximum_spatial_window_fraction
        * limiting_dimension
        / largest_window,
    )
    if (
        fraction < 1.0
        and prod(image_shape_yx) > config.maximum_constant_map_pixels
    ):
        raise ValueError(
            "spatial mesh protection exceeds bounded image admission"
        )
    return replace(
        config,
        coarse=replace(
            config.coarse,
            window_shape_yx=tuple(
                max(1, int(size * fraction))
                for size in config.coarse.window_shape_yx
            ),
            step_yx=tuple(
                max(1, int(size * fraction)) for size in config.coarse.step_yx
            ),
        ),
        maximum_spatial_window_fraction=1.0,
    )


def estimate_background_rms(  # noqa: PLR0913
    source: WindowReadable,
    metadata: ImageMetadata,
    config: SourceFinderConfig,
    executor: Executor,
    work_directory: Path,
    *,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    generation_id: str,
) -> tuple[ZarrProductSink, bool]:
    """Run the exact candidate-owned bounded background/RMS stage.

    The stage publishes the background and the RMS as tiled planes, and the
    generation is what comes back: every later pass reads it by window. The
    one fact the composition needs about the estimate is whether any pixel
    can use it, which is reduced while streaming rather than kept as a mask.
    """
    from hebog.science.configuration import (  # noqa: PLC0415
        source_finder_configs,
    )
    from hebog.stages.background import (  # noqa: PLC0415
        MultiscaleSourceProtection,
    )

    manifest = plan_image_partitions(
        image_shape_yx=metadata.shape_yx,
        tile_core_shape_yx=_TILE_SHAPE_YX,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "background.zarr",
        manifest,
        generation_id=generation_id,
    )
    candidate_detection = source_finder_configs()[0]
    detection_config = replace(
        candidate_detection,
        source_finder=config,
        background_rms=replace(
            (
                _public_background_config(
                    metadata.shape_yx,
                    candidate_detection.background_rms,
                    source_finder=config,
                )
                if config.profile == "continuum"
                else candidate_detection.background_rms
            ),
            background=config.background,
        ),
    )
    run_detection_stage(
        source,
        manifest,
        detection_config,
        executor,
        sink,
        protect_coarse_source_support=(
            config.profile == "continuum"
            and detection_config.background_rms.coarse.window_shape_yx
            != candidate_detection.background_rms.coarse.window_shape_yx
        ),
        refine_local_noise=(
            config.profile == "continuum"
            and min(metadata.shape_yx)
            >= max(candidate_detection.background_rms.coarse.window_shape_yx)
        ),
        multiscale_protection=(
            MultiscaleSourceProtection(
                beam,
                config,
                review.matrix.support_fraction_bounds[0],
            )
            if config.profile == "continuum"
            else None
        ),
    )
    return sink, estimate_has_usable_noise(source, sink, metadata)


def estimate_has_usable_noise(
    source: WindowReadable,
    background_rms_source: ZarrProductSink,
    metadata: ImageMetadata,
) -> bool:
    """Return whether any pixel has a usable local noise estimate.

    This is the one decision the estimate makes about itself, and the only
    thing the composition needs from it: a pixel is usable where the image is
    valid and the estimate is positive. The stage has already required, on
    the core that computed it, that the estimate is finite wherever the image
    is valid, or, when no coarse window held enough samples for a
    background, nowhere, so validity is the image's own and needs no second
    opinion. The answer is reduced one canonical tile row at a time, so
    neither the estimate nor a mask over it is ever held whole.

    Raises:
        ValueError: If the published rows do not cover the image.
    """
    height, width = metadata.shape_yx
    rows = min(
        height,
        background_rms_source.manifest.tile_core_shape_yx[0],
    )
    usable = False
    start = 0
    for block in background_rms_source.iter_completed_row_blocks(
        "rms",
        max_block_bytes=rows * width * np.dtype(np.float64).itemsize,
    ):
        stop = start + block.shape[0]
        # Once a usable pixel is found, the image is read no further: the
        # remaining rows only confirm that the estimate covers the image.
        if not usable:
            window = source.read_window(ImageBounds(start, stop, 0, width))
            usable = bool(
                np.any(
                    window.valid_pixels
                    & (np.asarray(block, dtype=np.float64) > 0.0)
                )
            )
        start = stop
    if start != height:
        raise ValueError(
            f"background/RMS rows must total {height}; received {start}"
        )
    return usable


def detect_multiscale_products(  # noqa: PLR0913
    source: WindowReadable,
    background_rms_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[ZarrProductSink, TiledMultiscaleDetection]:
    """Run the tiled detection pass and read its published planes.

    The composition owns no plane at all: the pass publishes what a later
    pass reads by window, and reduces each scale feature's peak while its
    response is still on the task that evaluated it. Only the reconciled
    island records come back.

    ``tile_core_pixels`` is the non-overlapping output core each task owns.
    It defaults to the smallest core the scalability contract admits, and is
    widened when the widest filter halo would exceed a quarter of it. Tile
    geometry changes which task computes a value, never the value. One tile
    per batch is already a coarse task at that core, so batching adds nothing
    here.
    """
    from hebog.algorithms.multiscale_tiles import (  # noqa: PLC0415
        scale_filter_halo_pixels,
    )
    from hebog.science.continuum import (  # noqa: PLC0415
        residual_detection_config,
    )
    from hebog.science.models import (  # noqa: PLC0415
        TiledMultiscaleDetection,
    )
    from hebog.stages.multiscale import (  # noqa: PLC0415
        MultiscaleStageConfig,
        run_multiscale_stage,
    )

    halo = scale_filter_halo_pixels(beam)
    core = max(tile_core_pixels, 4 * halo + 1)
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(halo, halo),
    )
    sink = ZarrProductSink(
        work_directory / "multiscale.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_multiscale_stage(
        source,
        background_rms_source,
        manifest,
        config=MultiscaleStageConfig(
            beam=beam,
            detection=residual_detection_config(review),
            maximum_tiles_per_batch=1,
        ),
        executor=executor,
        sink=sink,
    )
    return sink, TiledMultiscaleDetection(
        detection_islands=result.detection_islands,
        scale_islands_by_order=result.scale_islands_by_order,
        scale_nominal_beam_fwhms=result.scale_nominal_beam_fwhms,
    )


def reduce_support_topology(  # noqa: PLR0913
    detection_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    scale_orders: tuple[int, ...],
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> ZarrProductSink:
    """Reconcile adjacent-scale persistence and return its plane's store.

    Persistence is not bounded by a halo: it is a record graph over the whole
    image. It is reconciled from compact per-core summaries and published as
    owned cores, and the generation is returned so the support rounds read it
    by window.
    """
    from hebog.stages.support import (  # noqa: PLC0415
        SupportTopologyStageConfig,
        run_support_topology_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "support.zarr",
        manifest,
        generation_id=generation_id,
    )
    run_support_topology_stage(
        detection_source,
        manifest,
        config=SupportTopologyStageConfig(
            scale_orders=scale_orders,
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
        ),
        executor=executor,
        sink=sink,
    )
    return sink


def publish_support_labels(  # noqa: PLR0913
    detection_source: ZarrProductSink,
    support_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection_islands: tuple[Any, ...],
    config: SourceFinderConfig,
    review: ContinuumScienceProfile,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[int, int, ZarrProductSink]:
    """Decide owner connectivity and publish the support pass's labels.

    Two of the decisions here are scoped to an owner rather than to a tile,
    so they are taken once per owner from the window holding it and applied
    by the core that owns each pixel. The caller's island admission is
    applied in the same write, and the count of islands it accepted is the
    only thing that comes back: every plane stays in the generation, where
    the mask product and the object rounds read it by window.
    """
    from hebog.algorithms.extended_measurement import (  # noqa: PLC0415
        segment_refinement_halo_pixels,
    )
    from hebog.stages.publication import (  # noqa: PLC0415
        PublicationStageConfig,
        run_publication_stage,
    )

    halo = segment_refinement_halo_pixels(beam.major_fwhm_pixels)
    core = max(tile_core_pixels, 4 * halo + 1)
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(halo, halo),
    )
    sink = ZarrProductSink(
        work_directory / "publication.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_publication_stage(
        detection_source,
        support_source,
        manifest,
        detection_islands=detection_islands,
        config=PublicationStageConfig(
            beam=beam,
            island_threshold_sigma=review.matrix.island_sigma,
            minimum_island_pixels=config.minimum_island_pixels,
            maximum_island_pixels=config.maximum_island_pixels,
            maximum_tiles_per_batch=1,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        executor=executor,
        sink=sink,
    )
    return result.accepted_island_count, result.wide_owner_count, sink


def publish_component_topology(  # noqa: PLR0913
    support_source: ZarrProductSink,
    detection_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    config: SourceFinderConfig,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[ZarrProductSink, TiledComponentTopology]:
    """Deblend every parent in its own window and read the components.

    Deblending needs a parent's complete support and nothing beyond it, so
    the object pass decides one parent per task and the cores write the
    component labels they own.
    """
    from hebog.science.continuum import (  # noqa: PLC0415
        compact_deblend_config,
    )
    from hebog.science.models import (  # noqa: PLC0415
        TiledComponentTopology,
    )
    from hebog.stages.objects import (  # noqa: PLC0415
        ComponentTopologyStageConfig,
        run_component_topology_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "components.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_component_topology_stage(
        support_source,
        detection_source,
        manifest,
        config=ComponentTopologyStageConfig(
            deblend=compact_deblend_config(config),
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        executor=executor,
        sink=sink,
    )
    return sink, TiledComponentTopology(
        component_count=result.component_count,
        deblended_parent_count=result.deblended_parent_count,
        deferred_parent_count=result.deferred_parent_count,
    )


def publish_segment_rows(  # noqa: PLR0913, PLR0917
    source: WindowReadable,
    background_rms_source: ZarrProductSink,
    detection_source: ZarrProductSink,
    label_source: ZarrProductSink,
    centroid_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    wcs_header_text: str,
    restoring_beam: RestoringBeam,
    label_product_name: str,
    centroid_product_name: str,
    aperture_tie_policy: Literal["nearest-support", "canonical-source"],
    with_position_diagnostics: bool,
    generation_id: str,
    sink_name: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[tuple[Any, ...], Mapping[int, float], Mapping[int, Any], int]:
    """Measure one catalogue row per segment, each in its own window.

    The cores write the expanded apertures under the reviewed radius, they
    observe the bounds each segment and aperture occupies, and one task per
    batch of segments measures their rows, their local noise and their moment
    shapes. The aperture plane stays in the published generation: the rows
    carry what the catalogue needs from it, so the driver never holds it.
    """
    from math import ceil, log, pi  # noqa: PLC0415

    from hebog.science.continuum import (  # noqa: PLC0415
        CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    )
    from hebog.stages.catalogue_rows import (  # noqa: PLC0415
        SegmentRowStageConfig,
        run_segment_row_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / f"{sink_name}.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_segment_row_stage(
        source,
        background_rms_source,
        detection_source,
        label_source,
        centroid_source,
        detection_source,
        manifest,
        config=SegmentRowStageConfig(
            label_product_name=label_product_name,
            centroid_product_name=centroid_product_name,
            aperture_radius_pixels=ceil(
                CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
                * beam.major_fwhm_pixels
            ),
            aperture_tie_policy=aperture_tie_policy,
            beam_area_pixels=(
                2.0
                * pi
                / (8.0 * log(2.0))
                * beam.major_fwhm_pixels
                * beam.minor_fwhm_pixels
            ),
            denoised_position_maximum_peak_to_mean_ratio=(
                _DENOISED_POSITION_PEAK_TO_MEAN_RATIO
            ),
            with_position_diagnostics=with_position_diagnostics,
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_objects_per_batch=_OWNER_OBJECTS_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        wcs_header_text=wcs_header_text,
        beam=restoring_beam,
        executor=executor,
        sink=sink,
    )
    return (
        result.rows,
        result.local_rms_by_label,
        result.position_diagnostics,
        result.wide_segment_count,
    )


def publish_detection_islands(  # noqa: PLR0913
    source: WindowReadable,
    background_rms_source: ZarrProductSink,
    publication_source: ZarrProductSink,
    component_source: ZarrProductSink,
    executor: Executor,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[tuple[Any, ...], Mapping[int, tuple[str, ...]], int]:
    """Measure one catalogue row per island of the published retained mask.

    The cores label their own mask and observe which owners its islands hold,
    the fragments reconcile into islands named by canonical first pixel, and
    one task per batch of islands measures their rows. Nothing is published:
    the island labels exist only inside these rounds.
    """
    from math import log, pi  # noqa: PLC0415

    from hebog.stages.islands import (  # noqa: PLC0415
        DetectionIslandStageConfig,
        run_detection_island_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    result = run_detection_island_stage(
        source,
        background_rms_source,
        publication_source,
        component_source,
        manifest,
        config=DetectionIslandStageConfig(
            beam_area_pixels=(
                pi
                * beam.major_fwhm_pixels
                * beam.minor_fwhm_pixels
                / (4.0 * log(2.0))
            ),
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_objects_per_batch=_OWNER_OBJECTS_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        executor=executor,
    )
    return result.islands, result.island_ids_by_owner, result.wide_island_count


def publish_source_planes(  # noqa: PLR0913, PLR0917
    component_source: ZarrProductSink,
    detection_source: ZarrProductSink,
    scale_support_source: ZarrProductSink,
    measurement_support_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    association: SourceAssociationResult,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[ZarrProductSink, ZarrProductSink, int]:
    """Publish the source labels and the persistent support they own.

    The owners a source holds are a record map, so the cores write the
    labels from the shard that reaches them; the support a source owns spans
    tiles, so it is reconciled before each connected component divides its
    unseeded pixels between the sources that seed it.
    """
    from hebog.science.catalogues import (  # noqa: PLC0415
        source_label_by_owner,
    )
    from hebog.stages.sources import (  # noqa: PLC0415
        SourceLabelStageConfig,
        SourceSupportStageConfig,
        run_source_label_stage,
        run_source_support_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    label_sink = ZarrProductSink(
        work_directory / "source-labels.zarr",
        manifest,
        generation_id=generation_id,
    )
    run_source_label_stage(
        component_source,
        manifest,
        config=SourceLabelStageConfig(
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
        ),
        source_by_owner=source_label_by_owner(association),
        executor=executor,
        sink=label_sink,
    )
    support_sink = ZarrProductSink(
        work_directory / "source-support.zarr",
        manifest,
        generation_id=generation_id,
    )
    support_result = run_source_support_stage(
        label_sink,
        detection_source,
        scale_support_source,
        measurement_support_source,
        manifest,
        config=SourceSupportStageConfig(
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_objects_per_batch=_OWNER_OBJECTS_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        executor=executor,
        sink=support_sink,
    )
    return label_sink, support_sink, support_result.wide_component_count


def publish_hierarchy_overlaps(  # noqa: PLR0913
    detection_source: ZarrProductSink,
    component_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    records: tuple[DetectionComponentRecord, ...],
    scale_detections: Sequence[ScaleDetections],
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[HierarchyOverlaps, ZarrProductSink]:
    """Reduce every pixel fact the source hierarchy decision needs.

    The cores observe which components, features and retained support
    components meet, one task per feature derives its reviewed B3 influence,
    and one task per candidate pair decides whether two envelopes overlap.
    The decision that consumes the result holds no plane, and the component
    records reach both it and this pass already built.
    """
    from hebog.stages.association import (  # noqa: PLC0415
        HierarchyOverlapStageConfig,
        run_hierarchy_overlap_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "hierarchy.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_hierarchy_overlap_stage(
        detection_source,
        component_source,
        manifest,
        config=HierarchyOverlapStageConfig(
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_features_per_batch=_OWNER_OBJECTS_PER_BATCH,
            maximum_pairs_per_batch=_ENVELOPE_PAIRS_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        records=records,
        scale_detections=scale_detections,
        executor=executor,
        sink=sink,
    )
    return result.overlaps, sink


def publish_component_fits(  # noqa: PLR0913, PLR0917
    source: WindowReadable,
    background_rms_source: ZarrProductSink,
    detection_source: ZarrProductSink,
    component_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    wcs_header_text: str,
    restoring_beam: RestoringBeam,
    config: SourceFinderConfig,
    review: ContinuumScienceProfile,
    component_count: int,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[TiledComponentFits, ZarrProductSink]:
    """Fit every measurement parent in its own context window.

    Owners whose fit contexts touch need a joint model, so the contexts are
    reconciled first, a parent no joint fit can hold is split into its
    islands, and each fit parent is then measured inside the window holding
    it. The cores combine the persistent measurement support the
    parents contributed, and the connected features of that support are then
    grouped one window at a time.

    Each parent also describes the direct components it owns, so the records
    the association decision reads come from the residual the fits already
    hold rather than from a second pass of per-component reads.
    ``component_count`` is the topology's, and the records must describe
    every one of those components.
    """
    from hebog.algorithms.component_measurement import (  # noqa: PLC0415
        fit_parent_margin_pixels,
    )
    from hebog.algorithms.multiscale import (  # noqa: PLC0415
        build_residual_atrous_plan,
    )
    from hebog.science.configuration import (  # noqa: PLC0415
        source_finder_configs,
    )
    from hebog.science.continuum import (  # noqa: PLC0415
        compact_deblend_config,
    )
    from hebog.science.models import TiledComponentFits  # noqa: PLC0415
    from hebog.stages.objects import (  # noqa: PLC0415
        ComponentFitStageConfig,
        ExtendedGroupStageConfig,
        FitParentStageConfig,
        run_component_fit_stage,
        run_extended_group_stage,
        run_fit_parent_stage,
    )

    _, _, moment_config, fit_config = source_finder_configs()
    fit_config = replace(fit_config, integrated_flux_bias_correction_sigma=0.0)
    atrous_plan = build_residual_atrous_plan(beam, noise_correlation=beam)
    context_margin = int(fit_config.context_margin_pixels)
    core = max(tile_core_pixels, 4 * context_margin + 1)
    fit_parent_manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(context_margin, context_margin),
    )
    fit_parent_sink = ZarrProductSink(
        work_directory / "fit-parents.zarr",
        fit_parent_manifest,
        generation_id=generation_id,
    )
    run_fit_parent_stage(
        component_source,
        fit_parent_manifest,
        config=FitParentStageConfig(
            context_margin_pixels=context_margin,
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            read_margin_pixels=fit_parent_margin_pixels(
                fit_config, atrous_plan
            ),
            maximum_bounds_pixels=(
                compact_deblend_config(config).maximum_compact_bounds_pixels
            ),
        ),
        executor=executor,
        sink=fit_parent_sink,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "component-fits.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_component_fit_stage(
        source,
        background_rms_source,
        detection_source,
        component_source,
        fit_parent_sink,
        manifest,
        config=ComponentFitStageConfig(
            moment=moment_config,
            fit=fit_config,
            atrous_plan=atrous_plan,
            detection_sigma=config.detection_threshold_sigma,
            island_sigma=config.island_threshold_sigma,
            minimum_pixels=config.minimum_island_pixels,
            maximum_bounds_pixels=(
                compact_deblend_config(config).maximum_compact_bounds_pixels
            ),
            minimum_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        component_count=component_count,
        wcs_header_text=wcs_header_text,
        beam=restoring_beam,
        executor=executor,
        sink=sink,
    )
    groups = run_extended_group_stage(
        source,
        background_rms_source,
        detection_source,
        component_source,
        sink,
        manifest,
        config=ExtendedGroupStageConfig(
            atrous_plan=atrous_plan,
            detection_sigma=config.detection_threshold_sigma,
            island_sigma=config.island_threshold_sigma,
            minimum_pixels=config.minimum_island_pixels,
            maximum_bounds_pixels=(
                compact_deblend_config(config).maximum_compact_bounds_pixels
            ),
            minimum_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        parents=result.parents,
        wcs_header_text=wcs_header_text,
        beam=restoring_beam,
        executor=executor,
    )
    return TiledComponentFits(
        parents=result.parents,
        features=groups.features,
        component_records=result.component_records,
        wide_parent_count=result.wide_parent_count,
    ), sink


def _source_association(
    records: tuple[DetectionComponentRecord, ...],
    scale_detections: Sequence[ScaleDetections],
    overlaps: HierarchyOverlaps,
    groups: tuple[frozenset[int], ...],
) -> tuple[SourceAssociationResult, SourceAssociationResult]:
    """Decide source membership, or nothing when no owner remains.

    The terminal composition publishes nothing for an image whose admitted
    islands are all rejected, and the hierarchy has no direct component to
    describe, so the decision is skipped rather than fabricated.
    """
    from hebog.algorithms.source_association import (  # noqa: PLC0415
        associate_from_hierarchy_overlaps,
        constrain_source_memberships,
    )
    from hebog.data_models.source_association import (  # noqa: PLC0415
        SourceAssociationResult as _Association,
    )

    if not records:
        empty = _Association(
            components=(),
            edges=(),
            memberships=(),
            ambiguous_component_ids=(),
        )
        return empty, empty
    hierarchy = associate_from_hierarchy_overlaps(
        records, tuple(scale_detections), overlaps
    )
    return hierarchy, constrain_source_memberships(hierarchy, groups)


def run_stages(  # noqa: PLR0913
    source: WindowReadable,
    metadata: ImageMetadata,
    executor: Executor,
    work_directory: Path,
    *,
    config: SourceFinderConfig,
    wcs_header_text: str,
    restoring_beam: RestoringBeam,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    generation_id: str,
) -> StageSequenceResult:
    """Estimate the background and RMS, then run every later stage in order.

    ``beam`` is the restoring beam in local pixel axes and ``review`` the
    installed profile under the caller's thresholds. ``wcs_header_text`` is
    the header text each task rebuilds the celestial WCS from, and
    ``restoring_beam`` the beam that header states. Every stage writes its
    planes to a generation below ``work_directory`` named by
    ``generation_id``, and later stages read them by window.
    """
    background_rms_source, usable_noise = estimate_background_rms(
        source,
        metadata,
        config,
        executor,
        work_directory,
        beam=beam,
        review=review,
        generation_id=generation_id,
    )
    if not usable_noise:
        return StageSequenceResult(
            background_rms_source=background_rms_source,
            rms_scientific_status="unavailable",
            published=None,
        )
    return StageSequenceResult(
        background_rms_source=background_rms_source,
        rms_scientific_status="valid",
        published=run_stages_from_background(
            source,
            background_rms_source,
            executor,
            work_directory,
            image_shape_yx=metadata.shape_yx,
            config=config,
            wcs_header_text=wcs_header_text,
            restoring_beam=restoring_beam,
            beam=beam,
            review=review,
            generation_id=generation_id,
        ),
    )


def run_stages_from_background(  # noqa: PLR0913
    source: WindowReadable,
    background_rms_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    config: SourceFinderConfig,
    wcs_header_text: str,
    restoring_beam: RestoringBeam,
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    generation_id: str,
    multiscale_tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
    support_tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> PublishedStages:
    """Run every stage after the background and RMS, in order.

    ``background_rms_source`` is a published background and RMS generation,
    which every stage reads by window rather than estimating again.
    ``multiscale_tile_core_pixels`` is the multiscale pass's core and
    ``support_tile_core_pixels`` the core of every pass from the support
    reduction on; both default to the smallest
    core the scalability contract admits, as ``find_sources`` runs them, and
    no core changes a product.
    """
    detection_source, multiscale = detect_multiscale_products(
        source,
        background_rms_source,
        executor,
        work_directory,
        image_shape_yx=image_shape_yx,
        beam=beam,
        review=review,
        generation_id=generation_id,
        tile_core_pixels=multiscale_tile_core_pixels,
    )
    support_source = reduce_support_topology(
        detection_source,
        executor,
        work_directory,
        image_shape_yx=image_shape_yx,
        scale_orders=tuple(
            range(1, len(multiscale.scale_islands_by_order) + 1)
        ),
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    accepted_island_count, wide_owner_count, labels_source = (
        publish_support_labels(
            detection_source,
            support_source,
            executor,
            work_directory,
            image_shape_yx=image_shape_yx,
            beam=beam,
            detection_islands=multiscale.detection_islands,
            config=config,
            review=review,
            generation_id=generation_id,
            tile_core_pixels=support_tile_core_pixels,
        )
    )
    component_source, topology = publish_component_topology(
        labels_source,
        detection_source,
        executor,
        work_directory,
        image_shape_yx=image_shape_yx,
        config=config,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    scale_detections = retained_scale_detections(multiscale)
    component_fits, fit_source = publish_component_fits(
        source,
        background_rms_source,
        detection_source,
        component_source,
        executor,
        work_directory,
        image_shape_yx=image_shape_yx,
        beam=beam,
        wcs_header_text=wcs_header_text,
        restoring_beam=restoring_beam,
        config=config,
        review=review,
        component_count=topology.component_count,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    records = component_fits.component_records
    overlaps, hierarchy_source = publish_hierarchy_overlaps(
        detection_source,
        component_source,
        executor,
        work_directory,
        image_shape_yx=image_shape_yx,
        records=records,
        scale_detections=scale_detections,
        generation_id=generation_id,
        tile_core_pixels=support_tile_core_pixels,
    )
    measurements = reconcile_component_measurements(
        parents=component_fits.parents,
        features=component_fits.features,
    )
    hierarchy, association = _source_association(
        records,
        scale_detections,
        overlaps,
        (*measurements.compact_groups, *measurements.extended_groups),
    )
    source_label_source, source_support_source, wide_component_count = (
        publish_source_planes(
            component_source,
            detection_source,
            hierarchy_source,
            fit_source,
            executor,
            work_directory,
            image_shape_yx=image_shape_yx,
            association=association,
            generation_id=generation_id,
            tile_core_pixels=support_tile_core_pixels,
        )
    )
    islands, island_ids_by_owner, wide_island_count = (
        publish_detection_islands(
            source,
            background_rms_source,
            labels_source,
            component_source,
            executor,
            image_shape_yx=image_shape_yx,
            beam=beam,
            tile_core_pixels=support_tile_core_pixels,
        )
    )
    component_rows, component_local_rms, _, wide_component_segment_count = (
        publish_segment_rows(
            source,
            background_rms_source,
            detection_source,
            component_source,
            component_source,
            executor,
            work_directory,
            image_shape_yx=image_shape_yx,
            beam=beam,
            wcs_header_text=wcs_header_text,
            restoring_beam=restoring_beam,
            label_product_name="component-measurement-labels",
            centroid_product_name="component-measurement-labels",
            aperture_tie_policy="nearest-support",
            with_position_diagnostics=False,
            generation_id=generation_id,
            sink_name="component-rows",
            tile_core_pixels=support_tile_core_pixels,
        )
    )
    (
        source_rows,
        source_local_rms,
        source_positions,
        wide_source_segment_count,
    ) = publish_segment_rows(
        source,
        background_rms_source,
        detection_source,
        source_support_source,
        source_label_source,
        executor,
        work_directory,
        image_shape_yx=image_shape_yx,
        beam=beam,
        wcs_header_text=wcs_header_text,
        restoring_beam=restoring_beam,
        label_product_name="source-measurement-labels",
        centroid_product_name="source-labels",
        aperture_tie_policy="canonical-source",
        with_position_diagnostics=True,
        generation_id=generation_id,
        sink_name="source-rows",
        tile_core_pixels=support_tile_core_pixels,
    )
    return PublishedStages(
        detection_source=detection_source,
        support_source=support_source,
        publication_source=labels_source,
        component_source=component_source,
        fit_source=fit_source,
        hierarchy_source=hierarchy_source,
        source_label_source=source_label_source,
        source_support_source=source_support_source,
        multiscale=multiscale,
        records=PublishedStageRecords(
            accepted_island_count=accepted_island_count,
            topology=topology,
            measurements=measurements,
            association=association,
            hierarchy=hierarchy,
            component_rows=component_rows,
            source_rows=source_rows,
            source_positions=source_positions,
            component_local_rms=component_local_rms,
            source_local_rms=source_local_rms,
            islands=islands,
            island_ids_by_owner=island_ids_by_owner,
        ),
        wide_object_counts=WideObjectCounts(
            publication_owners=wide_owner_count,
            support_components=wide_component_count,
            deferred_fit_parents=component_fits.wide_parent_count,
            islands=wide_island_count,
            segments=wide_component_segment_count + wide_source_segment_count,
        ),
    )
