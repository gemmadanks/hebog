"""Independent regression cases for Phase 4 scientific recovery.

Each case runs the bounded serial compact branch (detection, deblending,
moments, Gaussian fitting and catalogue completion) with its frozen Phase 4
configuration and scores the Gaussian components against analytic truth.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pytest

from hebog.algorithms.astrometry import (
    compact_geometry_at_pixel,
    local_tangent_plane_transform,
)
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
from hebog.data_models import ImageBounds
from hebog.data_models.catalogues import GaussianShape, SourceCatalogue
from hebog.data_models.images import ImageMetadata
from hebog.executors import SerialExecutor
from hebog.io import ImageWindow, ZarrProductSink
from hebog.stages.catalogue import run_compact_catalogue_stage
from hebog.stages.detection import DetectionStageConfig, run_detection_stage
from hebog.validation.campaigns import phase_four_truth_source
from hebog.validation.comparison import (
    CatalogueEllipse,
    CatalogueMatch,
    CatalogueSource,
    compare_catalogues,
)
from hebog.validation.contracts import load_phase_four_scientific_gates
from hebog.validation.datasets import (
    AssociationTruthGroup,
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_window,
    iter_dataset_recipes,
    load_dataset_manifest,
    recipe_sha256,
)
from hebog.validation.materialization import synthetic_image_metadata

_ROOT = Path(__file__).parents[2]
_PAIRED_REGRESSION = _ROOT / "config/datasets/phase-4-paired-regression.json"
_PHASE4R_DEVELOPMENT = _ROOT / "config/datasets/phase-4r-development.json"
_PHASE4R_DEVELOPMENT_2 = _ROOT / "config/datasets/phase-4r-development-2.json"
_PHASE4R_REPLACEMENT = (
    _ROOT / "config/datasets/phase-4r-qualification-replacement.json"
)
_OUTLIER = load_phase_four_scientific_gates(
    _ROOT / "config/contracts/phase-4-scientific-gates.json"
).catastrophic_outlier
_MAXIMUM_SEPARATION_BEAMS = 0.5
_POSITION_ANGLE_MINIMUM_AXIS_RATIO = 1.1
_UNDERSIZED_BLEND_CHILD_SEEDS = (
    2026100024,
    2026100064,
    2026100165,
    2026100180,
)
_BLEND_DEVELOPMENT_SEEDS = tuple(range(2026501001, 2026501019))


class _SyntheticImageSource:
    """Generate exact float64 windows without materializing a full plane."""

    def __init__(self, recipe: SyntheticRecipe) -> None:
        self._recipe = recipe

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one generated window and its finite-pixel validity."""
        values = generate_synthetic_window(
            self._recipe,
            y_start=bounds.y_start,
            y_stop=bounds.y_stop,
            x_start=bounds.x_start,
            x_stop=bounds.x_stop,
        )
        return ImageWindow(
            bounds=bounds,
            values=np.asarray(values, dtype=np.float64),
            valid_pixels=np.isfinite(values),
        )

    def read_windows(
        self,
        bounds_collection: tuple[ImageBounds, ...],
    ) -> tuple[ImageWindow, ...]:
        """Return generated windows in request order."""
        return tuple(self.read_window(bounds) for bounds in bounds_collection)


def _detection_config() -> DetectionStageConfig:
    """Return the frozen Phase 4 threshold and RMS profile."""
    statistics = RmsWindowStatisticsConfig(3.0, 10, 6)
    return DetectionStageConfig(
        background_rms=BackgroundRmsConfig(
            coarse=RmsGridConfig((150, 150), (50, 50), statistics, 32),
            adaptive=AdaptiveRmsConfig(
                grid=RmsGridConfig((35, 35), (7, 7), statistics, 32),
                candidate_threshold_sigma=75.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=1_000_000,
        ),
        source_finder=SourceFinderConfig(5.0, 3.0, 7),
    )


def _ellipse(shape: GaussianShape | None) -> CatalogueEllipse | None:
    """Translate one catalogue ellipse to the comparison record."""
    if shape is None:
        return None
    return CatalogueEllipse(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=shape.position_angle_degrees,
    )


def _component_sources(
    catalogue: SourceCatalogue,
    metadata: ImageMetadata,
) -> tuple[CatalogueSource, ...]:
    """Translate Gaussian components, keeping source association flux."""
    sources_by_id = {source.source_id: source for source in catalogue.sources}
    beam_area_degrees = (
        metadata.beam.major_fwhm_degrees * metadata.beam.minor_fwhm_degrees
    )
    rows: list[CatalogueSource] = []
    for component in catalogue.gaussian_components:
        source = sources_by_id[component.source_id]
        association_flux = source.association_aperture_integrated_flux_jy
        if association_flux is None:
            association_flux = (
                component.flux.peak_flux_jy_per_beam
                * component.fitted_shape.major_fwhm_degrees
                * component.fitted_shape.minor_fwhm_degrees
                / beam_area_degrees
            )
        rows.append(
            CatalogueSource(
                identifier=component.gaussian_component_id,
                right_ascension_degrees=(
                    component.position.right_ascension_degrees
                ),
                declination_degrees=component.position.declination_degrees,
                peak_flux_jy_per_beam=component.flux.peak_flux_jy_per_beam,
                integrated_flux_jy=component.flux.integrated_flux_jy,
                association_integrated_flux_jy=association_flux,
                fitted_shape=_ellipse(component.fitted_shape),
                deconvolved_shape=_ellipse(component.deconvolved_shape),
                deconvolved_major_fwhm_degrees=(
                    component.deconvolved_major_fwhm_degrees
                ),
                deconvolution_status=(
                    "resolved"
                    if component.deconvolved_shape is not None
                    else "major-axis-only"
                    if component.deconvolved_major_fwhm_degrees is not None
                    else "unresolved"
                    if "unresolved" in component.quality_flags
                    else "unavailable"
                ),
                quality_flags=component.quality_flags,
            )
        )
    return tuple(rows)


def _run_compact_branch(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    directory: Path,
) -> tuple[CatalogueSource, ...]:
    """Run the serial compact branch over one generated image."""
    metadata = synthetic_image_metadata(dataset)
    manifest = plan_image_partitions(
        image_shape_yx=recipe.shape_yx,
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    generation_id = f"{dataset.identifier}-{recipe.seed}"
    sink = ZarrProductSink(
        directory / "products.zarr",
        manifest,
        generation_id=generation_id,
    )
    source = _SyntheticImageSource(recipe)
    executor = SerialExecutor()
    detection = run_detection_stage(
        source,
        manifest,
        _detection_config(),
        executor,
        sink,
    )
    catalogue_config = CompactCatalogueConfig(10_000, 1e-10, 5.0)
    stage = run_compact_catalogue_stage(
        source,
        detection,
        deblend_config=CompactDeblendConfig(
            5.0, 2, 1.0, 7, 100_000, 250_000, 8_000, 500_000
        ),
        moment_config=CompactMomentConfig(3, 1e-12),
        fit_config=CompactGaussianFitConfig(
            7,
            300,
            0.2,
            30.0,
            5.0,
            1.0,
            1e-8,
            30.0,
            background_model="fixed-zero",
            pixel_support="owned-region",
            point_estimator="correlated-gls",
            model_selection="beam-or-free",
            position_estimator="bounded-context-free",
        ),
        catalogue_config=catalogue_config,
        geometry=compact_geometry_at_pixel(
            metadata,
            (recipe.shape_yx[1] / 2.0, recipe.shape_yx[0] / 2.0),
        ),
        metadata=metadata,
        executor=executor,
        sink=sink,
    )
    completed = complete_compact_catalogue(
        catalogue_id=generation_id,
        metadata=metadata,
        shards=stage.records,
        deferred_island_ids=tuple(
            item.island.island_id for item in stage.deferred_islands
        ),
        config=catalogue_config,
    )
    return _component_sources(completed.catalogue, metadata)


def _recipe(
    manifest: Path, seed: int
) -> tuple[DatasetRecord, SyntheticRecipe]:
    """Return the first dataset of a manifest and one of its realizations."""
    dataset = load_dataset_manifest(manifest).datasets[0]
    recipe = next(
        recipe
        for recipe in iter_dataset_recipes(dataset)
        if recipe.seed == seed
    )
    return dataset, recipe


def _classification_indices(
    dataset: DatasetRecord,
    identifier: str,
) -> tuple[int, ...]:
    """Return the source indices of one declared classification stratum."""
    return next(
        (
            stratum.source_indices
            for stratum in dataset.classification_strata
            if stratum.identifier == identifier
        ),
        (),
    )


def _association_truth(
    group: AssociationTruthGroup,
    recipe: SyntheticRecipe,
    dataset: DatasetRecord,
) -> CatalogueSource:
    """Return analytic truth for one observable association group.

    Individually resolvable groups use the analytic Gaussian, forced
    unresolved when declared a point source. Blends use their declared
    brightness-weighted position and total flux.
    """
    if group.resolution_class == "individually-resolvable":
        truth = phase_four_truth_source(
            recipe.sources[group.source_indices[0]],
            dataset,
            identifier=group.identifier,
        )
        if group.source_indices[0] in _classification_indices(
            dataset, "shape-unresolved"
        ):
            return replace(
                truth,
                integrated_flux_jy=truth.peak_flux_jy_per_beam,
                deconvolved_shape=None,
                deconvolved_major_fwhm_degrees=None,
                deconvolution_status="unresolved",
                quality_flags=("unresolved",),
            )
        return truth
    metadata = synthetic_image_metadata(dataset)
    transform = local_tangent_plane_transform(
        metadata,
        group.reference_position_xy,
    )
    geometry = compact_geometry_at_pixel(metadata, group.reference_position_xy)
    integrated_flux = (
        group.reference_integrated_brightness_jy_pixels_per_beam
        * geometry.pixel_solid_angle_steradians
        / geometry.restoring_beam_solid_angle_steradians
    )
    return CatalogueSource(
        identifier=group.identifier,
        right_ascension_degrees=transform.position.right_ascension_degrees,
        declination_degrees=transform.position.declination_degrees,
        peak_flux_jy_per_beam=integrated_flux,
        integrated_flux_jy=integrated_flux,
    )


def _association_matches(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    candidates: tuple[CatalogueSource, ...],
) -> dict[str, CatalogueMatch]:
    """Match every truth group one-to-one using association flux."""
    report = compare_catalogues(
        tuple(
            _association_truth(group, recipe, dataset)
            for group in dataset.association_truth_groups
        ),
        tuple(
            replace(
                candidate,
                integrated_flux_jy=candidate.association_integrated_flux_jy,
            )
            if candidate.association_integrated_flux_jy is not None
            else candidate
            for candidate in candidates
        ),
        beam_fwhm_degrees=synthetic_image_metadata(
            dataset
        ).beam.major_fwhm_degrees,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
        position_angle_minimum_axis_ratio=_POSITION_ANGLE_MINIMUM_AXIS_RATIO,
    )
    return {match.reference_identifier: match for match in report.matches}


def _maximum_absolute(*values: float | None) -> float:
    """Return the largest available absolute difference, or zero."""
    return max(
        (abs(value) for value in values if value is not None), default=0
    )


def _is_gated_catastrophic(
    match: CatalogueMatch,
    *,
    marginal_extension: bool,
) -> bool:
    """Apply the Phase 4 outlier gate, exempting marginal-extension flux."""
    return (
        match.separation_beam_fwhm > _OUTLIER.position_beams
        or abs(match.peak_flux_fractional_difference)
        > _OUTLIER.peak_flux_fractional_difference
        or (
            not marginal_extension
            and abs(match.integrated_flux_fractional_difference)
            > _OUTLIER.integrated_flux_fractional_difference
        )
        or _maximum_absolute(
            match.fitted_major_axis_fractional_difference,
            match.fitted_minor_axis_fractional_difference,
        )
        > _OUTLIER.fitted_axis_fractional_difference
        or _maximum_absolute(
            match.deconvolved_major_axis_fractional_difference,
            match.deconvolved_minor_axis_fractional_difference,
        )
        > _OUTLIER.deconvolved_axis_fractional_difference
    )


@dataclass(frozen=True, slots=True)
class _SourcePair:
    """One individually resolvable truth source and its matched component."""

    candidate: CatalogueSource
    match: CatalogueMatch
    gated_catastrophic: bool


def _source_pair(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    candidates: tuple[CatalogueSource, ...],
    group_identifier: str,
) -> _SourcePair | None:
    """Compare one truth source with its associated component, if any.

    The component uses Rapthor's source semantics: an unresolved row reports
    its peak flux as its total flux.
    """
    association = _association_matches(dataset, recipe, candidates).get(
        group_identifier
    )
    if association is None:
        return None
    group = next(
        group
        for group in dataset.association_truth_groups
        if group.identifier == group_identifier
    )
    candidate = next(
        candidate
        for candidate in candidates
        if candidate.identifier == association.candidate_identifier
    )
    if candidate.deconvolution_status == "unresolved":
        candidate = replace(
            candidate,
            integrated_flux_jy=candidate.peak_flux_jy_per_beam,
        )
    report = compare_catalogues(
        (_association_truth(group, recipe, dataset),),
        (candidate,),
        beam_fwhm_degrees=synthetic_image_metadata(
            dataset
        ).beam.major_fwhm_degrees,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
        position_angle_minimum_axis_ratio=_POSITION_ANGLE_MINIMUM_AXIS_RATIO,
    )
    if not report.matches:
        return None
    match = report.matches[0]
    return _SourcePair(
        candidate=candidate,
        match=match,
        gated_catastrophic=_is_gated_catastrophic(
            match,
            marginal_extension=group.source_indices[0]
            in _classification_indices(dataset, "shape-marginal-resolved"),
        ),
    )


def test_phase4r_low_snr_extended_edge_fit_is_not_catastrophic(
    tmp_path: Path,
) -> None:
    """Correlated fitting must not force a clear edge source to beam size."""
    dataset, recipe = _recipe(_PHASE4R_DEVELOPMENT, 2026120002)
    candidates = _run_compact_branch(dataset, recipe, tmp_path)

    pair = _source_pair(dataset, recipe, candidates, "source-00003")

    assert pair is not None
    assert not pair.gated_catastrophic
    assert "correlated-noise-gls-errors" in pair.candidate.quality_flags
    assert "beam-constrained-fit" not in pair.candidate.quality_flags


def test_viewed_marginal_minor_failure_is_censored_not_catastrophic(
    tmp_path: Path,
) -> None:
    """The Phase 4R minor-axis failure becomes an explicit one-axis result."""
    dataset, recipe = _recipe(_PHASE4R_REPLACEMENT, 2026200085)
    candidates = _run_compact_branch(dataset, recipe, tmp_path)

    pair = _source_pair(dataset, recipe, candidates, "source-00005")

    assert pair is not None
    assert pair.candidate.deconvolution_status in {
        "major-axis-only",
        "unresolved",
    }
    assert not pair.gated_catastrophic
    assert {
        "major-axis-not-significant",
        "minor-axis-not-significant",
    }.intersection(pair.candidate.quality_flags)


def test_phase4r_edge_retry_preserves_the_valid_association(
    tmp_path: Path,
) -> None:
    """A boundary retry uses its stable intensity-weighted centroid."""
    dataset, recipe = _recipe(_PHASE4R_DEVELOPMENT_2, 2026140009)
    candidates = _run_compact_branch(dataset, recipe, tmp_path)

    pair = _source_pair(dataset, recipe, candidates, "source-00003")

    assert pair is not None
    assert pair.match.separation_beam_fwhm < 0.5
    assert not pair.gated_catastrophic


def test_phase4r_blend_uses_mask_aware_association_aperture(
    tmp_path: Path,
) -> None:
    """Association flux uses bounded aperture photometry for a blend."""
    dataset, recipe = _recipe(_PHASE4R_DEVELOPMENT_2, 2026140002)
    candidates = _run_compact_branch(dataset, recipe, tmp_path)

    blend = _association_matches(dataset, recipe, candidates).get(
        "blend-00001"
    )

    assert blend is not None
    assert abs(blend.integrated_flux_fractional_difference) < 0.1


@pytest.mark.equivalence
@pytest.mark.parametrize("seed", _UNDERSIZED_BLEND_CHILD_SEEDS)
def test_unresolved_blend_does_not_leave_an_unfit_watershed_child(
    seed: int,
    tmp_path: Path,
) -> None:
    """A fit-capable parent remains complete after conservative deblending."""
    dataset, recipe = _recipe(_PAIRED_REGRESSION, seed)

    assert _run_compact_branch(dataset, recipe, tmp_path)


@pytest.mark.equivalence
@pytest.mark.parametrize(
    ("seed", "truth_identifier", "expected_extension"),
    (
        (2026100200, "source-00013", False),
        (2026100155, "source-00009", True),
    ),
)
def test_high_confidence_extension_policy_separates_point_and_clear_truth(
    seed: int,
    truth_identifier: str,
    expected_extension: bool,
    tmp_path: Path,
) -> None:
    """The independent worst-margin examples remain correctly classified."""
    dataset, recipe = _recipe(_PAIRED_REGRESSION, seed)
    candidates = _run_compact_branch(dataset, recipe, tmp_path)

    pair = _source_pair(dataset, recipe, candidates, truth_identifier)

    assert pair is not None
    if expected_extension:
        assert pair.candidate.deconvolution_status in {
            "resolved",
            "major-axis-only",
        }
    else:
        assert pair.candidate.deconvolution_status == "unresolved"


def _blend_development_case(
    base: DatasetRecord,
    *,
    seed: int,
    pair_angle_offset_degrees: float,
    faint_to_bright_ratio: float,
) -> DatasetRecord:
    """Rotate one independent blend while preserving its total peak flux."""
    blend = next(
        group
        for group in base.association_truth_groups
        if group.resolution_class == "unresolved-blend"
    )
    first_index, second_index = blend.source_indices
    sources = list(base.recipe.sources)
    first = sources[first_index]
    second = sources[second_index]
    total_peak_flux = 0.006
    first_peak = total_peak_flux / (1.0 + faint_to_bright_ratio)
    second_peak = total_peak_flux - first_peak
    center_xy = (103.5, 211.0)
    separation_pixels = 3.8
    angle = np.deg2rad(
        base.beam.position_angle_degrees + pair_angle_offset_degrees
    )
    offset_xy = (
        0.5 * separation_pixels * np.cos(angle),
        0.5 * separation_pixels * np.sin(angle),
    )
    sources[first_index] = first.model_copy(
        update={
            "peak_flux_jy_per_beam": first_peak,
            "x_pixel": center_xy[0] - offset_xy[0],
            "y_pixel": center_xy[1] - offset_xy[1],
        }
    )
    sources[second_index] = second.model_copy(
        update={
            "peak_flux_jy_per_beam": second_peak,
            "x_pixel": center_xy[0] + offset_xy[0],
            "y_pixel": center_xy[1] + offset_xy[1],
        }
    )
    recipe_document = base.recipe.model_dump(mode="json")
    recipe_document.update(
        {
            "seed": seed,
            "sources": [source.model_dump(mode="json") for source in sources],
        }
    )
    recipe = SyntheticRecipe.model_validate(recipe_document)
    pair = (sources[first_index], sources[second_index])
    brightnesses = np.asarray(
        [
            source.peak_flux_jy_per_beam
            * 2.0
            * np.pi
            * source.major_sigma_pixels
            * source.minor_sigma_pixels
            for source in pair
        ]
    )
    reference_position_xy = (
        float(
            np.dot(brightnesses, [source.x_pixel for source in pair])
            / np.sum(brightnesses)
        ),
        float(
            np.dot(brightnesses, [source.y_pixel for source in pair])
            / np.sum(brightnesses)
        ),
    )
    groups = [
        group.model_copy(
            update={
                "reference_position_xy": reference_position_xy,
                "reference_integrated_brightness_jy_pixels_per_beam": float(
                    np.sum(brightnesses)
                ),
            }
        )
        if group.identifier == blend.identifier
        else group
        for group in base.association_truth_groups
    ]
    document = base.model_dump(mode="json")
    document.update(
        {
            "identifier": "phase4u-development-blend-matrix-256",
            "purpose": (
                "Independent rotated and unequal compact blends for Phase 4U "
                "association-flux development"
            ),
            "recipe": recipe.model_dump(mode="json"),
            "recipe_sha256": recipe_sha256(recipe),
            "noise_realization_seeds": [],
            "association_truth_groups": [
                group.model_dump(mode="json") for group in groups
            ],
        }
    )
    return DatasetRecord.model_validate(document)


@pytest.mark.equivalence
def test_noisy_rotated_blend_matrix_has_margin_inside_absolute_gate(
    tmp_path: Path,
) -> None:
    """Fresh development blends avoid systematic orientation-dependent loss."""
    base = load_dataset_manifest(_PHASE4R_DEVELOPMENT_2).datasets[0]
    configurations = tuple(
        (angle, ratio)
        for _ in range(3)
        for ratio in (1.0, 0.5)
        for angle in (0.0, 45.0, 90.0)
    )
    signed_errors: list[float] = []
    for seed, (angle, ratio) in zip(
        _BLEND_DEVELOPMENT_SEEDS,
        configurations,
        strict=True,
    ):
        dataset = _blend_development_case(
            base,
            seed=seed,
            pair_angle_offset_degrees=angle,
            faint_to_bright_ratio=ratio,
        )
        candidates = _run_compact_branch(
            dataset, dataset.recipe, tmp_path / str(seed)
        )
        blend = _association_matches(dataset, dataset.recipe, candidates).get(
            "blend-00001"
        )
        assert blend is not None
        signed_errors.append(blend.integrated_flux_fractional_difference)

    absolute_errors = np.abs(signed_errors)
    assert float(np.quantile(absolute_errors, 0.95)) < 0.15
    assert abs(float(np.mean(signed_errors))) < 0.08
