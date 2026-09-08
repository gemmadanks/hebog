"""Independent analytic truth for the joint R1--R4 scientific repairs."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.extended_measurement import (
    measure_detected_segment_position,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.public_science import build_configured_continuum_products
from hebog.validation import products as product_builder
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.products import _segment_position

_ROOT = Path(__file__).parents[2]


def test_terminal_keeps_stage_support_separate_from_published_mask() -> None:
    """A truth-linked runner can locate losses before scratch cleanup."""
    yy, xx = np.mgrid[:97, :97]
    signal = 12 * np.exp(-((xx - 48) ** 2 + (yy - 48) ** 2) / 8)
    signal += 2 * np.exp(-0.5 * (((xx - 48) / 12) ** 2 + ((yy - 48) / 6) ** 2))
    products = _products(signal)
    stages = dict(products.support_stages)
    assert set(stages) == {
        "direct",
        "multiscale",
        "persistent",
        "component-owner",
        "source-union",
        "source-owned-persistent",
        "source-measurement",
        "publication",
    }
    assert stages["source-measurement"].sum() > stages["publication"].sum()
    np.testing.assert_array_equal(
        stages["publication"], products.detection.retained_mask
    )
    assert all(
        mask.dtype == np.bool_ and not mask.flags.writeable
        for mask in stages.values()
    )


def test_independent_resolved_loops_keep_distinct_source_membership() -> None:
    """Scale evidence must neither duplicate nor merge disjoint shells."""
    yy, xx = np.mgrid[:97, :193]
    image = np.zeros_like(xx, dtype=float)
    for center_x in (48, 144):
        radius = np.hypot(xx - center_x, yy - 48)
        angle = np.arctan2(yy - 48, xx - center_x)
        image += (
            6
            * (1 + 0.6 * np.cos(6 * angle))
            * np.exp(-0.5 * ((radius - 18) / 2) ** 2)
        )
    products = _products(image)
    assert len(products.catalogue) == 2
    assert len(products.component_catalogue) == 12
    assert [row.component_count for row in products.catalogue] == [6, 6]
    assert len({row.identifier for row in products.catalogue}) == 2


def test_reconstructed_rows_preserve_ambiguity_and_validate_ids() -> None:
    """A malformed measurement is not silently attached to an owner."""
    yy, xx = np.mgrid[:49, :49]
    products = _products(10 * np.exp(-((xx - 24) ** 2 + (yy - 24) ** 2) / 8))
    association = products.source_association
    _, memberships = product_builder._source_label_plane(
        np.asarray(products.measurement_component_labels, dtype=np.int64),
        association,
    )
    label = next(iter(memberships))
    measured = replace(
        products.catalogue[0], identifier=f"hebog-segment-{label}"
    )
    ambiguous = replace(
        association,
        ambiguous_component_ids=tuple(
            row.component_id for row in association.components
        ),
    )
    result = product_builder._reconstructed_source_rows(
        (measured,),
        products.component_catalogue,
        memberships,
        ambiguous,
        compact_ids=set(),
        require_signed_aperture=True,
    )
    assert "ambiguous-multiscale-parent" in result[0].quality_flags
    with pytest.raises(ValueError, match="identity is malformed"):
        product_builder._reconstructed_source_rows(
            (products.catalogue[0],),
            products.component_catalogue,
            memberships,
            association,
            compact_ids=set(),
            require_signed_aperture=True,
        )


def test_compact_neighbour_remains_separate_from_a_core_and_halo() -> None:
    """An extended source cannot absorb a distinct compact neighbour."""
    yy, xx = np.mgrid[:97, :97]
    extended = 12 * np.exp(-((xx - 36) ** 2 + (yy - 48) ** 2) / 8)
    extended += 2 * np.exp(
        -0.5 * (((xx - 36) / 12) ** 2 + ((yy - 48) / 6) ** 2)
    )
    compact = 10 * np.exp(-((xx - 66) ** 2 + (yy - 48) ** 2) / 8)
    products = _products(extended + compact)
    assert len(products.catalogue) == 2
    centers = WCS(_header(yy.shape)).celestial.all_world2pix(
        [
            (row.right_ascension_degrees, row.declination_degrees)
            for row in products.catalogue
        ],
        0,
    )
    centers = np.asarray(centers)
    np.testing.assert_allclose(
        sorted(centers.tolist()),
        ((36.0, 48.0), (66.0, 48.0)),
        atol=0.3,
        rtol=0,
    )


def _header(shape: tuple[int, int]) -> fits.Header:
    """Use one-arcsecond pixels and a four-arcsecond circular beam."""
    return fits.Header(
        {
            "NAXIS": 2,
            "NAXIS1": shape[1],
            "NAXIS2": shape[0],
            "CTYPE1": "RA---SIN",
            "CTYPE2": "DEC--SIN",
            "CRPIX1": (shape[1] + 1) / 2,
            "CRPIX2": (shape[0] + 1) / 2,
            "CRVAL1": 10.0,
            "CRVAL2": -30.0,
            "CDELT1": -1.0 / 3600.0,
            "CDELT2": 1.0 / 3600.0,
            "BMAJ": 4.0 / 3600.0,
            "BMIN": 4.0 / 3600.0,
            "BPA": 0.0,
            "BUNIT": "Jy/beam",
            "RESTFRQ": 150e6,
        }
    )


def _products(signal: np.ndarray):
    """Exercise the complete configured composition with analytic noise."""
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )
    result = build_configured_continuum_products(
        signal,
        np.zeros_like(signal),
        np.ones_like(signal),
        _header(signal.shape),
        beam=BeamShapePixels(4.0, 4.0, 0.0),
        review=review,
        config=SourceFinderConfig(5.0, 3.0, 7),
    )
    assert result is not None
    return result


def test_missing_optional_beam_angle_uses_zero_position_angle() -> None:
    """FITS permits a zero-angle beam without an explicit BPA card."""
    yy, xx = np.mgrid[:33, :41]
    signal = 10 * np.exp(-((xx - 20) ** 2 + (yy - 16) ** 2) / 8)
    header = _header(signal.shape)
    del header["BPA"]
    review = PhaseFiveCorrectiveAReview.model_validate_json(
        (
            _ROOT / "src/hebog/resources/phase_5_continuum_review.json"
        ).read_bytes()
    )
    products = build_configured_continuum_products(
        signal,
        np.zeros_like(signal),
        np.ones_like(signal),
        header,
        beam=BeamShapePixels(4.0, 4.0, 0.0),
        review=review,
        config=SourceFinderConfig(5.0, 3.0, 7),
    )
    assert products is not None
    assert len(products.catalogue) == 1


def test_shell_reconciliation_does_not_absorb_a_compact_neighbour() -> None:
    """Resolved-loop evidence belongs to its arcs, not all nearby peaks."""
    yy, xx = np.mgrid[:97, :97]
    radius = np.hypot(xx - 48, yy - 48)
    angle = np.arctan2(yy - 48, xx - 48)
    signal = (
        6
        * (1 + 0.6 * np.cos(6 * angle))
        * np.exp(-0.5 * ((radius - 18) / 2) ** 2)
    )
    signal += 12 * np.exp(-((xx - 76) ** 2 + (yy - 48) ** 2) / 8)
    products = _products(signal)
    assert len(products.catalogue) == 2
    centers = WCS(_header(signal.shape)).celestial.all_world2pix(
        [
            (row.right_ascension_degrees, row.declination_degrees)
            for row in products.catalogue
        ],
        0,
    )
    np.testing.assert_allclose(
        sorted(np.asarray(centers).tolist()),
        ((48.0, 48.0), (76.0, 48.0)),
        atol=0.3,
        rtol=0,
    )


@pytest.mark.parametrize("count", (2, 3, 4))
def test_connected_independent_gaussians_remain_separate_sources(
    count: int,
) -> None:
    """A shared above-threshold island must not merge independent truth."""
    yy, xx = np.mgrid[:97, :97]
    centers = tuple(34.0 + 7.0 * index for index in range(count))
    amplitudes = tuple(10.0 - 0.5 * index for index in range(count))
    signal = sum(
        amplitude * np.exp(-((yy - 48.0) ** 2 + (xx - center) ** 2) / 8.0)
        for amplitude, center in zip(amplitudes, centers, strict=True)
    )
    result = _products(np.asarray(signal))

    assert result.detection.component_count == 1
    assert len(result.component_catalogue) == count
    assert len(result.catalogue) == count
    assert all(row.component_count == 1 for row in result.catalogue)
    wcs = WCS(_header(yy.shape)).celestial
    positions = np.asarray(
        wcs.all_world2pix(
            [
                (row.right_ascension_degrees, row.declination_degrees)
                for row in result.catalogue
            ],
            0,
        )
    )
    np.testing.assert_allclose(
        sorted(positions.tolist()),
        [(center, 48.0) for center in centers],
        atol=1e-3,
        rtol=0.0,
    )
    beam_area = np.pi * 16.0 / (4.0 * np.log(2.0))
    expected_flux = sorted(
        amplitude * 8 * np.pi / beam_area for amplitude in amplitudes
    )
    np.testing.assert_allclose(
        sorted(row.integrated_flux_jy for row in result.catalogue),
        expected_flux,
        rtol=1e-3,
    )


@pytest.mark.parametrize("morphology", ("shell", "filament"))
def test_extended_single_source_survives_compact_separation(
    morphology: str,
) -> None:
    """One curved extended source is not split into independent knots."""
    yy, xx = np.mgrid[:97, :97]
    if morphology == "shell":
        radius = np.hypot(xx - 48.0, yy - 48.0)
        angle = np.arctan2(yy - 48.0, xx - 48.0)
        signal = 6.0 * np.exp(-0.5 * ((radius - 18.0) / 2.0) ** 2)
        signal *= 1.0 + 0.6 * np.cos(6.0 * angle)
    else:
        ridge = 48.0 + 8.0 * np.sin((xx - 48.0) / 12.0)
        signal = 8.0 * np.exp(-0.5 * ((yy - ridge) / 2.0) ** 2)
        signal *= np.exp(-0.5 * ((xx - 48.0) / 19.0) ** 2)
    result = _products(signal)

    assert len(result.catalogue) == 1
    if morphology == "shell":
        assert len(result.component_catalogue) == 6
    assert result.catalogue[0].component_count == len(
        result.component_catalogue
    )
    source_disposition = next(
        item
        for item in result.measurement_dispositions
        if item.object_kind == "source"
    )
    assert source_disposition.estimator == "source-owned-signed-aperture"
    assert (
        "original-pixel-gaussian-model"
        not in result.catalogue[0].quality_flags
    )
    assert result.catalogue[0].fitted_shape is None
    assert result.catalogue[0].deconvolution_status == "unavailable"


def test_valid_fit_survives_unavailable_aperture_moment_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing auxiliary moment row cannot erase a measured Gaussian."""

    def missing_aperture(*_args: object, **_kwargs: object) -> tuple[()]:
        return ()

    monkeypatch.setattr(
        product_builder,
        "build_hebog_segment_moment_catalogue",
        missing_aperture,
    )
    yy, xx = np.mgrid[:65, :65]
    signal = 10 * np.exp(-((xx - 32) ** 2 / 8 + (yy - 32) ** 2 / 5))
    result = _products(signal)
    assert len(result.component_catalogue) == len(result.catalogue) == 1
    assert result.catalogue[0].integrated_flux_jy > 0.0
    assert all(
        item.status == "measured" for item in result.measurement_dispositions
    )


def test_terminal_gaussians_exclude_unavailable_moments() -> None:
    """Notebook and evaluator components have the same fit-only semantics."""
    yy, xx = np.mgrid[:65, :97]
    signal = 10 * np.exp(-((xx - 70) ** 2 + (yy - 32) ** 2) / 8)
    signal[32, 12:19] = 10.0
    result = _products(signal)
    assert len(result.catalogue) == 2
    assert len(result.source_association.components) == 2
    assert len(result.component_catalogue) == 1
    assert all(
        "original-pixel-gaussian-model" in row.quality_flags
        for row in result.component_catalogue
    )


@pytest.mark.parametrize("peak", (6.0, 10.0, 100.0))
def test_compact_shape_is_not_a_threshold_truncated_moment(
    peak: float,
) -> None:
    """An analytic resolved Gaussian keeps its shape across support cuts."""
    yy, xx = np.mgrid[:65, :65]
    signal = peak * np.exp(
        -4.0 * np.log(2.0) * ((xx - 32) ** 2 / 49.0 + (yy - 32) ** 2 / 36.0)
    )
    result = _products(signal)

    assert len(result.catalogue) == len(result.component_catalogue) == 1
    for row in (*result.catalogue, *result.component_catalogue):
        assert row.fitted_shape is not None
        np.testing.assert_allclose(
            (
                row.fitted_shape.major_fwhm_degrees * 3600.0,
                row.fitted_shape.minor_fwhm_degrees * 3600.0,
            ),
            (7.0, 6.0),
            rtol=1e-3,
        )
        assert "segment-moment-equivalent-shape" not in row.quality_flags
        assert row.peak_flux_error_jy_per_beam is not None
        assert row.integrated_flux_error_jy is not None
        assert row.right_ascension_error_degrees is not None
        assert row.fitted_shape.major_fwhm_error_degrees is not None


def test_cancelled_signed_centroid_uses_stable_denoised_alternative() -> None:
    """Small positive total flux must not publish an off-image position."""
    signal = np.zeros((9, 9), dtype=np.float64)
    signal[4, 2:7] = (10.0, -2.4, -2.4, -2.4, -2.4)
    support = np.zeros(signal.shape, dtype=np.bool_)
    support[4, 2:7] = True

    estimate = _segment_position(
        signal,
        np.maximum(signal, 0.0),
        support,
        maximum_peak_to_mean_ratio=3.0,
    )

    assert estimate.available
    assert estimate.centroid_xy == (2.0, 4.0)
    assert estimate.weighting == "denoised"


def test_collinear_positive_centroid_tolerates_floating_point_roundoff() -> (
    None
):
    """A single-row source is not unstable because y rounds below its row."""
    signal = np.zeros((20, 10))
    signal[7, 2:5] = 0.1 * np.array((1, 2, 3))
    estimate = measure_detected_segment_position(signal, signal > 0)
    assert estimate.available
    assert estimate.centroid_xy == pytest.approx((10 / 3, 7))


def test_symmetric_numerical_cancellation_is_explicitly_unavailable() -> None:
    """Staying in the image does not excuse a numerically cancelled sum."""
    signal = np.zeros((9, 9))
    signal[4, 2:5] = (1, -2 + 1e-12, 1)
    estimate = measure_detected_segment_position(signal, signal != 0)
    assert not estimate.available
    assert estimate.unavailable_reason == "ill-conditioned-segment-position"


@pytest.mark.parametrize("count", (3, 6))
def test_independent_compact_polygon_is_not_an_extended_shell(
    count: int,
) -> None:
    """Circular arrangement alone cannot turn independent truth into a ring."""
    yy, xx = np.mgrid[:97, :97]
    angles = np.arange(count) * 2 * np.pi / count
    signal = np.zeros_like(xx, dtype=np.float64)
    for index, angle in enumerate(angles):
        cx, cy = 48 + 18 * np.cos(angle), 48 + 18 * np.sin(angle)
        signal += (10 - 0.2 * index) * np.exp(
            -((xx - cx) ** 2 + (yy - cy) ** 2) / 8
        )
    result = _products(signal)
    assert len(result.catalogue) == count
    assert all(row.component_count == 1 for row in result.catalogue)


def test_mixed_core_and_halo_remains_one_extended_source() -> None:
    """A 75%-flux halo is not lost when its compact core fits successfully."""
    yy, xx = np.mgrid[:97, :97]
    core = 12 * np.exp(-0.5 * (((xx - 48) / 2) ** 2 + ((yy - 48) / 2) ** 2))
    halo = 2 * np.exp(-0.5 * (((xx - 48) / 12) ** 2 + ((yy - 48) / 6) ** 2))
    result = _products(core + halo)
    assert len(result.catalogue) == 1
    assert result.catalogue[0].component_count is not None
    assert result.catalogue[0].component_count >= 1
    source = next(
        item
        for item in result.measurement_dispositions
        if item.object_kind == "source"
    )
    assert source.estimator == "source-owned-signed-aperture"
    beam_area = np.pi * 16 / (4 * np.log(2))
    truth_flux = float(np.sum(core + halo)) / beam_area
    # The pre-existing Continuum aperture retention floor remains binding.
    assert result.catalogue[0].integrated_flux_jy >= 0.9 * truth_flux
