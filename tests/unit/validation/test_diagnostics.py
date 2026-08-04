"""Tests for explainable per-source campaign diagnostics."""

from __future__ import annotations

import pytest

from hebog.validation.comparison import (
    CatalogueEllipse,
    CatalogueOutlierThresholds,
    CatalogueSource,
    compare_catalogues,
)
from hebog.validation.diagnostics import source_pair_diagnostics


def _truth(identifier: str, right_ascension: float) -> CatalogueSource:
    """Return one unresolved truth source."""
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=right_ascension,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.0,
        deconvolution_status="unresolved",
        quality_flags=("unresolved",),
    )


def _candidate(
    identifier: str,
    right_ascension: float,
    *,
    integrated_flux: float,
) -> CatalogueSource:
    """Return one unresolved candidate with all Phase 4 formal errors."""
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=right_ascension,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=integrated_flux,
        right_ascension_error_degrees=0.001,
        declination_error_degrees=0.001,
        peak_flux_error_jy_per_beam=0.1,
        integrated_flux_error_jy=0.1,
        deconvolution_status="unresolved",
        quality_flags=("unresolved",),
    )


def _thresholds() -> CatalogueOutlierThresholds:
    """Return explicit catastrophic thresholds for diagnostic tests."""
    return CatalogueOutlierThresholds(
        position_beams=0.5,
        peak_flux_fractional_difference=0.5,
        integrated_flux_fractional_difference=0.5,
        fitted_axis_fractional_difference=0.5,
        deconvolved_axis_fractional_difference=1.0,
    )


def test_source_diagnostics_expose_all_pair_decisions() -> None:
    """Every truth/candidate decision retains its underlying source metrics."""
    truth = (_truth("truth-1", 10.0), _truth("truth-2", 10.1))
    candidate = (
        _candidate("candidate-1", 10.0, integrated_flux=1.6),
        _candidate("candidate-extra", 11.0, integrated_flux=1.0),
    )
    report = compare_catalogues(
        truth,
        candidate,
        beam_fwhm_degrees=0.01,
        maximum_separation_beams=0.5,
        outlier_thresholds=_thresholds(),
    )

    diagnostics = source_pair_diagnostics(
        truth,
        candidate,
        report,
        truth_strata_by_identifier={
            "truth-1": ("shape-marginal-resolved", "snr-10"),
            "truth-2": ("shape-unresolved", "snr-10"),
        },
        ungated_catastrophic_metrics_by_truth_identifier={
            "truth-1": frozenset({"integrated-flux"}),
        },
        position_angle_minimum_axis_ratio=1.1,
    )

    matched, missing_truth, extra_candidate = diagnostics
    assert matched.decision == "matched"
    assert matched.catastrophic is not None
    assert matched.catastrophic.integrated_flux is True
    assert matched.gated_catastrophic is False
    assert {
        residual.metric: residual.value
        for residual in matched.normalized_residuals
    } == {
        "declination": 0.0,
        "integrated-flux": pytest.approx(6.0),
        "peak-flux": 0.0,
        "right-ascension": 0.0,
    }
    assert missing_truth.decision == "unmatched-truth"
    assert missing_truth.truth_identifier == "truth-2"
    assert extra_candidate.decision == "unmatched-candidate"
    assert extra_candidate.candidate_identifier == "candidate-extra"


def test_source_diagnostics_retain_position_angle_differences() -> None:
    """Final absolute gates retain both fitted and deconvolved angles."""
    truth = CatalogueSource(
        identifier="truth",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.5,
        fitted_shape=CatalogueEllipse(0.01, 0.005, 179.0),
        deconvolved_shape=CatalogueEllipse(0.008, 0.004, 179.0),
        deconvolution_status="resolved",
    )
    candidate = CatalogueSource(
        identifier="candidate",
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=1.5,
        fitted_shape=CatalogueEllipse(0.011, 0.0045, 1.0),
        deconvolved_shape=CatalogueEllipse(0.0088, 0.0036, 1.0),
        deconvolution_status="resolved",
    )
    report = compare_catalogues(
        (truth,),
        (candidate,),
        beam_fwhm_degrees=0.1,
        maximum_separation_beams=0.5,
        outlier_thresholds=_thresholds(),
        position_angle_minimum_axis_ratio=1.1,
    )

    diagnostic = source_pair_diagnostics(
        (truth,),
        (candidate,),
        report,
        truth_strata_by_identifier={"truth": ("shape-clear-resolved",)},
        ungated_catastrophic_metrics_by_truth_identifier={},
        position_angle_minimum_axis_ratio=1.1,
    )[0]

    assert diagnostic.fitted_position_angle_difference_degrees == (
        pytest.approx(2.0)
    )
    assert diagnostic.deconvolved_position_angle_difference_degrees == (
        pytest.approx(2.0)
    )


def test_source_diagnostics_require_explicit_catastrophic_thresholds() -> None:
    """A diagnostic campaign cannot silently omit governed outlier flags."""
    truth = (_truth("truth", 10.0),)
    candidate = (_candidate("candidate", 10.0, integrated_flux=1.0),)
    report = compare_catalogues(
        truth,
        candidate,
        beam_fwhm_degrees=0.01,
        maximum_separation_beams=0.5,
    )

    with pytest.raises(ValueError, match="catastrophic thresholds"):
        source_pair_diagnostics(
            truth,
            candidate,
            report,
            truth_strata_by_identifier={"truth": ("shape-unresolved",)},
            ungated_catastrophic_metrics_by_truth_identifier={},
            position_angle_minimum_axis_ratio=1.1,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"position_angle_minimum_axis_ratio": 1.0}, "greater than one"),
        ({"truth": ()}, "reference count changed"),
        ({"candidate": ()}, "candidate count changed"),
        (
            {"truth_strata_by_identifier": dict[str, tuple[str, ...]]()},
            "cover every truth",
        ),
        (
            {
                "ungated_catastrophic_metrics_by_truth_identifier": {
                    "unknown-truth": frozenset[str]()
                }
            },
            "unknown truth identifier",
        ),
        (
            {
                "ungated_catastrophic_metrics_by_truth_identifier": {
                    "truth": frozenset({"not-a-metric"})
                }
            },
            "unsupported ungated",
        ),
    ],
)
def test_source_diagnostics_reject_inconsistent_protocol_inputs(
    change: dict[str, object],
    message: str,
) -> None:
    """Per-source evidence cannot drift from its aggregate report protocol."""
    truth = (_truth("truth", 10.0),)
    candidate = (_candidate("candidate", 10.0, integrated_flux=1.0),)
    report = compare_catalogues(
        truth,
        candidate,
        beam_fwhm_degrees=0.01,
        maximum_separation_beams=0.5,
        outlier_thresholds=_thresholds(),
    )
    arguments: dict[str, object] = {
        "truth": truth,
        "candidate": candidate,
        "report": report,
        "truth_strata_by_identifier": {"truth": ("shape-unresolved",)},
        "ungated_catastrophic_metrics_by_truth_identifier": {},
        "position_angle_minimum_axis_ratio": 1.1,
    }
    arguments.update(change)

    with pytest.raises(ValueError, match=message):
        source_pair_diagnostics(**arguments)  # type: ignore[arg-type]
