#!/usr/bin/env python3
"""Repair result-neutral paired tail diagnostics without changing science."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast


def truth_linked_tail_record(  # noqa: PLR0913
    *,
    parent: Mapping[str, Any],
    current: Any,
    incumbent: Any,
    compiler_globals: Mapping[str, Any],
    historical_registry: Mapping[str, object],
    repository_root: Path,
    source_request: Path,
    smoke: Mapping[str, Any],
    preparer: Mapping[str, Any],
) -> dict[str, object]:
    """Compile frozen tail diagnostics with distinct scientific label roles.

    Catalogue-source memberships describe measurement supports, whereas
    published-mask statistics describe only publication supports.  Hebog may
    deliberately omit a low-persistence measurement support from publication,
    so association objects must be reconstructed from measurement labels when
    that artifact exists.  Reference finders use publication labels for both
    roles because they do not expose a separate measurement-label product.
    """
    memberships = parent["_sentinel_memberships"](
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
            artifact_roles = {
                artifact.role for artifact in run.result.artifacts
            }
            association_labels = (
                smoke["_measurement_label_plane"](run)
                if run.result.finder_id == "hebog"
                and "measurement-labels-fits" in artifact_roles
                else publication_labels
            )
            candidates = compiler_globals["_candidate_objects"](
                catalogue,
                association_labels,
                finder_id=run.result.finder_id,
                header=header,
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
                source_member_counts=parent["_source_member_counts"](
                    catalogue, candidates
                ),
                hierarchy_diagnostics=parent["_hierarchy_diagnostics"](
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
            summary["record_sha256"] = parent["canonical_sha256"](summary)
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
        "summaries_sha256": parent["canonical_sha256"](summaries),
        "array_planes_retained": False,
        "promotion_effect": "none-diagnostic-only",
    }
