"""Freeze fresh Phase 5 astrometry development and confirmation inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from math import pi
from pathlib import Path
from typing import cast

from hebog.validation.contracts import PhaseFiveAstrometryRevisionReview
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRecord,
    SyntheticRecipe,
    SyntheticSource,
    recipe_sha256,
)

_DEVELOPMENT_FIRST_SEEDS = (
    2026740001,
    2026741001,
    2026742001,
    2026743001,
)
_CONFIRMATION_FIRST_SEEDS = (
    2026750001,
    2026751001,
    2026752001,
    2026753001,
)
_DEVELOPMENT_REALIZATIONS = 10
_CONFIRMATION_REALIZATIONS = 100
_BEAMS = (
    (5.0, 3.5, 20.0),
    (5.5, 3.75, 42.0),
    (6.0, 4.0, 75.0),
    (4.75, 3.0, -15.0),
    (5.25, 3.25, 5.0),
    (5.75, 4.0, 52.0),
    (4.9, 3.4, 98.0),
    (6.25, 4.25, -32.0),
)


def _source(
    position_xy: tuple[float, float],
    peak: float,
    shape: tuple[float, float, float],
) -> SyntheticSource:
    """Build one explicit curved-filament Gaussian knot."""
    x, y = position_xy
    major, minor, rotation = shape
    return SyntheticSource(
        x_pixel=x,
        y_pixel=y,
        peak_flux_jy_per_beam=peak,
        major_sigma_pixels=major,
        minor_sigma_pixels=minor,
        rotation_degrees_counterclockwise_from_x=rotation,
    )


_DEVELOPMENT_CURVES = (
    (
        _source((199, 500), 0.0015, (6.0, 2.0, 135)),
        _source((219, 486), 0.0021, (6.0, 2.0, 0)),
        _source((239, 500), 0.0017, (6.0, 2.0, 45)),
    ),
    (
        _source((207, 478), 0.0014, (5.5, 1.8, 110)),
        _source((218, 489), 0.0020, (6.5, 2.2, 75)),
        _source((224, 505), 0.0018, (6.0, 2.0, 105)),
        _source((216, 522), 0.0013, (5.0, 1.8, 135)),
    ),
    (
        _source((195, 486), 0.0012, (5.0, 1.7, 35)),
        _source((207, 496), 0.0017, (5.5, 1.8, 20)),
        _source((220, 501), 0.0022, (6.5, 2.1, 0)),
        _source((234, 496), 0.0016, (5.5, 1.8, -20)),
        _source((246, 484), 0.0011, (5.0, 1.7, -40)),
    ),
    (
        _source((190, 508), 0.0011, (5.0, 1.6, -25)),
        _source((202, 498), 0.0015, (5.5, 1.8, -40)),
        _source((214, 488), 0.0020, (6.0, 2.0, -15)),
        _source((227, 486), 0.0019, (6.0, 2.0, 15)),
        _source((240, 495), 0.0014, (5.5, 1.8, 40)),
        _source((251, 508), 0.0010, (5.0, 1.6, 25)),
    ),
)

_CONFIRMATION_CURVES = (
    (
        _source((196, 505), 0.0013, (5.4, 1.9, 125)),
        _source((210, 489), 0.0018, (6.2, 2.0, 145)),
        _source((228, 488), 0.0020, (6.0, 2.1, 35)),
        _source((244, 503), 0.0012, (5.2, 1.8, 55)),
    ),
    (
        _source((229, 469), 0.0011, (5.0, 1.7, 65)),
        _source((215, 483), 0.0015, (5.6, 1.9, 100)),
        _source((209, 499), 0.0022, (6.4, 2.2, 90)),
        _source((215, 516), 0.0017, (5.7, 1.9, 80)),
        _source((231, 529), 0.0010, (5.0, 1.7, 115)),
    ),
    (
        _source((191, 479), 0.0010, (5.0, 1.6, 25)),
        _source((202, 488), 0.0014, (5.4, 1.8, 35)),
        _source((214, 498), 0.0019, (6.0, 2.0, 20)),
        _source((227, 505), 0.0021, (6.2, 2.1, 0)),
        _source((241, 506), 0.0015, (5.5, 1.8, -15)),
        _source((253, 499), 0.0011, (5.0, 1.6, -35)),
    ),
    (
        _source((187, 503), 0.0009, (4.8, 1.6, -20)),
        _source((198, 493), 0.0012, (5.0, 1.7, -35)),
        _source((210, 484), 0.0017, (5.8, 1.9, -20)),
        _source((223, 481), 0.0023, (6.5, 2.2, 0)),
        _source((236, 487), 0.0018, (5.9, 2.0, 25)),
        _source((247, 499), 0.0013, (5.2, 1.7, 40)),
        _source((254, 514), 0.0009, (4.8, 1.6, 65)),
    ),
)


@dataclass(frozen=True)
class _DatasetSpec:
    """Inputs that distinguish one astrometry dataset geometry."""

    role: str
    label: str
    variant: int
    first_seed: int
    realizations: int
    curve_sources: tuple[SyntheticSource, ...]
    beam: tuple[float, float, float]


@dataclass(frozen=True)
class _PopulationSpec:
    """Inputs that distinguish one frozen astrometry population."""

    role: str
    label: str
    first_seeds: tuple[int, ...]
    realizations: int
    curves: tuple[tuple[SyntheticSource, ...], ...]
    beams: tuple[tuple[float, float, float], ...]


def _sha256(path: Path) -> str:
    """Return the exact identity of one frozen input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(document: dict[str, object]) -> bytes:
    """Serialize one frozen record canonically for embedded checksums."""
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _group_quantities(
    sources: tuple[SyntheticSource, ...],
) -> tuple[tuple[float, float], float]:
    """Return the analytic integrated-flux centroid and brightness."""
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


def _replace_curve(
    record: dict[str, object],
    curve_sources: tuple[SyntheticSource, ...],
) -> None:
    """Replace one curve while preserving all other governed truth groups."""
    recipe = cast(dict[str, object], record["recipe"])
    old_sources = tuple(
        SyntheticSource.model_validate(source)
        for source in cast(list[dict[str, object]], recipe["sources"])
    )
    groups = cast(list[dict[str, object]], record["multiscale_truth_groups"])
    new_sources: list[SyntheticSource] = []
    for group in groups:
        group_sources = (
            curve_sources
            if group["morphology"] == "curved-filament"
            else tuple(
                old_sources[index]
                for index in cast(list[int], group["source_indices"])
            )
        )
        start = len(new_sources)
        new_sources.extend(group_sources)
        group["source_indices"] = list(range(start, len(new_sources)))
        position, brightness = _group_quantities(group_sources)
        group["reference_position_xy"] = list(position)
        group["reference_integrated_brightness_jy_pixels_per_beam"] = (
            brightness
        )
        if group["morphology"] == "curved-filament":
            group["major_extent_beams"] = 12.0
            group["minor_extent_beams"] = 3.0
    recipe["sources"] = [
        source.model_dump(mode="json") for source in new_sources
    ]


def _dataset(
    template: DatasetRecord,
    spec: _DatasetSpec,
) -> DatasetRecord:
    """Build one geometry-specific record with a disjoint noise population."""
    record = cast(
        dict[str, object], deepcopy(template.model_dump(mode="json"))
    )
    record["identifier"] = (
        f"phase5-astrometry-{spec.label}-{spec.variant + 1}-1024"
    )
    record["role"] = spec.role
    record["purpose"] = (
        f"Fresh {spec.label} astrometry geometry {spec.variant + 1} for "
        "direct and "
        "model-assisted extended-position comparison."
    )
    record["provenance"] = (
        "Approved Step 2C-H population frozen before successor estimator "
        "implementation or result generation."
    )
    major, minor, angle = spec.beam
    record["beam"] = {
        "major_fwhm_pixels": major,
        "minor_fwhm_pixels": minor,
        "position_angle_degrees": angle,
    }
    wcs = cast(dict[str, object], record["wcs"])
    wcs["rotation_degrees_counterclockwise"] = angle / 3.0
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = spec.first_seed
    recipe["noise_correlation"] = {
        "major_fwhm_pixels": major,
        "minor_fwhm_pixels": minor,
        "position_angle_degrees": angle,
        "truncation_sigma": 4.0,
    }
    _replace_curve(record, spec.curve_sources)
    record["noise_realization_seeds"] = list(
        range(spec.first_seed + 1, spec.first_seed + spec.realizations)
    )
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    return DatasetRecord.model_validate(record)


def _manifest(
    template: DatasetRecord,
    spec: _PopulationSpec,
) -> DatasetManifest:
    """Build one four-geometry development or confirmation manifest."""
    return DatasetManifest(
        schema_version=3,
        manifest_id=f"phase-5-astrometry-{spec.label}",
        datasets=tuple(
            _dataset(
                template,
                _DatasetSpec(
                    role=spec.role,
                    label=spec.label,
                    variant=variant,
                    first_seed=first_seed,
                    realizations=spec.realizations,
                    curve_sources=curve,
                    beam=beam,
                ),
            )
            for variant, (first_seed, curve, beam) in enumerate(
                zip(spec.first_seeds, spec.curves, spec.beams, strict=True)
            )
        ),
    )


def _documents(
    template_path: Path,
    human_decision_path: Path,
    closed_decision_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build and validate both fresh manifests and the bound protocol."""
    template_manifest = DatasetManifest.model_validate_json(
        template_path.read_text(encoding="utf-8")
    )
    if len(template_manifest.datasets) != 1:
        raise ValueError("astrometry revision requires one Phase 5 template")
    template = template_manifest.datasets[0]
    development = _manifest(
        template,
        _PopulationSpec(
            role="development",
            label="development",
            first_seeds=_DEVELOPMENT_FIRST_SEEDS,
            realizations=_DEVELOPMENT_REALIZATIONS,
            curves=_DEVELOPMENT_CURVES,
            beams=_BEAMS[:4],
        ),
    )
    confirmation = _manifest(
        template,
        _PopulationSpec(
            role="regression",
            label="confirmation",
            first_seeds=_CONFIRMATION_FIRST_SEEDS,
            realizations=_CONFIRMATION_REALIZATIONS,
            curves=_CONFIRMATION_CURVES,
            beams=_BEAMS[4:],
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
        "contract_id": "phase-5-astrometry-revision-review",
        "status": "frozen-before-astrometry-development-results",
        "human_decision_sha256": _sha256(human_decision_path),
        "closed_decision_sha256": _sha256(closed_decision_path),
        "closed_confirmation_policy": (
            "no-tuning-rescoring-or-reconfirmation"
        ),
        "dataset_manifests": [
            {
                "role": "development",
                "manifest": (
                    "config/datasets/phase-5-astrometry-development.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(development_document)
                ).hexdigest(),
                "image_count": 40,
            },
            {
                "role": "regression",
                "manifest": (
                    "config/datasets/phase-5-astrometry-confirmation.json"
                ),
                "manifest_sha256": hashlib.sha256(
                    _json_bytes(confirmation_document)
                ).hexdigest(),
                "image_count": 400,
            },
        ],
        "estimator_candidates": [
            "direct-observable-pixel-centroid",
            "covariance-gated-model-assisted-centroid",
        ],
        "endpoint": {
            "target": "observable-valid-domain-flux-centroid",
            "observation_unit": "eligible-astronomical-truth-group",
            "independent_unit": "noise-seed-image",
            "statistics": ["median", "percentile-95"],
            "resampling": ("whole-image-cluster-bootstrap-retain-all-groups"),
            "bootstrap_resamples": 10000,
            "bootstrap_seed": 20260809,
            "confidence_level": 0.95,
            "absolute_gate_rule": (
                "point-estimate-with-one-sided-confidence-bound-reported"
            ),
            "maximum_median_position_beams": 0.1,
            "maximum_percentile_95_position_beams": 0.25,
            "per_image_risk_metric": "separate-report-only-maximum",
        },
        "uncertainty": {
            "covariance_shape": "two-by-two",
            "covariance_coordinates": ["pixel", "sky"],
            "pixel_covariance_method": (
                "delta-method-full-gaussian-beam-correlation"
            ),
            "sky_transform": "local-wcs-jacobian",
            "nonlinear_calibration": ("repeated-correlated-noise-injections"),
            "calibration_statistic": "mahalanobis-chi-square-two",
            "coverage_levels": [0.68, 0.95],
            "maximum_absolute_coverage_error": [0.1, 0.05],
            "require_positive_definite_fraction": 1.0,
            "coverage_strata": [
                "morphology",
                "signal-to-noise",
                "scale",
                "image-edge",
                "invalid-pixels",
                "truncation",
                "estimator-disposition",
            ],
        },
        "selection": {
            "selection_population": "fresh-development-only",
            "absolute_and_coverage_rule": (
                "every-endpoint-and-stratum-passes-no-compensation"
            ),
            "preference": (
                "prefer-direct-unless-model-materially-improves-tail"
            ),
            "minimum_model_p95_improvement_beams": 0.02,
            "maximum_model_unavailable_fraction": 0.01,
            "maximum_model_inadequate_fraction": 0.05,
            "confirmation_policy": (
                "freeze-selected-estimator-before-one-look-confirmation"
            ),
        },
        "external_position_mappings": [
            "pybdsf-source-moment-centroid-where-semantically-aligned",
            "aegean-component-centre-compact-gaussian-scope-only",
            "no-aegean-irregular-island-position-binding",
        ],
        "development_execution_authorized": True,
        "confirmation_execution_authorized": False,
        "step_two_c_p_execution_authorized": False,
        "step_three_authorized": False,
        "optimization_authorized": False,
        "qualification_opened": False,
    }
    protocol = PhaseFiveAstrometryRevisionReview.model_validate(
        protocol_document
    )
    return (
        development_document,
        confirmation_document,
        cast(dict[str, object], protocol.model_dump(mode="json")),
    )


def _parse_args() -> argparse.Namespace:
    """Parse paths while keeping all scientific choices fixed in code."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=root / "config/datasets/phase-5-regression.json",
    )
    parser.add_argument(
        "--human-decision",
        type=Path,
        default=(
            root / "config/contracts/phase-5-astrometry-human-decision.json"
        ),
    )
    parser.add_argument(
        "--closed-decision",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-decision.json",
    )
    parser.add_argument(
        "--development-output",
        type=Path,
        default=(root / "config/datasets/phase-5-astrometry-development.json"),
    )
    parser.add_argument(
        "--confirmation-output",
        type=Path,
        default=(
            root / "config/datasets/phase-5-astrometry-confirmation.json"
        ),
    )
    parser.add_argument(
        "--protocol-output",
        type=Path,
        default=(
            root / "config/contracts/phase-5-astrometry-revision-review.json"
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
        arguments.human_decision,
        arguments.closed_decision,
    )
    for path, document in zip(outputs, documents, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_json_bytes(document))


if __name__ == "__main__":
    main()
