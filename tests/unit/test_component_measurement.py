"""Bounded model admission and morphology evidence on analytic pixels."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from astropy.wcs import WCS

from hebog.algorithms import component_measurement as measurement
from hebog.algorithms.component_measurement import measure_component_models
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    build_residual_atrous_plan,
)
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    UnavailableCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import ImageBounds


def _measure(  # noqa: PLR0913
    *,
    component_index: int = 1,
    maximum_bounds_pixels: int = 10000,
    center_xy: tuple[float, float] = (16.0, 12.0),
    valid: np.ndarray | None = None,
    centers: tuple[tuple[float, float], ...] | None = None,
    shape_yx: tuple[int, int] = (25, 33),
):
    """One original-pixel ellipse with independently supplied unit RMS."""
    yy, xx = np.mgrid[: shape_yx[0], : shape_yx[1]]
    signal = np.zeros(shape_yx)
    labels = np.zeros(shape_yx, dtype=np.int32)
    for index, center in enumerate(centers or (center_xy,), component_index):
        profile = 10 * np.exp(
            -0.5
            * (((xx - center[0]) / 2.4) ** 2 + ((yy - center[1]) / 1.6) ** 2)
        )
        signal += profile
        labels[profile >= 3] = index
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cdelt = [-1 / 3600, 1 / 3600]
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.crval = [10.0, -30.0]
    beam = BeamShapePixels(4.0, 3.0, 0.0)
    config = CompactGaussianFitConfig(
        minimum_fit_pixels=7,
        maximum_function_evaluations=300,
        minimum_sigma_pixels=0.2,
        maximum_sigma_pixels=20.0,
        maximum_amplitude_factor=5.0,
        center_margin_pixels=1.0,
        convergence_tolerance=1e-10,
        maximum_axis_ratio=20.0,
        background_model="fixed-zero",
    )
    return measure_component_models(
        signal,
        np.ones_like(signal),
        np.ones(signal.shape, dtype=np.bool_) if valid is None else valid,
        labels,
        labels,
        wcs,
        RestoringBeam(4 / 3600, 3 / 3600, 0.0),
        CompactMomentConfig(3, 1e-12),
        config,
        detection_sigma=5.0,
        island_sigma=3.0,
        minimum_pixels=7,
        maximum_bounds_pixels=maximum_bounds_pixels,
        atrous_plan=build_residual_atrous_plan(beam, noise_correlation=beam),
        minimum_support_fraction=0.5,
    )


def test_sparse_parent_and_component_labels_preserve_model_measurements() -> (
    None
):
    """Task-local integer renumbering cannot change physical measurements."""
    original = _measure()
    renumbered = _measure(component_index=19)
    assert (
        original.deferred_parent_count == renumbered.deferred_parent_count == 0
    )
    assert original.compact_groups == (frozenset((1,)),)
    assert renumbered.compact_groups == (frozenset((19,)),)
    first, second = original.fits[0][1], renumbered.fits[0][1]
    assert isinstance(first, ValidCompactGaussianFit)
    assert isinstance(second, ValidCompactGaussianFit)
    assert first.parameters == second.parameters


def test_parent_work_deferral_does_not_allocate_a_fit() -> None:
    """The enclosing window is admitted before a dense fit context exists."""
    result = _measure(maximum_bounds_pixels=1)
    assert result.fits == result.compact_groups == ()
    assert result.deferred_parent_count == 1


@pytest.mark.parametrize("margin", (0, 1, 3))
def test_fit_contexts_preserve_disconnected_owners_and_label_permutations(
    margin: int,
) -> None:
    """Owner links join disjoint footprints without merging distant peers."""
    labels = np.zeros((17, 47), dtype=np.int32)
    labels[8, 4] = labels[8, 24] = 7
    labels[8, 6] = 2
    labels[8, 42] = 9
    parents = measurement._measurement_fit_parents(labels, margin)
    assert parents[8, 4] == parents[8, 24] != parents[8, 42]
    assert (parents[8, 4] == parents[8, 6]) == (margin > 0)
    assert np.all(parents[labels == 0] == 0)
    mapping = np.arange(10, dtype=np.int32)
    mapping[[2, 7, 9]] = (41, 6, 5)
    renumbered = measurement._measurement_fit_parents(mapping[labels], margin)
    np.testing.assert_array_equal(parents, renumbered)
    np.testing.assert_array_equal(
        measurement._measurement_fit_parents(np.zeros_like(labels), margin),
        np.zeros_like(labels),
    )


def test_connected_oversized_fit_remains_explicitly_unavailable() -> None:
    """Context separation cannot waive the joint-parameter limit of a chain."""
    result = _measure(
        centers=tuple((12.0 + 12 * index, 16.0) for index in range(17)),
        shape_yx=(33, 217),
        maximum_bounds_pixels=100_000,
    )
    assert len(result.fits) == 17
    assert all(
        isinstance(fit, UnavailableCompactGaussianFit)
        and fit.reason == "joint-fit-work-limit"
        for _, fit in result.fits
    )


def test_distant_compact_sources_do_not_share_a_joint_fit_work_limit() -> None:
    """A broad hierarchy is not one inseparable 108-parameter fit."""
    centers = tuple(
        (16.0 + 32 * x, 16.0 + 32 * y) for y in range(3) for x in range(6)
    )
    result = _measure(
        centers=centers, shape_yx=(97, 193), maximum_bounds_pixels=100_000
    )
    assert len(result.fits) == len(centers)
    assert result.deferred_parent_count == 0
    for (index, fitted), center in zip(result.fits, centers, strict=True):
        assert isinstance(fitted, ValidCompactGaussianFit)
        assert fitted.parameters.centroid_xy == pytest.approx(center, abs=1e-5)
        assert frozenset((index,)) in result.compact_groups


def test_extended_evidence_does_not_split_an_admitted_source_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial morphology proposal joins whole admitted source owners."""

    def extended_proposal(
        *_args: object, **kwargs: Any
    ) -> tuple[frozenset[int], ...]:
        group = frozenset((2, 3))
        kwargs["evidence"].append(
            measurement.ComponentGroupingEvidence("resolved-loop", (1,), group)
        )
        return (group,)

    monkeypatch.setattr(
        measurement, "_cross_parent_loop_groups", extended_proposal
    )
    result = _measure(
        centers=((12.0, 16.0), (15.0, 16.0), (60.0, 16.0), (95.0, 16.0)),
        shape_yx=(33, 113),
        maximum_bounds_pixels=100_000,
    )
    assert frozenset((1, 2)) in result.proposed_compact_groups
    assert result.extended_groups == (frozenset((1, 2, 3)),)
    assert result.compact_groups == (frozenset((4,)),)
    loop = next(
        item
        for item in result.grouping_evidence
        if item.reason == "resolved-loop"
    )
    assert loop.protected_labels == frozenset((2, 3))


@pytest.mark.parametrize("center", ((0.7, 1.2), (31.5, 23.3)))
def test_edge_context_recovers_the_in_image_gaussian(
    center: tuple[float, float],
) -> None:
    """A clipped fit window retains original global coordinates and flux."""
    fitted = _measure(center_xy=center).fits[0][1]
    assert isinstance(fitted, ValidCompactGaussianFit)
    assert fitted.parameters.centroid_xy == pytest.approx(center, abs=1e-5)
    assert fitted.parameters.major_sigma_pixels == pytest.approx(2.4, rel=1e-5)
    assert fitted.parameters.minor_sigma_pixels == pytest.approx(1.6, rel=1e-5)


def test_overlapping_models_group_without_double_counting_model_pixels() -> (
    None
):
    fitted = _measure().fits[0][1]
    assert isinstance(fitted, ValidCompactGaussianFit)
    bounds = ImageBounds(0, 25, 0, 33)
    single, _ = measurement._model_and_groups(((1, fitted),), bounds)
    model, groups = measurement._model_and_groups(
        (
            (1, fitted),
            (2, fitted),
            (
                3,
                replace(
                    fitted,
                    parameters=replace(
                        fitted.parameters, centroid_xy=(18.0, 12.0)
                    ),
                ),
            ),
        ),
        bounds,
    )
    assert groups == (frozenset((1, 2, 3)),)
    assert np.all(model >= 2 * single)
    assert measurement._merge_overlapping_groups(
        [
            frozenset((1, 2)),
            frozenset((4, 5)),
            frozenset((2, 3)),
            frozenset((3, 4)),
        ]
    ) == (frozenset((1, 2, 3, 4, 5)),)


def test_loop_evidence_rejects_unavailable_shapes_and_zero_radius() -> None:
    fitted = _measure().fits[0][1]
    assert isinstance(fitted, ValidCompactGaussianFit)
    assert fitted.uncertainty is not None
    for fit, center in (
        (replace(fitted, uncertainty=None), (2.0, 2.0)),
        (fitted, fitted.parameters.centroid_xy),
        (
            replace(
                fitted,
                uncertainty=replace(
                    fitted.uncertainty,
                    shape_parameter_covariance=(
                        -1.0,
                        0.0,
                        0.0,
                        -1.0,
                        0.0,
                        -1.0,
                    ),
                ),
            ),
            (2.0, 2.0),
        ),
    ):
        assert not measurement._tangential_shape_evidence(
            ((1, fit),), center, np.eye(2), 3.0
        )


@pytest.mark.parametrize(
    "outside_xy", ((-1.0, 40.0), (161.0, 40.0), (40.0, -1.0), (40.0, 81.0))
)
def test_disconnected_loops_in_one_context_do_not_share_fitted_arcs(
    outside_xy: tuple[float, float],
) -> None:
    """Tangential orientation alone cannot attach a remote component."""
    fitted = _measure().fits[0][1]
    assert isinstance(fitted, ValidCompactGaussianFit)
    yy, xx = np.mgrid[:81, :161]
    signal = np.zeros(xx.shape, dtype=float)
    fits = []
    for loop, center_x in enumerate((40, 120)):
        radius = np.hypot(xx - center_x, yy - 40)
        signal += 6 * np.exp(-0.5 * ((radius - 15) / 2) ** 2)
        for arc, angle in enumerate(np.arange(4) * np.pi / 2):
            fits.append(
                (
                    1 + 4 * loop + arc,
                    replace(
                        fitted,
                        parameters=replace(
                            fitted.parameters,
                            centroid_xy=(
                                center_x + 15 * np.cos(angle),
                                40 + 15 * np.sin(angle),
                            ),
                            major_sigma_pixels=5.0,
                            minor_sigma_pixels=2.0,
                            major_axis_angle_degrees=float(
                                (np.rad2deg(angle) + 90) % 180
                            ),
                        ),
                    ),
                )
            )
    fits.append(
        (
            9,
            replace(
                fitted,
                parameters=replace(fitted.parameters, centroid_xy=outside_xy),
            ),
        )
    )
    beam = BeamShapePixels(4.0, 3.0, 0.0)
    groups = measurement._resolved_emission_loop(
        signal,
        np.ones(signal.shape),
        np.ones(signal.shape, dtype=bool),
        build_residual_atrous_plan(beam, noise_correlation=beam),
        fits=tuple(fits),
        bounds=ImageBounds(0, 81, 0, 161),
        beam_covariance=np.diag(np.square(np.array((4.0, 3.0)) / 2.35482)),
        island_sigma=3.0,
        minimum_support_fraction=0.5,
    )
    assert set(groups) == {frozenset(range(1, 5)), frozenset(range(5, 9))}


@pytest.mark.parametrize(
    "centres",
    (
        ((8.0, 12.0), (16.0, 12.0)),
        ((8.0, 12.0), (16.0, 12.0), (24.0, 12.0)),
        ((8.0, 8.0), (24.0, 8.0), (16.0, 20.0)),
        ((-1.0, 12.0), (34.0, 12.0), (16.0, 26.0)),
    ),
)
def test_open_arc_rejects_insufficient_or_non_tangential_evidence(
    centres: tuple[tuple[float, float], ...],
) -> None:
    """Connected parallel ellipses or collinear centres do not prove an arc."""
    fitted = _measure().fits[0][1]
    assert isinstance(fitted, ValidCompactGaussianFit)
    fits = tuple(
        (
            index,
            replace(
                fitted,
                parameters=replace(fitted.parameters, centroid_xy=centre),
            ),
        )
        for index, centre in enumerate(centres, 1)
    )
    assert (
        measurement._resolved_open_arc_groups(
            np.full((25, 33), 6.0),
            np.ones((25, 33), dtype=bool),
            fits,
            ImageBounds(0, 25, 0, 33),
            np.eye(2),
            3.0,
        )
        == ()
    )


def test_compact_core_evidence_requires_an_available_local_model() -> None:
    """Absent models or residual wings cannot override compact protection."""
    fitted = _measure().fits[0][1]
    assert isinstance(fitted, ValidCompactGaussianFit)
    labels = np.zeros((25, 33), dtype=np.int32)
    labels[0, 0] = 1
    arguments = (
        labels,
        1,
        ImageBounds(0, 25, 0, 33),
        labels > 0,
    )
    assert not measurement._fit_core_in_feature(1, (), *arguments)
    assert not measurement._fit_core_in_feature(1, ((1, fitted),), *arguments)
    labels[12, 16] = 1
    assert measurement._fit_core_in_feature(
        1, ((1, fitted),), labels, 1, arguments[2], labels > 0
    )


def test_residual_merge_attribution_does_not_change_membership() -> None:
    """Optional telemetry leaves a connected broad residual's owners intact."""
    yy, xx = np.mgrid[:81, :97]
    signal = 8 * np.exp(-0.5 * (((xx - 48) / 12) ** 2 + ((yy - 40) / 5) ** 2))
    support = signal >= 3
    labels = np.where(support, np.where(xx < 48, 1, 2), 0)
    beam = BeamShapePixels(4.0, 3.0, 0.0)
    arguments = (
        signal,
        np.ones(signal.shape),
        np.ones(signal.shape, dtype=bool),
        labels,
        (),
        (),
        support,
        build_residual_atrous_plan(beam, noise_correlation=beam),
        0.5,
        5.0,
        3.0,
        7,
        signal.size,
    )
    evidence: list[measurement.ComponentGroupingEvidence] = []
    baseline = measurement._extended_residual_groups(
        *arguments, evidence=evidence
    )
    assert baseline == (frozenset((1, 2)),)
    assert len(evidence) == 1
    assert evidence[0].reason == "persistent-residual"
    assert evidence[0].component_labels == frozenset((1, 2))
    assert evidence[0].scale_ids
    assert measurement._extended_residual_groups(*arguments) == baseline


def test_all_invalid_parent_defers_without_fabricating_measurement() -> None:
    result = _measure(valid=np.zeros((25, 33), dtype=np.bool_))
    assert result.fits == result.compact_groups == ()
    assert result.deferred_parent_count == 1


def test_morphology_work_limits_apply_before_context_model_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded native fit cannot open an unbounded reconciliation context."""
    fitted = _measure().fits[0][1]
    labels = np.zeros((25, 33), dtype=np.int32)
    labels[12, 12:15] = (1, 2, 3)
    fits = tuple((index, fitted) for index in (1, 2, 3))
    beam = BeamShapePixels(4.0, 3.0, 0.0)
    plan = build_residual_atrous_plan(beam, noise_correlation=beam)

    def forbidden(*_args: object, **_kwargs: object):
        raise AssertionError(
            "oversized morphology context must not be evaluated"
        )

    monkeypatch.setattr(measurement, "_resolved_emission_loop", forbidden)
    monkeypatch.setattr(measurement, "_model_and_groups", forbidden)
    assert (
        measurement._cross_parent_loop_groups(
            labels.astype(float),
            np.ones(labels.shape),
            np.ones(labels.shape, dtype=bool),
            labels,
            fits,
            WCS(naxis=2),
            RestoringBeam(4 / 3600, 3 / 3600, 0.0),
            plan,
            3.0,
            0.5,
            1,
            measurement_support=labels > 0,
        )
        == ()
    )
    assert (
        measurement._extended_residual_groups(
            labels.astype(float),
            np.ones(labels.shape),
            np.ones(labels.shape, dtype=bool),
            labels,
            fits,
            (),
            labels > 0,
            plan,
            0.5,
            5.0,
            3.0,
            7,
            1,
        )
        == ()
    )
