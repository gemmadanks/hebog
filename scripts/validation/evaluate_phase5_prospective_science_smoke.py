#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportPrivateUsage=false
"""Compile and evaluate the frozen non-promotional Phase 5 smoke lane."""

from __future__ import annotations

import argparse
import json
import os
import runpy
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import is_dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import numpy as np

from hebog.data_models.source_association import SourceAssociationResult
from hebog.validation import (
    parent_construction_association_evaluation,
    source_association_evaluation_repair,
)
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_runners import (
    canonical_sha256,
    file_sha256,
    source_tree_sha256,
)
from hebog.validation.products import load_fits_plane
from hebog.validation.prospective_science_contract import (
    load_prospective_endpoint_registry,
)
from hebog.validation.prospective_science_smoke import (
    evaluate_prospective_science_smoke,
    select_prospective_smoke_inputs,
)
from hebog.validation.terminal_cycle_eligibility_evaluation import (
    aggregate_terminal_cycle_eligibility,
)

_MATERIALIZER = (
    "scripts/validation/materialize_phase5_prospective_hebog_products.py"
)
_TERMINAL_PARENT_WRAPPER = (
    "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
)
_REGISTRY = (
    "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_CONTINUUM_POWER = "config/contracts/phase-5-external-comparison.json"
_IMAGE_DIMENSIONS = 2
_RUN_ARGUMENT_POSITION = 2


def _measurement_artifact_path(run: Any) -> Path:
    """Resolve exactly one safe persisted measurement-label plane."""
    matches = tuple(
        artifact
        for artifact in run.result.artifacts
        if getattr(artifact, "role", None) == "measurement-labels-fits"
    )
    if len(matches) != 1:
        raise ValueError(
            "candidate run must contain exactly one measurement label plane"
        )
    relative = Path(cast(str, matches[0].relative_path))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("candidate measurement label path must be relative")
    return cast(Path, run.directory) / relative


def _measurement_label_plane(run: Any) -> np.ndarray:
    """Load one exact non-negative integer measurement-label plane."""
    raw = load_fits_plane(_measurement_artifact_path(run))
    if (
        not np.all(np.isfinite(raw))
        or np.any(raw < 0)
        or not np.all(raw == np.floor(raw))
    ):
        raise ValueError(
            "candidate measurement label plane must contain non-negative "
            "integers"
        )
    return np.asarray(raw, dtype=np.int64)


class _MaskSeparatedContinuumCompiler:
    """Use measurement support for sources and published support for masks."""

    def __init__(
        self,
        delegate: Any,
        *,
        measurement_configuration: str,
    ) -> None:
        if not callable(delegate):
            raise ValueError("mask-separated compiler delegate is invalid")
        if not measurement_configuration:
            raise ValueError("measurement configuration must be non-empty")
        self._delegate = delegate
        self._measurement_configuration = measurement_configuration

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Patch only source-union synthesis for one verified Hebog run."""
        run = (
            args[_RUN_ARGUMENT_POSITION]
            if len(args) > _RUN_ARGUMENT_POSITION
            else kwargs.get("run")
        )
        result = getattr(run, "result", None)
        if not (
            getattr(result, "status", None) == "success"
            and getattr(result, "finder_id", None) == "hebog"
            and getattr(result, "configuration_sha256", None)
            == self._measurement_configuration
        ):
            return self._delegate(*args, **kwargs)
        measurement = _measurement_label_plane(run)
        previous = (
            source_association_evaluation_repair._synthetic_source_labels
        )

        def measurement_support(catalogue: Any, published_labels: Any) -> Any:
            published = np.asarray(published_labels)
            if published.shape != measurement.shape:
                raise ValueError(
                    "published and measurement label planes must share shape"
                )
            return previous(catalogue, measurement)

        source_association_evaluation_repair._synthetic_source_labels = (
            measurement_support
        )
        try:
            return self._delegate(*args, **kwargs)
        finally:
            source_association_evaluation_repair._synthetic_source_labels = (
                previous
            )


def _install_mask_separated_compiler(
    compiler_globals: dict[str, Any],
    *,
    measurement_configuration: str,
) -> None:
    """Wrap the current compiler without mutating historical code."""
    current = compiler_globals.get("_continuum_image_observations")
    if not callable(current) or isinstance(
        current, _MaskSeparatedContinuumCompiler
    ):
        raise ValueError("mask-separated compiler seam changed")
    compiler_globals["_continuum_image_observations"] = (
        _MaskSeparatedContinuumCompiler(
            current,
            measurement_configuration=measurement_configuration,
        )
    )


def _mask_separated_support_labels(
    catalogue: tuple[CatalogueSource, ...],
    label_plane: Any,
    association: SourceAssociationResult,
) -> dict[str, tuple[int, ...]]:
    """Bind verified measurement identities to a refined publication mask.

    The association sidecar partitions the stable measurement components.
    The separate publication mask may remove every pixel for one of those
    components, but it may never publish a positive label that the verified
    measurement partition does not claim.
    """
    labels = np.asarray(label_plane)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype, np.integer
    ):
        raise ValueError(
            "candidate label plane must be a two-dimensional integer array"
        )
    if np.any(labels < 0):
        raise ValueError(
            "candidate label plane must contain non-negative labels"
        )
    present_labels = {
        int(value) for value in np.unique(labels) if int(value) > 0
    }
    component_by_id, membership_by_id = (
        parent_construction_association_evaluation._verified_association_maps(
            association
        )
    )
    identifiers = tuple(source.identifier for source in catalogue)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("associated source identifiers must be unique")
    output: dict[str, tuple[int, ...]] = {}
    claimed_labels: set[int] = set()
    for source in catalogue:
        if (
            source.identifier != source.island_identifier
            or not source.identifier.startswith("source-associated-")
        ):
            raise ValueError("associated source identity is malformed")
        membership = membership_by_id.get(source.identifier)
        if membership is None or source.component_count != len(
            membership.component_ids
        ):
            raise ValueError("associated source membership cannot be verified")
        try:
            support_labels = tuple(
                sorted(
                    component_by_id[component_id].label_value
                    for component_id in membership.component_ids
                )
            )
        except KeyError as error:
            raise ValueError(
                "associated source membership cannot be verified"
            ) from error
        if not support_labels or claimed_labels.intersection(support_labels):
            raise ValueError("associated source membership cannot be verified")
        claimed_labels.update(support_labels)
        output[source.identifier] = support_labels
    if set(membership_by_id) != set(
        identifiers
    ) or not present_labels.issubset(claimed_labels):
        raise ValueError(
            "associated source memberships must partition native supports"
        )
    return output


@contextmanager
def _mask_measurement_separation_evaluation() -> Generator[None]:
    """Temporarily install the current mask-separated evaluation seam."""
    previous = (
        parent_construction_association_evaluation._recorded_support_labels
    )
    parent_construction_association_evaluation._recorded_support_labels = (
        _mask_separated_support_labels
    )
    try:
        yield
    finally:
        parent_construction_association_evaluation._recorded_support_labels = (
            previous
        )


def _subset_verified(verified: Any, identifiers: set[str]) -> Any:
    """Return one bounded view without mutating retained evidence."""
    request = verified.request.model_copy(
        update={
            "inputs": tuple(
                item
                for item in verified.request.inputs
                if item.input_id in identifiers
            ),
            "runs": tuple(
                item
                for item in verified.request.runs
                if item.input_id in identifiers
            ),
        }
    )
    values = {
        **vars(verified),
        "request": request,
        "inputs": {
            key: value
            for key, value in verified.inputs.items()
            if key in identifiers
        },
        "runs": {
            key: value
            for key, value in verified.runs.items()
            if key[0] in identifiers
        },
    }
    if is_dataclass(verified):
        return replace(
            cast(Any, verified),
            request=values["request"],
            inputs=values["inputs"],
            runs=values["runs"],
        )
    return SimpleNamespace(**values)


def _compiler(
    frozen: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the exact historical compiler and endpoint registry."""
    compiler = runpy.run_path(str(frozen["_COMPILER_PATH"]))
    frozen["_install_historical_source_view"](compiler)
    terminal = compiler["_configured_terminal"]()
    globals_ = terminal["compile_terminal_analysis"].__globals__
    registry = globals_["load_endpoint_registry"](
        frozen["_REGISTRY_PATH"], frozen["_COMPILER_PATH"]
    )
    return globals_, cast(dict[str, Any], registry)


def _candidate_view(  # noqa: PLR0913
    frozen: dict[str, Any],
    verified: Any,
    scratch: Path,
    *,
    configuration: str,
    revision: str,
    compiler_globals: dict[str, Any],
) -> Any:
    """Attach one exact materialized Hebog product set."""
    return frozen["_prospective_campaign"](
        verified,
        scratch,
        configuration_sha256=configuration,
        revision=revision,
        compiler_globals=compiler_globals,
    )


def _paired_incumbent_view(
    current: Any,
    incumbent: Any,
    compiler_globals: dict[str, Any],
) -> Any:
    """Install incumbent Hebog under one temporary comparator key."""
    runs = dict(current.runs)
    run_type = compiler_globals["VerifiedRun"]
    for campaign_input in current.request.inputs:
        incumbent_run = incumbent.runs[
            (campaign_input.input_id, "hebog", "candidate")
        ]
        reference = current.runs[
            (campaign_input.input_id, "pinned-pybdsf-master", "operational")
        ]
        runs[
            (campaign_input.input_id, "pinned-pybdsf-master", "operational")
        ] = run_type(
            request=reference.request,
            result=incumbent_run.result,
            directory=incumbent_run.directory,
        )
    if is_dataclass(current):
        return replace(cast(Any, current), runs=runs)
    return SimpleNamespace(**{**vars(current), "runs": runs})


def _compile_incumbent_pair(
    parent: dict[str, Any],
    current: Any,
    incumbent: Any,
    root: Path,
    *,
    configuration: str,
) -> tuple[Any, ...]:
    """Compile the mixed pair under the incumbent's permissive schema.

    The current sidecars are independently required to satisfy the complete
    terminal-cycle schema before this call. The historical parent compiler
    accepts those additive diagnostics while correctly parsing incumbent
    sidecars that predate them.
    """
    _, _, historical = parent["_load_source_association_composition"]()
    parent["_install_terminal_parent_static_seams"](historical)
    compiler_globals, registry = _compiler(historical)
    paired = _paired_incumbent_view(current, incumbent, compiler_globals)
    historical["_install_prospective_compiler"](
        compiler_globals, paired, configuration
    )
    _install_mask_separated_compiler(
        compiler_globals,
        measurement_configuration=configuration,
    )
    compiled, _ = compiler_globals["compile_continuum_campaign"](
        paired, registry, root
    )
    return cast(tuple[Any, ...], compiled)


def _product_artifacts(directory: Path) -> dict[str, str]:
    """Return role-to-digest identities from one verified marker."""
    marker = json.loads((directory / "complete.json").read_text())
    return {
        item["role"]: item["sha256"]
        for item in marker["artifacts"]
        if item["role"] != "source-association-json"
    }


def _verify_product_set(
    identifiers: set[str],
    scratch: Path,
    *,
    configuration: str,
    source_tree: str,
) -> str:
    """Verify every marker and return one canonical product-set identity."""
    product_root = scratch / "products"
    directories = {
        path.name: path for path in product_root.iterdir() if path.is_dir()
    }
    if set(directories) != identifiers:
        raise ValueError("prospective smoke product population changed")
    records: list[dict[str, object]] = []
    for input_id in sorted(identifiers):
        directory = directories[input_id]
        marker_path = directory / "complete.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if (
            not isinstance(marker, dict)
            or marker.get("schema_version") != 1
            or marker.get("input_id") != input_id
            or marker.get("configuration_sha256") != configuration
            or marker.get("source_tree_sha256") != source_tree
        ):
            raise ValueError("prospective smoke product marker changed")
        artifacts = marker.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("prospective smoke product artifacts are absent")
        roles: set[str] = set()
        artifact_records: list[dict[str, object]] = []
        for value in artifacts:
            if not isinstance(value, dict):
                raise ValueError(
                    "prospective smoke product artifact malformed"
                )
            role = value.get("role")
            relative_value = value.get("relative_path")
            if not isinstance(role, str) or not isinstance(
                relative_value, str
            ):
                raise ValueError(
                    "prospective smoke product artifact malformed"
                )
            relative = Path(relative_value)
            if (
                role in roles
                or relative.is_absolute()
                or ".." in relative.parts
                or relative.name == "complete.json"
            ):
                raise ValueError("prospective smoke product artifact unsafe")
            roles.add(role)
            path = directory / relative
            if (
                not path.is_file()
                or path.stat().st_size != value.get("byte_count")
                or file_sha256(path) != value.get("sha256")
            ):
                raise ValueError("prospective smoke product artifact changed")
            artifact_records.append(
                {
                    "role": role,
                    "relative_path": relative.as_posix(),
                    "byte_count": value["byte_count"],
                    "sha256": value["sha256"],
                }
            )
        records.append(
            {
                "input_id": input_id,
                "configuration_sha256": configuration,
                "source_tree_sha256": source_tree,
                "artifacts": sorted(
                    artifact_records, key=lambda item: cast(str, item["role"])
                ),
            }
        )
    return canonical_sha256(records)


def _compact_equal(
    identifiers: set[str], current: Path, incumbent: Path
) -> bool:
    """Require byte-identical compact products for every smoke input."""
    compact = tuple(item for item in identifiers if "compact-blend" in item)
    return bool(compact) and all(
        _product_artifacts(current / "products" / input_id)
        == _product_artifacts(incumbent / "products" / input_id)
        for input_id in compact
    )


def _association_paths(
    identifiers: set[str], scratch: Path
) -> tuple[Path, ...]:
    """Resolve every current Continuum sidecar from its exact marker."""
    paths: list[Path] = []
    for input_id in sorted(identifiers):
        if "continuum" not in input_id:
            continue
        directory = scratch / "products" / input_id
        marker = json.loads((directory / "complete.json").read_text())
        matches = [
            item
            for item in marker["artifacts"]
            if item["role"] == "source-association-json"
        ]
        if len(matches) != 1:
            raise ValueError("prospective smoke association is absent")
        path = directory / matches[0]["relative_path"]
        if not path.is_file() or file_sha256(path) != matches[0]["sha256"]:
            raise ValueError("prospective smoke association changed")
        paths.append(path)
    return tuple(paths)


def _planning_deviations(root: Path) -> dict[str, float]:
    """Return the frozen family floors plus aligned axis defaults."""
    contract = json.loads((root / _CONTINUUM_POWER).read_text())
    assumptions = contract["power_audit"]["continuum_assumptions"]
    values = {
        item["metric_family"]: item["planning_paired_standard_deviation"]
        for item in assumptions
    }
    values["absolute-mean-offset-x"] = 0.15
    values["absolute-mean-offset-y"] = 0.15
    return cast(dict[str, float], values)


def _publish(path: Path, record: dict[str, object]) -> None:
    """Atomically publish one write-once finite smoke record."""
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


def main() -> None:
    """Verify, compile, evaluate, and atomically publish the smoke result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--source-request", required=True, type=Path)
    parser.add_argument("--population", required=True, type=Path)
    parser.add_argument("--current-scratch", required=True, type=Path)
    parser.add_argument("--incumbent-scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite smoke result: {arguments.output}"
        )
    root = arguments.repository_root.resolve()
    identifiers = set(
        select_prospective_smoke_inputs(
            arguments.source_request, arguments.population
        )
    )
    materializer = runpy.run_path(str(root / _MATERIALIZER))
    parent = runpy.run_path(str(root / _TERMINAL_PARENT_WRAPPER))
    verified, _ = materializer["_verified_reference"](
        root, arguments.reference_reconstruction
    )
    verified = _subset_verified(verified, identifiers)
    revision = (
        materializer["subprocess"]
        .check_output(("git", "rev-parse", "HEAD"), cwd=root, text=True)
        .strip()
    )
    configuration = materializer["_current_configuration"](root)
    current_source_tree = source_tree_sha256(root)
    current_product_set = _verify_product_set(
        identifiers,
        arguments.current_scratch,
        configuration=configuration,
        source_tree=current_source_tree,
    )
    frozen = materializer["_current_composition"](
        root, revision=revision, configuration=configuration
    )
    compiler_globals, historical_registry = _compiler(frozen)
    current = _candidate_view(
        frozen,
        verified,
        arguments.current_scratch,
        configuration=configuration,
        revision=revision,
        compiler_globals=compiler_globals,
    )
    incumbent_configuration = parent["_CANDIDATE_CONFIGURATION_SHA256"]
    incumbent_revision = parent["_CANDIDATE_REVISION"]
    incumbent_source_tree = parent["_CANDIDATE_SOURCE_TREE_SHA256"]
    incumbent_product_set = _verify_product_set(
        identifiers,
        arguments.incumbent_scratch,
        configuration=incumbent_configuration,
        source_tree=incumbent_source_tree,
    )
    previous_identity = frozen["_candidate_runtime_identity"]
    frozen["_candidate_runtime_identity"] = parent[
        "_candidate_runtime_identity"
    ]
    try:
        incumbent = _candidate_view(
            frozen,
            verified,
            arguments.incumbent_scratch,
            configuration=incumbent_configuration,
            revision=incumbent_revision,
            compiler_globals=compiler_globals,
        )
    finally:
        frozen["_candidate_runtime_identity"] = previous_identity
    with _mask_measurement_separation_evaluation():
        frozen["_install_prospective_compiler"](
            compiler_globals, current, configuration
        )
        _install_mask_separated_compiler(
            compiler_globals,
            measurement_configuration=configuration,
        )
        current_continuum, _ = compiler_globals["compile_continuum_campaign"](
            current, historical_registry, root
        )
        incumbent_continuum = _compile_incumbent_pair(
            parent,
            current,
            incumbent,
            root,
            configuration=configuration,
        )
    association_paths = _association_paths(
        identifiers, arguments.current_scratch
    )
    terminal_cycle = aggregate_terminal_cycle_eligibility(
        association_paths, expected_image_count=64
    )
    registry = load_prospective_endpoint_registry(root / _REGISTRY)
    record = evaluate_prospective_science_smoke(
        registry=registry,
        current_continuum=current_continuum,
        incumbent_paired_continuum=incumbent_continuum,
        planning_deviation_by_family=_planning_deviations(root),
        compact_product_identity_equal=_compact_equal(
            identifiers,
            arguments.current_scratch,
            arguments.incumbent_scratch,
        ),
        terminal_cycle_aggregate=terminal_cycle,
    )
    record.update(
        {
            "candidate_revision": revision,
            "candidate_source_tree_sha256": current_source_tree,
            "candidate_configuration_sha256": configuration,
            "candidate_product_set_canonical_sha256": current_product_set,
            "incumbent_revision": incumbent_revision,
            "incumbent_source_tree_sha256": incumbent_source_tree,
            "incumbent_configuration_sha256": incumbent_configuration,
            "incumbent_product_set_canonical_sha256": incumbent_product_set,
            "selected_input_count": len(identifiers),
            "population_sha256": file_sha256(arguments.population),
            "materializer_sha256": file_sha256(root / _MATERIALIZER),
            "evaluator_sha256": file_sha256(Path(__file__).resolve()),
        }
    )
    _publish(arguments.output, record)
    print(arguments.output)
    print(f"status={record['status']}")


if __name__ == "__main__":
    main()
