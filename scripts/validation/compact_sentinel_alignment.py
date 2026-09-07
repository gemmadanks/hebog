"""Like-semantics source and component evidence for a future sentinel.

This module operates only on in-memory fixture or future-runner products.  It
does not read a campaign, execute either finder, or alter source-finding
science.  Source-level measurements and source-union ownership are binding;
native component or island observations remain an explicitly report-only
diagnostic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt

from hebog.validation.external_runners import canonical_sha256
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
    measure_continuum_image,
)

FinderId = Literal["current-hebog", "released-pybdsf"]
NativeTopologyDomain = Literal["component-owner", "island-owner"]
AdaptiveBackgroundTrigger = Literal["below", "boundary", "above"]
MetricValue = float | list[float]
_IMAGE_DIMENSIONS = 2
_SCHEMA_VERSION = 2
_SHA256_HEX_LENGTH = 64


def _finite_centre(value: tuple[float, float], *, name: str) -> None:
    """Require one finite two-dimensional pixel centre."""
    if len(value) != _IMAGE_DIMENSIONS or not all(
        isfinite(item) for item in value
    ):
        raise ValueError(f"{name} must contain two finite values")


def _positive_flux(value: float, *, name: str) -> None:
    """Require one finite positive integrated flux."""
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class AlignedComponent:
    """One individual fitted component with explicit source membership."""

    identifier: str
    source_identifier: str
    native_support_label: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Validate component identity, native ownership, and observables."""
        if not self.identifier or not self.source_identifier:
            raise ValueError(
                "component and source identifiers must not be empty"
            )
        if (
            type(self.native_support_label) is not int
            or self.native_support_label <= 0
        ):
            raise ValueError("component native support label must be positive")
        _finite_centre(self.centre_xy, name="component centre")
        _positive_flux(self.integrated_flux_jy, name="component flux")


@dataclass(frozen=True, slots=True)
class AlignedSource:
    """One source measurement and its exact component/support membership."""

    identifier: str
    member_component_ids: tuple[str, ...]
    native_support_labels: tuple[int, ...]
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Require canonical, non-empty membership and physical observables."""
        if not self.identifier:
            raise ValueError("source identifier must not be empty")
        if not self.member_component_ids or self.member_component_ids != tuple(
            sorted(set(self.member_component_ids))
        ):
            raise ValueError(
                "source component IDs must be non-empty and canonical"
            )
        if (
            not self.native_support_labels
            or self.native_support_labels
            != tuple(sorted(set(self.native_support_labels)))
            or min(self.native_support_labels) <= 0
        ):
            raise ValueError(
                "source native support labels must be positive and canonical"
            )
        _finite_centre(self.centre_xy, name="source centre")
        _positive_flux(self.integrated_flux_jy, name="source flux")


@dataclass(frozen=True, slots=True)
class AlignedSummaryInput:
    """Transient arrays and immutable records for one finder realization."""

    input_id: str
    finder_id: FinderId
    truth: tuple[ContinuumTruthObject, ...]
    truth_label_plane: npt.NDArray[np.integer[Any]]
    sources: tuple[AlignedSource, ...]
    components: tuple[AlignedComponent, ...]
    native_owner_label_plane: npt.NDArray[np.integer[Any]]
    source_union_label_plane: npt.NDArray[np.integer[Any]]
    native_topology_domain: NativeTopologyDomain
    published_support_mask: npt.NDArray[np.bool_]
    beam_fwhm_pixels: float
    adaptive_background_trigger: AdaptiveBackgroundTrigger
    cell_id: str = "fixture-cell"
    dataset_identifier: str = "fixture-dataset"
    seed: int = 1


def group_components_by_source(
    components: tuple[AlignedComponent, ...],
) -> tuple[AlignedSource, ...]:
    """Aggregate individual components once per explicit source identity.

    The source centre is the integrated-flux-weighted component centre.  This
    is appropriate for a grouped Gaussian mixture and, critically, the source
    flux is the sum of each component's individual flux exactly once.
    """
    rows = tuple(components)
    identifiers = tuple(item.identifier for item in rows)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("component identifiers must be unique")
    grouped: dict[str, list[AlignedComponent]] = defaultdict(list)
    for component in rows:
        grouped[component.source_identifier].append(component)
    output: list[AlignedSource] = []
    for source_identifier, members in sorted(grouped.items()):
        ordered = tuple(sorted(members, key=lambda item: item.identifier))
        integrated_flux = sum(item.integrated_flux_jy for item in ordered)
        output.append(
            AlignedSource(
                identifier=source_identifier,
                member_component_ids=tuple(
                    item.identifier for item in ordered
                ),
                native_support_labels=tuple(
                    sorted({item.native_support_label for item in ordered})
                ),
                centre_xy=(
                    sum(
                        item.centre_xy[0] * item.integrated_flux_jy
                        for item in ordered
                    )
                    / integrated_flux,
                    sum(
                        item.centre_xy[1] * item.integrated_flux_jy
                        for item in ordered
                    )
                    / integrated_flux,
                ),
                integrated_flux_jy=integrated_flux,
            )
        )
    return tuple(output)


def _label_plane(value: npt.ArrayLike, *, name: str) -> npt.NDArray[np.int64]:
    """Require one non-negative two-dimensional integer owner plane."""
    labels = np.asarray(value)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype, np.integer
    ):
        raise ValueError(f"{name} must be a two-dimensional integer array")
    if np.any(labels < 0):
        raise ValueError(f"{name} must contain non-negative labels")
    return np.asarray(labels, dtype=np.int64)


def _support_mask(
    value: npt.ArrayLike, *, shape: tuple[int, int]
) -> npt.NDArray[np.bool_]:
    """Require an exact two-dimensional Boolean published support mask."""
    mask = np.asarray(value)
    if mask.shape != shape or mask.dtype != np.bool_:
        raise ValueError(
            "published support mask must be a matching Boolean array"
        )
    return np.asarray(mask, dtype=np.bool_)


def _validate_memberships(
    sources: tuple[AlignedSource, ...],
    components: tuple[AlignedComponent, ...],
    native_labels: npt.NDArray[np.int64],
    *,
    native_topology_domain: NativeTopologyDomain,
) -> None:
    """Require exact source/component/native-owner partitions."""
    _validate_source_memberships(sources, components)
    _validate_native_owners(
        components,
        native_labels,
        native_topology_domain=native_topology_domain,
    )


def _validate_source_memberships(
    sources: tuple[AlignedSource, ...],
    components: tuple[AlignedComponent, ...],
) -> None:
    """Require sources to partition every component exactly once."""
    if len({item.identifier for item in sources}) != len(sources):
        raise ValueError("source identifiers must be unique")
    if len({item.identifier for item in components}) != len(components):
        raise ValueError("component identifiers must be unique")
    components_by_id = {item.identifier: item for item in components}
    source_ids = {item.identifier for item in sources}
    member_ids = tuple(
        component_id
        for source in sources
        for component_id in source.member_component_ids
    )
    if (
        len(member_ids) != len(set(member_ids))
        or set(member_ids) != set(components_by_id)
        or any(item.source_identifier not in source_ids for item in components)
    ):
        raise ValueError("source memberships must partition components")
    for source in sources:
        members = tuple(
            components_by_id[item] for item in source.member_component_ids
        )
        if any(
            item.source_identifier != source.identifier for item in members
        ):
            raise ValueError("source memberships must partition components")
        expected_labels = tuple(
            sorted({item.native_support_label for item in members})
        )
        if source.native_support_labels != expected_labels:
            raise ValueError(
                "source native support labels disagree with components"
            )


def _validate_native_owners(
    components: tuple[AlignedComponent, ...],
    native_labels: npt.NDArray[np.int64],
    *,
    native_topology_domain: NativeTopologyDomain,
) -> None:
    """Require components and native owner labels to agree exactly."""
    positive_labels = {
        int(item) for item in np.unique(native_labels) if item > 0
    }
    component_labels = {item.native_support_label for item in components}
    if positive_labels != component_labels:
        raise ValueError(
            "native support labels disagree with component ownership"
        )
    if native_topology_domain not in {"component-owner", "island-owner"}:
        raise ValueError("native topology domain is unsupported")
    if native_topology_domain == "component-owner":
        counts: dict[int, int] = defaultdict(int)
        for component in components:
            counts[component.native_support_label] += 1
        if any(value != 1 for value in counts.values()):
            raise ValueError(
                "component-owner labels must own one component each"
            )


def _source_label_map(
    sources: tuple[AlignedSource, ...],
) -> dict[str, int]:
    """Assign canonical source-union labels from stable source identities."""
    return {
        source.identifier: index
        for index, source in enumerate(
            sorted(sources, key=lambda item: item.identifier), start=1
        )
    }


def _validated_source_union_labels(
    value: npt.ArrayLike,
    sources: tuple[AlignedSource, ...],
    native_labels: npt.NDArray[np.int64],
) -> tuple[npt.NDArray[np.int64], dict[str, int]]:
    """Require an explicit canonical source partition of native support."""
    labels = _label_plane(value, name="source-union label plane")
    if labels.shape != native_labels.shape:
        raise ValueError(
            "source-union and native owner planes must share shape"
        )
    if np.any((native_labels > 0) != (labels > 0)):
        raise ValueError(
            "source unions must partition every native support pixel"
        )
    source_labels = _source_label_map(sources)
    present = {int(item) for item in np.unique(labels) if item > 0}
    if present != set(source_labels.values()):
        raise ValueError(
            "source-union labels must canonically own every source"
        )
    return labels, source_labels


def _source_union_membership_sha256(
    labels: npt.NDArray[np.int64], source_label: int
) -> str:
    """Hash one exact pixel membership without retaining an image array."""
    coordinates = np.asarray(np.argwhere(labels == source_label), dtype="<i8")
    digest = sha256(b"phase-5-source-union-membership-v1\0")
    digest.update(np.asarray(labels.shape, dtype="<i8").tobytes())
    digest.update(coordinates.tobytes())
    return digest.hexdigest()


def _overall_metrics(
    measurements: dict[str, dict[str, float | tuple[float, ...]]],
) -> dict[str, MetricValue]:
    """Retain finite whole-image sufficient statistics without arrays."""
    output: dict[str, MetricValue] = {}
    for metric, strata in measurements.items():
        value = strata.get("overall")
        if isinstance(value, tuple):
            output[metric] = [float(item) for item in value]
        elif isinstance(value, (float, int)):
            output[metric] = float(value)
        else:
            raise ValueError(f"aligned overall metric is absent: {metric}")
    return dict(sorted(output.items()))


def _source_records(
    sources: tuple[AlignedSource, ...],
    source_labels: dict[str, int],
    source_union_labels: npt.NDArray[np.int64],
) -> list[dict[str, object]]:
    """Serialize source measurements and exact unions without arrays."""
    return [
        {
            "centre_xy": [float(item.centre_xy[0]), float(item.centre_xy[1])],
            "identifier": item.identifier,
            "integrated_flux_jy": float(item.integrated_flux_jy),
            "member_component_ids": list(item.member_component_ids),
            "native_support_labels": list(item.native_support_labels),
            "source_union_label": source_labels[item.identifier],
            "source_union_membership_sha256": (
                _source_union_membership_sha256(
                    source_union_labels, source_labels[item.identifier]
                )
            ),
            "source_union_pixel_count": int(
                np.count_nonzero(
                    source_union_labels == source_labels[item.identifier]
                )
            ),
        }
        for item in sorted(sources, key=lambda value: value.identifier)
    ]


def _component_records(
    components: tuple[AlignedComponent, ...],
) -> list[dict[str, object]]:
    """Serialize individual component observables without grouped flux."""
    return [
        {
            "centre_xy": [float(item.centre_xy[0]), float(item.centre_xy[1])],
            "identifier": item.identifier,
            "integrated_flux_jy": float(item.integrated_flux_jy),
            "native_support_label": item.native_support_label,
            "source_identifier": item.source_identifier,
        }
        for item in sorted(components, key=lambda value: value.identifier)
    ]


def compile_aligned_summary(batch: AlignedSummaryInput) -> dict[str, Any]:
    """Compile one source-binding and component-diagnostic fixture summary."""
    if not batch.input_id:
        raise ValueError("aligned input identity must not be empty")
    if not batch.cell_id or not batch.dataset_identifier:
        raise ValueError(
            "aligned cell and dataset identities must not be empty"
        )
    if type(batch.seed) is not int or batch.seed < 0:
        raise ValueError("aligned seed must be a non-negative integer")
    if batch.finder_id not in {"current-hebog", "released-pybdsf"}:
        raise ValueError("aligned finder identity is unsupported")
    if not isfinite(batch.beam_fwhm_pixels) or batch.beam_fwhm_pixels <= 0.0:
        raise ValueError("beam FWHM must be finite and positive")
    if batch.adaptive_background_trigger not in {"below", "boundary", "above"}:
        raise ValueError("adaptive background trigger stratum is unsupported")
    truth_labels = _label_plane(
        batch.truth_label_plane, name="truth label plane"
    )
    native_labels = _label_plane(
        batch.native_owner_label_plane, name="native owner label plane"
    )
    if truth_labels.shape != native_labels.shape:
        raise ValueError(
            "truth and native owner label planes must share shape"
        )
    support_mask = _support_mask(
        batch.published_support_mask, shape=native_labels.shape
    )
    if np.any(support_mask != (native_labels > 0)):
        raise ValueError(
            "published support must equal positive native ownership"
        )
    sources = tuple(batch.sources)
    components = tuple(batch.components)
    _validate_memberships(
        sources,
        components,
        native_labels,
        native_topology_domain=batch.native_topology_domain,
    )
    source_union_labels, source_labels = _validated_source_union_labels(
        batch.source_union_label_plane,
        sources,
        native_labels,
    )
    source_catalogue = tuple(
        ContinuumCatalogueObject(
            item.identifier,
            source_labels[item.identifier],
            item.centre_xy,
            item.integrated_flux_jy,
        )
        for item in sources
    )
    source_measurements = measure_continuum_image(
        tuple(batch.truth),
        source_catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=source_union_labels,
        beam_fwhm_pixels=batch.beam_fwhm_pixels,
    )
    component_metrics: dict[str, MetricValue] | None = None
    if batch.native_topology_domain == "component-owner":
        component_catalogue = tuple(
            ContinuumCatalogueObject(
                item.identifier,
                item.native_support_label,
                item.centre_xy,
                item.integrated_flux_jy,
            )
            for item in components
        )
        component_metrics = _overall_metrics(
            measure_continuum_image(
                tuple(batch.truth),
                component_catalogue,
                truth_label_plane=truth_labels,
                candidate_label_plane=native_labels,
                beam_fwhm_pixels=batch.beam_fwhm_pixels,
            )
        )
    record: dict[str, Any] = {
        "adaptive_background_trigger": batch.adaptive_background_trigger,
        "cell_id": batch.cell_id,
        "component_diagnostic": {
            "binding": False,
            "metrics": component_metrics,
        },
        "component_records": _component_records(components),
        "counts": {
            "component_count": len(components),
            "source_count": len(sources),
            "source_union_count": len(
                {
                    int(item)
                    for item in np.unique(source_union_labels)
                    if item > 0
                }
            ),
        },
        "finder_id": batch.finder_id,
        "input_id": batch.input_id,
        "metrics": _overall_metrics(source_measurements),
        "ownership_valid": True,
        "product_valid": True,
        "schema_version": _SCHEMA_VERSION,
        "seed": batch.seed,
        "semantics": {
            "binary_support_domain": "positive-support",
            "binding_catalogue_level": "source",
            "binding_topology_domain": "source-union",
            "component_catalogue_level": "component",
            "component_diagnostic_binding": False,
            "component_topology_domain": batch.native_topology_domain,
        },
        "source_records": _source_records(
            sources, source_labels, source_union_labels
        ),
        "dataset_identifier": batch.dataset_identifier,
    }
    record["record_sha256"] = canonical_sha256(record)
    validate_aligned_summary(record)
    return record


def _validate_retained_semantics(
    summary: dict[str, Any],
) -> tuple[dict[str, object], dict[str, object]]:
    """Require explicit source binding and diagnostic component semantics."""
    semantics = summary.get("semantics")
    if not isinstance(semantics, dict):
        raise ValueError("aligned summary semantics are absent")
    typed_semantics = cast(dict[str, object], semantics)
    if typed_semantics.get("binding_topology_domain") != "source-union":
        raise ValueError(
            "aligned binding topology domain must be source-union"
        )
    expected = {
        "binary_support_domain": "positive-support",
        "binding_catalogue_level": "source",
        "binding_topology_domain": "source-union",
        "component_catalogue_level": "component",
        "component_diagnostic_binding": False,
    }
    if any(
        typed_semantics.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("aligned source/component semantics are invalid")
    component_domain = typed_semantics.get("component_topology_domain")
    if component_domain not in {"component-owner", "island-owner"}:
        raise ValueError("aligned component topology domain is invalid")
    diagnostic = summary.get("component_diagnostic")
    if not isinstance(diagnostic, dict):
        raise ValueError("component evidence must remain diagnostic-only")
    typed_diagnostic = cast(dict[str, object], diagnostic)
    if typed_diagnostic.get("binding") is not False:
        raise ValueError("component evidence must remain diagnostic-only")
    if (
        component_domain == "island-owner"
        and typed_diagnostic.get("metrics") is not None
    ):
        raise ValueError("island-owner component topology cannot be scored")
    if component_domain == "component-owner" and not isinstance(
        typed_diagnostic.get("metrics"), dict
    ):
        raise ValueError("component-owner diagnostics must retain metrics")
    return typed_semantics, typed_diagnostic


def _retained_records(
    summary: dict[str, Any],
) -> tuple[
    dict[str, object], list[dict[str, object]], list[dict[str, object]]
]:
    """Return structurally valid retained counts, sources, and components."""
    counts = summary.get("counts")
    sources = summary.get("source_records")
    components = summary.get("component_records")
    if (
        not isinstance(counts, dict)
        or not isinstance(sources, list)
        or not isinstance(components, list)
    ):
        raise ValueError("aligned summary counts are inconsistent")
    typed_counts = cast(dict[str, object], counts)
    typed_sources = cast(list[object], sources)
    typed_components = cast(list[object], components)
    if (
        typed_counts.get("source_count") != len(typed_sources)
        or typed_counts.get("source_union_count") != len(typed_sources)
        or typed_counts.get("component_count") != len(typed_components)
    ):
        raise ValueError("aligned summary counts are inconsistent")
    if not all(
        isinstance(item, dict) for item in (*typed_sources, *typed_components)
    ):
        raise ValueError("retained source memberships are inconsistent")
    return (
        typed_counts,
        [cast(dict[str, object], item) for item in typed_sources],
        [cast(dict[str, object], item) for item in typed_components],
    )


def _retained_identifiers(records: list[dict[str, object]]) -> set[str]:
    """Require unique non-empty retained identifiers."""
    values = [item.get("identifier") for item in records]
    if any(not isinstance(item, str) or not item for item in values):
        raise ValueError("retained source memberships are inconsistent")
    identifiers = {cast(str, item) for item in values}
    if len(identifiers) != len(records):
        raise ValueError("retained source memberships are inconsistent")
    return identifiers


def _retained_source_members(
    source_records: list[dict[str, object]],
) -> dict[str, list[str]]:
    """Require canonical non-empty component membership for each source."""
    output: dict[str, list[str]] = {}
    for source in source_records:
        identifier = cast(str, source["identifier"])
        members = source.get("member_component_ids")
        if not isinstance(members, list):
            raise ValueError("retained source memberships are inconsistent")
        member_values = cast(list[object], members)
        if not member_values or any(
            not isinstance(item, str) or not item for item in member_values
        ):
            raise ValueError("retained source memberships are inconsistent")
        typed_members = cast(list[str], member_values)
        if typed_members != sorted(set(typed_members)):
            raise ValueError("retained source memberships are inconsistent")
        output[identifier] = typed_members
    return output


def _retained_component_sources(
    component_records: list[dict[str, object]], source_ids: set[str]
) -> dict[str, str]:
    """Require each component to name one retained source and native owner."""
    output: dict[str, str] = {}
    for component in component_records:
        identifier = cast(str, component["identifier"])
        source_identifier = component.get("source_identifier")
        native_label = component.get("native_support_label")
        if (
            not isinstance(source_identifier, str)
            or source_identifier not in source_ids
            or type(native_label) is not int
            or native_label <= 0
        ):
            raise ValueError("retained source memberships are inconsistent")
        output[identifier] = source_identifier
    return output


def _validate_retained_observables(
    records: list[dict[str, object]], *, record_kind: str
) -> None:
    """Require finite centres and positive individual or grouped fluxes."""
    for record in records:
        centre = record.get("centre_xy")
        flux = record.get("integrated_flux_jy")
        if not isinstance(centre, list):
            raise ValueError(
                f"retained {record_kind} observables are inconsistent"
            )
        centre_values = cast(list[object], centre)
        if (
            len(centre_values) != _IMAGE_DIMENSIONS
            or any(
                isinstance(item, bool)
                or not isinstance(item, (float, int))
                or not isfinite(item)
                for item in centre_values
            )
            or isinstance(flux, bool)
            or not isinstance(flux, (float, int))
            or not isfinite(flux)
            or flux <= 0.0
        ):
            raise ValueError(
                f"retained {record_kind} observables are inconsistent"
            )


def _validate_retained_source_unions(
    source_records: list[dict[str, object]], source_ids: set[str]
) -> None:
    """Require canonical labels and usable array-free source-union evidence."""
    canonical_source_labels = {
        identifier: index
        for index, identifier in enumerate(sorted(source_ids), start=1)
    }
    for source in source_records:
        source_identifier = cast(str, source["identifier"])
        membership_sha256 = source.get("source_union_membership_sha256")
        if (
            source.get("source_union_label")
            != canonical_source_labels[source_identifier]
            or type(source.get("source_union_pixel_count")) is not int
            or cast(int, source.get("source_union_pixel_count")) <= 0
            or not isinstance(membership_sha256, str)
            or len(membership_sha256) != _SHA256_HEX_LENGTH
            or any(
                character not in "0123456789abcdef"
                for character in membership_sha256
            )
        ):
            raise ValueError("retained source-union ownership is inconsistent")


def _validate_retained_memberships(summary: dict[str, Any]) -> None:
    """Require retained counts and member identities to be reconstructable."""
    _counts, source_records, component_records = _retained_records(summary)
    source_ids = _retained_identifiers(source_records)
    component_ids = _retained_identifiers(component_records)
    source_members = _retained_source_members(source_records)
    component_sources = _retained_component_sources(
        component_records, source_ids
    )
    _validate_retained_observables(source_records, record_kind="source")
    _validate_retained_observables(component_records, record_kind="component")
    retained_member_ids = [
        component_id
        for members in source_members.values()
        for component_id in members
    ]
    if (
        len(retained_member_ids) != len(set(retained_member_ids))
        or set(retained_member_ids) != component_ids
        or any(
            component_sources.get(member) != source_identifier
            for source_identifier, members in source_members.items()
            for member in members
        )
    ):
        raise ValueError("retained source memberships are inconsistent")
    component_by_id = {
        cast(str, item["identifier"]): item for item in component_records
    }
    for source in source_records:
        source_identifier = cast(str, source["identifier"])
        expected_native_labels = sorted(
            {
                cast(int, component_by_id[item]["native_support_label"])
                for item in source_members[source_identifier]
            }
        )
        if source.get("native_support_labels") != expected_native_labels:
            raise ValueError("retained source memberships are inconsistent")
    _validate_retained_source_unions(source_records, source_ids)


def validate_aligned_summary(summary: dict[str, Any]) -> None:
    """Fail closed unless one retained summary has explicit like semantics."""
    if summary.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("aligned summary schema version is invalid")
    _validate_retained_semantics(summary)
    _validate_retained_memberships(summary)
    record_sha256 = summary.get("record_sha256")
    unhashed = {
        key: value for key, value in summary.items() if key != "record_sha256"
    }
    if not isinstance(record_sha256, str) or record_sha256 != canonical_sha256(
        unhashed
    ):
        raise ValueError("aligned summary digest is invalid")
