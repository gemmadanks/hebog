# pyright: reportMissingTypeStubs=false
"""Fixture-only contracts for the prospective public-finder correction."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.data_models.catalogues import Island, SourceCatalogue
from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.external_runners import file_sha256
from hebog.validation.public_finder_correction import (
    PublicFinderCorrectionContinuumProducts,
    Sdc1SourceFindingRecord,
    build_public_finder_correction_continuum_products,
    build_public_finder_source_reconstruction_continuum_products,
    build_public_moment_source_candidate,
    build_sdc1_source_finding_records,
    public_finder_boundary_refinement_configuration,
    public_finder_correction_candidate_configuration,
    public_finder_mask_measurement_separation_configuration,
    public_finder_source_association_candidate_configuration,
    public_finder_source_hierarchy_parent_construction_configuration,
    public_finder_source_reconstruction_candidate_configuration,
    public_finder_source_reconstruction_root_cause_repair_configuration,
    public_finder_terminal_cycle_eligibility_configuration,
    public_finder_terminal_feature_persistence_configuration,
    public_finder_terminal_parent_correction_configuration,
)
from hebog.validation.publication_snr_repair import (
    public_finder_publication_snr_repair_configuration,
)

_ROOT = Path(__file__).parents[3]


def _resolved_source() -> CatalogueSource:
    """Return one fully characterized synthetic public source."""
    return CatalogueSource(
        identifier="hebog-segment-1",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=2e-3,
        integrated_flux_jy=3e-3,
        association_integrated_flux_jy=4e-3,
        fitted_shape=CatalogueEllipse(
            major_fwhm_degrees=3.0 / 3600.0,
            minor_fwhm_degrees=2.0 / 3600.0,
            position_angle_degrees=25.0,
        ),
        deconvolved_shape=CatalogueEllipse(
            major_fwhm_degrees=2.0 / 3600.0,
            minor_fwhm_degrees=1.0 / 3600.0,
            position_angle_degrees=35.0,
        ),
        deconvolution_status="resolved",
        quality_flags=("segment-moment-equivalent-shape",),
    )


def test_sdc1_source_finding_adapter_maps_only_available_dimensions() -> None:
    """The adapter maps position, intrinsic size, and apparent flux only."""
    record = build_sdc1_source_finding_records((_resolved_source(),))[0]

    assert record.identifier == "hebog-segment-1"
    assert record.right_ascension_degrees == 10.0
    assert record.declination_degrees == -30.0
    assert record.apparent_integrated_flux_jy == 4e-3
    assert record.major_fwhm_arcseconds == pytest.approx(2.0)
    assert record.minor_fwhm_arcseconds == pytest.approx(1.0)
    assert record.position_angle_clockwise_from_west_degrees == pytest.approx(
        125.0
    )
    assert record.size_code == 2
    assert record.core_fraction is None
    assert record.source_class is None
    assert record.official_global_score_eligible is False


def test_moment_record_round_trips_through_canonical_source_catalogue() -> (
    None
):
    """The public shape survives the pipeline-neutral canonical schema."""
    source = _resolved_source()
    candidate = build_public_moment_source_candidate(
        source,
        local_rms_jy_per_beam=1e-4,
        reference_frequency_hz=1.4e9,
    )
    catalogue = SourceCatalogue.create(
        catalogue_id="catalogue-public-correction",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=1.4e9,
        islands=(
            Island(
                island_id="hebog-segment-1",
                pixel_count=20,
                integrated_flux_jy=source.integrated_flux_jy,
                integrated_flux_error_jy=None,
                local_rms_jy_per_beam=1e-4,
                mean_brightness_jy_per_beam=5e-4,
            ),
        ),
        sources=(candidate,),
        gaussian_components=(),
    )

    restored = SourceCatalogue.from_json_bytes(
        catalogue.canonical_json_bytes()
    )

    assert restored == catalogue
    assert restored.sources[0].fitted_shape is not None
    assert restored.sources[0].deconvolved_shape is not None
    assert "segment-moment-equivalent-shape" in (
        restored.sources[0].quality_flags
    )


def test_sdc1_source_finding_adapter_rejects_unavailable_shape() -> None:
    """A partial record cannot silently enter future source-aware scoring."""
    source = CatalogueSource(
        identifier="shape-unavailable",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.0,
        deconvolution_status="unavailable",
        quality_flags=(
            "segment-moment-equivalent-shape",
            "shape-unavailable",
        ),
    )

    with pytest.raises(ValueError, match="resolved moment-equivalent shape"):
        build_sdc1_source_finding_records((source,))


def test_sdc1_source_finding_adapter_preserves_unresolved_state() -> None:
    """A resolution upper limit is explicit rather than an invented ellipse."""
    source = CatalogueSource(
        identifier="unresolved",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.0,
        fitted_shape=CatalogueEllipse(
            major_fwhm_degrees=1.0 / 3600.0,
            minor_fwhm_degrees=1.0 / 3600.0,
            position_angle_degrees=0.0,
        ),
        deconvolution_status="unresolved",
        quality_flags=(
            "segment-moment-equivalent-shape",
            "unresolved",
        ),
    )

    record = build_sdc1_source_finding_records((source,))[0]

    assert record.deconvolution_status == "unresolved"
    assert record.major_fwhm_arcseconds == 0.0
    assert record.minor_fwhm_arcseconds == 0.0
    assert record.position_angle_clockwise_from_west_degrees is None


def test_sdc1_source_finding_adapter_requires_shape_provenance() -> None:
    """A Gaussian fit cannot be mislabeled as the reviewed moment record."""
    source = _resolved_source()
    source = CatalogueSource(
        identifier=source.identifier,
        right_ascension_degrees=source.right_ascension_degrees,
        declination_degrees=source.declination_degrees,
        peak_flux_jy_per_beam=source.peak_flux_jy_per_beam,
        integrated_flux_jy=source.integrated_flux_jy,
        association_integrated_flux_jy=(source.association_integrated_flux_jy),
        fitted_shape=source.fitted_shape,
        deconvolved_shape=source.deconvolved_shape,
        deconvolution_status="resolved",
    )

    with pytest.raises(ValueError, match="provenance"):
        build_sdc1_source_finding_records((source,))
    with pytest.raises(ValueError, match="provenance"):
        build_public_moment_source_candidate(
            source,
            local_rms_jy_per_beam=1e-4,
            reference_frequency_hz=1.4e9,
        )


def test_sdc1_source_finding_adapter_rejects_duplicates_and_partial_axes() -> (
    None
):
    """Future scorer input cannot contain ambiguous identity or morphology."""
    source = _resolved_source()
    with pytest.raises(ValueError, match="identifiers"):
        build_sdc1_source_finding_records((source, source))

    partial = CatalogueSource(
        identifier="major-only",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.0,
        fitted_shape=source.fitted_shape,
        deconvolved_major_fwhm_degrees=1.0 / 3600.0,
        deconvolution_status="major-axis-only",
        quality_flags=(
            "major-axis-only",
            "segment-moment-equivalent-shape",
        ),
    )
    with pytest.raises(ValueError, match="explicit unresolved"):
        build_sdc1_source_finding_records((partial,))


def test_sdc1_record_rejects_nonphysical_manual_construction() -> None:
    """The in-memory boundary remains safe even without a serializer."""
    record = Sdc1SourceFindingRecord(
        identifier="source",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        apparent_integrated_flux_jy=1.0,
        major_fwhm_arcseconds=2.0,
        minor_fwhm_arcseconds=1.0,
        position_angle_clockwise_from_west_degrees=20.0,
        deconvolution_status="resolved",
        size_code=2,
    )
    with pytest.raises(ValueError, match="finite"):
        replace(record, identifier="")
    with pytest.raises(ValueError, match="positive"):
        replace(record, apparent_integrated_flux_jy=0.0)
    with pytest.raises(ValueError, match="coordinates"):
        replace(record, right_ascension_degrees=360.0)
    with pytest.raises(ValueError, match="ordered"):
        replace(
            record,
            major_fwhm_arcseconds=1.0,
            minor_fwhm_arcseconds=2.0,
        )
    with pytest.raises(ValueError, match="complete"):
        replace(
            record,
            position_angle_clockwise_from_west_degrees=None,
        )
    with pytest.raises(ValueError, match="axis-free"):
        replace(record, deconvolution_status="unresolved")
    with pytest.raises(ValueError, match="status"):
        replace(
            record,
            major_fwhm_arcseconds=0.0,
            minor_fwhm_arcseconds=0.0,
            position_angle_clockwise_from_west_degrees=None,
            deconvolution_status=cast(Any, "major-axis-only"),
        )
    with pytest.raises(ValueError, match="explicitly unavailable"):
        replace(record, size_code=cast(Any, 1))


def test_public_correction_configuration_fails_closed_on_malformed_base(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Configuration identity cannot infer a malformed Continuum record."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "post_correction_candidate_configuration",
        return_value={"compact": {}, "continuum": "wrong"},
    )
    contract = tmp_path / "contract.json"
    contract.write_text("{}\n", encoding="utf-8")

    with pytest.raises(TypeError, match="dictionary"):
        public_finder_correction_candidate_configuration(contract, contract)


def test_source_association_configuration_binds_approved_review_and_decision(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The new non-executable identity cannot omit its exact authority."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_correction_candidate_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    pre_review = tmp_path / "pre-review.json"
    decision = tmp_path / "decision.json"
    pre_review.write_text('{"review": 1}\n', encoding="utf-8")
    decision.write_text('{"decision": 1}\n', encoding="utf-8")

    configuration = public_finder_source_association_candidate_configuration(
        tmp_path / "base.json",
        tmp_path / "correction.json",
        pre_review,
        decision,
    )

    assert configuration["compact"] == {"frozen": True}
    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["source_association_policy"] == (
        "undilated-three-sigma-directional-fwhm-complete-link-v1"
    )
    assert continuum["source_association_pre_review_sha256"] == file_sha256(
        pre_review
    )
    assert continuum[
        "source_association_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_source_reconstruction_configuration_binds_all_prospective_policies(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The corrected identity names hierarchy, measurement, mask, and score."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_correction_candidate_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    pre_review = tmp_path / "pre-review.json"
    decision = tmp_path / "decision.json"
    pre_review.write_text('{"review": 1}\n', encoding="utf-8")
    decision.write_text('{"decision": 1}\n', encoding="utf-8")

    configuration = (
        public_finder_source_reconstruction_candidate_configuration(
            tmp_path / "base.json",
            tmp_path / "correction.json",
            pre_review,
            decision,
        )
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["source_reconstruction_policy"] == (
        "undilated-adjacent-scale-unambiguous-common-parent-v1"
    )
    assert continuum["source_measurement_policy"] == (
        "disjoint-source-owned-aperture-moment-v1"
    )
    assert continuum["connected_support_policy"] == (
        "direct-seed-connected-half-beam-multiscale-recovery-v1"
    )
    assert continuum["source_topology_policy"] == (
        "binding-catalogue-source-diagnostic-detection-component-v1"
    )
    assert continuum["source_reconstruction_pre_review_sha256"] == (
        file_sha256(pre_review)
    )
    assert continuum[
        "source_reconstruction_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_root_cause_repair_configuration_binds_activation_authority(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The repaired identity binds both reviews without becoming executable."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_source_reconstruction_candidate_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    root_review = tmp_path / "root-review.json"
    root_decision = tmp_path / "root-decision.json"
    root_review.write_text('{"review": 2}\n', encoding="utf-8")
    root_decision.write_text('{"decision": 2}\n', encoding="utf-8")

    configuration = (
        public_finder_source_reconstruction_root_cause_repair_configuration(
            tmp_path / "base.json",
            tmp_path / "correction.json",
            tmp_path / "source-review.json",
            tmp_path / "source-decision.json",
            root_review,
            root_decision,
        )
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["source_reconstruction_activation_policy"] == (
        "direct-seed-nearest-persistent-common-convergence-v2"
    )
    assert continuum["source_reconstruction_telemetry_policy"] == (
        "array-free-hierarchy-activation-census-v1"
    )
    assert continuum[
        "source_reconstruction_root_cause_pre_review_sha256"
    ] == file_sha256(root_review)
    assert continuum[
        "source_reconstruction_root_cause_implementation_decision_sha256"
    ] == file_sha256(root_decision)


def test_parent_construction_configuration_binds_exact_authority(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The parent identity extends the repair without becoming executable."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_source_reconstruction_root_cause_repair_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    parent_review = tmp_path / "parent-review.json"
    parent_decision = tmp_path / "parent-decision.json"
    parent_review.write_text('{"review": 3}\n', encoding="utf-8")
    parent_decision.write_text('{"decision": 3}\n', encoding="utf-8")

    configuration = (
        public_finder_source_hierarchy_parent_construction_configuration(
            tmp_path / "base.json",
            tmp_path / "correction.json",
            tmp_path / "source-review.json",
            tmp_path / "source-decision.json",
            tmp_path / "root-review.json",
            tmp_path / "root-decision.json",
            parent_review,
            parent_decision,
        )
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["source_hierarchy_parent_construction_policy"] == (
        "b3-footprint-cycle-supported-adjacent-persistent-parent-v1"
    )
    assert continuum["source_hierarchy_parent_telemetry_policy"] == (
        "array-free-scale-parent-candidate-acceptance-census-v1"
    )
    assert continuum[
        "source_hierarchy_parent_construction_pre_review_sha256"
    ] == file_sha256(parent_review)
    assert continuum[
        "source_hierarchy_parent_construction_implementation_decision_sha256"
    ] == file_sha256(parent_decision)


def test_terminal_parent_configuration_binds_the_narrowed_science(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The replacement identity binds both safeguards and their authority."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_source_hierarchy_parent_construction_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    review = tmp_path / "terminal-parent-review.md"
    decision = tmp_path / "terminal-parent-decision.json"
    review.write_text("# review\n", encoding="utf-8")
    decision.write_text('{"decision": 4}\n', encoding="utf-8")

    configuration = public_finder_terminal_parent_correction_configuration(
        tmp_path / "base.json",
        tmp_path / "correction.json",
        tmp_path / "source-review.json",
        tmp_path / "source-decision.json",
        tmp_path / "root-review.json",
        tmp_path / "root-decision.json",
        tmp_path / "parent-review.json",
        tmp_path / "parent-decision.json",
        review,
        decision,
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["persistent_support_corroboration_policy"] == (
        "adjacent-significant-support-corroboration-no-membership-v1"
    )
    assert continuum["terminal_cycle_parent_policy"] == (
        "three-feature-cycle-all-constituents-adjacent-persistent-v1"
    )
    assert continuum["terminal_parent_review_sha256"] == file_sha256(review)
    assert continuum[
        "terminal_parent_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_terminal_feature_persistence_configuration_binds_exact_authority(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The displaced-child identity extends only terminal persistence."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_terminal_parent_correction_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    review = tmp_path / "terminal-feature-review.json"
    decision = tmp_path / "terminal-feature-decision.json"
    review.write_text('{"review": 5}\n', encoding="utf-8")
    decision.write_text('{"decision": 5}\n', encoding="utf-8")

    configuration = public_finder_terminal_feature_persistence_configuration(
        tmp_path / "base.json",
        tmp_path / "correction.json",
        tmp_path / "source-review.json",
        tmp_path / "source-decision.json",
        tmp_path / "root-review.json",
        tmp_path / "root-decision.json",
        tmp_path / "parent-review.json",
        tmp_path / "parent-decision.json",
        tmp_path / "terminal-parent-review.md",
        tmp_path / "terminal-parent-decision.json",
        review,
        decision,
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["terminal_feature_persistence_policy"] == (
        "exact-or-mutually-unique-displaced-b3-support-child-v1"
    )
    assert continuum["terminal_feature_persistence_telemetry_policy"] == (
        "array-free-terminal-persistence-rejection-census-v1"
    )
    assert continuum["terminal_feature_persistence_pre_review_sha256"] == (
        file_sha256(review)
    )
    assert continuum[
        "terminal_feature_persistence_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_terminal_cycle_eligibility_configuration_binds_exact_authority(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """The eligibility identity changes no preceding science policy."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_terminal_feature_persistence_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    review = tmp_path / "terminal-cycle-review.json"
    decision = tmp_path / "terminal-cycle-decision.json"
    review.write_text('{"review": 6}\n', encoding="utf-8")
    decision.write_text('{"decision": 6}\n', encoding="utf-8")

    configuration = public_finder_terminal_cycle_eligibility_configuration(
        tmp_path / "base.json",
        tmp_path / "correction.json",
        tmp_path / "source-review.json",
        tmp_path / "source-decision.json",
        tmp_path / "root-review.json",
        tmp_path / "root-decision.json",
        tmp_path / "parent-review.json",
        tmp_path / "parent-decision.json",
        tmp_path / "terminal-parent-review.md",
        tmp_path / "terminal-parent-decision.json",
        tmp_path / "terminal-feature-review.json",
        tmp_path / "terminal-feature-decision.json",
        review,
        decision,
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["terminal_cycle_eligibility_policy"] == (
        "persistent-unseeded-geometry-seeded-membership-v1"
    )
    assert continuum["terminal_cycle_eligibility_telemetry_policy"] == (
        "array-free-terminal-cycle-eligibility-census-v1"
    )
    assert continuum["terminal_cycle_eligibility_pre_review_sha256"] == (
        file_sha256(review)
    )
    assert continuum[
        "terminal_cycle_eligibility_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_boundary_refinement_configuration_binds_exact_review(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Boundary refinement extends the candidate without policy drift."""
    mocker.patch(
        "hebog.validation.public_finder_correction."
        "public_finder_terminal_cycle_eligibility_configuration",
        return_value={"compact": {"frozen": True}, "continuum": {"base": 1}},
    )
    review = tmp_path / "boundary-review.json"
    decision = tmp_path / "boundary-decision.json"
    review.write_text('{"review": 7}\n', encoding="utf-8")
    decision.write_text('{"decision": 7}\n', encoding="utf-8")

    configuration = public_finder_boundary_refinement_configuration(
        base_review_path=tmp_path / "base.json",
        correction_contract_path=tmp_path / "correction.json",
        source_reconstruction_pre_review_path=tmp_path / "source-review.json",
        source_reconstruction_decision_path=tmp_path / "source-decision.json",
        root_cause_pre_review_path=tmp_path / "root-review.json",
        root_cause_implementation_decision_path=(
            tmp_path / "root-decision.json"
        ),
        parent_construction_pre_review_path=tmp_path / "parent-review.json",
        parent_construction_implementation_decision_path=(
            tmp_path / "parent-decision.json"
        ),
        terminal_parent_review_path=tmp_path / "terminal-parent-review.md",
        terminal_parent_implementation_decision_path=(
            tmp_path / "terminal-parent-decision.json"
        ),
        terminal_feature_pre_review_path=tmp_path / "feature-review.json",
        terminal_feature_implementation_decision_path=(
            tmp_path / "feature-decision.json"
        ),
        terminal_cycle_pre_review_path=tmp_path / "cycle-review.json",
        terminal_cycle_implementation_decision_path=(
            tmp_path / "cycle-decision.json"
        ),
        boundary_refinement_pre_review_path=review,
        boundary_refinement_implementation_decision_path=decision,
    )

    assert configuration["compact"] == {"frozen": True}
    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["base"] == 1
    assert continuum["boundary_refinement_policy"] == (
        "seeded-owner-dense-core-high-snr-nearby-significant-boundary-"
        "refinement-v1"
    )
    assert continuum["boundary_refinement_pre_review_sha256"] == (
        file_sha256(review)
    )
    assert continuum["boundary_refinement_implementation_decision_sha256"] == (
        file_sha256(decision)
    )


def test_mask_measurement_configuration_binds_exact_review(
    tmp_path: Path,
) -> None:
    """The mask-only correction has an explicit immutable identity layer."""
    files = tuple(tmp_path / f"contract-{index}.json" for index in range(18))
    for index, path in enumerate(files):
        path.write_text(f'{{"index": {index}}}\n', encoding="utf-8")

    configuration = public_finder_mask_measurement_separation_configuration(
        *files,
    )

    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["mask_measurement_separation_policy"] == (
        "three-sigma-published-mask-stable-seeded-measurement-v1"
    )
    assert continuum["mask_measurement_separation_pre_review_sha256"] == (
        file_sha256(files[-2])
    )
    assert continuum[
        "mask_measurement_separation_implementation_decision_sha256"
    ] == file_sha256(files[-1])


def test_publication_snr_configuration_extends_exact_base(
    tmp_path: Path,
) -> None:
    """The publication statistic has an explicit immutable identity layer."""
    review = tmp_path / "review.json"
    decision = tmp_path / "decision.json"
    review.write_text('{"review": true}\n', encoding="utf-8")
    decision.write_text('{"decision": true}\n', encoding="utf-8")
    base = {"compact": {"frozen": True}, "continuum": {"base": 1}}

    configuration = public_finder_publication_snr_repair_configuration(
        base,
        review,
        decision,
    )

    assert configuration["compact"] == {"frozen": True}
    continuum = cast(dict[str, object], configuration["continuum"])
    assert continuum["base"] == 1
    assert continuum["publication_snr_policy"] == (
        "direct-original-pixel-snr-published-boundary-v1"
    )
    assert continuum["publication_snr_pre_review_sha256"] == file_sha256(
        review
    )
    assert continuum[
        "publication_snr_implementation_decision_sha256"
    ] == file_sha256(decision)
    assert base == {"compact": {"frozen": True}, "continuum": {"base": 1}}


def test_source_reconstruction_builder_uses_scale_hierarchy_measurement(
    mocker: MockerFixture,
) -> None:
    """The future candidate composes corrected products without execution."""
    shape = (5, 5)
    image = np.ones(shape)
    background = np.zeros(shape)
    rms = np.ones(shape)
    labels = np.ones(shape, dtype=np.int32)
    direct_labels = np.zeros(shape, dtype=np.int32)
    direct_labels[2, 2] = 1
    measurement_labels = np.ones(shape, dtype=np.int32)
    detection = cast(
        Any,
        SimpleNamespace(component_labels=labels),
    )
    scale_planes = (cast(Any, SimpleNamespace(scale_order=1)),)
    position_signal = np.full(shape, 2.0)
    evaluate = mocker.patch(
        "hebog.validation.public_finder_correction."
        "evaluate_public_finder_correction_candidate_products",
        return_value=SimpleNamespace(
            detection=detection,
            direct_component_labels=direct_labels,
            measurement_component_labels=measurement_labels,
            significant_multiscale_support=np.zeros(shape, dtype=np.bool_),
            scale_detection_planes=scale_planes,
            position_signal_jy_per_beam=position_signal,
        ),
    )
    catalogue = (cast(Any, SimpleNamespace(identifier="source")),)
    components = (cast(Any, SimpleNamespace(identifier="component")),)
    association = cast(Any, SimpleNamespace())
    measure = mocker.patch(
        "hebog.validation.public_finder_correction."
        "build_hebog_reconstructed_source_catalogues",
        return_value=SimpleNamespace(
            source_catalogue=catalogue,
            component_catalogue=components,
            association=association,
        ),
    )
    beam = BeamShapePixels(4.0, 3.0, 0.0)
    review = cast(Any, SimpleNamespace())

    result = build_public_finder_source_reconstruction_continuum_products(
        image,
        background,
        rms,
        fits.Header(),
        beam=beam,
        review=review,
    )

    assert result.catalogue is catalogue
    assert result.component_catalogue is components
    assert result.source_association is association
    assert evaluate.call_args.kwargs == {"beam": beam, "review": review}
    assert measure.call_args.args[3] is measurement_labels
    assert measure.call_args.args[4] is direct_labels
    np.testing.assert_array_equal(
        measure.call_args.args[5],
        np.zeros(shape, dtype=np.bool_),
    )
    assert measure.call_args.args[6] is scale_planes
    assert measure.call_args.kwargs["position_signal_jy_per_beam"] is (
        position_signal
    )


def _real_scale_header(shape: tuple[int, int]) -> fits.Header:
    """Return one fixed synthetic one-arcsecond image header."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = shape[1]
    header["NAXIS2"] = shape[0]
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = shape[1] // 2 + 1.0
    header["CRPIX2"] = shape[0] // 2 + 1.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    return header


def _real_scale_source_products(
    image: np.ndarray,
) -> PublicFinderCorrectionContinuumProducts:
    """Run one synthetic image through the real corrective scale path."""
    review = load_phase_five_corrective_a_review(
        _ROOT / "config/contracts/phase-5-corrective-a-review.json"
    )
    return build_public_finder_source_reconstruction_continuum_products(
        image,
        np.zeros(image.shape),
        np.ones(image.shape),
        _real_scale_header(image.shape),
        beam=BeamShapePixels(4.0, 4.0, 0.0),
        review=review,
    )


def _modulated_ring_image(
    *,
    lobe_count: int,
    radius: float = 10.0,
    x_axis_ratio: float = 1.0,
) -> np.ndarray:
    """Return a fixed synthetic closed curved source with bright lobes."""
    shape = (81, 81)
    y_pixels, x_pixels = np.mgrid[: shape[0], : shape[1]]
    scaled_x = (x_pixels - 40.0) / x_axis_ratio
    radial_distance = np.hypot(scaled_x, y_pixels - 40.0)
    position_angle = np.arctan2(y_pixels - 40.0, scaled_x)
    image = np.exp(-((radial_distance - radius) ** 2) / 2.0)
    image *= 1.0 + 8.0 * np.clip(
        np.cos(float(lobe_count) * position_angle),
        0.0,
        None,
    )
    return image


def test_real_scale_composition_reconstructs_one_persistent_shell_parent() -> (
    None
):
    """The fixed filter footprint reconstructs one persistent shell parent."""
    products = _real_scale_source_products(_modulated_ring_image(lobe_count=4))

    diagnostics = products.source_association.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.direct_component_count == 4
    assert diagnostics.catalogue_source_count == 1
    assert diagnostics.membership_size_histogram == ((4, 1),)
    assert diagnostics.per_scale_feature_counts == ((1, 4), (2, 4), (3, 4))
    assert diagnostics.unique_convergence_count == 1
    assert diagnostics.per_scale_parent_candidate_counts == (
        (1, 0),
        (2, 1),
        (3, 1),
    )
    assert diagnostics.scale_aware_parent_candidate_count == 2
    assert diagnostics.persistent_parent_count == 0
    assert diagnostics.rejected_parent_ambiguity_count == 2
    assert diagnostics.terminal_cycle_parent_count == 1


@pytest.mark.parametrize(
    ("lobe_count", "radius", "x_axis_ratio"),
    (
        (3, 7.0, 1.0),
        (6, 10.0, 1.5),
        (7, 10.0, 1.5),
        (8, 12.0, 1.0),
    ),
    ids=(
        "three-lobe",
        "closed-curved-filament",
        "seven-knot-curved-filament",
        "eight-knot-shell",
    ),
)
def test_real_scale_parent_construction_handles_other_extended_morphologies(
    lobe_count: int,
    radius: float,
    x_axis_ratio: float,
) -> None:
    """Real scale products reconstruct multi-lobe and curved sources."""
    products = _real_scale_source_products(
        _modulated_ring_image(
            lobe_count=lobe_count,
            radius=radius,
            x_axis_ratio=x_axis_ratio,
        )
    )

    diagnostics = products.source_association.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.direct_component_count == lobe_count
    assert diagnostics.catalogue_source_count == 1
    assert diagnostics.membership_size_histogram == ((lobe_count, 1),)
    assert diagnostics.unique_convergence_count == 1


def test_real_scale_terminal_three_lobe_uses_persistent_parent() -> None:
    """Persistent features recover a parent first visible at scale three."""
    products = _real_scale_source_products(
        _modulated_ring_image(lobe_count=3, radius=10.0)
    )

    diagnostics = products.source_association.hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.direct_component_count == 3
    assert diagnostics.catalogue_source_count == 1
    assert diagnostics.membership_size_histogram == ((3, 1),)
    assert diagnostics.per_scale_parent_candidate_counts == (
        (1, 0),
        (2, 0),
        (3, 1),
    )
    assert diagnostics.persistent_parent_count == 0
    assert diagnostics.rejected_parent_ambiguity_count == 1
    assert diagnostics.connected_support_candidate_count == 0
    assert diagnostics.terminal_cycle_candidate_count == 1
    assert diagnostics.terminal_cycle_parent_count == 1


def test_public_correction_rejects_nonreal_input_before_science() -> None:
    """The prospective adapter fails closed before invoking the evaluator."""
    with pytest.raises(ValueError, match="aligned real"):
        build_public_finder_correction_continuum_products(
            np.ones((2, 2), dtype=np.complex128),
            np.zeros((2, 2)),
            np.ones((2, 2)),
            fits.Header(),
            beam=BeamShapePixels(2.0, 1.0, 0.0),
            review=object(),  # type: ignore[arg-type]
        )
