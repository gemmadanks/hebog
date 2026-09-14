# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Finder-specific source-union projections for validation evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from typing import Literal

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.data_models.source_association import SourceAssociationResult
from hebog.validation.comparison import CatalogueSource

FinderId = Literal["current-hebog", "released-pybdsf"]
NativeTopologyDomain = Literal["component-owner", "island-owner"]
SourceUnionDerivation = Literal[
    "hebog-association-membership-v1-direct-topology",
    "pybdsf-source-model-dominance-v1-derived-topology",
]
_IMAGE_DIMENSIONS = 2


def _finite_centre(value: tuple[float, float], *, name: str) -> None:
    """Require one finite two-dimensional pixel centre."""
    if len(value) != _IMAGE_DIMENSIONS or not all(
        isfinite(item) for item in value
    ):
        raise ValueError(f"{name} must contain two finite values")


def _positive(value: float, *, name: str) -> None:
    """Require one finite positive physical value."""
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")


def _label_plane(value: npt.ArrayLike, *, name: str) -> npt.NDArray[np.int32]:
    """Return one immutable non-negative two-dimensional label plane."""
    labels = np.asarray(value)
    if (
        labels.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any(labels < 0)
        or np.any(labels > np.iinfo(np.int32).max)
    ):
        raise ValueError(f"{name} must be a non-negative 2D integer array")
    output = np.ascontiguousarray(labels, dtype=np.int32)
    output.setflags(write=False)
    return output


def _world_to_pixel(
    row: CatalogueSource, celestial: WCS, *, name: str
) -> tuple[float, float]:
    """Map one catalogue position into the reviewed pixel frame."""
    centre = celestial.all_world2pix(
        [[row.right_ascension_degrees, row.declination_degrees]], 0
    )[0]
    output = (float(centre[0]), float(centre[1]))
    _finite_centre(output, name=name)
    return output


@dataclass(frozen=True, slots=True)
class SourceUnionComponent:
    """One fitted component and its explicit catalogue-source membership."""

    identifier: str
    source_identifier: str
    native_support_label: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Require stable membership, ownership, and observables."""
        if not self.identifier or not self.source_identifier:
            raise ValueError("source-union component identities are required")
        if (
            type(self.native_support_label) is not int
            or self.native_support_label <= 0
        ):
            raise ValueError("source-union component label must be positive")
        _finite_centre(self.centre_xy, name="component centre")
        _positive(self.integrated_flux_jy, name="component flux")


@dataclass(frozen=True, slots=True)
class SourceUnionSource:
    """One binding source row and the components assigned to it."""

    identifier: str
    member_component_ids: tuple[str, ...]
    native_support_labels: tuple[int, ...]
    centre_xy: tuple[float, float]
    integrated_flux_jy: float

    def __post_init__(self) -> None:
        """Require canonical non-empty membership and source observables."""
        if not self.identifier:
            raise ValueError("source-union source identity is required")
        if not self.member_component_ids or self.member_component_ids != tuple(
            sorted(set(self.member_component_ids))
        ):
            raise ValueError("source-union component membership is invalid")
        if (
            not self.native_support_labels
            or self.native_support_labels
            != tuple(sorted(set(self.native_support_labels)))
            or min(self.native_support_labels) <= 0
        ):
            raise ValueError("source-union native labels are invalid")
        _finite_centre(self.centre_xy, name="source centre")
        _positive(self.integrated_flux_jy, name="source flux")


@dataclass(frozen=True, slots=True)
class SourceUnionProjection:
    """Transient aligned ownership emitted by one finder adapter."""

    finder_id: FinderId
    sources: tuple[SourceUnionSource, ...]
    components: tuple[SourceUnionComponent, ...]
    native_owner_label_plane: npt.NDArray[np.int32]
    source_union_label_plane: npt.NDArray[np.int32]
    native_topology_domain: NativeTopologyDomain
    source_union_derivation: SourceUnionDerivation
    unowned_native_support_labels: tuple[int, ...]

    def __post_init__(self) -> None:
        """Require a coherent finder/domain/derivation projection."""
        if self.native_owner_label_plane.shape != (
            self.source_union_label_plane.shape
        ):
            raise ValueError("source-union projection planes must share shape")
        expected = {
            "current-hebog": (
                "component-owner",
                "hebog-association-membership-v1-direct-topology",
            ),
            "released-pybdsf": (
                "island-owner",
                "pybdsf-source-model-dominance-v1-derived-topology",
            ),
        }
        if expected.get(self.finder_id) != (
            self.native_topology_domain,
            self.source_union_derivation,
        ):
            raise ValueError("source-union projection semantics are invalid")
        if self.unowned_native_support_labels != tuple(
            sorted(set(self.unowned_native_support_labels))
        ) or any(item <= 0 for item in self.unowned_native_support_labels):
            raise ValueError("unowned native support labels are invalid")


@dataclass(frozen=True, slots=True)
class PyBdsfSourceRow:
    """Native PyBDSF ``srl`` observables in the adapter's pixel frame."""

    island_id: int
    source_id: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float
    gaussian_count: int

    def __post_init__(self) -> None:
        """Require one canonical native source row."""
        if (
            type(self.island_id) is not int
            or self.island_id < 0
            or type(self.source_id) is not int
            or self.source_id < 0
            or type(self.gaussian_count) is not int
            or self.gaussian_count <= 0
        ):
            raise ValueError("PyBDSF source identity and count are invalid")
        _finite_centre(self.centre_xy, name="PyBDSF source centre")
        _positive(self.integrated_flux_jy, name="PyBDSF source flux")


@dataclass(frozen=True, slots=True)
class PyBdsfGaussianRow:
    """One accepted PyBDSF Gaussian model in the adapter's pixel frame."""

    identifier: str
    island_id: int
    source_id: int
    centre_xy: tuple[float, float]
    integrated_flux_jy: float
    peak_flux_jy_per_beam: float
    covariance_pixels_squared: tuple[tuple[float, float], tuple[float, float]]

    def __post_init__(self) -> None:
        """Require one finite positive-definite accepted Gaussian model."""
        if (
            not self.identifier
            or type(self.island_id) is not int
            or self.island_id < 0
            or type(self.source_id) is not int
            or self.source_id < 0
        ):
            raise ValueError("PyBDSF Gaussian identity is invalid")
        _finite_centre(self.centre_xy, name="PyBDSF Gaussian centre")
        _positive(self.integrated_flux_jy, name="PyBDSF Gaussian flux")
        _positive(self.peak_flux_jy_per_beam, name="PyBDSF Gaussian peak")
        covariance = np.asarray(self.covariance_pixels_squared)
        if (
            covariance.shape != (_IMAGE_DIMENSIONS, _IMAGE_DIMENSIONS)
            or not np.all(np.isfinite(covariance))
            or not np.array_equal(covariance, covariance.T)
            or np.min(np.linalg.eigvalsh(covariance)) <= 0.0
        ):
            raise ValueError("PyBDSF Gaussian covariance is invalid")


def project_hebog_source_unions(
    *,
    source_catalogue: tuple[CatalogueSource, ...],
    component_catalogue: tuple[CatalogueSource, ...],
    association: SourceAssociationResult,
    measurement_component_labels: npt.ArrayLike,
    header: fits.Header,
) -> SourceUnionProjection:
    """Project Hebog's exact association membership into source unions."""
    labels = _label_plane(
        measurement_component_labels,
        name="Hebog measurement component labels",
    )
    source_by_id = {item.identifier: item for item in source_catalogue}
    component_by_id = {item.identifier: item for item in component_catalogue}
    membership_ids = {item.source_id for item in association.memberships}
    association_component_ids = {
        item.component_id for item in association.components
    }
    if (
        len(source_by_id) != len(source_catalogue)
        or set(source_by_id) != membership_ids
    ):
        raise ValueError("Hebog source catalogue and associations disagree")
    if (
        len(component_by_id) != len(component_catalogue)
        or set(component_by_id) != association_component_ids
    ):
        raise ValueError("Hebog component catalogue and associations disagree")
    association_by_id = {
        item.component_id: item for item in association.components
    }
    positive_labels = {int(item) for item in np.unique(labels) if item > 0}
    if positive_labels != {
        item.label_value for item in association.components
    }:
        raise ValueError("Hebog owner labels and associations disagree")

    celestial = WCS(header, relax=True).celestial
    source_label_by_id = {
        item.source_id: index
        for index, item in enumerate(association.memberships, start=1)
    }
    union_labels = np.zeros(labels.shape, dtype=np.int32)
    components: list[SourceUnionComponent] = []
    sources: list[SourceUnionSource] = []
    for membership in association.memberships:
        member_labels = tuple(
            sorted(
                association_by_id[component_id].label_value
                for component_id in membership.component_ids
            )
        )
        membership_mask = np.isin(labels, member_labels)
        if not np.any(membership_mask):
            raise ValueError("Hebog owner labels and associations disagree")
        if np.any(union_labels[membership_mask] != 0):
            raise ValueError(
                "Hebog source ownership and associations disagree"
            )
        union_labels[membership_mask] = source_label_by_id[
            membership.source_id
        ]
        source_row = source_by_id[membership.source_id]
        sources.append(
            SourceUnionSource(
                identifier=membership.source_id,
                member_component_ids=membership.component_ids,
                native_support_labels=member_labels,
                centre_xy=_world_to_pixel(
                    source_row, celestial, name="Hebog source centre"
                ),
                integrated_flux_jy=source_row.integrated_flux_jy,
            )
        )
        for component_id in membership.component_ids:
            row = component_by_id[component_id]
            components.append(
                SourceUnionComponent(
                    identifier=component_id,
                    source_identifier=membership.source_id,
                    native_support_label=(
                        association_by_id[component_id].label_value
                    ),
                    centre_xy=_world_to_pixel(
                        row, celestial, name="Hebog component centre"
                    ),
                    integrated_flux_jy=row.integrated_flux_jy,
                )
            )
    if np.any((labels > 0) != (union_labels > 0)):
        raise ValueError("Hebog source ownership and owner labels disagree")
    union_labels.setflags(write=False)
    return SourceUnionProjection(
        finder_id="current-hebog",
        sources=tuple(sources),
        components=tuple(
            sorted(components, key=lambda component: component.identifier)
        ),
        native_owner_label_plane=labels,
        source_union_label_plane=union_labels,
        native_topology_domain="component-owner",
        source_union_derivation=(
            "hebog-association-membership-v1-direct-topology"
        ),
        unowned_native_support_labels=(),
    )


def _pybdsf_source_identifier(island_id: int, source_id: int) -> str:
    """Return one globally unique canonical PyBDSF source identity."""
    return f"pybdsf-island-{island_id}-source-{source_id}"


def _source_log_model(
    coordinates_xy: npt.NDArray[np.float64],
    gaussians: tuple[PyBdsfGaussianRow, ...],
) -> npt.NDArray[np.float64]:
    """Evaluate one summed Gaussian model in stable log space."""
    component_models: list[npt.NDArray[np.float64]] = []
    for gaussian in gaussians:
        covariance = np.asarray(
            gaussian.covariance_pixels_squared, dtype=np.float64
        )
        inverse = np.linalg.inv(covariance)
        offset = coordinates_xy - np.asarray(
            gaussian.centre_xy, dtype=np.float64
        )
        quadratic = np.einsum(
            "pi,ij,pj->p", offset, inverse, offset, optimize=True
        )
        component_models.append(
            np.log(gaussian.peak_flux_jy_per_beam) - 0.5 * quadratic
        )
    return np.logaddexp.reduce(np.asarray(component_models), axis=0)


@dataclass(frozen=True, slots=True)
class _ValidatedPyBdsfInputs:
    """Canonical checked PyBDSF rows and native-island identities."""

    labels: npt.NDArray[np.int32]
    ordered_sources: tuple[PyBdsfSourceRow, ...]
    source_keys: tuple[tuple[int, int], ...]
    gaussian_groups: dict[tuple[int, int], tuple[PyBdsfGaussianRow, ...]]
    native_labels: frozenset[int]


def _validated_pybdsf_inputs(
    source_rows: tuple[PyBdsfSourceRow, ...],
    gaussian_rows: tuple[PyBdsfGaussianRow, ...],
    native_island_labels: npt.ArrayLike,
) -> _ValidatedPyBdsfInputs:
    """Canonicalize rows and fail closed on every identity mismatch."""
    labels = _label_plane(
        native_island_labels, name="PyBDSF native island labels"
    )
    ordered_sources = tuple(
        sorted(source_rows, key=lambda item: (item.island_id, item.source_id))
    )
    source_keys = tuple(
        (item.island_id, item.source_id) for item in ordered_sources
    )
    if len(set(source_keys)) != len(source_keys):
        raise ValueError("PyBDSF source/Gaussian membership is inconsistent")
    gaussian_ids = tuple(item.identifier for item in gaussian_rows)
    if len(set(gaussian_ids)) != len(gaussian_ids):
        raise ValueError("PyBDSF source/Gaussian membership is inconsistent")
    mutable_groups: dict[tuple[int, int], list[PyBdsfGaussianRow]] = (
        defaultdict(list)
    )
    for gaussian in gaussian_rows:
        mutable_groups[(gaussian.island_id, gaussian.source_id)].append(
            gaussian
        )
    groups = {
        key: tuple(sorted(value, key=lambda item: item.identifier))
        for key, value in mutable_groups.items()
    }
    if set(groups) != set(source_keys) or any(
        source.gaussian_count != len(groups[key])
        for key, source in zip(source_keys, ordered_sources, strict=True)
    ):
        raise ValueError("PyBDSF source/Gaussian membership is inconsistent")
    native_labels = frozenset(
        int(item) for item in np.unique(labels) if item > 0
    )
    native_island_ids = {item - 1 for item in native_labels}
    if any(island_id not in native_island_ids for island_id, _ in source_keys):
        raise ValueError("PyBDSF source/Gaussian membership is inconsistent")
    return _ValidatedPyBdsfInputs(
        labels,
        ordered_sources,
        source_keys,
        groups,
        native_labels,
    )


def _partition_pybdsf_islands(
    inputs: _ValidatedPyBdsfInputs,
) -> tuple[npt.NDArray[np.int32], tuple[int, ...]]:
    """Partition modelled islands and retain whole fitless islands unowned."""
    source_label_by_key = {
        key: index for index, key in enumerate(inputs.source_keys, start=1)
    }
    keys_by_island: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for key in inputs.source_keys:
        keys_by_island[key[0]].append(key)
    union_labels = np.zeros(inputs.labels.shape, dtype=np.int32)
    unowned: list[int] = []
    for native_label in sorted(inputs.native_labels):
        island_id = native_label - 1
        island_keys = keys_by_island.get(island_id, [])
        coordinate_yx = np.argwhere(inputs.labels == native_label)
        if not island_keys:
            unowned.append(native_label)
        elif len(island_keys) == 1:
            union_labels[inputs.labels == native_label] = source_label_by_key[
                island_keys[0]
            ]
        else:
            coordinate_xy = np.asarray(
                coordinate_yx[:, ::-1], dtype=np.float64
            )
            models = np.asarray(
                [
                    _source_log_model(
                        coordinate_xy, inputs.gaussian_groups[key]
                    )
                    for key in island_keys
                ]
            )
            winners = np.argmax(models, axis=0)
            for coordinate, winner in zip(coordinate_yx, winners, strict=True):
                union_labels[tuple(coordinate)] = source_label_by_key[
                    island_keys[int(winner)]
                ]
    _validate_pybdsf_partition(
        inputs.labels,
        union_labels,
        source_label_by_key,
        unowned,
    )
    union_labels.setflags(write=False)
    return union_labels, tuple(unowned)


def _validate_pybdsf_partition(
    labels: npt.NDArray[np.int32],
    union_labels: npt.NDArray[np.int32],
    source_label_by_key: dict[tuple[int, int], int],
    unowned: list[int],
) -> None:
    """Require every modelled island pixel and real source exactly once."""
    for key, source_label in source_label_by_key.items():
        if not np.any(union_labels == source_label):
            raise ValueError("PyBDSF source owns no native pixels")
        native_label = key[0] + 1
        if np.any((union_labels == source_label) & (labels != native_label)):
            raise ValueError("PyBDSF source owns pixels outside its island")
    modelled = {
        int(item) for item in np.unique(labels) if item > 0
    }.difference(unowned)
    if np.any(np.isin(labels, tuple(modelled)) != (union_labels > 0)):
        raise ValueError("PyBDSF modelled island pixels are not partitioned")


def _pybdsf_projection_records(
    inputs: _ValidatedPyBdsfInputs,
) -> tuple[tuple[SourceUnionSource, ...], tuple[SourceUnionComponent, ...]]:
    """Project native source observables and diagnostic Gaussian rows."""
    components = tuple(
        SourceUnionComponent(
            identifier=item.identifier,
            source_identifier=_pybdsf_source_identifier(
                item.island_id, item.source_id
            ),
            native_support_label=item.island_id + 1,
            centre_xy=item.centre_xy,
            integrated_flux_jy=item.integrated_flux_jy,
        )
        for item in sorted(
            (
                gaussian
                for group in inputs.gaussian_groups.values()
                for gaussian in group
            ),
            key=lambda value: value.identifier,
        )
    )
    sources = tuple(
        SourceUnionSource(
            identifier=_pybdsf_source_identifier(
                item.island_id, item.source_id
            ),
            member_component_ids=tuple(
                gaussian.identifier
                for gaussian in inputs.gaussian_groups[
                    (item.island_id, item.source_id)
                ]
            ),
            native_support_labels=(item.island_id + 1,),
            centre_xy=item.centre_xy,
            integrated_flux_jy=item.integrated_flux_jy,
        )
        for item in inputs.ordered_sources
    )
    return sources, components


def derive_pybdsf_source_model_dominance(
    *,
    source_rows: tuple[PyBdsfSourceRow, ...],
    gaussian_rows: tuple[PyBdsfGaussianRow, ...],
    native_island_labels: npt.ArrayLike,
) -> SourceUnionProjection:
    """Derive a validation-only PyBDSF source-owner topology."""
    inputs = _validated_pybdsf_inputs(
        source_rows, gaussian_rows, native_island_labels
    )
    union_labels, unowned = _partition_pybdsf_islands(inputs)
    sources, components = _pybdsf_projection_records(inputs)
    return SourceUnionProjection(
        finder_id="released-pybdsf",
        sources=sources,
        components=components,
        native_owner_label_plane=inputs.labels,
        source_union_label_plane=union_labels,
        native_topology_domain="island-owner",
        source_union_derivation=(
            "pybdsf-source-model-dominance-v1-derived-topology"
        ),
        unowned_native_support_labels=unowned,
    )
