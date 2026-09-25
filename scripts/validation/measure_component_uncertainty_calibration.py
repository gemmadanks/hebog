# pyright: reportPrivateUsage=false
"""Measure Gaussian-component uncertainty calibration against injected truth.

Generates seed-disjoint 1,024-pixel images of isolated sources on a grid,
with pixel-independent and beam-correlated noise, runs the public finder with
each requested point estimator, and reports pulls against truth::

    excess = published / truth - 1        (positions: offset in beams)
    pull  = (published - truth) / published one-sigma error

for position, peak flux, integrated flux and fitted axes. The excess covers
every matched component; the pull covers only those publishing an
uncertainty, and is reported with the share of the population that is.
Calibrated errors give a pull standard deviation near one and 68.3% of
pulls within one, read against that share.

Outputs go under ``benchmark-results/uncertainty-calibration/<label>``.
This is development evidence for choosing uncertainty calibration, not
qualification.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

import hebog
from hebog import public_api
from hebog.executors import SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.validation.campaigns import phase_four_truth_source
from hebog.validation.component_calibration import (
    ComponentComparison,
    summarise_component_calibration,
)
from hebog.validation.datasets import (
    DatasetManifest,
    SyntheticRecipe,
    load_dataset_manifest,
    recipe_sha256,
)
from hebog.validation.materialization import materialize_dataset

_ROOT = Path(__file__).resolve().parents[2]
_SEED_BASE = 2026091700
_NOISE_RMS = 1e-4
_BEAM_MAJOR_FWHM_PIXELS = 5.0
_BEAM_MINOR_FWHM_PIXELS = 4.0
_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
_PIXEL_SCALE_DEGREES = 1.5 / 3600.0
_GRID = 8
_SIZE = 1024
_SNRS = (10.0, 20.0, 50.0)
# Beam-sized sources cannot distinguish a correct shape from one always
# constrained to the beam, because their truth is the beam. The two factors
# between them are the ones where publishing the beam would bias sizes and
# fluxes low, and a free fit would bias them high.
_SIZE_FACTORS = (1.0, 1.15, 1.3, 1.5)
_ONE_SIGMA = 0.6827


def _recipe(seed: int, *, correlated: bool) -> dict[str, Any]:
    """Isolated sources cycling through SNR and size, with sub-pixel jitter."""
    generator = np.random.default_rng(seed)
    spacing = _SIZE / _GRID
    sources: list[dict[str, float]] = []
    for index in range(_GRID * _GRID):
        row, column = divmod(index, _GRID)
        factor = _SIZE_FACTORS[index % len(_SIZE_FACTORS)]
        snr = _SNRS[(index // len(_SIZE_FACTORS)) % len(_SNRS)]
        sources.append(
            {
                "x_pixel": round(
                    spacing * (column + 0.5) + generator.uniform(-0.5, 0.5), 4
                ),
                "y_pixel": round(
                    spacing * (row + 0.5) + generator.uniform(-0.5, 0.5), 4
                ),
                "peak_flux_jy_per_beam": snr * _NOISE_RMS,
                "major_sigma_pixels": factor
                * _BEAM_MAJOR_FWHM_PIXELS
                / _FWHM_PER_SIGMA,
                "minor_sigma_pixels": factor
                * _BEAM_MINOR_FWHM_PIXELS
                / _FWHM_PER_SIGMA,
                "rotation_degrees_counterclockwise_from_x": 0.0,
            }
        )
    document: dict[str, Any] = {
        "generator": "hebog.synthetic.gaussian-noise",
        "generator_version": 3 if correlated else 2,
        "seed": seed,
        "shape_yx": [_SIZE, _SIZE],
        "background": 0.0,
        "noise_rms": _NOISE_RMS,
        "sources": sources,
        "noise_rms_fractional_gradient_xy": [0.0, 0.0],
        "invalid_rectangles": [],
    }
    if correlated:
        document["noise_correlation"] = {
            "major_fwhm_pixels": _BEAM_MAJOR_FWHM_PIXELS,
            "minor_fwhm_pixels": _BEAM_MINOR_FWHM_PIXELS,
            "position_angle_degrees": 0.0,
            "truncation_sigma": 4.0,
        }
    return document


def _manifest(path: Path, identifier: str, recipe: dict[str, Any]) -> Path:
    model = SyntheticRecipe.model_validate(recipe)
    document = {
        "schema_version": 1,
        "manifest_id": "uncertainty-calibration",
        "datasets": [
            {
                "identifier": identifier,
                "role": "development",
                "purpose": "Component uncertainty calibration.",
                "provenance": (
                    "scripts/validation/"
                    "measure_component_uncertainty_calibration.py"
                ),
                "redistribution": "generated-locally",
                "beam": {
                    "major_fwhm_pixels": _BEAM_MAJOR_FWHM_PIXELS,
                    "minor_fwhm_pixels": _BEAM_MINOR_FWHM_PIXELS,
                    "position_angle_degrees": 0.0,
                },
                "wcs": {
                    "frame": "icrs",
                    "reference_pixel_xy": [
                        (_SIZE - 1) / 2.0,
                        (_SIZE - 1) / 2.0,
                    ],
                    "reference_sky_degrees": [180.0, 45.0],
                    "pixel_scale_degrees_xy": [
                        -_PIXEL_SCALE_DEGREES,
                        _PIXEL_SCALE_DEGREES,
                    ],
                    "rotation_degrees_counterclockwise": 0.0,
                },
                "expected_statistics": {
                    "background_jy_per_beam": 0.0,
                    "noise_rms_jy_per_beam": _NOISE_RMS,
                    "finite_fraction": 1.0,
                },
                "recipe": model.model_dump(mode="json"),
                "recipe_sha256": recipe_sha256(model),
            }
        ],
    }
    DatasetManifest.model_validate(document)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _use_point_estimator(estimator: str) -> None:
    """Override the installed fit config's point estimator everywhere.

    `source_finder_configs` lives in `hebog.science.configuration`, and
    `hebog.science.continuum` binds the name at import time, so patching one
    module alone leaves the other calling the installed policy.
    """
    from hebog.science import configuration, continuum  # noqa: PLC0415

    original = configuration.source_finder_configs

    def configured() -> Any:
        configs = list(original())
        configs[3] = replace(configs[3], point_estimator=estimator)
        return tuple(configs)

    configuration.source_finder_configs = configured
    continuum.source_finder_configs = configured


def _pulls(
    manifest: Path,
    catalogue_path: Path,
    snr_by_index: list[float],
) -> list[dict[str, Any]]:
    dataset = load_dataset_manifest(manifest).datasets[0]
    catalogue = read_catalogue_fits_product(catalogue_path)
    beam_degrees = _BEAM_MAJOR_FWHM_PIXELS * _PIXEL_SCALE_DEGREES
    components = catalogue.gaussian_components
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(dataset.recipe.sources):
        truth = phase_four_truth_source(source, dataset, identifier=str(index))
        cos_dec = math.cos(math.radians(truth.declination_degrees))
        best = None
        best_separation = math.inf
        for component in components:
            d_ra = (
                component.position.right_ascension_degrees
                - truth.right_ascension_degrees
            ) * cos_dec
            d_dec = (
                component.position.declination_degrees
                - truth.declination_degrees
            )
            separation = math.hypot(d_ra, d_dec)
            if separation < best_separation:
                best, best_separation = component, separation
        record: dict[str, Any] = {
            "snr": snr_by_index[index],
            "size_factor": _SIZE_FACTORS[index % len(_SIZE_FACTORS)],
            "matched": best is not None and best_separation < beam_degrees,
        }
        if record["matched"]:
            assert best is not None
            position = best.position
            flux = best.flux
            shape = best.fitted_shape
            truth_shape = truth.fitted_shape
            assert truth_shape is not None

            def difference(published: float, expected: float) -> float:
                return published - expected

            def excess(published: float, expected: float) -> float | None:
                """Return the fractional distance from truth."""
                return published / expected - 1.0 if expected else None

            def pull(delta: float, error: float | None) -> float | None:
                """Return the distance from truth in published errors."""
                return delta / error if error else None

            offsets = {
                "ra": difference(
                    position.right_ascension_degrees,
                    truth.right_ascension_degrees,
                )
                * cos_dec,
                "dec": difference(
                    position.declination_degrees, truth.declination_degrees
                ),
            }
            record |= {
                "beam_constrained": (
                    "beam-constrained-fit" in best.quality_flags
                ),
                # Positions are reported in beams, the unit a position error
                # is judged in; the rest are fractions of truth.
                "excesses": {
                    "ra": offsets["ra"] / beam_degrees,
                    "dec": offsets["dec"] / beam_degrees,
                    "peak": excess(
                        flux.peak_flux_jy_per_beam,
                        truth.peak_flux_jy_per_beam,
                    ),
                    "integrated": excess(
                        flux.integrated_flux_jy, truth.integrated_flux_jy
                    ),
                    "major": excess(
                        shape.major_fwhm_degrees,
                        truth_shape.major_fwhm_degrees,
                    ),
                    "minor": excess(
                        shape.minor_fwhm_degrees,
                        truth_shape.minor_fwhm_degrees,
                    ),
                },
                "pulls": {
                    # Offset and error are both great-circle angles.
                    "ra": pull(
                        offsets["ra"],
                        position.right_ascension_error_degrees,
                    ),
                    "dec": pull(
                        offsets["dec"],
                        position.declination_error_degrees,
                    ),
                    "peak": pull(
                        difference(
                            flux.peak_flux_jy_per_beam,
                            truth.peak_flux_jy_per_beam,
                        ),
                        flux.peak_flux_error_jy_per_beam,
                    ),
                    "integrated": pull(
                        difference(
                            flux.integrated_flux_jy,
                            truth.integrated_flux_jy,
                        ),
                        flux.integrated_flux_error_jy,
                    ),
                    "major": pull(
                        difference(
                            shape.major_fwhm_degrees,
                            truth_shape.major_fwhm_degrees,
                        ),
                        shape.major_fwhm_error_degrees,
                    ),
                    "minor": pull(
                        difference(
                            shape.minor_fwhm_degrees,
                            truth_shape.minor_fwhm_degrees,
                        ),
                        shape.minor_fwhm_error_degrees,
                    ),
                },
            }
        rows.append(record)
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise one stratum over every matched component."""
    return summarise_component_calibration(
        [
            ComponentComparison(
                matched=bool(row["matched"]),
                beam_constrained=bool(row.get("beam_constrained", False)),
                excesses=row.get("excesses", {}),
                pulls=row.get("pulls", {}),
            )
            for row in rows
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--realizations", type=int, default=5)
    parser.add_argument(
        "--point-estimator",
        choices=("diagonal-weighted", "correlated-gls"),
        required=True,
    )
    args = parser.parse_args()
    _use_point_estimator(args.point_estimator)
    root = _ROOT / "benchmark-results/uncertainty-calibration" / args.label
    root.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {
        "point_estimator": args.point_estimator,
        "scientific_composition_sha256": (
            public_api._scientific_composition_sha256()
        ),
        "strata": {},
    }
    all_rows: dict[str, list[dict[str, Any]]] = {}
    for correlated in (False, True):
        noise = "correlated" if correlated else "white"
        for realization in range(args.realizations):
            seed = _SEED_BASE + 2 * realization + int(correlated)
            identifier = f"calibration-{noise}-{realization}"
            recipe = _recipe(seed, correlated=correlated)
            manifest = _manifest(
                root / f"{identifier}.json", identifier, recipe
            )
            image = root / f"{identifier}.fits"
            materialize_dataset(manifest, identifier, image)
            products = root / f"{identifier}-products"
            shutil.rmtree(products, ignore_errors=True)
            result = hebog.find_sources(
                hebog.SourceFinderRequest(image, products, identifier),
                hebog.SourceFinderConfig(5.0, 3.0, 7),
                SerialExecutor(),
            )
            snrs = [
                source["peak_flux_jy_per_beam"] / _NOISE_RMS
                for source in recipe["sources"]
            ]
            rows = _pulls(manifest, result.catalogue_path, snrs)
            for row in rows:
                key = f"{noise}/snr{int(row['snr'])}/x{row['size_factor']}"
                all_rows.setdefault(key, []).append(row)
                all_rows.setdefault(noise, []).append(row)
            print(f"{identifier}: {len(rows)} sources", flush=True)
    for key, rows in sorted(all_rows.items()):
        results["strata"][key] = _summary(rows)
    (root / "summary.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(results["strata"], indent=1))


if __name__ == "__main__":
    main()
