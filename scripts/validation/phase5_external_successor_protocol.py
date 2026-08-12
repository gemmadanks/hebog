#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate and adapt the Step 2C-PF successor protocol at script boundaries.

The installed Hebog runtime deliberately retains the closed Step 2C-P data
models.  These helpers validate the complete successor documents before
presenting a compatibility view to the unchanged materializer, runners, and
launcher.  No scientific values are read here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from hebog.validation.contracts import (
    PhaseFiveExternalComparisonProtocol,
    load_phase_five_external_comparison_protocol,
)

_PROTOCOL_ID = "phase-5-external-successor-comparison"
_DECISION_ID = "phase-5-external-successor-execution-decision"
_CONTINUUM_MANIFEST = (
    "config/datasets/phase-5-external-successor-continuum.json"
)
_COMPACT_MANIFEST = (
    "config/datasets/phase-5-external-successor-compact-blend.json"
)
_CONTINUUM_SHA256 = (
    "906a3e8bcc5bbc775418c30b5da08559e1425fbae74dd05fd9b2e96f69df7c46"
)
_COMPACT_SHA256 = (
    "05507a6605873981636b18d1b63e1b6e715937790c290027e72117a5928ce81c"
)
_SOURCE_TREE_SHA256 = (
    "d50be758d788967cf13912190b9de43e021d7e9f4325c2b7e5180f89c29516fd"
)
_HEBOG_IMAGE_DIGEST = (
    "sha256:d0c1319072c3716811ed51452fe83d92be8f8d2b62a11795678f31037b7b1f68"
)
_HEBOG_INVENTORY_SHA256 = (
    "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
)
_RUNNER_PATHS = (
    "scripts/benchmark/run_phase5_external_successor_hebog.py",
    "scripts/benchmark/run_phase5_external_successor_pybdsf.py",
    "scripts/benchmark/run_phase5_external_successor_aegean.py",
)
_POPULATION_COUNT = 2
_PYBDSF_NCORES = 4


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
    """Reject missing and ignored fields at a governed JSON boundary."""
    if set(document) != expected:
        raise ValueError(f"{description} fields changed")


def _require_bound_file(
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


def load_successor_protocol(
    path: Path,
) -> PhaseFiveExternalComparisonProtocol:
    """Validate the successor population and return its compatibility view."""
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
                "successor_population_contract_path",
                "successor_population_contract_sha256",
            }
        ),
        description="successor external protocol",
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
        raise ValueError("successor external protocol state is invalid")
    root = path.resolve().parents[2]
    closed_path = root / "config/contracts/phase-5-external-comparison.json"
    if document.get(
        "base_protocol_path"
    ) != "config/contracts/phase-5-external-comparison.json" or document.get(
        "base_protocol_sha256"
    ) != file_sha256(closed_path):
        raise ValueError("closed external protocol identity changed")
    population_contract_path = document.get(
        "successor_population_contract_path"
    )
    population_contract_sha256 = document.get(
        "successor_population_contract_sha256"
    )
    if (
        population_contract_path
        != "config/contracts/phase-5-external-successor-population.json"
        or not isinstance(population_contract_sha256, str)
        or file_sha256(root / population_contract_path)
        != population_contract_sha256
    ):
        raise ValueError("successor population contract changed")

    closed = load_phase_five_external_comparison_protocol(closed_path)
    populations = document.get("populations")
    if (
        not isinstance(populations, list)
        or len(populations) != _POPULATION_COUNT
    ):
        raise ValueError("successor external populations are incomplete")
    expected_population = (
        ("continuum", _CONTINUUM_MANIFEST, _CONTINUUM_SHA256, 600),
        ("compact-blend", _COMPACT_MANIFEST, _COMPACT_SHA256, 800),
    )
    observed_population = tuple(
        (
            item.get("lane"),
            item.get("manifest"),
            item.get("manifest_sha256"),
            item.get("image_count"),
        )
        for item in populations
        if isinstance(item, dict)
    )
    if observed_population != expected_population:
        raise ValueError("successor external population identity changed")
    for item in populations:
        if not isinstance(item, dict):
            raise ValueError("successor external population is not an object")
        require_exact_keys(
            item,
            frozenset({"image_count", "lane", "manifest", "manifest_sha256"}),
            description="successor external population",
        )
        manifest_path = root / cast(str, item["manifest"])
        if file_sha256(manifest_path) != item["manifest_sha256"]:
            raise ValueError("successor external manifest checksum changed")

    compatible_populations = tuple(
        old.model_copy(update=new)
        for old, new in zip(closed.populations, populations, strict=True)
    )
    return closed.model_copy(update={"populations": compatible_populations})


@dataclass(frozen=True, slots=True)
class SuccessorRunnerArtifact:
    """One checksum-bound successor runner wrapper."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class SuccessorExecutionDecision:
    """Successor authorization view consumed by the closed mechanics."""

    protocol_sha256: str
    candidate_review_sha256: str
    implementation_commit: str
    source_tree_sha256: str
    hebog_container_image_digest: str
    hebog_dependency_inventory_sha256: str
    pybdsf_ncores: int
    runners: tuple[SuccessorRunnerArtifact, ...]
    named_review: str
    execution_authorized: bool
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]


def load_successor_execution_decision(
    path: Path,
) -> SuccessorExecutionDecision:
    """Validate pending or named authorization without opening data."""
    document = json_object(path)
    require_exact_keys(
        document,
        frozenset(
            {
                "candidate_review_sha256",
                "decision",
                "decision_id",
                "execution_authorized",
                "hebog_container_image_digest",
                "hebog_dependency_inventory_sha256",
                "implementation_commit",
                "named_review",
                "next_action",
                "one_look_opened",
                "optimization_authorized",
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
        description="successor execution decision",
    )
    pending = document.get("status") == "awaiting-named-execution-approval"
    approved = document.get("status") == "reviewed-before-external-output"
    if (
        document.get("schema_version") != 1
        or document.get("decision_id") != _DECISION_ID
        or pending == approved
        or document.get("implementation_commit")
        != "c1f7eb0bdf5e8581e0024f0f7469c2908a22a594"
        or document.get("source_tree_sha256") != _SOURCE_TREE_SHA256
        or document.get("hebog_container_image_digest") != _HEBOG_IMAGE_DIGEST
        or document.get("hebog_dependency_inventory_sha256")
        != _HEBOG_INVENTORY_SHA256
        or document.get("pybdsf_ncores") != _PYBDSF_NCORES
        or document.get("one_look_opened") is not False
        or document.get("step_three_authorized") is not False
        or document.get("optimization_authorized") is not False
        or document.get("qualification_opened") is not False
    ):
        raise ValueError("successor execution decision identity is invalid")
    expected_state = (
        (
            "await-named-execution-approval",
            False,
            "pending",
            "obtain-named-approval-before-successor-preflight",
        )
        if pending
        else (
            "authorize-one-terminal-successor-comparison",
            True,
            document.get("named_review"),
            "execute-complete-successor-comparison-once-without-opening-"
            "partial-results",
        )
    )
    if (
        document.get("decision"),
        document.get("execution_authorized"),
        document.get("named_review"),
        document.get("next_action"),
    ) != expected_state:
        raise ValueError("successor execution authorization state is invalid")
    if approved and not cast(str, document["named_review"]).strip():
        raise ValueError("successor named review is absent")
    root = path.resolve().parents[2]
    protocol_path = (
        root / "config/contracts/phase-5-external-successor-comparison.json"
    )
    if document.get("protocol_sha256") != file_sha256(protocol_path):
        raise ValueError("successor execution protocol checksum changed")
    review_path = root / "config/contracts/phase-5-corrective-a-review.json"
    if document.get("candidate_review_sha256") != file_sha256(review_path):
        raise ValueError("successor candidate review checksum changed")
    runners = document.get("runners")
    if (
        not isinstance(runners, list)
        or tuple(
            item.get("relative_path")
            for item in runners
            if isinstance(item, dict)
        )
        != _RUNNER_PATHS
    ):
        raise ValueError("successor runner order is not canonical")
    runner_records: list[SuccessorRunnerArtifact] = []
    for item in runners:
        if not isinstance(item, dict):
            raise ValueError("successor runner identity is malformed")
        require_exact_keys(
            item,
            frozenset({"relative_path", "sha256"}),
            description="successor runner identity",
        )
        relative_path = cast(str, item["relative_path"])
        sha256 = cast(str, item["sha256"])
        if file_sha256(root / relative_path) != sha256:
            raise ValueError(f"successor runner changed: {relative_path}")
        runner_records.append(SuccessorRunnerArtifact(relative_path, sha256))
    return SuccessorExecutionDecision(
        protocol_sha256=cast(str, document["protocol_sha256"]),
        candidate_review_sha256=cast(str, document["candidate_review_sha256"]),
        implementation_commit=cast(str, document["implementation_commit"]),
        source_tree_sha256=cast(str, document["source_tree_sha256"]),
        hebog_container_image_digest=cast(
            str, document["hebog_container_image_digest"]
        ),
        hebog_dependency_inventory_sha256=cast(
            str, document["hebog_dependency_inventory_sha256"]
        ),
        pybdsf_ncores=cast(int, document["pybdsf_ncores"]),
        runners=tuple(runner_records),
        named_review=cast(str, document["named_review"]),
        execution_authorized=cast(bool, document["execution_authorized"]),
        one_look_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )


def load_successor_endpoint_registry(path: Path) -> dict[str, Any]:
    """Validate the complete composed registry and every upstream byte."""
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
                "registry_id",
                "schema_version",
                "status",
                "successor_composition",
                "successor_registry_id",
            }
        ),
        description="successor endpoint registry",
    )
    if (
        document.get("schema_version") != 1
        or document.get("registry_id") != "phase-5-external-endpoint-registry"
        or document.get("successor_registry_id")
        != "phase-5-external-successor-endpoint-registry"
        or document.get("status") != "frozen-before-campaign-output"
        or document.get("closed_campaign_reuse_authorized") is not False
    ):
        raise ValueError("successor endpoint registry identity is invalid")
    root = path.resolve().parents[2]
    closed_path = (
        root / "config/contracts/phase-5-external-endpoint-registry.json"
    )
    if (
        document.get("base_registry_path")
        != "config/contracts/phase-5-external-endpoint-registry.json"
        or document.get("base_registry_sha256") != file_sha256(closed_path)
    ):
        raise ValueError("closed endpoint registry identity changed")
    for path_key, sha_key, description in (
        ("protocol_path", "protocol_sha256", "successor protocol"),
        (
            "continuum_manifest_path",
            "continuum_manifest_sha256",
            "successor continuum manifest",
        ),
        (
            "compact_manifest_path",
            "compact_manifest_sha256",
            "successor compact manifest",
        ),
        (
            "execution_decision_path",
            "execution_decision_sha256",
            "successor execution decision",
        ),
        ("launcher_path", "launcher_sha256", "successor launcher"),
    ):
        _require_bound_file(
            root,
            document,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    composition = document.get("successor_composition")
    if not isinstance(composition, dict):
        raise ValueError("successor compiler composition is absent")
    require_exact_keys(
        composition,
        frozenset(
            {
                "protocol_verifier_path",
                "protocol_verifier_sha256",
                "science_kernel_path",
                "science_kernel_sha256",
                "successor_compiler_path",
                "successor_compiler_sha256",
                "terminal_compiler_path",
                "terminal_compiler_sha256",
                "terminal_launcher_path",
                "terminal_launcher_sha256",
            }
        ),
        description="successor compiler composition",
    )
    for path_key, sha_key, description in (
        (
            "terminal_compiler_path",
            "terminal_compiler_sha256",
            "closed terminal compiler",
        ),
        (
            "successor_compiler_path",
            "successor_compiler_sha256",
            "successor compiler wrapper",
        ),
        (
            "science_kernel_path",
            "science_kernel_sha256",
            "successor science kernel",
        ),
        (
            "protocol_verifier_path",
            "protocol_verifier_sha256",
            "successor protocol verifier",
        ),
        (
            "terminal_launcher_path",
            "terminal_launcher_sha256",
            "closed terminal launcher",
        ),
    ):
        _require_bound_file(
            root,
            composition,
            path_key=path_key,
            sha_key=sha_key,
            description=description,
        )
    if (
        composition.get("terminal_compiler_sha256")
        != "7a0558916ac003b71a781337dc710c99c359899c4d77f88486c1c206916b43f6"
        or composition.get("science_kernel_sha256")
        != "8e38de3b4347faee9636b89d03f8cdcdd77e39fd1e087d2b44454e5fd7063c55"
    ):
        raise ValueError("successor compiler composition changed")
    load_successor_protocol(root / cast(str, document["protocol_path"]))
    load_successor_execution_decision(
        root / cast(str, document["execution_decision_path"])
    )
    closed = json_object(closed_path)
    changed = {
        key: value
        for key, value in document.items()
        if key
        not in {
            "base_registry_path",
            "base_registry_sha256",
        }
    }
    closed.update(changed)
    return closed
