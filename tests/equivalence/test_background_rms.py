# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Phase 2 RMS-map comparisons with frozen PyBDSF references."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import (
    AdaptiveRmsConfig,
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
)
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource
from hebog.stages.background import (
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
)
from hebog.validation.comparison import compare_rms_maps

pytestmark = pytest.mark.equivalence

_REFERENCE_ROOT = (
    Path(__file__).parents[1]
    / "data"
    / "pybdsf"
    / "pybdsf-compact-reference-256"
)
_INPUT_SHA256 = (
    "80e7d55f5ff22a46be2d977babe0d05f7899972f13b9518a606959eeab502ffc"
)


def _configuration() -> BackgroundRmsConfig:
    """Return the frozen Rapthor RMS geometry and Hebog robust policy."""
    statistics = RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=6,
    )
    return BackgroundRmsConfig(
        coarse=RmsGridConfig(
            window_shape_yx=(150, 150),
            step_yx=(50, 50),
            statistics=statistics,
            maximum_batch_cells=16,
        ),
        adaptive=AdaptiveRmsConfig(
            grid=RmsGridConfig(
                window_shape_yx=(35, 35),
                step_yx=(7, 7),
                statistics=statistics,
                maximum_batch_cells=16,
            ),
            candidate_threshold_sigma=75.0,
            influence_radius_pixels=75.0,
            transition_width_pixels=20.0,
        ),
        maximum_spatial_window_fraction=0.25,
        maximum_constant_map_pixels=1_000_000,
    )


@pytest.fixture(scope="module")
def candidate_rms() -> npt.NDArray[np.float64]:
    """Estimate the compact RMS map once through the public stage seams."""
    source = FitsImageSource(_REFERENCE_ROOT / "input.fits")
    shape_yx = source.metadata().shape_yx
    config = _configuration()
    grids = estimate_background_rms_grids(
        source,
        shape_yx,
        config,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )
    manifest = plan_image_partitions(
        image_shape_yx=shape_yx,
        tile_core_shape_yx=shape_yx,
        halo_yx=(0, 0),
    )
    request = prepare_background_rms_tile_request(
        manifest.tiles[0],
        grids,
        config,
    )
    return estimate_background_rms_tile(source, request).rms


@pytest.fixture(scope="module")
def source_free_pixels() -> npt.NDArray[np.bool_]:
    """Return pixels outside the frozen PyBDSF source-filter mask."""
    raw_mask = cast(
        Any,
        fits.getdata(_REFERENCE_ROOT / "release" / "source_filter_mask.fits"),
    )
    return np.asarray(np.squeeze(np.asarray(raw_mask)) == 0, dtype=np.bool_)


def test_compact_reference_input_checksum_is_intact() -> None:
    """The candidate input remains bound to the frozen Phase 0 dataset."""
    digest = hashlib.sha256((_REFERENCE_ROOT / "input.fits").read_bytes())

    assert digest.hexdigest() == _INPUT_SHA256


@pytest.mark.parametrize("reference", ["release", "master"])
@pytest.mark.parametrize(
    "product", ["true_sky_rms.fits", "flat_noise_rms.fits"]
)
def test_compact_rms_map_meets_pybdsf_scientific_gates(
    candidate_rms: npt.NDArray[np.float64],
    source_free_pixels: npt.NDArray[np.bool_],
    reference: str,
    product: str,
) -> None:
    """Source-free median and tail differences meet the Phase 2 gates."""
    raw_reference = cast(
        Any,
        fits.getdata(_REFERENCE_ROOT / reference / product),
    )
    reference_rms = np.asarray(
        np.squeeze(np.asarray(raw_reference)),
        dtype=np.float64,
    )

    report = compare_rms_maps(
        reference_rms,
        candidate_rms,
        valid_mask=source_free_pixels,
    )

    median_difference = report.median_absolute_fractional_difference
    tail_difference = report.percentile_95_absolute_fractional_difference
    assert median_difference is not None
    assert tail_difference is not None
    assert median_difference <= 0.02
    assert tail_difference <= 0.05
