#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate the approved fresh Phase 5 post-failure composition."""

from __future__ import annotations

import hashlib
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, create_model

from hebog.validation.campaign_parallel import (
    concurrent_campaign_request_model,
)
from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol
from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).parents[2]
_CONFIRMATION_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_confirmation_protocol.py")
)
_FREEZER = runpy.run_path(
    str(
        _ROOT / "scripts/validation/"
        "freeze_phase5_external_post_failure_population.py"
    )
)
_PROTOCOL_ID = "phase-5-external-post-failure-comparison"
_DECISION_ID = "phase-5-external-post-failure-execution-decision"
_PREFLIGHT_REVIEW = (
    "config/contracts/phase-5-external-post-failure-preflight-review.json"
)
_POPULATION_PATH = (
    "config/contracts/phase-5-external-post-failure-population.json"
)
_POPULATION_SHA256 = (
    "42c3d07c2aeb74caf00f6e888a9cf3c6cecda3f05decb820db7e18cb646d87fd"
)
_CONTINUUM_MANIFEST = (
    "config/datasets/phase-5-external-post-failure-continuum.json"
)
_COMPACT_MANIFEST = (
    "config/datasets/phase-5-external-post-failure-compact-blend.json"
)
_CONTINUUM_SHA256 = (
    "4ce811e8aebc26b858473eb4473abba1b3bb5a916acb2ee6b645441723322e77"
)
_COMPACT_SHA256 = (
    "8c39320199bdca5fccb478599da286fad9ae0a2bec5fbd2fecfe595cabc49e48"
)
_IMPLEMENTATION_COMMIT = "63e4b5886a3f5acb75125d258f5b71c13ca4eeaf"
_SOURCE_TREE_SHA256 = (
    "864d8f2b06cc8c561c8d1f7e2b2f9a511baa5e170b91150bf4c6fa5255002d75"
)
_HEBOG_IMAGE_DIGEST = (
    "sha256:4a7bc97509845f08c9d272ffe21d834eba8c9e54aaf2c291945e1cae56057970"
)
_HEBOG_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
)
_CANDIDATE_REVIEW_SHA256 = (
    "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
)
_PRE_REVIEW_SHA256 = (
    "31ca691e1c5fc7ca905e0ad874906533ed55b7a4746c68543457951264aba07d"
)
_RUNNERS = (
    (
        "scripts/benchmark/run_phase5_external_post_failure_hebog.py",
        "c9eb67ba5b0c2d5b2e91b3d854720a0694bef10c6a11f80121bda2f987e3fab8",
    ),
    (
        "scripts/benchmark/run_phase5_external_post_failure_pybdsf.py",
        "a0ea3d8731e396c28f40ab4fc7b80c274ab07416560dead7d2d40ef4bc860365",
    ),
    (
        "scripts/benchmark/run_phase5_external_post_failure_aegean.py",
        "18d8570cd11bf1eddd2261ba69f61902a4420c470f2341d8a18c6d86f9332a77",
    ),
)
_PYBDSF_NCORES = 4
_EXECUTION_CONCURRENCY = 2
_MINIMUM_AVAILABLE_GIB = 120.0
_GIB_ROUNDING_TOLERANCE = 0.5e-6


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


def load_post_failure_population(path: Path) -> dict[str, Any]:
    """Validate the approved power, population, and science identity freeze."""
    if file_sha256(path) != _POPULATION_SHA256:
        raise ValueError("post-failure population checksum changed")
    document = json_object(path)
    _FREEZER["PostFailurePopulationFreeze"].model_validate(document)
    root = path.resolve().parents[2]
    if source_tree_sha256(root) != _SOURCE_TREE_SHA256:
        raise ValueError("post-failure source tree changed")
    populations = cast(list[dict[str, Any]], document["populations"])
    expected = (
        ("continuum", _CONTINUUM_MANIFEST, _CONTINUUM_SHA256, 1600),
        ("compact-blend", _COMPACT_MANIFEST, _COMPACT_SHA256, 800),
    )
    if (
        tuple(
            (
                item["lane"],
                item["manifest"],
                item["manifest_sha256"],
                item["image_count"],
            )
            for item in populations
        )
        != expected
    ):
        raise ValueError("post-failure frozen population changed")
    for item in populations:
        if file_sha256(root / item["manifest"]) != item["manifest_sha256"]:
            raise ValueError("post-failure manifest checksum changed")
    source = cast(dict[str, Any], document["source_binding"])
    for field in (
        "observable_measurement",
        "observable_compiler",
        "candidate_runner",
    ):
        artifact = cast(dict[str, Any], source[field])
        if file_sha256(root / artifact["relative_path"]) != artifact["sha256"]:
            raise ValueError("post-failure science artifact changed")
    return document


def load_post_failure_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Expose inherited gates over only the approved fresh populations."""
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
                "population_contract_path",
                "population_contract_sha256",
                "qualification_opened",
                "schema_version",
                "status",
                "step_three_authorized",
            }
        ),
        description="post-failure external protocol",
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
        raise ValueError("post-failure external protocol state is invalid")
    root = path.resolve().parents[2]
    base_path = (
        root / "config/contracts/phase-5-external-confirmation-comparison.json"
    )
    if (
        document.get("base_protocol_path")
        != "config/contracts/phase-5-external-confirmation-comparison.json"
        or document.get("base_protocol_sha256") != file_sha256(base_path)
        or document.get("population_contract_path") != _POPULATION_PATH
        or document.get("population_contract_sha256") != _POPULATION_SHA256
    ):
        raise ValueError("post-failure protocol ancestry changed")
    load_post_failure_population(root / _POPULATION_PATH)
    populations = document.get("populations")
    expected = (
        ("continuum", _CONTINUUM_MANIFEST, _CONTINUUM_SHA256, 1600),
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
        raise ValueError("post-failure protocol population changed")
    base = _CONFIRMATION_HELPERS["load_confirmation_protocol"](base_path)
    compatible = tuple(
        old.model_copy(update=new)
        for old, new in zip(base.populations, populations, strict=True)
    )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        base.model_copy(update={"populations": compatible}),
    )


@dataclass(frozen=True, slots=True)
class PostFailureRunnerArtifact:
    """One checksum-bound post-failure runner wrapper."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class PostFailureExecutionDecision:
    """Authorization view consumed by the unchanged campaign mechanics."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    execution_concurrency: int
    runners: tuple[PostFailureRunnerArtifact, ...]
    preflight_review_sha256: str
    named_review: str
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def post_failure_preflight_review_sha256(
    document: dict[str, Any],
    root: Path,
    *,
    pending: bool,
) -> str:
    """Validate the asymmetric pending/approved review binding."""
    value = document.get("preflight_review_sha256")
    if pending:
        if value != "pending":
            raise ValueError("pending post-failure review binding changed")
        return "pending"
    review = load_post_failure_preflight_review(root / _PREFLIGHT_REVIEW)
    if (
        not isinstance(value, str)
        or value != file_sha256(root / _PREFLIGHT_REVIEW)
        or value not in cast(str, document["named_review"])
        or review.get("status") != "ready-for-named-execution-approval"
        or review.get("named_execution_approval_recommended") is not True
    ):
        raise ValueError("approved post-failure review binding changed")
    return value


def load_post_failure_preflight_review(path: Path) -> dict[str, Any]:
    """Validate identities and readiness without opening science."""
    document = json_object(path)
    require_exact_keys(
        document,
        frozenset(
            {
                "execution_authorized",
                "identity_artifacts",
                "implementation",
                "named_execution_approval_recommended",
                "next_action",
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
        ),
        description="post-failure preflight review",
    )
    status = document.get("status")
    if (
        document.get("schema_version") != 1
        or document.get("review_id")
        != "phase-5-external-post-failure-preflight-review"
        or status
        not in {
            "blocked-before-named-execution-approval",
            "ready-for-named-execution-approval",
        }
        or document.get("execution_authorized") is not False
        or document.get("scientific_products_opened") is not False
    ):
        raise ValueError("post-failure preflight review state is invalid")
    storage = document.get("storage")
    output_paths = document.get("output_paths")
    if not isinstance(storage, dict) or not isinstance(output_paths, dict):
        raise ValueError("post-failure operational review is incomplete")
    require_exact_keys(
        storage,
        frozenset(
            {
                "minimum_available_gib",
                "observed_available_gib",
                "observed_available_kib",
                "passed",
                "scaling_basis",
            }
        ),
        description="post-failure storage observation",
    )
    minimum_gib = storage.get("minimum_available_gib")
    observed_gib = storage.get("observed_available_gib")
    observed_kib = storage.get("observed_available_kib")
    if (
        type(minimum_gib) not in {int, float}
        or type(observed_gib) not in {int, float}
        or type(observed_kib) is not int
        or minimum_gib != _MINIMUM_AVAILABLE_GIB
        or observed_gib < 0
        or observed_kib < 0
        or abs(observed_gib - observed_kib / (1024 * 1024))
        > _GIB_ROUNDING_TOLERANCE
        or storage.get("scaling_basis")
        != "prior-60-gib-1400-image-headroom-plus-1000-additional-"
        "continuum-images"
    ):
        raise ValueError("post-failure storage observation is invalid")
    observed_storage_passed = observed_gib >= minimum_gib
    ready = status == "ready-for-named-execution-approval"
    if (
        storage.get("passed") is not observed_storage_passed
        or observed_storage_passed is not ready
        or output_paths.get("both_absent") is not True
        or document.get("named_execution_approval_recommended") is not ready
    ):
        raise ValueError(
            "post-failure storage observation and readiness are inconsistent"
        )
    identities = document.get("identity_artifacts")
    if not isinstance(identities, list) or not identities:
        raise ValueError("post-failure preflight identities are absent")
    root = path.resolve().parents[2]
    for identity in identities:
        if not isinstance(identity, dict):
            raise ValueError("post-failure preflight identity is malformed")
        require_exact_keys(
            identity,
            frozenset({"relative_path", "sha256"}),
            description="post-failure preflight artifact",
        )
        relative = identity.get("relative_path")
        expected = identity.get("sha256")
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or file_sha256(root / relative) != expected
        ):
            raise ValueError("post-failure preflight artifact changed")
    return document


def load_post_failure_execution_decision(
    path: Path,
) -> PostFailureExecutionDecision:
    """Validate pending or named post-failure authorization."""
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
                "population_contract_sha256",
                "pre_review_sha256",
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
        description="post-failure execution decision",
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
        or document.get("pre_review_sha256") != _PRE_REVIEW_SHA256
        or document.get("population_contract_sha256") != _POPULATION_SHA256
        or document.get("pybdsf_ncores") != _PYBDSF_NCORES
        or document.get("execution_concurrency") != _EXECUTION_CONCURRENCY
        or document.get("one_look_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
        or document.get("preflight_review_path") != _PREFLIGHT_REVIEW
    ):
        raise ValueError("post-failure execution decision identity is invalid")
    expected_state = (
        (
            "await-named-execution-approval",
            False,
            "pending",
            "obtain-named-approval-before-post-failure-preflight",
        )
        if pending
        else (
            "authorize-one-terminal-post-failure-comparison",
            True,
            document.get("named_review"),
            "execute-complete-post-failure-comparison-once-without-opening-"
            "partial-results",
        )
    )
    if (
        document.get("decision"),
        document.get("execution_authorized"),
        document.get("named_review"),
        document.get("next_action"),
    ) != expected_state:
        raise ValueError("post-failure authorization state is invalid")
    root = path.resolve().parents[2]
    protocol_path = (
        root / "config/contracts/phase-5-external-post-failure-comparison.json"
    )
    review_path = root / "config/contracts/phase-5-corrective-a-review.json"
    if document.get("protocol_sha256") != file_sha256(
        protocol_path
    ) or document.get("candidate_review_sha256") != file_sha256(review_path):
        raise ValueError("post-failure decision binding changed")
    preflight_review_sha256 = post_failure_preflight_review_sha256(
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
        raise ValueError("post-failure runner identity changed")
    records = tuple(
        PostFailureRunnerArtifact(relative_path=path_, sha256=sha256)
        for path_, sha256 in _RUNNERS
    )
    for item in records:
        if file_sha256(root / item.relative_path) != item.sha256:
            raise ValueError(
                f"post-failure runner changed: {item.relative_path}"
            )
    return PostFailureExecutionDecision(
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


def load_post_failure_endpoint_registry(path: Path) -> dict[str, Any]:
    """Validate prospective composition and inherit the endpoint matrix."""
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
        document,
        required,
        description="post-failure endpoint registry",
    )
    if (
        document.get("schema_version") != 1
        or document.get("registry_id")
        != "phase-5-external-post-failure-endpoint-registry"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
    ):
        raise ValueError("post-failure endpoint registry state is invalid")
    root = path.resolve().parents[2]
    base_path = (
        root / "config/contracts/"
        "phase-5-external-confirmation-endpoint-registry.json"
    )
    if (
        document.get("base_registry_path")
        != "config/contracts/"
        "phase-5-external-confirmation-endpoint-registry.json"
        or document.get("base_registry_sha256") != file_sha256(base_path)
    ):
        raise ValueError("post-failure endpoint ancestry changed")
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "post-failure protocol"),
        (
            "continuum_manifest_path",
            "continuum_manifest_sha256",
            "post-failure continuum manifest",
        ),
        (
            "compact_manifest_path",
            "compact_manifest_sha256",
            "post-failure compact manifest",
        ),
        (
            "execution_decision_path",
            "execution_decision_sha256",
            "post-failure execution decision",
        ),
        ("launcher_path", "launcher_sha256", "post-failure launcher"),
        ("compiler_path", "compiler_sha256", "post-failure compiler"),
        (
            "protocol_verifier_path",
            "protocol_verifier_sha256",
            "post-failure protocol verifier",
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
            "observable truth compiler",
        ),
        (
            "population_contract_path",
            "population_contract_sha256",
            "post-failure population contract",
        ),
    ):
        require_bound_file(
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    load_post_failure_protocol(root / cast(str, document["protocol_path"]))
    load_post_failure_execution_decision(
        root / cast(str, document["execution_decision_path"])
    )
    base = _CONFIRMATION_HELPERS["load_confirmation_endpoint_registry"](
        base_path
    )
    compatible = dict(base)
    compatible.update(document)
    compatible["registry_id"] = "phase-5-external-endpoint-registry"
    return compatible


def post_failure_campaign_request_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Return the exact 2,400-image, 12,000-run two-lane request model."""
    scaled = create_model(
        f"PostFailure{historical_model.__name__}",
        __base__=historical_model,
        image_count=(Literal[2400], ...),
        run_count=(Literal[12000], ...),
    )
    return concurrent_campaign_request_model(scaled)


def post_failure_terminal_result_model(
    historical_model: type[BaseModel],
) -> type[BaseModel]:
    """Return the exact terminal result model for the fresh population."""
    return create_model(
        f"PostFailure{historical_model.__name__}",
        __base__=historical_model,
        image_count=(Literal[2400], ...),
        run_count=(Literal[12000], ...),
    )
