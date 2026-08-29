"""Contracts for the measurement-repair replay composition pre-review."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.public_finder_correction import (
    public_finder_source_association_candidate_configuration,
)

_ROOT = Path(__file__).parents[3]
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-replay-pre-review.json"
)
_READINESS = _ROOT / "config/contracts/phase-5-readiness.json"
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-association-"
    "measurement-repair-replay-implementation-decision.json"
)
_CANDIDATE_REVISION = "6184a32648eee637f0aca03ab2ec0249bd0510f0"
_IMPLEMENTATION_REVISION = "9cc00fb339b12fb00695b0799f828a5afba8ee16"


def _load(path: Path) -> dict[str, Any]:
    """Load one JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _committed_bytes(revision: str, path: str) -> bytes:
    """Read one file from an exact Git revision."""
    return subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _committed_json(revision: str, path: str) -> dict[str, Any]:
    """Load one JSON object from an exact historical revision."""
    document = json.loads(_committed_bytes(revision, path))
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


def _committed_source_tree_sha256(revision: str) -> str:
    """Reproduce the production-source identity at one revision."""
    paths = subprocess.check_output(
        ("git", "ls-tree", "-r", "--name-only", revision, "src/hebog"),
        cwd=_ROOT,
        text=True,
    ).splitlines()
    digest = hashlib.sha256()
    for path in sorted(item for item in paths if item.endswith(".py")):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(_committed_bytes(revision, path))
        digest.update(b"\0")
    return digest.hexdigest()


def test_pre_review_is_non_executable_and_requires_named_approval() -> None:
    """The review opens no implementation, replay, or later authority."""
    review = _load(_PRE_REVIEW)

    assert review["schema_version"] == 1
    assert review["status"] == (
        "ready-for-named-measurement-repair-replay-composition-review"
    )
    assert set(review["authorization"].values()) == {False}
    assert review["required_next_decision"] == (
        "named-approval-of-this-exact-pre-review-for-wrapper-readiness-"
        "implementation-no-write-validation-and-non-executable-identity-"
        "freezing-only"
    )


def test_pre_review_binds_exact_repair_candidate_and_configuration() -> None:
    """The review binds committed code and the unchanged science config."""
    review = _load(_PRE_REVIEW)
    candidate = cast(dict[str, Any], review["candidate"])

    assert candidate == {
        "configuration_sha256": (
            "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
        ),
        "measurement_repair": {
            "path": "src/hebog/validation/products.py",
            "sha256": (
                "a3c53daac3dbae03bd6b3f62488cd46de541d79d9c6c903d34ce7951334d690b"
            ),
        },
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _committed_source_tree_sha256(
            _CANDIDATE_REVISION
        ),
        "tree": "d27f59168111ded8690c783e56bc735b294d7250",
    }
    assert (
        hashlib.sha256(
            _committed_bytes(
                _CANDIDATE_REVISION,
                "src/hebog/validation/products.py",
            )
        ).hexdigest()
        == candidate["measurement_repair"]["sha256"]
    )
    configuration = public_finder_source_association_candidate_configuration(
        _ROOT / "config/contracts/phase-5-corrective-a-review.json",
        _ROOT / "config/contracts/phase-5-public-finder-correction.json",
        _ROOT / "config/contracts/phase-5-public-finder-source-association-"
        "pre-review.json",
        _ROOT / "config/contracts/phase-5-public-finder-source-association-"
        "implementation-decision.json",
    )
    assert canonical_sha256(configuration) == candidate["configuration_sha256"]


def test_pre_review_uses_new_write_once_namespaces() -> None:
    """Consumed source-association execution state cannot be overwritten."""
    review = _load(_PRE_REVIEW)
    boundary = cast(dict[str, Any], review["consumed_boundary"])
    prospective = cast(dict[str, Any], review["prospective_composition"])

    assert boundary["execution_decision"] == {
        "path": (
            "config/contracts/phase-5-public-finder-source-association-"
            "cumulative-replay-execution-decision.json"
        ),
        "sha256": (
            "d806f38e7f57ef4fea757a9d5fcb3499221bc0d89058d3582dfce96c2d1a4e34"
        ),
    }
    assert boundary["wrapper"] == {
        "path": (
            "scripts/validation/review_phase5_public_finder_source_"
            "association_cumulative_regressions.py"
        ),
        "sha256": (
            "bfc1d6d0d255b9fd7e7b43f910e9c2665d9083de572bce7b64afee66c473f357"
        ),
    }
    assert boundary["ledger_published"] is False
    assert boundary["completed_candidate_product_count"] == 58
    assert prospective["output_path"].endswith(
        "cumulative-regression-ledger-public-finder-source-association-"
        "measurement-repair.json"
    )
    assert prospective["scratch_path"].endswith(
        "hebog-phase5-public-finder-source-association-measurement-repair-"
        "6184a32"
    )
    assert prospective["output_path"] != boundary["output_path"]
    assert prospective["scratch_path"] != boundary["scratch_path"]


def test_pre_review_prospectively_rebinds_readiness() -> None:
    """Readiness identities must change before repaired evidence is opened."""
    review = _load(_PRE_REVIEW)
    readiness = cast(dict[str, Any], review["readiness_repair"])
    current = _committed_json(
        _IMPLEMENTATION_REVISION,
        str(_READINESS.relative_to(_ROOT)),
    )
    implementation = _load(_IMPLEMENTATION_DECISION)
    current_requirement = cast(dict[str, Any], current["required_evidence"][0])

    assert readiness["current_contract"] == {
        "path": "config/contracts/phase-5-readiness.json",
        "sha256": implementation["readiness"]["previous_sha256"],
        "status": "frozen-pre-readiness",
    }
    assert (
        hashlib.sha256(
            _committed_bytes(
                _IMPLEMENTATION_REVISION,
                str(_READINESS.relative_to(_ROOT)),
            )
        ).hexdigest()
        != readiness["current_contract"]["sha256"]
    )
    assert current_requirement["required_fields"]["candidate_revision"] == (
        _CANDIDATE_REVISION
    )
    replacement = readiness["required_replacement_fields"]
    assert replacement["candidate_revision"] == _CANDIDATE_REVISION
    assert replacement["candidate_source_tree_sha256"] == (
        "517d56e19a5d58eb386d96bdb181d36afb574ad018222f870cc8434c398044ff"
    )
    assert replacement["candidate_configuration_sha256"] == (
        "78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946"
    )
    assert replacement["cumulative_science_regression_ready"] is True
    assert replacement["like_semantics_compact_regressions"] == []
    assert replacement["like_semantics_continuum_regressions"] == []
    assert readiness["must_precede_replay"] is True
