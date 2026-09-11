"""Small synthetic checks for the exact R6 public capture path."""

# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import io
import json
import runpy
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from distributed import Client, LocalCluster

from hebog.config import SourceFinderConfig
from hebog.executors import SerialExecutor
from hebog.executors.dask import DaskExecutor
from hebog.validation.external_runners import file_sha256
from hebog.validation.products import load_fits_plane

_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_ROOT))
worker: Any = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_worker"
)
capture_current_image = worker.capture_current_image
retained: Any = importlib.import_module(
    "scripts.validation.source_catalogue_retained_measurements"
)


@pytest.mark.integration
@pytest.mark.parametrize("empty", (False, True))
def test_current_capture_retains_products_before_evaluation(
    tmp_path: Path,
    empty: bool,
) -> None:
    helpers: dict[str, Any] = runpy.run_path(
        str(Path(__file__).with_name("test_public_notebook_runner.py"))
    )
    image = helpers["_geometry_matrix_image"]()
    if empty:
        image[:] = 0.0
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(image, helpers["_header"](image.shape)).writeto(path)
    output = tmp_path / "capture"
    record = capture_current_image(
        path,
        output,
        input_id="synthetic-r6",
        config=SourceFinderConfig(5.0, 3.0, 7),
        executor=SerialExecutor(),
    )
    assert json.loads((output / "capture.json").read_bytes()) == record
    assert record["input_id"] == "synthetic-r6"
    assert record["finder_id"] == "current-hebog"
    assert record["input_sha256"] == file_sha256(path)
    assert record["source_count"] == (0 if empty else len(record["sources"]))
    assert (record["source_count"] > 0) is not empty
    for binding in record["planes"].values():
        plane_path = output / binding["path"]
        assert file_sha256(plane_path) == binding["sha256"]
        assert load_fits_plane(plane_path).shape == image.shape
    publication = load_fits_plane(
        output / record["planes"]["publication"]["path"]
    )
    owners = load_fits_plane(output / record["planes"]["source-union"]["path"])
    assert not np.any((owners > 0) & (publication == 0))
    assert record["measurement_dispositions"] or empty
    restored, view = retained.read_current_capture(output / "capture.json")
    assert restored == record
    assert np.array_equal(view.union_labels, owners)
    assert len(view.sources) == record["source_count"]
    assert len(view.measured_components) == len(record["measured_components"])
    # The public bundle remains independently readable after capture, and a
    # duplicate cannot overwrite either product or pre-evaluation evidence.
    with pytest.raises(FileExistsError):
        capture_current_image(
            path,
            output,
            input_id="synthetic-r6",
            config=SourceFinderConfig(5.0, 3.0, 7),
            executor=SerialExecutor(),
        )


@pytest.mark.integration
def test_failed_public_capture_restores_analysis_and_preserves_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = worker.public_api._analyse_image

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("injected finder failure")

    monkeypatch.setattr(worker.public_api, "find_sources", fail)
    output = tmp_path / "failed-capture"
    with pytest.raises(RuntimeError, match="injected finder"):
        capture_current_image(
            tmp_path / "unused.fits",
            output,
            input_id="failure-fixture",
            config=SourceFinderConfig(5.0, 3.0, 7),
            executor=SerialExecutor(),
        )
    assert worker.public_api._analyse_image is original
    assert output.is_dir()
    assert not (output / "capture.json").exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    "corruption", ("source-count", "component-count", "mask")
)
def test_capture_rejects_projection_disagreement_without_erasing_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    helpers = runpy.run_path(
        str(Path(__file__).with_name("test_public_notebook_runner.py"))
    )
    image = helpers["_geometry_matrix_image"]()
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(image, helpers["_header"](image.shape)).writeto(path)
    original = worker.public_api.find_sources

    def inconsistent(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if corruption == "mask":
            fits.PrimaryHDU(np.zeros(image.shape)).writeto(
                result.mask.path, overwrite=True
            )
            return result
        field = (
            "source_count"
            if corruption == "source-count"
            else "gaussian_component_count"
        )
        return result.model_copy(update={field: getattr(result, field) + 1})

    monkeypatch.setattr(worker.public_api, "find_sources", inconsistent)
    output = tmp_path / "capture"
    with pytest.raises(ValueError, match="differs"):
        capture_current_image(
            path,
            output,
            input_id="projection-fixture",
            config=SourceFinderConfig(5.0, 3.0, 7),
            executor=SerialExecutor(),
        )
    assert (output / "public").is_dir()
    assert not (output / "capture.json").exists()


@pytest.mark.integration
@pytest.mark.parametrize("oversampled", (False, True))
def test_capture_science_identity_is_serial_existing_dask_invariant(
    tmp_path: Path,
    oversampled: bool,
) -> None:
    helpers = runpy.run_path(
        str(Path(__file__).with_name("test_public_notebook_runner.py"))
    )
    image = helpers["_geometry_matrix_image"]()
    header = helpers["_header"](image.shape)
    if oversampled:
        yy, xx = np.indices((49, 57), dtype=float)
        image = 100 * np.exp(
            -0.5 * (((xx - 28.3) / 3.3) ** 2 + ((yy - 24.7) / 3.0) ** 2)
        )
        image += 0.1 * (np.sin(2 * xx + 0.3 * yy) + np.cos(1.3 * yy))
        header = helpers["_header"](image.shape)
        header["BMAJ"] = header["BMIN"] = 7.0 / 3600.0
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(image, header).writeto(path)
    config = SourceFinderConfig(5.0, 3.0, 7)
    serial = tmp_path / "serial"
    record = capture_current_image(
        path,
        serial,
        input_id="invariance-fixture",
        config=config,
        executor=SerialExecutor(),
    )
    if oversampled:
        components = [
            row
            for row in record["measurement_dispositions"]
            if row["object_kind"] == "component"
        ]
        assert len(components) == 1
        assert components[0]["catalogue_row_published"]
        fit = components[0]["fit_diagnostics"]
        assert fit["point_estimator"] == "diagonal-weighted"
        assert fit["point_estimator_fallback_reason"] in {
            "correlation-factorization-failed",
            "correlation-ill-conditioned",
        }
        assert record["source_count"] == 1
        assert len(record["components"]) == 1
        np.testing.assert_allclose(
            record["components"][0]["centre_xy"], (28.3, 24.7), atol=0.1
        )
        publication = load_fits_plane(
            serial / record["planes"]["publication"]["path"]
        )
        assert publication[25, 28] > 0
    expected = retained.capture_science_sha256(serial / "capture.json")
    with (
        LocalCluster(
            n_workers=2,
            threads_per_worker=1,
            processes=True,
            dashboard_address="127.0.0.1:0",
        ) as cluster,
        Client(cluster) as client,
    ):
        parallel = tmp_path / "dask"
        capture_current_image(
            path,
            parallel,
            input_id="invariance-fixture",
            config=config,
            executor=DaskExecutor(client),
        )
    assert (
        retained.capture_science_sha256(parallel / "capture.json") == expected
    )


@pytest.mark.integration
@pytest.mark.parametrize("mismatch", (False, True))
def test_two_spawned_captures_and_existing_dask_reach_the_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: bool,
) -> None:
    runner: Any = importlib.import_module(
        "scripts.validation.run_source_catalogue_cumulative_replay"
    )
    execution: Any = importlib.import_module(
        "scripts.validation.source_catalogue_campaign_execution"
    )
    helpers = runpy.run_path(
        str(Path(__file__).with_name("test_public_notebook_runner.py"))
    )
    image = helpers["_geometry_matrix_image"]()
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(image, helpers["_header"](image.shape)).writeto(path)
    manifest = tmp_path / "input.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "role": "image",
                        "relative_path": path.name,
                        "sha256": file_sha256(path),
                        "byte_count": path.stat().st_size,
                    }
                ]
            }
        )
    )
    tasks = [
        {
            "input_id": f"spawned-{index}",
            "output_directory": str(tmp_path / f"serial-{index}"),
            "configuration": asdict(SourceFinderConfig(5.0, 3.0, 7)),
            "input_manifest": {
                "path": str(manifest),
                "sha256": file_sha256(manifest),
            },
        }
        for index in range(2)
    ]
    progress = io.StringIO()
    outputs = runner._run_stage(
        "fixture", tasks, execution.capture_current_task, progress
    )
    captures = {
        json.loads(Path(row["path"]).read_bytes())["input_id"]: row
        for row in outputs
    }
    assert len(captures) == 2
    assert "completed=2/2" in progress.getvalue()
    plan = {
        "dask_input_ids": [row["input_id"] for row in tasks],
        "scratch": str(tmp_path),
        "configuration": tasks[0]["configuration"],
    }
    pairs = [
        {**row, "captures": {"current-hebog": captures[row["input_id"]]}}
        for row in tasks
    ]
    original = runner.capture_science_sha256

    def science_hash(path: Path) -> str:
        observed = original(path)
        return "0" * 64 if mismatch and "dask" in path.parts else observed

    monkeypatch.setattr(runner, "capture_science_sha256", science_hash)
    results = runner.compare_existing_dask(plan, pairs, progress)
    assert len(results) == 2
    assert all(row["pass"] is not mismatch for row in results)
    assert (
        json.loads((tmp_path / "dask-comparisons.json").read_bytes())[
            "comparisons"
        ]
        == results
    )
