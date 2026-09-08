"""Bounded original-pixel Gaussian measurements for detected components."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import cast

import numpy as np
from astropy.wcs import WCS
from scipy.ndimage import binary_fill_holes, find_objects, label

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
    ValidCompactGaussianFit,
)
from hebog.data_models.images import RestoringBeam
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
class ComponentMeasurements:
    """Fits retain detection labels; compact groups constrain association."""

    fits: tuple[tuple[int, CompactGaussianFitResult], ...]
    compact_groups: tuple[frozenset[int], ...]
    deferred_parent_count: int
    measurement_support: np.ndarray | None = None
    extended_groups: tuple[frozenset[int], ...] = ()


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
    return persistent_seeded_scale_support(
        _matched_snrs(residual, rms, valid, plan, minimum_support_fraction),
        residual,
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
    prepared = prepare_scale_filter_inputs(
        residual, valid, np.zeros_like(residual), rms
    )
    bank = _adequacy_filter_bank(plan)
    result = evaluate_scale_filter_bank(
        prepared, bank, minimum_support_fraction=minimum_support_fraction
    )
    return calibrated_scale_snrs(
        result.responses, minimum_support_fraction=minimum_support_fraction
    )


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
    for snr in snrs:
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
            # Scale copies of the same arcs are evidence for one source,
            # not repeated or overlapping membership constraints.
            for previous in groups[:]:
                if previous & selected:
                    selected.update(previous)
                    groups.remove(previous)
            groups.append(selected)
    return tuple(frozenset(group) for group in groups)


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


def _cross_parent_loop_groups(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    labels: np.ndarray,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    wcs: WCS,
    beam: RestoringBeam,
    plan: ResidualAtrousPlan,
    island_sigma: float,
    minimum_support_fraction: float,
    maximum_bounds_pixels: int,
) -> tuple[frozenset[int], ...]:
    """Reconcile resolved loops larger than a wavelet-parent footprint.

    Reuse local fits; never allocate a joint fit of an extended island. A
    connected region is only a work unit. Actual grouping still requires
    an image-space hole and resolved tangential shape evidence.
    """
    connected, _ = cast(
        tuple[np.ndarray, int], label((labels > 0) & valid, np.ones((3, 3)))
    )
    by_label = {
        index: fit
        for index, fit in fits
        if isinstance(fit, ValidCompactGaussianFit)
    }
    margin = _adequacy_filter_bank(plan).maximum_halo_pixels
    groups: list[frozenset[int]] = []
    for identity, slices in enumerate(find_objects(connected), 1):
        assert slices is not None
        ys, xs = slices
        indexes = frozenset(
            int(index)
            for index in np.unique(
                labels[slices][connected[slices] == identity]
            )
            if index > 0
        )
        if (
            len(indexes) < _MINIMUM_LOOP_COMPONENTS
            or not indexes <= by_label.keys()
        ):
            continue
        bounds = ImageBounds(
            max(0, ys.start - margin),
            min(labels.shape[0], ys.stop + margin),
            max(0, xs.start - margin),
            min(labels.shape[1], xs.stop + margin),
        )
        if np.prod(bounds.shape_yx) > maximum_bounds_pixels:
            continue
        center = (
            (bounds.x_start + bounds.x_stop - 1) / 2,
            (bounds.y_start + bounds.y_stop - 1) / 2,
        )
        geometry = compact_geometry_from_wcs(beam, wcs, center)
        covariance = geometry.restoring_beam_covariance_pixels_squared
        assert covariance is not None
        xx, xy, yy = covariance
        window = np.s_[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ]
        groups.extend(
            _resolved_emission_loop(
                residual[window],
                rms[window],
                valid[window],
                plan,
                fits=tuple(
                    (index, by_label[index]) for index in sorted(indexes)
                ),
                bounds=bounds,
                beam_covariance=np.array(((xx, xy), (xy, yy))),
                island_sigma=island_sigma,
                minimum_support_fraction=minimum_support_fraction,
            )
        )
    return tuple(groups)


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


def _extended_residual_groups(  # noqa: PLR0913, PLR0917
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    labels: np.ndarray,
    fits: tuple[tuple[int, CompactGaussianFitResult], ...],
    compact_groups: tuple[frozenset[int], ...],
    measurement_support: np.ndarray,
    plan: ResidualAtrousPlan,
    minimum_support_fraction: float,
    detection_sigma: float,
    island_sigma: float,
    minimum_pixels: int,
    maximum_bounds_pixels: int,
) -> tuple[frozenset[int], ...]:
    """Join residual halo fragments, without absorbing proven compact rows.

    Shared filtered support is insufficient: require seeded adjacent-scale
    emission remaining after subtraction of the valid, unconstrained native
    component models. A fit at a bound cannot explain away that emission.
    The residual determines membership only; flux still uses original pixels.
    """
    protected = {index for group in compact_groups for index in group}
    connected, _ = cast(
        tuple[np.ndarray, int],
        label(measurement_support & valid, np.ones((3, 3))),
    )
    groups: list[frozenset[int]] = []
    for identity, slices in enumerate(find_objects(connected), 1):
        assert slices is not None
        ys, xs = slices
        indexes = frozenset(
            int(index)
            for index in np.unique(
                labels[slices][connected[slices] == identity]
            )
            if index > 0 and index not in protected
        )
        if len(indexes) <= 1:
            continue
        margin = _adequacy_filter_bank(plan).maximum_halo_pixels
        bounds = ImageBounds(
            max(0, ys.start - margin),
            min(labels.shape[0], ys.stop + margin),
            max(0, xs.start - margin),
            min(labels.shape[1], xs.stop + margin),
        )
        if np.prod(bounds.shape_yx) > maximum_bounds_pixels:
            continue
        window = np.s_[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ]
        model, _ = _model_and_groups(
            tuple(
                (index, fit)
                for index, fit in fits
                if isinstance(fit, ValidCompactGaussianFit)
                and "fit-at-bound" not in fit.quality_flags
                and np.any(labels[window] == index)
            ),
            bounds,
        )
        persistent = _persistent_measurement_support(
            residual[window] - model,
            rms[window],
            valid[window],
            plan,
            minimum_support_fraction,
            detection_sigma,
            island_sigma,
            minimum_pixels,
        )
        residual_labels, _ = cast(
            tuple[np.ndarray, int], label(persistent, np.ones((3, 3)))
        )
        for feature in range(1, int(residual_labels.max()) + 1):
            members = frozenset(
                int(index)
                for index in np.unique(
                    labels[window][residual_labels == feature]
                )
                if index in indexes
            )
            if len(members) > 1:
                groups.append(members)
    return tuple(groups)


def measure_component_models(  # noqa: PLR0913, PLR0917, PLR0915
    residual: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    direct_labels: np.ndarray,
    measurement_labels: np.ndarray,
    parent_labels: np.ndarray,
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
    parents = parent_labels
    objects = find_objects(parents)
    output: list[tuple[int, CompactGaussianFitResult]] = []
    compact_groups: list[frozenset[int]] = []
    extended_groups: list[frozenset[int]] = []
    deferred = 0
    measurement_support = np.zeros(residual.shape, dtype=np.bool_)
    margin = max(
        ceil(fit_config.context_margin_pixels),
        atrous_plan.maximum_halo_pixels,
        _adequacy_filter_bank(atrous_plan).maximum_halo_pixels,
    )
    for parent_index, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        ys, xs = slices
        bounds = ImageBounds(
            max(0, ys.start - margin),
            min(residual.shape[0], ys.stop + margin),
            max(0, xs.start - margin),
            min(residual.shape[1], xs.stop + margin),
        )
        if np.prod(bounds.shape_yx) > maximum_bounds_pixels:
            deferred += 1
            continue
        window = np.s_[
            bounds.y_start : bounds.y_stop, bounds.x_start : bounds.x_stop
        ]
        parent_support = parents[window] == parent_index
        local_valid = (
            valid[window]
            & np.isfinite(residual[window])
            & np.isfinite(rms[window])
            & (rms[window] > 0.0)
        )
        local_valid &= (parents[window] == 0) | parent_support
        seeds = np.where(
            parent_support & (residual[window] > 0.0) & local_valid,
            direct_labels[window],
            0,
        ).astype(np.int32)
        indexes = tuple(int(index) for index in np.unique(seeds) if index > 0)
        if not indexes:
            deferred += 1
            continue
        island_id = f"measurement-parent-{parent_index}"
        regions = tuple(
            _region(
                seeds,
                index,
                residual[window],
                rms[window],
                (bounds.y_start, bounds.x_start),
                island_id,
            )
            for index in indexes
        )
        island = _measurement_island(
            regions, seeds, bounds, parent_index, residual.shape
        )
        compact = _ComponentFitInput(
            island,
            bounds,
            regions,
            residual[window],
            rms[window],
            local_valid,
            seeds,
        )
        center_xy = (
            (bounds.x_start + bounds.x_stop - 1) / 2,
            (bounds.y_start + bounds.y_stop - 1) / 2,
        )
        geometry = compact_geometry_from_wcs(beam, wcs, center_xy)
        moments = measure_compact_moments(compact, geometry, moment_config)[1:]
        fitted = fit_compact_gaussian_mixture(
            compact, moments, geometry, fit_config
        )
        labelled = tuple(zip(indexes, fitted, strict=True))
        output.extend(labelled)
        # Measurement-only persistent emission belongs to admitted owners
        # independently of whether a compact Gaussian describes them. A
        # bounded or unavailable fit must not truncate extended photometry.
        measurement_support[window] |= _persistent_measurement_support(
            residual[window],
            rms[window],
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
        expected_indexes = set(
            np.unique(measurement_labels[window][parent_support])
        ) - {0}
        if len(complete) != len(expected_indexes):
            continue
        model, groups = _model_and_groups(complete, bounds)
        covariance = geometry.restoring_beam_covariance_pixels_squared
        assert covariance is not None
        beam_xx, beam_xy, beam_yy = covariance
        loop_groups = (
            _resolved_emission_loop(
                residual[window],
                rms[window],
                local_valid,
                atrous_plan,
                fits=complete,
                bounds=bounds,
                beam_covariance=np.array(
                    ((beam_xx, beam_xy), (beam_xy, beam_yy))
                ),
                island_sigma=island_sigma,
                minimum_support_fraction=minimum_support_fraction,
            )
            if len(groups) > 1
            else ()
        )
        if loop_groups:
            extended_groups.extend(loop_groups)
            loop_labels = {index for group in loop_groups for index in group}
            nearest = expand_source_measurement_labels(
                measurement_labels[window],
                valid[window],
                radius_pixels=ceil(float(np.hypot(*bounds.shape_yx))),
            )
            for group in groups:
                remaining = group - loop_labels
                if remaining and not _unmodelled_detection(
                    residual[window] - model,
                    rms[window],
                    local_valid,
                    detection_sigma,
                    island_sigma,
                    minimum_pixels,
                    atrous_plan,
                    minimum_support_fraction,
                    np.isin(nearest, tuple(remaining)),
                ):
                    compact_groups.append(remaining)
            continue
        if not _unmodelled_detection(
            residual[window] - model,
            rms[window],
            local_valid,
            detection_sigma,
            island_sigma,
            minimum_pixels,
            atrous_plan,
            minimum_support_fraction,
            expand_source_measurement_labels(
                parents[window],
                valid[window],
                radius_pixels=ceil(float(np.hypot(*bounds.shape_yx))),
            )
            == parent_index,
        ):
            compact_groups.extend(groups)
    extended_groups.extend(
        _cross_parent_loop_groups(
            residual,
            rms,
            valid,
            measurement_labels,
            tuple(output),
            wcs,
            beam,
            atrous_plan,
            island_sigma,
            minimum_support_fraction,
            maximum_bounds_pixels,
        )
    )
    extended_groups.extend(
        _extended_residual_groups(
            residual,
            rms,
            valid,
            measurement_labels,
            tuple(output),
            tuple(compact_groups),
            measurement_support,
            atrous_plan,
            minimum_support_fraction,
            detection_sigma,
            island_sigma,
            minimum_pixels,
            maximum_bounds_pixels,
        )
    )
    reconciled = _merge_overlapping_groups(extended_groups)
    extended_labels = {index for group in reconciled for index in group}
    compact_groups = [
        group - extended_labels
        for group in compact_groups
        if group - extended_labels
    ]
    measurement_support.setflags(write=False)
    return ComponentMeasurements(
        tuple(output),
        tuple(compact_groups),
        deferred,
        measurement_support,
        tuple(reconciled),
    )
