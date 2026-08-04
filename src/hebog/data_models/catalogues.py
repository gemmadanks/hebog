"""Versioned pipeline-neutral source catalogue records."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from math import isfinite
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_DOMAIN_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_FULL_CIRCLE_DEGREES = 360
_MINIMUM_DECLINATION_DEGREES = -90
_MAXIMUM_DECLINATION_DEGREES = 90
_HALF_CIRCLE_DEGREES = 180


def _require_domain_identifier(identifier: str, *, field_name: str) -> None:
    """Require one stable lowercase identifier safe for interchange."""
    if _DOMAIN_IDENTIFIER.fullmatch(identifier) is None:
        raise ValueError(f"{field_name} must be a domain identifier")


def _require_optional_errors(
    values: Iterable[float | None],
    *,
    field_name: str,
) -> None:
    """Require every available uncertainty to be finite and non-negative."""
    if any(
        value is not None and (not isfinite(value) or value < 0)
        for value in values
    ):
        raise ValueError(f"{field_name} must be finite and non-negative")


def _require_unique_canonical_ids(
    identifiers: tuple[str, ...],
    *,
    object_name: str,
) -> None:
    """Reject duplicate or executor-order-dependent identity sequences."""
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{object_name} IDs must be unique")
    if identifiers != tuple(sorted(identifiers)):
        raise ValueError(f"{object_name} records must use canonical order")


class _CatalogueModel(BaseModel):
    """Strict immutable base for scheduler-safe catalogue records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SkyPosition(_CatalogueModel):
    """One ICRS sky position and optional one-sigma errors in degrees."""

    right_ascension_degrees: float
    declination_degrees: float
    right_ascension_error_degrees: float | None
    declination_error_degrees: float | None

    @model_validator(mode="after")
    def _validate_position(self) -> Self:
        """Require canonical finite sky coordinates and uncertainties."""
        if not isfinite(self.right_ascension_degrees) or not (
            0 <= self.right_ascension_degrees < _FULL_CIRCLE_DEGREES
        ):
            raise ValueError(
                "right ascension must be finite and within [0, 360) degrees"
            )
        if not isfinite(self.declination_degrees) or not (
            _MINIMUM_DECLINATION_DEGREES
            <= self.declination_degrees
            <= _MAXIMUM_DECLINATION_DEGREES
        ):
            raise ValueError(
                "declination must be finite and within [-90, 90] degrees"
            )
        _require_optional_errors(
            (
                self.right_ascension_error_degrees,
                self.declination_error_degrees,
            ),
            field_name="position errors",
        )
        return self


class FluxMeasurement(_CatalogueModel):
    """Peak and integrated source flux plus local noise in canonical units."""

    peak_flux_jy_per_beam: float
    peak_flux_error_jy_per_beam: float | None
    integrated_flux_jy: float
    integrated_flux_error_jy: float | None
    local_rms_jy_per_beam: float

    @model_validator(mode="after")
    def _validate_flux(self) -> Self:
        """Require positive finite measurements and valid uncertainties."""
        if (
            not isfinite(self.peak_flux_jy_per_beam)
            or not isfinite(self.integrated_flux_jy)
            or self.peak_flux_jy_per_beam <= 0
            or self.integrated_flux_jy <= 0
        ):
            raise ValueError("peak and integrated fluxes must be positive")
        _require_optional_errors(
            (
                self.peak_flux_error_jy_per_beam,
                self.integrated_flux_error_jy,
            ),
            field_name="flux errors",
        )
        if (
            not isfinite(self.local_rms_jy_per_beam)
            or self.local_rms_jy_per_beam <= 0
        ):
            raise ValueError("local RMS must be finite and positive")
        return self


class GaussianShape(_CatalogueModel):
    """One fitted FWHM ellipse and optional one-sigma errors in degrees."""

    major_fwhm_degrees: float
    minor_fwhm_degrees: float
    position_angle_degrees: float
    major_fwhm_error_degrees: float | None
    minor_fwhm_error_degrees: float | None
    position_angle_error_degrees: float | None

    @model_validator(mode="after")
    def _validate_shape(self) -> Self:
        """Require a positive ordered ellipse in canonical orientation."""
        if (
            not isfinite(self.major_fwhm_degrees)
            or not isfinite(self.minor_fwhm_degrees)
            or self.major_fwhm_degrees <= 0
            or self.minor_fwhm_degrees <= 0
        ):
            raise ValueError("Gaussian shape axes must be finite and positive")
        if self.minor_fwhm_degrees > self.major_fwhm_degrees:
            raise ValueError("Gaussian shape minor axis cannot exceed major")
        if not isfinite(self.position_angle_degrees) or not (
            0 <= self.position_angle_degrees < _HALF_CIRCLE_DEGREES
        ):
            raise ValueError(
                "Gaussian shape position angle must be within [0, 180)"
            )
        _require_optional_errors(
            (
                self.major_fwhm_error_degrees,
                self.minor_fwhm_error_degrees,
                self.position_angle_error_degrees,
            ),
            field_name="shape errors",
        )
        return self


class SpectralModel(_CatalogueModel):
    """Frequency convention for one reported source or component flux.

    For ``log-polynomial``, coefficient ``k`` multiplies
    ``log(frequency / reference_frequency) ** (k + 1)`` in natural-log flux
    space. An empty tuple explicitly means that no spectral fit was made.
    """

    kind: Literal["reference-frequency-only", "log-polynomial"]
    reference_frequency_hz: float
    coefficients: tuple[float, ...]

    @model_validator(mode="after")
    def _validate_spectrum(self) -> Self:
        """Require one finite, internally consistent spectral convention."""
        if (
            not isfinite(self.reference_frequency_hz)
            or self.reference_frequency_hz <= 0
        ):
            raise ValueError("reference frequency must be finite and positive")
        if not all(isfinite(coefficient) for coefficient in self.coefficients):
            raise ValueError("spectral coefficients must be finite")
        if self.kind == "reference-frequency-only" and self.coefficients:
            raise ValueError(
                "reference-frequency-only model must not contain coefficients"
            )
        if self.kind == "log-polynomial" and not self.coefficients:
            raise ValueError("log-polynomial model requires coefficients")
        return self


class Island(_CatalogueModel):
    """One connected above-threshold pixel region."""

    island_id: str
    pixel_count: int
    integrated_flux_jy: float
    integrated_flux_error_jy: float | None
    local_rms_jy_per_beam: float
    mean_brightness_jy_per_beam: float

    @model_validator(mode="after")
    def _validate_island(self) -> Self:
        """Validate stable identity and finite island summaries."""
        _require_domain_identifier(self.island_id, field_name="island ID")
        if self.pixel_count <= 0:
            raise ValueError("island pixel count must be positive")
        if (
            not isfinite(self.integrated_flux_jy)
            or self.integrated_flux_jy <= 0
        ):
            raise ValueError("island integrated flux must be positive")
        _require_optional_errors(
            (self.integrated_flux_error_jy,),
            field_name="island flux error",
        )
        if (
            not isfinite(self.local_rms_jy_per_beam)
            or self.local_rms_jy_per_beam <= 0
        ):
            raise ValueError("island local RMS must be finite and positive")
        if not isfinite(self.mean_brightness_jy_per_beam):
            raise ValueError("island mean brightness must be finite")
        return self


class _MeasuredCatalogueObject(_CatalogueModel):
    """Shared physical fields for source and Gaussian-component records."""

    island_id: str
    position: SkyPosition
    flux: FluxMeasurement
    spectral_model: SpectralModel
    deconvolved_shape: GaussianShape | None
    quality_flags: tuple[str, ...]

    @field_validator("quality_flags")
    @classmethod
    def _validate_quality_flags(
        cls,
        flags: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require deterministic, extensible domain flag names."""
        for flag in flags:
            _require_domain_identifier(flag, field_name="quality flag")
        if flags != tuple(sorted(set(flags))):
            raise ValueError("quality flags must be unique and canonical")
        return flags

    @model_validator(mode="after")
    def _validate_island_id(self) -> Self:
        """Require a stable island association."""
        _require_domain_identifier(self.island_id, field_name="island ID")
        return self


class SourceCandidate(_MeasuredCatalogueObject):
    """One catalogue-level association of measured astrophysical emission."""

    source_id: str
    fitted_shape: GaussianShape | None
    restoring_beam_aperture_integrated_flux_jy: float | None = None

    @model_validator(mode="after")
    def _validate_source_id(self) -> Self:
        """Require stable identity and valid optional aperture photometry."""
        _require_domain_identifier(self.source_id, field_name="source ID")
        aperture_flux = self.restoring_beam_aperture_integrated_flux_jy
        if aperture_flux is not None and (
            not isfinite(aperture_flux) or aperture_flux <= 0
        ):
            raise ValueError(
                "restoring-beam aperture flux must be finite and positive"
            )
        return self


class GaussianComponent(_MeasuredCatalogueObject):
    """One fitted Gaussian assigned to exactly one source and island."""

    gaussian_component_id: str
    source_id: str
    fitted_shape: GaussianShape

    @model_validator(mode="after")
    def _validate_component_ids(self) -> Self:
        """Require stable component and source identities."""
        _require_domain_identifier(
            self.gaussian_component_id,
            field_name="Gaussian component ID",
        )
        _require_domain_identifier(self.source_id, field_name="source ID")
        return self


class SourceCatalogue(_CatalogueModel):
    """Canonical MFS catalogue with distinct islands, sources, and fits."""

    catalogue_id: str
    coordinate_frame: Literal["icrs"]
    position_epoch: str
    reference_frequency_hz: float
    islands: tuple[Island, ...]
    sources: tuple[SourceCandidate, ...]
    gaussian_components: tuple[GaussianComponent, ...]
    schema_version: Literal[2] = 2

    @model_validator(mode="after")
    def _validate_catalogue(self) -> Self:
        """Validate metadata, canonical identities, and relationships."""
        _require_domain_identifier(
            self.catalogue_id,
            field_name="catalogue ID",
        )
        if not self.position_epoch:
            raise ValueError("catalogue position epoch must not be empty")
        if (
            not isfinite(self.reference_frequency_hz)
            or self.reference_frequency_hz <= 0
        ):
            raise ValueError("catalogue reference frequency must be positive")
        self._validate_identity_sets()
        self._validate_relationships()
        self._validate_reference_frequencies()
        return self

    def _validate_identity_sets(self) -> None:
        """Require a deterministic unique order within each object class."""
        _require_unique_canonical_ids(
            tuple(island.island_id for island in self.islands),
            object_name="island",
        )
        _require_unique_canonical_ids(
            tuple(source.source_id for source in self.sources),
            object_name="source",
        )
        _require_unique_canonical_ids(
            tuple(
                component.gaussian_component_id
                for component in self.gaussian_components
            ),
            object_name="Gaussian component",
        )

    def _validate_relationships(self) -> None:
        """Require every source and component relationship to resolve."""
        islands_by_id = {island.island_id: island for island in self.islands}
        sources_by_id = {source.source_id: source for source in self.sources}
        for source in self.sources:
            if source.island_id not in islands_by_id:
                raise ValueError("source references an unknown island")
        for component in self.gaussian_components:
            source = sources_by_id.get(component.source_id)
            if source is None:
                raise ValueError(
                    "Gaussian component references an unknown source"
                )
            if component.island_id != source.island_id:
                raise ValueError(
                    "source and Gaussian component must share an island"
                )

    def _validate_reference_frequencies(self) -> None:
        """Keep every initial MFS measurement on one explicit frequency."""
        measured_objects = (*self.sources, *self.gaussian_components)
        if any(
            item.spectral_model.reference_frequency_hz
            != self.reference_frequency_hz
            for item in measured_objects
        ):
            raise ValueError(
                "catalogue measurements must share its reference frequency"
            )

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        *,
        catalogue_id: str,
        coordinate_frame: Literal["icrs"],
        position_epoch: str,
        reference_frequency_hz: float,
        islands: Iterable[Island],
        sources: Iterable[SourceCandidate],
        gaussian_components: Iterable[GaussianComponent],
    ) -> Self:
        """Canonicalize reconciled records before schema validation."""
        return cls(
            catalogue_id=catalogue_id,
            coordinate_frame=coordinate_frame,
            position_epoch=position_epoch,
            reference_frequency_hz=reference_frequency_hz,
            islands=tuple(sorted(islands, key=lambda item: item.island_id)),
            sources=tuple(sorted(sources, key=lambda item: item.source_id)),
            gaussian_components=tuple(
                sorted(
                    gaussian_components,
                    key=lambda item: item.gaussian_component_id,
                )
            ),
        )

    def canonical_json_bytes(self) -> bytes:
        """Return deterministic UTF-8 JSON with one final newline."""
        document = json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"{document}\n".encode()

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> Self:
        """Validate one serialized internal catalogue."""
        catalogue = cls.model_validate_json(payload)
        if catalogue.canonical_json_bytes() != payload:
            raise ValueError("source catalogue JSON must be canonical")
        return catalogue
