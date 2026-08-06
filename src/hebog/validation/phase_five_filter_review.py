# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Candidate-neutral evaluation utilities for Phase 5 Step 2B."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot, sqrt
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation, label

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    FilterFamily,
    PreparedScaleInputs,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    build_scale_filter_bank,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
)
from hebog.validation.contracts import PhaseFiveFilterReview
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
_ArrayScalar = TypeVar("_ArrayScalar", bound=np.generic)


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
    scale_orders: tuple[int, ...]
    reference_position_xy: tuple[float, float]
    reference_integrated_flux: float
    detection_mask: npt.NDArray[np.bool_]
    flux_aperture: npt.NDArray[np.bool_]


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
    review: PhaseFiveFilterReview,
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
    review: PhaseFiveFilterReview,
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
                scale_orders=group.governed_scale_orders,
                reference_position_xy=group.reference_position_xy,
                reference_integrated_flux=(
                    group.reference_integrated_brightness_jy_pixels_per_beam
                ),
                detection_mask=_read_only(detection_mask),
                flux_aperture=_read_only(flux_aperture),
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
