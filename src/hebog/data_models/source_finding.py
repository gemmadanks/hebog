"""Pipeline-neutral request and materialised-result records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

_SHA256 = re.compile(r"[0-9a-f]{64}")
_DOMAIN_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_PRODUCT_MEDIA_TYPES = {
    "source-catalogue": "application/fits",
    "rms": "image/fits",
    "source-filtering-mask": "image/fits",
    "diagnostics": "application/json",
}

ProductRole = Literal[
    "source-catalogue",
    "rms",
    "source-filtering-mask",
    "diagnostics",
]


def _require_population_counts(
    *,
    source_count: int,
    gaussian_component_count: int,
    island_count: int,
) -> None:
    """Require non-negative, internally consistent catalogue populations."""
    counts = {
        "source_count": source_count,
        "gaussian_component_count": gaussian_component_count,
        "island_count": island_count,
    }
    for name, count in counts.items():
        if count < 0:
            raise ValueError(f"{name} cannot be negative")
    if gaussian_component_count > 0 and source_count == 0:
        raise ValueError("Gaussian components require a source")
    if source_count > 0 and island_count == 0:
        raise ValueError("sources require an island")


class SourceFindingDiagnostics(BaseModel):
    """Versioned scientific population summary for one completed run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str
    source_count: int
    gaussian_component_count: int
    island_count: int
    rms_scientific_status: Literal["valid", "unavailable"]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def _validate_diagnostics(self) -> Self:
        """Require a named run and internally consistent populations."""
        if not self.run_id:
            raise ValueError("diagnostics run ID must not be empty")
        _require_population_counts(
            source_count=self.source_count,
            gaussian_component_count=self.gaussian_component_count,
            island_count=self.island_count,
        )
        return self

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
        """Validate one canonical serialized diagnostics document."""
        diagnostics = cls.model_validate_json(payload)
        if diagnostics.canonical_json_bytes() != payload:
            raise ValueError(
                "source-finding diagnostics JSON must be canonical"
            )
        return diagnostics


class SourceScaleProvenance(BaseModel):
    """Auditable scale and support provenance for one extended source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_id: str
    island_id: str
    association_id: str
    scale_detection_ids: tuple[str, ...]
    selected_scale_detection_id: str
    contributing_scale_orders: tuple[int, ...]
    relationship: Literal[
        "extended-only",
        "contains-compact-support",
        "overlaps-compact-support",
    ]
    support_pixel_count: int
    visible_model_fraction: float
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def _validate_provenance(self) -> Self:
        """Require canonical identities and complete selected provenance."""
        identifiers = (
            (self.source_id, "source"),
            (self.island_id, "island"),
            (self.association_id, "association"),
        )
        for identifier, field_name in identifiers:
            if _DOMAIN_IDENTIFIER.fullmatch(identifier) is None:
                raise ValueError(
                    f"{field_name} ID must be a domain identifier"
                )
        if self.scale_detection_ids != tuple(
            sorted(set(self.scale_detection_ids))
        ) or any(
            _DOMAIN_IDENTIFIER.fullmatch(identifier) is None
            for identifier in self.scale_detection_ids
        ):
            raise ValueError(
                "scale detection IDs must be canonical domain identifiers"
            )
        if self.selected_scale_detection_id not in self.scale_detection_ids:
            raise ValueError(
                "selected scale detection must belong to the provenance"
            )
        if (
            not self.contributing_scale_orders
            or self.contributing_scale_orders
            != tuple(sorted(set(self.contributing_scale_orders)))
            or any(order < 1 for order in self.contributing_scale_orders)
        ):
            raise ValueError(
                "contributing scale orders must be positive and canonical"
            )
        if self.support_pixel_count < 1:
            raise ValueError("provenance support pixel count must be positive")
        if not isfinite(self.visible_model_fraction) or not (
            0 < self.visible_model_fraction <= 1
        ):
            raise ValueError(
                "visible model fraction must be finite and in (0, 1]"
            )
        return self


class ContinuumSourceFindingDiagnostics(BaseModel):
    """Version-two diagnostics with per-extended-source provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str
    source_count: int
    gaussian_component_count: int
    island_count: int
    extended_source_count: int
    terminal_disposition_count: int
    rms_scientific_status: Literal["valid", "unavailable"]
    source_provenance: tuple[SourceScaleProvenance, ...]
    schema_version: Literal[2] = 2

    @model_validator(mode="after")
    def _validate_diagnostics(self) -> Self:
        """Require canonical provenance and consistent populations."""
        if not self.run_id:
            raise ValueError("diagnostics run ID must not be empty")
        _require_population_counts(
            source_count=self.source_count,
            gaussian_component_count=self.gaussian_component_count,
            island_count=self.island_count,
        )
        if not 0 <= self.extended_source_count <= self.source_count:
            raise ValueError(
                "extended source count must fit the source population"
            )
        if len(self.source_provenance) != self.extended_source_count:
            raise ValueError(
                "extended source count must match source provenance"
            )
        source_ids = tuple(item.source_id for item in self.source_provenance)
        association_ids = tuple(
            item.association_id for item in self.source_provenance
        )
        if source_ids != tuple(sorted(set(source_ids))):
            raise ValueError("source provenance must use canonical source IDs")
        if len(set(association_ids)) != len(association_ids):
            raise ValueError("source provenance associations must be unique")
        if self.terminal_disposition_count < self.island_count:
            raise ValueError(
                "terminal dispositions cannot be fewer than output islands"
            )
        return self

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
        """Validate one canonical serialized continuum diagnostic."""
        diagnostics = cls.model_validate_json(payload)
        if diagnostics.canonical_json_bytes() != payload:
            raise ValueError(
                "continuum source-finding diagnostics JSON must be canonical"
            )
        return diagnostics


class PublicSourceFindingProvenance(BaseModel):
    """Exact input, configuration, and scientific-composition identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_sha256: str
    configuration_sha256: str
    scientific_profile_sha256: str
    scientific_composition_sha256: str
    scientific_composition: Literal[
        "phase-5-configurable-deblended-component-and-source-topology-v8"
    ]
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def _validate_provenance(self) -> Self:
        """Require every bound identity to be exact lowercase SHA-256."""
        identities = (
            self.input_sha256,
            self.configuration_sha256,
            self.scientific_profile_sha256,
            self.scientific_composition_sha256,
        )
        if any(_SHA256.fullmatch(identity) is None for identity in identities):
            raise ValueError("public provenance identities must be SHA-256")
        return self


class PublicSourceFindingDiagnostics(BaseModel):
    """Version-five public-run diagnostics with reproducible provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str
    profile: Literal["continuum", "compact"]
    profile_limitations: tuple[Literal["extended-emission-incomplete"], ...]
    configuration_qualification: Literal[
        "phase-5-reference", "custom-unqualified"
    ]
    source_count: int
    gaussian_component_count: int
    island_count: int
    deblended_parent_count: int = 0
    deferred_deblend_parent_count: int = 0
    rms_scientific_status: Literal["valid", "unavailable"]
    provenance: PublicSourceFindingProvenance
    schema_version: Literal[5] = 5

    @model_validator(mode="after")
    def _validate_diagnostics(self) -> Self:
        """Require consistent populations and honest profile limitations."""
        if not self.run_id:
            raise ValueError("diagnostics run ID must not be empty")
        _require_population_counts(
            source_count=self.source_count,
            gaussian_component_count=self.gaussian_component_count,
            island_count=self.island_count,
        )
        if (
            self.deblended_parent_count < 0
            or self.deferred_deblend_parent_count < 0
        ):
            raise ValueError("deblend disposition counts cannot be negative")
        expected_limitations = (
            ("extended-emission-incomplete",)
            if self.profile == "compact"
            else ()
        )
        if self.profile_limitations != expected_limitations:
            raise ValueError(
                "public diagnostics limitations must match the profile"
            )
        return self

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
        """Validate one canonical serialized public diagnostic."""
        diagnostics = cls.model_validate_json(payload)
        if diagnostics.canonical_json_bytes() != payload:
            raise ValueError(
                "public source-finding diagnostics JSON must be canonical"
            )
        return diagnostics


DiagnosticsProduct = (
    SourceFindingDiagnostics
    | ContinuumSourceFindingDiagnostics
    | PublicSourceFindingDiagnostics
)


@dataclass(frozen=True, slots=True)
class SourceFinderRequest:
    """Inputs for one independent source-finding analysis."""

    image_path: Path
    output_directory: Path
    run_id: str
    schema_version: Literal[1] = 1

    def __post_init__(self) -> None:
        """Reject unsupported schema versions and empty run identifiers."""
        if self.schema_version != 1:
            raise ValueError(
                "unsupported source-finder request schema version"
            )
        if not self.run_id:
            raise ValueError("run_id must not be empty")


class MaterializedProduct(BaseModel):
    """Closed restartable output file and its content identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    product_role: ProductRole
    path: Path
    media_type: Literal["application/fits", "image/fits", "application/json"]
    byte_count: int
    content_sha256: str
    scientific_status: Literal["valid", "unavailable"]
    content_schema_version: int
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def _validate_product(self) -> Self:
        """Validate a portable file identity without opening the path."""
        if not self.path.name:
            raise ValueError("materialized product file path is required")
        if self.byte_count <= 0:
            raise ValueError(
                "materialized product byte count must be positive"
            )
        if _SHA256.fullmatch(self.content_sha256) is None:
            raise ValueError(
                "materialized product SHA-256 must be lowercase hex"
            )
        if self.content_schema_version < 1:
            raise ValueError(
                "materialized product content schema version must be positive"
            )
        expected_media_type = _PRODUCT_MEDIA_TYPES[self.product_role]
        if self.media_type != expected_media_type:
            raise ValueError(
                f"{self.product_role} media type must be {expected_media_type}"
            )
        return self


class SourceFinderResult(BaseModel):
    """Versioned materialised products from one scientific image analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str
    catalogue: MaterializedProduct
    rms: MaterializedProduct
    mask: MaterializedProduct
    diagnostics: MaterializedProduct
    source_count: int
    gaussian_component_count: int
    island_count: int
    wall_seconds: float
    schema_version: Literal[2] = 2

    @model_validator(mode="after")
    def _validate_result(self) -> Self:
        """Require one exact, scientifically labelled product set."""
        self._validate_identity_and_counts()
        self._validate_product_roles()
        return self

    def _validate_identity_and_counts(self) -> None:
        """Validate the run, population counts, and elapsed time."""
        if not self.run_id:
            raise ValueError("source-finder result run ID must not be empty")
        _require_population_counts(
            source_count=self.source_count,
            gaussian_component_count=self.gaussian_component_count,
            island_count=self.island_count,
        )
        if not isfinite(self.wall_seconds) or self.wall_seconds < 0:
            raise ValueError("wall_seconds must be finite and non-negative")

    def _validate_product_roles(self) -> None:
        """Validate roles, distinct paths, and scientific availability."""
        expected_roles = (
            ("catalogue", self.catalogue, "source-catalogue"),
            ("rms", self.rms, "rms"),
            ("mask", self.mask, "source-filtering-mask"),
            ("diagnostics", self.diagnostics, "diagnostics"),
        )
        for name, product, expected_role in expected_roles:
            if product.product_role != expected_role:
                raise ValueError(
                    f"{name} product role must be {expected_role}"
                )
        paths = tuple(product.path for _, product, _ in expected_roles)
        if len(set(paths)) != len(paths):
            raise ValueError("materialized product paths must be distinct")
        required_products = (
            self.catalogue,
            self.mask,
            self.diagnostics,
        )
        if any(
            product.scientific_status != "valid"
            for product in required_products
        ):
            raise ValueError(
                "only RMS may be scientifically unavailable in a success"
            )

    @property
    def catalogue_path(self) -> Path:
        """Return the materialised catalogue path for workflow consumers."""
        return self.catalogue.path

    @property
    def rms_path(self) -> Path:
        """Return the materialised RMS image path."""
        return self.rms.path

    @property
    def mask_path(self) -> Path:
        """Return the materialised source-filtering mask path."""
        return self.mask.path

    @property
    def diagnostics_path(self) -> Path:
        """Return the materialised diagnostics path."""
        return self.diagnostics.path

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
        """Validate one serialized materialised result."""
        result = cls.model_validate_json(payload)
        if result.canonical_json_bytes() != payload:
            raise ValueError("source-finder result JSON must be canonical")
        return result
