#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Reconstruct only omitted parent-construction association provenance."""

from __future__ import annotations

import argparse
import json
import runpy
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.datasets import DatasetRecord
from hebog.validation.external_runners import file_sha256
from hebog.validation.parent_construction_association_evaluation import (
    continuum_catalogue_objects_from_association,
    source_association_from_json,
)
from hebog.validation.products import (
    load_comparison_catalogue,
    load_fits_plane,
)

_ROOT = Path(__file__).parents[2]
_PARENT_WRAPPER = (
    _ROOT / "scripts/validation/review_phase5_public_finder_source_hierarchy_"
    "parent_construction_cumulative_regressions.py"
)
_FAILURE = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-provenance-failure.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-repair-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-repair-implementation-decision.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-reconstruction-execution-"
    "decision.json"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_CLOSED_BASELINE = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_PRESERVED_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-finder-source-hierarchy-parent-"
    "construction-5f2b098"
)
_FAILED_LEDGER = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-public-finder-"
    "source-hierarchy-parent-construction.json"
)
_TERMINAL = Path(
    "benchmark-results/phase-5/parent-construction-association-"
    "provenance-reconstruction"
)
_STAGING = Path(
    "benchmark-results/phase-5/.parent-construction-association-"
    "provenance-reconstruction.staging"
)
_PARENT_WRAPPER_SHA256 = (
    "053fc6479d75a9f11e97cc2ec6f7de41610c5c03083bd81ce01ca47ef104c8d7"
)
_FAILURE_SHA256 = (
    "1a391c240a957f4a41684ce2d6c19cef9d6a210239592aef460e00e8e476355a"
)
_CANDIDATE_REVISION = "5f2b09880dc10feb6ffaec50ffcf3c807a093416"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "a7ef1887bcaeb15abf48722d45de33f81d8be65d58fde19861bf0ece90b4dba8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "88634678d7b24c9d9d47a5ba714c66fcc627c8a201b9639b133e326cd1c72484"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_INPUT_COUNT = 2400
_CONTINUUM_COUNT = 1600
_REFERENCE_RUN_COUNT = 9600
_WORKERS = 2
_MINIMUM_HEADROOM_BYTES = 20 * 1024**3
_PROHIBITED_AUTHORIZATIONS = {
    "another_campaign_authorized": False,
    "candidate_execution_authorized": False,
    "compilation_authorized": False,
    "cutover_authorized": False,
    "evaluation_authorized": False,
    "fresh_qualification_authorized": False,
    "release_authorized": False,
    "rescoring_authorized": False,
    "tuning_authorized": False,
    "viewed_public_execution_authorized": False,
}


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one deterministic finite evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _json_object(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _load_parent_wrapper() -> dict[str, Any]:
    """Load the exact failed wrapper without executing its entry point."""
    if file_sha256(_PARENT_WRAPPER) != _PARENT_WRAPPER_SHA256:
        raise ValueError("parent-construction wrapper identity changed")
    return runpy.run_path(str(_PARENT_WRAPPER))


def _require_exact_invocation(arguments: argparse.Namespace) -> None:
    """Require the immutable source and one future sidecar namespace."""
    expected = {
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "closed_component_baseline_ledger": _CLOSED_BASELINE,
        "preserved_scratch": _PRESERVED_SCRATCH,
        "failed_ledger": _FAILED_LEDGER,
        "output": _TERMINAL,
        "staging": _STAGING,
        "workers": _WORKERS,
    }
    for field, value in expected.items():
        if getattr(arguments, field, None) != value:
            raise ValueError(f"association reconstruction {field} changed")


def _verified_marker(
    directory: Path,
    *,
    input_id: str,
    lane: str,
) -> dict[str, object]:
    """Verify one preserved candidate marker without opening science."""
    marker_path = directory / "complete.json"
    marker = _json_object(marker_path, label="candidate complete marker")
    if (
        marker.get("schema_version") != 1
        or marker.get("input_id") != input_id
        or marker.get("configuration_sha256")
        != _CANDIDATE_CONFIGURATION_SHA256
        or marker.get("source_tree_sha256") != _CANDIDATE_SOURCE_TREE_SHA256
        or marker_path.read_bytes() != _canonical_json_bytes(marker)
    ):
        raise ValueError("candidate marker identity changed")
    values = marker.get("artifacts")
    if not isinstance(values, list):
        raise ValueError("candidate artifact records are malformed")
    expected_roles = (
        {
            "segment-catalogue-json",
            "segment-labels-fits",
            "segment-mask-fits",
        }
        if lane == "continuum"
        else {"compact-catalogue-json"}
    )
    roles: set[str] = set()
    expected_names = {"complete.json"}
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("candidate artifact records are malformed")
        role = value.get("role")
        relative = value.get("relative_path")
        if (
            not isinstance(role, str)
            or not isinstance(relative, str)
            or Path(relative).name != relative
        ):
            raise ValueError("candidate artifact records are malformed")
        path = directory / relative
        if (
            not path.is_file()
            or value.get("byte_count") != path.stat().st_size
            or value.get("sha256") != file_sha256(path)
        ):
            raise ValueError("candidate artifact identity changed")
        roles.add(role)
        expected_names.add(relative)
    if (
        roles != expected_roles
        or {item.name for item in directory.iterdir()} != expected_names
    ):
        raise ValueError("candidate artifact set changed")
    return marker


def _verify_preserved_products(
    scratch: Path,
    expected_inputs: tuple[tuple[str, str], ...],
) -> str:
    """Verify all candidate shards and return their aggregate identity."""
    products = scratch / "products"
    progress = scratch / "progress.log"
    if (
        len(expected_inputs) != _INPUT_COUNT
        or not products.is_dir()
        or not progress.is_file()
        or {item.name for item in scratch.iterdir()}
        != {"products", "progress.log"}
    ):
        raise ValueError("preserved candidate scratch is incomplete")
    expected_ids = {item[0] for item in expected_inputs}
    if {item.name for item in products.iterdir()} != expected_ids:
        raise ValueError("preserved candidate population changed")
    markers = [
        _verified_marker(
            products / input_id,
            input_id=input_id,
            lane=lane,
        )
        for input_id, lane in expected_inputs
    ]
    lines = progress.read_text(encoding="utf-8").splitlines()
    completed = {
        line.rsplit(" input=", maxsplit=1)[1]
        for line in lines
        if " input=" in line
    }
    if len(lines) != _INPUT_COUNT or completed != expected_ids:
        raise ValueError("candidate progress record is incomplete")
    return canonical_sha256(markers)


def verify_association_reconstruction(
    arguments: argparse.Namespace,
    *,
    allow_staging: bool = False,
) -> dict[str, object]:
    """Verify identities and products without reconstructing science."""
    _require_exact_invocation(arguments)
    if arguments.failed_ledger.exists():
        raise ValueError("failed replay unexpectedly published a ledger")
    if arguments.output.exists() or (
        arguments.staging.exists() and not allow_staging
    ):
        raise ValueError("association reconstruction namespace exists")
    if (
        file_sha256(_FAILURE) != _FAILURE_SHA256
        or file_sha256(arguments.closed_component_baseline_ledger)
        != _CLOSED_BASELINE_SHA256
    ):
        raise ValueError("association reconstruction evidence changed")
    review = _json_object(_PRE_REVIEW, label="repair pre-review")
    if review.get("status") != (
        "implementation-authorized-by-explicit-user-fix-request"
    ):
        raise ValueError("association reconstruction is not prepared")
    wrapper = _load_parent_wrapper()
    verified = wrapper["_verify_reference_reconstruction"](arguments)
    expected_inputs = tuple(
        (item.input_id, item.lane) for item in verified.request.inputs
    )
    product_set_sha256 = _verify_preserved_products(
        arguments.preserved_scratch,
        expected_inputs,
    )
    continuum_count = sum(lane == "continuum" for _, lane in expected_inputs)
    if (
        len(verified.inputs) != _INPUT_COUNT
        or len(verified.runs) != _REFERENCE_RUN_COUNT
        or continuum_count != _CONTINUUM_COUNT
        or verified.reference_reconstruction_sha256
        != _REFERENCE_RECONSTRUCTION_SHA256
    ):
        raise ValueError("association reconstruction population changed")
    headroom = shutil.disk_usage(_ROOT).free
    if headroom < _MINIMUM_HEADROOM_BYTES:
        raise ValueError("association reconstruction host headroom is unsafe")
    _, _, frozen = wrapper["_load_source_association_composition"]()
    wrapper["_install_parent_construction_static_seams"](frozen)
    writer = frozen.get("_write_continuum_products")
    if not callable(writer):
        raise ValueError("association reconstruction candidate seam changed")
    return {
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_product_set_sha256": product_set_sha256,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "continuum_input_count": continuum_count,
        "failed_ledger_absent": True,
        "minimum_host_headroom_bytes": _MINIMUM_HEADROOM_BYTES,
        "output_absent": True,
        "preserved_product_count": len(expected_inputs),
        "reconstruction_started": False,
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "status": "pass",
    }


def _artifact_paths(directory: Path) -> dict[str, Path]:
    """Resolve every verified preserved artifact by role."""
    marker = _json_object(
        directory / "complete.json", label="candidate complete marker"
    )
    values = cast(list[dict[str, object]], marker["artifacts"])
    return {
        cast(str, item["role"]): directory / cast(str, item["relative_path"])
        for item in values
    }


def _verified_association_marker(
    directory: Path,
    *,
    input_id: str,
    preserved_complete_sha256: str,
) -> bool:
    """Return whether one restartable sidecar shard is exact and complete."""
    marker_path = directory / "complete.json"
    association_path = directory / "source_association.json"
    if not marker_path.is_file() or not association_path.is_file():
        return False
    marker = _json_object(marker_path, label="association complete marker")
    exact = (
        {item.name for item in directory.iterdir()}
        == {"complete.json", "source_association.json"}
        and marker.get("schema_version") == 1
        and marker.get("input_id") == input_id
        and marker.get("candidate_configuration_sha256")
        == _CANDIDATE_CONFIGURATION_SHA256
        and marker.get("candidate_revision") == _CANDIDATE_REVISION
        and marker.get("candidate_source_tree_sha256")
        == _CANDIDATE_SOURCE_TREE_SHA256
        and marker.get("preserved_complete_sha256")
        == preserved_complete_sha256
        and marker.get("reconstruction_program_sha256")
        == file_sha256(Path(__file__))
        and marker.get("source_association_sha256")
        == file_sha256(association_path)
        and marker_path.read_bytes() == _canonical_json_bytes(marker)
    )
    if exact:
        source_association_from_json(
            json.loads(association_path.read_text(encoding="utf-8"))
        )
    return exact


def _reconstruct_one(task: dict[str, object]) -> str:
    """Regenerate one exact Continuum association and verify old products."""
    wrapper = _load_parent_wrapper()
    _, _, frozen = wrapper["_load_source_association_composition"]()
    wrapper["_install_parent_construction_static_seams"](frozen)
    writer = frozen["_write_continuum_products"]
    writer_globals = writer.__globals__
    original_builder = writer_globals[
        "build_post_correction_continuum_products"
    ]
    captured: list[Any] = []

    def capture(*args: object, **kwargs: object) -> Any:
        products = original_builder(*args, **kwargs)
        captured.append(products)
        return products

    writer_globals["build_post_correction_continuum_products"] = capture
    destination = Path(cast(str, task["association_directory"]))
    input_id = cast(str, task["input_id"])
    preserved_directory = Path(cast(str, task["output_directory"]))
    preserved_complete_sha256 = file_sha256(
        preserved_directory / "complete.json"
    )
    if _verified_association_marker(
        destination,
        input_id=input_id,
        preserved_complete_sha256=preserved_complete_sha256,
    ):
        return cast(str, task["input_id"])
    if destination.exists():
        raise ValueError("association reconstruction shard identity changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{destination.name}.", dir=destination.parent
    ) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        dataset = DatasetRecord.model_validate(task["dataset"])
        try:
            generated = writer(
                dataset,
                image_path=Path(cast(str, task["image_path"])),
                mean_path=Path(cast(str, task["mean_path"])),
                rms_path=Path(cast(str, task["rms_path"])),
                output=staging,
            )
        finally:
            writer_globals["build_post_correction_continuum_products"] = (
                original_builder
            )
        if len(captured) != 1:
            raise ValueError("association reconstruction builder call changed")
        preserved = _artifact_paths(preserved_directory)
        if set(generated) != set(preserved) or any(
            file_sha256(path) != file_sha256(preserved[role])
            for role, path in generated.items()
        ):
            raise ValueError("regenerated candidate product changed")
        association = captured[0].source_association
        document = asdict(association)
        source_association_from_json(json.loads(json.dumps(document)))
        catalogue = load_comparison_catalogue(
            generated["segment-catalogue-json"]
        )
        labels = np.asarray(
            load_fits_plane(generated["segment-labels-fits"]),
            dtype=np.int64,
        )
        header = cast(
            fits.Header,
            fits.getheader(generated["segment-labels-fits"]),
        )
        continuum_catalogue_objects_from_association(
            catalogue,
            labels,
            association,
            finder_id="hebog",
            header=header,
        )
        for path in generated.values():
            path.unlink()
        association_path = staging / "source_association.json"
        association_path.write_bytes(_canonical_json_bytes(document))
        marker = {
            "candidate_configuration_sha256": (
                _CANDIDATE_CONFIGURATION_SHA256
            ),
            "candidate_revision": _CANDIDATE_REVISION,
            "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
            "input_id": task["input_id"],
            "preserved_complete_sha256": preserved_complete_sha256,
            "reconstruction_program_sha256": file_sha256(Path(__file__)),
            "schema_version": 1,
            "source_association_sha256": file_sha256(association_path),
        }
        (staging / "complete.json").write_bytes(_canonical_json_bytes(marker))
        if {item.name for item in staging.iterdir()} != {
            "complete.json",
            "source_association.json",
        }:
            raise ValueError("association reconstruction retained extra files")
        Path(temporary, "bundle").replace(destination)
    return cast(str, task["input_id"])


def _continuum_tasks(
    arguments: argparse.Namespace,
    verified: Any,
) -> tuple[dict[str, object], ...]:
    """Compose the exact frozen candidate tasks and select Continuum only."""
    wrapper = _load_parent_wrapper()
    _, _, frozen = wrapper["_load_source_association_composition"]()
    wrapper["_install_parent_construction_static_seams"](frozen)
    compiler = runpy.run_path(str(frozen["_COMPILER_PATH"]))
    frozen["_install_historical_source_view"](compiler)
    terminal = compiler["_configured_terminal"]()
    compiler_globals = terminal["compile_terminal_analysis"].__globals__
    registry = compiler_globals["load_endpoint_registry"](
        frozen["_REGISTRY_PATH"],
        frozen["_COMPILER_PATH"],
    )
    compact, _ = compiler_globals["_dataset_maps"](
        _ROOT / registry["compact_manifest_path"]
    )
    continuum, _ = compiler_globals["_dataset_maps"](
        _ROOT / registry["continuum_manifest_path"]
    )
    tasks = frozen["_candidate_tasks"](
        verified,
        {**compact, **continuum},
        arguments.preserved_scratch,
        configuration_sha256=_CANDIDATE_CONFIGURATION_SHA256,
        source_sha256=_CANDIDATE_SOURCE_TREE_SHA256,
    )
    return tuple(
        {
            **task,
            "association_directory": str(
                arguments.staging
                / "associations"
                / cast(str, task["input_id"])
            ),
        }
        for task in tasks
        if task["lane"] == "continuum"
    )


def _authorize_reconstruction(
    verified: dict[str, object],
) -> dict[str, object]:
    """Require one exact later decision and no broader authority."""
    decision = _json_object(
        _EXECUTION_DECISION, label="association reconstruction decision"
    )
    if (
        decision.get("status")
        != "reviewed-before-association-provenance-reconstruction"
        or decision.get("reconstruction_authorized") is not True
        or decision.get("verified_composition") != verified
        or decision.get("reconstruction_program_sha256")
        != file_sha256(Path(__file__))
        or decision.get("implementation_decision_sha256")
        != file_sha256(_IMPLEMENTATION_DECISION)
        or decision.get("pre_review_sha256") != file_sha256(_PRE_REVIEW)
        or decision.get("failure_sha256") != file_sha256(_FAILURE)
    ):
        raise ValueError("association reconstruction is not authorized")
    if decision.get("prohibited_authorizations") != (
        _PROHIBITED_AUTHORIZATIONS
    ):
        raise ValueError("association reconstruction authority changed")
    return decision


def run_authorized_reconstruction(arguments: argparse.Namespace) -> None:
    """Reconstruct one write-once sidecar set after exact approval."""
    composition = verify_association_reconstruction(
        arguments,
        allow_staging=arguments.staging.exists(),
    )
    _authorize_reconstruction(composition)
    arguments.staging.mkdir(parents=True, exist_ok=True)
    progress_path = arguments.staging / "progress.log"
    wrapper = _load_parent_wrapper()
    verified = wrapper["_verify_reference_reconstruction"](arguments)
    tasks = _continuum_tasks(arguments, verified)
    if len(tasks) != _CONTINUUM_COUNT:
        raise ValueError("association reconstruction task count changed")
    completed = (
        set(progress_path.read_text().splitlines())
        if (progress_path.is_file())
        else set()
    )
    pending = [task for task in tasks if task["input_id"] not in completed]
    with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
        futures = {
            pool.submit(_reconstruct_one, task): task for task in pending
        }
        for future in as_completed(futures):
            input_id = future.result()
            with progress_path.open("a", encoding="utf-8") as stream:
                stream.write(f"{input_id}\n")
                stream.flush()
    markers = [
        _json_object(
            arguments.staging
            / "associations"
            / cast(str, task["input_id"])
            / "complete.json",
            label="association complete marker",
        )
        for task in tasks
    ]
    recovery = {
        "association_count": len(markers),
        "association_product_set_sha256": canonical_sha256(markers),
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_product_set_sha256": composition[
            "candidate_product_set_sha256"
        ],
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "decision_sha256": file_sha256(_EXECUTION_DECISION),
        "failure_sha256": file_sha256(_FAILURE),
        "implementation_decision_sha256": file_sha256(
            _IMPLEMENTATION_DECISION
        ),
        "parent_wrapper_sha256": _PARENT_WRAPPER_SHA256,
        "pre_review_sha256": file_sha256(_PRE_REVIEW),
        "reference_reconstruction_sha256": (_REFERENCE_RECONSTRUCTION_SHA256),
        "reconstruction_program_sha256": file_sha256(Path(__file__)),
        "schema_version": 1,
        "status": "sealed",
    }
    (arguments.staging / "recovery.json").write_bytes(
        _canonical_json_bytes(recovery)
    )
    arguments.staging.replace(arguments.output)


def _parse_args() -> argparse.Namespace:
    """Parse the single prospective reconstruction namespace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.reference_reconstruction = _REFERENCE_RECONSTRUCTION
    arguments.closed_component_baseline_ledger = _CLOSED_BASELINE
    arguments.preserved_scratch = _PRESERVED_SCRATCH
    arguments.failed_ledger = _FAILED_LEDGER
    arguments.output = _TERMINAL
    arguments.staging = _STAGING
    arguments.workers = _WORKERS
    arguments.campaign = None
    return arguments


def main() -> None:
    """Verify or execute only the exact governed reconstruction."""
    arguments = _parse_args()
    if arguments.verify_only:
        print(
            json.dumps(
                verify_association_reconstruction(arguments),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_authorized_reconstruction(arguments)


if __name__ == "__main__":
    main()
