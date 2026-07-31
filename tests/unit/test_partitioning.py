"""Tests for deterministic tile ownership and clipped halos."""

from __future__ import annotations

import pickle
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models import ImageBounds, PartitionManifest, TilePartition


def _one_tile_manifest() -> PartitionManifest:
    """Return a small valid manifest for mutation tests."""
    return plan_image_partitions(
        image_shape_yx=(5, 7),
        tile_core_shape_yx=(8, 8),
        halo_yx=(1, 1),
    )


def test_small_image_uses_one_tile_with_clipped_halo() -> None:
    """A small image keeps the same ownership semantics without fan-out."""
    manifest = _one_tile_manifest()

    assert manifest.image_shape_yx == (5, 7)
    assert len(manifest.tiles) == 1
    tile = manifest.tiles[0]
    assert tile.tile_id == "tile-00000-00000"
    assert tile.core_bounds == ImageBounds(0, 5, 0, 7)
    assert tile.read_bounds == tile.core_bounds
    assert tile.core_slices_yx == (slice(0, 5), slice(0, 7))
    assert pickle.loads(pickle.dumps(manifest)) == manifest


def test_many_tiles_cover_every_pixel_once_and_clip_halos() -> None:
    """Row-major cores partition the plane while read halos may overlap."""
    manifest = plan_image_partitions(
        image_shape_yx=(17, 19),
        tile_core_shape_yx=(8, 8),
        halo_yx=(1, 1),
    )
    ownership = np.zeros(manifest.image_shape_yx, dtype=np.uint8)
    plane = np.arange(17 * 19).reshape(manifest.image_shape_yx)

    for tile in manifest.tiles:
        core = tile.core_bounds
        read = tile.read_bounds
        ownership[
            core.y_start : core.y_stop,
            core.x_start : core.x_stop,
        ] += 1
        read_values = plane[
            read.y_start : read.y_stop,
            read.x_start : read.x_stop,
        ]
        core_values = read_values[tile.core_slices_yx]
        np.testing.assert_array_equal(
            core_values,
            plane[
                core.y_start : core.y_stop,
                core.x_start : core.x_stop,
            ],
        )
        assert 0 <= read.y_start <= core.y_start
        assert core.y_stop <= read.y_stop <= manifest.image_shape_yx[0]
        assert 0 <= read.x_start <= core.x_start
        assert core.x_stop <= read.x_stop <= manifest.image_shape_yx[1]

    np.testing.assert_array_equal(ownership, 1)
    observed_indices = [
        (tile.tile_y_index, tile.tile_x_index) for tile in manifest.tiles
    ]
    assert observed_indices == [
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
        (2, 1),
        (2, 2),
    ]


def test_shifted_partition_origin_preserves_ownership() -> None:
    """A shifted grid creates smaller edge cores but no gaps or overlaps."""
    manifest = plan_image_partitions(
        image_shape_yx=(19, 23),
        tile_core_shape_yx=(8, 8),
        halo_yx=(1, 1),
        partition_origin_yx=(3, 5),
    )
    ownership = np.zeros(manifest.image_shape_yx, dtype=np.uint8)

    for tile in manifest.tiles:
        core = tile.core_bounds
        ownership[
            core.y_start : core.y_stop,
            core.x_start : core.x_stop,
        ] += 1

    np.testing.assert_array_equal(ownership, 1)
    assert manifest.tiles[0].core_bounds == ImageBounds(0, 3, 0, 5)
    assert manifest.tiles[1].core_bounds == ImageBounds(0, 3, 5, 13)


@given(
    height=st.integers(min_value=1, max_value=40),
    width=st.integers(min_value=1, max_value=40),
    core_height=st.integers(min_value=1, max_value=16),
    core_width=st.integers(min_value=1, max_value=16),
)
def test_every_generated_core_has_exactly_one_owner(
    height: int,
    width: int,
    core_height: int,
    core_width: int,
) -> None:
    """Partition ownership is complete for bounded generated geometries."""
    manifest = plan_image_partitions(
        image_shape_yx=(height, width),
        tile_core_shape_yx=(core_height, core_width),
        halo_yx=(0, 0),
    )
    ownership = np.zeros((height, width), dtype=np.uint8)

    for tile in manifest.tiles:
        core = tile.core_bounds
        ownership[
            core.y_start : core.y_stop,
            core.x_start : core.x_stop,
        ] += 1

    assert np.all(ownership == 1)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"image_shape_yx": (0, 8)}, "image shape"),
        ({"tile_core_shape_yx": (0, 8)}, "tile core shape"),
        ({"halo_yx": (-1, 0)}, "halo"),
        ({"halo_yx": (2, 1)}, "one quarter"),
        ({"partition_origin_yx": (-1, 0)}, "partition origin"),
        ({"partition_origin_yx": (8, 0)}, "partition origin"),
    ],
)
def test_rejects_invalid_partition_configuration(
    arguments: dict[str, tuple[int, int]],
    message: str,
) -> None:
    """Invalid geometry fails before a task graph can be constructed."""
    values = {
        "image_shape_yx": (16, 16),
        "tile_core_shape_yx": (8, 8),
        "halo_yx": (1, 1),
        "partition_origin_yx": (0, 0),
    }
    values.update(arguments)

    with pytest.raises(ValueError, match=message):
        plan_image_partitions(**values)


def test_rejects_an_unsupported_manifest_version() -> None:
    """Partition records never guess how to interpret a future schema."""
    with pytest.raises(ValueError, match="schema version"):
        replace(_one_tile_manifest(), schema_version=2)


@pytest.mark.parametrize(
    "changes",
    [
        {"tile_y_index": -1},
        {"tile_x_index": -1},
        {"read_bounds": ImageBounds(1, 5, 0, 7)},
    ],
)
def test_rejects_an_invalid_tile_record(changes: dict[str, object]) -> None:
    """Tile records require non-negative indices and a containing read halo."""
    tile = _one_tile_manifest().tiles[0]

    with pytest.raises(ValueError, match="tile"):
        replace(tile, **changes)


@pytest.mark.parametrize(
    "tiles",
    [
        (),
        (
            TilePartition(
                tile_y_index=1,
                tile_x_index=0,
                core_bounds=ImageBounds(0, 5, 0, 7),
                read_bounds=ImageBounds(0, 5, 0, 7),
            ),
        ),
    ],
)
def test_rejects_an_incomplete_or_misordered_manifest(
    tiles: tuple[TilePartition, ...],
) -> None:
    """A manifest cannot omit ownership or relabel its row-major tiles."""
    with pytest.raises(ValueError, match="tiles"):
        replace(_one_tile_manifest(), tiles=tiles)
