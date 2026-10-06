"""Compare Hebog and PyBDSF flux calibration on the M1 calibration population.

Reads one population's truth manifests and Hebog products from a
``measure_component_uncertainty_calibration.py`` run, and the PyBDSF
catalogues ``run_pybdsf_calibration.py`` produced from the same images in the
reference containers. Matching and the per-stratum statistics are the same as
in that script: nearest catalogue entry within one beam major FWHM;
excess = published / truth - 1.

The cases are the realizations the Hebog run holds, and each is paired with
a PyBDSF case only when PyBDSF processed the same image bytes; a missing or
different case stops the comparison. Truth, noise, beam and size classes are
read from each case's dataset record.

The paired bounds resample whole realizations, which is valid only if the
realizations are independent, so the comparison also reports how the same
grid source's flux excess correlates between realizations.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from astropy.stats import sigma_clipped_stats

from hebog.io import read_catalogue_fits_product
from hebog.validation.campaigns import phase_four_truth_source
from hebog.validation.component_calibration import (
    ComponentComparison,
    summarise_component_calibration,
)
from hebog.validation.datasets import load_dataset_manifest
from hebog.validation.products import (
    load_pybdsf_catalogue,
    load_pybdsf_gaussian_catalogue,
)

_DEFAULT_ROOT = Path("benchmark-results/uncertainty-calibration")
_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))
_NOISE_CLASSES = ("white", "correlated")


def _cases(hebog_run: Path) -> list[str]:
    """Return the run's realizations, white before correlated, by index."""

    def order(case: str) -> tuple[int, int]:
        _, noise, index = case.split("-")
        return _NOISE_CLASSES.index(noise), int(index)

    cases = sorted(
        (path.stem for path in hebog_run.glob("calibration-*.json")),
        key=order,
    )
    if not cases:
        raise SystemExit(f"{hebog_run} holds no calibration case")
    return cases


def _sha256(path: Path) -> str:
    """Return a file's SHA-256, refusing a missing file by name."""
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_reference(
    hebog_run: Path,
    reference: Path,
    image_sha256: dict[str, str],
) -> None:
    """Refuse a PyBDSF run that does not hold every case's same image.

    Case names repeat between populations, so a name alone would pair a
    run of other images with this truth. Every PyBDSF case keeps the copy
    of the image it processed, which is compared byte for byte.
    """
    for case in _cases(hebog_run):
        for name in ("source_catalog.fits", "gaussian_catalog.fits"):
            if not (reference / case / name).is_file():
                raise SystemExit(f"missing {reference / case / name}")
        if _sha256(reference / case / f"{case}.fits") != image_sha256[case]:
            raise SystemExit(
                f"{reference / case} processed a different image from "
                f"{hebog_run / case}.fits"
            )


@dataclass(frozen=True)
class Measured:
    """One catalogue entry in the units the truth is expressed in.

    Positions are RA/Dec in degrees, and ``e_ra`` is a great-circle one-sigma
    error, the convention the reported offsets and pulls use. Hebog and PyBDSF
    both publish it that way, so no loader converts.
    """

    ra: float
    dec: float
    peak: float
    integrated: float
    major: float | None
    minor: float | None
    e_ra: float | None
    e_dec: float | None
    e_peak: float | None
    e_integrated: float | None
    e_major: float | None
    e_minor: float | None
    constrained: bool


def _hebog(products: Path, level: str) -> list[Measured]:
    catalogue = read_catalogue_fits_product(products / "catalogue.fits")
    objects = (
        catalogue.gaussian_components
        if level == "components"
        else catalogue.sources
    )
    rows: list[Measured] = []
    for item in objects:
        shape = item.fitted_shape
        rows.append(
            Measured(
                ra=item.position.right_ascension_degrees,
                dec=item.position.declination_degrees,
                peak=item.flux.peak_flux_jy_per_beam,
                integrated=item.flux.integrated_flux_jy,
                major=shape.major_fwhm_degrees if shape else None,
                minor=shape.minor_fwhm_degrees if shape else None,
                e_ra=item.position.right_ascension_error_degrees,
                e_dec=item.position.declination_error_degrees,
                e_peak=item.flux.peak_flux_error_jy_per_beam,
                e_integrated=item.flux.integrated_flux_error_jy,
                e_major=shape.major_fwhm_error_degrees if shape else None,
                e_minor=shape.minor_fwhm_error_degrees if shape else None,
                constrained="beam-constrained-fit" in item.quality_flags,
            )
        )
    return rows


def _pybdsf(case_dir: Path, level: str) -> list[Measured]:
    if level == "components":
        entries = load_pybdsf_gaussian_catalogue(
            case_dir / "gaussian_catalog.fits"
        )
    else:
        entries = load_pybdsf_catalogue(case_dir / "source_catalog.fits")
    rows: list[Measured] = []
    for item in entries:
        shape = item.fitted_shape
        rows.append(
            Measured(
                ra=item.right_ascension_degrees,
                dec=item.declination_degrees,
                peak=item.peak_flux_jy_per_beam,
                integrated=item.integrated_flux_jy,
                major=shape.major_fwhm_degrees if shape else None,
                minor=shape.minor_fwhm_degrees if shape else None,
                e_ra=item.right_ascension_error_degrees,
                e_dec=item.declination_error_degrees,
                e_peak=item.peak_flux_error_jy_per_beam,
                e_integrated=item.integrated_flux_error_jy,
                e_major=shape.major_fwhm_error_degrees if shape else None,
                e_minor=shape.minor_fwhm_error_degrees if shape else None,
                constrained=item.deconvolution_status == "unresolved",
            )
        )
    return rows


def _excess(published: float | None, expected: float) -> float | None:
    if published is None or not expected:
        return None
    return published / expected - 1.0


def _pull(
    published: float | None, expected: float, error: float | None
) -> float | None:
    if published is None or not error:
        return None
    return (published - expected) / error


def _match(
    manifest_path: Path, measured: list[Measured]
) -> list[dict[str, Any]]:
    dataset = load_dataset_manifest(manifest_path).datasets[0]
    beam_degrees = dataset.beam.major_fwhm_pixels * abs(
        dataset.wcs.pixel_scale_degrees_xy[1]
    )
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(dataset.recipe.sources):
        truth = phase_four_truth_source(source, dataset, identifier=str(index))
        cos_dec = math.cos(math.radians(truth.declination_degrees))
        best: Measured | None = None
        best_separation = math.inf
        for item in measured:
            separation = math.hypot(
                (item.ra - truth.right_ascension_degrees) * cos_dec,
                item.dec - truth.declination_degrees,
            )
            if separation < best_separation:
                best, best_separation = item, separation
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
            truth_shape = truth.fitted_shape
            assert truth_shape is not None
            offsets = {
                "ra": (best.ra - truth.right_ascension_degrees) * cos_dec,
                "dec": best.dec - truth.declination_degrees,
            }
            record["beam_constrained"] = best.constrained
            record["excesses"] = {
                "ra": offsets["ra"] / beam_degrees,
                "dec": offsets["dec"] / beam_degrees,
                "peak": _excess(best.peak, truth.peak_flux_jy_per_beam),
                "integrated": _excess(
                    best.integrated, truth.integrated_flux_jy
                ),
                "major": _excess(best.major, truth_shape.major_fwhm_degrees),
                "minor": _excess(best.minor, truth_shape.minor_fwhm_degrees),
            }
            record["pulls"] = {
                # Offsets and every `e_ra` are great-circle, so scaling the
                # RA difference by cos(dec) keeps the pull dimensionless.
                "ra": _pull(
                    best.ra * cos_dec,
                    truth.right_ascension_degrees * cos_dec,
                    best.e_ra,
                ),
                "dec": _pull(best.dec, truth.declination_degrees, best.e_dec),
                "peak": _pull(
                    best.peak, truth.peak_flux_jy_per_beam, best.e_peak
                ),
                "integrated": _pull(
                    best.integrated,
                    truth.integrated_flux_jy,
                    best.e_integrated,
                ),
                "major": _pull(
                    best.major, truth_shape.major_fwhm_degrees, best.e_major
                ),
                "minor": _pull(
                    best.minor, truth_shape.minor_fwhm_degrees, best.e_minor
                ),
            }
        rows.append(record)
    return rows


def _strata(rows_by_case: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case, rows in rows_by_case.items():
        noise = case.split("-")[1]
        for row in rows:
            snr = int(row["snr"])
            keys = (
                f"{noise}/snr{snr}/x{row['size_factor']}",
                f"{noise}/snr{snr}",
                noise,
                f"all/snr{snr}",
                f"all/snr{snr}/x{row['size_factor']}",
                "all",
            )
            for key in keys:
                grouped.setdefault(key, []).append(row)
    return {
        key: summarise_component_calibration(
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
        for key, rows in sorted(grouped.items())
    }


def _collect(
    hebog_run: Path,
    loader: Callable[[str], list[Measured]],
) -> dict[str, Any]:
    """Match one finder's catalogues to truth over the whole population."""
    rows_by_case = {
        case: _match(hebog_run / f"{case}.json", loader(case))
        for case in _cases(hebog_run)
    }
    return _strata(rows_by_case)


def _matched_rows(
    hebog_run: Path,
    loader: Callable[[str], list[Measured]],
) -> dict[str, list[dict[str, Any]]]:
    """Return each case's matched rows, for resampling whole realizations."""
    return {
        case: _match(hebog_run / f"{case}.json", loader(case))
        for case in _cases(hebog_run)
    }


def _excesses(
    rows_by_case: dict[str, list[dict[str, Any]]],
    cases: Iterable[str],
    *,
    signal_to_noise: int,
    noise: str | None,
) -> npt.NDArray[np.float64]:
    """Return the integrated-flux excesses of one stratum."""
    values = [
        row["excesses"]["integrated"]
        for case in cases
        for row in rows_by_case[case]
        if int(row["snr"]) == signal_to_noise
        and row["matched"]
        and (noise is None or case.split("-")[1] == noise)
    ]
    return np.asarray(values, dtype=np.float64)


def _median_and_tail(
    values: npt.NDArray[np.float64],
) -> tuple[float, float]:
    """Return one stratum's median excess and absolute 95th percentile."""
    return float(np.median(values)), float(np.percentile(np.abs(values), 95))


def _paired_difference(  # noqa: PLR0913
    hebog_rows: dict[str, list[dict[str, Any]]],
    reference_rows: dict[str, list[dict[str, Any]]],
    *,
    signal_to_noise: int,
    noise: str | None,
    resamples: int,
    seed: int,
) -> dict[str, float]:
    """Bootstrap Hebog minus the reference over whole realizations.

    Realizations are the independent sampling unit the scientific gates
    require, so each resample draws whole cases within its noise class and
    both finders are evaluated on the same draw.
    """
    generator = np.random.default_rng(seed)
    cases = list(hebog_rows)
    white = [case for case in cases if "white" in case]
    correlated = [case for case in cases if "correlated" in case]
    observed = tuple(
        a - b
        for a, b in zip(
            _median_and_tail(
                _excesses(
                    hebog_rows,
                    cases,
                    signal_to_noise=signal_to_noise,
                    noise=noise,
                )
            ),
            _median_and_tail(
                _excesses(
                    reference_rows,
                    cases,
                    signal_to_noise=signal_to_noise,
                    noise=noise,
                )
            ),
            strict=True,
        )
    )
    differences = np.empty((resamples, 2), dtype=np.float64)
    for index in range(resamples):
        drawn = [
            *generator.choice(white, len(white)),
            *generator.choice(correlated, len(correlated)),
        ]
        subject = _median_and_tail(
            _excesses(
                hebog_rows,
                drawn,
                signal_to_noise=signal_to_noise,
                noise=noise,
            )
        )
        reference = _median_and_tail(
            _excesses(
                reference_rows,
                drawn,
                signal_to_noise=signal_to_noise,
                noise=noise,
            )
        )
        differences[index] = (
            subject[0] - reference[0],
            subject[1] - reference[1],
        )
    upper = np.percentile(differences, 95, axis=0)
    return {
        "median_difference": observed[0],
        "median_upper_95": float(upper[0]),
        "absolute_p95_difference": observed[1],
        "absolute_p95_upper_95": float(upper[1]),
    }


def _realization_correlations(
    rows_by_case: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Correlate each grid source's flux excess between realizations.

    Each signal-to-noise and size class is standardized over all of a noise
    class's realizations first, so shared truth cannot correlate. For
    independent realizations each pair's correlation is 0 with a standard
    error of about 1/sqrt(64) = 0.125; one noise field shared between
    realizations makes it positive.
    """
    correlations: dict[str, dict[str, Any]] = {}
    for noise in ("white", "correlated"):
        cases = [case for case in rows_by_case if case.split("-")[1] == noise]
        table = np.asarray(
            [
                [
                    row["excesses"]["integrated"]
                    if row["matched"]
                    and row["excesses"]["integrated"] is not None
                    else np.nan
                    for row in rows_by_case[case]
                ]
                for case in cases
            ],
            dtype=np.float64,
        )
        classes = [
            (int(row["snr"]), row["size_factor"])
            for row in rows_by_case[cases[0]]
        ]
        for key in set(classes):
            members = np.asarray([item == key for item in classes])
            block = table[:, members]
            table[:, members] = (block - np.nanmean(block)) / np.nanstd(block)
        pairs: dict[str, float] = {}
        for first, second in itertools.combinations(range(len(cases)), 2):
            finite = np.isfinite(table[first]) & np.isfinite(table[second])
            pairs[f"{cases[first]} / {cases[second]}"] = float(
                np.corrcoef(table[first, finite], table[second, finite])[0, 1]
            )
        correlations[noise] = {
            "pairs": pairs,
            "mean": float(np.mean(list(pairs.values()))),
            "maximum": max(pairs.values()),
        }
    return correlations


def _print_realization_correlations(
    correlations: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """Print the mean and largest correlation between realizations."""
    print("\n=== flux excess correlation between realizations ===")
    print(f"{'finder / noise':44s}{'mean':>12s}{'maximum':>12s}")
    for finder, by_noise in correlations.items():
        for noise, stats in by_noise.items():
            print(
                f"{finder + ' / ' + noise:44s}"
                + f"{stats['mean']:+12.2f}"
                + f"{stats['maximum']:+12.2f}"
            )


def _clipped_ratio(
    rows_by_case: dict[str, list[dict[str, Any]]],
    *,
    minimum_signal_to_noise: int,
    noise: str | None,
) -> dict[str, float]:
    """Return the 3-sigma-clipped mean flux ratio and its scatter.

    Rapthor's photometry check takes a sigma-clipped mean of the ratio
    between catalogue and reference flux, so the limit is asserted on the
    same statistic rather than on the raw mean.
    """
    ratios = np.asarray(
        [
            1.0 + row["excesses"]["integrated"]
            for case, rows in rows_by_case.items()
            for row in rows
            if row["matched"]
            and int(row["snr"]) >= minimum_signal_to_noise
            and (noise is None or case.split("-")[1] == noise)
        ],
        dtype=np.float64,
    )
    mean, _, deviation = sigma_clipped_stats(ratios, sigma=3.0, maxiters=None)
    return {
        "clipped_mean_ratio": float(mean),
        "clipped_standard_deviation": float(deviation),
        "count": int(ratios.size),
    }


def _clipped_ratios(
    hebog_run: Path,
    reference: Path,
) -> dict[str, dict[str, float]]:
    """Return the clipped ratio for Hebog and the reference, by noise class."""
    loaders: list[tuple[str, Callable[[str], list[Measured]]]] = [
        (
            "hebog-sources",
            lambda case: _hebog(hebog_run / f"{case}-products", "sources"),
        ),
        (
            "pybdsf-master-sources",
            lambda case: _pybdsf(reference / case, "sources"),
        ),
    ]
    clipped: dict[str, dict[str, float]] = {}
    for label, loader in loaders:
        rows = _matched_rows(hebog_run, loader)
        for noise in (None, "white", "correlated"):
            clipped[f"{label} / {noise or 'all'}"] = _clipped_ratio(
                rows, minimum_signal_to_noise=20, noise=noise
            )
    return clipped


def _print_clipped_ratios(clipped: dict[str, dict[str, float]]) -> None:
    """Print the clipped mean ratio to truth for every finder and class."""
    print("\n=== 3-sigma-clipped mean ratio to truth, SNR >= 20 ===")
    print(f"{'finder / noise':44s}{'ratio':>12s}{'scatter':>12s}")
    for key, stats in clipped.items():
        print(
            f"{key:44s}"
            + f"{stats['clipped_mean_ratio']:12.3f}"
            + f"{stats['clipped_standard_deviation']:12.3f}"
        )


def _print_excess_tables(finders: dict[str, dict[str, Any]]) -> None:
    """Print median excess and tail per stratum for every finder."""
    names = list(finders)
    for field in ("integrated", "peak"):
        print(f"\n=== {field} flux: median excess / abs p95 / matched ===")
        print(f"{'stratum':26s}" + "".join(f"{n:>34s}" for n in names))
        for key in finders[names[0]]:
            line = f"{key:26s}"
            for name in names:
                stratum = finders[name][key]
                stats = stratum["excess"].get(field)
                if stats is None:
                    line += f"{'-':>34s}"
                    continue
                line += (
                    f"{stats['median']:+.3f} / {stats['absolute_p95']:.3f}"
                    f" / {stratum['matched']:3d}/{stratum['sources']:3d}"
                ).rjust(34)
            print(line)


def _print_pull_table(finders: dict[str, dict[str, Any]]) -> None:
    """Print the integrated-flux pull summary for every finder."""
    names = list(finders)
    print("\n=== integrated pull: median / std / coverage / reported ===")
    for key in ("all/snr10", "all/snr20", "all/snr50", "white", "correlated"):
        line = f"{key:26s}"
        for name in names:
            stats = finders[name][key]["pull"].get("integrated")
            if stats is None:
                line += f"{'-':>34s}"
                continue
            line += (
                f"{stats['median']:+.2f} / {stats['standard_deviation']:.2f}"
                f" / {stats['coverage']:.2f}"
                f" / {stats['reported_fraction']:.2f}"
            ).rjust(34)
        print(line)


def _print_paired_bounds(paired: dict[str, dict[str, float]]) -> None:
    """Print the paired Hebog-minus-reference bootstrap bounds."""
    print("\n=== Hebog minus pinned PyBDSF master, upper one-sided 95% ===")
    print(f"{'stratum':26s}{'d(median)':>22s}{'d(abs p95)':>22s}")
    for key, bounds in paired.items():
        print(
            f"{key:26s}"
            + (
                f"{bounds['median_difference']:+.3f} "
                f"up {bounds['median_upper_95']:+.3f}"
            ).rjust(22)
            + (
                f"{bounds['absolute_p95_difference']:+.3f} "
                f"up {bounds['absolute_p95_upper_95']:+.3f}"
            ).rjust(22)
        )


def _parse_args() -> argparse.Namespace:
    """Parse the comparison's population root and bootstrap settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    # No defaults: a Hebog run compared with catalogues of another
    # population would match them against the wrong truth.
    parser.add_argument(
        "--hebog-run",
        required=True,
        help="Hebog population directory under --root",
    )
    parser.add_argument(
        "--pybdsf-master-run",
        required=True,
        help="pinned PyBDSF master catalogues under --root, same population",
    )
    parser.add_argument(
        "--pybdsf-release-run",
        help="released PyBDSF catalogues under --root, same population",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="comparison JSON to write (default: named for the Hebog run)",
    )
    parser.add_argument("--resamples", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="omit the paired Hebog-minus-reference bounds",
    )
    return parser.parse_args()


def main() -> None:
    """Compare every finder against truth on the M1 population."""
    args = _parse_args()
    root = Path(args.root)
    hebog_run = root / str(args.hebog_run)
    pybdsf_runs = {"pybdsf-master": root / str(args.pybdsf_master_run)}
    if args.pybdsf_release_run:
        pybdsf_runs["pybdsf-release"] = root / str(args.pybdsf_release_run)
    image_sha256 = {
        case: _sha256(hebog_run / f"{case}.fits") for case in _cases(hebog_run)
    }
    for run in pybdsf_runs.values():
        _require_reference(hebog_run, run, image_sha256)
    finders: dict[str, dict[str, Any]] = {}
    for level in ("components", "sources"):
        finders[f"hebog-{level}"] = _collect(
            hebog_run,
            lambda case, level=level: _hebog(
                hebog_run / f"{case}-products", level
            ),
        )
        for name, run in pybdsf_runs.items():
            finders[f"{name}-{level}"] = _collect(
                hebog_run,
                lambda case, run=run, level=level: _pybdsf(run / case, level),
            )
    document: dict[str, Any] = {
        "runs": {
            "root": str(root),
            "hebog": str(args.hebog_run),
            "pybdsf_master": str(args.pybdsf_master_run),
            "pybdsf_release": args.pybdsf_release_run,
        },
        "image_sha256": image_sha256,
        "finders": finders,
    }
    reference = pybdsf_runs["pybdsf-master"]
    clipped = _clipped_ratios(hebog_run, reference)
    document["clipped_ratio_snr20"] = clipped
    hebog_rows = _matched_rows(
        hebog_run,
        lambda case: _hebog(hebog_run / f"{case}-products", "sources"),
    )
    reference_rows = _matched_rows(
        hebog_run,
        lambda case: _pybdsf(reference / case, "sources"),
    )
    correlations = {
        "hebog-sources": _realization_correlations(hebog_rows),
        "pybdsf-master-sources": _realization_correlations(reference_rows),
    }
    document["realization_correlation"] = correlations
    if not args.skip_bootstrap:
        paired: dict[str, dict[str, float]] = {}
        for noise in (None, "white", "correlated"):
            for signal_to_noise in (10, 20, 50):
                key = f"{noise or 'all'}/snr{signal_to_noise}"
                paired[key] = _paired_difference(
                    hebog_rows,
                    reference_rows,
                    signal_to_noise=signal_to_noise,
                    noise=noise,
                    resamples=args.resamples,
                    seed=args.seed,
                )
        document["paired_sources_minus_pybdsf_master"] = paired
    out = (
        Path(args.output)
        if args.output
        else root / f"{args.hebog_run}-pybdsf-comparison.json"
    )
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    _print_excess_tables(finders)
    _print_pull_table(finders)
    _print_clipped_ratios(clipped)
    _print_realization_correlations(correlations)
    if "paired_sources_minus_pybdsf_master" in document:
        _print_paired_bounds(document["paired_sources_minus_pybdsf_master"])
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
