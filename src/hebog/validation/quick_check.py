# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Fixed-case scientific regression check for everyday development.

The quick science check runs the public finder on a small, fixed set of
generated and real images and reports the measurements Rapthor consumes
against injected truth, cached pinned-PyBDSF-``master`` outputs and, where
published, survey RMS and mask maps. A report can be compared with an earlier
report to flag regressions beyond configured tolerances.

It is a regression detector for one development machine, not powered
scientific parity: every case is one realization, and no confidence interval
is claimed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import numpy as np
from astropy.io import fits
from pydantic import BaseModel, ConfigDict, Field

from hebog.data_models import SuppliedImageMetadata
from hebog.data_models.catalogues import SourceCatalogue
from hebog.io import FitsImageSource
from hebog.science.models import CatalogueSource
from hebog.validation.campaigns import phase_four_truth_source
from hebog.validation.comparison import (
    CatalogueComparisonReport,
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.datasets import DatasetRecord, load_dataset_manifest
from hebog.validation.materialization import materialize_dataset
from hebog.validation.products import load_fits_plane
from hebog.validation.remote_cutouts import fetch_remote_cutout

MetricValues = dict[str, float | None]
"""Flat metric name to value; ``None`` means not measurable for the case."""

REFERENCE_WORKER = Path("scripts/benchmark/run_notebook_reference.py")
"""Container worker for one reference finder run, relative to the checkout."""
REFERENCE_CONTAINER_COMMAND = Path(
    "scripts/benchmark/prepare_notebook_comparison.py"
)
"""Host script that builds the reference container command line."""
_NOTEBOOK_CONFIGURATION = Path("config/comparisons/notebook-comparison.json")
_IDEAL_ONE_SIGMA_COVERAGE = 0.6827
_SNR_BRIGHT = 10.0


class _QuickCheckModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImageWindow(_QuickCheckModel):
    """A square window in zero-based image pixels."""

    x_start: int = Field(ge=0)
    y_start: int = Field(ge=0)
    size: int = Field(gt=0)


class RemoteImage(_QuickCheckModel):
    """A public FITS image and the window fetched from it."""

    url: str = Field(min_length=1)
    window: ImageWindow


class PublishedMap(_QuickCheckModel):
    """A published survey map cut-out and where it came from."""

    path: str = Field(min_length=1)
    source: RemoteImage | None = None


class PublishedMaps(_QuickCheckModel):
    """Published PyBDSF RMS and island-mask maps aligned with an image."""

    rms: PublishedMap
    mask: PublishedMap


class GeneratedCase(_QuickCheckModel):
    """A synthetic image with injected truth from the dataset manifest."""

    kind: Literal["generated"]
    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    dataset_id: str = Field(min_length=1)


class ImageCase(_QuickCheckModel):
    """A real image, optionally cropped locally or fetched as a cut-out."""

    kind: Literal["image"]
    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    image: str = Field(min_length=1)
    window: ImageWindow | None = None
    remote_source: RemoteImage | None = None
    supplied_metadata: dict[str, float] | None = None
    published_maps: PublishedMaps | None = None


QuickCheckCase = Annotated[
    GeneratedCase | ImageCase, Field(discriminator="kind")
]


class HebogSettings(_QuickCheckModel):
    """Public finder configuration used for every case."""

    detection_threshold_sigma: float
    island_threshold_sigma: float
    minimum_island_pixels: int
    profile: Literal["continuum", "compact"]


class ReferenceSettings(_QuickCheckModel):
    """The containerised reference finder and its resources."""

    finder_id: Literal["pinned-pybdsf-master"]
    container_image: str = Field(min_length=1)
    ncores: int = Field(gt=0)


class RegressionTolerances(_QuickCheckModel):
    """Largest change in the worse direction reported as unchanged."""

    fraction_drop: float = Field(ge=0)
    separation_increase_beams: float = Field(ge=0)
    fractional_error_increase: float = Field(ge=0)
    coverage_error_increase: float = Field(ge=0)


class QuickCheckConfiguration(_QuickCheckModel):
    """Versioned case set, settings and tolerances for the quick check."""

    schema_version: Literal[1]
    check_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    dataset_manifest: str
    hebog: HebogSettings
    reference: ReferenceSettings
    maximum_separation_beams: float = Field(gt=0)
    change_budget_seconds: float = Field(gt=0)
    tolerances: RegressionTolerances
    cases: tuple[QuickCheckCase, ...] = Field(min_length=1)


def load_quick_check_configuration(path: Path) -> QuickCheckConfiguration:
    """Load and validate one quick-check configuration."""
    configuration = QuickCheckConfiguration.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    identifiers = [case.case_id for case in configuration.cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("quick-check case identifiers must be unique")
    return configuration


@dataclass(frozen=True, slots=True)
class PreparedCase:
    """One ready input, its reference input and any injected truth."""

    case_id: str
    input_path: Path
    input_sha256: str
    reference_input_path: Path
    supplied_metadata: SuppliedImageMetadata | None
    truth: tuple[CatalogueSource, ...] | None
    noise_rms_jy_per_beam: float | None
    published_rms_path: Path | None
    published_mask_path: Path | None


def file_sha256(path: Path) -> str:
    """Hash one file in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _without_shapes(source: CatalogueSource) -> CatalogueSource:
    """Keep position and flux; shape comparison is not part of this check."""
    return replace(
        source,
        fitted_shape=None,
        deconvolved_shape=None,
        deconvolved_major_fwhm_degrees=None,
        deconvolution_status="unavailable",
        quality_flags=(),
    )


def truth_catalogue(dataset: DatasetRecord) -> tuple[CatalogueSource, ...]:
    """Return every injected source as a position-and-flux truth row."""
    return tuple(
        _without_shapes(
            phase_four_truth_source(
                source, dataset, identifier=f"truth-{index:03d}"
            )
        )
        for index, source in enumerate(dataset.recipe.sources)
    )


def _write_local_window(
    source: Path, destination: Path, window: ImageWindow
) -> None:
    """Crop one image plane, keeping singleton axes and the sky frame."""
    with fits.open(source, mode="readonly", memmap=True) as hdus:
        primary = cast(Any, hdus[0])
        leading = (0,) * (primary.header["NAXIS"] - 2)
        stop_y = window.y_start + window.size
        stop_x = window.x_start + window.size
        height, width = primary.shape[-2:]
        if stop_y > height or stop_x > width:
            raise ValueError(f"quick-check window lies outside {source}")
        values = np.asarray(
            primary.section[
                (
                    *leading,
                    slice(window.y_start, stop_y),
                    slice(window.x_start, stop_x),
                )
            ]
        )
        header = primary.header.copy()
    header["CRPIX1"] = float(header["CRPIX1"]) - window.x_start
    header["CRPIX2"] = float(header["CRPIX2"]) - window.y_start
    destination.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(
        data=values.reshape((1,) * len(leading) + values.shape),
        header=header,
    ).writeto(destination)


def _reference_input(
    input_path: Path,
    supplied: SuppliedImageMetadata | None,
    destination: Path,
) -> Path:
    """Give PyBDSF the beam and frequency Hebog resolved for the input.

    PyBDSF reads frequency only from a spectral axis, ``RESTFREQ`` or
    ``FREQ``, not ``RESTFRQ``, and needs all three beam keywords. When the
    header lacks any of these, a copy with Hebog's resolved values is used,
    so both finders measure the same physical image.
    """
    header = cast(fits.Header, fits.getheader(input_path))
    axis_count = int(cast(int, header.get("NAXIS", 0)))
    axis_types = [
        str(cast(object, header.get(f"CTYPE{axis}", "")))
        for axis in range(1, axis_count + 1)
    ]
    has_frequency = any(kind.startswith("FREQ") for kind in axis_types) or (
        "RESTFREQ" in header or "FREQ" in header
    )
    has_beam = all(keyword in header for keyword in ("BMAJ", "BMIN", "BPA"))
    if has_frequency and has_beam:
        return input_path
    if destination.exists():
        return destination
    metadata = FitsImageSource(input_path, supplied).metadata()
    with fits.open(input_path, mode="readonly") as hdus:
        primary = cast(Any, hdus[0])
        completed = primary.header.copy()
        data = np.asarray(primary.data)
    if not has_frequency:
        completed["RESTFREQ"] = metadata.reference_frequency_hz
    for keyword, value in (
        ("BMAJ", metadata.beam.major_fwhm_degrees),
        ("BMIN", metadata.beam.minor_fwhm_degrees),
        ("BPA", metadata.beam.position_angle_degrees),
    ):
        if keyword not in completed:
            completed[keyword] = value
    destination.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=data, header=completed).writeto(destination)
    return destination


def prepare_case(
    case: GeneratedCase | ImageCase,
    *,
    dataset_manifest: Path,
    repository_root: Path,
    inputs_root: Path,
    allow_download: bool = False,
) -> PreparedCase:
    """Materialise, crop or fetch one case input, reusing cached files.

    Generated cases name a dataset in ``dataset_manifest``; image paths are
    relative to ``repository_root``.
    """
    case_root = inputs_root / case.case_id
    if isinstance(case, GeneratedCase):
        dataset = next(
            item
            for item in load_dataset_manifest(dataset_manifest).datasets
            if item.identifier == case.dataset_id
        )
        input_path = case_root / f"{dataset.recipe_sha256[:16]}.fits"
        if not input_path.exists():
            input_path.parent.mkdir(parents=True, exist_ok=True)
            materialize_dataset(dataset_manifest, case.dataset_id, input_path)
        return PreparedCase(
            case_id=case.case_id,
            input_path=input_path,
            input_sha256=file_sha256(input_path),
            reference_input_path=input_path,
            supplied_metadata=None,
            truth=truth_catalogue(dataset),
            noise_rms_jy_per_beam=dataset.recipe.noise_rms,
            published_rms_path=None,
            published_mask_path=None,
        )
    image_path = repository_root / case.image
    for remote, local in (
        (case.remote_source, image_path),
        *(
            (item.source, repository_root / item.path)
            for item in (
                (case.published_maps.rms, case.published_maps.mask)
                if case.published_maps is not None
                else ()
            )
        ),
    ):
        if local.exists() or remote is None:
            continue
        if not allow_download:
            raise FileNotFoundError(
                f"{local} is missing; rerun with downloads allowed"
            )
        fetch_remote_cutout(
            remote.url,
            local,
            x_start=remote.window.x_start,
            y_start=remote.window.y_start,
            size=remote.window.size,
        )
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    input_path = image_path
    if case.window is not None:
        window = case.window
        input_path = case_root / (
            f"x{window.x_start}-y{window.y_start}-s{window.size}.fits"
        )
        if not input_path.exists():
            _write_local_window(image_path, input_path, window)
    supplied = (
        SuppliedImageMetadata(**case.supplied_metadata)
        if case.supplied_metadata is not None
        else None
    )
    return PreparedCase(
        case_id=case.case_id,
        input_path=input_path,
        input_sha256=file_sha256(input_path),
        reference_input_path=_reference_input(
            input_path, supplied, case_root / "reference-input.fits"
        ),
        supplied_metadata=supplied,
        truth=None,
        noise_rms_jy_per_beam=None,
        published_rms_path=(
            repository_root / case.published_maps.rms.path
            if case.published_maps is not None
            else None
        ),
        published_mask_path=(
            repository_root / case.published_maps.mask.path
            if case.published_maps is not None
            else None
        ),
    )


def public_catalogue_sources(
    catalogue: SourceCatalogue,
    *,
    level: Literal["sources", "components"],
) -> tuple[CatalogueSource, ...]:
    """Project published sources or Gaussian components for comparison."""
    rows = (
        catalogue.sources
        if level == "sources"
        else catalogue.gaussian_components
    )
    projected: list[CatalogueSource] = []
    for row in rows:
        identifier = (
            row.source_id
            if level == "sources"
            else cast(Any, row).gaussian_component_id
        )
        projected.append(
            CatalogueSource(
                identifier=identifier,
                right_ascension_degrees=row.position.right_ascension_degrees,
                declination_degrees=row.position.declination_degrees,
                peak_flux_jy_per_beam=row.flux.peak_flux_jy_per_beam,
                integrated_flux_jy=row.flux.integrated_flux_jy,
                right_ascension_error_degrees=(
                    row.position.right_ascension_error_degrees
                ),
                declination_error_degrees=(
                    row.position.declination_error_degrees
                ),
                peak_flux_error_jy_per_beam=row.flux.peak_flux_error_jy_per_beam,
                integrated_flux_error_jy=row.flux.integrated_flux_error_jy,
            )
        )
    return tuple(projected)


def _coverage(report: CatalogueComparisonReport, metric: str) -> float | None:
    """Return one-sigma coverage of a reported uncertainty, if measured."""
    for item in report.uncertainty_calibration:
        if item.metric == metric:
            return item.coverage_fraction
    return None


def _catalogue_metrics(
    prefix: str,
    report: CatalogueComparisonReport,
) -> MetricValues:
    """Flatten the catalogue measurements this check tracks."""
    return {
        f"{prefix}.reference_count": float(report.reference_count),
        f"{prefix}.candidate_count": float(report.candidate_count),
        f"{prefix}.completeness": report.completeness,
        f"{prefix}.reliability": report.reliability,
        f"{prefix}.separation_p50_beams": report.median_separation_beam_fwhm,
        f"{prefix}.separation_p95_beams": (
            report.percentile_95_separation_beam_fwhm
        ),
        f"{prefix}.peak_flux_error_p50": (
            report.median_absolute_peak_flux_fractional_difference
        ),
        f"{prefix}.peak_flux_error_p95": (
            report.percentile_95_absolute_peak_flux_fractional_difference
        ),
        f"{prefix}.integrated_flux_error_p50": (
            report.median_absolute_integrated_flux_fractional_difference
        ),
        f"{prefix}.integrated_flux_error_p95": (
            report.percentile_95_absolute_integrated_flux_fractional_difference
        ),
    }


def truth_metrics(
    truth: Sequence[CatalogueSource],
    components: Sequence[CatalogueSource],
    *,
    beam_fwhm_degrees: float,
    maximum_separation_beams: float,
    noise_rms_jy_per_beam: float,
) -> MetricValues:
    """Compare published Gaussian components with injected truth."""
    report = compare_catalogues(
        truth,
        components,
        beam_fwhm_degrees=beam_fwhm_degrees,
        maximum_separation_beams=maximum_separation_beams,
    )
    metrics = _catalogue_metrics("truth", report)
    metrics["truth.right_ascension_coverage"] = _coverage(
        report, "right-ascension"
    )
    metrics["truth.declination_coverage"] = _coverage(report, "declination")
    bright = [
        source
        for source in truth
        if source.peak_flux_jy_per_beam >= _SNR_BRIGHT * noise_rms_jy_per_beam
    ]
    metrics["truth.snr10_completeness"] = (
        compare_catalogues(
            bright,
            components,
            beam_fwhm_degrees=beam_fwhm_degrees,
            maximum_separation_beams=maximum_separation_beams,
        ).completeness
        if bright
        else None
    )
    return metrics


def map_metrics(
    prefix: str,
    *,
    reference_rms_path: Path | None,
    reference_mask_path: Path | None,
    rms_path: Path,
    mask_path: Path,
) -> MetricValues:
    """Compare Hebog's RMS and mask products with reference maps."""
    metrics: MetricValues = {}
    if reference_rms_path is not None:
        rms_report = compare_rms_maps(
            load_fits_plane(reference_rms_path), load_fits_plane(rms_path)
        )
        metrics[f"{prefix}.rms_error_p50"] = (
            rms_report.median_absolute_fractional_difference
        )
        metrics[f"{prefix}.rms_error_p95"] = (
            rms_report.percentile_95_absolute_fractional_difference
        )
    if reference_mask_path is not None:
        reference_mask = load_fits_plane(reference_mask_path)
        valid = np.isfinite(reference_mask)
        mask_report = compare_masks(
            np.nan_to_num(reference_mask) > 0,
            load_fits_plane(mask_path) > 0,
            valid_mask=valid,
        )
        metrics[f"{prefix}.mask_iou"] = mask_report.intersection_over_union
    return metrics


def reference_metrics(
    reference_sources: Sequence[CatalogueSource],
    hebog_sources: Sequence[CatalogueSource],
    *,
    beam_fwhm_degrees: float,
    maximum_separation_beams: float,
) -> MetricValues:
    """Compare published sources with the reference finder's source list."""
    return _catalogue_metrics(
        "pybdsf_master",
        compare_catalogues(
            [_without_shapes(source) for source in reference_sources],
            hebog_sources,
            beam_fwhm_degrees=beam_fwhm_degrees,
            maximum_separation_beams=maximum_separation_beams,
        ),
    )


_HIGHER_IS_BETTER = (
    "completeness",
    "reliability",
    "mask_iou",
)
_LOWER_IS_BETTER_SEPARATION = ("separation_p50_beams", "separation_p95_beams")
_LOWER_IS_BETTER_FRACTION = (
    "peak_flux_error_p50",
    "peak_flux_error_p95",
    "integrated_flux_error_p50",
    "integrated_flux_error_p95",
    "rms_error_p50",
    "rms_error_p95",
)
_COVERAGE = ("right_ascension_coverage", "declination_coverage")


@dataclass(frozen=True, slots=True)
class RegressionFinding:
    """One change in the worse direction beyond tolerance."""

    case_id: str
    metric: str
    baseline: float | str | None
    current: float | str | None
    reason: str


def _metric_regression(
    metric: str,
    baseline: float,
    current: float,
    tolerances: RegressionTolerances,
) -> str | None:
    """Explain a worse-direction change beyond tolerance, if any."""
    name = metric.rsplit(".", 1)[-1]
    if name.endswith("completeness") or name in _HIGHER_IS_BETTER:
        if baseline - current > tolerances.fraction_drop:
            return f"dropped by {baseline - current:.3f}"
    elif name in _LOWER_IS_BETTER_SEPARATION:
        if current - baseline > tolerances.separation_increase_beams:
            return f"increased by {current - baseline:.3f} beams"
    elif name in _LOWER_IS_BETTER_FRACTION:
        if current - baseline > tolerances.fractional_error_increase:
            return f"increased by {current - baseline:.3f}"
    elif name in _COVERAGE:
        baseline_error = abs(baseline - _IDEAL_ONE_SIGMA_COVERAGE)
        current_error = abs(current - _IDEAL_ONE_SIGMA_COVERAGE)
        if current_error - baseline_error > tolerances.coverage_error_increase:
            return "moved further from 68.3% one-sigma coverage"
    return None


def compare_reports(
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    tolerances: RegressionTolerances,
) -> tuple[RegressionFinding, ...]:
    """Return regressions of a report against a baseline report.

    A current case absent from the baseline is also a finding: it has not
    been compared, so the run cannot claim that it did not regress.
    """
    findings: list[RegressionFinding] = []
    current_cases = {case["case_id"]: case for case in current["cases"]}
    baseline_ids = {case["case_id"] for case in baseline["cases"]}
    findings.extend(
        RegressionFinding(
            case_id, "status", None, case["status"], "not in baseline"
        )
        for case_id, case in current_cases.items()
        if case_id not in baseline_ids
    )
    for baseline_case in baseline["cases"]:
        case_id = baseline_case["case_id"]
        case = current_cases.get(case_id)
        if case is None:
            findings.append(
                RegressionFinding(
                    case_id, "status", baseline_case["status"], None, "missing"
                )
            )
            continue
        if baseline_case["status"] == "success" != case["status"]:
            findings.append(
                RegressionFinding(
                    case_id,
                    "status",
                    baseline_case["status"],
                    case["status"],
                    case.get("error") or "no longer succeeds",
                )
            )
            continue
        for metric, baseline_value in baseline_case["metrics"].items():
            current_value = case["metrics"].get(metric)
            if baseline_value is None:
                continue
            if current_value is None:
                findings.append(
                    RegressionFinding(
                        case_id,
                        metric,
                        baseline_value,
                        None,
                        "no longer measurable",
                    )
                )
                continue
            reason = _metric_regression(
                metric, baseline_value, current_value, tolerances
            )
            if reason is not None:
                findings.append(
                    RegressionFinding(
                        case_id, metric, baseline_value, current_value, reason
                    )
                )
    return tuple(findings)


def reference_cache_directory(
    references_root: Path,
    *,
    case_id: str,
    reference_input_sha256: str,
    finder_id: str,
    identity: Mapping[str, object],
) -> Path:
    """Return the cache directory for one reference run.

    ``identity`` holds everything that can change the reference result or
    its timing: the immutable container image ID, the finder settings, the
    core count and the reference code identity from
    :func:`reference_code_sha256`. Changing any of them selects a new
    directory, so neither a cached result nor a cached failure is reused
    across references.
    """
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (
        references_root
        / case_id
        / reference_input_sha256[:16]
        / f"{finder_id}-{digest[:16]}"
    )


_IMPORT_CLOSURE = """
import runpy, sys
runpy.run_path(sys.argv[1], run_name="quick_check_code_identity")
for module in list(sys.modules.values()):
    path = getattr(module, "__file__", None)
    if path:
        print(path)
"""


def reference_code_sha256(
    worker: Path,
    *,
    repository_root: Path,
    source_root: Path,
) -> str:
    """Hash a reference worker and every repository module it imports.

    The reference container runs the worker from the mounted checkout, so a
    change to the worker or to any repository module in its import closure
    can change the reference products. The closure is found by importing the
    worker, without running its entry point, in a fresh interpreter that
    uses ``source_root`` as its import path. Modules outside
    ``repository_root``, such as the standard library, are not hashed.
    """
    environment = dict(os.environ, PYTHONPATH=str(source_root))
    listing = subprocess.run(
        [sys.executable, "-c", _IMPORT_CLOSURE, str(worker)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    ).stdout.splitlines()
    root = repository_root.resolve()
    files = {worker.resolve()} | {
        Path(line).resolve()
        for line in listing
        if Path(line).resolve().is_relative_to(root)
    }
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def container_image_identity(engine: str, image: str) -> str:
    """Return the immutable local ID of one container image."""
    result = subprocess.run(
        [engine, "image", "inspect", "--format", "{{.Id}}", image],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def reference_identity(
    reference: ReferenceSettings, *, engine: str, repository_root: Path
) -> dict[str, object]:
    """Describe everything that can change a reference result or timing.

    The container runs the notebook reference worker and its ``hebog``
    imports from the checkout, and the host builds its command line, so both
    are part of the identity alongside the image, finder settings and core
    count.
    """
    settings = json.loads(
        (repository_root / _NOTEBOOK_CONFIGURATION).read_text(encoding="utf-8")
    )
    return {
        "container_image_id": container_image_identity(
            engine, reference.container_image
        ),
        "finder_settings": settings["reference_finders"][reference.finder_id],
        "ncores": reference.ncores,
        "reference_code_sha256": reference_code_sha256(
            repository_root / REFERENCE_WORKER,
            repository_root=repository_root,
            source_root=repository_root / "src",
        ),
        "container_command_sha256": file_sha256(
            repository_root / REFERENCE_CONTAINER_COMMAND
        ),
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    """Write one canonical report without replacing an earlier one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(report, allow_nan=False, indent=2, sort_keys=True)
            + "\n"
        )
