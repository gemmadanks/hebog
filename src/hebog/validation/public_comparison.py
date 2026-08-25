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
from typing import Literal, TypeAlias

import numpy as np
import numpy.typing as npt
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
