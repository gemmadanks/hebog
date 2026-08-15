#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Re-evaluate the prospective candidate on every viewed Phase 5 image."""

from __future__ import annotations

import argparse
import json
import runpy
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.campaign_runtime import canonical_sha256
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.datasets import DatasetRecord
from hebog.validation.external_runners import (
    ExternalRunArtifact,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.hebog_campaign import (
    corrected_hebog_campaign_configuration,
    process_hebog_image,
)
from hebog.validation.post_campaign_science import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    diagnose_compact_component_realization,
    evaluate_post_campaign_candidate_products,
)
from hebog.validation.products import (
    build_hebog_segment_catalogue,
    load_fits_plane,
    write_comparison_catalogue,
)

_ROOT = Path(__file__).parents[2]
_COMPILER_PATH = (
    _ROOT
    / "scripts/validation/compile_phase5_external_post_failure_campaign.py"
)
_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-post-failure-endpoint-registry.json"
)
_EVALUATOR_PATH = (
    _ROOT
    / "scripts/validation/evaluate_phase5_external_post_failure_decision.py"
)
_EVALUATION_PATH = (
    _ROOT / "config/contracts/phase-5-external-post-failure-evaluation.json"
)
_BASE_REVIEW_PATH = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_HISTORIC_PREFIXES = (
    "external-source-finder",
    "external-successor",
    "external-confirmation",
    "external-post-failure",
)


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite, deterministic development record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _git_revision() -> str:
    """Return the exact checked-out revision used for this replay."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("cumulative replay requires a clean source checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=_ROOT,
        text=True,
    ).strip()


def _candidate_configuration_sha256() -> str:
    """Bind compact and Continuum prospective science settings together."""
    return canonical_sha256(
        {
            "compact": corrected_hebog_campaign_configuration(),
            "continuum": {
                "base_review_sha256": file_sha256(_BASE_REVIEW_PATH),
                "measurement_aperture_radius_beams": (
                    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
                ),
                "position_policy": (
                    "residual-b3-at-or-below-peak-to-mean-3-otherwise-original"
                ),
                "support_policy": "refined-residual-b3-multiscale-boundary",
            },
        }
    )


def _install_historical_source_view(namespace: dict[str, Any]) -> None:
    """Verify closed evidence against its frozen source identity only."""
    helpers = namespace["_HELPERS"]
    loader_globals = helpers["load_post_failure_population"].__globals__
    historical_sha256 = helpers["_SOURCE_TREE_SHA256"]
    loader_globals["source_tree_sha256"] = lambda _root: historical_sha256


def _input_artifact_path(
    bundle: Any,
    input_path: Path,
    role: str,
) -> Path:
    """Resolve one already verified common input artifact."""
    artifact = next(item for item in bundle.artifacts if item.role == role)
    return input_path.parent / artifact.relative_path


def _artifact_records(directory: Path) -> tuple[dict[str, object], ...]:
    """Return exact candidate product identities from one completed shard."""
    marker = directory / "complete.json"
    document = json.loads(marker.read_text(encoding="utf-8"))
    records = document.get("artifacts")
    if not isinstance(records, list):
        raise ValueError("candidate product marker has no artifacts")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("candidate product artifact is malformed")
        path = directory / cast(str, record["relative_path"])
        if (
            not path.is_file()
            or path.stat().st_size != record["byte_count"]
            or file_sha256(path) != record["sha256"]
        ):
            raise ValueError("candidate product artifact identity changed")
    return tuple(cast(dict[str, object], item) for item in records)


def _completed_candidate(
    directory: Path,
    *,
    input_id: str,
    configuration_sha256: str,
    source_sha256: str,
) -> bool:
    """Return whether one restartable shard has the exact current identity."""
    marker = directory / "complete.json"
    if not marker.is_file():
        return False
    document = json.loads(marker.read_text(encoding="utf-8"))
    if (
        document.get("input_id") != input_id
        or document.get("configuration_sha256") != configuration_sha256
        or document.get("source_tree_sha256") != source_sha256
    ):
        return False
    _artifact_records(directory)
    return True


def _write_continuum_products(
    dataset: DatasetRecord,
    *,
    image_path: Path,
    mean_path: Path,
    rms_path: Path,
    output: Path,
) -> dict[str, Path]:
    """Write the complete prospective Continuum product set."""
    image = load_fits_plane(image_path)
    mean = load_fits_plane(mean_path)
    rms = load_fits_plane(rms_path)
    valid = np.isfinite(image) & np.isfinite(mean) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError("external mean/RMS validity differs from image")
    beam = BeamShapePixels(
        dataset.beam.major_fwhm_pixels,
        dataset.beam.minor_fwhm_pixels,
        dataset.beam.position_angle_degrees,
    )
    products = evaluate_post_campaign_candidate_products(
        image,
        valid,
        mean,
        rms,
        beam=beam,
        review=load_phase_five_corrective_a_review(_BASE_REVIEW_PATH),
    )
    header = cast(fits.Header, fits.getheader(image_path))
    catalogue = build_hebog_segment_catalogue(
        image,
        mean,
        valid,
        products.detection.component_labels,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=products.position_signal_jy_per_beam,
    )
    catalogue_path = output / "segment_catalogue.json"
    labels_path = output / "segment_labels.fits"
    mask_path = output / "segment_mask.fits"
    write_comparison_catalogue(catalogue_path, catalogue)
    fits.PrimaryHDU(
        data=products.detection.component_labels[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(labels_path)
    fits.PrimaryHDU(
        data=products.detection.retained_mask.astype(np.uint8)[
            np.newaxis, np.newaxis, :, :
        ],
        header=header,
    ).writeto(mask_path)
    return {
        "segment-catalogue-json": catalogue_path,
        "segment-labels-fits": labels_path,
        "segment-mask-fits": mask_path,
    }


def _write_compact_products(
    dataset: DatasetRecord,
    *,
    seed: int,
    image_path: Path,
    output: Path,
) -> dict[str, Path]:
    """Write one prospective fitted-Gaussian-component catalogue."""
    image = load_fits_plane(image_path)
    with TemporaryDirectory(prefix="hebog-phase5-cumulative-compact-") as work:
        catalogue = process_hebog_image(
            image,
            dataset,
            Path(work),
            generation_id=f"{dataset.identifier}-{seed}",
        )
    catalogue_path = output / "compact_catalogue.json"
    write_comparison_catalogue(catalogue_path, catalogue)
    return {"compact-catalogue-json": catalogue_path}


def _generate_candidate_product(task: dict[str, object]) -> str:
    """Generate or verify one restartable prospective candidate shard."""
    directory = Path(cast(str, task["output_directory"]))
    input_id = cast(str, task["input_id"])
    configuration = cast(str, task["configuration_sha256"])
    source_sha256 = cast(str, task["source_tree_sha256"])
    if _completed_candidate(
        directory,
        input_id=input_id,
        configuration_sha256=configuration,
        source_sha256=source_sha256,
    ):
        return input_id
    if directory.exists():
        raise FileExistsError(
            f"candidate shard has a different identity: {directory}"
        )
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{input_id}.",
        dir=directory.parent,
    ) as temporary:
        staging = Path(temporary)
        dataset = DatasetRecord.model_validate(task["dataset"])
        image_path = Path(cast(str, task["image_path"]))
        if task["lane"] == "continuum":
            products = _write_continuum_products(
                dataset,
                image_path=image_path,
                mean_path=Path(cast(str, task["mean_path"])),
                rms_path=Path(cast(str, task["rms_path"])),
                output=staging,
            )
        else:
            products = _write_compact_products(
                dataset,
                seed=cast(int, task["seed"]),
                image_path=image_path,
                output=staging,
            )
        artifacts = [
            {
                "role": role,
                "relative_path": path.name,
                "byte_count": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for role, path in sorted(products.items())
        ]
        marker = {
            "schema_version": 1,
            "input_id": input_id,
            "configuration_sha256": configuration,
            "source_tree_sha256": source_sha256,
            "artifacts": artifacts,
        }
        (staging / "complete.json").write_bytes(_canonical_json_bytes(marker))
        Path(temporary).replace(directory)
    return input_id


def _candidate_tasks(
    verified: Any,
    datasets: dict[str, DatasetRecord],
    scratch: Path,
    *,
    configuration_sha256: str,
    source_sha256: str,
) -> tuple[dict[str, object], ...]:
    """Describe every complete viewed image exactly once."""
    tasks: list[dict[str, object]] = []
    for campaign_input in verified.request.inputs:
        bundle, input_path = verified.inputs[campaign_input.input_id]
        tasks.append(
            {
                "input_id": campaign_input.input_id,
                "lane": campaign_input.lane,
                "seed": campaign_input.seed,
                "dataset": datasets[
                    campaign_input.dataset_identifier
                ].model_dump(mode="json"),
                "image_path": str(
                    _input_artifact_path(bundle, input_path, "image")
                ),
                "mean_path": str(
                    _input_artifact_path(bundle, input_path, "mean")
                ),
                "rms_path": str(
                    _input_artifact_path(bundle, input_path, "rms")
                ),
                "output_directory": str(
                    scratch / "products" / campaign_input.input_id
                ),
                "configuration_sha256": configuration_sha256,
                "source_tree_sha256": source_sha256,
            }
        )
    return tuple(tasks)


def _run_candidate_tasks(
    tasks: tuple[dict[str, object], ...],
    *,
    workers: int,
    progress_path: Path,
) -> None:
    """Run bounded candidate shards and persist operational progress."""
    completed = 0
    with (
        progress_path.open("a", encoding="utf-8") as progress,
        ProcessPoolExecutor(max_workers=workers) as executor,
    ):
        futures = {
            executor.submit(_generate_candidate_product, task): task
            for task in tasks
        }
        for future in as_completed(futures):
            input_id = future.result()
            completed += 1
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{len(tasks)} input={input_id}\n"
            )
            progress.flush()


def _prospective_campaign(
    verified: Any,
    scratch: Path,
    *,
    configuration_sha256: str,
    revision: str,
    compiler_globals: dict[str, Any],
) -> Any:
    """Replace only Hebog product handles in the verified campaign view."""
    runs = dict(verified.runs)
    verified_run_type = compiler_globals["VerifiedRun"]
    for campaign_input in verified.request.inputs:
        key = (campaign_input.input_id, "hebog", "candidate")
        closed = verified.runs[key]
        directory = scratch / "products" / campaign_input.input_id
        artifacts = tuple(
            ExternalRunArtifact.model_validate(item)
            for item in _artifact_records(directory)
        )
        runtime = closed.result.runtime.model_copy(
            update={"source_revision": revision}
        )
        result = closed.result.model_copy(
            update={
                "runtime": runtime,
                "configuration_sha256": configuration_sha256,
                "wall_seconds": 0.0,
                "artifacts": artifacts,
            }
        )
        runs[key] = verified_run_type(
            request=closed.request,
            result=result,
            directory=directory,
        )
    return replace(verified, runs=runs)


def _fitted_component_realization(  # noqa: PLR0913
    original: Any,
    catalogue_loader: Any,
    run: Any,
    dataset: Any,
    recipe: Any,
    *,
    implementation_identifier: str,
    outlier_thresholds: Any,
    position_angle_minimum_axis_ratio: float,
) -> Any:
    """Compile every compact finder with like-product component semantics."""
    if run.result.status != "success":
        return original(
            run,
            dataset,
            recipe,
            implementation_identifier=implementation_identifier,
            outlier_thresholds=outlier_thresholds,
            position_angle_minimum_axis_ratio=(
                position_angle_minimum_axis_ratio
            ),
        )
    return diagnose_compact_component_realization(
        dataset,
        recipe,
        catalogue_loader(run),
        implementation_identifier=implementation_identifier,
        outlier_thresholds=outlier_thresholds,
        position_angle_minimum_axis_ratio=position_angle_minimum_axis_ratio,
    )


def _compile_compact_views(
    compiler_globals: dict[str, Any],
    verified: Any,
    prospective: Any,
    registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile closed and prospective products under one component boundary."""
    original = compiler_globals["_compact_realization"]
    catalogue_loader = compiler_globals["_compact_catalogue"]

    def component_view(*args: object, **kwargs: object) -> Any:
        return _fitted_component_realization(
            original,
            catalogue_loader,
            *args,
            **kwargs,
        )

    compiler_globals["_compact_realization"] = component_view
    try:
        closed = compiler_globals["compile_compact_campaign"](
            verified,
            registry,
            _ROOT,
        )
        current = compiler_globals["compile_compact_campaign"](
            prospective,
            registry,
            _ROOT,
        )
    finally:
        compiler_globals["_compact_realization"] = original
    return cast(dict[str, Any], closed), cast(dict[str, Any], current)


def _evaluate_continuum(
    endpoints: tuple[Any, ...],
    evaluator: dict[str, Any],
) -> tuple[Any, ...]:
    """Apply the unchanged endpoint-specific frozen decision rules."""
    contract = evaluator["load_post_failure_evaluation_contract"](
        _EVALUATION_PATH,
        _EVALUATOR_PATH,
    )
    decide = evaluator["EndpointSpecificEvaluator"](
        cast(list[dict[str, Any]], contract["endpoint_power_priors"])
    )
    terminal = evaluator["_TERMINAL"]
    return tuple(
        decide(
            endpoint,
            terminal["endpoint_policy"](
                contract,
                lane="continuum",
                metric_family=endpoint.metric_family,
                position_population=endpoint.position_population,
            ),
        )
        for endpoint in endpoints
    )


def _compact_statuses(compact: dict[str, Any]) -> dict[str, str]:
    """Flatten every exact compact endpoint into a stable key."""
    rows: dict[str, str] = {}
    pybdsf = cast(dict[str, Any], compact["phase_four_pybdsf_decision"])
    selected = (
        *pybdsf["metric_decisions"],
        *compact["aegean_binding_metric_decisions"],
    )
    for item in selected:
        key = (
            f"compact::{item['reference_identifier']}::"
            f"{item['metric_id']}::{item['stratum']}"
        )
        rows[key] = item["status"]
    return rows


def _continuum_statuses(decisions: list[dict[str, Any]]) -> dict[str, str]:
    """Flatten every exact Continuum endpoint into a stable key."""
    return {item["endpoint_id"]: item["status"] for item in decisions}


def _transition_rows(
    left: dict[str, str],
    right: dict[str, str],
    *,
    left_id: str,
    right_id: str,
    comparable: bool,
) -> tuple[dict[str, object], ...]:
    """Record every shared endpoint whose status changed."""
    return tuple(
        {
            "endpoint_id": key,
            "from_campaign": left_id,
            "from_status": left[key],
            "to_campaign": right_id,
            "to_status": right[key],
            "like_semantics_and_population": comparable,
        }
        for key in sorted(set(left) & set(right))
        if left[key] != right[key]
    )


def _historic_views() -> tuple[dict[str, object], ...]:
    """Load statuses only from every prior external campaign decision."""
    views: list[dict[str, object]] = []
    for prefix in _HISTORIC_PREFIXES:
        analysis_path = (
            _ROOT / f"benchmark-results/phase-5/{prefix}-analysis.json"
        )
        decision_path = (
            _ROOT / f"benchmark-results/phase-5/{prefix}-decision.json"
        )
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        views.append(
            {
                "campaign_id": prefix,
                "analysis_sha256": file_sha256(analysis_path),
                "decision_sha256": file_sha256(decision_path),
                "compact": _compact_statuses(analysis["compact"]),
                "continuum": _continuum_statuses(
                    decision["continuum_endpoints"]
                ),
                "comparison_basis": "historical-compiler-and-population",
            }
        )
    return tuple(views)


def _regressions(
    baseline: dict[str, str],
    current: dict[str, str],
) -> tuple[str, ...]:
    """Return shared endpoints that lost an exact passing result."""
    return tuple(
        key
        for key in sorted(set(baseline) & set(current))
        if baseline[key] == "pass" and current[key] != "pass"
    )


def _parse_args() -> argparse.Namespace:
    """Parse the sealed development source and write-once ledger paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    return parser.parse_args()


def main() -> None:  # noqa: PLR0915
    """Verify, replay, compile, and publish the cumulative ledger."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite cumulative ledger: {arguments.output}"
        )
    if arguments.workers < 1:
        raise ValueError("cumulative ledger workers must be positive")
    arguments.scratch.mkdir(parents=True, exist_ok=True)
    progress_path = arguments.scratch / "progress.log"
    compiler = runpy.run_path(str(_COMPILER_PATH))
    _install_historical_source_view(compiler)
    terminal = compiler["_configured_terminal"]()
    compiler_globals = terminal["compile_terminal_analysis"].__globals__
    registry = compiler_globals["load_endpoint_registry"](
        _REGISTRY_PATH,
        _COMPILER_PATH,
    )
    verified = compiler_globals["verify_terminal_campaign"](
        arguments.campaign,
        registry,
        _ROOT,
    )
    compact_datasets, _ = compiler_globals["_dataset_maps"](
        _ROOT / registry["compact_manifest_path"]
    )
    continuum_datasets, _ = compiler_globals["_dataset_maps"](
        _ROOT / registry["continuum_manifest_path"]
    )
    datasets = {**compact_datasets, **continuum_datasets}
    configuration = _candidate_configuration_sha256()
    source_sha256 = source_tree_sha256(_ROOT)
    revision = _git_revision()
    tasks = _candidate_tasks(
        verified,
        datasets,
        arguments.scratch,
        configuration_sha256=configuration,
        source_sha256=source_sha256,
    )
    _run_candidate_tasks(
        tasks,
        workers=arguments.workers,
        progress_path=progress_path,
    )
    product_identity = canonical_sha256(
        [
            json.loads(
                (
                    arguments.scratch
                    / "products"
                    / cast(str, task["input_id"])
                    / "complete.json"
                ).read_text(encoding="utf-8")
            )
            for task in tasks
        ]
    )
    prospective = _prospective_campaign(
        verified,
        arguments.scratch,
        configuration_sha256=configuration,
        revision=revision,
        compiler_globals=compiler_globals,
    )
    continuum, continuum_diagnostics = compiler_globals[
        "compile_continuum_campaign"
    ](prospective, registry, _ROOT)
    closed_compact, current_compact = _compile_compact_views(
        compiler_globals,
        verified,
        prospective,
        registry,
    )
    evaluator = runpy.run_path(str(_EVALUATOR_PATH))
    _install_historical_source_view(evaluator)
    continuum_decisions = _evaluate_continuum(continuum, evaluator)
    current_continuum_rows = [asdict(item) for item in continuum_decisions]
    current_continuum = _continuum_statuses(current_continuum_rows)
    closed_component = _compact_statuses(closed_compact)
    current_compact_statuses = _compact_statuses(current_compact)
    historic = _historic_views()
    post_failure = historic[-1]
    baseline_continuum = cast(dict[str, str], post_failure["continuum"])
    compact_regressions = _regressions(
        closed_component,
        current_compact_statuses,
    )
    continuum_regressions = _regressions(
        baseline_continuum,
        current_continuum,
    )
    transitions: list[dict[str, object]] = []
    for left, right in pairwise(historic):
        transitions.extend(
            _transition_rows(
                cast(dict[str, str], left["compact"]),
                cast(dict[str, str], right["compact"]),
                left_id=cast(str, left["campaign_id"]),
                right_id=cast(str, right["campaign_id"]),
                comparable=False,
            )
        )
        transitions.extend(
            _transition_rows(
                cast(dict[str, str], left["continuum"]),
                cast(dict[str, str], right["continuum"]),
                left_id=cast(str, left["campaign_id"]),
                right_id=cast(str, right["campaign_id"]),
                comparable=False,
            )
        )
    transitions.extend(
        _transition_rows(
            closed_component,
            current_compact_statuses,
            left_id="post-failure-fitted-component-baseline",
            right_id="prospective-candidate",
            comparable=True,
        )
    )
    transitions.extend(
        _transition_rows(
            baseline_continuum,
            current_continuum,
            left_id="external-post-failure",
            right_id="prospective-candidate",
            comparable=True,
        )
    )
    continuum_counts = {
        status: sum(item.status == status for item in continuum_decisions)
        for status in ("pass", "fail", "underpowered", "indeterminate")
    }
    ready = (
        current_compact["status"] == "pass"
        and continuum_counts
        == {
            "pass": len(continuum_decisions),
            "fail": 0,
            "underpowered": 0,
            "indeterminate": 0,
        }
        and not compact_regressions
        and not continuum_regressions
    )
    ledger = {
        "schema_version": 1,
        "ledger_id": "phase-5-cumulative-regression-ledger",
        "status": "pass" if ready else "fail",
        "captured_at": datetime.now(UTC).isoformat(),
        "evidence_role": "viewed-development-regression",
        "sealed_campaign_sha256": verified.campaign_sha256,
        "candidate_revision": revision,
        "candidate_source_tree_sha256": source_sha256,
        "candidate_configuration_sha256": configuration,
        "transient_candidate_product_set_sha256": product_identity,
        "image_counts": {"continuum": 1600, "compact-blend": 800},
        "catalogue_semantics": "fitted-gaussian-component",
        "historic_views": list(historic),
        "historic_status_transitions": transitions,
        "closed_post_failure_component_baseline": closed_compact,
        "prospective_compact": current_compact,
        "prospective_continuum_endpoints": current_continuum_rows,
        "prospective_continuum_diagnostics": [
            asdict(item) for item in continuum_diagnostics
        ],
        "prospective_continuum_status_counts": continuum_counts,
        "like_semantics_compact_regressions": list(compact_regressions),
        "like_semantics_continuum_regressions": list(continuum_regressions),
        "all_required_endpoints_pass": ready,
        "fresh_campaign_execution_authorized": False,
        "step_three_authorized": False,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(ledger))
    shutil.rmtree(arguments.scratch / "products")
    print(arguments.output)
    print(f"status={ledger['status']}")
    print(f"compact={current_compact['status']}")
    print(f"continuum={continuum_counts}")
    print(
        f"regressions={len(compact_regressions) + len(continuum_regressions)}"
    )


if __name__ == "__main__":
    main()
