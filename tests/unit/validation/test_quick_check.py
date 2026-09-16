# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false
"""Configuration, inputs, metrics and regressions of the quick check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from pydantic import ValidationError

from hebog.data_models import (
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.science.models import CatalogueSource
from hebog.validation.quick_check import (
    GeneratedCase,
    ImageCase,
    RegressionTolerances,
    compare_reports,
    load_quick_check_configuration,
    map_metrics,
    prepare_case,
    public_catalogue_sources,
    reference_cache_directory,
    truth_metrics,
    write_report,
)

_ROOT = Path(__file__).parents[3]
_CONFIGURATION = _ROOT / "config/checks/quick-science-check.json"
_TOLERANCES = RegressionTolerances(
    fraction_drop=0.02,
    separation_increase_beams=0.05,
    fractional_error_increase=0.02,
    coverage_error_increase=0.05,
)
_BEAM_DEGREES = 5.0 / 3600.0


def _source(
    identifier: str,
    ra: float,
    peak: float,
    *,
    error: float | None = None,
) -> CatalogueSource:
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=ra,
        declination_degrees=0.0,
        peak_flux_jy_per_beam=peak,
        integrated_flux_jy=peak,
        right_ascension_error_degrees=error,
        declination_error_degrees=error,
    )


def _report(
    metrics: dict[str, float | None], status: str = "success"
) -> dict[str, Any]:
    return {
        "cases": [
            {
                "case_id": "case",
                "status": status,
                "error": None if status == "success" else "boom",
                "metrics": metrics,
            }
        ]
    }


def test_checked_in_configuration_loads_every_case() -> None:
    """The committed case set is valid and references known datasets."""
    configuration = load_quick_check_configuration(_CONFIGURATION)
    manifest = json.loads(
        (_ROOT / configuration.dataset_manifest).read_text(encoding="utf-8")
    )
    dataset_ids = {item["identifier"] for item in manifest["datasets"]}

    generated = [
        case for case in configuration.cases if isinstance(case, GeneratedCase)
    ]
    assert {case.dataset_id for case in generated} == dataset_ids
    assert any(isinstance(case, ImageCase) for case in configuration.cases)
    assert configuration.reference.finder_id == "pinned-pybdsf-master"


def test_configuration_rejects_duplicate_and_unknown_fields(
    tmp_path: Path,
) -> None:
    """Ambiguous case IDs and misspelt settings fail before any run."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    duplicate = dict(document, cases=[document["cases"][0]] * 2)
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(duplicate))
    with pytest.raises(ValueError, match="unique"):
        load_quick_check_configuration(path)

    misspelt = dict(document, tolerance=document["tolerances"])
    path.write_text(json.dumps(misspelt))
    with pytest.raises(ValidationError):
        load_quick_check_configuration(path)


def test_truth_metrics_count_completeness_reliability_and_bright_sources() -> (
    None
):
    """A missed faint source lowers completeness but not SNR>=10 recovery."""
    noise = 1e-4
    truth = (
        _source("bright", 10.0, 50 * noise),
        _source("faint", 10.1, 5 * noise),
    )
    found = (
        _source("a", 10.0, 50 * noise, error=0.1 / 3600),
        _source("spurious", 10.2, 6 * noise),
    )

    metrics = truth_metrics(
        truth,
        found,
        beam_fwhm_degrees=_BEAM_DEGREES,
        maximum_separation_beams=1.0,
        noise_rms_jy_per_beam=noise,
    )

    assert metrics["truth.completeness"] == 0.5
    assert metrics["truth.reliability"] == 0.5
    assert metrics["truth.snr10_completeness"] == 1.0
    assert metrics["truth.separation_p50_beams"] == 0.0


def test_map_metrics_ignore_invalid_reference_pixels(tmp_path: Path) -> None:
    """RMS error is fractional and mask IoU uses valid reference pixels."""
    reference_rms = tmp_path / "reference-rms.fits"
    reference_mask = tmp_path / "reference-mask.fits"
    rms = tmp_path / "rms.fits"
    mask = tmp_path / "mask.fits"
    fits.PrimaryHDU(np.full((1, 1, 4, 4), 2.0)).writeto(reference_rms)
    fits.PrimaryHDU(np.full((4, 4), 2.2)).writeto(rms)
    reference = np.zeros((4, 4))
    reference[0, :2] = 1.0
    reference[3, 3] = np.nan
    fits.PrimaryHDU(reference).writeto(reference_mask)
    candidate = np.zeros((4, 4), dtype=np.uint8)
    candidate[0, 0] = 1
    candidate[3, 3] = 1
    fits.PrimaryHDU(candidate).writeto(mask)

    metrics = map_metrics(
        "published",
        reference_rms_path=reference_rms,
        reference_mask_path=reference_mask,
        rms_path=rms,
        mask_path=mask,
    )

    assert metrics["published.rms_error_p50"] == pytest.approx(0.1)
    assert metrics["published.mask_iou"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("metric", "baseline", "current", "regressed"),
    [
        ("truth.completeness", 0.9, 0.87, True),
        ("truth.completeness", 0.9, 0.89, False),
        ("pybdsf_master.mask_iou", 0.8, 0.85, False),
        ("truth.separation_p95_beams", 0.1, 0.2, True),
        ("pybdsf_master.rms_error_p50", 0.05, 0.06, False),
        ("published.rms_error_p95", 0.05, 0.08, True),
        ("truth.right_ascension_coverage", 0.68, 0.9, True),
        ("truth.right_ascension_coverage", 0.5, 0.66, False),
        ("truth.reference_count", 6.0, 1.0, False),
    ],
)
def test_regressions_follow_each_metric_direction(
    metric: str,
    baseline: float,
    current: float,
    regressed: bool,
) -> None:
    """Only a worse-direction change beyond tolerance is a regression."""
    findings = compare_reports(
        _report({metric: current}),
        _report({metric: baseline}),
        _TOLERANCES,
    )

    assert bool(findings) is regressed


def test_lost_cases_statuses_and_metrics_are_regressions() -> None:
    """A case that disappears, fails or loses a metric is never ignored."""
    baseline = _report({"truth.completeness": 1.0})

    assert compare_reports({"cases": []}, baseline, _TOLERANCES)[0].reason == (
        "missing"
    )
    assert (
        compare_reports(_report({}, "failure"), baseline, _TOLERANCES)[
            0
        ].reason
        == "boom"
    )
    assert compare_reports(
        _report({"truth.completeness": None}), baseline, _TOLERANCES
    )[0].reason == ("no longer measurable")
    assert not compare_reports(
        _report({"truth.completeness": 1.0}),
        _report({"truth.completeness": None}),
        _TOLERANCES,
    )


def test_generated_case_is_materialised_once_with_truth(
    tmp_path: Path,
) -> None:
    """A generated input is cached and carries every injected source."""
    configuration = load_quick_check_configuration(_CONFIGURATION)
    case = next(
        case
        for case in configuration.cases
        if isinstance(case, GeneratedCase) and case.case_id == "close-blends"
    )

    first = prepare_case(
        case,
        configuration=configuration,
        repository_root=_ROOT,
        inputs_root=tmp_path,
    )
    modified = first.input_path.stat().st_mtime_ns
    second = prepare_case(
        case,
        configuration=configuration,
        repository_root=_ROOT,
        inputs_root=tmp_path,
    )

    assert first.truth is not None and len(first.truth) == 6
    assert second.input_path.stat().st_mtime_ns == modified
    assert second.input_sha256 == first.input_sha256
    assert first.reference_input_path == first.input_path


def _image_configuration(tmp_path: Path, case: dict[str, Any]) -> Any:
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    document["cases"] = [case]
    path = tmp_path / "configuration.json"
    path.write_text(json.dumps(document))
    return load_quick_check_configuration(path)


def _write_radio_image(path: Path, *, with_bpa: bool) -> None:
    header = fits.Header()
    header["BUNIT"] = "JY/BEAM"
    header["BMAJ"] = 0.002
    header["BMIN"] = 0.001
    if with_bpa:
        header["BPA"] = 10.0
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 5.0
    header["CRPIX2"] = 5.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = 50.0
    header["CDELT1"] = -0.0004
    header["CDELT2"] = 0.0004
    header["RADESYS"] = "ICRS"
    header["RESTFRQ"] = 144e6
    values = np.arange(100, dtype=np.float32).reshape(10, 10)
    fits.PrimaryHDU(values, header).writeto(path)


def test_image_case_crops_and_completes_the_reference_header(
    tmp_path: Path,
) -> None:
    """PyBDSF gets RESTFREQ and supplied BPA; Hebog keeps the original."""
    root = tmp_path / "repository"
    root.mkdir()
    _write_radio_image(root / "image.fits", with_bpa=False)
    configuration = _image_configuration(
        tmp_path,
        {
            "kind": "image",
            "case_id": "cropped",
            "image": "image.fits",
            "window": {"x_start": 2, "y_start": 3, "size": 4},
            "supplied_metadata": {"beam_position_angle_degrees": 0.0},
        },
    )

    prepared = prepare_case(
        configuration.cases[0],
        configuration=configuration,
        repository_root=root,
        inputs_root=tmp_path / "inputs",
    )

    with fits.open(prepared.input_path) as hdus:
        np.testing.assert_array_equal(
            hdus[0].data, np.arange(100).reshape(10, 10)[3:7, 2:6]
        )
        assert hdus[0].header["CRPIX1"] == 3.0
        assert "BPA" not in hdus[0].header
    reference = fits.getheader(prepared.reference_input_path)
    assert reference["BPA"] == 0.0
    assert reference["RESTFREQ"] == 144e6
    assert prepared.supplied_metadata is not None


def test_missing_remote_input_needs_explicit_download(tmp_path: Path) -> None:
    """Configured cut-outs are fetched only when downloads are allowed."""
    configuration = _image_configuration(
        tmp_path,
        {
            "kind": "image",
            "case_id": "remote",
            "image": "missing.fits",
            "remote_source": {
                "url": "https://example.invalid/image.fits",
                "window": {"x_start": 0, "y_start": 0, "size": 4},
            },
        },
    )

    with pytest.raises(FileNotFoundError, match="downloads allowed"):
        prepare_case(
            configuration.cases[0],
            configuration=configuration,
            repository_root=tmp_path,
            inputs_root=tmp_path / "inputs",
        )


def test_reports_are_never_replaced(tmp_path: Path) -> None:
    """A report is evidence for one run and cannot be overwritten."""
    path = tmp_path / "report.json"
    write_report(path, {"cases": []})

    with pytest.raises(FileExistsError):
        write_report(path, {"cases": []})


def test_public_catalogue_projects_sources_and_components() -> None:
    """Published rows keep identity, position, flux and position errors."""
    position = SkyPosition(
        right_ascension_degrees=180.25,
        declination_degrees=-30.5,
        right_ascension_error_degrees=0.0001,
        declination_error_degrees=None,
    )
    flux = FluxMeasurement(
        peak_flux_jy_per_beam=0.01,
        peak_flux_error_jy_per_beam=0.001,
        integrated_flux_jy=0.012,
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=0.0002,
    )
    shape = GaussianShape(
        major_fwhm_degrees=0.002,
        minor_fwhm_degrees=0.001,
        position_angle_degrees=45.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    spectrum = SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=150e6,
        coefficients=(),
    )
    common: dict[str, Any] = {
        "island_id": "island-1",
        "position": position,
        "flux": flux,
        "spectral_model": spectrum,
        "fitted_shape": shape,
        "deconvolved_shape": None,
        "quality_flags": (),
    }
    catalogue = SourceCatalogue.create(
        catalogue_id="catalogue",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=150e6,
        islands=(
            Island(
                island_id="island-1",
                pixel_count=9,
                integrated_flux_jy=0.012,
                integrated_flux_error_jy=None,
                local_rms_jy_per_beam=0.0002,
                mean_brightness_jy_per_beam=0.001,
            ),
        ),
        sources=(SourceCandidate(source_id="source-1", **common),),
        gaussian_components=(
            GaussianComponent(
                gaussian_component_id="component-1",
                source_id="source-1",
                **common,
            ),
        ),
    )

    (source,) = public_catalogue_sources(catalogue, level="sources")
    (component,) = public_catalogue_sources(catalogue, level="components")

    assert source.identifier == "source-1"
    assert component.identifier == "component-1"
    assert source.right_ascension_error_degrees == 0.0001
    assert source.declination_error_degrees is None
    assert component.integrated_flux_jy == 0.012
    assert component.fitted_shape is None


def test_cases_without_a_baseline_are_reported() -> None:
    """A new or renamed case cannot pass silently for lack of a baseline."""
    current = {
        "cases": [
            {"case_id": "case", "status": "success", "metrics": {}},
            {"case_id": "new-case", "status": "success", "metrics": {}},
        ]
    }

    findings = compare_reports(current, _report({}), _TOLERANCES)

    assert [(item.case_id, item.reason) for item in findings] == [
        ("new-case", "not in baseline")
    ]


def test_reference_cache_depends_on_the_reference_identity(
    tmp_path: Path,
) -> None:
    """A new image, finder option or core count never reuses a result."""
    identity: dict[str, object] = {
        "container_image_id": "sha256:" + "a" * 64,
        "finder_settings": {"thresh_pix": 5.0},
        "ncores": 4,
    }

    def directory(**changes: object) -> Path:
        return reference_cache_directory(
            tmp_path,
            case_id="case",
            reference_input_sha256="b" * 64,
            finder_id="pinned-pybdsf-master",
            identity={**identity, **changes},
        )

    assert directory() == directory()
    assert directory().parent == tmp_path / "case" / ("b" * 16)
    assert (
        len(
            {
                directory(),
                directory(container_image_id="sha256:" + "c" * 64),
                directory(finder_settings={"thresh_pix": 4.0}),
                directory(ncores=2),
            }
        )
        == 4
    )
