"""Contracts for versioned pipeline-neutral catalogue records."""

from __future__ import annotations

import json
import pickle

import pytest
from pydantic import BaseModel, ValidationError

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


def _position() -> SkyPosition:
    """Return one ICRS position with an unavailable declination error."""
    return SkyPosition(
        right_ascension_degrees=180.25,
        declination_degrees=-30.5,
        right_ascension_error_degrees=0.0001,
        declination_error_degrees=None,
    )


def _flux() -> FluxMeasurement:
    """Return canonical source photometry and its local noise."""
    return FluxMeasurement(
        peak_flux_jy_per_beam=0.01,
        peak_flux_error_jy_per_beam=0.001,
        integrated_flux_jy=0.012,
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=0.0002,
    )


def _shape() -> GaussianShape:
    """Return one fitted FWHM ellipse in canonical sky coordinates."""
    return GaussianShape(
        major_fwhm_degrees=0.002,
        minor_fwhm_degrees=0.001,
        position_angle_degrees=45.0,
        major_fwhm_error_degrees=0.0001,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=2.0,
    )


def _spectrum(
    *, reference_frequency_hz: float = 150_000_000.0
) -> SpectralModel:
    """Return an explicit MFS measurement without a spectral fit."""
    return SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=reference_frequency_hz,
        coefficients=(),
    )


def _island(*, island_id: str = "island-00001") -> Island:
    """Return one measured above-threshold island."""
    return Island(
        island_id=island_id,
        pixel_count=24,
        integrated_flux_jy=0.013,
        integrated_flux_error_jy=0.001,
        local_rms_jy_per_beam=0.0002,
        mean_brightness_jy_per_beam=-0.00001,
    )


def _source(
    *,
    source_id: str = "source-00001",
    island_id: str = "island-00001",
) -> SourceCandidate:
    """Return one catalogue-level association with no deconvolved shape."""
    return SourceCandidate(
        source_id=source_id,
        island_id=island_id,
        position=_position(),
        flux=_flux(),
        spectral_model=_spectrum(),
        fitted_shape=_shape(),
        deconvolved_shape=None,
        quality_flags=("deblended", "edge-truncated"),
        restoring_beam_aperture_integrated_flux_jy=0.011,
    )


def _component(
    *,
    component_id: str = "gaussian-component-00001",
    source_id: str = "source-00001",
    island_id: str = "island-00001",
) -> GaussianComponent:
    """Return one fitted Gaussian assigned to a source and island."""
    return GaussianComponent(
        gaussian_component_id=component_id,
        source_id=source_id,
        island_id=island_id,
        position=_position(),
        flux=_flux(),
        spectral_model=_spectrum(),
        fitted_shape=_shape(),
        deconvolved_shape=None,
        quality_flags=(),
    )


def _catalogue() -> SourceCatalogue:
    """Return one internally consistent MFS catalogue."""
    return SourceCatalogue.create(
        catalogue_id="catalogue-run-001",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150_000_000.0,
        islands=(_island(),),
        sources=(_source(),),
        gaussian_components=(_component(),),
    )


def _document(model: BaseModel) -> dict[str, object]:
    """Return a mutable typed Pydantic document."""
    return model.model_dump(mode="python")


def test_catalogue_round_trip_is_canonical_and_pickle_safe() -> None:
    """Executor payloads and persisted schema metadata are deterministic."""
    catalogue = _catalogue()

    assert catalogue.schema_version == 2
    assert catalogue.coordinate_frame == "icrs"
    assert catalogue.sources[0].deconvolved_shape is None
    assert catalogue.sources[0].position.declination_error_degrees is None
    assert catalogue.sources[0].flux.integrated_flux_error_jy is None
    assert (
        catalogue.sources[0].restoring_beam_aperture_integrated_flux_jy
        == 0.011
    )
    assert (
        SourceCatalogue.from_json_bytes(catalogue.canonical_json_bytes())
        == catalogue
    )
    assert catalogue.canonical_json_bytes().endswith(b"\n")
    assert pickle.loads(pickle.dumps(catalogue)) == catalogue

    pretty = json.dumps(catalogue.model_dump(mode="json"), indent=2).encode()
    with pytest.raises(ValueError, match="canonical"):
        SourceCatalogue.from_json_bytes(pretty)


def test_empty_catalogue_is_valid_without_dummy_science_rows() -> None:
    """No detections is a valid result and needs no synthetic component."""
    catalogue = SourceCatalogue.create(
        catalogue_id="catalogue-empty",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150_000_000.0,
        islands=(),
        sources=(),
        gaussian_components=(),
    )

    assert catalogue.islands == ()
    assert catalogue.sources == ()
    assert catalogue.gaussian_components == ()
    assert (
        SourceCatalogue.from_json_bytes(catalogue.canonical_json_bytes())
        == catalogue
    )


def test_source_candidate_can_use_non_gaussian_measurements() -> None:
    """A catalogue source does not require a fitted Gaussian component."""
    document = _document(_source())
    document["fitted_shape"] = None

    source = SourceCandidate.model_validate(document)

    assert source.fitted_shape is None


def test_catalogue_create_orders_each_identity_class_canonically() -> None:
    """Worker completion order cannot change catalogue serialization."""
    catalogue = SourceCatalogue.create(
        catalogue_id="catalogue-run-001",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150_000_000.0,
        islands=(
            _island(island_id="island-00002"),
            _island(),
        ),
        sources=(
            _source(
                source_id="source-00002",
                island_id="island-00002",
            ),
            _source(),
        ),
        gaussian_components=(
            _component(
                component_id="gaussian-component-00002",
                source_id="source-00002",
                island_id="island-00002",
            ),
            _component(),
        ),
    )

    assert tuple(item.island_id for item in catalogue.islands) == (
        "island-00001",
        "island-00002",
    )
    assert tuple(item.source_id for item in catalogue.sources) == (
        "source-00001",
        "source-00002",
    )
    assert tuple(
        item.gaussian_component_id for item in catalogue.gaussian_components
    ) == (
        "gaussian-component-00001",
        "gaussian-component-00002",
    )


@pytest.mark.parametrize(
    ("section", "replacement", "message"),
    [
        ("islands", (_island(), _island()), "island IDs must be unique"),
        ("sources", (_source(), _source()), "source IDs must be unique"),
        (
            "gaussian_components",
            (_component(), _component()),
            "Gaussian component IDs must be unique",
        ),
        (
            "sources",
            (_source(island_id="island-missing"),),
            "unknown island",
        ),
        (
            "gaussian_components",
            (_component(source_id="source-missing"),),
            "unknown source",
        ),
        (
            "gaussian_components",
            (_component(island_id="island-missing"),),
            "source and Gaussian component must share an island",
        ),
    ],
)
def test_catalogue_rejects_ambiguous_or_broken_relationships(
    section: str,
    replacement: tuple[BaseModel, ...],
    message: str,
) -> None:
    """Stable identities and source-component-island links fail closed."""
    document = _document(_catalogue())
    document[section] = tuple(_document(item) for item in replacement)

    with pytest.raises(ValidationError, match=message):
        SourceCatalogue.model_validate(document)


def test_catalogue_rejects_noncanonical_persisted_order() -> None:
    """Stored catalogues cannot depend on executor completion order."""
    catalogue = SourceCatalogue.create(
        catalogue_id="catalogue-run-001",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150_000_000.0,
        islands=(
            _island(),
            _island(island_id="island-00002"),
        ),
        sources=(),
        gaussian_components=(),
    )
    document = _document(catalogue)
    document["islands"] = tuple(reversed(document["islands"]))  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="canonical order"):
        SourceCatalogue.model_validate(document)


def test_catalogue_rejects_mixed_reference_frequencies() -> None:
    """MFS catalogue fluxes cannot silently refer to different frequencies."""
    source = _document(_source())
    source["spectral_model"] = _document(
        _spectrum(reference_frequency_hz=200_000_000.0)
    )
    document = _document(_catalogue())
    document["sources"] = (source,)

    with pytest.raises(ValidationError, match="reference frequency"):
        SourceCatalogue.model_validate(document)


def test_catalogue_rejects_coerced_interchange_types() -> None:
    """Persisted schema fields cannot change type through coercion."""
    document = _document(_catalogue())
    document["reference_frequency_hz"] = "150000000"

    with pytest.raises(ValidationError, match="reference_frequency_hz"):
        SourceCatalogue.model_validate(document)


@pytest.mark.parametrize(
    ("model", "changes", "message"),
    [
        (_position(), {"right_ascension_degrees": 360.0}, "right ascension"),
        (_position(), {"declination_degrees": -90.1}, "declination"),
        (
            _position(),
            {"right_ascension_error_degrees": -0.1},
            "position errors",
        ),
        (_flux(), {"peak_flux_jy_per_beam": 0.0}, "fluxes must be positive"),
        (
            _flux(),
            {"integrated_flux_error_jy": -0.1},
            "flux errors",
        ),
        (
            _flux(),
            {"local_rms_jy_per_beam": float("nan")},
            "local RMS",
        ),
        (_shape(), {"minor_fwhm_degrees": 0.003}, "minor axis"),
        (_shape(), {"major_fwhm_degrees": 0.0}, "axes"),
        (_shape(), {"position_angle_degrees": 180.0}, "position angle"),
        (
            _shape(),
            {"major_fwhm_error_degrees": -0.1},
            "shape errors",
        ),
        (
            _spectrum(),
            {"reference_frequency_hz": 0.0},
            "reference frequency",
        ),
        (
            _spectrum(),
            {"kind": "log-polynomial", "coefficients": (float("nan"),)},
            "coefficients",
        ),
        (
            _spectrum(),
            {"kind": "reference-frequency-only", "coefficients": (-0.7,)},
            "must not contain coefficients",
        ),
        (
            _spectrum(),
            {"kind": "log-polynomial", "coefficients": ()},
            "requires coefficients",
        ),
    ],
)
def test_measurements_reject_noncanonical_physical_values(
    model: BaseModel,
    changes: dict[str, object],
    message: str,
) -> None:
    """Canonical units still require valid physical domains and nulls."""
    document = _document(model)
    document.update(changes)

    with pytest.raises(ValidationError, match=message):
        type(model).model_validate(document)


@pytest.mark.parametrize(
    ("model", "changes", "message"),
    [
        (_source(), {"source_id": "../source"}, "domain identifier"),
        (
            _source(),
            {"restoring_beam_aperture_integrated_flux_jy": 0.0},
            "aperture flux",
        ),
        (
            _source(),
            {"quality_flags": ("edge-truncated", "deblended")},
            "quality flags must be unique and canonical",
        ),
        (_island(), {"pixel_count": 0}, "pixel count"),
        (_island(), {"integrated_flux_jy": 0.0}, "integrated flux"),
        (
            _island(),
            {"local_rms_jy_per_beam": float("nan")},
            "local RMS",
        ),
        (
            _island(),
            {"mean_brightness_jy_per_beam": float("nan")},
            "mean brightness",
        ),
        (_catalogue(), {"schema_version": 1}, "schema_version"),
        (_catalogue(), {"position_epoch": ""}, "position epoch"),
        (
            _catalogue(),
            {"reference_frequency_hz": 0.0},
            "reference frequency",
        ),
    ],
)
def test_catalogue_records_reject_invalid_identity_or_metadata(
    model: BaseModel,
    changes: dict[str, object],
    message: str,
) -> None:
    """Identifiers, order, counts, and schema metadata are explicit."""
    document = _document(model)
    document.update(changes)

    with pytest.raises(ValidationError, match=message):
        type(model).model_validate(document)
