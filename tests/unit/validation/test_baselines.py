"""Tests for compiling raw PyBDSF campaigns into governed evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hebog.validation.baselines import (
    BaselineEvidenceMetadata,
    compile_pybdsf_benchmark_evidence,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    BenchmarkEvidence,
    EvidenceStatus,
    ExecutorKind,
    WorkloadClass,
    load_evidence,
)

_ARTIFACT_NAMES = (
    "apparent_sky.txt",
    "diagnostics.json",
    "flat_noise_rms.fits",
    "source_catalog.fits",
    "source_filter_mask.fits",
    "true_sky.txt",
    "true_sky_rms.fits",
)


def _canonical_sha256(value: object) -> str:
    """Return the runner's canonical JSON digest for test records."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _metrics(index: int) -> dict[str, float | int]:
    """Return internally consistent raw timing metrics."""
    return {
        "cpu_seconds": 0.75 + index / 100,
        "peak_rss_bytes": 2048 + index,
        "system_seconds": 0.25,
        "user_seconds": 0.5 + index / 100,
        "wall_seconds": 1.0 + index / 100,
    }


def _write_campaign(directory: Path) -> None:
    """Write a complete six-run synthetic raw campaign."""
    configuration = {"threshold": 5.0}
    dependencies = [{"name": "bdsf", "version": "1.14.1"}]
    environment = {
        "cpu_count": 8,
        "machine": "test-machine",
        "node_memory_bytes": 16 * 1024**3,
        "platform": "test-platform",
        "python": "3.12.0",
    }
    run_paths: list[str] = []
    for index in range(6):
        repetition = directory / f"rep-{index:02d}"
        repetition.mkdir(parents=True)
        artifacts = {}
        for name in _ARTIFACT_NAMES:
            content = f"stable {name}\n".encode()
            path = repetition / name
            path.write_bytes(content)
            artifacts[name] = {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        run = {
            "artifacts": artifacts,
            "captured_at": f"2026-07-18T12:00:0{index}+00:00",
            "complete": _metrics(index),
            "configuration": configuration,
            "configuration_sha256": _canonical_sha256(configuration),
            "container_image_digest": f"sha256:{'a' * 64}",
            "dataset": {
                "flat_noise_sha256": "b" * 64,
                "identifier": "compact-reference-256",
                "true_sky_sha256": "b" * 64,
            },
            "dependency_inventory": dependencies,
            "dependency_inventory_sha256": _canonical_sha256(dependencies),
            "environment": environment,
            "environment_sha256": _canonical_sha256(environment),
            "instrumentation": {
                "array_copies": "unavailable",
                "dask": "not applicable",
                "peak_rss": "sampled",
            },
            "ncores": 4,
            "reference": "release",
            "repetition_index": index,
            "schema_version": 1,
            "software": {
                "bdsf": {
                    "commit": "c" * 40,
                    "version": "1.14.1",
                },
                "lsmtool": {
                    "commit": "d" * 40,
                    "version": "1.8.0",
                },
                "rapthor": {
                    "commit": "e" * 40,
                    "version": None,
                },
            },
            "stages": [
                {"metrics": _metrics(index), "stage": "flat-noise-pybdsf"}
            ],
            "warmup": index == 0,
        }
        run_path = repetition / "run.json"
        run_path.write_text(json.dumps(run), encoding="utf-8")
        run_paths.append(f"rep-{index:02d}/run.json")
    index_document = {
        "container_image": "example.invalid/reference@sha256:fixed",
        "container_image_digest": f"sha256:{'a' * 64}",
        "dataset_id": "compact-reference-256",
        "input_sha256": {
            "flat_noise_image": "b" * 64,
            "true_sky_image": "b" * 64,
        },
        "lsmtool_checkout": {
            "branch": "pinned-lsmtool",
            "commit": "d" * 40,
            "working_tree": "clean",
        },
        "ncores": 4,
        "rapthor_checkout": {
            "branch": "pinned-rapthor",
            "commit": "e" * 40,
            "working_tree": "clean",
        },
        "reference": "release",
        "repetitions": 5,
        "runs": run_paths,
        "schema_version": 1,
        "scientific_identity_normalization": {
            "apparent_sky.txt": "history comments excluded",
            "true_sky.txt": "history comments excluded",
        },
        "tool_sha256": {
            "campaign_runner": "c" * 64,
            "evidence_compiler": "d" * 64,
            "reference_runner": "e" * 64,
        },
        "tree_hash_exclusions": ["table.lock"],
        "warmups": 1,
    }
    (directory / "baseline-index.json").write_text(
        json.dumps(index_document),
        encoding="utf-8",
    )


def _compile(directory: Path) -> BenchmarkEvidence:
    """Compile the standard test campaign."""
    return compile_pybdsf_benchmark_evidence(
        directory,
        BaselineEvidenceMetadata(
            run_id="phase-0-pybdsf-release-compact",
            dataset_role=DatasetRole.REGRESSION,
            shape_yx=(256, 256),
            workload_class=WorkloadClass.NORMAL,
        ),
    )


def test_compile_pybdsf_campaign_preserves_metrics_and_provenance(
    tmp_path: Path,
) -> None:
    """A complete campaign becomes reviewed, typed benchmark evidence."""
    _write_campaign(tmp_path)

    evidence = _compile(tmp_path)

    assert evidence.status is EvidenceStatus.REVIEWED
    assert evidence.subject.version == "1.14.1"
    assert evidence.dataset.content_sha256 == "b" * 64
    assert evidence.resources.executor is ExecutorKind.EXTERNAL
    assert len(evidence.measurements) == 6
    assert sum(not item.warmup for item in evidence.measurements) == 5
    assert evidence.measurements[1].complete.array_copy_count is None
    assert evidence.measurements[1].complete.dask_task_count == 0
    assert evidence.measurements[1].stages[0].stage == "flat-noise-pybdsf"


def test_compile_pybdsf_campaign_rejects_tampered_product(
    tmp_path: Path,
) -> None:
    """Raw provenance fails closed when a measured artifact changes."""
    _write_campaign(tmp_path)
    (tmp_path / "rep-03" / "source_catalog.fits").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="byte size changed"):
        _compile(tmp_path)


def test_compile_pybdsf_campaign_rejects_protocol_drift(
    tmp_path: Path,
) -> None:
    """A repetition cannot silently change environment or configuration."""
    _write_campaign(tmp_path)
    run_path = tmp_path / "rep-04" / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["ncores"] = 8
    run_path.write_text(json.dumps(run), encoding="utf-8")

    with pytest.raises(ValueError, match="ncores"):
        _compile(tmp_path)


def test_compile_pybdsf_campaign_requires_complete_tool_identity(
    tmp_path: Path,
) -> None:
    """Every provenance-critical baseline tool must be identified."""
    _write_campaign(tmp_path)
    index_path = tmp_path / "baseline-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    del index["tool_sha256"]["reference_runner"]
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="tool SHA-256 set is incomplete"):
        _compile(tmp_path)


@pytest.mark.parametrize("digest", ["a" * 63, "g" * 64])
def test_compile_pybdsf_campaign_rejects_invalid_tool_digest(
    tmp_path: Path,
    digest: str,
) -> None:
    """Baseline tool identities must be complete lowercase SHA-256 values."""
    _write_campaign(tmp_path)
    index_path = tmp_path / "baseline-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["tool_sha256"]["campaign_runner"] = digest
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="tool SHA-256 is invalid"):
        _compile(tmp_path)


def test_phase_zero_representative_inventory_matches_evidence() -> None:
    """Every restricted representative input is bound to reviewed evidence."""
    root = Path(__file__).parents[3]
    baseline_directory = root / "config" / "baselines"
    inventory = json.loads(
        (baseline_directory / "phase-0-representative-dataset.json").read_text(
            encoding="utf-8"
        )
    )
    input_sha256 = {
        name: item["sha256"] for name, item in inventory["inputs"].items()
    }
    evidence = load_evidence(
        baseline_directory
        / "phase-0-pybdsf-release-representative-evidence.json"
    )

    assert isinstance(evidence, BenchmarkEvidence)
    assert set(input_sha256) == {
        "apparent_skymodel",
        "beam_ms_0",
        "flat_noise_image",
        "true_sky_image",
        "true_skymodel",
        "vertices",
    }
    assert _canonical_sha256(input_sha256) == inventory["content_sha256"]
    assert evidence.dataset.content_sha256 == inventory["content_sha256"]
    assert evidence.dataset.shape_yx == tuple(inventory["shape_yx"])


def test_phase_zero_starting_inventory_captures_runtime() -> None:
    """The baseline inventory no longer leaves runtime identity unresolved."""
    root = Path(__file__).parents[3]
    inventory = json.loads(
        (
            root / "config" / "baselines" / "phase-0-starting-revisions.json"
        ).read_text(encoding="utf-8")
    )

    assert inventory["status"] == "captured"
    assert (
        inventory["declared_dependencies"]["rapthor_pybdsf"][
            "installed_version"
        ]
        == "1.14.1"
    )
    assert inventory["container_definitions"]["reference_runtime"][
        "built_image_digest"
    ].startswith("sha256:")
    assert inventory["master_wheel"]["sha256"] == (
        "2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d"
    )


def test_phase_zero_reference_environments_bind_tools_and_packages() -> None:
    """Corrected baselines retain durable sanitized runtime provenance."""
    root = Path(__file__).parents[3]
    record = json.loads(
        (
            root
            / "config"
            / "baselines"
            / "phase-0-reference-environments.json"
        ).read_text(encoding="utf-8")
    )

    assert record["configuration"]["threshold_pixel_sigma"] == 5.0
    assert record["configuration"]["threshold_island_sigma"] == 3.0
    assert record["lsmtool_checkout"]["commit"] == (
        "3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a"
    )
    expected_tools = {
        "campaign_runner": "run_phase0_pybdsf_baseline.py",
        "evidence_compiler": "compile_phase0_pybdsf_evidence.py",
        "reference_runner": "pybdsf_reference_run.py",
    }
    for name, filename in expected_tools.items():
        path = root / "scripts" / "benchmark" / filename
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == record["tool_sha256"][name]
        )
    release_packages = record["environments"]["release"][
        "installed_distributions"
    ]
    master_packages = record["environments"]["master"][
        "installed_distributions"
    ]
    assert {"name": "bdsf", "version": "1.14.1"} in release_packages
    assert {
        "name": "bdsf",
        "version": "1.14.2.dev40+gc70103be3",
    } in master_packages
