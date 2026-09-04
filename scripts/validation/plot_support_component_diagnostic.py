#!/usr/bin/env python3
# pyright: reportUnknownMemberType=false
"""Plot one source-finder support disagreement in image-domain context."""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from hebog.validation.products import load_fits_plane
from hebog.validation.support_diagnostics import (
    compare_support_component,
    summarize_support_component_evidence,
)
from hebog.validation.support_plotting import (
    plot_support_component_diagnostic,
    read_beam_geometry,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--background", type=Path, required=True)
    parser.add_argument("--rms", type=Path, required=True)
    parser.add_argument("--candidate-labels", type=Path, required=True)
    parser.add_argument("--reference-labels", type=Path, required=True)
    parser.add_argument("--reference-label", type=int, required=True)
    parser.add_argument("--candidate-name", default="candidate")
    parser.add_argument("--reference-name", default="reference")
    parser.add_argument("--beam-area-pixels", type=float)
    parser.add_argument("--padding-beams", type=float, default=3.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def _load_labels(path: Path) -> np.ndarray:
    raw = load_fits_plane(path)
    rounded = np.rint(raw)
    if not np.all(np.isfinite(raw)) or not np.array_equal(raw, rounded):
        raise ValueError(f"label plane must contain finite integers: {path}")
    return np.asarray(rounded, dtype=np.int32)


def main() -> None:
    args = _parse_args()
    image = load_fits_plane(args.image)
    background = load_fits_plane(args.background)
    rms = load_fits_plane(args.rms)
    candidate_labels = _load_labels(args.candidate_labels)
    reference_labels = _load_labels(args.reference_labels)
    if any(plane.shape != image.shape for plane in (background, rms)):
        raise ValueError(
            "image, background, and RMS planes must have the same shape"
        )
    comparison = compare_support_component(
        candidate_labels,
        reference_labels,
        args.reference_label,
    )
    beam_area_pixels, beam_width_pixels = read_beam_geometry(
        args.image,
        args.beam_area_pixels,
    )
    figure, local_off_source = plot_support_component_diagnostic(
        image=image,
        background=background,
        rms=rms,
        candidate_labels=candidate_labels,
        reference_labels=reference_labels,
        comparison=comparison,
        beam_area_pixels=beam_area_pixels,
        beam_width_pixels=beam_width_pixels,
        padding_beams=args.padding_beams,
        candidate_name=args.candidate_name,
        reference_name=args.reference_name,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=180)
    plt.close(figure)

    if args.summary_output is not None:
        evidence = summarize_support_component_evidence(
            comparison,
            candidate_labels,
            reference_labels,
            image=image,
            background=background,
            rms=rms,
            beam_area_pixels=beam_area_pixels,
        )
        record = {
            "schema_version": 1,
            "interpretation": (
                "descriptive finder-to-finder support disagreement; neither "
                "label plane is designated as scientific truth"
            ),
            "candidate_name": args.candidate_name,
            "reference_name": args.reference_name,
            "image": str(args.image.resolve()),
            "background": str(args.background.resolve()),
            "rms": str(args.rms.resolve()),
            "candidate_labels": str(args.candidate_labels.resolve()),
            "reference_labels": str(args.reference_labels.resolve()),
            "beam_area_pixels": beam_area_pixels,
            "comparison": dataclasses.asdict(comparison),
            "evidence": dataclasses.asdict(evidence),
            "local_off_source_evidence": dataclasses.asdict(local_off_source),
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
