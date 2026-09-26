# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Owner connectivity from tile cores, against the window kernels."""

from __future__ import annotations

from typing import cast

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import ndimage

from hebog.algorithms.extended_measurement import (
    owner_support_is_split,
    preserve_owner_publication_bridges,
)
from hebog.algorithms.owner_connectivity import (
    ComponentKey,
    OwnerBridgeCore,
    apply_owner_bridges,
    decide_owner_bridges,
    join_components,
    label_components,
    observe_owner_bridges,
    owner_bridge_planes,
    split_owners,
    touching_across_cores,
    touching_within_core,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models.partitioning import PartitionManifest

_STRUCTURE = np.ones((3, 3), dtype=np.int8)


def _manifest(
    shape_yx: tuple[int, int], core: int, origin: tuple[int, int]
) -> PartitionManifest:
    """Partition a small plane into core-only tiles."""
    return plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(0, 0),
        partition_origin_yx=origin,
    )


def _core(
    plane: npt.NDArray[np.int32], manifest: PartitionManifest, index: int
) -> npt.NDArray[np.int32]:
    """Return one tile's core of a whole plane."""
    bounds = manifest.tiles[index].core_bounds
    return plane[
        bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
    ]


def _random_labels(
    seed: int, shape_yx: tuple[int, int], labels: tuple[int, ...]
) -> npt.NDArray[np.int32]:
    """Return one sparse random label plane over the given labels."""
    rng = np.random.default_rng(seed)
    return np.asarray(
        rng.choice(np.asarray((0, 0, *labels), dtype=np.int32), size=shape_yx),
        dtype=np.int32,
    )


def _whole_components(
    plane: npt.NDArray[np.int32], label_value: int
) -> npt.NDArray[np.int32]:
    """Label one label's eight-connected components over a whole plane."""
    components, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        ndimage.label(plane == label_value, structure=_STRUCTURE),
    )
    return components


def test_components_of_different_labels_never_join() -> None:
    """Touching pixels of two labels are two components; a diagonal joins."""
    plane = np.asarray(
        [
            [1, 1, 2, 0],
            [0, 0, 2, 1],
            [3, 0, 0, 0],
            [0, 3, 0, 1],
        ],
        dtype=np.int32,
    )
    manifest = _manifest(plane.shape, 4, (0, 0))

    components = label_components(plane, manifest.tiles[0])

    assert components.labels == (1, 1, 1, 2, 3)
    np.testing.assert_array_equal(
        components.components,
        np.asarray(
            [
                [1, 1, 4, 0],
                [0, 0, 4, 2],
                [5, 0, 0, 0],
                [0, 5, 0, 3],
            ],
            dtype=np.int32,
        ),
    )


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    core=st.integers(2, 6),
    origin=st.tuples(st.integers(0, 1), st.integers(0, 1)),
)
def test_joined_components_are_the_whole_plane_components(
    seed: int, core: int, origin: tuple[int, int]
) -> None:
    """Joining each core's components across edges labels the whole plane.

    Two pixels share a joined root exactly when they share a component of
    their label over the whole plane, for any core size and origin.
    """
    shape_yx = (11, 13)
    plane = _random_labels(seed, shape_yx, (1, 2, 5))
    manifest = _manifest(
        shape_yx, core, (min(origin[0], core - 1), min(origin[1], core - 1))
    )
    tiles = tuple(
        label_components(_core(plane, manifest, index), tile)
        for index, tile in enumerate(manifest.tiles)
    )
    summaries = tuple(tile.summary() for tile in tiles)
    roots = join_components(
        (key for summary in summaries for key in summary.component_keys()),
        touching_across_cores(summaries, summaries),
    )

    joined = np.zeros(shape_yx, dtype=np.int64)
    names: dict[ComponentKey, int] = {}
    for tile in tiles:
        bounds = tile.partition.core_bounds
        region = joined[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ]
        for local in range(1, len(tile.labels) + 1):
            root = roots[(tile.partition.tile_id, local)]
            region[tile.components == local] = names.setdefault(
                root, len(names) + 1
            )
    for label_value in (1, 2, 5):
        whole = _whole_components(plane, label_value)
        member = plane == label_value
        pairs = set(
            zip(whole[member].tolist(), joined[member].tolist(), strict=True)
        )
        assert len(pairs) == len({left for left, _ in pairs})
        assert len(pairs) == len({right for _, right in pairs})
    assert split_owners(summaries) == frozenset(
        label_value
        for label_value in (1, 2, 5)
        if owner_support_is_split(plane, label_value=label_value)
    )


def test_pixels_touch_inside_one_core_only_between_one_label() -> None:
    """A pixel touches its eight neighbours, and only those of its label."""
    first = np.asarray([[1, 0, 0], [0, 0, 2], [0, 0, 0]], dtype=np.int32)
    second = np.asarray([[0, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.int32)
    tile = _manifest(first.shape, 3, (0, 0)).tiles[0]

    pairs = touching_within_core(
        label_components(first, tile), label_components(second, tile)
    )

    assert pairs == frozenset({(1, 1)})


def _grown(
    rng: np.random.Generator,
    free: npt.NDArray[np.bool_],
    size: int,
) -> npt.NDArray[np.bool_]:
    """Grow one eight-connected region from a random free pixel."""
    region = np.zeros(free.shape, dtype=np.bool_)
    candidates = np.argwhere(free)
    if not candidates.size:
        return region
    region[tuple(candidates[rng.integers(len(candidates))])] = True
    for _ in range(size - 1):
        grown = np.asarray(
            ndimage.binary_dilation(region, structure=_STRUCTURE),
            dtype=np.bool_,
        )
        frontier = np.argwhere(grown & free & ~region)
        if not frontier.size:
            break
        region[tuple(frontier[rng.integers(len(frontier))])] = True
    return region


def _previous_and_refined(
    seed: int, shape_yx: tuple[int, int]
) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]]:
    """Return random published and persistent planes for owners 1 and 2.

    Each owner's earlier publication is grown as one connected region, or
    now and then as two, and its persistent support keeps part of it plus a
    few pixels outside it. An owner's published pixel therefore carries that
    owner or nothing in the persistent plane, as the support pass
    guarantees.
    """
    rng = np.random.default_rng(seed)
    previous = np.zeros(shape_yx, dtype=np.int32)
    for owner in (1, 2):
        for _ in range(1 if rng.random() < 0.85 else 2):
            region = _grown(rng, previous == 0, int(rng.integers(4, 24)))
            previous[region] = owner
    refined = np.where(
        (previous > 0) & (rng.random(shape_yx) < 0.55), previous, 0
    ).astype(np.int32)
    extra = (previous == 0) & (rng.random(shape_yx) < 0.06)
    refined[extra] = rng.choice(
        np.asarray((1, 2), dtype=np.int32), size=int(extra.sum())
    )
    return previous, refined


def _kernel_bridges(
    previous: npt.NDArray[np.int32], refined: npt.NDArray[np.int32]
) -> npt.NDArray[np.int32] | str:
    """Apply the window kernel owner by owner, or name the error it raises."""
    local = refined.copy()
    try:
        for owner in (1, 2):
            local = preserve_owner_publication_bridges(
                previous, local, label_value=owner
            )
    except ValueError as error:
        return str(error)
    return local


def _core_bridges(
    previous: npt.NDArray[np.int32],
    refined: npt.NDArray[np.int32],
    manifest: PartitionManifest,
) -> npt.NDArray[np.int32] | str:
    """Decide the same rule from cores, and write each core's share."""
    owners = (1, 2)
    planes = tuple(
        owner_bridge_planes(
            _core(refined, manifest, index),
            _core(previous, manifest, index),
            owners,
            tile,
        )
        for index, tile in enumerate(manifest.tiles)
    )
    cores: tuple[OwnerBridgeCore, ...] = tuple(
        observe_owner_bridges(plane, _core(previous, manifest, index))
        for index, plane in enumerate(planes)
    )
    try:
        shares, _ = decide_owner_bridges(cores)
    except ValueError as error:
        return str(error)
    result = refined.copy()
    for index, plane in enumerate(planes):
        share = shares.get(manifest.tiles[index].tile_id)
        if share is not None:
            apply_owner_bridges(_core(result, manifest, index), plane, share)
    return result


@settings(max_examples=150, deadline=None)
@given(
    seed=st.integers(0, 100_000),
    core=st.integers(2, 7),
)
def test_bridges_decided_from_cores_are_the_window_kernels(
    seed: int, core: int
) -> None:
    """Every bridge case the kernel takes, the joined cores take identically.

    Bridging, restoring the whole earlier support, keeping only its part and
    refusing a disconnected earlier support all follow from components and
    which of them touch, so cores of any size reproduce the kernel.
    """
    previous, refined = _previous_and_refined(seed, (9, 12))

    expected = _kernel_bridges(previous, refined)
    result = _core_bridges(previous, refined, _manifest((9, 12), core, (0, 0)))

    if isinstance(expected, str):
        assert result == expected
    else:
        assert not isinstance(result, str)
        np.testing.assert_array_equal(result, expected)


# ``L`` is persistent support published earlier, ``Q`` persistent support
# that was not, ``P`` a pixel published earlier that is not persistent, and
# ``.`` neither. Restoring the earlier support can never reconnect parts the
# bridges left apart, because a candidate touching two parts is a bridge, so
# the rule either bridges or keeps the one part holding earlier pixels.
_BRIDGE_CASES = {
    # A candidate touches both parts, so it bridges them.
    "bridge": (
        "LL.LL",
        "LLPLL",
        "LL.LL",
    ),
    # Nothing bridges, so the part holding earlier pixels stays and gains
    # its candidate, and the part holding none falls away.
    "keep": (
        "LLP...QQ",
        "LL....QQ",
    ),
}


def _case_planes(
    rows: tuple[str, ...],
) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.int32]]:
    """Return previous and refined planes for owner 1 from coded rows."""
    width = max(len(row) for row in rows)
    grid = np.asarray([list(row.ljust(width, ".")) for row in rows])
    refined = np.where((grid == "L") | (grid == "Q"), 1, 0).astype(np.int32)
    previous = np.where((grid == "L") | (grid == "P"), 1, 0).astype(np.int32)
    return previous, refined


@pytest.mark.parametrize("case", sorted(_BRIDGE_CASES))
@pytest.mark.parametrize("core", [2, 3, 5])
def test_each_bridge_case_is_decided_across_cores(
    case: str, core: int
) -> None:
    """Each branch of the rule survives cutting the owner between cores."""
    previous, refined = _case_planes(_BRIDGE_CASES[case])
    manifest = _manifest(previous.shape, core, (0, 0))

    expected = _kernel_bridges(previous, refined)

    assert not isinstance(expected, str)
    assert not np.array_equal(expected, refined), "the case must change pixels"
    result = _core_bridges(previous, refined, manifest)
    assert not isinstance(result, str)
    np.testing.assert_array_equal(result, expected)


def test_a_disconnected_earlier_support_fails_closed_across_cores() -> None:
    """Two separate earlier parts that nothing reconnects are refused."""
    previous, refined = _case_planes(("LP..PL",))
    manifest = _manifest(previous.shape, 2, (0, 0))

    expected = _kernel_bridges(previous, refined)

    assert expected == "previous publication ownership must be connected"
    assert _core_bridges(previous, refined, manifest) == expected


def test_a_plane_must_cover_the_core_it_labels() -> None:
    """Components numbered for another shape could not be written back."""
    tile = _manifest((4, 4), 4, (0, 0)).tiles[0]

    with pytest.raises(ValueError, match="cover the partition's core"):
        label_components(np.zeros((3, 4), dtype=np.int32), tile)


def test_an_owner_without_persistent_support_is_left_alone() -> None:
    """With no base support there is nothing to bridge or keep."""
    previous, refined = _case_planes(("PP.P",))
    manifest = _manifest(previous.shape, 2, (0, 0))

    result = _core_bridges(previous, refined, manifest)

    assert not isinstance(result, str)
    np.testing.assert_array_equal(result, refined)
    assert np.array_equal(_kernel_bridges(previous, refined), refined)
