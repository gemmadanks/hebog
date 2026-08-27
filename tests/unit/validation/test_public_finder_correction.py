# pyright: reportMissingTypeStubs=false
"""Fixture-only contracts for the prospective public-finder correction."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.data_models.catalogues import Island, SourceCatalogue
from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.external_runners import file_sha256
from hebog.validation.public_finder_correction import (
    Sdc1SourceFindingRecord,
    build_public_finder_correction_continuum_products,
    build_public_moment_source_candidate,
    build_sdc1_source_finding_records,
    public_finder_correction_candidate_configuration,
    public_finder_source_association_candidate_configuration,
)


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
