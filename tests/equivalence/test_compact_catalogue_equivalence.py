# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Phase 4 compact catalogue comparison with both exact PyBDSF references."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from hebog.adapters.rapthor_catalogue import (
    read_rapthor_catalogue_fits,
    write_rapthor_catalogue_fits,
)
from hebog.algorithms.astrometry import compact_geometry_at_pixel
from hebog.algorithms.catalogue import complete_compact_catalogue
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    CompactCatalogueConfig,
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
    SourceFinderConfig,
)
from hebog.data_models.catalogues import GaussianShape, SourceCatalogue
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.stages.catalogue import run_compact_catalogue_stage
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.validation.comparison import (
    CatalogueComparisonReport,
    CatalogueEllipse,
    CatalogueOutlierThresholds,
    CatalogueSource,
    compare_catalogues,
)
from hebog.validation.contracts import (
    PhaseFourCatalogueGate,
    load_phase_four_scientific_gates,
)
from hebog.validation.products import load_pybdsf_catalogue

pytestmark = pytest.mark.equivalence

_ROOT = Path(__file__).parents[2]
_REFERENCE_ROOT = _ROOT / "tests/data/pybdsf/pybdsf-compact-reference-256"
_BEAM_FWHM_DEGREES = 0.001111111111111111
_GATES = load_phase_four_scientific_gates(
    _ROOT / "config/contracts/phase-4-scientific-gates.json"
)


def _detection_config() -> DetectionStageConfig:
    """Return the frozen Rapthor compact threshold and RMS profile."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
    return DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig(
                window_shape_yx=(150, 150),
                step_yx=(50, 50),
                statistics=statistics,
                maximum_batch_cells=16,
            ),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig(
                    window_shape_yx=(35, 35),
                    step_yx=(7, 7),
                    statistics=statistics,
                    maximum_batch_cells=16,
                ),
                candidate_threshold_sigma=75.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=1_000_000,
        ),
        source_finder=SourceFinderConfig(5.0, 3.0, 7),
    )


def _shape(shape: GaussianShape | None) -> CatalogueEllipse | None:
    """Translate one internal ellipse to the independent comparison model."""
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


def _comparison_sources(
    catalogue: SourceCatalogue,
) -> tuple[CatalogueSource, ...]:
    """Translate complete internal records without reading adapter bytes."""
    component_counts = {
        source.source_id: sum(
            component.source_id == source.source_id
            for component in catalogue.gaussian_components
        )
        for source in catalogue.sources
    }
    return tuple(
        CatalogueSource(
            identifier=source.source_id,
            right_ascension_degrees=source.position.right_ascension_degrees,
            declination_degrees=source.position.declination_degrees,
            peak_flux_jy_per_beam=source.flux.peak_flux_jy_per_beam,
            integrated_flux_jy=source.flux.integrated_flux_jy,
            right_ascension_error_degrees=(
                source.position.right_ascension_error_degrees
            ),
            declination_error_degrees=(
                source.position.declination_error_degrees
            ),
            peak_flux_error_jy_per_beam=(
                source.flux.peak_flux_error_jy_per_beam
            ),
            integrated_flux_error_jy=(source.flux.integrated_flux_error_jy),
            fitted_shape=_shape(source.fitted_shape),
            deconvolved_shape=_shape(source.deconvolved_shape),
            deconvolution_status=(
                "resolved"
                if source.deconvolved_shape is not None
                else "unresolved"
                if "unresolved" in source.quality_flags
                else "unavailable"
            ),
            island_identifier=source.island_id,
            component_count=component_counts[source.source_id],
            quality_flags=source.quality_flags,
        )
        for source in catalogue.sources
    )


def _canonicalize_unresolved_reference_flux(
    sources: tuple[CatalogueSource, ...],
) -> tuple[CatalogueSource, ...]:
    """Map PyBDSF's free-area point-source flux to reviewed semantics."""
    return tuple(
        replace(
            source,
            integrated_flux_jy=source.peak_flux_jy_per_beam,
            integrated_flux_error_jy=source.peak_flux_error_jy_per_beam,
        )
        if source.deconvolution_status == "unresolved"
        else source
        for source in sources
    )


def _require_catalogue_gates(
    report: CatalogueComparisonReport,
    gates: PhaseFourCatalogueGate,
) -> None:
    """Apply every frozen exact-reference Phase 4 catalogue gate."""
    assert report.completeness >= gates.minimum_completeness
    assert report.reliability >= gates.minimum_reliability
    scalar_limits = (
        (
            report.median_separation_beam_fwhm,
            gates.maximum_median_position_beams,
        ),
        (
            report.percentile_95_separation_beam_fwhm,
            gates.maximum_percentile_95_position_beams,
        ),
        (
            report.median_absolute_peak_flux_fractional_difference,
            gates.maximum_median_peak_flux_fractional_difference,
        ),
        (
            report.percentile_95_absolute_peak_flux_fractional_difference,
            gates.maximum_percentile_95_peak_flux_fractional_difference,
        ),
        (
            report.median_absolute_integrated_flux_fractional_difference,
            gates.maximum_median_integrated_flux_fractional_difference,
        ),
        (
            report.percentile_95_absolute_integrated_flux_fractional_difference,
            gates.maximum_percentile_95_integrated_flux_fractional_difference,
        ),
        (
            report.median_absolute_fitted_axis_fractional_difference,
            gates.maximum_median_fitted_axis_fractional_difference,
        ),
        (
            report.percentile_95_absolute_fitted_axis_fractional_difference,
            gates.maximum_percentile_95_fitted_axis_fractional_difference,
        ),
        (
            report.median_absolute_deconvolved_axis_fractional_difference,
            gates.maximum_median_deconvolved_axis_fractional_difference,
        ),
        (
            report.percentile_95_absolute_deconvolved_axis_fractional_difference,
            gates.maximum_percentile_95_deconvolved_axis_fractional_difference,
        ),
    )
    for value, maximum in scalar_limits:
        assert value is not None
        assert value <= maximum
    fitted_angles = (
        report.median_absolute_fitted_position_angle_difference_degrees,
        report.percentile_95_absolute_fitted_position_angle_difference_degrees,
    )
    deconvolved_angles = (
        report.median_absolute_deconvolved_position_angle_difference_degrees,
        report.percentile_95_absolute_deconvolved_position_angle_difference_degrees,
    )
    for median, tail in (fitted_angles, deconvolved_angles):
        assert median is not None
        assert tail is not None
        assert median <= gates.maximum_median_position_angle_difference_degrees
        assert (
            tail
            <= gates.maximum_percentile_95_position_angle_difference_degrees
        )
    assert report.unresolved_classification_accuracy is not None
    assert report.unresolved_classification_accuracy >= min(
        gates.minimum_point_source_specificity,
        gates.minimum_clear_resolved_classification_recall,
    )
    assert (
        report.association.precision
        >= gates.minimum_association_pair_precision
    )
    assert report.association.recall >= gates.minimum_association_pair_recall
    assert report.association.identity_availability_fraction is not None
    assert (
        report.association.identity_availability_fraction
        >= gates.minimum_association_identity_availability
    )
    availability = {
        item.metric: item.availability_fraction
        for item in report.field_availability
    }
    assert availability["fitted-shape"] is not None
    assert (
        availability["fitted-shape"] >= gates.minimum_fitted_shape_availability
    )
    assert availability["deconvolution-classification"] is not None
    assert (
        availability["deconvolution-classification"]
        >= gates.minimum_deconvolution_classification_availability
    )
    assert availability["resolved-deconvolved-shape"] is not None
    assert (
        availability["resolved-deconvolved-shape"]
        >= gates.minimum_resolved_deconvolved_shape_availability
    )
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
            >= gates.minimum_position_flux_uncertainty_availability
        )
    assert report.catastrophic_outlier_fraction is not None
    assert (
        report.catastrophic_outlier_fraction
        <= gates.maximum_catastrophic_outlier_fraction
    )


@pytest.fixture(scope="module")
def compact_catalogue(
    tmp_path_factory: pytest.TempPathFactory,
) -> SourceCatalogue:
    """Run the complete incremental Phase 4 compact path once."""
    source = FitsImageSource(_REFERENCE_ROOT / "input.fits")
    metadata = source.metadata()
    manifest = plan_image_partitions(
        image_shape_yx=metadata.shape_yx,
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        tmp_path_factory.mktemp("phase4-compact") / "products.zarr",
        manifest,
        generation_id="phase-4-compact-equivalence",
    )
    detection = run_detection_stage(
        source,
        manifest,
        _detection_config(),
        SerialExecutor(),
        sink,
    )
    deblend = CompactDeblendConfig(
        minimum_peak_signal_to_noise=5.0,
        minimum_peak_separation_pixels=2,
        minimum_saddle_depth_sigma=1.0,
        minimum_region_pixels=7,
        maximum_compact_island_pixels=100_000,
        maximum_compact_bounds_pixels=250_000,
        maximum_batch_pixels=500_000,
    )
    moment = CompactMomentConfig(3, 1e-12)
    fit = CompactGaussianFitConfig(7, 300, 0.2, 30.0, 5.0, 1.0, 1e-8, 30.0)
    catalogue_config = CompactCatalogueConfig(10_000, 1e-10, 2.0)
    geometry = compact_geometry_at_pixel(
        metadata,
        (metadata.shape_yx[1] / 2.0, metadata.shape_yx[0] / 2.0),
    )
    stage = run_compact_catalogue_stage(
        source,
        detection,
        deblend_config=deblend,
        moment_config=moment,
        fit_config=fit,
        catalogue_config=catalogue_config,
        geometry=geometry,
        metadata=metadata,
        executor=SerialExecutor(),
        sink=sink,
    )
    completed = complete_compact_catalogue(
        catalogue_id="phase-4-compact-reference",
        metadata=metadata,
        shards=stage.records,
        deferred_island_ids=tuple(
            item.island.island_id for item in stage.deferred_islands
        ),
        config=catalogue_config,
    )
    return completed.catalogue


@pytest.mark.parametrize("reference", ["release", "master"])
def test_compact_catalogue_meets_both_exact_reference_gates(
    compact_catalogue: SourceCatalogue,
    reference: str,
) -> None:
    """The same complete compact catalogue is compared with both anchors."""
    report = compare_catalogues(
        _canonicalize_unresolved_reference_flux(
            load_pybdsf_catalogue(
                _REFERENCE_ROOT / reference / "source_catalog.fits"
            )
        ),
        _comparison_sources(compact_catalogue),
        beam_fwhm_degrees=_BEAM_FWHM_DEGREES,
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=_GATES.catastrophic_outlier.position_beams,
            peak_flux_fractional_difference=(
                _GATES.catastrophic_outlier.peak_flux_fractional_difference
            ),
            integrated_flux_fractional_difference=(
                _GATES.catastrophic_outlier.integrated_flux_fractional_difference
            ),
            fitted_axis_fractional_difference=(
                _GATES.catastrophic_outlier.fitted_axis_fractional_difference
            ),
            deconvolved_axis_fractional_difference=(
                _GATES.catastrophic_outlier.deconvolved_axis_fractional_difference
            ),
        ),
    )

    assert report.reference_count == report.candidate_count == 3
    _require_catalogue_gates(report, _GATES.compact_reference)
    assert report.component_count_agreement_fraction == 1.0


def test_pybdsf_unresolved_flux_divergence_is_explicitly_canonicalized() -> (
    None
):
    """Keep raw compatibility evidence distinct from preferred point flux."""
    raw = load_pybdsf_catalogue(
        _REFERENCE_ROOT / "release" / "source_catalog.fits"
    )
    canonical = _canonicalize_unresolved_reference_flux(raw)

    assert raw[2].deconvolution_status == "unresolved"
    assert raw[2].integrated_flux_jy != pytest.approx(
        raw[2].peak_flux_jy_per_beam
    )
    assert canonical[2].integrated_flux_jy == raw[2].peak_flux_jy_per_beam
    assert canonical[1] == raw[1]


def _rapthor_astrometry_selection(
    catalogue_path: Path,
) -> tuple[int, ...]:
    """Apply the pinned Rapthor diagnostic cuts to one FITS view."""
    table = read_rapthor_catalogue_fits(catalogue_path)
    selected = np.asarray(table["DC_Maj"], dtype=np.float64) < 10.0 / 3600.0
    selected &= np.asarray(table["E_RA"], dtype=np.float64) < 2.0 / 3600.0
    selected &= np.asarray(table["E_DEC"], dtype=np.float64) < 2.0 / 3600.0
    return tuple(
        int(value) for value in np.asarray(table["Source_id"])[selected]
    )


def test_rapthor_fits_view_preserves_exact_diagnostic_selection(
    compact_catalogue: SourceCatalogue,
    tmp_path: Path,
) -> None:
    """The eight-column view keeps all compact-reference diagnostic rows."""
    path = tmp_path / "source_catalog.fits"
    write_rapthor_catalogue_fits(path, compact_catalogue)

    selected = _rapthor_astrometry_selection(path)

    assert selected == (0, 1, 2)
