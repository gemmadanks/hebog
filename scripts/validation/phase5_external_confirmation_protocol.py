#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate the fresh Phase 5 confirmation campaign composition."""

from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol

_ROOT = Path(__file__).parents[2]
_PREDECESSOR_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_successor_protocol.py")
)
_PROTOCOL_ID = "phase-5-external-confirmation-comparison"
_DECISION_ID = "phase-5-external-confirmation-execution-decision"
_PREFLIGHT_REVIEW = (
    "config/contracts/phase-5-external-confirmation-preflight-review.json"
)
_CONTINUUM_MANIFEST = (
    "config/datasets/phase-5-external-confirmation-continuum.json"
)
_COMPACT_MANIFEST = (
    "config/datasets/phase-5-external-confirmation-compact-blend.json"
)
_CONTINUUM_SHA256 = (
    "6f4118de01331bb19a8b56402a07dd168f617d22c94c8774d499eeb180793874"
)
_COMPACT_SHA256 = (
    "1ef6561a4bc87d2197f940f7a605f723663aa49052a9bffc5ca32249aa6808f8"
)
_POPULATION_SHA256 = (
    "c346549df25c8b7d7bdadc6791e590d0333c08d918bd9c530b27042025444768"
)
_IMPLEMENTATION_COMMIT = "ee69ebae316e79b793c410d36c94fb3e0121908d"
_SOURCE_TREE_SHA256 = (
    "b002878831c5f00fbe15c7b1d5a34abcee773aa35457b6fb2d56acef050fc942"
)
_HEBOG_IMAGE_DIGEST = (
    "sha256:88696bd96844d5d28022ce21185b731b2d78183192db53991e8b04e556dfcbf3"
)
_HEBOG_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
)
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_RUNNERS = (
    (
        "scripts/benchmark/run_phase5_external_confirmation_hebog.py",
        "d2b3bfce1fbfab1e95d2adb1df5fe18a11819b85ba131342d91ca66e721420f8",
    ),
    (
        "scripts/benchmark/run_phase5_external_confirmation_pybdsf.py",
        "0e224725709796e05f147ccfff2c8d480a3ec93bbffd59a95bea3be9cf4295c8",
    ),
    (
        "scripts/benchmark/run_phase5_external_confirmation_aegean.py",
        "37b716055e9f14a9287708e5352bec14dd5b8c8899bbf73f7b2f477cfc3a3263",
    ),
)
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2


def file_sha256(path: Path) -> str:
    """Hash one repository artifact without retaining it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_object(path: Path) -> dict[str, Any]:
    """Load one strict JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def require_exact_keys(
    document: dict[str, Any],
    expected: frozenset[str],
    *,
    description: str,
) -> None:
    """Reject missing and ignored fields at a governed boundary."""
    if set(document) != expected:
        raise ValueError(f"{description} fields changed")


def require_bound_file(
    root: Path,
    document: dict[str, Any],
    *,
    path_key: str,
    sha_key: str,
    description: str,
) -> None:
    """Verify one exact repository dependency."""
    relative_path = document.get(path_key)
    expected_sha256 = document.get(sha_key)
    if not isinstance(relative_path, str) or not isinstance(
        expected_sha256, str
    ):
        raise ValueError(f"{description} identity is incomplete")
    if file_sha256(root / relative_path) != expected_sha256:
        raise ValueError(f"{description} checksum changed")


def load_confirmation_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Validate fresh populations and expose the inherited science policy."""
    document = json_object(path)
    require_exact_keys(
        document,
        frozenset(
            {
                "base_protocol_path",
                "base_protocol_sha256",
                "closed_campaign_reuse_authorized",
                "contract_id",
                "execution_authorized",
                "optimization_authorized",
                "populations",
                "qualification_opened",
                "schema_version",
                "status",
                "step_three_authorized",
                "population_contract_path",
                "population_contract_sha256",
            }
        ),
        description="confirmation external protocol",
    )
    if (
        document.get("schema_version") != 1
        or document.get("contract_id") != _PROTOCOL_ID
        or document.get("status") != "frozen-before-external-output"
        or document.get("execution_authorized") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
        or document.get("closed_campaign_reuse_authorized") is not False
    ):
        raise ValueError("confirmation external protocol state is invalid")
    root = path.resolve().parents[2]
    base_path = (
        root / "config/contracts/phase-5-external-successor-comparison.json"
    )
    if (
        document.get("base_protocol_path")
        != "config/contracts/phase-5-external-successor-comparison.json"
        or document.get("base_protocol_sha256") != file_sha256(base_path)
        or document.get("population_contract_path")
        != "config/contracts/phase-5-external-confirmation-population.json"
        or document.get("population_contract_sha256") != _POPULATION_SHA256
        or file_sha256(
            root
            / "config/contracts/phase-5-external-confirmation-population.json"
        )
        != _POPULATION_SHA256
    ):
        raise ValueError("confirmation protocol ancestry changed")
    populations = document.get("populations")
    expected = (
        ("continuum", _CONTINUUM_MANIFEST, _CONTINUUM_SHA256, 600),
        ("compact-blend", _COMPACT_MANIFEST, _COMPACT_SHA256, 800),
    )
    if (
        not isinstance(populations, list)
        or tuple(
            (
                item.get("lane"),
                item.get("manifest"),
                item.get("manifest_sha256"),
                item.get("image_count"),
            )
            for item in populations
            if isinstance(item, dict)
        )
        != expected
    ):
        raise ValueError("confirmation population identity changed")
    for item in populations:
        if not isinstance(item, dict):
            raise ValueError("confirmation population is not an object")
        require_exact_keys(
            item,
            frozenset({"image_count", "lane", "manifest", "manifest_sha256"}),
            description="confirmation population",
        )
        if (
            file_sha256(root / cast(str, item["manifest"]))
            != item["manifest_sha256"]
        ):
            raise ValueError("confirmation manifest checksum changed")
    base = _PREDECESSOR_HELPERS["load_successor_protocol"](base_path)
    compatible = tuple(
        old.model_copy(update=new)
        for old, new in zip(base.populations, populations, strict=True)
    )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        base.model_copy(update={"populations": compatible}),
    )


@dataclass(frozen=True, slots=True)
class ConfirmationRunnerArtifact:
    """One checksum-bound confirmation runner wrapper."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ConfirmationExecutionDecision:
    """Authorization view consumed by the unchanged campaign mechanics."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    execution_concurrency: int
    runners: tuple[ConfirmationRunnerArtifact, ...]
    preflight_review_sha256: str
    named_review: str
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def confirmation_preflight_review_sha256(
    document: dict[str, Any],
    root: Path,
    *,
    pending: bool,
) -> str:
    """Validate the asymmetric pending/approved review binding."""
    value = document.get("preflight_review_sha256")
    if pending:
        if value != "pending":
            raise ValueError("pending confirmation review binding changed")
        return "pending"
    if (
        not isinstance(value, str)
        or value != file_sha256(root / _PREFLIGHT_REVIEW)
        or value not in cast(str, document["named_review"])
    ):
        raise ValueError("approved confirmation review binding changed")
    return value


def load_confirmation_execution_decision(
    path: Path,
) -> ConfirmationExecutionDecision:
    """Validate pending or named confirmation authorization."""
    document = json_object(path)
    require_exact_keys(
        document,
        frozenset(
            {
                "candidate_review_sha256",
                "decision",
                "decision_id",
                "execution_authorized",
                "execution_concurrency",
                "hebog_container_image_digest",
                "hebog_dependency_inventory_sha256",
                "implementation_commit",
                "named_review",
                "next_action",
                "one_look_opened",
                "optimization_authorized",
                "preflight_review_path",
                "preflight_review_sha256",
                "protocol_sha256",
                "pybdsf_ncores",
                "qualification_opened",
                "runners",
                "schema_version",
                "source_tree_sha256",
                "status",
                "step_three_authorized",
            }
        ),
        description="confirmation execution decision",
    )
    pending = document.get("status") == "awaiting-named-execution-approval"
    approved = document.get("status") == "reviewed-before-external-output"
    if (
        document.get("schema_version") != 1
        or document.get("decision_id") != _DECISION_ID
        or pending == approved
        or document.get("implementation_commit") != _IMPLEMENTATION_COMMIT
        or document.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or document.get("hebog_container_image_digest") != _HEBOG_IMAGE_DIGEST
        or document.get("hebog_dependency_inventory_sha256")
        != _HEBOG_INVENTORY_SHA256
        or document.get("candidate_review_sha256") != _CANDIDATE_REVIEW_SHA256
        or document.get("pybdsf_ncores") != _PYBDSF_NCORES
        or document.get("execution_concurrency") != _EXECUTION_CONCURRENCY
        or document.get("one_look_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
        or document.get("preflight_review_path") != _PREFLIGHT_REVIEW
    ):
        raise ValueError("confirmation execution decision identity is invalid")
    expected_state = (
        (
            "await-named-execution-approval",
            False,
            "pending",
            "obtain-named-approval-before-confirmation-preflight",
        )
        if pending
        else (
            "authorize-one-terminal-confirmation-comparison",
            True,
            document.get("named_review"),
            "execute-complete-confirmation-comparison-once-without-opening-"
            "partial-results",
        )
    )
    if (
        document.get("decision"),
        document.get("execution_authorized"),
        document.get("named_review"),
        document.get("next_action"),
    ) != expected_state:
        raise ValueError("confirmation authorization state is invalid")
    if approved and not cast(str, document["named_review"]).strip():
        raise ValueError("confirmation named review is absent")
    root = path.resolve().parents[2]
    protocol_path = (
        root / "config/contracts/phase-5-external-confirmation-comparison.json"
    )
    review_path = root / "config/contracts/phase-5-corrective-a-review.json"
    if document.get("protocol_sha256") != file_sha256(
        protocol_path
    ) or document.get("candidate_review_sha256") != file_sha256(review_path):
        raise ValueError("confirmation decision binding changed")
    preflight_review_sha256 = confirmation_preflight_review_sha256(
        document,
        root,
        pending=pending,
    )
    runners = document.get("runners")
    if (
        not isinstance(runners, list)
        or tuple(
            (item.get("relative_path"), item.get("sha256"))
            for item in runners
            if isinstance(item, dict)
        )
        != _RUNNERS
    ):
        raise ValueError("confirmation runner identity changed")
    records = tuple(
        ConfirmationRunnerArtifact(relative_path=path_, sha256=sha256)
        for path_, sha256 in _RUNNERS
    )
    for item in records:
        if file_sha256(root / item.relative_path) != item.sha256:
            raise ValueError(
                f"confirmation runner changed: {item.relative_path}"
            )
    return ConfirmationExecutionDecision(
        protocol_sha256=cast(str, document["protocol_sha256"]),
        candidate_review_sha256=_CANDIDATE_REVIEW_SHA256,
        implementation_commit=_IMPLEMENTATION_COMMIT,
        source_tree_sha256=_SOURCE_TREE_SHA256,
        hebog_container_image_digest=_HEBOG_IMAGE_DIGEST,
        hebog_dependency_inventory_sha256=_HEBOG_INVENTORY_SHA256,
        pybdsf_ncores=_PYBDSF_NCORES,
        execution_concurrency=_EXECUTION_CONCURRENCY,
        runners=records,
        preflight_review_sha256=preflight_review_sha256,
        named_review=cast(str, document["named_review"]),
        execution_authorized=cast(bool, document["execution_authorized"]),
        one_look_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )


def load_confirmation_endpoint_registry(path: Path) -> dict[str, Any]:
    """Validate confirmation composition and inherit the endpoint matrix."""
    document = json_object(path)
    require_exact_keys(
        document,
        frozenset(
            {
                "base_registry_path",
                "base_registry_sha256",
                "closed_campaign_reuse_authorized",
                "compact_manifest_path",
                "compact_manifest_sha256",
                "compiler_accelerator_path",
                "compiler_accelerator_sha256",
                "compiler_path",
                "compiler_sha256",
                "continuum_manifest_path",
                "continuum_manifest_sha256",
                "execution_decision_path",
                "execution_decision_sha256",
                "launcher_path",
                "launcher_sha256",
                "protocol_path",
                "protocol_sha256",
                "protocol_verifier_path",
                "protocol_verifier_sha256",
                "registry_id",
                "schema_version",
                "status",
            }
        ),
        description="confirmation endpoint registry",
    )
    if (
        document.get("schema_version") != 1
        or document.get("registry_id")
        != "phase-5-external-confirmation-endpoint-registry"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
    ):
        raise ValueError("confirmation endpoint registry state is invalid")
    root = path.resolve().parents[2]
    base_path = (
        root
        / "config/contracts/phase-5-external-successor-endpoint-registry.json"
    )
    if (
        document.get("base_registry_path")
        != "config/contracts/phase-5-external-successor-endpoint-registry.json"
        or document.get("base_registry_sha256") != file_sha256(base_path)
    ):
        raise ValueError("confirmation endpoint ancestry changed")
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "confirmation protocol"),
        (
            "continuum_manifest_path",
            "continuum_manifest_sha256",
            "confirmation continuum manifest",
        ),
        (
            "compact_manifest_path",
            "compact_manifest_sha256",
            "confirmation compact manifest",
        ),
        (
            "execution_decision_path",
            "execution_decision_sha256",
            "confirmation execution decision",
        ),
        ("launcher_path", "launcher_sha256", "confirmation launcher"),
        ("compiler_path", "compiler_sha256", "confirmation compiler"),
        (
            "protocol_verifier_path",
            "protocol_verifier_sha256",
            "confirmation protocol verifier",
        ),
        (
            "compiler_accelerator_path",
            "compiler_accelerator_sha256",
            "confirmation compiler accelerator",
        ),
    ):
        require_bound_file(
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    load_confirmation_protocol(root / cast(str, document["protocol_path"]))
    load_confirmation_execution_decision(
        root / cast(str, document["execution_decision_path"])
    )
    base = _PREDECESSOR_HELPERS["load_successor_endpoint_registry"](base_path)
    compatible = dict(base)
    compatible.update(document)
    compatible["registry_id"] = "phase-5-external-endpoint-registry"
    return compatible
