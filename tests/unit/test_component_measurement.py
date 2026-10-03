"""Bounded model admission and morphology evidence on analytic pixels."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

import numpy as np
import pytest
from astropy.wcs import WCS

from hebog.algorithms import component_measurement as measurement
from hebog.algorithms.component_measurement import measure_component_models
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    ScaleFilterBankResult,
    ScaleFilterResponse,
    build_residual_atrous_plan,
)
from hebog.config import CompactGaussianFitConfig, CompactMomentConfig
from hebog.data_models.fitting import (
    FailedCompactGaussianFit,
    UnavailableCompactGaussianFit,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import ImageBounds


@pytest.mark.parametrize("residual_value", (-1.0, 0.0, 1.0))
@pytest.mark.parametrize("residual_grouping", (False, True))
@pytest.mark.parametrize("coarsest_scale_silent", (False, True))
def test_persistent_support_uses_filtered_response_domain(
    monkeypatch: pytest.MonkeyPatch,
    residual_value: float,
    residual_grouping: bool,
    coarsest_scale_silent: bool,
) -> None:
    """Filtered features need not contain positive unfiltered residuals.

    Inject the bounded filter result to isolate both measurement callers'
    response/SNR pairing; this is not a physical source-detection fixture.
    Two adjacent scales make the feature persistent, and the grouping
    evidence names only the scales whose adjacent pairs carry it.
    """
    residual = np.full((13, 15), residual_value)
    valid = np.ones(residual.shape, dtype=np.bool_)
    feature = np.zeros_like(residual)
    feature[4:9, 5:10] = 6.0
    responses = tuple(
        ScaleFilterResponse(
            order,
            float(2 ** (order - 1)),
            feature * order * (order < 3 or not coarsest_scale_silent),
            np.full_like(residual, order),
            np.ones_like(residual),
            valid,
        )
        for order in (1, 2, 3)
    )
    bank_result = ScaleFilterBankResult(
        "beam-aware-matched-filter", responses, 0, 0, 0
    )

    def filtered(*_args: object, **_kwargs: object) -> ScaleFilterBankResult:
        return bank_result

    monkeypatch.setattr(measurement, "evaluate_scale_filter_bank", filtered)
    beam = BeamShapePixels(2.0, 1.5, 20.0)
    plan = build_residual_atrous_plan(beam, noise_correlation=beam)
    if residual_grouping:
        labels = np.zeros(residual.shape, dtype=np.int32)
        labels[5, 6] = 1
        labels[7, 8] = 2
        evidence: list[measurement.ComponentGroupingEvidence] = []
        actual = measurement._residual_groups_in_feature(
            residual,
            np.ones_like(residual),
            valid,
            labels,
            feature > 0,
            (),
            frozenset(),
            plan,
            0.5,
            5.0,
            3.0,
            7,
            bounds=ImageBounds(0, residual.shape[0], 0, residual.shape[1]),
            evidence=evidence,
        )
        assert actual == (frozenset((1, 2)),)
        assert evidence[0].reason == "persistent-residual"
        assert evidence[0].scale_ids == (
            (1, 2) if coarsest_scale_silent else (1, 2, 3)
        )
    else:
        actual = measurement._persistent_measurement_support(
            residual, np.ones_like(residual), valid, plan, 0.5, 5.0, 3.0, 7
        )
        np.testing.assert_array_equal(actual, feature > 0)


def _measure(  # noqa: PLR0913
    *,
    component_index: int = 1,
    maximum_bounds_pixels: int = 10000,
    center_xy: tuple[float, float] = (16.0, 12.0),
    valid: np.ndarray | None = None,
    centers: tuple[tuple[float, float], ...] | None = None,
    shape_yx: tuple[int, int] = (25, 33),
    sigma_xy: tuple[float, float] = (2.4, 1.6),
    pixel_support: Literal["bounded-context", "owned-region"] = (
        "bounded-context"
    ),
    unlabelled: np.ndarray | None = None,
) -> measurement.ComponentMeasurements:
    """One original-pixel ellipse with independently supplied unit RMS.

    ``unlabelled`` is added to the image without a detection label.
    """
    yy, xx = np.mgrid[: shape_yx[0], : shape_yx[1]]
    signal = np.zeros(shape_yx) if unlabelled is None else unlabelled.copy()
    labels = np.zeros(shape_yx, dtype=np.int32)
    for index, center in enumerate(centers or (center_xy,), component_index):
        profile = 10 * np.exp(
            -0.5
            * (
                ((xx - center[0]) / sigma_xy[0]) ** 2
                + ((yy - center[1]) / sigma_xy[1]) ** 2
            )
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
        pixel_support=pixel_support,
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


def _planted_feature(
    centre_xy: tuple[float, float], amplitude: float, sigma: float
) -> np.ndarray:
    """One circular Gaussian on the 49 by 81 pixel adequacy fixture."""
    yy, xx = np.mgrid[:49, :81]
    return amplitude * np.exp(
        -0.5 * ((xx - centre_xy[0]) ** 2 + (yy - centre_xy[1]) ** 2) / sigma**2
    )


@pytest.mark.parametrize(
    ("feature_xy", "amplitude", "sigma", "seeded", "touching", "unmodelled"),
    (
        ((27.0, 24.0), -3.5, 3.0, True, True, False),
        ((28.0, 24.0), 2.2, 4.0, False, True, False),
        ((42.0, 24.0), 6.0, 2.0, True, False, False),
        ((27.0, 24.0), 4.5, 3.0, True, True, True),
    ),
    ids=("dip", "unseeded", "apart", "on-support"),
)
def test_unmodelled_emission_is_seeded_positive_and_on_the_model(  # noqa: PLR0913, PLR0917
    feature_xy: tuple[float, float],
    amplitude: float,
    sigma: float,
    seeded: bool,
    touching: bool,
    unmodelled: bool,
) -> None:
    """A residual fails a model only as PyBDSF's residual search would.

    PyBDSF searches its residual for positive wavelet islands seeded at the
    detection threshold and joins each to the islands it overlaps. Each
    residual is one planted feature beside a perfectly modelled source: a
    seeded dip on the source's support, a positive feature on it that no
    matched scale lifts to a seed, and a seeded positive feature apart from
    it leave the model adequate; a seeded positive feature on it does not.
    The residual's own significance and footprint are checked first.
    """
    residual = _planted_feature(feature_xy, amplitude, sigma)
    yy, xx = np.mgrid[:49, :81]
    support = (
        10 * np.exp(-0.5 * (((xx - 20) / 2.4) ** 2 + ((yy - 24) / 1.6) ** 2))
        >= 3
    )
    unit = np.ones_like(residual)
    valid = np.ones(residual.shape, dtype=np.bool_)
    beam = BeamShapePixels(4.0, 3.0, 0.0)
    plan = build_residual_atrous_plan(beam, noise_correlation=beam)
    signed = tuple(
        np.where(np.isfinite(snr), np.sign(amplitude) * snr, 0.0)
        for snr in measurement._matched_snrs(residual, unit, valid, plan, 0.5)
    )
    peak = max(float(snr.max()) for snr in signed)
    assert peak >= 3.0
    assert (peak >= 5.0) is seeded
    assert any(np.any(support & (snr >= 3.0)) for snr in signed) is touching

    actual = measurement._unmodelled_detection(
        residual, unit, valid, 5.0, 3.0, 7, plan, 0.5, valid, support
    )

    assert actual is unmodelled


@pytest.mark.parametrize(
    ("feature_xy", "amplitude", "sigma", "adequate"),
    (((42.0, 24.0), 6.0, 2.0, True), ((27.0, 24.0), 4.5, 3.0, False)),
    ids=("apart", "on-support"),
)
def test_a_fit_parent_is_judged_on_its_own_support(
    feature_xy: tuple[float, float],
    amplitude: float,
    sigma: float,
    adequate: bool,
) -> None:
    """Seeded emission beside a source fails its model only on its support.

    Both features hold a detection-threshold seed. The one apart from the
    source lies inside the parent's read window but off its support, so the
    source keeps its compact group; the one on its support removes it.
    """
    result = _measure(
        center_xy=(20.0, 24.0),
        shape_yx=(49, 81),
        pixel_support="owned-region",
        unlabelled=_planted_feature(feature_xy, amplitude, sigma),
    )

    assert isinstance(result.fits[0][1], ValidCompactGaussianFit)
    assert result.compact_groups == ((frozenset((1,)),) if adequate else ())


@pytest.mark.parametrize("pixel_support", ("owned-region", "bounded-context"))
def test_fallback_adequacy_uses_the_declared_likelihood_domain(
    monkeypatch: pytest.MonkeyPatch, pixel_support: str
) -> None:
    """Outside-domain emission cannot reject a Gaussian component.

    Tag the fitted record as a fallback to isolate admission, then place
    residual emission outside its owned pixels but inside the read halo.
    Public tests separately exercise actual beam model selection.
    """
    captured: list[Any] = []
    original = measurement.fit_compact_gaussian_mixture

    def capture(compact: Any, *args: Any, **kwargs: Any):
        captured.append((compact, args[-1]))
        return original(compact, *args, **kwargs)

    monkeypatch.setattr(measurement, "fit_compact_gaussian_mixture", capture)
    result = _measure()
    fit = result.fits[0][1]
    assert isinstance(fit, ValidCompactGaussianFit)
    compact, config = captured[0]
    residual = compact.physical_residual.copy()
    residual[2:7, 2:7] += 50
    assert not np.any(compact.region_labels[2:7, 2:7])
    compact = replace(compact, physical_residual=residual)
    fit = replace(
        fit,
        diagnostics=replace(
            fit.diagnostics,
            model_identity="beam-constrained",
            fallback_reason="free-model-ill-conditioned",
        ),
    )
    beam = BeamShapePixels(4, 3, 0)
    config = replace(config, pixel_support=pixel_support)
    actual = measurement._admit_fallbacks(
        ((1, fit),),
        compact,
        config,
        build_residual_atrous_plan(beam, noise_correlation=beam),
        0.5,
        5.0,
        3.0,
        7,
    )[0][1]
    if pixel_support == "owned-region":
        assert actual is fit
    else:
        assert isinstance(actual, FailedCompactGaussianFit)
        assert actual.reason == "fit-model-inadequate"


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


@pytest.mark.parametrize(
    ("count", "spacing", "sigma_xy", "centroid_pixels", "size_fraction"),
    (
        (17, 12.0, (2.4, 1.6), 0.002, 0.002),
        (16, 40.0, (10.0, 10.0), 0.15, 0.04),
    ),
)
def test_a_chain_too_large_to_fit_jointly_is_fitted_island_by_island(
    count: int,
    spacing: float,
    sigma_xy: tuple[float, float],
    centroid_pixels: float,
    size_fraction: float,
) -> None:
    """Islands whose fit contexts chain are fitted one by one when needed.

    Seventeen compact islands exceed one joint fit's sixteen components, and
    sixteen islands of about 750 pixels its Jacobian bound. Fitting either
    chain whole would leave every component deferred, so each island is
    fitted alone instead, as PyBDSF fits every island, with the reviewed
    owned-region pixels. An island's fit does not model a neighbouring
    island's wings: the compact end source moves under 0.001 pixels and
    0.11% in size, while the large sources, whose neighbours' wings reach
    half a sigma into an island, move their end source 0.11 pixels and
    change size up to 3.4%. Sources flanked on both sides are exact.
    """
    centers = tuple(
        (spacing + spacing * index, 2.0 * sigma_xy[1] + 12.0)
        for index in range(count)
    )
    result = _measure(
        centers=centers,
        shape_yx=(
            int(4.0 * sigma_xy[1] + 25.0),
            int(spacing * (count + 1)),
        ),
        maximum_bounds_pixels=100_000,
        sigma_xy=sigma_xy,
        pixel_support="owned-region",
    )
    assert len(result.fits) == len(centers)
    assert result.deferred_parent_count == 0
    for (_, fitted), center in zip(result.fits, centers, strict=True):
        assert isinstance(fitted, ValidCompactGaussianFit)
        assert fitted.parameters.centroid_xy == pytest.approx(
            center, abs=centroid_pixels
        )
        assert (
            fitted.parameters.major_sigma_pixels,
            fitted.parameters.minor_sigma_pixels,
        ) == pytest.approx(sigma_xy, rel=size_fraction)


def test_one_island_too_large_to_fit_jointly_remains_unavailable() -> None:
    """An island is the smallest fit parent, so its joint limit still holds."""
    result = _measure(
        centers=tuple((12.0 + 6 * index, 16.0) for index in range(17)),
        shape_yx=(33, 121),
        maximum_bounds_pixels=100_000,
    )
    assert len(result.fits) == 17
    assert all(
        isinstance(fit, UnavailableCompactGaussianFit)
        and fit.reason == "joint-fit-work-limit"
        for _, fit in result.fits
    )


def test_a_parent_is_judged_by_its_direct_pixels_not_its_support() -> None:
    """Measurement support wider than the direct pixels is not fit work.

    The chain's three owners hold 36 support pixels but only 4 direct
    pixels, the centres: 18 parameters by 4 pixels fit within 100 Jacobian
    elements though 648 would not, so the chain stays one parent; with
    every support pixel direct it would split.
    """
    labels = np.zeros((20, 80), dtype=np.int32)
    labels[5:8, 2:5] = 1
    labels[5:8, 12:15] = 2
    labels[16:19, 30:33] = 2
    labels[5:8, 22:25] = 3
    direct = np.zeros_like(labels)
    for y, x in ((6, 3), (6, 13), (17, 31), (6, 23)):
        direct[y, x] = labels[y, x]
    bounds = {
        "context_margin_pixels": 8,
        "read_margin_pixels": 2,
        "maximum_bounds_pixels": 10_000,
        "maximum_jacobian_elements": 100,
    }

    narrow = measurement._bounded_fit_parents(labels, direct, **bounds)
    wide = measurement._bounded_fit_parents(labels, labels, **bounds)

    np.testing.assert_array_equal(
        narrow, measurement._measurement_fit_parents(labels, 8)
    )
    assert (wide[6, 3], wide[6, 13], wide[6, 23]) == (1, 2, 3)


@pytest.mark.parametrize("limit", ("components", "pixels", "window"))
def test_a_fit_parent_too_large_to_fit_jointly_takes_its_islands(
    limit: str,
) -> None:
    """Only a parent one joint fit cannot hold is split, into its islands.

    Three islands chain through their eight-pixel contexts, and owner 2 has a
    second piece joined to them through the owner itself; a separate pair
    chains too. The chain exceeds the limit, by component count or by read
    window, and each of its islands becomes a parent, owner 2's two pieces
    one; the pair stays joined. The chain's three owners and 36 direct
    pixels are 18 parameters and 648 Jacobian elements, the pair's 12 and
    216. Parents keep the joined order.
    """
    labels = np.zeros((20, 80), dtype=np.int32)
    labels[5:8, 2:5] = 1
    labels[5:8, 12:15] = 2
    labels[16:19, 30:33] = 2
    labels[5:8, 22:25] = 3
    labels[14:17, 50:53] = 4
    labels[14:17, 60:63] = 5
    joined = measurement._measurement_fit_parents(labels, 8)
    assert joined[6, 3] == joined[6, 13] == joined[17, 31] == joined[6, 23]
    assert joined[15, 51] == joined[15, 61] != joined[6, 3]
    bounds = {
        "components": {"maximum_parameters": 12},
        "pixels": {"maximum_jacobian_elements": 500},
        "window": {"maximum_bounds_pixels": 500},
    }[limit]

    parents = measurement._bounded_fit_parents(
        labels,
        labels,
        context_margin_pixels=8,
        read_margin_pixels=2,
        **{"maximum_bounds_pixels": 10_000, **bounds},
    )

    assert (parents[6, 3], parents[6, 13], parents[6, 23]) == (1, 2, 3)
    assert parents[17, 31] == parents[6, 13]
    assert parents[15, 51] == parents[15, 61] == 4
    assert np.all(parents[labels == 0] == 0)
    np.testing.assert_array_equal(
        measurement._bounded_fit_parents(
            labels,
            labels,
            context_margin_pixels=8,
            read_margin_pixels=2,
            maximum_bounds_pixels=10_000,
        ),
        joined,
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
        measurement, "_loop_groups_in_feature", extended_proposal
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
        support,
        (),
        frozenset(),
        build_residual_atrous_plan(beam, noise_correlation=beam),
        0.5,
        5.0,
        3.0,
        7,
    )
    bounds = ImageBounds(0, signal.shape[0], 0, signal.shape[1])
    evidence: list[measurement.ComponentGroupingEvidence] = []
    baseline = measurement._residual_groups_in_feature(
        *arguments, bounds=bounds, evidence=evidence
    )
    assert baseline == (frozenset((1, 2)),)
    assert len(evidence) == 1
    assert evidence[0].reason == "persistent-residual"
    assert evidence[0].component_labels == frozenset((1, 2))
    assert evidence[0].scale_ids
    repeated: list[measurement.ComponentGroupingEvidence] = []
    assert (
        measurement._residual_groups_in_feature(
            *arguments, bounds=bounds, evidence=repeated
        )
        == baseline
    )
    assert repeated == evidence


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
        measurement.support_feature_window(
            ImageBounds(12, 13, 12, 15),
            margin=measurement.support_feature_margin_pixels(plan),
            image_shape_yx=labels.shape,
            maximum_bounds_pixels=1,
        )
        is None
    )
    assert (
        measurement._whole_plane_feature_groups(
            labels.astype(float),
            np.ones(labels.shape),
            np.ones(labels.shape, dtype=bool),
            labels,
            labels > 0,
            fits,
            frozenset(),
            WCS(naxis=2),
            RestoringBeam(4 / 3600, 3 / 3600, 0.0),
            plan,
            detection_sigma=5.0,
            island_sigma=3.0,
            minimum_pixels=7,
            maximum_bounds_pixels=1,
            minimum_support_fraction=0.5,
        )
        == ()
    )
