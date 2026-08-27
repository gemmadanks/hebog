"""Immutable component-to-source association evidence."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

_COORDINATE_DIMENSIONS = 2


def _require_identifier(value: str, *, field_name: str) -> None:
    """Require one non-empty canonical ASCII domain identifier."""
    if (
        not value
        or not value.isascii()
        or value != value.lower()
        or value.startswith("-")
        or value.endswith("-")
        or any(
            not (character.isalnum() or character == "-")
            for character in value
        )
    ):
        raise ValueError(f"{field_name} must be a canonical domain identifier")


@dataclass(frozen=True, slots=True)
class DetectionComponentRecord:
    """Stable identity and pixel geometry for one immutable owner component."""

    component_id: str
    label_value: int
    canonical_pixel_yx: tuple[int, int]
    centroid_yx: tuple[float, float]
    covariance_pixels_squared: (
        tuple[tuple[float, float], tuple[float, float]] | None
    )
    component_labels_are_identity: Literal[False] = False

    def __post_init__(self) -> None:
        """Require valid immutable geometry without promoting local labels."""
        _require_identifier(self.component_id, field_name="component ID")
        if self.label_value <= 0:
            raise ValueError("component label value must be positive")
        if (
            len(self.canonical_pixel_yx) != _COORDINATE_DIMENSIONS
            or min(self.canonical_pixel_yx) < 0
        ):
            raise ValueError("canonical pixel must contain non-negative y-x")
        if len(self.centroid_yx) != _COORDINATE_DIMENSIONS or not all(
            isfinite(value) and value >= 0.0 for value in self.centroid_yx
        ):
            raise ValueError("component centroid must contain finite y-x")
        covariance = self.covariance_pixels_squared
        if covariance is None:
            return
        (yy, yx), (xy, xx) = covariance
        if (
            not all(isfinite(value) for value in (yy, yx, xy, xx))
            or yy <= 0.0
            or xx <= 0.0
            or yx != xy
            or yy * xx - yx * xy <= 0.0
        ):
            raise ValueError(
                "component covariance must be finite symmetric positive "
                "definite"
            )


@dataclass(frozen=True, slots=True)
class SourceAssociationEdge:
    """One accepted pair supported by continuity and directional size."""

    first_component_id: str
    second_component_id: str
    saddle_margin_sigma: float
    normalized_separation: float

    def __post_init__(self) -> None:
        """Require one canonical undirected accepted edge."""
        _require_identifier(
            self.first_component_id,
            field_name="first component ID",
        )
        _require_identifier(
            self.second_component_id,
            field_name="second component ID",
        )
        if self.first_component_id >= self.second_component_id:
            raise ValueError("association edge component IDs must be ordered")
        if (
            not isfinite(self.saddle_margin_sigma)
            or self.saddle_margin_sigma < 0.0
        ):
            raise ValueError("association saddle margin must be non-negative")
        if (
            not isfinite(self.normalized_separation)
            or not 0.0 <= self.normalized_separation <= 1.0
        ):
            raise ValueError(
                "association normalized separation must be within [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class CatalogueSourceMembership:
    """Canonical exact partition of components assigned to one source."""

    source_id: str
    component_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require a non-empty canonical component membership."""
        _require_identifier(self.source_id, field_name="source ID")
        if not self.component_ids or self.component_ids != tuple(
            sorted(set(self.component_ids))
        ):
            raise ValueError(
                "source component IDs must be non-empty unique and canonical"
            )
        for component_id in self.component_ids:
            _require_identifier(component_id, field_name="component ID")


@dataclass(frozen=True, slots=True)
class SourceAssociationResult:
    """Complete array-free association graph and source partition."""

    components: tuple[DetectionComponentRecord, ...]
    edges: tuple[SourceAssociationEdge, ...]
    memberships: tuple[CatalogueSourceMembership, ...]

    def __post_init__(self) -> None:
        """Require unique evidence and an exact component partition."""
        component_ids = tuple(item.component_id for item in self.components)
        label_values = tuple(item.label_value for item in self.components)
        if component_ids != tuple(sorted(set(component_ids))) or len(
            set(label_values)
        ) != len(label_values):
            raise ValueError("association component records must be unique")
        edge_keys = tuple(
            (item.first_component_id, item.second_component_id)
            for item in self.edges
        )
        if edge_keys != tuple(sorted(set(edge_keys))):
            raise ValueError("association edges must be unique and canonical")
        if any(
            component_id not in set(component_ids)
            for edge in self.edges
            for component_id in (
                edge.first_component_id,
                edge.second_component_id,
            )
        ):
            raise ValueError("association edge names an unknown component")
        source_ids = tuple(item.source_id for item in self.memberships)
        if source_ids != tuple(sorted(set(source_ids))):
            raise ValueError(
                "association source memberships must be canonical"
            )
        claimed = tuple(
            component_id
            for membership in self.memberships
            for component_id in membership.component_ids
        )
        if len(claimed) != len(set(claimed)) or set(claimed) != set(
            component_ids
        ):
            raise ValueError(
                "source memberships must partition every component "
                "exactly once"
            )
