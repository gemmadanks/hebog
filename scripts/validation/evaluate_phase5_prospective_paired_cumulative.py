#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile one prospective current/incumbent Phase 5 paired replay."""

from __future__ import annotations

import argparse
import json
import os
import runpy
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.prospective_science_contract import (
    ProspectiveEndpoint,
    ProspectiveEndpointRegistry,
    load_prospective_endpoint_registry,
)

_ROOT = Path(__file__).parents[2]
_PREPARER = (
    _ROOT / "scripts/validation/prepare_phase5_prospective_paired_evidence.py"
)
_SMOKE_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
)
_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_paired_products.py"
)
_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_SENTINELS = (
    _ROOT / "config/contracts/phase-5-prospective-paired-tail-sentinels.json"
)
_CONTINUUM_MANIFEST = (
    _ROOT / "config/datasets/phase-5-external-post-failure-continuum.json"
)
_CURRENT_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CURRENT_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_RUN_ARGUMENT_POSITION = 2


def _comparison_by_reference(endpoint: Any) -> dict[str, Any]:
    """Index one compiled Continuum endpoint's paired evidence."""
    comparisons = getattr(endpoint, "comparisons", None)
    if not isinstance(comparisons, tuple):
        raise ValueError("compiled Continuum comparisons are malformed")
    output = {item.reference_id: item for item in comparisons}
    if len(output) != len(comparisons):
        raise ValueError("compiled Continuum comparison is duplicated")
    return output


def _load_materializer() -> dict[str, Any]:
    """Load the publication candidate over the generalized producer CLI."""
    prospective = runpy.run_path(str(_MATERIALIZER))
    return cast(dict[str, Any], prospective["_load_materializer"](_ROOT))


def _observation_callback(
    *,
    records: dict[tuple[str, str], dict[str, object]],
    preparer: Mapping[str, Any],
    hebog_finder_by_configuration: Mapping[str, str],
    allowed_finders: frozenset[str],
) -> Callable[[Any, Mapping[str, object]], None]:
    """Build one duplicate-detecting array-free observation callback."""
    build = preparer.get("build_array_free_endpoint_summary")
    if not callable(build):
        raise ValueError("array-free endpoint summary seam changed")

    def record(run: Any, observations: Mapping[str, object]) -> None:
        result = getattr(run, "result", None)
        native_finder = getattr(result, "finder_id", None)
        configuration = getattr(result, "configuration_sha256", None)
        finder_id = (
            hebog_finder_by_configuration.get(configuration)
            if native_finder == "hebog" and isinstance(configuration, str)
            else native_finder
        )
        if finder_id not in allowed_finders:
            return
        if not isinstance(observations, dict) or not observations:
            raise ValueError("continuum observations are malformed")
        image_ids = {
            getattr(observation, "image_key", None)
            for observation in observations.values()
        }
        if len(image_ids) != 1 or not isinstance(next(iter(image_ids)), str):
            raise ValueError("continuum observation image identity changed")
        input_id = cast(str, next(iter(image_ids)))
        key = (finder_id, input_id)
        if key in records:
            raise ValueError("continuum realization summary is duplicated")
        records[key] = cast(
            dict[str, object],
            build(
                input_id=input_id,
                finder_id=finder_id,
                observations=observations,
            ),
        )

    return record


def _install_observation_recorder(
    compiler_globals: dict[str, Any],
    callback: Callable[[Any, Mapping[str, object]], None],
) -> None:
    """Retain endpoint statistics around the exact continuum compiler seam."""
    delegate = compiler_globals.get("_continuum_image_observations")
    if not callable(delegate):
        raise ValueError("continuum observation compiler seam changed")

    def recording_compiler(*args: Any, **kwargs: Any) -> Any:
        observations = delegate(*args, **kwargs)
        run = (
            args[_RUN_ARGUMENT_POSITION]
            if len(args) > _RUN_ARGUMENT_POSITION
            else kwargs.get("run")
        )
        callback(run, cast(Mapping[str, object], observations))
        return observations

    compiler_globals["_continuum_image_observations"] = recording_compiler


def _compile_incumbent_pair(  # noqa: PLR0913
    *,
    parent: Mapping[str, Any],
    current: Any,
    incumbent: Any,
    repository_root: Path,
    current_configuration: str,
    smoke: Mapping[str, Any],
    observation_callback: Callable[[Any, Mapping[str, object]], None],
) -> tuple[Any, ...]:
    """Compile every incumbent comparison without modifying frozen smoke."""
    _, _, historical = parent["_load_source_association_composition"]()
    parent["_install_terminal_parent_static_seams"](historical)
    compiler_globals, registry = smoke["_compiler"](historical)
    paired = smoke["_paired_incumbent_view"](
        current, incumbent, compiler_globals
    )
    expand = compiler_globals["expand_continuum_endpoint_specs"]

    def incumbent_paired_specs(value: object) -> tuple[Any, ...]:
        return tuple(replace(item, paired=True) for item in expand(value))

    compiler_globals["expand_continuum_endpoint_specs"] = (
        incumbent_paired_specs
    )
    historical["_install_prospective_compiler"](
        compiler_globals, paired, current_configuration
    )
    smoke["_install_mask_separated_compiler"](
        compiler_globals,
        measurement_configuration=current_configuration,
    )
    _install_observation_recorder(compiler_globals, observation_callback)
    compiled, _ = compiler_globals["compile_continuum_campaign"](
        paired, registry, repository_root
    )
    return cast(tuple[Any, ...], compiled)


def _endpoint_summary_record(
    records: Mapping[tuple[str, str], Mapping[str, object]],
    *,
    expected_inputs: int,
) -> dict[str, object]:
    """Validate complete current/comparator retention and bind its digest."""
    expected_finders = (
        "current-hebog",
        "incumbent-hebog",
        "pinned-pybdsf-master",
        "released-pybdsf",
    )
    counts = Counter(finder for finder, _ in records)
    if counts != Counter(dict.fromkeys(expected_finders, expected_inputs)):
        raise ValueError("per-realization endpoint retention is incomplete")
    summaries = [
        dict(value)
        for _, value in sorted(
            records.items(), key=lambda item: (item[0][0], item[0][1])
        )
    ]
    return {
        "schema_version": 1,
        "record_id": "phase-5-paired-array-free-endpoint-summaries",
        "summary_count": len(summaries),
        "finder_counts": dict(sorted(counts.items())),
        "summaries": summaries,
        "summaries_sha256": canonical_sha256(summaries),
        "array_planes_retained": False,
    }


def _source_member_counts(
    normalized_catalogue: Sequence[Any],
    candidates: Sequence[Any],
) -> dict[str, int]:
    """Bind normalized catalogue composition to compiler candidate IDs."""
    if len(normalized_catalogue) != len(candidates):
        raise ValueError("catalogue and candidate cardinalities differ")
    output: dict[str, int] = {}
    for source, candidate in zip(
        normalized_catalogue, candidates, strict=True
    ):
        count = getattr(source, "component_count", None)
        count = count if type(count) is int and count > 0 else 1
        identifier = getattr(candidate, "identifier", None)
        if not isinstance(identifier, str) or identifier in output:
            raise ValueError("candidate source identity is malformed")
        output[identifier] = count
    return output


def _hierarchy_diagnostics(
    run: Any, compiler_globals: Mapping[str, Any]
) -> dict[str, object]:
    """Load only bounded JSON-native hierarchy counts from a Hebog sidecar."""
    if getattr(run.result, "finder_id", None) != "hebog":
        return {}
    path = compiler_globals["_artifact_path"](run, "source-association-json")
    value = json.loads(path.read_text(encoding="utf-8"))
    diagnostics = value.get("hierarchy_diagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("source hierarchy diagnostics are absent")
    return cast(dict[str, object], diagnostics)


def _sentinel_memberships(
    *,
    source_request: Path,
    preparer: Mapping[str, Any],
) -> dict[str, list[dict[str, object]]]:
    """Reproduce the result-neutral sentinel selection and index by input."""
    frozen = json.loads(_SENTINELS.read_text(encoding="utf-8"))
    selected = preparer["select_result_neutral_tail_sentinels"](
        request=json.loads(source_request.read_text(encoding="utf-8")),
        continuum_manifest=json.loads(
            _CONTINUUM_MANIFEST.read_text(encoding="utf-8")
        ),
        count_per_dataset_and_sentinel=frozen[
            "count_per_dataset_and_sentinel"
        ],
    )
    if (
        selected["membership_sha256"] != frozen.get("membership_sha256")
        or selected["membership_count"] != frozen.get("membership_count")
        or selected["unique_input_count"] != frozen.get("unique_input_count")
    ):
        raise ValueError("result-neutral tail sentinel identity changed")
    output: dict[str, list[dict[str, object]]] = {}
    for row in selected["memberships"]:
        output.setdefault(row["input_id"], []).append(row)
    return output


def _truth_linked_tail_record(  # noqa: PLR0913
    *,
    current: Any,
    incumbent: Any,
    compiler_globals: Mapping[str, Any],
    historical_registry: Mapping[str, object],
    repository_root: Path,
    source_request: Path,
    smoke: Mapping[str, Any],
    preparer: Mapping[str, Any],
) -> dict[str, object]:
    """Compile bounded truth-linked diagnostics only for frozen sentinels."""
    memberships = _sentinel_memberships(
        source_request=source_request, preparer=preparer
    )
    datasets, recipes = compiler_globals["_dataset_maps"](
        repository_root
        / cast(str, historical_registry["continuum_manifest_path"])
    )
    review = compiler_globals["load_phase_five_corrective_a_review"](
        repository_root
        / cast(str, historical_registry["phase_five_review_path"])
    )
    inputs = {item.input_id: item for item in current.request.inputs}
    finder_views = (
        ("current-hebog", current, "hebog", "candidate"),
        ("incumbent-hebog", incumbent, "hebog", "candidate"),
        (
            "pinned-pybdsf-master",
            current,
            "pinned-pybdsf-master",
            "operational",
        ),
        ("released-pybdsf", current, "released-pybdsf", "operational"),
    )
    summaries: list[dict[str, object]] = []
    for input_id, sentinel_rows in sorted(memberships.items()):
        campaign_input = inputs[input_id]
        dataset = datasets[campaign_input.dataset_identifier]
        recipe = recipes[(dataset.identifier, campaign_input.seed)]
        bundle, input_path = current.inputs[input_id]
        image_path = compiler_globals["_input_artifact_path"](
            bundle, input_path, "image"
        )
        image = compiler_globals["load_fits_plane"](image_path)
        mean = compiler_globals["load_fits_plane"](
            compiler_globals["_input_artifact_path"](
                bundle, input_path, "mean"
            )
        )
        rms = compiler_globals["load_fits_plane"](
            compiler_globals["_input_artifact_path"](bundle, input_path, "rms")
        )
        valid = (
            compiler_globals["np"].isfinite(image)
            & compiler_globals["np"].isfinite(mean)
            & compiler_globals["np"].isfinite(rms)
        )
        truth, truth_labels = compiler_globals["_truth_objects"](
            dataset, recipe, valid, review
        )
        header = compiler_globals["fits"].getheader(image_path)
        sentinel_ids = sorted(
            {cast(str, row["sentinel_id"]) for row in sentinel_rows}
        )
        truth_group_ids = sorted(
            {
                cast(str, group)
                for row in sentinel_rows
                for group in cast(list[object], row["truth_group_ids"])
            }
        )
        for logical_finder, view, native_finder, mode in finder_views:
            run = view.runs[(input_id, native_finder, mode)]
            catalogue, publication_labels = compiler_globals[
                "_catalogue_and_labels"
            ](run)
            candidates = compiler_globals["_candidate_objects"](
                catalogue,
                publication_labels,
                finder_id=run.result.finder_id,
                header=header,
            )
            artifact_roles = {
                artifact.role for artifact in run.result.artifacts
            }
            association_labels = (
                smoke["_measurement_label_plane"](run)
                if run.result.finder_id == "hebog"
                and "measurement-labels-fits" in artifact_roles
                else publication_labels
            )
            summary = preparer["build_truth_linked_continuum_summary"](
                input_id=input_id,
                dataset_identifier=dataset.identifier,
                seed=campaign_input.seed,
                finder_id=logical_finder,
                truth=truth,
                catalogue=candidates,
                truth_label_plane=truth_labels,
                candidate_label_plane=publication_labels,
                association_label_plane=association_labels,
                beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
                source_member_counts=_source_member_counts(
                    catalogue, candidates
                ),
                hierarchy_diagnostics=_hierarchy_diagnostics(
                    run, compiler_globals
                ),
            )
            summary.pop("record_sha256")
            summary.update(
                {
                    "sentinel_ids": sentinel_ids,
                    "sentinel_truth_group_ids": truth_group_ids,
                }
            )
            summary["record_sha256"] = canonical_sha256(summary)
            summaries.append(summary)
    summaries.sort(
        key=lambda row: (
            cast(str, row["finder_id"]),
            cast(str, row["input_id"]),
        )
    )
    expected = len(memberships) * len(finder_views)
    if len(summaries) != expected:
        raise ValueError("truth-linked tail retention is incomplete")
    return {
        "schema_version": 1,
        "record_id": "phase-5-paired-truth-linked-tail-diagnostics",
        "evidence_role": "result-neutral-development-diagnostic",
        "summary_count": len(summaries),
        "unique_input_count": len(memberships),
        "finder_counts": dict(
            sorted(Counter(row["finder_id"] for row in summaries).items())
        ),
        "summaries": summaries,
        "summaries_sha256": canonical_sha256(summaries),
        "array_planes_retained": False,
        "promotion_effect": "none-diagnostic-only",
    }


def _comparison_evidence(
    endpoint: ProspectiveEndpoint,
    comparator_id: str,
    candidate_status: object,
    comparison: Any | None,
    planning_deviation_by_family: Mapping[str, float],
) -> dict[str, object]:
    """Translate one compiled comparison without deciding it twice."""
    available = (
        comparison is not None
        and getattr(comparison, "status", None) == "success"
    )
    successful = cast(Any, comparison) if available else None
    return {
        "candidate_available": candidate_status == "success",
        "comparator_available": available,
        "comparator_id": comparator_id,
        "endpoint_id": endpoint.endpoint_id,
        "observed_paired_standard_deviation": (
            successful.observed_paired_standard_deviation
            if successful is not None
            else None
        ),
        "planning_paired_standard_deviation": (
            planning_deviation_by_family.get(endpoint.metric_family)
        ),
        "positive_regression": (
            successful.positive_regression if successful is not None else None
        ),
        "upper_confidence_limit": (
            successful.upper_confidence_limit
            if successful is not None
            else None
        ),
    }


def _continuum_evidence_rows(
    *,
    registry: ProspectiveEndpointRegistry,
    current: Sequence[Any],
    incumbent_pair: Sequence[Any],
    planning_deviation_by_family: Mapping[str, float],
) -> list[dict[str, object]]:
    """Return every frozen Continuum co-primary comparison exactly once."""
    current_by_id = {item.endpoint_id: item for item in current}
    incumbent_by_id = {item.endpoint_id: item for item in incumbent_pair}
    if len(current_by_id) != len(current) or len(incumbent_by_id) != len(
        incumbent_pair
    ):
        raise ValueError("compiled Continuum endpoint is duplicated")
    rows: list[dict[str, object]] = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "continuum" or endpoint.role != "binding":
            continue
        try:
            current_endpoint = current_by_id[endpoint.endpoint_id]
            incumbent_endpoint = incumbent_by_id[endpoint.endpoint_id]
        except KeyError as error:
            raise ValueError(
                "compiled Continuum endpoint is absent: "
                f"{endpoint.endpoint_id}"
            ) from error
        references = _comparison_by_reference(current_endpoint)
        incumbent_references = _comparison_by_reference(incumbent_endpoint)
        for comparator_id in endpoint.comparators:
            comparison = (
                incumbent_references.get("pinned-pybdsf-master")
                if comparator_id == "incumbent-hebog"
                else references.get(comparator_id)
            )
            rows.append(
                _comparison_evidence(
                    endpoint,
                    comparator_id,
                    current_endpoint.candidate_status,
                    comparison,
                    planning_deviation_by_family,
                )
            )
    return rows


def _compact_decision_index(
    compact: Mapping[str, object],
) -> dict[tuple[str, str, str], Mapping[str, object]]:
    """Index the complete compact decisions by comparator, metric, stratum."""
    pybdsf = cast(Mapping[str, object], compact["phase_four_pybdsf_decision"])
    values = pybdsf.get("metric_decisions")
    aegean = compact.get("aegean_binding_metric_decisions")
    if not isinstance(values, list) or not isinstance(aegean, list):
        raise ValueError("compiled compact decisions are malformed")
    output: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for value in (*values, *aegean):
        if not isinstance(value, dict):
            raise ValueError("compiled compact decision is malformed")
        row = cast(Mapping[str, object], value)
        key_values = (
            row.get("reference_identifier"),
            row.get("metric_id"),
            row.get("stratum"),
        )
        if not all(isinstance(item, str) for item in key_values):
            raise ValueError("compiled compact decision identity is malformed")
        key = cast(tuple[str, str, str], key_values)
        if key in output:
            raise ValueError("compiled compact decision is duplicated")
        output[key] = row
    return output


def _compact_evidence_rows(
    *,
    registry: ProspectiveEndpointRegistry,
    compact: Mapping[str, object],
    compact_product_identity_equal: bool,
) -> list[dict[str, object]]:
    """Return compact cross-finder rows plus structural incumbent pairing."""
    indexed = _compact_decision_index(compact)
    rows: list[dict[str, object]] = []
    for endpoint in registry.endpoints:
        if endpoint.lane != "compact" or endpoint.role != "binding":
            continue
        for comparator_id in endpoint.comparators:
            if comparator_id == "incumbent-hebog":
                rows.append(
                    {
                        "candidate_available": True,
                        "comparator_available": compact_product_identity_equal,
                        "comparator_id": comparator_id,
                        "endpoint_id": endpoint.endpoint_id,
                        "observed_paired_standard_deviation": 0.0,
                        "planning_paired_standard_deviation": None,
                        "positive_regression": (
                            0.0 if compact_product_identity_equal else None
                        ),
                        "upper_confidence_limit": (
                            0.0 if compact_product_identity_equal else None
                        ),
                    }
                )
                continue
            row = indexed.get(
                (comparator_id, endpoint.metric_family, endpoint.stratum)
            )
            rows.append(
                {
                    "candidate_available": (
                        row is not None
                        and row.get("candidate_value") is not None
                    ),
                    "comparator_available": (
                        row is not None
                        and row.get("reference_value") is not None
                    ),
                    "comparator_id": comparator_id,
                    "endpoint_id": endpoint.endpoint_id,
                    "observed_paired_standard_deviation": None,
                    "planning_paired_standard_deviation": None,
                    "positive_regression": (
                        row.get("positive_regression") if row else None
                    ),
                    "upper_confidence_limit": (
                        row.get("upper_confidence_limit") if row else None
                    ),
                }
            )
    return rows


def _objective_rows(
    registry: ProspectiveEndpointRegistry,
    compiled: Sequence[Any],
) -> list[dict[str, object]]:
    """Expose longer-term targets without turning them into promotion gates."""
    compiled_by_id = {item.endpoint_id: item for item in compiled}
    rows: list[dict[str, object]] = []
    for endpoint in registry.endpoints:
        if endpoint.role != "longer-term-objective":
            continue
        value = compiled_by_id.get(endpoint.endpoint_id)
        rows.append(
            {
                "candidate_status": getattr(
                    value, "candidate_status", "unavailable"
                ),
                "candidate_value": getattr(value, "candidate_value", None),
                "endpoint_id": endpoint.endpoint_id,
                "objective_passed": None,
                "objective_value": None,
            }
        )
    return rows


def compile_prospective_decision(  # noqa: PLR0913
    *,
    registry: ProspectiveEndpointRegistry,
    current_continuum: Sequence[Any],
    incumbent_paired_continuum: Sequence[Any],
    continuum_objectives: Sequence[Any],
    compact: Mapping[str, object],
    compact_product_identity_equal: bool,
    planning_deviation_by_family: Mapping[str, float],
    safety_results: Mapping[str, bool],
) -> dict[str, object]:
    """Compile the endpoint-complete prospective cumulative decision."""
    preparer = runpy.run_path(str(_PREPARER))
    comparisons = [
        *_compact_evidence_rows(
            registry=registry,
            compact=compact,
            compact_product_identity_equal=compact_product_identity_equal,
        ),
        *_continuum_evidence_rows(
            registry=registry,
            current=current_continuum,
            incumbent_pair=incumbent_paired_continuum,
            planning_deviation_by_family=planning_deviation_by_family,
        ),
    ]
    if len(comparisons) != registry.counts.total_coprimary_comparisons:
        raise ValueError("prospective comparison population changed")
    return cast(
        dict[str, object],
        preparer["evaluate_prospective_cumulative_evidence"](
            registry=registry,
            comparisons=comparisons,
            safety_results=safety_results,
            absolute_objectives=_objective_rows(
                registry, continuum_objectives
            ),
        ),
    )


def _publish(path: Path, record: dict[str, object]) -> None:
    """Atomically publish one finite write-once paired decision."""
    payload = (
        json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n"
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


def _planning_deviations(root: Path) -> dict[str, float]:
    """Reuse the exact pre-results Continuum planning assumptions."""
    smoke = runpy.run_path(str(_SMOKE_EVALUATOR))
    return cast(dict[str, float], smoke["_planning_deviations"](root))


def _parse_args() -> argparse.Namespace:
    """Parse two sealed product sets and one write-once output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--source-request", required=True, type=Path)
    parser.add_argument("--population", required=True, type=Path)
    parser.add_argument("--current-scratch", required=True, type=Path)
    parser.add_argument("--incumbent-scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:  # noqa: PLR0915
    """Verify, compile, decide, and atomically publish paired evidence."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite paired decision: {arguments.output}"
        )
    root = arguments.repository_root.resolve()
    materializer = _load_materializer()
    smoke = runpy.run_path(str(_SMOKE_EVALUATOR))
    preparer = runpy.run_path(str(_PREPARER))
    identifiers = materializer["_selected_inputs"](
        arguments.source_request, arguments.population
    )
    verified, _ = materializer["_verified_reference"](
        root, arguments.reference_reconstruction
    )
    verified = smoke["_subset_verified"](verified, identifiers)
    current_revision = _CURRENT_REVISION
    current_configuration = materializer["_current_configuration"](root)
    current_source_tree = materializer["source_tree_sha256"](root)
    if (
        current_configuration != _CURRENT_CONFIGURATION_SHA256
        or current_source_tree != _CURRENT_SOURCE_TREE_SHA256
    ):
        raise ValueError("prospective current scientific identity changed")
    current_product_set = smoke["_verify_product_set"](
        identifiers,
        arguments.current_scratch,
        configuration=current_configuration,
        source_tree=current_source_tree,
    )
    parent = runpy.run_path(
        str(root / materializer["_TERMINAL_PARENT_WRAPPER"])
    )
    incumbent_revision = parent["_CANDIDATE_REVISION"]
    incumbent_configuration = parent["_CANDIDATE_CONFIGURATION_SHA256"]
    incumbent_source_tree = parent["_CANDIDATE_SOURCE_TREE_SHA256"]
    incumbent_product_set = smoke["_verify_product_set"](
        identifiers,
        arguments.incumbent_scratch,
        configuration=incumbent_configuration,
        source_tree=incumbent_source_tree,
    )
    frozen = materializer["_current_composition"](
        root,
        revision=current_revision,
        configuration=current_configuration,
    )
    compiler_globals, historical_registry = smoke["_compiler"](frozen)
    current = smoke["_candidate_view"](
        frozen,
        verified,
        arguments.current_scratch,
        configuration=current_configuration,
        revision=current_revision,
        compiler_globals=compiler_globals,
    )
    previous_identity = frozen["_candidate_runtime_identity"]
    frozen["_candidate_runtime_identity"] = parent[
        "_candidate_runtime_identity"
    ]
    try:
        incumbent = smoke["_candidate_view"](
            frozen,
            verified,
            arguments.incumbent_scratch,
            configuration=incumbent_configuration,
            revision=incumbent_revision,
            compiler_globals=compiler_globals,
        )
    finally:
        frozen["_candidate_runtime_identity"] = previous_identity
    compact_equal = smoke["_compact_equal"](
        identifiers,
        arguments.current_scratch,
        arguments.incumbent_scratch,
    )
    endpoint_summaries: dict[tuple[str, str], dict[str, object]] = {}
    current_observation_callback = _observation_callback(
        records=endpoint_summaries,
        preparer=preparer,
        hebog_finder_by_configuration={current_configuration: "current-hebog"},
        allowed_finders=frozenset(
            {
                "current-hebog",
                "pinned-pybdsf-master",
                "released-pybdsf",
            }
        ),
    )
    with smoke["_mask_measurement_separation_evaluation"]():
        frozen["_install_prospective_compiler"](
            compiler_globals, current, current_configuration
        )
        smoke["_install_mask_separated_compiler"](
            compiler_globals,
            measurement_configuration=current_configuration,
        )
        _install_observation_recorder(
            compiler_globals, current_observation_callback
        )
        current_continuum, objectives = compiler_globals[
            "compile_continuum_campaign"
        ](current, historical_registry, root)
        incumbent_observation_callback = _observation_callback(
            records=endpoint_summaries,
            preparer=preparer,
            hebog_finder_by_configuration={
                incumbent_configuration: "incumbent-hebog"
            },
            allowed_finders=frozenset({"incumbent-hebog"}),
        )
        incumbent_continuum = _compile_incumbent_pair(
            parent=parent,
            current=current,
            incumbent=incumbent,
            repository_root=root,
            current_configuration=current_configuration,
            smoke=smoke,
            observation_callback=incumbent_observation_callback,
        )
        compact = compiler_globals["compile_compact_campaign"](
            current, historical_registry, root
        )
    record = compile_prospective_decision(
        registry=load_prospective_endpoint_registry(_REGISTRY),
        current_continuum=current_continuum,
        incumbent_paired_continuum=incumbent_continuum,
        continuum_objectives=objectives,
        compact=compact,
        compact_product_identity_equal=compact_equal,
        planning_deviation_by_family=_planning_deviations(root),
        safety_results=dict.fromkeys(
            (
                "finite-measurements",
                "product-validity",
                "schema-and-provenance-integrity",
                "serial-and-existing-dask-determinism",
                "write-once-publication",
            ),
            True,
        ),
    )
    continuum_input_count = sum(
        item.lane == "continuum" for item in current.request.inputs
    )
    endpoint_summary_record = _endpoint_summary_record(
        endpoint_summaries, expected_inputs=continuum_input_count
    )
    tail_record = _truth_linked_tail_record(
        current=current,
        incumbent=incumbent,
        compiler_globals=compiler_globals,
        historical_registry=historical_registry,
        repository_root=root,
        source_request=arguments.source_request,
        smoke=smoke,
        preparer=preparer,
    )
    record.update(
        {
            "candidate_revision": current_revision,
            "candidate_source_tree_sha256": current_source_tree,
            "candidate_configuration_sha256": current_configuration,
            "candidate_product_set_sha256": current_product_set,
            "incumbent_revision": incumbent_revision,
            "incumbent_source_tree_sha256": incumbent_source_tree,
            "incumbent_configuration_sha256": incumbent_configuration,
            "incumbent_product_set_sha256": incumbent_product_set,
            "selected_input_count": len(identifiers),
            "population_sha256": file_sha256(arguments.population),
            "tail_sentinels_sha256": file_sha256(_SENTINELS),
            "array_free_endpoint_summaries": endpoint_summary_record,
            "truth_linked_tail_diagnostics": tail_record,
            "evaluator_sha256": file_sha256(Path(__file__).resolve()),
        }
    )
    record["record_canonical_sha256"] = canonical_sha256(record)
    _publish(arguments.output, record)
    print(arguments.output)
    print(f"status={record['status']}")


if __name__ == "__main__":
    main()
