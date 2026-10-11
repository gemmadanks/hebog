# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Plan and judge a run of pinned LSMTool's ``filter_sources`` on Hebog's mask.

Rapthor's filter step hands the island mask the adapter writes to LSMTool's
``filter_sources``, which clips the mask to the sector polygon in place,
keeps the true-sky components that fall on an island, groups them into one
patch per island, and gives the apparent-sky components of the same names
the same patches. :func:`plan_filter_inputs` writes a sector polygon and
WSClean-style true-sky and apparent-sky models whose outcome is known from
the mask, and :func:`filter_failures` compares what LSMTool did with it.

Components sit a quarter pixel from interior pixel centres, at least two
pixels inside an island or three pixels from every island, and two pixels
inside the polygon, so LSMTool's truncating pixel conversion and its
polygon border cannot change the outcome.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS
from scipy import ndimage

# LSMTool labels mask islands with 8-connectivity
# (``generate_binary_structure(2, 2)``).
_ISLAND_STRUCTURE = ndimage.generate_binary_structure(2, 2)
_INTERIOR_PIXELS = 2.0
_DECOY_CLEARANCE_PIXELS = 3.0
_POLYGON_CLEARANCE_PIXELS = 2.0
_QUARTER_PIXEL = 0.25
_MICROSECONDS = 1_000_000
# A right ascension of 15 degrees is one hour, 3,600 seconds of time.
_SECONDS_PER_DEGREE_OF_RIGHT_ASCENSION = 3600.0 / 15.0
# Decoys are drawn from a grid of about this many points, so a sector-sized
# mask is never searched pixel by pixel.
_DECOY_GRID_POINTS = 10_000
_FLUX_RELATIVE_TOLERANCE = 1e-5
_SKY_MODEL_FORMAT = (
    "FORMAT = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI, "
    "ReferenceFrequency='{frequency}', MajorAxis, MinorAxis, Orientation\n"
)


@dataclass(frozen=True, slots=True)
class PlannedComponent:
    """One sky-model component and what ``filter_sources`` should do to it.

    ``island`` is the 8-connected island of the clipped mask the component
    falls on, 0 for none; the component is kept exactly when it is not 0.
    ``clipped`` marks a component on an island the polygon clips away.
    """

    name: str
    x: float
    y: float
    true_flux_jy: float
    apparent_flux_jy: float
    island: int
    clipped: bool


@dataclass(frozen=True, slots=True)
class FilterPlan:
    """The inputs written for ``filter_sources`` and its expected outcome."""

    vertices_path: Path
    true_sky_model_path: Path
    apparent_sky_model_path: Path
    polygon_pixels: tuple[tuple[float, float], ...]
    components: tuple[PlannedComponent, ...]

    def kept(self) -> frozenset[str]:
        """Return the names of the components ``filter_sources`` keeps."""
        return frozenset(
            component.name for component in self.components if component.island
        )

    def groups(self) -> frozenset[frozenset[str]]:
        """Return the kept names grouped by the island they fall on."""
        islands: dict[int, set[str]] = {}
        for component in self.components:
            if component.island:
                islands.setdefault(component.island, set()).add(component.name)
        return frozenset(frozenset(names) for names in islands.values())


@dataclass(frozen=True, slots=True)
class FilterOutcome:
    """What ``filter_sources`` wrote, as the container worker reported it.

    Each mapping is keyed by component name: the patch of each true-sky and
    apparent-sky survivor, and each apparent-sky survivor's flux in Jy.
    """

    true_patches: Mapping[str, str]
    apparent_patches: Mapping[str, str]
    apparent_fluxes_jy: Mapping[str, float]

    @classmethod
    def read(cls, path: Path) -> FilterOutcome:
        """Read the worker's JSON summary."""
        document = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            true_patches={
                name: patch for name, patch, _ in document["true_sky"]
            },
            apparent_patches={
                name: patch for name, patch, _ in document["apparent_sky"]
            },
            apparent_fluxes_jy={
                name: float(flux) for name, _, flux in document["apparent_sky"]
            },
        )

    def groups(self) -> frozenset[frozenset[str]]:
        """Return the true-sky survivors grouped by patch."""
        patches: dict[str, set[str]] = {}
        for name, patch in self.true_patches.items():
            patches.setdefault(patch, set()).add(name)
        return frozenset(frozenset(names) for names in patches.values())


def _nonzero_plane(data: Any) -> npt.NDArray[np.bool_]:
    """Return where a FITS mask's image plane is not zero."""
    return np.asarray(data[(0,) * (data.ndim - 2)] != 0, dtype=np.bool_)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _inset_rectangle(
    shape_yx: tuple[int, int], margin_fraction: float
) -> tuple[tuple[float, float], ...]:
    """Return a closed rectangle, in 0-based pixels, inset by a margin."""
    height, width = shape_yx
    left, right = (
        margin_fraction * (width - 1),
        (1 - margin_fraction) * (width - 1),
    )
    bottom, top = (
        margin_fraction * (height - 1),
        (1 - margin_fraction) * (height - 1),
    )
    return (
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
        (left, bottom),
    )


def _inside(
    polygon: tuple[tuple[float, float], ...],
    x: float,
    y: float,
    clearance: float,
) -> bool:
    """Return whether a pixel lies inside the rectangle by ``clearance``."""
    xs = [corner[0] for corner in polygon]
    ys = [corner[1] for corner in polygon]
    return (
        min(xs) + clearance <= x <= max(xs) - clearance
        and min(ys) + clearance <= y <= max(ys) - clearance
    )


def _rectangle(
    polygon: tuple[tuple[float, float], ...],
) -> tuple[slice, slice]:
    """Return the slices of the pixels whose centres the rectangle holds."""
    xs = [corner[0] for corner in polygon]
    ys = [corner[1] for corner in polygon]
    return (
        slice(max(0, math.ceil(min(ys))), max(0, math.floor(max(ys)) + 1)),
        slice(max(0, math.ceil(min(xs))), max(0, math.floor(max(xs)) + 1)),
    )


def _clipped(
    mask: npt.NDArray[np.bool_], polygon: tuple[tuple[float, float], ...]
) -> npt.NDArray[np.bool_]:
    """Return the mask with every pixel outside the rectangle cleared."""
    clipped = np.zeros_like(mask)
    inside = _rectangle(polygon)
    clipped[inside] = mask[inside]
    return clipped


def _islands(
    mask: npt.NDArray[np.bool_],
) -> tuple[npt.NDArray[np.int32], int]:
    """Label a mask's 8-connected islands from 1, and count them."""
    labels, count = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=_ISLAND_STRUCTURE),
    )
    return labels, count


def _distance_to_edge(
    region: npt.NDArray[np.bool_],
) -> npt.NDArray[np.float64]:
    """Return each region pixel's distance to the nearest pixel outside it."""
    return np.asarray(ndimage.distance_transform_edt(region), dtype=np.float64)


def _island_sites(
    labels: npt.NDArray[np.int32], label: int, box: tuple[slice, slice]
) -> list[tuple[str, int, int]]:
    """Return an island's deepest pixel, and one three pixels from it.

    The depth is measured within the island's bounding box, padded so the
    box edge counts as outside the island.
    """
    depth = _distance_to_edge(np.pad(labels[box] == label, 1))[1:-1, 1:-1]
    candidates = np.argwhere(depth >= _INTERIOR_PIXELS)
    if not len(candidates):
        return []
    candidates += np.array([box[0].start, box[1].start])
    depths = depth[depth >= _INTERIOR_PIXELS]
    first = candidates[int(np.argmax(depths))]
    sites = [(f"island{label}a", int(first[1]), int(first[0]))]
    apart = np.hypot(*(candidates - first).T) >= _DECOY_CLEARANCE_PIXELS
    if apart.any():
        second = candidates[apart][int(np.argmax(depths[apart]))]
        sites.append((f"island{label}b", int(second[1]), int(second[0])))
    return sites


def _decoy_sites(
    mask: npt.NDArray[np.bool_], decoy_count: int
) -> list[tuple[str, int, int]]:
    """Return background points with no island pixel within three pixels.

    They are spread evenly over a grid of about 10,000 points.
    """
    height, width = mask.shape
    radius = int(_DECOY_CLEARANCE_PIXELS)
    step = max(1, math.isqrt(mask.size // _DECOY_GRID_POINTS))
    clear = [
        (x, y)
        for y in range(radius, height - radius, step)
        for x in range(radius, width - radius, step)
        if not mask[
            y - radius : y + radius + 1, x - radius : x + radius + 1
        ].any()
    ]
    if not decoy_count or not clear:
        return []
    chosen = np.unique(np.linspace(0, len(clear) - 1, decoy_count).astype(int))
    return [
        (f"decoy{index}", *clear[int(row)]) for index, row in enumerate(chosen)
    ]


def _component_sites(
    mask: npt.NDArray[np.bool_],
    polygon: tuple[tuple[float, float], ...],
    *,
    island_limit: int,
    decoy_count: int,
) -> list[tuple[str, int, int]]:
    """Choose interior island pixels and clear background pixels.

    Up to ``island_limit`` islands, spread evenly through their raster
    order, each get their deepest pixel, and a second one at least three
    pixels away when they have one, so grouping joins two components.
    Decoys sit at least three pixels from every island, both inside and
    outside the polygon.
    """
    labels, count = _islands(mask)
    boxes = ndimage.find_objects(labels)
    chosen = (
        np.unique(np.linspace(1, count, min(count, island_limit)).astype(int))
        if count and island_limit
        else np.empty(0, dtype=int)
    )
    sites = [
        site
        for label in chosen
        for site in _island_sites(labels, int(label), boxes[int(label) - 1])
    ]
    sites.extend(_decoy_sites(mask, decoy_count))
    return [
        site
        for site in sites
        if _inside(polygon, site[1], site[2], _POLYGON_CLEARANCE_PIXELS)
        or not _inside(polygon, site[1], site[2], -_POLYGON_CLEARANCE_PIXELS)
    ]


def _sexagesimal(seconds: float) -> tuple[int, int, int, int]:
    """Split seconds into units, minutes, seconds and microseconds.

    ``seconds`` is non-negative. It is rounded to the microsecond once, as an
    integer, so a rounded-up second carries into the minute and the minute
    into the unit.
    """
    whole, microseconds = divmod(round(seconds * _MICROSECONDS), _MICROSECONDS)
    minutes, second = divmod(whole, 60)
    unit, minute = divmod(minutes, 60)
    return unit, minute, second, microseconds


def _right_ascension_text(ra_deg: float) -> str:
    """Return a right ascension as makesourcedb's ``hh:mm:ss.ssssss``.

    The text is formatted with integer arithmetic rather than Astropy's
    vectorised ``Angle.to_string``, which raised a spurious floating-point
    ``invalid`` warning on Linux x86-64 under Python 3.14.
    """
    hours, minutes, seconds, microseconds = _sexagesimal(
        (ra_deg % 360.0) * _SECONDS_PER_DEGREE_OF_RIGHT_ASCENSION
    )
    return f"{hours % 24:02d}:{minutes:02d}:{seconds:02d}.{microseconds:06d}"


def _declination_text(dec_deg: float) -> str:
    """Return a declination as makesourcedb's ``+dd.mm.ss.ssssss``."""
    degrees, arcminutes, arcseconds, microseconds = _sexagesimal(
        abs(dec_deg) * 3600.0
    )
    sign = "-" if dec_deg < 0 else "+"
    return (
        f"{sign}{degrees:02d}.{arcminutes:02d}.{arcseconds:02d}."
        f"{microseconds:06d}"
    )


def _sky_model_line(
    name: str, ra_deg: float, dec_deg: float, flux_jy: float, frequency: float
) -> str:
    ra = _right_ascension_text(ra_deg)
    dec = _declination_text(dec_deg)
    return (
        f"{name},POINT,{ra},{dec},{flux_jy!r},[-0.7],false,{frequency!r},,,\n"
    )


def plan_filter_inputs(  # noqa: PLR0913
    mask_path: Path,
    true_sky_image_path: Path,
    flat_noise_image_path: Path,
    directory: Path,
    *,
    margin_fraction: float = 0.1,
    island_limit: int = 2_000,
    decoy_count: int = 20,
) -> FilterPlan:
    """Write a sector polygon and sky models whose outcome the mask decides.

    The polygon is the image inset by ``margin_fraction`` of each side, so
    islands in the margin are clipped away. At most ``island_limit`` islands
    carry components, which keeps LSMTool's per-component mask lookups
    bounded on a sector-sized mask. Each true-sky component's
    apparent flux is its true flux times the primary-beam attenuation at its
    pixel, the flat-noise image over the true-sky image.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with fits.open(mask_path, memmap=True) as hdus:
        header = hdus[0].header
        mask = _nonzero_plane(hdus[0].data)
    celestial = WCS(header).celestial
    frequency = float(header["CRVAL4"])
    polygon = _inset_rectangle(mask.shape, margin_fraction)
    labels, _ = _islands(_clipped(mask, polygon))
    with (
        fits.open(true_sky_image_path, memmap=True) as true_sky,
        fits.open(flat_noise_image_path, memmap=True) as flat_noise,
    ):
        true_plane = true_sky[0].data[(0,) * (true_sky[0].data.ndim - 2)]
        flat_plane = flat_noise[0].data[(0,) * (flat_noise[0].data.ndim - 2)]
        components = []
        for index, (name, x, y) in enumerate(
            _component_sites(
                mask,
                polygon,
                island_limit=island_limit,
                decoy_count=decoy_count,
            )
        ):
            attenuation = float(flat_plane[y, x]) / float(true_plane[y, x])
            if not (np.isfinite(attenuation) and attenuation > 0):
                attenuation = 1.0
            true_flux = 1.0 + 0.01 * index
            components.append(
                PlannedComponent(
                    name=name,
                    x=x + _QUARTER_PIXEL,
                    y=y + _QUARTER_PIXEL,
                    true_flux_jy=true_flux,
                    apparent_flux_jy=true_flux * attenuation,
                    island=int(labels[y, x]),
                    clipped=bool(mask[y, x]) and not labels[y, x],
                )
            )
    vertices = np.asarray(
        celestial.wcs_pix2world(np.asarray(polygon, dtype=np.float64), 0),
        dtype=np.float64,
    )
    plan = FilterPlan(
        vertices_path=directory / "vertices.npy",
        true_sky_model_path=directory / "true-sky-sources.txt",
        apparent_sky_model_path=directory / "apparent-sky-sources.txt",
        polygon_pixels=polygon,
        components=tuple(components),
    )
    np.save(plan.vertices_path, vertices)
    positions = celestial.wcs_pix2world(
        np.asarray([[c.x, c.y] for c in components], dtype=np.float64), 0
    )
    for path, apparent in (
        (plan.true_sky_model_path, False),
        (plan.apparent_sky_model_path, True),
    ):
        path.write_text(
            _SKY_MODEL_FORMAT.format(frequency=frequency)
            + "".join(
                _sky_model_line(
                    component.name,
                    float(ra),
                    float(dec),
                    component.apparent_flux_jy
                    if apparent
                    else component.true_flux_jy,
                    frequency,
                )
                for component, (ra, dec) in zip(
                    components, positions, strict=True
                )
            ),
            encoding="utf-8",
        )
    return plan


def filter_failures(
    plan: FilterPlan,
    outcomes: Mapping[str, FilterOutcome],
    clipped_masks: Mapping[str, Path],
) -> list[str]:
    """Return each way ``filter_sources`` departed from the plan.

    ``outcomes`` and ``clipped_masks`` are keyed by the executor whose
    products LSMTool filtered. Every run must keep exactly the components
    on islands, group them by island, give the apparent-sky survivors the
    same names, patches and their own fluxes, and leave no mask pixel
    outside the polygon; and every executor's run must agree.
    """
    failures: list[str] = []
    planned_apparent = {
        component.name: component.apparent_flux_jy
        for component in plan.components
    }
    for executor, outcome in outcomes.items():
        kept = frozenset(outcome.true_patches)
        if kept != plan.kept():
            failures.append(
                f"{executor}: kept {sorted(kept)}, expected "
                f"{sorted(plan.kept())}"
            )
        if outcome.groups() != plan.groups():
            failures.append(f"{executor}: patches do not group by island")
        if dict(outcome.apparent_patches) != dict(outcome.true_patches):
            failures.append(
                f"{executor}: apparent-sky names or patches differ"
            )
        if any(
            not np.isclose(
                flux,
                planned_apparent.get(name, np.nan),
                rtol=_FLUX_RELATIVE_TOLERANCE,
                atol=0.0,
            )
            for name, flux in outcome.apparent_fluxes_jy.items()
        ):
            failures.append(f"{executor}: apparent-sky fluxes changed")
    for executor, path in clipped_masks.items():
        with fits.open(path, memmap=True) as hdus:
            clipped = _nonzero_plane(hdus[0].data)
        inside = _rectangle(_inset_by(plan.polygon_pixels, -1.0))
        outside = int(np.count_nonzero(clipped)) - int(
            np.count_nonzero(clipped[inside])
        )
        if outside:
            failures.append(
                f"{executor}: {outside} mask pixels lie outside the polygon"
            )
    if len({_canonical(outcome) for outcome in outcomes.values()}) > 1:
        failures.append("the executors' filtered sky models differ")
    if len({_file_sha256(path) for path in clipped_masks.values()}) > 1:
        failures.append("the executors' clipped masks differ")
    return failures


def _inset_by(
    polygon: tuple[tuple[float, float], ...], pixels: float
) -> tuple[tuple[float, float], ...]:
    """Return the rectangle grown (negative) or shrunk by ``pixels``."""
    xs = [corner[0] for corner in polygon]
    ys = [corner[1] for corner in polygon]
    left, right = min(xs) + pixels, max(xs) - pixels
    bottom, top = min(ys) + pixels, max(ys) - pixels
    return (
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
        (left, bottom),
    )


def _canonical(outcome: FilterOutcome) -> str:
    return json.dumps(
        [
            sorted(outcome.true_patches.items()),
            sorted(outcome.apparent_patches.items()),
            sorted(outcome.apparent_fluxes_jy.items()),
        ]
    )
