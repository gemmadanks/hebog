"""Scheduler-safe records for Phase 5 scale-space reconciliation."""

from __future__ import annotations

import re
from math import isfinite
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_DOMAIN_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_HALF_CIRCLE_DEGREES = 180.0


def _require_identifier(identifier: str, *, field_name: str) -> None:
    """Require one stable domain identifier."""
    if _DOMAIN_IDENTIFIER.fullmatch(identifier) is None:
        raise ValueError(f"{field_name} must be a domain identifier")


def _require_canonical_identifiers(
    identifiers: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    """Require unique canonical identity order."""
    if identifiers != tuple(sorted(set(identifiers))):
        raise ValueError(f"{field_name} must be unique and canonical")
    for identifier in identifiers:
        _require_identifier(identifier, field_name=field_name)


class _MultiscaleModel(BaseModel):
    """Strict immutable base for scheduler-safe Phase 5 records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ScaleDetection(_MultiscaleModel):
    """One bounded significant support region at one configured scale."""

    detection_id: str
    parent_island_id: str | None
    scale_order: int = Field(ge=1)
    nominal_scale_beam_fwhm: float = Field(gt=0)
    support_pixel_count: int = Field(ge=1)
    valid_support_fraction: float = Field(gt=0, le=1)
    bounds_yx: tuple[int, int, int, int]
    canonical_pixel_yx: tuple[int, int]
    peak_response_jy_per_beam: float = Field(gt=0)
    peak_signal_to_noise: float
    touches_image_edge: bool
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_detection(self) -> Self:
        """Validate global identity, bounds, and finite scale response."""
        _require_identifier(self.detection_id, field_name="detection ID")
        if self.parent_island_id is not None:
            _require_identifier(
                self.parent_island_id,
                field_name="parent island ID",
            )
        y_start, y_stop, x_start, x_stop = self.bounds_yx
        if min(self.bounds_yx) < 0 or y_start >= y_stop or x_start >= x_stop:
            raise ValueError("scale detection bounds must be increasing")
        y_pixel, x_pixel = self.canonical_pixel_yx
        if not (y_start <= y_pixel < y_stop and x_start <= x_pixel < x_stop):
            raise ValueError("canonical scale pixel must be inside bounds")
        response_values = (
            self.nominal_scale_beam_fwhm,
            self.valid_support_fraction,
            self.peak_response_jy_per_beam,
            self.peak_signal_to_noise,
        )
        if not all(isfinite(value) for value in response_values):
            raise ValueError("scale response values must be finite")
        return self


class CrossScaleAssociation(_MultiscaleModel):
    """Deterministic association of scale and optional compact detections."""

    association_id: str
    scale_detection_ids: tuple[str, ...] = Field(min_length=1)
    compact_source_ids: tuple[str, ...]
    selected_scale_detection_id: str
    contributing_scale_orders: tuple[int, ...] = Field(min_length=1)
    relationship: Literal[
        "extended-only",
        "contains-compact",
        "mixed-projection",
    ]
    schema_version: Literal[1] = 1

    @field_validator("scale_detection_ids", "compact_source_ids")
    @classmethod
    def validate_identifiers(
        cls,
        identifiers: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require stable association inputs."""
        _require_canonical_identifiers(
            identifiers,
            field_name="association IDs",
        )
        return identifiers

    @model_validator(mode="after")
    def validate_association(self) -> Self:
        """Bind the selected representation to retained provenance."""
        _require_identifier(self.association_id, field_name="association ID")
        if self.selected_scale_detection_id not in self.scale_detection_ids:
            raise ValueError(
                "selected scale detection must belong to the association"
            )
        if self.contributing_scale_orders != tuple(
            sorted(set(self.contributing_scale_orders))
        ) or any(order < 1 for order in self.contributing_scale_orders):
            raise ValueError("contributing scale orders must be canonical")
        if (
            self.relationship == "contains-compact"
            and not self.compact_source_ids
        ):
            raise ValueError(
                "contains-compact association requires a compact source"
            )
        return self


class ExtendedEmissionMeasurement(_MultiscaleModel):
    """One physical extended-emission measurement and availability state."""

    association_id: str
    centroid_xy: tuple[float, float]
    integrated_flux_jy: float = Field(gt=0)
    integrated_flux_error_jy: float | None = Field(default=None, ge=0)
    local_rms_jy_per_beam: float = Field(gt=0)
    support_pixel_count: int = Field(ge=1)
    major_extent_beams: float = Field(gt=0)
    minor_extent_beams: float = Field(gt=0)
    position_angle_degrees: float
    visible_model_fraction: float = Field(gt=0, le=1)
    uncertainty_status: Literal["available", "unavailable"]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        """Require finite ordered geometry and honest uncertainty status."""
        _require_identifier(self.association_id, field_name="association ID")
        values = (
            *self.centroid_xy,
            self.integrated_flux_jy,
            self.local_rms_jy_per_beam,
            self.major_extent_beams,
            self.minor_extent_beams,
            self.position_angle_degrees,
            self.visible_model_fraction,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("extended measurement values must be finite")
        if self.minor_extent_beams > self.major_extent_beams:
            raise ValueError("extended minor extent cannot exceed major")
        if not 0 <= self.position_angle_degrees < _HALF_CIRCLE_DEGREES:
            raise ValueError("extended position angle must be within [0, 180)")
        error_available = self.integrated_flux_error_jy is not None
        if error_available != (self.uncertainty_status == "available"):
            raise ValueError(
                "uncertainty status must match flux-error availability"
            )
        return self


class MultiscaleOmission(_MultiscaleModel):
    """One explicit unavailable Phase 5 object that blocks publication."""

    object_id: str
    stage: Literal[
        "scale-detection",
        "cross-scale-association",
        "extended-measurement",
        "combined-catalogue",
    ]
    reason: str = Field(min_length=1)
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_omission(self) -> Self:
        """Require a stable object identity and machine-readable reason."""
        _require_identifier(self.object_id, field_name="omission object ID")
        _require_identifier(self.reason, field_name="omission reason")
        return self


class CombinedIslandDisposition(_MultiscaleModel):
    """Terminal compact, multiscale, artifact, or failure disposition."""

    island_id: str
    status: Literal[
        "retained-compact",
        "accepted-multiscale",
        "rejected-artifact",
        "failed",
    ]
    source_ids: tuple[str, ...]
    association_ids: tuple[str, ...]
    reason: str | None
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        """Require terminal evidence appropriate to the disposition."""
        _require_identifier(self.island_id, field_name="island ID")
        _require_canonical_identifiers(
            self.source_ids, field_name="source IDs"
        )
        _require_canonical_identifiers(
            self.association_ids,
            field_name="association IDs",
        )
        if self.reason is not None:
            _require_identifier(self.reason, field_name="disposition reason")
        if self.status == "retained-compact" and not self.source_ids:
            raise ValueError("retained compact disposition requires a source")
        if self.status == "accepted-multiscale" and not self.association_ids:
            raise ValueError(
                "accepted multiscale disposition requires association"
            )
        if (
            self.status in {"rejected-artifact", "failed"}
            and self.reason is None
        ):
            raise ValueError(
                "rejected or failed disposition requires a reason"
            )
        if self.status not in {"rejected-artifact", "failed"} and self.reason:
            raise ValueError(
                "successful disposition cannot carry a failure reason"
            )
        return self


class CombinedCatalogueState(_MultiscaleModel):
    """Bounded reconciliation state for one complete catalogue decision."""

    catalogue_id: str
    dispositions: tuple[CombinedIslandDisposition, ...]
    omissions: tuple[MultiscaleOmission, ...]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        """Require canonical unique dispositions and omissions."""
        _require_identifier(self.catalogue_id, field_name="catalogue ID")
        disposition_ids = tuple(item.island_id for item in self.dispositions)
        omission_ids = tuple(item.object_id for item in self.omissions)
        _require_canonical_identifiers(
            disposition_ids,
            field_name="disposition island IDs",
        )
        _require_canonical_identifiers(
            omission_ids,
            field_name="omission object IDs",
        )
        return self

    @property
    def publication_eligible(self) -> bool:
        """Return whether every island has a non-failed terminal outcome."""
        return not self.omissions and all(
            item.status != "failed" for item in self.dispositions
        )
