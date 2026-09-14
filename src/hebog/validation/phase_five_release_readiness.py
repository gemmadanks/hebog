"""Fail-closed Phase 5 readiness review and acceptance records."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import TypeGuard, cast

_CONTRACT_ID = "phase-5-readiness"
_PACKET_ID = "phase-5-readiness-review-packet"
_READINESS_ID = "phase-5-readiness-record"
_ACCEPTANCE_ROLES = ("radio-astronomy", "engineering")
_ACCEPTANCE_KEYS = frozenset(
    {
        "acceptance_id",
        "blocking_findings",
        "cutover_authorized",
        "phase_five_milestone_accepted",
        "release_authorized",
        "review_packet_sha256",
        "reviewed_on",
        "reviewer",
        "role",
        "schema_version",
        "status",
    }
)
_HEXADECIMAL = frozenset("0123456789abcdef")
_SHA256_LENGTH = 64


def _sha256(path: Path) -> str:
    """Return the exact byte identity of one evidence artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, *, label: str) -> dict[str, object]:
    """Load one JSON object and reject every other top-level shape."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _relative_path(path: Path, repository_root: Path) -> str:
    """Return one stable repository-relative path."""
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as error:
        message = "readiness path leaves the repository root"
        raise ValueError(message) from error


def _resolve_path(raw: object, repository_root: Path) -> Path:
    """Resolve one required relative path within the repository."""
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise ValueError("readiness evidence path must be repository-relative")
    path = (repository_root / raw).resolve()
    _relative_path(path, repository_root)
    return path


def _hexadecimal_identity(value: object) -> bool:
    """Return whether a value is one lowercase SHA-256 identity."""
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and set(value) <= _HEXADECIMAL
    )


def _string_object_mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow one JSON object to the record type used by this module."""
    if not isinstance(value, dict):
        return False
    mapping = cast(dict[object, object], value)
    return all(isinstance(key, str) for key in mapping)


def _required_value(document: dict[str, object], dotted_path: str) -> object:
    """Read a dotted object path without implicit list or type coercion."""
    current: object = document
    for key in dotted_path.split("."):
        if (
            not key
            or not _string_object_mapping(current)
            or key not in current
        ):
            raise ValueError(f"required field {dotted_path!r} is absent")
        current = current[key]
    return current


def _validate_authorization_boundary(contract: dict[str, object]) -> None:
    """Require every post-Phase-5 lifecycle authority to remain closed."""
    prohibited = contract.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or not prohibited:
        raise ValueError("readiness authorization boundary changed")
    prohibited_record = cast(dict[str, object], prohibited)
    if (
        prohibited_record.get("cutover_authorized") is not False
        or prohibited_record.get("release_authorized") is not False
        or any(value is not False for value in prohibited_record.values())
    ):
        raise ValueError("readiness authorization boundary changed")


def _validate_review_questions(contract: dict[str, object]) -> None:
    """Require substantive, role-specific questions in the frozen packet."""
    questions = contract.get("review_questions")
    if not _string_object_mapping(questions):
        raise ValueError("readiness review questions differ")
    if frozenset(questions) != frozenset(_ACCEPTANCE_ROLES):
        raise ValueError("readiness review question roles differ")
    for role in _ACCEPTANCE_ROLES:
        values = questions[role]
        if (
            not isinstance(values, list)
            or not values
            or any(
                not isinstance(question, str) or not question.strip()
                for question in cast(list[object], values)
            )
        ):
            raise ValueError(f"readiness {role} review questions differ")


def _validate_evidence_requirements(
    requirements: object,
    repository_root: Path,
) -> None:
    """Validate evidence declarations before any evidence is inspected."""
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("readiness evidence requirements must be a list")
    requirement_values = cast(list[object], requirements)
    identifiers: set[str] = set()
    paths: set[str] = set()
    for value in requirement_values:
        if not isinstance(value, dict):
            message = "readiness evidence requirement must be an object"
            raise ValueError(message)
        requirement = cast(dict[str, object], value)
        identifier = requirement.get("evidence_id")
        raw_path = requirement.get("path")
        owner = requirement.get("review_owner")
        fields = requirement.get("required_fields")
        expected_sha256 = requirement.get("sha256")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("readiness evidence identifier is invalid")
        if identifier in identifiers:
            raise ValueError("readiness evidence identifier is duplicated")
        identifiers.add(identifier)
        path = _resolve_path(raw_path, repository_root)
        display_path = _relative_path(path, repository_root)
        if display_path in paths:
            raise ValueError("readiness evidence path is duplicated")
        paths.add(display_path)
        if owner not in _ACCEPTANCE_ROLES:
            message = f"readiness evidence {identifier!r} owner differs"
            raise ValueError(message)
        if not isinstance(fields, dict) or not fields:
            raise ValueError(
                f"readiness evidence {identifier!r} fields must be an object"
            )
        if expected_sha256 is not None and not _hexadecimal_identity(
            expected_sha256
        ):
            raise ValueError(
                f"readiness evidence {identifier!r} SHA-256 is invalid"
            )


def _program_records(
    programs: object,
    repository_root: Path,
) -> list[dict[str, object]]:
    """Verify exact generator and command programs named by the contract."""
    if not isinstance(programs, list) or not programs:
        raise ValueError("readiness programs must be a non-empty list")
    program_values = cast(list[object], programs)
    records: list[dict[str, object]] = []
    identifiers: set[str] = set()
    paths: set[str] = set()
    for value in program_values:
        if not _string_object_mapping(value):
            raise ValueError("readiness program must be an object")
        identifier = value.get("program_id")
        expected_sha256 = value.get("sha256")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("readiness program identifier is invalid")
        if identifier in identifiers:
            raise ValueError("readiness program identifier is duplicated")
        if not _hexadecimal_identity(expected_sha256):
            raise ValueError(
                f"readiness program {identifier!r} SHA-256 is invalid"
            )
        path = _resolve_path(value.get("path"), repository_root)
        display_path = _relative_path(path, repository_root)
        if display_path in paths:
            raise ValueError("readiness program path is duplicated")
        if not path.is_file() or _sha256(path) != expected_sha256:
            raise ValueError(
                f"readiness program {identifier!r} identity differs"
            )
        identifiers.add(identifier)
        paths.add(display_path)
        records.append(
            {
                "program_id": identifier,
                "path": display_path,
                "sha256": expected_sha256,
            }
        )
    return records


def _contract_document(
    contract_path: Path,
    repository_root: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Load and validate the frozen readiness boundary."""
    contract = _load_object(contract_path, label="readiness contract")
    if (
        contract.get("schema_version") != 1
        or contract.get("contract_id") != _CONTRACT_ID
        or contract.get("status") != "frozen-pre-readiness"
    ):
        raise ValueError("readiness contract identity or status differs")
    if _relative_path(contract_path, repository_root) == "":
        raise ValueError("readiness contract path is invalid")
    if contract.get("required_acceptance_roles") != list(_ACCEPTANCE_ROLES):
        raise ValueError("readiness acceptance roles differ")
    _validate_authorization_boundary(contract)
    _validate_review_questions(contract)
    _validate_evidence_requirements(
        contract.get("required_evidence"),
        repository_root,
    )
    programs = _program_records(contract.get("programs"), repository_root)
    return contract, programs


def prepare_phase_five_readiness_review(
    contract_path: Path,
    *,
    repository_root: Path,
) -> dict[str, object]:
    """Freeze available evidence into a non-promotional review packet.

    Missing evidence is listed as a blocker. Present evidence must match every
    predeclared field and any predeclared SHA-256 or packet construction fails.
    Even a complete machine packet does not close Phase 5: it only becomes
    eligible for two independent, packet-bound acceptances.
    """
    contract, programs = _contract_document(contract_path, repository_root)
    evidence_records: list[dict[str, object]] = []
    blockers: list[str] = []
    requirements = cast(list[dict[str, object]], contract["required_evidence"])
    for requirement in requirements:
        identifier = cast(str, requirement["evidence_id"])
        path = _resolve_path(requirement["path"], repository_root)
        display_path = _relative_path(path, repository_root)
        if not path.is_file():
            evidence_records.append(
                {
                    "evidence_id": identifier,
                    "path": display_path,
                    "review_owner": requirement["review_owner"],
                    "state": "missing",
                }
            )
            blockers.append(f"missing-evidence:{identifier}")
            continue

        identity = _sha256(path)
        expected_sha256 = requirement.get("sha256")
        if expected_sha256 is not None and identity != expected_sha256:
            message = f"readiness evidence {identifier!r} SHA-256 differs"
            raise ValueError(message)
        document = _load_object(path, label=f"readiness evidence {identifier}")
        fields = cast(dict[str, object], requirement["required_fields"])
        observed: dict[str, object] = {}
        for dotted_path, expected in fields.items():
            try:
                actual = _required_value(document, dotted_path)
            except ValueError as error:
                raise ValueError(
                    f"readiness evidence {identifier!r} {error}"
                ) from error
            if actual != expected:
                raise ValueError(
                    f"readiness evidence {identifier!r} required field "
                    f"{dotted_path!r} differs"
                )
            observed[dotted_path] = actual
        evidence_records.append(
            {
                "evidence_id": identifier,
                "path": display_path,
                "sha256": identity,
                "review_owner": requirement["review_owner"],
                "state": "verified",
                "required_fields": observed,
            }
        )

    ready = not blockers
    prohibited = cast(dict[str, bool], contract["prohibited_authorizations"])
    authorization = {
        **prohibited,
        "phase_six_execution_authorized": False,
        "readiness_publication_authorized": False,
    }
    return {
        "schema_version": 1,
        "packet_id": _PACKET_ID,
        "status": (
            "ready-for-independent-review"
            if ready
            else "blocked-before-independent-review"
        ),
        "phase_five_complete": False,
        "contract": {
            "path": _relative_path(contract_path, repository_root),
            "sha256": _sha256(contract_path),
        },
        "programs": programs,
        "evidence": evidence_records,
        "blockers": blockers,
        "required_acceptance_roles": list(_ACCEPTANCE_ROLES),
        "review_questions": contract.get("review_questions", {}),
        "authorization": authorization,
    }


def _acceptance_reviewer(
    document: dict[str, object],
    role: object,
) -> tuple[dict[str, object], str]:
    """Validate and return one acceptance reviewer and review date."""
    reviewer = document.get("reviewer")
    if not isinstance(reviewer, dict):
        raise ValueError(f"Phase 5 {role} reviewer identity is missing")
    reviewer_record = cast(dict[str, object], reviewer)
    reviewer_name = reviewer_record.get("name")
    if not isinstance(reviewer_name, str) or not reviewer_name.strip():
        raise ValueError(f"Phase 5 {role} reviewer identity is missing")
    reviewed_on = document.get("reviewed_on")
    if not isinstance(reviewed_on, str):
        raise ValueError(f"Phase 5 {role} review date is missing")
    try:
        date.fromisoformat(reviewed_on)
    except ValueError as error:
        raise ValueError(f"Phase 5 {role} review date is invalid") from error
    return reviewer_record, reviewed_on


def _validate_acceptance(
    path: Path,
    *,
    packet_sha256: str,
    repository_root: Path,
) -> dict[str, object]:
    """Validate an exact acceptance without promotion authority."""
    document = _load_object(path, label="Phase 5 acceptance")
    if frozenset(document) != _ACCEPTANCE_KEYS:
        raise ValueError("Phase 5 acceptance fields differ")
    role = document.get("role")
    if role not in _ACCEPTANCE_ROLES:
        raise ValueError("Phase 5 acceptance role differs")
    if (
        document.get("schema_version") != 1
        or document.get("acceptance_id") != f"phase-5-{role}-acceptance"
    ):
        raise ValueError(f"Phase 5 {role} acceptance identity differs")
    if document.get("status") != "accepted":
        raise ValueError(f"Phase 5 {role} acceptance must be accepted")
    if document.get("review_packet_sha256") != packet_sha256:
        raise ValueError(f"Phase 5 {role} acceptance packet identity changed")
    if document.get("phase_five_milestone_accepted") is not True:
        raise ValueError(f"Phase 5 {role} milestone not accepted")
    findings = document.get("blocking_findings")
    if findings != []:
        raise ValueError(f"Phase 5 {role} acceptance has blocking findings")
    if (
        document.get("cutover_authorized") is not False
        or document.get("release_authorized") is not False
    ):
        raise ValueError(f"Phase 5 {role} authorization boundary changed")
    reviewer, reviewed_on = _acceptance_reviewer(document, role)
    return {
        "role": role,
        "path": _relative_path(path, repository_root),
        "sha256": _sha256(path),
        "reviewer": reviewer,
        "reviewed_on": reviewed_on,
    }


def finalize_phase_five_readiness(
    review_packet_path: Path,
    *,
    acceptance_paths: tuple[Path, ...],
    repository_root: Path,
) -> dict[str, object]:
    """Close Phase 5 only from complete evidence and two exact acceptances."""
    packet = _load_object(review_packet_path, label="Phase 5 review packet")
    if (
        packet.get("schema_version") != 1
        or packet.get("packet_id") != _PACKET_ID
        or packet.get("status") != "ready-for-independent-review"
        or packet.get("phase_five_complete") is not False
        or packet.get("blockers") != []
    ):
        raise ValueError("Phase 5 packet is not ready for independent review")
    contract_record = packet.get("contract")
    if not isinstance(contract_record, dict):
        raise ValueError("Phase 5 packet contract identity differs")
    contract = cast(dict[str, object], contract_record)
    contract_path = _resolve_path(contract.get("path"), repository_root)
    if _sha256(contract_path) != contract.get("sha256"):
        raise ValueError("Phase 5 packet contract identity differs")
    rebuilt = prepare_phase_five_readiness_review(
        contract_path,
        repository_root=repository_root,
    )
    if rebuilt != packet:
        raise ValueError("Phase 5 review packet or evidence changed")

    packet_sha256 = _sha256(review_packet_path)
    acceptances_by_role: dict[str, dict[str, object]] = {}
    for acceptance_path in acceptance_paths:
        acceptance = _validate_acceptance(
            acceptance_path,
            packet_sha256=packet_sha256,
            repository_root=repository_root,
        )
        role = cast(str, acceptance["role"])
        if role in acceptances_by_role:
            raise ValueError("Phase 5 acceptance role is duplicated")
        acceptances_by_role[role] = acceptance
    if tuple(sorted(acceptances_by_role)) != tuple(sorted(_ACCEPTANCE_ROLES)):
        message = "Phase 5 requires radio-astronomy and engineering acceptance"
        raise ValueError(message)

    authorization = cast(dict[str, bool], packet["authorization"])
    if any(authorization.values()):
        raise ValueError("Phase 5 packet authorization boundary changed")
    evidence = cast(list[dict[str, object]], packet["evidence"])
    return {
        "schema_version": 1,
        "readiness_id": _READINESS_ID,
        "status": "complete",
        "phase_five_complete": True,
        "review_packet": {
            "path": _relative_path(review_packet_path, repository_root),
            "sha256": packet_sha256,
        },
        "review_packet_sha256": packet_sha256,
        "contract_sha256": contract["sha256"],
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "path": item["path"],
                "sha256": item["sha256"],
            }
            for item in evidence
        ],
        "acceptances": [
            acceptances_by_role[role] for role in _ACCEPTANCE_ROLES
        ],
        "next_phase": "phase-6-distributed-execution",
        "authorization": authorization,
    }
