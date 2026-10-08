"""Contracts of the complete-execution profile's timing and cost model."""

from __future__ import annotations

import importlib.util
import json
import math
import runpy
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.validation.datasets import (
    DatasetManifest,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.execution_profile import (
    IMPORTS_STAGE,
    OVERHEAD_STAGE,
    PROCESS_STAGE,
    ProfiledCase,
    StageRecorder,
    compare_with_model,
    current_peak_rss_bytes,
    fit_stage_cost_models,
    install_stage_timers,
    load_profile_configuration,
    process_wall_seconds_by_stage,
    stage_records,
    task_occupancy_by_stage,
    top_self_time,
)

_ROOT = Path(__file__).parents[3]
_CONFIGURATION = _ROOT / "config/benchmarks/complete-execution-profile.json"
_MANIFEST = _ROOT / "config/datasets/complete-execution-profile.json"
_BUILDER = _ROOT / "scripts/benchmark/build_profile_datasets.py"
_WORKER = _ROOT / "scripts/benchmark/profile_complete_execution_worker.py"
_POSIX_USAGE = importlib.util.find_spec("resource") is not None
_needs_usage = pytest.mark.skipif(
    not _POSIX_USAGE,
    reason="stage timing needs the POSIX resource module",
)


def _busy(seconds: float) -> None:
    """Spend at least ``seconds`` of wall and CPU time."""
    from time import perf_counter  # noqa: PLC0415

    deadline = perf_counter() + seconds
    while perf_counter() < deadline:
        pass


@_needs_usage
def test_nested_stages_report_time_under_their_parent() -> None:
    recorder = StageRecorder()
    with recorder.stage("parent"):
        for _ in range(2):
            with recorder.stage("child"):
                _busy(0.01)
        _busy(0.01)
    records = {record.stage: record for record in recorder.records()}
    parent = records[("parent",)]
    child = records[("parent", "child")]
    assert child.calls == 2
    assert parent.calls == 1
    assert parent.wall_seconds >= child.wall_seconds
    assert parent.self_wall_seconds == pytest.approx(
        parent.wall_seconds - child.wall_seconds
    )
    assert parent.self_cpu_seconds == pytest.approx(
        parent.cpu_seconds - child.cpu_seconds
    )
    assert child.self_wall_seconds == pytest.approx(child.wall_seconds)


@_needs_usage
def test_stage_records_survive_the_worker_result_document() -> None:
    """The driver rebuilds stages from the worker's JSON, so both agree."""
    recorder = StageRecorder()
    with recorder.stage("parent"), recorder.stage("child"):
        _busy(0.001)
    original = recorder.records()
    restored = stage_records([record.document() for record in original])
    assert restored == original


@_needs_usage
def test_repeated_calls_accumulate_into_one_stage() -> None:
    recorder = StageRecorder()
    for _ in range(3):
        with recorder.stage("repeated"):
            _busy(0.001)
    (record,) = recorder.records()
    assert record.calls == 3
    assert record.wall_seconds > 0.0


@_needs_usage
def test_each_call_is_recorded_on_the_wall_clock() -> None:
    """Calls carry ``time.time`` bounds, the clock Dask stamps tasks with."""
    from time import time  # noqa: PLC0415

    recorder = StageRecorder()
    before = time()
    for _ in range(2):
        with recorder.stage("parent"), recorder.stage("child"):
            _busy(0.001)
    after = time()

    intervals = recorder.intervals()

    assert set(intervals) == {("parent",), ("parent", "child")}
    child_calls = intervals[("parent", "child")]
    parent_calls = intervals[("parent",)]
    assert len(child_calls) == len(parent_calls) == 2
    for (child_start, child_stop), (parent_start, parent_stop) in zip(
        child_calls, parent_calls, strict=True
    ):
        assert before <= parent_start <= child_start <= child_stop
        assert child_stop <= parent_stop <= after


def test_task_time_counts_only_the_overlap_with_each_call() -> None:
    """A task straddling a call's edge contributes only its overlap."""
    (occupancy,) = task_occupancy_by_stage(
        {("stage",): ((5.0, 15.0), (20.0, 22.0))},
        ((0.0, 10.0), (12.0, 21.0), (30.0, 40.0)),
        worker_count=1,
    )

    # 5 s of the first task, 3 + 1 s of the second, none of the third.
    assert occupancy.task_seconds == pytest.approx(9.0)
    assert occupancy.worker_occupancy == pytest.approx(9.0 / 12.0)


def test_task_time_keeps_its_precision_at_epoch_timestamps() -> None:
    """Dask stamps tasks in epoch seconds, about 1.8e9 each.

    Running sums of ten thousand raw epoch values would carry errors of
    milliseconds; measured from the earliest instant, the stage's task time
    equals the exact sum of each task's own duration.
    """
    epoch = 1.8e9
    tasks = tuple(
        (epoch + index * 0.01, epoch + index * 0.01 + 0.001)
        for index in range(10_000)
    )

    (occupancy,) = task_occupancy_by_stage(
        {("run",): ((epoch - 1.0, epoch + 101.0),)},
        tasks,
        worker_count=1,
    )

    assert occupancy.task_count == 10_000
    assert occupancy.task_seconds == pytest.approx(
        math.fsum(stop - start for start, stop in tasks), abs=1e-6
    )


def test_a_task_is_counted_in_the_stage_it_starts_in() -> None:
    occupancies = task_occupancy_by_stage(
        {("first",): ((0.0, 10.0),), ("second",): ((10.5, 20.0),)},
        ((1.0, 12.0), (2.0, 3.0), (11.0, 19.0)),
        worker_count=2,
    )

    counts = {item.stage: item.task_count for item in occupancies}
    assert counts == {("first",): 2, ("second",): 1}
    second = next(item for item in occupancies if item.stage == ("second",))
    # 1.5 s of the long first task and all 8 s of the third, on 2 workers.
    assert second.task_seconds == pytest.approx(9.5)
    assert second.worker_occupancy == pytest.approx(9.5 / (9.5 * 2))


def test_overlapping_task_records_count_no_more_busy_workers_than_exist() -> (
    None
):
    """A single-threaded worker's tasks can be recorded overlapping.

    Each Dask worker adds its latest heartbeat estimate of its clock's
    offset from the scheduler's to every task time it reports. The estimate
    changes at each heartbeat, so a worker's next task can be stamped as
    starting before its previous one stopped: here the first worker's two
    tasks overlap from 9 to 10 s, when three tasks appear to run on two
    workers. Task time keeps every task's whole duration, but no more
    workers count as busy than there are.
    """
    occupancies = task_occupancy_by_stage(
        {("overlap",): ((8.0, 12.0),), ("longer",): ((8.0, 16.0),)},
        # The first worker's two tasks, then the second worker's one.
        ((0.0, 10.0), (9.0, 20.0), (0.0, 12.0)),
        worker_count=2,
    )

    by_stage = {item.stage: item for item in occupancies}
    overlap, longer = by_stage[("overlap",)], by_stage[("longer",)]
    # 2 + 3 + 2 * 2 s of tasks in 4 s, with both workers busy throughout.
    assert overlap.task_seconds == pytest.approx(9.0)
    assert overlap.worker_occupancy == 1.0
    # From 12 to 16 s only the first worker is busy: 8 + 4 of 2 * 8 s.
    assert longer.task_seconds == pytest.approx(13.0)
    assert longer.worker_occupancy == pytest.approx(12.0 / 16.0)


_WHOLE_SECONDS = st.integers(min_value=0, max_value=1_000)
_INTERVALS = st.tuples(_WHOLE_SECONDS, _WHOLE_SECONDS).map(
    lambda pair: (float(min(pair)), float(max(pair)))
)


@given(
    tasks=st.lists(_INTERVALS, max_size=20),
    calls=st.lists(_INTERVALS, min_size=1, max_size=4),
    worker_count=st.integers(min_value=1, max_value=4),
)
def test_occupancy_is_a_share_whatever_the_task_records(
    tasks: list[tuple[float, float]],
    calls: list[tuple[float, float]],
    worker_count: int,
) -> None:
    """Occupancy lies in [0, 1] however the task records overlap.

    Whole seconds keep every sum exact, so the bound is the construction's,
    not a tolerance for rounding.
    """
    (occupancy,) = task_occupancy_by_stage(
        {("stage",): tuple(calls)}, tuple(tasks), worker_count=worker_count
    )

    assert 0.0 <= occupancy.worker_occupancy <= 1.0


def test_a_stage_without_tasks_or_wall_time_reports_zero() -> None:
    occupancies = task_occupancy_by_stage(
        {("idle",): ((0.0, 5.0),), ("instant",): ((1.0, 1.0),)},
        (),
        worker_count=4,
    )

    assert [item.document() for item in occupancies] == [
        {
            "stage": ["idle"],
            "task_count": 0,
            "task_seconds": 0.0,
            "worker_occupancy": 0.0,
        },
        {
            "stage": ["instant"],
            "task_count": 0,
            "task_seconds": 0.0,
            "worker_occupancy": 0.0,
        },
    ]


@pytest.mark.parametrize(
    ("stages", "tasks", "workers", "message"),
    [
        ({("s",): ((0.0, 1.0),)}, (), 0, "worker_count"),
        ({("s",): ((2.0, 1.0),)}, (), 1, "ends before"),
        ({("s",): ((0.0, 1.0),)}, ((3.0, 2.0),), 1, "ends before"),
    ],
)
def test_task_attribution_refuses_invalid_inputs(
    stages: dict[tuple[str, ...], tuple[tuple[float, float], ...]],
    tasks: tuple[tuple[float, float], ...],
    workers: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        task_occupancy_by_stage(stages, tasks, worker_count=workers)


@_needs_usage
def test_timers_wrap_every_module_binding_of_one_function() -> None:
    """A stage must be timed wherever the public path calls it.

    ``evaluate_residual_atrous`` is called through the bindings of
    ``hebog.public_science``, ``hebog.science.continuum`` and
    ``hebog.algorithms.component_measurement``. Wrapping only the first
    leaves the other calls inside their parent's self time.
    """

    def original() -> str:
        return "measured"

    defining = types.ModuleType("hebog.fake_defining")
    defining.original = original  # pyright: ignore[reportAttributeAccessIssue]
    importer = types.ModuleType("hebog.fake_importer")
    importer.original = original  # pyright: ignore[reportAttributeAccessIssue]
    unrelated = types.ModuleType("other.fake_importer")
    unrelated.original = original  # pyright: ignore[reportAttributeAccessIssue]
    modules = {
        "hebog.fake_defining": defining,
        "hebog.fake_importer": importer,
        "other.fake_importer": unrelated,
    }
    recorder = StageRecorder()
    installed = install_stage_timers(
        recorder,
        (("hebog.fake_defining", "original", "stage"),),
        modules=modules,
    )
    assert installed == 2
    assert defining.original() == "measured"  # pyright: ignore[reportAttributeAccessIssue]
    assert importer.original() == "measured"  # pyright: ignore[reportAttributeAccessIssue]
    assert unrelated.original() == "measured"  # pyright: ignore[reportAttributeAccessIssue]
    (record,) = recorder.records()
    assert record.stage == ("stage",)
    assert record.calls == 2


@_needs_usage
def test_methods_are_wrapped_on_their_class() -> None:
    class Reader:
        def read(self) -> str:
            return "window"

    module = types.ModuleType("hebog.fake_io")
    module.Reader = Reader  # pyright: ignore[reportAttributeAccessIssue]
    recorder = StageRecorder()
    installed = install_stage_timers(
        recorder,
        (("hebog.fake_io", "Reader.read", "read"),),
        modules={"hebog.fake_io": module},
    )
    assert installed == 1
    assert Reader().read() == "window"
    (record,) = recorder.records()
    assert record.calls == 1


@_needs_usage
def test_process_split_separates_imports_from_work_after_the_run() -> None:
    """Every part of the process lands in the bucket that describes it.

    The worker's clock starts at its first line, so process creation and
    interpreter start-up happen before it and interpreter shutdown after
    it; neither is import time nor work the run did.
    """
    recorder = StageRecorder()
    with recorder.stage("find_sources"):
        with recorder.stage("science"):
            _busy(0.01)
        _busy(0.01)
    records = recorder.records()
    root = next(item for item in records if item.stage == ("find_sources",))
    worker_lifetime = root.wall_seconds + 3.5
    split = process_wall_seconds_by_stage(
        records,
        process_wall_seconds=worker_lifetime + 0.25,
        worker_lifetime_seconds=worker_lifetime,
        import_seconds=3.0,
        root_stage="find_sources",
    )
    assert split[IMPORTS_STAGE] == pytest.approx(3.0)
    assert split[OVERHEAD_STAGE] == pytest.approx(0.5)
    assert split[PROCESS_STAGE] == pytest.approx(0.25)
    assert split["science"] == pytest.approx(
        root.wall_seconds - root.self_wall_seconds
    )
    assert sum(split.values()) == pytest.approx(worker_lifetime + 0.25)


def test_stage_timing_reports_a_clear_error_without_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows has no ``resource``; the profiler says so instead of failing
    at import, so the cost model and configuration stay usable there."""
    monkeypatch.setitem(sys.modules, "resource", None)
    with pytest.raises(OSError, match="macOS or Linux"):
        current_peak_rss_bytes()


@_needs_usage
def test_peak_memory_is_reported_in_bytes() -> None:
    assert current_peak_rss_bytes() > 0


def _case(
    case_id: str,
    group: str,
    megapixels: float,
    components: int,
    seconds: float,
) -> ProfiledCase:
    return ProfiledCase(
        case_id=case_id,
        group=group,
        megapixels=megapixels,
        components=components,
        stage_wall_seconds={"stage": seconds},
    )


def _ladder(
    fixed: float, per_megapixel: float, per_component: float, product: float
) -> list[ProfiledCase]:
    cases: list[ProfiledCase] = []
    for megapixels in (0.26, 1.05, 4.19):
        for components in (0, round(256 * megapixels)):
            seconds = (
                fixed
                + per_megapixel * megapixels
                + per_component * components
                + product * megapixels * components
            )
            cases.append(
                _case(
                    f"case-{megapixels}-{components}",
                    "ladder",
                    megapixels,
                    components,
                    seconds,
                )
            )
    return cases


def test_fit_separates_size_density_and_per_component_scanning() -> None:
    models = fit_stage_cost_models(_ladder(1.4, 18.7, 0.053, 0.045))
    assert models is not None
    model = models["stage"]
    assert model.fixed_seconds == pytest.approx(1.4, abs=1e-6)
    assert model.seconds_per_megapixel == pytest.approx(18.7, abs=1e-6)
    assert model.seconds_per_component == pytest.approx(0.053, abs=1e-6)
    assert model.seconds_per_megapixel_component == pytest.approx(
        0.045, abs=1e-6
    )
    assert model.maximum_absolute_residual_seconds == pytest.approx(
        0.0, abs=1e-6
    )
    assert model.predicted_seconds(
        megapixels=2.0, components=100
    ) == pytest.approx(1.4 + 37.4 + 5.3 + 9.0)


def test_fit_needs_cases_that_vary_size_and_density_independently() -> None:
    """One density gives no way to tell per-component work from per-pixel."""
    dense_only = [
        case for case in _ladder(1.0, 2.0, 0.5, 0.1) if case.components > 0
    ]
    assert fit_stage_cost_models(dense_only) is None


def test_fit_uses_only_ladder_cases_and_totals_every_stage() -> None:
    cases = [
        *_ladder(1.0, 2.0, 0.5, 0.1),
        _case("real", "real", 1.05, 500, 999.0),
    ]
    models = fit_stage_cost_models(cases)
    assert models is not None
    assert set(models) == {"stage", "total"}
    assert models["total"].maximum_absolute_residual_seconds == pytest.approx(
        0.0, abs=1e-6
    )


def test_checked_in_configuration_names_only_known_datasets() -> None:
    configuration = load_profile_configuration(_CONFIGURATION)
    identifiers = {
        dataset.identifier
        for dataset in load_dataset_manifest(
            _ROOT / configuration.dataset_manifest
        ).datasets
    }
    generated = [
        item.case
        for item in configuration.cases
        if item.case.kind == "generated"
    ]
    assert generated
    for case in generated:
        assert case.dataset_id in identifiers
    assert {item.group for item in configuration.cases} == {"ladder", "real"}


def test_configuration_rejects_an_unknown_field(tmp_path: Path) -> None:
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    document["unexpected"] = True
    path = tmp_path / "configuration.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected"):
        load_profile_configuration(path)


@pytest.fixture
def builder() -> dict[str, Any]:
    return runpy.run_path(str(_BUILDER))


def test_committed_manifest_matches_its_builder(
    builder: dict[str, Any],
) -> None:
    built = json.dumps(builder["build_manifest"](), indent=2, sort_keys=True)
    assert _MANIFEST.read_text(encoding="utf-8") == built + "\n"


def test_generated_ladder_holds_density_constant() -> None:
    datasets = load_dataset_manifest(_MANIFEST).datasets
    densities = {
        len(dataset.recipe.sources)
        / (dataset.recipe.shape_yx[0] * dataset.recipe.shape_yx[1])
        for dataset in datasets
        if dataset.recipe.sources
    }
    assert len(densities) == 1
    # The 4,096-pixel rung is the smallest holding more than one admitted
    # tile core, so it is the smallest that separates state scaling with the
    # tile from state scaling with the image.
    assert {dataset.recipe.shape_yx for dataset in datasets} == {
        (512, 512),
        (1024, 1024),
        (2048, 2048),
        (4096, 4096),
    }
    assert all(dataset.role == "development" for dataset in datasets)


def test_ladder_seeds_are_disjoint_from_every_other_manifest() -> None:
    seeds = {
        recipe.seed
        for dataset in load_dataset_manifest(_MANIFEST).datasets
        for recipe in iter_dataset_recipes(dataset)
    }
    assert seeds
    for path in (_ROOT / "config/datasets").glob("*.json"):
        if path == _MANIFEST:
            continue
        historical = DatasetManifest.model_validate_json(path.read_bytes())
        assert seeds.isdisjoint(
            recipe.seed
            for dataset in historical.datasets
            for recipe in iter_dataset_recipes(dataset)
        ), path


def test_worker_times_attributes_that_still_exist() -> None:
    """A renamed or moved function must fail here, not vanish silently."""
    import importlib  # noqa: PLC0415

    worker = runpy.run_path(str(_WORKER))
    stages = worker["_STAGES"]
    assert stages
    for module_name, attribute, stage in stages:
        module = importlib.import_module(module_name)
        owner: Any = module
        for part in attribute.split("."):
            assert hasattr(owner, part), f"{module_name}.{attribute}"
            owner = getattr(owner, part)
        assert callable(owner)
        assert stage


def test_model_documents_every_fitted_term() -> None:
    models = fit_stage_cost_models(_ladder(1.4, 18.7, 0.053, 0.045))
    assert models is not None
    document = models["total"].document()
    assert set(document) == {
        "fixed_seconds",
        "seconds_per_megapixel",
        "seconds_per_component",
        "seconds_per_megapixel_component",
        "maximum_absolute_residual_seconds",
    }
    assert document["seconds_per_megapixel_component"] == pytest.approx(
        0.045, abs=1e-6
    )


def test_fit_needs_at_least_one_case_of_the_fitted_group() -> None:
    assert fit_stage_cost_models([_case("real", "real", 1.0, 5, 2.0)]) is None


def test_real_cases_are_compared_with_the_fitted_model() -> None:
    cases = [
        *_ladder(1.0, 2.0, 0.5, 0.1),
        _case("real", "real", 2.0, 10, 12.0),
    ]
    models = fit_stage_cost_models(cases)
    assert models is not None
    (comparison,) = compare_with_model(cases, models["total"])
    assert comparison["case_id"] == "real"
    assert comparison["measured_seconds"] == pytest.approx(12.0)
    assert comparison["model_seconds"] == pytest.approx(1.0 + 4.0 + 5.0 + 2.0)


def test_top_self_time_ranks_the_costliest_functions(tmp_path: Path) -> None:
    import cProfile  # noqa: PLC0415

    def cheap() -> None:
        _busy(0.005)

    def expensive() -> None:
        _busy(0.05)

    statistics = tmp_path / "profile.pstats"
    profiler = cProfile.Profile()
    profiler.enable()
    cheap()
    expensive()
    profiler.disable()
    profiler.dump_stats(statistics)
    rows = top_self_time(statistics, limit=3)
    assert len(rows) == 3
    assert rows[0]["self_seconds"] >= rows[-1]["self_seconds"]
    functions = [str(row["function"]) for row in rows]
    assert any("_busy" in function for function in functions)
