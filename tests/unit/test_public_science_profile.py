"""Tests for the immutable scientific profile shipped in the wheel."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from importlib.resources import files
from math import prod
from pathlib import Path
from typing import cast

import pytest
from astropy.io import fits
from astropy.wcs import WCS
from hypothesis import example, given, settings
from hypothesis import strategies as st

import hebog
from hebog import public_api
from hebog.algorithms.background import plan_rms_grid
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.data_models import (
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
    WideObjectCounts,
)
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.pipeline import (
    SourceFinderError,
    SourceFinderImageTooLargeError,
    UnsupportedSourceFinderConfigurationError,
)
from hebog.science.configuration import source_finder_configs
from hebog.stages import background as background_stage
from hebog.stages import composition

_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("shape", "window", "step"),
    [
        ((149, 512), 150, 50),
        ((150, 512), 37, 12),
        ((384, 512), 96, 32),
        ((512, 384), 96, 32),
        ((599, 800), 149, 49),
        ((600, 800), 150, 50),
        ((1024, 1024), 150, 50),
    ],
)
def test_public_background_mesh_is_bounded_by_image_capacity(
    shape: tuple[int, int], window: int, step: int
) -> None:
    """Only intermediate images need a smaller spatial coarse mesh."""
    original = source_finder_configs()[0].background_rms
    repaired = composition._public_background_config(
        shape, original, source_finder=SourceFinderConfig(5.0, 3.0, 7)
    )
    assert repaired.coarse.window_shape_yx == (window, window)
    assert repaired.coarse.step_yx == (step, step)
    assert repaired.adaptive == original.adaptive
    assert repaired.coarse.statistics == original.coarse.statistics
    assert (
        repaired.maximum_constant_map_pixels
        == original.maximum_constant_map_pixels
    )
    assert original.coarse.window_shape_yx == (150, 150)


def test_repaired_science_cannot_inherit_reference_qualification() -> None:
    """Matching old thresholds is not qualification of a changed finder."""
    assert (
        public_api._configuration_qualification(
            SourceFinderConfig(5.0, 3.0, 7)
        )
        == "development-unqualified"
    )
    assert public_api._COMPOSITION_NAME == (
        "phase-5-evidence-bound-public-catalogue-v22"
    )
    assert {
        "hebog.algorithms.component_measurement",
        "hebog.algorithms.fitting",
        "hebog.algorithms.deblending",
        "hebog.data_models.measurement_diagnostics",
        "hebog.algorithms.multiscale_tiles",
        "hebog.stages.multiscale",
    } <= set(public_api._SCIENTIFIC_MODULES)


_PACKAGE_ROOT = Path(hebog.__file__).parent


def _source_file(module_name: str) -> Path | None:
    """Return a Hebog module's source file, or None for a name in a module."""
    path = _PACKAGE_ROOT.joinpath(*module_name.split(".")[1:])
    if (path / "__init__.py").is_file():
        return path / "__init__.py"
    module = path.parent / f"{path.name}.py"
    return module if module.is_file() else None


def _imported_names(source_file: Path) -> Iterator[str]:
    """Yield every dotted name one source file imports, wherever it does.

    Imports inside functions and under ``TYPE_CHECKING`` count too: a
    function-level import runs when the finder calls the function, and
    including the rest only binds more.
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import in {source_file}"
            assert node.module is not None, source_file
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def _import_closure(module_name: str) -> set[str]:
    """Return every Hebog module that running one module can execute.

    A package's ``__init__`` runs before any of its submodules, so each
    imported module brings its parent packages with it.
    """
    closure: set[str] = set()
    pending = [module_name]
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure.add(name)
        source_file = _source_file(name)
        assert source_file is not None, name
        for imported in _imported_names(source_file):
            parts = imported.split(".")
            if parts[0] == "hebog" and _source_file(imported) is not None:
                pending.extend(
                    ".".join(parts[:end]) for end in range(1, len(parts) + 1)
                )
    return closure


def test_composition_fingerprint_binds_the_configuration_and_fft_kernels() -> (
    None
):
    """A changed stage default or FFT kernel must change the fingerprint.

    The 4 October review found both imported by the finder and missing from
    the fingerprint, so a run with changed defaults kept the old identity.
    """
    assert {"hebog.config", "hebog.algorithms.fft"} <= set(
        public_api._SCIENTIFIC_MODULES
    )


def test_composition_fingerprint_binds_the_finders_whole_import_closure() -> (
    None
):
    """Every module the finder imports is bound unless it is named exempt.

    The expectation is the import closure itself, so a module the finder
    starts to import changes the fingerprint, or fails here until it is bound
    or exempted with a reason.
    """
    closure = _import_closure("hebog.public_api")

    assert set(public_api._SCIENTIFIC_MODULES) == closure - set(
        public_api._UNBOUND_MODULES
    )
    assert list(public_api._SCIENTIFIC_MODULES) == sorted(
        set(public_api._SCIENTIFIC_MODULES)
    )


@pytest.mark.parametrize("module_name", sorted(public_api._UNBOUND_MODULES))
def test_every_module_left_out_of_the_fingerprint_is_still_imported(
    module_name: str,
) -> None:
    """An exemption that stops matching must fail, not quietly widen.

    A stale entry would exempt nothing while looking deliberate, and an entry
    that someone has since bound would hide that the rule changed.
    """
    assert module_name in _import_closure("hebog.public_api")
    assert module_name not in public_api._SCIENTIFIC_MODULES
    assert public_api._UNBOUND_MODULES[module_name].strip()


def _composition_sha256() -> str:
    """Compute the fingerprint afresh, bypassing the process-wide cache."""
    return public_api._scientific_composition_sha256.__wrapped__()


def test_composition_fingerprint_binds_every_packaged_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed or added resource file changes the fingerprint, at any depth.

    The reviewed profile decides results as much as the code does, and the
    quick check and notebook runner record only this fingerprint.
    """
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "profile.json").write_text("{}", encoding="utf-8")
    (resources / "__pycache__").mkdir()

    def packaged(_package: str) -> Path:
        return resources

    monkeypatch.setattr(public_api, "files", packaged)
    original = _composition_sha256()

    (resources / "__pycache__" / "profile.cpython.pyc").write_bytes(b"cache")
    unchanged = _composition_sha256()
    (resources / "profile.json").write_text('{"a": 1}', encoding="utf-8")
    changed = _composition_sha256()
    (resources / "profile.json").write_text("{}", encoding="utf-8")
    (resources / "extra.json").write_text("{}", encoding="utf-8")
    added = _composition_sha256()
    (resources / "extra.json").unlink()
    (resources / "tables").mkdir()
    (resources / "tables" / "beam.json").write_text("{}", encoding="utf-8")
    nested = _composition_sha256()

    assert unchanged == original
    assert len({original, changed, added, nested}) == 4


def test_a_module_that_cannot_be_located_stops_the_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bound module missing from the installation is not skipped."""
    monkeypatch.setattr(
        public_api,
        "_SCIENTIFIC_MODULES",
        ("hebog.config", "hebog.not_installed"),
    )

    with pytest.raises(
        SourceFinderError,
        match=r"cannot identify scientific module hebog\.not_installed",
    ):
        _composition_sha256()


def test_composition_fingerprint_reads_modules_without_importing_them() -> (
    None
):
    """Hashing locates sources, so the optional Dask executor stays unloaded.

    The fingerprint binds ``hebog.executors.dask``, which the finder reaches
    only when a caller asks for it, and computing the fingerprint must not
    import it or its scheduler.
    """
    script = (
        "import sys\n"
        "from hebog import public_api\n"
        "public_api._scientific_composition_sha256()\n"
        "print(sorted(name for name in sys.modules\n"
        "    if name.split('.')[0] in {'hebog', 'distributed'}))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    loaded = set(ast.literal_eval(completed.stdout))

    assert "hebog.executors.dask" in public_api._SCIENTIFIC_MODULES
    assert "hebog.executors.dask" not in loaded
    assert "distributed" not in loaded
    assert "hebog.public_science" not in loaded


def test_intermediate_mesh_cannot_bypass_the_bounded_read_admission() -> None:
    """A skinny, very long image cannot introduce an unbounded mask read."""
    original = source_finder_configs()[0].background_rms
    with pytest.raises(ValueError, match="bounded image admission"):
        composition._public_background_config(
            (150, 10_000),
            original,
            source_finder=SourceFinderConfig(5.0, 3.0, 7),
        )


def _stages_refuse(shape_yx: tuple[int, int], profile: str) -> bool:
    """Return whether the background stage would refuse this image shape."""
    background = source_finder_configs()[0].background_rms
    if profile == "continuum":
        try:
            background = composition._public_background_config(
                shape_yx,
                background,
                source_finder=SourceFinderConfig(5.0, 3.0, 7),
            )
        except ValueError:
            return True
    return (
        background_stage._use_constant_map(shape_yx, background)
        and prod(shape_yx) > background.maximum_constant_map_pixels
    )


@given(
    height=st.integers(min_value=1, max_value=15_402),
    width=st.integers(min_value=1, max_value=15_402),
)
@example(height=149, width=6_711)
@example(height=149, width=6_712)
@example(height=150, width=6_666)
@example(height=150, width=6_667)
@example(height=599, width=1_669)
@example(height=599, width=1_670)
@example(height=600, width=15_402)
@example(height=1_000, width=1_000)
@example(height=2_600, width=400)
def test_the_narrow_image_rule_refuses_exactly_what_the_stages_would(
    height: int, width: int
) -> None:
    """The public rule is decided before the analysis, and is the same rule.

    Each profile reaches its own bounded-read check in the background
    stage, after work has begun; the public boundary states one rule that
    refuses the same shapes for both.
    """
    shape_yx = (height, width)
    try:
        public_api._require_bounded_shape(shape_yx)
    except SourceFinderImageTooLargeError:
        refused = True
    else:
        refused = False

    assert _stages_refuse(shape_yx, "continuum") == refused
    assert _stages_refuse(shape_yx, "compact") == refused


def _largest_local_noise_read(
    shape_yx: tuple[int, int], beam_fwhm_pixels: float
) -> int:
    """Return the most pixels one local-noise task reads for this beam."""
    background = source_finder_configs()[0].background_rms
    assert background.adaptive is not None
    fine = background.adaptive.grid
    grid = plan_rms_grid(
        image_shape_yx=shape_yx,
        window_shape_yx=fine.window_shape_yx,
        step_yx=fine.step_yx,
    )
    policy = background_stage.MultiscaleSourceProtection(
        BeamShapePixels(beam_fwhm_pixels, beam_fwhm_pixels, 0.0),
        SourceFinderConfig(5.0, 3.0, 7),
        0.5,
    )
    return max(
        prod(bounds.shape_yx)
        for _, _, bounds in background_stage._local_noise_contexts(
            grid, background, policy
        )
    )


@settings(deadline=None, max_examples=60)
@given(
    height=st.integers(min_value=150, max_value=15_402),
    width=st.integers(min_value=150, max_value=15_402),
)
@example(height=1_017, width=1_017)
@example(height=1_020, width=1_020)
@example(height=150, width=6_666)
@example(height=599, width=1_669)
@example(height=15_402, width=15_402)
def test_the_widest_admitted_beam_fits_the_local_noise_read_on_any_image(
    height: int, width: int
) -> None:
    """Every admitted beam keeps the stage's bounded local-noise read.

    Refinement reads a block of noise cells with the widest protection
    filter around it and refuses a read above its bound, after work has
    begun. The read grows with the beam, so the widest admitted beam is the
    case to check, on every shape the narrow-image rule admits. The beam
    limit is set by recovery on injected sources, not by this bound, which
    leaves a margin: this test fails if the limit is ever raised past it.
    """
    shape_yx = (height, width)
    try:
        public_api._require_bounded_shape(shape_yx)
    except SourceFinderImageTooLargeError:
        return
    background = source_finder_configs()[0].background_rms

    assert (
        _largest_local_noise_read(
            shape_yx, public_api._MAXIMUM_BEAM_FWHM_PIXELS
        )
        <= background.maximum_constant_map_pixels
    )


@pytest.mark.parametrize("shape", ((149, 512), (150, 512), (1024, 1024)))
@pytest.mark.parametrize(
    ("detection", "island", "expected_trigger"),
    (
        (5.0, 3.0, 75.0),
        (100.0, 3.0, 75.0),
        (100.0, 74.0, 75.0),
        (100.0, 75.0, 100.0),
        (100.0, 80.0, 100.0),
        (75.00000000000001, 75.0, 75.00000000000001),
        (sys.float_info.max, sys.float_info.max / 2, sys.float_info.max),
    ),
)
def test_private_background_trigger_respects_custom_island_threshold(
    shape: tuple[int, int],
    detection: float,
    island: float,
    expected_trigger: float,
) -> None:
    """Refinement seeds must belong to support grown at caller thresholds."""
    original = source_finder_configs()[0].background_rms
    caller = SourceFinderConfig(detection, island, 7)
    repaired = composition._public_background_config(
        shape, original, source_finder=caller
    )

    assert original.adaptive is not None
    assert repaired.adaptive is not None
    assert repaired.adaptive.candidate_threshold_sigma == expected_trigger
    assert repaired.adaptive.candidate_threshold_sigma > island
    assert (
        replace(repaired.adaptive, candidate_threshold_sigma=75.0)
        == original.adaptive
    )
    assert original.adaptive.candidate_threshold_sigma == 75.0
    assert caller == SourceFinderConfig(detection, island, 7)


@pytest.mark.parametrize("shape", ((149, 512), (150, 512)))
def test_custom_threshold_does_not_enable_disabled_adaptive_background(
    shape: tuple[int, int],
) -> None:
    """Threshold reconciliation cannot invent an absent refinement policy."""
    original = replace(
        source_finder_configs()[0].background_rms,
        adaptive=None,
    )
    repaired = composition._public_background_config(
        shape, original, source_finder=SourceFinderConfig(100.0, 80.0, 7)
    )
    assert repaired.adaptive is None
    assert original.adaptive is None


def _centred_metadata(
    *,
    projection: str,
    reference_sky_degrees: tuple[float, float],
    pixel_scale_arcsec: float,
    beam_pixels: float,
) -> ImageMetadata:
    """Return 256² ICRS metadata whose reference pixel is the image centre.

    The local scale there is the pixel scale, so a beam a whole number of
    pixels wide is exactly that wide in pixels. The header text is what
    FITS ingress keeps.
    """
    scale = pixel_scale_arcsec / 3600.0
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = [f"RA---{projection}", f"DEC--{projection}"]
    wcs.wcs.crpix = [128.5, 128.5]
    wcs.wcs.crval = reference_sky_degrees
    wcs.wcs.cdelt = [-scale, scale]
    wcs.wcs.radesys = "ICRS"
    header = cast(fits.Header, wcs.to_header(relax=True))
    return ImageMetadata(
        shape_yx=(256, 256),
        unit="Jy/beam",
        beam=RestoringBeam(beam_pixels * scale, beam_pixels * scale, 0.0),
        celestial_wcs=CelestialWcs(
            fits_header=header.tostring(
                sep="\n", endcard=False, padding=False
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150e6,
    )


@pytest.mark.parametrize("beam_pixels", (3.0, 4.0, 10.0, 22.0))
@pytest.mark.parametrize(
    ("projection", "reference_sky_degrees", "pixel_scale_arcsec"),
    (
        # The beam-sampling study's geometry, where a 1e-3 pixel Jacobian
        # step read 10 pixels as 10.000000508 on Linux.
        ("SIN", (180.0, 45.0), 1.5),
        ("SIN", (359.9, 60.0), 0.1),
        ("TAN", (250.0, 85.0), 60.0),
    ),
)
def test_a_whole_pixel_beam_is_exactly_whole_in_pixels(
    projection: str,
    reference_sky_degrees: tuple[float, float],
    pixel_scale_arcsec: float,
    beam_pixels: float,
) -> None:
    """Given a beam N pixels wide where the scale is the pixel scale,
    when the finder derives its beam in pixels,
    then both axes are exactly N, on every platform.

    ``ceil(1.5 * N)`` sets the segment-row aperture radius and
    ``ceil(0.5 * N)`` the recovery radius and the halos; both land on an
    integer for an even N, so an axis rounded to N plus 1e-6 on one
    platform would publish from a different aperture and halo.
    """
    beam = public_api._beam_shape_pixels(
        _centred_metadata(
            projection=projection,
            reference_sky_degrees=reference_sky_degrees,
            pixel_scale_arcsec=pixel_scale_arcsec,
            beam_pixels=beam_pixels,
        )
    )

    assert (
        beam.major_fwhm_pixels,
        beam.minor_fwhm_pixels,
        beam.position_angle_degrees,
    ) == (beam_pixels, beam_pixels, 0.0)


def test_a_pixel_scale_that_underflows_is_refused_before_analysis() -> None:
    """A beam with no finite size in pixels is refused, as the rule says."""
    metadata = _centred_metadata(
        projection="SIN",
        reference_sky_degrees=(180.0, 45.0),
        pixel_scale_arcsec=1e-300,
        beam_pixels=4.0,
    )

    with pytest.raises(
        UnsupportedSourceFinderConfigurationError,
        match="no finite size in pixels",
    ):
        public_api._require_sampled_beam(metadata)


def _provenance() -> PublicSourceFindingProvenance:
    """Return one exact public provenance fixture."""
    return PublicSourceFindingProvenance(
        input_sha256="1" * 64,
        configuration_sha256="2" * 64,
        scientific_profile_sha256="3" * 64,
        scientific_composition_sha256="4" * 64,
        scientific_composition=("phase-5-evidence-bound-public-catalogue-v22"),
    )


def test_profile_matches_reviewed_repository_record() -> None:
    """The wheel cannot silently drift from the reviewed science profile."""
    installed = (
        files("hebog.resources")
        .joinpath("reviewed_continuum_profile.json")
        .read_bytes()
    )
    reviewed = (
        _ROOT / "config/contracts/phase-5-corrective-a-review.json"
    ).read_bytes()

    assert installed == reviewed
    assert hashlib.sha256(installed).hexdigest() == (
        "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
    )


def test_public_diagnostics_round_trip_exact_provenance() -> None:
    """Public diagnostics preserve profile limitations and exact identities."""
    diagnostics = PublicSourceFindingDiagnostics(
        run_id="public-test",
        profile="compact",
        profile_limitations=("extended-emission-incomplete",),
        configuration_qualification="development-unqualified",
        source_count=1,
        gaussian_component_count=1,
        island_count=1,
        deblended_parent_count=1,
        deferred_deblend_parent_count=0,
        measurement_dispositions=_dispositions(),
        rms_scientific_status="valid",
        provenance=_provenance(),
    )

    assert (
        PublicSourceFindingDiagnostics.from_json_bytes(
            diagnostics.canonical_json_bytes()
        )
        == diagnostics
    )
    assert diagnostics.schema_version == 12
    assert diagnostics.deblended_parent_count == 1
    assert diagnostics.deferred_deblend_parent_count == 0


def _dispositions() -> tuple[MeasurementDisposition, ...]:
    """A single measured component with one public singleton source."""
    component = MeasurementDisposition(
        object_kind="component",
        object_id="component-one",
        status="measured",
        estimator="original-pixel-gaussian-model",
        reason=None,
        catalogue_row_published=True,
    )
    return (
        component,
        component.model_copy(
            update={
                "object_kind": "source",
                "object_id": "source-one",
                "member_component_ids": (component.object_id,),
            }
        ),
    )


@pytest.mark.parametrize("defect", ("missing", "duplicate", "member", "count"))
def test_public_diagnostics_require_a_complete_measurement_census(
    defect: str,
) -> None:
    """Published counts and retained identities must not silently diverge."""
    entries = _dispositions()
    if defect == "missing":
        entries = ()
    elif defect == "duplicate":
        entries = (*entries, entries[0])
    elif defect == "member":
        entries = (
            entries[0],
            entries[1].model_copy(
                update={
                    "member_component_ids": ("not-a-component",),
                }
            ),
        )
    with pytest.raises(ValueError, match="measurement census"):
        PublicSourceFindingDiagnostics(
            run_id="census",
            profile="continuum",
            profile_limitations=(),
            configuration_qualification="custom-unqualified",
            source_count=2 if defect == "count" else 1,
            gaussian_component_count=1,
            island_count=1,
            measurement_dispositions=entries,
            rms_scientific_status="valid",
            provenance=_provenance(),
        )


def test_public_provenance_rejects_non_sha_identity() -> None:
    """Public evidence cannot carry a truncated implementation identity."""
    document = _provenance().model_dump()
    document["scientific_composition_sha256"] = "1234"

    with pytest.raises(ValueError, match="must be SHA-256"):
        PublicSourceFindingProvenance.model_validate(document)


@pytest.mark.parametrize(
    ("run_id", "profile", "limitations", "message"),
    [
        ("", "continuum", (), "run ID"),
        (
            "public-test",
            "continuum",
            ("extended-emission-incomplete",),
            "limitations",
        ),
    ],
)
def test_public_diagnostics_reject_inconsistent_identity_and_profile(
    run_id: str,
    profile: str,
    limitations: tuple[str, ...],
    message: str,
) -> None:
    """A public diagnostic cannot overstate its profile or omit its run."""
    with pytest.raises(ValueError, match=message):
        PublicSourceFindingDiagnostics.model_validate(
            {
                "run_id": run_id,
                "profile": profile,
                "profile_limitations": limitations,
                "configuration_qualification": "development-unqualified",
                "source_count": 0,
                "gaussian_component_count": 0,
                "island_count": 0,
                "rms_scientific_status": "unavailable",
                "provenance": _provenance().model_dump(),
            }
        )


def test_public_diagnostics_reject_noncanonical_json() -> None:
    """Whitespace drift cannot masquerade as canonical public evidence."""
    diagnostics = PublicSourceFindingDiagnostics(
        run_id="public-test",
        profile="continuum",
        profile_limitations=(),
        configuration_qualification="custom-unqualified",
        source_count=0,
        gaussian_component_count=0,
        island_count=0,
        rms_scientific_status="unavailable",
        provenance=_provenance(),
    )

    with pytest.raises(ValueError, match="must be canonical"):
        PublicSourceFindingDiagnostics.from_json_bytes(
            diagnostics.canonical_json_bytes() + b" "
        )


def test_public_diagnostics_reject_negative_deblend_disposition() -> None:
    """Bounded deblend deferral cannot be hidden in invalid telemetry."""
    with pytest.raises(ValueError, match="deblend disposition"):
        PublicSourceFindingDiagnostics(
            run_id="public-test",
            profile="continuum",
            profile_limitations=(),
            configuration_qualification="development-unqualified",
            source_count=1,
            gaussian_component_count=1,
            island_count=1,
            deblended_parent_count=0,
            deferred_deblend_parent_count=-1,
            rms_scientific_status="valid",
            provenance=_provenance(),
        )


def test_wide_object_counts_default_to_zero_and_reject_negatives() -> None:
    """Every round's wide-object count is zero unless an object was wide."""
    assert WideObjectCounts() == WideObjectCounts(
        publication_owners=0,
        support_components=0,
        deferred_fit_parents=0,
        islands=0,
        segments=0,
    )
    with pytest.raises(ValueError, match="negative"):
        WideObjectCounts(segments=-1)
