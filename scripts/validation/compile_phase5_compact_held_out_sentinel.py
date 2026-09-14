#!/usr/bin/env python3
"""Validate the complete array-free compact sentinel summary population."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.validation.comparison import CatalogueSource
from hebog.validation.datasets import DatasetRecord, SyntheticRecipe
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumFinderId,
    ContinuumTruthObject,
    continuum_catalogue_objects,
    measure_continuum_image,
)
from hebog.validation.phase_five_filter_review import _build_generated_truth

_METRICS = (
    "completeness",
    "reliability",
    "integrated-flux-median",
    "integrated-flux-p95",
    "absolute-mean-offset-x",
    "absolute-mean-offset-y",
    "position-median",
    "position-p95",
    "duplicate-fraction",
    "mask-precision",
    "mask-recall",
    "mask-iou",
    "split-fraction",
    "merge-fraction",
)


def _summary_key(summary: dict[str, object]) -> tuple[str, str]:
    """Return one strict input/finder identity."""
    input_id = summary.get("input_id")
    finder_id = summary.get("finder_id")
    if not isinstance(input_id, str) or not isinstance(finder_id, str):
        raise ValueError("summary identity is malformed")
    return input_id, finder_id


def compile_summaries(
    summaries: list[dict[str, object]],
    *,
    expected_pairs: tuple[tuple[str, str], ...],
) -> tuple[dict[str, object], ...]:
    """Require every expected finder pair once without pooled omission."""
    observed = tuple(_summary_key(summary) for summary in summaries)
    if len(observed) != len(set(observed)):
        raise ValueError("summary population contains duplicate identities")
    expected_set = set(expected_pairs)
    observed_set = set(observed)
    missing = expected_set.difference(observed_set)
    extras = observed_set.difference(expected_set)
    if missing:
        raise ValueError("summary population is incomplete")
    if extras:
        raise ValueError("summary population has extras")
    by_key = dict(zip(observed, summaries, strict=True))
    return tuple(by_key[key] for key in expected_pairs)


def valid_pixels(recipe: SyntheticRecipe) -> npt.NDArray[np.bool_]:
    """Return the exact finite-pixel domain without generating image data."""
    valid = np.ones(recipe.shape_yx, dtype=np.bool_)
    for rectangle in recipe.invalid_rectangles:
        valid[
            rectangle.y_start : rectangle.y_stop,
            rectangle.x_start : rectangle.x_stop,
        ] = False
    return valid


def _observable_position(
    signal: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
) -> tuple[float, float]:
    """Return the flux-weighted centre on the observable truth support."""
    weights = np.where(support, signal, 0.0)
    total = float(np.sum(weights))
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("sentinel truth support has no positive signal")
    y_pixels, x_pixels = np.indices(signal.shape, dtype=np.float64)
    return (
        float(np.sum(weights * x_pixels) / total),
        float(np.sum(weights * y_pixels) / total),
    )


def truth_objects(
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    *,
    review: Any,
) -> tuple[tuple[ContinuumTruthObject, ...], npt.NDArray[np.int64]]:
    """Compile disjoint observable truth groups under the reviewed rules."""
    generated = _build_generated_truth(dataset, review)
    groups = {
        item.identifier: item for item in dataset.multiscale_truth_groups
    }
    strata: dict[str, set[str]] = defaultdict(set)
    for stratum in dataset.multiscale_group_strata:
        for identifier in stratum.group_identifiers:
            strata[identifier].add(stratum.identifier)
    observable = valid_pixels(recipe)
    labels = np.zeros(recipe.shape_yx, dtype=np.int64)
    objects: list[ContinuumTruthObject] = []
    beam_area_pixels = (
        np.pi
        * dataset.beam.major_fwhm_pixels
        * dataset.beam.minor_fwhm_pixels
        / (4.0 * np.log(2.0))
    )
    for label, generated_group in enumerate(generated, start=1):
        group = groups[generated_group.identifier]
        support = generated_group.detection_mask & observable
        if not np.any(support):
            raise ValueError("sentinel truth group has no observable support")
        if np.any(labels[support] != 0):
            raise ValueError("sentinel truth supports overlap")
        labels[support] = label
        objects.append(
            ContinuumTruthObject(
                identifier=group.identifier,
                support_label=label,
                centre_xy=_observable_position(
                    generated_group.signal_jy_per_beam,
                    support,
                ),
                integrated_flux_jy=(
                    group.reference_integrated_brightness_jy_pixels_per_beam
                    / beam_area_pixels
                ),
                catalogue_role=group.catalogue_role,
                strata=tuple(sorted(strata[group.identifier])),
            )
        )
    labels.setflags(write=False)
    return tuple(objects), labels


def _overall_metrics(
    measurements: dict[str, dict[str, float | tuple[float, ...]]],
) -> dict[str, float | list[float]]:
    """Retain only the predeclared whole-image sufficient statistics."""
    output: dict[str, float | list[float]] = {}
    for metric in _METRICS:
        value = measurements.get(metric, {}).get("overall")
        if isinstance(value, tuple):
            output[metric] = [float(item) for item in value]
        elif isinstance(value, (float, int)):
            output[metric] = float(value)
        else:
            raise ValueError(f"sentinel overall metric is absent: {metric}")
    return output


def compile_finder_summary(  # noqa: PLR0913
    *,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
    finder_id: str,
    catalogue: tuple[CatalogueSource, ...],
    label_plane: npt.ArrayLike,
    header: fits.Header,
    review: Any,
    elapsed_seconds: float,
    candidate_revision: str | None,
    runtime_identity: dict[str, object],
) -> dict[str, object]:
    """Compile one finder result to finite array-free comparison evidence."""
    labels = np.asarray(label_plane)
    if (
        labels.shape != recipe.shape_yx
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any(labels < 0)
    ):
        raise ValueError("sentinel finder label plane is invalid")
    compiler_finder: ContinuumFinderId = (
        "hebog" if finder_id == "current-hebog" else "released-pybdsf"
    )
    candidate: tuple[ContinuumCatalogueObject, ...] = (
        continuum_catalogue_objects(
            catalogue,
            labels,
            finder_id=compiler_finder,
            header=header,
        )
    )
    truth, truth_labels = truth_objects(dataset, recipe, review=review)
    measured = measure_continuum_image(
        truth,
        candidate,
        truth_label_plane=truth_labels,
        candidate_label_plane=labels,
        beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
    )
    positive_labels = {int(item) for item in np.unique(labels) if item > 0}
    catalogue_labels = {item.support_label for item in candidate}
    return {
        "candidate_revision": candidate_revision,
        "catalogue_count": len(catalogue),
        "cell_id": _cell_id(dataset.identifier),
        "dataset_identifier": dataset.identifier,
        "elapsed_seconds": float(elapsed_seconds),
        "finder_id": finder_id,
        "input_id": f"{dataset.identifier}-seed-{recipe.seed}",
        "metrics": _overall_metrics(measured),
        "native_support_count": len(positive_labels),
        "ownership_valid": catalogue_labels.issubset(positive_labels),
        "product_valid": True,
        "runtime_identity": runtime_identity,
        "schema_version": 1,
        "seed": recipe.seed,
        "truth_group_count": len(truth),
    }


def _cell_id(dataset_identifier: str) -> str:
    """Remove either governed sentinel population prefix."""
    for prefix in (
        "phase5-sentinel-extended-",
        "phase5-sentinel-compact-guard-",
    ):
        if dataset_identifier.startswith(prefix):
            return dataset_identifier.removeprefix(prefix)
    raise ValueError("sentinel dataset identifier is malformed")


def load_summaries(path: Path) -> list[dict[str, object]]:
    """Load one JSON array without accepting non-object rows."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(
        not isinstance(item, dict) for item in value
    ):
        raise ValueError("sentinel summaries must be a JSON object array")
    return cast(list[dict[str, object]], value)


if __name__ == "__main__":
    raise SystemExit(
        "The compact compiler is invoked by the checksum-bound runner."
    )
