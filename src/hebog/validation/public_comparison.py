# pyright: reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Scientific adapters for the approved Phase 5 public comparisons.

The functions in this module are deliberately independent of FITS and archive
I/O.  They make the reviewed SDC1 selection arithmetic and the Hydra catalogue
normalization available as small, deterministic array-to-record operations.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import atan2, cos, isfinite, log, radians, sin, sqrt
from typing import Literal, TypeAlias

import numpy as np
import numpy.typing as npt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import min_weight_full_bipartite_matching
from scipy.spatial import cKDTree

FloatArray: TypeAlias = npt.NDArray[np.float64]
HydraFinder: TypeAlias = Literal[
    "aegean", "caesar", "profound", "pybdsf", "selavy"
]
HydraDepth: TypeAlias = Literal["deep", "shallow"]

_SDC1_BEAM_FWHM_ARCSEC = 0.6
_SDC1_NOISE_JY_PER_BEAM = 73e-9
_LOW_SNR_MINIMUM = 5.0
_LOW_SNR_MAXIMUM = 8.0
_PAIR_MINIMUM_SOURCES = 2
_MATCH_FLUX_DECIMAL_PLACES = 9
_POSITION_ANGLE_MINIMUM_AXIS_RATIO = 1.1
_SELECTION_STRATA = (
    "sparse",
    "ordinary",
    "crowded",
    "resolved",
    "close-pair",
    "high-dynamic-range",
    "low-apparent-SNR",
    "primary-beam-boundary",
)


@dataclass(frozen=True, slots=True)
class PublicTileAttributes:
    """Truth-only attributes for one admitted aligned SDC1 tile."""

    tile_id: str
    x_start: int
    y_start: int
    source_count: int
    resolved_fraction: float
    closest_pair_beams: float
    dynamic_range: float
    low_snr_fraction: float
    mean_primary_beam: float
    truth_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PublicTileTruth:
    """Truth arrays needed to derive one tile's selection attributes."""

    identifiers: npt.ArrayLike
    ra_deg: npt.ArrayLike
    dec_deg: npt.ArrayLike
    major_fwhm_arcsec: npt.ArrayLike
    apparent_flux_jy: npt.ArrayLike
    peak_snr: npt.ArrayLike


@dataclass(frozen=True, slots=True)
class SelectedPublicTile:
    """One unique SDC1 tile selected for a reviewed stratum."""

    stratum: str
    tile: PublicTileAttributes


@dataclass(frozen=True, slots=True)
class HydraComponent:
    """Finder-neutral view of one published Hydra catalogue component.

    Native identifiers remain strings so numeric and textual finder schemas
    are represented without information-losing coercion.  Missing peak flux
    is explicit for ProFound rather than inferred from integrated flux.
    """

    finder_id: HydraFinder
    depth: HydraDepth
    native_id: str
    native_island_id: str
    native_component_id: str
    ra_deg: float
    dec_deg: float
    peak_flux_jy_per_beam: float | None
    integrated_flux_jy: float
    major_axis_arcsec: float
    minor_axis_arcsec: float
    position_angle_deg: float


@dataclass(frozen=True, slots=True)
class PublicCatalogueComponent:
    """Minimal finder-neutral component used by the public comparisons."""

    identifier: str
    right_ascension_degrees: float
    declination_degrees: float
    integrated_flux_jy: float
    peak_signal_to_noise: float | None = None
    major_axis_arcsec: float | None = None
    minor_axis_arcsec: float | None = None
    position_angle_degrees: float | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous identifiers and non-physical core values."""
        if not self.identifier:
            raise ValueError("public catalogue identifier must not be empty")
        required = (
            self.right_ascension_degrees,
            self.declination_degrees,
            self.integrated_flux_jy,
        )
        if not all(isfinite(value) for value in required):
            raise ValueError("public catalogue core values must be finite")
        if self.integrated_flux_jy <= 0.0:
            raise ValueError(
                "public catalogue integrated flux must be positive"
            )
        optional = (
            self.peak_signal_to_noise,
            self.major_axis_arcsec,
            self.minor_axis_arcsec,
            self.position_angle_degrees,
        )
        if any(
            value is not None and not isfinite(value) for value in optional
        ):
            raise ValueError("public catalogue optional values must be finite")
        if (
            self.peak_signal_to_noise is not None
            and self.peak_signal_to_noise < 0
        ):
            raise ValueError(
                "public catalogue signal-to-noise must be non-negative"
            )
        for axis in (self.major_axis_arcsec, self.minor_axis_arcsec):
            if axis is not None and axis < 0.0:
                raise ValueError("public catalogue axes must be non-negative")


@dataclass(frozen=True, slots=True)
class PublicCatalogueAssociation:
    """One primary or eligible public-catalogue association."""

    left_identifier: str
    right_identifier: str
    separation_beams: float
    offset_x_beams: float
    offset_y_beams: float
    integrated_flux_ratio: float
    absolute_log_flux_ratio: float


@dataclass(frozen=True, slots=True)
class PublicCatalogueAssociationReport:
    """Deterministic eligible graph and its primary one-to-one assignment."""

    primary_associations: tuple[PublicCatalogueAssociation, ...]
    eligible_associations: tuple[PublicCatalogueAssociation, ...]
    unmatched_left_identifiers: tuple[str, ...]
    unmatched_right_identifiers: tuple[str, ...]
    left_identifiers_with_multiple_edges: tuple[str, ...]
    right_identifiers_with_multiple_edges: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _HydraMapping:
    native_id: str
    island_id: str
    component_id: str
    ra: str
    dec: str
    peak_flux: str | None
    integrated_flux: str
    major_axis: str
    minor_axis: str
    position_angle: str
    flux_scale: float
    axis_scale: float


_HYDRA_MAPPINGS: Mapping[HydraFinder, _HydraMapping] = {
    "aegean": _HydraMapping(
        native_id="id",
        island_id="island_id",
        component_id="source_id",
        ra="ra",
        dec="dec",
        peak_flux="flux_peak",
        integrated_flux="flux_total",
        major_axis="semimajor",
        minor_axis="semiminor",
        position_angle="pa",
        flux_scale=1.0,
        axis_scale=1.0,
    ),
    "caesar": _HydraMapping(
        native_id="id",
        island_id="id",
        component_id="component_id",
        ra="ra",
        dec="dec",
        peak_flux="flux_peak",
        integrated_flux="flux_total",
        major_axis="bmaj_wcs",
        minor_axis="bmin_wcs",
        position_angle="pa_wcs",
        flux_scale=1.0,
        axis_scale=1.0,
    ),
    "profound": _HydraMapping(
        native_id="unique_id",
        island_id="id",
        component_id="component_id",
        ra="ra_centre",
        dec="dec_centre",
        peak_flux=None,
        integrated_flux="flux_total",
        major_axis="semimajor",
        minor_axis="semiminor",
        position_angle="pa",
        flux_scale=1.0,
        axis_scale=3600.0,
    ),
    "pybdsf": _HydraMapping(
        native_id="id",
        island_id="island_id",
        component_id="source_id",
        ra="ra",
        dec="dec",
        peak_flux="flux_peak",
        integrated_flux="flux_total",
        major_axis="major",
        minor_axis="minor",
        position_angle="pa",
        flux_scale=1.0,
        axis_scale=3600.0,
    ),
    "selavy": _HydraMapping(
        native_id="id",
        island_id="island_id",
        component_id="component_id",
        ra="ra",
        dec="dec",
        peak_flux="flux_peak",
        integrated_flux="flux_total",
        major_axis="major",
        minor_axis="minor",
        position_angle="pa",
        flux_scale=1e-3,
        axis_scale=1.0,
    ),
}


def gaussian_fwhm_arcsec(
    size_code: npt.ArrayLike,
    major_arcsec: npt.ArrayLike,
    minor_arcsec: npt.ArrayLike,
) -> tuple[FloatArray, FloatArray]:
    """Convert the three official SDC1 size meanings to Gaussian FWHM."""
    codes = np.asarray(size_code)
    major = np.asarray(major_arcsec, dtype=np.float64)
    minor = np.asarray(minor_arcsec, dtype=np.float64)
    if codes.shape != major.shape or major.shape != minor.shape:
        raise ValueError("size code and axis arrays must have equal shapes")
    if not np.all(np.isin(codes, (1, 2, 3))):
        raise ValueError("SDC1 size code must be 1, 2, or 3")
    if not np.all(np.isfinite(major)) or not np.all(np.isfinite(minor)):
        raise ValueError("SDC1 source axes must be finite")
    if np.any(major < 0.0) or np.any(minor < 0.0):
        raise ValueError("SDC1 source axes must be non-negative")

    factors = np.choose(
        codes.astype(np.int64) - 1,
        (2.355 / 5.0, 1.0, np.sqrt(2.0)),
    )
    return major * factors, minor * factors


def apparent_peak_snr(
    *,
    integrated_flux_jy: npt.ArrayLike,
    primary_beam_response: npt.ArrayLike,
    major_fwhm_arcsec: npt.ArrayLike,
    minor_fwhm_arcsec: npt.ArrayLike,
) -> FloatArray:
    """Return the approved beam-convolved apparent peak SNR for SDC1."""
    flux = np.asarray(integrated_flux_jy, dtype=np.float64)
    response = np.asarray(primary_beam_response, dtype=np.float64)
    major = np.asarray(major_fwhm_arcsec, dtype=np.float64)
    minor = np.asarray(minor_fwhm_arcsec, dtype=np.float64)
    if not (flux.shape == response.shape == major.shape == minor.shape):
        raise ValueError("apparent peak SNR inputs must have equal shapes")
    if not all(
        np.all(np.isfinite(values))
        for values in (flux, response, major, minor)
    ):
        raise ValueError("apparent peak SNR inputs must be finite")
    if np.any(response < 0.0) or np.any(major < 0.0) or np.any(minor < 0.0):
        raise ValueError("primary-beam response and axes must be non-negative")

    apparent_flux = flux * response
    convolved_area = np.sqrt(major**2 + _SDC1_BEAM_FWHM_ARCSEC**2)
    convolved_area *= np.sqrt(minor**2 + _SDC1_BEAM_FWHM_ARCSEC**2)
    return (
        apparent_flux
        * _SDC1_BEAM_FWHM_ARCSEC**2
        / convolved_area
        / _SDC1_NOISE_JY_PER_BEAM
    )


def sdc1_position_angle_degrees(position_angle_degrees: float) -> float:
    """Convert SDC1 clockwise-from-west angles to Hebog axial degrees."""
    if not isfinite(position_angle_degrees):
        raise ValueError("SDC1 position angle must be finite")
    return (position_angle_degrees - 90.0) % 180.0


def build_public_tile_attributes(
    *,
    tile_id: str,
    x_start: int,
    y_start: int,
    truth: PublicTileTruth,
    mean_primary_beam: float,
) -> PublicTileAttributes:
    """Calculate the complete reviewed attribute set for one SDC1 tile."""
    identifiers = np.asarray(truth.identifiers)
    ra = np.asarray(truth.ra_deg, dtype=np.float64)
    dec = np.asarray(truth.dec_deg, dtype=np.float64)
    major = np.asarray(truth.major_fwhm_arcsec, dtype=np.float64)
    flux = np.asarray(truth.apparent_flux_jy, dtype=np.float64)
    snr = np.asarray(truth.peak_snr, dtype=np.float64)
    if not (
        identifiers.shape
        == ra.shape
        == dec.shape
        == major.shape
        == flux.shape
        == snr.shape
    ):
        raise ValueError("SDC1 tile source arrays must have equal shapes")
    if identifiers.ndim != 1:
        raise ValueError("SDC1 tile source arrays must be one-dimensional")
    if not all(
        np.all(np.isfinite(values)) for values in (ra, dec, major, flux, snr)
    ):
        raise ValueError("SDC1 tile source arrays must be finite")
    if not np.isfinite(mean_primary_beam):
        raise ValueError("mean primary-beam response must be finite")

    count = len(identifiers)
    resolved_fraction = (
        float(np.mean(major > _SDC1_BEAM_FWHM_ARCSEC)) if count else 0.0
    )
    low_snr_fraction = (
        float(np.mean((snr >= _LOW_SNR_MINIMUM) & (snr <= _LOW_SNR_MAXIMUM)))
        if count
        else 0.0
    )
    positive_flux = flux[flux > 0.0]
    dynamic_range = (
        float(np.max(positive_flux) / np.median(positive_flux))
        if len(positive_flux)
        else 0.0
    )
    closest_pair_beams = _closest_pair_beams(ra, dec)
    return PublicTileAttributes(
        tile_id=tile_id,
        x_start=x_start,
        y_start=y_start,
        source_count=count,
        resolved_fraction=resolved_fraction,
        closest_pair_beams=closest_pair_beams,
        dynamic_range=dynamic_range,
        low_snr_fraction=low_snr_fraction,
        mean_primary_beam=float(mean_primary_beam),
        truth_ids=tuple(int(identifier) for identifier in identifiers),
    )


def _closest_pair_beams(ra_deg: FloatArray, dec_deg: FloatArray) -> float:
    """Return exact spherical nearest-neighbour separation in beam units."""
    if len(ra_deg) < _PAIR_MINIMUM_SOURCES:
        return float("inf")
    ra_rad = np.deg2rad(ra_deg)
    dec_rad = np.deg2rad(dec_deg)
    cos_dec = np.cos(dec_rad)
    unit_vectors = np.column_stack(
        (
            cos_dec * np.cos(ra_rad),
            cos_dec * np.sin(ra_rad),
            np.sin(dec_rad),
        )
    )
    distances, _indices = cKDTree(unit_vectors).query(unit_vectors, k=2)
    chord = float(np.min(distances[:, 1]))
    separation_rad = 2.0 * np.arcsin(min(1.0, chord / 2.0))
    return float(np.rad2deg(separation_rad) * 3600.0 / _SDC1_BEAM_FWHM_ARCSEC)


def select_public_tiles(
    admitted_tiles: Sequence[PublicTileAttributes],
) -> tuple[SelectedPublicTile, ...]:
    """Select eight unique tiles with the exact reviewed ranking rules."""
    if len(admitted_tiles) < len(_SELECTION_STRATA):
        raise ValueError("selection requires at least eight admitted tiles")
    tile_ids = [tile.tile_id for tile in admitted_tiles]
    if len(set(tile_ids)) != len(tile_ids):
        raise ValueError("admitted tile identifiers must be unique")
    median_count = float(
        np.median([tile.source_count for tile in admitted_tiles])
    )

    def tie(tile: PublicTileAttributes) -> tuple[int, int]:
        return tile.y_start, tile.x_start

    rankings: dict[
        str, Callable[[PublicTileAttributes], tuple[float, int, int]]
    ] = {
        "sparse": lambda tile: (float(tile.source_count), *tie(tile)),
        "ordinary": lambda tile: (
            abs(tile.source_count - median_count),
            *tie(tile),
        ),
        "crowded": lambda tile: (-float(tile.source_count), *tie(tile)),
        "resolved": lambda tile: (-tile.resolved_fraction, *tie(tile)),
        "close-pair": lambda tile: (tile.closest_pair_beams, *tie(tile)),
        "high-dynamic-range": lambda tile: (
            -tile.dynamic_range,
            *tie(tile),
        ),
        "low-apparent-SNR": lambda tile: (
            -tile.low_snr_fraction,
            *tie(tile),
        ),
        "primary-beam-boundary": lambda tile: (
            tile.mean_primary_beam,
            *tie(tile),
        ),
    }
    selected: list[SelectedPublicTile] = []
    used: set[str] = set()
    for stratum in _SELECTION_STRATA:
        ranking = rankings[stratum]
        tile = next(
            item
            for item in sorted(admitted_tiles, key=ranking)
            if item.tile_id not in used
        )
        used.add(tile.tile_id)
        selected.append(SelectedPublicTile(stratum=stratum, tile=tile))
    return tuple(selected)


def _identity(value: object) -> str:
    """Represent a native catalogue identifier without numeric coercion."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict").strip()
    return str(value).strip()


def adapt_hydra_columns(
    *,
    finder_id: HydraFinder,
    depth: HydraDepth,
    columns: Mapping[str, npt.ArrayLike],
) -> tuple[HydraComponent, ...]:
    """Normalize one published Hydra table using the approved field map."""
    if finder_id not in _HYDRA_MAPPINGS:
        raise ValueError(f"unsupported Hydra finder: {finder_id}")
    if depth not in ("deep", "shallow"):
        raise ValueError(f"unsupported Hydra depth: {depth}")
    mapping = _HYDRA_MAPPINGS[finder_id]
    required = {
        mapping.native_id,
        mapping.island_id,
        mapping.component_id,
        mapping.ra,
        mapping.dec,
        mapping.integrated_flux,
        mapping.major_axis,
        mapping.minor_axis,
        mapping.position_angle,
    }
    if mapping.peak_flux is not None:
        required.add(mapping.peak_flux)
    missing = sorted(required.difference(columns))
    if missing:
        raise ValueError(f"missing Hydra columns: {', '.join(missing)}")

    arrays = {name: np.asarray(columns[name]) for name in required}
    lengths = {len(values) for values in arrays.values()}
    if len(lengths) != 1:
        raise ValueError("Hydra columns must have equal lengths")
    count = lengths.pop()

    def number(field: str, index: int, scale: float = 1.0) -> float:
        value = float(arrays[field][index]) * scale
        if not np.isfinite(value):
            raise ValueError(
                f"Hydra column {field} contains a non-finite value"
            )
        return value

    records: list[HydraComponent] = []
    for index in range(count):
        peak = (
            None
            if mapping.peak_flux is None
            else number(mapping.peak_flux, index, mapping.flux_scale)
        )
        records.append(
            HydraComponent(
                finder_id=finder_id,
                depth=depth,
                native_id=_identity(arrays[mapping.native_id][index]),
                native_island_id=_identity(arrays[mapping.island_id][index]),
                native_component_id=_identity(
                    arrays[mapping.component_id][index]
                ),
                ra_deg=number(mapping.ra, index),
                dec_deg=number(mapping.dec, index),
                peak_flux_jy_per_beam=peak,
                integrated_flux_jy=number(
                    mapping.integrated_flux,
                    index,
                    mapping.flux_scale,
                ),
                major_axis_arcsec=number(
                    mapping.major_axis,
                    index,
                    mapping.axis_scale,
                ),
                minor_axis_arcsec=number(
                    mapping.minor_axis,
                    index,
                    mapping.axis_scale,
                ),
                position_angle_deg=number(mapping.position_angle, index),
            )
        )
    return tuple(records)


def _spherical_offsets_arcsec(
    left: PublicCatalogueComponent,
    right: PublicCatalogueComponent,
) -> tuple[float, float, float]:
    """Return signed tangent offsets and exact great-circle separation."""
    left_ra = radians(left.right_ascension_degrees)
    right_ra = radians(right.right_ascension_degrees)
    left_dec = radians(left.declination_degrees)
    right_dec = radians(right.declination_degrees)
    delta_ra = atan2(sin(right_ra - left_ra), cos(right_ra - left_ra))
    delta_dec = right_dec - left_dec
    haversine = sin(delta_dec / 2.0) ** 2
    haversine += cos(left_dec) * cos(right_dec) * sin(delta_ra / 2.0) ** 2
    haversine = min(1.0, max(0.0, haversine))
    separation = 2.0 * atan2(sqrt(haversine), sqrt(1.0 - haversine))
    arcseconds_per_radian = 180.0 * 3600.0 / np.pi
    mean_dec = (left_dec + right_dec) / 2.0
    return (
        delta_ra * cos(mean_dec) * arcseconds_per_radian,
        delta_dec * arcseconds_per_radian,
        separation * arcseconds_per_radian,
    )


def _unique_components(
    components: Sequence[PublicCatalogueComponent],
    *,
    role: str,
) -> tuple[PublicCatalogueComponent, ...]:
    """Sort one side of a comparison and require stable unique IDs."""
    ordered = tuple(sorted(components, key=lambda item: item.identifier))
    identifiers = tuple(item.identifier for item in ordered)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"public {role} catalogue identifiers must be unique")
    return ordered


def _unit_sphere_coordinates(
    components: Sequence[PublicCatalogueComponent],
) -> FloatArray:
    """Project catalogue coordinates onto the three-dimensional unit sphere."""
    if not components:
        return np.empty((0, 3), dtype=np.float64)
    right_ascension = np.deg2rad(
        [item.right_ascension_degrees for item in components]
    )
    declination = np.deg2rad([item.declination_degrees for item in components])
    cos_declination = np.cos(declination)
    return np.column_stack(
        (
            cos_declination * np.cos(right_ascension),
            cos_declination * np.sin(right_ascension),
            np.sin(declination),
        )
    ).astype(np.float64, copy=False)


def associate_public_catalogues(  # noqa: PLR0915
    left_components: Sequence[PublicCatalogueComponent],
    right_components: Sequence[PublicCatalogueComponent],
    *,
    beam_fwhm_arcsec: float,
    maximum_separation_beams: float,
) -> PublicCatalogueAssociationReport:
    """Associate two catalogues with the approved deterministic objective.

    The assignment first maximizes cardinality. Among maximum-cardinality
    assignments it minimizes the summed absolute natural-log integrated-flux
    ratio rounded to nine decimal places, then summed angular separation,
    with sorted identifiers providing the final deterministic tie order.
    """
    if not isfinite(beam_fwhm_arcsec) or beam_fwhm_arcsec <= 0.0:
        raise ValueError("public comparison beam must be finite and positive")
    if (
        not isfinite(maximum_separation_beams)
        or maximum_separation_beams <= 0.0
    ):
        raise ValueError(
            "public comparison radius must be finite and positive"
        )
    left = _unique_components(left_components, role="left")
    right = _unique_components(right_components, role="right")
    eligible: dict[tuple[int, int], PublicCatalogueAssociation] = {}
    maximum_flux_units = 0
    maximum_separation_radians = radians(
        maximum_separation_beams * beam_fwhm_arcsec / 3600.0
    )
    chord_radius = 2.0 * sin(maximum_separation_radians / 2.0)
    right_tree = cKDTree(_unit_sphere_coordinates(right)) if right else None
    neighbours = (
        right_tree.query_ball_point(
            _unit_sphere_coordinates(left),
            chord_radius,
        )
        if right_tree is not None
        else [[] for _item in left]
    )
    for left_index, (left_item, right_indices) in enumerate(
        zip(left, neighbours, strict=True)
    ):
        for right_index in sorted(right_indices):
            right_item = right[right_index]
            offset_x, offset_y, separation_arcsec = _spherical_offsets_arcsec(
                left_item,
                right_item,
            )
            separation_beams = separation_arcsec / beam_fwhm_arcsec
            if separation_beams > maximum_separation_beams:
                continue
            flux_ratio = (
                right_item.integrated_flux_jy / left_item.integrated_flux_jy
            )
            flux_cost = abs(log(flux_ratio))
            flux_units = round(flux_cost * 10**_MATCH_FLUX_DECIMAL_PLACES)
            maximum_flux_units = max(maximum_flux_units, flux_units)
            eligible[(left_index, right_index)] = PublicCatalogueAssociation(
                left_identifier=left_item.identifier,
                right_identifier=right_item.identifier,
                separation_beams=separation_beams,
                offset_x_beams=offset_x / beam_fwhm_arcsec,
                offset_y_beams=offset_y / beam_fwhm_arcsec,
                integrated_flux_ratio=flux_ratio,
                absolute_log_flux_ratio=flux_cost,
            )

    left_count = len(left)
    right_count = len(right)
    primary_indices: set[tuple[int, int]] = set()
    if left_count:
        maximum_matches = min(left_count, right_count)
        separation_scale = maximum_matches * maximum_separation_beams + 1.0
        maximum_edge_cost = maximum_flux_units
        maximum_edge_cost += maximum_separation_beams / separation_scale + 1.0
        unmatched_penalty = maximum_matches * maximum_edge_cost + 1.0
        row_values: list[int] = []
        column_values: list[int] = []
        cost_values: list[float] = []
        for (left_index, right_index), association in eligible.items():
            flux_units = round(
                association.absolute_log_flux_ratio
                * 10**_MATCH_FLUX_DECIMAL_PLACES
            )
            cost = flux_units + association.separation_beams / separation_scale
            row_values.append(left_index)
            column_values.append(right_index)
            cost_values.append(max(float(np.nextafter(0.0, 1.0)), cost))
        for left_index in range(left_count):
            row_values.append(left_index)
            column_values.append(right_count + left_index)
            cost_values.append(unmatched_penalty)
        costs = coo_matrix(
            (cost_values, (row_values, column_values)),
            shape=(left_count, right_count + left_count),
            dtype=np.float64,
        ).tocsr()
        row_indices, column_indices = min_weight_full_bipartite_matching(costs)
        primary_indices = {
            (int(row), int(column))
            for row, column in zip(row_indices, column_indices, strict=True)
            if (int(row), int(column)) in eligible
        }

    primary = tuple(
        eligible[index]
        for index in sorted(
            primary_indices,
            key=lambda item: (
                eligible[item].left_identifier,
                eligible[item].right_identifier,
            ),
        )
    )
    eligible_records = tuple(
        sorted(
            eligible.values(),
            key=lambda item: (item.left_identifier, item.right_identifier),
        )
    )
    matched_left = {item.left_identifier for item in primary}
    matched_right = {item.right_identifier for item in primary}
    left_degrees = {
        item.identifier: sum(
            association.left_identifier == item.identifier
            for association in eligible_records
        )
        for item in left
    }
    right_degrees = {
        item.identifier: sum(
            association.right_identifier == item.identifier
            for association in eligible_records
        )
        for item in right
    }
    return PublicCatalogueAssociationReport(
        primary_associations=primary,
        eligible_associations=eligible_records,
        unmatched_left_identifiers=tuple(
            item.identifier
            for item in left
            if item.identifier not in matched_left
        ),
        unmatched_right_identifiers=tuple(
            item.identifier
            for item in right
            if item.identifier not in matched_right
        ),
        left_identifiers_with_multiple_edges=tuple(
            identifier
            for identifier, degree in left_degrees.items()
            if degree > 1
        ),
        right_identifiers_with_multiple_edges=tuple(
            identifier
            for identifier, degree in right_degrees.items()
            if degree > 1
        ),
    )


def associate_truth_with_guard(
    binding_truth_components: Sequence[PublicCatalogueComponent],
    guard_truth_components: Sequence[PublicCatalogueComponent],
    candidate_components: Sequence[PublicCatalogueComponent],
    *,
    beam_fwhm_arcsec: float,
    maximum_separation_beams: float,
) -> PublicCatalogueAssociationReport:
    """Associate binding truth before guard without changing the edge graph."""
    binding_identifiers = {
        item.identifier for item in binding_truth_components
    }
    guard_identifiers = {item.identifier for item in guard_truth_components}
    if binding_identifiers.intersection(guard_identifiers):
        raise ValueError(
            "binding and guard truth identifiers must be disjoint"
        )
    all_truth = (*binding_truth_components, *guard_truth_components)
    graph = associate_public_catalogues(
        all_truth,
        candidate_components,
        beam_fwhm_arcsec=beam_fwhm_arcsec,
        maximum_separation_beams=maximum_separation_beams,
    )
    binding = associate_public_catalogues(
        binding_truth_components,
        candidate_components,
        beam_fwhm_arcsec=beam_fwhm_arcsec,
        maximum_separation_beams=maximum_separation_beams,
    )
    candidate_by_identifier = {
        item.identifier: item for item in candidate_components
    }
    remaining_candidates = tuple(
        candidate_by_identifier[identifier]
        for identifier in binding.unmatched_right_identifiers
    )
    guard = associate_public_catalogues(
        guard_truth_components,
        remaining_candidates,
        beam_fwhm_arcsec=beam_fwhm_arcsec,
        maximum_separation_beams=maximum_separation_beams,
    )
    primary = tuple(
        sorted(
            (*binding.primary_associations, *guard.primary_associations),
            key=lambda item: (item.left_identifier, item.right_identifier),
        )
    )
    matched_left = {item.left_identifier for item in primary}
    matched_right = {item.right_identifier for item in primary}
    return PublicCatalogueAssociationReport(
        primary_associations=primary,
        eligible_associations=graph.eligible_associations,
        unmatched_left_identifiers=tuple(
            identifier
            for identifier in (
                *binding.unmatched_left_identifiers,
                *guard.unmatched_left_identifiers,
            )
            if identifier not in matched_left
        ),
        unmatched_right_identifiers=tuple(
            item.identifier
            for item in _unique_components(
                candidate_components,
                role="candidate",
            )
            if item.identifier not in matched_right
        ),
        left_identifiers_with_multiple_edges=(
            graph.left_identifiers_with_multiple_edges
        ),
        right_identifiers_with_multiple_edges=(
            graph.right_identifiers_with_multiple_edges
        ),
    )


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    """Return one deterministic linear percentile or explicit absence."""
    if not values:
        return None
    return float(
        np.percentile(np.asarray(values), percentile, method="linear")
    )


def summarize_truth_association(
    report: PublicCatalogueAssociationReport,
    truth_components: Sequence[PublicCatalogueComponent],
    candidate_components: Sequence[PublicCatalogueComponent],
    *,
    binding_truth_identifiers: frozenset[str] | None = None,
) -> dict[str, float | int | None]:
    """Calculate the complete binding SDC1 endpoint family."""
    binding_truth = (
        frozenset(item.identifier for item in truth_components)
        if binding_truth_identifiers is None
        else binding_truth_identifiers
    )
    known_truth = {item.identifier for item in truth_components}
    if not binding_truth.issubset(known_truth):
        raise ValueError(
            "binding truth identifiers must exist in the catalogue"
        )
    truth_count = len(binding_truth)
    candidate_count = len(candidate_components)
    binding_associations = tuple(
        item
        for item in report.primary_associations
        if item.left_identifier in binding_truth
    )
    matched_count = len(binding_associations)
    reliable_candidate_count = len(
        {item.right_identifier for item in report.primary_associations}
    )
    flux_errors = tuple(
        abs(item.integrated_flux_ratio - 1.0) for item in binding_associations
    )
    radial_offsets = tuple(
        item.separation_beams for item in binding_associations
    )
    x_offsets = tuple(item.offset_x_beams for item in binding_associations)
    y_offsets = tuple(item.offset_y_beams for item in binding_associations)
    return {
        "truth_count": truth_count,
        "candidate_count": candidate_count,
        "matched_count": matched_count,
        "completeness": matched_count / truth_count if truth_count else None,
        "reliability": (
            reliable_candidate_count / candidate_count
            if candidate_count
            else None
        ),
        "duplicate-fraction": (
            len(
                binding_truth.intersection(
                    report.left_identifiers_with_multiple_edges
                )
            )
            / truth_count
            if truth_count
            else None
        ),
        "merge-fraction": (
            len(report.right_identifiers_with_multiple_edges) / candidate_count
            if candidate_count
            else None
        ),
        "integrated-flux-median": _percentile(flux_errors, 50.0),
        "integrated-flux-p95": _percentile(flux_errors, 95.0),
        "absolute-mean-offset-x": (
            abs(float(np.mean(x_offsets))) if x_offsets else None
        ),
        "absolute-mean-offset-y": (
            abs(float(np.mean(y_offsets))) if y_offsets else None
        ),
        "position-p95": _percentile(radial_offsets, 95.0),
    }


def summarize_shape_diagnostics(
    report: PublicCatalogueAssociationReport,
    left_components: Sequence[PublicCatalogueComponent],
    right_components: Sequence[PublicCatalogueComponent],
    *,
    included_left_identifiers: frozenset[str] | None = None,
) -> dict[str, float | int | None]:
    """Summarize non-binding fitted-size and orientation diagnostics."""
    left = {item.identifier: item for item in left_components}
    right = {item.identifier: item for item in right_components}
    major_errors: list[float] = []
    minor_errors: list[float] = []
    position_angle_errors: list[float] = []
    for association in report.primary_associations:
        if (
            included_left_identifiers is not None
            and association.left_identifier not in included_left_identifiers
        ):
            continue
        left_item = left[association.left_identifier]
        right_item = right[association.right_identifier]
        if (
            left_item.major_axis_arcsec is not None
            and left_item.major_axis_arcsec > 0.0
            and right_item.major_axis_arcsec is not None
        ):
            major_errors.append(
                abs(
                    right_item.major_axis_arcsec / left_item.major_axis_arcsec
                    - 1.0
                )
            )
        if (
            left_item.minor_axis_arcsec is not None
            and left_item.minor_axis_arcsec > 0.0
            and right_item.minor_axis_arcsec is not None
        ):
            minor_errors.append(
                abs(
                    right_item.minor_axis_arcsec / left_item.minor_axis_arcsec
                    - 1.0
                )
            )
        if (
            left_item.position_angle_degrees is not None
            and right_item.position_angle_degrees is not None
            and left_item.major_axis_arcsec is not None
            and left_item.major_axis_arcsec > 0.0
            and left_item.minor_axis_arcsec is not None
            and (
                left_item.minor_axis_arcsec == 0.0
                or left_item.major_axis_arcsec / left_item.minor_axis_arcsec
                >= _POSITION_ANGLE_MINIMUM_AXIS_RATIO
            )
        ):
            difference = (
                right_item.position_angle_degrees
                - left_item.position_angle_degrees
            )
            position_angle_errors.append(
                abs((difference + 90.0) % 180.0 - 90.0)
            )
    return {
        "major-axis-count": len(major_errors),
        "major-axis-fractional-error-median": _percentile(major_errors, 50.0),
        "major-axis-fractional-error-p95": _percentile(major_errors, 95.0),
        "minor-axis-count": len(minor_errors),
        "minor-axis-fractional-error-median": _percentile(minor_errors, 50.0),
        "minor-axis-fractional-error-p95": _percentile(minor_errors, 95.0),
        "position-angle-count": len(position_angle_errors),
        "position-angle-absolute-error-median-deg": _percentile(
            position_angle_errors, 50.0
        ),
        "position-angle-absolute-error-p95-deg": _percentile(
            position_angle_errors, 95.0
        ),
    }


def _unmatched_audit(
    identifiers: Sequence[str],
    components: Sequence[PublicCatalogueComponent],
) -> list[dict[str, float | str | None]]:
    """Return at most ten stable highest-SNR unmatched records."""
    selected = set(identifiers)
    records = [item for item in components if item.identifier in selected]
    records.sort(
        key=lambda item: (
            -(
                item.peak_signal_to_noise
                if item.peak_signal_to_noise is not None
                else -1.0
            ),
            item.identifier,
        )
    )
    return [
        {
            "identifier": item.identifier,
            "peak_signal_to_noise": item.peak_signal_to_noise,
        }
        for item in records[:10]
    ]


def summarize_hydra_association(
    report: PublicCatalogueAssociationReport,
    left_components: Sequence[PublicCatalogueComponent],
    right_components: Sequence[PublicCatalogueComponent],
) -> dict[str, object]:
    """Calculate complete non-binding Hydra comparison diagnostics."""
    left_count = len(left_components)
    right_count = len(right_components)
    matched_count = len(report.primary_associations)
    smaller_count = min(left_count, right_count)
    separations = tuple(
        item.separation_beams for item in report.primary_associations
    )
    flux_ratios = tuple(
        item.integrated_flux_ratio for item in report.primary_associations
    )
    positive_outliers = sorted(
        (
            item
            for item in report.primary_associations
            if item.integrated_flux_ratio > 1.0
        ),
        key=lambda item: (
            -log(item.integrated_flux_ratio),
            item.left_identifier,
            item.right_identifier,
        ),
    )
    return {
        "binding": False,
        "left_count": left_count,
        "right_count": right_count,
        "matched_count": matched_count,
        "overlap": matched_count / smaller_count if smaller_count else None,
        "left_recovery_surrogate": (
            matched_count / left_count if left_count else None
        ),
        "right_recovery_surrogate": (
            matched_count / right_count if right_count else None
        ),
        "position-median-beams": _percentile(separations, 50.0),
        "position-p95-beams": _percentile(separations, 95.0),
        "integrated-flux-ratio-median": _percentile(flux_ratios, 50.0),
        "integrated-flux-ratio-p95": _percentile(flux_ratios, 95.0),
        "left_unmatched_highest_snr": _unmatched_audit(
            report.unmatched_left_identifiers,
            left_components,
        ),
        "right_unmatched_highest_snr": _unmatched_audit(
            report.unmatched_right_identifiers,
            right_components,
        ),
        "largest-positive-flux-ratio-outliers": [
            {
                "left_identifier": item.left_identifier,
                "right_identifier": item.right_identifier,
                "integrated_flux_ratio": item.integrated_flux_ratio,
            }
            for item in positive_outliers[:10]
        ],
    }
