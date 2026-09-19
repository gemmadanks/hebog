"""Joint development morphology checks, independent of held-out pixels."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

from dataclasses import dataclass
from math import cos, hypot, pi, sin, sqrt
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits

from hebog import public_api
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.data_models.source_finding import SourceFinderRequest
from hebog.executors.serial import SerialExecutor
from hebog.io.fits import FitsImageSource
from hebog.public_science import build_configured_continuum_products
from hebog.science.profile import (
    configured_science_profile,
    load_continuum_science_profile,
)
from hebog.validation.datasets import (
    BeamMetadata,
    DatasetManifest,
    DatasetRecord,
    DatasetRole,
    ExpectedImageStatistics,
    RedistributionStatus,
    SyntheticNoiseCorrelation,
    SyntheticRecipe,
    SyntheticSource,
    WcsMetadata,
    generate_synthetic_image,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.public_measurement_projection import (
    ContinuumCatalogueObject,
    project_public_measurements,
)
from hebog.validation.tiled_detection import publish_continuum_inputs

_ROOT = Path(__file__).parents[2]
_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * np.log(2.0))
_IMAGE_SHAPE_YX = (512, 512)
_NOMINAL_RMS = 0.0002
_BACKGROUND = -0.001
_TRUTH_THRESHOLD_SIGMA = 3.0
_FIRST_SEED = 2_026_980_001
_BEAMS = {
    "beam-a": BeamMetadata(
        major_fwhm_pixels=5.4,
        minor_fwhm_pixels=3.6,
        position_angle_degrees=31.0,
    ),
    "beam-b": BeamMetadata(
        major_fwhm_pixels=6.3,
        minor_fwhm_pixels=4.0,
        position_angle_degrees=68.0,
    ),
}
_MINIMUM_SUPPORT_OVERLAP = 0.1


@dataclass(frozen=True, slots=True)
class _Geometry:
    """One morphology, beam, noise gradient, extent, placement and peak."""

    morphology: str
    beam_id: str
    noise_gradient_id: str
    extent_major_beams: float
    placement_id: str
    target_nominal_peak_sigma: float

    @property
    def identifier(self) -> str:
        """Return a domain identifier naming every geometry choice."""
        return (
            f"{self.morphology}-{self.beam_id}-{self.noise_gradient_id}-"
            f"scale-{int(self.extent_major_beams)}-{self.placement_id}-"
            f"peak-{int(self.target_nominal_peak_sigma)}"
        )


def _development_geometries() -> tuple[_Geometry, ...]:
    """Return the 36 development cells in their frozen order.

    Twelve morphology, beam and noise-gradient combinations each receive one
    extent and placement from a covering design, and three nominal peaks that
    bracket the 75-sigma adaptive-background trigger.
    """
    extents = (4.0, 8.0, 12.0)
    placements = ("interior", "tile-corner")
    return tuple(
        _Geometry(
            morphology,
            beam_id,
            gradient_id,
            extents[covering_index % len(extents)],
            placements[covering_index % len(placements)],
            peak_sigma,
        )
        for morphology_index, morphology in enumerate(
            ("shell", "curved-filament", "mixed-compact-extended")
        )
        for beam_index, beam_id in enumerate(_BEAMS)
        for gradient_index, gradient_id in enumerate(("flat", "varying"))
        for covering_index in (morphology_index + beam_index + gradient_index,)
        for peak_sigma in (60.0, 75.0, 90.0)
    )


def _source(
    position_xy: tuple[float, float],
    peak: float,
    major_fwhm: float,
    minor_fwhm: float,
    angle: float,
) -> SyntheticSource:
    """Build one Gaussian from FWHM axes in pixels."""
    return SyntheticSource(
        x_pixel=position_xy[0],
        y_pixel=position_xy[1],
        peak_flux_jy_per_beam=peak,
        major_sigma_pixels=max(major_fwhm, minor_fwhm) / _FWHM_PER_SIGMA,
        minor_sigma_pixels=min(major_fwhm, minor_fwhm) / _FWHM_PER_SIGMA,
        rotation_degrees_counterclockwise_from_x=angle % 180.0,
    )


def _unit_sources(geometry: _Geometry) -> tuple[SyntheticSource, ...]:
    """Return one uncalibrated composite with unit component peaks."""
    beam = _BEAMS[geometry.beam_id]
    center_x, center_y = (
        (181.0, 173.0)
        if geometry.placement_id == "interior"
        else (256.0, 256.0)
    )
    if geometry.morphology == "shell":
        # Eight contiguous knots on one ring.
        radius = 0.5 * geometry.extent_major_beams * beam.major_fwhm_pixels
        tangent_fwhm = max(
            beam.major_fwhm_pixels, 1.15 * 2.0 * pi * radius / 8
        )
        return tuple(
            _source(
                (
                    center_x + radius * cos(angle),
                    center_y + radius * sin(angle),
                ),
                1.0,
                tangent_fwhm,
                beam.minor_fwhm_pixels,
                np.rad2deg(angle) + 90.0,
            )
            for angle in np.linspace(0.0, 2.0 * pi, 8, endpoint=False)
        )
    if geometry.morphology == "curved-filament":
        # Seven overlapping knots on a centred 120-degree arc.
        radius = beam.major_fwhm_pixels * min(
            geometry.extent_major_beams / (2.0 * sin(pi / 3.0)),
            1.25 / (2.0 * sin(pi / 18.0)),
        )
        angles = np.linspace(-pi / 3.0, pi / 3.0, 7)
        offsets = np.column_stack(
            (radius * np.cos(angles), radius * np.sin(angles))
        )
        mean_x, mean_y = (float(value) for value in np.mean(offsets, axis=0))
        segment = geometry.extent_major_beams * beam.major_fwhm_pixels / 7.0
        tangent_fwhm = sqrt(beam.major_fwhm_pixels**2 + segment**2)
        return tuple(
            _source(
                (center_x + x_offset - mean_x, center_y + y_offset - mean_y),
                1.0,
                tangent_fwhm,
                beam.minor_fwhm_pixels,
                np.rad2deg(angle) + 90.0,
            )
            for angle, (x_offset, y_offset) in zip(
                angles, offsets, strict=True
            )
        )
    # A restoring-beam core and a halo carrying 75% of the flux.
    halo_major = geometry.extent_major_beams * beam.major_fwhm_pixels
    halo_minor = max(2.0 * beam.minor_fwhm_pixels, halo_major / 2.0)
    core_area = beam.major_fwhm_pixels * beam.minor_fwhm_pixels
    halo_peak = 3.0 * core_area / (halo_major * halo_minor)
    return tuple(
        _source(
            (center_x, center_y),
            peak,
            major,
            minor,
            beam.position_angle_degrees,
        )
        for peak, major, minor in (
            (1.0, beam.major_fwhm_pixels, beam.minor_fwhm_pixels),
            (halo_peak, halo_major, halo_minor),
        )
    )


def _recipe(
    geometry: _Geometry,
    sources: tuple[SyntheticSource, ...],
    *,
    seed: int,
) -> SyntheticRecipe:
    """Return one noisy realization with beam-correlated noise."""
    beam = _BEAMS[geometry.beam_id]
    return SyntheticRecipe(
        generator="hebog.synthetic.gaussian-noise",
        generator_version=3,
        seed=seed,
        shape_yx=_IMAGE_SHAPE_YX,
        background=_BACKGROUND,
        noise_rms=_NOMINAL_RMS,
        sources=sources,
        noise_rms_fractional_gradient_xy=(
            (0.0, 0.0) if geometry.noise_gradient_id == "flat" else (0.4, -0.2)
        ),
        noise_correlation=SyntheticNoiseCorrelation(
            major_fwhm_pixels=beam.major_fwhm_pixels,
            minor_fwhm_pixels=beam.minor_fwhm_pixels,
            position_angle_degrees=beam.position_angle_degrees,
        ),
    )


def _signal(recipe: SyntheticRecipe) -> npt.NDArray[np.float64]:
    """Evaluate only the noiseless analytic source contribution."""
    return generate_synthetic_image(
        recipe.model_copy(update={"background": 0.0, "noise_rms": 0.0})
    )


def _development_dataset(geometry: _Geometry, *, seed: int) -> DatasetRecord:
    """Return one noisy development image scaled to its nominal peak."""
    unit_sources = _unit_sources(geometry)
    scale = (
        geometry.target_nominal_peak_sigma
        * _NOMINAL_RMS
        / float(np.max(_signal(_recipe(geometry, unit_sources, seed=seed))))
    )
    recipe = _recipe(
        geometry,
        tuple(
            source.model_copy(
                update={
                    "peak_flux_jy_per_beam": source.peak_flux_jy_per_beam
                    * scale
                }
            )
            for source in unit_sources
        ),
        seed=seed,
    )
    return DatasetRecord(
        identifier=geometry.identifier,
        role=DatasetRole.DEVELOPMENT,
        purpose="Extended-source recovery over a controlled background.",
        provenance="Deterministic analytic Gaussian composite.",
        redistribution=RedistributionStatus.GENERATED_LOCALLY,
        beam=_BEAMS[geometry.beam_id],
        wcs=WcsMetadata(
            reference_pixel_xy=(256.0, 256.0),
            reference_sky_degrees=(180.0, -30.0),
            pixel_scale_degrees_xy=(-0.0004, 0.0004),
            rotation_degrees_counterclockwise=23.0,
        ),
        expected_statistics=ExpectedImageStatistics(
            background_jy_per_beam=_BACKGROUND,
            noise_rms_jy_per_beam=_NOMINAL_RMS,
            finite_fraction=1.0,
        ),
        recipe=recipe,
        recipe_sha256=recipe_sha256(recipe),
    )


def _true_rms(recipe: SyntheticRecipe) -> npt.NDArray[np.float64]:
    """Return the exact local noise RMS of generator version three."""
    height, width = recipe.shape_yx
    gradient_x, gradient_y = recipe.noise_rms_fractional_gradient_xy
    x = np.arange(width, dtype=np.float64)[np.newaxis, :] / (width - 1) - 0.5
    y = np.arange(height, dtype=np.float64)[:, np.newaxis] / (height - 1) - 0.5
    return recipe.noise_rms * (1.0 + gradient_x * x + gradient_y * y)


@dataclass(frozen=True, slots=True)
class _TruthRecovery:
    """How one extended truth object is recovered by a source catalogue."""

    matched_source: ContinuumCatalogueObject | None
    eligible_support_count: int
    mask_recall: float
    mask_iou: float


def _eligible_overlap(
    truth_support: npt.NDArray[np.bool_],
    candidate_support: npt.NDArray[np.bool_],
    candidate_centre_xy: tuple[float, float],
    *,
    beam_fwhm_pixels: float,
) -> float | None:
    """Return the support overlap of an eligible candidate, else ``None``.

    A candidate is eligible when its support covers at least 10% of the
    smaller support, or when its centre lies within one beam FWHM of truth.
    """
    overlap = np.count_nonzero(truth_support & candidate_support) / min(
        np.count_nonzero(truth_support), np.count_nonzero(candidate_support)
    )
    y_pixels, x_pixels = np.nonzero(truth_support)
    nearest = float(
        np.min(
            np.hypot(
                x_pixels - candidate_centre_xy[0],
                y_pixels - candidate_centre_xy[1],
            )
        )
    )
    if overlap >= _MINIMUM_SUPPORT_OVERLAP or nearest <= beam_fwhm_pixels:
        return overlap
    return None


def _recover_truth(
    truth_support: npt.NDArray[np.bool_],
    truth_centre_xy: tuple[float, float],
    sources: tuple[ContinuumCatalogueObject, ...],
    source_labels: npt.NDArray[np.integer],
    *,
    beam_fwhm_pixels: float,
) -> _TruthRecovery:
    """Associate one truth object with catalogue rows and native supports.

    The matched source has the largest support overlap, then the nearest
    centre, then the first identifier. Every positive label is a support;
    its centre is the mean of its catalogue rows, or of its pixels when it
    has none, so more than one eligible support means the truth was split.
    """
    ranked: list[tuple[float, float, str, ContinuumCatalogueObject]] = []
    for source in sources:
        overlap = _eligible_overlap(
            truth_support,
            source_labels == source.support_label,
            source.centre_xy,
            beam_fwhm_pixels=beam_fwhm_pixels,
        )
        if overlap is not None:
            distance = hypot(
                source.centre_xy[0] - truth_centre_xy[0],
                source.centre_xy[1] - truth_centre_xy[1],
            )
            ranked.append((-overlap, distance, source.identifier, source))
    eligible_support_count = 0
    for label in np.unique(source_labels[source_labels > 0]):
        support = source_labels == label
        rows = [row for row in sources if row.support_label == label]
        if rows:
            centre_xy = (
                float(np.mean([row.centre_xy[0] for row in rows])),
                float(np.mean([row.centre_xy[1] for row in rows])),
            )
        else:
            y_pixels, x_pixels = np.nonzero(support)
            centre_xy = (float(np.mean(x_pixels)), float(np.mean(y_pixels)))
        eligible_support_count += (
            _eligible_overlap(
                truth_support,
                support,
                centre_xy,
                beam_fwhm_pixels=beam_fwhm_pixels,
            )
            is not None
        )
    candidate_mask = source_labels > 0
    intersection = np.count_nonzero(truth_support & candidate_mask)
    return _TruthRecovery(
        matched_source=min(ranked)[3] if ranked else None,
        eligible_support_count=eligible_support_count,
        mask_recall=intersection / np.count_nonzero(truth_support),
        mask_iou=intersection
        / np.count_nonzero(truth_support | candidate_mask),
    )


@pytest.fixture(scope="module")
def development_geometry_matrix() -> tuple[_Geometry, ...]:
    """Reuse all 36 declared development geometries, never held-out data."""
    proposed = set(range(_FIRST_SEED, _FIRST_SEED + 36))
    for path in (_ROOT / "config/datasets").glob("*.json"):
        historical = DatasetManifest.model_validate_json(path.read_bytes())
        assert proposed.isdisjoint(
            recipe.seed
            for dataset in historical.datasets
            for recipe in iter_dataset_recipes(dataset)
        ), path
    return _development_geometries()


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("cell_index", range(36))
@pytest.mark.parametrize(
    ("with_noise", "estimate_background"),
    ((False, False), (True, False), (True, True)),
    ids=("analytic", "noisy", "public-background"),
)
def test_joint_geometry_with_controlled_or_public_background(
    development_geometry_matrix: tuple[_Geometry, ...],
    cell_index: int,
    tmp_path: Path,
    with_noise: bool,
    estimate_background: bool,
) -> None:
    """Separate intrinsic topology losses from the exact public background."""
    dataset = _development_dataset(
        development_geometry_matrix[cell_index],
        seed=_FIRST_SEED + cell_index,
    )
    recipe = dataset.recipe
    signal = _signal(recipe)
    rms = _true_rms(recipe)
    truth_support = signal >= _TRUTH_THRESHOLD_SIGMA * rms
    image = generate_synthetic_image(recipe) if with_noise else signal
    background = np.full_like(signal, recipe.background if with_noise else 0.0)
    header = synthetic_fits_header(dataset)
    beam = dataset.beam
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(image, header).writeto(path)
    source = FitsImageSource(path)
    metadata = source.metadata()
    if estimate_background:
        scientific = public_api._analyse_image(
            SourceFinderRequest(path, tmp_path / "output", dataset.identifier),
            source,
            metadata,
            SerialExecutor(),
            tmp_path / "work",
            config=SourceFinderConfig(5.0, 3.0, 7),
            header=header,
        )
        products = scientific.terminal
    else:
        review = load_continuum_science_profile(
            (
                _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
            ).read_bytes()
        )
        config = SourceFinderConfig(5.0, 3.0, 7)
        beam_pixels = BeamShapePixels(
            beam.major_fwhm_pixels,
            beam.minor_fwhm_pixels,
            beam.position_angle_degrees,
        )
        published = publish_continuum_inputs(
            np.asarray(image, dtype=np.float64),
            np.ones(image.shape, dtype=np.bool_),
            background,
            rms,
            beam=beam_pixels,
            review=configured_science_profile(review, config),
            work_directory=tmp_path / "detection",
            config=config,
        )
        products = build_configured_continuum_products(
            image,
            background,
            rms,
            header,
            beam=beam_pixels,
            review=review,
            config=config,
            multiscale=published.multiscale,
            labels=published.labels,
            topology=published.topology,
        )
        scientific = public_api._ScientificProducts(
            image, background, rms, products
        )
    assert products is not None
    catalogue, mask = public_api._public_catalogue(
        scientific, metadata, run_id=dataset.identifier, profile="continuum"
    )
    projection = project_public_measurements(products, catalogue, mask, header)
    brightness = np.asarray(
        [
            item.peak_flux_jy_per_beam
            * 2.0
            * pi
            * item.major_sigma_pixels
            * item.minor_sigma_pixels
            for item in recipe.sources
        ]
    )
    truth_centre_xy = (
        float(np.dot(brightness, [item.x_pixel for item in recipe.sources]))
        / float(np.sum(brightness)),
        float(np.dot(brightness, [item.y_pixel for item in recipe.sources]))
        / float(np.sum(brightness)),
    )
    truth_flux_jy = float(np.sum(brightness)) / (
        pi * beam.major_fwhm_pixels * beam.minor_fwhm_pixels / (4 * np.log(2))
    )

    recovery = _recover_truth(
        truth_support,
        truth_centre_xy,
        projection.sources,
        projection.source_union_labels,
        beam_fwhm_pixels=beam.major_fwhm_pixels,
    )

    assert recovery.matched_source is not None, recovery
    assert recovery.eligible_support_count == 1, recovery
    assert (
        abs(recovery.matched_source.integrated_flux_jy - truth_flux_jy)
        / truth_flux_jy
        <= 0.25
    ), recovery
    assert 0 <= recovery.mask_recall <= 1
    assert 0 <= recovery.mask_iou <= 1
    if not with_noise:
        assert recovery.mask_recall >= 0.75, recovery
        assert recovery.mask_iou >= 0.60, recovery
    # Noisy cells report these absolute mask targets without hard floors;
    # paired parity and retention remain separate comparisons. This fixture
    # alone cannot qualify a candidate.
