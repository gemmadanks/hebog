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
