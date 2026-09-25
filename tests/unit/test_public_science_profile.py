"""Tests for the immutable scientific profile shipped in the wheel."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import pytest

from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.data_models import (
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
)
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.science.configuration import source_finder_configs

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
    repaired = public_api._public_background_config(
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


# Tiling geometry is deliberately outside the fingerprint: every result is
# required to be partition-invariant, and that contract is tested on its own,
# so planning a different partition must not read as a scientific change.
_UNBOUND_BY_DESIGN = frozenset({"hebog.algorithms.partitioning"})


def _module_source(module_name: str) -> str:
    """Return one installed module's source without importing it."""
    specification = importlib.util.find_spec(module_name)
    assert specification is not None, module_name
    assert specification.origin is not None, module_name
    return Path(specification.origin).read_text(encoding="utf-8")


def _imported_submodules(source: str, package: str) -> set[str]:
    """Return the ``hebog.<package>`` submodules one source file imports."""
    return {
        f"hebog.{package}.{match.group(1)}"
        for match in re.finditer(
            rf"from hebog\.{package}\.(\w+) import", source
        )
    }


def _bound(package: str) -> set[str]:
    """Return the fingerprint's modules from one package."""
    prefix = f"hebog.{package}."
    return {
        name
        for name in public_api._SCIENTIFIC_MODULES
        if name.startswith(prefix)
    }


def test_composition_fingerprint_binds_every_stage_the_public_path_runs() -> (
    None
):
    """A stage the public path imports must reach the recorded fingerprint.

    The fingerprint identifies the implementation that produced a result, so a
    scientific change in any stage the public path runs has to change it. The
    expectation is derived from the imports themselves, so adding a stage
    without binding it fails here instead of silently reusing a digest.
    """
    imported = _imported_submodules(
        _module_source("hebog.public_api"), "stages"
    )

    assert imported, "no stage import was found to derive the expectation from"
    assert imported == _bound("stages")


def test_composition_fingerprint_binds_the_algorithms_those_stages_reach() -> (
    None
):
    """An algorithm is no less scientific for being reached through a stage.

    Binding only what the driver imports directly leaves a kernel that decides
    fitting windows or ownership unbound as soon as a stage, rather than the
    driver, is the one that calls it. The expectation therefore follows the
    imports one level in, through every bound stage and science module.
    """
    reached: set[str] = set()
    sources = ["hebog.public_api", *_bound("stages"), *_bound("science")]
    for module_name in sources:
        reached |= _imported_submodules(
            _module_source(module_name), "algorithms"
        )

    assert reached, "no algorithm import was found to derive from"
    assert reached - _UNBOUND_BY_DESIGN <= _bound("algorithms")


def test_every_algorithm_left_out_of_the_fingerprint_is_still_left_out() -> (
    None
):
    """An exemption that stops matching must fail, not quietly widen.

    A stale entry here would exempt nothing while looking deliberate, and an
    entry that someone has since bound would hide that the rule changed.
    """
    reached: set[str] = set()
    sources = ["hebog.public_api", *_bound("stages"), *_bound("science")]
    for module_name in sources:
        reached |= _imported_submodules(
            _module_source(module_name), "algorithms"
        )

    for module_name in _UNBOUND_BY_DESIGN:
        assert module_name in reached, f"{module_name} is no longer imported"
        assert module_name not in _bound("algorithms"), (
            f"{module_name} is bound now, so its exemption is obsolete"
        )


def test_intermediate_mesh_cannot_bypass_the_bounded_read_admission() -> None:
    """A skinny, very long image cannot introduce an unbounded mask read."""
    original = source_finder_configs()[0].background_rms
    with pytest.raises(ValueError, match="bounded image admission"):
        public_api._public_background_config(
            (150, 10_000),
            original,
            source_finder=SourceFinderConfig(5.0, 3.0, 7),
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
    repaired = public_api._public_background_config(
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
    repaired = public_api._public_background_config(
        shape, original, source_finder=SourceFinderConfig(100.0, 80.0, 7)
    )
    assert repaired.adaptive is None
    assert original.adaptive is None


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
    assert diagnostics.schema_version == 9
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
