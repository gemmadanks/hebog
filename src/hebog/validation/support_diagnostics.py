"""Descriptive diagnostics for disagreements between support label planes.

These helpers compare source-finder products; they do not designate either
finder as scientific truth. They operate in memory and are intended for
bounded validation cutouts and campaign notebooks, not production execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class SupportComponentSummary:
    """Pixel overlap summary for one reference support component."""

    reference_label: int
    candidate_labels: tuple[int, ...]
    reference_pixel_count: int
    candidate_pixel_count: int
    intersection_pixel_count: int
    reference_only_pixel_count: int
    candidate_only_pixel_count: int
    precision: float | None
    recall: float
    intersection_over_union: float

    @property
    def fragment_count(self) -> int:
        """Return the number of candidate labels touching the component."""
        return len(self.candidate_labels)


@dataclass(frozen=True, slots=True)
class SupportComponentComparison:
    """One component summary plus its union bounding box."""

    summary: SupportComponentSummary
    bounds_yx_half_open: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class SupportRoleMasks:
    """Disjoint pixel roles for one support-component comparison."""

    common: npt.NDArray[np.bool_]
    reference_only: npt.NDArray[np.bool_]
    candidate_only: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class SupportPixelEvidence:
    """Image-domain evidence for one disjoint support role.

    Flux fields assume that the supplied image, background, and RMS planes are
    in Jy/beam and divide their pixel sums by ``beam_area_pixels``.
    """

    pixel_count: int
    valid_pixel_count: int
    beam_area_count: float
    raw_flux_jy: float | None
    background_flux_jy: float | None
    residual_flux_jy: float | None
    rms_median_jy_per_beam: float | None
    direct_snr_p10: float | None
    direct_snr_median: float | None
    direct_snr_p90: float | None
    direct_snr_maximum: float | None
    at_least_3_sigma_pixel_count: int
    at_least_5_sigma_pixel_count: int


@dataclass(frozen=True, slots=True)
class SupportComponentEvidence:
    """Image-domain evidence split by support agreement role."""

    common: SupportPixelEvidence
    reference_only: SupportPixelEvidence
    candidate_only: SupportPixelEvidence


LabelPlane = npt.NDArray[np.integer[Any]]
_PLANE_DIMENSIONS = 2
_ISLAND_THRESHOLD_SIGMA = 3.0
_PEAK_THRESHOLD_SIGMA = 5.0


def _validate_label_planes(
    candidate_labels: npt.ArrayLike,
    reference_labels: npt.ArrayLike,
) -> tuple[LabelPlane, LabelPlane]:
    candidate = np.asarray(candidate_labels)
    reference = np.asarray(reference_labels)
    if (
        candidate.ndim != _PLANE_DIMENSIONS
        or reference.ndim != _PLANE_DIMENSIONS
    ):
        raise ValueError("support label planes must be two-dimensional")
    if candidate.shape != reference.shape:
        raise ValueError("support label planes must have the same shape")
    if not np.issubdtype(candidate.dtype, np.integer) or not np.issubdtype(
        reference.dtype, np.integer
    ):
        raise ValueError("support planes must contain integer labels")
    if np.any(candidate < 0) or np.any(reference < 0):
        raise ValueError("support labels must be non-negative")
    return candidate, reference


def _summary(
    *,
    reference_label: int,
    candidate_labels: tuple[int, ...],
    reference_pixel_count: int,
    candidate_pixel_count: int,
    intersection_pixel_count: int,
) -> SupportComponentSummary:
    reference_only = reference_pixel_count - intersection_pixel_count
    candidate_only = candidate_pixel_count - intersection_pixel_count
    union = reference_pixel_count + candidate_only
    return SupportComponentSummary(
        reference_label=reference_label,
        candidate_labels=candidate_labels,
        reference_pixel_count=reference_pixel_count,
        candidate_pixel_count=candidate_pixel_count,
        intersection_pixel_count=intersection_pixel_count,
        reference_only_pixel_count=reference_only,
        candidate_only_pixel_count=candidate_only,
        precision=(
            intersection_pixel_count / candidate_pixel_count
            if candidate_pixel_count
            else None
        ),
        recall=intersection_pixel_count / reference_pixel_count,
        intersection_over_union=intersection_pixel_count / union,
    )


def compare_support_component(
    candidate_labels: npt.ArrayLike,
    reference_labels: npt.ArrayLike,
    reference_label: int,
) -> SupportComponentComparison:
    """Compare all candidate labels touching one positive reference label."""
    candidate, reference = _validate_label_planes(
        candidate_labels,
        reference_labels,
    )
    if reference_label <= 0:
        raise ValueError("reference_label must be positive")
    reference_mask = reference == reference_label
    reference_pixel_count = int(np.count_nonzero(reference_mask))
    if reference_pixel_count == 0:
        raise ValueError(f"reference label {reference_label} is absent")

    touching = np.unique(candidate[reference_mask])
    candidate_ids = tuple(int(value) for value in touching if value > 0)
    candidate_mask = (
        np.isin(candidate, candidate_ids)
        if candidate_ids
        else np.zeros(candidate.shape, dtype=np.bool_)
    )
    intersection_pixel_count = int(
        np.count_nonzero(reference_mask & candidate_mask)
    )
    candidate_pixel_count = int(np.count_nonzero(candidate_mask))
    union_mask = reference_mask | candidate_mask
    y_indices, x_indices = np.nonzero(union_mask)
    bounds = (
        int(y_indices.min()),
        int(y_indices.max()) + 1,
        int(x_indices.min()),
        int(x_indices.max()) + 1,
    )
    return SupportComponentComparison(
        summary=_summary(
            reference_label=reference_label,
            candidate_labels=candidate_ids,
            reference_pixel_count=reference_pixel_count,
            candidate_pixel_count=candidate_pixel_count,
            intersection_pixel_count=intersection_pixel_count,
        ),
        bounds_yx_half_open=bounds,
    )


def rank_reference_support_disagreements(
    candidate_labels: npt.ArrayLike,
    reference_labels: npt.ArrayLike,
) -> tuple[SupportComponentSummary, ...]:
    """Rank reference components by fragmentation, then omitted support.

    The ordering puts visibly split components first and breaks ties by the
    number of reference-only pixels. It is a diagnostic triage order, not a
    scientific quality score.
    """
    candidate, reference = _validate_label_planes(
        candidate_labels,
        reference_labels,
    )
    positive_reference = reference > 0
    reference_ids, reference_counts = np.unique(
        reference[positive_reference],
        return_counts=True,
    )
    if reference_ids.size == 0:
        return ()

    positive_candidate = candidate > 0
    candidate_ids, candidate_counts = np.unique(
        candidate[positive_candidate],
        return_counts=True,
    )
    candidate_count_by_id = {
        int(label): int(count)
        for label, count in zip(candidate_ids, candidate_counts, strict=True)
    }
    overlap = positive_reference & positive_candidate
    intersection_by_reference: dict[int, list[tuple[int, int]]] = {}
    if np.any(overlap):
        pairs = np.column_stack((reference[overlap], candidate[overlap]))
        unique_pairs, pair_counts = np.unique(
            pairs,
            axis=0,
            return_counts=True,
        )
        for pair, count in zip(unique_pairs, pair_counts, strict=True):
            reference_id, candidate_id = (int(value) for value in pair)
            intersection_by_reference.setdefault(reference_id, []).append(
                (candidate_id, int(count))
            )

    summaries: list[SupportComponentSummary] = []
    for raw_reference_id, raw_reference_count in zip(
        reference_ids,
        reference_counts,
        strict=True,
    ):
        reference_id = int(raw_reference_id)
        intersections = intersection_by_reference.get(reference_id, [])
        touching_ids = tuple(sorted(item[0] for item in intersections))
        summaries.append(
            _summary(
                reference_label=reference_id,
                candidate_labels=touching_ids,
                reference_pixel_count=int(raw_reference_count),
                candidate_pixel_count=sum(
                    candidate_count_by_id[label] for label in touching_ids
                ),
                intersection_pixel_count=sum(
                    count for _, count in intersections
                ),
            )
        )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (
                -item.fragment_count,
                -item.reference_only_pixel_count,
                -item.reference_pixel_count,
                item.reference_label,
            ),
        )
    )


def support_component_masks(
    comparison: SupportComponentComparison,
    candidate_labels: npt.ArrayLike,
    reference_labels: npt.ArrayLike,
) -> SupportRoleMasks:
    """Return common and one-sided masks for a component comparison."""
    candidate, reference = _validate_label_planes(
        candidate_labels,
        reference_labels,
    )
    summary = comparison.summary
    reference_mask = reference == summary.reference_label
    candidate_mask = (
        np.isin(candidate, summary.candidate_labels)
        if summary.candidate_labels
        else np.zeros(candidate.shape, dtype=np.bool_)
    )
    return SupportRoleMasks(
        common=reference_mask & candidate_mask,
        reference_only=reference_mask & ~candidate_mask,
        candidate_only=candidate_mask & ~reference_mask,
    )


def _validate_evidence_planes(
    shape: tuple[int, int],
    *,
    image: npt.ArrayLike,
    background: npt.ArrayLike,
    rms: npt.ArrayLike,
) -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]:
    planes = (
        np.asarray(image, dtype=np.float64),
        np.asarray(background, dtype=np.float64),
        np.asarray(rms, dtype=np.float64),
    )
    if any(plane.shape != shape for plane in planes):
        raise ValueError("evidence planes and labels must have the same shape")
    return planes


def summarize_support_pixels(
    mask: npt.ArrayLike,
    *,
    image: npt.ArrayLike,
    background: npt.ArrayLike,
    rms: npt.ArrayLike,
    beam_area_pixels: float,
) -> SupportPixelEvidence:
    """Summarize direct-S/N and flux evidence under one Boolean mask."""
    selected = np.asarray(mask, dtype=np.bool_)
    if selected.ndim != _PLANE_DIMENSIONS:
        raise ValueError("support evidence mask must be two-dimensional")
    if not np.isfinite(beam_area_pixels) or beam_area_pixels <= 0.0:
        raise ValueError("beam_area_pixels must be finite and positive")
    image_plane, background_plane, rms_plane = _validate_evidence_planes(
        selected.shape,
        image=image,
        background=background,
        rms=rms,
    )
    valid = (
        selected
        & np.isfinite(image_plane)
        & np.isfinite(background_plane)
        & np.isfinite(rms_plane)
        & (rms_plane > 0.0)
    )
    pixel_count = int(np.count_nonzero(selected))
    valid_pixel_count = int(np.count_nonzero(valid))
    if valid_pixel_count == 0:
        return SupportPixelEvidence(
            pixel_count=pixel_count,
            valid_pixel_count=0,
            beam_area_count=pixel_count / beam_area_pixels,
            raw_flux_jy=None,
            background_flux_jy=None,
            residual_flux_jy=None,
            rms_median_jy_per_beam=None,
            direct_snr_p10=None,
            direct_snr_median=None,
            direct_snr_p90=None,
            direct_snr_maximum=None,
            at_least_3_sigma_pixel_count=0,
            at_least_5_sigma_pixel_count=0,
        )

    residual = image_plane[valid] - background_plane[valid]
    direct_snr = residual / rms_plane[valid]
    p10, median, p90 = np.quantile(direct_snr, (0.1, 0.5, 0.9))
    return SupportPixelEvidence(
        pixel_count=pixel_count,
        valid_pixel_count=valid_pixel_count,
        beam_area_count=pixel_count / beam_area_pixels,
        raw_flux_jy=float(np.sum(image_plane[valid]) / beam_area_pixels),
        background_flux_jy=float(
            np.sum(background_plane[valid]) / beam_area_pixels
        ),
        residual_flux_jy=float(np.sum(residual) / beam_area_pixels),
        rms_median_jy_per_beam=float(np.median(rms_plane[valid])),
        direct_snr_p10=float(p10),
        direct_snr_median=float(median),
        direct_snr_p90=float(p90),
        direct_snr_maximum=float(np.max(direct_snr)),
        at_least_3_sigma_pixel_count=int(
            np.count_nonzero(direct_snr >= _ISLAND_THRESHOLD_SIGMA)
        ),
        at_least_5_sigma_pixel_count=int(
            np.count_nonzero(direct_snr >= _PEAK_THRESHOLD_SIGMA)
        ),
    )


def summarize_support_component_evidence(  # noqa: PLR0913
    comparison: SupportComponentComparison,
    candidate_labels: npt.ArrayLike,
    reference_labels: npt.ArrayLike,
    *,
    image: npt.ArrayLike,
    background: npt.ArrayLike,
    rms: npt.ArrayLike,
    beam_area_pixels: float,
) -> SupportComponentEvidence:
    """Summarize image evidence for all roles in one comparison."""
    masks = support_component_masks(
        comparison,
        candidate_labels,
        reference_labels,
    )
    return SupportComponentEvidence(
        common=summarize_support_pixels(
            masks.common,
            image=image,
            background=background,
            rms=rms,
            beam_area_pixels=beam_area_pixels,
        ),
        reference_only=summarize_support_pixels(
            masks.reference_only,
            image=image,
            background=background,
            rms=rms,
            beam_area_pixels=beam_area_pixels,
        ),
        candidate_only=summarize_support_pixels(
            masks.candidate_only,
            image=image,
            background=background,
            rms=rms,
            beam_area_pixels=beam_area_pixels,
        ),
    )
