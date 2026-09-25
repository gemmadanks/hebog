# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Per-island catalogue rows, against the whole-plane island builder."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from math import log, pi
from pathlib import Path
from typing import TypeVar

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import TileLabelMapping
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.zarr import ZarrProductSink
from hebog.science.catalogues import build_detection_island_catalogue
from hebog.stages.islands import (
    DetectionIslandStageConfig,
    DetectionIslandStageResult,
    _CoreBatch,
    _global_owner_pairs,
    _Island,
    _island_batches,
    _island_mask,
    _IslandBatch,
    _scan_islands,
    run_detection_island_stage,
)
from hebog.validation.tiled_detection import ArrayImageSource

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (64, 96)
_BEAM_MAJOR = 4.0
_BEAM_MINOR = 3.0


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


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
]:
    """Return the image, RMS, retained mask and owner labels.

    The mask is deliberately awkward: one island spans four 16-pixel cores
    through their shared corner, one runs along a core edge, one sits on the
    image's own corner, and one owner's retained support is split between two
    islands, which is why an owner names a tuple of them.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    retained = np.zeros(_SHAPE_YX, dtype=np.bool_)
    # A diagonal filament through the corner where four cores meet.
    for offset in range(-6, 7):
        retained[32 + offset, 32 + offset] = True
        retained[32 + offset, 33 + offset] = True
    # A bar lying along one core boundary.
    retained[16, 60:76] = True
    retained[17, 60:76] = True
    # The image's own top-left corner.
    retained[0:3, 0:3] = True
    # One owner whose support is split into two islands.
    retained[48:51, 8:11] = True
    retained[48:51, 20:23] = True
    owners = np.zeros(_SHAPE_YX, dtype=np.int32)
    owners[retained] = 1
    owners[48:51, 8:11] = 2
    owners[48:51, 20:23] = 2
    owners[0:3, 0:3] = 3
    image = np.where(retained, 6.0, 0.5) + 0.01 * np.asarray(
        xx, dtype=np.float64
    )
    rms = 1.0 + 0.02 * np.asarray(yy, dtype=np.float64)
    return image, rms, retained, owners


def _beam_area_pixels() -> float:
    """Return the beam area the island rows divide their flux by."""
    return pi * _BEAM_MAJOR * _BEAM_MINOR / (4.0 * log(2.0))


def _manifest(core: int) -> PartitionManifest:
    """Plan one core-only partition of the fixture image."""
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(core, core),
        halo_yx=(0, 0),
    )


def _publish(
    root: Path,
    products: tuple[tuple[str, npt.NDArray[np.generic], str], ...],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish one generation of analytic planes over 16-pixel cores."""
    manifest = _manifest(16)
    sink = ZarrProductSink(root, manifest, generation_id=generation_id)
    for product_name, _, dtype in products:
        sink.initialize_product(
            product_name=product_name, dtype=np.dtype(dtype)
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
    retained: npt.NDArray[np.bool_] | None = None,
    owners: npt.NDArray[np.int32] | None = None,
) -> tuple[ZarrProductSink, ...]:
    """Publish every generation the island rounds read."""
    root.mkdir(parents=True, exist_ok=True)
    _, rms, mask, owner_labels = _planes()
    return (
        _publish(
            root / "background.zarr",
            (
                ("background", np.zeros(_SHAPE_YX, dtype=np.float64), "<f8"),
                ("rms", rms, "<f8"),
            ),
            generation_id="background-fixture",
        ),
        _publish(
            root / "publication.zarr",
            (
                (
                    "retained-mask",
                    mask if retained is None else retained,
                    "bool",
                ),
            ),
            generation_id="publication-fixture",
        ),
        _publish(
            root / "components.zarr",
            (
                (
                    "component-measurement-labels",
                    owner_labels if owners is None else owners,
                    "<i4",
                ),
            ),
            generation_id="component-fixture",
        ),
    )


def _config(**overrides: object) -> DetectionIslandStageConfig:
    """Return the island configuration with one field replaced."""
    fields: dict[str, object] = {
        "beam_area_pixels": _beam_area_pixels(),
        "maximum_tiles_per_batch": 2,
        "maximum_objects_per_batch": 2,
        "maximum_batch_read_pixels": 65536,
        **overrides,
    }
    return DetectionIslandStageConfig(**fields)  # type: ignore[arg-type]


def _run(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    retained: npt.NDArray[np.bool_] | None = None,
    owners: npt.NDArray[np.int32] | None = None,
    **overrides: object,
) -> DetectionIslandStageResult:
    """Measure every island's row, in isolation."""
    background, publication, components = _sources(
        root, retained=retained, owners=owners
    )
    image, _, _, _ = _planes()
    return run_detection_island_stage(
        ArrayImageSource(image, np.ones(_SHAPE_YX, dtype=np.bool_)),
        background,
        publication,
        components,
        _manifest(core),
        config=_config(**overrides),
        executor=SerialExecutor() if executor is None else executor,  # type: ignore[arg-type]
    )


def _whole_plane(
    retained: npt.NDArray[np.bool_] | None = None,
    owners: npt.NDArray[np.int32] | None = None,
):
    """Measure every island over complete planes, as the serial oracle."""
    image, rms, mask, owner_labels = _planes()
    return build_detection_island_catalogue(
        image,
        rms,
        mask if retained is None else retained,
        owner_labels if owners is None else owners,
        beam_area_pixels=_beam_area_pixels(),
    )


def test_published_islands_match_the_whole_plane_catalogue(
    tmp_path: Path,
) -> None:
    """Reconciled per-core labelling reproduces one whole-plane labelling."""
    expected = _whole_plane()

    result = _run(tmp_path / "run")

    assert len(expected.islands) > 3, "the fixture must hold several islands"
    assert result.islands == expected.islands
    assert dict(result.island_ids_by_owner) == dict(
        expected.island_ids_by_owner
    )


def test_an_owner_split_between_islands_names_both(tmp_path: Path) -> None:
    """Split support makes an owner name every island it holds."""
    result = _run(tmp_path / "run")

    assert len(result.island_ids_by_owner[2]) == 2
    assert result.island_ids_by_owner[2] == tuple(
        sorted(result.island_ids_by_owner[2])
    )
    assert all(
        identifier in {island.identifier for island in result.islands}
        for identifiers in result.island_ids_by_owner.values()
        for identifier in identifiers
    )


@pytest.mark.parametrize("core", [16, 24, 32, 64])
def test_islands_are_partition_and_batch_invariant(
    tmp_path: Path, core: int
) -> None:
    """Tile geometry and batching decide which task runs, not the rows."""
    reference = _run(tmp_path / "reference", core=64)

    result = _run(
        tmp_path / f"core-{core}",
        core=core,
        maximum_tiles_per_batch=1,
        maximum_objects_per_batch=1,
        maximum_batch_read_pixels=1,
    )

    assert result.islands == reference.islands
    assert dict(result.island_ids_by_owner) == dict(
        reference.island_ids_by_owner
    )


def test_islands_are_executor_invariant(tmp_path: Path) -> None:
    """Workers measure exactly what one in-process reference measures."""
    reference = _run(tmp_path / "reference")

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result = _run(tmp_path / "dask", executor=DaskExecutor(client))

    assert result.islands == reference.islands
    assert dict(result.island_ids_by_owner) == dict(
        reference.island_ids_by_owner
    )


def test_the_island_stage_publishes_no_plane(tmp_path: Path) -> None:
    """Only these rounds read the island labels, so none is stored."""
    result = _run(tmp_path / "run")

    assert result.island_count == len(result.islands)
    assert result.partition_count == len(_manifest(16).tiles)
    assert result.executor_task_count > result.partition_count // 2
    assert result.maximum_graph_width > 0
    assert result.maximum_island_read_pixels > 0
    assert result.boundary_summary_array_bytes > 0
    assert not any(
        path.name.endswith(".zarr")
        for path in (tmp_path / "run").iterdir()
        if path.name.startswith("island")
    )


def test_an_image_with_no_retained_pixel_measures_nothing(
    tmp_path: Path,
) -> None:
    """An empty mask reaches the reconciliation without fabricating a row."""
    result = _run(
        tmp_path / "run",
        retained=np.zeros(_SHAPE_YX, dtype=np.bool_),
        owners=np.zeros(_SHAPE_YX, dtype=np.int32),
    )

    assert result.islands == ()
    assert dict(result.island_ids_by_owner) == {}
    assert result.island_count == 0
    assert result.maximum_island_read_pixels == 0


def test_a_retained_pixel_without_an_owner_still_publishes_its_island(
    tmp_path: Path,
) -> None:
    """Mask connectivity is not owner support: an island needs no owner."""
    _, _, mask, _ = _planes()

    result = _run(tmp_path / "run", owners=np.zeros(_SHAPE_YX, dtype=np.int32))
    expected = _whole_plane(owners=np.zeros(_SHAPE_YX, dtype=np.int32))

    assert result.islands == expected.islands
    assert dict(result.island_ids_by_owner) == {}
    assert np.any(mask), "the fixture must retain pixels"


@pytest.mark.parametrize("dropped_round", [1, 2])
def test_every_island_round_fails_closed_on_a_silent_executor(
    tmp_path: Path, dropped_round: int
) -> None:
    """A round that returns nothing is an error, never an empty catalogue."""
    with pytest.raises(ValueError, match="executor returned no island"):
        _run(
            tmp_path / f"dropped-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"maximum_tiles_per_batch": 0}, "maximum_tiles_per_batch"),
        ({"maximum_objects_per_batch": 0}, "maximum_objects_per_batch"),
        ({"maximum_batch_read_pixels": 0}, "maximum_batch_read_pixels"),
        ({"beam_area_pixels": 0.0}, "beam_area_pixels"),
        ({"beam_area_pixels": float("nan")}, "beam_area_pixels"),
    ),
)
def test_the_island_stage_rejects_invalid_configuration(
    overrides: dict[str, object], message: str
) -> None:
    """An unbounded task or an impossible beam never reaches the executor."""
    with pytest.raises(ValueError, match=message):
        _config(**overrides)


def test_the_island_rounds_forbid_empty_executor_work_records() -> None:
    """Every executor record names the work it carries."""
    with pytest.raises(ValueError, match="core batch must not be empty"):
        _CoreBatch(partitions=())
    with pytest.raises(ValueError, match="row batch must not be empty"):
        _IslandBatch(islands=(), read_bounds=ImageBounds(0, 1, 0, 1))


def test_the_island_stage_requires_matching_generations(
    tmp_path: Path,
) -> None:
    """Every published identity is checked before a round is submitted."""
    background, publication, components = _sources(tmp_path / "run")
    image, _, _, _ = _planes()
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    haloed = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(32, 32),
        halo_yx=(1, 1),
    )

    def run(
        manifest: PartitionManifest,
        *,
        publication_source: ZarrProductSink | None = None,
    ) -> DetectionIslandStageResult:
        """Run the stage with one identity replaced."""
        return run_detection_island_stage(
            ArrayImageSource(image, np.ones(_SHAPE_YX, dtype=np.bool_)),
            background,
            publication if publication_source is None else publication_source,
            components,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
        )

    with pytest.raises(ValueError, match="without a halo"):
        run(haloed)
    with pytest.raises(ValueError, match="match the island image shape"):
        run(other_shape)
    with pytest.raises(ValueError, match="every island plane read"):
        run(_manifest(16), publication_source=background)


class _ShiftedBoundsSource:
    """An image source that answers with bounds it was not asked for."""

    def __init__(self, source: ArrayImageSource) -> None:
        """Retain the source whose honest answers are then corrupted."""
        self._source = source

    def read_window(self, bounds: ImageBounds):
        """Return the asked-for pixels under one narrower bound."""
        window = self._source.read_window(bounds)
        return replace(
            window,
            bounds=ImageBounds(
                bounds.y_start,
                bounds.y_stop,
                bounds.x_start,
                max(bounds.x_start + 1, bounds.x_stop - 1),
            ),
        )


def test_a_read_that_answers_different_bounds_fails_closed(
    tmp_path: Path,
) -> None:
    """An island is never measured from pixels it did not ask for."""
    background, publication, components = _sources(tmp_path / "run")
    image, _, _, _ = _planes()

    with pytest.raises(ValueError, match="different island bounds"):
        run_detection_island_stage(
            _ShiftedBoundsSource(
                ArrayImageSource(image, np.ones(_SHAPE_YX, dtype=np.bool_))
            ),
            background,
            publication,
            components,
            _manifest(16),
            config=_config(),
            executor=SerialExecutor(),
        )


@pytest.mark.parametrize(
    ("mask", "message"),
    (
        (
            np.zeros((2, 2), dtype=np.bool_),
            "own its canonical first pixel",
        ),
        (
            np.ones((2, 2), dtype=np.bool_),
            "match its reconciled extent",
        ),
    ),
    ids=("absent", "wrong-extent"),
)
def test_an_island_window_must_reproduce_the_reconciled_island(
    mask: npt.NDArray[np.bool_], message: str
) -> None:
    """A window that does not hold the reconciled island is never measured.

    The reconciliation already counted the island's pixels, so the window
    that measures it has to find the same ones: anything else would be a row
    built from truncated or merged pixels.
    """
    island = _Island(
        global_label=1,
        first_pixel_yx=(0, 0),
        pixel_count=3,
        bounds=ImageBounds(0, 2, 0, 2),
    )

    with pytest.raises(ValueError, match=message):
        _island_mask(mask, island)


def test_an_unreconciled_island_observation_fails_closed(
    tmp_path: Path,
) -> None:
    """A core's island must survive reconciliation, or the join stops.

    Every retained pixel is an island member and every island owns a pixel,
    so this round admits no unaccepted island; a reconciliation policy that
    dropped one would otherwise leave an owner naming nothing.
    """
    _, publication, components = _sources(tmp_path / "run")
    manifest = _manifest(64)
    scanned = _scan_islands(
        _CoreBatch(partitions=manifest.tiles),
        publication_source=publication,
        component_source=components,
        image_shape_yx=_SHAPE_YX,
    )
    dropped = tuple(
        TileLabelMapping(
            tile_id=tile.summary.partition.tile_id,
            local_labels=tuple(
                summary.local_label for summary in tile.summary.islands
            ),
            global_labels=tuple(0 for _ in tile.summary.islands),
        )
        for tile in scanned.tiles
    )

    assert scanned.tiles, "the fixture must observe at least one core"
    with pytest.raises(ValueError, match="must be reconciled"):
        _global_owner_pairs(scanned.tiles, dropped)


def test_one_read_serves_several_islands_within_the_budget() -> None:
    """Neighbouring islands share a read; the budget decides how many."""
    islands = (
        _Island(1, (0, 0), 4, ImageBounds(0, 2, 0, 2)),
        _Island(2, (1, 3), 4, ImageBounds(1, 3, 3, 5)),
        _Island(3, (20, 20), 4, ImageBounds(20, 22, 20, 22)),
    )

    shared = _island_batches(
        islands, maximum_objects_per_batch=8, maximum_batch_read_pixels=64
    )
    split = _island_batches(
        islands, maximum_objects_per_batch=1, maximum_batch_read_pixels=64
    )

    assert [batch.read_bounds for batch in shared] == [
        ImageBounds(0, 3, 0, 5),
        ImageBounds(20, 22, 20, 22),
    ]
    assert [
        island.global_label for batch in split for island in batch.islands
    ] == [1, 2, 3]
    assert len(split) == len(islands)
    assert (
        _island_batches(
            (), maximum_objects_per_batch=1, maximum_batch_read_pixels=1
        )
        == ()
    )
