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
from hebog.data_models import (
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
)

_ROOT = Path(__file__).parents[2]


def _provenance() -> PublicSourceFindingProvenance:
    """Return one exact public provenance fixture."""
    return PublicSourceFindingProvenance(
        input_sha256="1" * 64,
        configuration_sha256="2" * 64,
        scientific_profile_sha256="3" * 64,
        scientific_composition_sha256="4" * 64,
        scientific_composition=(
            "phase-5-configurable-source-protected-adaptive-background-v3"
        ),
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
        configuration_qualification="phase-5-reference",
        source_count=1,
        gaussian_component_count=1,
        island_count=1,
        rms_scientific_status="valid",
        provenance=_provenance(),
    )

    assert (
        PublicSourceFindingDiagnostics.from_json_bytes(
            diagnostics.canonical_json_bytes()
        )
        == diagnostics
    )
    assert diagnostics.schema_version == 4


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
                "configuration_qualification": "phase-5-reference",
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


def test_source_protected_public_identity_binds_current_science() -> None:
    """The successor review binds the exact installed corrected candidate."""
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
    for relative_path, expected in review["interface_file_sha256"].items():
        assert hashlib.sha256(
            (_ROOT / relative_path).read_bytes()
        ).hexdigest() == (expected)
    composition = hashlib.sha256()
    for module_name, expected in review["scientific_module_sha256"].items():
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").resolve()
        module_contents = module_path.read_bytes()
        assert hashlib.sha256(module_contents).hexdigest() == expected
        composition.update(module_name.encode())
        composition.update(b"\0")
        composition.update(module_contents)
        composition.update(b"\0")

    assert review["scientific_composition"] == public_api._COMPOSITION_NAME
    assert composition.hexdigest() == review["scientific_composition_sha256"]
