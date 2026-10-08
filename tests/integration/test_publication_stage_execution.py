# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Owner and core rounds of the support pass, against the whole-plane chain."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
    multiscale_recovery_radius_pixels,
    published_owner_labels,
    refine_multiscale_segment_labels,
    refine_persistent_publication_labels,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import (
    DaskExecutor,
    Executor,
    SerialExecutor,
    TaskRequirement,
    ThreadExecutor,
)
from hebog.io.zarr import ZarrProductSink
from hebog.stages.batching import read_pixels
from hebog.stages.publication import (
    PublicationStageConfig,
    PublicationStageResult,
    _owner_batches,
    _OwnerBatch,
    _OwnerRequest,
    _require_every_core,
    _TileBatch,
    _TileRequest,
    publication_product_names,
    run_publication_stage,
)

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (40, 80)
_BEAM = BeamShapePixels(2.0, 1.6, 0.0)
# The smallest core above four times the beam's 4-pixel support halo.
_CORE = 17
_ISLAND_SIGMA = 3.0
_MINIMUM_ISLAND_PIXELS = 7
_HIGH_SNR = 8.0
_WEAK_SNR = 4.0
# Wide enough that the recovery radius reaches across the gap between owners.
_TAILED_BEAM = BeamShapePixels(4.0, 4.0, 0.0)


class _ReverseCompletionExecutor(SerialExecutor):
    """Return completed task records in reverse order."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Evaluate canonically but expose reverse completion order."""
        return list(
            reversed(
                super().map_batches(function, batches, requirement=requirement)
            )
        )


class _EmptyExecutor(SerialExecutor):
    """Drop every submitted result for fail-closed executor testing."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Return no result without evaluating work."""
        del function, batches, requirement
        return []


def _planes() -> tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
]:
    """Return a dumbbell, a compact, a tiny and a faint cross-shaped owner.

    The dumbbell's waist is a single pixel of weak signal to noise, so the
    3x3 opening removes it and refinement splits the owner. That is what the
    owner rounds exist to notice: the split is only visible from the window
    holding both lobes, which spans three 17-pixel cores; the left lobe ends
    exactly on the x=17 edge, as the compact owner 2 does. The faint cross,
    owner 4, is a narrow-beam detection below the 6-sigma boundary floor
    with no 3x3 block, so refinement and then persistence would each remove
    it entirely; it sits on the corner where four 17-pixel cores meet and
    reaches three of them.
    """
    labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    labels[8:13, 8:17] = 1
    labels[8:13, 32:41] = 1
    labels[10, 17:32] = 1
    labels[25:31, 10:17] = 2
    labels[33, 60:63] = 3
    labels[32:37, 51] = 4
    labels[34, 49:54] = 4
    direct_snr = np.full(_SHAPE_YX, -np.inf, dtype=np.float64)
    direct_snr[labels > 0] = _HIGH_SNR
    direct_snr[10, 17:32] = _WEAK_SNR
    direct_snr[labels == 4] = _WEAK_SNR
    reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    reconstruction[7:14, 7:18] = True
    reconstruction[7:14, 31:42] = True
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    return labels, direct_snr, reconstruction, valid


def _detection_islands() -> tuple[DetectedIsland, ...]:
    """Describe each direct owner of the shared fixture."""
    return _islands(_planes()[0])


def _islands(labels: npt.NDArray[np.int32]) -> tuple[DetectedIsland, ...]:
    """Describe each direct owner the way reconciliation would."""
    islands: list[DetectedIsland] = []
    for label_value in (int(value) for value in np.unique(labels[labels > 0])):
        rows, columns = np.nonzero(labels == label_value)
        islands.append(
            DetectedIsland(
                island_id=f"island-{label_value:05d}",
                global_label=label_value,
                pixel_count=int(rows.size),
                bounds=ImageBounds(
                    int(rows.min()),
                    int(rows.max()) + 1,
                    int(columns.min()),
                    int(columns.max()) + 1,
                ),
                peak_signal_to_noise=_HIGH_SNR,
                peak_position_yx=(int(rows[0]), int(columns[0])),
                first_pixel_yx=(int(rows[0]), int(columns[0])),
                touches_image_edge=False,
            )
        )
    return tuple(islands)


def _publish(
    root: Path,
    products: tuple[tuple[str, npt.NDArray[np.generic], str], ...],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish one generation of analytic planes over 16-pixel cores."""
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(root, manifest, generation_id=generation_id)
    for product_name, _, dtype in products:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype(dtype),
        )
    sink.publish_generation(
        product_names=tuple(name for name, _, _ in products),
        chunks=[
            sink.write_chunk(
                product_name=product_name,
                tile=tile,
                values=np.asarray(
                    values[
                        tile.core_bounds.y_start : tile.core_bounds.y_stop,
                        tile.core_bounds.x_start : tile.core_bounds.x_stop,
                    ]
                ),
            )
            for tile in manifest.tiles
            for product_name, values, _ in products
        ],
    )
    return sink


def _sources(
    root: Path,
    *,
    empty: bool = False,
) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish the detection and support generations this pass reads."""
    labels, direct_snr, reconstruction, valid = _planes()
    if empty:
        labels = np.zeros(_SHAPE_YX, dtype=np.int32)
        direct_snr = np.full(_SHAPE_YX, -np.inf, dtype=np.float64)
        reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    return _publish_planes(
        root,
        labels=labels,
        direct_snr=direct_snr,
        reconstruction=reconstruction,
        valid=valid,
        persistent=np.zeros(_SHAPE_YX, dtype=np.bool_),
    )


def _publish_planes(  # noqa: PLR0913
    root: Path,
    *,
    labels: npt.NDArray[np.int32],
    direct_snr: npt.NDArray[np.float64],
    reconstruction: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
    persistent: npt.NDArray[np.bool_],
) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish the two generations of planes the support pass reads."""
    return (
        _publish(
            root / "detection.zarr",
            (
                ("detection-labels", labels, "<i4"),
                ("direct-snr", direct_snr, "<f8"),
                ("reconstruction-mask", reconstruction, "bool"),
                ("valid-pixels", valid, "bool"),
            ),
            generation_id="detection-fixture",
        ),
        _publish(
            root / "support.zarr",
            (("persistent-support", persistent, "bool"),),
            generation_id="support-fixture",
        ),
    )


def _manifest(core: int, *, halo: int | None = None) -> PartitionManifest:
    """Plan one support partition with the exact support halo."""
    halo = _config().halo_pixels if halo is None else halo
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(core, core),
        halo_yx=(halo, halo),
    )


def _config(
    *,
    maximum_tiles_per_batch: int = 2,
    maximum_batch_read_pixels: int = 8192,
    beam: BeamShapePixels = _BEAM,
) -> PublicationStageConfig:
    """Return the reviewed thresholds with bounded task limits."""
    return PublicationStageConfig(
        beam=beam,
        island_threshold_sigma=_ISLAND_SIGMA,
        minimum_island_pixels=_MINIMUM_ISLAND_PIXELS,
        maximum_island_pixels=None,
        maximum_tiles_per_batch=maximum_tiles_per_batch,
        maximum_batch_read_pixels=maximum_batch_read_pixels,
    )


def _run(
    root: Path,
    *,
    core: int = _CORE,
    executor: object | None = None,
    config: PublicationStageConfig | None = None,
) -> tuple[PublicationStageResult, ZarrProductSink]:
    """Execute one isolated publication-stage variant."""
    root.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _sources(root)
    manifest = _manifest(core)
    sink = ZarrProductSink(
        root / "publication.zarr",
        manifest,
        generation_id="publication",
    )
    result = run_publication_stage(
        detection_source,
        support_source,
        manifest,
        detection_islands=_detection_islands(),
        config=_config() if config is None else config,
        executor=(  # type: ignore[arg-type]
            SerialExecutor() if executor is None else executor
        ),
        sink=sink,
    )
    return result, sink


def _published(
    sink: ZarrProductSink,
) -> dict[str, npt.NDArray[np.generic]]:
    """Read every published support plane over the whole image."""
    bounds = ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
    return {
        name: np.asarray(sink.read_completed_window(name, bounds))
        for name in publication_product_names()
    }


def _whole_plane_chain() -> dict[str, npt.NDArray[np.generic]]:
    """Evaluate the support chain over the shared fixture's planes."""
    return _chain(*_planes(), np.zeros(_SHAPE_YX, dtype=np.bool_), beam=_BEAM)


def _chain(  # noqa: PLR0913
    labels: npt.NDArray[np.int32],
    direct_snr: npt.NDArray[np.float64],
    reconstruction: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
    persistent: npt.NDArray[np.bool_],
    *,
    beam: BeamShapePixels,
) -> dict[str, npt.NDArray[np.generic]]:
    """Evaluate the support chain over complete planes, as the oracle."""
    measurement = assign_seeded_multiscale_support(
        labels,
        reconstruction,
        valid,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
    )
    direct_publication = refine_multiscale_segment_labels(
        labels,
        direct_snr,
        reconstruction,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        recovered_minimum_snr=_ISLAND_SIGMA,
    )
    publication = published_owner_labels(
        direct_publication, measurement, flood_labels=labels
    )
    final = refine_persistent_publication_labels(
        measurement,
        publication,
        direct_snr,
        persistent,
    )
    accepted = np.asarray(
        [
            island.global_label
            for island in _islands(labels)
            if island.pixel_count >= _MINIMUM_ISLAND_PIXELS
        ],
        dtype=np.int32,
    )

    def retain(values: npt.NDArray[np.int32]) -> npt.NDArray[np.int32]:
        """Apply the caller's island admission to one label plane."""
        return np.where(np.isin(values, accepted), values, 0).astype(
            np.int32,
            copy=False,
        )

    retained_publication = retain(final)
    return {
        "component-labels": retain(labels),
        "measurement-labels": retain(measurement),
        "publication-labels": retained_publication,
        "retained-mask": np.asarray(retained_publication > 0, dtype=np.bool_),
    }


def test_published_labels_match_the_whole_plane_support_chain(
    tmp_path: Path,
) -> None:
    """Tiled owner and core rounds reproduce the whole-plane kernels."""
    result, sink = _run(tmp_path / "run")

    published = _published(sink)

    expected = _whole_plane_chain()
    for name, values in expected.items():
        np.testing.assert_array_equal(published[name], values, name)
    assert result.accepted_island_count == 3
    assert set(np.unique(published["component-labels"])) == {0, 1, 2, 4}


def test_owner_rounds_fire_on_an_owner_no_core_contains(
    tmp_path: Path,
) -> None:
    """The split and the bridge are both decided, and both change pixels.

    The faint cross is restored by both rounds: refinement and persistence
    would each leave it nothing.
    """
    result, sink = _run(tmp_path / "run")

    published = _published(sink)
    labels, _, _, _ = _planes()

    assert result.restored_owner_count == 2
    assert result.bridged_owner_count == 2
    assert result.published_owner_count >= 2
    # The waist is a single weak pixel: every pixel decision drops it, and
    # only the owner rounds put it back.
    assert published["publication-labels"][10, 20] == 1
    assert bool(published["retained-mask"][10, 20])
    np.testing.assert_array_equal(
        published["publication-labels"] == 4, labels == 4
    )


def test_publication_stage_is_partition_and_executor_invariant(
    tmp_path: Path,
) -> None:
    """One published generation survives geometry, batching and workers."""
    expected = _published(_run(tmp_path / "reference", core=64)[1])
    variants: list[tuple[str, int, object, PublicationStageConfig]] = [
        ("cores-17", _CORE, SerialExecutor(), _config()),
        ("cores-20", 20, SerialExecutor(), _config(maximum_tiles_per_batch=1)),
        (
            "owner-batches",
            _CORE,
            SerialExecutor(),
            _config(maximum_batch_read_pixels=1),
        ),
        ("reverse", _CORE, _ReverseCompletionExecutor(), _config()),
    ]
    for name, core, executor, config in variants:
        _, sink = _run(
            tmp_path / name,
            core=core,
            executor=executor,
            config=config,
        )
        published = _published(sink)
        for product_name, values in expected.items():
            np.testing.assert_array_equal(
                published[product_name],
                values,
                f"{name}:{product_name}",
            )

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=":0",
    ) as client:
        _, sink = _run(tmp_path / "dask", executor=DaskExecutor(client))
    published = _published(sink)
    for product_name, values in expected.items():
        np.testing.assert_array_equal(published[product_name], values)


def test_a_one_pixel_budget_decides_every_owner_from_its_cores(
    tmp_path: Path,
) -> None:
    """No owner window fits a one-pixel budget, so no owner window is read.

    The split is still decided and the bridge still fires, from the cores.
    """
    result, _ = _run(
        tmp_path / "run",
        config=_config(maximum_batch_read_pixels=1),
    )

    assert result.owner_batch_count == 0
    assert result.wide_owner_count == len(_detection_islands())
    assert result.restored_owner_count == 2
    assert result.bridged_owner_count == 2


def test_publication_stage_publishes_the_canonical_product_set(
    tmp_path: Path,
) -> None:
    """The generation carries exactly one chunk per product and core."""
    manifest = _manifest(_CORE)

    result, _ = _run(tmp_path / "run")

    assert set(result.generation.product_names) == set(
        publication_product_names()
    )
    assert len(result.generation.chunks) == len(
        publication_product_names()
    ) * len(manifest.tiles)
    assert result.executor_task_count > 0
    assert result.maximum_graph_width > 0
    assert result.maximum_owner_read_pixels > 0


def test_publication_stage_rejects_a_manifest_without_the_support_halo(
    tmp_path: Path,
) -> None:
    """A halo one pixel short of the support reach cannot decide a core.

    At the 2-pixel beam that is the refinement's own reach, which leaves
    persistence one pixel short.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _sources(tmp_path)
    manifest = _manifest(_CORE, halo=_config().halo_pixels - 1)

    with pytest.raises(ValueError, match="exact support halo"):
        run_publication_stage(
            detection_source,
            support_source,
            manifest,
            detection_islands=_detection_islands(),
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "publication.zarr",
                manifest,
                generation_id="publication",
            ),
        )


def test_publication_stage_fails_closed_on_a_silent_executor(
    tmp_path: Path,
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match="no owner-decision results"):
        _run(tmp_path / "run", executor=_EmptyExecutor())


@pytest.mark.parametrize(
    "maximum_tiles_per_batch, maximum_batch_read_pixels, message",
    [
        (0, 8192, "maximum_tiles_per_batch"),
        (2, 0, "maximum_batch_read_pixels"),
    ],
)
def test_publication_stage_rejects_invalid_configuration(
    maximum_tiles_per_batch: int,
    maximum_batch_read_pixels: int,
    message: str,
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        PublicationStageConfig(
            beam=_BEAM,
            island_threshold_sigma=_ISLAND_SIGMA,
            minimum_island_pixels=_MINIMUM_ISLAND_PIXELS,
            maximum_island_pixels=None,
            maximum_tiles_per_batch=maximum_tiles_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )


class _DropNthMapExecutor(SerialExecutor):
    """Complete every round but one, to prove each fails closed."""

    def __init__(self, dropped_round: int) -> None:
        """Count maps so one chosen round can return nothing."""
        super().__init__()
        self._dropped_round = dropped_round
        self._call_count = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Run every round except the chosen one."""
        self._call_count += 1
        if self._call_count == self._dropped_round:
            return []
        return super().map_batches(function, batches, requirement=requirement)


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no owner-decision results"),
        (2, "no published-owner results"),
        (3, "no owner-decision results"),
        (4, "no publication results"),
    ],
)
def test_every_round_fails_closed_on_a_silent_executor(
    tmp_path: Path,
    dropped_round: int,
    message: str,
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_publication_stage_forbids_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="owner batch must not be empty"):
        _OwnerBatch(requests=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="tile batch must not be empty"):
        _TileBatch(requests=())


def test_publication_stage_requires_a_positive_island_limit() -> None:
    """An island admitted at zero pixels is not a limit."""
    with pytest.raises(ValueError, match="minimum island pixels"):
        PublicationStageConfig(
            beam=_BEAM,
            island_threshold_sigma=_ISLAND_SIGMA,
            minimum_island_pixels=0,
            maximum_island_pixels=None,
            maximum_tiles_per_batch=2,
            maximum_batch_read_pixels=8192,
        )


def test_publication_stage_requires_a_matching_sink(tmp_path: Path) -> None:
    """A sink for another partition cannot receive this stage's cores."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _sources(tmp_path)

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run_publication_stage(
            detection_source,
            support_source,
            _manifest(_CORE),
            detection_islands=_detection_islands(),
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "mismatched.zarr",
                _manifest(32),
                generation_id="mismatched",
            ),
        )


def test_publication_stage_requires_the_planes_and_shape_it_reads(
    tmp_path: Path,
) -> None:
    """Both published generations are checked before any product exists."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _sources(tmp_path)
    halo = _config().halo_pixels
    other_shape = plan_image_partitions(
        image_shape_yx=(24, 24),
        tile_core_shape_yx=(_CORE, _CORE),
        halo_yx=(halo, halo),
    )
    incomplete = ZarrProductSink(
        tmp_path / "incomplete.zarr",
        _manifest(_CORE),
        generation_id="incomplete",
    )
    incomplete.initialize_product(
        product_name="detection-labels",
        dtype=np.dtype("<i4"),
    )
    incomplete.publish_generation(
        product_names=("detection-labels",),
        chunks=[
            incomplete.write_chunk(
                product_name="detection-labels",
                tile=tile,
                values=np.zeros(tile.core_bounds.shape_yx, dtype=np.int32),
            )
            for tile in _manifest(_CORE).tiles
        ],
    )

    with pytest.raises(ValueError, match="match the publication image shape"):
        run_publication_stage(
            detection_source,
            support_source,
            other_shape,
            detection_islands=_detection_islands(),
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "other.zarr",
                other_shape,
                generation_id="other",
            ),
        )
    with pytest.raises(ValueError, match="every support plane read"):
        run_publication_stage(
            detection_source,
            incomplete,
            _manifest(_CORE),
            detection_islands=_detection_islands(),
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "publication-incomplete.zarr",
                _manifest(_CORE),
                generation_id="publication",
            ),
        )


def test_publication_stage_publishes_an_empty_image_without_owner_work(
    tmp_path: Path,
) -> None:
    """An image with no detected island still publishes a complete core set."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _sources(tmp_path, empty=True)
    manifest = _manifest(_CORE)
    sink = ZarrProductSink(
        tmp_path / "publication.zarr",
        manifest,
        generation_id="publication",
    )

    result = run_publication_stage(
        detection_source,
        support_source,
        manifest,
        detection_islands=(),
        config=_config(),
        executor=SerialExecutor(),
        sink=sink,
    )

    published = _published(sink)
    assert result.owner_batch_count == 0
    assert result.restored_owner_count == 0
    assert result.bridged_owner_count == 0
    assert result.accepted_island_count == 0
    assert result.maximum_owner_read_pixels == 0
    for values in published.values():
        assert not np.any(values)


def test_publication_stage_requires_records_for_every_published_owner(
    tmp_path: Path,
) -> None:
    """Island records that do not describe the planes fail loudly."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _sources(tmp_path)
    manifest = _manifest(_CORE)

    with pytest.raises(ValueError, match="identify every local owner"):
        run_publication_stage(
            detection_source,
            support_source,
            manifest,
            detection_islands=_detection_islands()[:1],
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "publication.zarr",
                manifest,
                generation_id="publication",
            ),
        )


def _edge_owner_sources(
    root: Path,
) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish one owner whose direct support stops at a 32-pixel core edge.

    The owner's reconciled bounds end at column 32, so they do not intersect
    the core starting there, while its significant multiscale support reaches
    one column past the edge and refinement recovers it for the owner.
    """
    labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    labels[20:25, 24:32] = 1
    reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    reconstruction[19:26, 23:34] = True
    direct_snr = np.full(_SHAPE_YX, -np.inf, dtype=np.float64)
    direct_snr[(labels > 0) | reconstruction] = _HIGH_SNR
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    return _publish_planes(
        root,
        labels=labels,
        direct_snr=direct_snr,
        reconstruction=reconstruction,
        valid=valid,
        persistent=np.zeros(_SHAPE_YX, dtype=np.bool_),
    )


def _edge_owner_islands() -> tuple[DetectedIsland, ...]:
    """Describe the edge owner the way reconciliation would."""
    return (
        DetectedIsland(
            island_id="island-00001",
            global_label=1,
            pixel_count=40,
            bounds=ImageBounds(20, 25, 24, 32),
            peak_signal_to_noise=_HIGH_SNR,
            peak_position_yx=(20, 24),
            first_pixel_yx=(20, 24),
            touches_image_edge=False,
        ),
    )


def _run_edge_owner(
    root: Path,
    *,
    core: int,
) -> dict[str, npt.NDArray[np.generic]]:
    """Publish the edge owner's support over one partition geometry."""
    root.mkdir(parents=True, exist_ok=True)
    detection_source, support_source = _edge_owner_sources(root)
    manifest = _manifest(core)
    sink = ZarrProductSink(
        root / "publication.zarr",
        manifest,
        generation_id="publication",
    )
    run_publication_stage(
        detection_source,
        support_source,
        manifest,
        detection_islands=_edge_owner_islands(),
        config=_config(),
        executor=SerialExecutor(),
        sink=sink,
    )
    return _published(sink)


def test_recovered_support_survives_a_core_edge_its_owner_stops_short_of(
    tmp_path: Path,
) -> None:
    """Island admission is read-scoped, so tiles keep recovered support.

    The owner's reconciled bounds end exactly at the x=32 core edge, so a
    core-scoped admission shard would omit it from the core starting there and
    clear the column of support refinement recovered for it.
    """
    expected = _run_edge_owner(tmp_path / "one-tile", core=64)
    published = _run_edge_owner(tmp_path / "cores-32", core=32)

    # The recovered column belongs to the owner in both geometries.
    for name in ("measurement-labels", "publication-labels"):
        np.testing.assert_array_equal(
            expected[name][20:25, 32],
            np.ones(5, dtype=np.int32),
            name,
        )
    assert np.all(expected["retained-mask"][20:25, 32])
    for name, values in expected.items():
        np.testing.assert_array_equal(published[name], values, name)


def _dense_core_reach_planes() -> tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
]:
    """Return a corner whose dense core rests on another owner's measurement.

    Owner 1 is a 5x6 block with a one-pixel arm on rows 8 to 10 at x=20;
    owner 2 is a block from x=23. The 2-pixel beam's recovery radius is
    exactly one pixel, so measurement gives the significant column at x=21
    to owner 1 and the one at x=22 to owner 2, whose seed is one pixel
    further. With them, the opening of the measurement support covers x=20
    to 22 on rows 8 to 10, which puts two more opened pixels in the 3x3
    count around (10, 19), the block's corner, and makes it dense core.
    Nothing else keeps that pixel: it is weak and not persistent. So
    persistence at x=19 depends on owner 2's seed at x=23, four pixels away,
    and 20-pixel cores end at x=19.
    """
    labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    labels[10:15, 14:20] = 1
    labels[8:11, 20] = 1
    labels[8:11, 23:28] = 2
    direct_snr = np.full(_SHAPE_YX, -np.inf, dtype=np.float64)
    direct_snr[labels > 0] = _HIGH_SNR
    direct_snr[10, 19] = _WEAK_SNR
    reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    reconstruction[8:11, 21:23] = True
    reconstruction[10, 19] = True
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    return labels, direct_snr, reconstruction, valid


_Planes = tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
]


def test_persistence_reads_measurement_a_whole_recovery_radius_away(
    tmp_path: Path,
) -> None:
    """A core edge four pixels from a deciding seed keeps the corner pixel.

    The dense core counts a 3x3 opening of the measurement labels, three
    pixels, and measurement reaches seeds up to the recovery radius further.
    When that radius is a whole number of pixels, the read must reach one
    pixel beyond the refinement's own reach, or the core at x=0 to 19 drops
    (10, 19) that the whole plane keeps, whether owners are decided from
    their windows or, at a one-pixel budget, from their cores.
    """
    planes = _dense_core_reach_planes()
    persistent = np.zeros(_SHAPE_YX, dtype=np.bool_)
    radius = 0.5 * _BEAM.major_fwhm_pixels
    assert multiscale_recovery_radius_pixels(_BEAM.major_fwhm_pixels) == radius
    expected = _chain(*planes, persistent, beam=_BEAM)
    np.testing.assert_array_equal(
        expected["measurement-labels"][8:11, 21:23],
        np.tile(np.asarray([1, 2], dtype=np.int32), (3, 1)),
    )
    assert expected["publication-labels"][10, 19] == 1

    for name, core, budget in (
        ("one-tile", 80, 8192),
        ("cores-20", 20, 8192),
        ("from-cores", 20, 1),
    ):
        _, published = _run_planes(
            tmp_path / name,
            planes,
            persistent=persistent,
            beam=_BEAM,
            core=core,
            maximum_batch_read_pixels=budget,
        )
        for product_name, values in expected.items():
            np.testing.assert_array_equal(
                published[product_name], values, f"{name}:{product_name}"
            )


def _run_planes(  # noqa: PLR0913
    root: Path,
    planes: _Planes,
    *,
    persistent: npt.NDArray[np.bool_],
    beam: BeamShapePixels,
    core: int,
    executor: Executor | None = None,
    maximum_batch_read_pixels: int = 8192,
) -> tuple[PublicationStageResult, dict[str, npt.NDArray[np.generic]]]:
    """Publish one fixture's support over one geometry, budget and executor."""
    root.mkdir(parents=True, exist_ok=True)
    labels, direct_snr, reconstruction, valid = planes
    detection_source, support_source = _publish_planes(
        root,
        labels=labels,
        direct_snr=direct_snr,
        reconstruction=reconstruction,
        valid=valid,
        persistent=persistent,
    )
    config = _config(
        beam=beam,
        maximum_batch_read_pixels=maximum_batch_read_pixels,
    )
    manifest = _manifest(core, halo=config.halo_pixels)
    sink = ZarrProductSink(
        root / "publication.zarr",
        manifest,
        generation_id="publication",
    )
    result = run_publication_stage(
        detection_source,
        support_source,
        manifest,
        detection_islands=_islands(labels),
        config=config,
        executor=SerialExecutor() if executor is None else executor,
        sink=sink,
    )
    return result, _published(sink)


def _tailed_owner_planes() -> tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
]:
    """Return an owner whose thin tail ends nearer a neighbour's block.

    Owner 1 is a 5x5 block with a one-pixel tail four rows long; owner 2 is
    a block two rows below the tail's end, apart as two flood islands are.
    All of it is weak, so the opening removes the tail. Multiscale support
    recovers the tail's last pixel, whose nearest opened pixel is owner 2's,
    and persists there. 21-pixel cores cut the block and owner 2 at x=21 and
    put the tail's last pixel in the row of cores below the block; 24-pixel
    cores cut owner 2 at y=24 and end it exactly on the x=24 edge.
    """
    labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    labels[13:18, 18:23] = 1
    labels[18:22, 20] = 1
    labels[23:26, 17:24] = 2
    direct_snr = np.full(_SHAPE_YX, -np.inf, dtype=np.float64)
    direct_snr[labels > 0] = _WEAK_SNR
    reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    reconstruction[21, 20] = True
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    return labels, direct_snr, reconstruction, valid


def _run_tailed_owner(
    root: Path,
    *,
    core: int,
    executor: Executor,
    maximum_batch_read_pixels: int,
) -> tuple[PublicationStageResult, dict[str, npt.NDArray[np.generic]]]:
    """Publish the tailed owner's support over one geometry and executor."""
    planes = _tailed_owner_planes()
    return _run_planes(
        root,
        planes,
        persistent=planes[2],
        beam=_TAILED_BEAM,
        core=core,
        executor=executor,
        maximum_batch_read_pixels=maximum_batch_read_pixels,
    )


def test_a_tailed_owner_is_restored_and_published_in_one_part(
    tmp_path: Path,
) -> None:
    """Every geometry, budget and executor publishes the whole-plane support.

    The tail's last pixel stays owner 1's, so the restore round finds cleanup
    split owner 1 and restores it, and the bridge round joins the block to
    that pixel through the restored tail. While refinement gave the pixel to
    owner 2, owner 1 was published in two parts that nothing joined, and the
    bridge round refused it.
    """
    labels, direct_snr, reconstruction, valid = _tailed_owner_planes()
    expected = _chain(
        labels,
        direct_snr,
        reconstruction,
        valid,
        reconstruction,
        beam=_TAILED_BEAM,
    )
    owner = expected["publication-labels"] == 1
    _, owner_parts = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage_label(owner, structure=np.ones((3, 3), dtype=np.int8)),
    )
    assert owner_parts == 1
    assert np.all(owner[18:22, 20])

    def check(name: str, core: int, executor: Executor, budget: int) -> None:
        """Run one variant and require the whole-plane products."""
        result, published = _run_tailed_owner(
            tmp_path / name,
            core=core,
            executor=executor,
            maximum_batch_read_pixels=budget,
        )
        assert result.restored_owner_count == 1, name
        assert result.bridged_owner_count == 1, name
        for product_name, values in expected.items():
            np.testing.assert_array_equal(
                published[product_name], values, f"{name}:{product_name}"
            )

    check("one-tile", 80, SerialExecutor(), 8192)
    check("cores-21", 21, SerialExecutor(), 8192)
    check("cores-24-reverse", 24, _ReverseCompletionExecutor(), 8192)
    check("from-cores", 21, SerialExecutor(), 1)
    with ThreadExecutor(2) as threads:
        check("threads", 21, threads, 8192)
    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=":0",
    ) as client:
        check("dask-from-cores", 21, DaskExecutor(client), 1)


def _support_apart_from_owners() -> _Planes:
    """Return two owners with significant support apart from their floods.

    Owner 1 is a block whose bounds end on the x=21 and y=21 core edges.
    One pixel beyond them at 2 sigma, significant at 4 sigma, is a recovered
    pixel outside every flood two pixels from the block. Owner 3, whose
    bounds end on the x=42 core edge, has pixel (25, 43) two pixels away in
    a straight line across an unsupported column; the support joins it to
    owner 3 only along a strand to owner 5's block and a detour back along
    row 29.
    """
    labels = np.zeros(_SHAPE_YX, dtype=np.int32)
    labels[16:21, 16:21] = 1
    labels[22:29, 39:42] = 3
    labels[24:27, 51:54] = 5
    direct_snr = np.full(_SHAPE_YX, -np.inf, dtype=np.float64)
    direct_snr[labels > 0] = _HIGH_SNR
    reconstruction = np.zeros(_SHAPE_YX, dtype=np.bool_)
    reconstruction[18, 21:23] = True
    reconstruction[25, 43:51] = True
    reconstruction[27:30, 52] = True
    reconstruction[29, 42:53] = True
    direct_snr[reconstruction] = 2.0
    direct_snr[18, 22] = _WEAK_SNR
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    return labels, direct_snr, reconstruction, valid


def test_support_apart_from_an_owner_is_neither_measured_nor_published_for_it(
    tmp_path: Path,
) -> None:
    """Every geometry, budget and executor attaches support along owners.

    By straight-line distance, measurement gave pixel (25, 43) to owner 3,
    which held it apart from its flood, and publication gave the recovered
    pixel (18, 22) to owner 1 apart from its block; persisting without the
    pixel between, it stopped the bridge round with a bare ``ValueError``
    (plan task 64). Neither is attached now, from any core geometry.
    """
    planes = _support_apart_from_owners()
    persistent = np.zeros(_SHAPE_YX, dtype=np.bool_)
    persistent[18, 22] = True
    expected = _chain(*planes, persistent, beam=_TAILED_BEAM)
    assert expected["measurement-labels"][18, 22] == 1
    assert expected["measurement-labels"][25, 43] == 0
    np.testing.assert_array_equal(
        np.asarray(expected["publication-labels"], dtype=np.int32) > 0,
        planes[0] > 0,
    )

    def check(name: str, core: int, executor: Executor, budget: int) -> None:
        """Run one variant and require the whole-plane products."""
        _, published = _run_planes(
            tmp_path / name,
            planes,
            persistent=persistent,
            beam=_TAILED_BEAM,
            core=core,
            executor=executor,
            maximum_batch_read_pixels=budget,
        )
        for product_name, values in expected.items():
            np.testing.assert_array_equal(
                published[product_name], values, f"{name}:{product_name}"
            )

    check("one-tile", 80, SerialExecutor(), 8192)
    check("cores-21", 21, SerialExecutor(), 8192)
    check("cores-24-reverse", 24, _ReverseCompletionExecutor(), 8192)
    check("from-cores", 21, SerialExecutor(), 1)
    with ThreadExecutor(2) as threads:
        check("threads", 21, threads, 8192)
    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=":0",
    ) as client:
        check("dask-from-cores", 21, DaskExecutor(client), 1)


def _owner_reads() -> tuple[int, ...]:
    """Return every owner's read size: its window and the support halo."""
    recovery = multiscale_recovery_radius_pixels(_BEAM.major_fwhm_pixels)
    halo = _config().halo_pixels
    return tuple(
        read_pixels(
            island.bounds.expanded(recovery, _SHAPE_YX).expanded(
                halo, _SHAPE_YX
            )
        )
        for island in _detection_islands()
    )


def test_an_owner_wider_than_the_budget_is_decided_from_its_cores(
    tmp_path: Path,
) -> None:
    """Restoring and bridging a wide owner never reads its window.

    Both are questions about the connected components of one owner's
    pixels, so each core labels its own and the components join across core
    edges. The budget is the second-widest owner's read, so only the
    dumbbell, which spans three 17-pixel cores and is both split by cleanup
    and bridged, takes that path; every read stays within one haloed core or
    a narrow owner's window, below the dumbbell's own window.
    """
    reads = sorted(_owner_reads())
    assert reads[-1] > reads[-2], "the fixture must hold one widest owner"
    core_read = (_CORE + 2 * _config().halo_pixels) ** 2
    assert core_read < reads[-1], "a core read must be narrower than it"

    result, sink = _run(
        tmp_path / "run",
        core=_CORE,
        config=_config(maximum_batch_read_pixels=reads[-2]),
    )

    published = _published(sink)
    for name, values in _whole_plane_chain().items():
        np.testing.assert_array_equal(published[name], values, name)
    assert result.wide_owner_count == 1
    assert result.restored_owner_count == 2
    assert result.bridged_owner_count == 2
    assert result.maximum_owner_read_pixels <= core_read
    assert _run(tmp_path / "default")[0].wide_owner_count == 0


def test_wide_owners_are_executor_invariant(tmp_path: Path) -> None:
    """Workers decide the cores' parts exactly as one process does."""
    expected = _published(_run(tmp_path / "reference", core=64)[1])

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=":0",
    ) as client:
        _, sink = _run(
            tmp_path / "dask",
            executor=DaskExecutor(client),
            config=_config(maximum_batch_read_pixels=1),
        )

    published = _published(sink)
    for product_name, values in expected.items():
        np.testing.assert_array_equal(published[product_name], values)


@pytest.mark.parametrize(
    ("dropped_round", "message"),
    ((1, "no wide owner split results"), (3, "no wide owner bridge results")),
)
def test_every_wide_owner_round_fails_closed_on_a_silent_executor(
    tmp_path: Path, dropped_round: int, message: str
) -> None:
    """With every owner wide, the cores' rounds are the first and third.

    No owner window fits, so the window rounds submit nothing; the second
    round is the published-owner scan.
    """
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / "run",
            executor=_DropNthMapExecutor(dropped_round),
            config=_config(maximum_batch_read_pixels=1),
        )


def test_every_core_a_wide_owner_reaches_must_answer() -> None:
    """A component count taken from part of the cores could be wrong."""
    partition = _manifest(_CORE).tiles[0]
    batches = (
        _TileBatch(
            requests=(
                _TileRequest(
                    partition=partition,
                    seed_references_yx=(),
                    restored_owners=(),
                    wide_owners=(1,),
                ),
            )
        ),
    )

    _require_every_core(batches, (partition.tile_id,), question="split")
    with pytest.raises(ValueError, match="must answer its split"):
        _require_every_core(batches, (), question="split")


def test_an_owner_window_wider_than_the_budget_is_never_batched() -> None:
    """Such an owner is decided from its cores, so no batch may read it."""
    wide = _OwnerRequest(
        label_value=1,
        window=ImageBounds(0, 3, 0, 3),
        read_bounds=ImageBounds(0, 4, 0, 4),
    )

    with pytest.raises(ValueError, match="wider than the read budget"):
        _owner_batches((wide,), maximum_batch_read_pixels=8)
