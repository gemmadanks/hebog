#!/usr/bin/env python3
"""Run the source-union-aligned compact Phase 5 sentinel when authorized."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, cast

import numpy as np
from astropy.io import fits
from distributed import Client

import hebog
from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest
from hebog.executors import DaskExecutor, Executor, SerialExecutor
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.products import load_fits_plane

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_legacy = importlib.import_module(
    "scripts.benchmark.run_phase5_compact_held_out_sentinel"
)
_public_runner = importlib.import_module(
    "scripts.benchmark.run_phase5_public_finder_hebog"
)
_compiler = importlib.import_module(
    "scripts.validation.compile_phase5_compact_held_out_sentinel"
)
_alignment = importlib.import_module(
    "scripts.validation.compact_sentinel_alignment"
)
_adapters = importlib.import_module(
    "scripts.validation.compact_sentinel_source_unions"
)
_evaluator = importlib.import_module(
    "scripts.validation.evaluate_phase5_compact_held_out_sentinel_aligned"
)
_population = importlib.import_module(
    "scripts.validation.phase5_compact_held_out_source_union_sentinel"
)

AlignedSummaryInput = _alignment.AlignedSummaryInput
compile_aligned_summary = _alignment.compile_aligned_summary
validate_aligned_summary = _alignment.validate_aligned_summary
SourceUnionComponent = _adapters.SourceUnionComponent
SourceUnionProjection = _adapters.SourceUnionProjection
SourceUnionSource = _adapters.SourceUnionSource
project_hebog_source_unions = _adapters.project_hebog_source_unions
compile_summaries = _compiler.compile_summaries
truth_objects = _compiler.truth_objects
evaluate_summaries = _evaluator.evaluate_summaries
audit_manifest = _population.audit_manifest
adaptive_background_trigger = _population.adaptive_background_trigger
cell_id = _population.cell_id
expected_input_ids = _population.expected_input_ids
public_hebog_configuration_sha256 = (
    _public_runner.public_hebog_configuration_sha256
)
_captured_science = _legacy._captured_science
_write_input = _legacy._write_input
_write_once_json = _legacy._write_once_json

_MANIFEST = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-manifest.json"
)
_IDENTITY = _ROOT / (
    "config/contracts/"
    "phase-5-compact-held-out-source-union-sentinel-identity-review.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-compact-held-out-source-union-sentinel"
)
_OUTPUT = _ROOT / (
    "benchmark-results/phase-5/compact-held-out-source-union-sentinel.json"
)
_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_CANDIDATE_REVISION = "95cfc76ded56556dc3ad6894410962d34f0d5604"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_PYBDSF_IMAGE_ID = (
    "43a6513865a597285dc1bf473e27fc69fdd86fb143c35a24144eb6c1152bb36e"
)
_PYBDSF_DIGEST = (
    "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198"
)
_CONFIG = SourceFinderConfig(5.0, 3.0, 7, profile="continuum")
_CELL_COUNT = 42
_IMAGE_COUNT = 168
_DASK_COMPARISON_COUNT = 12
_EVIDENCE_SCHEMA_VERSION = 3
_PYBDSF_RESULT_SCHEMA_VERSION = 2
_AUTHORIZATION = {
    "another_replay": False,
    "current_hebog_execution": True,
    "cutover": False,
    "existing_dask_comparison": True,
    "held_out_execution": True,
    "optimization": False,
    "release": False,
    "released_pybdsf_execution": True,
    "rescoring": False,
    "tuning": False,
    "viewed_data_execution": False,
}


def _json_object(path: Path) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return cast(dict[str, Any], value)


def _identity_bindings(
    repository_root: Path, identity: dict[str, Any]
) -> None:
    """Verify every frozen program byte before execution is possible."""
    bindings = identity.get("program_bindings")
    if not isinstance(bindings, dict):
        raise ValueError("sentinel program bindings are malformed")
    for binding in bindings.values():
        if not isinstance(binding, dict):
            raise ValueError("sentinel program binding is malformed")
        path = binding.get("path")
        digest = binding.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or file_sha256(repository_root / path) != digest
        ):
            raise ValueError("sentinel program binding changed")


def verify_no_write(  # noqa: PLR0913
    *,
    repository_root: Path,
    manifest_path: Path,
    identity_path: Path,
    scratch: Path,
    output: Path,
    minimum_free_disk_gib: float,
    podman_executable: str | None = None,
) -> dict[str, object]:
    """Validate the complete frozen successor without generating pixels."""
    root = repository_root.resolve()
    identity = _json_object(identity_path)
    authorization = identity.get("authorization")
    if not isinstance(authorization, dict):
        raise ValueError("sentinel identity is not frozen non-executable")
    typed_authorization = cast(dict[str, object], authorization)
    if (
        identity.get("status") != "frozen-non-executable"
        or set(typed_authorization.values()) != {False}
        or identity.get("evidence_schema_version") != _EVIDENCE_SCHEMA_VERSION
    ):
        raise ValueError("sentinel identity is not frozen non-executable")
    _identity_bindings(root, identity)
    if identity.get("candidate") != {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "entrypoint": "hebog.find_sources",
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }:
        raise ValueError("sentinel candidate identity changed")
    if (
        source_tree_sha256(root) != _CANDIDATE_SOURCE_TREE_SHA256
        or public_hebog_configuration_sha256()
        != _CANDIDATE_CONFIGURATION_SHA256
    ):
        raise ValueError("installed public Hebog candidate changed")
    manifest = load_dataset_manifest(manifest_path)
    manifest_binding = cast(dict[str, object], identity.get("manifest", {}))
    if (
        manifest_binding.get("sha256") != file_sha256(manifest_path)
        or len(manifest.datasets) != _CELL_COUNT
        or len(expected_input_ids(manifest)) != _IMAGE_COUNT
    ):
        raise ValueError("sentinel manifest identity changed")
    audit = audit_manifest(root, manifest)
    if scratch.exists() or output.exists():
        raise FileExistsError("sentinel scratch or write-once output exists")
    free_gib = shutil.disk_usage(scratch.parent).free / (1024**3)
    if free_gib < minimum_free_disk_gib:
        raise OSError("insufficient free disk for compact held-out sentinel")
    runtime: dict[str, object] = {"status": "not-requested"}
    if podman_executable is not None:
        from scripts.benchmark.run_phase5_external_campaign import (  # noqa: PLC0415
            inspect_container_image,
        )

        inspected = inspect_container_image(
            f"sha256:{_PYBDSF_IMAGE_ID}",
            "released-pybdsf",
            podman_executable=podman_executable,
        )
        if (
            inspected.image_id != _PYBDSF_IMAGE_ID
            or inspected.digest != _PYBDSF_DIGEST
        ):
            raise ValueError("released PyBDSF container identity changed")
        runtime = {
            "architecture": inspected.architecture,
            "container_digest": inspected.digest,
            "image_id": inspected.image_id,
            "operating_system": inspected.operating_system,
            "status": "pass",
        }
    return {
        "finder_execution_started": False,
        "free_disk_gib": free_gib,
        "image_count": _IMAGE_COUNT,
        "manifest_sha256": file_sha256(manifest_path),
        "released_pybdsf_runtime": runtime,
        "seed_audit": audit,
        "status": "pass",
    }


def _verify_decision(
    *, execution_decision: Path, identity_review: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Require one separately approved exact one-use decision."""
    identity = _json_object(identity_review)
    decision = _json_object(execution_decision)
    expected = identity.get("expected_execution")
    expected_sha256 = identity.get("expected_execution_sha256")
    if (
        identity.get("status") != "frozen-non-executable"
        or canonical_sha256(expected) != expected_sha256
        or decision.get("status")
        != "authorized-for-one-compact-held-out-source-union-sentinel"
        or decision.get("authorization") != _AUTHORIZATION
        or decision.get("one_use") is not True
        or decision.get("expected_execution_sha256") != expected_sha256
        or decision.get("identity_review")
        != {
            "path": identity_review.relative_to(_ROOT).as_posix(),
            "sha256": file_sha256(identity_review),
        }
    ):
        raise PermissionError("exact execution decision is required")
    return identity, decision


def verify_execution_authority(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Bind every execution path and concurrency value to an approval."""
    decision_path = getattr(arguments, "execution_decision", None)
    if decision_path is None:
        raise PermissionError("exact execution decision is required")
    identity, _decision = _verify_decision(
        execution_decision=Path(decision_path),
        identity_review=Path(arguments.identity_review),
    )
    expected = identity["expected_execution"]
    observed = {
        "dask_scheduler_address_present": bool(
            getattr(arguments, "dask_scheduler_address", None)
        ),
        "identity_review": Path(arguments.identity_review)
        .relative_to(_ROOT)
        .as_posix(),
        "manifest": Path(arguments.manifest).relative_to(_ROOT).as_posix(),
        "output": Path(arguments.output).relative_to(_ROOT).as_posix(),
        "scratch": str(Path(arguments.scratch)),
        "workers": int(arguments.workers),
    }
    if any(expected.get(key) != value for key, value in observed.items()):
        raise PermissionError("exact execution decision is required")
    return identity


def _with_runtime(
    summary: dict[str, Any],
    *,
    elapsed_seconds: float,
    candidate_revision: str | None,
    runtime_identity: dict[str, object],
) -> dict[str, object]:
    """Add non-scientific provenance and restore the record digest."""
    summary.pop("record_sha256")
    summary.update(
        {
            "candidate_revision": candidate_revision,
            "elapsed_seconds": float(elapsed_seconds),
            "runtime_identity": runtime_identity,
        }
    )
    summary["record_sha256"] = canonical_sha256(summary)
    validate_aligned_summary(summary)
    return cast(dict[str, object], summary)


def _compile_projection(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    projection: Any,
    review: Any,
    elapsed_seconds: float,
    candidate_revision: str | None,
    runtime_identity: dict[str, object],
) -> dict[str, object]:
    """Compile one finder projection against the shared analytic truth."""
    truth, truth_labels = truth_objects(dataset, recipe, review=review)
    return _with_runtime(
        compile_aligned_summary(
            AlignedSummaryInput(
                input_id=f"{dataset.identifier}-seed-{recipe.seed}",
                finder_id=projection.finder_id,
                truth=truth,
                truth_label_plane=truth_labels,
                sources=projection.sources,
                components=projection.components,
                native_owner_label_plane=projection.native_owner_label_plane,
                source_union_label_plane=projection.source_union_label_plane,
                native_topology_domain=projection.native_topology_domain,
                published_support_mask=(
                    projection.native_owner_label_plane > 0
                ),
                beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
                adaptive_background_trigger=adaptive_background_trigger(
                    dataset
                ),
                cell_id=cell_id(dataset),
                dataset_identifier=dataset.identifier,
                seed=recipe.seed,
                source_union_derivation=projection.source_union_derivation,
                unowned_native_support_labels=(
                    projection.unowned_native_support_labels
                ),
            )
        ),
        elapsed_seconds=elapsed_seconds,
        candidate_revision=candidate_revision,
        runtime_identity=runtime_identity,
    )


def _run_hebog(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    input_path: Path,
    output: Path,
    executor: Executor,
    review: Any,
) -> dict[str, object]:
    """Run the public facade and project its exact source associations."""
    started = monotonic()
    run_id = f"source-union-sentinel-{dataset.identifier}-{recipe.seed}"
    with _captured_science() as captured:
        result = hebog.find_sources(
            SourceFinderRequest(input_path, output, run_id), _CONFIG, executor
        )
    if len(captured) != 1 or captured[0].terminal is None:
        raise ValueError("public Hebog terminal products are unavailable")
    terminal = captured[0].terminal
    if result.source_count != len(
        terminal.catalogue
    ) or result.gaussian_component_count != len(terminal.component_catalogue):
        raise ValueError("public Hebog source/component population changed")
    header = cast(fits.Header, fits.getheader(input_path))
    projection = project_hebog_source_unions(
        source_catalogue=tuple(terminal.catalogue),
        component_catalogue=tuple(terminal.component_catalogue),
        association=terminal.source_association,
        measurement_component_labels=terminal.measurement_component_labels,
        header=header,
    )
    return _compile_projection(
        dataset=dataset,
        recipe=recipe,
        projection=projection,
        review=review,
        elapsed_seconds=monotonic() - started,
        candidate_revision=_CANDIDATE_REVISION,
        runtime_identity={
            "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
            "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        },
    )


def _pybdsf_command(
    *,
    repository_root: Path,
    case_root: Path,
    execution_decision: Path,
    identity_review: Path,
    podman_executable: str,
) -> tuple[str, ...]:
    """Return the exact network-disabled immutable-image child command."""
    return (
        podman_executable,
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{repository_root}:/repository:ro",
        "--volume",
        f"{case_root}:/campaign:rw",
        "--workdir",
        "/repository",
        "--entrypoint",
        "python3",
        "--env",
        "PYTHONPATH=/repository/src:/repository",
        f"sha256:{_PYBDSF_IMAGE_ID}",
        (
            "/repository/scripts/benchmark/"
            "run_phase5_compact_held_out_source_union_pybdsf.py"
        ),
        "--input",
        "/campaign/input.fits",
        "--output",
        "/campaign/pybdsf",
        "--execution-decision",
        "/repository/"
        + execution_decision.relative_to(repository_root).as_posix(),
        "--identity-review",
        "/repository/"
        + identity_review.relative_to(repository_root).as_posix(),
        "--container-digest",
        _PYBDSF_DIGEST,
    )


def _load_pybdsf_projection(output: Path) -> SourceUnionProjection:
    """Load and hash-check one child-derived source-union projection."""
    result = _json_object(output / "result.json")
    artifacts = result.get("artifacts")
    if (
        result.get("status") != "success"
        or result.get("container_digest") != _PYBDSF_DIGEST
        or result.get("schema_version") != _PYBDSF_RESULT_SCHEMA_VERSION
        or not isinstance(artifacts, dict)
    ):
        raise ValueError("released PyBDSF result identity changed")
    typed_artifacts = cast(dict[str, object], artifacts)
    required = {
        "source-catalogue.fits",
        "gaussian-catalogue.fits",
        "island-labels.fits",
        "source-union-labels.fits",
        "source-union-projection.json",
    }
    if set(typed_artifacts) != required:
        raise ValueError("released PyBDSF artifact set changed")
    for name, evidence in typed_artifacts.items():
        if not isinstance(evidence, dict) or evidence.get(
            "sha256"
        ) != file_sha256(output / name):
            raise ValueError("released PyBDSF artifact identity changed")
    document = _json_object(output / "source-union-projection.json")
    sources = tuple(
        SourceUnionSource(
            identifier=item["identifier"],
            member_component_ids=tuple(item["member_component_ids"]),
            native_support_labels=tuple(item["native_support_labels"]),
            centre_xy=tuple(item["centre_xy"]),
            integrated_flux_jy=item["integrated_flux_jy"],
        )
        for item in document["sources"]
    )
    components = tuple(
        SourceUnionComponent(
            identifier=item["identifier"],
            source_identifier=item["source_identifier"],
            native_support_label=item["native_support_label"],
            centre_xy=tuple(item["centre_xy"]),
            integrated_flux_jy=item["integrated_flux_jy"],
        )
        for item in document["components"]
    )
    return SourceUnionProjection(
        finder_id="released-pybdsf",
        sources=sources,
        components=components,
        native_owner_label_plane=np.asarray(
            load_fits_plane(output / "island-labels.fits"), dtype=np.int32
        ),
        source_union_label_plane=np.asarray(
            load_fits_plane(output / "source-union-labels.fits"),
            dtype=np.int32,
        ),
        native_topology_domain="island-owner",
        source_union_derivation=(
            "pybdsf-source-model-dominance-v1-derived-topology"
        ),
        unowned_native_support_labels=tuple(
            document["unowned_native_support_labels"]
        ),
    )


def _run_pybdsf(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    case_root: Path,
    execution_decision: Path,
    identity_review: Path,
    repository_root: Path,
    podman_executable: str,
    review: Any,
) -> dict[str, object]:
    """Run and compile the isolated released-PyBDSF source projection."""
    started = monotonic()
    completed = subprocess.run(
        _pybdsf_command(
            repository_root=repository_root,
            case_root=case_root,
            execution_decision=execution_decision,
            identity_review=identity_review,
            podman_executable=podman_executable,
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "released PyBDSF child failed: " + completed.stderr[-2000:]
        )
    result = _json_object(case_root / "pybdsf/result.json")
    return _compile_projection(
        dataset=dataset,
        recipe=recipe,
        projection=_load_pybdsf_projection(case_root / "pybdsf"),
        review=review,
        elapsed_seconds=monotonic() - started,
        candidate_revision=None,
        runtime_identity={
            "container_digest": _PYBDSF_DIGEST,
            "dependency_inventory_sha256": result[
                "dependency_inventory_sha256"
            ],
            "version": result["version"],
        },
    )


def _pair_worker(  # noqa: PLR0913, PLR0917
    dataset_document: dict[str, object],
    recipe_document: dict[str, object],
    repository_root: str,
    scratch: str,
    execution_decision: str,
    identity_review: str,
    podman_executable: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Run one paired realization in an isolated host worker."""
    dataset = DatasetRecord.model_validate(dataset_document)
    recipe = SyntheticRecipe.model_validate(recipe_document)
    root = Path(repository_root)
    review = load_phase_five_corrective_a_review(
        root / "config/contracts/phase-5-corrective-a-review.json"
    )
    input_id = f"{dataset.identifier}-seed-{recipe.seed}"
    with TemporaryDirectory(prefix=f".{input_id}.", dir=scratch) as raw:
        case_root = Path(raw)
        input_path = case_root / "input.fits"
        _write_input(input_path, dataset, recipe)
        current = _run_hebog(
            dataset=dataset,
            recipe=recipe,
            input_path=input_path,
            output=case_root / "hebog",
            executor=SerialExecutor(),
            review=review,
        )
        reference = _run_pybdsf(
            dataset=dataset,
            recipe=recipe,
            case_root=case_root,
            execution_decision=Path(execution_decision),
            identity_review=Path(identity_review),
            repository_root=root,
            podman_executable=podman_executable,
            review=review,
        )
    return current, reference


def _science_projection(summary: dict[str, object]) -> dict[str, object]:
    """Remove executor/runtime identity for exact Serial/Dask comparison."""
    excluded = {
        "candidate_revision",
        "elapsed_seconds",
        "record_sha256",
        "runtime_identity",
    }
    return {
        key: value for key, value in summary.items() if key not in excluded
    }


def _dask_checks(
    manifest: DatasetManifest,
    serial: dict[str, dict[str, object]],
    *,
    scratch: Path,
    scheduler_address: str,
) -> tuple[dict[str, object], ...]:
    """Compare 12 representative public runs with caller-owned Dask."""
    review = load_phase_five_corrective_a_review(_REVIEW)
    selected = manifest.datasets[:36:3]
    if len(selected) != _DASK_COMPARISON_COUNT:
        raise ValueError("sentinel Dask selection changed")
    output: list[dict[str, object]] = []
    with Client(scheduler_address, set_as_default=False) as client:
        executor = DaskExecutor(client)
        for dataset in selected:
            recipe = iter_dataset_recipes(dataset)[0]
            input_id = f"{dataset.identifier}-seed-{recipe.seed}"
            with TemporaryDirectory(
                prefix=f".dask-{input_id}.", dir=scratch
            ) as raw:
                case_root = Path(raw)
                input_path = case_root / "input.fits"
                _write_input(input_path, dataset, recipe)
                observed = _run_hebog(
                    dataset=dataset,
                    recipe=recipe,
                    input_path=input_path,
                    output=case_root / "hebog",
                    executor=executor,
                    review=review,
                )
            equal = canonical_sha256(_science_projection(observed)) == (
                canonical_sha256(_science_projection(serial[input_id]))
            )
            output.append({"equal": equal, "input_id": input_id})
    return tuple(output)


def execute(arguments: argparse.Namespace, identity: dict[str, Any]) -> None:
    """Consume one authority and publish exactly one terminal decision."""
    manifest = load_dataset_manifest(arguments.manifest)
    arguments.scratch.mkdir(parents=False)
    (arguments.scratch / "summaries").mkdir()
    summaries: list[dict[str, object]] = []
    try:
        payloads = [
            (dataset, recipe)
            for dataset in manifest.datasets
            for recipe in iter_dataset_recipes(dataset)
        ]
        with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
            futures = {
                pool.submit(
                    _pair_worker,
                    dataset.model_dump(mode="json"),
                    recipe.model_dump(mode="json"),
                    str(arguments.repository_root),
                    str(arguments.scratch),
                    str(arguments.execution_decision),
                    str(arguments.identity_review),
                    arguments.podman_executable,
                ): f"{dataset.identifier}-seed-{recipe.seed}"
                for dataset, recipe in payloads
            }
            for completed_count, future in enumerate(
                as_completed(futures), start=1
            ):
                pair = future.result()
                input_id = futures[future]
                _write_once_json(
                    arguments.scratch / "summaries" / f"{input_id}.json",
                    list(pair),
                )
                summaries.extend(pair)
                with (arguments.scratch / "progress.log").open(
                    "a", encoding="utf-8"
                ) as stream:
                    stream.write(
                        f"completed {completed_count}/{_IMAGE_COUNT} "
                        f"{input_id}\n"
                    )
        expected_pairs = tuple(
            (input_id, finder)
            for input_id in expected_input_ids(manifest)
            for finder in ("current-hebog", "released-pybdsf")
        )
        compiled = compile_summaries(summaries, expected_pairs=expected_pairs)
        serial = {
            cast(str, item["input_id"]): item
            for item in compiled
            if item["finder_id"] == "current-hebog"
        }
        dask = _dask_checks(
            manifest,
            serial,
            scratch=arguments.scratch,
            scheduler_address=arguments.dask_scheduler_address,
        )
        decision = evaluate_summaries(
            list(compiled),
            expected_cell_ids=tuple(
                cell_id(item) for item in manifest.datasets
            ),
            realizations_per_cell=4,
            dask_comparisons=dask,
        )
        decision.update(
            {
                "candidate": identity["candidate"],
                "evidence_schema_version": 3,
                "execution_decision_sha256": file_sha256(
                    arguments.execution_decision
                ),
                "identity_review_sha256": file_sha256(
                    arguments.identity_review
                ),
                "input_count": _IMAGE_COUNT,
                "pair_summary_canonical_sha256": canonical_sha256(compiled),
                "pybdsf_container_digest": _PYBDSF_DIGEST,
                "total_finder_executions": 348,
            }
        )
    except Exception as error:
        decision = {
            "candidate": identity["candidate"],
            "error_message": str(error),
            "error_type": type(error).__name__,
            "passed": False,
            "schema_version": 1,
            "status": "operational-fail",
        }
    _write_once_json(arguments.output, decision)


def _parse_args() -> argparse.Namespace:
    """Parse preflight or separately authorized execution inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--manifest", type=Path, default=_MANIFEST)
    parser.add_argument("--identity-review", type=Path, default=_IDENTITY)
    parser.add_argument("--execution-decision", type=Path)
    parser.add_argument("--scratch", type=Path, default=_SCRATCH)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dask-scheduler-address")
    parser.add_argument("--podman-executable", default="podman")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run a no-write preflight or consume one exact decision."""
    arguments = _parse_args()
    verified = verify_no_write(
        repository_root=arguments.repository_root,
        manifest_path=arguments.manifest,
        identity_path=arguments.identity_review,
        scratch=arguments.scratch,
        output=arguments.output,
        minimum_free_disk_gib=8,
        podman_executable=arguments.podman_executable,
    )
    if arguments.preflight_only:
        print(json.dumps(verified, sort_keys=True))
        return
    identity = verify_execution_authority(arguments)
    execute(arguments, identity)


if __name__ == "__main__":
    main()
