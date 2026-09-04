"""Tests for importable support-diagnostic plotting helpers."""
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.support_diagnostics import compare_support_component
from hebog.validation.support_plotting import (
    plot_support_component_diagnostic,
    read_beam_geometry,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_beam_override_does_not_require_readable_image() -> None:
    assert read_beam_geometry(Path("not-present.fits"), 16.0) == (16.0, 4.0)


@pytest.mark.parametrize("beam_area", [0.0, -1.0, float("nan")])
def test_beam_override_must_be_positive_and_finite(beam_area: float) -> None:
    with pytest.raises(
        ValueError,
        match="beam-area-pixels must be finite and positive",
    ):
        read_beam_geometry(Path("not-present.fits"), beam_area)


def test_beam_geometry_uses_fits_header(tmp_path: Path) -> None:
    image_path = tmp_path / "image.fits"
    header = fits.Header(
        {
            "BMAJ": 4.0,
            "BMIN": 2.0,
            "CDELT1": -0.5,
            "CDELT2": 0.5,
        }
    )
    fits.PrimaryHDU(np.zeros((2, 2)), header=header).writeto(image_path)

    area, width = read_beam_geometry(image_path, None)

    assert area == pytest.approx(np.pi * 8.0 * 4.0 / (4.0 * np.log(2.0)))
    assert width == 8.0


def test_beam_geometry_requires_complete_fits_header(tmp_path: Path) -> None:
    image_path = tmp_path / "image.fits"
    fits.PrimaryHDU(np.zeros((2, 2))).writeto(image_path)

    with pytest.raises(ValueError, match="image header needs BMAJ"):
        read_beam_geometry(image_path, None)


@pytest.mark.parametrize(
    ("keyword", "value"),
    [("BMAJ", 0.0), ("BMIN", -1.0), ("CDELT1", 0.0)],
)
def test_beam_geometry_rejects_invalid_header_values(
    tmp_path: Path,
    keyword: str,
    value: float,
) -> None:
    image_path = tmp_path / "image.fits"
    header = fits.Header(
        {
            "BMAJ": 4.0,
            "BMIN": 2.0,
            "CDELT1": -0.5,
            "CDELT2": 0.5,
        }
    )
    header[keyword] = value
    fits.PrimaryHDU(np.zeros((2, 2)), header=header).writeto(image_path)

    with pytest.raises(ValueError, match="finite positive beam"):
        read_beam_geometry(image_path, None)


@pytest.mark.parametrize(
    ("beam_width_pixels", "padding_beams", "message"),
    [
        (0.0, 1.0, "beam_width_pixels"),
        (1.0, -1.0, "padding_beams"),
        (1.0, float("nan"), "padding_beams"),
    ],
)
def test_plot_rejects_invalid_display_geometry(
    beam_width_pixels: float,
    padding_beams: float,
    message: str,
) -> None:
    labels = np.zeros((3, 3), dtype=np.int32)
    labels[1, 1] = 1
    comparison = compare_support_component(labels, labels, 1)
    plane = np.ones((3, 3), dtype=np.float64)

    with pytest.raises(ValueError, match=message):
        plot_support_component_diagnostic(
            image=plane,
            background=plane,
            rms=plane,
            candidate_labels=labels,
            reference_labels=labels,
            comparison=comparison,
            beam_area_pixels=1.0,
            beam_width_pixels=beam_width_pixels,
            padding_beams=padding_beams,
            candidate_name="candidate",
            reference_name="reference",
        )


def test_plot_support_component_diagnostic_renders_support_roles() -> None:
    shape = (10, 10)
    reference_labels = np.zeros(shape, dtype=np.int32)
    reference_labels[3:7, 3:7] = 7
    candidate_labels = np.zeros(shape, dtype=np.int32)
    candidate_labels[2:6, 3:6] = 11
    comparison = compare_support_component(
        candidate_labels,
        reference_labels,
        reference_label=7,
    )
    image = np.linspace(-0.1, 1.0, num=100).reshape(shape)
    background = np.full(shape, 0.01)
    rms = np.full(shape, 0.1)

    figure, off_source = plot_support_component_diagnostic(
        image=image,
        background=background,
        rms=rms,
        candidate_labels=candidate_labels,
        reference_labels=reference_labels,
        comparison=comparison,
        beam_area_pixels=2.0,
        beam_width_pixels=2.0,
        padding_beams=1.0,
        candidate_name="Hebog",
        reference_name="PyBDSF",
    )
    try:
        assert figure.axes[0].get_title() == "Input image"
        assert any(
            axis.get_title() == "Support agreement" for axis in figure.axes
        )
        assert off_source.pixel_count > 0
    finally:
        plt.close(figure)


def test_plotting_api_imports_outside_repository(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from hebog.validation.support_plotting import "
                "plot_support_component_diagnostic, read_beam_geometry"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_campaign_notebook_imports_plotting_from_installed_package() -> None:
    notebook = _REPOSITORY_ROOT / (
        "notebooks/campaign_source_finder_comparison.py"
    )
    tree = ast.parse(notebook.read_text(encoding="utf-8"))
    plotting_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(
            alias.name == "plot_support_component_diagnostic"
            for alias in node.names
        )
    }

    assert plotting_imports == {"hebog.validation.support_plotting"}
