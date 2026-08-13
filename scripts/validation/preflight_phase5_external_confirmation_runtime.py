#!/usr/bin/env python3
"""Exercise the reviewed two-lane container resource bound without science."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from time import monotonic

_WORKLOAD = (
    "import hashlib,numpy as np; "
    "from scipy.ndimage import gaussian_filter; "
    "a=np.random.default_rng(20260813).normal(size=(1536,1536)); "
    "a=gaussian_filter(a,1.5); a=gaussian_filter(a,3.0); "
    "a=gaussian_filter(a,6.0); "
    "print(hashlib.sha256(a.tobytes()).hexdigest())"
)
_PAIRS = (
    ("released-pybdsf", "hebog"),
    ("pinned-pybdsf-master", "hebog"),
    ("released-pybdsf", "aegean"),
)


@dataclass(frozen=True, slots=True)
class Probe:
    """One immutable, non-scientific container probe result."""

    finder_id: str
    wall_seconds: float
    output_sha256: str


def _command(podman: str, image: str, *, cpu_count: int) -> tuple[str, ...]:
    """Build one network-disabled, CPU-bounded probe command."""
    return (
        podman,
        "run",
        "--rm",
        "--network=none",
        "--cpus",
        str(cpu_count),
        "--entrypoint",
        "python3",
        image,
        "-c",
        _WORKLOAD,
    )


def _run(finder_id: str, command: tuple[str, ...]) -> Probe:
    """Execute and validate one bounded deterministic probe."""
    started = monotonic()
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    wall_seconds = monotonic() - started
    if completed.returncode != 0:
        raise RuntimeError(
            f"runtime probe failed for {finder_id}: {completed.stderr.strip()}"
        )
    output = completed.stdout.strip()
    if len(output) != hashlib.sha256().digest_size * 2:
        raise ValueError(f"runtime probe output changed for {finder_id}")
    try:
        int(output, 16)
    except ValueError as error:
        raise ValueError(
            f"runtime probe output changed for {finder_id}"
        ) from error
    return Probe(finder_id, wall_seconds, output)


def run_matrix(images: dict[str, str], *, podman: str) -> dict[str, object]:
    """Compare isolated and two-lane execution for every resource pairing."""
    serial: dict[str, Probe] = {}
    for finder_id, cpu_count in (
        ("released-pybdsf", 4),
        ("pinned-pybdsf-master", 4),
        ("hebog", 1),
        ("aegean", 1),
    ):
        serial[finder_id] = _run(
            finder_id,
            _command(podman, images[finder_id], cpu_count=cpu_count),
        )
    pairs: list[dict[str, object]] = []
    for pybdsf, companion in _PAIRS:
        started = monotonic()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(
                    _run,
                    pybdsf,
                    _command(podman, images[pybdsf], cpu_count=4),
                ),
                executor.submit(
                    _run,
                    companion,
                    _command(podman, images[companion], cpu_count=1),
                ),
            )
            concurrent = tuple(future.result() for future in futures)
        concurrent_wall = monotonic() - started
        for probe in concurrent:
            if probe.output_sha256 != serial[probe.finder_id].output_sha256:
                raise ValueError(
                    f"concurrent output changed for {probe.finder_id}"
                )
        isolated_sum = sum(
            serial[probe.finder_id].wall_seconds for probe in concurrent
        )
        if concurrent_wall >= isolated_sum:
            raise RuntimeError(
                f"two-lane probe has no overlap for {pybdsf}/{companion}"
            )
        pairs.append(
            {
                "pybdsf": pybdsf,
                "companion": companion,
                "wall_seconds": concurrent_wall,
                "isolated_sum_seconds": isolated_sum,
                "overlap_ratio": concurrent_wall / isolated_sum,
                "results": [asdict(item) for item in concurrent],
            }
        )
    return {
        "schema_version": 1,
        "status": "pass-non-scientific-two-lane-resource-probe",
        "cpu_budget": {"host": 6, "pybdsf": 4, "companion": 1},
        "network_disabled": True,
        "fresh_containers": True,
        "serial": {key: asdict(value) for key, value in serial.items()},
        "pairs": pairs,
        "scientific_evidence": False,
    }


def _parse_args() -> argparse.Namespace:
    """Parse exact local images without permitting a changed matrix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hebog-image", required=True)
    parser.add_argument("--released-pybdsf-image", required=True)
    parser.add_argument("--master-pybdsf-image", required=True)
    parser.add_argument("--aegean-image", required=True)
    parser.add_argument("--podman", default="podman")
    return parser.parse_args()


def main() -> None:
    """Execute the bounded development matrix and print its result."""
    arguments = _parse_args()
    result = run_matrix(
        {
            "hebog": arguments.hebog_image,
            "released-pybdsf": arguments.released_pybdsf_image,
            "pinned-pybdsf-master": arguments.master_pybdsf_image,
            "aegean": arguments.aegean_image,
        },
        podman=arguments.podman,
    )
    print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
