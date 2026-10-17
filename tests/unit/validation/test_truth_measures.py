"""Each finder's correctness, measured beside its agreement with PyBDSF."""

from __future__ import annotations

import math

import numpy as np
import pytest

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.rapthor_agreement import ComponentPixels
from hebog.validation.truth_measures import (
    EmissionRecall,
    InjectedSources,
    InjectionOutcome,
    MaskIslands,
    NoiseComparison,
    RealEmissionDecisions,
    compare_noise,
    emission_recall,
    ideal_mask,
    inject_point_sources,
    injected_recovery,
    mask_islands,
    negative_pixel_noise,
    plan_injection,
    real_emission_decisions,
    recovery_by_level,
    significant_emission,
)

_ROUND_BEAM = BeamShapePixels(
    major_fwhm_pixels=4.0, minor_fwhm_pixels=4.0, position_angle_degrees=0.0
)


def _uniform(shape: tuple[int, int], value: float) -> np.ndarray:
    return np.full(shape, value, dtype=np.float64)


def test_the_ideal_mask_keeps_islands_seeded_at_the_peak_threshold() -> None:
    """An island counts only when it reaches ``threshpix`` somewhere.

    Both islands reach ``threshisl``; only the left one holds a pixel at
    ``threshpix``. The diagonal neighbour joins its island, as PyBDSF's and
    LSMTool's 8-connected islands do.
    """
    emission = np.zeros((6, 8))
    emission[1, 1:3] = (6.0, 3.5)
    emission[2, 3] = 3.2
    emission[4, 5:7] = (4.0, 3.1)

    mask = ideal_mask(
        emission, _uniform((6, 8), 1.0), threshisl=3, threshpix=5
    )

    expected = np.zeros((6, 8), dtype=np.bool_)
    expected[1, 1:3] = True
    expected[2, 3] = True
    np.testing.assert_array_equal(mask, expected)


def test_the_ideal_mask_scales_with_the_local_noise() -> None:
    """The same emission is an island where the noise is low, not high."""
    emission = np.zeros((3, 6))
    emission[1, 1] = emission[1, 4] = 6.0
    noise = np.ones((3, 6))
    noise[:, 3:] = 2.0

    mask = ideal_mask(emission, noise, threshisl=3, threshpix=5)

    assert mask[1, 1] and not mask[1, 4]


def test_blank_or_unmeasured_pixels_are_never_ideal() -> None:
    """NaN emission and non-positive or NaN noise leave a pixel out."""
    emission = np.full((1, 4), 10.0)
    emission[0, 0] = np.nan
    noise = np.array([[1.0, 0.0, np.nan, 1.0]])

    mask = ideal_mask(emission, noise, threshisl=3, threshpix=5)

    np.testing.assert_array_equal(mask, [[False, False, False, True]])


def test_emission_recall_counts_pixels_flux_and_masking_off_emission() -> None:
    """Recall covers the ideal pixels; off-emission is below one sigma."""
    emission = np.array([[6.0, 4.0, 0.5, 0.0], [0.0, 0.0, 0.0, np.nan]])
    noise = np.ones((2, 4))
    ideal = emission >= 3
    mask = np.array([[True, False, True, True], [False, False, False, True]])

    recall = emission_recall(mask, ideal=ideal, emission=emission, noise=noise)

    assert recall == EmissionRecall(
        ideal_pixels=2,
        covered_pixels=1,
        ideal_flux=10.0,
        covered_flux=6.0,
        mask_pixels=3,
        off_emission_pixels=2,
    )
    assert recall.recall == 0.5
    assert recall.flux_recall == 0.6
    assert recall.off_emission_fraction == pytest.approx(2 / 3)


def test_emission_recall_pools_and_is_unmeasured_without_emission() -> None:
    """Pooling sums every count; an empty population has no ratios."""
    first = EmissionRecall(2, 1, 10.0, 6.0, 3, 1)
    second = EmissionRecall(4, 4, 8.0, 8.0, 5, 0)

    assert first + second == EmissionRecall(6, 5, 18.0, 14.0, 8, 1)
    empty = EmissionRecall()
    assert empty.recall is None
    assert empty.flux_recall is None
    assert empty.off_emission_fraction is None


def test_negative_pixel_noise_is_the_rms_of_each_boxs_negative_pixels() -> (
    None
):
    """Positive pixels, which sources can raise, play no part.

    The left box's negative pixels are -1 and -3, an RMS of sqrt(5); the
    right box has one negative pixel, too few, so it is unmeasured. The
    shape is kept although the boxes do not tile the width.
    """
    image = np.array(
        [[-1.0, 2.0, -2.0, 9.0, 9.0], [-3.0, 50.0, 4.0, 1.0, np.nan]]
    )

    noise = negative_pixel_noise(image, box_pixels=2, minimum_pixels=2)

    assert noise.shape == image.shape
    np.testing.assert_allclose(noise[:, :2], math.sqrt(5.0))
    assert np.all(np.isnan(noise[:, 2:]))


def test_negative_pixel_noise_recovers_gaussian_noise_under_sources() -> None:
    """Faint positive sources leave the estimate at the noise."""
    generator = np.random.default_rng(76)
    image = generator.normal(0.0, 2.0, (256, 256))
    image[::16, ::16] += 6.0

    noise = negative_pixel_noise(image, box_pixels=128, minimum_pixels=100)

    np.testing.assert_allclose(noise, 2.0, rtol=0.05)


def test_noise_comparison_counts_inflated_and_deflated_pixels() -> None:
    """Only pixels where both maps are finite and positive are compared."""
    rms = np.array([[1.0, 1.3, 0.7, 2.0, np.nan, 1.0]])
    noise = np.array([[1.0, 1.0, 1.0, 1.0, 1.0, 0.0]])

    comparison = compare_noise(rms, noise, tolerance=0.2)

    assert comparison.pixels == 4
    assert comparison.inflated == 2
    assert comparison.deflated == 1
    assert comparison.inflated_fraction == 0.5
    assert comparison.deflated_fraction == 0.25
    assert comparison.geometric_mean_ratio == pytest.approx(
        (1.0 * 1.3 * 0.7 * 2.0) ** 0.25
    )


def test_noise_comparison_at_components_and_pooled() -> None:
    """Component pixels select the decisions' pixels; pooling sums them."""
    rms = np.array([[1.0, 2.0], [4.0, 1.0]])
    noise = np.ones((2, 2))
    components = ComponentPixels(
        rows=np.array([0, 1], dtype=np.intp),
        columns=np.array([1, 0], dtype=np.intp),
    )

    at_components = compare_noise(rms, noise, tolerance=0.2, pixels=components)

    assert (at_components.pixels, at_components.inflated) == (2, 2)
    pooled = at_components + compare_noise(rms, noise, tolerance=0.2)
    assert pooled.pixels == 6
    assert pooled.geometric_mean_ratio == pytest.approx(
        (2.0 * 4.0 * 1.0 * 2.0 * 4.0 * 1.0) ** (1 / 6)
    )
    assert NoiseComparison().geometric_mean_ratio is None
    assert NoiseComparison().inflated_fraction is None


def test_an_injected_point_source_has_the_beams_shape_and_flux() -> None:
    """A beam-shaped source of peak A Jy/beam integrates to A beam areas.

    The original image is left unchanged and blank pixels stay blank.
    """
    image = np.zeros((41, 41))
    image[0, 0] = np.nan
    sources = InjectedSources(
        x=np.array([20.0]),
        y=np.array([20.0]),
        snr=np.array([10.0]),
        peak_jy_per_beam=np.array([3.0]),
    )

    injected = inject_point_sources(image, sources, _ROUND_BEAM)

    assert np.count_nonzero(image[1:, 1:]) == 0
    assert np.isnan(injected[0, 0])
    assert injected[20, 20] == pytest.approx(3.0)
    sigma = 4.0 / (2 * math.sqrt(2 * math.log(2)))
    assert np.nansum(injected) == pytest.approx(
        3.0 * 2 * math.pi * sigma**2, rel=1e-3
    )


def test_an_injected_source_lies_along_the_beams_major_axis() -> None:
    """The angle runs counter-clockwise from +x, as Hebog's pixel beam."""
    beam = BeamShapePixels(
        major_fwhm_pixels=8.0,
        minor_fwhm_pixels=2.0,
        position_angle_degrees=90.0,
    )
    sources = InjectedSources(
        x=np.array([15.0]),
        y=np.array([15.0]),
        snr=np.array([5.0]),
        peak_jy_per_beam=np.array([1.0]),
    )

    injected = inject_point_sources(np.zeros((31, 31)), sources, beam)

    assert injected[19, 15] == pytest.approx(0.5)
    assert injected[15, 16] == pytest.approx(0.5)


def test_injection_avoids_blanks_edges_and_existing_emission() -> None:
    """Sites keep clear of blank pixels, the border and emission.

    The noise is one everywhere; a 4-sigma source and a blank square each
    exclude their surroundings, and no site lies within the margin.
    """
    image = np.zeros((200, 200))
    image[100, 100] = 4.0
    image[20:40, 150:170] = np.nan
    noise = np.ones_like(image)

    sources = plan_injection(
        image,
        noise,
        beam_fwhm_pixels=4.0,
        snr_levels=(5.0, 10.0),
        per_level=1000,
        spacing_beams=5.0,
        margin_beams=3.0,
        clear_beams=2.0,
        clear_sigma=3.0,
        seed=1,
    )

    assert len(sources) > 20
    assert np.all((sources.x >= 12) & (sources.x <= 187))
    assert np.all((sources.y >= 12) & (sources.y <= 187))
    assert not np.any(np.hypot(sources.x - 100, sources.y - 100) < 8)
    # Sites are tested at their nearest pixel, half a pixel from the site.
    assert not np.any(
        (sources.x > 141.5)
        & (sources.x < 177.5)
        & (sources.y > 11.5)
        & (sources.y < 47.5)
    )
    separations = np.hypot(
        sources.x[:, None] - sources.x[None, :],
        sources.y[:, None] - sources.y[None, :],
    )
    np.fill_diagonal(separations, np.inf)
    assert separations.min() >= 0.5 * 5.0 * 4.0


def test_injection_assigns_levels_in_turn_and_is_reproducible() -> None:
    """Each level gets as many sources; the peak is SNR times the noise."""
    image = np.zeros((300, 300))
    noise = np.full_like(image, 0.5)

    def planned(seed: int) -> InjectedSources:
        return plan_injection(
            image,
            noise,
            beam_fwhm_pixels=4.0,
            snr_levels=(3.0, 5.0, 8.0),
            per_level=4,
            spacing_beams=5.0,
            margin_beams=2.0,
            clear_beams=2.0,
            clear_sigma=3.0,
            seed=seed,
        )

    first = planned(7)

    assert len(first) == 12
    np.testing.assert_array_equal(first.x, planned(7).x)
    assert sorted(first.snr.tolist()) == [3.0] * 4 + [5.0] * 4 + [8.0] * 4
    np.testing.assert_allclose(first.peak_jy_per_beam, 0.5 * first.snr)
    assert not np.array_equal(first.x, planned(8).x)


def test_too_few_sites_leave_every_level_short_alike() -> None:
    """Levels stay balanced when the image cannot hold every source."""
    sources = plan_injection(
        np.zeros((60, 60)),
        np.ones((60, 60)),
        beam_fwhm_pixels=4.0,
        snr_levels=(5.0, 10.0),
        per_level=50,
        spacing_beams=3.0,
        margin_beams=1.0,
        clear_beams=1.0,
        clear_sigma=3.0,
        seed=3,
    )

    counts = [int(np.sum(sources.snr == level)) for level in (5.0, 10.0)]
    assert counts[0] == counts[1] > 0


def test_recovery_reads_the_mask_and_matches_the_catalogue() -> None:
    """The mask is read as LSMTool does; a match must lie within the radius.

    The first source is kept and matched to the nearer of two entries; the
    second is neither kept nor matched, because its entry is too far.
    """
    sources = InjectedSources(
        x=np.array([2.7, 10.0]),
        y=np.array([3.9, 10.0]),
        snr=np.array([5.0, 10.0]),
        peak_jy_per_beam=np.array([2.0, 4.0]),
    )
    mask = np.zeros((20, 20), dtype=np.bool_)
    mask[3, 2] = True

    outcome = injected_recovery(
        sources,
        mask=mask,
        catalogue_x=np.array([3.0, 4.5, 12.5]),
        catalogue_y=np.array([4.0, 4.0, 10.0]),
        catalogue_flux=np.array([2.2, 9.0, 4.0]),
        match_radius_pixels=2.0,
    )

    np.testing.assert_array_equal(outcome.kept, [True, False])
    np.testing.assert_array_equal(outcome.matched, [True, False])
    np.testing.assert_allclose(outcome.flux_ratio, [1.1, np.nan])


def test_recovery_against_an_empty_catalogue_matches_nothing() -> None:
    """A finder that publishes nothing recovers no source."""
    sources = InjectedSources(
        x=np.array([1.0]),
        y=np.array([1.0]),
        snr=np.array([5.0]),
        peak_jy_per_beam=np.array([1.0]),
    )

    outcome = injected_recovery(
        sources,
        mask=np.zeros((3, 3), dtype=np.bool_),
        catalogue_x=np.zeros(0),
        catalogue_y=np.zeros(0),
        catalogue_flux=np.zeros(0),
        match_radius_pixels=2.0,
    )

    assert not outcome.matched.any()
    assert np.isnan(outcome.flux_ratio).all()


def test_recovery_is_summarised_by_level_over_several_images() -> None:
    """Counts sum over images; the flux ratio is the median of the matched."""
    first = InjectionOutcome(
        snr=np.array([5.0, 5.0, 10.0]),
        kept=np.array([True, False, True]),
        matched=np.array([True, False, True]),
        flux_ratio=np.array([0.8, np.nan, 1.0]),
    )
    second = InjectionOutcome(
        snr=np.array([5.0, 10.0]),
        kept=np.array([True, True]),
        matched=np.array([True, False]),
        flux_ratio=np.array([1.2, np.nan]),
    )

    levels = recovery_by_level([first, second])

    assert list(levels) == [5.0, 10.0]
    assert levels[5.0].injected == 3
    assert levels[5.0].kept == 2
    assert levels[5.0].matched == 2
    assert levels[5.0].median_flux_ratio == pytest.approx(1.0)
    assert levels[10.0].kept_fraction == 1.0
    assert levels[10.0].matched_fraction == 0.5
    assert levels[10.0].median_flux_ratio == pytest.approx(1.0)


def test_a_level_without_matches_has_no_flux_ratio() -> None:
    """Nothing matched means nothing to measure the flux of."""
    outcome = InjectionOutcome(
        snr=np.array([3.0]),
        kept=np.array([False]),
        matched=np.array([False]),
        flux_ratio=np.array([np.nan]),
    )

    level = recovery_by_level([outcome])[3.0]

    assert level.median_flux_ratio is None
    assert level.kept_fraction == 0.0


def test_mask_islands_are_8_connected_and_measured_in_pixels() -> None:
    """Every island of a negated image's mask is a false detection."""
    mask = np.zeros((5, 5), dtype=np.bool_)
    mask[0, 0] = mask[1, 1] = True
    mask[3, 3:5] = True

    assert mask_islands(mask) == MaskIslands(islands=2, pixels=4)
    assert mask_islands(mask) + MaskIslands(1, 3) == MaskIslands(3, 7)


def test_real_emission_is_a_significant_pixel_or_the_ideal_mask() -> None:
    """A component is real where the image reaches the threshold."""
    image = np.array([[6.0, 4.0, np.nan, 10.0]])
    noise = np.array([[1.0, 1.0, 1.0, np.nan]])
    pixels = ComponentPixels(
        rows=np.zeros(4, dtype=np.intp),
        columns=np.arange(4, dtype=np.intp),
    )

    real = significant_emission(
        pixels, image=image, noise=noise, threshold_sigma=5.0
    )

    np.testing.assert_array_equal(real, [True, False, False, False])


def test_disagreements_are_split_by_whether_they_are_real() -> None:
    """Lost real emission is counted against the real components kept.

    The reference keeps three real components and one noise component;
    the candidate loses one real and the noise one, and gains one real
    component the reference misses.
    """
    pixels = ComponentPixels(
        rows=np.zeros(6, dtype=np.intp),
        columns=np.arange(6, dtype=np.intp),
    )
    reference = np.array([[True, True, True, True, False, False]])
    candidate = np.array([[True, True, False, False, True, False]])
    real = np.array([True, True, True, False, True, False])
    strata = {"bright": np.array([True, False, True, False, False, False])}

    decisions = real_emission_decisions(
        candidate, reference, pixels, strata, real=real
    )

    assert decisions["all"] == RealEmissionDecisions(
        reference_kept_real=3,
        lost_real=1,
        reference_only=2,
        candidate_kept_real=3,
        gained_real=1,
        candidate_only=1,
    )
    assert decisions["all"].lost_real_fraction == pytest.approx(1 / 3)
    assert decisions["all"].gained_real_fraction == pytest.approx(1 / 3)
    assert decisions["bright"].lost_real == 1
    assert decisions["bright"].reference_kept_real == 2


def test_real_emission_decisions_pool_and_are_unmeasured_when_empty() -> None:
    """Pooling sums counts; no real components kept means no fraction."""
    first = RealEmissionDecisions(3, 1, 2, 3, 1, 1)

    assert first + first == RealEmissionDecisions(6, 2, 4, 6, 2, 2)
    assert RealEmissionDecisions().lost_real_fraction is None
    assert RealEmissionDecisions().gained_real_fraction is None
