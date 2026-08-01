"""Pure bounded normalization and two-threshold detection kernels."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hebog.config import SourceFinderConfig

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class DetectionThresholdMasks:
    """Immutable island-membership and strict detection-seed masks."""

    normalized_residual: npt.NDArray[np.float64]
    island_membership: npt.NDArray[np.bool_]
    detection_seeds: npt.NDArray[np.bool_]
    valid_pixel_count: int


def _as_float_plane(
    values: npt.ArrayLike,
    *,
    name: str,
) -> npt.NDArray[np.float64]:
    """Convert one real two-dimensional scientific plane to float64."""
    array = np.asarray(values)
    if array.ndim != _IMAGE_DIMENSIONS:
        raise ValueError(f"{name} must be two-dimensional")
    if np.issubdtype(array.dtype, np.bool_) or not np.issubdtype(
        array.dtype,
        np.number,
    ):
        raise TypeError(f"{name} must contain real numeric values")
    if np.issubdtype(array.dtype, np.complexfloating):
        raise TypeError(f"{name} must contain real numeric values")
    return np.asarray(array, dtype=np.float64)


def detect_threshold_masks(
    image: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background: npt.ArrayLike,
    rms: npt.ArrayLike,
    config: SourceFinderConfig,
) -> DetectionThresholdMasks:
    """Threshold one bounded image tile without persisting an SNR plane.

    Island membership includes pixels exactly at the island threshold.
    Detection seeds require a value strictly above the detection threshold.
    This explicit asymmetry reproduces the reviewed initial compact-detection
    contract without introducing workflow defaults into the kernel.
    """
    image_array = _as_float_plane(image, name="image")
    background_array = _as_float_plane(background, name="background")
    rms_array = _as_float_plane(rms, name="rms")
    validity = np.asarray(valid_pixels)
    if validity.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("valid_pixels must be two-dimensional")
    if not np.issubdtype(validity.dtype, np.bool_):
        raise TypeError("valid_pixels must be a boolean array")
    if not (
        image_array.shape
        == background_array.shape
        == rms_array.shape
        == validity.shape
    ):
        raise ValueError("detection arrays must have the same shape")

    scientifically_valid = (
        np.asarray(validity, dtype=np.bool_)
        & np.isfinite(image_array)
        & np.isfinite(background_array)
        & np.isfinite(rms_array)
        & (rms_array > 0)
    )
    normalized = np.full(image_array.shape, np.nan, dtype=np.float64)
    np.divide(
        image_array - background_array,
        rms_array,
        out=normalized,
        where=scientifically_valid,
    )
    island_membership = scientifically_valid & (
        normalized >= config.island_threshold_sigma
    )
    detection_seeds = scientifically_valid & (
        normalized > config.detection_threshold_sigma
    )
    normalized.setflags(write=False)
    island_membership.setflags(write=False)
    detection_seeds.setflags(write=False)
    return DetectionThresholdMasks(
        normalized_residual=normalized,
        island_membership=island_membership,
        detection_seeds=detection_seeds,
        valid_pixel_count=int(np.count_nonzero(scientifically_valid)),
    )
