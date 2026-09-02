#!/usr/bin/env python3
# pyright: reportAny=false
# pyright: reportExplicitAny=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Reconstruct the paired incumbent under its exact historical source tree."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import runpy
import subprocess
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import numpy as np
from astropy.io import fits

from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)

_ROOT = Path(__file__).parents[2]
_HISTORICAL_ROOT = Path(
    "/private/tmp/hebog-phase5-terminal-parent-replay-c1614c2"
)
_HISTORICAL_WRAPPER = (
    "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
)
_HISTORICAL_PROGRAM = "src/hebog/validation/public_finder_correction.py"
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-incumbent-provenance-repair-pre-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-paired-incumbent-reconstruction-execution-"
    "decision.json"
)
_PRE_REVIEW_SHA256 = (
    "5fbafa4e3d4f215d6668a7f3ac2fda27e7da52d4341ead266b9c2f72342a5bb5"
)
_HISTORICAL_EXECUTION_REVISION = "c1614c2e1b7f8a47877c20a97bb732541ae039d2"
_INCUMBENT_REVISION = "85d580713664b962ae256a98b065849cf8eb9283"
_INCUMBENT_SOURCE_TREE_SHA256 = (
    "a082cbe4b3416f787b455bb5a06be1eb66cb33ec807c74fa48056dfe8c630696"
)
_INCUMBENT_CONFIGURATION_SHA256 = (
    "88ac8bea8e865c765d5f346235642f88b298140955af67ada99b9f9bf6187523"
)
_HISTORICAL_WRAPPER_SHA256 = (
    "2c40315ffe821008b249a57b5e8c012b0f6526ae8aacab5a9bbdb35bdeac2f21"
)
_HISTORICAL_PROGRAM_SHA256 = (
    "1e9483fc033f6e78987b90aafb8a67302071a53e622376d368d229c2cbcee3c0"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_SOURCE_REQUEST_SHA256 = (
    "7ba9be1b20ff0448e51729337acf2a7028cc0ec578c5e25106b9b34b07506df4"
)
_POPULATION_SHA256 = (
    "0bd3e6a6e505f8fb307a108d90e932f6b3f16ae5fc6c654ab4c82de14f483687"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_REFERENCE_RUN_COUNT = 9600
_EXPECTED_COMPACT_COUNT = 800
_EXPECTED_CONTINUUM_COUNT = 1600
_EXPECTED_WORKERS = 2
_IMAGE_DIMENSIONS = 2
_EXPECTED_CONTINUUM_ROLES = {
    "segment-catalogue-json",
    "segment-labels-fits",
    "segment-mask-fits",
    "source-association-json",
}
_EXPECTED_COMPACT_ROLES = {"compact-catalogue-json"}
_PROHIBITED_AUTHORIZATIONS = (
    "current_candidate_execution_authorized",
    "cutover_authorized",
    "fresh_qualification_authorized",
    "optimization_authorized",
    "release_authorized",
    "rescoring_authorized",
    "scientific_change_authorized",
    "threshold_or_margin_tuning_authorized",
    "viewed_data_execution_authorized",
)


def _require_module_origin(candidate_root: Path, module_path: Path) -> None:
    """Require an imported science module to come from the candidate tree."""
    expected = (
        candidate_root / "src/hebog/validation/public_finder_correction.py"
    ).resolve()
    if module_path.resolve() != expected:
        raise ValueError(
            "incumbent science module origin differs from candidate checkout"
        )


def _historical_wrapper(root: Path) -> dict[str, Any]:
    """Load and verify the exact historical producer composition."""
    wrapper_path = root / _HISTORICAL_WRAPPER
    program_path = root / _HISTORICAL_PROGRAM
    revision = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=root, text=True
    ).strip()
    if revision != _HISTORICAL_EXECUTION_REVISION:
        raise ValueError("historical incumbent execution revision changed")
    if source_tree_sha256(root) != _INCUMBENT_SOURCE_TREE_SHA256:
        raise ValueError("historical incumbent source tree changed")
    if (
        file_sha256(wrapper_path) != _HISTORICAL_WRAPPER_SHA256
        or file_sha256(program_path) != _HISTORICAL_PROGRAM_SHA256
    ):
        raise ValueError("historical incumbent producer program changed")
    wrapper = cast(dict[str, Any], runpy.run_path(str(wrapper_path)))
    producer = wrapper.get(
        "build_public_finder_source_reconstruction_continuum_products"
    )
    module_path = (
        inspect.getsourcefile(producer) if callable(producer) else None
    )
    if module_path is None:
        raise ValueError("historical incumbent science module is unavailable")
    _require_module_origin(root, Path(module_path))
    if (
        wrapper.get("_CANDIDATE_REVISION") != _INCUMBENT_REVISION
        or wrapper.get("_CANDIDATE_SOURCE_TREE_SHA256")
        != _INCUMBENT_SOURCE_TREE_SHA256
        or wrapper.get("_CANDIDATE_CONFIGURATION_SHA256")
        != _INCUMBENT_CONFIGURATION_SHA256
    ):
        raise ValueError("historical incumbent scientific identity changed")
    return wrapper


def _selected_inputs(request_path: Path, population_path: Path) -> set[str]:
    """Resolve the exact result-neutral paired population."""
    if (
        file_sha256(request_path) != _SOURCE_REQUEST_SHA256
        or file_sha256(population_path) != _POPULATION_SHA256
    ):
        raise ValueError("paired incumbent population identity changed")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    population = json.loads(population_path.read_text(encoding="utf-8"))
    selection = population["selection"]
    groups: dict[tuple[str, str], list[str]] = {}
    for value in request["inputs"]:
        key = (value["lane"], value["dataset_identifier"])
        groups.setdefault(key, []).append(value["input_id"])
    selected: list[str] = []
    for (lane, _dataset), identifiers in sorted(groups.items()):
        count = (
            selection["compact_count"]
            if lane == "compact-blend"
            else selection["continuum_count_per_dataset"]
        )
        selected.extend(
            sorted(
                identifiers,
                key=lambda item: (
                    hashlib.sha256(item.encode()).hexdigest(),
                    item,
                ),
            )[:count]
        )
    ordered = tuple(sorted(selected))
    if (
        len(ordered) != _EXPECTED_INPUT_COUNT
        or canonical_sha256(ordered)
        != selection["selected_input_set_canonical_sha256"]
    ):
        raise ValueError("paired incumbent selected population changed")
    return set(ordered)


def _reference_and_tasks(
    arguments: argparse.Namespace,
) -> tuple[Any, tuple[dict[str, object], ...]]:
    """Verify retained evidence and construct exact historical tasks."""
    wrapper = _historical_wrapper(arguments.historical_root)
    reference = arguments.reference_reconstruction / "recovery.json"
    if (
        not reference.is_file()
        or file_sha256(reference) != _REFERENCE_RECONSTRUCTION_SHA256
    ):
        raise ValueError("paired incumbent reference reconstruction changed")
    verified = wrapper["_verify_reference_reconstruction"](
        SimpleNamespace(
            campaign=None,
            reference_reconstruction=arguments.reference_reconstruction,
            closed_component_baseline_ledger=arguments.closed_baseline,
        )
    )
    if len(verified.runs) != _EXPECTED_REFERENCE_RUN_COUNT:
        raise ValueError("paired incumbent reference run count changed")
    selected = _selected_inputs(arguments.source_request, arguments.population)
    if {item.input_id for item in verified.request.inputs} != selected:
        raise ValueError("paired incumbent verified population changed")
    _, _, frozen = wrapper["_load_source_association_composition"]()
    wrapper["_install_terminal_parent_static_seams"](frozen)
    compiler = runpy.run_path(str(frozen["_COMPILER_PATH"]))
    frozen["_install_historical_source_view"](compiler)
    terminal = compiler["_configured_terminal"]()
    compiler_globals = terminal["compile_terminal_analysis"].__globals__
    registry = compiler_globals["load_endpoint_registry"](
        frozen["_REGISTRY_PATH"], frozen["_COMPILER_PATH"]
    )
    compact, _ = compiler_globals["_dataset_maps"](
        arguments.historical_root / registry["compact_manifest_path"]
    )
    continuum, _ = compiler_globals["_dataset_maps"](
        arguments.historical_root / registry["continuum_manifest_path"]
    )
    tasks = tuple(
        frozen["_candidate_tasks"](
            verified,
            {**compact, **continuum},
            arguments.scratch,
            configuration_sha256=_INCUMBENT_CONFIGURATION_SHA256,
            source_sha256=_INCUMBENT_SOURCE_TREE_SHA256,
        )
    )
    if (
        len(tasks) != _EXPECTED_INPUT_COUNT
        or {cast(str, task["input_id"]) for task in tasks} != selected
    ):
        raise ValueError("paired incumbent candidate task population changed")
    return verified, tasks


def _association_component_labels(
    association: Mapping[str, object],
) -> dict[str, int]:
    """Return unique positive component identities from one sidecar."""
    components = association.get("components")
    if not isinstance(components, list):
        raise ValueError("historical incumbent association is malformed")
    component_labels: dict[str, int] = {}
    for value in components:
        if not isinstance(value, dict):
            raise ValueError("historical incumbent association is malformed")
        identifier = value.get("component_id")
        label_value = value.get("label_value")
        if (
            not isinstance(identifier, str)
            or type(label_value) is not int
            or label_value <= 0
            or identifier in component_labels
        ):
            raise ValueError("historical incumbent association is malformed")
        component_labels[identifier] = label_value
    return component_labels


def _association_memberships(
    association: Mapping[str, object],
) -> tuple[set[str], set[str]]:
    """Return unique sources and disjoint claimed components."""
    memberships = association.get("memberships")
    if not isinstance(memberships, list):
        raise ValueError("historical incumbent association is malformed")
    membership_ids: set[str] = set()
    claimed_components: set[str] = set()
    for value in memberships:
        if not isinstance(value, dict):
            raise ValueError("historical incumbent association is malformed")
        source_id = value.get("source_id")
        component_ids = value.get("component_ids")
        if (
            not isinstance(source_id, str)
            or not isinstance(component_ids, list)
            or not component_ids
            or not all(isinstance(item, str) for item in component_ids)
            or source_id in membership_ids
            or claimed_components.intersection(component_ids)
        ):
            raise ValueError("historical incumbent association is malformed")
        membership_ids.add(source_id)
        claimed_components.update(cast(list[str], component_ids))
    return membership_ids, claimed_components


def _verify_support_partition(
    association: Mapping[str, object],
    catalogue_identifiers: Sequence[str],
    label_plane: np.ndarray,
) -> None:
    """Require historical memberships to partition the persisted labels."""
    labels = np.asarray(label_plane)
    if (
        labels.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any(labels < 0)
    ):
        raise ValueError("historical incumbent label plane is invalid")
    component_labels = _association_component_labels(association)
    membership_ids, claimed_components = _association_memberships(association)
    catalogue_ids = tuple(catalogue_identifiers)
    if (
        len(catalogue_ids) != len(set(catalogue_ids))
        or set(catalogue_ids) != membership_ids
    ):
        raise ValueError("historical incumbent catalogue membership changed")
    if claimed_components != set(component_labels):
        raise ValueError("historical incumbent association partition changed")
    present_labels = {int(value) for value in np.unique(labels) if value > 0}
    if present_labels != set(component_labels.values()):
        raise ValueError("historical incumbent support partition changed")


def _verified_marker(
    directory: Path,
    *,
    input_id: str,
    lane: str,
) -> dict[str, object]:
    """Verify one exact historical product and its support semantics."""
    marker_path = directory / "complete.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if (
        not isinstance(marker, dict)
        or marker.get("schema_version") != 1
        or marker.get("input_id") != input_id
        or marker.get("configuration_sha256")
        != _INCUMBENT_CONFIGURATION_SHA256
        or marker.get("source_tree_sha256") != _INCUMBENT_SOURCE_TREE_SHA256
    ):
        raise ValueError("historical incumbent marker identity changed")
    artifacts = marker.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("historical incumbent artifacts are malformed")
    roles: dict[str, Path] = {}
    expected_names = {"complete.json"}
    for value in artifacts:
        if not isinstance(value, dict):
            raise ValueError("historical incumbent artifacts are malformed")
        role = value.get("role")
        relative = value.get("relative_path")
        if (
            not isinstance(role, str)
            or not isinstance(relative, str)
            or Path(relative).name != relative
            or role in roles
        ):
            raise ValueError("historical incumbent artifacts are malformed")
        path = directory / relative
        if (
            not path.is_file()
            or value.get("byte_count") != path.stat().st_size
            or value.get("sha256") != file_sha256(path)
        ):
            raise ValueError("historical incumbent artifact identity changed")
        roles[role] = path
        expected_names.add(relative)
    expected_roles = (
        _EXPECTED_CONTINUUM_ROLES
        if lane == "continuum"
        else _EXPECTED_COMPACT_ROLES
    )
    if (
        set(roles) != expected_roles
        or {item.name for item in directory.iterdir()} != expected_names
    ):
        raise ValueError("historical incumbent artifact set changed")
    if lane == "continuum":
        association = json.loads(
            roles["source-association-json"].read_text(encoding="utf-8")
        )
        catalogue = json.loads(
            roles["segment-catalogue-json"].read_text(encoding="utf-8")
        )
        if not isinstance(association, dict) or not isinstance(
            catalogue, list
        ):
            raise ValueError("historical incumbent science records malformed")
        label_plane = np.asarray(
            fits.getdata(roles["segment-labels-fits"])
        ).squeeze()
        _verify_support_partition(
            cast(dict[str, object], association),
            tuple(cast(str, item["identifier"]) for item in catalogue),
            label_plane,
        )
    return cast(dict[str, object], marker)


def _verify_product_set(
    scratch: Path,
    expected_inputs: Mapping[str, str],
) -> str:
    """Verify every historical shard and return its canonical identity."""
    products = scratch / "products"
    progress = scratch / "progress.log"
    if (
        len(expected_inputs) != _EXPECTED_INPUT_COUNT
        or not products.is_dir()
        or not progress.is_file()
        or {item.name for item in scratch.iterdir()}
        != {"products", "progress.log"}
        or {item.name for item in products.iterdir()} != set(expected_inputs)
    ):
        raise ValueError("historical incumbent product set is incomplete")
    markers = [
        _verified_marker(
            products / input_id,
            input_id=input_id,
            lane=expected_inputs[input_id],
        )
        for input_id in sorted(expected_inputs)
    ]
    lines = progress.read_text(encoding="utf-8").splitlines()
    completed = {
        line.rsplit(" input=", maxsplit=1)[1]
        for line in lines
        if " input=" in line
    }
    if len(lines) != _EXPECTED_INPUT_COUNT or completed != set(
        expected_inputs
    ):
        raise ValueError("historical incumbent progress record is incomplete")
    return canonical_sha256(markers)


def _generate_product(task: dict[str, object]) -> str:
    """Generate one shard with imports bound to the historical checkout."""
    wrapper = _historical_wrapper(Path(cast(str, task["historical_root"])))
    candidate_task = {
        key: value for key, value in task.items() if key != "historical_root"
    }
    return cast(str, wrapper["_generate_candidate_product"](candidate_task))


def _publish(path: Path, document: Mapping[str, object]) -> None:
    """Atomically publish one finite write-once reconstruction record."""
    payload = (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _expected_execution_fields(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    """Return every identity authorized for the one reconstruction."""
    return {
        "closed_baseline_path": str(arguments.closed_baseline),
        "historical_execution_revision": _HISTORICAL_EXECUTION_REVISION,
        "historical_program_sha256": _HISTORICAL_PROGRAM_SHA256,
        "historical_root": str(arguments.historical_root),
        "historical_wrapper_sha256": _HISTORICAL_WRAPPER_SHA256,
        "incumbent_configuration_sha256": (_INCUMBENT_CONFIGURATION_SHA256),
        "incumbent_revision": _INCUMBENT_REVISION,
        "incumbent_source_tree_sha256": _INCUMBENT_SOURCE_TREE_SHA256,
        "output_path": str(arguments.output),
        "population_path": str(arguments.population),
        "population_sha256": _POPULATION_SHA256,
        "pre_review_sha256": _PRE_REVIEW_SHA256,
        "reconstruction_program_sha256": file_sha256(Path(__file__).resolve()),
        "reference_reconstruction_path": str(
            arguments.reference_reconstruction
        ),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "scratch_path": str(arguments.scratch),
        "source_request_path": str(arguments.source_request),
        "source_request_sha256": _SOURCE_REQUEST_SHA256,
        "workers": arguments.workers,
    }


def _require_execution_authority(arguments: argparse.Namespace) -> str:
    """Require the exact one-use reconstruction decision."""
    if not _EXECUTION_DECISION.is_file():
        raise ValueError("incumbent reconstruction is not authorized")
    decision = json.loads(_EXECUTION_DECISION.read_text(encoding="utf-8"))
    if (
        not isinstance(decision, dict)
        or decision.get("status")
        != "authorized-for-one-exact-incumbent-reconstruction"
        or decision.get("incumbent_reconstruction_authorized") is not True
        or decision.get("evaluation_authorized") is not True
        or decision.get("expected_execution_sha256")
        != canonical_sha256(_expected_execution_fields(arguments))
        or decision.get("prohibited_authorizations")
        != dict.fromkeys(_PROHIBITED_AUTHORIZATIONS, False)
    ):
        raise ValueError("incumbent reconstruction authorization changed")
    return file_sha256(_EXECUTION_DECISION)


def _parse_args() -> argparse.Namespace:
    """Parse one exact reconstruction or its no-write verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--reference-reconstruction", type=Path, required=True)
    parser.add_argument("--closed-baseline", type=Path, required=True)
    parser.add_argument("--source-request", type=Path, required=True)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify identities, then reconstruct the exact incumbent once."""
    arguments = _parse_args()
    if file_sha256(_PRE_REVIEW) != _PRE_REVIEW_SHA256:
        raise ValueError("incumbent provenance repair pre-review changed")
    if arguments.historical_root.resolve() != _HISTORICAL_ROOT:
        raise ValueError("incumbent historical checkout path changed")
    if arguments.workers != _EXPECTED_WORKERS:
        raise ValueError("incumbent reconstruction worker count changed")
    verified, tasks = _reference_and_tasks(arguments)
    if arguments.verify_only:
        if arguments.scratch.exists() or arguments.output.exists():
            raise ValueError(
                "incumbent reconstruction write-once state changed"
            )
        print(
            json.dumps(
                {
                    "candidate_execution_started": False,
                    "input_count": len(tasks),
                    "reference_run_count": len(verified.runs),
                    "status": "pass",
                    "expected_execution_sha256": canonical_sha256(
                        _expected_execution_fields(arguments)
                    ),
                },
                sort_keys=True,
            )
        )
        return
    execution_decision_sha256 = _require_execution_authority(arguments)
    if arguments.scratch.exists() or arguments.output.exists():
        raise FileExistsError("incumbent reconstruction output already exists")
    arguments.scratch.mkdir(parents=True, exist_ok=False)
    progress_path = arguments.scratch / "progress.log"
    enriched = tuple(
        {**task, "historical_root": str(arguments.historical_root)}
        for task in tasks
    )
    with (
        progress_path.open("a", encoding="utf-8") as progress,
        ProcessPoolExecutor(max_workers=arguments.workers) as executor,
    ):
        futures = {
            executor.submit(_generate_product, task) for task in enriched
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            input_id = future.result()
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{len(tasks)} input={input_id}\n"
            )
            progress.flush()
    expected_inputs = {
        item.input_id: item.lane for item in verified.request.inputs
    }
    product_set = _verify_product_set(arguments.scratch, expected_inputs)
    record: dict[str, object] = {
        "schema_version": 1,
        "record_id": "phase-5-prospective-paired-incumbent-reconstruction",
        "status": "complete",
        "candidate_revision": _INCUMBENT_REVISION,
        "candidate_source_tree_sha256": _INCUMBENT_SOURCE_TREE_SHA256,
        "candidate_configuration_sha256": (_INCUMBENT_CONFIGURATION_SHA256),
        "historical_execution_revision": _HISTORICAL_EXECUTION_REVISION,
        "historical_wrapper_sha256": _HISTORICAL_WRAPPER_SHA256,
        "historical_program_sha256": _HISTORICAL_PROGRAM_SHA256,
        "pre_review_sha256": _PRE_REVIEW_SHA256,
        "execution_decision_sha256": execution_decision_sha256,
        "reconstruction_program_sha256": file_sha256(Path(__file__).resolve()),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "population_sha256": _POPULATION_SHA256,
        "input_count": len(tasks),
        "compact_product_count": sum(
            value == "compact-blend" for value in expected_inputs.values()
        ),
        "continuum_product_count": sum(
            value == "continuum" for value in expected_inputs.values()
        ),
        "product_set_sha256": product_set,
        "current_candidate_execution_started": False,
        "scientific_policy_changed": False,
    }
    if (
        record["compact_product_count"] != _EXPECTED_COMPACT_COUNT
        or record["continuum_product_count"] != _EXPECTED_CONTINUUM_COUNT
    ):
        raise ValueError("incumbent reconstruction lane counts changed")
    record["record_canonical_sha256"] = canonical_sha256(record)
    _publish(arguments.output, record)
    print(arguments.output)
    print(f"product_set_sha256={product_set}")


if __name__ == "__main__":
    main()
