"""Array-free dispositions for measured and unmeasurable detections."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.data_models.fitting import GaussianFitDiagnostics


class SourcePositionDiagnostics(BaseModel):
    """Small attribution record; no pixels, truth or scheduler objects."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False
    )

    signed_original_xy: tuple[float, float] | None
    denoised_xy: tuple[float, float] | None
    selected_xy: tuple[float, float] | None
    selection_reason: str
    unavailable_reason: str | None
    position_pixel_count: int = Field(ge=0)
    aperture_pixel_count: int = Field(ge=0)
    position_signed_weight: float | None
    aperture_signed_flux_jy: float | None
    aperture_background_mean: float | None


class AssociationDecisionDiagnostics(BaseModel):
    """Competing group IDs, linear in component count, with no image arrays."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    hierarchy_group_id: str
    compact_model_group_id: str | None
    extended_group_id: str | None
    decision: Literal["hierarchy", "compact-model", "extended-morphology"]


class MeasurementDisposition(BaseModel):
    """Preserve a detected object's identity independently of fitted rows."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_kind: Literal["source", "component"]
    object_id: str
    status: Literal["measured", "unavailable", "deferred"]
    estimator: (
        Literal[
            "original-pixel-gaussian-model", "source-owned-signed-aperture"
        ]
        | None
    )
    reason: str | None
    member_component_ids: tuple[str, ...] = ()
    catalogue_row_published: bool = False
    fit_diagnostics: GaussianFitDiagnostics | None = None
    fit_covariance_available: bool | None = None
    position_diagnostics: SourcePositionDiagnostics | None = None
    association_diagnostics: AssociationDecisionDiagnostics | None = None

    @model_validator(mode="after")
    def _validate_disposition(self) -> Self:
        """An absence has a reason; a measurement names its estimator."""
        if not self.object_id:
            raise ValueError("measurement disposition requires an object ID")
        if self.status == "measured":
            if self.estimator is None or self.reason is not None:
                raise ValueError("measured disposition requires an estimator")
        elif not self.reason or self.estimator is not None:
            raise ValueError("unavailable disposition requires a reason")
        if self.catalogue_row_published and self.status != "measured":
            raise ValueError("unmeasured row cannot be published")
        if tuple(sorted(set(self.member_component_ids))) != (
            self.member_component_ids
        ):
            raise ValueError("measurement members must be unique and sorted")
        if any(not identifier for identifier in self.member_component_ids):
            raise ValueError("measurement member ID must not be empty")
        if self.object_kind == "source" and not self.member_component_ids:
            raise ValueError("measurement source members must not be empty")
        if self.object_kind == "component" and self.member_component_ids:
            raise ValueError("measurement component cannot have members")
        return self
