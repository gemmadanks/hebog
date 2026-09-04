# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Array-free attribution for adaptive-background development fixtures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy import ndimage

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class TruthSupportAttribution:
    """Bounded counts locating truth-support changes between science stages."""

    truth_pixel_count: int
    coarse_support_count: int
    adaptive_support_count: int
    measurement_support_count: int
    publication_support_count: int
    coarse_component_count: int
    adaptive_component_count: int
    measurement_component_count: int
    publication_component_count: int
    adaptive_background_rejected_count: int
    adaptive_background_recovered_count: int
    measurement_rejected_count: int
    measurement_recovered_count: int
    publication_rejected_count: int
    publication_recovered_count: int

    def to_record(self) -> dict[str, int]:
        """Return a JSON-ready record containing no image-sized arrays."""
        return cast(dict[str, int], asdict(self))


@dataclass(frozen=True, slots=True)
class SourceMeasurementAttribution:
    """Array-free ownership and measurement/publication stage census."""

    source_seed_pixel_count: int
    persistent_support_pixel_count: int
    source_owned_persistent_pixel_count: int
    source_unowned_persistent_pixel_count: int
    source_owned_support_pixel_count: int
    source_measurement_pixel_count: int
    publication_pixel_count: int
    measurement_publication_overlap_count: int
    measurement_only_pixel_count: int
    publication_only_pixel_count: int
    competing_support_component_count: int

    def to_record(self) -> dict[str, int]:
        """Return a JSON-ready record containing no image-sized arrays."""
        return cast(dict[str, int], asdict(self))


def _boolean_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.bool_]:
    """Validate one exact aligned boolean support plane."""
    array = np.asarray(values)
    if (
        array.ndim != _IMAGE_DIMENSIONS
        or array.dtype != np.dtype(np.bool_)
        or (shape is not None and array.shape != shape)
    ):
        raise ValueError(
            f"adaptive support diagnostic {name} must be one aligned "
            "boolean plane"
        )
    return np.asarray(array, dtype=np.bool_)


def _component_count(values: npt.NDArray[np.bool_]) -> int:
    """Count eight-connected retained truth-support components."""
    _, count = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            values,
            structure=np.ones((3, 3), dtype=np.bool_),
        ),
    )
    return count


def _source_label_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.int64]:
    """Validate one non-negative aligned source-identity plane."""
    labels = np.asarray(values)
    if (
        labels.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(labels.dtype, np.integer)
        or bool(np.any(labels < 0))
        or (shape is not None and labels.shape != shape)
    ):
        raise ValueError(
            f"adaptive support diagnostic {name} must be one aligned "
            "non-negative integer plane"
        )
    return np.asarray(labels, dtype=np.int64)


def attribute_source_measurement_support(
    source_seed_labels: npt.ArrayLike,
    persistent_support: npt.ArrayLike,
    source_owned_labels: npt.ArrayLike,
    source_measurement_labels: npt.ArrayLike,
    publication_support: npt.ArrayLike,
) -> SourceMeasurementAttribution:
    """Reduce source ownership and publication differences to exact counts."""
    seeds = _source_label_plane(source_seed_labels, name="source seeds")
    persistent = _boolean_plane(
        persistent_support,
        name="persistent source support",
        shape=seeds.shape,
    )
    owned = _source_label_plane(
        source_owned_labels,
        name="source-owned persistent support",
        shape=seeds.shape,
    )
    measurement = _source_label_plane(
        source_measurement_labels,
        name="source measurement",
        shape=seeds.shape,
    )
    publication = _boolean_plane(
        publication_support,
        name="publication",
        shape=seeds.shape,
    )
    seed_ids = {int(value) for value in np.unique(seeds) if value > 0}
    owned_ids = {int(value) for value in np.unique(owned) if value > 0}
    measurement_ids = {
        int(value) for value in np.unique(measurement) if value > 0
    }
    if (owned_ids | measurement_ids) - seed_ids:
        raise ValueError(
            "adaptive support diagnostic measurement created a source identity"
        )
    seed_pixels = seeds > 0
    owned_pixels = owned > 0
    measurement_pixels = measurement > 0
    if np.any(owned[seed_pixels] != seeds[seed_pixels]) or np.any(
        measurement[owned_pixels] != owned[owned_pixels]
    ):
        raise ValueError(
            "adaptive support diagnostic measurement changed source seeds"
        )
    if np.any(owned_pixels & ~seed_pixels & ~persistent):
        raise ValueError(
            "adaptive support diagnostic measurement used non-persistent "
            "support"
        )
    connected, count = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            seed_pixels | persistent,
            structure=np.ones((3, 3), dtype=np.bool_),
        ),
    )
    competing = 0
    for component in range(1, int(count) + 1):
        owners = {
            int(value)
            for value in np.unique(seeds[connected == component])
            if value > 0
        }
        competing += len(owners) > 1
    owned_persistent = persistent & owned_pixels
    overlap = measurement_pixels & publication
    return SourceMeasurementAttribution(
        source_seed_pixel_count=int(np.count_nonzero(seed_pixels)),
        persistent_support_pixel_count=int(np.count_nonzero(persistent)),
        source_owned_persistent_pixel_count=int(
            np.count_nonzero(owned_persistent)
        ),
        source_unowned_persistent_pixel_count=int(
            np.count_nonzero(persistent & ~owned_pixels)
        ),
        source_owned_support_pixel_count=int(np.count_nonzero(owned_pixels)),
        source_measurement_pixel_count=int(
            np.count_nonzero(measurement_pixels)
        ),
        publication_pixel_count=int(np.count_nonzero(publication)),
        measurement_publication_overlap_count=int(np.count_nonzero(overlap)),
        measurement_only_pixel_count=int(
            np.count_nonzero(measurement_pixels & ~publication)
        ),
        publication_only_pixel_count=int(
            np.count_nonzero(publication & ~measurement_pixels)
        ),
        competing_support_component_count=int(competing),
    )


def attribute_truth_support(
    truth_support: npt.ArrayLike,
    coarse_support: npt.ArrayLike,
    adaptive_support: npt.ArrayLike,
    measurement_support: npt.ArrayLike,
    publication_support: npt.ArrayLike,
) -> TruthSupportAttribution:
    """Reduce stage-local truth support to non-binding causal diagnostics."""
    truth = _boolean_plane(truth_support, name="truth")
    if not np.any(truth):
        raise ValueError("adaptive support diagnostic truth must not be empty")
    stages = tuple(
        _boolean_plane(values, name=name, shape=truth.shape)
        for name, values in (
            ("coarse", coarse_support),
            ("adaptive", adaptive_support),
            ("measurement", measurement_support),
            ("publication", publication_support),
        )
    )
    coarse, adaptive, measurement, publication = (
        stage & truth for stage in stages
    )

    def count(values: npt.NDArray[np.bool_]) -> int:
        return int(np.count_nonzero(values))

    return TruthSupportAttribution(
        truth_pixel_count=count(truth),
        coarse_support_count=count(coarse),
        adaptive_support_count=count(adaptive),
        measurement_support_count=count(measurement),
        publication_support_count=count(publication),
        coarse_component_count=_component_count(coarse),
        adaptive_component_count=_component_count(adaptive),
        measurement_component_count=_component_count(measurement),
        publication_component_count=_component_count(publication),
        adaptive_background_rejected_count=count(coarse & ~adaptive),
        adaptive_background_recovered_count=count(~coarse & adaptive),
        measurement_rejected_count=count(adaptive & ~measurement),
        measurement_recovered_count=count(~adaptive & measurement),
        publication_rejected_count=count(measurement & ~publication),
        publication_recovered_count=count(~measurement & publication),
    )
