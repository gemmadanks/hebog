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
