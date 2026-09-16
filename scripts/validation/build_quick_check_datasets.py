"""Build the generated cases of the quick science check.

Writes ``config/datasets/quick-science-check.json``, a development-role
dataset manifest. The cases are small, deterministic and seed-disjoint from
earlier manifests. Noise is beam-correlated, as in restored radio images,
except in one case that tracks the effect of uncorrelated noise. Each case
exercises one behaviour the plan requires every change to keep: compact
sources across signal-to-noise, close blends, extended and elongated
emission, edges and corners of a non-square image, negative background,
invalid pixels, varying noise, a dense field and empty or all-invalid input.

Run ``uv run python scripts/validation/build_quick_check_datasets.py`` and
commit the manifest. The quick science check reads only the manifest.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from hebog.validation.datasets import (
    DatasetManifest,
    SyntheticRecipe,
    recipe_sha256,
)

_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT = _ROOT / "config/datasets/quick-science-check.json"
_SEED_BASE = 2026091600
_NOISE_RMS = 1e-4
_BEAM_MAJOR_FWHM_PIXELS = 5.0
_BEAM_MINOR_FWHM_PIXELS = 4.0
_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))
_POINT_MAJOR_SIGMA = _BEAM_MAJOR_FWHM_PIXELS / _FWHM_PER_SIGMA
_POINT_MINOR_SIGMA = _BEAM_MINOR_FWHM_PIXELS / _FWHM_PER_SIGMA
_PIXEL_SCALE_DEGREES = 1.5 / 3600.0
_BEAM_CORRELATION = {
    "major_fwhm_pixels": _BEAM_MAJOR_FWHM_PIXELS,
    "minor_fwhm_pixels": _BEAM_MINOR_FWHM_PIXELS,
    "position_angle_degrees": 0.0,
    "truncation_sigma": 4.0,
}


def _point(x: float, y: float, snr: float) -> dict[str, float]:
    """Return one beam-shaped source at a signal-to-noise ratio."""
    return {
        "x_pixel": x,
        "y_pixel": y,
        "peak_flux_jy_per_beam": snr * _NOISE_RMS,
        "major_sigma_pixels": _POINT_MAJOR_SIGMA,
        "minor_sigma_pixels": _POINT_MINOR_SIGMA,
        "rotation_degrees_counterclockwise_from_x": 0.0,
    }


def _ellipse(  # noqa: PLR0913, PLR0917
    x: float,
    y: float,
    snr: float,
    major_sigma: float,
    minor_sigma: float,
    rotation: float,
) -> dict[str, float]:
    """Return one resolved elliptical Gaussian source."""
    return {
        "x_pixel": x,
        "y_pixel": y,
        "peak_flux_jy_per_beam": snr * _NOISE_RMS,
        "major_sigma_pixels": major_sigma,
        "minor_sigma_pixels": minor_sigma,
        "rotation_degrees_counterclockwise_from_x": rotation,
    }


def _dense_field(size: int, count: int, seed: int) -> list[dict[str, float]]:
    """Scatter compact sources with SNR 5 to 50 on a jittered grid."""
    generator = np.random.default_rng(seed)
    side = int(np.ceil(np.sqrt(count)))
    spacing = (size - 40) / side
    sources: list[dict[str, float]] = []
    for index in range(count):
        row, column = divmod(index, side)
        x = (
            20
            + spacing * (column + 0.5)
            + generator.uniform(-0.3, 0.3) * spacing
        )
        y = 20 + spacing * (row + 0.5) + generator.uniform(-0.3, 0.3) * spacing
        log_snr = float(generator.uniform(math.log(5.0), math.log(50.0)))
        snr = float(np.exp(log_snr))
        sources.append(_point(round(x, 3), round(y, 3), round(snr, 3)))
    return sources


def _cases() -> list[dict[str, Any]]:
    """Return the ordered case definitions before provenance is added."""
    blend_offsets = (1.0, 1.5, 2.5)
    return [
        {
            "identifier": "compact-snr-ladder",
            "purpose": (
                "Isolated beam-shaped sources at SNR 5, 7, 10, 20, 50 and 100."
            ),
            "shape_yx": (512, 512),
            "sources": [
                _point(96.0 + 64.0 * index, 128.0 + 48.0 * (index % 2), snr)
                for index, snr in enumerate(
                    (5.0, 7.0, 10.0, 20.0, 50.0, 100.0)
                )
            ],
        },
        {
            "identifier": "close-blends",
            "purpose": (
                "Equal-brightness SNR 30 pairs separated by 1, 1.5 and 2.5 "
                "beam major axes."
            ),
            "shape_yx": (512, 512),
            "sources": [
                source
                for index, offset in enumerate(blend_offsets)
                for source in (
                    _point(128.0 + 128.0 * index, 256.0, 30.0),
                    _point(
                        128.0
                        + 128.0 * index
                        + offset * _BEAM_MAJOR_FWHM_PIXELS,
                        256.0,
                        30.0,
                    ),
                )
            ],
        },
        {
            "identifier": "extended-gaussians",
            "purpose": (
                "Resolved sources three and six beams across, including an "
                "elongated rotated source."
            ),
            "shape_yx": (512, 512),
            "sources": [
                _ellipse(128.0, 128.0, 40.0, 6.4, 5.1, 0.0),
                _ellipse(360.0, 150.0, 30.0, 12.7, 10.2, 30.0),
                _ellipse(256.0, 380.0, 25.0, 14.0, 3.0, 120.0),
            ],
        },
        {
            "identifier": "filament-and-ring",
            "purpose": (
                "A chain of overlapping elongated components and a ring of "
                "eight compact components."
            ),
            "shape_yx": (512, 512),
            "sources": [
                *(
                    _ellipse(
                        80.0 + 18.0 * index,
                        120.0 + 9.0 * index,
                        15.0,
                        5.0,
                        2.0,
                        26.6,
                    )
                    for index in range(8)
                ),
                *(
                    _point(
                        round(360.0 + 40.0 * float(np.cos(angle)), 3),
                        round(360.0 + 40.0 * float(np.sin(angle)), 3),
                        20.0,
                    )
                    for angle in np.linspace(
                        0.0, 2.0 * np.pi, 8, endpoint=False
                    )
                ),
            ],
        },
        {
            "identifier": "edges-and-corners",
            "purpose": (
                "Sources on every edge and corner of a non-square image, plus "
                "one central source."
            ),
            "shape_yx": (384, 512),
            "sources": [
                _point(1.0, 1.0, 40.0),
                _point(510.0, 1.0, 40.0),
                _point(1.0, 382.0, 40.0),
                _point(510.0, 382.0, 40.0),
                _point(256.0, 0.5, 40.0),
                _point(0.5, 192.0, 40.0),
                _point(256.0, 192.0, 40.0),
            ],
        },
        {
            "identifier": "negative-background",
            "purpose": (
                "A constant negative background of five times the noise with "
                "compact sources."
            ),
            "shape_yx": (256, 256),
            "background": -5.0 * _NOISE_RMS,
            "sources": [_point(64.0, 64.0, 15.0), _point(190.0, 170.0, 40.0)],
        },
        {
            "identifier": "invalid-pixels",
            "purpose": (
                "NaN blocks, including one that crosses a source, beside valid"
                " sources."
            ),
            "shape_yx": (512, 512),
            "sources": [
                _point(120.0, 120.0, 30.0),
                _point(300.0, 256.0, 30.0),
                _point(420.0, 420.0, 20.0),
            ],
            "invalid_rectangles": [
                {"y_start": 250, "y_stop": 262, "x_start": 302, "x_stop": 330},
                {"y_start": 0, "y_stop": 64, "x_start": 448, "x_stop": 512},
            ],
        },
        {
            "identifier": "varying-noise",
            "purpose": (
                "A noise level that changes by 80 percent across the image, "
                "with an SNR ladder."
            ),
            "shape_yx": (512, 512),
            "gradient": (0.8, 0.0),
            "sources": [
                _point(64.0 + 96.0 * index, 256.0, snr)
                for index, snr in enumerate((8.0, 12.0, 20.0, 12.0, 8.0))
            ],
        },
        {
            "identifier": "white-noise-snr-ladder",
            "purpose": (
                "The SNR ladder with pixel-independent noise. Restored radio "
                "images have beam-correlated noise; this case tracks the "
                "component fits' known sensitivity to uncorrelated noise."
            ),
            "shape_yx": (512, 512),
            "white_noise": True,
            "sources": [
                _point(96.0 + 64.0 * index, 128.0 + 48.0 * (index % 2), snr)
                for index, snr in enumerate(
                    (5.0, 7.0, 10.0, 20.0, 50.0, 100.0)
                )
            ],
        },
        {
            "identifier": "dense-field",
            "purpose": (
                "Sixty compact sources with SNR 5 to 50 on a jittered grid."
            ),
            "shape_yx": (1024, 1024),
            "sources": _dense_field(1024, 60, _SEED_BASE + 99),
        },
        {
            "identifier": "empty-noise",
            "purpose": "Noise only; a valid result has no sources.",
            "shape_yx": (256, 256),
            "sources": [],
        },
        {
            "identifier": "all-invalid",
            "purpose": (
                "Every pixel is NaN; the result must be an explicit "
                "unavailable RMS and empty catalogue."
            ),
            "shape_yx": (128, 128),
            "sources": [],
            "invalid_rectangles": [
                {"y_start": 0, "y_stop": 128, "x_start": 0, "x_stop": 128}
            ],
        },
    ]


def build_manifest() -> dict[str, Any]:
    """Return the validated manifest document."""
    datasets: list[dict[str, Any]] = []
    for index, case in enumerate(_cases(), start=1):
        height, width = case["shape_yx"]
        invalid = case.get("invalid_rectangles", [])
        white_noise = bool(case.get("white_noise", False))
        version = 2 if white_noise else 3
        recipe_document: dict[str, Any] = {
            "generator": "hebog.synthetic.gaussian-noise",
            "generator_version": version,
            "seed": _SEED_BASE + index,
            "shape_yx": [height, width],
            "background": case.get("background", 0.0),
            "noise_rms": _NOISE_RMS,
            "sources": case["sources"],
            "noise_rms_fractional_gradient_xy": list(
                case.get("gradient", (0.0, 0.0))
            ),
            "invalid_rectangles": invalid,
        }
        if not white_noise:
            recipe_document["noise_correlation"] = _BEAM_CORRELATION
        recipe = SyntheticRecipe.model_validate(recipe_document)
        invalid_pixels = sum(
            (item["y_stop"] - item["y_start"])
            * (item["x_stop"] - item["x_start"])
            for item in invalid
        )
        datasets.append(
            {
                "identifier": f"quick-{case['identifier']}",
                "role": "development",
                "purpose": case["purpose"],
                "provenance": (
                    "Generated by scripts/validation/"
                    "build_quick_check_datasets.py for the quick science "
                    "check; seed-disjoint from earlier manifests."
                ),
                "redistribution": "generated-locally",
                "beam": {
                    "major_fwhm_pixels": _BEAM_MAJOR_FWHM_PIXELS,
                    "minor_fwhm_pixels": _BEAM_MINOR_FWHM_PIXELS,
                    "position_angle_degrees": 0.0,
                },
                "wcs": {
                    "frame": "icrs",
                    "reference_pixel_xy": [
                        (width - 1) / 2.0,
                        (height - 1) / 2.0,
                    ],
                    "reference_sky_degrees": [180.0, 45.0],
                    "pixel_scale_degrees_xy": [
                        -_PIXEL_SCALE_DEGREES,
                        _PIXEL_SCALE_DEGREES,
                    ],
                    "rotation_degrees_counterclockwise": 0.0,
                },
                "expected_statistics": {
                    "background_jy_per_beam": recipe.background,
                    "noise_rms_jy_per_beam": recipe.noise_rms,
                    "finite_fraction": 1.0 - invalid_pixels / (height * width),
                },
                "recipe": recipe.model_dump(mode="json"),
                "recipe_sha256": recipe_sha256(recipe),
            }
        )
    document: dict[str, Any] = {
        "schema_version": 1,
        "manifest_id": "quick-science-check",
        "datasets": datasets,
    }
    DatasetManifest.model_validate(document)
    return document


def main() -> None:
    """Write the manifest, refusing to replace a different one silently."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if stale")
    args = parser.parse_args()
    text = json.dumps(build_manifest(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if _OUTPUT.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{_OUTPUT} is stale; rerun without --check")
        return
    _OUTPUT.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
