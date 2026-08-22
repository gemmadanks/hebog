#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate the approved fresh Phase 5 recovery composition."""

from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, create_model

from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol
from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).parents[2]
_BASE = runpy.run_path(
    str(
        _ROOT
        / "scripts/validation/phase5_external_post_correction_protocol.py"
    )
)
_PROTOCOL_ID = "phase-5-external-recovery-comparison"
_DECISION_ID = "phase-5-external-recovery-execution-decision"
_POPULATION_PATH = "config/contracts/phase-5-external-recovery-population.json"
_POPULATION_SHA256 = (
    "c2a4ac5b9763f2451fd07a18440b76ff3d5705dd2e56dd4273475efbe0423220"
)
_CONTINUUM_MANIFEST = (
    "config/datasets/phase-5-external-recovery-continuum.json"
)
_CONTINUUM_SHA256 = (
    "d10f43874d5f2cf045a87b5f13e5cff8a29e74bc989dbfd113748a61403441b1"
)
_COMPACT_MANIFEST = (
    "config/datasets/phase-5-external-recovery-compact-blend.json"
)
_COMPACT_SHA256 = (
    "57b09825d62bb7a8732dbb25bed4d45f623f191a1b969fd48fed121090f4c85a"
)
_IDENTITY_REVIEW = (
    "config/contracts/phase-5-external-recovery-identity-review.json"
)
_CANDIDATE_REVISION = "c184acf7f55f936442285835b4601a6ac193fe2a"
_SOURCE_TREE_SHA256 = (
    "b4176ce387fa1569cc86ca300bfa7de6462758a1068de46cd4a16616a6ec3adc"
)
_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_CUMULATIVE_LEDGER_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_POWER_REVIEW_SHA256 = (
    "bbfab3a0781c8a12083190d8c591152d5c461a45824bab6cba39e770915af9fc"
)
_RECOVERY_DECISION_SHA256 = (
    "b35f4a811827df8960c22484193e9198d547bbb0e588e5b215d1f8d9ed66865f"
)
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_IMAGE_COUNT = 2488
_RUN_COUNT = 12440
_BINDING_RUN_COUNT = 8264
_CONTINUUM_IMAGE_COUNT = 1688
_COMPACT_IMAGE_COUNT = 800
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_RUNTIME_IMAGES = (
    (
        "hebog",
        "e519dc15b846dec7ac00a6cada7684d0c0b2615490dd6688ac4c6cdf5f3021ca",
        "sha256:1a83f64948460a46dd6f6c5e9434d155fd9b2ae45f97db849d5288f350dca8d1",
        "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2",
    ),
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
_REFERENCE_IMAGE_DIGESTS = tuple(
    (finder_id, digest)
    for finder_id, _image_id, digest, _inventory in _RUNTIME_IMAGES
    if finder_id != "hebog"
)
_HEBOG_IMAGE_DIGEST = _RUNTIME_IMAGES[0][2]
_HEBOG_INVENTORY_SHA256 = _RUNTIME_IMAGES[0][3]
_RUNNER_PATHS = (
    "scripts/benchmark/run_phase5_external_recovery_hebog.py",
    "scripts/benchmark/run_phase5_external_recovery_pybdsf.py",
    "scripts/benchmark/run_phase5_external_recovery_aegean.py",
)


def file_sha256(path: Path) -> str:
    """Hash one artifact without retaining it in memory."""
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
    if frozenset(document) != expected:
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


def _install_closed_source_view() -> None:
    """Verify the closed post-correction base against its recorded source."""
    loader = _BASE["load_post_correction_population"]

    def historical_source_tree(_root: Path) -> str:
        return cast(str, _BASE["_SOURCE_TREE_SHA256"])

    loader.__globals__["source_tree_sha256"] = historical_source_tree


def load_recovery_population(path: Path) -> dict[str, Any]:
    """Validate the approved science, power, and fresh seed freeze."""
    if file_sha256(path) != _POPULATION_SHA256:
        raise ValueError("recovery population checksum changed")
    document = json_object(path)
    candidate = cast(dict[str, Any], document.get("candidate"))
    approval = cast(dict[str, Any], document.get("scientific_approval"))
    evidence = cast(dict[str, Any], document.get("evidence"))
    audit = cast(dict[str, Any], document.get("population_audit"))
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-external-recovery-population"
        or document.get("status")
        != "scientifically-approved-and-frozen-before-output"
        or approval
        != {
            "reviewer": "Gemma Danks",
            "approved_on": "2026-08-22",
            "scope": "recovery-scientific-freeze-only-no-execution",
        }
        or candidate.get("revision") != _CANDIDATE_REVISION
        or candidate.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or candidate.get("configuration_sha256") != _CONFIGURATION_SHA256
        or evidence.get("cumulative_ledger_sha256")
        != _CUMULATIVE_LEDGER_SHA256
        or evidence.get("power_review_sha256") != _POWER_REVIEW_SHA256
        or evidence.get("recovery_decision_sha256")
        != _RECOVERY_DECISION_SHA256
        or audit.get("new_seed_count") != _IMAGE_COUNT
        or audit.get("seed_disjoint") is not True
        or document.get("execution_authorized") is not False
        or document.get("finder_output_generated") is not False
        or document.get("finder_output_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
    ):
        raise ValueError("recovery population state is invalid")
    root = path.resolve().parents[2]
    if source_tree_sha256(root) != _SOURCE_TREE_SHA256:
        raise ValueError("recovery source tree changed")
    generator = cast(dict[str, Any], document["generator"])
    if file_sha256(root / generator["relative_path"]) != generator["sha256"]:
        raise ValueError("recovery population generator changed")
    populations = cast(list[dict[str, Any]], document["populations"])
    expected = (
        ("continuum", _CONTINUUM_MANIFEST, _CONTINUUM_SHA256, 1688),
        ("compact-blend", _COMPACT_MANIFEST, _COMPACT_SHA256, 800),
    )
    observed = tuple(
        (
            item.get("lane"),
            item.get("manifest"),
            item.get("manifest_sha256"),
            item.get("image_count"),
        )
        for item in populations
    )
    if observed != expected:
        raise ValueError("recovery frozen population changed")
    for item in populations:
        if file_sha256(root / item["manifest"]) != item["manifest_sha256"]:
            raise ValueError("recovery manifest checksum changed")
    _BASE["_validate_power"](cast(dict[str, Any], document["power_audit"]))
    return document


def load_recovery_protocol(path: Path) -> PhaseFiveExternalComparisonProtocol:
    """Expose unchanged gates over the fresh recovery population."""
    document = json_object(path)
    required = frozenset(
        {
            "base_protocol_path",
            "base_protocol_sha256",
            "candidate_configuration_sha256",
            "closed_campaign_reuse_authorized",
            "contract_id",
            "execution_authorized",
            "optimization_authorized",
            "population_contract_path",
            "population_contract_sha256",
            "populations",
            "qualification_opened",
            "schema_version",
            "status",
            "step_three_authorized",
        }
    )
    require_exact_keys(document, required, description="recovery protocol")
    if (
        document.get("schema_version") != 1
        or document.get("contract_id") != _PROTOCOL_ID
        or document.get("status") != "frozen-before-external-output"
        or document.get("candidate_configuration_sha256")
        != _CONFIGURATION_SHA256
        or document.get("execution_authorized") is not False
        or document.get("closed_campaign_reuse_authorized") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
    ):
        raise ValueError("recovery protocol state is invalid")
    root = path.resolve().parents[2]
    base_relative = (
        "config/contracts/phase-5-external-post-correction-comparison.json"
    )
    base_path = root / base_relative
    if (
        document.get("base_protocol_path") != base_relative
        or document.get("base_protocol_sha256") != file_sha256(base_path)
        or document.get("population_contract_path") != _POPULATION_PATH
        or document.get("population_contract_sha256") != _POPULATION_SHA256
    ):
        raise ValueError("recovery protocol ancestry changed")
    load_recovery_population(root / _POPULATION_PATH)
    populations = cast(list[dict[str, Any]], document.get("populations"))
    expected = (
        ("continuum", _CONTINUUM_MANIFEST, _CONTINUUM_SHA256, 1688),
        ("compact-blend", _COMPACT_MANIFEST, _COMPACT_SHA256, 800),
    )
    observed = tuple(
        (
            item.get("lane"),
            item.get("manifest"),
            item.get("manifest_sha256"),
            item.get("image_count"),
        )
        for item in populations
    )
    if observed != expected:
        raise ValueError("recovery protocol population changed")
    _install_closed_source_view()
    base = _BASE["load_post_correction_protocol"](base_path)
    reference_digests = dict(_REFERENCE_IMAGE_DIGESTS)
    compatible_references = tuple(
        item.model_copy(
            update={
                "container_image_digest": reference_digests[item.finder_id]
            }
        )
        for item in base.references
    )
    compatible_populations = tuple(
        old.model_copy(update=new)
        for old, new in zip(base.populations, populations, strict=True)
    )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        base.model_copy(
            update={
                "references": compatible_references,
                "populations": compatible_populations,
            }
        ),
    )


@dataclass(frozen=True, slots=True)
class RecoveryRunnerArtifact:
    """One checksum-bound recovery runner wrapper."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RecoveryExecutionDecision:
    """Pending or approved authorization consumed by campaign mechanics."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    execution_concurrency: int
    runners: tuple[RecoveryRunnerArtifact, ...]
    identity_review_sha256: str
    named_review: str
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def _identity_review_binding(
    document: dict[str, Any],
    root: Path,
    *,
    pending: bool,
) -> str:
    """Validate the pending or exact approved identity review binding."""
    value = document.get("identity_review_sha256")
    if pending:
        if value != "pending":
            raise ValueError("pending recovery review binding changed")
        return "pending"
    review = load_recovery_identity_review(root / _IDENTITY_REVIEW)
    if (
        not isinstance(value, str)
        or value != file_sha256(root / _IDENTITY_REVIEW)
        or value not in cast(str, document.get("named_review"))
        or review.get("status") != "ready-for-named-execution-approval"
    ):
        raise ValueError("approved recovery review binding changed")
    return value


def load_recovery_execution_decision(path: Path) -> RecoveryExecutionDecision:
    """Validate pending or named recovery one-look authorization."""
    document = json_object(path)
    required = frozenset(
        {
            "candidate_configuration_sha256",
            "candidate_review_sha256",
            "cumulative_ledger_sha256",
            "decision",
            "decision_id",
            "execution_authorized",
            "execution_concurrency",
            "hebog_container_image_digest",
            "hebog_dependency_inventory_sha256",
            "identity_review_path",
            "identity_review_sha256",
            "implementation_commit",
            "named_review",
            "next_action",
            "one_look_opened",
            "optimization_authorized",
            "population_contract_sha256",
            "power_review_sha256",
            "protocol_sha256",
            "pybdsf_ncores",
            "qualification_opened",
            "runners",
            "schema_version",
            "source_tree_sha256",
            "status",
            "step_three_authorized",
        }
    )
    require_exact_keys(document, required, description="recovery decision")
    pending = document.get("status") == "awaiting-named-execution-approval"
    approved = document.get("status") == "reviewed-before-external-output"
    if (
        document.get("schema_version") != 1
        or document.get("decision_id") != _DECISION_ID
        or pending == approved
        or document.get("implementation_commit") != _CANDIDATE_REVISION
        or document.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or document.get("candidate_configuration_sha256")
        != _CONFIGURATION_SHA256
        or document.get("cumulative_ledger_sha256")
        != _CUMULATIVE_LEDGER_SHA256
        or document.get("power_review_sha256") != _POWER_REVIEW_SHA256
        or document.get("population_contract_sha256") != _POPULATION_SHA256
        or document.get("candidate_review_sha256") != _CANDIDATE_REVIEW_SHA256
        or document.get("hebog_container_image_digest") != _HEBOG_IMAGE_DIGEST
        or document.get("hebog_dependency_inventory_sha256")
        != _HEBOG_INVENTORY_SHA256
        or document.get("pybdsf_ncores") != _PYBDSF_NCORES
        or document.get("execution_concurrency") != _EXECUTION_CONCURRENCY
        or document.get("identity_review_path") != _IDENTITY_REVIEW
        or document.get("one_look_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
    ):
        raise ValueError("recovery decision identity is invalid")
    expected_state = (
        (
            "await-named-one-look-approval",
            False,
            "pending",
            "obtain-named-one-look-approval-before-no-write-preflight",
        )
        if pending
        else (
            "authorize-one-terminal-recovery-comparison",
            True,
            document.get("named_review"),
            "run-complete-no-write-preflight-before-terminal-execution",
        )
    )
    if (
        document.get("decision"),
        document.get("execution_authorized"),
        document.get("named_review"),
        document.get("next_action"),
    ) != expected_state:
        raise ValueError("recovery authorization state is invalid")
    root = path.resolve().parents[2]
    protocol_path = (
        root / "config/contracts/phase-5-external-recovery-comparison.json"
    )
    if document.get("protocol_sha256") != file_sha256(protocol_path):
        raise ValueError("recovery decision protocol changed")
    review_sha256 = _identity_review_binding(document, root, pending=pending)
    runners = document.get("runners")
    if not isinstance(runners, list):
        raise ValueError("recovery runner identities are absent")
    observed_paths = tuple(
        item.get("relative_path") for item in runners if isinstance(item, dict)
    )
    if observed_paths != _RUNNER_PATHS:
        raise ValueError("recovery runner order changed")
    records = tuple(
        RecoveryRunnerArtifact(
            relative_path=cast(str, item["relative_path"]),
            sha256=cast(str, item["sha256"]),
        )
        for item in runners
    )
    for item in records:
        if file_sha256(root / item.relative_path) != item.sha256:
            raise ValueError(f"recovery runner changed: {item.relative_path}")
    return RecoveryExecutionDecision(
        protocol_sha256=cast(str, document["protocol_sha256"]),
        candidate_review_sha256=_CANDIDATE_REVIEW_SHA256,
        implementation_commit=_CANDIDATE_REVISION,
        source_tree_sha256=_SOURCE_TREE_SHA256,
        hebog_container_image_digest=_HEBOG_IMAGE_DIGEST,
        hebog_dependency_inventory_sha256=_HEBOG_INVENTORY_SHA256,
        pybdsf_ncores=_PYBDSF_NCORES,
        execution_concurrency=_EXECUTION_CONCURRENCY,
        runners=records,
        identity_review_sha256=review_sha256,
        named_review=cast(str, document["named_review"]),
        execution_authorized=cast(bool, document["execution_authorized"]),
        one_look_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )


def load_recovery_endpoint_registry(path: Path) -> dict[str, Any]:
    """Validate the exact prospective compiler and endpoint composition."""
    document = json_object(path)
    if (
        document.get("schema_version") != 1
        or document.get("registry_id")
        != "phase-5-external-recovery-endpoint-registry"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
    ):
        raise ValueError("recovery registry state is invalid")
    root = path.resolve().parents[2]
    base_relative = (
        "config/contracts/"
        "phase-5-external-post-correction-endpoint-registry.json"
    )
    base_path = root / base_relative
    if document.get("base_registry_path") != base_relative or document.get(
        "base_registry_sha256"
    ) != file_sha256(base_path):
        raise ValueError("recovery registry ancestry changed")
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "recovery protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "recovery population",
        ),
        ("continuum_manifest_path", "continuum_manifest_sha256", "continuum"),
        ("compact_manifest_path", "compact_manifest_sha256", "compact"),
        (
            "execution_decision_path",
            "execution_decision_sha256",
            "recovery decision",
        ),
        ("launcher_path", "launcher_sha256", "recovery launcher"),
        ("compiler_path", "compiler_sha256", "recovery compiler"),
        (
            "protocol_verifier_path",
            "protocol_verifier_sha256",
            "recovery verifier",
        ),
        (
            "compiler_accelerator_path",
            "compiler_accelerator_sha256",
            "recovery compiler seams",
        ),
        (
            "candidate_adapter_path",
            "candidate_adapter_sha256",
            "recovery candidate adapter",
        ),
    ):
        require_bound_file(
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    _install_closed_source_view()
    base = _BASE["load_post_correction_endpoint_registry"](base_path)
    compatible = dict(base)
    compatible.update(document)
    return compatible


def _authorization_transitioned(root: Path) -> bool:
    """Return whether the pending decision received named approval."""
    decision = json_object(
        root
        / "config/contracts/phase-5-external-recovery-execution-decision.json"
    )
    status = decision.get("status")
    if status not in {
        "awaiting-named-execution-approval",
        "reviewed-before-external-output",
    }:
        raise ValueError("recovery authorization state is invalid")
    return status == "reviewed-before-external-output"


def load_recovery_identity_review(path: Path) -> dict[str, Any]:
    """Validate frozen programs and four runtimes without authorizing them."""
    document = json_object(path)
    if (
        document.get("schema_version") != 1
        or document.get("review_id")
        != "phase-5-external-recovery-identity-review"
        or document.get("status") != "ready-for-named-execution-approval"
        or document.get("execution_authorized") is not False
        or document.get("scientific_products_opened") is not False
    ):
        raise ValueError("recovery identity review state is invalid")
    implementation = cast(dict[str, Any], document.get("implementation"))
    population = cast(dict[str, Any], document.get("population"))
    authorization = cast(dict[str, Any], document.get("authorization"))
    if (
        implementation
        != {
            "candidate_revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _SOURCE_TREE_SHA256,
            "configuration_sha256": _CONFIGURATION_SHA256,
        }
        or population
        != {
            "image_count": _IMAGE_COUNT,
            "continuum_image_count": _CONTINUUM_IMAGE_COUNT,
            "compact_blend_image_count": _COMPACT_IMAGE_COUNT,
            "binding_run_count": _BINDING_RUN_COUNT,
            "terminal_run_count": _RUN_COUNT,
        }
        or authorization.get("required_next_decision")
        != "named-one-look-approval-bound-to-this-review-and-four-runtimes"
    ):
        raise ValueError("recovery identity review binding changed")
    runtime_images = document.get("runtime_images")
    if not isinstance(runtime_images, list):
        raise ValueError("recovery runtime identities are absent")
    observed = tuple(
        (
            item.get("finder_id"),
            item.get("image_id"),
            item.get("digest"),
            item.get("dependency_inventory_sha256"),
        )
        for item in runtime_images
        if isinstance(item, dict)
    )
    if observed != _RUNTIME_IMAGES:
        raise ValueError("recovery runtime identities changed")
    identities = document.get("identity_artifacts")
    if not isinstance(identities, list) or not identities:
        raise ValueError("recovery program identities are absent")
    root = path.resolve().parents[2]
    transitioned = _authorization_transitioned(root)
    approval_dependent = {
        "config/contracts/phase-5-external-recovery-execution-decision.json",
        "config/contracts/phase-5-external-recovery-endpoint-registry.json",
        "config/contracts/phase-5-external-recovery-evaluation.json",
    }
    for identity in identities:
        if not isinstance(identity, dict):
            raise ValueError("recovery program identity is malformed")
        relative = identity.get("relative_path")
        expected = identity.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("recovery program identity changed")
        if (
            relative not in approval_dependent or not transitioned
        ) and file_sha256(root / relative) != expected:
            raise ValueError("recovery program identity changed")
    return document


def recovery_campaign_request_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Replace only the approved population literals on a request model."""
    return create_model(
        f"Recovery{historical_model.__name__}",
        __base__=historical_model,
        image_count=(Literal[2488], ...),
        run_count=(Literal[12440], ...),
    )


def recovery_terminal_result_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Replace only the approved population literals on a result model."""
    return recovery_campaign_request_model(historical_model)
