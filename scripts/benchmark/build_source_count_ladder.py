#!/usr/bin/env python3
"""Build the source-count ladder's noise-raised rungs.

``config/benchmarks/source-count-ladder-noise.json`` names a base case of
``config/benchmarks/source-count-ladder.json``, a seed and the rungs. The
base window is prepared as the benchmarks prepare it, and each rung is
written where the ladder's case of the same ID reads it: the base window
with its robust RMS raised by the rung's factor, by noise smoothed with the
window's restoring beam (``hebog.validation.source_count_ladder``). Every
rung uses the one seed, so each holds the same noise pattern at its own
level. A rung already written is kept. The rungs share one directory, and
``manifest.json`` there records each rung's checksum and robust RMS, the
base's checksum, the seed and the beam::

    uv run python scripts/benchmark/build_source_count_ladder.py
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.validation.execution_profile import load_profile_configuration
from hebog.validation.quick_check import ImageCase, file_sha256, prepare_case
from hebog.validation.source_count_ladder import (
    load_ladder_noise_configuration,
    raise_noise,
    robust_rms,
)

_ROOT = Path(__file__).resolve().parents[2]
_LADDER = _ROOT / "config/benchmarks/source-count-ladder.json"
_NOISE = _ROOT / "config/benchmarks/source-count-ladder-noise.json"
_INPUTS = _ROOT / "benchmark-results/quick-check/inputs"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ladder", type=Path, default=_LADDER)
    parser.add_argument("--noise", type=Path, default=_NOISE)
    parser.add_argument("--inputs-root", type=Path, default=_INPUTS)
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="fetch a missing base image",
    )
    return parser.parse_args()


def _beam_fwhm_pixels(header: fits.Header) -> float:
    """Return a circular restoring beam's width in pixels."""
    major, minor = float(header["BMAJ"]), float(header["BMIN"])
    if not np.isclose(major, minor):
        raise ValueError("the noise rungs need a circular restoring beam")
    return major / abs(float(header["CDELT2"]))


def main() -> int:
    """Write every missing rung and the manifest."""
    args = _parse_args()
    ladder = load_profile_configuration(args.ladder)
    noise = load_ladder_noise_configuration(args.noise)
    cases = {item.case.case_id: item.case for item in ladder.cases}
    prepared = prepare_case(
        cases[noise.base_case],
        dataset_manifest=_ROOT / ladder.dataset_manifest,
        repository_root=_ROOT,
        inputs_root=args.inputs_root,
        allow_download=args.allow_download,
    )
    with fits.open(prepared.input_path) as hdus:
        primary = cast(Any, hdus[0])
        header = primary.header.copy()
        values = np.asarray(primary.data, dtype=np.float32)
    beam_fwhm_pixels = _beam_fwhm_pixels(header)
    rungs = []
    targets = []
    for rung in noise.rungs:
        case = cases[rung.case_id]
        if not isinstance(case, ImageCase):
            raise TypeError(f"{rung.case_id} is not an image case")
        target = _ROOT / case.image
        targets.append(target)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = target.with_name(f".{target.name}.partial")
            fits.PrimaryHDU(
                data=raise_noise(
                    values,
                    factor=rung.noise_factor,
                    beam_fwhm_pixels=beam_fwhm_pixels,
                    seed=noise.seed,
                ),
                header=header,
            ).writeto(staged, overwrite=True)
            os.replace(staged, target)
        with fits.open(target) as hdus:
            written = np.asarray(cast(Any, hdus[0]).data)
        rungs.append(
            {
                "case_id": rung.case_id,
                "noise_factor": rung.noise_factor,
                "sha256": file_sha256(target),
                "robust_rms": robust_rms(written),
            }
        )
        print(f"{rung.case_id}: x{rung.noise_factor}", flush=True)
    manifest = {
        "schema_version": 1,
        "base_case": noise.base_case,
        "base_input_sha256": prepared.input_sha256,
        "base_robust_rms": robust_rms(values),
        "beam_fwhm_pixels": beam_fwhm_pixels,
        "seed": noise.seed,
        "rungs": rungs,
    }
    (directory,) = {target.parent for target in targets}
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
