#!/usr/bin/env python3
"""Run the one-look compact Phase 5 held-out sentinel when authorized."""

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
from collections.abc import Generator
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, cast

import numpy as np
from astropy.io import fits
from distributed import Client

import hebog
from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest
from hebog.executors import DaskExecutor, Executor, SerialExecutor
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_image,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.products import (
    load_fits_plane,
    load_pybdsf_gaussian_catalogue,
)

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_public_runner = importlib.import_module(
    "scripts.benchmark.run_phase5_public_finder_hebog"
)
_compiler = importlib.import_module(
    "scripts.validation.compile_phase5_compact_held_out_sentinel"
)
_evaluator = importlib.import_module(
    "scripts.validation.evaluate_phase5_compact_held_out_sentinel"
)
_population = importlib.import_module(
    "scripts.validation.phase5_compact_held_out_sentinel"
)
public_hebog_configuration_sha256 = (
    _public_runner.public_hebog_configuration_sha256
)
compile_finder_summary = _compiler.compile_finder_summary
compile_summaries = _compiler.compile_summaries
evaluate_summaries = _evaluator.evaluate_summaries
audit_manifest = _population.audit_manifest
cell_id = _population.cell_id
expected_input_ids = _population.expected_input_ids

_MANIFEST = _ROOT / "config/datasets/phase-5-compact-held-out-sentinel.json"
_IDENTITY = (
    _ROOT
    / "config/contracts/phase-5-compact-held-out-sentinel-identity-review.json"
)
_SCRATCH = Path("/private/tmp/hebog-phase5-compact-held-out-sentinel")
_OUTPUT = _ROOT / "benchmark-results/phase-5/compact-held-out-sentinel.json"
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
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify every frozen program byte before any execution is possible."""
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
    """Validate the complete frozen program without generating an image."""
    root = repository_root.resolve()
    identity = _json_object(identity_path)
    if identity.get("status") != "frozen-non-executable" or set(
        cast(dict[str, object], identity.get("authorization", {})).values()
    ) != {False}:
        raise ValueError("sentinel identity is not frozen non-executable")
    _identity_bindings(root, identity)
    candidate = identity.get("candidate")
    if candidate != {
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
    *,
    execution_decision: Path,
    identity_review: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Require a separate exact one-use authority document."""
    identity = _json_object(identity_review)
    decision = _json_object(execution_decision)
    expected_execution = identity.get("expected_execution")
    expected_sha256 = identity.get("expected_execution_sha256")
    if (
        identity.get("status") != "frozen-non-executable"
        or canonical_sha256(expected_execution) != expected_sha256
        or decision.get("status")
        != "authorized-for-one-compact-held-out-sentinel"
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


def verify_child_execution_authority(
    *,
    execution_decision: Path,
    identity_review: Path,
) -> None:
    """Expose only the authority check needed by the isolated child."""
    _verify_decision(
        execution_decision=execution_decision,
        identity_review=identity_review,
    )


def verify_execution_authority(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Bind CLI paths and concurrency to one separately approved execution."""
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
    for key, value in observed.items():
        if expected.get(key) != value:
            raise PermissionError("exact execution decision is required")
    return identity


@contextmanager
def _captured_science() -> Generator[list[Any]]:
    """Observe the public facade's exact terminal products without mutation."""
    original = public_api._analyse_image
    captured: list[Any] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        products = original(*args, **kwargs)
        captured.append(products)
        return products

    public_api._analyse_image = wrapper
    try:
        yield captured
    finally:
        public_api._analyse_image = original


def _write_input(
    path: Path, dataset: DatasetRecord, recipe: SyntheticRecipe
) -> None:
    """Materialize one bounded shared FITS plane for both exact finders."""
    image = generate_synthetic_image(recipe)
    header = synthetic_fits_header(dataset)
    fits.PrimaryHDU(
        data=np.asarray(image[np.newaxis, np.newaxis], dtype=np.float32),
        header=header,
    ).writeto(path)


def _run_hebog(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    input_path: Path,
    output: Path,
    executor: Executor,
    review: Any,
) -> dict[str, object]:
    """Run the installed top-level facade and compile its Gaussian products."""
    started = monotonic()
    run_id = f"sentinel-{dataset.identifier}-{recipe.seed}"
    with _captured_science() as captured:
        result = hebog.find_sources(
            SourceFinderRequest(input_path, output, run_id),
            _CONFIG,
            executor,
        )
    if len(captured) != 1 or captured[0].terminal is None:
        raise ValueError("public Hebog terminal products are unavailable")
    terminal = captured[0].terminal
    catalogue = tuple(terminal.component_catalogue)
    if result.gaussian_component_count != len(catalogue):
        raise ValueError("public Hebog Gaussian population changed")
    return compile_finder_summary(
        dataset=dataset,
        recipe=recipe,
        finder_id="current-hebog",
        catalogue=catalogue,
        label_plane=terminal.measurement_component_labels,
        header=cast(fits.Header, fits.getheader(input_path)),
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
    """Return one network-disabled immutable-image child command."""
    decision_relative = execution_decision.relative_to(repository_root)
    identity_relative = identity_review.relative_to(repository_root)
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
        "/repository/scripts/benchmark/run_phase5_compact_held_out_pybdsf.py",
        "--input",
        "/campaign/input.fits",
        "--output",
        "/campaign/pybdsf",
        "--execution-decision",
        f"/repository/{decision_relative.as_posix()}",
        "--identity-review",
        f"/repository/{identity_relative.as_posix()}",
        "--container-digest",
        _PYBDSF_DIGEST,
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
    """Run and immediately compile the exact isolated released PyBDSF leg."""
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
    output = case_root / "pybdsf"
    result = _json_object(output / "result.json")
    if (
        result.get("status") != "success"
        or result.get("container_digest") != _PYBDSF_DIGEST
    ):
        raise ValueError("released PyBDSF result identity changed")
    catalogue = load_pybdsf_gaussian_catalogue(
        output / "gaussian-catalogue.fits"
    )
    labels = np.asarray(
        load_fits_plane(output / "island-labels.fits"), dtype=np.int32
    )
    return compile_finder_summary(
        dataset=dataset,
        recipe=recipe,
        finder_id="released-pybdsf",
        catalogue=catalogue,
        label_plane=labels,
        header=cast(fits.Header, fits.getheader(case_root / "input.fits")),
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
    """Run one paired image in an isolated host worker."""
    dataset = DatasetRecord.model_validate(dataset_document)
    recipe = SyntheticRecipe.model_validate(recipe_document)
    review = load_phase_five_corrective_a_review(
        Path(repository_root)
        / "config/contracts/phase-5-corrective-a-review.json"
    )
    input_id = f"{dataset.identifier}-seed-{recipe.seed}"
    with TemporaryDirectory(prefix=f".{input_id}.", dir=scratch) as raw:
        case_root = Path(raw)
        input_path = case_root / "input.fits"
        _write_input(input_path, dataset, recipe)
        hebog_summary = _run_hebog(
            dataset=dataset,
            recipe=recipe,
            input_path=input_path,
            output=case_root / "hebog",
            executor=SerialExecutor(),
            review=review,
        )
        pybdsf_summary = _run_pybdsf(
            dataset=dataset,
            recipe=recipe,
            case_root=case_root,
            execution_decision=Path(execution_decision),
            identity_review=Path(identity_review),
            repository_root=Path(repository_root),
            podman_executable=podman_executable,
            review=review,
        )
    return hebog_summary, pybdsf_summary


def _science_projection(summary: dict[str, object]) -> dict[str, object]:
    """Remove runtime and executor identity for Serial/Dask comparison."""
    return {
        key: summary[key]
        for key in (
            "catalogue_count",
            "metrics",
            "native_support_count",
            "ownership_valid",
            "product_valid",
            "truth_group_count",
        )
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


def _write_once_json(path: Path, value: object) -> None:
    """Atomically publish one canonical JSON document without overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError(f"refusing to overwrite terminal output: {path}")
    temporary.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def execute(arguments: argparse.Namespace, identity: dict[str, Any]) -> None:
    """Consume one authority and publish exactly one terminal decision."""
    manifest = load_dataset_manifest(arguments.manifest)
    arguments.scratch.mkdir(parents=False)
    (arguments.scratch / "summaries").mkdir()
    progress = arguments.scratch / "progress.log"
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
                with progress.open("a", encoding="utf-8") as stream:
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
