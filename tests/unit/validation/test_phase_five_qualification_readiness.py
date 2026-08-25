"""Pre-opening audit of the Phase 5 qualification design."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from hebog.validation.phase_five_readiness import (
    audit_phase_five_qualification_design,
)

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config/datasets/phase-5-qualification.json"


def _power_review(path: Path, *, qualification_opened: bool = False) -> Path:
    payload = {
        "schema_version": 1,
        "review_id": "phase-5-viewed-recovery-power-review",
        "status": "ready-for-named-scientific-freeze-review",
        "cumulative_ledger": {
            "candidate_revision": "c" * 40,
            "candidate_source_tree_sha256": "1" * 64,
            "candidate_configuration_sha256": "2" * 64,
        },
        "planning": {
            "minimum_continuum_realization_count": 1532,
            "selected_continuum_realization_count": 1688,
            "continuum_realizations_per_geometry": 422,
            "geometry_count": 4,
            "paired_comparison_count": 226,
        },
        "power": {
            "combined_familywise_power_lower_bound": 0.905,
            "minimum_joint_power": 0.9,
        },
        "authorization": {
            "execution_authorized": False,
            "fresh_population_frozen": False,
            "qualification_opened": qualification_opened,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _mutate_review(path: Path, dotted_key: str, value: object) -> Path:
    """Replace one nested field in a temporary power review."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys = dotted_key.split(".")
    target = payload
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_qualification_design_audit_keeps_underpowered_manifest_unopened(
    tmp_path: Path,
) -> None:
    """The old 400-image design cannot be opened under the current audit."""
    review = _power_review(tmp_path / "power.json")

    audit = audit_phase_five_qualification_design(_MANIFEST, review)
    current = cast(dict[str, object], audit["current_design"])
    power = cast(dict[str, object], audit["power_requirement"])
    replacement = cast(dict[str, object], audit["replacement_design"])
    authorization = cast(dict[str, object], audit["authorization"])

    assert audit["status"] == "replacement-design-required"
    assert current["realization_count"] == 400
    assert current["geometry_count"] == 1
    assert power["minimum_realization_count"] == 1532
    assert replacement["realization_count"] == 1688
    assert replacement["geometry_count"] == 4
    assert replacement["realizations_per_geometry"] == 422
    assert replacement["preserve_current_manifest_unopened"]
    assert not authorization["qualification_opened"]
    assert not authorization["execution_authorized"]


def test_qualification_design_audit_rejects_open_or_inconsistent_power(
    tmp_path: Path,
) -> None:
    """Viewed qualification or inconsistent power identities fail closed."""
    opened = _power_review(tmp_path / "opened.json", qualification_opened=True)
    with pytest.raises(ValueError, match="must remain unopened"):
        audit_phase_five_qualification_design(_MANIFEST, opened)

    review = _power_review(tmp_path / "unbalanced.json")
    payload = json.loads(review.read_text(encoding="utf-8"))
    payload["planning"]["continuum_realizations_per_geometry"] = 421
    review.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="balanced geometry design"):
        audit_phase_five_qualification_design(_MANIFEST, review)


@pytest.mark.parametrize(
    ("dotted_key", "value", "message"),
    [
        ("planning", [], "planning.*object"),
        (
            "planning.minimum_continuum_realization_count",
            True,
            "positive integer",
        ),
        (
            "power.combined_familywise_power_lower_bound",
            "high",
            "must be numeric",
        ),
        ("power.minimum_joint_power", 2.0, "must be a probability"),
        (
            "cumulative_ledger.candidate_revision",
            "g" * 40,
            "hexadecimal identity",
        ),
        ("status", "viewed", "identity or status differs"),
        (
            "authorization.execution_authorized",
            True,
            "pre-freeze and pre-execution",
        ),
        (
            "planning.selected_continuum_realization_count",
            1500,
            "smaller than the power minimum",
        ),
        (
            "power.combined_familywise_power_lower_bound",
            0.8,
            "familywise power does not pass",
        ),
    ],
)
def test_qualification_design_audit_rejects_malformed_power_review(
    tmp_path: Path,
    dotted_key: str,
    value: object,
    message: str,
) -> None:
    """Every required power and provenance field fails closed."""
    review = _mutate_review(
        _power_review(tmp_path / "power.json"), dotted_key, value
    )

    with pytest.raises(ValueError, match=message):
        audit_phase_five_qualification_design(_MANIFEST, review)


def test_qualification_design_audit_rejects_manifest_or_document_drift(
    tmp_path: Path,
) -> None:
    """Only the qualification manifest and an object review are accepted."""
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    payload["manifest_id"] = "phase-5-other"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    review = _power_review(tmp_path / "power.json")
    with pytest.raises(ValueError, match="manifest identity differs"):
        audit_phase_five_qualification_design(manifest, review)

    payload["manifest_id"] = "phase-5-qualification"
    payload["datasets"][0]["role"] = "regression"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="must contain qualification data"):
        audit_phase_five_qualification_design(manifest, review)

    review.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        audit_phase_five_qualification_design(_MANIFEST, review)


def test_qualification_design_audit_can_recognize_a_sufficient_design(
    tmp_path: Path,
) -> None:
    """The status can close once the reviewed requirement is actually met."""
    review = _power_review(tmp_path / "power.json")
    for dotted_key, value in (
        ("planning.minimum_continuum_realization_count", 400),
        ("planning.selected_continuum_realization_count", 400),
        ("planning.continuum_realizations_per_geometry", 400),
        ("planning.geometry_count", 1),
    ):
        _mutate_review(review, dotted_key, value)

    audit = audit_phase_five_qualification_design(_MANIFEST, review)

    assert audit["status"] == "current-design-sufficient"


def test_qualification_design_review_cli_is_write_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command publishes one write-once audit and refuses replacement."""
    review = _power_review(tmp_path / "power.json")
    output = tmp_path / "audit.json"
    module = runpy.run_path(
        str(_ROOT / "scripts/validation/review_phase5_qualification_design.py")
    )
    arguments = SimpleNamespace(
        manifest=_MANIFEST,
        power_review=review,
        output=output,
    )
    monkeypatch.setitem(
        module["main"].__globals__, "_parse_args", lambda: arguments
    )

    module["main"]()
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["status"] == "replacement-design-required"

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module["main"]()
