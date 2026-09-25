"""Worker contract, statistics, evidence and runner of the traced peak."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hebog.validation.evidence import (
    TRACED_PEAK_TOLERANCE_BYTES,
    EvidenceStatus,
    ExecutorKind,
    SoftwareIdentity,
    TracedAllocationEvidence,
    load_evidence,
)
from hebog.validation.quick_benchmark import (
    ProcessUsage,
    development_dataset,
    load_quick_benchmark_configuration,
    local_resources,
    tier_cases,
)
from hebog.validation.traced_peak import (
    BYTES_PER_MEBIBYTE,
    TracedPeakRecord,
    TracedPeakRun,
    admits,
    load_traced_peak_record,
    mebibytes,
    summarise_traced_peaks,
    traced_peak_evidence,
    traced_peaks,
)

_ROOT = Path(__file__).parents[3]
_CONFIGURATION = _ROOT / "config/benchmarks/quick-benchmark.json"
_RUNNER = _ROOT / "scripts/benchmark/measure_traced_peak.py"
_WORKER = _ROOT / "scripts/benchmark/measure_traced_peak_worker.py"
_SHA = "a" * 64


def _record_payload(**overrides: object) -> dict[str, object]:
    """Return what a worker reports about one 3,000² traced repetition."""
    return {
        "finder_peak_traced_bytes": 1_407_000_000,
        "gaussian_component_count": 411,
        "import_traced_bytes": 95_000_000,
        "peak_traced_bytes": 1_407_000_000,
        "public_size_limit_pixels": 3000,
        "source_count": 300,
        "traced_wall_seconds": 240.5,
    } | overrides


def _record(**overrides: object) -> TracedPeakRecord:
    return TracedPeakRecord.model_validate(_record_payload(**overrides))


def _run(peak_traced_bytes: int) -> TracedPeakRun:
    return TracedPeakRun(
        record=_record(
            peak_traced_bytes=peak_traced_bytes,
            finder_peak_traced_bytes=peak_traced_bytes,
        ),
        usage=ProcessUsage(
            wall_seconds=250.0, cpu_seconds=240.0, peak_rss_bytes=2**31
        ),
    )


def _evidence(
    *peaks: int, status: EvidenceStatus = EvidenceStatus.EXPLORATORY
) -> TracedAllocationEvidence:
    configuration = load_quick_benchmark_configuration(_CONFIGURATION)
    case = tier_cases(configuration, "smoke")[0]
    evidence = traced_peak_evidence(
        run_id="traced-peak-compact-snr-ladder",
        captured_at=datetime(2026, 9, 25, tzinfo=UTC),
        dataset=development_dataset(
            case, content_sha256=_SHA, shape_yx=(512, 512)
        ),
        configuration_sha256=_SHA,
        subject=SoftwareIdentity(
            name="hebog",
            version="0.13.0",
            dependency_inventory_sha256=_SHA,
        ),
        environment_sha256=_SHA,
        resources=local_resources(
            ExecutorKind.SERIAL, allocated_cpu_cores=1, memory_bytes=2**34
        ),
        runs=[_run(peak) for peak in peaks],
    )
    if status is EvidenceStatus.EXPLORATORY:
        return evidence
    return TracedAllocationEvidence.model_validate(
        evidence.model_dump() | {"status": status}
    )


def test_worker_record_round_trips_from_its_written_file(
    tmp_path: Path,
) -> None:
    """The runner reads exactly the numbers the worker wrote."""
    path = tmp_path / "result.json"
    path.write_text(json.dumps(_record_payload()), encoding="utf-8")

    record = load_traced_peak_record(path)

    assert record == _record()
    assert record.peak_traced_bytes == 1_407_000_000
    assert record.public_size_limit_pixels == 3000


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        (
            {"peak_traced_bytes": 1_000_000_000},
            "process peak cannot be below the finder peak",
        ),
        (
            {"import_traced_bytes": 1_500_000_000},
            "import floor cannot exceed the finder peak",
        ),
        ({"peak_traced_bytes": 0}, "greater than 0"),
        ({"traced_wall_seconds": -1.0}, "greater than or equal to 0"),
    ),
)
def test_worker_record_rejects_impossible_spans(
    overrides: dict[str, object], message: str
) -> None:
    """A record no tracing session could produce is not a measurement."""
    with pytest.raises(ValidationError, match=message):
        _record(**overrides)


def test_worker_record_rejects_unknown_fields() -> None:
    """The worker contract is exact, so a renamed field fails loudly."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        TracedPeakRecord.model_validate(
            _record_payload() | {"peak_bytes": 1_407_000_000}
        )


def test_summary_quotes_the_worst_peak_and_reports_reproducibility() -> None:
    """Repeated peaks are reproduced; one repetition measures neither."""
    reproduced = summarise_traced_peaks([2 * BYTES_PER_MEBIBYTE] * 3)
    disagreeing = summarise_traced_peaks(
        [2 * BYTES_PER_MEBIBYTE, 3 * BYTES_PER_MEBIBYTE]
    )
    single = summarise_traced_peaks([2 * BYTES_PER_MEBIBYTE])

    assert (reproduced.repetitions, reproduced.reproduced) == (3, True)
    assert (reproduced.peak_mebibytes, reproduced.spread_bytes) == (2.0, 0)
    assert disagreeing.reproduced is False
    assert disagreeing.peak_mebibytes == 3.0
    assert disagreeing.spread_bytes == BYTES_PER_MEBIBYTE
    assert (
        disagreeing.minimum_peak_bytes,
        disagreeing.maximum_peak_bytes,
    ) == (
        2 * BYTES_PER_MEBIBYTE,
        3 * BYTES_PER_MEBIBYTE,
    )
    assert single.reproduced is None
    with pytest.raises(ValueError, match="at least one"):
        summarise_traced_peaks([])


def test_reproducibility_is_assessed_at_the_stated_tolerance() -> None:
    """A run repeats to kilobytes, not to the byte, so the rule is a spread.

    The tolerance is the precision a peak is quoted at, so a spread within it
    reproduces and a spread beyond it does not.
    """
    base = 1_384_517_879
    within = summarise_traced_peaks([base, base + TRACED_PEAK_TOLERANCE_BYTES])
    beyond = summarise_traced_peaks(
        [base, base + TRACED_PEAK_TOLERANCE_BYTES + 1]
    )

    assert TRACED_PEAK_TOLERANCE_BYTES == BYTES_PER_MEBIBYTE // 10
    assert within.reproduced is True
    assert beyond.reproduced is False


def test_mebibytes_and_envelope_admission_are_explicit() -> None:
    """Peaks are quoted in MiB; the long axis decides admission."""
    assert mebibytes(BYTES_PER_MEBIBYTE // 2) == 0.5
    assert admits((2048, 3000), 3000) is True
    assert admits((3600, 3000), 3000) is False


def test_evidence_records_every_traced_repetition_as_exploratory(
    tmp_path: Path,
) -> None:
    """Evidence round-trips and carries both spans of each repetition."""
    evidence = _evidence(1_407_000_000, 1_407_000_000)
    path = tmp_path / "traced-peak.json"
    path.write_text(evidence.model_dump_json(), encoding="utf-8")

    loaded = load_evidence(path)

    assert loaded == evidence
    assert evidence.status is EvidenceStatus.EXPLORATORY
    assert evidence.evidence_type == "traced-allocation"
    assert traced_peaks(evidence) == (1_407_000_000, 1_407_000_000)
    first = evidence.measurements[0]
    assert first.repetition_index == 0
    assert first.import_traced_bytes == 95_000_000
    assert first.peak_rss_bytes == 2**31
    assert first.source_count == 300
    assert first.gaussian_component_count == 411
    assert evidence.resources.executor is ExecutorKind.SERIAL


def test_reviewed_traced_evidence_needs_a_reproduced_peak() -> None:
    """A reviewed peak repeats within the tolerance, or is not reviewed."""
    with pytest.raises(ValidationError, match="two repetitions"):
        _evidence(1_407_000_000, status=EvidenceStatus.REVIEWED)
    with pytest.raises(ValidationError, match="one reproduced peak"):
        _evidence(1_407_000_000, 1_408_000_000, status=EvidenceStatus.REVIEWED)

    reviewed = _evidence(
        1_407_000_000,
        1_407_000_000 + TRACED_PEAK_TOLERANCE_BYTES,
        status=EvidenceStatus.REVIEWED,
    )

    assert reviewed.status is EvidenceStatus.REVIEWED


def _runner() -> dict[str, Any]:
    return runpy.run_path(str(_RUNNER))


def test_runner_traces_the_configured_case_and_raises_the_size_limit() -> None:
    """The limit follows the input, so a raise candidate can be measured."""
    runner = _runner()

    command = runner["_worker_command"](
        input_path=Path("image.fits"),
        case_id="lotss-dr3-1312-dense-3000",
        settings_json="{}",
        supplied_metadata=None,
        shape_yx=(3000, 3600),
    )

    assert command[1] == str(_WORKER)
    limit = command.index("--diagnostic-size-limit")
    assert command[limit + 1] == "3600"
    assert "--supplied-metadata" not in command


def test_runner_passes_supplied_metadata_only_when_present() -> None:
    """A case without supplied metadata sends no metadata option."""
    runner = _runner()

    command = runner["_worker_command"](
        input_path=Path("image.fits"),
        case_id="sdc1-b2-1000h-crowded",
        settings_json="{}",
        supplied_metadata={"beam_position_angle_degrees": 0.0},
        shape_yx=(1024, 1024),
    )

    index = command.index("--supplied-metadata")
    assert json.loads(command[index + 1]) == {
        "beam_position_angle_degrees": 0.0
    }


def test_runner_fails_only_on_disagreeing_repetitions() -> None:
    """One repetition is unmeasured, two that disagree fail the run."""
    runner = _runner()
    records: list[dict[str, Any]] = [
        {
            "case_id": "single",
            "status": "success",
            "peak": {"reproduced": None},
        },
        {
            "case_id": "reproduced",
            "status": "success",
            "peak": {"reproduced": True},
        },
        {
            "case_id": "unstable",
            "status": "success",
            "peak": {"reproduced": False},
        },
        {"case_id": "broken", "status": "failure", "error": "boom"},
    ]

    assert runner["_unreproduced_cases"](records) == ("unstable",)
    assert runner["_failed_cases"](records) == ("broken",)
    assert runner["_reproduced_text"](None) == "-"
    assert runner["_reproduced_text"](True) == "yes"
    assert runner["_reproduced_text"](False) == "NO"


def test_runner_identifies_the_quick_benchmark_configuration() -> None:
    """A traced peak and a timing share one measured-case identity."""
    runner = _runner()
    configuration = load_quick_benchmark_configuration(_CONFIGURATION)
    case = tier_cases(configuration, "smoke")[0]
    benchmark = runpy.run_path(
        str(_ROOT / "scripts/benchmark/quick_benchmark.py")
    )

    assert runner["_configuration_sha256"](configuration, case) == benchmark[
        "_configuration_sha256"
    ](configuration, case)
