# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Sidecar-aware evaluation for Phase 5 parent-construction products.

The parent-construction replay preserved complete catalogue, label, and mask
products but its historical writer omitted the in-memory source-association
record.  This module is a new evaluation overlay: it leaves every frozen
compiler byte-identical and requires an explicit reconstructed association
sidecar before an associated Hebog catalogue can be measured.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationEdge,
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_recovery_compiler import (
    RecoveryContinuumImageCompiler,
    label_planes_on_valid_domain,
)
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
    associated_source_identifier,
    continuum_catalogue_objects,
    detection_component_identifier,
)

_ASSOCIATED_PREFIX = "source-associated-"
_IMAGE_DIMENSIONS = 2
ContinuumFinderId = Literal[
    "hebog",
    "released-pybdsf",
    "pinned-pybdsf-master",
]
AssociationPath = Callable[[Any], Path]
CandidateObjects = Callable[..., tuple[Any, ...]]


def _json_mapping(value: object, *, label: str) -> Mapping[str, object]:
    """Require one JSON object without structural coercion."""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _json_rows(
    value: object, *, label: str
) -> tuple[Mapping[str, object], ...]:
    """Require one JSON array containing only objects."""
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return tuple(_json_mapping(item, label=f"{label} item") for item in value)


def _integer_pair(value: object, *, label: str) -> tuple[int, int]:
    """Require one JSON integer pair."""
    if (
        not isinstance(value, list)
        or len(value) != _IMAGE_DIMENSIONS
        or any(type(item) is not int for item in value)
    ):
        raise ValueError(f"{label} must be an integer pair")
    return cast(tuple[int, int], tuple(value))


def _number_pair(value: object, *, label: str) -> tuple[float, float]:
    """Require one JSON numeric pair without accepting booleans."""
    if (
        not isinstance(value, list)
        or len(value) != _IMAGE_DIMENSIONS
        or any(type(item) not in (int, float) for item in value)
    ):
        raise ValueError(f"{label} must be a numeric pair")
    return (float(value[0]), float(value[1]))


def _integer_pairs(
    value: object, *, label: str
) -> tuple[tuple[int, int], ...]:
    """Require one JSON array of integer pairs."""
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return tuple(_integer_pair(item, label=f"{label} item") for item in value)


def _required_integer(row: Mapping[str, object], name: str) -> int:
    """Read one required exact integer."""
    value = row.get(name)
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _required_number(row: Mapping[str, object], name: str) -> float:
    """Read one required finite-domain numeric value."""
    value = row.get(name)
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be numeric")
    return float(cast(int | float, value))


def _required_string(row: Mapping[str, object], name: str) -> str:
    """Read one required string."""
    value = row.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _covariance(
    value: object,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Read one optional two-by-two covariance matrix."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != _IMAGE_DIMENSIONS:
        raise ValueError("component covariance must be a two-by-two matrix")
    first = _number_pair(value[0], label="component covariance row")
    second = _number_pair(value[1], label="component covariance row")
    return (first, second)


def _hierarchy_diagnostics_from_json(
    value: object,
) -> SourceHierarchyDiagnostics | None:
    """Load optional hierarchy diagnostics from their exact JSON shape."""
    if value is None:
        return None
    row = _json_mapping(value, label="source hierarchy diagnostics")
    return SourceHierarchyDiagnostics(
        direct_component_count=_required_integer(
            row, "direct_component_count"
        ),
        catalogue_source_count=_required_integer(
            row, "catalogue_source_count"
        ),
        membership_size_histogram=_integer_pairs(
            row.get("membership_size_histogram"),
            label="source hierarchy membership histogram",
        ),
        unattached_component_count=_required_integer(
            row, "unattached_component_count"
        ),
        multiple_finest_feature_attachment_count=_required_integer(
            row, "multiple_finest_feature_attachment_count"
        ),
        branched_lineage_count=_required_integer(
            row, "branched_lineage_count"
        ),
        no_common_convergence_count=_required_integer(
            row, "no_common_convergence_count"
        ),
        unique_convergence_count=_required_integer(
            row, "unique_convergence_count"
        ),
        per_scale_feature_counts=_integer_pairs(
            row.get("per_scale_feature_counts"),
            label="source hierarchy feature counts",
        ),
        adjacent_scale_parent_edge_count=_required_integer(
            row, "adjacent_scale_parent_edge_count"
        ),
        scale_aware_parent_candidate_count=_required_integer(
            row, "scale_aware_parent_candidate_count"
        ),
        persistent_parent_count=_required_integer(
            row, "persistent_parent_count"
        ),
        rejected_parent_ambiguity_count=_required_integer(
            row, "rejected_parent_ambiguity_count"
        ),
        per_scale_parent_candidate_counts=_integer_pairs(
            row.get("per_scale_parent_candidate_counts"),
            label="source hierarchy parent candidate counts",
        ),
    )


def source_association_from_json(value: object) -> SourceAssociationResult:
    """Deserialize and validate one complete association evidence object."""
    document = _json_mapping(value, label="source association")
    components: list[DetectionComponentRecord] = []
    for row in _json_rows(
        document.get("components"), label="association components"
    ):
        labels_are_identity = row.get("component_labels_are_identity")
        if labels_are_identity is not False:
            raise ValueError("component labels must not be identity")
        components.append(
            DetectionComponentRecord(
                component_id=_required_string(row, "component_id"),
                label_value=_required_integer(row, "label_value"),
                canonical_pixel_yx=_integer_pair(
                    row.get("canonical_pixel_yx"),
                    label="component canonical pixel",
                ),
                centroid_yx=_number_pair(
                    row.get("centroid_yx"), label="component centroid"
                ),
                covariance_pixels_squared=_covariance(
                    row.get("covariance_pixels_squared")
                ),
            )
        )
    edges = tuple(
        SourceAssociationEdge(
            first_component_id=_required_string(row, "first_component_id"),
            second_component_id=_required_string(row, "second_component_id"),
            saddle_margin_sigma=_required_number(row, "saddle_margin_sigma"),
            normalized_separation=_required_number(
                row, "normalized_separation"
            ),
        )
        for row in _json_rows(document.get("edges"), label="association edges")
    )
    memberships: list[CatalogueSourceMembership] = []
    for row in _json_rows(
        document.get("memberships"), label="association memberships"
    ):
        component_ids = row.get("component_ids")
        if not isinstance(component_ids, list) or not all(
            isinstance(item, str) for item in component_ids
        ):
            raise ValueError("membership component IDs must be a JSON array")
        memberships.append(
            CatalogueSourceMembership(
                source_id=_required_string(row, "source_id"),
                component_ids=tuple(component_ids),
            )
        )
    ambiguous = document.get("ambiguous_component_ids")
    if not isinstance(ambiguous, list) or not all(
        isinstance(item, str) for item in ambiguous
    ):
        raise ValueError("ambiguous component IDs must be a JSON array")
    return SourceAssociationResult(
        components=tuple(components),
        edges=edges,
        memberships=tuple(memberships),
        ambiguous_component_ids=tuple(ambiguous),
        hierarchy_diagnostics=_hierarchy_diagnostics_from_json(
            document.get("hierarchy_diagnostics")
        ),
    )


def load_source_association(path: Path) -> SourceAssociationResult:
    """Load one required sidecar without accepting an unreadable artifact."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            "source association artifact cannot be loaded"
        ) from error
    return source_association_from_json(value)


def _verified_association_maps(
    association: SourceAssociationResult,
) -> tuple[
    dict[str, DetectionComponentRecord],
    dict[str, CatalogueSourceMembership],
]:
    """Independently verify both association digest domains."""
    component_by_id = {
        component.component_id: component
        for component in association.components
    }
    for component in association.components:
        if component.component_id != detection_component_identifier(
            component.canonical_pixel_yx
        ):
            raise ValueError(
                "association component identity cannot be verified"
            )
    membership_by_id = {
        membership.source_id: membership
        for membership in association.memberships
    }
    for membership in association.memberships:
        if membership.source_id != associated_source_identifier(
            membership.component_ids
        ):
            raise ValueError("association source identity cannot be verified")
    return component_by_id, membership_by_id


def _recorded_support_labels(
    catalogue: tuple[CatalogueSource, ...],
    label_plane: npt.ArrayLike,
    association: SourceAssociationResult,
) -> dict[str, tuple[int, ...]]:
    """Bind persisted direct identities to recovered owner labels."""
    labels = np.asarray(label_plane)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype, np.integer
    ):
        raise ValueError(
            "candidate label plane must be a two-dimensional integer array"
        )
    if np.any(labels < 0):
        raise ValueError(
            "candidate label plane must contain non-negative labels"
        )
    present_labels = {
        int(value) for value in np.unique(labels) if int(value) > 0
    }
    component_by_id, membership_by_id = _verified_association_maps(association)
    identifiers = tuple(source.identifier for source in catalogue)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("associated source identifiers must be unique")
    output: dict[str, tuple[int, ...]] = {}
    claimed_labels: set[int] = set()
    for source in catalogue:
        if (
            source.identifier != source.island_identifier
            or not source.identifier.startswith(_ASSOCIATED_PREFIX)
        ):
            raise ValueError("associated source identity is malformed")
        membership = membership_by_id.get(source.identifier)
        if membership is None or source.component_count != len(
            membership.component_ids
        ):
            raise ValueError("associated source membership cannot be verified")
        support_labels = tuple(
            sorted(
                component_by_id[component_id].label_value
                for component_id in membership.component_ids
            )
        )
        if (
            not support_labels
            or not set(support_labels).issubset(present_labels)
            or claimed_labels.intersection(support_labels)
        ):
            raise ValueError("associated source membership cannot be verified")
        claimed_labels.update(support_labels)
        output[source.identifier] = support_labels
    if (
        set(membership_by_id) != set(identifiers)
        or claimed_labels != present_labels
    ):
        raise ValueError(
            "associated source memberships must partition native supports"
        )
    return output


def _objects_with_support(
    sources: tuple[CatalogueSource, ...],
    support_by_source: Mapping[str, tuple[int, ...]],
    *,
    header: fits.Header,
) -> tuple[AssociatedContinuumCatalogueObject, ...]:
    """Translate verified support unions into evaluator records."""
    celestial = WCS(header, relax=True).celestial
    output: list[AssociatedContinuumCatalogueObject] = []
    for source in sources:
        centre = celestial.all_world2pix(
            [[source.right_ascension_degrees, source.declination_degrees]],
            0,
        )[0]
        integrated_flux = (
            source.association_integrated_flux_jy
            if source.association_integrated_flux_jy is not None
            else source.integrated_flux_jy
        )
        output.append(
            AssociatedContinuumCatalogueObject(
                identifier=source.identifier,
                support_labels=support_by_source[source.identifier],
                centre_xy=(float(centre[0]), float(centre[1])),
                integrated_flux_jy=integrated_flux,
            )
        )
    return tuple(output)


def continuum_catalogue_objects_from_association(
    catalogue: Sequence[CatalogueSource],
    label_plane: npt.ArrayLike,
    association: SourceAssociationResult,
    *,
    finder_id: ContinuumFinderId,
    header: fits.Header,
) -> tuple[Any, ...]:
    """Translate associated Hebog rows from explicit membership evidence."""
    sources = tuple(catalogue)
    associated = finder_id == "hebog" and any(
        (source.island_identifier or "").startswith(_ASSOCIATED_PREFIX)
        for source in sources
    )
    if not associated:
        return continuum_catalogue_objects(
            sources,
            label_plane,
            finder_id=finder_id,
            header=header,
        )
    if not all(
        (source.island_identifier or "").startswith(_ASSOCIATED_PREFIX)
        for source in sources
    ):
        raise ValueError(
            "Hebog catalogue cannot mix segment and associated sources"
        )
    return _objects_with_support(
        sources,
        _recorded_support_labels(sources, label_plane, association),
        header=header,
    )


def _associated_catalogue(
    catalogue: Sequence[CatalogueSource], finder_id: str
) -> bool:
    """Return whether one successful run requires association provenance."""
    return finder_id == "hebog" and any(
        (source.island_identifier or "").startswith(_ASSOCIATED_PREFIX)
        for source in catalogue
    )


class ParentConstructionContinuumImageCompiler(RecoveryContinuumImageCompiler):
    """Compile associated Hebog runs only from explicit sidecar evidence."""

    def __init__(
        self,
        terminal_globals: dict[str, Any],
        *,
        association_path: AssociationPath,
    ) -> None:
        super().__init__(terminal_globals)
        self._association_path = association_path
        self._fallback_candidate_objects = cast(
            CandidateObjects, terminal_globals["_candidate_objects"]
        )

    def __call__(  # noqa: PLR0913, PLR0917
        self,
        verified: Any,
        campaign_input: Any,
        run: Any,
        dataset: Any,
        recipe: Any,
        review: Any,
        specifications: Sequence[Any],
    ) -> dict[str, Any]:
        """Compile one finder while preserving every historical policy."""
        image_key = campaign_input.input_id
        if run.result.status != "success":
            failure = run.result.failure
            return cast(
                dict[str, Any],
                self._terminal["_failed_endpoint_observations"](
                    specifications,
                    image_key=image_key,
                    reason=(
                        failure.message
                        if failure is not None
                        else "finder failed"
                    ),
                ),
            )
        if self._image_key != image_key or self._common is None:
            self._common = self._prepare_common(
                verified,
                campaign_input,
                dataset,
                recipe,
                review,
            )
            self._image_key = image_key
        common = self._common
        catalogue, candidate_labels = self._terminal["_catalogue_and_labels"](
            run
        )
        truth_labels, candidate_labels = label_planes_on_valid_domain(
            common.truth_labels,
            candidate_labels,
            common.valid_pixels,
        )
        if _associated_catalogue(catalogue, run.result.finder_id):
            candidates = continuum_catalogue_objects_from_association(
                catalogue,
                candidate_labels,
                load_source_association(self._association_path(run)),
                finder_id=run.result.finder_id,
                header=common.header,
            )
        else:
            candidates = self._fallback_candidate_objects(
                catalogue,
                candidate_labels,
                finder_id=run.result.finder_id,
                header=common.header,
            )
        values = self._terminal["measure_continuum_image"](
            common.truth,
            candidates,
            truth_label_plane=truth_labels,
            candidate_label_plane=candidate_labels,
            beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
        )
        observation_type = self._terminal["EndpointObservation"]
        output: dict[str, Any] = {}
        for specification in specifications:
            untyped = cast(
                float | tuple[float, ...],
                values[specification.metric_family][specification.stratum],
            )
            row = untyped if isinstance(untyped, tuple) else (untyped,)
            output[specification.endpoint_id] = observation_type(
                image_key=image_key,
                values=tuple(float(item) for item in row),
            )
        return output


def install_parent_construction_association_evaluation(
    terminal_globals: dict[str, Any],
    *,
    association_path: AssociationPath,
) -> None:
    """Replace only the compiler object with the sidecar-aware overlay."""
    current = terminal_globals.get("_continuum_image_observations")
    candidate_objects = terminal_globals.get("_candidate_objects")
    measure_image = terminal_globals.get("measure_continuum_image")
    if (
        not isinstance(current, RecoveryContinuumImageCompiler)
        or not callable(candidate_objects)
        or not callable(measure_image)
        or not callable(association_path)
    ):
        raise ValueError("parent-construction evaluation seam changed")
    terminal_globals["_continuum_image_observations"] = (
        ParentConstructionContinuumImageCompiler(
            terminal_globals,
            association_path=association_path,
        )
    )
