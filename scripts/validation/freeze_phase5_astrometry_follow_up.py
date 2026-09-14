"""Freeze fresh inputs for the Phase 5 extended-position follow-up."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from math import cos, pi, radians, sin
from pathlib import Path
from typing import cast

from hebog.validation.contracts import PhaseFiveAstrometryFollowUpReview
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    SyntheticSource,
    recipe_sha256,
)

_DEVELOPMENT_FIRST_SEEDS = (
    2026760001,
    2026761001,
    2026762001,
    2026763001,
)
_CONFIRMATION_FIRST_SEEDS = (
    2026770001,
    2026771001,
    2026772001,
    2026773001,
)
_DEVELOPMENT_REALIZATIONS = 20
_CONFIRMATION_REALIZATIONS = 100
_EDGE_CENTRE_MAXIMUM_X = 20.0
_BEAMS = (
    (5.2, 3.3, 12.0),
    (5.8, 3.9, 47.0),
    (4.8, 3.1, 83.0),
    (6.1, 4.2, -24.0),
    (5.4, 3.6, 31.0),
    (6.3, 4.0, 68.0),
    (4.9, 3.2, -41.0),
    (5.7, 3.7, 106.0),
)
_ROTATIONS = (18.0, -33.0, 57.0, 102.0, 26.0, -51.0, 74.0, 129.0)
_SIZE_FACTORS = (0.88, 1.12, 0.97, 1.18, 1.05, 0.92, 1.14, 0.84)
_PEAK_FACTORS = (0.9, 1.08, 0.96, 1.15, 1.04, 0.87, 1.12, 0.93)
_GENERAL_SHIFTS = (
    (-24.0, 18.0),
    (20.0, -22.0),
    (36.0, 24.0),
    (-31.0, -26.0),
    (13.0, 31.0),
    (-18.0, -34.0),
    (28.0, -15.0),
    (-35.0, 12.0),
)
_SHELL_CENTRES = (
    (520.0, 520.0),
    (517.0, 523.0),
    (523.0, 517.0),
    (519.0, 521.0),
    (522.0, 519.0),
    (516.0, 524.0),
    (524.0, 516.0),
    (518.0, 522.0),
)
_MIXED_CENTRES = (
    (775.0, 279.0),
    (778.0, 282.0),
    (776.0, 281.0),
    (780.0, 278.0),
    (777.0, 280.0),
    (779.0, 283.0),
    (774.0, 277.0),
    (781.0, 281.0),
)
_EDGE_CENTRES = (
    (1.5, 618.0),
    (2.5, 672.0),
    (0.8, 705.0),
    (3.0, 594.0),
    (1.2, 731.0),
    (2.2, 653.0),
    (0.6, 687.0),
    (2.8, 614.0),
)


@dataclass(frozen=True)
class _PopulationSpec:
    """Inputs distinguishing a fresh development or confirmation role."""

    role: str
    label: str
    first_seeds: tuple[int, ...]
    realizations: int
    variant_offset: int


def _sha256(path: Path) -> str:
    """Return the exact identity of one frozen input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(document: dict[str, object]) -> bytes:
    """Serialize a frozen record canonically."""
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _group_quantities(
    sources: tuple[SyntheticSource, ...],
) -> tuple[tuple[float, float], float]:
    """Return analytic integrated-flux centroid and brightness."""
    brightnesses = tuple(
        source.peak_flux_jy_per_beam
        * 2.0
        * pi
        * source.major_sigma_pixels
        * source.minor_sigma_pixels
        for source in sources
    )
    total = sum(brightnesses)
    return (
        (
            sum(
                brightness * source.x_pixel
                for brightness, source in zip(
                    brightnesses, sources, strict=True
                )
            )
            / total,
            sum(
                brightness * source.y_pixel
                for brightness, source in zip(
                    brightnesses, sources, strict=True
                )
            )
            / total,
        ),
        total,
    )


def _target_centre(
    morphology: str,
    original_centre: tuple[float, float],
    variant: int,
) -> tuple[float, float]:
    """Preserve governed boundaries while varying every source geometry."""
    if morphology == "shell":
        return _SHELL_CENTRES[variant]
    if morphology == "mixed-compact-extended":
        return _MIXED_CENTRES[variant]
    if morphology == "filament":
        return (512.0, 267.0 + _GENERAL_SHIFTS[variant][1] / 4.0)
    if morphology == "diffuse" and original_centre[0] < _EDGE_CENTRE_MAXIMUM_X:
        return _EDGE_CENTRES[variant]
    shift_x, shift_y = _GENERAL_SHIFTS[variant]
    return (original_centre[0] + shift_x, original_centre[1] + shift_y)


def _transform_group(
    sources: tuple[SyntheticSource, ...],
    *,
    morphology: str,
    variant: int,
) -> tuple[SyntheticSource, ...]:
    """Rotate, resize, translate, and reweight one complete truth group."""
    original_centre, _ = _group_quantities(sources)
    target_x, target_y = _target_centre(morphology, original_centre, variant)
    angle = _ROTATIONS[variant]
    cosine = cos(radians(angle))
    sine = sin(radians(angle))
    geometry_scale = _SIZE_FACTORS[variant]
    transformed: list[SyntheticSource] = []
    for index, source in enumerate(sources):
        offset_x = source.x_pixel - original_centre[0]
        offset_y = source.y_pixel - original_centre[1]
        rotated_x = geometry_scale * (cosine * offset_x - sine * offset_y)
        rotated_y = geometry_scale * (sine * offset_x + cosine * offset_y)
        if morphology == "mixed-compact-extended" and index == 1:
            rotated_x += (-1.0, 1.5, -1.5, 2.0)[variant % 4]
            rotated_y += (1.0, -1.0, 1.5, -1.5)[variant % 4]
        contrast = 1.0 + 0.08 * (
            ((index + 2 * variant) % max(2, len(sources)))
            - (max(2, len(sources)) - 1) / 2.0
        )
        peak = source.peak_flux_jy_per_beam * _PEAK_FACTORS[variant]
        peak *= contrast
        shape_scale = geometry_scale * (1.0 + 0.025 * (index - 1))
        transformed.append(
            source.model_copy(
                update={
                    "x_pixel": target_x + rotated_x,
                    "y_pixel": target_y + rotated_y,
                    "peak_flux_jy_per_beam": peak,
                    "major_sigma_pixels": (
                        source.major_sigma_pixels * shape_scale
                    ),
                    "minor_sigma_pixels": (
                        source.minor_sigma_pixels * shape_scale
                    ),
                    "rotation_degrees_counterclockwise_from_x": (
                        source.rotation_degrees_counterclockwise_from_x + angle
                    )
                    % 180.0,
                }
            )
        )
    return tuple(transformed)


def _vary_all_groups(record: dict[str, object], variant: int) -> None:
    """Replace every truth group and refresh its analytic reference values."""
    recipe = cast(dict[str, object], record["recipe"])
    original_sources = tuple(
        SyntheticSource.model_validate(source)
        for source in cast(list[dict[str, object]], recipe["sources"])
    )
    groups = cast(list[dict[str, object]], record["multiscale_truth_groups"])
    varied_sources: list[SyntheticSource] = []
    for group in groups:
        group_sources = tuple(
            original_sources[index]
            for index in cast(list[int], group["source_indices"])
        )
        transformed = _transform_group(
            group_sources,
            morphology=cast(str, group["morphology"]),
            variant=variant,
        )
        start = len(varied_sources)
        varied_sources.extend(transformed)
        group["source_indices"] = list(range(start, len(varied_sources)))
        position, brightness = _group_quantities(transformed)
        group["reference_position_xy"] = list(position)
        group["reference_integrated_brightness_jy_pixels_per_beam"] = (
            brightness
        )
        group["major_extent_beams"] = float(
            cast(float, group["major_extent_beams"]) * _SIZE_FACTORS[variant]
        )
        group["minor_extent_beams"] = float(
            cast(float, group["minor_extent_beams"]) * _SIZE_FACTORS[variant]
        )
    recipe["sources"] = [
        source.model_dump(mode="json") for source in varied_sources
    ]


def _dataset(
    template: DatasetRecord,
    *,
    spec: _PopulationSpec,
    population_variant: int,
) -> DatasetRecord:
    """Build one geometry-specific record with disjoint noise seeds."""
    variant = spec.variant_offset + population_variant
    first_seed = spec.first_seeds[population_variant]
    record = cast(
        dict[str, object], deepcopy(template.model_dump(mode="json"))
    )
    record["identifier"] = (
        f"phase5-astrometry-follow-up-{spec.label}-"
        f"{population_variant + 1}-1024"
    )
    record["role"] = spec.role
    record["purpose"] = (
        f"Fresh {spec.label} geometry {population_variant + 1} for the "
        "detected-segment extended-position contract."
    )
    record["provenance"] = (
        "Step 2C-HR population frozen before segment-estimator "
        "implementation or result generation; all astronomical morphology "
        "geometries and noise seeds are disjoint from prior campaigns."
    )
    major, minor, beam_angle = _BEAMS[variant]
    record["beam"] = {
        "major_fwhm_pixels": major,
        "minor_fwhm_pixels": minor,
        "position_angle_degrees": beam_angle,
    }
    wcs = cast(dict[str, object], record["wcs"])
    wcs["rotation_degrees_counterclockwise"] = beam_angle / 2.5
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = first_seed
    recipe["noise_correlation"] = {
        "major_fwhm_pixels": major,
        "minor_fwhm_pixels": minor,
        "position_angle_degrees": beam_angle,
        "truncation_sigma": 4.0,
    }
    _vary_all_groups(record, variant)
    record["noise_realization_seeds"] = list(
        range(first_seed + 1, first_seed + spec.realizations)
    )
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    return DatasetRecord.model_validate(record)


def _manifest(
    template: DatasetRecord,
    spec: _PopulationSpec,
) -> DatasetManifest:
    """Build one four-geometry follow-up manifest."""
    return DatasetManifest(
        schema_version=3,
        manifest_id=f"phase-5-astrometry-follow-up-{spec.label}",
        datasets=tuple(
            _dataset(template, spec=spec, population_variant=variant)
            for variant in range(4)
        ),
    )


def _documents(
    template_path: Path,
    prior_decision_path: Path,
    technical_review_path: Path,
    base_detection_protocol_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build and validate fresh manifests and their bound protocol."""
    template_manifest = DatasetManifest.model_validate_json(
        template_path.read_text(encoding="utf-8")
    )
    if len(template_manifest.datasets) != 1:
        raise ValueError("astrometry follow-up requires one Phase 5 template")
    template = template_manifest.datasets[0]
    development = _manifest(
        template,
        _PopulationSpec(
            role="development",
            label="development",
            first_seeds=_DEVELOPMENT_FIRST_SEEDS,
            realizations=_DEVELOPMENT_REALIZATIONS,
            variant_offset=0,
        ),
    )
    confirmation = _manifest(
        template,
        _PopulationSpec(
            role="regression",
            label="confirmation",
            first_seeds=_CONFIRMATION_FIRST_SEEDS,
            realizations=_CONFIRMATION_REALIZATIONS,
            variant_offset=4,
        ),
    )
    development_document = cast(
        dict[str, object], development.model_dump(mode="json")
    )
    confirmation_document = cast(
        dict[str, object], confirmation.model_dump(mode="json")
    )
    protocol_document: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "phase-5-astrometry-follow-up-review",
        "status": "frozen-before-follow-up-development-results",
        "prior_decision_sha256": _sha256(prior_decision_path),
        "technical_review_sha256": _sha256(technical_review_path),
        "base_detection_protocol_sha256": _sha256(
            base_detection_protocol_path
        ),
        "technical_review_author": "Codex AI technical review",
        "independent_human_review_complete": False,
        "closed_population_policy": (
            "no-tuning-rescoring-confirmation-or-selection"
        ),
        "dataset_manifests": [
            {
                "role": "development",
                "manifest": (
                    "config/datasets/"
                    "phase-5-astrometry-follow-up-development.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(development_document)
                ).hexdigest(),
                "image_count": 80,
            },
            {
                "role": "regression",
                "manifest": (
                    "config/datasets/"
                    "phase-5-astrometry-follow-up-confirmation.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(confirmation_document)
                ).hexdigest(),
                "image_count": 400,
            },
        ],
        "compact_position": {
            "position": "fitted-gaussian-component-centre",
            "maximum_median_position_beams": 0.1,
            "maximum_percentile_95_position_beams": 0.25,
        },
        "extended_position": {
            "position": "detected-segment-flux-centroid",
            "truth_target": ("noiseless-three-sigma-truth-segment-centroid"),
            "peak_position": "brightest-original-pixel",
            "host_position_claim": False,
            "former_full_observable_target": "diagnostic-only",
        },
        "estimator": {
            "candidate": "original-pixel-detected-segment-centroid",
            "detection_provenance": "residual-b3-atrous",
            "measurement_pixels": "original-background-subtracted",
            "support": "accepted-b3-associated-original-pixel-segment",
            "weighting": "signed-flux",
            "centroid_support_dilation_pixels": 0,
            "peak_tie_breaking": "row-major-first",
            "position_uncertainty": (
                "unavailable-until-support-selection-calibrated"
            ),
        },
        "endpoint": {
            "observation_unit": "eligible-astronomical-truth-group",
            "independent_unit": "noise-seed-image",
            "resampling": ("whole-image-cluster-bootstrap-retain-all-groups"),
            "bootstrap_resamples": 10_000,
            "bootstrap_seed": 20260809,
            "confidence_level": 0.95,
            "availability_fraction": 1.0,
            "maximum_absolute_axis_bias_beams": 0.1,
            "maximum_radial_percentile_95_beams": 0.5,
            "binding_rule": (
                "one-sided-confidence-bound-passes-every-governed-stratum"
            ),
            "radial_median": "report-only",
        },
        "governed_strata": [
            "above-compact-deblend-limit",
            "image-edge",
            "invalid-pixels",
            "morphology-artifact",
            "morphology-curved-filament",
            "morphology-diffuse",
            "morphology-filament",
            "morphology-mixed-compact-extended",
            "morphology-shell",
            "scale-1-beam",
            "scale-2-beam",
            "scale-4-beam",
            "tile-boundary",
            "tile-corner",
            "varying-noise",
        ],
        "external_position_mappings": [
            ("pybdsf-source-moment-where-grouping-and-model-semantics-align"),
            "aegean-component-centre-compact-gaussian-scope-only",
            "selavy-island-centroid-semantic-precedent",
            "profound-segment-centroid-semantic-precedent",
        ],
        "development_execution_authorized": True,
        "confirmation_execution_authorized": False,
        "step_two_c_p_execution_authorized": False,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
    }
    protocol = PhaseFiveAstrometryFollowUpReview.model_validate(
        protocol_document
    )
    return (
        development_document,
        confirmation_document,
        cast(dict[str, object], protocol.model_dump(mode="json")),
    )


def _parse_args() -> argparse.Namespace:
    """Parse paths while keeping scientific choices fixed in code."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=root / "config/datasets/phase-5-regression.json",
    )
    parser.add_argument(
        "--prior-decision",
        type=Path,
        default=(
            root
            / "config/contracts/phase-5-astrometry-selection-decision.json"
        ),
    )
    parser.add_argument(
        "--technical-review",
        type=Path,
        default=(
            root / "docs/reference/phase-5-astrometry-follow-up-review.md"
        ),
    )
    parser.add_argument(
        "--base-detection-protocol",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-review.json",
    )
    parser.add_argument(
        "--development-output",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-astrometry-follow-up-development.json"
        ),
    )
    parser.add_argument(
        "--confirmation-output",
        type=Path,
        default=(
            root / "config/datasets/"
            "phase-5-astrometry-follow-up-confirmation.json"
        ),
    )
    parser.add_argument(
        "--protocol-output",
        type=Path,
        default=(
            root / "config/contracts/phase-5-astrometry-follow-up-review.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Write all frozen inputs once, refusing a partial replacement."""
    arguments = _parse_args()
    outputs = (
        arguments.development_output,
        arguments.confirmation_output,
        arguments.protocol_output,
    )
    existing = tuple(path for path in outputs if path.exists())
    if existing:
        raise FileExistsError(
            f"refusing to overwrite frozen inputs: {existing}"
        )
    documents = _documents(
        arguments.template,
        arguments.prior_decision,
        arguments.technical_review,
        arguments.base_detection_protocol,
    )
    for path, document in zip(outputs, documents, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_json_bytes(document))


if __name__ == "__main__":
    main()
