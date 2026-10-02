# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false
"""Configuration, inputs, metrics and regressions of the quick check."""

from __future__ import annotations

import importlib.metadata
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from astropy.table import Table
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
    SuppliedImageMetadata,
)
from hebog.science.models import CatalogueSource
from hebog.validation.quick_benchmark import (
    load_quick_benchmark_configuration,
)
from hebog.validation.quick_check import (
    REFERENCE_CODE,
    REFERENCE_CONTAINER_COMMAND,
    REFERENCE_WORKER,
    GeneratedCase,
    ImageCase,
    RegressionTolerances,
    compare_reports,
    load_quick_check_configuration,
    map_metrics,
    prepare_case,
    public_catalogue_sources,
    reference_cache_directory,
    reference_code_sha256,
    reference_identity,
    supplied_metadata_values,
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
    """The committed case set is valid and references known datasets.

    The quick benchmark shares the manifest, so every generated dataset in
    it must be a science-check case or a benchmark case: a dataset neither
    runs is dead weight, and a case naming an unknown dataset cannot run.
    """
    configuration = load_quick_check_configuration(_CONFIGURATION)
    manifest = json.loads(
        (_ROOT / configuration.dataset_manifest).read_text(encoding="utf-8")
    )
    dataset_ids = {item["identifier"] for item in manifest["datasets"]}
    benchmark = load_quick_benchmark_configuration(
        _ROOT / "config" / "benchmarks" / "quick-benchmark.json"
    )
    assert benchmark.dataset_manifest == configuration.dataset_manifest

    generated = [
        case for case in configuration.cases if isinstance(case, GeneratedCase)
    ]
    benchmark_generated = {
        item.case.dataset_id
        for item in benchmark.cases
        if isinstance(item.case, GeneratedCase)
    }
    assert {case.dataset_id for case in generated} <= dataset_ids
    assert {case.dataset_id for case in generated} | benchmark_generated == (
        dataset_ids
    )
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
        dataset_manifest=_ROOT / configuration.dataset_manifest,
        repository_root=_ROOT,
        inputs_root=tmp_path,
    )
    modified = first.input_path.stat().st_mtime_ns
    second = prepare_case(
        case,
        dataset_manifest=_ROOT / configuration.dataset_manifest,
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
        dataset_manifest=_ROOT / configuration.dataset_manifest,
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
    assert prepared.supplied_metadata == SuppliedImageMetadata(
        beam_position_angle_degrees=0.0
    )


@pytest.mark.parametrize(
    "supplied",
    [
        {"beam_position_angle_degrees": 0.0},
        {"brightness_unit": "Jy/beam", "reference_frequency_hz": 144e6},
    ],
)
def test_a_case_supplies_any_metadata_value_and_keeps_its_identity(
    supplied: dict[str, Any],
) -> None:
    """A manifest's supplied values, text or number, are one typed record.

    Case identities hash the dumped case, so it must carry exactly the
    values the manifest states and none of the record's unset fields.
    """
    case = ImageCase.model_validate(
        {
            "kind": "image",
            "case_id": "supplied",
            "image": "image.fits",
            "supplied_metadata": supplied,
        }
    )

    assert case.supplied_metadata == SuppliedImageMetadata(**supplied)
    assert case.model_dump(mode="json")["supplied_metadata"] == supplied
    assert supplied_metadata_values(case.supplied_metadata) == supplied
    assert supplied_metadata_values(None) is None


@pytest.mark.parametrize(
    ("supplied", "message"),
    [
        ({"beam_position_angel_degrees": 0.0}, "beam_position_angel_degrees"),
        ({"brightness_unit": " "}, "brightness unit"),
        ({"reference_frequency_hz": "high"}, "reference_frequency_hz"),
    ],
)
def test_a_case_with_unusable_supplied_metadata_fails_to_load(
    supplied: dict[str, Any], message: str
) -> None:
    """The manifest is checked by the record's own rules when it loads."""
    with pytest.raises(ValidationError, match=message):
        ImageCase.model_validate(
            {
                "kind": "image",
                "case_id": "supplied",
                "image": "image.fits",
                "supplied_metadata": supplied,
            }
        )


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
            dataset_manifest=_ROOT / configuration.dataset_manifest,
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


def _write_reference_checkout(root: Path) -> None:
    """Write a checkout whose worker imports ``hebog`` as the real one does.

    Importing the listed modules also runs the package's own imports and,
    through the catalogue records, imports an algorithm module.
    """
    files = {
        REFERENCE_WORKER: (
            "import hebog.validation.campaign_runtime\n"
            "import hebog.validation.products\n"
        ),
        Path("src/hebog/__init__.py"): (
            'from hebog import config\n__version__ = "0.17.0"\n'
        ),
        Path("src/hebog/config.py"): "VALUE = 1\n",
        Path("src/hebog/algorithms/__init__.py"): "",
        Path("src/hebog/algorithms/fitting.py"): "VALUE = 1\n",
        Path("src/hebog/science/__init__.py"): "",
        Path("src/hebog/science/models.py"): (
            "import hebog.algorithms.fitting\n"
        ),
        Path("src/hebog/validation/__init__.py"): "",
        Path("src/hebog/validation/campaign_runtime.py"): "VALUE = 1\n",
        Path("src/hebog/validation/products.py"): (
            "import hebog.science.models\n"
        ),
    }
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text)


def test_reference_code_identity_ignores_code_the_worker_does_not_run(
    tmp_path: Path,
) -> None:
    """Another checkout, a release or an algorithm change keeps references.

    The worker imports the whole package but runs only the listed code, so
    editing any listed file, and only those, selects a new reference.
    """
    main, worktree = tmp_path / "main", tmp_path / "worktree"
    _write_reference_checkout(main)
    _write_reference_checkout(worktree)
    first = reference_code_sha256(main)

    (worktree / "src/hebog/__init__.py").write_text(
        'from hebog import config\n__version__ = "0.18.0"\n'
    )
    for unrun in ("src/hebog/config.py", "src/hebog/algorithms/fitting.py"):
        (worktree / unrun).write_text("VALUE = 2\n")
    assert reference_code_sha256(worktree) == first

    digests = {first}
    for relative in REFERENCE_CODE:
        with (worktree / relative).open("a", encoding="utf-8") as handle:
            handle.write("# edited\n")
        digests.add(reference_code_sha256(worktree))
    assert len(digests) == len(REFERENCE_CODE) + 1


def test_reference_code_identity_needs_a_worker_that_imports(
    tmp_path: Path,
) -> None:
    """A worker that cannot import fails before any reference runs.

    In the container the failure would be cached under an identity that
    fixing the broken, unhashed module does not change.
    """
    _write_reference_checkout(tmp_path)
    (tmp_path / "src/hebog/algorithms/fitting.py").write_text(
        "raise ImportError('broken')\n"
    )

    with pytest.raises(subprocess.CalledProcessError):
        reference_code_sha256(tmp_path)


_PYBDSF_COLUMNS = (
    "Gaus_id",
    "Isl_id",
    "Source_id",
    "Wave_id",
    "RA",
    "E_RA",
    "DEC",
    "E_DEC",
    "Total_flux",
    "E_Total_flux",
    "Peak_flux",
    "E_Peak_flux",
    "Maj",
    "E_Maj",
    "Min",
    "E_Min",
    "PA",
    "E_PA",
    "DC_Maj",
    "E_DC_Maj",
    "DC_Min",
    "E_DC_Min",
    "DC_PA",
    "E_DC_PA",
)


class _OneIslandPyBDSFImage:
    """Stands in for PyBDSF's image: one resolved source in one island."""

    def __init__(self, labels_yx: npt.NDArray[np.int32]) -> None:
        self.labels_yx = labels_yx
        self.pyrank = (labels_yx - 1).T

    def write_catalog(self, *, outfile: str, **_options: object) -> None:
        """Write the source or Gaussian list; one row serves as both."""
        row = (0, 0, 0, 0, 10.0, 1e-5, 50.0, 1e-5, 0.02, 1e-3, 0.01, 1e-3)
        shapes = (3e-3, 1e-4, 2e-3, 1e-4, 20.0, 2.0)
        deconvolved = (2e-3, 1e-4, 1e-3, 1e-4, 20.0, 2.0)
        Table(rows=[row + shapes + deconvolved], names=_PYBDSF_COLUMNS).write(
            outfile
        )

    def export_image(
        self, *, outfile: str, img_type: str, **_options: object
    ) -> bool:
        """Write the island mask or a flat RMS map."""
        plane = (
            self.labels_yx > 0
            if img_type == "island_mask"
            else np.ones(self.labels_yx.shape)
        )
        fits.PrimaryHDU(plane.astype(np.float32)).writeto(outfile)
        return True


def test_reference_code_is_exactly_the_code_the_worker_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity hashes every repository file a PyBDSF reference runs.

    A profile hook records the files whose functions the worker calls while
    it reads, checks and normalises PyBDSF's products. A module the worker
    starts to use, or a listed one it stops using, fails here until the list
    follows.
    """
    worker = runpy.run_path(str(_ROOT / REFERENCE_WORKER))
    settings = worker["reference_settings"]()["pinned-pybdsf-master"]

    def installed_version(_package: str) -> str:
        return str(settings["version"])

    labels = np.zeros((10, 10), dtype=np.int32)
    labels[4:6, 5:7] = 1

    def process_image(
        *_arguments: object, **_options: object
    ) -> _OneIslandPyBDSFImage:
        return _OneIslandPyBDSFImage(labels)

    bdsf = ModuleType("bdsf")
    bdsf.process_image = process_image
    monkeypatch.setitem(sys.modules, "bdsf", bdsf)
    monkeypatch.setattr(importlib.metadata, "version", installed_version)
    image = tmp_path / "input.fits"
    _write_radio_image(image, with_bpa=True)
    called: set[str] = set()

    def record(frame: FrameType, event: str, _argument: object) -> None:
        if event == "call":
            called.add(frame.f_code.co_filename)

    previous = sys.getprofile()
    sys.setprofile(record)
    try:
        worker["run_reference"](
            image=image,
            output=tmp_path / "reference",
            case_id="case",
            finder="pinned-pybdsf-master",
            container_image_id="image",
            ncores=1,
        )
    finally:
        sys.setprofile(previous)

    root = _ROOT.resolve()
    ran = {
        path.relative_to(root).as_posix()
        for path in (Path(name).resolve() for name in called)
        if path.is_relative_to(root / "src")
        or path.is_relative_to(root / "scripts")
    }
    assert ran == {path.as_posix() for path in REFERENCE_CODE}


@pytest.mark.skipif(sys.platform == "win32", reason="uses a shell script")
def test_reference_identity_names_image_settings_cores_and_code(
    tmp_path: Path,
) -> None:
    """The identity changes with the image ID and with the reference code."""
    for relative in (*REFERENCE_CODE, REFERENCE_CONTAINER_COMMAND):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("VALUE = 1\n")
    settings = tmp_path / "config/comparisons/notebook-comparison.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"reference_finders": {"pinned-pybdsf-master": {"a": 1}}})
    )
    engine = tmp_path / "engine"
    engine.write_text("#!/bin/sh\necho image-one\n")
    engine.chmod(0o755)
    reference = load_quick_check_configuration(_CONFIGURATION).reference

    def identity() -> dict[str, object]:
        return reference_identity(
            reference, engine=str(engine), repository_root=tmp_path
        )

    first = identity()
    assert first["container_image_id"] == "image-one"
    assert first["finder_settings"] == {"a": 1}
    assert first["ncores"] == reference.ncores
    (tmp_path / REFERENCE_WORKER).write_text("VALUE = 2\n")
    assert (
        identity()["reference_code_sha256"] != first["reference_code_sha256"]
    )
    engine.write_text("#!/bin/sh\necho image-two\n")
    assert identity()["container_image_id"] == "image-two"
