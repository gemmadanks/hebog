"""Freeze the reviewed Phase 4U compact-blend qualification population."""

from __future__ import annotations

import argparse
import json
from math import cos, pi, radians, sin
from pathlib import Path
from typing import cast

import numpy as np

from hebog.validation.datasets import (
    DatasetManifest,
    SyntheticRecipe,
    load_dataset_manifest,
    recipe_sha256,
)

_FIRST_SEED = 2026600001
_REALIZATION_COUNT = 800
_FWHM_TO_SIGMA = 1.0 / np.sqrt(8.0 * np.log(2.0))
_TOTAL_BLEND_PEAK_SNR = 27.0
_BLEND_CASES = (
    ((105.0, 105.0), 0.45, 0.0, 1.0),
    ((205.0, 105.0), 0.45, 90.0, 0.5),
    ((305.0, 105.0), 0.65, 45.0, 1.0),
    ((405.0, 105.0), 0.65, 0.0, 0.5),
    ((105.0, 285.0), 0.80, 90.0, 1.0),
    ((405.0, 285.0), 0.80, 45.0, 0.5),
)


def _integrated_brightness(source: dict[str, float]) -> float:
    """Return the analytic integral of one injected Gaussian."""
    return (
        2.0
        * pi
        * source["peak_flux_jy_per_beam"]
        * source["major_sigma_pixels"]
        * source["minor_sigma_pixels"]
    )


def _blend_population(
    *,
    noise_rms: float,
    beam_major_fwhm: float,
    beam_minor_fwhm: float,
    beam_angle_degrees: float,
    first_source_index: int,
) -> tuple[list[dict[str, float]], list[dict[str, object]]]:
    """Build six pairwise-crossed unresolved blend geometries."""
    major_sigma = beam_major_fwhm * _FWHM_TO_SIGMA
    minor_sigma = beam_minor_fwhm * _FWHM_TO_SIGMA
    total_peak = _TOTAL_BLEND_PEAK_SNR * noise_rms
    sources: list[dict[str, float]] = []
    groups: list[dict[str, object]] = []
    for index, (center, separation_beams, angle_offset, ratio) in enumerate(
        _BLEND_CASES,
        start=1,
    ):
        angle_offset_radians = radians(angle_offset)
        directional_fwhm = 1.0 / np.sqrt(
            (cos(angle_offset_radians) / beam_major_fwhm) ** 2
            + (sin(angle_offset_radians) / beam_minor_fwhm) ** 2
        )
        separation_pixels = separation_beams * directional_fwhm
        angle = radians(beam_angle_degrees + angle_offset)
        half_offset = (
            0.5 * separation_pixels * cos(angle),
            0.5 * separation_pixels * sin(angle),
        )
        bright_peak = total_peak / (1.0 + ratio)
        faint_peak = total_peak - bright_peak
        pair = [
            {
                "x_pixel": center[0] - half_offset[0],
                "y_pixel": center[1] - half_offset[1],
                "peak_flux_jy_per_beam": bright_peak,
                "major_sigma_pixels": major_sigma,
                "minor_sigma_pixels": minor_sigma,
                "rotation_degrees_counterclockwise_from_x": (
                    beam_angle_degrees
                ),
            },
            {
                "x_pixel": center[0] + half_offset[0],
                "y_pixel": center[1] + half_offset[1],
                "peak_flux_jy_per_beam": faint_peak,
                "major_sigma_pixels": major_sigma,
                "minor_sigma_pixels": minor_sigma,
                "rotation_degrees_counterclockwise_from_x": (
                    beam_angle_degrees
                ),
            },
        ]
        source_indices = [
            first_source_index + len(sources),
            first_source_index + len(sources) + 1,
        ]
        integrals = [_integrated_brightness(source) for source in pair]
        total_integral = sum(integrals)
        groups.append(
            {
                "identifier": f"blend-{index:05d}",
                "source_indices": source_indices,
                "resolution_class": "unresolved-blend",
                "reference_position_xy": [
                    sum(
                        source[axis] * integrated
                        for source, integrated in zip(
                            pair, integrals, strict=True
                        )
                    )
                    / total_integral
                    for axis in ("x_pixel", "y_pixel")
                ],
                "reference_integrated_brightness_jy_pixels_per_beam": (
                    total_integral
                ),
            }
        )
        sources.extend(pair)
    return sources, groups


def _document(template: Path) -> dict[str, object]:
    """Derive an unopened population from the reviewed compact field."""
    template_manifest = load_dataset_manifest(template)
    if template_manifest.manifest_id != "phase-4t-qualification":
        raise ValueError(
            "Phase 4U requires the frozen Phase 4T field template"
        )
    base = template_manifest.datasets[0]
    individual_groups = [
        group
        for group in base.association_truth_groups
        if group.resolution_class == "individually-resolvable"
    ]
    individual_indices = sorted(
        index for group in individual_groups for index in group.source_indices
    )
    if individual_indices != list(range(48)):
        raise ValueError("Phase 4T individual-source template changed")
    beam = base.beam
    blend_sources, blend_groups = _blend_population(
        noise_rms=base.recipe.noise_rms,
        beam_major_fwhm=beam.major_fwhm_pixels,
        beam_minor_fwhm=beam.minor_fwhm_pixels,
        beam_angle_degrees=beam.position_angle_degrees,
        first_source_index=len(individual_indices),
    )
    recipe_document = base.recipe.model_dump(mode="json")
    recipe_document.update(
        {
            "seed": _FIRST_SEED,
            "sources": [
                base.recipe.sources[index].model_dump(mode="json")
                for index in individual_indices
            ]
            + blend_sources,
        }
    )
    recipe = SyntheticRecipe.model_validate(recipe_document)
    dataset = base.model_dump(mode="json")
    dataset.update(
        {
            "identifier": "phase4u-blend-qualification-512",
            "purpose": (
                "One frozen unseen Phase 4U qualification of corrected "
                "compact blend photometry across separation, angle, and "
                "flux ratio."
            ),
            "provenance": (
                "Frozen ungenerated and unopened after the immutable Phase 4T "
                "failure and a seed-disjoint analytic/generated remediation. "
                "The project owner authorized AI expert review before freeze; "
                "independent human review remains a production gate. Exact "
                "references, unchanged absolute gates, and the one-look rule "
                "are immutable. No controlled real residual/noise injection "
                "was available; this limitation prevents a real-data claim."
            ),
            "recipe": recipe.model_dump(mode="json"),
            "recipe_sha256": recipe_sha256(recipe),
            "noise_realization_seeds": list(
                range(_FIRST_SEED + 1, _FIRST_SEED + _REALIZATION_COUNT)
            ),
            "association_truth_groups": [
                group.model_dump(mode="json") for group in individual_groups
            ]
            + blend_groups,
            "association_group_strata": [
                {
                    "identifier": "unresolved-blend",
                    "group_identifiers": [
                        f"blend-{index:05d}" for index in range(1, 7)
                    ],
                },
                {
                    "identifier": "blend-equal-flux",
                    "group_identifiers": [
                        "blend-00001",
                        "blend-00003",
                        "blend-00005",
                    ],
                },
                {
                    "identifier": "blend-two-to-one-flux",
                    "group_identifiers": [
                        "blend-00002",
                        "blend-00004",
                        "blend-00006",
                    ],
                },
            ],
        }
    )
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": 2,
            "manifest_id": "phase-4u-qualification",
            "datasets": [dataset],
        }
    )
    return cast(dict[str, object], manifest.model_dump(mode="json"))


def _parse_args() -> argparse.Namespace:
    """Parse the immutable template and output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Write the canonical manifest without replacing any prior file."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite frozen manifest: {arguments.output}"
        )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            _document(arguments.template),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
