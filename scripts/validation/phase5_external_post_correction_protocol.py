#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate the approved fresh Phase 5 post-correction composition."""

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
from hebog.validation.phase_five_post_failure_power import (
    PairedPowerPrior,
    conservative_familywise_power,
    minimum_realization_count,
    prospective_joint_power,
)

_ROOT = Path(__file__).parents[2]
_BASE = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_post_failure_protocol.py")
)
_PROTOCOL_ID = "phase-5-external-post-correction-comparison"
_DECISION_ID = "phase-5-external-post-correction-execution-decision"
_POPULATION_PATH = (
    "config/contracts/phase-5-external-post-correction-population.json"
)
_POPULATION_SHA256 = (
    "f1fec27a1469073cc59ffcc65bce02954ed4f0825f2381aeb0387bdf0b9a803a"
)
_CONTINUUM_MANIFEST = (
    "config/datasets/phase-5-external-post-correction-continuum.json"
)
_CONTINUUM_SHA256 = (
    "3bf2af93f71939c80035c8db7760e5435a8e40764e3af24c94bb009713ea7913"
)
_COMPACT_MANIFEST = (
    "config/datasets/phase-5-external-post-correction-compact-blend.json"
)
_COMPACT_SHA256 = (
    "9ae3642fdbaa1bf7e867ef5faa1ae29274a4ece74b7cf95d6610e0b86c74cafc"
)
_PREFLIGHT_REVIEW = (
    "config/contracts/phase-5-external-post-correction-preflight-review.json"
)
_CANDIDATE_REVISION = "dfc3e25e635f4f6710558e483fa5a525ba904661"
_SOURCE_TREE_SHA256 = (
    "a549143b6475e75f7463c834e891c005a0660c2de9f4a0a3556c18bb9d39541d"
)
_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_CUMULATIVE_LEDGER_SHA256 = (
    "7ffd636482438c92462a0f15e00ff6759ae875d7b6ebab50bc1c8a3a9cf35be2"
)
_POWER_REVIEW_SHA256 = (
    "d68163f545d02f88433602a7b1ccd3f480aefafa7e30aa786bb9201bdadaa63d"
)
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_IMAGE_COUNT = 2488
_RUN_COUNT = 12440
_BINDING_RUN_COUNT = 8264
_CONTINUUM_IMAGE_COUNT = 1688
_COMPACT_IMAGE_COUNT = 800
_CONTINUUM_PER_GEOMETRY = 422
_EXPECTED_PRIOR_COUNT = 226
_RESERVED_DEVELOPMENT_SEED_COUNT = 280
_POWER_TOLERANCE = 1e-12
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_MINIMUM_AVAILABLE_GIB = 126.0
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
_HEBOG_IMAGE_DIGEST = _RUNTIME_IMAGES[0][2]
_HEBOG_INVENTORY_SHA256 = _RUNTIME_IMAGES[0][3]
_RUNNER_PATHS = (
    "scripts/benchmark/run_phase5_external_post_correction_hebog.py",
    "scripts/benchmark/run_phase5_external_post_correction_pybdsf.py",
    "scripts/benchmark/run_phase5_external_post_correction_aegean.py",
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
        expected_sha256,
        str,
    ):
        raise ValueError(f"{description} identity is incomplete")
    if file_sha256(root / relative_path) != expected_sha256:
        raise ValueError(f"{description} checksum changed")


def _install_historical_source_view() -> None:
    """Verify the closed base only against its frozen source identity."""
    loader = _BASE["load_post_failure_population"]
    loader.__globals__["source_tree_sha256"] = lambda _root: _BASE[
        "_SOURCE_TREE_SHA256"
    ]


def _validate_power(power: dict[str, Any]) -> None:
    """Recompute the selected sample's conservative power bounds."""
    assumptions = power.get("paired_assumptions")
    if (
        not isinstance(assumptions, list)
        or len(assumptions) != _EXPECTED_PRIOR_COUNT
    ):
        raise ValueError("post-correction power assumptions changed")
    priors = tuple(PairedPowerPrior(**item) for item in assumptions)
    compact_power = float(power["compact_familywise_power_lower_bound"])
    minimum_joint = float(power["minimum_joint_power"])
    minimum = minimum_realization_count(
        priors,
        compact_familywise_power=compact_power,
        minimum_joint_power=minimum_joint,
    )
    continuum_power = conservative_familywise_power(
        priors,
        _CONTINUUM_IMAGE_COUNT,
    )
    combined_power = prospective_joint_power(continuum_power, compact_power)
    if (
        minimum != power.get("minimum_continuum_realization_count")
        or power.get("selected_continuum_realization_count")
        != _CONTINUUM_IMAGE_COUNT
        or power.get("continuum_realizations_per_geometry")
        != _CONTINUUM_PER_GEOMETRY
        or power.get("compact_realization_count") != _COMPACT_IMAGE_COUNT
        or abs(
            continuum_power
            - float(power["continuum_familywise_power_lower_bound"])
        )
        > _POWER_TOLERANCE
        or abs(
            combined_power
            - float(power["combined_familywise_power_lower_bound"])
        )
        > _POWER_TOLERANCE
        or combined_power < minimum_joint
    ):
        raise ValueError("post-correction power audit does not recompute")


def load_post_correction_population(path: Path) -> dict[str, Any]:
    """Validate the approved science, power, and seed identity freeze."""
    if file_sha256(path) != _POPULATION_SHA256:
        raise ValueError("post-correction population checksum changed")
    document = json_object(path)
    require_exact_keys(
        document,
        frozenset(
            {
                "candidate",
                "closed_campaign_policy",
                "contract_id",
                "evidence",
                "execution_authorized",
                "finder_output_generated",
                "finder_output_opened",
                "generator",
                "next_action",
                "optimization_authorized",
                "population_audit",
                "populations",
                "power_audit",
                "qualification_opened",
                "schema_version",
                "scientific_approval",
                "status",
                "step_three_authorized",
            }
        ),
        description="post-correction population",
    )
    candidate = cast(dict[str, Any], document.get("candidate"))
    approval = cast(dict[str, Any], document.get("scientific_approval"))
    evidence = cast(dict[str, Any], document.get("evidence"))
    audit = cast(dict[str, Any], document.get("population_audit"))
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-external-post-correction-population"
        or document.get("status")
        != "scientifically-approved-and-frozen-before-output"
        or approval
        != {
            "reviewer": "Gemma Danks",
            "approved_on": "2026-08-16",
            "scope": (
                "candidate-and-powered-design-for-freezing-fresh-external-"
                "identities-only"
            ),
        }
        or candidate.get("revision") != _CANDIDATE_REVISION
        or candidate.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or candidate.get("configuration_sha256") != _CONFIGURATION_SHA256
        or evidence.get("cumulative_ledger_sha256")
        != _CUMULATIVE_LEDGER_SHA256
        or evidence.get("power_review_sha256") != _POWER_REVIEW_SHA256
        or audit.get("new_seed_count") != _IMAGE_COUNT
        or audit.get("reserved_development_seed_count")
        != _RESERVED_DEVELOPMENT_SEED_COUNT
        or audit.get("seed_disjoint") is not True
        or document.get("execution_authorized") is not False
        or document.get("finder_output_generated") is not False
        or document.get("finder_output_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
    ):
        raise ValueError("post-correction population state is invalid")
    root = path.resolve().parents[2]
    if source_tree_sha256(root) != _SOURCE_TREE_SHA256:
        raise ValueError("post-correction source tree changed")
    generator = cast(dict[str, Any], document["generator"])
    if file_sha256(root / generator["relative_path"]) != generator["sha256"]:
        raise ValueError("post-correction population generator changed")
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
        raise ValueError("post-correction frozen population changed")
    for item in populations:
        if file_sha256(root / item["manifest"]) != item["manifest_sha256"]:
            raise ValueError("post-correction manifest checksum changed")
    _validate_power(cast(dict[str, Any], document["power_audit"]))
    return document


def load_post_correction_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Expose unchanged science policy over the fresh powered population."""
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
    require_exact_keys(
        document, required, description="post-correction protocol"
    )
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
        raise ValueError("post-correction protocol state is invalid")
    root = path.resolve().parents[2]
    base_path = (
        root / "config/contracts/phase-5-external-post-failure-comparison.json"
    )
    if (
        document.get("base_protocol_path")
        != "config/contracts/phase-5-external-post-failure-comparison.json"
        or document.get("base_protocol_sha256") != file_sha256(base_path)
        or document.get("population_contract_path") != _POPULATION_PATH
        or document.get("population_contract_sha256") != _POPULATION_SHA256
    ):
        raise ValueError("post-correction protocol ancestry changed")
    load_post_correction_population(root / _POPULATION_PATH)
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
        raise ValueError("post-correction protocol population changed")
    _install_historical_source_view()
    base = _BASE["load_post_failure_protocol"](base_path)
    compatible = tuple(
        old.model_copy(update=new)
        for old, new in zip(base.populations, populations, strict=True)
    )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        base.model_copy(update={"populations": compatible}),
    )


@dataclass(frozen=True, slots=True)
class PostCorrectionRunnerArtifact:
    """One checksum-bound post-correction runner wrapper."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class PostCorrectionExecutionDecision:
    """Authorization view consumed by unchanged campaign mechanics."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    execution_concurrency: int
    runners: tuple[PostCorrectionRunnerArtifact, ...]
    preflight_review_sha256: str
    named_review: str
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def _preflight_review_binding(
    document: dict[str, Any],
    root: Path,
    *,
    pending: bool,
) -> str:
    """Validate pending or exact approved preflight review identity."""
    value = document.get("preflight_review_sha256")
    if pending:
        if value != "pending":
            raise ValueError("pending post-correction review binding changed")
        return "pending"
    review = load_post_correction_preflight_review(root / _PREFLIGHT_REVIEW)
    if (
        not isinstance(value, str)
        or value != file_sha256(root / _PREFLIGHT_REVIEW)
        or value not in cast(str, document.get("named_review"))
        or review.get("status") != "ready-for-named-execution-approval"
    ):
        raise ValueError("approved post-correction review binding changed")
    return value


def load_post_correction_execution_decision(
    path: Path,
) -> PostCorrectionExecutionDecision:
    """Validate pending or named post-correction authorization."""
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
            "implementation_commit",
            "named_review",
            "next_action",
            "one_look_opened",
            "optimization_authorized",
            "population_contract_sha256",
            "power_review_sha256",
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
    )
    require_exact_keys(
        document, required, description="post-correction decision"
    )
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
        or document.get("preflight_review_path") != _PREFLIGHT_REVIEW
        or document.get("one_look_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
    ):
        raise ValueError("post-correction decision identity is invalid")
    expected_state = (
        (
            "await-named-one-look-approval",
            False,
            "pending",
            "obtain-named-one-look-approval-before-no-write-preflight",
        )
        if pending
        else (
            "authorize-one-terminal-post-correction-comparison",
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
        raise ValueError("post-correction authorization state is invalid")
    root = path.resolve().parents[2]
    protocol_path = (
        root
        / "config/contracts/phase-5-external-post-correction-comparison.json"
    )
    if document.get("protocol_sha256") != file_sha256(protocol_path):
        raise ValueError("post-correction decision protocol changed")
    review_sha256 = _preflight_review_binding(document, root, pending=pending)
    runners = document.get("runners")
    if not isinstance(runners, list):
        raise ValueError("post-correction runner identities are absent")
    observed_paths = tuple(
        item.get("relative_path") for item in runners if isinstance(item, dict)
    )
    if observed_paths != _RUNNER_PATHS:
        raise ValueError("post-correction runner order changed")
    records = tuple(
        PostCorrectionRunnerArtifact(
            relative_path=cast(str, item["relative_path"]),
            sha256=cast(str, item["sha256"]),
        )
        for item in runners
    )
    for item in records:
        if file_sha256(root / item.relative_path) != item.sha256:
            raise ValueError(
                f"post-correction runner changed: {item.relative_path}"
            )
    return PostCorrectionExecutionDecision(
        protocol_sha256=cast(str, document["protocol_sha256"]),
        candidate_review_sha256=_CANDIDATE_REVIEW_SHA256,
        implementation_commit=_CANDIDATE_REVISION,
        source_tree_sha256=_SOURCE_TREE_SHA256,
        hebog_container_image_digest=_HEBOG_IMAGE_DIGEST,
        hebog_dependency_inventory_sha256=_HEBOG_INVENTORY_SHA256,
        pybdsf_ncores=_PYBDSF_NCORES,
        execution_concurrency=_EXECUTION_CONCURRENCY,
        runners=records,
        preflight_review_sha256=review_sha256,
        named_review=cast(str, document["named_review"]),
        execution_authorized=cast(bool, document["execution_authorized"]),
        one_look_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )


def _authorization_transitioned(root: Path) -> bool:
    """Return whether the pending decision received named approval."""
    decision = json_object(
        root / "config/contracts/"
        "phase-5-external-post-correction-execution-decision.json"
    )
    status = decision.get("status")
    if status not in {
        "awaiting-named-execution-approval",
        "reviewed-before-external-output",
    }:
        raise ValueError("post-correction authorization state is invalid")
    return status == "reviewed-before-external-output"


def load_post_correction_endpoint_registry(path: Path) -> dict[str, Any]:
    """Validate the fresh composition and inherit every endpoint policy."""
    document = json_object(path)
    required = frozenset(
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
            "observable_compiler_path",
            "observable_compiler_sha256",
            "observable_measurement_path",
            "observable_measurement_sha256",
            "population_contract_path",
            "population_contract_sha256",
            "protocol_path",
            "protocol_sha256",
            "protocol_verifier_path",
            "protocol_verifier_sha256",
            "registry_id",
            "schema_version",
            "status",
        }
    )
    require_exact_keys(
        document, required, description="post-correction registry"
    )
    if (
        document.get("schema_version") != 1
        or document.get("registry_id")
        != "phase-5-external-post-correction-endpoint-registry"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
    ):
        raise ValueError("post-correction registry state is invalid")
    root = path.resolve().parents[2]
    base_path = (
        root / "config/contracts/"
        "phase-5-external-post-failure-endpoint-registry.json"
    )
    if (
        document.get("base_registry_path")
        != "config/contracts/"
        "phase-5-external-post-failure-endpoint-registry.json"
        or document.get("base_registry_sha256") != file_sha256(base_path)
    ):
        raise ValueError("post-correction registry ancestry changed")
    approval_dependent = {
        "config/contracts/"
        "phase-5-external-post-correction-execution-decision.json"
    }
    transitioned = _authorization_transitioned(root)
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "post-correction protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "post-correction population",
        ),
        (
            "continuum_manifest_path",
            "continuum_manifest_sha256",
            "post-correction continuum manifest",
        ),
        (
            "compact_manifest_path",
            "compact_manifest_sha256",
            "post-correction compact manifest",
        ),
        (
            "execution_decision_path",
            "execution_decision_sha256",
            "post-correction decision",
        ),
        ("launcher_path", "launcher_sha256", "post-correction launcher"),
        ("compiler_path", "compiler_sha256", "post-correction compiler"),
        (
            "protocol_verifier_path",
            "protocol_verifier_sha256",
            "post-correction verifier",
        ),
        (
            "compiler_accelerator_path",
            "compiler_accelerator_sha256",
            "compiler accelerator",
        ),
        (
            "observable_measurement_path",
            "observable_measurement_sha256",
            "observable measurement",
        ),
        (
            "observable_compiler_path",
            "observable_compiler_sha256",
            "observable compiler",
        ),
    ):
        relative = document.get(path_key)
        if relative in approval_dependent and transitioned:
            continue
        require_bound_file(
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    _install_historical_source_view()
    base = _BASE["load_post_failure_endpoint_registry"](base_path)
    compatible = dict(base)
    compatible.update(document)
    return compatible


def load_post_correction_preflight_review(
    path: Path,
) -> dict[str, Any]:
    """Validate the exact programs and four runtime identities for review."""
    document = json_object(path)
    required = frozenset(
        {
            "authorization",
            "execution_authorized",
            "identity_artifacts",
            "implementation",
            "output_paths",
            "population",
            "resource_policy",
            "review_id",
            "reviewed_at",
            "runtime_images",
            "runtime_probe",
            "schema_version",
            "scientific_products_opened",
            "status",
            "storage",
        }
    )
    require_exact_keys(
        document, required, description="post-correction review"
    )
    if (
        document.get("schema_version") != 1
        or document.get("review_id")
        != "phase-5-external-post-correction-preflight-review"
        or document.get("status")
        not in {
            "identities-frozen-storage-blocked-before-named-execution-approval",
            "ready-for-named-execution-approval",
        }
        or document.get("execution_authorized") is not False
        or document.get("scientific_products_opened") is not False
    ):
        raise ValueError("post-correction review state is invalid")
    implementation = cast(dict[str, Any], document.get("implementation"))
    population = cast(dict[str, Any], document.get("population"))
    authorization = cast(dict[str, Any], document.get("authorization"))
    storage = cast(dict[str, Any], document.get("storage"))
    output_paths = cast(dict[str, Any], document.get("output_paths"))
    storage_ready = document.get("status") == (
        "ready-for-named-execution-approval"
    )
    if (
        implementation.get("candidate_revision") != _CANDIDATE_REVISION
        or implementation.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or implementation.get("configuration_sha256") != _CONFIGURATION_SHA256
        or population
        != {
            "image_count": _IMAGE_COUNT,
            "continuum_image_count": _CONTINUUM_IMAGE_COUNT,
            "compact_blend_image_count": _COMPACT_IMAGE_COUNT,
            "binding_run_count": _BINDING_RUN_COUNT,
            "terminal_run_count": _RUN_COUNT,
        }
        or storage.get("minimum_available_gib") != _MINIMUM_AVAILABLE_GIB
        or storage.get("passed") is not storage_ready
        or (storage.get("observed_available_gib", 0) >= _MINIMUM_AVAILABLE_GIB)
        is not storage_ready
        or output_paths.get("both_absent") is not True
        or authorization.get("required_next_decision")
        != (
            "named-one-look-approval-bound-to-this-review-and-four-runtimes"
            if storage_ready
            else "restore-storage-headroom-before-named-one-look-review"
        )
    ):
        raise ValueError("post-correction review binding changed")
    runtime_images = document.get("runtime_images")
    if not isinstance(runtime_images, list):
        raise ValueError("post-correction runtime identities are absent")
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
        raise ValueError("post-correction runtime identities changed")
    identities = document.get("identity_artifacts")
    if not isinstance(identities, list) or not identities:
        raise ValueError("post-correction program identities are absent")
    root = path.resolve().parents[2]
    transitioned = _authorization_transitioned(root)
    approval_dependent = {
        "config/contracts/"
        "phase-5-external-post-correction-execution-decision.json",
        "config/contracts/"
        "phase-5-external-post-correction-endpoint-registry.json",
        "config/contracts/phase-5-external-post-correction-evaluation.json",
    }
    for identity in identities:
        if not isinstance(identity, dict):
            raise ValueError("post-correction program identity is malformed")
        relative = identity.get("relative_path")
        expected = identity.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("post-correction program identity changed")
        if (
            relative not in approval_dependent or not transitioned
        ) and file_sha256(root / relative) != expected:
            raise ValueError("post-correction program identity changed")
    return document


def post_correction_campaign_request_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Replace only the approved population literals on a request model."""
    return create_model(
        f"PostCorrection{historical_model.__name__}",
        __base__=historical_model,
        image_count=(Literal[2488], ...),
        run_count=(Literal[12440], ...),
    )


def post_correction_terminal_result_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Replace only the approved population literals on a result model."""
    return post_correction_campaign_request_model(historical_model)
