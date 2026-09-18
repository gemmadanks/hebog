# pyright: reportMissingTypeStubs=false
"""Boundary validation of the composition over published detection planes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.science.continuum import evaluate_continuum_candidate_products
from hebog.science.models import TiledMultiscaleDetection
from hebog.science.profile import (
    ContinuumScienceProfile,
    load_continuum_science_profile,
)

_ROOT = Path(__file__).parents[2]
_SHAPE = (6, 7)


def _review() -> ContinuumScienceProfile:
    """Load the installed reviewed continuum profile fixture."""
    return load_continuum_science_profile(
        (
            _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
        ).read_bytes()
    )


def _multiscale(
    *,
    significant_scale_masks: tuple[npt.NDArray[np.bool_], ...] | None = None,
) -> TiledMultiscaleDetection:
    """Return one empty published detection pass over a small plane."""
    empty = np.zeros(_SHAPE, dtype=np.bool_)
    return TiledMultiscaleDetection(
        detection_labels=np.zeros(_SHAPE, dtype=np.int32),
        reconstruction_mask=empty,
        position_signal_jy_per_beam=np.zeros(_SHAPE, dtype=np.float64),
        significant_scale_masks=(
            (empty, empty, empty)
            if significant_scale_masks is None
            else significant_scale_masks
        ),
        scale_islands_by_order=((), (), ()),
        scale_nominal_beam_fwhms=(1.0, 2.0, 4.0),
    )


def _evaluate(
    valid_pixels: npt.NDArray[np.bool_],
    multiscale: TiledMultiscaleDetection,
) -> None:
    """Run the composition over one analytic plane and its published pass."""
    evaluate_continuum_candidate_products(
        np.zeros(_SHAPE, dtype=np.float64),
        valid_pixels,
        np.zeros(_SHAPE, dtype=np.float64),
        np.ones(_SHAPE, dtype=np.float64),
        beam=BeamShapePixels(4.0, 3.0, 0.0),
        review=_review(),
        multiscale=multiscale,
    )


def test_composition_rejects_a_validity_plane_it_cannot_align() -> None:
    """The detection domain must be one aligned boolean plane."""
    with pytest.raises(ValueError, match="aligned boolean plane"):
        _evaluate(
            np.ones(_SHAPE, dtype=np.int32),  # pyright: ignore[reportArgumentType]
            _multiscale(),
        )


def test_composition_rejects_scale_support_outside_the_valid_domain() -> None:
    """Published scale support cannot claim a scientifically invalid pixel."""
    invalid_support = np.zeros(_SHAPE, dtype=np.bool_)
    invalid_support[2, 3] = True
    valid = np.ones(_SHAPE, dtype=np.bool_)
    valid[2, 3] = False

    with pytest.raises(ValueError, match="scientifically valid"):
        _evaluate(
            valid,
            _multiscale(
                significant_scale_masks=(
                    invalid_support,
                    np.zeros(_SHAPE, dtype=np.bool_),
                    np.zeros(_SHAPE, dtype=np.bool_),
                )
            ),
        )
