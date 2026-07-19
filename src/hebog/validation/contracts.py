"""Frozen Phase 0 performance, scalability, and behaviour contracts.

These records describe gates and test obligations. They do not select an
execution plan or import a scheduler, read science data, or run benchmarks.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.evidence import WorkloadClass

_MINIMUM_MATRIX_SIZE = 256
_MAXIMUM_MATRIX_SIZE = 100_000
_DASK_MEMORY_THRESHOLD_COUNT = 4


class _ContractModel(BaseModel):
    """Strict immutable base for checked-in contract records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionBoundary(str, Enum):
    """A performance crossover that requires explicit bracketing cases."""

    DIRECT_TO_LOCAL = "direct-to-local"
    LOCAL_TO_DASK = "local-to-dask"
    DIRECT_TO_CHUNKED_STORAGE = "direct-to-chunked-storage"


class CrossoverProbe(_ContractModel):
    """Initial range in which an execution crossover must be measured."""

    boundary: ExecutionBoundary
    lower_size_pixels: int = Field(ge=1)
    upper_size_pixels: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Require a non-empty ordered probe interval."""
        if self.lower_size_pixels >= self.upper_size_pixels:
            raise ValueError("crossover probe bounds must be increasing")
        return self


class PreviousHebogGate(_ContractModel):
    """Statistical rule for comparing consecutive Hebog baselines."""

    schema_version: Literal[1]
    warmup_repetitions: int = Field(ge=1)
    minimum_measured_repetitions: int = Field(ge=5)
    confidence_level: float = Field(gt=0, lt=1)
    bootstrap_resamples: int = Field(ge=1_000)
    regression_ratio_lower_bound: float = Field(gt=1)


class OneTileOverheadBudget(_ContractModel):
    """Maximum framework overhead for a warm one-tile request."""

    configuration_seconds: float = Field(ge=0)
    fits_io_seconds: float = Field(ge=0)
    partition_planning_seconds: float = Field(ge=0)
    serial_dispatch_seconds: float = Field(ge=0)
    local_dispatch_seconds: float = Field(ge=0)
    dask_dispatch_seconds: float = Field(ge=0)


class PerformanceMatrixContract(_ContractModel):
    """Frozen logarithmic size and scientific-work performance matrix."""

    schema_version: Literal[1]
    matrix_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["frozen-provisional"]
    sizes_pixels: tuple[int, ...] = Field(min_length=2)
    workload_classes: tuple[WorkloadClass, ...]
    initial_crossover_probes: tuple[CrossoverProbe, ...]
    crossover_bracketing_rule: str = Field(min_length=1)
    released_pybdsf_maximum_ratio: float = Field(gt=0, le=1)
    master_pybdsf_exclusive_ratio_limit: float = Field(gt=0, le=1)
    previous_hebog: PreviousHebogGate
    one_tile_overhead_budget: OneTileOverheadBudget

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Protect matrix coverage and comparison semantics."""
        if tuple(sorted(set(self.sizes_pixels))) != self.sizes_pixels:
            raise ValueError("performance sizes must be unique and increasing")
        if (
            self.sizes_pixels[0] != _MINIMUM_MATRIX_SIZE
            or self.sizes_pixels[-1] != _MAXIMUM_MATRIX_SIZE
        ):
            raise ValueError("performance matrix must span 256 to 100000")
        if set(self.workload_classes) != set(WorkloadClass):
            raise ValueError(
                "performance matrix must include every workload class"
            )
        if len(set(self.workload_classes)) != len(self.workload_classes):
            raise ValueError("performance workload classes must be unique")
        boundaries = [
            probe.boundary for probe in self.initial_crossover_probes
        ]
        if set(boundaries) != set(ExecutionBoundary):
            raise ValueError(
                "every execution boundary requires an initial probe"
            )
        if len(set(boundaries)) != len(boundaries):
            raise ValueError("execution boundary probes must be unique")
        return self


class StorageContract(_ContractModel):
    """Storage capabilities required by the extreme qualification case."""

    input: Literal["window-readable-fits-or-chunk-addressable"]
    intermediate: Literal["independently-retryable-chunks"]
    output: Literal["chunked-then-compatible-materialisation"]
    shared_storage_identifier: str = Field(min_length=1)
    normal_run_spill_fraction_limit: float = Field(ge=0, le=1)


class ResourceProfile(_ContractModel):
    """Representative admitted resources on one production node."""

    node_memory_bytes: int = Field(ge=1)
    workers_per_node: int = Field(ge=1)
    threads_per_worker: int = Field(ge=1)
    os_scheduler_headroom_bytes: int = Field(ge=0)
    concurrent_pipeline_reserve_bytes: int = Field(ge=0)
    worker_memory_limit_bytes: int = Field(ge=1)
    dask_target_fraction: float = Field(gt=0, lt=1)
    dask_spill_fraction: float = Field(gt=0, lt=1)
    dask_pause_fraction: float = Field(gt=0, lt=1)
    dask_terminate_fraction: float = Field(gt=0, le=1)
    spill_medium: Literal["worker-local-nvme"]

    @model_validator(mode="after")
    def validate_admission(self) -> Self:
        """Keep workers and Dask thresholds inside admitted memory."""
        admitted = (
            self.node_memory_bytes
            - self.os_scheduler_headroom_bytes
            - self.concurrent_pipeline_reserve_bytes
        )
        if admitted <= 0:
            raise ValueError("resource reserves must leave admitted memory")
        if self.workers_per_node * self.worker_memory_limit_bytes > admitted:
            raise ValueError("worker limits exceed admitted node memory")
        thresholds = (
            self.dask_target_fraction,
            self.dask_spill_fraction,
            self.dask_pause_fraction,
            self.dask_terminate_fraction,
        )
        if (
            tuple(sorted(thresholds)) != thresholds
            or len(set(thresholds)) != _DASK_MEMORY_THRESHOLD_COUNT
        ):
            raise ValueError(
                "Dask memory thresholds must be strictly increasing"
            )
        return self


class NodeScalingGate(_ContractModel):
    """Runtime and efficiency limits at one controlled topology."""

    worker_nodes: int = Field(ge=1)
    maximum_runtime_seconds: float = Field(gt=0)
    maximum_scheduler_overhead_fraction: float = Field(ge=0, lt=1)
    minimum_worker_occupancy_fraction: float = Field(ge=0, le=1)
    minimum_strong_scaling_efficiency: float | None = Field(default=None, gt=0)
    minimum_weak_scaling_efficiency: float | None = Field(default=None, gt=0)


class ScalabilityContract(_ContractModel):
    """Frozen contract for the 100,000-square qualification case."""

    schema_version: Literal[1]
    contract_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["frozen-provisional"]
    logical_shape_yx: tuple[int, int]
    input_planes: tuple[str, ...] = Field(min_length=1)
    output_planes: tuple[str, ...] = Field(min_length=1)
    maximum_live_float32_plane_equivalents: int = Field(ge=1)
    storage: StorageContract
    resource_profile: ResourceProfile
    candidate_tile_core_sizes: tuple[int, ...] = Field(min_length=1)
    maximum_halo_fraction_of_core: float = Field(gt=0, lt=0.5)
    maximum_worker_peak_fraction: float = Field(gt=0, lt=1)
    maximum_graph_tasks: int = Field(ge=1)
    node_gates: tuple[NodeScalingGate, ...]
    tile_batch_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        """Protect the required geometry, topology matrix, and plane names."""
        if self.logical_shape_yx != (_MAXIMUM_MATRIX_SIZE,) * 2:
            raise ValueError(
                "scalability contract must describe 100000 square"
            )
        if len(set(self.input_planes)) != len(self.input_planes):
            raise ValueError("input plane names must be unique")
        if len(set(self.output_planes)) != len(self.output_planes):
            raise ValueError("output plane names must be unique")
        if tuple(sorted(set(self.candidate_tile_core_sizes))) != (
            self.candidate_tile_core_sizes
        ):
            raise ValueError(
                "candidate tile sizes must be unique and increasing"
            )
        nodes = tuple(gate.worker_nodes for gate in self.node_gates)
        if nodes != (1, 10, 50, 100, 200):
            raise ValueError("node gates must cover 1, 10, 50, 100, and 200")
        if self.node_gates[0].minimum_strong_scaling_efficiency is not None:
            raise ValueError(
                "one-node strong-scaling efficiency is the baseline"
            )
        return self


class BehaviourLane(str, Enum):
    """Executable lane owning an unimplemented public behaviour."""

    CONTRACT = "contract"
    ACCEPTANCE = "acceptance"


class PublicBehaviour(_ContractModel):
    """One frozen observable behaviour and its strict-xfail test."""

    identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    lane: BehaviourLane
    scenario: str = Field(min_length=1)
    test_id: str = Field(pattern=r"^test_[a-z0-9_]+$")
    expected_until_implemented: Literal["strict-xfail"]


class PublicBehaviourManifest(_ContractModel):
    """Frozen list of public behaviours that drive red-green-refactor work."""

    schema_version: Literal[1]
    manifest_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["frozen-provisional"]
    behaviours: tuple[PublicBehaviour, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_behaviours(self) -> Self:
        """Keep scenario and test ownership unambiguous."""
        identifiers = [behaviour.identifier for behaviour in self.behaviours]
        test_ids = [behaviour.test_id for behaviour in self.behaviours]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("public behaviour identifiers must be unique")
        if len(set(test_ids)) != len(test_ids):
            raise ValueError("public behaviour test IDs must be unique")
        return self


def load_performance_matrix(path: Path) -> PerformanceMatrixContract:
    """Load and validate a performance-matrix contract."""
    return PerformanceMatrixContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_scalability_contract(path: Path) -> ScalabilityContract:
    """Load and validate an extreme-image scalability contract."""
    return ScalabilityContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_public_behaviours(path: Path) -> PublicBehaviourManifest:
    """Load and validate the public-behaviour manifest."""
    return PublicBehaviourManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
