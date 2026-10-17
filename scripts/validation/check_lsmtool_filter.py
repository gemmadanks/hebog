#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Run pinned LSMTool's filter_sources on the Rapthor adapter's products.

The adapter runs one sector's true-sky and flat-noise images under the
Serial, Thread and Dask executors, each into its own directory.
``plan_filter_inputs`` writes a sector polygon and WSClean-style sky models
from the serial run's island mask, and the LSMTool container
(``scripts/validation/containers/lsmtool``) filters every executor's
products with them, as Rapthor's step will after calling the adapter. The
check passes when LSMTool keeps, groups and transfers exactly what the mask
decides and every executor's products give the same result; it writes
``report.json`` in the output directory and exits 1 otherwise. The adapter
runs with its default profile and background unless ``--profile`` or
``--background`` chooses another. An output
directory that holds a finished run is reused through the adapter's retry
reuse::

    uv run python scripts/validation/check_lsmtool_filter.py \\
        --true-sky TRUE.fits --flat-noise FLAT.fits --output DIRECTORY
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import replace
from pathlib import Path
from time import monotonic

from distributed import Client, LocalCluster

import hebog
from hebog.adapters import (
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    RapthorSourceFindingResult,
    find_sector_sources,
)
from hebog.executors import (
    DaskExecutor,
    Executor,
    SerialExecutor,
    ThreadExecutor,
)
from hebog.validation.lsmtool_filter import (
    FilterOutcome,
    FilterPlan,
    filter_failures,
    plan_filter_inputs,
)

_WORKER = Path(__file__).with_name("lsmtool_filter_worker.py")


def _executors(
    cores: int,
) -> dict[str, Callable[[], AbstractContextManager[Executor]]]:
    @contextmanager
    def serial() -> Generator[Executor]:
        yield SerialExecutor()

    @contextmanager
    def threads() -> Generator[Executor]:
        with ThreadExecutor(thread_count=cores) as executor:
            yield executor

    @contextmanager
    def dask() -> Generator[Executor]:
        with (
            LocalCluster(
                n_workers=cores,
                threads_per_worker=1,
                processes=True,
                dashboard_address=":0",
            ) as cluster,
            Client(cluster) as client,
        ):
            yield DaskExecutor(client)

    return {"serial": serial, "threads": threads, "dask": dask}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _filter(
    image: str,
    output: Path,
    result: RapthorSourceFindingResult,
    plan: FilterPlan,
) -> FilterOutcome:
    """Filter one executor's products in the container."""
    summary = result.products_directory.parent / "lsmtool"

    def in_container(path: Path) -> str:
        return f"/work/{path.relative_to(output).as_posix()}"

    subprocess.run(
        [
            "podman",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--volume",
            f"{output}:/work",
            "--volume",
            f"{_WORKER}:/worker.py:ro",
            image,
            "python",
            "/worker.py",
            in_container(result.mask_path),
            in_container(plan.vertices_path),
            in_container(plan.true_sky_model_path),
            in_container(plan.apparent_sky_model_path),
            in_container(summary),
        ],
        check=True,
    )
    return FilterOutcome.read(summary / "summary.json")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument("--true-sky", type=Path, required=True)
    parser.add_argument("--flat-noise", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="localhost/hebog-lsmtool:156ae6a")
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--threshpix", type=float, default=5.0)
    parser.add_argument("--threshisl", type=float, default=3.0)
    parser.add_argument("--margin", type=float, default=0.1)
    parser.add_argument("--islands", type=int, default=2_000)
    parser.add_argument("--decoys", type=int, default=20)
    parser.add_argument(
        "--executors",
        default="serial,threads,dask",
        help="comma-separated executors; the first one's mask is planned",
    )
    parser.add_argument(
        "--profile",
        choices=("compact", "continuum"),
        help="Hebog's science profile; by default the adapter's",
    )
    parser.add_argument(
        "--background",
        choices=("zero", "estimated"),
        help="Hebog's background; by default the adapter's",
    )
    return parser.parse_args(argv)


def _compatibility(
    arguments: argparse.Namespace,
) -> RapthorCompatibilityConfig:
    """Return the adapter settings the check runs every executor with."""
    defaults = RapthorCompatibilityConfig(
        threshpix=arguments.threshpix, threshisl=arguments.threshisl
    )
    return replace(
        defaults,
        profile=arguments.profile or defaults.profile,
        background=arguments.background or defaults.background,
    )


def main() -> int:
    """Run the check and report it."""
    arguments = _parse_args()
    output = arguments.output.absolute()
    # A finished run in an existing output is reused, not recomputed.
    output.mkdir(parents=True, exist_ok=True)
    config = _compatibility(arguments)
    results: dict[str, RapthorSourceFindingResult] = {}
    executors = _executors(arguments.cores)
    for name in arguments.executors.split(","):
        with executors[name]() as executor:
            results[name] = find_sector_sources(
                RapthorSourceFindingRequest(
                    true_sky_image_path=arguments.true_sky,
                    flat_noise_image_path=arguments.flat_noise,
                    output_root=output / name / "sector_1",
                    run_id="lsmtool-filter-check",
                ),
                config,
                executor,
            )
        print(
            f"{name}: {results[name].source_count} sources in "
            f"{results[name].wall_seconds:.1f} s",
            flush=True,
        )
    inputs = output / "inputs"
    plan = plan_filter_inputs(
        next(iter(results.values())).mask_path,
        arguments.true_sky,
        arguments.flat_noise,
        inputs,
        margin_fraction=arguments.margin,
        island_limit=arguments.islands,
        decoy_count=arguments.decoys,
    )
    outcomes = {}
    filter_seconds = {}
    for name, result in results.items():
        started = monotonic()
        outcomes[name] = _filter(arguments.image, output, result, plan)
        filter_seconds[name] = monotonic() - started
    failures = filter_failures(
        plan, outcomes, {name: r.mask_path for name, r in results.items()}
    )
    image_id = subprocess.run(
        ["podman", "image", "inspect", "--format", "{{.Id}}", arguments.image],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "hebog": hebog.__version__,
        "lsmtool_image": {"tag": arguments.image, "id": image_id},
        "true_sky_sha256": _sha256(arguments.true_sky),
        "flat_noise_sha256": _sha256(arguments.flat_noise),
        "settings": vars(arguments)
        | {
            "true_sky": arguments.true_sky.as_posix(),
            "flat_noise": arguments.flat_noise.as_posix(),
            "output": output.as_posix(),
        },
        "compatibility": {
            "profile": config.profile,
            "background": config.background,
        },
        "executors": {
            name: {
                "source_count": result.source_count,
                "island_count": result.island_count,
                "adapter_seconds": round(result.wall_seconds, 3),
                "filter_seconds": round(filter_seconds[name], 3),
            }
            for name, result in results.items()
        },
        "components": len(plan.components),
        "kept": len(plan.kept()),
        "patches": len(plan.groups()),
        "clipped": sum(component.clipped for component in plan.components),
        "decoys": sum(
            component.name.startswith("decoy") for component in plan.components
        ),
        "failures": failures,
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "executors",
                    "components",
                    "kept",
                    "patches",
                    "clipped",
                    "decoys",
                    "failures",
                )
            },
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
