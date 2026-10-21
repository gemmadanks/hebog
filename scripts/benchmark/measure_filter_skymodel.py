#!/usr/bin/env python3
"""Measure Rapthor's filter step: Hebog against pinned PyBDSF master.

Plan task 23's matched benchmark. The sector's inputs are written once from
a real image (``hebog.validation.filter_benchmark``). Each warm-up and
measured repetition then runs ``filter_skymodel_worker.py`` in a fresh
container of the matched benchmark image
(``scripts/benchmark/containers/filter-skymodel``) on the same cores,
alternating Rapthor's native Hebog task and its PyBDSF subprocess so that
drift affects both. Every run has its own working directory holding a copy
of the inputs, as Rapthor's pipeline directory does.

Under ``benchmark-results/filter-skymodel/runs/<label>/`` it writes the
sector, each run's directory and ``run.json``, one evidence document per
finder, and ``report.json``: each finder's timings, the ratio of the
finder-part medians (the task's start to LSMTool's ``filter_sources`` call,
the span the finder controls) with its one-sided 95% bootstrap bounds
against the deployment gate's limit for the sector's class, dense or sparse
by the sources in ``master``'s catalogue
(``config/benchmarks/phase-0-performance.json``), the complete step's ratio
beside it, whether each finder's
catalogue, RMS maps and mask repeated byte for byte, and the identities of
the image, inputs and software::

    uv run python scripts/benchmark/measure_filter_skymodel.py \\
        --container-image IMAGE --beam-ms MEASUREMENT_SET --label LABEL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import hebog
from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.contracts import (
    PyBdsfMasterGate,
    load_performance_matrix,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    DatasetIdentity,
    ExecutorKind,
    ResourceAllocation,
    SoftwareIdentity,
    WorkloadClass,
    write_evidence,
)
from hebog.validation.execution_profile import load_profile_configuration
from hebog.validation.filter_benchmark import SectorInputs, write_sector_inputs
from hebog.validation.quick_benchmark import (
    ProcessUsage,
    Repetition,
    benchmark_evidence,
    compare_with_pybdsf_master,
    local_resources,
    median_ratio,
    summarise_timings,
)
from hebog.validation.quick_check import (
    GeneratedCase,
    ImageCase,
    file_sha256,
    load_quick_check_configuration,
    prepare_case,
)
from hebog.validation.rapthor_agreement import load_agreement_configuration

_ROOT = Path(__file__).resolve().parents[2]
_WORKER = Path(__file__).with_name("filter_skymodel_worker.py")
_AGREEMENT = _ROOT / "config/checks/rapthor-agreement.json"
_SCALING_PROFILE = _ROOT / "config/benchmarks/sector-scaling-profile.json"
_SOURCE_COUNT_LADDER = _ROOT / "config/benchmarks/source-count-ladder.json"
_PERFORMANCE = _ROOT / "config/benchmarks/phase-0-performance.json"
_DEFAULT_CASE = "lotss-dr3-1312-3000"
_FINDERS = ("bdsf", "hebog")
# Products that must repeat byte for byte. LSMTool stamps its sky models
# with the time, and the diagnostics record timings and memory.
_STABLE_PRODUCTS = (
    "flat_noise_rms",
    "true_sky_rms",
    "source_catalog",
    "source_filtering_mask",
)
_BOOTSTRAP_RESAMPLES = 10_000


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument(
        "--case",
        default=_DEFAULT_CASE,
        help=(
            "an image case of the Rapthor agreement configuration, the "
            "sector scaling profile or the source-count ladder"
        ),
    )
    parser.add_argument(
        "--beam-ms",
        type=Path,
        help="a Measurement Set: Rapthor's production two-pass mode",
    )
    parser.add_argument(
        "--container-image",
        required=True,
        help="the benchmark image, which holds the Hebog and Rapthor measured",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_ROOT / "benchmark-results/filter-skymodel",
    )
    parser.add_argument("--label", required=True)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--threshpix", type=float, default=5.0)
    parser.add_argument("--threshisl", type=float, default=3.0)
    parser.add_argument("--island-sigma", type=float, default=3.0)
    parser.add_argument("--peak-sigma", type=float, default=5.0)
    parser.add_argument("--margin", type=float, default=0.05)
    parser.add_argument(
        "--hebog-dask-workers",
        type=int,
        help=(
            "run Hebog's native task on this many single-threaded Dask "
            "worker processes instead of Rapthor's threads (a screening "
            "measurement: Rapthor has no Dask path for Hebog yet)"
        ),
    )
    return parser.parse_args(argv)


def _case(case_id: str) -> tuple[GeneratedCase | ImageCase, Path]:
    """Return one image case and the dataset manifest that identifies it."""
    agreement = load_agreement_configuration(_AGREEMENT)
    quick_check = load_quick_check_configuration(_ROOT / agreement.quick_check)
    cases: dict[str, tuple[GeneratedCase | ImageCase, Path]] = {
        item.case.case_id: (item.case, _ROOT / quick_check.dataset_manifest)
        for item in agreement.cases
    }
    for path in (_SCALING_PROFILE, _SOURCE_COUNT_LADDER):
        profile = load_profile_configuration(path)
        cases |= {
            item.case.case_id: (item.case, _ROOT / profile.dataset_manifest)
            for item in profile.cases
        }
    if case_id not in cases:
        raise ValueError(
            f"unknown case {case_id}; choose one of {', '.join(cases)}"
        )
    return cases[case_id]


def _case_image(case_id: str) -> Path:
    """Return the prepared input of one image case."""
    case, dataset_manifest = _case(case_id)
    return prepare_case(
        case,
        dataset_manifest=dataset_manifest,
        repository_root=_ROOT,
        inputs_root=_ROOT / "benchmark-results/quick-check/inputs",
    ).input_path


def _podman(*arguments: str) -> str:
    return subprocess.run(
        ["podman", *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def _image_identity(image: str) -> dict[str, Any]:
    """Return the image's identity and the memory its containers share.

    The memory is that of Podman's virtual machine, which no container
    limit narrows.
    """
    inventory = _podman(
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network=none",
        image,
        "python",
        "-m",
        "pip",
        "list",
        "--format=json",
    )
    labels = json.loads(
        _podman("image", "inspect", "--format", "{{json .Labels}}", image)
    )
    return {
        "image": image,
        "id": _podman("image", "inspect", "--format", "{{.Id}}", image),
        "digest": _podman(
            "image", "inspect", "--format", "{{.Digest}}", image
        ),
        "rapthor_revision": labels.get("org.hebog.rapthor-revision", ""),
        "dependency_inventory_sha256": hashlib.sha256(
            inventory.encode()
        ).hexdigest(),
        "memory_bytes": int(_podman("info", "--format", "{{.Host.MemTotal}}")),
    }


def _run(
    args: argparse.Namespace,
    sector: SectorInputs,
    beam_ms: Path | None,
    directory: Path,
    finder: str,
) -> dict[str, Any]:
    """Run one repetition of one finder in a fresh container."""
    shutil.copytree(sector.directory, directory)
    if beam_ms is not None:
        shutil.copytree(beam_ms, directory / "beam.ms")
    subprocess.run(
        _container_command(
            args, directory, finder, beam_ms=beam_ms is not None
        ),
        check=True,
    )
    run: dict[str, Any] = json.loads(
        (directory / "run.json").read_text(encoding="utf-8")
    )
    print(
        f"{directory.name}: {run['wall_seconds']:.1f} s, "
        f"{run['nsources']} sources",
        flush=True,
    )
    return run


def _container_command(
    args: argparse.Namespace, directory: Path, finder: str, *, beam_ms: bool
) -> list[str]:
    """Return the command that runs one finder's filter step in a container.

    ``directory`` holds the sector's inputs, and with ``beam_ms`` its
    Measurement Set as ``beam.ms``.
    """
    command = [
        "podman",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network=none",
        "--cpus",
        str(args.cores),
        "--volume",
        f"{directory}:/sector",
        "--volume",
        f"{_WORKER}:/worker.py:ro",
        args.container_image,
        "python",
        "/worker.py",
        "--finder",
        finder,
        "--directory",
        "/sector",
        "--ncores",
        str(args.cores),
        "--threshpix",
        str(args.threshpix),
        "--threshisl",
        str(args.threshisl),
    ]
    if beam_ms:
        command += ["--beam-ms", "/sector/beam.ms"]
    if finder == "hebog" and args.hebog_dask_workers is not None:
        command += ["--dask-workers", str(args.hebog_dask_workers)]
    return command


def _finder_resources(
    finder: str, *, cores: int, dask_workers: int | None, memory_bytes: int
) -> ResourceAllocation:
    """Describe how one finder ran on the container's cores and memory.

    ``master`` and Rapthor's native Hebog task each run one process with a
    thread a core. With ``dask_workers`` Hebog instead runs that many
    single-threaded worker processes, each limited to an equal share of the
    memory.
    """
    if finder == "hebog" and dask_workers is not None:
        return ResourceAllocation(
            executor=ExecutorKind.DASK,
            worker_nodes=1,
            workers_per_node=dask_workers,
            threads_per_worker=1,
            allocated_cpu_cores=cores,
            node_memory_bytes=memory_bytes,
            worker_memory_limit_bytes=memory_bytes // dask_workers,
            reserved_headroom_per_node_bytes=0,
            storage_identifier="local-filesystem",
        )
    return local_resources(
        ExecutorKind.LOCAL if finder == "hebog" else ExecutorKind.EXTERNAL,
        allocated_cpu_cores=cores,
        memory_bytes=memory_bytes,
    )


def _tree_sha256(directory: Path) -> str:
    """Hash a Measurement Set's relative file names and bytes.

    CASA's ``table.lock`` files change whenever a table is opened, so they
    are left out, as in the Phase 0 baselines.
    """
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "table.lock":
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _repeated(runs: Sequence[dict[str, Any]]) -> dict[str, bool]:
    """Return whether each stable product repeated across the runs."""
    return {
        name: len(
            {
                None
                if run["products"][name] is None
                else run["products"][name]["sha256"]
                for run in runs
            }
        )
        == 1
        for name in _STABLE_PRODUCTS
    }


def _compare_phases(
    runs: Mapping[str, Sequence[Mapping[str, Any]]],
    gate: PyBdsfMasterGate,
    *,
    resamples: int,
) -> dict[str, Any]:
    """Apply the gate to the finder's span and report the whole step.

    The gate's ``measured_phase`` is the source-finding part of Rapthor's
    step, from the task's start to LSMTool's ``filter_sources`` call, the
    span the finder controls. Its limit is the sector class's, from the
    sources in ``master``'s catalogue, which every measured run must agree
    on. The complete step, whose LSMTool filtering is the same for either
    finder, is reported beside it and never gated. Warm-up repetitions
    count for neither.
    """
    measured = {
        finder: [run for run in finder_runs if not run["warmup"]]
        for finder, finder_runs in runs.items()
    }
    master_source_counts = sorted(
        {run["catalogue_rows"] for run in measured["bdsf"]}
    )
    if len(master_source_counts) != 1:
        raise ValueError(
            "master's catalogue changed between runs: "
            f"{', '.join(map(str, master_source_counts))} sources"
        )
    master_source_count = master_source_counts[0]
    phase = f"{gate.measured_phase}_seconds"
    gated = compare_with_pybdsf_master(
        [run[phase] for run in measured["hebog"]],
        [run[phase] for run in measured["bdsf"]],
        gate,
        master_source_count=master_source_count,
        resamples=resamples,
    )
    complete = median_ratio(
        [run["wall_seconds"] for run in measured["hebog"]],
        [run["wall_seconds"] for run in measured["bdsf"]],
        resamples=resamples,
        confidence_level=gate.confidence_level,
    )
    return {
        "phase": gate.measured_phase,
        "master_source_count": master_source_count,
        "sector_class": gate.sector_class(master_source_count),
        "ratio": gated.ratio.ratio,
        "lower_bound": gated.ratio.lower_bound,
        "upper_bound": gated.ratio.upper_bound,
        "maximum_ratio": gate.maximum_ratio(master_source_count),
        "outcome": gated.outcome,
        "complete_step": {
            "ratio": complete.ratio,
            "lower_bound": complete.lower_bound,
            "upper_bound": complete.upper_bound,
        },
    }


def main() -> int:
    """Run the matched benchmark and write its evidence and report."""
    args = _parse_args()
    # Podman mounts need absolute paths.
    root = (args.output_root / "runs" / args.label).resolve()
    if root.exists():
        raise FileExistsError(f"{root} already exists")
    image = _case_image(args.case)
    sector = write_sector_inputs(
        image,
        root / "sector",
        island_sigma=args.island_sigma,
        peak_sigma=args.peak_sigma,
        margin_fraction=args.margin,
    )
    print(
        f"{args.case}: {sector.component_count} WSClean-like components",
        flush=True,
    )
    container = _image_identity(args.container_image)
    runs: dict[str, list[dict[str, Any]]] = {finder: [] for finder in _FINDERS}
    for index in range(args.warmups + args.repetitions):
        # Alternate which finder goes first, so drift affects both alike.
        order = _FINDERS if index % 2 == 0 else _FINDERS[::-1]
        for finder in order:
            run = _run(
                args,
                sector,
                args.beam_ms,
                root / "runs" / f"{index:02d}-{finder}",
                finder,
            )
            runs[finder].append(run | {"warmup": index < args.warmups})
    gate = load_performance_matrix(_PERFORMANCE).pybdsf_master
    measured = {
        finder: [
            run["wall_seconds"] for run in finder_runs if not run["warmup"]
        ]
        for finder, finder_runs in runs.items()
    }
    comparison = _compare_phases(runs, gate, resamples=_BOOTSTRAP_RESAMPLES)
    configuration = {
        "case": args.case,
        "image_sha256": file_sha256(image),
        "cores": args.cores,
        "threshpix": args.threshpix,
        "threshisl": args.threshisl,
        "island_sigma": args.island_sigma,
        "peak_sigma": args.peak_sigma,
        "margin_fraction": args.margin,
        "beam_ms": None
        if args.beam_ms is None
        else {
            "name": args.beam_ms.name,
            "tree_sha256": _tree_sha256(args.beam_ms),
        },
        "command_profile": "off",
        "hebog_dask_workers": args.hebog_dask_workers,
    }
    configuration_sha256 = canonical_sha256(configuration)
    dataset = DatasetIdentity(
        identifier=args.case,
        role=DatasetRole.DEVELOPMENT,
        content_sha256=file_sha256(sector.true_sky_image_path),
        shape_yx=sector.shape_yx,
        workload_class=WorkloadClass.NORMAL,
    )
    captured_at = datetime.now(UTC)
    versions = runs["hebog"][0]["versions"]
    subjects = {
        "hebog": SoftwareIdentity(
            name="hebog",
            version=hebog.__version__,
            container_image_digest=container["digest"] or None,
            dependency_inventory_sha256=container[
                "dependency_inventory_sha256"
            ],
        ),
        "bdsf": SoftwareIdentity(
            name="pybdsf-master",
            version=versions["bdsf"],
            commit_sha=gate.commit_sha,
            container_image_digest=container["digest"] or None,
            dependency_inventory_sha256=container[
                "dependency_inventory_sha256"
            ],
        ),
    }
    for finder, finder_runs in runs.items():
        write_evidence(
            root / f"{subjects[finder].name}-evidence.json",
            benchmark_evidence(
                run_id=f"{args.label}-{finder}",
                captured_at=captured_at,
                dataset=dataset,
                configuration_sha256=configuration_sha256,
                subject=subjects[finder],
                environment_sha256=container["dependency_inventory_sha256"],
                resources=_finder_resources(
                    finder,
                    cores=args.cores,
                    dask_workers=args.hebog_dask_workers,
                    memory_bytes=container["memory_bytes"],
                ),
                finder_stage="rapthor-filter-skymodel-products",
                repetitions=[
                    Repetition(
                        warmup=run["warmup"],
                        complete=ProcessUsage(
                            wall_seconds=run["wall_seconds"],
                            cpu_seconds=run["cpu_seconds"],
                            peak_rss_bytes=run["peak_rss_bytes"],
                        ),
                        # The finder's span; the worker records no CPU or
                        # RSS per phase, so those are the whole run's.
                        finder=ProcessUsage(
                            wall_seconds=run["finder_seconds"],
                            cpu_seconds=run["cpu_seconds"],
                            peak_rss_bytes=run["peak_rss_bytes"],
                        ),
                    )
                    for run in finder_runs
                ],
            ),
        )
    report = {
        "schema_version": 1,
        "label": args.label,
        "created_at": captured_at.isoformat(),
        "configuration": configuration,
        "configuration_sha256": configuration_sha256,
        "component_count": sector.component_count,
        "shape_yx": list(sector.shape_yx),
        "container": container,
        "versions": versions,
        "timings": {
            finder: asdict(summarise_timings(values))
            for finder, values in measured.items()
        },
        "phase_medians_seconds": {
            finder: {
                phase: statistics.median(
                    run[phase] for run in finder_runs if not run["warmup"]
                )
                for phase in ("finder_seconds", "filter_sources_seconds")
            }
            for finder, finder_runs in runs.items()
        },
        "comparison": comparison,
        "products_repeated": {
            finder: _repeated(
                [run for run in finder_runs if not run["warmup"]]
            )
            for finder, finder_runs in runs.items()
        },
        "runs": runs,
    }
    (root / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    complete = comparison["complete_step"]
    print(
        f"Hebog / PyBDSF master {comparison['phase']}-part median ratio "
        f"{comparison['ratio']:.3f} (one-sided 95% bounds "
        f"{comparison['lower_bound']:.3f} to "
        f"{comparison['upper_bound']:.3f}); "
        f"{comparison['sector_class']} sector "
        f"({comparison['master_source_count']} sources in master's "
        f"catalogue), gate {comparison['maximum_ratio']}: "
        f"{comparison['outcome']}; complete step "
        f"{complete['ratio']:.3f} ({complete['lower_bound']:.3f} to "
        f"{complete['upper_bound']:.3f}), reported beside the gate",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
