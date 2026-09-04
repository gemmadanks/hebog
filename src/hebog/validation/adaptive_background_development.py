"""Prospective design for the bounded adaptive-background development lane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AdaptiveMorphology = Literal[
    "shell",
    "curved-filament",
    "mixed-compact-extended",
]
AdaptiveTriggerCohort = Literal["below", "boundary", "above"]

_MORPHOLOGIES: tuple[AdaptiveMorphology, ...] = (
    "shell",
    "curved-filament",
    "mixed-compact-extended",
)
_BEAMS = ("beam-a", "beam-b")
_NOISE_GRADIENTS = ("flat", "varying")
_EXTENTS_BEAMS = (4.0, 8.0, 12.0)
_PLACEMENTS = ("interior", "tile-corner")
_TRIGGER_TARGETS: tuple[tuple[AdaptiveTriggerCohort, float], ...] = (
    ("below", 60.0),
    ("boundary", 75.0),
    ("above", 90.0),
)
_FIRST_NOISE_SEED = 2_026_950_001
_SEEDS_PER_CELL = 4
_GEOMETRY_COUNT = 12
_CELL_COUNT = 36


@dataclass(frozen=True, slots=True)
class AdaptiveDevelopmentCell:
    """One immutable geometry, trigger cohort, and noise-seed group."""

    cell_id: str
    morphology: AdaptiveMorphology
    beam_id: str
    noise_gradient_id: str
    extent_major_beams: float
    placement_id: str
    trigger_cohort: AdaptiveTriggerCohort
    target_nominal_peak_sigma: float
    noise_seeds: tuple[int, ...]


def _cell_id(  # noqa: PLR0913
    *,
    morphology: AdaptiveMorphology,
    beam_id: str,
    noise_gradient_id: str,
    extent_major_beams: float,
    placement_id: str,
    trigger_cohort: AdaptiveTriggerCohort,
) -> str:
    """Return the canonical identifier for one prospective cell."""
    morphology_id = morphology.replace("-", "_")
    return (
        f"{morphology_id}--{beam_id}--{noise_gradient_id}--"
        f"scale-{int(extent_major_beams)}--{placement_id}--"
        f"{trigger_cohort}"
    )


def _unvalidated_matrix() -> tuple[AdaptiveDevelopmentCell, ...]:
    """Construct the exact deterministic covering design."""
    cells: list[AdaptiveDevelopmentCell] = []
    next_seed = _FIRST_NOISE_SEED
    for morphology_index, morphology in enumerate(_MORPHOLOGIES):
        for beam_index, beam_id in enumerate(_BEAMS):
            for gradient_index, gradient_id in enumerate(_NOISE_GRADIENTS):
                covering_index = morphology_index + beam_index + gradient_index
                extent = _EXTENTS_BEAMS[covering_index % len(_EXTENTS_BEAMS)]
                placement = _PLACEMENTS[covering_index % len(_PLACEMENTS)]
                for cohort, target_sigma in _TRIGGER_TARGETS:
                    seeds = tuple(
                        range(next_seed, next_seed + _SEEDS_PER_CELL)
                    )
                    next_seed += _SEEDS_PER_CELL
                    cells.append(
                        AdaptiveDevelopmentCell(
                            cell_id=_cell_id(
                                morphology=morphology,
                                beam_id=beam_id,
                                noise_gradient_id=gradient_id,
                                extent_major_beams=extent,
                                placement_id=placement,
                                trigger_cohort=cohort,
                            ),
                            morphology=morphology,
                            beam_id=beam_id,
                            noise_gradient_id=gradient_id,
                            extent_major_beams=extent,
                            placement_id=placement,
                            trigger_cohort=cohort,
                            target_nominal_peak_sigma=target_sigma,
                            noise_seeds=seeds,
                        )
                    )
    return tuple(cells)


def _geometry_identity(
    cell: AdaptiveDevelopmentCell,
) -> tuple[AdaptiveMorphology, str, str, float, str]:
    """Return the trigger-independent identity of one geometry cell."""
    return (
        cell.morphology,
        cell.beam_id,
        cell.noise_gradient_id,
        cell.extent_major_beams,
        cell.placement_id,
    )


def validate_adaptive_development_matrix(
    cells: tuple[AdaptiveDevelopmentCell, ...],
) -> None:
    """Fail closed if the frozen covering design or seed set changes."""
    if len(cells) != _CELL_COUNT:
        raise ValueError("adaptive development matrix must have 36 cells")

    expected_targets = dict(_TRIGGER_TARGETS)
    if any(
        expected_targets.get(cell.trigger_cohort)
        != cell.target_nominal_peak_sigma
        for cell in cells
    ):
        raise ValueError("adaptive trigger cohort or target changed")

    seeds = tuple(seed for cell in cells for seed in cell.noise_seeds)
    expected_seeds = tuple(
        range(
            _FIRST_NOISE_SEED,
            _FIRST_NOISE_SEED + _CELL_COUNT * _SEEDS_PER_CELL,
        )
    )
    if (
        any(len(cell.noise_seeds) != _SEEDS_PER_CELL for cell in cells)
        or seeds != expected_seeds
        or len(seeds) != len(set(seeds))
    ):
        raise ValueError("adaptive development noise seeds changed")

    expected = _unvalidated_matrix()
    geometries = {_geometry_identity(cell) for cell in cells}
    expected_geometries = {_geometry_identity(cell) for cell in expected}
    if geometries != expected_geometries or len(geometries) != _GEOMETRY_COUNT:
        raise ValueError("adaptive development geometry coverage changed")
    if any(
        {
            cell.trigger_cohort
            for cell in cells
            if _geometry_identity(cell) == geometry
        }
        != set(expected_targets)
        for geometry in geometries
    ):
        raise ValueError("each geometry requires all trigger cohorts")

    if cells != expected:
        raise ValueError("adaptive development cell identities changed")


def build_adaptive_development_matrix() -> tuple[AdaptiveDevelopmentCell, ...]:
    """Return the exact validated 144-image prospective matrix."""
    matrix = _unvalidated_matrix()
    validate_adaptive_development_matrix(matrix)
    return matrix
