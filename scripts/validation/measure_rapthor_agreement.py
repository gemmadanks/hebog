#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Measure Rapthor's retained/rejected agreement under each Hebog lane.

Plan task 21 asks which Hebog profile and background Rapthor should run:
``compact`` only if its mask makes Rapthor keep the same sky-model
components as pinned PyBDSF ``master``'s does, on at least the configured
share overall and in every safety stratum, otherwise ``continuum``.

Cases, lanes, strata and the gate come from
``config/checks/rapthor-agreement.json``, which adds real LOFAR images to
the quick science check's cases and reuses its pinned-``master`` reference.
Reference outputs, and those of released PyBDSF, which runs as a control,
are computed once per input in their Podman images and cached under
``benchmark-results/quick-check/references``. Hebog runs every lane through
the public API with the configuration the Rapthor adapter builds, Rapthor's
thresholds and PyBDSF's minimum island rule, and the Rapthor catalogue
view is written beside each run's products.

The report, ``report.json`` in the run directory, holds every case's and
the pooled counts for each lane and stratum, each lane's gate outcome, the
profile the rule chooses for each background, and Rapthor's catalogue-cut
counts. The exit status is 1 when a lane's run failed, which leaves its
case unmeasured, and 0 otherwise, whatever the gate decides::

    uv run python scripts/validation/measure_rapthor_agreement.py --jobs 4
"""

from __future__ import annotations

import argparse
import runpy
import subprocess
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from astropy.wcs.utils import proj_plane_pixel_scales

import hebog
from hebog import public_api
from hebog.adapters import RapthorCompatibilityConfig
from hebog.adapters.rapthor import pybdsf_minimum_island_pixels
from hebog.adapters.rapthor_catalogue import write_rapthor_catalogue_fits
from hebog.algorithms.astrometry import celestial_wcs_from_metadata
from hebog.data_models import ImageMetadata, SourceCatalogue
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource, read_catalogue_fits_product
from hebog.validation.products import (
    load_fits_plane,
    load_mask_plane,
    load_pybdsf_gaussian_catalogue,
)
from hebog.validation.quick_check import (
    ContainerReference,
    GeneratedCase,
    ImageCase,
    PreparedCase,
    file_sha256,
    load_quick_check_configuration,
    prepare_case,
    reference_identity,
    write_report,
)
from hebog.validation.rapthor_agreement import (
    ALL_COMPONENTS,
    CatalogueCutCounts,
    ComponentPixels,
    DecisionCounts,
    GateOutcome,
    Lane,
    RapthorAgreementConfiguration,
    WeightedAgreement,
    compare_catalogue_cuts,
    compare_decisions,
    component_strata,
    emission_pixels,
    gate_outcome,
    hebog_cut_catalogue,
    load_agreement_configuration,
    pybdsf_cut_catalogue,
    rapthor_profile,
    weighted_agreement,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIGURATION = _ROOT / "config/checks/rapthor-agreement.json"
_DEFAULT_OUTPUT = _ROOT / "benchmark-results/rapthor-agreement"
# The quick check's cache: its inputs and reference outputs are shared.
_QUICK_CHECK_ROOT = _ROOT / "benchmark-results/quick-check"
_QUICK_CHECK_SCRIPT = _ROOT / "scripts/validation/quick_science_check.py"
_MASTER = "pinned-pybdsf-master"
_CONTROL = "released-pybdsf"
# PyBDSF's beam area: 2 pi / (8 ln 2) times the product of the FWHMs.
_BEAM_AREA_FACTOR = 1.1331

ImageKind = Literal["true-sky", "apparent"] | None


@dataclass(frozen=True, slots=True)
class LaneRun:
    """Where one lane's run of one case left its products."""

    status: Literal["success", "failure"]
    seconds: float
    error: str | None = None
    mask_path: Path | None = None
    catalogue_path: Path | None = None
    view_path: Path | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n")[0]
    )
    parser.add_argument(
        "--configuration", type=Path, default=_DEFAULT_CONFIGURATION
    )
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--label", help="run directory name")
    parser.add_argument("--cases", nargs="+", help="run only these case IDs")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Hebog runs at once, each serial (default 1)",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="fetch missing configured cut-outs",
    )
    parser.add_argument(
        "--skip-references",
        action="store_true",
        help="use cached reference results only",
    )
    parser.add_argument("--engine", default="podman")
    return parser.parse_args()


def _default_label() -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return f"{commit}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"


def _run_lane(
    prepared: PreparedCase,
    lane: Lane,
    threshpix: float,
    threshisl: float,
    output: Path,
) -> LaneRun:
    """Run one lane on one case, as Rapthor's adapter configures the finder.

    The adapter itself takes no supplied metadata, which the SDC1 cut-outs
    need for their beam angle, so the public API runs with the adapter's
    configuration instead.
    """
    started = time.perf_counter()
    rapthor = RapthorCompatibilityConfig(
        threshpix=threshpix,
        threshisl=threshisl,
        profile=lane.profile,
        background=lane.background,
    )
    try:
        metadata = FitsImageSource(
            prepared.input_path, prepared.supplied_metadata
        ).metadata()
        result = hebog.find_sources(
            hebog.SourceFinderRequest(
                image_path=prepared.input_path,
                output_directory=output / "products",
                run_id=f"{prepared.case_id}-{lane.name}",
                supplied_metadata=prepared.supplied_metadata,
            ),
            rapthor.source_finder_config(
                pybdsf_minimum_island_pixels(metadata)
            ),
            SerialExecutor(),
        )
        view = output / "source_catalog.fits"
        write_rapthor_catalogue_fits(
            view, read_catalogue_fits_product(result.catalogue)
        )
    except Exception as error:  # reported per run, never hidden
        return LaneRun(
            status="failure",
            seconds=time.perf_counter() - started,
            error=f"{type(error).__name__}: {error}",
        )
    return LaneRun(
        status="success",
        seconds=time.perf_counter() - started,
        mask_path=result.mask.path,
        catalogue_path=result.catalogue.path,
        view_path=view,
    )


def _run_lanes(
    prepared: Mapping[str, PreparedCase],
    configuration: RapthorAgreementConfiguration,
    run_root: Path,
    jobs: int,
) -> dict[tuple[str, str], LaneRun]:
    """Run every lane on every case, ``jobs`` processes at a time."""
    work = [
        (case_id, lane) for case_id in prepared for lane in configuration.lanes
    ]
    arguments = [
        (
            prepared[case_id],
            lane,
            configuration.threshpix,
            configuration.threshisl,
            run_root / lane.name / case_id,
        )
        for case_id, lane in work
    ]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            runs = list(pool.map(_run_lane, *zip(*arguments, strict=True)))
    else:
        runs = [_run_lane(*item) for item in arguments]
    for (case_id, lane), run in zip(work, runs, strict=True):
        print(
            f"{case_id} {lane.name}: {run.status} in {run.seconds:.1f} s",
            flush=True,
        )
    return {
        (case_id, lane.name): run
        for (case_id, lane), run in zip(work, runs, strict=True)
    }


def _beam_pixels(metadata: ImageMetadata) -> tuple[float, float]:
    """Return the beam's geometric-mean FWHM and its area, in pixels."""
    scale_x, scale_y = (
        float(scale)
        for scale in proj_plane_pixel_scales(
            celestial_wcs_from_metadata(metadata)
        )
    )
    major = metadata.beam.major_fwhm_degrees / scale_x
    minor = metadata.beam.minor_fwhm_degrees / scale_y
    return float(np.sqrt(major * minor)), _BEAM_AREA_FACTOR * major * minor


def _counts_record(counts: Mapping[str, DecisionCounts]) -> dict[str, Any]:
    return {
        name: asdict(value)
        | {
            "agreement": value.agreement,
            "grouping_agreement": value.grouping_agreement,
        }
        for name, value in counts.items()
    }


def _decision_counts(record: Mapping[str, Any]) -> DecisionCounts:
    """Read counts back from a report record, without its derived ratios."""
    return DecisionCounts(
        **{
            key: value
            for key, value in record.items()
            if key not in {"agreement", "grouping_agreement"}
        }
    )


def _artifact(root: Path, result: Mapping[str, Any], role: str) -> Path:
    return root / result["artifacts"][role]["path"]


def _component_positions(
    reference: tuple[Path, dict[str, Any]],
    catalogues: Mapping[str, SourceCatalogue],
) -> tuple[list[float], list[float]]:
    """Return every reference and lane Gaussian centre, in degrees."""
    root, result = reference
    gaussians = load_pybdsf_gaussian_catalogue(
        _artifact(root, result, "gaussian-catalogue-fits")
    )
    right_ascensions = [row.right_ascension_degrees for row in gaussians]
    declinations = [row.declination_degrees for row in gaussians]
    for catalogue in catalogues.values():
        for component in catalogue.gaussian_components:
            right_ascensions.append(component.position.right_ascension_degrees)
            declinations.append(component.position.declination_degrees)
    return right_ascensions, declinations


def _measure_case(  # noqa: PLR0913
    prepared: PreparedCase,
    *,
    image_kind: ImageKind,
    references: Mapping[str, tuple[Path, dict[str, Any]] | None],
    runs: Mapping[str, LaneRun],
    configuration: RapthorAgreementConfiguration,
    match_radius_beams: float,
) -> dict[str, Any]:
    """Measure every lane's decisions on one case against ``master``'s."""
    record: dict[str, Any] = {
        "case_id": prepared.case_id,
        "input_sha256": prepared.input_sha256,
        "image_kind": image_kind,
        "lane_status": {
            name: {"status": run.status, "seconds": run.seconds}
            | ({"error": run.error} if run.error else {})
            for name, run in runs.items()
        },
        "reference_available": {
            name: value is not None for name, value in references.items()
        },
    }
    master = references[_MASTER]
    succeeded = {
        name: run for name, run in runs.items() if run.status == "success"
    }
    if master is None or len(succeeded) != len(runs):
        record["status"] = "unmeasured"
        return record
    root, result = master
    metadata = FitsImageSource(
        prepared.input_path, prepared.supplied_metadata
    ).metadata()
    wcs = celestial_wcs_from_metadata(metadata)
    beam_fwhm_pixels, beam_area_pixels = _beam_pixels(metadata)
    image = load_fits_plane(prepared.input_path)
    reference_mask = load_mask_plane(
        _artifact(root, result, "island-mask-fits")
    )
    masks = {
        name: load_mask_plane(cast(Path, run.mask_path))
        for name, run in succeeded.items()
    }
    catalogues = {
        name: read_catalogue_fits_product(cast(Path, run.catalogue_path))
        for name, run in succeeded.items()
    }
    control = references[_CONTROL]
    if control is not None:
        masks[_CONTROL] = load_mask_plane(
            _artifact(*control, "island-mask-fits")
        )
    right_ascensions, declinations = _component_positions(master, catalogues)
    x, y = (
        wcs.wcs_world2pix(right_ascensions, declinations, 0)
        if right_ascensions
        else ([], [])
    )
    pixels = ComponentPixels.at_positions(x, y, metadata.shape_yx)
    union_mask = reference_mask.copy()
    for name in succeeded:
        union_mask |= masks[name]
    strata = component_strata(
        pixels,
        image=image,
        reference_rms=load_fits_plane(_artifact(root, result, "rms-map-fits")),
        union_mask=union_mask,
        beam_fwhm_pixels=beam_fwhm_pixels,
        beam_area_pixels=beam_area_pixels,
        rules=configuration.strata.rules(),
        image_kind=image_kind,
    )
    emission, weights = emission_pixels(
        image,
        floor_sigma=configuration.emission.floor_sigma,
        seed_sigma=configuration.emission.seed_sigma,
    )
    truth = None
    if prepared.truth:
        truth_x, truth_y = wcs.wcs_world2pix(
            [row.right_ascension_degrees for row in prepared.truth],
            [row.declination_degrees for row in prepared.truth],
            0,
        )
        truth = ComponentPixels.at_positions(
            truth_x, truth_y, metadata.shape_yx
        )
    reference_rows = pybdsf_cut_catalogue(
        _artifact(root, result, "source-catalogue-fits")
    )
    cut_rows = {
        name: hebog_cut_catalogue(
            catalogues[name], cast(Path, succeeded[name].view_path)
        )
        for name in succeeded
    }
    if control is not None:
        cut_rows[_CONTROL] = pybdsf_cut_catalogue(
            _artifact(*control, "source-catalogue-fits")
        )
    match_radius = match_radius_beams * float(
        np.sqrt(
            metadata.beam.major_fwhm_degrees * metadata.beam.minor_fwhm_degrees
        )
    )
    record |= {
        "status": "measured",
        "components": len(pixels),
        "stratum_sizes": {
            name: int(selection.sum()) for name, selection in strata.items()
        },
        "versus_master": {
            name: _counts_record(
                compare_decisions(mask, reference_mask, pixels, strata)
            )
            for name, mask in masks.items()
        },
        "compact_versus_continuum": {
            background: _counts_record(
                compare_decisions(
                    masks[f"compact-{background}"],
                    masks[f"continuum-{background}"],
                    pixels,
                    strata,
                )
            )
            for background in ("estimated", "zero")
            if {f"compact-{background}", f"continuum-{background}"}
            <= set(masks)
        },
        "emission_pixels": {
            name: {
                "counts": asdict(
                    compare_decisions(mask, reference_mask, emission, {})[
                        ALL_COMPONENTS
                    ]
                ),
                "weighted": asdict(
                    weighted_agreement(mask, reference_mask, emission, weights)
                ),
            }
            for name, mask in masks.items()
        },
        "truth": (
            None
            if truth is None
            else {
                name: asdict(
                    compare_decisions(mask, reference_mask, truth, {})[
                        ALL_COMPONENTS
                    ]
                )
                for name, mask in masks.items()
            }
        ),
        "catalogue_cuts": {
            "master": asdict(
                compare_catalogue_cuts(
                    reference_rows,
                    reference_rows,
                    match_radius_degrees=match_radius,
                )
            ),
        }
        | {
            name: asdict(
                compare_catalogue_cuts(
                    rows, reference_rows, match_radius_degrees=match_radius
                )
            )
            for name, rows in cut_rows.items()
        },
    }
    return record


def _pooled_lane(
    records: list[dict[str, Any]], name: str, threshold: float
) -> dict[str, Any]:
    """Pool one lane's counts over every measured case and apply the gate."""
    measured = [record for record in records if record["status"] == "measured"]
    strata: dict[str, DecisionCounts] = {}
    emission = DecisionCounts()
    truth = DecisionCounts()
    cuts = CatalogueCutCounts()
    weighted: list[float] = []
    for record in measured:
        if name not in record["versus_master"]:
            continue
        for stratum, counts in record["versus_master"][name].items():
            strata[stratum] = strata.get(
                stratum, DecisionCounts()
            ) + _decision_counts(counts)
        emission += DecisionCounts(**record["emission_pixels"][name]["counts"])
        agreement = WeightedAgreement(
            **record["emission_pixels"][name]["weighted"]
        ).agreement
        if agreement is not None:
            weighted.append(agreement)
        if record["truth"] is not None:
            truth += DecisionCounts(**record["truth"][name])
        cuts += CatalogueCutCounts(**record["catalogue_cuts"][name])
    outcome = gate_outcome(strata, threshold)
    return {
        "strata": _counts_record(strata),
        "gate": asdict(outcome),
        "emission_pixels": asdict(emission)
        | {
            "agreement": emission.agreement,
            "case_mean_flux_agreement": (
                float(np.mean(weighted)) if weighted else None
            ),
        },
        "truth": asdict(truth) | {"agreement": truth.agreement},
        "catalogue_cuts": asdict(cuts),
    }


def _pooled_pair(
    records: list[dict[str, Any]], background: str
) -> dict[str, Any]:
    """Pool compact's decisions against continuum's for one background."""
    strata: dict[str, DecisionCounts] = {}
    for record in records:
        pair = record.get("compact_versus_continuum", {}).get(background)
        for stratum, counts in (pair or {}).items():
            strata[stratum] = strata.get(
                stratum, DecisionCounts()
            ) + _decision_counts(counts)
    return _counts_record(strata)


def _print_summary(report: Mapping[str, Any]) -> None:
    lanes = report["lanes"]
    strata = list(next(iter(lanes.values()))["strata"])
    print(f"{'lane':22s}" + "".join(f"{name:>11s}" for name in strata))
    for name, lane in lanes.items():
        cells = "".join(
            f"{'-':>11s}"
            if lane["strata"][stratum]["agreement"] is None
            else f"{lane['strata'][stratum]['agreement']:>11.4f}"
            for stratum in strata
        )
        print(f"{name:22s}{cells}  {lane['gate']['status']}")
    print(f"profile rule: {report['profile_rule']}")


def _references(
    prepared: PreparedCase,
    references: Mapping[str, tuple[ContainerReference, dict[str, object]]],
    reference_result: Callable[..., tuple[Path, dict[str, Any]] | None],
    *,
    engine: str,
    run_missing: bool,
) -> dict[str, tuple[Path, dict[str, Any]] | None]:
    return {
        name: reference_result(
            prepared,
            reference=reference,
            identity=identity,
            output_root=_QUICK_CHECK_ROOT,
            engine=engine,
            run_missing=run_missing,
        )
        for name, (reference, identity) in references.items()
    }


def main() -> int:
    """Run the measurement and write its report."""
    args = _parse_args()
    started = time.perf_counter()
    configuration = load_agreement_configuration(args.configuration)
    quick_check_path = _ROOT / configuration.quick_check
    quick_check = load_quick_check_configuration(quick_check_path)
    cases: list[tuple[GeneratedCase | ImageCase, ImageKind]] = [
        (case, None) for case in quick_check.cases
    ]
    cases.extend((item.case, item.image_kind) for item in configuration.cases)
    if args.cases:
        cases = [item for item in cases if item[0].case_id in args.cases]
    label = args.label or _default_label()
    run_root = args.output_root / "runs" / label
    report_path = run_root / "report.json"
    if report_path.exists():
        raise FileExistsError(f"{report_path} already exists")
    references = {
        _MASTER: quick_check.reference,
        _CONTROL: configuration.control,
    }
    identities = {
        name: reference_identity(
            reference, engine=args.engine, repository_root=_ROOT
        )
        for name, reference in references.items()
    }
    reference_result = runpy.run_path(str(_QUICK_CHECK_SCRIPT))[
        "_reference_result"
    ]
    prepared: dict[str, PreparedCase] = {}
    case_references: dict[str, dict[str, Any]] = {}
    for case, _ in cases:
        prepared[case.case_id] = prepare_case(
            case,
            dataset_manifest=_ROOT / quick_check.dataset_manifest,
            repository_root=_ROOT,
            inputs_root=_QUICK_CHECK_ROOT / "inputs",
            allow_download=args.allow_download,
        )
        case_references[case.case_id] = _references(
            prepared[case.case_id],
            {
                name: (reference, identities[name])
                for name, reference in references.items()
            },
            reference_result,
            engine=args.engine,
            run_missing=not args.skip_references,
        )
    runs = _run_lanes(prepared, configuration, run_root, args.jobs)
    records = [
        _measure_case(
            prepared[case.case_id],
            image_kind=image_kind,
            references=case_references[case.case_id],
            runs={
                lane.name: runs[(case.case_id, lane.name)]
                for lane in configuration.lanes
            },
            configuration=configuration,
            match_radius_beams=quick_check.maximum_separation_beams,
        )
        for case, image_kind in cases
    ]
    threshold = configuration.agreement_threshold
    lanes = {
        lane.name: _pooled_lane(records, lane.name, threshold)
        for lane in configuration.lanes
    }
    elapsed = time.perf_counter() - started
    report: dict[str, Any] = {
        "schema_version": 1,
        "check_id": configuration.check_id,
        "label": label,
        "created_at": datetime.now(UTC).isoformat(),
        "hebog_version": hebog.__version__,
        "scientific_composition_sha256": (
            public_api._scientific_composition_sha256()
        ),
        "configuration_sha256": file_sha256(args.configuration),
        "quick_check_configuration_sha256": file_sha256(quick_check_path),
        "reference_identities": identities,
        "population": "fitted-gaussian-pixels",
        "agreement_threshold": threshold,
        "lanes": lanes,
        "control": _pooled_lane(records, _CONTROL, threshold),
        "compact_versus_continuum": {
            background: _pooled_pair(records, background)
            for background in ("estimated", "zero")
        },
        "reference_catalogue_cuts": asdict(
            sum(
                (
                    CatalogueCutCounts(**record["catalogue_cuts"]["master"])
                    for record in records
                    if record["status"] == "measured"
                ),
                CatalogueCutCounts(),
            )
        ),
        "profile_rule": {
            background: rapthor_profile(
                GateOutcome(**lanes[f"compact-{background}"]["gate"])
            )
            for background in ("estimated", "zero")
            if f"compact-{background}" in lanes
        },
        "elapsed_seconds": elapsed,
        "budget_seconds": configuration.budget_seconds,
        "within_budget": elapsed <= configuration.budget_seconds,
        "cases": records,
    }
    write_report(report_path, report)
    _print_summary(report)
    print(f"report: {report_path} in {elapsed:.0f} s", flush=True)
    return int(any(run.status == "failure" for run in runs.values()))


if __name__ == "__main__":
    raise SystemExit(main())
