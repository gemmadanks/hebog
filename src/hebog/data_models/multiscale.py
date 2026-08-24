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


class CompactSourceSupport(_MultiscaleModel):
    """One accepted Phase 4 source and its exact image-plane support."""

    source_id: str
    island_id: str
    support_pixel_count: int = Field(ge=1)
    bounds_yx: tuple[int, int, int, int]
    reference_position_yx: tuple[float, float]
    gaussian_component_ids: tuple[str, ...]
    schema_version: Literal[1] = 1

    @field_validator("gaussian_component_ids")
    @classmethod
    def validate_component_ids(
        cls,
        identifiers: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require canonical retained Phase 4 component identities."""
        _require_canonical_identifiers(
            identifiers,
            field_name="Gaussian component IDs",
        )
        return identifiers

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        """Require stable identities, finite position, and valid bounds."""
        _require_identifier(self.source_id, field_name="source ID")
        _require_identifier(self.island_id, field_name="island ID")
        y_start, y_stop, x_start, x_stop = self.bounds_yx
        if min(self.bounds_yx) < 0 or y_start >= y_stop or x_start >= x_stop:
            raise ValueError("compact source bounds must be increasing")
        if not all(
            isfinite(value) and value >= 0
            for value in self.reference_position_yx
        ):
            raise ValueError(
                "compact reference position must be finite and non-negative"
            )
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
        "contains-compact-support",
        "overlaps-compact-support",
    ]
    schema_version: Literal[2] = 2

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
        has_compact_context = self.relationship != "extended-only"
        if has_compact_context and not self.compact_source_ids:
            raise ValueError(
                "compact-support association requires a compact source"
            )
        if not has_compact_context and self.compact_source_ids:
            raise ValueError(
                "extended-only association cannot name a compact source"
            )
        return self


class CompactExtendedContextEdge(_MultiscaleModel):
    """One spatial edge retaining separate compact and extended identities."""

    association_id: str
    compact_source_id: str
    relationship: Literal[
        "contains-compact-support",
        "overlaps-compact-support",
    ]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_edge(self) -> Self:
        """Require stable identities on both sides of the context edge."""
        _require_identifier(self.association_id, field_name="association ID")
        _require_identifier(
            self.compact_source_id,
            field_name="compact source ID",
        )
        return self


class CombinedIslandIdentity(_MultiscaleModel):
    """Stable membership identities for one combined graph component."""

    island_id: str
    compact_island_ids: tuple[str, ...]
    compact_source_ids: tuple[str, ...]
    association_ids: tuple[str, ...]
    extended_source_ids: tuple[str, ...]
    gaussian_component_ids: tuple[str, ...]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_membership(self) -> Self:
        """Require canonical complete source and association membership."""
        _require_identifier(self.island_id, field_name="combined island ID")
        identity_fields = (
            (self.compact_island_ids, "compact island IDs"),
            (self.compact_source_ids, "compact source IDs"),
            (self.association_ids, "association IDs"),
            (self.extended_source_ids, "extended source IDs"),
            (self.gaussian_component_ids, "Gaussian component IDs"),
        )
        for identifiers, field_name in identity_fields:
            _require_canonical_identifiers(
                identifiers,
                field_name=field_name,
            )
        if not self.compact_island_ids and not self.association_ids:
            raise ValueError(
                "combined identity requires a compact island or association"
            )
        if bool(self.compact_island_ids) != bool(self.compact_source_ids):
            raise ValueError(
                "compact island and source membership must both be present"
            )
        if len(self.association_ids) != len(self.extended_source_ids):
            raise ValueError(
                "combined identity requires one extended source per "
                "association"
            )
        if self.gaussian_component_ids and not self.compact_source_ids:
            raise ValueError(
                "Gaussian components require retained compact sources"
            )
        return self


class ExtendedSourceIdentity(_MultiscaleModel):
    """One stable irregular source identity derived from an association."""

    association_id: str
    island_id: str
    source_id: str
    gaussian_component_ids: tuple[str, ...] = Field(default=(), max_length=0)
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        """Require stable association, island, and source identities."""
        _require_identifier(self.association_id, field_name="association ID")
        _require_identifier(self.island_id, field_name="combined island ID")
        _require_identifier(self.source_id, field_name="extended source ID")
        return self


class ExtendedEmissionMeasurement(_MultiscaleModel):
    """One physical extended-emission measurement and availability state."""

    association_id: str
    centroid_xy: tuple[float, float]
    centroid_kind: Literal["detected-segment-flux-centroid"]
    peak_position_xy: tuple[int, int]
    host_position_claim: Literal[False]
    position_covariance_pixels_squared: None = None
    position_uncertainty_status: Literal["unavailable"]
    integrated_flux_jy: float = Field(gt=0)
    integrated_flux_error_jy: float | None = Field(default=None, ge=0)
    local_rms_jy_per_beam: float = Field(gt=0)
    support_pixel_count: int = Field(ge=1)
    major_extent_beams: float = Field(gt=0)
    minor_extent_beams: float = Field(gt=0)
    position_angle_degrees: float
    visible_model_fraction: float = Field(gt=0, le=1)
    flux_uncertainty_status: Literal["available", "unavailable"]
    schema_version: Literal[2] = 2

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
        if min(*self.centroid_xy, *self.peak_position_xy) < 0:
            raise ValueError("extended positions must be non-negative")
        if self.minor_extent_beams > self.major_extent_beams:
            raise ValueError("extended minor extent cannot exceed major")
        if not 0 <= self.position_angle_degrees < _HALF_CIRCLE_DEGREES:
            raise ValueError("extended position angle must be within [0, 180)")
        error_available = self.integrated_flux_error_jy is not None
        if error_available != (self.flux_uncertainty_status == "available"):
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
    accepted_island_ids: tuple[str, ...]
    deferred_island_ids: tuple[str, ...]
    dispositions: tuple[CombinedIslandDisposition, ...]
    omissions: tuple[MultiscaleOmission, ...]
    schema_version: Literal[2] = 2

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        """Require canonical required identities and terminal evidence."""
        _require_identifier(self.catalogue_id, field_name="catalogue ID")
        required_ids = _validate_required_island_ids(
            self.accepted_island_ids,
            self.deferred_island_ids,
        )
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
        if not set(disposition_ids).issubset(required_ids):
            raise ValueError("disposition names an unknown required island")
        return self

    @property
    def missing_disposition_ids(self) -> tuple[str, ...]:
        """Return accepted or deferred islands without terminal evidence."""
        disposition_ids = {item.island_id for item in self.dispositions}
        return tuple(
            sorted(
                {
                    *self.accepted_island_ids,
                    *self.deferred_island_ids,
                }
                - disposition_ids
            )
        )

    @property
    def publication_eligible(self) -> bool:
        """Return whether every island has a non-failed terminal outcome."""
        return (
            not self.omissions
            and not self.missing_disposition_ids
            and all(item.status != "failed" for item in self.dispositions)
        )


def _validate_required_island_ids(
    accepted_island_ids: tuple[str, ...],
    deferred_island_ids: tuple[str, ...],
) -> set[str]:
    """Require canonical disjoint accepted and deferred ownership."""
    _require_canonical_identifiers(
        accepted_island_ids,
        field_name="accepted island IDs",
    )
    _require_canonical_identifiers(
        deferred_island_ids,
        field_name="deferred island IDs",
    )
    accepted = set(accepted_island_ids)
    deferred = set(deferred_island_ids)
    if accepted & deferred:
        raise ValueError("accepted and deferred island IDs must be disjoint")
    return accepted | deferred


class CombinedCatalogueShard(_MultiscaleModel):
    """One bounded canonical shard of terminal catalogue evidence."""

    accepted_island_ids: tuple[str, ...]
    deferred_island_ids: tuple[str, ...]
    dispositions: tuple[CombinedIslandDisposition, ...]
    omissions: tuple[MultiscaleOmission, ...]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_shard(self) -> Self:
        """Require canonical shard-local ownership and evidence."""
        required_ids = _validate_required_island_ids(
            self.accepted_island_ids,
            self.deferred_island_ids,
        )
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
        if not set(disposition_ids).issubset(required_ids):
            raise ValueError("disposition names an unknown required island")
        return self

    @property
    def record_count(self) -> int:
        """Return all small records admitted to final in-memory state."""
        return (
            len(self.accepted_island_ids)
            + len(self.deferred_island_ids)
            + len(self.dispositions)
            + len(self.omissions)
        )


class CombinedCatalogueReduction(_MultiscaleModel):
    """Canonical pairwise reduction and bounded-fan-in evidence."""

    shard: CombinedCatalogueShard
    input_shard_count: int = Field(ge=0)
    reduction_depth: int = Field(ge=0)
    maximum_input_shard_record_count: int = Field(ge=0)
    schema_version: Literal[1] = 1


class CompletedCombinedCatalogueState(_MultiscaleModel):
    """Publication-eligible state plus its bounded reduction evidence."""

    state: CombinedCatalogueState
    shard_count: int = Field(ge=0)
    reduction_depth: int = Field(ge=0)
    maximum_shard_record_count: int = Field(ge=0)
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        """Forbid an incomplete state from masquerading as completed."""
        if not self.state.publication_eligible:
            raise ValueError(
                "completed combined catalogue state must be publication "
                "eligible"
            )
        return self
