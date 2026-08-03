"""Shared provenance and failure helpers for isolated campaign runners."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

from hebog.validation.comparison import CatalogueOutlierThresholds
from hebog.validation.contracts import load_phase_four_scientific_gates
from hebog.validation.datasets import DatasetRecord, load_dataset_manifest
from hebog.validation.evidence import (
    CampaignFailure,
    DatasetIdentity,
    WorkloadClass,
)


def canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value without presentation whitespace."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def json_document(path: Path) -> object:
    """Load one scientific contract as JSON for canonical hashing."""
    return json.loads(path.read_text(encoding="utf-8"))


def contract_set_sha256(paths: list[Path]) -> str:
    """Bind the ordered shared scientific contracts used by every shard."""
    if not paths:
        raise ValueError("at least one scientific contract is required")
    return canonical_sha256([json_document(path) for path in paths])


def dependency_inventory_sha256() -> str:
    """Hash the complete installed distribution inventory."""
    inventory = sorted(
        (
            {
                "name": distribution.metadata["Name"]
                .lower()
                .replace("_", "-"),
                "version": distribution.version,
            }
            for distribution in importlib.metadata.distributions()
        ),
        key=lambda item: item["name"],
    )
    return canonical_sha256(inventory)


def failure_from_exception(
    error: Exception,
    *,
    stage: str,
    traceback_text: str,
) -> CampaignFailure:
    """Convert an implementation exception to stable paired evidence."""
    message = str(error).strip() or repr(error)
    return CampaignFailure(
        stage=stage,
        exception_type=type(error).__name__,
        message=message,
        traceback_sha256=hashlib.sha256(
            traceback_text.encode("utf-8")
        ).hexdigest(),
    )


def dataset_by_identifier(path: Path, identifier: str) -> DatasetRecord:
    """Resolve one exact governed dataset."""
    matches = tuple(
        dataset
        for dataset in load_dataset_manifest(path).datasets
        if dataset.identifier == identifier
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected one dataset named {identifier!r}, found {len(matches)}"
        )
    return matches[0]


def campaign_dataset_identity(dataset: DatasetRecord) -> DatasetIdentity:
    """Bind the complete recipe, seed population, truth, WCS, and strata."""
    content_sha256 = canonical_sha256(dataset.model_dump(mode="json"))
    return DatasetIdentity(
        identifier=dataset.identifier,
        role=dataset.role,
        content_sha256=content_sha256,
        shape_yx=dataset.recipe.shape_yx,
        workload_class=WorkloadClass.NORMAL,
    )


def phase_four_outlier_thresholds(path: Path) -> CatalogueOutlierThresholds:
    """Load the unchanged community-science catastrophic thresholds."""
    outlier = load_phase_four_scientific_gates(path).catastrophic_outlier
    return CatalogueOutlierThresholds(
        position_beams=outlier.position_beams,
        peak_flux_fractional_difference=(
            outlier.peak_flux_fractional_difference
        ),
        integrated_flux_fractional_difference=(
            outlier.integrated_flux_fractional_difference
        ),
        fitted_axis_fractional_difference=(
            outlier.fitted_axis_fractional_difference
        ),
        deconvolved_axis_fractional_difference=(
            outlier.deconvolved_axis_fractional_difference
        ),
    )
