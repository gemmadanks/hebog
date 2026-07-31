"""Tests for scheduler-safe request and result records."""

import pickle
from dataclasses import replace
from pathlib import Path

import pytest

from hebog import SourceFinderRequest, SourceFinderResult
from hebog.adapters.rapthor import (
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
)
from hebog.config import SourceFinderConfig


def _source_finder_request() -> SourceFinderRequest:
    """Return one valid pipeline-neutral request for mutation tests."""
    return SourceFinderRequest(
        image_path=Path("image.fits"),
        output_directory=Path("output"),
        run_id="test-run",
    )


def _source_finder_result() -> SourceFinderResult:
    """Return one valid pipeline-neutral result for mutation tests."""
    return SourceFinderResult(
        catalogue_path=Path("catalogue.fits"),
        rms_path=Path("rms.fits"),
        mask_path=Path("mask.fits"),
        diagnostics_path=Path("diagnostics.json"),
        source_count=2,
        wall_seconds=1.5,
    )


def _rapthor_request() -> RapthorSourceFindingRequest:
    """Return one valid Rapthor request for mutation tests."""
    return RapthorSourceFindingRequest(
        flat_noise_image_path=Path("apparent.fits"),
        primary_beam_corrected_image_path=Path("pb.fits"),
        sector_vertices_path=Path("vertices.npy"),
        output_directory=Path("products"),
        run_id="rapthor-sector-1",
    )


def _rapthor_result() -> RapthorSourceFindingResult:
    """Return one valid Rapthor result for mutation tests."""
    return RapthorSourceFindingResult(
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


def _rapthor_config() -> RapthorCompatibilityConfig:
    """Return one valid compatibility profile for mutation tests."""
    return RapthorCompatibilityConfig(
        source_finder=SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
        )
    )


def test_request_is_pickle_serializable() -> None:
    """Dask can serialize the public request record."""
    request = _source_finder_request()

    assert pickle.loads(pickle.dumps(request)) == request


def test_result_exposes_one_pipeline_neutral_product_set() -> None:
    """One scientific analysis returns one catalogue, RMS, and mask set."""
    result = _source_finder_result()

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
    config = _rapthor_config()

    assert config.source_finder.detection_threshold_sigma == 5.0
    assert config.rms_box_pixels == (150, 50)
    assert config.bright_source_rms_box_pixels == (35, 7)
    assert config.adaptive_rms_threshold_sigma == 75.0


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "unsupported source-finder request"),
        ({"run_id": ""}, "run_id must not be empty"),
    ],
)
def test_source_finder_request_rejects_invalid_metadata(
    changes: dict[str, object],
    message: str,
) -> None:
    """Pipeline-neutral request metadata fails at construction time."""
    with pytest.raises(ValueError, match=message):
        replace(_source_finder_request(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "unsupported source-finder result"),
        ({"source_count": -1}, "source_count cannot be negative"),
        ({"wall_seconds": float("nan")}, "wall_seconds must be finite"),
        ({"wall_seconds": -1.0}, "wall_seconds must be finite"),
    ],
)
def test_source_finder_result_rejects_invalid_metadata(
    changes: dict[str, object],
    message: str,
) -> None:
    """Pipeline-neutral result metadata fails at construction time."""
    with pytest.raises(ValueError, match=message):
        replace(_source_finder_result(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "unsupported Rapthor request"),
        ({"run_id": ""}, "run_id must not be empty"),
    ],
)
def test_rapthor_request_rejects_invalid_metadata(
    changes: dict[str, object],
    message: str,
) -> None:
    """Rapthor request metadata fails at the compatibility boundary."""
    with pytest.raises(ValueError, match=message):
        replace(_rapthor_request(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "unsupported Rapthor result"),
        ({"source_count": -1}, "source_count cannot be negative"),
        ({"wall_seconds": float("nan")}, "wall_seconds must be finite"),
        ({"wall_seconds": -1.0}, "wall_seconds must be finite"),
    ],
)
def test_rapthor_result_rejects_invalid_metadata(
    changes: dict[str, object],
    message: str,
) -> None:
    """Rapthor result metadata fails at the compatibility boundary."""
    with pytest.raises(ValueError, match=message):
        replace(_rapthor_result(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"rms_box_pixels": (0, 1)}, "width and step must be positive"),
        ({"rms_box_pixels": (1, 0)}, "width and step must be positive"),
        ({"rms_box_pixels": (1, 2)}, "step cannot exceed its width"),
        (
            {"bright_source_rms_box_pixels": (0, 1)},
            "bright_source_rms_box_pixels",
        ),
        (
            {"adaptive_rms_threshold_sigma": float("nan")},
            "adaptive_rms_threshold_sigma",
        ),
        (
            {"adaptive_rms_threshold_sigma": 0.0},
            "adaptive_rms_threshold_sigma",
        ),
        ({"multiscale_levels": 0}, "multiscale_levels must be positive"),
    ],
)
def test_rapthor_profile_rejects_invalid_compatibility_values(
    changes: dict[str, object],
    message: str,
) -> None:
    """Invalid workflow compatibility values fail before execution."""
    with pytest.raises(ValueError, match=message):
        replace(_rapthor_config(), **changes)
