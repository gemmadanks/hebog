#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Validate the frozen Phase 5 public-finder execution composition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).parents[2]
_PRE_REVIEW_SHA256 = (
    "476265e1b4e4ef1356f62a1b31ce4eb4ba3db995c84feddd8134da94bdb5ce4a"
)
_IMPLEMENTATION_DECISION_SHA256 = (
    "46216d4a93ecbbba1b66fad7d7dea049e6e34774a4b5cea44ca176318f67b349"
)
_SELECTED_REGISTRY_SHA256 = (
    "df3a9088e68d4f2ba9ac1332a82ad8645f194466d3da5ae724c76494f630f1f4"
)
_SELECTED_POPULATION_SHA256 = (
    "0a7c2b18d96ee47277072528949c5a64239f0c3053d5e7b33c03b36c194b7824"
)
_ACQUISITION_SHA256 = (
    "a74e60de95debcc53bdf43d4f6046a6f74befe8a85e849a5b0105f2ecb0bd0ce"
)
_SCHEMA_REVIEW_SHA256 = (
    "409318f58cafe259b4347953051ef8dddcf2308f041e8145e4199f7ad281eed8"
)
_CANDIDATE_REVISION = "90626641c8705ba9d55fdea02a705983528b8aa0"
_SOURCE_TREE_SHA256 = (
    "e4307246efa7db3ec941b3906f8ce443404b8b84cdc78aa89881e738850cdf8a"
)
_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)
_HEBOG_IMAGE_ID = (
    "e7f1ce9e9b26f6e29a14e75833bcec52e56b95ce58102f2905c3623f9902632c"
)
_HEBOG_DIGEST = (
    "sha256:132f1c3da7f353edc642e9bc2e6108aff8a1dbf6f9a5556f50144db864114363"
)
_PROGRAM_PATHS = (
    "scripts/validation/phase5_public_finder_protocol.py",
    "scripts/benchmark/run_phase5_public_finder_campaign.py",
    "scripts/benchmark/run_phase5_public_finder_hebog.py",
    "scripts/validation/compile_phase5_public_finder_campaign.py",
    "scripts/validation/evaluate_phase5_public_finder_decision.py",
)
_OUTPUTS = {
    "analysis": "benchmark-results/phase-5/public-finder-analysis.json",
    "campaign": "benchmark-results/phase-5/public-finder-comparison",
    "decision": "benchmark-results/phase-5/public-finder-decision.json",
}
_CASE_COUNT = 10
_STRATUM_COUNT = 8
_HYDRA_CASE_COUNT = 2
_PUBLISHED_SUBMISSION_COUNT = 9
_MATCH_FLUX_DECIMAL_PLACES = 9
_MAXIMUM_SEPARATION_BEAMS = 0.5
_POSITION_ANGLE_MINIMUM_AXIS_RATIO = 1.1
_GUARD_ASSIGNMENT_PRIORITY = (
    "binding-core-truth-primary-assignment-before-guard-truth-on-remaining-"
    "candidates-with-one-shared-eligible-edge-graph"
)
_MATCH_ASSIGNMENT = (
    "maximum-cardinality-then-minimum-summed-nine-decimal-quantized-absolute-"
    "natural-log-integrated-flux-ratio-then-minimum-summed-separation-then-"
    "sorted-identifiers"
)


def file_sha256(path: Path) -> str:
    """Hash one identity without retaining the artifact in memory."""
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


def canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite deterministic evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def write_once_json(path: Path, value: object) -> None:
    """Publish one evidence record without permitting overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(value))


def _require_identity(
    root: Path,
    identity: object,
    *,
    expected_path: str,
    expected_sha256: str,
    description: str,
) -> None:
    """Require one exact repository or ignored evidence identity."""
    if identity != {"path": expected_path, "sha256": expected_sha256}:
        raise ValueError(f"{description} identity changed")
    if file_sha256(root / expected_path) != expected_sha256:
        raise ValueError(f"{description} checksum changed")


def load_public_finder_protocol(path: Path) -> dict[str, Any]:
    """Validate the exact science contract without opening finder products."""
    document = json_object(path)
    root = path.resolve().parents[2]
    candidate = document.get("candidate")
    runtime = document.get("runtime")
    sdc1 = document.get("sdc1")
    hydra = document.get("hydra")
    selected = document.get("selected_population")
    source_evidence = document.get("source_evidence")
    strata = sdc1.get("strata") if isinstance(sdc1, dict) else None
    matching = document.get("matching")
    diagnostics = sdc1.get("diagnostics") if isinstance(sdc1, dict) else None
    hydra_cases = hydra.get("cases") if isinstance(hydra, dict) else None
    if (
        document.get("schema_version") != 1
        or document.get("contract_id") != "phase-5-public-finder-protocol"
        or document.get("status")
        != "implemented-and-frozen-before-public-finder-execution"
        or document.get("case_count") != _CASE_COUNT
        or document.get("published_finder_reruns") is not False
        or candidate
        != {
            "configuration_sha256": _CONFIGURATION_SHA256,
            "revision": _CANDIDATE_REVISION,
            "source_tree_sha256": _SOURCE_TREE_SHA256,
        }
        or not isinstance(runtime, dict)
        or runtime.get("image_id") != _HEBOG_IMAGE_ID
        or runtime.get("digest") != _HEBOG_DIGEST
        or runtime.get("dependency_inventory_sha256")
        != "d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2"
        or not isinstance(sdc1, dict)
        or not isinstance(strata, list)
        or len(strata) != _STRATUM_COUNT
        or sdc1.get("halo_pixels_yx") != [75, 75]
        or sdc1.get("guard_assignment_priority") != _GUARD_ASSIGNMENT_PRIORITY
        or not isinstance(diagnostics, dict)
        or diagnostics.get("shape_comparison")
        != "intrinsic-truth-versus-candidate-deconvolved-gaussian"
        or diagnostics.get("position_angle_minimum_truth_axis_ratio")
        != _POSITION_ANGLE_MINIMUM_AXIS_RATIO
        or diagnostics.get("published_submission_count")
        != _PUBLISHED_SUBMISSION_COUNT
        or not isinstance(hydra, dict)
        or hydra.get("binding") is not False
        or hydra.get("finder_vote_as_truth") is not False
        or not isinstance(hydra_cases, list)
        or len(hydra_cases) != _HYDRA_CASE_COUNT
        or not isinstance(matching, dict)
        or matching.get("maximum_separation_beams")
        != _MAXIMUM_SEPARATION_BEAMS
        or matching.get("flux_cost_decimal_places")
        != _MATCH_FLUX_DECIMAL_PLACES
        or matching.get("assignment") != _MATCH_ASSIGNMENT
        or document.get("output_roles")
        != [
            "segment-catalogue-json",
            "segment-labels-fits",
            "segment-mask-fits",
            "background-fits",
            "rms-fits",
        ]
        or not isinstance(selected, dict)
        or selected.get("sha256") != _SELECTED_POPULATION_SHA256
        or not isinstance(source_evidence, dict)
    ):
        raise ValueError("public finder protocol state is invalid")
    _require_identity(
        root,
        document.get("pre_review"),
        expected_path=(
            "config/contracts/phase-5-public-finder-execution-pre-review.json"
        ),
        expected_sha256=_PRE_REVIEW_SHA256,
        description="public finder pre-review",
    )
    _require_identity(
        root,
        document.get("implementation_decision"),
        expected_path=(
            "config/contracts/phase-5-public-finder-implementation-decision.json"
        ),
        expected_sha256=_IMPLEMENTATION_DECISION_SHA256,
        description="public finder implementation decision",
    )
    _require_identity(
        root,
        source_evidence.get("acquisition"),
        expected_path=(
            "benchmark-results/phase-5/public-comparison-acquisition/"
            "acquisition.json"
        ),
        expected_sha256=_ACQUISITION_SHA256,
        description="public acquisition",
    )
    _require_identity(
        root,
        source_evidence.get("schema_review"),
        expected_path=(
            "config/contracts/phase-5-public-comparison-schema-review.json"
        ),
        expected_sha256=_SCHEMA_REVIEW_SHA256,
        description="public schema review",
    )
    registry_identity = {
        "path": selected.get("registry_path"),
        "sha256": selected.get("registry_sha256"),
    }
    _require_identity(
        root,
        registry_identity,
        expected_path=(
            "config/contracts/phase-5-public-comparison-selected-population.json"
        ),
        expected_sha256=_SELECTED_REGISTRY_SHA256,
        description="selected public population registry",
    )
    population_path = root / cast(str, selected["path"])
    if file_sha256(population_path) != _SELECTED_POPULATION_SHA256:
        raise ValueError("selected public population checksum changed")
    population = json_object(population_path)
    if (
        population.get("status") != "sealed-before-finder-execution"
        or population.get("finder_execution_authorized") is not False
        or population.get("finder_outputs_created") is not False
    ):
        raise ValueError("selected public population is not closed")
    return document


def load_public_finder_execution_decision(  # noqa: C901
    path: Path,
) -> dict[str, Any]:
    """Validate pending or separately approved exact one-look authority."""
    document = json_object(path)
    root = path.resolve().parents[2]
    protocol_identity = document.get("protocol")
    review_identity = document.get("identity_review")
    authorized = document.get("execution_authorized") is True
    if (
        document.get("schema_version") != 1
        or document.get("decision_id")
        != "phase-5-public-finder-execution-decision"
        or not isinstance(protocol_identity, dict)
        or not isinstance(review_identity, dict)
        or document.get("campaign_execution_authorized") is not authorized
        or document.get("finder_execution_authorized") is not authorized
        or document.get("compilation_authorized") is not authorized
        or document.get("evaluation_authorized") is not authorized
        or document.get("optimization_authorized") is not False
        or document.get("tuning_authorized") is not False
        or document.get("rescoring_authorized") is not False
        or document.get("cutover_authorized") is not False
        or document.get("release_authorized") is not False
    ):
        raise ValueError("public finder execution decision is invalid")
    protocol_path = root / cast(str, protocol_identity.get("path"))
    if file_sha256(protocol_path) != protocol_identity.get("sha256"):
        raise ValueError("public finder protocol checksum changed")
    load_public_finder_protocol(protocol_path)
    review_path = root / cast(str, review_identity.get("path"))
    if file_sha256(review_path) != review_identity.get("sha256"):
        raise ValueError("public finder identity review checksum changed")
    review = json_object(review_path)
    programs = review.get("programs")
    if (
        review.get("status") != "ready-for-named-one-look-execution-review"
        or review.get("execution_authorized") is not False
        or not isinstance(programs, list)
        or tuple(item.get("path") for item in programs) != _PROGRAM_PATHS
    ):
        raise ValueError("public finder identity review is invalid")
    for program in programs:
        if file_sha256(root / program["path"]) != program.get("sha256"):
            raise ValueError("public finder program checksum changed")
    outputs = review.get("outputs")
    if outputs != _OUTPUTS:
        raise ValueError("public finder output paths changed")
    if not authorized:
        if (
            document.get("status") != "pending-named-one-look-approval"
            or document.get("named_review") is not None
        ):
            raise ValueError("pending public finder decision changed")
    else:
        named_review = document.get("named_review")
        approval = (
            named_review.get("approval")
            if isinstance(named_review, dict)
            else None
        )
        if (
            document.get("status") != "reviewed-before-public-one-look"
            or not isinstance(named_review, dict)
            or named_review.get("reviewer") != "Gemma Danks"
            or not isinstance(approval, str)
            or cast(str, review_identity.get("sha256")) not in approval
        ):
            raise ValueError("public finder execution is not exactly approved")
    return document


if __name__ == "__main__":
    load_public_finder_protocol(
        _ROOT / "config/contracts/phase-5-public-finder-protocol.json"
    )
