"""Joint development morphology checks, independent of held-out pixels."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

from hebog import public_api
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.data_models.source_finding import SourceFinderRequest
from hebog.executors.serial import SerialExecutor
from hebog.io.fits import FitsImageSource
from hebog.public_science import build_configured_continuum_products
from hebog.science.profile import load_continuum_science_profile
from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
    source_signal_and_truth,
)
from hebog.validation.datasets import (
    DatasetManifest,
    generate_synthetic_image,
    iter_dataset_recipes,
)
from hebog.validation.external_successor_compiler import (
    ContinuumTruthObject,
    measure_continuum_image,
)
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.public_measurement_projection import (
    project_public_measurements,
)
from hebog.validation.source_catalogue_diagnostics import (
    SourceDiagnosticInput,
    compile_source_diagnostics,
)


@pytest.fixture(scope="module")
def development_geometry_matrix() -> DatasetManifest:
    """Reuse all 36 declared development geometries, never held-out data."""
    proposed = set(range(2_026_980_001, 2_026_980_037))
    for path in (Path(__file__).parents[2] / "config/datasets").glob("*.json"):
        historical = DatasetManifest.model_validate_json(path.read_bytes())
        assert proposed.isdisjoint(
            recipe.seed
            for dataset in historical.datasets
            for recipe in iter_dataset_recipes(dataset)
        ), path
    return build_adaptive_development_manifest()


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("cell_index", range(36))
@pytest.mark.parametrize(
    ("with_noise", "estimate_background"),
    ((False, False), (True, False), (True, True)),
    ids=("analytic", "noisy", "public-background"),
)
def test_joint_geometry_with_controlled_or_public_background(
    development_geometry_matrix: DatasetManifest,
    cell_index: int,
    tmp_path: Path,
    with_noise: bool,
    estimate_background: bool,
) -> None:
    """Separate intrinsic topology losses from the exact public background."""
    dataset = development_geometry_matrix.datasets[cell_index]
    assert dataset.recipe is not None
    signal, support, rms = source_signal_and_truth(dataset.recipe)
    recipe = dataset.recipe.model_copy(
        update={
            "seed": 2_026_980_001 + cell_index,
            "background": -0.001,
        }
    )
    image = generate_synthetic_image(recipe) if with_noise else signal
    background = np.full_like(signal, recipe.background if with_noise else 0.0)
    header = synthetic_fits_header(dataset)
    review = load_continuum_science_profile(
        (
            Path(__file__).parents[2]
            / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )
    beam = dataset.beam
    background_error = np.zeros_like(signal)
    relative_rms_error = np.zeros_like(signal)
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
        background_error = (scientific.background - background) / rms
        relative_rms_error = scientific.rms / rms - 1
    else:
        products = build_configured_continuum_products(
            image,
            background,
            rms,
            header,
            beam=BeamShapePixels(
                beam.major_fwhm_pixels,
                beam.minor_fwhm_pixels,
                beam.position_angle_degrees,
            ),
            review=review,
            config=SourceFinderConfig(5.0, 3.0, 7),
        )
        scientific = public_api._ScientificProducts(
            image, background, rms, products
        )
    assert products is not None
    group = dataset.multiscale_truth_groups[0]
    beam_area = (
        np.pi
        * beam.major_fwhm_pixels
        * beam.minor_fwhm_pixels
        / (4 * np.log(2))
    )
    truth = (
        ContinuumTruthObject(
            group.identifier,
            1,
            group.reference_position_xy,
            group.reference_integrated_brightness_jy_pixels_per_beam
            / beam_area,
            "astronomical-source",
            (),
        ),
    )
    catalogue, mask = public_api._public_catalogue(
        scientific, metadata, run_id=dataset.identifier, profile="continuum"
    )
    projection = project_public_measurements(products, catalogue, mask, header)
    labels, rows = projection.source_union_labels, projection.sources
    packet = compile_source_diagnostics(
        SourceDiagnosticInput(
            input_id=dataset.identifier,
            finder_id=(
                "hebog-public-background"
                if estimate_background
                else "hebog-analytic-background"
            ),
            truth=truth,
            sources=rows,
            truth_labels=support.astype(np.int32),
            source_union_labels=labels,
            stage_masks=dict(products.support_stages),
            background_error=background_error,
            relative_rms_error=relative_rms_error,
            valid_pixels=products.valid_pixels,
            beam_fwhm_pixels=beam.major_fwhm_pixels,
            dispositions=projection.dispositions,
            measured_sources=projection.measured_sources,
            measured_components=projection.measured_components,
        )
    )
    # Keep full diagnostics when pytest retains a failed case's directory.
    (tmp_path / "diagnostics.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )
    metrics: dict[str, Any] = measure_continuum_image(
        truth,
        rows,
        truth_label_plane=support.astype(np.int32),
        candidate_label_plane=labels,
        beam_fwhm_pixels=beam.major_fwhm_pixels,
    )
    assert metrics["completeness"]["overall"] == 1, metrics
    assert metrics["split-fraction"]["overall"] == 0, metrics
    assert max(metrics["integrated-flux-p95"]["overall"]) <= 0.25, metrics
    objectives = {
        "mask-recall": {
            "value": metrics["mask-recall"]["overall"],
            "target": 0.75,
        },
        "mask-iou": {
            "value": metrics["mask-iou"]["overall"],
            "target": 0.60,
        },
    }
    for objective in objectives.values():
        assert 0 <= objective["value"] <= 1
        objective["met"] = objective["value"] >= objective["target"]
    (tmp_path / "absolute-objectives.json").write_text(
        json.dumps(objectives, allow_nan=False), encoding="utf-8"
    )
    if not with_noise:
        assert all(row["met"] for row in objectives.values()), objectives
    # Noisy cells report these absolute mask targets without hard floors;
    # paired parity and retention remain separate comparisons. This fixture
    # alone cannot qualify a candidate.
