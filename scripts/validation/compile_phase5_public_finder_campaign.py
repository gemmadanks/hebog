#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile one sealed Phase 5 public-finder campaign exactly once."""

from __future__ import annotations

import argparse
import io
import runpy
import tarfile
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

from hebog.validation.products import (
    load_comparison_catalogue,
    load_fits_plane,
)
from hebog.validation.public_comparison import (
    HydraDepth,
    HydraFinder,
    PublicCatalogueAssociationReport,
    PublicCatalogueComponent,
    adapt_hydra_columns,
    apparent_peak_snr,
    associate_public_catalogues,
    associate_truth_with_guard,
    gaussian_fwhm_arcsec,
    sdc1_position_angle_degrees,
    summarize_hydra_association,
    summarize_shape_diagnostics,
    summarize_truth_association,
)

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = _ROOT / "config/contracts/phase-5-public-finder-protocol.json"
_DECISION_PATH = (
    _ROOT / "config/contracts/phase-5-public-finder-execution-decision.json"
)
_CAMPAIGN_PATH = (
    _ROOT / "benchmark-results/phase-5/public-finder-comparison/campaign.json"
)
_OUTPUT_PATH = _ROOT / "benchmark-results/phase-5/public-finder-analysis.json"
_ACQUISITION_PATH = (
    _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
    "acquisition.json"
)
_SELECTION_PATH = (
    _ROOT
    / "benchmark-results/phase-5/public-comparison-selection/population.json"
)
_SCHEMA_REVIEW_PATH = (
    _ROOT / "config/contracts/phase-5-public-comparison-schema-review.json"
)
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_public_finder_protocol.py")
)
_TRUTH_COLUMN_COUNT = 12
_MINIMUM_TRUTH_SNR = 5.0
_CASE_COUNT = 10
_HYDRA_DIAGNOSTIC_COUNT = 16
_EXPECTED_ARTIFACT_PATHS = {
    "background-fits": "background.fits",
    "rms-fits": "rms.fits",
    "segment-catalogue-json": "segment_catalogue.json",
    "segment-labels-fits": "segment_labels.fits",
    "segment-mask-fits": "segment_mask.fits",
}
_DIAGNOSTIC_METRICS = (
    "absolute-mean-offset-x",
    "absolute-mean-offset-y",
    "completeness",
    "duplicate-fraction",
    "integrated-flux-median",
    "integrated-flux-p95",
    "matched_count",
    "position-p95",
    "truth_count",
)


def evaluate_metric_limits(
    population: str,
    metrics: dict[str, float | int | None],
    limits: dict[str, dict[str, float]],
) -> dict[str, object]:
    """Evaluate one SDC1 population without cross-population compensation."""
    decisions = []
    for metric_name, limit in sorted(limits.items()):
        value = metrics.get(metric_name)
        if value is None:
            passed = False
            reason = "metric-unavailable"
        elif "at_least" in limit:
            passed = float(value) >= limit["at_least"]
            reason = "at-least"
        elif "at_most" in limit:
            passed = float(value) <= limit["at_most"]
            reason = "at-most"
        else:
            raise ValueError(f"unsupported public metric limit: {metric_name}")
        decisions.append(
            {
                "metric": metric_name,
                "value": value,
                "limit": limit,
                "comparison": reason,
                "passed": passed,
            }
        )
    return {
        "population": population,
        "metrics": metrics,
        "decisions": decisions,
        "passed": all(item["passed"] for item in decisions),
    }


def _acquisition_paths() -> dict[str, Path]:
    """Resolve every frozen raw public artifact."""
    acquisition = _HELPERS["json_object"](_ACQUISITION_PATH)
    paths = {
        item["identifier"]: _ACQUISITION_PATH.parent / "raw" / item["filename"]
        for item in acquisition["artifacts"]
    }
    for item in acquisition["artifacts"]:
        if (
            _HELPERS["file_sha256"](paths[item["identifier"]])
            != item["sha256"]
        ):
            raise ValueError("public acquisition artifact checksum changed")
    return paths


def _case_artifacts(
    campaign_directory: Path,
    summary: dict[str, Any],
    *,
    case_id: str,
    configuration_sha256: str,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Verify one terminal result and its complete five-product bundle."""
    expected_result_path = Path("results") / case_id / "result.json"
    if (
        summary.get("case_id") != case_id
        or summary.get("status") != "success"
        or Path(cast(str, summary.get("result_path"))) != expected_result_path
    ):
        raise ValueError("public finder terminal result identity changed")
    result_path = campaign_directory / expected_result_path
    if _HELPERS["file_sha256"](result_path) != summary["result_sha256"]:
        raise ValueError("public finder terminal result checksum changed")
    result = _HELPERS["json_object"](result_path)
    input_record_path = campaign_directory / "inputs" / case_id / "input.json"
    input_record = _HELPERS["json_object"](input_record_path)
    input_location = input_record.get("input_location")
    input_relative = Path(cast(str, input_record.get("input_path")))
    if (
        result.get("status") != "success"
        or result.get("case_id") != case_id
        or result.get("configuration_sha256") != configuration_sha256
        or input_record.get("case_id") != case_id
        or input_location not in {"repository", "staging"}
        or input_relative.is_absolute()
        or ".." in input_relative.parts
    ):
        raise ValueError("public finder result provenance changed")
    input_root = (
        _ROOT if input_location == "repository" else campaign_directory
    )
    input_path = input_root / input_relative
    if _HELPERS["file_sha256"](input_path) != input_record.get(
        "input_sha256"
    ) or result.get("input_sha256") != input_record.get("input_sha256"):
        raise ValueError("public finder result input checksum changed")
    expected_core = input_record.get("local_core_yx_half_open")
    if (
        expected_core is not None
        and result.get("core_bounds_yx_half_open") != expected_core
    ):
        raise ValueError("public finder result core changed")
    artifacts = {}
    for role, identity in result["artifacts"].items():
        if identity.get("path") != _EXPECTED_ARTIFACT_PATHS.get(role):
            raise ValueError("public finder product identity changed")
        path = result_path.parent / _EXPECTED_ARTIFACT_PATHS[role]
        if (
            path.stat().st_size != identity["byte_size"]
            or _HELPERS["file_sha256"](path) != identity["sha256"]
        ):
            raise ValueError("public finder product checksum changed")
        artifacts[role] = path
    if set(artifacts) != set(_EXPECTED_ARTIFACT_PATHS):
        raise ValueError("public finder product roles are incomplete")
    return result, artifacts


def _validate_campaign_manifest(
    campaign: dict[str, Any],
    *,
    expected_case_ids: tuple[str, ...],
    protocol_sha256: str,
    execution_decision_sha256: str,
) -> None:
    """Require one exact sealed campaign before opening scientific products."""
    results = campaign.get("results")
    if (
        campaign.get("status") != "terminal-raw-results-sealed"
        or campaign.get("case_count") != len(expected_case_ids)
        or campaign.get("successful_case_count") != len(expected_case_ids)
        or campaign.get("protocol_sha256") != protocol_sha256
        or campaign.get("execution_decision_sha256")
        != execution_decision_sha256
        or not isinstance(results, list)
        or tuple(item.get("case_id") for item in results) != expected_case_ids
        or any(item.get("status") != "success" for item in results)
    ):
        raise ValueError("public finder campaign provenance is invalid")


def _validate_campaign_request(
    campaign_directory: Path,
    campaign: dict[str, Any],
    *,
    protocol_sha256: str,
    execution_decision_sha256: str,
    identity_review_sha256: str,
) -> None:
    """Bind a terminal manifest to its exact authorized opening request."""
    request_path = campaign_directory / "request.json"
    request = _HELPERS["json_object"](request_path)
    if (
        _HELPERS["file_sha256"](request_path) != campaign.get("request_sha256")
        or request.get("status") != "authorized-private-staging"
        or request.get("protocol_sha256") != protocol_sha256
        or request.get("execution_decision_sha256")
        != execution_decision_sha256
        or request.get("identity_review_sha256") != identity_review_sha256
        or request.get("case_count") != _CASE_COUNT
    ):
        raise ValueError("public finder campaign request provenance changed")


def _candidate_components(
    artifacts: dict[str, Path],
    *,
    shape_role: Literal["fitted", "deconvolved"] = "fitted",
) -> tuple[PublicCatalogueComponent, ...]:
    """Load Hebog components and sample their candidate-owned local RMS."""
    catalogue = load_comparison_catalogue(artifacts["segment-catalogue-json"])
    rms = load_fits_plane(artifacts["rms-fits"])
    celestial = WCS(
        cast(fits.Header, fits.getheader(artifacts["rms-fits"])),
        relax=True,
    ).celestial
    components = []
    for source in catalogue:
        x_pixel, y_pixel = celestial.all_world2pix(
            source.right_ascension_degrees,
            source.declination_degrees,
            0,
        )
        x_index = int(np.clip(np.rint(x_pixel), 0, rms.shape[1] - 1))
        y_index = int(np.clip(np.rint(y_pixel), 0, rms.shape[0] - 1))
        local_rms = float(rms[y_index, x_index])
        signal_to_noise = (
            source.peak_flux_jy_per_beam / local_rms
            if np.isfinite(local_rms) and local_rms > 0.0
            else None
        )
        shape = (
            source.fitted_shape
            if shape_role == "fitted"
            else source.deconvolved_shape
        )
        integrated_flux = (
            source.association_integrated_flux_jy
            if source.association_integrated_flux_jy is not None
            else source.integrated_flux_jy
        )
        components.append(
            PublicCatalogueComponent(
                identifier=source.identifier,
                right_ascension_degrees=source.right_ascension_degrees,
                declination_degrees=source.declination_degrees,
                integrated_flux_jy=integrated_flux,
                peak_signal_to_noise=signal_to_noise,
                major_axis_arcsec=(
                    shape.major_fwhm_degrees * 3600.0
                    if shape is not None
                    else None
                ),
                minor_axis_arcsec=(
                    shape.minor_fwhm_degrees * 3600.0
                    if shape is not None
                    else None
                ),
                position_angle_degrees=(
                    shape.position_angle_degrees if shape is not None else None
                ),
            )
        )
    return tuple(components)


def _restoring_beam_fwhm_arcsec(path: Path) -> float:
    """Return the geometric-mean restoring beam from one public image."""
    header = cast(fits.Header, fits.getheader(path))
    try:
        major = float(cast(Any, header["BMAJ"]))
        minor = float(cast(Any, header["BMIN"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("public Hydra restoring beam is invalid") from error
    beam = float(np.sqrt(major * minor) * 3600.0)
    if not np.isfinite(beam) or beam <= 0.0:
        raise ValueError("public Hydra restoring beam is invalid")
    return beam


def _truth_rows(path: Path) -> np.ndarray:
    """Load the official fixed-width SDC1 truth columns."""
    rows = np.loadtxt(path, dtype=np.float64)
    rows = np.atleast_2d(rows)
    if rows.shape[1] != _TRUTH_COLUMN_COUNT:
        raise ValueError("SDC1 truth column count changed")
    return rows


def _primary_beam_response(
    rows: np.ndarray,
    *,
    primary_beam: np.ndarray,
    primary_beam_wcs: WCS,
) -> np.ndarray:
    """Bilinearly sample the approved primary beam at truth centroids."""
    x_pixel, y_pixel = primary_beam_wcs.all_world2pix(
        rows[:, 3], rows[:, 4], 0
    )
    return np.asarray(
        map_coordinates(
            primary_beam,
            (y_pixel, x_pixel),
            order=1,
            mode="constant",
            cval=np.nan,
            prefilter=False,
        ),
        dtype=np.float64,
    )


def _sdc1_components(
    rows: np.ndarray,
    responses: np.ndarray,
) -> tuple[
    tuple[PublicCatalogueComponent, ...],
    dict[str, tuple[float, int]],
]:
    """Normalize admitted SDC1 truth into the public association schema."""
    major, minor = gaussian_fwhm_arcsec(rows[:, 10], rows[:, 7], rows[:, 8])
    snr = apparent_peak_snr(
        integrated_flux_jy=rows[:, 5],
        primary_beam_response=responses,
        major_fwhm_arcsec=major,
        minor_fwhm_arcsec=minor,
    )
    apparent_flux = rows[:, 5] * responses
    finite = np.all(np.isfinite(rows[:, :12]), axis=1)
    finite &= np.isfinite(responses) & np.isfinite(snr)
    finite &= (snr >= _MINIMUM_TRUTH_SNR) & (apparent_flux > 0.0)
    selected_rows = rows[finite]
    selected_flux = apparent_flux[finite]
    selected_snr = snr[finite]
    selected_major = major[finite]
    selected_minor = minor[finite]
    components = tuple(
        PublicCatalogueComponent(
            identifier=f"sdc1:{int(row[0])}",
            right_ascension_degrees=float(row[3]),
            declination_degrees=float(row[4]),
            integrated_flux_jy=float(flux),
            peak_signal_to_noise=float(source_snr),
            major_axis_arcsec=float(source_major),
            minor_axis_arcsec=float(source_minor),
            position_angle_degrees=sdc1_position_angle_degrees(float(row[9])),
        )
        for row, flux, source_snr, source_major, source_minor in zip(
            selected_rows,
            selected_flux,
            selected_snr,
            selected_major,
            selected_minor,
            strict=True,
        )
    )
    attributes = {
        f"sdc1:{int(row[0])}": (float(source_snr), int(row[10]))
        for row, source_snr in zip(
            selected_rows,
            selected_snr,
            strict=True,
        )
    }
    return components, attributes


def _truth_for_stratum(  # noqa: PLR0913
    all_rows: np.ndarray,
    image_x_pixel: np.ndarray,
    image_y_pixel: np.ndarray,
    *,
    primary_beam: np.ndarray,
    primary_beam_wcs: WCS,
    stratum: dict[str, Any],
    halo_pixels: int,
) -> tuple[
    tuple[PublicCatalogueComponent, ...],
    frozenset[str],
    dict[str, tuple[float, int]],
]:
    """Return binding core truth plus non-binding halo guard truth."""
    x_start, x_stop, y_start, y_stop = stratum["bounds_xy_half_open"]
    in_halo = (
        (image_x_pixel >= x_start - halo_pixels)
        & (image_x_pixel < x_stop + halo_pixels)
        & (image_y_pixel >= y_start - halo_pixels)
        & (image_y_pixel < y_stop + halo_pixels)
    )
    rows = all_rows[in_halo]
    responses = _primary_beam_response(
        rows,
        primary_beam=primary_beam,
        primary_beam_wcs=primary_beam_wcs,
    )
    components, attributes = _sdc1_components(rows, responses)
    pixel_by_id = {
        f"sdc1:{int(row[0])}": (float(x), float(y))
        for row, x, y in zip(
            rows,
            image_x_pixel[in_halo],
            image_y_pixel[in_halo],
            strict=True,
        )
    }
    binding = frozenset(
        item.identifier
        for item in components
        if x_start <= pixel_by_id[item.identifier][0] < x_stop
        and y_start <= pixel_by_id[item.identifier][1] < y_stop
    )
    return components, binding, attributes


def _diagnostic_subset(
    report: PublicCatalogueAssociationReport,
    truth: tuple[PublicCatalogueComponent, ...],
    candidates: tuple[PublicCatalogueComponent, ...],
    identifiers: frozenset[str],
) -> dict[str, float | int | None]:
    """Return only truth-subpopulation metrics with reviewed meanings."""
    summary = summarize_truth_association(
        report,
        truth,
        candidates,
        binding_truth_identifiers=identifiers,
    )
    return {name: summary[name] for name in _DIAGNOSTIC_METRICS}


def _sdc1_subpopulation_diagnostics(  # noqa: PLR0913
    report: PublicCatalogueAssociationReport,
    *,
    truth: tuple[PublicCatalogueComponent, ...],
    candidates: tuple[PublicCatalogueComponent, ...],
    binding: frozenset[str],
    attributes: dict[str, tuple[float, int]],
    diagnostics: dict[str, Any],
) -> dict[str, object]:
    """Stratify report-only SDC1 metrics by SNR and truth size code."""
    snr_bins = []
    for lower, upper in diagnostics["apparent_peak_snr_bins_half_open"]:
        selected = frozenset(
            identifier
            for identifier in binding
            if attributes[identifier][0] >= lower
            and (upper is None or attributes[identifier][0] < upper)
        )
        snr_bins.append(
            {
                "lower_inclusive": lower,
                "upper_exclusive": upper,
                "metrics": _diagnostic_subset(
                    report,
                    truth,
                    candidates,
                    selected,
                ),
            }
        )
    size_codes = []
    for size_code in diagnostics["truth_size_codes"]:
        selected = frozenset(
            identifier
            for identifier in binding
            if attributes[identifier][1] == size_code
        )
        size_codes.append(
            {
                "size_code": size_code,
                "metrics": _diagnostic_subset(
                    report,
                    truth,
                    candidates,
                    selected,
                ),
            }
        )
    return {
        "apparent_peak_snr_bins": snr_bins,
        "truth_size_codes": size_codes,
    }


def _official_sdc1_diagnostics(protocol: dict[str, Any]) -> dict[str, object]:
    """Record why official report-only metrics are unavailable."""
    diagnostics = protocol["sdc1"]["diagnostics"]
    review = _HELPERS["json_object"](_SCHEMA_REVIEW_PATH)
    submissions = review["sdc1"]["submitted_catalogues"]["target_submissions"]
    if len(submissions) != diagnostics["published_submission_count"]:
        raise ValueError("approved SDC1 submission inventory changed")
    submission_reason = diagnostics["published_submission_policy"]
    return {
        "binding": False,
        "official_sdc1_score": {
            "status": "unavailable",
            "reason": diagnostics["official_sdc1_score"],
        },
        "official_population_classification": {
            "status": "unavailable",
            "reason": diagnostics["official_population_classification"],
        },
        "published_submissions": [
            {
                "member": item["member"],
                "status": "unavailable",
                "reason": submission_reason,
            }
            for item in submissions
        ],
    }


def _prefix_candidates(
    components: tuple[PublicCatalogueComponent, ...],
    prefix: str,
) -> tuple[PublicCatalogueComponent, ...]:
    """Make candidate IDs globally unique for the pooled endpoint."""
    return tuple(
        PublicCatalogueComponent(
            identifier=f"{prefix}:{item.identifier}",
            right_ascension_degrees=item.right_ascension_degrees,
            declination_degrees=item.declination_degrees,
            integrated_flux_jy=item.integrated_flux_jy,
            peak_signal_to_noise=item.peak_signal_to_noise,
            major_axis_arcsec=item.major_axis_arcsec,
            minor_axis_arcsec=item.minor_axis_arcsec,
            position_angle_degrees=item.position_angle_degrees,
        )
        for item in components
    )


def _hydra_member(finder: str, depth: str) -> str:
    """Return one approved archive catalogue member."""
    return (
        "emu_pilot_sample_2x2deg.hydra_dir/catalogues/"
        f"{depth}/emu_pilot_sample_2x2deg.hydra.{finder}.{depth}.fits"
    )


def _hydra_catalogue(
    archive: tarfile.TarFile,
    *,
    finder: HydraFinder,
    depth: HydraDepth,
) -> tuple[tuple[PublicCatalogueComponent, ...], dict[str, object]]:
    """Load one approved Hydra finder table and its native residual fields."""
    extracted = archive.extractfile(_hydra_member(finder, depth))
    if extracted is None:
        raise ValueError("approved Hydra finder catalogue is absent")
    payload = extracted.read()
    with fits.open(io.BytesIO(payload), mode="readonly") as hdus:
        table_hdu = cast(
            Any,
            next(
                hdu for hdu in hdus if getattr(hdu, "data", None) is not None
            ),
        )
        table = table_hdu.data
        names = tuple(cast(str, name).lower() for name in table.names)
        columns = {name: np.asarray(table[name]) for name in names}
        adapted = adapt_hydra_columns(
            finder_id=finder,
            depth=depth,
            columns=columns,
        )
        rms_values = columns.get("rms_noise_bane")
        residuals = {
            name: float(np.mean(np.asarray(values)[np.isfinite(values)]))
            for name, values in columns.items()
            if "residual" in name and np.any(np.isfinite(values))
        }
    components = []
    for index, item in enumerate(adapted):
        rms = (
            float(rms_values[index]) * 1e-3 if rms_values is not None else None
        )
        snr = (
            item.peak_flux_jy_per_beam / rms
            if item.peak_flux_jy_per_beam is not None
            and rms is not None
            and np.isfinite(rms)
            and rms > 0.0
            else None
        )
        components.append(
            PublicCatalogueComponent(
                identifier=f"{finder}:{depth}:{item.native_id}",
                right_ascension_degrees=item.ra_deg,
                declination_degrees=item.dec_deg,
                integrated_flux_jy=item.integrated_flux_jy,
                peak_signal_to_noise=snr,
                major_axis_arcsec=item.major_axis_arcsec,
                minor_axis_arcsec=item.minor_axis_arcsec,
                position_angle_degrees=item.position_angle_deg,
            )
        )
    return (
        tuple(components),
        {
            "values": residuals,
            "unavailable_reason": (
                None
                if residuals
                else "published-catalogue-has-no-native-residual-fields"
            ),
        },
    )


def _threshold_deep_to_shallow(
    deep: tuple[PublicCatalogueComponent, ...],
    shallow: tuple[PublicCatalogueComponent, ...],
) -> tuple[
    tuple[PublicCatalogueComponent, ...],
    float | None,
    str | None,
]:
    """Apply the observed shallow catalogue's minimum finite peak SNR."""
    shallow_snr = tuple(
        item.peak_signal_to_noise
        for item in shallow
        if item.peak_signal_to_noise is not None
    )
    if not shallow_snr:
        return (
            deep,
            None,
            "no-finite-shallow-peak-snr-is-available-for-this-finder",
        )
    threshold = min(shallow_snr)
    return (
        tuple(
            item
            for item in deep
            if item.peak_signal_to_noise is not None
            and item.peak_signal_to_noise >= threshold
        ),
        threshold,
        None,
    )


def _hydra_diagnostic(  # noqa: PLR0913
    name: str,
    left: tuple[PublicCatalogueComponent, ...],
    right: tuple[PublicCatalogueComponent, ...],
    *,
    beam_arcsec: float,
    threshold: float | None = None,
    threshold_unavailable_reason: str | None = None,
) -> dict[str, object]:
    """Compile one named non-binding Hydra association."""
    report = associate_public_catalogues(
        left,
        right,
        beam_fwhm_arcsec=beam_arcsec,
        maximum_separation_beams=0.5,
    )
    return {
        "comparison": name,
        "beam_fwhm_arcsec": beam_arcsec,
        "shallow_peak_snr_threshold": threshold,
        "shallow_peak_snr_threshold_unavailable_reason": (
            threshold_unavailable_reason
        ),
        **summarize_hydra_association(report, left, right),
    }


def compile_public_finder_analysis(  # noqa: PLR0915
    campaign_path: Path,
    protocol: dict[str, Any],
    *,
    execution_decision_sha256: str,
    identity_review_sha256: str,
) -> dict[str, object]:
    """Compile binding SDC1 science and non-binding Hydra diagnostics."""
    campaign = _HELPERS["json_object"](campaign_path)
    campaign_directory = campaign_path.parent
    expected_case_ids = tuple(
        f"sdc1-{item['stratum']}-{item['tile_id']}"
        for item in protocol["sdc1"]["strata"]
    ) + tuple(item["case_id"] for item in protocol["hydra"]["cases"])
    protocol_sha256 = _HELPERS["file_sha256"](_PROTOCOL_PATH)
    _validate_campaign_manifest(
        campaign,
        expected_case_ids=expected_case_ids,
        protocol_sha256=protocol_sha256,
        execution_decision_sha256=execution_decision_sha256,
    )
    _validate_campaign_request(
        campaign_directory,
        campaign,
        protocol_sha256=protocol_sha256,
        execution_decision_sha256=execution_decision_sha256,
        identity_review_sha256=identity_review_sha256,
    )
    results = {
        item["case_id"]: _case_artifacts(
            campaign_directory,
            item,
            case_id=item["case_id"],
            configuration_sha256=protocol["candidate"]["configuration_sha256"],
        )
        for item in campaign["results"]
    }
    raw = _acquisition_paths()
    all_truth = _truth_rows(raw["truth-catalogue"])
    with fits.open(raw["image"], mode="readonly", memmap=True) as hdus:
        image_wcs = WCS(cast(Any, hdus[0]).header, relax=True).celestial
    image_x_values, image_y_values = image_wcs.all_world2pix(
        all_truth[:, 3],
        all_truth[:, 4],
        0,
    )
    image_x_pixel = np.asarray(image_x_values, dtype=np.float64)
    image_y_pixel = np.asarray(image_y_values, dtype=np.float64)
    primary_beam = load_fits_plane(raw["primary-beam"])
    with fits.open(raw["primary-beam"], mode="readonly", memmap=True) as hdus:
        primary_beam_wcs = WCS(cast(Any, hdus[0]).header, relax=True).celestial
    endpoints = []
    pooled_truth: dict[str, PublicCatalogueComponent] = {}
    pooled_candidates = []
    pooled_binding: set[str] = set()
    pooled_attributes: dict[str, tuple[float, int]] = {}
    limits = protocol["sdc1"]["binding_metric_limits"]
    diagnostic_protocol = protocol["sdc1"]["diagnostics"]
    for stratum in protocol["sdc1"]["strata"]:
        case_id = f"sdc1-{stratum['stratum']}-{stratum['tile_id']}"
        _result, artifacts = results[case_id]
        candidates = _prefix_candidates(
            _candidate_components(artifacts, shape_role="deconvolved"),
            cast(str, stratum["stratum"]),
        )
        truth, binding, attributes = _truth_for_stratum(
            all_truth,
            image_x_pixel,
            image_y_pixel,
            primary_beam=primary_beam,
            primary_beam_wcs=primary_beam_wcs,
            stratum=stratum,
            halo_pixels=protocol["sdc1"]["halo_pixels_yx"][0],
        )
        report = associate_truth_with_guard(
            tuple(item for item in truth if item.identifier in binding),
            tuple(item for item in truth if item.identifier not in binding),
            candidates,
            beam_fwhm_arcsec=protocol["sdc1"]["beam_fwhm_arcsec"],
            maximum_separation_beams=protocol["matching"][
                "maximum_separation_beams"
            ],
        )
        metrics = summarize_truth_association(
            report,
            truth,
            candidates,
            binding_truth_identifiers=binding,
        )
        endpoint = evaluate_metric_limits(stratum["stratum"], metrics, limits)
        endpoint["shape_diagnostics"] = summarize_shape_diagnostics(
            report,
            truth,
            candidates,
            included_left_identifiers=binding,
        )
        endpoint["subpopulation_diagnostics"] = (
            _sdc1_subpopulation_diagnostics(
                report,
                truth=truth,
                candidates=candidates,
                binding=binding,
                attributes=attributes,
                diagnostics=diagnostic_protocol,
            )
        )
        endpoints.append(endpoint)
        pooled_truth.update({item.identifier: item for item in truth})
        pooled_candidates.extend(candidates)
        pooled_binding.update(binding)
        pooled_attributes.update(attributes)
    pooled_report = associate_truth_with_guard(
        tuple(
            item
            for item in pooled_truth.values()
            if item.identifier in pooled_binding
        ),
        tuple(
            item
            for item in pooled_truth.values()
            if item.identifier not in pooled_binding
        ),
        tuple(pooled_candidates),
        beam_fwhm_arcsec=protocol["sdc1"]["beam_fwhm_arcsec"],
        maximum_separation_beams=protocol["matching"][
            "maximum_separation_beams"
        ],
    )
    overall = evaluate_metric_limits(
        "overall",
        summarize_truth_association(
            pooled_report,
            tuple(pooled_truth.values()),
            tuple(pooled_candidates),
            binding_truth_identifiers=frozenset(pooled_binding),
        ),
        limits,
    )
    overall["shape_diagnostics"] = summarize_shape_diagnostics(
        pooled_report,
        tuple(pooled_truth.values()),
        tuple(pooled_candidates),
        included_left_identifiers=frozenset(pooled_binding),
    )
    overall["subpopulation_diagnostics"] = _sdc1_subpopulation_diagnostics(
        pooled_report,
        truth=tuple(pooled_truth.values()),
        candidates=tuple(pooled_candidates),
        binding=frozenset(pooled_binding),
        attributes=pooled_attributes,
        diagnostics=diagnostic_protocol,
    )
    endpoints.insert(0, overall)
    hebog_hydra = {
        depth: _candidate_components(results[f"hydra-{depth}"][1])
        for depth in ("deep", "shallow")
    }
    hydra_beams = {
        depth: _restoring_beam_fwhm_arcsec(raw[f"{depth}-image"])
        for depth in ("deep", "shallow")
    }
    published: dict[tuple[str, str], tuple[PublicCatalogueComponent, ...]] = {}
    residuals: dict[str, dict[str, object]] = {}
    with tarfile.open(raw["hydra-archive"], mode="r:gz") as archive:
        ordered_catalogues = sorted(
            (
                (finder, depth)
                for finder in protocol["hydra"]["published_finders"]
                for depth in ("deep", "shallow")
            ),
            key=lambda item: (
                archive.getmember(_hydra_member(item[0], item[1])).offset_data
            ),
        )
        for finder, depth in ordered_catalogues:
            components, native_residuals = _hydra_catalogue(
                archive,
                finder=cast(HydraFinder, finder),
                depth=cast(HydraDepth, depth),
            )
            published[(finder, depth)] = components
            residuals[f"{finder}-{depth}"] = native_residuals
    diagnostics = []
    deep_proxy, threshold, threshold_reason = _threshold_deep_to_shallow(
        hebog_hydra["deep"], hebog_hydra["shallow"]
    )
    diagnostics.append(
        _hydra_diagnostic(
            "hebog-deep-versus-hebog-shallow",
            deep_proxy,
            hebog_hydra["shallow"],
            beam_arcsec=float(
                np.sqrt(hydra_beams["deep"] * hydra_beams["shallow"])
            ),
            threshold=threshold,
            threshold_unavailable_reason=threshold_reason,
        )
    )
    for finder in protocol["hydra"]["published_finders"]:
        diagnostics.extend(
            (
                _hydra_diagnostic(
                    f"hebog-{depth}-versus-{finder}-{depth}",
                    hebog_hydra[depth],
                    published[(finder, depth)],
                    beam_arcsec=hydra_beams[depth],
                )
                for depth in ("deep", "shallow")
            )
        )
        published_deep, threshold, threshold_reason = (
            _threshold_deep_to_shallow(
                published[(finder, "deep")],
                published[(finder, "shallow")],
            )
        )
        diagnostics.append(
            _hydra_diagnostic(
                f"{finder}-deep-versus-{finder}-shallow",
                published_deep,
                published[(finder, "shallow")],
                beam_arcsec=float(
                    np.sqrt(hydra_beams["deep"] * hydra_beams["shallow"])
                ),
                threshold=threshold,
                threshold_unavailable_reason=threshold_reason,
            )
        )
    return {
        "schema_version": 1,
        "analysis_id": "phase-5-public-finder-terminal-analysis",
        "campaign_sha256": _HELPERS["file_sha256"](campaign_path),
        "protocol_sha256": protocol_sha256,
        "execution_decision_sha256": execution_decision_sha256,
        "identity_review_sha256": identity_review_sha256,
        "successful_hebog_run_count": campaign["successful_case_count"],
        "expected_hebog_run_count": protocol["case_count"],
        "sdc1_endpoints": endpoints,
        "sdc1_all_binding_endpoints_passed": all(
            item["passed"] for item in endpoints
        ),
        "sdc1_official_diagnostics": _official_sdc1_diagnostics(protocol),
        "hydra_diagnostics": diagnostics,
        "hydra_beam_fwhm_arcsec_by_depth": hydra_beams,
        "hydra_published_residual_summaries": residuals,
        "hydra_diagnostics_complete": (
            len(diagnostics) == _HYDRA_DIAGNOSTIC_COUNT
        ),
        "scientific_outcomes_before_runtime": True,
        "runtime": {
            case_id: result[0]["elapsed_seconds"]
            for case_id, result in sorted(results.items())
        },
    }


def _parse_args() -> argparse.Namespace:
    """Parse the exact separately authorized compilation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, default=_DECISION_PATH)
    parser.add_argument("--campaign", type=Path, default=_CAMPAIGN_PATH)
    parser.add_argument("--output", type=Path, default=_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    """Reject pending authority, then compile one sealed campaign once."""
    arguments = _parse_args()
    decision = _HELPERS["load_public_finder_execution_decision"](
        arguments.authorization
    )
    if not decision["compilation_authorized"]:
        raise ValueError("public finder compilation is not authorized")
    if (
        arguments.authorization.resolve() != _DECISION_PATH.resolve()
        or arguments.campaign.resolve() != _CAMPAIGN_PATH.resolve()
        or arguments.output.resolve() != _OUTPUT_PATH.resolve()
    ):
        raise ValueError("public finder compilation path changed")
    protocol = _HELPERS["load_public_finder_protocol"](_PROTOCOL_PATH)
    analysis = compile_public_finder_analysis(
        arguments.campaign,
        protocol,
        execution_decision_sha256=_HELPERS["file_sha256"](
            arguments.authorization
        ),
        identity_review_sha256=decision["identity_review"]["sha256"],
    )
    _HELPERS["write_once_json"](arguments.output, analysis)


if __name__ == "__main__":
    main()
