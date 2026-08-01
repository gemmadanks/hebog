"""Serializable deterministic image-partition records."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import isfinite
from typing import Literal, Self


@dataclass(frozen=True, slots=True)
class ImageBounds:
    """Half-open global pixel bounds in NumPy ``(y, x)`` axis order."""

    y_start: int
    y_stop: int
    x_start: int
    x_stop: int

    def __post_init__(self) -> None:
        """Require non-negative, non-empty half-open bounds."""
        if min(self.y_start, self.y_stop, self.x_start, self.x_stop) < 0:
            raise ValueError("image bounds must be non-negative")
        if self.y_stop <= self.y_start or self.x_stop <= self.x_start:
            raise ValueError("image bounds must be non-empty")

    @property
    def shape_yx(self) -> tuple[int, int]:
        """Return the bounded array shape in NumPy axis order."""
        return (
            self.y_stop - self.y_start,
            self.x_stop - self.x_start,
        )

    def require_inside(self, shape_yx: tuple[int, int]) -> None:
        """Reject bounds extending beyond one logical image plane."""
        if self.y_stop > shape_yx[0] or self.x_stop > shape_yx[1]:
            raise ValueError(
                f"image bounds must stay inside image shape {shape_yx}"
            )

    def contains(self, other: ImageBounds) -> bool:
        """Return whether another region lies completely within the bounds."""
        return (
            self.y_start <= other.y_start
            and other.y_stop <= self.y_stop
            and self.x_start <= other.x_start
            and other.x_stop <= self.x_stop
        )


@dataclass(frozen=True, slots=True)
class TilePartition:
    """One non-overlapping output core and its clipped read-only halo."""

    tile_y_index: int
    tile_x_index: int
    core_bounds: ImageBounds
    read_bounds: ImageBounds

    def __post_init__(self) -> None:
        """Require valid indices and a read region containing the core."""
        if min(self.tile_y_index, self.tile_x_index) < 0:
            raise ValueError("tile indices must be non-negative")
        if not self.read_bounds.contains(self.core_bounds):
            raise ValueError("tile read bounds must contain its core bounds")

    @property
    def tile_id(self) -> str:
        """Return a deterministic row-major identifier."""
        return f"tile-{self.tile_y_index:05d}-{self.tile_x_index:05d}"

    @property
    def core_slices_yx(self) -> tuple[slice, slice]:
        """Locate the owned core inside an array read through its halo."""
        return (
            slice(
                self.core_bounds.y_start - self.read_bounds.y_start,
                self.core_bounds.y_stop - self.read_bounds.y_start,
            ),
            slice(
                self.core_bounds.x_start - self.read_bounds.x_start,
                self.core_bounds.x_stop - self.read_bounds.x_start,
            ),
        )


def _validate_geometry(
    image_shape_yx: tuple[int, int],
    tile_core_shape_yx: tuple[int, int],
    halo_yx: tuple[int, int],
    partition_origin_yx: tuple[int, int],
) -> None:
    """Validate bounded tiling inputs before generating any records."""
    if min(image_shape_yx) < 1:
        raise ValueError("image shape dimensions must be positive")
    if min(tile_core_shape_yx) < 1:
        raise ValueError("tile core shape dimensions must be positive")
    if min(halo_yx) < 0:
        raise ValueError("halo dimensions cannot be negative")
    if any(
        halo > 0 and halo * 4 >= core
        for halo, core in zip(halo_yx, tile_core_shape_yx, strict=True)
    ):
        raise ValueError("each halo must remain below one quarter of its core")
    if min(partition_origin_yx) < 0 or any(
        origin >= core
        for origin, core in zip(
            partition_origin_yx,
            tile_core_shape_yx,
            strict=True,
        )
    ):
        raise ValueError("partition origin must lie inside the tile core")


def _axis_bounds(
    length: int,
    core: int,
    origin: int,
) -> tuple[tuple[int, int], ...]:
    """Return contiguous axis intervals for one possibly shifted grid."""
    first_stop = origin or core
    boundaries = (0, *range(first_stop, length, core), length)
    return tuple(pairwise(boundaries))


def _axis_owner_index(
    position: float,
    *,
    length: int,
    core: int,
    origin: int,
) -> int:
    """Resolve one valid continuous coordinate to its half-open core."""
    first_stop = origin or core
    if position < first_stop or first_stop >= length:
        return 0
    return 1 + int((position - first_stop) // core)


def _axis_partition_count(*, length: int, core: int, origin: int) -> int:
    """Return the number of canonical intervals without materialising them."""
    first_stop = origin or core
    remaining = max(0, length - first_stop)
    return 1 + (remaining + core - 1) // core


def _canonical_tiles(
    image_shape_yx: tuple[int, int],
    tile_core_shape_yx: tuple[int, int],
    halo_yx: tuple[int, int],
    partition_origin_yx: tuple[int, int],
) -> tuple[TilePartition, ...]:
    """Build the unique reviewed row-major partition for one geometry."""
    y_bounds = _axis_bounds(
        image_shape_yx[0],
        tile_core_shape_yx[0],
        partition_origin_yx[0],
    )
    x_bounds = _axis_bounds(
        image_shape_yx[1],
        tile_core_shape_yx[1],
        partition_origin_yx[1],
    )
    return tuple(
        TilePartition(
            tile_y_index=tile_y_index,
            tile_x_index=tile_x_index,
            core_bounds=ImageBounds(y_start, y_stop, x_start, x_stop),
            read_bounds=ImageBounds(
                max(0, y_start - halo_yx[0]),
                min(image_shape_yx[0], y_stop + halo_yx[0]),
                max(0, x_start - halo_yx[1]),
                min(image_shape_yx[1], x_stop + halo_yx[1]),
            ),
        )
        for tile_y_index, (y_start, y_stop) in enumerate(y_bounds)
        for tile_x_index, (x_start, x_stop) in enumerate(x_bounds)
    )


@dataclass(frozen=True, slots=True)
class PartitionManifest:
    """Canonical tiling record with one owner per output pixel."""

    image_shape_yx: tuple[int, int]
    tile_core_shape_yx: tuple[int, int]
    halo_yx: tuple[int, int]
    partition_origin_yx: tuple[int, int]
    tiles: tuple[TilePartition, ...]
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject unsupported versions and non-canonical ownership records."""
        if self.schema_version != 1:
            raise ValueError("unsupported partition manifest schema version")
        _validate_geometry(
            self.image_shape_yx,
            self.tile_core_shape_yx,
            self.halo_yx,
            self.partition_origin_yx,
        )
        expected = _canonical_tiles(
            self.image_shape_yx,
            self.tile_core_shape_yx,
            self.halo_yx,
            self.partition_origin_yx,
        )
        if self.tiles != expected:
            raise ValueError(
                "partition manifest tiles must match canonical row-major "
                "ownership"
            )

    def owner_for_position_yx(
        self,
        position_yx: tuple[float, float],
    ) -> TilePartition:
        """Return the unique tile owning a source reference position.

        Positions use zero-based continuous ``(y, x)`` pixel coordinates.
        A position exactly on an internal boundary belongs to the core that
        starts at that boundary. A source may overlap other cores and halos;
        only its deterministic reference position selects catalogue ownership.
        """
        y_position, x_position = position_yx
        height, width = self.image_shape_yx
        if (
            not isfinite(y_position)
            or not isfinite(x_position)
            or not 0 <= y_position < height
            or not 0 <= x_position < width
        ):
            raise ValueError(
                "source reference position must be finite and inside the image"
            )
        y_index = _axis_owner_index(
            y_position,
            length=height,
            core=self.tile_core_shape_yx[0],
            origin=self.partition_origin_yx[0],
        )
        x_index = _axis_owner_index(
            x_position,
            length=width,
            core=self.tile_core_shape_yx[1],
            origin=self.partition_origin_yx[1],
        )
        tiles_per_row = _axis_partition_count(
            length=width,
            core=self.tile_core_shape_yx[1],
            origin=self.partition_origin_yx[1],
        )
        return self.tiles[y_index * tiles_per_row + x_index]

    @classmethod
    def create(
        cls,
        *,
        image_shape_yx: tuple[int, int],
        tile_core_shape_yx: tuple[int, int],
        halo_yx: tuple[int, int],
        partition_origin_yx: tuple[int, int] = (0, 0),
    ) -> Self:
        """Validate geometry and construct its unique canonical manifest."""
        _validate_geometry(
            image_shape_yx,
            tile_core_shape_yx,
            halo_yx,
            partition_origin_yx,
        )
        return cls(
            image_shape_yx=image_shape_yx,
            tile_core_shape_yx=tile_core_shape_yx,
            halo_yx=halo_yx,
            partition_origin_yx=partition_origin_yx,
            tiles=_canonical_tiles(
                image_shape_yx,
                tile_core_shape_yx,
                halo_yx,
                partition_origin_yx,
            ),
        )
