"""Fail-closed Phase 5 readiness review and acceptance contracts."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from hebog.validation.phase_five_release_readiness import (
    finalize_phase_five_readiness,
    prepare_phase_five_readiness_review,
)

_ROOT = Path(__file__).parents[3]
_READINESS_CONTRACT = _ROOT / "config/contracts/phase-5-readiness.json"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(path: Path, *, status: str = "pass") -> Path:
    return _write_json(
        path,
        {
            "schema_version": 1,
            "status": status,
            "nested": {"ready": True},
            "regressions": [],
        },
    )


def _contract(
    root: Path,
    *,
    include_second: bool = True,
) -> Path:
    evidence = _evidence(root / "evidence" / "science.json")
    library = _write_json(root / "programs" / "readiness.json", {"v": 1})
    command = _write_json(root / "programs" / "command.json", {"v": 1})
    requirements: list[dict[str, object]] = [
        {
            "evidence_id": "science",
            "path": "evidence/science.json",
            "sha256": _sha256(evidence),
            "required_fields": {
                "nested.ready": True,
                "regressions": [],
                "status": "pass",
            },
            "review_owner": "radio-astronomy",
        }
    ]
    if include_second:
        requirements.append(
            {
                "evidence_id": "engineering",
                "path": "evidence/engineering.json",
                "sha256": None,
                "required_fields": {"status": "pass"},
                "review_owner": "engineering",
            }
        )
    return _write_json(
        root / "readiness-contract.json",
        {
            "schema_version": 1,
            "contract_id": "phase-5-readiness",
            "status": "frozen-pre-readiness",
            "programs": [
                {
                    "program_id": "readiness-library",
                    "path": "programs/readiness.json",
                    "sha256": _sha256(library),
                },
                {
                    "program_id": "readiness-command",
                    "path": "programs/command.json",
                    "sha256": _sha256(command),
                },
            ],
            "required_evidence": requirements,
            "required_acceptance_roles": ["radio-astronomy", "engineering"],
            "review_questions": {
                "radio-astronomy": ["Is the science acceptable?"],
                "engineering": ["Is the implementation acceptable?"],
            },
            "prohibited_authorizations": {
                "cutover_authorized": False,
                "release_authorized": False,
            },
        },
    )


def _acceptance(
    path: Path,
    *,
    role: str,
    packet_sha256: str,
    status: str = "accepted",
) -> Path:
    return _write_json(
        path,
        {
            "schema_version": 1,
            "acceptance_id": f"phase-5-{role}-acceptance",
            "role": role,
            "status": status,
            "reviewer": {"name": "Independent Reviewer"},
            "reviewed_on": "2026-08-27",
            "review_packet_sha256": packet_sha256,
            "phase_five_milestone_accepted": True,
            "blocking_findings": [],
            "cutover_authorized": False,
            "release_authorized": False,
        },
    )


def test_prepare_review_packet_lists_missing_evidence_without_passing(
    tmp_path: Path,
) -> None:
    """An absent result is a named blocker, never an inferred pass."""
    packet = prepare_phase_five_readiness_review(
        _contract(tmp_path),
        repository_root=tmp_path,
    )

    assert packet["status"] == "blocked-before-independent-review"
    assert packet["phase_five_complete"] is False
    assert packet["blockers"] == ["missing-evidence:engineering"]
    evidence = cast(list[dict[str, object]], packet["evidence"])
    assert [item["state"] for item in evidence] == ["verified", "missing"]
    assert set(cast(dict[str, bool], packet["authorization"]).values()) == {
        False
    }


def test_repository_contract_names_every_phase_five_closure_boundary() -> None:
    """The real packet cannot omit a hard gate or either independent role."""
    contract = json.loads(_READINESS_CONTRACT.read_text(encoding="utf-8"))

    assert contract["required_acceptance_roles"] == [
        "radio-astronomy",
        "engineering",
    ]
    assert {item["evidence_id"] for item in contract["required_evidence"]} == {
        "bounded-deterministic-execution-contract",
        "closed-final-qualification-context",
        "incremental-multiscale-performance",
        "public-finder-correction-cumulative-regression",
        "public-finder-correction-held-out-qualification",
        "rapthor-profile",
        "terminal-public-failure-context",
        "terminal-public-failure-scientific-review",
    }
    assert {item["program_id"] for item in contract["programs"]} == {
        "readiness-command",
        "readiness-library",
    }
    assert set(contract["review_questions"]) == {
        "engineering",
        "radio-astronomy",
    }
    assert all(contract["review_questions"].values())
    assert set(contract["prohibited_authorizations"].values()) == {False}


def test_prepare_review_packet_rejects_program_hash_drift(
    tmp_path: Path,
) -> None:
    """The exact readiness implementation is part of the packet identity."""
    contract = _contract(tmp_path)
    program = tmp_path / "programs" / "readiness.json"
    program.write_bytes(program.read_bytes() + b"\n")

    with pytest.raises(ValueError, match=r"readiness-library.*identity"):
        prepare_phase_five_readiness_review(
            contract,
            repository_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"prohibited_authorizations": {}}, "authorization boundary"),
        (
            {
                "prohibited_authorizations": {
                    "cutover_authorized": True,
                    "release_authorized": False,
                }
            },
            "authorization boundary",
        ),
        ({"review_questions": []}, "review questions differ"),
        (
            {"review_questions": {"radio-astronomy": ["Question?"]}},
            "question roles differ",
        ),
        (
            {
                "review_questions": {
                    "radio-astronomy": ["Question?"],
                    "engineering": [],
                }
            },
            "engineering review questions differ",
        ),
        ({"required_evidence": []}, "evidence requirements"),
        ({"programs": []}, "programs must be"),
    ],
)
def test_prepare_rejects_changed_contract_boundaries(
    tmp_path: Path,
    mutation: dict[str, object],
    message: str,
) -> None:
    """A weakened contract fails before any scientific evidence is reviewed."""
    contract = _contract(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload.update(mutation)
    _write_json(contract, payload)

    with pytest.raises(ValueError, match=message):
        prepare_phase_five_readiness_review(
            contract,
            repository_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"evidence_id": ""}, "identifier is invalid"),
        ({"path": "/tmp/outside.json"}, "repository-relative"),
        ({"review_owner": "operations"}, "owner differs"),
        ({"required_fields": {}}, "fields must be an object"),
        ({"sha256": "not-a-sha"}, "SHA-256 is invalid"),
    ],
)
def test_prepare_rejects_invalid_evidence_declarations(
    tmp_path: Path,
    mutation: dict[str, object],
    message: str,
) -> None:
    """Evidence declarations must remain typed, owned, and repository-local."""
    contract = _contract(tmp_path)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["required_evidence"][0].update(mutation)
    _write_json(contract, payload)

    with pytest.raises(ValueError, match=message):
        prepare_phase_five_readiness_review(
            contract,
            repository_root=tmp_path,
        )


def test_prepare_rejects_absent_required_nested_field(tmp_path: Path) -> None:
    """A missing declared field is malformed rather than pending."""
    contract = _contract(tmp_path, include_second=False)
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["required_evidence"][0]["required_fields"]["absent.ready"] = True
    _write_json(contract, payload)

    with pytest.raises(ValueError, match=r"science.*absent.ready.*absent"):
        prepare_phase_five_readiness_review(
            contract,
            repository_root=tmp_path,
        )


def test_prepare_review_packet_rejects_present_but_invalid_evidence(
    tmp_path: Path,
) -> None:
    """Malformed or failing evidence cannot be downgraded to a blocker only."""
    contract = _contract(tmp_path, include_second=False)
    contract_payload = json.loads(contract.read_text(encoding="utf-8"))
    contract_payload["required_evidence"][0]["sha256"] = None
    _write_json(contract, contract_payload)
    _evidence(tmp_path / "evidence" / "science.json", status="fail")

    with pytest.raises(ValueError, match=r"science.*required field.*status"):
        prepare_phase_five_readiness_review(
            contract,
            repository_root=tmp_path,
        )


def test_prepare_review_packet_rejects_evidence_hash_drift(
    tmp_path: Path,
) -> None:
    """A reviewed evidence identity cannot change under the same contract."""
    contract = _contract(tmp_path, include_second=False)
    evidence = tmp_path / "evidence" / "science.json"
    evidence.write_bytes(evidence.read_bytes() + b"\n")

    with pytest.raises(ValueError, match=r"science.*SHA-256"):
        prepare_phase_five_readiness_review(
            contract,
            repository_root=tmp_path,
        )


def test_prepare_review_packet_is_ready_only_when_every_gate_is_present(
    tmp_path: Path,
) -> None:
    """Complete machine evidence opens review, not Phase 5 itself."""
    contract = _contract(tmp_path)
    _evidence(tmp_path / "evidence" / "engineering.json")

    packet = prepare_phase_five_readiness_review(
        contract,
        repository_root=tmp_path,
    )

    assert packet["status"] == "ready-for-independent-review"
    assert packet["phase_five_complete"] is False
    assert packet["blockers"] == []
    assert packet["required_acceptance_roles"] == [
        "radio-astronomy",
        "engineering",
    ]


def test_finalize_refuses_a_blocked_packet(tmp_path: Path) -> None:
    """Human signatures cannot compensate for missing machine evidence."""
    packet = prepare_phase_five_readiness_review(
        _contract(tmp_path),
        repository_root=tmp_path,
    )
    packet_path = _write_json(tmp_path / "packet.json", packet)

    with pytest.raises(ValueError, match="not ready for independent review"):
        finalize_phase_five_readiness(
            packet_path,
            acceptance_paths=(),
            repository_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"status": "rejected"}, "must be accepted"),
        ({"review_packet_sha256": "0" * 64}, "packet identity changed"),
        ({"blocking_findings": ["unresolved"]}, "blocking findings"),
        ({"cutover_authorized": True}, "authorization boundary changed"),
        ({"phase_five_milestone_accepted": False}, "milestone not accepted"),
        ({"tuning_authorized": True}, "acceptance fields differ"),
        ({"reviewer": []}, "reviewer identity is missing"),
        ({"reviewer": {"name": " "}}, "reviewer identity is missing"),
        ({"reviewed_on": None}, "review date is missing"),
        ({"reviewed_on": "not-a-date"}, "review date is invalid"),
        ({"role": "legal"}, "acceptance role differs"),
        ({"acceptance_id": "changed"}, "acceptance identity differs"),
    ],
)
def test_finalize_rejects_invalid_acceptance(
    tmp_path: Path,
    mutation: dict[str, object],
    message: str,
) -> None:
    """Reviewer records are exact, non-compensating, and non-promotional."""
    contract = _contract(tmp_path)
    _evidence(tmp_path / "evidence" / "engineering.json")
    packet = prepare_phase_five_readiness_review(
        contract,
        repository_root=tmp_path,
    )
    packet_path = _write_json(tmp_path / "packet.json", packet)
    packet_sha256 = _sha256(packet_path)
    scientific = _acceptance(
        tmp_path / "scientific.json",
        role="radio-astronomy",
        packet_sha256=packet_sha256,
    )
    engineering = _acceptance(
        tmp_path / "engineering.json",
        role="engineering",
        packet_sha256=packet_sha256,
    )
    payload = json.loads(scientific.read_text(encoding="utf-8"))
    payload.update(mutation)
    _write_json(scientific, payload)

    with pytest.raises(ValueError, match=message):
        finalize_phase_five_readiness(
            packet_path,
            acceptance_paths=(scientific, engineering),
            repository_root=tmp_path,
        )


def test_finalize_publishes_completion_without_cutover_or_release(
    tmp_path: Path,
) -> None:
    """Exact acceptances close the milestone and no later lifecycle gate."""
    contract = _contract(tmp_path)
    _evidence(tmp_path / "evidence" / "engineering.json")
    packet = prepare_phase_five_readiness_review(
        contract,
        repository_root=tmp_path,
    )
    packet_path = _write_json(tmp_path / "packet.json", packet)
    packet_sha256 = _sha256(packet_path)
    acceptances = tuple(
        _acceptance(
            tmp_path / f"{role}.json",
            role=role,
            packet_sha256=packet_sha256,
        )
        for role in ("radio-astronomy", "engineering")
    )

    record = finalize_phase_five_readiness(
        packet_path,
        acceptance_paths=acceptances,
        repository_root=tmp_path,
    )

    assert record["status"] == "complete"
    assert record["phase_five_complete"] is True
    assert record["review_packet_sha256"] == packet_sha256
    assert set(cast(dict[str, bool], record["authorization"]).values()) == {
        False
    }
    acceptance_records = cast(list[dict[str, object]], record["acceptances"])
    assert [item["role"] for item in acceptance_records] == [
        "radio-astronomy",
        "engineering",
    ]


def test_readiness_cli_outputs_are_write_once(tmp_path: Path) -> None:
    """Neither the packet nor terminal record can overwrite reviewed bytes."""
    module = runpy.run_path(
        str(_ROOT / "scripts/validation/review_phase5_readiness.py")
    )
    contract = _contract(tmp_path)
    packet_output = tmp_path / "packet.json"
    arguments = SimpleNamespace(
        command="prepare",
        contract=contract,
        repository_root=tmp_path,
        output=packet_output,
    )
    module["main"].__globals__["_parse_args"] = lambda: arguments

    module["main"]()
    assert json.loads(packet_output.read_text(encoding="utf-8"))["status"] == (
        "blocked-before-independent-review"
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module["main"]()
