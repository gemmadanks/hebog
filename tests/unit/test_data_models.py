"""Tests for scheduler-safe request and result records."""

import json
import pickle
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

import hebog.data_models as domain_models
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
            minimum_island_pixels=6,
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


def test_multiscale_records_are_scheduler_safe_and_fail_closed() -> None:
    """Phase 5 records preserve provenance and block incomplete publication."""
    detection = domain_models.ScaleDetection(
        detection_id="scale-detection-0001",
        parent_island_id="island-0001",
        scale_order=2,
        nominal_scale_beam_fwhm=2.0,
        support_pixel_count=80,
        valid_support_fraction=0.8,
        bounds_yx=(10, 20, 30, 42),
        canonical_pixel_yx=(12, 35),
        peak_response_jy_per_beam=0.0016,
        peak_signal_to_noise=8.0,
        touches_image_edge=False,
    )
    association = domain_models.CrossScaleAssociation(
        association_id="scale-association-0001",
        scale_detection_ids=(detection.detection_id,),
        compact_source_ids=("source-0001",),
        selected_scale_detection_id=detection.detection_id,
        contributing_scale_orders=(2,),
        relationship="contains-compact-support",
    )
    measurement = domain_models.ExtendedEmissionMeasurement(
        association_id=association.association_id,
        centroid_xy=(35.5, 14.0),
        centroid_kind="detected-segment-flux-centroid",
        peak_position_xy=(36, 14),
        host_position_claim=False,
        position_covariance_pixels_squared=None,
        position_uncertainty_status="unavailable",
        peak_flux_jy_per_beam=0.002,
        integrated_flux_jy=0.05,
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=0.0002,
        support_pixel_count=80,
        major_extent_beams=3.0,
        minor_extent_beams=1.5,
        position_angle_degrees=25.0,
        visible_model_fraction=0.95,
        flux_uncertainty_status="unavailable",
    )
    omission = domain_models.MultiscaleOmission(
        object_id=association.association_id,
        stage="extended-measurement",
        reason="insufficient-valid-support",
    )
    disposition = domain_models.CombinedIslandDisposition(
        island_id="island-0001",
        status="failed",
        source_ids=(),
        association_ids=(association.association_id,),
        reason=omission.reason,
    )
    state = domain_models.CombinedCatalogueState(
        catalogue_id="catalogue-0001",
        accepted_island_ids=("island-0001",),
        deferred_island_ids=(),
        dispositions=(disposition,),
        omissions=(omission,),
    )

    assert measurement.centroid_kind == "detected-segment-flux-centroid"
    assert measurement.peak_position_xy == (36, 14)
    assert measurement.host_position_claim is False
    assert measurement.position_uncertainty_status == "unavailable"
    assert measurement.flux_uncertainty_status == "unavailable"
    assert measurement.schema_version == 3
    assert state.publication_eligible is False
    assert pickle.loads(pickle.dumps(state)) == state


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"source_id": "bad ID"}, "domain identifier"),
        (
            {
                "scale_detection_ids": (
                    "scale-detection-two",
                    "scale-detection-one",
                )
            },
            "canonical",
        ),
        ({"selected_scale_detection_id": "scale-detection-two"}, "selected"),
        ({"contributing_scale_orders": ()}, "positive and canonical"),
        ({"support_pixel_count": 0}, "positive"),
        ({"visible_model_fraction": float("inf")}, "finite"),
    ],
)
def test_source_scale_provenance_rejects_incomplete_evidence(
    update: dict[str, object],
    message: str,
) -> None:
    """Published extended provenance is canonical and scientifically finite."""
    payload: dict[str, object] = {
        "source_id": "source-extended",
        "island_id": "island-combined",
        "association_id": "scale-association-extended",
        "scale_detection_ids": ("scale-detection-one",),
        "selected_scale_detection_id": "scale-detection-one",
        "contributing_scale_orders": (1,),
        "relationship": "extended-only",
        "support_pixel_count": 12,
        "visible_model_fraction": 0.9,
    }
    payload.update(update)

    with pytest.raises(ValidationError, match=message):
        domain_models.SourceScaleProvenance.model_validate(payload)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"run_id": ""}, "must not be empty"),
        ({"extended_source_count": 2}, "fit the source population"),
        ({"extended_source_count": 0}, "match source provenance"),
        ({"terminal_disposition_count": 0}, "cannot be fewer"),
    ],
)
def test_continuum_diagnostics_rejects_inconsistent_populations(
    update: dict[str, object],
    message: str,
) -> None:
    """Version-two diagnostics cannot detach provenance from populations."""
    provenance = domain_models.SourceScaleProvenance(
        source_id="source-extended",
        island_id="island-combined",
        association_id="scale-association-extended",
        scale_detection_ids=("scale-detection-one",),
        selected_scale_detection_id="scale-detection-one",
        contributing_scale_orders=(1,),
        relationship="extended-only",
        support_pixel_count=12,
        visible_model_fraction=0.9,
    )
    payload: dict[str, object] = {
        "run_id": "run-one",
        "source_count": 1,
        "gaussian_component_count": 0,
        "island_count": 1,
        "extended_source_count": 1,
        "terminal_disposition_count": 1,
        "rms_scientific_status": "valid",
        "source_provenance": (provenance,),
    }
    payload.update(update)

    with pytest.raises(ValidationError, match=message):
        domain_models.ContinuumSourceFindingDiagnostics.model_validate(payload)


def test_cross_scale_association_requires_selected_detection_membership() -> (
    None
):
    """A selected representation must retain its scale provenance."""
    with pytest.raises(ValidationError, match="selected scale detection"):
        domain_models.CrossScaleAssociation(
            association_id="scale-association-0001",
            scale_detection_ids=("scale-detection-0001",),
            compact_source_ids=(),
            selected_scale_detection_id="scale-detection-0002",
            contributing_scale_orders=(1,),
            relationship="extended-only",
        )


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"detection_id": "bad ID"}, "domain identifier"),
        ({"parent_island_id": "bad ID"}, "domain identifier"),
        ({"bounds_yx": (10, 10, 30, 42)}, "increasing"),
        ({"canonical_pixel_yx": (25, 35)}, "inside bounds"),
        ({"nominal_scale_beam_fwhm": float("inf")}, "finite"),
        ({"peak_response_jy_per_beam": float("inf")}, "finite"),
        ({"peak_signal_to_noise": float("inf")}, "finite"),
    ],
)
def test_scale_detection_rejects_invalid_geometry(
    update: dict[str, object],
    message: str,
) -> None:
    """Scale detections fail before noncanonical state can cross a task."""
    payload: dict[str, object] = {
        "detection_id": "scale-detection-0001",
        "parent_island_id": "island-0001",
        "scale_order": 2,
        "nominal_scale_beam_fwhm": 2.0,
        "support_pixel_count": 80,
        "valid_support_fraction": 0.8,
        "bounds_yx": (10, 20, 30, 42),
        "canonical_pixel_yx": (12, 35),
        "peak_response_jy_per_beam": 0.0016,
        "peak_signal_to_noise": 8.0,
        "touches_image_edge": False,
    }
    payload.update(update)

    with pytest.raises(ValidationError, match=message):
        domain_models.ScaleDetection.model_validate(payload)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (
            {
                "scale_detection_ids": (
                    "scale-detection-0002",
                    "scale-detection-0001",
                )
            },
            "unique and canonical",
        ),
        ({"association_id": "bad ID"}, "domain identifier"),
        ({"contributing_scale_orders": (2, 1)}, "canonical"),
        (
            {"relationship": "contains-compact-support"},
            "requires a compact source",
        ),
        (
            {"relationship": "overlaps-compact-support"},
            "requires a compact source",
        ),
        (
            {"compact_source_ids": ("source-0001",)},
            "cannot name a compact source",
        ),
    ],
)
def test_cross_scale_association_rejects_noncanonical_inputs(
    update: dict[str, object],
    message: str,
) -> None:
    """Cross-scale identities are independent of completion order."""
    payload: dict[str, object] = {
        "association_id": "scale-association-0001",
        "scale_detection_ids": ("scale-detection-0001",),
        "compact_source_ids": (),
        "selected_scale_detection_id": "scale-detection-0001",
        "contributing_scale_orders": (1,),
        "relationship": "extended-only",
    }
    payload.update(update)

    with pytest.raises(ValidationError, match=message):
        domain_models.CrossScaleAssociation.model_validate(payload)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"association_id": "bad ID"}, "domain identifier"),
        ({"centroid_xy": (float("inf"), 1.0)}, "finite"),
        ({"peak_position_xy": (-1, 14)}, "non-negative"),
        ({"minor_extent_beams": 4.0}, "cannot exceed"),
        ({"position_angle_degrees": 180.0}, "within"),
        (
            {"integrated_flux_error_jy": 0.01},
            "status must match",
        ),
    ],
)
def test_extended_measurement_rejects_invalid_science_state(
    update: dict[str, object],
    message: str,
) -> None:
    """Extended measurements never encode invalid geometry or uncertainty."""
    payload: dict[str, object] = {
        "association_id": "scale-association-0001",
        "centroid_xy": (35.5, 14.0),
        "centroid_kind": "detected-segment-flux-centroid",
        "peak_position_xy": (36, 14),
        "host_position_claim": False,
        "position_covariance_pixels_squared": None,
        "position_uncertainty_status": "unavailable",
        "peak_flux_jy_per_beam": 0.002,
        "integrated_flux_jy": 0.05,
        "integrated_flux_error_jy": None,
        "local_rms_jy_per_beam": 0.0002,
        "support_pixel_count": 80,
        "major_extent_beams": 3.0,
        "minor_extent_beams": 1.5,
        "position_angle_degrees": 25.0,
        "visible_model_fraction": 0.95,
        "flux_uncertainty_status": "unavailable",
    }
    payload.update(update)

    with pytest.raises(ValidationError, match=message):
        domain_models.ExtendedEmissionMeasurement.model_validate(payload)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"source_ids": ()}, "requires a source"),
        ({"status": "accepted-multiscale"}, "requires association"),
        ({"status": "rejected-artifact"}, "requires a reason"),
        ({"reason": "unexpected-failure"}, "cannot carry"),
        ({"source_ids": ("source-0002", "source-0001")}, "canonical"),
    ],
)
def test_combined_disposition_rejects_incomplete_terminal_state(
    update: dict[str, object],
    message: str,
) -> None:
    """Every island disposition carries evidence appropriate to its state."""
    payload: dict[str, object] = {
        "island_id": "island-0001",
        "status": "retained-compact",
        "source_ids": ("source-0001",),
        "association_ids": (),
        "reason": None,
    }
    payload.update(update)

    with pytest.raises(ValidationError, match=message):
        domain_models.CombinedIslandDisposition.model_validate(payload)


def test_complete_multiscale_state_is_publication_eligible() -> None:
    """A canonical non-failed terminal state can be published."""
    disposition = domain_models.CombinedIslandDisposition(
        island_id="island-0001",
        status="accepted-multiscale",
        source_ids=(),
        association_ids=("scale-association-0001",),
        reason=None,
    )
    state = domain_models.CombinedCatalogueState(
        catalogue_id="catalogue-0001",
        accepted_island_ids=("island-0001",),
        deferred_island_ids=(),
        dispositions=(disposition,),
        omissions=(),
    )

    assert state.publication_eligible is True


def test_multiscale_omissions_and_state_require_canonical_identifiers() -> (
    None
):
    """Fail-closed state retains machine-readable canonical identities."""
    with pytest.raises(ValidationError, match="domain identifier"):
        domain_models.MultiscaleOmission(
            object_id="scale-association-0001",
            stage="extended-measurement",
            reason="not machine readable",
        )

    dispositions = tuple(
        domain_models.CombinedIslandDisposition(
            island_id=island_id,
            status="retained-compact",
            source_ids=(source_id,),
            association_ids=(),
            reason=None,
        )
        for island_id, source_id in (
            ("island-0002", "source-0002"),
            ("island-0001", "source-0001"),
        )
    )
    with pytest.raises(ValidationError, match="unique and canonical"):
        domain_models.CombinedCatalogueState(
            catalogue_id="catalogue-0001",
            accepted_island_ids=("island-0001", "island-0002"),
            deferred_island_ids=(),
            dispositions=dispositions,
            omissions=(),
        )


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
