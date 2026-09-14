"""Analytic contracts for bounded compact-deferred island completion."""

from __future__ import annotations

from dataclasses import fields, replace

import numpy as np
import pytest

from hebog.algorithms.deblending import (
    DeferredDeblendIsland,
    PartitionedDeferredIsland,
    extract_deferred_island_shard_membership,
    partition_deferred_islands,
)
from hebog.algorithms.detection import DetectionThresholdMasks
from hebog.algorithms.labelling import (
    LocalIslandTileSummary,
    label_detection_tile,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import (
    ReconciledIslands,
    reconcile_candidate_tiles,
)
from hebog.config import DeferredIslandCompletionConfig
from hebog.data_models.partitioning import PartitionManifest


def _mask() -> np.ndarray:
    """Return one irregular island and one separate compact component."""
    mask = np.zeros((9, 11), dtype=np.bool_)
    mask[1:8, 2:9] = True
    mask[3:6, 4:7] = False
    mask[4, 4:7] = True
    mask[0, 10] = True
    return mask


def _label_manifest(
    mask: np.ndarray,
    manifest: PartitionManifest,
) -> tuple[tuple[LocalIslandTileSummary, ...], ReconciledIslands]:
    """Label one accepted mask through bounded owned cores."""
    tiles: list[LocalIslandTileSummary] = []
    for partition in manifest.tiles:
        bounds = partition.core_bounds
        selected = np.asarray(
            mask[
                bounds.y_start : bounds.y_stop,
                bounds.x_start : bounds.x_stop,
            ],
            dtype=np.bool_,
        )
        normalized = selected.astype(np.float64)
        tiles.append(
            label_detection_tile(
                DetectionThresholdMasks(
                    normalized_residual=normalized,
                    island_membership=selected,
                    detection_seeds=selected,
                    valid_pixel_count=selected.size,
                ),
                partition,
                image_shape_yx=manifest.image_shape_yx,
            ).compact_summary()
        )
    summaries = tuple(tiles)
    return summaries, reconcile_candidate_tiles(manifest, summaries)


def _reconstruct(
    mask: np.ndarray,
    completed: PartitionedDeferredIsland,
) -> np.ndarray:
    """Reconstruct one analytic result through only bounded shard reads."""
    reconstructed = np.zeros(mask.shape, dtype=np.bool_)
    for shard in completed.shards:
        bounds = shard.partition.core_bounds
        selected = mask[
            bounds.y_start : bounds.y_stop,
            bounds.x_start : bounds.x_stop,
        ]
        membership = extract_deferred_island_shard_membership(shard, selected)
        reconstructed[
            bounds.y_start : bounds.y_stop,
            bounds.x_start : bounds.x_stop,
        ] |= membership
    return reconstructed


@pytest.mark.parametrize(
    ("tile_shape", "origin"),
    [
        ((3, 4), (0, 0)),
        ((4, 3), (2, 1)),
        ((5, 5), (1, 2)),
    ],
)
def test_deferred_completion_is_partition_invariant_and_bounded(
    tile_shape: tuple[int, int],
    origin: tuple[int, int],
) -> None:
    """Exact membership and identity do not depend on shard geometry."""
    mask = _mask()
    manifest = plan_image_partitions(
        image_shape_yx=mask.shape,
        tile_core_shape_yx=tile_shape,
        halo_yx=(0, 0),
        partition_origin_yx=origin,
    )
    summaries, reconciliation = _label_manifest(mask, manifest)
    large = max(reconciliation.islands, key=lambda island: island.pixel_count)
    deferred = DeferredDeblendIsland(large, "island-pixel-limit")

    completed = partition_deferred_islands(
        manifest,
        summaries,
        reconciliation,
        (deferred,),
        DeferredIslandCompletionConfig(maximum_tile_pixels=25),
    )[0]
    reordered = partition_deferred_islands(
        manifest,
        tuple(reversed(summaries)),
        reconciliation,
        (deferred,),
        DeferredIslandCompletionConfig(maximum_tile_pixels=25),
    )[0]

    assert reordered == completed
    assert completed.island == large
    assert completed.reason == "island-pixel-limit"
    assert completed.pixel_count == large.pixel_count
    assert completed.maximum_shard_pixels <= 25
    assert len(completed.shards) > 1
    assert sum(shard.pixel_count for shard in completed.shards) == (
        large.pixel_count
    )
    assert all(
        shard.partition.core_bounds.shape_yx[0]
        * shard.partition.core_bounds.shape_yx[1]
        <= 25
        for shard in completed.shards
    )
    expected = np.array(mask, copy=True)
    expected[0, 10] = False
    np.testing.assert_array_equal(_reconstruct(mask, completed), expected)
    assert not any(
        isinstance(getattr(shard, field.name), np.ndarray)
        for shard in completed.shards
        for field in fields(shard)
    )


@pytest.mark.parametrize("maximum", [0, True, 3.5])
def test_deferred_completion_config_requires_a_positive_integer(
    maximum: object,
) -> None:
    """The hard per-task pixel bound cannot be absent or ambiguous."""
    with pytest.raises(ValueError, match="maximum_tile_pixels"):
        DeferredIslandCompletionConfig(
            maximum_tile_pixels=maximum,  # type: ignore[arg-type]
        )


def test_deferred_completion_rejects_tiles_above_the_hard_bound() -> None:
    """A caller cannot submit a completion manifest with oversized cores."""
    mask = _mask()
    manifest = plan_image_partitions(
        image_shape_yx=mask.shape,
        tile_core_shape_yx=(4, 4),
        halo_yx=(0, 0),
    )
    summaries, reconciliation = _label_manifest(mask, manifest)
    large = max(reconciliation.islands, key=lambda island: island.pixel_count)

    with pytest.raises(ValueError, match="tile exceeds"):
        partition_deferred_islands(
            manifest,
            summaries,
            reconciliation,
            (DeferredDeblendIsland(large, "bounds-pixel-limit"),),
            DeferredIslandCompletionConfig(maximum_tile_pixels=15),
        )


def test_deferred_completion_fails_closed_on_identity_or_shard_drift() -> None:
    """Missing parents and changed local membership cannot be published."""
    mask = _mask()
    manifest = plan_image_partitions(
        image_shape_yx=mask.shape,
        tile_core_shape_yx=(3, 4),
        halo_yx=(0, 0),
    )
    summaries, reconciliation = _label_manifest(mask, manifest)
    large = max(reconciliation.islands, key=lambda island: island.pixel_count)
    deferred = DeferredDeblendIsland(large, "island-pixel-limit")
    completed = partition_deferred_islands(
        manifest,
        summaries,
        reconciliation,
        (deferred,),
        DeferredIslandCompletionConfig(maximum_tile_pixels=12),
    )[0]
    first = completed.shards[0]
    bounds = first.partition.core_bounds
    selected = np.array(
        mask[
            bounds.y_start : bounds.y_stop,
            bounds.x_start : bounds.x_stop,
        ],
        copy=True,
    )
    first_local = (
        first.first_pixel_yx[0] - bounds.y_start,
        first.first_pixel_yx[1] - bounds.x_start,
    )
    selected[first_local] = False

    with pytest.raises(ValueError, match="membership disagrees"):
        extract_deferred_island_shard_membership(first, selected)
    with pytest.raises(TypeError, match="boolean"):
        extract_deferred_island_shard_membership(
            first,
            np.ones(first.partition.core_bounds.shape_yx, dtype=np.int8),
        )
    with pytest.raises(ValueError, match="tile core"):
        extract_deferred_island_shard_membership(
            first,
            np.ones((1, 1), dtype=np.bool_),
        )
    with pytest.raises(ValueError, match="reconciled island"):
        partition_deferred_islands(
            manifest,
            summaries,
            reconciliation,
            (replace(deferred, island=replace(large, pixel_count=1)),),
            DeferredIslandCompletionConfig(maximum_tile_pixels=12),
        )


def test_deferred_records_reject_incomplete_or_noncanonical_topology() -> None:
    """Array-free shard records cannot describe ambiguous membership."""
    mask = _mask()
    manifest = plan_image_partitions(
        image_shape_yx=mask.shape,
        tile_core_shape_yx=(3, 4),
        halo_yx=(0, 0),
    )
    summaries, reconciliation = _label_manifest(mask, manifest)
    large = max(reconciliation.islands, key=lambda island: island.pixel_count)
    completed = partition_deferred_islands(
        manifest,
        summaries,
        reconciliation,
        (DeferredDeblendIsland(large, "island-pixel-limit"),),
        DeferredIslandCompletionConfig(maximum_tile_pixels=12),
    )[0]
    first = completed.shards[0]

    for replacement, message in (
        ({"local_labels": ()}, "labels"),
        ({"pixel_count": 0}, "pixel count"),
        ({"bounds": large.bounds}, "inside its tile"),
        (
            {
                "first_pixel_yx": (
                    first.bounds.y_stop,
                    first.bounds.x_start,
                )
            },
            "first pixel",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            shard = replace(first, **replacement)  # type: ignore[arg-type]
            replace(completed, shards=(shard, *completed.shards[1:]))

    for replacement, message in (
        ({"shards": ()}, "requires shards"),
        ({"shards": tuple(reversed(completed.shards))}, "canonical"),
        (
            {
                "shards": (
                    replace(first, island_id="island-99999"),
                    *completed.shards[1:],
                )
            },
            "parent identity",
        ),
        ({"island": replace(large, pixel_count=1)}, "membership"),
        (
            {
                "island": replace(
                    large,
                    bounds=first.bounds,
                )
            },
            "bounds",
        ),
        (
            {
                "island": replace(
                    large,
                    first_pixel_yx=(
                        large.bounds.y_stop - 1,
                        large.bounds.x_stop - 1,
                    ),
                )
            },
            "first pixel",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            replace(completed, **replacement)  # type: ignore[arg-type]


def test_deferred_partition_inputs_reject_incomplete_reconciliation() -> None:
    """Every tile, mapping, parent, and selected label must be explicit."""
    mask = _mask()
    manifest = plan_image_partitions(
        image_shape_yx=mask.shape,
        tile_core_shape_yx=(3, 4),
        halo_yx=(0, 0),
    )
    summaries, reconciliation = _label_manifest(mask, manifest)
    large = max(reconciliation.islands, key=lambda island: island.pixel_count)
    deferred = DeferredDeblendIsland(large, "island-pixel-limit")
    config = DeferredIslandCompletionConfig(maximum_tile_pixels=12)

    with pytest.raises(ValueError, match="tiles must be canonical"):
        partition_deferred_islands(
            manifest,
            summaries[:-1],
            reconciliation,
            (deferred,),
            config,
        )
    selected_index = next(
        index
        for index, summary in enumerate(summaries)
        if summary.partition.core_bounds.y_start > 0
        and summary.partition.core_bounds.x_start > 0
    )
    selected = summaries[selected_index]
    expanded = selected.partition.core_bounds.expanded(1, mask.shape)
    wrong_partition = replace(selected.partition, read_bounds=expanded)
    wrong_summaries = (
        *summaries[:selected_index],
        replace(selected, partition=wrong_partition),
        *summaries[selected_index + 1 :],
    )
    with pytest.raises(ValueError, match="partition is not canonical"):
        partition_deferred_islands(
            manifest,
            wrong_summaries,
            reconciliation,
            (deferred,),
            config,
        )
    with pytest.raises(ValueError, match="cover every tile"):
        partition_deferred_islands(
            manifest,
            summaries,
            replace(
                reconciliation,
                tile_mappings=reconciliation.tile_mappings[:-1],
            ),
            (deferred,),
            config,
        )
    with pytest.raises(ValueError, match="identities must be unique"):
        partition_deferred_islands(
            manifest,
            summaries,
            reconciliation,
            (deferred, deferred),
            config,
        )
    target_index = next(
        index
        for index, mapping in enumerate(reconciliation.tile_mappings)
        if large.global_label in mapping.global_labels
    )
    target_mapping = reconciliation.tile_mappings[target_index]
    wrong_mapping = replace(
        target_mapping,
        local_labels=(*target_mapping.local_labels, 999),
        global_labels=(*target_mapping.global_labels, large.global_label),
    )
    with pytest.raises(ValueError, match="label is absent"):
        partition_deferred_islands(
            manifest,
            summaries,
            replace(
                reconciliation,
                tile_mappings=(
                    *reconciliation.tile_mappings[:target_index],
                    wrong_mapping,
                    *reconciliation.tile_mappings[target_index + 1 :],
                ),
            ),
            (deferred,),
            config,
        )

    completed = partition_deferred_islands(
        manifest,
        summaries,
        reconciliation,
        (deferred,),
        config,
    )[0]
    absent = replace(completed.shards[0], local_labels=(999,))
    bounds = absent.partition.core_bounds
    with pytest.raises(ValueError, match="membership is absent"):
        extract_deferred_island_shard_membership(
            absent,
            mask[
                bounds.y_start : bounds.y_stop,
                bounds.x_start : bounds.x_stop,
            ],
        )
