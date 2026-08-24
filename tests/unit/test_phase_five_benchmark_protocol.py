"""Contracts for the incremental Phase 5 performance matrix."""

from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from hebog.io import FitsImageSource

_ROOT = Path(__file__).parents[2]
_GENERATOR: Any = SimpleNamespace(
    **runpy.run_path(str(_ROOT / "scripts/benchmark/generate_phase5_input.py"))
)
_MEASUREMENT: Any = SimpleNamespace(
    **runpy.run_path(
        str(_ROOT / "scripts/benchmark/measure_phase5_multiscale.py")
    )
)
_MATRIX: Any = SimpleNamespace(
    **runpy.run_path(str(_ROOT / "scripts/benchmark/run_phase5_matrix.py"))
)


def _protocol_path() -> Path:
    """Return the checked-in Phase 5 performance protocol."""
    return _ROOT / "config/benchmarks/phase-5-performance.json"


def _raw_protocol() -> dict[str, Any]:
    """Return one mutable protocol mapping for rejection tests."""
    value = json.loads(_protocol_path().read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _write_protocol(tmp_path: Path, value: dict[str, Any]) -> Path:
    """Write one malformed protocol candidate."""
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _make_draft(value: dict[str, Any]) -> None:
    """Change the protocol status."""
    value["status"] = "draft"


def _remove_profile(value: dict[str, Any]) -> None:
    """Remove one required workload profile."""
    value["profiles"] = ["sparse", "extended"]


def _move_crossover(value: dict[str, Any]) -> None:
    """Move the crossover beyond the required matrix anchors."""
    value["crossover_sizes_pixels"] = [1536]


def _zero_budget(value: dict[str, Any]) -> None:
    """Make the representative budget invalid."""
    budgets = cast(dict[str, Any], value["budgets"])
    budgets["multiscale_processing_seconds"] = 0


def test_phase_five_performance_protocol_covers_anchors_and_crossovers() -> (
    None
):
    """The frozen matrix spans every required workload and executor probe."""
    protocol = _MATRIX._load_protocol(_protocol_path())
    cells = _MATRIX._cell_identities(protocol)

    assert protocol.sizes == (256, 512, 1024, 3000)
    assert protocol.profiles == ("sparse", "normal", "extended")
    assert protocol.crossover_sizes == (1024, 3000)
    assert protocol.multiscale_budget_seconds == 6.0
    assert protocol.minimum_tile_size == 256
    assert protocol.representative_tile_size == 256
    assert protocol.maximum_tiles_per_batch == 12
    assert protocol.workers == 4
    assert protocol.threads_per_worker == 1
    assert protocol.warmups == 1
    assert protocol.repetitions == 5
    assert len(cells) == 18
    assert next(cell for cell in cells if cell.size == 256).tile_size == 256
    for size in protocol.crossover_sizes:
        for profile in protocol.profiles:
            assert {
                cell.executor
                for cell in cells
                if cell.size == size and cell.profile == profile
            } == {"serial", "dask"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (_make_draft, "frozen schema"),
        (_remove_profile, "profiles changed"),
        (_move_crossover, "matrix anchors"),
        (_zero_budget, "positive number"),
    ),
)
def test_phase_five_performance_protocol_rejects_drift(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    """Malformed resources, workloads, anchors, and budgets fail closed."""
    value = _raw_protocol()
    mutation(value)

    with pytest.raises(ValueError, match=message):
        _MATRIX._load_protocol(_write_protocol(tmp_path, value))


def test_phase_five_generator_is_deterministic_and_stratified() -> None:
    """Reproducible workload profiles share geometry but not morphology."""
    sparse = _GENERATOR._generate_values(128, "sparse")
    repeated = _GENERATOR._generate_values(128, "sparse")
    normal = _GENERATOR._generate_values(128, "normal")
    extended = _GENERATOR._generate_values(128, "extended")

    np.testing.assert_array_equal(repeated, sparse)
    assert sparse.shape == normal.shape == extended.shape == (128, 128)
    assert np.isfinite(sparse).all()
    assert not np.array_equal(normal, sparse)
    assert not np.array_equal(extended, sparse)


def test_phase_five_benchmark_derives_pixel_beam_from_fits(
    tmp_path: Path,
) -> None:
    """The measured filter beam follows input WCS and beam metadata."""
    path = tmp_path / "input.fits"
    _GENERATOR._generate_input(
        path,
        size=64,
        profile="extended",
    )

    beam = _MEASUREMENT._beam_from_metadata(FitsImageSource(path))

    assert beam.major_fwhm_pixels == pytest.approx(5.0, rel=1e-6)
    assert beam.minor_fwhm_pixels == pytest.approx(4.0, rel=1e-6)
    assert 0.0 <= beam.position_angle_degrees < 180.0


def test_phase_five_budget_decision_gates_every_representative_profile() -> (
    None
):
    """One slow 3,000-square primary profile fails the six-second gate."""
    protocol = _MATRIX._load_protocol(_protocol_path())
    cells = [
        {
            "median_wall_seconds": 5.0,
            "policy_role": "primary",
            "profile": profile,
            "size_pixels": 3000,
        }
        for profile in protocol.profiles
    ]
    assert _MATRIX._budget_decision(cells, protocol)["passed"]
    cells[-1]["median_wall_seconds"] = 6.01

    decision = _MATRIX._budget_decision(cells, protocol)

    assert not decision["passed"]
    assert decision["failed_profiles"] == ["extended"]
