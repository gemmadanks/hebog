# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure whether Rapthor keeps the same sky model with Hebog as with PyBDSF.

Rapthor's filter step keeps a sky-model component when LSMTool's
``filter_sources`` finds the finder's island mask set at the component's
pixel, read as ``mask[int(y), int(x)]`` from zero-based pixel coordinates
with negative positions rejected, and groups the kept components into one
patch per 8-connected island of the mask. Plan task 21 compares those
decisions under each Hebog configuration with pinned PyBDSF ``master``'s.

WSClean's component lists are not available for the images the check uses,
so a fitted-Gaussian population stands in for them: every distinct pixel
that holds the centre of a Gaussian the reference or any Hebog
configuration fitted, one set for every lane, so the lanes are compared on
the same components. Each component is tagged with the safety strata of
:func:`component_strata`; :func:`gate_outcome` passes a lane only when its
agreement reaches the threshold overall and in every stratum, and
:func:`rapthor_profile` chooses ``compact`` only for a passing lane.

Two diagnostic populations are reported beside it: injected truth, and
:func:`emission_pixels`, every pixel WSClean's auto-threshold would clean
inside its auto-mask. :func:`compare_catalogue_cuts` measures the catalogue
cuts Rapthor's astrometry and photometry checks apply to the source rows.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import astuple, dataclass, replace
from pathlib import Path
from typing import Literal, Self, cast

import numpy as np
import numpy.typing as npt
from astropy import units
from astropy.coordinates import SkyCoord, match_coordinates_sky
from astropy.stats import sigma_clipped_stats
from astropy.table import Table
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import ndimage
from scipy.spatial import cKDTree

from hebog.adapters.rapthor_catalogue import read_rapthor_catalogue_fits
from hebog.data_models import SourceCatalogue
from hebog.validation.quick_check import ImageCase

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IndexArray = npt.NDArray[np.intp]

ALL_COMPONENTS = "all"
"""The stratum holding every component of the population."""
SAFETY_STRATA = (
    "bright",
    "extended",
    "edge",
    "masked",
    "crowded",
    "sparse",
    "true-sky",
    "apparent",
)
"""The strata in which a lane must reach the agreement threshold."""

RAPTHOR_MAXIMUM_SIZE_DEGREES = 10.0 / 3600.0
"""Rapthor's astrometry and photometry checks keep ``DC_Maj`` below 10″."""
RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES = 2.0 / 3600.0
"""Rapthor's astrometry check keeps ``E_RA`` and ``E_DEC`` below 2″."""

# LSMTool labels mask islands with 8-connectivity
# (``generate_binary_structure(2, 2)``) when it groups components.
_EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)
# The noise of the emission population: sigma clipping at 3 sigma until it
# converges, as for a robust image RMS.
_NOISE_CLIP_SIGMA = 3.0
_NOISE_CLIP_ITERATIONS = 10


def _islands(mask: npt.ArrayLike) -> npt.NDArray[np.int32]:
    """Label a mask's 8-connected islands from 1; 0 is off the mask."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(
            np.asarray(mask, dtype=np.bool_), structure=_EIGHT_CONNECTED
        ),
    )
    return labels


def _pooled[Counts](first: Counts, second: Counts) -> Counts:
    """Return a counts record holding the field-wise sums of two."""
    return type(first)(
        *(
            left + right
            for left, right in zip(
                astuple(first),  # pyright: ignore[reportArgumentType]
                astuple(second),  # pyright: ignore[reportArgumentType]
                strict=True,
            )
        )
    )


@dataclass(frozen=True, slots=True)
class ComponentPixels:
    """Distinct image pixels holding at least one component, in raster order.

    ``rows`` and ``columns`` are zero-based ``(y, x)`` indices of equal
    length. Components that share a pixel share every mask decision, so
    each pixel counts once.
    """

    rows: IndexArray
    columns: IndexArray

    @classmethod
    def at_positions(
        cls,
        x_pixels: npt.ArrayLike,
        y_pixels: npt.ArrayLike,
        shape_yx: tuple[int, int],
    ) -> ComponentPixels:
        """Return the pixels LSMTool reads for zero-based positions.

        LSMTool truncates each coordinate with ``int`` and rejects negative
        positions; positions beyond the image are rejected too.
        """
        x = np.asarray(x_pixels, dtype=np.float64).ravel()
        y = np.asarray(y_pixels, dtype=np.float64).ravel()
        valid = np.isfinite(x) & np.isfinite(y) & (x >= 0) & (y >= 0)
        rows = np.trunc(y[valid]).astype(np.intp)
        columns = np.trunc(x[valid]).astype(np.intp)
        inside = (rows < shape_yx[0]) & (columns < shape_yx[1])
        distinct = np.unique(
            np.ravel_multi_index((rows[inside], columns[inside]), shape_yx)
        )
        unique_rows, unique_columns = np.unravel_index(distinct, shape_yx)
        return cls(
            rows=unique_rows.astype(np.intp),
            columns=unique_columns.astype(np.intp),
        )

    def __len__(self) -> int:
        """Return the number of distinct component pixels."""
        return int(self.rows.size)

    def kept_by(self, mask: npt.ArrayLike) -> BoolArray:
        """Return whether ``filter_sources`` keeps each component."""
        return np.asarray(mask, dtype=np.bool_)[self.rows, self.columns]

    def islands_in(self, mask: npt.ArrayLike) -> IndexArray:
        """Return each component's 8-connected mask island, 0 for none."""
        return _islands(mask)[self.rows, self.columns].astype(np.intp)


@dataclass(frozen=True, slots=True)
class StratumRules:
    """Where a component counts as bright, extended, edge, masked or crowded.

    Distances are in restoring-beam FWHM (the geometric mean of the axes,
    in pixels) and island areas in beam areas.
    """

    bright_snr: float
    edge_beams: float
    masked_beams: float
    crowded_beams: float
    extended_beam_areas: float


def component_strata(  # noqa: PLR0913
    pixels: ComponentPixels,
    *,
    image: FloatArray,
    reference_rms: FloatArray,
    union_mask: BoolArray,
    beam_fwhm_pixels: float,
    beam_area_pixels: float,
    rules: StratumRules,
    image_kind: Literal["true-sky", "apparent"] | None,
) -> dict[str, BoolArray]:
    """Tag each component with the safety strata it belongs to.

    A component is *bright* where the image is at least ``bright_snr``
    times the reference RMS; *edge* within ``edge_beams`` of the image
    border; *masked* within ``masked_beams`` of a blanked pixel; *crowded*
    with another component within ``crowded_beams``, and *sparse*
    otherwise; and *extended* on an 8-connected island of ``union_mask``
    (every finder's mask together) larger than ``extended_beam_areas``.
    ``image_kind`` places every component of a primary-beam-corrected or
    apparent image in that stratum.
    """
    rows, columns = pixels.rows, pixels.columns
    count = len(pixels)
    values = image[rows, columns]
    rms = reference_rms[rows, columns]
    measurable = np.isfinite(values) & np.isfinite(rms) & (rms > 0)
    bright = np.zeros(count, dtype=np.bool_)
    bright[measurable] = (
        values[measurable] >= rules.bright_snr * rms[measurable]
    )
    height, width = image.shape
    border_distance = np.minimum.reduce(
        [rows, columns, height - 1 - rows, width - 1 - columns]
    )
    blank = ~np.isfinite(image)
    masked = np.zeros(count, dtype=np.bool_)
    if blank.any():
        # The distance from each valid pixel to the nearest blank one; a
        # blank pixel is at distance 0.
        blank_distance = ndimage.distance_transform_edt(~blank)
        masked = (
            np.asarray(blank_distance)[rows, columns]
            <= rules.masked_beams * beam_fwhm_pixels
        )
    crowded = np.zeros(count, dtype=np.bool_)
    if count:
        neighbours = cKDTree(
            np.column_stack([rows, columns])
        ).query_ball_point(
            np.column_stack([rows, columns]),
            r=rules.crowded_beams * beam_fwhm_pixels,
            return_length=True,
        )
        # Every component is its own neighbour at distance zero.
        crowded = np.asarray(neighbours) > 1
    labels = _islands(union_mask)
    island_areas = np.bincount(labels.ravel())
    islands = labels[rows, columns]
    extended = (islands > 0) & (
        island_areas[islands] > rules.extended_beam_areas * beam_area_pixels
    )
    return {
        "bright": bright,
        "extended": extended,
        "edge": border_distance <= rules.edge_beams * beam_fwhm_pixels,
        "masked": masked,
        "crowded": crowded,
        "sparse": ~crowded,
        "true-sky": np.full(count, image_kind == "true-sky"),
        "apparent": np.full(count, image_kind == "apparent"),
    }


@dataclass(frozen=True, slots=True)
class DecisionCounts:
    """How a candidate's mask decisions compare with the reference's.

    ``grouped_alike`` counts the components both keep whose patch holds
    the same kept components under both masks.
    """

    components: int = 0
    both_kept: int = 0
    candidate_only: int = 0
    reference_only: int = 0
    grouped_alike: int = 0

    def __add__(self, other: DecisionCounts) -> DecisionCounts:
        """Pool the counts of two populations."""
        return _pooled(self, other)

    @property
    def agreement(self) -> float | None:
        """Return the fraction of components both keep or both reject."""
        if not self.components:
            return None
        disagreeing = self.candidate_only + self.reference_only
        return 1.0 - disagreeing / self.components

    @property
    def grouping_agreement(self) -> float | None:
        """Return the fraction of components both keep that group alike."""
        if not self.both_kept:
            return None
        return self.grouped_alike / self.both_kept


def compare_decisions(
    candidate_mask: npt.ArrayLike,
    reference_mask: npt.ArrayLike,
    pixels: ComponentPixels,
    strata: Mapping[str, BoolArray],
) -> dict[str, DecisionCounts]:
    """Count agreement over every component and within each stratum."""
    candidate = pixels.kept_by(candidate_mask)
    reference = pixels.kept_by(reference_mask)
    both = candidate & reference
    alike = np.zeros(len(pixels), dtype=np.bool_)
    alike[both] = _grouped_alike(
        pixels.islands_in(candidate_mask)[both],
        pixels.islands_in(reference_mask)[both],
    )
    selections = {ALL_COMPONENTS: np.ones(len(pixels), dtype=np.bool_)}
    return {
        name: DecisionCounts(
            components=int(selection.sum()),
            both_kept=int((selection & both).sum()),
            candidate_only=int((selection & candidate & ~reference).sum()),
            reference_only=int((selection & reference & ~candidate).sum()),
            grouped_alike=int((selection & alike).sum()),
        )
        for name, selection in (selections | dict(strata)).items()
    }


def _grouped_alike(
    candidate_islands: IndexArray, reference_islands: IndexArray
) -> BoolArray:
    """Return where a component's two patches hold the same components.

    The patch-mates a component has under both masks are the components
    sharing both of its islands, so its two patches are equal exactly when
    each holds as many components as the pair of islands does.
    """
    _, candidate_index, candidate_sizes = np.unique(
        candidate_islands, return_inverse=True, return_counts=True
    )
    _, reference_index, reference_sizes = np.unique(
        reference_islands, return_inverse=True, return_counts=True
    )
    _, pair_index, pair_sizes = np.unique(
        np.column_stack([candidate_islands, reference_islands]),
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    pair = pair_sizes[pair_index.ravel()]
    return (candidate_sizes[candidate_index] == pair) & (
        reference_sizes[reference_index] == pair
    )


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """Whether a lane reached the agreement threshold everywhere.

    A lane with an empty stratum and no failing one is ``incomplete``: an
    unmeasured stratum cannot pass.
    """

    status: Literal["passed", "failed", "incomplete"]
    failing_strata: tuple[str, ...]
    empty_strata: tuple[str, ...]


def gate_outcome(
    counts: Mapping[str, DecisionCounts], threshold: float
) -> GateOutcome:
    """Apply the agreement threshold overall and in every stratum."""
    failing = tuple(
        name
        for name, measured in counts.items()
        if measured.agreement is not None and measured.agreement < threshold
    )
    empty = tuple(
        name for name, measured in counts.items() if not measured.components
    )
    return GateOutcome(
        status="failed" if failing else "incomplete" if empty else "passed",
        failing_strata=failing,
        empty_strata=empty,
    )


def rapthor_profile(
    compact: GateOutcome,
) -> Literal["compact", "continuum"]:
    """Apply plan task 21's rule: ``compact`` only when its lane passes."""
    return "compact" if compact.status == "passed" else "continuum"


@dataclass(frozen=True, slots=True)
class WeightedAgreement:
    """Flux on which two masks agree, out of the population's flux."""

    agreeing: float = 0.0
    total: float = 0.0

    def __add__(self, other: WeightedAgreement) -> WeightedAgreement:
        """Pool two populations measured in the same units."""
        return _pooled(self, other)

    @property
    def agreement(self) -> float | None:
        """Return the agreeing fraction of the flux."""
        return self.agreeing / self.total if self.total > 0 else None


def emission_pixels(
    image: FloatArray, *, floor_sigma: float, seed_sigma: float
) -> tuple[ComponentPixels, FloatArray]:
    """Return the pixels WSClean would clean and their excess brightness.

    Rapthor runs WSClean with ``-auto-threshold 1`` inside an auto-mask
    seeded at 3 to 5 sigma, so clean components lie on emission at least
    ``floor_sigma`` above the median that is 8-connected to a pixel at
    least ``seed_sigma`` above it. Sigma is the 3-sigma-clipped standard
    deviation of the valid pixels, independent of either finder.
    """
    valid = np.isfinite(image)
    if valid.any():
        _, median, sigma = sigma_clipped_stats(
            image[valid],
            sigma=_NOISE_CLIP_SIGMA,
            maxiters=_NOISE_CLIP_ITERATIONS,
        )
    else:
        median = sigma = 0.0
    if not sigma > 0:
        empty = np.zeros(0, dtype=np.intp)
        return ComponentPixels(rows=empty, columns=empty), np.zeros(0)
    excess = np.where(valid, image - median, -np.inf)
    labels = _islands(excess >= floor_sigma * sigma)
    seeded = np.unique(labels[excess >= seed_sigma * sigma])
    rows, columns = np.nonzero(np.isin(labels, seeded[seeded > 0]))
    return (
        ComponentPixels(
            rows=rows.astype(np.intp), columns=columns.astype(np.intp)
        ),
        excess[rows, columns],
    )


def weighted_agreement(
    candidate_mask: npt.ArrayLike,
    reference_mask: npt.ArrayLike,
    pixels: ComponentPixels,
    weights: FloatArray,
) -> WeightedAgreement:
    """Return the weight of the components both masks decide alike."""
    alike = pixels.kept_by(candidate_mask) == pixels.kept_by(reference_mask)
    return WeightedAgreement(
        agreeing=float(weights[alike].sum()), total=float(weights.sum())
    )


@dataclass(frozen=True, slots=True)
class CutCatalogue:
    """The source columns Rapthor's catalogue cuts read, in degrees.

    ``several_components`` marks sources published from more than one
    Gaussian; ``fitted_major_degrees`` is the fitted, not deconvolved,
    major FWHM, NaN where none was published.
    """

    right_ascension_degrees: FloatArray
    declination_degrees: FloatArray
    deconvolved_major_degrees: FloatArray
    right_ascension_error_degrees: FloatArray
    declination_error_degrees: FloatArray
    several_components: BoolArray
    fitted_major_degrees: FloatArray

    def astrometry_kept(self) -> BoolArray:
        """Return which sources Rapthor's astrometry check keeps.

        A NaN size or error fails its comparison, so the row is dropped.
        """
        return (
            self.size_kept()
            & (
                self.right_ascension_error_degrees
                < RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES
            )
            & (
                self.declination_error_degrees
                < RAPTHOR_MAXIMUM_POSITION_ERROR_DEGREES
            )
        )

    def size_kept(self) -> BoolArray:
        """Return which sources the photometry check's size cut keeps."""
        return self.deconvolved_major_degrees < RAPTHOR_MAXIMUM_SIZE_DEGREES

    def unresolved_wide_fits(self) -> BoolArray:
        """Return sources published unresolved whose fit is 10″ or wider."""
        return (self.deconvolved_major_degrees == 0) & (
            self.fitted_major_degrees >= RAPTHOR_MAXIMUM_SIZE_DEGREES
        )

    def __len__(self) -> int:
        """Return the number of sources."""
        return int(self.right_ascension_degrees.size)

    def coordinates(self) -> SkyCoord:
        """Return the source positions."""
        return SkyCoord(
            self.right_ascension_degrees * units.deg,
            self.declination_degrees * units.deg,
        )


@dataclass(frozen=True, slots=True)
class CatalogueCutCounts:
    """How a candidate's astrometry-cut decisions compare with the reference's.

    Sources are paired as mutual nearest neighbours within the match
    radius. ``dropped_with_several_components`` counts the pairs the
    reference keeps and the candidate drops where the candidate's source
    has several components; ``kept_as_unresolved_wide_fit`` counts the
    pairs the reference drops and the candidate keeps where the candidate
    publishes an unresolved source from a fit 10″ or wider.
    """

    sources: int = 0
    astrometry_kept: int = 0
    size_kept: int = 0
    several_component_sources: int = 0
    unresolved_wide_fits: int = 0
    matched: int = 0
    matched_alike: int = 0
    reference_kept_candidate_dropped: int = 0
    dropped_with_several_components: int = 0
    reference_dropped_candidate_kept: int = 0
    kept_as_unresolved_wide_fit: int = 0

    def __add__(self, other: CatalogueCutCounts) -> CatalogueCutCounts:
        """Pool the counts of two catalogues."""
        return _pooled(self, other)


def compare_catalogue_cuts(
    candidate: CutCatalogue,
    reference: CutCatalogue,
    *,
    match_radius_degrees: float,
) -> CatalogueCutCounts:
    """Compare the sources each catalogue's astrometry cut keeps."""
    kept = candidate.astrometry_kept()
    several = candidate.several_components
    unresolved_wide = candidate.unresolved_wide_fits()
    own = CatalogueCutCounts(
        sources=len(candidate),
        astrometry_kept=int(kept.sum()),
        size_kept=int(candidate.size_kept().sum()),
        several_component_sources=int(several.sum()),
        unresolved_wide_fits=int(unresolved_wide.sum()),
    )
    candidate_index, reference_index = _mutual_matches(
        candidate, reference, match_radius_degrees
    )
    if not candidate_index.size:
        return own
    candidate_kept = kept[candidate_index]
    reference_kept = reference.astrometry_kept()[reference_index]
    dropped = reference_kept & ~candidate_kept
    added = ~reference_kept & candidate_kept
    return replace(
        own,
        matched=int(candidate_index.size),
        matched_alike=int((candidate_kept == reference_kept).sum()),
        reference_kept_candidate_dropped=int(dropped.sum()),
        dropped_with_several_components=int(
            (dropped & several[candidate_index]).sum()
        ),
        reference_dropped_candidate_kept=int(added.sum()),
        kept_as_unresolved_wide_fit=int(
            (added & unresolved_wide[candidate_index]).sum()
        ),
    )


def _mutual_matches(
    candidate: CutCatalogue, reference: CutCatalogue, radius_degrees: float
) -> tuple[IndexArray, IndexArray]:
    """Pair sources that are each other's nearest within the radius."""
    if not len(candidate) or not len(reference):
        empty = np.zeros(0, dtype=np.intp)
        return empty, empty
    candidate_coordinates = candidate.coordinates()
    reference_coordinates = reference.coordinates()
    nearest_reference, separation, _ = match_coordinates_sky(
        candidate_coordinates, reference_coordinates
    )
    nearest_candidate, _, _ = match_coordinates_sky(
        reference_coordinates, candidate_coordinates
    )
    candidate_index = np.arange(len(candidate))
    mutual = (
        np.asarray(nearest_candidate)[np.asarray(nearest_reference)]
        == candidate_index
    ) & (np.asarray(separation.deg) <= radius_degrees)
    return (
        candidate_index[mutual].astype(np.intp),
        np.asarray(nearest_reference)[mutual].astype(np.intp),
    )


def pybdsf_cut_catalogue(path: Path) -> CutCatalogue:
    """Read the cut columns of a PyBDSF ``srl`` FITS catalogue.

    PyBDSF writes positions, errors and sizes in degrees, and codes a
    source fitted with several Gaussians ``S_Code`` ``M``. When it finds no
    source it writes a table without those columns, an empty catalogue.
    """
    table = Table.read(path, format="fits")
    if not len(table):
        empty = np.zeros(0, dtype=np.float64)
        return CutCatalogue(
            right_ascension_degrees=empty,
            declination_degrees=empty,
            deconvolved_major_degrees=empty,
            right_ascension_error_degrees=empty,
            declination_error_degrees=empty,
            several_components=np.zeros(0, dtype=np.bool_),
            fitted_major_degrees=empty,
        )
    return CutCatalogue(
        right_ascension_degrees=_degrees(table, "RA"),
        declination_degrees=_degrees(table, "DEC"),
        deconvolved_major_degrees=_degrees(table, "DC_Maj"),
        right_ascension_error_degrees=_degrees(table, "E_RA"),
        declination_error_degrees=_degrees(table, "E_DEC"),
        several_components=np.char.strip(
            np.asarray(table["S_Code"], dtype=str)
        )
        == "M",
        fitted_major_degrees=_degrees(table, "Maj"),
    )


def hebog_cut_catalogue(
    catalogue: SourceCatalogue, view_path: Path
) -> CutCatalogue:
    """Read the Rapthor view of a catalogue, row for row with its sources.

    The view holds what Rapthor's cuts read; the catalogue says which
    sources have several Gaussian components and how wide each source's
    fit is.
    """
    view = read_rapthor_catalogue_fits(view_path)
    if len(view) != len(catalogue.sources):
        raise ValueError(
            f"{view_path} does not hold one row for each catalogue source"
        )
    components = Counter(
        component.source_id for component in catalogue.gaussian_components
    )
    return CutCatalogue(
        right_ascension_degrees=_degrees(view, "RA"),
        declination_degrees=_degrees(view, "DEC"),
        deconvolved_major_degrees=_degrees(view, "DC_Maj"),
        right_ascension_error_degrees=_degrees(view, "E_RA"),
        declination_error_degrees=_degrees(view, "E_DEC"),
        several_components=np.asarray(
            [components[source.source_id] > 1 for source in catalogue.sources],
            dtype=np.bool_,
        ),
        fitted_major_degrees=np.asarray(
            [
                np.nan
                if source.fitted_shape is None
                else source.fitted_shape.major_fwhm_degrees
                for source in catalogue.sources
            ],
            dtype=np.float64,
        ),
    )


def _degrees(table: Table, name: str) -> FloatArray:
    """Return one column in degrees; a column without an angle unit fails."""
    return np.asarray(
        table[name].quantity.to_value(units.deg), dtype=np.float64
    )


class _AgreementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Lane(_AgreementModel):
    """One Hebog configuration Rapthor could deploy."""

    profile: Literal["continuum", "compact"]
    background: Literal["estimated", "zero"]

    @property
    def name(self) -> str:
        """Return the lane's report name, such as ``compact-zero``."""
        return f"{self.profile}-{self.background}"


class ControlReference(_AgreementModel):
    """Released PyBDSF, run as a control on the same inputs."""

    finder_id: Literal["released-pybdsf"]
    container_image: str = Field(min_length=1)
    ncores: int = Field(gt=0)


class StratumSettings(_AgreementModel):
    """The configured :class:`StratumRules`."""

    bright_snr: float = Field(gt=0)
    edge_beams: float = Field(ge=0)
    masked_beams: float = Field(ge=0)
    crowded_beams: float = Field(gt=0)
    extended_beam_areas: float = Field(gt=0)

    def rules(self) -> StratumRules:
        """Return the rules as the pure record."""
        return StratumRules(
            bright_snr=self.bright_snr,
            edge_beams=self.edge_beams,
            masked_beams=self.masked_beams,
            crowded_beams=self.crowded_beams,
            extended_beam_areas=self.extended_beam_areas,
        )


class EmissionSettings(_AgreementModel):
    """The WSClean thresholds of the emission-pixel population."""

    floor_sigma: float = Field(gt=0)
    seed_sigma: float = Field(gt=0)


class AgreementCase(_AgreementModel):
    """An image beyond the quick check's, and the kind Rapthor gives it."""

    case: ImageCase
    image_kind: Literal["true-sky", "apparent"] | None = None


class RapthorAgreementConfiguration(_AgreementModel):
    """Versioned lanes, strata, gate and cases of the agreement check.

    ``quick_check`` names the quick-check configuration whose cases,
    dataset manifest and pinned-``master`` reference the check reuses, so
    its cached reference outputs serve both checks.
    """

    schema_version: Literal[1]
    check_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    quick_check: str = Field(min_length=1)
    threshpix: float = Field(gt=0)
    threshisl: float = Field(gt=0)
    lanes: tuple[Lane, ...] = Field(min_length=1)
    control: ControlReference
    strata: StratumSettings
    emission: EmissionSettings
    agreement_threshold: float = Field(gt=0, le=1)
    budget_seconds: float = Field(gt=0)
    cases: tuple[AgreementCase, ...]

    @model_validator(mode="after")
    def _unique_lanes_and_cases(self) -> Self:
        """Refuse a lane or case that would count its components twice."""
        lanes = [lane.name for lane in self.lanes]
        if len(set(lanes)) != len(lanes):
            raise ValueError("agreement lanes must be unique")
        cases = [item.case.case_id for item in self.cases]
        if len(set(cases)) != len(cases):
            raise ValueError("agreement cases must be unique")
        return self


def load_agreement_configuration(path: Path) -> RapthorAgreementConfiguration:
    """Load one agreement configuration; lanes and cases must be unique."""
    return RapthorAgreementConfiguration.model_validate_json(
        path.read_text(encoding="utf-8")
    )
