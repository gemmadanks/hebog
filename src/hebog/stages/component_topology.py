# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""Component topology, the first per-object round of the composition.

Every parent's deblending needs its complete support and nothing beyond it,
so one task decides one parent exactly, and the cores then write the
component labels they own.

Component numbering stays canonical because the driver offsets each parent's
local labels by the components every earlier parent produced, in ascending
parent order, which is the order a whole-plane pass would use. The driver
needs only each parent's component count for that, so no component pixel
reaches it: a core writing a deblended parent decides its memberships again
from the parent's own windows, which gives the same memberships bit for bit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from numbers import Integral

import numpy as np
import numpy.typing as npt

from hebog.algorithms.component_topology import (
    ParentComponentMembership,
    deblend_parent_components,
    parent_is_deferred,
)
from hebog.config import (
    CompactDeblendConfig,
)
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.executors.base import Executor
from hebog.io.base import CompletedProductSource
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import (
    batch_object_windows,
    map_round,
    read_pixels,
)
from hebog.stages.object_extents import (
    EXTENT_SCAN_BYTES_PER_READ_PIXEL,
    CoreExtent,
    ExtentBatchResult,
    ParentExtent,
    PublishBatchResult,
    bounds_intersect,
    core_label_extents,
    crop_slices,
    parent_holders,
    reduce_extents,
)
from hebog.stages.task_memory import read_requirement

# Each round's cost per pixel of its largest read, which a task declares
# (``hebog.stages.task_memory``): the largest traced task peak over that read
# on the 3,000-, 10,000- and 15,402-pixel LoTSS-DR3 anchors and the dense
# ELAIS-N1 central 5,000 pixels, rounded up to eight bytes (plan task 17).
_DEBLEND_BYTES_PER_READ_PIXEL = 168
_TOPOLOGY_PUBLICATION_BYTES_PER_READ_PIXEL = 96

_TOPOLOGY_PRODUCT_NAMES = (
    "component-direct-labels",
    "component-measurement-labels",
)


@dataclass(frozen=True, slots=True)
class ComponentTopologyStageConfig:
    """Reviewed deblending policy and the bounded task limits."""

    deblend: CompactDeblendConfig
    maximum_tiles_per_batch: int
    maximum_batch_read_pixels: int

    def __post_init__(self) -> None:
        """Reject an unbounded task before stage products are initialized."""
        for name, value in (
            ("maximum_tiles_per_batch", self.maximum_tiles_per_batch),
            ("maximum_batch_read_pixels", self.maximum_batch_read_pixels),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ComponentTopologyStageResult:
    """Published component labels and scalar execution evidence."""

    generation: ProductGenerationManifest
    component_count: int
    parent_count: int
    deblended_parent_count: int
    deferred_parent_count: int
    partition_count: int
    executor_task_count: int
    maximum_graph_width: int
    maximum_parent_read_pixels: int
    parent_batch_count: int


@dataclass(frozen=True, slots=True)
class _ParentBatch:
    """One bounded coarse executor task over several parents."""

    parents: tuple[ParentExtent, ...]
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.parents:
            raise ValueError("parent batch must not be empty")


@dataclass(frozen=True, slots=True)
class _ParentCount:
    """How many components one admitted parent deblends into."""

    parent_label: int
    component_count: int
    deferred: bool


@dataclass(frozen=True, slots=True)
class _DeblendBatchResult:
    """The component counts one batch of parents decided."""

    parents: tuple[_ParentCount, ...]
    maximum_parent_read_pixels: int


@dataclass(frozen=True, slots=True)
class _NumberedParent:
    """One deblended parent and the offset of its local component labels."""

    parent: ParentExtent
    component_offset: int


@dataclass(frozen=True, slots=True)
class _TileRequest:
    """One core and the numbered parents it holds.

    ``single_components`` pairs each parent published as one component with
    that component's label; its pixels are the parent's own support, which
    the core already holds. ``deblended_parents`` are the parents that split,
    in canonical order, which the core decides again from their windows.
    """

    partition: TilePartition
    single_components: tuple[tuple[int, int], ...] = ()
    deblended_parents: tuple[_NumberedParent, ...] = ()


@dataclass(frozen=True, slots=True)
class _TileBatch:
    """One bounded coarse executor task over several cores."""

    requests: tuple[_TileRequest, ...]

    def __post_init__(self) -> None:
        """Forbid empty executor work records."""
        if not self.requests:
            raise ValueError("component tile batch must not be empty")


def component_topology_product_names() -> tuple[str, ...]:
    """Return the canonical published component-topology product set."""
    return _TOPOLOGY_PRODUCT_NAMES


def _scan_extents(
    batch: _TileBatch,
    *,
    support_source: CompletedProductSource,
) -> ExtentBatchResult:
    """Observe every parent's extent inside the cores of one batch."""
    extents: list[CoreExtent] = []
    for request in batch.requests:
        bounds = request.partition.core_bounds
        direct = core_label_extents(
            np.asarray(
                support_source.read_completed_window(
                    "component-labels",
                    bounds,
                ),
                dtype=np.int32,
            ),
            bounds,
        )
        measurement = core_label_extents(
            np.asarray(
                support_source.read_completed_window(
                    "measurement-labels",
                    bounds,
                ),
                dtype=np.int32,
            ),
            bounds,
        )
        for parent_label, (
            measurement_bounds,
            _,
            _,
        ) in measurement.items():
            direct_record = direct.get(parent_label)
            extents.append(
                CoreExtent(
                    parent_label=parent_label,
                    direct_bounds=(
                        None if direct_record is None else direct_record[0]
                    ),
                    measurement_bounds=measurement_bounds,
                    first_pixel_yx=(
                        None if direct_record is None else direct_record[1]
                    ),
                    tile_id=request.partition.tile_id,
                    direct_pixel_count=(
                        0 if direct_record is None else direct_record[2]
                    ),
                )
            )
    return ExtentBatchResult(extents=tuple(extents))


def _deferred(parent: ParentExtent, deblend: CompactDeblendConfig) -> bool:
    """Return whether a parent is deferred, from its reconciled extent."""
    return parent_is_deferred(
        parent.direct_bounds, parent.direct_pixel_count, deblend
    )


def _parent_batches(
    parents: tuple[ParentExtent, ...],
    *,
    core_shape_yx: tuple[int, int],
    maximum_batch_read_pixels: int,
    deblend: CompactDeblendConfig,
) -> tuple[_ParentBatch, ...]:
    """Group parents so one read serves several, within the budget.

    Deblending needs a parent's whole support at once, and no core can stand
    in for it. The reviewed compact bounds limit that support: a parent
    beyond either is deferred and never reaches a batch, so an admitted
    parent's direct window is within ``maximum_compact_bounds_pixels``, and
    its measurement support reaches no further beyond it than the reviewed
    recovery radius the support pass attaches it within. So a parent wider
    than the read budget is read alone, and its read is bounded by that
    admission, not by the image.

    Raises:
        ValueError: If a deferred parent reaches a batch, which would leave
            its read bounded by nothing.
    """
    return tuple(
        _ParentBatch(parents=batch.objects, read_bounds=batch.read_bounds)
        for batch in batch_object_windows(
            parents,
            window=lambda parent: parent.measurement_bounds,
            core_shape_yx=core_shape_yx,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
            bounded_by_admission=lambda parent: not _deferred(parent, deblend),
        )
    )


def _deblend_parents(
    batch: _ParentBatch,
    *,
    support_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    deblend: CompactDeblendConfig,
    image_shape_yx: tuple[int, int],
) -> tuple[ParentComponentMembership, ...]:
    """Deblend every parent of one batch inside its own windows.

    The caller holds both sources' access sessions open. A parent's windows
    are its reconciled extents, whatever read serves them, so every task that
    deblends one parent decides the same memberships.
    """
    bounds = batch.read_bounds
    direct_snr = np.asarray(
        detection_source.read_completed_window("direct-snr", bounds),
        dtype=np.float64,
    )
    valid = np.asarray(
        detection_source.read_completed_window("valid-pixels", bounds),
        dtype=np.bool_,
    )
    normalized = np.where(valid, direct_snr, np.nan)
    direct_labels = np.asarray(
        support_source.read_completed_window("component-labels", bounds),
        dtype=np.int32,
    )
    measurement_labels = np.asarray(
        support_source.read_completed_window("measurement-labels", bounds),
        dtype=np.int32,
    )
    memberships: list[ParentComponentMembership] = []
    for parent in batch.parents:
        direct_crop = crop_slices(bounds, parent.direct_bounds)
        measurement_crop = crop_slices(bounds, parent.measurement_bounds)
        memberships.append(
            deblend_parent_components(
                normalized[direct_crop],
                direct_labels[direct_crop] == parent.parent_label,
                measurement_labels[measurement_crop] == parent.parent_label,
                valid[measurement_crop],
                parent_label=parent.parent_label,
                direct_bounds=parent.direct_bounds,
                measurement_bounds=parent.measurement_bounds,
                image_shape_yx=image_shape_yx,
                first_pixel_yx=parent.first_pixel_yx,
                config=deblend,
            )
        )
    return tuple(memberships)


def _deblend_batch(
    batch: _ParentBatch,
    *,
    support_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
) -> _DeblendBatchResult:
    """Count the components every parent of one batch deblends into."""
    memberships = _deblend_parents(
        batch,
        support_source=support_source,
        detection_source=detection_source,
        deblend=config.deblend,
        image_shape_yx=image_shape_yx,
    )
    return _DeblendBatchResult(
        parents=tuple(
            _ParentCount(
                parent_label=parent.parent_label,
                component_count=membership.component_count,
                deferred=membership.deferred,
            )
            for parent, membership in zip(
                batch.parents, memberships, strict=True
            )
        ),
        maximum_parent_read_pixels=read_pixels(batch.read_bounds),
    )


def _numbered_parents(
    parents: tuple[ParentExtent, ...],
    counts: Mapping[int, _ParentCount],
) -> tuple[dict[int, int], dict[int, int], int]:
    """Offset each parent's local components into canonical global labels.

    ``parents`` is in canonical order, so numbering does not move with tile
    geometry or completion order. A parent absent from ``counts`` is
    deferred, and one component. Returns the label of every parent published
    as one component, the offset of every deblended parent's local labels,
    and the number of components.
    """
    single_components: dict[int, int] = {}
    component_offsets: dict[int, int] = {}
    next_label = 1
    for extent in parents:
        count = counts.get(extent.parent_label)
        component_count = 1 if count is None else count.component_count
        if component_count == 1:
            single_components[extent.parent_label] = next_label
        else:
            component_offsets[extent.parent_label] = next_label - 1
        next_label += component_count
    return single_components, component_offsets, next_label - 1


def _write_requests(
    manifest: PartitionManifest,
    parents: tuple[ParentExtent, ...],
    *,
    single_components: Mapping[int, int],
    component_offsets: Mapping[int, int],
    holders: Mapping[int, frozenset[str]],
) -> tuple[_TileRequest, ...]:
    """Shard every numbered parent to the cores that hold its pixels.

    Each parent is visited once and appended to its holders, so the shards
    cost the parents' holdings rather than parents times cores.
    """
    held_single: dict[str, list[tuple[int, int]]] = {}
    held_deblended: dict[str, list[_NumberedParent]] = {}
    for extent in parents:
        label = extent.parent_label
        for tile_id in holders[label]:
            if label in single_components:
                held_single.setdefault(tile_id, []).append(
                    (label, single_components[label])
                )
            else:
                held_deblended.setdefault(tile_id, []).append(
                    _NumberedParent(
                        parent=extent,
                        component_offset=component_offsets[label],
                    )
                )
    return tuple(
        _TileRequest(
            partition=partition,
            single_components=tuple(held_single.get(partition.tile_id, ())),
            deblended_parents=tuple(held_deblended.get(partition.tile_id, ())),
        )
        for partition in manifest.tiles
    )


def _relabel_single_parents(
    planes: tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]],
    parent_planes: tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]],
    single_components: tuple[tuple[int, int], ...],
) -> None:
    """Write each single-component parent's label over its pixels, in place.

    Such a parent is published unchanged, so its component is exactly the
    parent's own support in each plane, and the core reads that support
    from its own window instead of receiving the pixels. Parents are looked
    up by sorted label, so one pass over the core serves all of them.
    """
    ordered = sorted(single_components)
    parent_labels = np.asarray([label for label, _ in ordered], dtype=np.int64)
    component_labels = np.asarray(
        [component for _, component in ordered], dtype=np.int32
    )
    for plane, parent_plane in zip(planes, parent_planes, strict=True):
        index = np.searchsorted(parent_labels, parent_plane)
        found = index < parent_labels.size
        found[found] = parent_labels[index[found]] == parent_plane[found]
        plane[found] = component_labels[index[found]]


def _write_owned_components(
    plane: npt.NDArray[np.int32],
    core: ImageBounds,
    window: ImageBounds,
    local_labels: npt.NDArray[np.int32],
    component_offset: int,
) -> None:
    """Write one parent's numbered components over the core pixels it owns."""
    if not bounds_intersect(core, window):
        return
    overlap = ImageBounds(
        max(core.y_start, window.y_start),
        min(core.y_stop, window.y_stop),
        max(core.x_start, window.x_start),
        min(core.x_stop, window.x_stop),
    )
    owned = local_labels[crop_slices(window, overlap)]
    np.copyto(
        plane[crop_slices(core, overlap)],
        owned + np.int32(component_offset),
        where=owned > 0,
    )


def _write_deblended_parents(  # noqa: PLR0913
    planes: tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]],
    core: ImageBounds,
    deblended_parents: tuple[_NumberedParent, ...],
    *,
    support_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
    core_shape_yx: tuple[int, int],
) -> int:
    """Decide each deblended parent again and write the part a core owns.

    Returns the widest read this took. The parents are admitted, so each
    batch's read is bounded by the budget or by that admission.
    """
    offsets = {
        numbered.parent.parent_label: numbered.component_offset
        for numbered in deblended_parents
    }
    widest_read = 0
    for batch in _parent_batches(
        tuple(numbered.parent for numbered in deblended_parents),
        core_shape_yx=core_shape_yx,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        deblend=config.deblend,
    ):
        memberships = _deblend_parents(
            batch,
            support_source=support_source,
            detection_source=detection_source,
            deblend=config.deblend,
            image_shape_yx=image_shape_yx,
        )
        for parent, membership in zip(batch.parents, memberships, strict=True):
            offset = offsets[parent.parent_label]
            _write_owned_components(
                planes[0],
                core,
                parent.direct_bounds,
                membership.direct_labels,
                offset,
            )
            _write_owned_components(
                planes[1],
                core,
                parent.measurement_bounds,
                membership.measurement_labels,
                offset,
            )
        widest_read = max(widest_read, read_pixels(batch.read_bounds))
    return widest_read


def _publish_batch(  # noqa: PLR0913
    batch: _TileBatch,
    *,
    support_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    sink: ZarrProductSink,
    config: ComponentTopologyStageConfig,
    image_shape_yx: tuple[int, int],
    core_shape_yx: tuple[int, int],
) -> PublishBatchResult:
    """Write the component labels each core of one batch owns.

    The core that writes both planes is where their agreement is decided, so
    it checks it: a direct owner must be scientifically valid and must carry
    the same label in the measurement plane. Asking the same question later
    would need both whole planes at once.

    Raises:
        ValueError: If a core's direct ownership is not a valid subset of its
            measurement ownership.
    """
    chunks: list[ProductChunk] = []
    observed: set[tuple[int, int]] = set()
    widest_read = 0
    for request in batch.requests:
        core = request.partition.core_bounds
        direct = np.zeros(core.shape_yx, dtype=np.int32)
        measurement = np.zeros(core.shape_yx, dtype=np.int32)
        if request.single_components:
            _relabel_single_parents(
                (direct, measurement),
                (
                    np.asarray(
                        support_source.read_completed_window(
                            "component-labels", core
                        ),
                        dtype=np.int32,
                    ),
                    np.asarray(
                        support_source.read_completed_window(
                            "measurement-labels", core
                        ),
                        dtype=np.int32,
                    ),
                ),
                request.single_components,
            )
        if request.deblended_parents:
            widest_read = max(
                widest_read,
                _write_deblended_parents(
                    (direct, measurement),
                    core,
                    request.deblended_parents,
                    support_source=support_source,
                    detection_source=detection_source,
                    config=config,
                    image_shape_yx=image_shape_yx,
                    core_shape_yx=core_shape_yx,
                ),
            )
        valid = np.asarray(
            detection_source.read_completed_window("valid-pixels", core),
            dtype=np.bool_,
        )
        if bool(np.any((direct > 0) & (~valid | (measurement != direct)))):
            raise ValueError(
                "direct component ownership must be a valid subset of "
                "measurement ownership"
            )
        observed.update(
            (int(value), plane_index)
            for plane_index, plane in enumerate((direct, measurement))
            for value in np.unique(plane)
            if value > 0
        )
        chunks.extend(
            sink.write_chunk(
                product_name=product_name,
                tile=request.partition,
                values=values,
            )
            for product_name, values in zip(
                _TOPOLOGY_PRODUCT_NAMES, (direct, measurement), strict=True
            )
        )
    return PublishBatchResult(
        product_chunks=tuple(chunks),
        observed_labels=tuple(sorted(observed)),
        maximum_parent_read_pixels=widest_read,
    )


def _tile_batches(
    requests: tuple[_TileRequest, ...],
    *,
    maximum_tiles_per_batch: int,
) -> tuple[_TileBatch, ...]:
    """Group canonical cores without changing scientific ownership."""
    return tuple(
        _TileBatch(requests=requests[start : start + maximum_tiles_per_batch])
        for start in range(0, len(requests), maximum_tiles_per_batch)
    )


def _validate_stage_inputs(
    support_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    manifest: PartitionManifest,
    sink: ZarrProductSink,
) -> None:
    """Fail before output initialization when identities cannot compose."""
    if sink.manifest != manifest:
        raise ValueError("component sink must use the stage manifest")
    if manifest.halo_yx != (0, 0):
        raise ValueError("component topology writes cores without a halo")
    for source, names in (
        (support_source, ("component-labels", "measurement-labels")),
        (detection_source, ("direct-snr", "valid-pixels")),
    ):
        if source.manifest.image_shape_yx != manifest.image_shape_yx:
            raise ValueError(
                "published generations must match the component image shape"
            )
        if not set(names).issubset(source.read_generation().product_names):
            raise ValueError(
                "published generations must carry every component plane read"
            )


def _require_matching_component_identities(
    results: tuple[PublishBatchResult, ...],
    component_count: int,
) -> None:
    """Require both published planes to name exactly the same components.

    Each core reported the labels it wrote and the plane that carried them, so
    the identity sets are compared from those summaries rather than from two
    whole planes. Every numbered component must appear in both: a component
    with no direct pixel has no identity, and one with no measurement pixel
    has no support to measure.

    Raises:
        ValueError: If the two planes name different components, or name one
            the numbering never produced.
    """
    named: tuple[set[int], set[int]] = (set(), set())
    for result in results:
        for label_value, plane_index in result.observed_labels:
            named[plane_index].add(label_value)
    expected = set(range(1, component_count + 1))
    if named[0] != expected or named[1] != expected:
        raise ValueError(
            "direct and measurement component identities must match"
        )


def run_component_topology_stage(  # noqa: PLR0913
    support_source: CompletedProductSource,
    detection_source: CompletedProductSource,
    manifest: PartitionManifest,
    *,
    config: ComponentTopologyStageConfig,
    executor: Executor,
    sink: ZarrProductSink,
) -> ComponentTopologyStageResult:
    """Deblend every parent in its own window and publish the components.

    Three rounds: the cores observe each parent's extent, one task per batch
    of parents deblends them inside those extents and counts their
    components, and the cores write the component labels they own. Parent
    order is canonical, so the component numbering does not move with tile
    geometry or completion order.

    The driver holds records only. A parent published as one component is
    its own support in both planes, so the cores that hold it relabel it from
    their own windows. That covers a parent beyond either hard compact-work
    bound, which is deferred exactly as the whole-plane deblender defers it,
    from its extent alone, and whose window is never read. A parent that
    splits is deblended again by each core that holds it, inside the same
    windows, which decides the same memberships; returning them instead
    would make the driver hold every component pixel in the image.
    """
    _validate_stage_inputs(support_source, detection_source, manifest, sink)
    scan_batches = _tile_batches(
        tuple(
            _TileRequest(partition=partition) for partition in manifest.tiles
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    scan_results = tuple(
        executor.map_batches(
            partial(_scan_extents, support_source=support_source),
            scan_batches,
            requirement=read_requirement(
                EXTENT_SCAN_BYTES_PER_READ_PIXEL,
                (partition.read_bounds for partition in manifest.tiles),
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
        )
    )
    if not scan_results:
        raise ValueError("executor returned no parent extent results")
    parents = reduce_extents(scan_results)
    parent_batches = _parent_batches(
        tuple(
            parent
            for parent in parents
            if not _deferred(parent, config.deblend)
        ),
        core_shape_yx=manifest.tile_core_shape_yx,
        maximum_batch_read_pixels=config.maximum_batch_read_pixels,
        deblend=config.deblend,
    )
    deblend_results = map_round(
        executor,
        partial(
            _deblend_batch,
            support_source=support_source,
            detection_source=detection_source,
            config=config,
            image_shape_yx=manifest.image_shape_yx,
        ),
        parent_batches,
        round_name="component deblend",
        requirement=read_requirement(
            _DEBLEND_BYTES_PER_READ_PIXEL,
            (batch.read_bounds for batch in parent_batches),
            chunk_shape_yx=manifest.tile_core_shape_yx,
        ),
    )
    counts = {
        count.parent_label: count
        for result in deblend_results
        for count in result.parents
    }
    single_components, component_offsets, component_count = _numbered_parents(
        parents, counts
    )
    for product_name in _TOPOLOGY_PRODUCT_NAMES:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype("<i4"),
        )
    publish_batches = _tile_batches(
        _write_requests(
            manifest,
            parents,
            single_components=single_components,
            component_offsets=component_offsets,
            holders=parent_holders(scan_results),
        ),
        maximum_tiles_per_batch=config.maximum_tiles_per_batch,
    )
    publish_results = tuple(
        executor.map_batches(
            partial(
                _publish_batch,
                support_source=support_source,
                detection_source=detection_source,
                sink=sink,
                config=config,
                image_shape_yx=manifest.image_shape_yx,
                core_shape_yx=manifest.tile_core_shape_yx,
            ),
            publish_batches,
            # A parent that splits is deblended again inside its own window,
            # which its round bounded as it bounds the deblend batches.
            requirement=read_requirement(
                _TOPOLOGY_PUBLICATION_BYTES_PER_READ_PIXEL,
                (
                    *(partition.read_bounds for partition in manifest.tiles),
                    *(batch.read_bounds for batch in parent_batches),
                ),
                chunk_shape_yx=manifest.tile_core_shape_yx,
            ),
        )
    )
    if not publish_results:
        raise ValueError("executor returned no component publication results")
    _require_matching_component_identities(publish_results, component_count)
    return ComponentTopologyStageResult(
        generation=sink.publish_generation(
            product_names=_TOPOLOGY_PRODUCT_NAMES,
            chunks=(
                chunk
                for result in publish_results
                for chunk in result.product_chunks
            ),
        ),
        component_count=component_count,
        parent_count=len(parents),
        deblended_parent_count=len(component_offsets),
        deferred_parent_count=len(parents)
        - len(counts)
        + sum(int(count.deferred) for count in counts.values()),
        partition_count=len(manifest.tiles),
        executor_task_count=(
            len(scan_batches) + len(parent_batches) + len(publish_batches)
        ),
        maximum_graph_width=max(
            len(scan_batches),
            len(parent_batches),
            len(publish_batches),
        ),
        maximum_parent_read_pixels=max(
            (
                result.maximum_parent_read_pixels
                for result in (*deblend_results, *publish_results)
            ),
            default=0,
        ),
        parent_batch_count=len(parent_batches),
    )
