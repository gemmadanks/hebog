"""Deterministic image partition planning."""

from __future__ import annotations

from hebog.data_models.partitioning import PartitionManifest


def plan_image_partitions(
    *,
    image_shape_yx: tuple[int, int],
    tile_core_shape_yx: tuple[int, int],
    halo_yx: tuple[int, int],
    partition_origin_yx: tuple[int, int] = (0, 0),
) -> PartitionManifest:
    """Plan canonical row-major cores and clipped stage read halos."""
    return PartitionManifest.create(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=tile_core_shape_yx,
        halo_yx=halo_yx,
        partition_origin_yx=partition_origin_yx,
    )
