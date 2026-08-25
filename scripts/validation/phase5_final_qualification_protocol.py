#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate the unopened final Phase 5 qualification composition."""

from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, create_model

from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol

_ROOT = Path(__file__).parents[2]
_POPULATION_PATH = (
    "config/contracts/phase-5-final-qualification-population.json"
)
_POPULATION_SHA256 = (
    "4a52f55114962d24d6371b166d393c3421a74156fa1c48305931fb39a631e5ac"
)
_MANIFEST_PATH = "config/datasets/phase-5-final-qualification-continuum.json"
_MANIFEST_SHA256 = (
    "7c67127e828a92bc100299cf9ffecd13851e485c4be9e95866e2d0827ebb80df"
)
_PROTOCOL_PATH = "config/contracts/phase-5-final-qualification-comparison.json"
_DECISION_PATH = (
    "config/contracts/phase-5-final-qualification-execution-decision.json"
)
_REGISTRY_PATH = (
    "config/contracts/phase-5-final-qualification-endpoint-registry.json"
)
_IDENTITY_REVIEW_PATH = (
    "config/contracts/phase-5-final-qualification-identity-review.json"
)
_EVALUATION_PATH = (
    "config/contracts/phase-5-final-qualification-evaluation.json"
)
_CANDIDATE_REVISION = "90626641c8705ba9d55fdea02a705983528b8aa0"
_SOURCE_TREE_SHA256 = (
    "e4307246efa7db3ec941b3906f8ce443404b8b84cdc78aa89881e738850cdf8a"
)
_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_IMAGE_COUNT = 1688
_RUN_COUNT = 8440
_BINDING_RUN_COUNT = 5064
_GEOMETRY_COUNT = 4
_REALIZATIONS_PER_GEOMETRY = 422
_COMPACT_RECORD_COUNT = 2
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_HEBOG_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
)
_RUNTIME_IMAGES = (
    (
        "hebog",
        "e7f1ce9e9b26f6e29a14e75833bcec52e56b95ce58102f2905c3623f9902632c",
        "sha256:132f1c3da7f353edc642e9bc2e6108aff8a1dbf6f9a5556f50144db864114363",
        _HEBOG_INVENTORY_SHA256,
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
_RUNNER_PATHS = (
    "scripts/benchmark/run_phase5_final_qualification_hebog.py",
    "scripts/benchmark/run_phase5_final_qualification_pybdsf.py",
    "scripts/benchmark/run_phase5_final_qualification_aegean.py",
)
_RECOVERY = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_recovery_protocol.py")
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


def _install_closed_recovery_view() -> None:
    """Validate the inherited recovery policy against its historical tree."""
    loader = _RECOVERY["load_recovery_population"]

    def historical_source_tree(_root: Path) -> str:
        return cast(str, _RECOVERY["_SOURCE_TREE_SHA256"])

    loader.__globals__["source_tree_sha256"] = historical_source_tree


def load_final_qualification_population(path: Path) -> dict[str, Any]:
    """Validate the named population freeze and closed compact evidence."""
    if file_sha256(path) != _POPULATION_SHA256:
        raise ValueError("final qualification population checksum changed")
    document = json_object(path)
    candidate = cast(dict[str, Any], document.get("candidate"))
    population = cast(dict[str, Any], document.get("population"))
    compact = cast(dict[str, Any], document.get("compact_evidence"))
    records = compact.get("records")
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-final-qualification-population"
        or document.get("status")
        != "scientifically-approved-and-frozen-before-output"
        or candidate
        != {
            "configuration_sha256": _CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _SOURCE_TREE_SHA256,
        }
        or population.get("manifest") != _MANIFEST_PATH
        or population.get("manifest_sha256") != _MANIFEST_SHA256
        or population.get("image_count") != _IMAGE_COUNT
        or population.get("geometry_count") != _GEOMETRY_COUNT
        or population.get("realizations_per_geometry")
        != _REALIZATIONS_PER_GEOMETRY
        or compact.get("fresh_compact_lane_required") is not False
        or compact.get("policy")
        != "bind-closed-evidence-without-pooling-or-rescoring"
        or not isinstance(records, list)
        or len(records) != _COMPACT_RECORD_COUNT
        or any(item.get("passed") is not True for item in records)
        or document.get("execution_authorized") is not False
        or document.get("qualification_opened") is not False
        or document.get("finder_output_generated") is not False
    ):
        raise ValueError("final qualification population state is invalid")
    root = path.resolve().parents[2]
    if file_sha256(root / _MANIFEST_PATH) != _MANIFEST_SHA256:
        raise ValueError("final qualification manifest changed")
    for record in records:
        if file_sha256(root / cast(str, record["path"])) != record["sha256"]:
            raise ValueError("closed compact evidence changed")
    return document


def load_final_qualification_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Expose unchanged continuum gates over the final qualification lane."""
    document = json_object(path)
    if (
        document.get("schema_version") != 1
        or document.get("contract_id")
        != "phase-5-final-qualification-comparison"
        or document.get("status") != "frozen-before-qualification-output"
        or document.get("candidate_configuration_sha256")
        != _CONFIGURATION_SHA256
        or document.get("closed_compact_evidence_only") is not True
        or document.get("execution_authorized") is not False
        or document.get("qualification_opened") is not False
        or document.get("cutover_authorized") is not False
    ):
        raise ValueError("final qualification protocol state is invalid")
    root = path.resolve().parents[2]
    base_relative = (
        "config/contracts/phase-5-external-recovery-comparison.json"
    )
    if (
        document.get("base_protocol_path") != base_relative
        or document.get("base_protocol_sha256")
        != file_sha256(root / base_relative)
        or document.get("population_contract_path") != _POPULATION_PATH
        or document.get("population_contract_sha256") != _POPULATION_SHA256
    ):
        raise ValueError("final qualification protocol ancestry changed")
    load_final_qualification_population(root / _POPULATION_PATH)
    populations = document.get("populations")
    expected = [
        {
            "image_count": _IMAGE_COUNT,
            "lane": "continuum",
            "manifest": _MANIFEST_PATH,
            "manifest_sha256": _MANIFEST_SHA256,
        }
    ]
    if populations != expected:
        raise ValueError("final qualification population changed")
    _install_closed_recovery_view()
    base = _RECOVERY["load_recovery_protocol"](root / base_relative)
    compatible_population = base.populations[0].model_copy(update=expected[0])
    return cast(
        PhaseFiveExternalComparisonProtocol,
        base.model_copy(update={"populations": (compatible_population,)}),
    )


@dataclass(frozen=True, slots=True)
class FinalQualificationRunnerArtifact:
    """One checksum-bound final qualification runner."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class FinalQualificationExecutionDecision:
    """Pending authorization consumed by generic campaign mechanics."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    execution_concurrency: int
    runners: tuple[FinalQualificationRunnerArtifact, ...]
    identity_review_sha256: str
    named_review: str
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def load_final_qualification_execution_decision(
    path: Path,
) -> FinalQualificationExecutionDecision:
    """Validate pending or named final-qualification authorization."""
    document = json_object(path)
    pending = document.get("status") == "awaiting-named-execution-approval"
    approved = document.get("status") == "reviewed-before-qualification-output"
    if (
        document.get("schema_version") != 1
        or document.get("decision_id")
        != "phase-5-final-qualification-execution-decision"
        or pending == approved
        or document.get("implementation_commit") != _CANDIDATE_REVISION
        or document.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or document.get("candidate_configuration_sha256")
        != _CONFIGURATION_SHA256
        or document.get("population_contract_sha256") != _POPULATION_SHA256
        or document.get("candidate_review_sha256") != _CANDIDATE_REVIEW_SHA256
        or document.get("hebog_container_image_digest")
        != _RUNTIME_IMAGES[0][2]
        or document.get("hebog_dependency_inventory_sha256")
        != _HEBOG_INVENTORY_SHA256
        or document.get("pybdsf_ncores") != _PYBDSF_NCORES
        or document.get("execution_concurrency") != _EXECUTION_CONCURRENCY
        or document.get("identity_review_path") != _IDENTITY_REVIEW_PATH
        or document.get("one_look_opened") is not False
        or document.get("qualification_opened") is not False
        or document.get("cutover_authorized") is not False
    ):
        raise ValueError("final qualification decision state is invalid")
    expected_state = (
        (
            "await-named-one-look-approval",
            False,
            "pending",
            "obtain-named-one-look-approval-before-no-write-preflight",
        )
        if pending
        else (
            "authorize-one-terminal-final-qualification",
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
        raise ValueError("final qualification authorization state is invalid")
    root = path.resolve().parents[2]
    if document.get("protocol_sha256") != file_sha256(root / _PROTOCOL_PATH):
        raise ValueError("final qualification decision protocol changed")
    runners = document.get("runners")
    if (
        not isinstance(runners, list)
        or tuple(item.get("relative_path") for item in runners)
        != _RUNNER_PATHS
    ):
        raise ValueError("final qualification runner order changed")
    records = tuple(
        FinalQualificationRunnerArtifact(
            relative_path=cast(str, item["relative_path"]),
            sha256=cast(str, item["sha256"]),
        )
        for item in runners
    )
    for item in records:
        if file_sha256(root / item.relative_path) != item.sha256:
            raise ValueError(
                f"final qualification runner changed: {item.relative_path}"
            )
    if pending:
        if document.get("identity_review_sha256") != "pending":
            raise ValueError("pending qualification review binding changed")
        review_sha256 = "pending"
    else:
        review_path = root / _IDENTITY_REVIEW_PATH
        review_sha256 = file_sha256(review_path)
        named_review = document.get("named_review")
        if (
            document.get("identity_review_sha256") != review_sha256
            or not isinstance(named_review, str)
            or review_sha256 not in named_review
            or load_final_qualification_identity_review(review_path).get(
                "status"
            )
            != "ready-for-named-execution-approval"
        ):
            raise ValueError("approved qualification review binding changed")
    return FinalQualificationExecutionDecision(
        protocol_sha256=cast(str, document["protocol_sha256"]),
        candidate_review_sha256=_CANDIDATE_REVIEW_SHA256,
        implementation_commit=_CANDIDATE_REVISION,
        source_tree_sha256=_SOURCE_TREE_SHA256,
        hebog_container_image_digest=_RUNTIME_IMAGES[0][2],
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


def load_final_qualification_endpoint_registry(path: Path) -> dict[str, Any]:
    """Validate the exact prospective final qualification composition."""
    document = json_object(path)
    if (
        document.get("schema_version") != 1
        or document.get("registry_id")
        != "phase-5-final-qualification-endpoint-registry"
        or document.get("status") != "frozen-before-qualification-output"
        or document.get("closed_compact_evidence_only") is not True
    ):
        raise ValueError("final qualification registry state is invalid")
    root = path.resolve().parents[2]
    base_relative = (
        "config/contracts/phase-5-external-recovery-endpoint-registry.json"
    )
    if document.get("base_registry_path") != base_relative or document.get(
        "base_registry_sha256"
    ) != file_sha256(root / base_relative):
        raise ValueError("final qualification registry ancestry changed")
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "qualification protocol"),
        (
            "population_contract_path",
            "population_contract_sha256",
            "population",
        ),
        ("continuum_manifest_path", "continuum_manifest_sha256", "manifest"),
        ("execution_decision_path", "execution_decision_sha256", "decision"),
        ("launcher_path", "launcher_sha256", "launcher"),
        ("compiler_path", "compiler_sha256", "compiler"),
        ("evaluator_path", "evaluator_sha256", "evaluator"),
        ("protocol_verifier_path", "protocol_verifier_sha256", "verifier"),
        (
            "compiler_accelerator_path",
            "compiler_accelerator_sha256",
            "compiler accelerator",
        ),
        (
            "candidate_adapter_path",
            "candidate_adapter_sha256",
            "candidate adapter",
        ),
    ):
        require_bound_file(
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    _install_closed_recovery_view()
    base = _RECOVERY["load_recovery_endpoint_registry"](root / base_relative)
    compatible = dict(base)
    compatible.update(document)
    return compatible


def load_final_qualification_identity_review(path: Path) -> dict[str, Any]:
    """Validate frozen programs and runtimes without authorizing them."""
    document = json_object(path)
    if (
        document.get("schema_version") != 1
        or document.get("review_id")
        != "phase-5-final-qualification-identity-review"
        or document.get("status") != "ready-for-named-execution-approval"
        or document.get("execution_authorized") is not False
        or document.get("qualification_opened") is not False
        or document.get("scientific_products_opened") is not False
    ):
        raise ValueError("final qualification identity review is invalid")
    if document.get("implementation") != {
        "candidate_revision": _CANDIDATE_REVISION,
        "configuration_sha256": _CONFIGURATION_SHA256,
        "source_tree_sha256": _SOURCE_TREE_SHA256,
    } or document.get("population") != {
        "binding_run_count": _BINDING_RUN_COUNT,
        "continuum_image_count": _IMAGE_COUNT,
        "image_count": _IMAGE_COUNT,
        "terminal_run_count": _RUN_COUNT,
    }:
        raise ValueError("final qualification review binding changed")
    runtimes = document.get("runtime_images")
    if (
        not isinstance(runtimes, list)
        or tuple(
            (
                item.get("finder_id"),
                item.get("image_id"),
                item.get("digest"),
                item.get("dependency_inventory_sha256"),
            )
            for item in runtimes
        )
        != _RUNTIME_IMAGES
    ):
        raise ValueError("final qualification runtime identities changed")
    identities = document.get("identity_artifacts")
    if not isinstance(identities, list) or not identities:
        raise ValueError("final qualification program identities are absent")
    root = path.resolve().parents[2]
    decision = json_object(root / _DECISION_PATH)
    transitioned = (
        decision.get("status") == "reviewed-before-qualification-output"
    )
    if decision.get("status") not in {
        "awaiting-named-execution-approval",
        "reviewed-before-qualification-output",
    }:
        raise ValueError("final qualification authorization state is invalid")
    approval_dependent = {
        _DECISION_PATH,
        _REGISTRY_PATH,
        _EVALUATION_PATH,
    }
    for identity in identities:
        relative_path = identity.get("relative_path")
        expected_sha256 = identity.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(
            expected_sha256, str
        ):
            raise ValueError("final qualification program identity changed")
        if (
            relative_path not in approval_dependent or not transitioned
        ) and file_sha256(root / relative_path) != expected_sha256:
            raise ValueError("final qualification program identity changed")
    return document


def final_qualification_campaign_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Replace only the approved final population literals."""
    return create_model(
        f"FinalQualification{historical_model.__name__}",
        __base__=historical_model,
        image_count=(Literal[1688], ...),
        run_count=(Literal[8440], ...),
    )
