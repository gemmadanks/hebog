# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""The sector-scaling sweep runs, resumes and records refused runs."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits

_ROOT = Path(__file__).parents[2]
_SWEEP = _ROOT / "scripts/benchmark/profile_scaling.py"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        importlib.util.find_spec("resource") is None,
        reason="stage timing needs the POSIX resource module",
    ),
]


def _configuration(directory: Path) -> Path:
    """Write one small two-source image and a configuration naming it."""
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"], header["CTYPE2"] = "RA---TAN", "DEC--TAN"
    header["CRPIX1"] = header["CRPIX2"] = 97.0
    header["CRVAL1"], header["CRVAL2"] = 180.0, -30.0
    header["CDELT1"], header["CDELT2"] = -1.0 / 3600.0, 1.0 / 3600.0
    header["CUNIT1"] = header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    y, x = np.mgrid[:192, :192]
    values = np.random.default_rng(20261014).normal(0.0, 1.0e-4, (192, 192))
    for row, column in ((48.0, 60.0), (140.0, 120.0)):
        values += 0.01 * np.exp(-((x - column) ** 2 + (y - row) ** 2) / 8.0)
    image = directory / "image.fits"
    fits.PrimaryHDU(data=values, header=header).writeto(image)
    configuration = directory / "configuration.json"
    configuration.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_manifest": "config/datasets/quick-science-check.json",
                "hebog": {
                    "detection_threshold_sigma": 5.0,
                    "island_threshold_sigma": 3.0,
                    "minimum_island_pixels": 7,
                    "profile": "continuum",
                },
                "cases": [
                    {
                        "group": "real",
                        "case": {
                            "case_id": "small",
                            "kind": "image",
                            "image": str(image),
                        },
                    }
                ],
            }
        )
    )
    return configuration


def _sweep(
    directory: Path, configuration: Path, *arguments: str
) -> dict[str, Any]:
    subprocess.run(
        [
            sys.executable,
            str(_SWEEP),
            "--configuration",
            str(configuration),
            "--output-root",
            str(directory / "profiles"),
            "--label",
            "sweep",
            *arguments,
        ],
        check=True,
        capture_output=True,
    )
    report = directory / "profiles/runs/sweep/scaling.json"
    return cast(dict[str, Any], json.loads(report.read_text("utf-8")))


def test_the_sweep_summarises_every_executor_and_resumes(
    tmp_path: Path,
) -> None:
    """Each executor's curve starts at one worker; nothing finished reruns."""
    configuration = _configuration(tmp_path)
    arguments = (
        "--thread-workers",
        "1",
        "2",
        "--dask-workers",
        "1",
        "2",
        "--memory-budget-bytes",
        "4000000000",
    )

    report = _sweep(tmp_path, configuration, *arguments)
    finished = sorted(
        path.stat().st_mtime_ns
        for path in (tmp_path / "profiles/runs/sweep").rglob("case.json")
    )
    again = _sweep(tmp_path, configuration, *arguments)

    assert report["runs"] == {
        "threads": {"workers": [1, 2], "cases": ["small"]},
        "dask": {"workers": [1, 2], "cases": ["small"]},
    }
    for executor in ("threads", "dask"):
        summary = report["cases"]["small"][executor]
        assert [row["workers"] for row in summary["curve"]] == [1, 2]
        assert summary["curve"][0]["speedup"] == 1.0
        assert summary["failures"] == []
        assert summary["amdahl"] is not None
        assert summary["serial_terms"]
    assert again["cases"] == report["cases"]
    assert finished == sorted(
        path.stat().st_mtime_ns
        for path in (tmp_path / "profiles/runs/sweep").rglob("case.json")
    )


def test_the_sweep_can_pair_each_image_with_its_flat_noise(
    tmp_path: Path,
) -> None:
    """With a flat-noise image, every run times its estimate as a stage.

    Rapthor's sectors pair the true-sky image with a flat-noise image of
    the same field, so the sweep uses the input as its own counterpart.
    """
    report = _sweep(
        tmp_path,
        _configuration(tmp_path),
        "--thread-workers",
        "1",
        "--dask-workers",
        "--memory-budget-bytes",
        "4000000000",
        "--with-flat-noise",
    )

    assert report["with_flat_noise"] is True
    (case,) = (tmp_path / "profiles/runs/sweep").rglob("case.json")
    stages = json.loads(case.read_text("utf-8"))["profile"]["stages"]
    assert [
        item["calls"]
        for item in stages
        if item["stage"][-1] == "flat-noise background and RMS"
    ] == [1]


def test_a_refused_run_is_recorded_and_the_sweep_goes_on(
    tmp_path: Path,
) -> None:
    """A budget smaller than any task admits no run, under any executor.

    The Dask workers' 500-byte limits are far below their own memory, so
    this also shows the cluster never pauses or restarts them for it.
    """
    report = _sweep(
        tmp_path,
        _configuration(tmp_path),
        "--thread-workers",
        "1",
        "2",
        "--dask-workers",
        "1",
        "2",
        "--memory-budget-bytes",
        "1000",
    )

    for executor in ("threads", "dask"):
        summary = report["cases"]["small"][executor]
        assert "curve" not in summary
        assert [failure["workers"] for failure in summary["failures"]] == [
            1,
            2,
        ]
        for failure in summary["failures"]:
            assert "ExecutorAdmissionError" in failure["errors"][-1]


def test_an_executor_given_no_worker_counts_is_skipped(tmp_path: Path) -> None:
    report = _sweep(
        tmp_path,
        _configuration(tmp_path),
        "--thread-workers",
        "1",
        "--thread-cases",
        "small",
        "--dask-workers",
        "--memory-budget-bytes",
        "4000000000",
    )

    assert report["runs"] == {"threads": {"workers": [1], "cases": ["small"]}}
    assert set(report["cases"]["small"]) == {"threads"}
