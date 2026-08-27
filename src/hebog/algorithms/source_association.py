# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Conservative deterministic grouping of immutable detection components."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from itertools import combinations
from math import isfinite
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import label as connected_component_labels

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationEdge,
    SourceAssociationResult,
)

_COMPONENT_NAMESPACE = b"phase-5-detection-component-v1\0"
_SOURCE_NAMESPACE = b"phase-5-associated-source-v1\0"
_IMAGE_DIMENSIONS = 2
_MINIMUM_SHAPE_PIXELS = 3
_GAUSSIAN_FWHM_FACTOR = 2.0 * np.sqrt(2.0 * np.log(2.0))


def _stable_id(namespace: bytes, prefix: str, values: tuple[str, ...]) -> str:
    """Hash canonical identity fields into one stable domain identifier."""
    digest = sha256(namespace)
    for value in values:
        digest.update(value.encode("ascii"))
        digest.update(b"\0")
    return f"{prefix}-{digest.hexdigest()}"


def _component_id(canonical_pixel_yx: tuple[int, int]) -> str:
    """Derive identity from the component's global canonical owner pixel."""
    return _stable_id(
        _COMPONENT_NAMESPACE,
        "component-detection",
        tuple(str(value) for value in canonical_pixel_yx),
    )


def _source_id(component_ids: tuple[str, ...]) -> str:
    """Derive one source identity from sorted stable component membership."""
    return _stable_id(
        _SOURCE_NAMESPACE,
        "source-associated",
        component_ids,
    )


def _validated_planes(
    component_labels: npt.ArrayLike,
    association_signal: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.int64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
]:
    """Return aligned component, signal, and validity planes."""
    label_values = np.asarray(component_labels)
    signal_values = np.asarray(association_signal)
    valid = np.asarray(valid_pixels)
    if (
        label_values.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(label_values.dtype, np.integer)
        or bool(np.any(label_values < 0))
    ):
        raise ValueError(
            "component labels must be a non-negative integer plane"
        )
    if (
        signal_values.ndim != _IMAGE_DIMENSIONS
        or signal_values.shape != label_values.shape
        or not np.issubdtype(signal_values.dtype, np.number)
        or np.iscomplexobj(signal_values)
    ):
        raise ValueError("association signal must be one aligned real plane")
    if (
        valid.ndim != _IMAGE_DIMENSIONS
        or valid.shape != label_values.shape
        or valid.dtype != np.bool_
    ):
        raise ValueError("valid pixels must be one aligned boolean plane")
    if bool(np.any((label_values > 0) & ~valid)):
        raise ValueError("component owner pixels must be scientifically valid")
    return (
        np.asarray(label_values, dtype=np.int64),
        np.asarray(signal_values, dtype=np.float64),
        np.asarray(valid, dtype=np.bool_),
    )


def _positive_moment_geometry(
    signal: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    *,
    origin_yx: tuple[int, int],
) -> tuple[
    tuple[float, float],
    tuple[tuple[float, float], tuple[float, float]] | None,
]:
    """Return positive-signal centroid and exact-support covariance."""
    positive = support & np.isfinite(signal) & (signal > 0.0)
    if not bool(np.any(positive)):
        y_pixels, x_pixels = np.nonzero(support)
        return (
            float(np.mean(y_pixels)) + origin_yx[0],
            float(np.mean(x_pixels)) + origin_yx[1],
        ), None
    weights = signal[positive]
    weight = float(np.sum(weights, dtype=np.float64))
    y_pixels, x_pixels = np.nonzero(positive)
    centroid_y = float(np.sum(y_pixels * weights, dtype=np.float64) / weight)
    centroid_x = float(np.sum(x_pixels * weights, dtype=np.float64) / weight)
    centroid = (
        centroid_y + origin_yx[0],
        centroid_x + origin_yx[1],
    )
    if weights.size < _MINIMUM_SHAPE_PIXELS:
        return centroid, None
    delta_y = y_pixels - centroid_y
    delta_x = x_pixels - centroid_x
    yy = float(np.sum(weights * delta_y * delta_y) / weight)
    yx = float(np.sum(weights * delta_y * delta_x) / weight)
    xx = float(np.sum(weights * delta_x * delta_x) / weight)
    if (
        not all(isfinite(value) for value in (yy, yx, xx))
        or yy <= 0.0
        or xx <= 0.0
        or yy * xx - yx * yx <= 0.0
    ):
        return centroid, None
    return centroid, ((yy, yx), (yx, xx))


def build_detection_component_records(
    component_labels: npt.ArrayLike,
    association_signal: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    origin_yx: tuple[int, int] = (0, 0),
    canonical_component_references_yx: (
        Mapping[int, tuple[int, int]] | None
    ) = None,
) -> tuple[DetectionComponentRecord, ...]:
    """Build stable component records from immutable exact owner support."""
    if len(origin_yx) != _IMAGE_DIMENSIONS or min(origin_yx) < 0:
        raise ValueError("component origin must contain non-negative y-x")
    labels, signal, valid = _validated_planes(
        component_labels,
        association_signal,
        valid_pixels,
    )
    records: list[DetectionComponentRecord] = []
    for label_value in sorted(
        int(value) for value in np.unique(labels) if value > 0
    ):
        support = (labels == label_value) & valid
        local_pixels = np.column_stack(np.nonzero(support))
        first_local = tuple(int(value) for value in local_pixels[0])
        derived_reference = (
            first_local[0] + origin_yx[0],
            first_local[1] + origin_yx[1],
        )
        canonical_reference = (
            canonical_component_references_yx.get(
                label_value,
                derived_reference,
            )
            if canonical_component_references_yx is not None
            else derived_reference
        )
        if min(canonical_reference) < 0:
            raise ValueError("canonical component references must be positive")
        centroid, covariance = _positive_moment_geometry(
            signal,
            support,
            origin_yx=origin_yx,
        )
        records.append(
            DetectionComponentRecord(
                component_id=_component_id(canonical_reference),
                label_value=label_value,
                canonical_pixel_yx=canonical_reference,
                centroid_yx=centroid,
                covariance_pixels_squared=covariance,
            )
        )
    return tuple(sorted(records, key=lambda item: item.canonical_pixel_yx))


def _validated_association_inputs(  # noqa: PLR0913
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    island_threshold_sigma: float,
) -> tuple[
    npt.NDArray[np.int64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
]:
    """Validate complete records and aligned frozen graph evidence."""
    labels, snr, valid = _validated_planes(
        component_labels,
        combined_snr,
        valid_pixels,
    )
    significant = np.asarray(significant_multiscale_support)
    if (
        significant.ndim != _IMAGE_DIMENSIONS
        or significant.shape != labels.shape
        or significant.dtype != np.bool_
    ):
        raise ValueError(
            "significant multiscale support must be one aligned boolean plane"
        )
    if (
        isinstance(island_threshold_sigma, bool)
        or not isfinite(island_threshold_sigma)
        or island_threshold_sigma <= 0.0
    ):
        raise ValueError("island threshold sigma must be finite and positive")
    label_values = tuple(
        sorted(int(value) for value in np.unique(labels) if value > 0)
    )
    record_labels = tuple(sorted(item.label_value for item in records))
    record_ids = tuple(item.component_id for item in records)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("component record IDs must be unique")
    if not records or record_labels != label_values:
        raise ValueError("component records must cover every positive label")
    return labels, significant, snr, valid


def _parent_support_by_label(
    records: tuple[DetectionComponentRecord, ...],
    labels: npt.NDArray[np.int64],
    significant: npt.NDArray[np.bool_],
    valid: npt.NDArray[np.bool_],
) -> dict[int, int]:
    """Map each owner to its undilated eight-connected parent support."""
    parent_labels, _ = cast(
        tuple[npt.NDArray[np.int64], int],
        connected_component_labels(
            ((labels > 0) | significant) & valid,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    output: dict[int, int] = {}
    for record in records:
        local_pixels = np.column_stack(
            np.nonzero(labels == record.label_value)
        )
        output[record.label_value] = int(parent_labels[tuple(local_pixels[0])])
    return output


def _line_pixels(
    first_yx: tuple[float, float],
    second_yx: tuple[float, float],
) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
    """Return deterministic nearest pixels on one straight centroid segment."""
    span = max(
        abs(second_yx[0] - first_yx[0]),
        abs(second_yx[1] - first_yx[1]),
    )
    sample_count = max(2, int(np.ceil(span)) + 1)
    y_pixels = np.rint(
        np.linspace(first_yx[0], second_yx[0], sample_count)
    ).astype(np.intp)
    x_pixels = np.rint(
        np.linspace(first_yx[1], second_yx[1], sample_count)
    ).astype(np.intp)
    return y_pixels, x_pixels


def _directional_fwhm_pixels(
    record: DetectionComponentRecord,
    unit_yx: npt.NDArray[np.float64],
) -> float | None:
    """Project one reviewed component covariance onto the joining line."""
    covariance = record.covariance_pixels_squared
    if covariance is None:
        return None
    values = np.asarray(covariance, dtype=np.float64)
    variance = float(unit_yx @ values @ unit_yx)
    if not isfinite(variance) or variance <= 0.0:
        return None
    return float(_GAUSSIAN_FWHM_FACTOR * np.sqrt(variance))


def _association_edge(  # noqa: PLR0911, PLR0913
    first: DetectionComponentRecord,
    second: DetectionComponentRecord,
    *,
    parent_support: dict[int, int],
    snr: npt.NDArray[np.float64],
    valid: npt.NDArray[np.bool_],
    origin_yx: tuple[int, int],
    island_threshold_sigma: float,
) -> SourceAssociationEdge | None:
    """Return one edge only when every frozen pair requirement passes."""
    if parent_support[first.label_value] != parent_support[second.label_value]:
        return None
    delta = np.subtract(
        second.centroid_yx, first.centroid_yx, dtype=np.float64
    )
    separation = float(np.linalg.norm(delta))
    if not isfinite(separation) or separation <= 0.0:
        return None
    unit_yx = np.asarray(delta / separation, dtype=np.float64)
    first_fwhm = _directional_fwhm_pixels(first, unit_yx)
    second_fwhm = _directional_fwhm_pixels(second, unit_yx)
    if first_fwhm is None or second_fwhm is None:
        return None
    maximum_separation = 0.5 * (first_fwhm + second_fwhm)
    normalized_separation = separation / maximum_separation
    if normalized_separation > 1.0:
        return None
    local_first = (
        first.centroid_yx[0] - origin_yx[0],
        first.centroid_yx[1] - origin_yx[1],
    )
    local_second = (
        second.centroid_yx[0] - origin_yx[0],
        second.centroid_yx[1] - origin_yx[1],
    )
    y_pixels, x_pixels = _line_pixels(local_first, local_second)
    if (
        bool(np.any(y_pixels < 0))
        or bool(np.any(x_pixels < 0))
        or bool(np.any(y_pixels >= snr.shape[0]))
        or bool(np.any(x_pixels >= snr.shape[1]))
        or not bool(np.all(valid[y_pixels, x_pixels]))
    ):
        return None
    line_snr = snr[y_pixels, x_pixels]
    if not bool(np.all(np.isfinite(line_snr))):
        return None
    saddle_margin = float(np.min(line_snr) - island_threshold_sigma)
    if saddle_margin < 0.0:
        return None
    first_id, second_id = sorted((first.component_id, second.component_id))
    return SourceAssociationEdge(
        first_component_id=first_id,
        second_component_id=second_id,
        saddle_margin_sigma=saddle_margin,
        normalized_separation=normalized_separation,
    )


def _canonical_edges(
    edges: tuple[SourceAssociationEdge, ...],
) -> tuple[SourceAssociationEdge, ...]:
    """Deduplicate exact executor evidence and reject disagreement."""
    by_key: dict[tuple[str, str], SourceAssociationEdge] = {}
    for edge in edges:
        key = (edge.first_component_id, edge.second_component_id)
        existing = by_key.setdefault(key, edge)
        if existing != edge:
            raise ValueError("duplicate association edges disagree")
    return tuple(by_key[key] for key in sorted(by_key))


def reduce_source_associations(
    records: tuple[DetectionComponentRecord, ...],
    edges: tuple[SourceAssociationEdge, ...],
) -> SourceAssociationResult:
    """Reduce pair evidence with deterministic complete-link agglomeration."""
    ordered_records = tuple(
        sorted(records, key=lambda item: item.component_id)
    )
    component_ids = tuple(item.component_id for item in ordered_records)
    if len(set(component_ids)) != len(component_ids):
        raise ValueError("component record IDs must be unique")
    canonical_edges = _canonical_edges(edges)
    known_edges = {
        (edge.first_component_id, edge.second_component_id)
        for edge in canonical_edges
    }
    if any(
        component_id not in set(component_ids)
        for edge in canonical_edges
        for component_id in (
            edge.first_component_id,
            edge.second_component_id,
        )
    ):
        raise ValueError("association edge names an unknown component")
    groups: list[set[str]] = [{component_id} for component_id in component_ids]
    science_order = sorted(
        canonical_edges,
        key=lambda item: (
            -item.saddle_margin_sigma,
            item.normalized_separation,
            item.first_component_id,
            item.second_component_id,
        ),
    )
    for edge in science_order:
        first_group = next(
            group for group in groups if edge.first_component_id in group
        )
        second_group = next(
            group for group in groups if edge.second_component_id in group
        )
        if first_group is second_group:
            continue
        if all(
            tuple(sorted((first_id, second_id))) in known_edges
            for first_id in first_group
            for second_id in second_group
        ):
            first_group.update(second_group)
            groups.remove(second_group)
    memberships = tuple(
        sorted(
            (
                CatalogueSourceMembership(
                    source_id=_source_id(tuple(sorted(group))),
                    component_ids=tuple(sorted(group)),
                )
                for group in groups
            ),
            key=lambda item: item.source_id,
        )
    )
    return SourceAssociationResult(
        components=ordered_records,
        edges=canonical_edges,
        memberships=memberships,
    )


def associate_detection_components(  # noqa: PLR0913
    records: tuple[DetectionComponentRecord, ...],
    component_labels: npt.ArrayLike,
    significant_multiscale_support: npt.ArrayLike,
    combined_snr: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    *,
    island_threshold_sigma: float,
    origin_yx: tuple[int, int] = (0, 0),
) -> SourceAssociationResult:
    """Build undilated pair evidence and reduce it to source memberships."""
    if len(origin_yx) != _IMAGE_DIMENSIONS or min(origin_yx) < 0:
        raise ValueError("association origin must contain non-negative y-x")
    labels, significant, snr, valid = _validated_association_inputs(
        records,
        component_labels,
        significant_multiscale_support,
        combined_snr,
        valid_pixels,
        island_threshold_sigma=island_threshold_sigma,
    )
    parent_support = _parent_support_by_label(
        records,
        labels,
        significant,
        valid,
    )
    edges = tuple(
        edge
        for first, second in combinations(records, 2)
        if (
            edge := _association_edge(
                first,
                second,
                parent_support=parent_support,
                snr=snr,
                valid=valid,
                origin_yx=origin_yx,
                island_threshold_sigma=island_threshold_sigma,
            )
        )
        is not None
    )
    return reduce_source_associations(records, edges)
