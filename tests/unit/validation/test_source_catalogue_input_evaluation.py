"""R6 per-input evaluation control tests use no campaign output directory."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import importlib
import json
import runpy
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
)
from hebog.validation.campaign_runtime import phase_four_outlier_thresholds
from hebog.validation.datasets import (
    iter_dataset_recipes,
    load_dataset_manifest,
    recipe_sha256,
)
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
evaluation: Any = importlib.import_module(
    "scripts.validation.source_catalogue_input_evaluation"
)


def test_real_context_loads_only_frozen_population_metadata() -> None:
    context = evaluation.evaluation_context(_ROOT)
    assert len(context["datasets"]) == 5
    assert len(context["recipes"]) == 2400
    assert len(context["specifications"]) == 158


@pytest.mark.parametrize("lane", ("compact-blend", "continuum"))
@pytest.mark.parametrize("defect", (None, "recipe", "finder", "lane"))
def test_input_census_and_recipe_checked_before_measurement(
    monkeypatch: pytest.MonkeyPatch,
    lane: str,
    defect: str | None,
) -> None:
    dataset = build_adaptive_development_manifest().datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]
    context = {
        "recipes": {(dataset.identifier, recipe.seed): recipe},
        "datasets": {dataset.identifier: dataset},
    }
    monkeypatch.setattr(
        evaluation, "evaluation_context", lambda _root: context
    )
    calls = []

    def measure(
        task: dict[str, Any], selected: dict[str, Any]
    ) -> tuple[Any, ...]:
        calls.append(task["lane"])
        assert selected["recipe"] == recipe
        return ({"fixture": True},)

    monkeypatch.setattr(evaluation, "_compact_records", measure)
    monkeypatch.setattr(evaluation, "_continuum_records", measure)
    task: dict[str, Any] = {
        "dataset_identifier": dataset.identifier,
        "seed": recipe.seed,
        "recipe_sha256": recipe_sha256(recipe),
        "lane": lane,
        "captures": {
            finder: {}
            for finder in (
                "current-hebog",
                "incumbent-hebog",
                "released-pybdsf",
                "pinned-pybdsf-master",
            )
        },
    }
    if lane == "compact-blend":
        task["captures"]["aegean"] = {}
    if defect == "recipe":
        task["recipe_sha256"] = "0" * 64
    elif defect == "finder":
        task["captures"].pop("incumbent-hebog")
    elif defect == "lane":
        task["lane"] = "unapproved-lane"
    if defect is None:
        assert evaluation.evaluate_captured_input(task, _ROOT) == (
            {"fixture": True},
        )
        assert calls == [lane]
    else:
        with pytest.raises(
            ValueError, match=r"recipe|finder census|unsupported"
        ):
            evaluation.evaluate_captured_input(task, _ROOT)
        assert not calls


@pytest.mark.parametrize("defect", (None, "manifest-hash", "duplicate-role"))
def test_native_manifest_verification_has_no_finder_side_effects(
    tmp_path: Path,
    defect: str | None,
) -> None:
    artifact = tmp_path / "native.json"
    artifact.write_text("[]\n")
    row = {
        "relative_path": artifact.name,
        "role": "catalogue",
        "byte_count": artifact.stat().st_size,
        "sha256": file_sha256(artifact),
    }
    manifest = tmp_path / "complete.json"
    manifest.write_text(
        json.dumps(
            {"artifacts": [row] * (2 if defect == "duplicate-role" else 1)}
        )
    )
    digest = "0" * 64 if defect == "manifest-hash" else file_sha256(manifest)
    if defect is None:
        assert evaluation.native_artifacts(manifest, digest) == {
            "catalogue": artifact
        }
    else:
        with pytest.raises(ValueError, match=r"changed|duplicated"):
            evaluation.native_artifacts(manifest, digest)


@pytest.mark.parametrize("changed_capture", (False, True))
def test_compact_input_retains_real_diagnostics_for_all_finders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_capture: bool,
) -> None:
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-4r-development.json"
    ).datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]
    path = tmp_path / "capture.json"
    path.write_text("{}\n")
    task: dict[str, Any] = {
        "input_id": "compact-fixture",
        "captures": {
            finder: {"path": str(path), "sha256": file_sha256(path)}
            for finder in (
                "current-hebog",
                "incumbent-hebog",
                "released-pybdsf",
                "pinned-pybdsf-master",
                "aegean",
            )
        },
    }
    if changed_capture:
        task["captures"]["current-hebog"]["sha256"] = "0" * 64
    monkeypatch.setattr(
        evaluation,
        "read_current_capture",
        lambda _path: ({"catalogues": {"published-components": {}}}, None),
    )
    monkeypatch.setattr(evaluation, "checked_artifact", lambda *_args: path)
    monkeypatch.setattr(
        evaluation,
        "native_artifacts",
        lambda *_args: dict.fromkeys(
            (
                "compact-catalogue-json",
                "gaussian-catalogue-fits",
                "component-catalogue-fits",
                "island-catalogue-fits",
            ),
            path,
        ),
    )
    monkeypatch.setattr(
        evaluation, "load_comparison_catalogue", lambda *_args: ()
    )
    monkeypatch.setattr(
        evaluation, "load_pybdsf_gaussian_catalogue", lambda *_args: ()
    )
    monkeypatch.setattr(evaluation, "load_aegean_catalogue", lambda *_args: ())
    context = {
        "dataset": dataset,
        "recipe": recipe,
        "outliers": phase_four_outlier_thresholds(
            _ROOT / "config/contracts/phase-4-scientific-gates.json"
        ),
        "minimum_axis_ratio": 1.1,
    }
    if changed_capture:
        with pytest.raises(ValueError, match="manifest changed"):
            evaluation._compact_records(task, context)
    else:
        records = evaluation._compact_records(task, context)
        assert len(records) == 5
        for record in records:
            diagnostic = record["compact_diagnostic"]
            assert diagnostic["candidate_count"] == 0
            assert diagnostic["status"] == "success"
            assert len(diagnostic["association_pairs"]) == len(
                dataset.association_truth_groups
            )
            assert all(
                row["decision"] == "unmatched-truth-group"
                for row in diagnostic["association_pairs"]
            )


def test_failed_native_run_cannot_be_presented_as_success(
    tmp_path: Path,
) -> None:
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps(
            {"status": "failed", "failure": "fit failed", "artifacts": []}
        )
    )
    with pytest.raises(ValueError, match="native run did not succeed"):
        evaluation.native_artifacts(path, file_sha256(path))


@pytest.mark.parametrize("changed_capture", (False, True))
def test_continuum_input_keeps_truth_and_native_capture_per_finder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_capture: bool,
) -> None:
    fixtures = runpy.run_path(
        str(Path(__file__).with_name("test_source_measurement_evidence.py"))
    )
    batch = fixtures["source_evidence_fixture"]().diagnostics
    image_paths = {}
    for role, values in (
        ("image", np.zeros(batch.truth_labels.shape)),
        ("mean", np.zeros(batch.truth_labels.shape)),
        ("rms", np.ones(batch.truth_labels.shape)),
    ):
        path = tmp_path / f"{role}.fits"
        fits.PrimaryHDU(values).writeto(path)
        image_paths[role] = path
    manifest = tmp_path / "input.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "role": role,
                        "relative_path": path.name,
                        "sha256": file_sha256(path),
                        "byte_count": path.stat().st_size,
                    }
                    for role, path in image_paths.items()
                ]
            }
        )
    )
    binding = {"path": str(manifest), "sha256": file_sha256(manifest)}
    task: dict[str, Any] = {
        "input_id": batch.input_id,
        "input_manifest": binding,
        "captures": {
            finder: dict(binding)
            for finder in (
                "current-hebog",
                "incumbent-hebog",
                "released-pybdsf",
                "pinned-pybdsf-master",
            )
        },
    }
    if changed_capture:
        task["captures"]["current-hebog"]["sha256"] = "0" * 64

    class Truth:
        records: ClassVar[list[dict[str, str]]] = [
            {"fixture": "observable-truth"}
        ]

        def __call__(self, *_args: Any) -> tuple[Any, Any]:
            return batch.truth, batch.truth_labels

    monkeypatch.setattr(
        evaluation, "ObservableTruthCompiler", lambda _namespace: Truth()
    )
    view = SimpleNamespace(
        sources=batch.sources,
        union_labels=batch.source_union_labels,
        publication=batch.stage_masks["publication"],
        stages=batch.stage_masks,
        background=np.zeros(batch.truth_labels.shape),
        rms=np.ones(batch.truth_labels.shape),
        dispositions=batch.dispositions,
        measured_sources=(),
        measured_components=(),
    )
    reference = SimpleNamespace(
        **{
            **vars(view),
            "sources": tuple(
                replace(row, integrated_flux_jy=6.0) for row in view.sources
            ),
        }
    )
    monkeypatch.setattr(
        evaluation, "read_current_capture", lambda _path: ({}, view)
    )
    monkeypatch.setattr(
        evaluation, "read_incumbent_sources", lambda *_args: reference
    )
    monkeypatch.setattr(
        evaluation, "read_pybdsf_sources", lambda *_args: reference
    )
    context = {
        "dataset": SimpleNamespace(
            beam=SimpleNamespace(major_fwhm_pixels=2.0)
        ),
        "recipe": object(),
        "review": object(),
        "specifications": tuple(
            spec
            for spec in evaluation.evaluation_context(_ROOT)["specifications"]
            if spec.stratum == "overall"
        ),
    }
    if changed_capture:
        with pytest.raises(ValueError, match="manifest changed"):
            evaluation._continuum_records(task, context)
    else:
        records = evaluation._continuum_records(task, context)
        assert len(records) == 4
        for record in records:
            assert record["capture"] == binding
            assert record["diagnostic_units"] == {
                "background_error": "Jy/beam",
                "relative_rms_error": "fraction",
            }
            assert record["observable_truth_support"] == Truth.records
            expected = 0.0 if record["finder_id"] == "current-hebog" else -0.4
            assert record["source_diagnostics"][
                "signed_measurement_residuals"
            ][0]["flux_fraction"] == pytest.approx(expected)
