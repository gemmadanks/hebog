#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
"""Run the quick science check and optionally compare with a baseline.

Cases, settings and tolerances come from
``config/checks/quick-science-check.json``. Generated inputs are materialised
and real cut-outs are cropped once, then reused. Pinned PyBDSF ``master``
runs once per input in its local Podman image and is cached under
``benchmark-results/quick-check/references``. Hebog runs every time through
the public API.

Exit status is 1 when a case fails or, with ``--baseline``, when a metric
regresses beyond tolerance. The check is a regression detector, not
scientific qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import runpy
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import hebog
from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.executors import SerialExecutor
from hebog.io import (
    FitsImageSource,
    read_catalogue_fits_product,
)
from hebog.validation.products import load_pybdsf_catalogue
from hebog.validation.quick_check import (
    MetricValues,
    PreparedCase,
    QuickCheckConfiguration,
    compare_reports,
    file_sha256,
    load_quick_check_configuration,
    map_metrics,
    prepare_case,
    public_catalogue_sources,
    reference_metrics,
    truth_metrics,
    write_report,
)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIGURATION = _ROOT / "config/checks/quick-science-check.json"
_DEFAULT_OUTPUT = _ROOT / "benchmark-results/quick-check"
_PREPARE = _ROOT / "scripts/benchmark/prepare_notebook_comparison.py"
_SUMMARY_METRICS = (
    "truth.completeness",
    "truth.reliability",
    "truth.integrated_flux_error_p95",
    "pybdsf_master.completeness",
    "pybdsf_master.reliability",
    "pybdsf_master.integrated_flux_error_p50",
    "pybdsf_master.rms_error_p50",
    "pybdsf_master.mask_iou",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configuration", type=Path, default=_DEFAULT_CONFIGURATION
    )
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--label",
        help="run directory name (default: commit and time)",
    )
    parser.add_argument("--baseline", type=Path, help="earlier report.json")
    parser.add_argument("--cases", nargs="+", help="run only these case IDs")
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
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{commit}{'-dirty' if dirty else ''}-{stamp}"


def _image_identity(engine: str, image: str) -> str:
    result = subprocess.run(
        [engine, "image", "inspect", "--format", "{{.Id}}", image],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _reference_result(
    prepared: PreparedCase,
    *,
    configuration: QuickCheckConfiguration,
    output_root: Path,
    engine: str,
    run_missing: bool,
) -> tuple[Path, dict[str, Any]] | None:
    """Return a cached reference result, running the container if needed.

    A reference failure, such as PyBDSF refusing an all-blank image, is
    cached next to the result directory so later runs do not repeat it; the
    case is then reported without reference metrics.
    """
    reference = configuration.reference
    output = (
        output_root
        / "references"
        / prepared.case_id
        / file_sha256(prepared.reference_input_path)[:16]
        / reference.finder_id
    )
    failure = output.with_name(f"{output.name}.failed.json")
    if failure.exists():
        return None
    if not (output / "result.json").exists():
        if not run_missing:
            return None
        run_container = runpy.run_path(str(_PREPARE))["_run_container"]
        try:
            run_container(
                repository_root=_ROOT,
                comparison_root=output_root,
                engine=engine,
                image=reference.container_image,
                input_path=prepared.reference_input_path,
                output=output,
                case_id=prepared.case_id,
                finder_id=reference.finder_id,
                ncores=reference.ncores,
            )
        except subprocess.CalledProcessError as error:
            failure.write_text(
                json.dumps(
                    {
                        "case_id": prepared.case_id,
                        "finder_id": reference.finder_id,
                        "exit_status": error.returncode,
                        "note": "reference run failed; see the console log",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"{prepared.case_id}: reference run failed", flush=True)
            return None
    result = cast(
        dict[str, Any], json.loads((output / "result.json").read_text())
    )
    if result.get("status") != "success":
        raise ValueError(f"reference run did not succeed: {output}")
    return output, result


def _artifact(root: Path, result: dict[str, Any], role: str) -> Path:
    return root / result["artifacts"][role]["path"]


def _case_metrics(
    prepared: PreparedCase,
    finder_result: hebog.SourceFinderResult,
    reference: tuple[Path, dict[str, Any]] | None,
    configuration: QuickCheckConfiguration,
) -> MetricValues:
    beam = (
        FitsImageSource(prepared.input_path, prepared.supplied_metadata)
        .metadata()
        .beam
    )
    beam_fwhm_degrees = math.sqrt(
        beam.major_fwhm_degrees * beam.minor_fwhm_degrees
    )
    catalogue = read_catalogue_fits_product(finder_result.catalogue)
    separation = configuration.maximum_separation_beams
    metrics: MetricValues = {}
    if prepared.truth is not None and prepared.noise_rms_jy_per_beam:
        metrics |= truth_metrics(
            prepared.truth,
            public_catalogue_sources(catalogue, level="components"),
            beam_fwhm_degrees=beam_fwhm_degrees,
            maximum_separation_beams=separation,
            noise_rms_jy_per_beam=prepared.noise_rms_jy_per_beam,
        )
    if reference is not None:
        root, result = reference
        metrics |= reference_metrics(
            load_pybdsf_catalogue(
                _artifact(root, result, "source-catalogue-fits")
            ),
            public_catalogue_sources(catalogue, level="sources"),
            beam_fwhm_degrees=beam_fwhm_degrees,
            maximum_separation_beams=separation,
        )
        metrics |= map_metrics(
            "pybdsf_master",
            reference_rms_path=_artifact(root, result, "rms-map-fits"),
            reference_mask_path=_artifact(root, result, "island-mask-fits"),
            rms_path=finder_result.rms_path,
            mask_path=finder_result.mask_path,
        )
    if prepared.published_rms_path is not None:
        metrics |= map_metrics(
            "published",
            reference_rms_path=prepared.published_rms_path,
            reference_mask_path=prepared.published_mask_path,
            rms_path=finder_result.rms_path,
            mask_path=finder_result.mask_path,
        )
    return {
        name: (value if value is None or math.isfinite(value) else None)
        for name, value in sorted(metrics.items())
    }


def _run_case(
    prepared: PreparedCase,
    *,
    configuration: QuickCheckConfiguration,
    run_root: Path,
    reference: tuple[Path, dict[str, Any]] | None,
) -> dict[str, Any]:
    settings = configuration.hebog
    record: dict[str, Any] = {
        "case_id": prepared.case_id,
        "input_sha256": prepared.input_sha256,
        "reference_available": reference is not None,
    }
    started = time.perf_counter()
    try:
        result = hebog.find_sources(
            hebog.SourceFinderRequest(
                image_path=prepared.input_path,
                output_directory=run_root / prepared.case_id / "products",
                run_id=prepared.case_id,
                supplied_metadata=prepared.supplied_metadata,
            ),
            SourceFinderConfig(
                detection_threshold_sigma=settings.detection_threshold_sigma,
                island_threshold_sigma=settings.island_threshold_sigma,
                minimum_island_pixels=settings.minimum_island_pixels,
                profile=settings.profile,
            ),
            SerialExecutor(),
        )
    except Exception as error:  # reported per case, never hidden
        record |= {
            "status": "failure",
            "error": f"{type(error).__name__}: {error}",
            "elapsed_seconds": time.perf_counter() - started,
            "metrics": {},
        }
        return record
    record |= {
        "status": "success",
        "error": None,
        "elapsed_seconds": time.perf_counter() - started,
        "source_count": result.source_count,
        "component_count": result.gaussian_component_count,
        "metrics": _case_metrics(prepared, result, reference, configuration),
    }
    return record


def _format(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _print_summary(report: dict[str, Any]) -> None:
    headers = (
        "case",
        "status",
        "s",
        *(m.split(".", 1)[1] for m in _SUMMARY_METRICS),
    )
    print(" | ".join(headers))
    for case in report["cases"]:
        values = [case["metrics"].get(metric) for metric in _SUMMARY_METRICS]
        print(
            " | ".join(
                (
                    case["case_id"],
                    case["status"],
                    f"{case['elapsed_seconds']:.1f}",
                    *(_format(value) for value in values),
                )
            )
        )
    print(
        f"Hebog time {report['hebog_elapsed_seconds']:.0f} s of a "
        f"{report['change_budget_seconds']:.0f} s budget; total "
        f"{report['total_elapsed_seconds']:.0f} s"
    )


def main() -> int:
    args = _parse_args()
    started = time.perf_counter()
    configuration = load_quick_check_configuration(args.configuration)
    output_root = args.output_root.resolve()
    label = args.label or _default_label()
    run_root = output_root / "runs" / label
    if run_root.exists():
        raise SystemExit(f"run directory already exists: {run_root}")
    selected: set[str] = set(cast(list[str], args.cases or []))
    unknown = selected - {case.case_id for case in configuration.cases}
    if unknown:
        raise SystemExit(f"unknown case IDs: {sorted(unknown)}")
    records: list[dict[str, Any]] = []
    for case in configuration.cases:
        if selected and case.case_id not in selected:
            continue
        prepared = prepare_case(
            case,
            configuration=configuration,
            repository_root=_ROOT,
            inputs_root=output_root / "inputs",
            allow_download=args.allow_download,
        )
        reference = _reference_result(
            prepared,
            configuration=configuration,
            output_root=output_root,
            engine=args.engine,
            run_missing=not args.skip_references,
        )
        record = _run_case(
            prepared,
            configuration=configuration,
            run_root=run_root,
            reference=reference,
        )
        print(
            f"{record['case_id']}: {record['status']} in "
            f"{record['elapsed_seconds']:.1f} s",
            flush=True,
        )
        records.append(record)
    hebog_seconds = sum(record["elapsed_seconds"] for record in records)
    report: dict[str, Any] = {
        "schema_version": 1,
        "check_id": configuration.check_id,
        "label": label,
        "created_at": datetime.now(UTC).isoformat(),
        "hebog_version": hebog.__version__,
        "scientific_composition_sha256": (
            public_api._scientific_composition_sha256()
        ),
        "configuration_sha256": hashlib.sha256(
            args.configuration.read_bytes()
        ).hexdigest(),
        "reference_finder_id": configuration.reference.finder_id,
        "reference_container_image_id": (
            None
            if args.skip_references
            else _image_identity(
                args.engine, configuration.reference.container_image
            )
        ),
        "change_budget_seconds": configuration.change_budget_seconds,
        "hebog_elapsed_seconds": hebog_seconds,
        "within_budget": hebog_seconds <= configuration.change_budget_seconds,
        "total_elapsed_seconds": time.perf_counter() - started,
        "cases": records,
    }
    write_report(run_root / "report.json", report)
    _print_summary(report)
    print(f"Report: {run_root / 'report.json'}")
    failed = [record for record in records if record["status"] != "success"]
    findings = ()
    if args.baseline is not None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        if selected:
            baseline["cases"] = [
                case
                for case in baseline["cases"]
                if case["case_id"] in selected
            ]
        findings = compare_reports(report, baseline, configuration.tolerances)
        for finding in findings:
            print(
                f"REGRESSION {finding.case_id} {finding.metric}: "
                f"{finding.baseline} -> {finding.current} ({finding.reason})"
            )
        if not findings:
            print(f"No regressions against {args.baseline}")
    return 1 if failed or findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
