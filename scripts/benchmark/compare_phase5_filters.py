# pyright: reportUnknownMemberType=false
"""Compare Phase 5 filter candidates on frozen development data only."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import os
import platform
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from statistics import median

import numpy as np

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    FilterFamily,
    PreparedScaleInputs,
    ScaleFilterBank,
    ScaleFilterBankResult,
    build_scale_filter_bank,
    evaluate_scale_filter_bank,
    prepare_scale_filter_inputs,
)
from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    dependency_inventory_sha256,
)
from hebog.validation.datasets import (
    DatasetRecord,
    DatasetRole,
    generate_synthetic_image,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.evidence import (
    EvidenceStatus,
    PhaseFiveFilterCandidateEvidence,
    PhaseFiveFilterSelectionEvidence,
    SoftwareIdentity,
    WorkloadClass,
    write_evidence,
)

_FAMILIES: tuple[FilterFamily, ...] = (
    "beam-aware-matched-filter",
    "undecimated-wavelet",
)
_SCALES = ((1, 1.0), (2, 2.0), (3, 4.0))
_TRUNCATION_SIGMA = 4.0
_MINIMUM_SUPPORT_FRACTION = 0.5
_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
_DEPENDENCIES = ("hebog", "numpy", "scipy")
_MINIMUM_REPETITIONS = 5
_MAXIMUM_UNIT_RESPONSE_ERROR = 0.02
_MAXIMUM_MASKED_RESPONSE_ERROR = 0.10
_MAXIMUM_EDGE_RESPONSE_ERROR = 0.10
_MAXIMUM_BACKGROUND_RESPONSE = 1e-12


@dataclass(frozen=True, slots=True)
class _DevelopmentInput:
    """One prepared development image and its governed recipe index."""

    prepared: PreparedScaleInputs
    recipe_index: int


def _parse_args() -> argparse.Namespace:
    """Parse the reproducible development-only comparison configuration."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=root / "config/datasets/phase-5-development.json",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repetitions", default=5, type=int)
    return parser.parse_args()


def _source_tree_sha256() -> str:
    """Hash all production Python used by the uncommitted comparison."""
    digest = hashlib.sha256()
    root = Path(__file__).parents[2]
    for path in sorted((root / "src" / "hebog").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _beam(dataset: DatasetRecord) -> BeamShapePixels:
    """Convert the governed dataset beam to algorithm pixel units."""
    return BeamShapePixels(
        major_fwhm_pixels=dataset.beam.major_fwhm_pixels,
        minor_fwhm_pixels=dataset.beam.minor_fwhm_pixels,
        position_angle_degrees=dataset.beam.position_angle_degrees,
    )


def _rms_plane(dataset: DatasetRecord, recipe_index: int) -> np.ndarray:
    """Materialize the exact affine RMS truth already supplied by Phase 2."""
    recipe = iter_dataset_recipes(dataset)[recipe_index]
    height, width = recipe.shape_yx
    gradient_x, gradient_y = recipe.noise_rms_fractional_gradient_xy
    x_normalized = (
        np.arange(width, dtype=np.float64) / max(width - 1, 1) - 0.5
    )[np.newaxis, :]
    y_normalized = (
        np.arange(height, dtype=np.float64) / max(height - 1, 1) - 0.5
    )[:, np.newaxis]
    scale = 1.0 + gradient_x * x_normalized + gradient_y * y_normalized
    return np.asarray(recipe.noise_rms * scale, dtype=np.float64)


def _prepare_development_inputs(
    dataset: DatasetRecord,
) -> tuple[_DevelopmentInput, ...]:
    """Generate development images and supply exact background/RMS products."""
    prepared: list[_DevelopmentInput] = []
    for recipe_index, recipe in enumerate(iter_dataset_recipes(dataset)):
        image = generate_synthetic_image(recipe)
        validity = np.isfinite(image)
        background = np.full(image.shape, recipe.background, dtype=np.float64)
        prepared.append(
            _DevelopmentInput(
                prepared=prepare_scale_filter_inputs(
                    image,
                    validity,
                    background,
                    _rms_plane(dataset, recipe_index),
                ),
                recipe_index=recipe_index,
            )
        )
    return tuple(prepared)


def _unit_flux_gaussian(
    beam: BeamShapePixels,
    shape_yx: tuple[int, int],
    *,
    centre_xy: tuple[float, float],
    scale_beams: float,
) -> np.ndarray:
    """Return one beam-aligned unit-integrated-flux analytic source."""
    y_grid, x_grid = np.indices(shape_yx, dtype=np.float64)
    x_offset = x_grid - centre_xy[0]
    y_offset = y_grid - centre_xy[1]
    angle = np.deg2rad(beam.position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    major_offset = cosine * x_offset + sine * y_offset
    minor_offset = -sine * x_offset + cosine * y_offset
    major_sigma = beam.major_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA
    minor_sigma = beam.minor_fwhm_pixels * scale_beams * _FWHM_TO_SIGMA
    return np.asarray(
        np.exp(
            -0.5
            * (
                np.square(major_offset / major_sigma)
                + np.square(minor_offset / minor_sigma)
            )
        )
        / scale_beams**2,
        dtype=np.float64,
    )


def _evaluate_image(
    prepared: PreparedScaleInputs,
    bank: ScaleFilterBank,
) -> ScaleFilterBankResult:
    """Run the exact one-tile candidate boundary used by every measurement."""
    return evaluate_scale_filter_bank(
        prepared,
        bank,
        minimum_support_fraction=_MINIMUM_SUPPORT_FRACTION,
    )


def _prepare_analytic(
    image: np.ndarray,
    *,
    valid: np.ndarray | None = None,
    background: np.ndarray | None = None,
) -> PreparedScaleInputs:
    """Prepare one analytic image with explicit Phase 2 products."""
    return prepare_scale_filter_inputs(
        image,
        np.ones(image.shape, dtype=np.bool_) if valid is None else valid,
        np.zeros(image.shape, dtype=np.float64)
        if background is None
        else background,
        np.full(image.shape, 0.01, dtype=np.float64),
    )


def _analytic_errors(
    bank: ScaleFilterBank,
) -> tuple[float, float, float, float]:
    """Measure normalization, mask, edge, and background response errors."""
    centre = (64.0, 64.0)
    unit_errors: list[float] = []
    for response_index, (_, scale_beams) in enumerate(_SCALES):
        image = _unit_flux_gaussian(
            bank.beam,
            (129, 129),
            centre_xy=centre,
            scale_beams=scale_beams,
        )
        response = _evaluate_image(
            _prepare_analytic(image),
            bank,
        ).responses[response_index]
        unit_errors.append(
            abs(float(response.response_jy_per_beam[64, 64]) - 1.0)
        )

    masked_image = _unit_flux_gaussian(
        bank.beam,
        (97, 97),
        centre_xy=(48.0, 48.0),
        scale_beams=2.0,
    )
    valid = np.ones(masked_image.shape, dtype=np.bool_)
    valid[:, :47] = False
    masked_image[~valid] = np.nan
    masked_response = _evaluate_image(
        _prepare_analytic(masked_image, valid=valid),
        bank,
    ).responses[1]
    masked_error = abs(
        float(masked_response.response_jy_per_beam[48, 48]) - 1.0
    )

    edge_image = _unit_flux_gaussian(
        bank.beam,
        (129, 129),
        centre_xy=(2.0, 64.0),
        scale_beams=4.0,
    )
    edge_response = _evaluate_image(
        _prepare_analytic(edge_image),
        bank,
    ).responses[2]
    edge_error = abs(float(edge_response.response_jy_per_beam[64, 2]) - 1.0)

    y_grid, x_grid = np.indices((65, 67), dtype=np.float64)
    background = 3.0 + 0.02 * x_grid - 0.03 * y_grid
    background_result = _evaluate_image(
        _prepare_analytic(background.copy(), background=background),
        bank,
    )
    background_error = max(
        float(
            np.max(
                np.abs(
                    response.response_jy_per_beam[
                        response.scientifically_valid
                    ]
                )
            )
        )
        for response in background_result.responses
    )
    return max(unit_errors), masked_error, edge_error, background_error


def _truth_group_fraction(
    dataset: DatasetRecord,
    prepared_inputs: tuple[_DevelopmentInput, ...],
    bank: ScaleFilterBank,
) -> float:
    """Return the fraction of governed truth-scale windows with a response."""
    response_count = 0
    finite_count = 0
    scale_indices = {
        item.scale_order: index for index, item in enumerate(bank.filters)
    }
    for development_input in prepared_inputs:
        result = _evaluate_image(development_input.prepared, bank)
        for group in dataset.multiscale_truth_groups:
            x_position, y_position = group.reference_position_xy
            for scale_order in group.governed_scale_orders:
                scale_index = scale_indices[scale_order]
                response = result.responses[scale_index]
                radius = ceil(
                    bank.beam.major_fwhm_pixels
                    * response.nominal_scale_beam_fwhm
                )
                y_centre = round(y_position)
                x_centre = round(x_position)
                y_start = max(0, y_centre - radius)
                y_stop = min(
                    response.response_jy_per_beam.shape[0],
                    y_centre + radius + 1,
                )
                x_start = max(0, x_centre - radius)
                x_stop = min(
                    response.response_jy_per_beam.shape[1],
                    x_centre + radius + 1,
                )
                window = response.response_jy_per_beam[
                    y_start:y_stop,
                    x_start:x_stop,
                ]
                response_count += 1
                finite_count += int(np.isfinite(window).any())
    return finite_count / response_count


def _measure_candidate(
    dataset: DatasetRecord,
    prepared_inputs: tuple[_DevelopmentInput, ...],
    bank: ScaleFilterBank,
    *,
    repetitions: int,
) -> PhaseFiveFilterCandidateEvidence:
    """Measure one warm candidate and apply the predeclared analytic gates."""
    _evaluate_image(prepared_inputs[0].prepared, bank)
    measured_wall_seconds: list[float] = []
    maximum_workspace_bytes = 0
    for _ in range(repetitions):
        gc.collect()
        started = time.perf_counter()
        for development_input in prepared_inputs:
            result = _evaluate_image(development_input.prepared, bank)
            maximum_workspace_bytes = max(
                maximum_workspace_bytes,
                result.maximum_workspace_bytes,
            )
        measured_wall_seconds.append(time.perf_counter() - started)

    unit_error, masked_error, edge_error, background_error = _analytic_errors(
        bank
    )
    finite_truth_fraction = _truth_group_fraction(
        dataset, prepared_inputs, bank
    )
    scientifically_adequate = (
        unit_error <= _MAXIMUM_UNIT_RESPONSE_ERROR
        and masked_error <= _MAXIMUM_MASKED_RESPONSE_ERROR
        and edge_error <= _MAXIMUM_EDGE_RESPONSE_ERROR
        and background_error <= _MAXIMUM_BACKGROUND_RESPONSE
        and finite_truth_fraction == 1.0
    )
    return PhaseFiveFilterCandidateEvidence(
        family=bank.family,
        measured_wall_seconds=tuple(measured_wall_seconds),
        median_wall_seconds=float(median(measured_wall_seconds)),
        maximum_workspace_bytes=maximum_workspace_bytes,
        convolution_count_per_image=bank.convolution_count_per_evaluation,
        temporary_plane_count=bank.temporary_plane_count,
        maximum_halo_pixels=bank.maximum_halo_pixels,
        maximum_unit_flux_response_fractional_error=unit_error,
        maximum_masked_response_fractional_error=masked_error,
        maximum_edge_response_fractional_error=edge_error,
        maximum_absolute_background_response_jy_per_beam=background_error,
        finite_truth_group_response_fraction=finite_truth_fraction,
        minimum_correlated_noise_gain=min(
            item.correlated_noise_gain for item in bank.filters
        ),
        maximum_correlated_noise_gain=max(
            item.correlated_noise_gain for item in bank.filters
        ),
        scientifically_adequate=scientifically_adequate,
    )


def _environment() -> dict[str, object]:
    """Return the controlled local environment used by the comparison."""
    return {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "dependencies": {
            name: importlib.metadata.version(name) for name in _DEPENDENCIES
        },
    }


def main() -> None:
    """Run both candidates and write one reviewed development decision."""
    args = _parse_args()
    if args.repetitions < _MINIMUM_REPETITIONS:
        raise ValueError("filter selection requires at least five repetitions")
    manifest = load_dataset_manifest(args.manifest)
    if len(manifest.datasets) != 1:
        raise ValueError(
            "filter selection requires exactly one dataset record"
        )
    dataset = manifest.datasets[0]
    if dataset.role is not DatasetRole.DEVELOPMENT:
        raise ValueError("filter selection may use development data only")

    beam = _beam(dataset)
    prepared_inputs = _prepare_development_inputs(dataset)
    banks = tuple(
        build_scale_filter_bank(
            beam,
            family=family,
            scales=_SCALES,
            truncation_sigma=_TRUNCATION_SIGMA,
            noise_correlation=beam,
        )
        for family in _FAMILIES
    )
    candidates = tuple(
        _measure_candidate(
            dataset,
            prepared_inputs,
            bank,
            repetitions=args.repetitions,
        )
        for bank in banks
    )
    adequate = tuple(
        item for item in candidates if item.scientifically_adequate
    )
    if not adequate:
        raise ValueError("neither filter candidate passed the analytic gates")
    selected = min(
        adequate,
        key=lambda item: (
            item.convolution_count_per_image,
            item.temporary_plane_count,
            item.maximum_halo_pixels,
            item.median_wall_seconds,
        ),
    )
    dataset_identity = campaign_dataset_identity(dataset).model_copy(
        update={"workload_class": WorkloadClass.DENSE_EXTENDED}
    )
    environment = _environment()
    evidence = PhaseFiveFilterSelectionEvidence(
        schema_version=1,
        evidence_type="phase-five-filter-selection",
        run_id="phase-five-filter-selection-development",
        captured_at=datetime.now(UTC),
        status=EvidenceStatus.REVIEWED,
        dataset=dataset_identity,
        configuration_sha256=canonical_sha256(
            {
                "manifest": manifest.model_dump(mode="json"),
                "families": _FAMILIES,
                "scales": _SCALES,
                "truncation_sigma": _TRUNCATION_SIGMA,
                "minimum_support_fraction": _MINIMUM_SUPPORT_FRACTION,
                "repetitions": args.repetitions,
            }
        ),
        subject=SoftwareIdentity(
            name="hebog",
            source_tree_sha256=_source_tree_sha256(),
            dependency_inventory_sha256=dependency_inventory_sha256(),
        ),
        environment_sha256=canonical_sha256(environment),
        candidates=candidates,
        selected_family=selected.family,
        decision_rule=(
            "all-analytic-gates-then-lowest-maintained-bounded-cost"
        ),
        qualification_opened=False,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)
    print(args.output)
    print(f"selected={evidence.selected_family}")
    for candidate in evidence.candidates:
        print(
            f"{candidate.family}: median={candidate.median_wall_seconds:.6f}s "
            f"convolutions={candidate.convolution_count_per_image} "
            f"halo={candidate.maximum_halo_pixels} "
            f"workspace={candidate.maximum_workspace_bytes}"
        )


if __name__ == "__main__":
    main()
