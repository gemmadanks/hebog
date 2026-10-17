# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Measure each finder's correctness, beside its agreement with PyBDSF.

Agreement with pinned PyBDSF ``master`` is compatibility, not correctness:
a component the two finders decide differently may be either finder's
mistake. These measures need no reference finder.

- On generated images, :func:`ideal_mask` is the mask a perfect finder
  would draw on the noiseless emission, and :func:`emission_recall`
  measures how much of it a finder's mask covers.
- On real images, :func:`plan_injection` and :func:`inject_point_sources`
  add beam-shaped sources at known signal-to-noise ratios away from the
  existing emission, and :func:`injected_recovery` measures which a finder
  keeps and how well it measures their flux.
- On negated real images every island is false; :func:`mask_islands`
  counts them.
- :func:`negative_pixel_noise` estimates the noise from negative pixels,
  which faint sources cannot inflate, and :func:`compare_noise` compares a
  finder's RMS map with it.
- :func:`real_emission_decisions` splits a finder's disagreements with the
  reference by whether the component lies on real emission: the ideal
  mask on generated images, :func:`significant_emission` on real ones.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy import ndimage
from scipy.spatial import cKDTree

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.rapthor_agreement import (
    ALL_COMPONENTS,
    ComponentPixels,
    pooled,
)

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

# PyBDSF's and LSMTool's islands are 8-connected.
_EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)
_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
# A beam-shaped source is drawn out to three major FWHM, where it has
# fallen below 1e-10 of its peak.
_STAMP_HALF_WIDTH_FWHM = 3.0
# Grid sites move by up to a quarter of the spacing each way, so no two
# sources are closer than half the spacing.
_JITTER_FRACTION = 0.25


def _labelled(mask: BoolArray) -> tuple[npt.NDArray[np.int32], int]:
    return cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage.label(mask, structure=_EIGHT_CONNECTED),
    )


def _measurable(noise: FloatArray) -> BoolArray:
    return np.isfinite(noise) & (noise > 0)


def ideal_mask(
    emission: FloatArray,
    noise: FloatArray,
    *,
    threshisl: float,
    threshpix: float,
) -> BoolArray:
    """Return the mask a perfect finder would draw on noiseless emission.

    An island is an 8-connected region of emission at least ``threshisl``
    times the local noise; it counts when it holds a pixel at least
    ``threshpix`` times the noise, as PyBDSF's islands do on the noisy
    image. Blank emission and unmeasured noise are never in the mask.
    """
    valid = np.isfinite(emission) & _measurable(noise)
    significance = np.zeros(emission.shape, dtype=np.float64)
    significance[valid] = emission[valid] / noise[valid]
    labels, _ = _labelled(valid & (significance >= threshisl))
    seeded = np.unique(labels[valid & (significance >= threshpix)])
    return np.isin(labels, seeded[seeded > 0])


@dataclass(frozen=True, slots=True)
class EmissionRecall:
    """How much of the ideal mask a finder's mask covers.

    Fluxes are sums of the noiseless emission in the image's units.
    ``off_emission_pixels`` are mask pixels where the emission is below
    one noise sigma: the mask there covers noise, not sources.
    """

    ideal_pixels: int = 0
    covered_pixels: int = 0
    ideal_flux: float = 0.0
    covered_flux: float = 0.0
    mask_pixels: int = 0
    off_emission_pixels: int = 0

    def __add__(self, other: EmissionRecall) -> EmissionRecall:
        """Pool two images' counts."""
        return pooled(self, other)

    @property
    def recall(self) -> float | None:
        """Return the fraction of ideal pixels the mask covers."""
        if not self.ideal_pixels:
            return None
        return self.covered_pixels / self.ideal_pixels

    @property
    def flux_recall(self) -> float | None:
        """Return the fraction of the ideal mask's emission covered."""
        if not self.ideal_flux > 0:
            return None
        return self.covered_flux / self.ideal_flux

    @property
    def off_emission_fraction(self) -> float | None:
        """Return the fraction of the mask that covers no emission."""
        if not self.mask_pixels:
            return None
        return self.off_emission_pixels / self.mask_pixels


def emission_recall(
    mask: BoolArray,
    *,
    ideal: BoolArray,
    emission: FloatArray,
    noise: FloatArray,
) -> EmissionRecall:
    """Measure a finder's mask against the ideal one on valid pixels."""
    valid = np.isfinite(emission) & _measurable(noise)
    in_mask = mask & valid
    covered = in_mask & ideal
    return EmissionRecall(
        ideal_pixels=int(np.count_nonzero(ideal & valid)),
        covered_pixels=int(np.count_nonzero(covered)),
        ideal_flux=float(emission[ideal & valid].sum()),
        covered_flux=float(emission[covered].sum()),
        mask_pixels=int(np.count_nonzero(in_mask)),
        off_emission_pixels=int(
            np.count_nonzero(in_mask & (emission < noise))
        ),
    )


def negative_pixel_noise(
    image: FloatArray, *, box_pixels: int, minimum_pixels: int
) -> FloatArray:
    """Return the RMS of the negative pixels in square boxes.

    Interferometric images have no total-power background, so the noise is
    centred on zero and the RMS of its negative half is the noise RMS;
    sources only add positive brightness and cannot inflate it. Each box of
    ``box_pixels`` a side, the last row and column of boxes clipped by the
    image, takes the value of its own negative pixels, or NaN when it has
    fewer than ``minimum_pixels`` of them.
    """
    height, width = image.shape
    rows = -(-height // box_pixels)
    columns = -(-width // box_pixels)
    padded = np.full((rows * box_pixels, columns * box_pixels), np.nan)
    padded[:height, :width] = image
    boxes = padded.reshape(rows, box_pixels, columns, box_pixels)
    negative = np.isfinite(boxes) & (boxes < 0)
    counts = negative.sum(axis=(1, 3))
    squares = np.where(negative, np.square(boxes), 0.0).sum(axis=(1, 3))
    noise = np.full((rows, columns), np.nan)
    enough = counts >= minimum_pixels
    noise[enough] = np.sqrt(squares[enough] / counts[enough])
    expanded = np.repeat(np.repeat(noise, box_pixels, axis=0), box_pixels, 1)
    return np.asarray(expanded[:height, :width], dtype=np.float64)


@dataclass(frozen=True, slots=True)
class NoiseComparison:
    """How a finder's RMS map compares with the negative-pixel noise.

    ``inflated`` counts pixels whose RMS exceeds the noise by more than the
    tolerance, ``deflated`` those below it by as much; ``log_ratio_sum``
    sums the natural logarithms of the ratios, so pooled comparisons keep
    their geometric mean.
    """

    pixels: int = 0
    inflated: int = 0
    deflated: int = 0
    log_ratio_sum: float = 0.0

    def __add__(self, other: NoiseComparison) -> NoiseComparison:
        """Pool two comparisons."""
        return pooled(self, other)

    @property
    def inflated_fraction(self) -> float | None:
        """Return the fraction of pixels whose RMS reads too high."""
        return self.inflated / self.pixels if self.pixels else None

    @property
    def deflated_fraction(self) -> float | None:
        """Return the fraction of pixels whose RMS reads too low."""
        return self.deflated / self.pixels if self.pixels else None

    @property
    def geometric_mean_ratio(self) -> float | None:
        """Return the geometric mean of the RMS over the noise."""
        if not self.pixels:
            return None
        return math.exp(self.log_ratio_sum / self.pixels)


def compare_noise(
    rms: FloatArray,
    noise: FloatArray,
    *,
    tolerance: float,
    pixels: ComponentPixels | None = None,
) -> NoiseComparison:
    """Compare an RMS map with the noise, at ``pixels`` or everywhere.

    Only pixels where both are finite and positive are compared.
    """
    if pixels is not None:
        rms = rms[pixels.rows, pixels.columns]
        noise = noise[pixels.rows, pixels.columns]
    valid = _measurable(rms) & _measurable(noise)
    ratio = rms[valid] / noise[valid]
    return NoiseComparison(
        pixels=int(ratio.size),
        inflated=int(np.count_nonzero(ratio > 1 + tolerance)),
        deflated=int(np.count_nonzero(ratio < 1 / (1 + tolerance))),
        log_ratio_sum=float(np.log(ratio).sum()),
    )


@dataclass(frozen=True, slots=True)
class InjectedSources:
    """Beam-shaped sources added to an image, in zero-based pixels.

    ``snr`` is each source's peak over the negative-pixel noise at its
    site, and ``peak_jy_per_beam`` that peak, which is also its flux in Jy.
    """

    x: FloatArray
    y: FloatArray
    snr: FloatArray
    peak_jy_per_beam: FloatArray

    def __len__(self) -> int:
        """Return the number of sources."""
        return int(self.x.size)


def plan_injection(  # noqa: PLR0913
    image: FloatArray,
    noise: FloatArray,
    *,
    beam_fwhm_pixels: float,
    snr_levels: Sequence[float],
    per_level: int,
    spacing_beams: float,
    margin_beams: float,
    clear_beams: float,
    clear_sigma: float,
    seed: int,
) -> InjectedSources:
    """Choose sites and peaks for sources to inject, reproducibly.

    Sites sit on a grid ``spacing_beams`` apart, each moved at random by
    up to a quarter of the spacing, at least ``margin_beams`` from the
    border. A site must lie further than ``clear_beams`` from any blank or
    unmeasured pixel and from any pixel brighter or fainter than
    ``clear_sigma`` times the noise, so the completeness is that of
    isolated sources. Sites are shuffled and taken in turn by each level,
    so every level gets the same number, at most ``per_level``.
    """
    generator = np.random.default_rng(seed)
    height, width = image.shape
    spacing = spacing_beams * beam_fwhm_pixels
    centres_y = np.arange(spacing / 2, height, spacing)
    centres_x = np.arange(spacing / 2, width, spacing)
    grid_y, grid_x = np.meshgrid(centres_y, centres_x, indexing="ij")
    jitter = _JITTER_FRACTION * spacing
    x = grid_x.ravel() + generator.uniform(-jitter, jitter, grid_x.size)
    y = grid_y.ravel() + generator.uniform(-jitter, jitter, grid_y.size)
    margin = margin_beams * beam_fwhm_pixels
    inside = (
        (x >= margin)
        & (x <= width - 1 - margin)
        & (y >= margin)
        & (y <= height - 1 - margin)
    )
    x, y = x[inside], y[inside]
    measurable = np.isfinite(image) & _measurable(noise)
    significant = np.zeros(image.shape, dtype=np.bool_)
    significant[measurable] = np.abs(image[measurable]) >= (
        clear_sigma * noise[measurable]
    )
    reach = math.ceil(clear_beams * beam_fwhm_pixels)
    # A square maximum filter is separable, so it stays fast at 3,000².
    occupied = (
        ndimage.maximum_filter(
            (~measurable | significant).astype(np.uint8),
            size=2 * reach + 1,
            mode="constant",
            cval=0,
        )
        > 0
    )
    rows = np.rint(y).astype(np.intp)
    columns = np.rint(x).astype(np.intp)
    clear = ~occupied[rows, columns]
    x, y, rows, columns = x[clear], y[clear], rows[clear], columns[clear]
    order = generator.permutation(x.size)
    count = min(per_level, x.size // len(snr_levels)) * len(snr_levels)
    chosen = order[:count]
    snr = np.resize(np.asarray(snr_levels, dtype=np.float64), count)
    return InjectedSources(
        x=x[chosen],
        y=y[chosen],
        snr=snr,
        peak_jy_per_beam=snr * noise[rows[chosen], columns[chosen]],
    )


def inject_point_sources(
    image: FloatArray, sources: InjectedSources, beam: BeamShapePixels
) -> FloatArray:
    """Return a copy of ``image`` with beam-shaped sources added.

    The beam's angle runs counter-clockwise from +x, as Hebog's pixel beam
    does. Blank pixels stay blank.
    """
    injected = np.array(image, dtype=np.float64, copy=True)
    height, width = image.shape
    reach = math.ceil(_STAMP_HALF_WIDTH_FWHM * beam.major_fwhm_pixels)
    angle = math.radians(beam.position_angle_degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    major_sigma = beam.major_fwhm_pixels / _FWHM_PER_SIGMA
    minor_sigma = beam.minor_fwhm_pixels / _FWHM_PER_SIGMA
    for x, y, peak in zip(
        sources.x, sources.y, sources.peak_jy_per_beam, strict=True
    ):
        row_start = max(0, math.floor(y) - reach)
        row_stop = min(height, math.floor(y) + reach + 1)
        column_start = max(0, math.floor(x) - reach)
        column_stop = min(width, math.floor(x) + reach + 1)
        y_offset = np.arange(row_start, row_stop)[:, np.newaxis] - y
        x_offset = np.arange(column_start, column_stop)[np.newaxis, :] - x
        major = cosine * x_offset + sine * y_offset
        minor = -sine * x_offset + cosine * y_offset
        injected[row_start:row_stop, column_start:column_stop] += (
            peak
            * np.exp(
                -0.5
                * (
                    np.square(major / major_sigma)
                    + np.square(minor / minor_sigma)
                )
            )
        )
    return injected


@dataclass(frozen=True, slots=True)
class InjectionOutcome:
    """Whether a finder kept and measured each injected source.

    ``kept`` is whether Rapthor's filter keeps a component at the source,
    reading the mask as LSMTool does; ``matched`` whether a published
    source lies within the match radius; ``flux_ratio`` the nearest such
    source's flux over the injected flux, NaN when none matched.
    """

    snr: FloatArray
    kept: BoolArray
    matched: BoolArray
    flux_ratio: FloatArray


def injected_recovery(  # noqa: PLR0913
    sources: InjectedSources,
    *,
    mask: BoolArray,
    catalogue_x: FloatArray,
    catalogue_y: FloatArray,
    catalogue_flux: FloatArray,
    match_radius_pixels: float,
) -> InjectionOutcome:
    """Measure which injected sources a finder keeps and matches."""
    kept = mask[
        np.trunc(sources.y).astype(np.intp),
        np.trunc(sources.x).astype(np.intp),
    ]
    flux_ratio = np.full(len(sources), np.nan)
    matched = np.zeros(len(sources), dtype=np.bool_)
    if catalogue_x.size:
        distance, nearest = cKDTree(
            np.column_stack([catalogue_x, catalogue_y])
        ).query(np.column_stack([sources.x, sources.y]))
        matched = np.asarray(distance) <= match_radius_pixels
        nearest = np.asarray(nearest)[matched]
        flux_ratio[matched] = (
            catalogue_flux[nearest] / sources.peak_jy_per_beam[matched]
        )
    return InjectionOutcome(
        snr=sources.snr,
        kept=np.asarray(kept, dtype=np.bool_),
        matched=matched,
        flux_ratio=flux_ratio,
    )


@dataclass(frozen=True, slots=True)
class LevelRecovery:
    """One signal-to-noise level's recovery over every image."""

    injected: int
    kept: int
    matched: int
    median_flux_ratio: float | None

    @property
    def kept_fraction(self) -> float:
        """Return the fraction of the level's sources Rapthor keeps."""
        return self.kept / self.injected

    @property
    def matched_fraction(self) -> float:
        """Return the fraction of the level's sources published."""
        return self.matched / self.injected


def recovery_by_level(
    outcomes: Sequence[InjectionOutcome],
) -> dict[float, LevelRecovery]:
    """Summarise recovery by signal-to-noise level, lowest first."""
    snr = np.concatenate([outcome.snr for outcome in outcomes])
    kept = np.concatenate([outcome.kept for outcome in outcomes])
    matched = np.concatenate([outcome.matched for outcome in outcomes])
    ratio = np.concatenate([outcome.flux_ratio for outcome in outcomes])
    levels: dict[float, LevelRecovery] = {}
    for level in np.unique(snr):
        selected = snr == level
        ratios = ratio[selected & matched]
        levels[float(level)] = LevelRecovery(
            injected=int(np.count_nonzero(selected)),
            kept=int(np.count_nonzero(selected & kept)),
            matched=int(np.count_nonzero(selected & matched)),
            median_flux_ratio=float(np.median(ratios))
            if ratios.size
            else None,
        )
    return levels


@dataclass(frozen=True, slots=True)
class MaskIslands:
    """The 8-connected islands of a mask and the pixels they cover."""

    islands: int = 0
    pixels: int = 0

    def __add__(self, other: MaskIslands) -> MaskIslands:
        """Pool two masks' counts."""
        return pooled(self, other)


def mask_islands(mask: BoolArray) -> MaskIslands:
    """Count a mask's 8-connected islands and its pixels."""
    _, count = _labelled(np.asarray(mask, dtype=np.bool_))
    return MaskIslands(islands=count, pixels=int(np.count_nonzero(mask)))


def significant_emission(
    pixels: ComponentPixels,
    *,
    image: FloatArray,
    noise: FloatArray,
    threshold_sigma: float,
) -> BoolArray:
    """Return which components lie on emission above the threshold.

    A component is on real emission where the image at its pixel is at
    least ``threshold_sigma`` times the noise; a blank pixel or unmeasured
    noise leaves it unproven.
    """
    values = image[pixels.rows, pixels.columns]
    level = noise[pixels.rows, pixels.columns]
    valid = np.isfinite(values) & _measurable(level)
    real = np.zeros(len(pixels), dtype=np.bool_)
    real[valid] = values[valid] >= threshold_sigma * level[valid]
    return real


@dataclass(frozen=True, slots=True)
class RealEmissionDecisions:
    """A candidate's disagreements with the reference, split by truth.

    ``lost_real`` counts the real components the reference keeps and the
    candidate rejects, out of ``reference_only``; ``gained_real`` the real
    components only the candidate keeps, out of ``candidate_only``. Both
    fractions are taken over the real components the reference keeps.
    """

    reference_kept_real: int = 0
    lost_real: int = 0
    reference_only: int = 0
    candidate_kept_real: int = 0
    gained_real: int = 0
    candidate_only: int = 0

    def __add__(self, other: RealEmissionDecisions) -> RealEmissionDecisions:
        """Pool two populations' counts."""
        return pooled(self, other)

    @property
    def lost_real_fraction(self) -> float | None:
        """Return the share of the reference's real components lost."""
        if not self.reference_kept_real:
            return None
        return self.lost_real / self.reference_kept_real

    @property
    def gained_real_fraction(self) -> float | None:
        """Return the real components gained per real one the reference has."""
        if not self.reference_kept_real:
            return None
        return self.gained_real / self.reference_kept_real


def real_emission_decisions(
    candidate_mask: npt.ArrayLike,
    reference_mask: npt.ArrayLike,
    pixels: ComponentPixels,
    strata: Mapping[str, BoolArray],
    *,
    real: BoolArray,
) -> dict[str, RealEmissionDecisions]:
    """Split disagreements by truth, over every component and each stratum."""
    candidate = pixels.kept_by(candidate_mask)
    reference = pixels.kept_by(reference_mask)
    selections = {ALL_COMPONENTS: np.ones(len(pixels), dtype=np.bool_)}

    def count(selected: BoolArray) -> int:
        return int(np.count_nonzero(selected))

    return {
        name: RealEmissionDecisions(
            reference_kept_real=count(selection & reference & real),
            lost_real=count(selection & reference & ~candidate & real),
            reference_only=count(selection & reference & ~candidate),
            candidate_kept_real=count(selection & candidate & real),
            gained_real=count(selection & candidate & ~reference & real),
            candidate_only=count(selection & candidate & ~reference),
        )
        for name, selection in (selections | dict(strata)).items()
    }
