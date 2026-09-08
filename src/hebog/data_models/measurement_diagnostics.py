"""Array-free dispositions for measured and unmeasurable detections."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator


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
