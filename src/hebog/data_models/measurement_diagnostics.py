"""Array-free dispositions for measured and unmeasurable detections."""

from __future__ import annotations

from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.data_models.fitting import GaussianFitDiagnostics

AssociationEvidenceKind: TypeAlias = Literal[
    "directional-fwhm-overlap",
    "resolved-loop",
    "resolved-open-arc",
    "persistent-residual",
]
_MINIMUM_MERGE_COMPONENTS = 2


class AssociationMergeEvidence(BaseModel):
    """One admitted merge, stored once on its final source, never per pixel."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    reason: AssociationEvidenceKind
    scale_ids: tuple[int, ...]
    member_component_ids: tuple[str, ...]
    protected_component_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_evidence(self) -> Self:
        """A merge names participants and any overridden compact protection."""
        if (
            len(self.member_component_ids) < _MINIMUM_MERGE_COMPONENTS
            or any(not item for item in self.member_component_ids)
            or tuple(sorted(set(self.member_component_ids)))
            != self.member_component_ids
            or tuple(sorted(set(self.protected_component_ids)))
            != self.protected_component_ids
            or not set(self.protected_component_ids)
            <= set(self.member_component_ids)
        ):
            raise ValueError("association evidence has invalid members")
        if (
            tuple(sorted(set(self.scale_ids))) != self.scale_ids
            or any(index not in (1, 2, 3) for index in self.scale_ids)
            or bool(self.scale_ids)
            != (self.reason != "directional-fwhm-overlap")
        ):
            raise ValueError("association evidence has invalid scale IDs")
        return self


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
    decision: Literal[
        "independent-component", "compact-model", "extended-morphology"
    ]


class MeasurementDisposition(BaseModel):
    """Preserve a detected object's identity independently of fitted rows."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_kind: Literal["source", "component"]
    object_id: str
    status: Literal["measured", "unavailable", "deferred"]
    estimator: (
        Literal[
            "original-pixel-gaussian-model",
            "source-owned-signed-aperture",
            "summed-fitted-component-flux",
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
    association_evidence: tuple[AssociationMergeEvidence, ...] = ()

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

    @model_validator(mode="after")
    def _validate_source_evidence(self) -> Self:
        """Source-level provenance cannot refer to a foreign component."""
        if self.association_evidence and (
            self.object_kind != "source"
            or any(
                not set(item.member_component_ids)
                <= set(self.member_component_ids)
                for item in self.association_evidence
            )
        ):
            raise ValueError("association evidence must belong to its source")
        return self
