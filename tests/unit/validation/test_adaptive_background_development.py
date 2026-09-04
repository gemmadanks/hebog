"""Contracts for the Phase 5 adaptive-background development design."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from hebog.validation.adaptive_background_development import (
    build_adaptive_development_matrix,
    validate_adaptive_development_matrix,
)


def test_matrix_is_small_balanced_and_brackets_the_frozen_trigger() -> None:
    """The development lane covers the risk without becoming a replay."""
    matrix = build_adaptive_development_matrix()

    assert len(matrix) == 36
    assert sum(len(cell.noise_seeds) for cell in matrix) == 144
    assert {cell.trigger_cohort for cell in matrix} == {
        "below",
        "boundary",
        "above",
    }
    assert {
        (cell.trigger_cohort, cell.target_nominal_peak_sigma)
        for cell in matrix
    } == {
        ("below", 60.0),
        ("boundary", 75.0),
        ("above", 90.0),
    }

    geometries = {
        (
            cell.morphology,
            cell.beam_id,
            cell.noise_gradient_id,
            cell.extent_major_beams,
            cell.placement_id,
        )
        for cell in matrix
    }
    assert len(geometries) == 12
    assert {
        (morphology, beam_id, gradient_id)
        for morphology, beam_id, gradient_id, _, _ in geometries
    } == {
        (morphology, beam_id, gradient_id)
        for morphology in (
            "shell",
            "curved-filament",
            "mixed-compact-extended",
        )
        for beam_id in ("beam-a", "beam-b")
        for gradient_id in ("flat", "varying")
    }
    assert {geometry[3] for geometry in geometries} == {4.0, 8.0, 12.0}
    assert {geometry[4] for geometry in geometries} == {
        "interior",
        "tile-corner",
    }
    assert Counter(geometry[3] for geometry in geometries) == {
        4.0: 4,
        8.0: 4,
        12.0: 4,
    }
    assert Counter(geometry[4] for geometry in geometries) == {
        "interior": 6,
        "tile-corner": 6,
    }


def test_matrix_seeds_are_unique_ordered_and_prospectively_reserved() -> None:
    """Every image is one new independent noise realization."""
    matrix = build_adaptive_development_matrix()
    seeds = tuple(seed for cell in matrix for seed in cell.noise_seeds)

    assert seeds == tuple(range(2_026_950_001, 2_026_950_145))
    assert len(seeds) == len(set(seeds))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            {"noise_seeds": (2_026_950_001,) * 4},
            "noise seeds",
        ),
        (
            {"target_nominal_peak_sigma": 76.0},
            "trigger cohort",
        ),
        (
            {"extent_major_beams": 5.0},
            "geometry coverage",
        ),
    ],
)
def test_matrix_rejects_identity_or_coverage_drift(
    change: dict[str, object],
    message: str,
) -> None:
    """A changed seed, trigger, or geometry cannot reuse the review."""
    matrix = list(build_adaptive_development_matrix())
    matrix[0] = replace(matrix[0], **change)

    with pytest.raises(ValueError, match=message):
        validate_adaptive_development_matrix(tuple(matrix))


def test_matrix_rejects_an_invented_cell() -> None:
    """Only the predeclared morphology vocabulary may enter the lane."""
    matrix = build_adaptive_development_matrix()
    invented = replace(matrix[-1], cell_id="invented")

    with pytest.raises(ValueError, match="cell identities"):
        validate_adaptive_development_matrix((*matrix[:-1], invented))


def test_matrix_rejects_a_missing_cell() -> None:
    """The execution count is part of the prospective identity."""
    matrix = build_adaptive_development_matrix()

    with pytest.raises(ValueError, match="must have 36 cells"):
        validate_adaptive_development_matrix(matrix[:-1])


def test_matrix_requires_every_trigger_cohort_per_geometry() -> None:
    """Balanced global counts cannot hide a missing within-geometry cohort."""
    matrix = list(build_adaptive_development_matrix())
    matrix[0] = replace(
        matrix[0],
        trigger_cohort="boundary",
        target_nominal_peak_sigma=75.0,
    )

    with pytest.raises(ValueError, match="geometry requires"):
        validate_adaptive_development_matrix(tuple(matrix))
