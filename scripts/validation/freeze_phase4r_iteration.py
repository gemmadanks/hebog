"""Freeze a disjoint Phase 4R noise-realization matrix from a template."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

from hebog.validation.datasets import (
    DatasetManifest,
    SyntheticRecipe,
    recipe_sha256,
)


def _parse_args() -> argparse.Namespace:
    """Parse one immutable derived-matrix request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-id")
    parser.add_argument("--identifier", required=True)
    parser.add_argument(
        "--role",
        required=True,
        choices=("development", "regression", "qualification"),
    )
    parser.add_argument("--first-seed", required=True, type=int)
    parser.add_argument("--realizations", required=True, type=int)
    parser.add_argument("--provenance", required=True)
    reflection = parser.add_mutually_exclusive_group()
    reflection.add_argument("--reflect-x", action="store_true")
    reflection.add_argument("--reflect-y", action="store_true")
    parser.add_argument(
        "--reference-sky-degrees",
        nargs=2,
        type=float,
        metavar=("RA", "DEC"),
    )
    parser.add_argument(
        "--pixel-scale-degrees-xy",
        nargs=2,
        type=float,
        metavar=("X", "Y"),
    )
    parser.add_argument("--wcs-rotation-degrees", type=float)
    parser.add_argument("--background", type=float)
    return parser.parse_args()


def _reflect_x(record: dict[str, object]) -> None:
    """Mirror pixel-bound truth while preserving every source covariance."""
    recipe = cast(dict[str, object], record["recipe"])
    _, width = cast(list[int], recipe["shape_yx"])
    sources = cast(list[dict[str, object]], recipe["sources"])
    for source in sources:
        source["x_pixel"] = width - 1 - float(source["x_pixel"])
        source["rotation_degrees_counterclockwise_from_x"] = (
            180.0 - float(source["rotation_degrees_counterclockwise_from_x"])
        ) % 180.0
    gradient_x, gradient_y = cast(
        list[float], recipe["noise_rms_fractional_gradient_xy"]
    )
    recipe["noise_rms_fractional_gradient_xy"] = [
        -gradient_x,
        gradient_y,
    ]
    rectangles = cast(list[dict[str, object]], recipe["invalid_rectangles"])
    for rectangle in rectangles:
        old_start = int(rectangle["x_start"])
        old_stop = int(rectangle["x_stop"])
        rectangle["x_start"] = width - old_stop
        rectangle["x_stop"] = width - old_start
    beam = cast(dict[str, object], record["beam"])
    reflected_angle = (180.0 - float(beam["position_angle_degrees"])) % 180.0
    beam["position_angle_degrees"] = reflected_angle
    noise_correlation = cast(dict[str, object], recipe["noise_correlation"])
    noise_correlation["position_angle_degrees"] = reflected_angle
    groups = cast(list[dict[str, object]], record["association_truth_groups"])
    for group in groups:
        position = cast(list[float], group["reference_position_xy"])
        position[0] = width - 1 - position[0]


def _reflect_y(record: dict[str, object]) -> None:
    """Mirror vertical truth while preserving every source covariance."""
    recipe = cast(dict[str, object], record["recipe"])
    height, _ = cast(list[int], recipe["shape_yx"])
    sources = cast(list[dict[str, object]], recipe["sources"])
    for source in sources:
        source["y_pixel"] = height - 1 - float(source["y_pixel"])
        source["rotation_degrees_counterclockwise_from_x"] = (
            180.0 - float(source["rotation_degrees_counterclockwise_from_x"])
        ) % 180.0
    gradient_x, gradient_y = cast(
        list[float], recipe["noise_rms_fractional_gradient_xy"]
    )
    recipe["noise_rms_fractional_gradient_xy"] = [
        gradient_x,
        -gradient_y,
    ]
    rectangles = cast(list[dict[str, object]], recipe["invalid_rectangles"])
    for rectangle in rectangles:
        old_start = int(rectangle["y_start"])
        old_stop = int(rectangle["y_stop"])
        rectangle["y_start"] = height - old_stop
        rectangle["y_stop"] = height - old_start
    beam = cast(dict[str, object], record["beam"])
    reflected_angle = (180.0 - float(beam["position_angle_degrees"])) % 180.0
    beam["position_angle_degrees"] = reflected_angle
    noise_correlation = cast(dict[str, object], recipe["noise_correlation"])
    noise_correlation["position_angle_degrees"] = reflected_angle
    groups = cast(list[dict[str, object]], record["association_truth_groups"])
    for group in groups:
        position = cast(list[float], group["reference_position_xy"])
        position[1] = height - 1 - position[1]


def _qualification_overrides(
    record: dict[str, object], arguments: argparse.Namespace
) -> None:
    """Apply reviewed qualification-only sky and noise-field choices."""
    if arguments.role != "qualification":
        return
    reflections = sum(
        bool(getattr(arguments, name, False))
        for name in ("reflect_x", "reflect_y")
    )
    if reflections != 1:
        raise ValueError(
            "qualification requires one disjoint pixel reflection"
        )
    required = {
        "reference_sky_degrees": arguments.reference_sky_degrees,
        "pixel_scale_degrees_xy": arguments.pixel_scale_degrees_xy,
        "wcs_rotation_degrees": arguments.wcs_rotation_degrees,
        "background": arguments.background,
    }
    missing = tuple(name for name, value in required.items() if value is None)
    if missing:
        raise ValueError(
            "qualification requires explicit field overrides: "
            + ", ".join(missing)
        )
    wcs = cast(dict[str, object], record["wcs"])
    wcs["reference_sky_degrees"] = list(arguments.reference_sky_degrees)
    wcs["pixel_scale_degrees_xy"] = list(arguments.pixel_scale_degrees_xy)
    wcs["rotation_degrees_counterclockwise"] = arguments.wcs_rotation_degrees
    recipe = cast(dict[str, object], record["recipe"])
    recipe["background"] = arguments.background
    statistics = cast(dict[str, object], record["expected_statistics"])
    statistics["background_jy_per_beam"] = arguments.background


def _derived_document(arguments: argparse.Namespace) -> dict[str, object]:
    """Return a validated single-record manifest with disjoint seeds."""
    if arguments.realizations < 1:
        raise ValueError("realizations must be positive")
    payload = cast(
        dict[str, object],
        json.loads(arguments.template.read_text(encoding="utf-8")),
    )
    datasets = cast(list[dict[str, object]], payload["datasets"])
    if len(datasets) != 1:
        raise ValueError("template must contain exactly one dataset")
    document = deepcopy(payload)
    if arguments.role == "qualification":
        document["manifest_id"] = getattr(arguments, "manifest_id", None) or (
            "phase-4r-qualification"
        )
    record = cast(list[dict[str, object]], document["datasets"])[0]
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = arguments.first_seed
    record["identifier"] = arguments.identifier
    record["role"] = arguments.role
    purpose = {
        "development": (
            "Phase 4R recovery-iteration model-selection development."
        ),
        "regression": "Phase 4R recovery-iteration confirmation only.",
        "qualification": "Phase 4R powered one-look qualification only.",
    }
    record["purpose"] = purpose[arguments.role]
    record["provenance"] = arguments.provenance
    record["noise_realization_seeds"] = list(
        range(
            arguments.first_seed + 1,
            arguments.first_seed + arguments.realizations,
        )
    )
    if getattr(arguments, "reflect_x", False):
        _reflect_x(record)
    elif getattr(arguments, "reflect_y", False):
        _reflect_y(record)
    _qualification_overrides(record, arguments)
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    validated = DatasetManifest.model_validate(document)
    return cast(dict[str, object], validated.model_dump(mode="json"))


def main() -> None:
    """Write one canonical manifest without replacing prior evidence."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite frozen manifest: {arguments.output}"
        )
    document = _derived_document(arguments)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
