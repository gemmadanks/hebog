# pyright: reportPrivateUsage=false
"""Measure Gaussian-component uncertainty calibration against injected truth.

Materializes the population in ``config/datasets/m1-flux-calibration.json``
(``build_flux_calibration_datasets.py``): 1,024-pixel images of isolated
sources on a grid, with pixel-independent and beam-correlated noise. Runs the
public finder with the requested point estimator and reports pulls against
truth::

    excess = published / truth - 1        (positions: offset in beams)
    pull  = (published - truth) / published one-sigma error

for position, peak flux, integrated flux and fitted axes. The excess covers
every matched component; the pull covers only those publishing an
uncertainty, and is reported with the share of the population that is.
Calibrated errors give a pull standard deviation near one and 68.3% of
pulls within one, read against that share.

Outputs go under ``benchmark-results/uncertainty-calibration/<label>``, with
each realization's record as a one-dataset manifest beside its image for
``compare_flux_calibration.py``. This is development evidence for choosing
uncertainty calibration, not qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

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
    DatasetRecord,
    load_dataset_manifest,
)
from hebog.validation.materialization import materialize_dataset

_ROOT = Path(__file__).resolve().parents[2]
_POPULATION = _ROOT / "config/datasets/m1-flux-calibration.json"
_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))


def _manifest(path: Path, dataset: DatasetRecord) -> Path:
    """Write one realization as a one-dataset manifest."""
    document = {
        "schema_version": 1,
        "manifest_id": "uncertainty-calibration",
        "datasets": [dataset.model_dump(mode="json")],
    }
    DatasetManifest.model_validate(document)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _repository_path(path: Path) -> str:
    """Return a path relative to the repository when it lies inside it."""
    resolved = path.resolve()
    if resolved.is_relative_to(_ROOT):
        return resolved.relative_to(_ROOT).as_posix()
    return resolved.as_posix()


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


def _pulls(manifest: Path, catalogue_path: Path) -> list[dict[str, Any]]:
    """Match each injected source and record its excess and pulls.

    Signal-to-noise, size class and beam come from the dataset record.
    """
    dataset = load_dataset_manifest(manifest).datasets[0]
    catalogue = read_catalogue_fits_product(catalogue_path)
    beam_degrees = dataset.beam.major_fwhm_pixels * abs(
        dataset.wcs.pixel_scale_degrees_xy[1]
    )
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
            "snr": source.peak_flux_jy_per_beam / dataset.recipe.noise_rms,
            "size_factor": round(
                source.major_sigma_pixels
                * _FWHM_PER_SIGMA
                / dataset.beam.major_fwhm_pixels,
                2,
            ),
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
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_POPULATION,
        help="population manifest (default: the M1 calibration population)",
    )
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
        "population": {
            "manifest": _repository_path(args.manifest),
            "sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        },
        "point_estimator": args.point_estimator,
        "scientific_composition_sha256": (
            public_api._scientific_composition_sha256()
        ),
        "strata": {},
    }
    all_rows: dict[str, list[dict[str, Any]]] = {}
    for dataset in load_dataset_manifest(args.manifest).datasets:
        identifier = dataset.identifier
        correlated = dataset.recipe.noise_correlation is not None
        noise = "correlated" if correlated else "white"
        manifest = _manifest(root / f"{identifier}.json", dataset)
        image = root / f"{identifier}.fits"
        materialize_dataset(manifest, identifier, image)
        products = root / f"{identifier}-products"
        shutil.rmtree(products, ignore_errors=True)
        result = hebog.find_sources(
            hebog.SourceFinderRequest(image, products, identifier),
            hebog.SourceFinderConfig(5.0, 3.0, 7),
            SerialExecutor(),
        )
        rows = _pulls(manifest, result.catalogue_path)
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
