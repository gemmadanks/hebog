"""Stage timing and cost modelling for the complete-execution profile.

``scripts/benchmark/profile_complete_execution.py`` and its worker are thin
runners over this module. A profile splits one complete public run into its
stages and fits stage cost against image size and source count, so that
per-pixel work, per-source work and per-source work repeated over the whole
image can be told apart.

Timing wraps module attributes inside the profiling process only; no Hebog
code changes, and nothing here runs at import.
"""

from __future__ import annotations

import functools
import importlib
import resource
import sys
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from hebog.validation.quick_check import HebogSettings, QuickCheckCase

STARTUP_STAGE = "interpreter start-up and imports"
"""Time from process start until the profiled imports are complete."""

OVERHEAD_STAGE = "other process overhead"
"""Process time outside start-up and the root stage.

It covers temporary-product cleanup, result writing and interpreter
shutdown, which all happen after the root stage ends.
"""

SELF_STAGE_SUFFIX = "other {stage} work"
_MODEL_TERMS = 4
_PACKAGE = "hebog"


@dataclass(frozen=True, slots=True)
class StageRecord:
    """Measured usage of one stage, including its nested stages."""

    stage: tuple[str, ...]
    calls: int
    wall_seconds: float
    self_wall_seconds: float
    cpu_seconds: float
    self_cpu_seconds: float
    peak_rss_bytes: int
    peak_rss_increase_bytes: int
    block_inputs: int
    block_outputs: int

    def document(self) -> dict[str, Any]:
        """Return one JSON-serializable record."""
        return {
            "stage": list(self.stage),
            "calls": self.calls,
            "wall_seconds": self.wall_seconds,
            "self_wall_seconds": self.self_wall_seconds,
            "cpu_seconds": self.cpu_seconds,
            "self_cpu_seconds": self.self_cpu_seconds,
            "peak_rss_bytes": self.peak_rss_bytes,
            "peak_rss_increase_bytes": self.peak_rss_increase_bytes,
            "block_inputs": self.block_inputs,
            "block_outputs": self.block_outputs,
        }


@dataclass(slots=True)
class _StageTotals:
    """Running totals of one stage, keyed by its path in the profile."""

    calls: int = 0
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    child_wall_seconds: float = 0.0
    child_cpu_seconds: float = 0.0
    peak_rss_bytes: int = 0
    peak_rss_increase_bytes: int = 0
    block_inputs: int = 0
    block_outputs: int = 0


def peak_rss_bytes(maximum_resident_set: int) -> int:
    """Convert ``ru_maxrss`` to bytes: macOS reports bytes, Linux KiB."""
    return (
        maximum_resident_set
        if sys.platform == "darwin"
        else maximum_resident_set * 1024
    )


class StageRecorder:
    """Accumulate nested stage usage for one single-threaded run.

    Stage paths record nesting, so a parent's self time excludes the stages
    it called. Block-I/O counters come from ``resource`` and stay zero on
    platforms that do not count them, which is a measured zero, not an
    absence of device I/O.
    """

    def __init__(self) -> None:
        """Start with no active stage and no totals."""
        self._path: tuple[str, ...] = ()
        self._totals: dict[tuple[str, ...], _StageTotals] = {}

    @contextmanager
    def stage(self, name: str) -> Generator[None]:
        """Measure one call of ``name`` under the active stage."""
        parent = self._path
        path = (*parent, name)
        before = resource.getrusage(resource.RUSAGE_SELF)
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        self._path = path
        try:
            yield
        finally:
            self._path = parent
            wall = time.perf_counter() - wall_started
            cpu = time.process_time() - cpu_started
            after = resource.getrusage(resource.RUSAGE_SELF)
            totals = self._totals.setdefault(path, _StageTotals())
            totals.calls += 1
            totals.wall_seconds += wall
            totals.cpu_seconds += cpu
            totals.peak_rss_bytes = max(
                totals.peak_rss_bytes, peak_rss_bytes(after.ru_maxrss)
            )
            totals.peak_rss_increase_bytes += peak_rss_bytes(
                after.ru_maxrss
            ) - peak_rss_bytes(before.ru_maxrss)
            totals.block_inputs += after.ru_inblock - before.ru_inblock
            totals.block_outputs += after.ru_oublock - before.ru_oublock
            if parent:
                parent_totals = self._totals.setdefault(parent, _StageTotals())
                parent_totals.child_wall_seconds += wall
                parent_totals.child_cpu_seconds += cpu

    def wrap(self, function: Callable[..., Any], name: str) -> Any:
        """Return ``function`` timed as stage ``name``."""

        @functools.wraps(function)
        def timed(*args: Any, **kwargs: Any) -> Any:
            with self.stage(name):
                return function(*args, **kwargs)

        return timed

    def records(self) -> tuple[StageRecord, ...]:
        """Return every measured stage, ordered by its path."""
        return tuple(
            StageRecord(
                stage=path,
                calls=totals.calls,
                wall_seconds=totals.wall_seconds,
                self_wall_seconds=(
                    totals.wall_seconds - totals.child_wall_seconds
                ),
                cpu_seconds=totals.cpu_seconds,
                self_cpu_seconds=(
                    totals.cpu_seconds - totals.child_cpu_seconds
                ),
                peak_rss_bytes=totals.peak_rss_bytes,
                peak_rss_increase_bytes=totals.peak_rss_increase_bytes,
                block_inputs=totals.block_inputs,
                block_outputs=totals.block_outputs,
            )
            for path, totals in sorted(self._totals.items())
        )


def stage_records(
    documents: Sequence[Mapping[str, Any]],
) -> tuple[StageRecord, ...]:
    """Rebuild stage records from one worker result document."""
    return tuple(
        StageRecord(
            stage=tuple(document["stage"]),
            calls=int(document["calls"]),
            wall_seconds=float(document["wall_seconds"]),
            self_wall_seconds=float(document["self_wall_seconds"]),
            cpu_seconds=float(document["cpu_seconds"]),
            self_cpu_seconds=float(document["self_cpu_seconds"]),
            peak_rss_bytes=int(document["peak_rss_bytes"]),
            peak_rss_increase_bytes=int(document["peak_rss_increase_bytes"]),
            block_inputs=int(document["block_inputs"]),
            block_outputs=int(document["block_outputs"]),
        )
        for document in documents
    )


def install_stage_timers(
    recorder: StageRecorder,
    stages: Sequence[tuple[str, str, str]],
    *,
    modules: Mapping[str, Any] | None = None,
) -> int:
    """Time each ``(module, attribute, stage)`` and return the bindings used.

    A function imported into several modules has one binding in each of
    them, and the public path may call any of them: ``import x; x.f()``
    resolves at call time, but ``from x import f`` bound ``f`` when that
    module was imported. Every binding in the ``hebog`` package is therefore
    replaced, so a call through an alias is timed as its own stage instead
    of disappearing into its caller's self time. A ``Class.method``
    attribute is wrapped once, on the class.
    """
    scope = dict(sys.modules if modules is None else modules)
    installed = 0
    for module_name, attribute, stage in stages:
        owner: Any = scope.get(module_name) or importlib.import_module(
            module_name
        )
        *parents, name = attribute.split(".")
        for parent in parents:
            owner = getattr(owner, parent)
        original = getattr(owner, name)
        timed = recorder.wrap(original, stage)
        setattr(owner, name, timed)
        installed += 1
        if parents:
            continue
        for other_name, other in scope.items():
            if (
                other is owner
                or other is None
                or not other_name.startswith(f"{_PACKAGE}.")
                or getattr(other, name, None) is not original
            ):
                continue
            setattr(other, name, timed)
            installed += 1
    return installed


def process_wall_seconds_by_stage(
    records: Sequence[StageRecord],
    *,
    process_wall_seconds: float,
    import_seconds: float,
    root_stage: str,
) -> dict[str, float]:
    """Split one process's wall time into start-up, stages and overhead.

    Nested stages stay inside their parent; the root stage's own work and
    the time outside it are reported separately, so start-up is the measured
    import time rather than everything the root stage did not cover.
    """
    stages = {record.stage: record for record in records}
    root = stages[(root_stage,)]
    split = {
        path[1]: record.wall_seconds
        for path, record in stages.items()
        if len(path) == 2  # noqa: PLR2004 pairs are (root, stage)
    }
    split[SELF_STAGE_SUFFIX.format(stage=root_stage)] = root.self_wall_seconds
    split[STARTUP_STAGE] = import_seconds
    split[OVERHEAD_STAGE] = (
        process_wall_seconds - import_seconds - root.wall_seconds
    )
    return split


@dataclass(frozen=True, slots=True)
class ProfiledCase:
    """One profiled case and the wall seconds of its top-level stages."""

    case_id: str
    group: str
    megapixels: float
    components: int
    stage_wall_seconds: Mapping[str, float] = field(
        default_factory=dict[str, float]
    )

    @property
    def total_wall_seconds(self) -> float:
        """Return the wall seconds of the complete process."""
        return sum(self.stage_wall_seconds.values())

    def model_terms(self) -> tuple[float, float, float, float]:
        """Return the fitted terms of this case."""
        return (
            1.0,
            self.megapixels,
            float(self.components),
            self.megapixels * self.components,
        )


@dataclass(frozen=True, slots=True)
class StageCostModel:
    """One stage's cost against image size and source count."""

    fixed_seconds: float
    seconds_per_megapixel: float
    seconds_per_component: float
    seconds_per_megapixel_component: float
    maximum_absolute_residual_seconds: float

    def predicted_seconds(
        self, *, megapixels: float, components: int
    ) -> float:
        """Return the cost this model expects for one image."""
        return (
            self.fixed_seconds
            + self.seconds_per_megapixel * megapixels
            + self.seconds_per_component * components
            + self.seconds_per_megapixel_component * megapixels * components
        )

    def document(self) -> dict[str, float]:
        """Return one JSON-serializable model."""
        return {
            "fixed_seconds": self.fixed_seconds,
            "seconds_per_megapixel": self.seconds_per_megapixel,
            "seconds_per_component": self.seconds_per_component,
            "seconds_per_megapixel_component": (
                self.seconds_per_megapixel_component
            ),
            "maximum_absolute_residual_seconds": (
                self.maximum_absolute_residual_seconds
            ),
        }


def fit_stage_cost_models(
    cases: Sequence[ProfiledCase],
    *,
    group: str = "ladder",
) -> dict[str, StageCostModel] | None:
    """Fit every stage of ``group``, and the total, by least squares.

    The interaction term is work repeated per component over the whole
    image, which grows with the square of image size at a fixed source
    density. Separating it needs cases whose size and density vary
    independently; ``None`` says the cases cannot tell the terms apart.
    """
    fitted = [case for case in cases if case.group == group]
    if not fitted:
        return None
    design = np.array([case.model_terms() for case in fitted])
    if np.linalg.matrix_rank(design) < _MODEL_TERMS:
        return None
    models: dict[str, StageCostModel] = {}
    stages = sorted(
        {name for case in fitted for name in case.stage_wall_seconds}
    )
    for stage in [*stages, "total"]:
        seconds = np.array(
            [
                case.total_wall_seconds
                if stage == "total"
                else case.stage_wall_seconds.get(stage, 0.0)
                for case in fitted
            ]
        )
        solution, *_ = np.linalg.lstsq(design, seconds, rcond=None)
        models[stage] = StageCostModel(
            fixed_seconds=float(solution[0]),
            seconds_per_megapixel=float(solution[1]),
            seconds_per_component=float(solution[2]),
            seconds_per_megapixel_component=float(solution[3]),
            maximum_absolute_residual_seconds=float(
                np.max(np.abs(seconds - design @ solution))
            ),
        )
    return models


def compare_with_model(
    cases: Sequence[ProfiledCase],
    model: StageCostModel,
    *,
    group: str = "real",
) -> list[dict[str, Any]]:
    """Report how far each case of ``group`` lies from a fitted model."""
    return [
        {
            "case_id": case.case_id,
            "megapixels": case.megapixels,
            "components": case.components,
            "measured_seconds": case.total_wall_seconds,
            "model_seconds": model.predicted_seconds(
                megapixels=case.megapixels, components=case.components
            ),
        }
        for case in cases
        if case.group == group
    ]


class ProfileCase(BaseModel):
    """One profiled input and the group it belongs to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group: Literal["ladder", "real"]
    case: QuickCheckCase


class ProfileConfiguration(BaseModel):
    """Versioned cases and finder settings of the execution profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    dataset_manifest: str = Field(min_length=1)
    hebog: HebogSettings
    cases: tuple[ProfileCase, ...] = Field(min_length=1)


def load_profile_configuration(path: Path) -> ProfileConfiguration:
    """Load and validate one execution-profile configuration."""
    return ProfileConfiguration.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def top_self_time(
    statistics_path: Path, *, limit: int = 40
) -> list[dict[str, Any]]:
    """Return the functions with the most self time in one ``cProfile`` run.

    ``cProfile`` sees only the calling thread, so work on Zarr's I/O thread
    is absent, and its overhead inflates Python-heavy code; use it to rank
    functions, not to time stages.
    """
    import pstats  # noqa: PLC0415

    statistics: Any = pstats.Stats(str(statistics_path))
    rows = [
        {
            "function": f"{Path(file).name}:{line}({function})",
            "calls": calls,
            "self_seconds": self_seconds,
            "cumulative_seconds": cumulative_seconds,
        }
        for (file, line, function), (
            _,
            calls,
            self_seconds,
            cumulative_seconds,
            _,
        ) in statistics.stats.items()
    ]
    return sorted(rows, key=lambda row: -float(row["self_seconds"]))[:limit]
