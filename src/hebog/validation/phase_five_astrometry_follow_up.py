# pyright: reportPrivateUsage=false
"""Development review for irregular detected-segment source positions."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Hashable, Literal, cast

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    SegmentPositionUnavailableReason,
    measure_detected_segment_position,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    prepare_scale_filter_inputs,
)
from hebog.validation.contracts import (
    PhaseFiveAstrometryFollowUpReview,
    PhaseFiveCorrectiveAReview,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    generate_synthetic_image,
    iter_dataset_recipes,
)
from hebog.validation.phase_five_astrometry_review import (
    BootstrapDesign,
    cluster_bootstrap_statistic,
)
from hebog.validation.phase_five_filter_review import (
    _build_generated_truth,
    _corrective_results,
    _rms_plane,
)

ExtendedPositionMetric = Literal[
    "availability",
    "absolute-mean-offset-x",
    "absolute-mean-offset-y",
    "radial-percentile-95",
]


@dataclass(frozen=True, slots=True)
class ExtendedPositionObservation:
    """One detected astronomical truth group's segment-position result."""

    dataset_identifier: str
    seed: int
    group_identifier: str
    morphology: str
    scale_orders: tuple[int, ...]
    available: bool
    centroid_xy: tuple[float, float] | None
    peak_position_xy: tuple[int, int] | None
    reference_position_xy: tuple[float, float]
    offset_xy_beams: tuple[float, float] | None
    radial_error_beams: float | None
    former_target_error_beams: float | None
    unavailable_reason: SegmentPositionUnavailableReason | None
    governed_strata: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtendedPositionEndpoint:
    """One binding availability, bias, or repeatability result."""

    stratum: str
    metric: ExtendedPositionMetric
    image_count: int
    group_count: int
    estimate: float
    confidence_bound: float
    limit: float
    required_relation: Literal["at-least", "at-most"]
    passed: bool


@dataclass(frozen=True, slots=True)
class ExtendedPositionDiagnostic:
    """Non-binding radial summaries retained for interpretation."""

    stratum: str
    available_group_count: int
    radial_median_beams: float
    former_target_percentile_95_beams: float


@dataclass(frozen=True, slots=True)
class AstrometryFollowUpDevelopmentSummary:
    """Complete development-only conclusion for the frozen candidate."""

    image_count: int
    group_count: int
    endpoints: tuple[ExtendedPositionEndpoint, ...]
    diagnostics: tuple[ExtendedPositionDiagnostic, ...]
    eligible_for_human_review: bool
    confirmation_execution_authorized: Literal[False] = False


def _cluster_rows(
    values: npt.NDArray[np.float64],
    image_keys: tuple[Hashable, ...],
) -> tuple[npt.NDArray[np.float64], ...]:
    """Group aligned values by first-seen independent image identity."""
    unique_keys = tuple(dict.fromkeys(image_keys))
    return tuple(
        values[np.asarray([key == item for item in image_keys])]
        for key in unique_keys
    )


def cluster_bootstrap_absolute_mean(
    *,
    values: tuple[float, ...],
    image_keys: tuple[Hashable, ...],
    resamples: int,
    seed: int,
    confidence_level: float,
) -> tuple[float, float]:
    """Return absolute signed bias and its upper image-cluster bound."""
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or len(image_keys) != array.size:
        raise ValueError("bias bootstrap requires aligned non-empty rows")
    if not np.all(np.isfinite(array)):
        raise ValueError("bias bootstrap values must be finite")
    if resamples < 1 or not 0 < confidence_level < 1:
        raise ValueError("bias bootstrap settings must be valid")
    rows = _cluster_rows(array, image_keys)
    random = np.random.default_rng(seed)
    bootstrap = np.empty(resamples, dtype=np.float64)
    counts = {len(row) for row in rows}
    if len(counts) == 1:
        matrix = np.stack(rows)
        for start in range(0, resamples, 1_000):
            stop = min(start + 1_000, resamples)
            indices = random.integers(
                0,
                len(rows),
                size=(stop - start, len(rows)),
            )
            sampled = matrix[indices].reshape(stop - start, -1)
            bootstrap[start:stop] = np.abs(np.mean(sampled, axis=1))
    else:
        for index in range(resamples):
            sampled_indices = random.integers(0, len(rows), size=len(rows))
            sampled_parts: tuple[npt.NDArray[np.float64], ...] = tuple(
                rows[int(item)] for item in sampled_indices
            )
            sampled = np.concatenate(sampled_parts)
            bootstrap[index] = abs(float(np.mean(sampled)))
    return (
        abs(float(np.mean(array))),
        float(np.quantile(bootstrap, confidence_level)),
    )


def _reference_position(
    truth_signal: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
) -> tuple[float, float]:
    """Return the exact noiseless flux centroid on declared truth support."""
    weights = np.where(support, truth_signal, 0.0)
    total = float(np.sum(weights, dtype=np.float64))
    if total <= 0 or not np.isfinite(total):
        raise ValueError("truth position requires positive finite support")
    y_grid, x_grid = np.indices(weights.shape, dtype=np.float64)
    return (
        float(np.sum(x_grid * weights, dtype=np.float64) / total),
        float(np.sum(y_grid * weights, dtype=np.float64) / total),
    )


def _governed_strata(
    dataset: DatasetRecord,
    group_identifier: str,
) -> tuple[str, ...]:
    """Return every frozen group stratum applicable to one source."""
    return tuple(
        stratum.identifier
        for stratum in dataset.multiscale_group_strata
        if group_identifier in stratum.group_identifiers
    )


def evaluate_astrometry_follow_up_image(
    dataset: DatasetRecord,
    *,
    recipe_index: int,
    base_review: PhaseFiveCorrectiveAReview,
) -> tuple[ExtendedPositionObservation, ...]:
    """Measure exact-segment positions on one fresh development image."""
    recipes = iter_dataset_recipes(dataset)
    if not 0 <= recipe_index < len(recipes):
        raise IndexError("astrometry follow-up recipe_index is out of range")
    recipe = recipes[recipe_index]
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
    _, atrous, thresholded = _corrective_results(
        prepared,
        beam,
        base_review,
        family="residual-b3-atrous",
    )
    if atrous is None:
        raise RuntimeError(
            "astrometry follow-up requires residual B3 evidence"
        )
    observations: list[ExtendedPositionObservation] = []
    for truth in _build_generated_truth(dataset, base_review):
        if truth.catalogue_role != "astronomical-source":
            continue
        detection_truth = truth.detection_mask & valid_pixels
        overlapping_labels = np.unique(
            thresholded.component_labels[detection_truth]
        )
        overlapping_labels = overlapping_labels[overlapping_labels > 0]
        if overlapping_labels.size == 0:
            continue
        support = (
            np.isin(thresholded.component_labels, overlapping_labels)
            & valid_pixels
        )
        estimate = measure_detected_segment_position(
            prepared.residual_jy_per_beam,
            support,
        )
        reference_xy = _reference_position(
            truth.signal_jy_per_beam,
            detection_truth,
        )
        former_reference_xy = _reference_position(
            truth.signal_jy_per_beam,
            valid_pixels,
        )
        if estimate.available:
            assert estimate.centroid_xy is not None
            offset_pixels = np.asarray(estimate.centroid_xy) - np.asarray(
                reference_xy
            )
            offset_xy_beams = (
                float(offset_pixels[0] / beam.major_fwhm_pixels),
                float(offset_pixels[1] / beam.major_fwhm_pixels),
            )
            radial_error = hypot(*offset_xy_beams)
            former_offset = (
                np.asarray(estimate.centroid_xy)
                - np.asarray(former_reference_xy)
            ) / beam.major_fwhm_pixels
            former_target_error = hypot(*former_offset)
        else:
            offset_xy_beams = None
            radial_error = None
            former_target_error = None
        observations.append(
            ExtendedPositionObservation(
                dataset_identifier=dataset.identifier,
                seed=recipe.seed,
                group_identifier=truth.identifier,
                morphology=truth.morphology,
                scale_orders=truth.scale_orders,
                available=estimate.available,
                centroid_xy=estimate.centroid_xy,
                peak_position_xy=estimate.peak_position_xy,
                reference_position_xy=reference_xy,
                offset_xy_beams=offset_xy_beams,
                radial_error_beams=radial_error,
                former_target_error_beams=former_target_error,
                unavailable_reason=estimate.unavailable_reason,
                governed_strata=_governed_strata(dataset, truth.identifier),
            )
        )
    return tuple(observations)


def evaluate_astrometry_follow_up_population(
    manifest: DatasetManifest,
    base_review: PhaseFiveCorrectiveAReview,
) -> tuple[ExtendedPositionObservation, ...]:
    """Evaluate the frozen candidate over the complete fresh population."""
    return tuple(
        observation
        for dataset in manifest.datasets
        for recipe_index in range(len(iter_dataset_recipes(dataset)))
        for observation in evaluate_astrometry_follow_up_image(
            dataset,
            recipe_index=recipe_index,
            base_review=base_review,
        )
    )


def _endpoint_strata(
    observations: tuple[ExtendedPositionObservation, ...],
    protocol: PhaseFiveAstrometryFollowUpReview,
) -> tuple[str, ...]:
    """Return every required astronomical stratum or fail closed."""
    required = tuple(
        stratum
        for stratum in protocol.governed_strata
        if stratum != "morphology-artifact"
    )
    observed = {
        stratum
        for observation in observations
        for stratum in observation.governed_strata
    }
    missing = tuple(stratum for stratum in required if stratum not in observed)
    if missing:
        raise ValueError(
            "astrometry follow-up is missing governed strata: "
            + ", ".join(missing)
        )
    return ("overall", *required)


def _in_stratum(
    observation: ExtendedPositionObservation,
    stratum: str,
) -> bool:
    """Return whether one source contributes to a compiled stratum."""
    return stratum == "overall" or stratum in observation.governed_strata


def _availability_endpoint(
    stratum: str,
    rows: tuple[ExtendedPositionObservation, ...],
    required_fraction: float,
) -> ExtendedPositionEndpoint:
    """Compile exact estimator availability for one source stratum."""
    estimate = sum(item.available for item in rows) / len(rows)
    return ExtendedPositionEndpoint(
        stratum=stratum,
        metric="availability",
        image_count=len(
            {(item.dataset_identifier, item.seed) for item in rows}
        ),
        group_count=len(rows),
        estimate=estimate,
        confidence_bound=estimate,
        limit=required_fraction,
        required_relation="at-least",
        passed=estimate >= required_fraction,
    )


def _error_endpoints(
    stratum: str,
    rows: tuple[ExtendedPositionObservation, ...],
    protocol: PhaseFiveAstrometryFollowUpReview,
) -> tuple[ExtendedPositionEndpoint, ...]:
    """Compile signed-axis bias and radial-tail confidence bounds."""
    available = tuple(item for item in rows if item.available)
    if not available:
        return ()
    image_keys = tuple(
        (item.dataset_identifier, item.seed) for item in available
    )
    image_count = len(set(image_keys))
    axis_results: list[ExtendedPositionEndpoint] = []
    axis_specifications: tuple[
        tuple[
            int,
            Literal["absolute-mean-offset-x", "absolute-mean-offset-y"],
        ],
        ...,
    ] = (
        (0, "absolute-mean-offset-x"),
        (1, "absolute-mean-offset-y"),
    )
    for axis, metric in axis_specifications:
        values = tuple(
            item.offset_xy_beams[axis]
            for item in available
            if item.offset_xy_beams is not None
        )
        estimate, upper = cluster_bootstrap_absolute_mean(
            values=values,
            image_keys=image_keys,
            resamples=protocol.endpoint.bootstrap_resamples,
            seed=protocol.endpoint.bootstrap_seed,
            confidence_level=protocol.endpoint.confidence_level,
        )
        limit = protocol.endpoint.maximum_absolute_axis_bias_beams
        axis_results.append(
            ExtendedPositionEndpoint(
                stratum=stratum,
                metric=metric,
                image_count=image_count,
                group_count=len(available),
                estimate=estimate,
                confidence_bound=upper,
                limit=limit,
                required_relation="at-most",
                passed=upper <= limit,
            )
        )
    radial_values = np.asarray(
        [cast(float, item.radial_error_beams) for item in available],
        dtype=np.float64,
    )
    radial_estimate, radial_upper = cluster_bootstrap_statistic(
        radial_values,
        image_keys,
        BootstrapDesign(
            statistic="percentile-95",
            resamples=protocol.endpoint.bootstrap_resamples,
            seed=protocol.endpoint.bootstrap_seed,
            confidence_level=protocol.endpoint.confidence_level,
        ),
    )
    radial_limit = protocol.endpoint.maximum_radial_percentile_95_beams
    return (
        *axis_results,
        ExtendedPositionEndpoint(
            stratum=stratum,
            metric="radial-percentile-95",
            image_count=image_count,
            group_count=len(available),
            estimate=radial_estimate,
            confidence_bound=radial_upper,
            limit=radial_limit,
            required_relation="at-most",
            passed=radial_upper <= radial_limit,
        ),
    )


def _diagnostic(
    stratum: str,
    rows: tuple[ExtendedPositionObservation, ...],
) -> ExtendedPositionDiagnostic | None:
    """Return non-binding old-target and median summaries when available."""
    available = tuple(item for item in rows if item.available)
    if not available:
        return None
    return ExtendedPositionDiagnostic(
        stratum=stratum,
        available_group_count=len(available),
        radial_median_beams=float(
            np.median(
                [cast(float, item.radial_error_beams) for item in available]
            )
        ),
        former_target_percentile_95_beams=float(
            np.percentile(
                [
                    cast(float, item.former_target_error_beams)
                    for item in available
                ],
                95,
            )
        ),
    )


def compile_astrometry_follow_up_development(
    observations: tuple[ExtendedPositionObservation, ...],
    protocol: PhaseFiveAstrometryFollowUpReview,
) -> AstrometryFollowUpDevelopmentSummary:
    """Apply every frozen irregular-position gate without compensation."""
    if not observations:
        raise ValueError("astrometry follow-up observations must not be empty")
    endpoints: list[ExtendedPositionEndpoint] = []
    diagnostics: list[ExtendedPositionDiagnostic] = []
    for stratum in _endpoint_strata(observations, protocol):
        rows = tuple(
            item for item in observations if _in_stratum(item, stratum)
        )
        endpoints.append(
            _availability_endpoint(
                stratum,
                rows,
                protocol.endpoint.availability_fraction,
            )
        )
        endpoints.extend(_error_endpoints(stratum, rows, protocol))
        diagnostic = _diagnostic(stratum, rows)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    image_keys = {
        (item.dataset_identifier, item.seed) for item in observations
    }
    group_keys = {
        (item.dataset_identifier, item.seed, item.group_identifier)
        for item in observations
    }
    return AstrometryFollowUpDevelopmentSummary(
        image_count=len(image_keys),
        group_count=len(group_keys),
        endpoints=tuple(endpoints),
        diagnostics=tuple(diagnostics),
        eligible_for_human_review=bool(endpoints)
        and all(item.passed for item in endpoints),
    )
