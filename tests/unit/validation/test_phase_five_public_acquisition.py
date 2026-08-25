"""Approved acquisition boundary for Phase 5 public evidence."""

from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
_SCRIPT = _ROOT / "scripts/validation/acquire_phase5_public_artifacts.py"
_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-comparison-scientific-decision.json"
)


def _script() -> dict[str, Any]:
    """Load the acquisition command without invoking network I/O."""
    return runpy.run_path(str(_SCRIPT))


def test_historical_acquisition_rejects_canonicalized_decision() -> None:
    """The sealed acquisition command retains its original byte identity."""
    with pytest.raises(ValueError, match="scientific decision changed"):
        _script()["load_acquisition_decision"](
            _ROOT,
            _DECISION,
        )


def test_public_acquisition_has_exact_canonical_artifacts() -> None:
    """The canonical decision retains all seven acquired requests."""
    acquisition = runpy.run_path(
        str(_ROOT / "scripts/validation/inspect_phase5_public_schemas.py")
    )["load_acquisition_record"](
        _ROOT,
        _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
        "acquisition.json",
    )

    assert len(acquisition["artifacts"]) == 7
    assert (
        sum(artifact["byte_size"] for artifact in acquisition["artifacts"])
        == 15_053_995_875
    )
    assert {
        artifact["dataset_id"] for artifact in acquisition["artifacts"]
    } == {
        "askap-emu-pilot-hydra-2x2",
        "ska-sdc1-mid-band2-1000h",
    }
    assert acquisition["finder_execution_authorized"] is False
    assert acquisition["cutout_selection_authorized"] is False
    assert acquisition["qualification_opened"] is False


def test_public_acquisition_inspection_hashes_complete_files(
    tmp_path: Path,
) -> None:
    """A terminal record requires exact byte sizes and SHA-256 values."""
    namespace = _script()
    request_type = namespace["AcquisitionRequest"]
    requests = (
        request_type("lane-a", "image", "image.fits", "https://a", 3),
        request_type("lane-b", "truth", "truth.txt", "https://b", 4),
    )
    (tmp_path / "image.fits").write_bytes(b"abc")
    (tmp_path / "truth.txt").write_bytes(b"data")

    records = namespace["inspect_acquired_artifacts"](requests, tmp_path)

    assert records[0]["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert records[1]["sha256"] == hashlib.sha256(b"data").hexdigest()
    assert records[1]["byte_size"] == 4


def test_public_acquisition_rejects_partial_or_changed_files(
    tmp_path: Path,
) -> None:
    """A partial artifact cannot be published as acquired evidence."""
    namespace = _script()
    request_type = namespace["AcquisitionRequest"]
    request = request_type(
        "lane-a",
        "image",
        "image.fits",
        "https://a",
        4,
    )
    (tmp_path / "image.fits").write_bytes(b"abc")

    with pytest.raises(ValueError, match="byte size differs"):
        namespace["inspect_acquired_artifacts"]((request,), tmp_path)


def test_public_acquisition_rejects_decision_drift(tmp_path: Path) -> None:
    """A changed URL or authorization record requires renewed review."""
    changed = tmp_path / "decision.json"
    changed.write_text(_DECISION.read_text().replace("/download", "/other", 1))

    with pytest.raises(ValueError, match="scientific decision changed"):
        _script()["load_acquisition_decision"](_ROOT, changed)


def test_public_acquisition_range_segments_are_complete_and_disjoint() -> None:
    """Parallel ranges cover every byte exactly once."""
    bounds = _script()["segment_bounds"](10, segment_count=3)

    assert bounds == ((0, 3), (4, 6), (7, 9))
    assert sum(end - start + 1 for start, end in bounds) == 10
