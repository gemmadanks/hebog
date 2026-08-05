"""Freeze the reviewed Phase 4S compact-source qualification population."""

from __future__ import annotations

import argparse
import json
from math import cos, pi, radians, sin
from pathlib import Path

import numpy as np
import numpy.typing as npt

from hebog.validation.datasets import (
    DatasetManifest,
    SyntheticRecipe,
    recipe_sha256,
)

_FIRST_SEED = 2026300001
_REALIZATION_COUNT = 800
_NOISE_RMS = 0.0002
_FWHM_TO_SIGMA = 1.0 / np.sqrt(8.0 * np.log(2.0))
_BEAM_MAJOR_FWHM = 5.2
_BEAM_MINOR_FWHM = 3.4
_BEAM_ANGLE_DEGREES = 67.0

_INTERIOR_POSITIONS = tuple(
    (x, y)
    for y in (72.0, 194.0, 318.0, 440.0)
    for x in (68.0, 143.0, 218.0, 293.0, 368.0, 443.0)
)
_EDGE_POSITIONS = (
    (1.4, 256.0),
    (510.0, 256.0),
    (256.0, 1.2),
    (256.0, 510.0),
    (1.4, 1.4),
    (510.0, 1.4),
    (1.4, 510.0),
    (510.0, 510.0),
)
_SNR_VALUES = (10.0, 15.0, 25.0, 50.0)
_ANGLE_OFFSETS_DEGREES = (0.0, 17.0, 39.0, 63.0, 91.0, 121.0, 147.0)


def _ellipse_covariance(
    major_fwhm: float,
    minor_fwhm: float,
    angle_degrees: float,
) -> npt.NDArray[np.float64]:
    """Return one Gaussian covariance in image x/y pixel coordinates."""
    angle = radians(angle_degrees)
    rotation = np.asarray(
        ((cos(angle), -sin(angle)), (sin(angle), cos(angle))),
        dtype=np.float64,
    )
    variances = np.diag(
        np.square(
            np.asarray((major_fwhm, minor_fwhm), dtype=np.float64)
            * _FWHM_TO_SIGMA
        )
    )
    return rotation @ variances @ rotation.T


def _observed_shape(
    intrinsic_major_beams: float,
    intrinsic_minor_beams: float,
    angle_offset_degrees: float,
) -> tuple[float, float, float]:
    """Convolve one intrinsic ellipse with the fixed restoring beam."""
    beam = _ellipse_covariance(
        _BEAM_MAJOR_FWHM,
        _BEAM_MINOR_FWHM,
        _BEAM_ANGLE_DEGREES,
    )
    intrinsic = _ellipse_covariance(
        intrinsic_major_beams * _BEAM_MAJOR_FWHM,
        intrinsic_minor_beams * _BEAM_MINOR_FWHM,
        _BEAM_ANGLE_DEGREES + angle_offset_degrees,
    )
    eigenvalues, eigenvectors = np.linalg.eigh(beam + intrinsic)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major = float(np.sqrt(eigenvalues[major_index]))
    minor = float(np.sqrt(eigenvalues[minor_index]))
    vector = eigenvectors[:, major_index]
    angle = float(np.degrees(np.arctan2(vector[1], vector[0])) % 180.0)
    return major, minor, angle


def _single_source_classes() -> tuple[str, ...]:
    """Cross SNR with point, marginal, and clear-resolved truth."""
    return (
        *("unresolved",) * 2,
        *("marginal",) * 6,
        *("unresolved",) * 2,
        *("marginal",) * 6,
        *("unresolved",) * 2,
        *("marginal",) * 2,
        *("clear",) * 4,
        *("unresolved",) * 2,
        *("marginal",) * 2,
        *("clear",) * 4,
    )


def _source_positions() -> tuple[tuple[float, float], ...]:
    """Place two members of every SNR block on distinct edge topologies."""
    positions: list[tuple[float, float]] = []
    for block in range(4):
        positions.extend(_INTERIOR_POSITIONS[block * 6 : (block + 1) * 6])
        positions.extend(_EDGE_POSITIONS[block * 2 : (block + 1) * 2])
    return tuple(positions)


def _sources() -> tuple[list[dict[str, float]], dict[str, list[int]]]:
    """Build continuous compact truth without generating a noise image."""
    classes = _single_source_classes()
    positions = _source_positions()
    indices_by_class = {
        name: [] for name in ("unresolved", "marginal", "clear")
    }
    marginal_scales = np.linspace(0.15, 1.25, classes.count("marginal"))
    clear_major_scales = np.linspace(1.7, 2.4, classes.count("clear"))
    clear_minor_scales = np.linspace(1.2, 1.7, classes.count("clear"))
    marginal_index = 0
    clear_index = 0
    sources: list[dict[str, float]] = []
    for index, ((x_pixel, y_pixel), shape_class) in enumerate(
        zip(positions, classes, strict=True)
    ):
        signal_to_noise = _SNR_VALUES[index // 8]
        if shape_class == "unresolved":
            major, minor, angle = _observed_shape(0.0, 0.0, 0.0)
        elif shape_class == "marginal":
            scale = float(marginal_scales[marginal_index])
            minor_scale = scale * (0.15 + 0.65 * ((marginal_index % 5) / 4))
            major, minor, angle = _observed_shape(
                scale,
                minor_scale,
                _ANGLE_OFFSETS_DEGREES[
                    marginal_index % len(_ANGLE_OFFSETS_DEGREES)
                ],
            )
            marginal_index += 1
        else:
            major, minor, angle = _observed_shape(
                float(clear_major_scales[clear_index]),
                float(clear_minor_scales[clear_index]),
                _ANGLE_OFFSETS_DEGREES[
                    (clear_index + 2) % len(_ANGLE_OFFSETS_DEGREES)
                ],
            )
            clear_index += 1
        indices_by_class[shape_class].append(index)
        sources.append(
            {
                "x_pixel": x_pixel,
                "y_pixel": y_pixel,
                "peak_flux_jy_per_beam": signal_to_noise * _NOISE_RMS,
                "major_sigma_pixels": major,
                "minor_sigma_pixels": minor,
                "rotation_degrees_counterclockwise_from_x": angle,
            }
        )

    blend_shape = _observed_shape(0.35, 0.15, 31.0)
    for x_pixel, y_pixel, peak in (
        (254.0, 258.0, 15.0 * _NOISE_RMS),
        (257.0, 255.0, 12.0 * _NOISE_RMS),
    ):
        sources.append(
            {
                "x_pixel": x_pixel,
                "y_pixel": y_pixel,
                "peak_flux_jy_per_beam": peak,
                "major_sigma_pixels": blend_shape[0],
                "minor_sigma_pixels": blend_shape[1],
                "rotation_degrees_counterclockwise_from_x": blend_shape[2],
            }
        )
    return sources, indices_by_class


def _integrated_brightness(source: dict[str, float]) -> float:
    """Return the analytic integral of one injected Gaussian."""
    return (
        2.0
        * pi
        * source["peak_flux_jy_per_beam"]
        * source["major_sigma_pixels"]
        * source["minor_sigma_pixels"]
    )


def _truth_groups(
    sources: list[dict[str, float]],
) -> list[dict[str, object]]:
    """Declare 32 individual sources and one unresolved association."""
    groups: list[dict[str, object]] = []
    for index, source in enumerate(sources[:32]):
        groups.append(
            {
                "identifier": f"source-{index + 1:05d}",
                "source_indices": [index],
                "resolution_class": "individually-resolvable",
                "reference_position_xy": [
                    source["x_pixel"],
                    source["y_pixel"],
                ],
                "reference_integrated_brightness_jy_pixels_per_beam": (
                    _integrated_brightness(source)
                ),
            }
        )
    blend_integrals = [
        _integrated_brightness(source) for source in sources[32:]
    ]
    total = sum(blend_integrals)
    groups.append(
        {
            "identifier": "blend-00001",
            "source_indices": [32, 33],
            "resolution_class": "unresolved-blend",
            "reference_position_xy": [
                sum(
                    source[axis] * integrated
                    for source, integrated in zip(
                        sources[32:], blend_integrals, strict=True
                    )
                )
                / total
                for axis in ("x_pixel", "y_pixel")
            ],
            "reference_integrated_brightness_jy_pixels_per_beam": total,
        }
    )
    return groups


def _document() -> dict[str, object]:
    """Return the exact reviewed manifest without materializing image data."""
    sources, indices_by_class = _sources()
    recipe_document: dict[str, object] = {
        "generator": "hebog.synthetic.gaussian-noise",
        "generator_version": 3,
        "seed": _FIRST_SEED,
        "shape_yx": [512, 512],
        "background": -0.00023,
        "noise_rms": _NOISE_RMS,
        "sources": sources,
        "noise_rms_fractional_gradient_xy": [-0.12, 0.19],
        "invalid_rectangles": [
            {"y_start": 112, "y_stop": 126, "x_start": 246, "x_stop": 266}
        ],
        "noise_correlation": {
            "major_fwhm_pixels": _BEAM_MAJOR_FWHM,
            "minor_fwhm_pixels": _BEAM_MINOR_FWHM,
            "position_angle_degrees": _BEAM_ANGLE_DEGREES,
            "truncation_sigma": 4.0,
        },
    }
    recipe = SyntheticRecipe.model_validate(recipe_document)
    invalid_pixels = 14 * 20
    dataset: dict[str, object] = {
        "identifier": "phase4s-compact-qualification-512",
        "role": "qualification",
        "purpose": (
            "One frozen 800-image compact, single-scale Phase 4S paired "
            "qualification of Hebog against released PyBDSF and pinned master."
        ),
        "provenance": (
            "Frozen ungenerated and unopened on 2026-08-05 after the "
            "project-owner-authorized AI-conducted expert review and before "
            "any implementation output. Seeds, truth, WCS, beam, correlated "
            "noise, background, invalid region, strata, and one-look rule are "
            "immutable. No controlled real residual/noise injection was "
            "available; this recorded limitation prevents a real-data claim."
        ),
        "redistribution": "generated-locally",
        "beam": {
            "major_fwhm_pixels": _BEAM_MAJOR_FWHM,
            "minor_fwhm_pixels": _BEAM_MINOR_FWHM,
            "position_angle_degrees": _BEAM_ANGLE_DEGREES,
        },
        "wcs": {
            "frame": "icrs",
            "reference_pixel_xy": [255.5, 255.5],
            "reference_sky_degrees": [214.7, -47.3],
            "pixel_scale_degrees_xy": [-0.00021, 0.00031],
            "rotation_degrees_counterclockwise": 28.0,
        },
        "expected_statistics": {
            "background_jy_per_beam": -0.00023,
            "noise_rms_jy_per_beam": _NOISE_RMS,
            "finite_fraction": 1.0 - invalid_pixels / (512 * 512),
        },
        "recipe": recipe.model_dump(mode="json"),
        "recipe_sha256": recipe_sha256(recipe),
        "noise_realization_seeds": list(
            range(_FIRST_SEED + 1, _FIRST_SEED + _REALIZATION_COUNT)
        ),
        "validation_strata": [
            {
                "identifier": f"snr-{int(signal_to_noise)}",
                "source_indices": list(range(block * 8, (block + 1) * 8)),
            }
            for block, signal_to_noise in enumerate(_SNR_VALUES)
        ]
        + [
            {
                "identifier": "edge",
                "source_indices": [6, 7, 14, 15, 22, 23, 30, 31],
            }
        ],
        "classification_strata": [
            {
                "identifier": "shape-unresolved",
                "source_indices": indices_by_class["unresolved"],
            },
            {
                "identifier": "shape-clear-resolved",
                "source_indices": indices_by_class["clear"],
            },
            {
                "identifier": "shape-marginal-resolved",
                "source_indices": indices_by_class["marginal"],
            },
        ],
        "association_truth_groups": _truth_groups(sources),
        "association_group_strata": [
            {
                "identifier": "unresolved-blend",
                "group_identifiers": ["blend-00001"],
            }
        ],
    }
    manifest = DatasetManifest.model_validate(
        {
            "schema_version": 2,
            "manifest_id": "phase-4s-qualification",
            "datasets": [dataset],
        }
    )
    return manifest.model_dump(mode="json")


def _parse_args() -> argparse.Namespace:
    """Parse the one permitted frozen-manifest output."""
    parser = argparse.ArgumentParser(description=__doc__)
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
        json.dumps(_document(), allow_nan=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
