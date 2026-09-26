"""Bounded original-pixel Gaussian measurements for detected components."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import pairwise
from math import ceil
from typing import cast

import numpy as np
from astropy.wcs import WCS
from scipy.ndimage import (
    binary_dilation,
    binary_fill_holes,
    find_objects,
    label,
)
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from hebog.algorithms.astrometry import (
    compact_geometry_from_wcs,
)
from hebog.algorithms.deblending import DeblendedRegion
from hebog.algorithms.extended_measurement import (
    expand_source_measurement_labels,
)
from hebog.algorithms.fitting import fit_compact_gaussian_mixture
from hebog.algorithms.measurement import measure_compact_moments
from hebog.algorithms.multiscale import (
    ResidualAtrousPlan,
    ScaleFilterBank,
    ScaleFilterResponse,
    build_scale_filter_bank,
    calibrated_scale_snrs,
    evaluate_residual_atrous,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
    reconstruct_significant_atrous,
)
from hebog.algorithms.multiscale_association import (
    persistent_seeded_scale_support,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    CompactGaussianFitResult,
    FailedCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import RestoringBeam
from hebog.data_models.measurement import CompactMeasurementGeometry
from hebog.data_models.measurement_diagnostics import AssociationEvidenceKind
from hebog.data_models.partitioning import ImageBounds

_MINIMUM_LOOP_COMPONENTS = 3


@dataclass(frozen=True, slots=True)
class _ComponentFitInput:
    """Array views owned by one bounded worker-local fitting operation."""

    island: DetectedIsland
    array_bounds: ImageBounds
    regions: tuple[DeblendedRegion, ...]
    physical_residual: np.ndarray
    rms: np.ndarray
    valid_pixels: np.ndarray
    region_labels: np.ndarray


@dataclass(frozen=True, slots=True)
class ComponentGroupingEvidence:
    """Worker-local merge evidence, linear in the bounded group population."""

    reason: AssociationEvidenceKind
    scale_ids: tuple[int, ...]
    component_labels: frozenset[int]
    protected_labels: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class ComponentMeasurements:
    """Fits retain detection labels; compact groups constrain association."""

    fits: tuple[tuple[int, CompactGaussianFitResult], ...]
    compact_groups: tuple[frozenset[int], ...]
    deferred_parent_count: int
    # The whole-plane oracle measures the support as it goes and returns it;
    # the tiled reconciliation reduces records only, and the cores published
    # the same plane for a later pass to read by window.
    measurement_support: np.ndarray | None = None
    extended_groups: tuple[frozenset[int], ...] = ()
    proposed_compact_groups: tuple[frozenset[int], ...] = ()
    grouping_evidence: tuple[ComponentGroupingEvidence, ...] = ()


def _persistent_measurement_support(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
) -> np.ndarray:
    """Admit measurement-only wings by the existing seeded scale rule.

    These are not new detections or published mask pixels. An already
    detected source may own this support only through connected, persistent
    original-image emission. Fitting residuals never supply positive flux.
    """
    responses = _matched_responses(
        residual, rms, valid, plan, minimum_support_fraction
    )
    return persistent_seeded_scale_support(
        calibrated_scale_snrs(
            responses, minimum_support_fraction=minimum_support_fraction
        ),
        tuple(item.response_jy_per_beam for item in responses),
        valid,
        detection_sigma=detection_sigma,
        island_sigma=island_sigma,
        minimum_pixels=minimum_pixels,
    )


def _bounds(support: np.ndarray, origin_yx: tuple[int, int]) -> ImageBounds:
    """Return the minimal rectangle of one non-empty local support."""
    yy, xx = np.nonzero(support)
    oy, ox = origin_yx
    return ImageBounds(
        int(yy.min()) + oy,
        int(yy.max()) + oy + 1,
        int(xx.min()) + ox,
        int(xx.max()) + ox + 1,
    )


def _region(  # noqa: PLR0913, PLR0917
    labels: np.ndarray,
    index: int,
    residual: np.ndarray,
    rms: np.ndarray,
    origin_yx: tuple[int, int],
    island_id: str,
) -> DeblendedRegion:
    """Summarize exact positive initialization pixels, not photometry."""
    support = labels == index
    yy, xx = np.nonzero(support)
    significance = np.divide(
        residual, rms, out=np.full_like(residual, -np.inf), where=support
    )
    position = np.argmax(significance)
    py, px = np.unravel_index(position, labels.shape)
    return DeblendedRegion(
        region_id=f"component-fit-{index}",
        region_label=index,
        island_id=island_id,
        pixel_count=len(yy),
        bounds=_bounds(support, origin_yx),
        peak_signal_to_noise=float(residual[py, px] / rms[py, px]),
        peak_position_yx=(int(py) + origin_yx[0], int(px) + origin_yx[1]),
        first_pixel_yx=(int(yy[0]) + origin_yx[0], int(xx[0]) + origin_yx[1]),
    )


def _model_and_groups(
    fits: tuple[tuple[int, ValidCompactGaussianFit], ...],
    bounds: ImageBounds,
) -> tuple[np.ndarray, tuple[frozenset[int], ...]]:
    """Group fitted ellipses only where their directional FWHMs touch.

    This uses the existing half-sum directional-size association criterion.
    The caller separately requires the complete model to explain the parent.
    A shared threshold island or wavelet parent cannot substitute for it.
    """
    yy, xx = np.mgrid[
        bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
    ]
    model = np.zeros(bounds.shape_yx, dtype=np.float64)
    covariances: list[np.ndarray] = []
    centers: list[np.ndarray] = []
    for _, fitted in fits:
        p = fitted.parameters
        angle = np.deg2rad(p.major_axis_angle_degrees)
        major = np.array((np.cos(angle), np.sin(angle)))
        minor = np.array((-np.sin(angle), np.cos(angle)))
        covariance = p.major_sigma_pixels**2 * np.outer(
            major, major
        ) + p.minor_sigma_pixels**2 * np.outer(minor, minor)
        center = np.asarray(p.centroid_xy)
        dx, dy = xx - center[0], yy - center[1]
        model += p.amplitude_jy_per_beam * np.exp(
            -0.5
            * (
                (major[0] * dx + major[1] * dy) ** 2 / p.major_sigma_pixels**2
                + (minor[0] * dx + minor[1] * dy) ** 2
                / p.minor_sigma_pixels**2
            )
        )
        covariances.append(covariance)
        centers.append(center)
    groups = [{index} for index, _ in fits]
    for i in range(len(fits)):
        for j in range(i):
            delta = centers[i] - centers[j]
            distance = float(np.linalg.norm(delta))
            if distance == 0.0:
                close = True
            else:
                unit = delta / distance
                radius = np.sqrt(2.0 * np.log(2.0)) * (
                    np.sqrt(unit @ covariances[i] @ unit)
                    + np.sqrt(unit @ covariances[j] @ unit)
                )
                close = distance <= radius
            if close:
                first = next(group for group in groups if fits[i][0] in group)
                second = next(group for group in groups if fits[j][0] in group)
                if first is not second:
                    first.update(second)
                    groups.remove(second)
    return model, tuple(frozenset(group) for group in groups)


def _owned_residual_feature(
    significance: np.ndarray,
    support: np.ndarray,
    attribution: np.ndarray,
    minimum_pixels: int,
) -> bool:
    """Attribute a coherent residual to its peak's nearest detected parent.

    A filter halo may read a neighbour's extended emission. Its residual
    cannot invalidate a compact model just because the read windows overlap.
    This changes model attribution, never source detection or published masks.
    """
    labels, _ = cast(tuple[np.ndarray, int], label(support, np.ones((3, 3))))
    for index, slices in enumerate(find_objects(labels), start=1):
        assert slices is not None
        member = labels[slices] == index
        if np.count_nonzero(member) < minimum_pixels:
            continue
        position = np.argmax(
            np.where(member, np.abs(significance[slices]), -np.inf)
        )
        if attribution[slices].ravel()[position]:
            return True
    return False


def _invalid_free_fallback(fit: ValidCompactGaussianFit) -> bool:
    """An invalid ellipse is not evidence that its owner is unresolved."""
    return (
        fit.diagnostics.model_identity == "beam-constrained"
        and fit.diagnostics.fallback_reason
        in {
            "free-model-bound-contact",
            "free-model-ill-conditioned",
            "free-model-non-convergence",
            "free-model-invalid-result",
        }
    )


def _admit_fallbacks(  # noqa: PLR0913, PLR0917
    fits: tuple[tuple[int, ValidCompactGaussianFit], ...],
    compact: _ComponentFitInput,
    fit_config: CompactGaussianFitConfig,
    plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
) -> tuple[tuple[int, CompactGaussianFitResult], ...]:
    """Reject inadequate beam fallbacks on their actual likelihood support.

    A component need not explain extended emission outside its fitting
    domain. Neighbours retain the original joint parameters/covariance;
    neither refit them independently nor splice in a competing solution.
    """
    if not any(_invalid_free_fallback(fit) for _, fit in fits):
        return fits
    model, _ = _model_and_groups(fits, compact.array_bounds)
    valid = compact.valid_pixels
    if fit_config.pixel_support == "owned-region":
        valid = valid & (compact.region_labels > 0)
    nearest = expand_source_measurement_labels(
        compact.region_labels,
        compact.valid_pixels,
        radius_pixels=ceil(float(np.hypot(*model.shape))),
    )
    output: list[tuple[int, CompactGaussianFitResult]] = []
    for index, fit in fits:
        if _invalid_free_fallback(fit) and _unmodelled_detection(
            compact.physical_residual - model,
            compact.rms,
            valid,
            detection_sigma,
            island_sigma,
            minimum_pixels,
            plan,
            minimum_support_fraction,
            nearest == index,
        ):
            output.append(
                (
                    index,
                    FailedCompactGaussianFit(
                        moment=fit.moment,
                        reason="fit-model-inadequate",
                        diagnostics=fit.diagnostics,
                        quality_flags=(
                            "fit-model-inadequate",
                            "joint-gaussian-fit",
                        ),
                    ),
                )
            )
        else:
            output.append((index, fit))
    return tuple(output)


def _unmodelled_detection(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    atrous_plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
    attribution: np.ndarray,
) -> bool:
    """Apply existing direct and multiscale admission to model residuals."""
    normalized = np.divide(
        residual, rms, out=np.zeros_like(residual), where=valid
    )
    labels, count = cast(
        tuple[np.ndarray, int],
        label(valid & (normalized >= island_sigma), np.ones((3, 3))),
    )
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    seeded = np.unique(labels[valid & (normalized >= detection_sigma)])
    accepted = np.zeros(count + 1, dtype=np.bool_)
    accepted[seeded] = sizes[seeded] >= minimum_pixels
    accepted[0] = False
    if _owned_residual_feature(
        normalized, accepted[labels], attribution, minimum_pixels
    ):
        return True
    prepared = prepare_scale_filter_inputs(
        residual, valid, np.zeros_like(residual), rms
    )
    atrous = evaluate_residual_atrous(
        prepared,
        atrous_plan,
        minimum_support_fraction=minimum_support_fraction,
    )
    reconstruction = reconstruct_significant_atrous(
        atrous,
        detection_sigma=detection_sigma,
        island_sigma=island_sigma,
        minimum_support_fraction=minimum_support_fraction,
    )
    if _owned_residual_feature(
        normalized, reconstruction.support_mask, attribution, minimum_pixels
    ):
        return True
    # This is adequacy of an already detected parent's model, not discovery
    # of a new source. Coherent residual emission at the existing island
    # level need not contain a second detection-threshold seed.
    snrs = _matched_snrs(
        residual, rms, valid, atrous_plan, minimum_support_fraction
    )
    for snr in snrs:
        coherent = valid & (np.abs(snr) >= island_sigma) & np.isfinite(snr)
        if _owned_residual_feature(snr, coherent, attribution, minimum_pixels):
            return True
    return False


def _matched_snrs(
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
) -> tuple[np.ndarray, ...]:
    """Use the existing beam-aware filter bank and correlated-noise model."""
    return calibrated_scale_snrs(
        _matched_responses(
            residual, rms, valid, plan, minimum_support_fraction
        ),
        minimum_support_fraction=minimum_support_fraction,
    )


def _matched_responses(
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
) -> tuple[ScaleFilterResponse, ...]:
    """Retain physical responses with the noise that calibrates their SNR."""
    prepared = prepare_scale_filter_inputs(
        residual, valid, np.zeros_like(residual), rms
    )
    bank = _adequacy_filter_bank(plan)
    result = evaluate_scale_filter_bank(
        prepared, bank, minimum_support_fraction=minimum_support_fraction
    )
    return result.responses


def _adequacy_filter_bank(plan: ResidualAtrousPlan) -> ScaleFilterBank:
    """Use one filter definition for both read halos and adequacy checks."""
    return build_scale_filter_bank(
        plan.beam,
        family="beam-aware-matched-filter",
        scales=((1, 1.0), (2, 2.0), (3, 4.0)),
        truncation_sigma=4.0,
        noise_correlation=plan.noise_correlation,
    )


def _tangential_shape_evidence(
    fits: tuple[tuple[int, ValidCompactGaussianFit], ...],
    center_xy: tuple[float, float],
    beam_covariance: np.ndarray,
    significance: float,
) -> bool:
    """Require coherent resolved arc shapes, not a polygon of point peaks.

    Subtract the known beam quadrupole. Propagate each fitted shape covariance
    into tangential-minus-radial variance. Summing standard errors, rather
    than variances, conservatively bounds unknown between-component
    correlations. This morphology diagnostic does not qualify a source.
    """
    excess = 0.0
    error_bound = 0.0
    for _, fit in fits:
        covariance = (
            fit.uncertainty.shape_parameter_covariance
            if fit.uncertainty is not None
            else None
        )
        if covariance is None:
            return False
        p = fit.parameters
        offset = np.asarray(p.centroid_xy) - center_xy
        radius = float(np.linalg.norm(offset))
        if radius == 0.0:
            return False
        radial = offset / radius
        tangent = np.array((-radial[1], radial[0]))
        angle = np.deg2rad(p.major_axis_angle_degrees) - np.arctan2(
            tangent[1], tangent[0]
        )
        cosine, sine = np.cos(2 * angle), np.sin(2 * angle)
        difference = p.major_sigma_pixels**2 - p.minor_sigma_pixels**2
        excess += float(
            difference * cosine
            - (
                tangent @ beam_covariance @ tangent
                - radial @ beam_covariance @ radial
            )
        )
        gradient = np.array(
            (
                2 * p.major_sigma_pixels * cosine,
                -2 * p.minor_sigma_pixels * cosine,
                -2 * difference * sine,
            )
        )
        a, b, c, d, e, f = covariance
        matrix = np.array(((a, b, c), (b, d, e), (c, e, f)))
        variance = float(gradient @ matrix @ gradient)
        if not np.isfinite(variance) or variance < 0.0:
            return False
        error_bound += np.sqrt(variance)
    return excess > significance * error_bound


def _resolved_emission_loop(  # noqa: PLR0913
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    plan: ResidualAtrousPlan,
    *,
    fits: tuple[tuple[int, ValidCompactGaussianFit], ...],
    bounds: ImageBounds,
    beam_covariance: np.ndarray,
    island_sigma: float,
    minimum_support_fraction: float,
    evidence: list[ComponentGroupingEvidence] | None = None,
) -> tuple[frozenset[int], ...]:
    """Retain a resolved emission loop with measured tangential structure.

    A graph cycle between influence envelopes is not an image-space loop.
    Compact objects arranged in a polygon can produce a loop by smoothing
    alone. Require additional resolved, covariant tangential-shape evidence.
    Invalid interiors cannot provide loop evidence. One beam area is the
    minimum resolved interior, not a catalogue acceptance threshold.
    """
    snrs = _matched_snrs(residual, rms, valid, plan, minimum_support_fraction)
    beam_area = (
        np.pi
        * plan.beam.major_fwhm_pixels
        * plan.beam.minor_fwhm_pixels
        / (4 * np.log(2))
    )
    groups: list[set[int]] = []
    for scale_id, snr in enumerate(snrs, 1):
        support = valid & (snr >= island_sigma)
        filled = np.asarray(binary_fill_holes(support), dtype=np.bool_)
        loops, _ = cast(tuple[np.ndarray, int], label(filled, np.ones((3, 3))))
        component_loops: dict[int, int] = {}
        for index, fit in fits:
            x, y = np.rint(fit.parameters.centroid_xy).astype(int)
            x, y = x - bounds.x_start, y - bounds.y_start
            if 0 <= y < loops.shape[0] and 0 <= x < loops.shape[1]:
                component_loops[index] = int(loops[y, x])
        holes = filled & ~support
        hole_labels, _ = cast(tuple[np.ndarray, int], label(holes))
        invalid_holes = np.unique(hole_labels[~valid])
        holes &= ~np.isin(hole_labels, invalid_holes)
        identities, counts = np.unique(hole_labels[holes], return_counts=True)
        for identity in identities[counts >= beam_area]:
            yy, xx = np.nonzero(hole_labels == identity)
            loop_id = int(loops[yy[0], xx[0]])
            center = (
                float(xx.mean()) + bounds.x_start,
                float(yy.mean()) + bounds.y_start,
            )
            selected = {
                index
                for index, fit in fits
                if component_loops.get(index) == loop_id
                and _tangential_shape_evidence(
                    ((index, fit),), center, beam_covariance, island_sigma
                )
            }
            if len(selected) < _MINIMUM_LOOP_COMPONENTS:
                continue
            if evidence is not None:
                evidence.append(
                    ComponentGroupingEvidence(
                        "resolved-loop", (scale_id,), frozenset(selected)
                    )
                )
            # Scale copies of the same arcs are evidence for one source,
            # not repeated or overlapping membership constraints.
            for previous in groups[:]:
                if previous & selected:
                    selected.update(previous)
                    groups.remove(previous)
            groups.append(selected)
    return tuple(frozenset(group) for group in groups)


def _resolved_open_arc_groups(  # noqa: PLR0913, PLR0917
    beam_scale_significance: np.ndarray,
    valid: np.ndarray,
    fits: tuple[tuple[int, ValidCompactGaussianFit], ...],
    bounds: ImageBounds,
    beam_covariance: np.ndarray,
    island_sigma: float,
    *,
    evidence: list[ComponentGroupingEvidence] | None = None,
) -> tuple[frozenset[int], ...]:
    """Test curved resolved shapes on beam-scale connected emission.

    An open arc need not enclose a hole. A bounded least-squares circle
    provides only a proposed curvature centre; the existing per-component
    covariant tangential test must still pass. Require the finest calibrated
    beam response at island significance connecting the fitted centres, not
    a coarse multiscale influence bridge.
    Point-like neighbours, collinear centres and unavailable shape errors
    supply no evidence for this association.
    """
    support, _ = cast(
        tuple[np.ndarray, int],
        label(
            valid & (beam_scale_significance >= island_sigma),
            np.ones((3, 3)),
        ),
    )
    by_feature: dict[int, list[tuple[int, ValidCompactGaussianFit]]] = {}
    for index, fit in fits:
        if (
            fit.uncertainty is None
            or fit.uncertainty.shape_parameter_covariance is None
        ):
            continue
        x, y = np.rint(fit.parameters.centroid_xy).astype(int) - (
            bounds.x_start,
            bounds.y_start,
        )
        if (
            0 <= y < support.shape[0]
            and 0 <= x < support.shape[1]
            and support[y, x] > 0
        ):
            by_feature.setdefault(int(support[y, x]), []).append((index, fit))
    groups = []
    for members in by_feature.values():
        if len(members) < _MINIMUM_LOOP_COMPONENTS:
            continue
        positions = np.array(
            [fit.parameters.centroid_xy for _, fit in members]
        )
        origin = positions.mean(axis=0)
        offsets = positions - origin
        design = np.column_stack((2 * offsets, np.ones(len(members))))
        solution, _, rank, _ = np.linalg.lstsq(
            design, np.sum(offsets**2, axis=1), rcond=None
        )
        if rank < design.shape[1]:
            continue
        center = tuple(float(value) for value in (origin + solution[:2]))
        selected = frozenset(
            index
            for index, fit in members
            if _tangential_shape_evidence(
                ((index, fit),),
                (center[0], center[1]),
                beam_covariance,
                island_sigma,
            )
        )
        if len(selected) >= _MINIMUM_LOOP_COMPONENTS:
            groups.append(selected)
            if evidence is not None:
                evidence.append(
                    ComponentGroupingEvidence(
                        "resolved-open-arc", (1,), selected
                    )
                )
    return tuple(groups)


def _measurement_island(
    regions: tuple[DeblendedRegion, ...],
    seeds: np.ndarray,
    bounds: ImageBounds,
    parent_index: int,
    image_shape: tuple[int, int],
) -> DetectedIsland:
    """Canonical original-image parent summary, independent of label rank."""
    peak = min(
        regions,
        key=lambda region: (
            -region.peak_signal_to_noise,
            region.peak_position_yx,
        ),
    )
    seed_bounds = _bounds(seeds > 0, (bounds.y_start, bounds.x_start))
    return DetectedIsland(
        f"measurement-parent-{parent_index}",
        parent_index,
        int(np.count_nonzero(seeds)),
        bounds,
        peak.peak_signal_to_noise,
        peak.peak_position_yx,
        min(region.first_pixel_yx for region in regions),
        seed_bounds.y_start == 0
        or seed_bounds.x_start == 0
        or seed_bounds.y_stop == image_shape[0]
        or seed_bounds.x_stop == image_shape[1],
    )


@dataclass(frozen=True, slots=True)
class SupportFeatureGroups:
    """Extended groups and evidence one support feature contributed."""

    extended_groups: tuple[frozenset[int], ...] = ()
    evidence: tuple[ComponentGroupingEvidence, ...] = ()


def support_feature_margin_pixels(atrous_plan: ResidualAtrousPlan) -> int:
    """Return the context one support feature reads beyond its own bounds."""
    return _adequacy_filter_bank(atrous_plan).maximum_halo_pixels


def compact_window_is_admitted(
    window: ImageBounds,
    *,
    maximum_bounds_pixels: int,
) -> bool:
    """Return whether the reviewed compact bound admits one window.

    A fit parent or support feature whose window the bound refuses is
    ADR-008 T3 work: the parent is deferred rather than fitted on truncated
    pixels, and the feature is left ungrouped, so neither window is read.
    """
    return int(np.prod(window.shape_yx)) <= maximum_bounds_pixels


def support_feature_window(
    feature_bounds: ImageBounds,
    *,
    margin: int,
    image_shape_yx: tuple[int, int],
    maximum_bounds_pixels: int,
) -> ImageBounds | None:
    """Return one feature's grouping window, or absence when unbounded.

    A feature wider than the reviewed compact bound is ADR-008 T3 work and
    contributes no grouping, exactly as the whole-plane pass leaves it.
    """
    bounds = ImageBounds(
        max(0, feature_bounds.y_start - margin),
        min(image_shape_yx[0], feature_bounds.y_stop + margin),
        max(0, feature_bounds.x_start - margin),
        min(image_shape_yx[1], feature_bounds.x_stop + margin),
    )
    if not compact_window_is_admitted(
        bounds, maximum_bounds_pixels=maximum_bounds_pixels
    ):
        return None
    return bounds


def _loop_groups_in_feature(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    labels: np.ndarray,
    feature: np.ndarray,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    wcs: WCS,
    beam: RestoringBeam,
    plan: ResidualAtrousPlan,
    island_sigma: float,
    minimum_support_fraction: float,
    *,
    bounds: ImageBounds,
    evidence: list[ComponentGroupingEvidence],
) -> tuple[frozenset[int], ...]:
    """Reconcile resolved loops larger than a wavelet-parent footprint.

    Reuse local fits; never allocate a joint fit of an extended island. A
    connected support feature is only a work unit. Actual grouping still
    requires resolved tangential shape evidence around a hole or along a
    connected beam-scale arc. Every array is this feature's window; ``feature``
    selects the pixels the reconciled feature owns inside it.
    """
    by_label = {
        index: fit
        for index, fit in fits
        if isinstance(fit, ValidCompactGaussianFit)
    }
    # An unavailable component supplies no shape evidence, but cannot veto
    # independent tangential evidence from three measured peers.
    indexes = _feature_components(labels, feature) & by_label.keys()
    if len(indexes) < _MINIMUM_LOOP_COMPONENTS:
        return ()
    geometry = compact_geometry_from_wcs(beam, wcs, bounds.center_xy)
    covariance = geometry.restoring_beam_covariance_pixels_squared
    assert covariance is not None
    xx, xy, yy = covariance
    beam_covariance = np.array(((xx, xy), (xy, yy)))
    members = tuple((index, by_label[index]) for index in sorted(indexes))
    beam_scale_significance = _matched_snrs(
        residual, rms, valid, plan, minimum_support_fraction
    )[0]
    return (
        *_resolved_emission_loop(
            residual,
            rms,
            valid,
            plan,
            fits=members,
            bounds=bounds,
            beam_covariance=beam_covariance,
            island_sigma=island_sigma,
            minimum_support_fraction=minimum_support_fraction,
            evidence=evidence,
        ),
        *_resolved_open_arc_groups(
            beam_scale_significance,
            valid,
            members,
            bounds,
            beam_covariance,
            island_sigma,
            evidence=evidence,
        ),
    )


def _feature_components(
    labels: np.ndarray, feature: np.ndarray
) -> frozenset[int]:
    """Return the measurement components one support feature holds."""
    return frozenset(
        int(index) for index in np.unique(labels[feature]) if index > 0
    )


def _merge_overlapping_groups(
    groups: list[frozenset[int]],
) -> tuple[frozenset[int], ...]:
    """Canonical transitive reconciliation of repeated scale evidence."""
    reconciled: list[frozenset[int]] = []
    for group in groups:
        combined = group
        for previous in reconciled[:]:
            if previous & combined:
                combined |= previous
                reconciled.remove(previous)
        reconciled.append(combined)
    return tuple(sorted(reconciled, key=min))


def _residual_groups_in_feature(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    labels: np.ndarray,
    feature: np.ndarray,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    *,
    bounds: ImageBounds,
    evidence: list[ComponentGroupingEvidence],
) -> tuple[frozenset[int], ...]:
    """Join residual halo fragments, without absorbing proven compact rows.

    Shared filtered support is insufficient: require seeded adjacent-scale
    emission remaining after subtraction of the independently admitted
    compact models. An auxiliary fit that failed the parent's adequacy check
    cannot explain away the extended emission that prevented its admission.
    The residual determines membership only; flux still uses original pixels.
    Every array is this feature's window, and a model component may sit
    outside the feature yet inside that window.
    """
    indexes = _feature_components(labels, feature)
    if len(indexes) <= 1:
        return ()
    model, _ = _model_and_groups(
        tuple(
            (index, fit)
            for index, fit in fits
            if isinstance(fit, ValidCompactGaussianFit)
            and index in protected_labels
            and "fit-at-bound" not in fit.quality_flags
            and np.any(labels == index)
        ),
        bounds,
    )
    responses = _matched_responses(
        residual - model, rms, valid, plan, minimum_support_fraction
    )
    snrs = calibrated_scale_snrs(
        responses, minimum_support_fraction=minimum_support_fraction
    )
    persistent = persistent_seeded_scale_support(
        snrs,
        tuple(item.response_jy_per_beam for item in responses),
        valid,
        detection_sigma=detection_sigma,
        island_sigma=island_sigma,
        minimum_pixels=minimum_pixels,
    )
    residual_labels, _ = cast(
        tuple[np.ndarray, int], label(persistent, np.ones((3, 3)))
    )
    local_residual_support = np.logical_or.reduce(
        tuple(
            (first >= island_sigma) & (second >= island_sigma)
            for first, second in pairwise(snrs)
        )
    )
    groups: list[frozenset[int]] = []
    for item in range(1, int(residual_labels.max()) + 1):
        members = frozenset(
            int(index)
            for index in np.unique(labels[residual_labels == item])
            if index in indexes
            and (
                index not in protected_labels
                or _fit_core_in_feature(
                    index,
                    fits,
                    residual_labels,
                    item,
                    bounds,
                    local_residual_support,
                )
            )
        )
        if len(members) <= 1:
            continue
        groups.append(members)
        scales: set[int] = set()
        for scale_id, (first, second) in enumerate(pairwise(snrs), 1):
            if np.any(
                (residual_labels == item)
                & (first >= island_sigma)
                & (second >= island_sigma)
            ):
                scales.update((scale_id, scale_id + 1))
        evidence.append(
            ComponentGroupingEvidence(
                "persistent-residual",
                tuple(sorted(scales)),
                members,
                members & protected_labels,
            )
        )
    return tuple(groups)


def group_support_feature_components(  # noqa: PLR0913, PLR0917
    residual_window: np.ndarray,
    rms_window: np.ndarray,
    valid_window: np.ndarray,
    measurement_window: np.ndarray,
    feature_window: np.ndarray,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    wcs: WCS,
    beam: RestoringBeam,
    atrous_plan: ResidualAtrousPlan,
    *,
    bounds: ImageBounds,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    minimum_support_fraction: float,
) -> SupportFeatureGroups:
    """Group the components one connected support feature holds.

    Both remaining cross-parent steps label the accumulated measurement
    support with the same connectivity, so they share this work unit and one
    read of its window. ``fits`` and ``protected_labels`` need only cover the
    components whose measurement labels reach this window.
    """
    evidence: list[ComponentGroupingEvidence] = []
    groups = (
        *_loop_groups_in_feature(
            residual_window,
            rms_window,
            valid_window,
            measurement_window,
            feature_window,
            fits,
            wcs,
            beam,
            atrous_plan,
            island_sigma,
            minimum_support_fraction,
            bounds=bounds,
            evidence=evidence,
        ),
        *_residual_groups_in_feature(
            residual_window,
            rms_window,
            valid_window,
            measurement_window,
            feature_window,
            fits,
            protected_labels,
            atrous_plan,
            minimum_support_fraction,
            detection_sigma,
            island_sigma,
            minimum_pixels,
            bounds=bounds,
            evidence=evidence,
        ),
    )
    return SupportFeatureGroups(groups, tuple(evidence))


def _fit_core_in_feature(  # noqa: PLR0913, PLR0917
    index: int,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    labels: np.ndarray,
    feature: int,
    bounds: ImageBounds,
    local_residual_support: np.ndarray,
) -> bool:
    """A compact fit cannot veto significant diffuse emission beneath it.

    A mere overlap at a wing or an unrelated feature peak is insufficient.
    Require adjacent-scale residual evidence inside the fit's half-maximum
    ellipse as well as the seeded persistent feature. The ellipse uses the
    same FWHM core as compact separation; a single centre pixel can miss
    asymmetric residuals after subtracting an extended fitted component.
    Membership in a broad envelope alone can bridge an empty gap.
    """
    fit = next((fit for label, fit in fits if label == index), None)
    if not isinstance(fit, ValidCompactGaussianFit):
        return False
    yy, xx = np.nonzero((labels == feature) & local_residual_support)
    parameters = fit.parameters
    dx = xx + bounds.x_start - parameters.centroid_xy[0]
    dy = yy + bounds.y_start - parameters.centroid_xy[1]
    angle = np.deg2rad(parameters.major_axis_angle_degrees)
    major = dx * np.cos(angle) + dy * np.sin(angle)
    minor = -dx * np.sin(angle) + dy * np.cos(angle)
    distance = (major / parameters.major_sigma_pixels) ** 2 + (
        minor / parameters.minor_sigma_pixels
    ) ** 2
    return bool(np.any(distance <= 2 * np.log(2)))


def _measurement_fit_parents(
    measurement_labels: np.ndarray, context_margin_pixels: int
) -> np.ndarray:
    """Join interacting fit contexts on one caller-bounded image window.

    A wavelet hierarchy is not a computational fit parent. Owners whose
    existing fit contexts touch need a joint model; distant contexts do not.
    Disconnected pieces of the same owner remain one fit target. Sparse
    reconciliation scales with owner/context links, not all owner pairs.
    """
    support = measurement_labels > 0
    contexts = (
        binary_dilation(
            support,
            structure=np.ones((3, 3)),
            iterations=context_margin_pixels,
        )
        if context_margin_pixels
        else support
    )
    context_labels, count = cast(
        tuple[np.ndarray, int], label(contexts, np.ones((3, 3)))
    )
    if count == 0:
        return np.zeros_like(measurement_labels, dtype=np.int32)
    links = np.unique(
        np.column_stack(
            (measurement_labels[support], context_labels[support])
        ),
        axis=0,
    )
    same_owner = np.diff(links[:, 0]) == 0
    first = links[:-1, 1][same_owner] - 1
    second = links[1:, 1][same_owner] - 1
    graph = coo_matrix(
        (np.ones(first.size), (first, second)), shape=(count, count)
    )
    _, groups = connected_components(graph, directed=False)
    lookup = np.concatenate((np.zeros(1, dtype=np.int32), groups + 1))
    return np.where(support, lookup[context_labels], 0).astype(np.int32)


@dataclass(frozen=True, slots=True)
class FitParentMeasurement:
    """One fit parent's bounded measurement outputs.

    Every field is a record or an array bounded by that parent's own read, so
    a caller that measures one fit parent per task returns nothing
    image-sized. ``support_window`` is the persistent measurement support the
    parent contributes, which callers combine with a boolean OR.
    """

    fits: tuple[tuple[int, CompactGaussianFitResult], ...] = ()
    compact_groups: tuple[frozenset[int], ...] = ()
    extended_groups: tuple[frozenset[int], ...] = ()
    evidence: tuple[ComponentGroupingEvidence, ...] = ()
    deferred: bool = False
    support_bounds: ImageBounds | None = None
    support_window: np.ndarray | None = None


def fit_parent_margin_pixels(
    fit_config: CompactGaussianFitConfig,
    atrous_plan: ResidualAtrousPlan,
) -> int:
    """Return the context a fit parent reads beyond its own support."""
    return max(
        ceil(fit_config.context_margin_pixels),
        atrous_plan.maximum_halo_pixels,
        _adequacy_filter_bank(atrous_plan).maximum_halo_pixels,
    )


def measure_fit_parent_components(  # noqa: PLR0913, PLR0917
    residual_window: np.ndarray,
    rms_window: np.ndarray,
    valid_window: np.ndarray,
    fit_parent_window: np.ndarray,
    direct_window: np.ndarray,
    measurement_window: np.ndarray,
    geometry: CompactMeasurementGeometry,
    moment_config: CompactMomentConfig,
    fit_config: CompactGaussianFitConfig,
    *,
    parent_index: int,
    bounds: ImageBounds,
    image_shape_yx: tuple[int, int],
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    maximum_bounds_pixels: int,
    atrous_plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
) -> FitParentMeasurement:
    """Fit one bounded measurement parent from its own original pixels.

    The window must hold the parent's support and the reviewed context margin
    around it; no decision here reads further, so one task can measure one
    fit parent exactly. A parent whose window exceeds the admitted bound is
    deferred rather than fitted on truncated pixels.

    ``geometry`` is the caller's local beam and pixel geometry at the centre
    of ``bounds``, as
    :func:`~hebog.algorithms.astrometry.compact_geometries_from_wcs` builds
    it for a whole batch at once. Deriving it here instead would pay
    Astropy's per-call frame machinery once per parent, which costs more
    than the fit.
    """
    if not compact_window_is_admitted(
        bounds, maximum_bounds_pixels=maximum_bounds_pixels
    ):
        return FitParentMeasurement(deferred=True)
    parent_support = fit_parent_window == parent_index
    local_valid = (
        valid_window
        & np.isfinite(residual_window)
        & np.isfinite(rms_window)
        & (rms_window > 0.0)
    )
    local_valid &= (fit_parent_window == 0) | parent_support
    seeds = np.where(
        parent_support & (residual_window > 0.0) & local_valid,
        direct_window,
        0,
    ).astype(np.int32)
    indexes = tuple(int(index) for index in np.unique(seeds) if index > 0)
    if not indexes:
        return FitParentMeasurement(deferred=True)
    island_id = f"measurement-parent-{parent_index}"
    regions = tuple(
        _region(
            seeds,
            index,
            residual_window,
            rms_window,
            (bounds.y_start, bounds.x_start),
            island_id,
        )
        for index in indexes
    )
    island = _measurement_island(
        regions, seeds, bounds, parent_index, image_shape_yx
    )
    compact = _ComponentFitInput(
        island,
        bounds,
        regions,
        residual_window,
        rms_window,
        local_valid,
        seeds,
    )
    moments = measure_compact_moments(compact, geometry, moment_config)[1:]
    # These are native component measurements, not Gaussian source
    # surrogates. Apply the already configured component extension rule
    # to the whole joint solution; do not splice per-component fits from
    # competing source/component models. Source flux is an aperture.
    fitted = fit_compact_gaussian_mixture(
        compact,
        moments,
        geometry,
        replace(
            fit_config,
            extension_significance_sigma=fit_config.component_extension_significance_sigma,
        ),
    )
    labelled = tuple(zip(indexes, fitted, strict=True))
    # Measurement-only persistent emission belongs to admitted owners
    # independently of whether a compact Gaussian describes them. A
    # bounded or unavailable fit must not truncate extended photometry.
    support_window = _persistent_measurement_support(
        residual_window,
        rms_window,
        local_valid,
        atrous_plan,
        minimum_support_fraction,
        detection_sigma,
        island_sigma,
        minimum_pixels,
    )
    complete = tuple(
        (index, fit)
        for index, fit in labelled
        if isinstance(fit, ValidCompactGaussianFit)
        and "fit-at-bound" not in fit.quality_flags
    )
    admitted = _admit_fallbacks(
        complete,
        compact,
        fit_config,
        atrous_plan,
        minimum_support_fraction,
        detection_sigma,
        island_sigma,
        minimum_pixels,
    )
    by_index = dict(admitted)
    fits = tuple((index, by_index.get(index, fit)) for index, fit in labelled)
    measured = FitParentMeasurement(
        fits=fits,
        support_bounds=bounds,
        support_window=support_window,
    )
    expected_indexes = set(np.unique(measurement_window[parent_support])) - {0}
    if len(complete) != len(expected_indexes) or any(
        isinstance(fit, FailedCompactGaussianFit) for _, fit in admitted
    ):
        return measured
    evidence: list[ComponentGroupingEvidence] = []
    model, groups = _model_and_groups(complete, bounds)
    covariance = geometry.restoring_beam_covariance_pixels_squared
    assert covariance is not None
    beam_xx, beam_xy, beam_yy = covariance
    loop_groups = (
        _resolved_emission_loop(
            residual_window,
            rms_window,
            local_valid,
            atrous_plan,
            fits=complete,
            bounds=bounds,
            beam_covariance=np.array(((beam_xx, beam_xy), (beam_xy, beam_yy))),
            island_sigma=island_sigma,
            minimum_support_fraction=minimum_support_fraction,
            evidence=evidence,
        )
        if len(groups) > 1
        else ()
    )
    compact_groups: list[frozenset[int]] = []
    if loop_groups:
        loop_labels = {index for group in loop_groups for index in group}
        nearest = expand_source_measurement_labels(
            measurement_window,
            valid_window,
            radius_pixels=ceil(float(np.hypot(*bounds.shape_yx))),
        )
        for group in groups:
            remaining = group - loop_labels
            if remaining and not _unmodelled_detection(
                residual_window - model,
                rms_window,
                local_valid,
                detection_sigma,
                island_sigma,
                minimum_pixels,
                atrous_plan,
                minimum_support_fraction,
                np.isin(nearest, tuple(remaining)),
            ):
                compact_groups.append(remaining)
        return replace(
            measured,
            compact_groups=tuple(compact_groups),
            extended_groups=tuple(loop_groups),
            evidence=tuple(evidence),
        )
    if not _unmodelled_detection(
        residual_window - model,
        rms_window,
        local_valid,
        detection_sigma,
        island_sigma,
        minimum_pixels,
        atrous_plan,
        minimum_support_fraction,
        expand_source_measurement_labels(
            fit_parent_window,
            valid_window,
            radius_pixels=ceil(float(np.hypot(*bounds.shape_yx))),
        )
        == parent_index,
    ):
        compact_groups.extend(groups)
    return replace(
        measured,
        compact_groups=tuple(compact_groups),
        evidence=tuple(evidence),
    )


def measure_component_models(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    direct_labels: np.ndarray,
    measurement_labels: np.ndarray,
    wcs: WCS,
    beam: RestoringBeam,
    moment_config: CompactMomentConfig,
    fit_config: CompactGaussianFitConfig,
    *,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    maximum_bounds_pixels: int,
    atrous_plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
) -> ComponentMeasurements:
    """Fit each bounded connected measurement parent with original pixels.

    No full-image fit matrix is constructed. Foreground owners outside a
    parent's window are excluded; negative background-context pixels remain
    in the fit. Positive exact seed pixels initialize the existing moment
    oracle only. Published ownership is never replaced by these fit masks.
    """
    parents = _measurement_fit_parents(
        measurement_labels, fit_config.context_margin_pixels
    )
    objects = find_objects(parents)
    measured_parents: list[FitParentMeasurement] = []
    measurement_support = np.zeros(residual.shape, dtype=np.bool_)
    margin = fit_parent_margin_pixels(fit_config, atrous_plan)
    for parent_index, slices in enumerate(objects, start=1):
        assert slices is not None, "fit-context labels must be dense"
        ys, xs = slices
        bounds = ImageBounds(
            max(0, ys.start - margin),
            min(residual.shape[0], ys.stop + margin),
            max(0, xs.start - margin),
            min(residual.shape[1], xs.stop + margin),
        )
        window = np.s_[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ]
        measured = measure_fit_parent_components(
            residual[window],
            rms[window],
            valid[window],
            parents[window],
            direct_labels[window],
            measurement_labels[window],
            compact_geometry_from_wcs(beam, wcs, bounds.center_xy),
            moment_config,
            fit_config,
            parent_index=parent_index,
            bounds=bounds,
            image_shape_yx=residual.shape,
            detection_sigma=detection_sigma,
            island_sigma=island_sigma,
            minimum_pixels=minimum_pixels,
            maximum_bounds_pixels=maximum_bounds_pixels,
            atrous_plan=atrous_plan,
            minimum_support_fraction=minimum_support_fraction,
        )
        measured_parents.append(measured)
        if measured.support_window is not None:
            measurement_support[window] |= measured.support_window
    fits = tuple(
        item for measured in measured_parents for item in measured.fits
    )
    protected_labels = frozenset(
        index
        for measured in measured_parents
        for group in measured.compact_groups
        for index in group
    )
    measurement_support.setflags(write=False)
    return replace(
        reconcile_component_measurements(
            parents=tuple(measured_parents),
            features=_whole_plane_feature_groups(
                residual,
                rms,
                valid,
                measurement_labels,
                measurement_support,
                fits,
                protected_labels,
                wcs,
                beam,
                atrous_plan,
                detection_sigma=detection_sigma,
                island_sigma=island_sigma,
                minimum_pixels=minimum_pixels,
                maximum_bounds_pixels=maximum_bounds_pixels,
                minimum_support_fraction=minimum_support_fraction,
            ),
        ),
        measurement_support=measurement_support,
    )


def _whole_plane_feature_groups(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    measurement_labels: np.ndarray,
    measurement_support: np.ndarray,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    protected_labels: frozenset[int],
    wcs: WCS,
    beam: RestoringBeam,
    atrous_plan: ResidualAtrousPlan,
    *,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    maximum_bounds_pixels: int,
    minimum_support_fraction: float,
) -> tuple[SupportFeatureGroups, ...]:
    """Group every connected support feature, as the serial oracle."""
    connected, _ = cast(
        tuple[np.ndarray, int],
        label(measurement_support & valid, np.ones((3, 3))),
    )
    margin = support_feature_margin_pixels(atrous_plan)
    grouped: list[SupportFeatureGroups] = []
    for identity, slices in enumerate(find_objects(connected), 1):
        assert slices is not None, "support-feature labels must be dense"
        ys, xs = slices
        bounds = support_feature_window(
            ImageBounds(ys.start, ys.stop, xs.start, xs.stop),
            margin=margin,
            image_shape_yx=residual.shape,
            maximum_bounds_pixels=maximum_bounds_pixels,
        )
        if bounds is None:
            continue
        window = np.s_[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ]
        grouped.append(
            group_support_feature_components(
                residual[window],
                rms[window],
                valid[window],
                measurement_labels[window],
                connected[window] == identity,
                fits,
                protected_labels,
                wcs,
                beam,
                atrous_plan,
                bounds=bounds,
                detection_sigma=detection_sigma,
                island_sigma=island_sigma,
                minimum_pixels=minimum_pixels,
                minimum_support_fraction=minimum_support_fraction,
            )
        )
    return tuple(grouped)


def reconcile_component_measurements(
    *,
    parents: tuple[FitParentMeasurement, ...],
    features: tuple[SupportFeatureGroups, ...],
) -> ComponentMeasurements:
    """Reconcile the parents' and features' records into one measurement.

    Every step that spans fit parents has already run: each connected support
    feature contributed its extended groups and grouping evidence. What is
    left is a reduction over records, so it holds no image-sized array at all:
    the support the parents contributed stays in the generation the cores
    wrote it to.
    """
    output: list[tuple[int, CompactGaussianFitResult]] = []
    compact_groups: list[frozenset[int]] = []
    extended_groups: list[frozenset[int]] = []
    evidence: list[ComponentGroupingEvidence] = []
    deferred = 0
    for measured in parents:
        deferred += int(measured.deferred)
        output.extend(measured.fits)
        compact_groups.extend(measured.compact_groups)
        extended_groups.extend(measured.extended_groups)
        evidence.extend(measured.evidence)
    for item in features:
        extended_groups.extend(item.extended_groups)
        evidence.extend(item.evidence)
    # Reconcile admitted sources as whole owners. An extended proposal may
    # include only some Gaussian members of an accepted compact source; it
    # must not split the other members into a second, overlapping source.
    # Independent compact owners remain separate unless evidence names them.
    proposed_extended_labels = {
        index for group in extended_groups for index in group
    }
    reconciled = tuple(
        group
        for group in _merge_overlapping_groups(
            [*extended_groups, *compact_groups]
        )
        if group & proposed_extended_labels
    )
    proposed_compact_groups = tuple(compact_groups)
    protected_compact_labels = {
        index for group in proposed_compact_groups for index in group
    }
    evidence = [
        replace(
            item,
            protected_labels=(
                item.protected_labels
                | (item.component_labels & protected_compact_labels)
            ),
        )
        for item in evidence
    ]
    evidence.extend(
        ComponentGroupingEvidence("directional-fwhm-overlap", (), group)
        for group in compact_groups
        if len(group) > 1
    )
    extended_labels = {index for group in reconciled for index in group}
    compact_groups = [
        group - extended_labels
        for group in compact_groups
        if group - extended_labels
    ]
    return ComponentMeasurements(
        tuple(output),
        tuple(compact_groups),
        deferred,
        None,
        tuple(reconciled),
        proposed_compact_groups,
        tuple(
            sorted(
                set(evidence),
                key=lambda item: (
                    item.reason,
                    item.scale_ids,
                    tuple(sorted(item.component_labels)),
                ),
            )
        ),
    )
