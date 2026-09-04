"""Regression contracts for adaptive-background result recovery."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    AdaptiveExecutorComparison,
    AdaptiveScienceSummary,
    build_adaptive_development_manifest,
)
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_COMPLETION = (
    _ROOT / "scripts/validation/"
    "complete_phase5_adaptive_background_development.py"
)


def _summary() -> AdaptiveScienceSummary:
    return AdaptiveScienceSummary(
        product_valid=True,
        completeness=1.0,
        integrated_flux_absolute_fractional_error=0.0,
        mask_iou=1.0,
        split=False,
        support_recall=1.0,
        background_error_median_rms=0.0,
        background_error_p95_rms=0.0,
        rms_error_median_fraction=0.0,
        rms_error_p95_fraction=0.0,
        source_count=1,
    )


def _observation() -> AdaptiveDevelopmentObservation:
    summary = _summary()
    return AdaptiveDevelopmentObservation(
        input_id="adaptive-development-example",
        cell_id="adaptive-cell-example",
        seed=1,
        trigger_cohort="below",
        pre_adaptive_maximum_sigma=1.0,
        adaptive_candidate_positions_yx=(),
        adaptive_activation_intersects_truth=False,
        adaptive=summary,
        coarse=summary,
    )


def test_completion_parses_the_exact_json_worker_boundary(
    tmp_path: Path,
) -> None:
    """Strict tuples must survive the JSON representation from workers."""
    completion = runpy.run_path(str(_COMPLETION))
    observation = _observation()
    path = tmp_path / "observation.json"
    path.write_text(
        json.dumps(observation.model_dump(mode="json")),
        encoding="utf-8",
    )

    recovered = completion["_load_observation"](path)

    assert recovered == observation
    assert recovered.adaptive_candidate_positions_yx == ()


def test_completion_rejects_non_json_worker_payload(tmp_path: Path) -> None:
    """Recovery must fail closed instead of coercing malformed evidence."""
    completion = runpy.run_path(str(_COMPLETION))
    path = tmp_path / "observation.json"
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid adaptive observation"):
        completion["_load_observation"](path)


def test_completion_runs_only_the_missing_dask_subset(tmp_path: Path) -> None:
    """Recovery must not repeat any of the 288 completed serial runs."""
    completion = runpy.run_path(str(_COMPLETION))
    tasks = completion["_tasks"](build_adaptive_development_manifest())
    summary = _summary()
    observations = tuple(
        AdaptiveDevelopmentObservation(
            input_id=task.input_id,
            cell_id=task.cell.cell_id,
            seed=task.recipe.seed,
            trigger_cohort=task.cell.trigger_cohort,
            pre_adaptive_maximum_sigma=1.0,
            adaptive_candidate_positions_yx=(),
            adaptive_activation_intersects_truth=False,
            adaptive=summary,
            coarse=summary,
        )
        for task in tasks
    )
    compared: list[str] = []

    def compare(
        task: object,
        serial: AdaptiveDevelopmentObservation,
        scratch: Path,
        executor: object,
    ) -> AdaptiveExecutorComparison:
        del task, scratch, executor
        compared.append(serial.input_id)
        return AdaptiveExecutorComparison(
            input_id=serial.input_id,
            serial_science_sha256="1" * 64,
            existing_dask_science_sha256="1" * 64,
        )

    completion["_PARENT"]["_dask_comparison"] = compare

    comparisons = completion["_executor_comparisons"](
        tasks,
        observations,
        tmp_path,
        object(),
    )

    expected = [
        task.input_id
        for task in tasks
        if task.cell.trigger_cohort == "above"
        and task.recipe.seed == task.cell.noise_seeds[0]
    ]
    assert compared == expected
    assert len(comparisons) == 12


def test_completion_fixture_verifies_all_preserved_observations(
    tmp_path: Path,
) -> None:
    """The product seal covers every artifact and manifest-bound record."""
    completion = runpy.run_path(str(_COMPLETION))
    manifest = build_adaptive_development_manifest()
    tasks = completion["_tasks"](manifest)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "progress.log").write_bytes(b"")
    summary = _summary()
    required_files = completion["_REQUIRED_TASK_FILES"]
    for task in tasks:
        directory = scratch / task.input_id
        for relative in required_files:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode())
        observation = AdaptiveDevelopmentObservation(
            input_id=task.input_id,
            cell_id=task.cell.cell_id,
            seed=task.recipe.seed,
            trigger_cohort=task.cell.trigger_cohort,
            pre_adaptive_maximum_sigma=1.0,
            adaptive_candidate_positions_yx=(),
            adaptive_activation_intersects_truth=False,
            adaptive=summary,
            coarse=summary,
        )
        (directory / "observation.json").write_text(
            json.dumps(observation.model_dump(mode="json")),
            encoding="utf-8",
        )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    inspected = completion["inspect_preserved_results"](
        scratch,
        manifest_path,
    )
    inventory, count = completion["_product_inventory"](scratch, tasks)
    observations = completion["_verified_observations"](scratch, tasks)

    assert count == len(required_files) * 144
    assert len(inventory) == count
    assert len(observations) == 144
    assert inspected["artifact_count"] == count
    assert inspected["input_count"] == 144
    assert tuple(item.input_id for item in observations) == tuple(
        task.input_id for task in tasks
    )

    changed = observations[0].model_copy(update={"seed": 0})
    with pytest.raises(ValueError, match="identity or metadata changed"):
        completion["_validate_observation"](changed, tasks[0])


def test_completion_identity_is_non_executable_and_exact() -> None:
    """The repair can be reviewed without inheriting consumed authority."""
    completion = runpy.run_path(str(_COMPLETION))
    identity = json.loads(completion["_IDENTITY_REVIEW"].read_text())

    completion["_verify_completion_identity"](identity)
    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}

    changed = {**identity, "expected_execution_sha256": "0" * 64}
    with pytest.raises(ValueError, match="identity is not frozen"):
        completion["_verify_completion_identity"](changed)


def test_completion_requires_a_new_exact_execution_decision() -> None:
    """The original lane approval cannot authorize recovery execution."""
    completion = runpy.run_path(str(_COMPLETION))
    arguments = SimpleNamespace(execution_decision=None)
    verified = {
        "identity_review_sha256": file_sha256(completion["_IDENTITY_REVIEW"])
    }

    with pytest.raises(PermissionError, match=r"exact.*approval"):
        completion["_verify_execution_authority"](arguments, verified)


def test_completion_requires_exactly_two_matching_dask_workers() -> None:
    """A matching subset cannot hide a missing or extra scheduler worker."""
    completion = runpy.run_path(str(_COMPLETION))
    expected = {"runtime": "exact"}

    class Client:
        def __init__(self, identities: dict[str, object]) -> None:
            self.identities = identities

        def run(self, function: object) -> dict[str, object]:
            del function
            return self.identities

    completion["_verify_existing_dask_runtime"](
        Client({"worker-1": expected, "worker-2": expected}),
        expected,
        2,
    )
    with pytest.raises(ValueError, match="Dask runtime identity changed"):
        completion["_verify_existing_dask_runtime"](
            Client({"worker-1": expected}),
            expected,
            2,
        )
    with pytest.raises(ValueError, match="Dask runtime identity changed"):
        completion["_verify_existing_dask_runtime"](
            Client({"worker-1": expected, "worker-2": {"runtime": "other"}}),
            expected,
            2,
        )
