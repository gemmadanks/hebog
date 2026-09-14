"""Truth-first evaluation of one complete, retained R6 input.

This module has no finder execution entry point. Late evaluation can be
repaired independently of the already captured scientific products.
"""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits
from scripts.validation import source_catalogue_campaign_evidence as evidence
from scripts.validation.compile_phase5_external_post_failure_campaign import (
    ObservableTruthCompiler,
)
from scripts.validation.source_catalogue_campaign_worker import (
    compile_continuum_record,
)
from scripts.validation.source_catalogue_retained_measurements import (
    FinderMeasurementView,
    checked_artifact,
    read_current_capture,
    read_incumbent_sources,
    read_pybdsf_sources,
)

from hebog.validation.datasets import recipe_sha256
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.post_campaign_science import (
    diagnose_compact_component_realization,
)
from hebog.validation.products import (
    load_aegean_catalogue,
    load_comparison_catalogue,
    load_fits_plane,
    load_pybdsf_gaussian_catalogue,
)
from hebog.validation.source_catalogue_diagnostics import SourceDiagnosticInput


@lru_cache(maxsize=1)
def evaluation_context(root: Path) -> dict[str, Any]:
    """Load small immutable manifest metadata once per worker, not images."""
    registry, _ = evidence.load_cumulative_policy(root)
    compiler = evidence.compiler
    compact, compact_recipes = compiler._dataset_maps(
        root / registry["compact_manifest_path"]
    )
    continuum, continuum_recipes = compiler._dataset_maps(
        root / registry["continuum_manifest_path"]
    )
    return {
        "registry": registry,
        "datasets": {**compact, **continuum},
        "recipes": {**compact_recipes, **continuum_recipes},
        "review": compiler.load_phase_five_corrective_a_review(
            root / registry["phase_five_review_path"]
        ),
        "specifications": compiler.expand_continuum_endpoint_specs(registry),
        "outliers": compiler.phase_four_outlier_thresholds(
            root / registry["phase_four_gates_path"]
        ),
        "minimum_axis_ratio": json.loads(
            (root / registry["phase_four_measurement_path"]).read_bytes()
        )["eligibility"]["position_angle_minimum_axis_ratio"],
    }


def native_artifacts(path: Path, expected_sha256: str) -> dict[str, Path]:
    """Verify an immutable native result/complete manifest and every file."""
    if path.is_symlink() or file_sha256(path) != expected_sha256:
        raise ValueError("native product manifest changed")
    record = json.loads(path.read_bytes())
    if "status" in record and record["status"] != "success":
        raise ValueError("native run did not succeed; preserve its failure")
    output: dict[str, Path] = {}
    for row in record["artifacts"]:
        if row["role"] in output:
            raise ValueError("native artifact role is duplicated")
        output[row["role"]] = checked_artifact(
            path.parent,
            {
                "path": row["relative_path"],
                "sha256": row["sha256"],
                "byte_count": row["byte_count"],
            },
        )
    return output


def _compact_records(
    task: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    """Diagnose real components without peak-as-total source substitution."""
    captures = task["captures"]
    current = Path(captures["current-hebog"]["path"])
    if file_sha256(current) != captures["current-hebog"]["sha256"]:
        raise ValueError("current capture manifest changed")
    captured, _ = read_current_capture(current)
    catalogues = {
        "current-hebog": load_comparison_catalogue(
            checked_artifact(
                current.parent, captured["catalogues"]["published-components"]
            )
        )
    }
    for finder, binding in captures.items():
        if finder == "current-hebog":
            continue
        artifacts = native_artifacts(Path(binding["path"]), binding["sha256"])
        if finder == "incumbent-hebog":
            rows = load_comparison_catalogue(
                artifacts["compact-catalogue-json"]
            )
        elif finder == "aegean":
            rows = load_aegean_catalogue(
                artifacts["component-catalogue-fits"],
                artifacts["island-catalogue-fits"],
            )
        else:
            rows = load_pybdsf_gaussian_catalogue(
                artifacts["gaussian-catalogue-fits"]
            )
        catalogues[finder] = rows
    output = []
    for finder, rows in catalogues.items():
        diagnostic = diagnose_compact_component_realization(
            context["dataset"],
            context["recipe"],
            rows,
            implementation_identifier=finder,
            outlier_thresholds=context["outliers"],
            position_angle_minimum_axis_ratio=context["minimum_axis_ratio"],
        )
        record = {
            "schema_version": 1,
            "lane": "compact-blend",
            "input_id": task["input_id"],
            "finder_id": finder,
            "compact_diagnostic": diagnostic.model_dump(mode="json"),
            "native_components": [asdict(row) for row in rows],
            "capture": captures[finder],
        }
        record["record_sha256"] = canonical_sha256(record)
        output.append(record)
    return tuple(output)


def _continuum_records(
    task: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    """Reuse observable injected truth for each independent finder view."""
    inputs = native_artifacts(
        Path(task["input_manifest"]["path"]), task["input_manifest"]["sha256"]
    )
    image, mean, rms = (
        load_fits_plane(inputs[role]) for role in ("image", "mean", "rms")
    )
    valid = np.isfinite(image) & np.isfinite(mean) & np.isfinite(rms)
    header = cast(fits.Header, fits.getheader(inputs["image"]))
    truth_compiler = ObservableTruthCompiler(dict(vars(evidence.compiler)))
    truth, truth_labels = truth_compiler(
        context["dataset"], context["recipe"], valid, context["review"]
    )
    output = []
    for finder, binding in task["captures"].items():
        path = Path(binding["path"])
        if file_sha256(path) != binding["sha256"]:
            raise ValueError("finder capture manifest changed")
        view: FinderMeasurementView
        if finder == "current-hebog":
            _, view = read_current_capture(path)
        elif finder == "incumbent-hebog":
            view = read_incumbent_sources(
                native_artifacts(path, binding["sha256"]), header
            )
        else:
            view = read_pybdsf_sources(
                native_artifacts(path, binding["sha256"]), header
            )
        diagnostic = SourceDiagnosticInput(
            input_id=task["input_id"],
            finder_id=finder,
            truth=truth,
            sources=view.sources,
            truth_labels=truth_labels,
            source_union_labels=view.union_labels,
            stage_masks=view.stages,
            background_error=view.background - mean,
            relative_rms_error=np.divide(
                view.rms - rms,
                rms,
                out=np.full(rms.shape, np.nan),
                where=rms > 0,
            ),
            valid_pixels=valid,
            beam_fwhm_pixels=context["dataset"].beam.major_fwhm_pixels,
            dispositions=view.dispositions,
            measured_sources=view.measured_sources,
            measured_components=view.measured_components,
        )
        record = compile_continuum_record(
            diagnostic, view.publication, context["specifications"]
        )
        record["observable_truth_support"] = truth_compiler.records
        record["diagnostic_units"] = {
            "background_error": "Jy/beam",
            "relative_rms_error": "fraction",
        }
        record["capture"] = binding
        record["record_sha256"] = canonical_sha256(
            {k: v for k, v in record.items() if k != "record_sha256"}
        )
        output.append(record)
    return tuple(output)


def evaluate_captured_input(
    task: dict[str, Any], root: Path
) -> tuple[dict[str, Any], ...]:
    """Evaluate a complete paired input without invoking either finder."""
    context = evaluation_context(root)
    recipe_key = task["dataset_identifier"], task["seed"]
    recipe = context["recipes"][recipe_key]
    if recipe_sha256(recipe) != task["recipe_sha256"]:
        raise ValueError("evaluation recipe identity changed")
    expected_finders = {
        "current-hebog",
        "incumbent-hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
    }
    if task["lane"] == "compact-blend":
        expected_finders.add("aegean")
    elif task["lane"] != "continuum":
        raise ValueError("evaluation lane is unsupported")
    if set(task["captures"]) != expected_finders:
        raise ValueError("evaluation finder census changed")
    selected = {
        **context,
        "recipe": recipe,
        "dataset": context["datasets"][task["dataset_identifier"]],
    }
    return (
        _compact_records
        if task["lane"] == "compact-blend"
        else _continuum_records
    )(task, selected)
