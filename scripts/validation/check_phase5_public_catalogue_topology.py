#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Diagnose component under-representation in one existing public bundle."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from math import ceil, isfinite
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from scipy.ndimage import label as label_connected
from scipy.ndimage import maximum_filter

_IMAGE_DIMENSIONS = 2
_MULTI_PEAK_MINIMUM = 2
_MAXIMUM_REPORTED_LABELS = 50


def _aligned_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one finite-compatible aligned diagnostic plane."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"{name} must be an aligned two-dimensional numeric plane"
        )
    return np.asarray(plane, dtype=np.float64)


def _component_counts_by_support(
    labels: npt.NDArray[np.int64],
    component_label_values: Sequence[int],
    component_labels: npt.ArrayLike | None,
) -> tuple[Counter[int], int]:
    """Map published components onto connected support identities."""
    component_values: list[int] = []
    for value in component_label_values:
        if isinstance(value, bool) or int(value) != value or int(value) <= 0:
            raise ValueError(
                "component label values must be positive integers"
            )
        component_values.append(int(value))
    if component_labels is None:
        return Counter(component_values), len(component_values)
    raw_components = np.asarray(component_labels)
    if (
        raw_components.ndim != _IMAGE_DIMENSIONS
        or raw_components.shape != labels.shape
        or not np.issubdtype(raw_components.dtype, np.integer)
        or np.any(raw_components < 0)
    ):
        raise ValueError(
            "component labels must be an aligned two-dimensional "
            "non-negative integer plane"
        )
    components = np.asarray(raw_components, dtype=np.int64)
    observed_components = set(np.unique(components[components > 0]))
    if observed_components != set(component_values):
        raise ValueError(
            "component label plane and association identities differ"
        )
    overlap = (components > 0) & (labels > 0)
    component_parent_pairs = np.unique(
        np.column_stack((components[overlap], labels[overlap])),
        axis=0,
    )
    parent_counts_by_component: Counter[int] = Counter(
        int(component) for component in component_parent_pairs[:, 0]
    )
    if set(parent_counts_by_component) != observed_components or any(
        count != 1 for count in parent_counts_by_component.values()
    ):
        raise ValueError(
            "each component must overlap exactly one support parent"
        )
    return (
        Counter(int(parent) for parent in component_parent_pairs[:, 1]),
        len(observed_components),
    )


def summarize_catalogue_topology(  # noqa: PLR0913
    image: npt.ArrayLike,
    background: npt.ArrayLike,
    rms: npt.ArrayLike,
    support_labels: npt.ArrayLike,
    *,
    beam_width_pixels: float,
    component_label_values: Sequence[int],
    component_labels: npt.ArrayLike | None = None,
    peak_threshold_sigma: float = 8.0,
) -> dict[str, object]:
    """Return a result-neutral summary of peaks and published components.

    A local maximum is only a diagnostic feature, not an asserted physical
    source. The result asks for review when a connected support contains more
    beam-separated high-significance maxima than published components.
    """
    if not isfinite(beam_width_pixels) or beam_width_pixels <= 0:
        raise ValueError("beam_width_pixels must be finite and positive")
    if not isfinite(peak_threshold_sigma) or peak_threshold_sigma <= 0:
        raise ValueError("peak_threshold_sigma must be finite and positive")
    image_plane = _aligned_plane(image, name="image")
    background_plane = _aligned_plane(
        background, name="background", shape=image_plane.shape
    )
    rms_plane = _aligned_plane(rms, name="RMS", shape=image_plane.shape)
    raw_labels = np.asarray(support_labels)
    if (
        raw_labels.ndim != _IMAGE_DIMENSIONS
        or raw_labels.shape != image_plane.shape
        or not np.issubdtype(raw_labels.dtype, np.integer)
        or np.any(raw_labels < 0)
    ):
        raise ValueError(
            "support labels must be an aligned two-dimensional "
            "non-negative integer plane"
        )
    labels = np.asarray(raw_labels, dtype=np.int64)
    component_counts, published_component_count = _component_counts_by_support(
        labels,
        component_label_values,
        component_labels,
    )

    window = max(3, ceil(beam_width_pixels))
    if window % 2 == 0:
        window += 1
    significance = np.divide(
        image_plane - background_plane,
        rms_plane,
        out=np.full(image_plane.shape, -np.inf, dtype=np.float64),
        where=(
            np.isfinite(image_plane)
            & np.isfinite(background_plane)
            & np.isfinite(rms_plane)
            & (rms_plane > 0)
        ),
    )
    candidates = (
        (labels > 0)
        & (significance >= peak_threshold_sigma)
        & (
            significance
            == maximum_filter(significance, size=window, mode="nearest")
        )
    )
    plateau_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        label_connected(candidates, structure=np.ones((3, 3), dtype=np.uint8)),
    )
    if np.any(candidates):
        pairs = np.unique(
            np.column_stack((labels[candidates], plateau_labels[candidates])),
            axis=0,
        )
        peak_counts: Counter[int] = Counter(
            int(label_value) for label_value in pairs[:, 0]
        )
    else:
        peak_counts = Counter()
    multi_peak_labels = sorted(
        value
        for value, count in peak_counts.items()
        if count >= _MULTI_PEAK_MINIMUM
    )
    review_labels = [
        value
        for value in multi_peak_labels
        if component_counts[value] < peak_counts[value]
    ]
    support_label_values = np.unique(labels[labels > 0])
    return {
        "schema_version": 1,
        "status": "review-required" if review_labels else "pass",
        "interpretation": (
            "local maxima are diagnostic features, not asserted "
            "astrophysical sources"
        ),
        "beam_width_pixels": float(beam_width_pixels),
        "maximum_filter_window_pixels": window,
        "peak_threshold_sigma": float(peak_threshold_sigma),
        "support_label_count": int(support_label_values.size),
        "published_component_count": published_component_count,
        "selected_peak_count": int(sum(peak_counts.values())),
        "multi_peak_support_count": len(multi_peak_labels),
        "component_underrepresented_support_count": len(review_labels),
        "maximum_peaks_per_support": max(peak_counts.values(), default=0),
        "review_label_values": review_labels[:_MAXIMUM_REPORTED_LABELS],
        "review_label_values_truncated_count": max(
            0,
            len(review_labels) - _MAXIMUM_REPORTED_LABELS,
        ),
    }


def _fits_plane(path: Path) -> npt.NDArray[np.float64]:
    """Read one FITS primary plane without retaining the file handle."""
    with fits.open(path, memmap=True) as handle:
        primary = cast(Any, handle[0])
        values = primary.data
        return np.asarray(values).squeeze().copy()


def _json(path: Path) -> object:
    """Read one JSON value."""
    return json.loads(path.read_text(encoding="utf-8"))


def _component_labels(path: Path) -> tuple[int, ...]:
    """Read authoritative component-to-support membership values."""
    value = _json(path)
    if not isinstance(value, dict) or not isinstance(
        value.get("components"), list
    ):
        raise ValueError("source association is malformed")
    output: list[int] = []
    for item in cast(list[Any], value["components"]):
        if not isinstance(item, dict) or not isinstance(
            item.get("label_value"), int
        ):
            raise ValueError("source association component is malformed")
        output.append(int(item["label_value"]))
    return tuple(output)


def _beam_width_pixels(path: Path) -> float:
    """Return the largest restoring-beam FWHM in image pixels."""
    header = cast(fits.Header, fits.getheader(path))
    try:
        return max(
            float(cast(Any, header["BMAJ"]))
            / abs(float(cast(Any, header["CDELT2"]))),
            float(cast(Any, header["BMIN"]))
            / abs(float(cast(Any, header["CDELT1"]))),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError("image has no valid restoring beam") from error


def _parse_args() -> argparse.Namespace:
    """Parse one no-write diagnostic invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--rms", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--component-labels", type=Path)
    parser.add_argument("--association", required=True, type=Path)
    parser.add_argument("--peak-threshold-sigma", type=float, default=8.0)
    parser.add_argument(
        "--require-resolved",
        action="store_true",
        help="exit non-zero when a support has fewer components than peaks",
    )
    return parser.parse_args()


def main() -> None:
    """Print one canonical diagnostic without writing scientific products."""
    arguments = _parse_args()
    result = summarize_catalogue_topology(
        _fits_plane(arguments.image),
        _fits_plane(arguments.background),
        _fits_plane(arguments.rms),
        _fits_plane(arguments.labels),
        beam_width_pixels=_beam_width_pixels(arguments.image),
        component_label_values=_component_labels(arguments.association),
        component_labels=(
            _fits_plane(arguments.component_labels)
            if arguments.component_labels is not None
            else None
        ),
        peak_threshold_sigma=arguments.peak_threshold_sigma,
    )
    print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    if arguments.require_resolved and result["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
