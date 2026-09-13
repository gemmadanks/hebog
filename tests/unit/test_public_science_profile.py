"""Tests for the immutable scientific profile shipped in the wheel."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
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
    from hebog.validation.hebog_campaign import (  # noqa: PLC0415
        phase_five_corrected_candidate_configs,
    )

    original = phase_five_corrected_candidate_configs()[0].background_rms
    repaired = public_api._public_background_config(shape, original)
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
        "phase-5-evidence-bound-public-catalogue-v16"
    )
    assert {
        "hebog.algorithms.component_measurement",
        "hebog.algorithms.fitting",
        "hebog.algorithms.deblending",
        "hebog.data_models.measurement_diagnostics",
    } <= set(public_api._SCIENTIFIC_MODULES)


def test_intermediate_mesh_cannot_bypass_the_bounded_read_admission() -> None:
    """A skinny, very long image cannot introduce an unbounded mask read."""
    from hebog.validation.hebog_campaign import (  # noqa: PLC0415
        phase_five_corrected_candidate_configs,
    )

    original = phase_five_corrected_candidate_configs()[0].background_rms
    with pytest.raises(ValueError, match="bounded image admission"):
        public_api._public_background_config((150, 10_000), original)


def _provenance() -> PublicSourceFindingProvenance:
    """Return one exact public provenance fixture."""
    return PublicSourceFindingProvenance(
        input_sha256="1" * 64,
        configuration_sha256="2" * 64,
        scientific_profile_sha256="3" * 64,
        scientific_composition_sha256="4" * 64,
        scientific_composition=("phase-5-evidence-bound-public-catalogue-v16"),
    )


def test_profile_matches_reviewed_repository_record() -> None:
    """The wheel cannot silently drift from the reviewed science profile."""
    installed = (
        files("hebog.resources")
        .joinpath("phase_5_continuum_review.json")
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
    assert diagnostics.schema_version == 8
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


def test_public_interface_identity_binds_its_historical_file_set() -> None:
    """An immutable interface review remains verifiable after later science."""
    relative_review = Path(
        "config/contracts/"
        "phase-5-configurable-public-interface-identity-review.json"
    )
    review = json.loads((_ROOT / relative_review).read_text(encoding="utf-8"))
    creation_revision = subprocess.run(
        (
            "git",
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--",
            str(relative_review),
        ),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]

    def historical_bytes(relative_path: str) -> bytes:
        return subprocess.run(
            ("git", "show", f"{creation_revision}:{relative_path}"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout

    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    for relative_path, expected in review["interface_file_sha256"].items():
        assert hashlib.sha256(historical_bytes(relative_path)).hexdigest() == (
            expected
        )
    composition = hashlib.sha256()
    for module_name, expected in review["scientific_module_sha256"].items():
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").relative_to(_ROOT)
        contents = historical_bytes(str(module_path))
        assert hashlib.sha256(contents).hexdigest() == expected
        composition.update(module_name.encode())
        composition.update(b"\0")
        composition.update(contents)
        composition.update(b"\0")

    assert composition.hexdigest() == review["scientific_composition_sha256"]


def test_source_protected_public_identity_binds_historical_science() -> None:
    """The superseded review remains bound to its exact candidate commit."""
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-adaptive-background-source-protection-"
        "public-interface-identity-review.json"
    )
    contents = review_path.read_bytes()
    review = json.loads(contents)

    assert hashlib.sha256(contents).hexdigest() == (
        "4f8c110fb45ffa151d54bc9c9dfdad1385306101a1e8397718f82a0b43388b81"
    )
    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    assert review["algorithm_candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "revision": "7ebde589c82e153e0f7d475a8469c120138be4da",
        "source_tree_sha256": (
            "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
        ),
    }
    candidate_revision = review["algorithm_candidate"]["revision"]

    def historical_bytes(relative_path: str) -> bytes:
        return subprocess.run(
            ("git", "show", f"{candidate_revision}:{relative_path}"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout

    for relative_path, expected in review["interface_file_sha256"].items():
        assert hashlib.sha256(historical_bytes(relative_path)).hexdigest() == (
            expected
        )
    composition = hashlib.sha256()
    for module_name, expected in review["scientific_module_sha256"].items():
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").relative_to(_ROOT)
        module_contents = historical_bytes(str(module_path))
        assert hashlib.sha256(module_contents).hexdigest() == expected
        composition.update(module_name.encode())
        composition.update(b"\0")
        composition.update(module_contents)
        composition.update(b"\0")

    assert review["scientific_composition"] == (
        "phase-5-configurable-source-protected-adaptive-background-v3"
    )
    assert composition.hexdigest() == review["scientific_composition_sha256"]
