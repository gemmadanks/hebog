"""Tests for scheduler-safe request and result records."""

import json
import pickle
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from hebog import SourceFinderRequest, SourceFinderResult
from hebog.adapters.rapthor import (
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
)
from hebog.config import SourceFinderConfig
from hebog.data_models import (
    CelestialWcs,
    ImageMetadata,
    MaterializedProduct,
    RestoringBeam,
    SourceFindingDiagnostics,
)


def _source_finder_request() -> SourceFinderRequest:
    """Return one valid pipeline-neutral request for mutation tests."""
    return SourceFinderRequest(
        image_path=Path("image.fits"),
        output_directory=Path("output"),
        run_id="test-run",
    )


def _materialized_product(
    role: Literal[
        "source-catalogue",
        "rms",
        "source-filtering-mask",
        "diagnostics",
    ],
    path: str,
    *,
    scientific_status: Literal["valid", "unavailable"] = "valid",
) -> MaterializedProduct:
    """Return one closed file identity without reading its contents."""
    if role == "source-catalogue":
        media_type = "application/fits"
    elif role == "diagnostics":
        media_type = "application/json"
    else:
        media_type = "image/fits"
    return MaterializedProduct(
        product_role=role,
        path=Path(path),
        media_type=media_type,
        byte_count=2880,
        content_sha256="a" * 64,
        scientific_status=scientific_status,
        content_schema_version=1,
    )


def _source_finder_result(
    *,
    rms_status: Literal["valid", "unavailable"] = "valid",
) -> SourceFinderResult:
    """Return one valid pipeline-neutral result for mutation tests."""
    return SourceFinderResult(
        run_id="test-run",
        catalogue=_materialized_product(
            "source-catalogue",
            "catalogue.fits",
        ),
        rms=_materialized_product(
            "rms",
            "rms.fits",
            scientific_status=rms_status,
        ),
        mask=_materialized_product("source-filtering-mask", "mask.fits"),
        diagnostics=_materialized_product(
            "diagnostics",
            "diagnostics.json",
        ),
        source_count=2,
        gaussian_component_count=3,
        island_count=1,
        wall_seconds=1.5,
    )


def _source_finding_diagnostics() -> SourceFindingDiagnostics:
    """Return one valid diagnostics document for boundary tests."""
    return SourceFindingDiagnostics(
        run_id="test-run",
        source_count=2,
        gaussian_component_count=3,
        island_count=1,
        rms_scientific_status="valid",
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


def _image_metadata() -> ImageMetadata:
    """Return valid plain image metadata for mutation tests."""
    return ImageMetadata(
        shape_yx=(32, 48),
        unit="Jy/beam",
        beam=RestoringBeam(
            major_fwhm_degrees=0.01,
            minor_fwhm_degrees=0.008,
            position_angle_degrees=20.0,
        ),
        celestial_wcs=CelestialWcs(
            fits_header="CTYPE1 = 'RA---SIN'",
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )


def test_request_is_pickle_serializable() -> None:
    """Dask can serialize the public request record."""
    request = _source_finder_request()

    assert pickle.loads(pickle.dumps(request)) == request


def test_result_exposes_one_pipeline_neutral_product_set() -> None:
    """One scientific analysis returns one catalogue, RMS, and mask set."""
    result = _source_finder_result()

    assert result.schema_version == 2
    assert result.catalogue_path == Path("catalogue.fits")
    assert result.rms_path == Path("rms.fits")
    assert result.mask_path == Path("mask.fits")
    assert result.diagnostics_path == Path("diagnostics.json")
    assert (
        SourceFinderResult.from_json_bytes(result.canonical_json_bytes())
        == result
    )
    assert pickle.loads(pickle.dumps(result)) == result

    pretty = json.dumps(result.model_dump(mode="json"), indent=2).encode()
    with pytest.raises(ValueError, match="canonical"):
        SourceFinderResult.from_json_bytes(pretty)


def test_result_can_mark_rms_science_unavailable_without_a_fake_estimate() -> (
    None
):
    """All-blank input remains successful without relabelling pixels as RMS."""
    result = _source_finder_result(rms_status="unavailable")

    assert result.source_count == 2
    assert result.rms.scientific_status == "unavailable"
    assert result.rms_path == Path("rms.fits")


def test_materialized_product_is_versioned_and_pickle_safe() -> None:
    """A closed artifact carries a portable role, format, and identity."""
    product = _materialized_product("source-catalogue", "catalogue.fits")

    assert product.schema_version == 1
    assert product.content_schema_version == 1
    assert pickle.loads(pickle.dumps(product)) == product


def test_source_finding_diagnostics_is_canonical_and_pickle_safe() -> None:
    """Diagnostics expose deterministic, strict restart metadata."""
    diagnostics = _source_finding_diagnostics()

    assert (
        SourceFindingDiagnostics.from_json_bytes(
            diagnostics.canonical_json_bytes()
        )
        == diagnostics
    )
    assert pickle.loads(pickle.dumps(diagnostics)) == diagnostics

    pretty = json.dumps(diagnostics.model_dump(mode="json"), indent=2).encode()
    with pytest.raises(ValueError, match="canonical"):
        SourceFindingDiagnostics.from_json_bytes(pretty)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"run_id": ""}, "run ID"),
        ({"source_count": -1}, "source_count"),
        (
            {"source_count": 0, "gaussian_component_count": 1},
            "components require",
        ),
        ({"source_count": 1, "island_count": 0}, "sources require"),
    ],
)
def test_source_finding_diagnostics_rejects_inconsistent_counts(
    updates: dict[str, object],
    message: str,
) -> None:
    """Diagnostics never report impossible scientific populations."""
    document = _source_finding_diagnostics().model_dump()
    document.update(updates)

    with pytest.raises(ValidationError, match=message):
        SourceFindingDiagnostics.model_validate(document)


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
        ({"schema_version": 1}, "schema_version"),
        ({"run_id": ""}, "run ID"),
        ({"source_count": -1}, "source_count cannot be negative"),
        (
            {"gaussian_component_count": -1},
            "gaussian_component_count cannot be negative",
        ),
        ({"island_count": -1}, "island_count cannot be negative"),
        ({"wall_seconds": float("nan")}, "wall_seconds must be finite"),
        ({"wall_seconds": -1.0}, "wall_seconds must be finite"),
    ],
)
def test_source_finder_result_rejects_invalid_metadata(
    changes: dict[str, object],
    message: str,
) -> None:
    """Pipeline-neutral result metadata fails at construction time."""
    document = _source_finder_result().model_dump(mode="python")
    document.update(changes)

    with pytest.raises(ValidationError, match=message):
        SourceFinderResult.model_validate(document)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"path": Path(".")}, "file path"),
        ({"byte_count": 0}, "byte count"),
        ({"content_sha256": "not-a-checksum"}, "SHA-256"),
        ({"content_schema_version": 0}, "content schema version"),
        ({"media_type": "image/fits"}, "media type"),
        ({"byte_count": "2880"}, "byte_count"),
    ],
)
def test_materialized_product_rejects_invalid_identity_or_format(
    changes: dict[str, object],
    message: str,
) -> None:
    """Restart metadata cannot ambiguously identify an output file."""
    document = _materialized_product(
        "source-catalogue",
        "catalogue.fits",
    ).model_dump(mode="python")
    document.update(changes)

    with pytest.raises(ValidationError, match=message):
        MaterializedProduct.model_validate(document)


def test_result_rejects_wrong_roles_paths_statuses_and_counts() -> None:
    """The public result exposes exactly one scientifically labelled set."""
    valid = _source_finder_result().model_dump(mode="python")
    cases = (
        (
            {"catalogue": _materialized_product("rms", "other.fits")},
            "catalogue product role",
        ),
        (
            {"rms": _materialized_product("rms", "catalogue.fits")},
            "paths must be distinct",
        ),
        (
            {
                "catalogue": _materialized_product(
                    "source-catalogue",
                    "catalogue.fits",
                    scientific_status="unavailable",
                )
            },
            "only RMS may be scientifically unavailable",
        ),
        (
            {
                "source_count": 0,
                "gaussian_component_count": 1,
                "island_count": 1,
            },
            "components require a source",
        ),
        (
            {
                "source_count": 1,
                "gaussian_component_count": 0,
                "island_count": 0,
            },
            "sources require an island",
        ),
    )

    for changes, message in cases:
        document = dict(valid)
        document.update(changes)
        with pytest.raises(ValidationError, match=message):
            SourceFinderResult.model_validate(document)


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


def test_image_metadata_is_small_and_pickle_serializable() -> None:
    """Workers receive physical metadata rather than live Astropy objects."""
    metadata = _image_metadata()

    assert metadata.celestial_wcs.coordinate_frame == "icrs"
    assert pickle.loads(pickle.dumps(metadata)) == metadata


@pytest.mark.parametrize("field", ["fits_header", "coordinate_frame"])
def test_celestial_wcs_rejects_missing_serialized_metadata(field: str) -> None:
    """A worker must be able to reconstruct and identify the celestial WCS."""
    with pytest.raises(ValueError, match="must not be empty"):
        replace(_image_metadata().celestial_wcs, **{field: ""})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"major_fwhm_degrees": float("nan")}, "must be finite"),
        ({"major_fwhm_degrees": 0.0}, "axes must be positive"),
        ({"minor_fwhm_degrees": 0.0}, "axes must be positive"),
        ({"minor_fwhm_degrees": 0.02}, "cannot exceed major"),
    ],
)
def test_restoring_beam_rejects_invalid_geometry(
    changes: dict[str, object],
    message: str,
) -> None:
    """Beam records fail before they reach a scientific kernel."""
    with pytest.raises(ValueError, match=message):
        replace(_image_metadata().beam, **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "schema version"),
        ({"shape_yx": (0, 2)}, "shape dimensions"),
        ({"unit": ""}, "unit must not be empty"),
        ({"reference_frequency_hz": float("nan")}, "finite and positive"),
        ({"reference_frequency_hz": 0.0}, "finite and positive"),
    ],
)
def test_image_metadata_rejects_incomplete_physical_values(
    changes: dict[str, object],
    message: str,
) -> None:
    """Versioned metadata never guesses missing scientific semantics."""
    with pytest.raises(ValueError, match=message):
        replace(_image_metadata(), **changes)
