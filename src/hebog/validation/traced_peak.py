"""Deterministic traced-allocation peak of one complete public finder run.

The plan gates every public envelope raise on ``tracemalloc``'s peak
rather than on peak resident memory: the traced peak counts the allocations the
process itself makes, including NumPy array data, and repeats within the
documented tolerance for one input, one configuration and one implementation,
while ``ru_maxrss`` on the same machine varies by tens of percent with machine load.

Tracing roughly doubles wall time, so a traced run is never a timing
measurement. This module therefore serves a runner of its own, and the quick
benchmark never traces: the two measure the same inputs and settings in
separate processes, and neither reads the other's numbers. Loading this module
never reads data or starts work.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.evidence import (
    TRACED_PEAK_TOLERANCE_BYTES,
    DatasetIdentity,
    EvidenceStatus,
    ResourceAllocation,
    SoftwareIdentity,
    TracedAllocationEvidence,
    TracedAllocationMeasurement,
)
from hebog.validation.quick_benchmark import ProcessUsage

BYTES_PER_MEBIBYTE = 2**20
"""One mebibyte, the unit the plan and the profile page quote peaks in."""


class TracedPeakRecord(BaseModel):
    """What one traced worker process reports about its own run.

    The worker reports only what the parent cannot know: the traced peaks of
    the two spans it measured, the size limit of the Hebog it imported, the
    work the run did, and its own traced wall time. Software identity comes
    from the parent, which runs in the same environment, so the traced
    process imports nothing but the standard library and the public API.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    peak_traced_bytes: int = Field(gt=0)
    finder_peak_traced_bytes: int = Field(gt=0)
    import_traced_bytes: int = Field(gt=0)
    public_size_limit_pixels: int = Field(gt=0)
    source_count: int = Field(ge=0)
    gaussian_component_count: int = Field(ge=0)
    traced_wall_seconds: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_spans(self) -> TracedPeakRecord:
        """Require peaks one tracing session can have produced.

        The import span and the finder span partition the run, so the
        process peak is the larger of the two, and the allocations the
        imports still hold cannot exceed the peak of the span that follows.
        """
        if self.peak_traced_bytes < self.finder_peak_traced_bytes:
            raise ValueError(
                "the process peak cannot be below the finder peak"
            )
        if self.import_traced_bytes > self.finder_peak_traced_bytes:
            raise ValueError("the import floor cannot exceed the finder peak")
        return self


def load_traced_peak_record(path: Path) -> TracedPeakRecord:
    """Load and validate what one traced worker process reported."""
    return TracedPeakRecord.model_validate_json(
        path.read_text(encoding="utf-8")
    )


@dataclass(frozen=True, slots=True)
class TracedPeakRun:
    """One repetition: the worker's own record and the parent's usage.

    ``usage`` measures the whole worker process through ``wait4``. Its wall
    time and peak resident memory are both inflated by tracing, so only its
    peak resident memory is recorded, and only as an envelope.
    """

    record: TracedPeakRecord
    usage: ProcessUsage


def traced_peak_evidence(  # noqa: PLR0913
    *,
    run_id: str,
    captured_at: datetime,
    dataset: DatasetIdentity,
    configuration_sha256: str,
    subject: SoftwareIdentity,
    environment_sha256: str,
    resources: ResourceAllocation,
    runs: Sequence[TracedPeakRun],
) -> TracedAllocationEvidence:
    """Record every traced repetition of one case as exploratory evidence.

    Traced evidence stays exploratory until a named envelope decision
    reviews it, as the plan's raise rule requires.
    """
    return TracedAllocationEvidence(
        schema_version=1,
        evidence_type="traced-allocation",
        run_id=run_id,
        captured_at=captured_at,
        status=EvidenceStatus.EXPLORATORY,
        dataset=dataset,
        configuration_sha256=configuration_sha256,
        subject=subject,
        environment_sha256=environment_sha256,
        resources=resources,
        measurements=tuple(
            TracedAllocationMeasurement(
                repetition_index=index,
                peak_traced_bytes=run.record.peak_traced_bytes,
                finder_peak_traced_bytes=run.record.finder_peak_traced_bytes,
                import_traced_bytes=run.record.import_traced_bytes,
                peak_rss_bytes=run.usage.peak_rss_bytes,
                traced_wall_seconds=run.record.traced_wall_seconds,
                source_count=run.record.source_count,
                gaussian_component_count=run.record.gaussian_component_count,
            )
            for index, run in enumerate(runs)
        ),
    )


def traced_peaks(evidence: TracedAllocationEvidence) -> tuple[int, ...]:
    """Return the process peak of every repetition, in order."""
    return tuple(
        measurement.peak_traced_bytes for measurement in evidence.measurements
    )


@dataclass(frozen=True, slots=True)
class TracedPeakSummary:
    """Peak allocation of one case across its repetitions.

    ``peak_bytes`` is the largest peak measured, so a case whose peak is not
    reproduced is quoted at its worst. ``reproduced`` is the property the
    gate rests on: every repetition allocated the same peak, to within
    :data:`~hebog.validation.evidence.TRACED_PEAK_TOLERANCE_BYTES`. It is
    ``None`` after one repetition, which is evidence neither way.
    """

    repetitions: int
    peak_bytes: int
    minimum_peak_bytes: int
    maximum_peak_bytes: int
    spread_bytes: int
    reproduced: bool | None

    @property
    def peak_mebibytes(self) -> float:
        """Return the quoted peak in mebibytes."""
        return mebibytes(self.peak_bytes)


def summarise_traced_peaks(values: Sequence[int]) -> TracedPeakSummary:
    """Summarise the peaks of one case's repetitions.

    Peaks count as reproduced when their spread is within
    :data:`~hebog.validation.evidence.TRACED_PEAK_TOLERANCE_BYTES`, because a
    run allocates its own strings, paths and metadata slightly differently
    from the next. One repetition leaves reproducibility unmeasured rather
    than passed.

    Raises:
        ValueError: If no repetition was measured.

    >>> summary = summarise_traced_peaks([2**20, 2**20 + 1024])
    >>> (summary.spread_bytes, summary.reproduced)
    (1024, True)
    >>> summarise_traced_peaks([2**20, 2**21]).reproduced
    False
    >>> summarise_traced_peaks([2**20]).reproduced is None
    True
    """
    if not values:
        raise ValueError("at least one traced repetition is required")
    spread = max(values) - min(values)
    return TracedPeakSummary(
        repetitions=len(values),
        peak_bytes=max(values),
        minimum_peak_bytes=min(values),
        maximum_peak_bytes=max(values),
        spread_bytes=spread,
        reproduced=(
            None if len(values) == 1 else spread <= TRACED_PEAK_TOLERANCE_BYTES
        ),
    )


def mebibytes(value: int) -> float:
    """Convert bytes to mebibytes, the unit peaks are quoted in.

    >>> mebibytes(3 * 2**20)
    3.0
    """
    return value / BYTES_PER_MEBIBYTE


def admits(shape_yx: tuple[int, int], size_limit_pixels: int) -> bool:
    """Whether the measured Hebog's public envelope admits this image.

    A peak measured above the limit is a raise candidate rather than a
    supported size, so the report says which it is.

    >>> admits((3000, 3000), 3000)
    True
    >>> admits((3000, 3600), 3000)
    False
    """
    return max(shape_yx) <= size_limit_pixels
