# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Candidate-neutral evaluation utilities for Phase 5 Step 2B."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot, sqrt
from typing import Literal, TypeVar, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation, label

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    FilterFamily,
    PreparedScaleInputs,
    ResidualAtrousResult,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    build_residual_atrous_plan,
    build_scale_filter_bank,
    evaluate_residual_atrous,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
    reconstruct_significant_atrous,
)
from hebog.validation.contracts import (
    PhaseFiveCorrectiveReview,
    PhaseFiveCorrectiveRReview,
    PhaseFiveFilterReview,
)
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_image,
    iter_dataset_recipes,
)

_FWHM_TO_SIGMA = 1.0 / (2.0 * sqrt(2.0 * np.log(2.0)))
_ANALYTIC_SHAPE = (193, 193)
_ANALYTIC_RMS = 0.01
_TRUNCATION_SIGMA = 4.0
_MINIMUM_REVIEW_SUPPORT = 0.5
_MINIMUM_TOPOLOGY_COMPONENTS = 3
_ArrayScalar = TypeVar("_ArrayScalar", bound=np.generic)
_ReviewContract = (
    PhaseFiveFilterReview
    | PhaseFiveCorrectiveReview
    | PhaseFiveCorrectiveRReview
)


def _read_only(
    array: npt.NDArray[_ArrayScalar],
) -> npt.NDArray[_ArrayScalar]:
    """Return an array protected from accidental review-time mutation."""
    array.setflags(write=False)
    return array


@dataclass(frozen=True, slots=True)
class AnalyticFilterReviewCase:
    """One exact Gaussian response case shared by both candidates."""

    identifier: str
    scale_order: int
    scale_beams: float
    geometry: str
    input_peak_snr: float
    expected_integrated_flux_jy: float
    centre_xy: tuple[int, int]
    image_jy_per_beam: npt.NDArray[np.float64]
    valid_pixels: npt.NDArray[np.bool_]
    background_jy_per_beam: npt.NDArray[np.float64]
    rms_jy_per_beam: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class AnalyticFilterObservation:
    """One candidate's measurements on an exact paired analytic case."""

    case_identifier: str
    family: FilterFamily
    scale_order: int
    geometry: str
    input_peak_snr: float
    support_fraction: float
    available: bool
    response_fractional_error: float | None
    integrated_flux_fractional_error: float | None
    calibrated_response_snr: float | None
    position_error_beams: float | None
    negative_lobe_fraction: float | None


@dataclass(frozen=True, slots=True)
class ThresholdFilterResult:
    """Candidate-neutral 5-sigma seeds and connected 3-sigma support."""

    combined_snr: npt.NDArray[np.float64]
    retained_mask: npt.NDArray[np.bool_]
    component_labels: npt.NDArray[np.int32]
    component_count: int


@dataclass(frozen=True, slots=True)
class CandidateScientificDecision:
    """Science and bounded-cost state used by the frozen decision order."""

    family: FilterFamily
    passes_absolute: bool
    noninferior_to_other: bool
    bounded_cost: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class GeneratedGroupObservation:
    """One truth group's candidate-neutral generated-image measurements."""

    group_identifier: str
    morphology: str
    scale_orders: tuple[int, ...]
    detected: bool
    maximum_snr: float
    integrated_flux_fractional_error: float | None
    position_error_beams: float | None
    support_available: bool
    fragment_count: int
    measurement_disposition: Literal[
        "measured",
        "known-artifact-control",
        "truncated-observable-domain",
    ] = "measured"
    position_offset_xy_beams: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class GeneratedImageObservation:
    """One candidate's complete minimal-threshold image observation."""

    dataset_identifier: str
    seed: int
    family: FilterFamily
    groups: tuple[GeneratedGroupObservation, ...]
    completeness: float
    reliability: float
    mask_intersection_over_union: float
    fragmentation_fraction: float
    noise_std_fractional_error: float
    component_count: int


@dataclass(frozen=True, slots=True)
class _GeneratedTruthGroup:
    """Reusable noiseless truth masks for all seeds in one dataset."""

    identifier: str
    morphology: str
    catalogue_role: Literal["astronomical-source", "artifact"]
    scale_orders: tuple[int, ...]
    reference_position_xy: tuple[float, float]
    reference_integrated_flux: float
    detection_mask: npt.NDArray[np.bool_]
    flux_aperture: npt.NDArray[np.bool_]
    signal_jy_per_beam: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class _ObservableMeasurementPlanes:
    """Original and truth planes used by the governed endpoint evaluator."""

    residual: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    valid_pixels: npt.NDArray[np.bool_]
    truth_signal: npt.NDArray[np.float64]
    component_labels: npt.NDArray[np.int32]


@dataclass(frozen=True, slots=True)
class _CorrectiveObservationContext:
    """Shared final-output state for generated group observations."""

    thresholded: ThresholdFilterResult
    response_source: ScaleFilterBankResult | ResidualAtrousResult
    prepared: PreparedScaleInputs
    beam: BeamShapePixels
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview


def _elliptical_gaussian(
    beam: BeamShapePixels,
    shape_yx: tuple[int, int],
    *,
    centre_xy: tuple[int, int],
    scale_beams: float,
    integrated_flux_jy: float,
) -> npt.NDArray[np.float64]:
    """Return a beam-aligned Gaussian with known integrated-flux response."""
    y_grid, x_grid = np.indices(shape_yx, dtype=np.float64)
    x_offset = x_grid - centre_xy[0]
    y_offset = y_grid - centre_xy[1]
    angle = np.deg2rad(beam.position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    major_offset = cosine * x_offset + sine * y_offset
    minor_offset = -sine * x_offset + cosine * y_offset
    major_sigma = beam.major_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA
    minor_sigma = beam.minor_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA
    return np.asarray(
        integrated_flux_jy
        / scale_beams**2
        * np.exp(
            -0.5
            * (
                np.square(major_offset / major_sigma)
                + np.square(minor_offset / minor_sigma)
            )
        ),
        dtype=np.float64,
    )


def _geometry_case(
    beam: BeamShapePixels,
    *,
    geometry: str,
    scale_beams: float,
    integrated_flux_jy: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_], tuple[int, int]]:
    """Construct one exact edge or missing-support geometry."""
    height, width = _ANALYTIC_SHAPE
    centre_xy = (width // 2, height // 2)
    edge_offset = ceil(beam.major_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA)
    if geometry == "image-edge":
        centre_xy = (edge_offset, height // 2)
    elif geometry == "image-corner":
        centre_xy = (edge_offset, edge_offset)

    image = _elliptical_gaussian(
        beam,
        _ANALYTIC_SHAPE,
        centre_xy=centre_xy,
        scale_beams=scale_beams,
        integrated_flux_jy=integrated_flux_jy,
    )
    valid = np.ones(_ANALYTIC_SHAPE, dtype=np.bool_)
    centre_x, centre_y = centre_xy
    y_grid, x_grid = np.indices(_ANALYTIC_SHAPE)
    if geometry == "vertical-half-plane":
        valid[:, : centre_x - 1] = False
    elif geometry == "horizontal-half-plane":
        valid[: centre_y - 1, :] = False
    elif geometry == "diagonal-half-plane":
        valid[x_grid + y_grid < centre_x + centre_y - 2] = False
    elif geometry == "irregular-hole":
        hole_width = max(2, edge_offset)
        valid[
            max(0, centre_y - hole_width) : centre_y + hole_width + 1,
            max(0, centre_x - hole_width) : centre_x,
        ] = False
    elif geometry not in {"unmasked", "image-edge", "image-corner"}:
        raise ValueError(f"unsupported analytic geometry: {geometry}")
    image[~valid] = np.nan
    return image, valid, centre_xy


def build_analytic_review_cases(
    beam: BeamShapePixels,
    review: _ReviewContract,
) -> tuple[AnalyticFilterReviewCase, ...]:
    """Build the complete frozen analytic matrix without candidate results."""
    scale_widths = dict(
        zip(review.matrix.scale_orders, (1.0, 2.0, 4.0), strict=True)
    )
    cases: list[AnalyticFilterReviewCase] = []
    for scale_order in review.matrix.scale_orders:
        scale_beams = scale_widths[scale_order]
        for geometry in review.matrix.mask_geometries:
            for input_peak_snr in review.matrix.snr_levels:
                integrated_flux = (
                    input_peak_snr * _ANALYTIC_RMS * scale_beams**2
                )
                image, valid, centre_xy = _geometry_case(
                    beam,
                    geometry=geometry,
                    scale_beams=scale_beams,
                    integrated_flux_jy=integrated_flux,
                )
                background = np.zeros(_ANALYTIC_SHAPE, dtype=np.float64)
                rms = np.full(
                    _ANALYTIC_SHAPE,
                    _ANALYTIC_RMS,
                    dtype=np.float64,
                )
                identifier = (
                    f"scale-{scale_order}-{geometry}-snr-{input_peak_snr:g}"
                )
                cases.append(
                    AnalyticFilterReviewCase(
                        identifier=identifier,
                        scale_order=scale_order,
                        scale_beams=scale_beams,
                        geometry=geometry,
                        input_peak_snr=input_peak_snr,
                        expected_integrated_flux_jy=integrated_flux,
                        centre_xy=centre_xy,
                        image_jy_per_beam=_read_only(image),
                        valid_pixels=_read_only(valid),
                        background_jy_per_beam=_read_only(background),
                        rms_jy_per_beam=_read_only(rms),
                    )
                )
    return tuple(cases)


def _position_and_negative_lobe(
    scale_response: ScaleFilterResponse,
    *,
    centre_xy: tuple[int, int],
    beam: BeamShapePixels,
    scale_beams: float,
    expected_flux: float,
) -> tuple[float, float]:
    """Measure local peak position and signed annular response depth."""
    response = scale_response.response_jy_per_beam
    effective_rms = scale_response.effective_rms_jy_per_beam
    centre_x, centre_y = centre_xy
    radius = ceil(beam.major_fwhm_pixels * scale_beams)
    y_start = max(0, centre_y - radius)
    y_stop = min(response.shape[0], centre_y + radius + 1)
    x_start = max(0, centre_x - radius)
    x_stop = min(response.shape[1], centre_x + radius + 1)
    local_response = response[y_start:y_stop, x_start:x_stop]
    local_rms = effective_rms[y_start:y_stop, x_start:x_stop]
    local_snr = np.full(local_response.shape, -np.inf, dtype=np.float64)
    np.divide(
        local_response,
        local_rms,
        out=local_snr,
        where=np.isfinite(local_response) & np.isfinite(local_rms),
    )
    peak_y, peak_x = np.unravel_index(np.argmax(local_snr), local_snr.shape)
    position_error = (
        hypot(
            x_start + int(peak_x) - centre_x,
            y_start + int(peak_y) - centre_y,
        )
        / beam.major_fwhm_pixels
    )

    y_grid, x_grid = np.indices(response.shape)
    distance = np.hypot(x_grid - centre_x, y_grid - centre_y)
    annulus = (distance >= radius) & (distance <= 2 * radius)
    finite_annulus = annulus & np.isfinite(response)
    negative_lobe = 0.0
    if finite_annulus.any():
        negative_lobe = max(
            0.0,
            -float(np.min(response[finite_annulus])) / expected_flux,
        )
    return position_error, negative_lobe


def evaluate_analytic_cases(
    cases: tuple[AnalyticFilterReviewCase, ...],
    beam: BeamShapePixels,
    review: PhaseFiveFilterReview,
) -> tuple[AnalyticFilterObservation, ...]:
    """Evaluate both candidates without changing any paired case input."""
    scales = tuple(
        zip(review.matrix.scale_orders, (1.0, 2.0, 4.0), strict=True)
    )
    observations: list[AnalyticFilterObservation] = []
    for family in review.candidates:
        bank = build_scale_filter_bank(
            beam,
            family=family,
            scales=scales,
            truncation_sigma=_TRUNCATION_SIGMA,
            noise_correlation=beam,
        )
        response_indices = {
            item.scale_order: index for index, item in enumerate(bank.filters)
        }
        for case in cases:
            prepared = prepare_scale_filter_inputs(
                case.image_jy_per_beam,
                case.valid_pixels,
                case.background_jy_per_beam,
                case.rms_jy_per_beam,
            )
            result = evaluate_scale_filter_bank(
                prepared,
                bank,
                minimum_support_fraction=(
                    review.matrix.support_fraction_bounds[0]
                ),
            )
            response = result.responses[response_indices[case.scale_order]]
            centre_x, centre_y = case.centre_xy
            support = float(
                np.clip(
                    response.valid_support_fraction[centre_y, centre_x],
                    0.0,
                    1.0,
                )
            )
            available = bool(response.scientifically_valid[centre_y, centre_x])
            if not available:
                response_error = None
                response_snr = None
                position_error = None
                negative_lobe = None
            else:
                value = float(
                    response.response_jy_per_beam[centre_y, centre_x]
                )
                effective_rms = float(
                    response.effective_rms_jy_per_beam[centre_y, centre_x]
                )
                response_error = (
                    abs(value - case.expected_integrated_flux_jy)
                    / case.expected_integrated_flux_jy
                )
                response_snr = value / effective_rms
                position_error, negative_lobe = _position_and_negative_lobe(
                    response,
                    centre_xy=case.centre_xy,
                    beam=beam,
                    scale_beams=case.scale_beams,
                    expected_flux=case.expected_integrated_flux_jy,
                )
            observations.append(
                AnalyticFilterObservation(
                    case_identifier=case.identifier,
                    family=family,
                    scale_order=case.scale_order,
                    geometry=case.geometry,
                    input_peak_snr=case.input_peak_snr,
                    support_fraction=support,
                    available=available,
                    response_fractional_error=response_error,
                    integrated_flux_fractional_error=response_error,
                    calibrated_response_snr=response_snr,
                    position_error_beams=position_error,
                    negative_lobe_fraction=negative_lobe,
                )
            )
    return tuple(observations)


def threshold_filter_responses(
    result: ScaleFilterBankResult,
    *,
    detection_sigma: float,
    island_sigma: float,
) -> ThresholdFilterResult:
    """Apply the same minimal threshold and connectivity rule to any family."""
    if detection_sigma <= island_sigma or island_sigma <= 0:
        raise ValueError(
            "thresholds require detection_sigma > island_sigma > 0"
        )
    shape = result.responses[0].response_jy_per_beam.shape
    combined_snr = np.full(shape, -np.inf, dtype=np.float64)
    for response in result.responses:
        scale_snr = np.full(shape, -np.inf, dtype=np.float64)
        np.divide(
            response.response_jy_per_beam,
            response.effective_rms_jy_per_beam,
            out=scale_snr,
            where=response.scientifically_valid,
        )
        np.maximum(combined_snr, scale_snr, out=combined_snr)
    island_support = combined_snr >= island_sigma
    label_result = cast(
        tuple[npt.NDArray[np.int32], int],
        label(
            island_support,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    component_labels = np.asarray(
        label_result[0],
        dtype=np.int32,
    )
    seed_labels = np.unique(component_labels[combined_snr >= detection_sigma])
    seed_labels = seed_labels[seed_labels > 0]
    retained_mask = np.isin(component_labels, seed_labels)
    retained_labels = np.where(retained_mask, component_labels, 0).astype(
        np.int32,
        copy=False,
    )
    return ThresholdFilterResult(
        combined_snr=_read_only(combined_snr),
        retained_mask=_read_only(retained_mask),
        component_labels=_read_only(retained_labels),
        component_count=int(seed_labels.size),
    )


def select_filter_family(
    candidates: tuple[CandidateScientificDecision, ...],
) -> FilterFamily | None:
    """Apply the frozen science-first, cost-second, fail-closed decision."""
    families = tuple(item.family for item in candidates)
    if families != (
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    ):
        raise ValueError(
            "filter decisions must contain both canonical families"
        )
    eligible = tuple(
        item
        for item in candidates
        if item.passes_absolute and item.noninferior_to_other
    )
    if not eligible:
        return None
    return min(eligible, key=lambda item: item.bounded_cost).family


def _rms_plane(recipe: SyntheticRecipe) -> npt.NDArray[np.float64]:
    """Return the exact affine RMS product already supplied by Phase 2."""
    height, width = recipe.shape_yx
    gradient_x, gradient_y = recipe.noise_rms_fractional_gradient_xy
    x_normalized = (
        np.arange(width, dtype=np.float64) / max(width - 1, 1) - 0.5
    )[np.newaxis, :]
    y_normalized = (
        np.arange(height, dtype=np.float64) / max(height - 1, 1) - 0.5
    )[:, np.newaxis]
    return np.asarray(
        recipe.noise_rms
        * (1.0 + gradient_x * x_normalized + gradient_y * y_normalized),
        dtype=np.float64,
    )


def _build_generated_truth(
    dataset: DatasetRecord,
    review: _ReviewContract,
) -> tuple[_GeneratedTruthGroup, ...]:
    """Build noiseless group masks once for every population seed."""
    rms = _rms_plane(dataset.recipe)
    truth_groups: list[_GeneratedTruthGroup] = []
    for group in dataset.multiscale_truth_groups:
        sources = tuple(
            dataset.recipe.sources[index] for index in group.source_indices
        )
        truth_recipe = dataset.recipe.model_copy(
            update={
                "sources": sources,
                "background": 0.0,
                "noise_rms": 0.0,
                "noise_rms_fractional_gradient_xy": (0.0, 0.0),
                "invalid_rectangles": (),
            }
        )
        signal = generate_synthetic_image(truth_recipe)
        peak = float(np.max(signal))
        detection_mask = np.asarray(
            signal >= review.matrix.island_sigma * rms,
            dtype=np.bool_,
        )
        flux_aperture = np.asarray(
            signal >= peak * np.exp(-8.0),
            dtype=np.bool_,
        )
        truth_groups.append(
            _GeneratedTruthGroup(
                identifier=group.identifier,
                morphology=group.morphology,
                catalogue_role=group.catalogue_role,
                scale_orders=group.governed_scale_orders,
                reference_position_xy=group.reference_position_xy,
                reference_integrated_flux=(
                    group.reference_integrated_brightness_jy_pixels_per_beam
                ),
                detection_mask=_read_only(detection_mask),
                flux_aperture=_read_only(flux_aperture),
                signal_jy_per_beam=_read_only(
                    np.asarray(signal, dtype=np.float64)
                ),
            )
        )
    return tuple(truth_groups)


def _noise_std_error(
    result: ScaleFilterBankResult,
    truth_mask: npt.NDArray[np.bool_],
    valid_pixels: npt.NDArray[np.bool_],
    *,
    exclusion_iterations: int,
) -> float:
    """Measure background response-noise calibration away from truth."""
    excluded = np.asarray(
        binary_dilation(truth_mask, iterations=exclusion_iterations),
        dtype=np.bool_,
    )
    background = valid_pixels & ~excluded
    errors: list[float] = []
    for response in result.responses:
        usable = background & response.scientifically_valid
        snr = (
            response.response_jy_per_beam[usable]
            / response.effective_rms_jy_per_beam[usable]
        )
        errors.append(abs(float(np.std(snr, ddof=1)) - 1.0))
    return float(np.median(errors))


def _group_observation(
    truth: _GeneratedTruthGroup,
    thresholded: ThresholdFilterResult,
    result: ScaleFilterBankResult,
    prepared_inputs: PreparedScaleInputs,
    beam: BeamShapePixels,
) -> GeneratedGroupObservation:
    """Measure one governed truth group without candidate-specific rules."""
    residual = prepared_inputs.residual_jy_per_beam
    valid_pixels = prepared_inputs.scientifically_valid
    detection_truth = truth.detection_mask & valid_pixels
    overlapping_labels = np.unique(
        thresholded.component_labels[detection_truth]
    )
    overlapping_labels = overlapping_labels[overlapping_labels > 0]
    detected = bool(overlapping_labels.size)
    maximum_snr = max(
        0.0,
        float(np.max(thresholded.combined_snr[detection_truth])),
    )
    response_indices = {
        response.scale_order: response for response in result.responses
    }
    centre_x = round(truth.reference_position_xy[0])
    centre_y = round(truth.reference_position_xy[1])
    support_available = all(
        response_indices[scale_order].scientifically_valid[centre_y, centre_x]
        for scale_order in truth.scale_orders
    )
    if not detected:
        flux_error = None
        position_error = None
    else:
        aperture = (
            truth.flux_aperture & valid_pixels & thresholded.retained_mask
        )
        measured_flux = float(np.sum(residual[aperture], dtype=np.float64))
        flux_error = abs(measured_flux - truth.reference_integrated_flux) / (
            truth.reference_integrated_flux
        )
        position_support = detection_truth & thresholded.retained_mask
        weights = np.clip(
            thresholded.combined_snr[position_support],
            0.0,
            None,
        )
        y_grid = np.broadcast_to(
            np.arange(residual.shape[0])[:, np.newaxis],
            residual.shape,
        )
        x_grid = np.broadcast_to(
            np.arange(residual.shape[1])[np.newaxis, :],
            residual.shape,
        )
        if float(np.sum(weights)) > 0:
            measured_x = float(
                np.average(x_grid[position_support], weights=weights)
            )
            measured_y = float(
                np.average(y_grid[position_support], weights=weights)
            )
            position_error = (
                hypot(
                    measured_x - truth.reference_position_xy[0],
                    measured_y - truth.reference_position_xy[1],
                )
                / beam.major_fwhm_pixels
            )
        else:
            position_error = None
    return GeneratedGroupObservation(
        group_identifier=truth.identifier,
        morphology=truth.morphology,
        scale_orders=truth.scale_orders,
        detected=detected,
        maximum_snr=maximum_snr,
        integrated_flux_fractional_error=flux_error,
        position_error_beams=position_error,
        support_available=support_available,
        fragment_count=int(overlapping_labels.size),
    )


def _evaluate_generated_with_truth(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    *,
    family: FilterFamily,
    review: PhaseFiveFilterReview,
    truth_groups: tuple[_GeneratedTruthGroup, ...],
) -> GeneratedImageObservation:
    """Evaluate an image against reusable candidate-neutral truth."""
    image = generate_synthetic_image(recipe)
    valid_pixels = np.isfinite(image)
    background = np.full(image.shape, recipe.background, dtype=np.float64)
    rms = _rms_plane(recipe)
    prepared = prepare_scale_filter_inputs(
        image,
        valid_pixels,
        background,
        rms,
    )
    beam = BeamShapePixels(
        dataset.beam.major_fwhm_pixels,
        dataset.beam.minor_fwhm_pixels,
        dataset.beam.position_angle_degrees,
    )
    bank = build_scale_filter_bank(
        beam,
        family=family,
        scales=tuple(
            zip(review.matrix.scale_orders, (1.0, 2.0, 4.0), strict=True)
        ),
        truncation_sigma=_TRUNCATION_SIGMA,
        noise_correlation=beam,
    )
    result = evaluate_scale_filter_bank(
        prepared,
        bank,
        minimum_support_fraction=review.matrix.support_fraction_bounds[0],
    )
    thresholded = threshold_filter_responses(
        result,
        detection_sigma=review.matrix.detection_sigma,
        island_sigma=review.matrix.island_sigma,
    )
    truth_mask = (
        np.logical_or.reduce(
            tuple(group.detection_mask for group in truth_groups)
        )
        & valid_pixels
    )
    group_observations = tuple(
        _group_observation(
            group,
            thresholded,
            result,
            prepared,
            beam,
        )
        for group in truth_groups
    )
    detected_groups = sum(item.detected for item in group_observations)
    completeness = detected_groups / len(group_observations)
    component_labels = np.unique(
        thresholded.component_labels[thresholded.retained_mask]
    )
    true_components = sum(
        bool(np.any(thresholded.component_labels[truth_mask] == component))
        for component in component_labels
    )
    reliability = (
        true_components / thresholded.component_count
        if thresholded.component_count
        else 0.0
    )
    intersection = int(
        np.count_nonzero(thresholded.retained_mask & truth_mask)
    )
    union = int(np.count_nonzero(thresholded.retained_mask | truth_mask))
    mask_iou = intersection / union if union else 1.0
    fragmented = sum(item.fragment_count > 1 for item in group_observations)
    return GeneratedImageObservation(
        dataset_identifier=dataset.identifier,
        seed=recipe.seed,
        family=family,
        groups=group_observations,
        completeness=completeness,
        reliability=reliability,
        mask_intersection_over_union=mask_iou,
        fragmentation_fraction=fragmented / len(group_observations),
        noise_std_fractional_error=_noise_std_error(
            result,
            truth_mask,
            valid_pixels,
            exclusion_iterations=ceil(2 * beam.major_fwhm_pixels),
        ),
        component_count=thresholded.component_count,
    )


def evaluate_generated_image(
    dataset: DatasetRecord,
    *,
    recipe_index: int,
    family: FilterFamily,
    review: PhaseFiveFilterReview,
) -> GeneratedImageObservation:
    """Evaluate one image for focused tests and diagnosis."""
    recipes = iter_dataset_recipes(dataset)
    if not 0 <= recipe_index < len(recipes):
        raise IndexError("generated review recipe_index is out of range")
    return _evaluate_generated_with_truth(
        dataset,
        recipes[recipe_index],
        family=family,
        review=review,
        truth_groups=_build_generated_truth(dataset, review),
    )


def evaluate_generated_population(
    dataset: DatasetRecord,
    review: PhaseFiveFilterReview,
) -> tuple[GeneratedImageObservation, ...]:
    """Evaluate both candidates over one frozen population without retuning."""
    truth_groups = _build_generated_truth(dataset, review)
    return tuple(
        _evaluate_generated_with_truth(
            dataset,
            recipe,
            family=family,
            review=review,
            truth_groups=truth_groups,
        )
        for recipe in iter_dataset_recipes(dataset)
        for family in review.candidates
    )


def _maximum_response_snr(
    shape: tuple[int, int],
    responses: tuple[ScaleFilterResponse, ...],
) -> npt.NDArray[np.float64]:
    """Combine calibrated scale evidence without changing final pixels."""
    combined = np.full(shape, -np.inf, dtype=np.float64)
    for response in responses:
        scale_snr = np.full(shape, -np.inf, dtype=np.float64)
        np.divide(
            response.response_jy_per_beam,
            response.effective_rms_jy_per_beam,
            out=scale_snr,
            where=response.scientifically_valid,
        )
        np.maximum(combined, scale_snr, out=combined)
    return combined


def _corrective_threshold(
    prepared: PreparedScaleInputs,
    matched: ScaleFilterBankResult,
    atrous: ResidualAtrousResult | None,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview,
) -> ThresholdFilterResult:
    """Seed from calibrated evidence and grow only on original residual."""
    shape = prepared.residual_jy_per_beam.shape
    combined_snr = _maximum_response_snr(shape, matched.responses)
    reconstructed_support = np.zeros(shape, dtype=np.bool_)
    if atrous is not None:
        reconstruction = reconstruct_significant_atrous(
            atrous,
            detection_sigma=review.matrix.detection_sigma,
            island_sigma=review.matrix.island_sigma,
        )
        reconstructed_support = reconstruction.support_mask
        atrous_snr = _maximum_response_snr(shape, atrous.responses)
        atrous_snr[~reconstructed_support] = -np.inf
        np.maximum(
            combined_snr,
            atrous_snr,
            out=combined_snr,
        )
    direct_snr = np.full(shape, -np.inf, dtype=np.float64)
    np.divide(
        prepared.residual_jy_per_beam,
        prepared.rms_jy_per_beam,
        out=direct_snr,
        where=prepared.scientifically_valid,
    )
    np.maximum(combined_snr, direct_snr, out=combined_snr)
    original_support = (
        direct_snr >= review.matrix.island_sigma
    ) & prepared.scientifically_valid
    raw_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        label(original_support, structure=np.ones((3, 3), dtype=np.int8)),
    )
    seed_labels = np.unique(
        raw_labels[combined_snr >= review.matrix.detection_sigma]
    )
    seed_labels = seed_labels[seed_labels > 0]
    retained = np.isin(raw_labels, seed_labels)
    minimum_area_beams = (
        review.corrections.minimum_island_area_beams
        if isinstance(review, PhaseFiveCorrectiveRReview)
        else 0.25
    )
    minimum_area = max(
        1,
        ceil(
            minimum_area_beams
            * 1.1331
            * beam.major_fwhm_pixels
            * beam.minor_fwhm_pixels
        ),
    )
    label_count = int(np.max(raw_labels)) + 1
    retained_counts = np.bincount(raw_labels[retained], minlength=label_count)
    accepted = retained_counts >= minimum_area
    if isinstance(review, PhaseFiveCorrectiveRReview):
        direct_maxima = np.full(label_count, -np.inf, dtype=np.float64)
        np.maximum.at(direct_maxima, raw_labels.ravel(), direct_snr.ravel())
        accepted |= (
            direct_maxima >= review.corrections.minimum_direct_seed_sigma
        )
    accepted_raw_labels = np.flatnonzero(accepted)
    accepted_raw_labels = accepted_raw_labels[accepted_raw_labels > 0]
    retained = np.isin(raw_labels, accepted_raw_labels)

    if atrous is not None and retained.any():
        association_distance_beams = (
            review.corrections.association_distance_beams
            if isinstance(review, PhaseFiveCorrectiveRReview)
            else 2.0
        )
        association_support = binary_dilation(
            retained | reconstructed_support,
            iterations=ceil(
                association_distance_beams * beam.major_fwhm_pixels
            ),
        )
        association_labels, _ = cast(
            tuple[npt.NDArray[np.int32], int],
            label(
                association_support,
                structure=np.ones((3, 3), dtype=np.int8),
            ),
        )
        component_labels = np.where(retained, association_labels, 0).astype(
            np.int32, copy=False
        )
    else:
        component_labels = np.where(retained, raw_labels, 0).astype(
            np.int32, copy=False
        )
    component_count = int(np.count_nonzero(np.unique(component_labels) > 0))
    return ThresholdFilterResult(
        combined_snr=_read_only(combined_snr),
        retained_mask=_read_only(np.asarray(retained, dtype=np.bool_)),
        component_labels=_read_only(component_labels),
        component_count=component_count,
    )


def _corrective_results(
    prepared: PreparedScaleInputs,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview,
    *,
    family: FilterFamily,
) -> tuple[
    ScaleFilterBankResult,
    ResidualAtrousResult | None,
    ThresholdFilterResult,
]:
    """Evaluate the common comparator and optional residual transform."""
    scales = tuple(
        zip(review.matrix.scale_orders, (1.0, 2.0, 4.0), strict=True)
    )
    matched = evaluate_scale_filter_bank(
        prepared,
        build_scale_filter_bank(
            beam,
            family="beam-aware-matched-filter",
            scales=scales,
            truncation_sigma=_TRUNCATION_SIGMA,
            noise_correlation=beam,
        ),
        minimum_support_fraction=review.matrix.support_fraction_bounds[0],
    )
    atrous = None
    if family == "residual-b3-atrous":
        atrous = evaluate_residual_atrous(
            prepared,
            build_residual_atrous_plan(beam, noise_correlation=beam),
            minimum_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
        )
    elif family != "beam-aware-matched-filter":
        raise ValueError("unsupported corrective-review family")
    thresholded = _corrective_threshold(
        prepared,
        matched,
        atrous,
        beam,
        review,
    )
    return matched, atrous, thresholded


def _observable_signal_measurement(
    planes: _ObservableMeasurementPlanes,
    overlapping_labels: npt.NDArray[np.int32],
    beam: BeamShapePixels,
) -> tuple[float, float]:
    """Measure flux and centroid errors on original observable pixels."""
    selected = np.isin(planes.component_labels, overlapping_labels)
    measurement_support = (
        np.asarray(
            binary_dilation(
                selected,
                iterations=ceil(4 * beam.major_fwhm_pixels),
            ),
            dtype=np.bool_,
        )
        & planes.valid_pixels
    )
    observable_truth = planes.truth_signal * planes.valid_pixels
    reference_flux = float(np.sum(observable_truth, dtype=np.float64))
    measured_flux = float(
        np.sum(planes.residual[measurement_support], dtype=np.float64)
    )
    flux_error = abs(measured_flux - reference_flux) / reference_flux
    coordinate_grids = np.indices(planes.residual.shape, dtype=np.float64)
    y_grid = np.asarray(coordinate_grids[0], dtype=np.float64)
    x_grid = np.asarray(coordinate_grids[1], dtype=np.float64)
    reference_x = float(
        np.sum(x_grid * observable_truth, dtype=np.float64) / reference_flux
    )
    reference_y = float(
        np.sum(y_grid * observable_truth, dtype=np.float64) / reference_flux
    )
    measurement_weights = np.where(measurement_support, planes.residual, 0.0)
    weight_sum = float(np.sum(measurement_weights, dtype=np.float64))
    if weight_sum <= 0:
        return flux_error, float("inf")
    measured_x = float(
        np.sum(x_grid * measurement_weights, dtype=np.float64) / weight_sum
    )
    measured_y = float(
        np.sum(y_grid * measurement_weights, dtype=np.float64) / weight_sum
    )
    position_error = (
        hypot(measured_x - reference_x, measured_y - reference_y)
        / beam.major_fwhm_pixels
    )
    return flux_error, position_error


def _weighted_coordinate_quantile(
    coordinates: npt.NDArray[np.float64],
    weights: npt.NDArray[np.float64],
    quantile: float,
) -> float:
    """Return a deterministic weighted order statistic."""
    order = np.argsort(coordinates, kind="stable")
    ordered_coordinates = coordinates[order]
    cumulative = np.cumsum(weights[order], dtype=np.float64)
    index = int(np.searchsorted(cumulative, quantile * cumulative[-1]))
    return float(ordered_coordinates[min(index, coordinates.size - 1)])


def _corrective_r_position(
    planes: _ObservableMeasurementPlanes,
    overlapping_labels: npt.NDArray[np.int32],
    review: PhaseFiveCorrectiveRReview,
) -> tuple[float, float]:
    """Estimate a robust centre from original, noise-excess pixels only."""
    selected = np.isin(planes.component_labels, overlapping_labels)
    dilation = review.corrections.astrometry_dilation_pixels
    support = (
        np.asarray(
            binary_dilation(selected, iterations=dilation),
            dtype=np.bool_,
        )
        & planes.valid_pixels
    )
    coordinate_grids = np.indices(planes.residual.shape, dtype=np.float64)
    y_grid = np.asarray(coordinate_grids[0], dtype=np.float64)
    x_grid = np.asarray(coordinate_grids[1], dtype=np.float64)
    excess = np.where(
        support,
        np.maximum(planes.residual - planes.rms, 0.0),
        0.0,
    )
    if float(np.sum(excess, dtype=np.float64)) <= 0:
        excess = np.where(support, np.maximum(planes.residual, 0.0), 0.0)

    raw_labels, raw_count = cast(
        tuple[npt.NDArray[np.int32], int],
        label(selected, structure=np.ones((3, 3), dtype=np.int8)),
    )
    component_centres: list[tuple[float, float]] = []
    component_fluxes: list[float] = []
    for component in range(1, raw_count + 1):
        component_support = (
            np.asarray(
                binary_dilation(
                    raw_labels == component,
                    iterations=dilation,
                ),
                dtype=np.bool_,
            )
            & planes.valid_pixels
        )
        component_weights = np.where(
            component_support,
            np.maximum(planes.residual, 0.0),
            0.0,
        )
        component_flux = float(np.sum(component_weights, dtype=np.float64))
        if component_flux <= 0:
            continue
        component_centres.append(
            (
                float(
                    np.sum(x_grid * component_weights, dtype=np.float64)
                    / component_flux
                ),
                float(
                    np.sum(y_grid * component_weights, dtype=np.float64)
                    / component_flux
                ),
            )
        )
        component_fluxes.append(component_flux)

    if component_fluxes:
        fluxes = np.asarray(component_fluxes, dtype=np.float64)
        main = fluxes >= (
            review.corrections.component_flux_fraction * float(np.max(fluxes))
        )
        if int(np.count_nonzero(main)) >= _MINIMUM_TOPOLOGY_COMPONENTS:
            centres = np.asarray(component_centres, dtype=np.float64)[main]
            return float(np.mean(centres[:, 0])), float(np.mean(centres[:, 1]))

    supported = excess > 0
    coordinates_x = x_grid[supported]
    coordinates_y = y_grid[supported]
    weights = excess[supported]
    if weights.size == 0 or float(np.sum(weights, dtype=np.float64)) <= 0:
        return float("nan"), float("nan")
    lower = 0.1
    return (
        0.5
        * (
            _weighted_coordinate_quantile(coordinates_x, weights, lower)
            + _weighted_coordinate_quantile(
                coordinates_x, weights, 1.0 - lower
            )
        ),
        0.5
        * (
            _weighted_coordinate_quantile(coordinates_y, weights, lower)
            + _weighted_coordinate_quantile(
                coordinates_y, weights, 1.0 - lower
            )
        ),
    )


def _corrective_r_signal_measurement(
    planes: _ObservableMeasurementPlanes,
    overlapping_labels: npt.NDArray[np.int32],
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveRReview,
) -> tuple[float, float, tuple[float, float]]:
    """Measure unchanged flux and corrected astrometry on original pixels."""
    flux_error, _ = _observable_signal_measurement(
        planes, overlapping_labels, beam
    )
    selected = np.isin(planes.component_labels, overlapping_labels)
    raw_labels, raw_count = cast(
        tuple[npt.NDArray[np.int32], int],
        label(selected, structure=np.ones((3, 3), dtype=np.int8)),
    )
    component_fluxes = np.zeros(raw_count + 1, dtype=np.float64)
    dilation = review.corrections.astrometry_dilation_pixels
    for component in range(1, raw_count + 1):
        component_support = (
            np.asarray(
                binary_dilation(
                    raw_labels == component,
                    iterations=dilation,
                ),
                dtype=np.bool_,
            )
            & planes.valid_pixels
        )
        component_fluxes[component] = float(
            np.sum(
                np.where(
                    component_support,
                    np.maximum(planes.residual, 0.0),
                    0.0,
                ),
                dtype=np.float64,
            )
        )
    maximum_component_flux = float(np.max(component_fluxes, initial=0.0))
    if maximum_component_flux > 0:
        main_components = np.flatnonzero(
            component_fluxes
            >= review.corrections.component_flux_fraction
            * maximum_component_flux
        )
        main_components = main_components[main_components > 0]
        measurement_labels = np.where(
            np.isin(raw_labels, main_components), 1, 0
        ).astype(np.int32, copy=False)
        planes = _ObservableMeasurementPlanes(
            residual=planes.residual,
            rms=planes.rms,
            valid_pixels=planes.valid_pixels,
            truth_signal=planes.truth_signal,
            component_labels=measurement_labels,
        )
        overlapping_labels = np.asarray([1], dtype=np.int32)

    _, original_position_error = _observable_signal_measurement(
        planes, overlapping_labels, beam
    )
    observable_truth = planes.truth_signal * planes.valid_pixels
    reference_flux = float(np.sum(observable_truth, dtype=np.float64))
    y_grid, x_grid = np.indices(planes.residual.shape, dtype=np.float64)
    reference_x = float(
        np.sum(x_grid * observable_truth, dtype=np.float64) / reference_flux
    )
    reference_y = float(
        np.sum(y_grid * observable_truth, dtype=np.float64) / reference_flux
    )
    selected = np.isin(planes.component_labels, overlapping_labels)
    expanded = np.asarray(
        binary_dilation(
            selected,
            iterations=ceil(4 * beam.major_fwhm_pixels),
        ),
        dtype=np.bool_,
    )
    touches_edge = bool(
        np.any(selected[0, :])
        or np.any(selected[-1, :])
        or np.any(selected[:, 0])
        or np.any(selected[:, -1])
        or np.any(expanded[0, :])
        or np.any(expanded[-1, :])
        or np.any(expanded[:, 0])
        or np.any(expanded[:, -1])
    )
    truncated = touches_edge or bool(np.any(expanded & ~planes.valid_pixels))
    direct_snr = np.full(planes.residual.shape, -np.inf, dtype=np.float64)
    np.divide(
        planes.residual,
        planes.rms,
        out=direct_snr,
        where=planes.valid_pixels,
    )
    noiseless = bool(
        np.all(
            planes.residual[planes.valid_pixels]
            >= -64.0
            * np.finfo(np.float64).eps
            * planes.rms[planes.valid_pixels]
        )
    )
    low_snr_truncation = truncated and (
        noiseless
        or float(np.max(direct_snr[selected], initial=-np.inf))
        < review.matrix.detection_sigma + review.matrix.island_sigma
    )
    use_aperture_moment = low_snr_truncation and np.isfinite(
        original_position_error
    )
    if use_aperture_moment:
        measurement_support = expanded & planes.valid_pixels
        measurement_weights = np.where(
            measurement_support, planes.residual, 0.0
        )
        weight_sum = float(np.sum(measurement_weights, dtype=np.float64))
        measured_x = float(
            np.sum(x_grid * measurement_weights, dtype=np.float64) / weight_sum
        )
        measured_y = float(
            np.sum(y_grid * measurement_weights, dtype=np.float64) / weight_sum
        )
    else:
        measured_x, measured_y = _corrective_r_position(
            planes, overlapping_labels, review
        )
    offset = (
        (measured_x - reference_x) / beam.major_fwhm_pixels,
        (measured_y - reference_y) / beam.major_fwhm_pixels,
    )
    position_error = (
        original_position_error if use_aperture_moment else hypot(*offset)
    )
    return flux_error, position_error, offset


def evaluate_corrective_analytic_cases(
    cases: tuple[AnalyticFilterReviewCase, ...],
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview,
) -> tuple[AnalyticFilterObservation, ...]:
    """Evaluate Step 2C final-output semantics on the unchanged matrix."""
    observations: list[AnalyticFilterObservation] = []
    for family in review.candidates:
        for case in cases:
            prepared = prepare_scale_filter_inputs(
                case.image_jy_per_beam,
                case.valid_pixels,
                case.background_jy_per_beam,
                case.rms_jy_per_beam,
            )
            matched, atrous, thresholded = _corrective_results(
                prepared, beam, review, family=family
            )
            truth_signal = np.where(
                case.valid_pixels,
                case.image_jy_per_beam - case.background_jy_per_beam,
                0.0,
            )
            peak = float(np.max(truth_signal))
            truth_core = truth_signal >= 0.5 * peak
            overlapping_labels = np.unique(
                thresholded.component_labels[truth_core]
            )
            overlapping_labels = overlapping_labels[overlapping_labels > 0]
            available = bool(overlapping_labels.size)
            centre_x, centre_y = case.centre_xy
            support_response = (
                atrous.responses[case.scale_order - 1]
                if atrous is not None
                else matched.responses[case.scale_order - 1]
            )
            support = float(
                np.clip(
                    support_response.valid_support_fraction[
                        centre_y, centre_x
                    ],
                    0.0,
                    1.0,
                )
            )
            if available:
                planes = _ObservableMeasurementPlanes(
                    residual=prepared.residual_jy_per_beam,
                    rms=prepared.rms_jy_per_beam,
                    valid_pixels=prepared.scientifically_valid,
                    truth_signal=truth_signal,
                    component_labels=thresholded.component_labels,
                )
                if isinstance(review, PhaseFiveCorrectiveRReview):
                    flux_error, position_error, _ = (
                        _corrective_r_signal_measurement(
                            planes, overlapping_labels, beam, review
                        )
                    )
                else:
                    flux_error, position_error = (
                        _observable_signal_measurement(
                            planes, overlapping_labels, beam
                        )
                    )
                response_snr = float(
                    np.max(thresholded.combined_snr[truth_core])
                )
            else:
                flux_error = None
                position_error = None
                response_snr = None
            observations.append(
                AnalyticFilterObservation(
                    case_identifier=case.identifier,
                    family=family,
                    scale_order=case.scale_order,
                    geometry=case.geometry,
                    input_peak_snr=case.input_peak_snr,
                    support_fraction=support,
                    available=available,
                    response_fractional_error=flux_error,
                    integrated_flux_fractional_error=flux_error,
                    calibrated_response_snr=response_snr,
                    position_error_beams=position_error,
                    negative_lobe_fraction=0.0 if available else None,
                )
            )
    return tuple(observations)


def _corrective_group_observation(
    truth: _GeneratedTruthGroup,
    context: _CorrectiveObservationContext,
) -> GeneratedGroupObservation:
    """Measure one generated truth group using only final original pixels."""
    thresholded = context.thresholded
    response_source = context.response_source
    prepared = context.prepared
    beam = context.beam
    review = context.review
    valid_pixels = prepared.scientifically_valid
    detection_truth = truth.detection_mask & valid_pixels
    overlapping_labels = np.unique(
        thresholded.component_labels[detection_truth]
    )
    overlapping_labels = overlapping_labels[overlapping_labels > 0]
    detected = bool(overlapping_labels.size)
    maximum_snr = max(
        0.0, float(np.max(thresholded.combined_snr[detection_truth]))
    )
    centre_x = round(truth.reference_position_xy[0])
    centre_y = round(truth.reference_position_xy[1])
    response_indices = {
        response.scale_order: response
        for response in response_source.responses
    }
    support_available = all(
        response_indices[scale_order].valid_support_fraction[
            centre_y, centre_x
        ]
        >= _MINIMUM_REVIEW_SUPPORT
        for scale_order in truth.scale_orders
    )
    disposition: Literal[
        "measured",
        "known-artifact-control",
        "truncated-observable-domain",
    ] = "measured"
    position_offset: tuple[float, float] | None = None
    if (
        detected
        and isinstance(review, PhaseFiveCorrectiveRReview)
        and truth.catalogue_role == "artifact"
    ):
        flux_error = None
        position_error = None
        disposition = "known-artifact-control"
    elif detected:
        planes = _ObservableMeasurementPlanes(
            residual=prepared.residual_jy_per_beam,
            rms=prepared.rms_jy_per_beam,
            valid_pixels=valid_pixels,
            truth_signal=truth.signal_jy_per_beam,
            component_labels=thresholded.component_labels,
        )
        if isinstance(review, PhaseFiveCorrectiveRReview):
            flux_error, position_error, position_offset = (
                _corrective_r_signal_measurement(
                    planes, overlapping_labels, beam, review
                )
            )
            selected = np.isin(
                thresholded.component_labels, overlapping_labels
            )
            dilation = review.corrections.astrometry_dilation_pixels
            expanded = np.asarray(
                binary_dilation(selected, iterations=dilation),
                dtype=np.bool_,
            )
            touches_edge = bool(
                np.any(selected[0, :])
                or np.any(selected[-1, :])
                or np.any(selected[:, 0])
                or np.any(selected[:, -1])
            )
            if touches_edge or np.any(expanded & ~valid_pixels):
                disposition = "truncated-observable-domain"
        else:
            flux_error, position_error = _observable_signal_measurement(
                planes, overlapping_labels, beam
            )
    else:
        flux_error = None
        position_error = None
    return GeneratedGroupObservation(
        group_identifier=truth.identifier,
        morphology=truth.morphology,
        scale_orders=truth.scale_orders,
        detected=detected,
        maximum_snr=maximum_snr,
        integrated_flux_fractional_error=flux_error,
        position_error_beams=position_error,
        support_available=support_available,
        fragment_count=int(overlapping_labels.size),
        measurement_disposition=disposition,
        position_offset_xy_beams=position_offset,
    )


def _evaluate_corrective_generated_with_truth(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    *,
    family: FilterFamily,
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview,
    truth_groups: tuple[_GeneratedTruthGroup, ...],
) -> GeneratedImageObservation:
    """Evaluate one generated image under frozen final-output semantics."""
    image = generate_synthetic_image(recipe)
    valid_pixels = np.isfinite(image)
    prepared = prepare_scale_filter_inputs(
        image,
        valid_pixels,
        np.full(image.shape, recipe.background, dtype=np.float64),
        _rms_plane(recipe),
    )
    beam = BeamShapePixels(
        dataset.beam.major_fwhm_pixels,
        dataset.beam.minor_fwhm_pixels,
        dataset.beam.position_angle_degrees,
    )
    matched, atrous, thresholded = _corrective_results(
        prepared, beam, review, family=family
    )
    response_source: ScaleFilterBankResult | ResidualAtrousResult = (
        atrous if atrous is not None else matched
    )
    truth_mask = (
        np.logical_or.reduce(
            tuple(group.detection_mask for group in truth_groups)
        )
        & valid_pixels
    )
    observation_context = _CorrectiveObservationContext(
        thresholded=thresholded,
        response_source=response_source,
        prepared=prepared,
        beam=beam,
        review=review,
    )
    groups = tuple(
        _corrective_group_observation(
            truth,
            observation_context,
        )
        for truth in truth_groups
    )
    component_labels = np.unique(
        thresholded.component_labels[thresholded.retained_mask]
    )
    component_labels = component_labels[component_labels > 0]
    true_components = sum(
        bool(np.any(thresholded.component_labels[truth_mask] == component))
        for component in component_labels
    )
    reliability = (
        true_components / thresholded.component_count
        if thresholded.component_count
        else 0.0
    )
    intersection = int(
        np.count_nonzero(thresholded.retained_mask & truth_mask)
    )
    union = int(np.count_nonzero(thresholded.retained_mask | truth_mask))
    fragmented = sum(group.fragment_count > 1 for group in groups)
    return GeneratedImageObservation(
        dataset_identifier=dataset.identifier,
        seed=recipe.seed,
        family=family,
        groups=groups,
        completeness=sum(group.detected for group in groups) / len(groups),
        reliability=reliability,
        mask_intersection_over_union=intersection / union if union else 1.0,
        fragmentation_fraction=fragmented / len(groups),
        noise_std_fractional_error=_noise_std_error(
            matched,
            truth_mask,
            valid_pixels,
            exclusion_iterations=ceil(2 * beam.major_fwhm_pixels),
        ),
        component_count=thresholded.component_count,
    )


def evaluate_corrective_generated_image(
    dataset: DatasetRecord,
    *,
    recipe_index: int,
    family: FilterFamily,
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview,
) -> GeneratedImageObservation:
    """Evaluate one corrective-review image for tests and diagnosis."""
    recipes = iter_dataset_recipes(dataset)
    if not 0 <= recipe_index < len(recipes):
        raise IndexError("generated review recipe_index is out of range")
    truth_groups = _build_generated_truth(dataset, review)
    return _evaluate_corrective_generated_with_truth(
        dataset,
        recipes[recipe_index],
        family=family,
        review=review,
        truth_groups=truth_groups,
    )


def evaluate_corrective_generated_population(
    dataset: DatasetRecord,
    review: PhaseFiveCorrectiveReview | PhaseFiveCorrectiveRReview,
) -> tuple[GeneratedImageObservation, ...]:
    """Evaluate both Step 2C candidates over one frozen population."""
    truth_groups = _build_generated_truth(dataset, review)
    return tuple(
        _evaluate_corrective_generated_with_truth(
            dataset,
            recipe,
            family=family,
            review=review,
            truth_groups=truth_groups,
        )
        for recipe in iter_dataset_recipes(dataset)
        for family in review.candidates
    )
