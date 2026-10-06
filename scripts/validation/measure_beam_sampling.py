#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Measure source recovery against restoring-beam width on injected truth.

Each image holds isolated beam-shaped sources on a centred grid with a
192-pixel spacing, at least 112 pixels from every edge, each jittered by up
to 8 pixels. Peak SNR, against the per-pixel noise, cycles through 5, 10,
30, 100 and 300. The beam is circular. Noise comes from generator version 3,
either correlated at the beam or white: white noise uses a correlation of
0.01 pixel FWHM, whose filter is a unit impulse in double precision, so it
keeps version 3's independent realizations. Every image runs through the
public ``find_sources`` with the default thresholds (5, 3, 7) under each
requested profile, and published sources are matched to truth within one
beam FWHM by the project's matcher.

``find_sources`` refuses a restoring beam wider than its supported limit (10
pixels), so the default grid stops there. ``--lift-beam-limit-to P`` replaces
that limit with ``P`` pixels for the run, to measure beyond it: a
measurement-only override of the private ``public_api`` constant, never a
supported setting. A beam wider than 22 pixels can still fail mid-run, where
local-noise refinement exceeds its read bound.

``--fine-mesh-reference-beam B`` scales the fine mesh, which serves both
bright-source refinement and local-noise refinement, by ``max(1, FWHM / B)``:
its window, step, influence radius and transition width. It is a diagnostic
of the option to scale the meshes with the beam, not a supported setting.

One JSON line per run goes to ``runs.jsonl`` in ``--output``, and a rerun
skips the runs already recorded there. ``summary.json`` holds completeness
with 95% Wilson intervals by mesh, profile, noise, image size, beam and SNR,
and false detections per image and per thousand beam areas. This is
development evidence for task 62 (see ``LOG.md``), not qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
from astropy.io import fits

import hebog
from hebog import public_api
from hebog.executors import SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.validation.comparison import (
    compare_catalogues,
    wilson_score_interval,
)
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_image,
    recipe_sha256,
)
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.products import load_fits_plane
from hebog.validation.quick_check import (
    public_catalogue_sources,
    truth_catalogue,
)

_ROOT = Path(__file__).resolve().parents[2]
_NOISE_RMS = 1e-4
_PIXEL_SCALE_DEGREES = 1.5 / 3600.0
_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
_BEAM_AREA_PER_SQUARE_FWHM = math.pi / (4.0 * math.log(2.0))
_WHITE_CORRELATION_FWHM_PIXELS = 0.01
_SNRS = (5.0, 10.0, 30.0, 100.0, 300.0)
_BRIGHT_SNR = 10.0
_SPACING_PIXELS = 192
_MINIMUM_MARGIN_PIXELS = 112
_JITTER_PIXELS = 8.0
_MAXIMUM_SEPARATION_BEAMS = 1.0
_THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)

Noise = Literal["white", "correlated"]
Profile = Literal["continuum", "compact"]


@dataclass(frozen=True, slots=True)
class Run:
    """One image and the configuration that analyses it."""

    size: int
    beam_fwhm_pixels: float
    noise: Noise
    realization: int
    profile: Profile
    fine_mesh_reference_beam: float | None = None
    lifted_beam_limit_pixels: float | None = None

    @property
    def seed(self) -> int:
        """Return the noise seed, shared by every analysis of this image."""
        identity = (
            f"beam-sampling/{self.size}/{self.beam_fwhm_pixels:g}/"
            f"{self.noise}/{self.realization}"
        )
        digest = hashlib.sha256(identity.encode()).digest()
        return int.from_bytes(digest[:8], "big")

    @property
    def mesh(self) -> str:
        """Name the mesh variant the run uses."""
        if self.fine_mesh_reference_beam is None:
            return "default"
        return f"fine-scaled-above-{self.fine_mesh_reference_beam:g}"

    @property
    def key(self) -> str:
        """Identify the run in the results file."""
        return (
            f"{self.mesh}/{self.profile}/{self.noise}/{self.size}/"
            f"{self.beam_fwhm_pixels:g}/{self.realization}"
        )


def source_layout(
    size: int,
    beam_fwhm_pixels: float,
    *,
    realization: int,
    seed: int,
) -> list[dict[str, float]]:
    """Place isolated beam-shaped sources, cycling through the SNRs.

    The grid is centred, so its outer sources are at least the minimum
    margin from every edge before jitter. Successive realizations shift the
    SNR cycle by one, so an image with fewer sources than SNRs still covers
    every SNR equally over five realizations.
    """
    per_side = (size - 2 * _MINIMUM_MARGIN_PIXELS) // _SPACING_PIXELS + 1
    offset = (size - (per_side - 1) * _SPACING_PIXELS) / 2.0
    sigma = beam_fwhm_pixels / _FWHM_PER_SIGMA
    generator = np.random.default_rng(seed)
    sources: list[dict[str, float]] = []
    for index in range(per_side * per_side):
        row, column = divmod(index, per_side)
        jitter_x, jitter_y = generator.uniform(
            -_JITTER_PIXELS, _JITTER_PIXELS, size=2
        )
        x_pixel = offset + column * _SPACING_PIXELS + jitter_x
        y_pixel = offset + row * _SPACING_PIXELS + jitter_y
        snr = _SNRS[(index + realization) % len(_SNRS)]
        sources.append(
            {
                "x_pixel": round(x_pixel, 4),
                "y_pixel": round(y_pixel, 4),
                "peak_flux_jy_per_beam": snr * _NOISE_RMS,
                "major_sigma_pixels": sigma,
                "minor_sigma_pixels": sigma,
                "rotation_degrees_counterclockwise_from_x": 0.0,
            }
        )
    return sources


def dataset_record(run: Run) -> DatasetRecord:
    """Return the governed dataset record for the run's image."""
    correlation = (
        run.beam_fwhm_pixels
        if run.noise == "correlated"
        else _WHITE_CORRELATION_FWHM_PIXELS
    )
    recipe = SyntheticRecipe.model_validate(
        {
            "generator": "hebog.synthetic.gaussian-noise",
            "generator_version": 3,
            "seed": run.seed,
            "shape_yx": [run.size, run.size],
            "background": 0.0,
            "noise_rms": _NOISE_RMS,
            "sources": source_layout(
                run.size,
                run.beam_fwhm_pixels,
                realization=run.realization,
                seed=run.seed,
            ),
            "noise_correlation": {
                "major_fwhm_pixels": correlation,
                "minor_fwhm_pixels": correlation,
                "position_angle_degrees": 0.0,
            },
        }
    )
    centre = (run.size - 1) / 2.0
    return DatasetRecord.model_validate(
        {
            "identifier": "beam-sampling",
            "role": "development",
            "purpose": "Source recovery against restoring-beam width.",
            "provenance": "scripts/validation/measure_beam_sampling.py",
            "redistribution": "generated-locally",
            "beam": {
                "major_fwhm_pixels": run.beam_fwhm_pixels,
                "minor_fwhm_pixels": run.beam_fwhm_pixels,
                "position_angle_degrees": 0.0,
            },
            "wcs": {
                "reference_pixel_xy": [centre, centre],
                "reference_sky_degrees": [180.0, 45.0],
                "pixel_scale_degrees_xy": [
                    -_PIXEL_SCALE_DEGREES,
                    _PIXEL_SCALE_DEGREES,
                ],
            },
            "expected_statistics": {
                "background_jy_per_beam": 0.0,
                "noise_rms_jy_per_beam": _NOISE_RMS,
                "finite_fraction": 1.0,
            },
            "recipe": recipe.model_dump(mode="json"),
            "recipe_sha256": recipe_sha256(recipe),
        }
    )


@contextmanager
def scaled_fine_mesh(factor: float) -> Iterator[None]:
    """Scale the installed fine mesh geometry while the context is open.

    ``hebog.science.continuum`` binds ``source_finder_configs`` at import
    time, so both modules are patched, and both are restored on exit. A
    factor of one returns the installed configuration value for value.
    """
    from hebog.science import configuration, continuum  # noqa: PLC0415

    installed = configuration.source_finder_configs

    def scaled() -> Any:
        configs = list(installed())
        detection = configs[0]
        background = detection.background_rms
        adaptive = background.adaptive
        assert adaptive is not None
        grid = adaptive.grid
        configs[0] = replace(
            detection,
            background_rms=replace(
                background,
                adaptive=replace(
                    adaptive,
                    grid=replace(
                        grid,
                        window_shape_yx=tuple(
                            round(value * factor)
                            for value in grid.window_shape_yx
                        ),
                        step_yx=tuple(
                            max(1, round(value * factor))
                            for value in grid.step_yx
                        ),
                    ),
                    influence_radius_pixels=(
                        adaptive.influence_radius_pixels * factor
                    ),
                    transition_width_pixels=(
                        adaptive.transition_width_pixels * factor
                    ),
                ),
            ),
        )
        return tuple(configs)

    configuration.source_finder_configs = scaled
    continuum.source_finder_configs = scaled
    try:
        yield
    finally:
        configuration.source_finder_configs = installed
        continuum.source_finder_configs = installed


@contextmanager
def lifted_beam_limit(limit_pixels: float | None) -> Iterator[None]:
    """Replace the finder's beam limit while the context is open.

    ``find_sources`` refuses a restoring beam wider than the limit before it
    analyses anything. ``None`` leaves the installed limit alone.
    """
    installed = public_api._MAXIMUM_BEAM_FWHM_PIXELS
    if limit_pixels is not None:
        public_api._MAXIMUM_BEAM_FWHM_PIXELS = limit_pixels
    try:
        yield
    finally:
        public_api._MAXIMUM_BEAM_FWHM_PIXELS = installed


def _mesh_factor(run: Run) -> float:
    """Return the fine-mesh scale factor the run asks for."""
    if run.fine_mesh_reference_beam is None:
        return 1.0
    return max(1.0, run.beam_fwhm_pixels / run.fine_mesh_reference_beam)


def _write_image(dataset: DatasetRecord, path: Path) -> None:
    """Write the dataset's image as a four-axis single-precision FITS file."""
    image = generate_synthetic_image(dataset.recipe)
    data = np.asarray(image[np.newaxis, np.newaxis], dtype=np.float32)
    fits.PrimaryHDU(data=data, header=synthetic_fits_header(dataset)).writeto(
        path
    )


def _source_rows(
    dataset: DatasetRecord,
    catalogue_path: Path,
    rms_path: Path | None,
    beam_fwhm_degrees: float,
) -> tuple[list[dict[str, Any]], int, float | None]:
    """Match published sources to truth and read the RMS at each source."""
    truth = truth_catalogue(dataset)
    published = public_catalogue_sources(
        read_catalogue_fits_product(catalogue_path), level="sources"
    )
    report = compare_catalogues(
        truth,
        published,
        beam_fwhm_degrees=beam_fwhm_degrees,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
    )
    candidates = {source.identifier: source for source in published}
    matches = {match.reference_identifier: match for match in report.matches}
    rms = load_fits_plane(rms_path) if rms_path is not None else None
    rows: list[dict[str, Any]] = []
    for truth_source, injected in zip(
        truth, dataset.recipe.sources, strict=True
    ):
        match = matches.get(truth_source.identifier)
        row: dict[str, Any] = {
            "snr": injected.peak_flux_jy_per_beam / _NOISE_RMS,
            "matched": match is not None,
            "rms_ratio": (
                float(
                    rms[round(injected.y_pixel), round(injected.x_pixel)]
                    / _NOISE_RMS
                )
                if rms is not None
                else None
            ),
        }
        if match is not None:
            candidate = candidates[match.candidate_identifier]
            row |= {
                "offset_beams": match.separation_beam_fwhm,
                "flux_ratio": candidate.integrated_flux_jy
                / truth_source.integrated_flux_jy,
            }
        rows.append(row)
    median_rms_ratio = (
        float(np.nanmedian(rms) / _NOISE_RMS) if rms is not None else None
    )
    return rows, len(report.unmatched_candidate_identifiers), median_rms_ratio


def measure(run: Run, work_root: Path) -> dict[str, Any]:
    """Analyse one image under one configuration and return its record."""
    dataset = dataset_record(run)
    record: dict[str, Any] = {
        "key": run.key,
        "run": asdict(run),
        "mesh": run.mesh,
        "seed": run.seed,
        "recipe_sha256": dataset.recipe_sha256,
    }
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(dir=work_root) as directory:
        image_path = Path(directory) / "image.fits"
        _write_image(dataset, image_path)
        try:
            with (
                lifted_beam_limit(run.lifted_beam_limit_pixels),
                scaled_fine_mesh(_mesh_factor(run)),
            ):
                result = hebog.find_sources(
                    hebog.SourceFinderRequest(
                        image_path, Path(directory) / "products", "beam"
                    ),
                    hebog.SourceFinderConfig(5.0, 3.0, 7, profile=run.profile),
                    SerialExecutor(),
                )
        except Exception as error:  # recorded per run, never hidden
            return record | {
                "status": (
                    "refused"
                    if isinstance(error, hebog.SourceFinderError)
                    else "failure"
                ),
                "error": f"{type(error).__name__}: {error}",
            }
        rms_valid = result.rms.scientific_status == "valid"
        rows, unmatched, median_rms_ratio = _source_rows(
            dataset,
            result.catalogue_path,
            result.rms_path if rms_valid else None,
            run.beam_fwhm_pixels * _PIXEL_SCALE_DEGREES,
        )
    return record | {
        "status": "success",
        "elapsed_seconds": time.perf_counter() - started,
        "published_sources": result.source_count,
        "unmatched_published_sources": unmatched,
        "median_rms_ratio": median_rms_ratio,
        "sources": rows,
    }


def _completeness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarise recovery and matched measurements of one SNR stratum."""
    recovered = sum(bool(row["matched"]) for row in rows)
    interval = wilson_score_interval(recovered, len(rows))
    matched = [row for row in rows if row["matched"]]

    def median(name: str, population: Sequence[Mapping[str, Any]]) -> Any:
        values = [row[name] for row in population if row[name] is not None]
        return statistics.median(values) if values else None

    return {
        "sources": len(rows),
        "recovered": recovered,
        "completeness": recovered / len(rows) if rows else None,
        "wilson_95": (
            [interval.lower, interval.upper] if interval is not None else None
        ),
        "median_flux_ratio": median("flux_ratio", matched),
        "median_offset_beams": median("offset_beams", matched),
        "median_rms_ratio_at_source": median("rms_ratio", rows),
    }


def summarise(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Group run records into cells and summarise each cell.

    A cell is one mesh, profile, noise, image size and beam; within it,
    completeness is reported by SNR and for every SNR of at least 10.
    False detections are published sources that match no truth.
    """
    cells: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        cells.setdefault(record["key"].rsplit("/", 1)[0], []).append(record)
    summary: dict[str, Any] = {}
    for cell, members in sorted(cells.items()):
        analysed = [item for item in members if item["status"] == "success"]
        rows = [row for item in analysed for row in item["sources"]]
        run = members[0]["run"]
        beam_areas = (
            run["size"] ** 2
            / (_BEAM_AREA_PER_SQUARE_FWHM * run["beam_fwhm_pixels"] ** 2)
            * len(analysed)
        )
        false = sum(item["unmatched_published_sources"] for item in analysed)
        median_rms = [
            item["median_rms_ratio"]
            for item in analysed
            if item["median_rms_ratio"] is not None
        ]
        summary[cell] = {
            "images": len(members),
            "refused": len(members) - len(analysed),
            "by_snr": {
                f"{snr:g}": _completeness(
                    [row for row in rows if row["snr"] == snr]
                )
                for snr in _SNRS
            },
            "snr_at_least_10": _completeness(
                [row for row in rows if row["snr"] >= _BRIGHT_SNR]
            ),
            "false_detections": false,
            "false_per_image": false / len(analysed) if analysed else None,
            "false_per_thousand_beams": (
                1000.0 * false / beam_areas if analysed else None
            ),
            "median_map_rms_ratio": (
                statistics.median(median_rms) if median_rms else None
            ),
        }
    return summary


def _runs(arguments: argparse.Namespace) -> list[Run]:
    """Expand the requested grid, widest and largest images first."""
    runs = [
        Run(
            size=size,
            beam_fwhm_pixels=beam,
            noise=noise,
            realization=realization,
            profile=profile,
            fine_mesh_reference_beam=arguments.fine_mesh_reference_beam,
            lifted_beam_limit_pixels=arguments.lift_beam_limit_to,
        )
        for size in arguments.sizes
        for beam in arguments.beams
        for noise in arguments.noise
        for profile in arguments.profiles
        for realization in range(arguments.realizations)
    ]
    return sorted(
        runs,
        key=lambda run: (run.noise == "white", run.size, run.beam_fwhm_pixels),
        reverse=True,
    )


def _read_records(path: Path) -> list[dict[str, Any]]:
    """Read every run already recorded."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def main() -> None:
    """Run the requested grid in parallel processes and summarise it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000])
    parser.add_argument(
        "--beams",
        type=float,
        nargs="+",
        default=[2, 3, 4, 6, 8, 10],
        help="beam FWHM in pixels; above 10 needs --lift-beam-limit-to",
    )
    parser.add_argument(
        "--noise",
        nargs="+",
        choices=("white", "correlated"),
        default=["white", "correlated"],
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=("continuum", "compact"),
        default=["continuum", "compact"],
    )
    parser.add_argument("--realizations", type=int, default=4)
    parser.add_argument("--fine-mesh-reference-beam", type=float)
    parser.add_argument(
        "--lift-beam-limit-to",
        type=float,
        help="measure beams the finder refuses, up to this width in pixels",
    )
    parser.add_argument("--workers", type=int, default=3)
    arguments = parser.parse_args()
    for variable in _THREAD_VARIABLES:
        os.environ.setdefault(variable, "1")
    output: Path = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    results = output / "runs.jsonl"
    done = {record["key"] for record in _read_records(results)}
    pending = [run for run in _runs(arguments) if run.key not in done]
    work_root = output / "work"
    work_root.mkdir(exist_ok=True)
    print(f"{len(pending)} runs to do, {len(done)} recorded", flush=True)
    with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
        futures = [pool.submit(measure, run, work_root) for run in pending]
        for future in as_completed(futures):
            record = future.result()
            with results.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            print(record["key"], record["status"], flush=True)
    shutil.rmtree(work_root, ignore_errors=True)
    summary = {
        "hebog_version": hebog.__version__,
        "scientific_composition_sha256": (
            public_api._scientific_composition_sha256()
        ),
        "cells": summarise(_read_records(results)),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
