# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Rapthor's retained/rejected decisions under Hebog and PyBDSF masks."""

from __future__ import annotations

import json
import math
from dataclasses import astuple
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from astropy import units
from astropy.io import fits
from astropy.table import Table
from pydantic import ValidationError
from scipy import ndimage

from hebog.adapters.rapthor_catalogue import write_rapthor_catalogue_fits
from hebog.data_models import (
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.validation.rapthor_agreement import (
    ALL_COMPONENTS,
    RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES,
    RAPTHOR_MAXIMUM_SIZE_DEGREES,
    SAFETY_STRATA,
    CatalogueCutCounts,
    ComponentPixels,
    CutCatalogue,
    DecisionCounts,
    GateOutcome,
    StratumRules,
    WeightedAgreement,
    compare_catalogue_cuts,
    compare_decisions,
    component_strata,
    emission_pixels,
    gate_outcome,
    hebog_cut_catalogue,
    load_agreement_configuration,
    pybdsf_cut_catalogue,
    rapthor_profile,
    weighted_agreement,
)

_ROOT = Path(__file__).parents[3]
_CONFIGURATION = _ROOT / "config/checks/rapthor-agreement.json"
_ARCSECOND = 1.0 / 3600.0


def _pixels(*rows_columns: tuple[int, int]) -> ComponentPixels:
    rows, columns = zip(*rows_columns, strict=True)
    return ComponentPixels(
        rows=np.asarray(rows, dtype=np.intp),
        columns=np.asarray(columns, dtype=np.intp),
    )


def test_component_pixels_are_the_pixels_lsmtool_reads() -> None:
    """LSMTool reads ``mask[int(y), int(x)]`` and rejects negative positions.

    Truncation, not rounding, picks the pixel; two components in one
    pixel are one decision; a position just below zero or past the last
    pixel is rejected.
    """
    pixels = ComponentPixels.at_positions(
        [2.9, 2.1, -0.4, 4.99, 5.0, 1.0, np.nan],
        [3.2, 3.9, 1.0, 0.0, 1.0, -0.01, 1.0],
        (4, 5),
    )

    assert pixels.rows.tolist() == [0, 3]
    assert pixels.columns.tolist() == [4, 2]
    assert len(pixels) == 2


def test_kept_components_are_grouped_by_8_connected_islands() -> None:
    """Diagonal neighbours share an island, as LSMTool's labelling has it."""
    mask = np.zeros((6, 6), dtype=bool)
    mask[1, 1] = mask[2, 2] = True
    mask[4, 4] = True
    pixels = _pixels((1, 1), (2, 2), (4, 4), (0, 5))

    kept = pixels.kept_by(mask)
    islands = pixels.islands_in(mask)

    assert kept.tolist() == [True, True, True, False]
    assert islands[0] == islands[1] != islands[2]
    assert islands[3] == 0


def _strata(
    pixels: ComponentPixels,
    *,
    image: np.ndarray | None = None,
    union_mask: np.ndarray | None = None,
    image_kind: str | None = None,
) -> dict[str, np.ndarray]:
    shape = (40, 40)
    return component_strata(
        pixels,
        image=np.ones(shape) if image is None else image,
        reference_rms=np.full(shape, 0.1),
        union_mask=(
            np.zeros(shape, dtype=bool) if union_mask is None else union_mask
        ),
        beam_fwhm_pixels=2.0,
        beam_area_pixels=4.5,
        rules=StratumRules(
            bright_snr=75.0,
            edge_beams=3.0,
            masked_beams=3.0,
            crowded_beams=2.0,
            extended_beam_areas=10.0,
        ),
        image_kind=image_kind,  # pyright: ignore[reportArgumentType]
    )


def test_every_safety_stratum_is_tagged() -> None:
    """Each stratum's rule, at its boundary, in beam FWHM and beam areas.

    The beam is 2 pixels wide and 4.5 pixels in area, so the edge and
    masked strata reach 6 pixels, crowding 4 pixels, and an extended
    island holds more than 45 pixels.
    """
    image = np.ones((40, 40))
    image[20, 20] = 7.5
    image[20, 26] = 7.49
    image[30:, 30:] = np.nan
    union_mask = np.zeros((40, 40), dtype=bool)
    union_mask[10:17, 10:17] = True
    union_mask[18:23, 18:23] = True
    pixels = _pixels(
        (20, 20),  # bright, isolated
        (20, 26),  # just below the bright cut; sparse
        (6, 20),  # six pixels from the top: edge
        (20, 7),  # seven pixels from the left: not edge
        (24, 31),  # six pixels above the blank block: masked
        (13, 13),  # on the 49-pixel island: extended
        (13, 17),  # four pixels from (13, 13): both crowded
    )

    strata = _strata(pixels, image=image, union_mask=union_mask)

    assert set(strata) == set(SAFETY_STRATA)
    assert strata["bright"].tolist() == [1, 0, 0, 0, 0, 0, 0]
    assert strata["edge"].tolist() == [0, 0, 1, 0, 0, 0, 0]
    assert strata["masked"].tolist() == [0, 0, 0, 0, 1, 0, 0]
    assert strata["extended"].tolist() == [0, 0, 0, 0, 0, 1, 0]
    assert strata["crowded"].tolist() == [0, 0, 0, 0, 0, 1, 1]
    assert (strata["sparse"] == ~strata["crowded"]).all()
    assert not strata["true-sky"].any()
    assert not strata["apparent"].any()


def test_an_island_of_the_beam_area_limit_is_not_extended() -> None:
    """Extended means larger than the limit; 45 pixels is not."""
    union_mask = np.zeros((40, 40), dtype=bool)
    union_mask[10:19, 10:15] = True

    strata = _strata(_pixels((12, 12)), union_mask=union_mask)

    assert not strata["extended"].any()


def test_an_empty_population_has_empty_strata() -> None:
    """An image with no fitted Gaussian has nothing to tag."""
    empty = np.zeros(0, dtype=np.intp)

    strata = _strata(ComponentPixels(rows=empty, columns=empty))

    assert all(selection.size == 0 for selection in strata.values())


@pytest.mark.parametrize("kind", ["true-sky", "apparent"])
def test_the_image_kind_tags_every_component(kind: str) -> None:
    """Rapthor's two images are strata of their own."""
    strata = _strata(_pixels((20, 20), (21, 30)), image_kind=kind)

    assert strata[kind].all()
    other = "apparent" if kind == "true-sky" else "true-sky"
    assert not strata[other].any()


def test_a_component_on_a_blank_pixel_is_masked_and_never_bright() -> None:
    """A blanked pixel has no value to compare with the RMS."""
    image = np.ones((40, 40))
    image[20, 20] = np.nan

    strata = _strata(_pixels((20, 20)), image=image)

    assert strata["masked"].tolist() == [True]
    assert strata["bright"].tolist() == [False]


def test_decisions_are_counted_in_both_directions_and_by_grouping() -> None:
    """The candidate merges two islands the reference keeps apart.

    Components A and B are kept by both, but the candidate's one island
    groups them while the reference's two do not; C is kept by the
    reference alone, D by the candidate alone, E by neither, and F by both
    in islands of its own.
    """
    candidate = np.zeros((10, 10), dtype=bool)
    reference = np.zeros((10, 10), dtype=bool)
    candidate[1, 1:4] = True  # A and B joined
    reference[1, 1] = reference[1, 3] = True  # A and B apart
    reference[5, 5] = True  # C
    candidate[7, 1] = True  # D
    candidate[8, 8] = reference[8, 8] = True  # F
    pixels = _pixels((1, 1), (1, 3), (5, 5), (7, 1), (3, 8), (8, 8))
    strata = {"first-two": np.array([1, 1, 0, 0, 0, 0], dtype=bool)}

    counts = compare_decisions(candidate, reference, pixels, strata)

    assert counts[ALL_COMPONENTS] == DecisionCounts(
        components=6,
        both_kept=3,
        candidate_only=1,
        reference_only=1,
        grouped_alike=1,
    )
    assert counts["first-two"] == DecisionCounts(
        components=2, both_kept=2, grouped_alike=0
    )
    assert counts[ALL_COMPONENTS].agreement == pytest.approx(4 / 6)
    assert counts[ALL_COMPONENTS].grouping_agreement == pytest.approx(1 / 3)


def test_decision_counts_pool_and_have_no_agreement_when_empty() -> None:
    """An empty population measures nothing rather than agreeing fully."""
    pooled = DecisionCounts(4, 2, 1, 0, 2) + DecisionCounts(2, 1, 0, 1, 0)

    assert pooled == DecisionCounts(6, 3, 1, 1, 2)
    assert DecisionCounts().agreement is None
    assert DecisionCounts(components=3).grouping_agreement is None


def _counts(**agreements: float) -> dict[str, DecisionCounts]:
    """Return 1,000 components a stratum with the given agreement."""
    counts = {ALL_COMPONENTS: DecisionCounts(components=1000, both_kept=1000)}
    counts |= {
        name: DecisionCounts(
            components=1000,
            both_kept=1000,
            reference_only=round(1000 * (1 - value)),
        )
        for name, value in agreements.items()
    }
    return counts


def test_a_lane_passes_only_when_every_stratum_reaches_the_threshold() -> None:
    """99.5% exactly passes; one stratum below it fails the lane."""
    every = dict.fromkeys(SAFETY_STRATA, 1.0)

    assert gate_outcome(_counts(**every), 0.995) == GateOutcome(
        status="passed", failing_strata=(), empty_strata=()
    )
    assert gate_outcome(_counts(**every | {"edge": 0.995}), 0.995).status == (
        "passed"
    )
    failing = gate_outcome(_counts(**every | {"edge": 0.994}), 0.995)
    assert failing.status == "failed"
    assert failing.failing_strata == ("edge",)


def test_an_unmeasured_stratum_leaves_the_lane_incomplete() -> None:
    """An empty safety stratum cannot pass, but a failure still fails."""
    counts = _counts(**dict.fromkeys(SAFETY_STRATA, 1.0))
    counts["masked"] = DecisionCounts()

    assert gate_outcome(counts, 0.995) == GateOutcome(
        status="incomplete", failing_strata=(), empty_strata=("masked",)
    )
    counts["edge"] = DecisionCounts(components=10, candidate_only=1)
    assert gate_outcome(counts, 0.995).status == "failed"


def test_compact_is_chosen_only_for_a_passing_lane() -> None:
    """Plan task 21: otherwise the Rapthor profile stays ``continuum``."""
    passed = GateOutcome("passed", (), ())

    assert rapthor_profile(passed) == "compact"
    assert rapthor_profile(GateOutcome("failed", ("all",), ())) == "continuum"
    assert rapthor_profile(GateOutcome("incomplete", (), ("bright",))) == (
        "continuum"
    )


def test_emission_pixels_follow_wscleans_threshold_and_auto_mask() -> None:
    """Pixels 1 sigma up are cleaned only in a region with a 5-sigma seed.

    Sigma is the clipped noise of the image, about 1 here: the 8-sigma
    source is cleaned with the noise peaks touching it, the 3-sigma blob
    without a seed is not, and a blank pixel never is.
    """
    generator = np.random.default_rng(20261013)
    image = generator.standard_normal((64, 64))
    image[10, 10] = 8.0
    image[40, 40:42] = 3.0
    image[0, 0] = np.nan

    pixels, weights = emission_pixels(image, floor_sigma=1.0, seed_sigma=5.0)

    found = set(
        zip(pixels.rows.tolist(), pixels.columns.tolist(), strict=True)
    )
    assert (10, 10) in found
    assert not found & {(40, 40), (40, 41), (0, 0)}
    region = np.zeros(image.shape, dtype=bool)
    region[pixels.rows, pixels.columns] = True
    labels, count = cast(
        tuple[np.ndarray, int],
        ndimage.label(region, structure=np.ones((3, 3))),
    )
    assert count == 1
    assert labels[10, 10] == 1
    assert weights.min() >= 0.9
    assert weights[(pixels.rows == 10) & (pixels.columns == 10)] == (
        pytest.approx(8.0, abs=0.1)
    )


def test_an_image_without_valid_noise_has_no_emission_pixels() -> None:
    """A blank or constant image gives no population, not every pixel."""
    for image in (np.full((8, 8), np.nan), np.ones((8, 8))):
        pixels, weights = emission_pixels(
            image, floor_sigma=1.0, seed_sigma=5.0
        )
        assert len(pixels) == 0
        assert weights.size == 0


def test_weighted_agreement_counts_the_flux_both_masks_decide_alike() -> None:
    """Disagreement on a faint pixel costs little flux."""
    candidate = np.array([[True, True, False]])
    reference = np.array([[True, False, False]])
    pixels = _pixels((0, 0), (0, 1), (0, 2))

    measured = weighted_agreement(
        candidate, reference, pixels, np.array([8.0, 1.0, 1.0])
    )

    assert measured == WeightedAgreement(agreeing=9.0, total=10.0)
    assert measured.agreement == pytest.approx(0.9)
    assert (measured + WeightedAgreement(1.0, 2.0)).agreement == pytest.approx(
        10.0 / 12.0
    )
    assert WeightedAgreement().agreement is None


def _catalogue(
    rows: list[tuple[float, float, float, float, bool, float]],
) -> CutCatalogue:
    """Build a catalogue from (RA″, DC_Maj″, E_RA″, E_DEC″, several, Maj″).

    Arcseconds are divided by 3,600 as Rapthor's limits are, so a value at
    a limit is exactly the limit.
    """
    values = np.asarray(
        [(r, d, e, f, m) for r, d, e, f, _, m in rows], dtype=np.float64
    ).reshape(-1, 5)
    degrees = values / 3600.0
    return CutCatalogue(
        right_ascension_degrees=10.0 + degrees[:, 0],
        declination_degrees=np.full(len(rows), 50.0),
        deconvolved_major_degrees=degrees[:, 1],
        right_ascension_error_degrees=degrees[:, 2],
        declination_error_degrees=degrees[:, 3],
        several_components=np.asarray([row[4] for row in rows], dtype=bool),
        fitted_major_degrees=degrees[:, 4],
    )


def test_rapthors_cuts_drop_nan_and_keep_values_below_the_limits() -> None:
    """``DC_Maj < 10″`` and errors ``< 2″``; NaN fails every comparison."""
    catalogue = _catalogue(
        [
            (0, 9.99, 1.99, 1.99, False, 12),
            (100, 10.0, 0.1, 0.1, False, 12),
            (200, 5, 2.0, 0.1, False, 7),
            (300, math.nan, math.nan, math.nan, True, math.nan),
            (400, 0, 0.1, 0.1, False, 63),
        ]
    )

    assert catalogue.astrometry_kept().tolist() == [1, 0, 0, 0, 1]
    assert catalogue.size_kept().tolist() == [1, 0, 1, 0, 1]
    assert catalogue.unresolved_wide_fits().tolist() == [0, 0, 0, 0, 1]
    assert pytest.approx(10 * _ARCSECOND) == RAPTHOR_MAXIMUM_SIZE_DEGREES
    assert pytest.approx(2 * _ARCSECOND) == (
        RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES
    )


def test_catalogue_cuts_count_the_two_effects_of_continuum_rows() -> None:
    """Matched pairs, and the two ways a continuum row changes a cut.

    Pair 1 agrees. Pair 2 is kept by the reference and dropped by the
    candidate, whose source has several components and no error. Pair 3
    is dropped by the reference's 30″ fit and kept by the candidate's
    unresolved row from a 63″ fit. The candidate's fourth source lies 12″
    of right ascension, 7.7″ at declination 50°, from the reference's
    fourth, beyond the 6″ match radius.
    """
    reference = _catalogue(
        [
            (0, 2, 0.1, 0.1, False, 7),
            (100, 3, 0.1, 0.1, False, 8),
            (200, 30, 0.1, 0.1, False, 31),
            (300, 2, 0.1, 0.1, False, 7),
        ]
    )
    candidate = _catalogue(
        [
            (0.5, 2, 0.1, 0.1, False, 7),
            (101, math.nan, math.nan, math.nan, True, math.nan),
            (200, 0, 0.1, 0.1, False, 63),
            (312, 2, 0.1, 0.1, False, 7),
        ]
    )

    counts = compare_catalogue_cuts(
        candidate, reference, match_radius_degrees=6 * _ARCSECOND
    )

    assert counts == CatalogueCutCounts(
        sources=4,
        astrometry_kept=3,
        size_kept=3,
        several_component_sources=1,
        unresolved_wide_fits=1,
        matched=3,
        matched_alike=1,
        reference_kept_candidate_dropped=1,
        dropped_with_several_components=1,
        reference_dropped_candidate_kept=1,
        kept_as_unresolved_wide_fit=1,
    )
    assert counts + counts == CatalogueCutCounts(
        *(2 * value for value in astuple(counts))
    )


def test_catalogue_cuts_of_an_empty_catalogue_match_nothing() -> None:
    """A finder that publishes nothing still reports the other's cuts."""
    reference = _catalogue([(0, 2, 0.1, 0.1, False, 7)])
    empty = _catalogue([])

    assert (
        compare_catalogue_cuts(
            empty, reference, match_radius_degrees=6 * _ARCSECOND
        )
        == CatalogueCutCounts()
    )
    counts = compare_catalogue_cuts(
        reference, empty, match_radius_degrees=6 * _ARCSECOND
    )
    assert (counts.sources, counts.astrometry_kept, counts.matched) == (
        1,
        1,
        0,
    )


def test_pybdsf_rows_are_read_in_degrees_with_several_gaussians_coded_m(
    tmp_path: Path,
) -> None:
    """PyBDSF's ``S_Code`` ``M`` marks a source of several Gaussians."""
    path = tmp_path / "source_catalog.fits"
    Table(
        {
            "RA": [10.0, 10.1] * units.deg,
            "DEC": [50.0, 50.0] * units.deg,
            "E_RA": [1.0, 1.0] * units.arcsec,
            "E_DEC": [0.1, np.nan] * units.arcsec,
            "DC_Maj": [0.0, 12.0] * units.arcsec,
            "Maj": [7.0, 13.0] * units.arcsec,
            "S_Code": ["S", "M"],
        }
    ).write(path)

    catalogue = pybdsf_cut_catalogue(path)

    assert catalogue.several_components.tolist() == [False, True]
    assert catalogue.right_ascension_error_degrees == pytest.approx(
        [_ARCSECOND, _ARCSECOND]
    )
    assert catalogue.astrometry_kept().tolist() == [True, False]
    assert catalogue.fitted_major_degrees == pytest.approx(
        [7 * _ARCSECOND, 13 * _ARCSECOND]
    )


def test_pybdsfs_empty_catalogue_without_columns_has_no_rows(
    tmp_path: Path,
) -> None:
    """PyBDSF writes a table of one placeholder column when it finds none."""
    path = tmp_path / "source_catalog.fits"
    fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.BinTableHDU.from_columns(
                [fits.Column(name="Source_id", format="J", array=[])]
            ),
        ]
    ).writeto(path)

    catalogue = pybdsf_cut_catalogue(path)

    assert len(catalogue) == 0
    assert not catalogue.astrometry_kept().any()


def test_a_pybdsf_column_without_an_angle_unit_is_refused(
    tmp_path: Path,
) -> None:
    """A unitless position could be in any unit; it is not guessed."""
    path = tmp_path / "source_catalog.fits"
    Table(
        {
            "RA": [10.0],
            "DEC": [50.0] * units.deg,
            "E_RA": [1.0] * units.arcsec,
            "E_DEC": [0.1] * units.arcsec,
            "DC_Maj": [0.0] * units.arcsec,
            "Maj": [7.0] * units.arcsec,
            "S_Code": ["S"],
        }
    ).write(path)

    with pytest.raises(units.UnitConversionError):
        pybdsf_cut_catalogue(path)


def _hebog_catalogue() -> SourceCatalogue:
    """Return a two-Gaussian source and an unresolved 63″ fit.

    The second source is a curved filament whose single fit is wide but
    not significantly extended, so it is published unresolved.
    """
    flux = FluxMeasurement(
        peak_flux_jy_per_beam=0.01,
        peak_flux_error_jy_per_beam=0.001,
        integrated_flux_jy=0.02,
        integrated_flux_error_jy=0.002,
        local_rms_jy_per_beam=0.0002,
    )
    spectrum = SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=150e6,
        coefficients=(),
    )

    def position(offset: float, error: float | None) -> SkyPosition:
        return SkyPosition(
            right_ascension_degrees=10.0 + offset,
            declination_degrees=50.0,
            right_ascension_error_degrees=error,
            declination_error_degrees=error,
        )

    def shape(major_arcseconds: float) -> GaussianShape:
        return GaussianShape(
            major_fwhm_degrees=major_arcseconds * _ARCSECOND,
            minor_fwhm_degrees=6 * _ARCSECOND,
            position_angle_degrees=0.0,
            major_fwhm_error_degrees=None,
            minor_fwhm_error_degrees=None,
            position_angle_error_degrees=None,
        )

    def component(name: str, source: str, offset: float) -> GaussianComponent:
        return GaussianComponent(
            gaussian_component_id=name,
            source_id=source,
            island_id=f"island-{source}",
            position=position(offset, 0.1 * _ARCSECOND),
            flux=flux,
            spectral_model=spectrum,
            fitted_shape=shape(7.0),
            deconvolved_shape=None,
            quality_flags=(),
        )

    sources = (
        SourceCandidate(
            source_id="pair",
            island_id="island-pair",
            position=position(0.0, None),
            flux=flux,
            spectral_model=spectrum,
            fitted_shape=None,
            deconvolved_shape=None,
            quality_flags=(),
        ),
        SourceCandidate(
            source_id="filament",
            island_id="island-filament",
            position=position(0.1, 0.1 * _ARCSECOND),
            flux=flux,
            spectral_model=spectrum,
            fitted_shape=shape(63.0),
            deconvolved_shape=None,
            quality_flags=("unresolved",),
        ),
    )
    return SourceCatalogue.create(
        catalogue_id="agreement",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150e6,
        islands=tuple(
            Island(
                island_id=f"island-{source.source_id}",
                pixel_count=40,
                integrated_flux_jy=0.02,
                integrated_flux_error_jy=None,
                local_rms_jy_per_beam=0.0002,
                mean_brightness_jy_per_beam=0.001,
            )
            for source in sources
        ),
        sources=sources,
        gaussian_components=(
            component("pair-1", "pair", -0.0001),
            component("pair-2", "pair", 0.0001),
            component("filament-1", "filament", 0.1),
        ),
    )


def test_hebog_rows_are_read_from_the_view_rapthor_reads(
    tmp_path: Path,
) -> None:
    """The two continuum rows task 21 measures, as Rapthor's cuts see them.

    The two-Gaussian source has no position error, so the astrometry cut
    drops it; the unresolved 63″ fit publishes ``DC_Maj`` 0 and passes.
    """
    catalogue = _hebog_catalogue()
    view = tmp_path / "sector.source_catalog.fits"
    write_rapthor_catalogue_fits(view, catalogue)

    rows = hebog_cut_catalogue(catalogue, view)

    order = [source.source_id for source in catalogue.sources]
    pair, filament = order.index("pair"), order.index("filament")
    assert rows.several_components[[pair, filament]].tolist() == [True, False]
    assert rows.astrometry_kept()[[pair, filament]].tolist() == [False, True]
    assert rows.unresolved_wide_fits()[[pair, filament]].tolist() == [
        False,
        True,
    ]
    assert np.isnan(rows.fitted_major_degrees[pair])


def test_a_view_of_another_catalogue_is_refused(tmp_path: Path) -> None:
    """Rows are paired with sources by order, so the counts must match."""
    catalogue = _hebog_catalogue()
    view = tmp_path / "sector.source_catalog.fits"
    write_rapthor_catalogue_fits(
        view,
        catalogue.model_copy(
            update={
                "sources": catalogue.sources[:1],
                "gaussian_components": catalogue.gaussian_components[:2],
                "islands": catalogue.islands[:1],
            }
        ),
    )

    with pytest.raises(ValueError, match="one row for each"):
        hebog_cut_catalogue(catalogue, view)


def test_the_checked_in_configuration_loads() -> None:
    """Four lanes, the released control, and the real LOFAR additions."""
    configuration = load_agreement_configuration(_CONFIGURATION)

    assert [lane.name for lane in configuration.lanes] == [
        "continuum-estimated",
        "continuum-zero",
        "compact-estimated",
        "compact-zero",
    ]
    assert configuration.agreement_threshold == 0.995
    assert configuration.strata.rules() == StratumRules(
        bright_snr=75.0,
        edge_beams=3.0,
        masked_beams=3.0,
        crowded_beams=2.0,
        extended_beam_areas=10.0,
    )
    assert configuration.control.finder_id == "released-pybdsf"
    assert {case.image_kind for case in configuration.cases} == {
        "true-sky",
        "apparent",
        None,
    }


@pytest.mark.parametrize("duplicated", ["lanes", "cases"])
def test_a_configuration_with_repeated_lanes_or_cases_is_refused(
    tmp_path: Path, duplicated: str
) -> None:
    """A repeated lane or case would count its components twice."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    document[duplicated] = [document[duplicated][0]] * 2
    path = tmp_path / "configuration.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=f"{duplicated} must be unique"):
        load_agreement_configuration(path)


def test_a_configuration_with_an_unknown_field_is_refused(
    tmp_path: Path,
) -> None:
    """A misspelt setting must not be silently ignored."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    document["agreement_treshold"] = 0.9
    path = tmp_path / "configuration.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_agreement_configuration(path)


def test_the_checked_in_configuration_sets_the_truth_measures() -> None:
    """Injection levels around Rapthor's 5-sigma peak and the noise check."""
    truth = load_agreement_configuration(_CONFIGURATION).truth

    assert truth.injection.snr_levels == (3, 4, 5, 6, 7, 10, 20, 50)
    assert truth.injection.per_level == 30
    assert truth.noise.box_beams == 20.0
    assert truth.noise.tolerance == 0.2
    assert truth.real_emission_sigma == 7.0


def test_a_configuration_of_the_first_schema_is_refused(
    tmp_path: Path,
) -> None:
    """A configuration without the truth measures fails, not runs without."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    del document["truth"]
    path = tmp_path / "configuration.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_agreement_configuration(path)


@pytest.mark.parametrize("levels", [[5, 5], [0, 5], []])
def test_injection_levels_must_be_distinct_and_positive(
    tmp_path: Path, levels: list[float]
) -> None:
    """A repeated level would double its sources; a zero level has none."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    document["truth"]["injection"]["snr_levels"] = levels
    path = tmp_path / "configuration.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_agreement_configuration(path)
