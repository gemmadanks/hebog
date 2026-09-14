#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bind the approved viewed-development recovery execution."""

from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol
from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).parents[2]
_PROTOCOL_PATH = (
    "config/contracts/phase-5-external-post-failure-comparison.json"
)
_PROTOCOL_SHA256 = (
    "a616da88f497a4c003a289ad3a6f667c24873eafc62a9711ae182d5f259ffdf5"
)
_DECISION_ID = "phase-5-viewed-recovery-execution-decision"
_ORIGINAL_CAMPAIGN_SHA256 = (
    "c16dc486464e09dd729f4a90eb1d586bfd6c2eecc04bda1a41b3b209c2ae091a"
)
_ORIGINAL_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_CANDIDATE_REVISION = "c184acf7f55f936442285835b4601a6ac193fe2a"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_MATERIALIZER_RUNTIME = (
    "hebog",
    "e519dc15b846dec7ac00a6cada7684d0c0b2615490dd6688ac4c6cdf5f3021ca",
    "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1",
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2",
)
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_REFERENCE_RUNTIMES = (
    (
        "released-pybdsf",
        "43a6513865a597285dc1bf473e27fc69fdd86fb143c35a24144eb6c1152bb36e",
        "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198",
        "8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f",
    ),
    (
        "pinned-pybdsf-master",
        "0360fbbfe42fe13aea1559f5603e4fcf4c51c84f7ad5fd201ba8fd76a88df087",
        "sha256:0e6d932416479bb7d7763fe2e025ea9fbbd0d0548a6f156b2cdd881766690c75",
        "83574dd4c15d79f3cf2ac52fb8aa7b5bd2ff323c93343b2f1337eec938e8bf99",
    ),
    (
        "aegean",
        "9e79e24b2460596a57a8ebba5c3987fa636886631579ef333ad46b801b3a86b8",
        "sha256:dcac8e646ff5ea6d11d314c5c7a51fb0c3ca710165934ad2ddf0ac3f999131b0",
        "346c1f32b0d78ce1d22f6d6ff20787a102d8491c14432865465596c9f41ba909",
    ),
)
_HISTORICAL = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_post_failure_protocol.py")
)


def file_sha256(path: Path) -> str:
    """Hash one bound recovery artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _install_historical_source_view() -> None:
    loader = _HISTORICAL["load_post_failure_population"]

    def historical_source_sha256(_root: Path) -> str:
        return cast(str, _HISTORICAL["_SOURCE_TREE_SHA256"])

    loader.__globals__["source_tree_sha256"] = historical_source_sha256


def load_viewed_recovery_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Load the viewed population with equivalent rebuilt references."""
    if path.resolve() != (_ROOT / _PROTOCOL_PATH).resolve():
        raise ValueError("unexpected viewed recovery protocol path")
    if file_sha256(path) != _PROTOCOL_SHA256:
        raise ValueError("viewed recovery protocol identity changed")
    _install_historical_source_view()
    protocol = _HISTORICAL["load_post_failure_protocol"](path)
    current = {
        finder: (image_id, digest, inventory)
        for finder, image_id, digest, inventory in _REFERENCE_RUNTIMES
    }
    if tuple(item.finder_id for item in protocol.references) != tuple(current):
        raise ValueError("viewed recovery reference order changed")
    references = []
    for reference in protocol.references:
        _, digest, inventory = current[reference.finder_id]
        if reference.dependency_inventory_sha256 != inventory:
            raise ValueError("viewed recovery dependency identity changed")
        references.append(
            reference.model_copy(update={"container_image_digest": digest})
        )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        protocol.model_copy(update={"references": tuple(references)}),
    )


@dataclass(frozen=True, slots=True)
class ViewedRecoveryRunner:
    """One exact runner authorized for reconstructed reference evidence."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ViewedRecoveryExecutionDecision:
    """Minimal decision view consumed by unchanged isolated runners."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    execution_concurrency: int
    runners: tuple[ViewedRecoveryRunner, ...]
    execution_authorized: bool
    fresh_campaign_execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def _require_runtime_identities(document: dict[str, Any]) -> None:
    observed = tuple(
        (
            item.get("finder_id"),
            item.get("image_id"),
            item.get("digest"),
            item.get("dependency_inventory_sha256"),
        )
        for item in cast(list[dict[str, Any]], document["reference_runtimes"])
    )
    if observed != _REFERENCE_RUNTIMES:
        raise ValueError("viewed recovery reference runtime changed")


def load_viewed_recovery_execution_decision(
    path: Path,
) -> ViewedRecoveryExecutionDecision:
    """Validate the named development-only recovery approval."""
    document = _json_object(path)
    expected_keys = {
        "schema_version",
        "decision_id",
        "status",
        "named_review",
        "protocol_path",
        "protocol_sha256",
        "original_campaign_sha256",
        "original_request_sha256",
        "candidate_review_sha256",
        "candidate_revision",
        "candidate_source_tree_sha256",
        "candidate_configuration_sha256",
        "materializer_runtime",
        "reference_runtimes",
        "pybdsf_ncores",
        "execution_concurrency",
        "runners",
        "execution_authorized",
        "fresh_campaign_execution_authorized",
        "one_look_opened",
        "step_three_authorized",
        "optimization_authorized",
        "qualification_opened",
    }
    if set(document) != expected_keys:
        raise ValueError("viewed recovery decision fields changed")
    root = path.resolve().parents[2]
    if (
        document["schema_version"] != 1
        or document["decision_id"] != _DECISION_ID
        or document["status"] != "approved-viewed-development-recovery"
        or document["protocol_path"] != _PROTOCOL_PATH
        or document["protocol_sha256"] != _PROTOCOL_SHA256
        or document["original_campaign_sha256"] != _ORIGINAL_CAMPAIGN_SHA256
        or document["original_request_sha256"] != _ORIGINAL_REQUEST_SHA256
        or document["candidate_revision"] != _CANDIDATE_REVISION
        or document["candidate_source_tree_sha256"]
        != _CANDIDATE_SOURCE_TREE_SHA256
        or document["candidate_configuration_sha256"]
        != _CANDIDATE_CONFIGURATION_SHA256
        or document["candidate_review_sha256"] != _CANDIDATE_REVIEW_SHA256
        or document["pybdsf_ncores"] != _PYBDSF_NCORES
        or document["execution_concurrency"] != _EXECUTION_CONCURRENCY
        or document["execution_authorized"] is not True
        or document["fresh_campaign_execution_authorized"] is not False
        or any(
            document[field] is not False
            for field in (
                "one_look_opened",
                "step_three_authorized",
                "optimization_authorized",
                "qualification_opened",
            )
        )
    ):
        raise ValueError("viewed recovery decision identity changed")
    if file_sha256(root / _PROTOCOL_PATH) != _PROTOCOL_SHA256:
        raise ValueError("viewed recovery protocol changed")
    if (
        file_sha256(root / "config/contracts/phase-5-corrective-a-review.json")
        != _CANDIDATE_REVIEW_SHA256
    ):
        raise ValueError("viewed recovery candidate review changed")
    if source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256:
        raise ValueError("viewed recovery candidate source changed")
    materializer = cast(dict[str, Any], document["materializer_runtime"])
    if (
        materializer.get("finder_id"),
        materializer.get("image_id"),
        materializer.get("digest"),
        materializer.get("dependency_inventory_sha256"),
    ) != _MATERIALIZER_RUNTIME:
        raise ValueError("viewed recovery materializer runtime changed")
    _require_runtime_identities(document)
    runners = tuple(
        ViewedRecoveryRunner(**item)
        for item in cast(list[dict[str, str]], document["runners"])
    )
    for runner in runners:
        if file_sha256(root / runner.relative_path) != runner.sha256:
            raise ValueError("viewed recovery runner changed")
    return ViewedRecoveryExecutionDecision(
        protocol_sha256=cast(str, document["protocol_sha256"]),
        candidate_review_sha256=cast(str, document["candidate_review_sha256"]),
        implementation_commit=cast(str, document["candidate_revision"]),
        source_tree_sha256=cast(str, document["candidate_source_tree_sha256"]),
        hebog_container_image_digest=cast(str, materializer["digest"]),
        hebog_dependency_inventory_sha256=cast(
            str, materializer["dependency_inventory_sha256"]
        ),
        pybdsf_ncores=cast(int, document["pybdsf_ncores"]),
        execution_concurrency=cast(int, document["execution_concurrency"]),
        runners=runners,
        execution_authorized=True,
        fresh_campaign_execution_authorized=False,
        one_look_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )
