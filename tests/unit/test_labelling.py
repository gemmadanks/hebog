"""Analytic tests for local labelling and deterministic reconciliation."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from hebog.algorithms.detection import detect_threshold_masks
from hebog.algorithms.labelling import LocalIslandTile, label_detection_tile
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import (
    DetectedIsland,
    ReconciledIslands,
    apply_reconciled_labels,
    reconcile_island_tiles,
)
from hebog.config import SourceFinderConfig
from hebog.data_models.partitioning import PartitionManifest


def _config(
    *,
    minimum_island_pixels: int = 1,
    maximum_island_pixels: int | None = None,
) -> SourceFinderConfig:
    """Return an explicit five/three compact-detection profile."""
    return SourceFinderConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=minimum_island_pixels,
        maximum_island_pixels=maximum_island_pixels,
    )


def _label_tiles(
    normalized: npt.NDArray[np.float64],
    *,
    tile_shape_yx: tuple[int, int],
    partition_origin_yx: tuple[int, int] = (0, 0),
    config: SourceFinderConfig | None = None,
) -> tuple[PartitionManifest, tuple[LocalIslandTile, ...]]:
    """Detect and label every owned core in one analytic SNR plane."""
    scientific_config = config or _config()
    manifest = plan_image_partitions(
        image_shape_yx=normalized.shape,
        tile_core_shape_yx=tile_shape_yx,
        halo_yx=(0, 0),
        partition_origin_yx=partition_origin_yx,
    )
    tiles: list[LocalIslandTile] = []
    for partition in manifest.tiles:
        bounds = partition.core_bounds
        selection = (
            slice(bounds.y_start, bounds.y_stop),
            slice(bounds.x_start, bounds.x_stop),
        )
        values = normalized[selection]
        masks = detect_threshold_masks(
            values,
            np.ones(values.shape, dtype=np.bool_),
            np.zeros(values.shape),
            np.ones(values.shape),
            scientific_config,
        )
        tiles.append(
            label_detection_tile(
                masks,
                partition,
                image_shape_yx=normalized.shape,
            )
        )
    return manifest, tuple(tiles)


def _mask_from_tiles(
    manifest: PartitionManifest,
    tiles: tuple[LocalIslandTile, ...],
    reconciliation: ReconciledIslands,
) -> npt.NDArray[np.bool_]:
    """Assemble one small analytic mask from reconciled owned cores."""
    mask = np.zeros(manifest.image_shape_yx, dtype=np.bool_)
    for tile in tiles:
        bounds = tile.partition.core_bounds
        mask[
            bounds.y_start : bounds.y_stop,
            bounds.x_start : bounds.x_stop,
        ] = apply_reconciled_labels(tile, reconciliation) > 0
    return mask


def test_one_tile_uses_eight_connectivity_and_global_properties() -> None:
    """Diagonal island pixels form one accepted component with stable facts."""
    normalized = np.zeros((5, 6), dtype=np.float64)
    normalized[0, 0] = 4.0
    normalized[1, 1] = 6.0
    manifest, tiles = _label_tiles(normalized, tile_shape_yx=(8, 8))

    reconciliation = reconcile_island_tiles(manifest, tiles, _config())

    assert len(reconciliation.islands) == 1
    island = reconciliation.islands[0]
    assert island.island_id == "island-00001"
    assert island.pixel_count == 2
    assert island.first_pixel_yx == (0, 0)
    assert island.peak_position_yx == (1, 1)
    assert island.peak_signal_to_noise == 6.0
    assert island.touches_image_edge
    assert island.bounds.y_start == 0
    assert island.bounds.y_stop == 2
    assert island.bounds.x_start == 0
    assert island.bounds.x_stop == 2


def test_global_size_and_seed_cuts_apply_after_reconciliation() -> None:
    """A cross-fragment island is filtered only after global aggregation."""
    normalized = np.zeros((3, 6), dtype=np.float64)
    normalized[1, 2:5] = [4.0, 6.0, 4.0]
    manifest, tiles = _label_tiles(normalized, tile_shape_yx=(3, 3))

    accepted = reconcile_island_tiles(
        manifest,
        tiles,
        _config(minimum_island_pixels=3, maximum_island_pixels=3),
    )
    rejected_minimum = reconcile_island_tiles(
        manifest,
        tiles,
        _config(minimum_island_pixels=4),
    )
    rejected_maximum = reconcile_island_tiles(
        manifest,
        tiles,
        _config(maximum_island_pixels=2),
    )

    assert len(accepted.islands) == 1
    assert rejected_minimum.islands == ()
    assert rejected_maximum.islands == ()
    assert not _mask_from_tiles(
        manifest,
        tiles,
        rejected_minimum,
    ).any()


def test_component_without_strict_detection_seed_is_rejected() -> None:
    """Island-threshold emission alone cannot create an accepted island."""
    normalized = np.full((3, 3), 4.0)
    manifest, tiles = _label_tiles(normalized, tile_shape_yx=(4, 4))

    reconciliation = reconcile_island_tiles(manifest, tiles, _config())

    assert reconciliation.islands == ()
    assert not _mask_from_tiles(manifest, tiles, reconciliation).any()


def test_side_and_four_tile_corner_connections_reconcile_once() -> None:
    """Side and diagonal corner fragments are neither lost nor duplicated."""
    normalized = np.zeros((6, 6), dtype=np.float64)
    normalized[2, 1:4] = [4.0, 6.0, 4.0]
    normalized[3, 3] = 4.0
    normalized[4, 4] = 4.0
    manifest, tiles = _label_tiles(normalized, tile_shape_yx=(3, 3))

    reconciliation = reconcile_island_tiles(manifest, tiles, _config())

    assert len(reconciliation.islands) == 1
    assert reconciliation.islands[0].pixel_count == 5
    np.testing.assert_array_equal(
        _mask_from_tiles(manifest, tiles, reconciliation),
        normalized >= 3.0,
    )


def test_partition_shape_origin_and_result_order_preserve_islands() -> None:
    """Global membership and identifiers ignore local labels and task order."""
    normalized = np.zeros((9, 10), dtype=np.float64)
    normalized[1:3, 1:3] = [[6.0, 4.0], [4.0, 4.0]]
    normalized[4:7, 4:8] = 4.0
    normalized[5, 6] = 8.0
    normalized[8, 9] = 7.0
    configurations = (
        ((12, 12), (0, 0)),
        ((3, 4), (0, 0)),
        ((4, 3), (2, 1)),
    )
    observed: list[
        tuple[npt.NDArray[np.bool_], tuple[DetectedIsland, ...]]
    ] = []

    for tile_shape, origin in configurations:
        manifest, tiles = _label_tiles(
            normalized,
            tile_shape_yx=tile_shape,
            partition_origin_yx=origin,
        )
        reconciliation = reconcile_island_tiles(
            manifest,
            tuple(reversed(tiles)),
            _config(),
        )
        observed.append(
            (
                _mask_from_tiles(manifest, tiles, reconciliation),
                reconciliation.islands,
            )
        )

    for mask, islands in observed[1:]:
        np.testing.assert_array_equal(mask, observed[0][0])
        assert islands == observed[0][1]
    assert tuple(island.island_id for island in observed[0][1]) == (
        "island-00001",
        "island-00002",
        "island-00003",
    )


def test_empty_detection_has_no_islands_or_mapping_values() -> None:
    """An empty image is a valid deterministic segmentation result."""
    normalized = np.zeros((5, 7), dtype=np.float64)
    manifest, tiles = _label_tiles(normalized, tile_shape_yx=(3, 3))

    reconciliation = reconcile_island_tiles(manifest, tiles, _config())

    assert reconciliation.islands == ()
    assert not _mask_from_tiles(manifest, tiles, reconciliation).any()
