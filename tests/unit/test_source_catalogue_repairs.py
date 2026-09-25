"""Independent analytic truth for the joint R1--R4 scientific repairs."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import gaussian_filter

from hebog.algorithms import component_measurement
from hebog.algorithms import fitting as gaussian_fitting
from hebog.algorithms.component_measurement import ComponentGroupingEvidence
from hebog.algorithms.extended_measurement import (
    SegmentWindow,
    measure_detected_segment_position,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import CompactGaussianFitConfig, SourceFinderConfig
from hebog.data_models.astrometry import LocalTangentPlaneTransform
from hebog.data_models.catalogues import SkyPosition
from hebog.data_models.fitting import CompactGaussianFitResult
from hebog.data_models.images import RestoringBeam
from hebog.data_models.measurement import ValidMomentMeasurement
from hebog.public_science import build_configured_continuum_products
from hebog.science import catalogues as product_builder
from hebog.science.catalogues import (
    _segment_pixel_moment_covariance,
    _segment_position,
    moment_shape_fields_at,
    unavailable_moment_shape_fields,
)
from hebog.science.models import ContinuumProducts
from hebog.science.profile import (
    ContinuumScienceProfile,
    configured_science_profile,
    load_continuum_science_profile,
)
from hebog.validation import tiled_detection
from hebog.validation.tiled_detection import publish_continuum_inputs

_ROOT = Path(__file__).parents[2]


def test_clipped_gaussian_source_keeps_observable_domain() -> None:
    """The aperture keeps the observable domain the fitted flux leaves.

    The source flux is the summed fitted component flux (23 September
    decision), which integrates the sky beyond the image edge and so exceeds
    the observable truth. The observable quantity stays published as the
    association aperture, which is what this guards.
    """
    yy, xx = np.mgrid[:49, :65]
    signal = 10 * np.exp(-0.5 * (((xx - 0.7) / 6) ** 2 + ((yy - 24) / 4) ** 2))
    products = _products(signal)
    # Truth is the injected flux inside the image, per 4-pixel beam area.
    observed_truth_flux = float(np.sum(signal)) / (
        np.pi * 4 * 4 / (4 * np.log(2))
    )
    assert len(products.catalogue) == len(products.component_catalogue) == 1
    source, component = products.catalogue[0], products.component_catalogue[0]
    assert "original-pixel-gaussian-model" in component.quality_flags
    assert "original-pixel-gaussian-model" not in source.quality_flags
    assert source.association_integrated_flux_jy == pytest.approx(
        observed_truth_flux, rel=0.001
    )
    assert source.integrated_flux_jy == pytest.approx(
        component.integrated_flux_jy
    )
    assert component.integrated_flux_jy > 1.5 * observed_truth_flux
    positions = np.asarray(
        WCS(_header(signal.shape)).celestial.all_world2pix(
            [
                (row.right_ascension_degrees, row.declination_degrees)
                for row in (source, component)
            ],
            0,
        )
    )
    assert positions[0, 0] > 3
    assert positions[1, 0] == pytest.approx(0.7, abs=0.001)
    assert source.deconvolution_status == "unavailable"
    assert source.integrated_flux_error_jy == pytest.approx(
        component.integrated_flux_error_jy
    )


def test_public_measurements_retain_fit_and_centroid_attribution() -> None:
    """A saved record must identify estimator support and its alternatives."""
    yy, xx = np.mgrid[:49, :49]
    result = _products(10 * np.exp(-((xx - 24) ** 2 + (yy - 24) ** 2) / 8))
    component = next(
        row
        for row in result.measurement_dispositions
        if row.object_kind == "component"
    )
    source = next(
        row
        for row in result.measurement_dispositions
        if row.object_kind == "source"
    )
    assert component.fit_diagnostics is not None
    assert component.fit_diagnostics.retained_pixel_count > 0
    assert component.fit_covariance_available is not None
    assert component.association_diagnostics is not None
    assert component.association_diagnostics.hierarchy_group_id
    assert component.association_diagnostics.compact_model_group_id
    assert component.association_diagnostics.extended_group_id is None
    assert component.association_diagnostics.decision == "compact-model"
    assert (
        type(component).model_validate_json(component.model_dump_json())
        == component
    )
    assert source.position_diagnostics is not None
    assert source.position_diagnostics.signed_original_xy == pytest.approx(
        (24, 24)
    )
    assert source.position_diagnostics.denoised_xy == pytest.approx((24, 24))
    assert source.position_diagnostics.position_pixel_count > 0
    assert (
        source.position_diagnostics.aperture_pixel_count
        > source.position_diagnostics.position_pixel_count
    )
    assert source.position_diagnostics.selection_reason
    assert (
        source.position_diagnostics.aperture_signed_flux_jy
        == pytest.approx(result.catalogue[0].integrated_flux_jy)
    )


def test_public_extended_source_retains_bounded_merge_evidence() -> None:
    """Every merged source exposes the evidence and participating members."""
    yy, xx = np.mgrid[:97, :97]
    radius = np.hypot(xx - 48, yy - 48)
    angle = np.arctan2(yy - 48, xx - 48)
    result = _products(
        6
        * (1 + 0.6 * np.cos(6 * angle))
        * np.exp(-0.5 * ((radius - 18) / 2) ** 2)
    )
    sources = [
        row
        for row in result.measurement_dispositions
        if row.object_kind == "source"
    ]
    assert len(sources) == 1
    assert len(sources[0].member_component_ids) > 1
    assert sources[0].association_evidence
    for evidence in sources[0].association_evidence:
        assert evidence.reason
        assert set(evidence.member_component_ids) <= set(
            sources[0].member_component_ids
        )
        assert set(evidence.protected_component_ids) <= set(
            evidence.member_component_ids
        )
    assert (
        type(sources[0]).model_validate_json(sources[0].model_dump_json())
        == sources[0]
    )


def test_public_merge_evidence_cannot_join_foreign_source_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corrupt grouping attribution fails before publishing a false claim."""
    original = tiled_detection.reconcile_component_measurements

    def invalid_evidence(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        assert len(result.fits) == 2
        return replace(
            result,
            grouping_evidence=(
                ComponentGroupingEvidence(
                    "directional-fwhm-overlap",
                    (),
                    frozenset(index for index, _ in result.fits),
                ),
            ),
        )

    monkeypatch.setattr(
        tiled_detection,
        "reconcile_component_measurements",
        invalid_evidence,
    )
    yy, xx = np.mgrid[:49, :97]
    signal = 10 * np.exp(-((xx - 16) ** 2 + (yy - 24) ** 2) / 8)
    signal += 10 * np.exp(-((xx - 80) ** 2 + (yy - 24) ** 2) / 8)
    with pytest.raises(ValueError, match="merge evidence disagrees"):
        _products(signal)


@pytest.mark.parametrize("peak", (8.0, 20.0, 80.0))
@pytest.mark.parametrize("separation", (12.0, 20.0, 32.0))
@pytest.mark.parametrize("ratio", (0.5, 1.0))
def test_noisy_compact_chain_keeps_independent_source_memberships(
    peak: float, separation: float, ratio: float
) -> None:
    """Coarse context and faint companions do not define one source."""
    yy, xx = np.mgrid[:81, :145]
    noise = gaussian_filter(
        np.random.default_rng(618).normal(size=yy.shape), 1
    )
    noise /= noise.std()
    centers = (
        (40.0, 40.0),
        (40 + separation, 40.0),
        (40 + 2 * separation, 40.0),
    )
    signal = noise.copy()
    for index, (x, y) in enumerate(centers):
        signal += (
            peak
            * (ratio if index == 1 else 1.0)
            * np.exp(-0.5 * (((xx - x) / 1.7) ** 2 + ((yy - y) / 1.7) ** 2))
        )
    products = _products(signal)
    association = products.source_association
    assert association is not None
    owners = {
        member: source.source_id
        for source in association.memberships
        for member in source.component_ids
    }
    detected = []
    for center in centers:
        # Below-threshold injected companions are not guaranteed detections.
        if center == centers[1] and peak * ratio < 5:
            continue
        component = min(
            association.components,
            key=lambda row: np.linalg.norm(
                np.asarray(row.centroid_yx)[::-1] - center
            ),
        )
        assert (
            np.linalg.norm(np.asarray(component.centroid_yx)[::-1] - center)
            < 4
        )
        detected.append(owners[component.component_id])
    assert len(set(detected)) == len(detected)


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
    memberships = dict(enumerate(association.memberships, start=1))
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
        require_signed_aperture=True,
    )
    assert "ambiguous-multiscale-parent" in result[0].quality_flags
    with pytest.raises(ValueError, match="identity is malformed"):
        product_builder._reconstructed_source_rows(
            (products.catalogue[0],),
            products.component_catalogue,
            memberships,
            association,
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


def _review() -> ContinuumScienceProfile:
    """Load the installed reviewed continuum profile fixture."""
    return load_continuum_science_profile(
        (
            _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
        ).read_bytes()
    )


def _configured_products(
    signal: np.ndarray,
    header: fits.Header,
) -> ContinuumProducts | None:
    """Run the tiled detection pass and the composition it feeds."""
    review = _review()
    beam = BeamShapePixels(4.0, 4.0, 0.0)
    config = SourceFinderConfig(5.0, 3.0, 7)
    background = np.zeros_like(signal)
    rms = np.ones_like(signal)
    with TemporaryDirectory() as directory:
        published = publish_continuum_inputs(
            np.asarray(signal, dtype=np.float64),
            np.ones(signal.shape, dtype=np.bool_),
            background,
            rms,
            beam=beam,
            review=configured_science_profile(review, config),
            work_directory=Path(directory),
            header=header,
            config=config,
        )
        valid = (
            np.isfinite(signal) & np.isfinite(background) & np.isfinite(rms)
        )
        return build_configured_continuum_products(
            valid,
            valid & (rms > 0.0),
            header,
            multiscale=published.multiscale,
            labels=published.labels,
            topology=published.topology,
            measurements=published.measurements,
            association=published.association,
            hierarchy=published.hierarchy,
            source_labels=published.source_labels,
            source_measurement_labels=(published.source_measurement_labels),
            component_rows=published.component_rows,
            source_rows=published.source_rows,
            source_positions=published.source_positions,
            component_local_rms=published.component_local_rms,
            source_local_rms=published.source_local_rms,
        )


def _products(signal: np.ndarray) -> ContinuumProducts:
    """Exercise the complete configured composition with analytic noise."""
    result = _configured_products(signal, _header(signal.shape))
    assert result is not None
    return result


def test_missing_optional_beam_angle_uses_zero_position_angle() -> None:
    """FITS permits a zero-angle beam without an explicit BPA card."""
    yy, xx = np.mgrid[:33, :41]
    signal = 10 * np.exp(-((xx - 20) ** 2 + (yy - 16) ** 2) / 8)
    header = _header(signal.shape)
    del header["BPA"]
    products = _configured_products(signal, header)
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
                for row in result.component_catalogue
            ],
            0,
        )
    )
    # Components retain whole-model parameters; sources now use apertures.
    # An undefined circular angle must not force a biased beam-sized model.
    ordered = sorted(
        zip(positions, result.component_catalogue, strict=True),
        key=lambda pair: pair[0][0],
    )
    for (position, row), center in zip(ordered, centers, strict=True):
        assert row.right_ascension_error_degrees is not None
        assert row.declination_error_degrees is not None
        x_error = (
            row.right_ascension_error_degrees
            * 3600
            * np.cos(np.deg2rad(row.declination_degrees))
        )
        y_error = row.declination_error_degrees * 3600
        assert abs(position[0] - center) <= 3 * x_error
        assert abs(position[1] - 48) <= 3 * y_error
        np.testing.assert_allclose(position, (center, 48), atol=1e-3)
    beam_area = np.pi * 16.0 / (4.0 * np.log(2.0))
    expected_flux = sorted(
        amplitude * 8 * np.pi / beam_area for amplitude in amplitudes
    )
    for row, truth_flux in zip(
        sorted(
            result.component_catalogue, key=lambda row: row.integrated_flux_jy
        ),
        expected_flux,
        strict=True,
    ):
        assert row.integrated_flux_error_jy is not None
        assert (
            abs(row.integrated_flux_jy - truth_flux)
            <= 3 * row.integrated_flux_error_jy
        )
        assert row.integrated_flux_jy == pytest.approx(truth_flux, rel=1e-3)
    # Source apertures divide the observed plane, not the infinite Gaussian
    # tails. Their sum must recover the same light without double counting.
    assert sum(
        row.integrated_flux_jy for row in result.catalogue
    ) == pytest.approx(
        float(np.sum(signal)) / beam_area,
        rel=1e-3,
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
    # The source's flux is its components' summed fitted flux, but the
    # source itself still claims no Gaussian shape of its own.
    assert source_disposition.estimator == "summed-fitted-component-flux"
    assert (
        "original-pixel-gaussian-model"
        not in result.catalogue[0].quality_flags
    )
    assert result.catalogue[0].fitted_shape is None
    assert result.catalogue[0].deconvolution_status == "unavailable"


def test_valid_fit_survives_unavailable_aperture_moment_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing auxiliary moment row cannot erase a measured Gaussian.

    The source rows are published by their own round now, so an absent one
    reaches the composition as an empty shard rather than as a builder that
    measured nothing.
    """

    original = tiled_detection.publish_segment_rows

    def missing_source_rows(*args: Any, **kwargs: Any):
        rows, local_rms, positions = original(*args, **kwargs)
        if kwargs["aperture_tie_policy"] == "canonical-source":
            return (), local_rms, positions
        return rows, local_rms, positions

    monkeypatch.setattr(
        tiled_detection, "publish_segment_rows", missing_source_rows
    )
    yy, xx = np.mgrid[:65, :65]
    signal = 10 * np.exp(-((xx - 32) ** 2 / 8 + (yy - 32) ** 2 / 5))
    result = _products(signal)
    assert len(result.component_catalogue) == 1
    assert result.component_catalogue[0].integrated_flux_jy > 0.0
    assert not result.catalogue
    assert {
        item.object_kind: item.status
        for item in result.measurement_dispositions
    } == {
        "component": "measured",
        "source": "unavailable",
    }


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


def test_rejected_ellipse_keeps_source_photometry_and_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A numerical rejection is not permission to erase a detected source."""
    yy, xx = np.mgrid[:49, :65]
    signal = 100 * np.exp(
        -0.5 * (((xx - 32.3) / 6) ** 2 + ((yy - 24.1) / 2) ** 2)
    )
    baseline = _products(signal)
    assert len(baseline.catalogue) == len(baseline.component_catalogue) == 1
    original = component_measurement.fit_compact_gaussian_mixture

    def limited_ellipse(
        compact: Any,
        moments: Any,
        geometry: Any,
        config: CompactGaussianFitConfig,
    ) -> tuple[CompactGaussianFitResult, ...]:
        # Exercise the actual fit with a stricter declared test-only ratio.
        # Rotate the initializer so the optimizer uses the exchanged axes
        # that formerly escaped the gate. No fabricated failed fit is used.
        assert all(
            isinstance(moment, ValidMomentMeasurement) for moment in moments
        )
        rotated = tuple(
            replace(
                moment,
                initializer=replace(
                    moment.initializer,
                    major_axis_angle_degrees=(
                        moment.initializer.major_axis_angle_degrees + 90
                    ),
                ),
            )
            for moment in moments
        )
        return original(
            compact,
            rotated,
            geometry,
            replace(config, model_selection="free-only", maximum_axis_ratio=2),
        )

    monkeypatch.setattr(
        component_measurement, "fit_compact_gaussian_mixture", limited_ellipse
    )
    rejected = _products(signal)
    assert len(rejected.catalogue) == 1
    assert not rejected.component_catalogue
    assert rejected.catalogue[0].integrated_flux_jy == pytest.approx(
        baseline.catalogue[0].integrated_flux_jy
    )
    np.testing.assert_array_equal(
        rejected.measurement_component_labels,
        baseline.measurement_component_labels,
    )
    disposition = next(
        row
        for row in rejected.measurement_dispositions
        if row.object_kind == "component"
    )
    assert disposition.status == "unavailable"
    assert disposition.reason == "fit-invalid-result"
    assert not disposition.catalogue_row_published
    assert disposition.fit_diagnostics is not None
    assert (
        type(disposition).model_validate_json(disposition.model_dump_json())
        == disposition
    )


@pytest.mark.parametrize("center_xy", ((32.3, 24.1), (0.7, 24.1), (0.7, 0.9)))
def test_inadequate_beam_fallback_keeps_source_not_gaussian(
    monkeypatch: pytest.MonkeyPatch,
    center_xy: tuple[float, float],
) -> None:
    """A failed resolved ellipse is not evidence for an unresolved source.

    Limit the test-only axis ratio to exercise a real rejected free fit and
    real beam fallback on independent analytic pixels, not campaign seeds.
    """
    yy, xx = np.mgrid[:49, :65]
    signal = 100 * np.exp(
        -0.5
        * (((xx - center_xy[0]) / 6) ** 2 + ((yy - center_xy[1]) / 2) ** 2)
    )
    baseline = _products(signal)
    original = component_measurement.fit_compact_gaussian_mixture

    def limited_ellipse(
        compact: Any,
        moments: Any,
        geometry: Any,
        config: CompactGaussianFitConfig,
    ) -> tuple[CompactGaussianFitResult, ...]:
        return original(
            compact,
            moments,
            geometry,
            replace(
                config, model_selection="beam-or-free", maximum_axis_ratio=2
            ),
        )

    monkeypatch.setattr(
        component_measurement, "fit_compact_gaussian_mixture", limited_ellipse
    )
    rejected = _products(signal)
    disposition = next(
        row
        for row in rejected.measurement_dispositions
        if row.object_kind == "component"
    )
    assert disposition.fit_diagnostics is not None
    assert disposition.fit_diagnostics.model_identity == "beam-constrained"
    assert (
        disposition.fit_diagnostics.fallback_reason
        == "free-model-invalid-result"
    )
    assert not rejected.component_catalogue
    assert disposition.status == "unavailable"
    assert disposition.reason == "fit-model-inadequate"
    assert not disposition.catalogue_row_published
    assert len(rejected.catalogue) == len(baseline.catalogue) == 1
    # The aperture is what the rejected fit cannot disturb. The source flux
    # itself moves by design: with no fitted component to sum, the source
    # falls back to that aperture and says so.
    assert rejected.catalogue[0].association_integrated_flux_jy == (
        pytest.approx(baseline.catalogue[0].association_integrated_flux_jy)
    )
    assert rejected.catalogue[0].integrated_flux_jy == pytest.approx(
        rejected.catalogue[0].association_integrated_flux_jy
    )
    assert (
        "aperture-flux-without-fitted-component"
        in rejected.catalogue[0].quality_flags
    )
    assert (
        "aperture-flux-without-fitted-component"
        not in baseline.catalogue[0].quality_flags
    )
    np.testing.assert_array_equal(
        rejected.measurement_component_labels,
        baseline.measurement_component_labels,
    )
    assert (
        type(disposition).model_validate_json(disposition.model_dump_json())
        == disposition
    )


@pytest.mark.parametrize(
    "fallback_reason",
    (
        "free-model-bound-contact",
        "free-model-ill-conditioned",
        "free-model-non-convergence",
        "free-model-invalid-result",
    ),
)
@pytest.mark.parametrize("center_xy", ((32.3, 24.1), (0.7, 24.1), (0.7, 0.9)))
@pytest.mark.parametrize("invalid_pixel", (False, True))
def test_valid_point_fallback_survives_free_failure(
    monkeypatch: pytest.MonkeyPatch,
    fallback_reason: str,
    center_xy: tuple[float, float],
    invalid_pixel: bool,
) -> None:
    """Numerical free-model failure cannot forbid an adequate point model."""
    yy, xx = np.mgrid[:49, :65]
    signal = 50 * np.exp(
        -4
        * np.log(2)
        * ((xx - center_xy[0]) ** 2 + (yy - center_xy[1]) ** 2)
        / 16
    )
    if invalid_pixel:
        signal[round(center_xy[1]), round(center_xy[0])] = np.nan

    def failed_free(*_args: Any, **_kwargs: Any) -> str:
        return fallback_reason

    monkeypatch.setattr(gaussian_fitting, "_free_fallback_reason", failed_free)
    result = _products(signal)
    assert len(result.component_catalogue) == len(result.catalogue) == 1
    component = result.component_catalogue[0]
    assert component.integrated_flux_jy == pytest.approx(50, rel=0.001)
    pixel = WCS(_header(signal.shape)).celestial.all_world2pix(
        [[component.right_ascension_degrees, component.declination_degrees]], 0
    )[0]
    np.testing.assert_allclose(pixel, center_xy, atol=0.001)
    disposition = next(
        row
        for row in result.measurement_dispositions
        if row.object_kind == "component"
    )
    assert disposition.status == "measured"
    assert disposition.fit_diagnostics is not None
    assert disposition.fit_diagnostics.fallback_reason == fallback_reason


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
    assert result.catalogue[0].fitted_shape is None
    # The source claims no shape of its own, but its flux is its component's
    # fitted flux, so it carries that component's uncertainty.
    assert result.catalogue[0].integrated_flux_error_jy == pytest.approx(
        result.component_catalogue[0].integrated_flux_error_jy
    )
    for row in result.component_catalogue:
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
    assert source.estimator == "summed-fitted-component-flux"
    beam_area = np.pi * 16 / (4 * np.log(2))
    truth_flux = float(np.sum(core + halo)) / beam_area
    # The aperture retention floor remains binding on the aperture, which is
    # still published. The source flux no longer measures it.
    assert result.catalogue[0].association_integrated_flux_jy >= (
        0.9 * truth_flux
    )
    # The 23 September definition costs this morphology most of its flux: the
    # fits describe the compact core and no fit describes the diffuse halo,
    # so the summed flux is far below the emission the aperture retains.
    # PyBDSF sums Gaussians the same way. Documented, not corrected; the M1
    # calibration population contains no extended emission.
    assert result.catalogue[0].integrated_flux_jy < 0.5 * truth_flux


@pytest.mark.parametrize("opening", (np.pi / 2, np.pi))
@pytest.mark.parametrize("asymmetric", (False, True))
def test_open_arc_keeps_its_components_and_single_flux_owner(
    opening: float, asymmetric: bool
) -> None:
    """A hole is not required to associate connected curved emission.

    Association needs each component's tangential elongation to exceed three
    calibrated standard errors. In the asymmetric arcs, one component's
    evidence is 2.5 to 3 sigma, so it stays a separate source; the arc's flux
    is still owned exactly once.
    """
    yy, xx = np.mgrid[:97, :97]
    radius = np.hypot(xx - 48, yy - 48)
    angle = np.arctan2(yy - 48, xx - 48)
    envelope = np.clip((np.pi - opening / 2 - np.abs(angle)) / 0.3, 0, 1)
    signal = 8 * np.exp(-0.5 * ((radius - 18) / 2) ** 2) * envelope
    signal *= 1 + 0.6 * np.cos(6 * angle)
    if asymmetric:
        signal *= 1 + 0.4 * np.sin(angle)
    products = _products(signal)
    truth_flux = float(signal.sum()) / (np.pi * 16 / (4 * np.log(2)))
    if asymmetric:
        assert len(products.catalogue) == 3
        # Ownership is what this guards: the arc's emission is apportioned
        # across the sources exactly once, which the apertures measure
        # exactly. The summed fitted flux carries the few per cent each
        # Gaussian adds by integrating beyond the observed arc.
        assert sum(
            source.association_integrated_flux_jy or 0.0
            for source in products.catalogue
        ) == pytest.approx(truth_flux, rel=0.05)
        assert sum(
            source.integrated_flux_jy for source in products.catalogue
        ) == pytest.approx(truth_flux, rel=0.10)
        return
    assert len(products.catalogue) == 1
    assert len(products.component_catalogue) >= 3
    unavailable = [
        row
        for row in products.measurement_dispositions
        if row.object_kind == "component" and row.status == "unavailable"
    ]
    assert all(row.reason == "fit-model-inadequate" for row in unavailable)
    assert all(not row.catalogue_row_published for row in unavailable)
    assert products.catalogue[0].component_count == len(
        products.component_catalogue
    ) + len(unavailable)
    assert products.catalogue[0].association_integrated_flux_jy == (
        pytest.approx(truth_flux, rel=0.05)
    )
    assert products.catalogue[0].integrated_flux_jy == pytest.approx(
        truth_flux, rel=0.10
    )


def test_merge_attribution_does_not_change_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collecting optional provenance cannot alter a positive morphology."""
    yy, xx = np.mgrid[:97, :97]
    radius = np.hypot(xx - 48, yy - 48)
    angle = np.arctan2(yy - 48, xx - 48)
    envelope = np.clip((3 * np.pi / 4 - np.abs(angle)) / 0.3, 0, 1)
    signal = 8 * np.exp(-0.5 * ((radius - 18) / 2) ** 2) * envelope
    signal *= 1 + 0.6 * np.cos(6 * angle)
    evidence_kind = "resolved-open-arc"
    function = "_resolved_open_arc_groups"
    baseline = _products(signal)
    assert any(
        item.reason == evidence_kind
        for row in baseline.measurement_dispositions
        for item in row.association_evidence
    )
    original = getattr(component_measurement, function)

    def without_evidence(*args: Any, **kwargs: Any):
        kwargs["evidence"] = None
        return original(*args, **kwargs)

    monkeypatch.setattr(component_measurement, function, without_evidence)
    without = _products(signal)
    assert without.catalogue == baseline.catalogue
    assert without.component_catalogue == baseline.component_catalogue
    assert without.source_association == baseline.source_association
    assert all(
        item.reason != evidence_kind
        for row in without.measurement_dispositions
        for item in row.association_evidence
    )


@pytest.mark.parametrize(
    "bad",
    (np.ones((2, 3)), np.full((3, 3), -1), np.ones((3, 3)) * 0.5),
)
def test_centroid_owner_domain_rejects_invalid_labels(bad: np.ndarray) -> None:
    with pytest.raises(ValueError, match="aligned non-negative integers"):
        product_builder._validated_centroid_labels(
            bad, np.ones((3, 3), dtype=np.int64)
        )


def test_centroid_owner_domain_rejects_foreign_owner() -> None:
    with pytest.raises(ValueError, match="subset of aperture ownership"):
        product_builder._validated_centroid_labels(
            np.full((3, 3), 2), np.ones((3, 3), dtype=np.int64)
        )


@pytest.mark.parametrize("mask_corner", (False, True))
@pytest.mark.parametrize("background_offset", (0.0, 0.5))
def test_centroid_attribution_separates_mask_background_and_aperture(
    mask_corner: bool,
    background_offset: float,
) -> None:
    """Retain one-factor effects without moving the source into flux wings."""
    yy, xx = np.mgrid[:9, :11]
    signal = 2 + 10 * np.exp(-((xx - 7) ** 2 + (yy - 4) ** 2) / 2)
    background = np.full(signal.shape, background_offset)
    valid = np.ones(signal.shape, dtype=bool)
    if mask_corner:
        valid[3, 6] = False
    position_labels = np.zeros(signal.shape, dtype=np.int64)
    position_labels[3:6, 6:9] = 1
    aperture_labels = position_labels.copy()
    aperture_labels[4, 1:6] = 1
    denoised = np.full(signal.shape, 2.0)
    records = {}
    rows = product_builder.build_hebog_segment_catalogue(
        signal,
        background,
        valid,
        aperture_labels,
        _header(signal.shape),
        beam_major_fwhm_pixels=4.0,
        beam_minor_fwhm_pixels=4.0,
        position_labels=position_labels,
        position_signal_jy_per_beam=denoised,
        position_diagnostics=records,
    )
    record = records[1]
    support = (position_labels == 1) & valid
    residual = signal - background
    expected = tuple(
        float(
            np.sum(grid[support] * residual[support])
            / np.sum(residual[support])
        )
        for grid in (xx, yy)
    )
    assert record.signed_original_xy == pytest.approx(expected)
    assert record.denoised_xy == pytest.approx(
        (xx[support].mean(), yy[support].mean())
    )
    assert record.position_pixel_count == 9 - int(mask_corner)
    assert record.aperture_pixel_count > record.position_pixel_count
    assert record.aperture_background_mean == background_offset
    assert record.aperture_signed_flux_jy == rows[0].integrated_flux_jy
    assert record.selected_xy == record.denoised_xy


def test_segment_moments_in_a_window_match_the_whole_plane() -> None:
    """A segment's window changes the work, not the measured shape.

    Moments over the whole plane for each segment cost image size times
    segment count; the windowed result must be identical, in the plane's
    pixel frame.
    """
    generator = np.random.default_rng(2026091903)
    residual = generator.uniform(-0.1, 0.4, (70, 90))
    support = np.zeros(residual.shape, dtype=np.bool_)
    support[52:60, 61:72] = generator.random((8, 11)) < 0.8
    residual[52:60, 61:72] += 1.5

    whole_plane = _segment_pixel_moment_covariance(residual, support)
    crop = (slice(52, 60), slice(61, 72))
    windowed = _segment_pixel_moment_covariance(
        residual[crop],
        support[crop],
        window=SegmentWindow(
            origin_yx=(52, 61), plane_shape_yx=residual.shape
        ),
    )

    assert whole_plane is not None
    assert windowed is not None
    assert windowed[0] == whole_plane[0]
    assert np.array_equal(windowed[1], whole_plane[1])


def test_a_shape_the_local_geometry_cannot_describe_is_unavailable() -> None:
    """A moment no ellipse can describe is reported, not raised.

    Measuring a moment and transforming it are separate steps, so a
    covariance the tangent plane cannot turn into a positive ellipse reaches
    the shape step on its own. It must be reported exactly as an unmeasurable
    segment is, because a catalogue row still exists for it.
    """
    transform = LocalTangentPlaneTransform(
        position=SkyPosition(
            right_ascension_degrees=10.0,
            declination_degrees=-30.0,
            right_ascension_error_degrees=None,
            declination_error_degrees=None,
        ),
        jacobian_degrees_per_pixel=((1.0 / 3600.0, 0.0), (0.0, 1.0 / 3600.0)),
    )
    beam = RestoringBeam(
        major_fwhm_degrees=0.004,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=0.0,
    )
    degenerate = np.zeros((2, 2), dtype=np.float64)

    fields = moment_shape_fields_at(
        ((5.0, 5.0), degenerate), transform=transform, beam_icrs=beam
    )

    assert fields == unavailable_moment_shape_fields()
    assert fields["fitted_shape"] is None
    assert fields["deconvolution_status"] == "unavailable"
