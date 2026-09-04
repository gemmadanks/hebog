# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Static plots for diagnosing source-finder support disagreements.

This module deliberately contains no import-time I/O. Keeping the reusable
plotting API inside the installed :mod:`hebog` package lets notebooks import
it independently of their working directory; command-line scripts remain
thin entry points.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from matplotlib.axes import Axes
from matplotlib.colors import BoundaryNorm, ListedColormap, LogNorm
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from hebog.validation.support_diagnostics import (
    SupportComponentComparison,
    SupportPixelEvidence,
    summarize_support_component_evidence,
    summarize_support_pixels,
    support_component_masks,
)


def read_beam_geometry(
    image_path: Path,
    override_area_pixels: float | None,
) -> tuple[float, float]:
    """Return beam area and a representative beam width in pixels."""
    if override_area_pixels is not None:
        if (
            not np.isfinite(override_area_pixels)
            or override_area_pixels <= 0.0
        ):
            raise ValueError("--beam-area-pixels must be finite and positive")
        return override_area_pixels, math.sqrt(override_area_pixels)

    header = fits.getheader(image_path)
    required = ("BMAJ", "BMIN", "CDELT1", "CDELT2")
    if any(key not in header for key in required):
        raise ValueError(
            "image header needs BMAJ, BMIN, CDELT1, and CDELT2, or pass "
            "--beam-area-pixels"
        )
    major_degrees = float(header["BMAJ"])
    minor_degrees = float(header["BMIN"])
    x_scale_degrees = float(header["CDELT1"])
    y_scale_degrees = float(header["CDELT2"])
    if (
        not all(
            np.isfinite(value)
            for value in (
                major_degrees,
                minor_degrees,
                x_scale_degrees,
                y_scale_degrees,
            )
        )
        or major_degrees <= 0.0
        or minor_degrees <= 0.0
        or x_scale_degrees == 0.0
        or y_scale_degrees == 0.0
    ):
        raise ValueError(
            "image header needs finite positive beam axes and finite "
            "non-zero pixel scales"
        )
    major_pixels = abs(major_degrees / y_scale_degrees)
    minor_pixels = abs(minor_degrees / x_scale_degrees)
    area_pixels = math.pi * major_pixels * minor_pixels / (4.0 * math.log(2.0))
    return area_pixels, max(major_pixels, minor_pixels)


def _padded_bounds(
    comparison: SupportComponentComparison,
    shape_yx: tuple[int, int],
    padding_pixels: int,
) -> tuple[int, int, int, int]:
    y_start, y_stop, x_start, x_stop = comparison.bounds_yx_half_open
    return (
        max(0, y_start - padding_pixels),
        min(shape_yx[0], y_stop + padding_pixels),
        max(0, x_start - padding_pixels),
        min(shape_yx[1], x_stop + padding_pixels),
    )


def _finite_limits(
    plane: np.ndarray,
    lower: float,
    upper: float,
) -> tuple[float, float]:
    finite = plane[np.isfinite(plane)]
    if finite.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(finite, (lower, upper))
    if low == high:
        high = low + max(abs(low), 1.0) * 1e-6
    return float(low), float(high)


def _contour_supports(  # noqa: PLR0913, PLR0917
    axis: Axes,
    candidate_mask: np.ndarray,
    reference_mask: np.ndarray,
    extent: tuple[int, int, int, int],
    candidate_name: str,
    reference_name: str,
) -> None:
    if np.any(reference_mask):
        axis.contour(
            reference_mask,
            levels=(0.5,),
            colors=("tab:orange",),
            linewidths=1.6,
            extent=extent,
        )
    if np.any(candidate_mask):
        axis.contour(
            candidate_mask,
            levels=(0.5,),
            colors=("tab:blue",),
            linewidths=1.2,
            extent=extent,
        )
    axis.legend(
        handles=(
            Patch(
                facecolor="none",
                edgecolor="tab:blue",
                label=candidate_name,
            ),
            Patch(
                facecolor="none",
                edgecolor="tab:orange",
                label=reference_name,
            ),
        ),
        loc="upper right",
        fontsize="small",
    )


def _imshow_with_colorbar(  # noqa: PLR0913
    figure: Figure,
    axis: Axes,
    plane: np.ndarray,
    *,
    extent: tuple[int, int, int, int],
    title: str,
    colorbar_label: str,
    **kwargs: Any,
) -> None:
    rendered = axis.imshow(plane, origin="lower", extent=extent, **kwargs)
    axis.set_title(title)
    figure.colorbar(rendered, ax=axis, shrink=0.82, label=colorbar_label)


def _evidence_value(value: float | None, scale: float = 1.0) -> float:
    return math.nan if value is None else value * scale


def plot_support_component_diagnostic(  # noqa: PLR0913, PLR0915
    *,
    image: np.ndarray,
    background: np.ndarray,
    rms: np.ndarray,
    candidate_labels: np.ndarray,
    reference_labels: np.ndarray,
    comparison: SupportComponentComparison,
    beam_area_pixels: float,
    beam_width_pixels: float,
    padding_beams: float,
    candidate_name: str,
    reference_name: str,
) -> tuple[Figure, SupportPixelEvidence]:
    """Plot image-domain evidence for one support-component disagreement."""
    if not np.isfinite(beam_width_pixels) or beam_width_pixels <= 0.0:
        raise ValueError("beam_width_pixels must be finite and positive")
    if not np.isfinite(padding_beams) or padding_beams < 0.0:
        raise ValueError("padding_beams must be finite and non-negative")
    evidence = summarize_support_component_evidence(
        comparison,
        candidate_labels,
        reference_labels,
        image=image,
        background=background,
        rms=rms,
        beam_area_pixels=beam_area_pixels,
    )
    masks = support_component_masks(
        comparison,
        candidate_labels,
        reference_labels,
    )
    padding = math.ceil(padding_beams * beam_width_pixels)
    y_start, y_stop, x_start, x_stop = _padded_bounds(
        comparison,
        image.shape,
        padding,
    )
    cut = np.s_[y_start:y_stop, x_start:x_stop]
    extent = (x_start, x_stop, y_start, y_stop)
    image_cut = image[cut]
    background_cut = background[cut]
    rms_cut = rms[cut]
    common_cut = masks.common[cut]
    reference_only_cut = masks.reference_only[cut]
    candidate_only_cut = masks.candidate_only[cut]
    reference_mask_cut = common_cut | reference_only_cut
    candidate_mask_cut = common_cut | candidate_only_cut
    local_off_source_mask = (
        (reference_labels[cut] == 0)
        & (candidate_labels[cut] == 0)
        & np.isfinite(image_cut)
    )
    local_off_source = summarize_support_pixels(
        local_off_source_mask,
        image=image_cut,
        background=background_cut,
        rms=rms_cut,
        beam_area_pixels=beam_area_pixels,
    )

    figure, axes = plt.subplots(
        2,
        4,
        figsize=(20, 10),
        constrained_layout=True,
    )
    raw_low, raw_high = _finite_limits(image_cut, 1.0, 99.7)
    _imshow_with_colorbar(
        figure,
        axes[0, 0],
        image_cut * 1e3,
        extent=extent,
        title="Input image",
        colorbar_label="mJy/beam",
        cmap="gray",
        vmin=raw_low * 1e3,
        vmax=raw_high * 1e3,
    )
    _contour_supports(
        axes[0, 0],
        candidate_mask_cut,
        reference_mask_cut,
        extent,
        candidate_name,
        reference_name,
    )

    background_low, background_high = _finite_limits(
        background_cut,
        1.0,
        99.0,
    )
    _imshow_with_colorbar(
        figure,
        axes[0, 1],
        background_cut * 1e3,
        extent=extent,
        title=f"{candidate_name} background",
        colorbar_label="mJy/beam",
        cmap="viridis",
        vmin=background_low * 1e3,
        vmax=background_high * 1e3,
    )
    _contour_supports(
        axes[0, 1],
        candidate_mask_cut,
        reference_mask_cut,
        extent,
        candidate_name,
        reference_name,
    )

    positive_rms = rms_cut[np.isfinite(rms_cut) & (rms_cut > 0.0)] * 1e6
    rms_low, rms_high = _finite_limits(positive_rms, 1.0, 99.5)
    _imshow_with_colorbar(
        figure,
        axes[0, 2],
        rms_cut * 1e6,
        extent=extent,
        title=f"{candidate_name} RMS",
        colorbar_label="µJy/beam (log scale)",
        cmap="magma",
        norm=LogNorm(vmin=max(rms_low, np.finfo(float).tiny), vmax=rms_high),
    )
    _contour_supports(
        axes[0, 2],
        candidate_mask_cut,
        reference_mask_cut,
        extent,
        candidate_name,
        reference_name,
    )

    direct_snr = np.divide(
        image_cut - background_cut,
        rms_cut,
        out=np.full(image_cut.shape, np.nan),
        where=np.isfinite(rms_cut) & (rms_cut > 0.0),
    )
    _imshow_with_colorbar(
        figure,
        axes[0, 3],
        direct_snr,
        extent=extent,
        title=f"{candidate_name} direct local significance",
        colorbar_label="sigma (clipped)",
        cmap="RdBu_r",
        vmin=-3.0,
        vmax=10.0,
    )
    _contour_supports(
        axes[0, 3],
        candidate_mask_cut,
        reference_mask_cut,
        extent,
        candidate_name,
        reference_name,
    )

    role_plane = np.zeros(image_cut.shape, dtype=np.uint8)
    role_plane[common_cut] = 1
    role_plane[reference_only_cut] = 2
    role_plane[candidate_only_cut] = 3
    role_colors = ListedColormap(("#6a3d9a", "#ff7f00", "#1f78b4"))
    axes[1, 0].imshow(
        np.ma.masked_equal(role_plane, 0),
        origin="lower",
        extent=extent,
        cmap=role_colors,
        norm=BoundaryNorm((0.5, 1.5, 2.5, 3.5), role_colors.N),
    )
    axes[1, 0].set_title("Support agreement")
    axes[1, 0].set_facecolor("0.12")
    axes[1, 0].legend(
        handles=(
            Patch(color="#6a3d9a", label="common"),
            Patch(color="#ff7f00", label=f"{reference_name} only"),
            Patch(color="#1f78b4", label=f"{candidate_name} only"),
        ),
        loc="upper right",
        fontsize="small",
    )

    finite_common_snr = direct_snr[common_cut & np.isfinite(direct_snr)]
    finite_reference_only_snr = direct_snr[
        reference_only_cut & np.isfinite(direct_snr)
    ]
    histogram_values = np.concatenate(
        (finite_common_snr, finite_reference_only_snr)
    )
    if histogram_values.size:
        lower, upper = np.percentile(histogram_values, (0.5, 99.5))
        lower = min(float(lower), 3.0)
        upper = max(float(upper), 5.0)
        bins = np.linspace(lower, upper, 51)
        axes[1, 1].hist(
            finite_common_snr,
            bins=bins,
            histtype="step",
            linewidth=1.8,
            color="#6a3d9a",
            label="common",
        )
        axes[1, 1].hist(
            finite_reference_only_snr,
            bins=bins,
            histtype="step",
            linewidth=1.8,
            color="#ff7f00",
            label=f"{reference_name} only",
        )
    axes[1, 1].axvline(3.0, color="0.35", linestyle="--", label="3 sigma")
    axes[1, 1].axvline(5.0, color="0.1", linestyle=":", label="5 sigma")
    axes[1, 1].set_yscale("symlog", linthresh=1.0)
    axes[1, 1].set_xlabel(f"{candidate_name} direct local significance")
    axes[1, 1].set_ylabel("pixels")
    axes[1, 1].set_title("Direct-S/N distributions")
    axes[1, 1].legend(fontsize="small")

    role_evidence = (
        ("common", evidence.common),
        (f"{reference_name}\nonly", evidence.reference_only),
        (f"{candidate_name}\nonly", evidence.candidate_only),
    )
    x_positions = np.arange(len(role_evidence))
    width = 0.24
    for offset, field, label, color in (
        (-width, "raw_flux_jy", "raw image", "0.35"),
        (0.0, "background_flux_jy", "assigned background", "#e31a1c"),
        (width, "residual_flux_jy", "residual", "#33a02c"),
    ):
        axes[1, 2].bar(
            x_positions + offset,
            [
                _evidence_value(getattr(item, field), 1e3)
                for _, item in role_evidence
            ],
            width,
            label=label,
            color=color,
        )
    axes[1, 2].axhline(0.0, color="black", linewidth=0.8)
    axes[1, 2].set_xticks(
        x_positions,
        [label for label, _ in role_evidence],
    )
    axes[1, 2].set_ylabel("integrated flux (mJy)")
    axes[1, 2].set_title("Flux accounting over support roles")
    axes[1, 2].legend(fontsize="small")

    summary = comparison.summary
    reference_only = evidence.reference_only
    off_source_rms = local_off_source.rms_median_jy_per_beam
    omitted_rms = reference_only.rms_median_jy_per_beam
    rms_ratio = (
        omitted_rms / off_source_rms
        if omitted_rms is not None
        and off_source_rms is not None
        and off_source_rms > 0.0
        else None
    )
    assigned_fraction = (
        reference_only.background_flux_jy / reference_only.raw_flux_jy
        if reference_only.background_flux_jy is not None
        and reference_only.raw_flux_jy is not None
        and reference_only.raw_flux_jy != 0.0
        else None
    )
    precision = (
        "n/a" if summary.precision is None else f"{summary.precision:.3f}"
    )
    text_lines = (
        f"{reference_name} label: {summary.reference_label}",
        f"touching {candidate_name} labels: "
        f"{summary.candidate_labels or 'none'}",
        f"fragments: {summary.fragment_count}",
        f"precision / recall / IoU: {precision} / {summary.recall:.3f} / "
        f"{summary.intersection_over_union:.3f}",
        f"reference support: {summary.reference_pixel_count:,} px "
        f"({summary.reference_pixel_count / beam_area_pixels:.2f} beams)",
        f"reference-only: {summary.reference_only_pixel_count:,} px "
        f"({summary.reference_only_pixel_count / beam_area_pixels:.2f} beams)",
        f"reference-only median direct S/N: "
        f"{_evidence_value(reference_only.direct_snr_median):.3g}",
        f"reference-only median RMS / local off-source: "
        f"{_evidence_value(omitted_rms, 1e6):.3g} / "
        f"{_evidence_value(off_source_rms, 1e6):.3g} µJy/beam",
        f"RMS ratio: {_evidence_value(rms_ratio):.3g}x",
        f"reference-only background / raw flux: "
        f"{_evidence_value(assigned_fraction, 100.0):.1f}%",
        "",
        "Interpretation aid only:",
        "the reference finder is not ground truth.",
    )
    axes[1, 3].axis("off")
    axes[1, 3].text(
        0.02,
        0.98,
        "\n".join(text_lines),
        va="top",
        ha="left",
        family="monospace",
        fontsize=10,
        transform=axes[1, 3].transAxes,
    )
    axes[1, 3].set_title("Component summary")

    for axis in (
        axes[0, 0],
        axes[0, 1],
        axes[0, 2],
        axes[0, 3],
        axes[1, 0],
    ):
        axis.set_xlabel("x pixel")
        axis.set_ylabel("y pixel")
    figure.suptitle(
        f"Support component diagnostic: {candidate_name} vs {reference_name}",
        fontsize=16,
    )
    return figure, local_off_source
