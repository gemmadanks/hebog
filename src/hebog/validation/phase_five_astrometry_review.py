# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
"""Prospective Phase 5 extended-source astrometry review utilities."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, hypot
from typing import Hashable, Literal, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import binary_dilation
from scipy.signal import fftconvolve

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    prepare_scale_filter_inputs,
)
from hebog.validation.contracts import (
    PhaseFiveAstrometryRevisionReview,
    PhaseFiveCorrectiveAReview,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    WcsMetadata,
    generate_synthetic_image,
    iter_dataset_recipes,
)
from hebog.validation.phase_five_filter_review import (
    _build_generated_truth,
    _corrective_results,
    _GeneratedTruthGroup,
    _multigaussian_model_position,
    _ObservableMeasurementPlanes,
    _rms_plane,
)

AstrometryCandidate = Literal[
    "direct-observable-pixel-centroid",
    "covariance-gated-model-assisted-centroid",
]
EstimatorDisposition = Literal[
    "direct",
    "model-assisted",
    "model-unavailable-fallback",
    "model-inadequate-fallback",
]
_Statistic = Literal["median", "percentile-95"]
_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
_CORRELATION_TRUNCATION_SIGMA = 6.0
_MODEL_WEIGHT = 1.0
_MODEL_GATE_CHI_SQUARED = 13.815510557964274
_LOW_SNR_UPPER_BOUND = 8.0
_MODERATE_SNR_UPPER_BOUND = 20.0
_POSITION_SUPPORT_DILATION_PIXELS = 2


@dataclass(frozen=True, slots=True)
class PositionEstimate:
    """One position and its complete two-dimensional covariance."""

    position_xy_pixels: tuple[float, float]
    pixel_covariance: tuple[tuple[float, float], tuple[float, float]]
    sky_covariance_degrees: tuple[tuple[float, float], tuple[float, float]]
    sky_jacobian_degrees_per_pixel: tuple[
        tuple[float, float], tuple[float, float]
    ]
    available: bool
    disposition: EstimatorDisposition
    model_available: bool
    model_adequate: bool
    model_normalized_cost: float | None = None


@dataclass(frozen=True, slots=True)
class AstrometryGroupObservation:
    """One eligible truth-group result from one independent noise image."""

    dataset_identifier: str
    seed: int
    candidate: AstrometryCandidate
    group_identifier: str
    morphology: str
    scale_orders: tuple[int, ...]
    maximum_snr: float
    available: bool
    position_xy_pixels: tuple[float, float] | None
    reference_position_xy_pixels: tuple[float, float]
    position_offset_xy_beams: tuple[float, float] | None
    position_error_beams: float | None
    pixel_covariance: tuple[tuple[float, float], tuple[float, float]] | None
    sky_covariance_degrees: (
        tuple[tuple[float, float], tuple[float, float]] | None
    )
    covariance_positive_definite: bool
    mahalanobis_squared: float
    touches_image_edge: bool
    intersects_invalid_pixels: bool
    truncated: bool
    estimator_disposition: EstimatorDisposition
    model_available: bool
    model_adequate: bool
    model_normalized_cost: float | None
    governed_strata: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BootstrapDesign:
    """Cluster-bootstrap settings bound by the successor protocol."""

    statistic: _Statistic
    resamples: int
    seed: int
    confidence_level: float


@dataclass(frozen=True, slots=True)
class _ObservationContext:
    """Shared truth and image metadata for two candidate rows."""

    dataset: DatasetRecord
    seed: int
    truth: _GeneratedTruthGroup
    maximum_snr: float
    reference_xy: tuple[float, float]
    intersects_invalid: bool
    truncated: bool


@dataclass(frozen=True, slots=True)
class AstrometryEndpointResult:
    """One direct catalogue-level position endpoint."""

    candidate: AstrometryCandidate
    stratum: str
    statistic: _Statistic
    image_count: int
    group_count: int
    estimate_beams: float
    upper_confidence_bound_beams: float
    absolute_limit_beams: float
    passed: bool


@dataclass(frozen=True, slots=True)
class AstrometryCoverageResult:
    """One calibrated two-dimensional uncertainty-coverage endpoint."""

    candidate: AstrometryCandidate
    stratum: str
    sample_count: int
    covariance_positive_definite_fraction: float
    level: float
    empirical_coverage: float
    maximum_absolute_error: float
    passed: bool


@dataclass(frozen=True, slots=True)
class AstrometryCandidateResult:
    """Conjunctive development-only conclusion for one estimator."""

    candidate: AstrometryCandidate
    covariance_scale: float
    overall_percentile_95_beams: float
    unavailable_fraction: float
    model_unavailable_fraction: float
    model_inadequate_fraction: float
    endpoints_pass: bool
    coverage_pass: bool
    model_admission_pass: bool
    eligible: bool


@dataclass(frozen=True, slots=True)
class AstrometryDevelopmentSummary:
    """Complete prospective estimator-selection result."""

    image_count: int
    group_count: int
    endpoints: tuple[AstrometryEndpointResult, ...]
    coverage: tuple[AstrometryCoverageResult, ...]
    candidates: tuple[AstrometryCandidateResult, ...]
    selected_candidate: AstrometryCandidate | None
    confirmation_execution_authorized: bool


def _matrix_tuple(
    matrix: npt.NDArray[np.float64],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Convert one finite 2x2 array into an immutable record value."""
    return (
        (float(matrix[0, 0]), float(matrix[0, 1])),
        (float(matrix[1, 0]), float(matrix[1, 1])),
    )


def local_wcs_jacobian(
    wcs: WcsMetadata,
) -> npt.NDArray[np.float64]:
    """Return the local linear pixel-to-sky Jacobian in degrees per pixel."""
    angle = np.deg2rad(wcs.rotation_degrees_counterclockwise)
    rotation = np.asarray(
        (
            (np.cos(angle), -np.sin(angle)),
            (np.sin(angle), np.cos(angle)),
        ),
        dtype=np.float64,
    )
    return rotation @ np.diag(np.asarray(wcs.pixel_scale_degrees_xy))


def _beam_correlation_kernel(
    beam: BeamShapePixels,
) -> npt.NDArray[np.float64]:
    """Sample the full rotated Gaussian beam correlation to numerical zero."""
    major_sigma = beam.major_fwhm_pixels * _FWHM_TO_SIGMA
    minor_sigma = beam.minor_fwhm_pixels * _FWHM_TO_SIGMA
    radius = ceil(_CORRELATION_TRUNCATION_SIGMA * major_sigma)
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    y_grid, x_grid = np.meshgrid(offsets, offsets, indexing="ij")
    angle = np.deg2rad(beam.position_angle_degrees)
    major_offset = np.cos(angle) * x_grid + np.sin(angle) * y_grid
    minor_offset = -np.sin(angle) * x_grid + np.cos(angle) * y_grid
    return np.asarray(
        np.exp(
            -0.5
            * (
                np.square(major_offset / major_sigma)
                + np.square(minor_offset / minor_sigma)
            )
        ),
        dtype=np.float64,
    )


def _centroid_covariance(
    signal: npt.NDArray[np.float64],
    rms: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    position_xy: tuple[float, float],
    beam: BeamShapePixels,
) -> npt.NDArray[np.float64]:
    """Propagate the complete Gaussian-correlated pixel covariance."""
    total = float(np.sum(signal[support], dtype=np.float64))
    if total <= 0 or not np.isfinite(total):
        return np.full((2, 2), np.nan, dtype=np.float64)
    support_y, support_x = np.nonzero(support)
    if support_x.size == 0:
        return np.full((2, 2), np.nan, dtype=np.float64)
    y_start = int(np.min(support_y))
    y_stop = int(np.max(support_y)) + 1
    x_start = int(np.min(support_x))
    x_stop = int(np.max(support_x)) + 1
    local_support = support[y_start:y_stop, x_start:x_stop]
    local_rms = rms[y_start:y_stop, x_start:x_stop]
    y_grid, x_grid = np.indices(local_support.shape, dtype=np.float64)
    x_grid += x_start
    y_grid += y_start
    centre_x, centre_y = position_xy
    derivatives = (
        np.where(local_support, (x_grid - centre_x) / total, 0.0),
        np.where(local_support, (y_grid - centre_y) / total, 0.0),
    )
    noise_gradients = tuple(
        derivative * local_rms for derivative in derivatives
    )
    kernel = _beam_correlation_kernel(beam)
    correlated = tuple(
        fftconvolve(gradient, kernel, mode="same")
        for gradient in noise_gradients
    )
    covariance = np.asarray(
        (
            (
                np.sum(noise_gradients[0] * correlated[0]),
                np.sum(noise_gradients[0] * correlated[1]),
            ),
            (
                np.sum(noise_gradients[1] * correlated[0]),
                np.sum(noise_gradients[1] * correlated[1]),
            ),
        ),
        dtype=np.float64,
    )
    return 0.5 * (covariance + covariance.T)


def direct_observable_pixel_centroid(
    signal: npt.NDArray[np.float64],
    rms: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    beam: BeamShapePixels,
    wcs: WcsMetadata,
) -> PositionEstimate:
    """Measure a signed original-pixel flux centroid and its 2D covariance."""
    if signal.shape != rms.shape or signal.shape != support.shape:
        raise ValueError("centroid signal, RMS, and support must align")
    finite_support = (
        support & np.isfinite(signal) & np.isfinite(rms) & (rms > 0)
    )
    total = float(np.sum(signal[finite_support], dtype=np.float64))
    if total <= 0 or not np.isfinite(total):
        return _unavailable_direct(wcs)
    y_grid, x_grid = np.indices(signal.shape, dtype=np.float64)
    supported_signal = np.where(finite_support, signal, 0.0)
    position_xy = (
        float(np.sum(x_grid * supported_signal, dtype=np.float64) / total),
        float(np.sum(y_grid * supported_signal, dtype=np.float64) / total),
    )
    covariance = _centroid_covariance(
        signal,
        rms,
        finite_support,
        position_xy,
        beam,
    )
    eigenvalues = np.linalg.eigvalsh(covariance)
    available = bool(
        np.all(np.isfinite(position_xy))
        and np.all(np.isfinite(covariance))
        and np.all(eigenvalues > 0)
    )
    jacobian = local_wcs_jacobian(wcs)
    sky_covariance = jacobian @ covariance @ jacobian.T
    return PositionEstimate(
        position_xy_pixels=position_xy,
        pixel_covariance=_matrix_tuple(covariance),
        sky_covariance_degrees=_matrix_tuple(sky_covariance),
        sky_jacobian_degrees_per_pixel=_matrix_tuple(jacobian),
        available=available,
        disposition="direct",
        model_available=False,
        model_adequate=False,
    )


def _unavailable_direct(wcs: WcsMetadata) -> PositionEstimate:
    """Return one explicit unavailable direct estimate."""
    nan_row = (float("nan"), float("nan"))
    nan_matrix = (nan_row, nan_row)
    return PositionEstimate(
        position_xy_pixels=(float("nan"), float("nan")),
        pixel_covariance=nan_matrix,
        sky_covariance_degrees=nan_matrix,
        sky_jacobian_degrees_per_pixel=_matrix_tuple(local_wcs_jacobian(wcs)),
        available=False,
        disposition="direct",
        model_available=False,
        model_adequate=False,
    )


def covariance_gated_model_assistance(
    direct: PositionEstimate,
    model_position_xy_pixels: tuple[float, float] | None,
    *,
    model_normalized_cost: float | None = None,
) -> PositionEstimate:
    """Use the model only inside the direct 99.9% covariance ellipse."""
    if not direct.available:
        return replace(
            direct,
            disposition="model-unavailable-fallback",
        )
    if model_position_xy_pixels is None or not all(
        np.isfinite(model_position_xy_pixels)
    ):
        return replace(
            direct,
            disposition="model-unavailable-fallback",
            model_normalized_cost=model_normalized_cost,
        )
    direct_xy = np.asarray(direct.position_xy_pixels, dtype=np.float64)
    model_xy = np.asarray(model_position_xy_pixels, dtype=np.float64)
    covariance = np.asarray(direct.pixel_covariance, dtype=np.float64)
    difference = model_xy - direct_xy
    mahalanobis = float(difference @ np.linalg.solve(covariance, difference))
    if not np.isfinite(mahalanobis) or mahalanobis > _MODEL_GATE_CHI_SQUARED:
        return replace(
            direct,
            disposition="model-inadequate-fallback",
            model_available=True,
            model_normalized_cost=model_normalized_cost,
        )
    position_xy = direct_xy + _MODEL_WEIGHT * difference
    assisted_covariance = covariance + _MODEL_WEIGHT**2 * np.outer(
        difference, difference
    )
    jacobian = np.asarray(
        direct.sky_jacobian_degrees_per_pixel,
        dtype=np.float64,
    )
    sky_covariance = jacobian @ assisted_covariance @ jacobian.T
    return replace(
        direct,
        position_xy_pixels=(float(position_xy[0]), float(position_xy[1])),
        pixel_covariance=_matrix_tuple(assisted_covariance),
        sky_covariance_degrees=_matrix_tuple(sky_covariance),
        disposition="model-assisted",
        model_available=True,
        model_adequate=True,
        model_normalized_cost=model_normalized_cost,
    )


def cluster_bootstrap_statistic(
    values: npt.NDArray[np.float64],
    image_keys: tuple[Hashable, ...],
    design: BootstrapDesign,
) -> tuple[float, float]:
    """Return a point estimate and upper cluster-bootstrap confidence bound."""
    if values.ndim != 1 or values.size == 0 or len(image_keys) != values.size:
        raise ValueError("cluster bootstrap requires aligned non-empty rows")
    if not np.all(np.isfinite(values)):
        raise ValueError("cluster bootstrap values must be finite")
    summarize = np.median if design.statistic == "median" else _percentile_95
    point = float(summarize(values))
    unique_keys = tuple(dict.fromkeys(image_keys))
    rows = tuple(
        values[np.asarray([key == item for item in image_keys])]
        for key in unique_keys
    )
    random = np.random.default_rng(design.seed)
    bootstrap = np.empty(design.resamples, dtype=np.float64)
    counts = {len(row) for row in rows}
    if len(counts) == 1:
        matrix = np.stack(rows)
        for start in range(0, design.resamples, 1_000):
            stop = min(start + 1_000, design.resamples)
            indices = random.integers(
                0,
                len(rows),
                size=(stop - start, len(rows)),
            )
            sampled = matrix[indices].reshape(stop - start, -1)
            bootstrap[start:stop] = (
                np.median(sampled, axis=1)
                if design.statistic == "median"
                else np.percentile(sampled, 95, axis=1)
            )
    else:
        for index in range(design.resamples):
            sampled_indices = random.integers(0, len(rows), size=len(rows))
            sampled = np.concatenate(
                tuple(rows[item] for item in sampled_indices)
            )
            bootstrap[index] = summarize(sampled)
    return point, float(np.quantile(bootstrap, design.confidence_level))


def _percentile_95(values: npt.NDArray[np.float64]) -> float:
    """Return the governed direct group-level tail statistic."""
    return float(np.percentile(values, 95))


def _reference_position(
    truth_signal: npt.NDArray[np.float64],
    valid_pixels: npt.NDArray[np.bool_],
) -> tuple[float, float]:
    """Measure the exact observable-valid-domain truth centroid."""
    observable = np.where(valid_pixels, truth_signal, 0.0)
    total = float(np.sum(observable, dtype=np.float64))
    y_grid, x_grid = np.indices(observable.shape, dtype=np.float64)
    return (
        float(np.sum(x_grid * observable, dtype=np.float64) / total),
        float(np.sum(y_grid * observable, dtype=np.float64) / total),
    )


def _mahalanobis_squared(
    estimate: PositionEstimate,
    reference_xy: tuple[float, float],
) -> float:
    """Return the two-dimensional normalized position error."""
    if not estimate.available:
        return float("inf")
    difference = np.asarray(estimate.position_xy_pixels) - np.asarray(
        reference_xy
    )
    covariance = np.asarray(estimate.pixel_covariance)
    return float(difference @ np.linalg.solve(covariance, difference))


def _governed_strata(
    dataset: DatasetRecord,
    group_identifier: str,
) -> tuple[str, ...]:
    """Return every frozen dataset stratum containing one truth group."""
    return tuple(
        stratum.identifier
        for stratum in dataset.multiscale_group_strata
        if group_identifier in stratum.group_identifiers
    )


def _observation(
    context: _ObservationContext,
    estimate: PositionEstimate,
    candidate: AstrometryCandidate,
) -> AstrometryGroupObservation:
    """Convert one numerical estimate into a small immutable review row."""
    dataset = context.dataset
    truth = context.truth
    reference_xy = context.reference_xy
    group_identifier = truth.identifier
    morphology = truth.morphology
    scale_orders = truth.scale_orders
    manifest_group = next(
        group
        for group in dataset.multiscale_truth_groups
        if group.identifier == group_identifier
    )
    if estimate.available:
        offset_pixels = np.asarray(estimate.position_xy_pixels) - np.asarray(
            reference_xy
        )
        offset_beams = (
            float(offset_pixels[0] / dataset.beam.major_fwhm_pixels),
            float(offset_pixels[1] / dataset.beam.major_fwhm_pixels),
        )
        position_error = hypot(*offset_beams)
        covariance = np.asarray(estimate.pixel_covariance)
        positive_definite = bool(
            np.all(np.isfinite(covariance))
            and np.linalg.eigvalsh(covariance).min() > 0
        )
        pixel_covariance = estimate.pixel_covariance
        sky_covariance = estimate.sky_covariance_degrees
        position_xy = estimate.position_xy_pixels
    else:
        offset_beams = None
        position_error = None
        positive_definite = False
        pixel_covariance = None
        sky_covariance = None
        position_xy = None
    return AstrometryGroupObservation(
        dataset_identifier=dataset.identifier,
        seed=context.seed,
        candidate=candidate,
        group_identifier=group_identifier,
        morphology=morphology,
        scale_orders=scale_orders,
        maximum_snr=context.maximum_snr,
        available=estimate.available,
        position_xy_pixels=position_xy,
        reference_position_xy_pixels=reference_xy,
        position_offset_xy_beams=offset_beams,
        position_error_beams=position_error,
        pixel_covariance=pixel_covariance,
        sky_covariance_degrees=sky_covariance,
        covariance_positive_definite=positive_definite,
        mahalanobis_squared=_mahalanobis_squared(estimate, reference_xy),
        touches_image_edge=manifest_group.touches_image_edge,
        intersects_invalid_pixels=context.intersects_invalid,
        truncated=context.truncated,
        estimator_disposition=estimate.disposition,
        model_available=estimate.model_available,
        model_adequate=estimate.model_adequate,
        model_normalized_cost=estimate.model_normalized_cost,
        governed_strata=_governed_strata(dataset, group_identifier),
    )


def evaluate_astrometry_revision_image(
    dataset: DatasetRecord,
    *,
    recipe_index: int,
    base_review: PhaseFiveCorrectiveAReview,
) -> tuple[AstrometryGroupObservation, ...]:
    """Compare both successor estimators on one fresh development image."""
    recipes = iter_dataset_recipes(dataset)
    if not 0 <= recipe_index < len(recipes):
        raise IndexError("astrometry revision recipe_index is out of range")
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
        raise RuntimeError("astrometry revision requires residual B3 evidence")
    truth_groups = _build_generated_truth(dataset, base_review)
    observations: list[AstrometryGroupObservation] = []
    for truth in truth_groups:
        if truth.catalogue_role != "astronomical-source":
            continue
        detection_truth = truth.detection_mask & valid_pixels
        overlapping_labels = np.unique(
            thresholded.component_labels[detection_truth]
        )
        overlapping_labels = overlapping_labels[overlapping_labels > 0]
        if overlapping_labels.size == 0:
            continue
        maximum_snr = max(
            0.0,
            float(np.max(thresholded.combined_snr[detection_truth])),
        )
        selected = np.isin(
            thresholded.component_labels,
            overlapping_labels,
        )
        island_boundary = np.asarray(
            binary_dilation(
                selected,
                iterations=_POSITION_SUPPORT_DILATION_PIXELS,
            ),
            dtype=np.bool_,
        )
        support = island_boundary & valid_pixels
        planes = _ObservableMeasurementPlanes(
            residual=prepared.residual_jy_per_beam,
            rms=prepared.rms_jy_per_beam,
            valid_pixels=valid_pixels,
            truth_signal=truth.signal_jy_per_beam,
            component_labels=thresholded.component_labels,
        )
        direct = direct_observable_pixel_centroid(
            planes.residual,
            planes.rms,
            support,
            beam,
            dataset.wcs,
        )
        reference_xy = _reference_position(
            truth.signal_jy_per_beam,
            valid_pixels,
        )
        expanded = np.asarray(
            binary_dilation(
                selected,
                iterations=base_review.corrections.astrometry_dilation_pixels,
            ),
            dtype=np.bool_,
        )
        touches_edge = bool(
            np.any(selected[0, :])
            or np.any(selected[-1, :])
            or np.any(selected[:, 0])
            or np.any(selected[:, -1])
        )
        intersects_invalid = bool(np.any(expanded & ~valid_pixels))
        truncated = touches_edge or intersects_invalid
        model = (
            _multigaussian_model_position(
                planes,
                overlapping_labels,
                beam,
                direct.position_xy_pixels,
                base_review,
            )
            if direct.available
            else None
        )
        assisted = covariance_gated_model_assistance(
            direct,
            (model[0], model[1]) if model is not None else None,
            model_normalized_cost=model[2] if model is not None else None,
        )
        observation_context = _ObservationContext(
            dataset=dataset,
            seed=recipe.seed,
            truth=truth,
            maximum_snr=maximum_snr,
            reference_xy=reference_xy,
            intersects_invalid=intersects_invalid,
            truncated=truncated,
        )
        observations.extend(
            (
                _observation(
                    observation_context,
                    estimate=direct,
                    candidate="direct-observable-pixel-centroid",
                ),
                _observation(
                    observation_context,
                    estimate=assisted,
                    candidate="covariance-gated-model-assisted-centroid",
                ),
            )
        )
    return tuple(observations)


def evaluate_astrometry_revision_population(
    manifest: DatasetManifest,
    base_review: PhaseFiveCorrectiveAReview,
) -> tuple[AstrometryGroupObservation, ...]:
    """Evaluate both estimators over a fresh governed population."""
    return tuple(
        observation
        for dataset in manifest.datasets
        for recipe_index in range(len(iter_dataset_recipes(dataset)))
        for observation in evaluate_astrometry_revision_image(
            dataset,
            recipe_index=recipe_index,
            base_review=base_review,
        )
    )


def _endpoint_strata(
    observations: tuple[AstrometryGroupObservation, ...],
) -> tuple[str, ...]:
    """Return overall and every governed truth-group stratum represented."""
    return (
        "overall",
        *sorted(
            {
                stratum
                for observation in observations
                for stratum in observation.governed_strata
                if not stratum.startswith("morphology-artifact")
            }
        ),
    )


def _in_endpoint_stratum(
    observation: AstrometryGroupObservation,
    stratum: str,
) -> bool:
    """Return whether one group contributes to an endpoint stratum."""
    return stratum == "overall" or stratum in observation.governed_strata


def _signal_to_noise_stratum(maximum_snr: float) -> str:
    """Assign the predeclared low, moderate, or high response-SNR bin."""
    if maximum_snr < _LOW_SNR_UPPER_BOUND:
        return "low"
    if maximum_snr < _MODERATE_SNR_UPPER_BOUND:
        return "moderate"
    return "high"


def _coverage_strata(
    observation: AstrometryGroupObservation,
) -> tuple[str, ...]:
    """Return the approved uncertainty-audit categories for one group."""
    return (
        "overall",
        f"morphology/{observation.morphology}",
        f"signal-to-noise/{_signal_to_noise_stratum(observation.maximum_snr)}",
        "scale/" + "-".join(str(item) for item in observation.scale_orders),
        f"image-edge/{'yes' if observation.touches_image_edge else 'no'}",
        "invalid-pixels/"
        + ("yes" if observation.intersects_invalid_pixels else "no"),
        f"truncation/{'yes' if observation.truncated else 'no'}",
        f"estimator-disposition/{observation.estimator_disposition}",
    )


def _calibration_scale(
    observations: tuple[AstrometryGroupObservation, ...],
) -> float:
    """Calibrate one global covariance scale from repeated-noise injections."""
    values = np.asarray(
        [
            item.mahalanobis_squared
            for item in observations
            if item.available
            and item.covariance_positive_definite
            and np.isfinite(item.mahalanobis_squared)
        ],
        dtype=np.float64,
    )
    if values.size == 0:
        return float("nan")
    chi_squared_two_median = 2.0 * np.log(2.0)
    scale = float(np.median(values) / chi_squared_two_median)
    return scale if scale > 0 and np.isfinite(scale) else float("nan")


def _compile_endpoints(
    candidate: AstrometryCandidate,
    observations: tuple[AstrometryGroupObservation, ...],
    protocol: PhaseFiveAstrometryRevisionReview,
) -> tuple[AstrometryEndpointResult, ...]:
    """Compile direct group-level endpoints with image-cluster resampling."""
    endpoints: list[AstrometryEndpointResult] = []
    candidate_rows = tuple(
        item
        for item in observations
        if item.candidate == candidate and item.available
    )
    specifications: tuple[tuple[_Statistic, float], ...] = (
        (
            "median",
            protocol.endpoint.maximum_median_position_beams,
        ),
        (
            "percentile-95",
            protocol.endpoint.maximum_percentile_95_position_beams,
        ),
    )
    for stratum in _endpoint_strata(candidate_rows):
        rows = tuple(
            item
            for item in candidate_rows
            if _in_endpoint_stratum(item, stratum)
        )
        if not rows:
            continue
        values = np.asarray(
            [item.position_error_beams for item in rows],
            dtype=np.float64,
        )
        image_keys = tuple(
            (item.dataset_identifier, item.seed) for item in rows
        )
        for statistic, limit in specifications:
            estimate, upper = cluster_bootstrap_statistic(
                values,
                image_keys,
                BootstrapDesign(
                    statistic=statistic,
                    resamples=protocol.endpoint.bootstrap_resamples,
                    seed=protocol.endpoint.bootstrap_seed,
                    confidence_level=protocol.endpoint.confidence_level,
                ),
            )
            endpoints.append(
                AstrometryEndpointResult(
                    candidate=candidate,
                    stratum=stratum,
                    statistic=statistic,
                    image_count=len(set(image_keys)),
                    group_count=len(rows),
                    estimate_beams=estimate,
                    upper_confidence_bound_beams=upper,
                    absolute_limit_beams=limit,
                    passed=estimate <= limit,
                )
            )
    return tuple(endpoints)


def _compile_coverage(
    candidate: AstrometryCandidate,
    observations: tuple[AstrometryGroupObservation, ...],
    protocol: PhaseFiveAstrometryRevisionReview,
    covariance_scale: float,
) -> tuple[AstrometryCoverageResult, ...]:
    """Compile 68% and 95% Mahalanobis coverage across every audit stratum."""
    candidate_rows = tuple(
        item for item in observations if item.candidate == candidate
    )
    represented_strata = sorted(
        {
            stratum
            for observation in candidate_rows
            for stratum in _coverage_strata(observation)
        }
    )
    thresholds = {
        level: -2.0 * np.log(1.0 - level)
        for level in protocol.uncertainty.coverage_levels
    }
    results: list[AstrometryCoverageResult] = []
    for stratum in represented_strata:
        rows = tuple(
            item
            for item in candidate_rows
            if stratum in _coverage_strata(item)
        )
        positive_fraction = sum(
            item.covariance_positive_definite for item in rows
        ) / len(rows)
        calibrated = np.asarray(
            [
                item.mahalanobis_squared / covariance_scale
                for item in rows
                if item.available
                and item.covariance_positive_definite
                and np.isfinite(item.mahalanobis_squared)
            ],
            dtype=np.float64,
        )
        for level, tolerance in zip(
            protocol.uncertainty.coverage_levels,
            protocol.uncertainty.maximum_absolute_coverage_error,
            strict=True,
        ):
            empirical = (
                float(np.mean(calibrated <= thresholds[level]))
                if calibrated.size
                else 0.0
            )
            passed = (
                positive_fraction
                >= protocol.uncertainty.require_positive_definite_fraction
                and calibrated.size == len(rows)
                and abs(empirical - level) <= tolerance
            )
            results.append(
                AstrometryCoverageResult(
                    candidate=candidate,
                    stratum=stratum,
                    sample_count=len(rows),
                    covariance_positive_definite_fraction=positive_fraction,
                    level=level,
                    empirical_coverage=empirical,
                    maximum_absolute_error=tolerance,
                    passed=passed,
                )
            )
    return tuple(results)


def select_astrometry_candidate(
    direct: AstrometryCandidateResult,
    model: AstrometryCandidateResult,
    *,
    minimum_model_improvement_beams: float,
) -> AstrometryCandidate | None:
    """Apply the frozen simple-baseline preference without compensation."""
    if not direct.eligible:
        return model.candidate if model.eligible else None
    improvement = (
        direct.overall_percentile_95_beams - model.overall_percentile_95_beams
    )
    if model.eligible and improvement >= minimum_model_improvement_beams:
        return model.candidate
    return direct.candidate


def compile_astrometry_development(
    observations: tuple[AstrometryGroupObservation, ...],
    protocol: PhaseFiveAstrometryRevisionReview,
) -> AstrometryDevelopmentSummary:
    """Calibrate, evaluate, and select on the fresh development role."""
    if not observations:
        raise ValueError(
            "astrometry development observations must not be empty"
        )
    candidates = cast(
        tuple[AstrometryCandidate, AstrometryCandidate],
        protocol.estimator_candidates,
    )
    endpoint_results: list[AstrometryEndpointResult] = []
    coverage_results: list[AstrometryCoverageResult] = []
    conclusions: list[AstrometryCandidateResult] = []
    for candidate in candidates:
        rows = tuple(
            item for item in observations if item.candidate == candidate
        )
        if not rows:
            raise ValueError(f"missing astrometry candidate rows: {candidate}")
        scale = _calibration_scale(rows)
        endpoints = _compile_endpoints(
            candidate,
            observations,
            protocol,
        )
        coverage = _compile_coverage(
            candidate,
            observations,
            protocol,
            scale,
        )
        endpoint_results.extend(endpoints)
        coverage_results.extend(coverage)
        unavailable_fraction = sum(not item.available for item in rows) / len(
            rows
        )
        inadequate_fraction = sum(
            item.estimator_disposition == "model-inadequate-fallback"
            for item in rows
        ) / len(rows)
        model_unavailable_fraction = sum(
            item.estimator_disposition == "model-unavailable-fallback"
            for item in rows
        ) / len(rows)
        model_admission_pass = candidate == candidates[0] or (
            model_unavailable_fraction
            <= protocol.selection.maximum_model_unavailable_fraction
            and inadequate_fraction
            <= protocol.selection.maximum_model_inadequate_fraction
        )
        overall_tail = next(
            item.estimate_beams
            for item in endpoints
            if item.stratum == "overall" and item.statistic == "percentile-95"
        )
        endpoints_pass = bool(endpoints) and all(
            item.passed for item in endpoints
        )
        coverage_pass = (
            bool(coverage)
            and np.isfinite(scale)
            and all(item.passed for item in coverage)
        )
        conclusions.append(
            AstrometryCandidateResult(
                candidate=candidate,
                covariance_scale=scale,
                overall_percentile_95_beams=overall_tail,
                unavailable_fraction=unavailable_fraction,
                model_unavailable_fraction=model_unavailable_fraction,
                model_inadequate_fraction=inadequate_fraction,
                endpoints_pass=endpoints_pass,
                coverage_pass=coverage_pass,
                model_admission_pass=model_admission_pass,
                eligible=(
                    endpoints_pass
                    and coverage_pass
                    and model_admission_pass
                    and unavailable_fraction == 0.0
                ),
            )
        )
    selected = select_astrometry_candidate(
        conclusions[0],
        conclusions[1],
        minimum_model_improvement_beams=(
            protocol.selection.minimum_model_p95_improvement_beams
        ),
    )
    image_keys = {
        (item.dataset_identifier, item.seed) for item in observations
    }
    group_keys = {
        (item.dataset_identifier, item.seed, item.group_identifier)
        for item in observations
    }
    return AstrometryDevelopmentSummary(
        image_count=len(image_keys),
        group_count=len(group_keys),
        endpoints=tuple(endpoint_results),
        coverage=tuple(coverage_results),
        candidates=tuple(conclusions),
        selected_candidate=selected,
        confirmation_execution_authorized=selected is not None,
    )
