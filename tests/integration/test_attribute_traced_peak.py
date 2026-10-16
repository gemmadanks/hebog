# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Traced-peak attribution runner contract over a complete run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from astropy.io import fits
from conftest import (
    radio_header,
    two_source_image,
)

_ROOT = Path(__file__).parents[2]
_RUNNER = _ROOT / "scripts/benchmark/attribute_traced_peak.py"
_SETTINGS = {
    "detection_threshold_sigma": 5.0,
    "island_threshold_sigma": 3.0,
    "minimum_island_pixels": 7,
    "profile": "continuum",
}

pytestmark = pytest.mark.integration


def test_the_peak_is_attributed_to_passes_tasks_and_call_sites(
    tmp_path: Path,
) -> None:
    """One traced run names where its peak lies and what the pass held.

    The run's own call is the outermost measured path, so its peak is the
    largest; each serial task nests under the pass that submitted it; and
    the largest entry inside the multiscale pass is reduced to call sites.
    """
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(
        data=two_source_image(), header=radio_header((192, 192))
    ).writeto(image)
    result = tmp_path / "attribution.json"

    subprocess.run(
        [
            sys.executable,
            str(_RUNNER),
            "--input",
            str(image),
            "--result",
            str(result),
            "--settings",
            json.dumps(_SETTINGS),
            "--frames",
            "4",
        ],
        check=True,
        capture_output=True,
    )

    record = cast(dict[str, Any], json.loads(result.read_text("utf-8")))
    assert record["source_count"] == 2
    assert record["import_bytes"] > 0
    spans = record["spans"]
    assert spans[0]["path"] == ["find_sources"]
    assert all(span["peak_bytes"] <= spans[0]["peak_bytes"] for span in spans)
    task_paths = [
        span["path"] for span in spans if span["path"][-1][:5] == "task "
    ]
    assert any("detect_multiscale_products" in path for path in task_paths)
    largest = record["largest_entry"]
    assert "detect_multiscale_products" in largest["path"][:-1]
    assert largest["bytes"] > record["import_bytes"]
    assert largest["sites"]
    assert all(site["bytes"] > 0 for site in largest["sites"])
