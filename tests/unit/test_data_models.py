"""Tests for scheduler-safe request and result records."""

import pickle
from pathlib import Path

from hebog import SourceFinderRequest, SourceFinderResult
from hebog.adapters.rapthor import (
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
)
from hebog.config import SourceFinderConfig


def test_request_is_pickle_serializable() -> None:
    """Dask can serialize the public request record."""
    request = SourceFinderRequest(
        image_path=Path("image.fits"),
        output_directory=Path("output"),
        run_id="test-run",
    )

    assert pickle.loads(pickle.dumps(request)) == request


def test_result_exposes_one_pipeline_neutral_product_set() -> None:
    """One scientific analysis returns one catalogue, RMS, and mask set."""
    result = SourceFinderResult(
        catalogue_path=Path("catalogue.fits"),
        rms_path=Path("rms.fits"),
        mask_path=Path("mask.fits"),
        diagnostics_path=Path("diagnostics.json"),
        source_count=2,
        wall_seconds=1.5,
    )

    assert result.schema_version == 1
    assert pickle.loads(pickle.dumps(result)) == result


def test_rapthor_records_expose_two_branch_compatibility_products() -> None:
    """The adapter, rather than the scientific API, owns Rapthor products."""
    request = RapthorSourceFindingRequest(
        flat_noise_image_path=Path("apparent.fits"),
        primary_beam_corrected_image_path=Path("pb.fits"),
        sector_vertices_path=Path("vertices.npy"),
        output_directory=Path("products"),
        run_id="rapthor-sector-1",
        apparent_sky_model_path=Path("apparent.txt"),
        intrinsic_sky_model_path=Path("intrinsic.txt"),
        beam_measurement_set_paths=(Path("observation.ms"),),
    )
    result = RapthorSourceFindingResult(
        catalogue_path=Path("source_catalog.fits"),
        primary_beam_corrected_rms_path=Path("true_sky_rms.fits"),
        flat_noise_rms_path=Path("flat_noise_rms.fits"),
        source_filtering_mask_path=Path("mask.fits"),
        filtered_intrinsic_sky_model_path=Path("true_sky.txt"),
        filtered_apparent_sky_model_path=Path("apparent_sky.txt"),
        diagnostics_path=Path("diagnostics.json"),
        source_count=2,
        wall_seconds=3.0,
    )

    assert request.schema_version == result.schema_version == 1
    assert pickle.loads(pickle.dumps(request)) == request
    assert pickle.loads(pickle.dumps(result)) == result


def test_rapthor_profile_composes_explicit_scientific_thresholds() -> None:
    """Workflow compatibility options do not become universal defaults."""
    config = RapthorCompatibilityConfig(
        source_finder=SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
        )
    )

    assert config.source_finder.detection_threshold_sigma == 5.0
    assert config.rms_box_pixels == (150, 50)
    assert config.bright_source_rms_box_pixels == (35, 7)
    assert config.adaptive_rms_threshold_sigma == 75.0
