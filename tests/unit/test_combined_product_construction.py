"""Contracts for final Phase 5 combined catalogue and mask construction."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.combined_catalogue import (
    complete_combined_catalogue_state,
)
from hebog.algorithms.combined_identity import CombinedIdentityResult
from hebog.algorithms.combined_products import (
    CombinedProductConstructionError,
    build_combined_diagnostics,
    combine_source_filtering_mask_blocks,
    construct_combined_catalogue,
)
from hebog.data_models.catalogue_construction import (
    CompletedCompactCatalogue,
)
from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.data_models.multiscale import (
    CombinedCatalogueShard,
    CombinedIslandDisposition,
    CombinedIslandIdentity,
    CompletedCombinedCatalogueState,
    CrossScaleAssociation,
    ExtendedEmissionMeasurement,
    ExtendedSourceIdentity,
)
from hebog.data_models.source_finding import (
    ContinuumSourceFindingDiagnostics,
    SourceFindingDiagnostics,
)


def _metadata() -> ImageMetadata:
    """Return one simple ICRS image contract."""
    return ImageMetadata(
        shape_yx=(4, 5),
        unit="Jy/beam",
        beam=RestoringBeam(0.003, 0.002, 0.0),
        celestial_wcs=CelestialWcs(
            fits_header=(
                "WCSAXES =                    2\n"
                "CRPIX1  =                  3.0\n"
                "CRPIX2  =                  3.0\n"
                "CDELT1  =               -0.001\n"
                "CDELT2  =                0.001\n"
                "CUNIT1  = 'deg     '\n"
                "CUNIT2  = 'deg     '\n"
                "CTYPE1  = 'RA---TAN'\n"
                "CTYPE2  = 'DEC--TAN'\n"
                "CRVAL1  =                180.0\n"
                "CRVAL2  =                -30.0\n"
                "LONPOLE =                180.0\n"
                "LATPOLE =                -30.0\n"
                "MJDREF  =                  0.0\n"
                "RADESYS = 'ICRS    '"
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )


def _compact_catalogue() -> CompletedCompactCatalogue:
    """Return one completed Phase 4 compact catalogue."""
    position = SkyPosition(
        right_ascension_degrees=180.0,
        declination_degrees=-30.0,
        right_ascension_error_degrees=None,
        declination_error_degrees=None,
    )
    spectrum = SpectralModel(
        kind="reference-frequency-only",
        reference_frequency_hz=150_000_000.0,
        coefficients=(),
    )
    flux = FluxMeasurement(
        peak_flux_jy_per_beam=0.02,
        peak_flux_error_jy_per_beam=None,
        integrated_flux_jy=0.05,
        integrated_flux_error_jy=None,
        local_rms_jy_per_beam=0.001,
    )
    shape = GaussianShape(
        major_fwhm_degrees=0.003,
        minor_fwhm_degrees=0.002,
        position_angle_degrees=0.0,
        major_fwhm_error_degrees=None,
        minor_fwhm_error_degrees=None,
        position_angle_error_degrees=None,
    )
    source = SourceCandidate(
        source_id="source-compact",
        island_id="island-compact",
        position=position,
        flux=flux,
        spectral_model=spectrum,
        fitted_shape=shape,
        deconvolved_shape=None,
        quality_flags=("unresolved",),
    )
    component = GaussianComponent(
        gaussian_component_id="gaussian-compact",
        source_id=source.source_id,
        island_id=source.island_id,
        position=position,
        flux=flux,
        spectral_model=spectrum,
        fitted_shape=shape,
        deconvolved_shape=None,
        quality_flags=("unresolved",),
    )
    catalogue = SourceCatalogue.create(
        catalogue_id="catalogue-combined",
        coordinate_frame="icrs",
        position_epoch="J2000",
        reference_frequency_hz=150_000_000.0,
        islands=(
            Island(
                island_id="island-compact",
                pixel_count=8,
                integrated_flux_jy=0.05,
                integrated_flux_error_jy=None,
                local_rms_jy_per_beam=0.001,
                mean_brightness_jy_per_beam=0.004,
            ),
        ),
        sources=(source,),
        gaussian_components=(component,),
    )
    return CompletedCompactCatalogue(catalogue, 1, 0, 1)


def _association() -> CrossScaleAssociation:
    """Return one mixed compact/extended association."""
    return CrossScaleAssociation(
        association_id="scale-association-diffuse",
        scale_detection_ids=("scale-detection-fine", "scale-detection-wide"),
        compact_source_ids=("source-compact",),
        selected_scale_detection_id="scale-detection-wide",
        contributing_scale_orders=(1, 2),
        relationship="contains-compact-support",
    )


def _measurement() -> ExtendedEmissionMeasurement:
    """Return one original-pixel irregular-source measurement."""
    return ExtendedEmissionMeasurement(
        association_id="scale-association-diffuse",
        centroid_xy=(2.0, 1.5),
        centroid_kind="detected-segment-flux-centroid",
        peak_position_xy=(2, 2),
        peak_flux_jy_per_beam=0.04,
        host_position_claim=False,
        position_covariance_pixels_squared=None,
        position_uncertainty_status="unavailable",
        integrated_flux_jy=0.2,
        integrated_flux_error_jy=0.02,
        local_rms_jy_per_beam=0.002,
        support_pixel_count=12,
        major_extent_beams=3.0,
        minor_extent_beams=1.5,
        position_angle_degrees=25.0,
        visible_model_fraction=0.9,
        flux_uncertainty_status="available",
    )


def _compact_only_inputs() -> tuple[
    CombinedIdentityResult,
    CompletedCombinedCatalogueState,
]:
    """Return exact compact identities and terminal completion."""
    identities = CombinedIdentityResult(
        islands=(
            CombinedIslandIdentity(
                island_id="island-compact",
                compact_island_ids=("island-compact",),
                compact_source_ids=("source-compact",),
                association_ids=(),
                extended_source_ids=(),
                gaussian_component_ids=("gaussian-compact",),
            ),
        ),
        extended_sources=(),
    )
    state = complete_combined_catalogue_state(
        catalogue_id="catalogue-combined",
        shards=(
            CombinedCatalogueShard(
                accepted_island_ids=("island-compact",),
                deferred_island_ids=(),
                dispositions=(
                    CombinedIslandDisposition(
                        island_id="island-compact",
                        status="retained-compact",
                        source_ids=("source-compact",),
                        association_ids=(),
                        reason=None,
                    ),
                ),
                omissions=(),
            ),
        ),
        maximum_state_records=4,
    )
    return identities, state


def _mixed_inputs() -> tuple[
    CombinedIdentityResult,
    CompletedCombinedCatalogueState,
]:
    """Return one mixed identity and accepted terminal completion."""
    identities = CombinedIdentityResult(
        islands=(
            CombinedIslandIdentity(
                island_id="combined-island-mixed",
                compact_island_ids=("island-compact",),
                compact_source_ids=("source-compact",),
                association_ids=("scale-association-diffuse",),
                extended_source_ids=("source-extended-diffuse",),
                gaussian_component_ids=("gaussian-compact",),
            ),
        ),
        extended_sources=(
            ExtendedSourceIdentity(
                association_id="scale-association-diffuse",
                island_id="combined-island-mixed",
                source_id="source-extended-diffuse",
            ),
        ),
    )
    state = complete_combined_catalogue_state(
        catalogue_id="catalogue-combined",
        shards=(
            CombinedCatalogueShard(
                accepted_island_ids=("combined-island-mixed",),
                deferred_island_ids=(),
                dispositions=(
                    CombinedIslandDisposition(
                        island_id="combined-island-mixed",
                        status="accepted-multiscale",
                        source_ids=("source-compact",),
                        association_ids=("scale-association-diffuse",),
                        reason=None,
                    ),
                ),
                omissions=(),
            ),
        ),
        maximum_state_records=4,
    )
    return identities, state


def test_compact_only_construction_preserves_the_exact_catalogue() -> None:
    """No accepted extended source may reconstruct Phase 4 records."""
    compact = _compact_catalogue()
    identities, state = _compact_only_inputs()

    combined = construct_combined_catalogue(
        compact,
        state=state,
        identities=identities,
        associations=(),
        measurements=(),
        metadata=_metadata(),
    )

    assert combined.compact_only_preserved is True
    assert combined.catalogue is compact.catalogue
    assert combined.source_provenance == ()
    diagnostics = build_combined_diagnostics(
        run_id="run-combined",
        combined=combined,
        rms_scientific_status="valid",
    )
    assert isinstance(diagnostics, SourceFindingDiagnostics)
    assert not isinstance(diagnostics, ContinuumSourceFindingDiagnostics)


def test_mixed_construction_retains_rows_and_adds_irregular_source() -> None:
    """Shared-island composition never fabricates an extended Gaussian."""
    identities, state = _mixed_inputs()

    combined = construct_combined_catalogue(
        _compact_catalogue(),
        state=state,
        identities=identities,
        associations=(_association(),),
        measurements=(_measurement(),),
        metadata=_metadata(),
    )

    assert combined.compact_only_preserved is False
    assert len(combined.catalogue.islands) == 1
    assert len(combined.catalogue.sources) == 2
    assert len(combined.catalogue.gaussian_components) == 1
    compact, extended = combined.catalogue.sources
    assert compact.source_id == "source-compact"
    assert compact.island_id == "combined-island-mixed"
    assert extended.source_id == "source-extended-diffuse"
    assert extended.island_id == "combined-island-mixed"
    assert extended.fitted_shape is None
    assert extended.flux.peak_flux_jy_per_beam == 0.04
    assert extended.flux.integrated_flux_jy == 0.2
    assert extended.deconvolved_major_fwhm_degrees == pytest.approx(0.009)
    assert "segment-moment-extent" in extended.quality_flags
    assert combined.catalogue.islands[0].integrated_flux_jy == pytest.approx(
        0.25
    )
    assert combined.source_provenance[0].scale_detection_ids == (
        "scale-detection-fine",
        "scale-detection-wide",
    )
    diagnostics = build_combined_diagnostics(
        run_id="run-combined",
        combined=combined,
        rms_scientific_status="valid",
    )
    assert isinstance(diagnostics, ContinuumSourceFindingDiagnostics)
    assert diagnostics.extended_source_count == 1
    assert diagnostics.source_provenance == combined.source_provenance


def test_construction_fails_closed_on_missing_or_conflicting_evidence() -> (
    None
):
    """Stable ordering cannot repair incomplete scientific composition."""
    identities, state = _mixed_inputs()
    with pytest.raises(CombinedProductConstructionError, match="measurement"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=state,
            identities=identities,
            associations=(_association(),),
            measurements=(),
            metadata=_metadata(),
        )
    with pytest.raises(CombinedProductConstructionError, match="terminal"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=state,
            identities=replace(
                identities,
                islands=(
                    identities.islands[0].model_copy(
                        update={"island_id": "combined-island-other"}
                    ),
                ),
            ),
            associations=(_association(),),
            measurements=(_measurement(),),
            metadata=_metadata(),
        )
    with pytest.raises(CombinedProductConstructionError, match="catalogue"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=state.model_copy(
                update={
                    "state": state.state.model_copy(
                        update={"catalogue_id": "catalogue-other"}
                    )
                }
            ),
            identities=identities,
            associations=(_association(),),
            measurements=(_measurement(),),
            metadata=_metadata(),
        )
    with pytest.raises(CombinedProductConstructionError, match="provenance"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=state,
            identities=identities,
            associations=(),
            measurements=(_measurement(),),
            metadata=_metadata(),
        )
    with pytest.raises(CombinedProductConstructionError, match="identities"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=state,
            identities=replace(identities, extended_sources=()),
            associations=(_association(),),
            measurements=(_measurement(),),
            metadata=_metadata(),
        )


def test_construction_rejects_invalid_metadata_and_duplicate_provenance() -> (
    None
):
    """Physical metadata and association identities are exact inputs."""
    identities, state = _mixed_inputs()
    compact = _compact_catalogue()

    with pytest.raises(CombinedProductConstructionError, match="Jy/beam"):
        construct_combined_catalogue(
            compact,
            state=state,
            identities=identities,
            associations=(_association(),),
            measurements=(_measurement(),),
            metadata=replace(_metadata(), unit="Jy/pixel"),
        )
    with pytest.raises(CombinedProductConstructionError, match="frequency"):
        construct_combined_catalogue(
            compact,
            state=state,
            identities=identities,
            associations=(_association(),),
            measurements=(_measurement(),),
            metadata=replace(
                _metadata(),
                reference_frequency_hz=160_000_000.0,
            ),
        )
    with pytest.raises(CombinedProductConstructionError, match="unique"):
        construct_combined_catalogue(
            compact,
            state=state,
            identities=identities,
            associations=(_association(), _association()),
            measurements=(_measurement(),),
            metadata=_metadata(),
        )


def test_terminal_dispositions_must_agree_with_combined_identity() -> None:
    """Retained and accepted terminal states cannot relabel source members."""
    compact_identities, compact_state = _compact_only_inputs()
    retained_disposition = CombinedIslandDisposition(
        island_id="island-compact",
        status="retained-compact",
        source_ids=("source-other",),
        association_ids=(),
        reason=None,
    )
    invalid_compact_state = compact_state.model_copy(
        update={
            "state": compact_state.state.model_copy(
                update={"dispositions": (retained_disposition,)}
            )
        }
    )
    with pytest.raises(CombinedProductConstructionError, match="retained"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=invalid_compact_state,
            identities=compact_identities,
            associations=(),
            measurements=(),
            metadata=_metadata(),
        )

    mixed_identities, mixed_state = _mixed_inputs()
    accepted_disposition = CombinedIslandDisposition(
        island_id="combined-island-mixed",
        status="accepted-multiscale",
        source_ids=(),
        association_ids=("scale-association-diffuse",),
        reason=None,
    )
    invalid_mixed_state = mixed_state.model_copy(
        update={
            "state": mixed_state.state.model_copy(
                update={"dispositions": (accepted_disposition,)}
            )
        }
    )
    with pytest.raises(CombinedProductConstructionError, match="accepted"):
        construct_combined_catalogue(
            _compact_catalogue(),
            state=invalid_mixed_state,
            identities=mixed_identities,
            associations=(_association(),),
            measurements=(_measurement(),),
            metadata=_metadata(),
        )


def test_rejected_extended_artifact_publishes_no_source_row() -> None:
    """A terminal artifact is excluded without becoming a failed omission."""
    association = CrossScaleAssociation(
        association_id="scale-association-artifact",
        scale_detection_ids=("scale-detection-artifact",),
        compact_source_ids=(),
        selected_scale_detection_id="scale-detection-artifact",
        contributing_scale_orders=(2,),
        relationship="extended-only",
    )
    identities = CombinedIdentityResult(
        islands=(
            CombinedIslandIdentity(
                island_id="combined-island-artifact",
                compact_island_ids=(),
                compact_source_ids=(),
                association_ids=(association.association_id,),
                extended_source_ids=("source-extended-artifact",),
                gaussian_component_ids=(),
            ),
        ),
        extended_sources=(
            ExtendedSourceIdentity(
                association_id=association.association_id,
                island_id="combined-island-artifact",
                source_id="source-extended-artifact",
            ),
        ),
    )
    state = complete_combined_catalogue_state(
        catalogue_id="catalogue-combined",
        shards=(
            CombinedCatalogueShard(
                accepted_island_ids=("combined-island-artifact",),
                deferred_island_ids=(),
                dispositions=(
                    CombinedIslandDisposition(
                        island_id="combined-island-artifact",
                        status="rejected-artifact",
                        source_ids=(),
                        association_ids=(association.association_id,),
                        reason="morphology-artifact",
                    ),
                ),
                omissions=(),
            ),
        ),
        maximum_state_records=4,
    )
    empty = CompletedCompactCatalogue(
        SourceCatalogue.create(
            catalogue_id="catalogue-combined",
            coordinate_frame="icrs",
            position_epoch="J2000",
            reference_frequency_hz=150_000_000.0,
            islands=(),
            sources=(),
            gaussian_components=(),
        ),
        0,
        0,
        0,
    )

    combined = construct_combined_catalogue(
        empty,
        state=state,
        identities=identities,
        associations=(association,),
        measurements=(),
        metadata=_metadata(),
    )

    assert combined.compact_only_preserved is False
    assert combined.catalogue.sources == ()
    assert combined.source_provenance == ()


def test_combined_mask_blocks_are_bounded_and_compact_preserving() -> None:
    """Output masks are a blockwise union with a copy-free compact no-op."""
    compact = (
        np.array([[True, False, False]], dtype=np.bool_),
        np.array([[False, True, False]], dtype=np.bool_),
    )
    extended = (
        np.array([[False, True, False]], dtype=np.bool_),
        np.array([[False, False, True]], dtype=np.bool_),
    )

    preserved = tuple(combine_source_filtering_mask_blocks(compact, None))
    combined = tuple(combine_source_filtering_mask_blocks(compact, extended))

    assert preserved[0] is compact[0]
    assert preserved[1] is compact[1]
    np.testing.assert_array_equal(combined[0], [[True, True, False]])
    np.testing.assert_array_equal(combined[1], [[False, True, True]])
    with pytest.raises(ValueError, match="same number"):
        tuple(combine_source_filtering_mask_blocks(compact, extended[:1]))
    with pytest.raises(TypeError, match="boolean"):
        tuple(
            combine_source_filtering_mask_blocks(
                compact,
                (np.ones((1, 3), dtype=np.uint8), *extended[1:]),
            )
        )
    with pytest.raises(ValueError, match="two-dimensional"):
        tuple(combine_source_filtering_mask_blocks((compact[0][0],), None))
    with pytest.raises(ValueError, match="matching shapes"):
        tuple(
            combine_source_filtering_mask_blocks(
                compact,
                (np.zeros((1, 2), dtype=np.bool_), *extended[1:]),
            )
        )
