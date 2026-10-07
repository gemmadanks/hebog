# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""The public finder's products against both frozen PyBDSF references.

``find_sources`` analyses the frozen 256-pixel compact field once under each
profile, and its catalogue, RMS map and mask are each compared with released
PyBDSF 1.14.1 and with pinned ``master`` (``tests/data/README.md``). Every
comparison is like for like:

- published sources against the reference's sources, for association,
  position, flux and the fitted model: a source of one Gaussian publishes
  that Gaussian's fit, as the reference does, and both define a source's
  integrated flux as the sum of its fitted Gaussians;
- published Gaussian components against the reference's source rows, for the
  fitted model: every reference source is a single Gaussian (``S_Code`` S),
  so its row is that Gaussian's fit;
- the RMS map on the pixels outside the reference mask; and
- the mask pixel by pixel and island by island.

The limits are the reviewed compact-reference gates of Phases 3 and 4 in
``config/contracts``, which for position and flux are also the plan's isolated
SNR >= 10 targets, and the plan's source-free RMS target. Two differences
are by design: the continuum RMS tail and the mask's extent. Each has its
own bounds below, the values measured on 5 October 2026 (``LOG.md``, task
49) widened by the quick science check's regression tolerance of 0.02 and
rounded outward.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from scipy import ndimage

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.data_models.catalogues import (
    GaussianComponent,
    GaussianShape,
    SourceCandidate,
    SourceCatalogue,
)
from hebog.executors import SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.validation.comparison import (
    CatalogueComparisonReport,
    CatalogueEllipse,
    CatalogueOutlierThresholds,
    CatalogueSource,
    compare_catalogues,
    compare_island_labels,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.contracts import (
    PhaseFourCatalogueGate,
    load_phase_four_scientific_gates,
    load_phase_three_scientific_gates,
)
from hebog.validation.products import (
    load_fits_plane,
    load_mask_plane,
    load_pybdsf_catalogue,
)

pytestmark = pytest.mark.equivalence

_ROOT = Path(__file__).parents[2]
_REFERENCE_ROOT = _ROOT / "tests/data/pybdsf/pybdsf-compact-reference-256"
_REFERENCES = ("release", "master")
_BEAM_FWHM_DEGREES = 0.001111111111111111
_MAXIMUM_SEPARATION_BEAMS = 0.5
_CATALOGUE_GATE = load_phase_four_scientific_gates(
    _ROOT / "config/contracts/phase-4-scientific-gates.json"
).compact_reference
_MASK_GATE = load_phase_three_scientific_gates(
    _ROOT / "config/contracts/phase-3-scientific-gates.json"
).compact_reference
_OUTLIERS = load_phase_four_scientific_gates(
    _ROOT / "config/contracts/phase-4-scientific-gates.json"
).catastrophic_outlier
# The plan's source-free RMS-map target, median and 95th percentile.
_RMS_MEDIAN = 0.02
_RMS_PERCENTILE_95 = 0.05

# Known differences, each the 5 October measurement plus 0.02. Continuum
# noise is refined on 35-pixel windows, which scatter more than PyBDSF's
# 150-pixel box: a 95th percentile of 5.5% against 5%.
_CONTINUUM_RMS_PERCENTILE_95 = 0.075
# The mask is publication support, which the boundary rule trims of sparse
# pixels below 6 sigma: it holds 92.7% (continuum) and 91.6% (compact) of the
# reference island pixels, an IoU of 0.922 and 0.916, against 0.99 and 0.98;
# the matched islands' IoU has a median of 0.909 and a minimum of 0.857, under
# both profiles, against 0.99 and 0.95.
_MASK_RECALL = 0.89
_MASK_INTERSECTION_OVER_UNION = 0.89
_ISLAND_MEDIAN_INTERSECTION_OVER_UNION = 0.88
_ISLAND_MINIMUM_INTERSECTION_OVER_UNION = 0.83


@dataclass(frozen=True, slots=True)
class _Published:
    """The three products one public run published, as read back."""

    profile: Literal["continuum", "compact"]
    catalogue: SourceCatalogue
    rms: npt.NDArray[np.float64]
    mask: npt.NDArray[np.bool_]


@pytest.fixture(scope="module", params=("continuum", "compact"))
def published(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> _Published:
    """Run the public finder once on the frozen input under one profile."""
    profile = cast(Literal["continuum", "compact"], request.param)
    result = hebog.find_sources(
        SourceFinderRequest(
            _REFERENCE_ROOT / "input.fits",
            tmp_path_factory.mktemp(profile) / "products",
            f"frozen-reference-{profile}",
        ),
        SourceFinderConfig(5.0, 3.0, 7, profile=profile),
        SerialExecutor(),
    )
    assert result.source_count == result.gaussian_component_count == 3
    assert result.island_count == 3
    return _Published(
        profile=profile,
        catalogue=read_catalogue_fits_product(result.catalogue),
        rms=load_fits_plane(result.rms_path),
        mask=load_mask_plane(result.mask_path),
    )


def _ellipse(shape: GaussianShape | None) -> CatalogueEllipse | None:
    """Translate one published ellipse to the comparison model."""
    if shape is None:
        return None
    return CatalogueEllipse(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=shape.position_angle_degrees,
        major_fwhm_error_degrees=shape.major_fwhm_error_degrees,
        minor_fwhm_error_degrees=shape.minor_fwhm_error_degrees,
        position_angle_error_degrees=shape.position_angle_error_degrees,
    )


def _comparison_rows(
    catalogue: SourceCatalogue, level: Literal["sources", "components"]
) -> tuple[CatalogueSource, ...]:
    """Project published sources or components onto the comparison model.

    A source counts its own Gaussian components; a component is one.
    """
    components_per_source = Counter(
        component.source_id for component in catalogue.gaussian_components
    )
    rows: tuple[SourceCandidate, ...] | tuple[GaussianComponent, ...] = (
        catalogue.sources
        if level == "sources"
        else catalogue.gaussian_components
    )
    return tuple(
        CatalogueSource(
            identifier=(
                row.gaussian_component_id
                if isinstance(row, GaussianComponent)
                else row.source_id
            ),
            right_ascension_degrees=row.position.right_ascension_degrees,
            declination_degrees=row.position.declination_degrees,
            peak_flux_jy_per_beam=row.flux.peak_flux_jy_per_beam,
            integrated_flux_jy=row.flux.integrated_flux_jy,
            right_ascension_error_degrees=(
                row.position.right_ascension_error_degrees
            ),
            declination_error_degrees=row.position.declination_error_degrees,
            peak_flux_error_jy_per_beam=row.flux.peak_flux_error_jy_per_beam,
            integrated_flux_error_jy=row.flux.integrated_flux_error_jy,
            fitted_shape=_ellipse(row.fitted_shape),
            deconvolved_shape=_ellipse(row.deconvolved_shape),
            deconvolved_major_fwhm_degrees=row.deconvolved_major_fwhm_degrees,
            deconvolution_status=(
                "resolved"
                if row.deconvolved_shape is not None
                else "major-axis-only"
                if row.deconvolved_major_fwhm_degrees is not None
                else "unresolved"
                if "unresolved" in row.quality_flags
                else "unavailable"
            ),
            island_identifier=row.island_id,
            component_count=(
                1
                if isinstance(row, GaussianComponent)
                else components_per_source[row.source_id]
            ),
            quality_flags=row.quality_flags,
        )
        for row in rows
    )


def _compare(
    reference: str,
    catalogue: SourceCatalogue,
    level: Literal["sources", "components"],
) -> CatalogueComparisonReport:
    """Match published rows with one reference's sources."""
    return compare_catalogues(
        load_pybdsf_catalogue(
            _REFERENCE_ROOT / reference / "source_catalog.fits"
        ),
        _comparison_rows(catalogue, level),
        beam_fwhm_degrees=_BEAM_FWHM_DEGREES,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=_OUTLIERS.position_beams,
            peak_flux_fractional_difference=(
                _OUTLIERS.peak_flux_fractional_difference
            ),
            integrated_flux_fractional_difference=(
                _OUTLIERS.integrated_flux_fractional_difference
            ),
            fitted_axis_fractional_difference=(
                _OUTLIERS.fitted_axis_fractional_difference
            ),
            deconvolved_axis_fractional_difference=(
                _OUTLIERS.deconvolved_axis_fractional_difference
            ),
        ),
        position_angle_minimum_axis_ratio=1.1,
    )


def _require_association(
    report: CatalogueComparisonReport, gate: PhaseFourCatalogueGate
) -> None:
    """Every reference row is matched once, on the same island grouping."""
    assert report.reference_count == report.candidate_count == 3
    assert report.completeness >= gate.minimum_completeness
    assert report.reliability >= gate.minimum_reliability
    assert report.component_count_agreement_fraction == 1.0
    association = report.association
    assert association.precision >= gate.minimum_association_pair_precision
    assert association.recall >= gate.minimum_association_pair_recall
    assert association.identity_availability_fraction is not None
    assert (
        association.identity_availability_fraction
        >= gate.minimum_association_identity_availability
    )


def _require_position_and_flux(
    report: CatalogueComparisonReport, gate: PhaseFourCatalogueGate
) -> None:
    """Positions, peaks and integrated fluxes agree within the gate."""
    limits = (
        (
            report.median_separation_beam_fwhm,
            report.percentile_95_separation_beam_fwhm,
            gate.maximum_median_position_beams,
            gate.maximum_percentile_95_position_beams,
        ),
        (
            report.median_absolute_peak_flux_fractional_difference,
            report.percentile_95_absolute_peak_flux_fractional_difference,
            gate.maximum_median_peak_flux_fractional_difference,
            gate.maximum_percentile_95_peak_flux_fractional_difference,
        ),
        (
            report.median_absolute_integrated_flux_fractional_difference,
            report.percentile_95_absolute_integrated_flux_fractional_difference,
            gate.maximum_median_integrated_flux_fractional_difference,
            gate.maximum_percentile_95_integrated_flux_fractional_difference,
        ),
    )
    for median, tail, maximum_median, maximum_tail in limits:
        assert median is not None
        assert tail is not None
        assert median <= maximum_median
        assert tail <= maximum_tail


def _require_fitted_model(
    report: CatalogueComparisonReport, gate: PhaseFourCatalogueGate
) -> None:
    """Shapes, resolution and uncertainties agree with the fitted Gaussians."""
    limits = (
        (
            report.median_absolute_fitted_axis_fractional_difference,
            report.percentile_95_absolute_fitted_axis_fractional_difference,
            gate.maximum_median_fitted_axis_fractional_difference,
            gate.maximum_percentile_95_fitted_axis_fractional_difference,
        ),
        (
            report.median_absolute_fitted_position_angle_difference_degrees,
            report.percentile_95_absolute_fitted_position_angle_difference_degrees,
            gate.maximum_median_position_angle_difference_degrees,
            gate.maximum_percentile_95_position_angle_difference_degrees,
        ),
        (
            report.median_absolute_deconvolved_axis_fractional_difference,
            report.percentile_95_absolute_deconvolved_axis_fractional_difference,
            gate.maximum_median_deconvolved_axis_fractional_difference,
            gate.maximum_percentile_95_deconvolved_axis_fractional_difference,
        ),
        (
            report.median_absolute_deconvolved_position_angle_difference_degrees,
            report.percentile_95_absolute_deconvolved_position_angle_difference_degrees,
            gate.maximum_median_position_angle_difference_degrees,
            gate.maximum_percentile_95_position_angle_difference_degrees,
        ),
    )
    for median, tail, maximum_median, maximum_tail in limits:
        assert median is not None
        assert tail is not None
        assert median <= maximum_median
        assert tail <= maximum_tail
    assert report.unresolved_classification_accuracy is not None
    assert report.unresolved_classification_accuracy >= min(
        gate.minimum_point_source_specificity,
        gate.minimum_clear_resolved_classification_recall,
    )
    assert report.catastrophic_outlier_fraction is not None
    assert (
        report.catastrophic_outlier_fraction
        <= gate.maximum_catastrophic_outlier_fraction
    )
    availability = {
        item.metric: item.availability_fraction
        for item in report.field_availability
    }
    for metric, minimum in (
        ("fitted-shape", gate.minimum_fitted_shape_availability),
        (
            "deconvolution-classification",
            gate.minimum_deconvolution_classification_availability,
        ),
        (
            "resolved-deconvolved-shape",
            gate.minimum_resolved_deconvolved_shape_availability,
        ),
    ):
        value = availability[metric]
        assert value is not None
        assert value >= minimum
    uncertainty = {
        item.metric: item.availability_fraction
        for item in report.uncertainty_calibration
    }
    for metric in (
        "right-ascension",
        "declination",
        "peak-flux",
        "integrated-flux",
    ):
        assert (
            uncertainty[metric]
            >= gate.minimum_position_flux_uncertainty_availability
        )


@pytest.mark.parametrize("reference", _REFERENCES)
def test_every_reference_source_is_one_gaussian(reference: str) -> None:
    """A reference source row is its single Gaussian's fit.

    This is what makes the published components the like-for-like
    comparison for the fitted model.
    """
    table = cast(
        npt.NDArray[np.void],
        fits.getdata(_REFERENCE_ROOT / reference / "source_catalog.fits"),
    )

    assert [str(code) for code in np.asarray(table["S_Code"])] == ["S"] * 3


@pytest.mark.parametrize("reference", _REFERENCES)
def test_published_sources_match_the_reference_sources(
    published: _Published, reference: str
) -> None:
    """Every source meets the compact gates under both profiles.

    Every source here is one Gaussian, which a source row publishes as its
    fit under both profiles (task 57), as the reference does.
    """
    report = _compare(reference, published.catalogue, "sources")

    _require_association(report, _CATALOGUE_GATE)
    _require_position_and_flux(report, _CATALOGUE_GATE)
    _require_fitted_model(report, _CATALOGUE_GATE)


@pytest.mark.parametrize("reference", _REFERENCES)
def test_published_components_match_the_reference_gaussians(
    published: _Published, reference: str
) -> None:
    """Every fitted Gaussian meets the compact-reference catalogue gates."""
    report = _compare(reference, published.catalogue, "components")

    _require_association(report, _CATALOGUE_GATE)
    _require_position_and_flux(report, _CATALOGUE_GATE)
    _require_fitted_model(report, _CATALOGUE_GATE)


@pytest.mark.parametrize("reference", _REFERENCES)
def test_published_rms_matches_the_reference_rms_off_source(
    published: _Published, reference: str
) -> None:
    """The source-free RMS meets the plan's target, or its known bound.

    The reference's flat-noise RMS is the same file as its true-sky RMS on
    this input, so one comparison covers both.
    """
    source_free = ~load_mask_plane(
        _REFERENCE_ROOT / reference / "source_filter_mask.fits"
    )

    report = compare_rms_maps(
        load_fits_plane(_REFERENCE_ROOT / reference / "true_sky_rms.fits"),
        published.rms,
        valid_mask=source_free,
    )

    assert report.compared_pixel_count == np.count_nonzero(source_free)
    assert report.median_absolute_fractional_difference is not None
    assert report.percentile_95_absolute_fractional_difference is not None
    assert report.median_absolute_fractional_difference <= _RMS_MEDIAN
    assert report.percentile_95_absolute_fractional_difference <= (
        _CONTINUUM_RMS_PERCENTILE_95
        if published.profile == "continuum"
        else _RMS_PERCENTILE_95
    )


def _islands(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Label a mask's eight-connected islands."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=np.ones((3, 3), dtype=np.bool_)),
    )
    return labels


def _mask_pixels(
    rows: tuple[tuple[float, float], ...],
) -> tuple[tuple[int, int], ...]:
    """Return the input pixel each sky position falls in, as (y, x)."""
    header = cast(fits.Header, fits.getheader(_REFERENCE_ROOT / "input.fits"))
    world = WCS(header).celestial
    pixels: list[tuple[int, int]] = []
    for right_ascension, declination in rows:
        x, y = cast(
            tuple[float, float],
            world.world_to_pixel_values(right_ascension, declination),
        )
        pixels.append((round(float(y)), round(float(x))))
    return tuple(pixels)


@pytest.mark.parametrize("reference", _REFERENCES)
def test_published_mask_matches_the_reference_island_mask(
    published: _Published, reference: str
) -> None:
    """The mask holds the reference's islands, one to one.

    The published mask is publication support, which is narrower than the
    reference's island mask by design, so its recall and IoU, and the IoU of
    its matched islands, have their own bounds. It marks nothing the
    reference leaves out beyond the gate, and every catalogued position of
    either catalogue lies inside both masks.
    """
    reference_mask = load_mask_plane(
        _REFERENCE_ROOT / reference / "source_filter_mask.fits"
    )

    pixels = compare_masks(reference_mask, published.mask)
    islands = compare_island_labels(
        _islands(reference_mask), _islands(published.mask)
    )

    assert pixels.precision >= _MASK_GATE.mask.minimum_precision
    assert pixels.recall >= _MASK_RECALL
    assert pixels.intersection_over_union >= _MASK_INTERSECTION_OVER_UNION
    assert islands.reference_count == islands.candidate_count == 3
    assert islands.completeness >= _MASK_GATE.islands.minimum_completeness
    assert islands.reliability >= _MASK_GATE.islands.minimum_reliability
    assert islands.median_matched_intersection_over_union is not None
    assert islands.minimum_matched_intersection_over_union is not None
    assert (
        islands.median_matched_intersection_over_union
        >= _ISLAND_MEDIAN_INTERSECTION_OVER_UNION
    )
    assert (
        islands.minimum_matched_intersection_over_union
        >= _ISLAND_MINIMUM_INTERSECTION_OVER_UNION
    )
    assert (
        len(islands.split_reference_labels)
        <= _MASK_GATE.islands.maximum_split_count
    )
    assert (
        len(islands.merged_candidate_labels)
        <= _MASK_GATE.islands.maximum_merge_count
    )
    positions = (
        *(
            (row.right_ascension_degrees, row.declination_degrees)
            for row in load_pybdsf_catalogue(
                _REFERENCE_ROOT / reference / "source_catalog.fits"
            )
        ),
        *(
            (
                row.position.right_ascension_degrees,
                row.position.declination_degrees,
            )
            for row in published.catalogue.gaussian_components
        ),
    )
    for y, x in _mask_pixels(positions):
        assert reference_mask[y, x]
        assert published.mask[y, x]
