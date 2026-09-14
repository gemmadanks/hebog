#!/usr/bin/env python3
"""Verify or execute the bounded Phase 5 adaptive-background lane."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Generator
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import numpy as np
from astropy.io import fits

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest, public_api
from hebog.data_models.catalogues import SourceCatalogue
from hebog.executors import SerialExecutor
from hebog.executors.base import Executor
from hebog.io import FitsImageSource, read_catalogue_fits_product
from hebog.validation.adaptive_background_development import (
    AdaptiveDevelopmentCell,
    build_adaptive_development_matrix,
)
from hebog.validation.adaptive_background_lane import (
    AdaptiveDevelopmentObservation,
    AdaptiveExecutorComparison,
    AdaptiveScienceSummary,
    build_adaptive_development_manifest,
    build_adaptive_runtime_identity,
    evaluate_adaptive_development,
    input_identifier,
    installed_adaptive_runtime_identity,
    source_signal_and_truth,
)
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    generate_synthetic_image,
    iter_dataset_recipes,
    recipe_sha256,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.products import load_fits_plane

_PRE_REVIEW = Path(
    "config/contracts/phase-5-adaptive-background-development-pre-review.json"
)
_PRE_REVIEW_SHA256 = (
    "6287ad3ef734c91142637142f04abebfb7226253e9e49060af686fe07292eed4"
)
_PUBLIC_IDENTITY = Path(
    "config/contracts/phase-5-public-interface-identity-review.json"
)
_PUBLIC_IDENTITY_SHA256 = (
    "a521c656683cdae8b8d2250a3d29dee716c4ff774a25e23556301b21e5d898f8"
)
_CANDIDATE_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_EXPECTED_INPUTS = 144
_EXPECTED_DASK = 12
_INTERNAL_CONFIG_COUNT = 5
_MANIFEST = Path(
    "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_IDENTITY = Path(
    "config/contracts/phase-5-adaptive-background-development-identity-review.json"
)
_IMPLEMENTATION = Path(
    "config/contracts/"
    "phase-5-adaptive-background-development-implementation-decision.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/adaptive-background-development-decision.json"
)
_PROGRAM_BINDING_PATHS = {
    "approved_design": (
        "src/hebog/validation/adaptive_background_development.py"
    ),
    "evaluator_and_population": (
        "src/hebog/validation/adaptive_background_lane.py"
    ),
    "freezer": (
        "scripts/validation/freeze_phase5_adaptive_background_development.py"
    ),
    "runner": (
        "scripts/validation/run_phase5_adaptive_background_development.py"
    ),
}
_EXPECTED_EXECUTION_AUTHORIZATION = {
    "candidate_execution_authorized": True,
    "coarse_control_execution_authorized": True,
    "cutover_authorized": False,
    "development_lane_execution_authorized": True,
    "fresh_qualification_authorized": False,
    "optimization_authorized": False,
    "pybdsf_execution_authorized": False,
    "release_authorized": False,
    "replay_authorized": False,
    "rescoring_authorized": False,
    "source_finding_change_authorized": False,
    "threshold_or_margin_tuning_authorized": False,
    "viewed_data_execution_authorized": False,
}


@dataclass(frozen=True, slots=True)
class _DevelopmentTask:
    """One exact synthetic realization and its approved matrix identity."""

    cell: AdaptiveDevelopmentCell
    dataset: DatasetRecord
    recipe: SyntheticRecipe
    input_id: str


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Load one required JSON object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _object_field(
    value: dict[str, Any], field: str, *, label: str
) -> dict[str, Any]:
    """Return one required nested object with an explicit failure."""
    nested: object = value.get(field)
    if not isinstance(nested, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], nested)


def _verify_public_candidate_identity(
    repository_root: Path,
    review: dict[str, Any],
) -> None:
    """Verify the frozen public facade and complete candidate source set."""
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if (
        review.get("status") != "frozen-non-executable"
        or review.get("algorithm_candidate") != expected_candidate
        or review.get("public_configuration")
        != {
            "continuum_is_default": True,
            "detection_threshold_sigma": 5.0,
            "island_threshold_sigma": 3.0,
            "maximum_island_pixels": None,
            "minimum_island_pixels": 7,
            "profiles": ["compact", "continuum"],
        }
    ):
        raise ValueError("public candidate identity changed")
    interface_files = _object_field(
        review,
        "interface_file_sha256",
        label="public interface file identities",
    )
    scientific_modules = _object_field(
        review,
        "scientific_module_sha256",
        label="public scientific module identities",
    )
    for relative_path, expected_sha256 in interface_files.items():
        if not isinstance(expected_sha256, str):
            raise ValueError("public interface source identity is malformed")
        if file_sha256(repository_root / relative_path) != expected_sha256:
            raise ValueError("public candidate source changed")
    for module_name, expected_sha256 in scientific_modules.items():
        if not isinstance(expected_sha256, str):
            raise ValueError("public scientific source identity is malformed")
        relative_path = Path("src", *module_name.split(".")).with_suffix(".py")
        if file_sha256(repository_root / relative_path) != expected_sha256:
            raise ValueError("public candidate source changed")


def _expected_execution() -> dict[str, object]:
    """Return the exact path-independent shape of a future lane run."""
    return {
        "candidate_executions": _EXPECTED_INPUTS,
        "coarse_control_executions": _EXPECTED_INPUTS,
        "existing_dask_executions": _EXPECTED_DASK,
        "existing_dask_scheduler": "caller-owned-runtime-address",
        "identity_review": str(_IDENTITY),
        "manifest": str(_MANIFEST),
        "output": str(_OUTPUT),
        "scratch": str(_SCRATCH),
        "workers": 2,
    }


def _public_config() -> SourceFinderConfig:
    """Return the exact frozen public continuum configuration."""
    return SourceFinderConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=7,
        profile="continuum",
    )


def _coarse_control_configs(configs: tuple[Any, ...]) -> tuple[Any, ...]:
    """Disable only adaptive refinement in one internal diagnostic policy."""
    if len(configs) != _INTERNAL_CONFIG_COUNT:
        raise ValueError("candidate internal configuration shape changed")
    detection = configs[0]
    background_rms = getattr(detection, "background_rms", None)
    if background_rms is None or background_rms.adaptive is None:
        raise ValueError("candidate adaptive background policy is absent")
    return (
        replace(
            detection,
            background_rms=replace(background_rms, adaptive=None),
        ),
        *configs[1:],
    )


@contextmanager
def _coarse_control_configuration() -> Generator[None]:
    """Install and reliably restore the one-factor coarse counterfactual."""
    import hebog.validation.hebog_campaign as campaign  # noqa: PLC0415

    original = campaign.phase_five_corrected_candidate_configs

    def coarse_only() -> tuple[Any, ...]:
        return _coarse_control_configs(original())

    campaign.phase_five_corrected_candidate_configs = coarse_only
    try:
        yield
    finally:
        campaign.phase_five_corrected_candidate_configs = original


@contextmanager
def _captured_public_science() -> Generator[dict[str, Any]]:
    """Capture array state and trigger positions without altering products."""
    captured: dict[str, Any] = {}
    original_analysis = public_api._analyse_image
    original_detection = public_api.run_detection_stage

    def detection(*args: Any, **kwargs: Any) -> Any:
        result = original_detection(*args, **kwargs)
        captured["adaptive_candidate_positions_yx"] = tuple(
            sorted(result.adaptive_candidate_positions_yx)
        )
        return result

    def analysis(*args: Any, **kwargs: Any) -> Any:
        products = original_analysis(*args, **kwargs)
        captured["products"] = products
        return products

    public_api.run_detection_stage = detection
    public_api._analyse_image = analysis
    try:
        yield captured
    finally:
        public_api.run_detection_stage = original_detection
        public_api._analyse_image = original_analysis


def _tasks(manifest: DatasetManifest) -> tuple[_DevelopmentTask, ...]:
    """Pair the exact checked-in manifest with every approved cell and seed."""
    expected = build_adaptive_development_manifest()
    if manifest != expected:
        raise ValueError("adaptive development manifest identity changed")
    matrix = build_adaptive_development_matrix()
    tasks = tuple(
        _DevelopmentTask(
            cell=cell,
            dataset=dataset,
            recipe=recipe,
            input_id=input_identifier(cell, recipe.seed),
        )
        for cell, dataset in zip(matrix, manifest.datasets, strict=True)
        for recipe in iter_dataset_recipes(dataset)
    )
    if len(tasks) != _EXPECTED_INPUTS or len(
        {task.input_id for task in tasks}
    ) != len(tasks):
        raise ValueError("adaptive development task population changed")
    return tasks


def _write_input(path: Path, task: _DevelopmentTask) -> None:
    """Materialize one deterministic public FITS input in scratch."""
    values = generate_synthetic_image(task.recipe)
    data = np.asarray(values[np.newaxis, np.newaxis, :, :], dtype=np.float32)
    realization_dataset = DatasetRecord.model_validate(
        {
            **task.dataset.model_dump(mode="python"),
            "recipe": task.recipe,
            "recipe_sha256": recipe_sha256(task.recipe),
            "noise_realization_seeds": (),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(
        data=data,
        header=synthetic_fits_header(realization_dataset),
    ).writeto(path)


def _true_integrated_flux_jy(dataset: DatasetRecord) -> float:
    """Convert analytic pixel brightness to restoring-beam-normalized Jy."""
    group = dataset.multiscale_truth_groups[0]
    beam_area = (
        2.0
        * np.pi
        * dataset.beam.major_fwhm_pixels
        * dataset.beam.minor_fwhm_pixels
        / (8.0 * np.log(2.0))
    )
    return group.reference_integrated_brightness_jy_pixels_per_beam / beam_area


def _science_summary(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    catalogue: SourceCatalogue,
    mask: np.ndarray,
    background: np.ndarray,
    rms: np.ndarray,
) -> AdaptiveScienceSummary:
    """Reduce one finder result to bounded analytic-truth evidence."""
    _, truth, true_rms = source_signal_and_truth(recipe)
    published = np.asarray(mask, dtype=np.bool_)
    estimated_background = np.asarray(background, dtype=np.float64)
    estimated_rms = np.asarray(rms, dtype=np.float64)
    expected_shape = recipe.shape_yx
    if any(
        values.shape != expected_shape
        for values in (published, estimated_background, estimated_rms)
    ):
        raise ValueError("adaptive development science product shape changed")
    if (
        not np.all(np.isfinite(estimated_background[truth]))
        or not np.all(np.isfinite(estimated_rms[truth]))
        or not np.all(estimated_rms[truth] > 0)
    ):
        raise ValueError(
            "adaptive development science product is invalid over "
            "truth support"
        )
    intersection = int(np.count_nonzero(published & truth))
    union = int(np.count_nonzero(published | truth))
    truth_count = int(np.count_nonzero(truth))
    if truth_count == 0:
        raise ValueError("adaptive development analytic truth is empty")
    support_recall = intersection / truth_count
    mask_iou = intersection / union if union else 0.0
    estimated_flux = sum(
        source.association_aperture_integrated_flux_jy
        if source.association_aperture_integrated_flux_jy is not None
        else source.flux.integrated_flux_jy
        for source in catalogue.sources
    )
    true_flux = _true_integrated_flux_jy(dataset)
    background_error = np.abs(
        (estimated_background[truth] - recipe.background) / true_rms[truth]
    )
    rms_error = (estimated_rms[truth] - true_rms[truth]) / true_rms[truth]
    return AdaptiveScienceSummary(
        product_valid=True,
        completeness=float(intersection > 0 and len(catalogue.sources) > 0),
        integrated_flux_absolute_fractional_error=abs(
            estimated_flux - true_flux
        )
        / true_flux,
        mask_iou=mask_iou,
        split=len(catalogue.sources) > 1,
        support_recall=support_recall,
        background_error_median_rms=float(np.median(background_error)),
        background_error_p95_rms=float(np.percentile(background_error, 95.0)),
        rms_error_median_fraction=float(np.median(rms_error)),
        rms_error_p95_fraction=float(np.percentile(rms_error, 95.0)),
        source_count=len(catalogue.sources),
    )


def _activation_intersects_truth(
    positions_yx: tuple[tuple[float, float], ...],
    truth: np.ndarray,
) -> bool:
    """Return whether one exact adaptive candidate lies in truth support."""
    height, width = truth.shape
    return any(
        0 <= round(y) < height
        and 0 <= round(x) < width
        and bool(truth[round(y), round(x)])
        for y, x in positions_yx
    )


def _candidate_products(
    task: _DevelopmentTask,
    input_path: Path,
    output: Path,
    executor: Executor,
) -> tuple[AdaptiveScienceSummary, tuple[tuple[float, float], ...]]:
    """Run the exact public candidate and reduce its validated products."""
    request = SourceFinderRequest(
        image_path=input_path,
        output_directory=output,
        run_id=f"adaptive-{task.input_id}",
    )
    with _captured_public_science() as captured:
        result = hebog.find_sources(request, _public_config(), executor)
    products = captured.get("products")
    positions = captured.get("adaptive_candidate_positions_yx")
    if products is None or not isinstance(positions, tuple):
        raise ValueError("public candidate diagnostic capture is incomplete")
    catalogue = read_catalogue_fits_product(result.catalogue)
    mask = load_fits_plane(result.mask.path)
    return (
        _science_summary(
            dataset=task.dataset,
            recipe=task.recipe,
            catalogue=catalogue,
            mask=mask,
            background=products.background,
            rms=products.rms,
        ),
        positions,
    )


def _coarse_products(
    task: _DevelopmentTask,
    input_path: Path,
    work: Path,
) -> tuple[AdaptiveScienceSummary, float]:
    """Run the internal one-factor coarse-only diagnostic in memory."""
    source = FitsImageSource(input_path)
    metadata = source.metadata()
    header = cast(fits.Header, fits.getheader(input_path))
    request = SourceFinderRequest(
        image_path=input_path,
        output_directory=work / "unused-public-output",
        run_id=f"coarse-{task.input_id}",
    )
    with _coarse_control_configuration():
        products = public_api._analyse_image(
            request,
            source,
            metadata,
            SerialExecutor(),
            work,
            header=header,
        )
    catalogue, mask = public_api._public_catalogue(
        products,
        metadata,
        run_id=request.run_id,
        profile="continuum",
    )
    valid = np.isfinite(products.rms) & (products.rms > 0)
    normalized = np.full(products.image.shape, np.nan, dtype=np.float64)
    normalized[valid] = (
        products.image[valid] - products.background[valid]
    ) / products.rms[valid]
    return (
        _science_summary(
            dataset=task.dataset,
            recipe=task.recipe,
            catalogue=catalogue,
            mask=mask,
            background=products.background,
            rms=products.rms,
        ),
        float(np.nanmax(normalized)),
    )


def _run_serial_task(task: _DevelopmentTask, scratch: Path) -> dict[str, Any]:
    """Produce one paired observation in an isolated restartable directory."""
    directory = scratch / task.input_id
    directory.mkdir(parents=False, exist_ok=False)
    input_path = directory / "image.fits"
    _write_input(input_path, task)
    adaptive, positions = _candidate_products(
        task,
        input_path,
        directory / "candidate-products",
        SerialExecutor(),
    )
    coarse, pre_adaptive = _coarse_products(
        task,
        input_path,
        directory / "coarse-work",
    )
    _, truth, _ = source_signal_and_truth(task.recipe)
    observation = AdaptiveDevelopmentObservation(
        input_id=task.input_id,
        cell_id=task.cell.cell_id,
        seed=task.recipe.seed,
        trigger_cohort=task.cell.trigger_cohort,
        pre_adaptive_maximum_sigma=pre_adaptive,
        adaptive_candidate_positions_yx=positions,
        adaptive_activation_intersects_truth=_activation_intersects_truth(
            positions, truth
        ),
        adaptive=adaptive,
        coarse=coarse,
    )
    payload = observation.model_dump(mode="json")
    (directory / "observation.json").write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _science_sha256(
    summary: AdaptiveScienceSummary,
    positions: tuple[tuple[float, float], ...],
    activation_intersects_truth: bool,
) -> str:
    """Hash scheduler-independent science while excluding runtime metadata."""
    return canonical_sha256(
        {
            "adaptive": summary.model_dump(mode="json"),
            "adaptive_activation_intersects_truth": (
                activation_intersects_truth
            ),
            "adaptive_candidate_positions_yx": positions,
        }
    )


def _verify_existing_dask_runtime(
    client: Any,
    expected: object,
) -> None:
    """Require at least one caller-owned worker with the frozen runtime."""
    worker_identities: object = client.run(installed_adaptive_runtime_identity)
    if (
        not isinstance(worker_identities, dict)
        or not worker_identities
        or any(value != expected for value in worker_identities.values())
    ):
        raise ValueError("adaptive Dask worker runtime identity changed")


def _dask_comparison(
    task: _DevelopmentTask,
    serial: AdaptiveDevelopmentObservation,
    scratch: Path,
    executor: Executor,
) -> AdaptiveExecutorComparison:
    """Repeat one above-trigger candidate on a caller-owned Dask scheduler."""
    input_path = scratch / task.input_id / "image.fits"
    dask, positions = _candidate_products(
        task,
        input_path,
        scratch / task.input_id / "dask-products",
        executor,
    )
    _, truth, _ = source_signal_and_truth(task.recipe)
    dask_intersects = _activation_intersects_truth(positions, truth)
    return AdaptiveExecutorComparison(
        input_id=task.input_id,
        serial_science_sha256=_science_sha256(
            serial.adaptive,
            serial.adaptive_candidate_positions_yx,
            serial.adaptive_activation_intersects_truth,
        ),
        existing_dask_science_sha256=_science_sha256(
            dask,
            positions,
            dask_intersects,
        ),
    )


def _verify_upstream_identities(repository_root: Path) -> None:
    """Verify the approved review and complete public candidate source set."""
    if file_sha256(repository_root / _PRE_REVIEW) != _PRE_REVIEW_SHA256:
        raise ValueError("approved adaptive pre-review identity changed")
    public_path = repository_root / _PUBLIC_IDENTITY
    if file_sha256(public_path) != _PUBLIC_IDENTITY_SHA256:
        raise ValueError("public candidate identity review changed")
    _verify_public_candidate_identity(
        repository_root,
        _json_object(public_path, label="public candidate identity review"),
    )


def _verify_program_bindings(
    repository_root: Path,
    identity: dict[str, Any],
) -> None:
    """Verify the exact complete prospective program set."""
    bindings = _object_field(
        identity,
        "program_bindings",
        label="adaptive identity review program_bindings",
    )
    if set(bindings) != set(_PROGRAM_BINDING_PATHS):
        raise ValueError("adaptive development program binding set changed")
    for name, expected_path in _PROGRAM_BINDING_PATHS.items():
        binding = bindings.get(name)
        if not isinstance(binding, dict):
            raise ValueError("adaptive program binding must be a JSON object")
        if binding.get("path") != expected_path or file_sha256(
            repository_root / expected_path
        ) != binding.get("sha256"):
            raise ValueError("adaptive development program identity changed")


def _verify_frozen_identity(
    repository_root: Path,
    identity: dict[str, Any],
    manifest_path: Path,
) -> None:
    """Verify non-executable identity, artifact, runtime, and command shape."""
    authorization = _object_field(
        identity,
        "authorization",
        label="adaptive identity review authorization",
    )
    if identity.get("status") != "frozen-non-executable" or set(
        authorization.values()
    ) != {False}:
        raise ValueError("adaptive identity review authorization changed")
    candidate = _object_field(
        identity,
        "candidate",
        label="adaptive identity review candidate",
    )
    expected_candidate = {
        "configuration_sha256": _CANDIDATE_CONFIGURATION_SHA256,
        "entrypoint": "hebog.find_sources",
        "revision": _CANDIDATE_REVISION,
        "source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
    }
    if candidate != expected_candidate:
        raise ValueError("adaptive development candidate identity changed")
    implementation = _object_field(
        identity,
        "implementation_decision",
        label="adaptive implementation decision binding",
    )
    if implementation.get("path") != str(_IMPLEMENTATION) or file_sha256(
        repository_root / _IMPLEMENTATION
    ) != implementation.get("sha256"):
        raise ValueError("adaptive implementation decision identity changed")
    _verify_program_bindings(repository_root, identity)
    population = _object_field(
        identity,
        "population",
        label="adaptive identity review population",
    )
    if file_sha256(manifest_path) != population.get("manifest_sha256"):
        raise ValueError("adaptive development manifest file changed")
    if identity.get("runtime") != build_adaptive_runtime_identity(
        repository_root
    ):
        raise ValueError("adaptive development runtime identity changed")
    expected_execution = _expected_execution()
    if identity.get(
        "expected_execution"
    ) != expected_execution or identity.get(
        "expected_execution_sha256"
    ) != canonical_sha256(expected_execution):
        raise ValueError("adaptive expected execution identity changed")


def verify_no_write(
    *,
    repository_root: Path,
    manifest_path: Path,
    identity_path: Path,
    scratch: Path,
    output: Path,
) -> dict[str, object]:
    """Verify the complete frozen population and every executable binding."""
    if scratch.exists() or output.exists():
        raise FileExistsError(
            "adaptive no-write output namespace must be absent"
        )
    _verify_upstream_identities(repository_root)
    identity = _json_object(identity_path, label="adaptive identity review")
    _verify_frozen_identity(repository_root, identity, manifest_path)
    manifest = DatasetManifest.model_validate_json(manifest_path.read_bytes())
    tasks = _tasks(manifest)
    dask_tasks = tuple(
        task
        for task in tasks
        if task.cell.trigger_cohort == "above"
        and task.recipe.seed == task.cell.noise_seeds[0]
    )
    if len(dask_tasks) != _EXPECTED_DASK:
        raise ValueError("adaptive Dask invariance population changed")
    return {
        "status": "pass",
        "candidate_execution_count": len(tasks),
        "coarse_control_execution_count": len(tasks),
        "existing_dask_execution_count": len(dask_tasks),
        "candidate_execution_started": False,
        "manifest_sha256": file_sha256(manifest_path),
        "identity_review_sha256": file_sha256(identity_path),
    }


def _verify_execution_authority(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Require one exact separately approved execution decision."""
    if arguments.workers != 2:  # noqa: PLR2004
        raise PermissionError(
            "adaptive development requires exactly two workers"
        )
    repository_root = arguments.repository_root.resolve()
    expected_paths = {
        "identity review": (
            arguments.identity_review,
            repository_root / _IDENTITY,
        ),
        "manifest": (arguments.manifest, repository_root / _MANIFEST),
        "output": (arguments.output, repository_root / _OUTPUT),
        "scratch": (arguments.scratch, _SCRATCH),
    }
    if any(
        supplied.resolve() != expected.resolve()
        for supplied, expected in expected_paths.values()
    ):
        raise PermissionError("adaptive development execution path changed")
    decision_path = arguments.execution_decision
    if decision_path is None:
        raise PermissionError("an exact execution decision is required")
    decision = _json_object(decision_path, label="adaptive execution decision")
    authorization = _object_field(
        decision,
        "authorization",
        label="adaptive execution decision authorization",
    )
    identity = _json_object(
        arguments.identity_review,
        label="adaptive identity review",
    )
    expected_execution_sha256 = canonical_sha256(_expected_execution())
    if (
        decision.get("status") != "authorized-for-one-development-lane"
        or authorization != _EXPECTED_EXECUTION_AUTHORIZATION
        or decision.get("identity_review_sha256")
        != file_sha256(arguments.identity_review)
        or decision.get("expected_execution_sha256")
        != expected_execution_sha256
        or identity.get("expected_execution_sha256")
        != expected_execution_sha256
    ):
        raise PermissionError("exact adaptive execution authority is invalid")
    return decision


def _atomic_write(path: Path, value: object) -> None:
    """Publish one terminal decision without overwriting existing evidence."""
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite adaptive decision: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(
                (
                    json.dumps(
                        value, allow_nan=False, indent=2, sort_keys=True
                    )
                    + "\n"
                ).encode()
            )
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _execute(
    arguments: argparse.Namespace, tasks: tuple[_DevelopmentTask, ...]
) -> None:
    """Execute one approved lane and atomically publish its decision."""
    if not arguments.dask_scheduler:
        raise ValueError("existing Dask scheduler address is required")
    arguments.scratch.mkdir(parents=True, exist_ok=False)
    observations_by_id: dict[str, AdaptiveDevelopmentObservation] = {}
    progress_path = arguments.scratch / "progress.log"
    with (
        progress_path.open("x", encoding="utf-8") as progress,
        ProcessPoolExecutor(max_workers=arguments.workers) as executor,
    ):
        futures = {
            executor.submit(_run_serial_task, task, arguments.scratch): task
            for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            observation = AdaptiveDevelopmentObservation.model_validate(
                future.result()
            )
            observations_by_id[observation.input_id] = observation
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{len(tasks)} "
                f"input={observation.input_id}\n"
            )
            progress.flush()
    observations = tuple(observations_by_id[task.input_id] for task in tasks)
    above_tasks = tuple(
        task
        for task in tasks
        if task.cell.trigger_cohort == "above"
        and task.recipe.seed == task.cell.noise_seeds[0]
    )
    from distributed import Client  # noqa: PLC0415

    from hebog.executors import DaskExecutor  # noqa: PLC0415

    identity = _json_object(
        arguments.identity_review,
        label="adaptive identity review",
    )
    runtime = _object_field(
        identity,
        "runtime",
        label="adaptive runtime identity",
    )
    with Client(arguments.dask_scheduler, set_as_default=False) as client:
        _verify_existing_dask_runtime(client, runtime.get("installed"))
        dask_executor = DaskExecutor(client)
        comparisons = tuple(
            _dask_comparison(
                task,
                observations_by_id[task.input_id],
                arguments.scratch,
                dask_executor,
            )
            for task in above_tasks
        )
    decision = evaluate_adaptive_development(observations, comparisons)
    decision["provenance"] = {
        "execution_decision_sha256": file_sha256(arguments.execution_decision),
        "identity_review_sha256": file_sha256(arguments.identity_review),
        "manifest_sha256": file_sha256(arguments.manifest),
    }
    _atomic_write(arguments.output, decision)


def main() -> None:
    """Verify all identities or consume one exact future execution approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--identity-review", required=True, type=Path)
    parser.add_argument("--execution-decision", type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--dask-scheduler")
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.repository_root = arguments.repository_root.resolve()
    if arguments.workers < 1:
        raise ValueError("adaptive development workers must be positive")
    verification = verify_no_write(
        repository_root=arguments.repository_root,
        manifest_path=arguments.manifest,
        identity_path=arguments.identity_review,
        scratch=arguments.scratch,
        output=arguments.output,
    )
    if arguments.verify_only:
        print(json.dumps(verification, allow_nan=False, sort_keys=True))
        return
    _verify_execution_authority(arguments)
    manifest = DatasetManifest.model_validate_json(
        arguments.manifest.read_bytes()
    )
    _execute(arguments, _tasks(manifest))


if __name__ == "__main__":
    main()
