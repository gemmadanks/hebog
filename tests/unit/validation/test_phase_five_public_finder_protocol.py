"""Contracts for the non-executable Phase 5 public-finder composition."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from hebog.validation.public_comparison import (
    PublicCatalogueComponent,
    associate_public_catalogues,
    associate_truth_with_guard,
    sdc1_position_angle_degrees,
    summarize_hydra_association,
    summarize_shape_diagnostics,
    summarize_truth_association,
)

_ROOT = Path(__file__).parents[3]
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-execution-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT
    / "config/contracts/phase-5-public-finder-implementation-decision.json"
)
_PROTOCOL = _ROOT / "config/contracts/phase-5-public-finder-protocol.json"
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-identity-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-execution-decision.json"
)
_PROTOCOL_SCRIPT = (
    _ROOT / "scripts/validation/phase5_public_finder_protocol.py"
)
_CAMPAIGN_SCRIPT = (
    _ROOT / "scripts/benchmark/run_phase5_public_finder_campaign.py"
)
_RUNNER_SCRIPT = _ROOT / "scripts/benchmark/run_phase5_public_finder_hebog.py"
_COMPILER_SCRIPT = (
    _ROOT / "scripts/validation/compile_phase5_public_finder_campaign.py"
)
_EVALUATOR_SCRIPT = (
    _ROOT / "scripts/validation/evaluate_phase5_public_finder_decision.py"
)


def _component(
    identifier: str,
    *,
    ra_arcsec: float,
    flux: float,
    snr: float = 10.0,
) -> PublicCatalogueComponent:
    return PublicCatalogueComponent(
        identifier=identifier,
        right_ascension_degrees=ra_arcsec / 3600.0,
        declination_degrees=0.0,
        integrated_flux_jy=flux,
        peak_signal_to_noise=snr,
    )


def test_named_approval_authorizes_implementation_but_not_execution() -> None:
    """The user's approval must remain narrower than a public one-look."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))

    assert decision["pre_review"] == {
        "path": (
            "config/contracts/phase-5-public-finder-execution-pre-review.json"
        ),
        "sha256": (
            "476265e1b4e4ef1356f62a1b31ce4eb4ba3db995c84feddd8134da94bdb5ce4a"
        ),
    }
    assert decision["named_review"]["reviewer"] == "Gemma Danks"
    assert decision["implementation_authorized"] is True
    assert decision["identity_freeze_authorized"] is True
    assert set(decision["prohibited_authorizations"].values()) == {False}


def test_public_association_is_cardinality_flux_distance_stable() -> None:
    """Flux similarity resolves the ambiguous maximum-cardinality graph."""
    left = (
        _component("truth-a", ra_arcsec=0.00, flux=1.0),
        _component("truth-b", ra_arcsec=0.20, flux=2.0),
    )
    right = (
        _component("candidate-a", ra_arcsec=0.10, flux=2.0),
        _component("candidate-b", ra_arcsec=0.10, flux=1.0),
    )

    report = associate_public_catalogues(
        left,
        right,
        beam_fwhm_arcsec=0.6,
        maximum_separation_beams=0.5,
    )

    assert tuple(
        (match.left_identifier, match.right_identifier)
        for match in report.primary_associations
    ) == (
        ("truth-a", "candidate-b"),
        ("truth-b", "candidate-a"),
    )
    assert report.left_identifiers_with_multiple_edges == (
        "truth-a",
        "truth-b",
    )
    assert report.right_identifiers_with_multiple_edges == (
        "candidate-a",
        "candidate-b",
    )


def test_public_association_handles_an_empty_catalogue() -> None:
    """The sparse assignment has an explicit no-counterpart result."""
    left = (_component("truth", ra_arcsec=0.0, flux=1.0),)

    report = associate_public_catalogues(
        left,
        (),
        beam_fwhm_arcsec=1.0,
        maximum_separation_beams=0.5,
    )

    assert report.primary_associations == ()
    assert report.unmatched_left_identifiers == ("truth",)
    assert report.unmatched_right_identifiers == ()


def test_binding_truth_is_assigned_before_halo_guard_truth() -> None:
    """Guard truth explains only candidates left after binding assignment."""
    binding = (_component("binding", ra_arcsec=0.0, flux=1.0),)
    guard = (_component("guard", ra_arcsec=0.05, flux=1.0),)
    candidates = (_component("candidate", ra_arcsec=0.05, flux=1.0),)

    report = associate_truth_with_guard(
        binding,
        guard,
        candidates,
        beam_fwhm_arcsec=1.0,
        maximum_separation_beams=0.5,
    )

    assert tuple(
        item.left_identifier for item in report.primary_associations
    ) == ("binding",)
    assert report.left_identifiers_with_multiple_edges == ()
    assert report.right_identifiers_with_multiple_edges == ("candidate",)


def test_sdc1_summary_uses_graph_degrees_and_frozen_endpoints() -> None:
    """Binding values use all admitted objects and primary associations."""
    truth = (
        _component("truth-a", ra_arcsec=0.0, flux=1.0),
        _component("truth-b", ra_arcsec=2.0, flux=2.0),
    )
    candidates = (
        _component("candidate-a", ra_arcsec=0.06, flux=1.1),
        _component("candidate-b", ra_arcsec=0.12, flux=1.2),
    )
    report = associate_public_catalogues(
        truth,
        candidates,
        beam_fwhm_arcsec=0.6,
        maximum_separation_beams=0.5,
    )

    summary = summarize_truth_association(report, truth, candidates)

    assert summary["truth_count"] == 2
    assert summary["candidate_count"] == 2
    assert summary["matched_count"] == 1
    assert summary["completeness"] == pytest.approx(0.5)
    assert summary["reliability"] == pytest.approx(0.5)
    assert summary["duplicate-fraction"] == pytest.approx(0.5)
    assert summary["merge-fraction"] == pytest.approx(0.0)
    assert summary["integrated-flux-median"] == pytest.approx(0.1)
    assert summary["position-p95"] == pytest.approx(0.1)


def test_hydra_summary_is_diagnostic_and_auditable() -> None:
    """Hydra records matched distributions plus stable unmatched audits."""
    left = (
        _component("left-match", ra_arcsec=0.0, flux=1.0),
        _component("left-unmatched", ra_arcsec=5.0, flux=3.0, snr=30.0),
    )
    right = (
        _component("right-match", ra_arcsec=0.1, flux=1.1),
        _component("right-unmatched", ra_arcsec=8.0, flux=4.0, snr=40.0),
    )
    report = associate_public_catalogues(
        left,
        right,
        beam_fwhm_arcsec=1.0,
        maximum_separation_beams=0.5,
    )

    summary = summarize_hydra_association(report, left, right)
    left_audit = cast(
        list[dict[str, object]], summary["left_unmatched_highest_snr"]
    )
    right_audit = cast(
        list[dict[str, object]], summary["right_unmatched_highest_snr"]
    )

    assert summary["binding"] is False
    assert summary["matched_count"] == 1
    assert summary["overlap"] == pytest.approx(0.5)
    assert left_audit[0]["identifier"] == "left-unmatched"
    assert right_audit[0]["identifier"] == "right-unmatched"


def test_shape_diagnostics_use_axial_position_angle_distance() -> None:
    """Shape diagnostics treat 0 and 180 degrees as the same orientation."""
    left = (
        PublicCatalogueComponent(
            identifier="truth",
            right_ascension_degrees=0.0,
            declination_degrees=0.0,
            integrated_flux_jy=1.0,
            major_axis_arcsec=2.0,
            minor_axis_arcsec=1.0,
            position_angle_degrees=179.0,
        ),
    )
    right = (
        PublicCatalogueComponent(
            identifier="candidate",
            right_ascension_degrees=0.0,
            declination_degrees=0.0,
            integrated_flux_jy=1.0,
            major_axis_arcsec=2.2,
            minor_axis_arcsec=0.9,
            position_angle_degrees=1.0,
        ),
    )
    report = associate_public_catalogues(
        left,
        right,
        beam_fwhm_arcsec=1.0,
        maximum_separation_beams=0.5,
    )

    diagnostics = summarize_shape_diagnostics(report, left, right)

    assert diagnostics["major-axis-fractional-error-median"] == pytest.approx(
        0.1
    )
    assert diagnostics["minor-axis-fractional-error-median"] == pytest.approx(
        0.1
    )
    assert diagnostics["position-angle-absolute-error-median-deg"] == 2.0


def test_shape_diagnostics_exclude_near_circular_position_angles() -> None:
    """Orientation is unavailable when the truth ellipse has no stable axis."""
    left = (
        PublicCatalogueComponent(
            identifier="truth",
            right_ascension_degrees=0.0,
            declination_degrees=0.0,
            integrated_flux_jy=1.0,
            major_axis_arcsec=1.05,
            minor_axis_arcsec=1.0,
            position_angle_degrees=0.0,
        ),
    )
    right = (
        PublicCatalogueComponent(
            identifier="candidate",
            right_ascension_degrees=0.0,
            declination_degrees=0.0,
            integrated_flux_jy=1.0,
            major_axis_arcsec=1.05,
            minor_axis_arcsec=1.0,
            position_angle_degrees=90.0,
        ),
    )
    report = associate_public_catalogues(
        left,
        right,
        beam_fwhm_arcsec=1.0,
        maximum_separation_beams=0.5,
    )

    diagnostics = summarize_shape_diagnostics(report, left, right)

    assert diagnostics["position-angle-count"] == 0
    assert diagnostics["position-angle-absolute-error-median-deg"] is None


@pytest.mark.parametrize(
    ("sdc1_angle", "hebog_angle"),
    ((0.0, 90.0), (90.0, 0.0), (180.0, 90.0), (270.0, 0.0)),
)
def test_sdc1_position_angle_conversion_is_axial(
    sdc1_angle: float,
    hebog_angle: float,
) -> None:
    """The reviewed SDC1 convention maps into Hebog's axial convention."""
    assert sdc1_position_angle_degrees(sdc1_angle) == hebog_angle


def test_protocol_is_exact_and_non_executable() -> None:
    """The implemented protocol binds inputs but does not authorize a run."""
    helpers = runpy.run_path(str(_PROTOCOL_SCRIPT))
    protocol = helpers["load_public_finder_protocol"](_PROTOCOL)

    assert protocol["selected_population"]["sha256"] == (
        "0a7c2b18d96ee47277072528949c5a64239f0c3053d5e7b33c03b36c194b7824"
    )
    assert protocol["case_count"] == 10
    assert "execution_authorized" not in protocol


def test_exact_identity_review_keeps_public_execution_closed() -> None:
    """The frozen programs and outputs remain pending a second approval."""
    helpers = runpy.run_path(str(_PROTOCOL_SCRIPT))
    review = json.loads(_IDENTITY_REVIEW.read_text(encoding="utf-8"))
    decision = helpers["load_public_finder_execution_decision"](
        _EXECUTION_DECISION
    )

    assert review["implementation_commit"] == (
        "3d234c5d414a002824db513a37b3fe8322aedaf2"
    )
    assert review["outputs_absent_at_review"] is True
    assert review["execution_authorized"] is False
    assert review["compilation_authorized"] is False
    assert review["evaluation_authorized"] is False
    assert set(review["prohibited_authorizations"].values()) == {False}
    assert decision["status"] == "pending-named-one-look-approval"
    assert decision["named_review"] is None
    assert decision["execution_authorized"] is False
    assert decision["finder_execution_authorized"] is False
    assert decision["campaign_execution_authorized"] is False
    assert decision["compilation_authorized"] is False
    assert decision["evaluation_authorized"] is False


def test_pending_campaign_preflight_rejects_before_external_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Implementation validation cannot accidentally open the campaign."""
    campaign = runpy.run_path(str(_CAMPAIGN_SCRIPT))
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    def pending_decision(_path: Path) -> dict[str, bool]:
        return {"execution_authorized": False}

    monkeypatch.setitem(
        campaign["preflight_public_finder"].__globals__, "_run", forbidden
    )
    monkeypatch.setitem(
        campaign["preflight_public_finder"].__globals__["_HELPERS"],
        "load_public_finder_execution_decision",
        pending_decision,
    )
    with pytest.raises(ValueError, match="not authorized"):
        campaign["preflight_public_finder"](
            repository_root=_ROOT,
            output=tmp_path / "campaign",
            hebog_image="unused",
        )
    assert called is False


def test_campaign_preflight_rejects_a_second_output_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Named authority can open only the identity-reviewed output path."""
    campaign = runpy.run_path(str(_CAMPAIGN_SCRIPT))
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    def authorized_decision(_path: Path) -> dict[str, bool]:
        return {"execution_authorized": True}

    def protocol_stub(_path: Path) -> dict[str, object]:
        return {}

    monkeypatch.setitem(
        campaign["preflight_public_finder"].__globals__, "_run", forbidden
    )
    monkeypatch.setitem(
        campaign["preflight_public_finder"].__globals__["_HELPERS"],
        "load_public_finder_execution_decision",
        authorized_decision,
    )
    monkeypatch.setitem(
        campaign["preflight_public_finder"].__globals__["_HELPERS"],
        "load_public_finder_protocol",
        protocol_stub,
    )
    with pytest.raises(ValueError, match="output path changed"):
        campaign["preflight_public_finder"](
            repository_root=_ROOT,
            output=tmp_path / "second-campaign",
            hebog_image="unused",
        )
    assert called is False


def test_compiler_rejects_campaign_provenance_drift() -> None:
    """A sealed-looking manifest cannot substitute a different one-look."""
    compiler = runpy.run_path(str(_COMPILER_SCRIPT))
    campaign = {
        "status": "terminal-raw-results-sealed",
        "case_count": 1,
        "successful_case_count": 1,
        "protocol_sha256": "wrong",
        "execution_decision_sha256": "decision",
        "results": [{"case_id": "case-a", "status": "success"}],
    }

    with pytest.raises(ValueError, match="provenance"):
        compiler["_validate_campaign_manifest"](
            campaign,
            expected_case_ids=("case-a",),
            protocol_sha256="protocol",
            execution_decision_sha256="decision",
        )


def test_sdc1_candidate_shape_uses_deconvolved_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Intrinsic SDC1 truth is compared with candidate deconvolved shape."""
    compiler = runpy.run_path(str(_COMPILER_SCRIPT))
    fitted = SimpleNamespace(
        major_fwhm_degrees=2.0 / 3600.0,
        minor_fwhm_degrees=1.0 / 3600.0,
        position_angle_degrees=20.0,
    )
    deconvolved = SimpleNamespace(
        major_fwhm_degrees=1.0 / 3600.0,
        minor_fwhm_degrees=0.5 / 3600.0,
        position_angle_degrees=30.0,
    )
    source = SimpleNamespace(
        identifier="candidate",
        right_ascension_degrees=0.0,
        declination_degrees=0.0,
        peak_flux_jy_per_beam=1.0,
        association_integrated_flux_jy=1.0,
        integrated_flux_jy=1.0,
        fitted_shape=fitted,
        deconvolved_shape=deconvolved,
    )

    class FakeWcs:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.celestial = self

        def all_world2pix(
            self, *_args: object, **_kwargs: object
        ) -> tuple[float, float]:
            return 0.0, 0.0

    def comparison_catalogue(_path: Path) -> tuple[SimpleNamespace, ...]:
        return (source,)

    def rms_plane(_path: Path) -> Any:
        return np.asarray([[0.1]])

    def fits_header(_path: Path) -> dict[str, object]:
        return {}

    globals_ = compiler["_candidate_components"].__globals__
    monkeypatch.setitem(
        globals_, "load_comparison_catalogue", comparison_catalogue
    )
    monkeypatch.setitem(globals_, "load_fits_plane", rms_plane)
    monkeypatch.setitem(globals_, "WCS", FakeWcs)
    monkeypatch.setattr(globals_["fits"], "getheader", fits_header)

    components = compiler["_candidate_components"](
        {
            "segment-catalogue-json": Path("catalogue.json"),
            "rms-fits": Path("rms.fits"),
        },
        shape_role="deconvolved",
    )

    assert components[0].major_axis_arcsec == pytest.approx(1.0)
    assert components[0].minor_axis_arcsec == pytest.approx(0.5)
    assert components[0].position_angle_degrees == 30.0


def test_hebog_runner_publishes_only_a_complete_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The runner builds privately before its one atomic directory rename."""
    runner = runpy.run_path(str(_RUNNER_SCRIPT))

    def build_bundle(**arguments: object) -> dict[str, object]:
        unpublished = cast(Path, arguments["output"])
        unpublished.mkdir()
        (unpublished / "result.json").write_text("{}\n", encoding="utf-8")
        return {"status": "success"}

    monkeypatch.setitem(
        runner["run_public_hebog"].__globals__,
        "_build_public_bundle",
        build_bundle,
    )
    output = tmp_path / "case"

    result = runner["run_public_hebog"](
        input_path=tmp_path / "unused.fits",
        output=output,
        case_id="test-case",
        core=None,
        configuration_sha256="unused",
    )

    assert result == {"status": "success"}
    assert (output / "result.json").is_file()
    assert tuple(tmp_path.glob(".case.*")) == ()


def test_compiler_and_evaluator_expose_pure_terminal_boundaries() -> None:
    """Scientific compilation and decisions remain testable without data."""
    compiler = runpy.run_path(str(_COMPILER_SCRIPT))
    evaluator = runpy.run_path(str(_EVALUATOR_SCRIPT))
    metric_limits = {
        "absolute-mean-offset-x": {"at_most": 0.1},
        "absolute-mean-offset-y": {"at_most": 0.1},
        "completeness": {"at_least": 0.9},
        "duplicate-fraction": {"at_most": 0.02},
        "integrated-flux-median": {"at_most": 0.1},
        "integrated-flux-p95": {"at_most": 0.25},
        "merge-fraction": {"at_most": 0.1},
        "position-p95": {"at_most": 0.5},
        "reliability": {"at_least": 0.95},
    }
    passing = {
        "absolute-mean-offset-x": 0.0,
        "absolute-mean-offset-y": 0.0,
        "completeness": 1.0,
        "duplicate-fraction": 0.0,
        "integrated-flux-median": 0.0,
        "integrated-flux-p95": 0.0,
        "merge-fraction": 0.0,
        "position-p95": 0.0,
        "reliability": 1.0,
    }

    endpoint = compiler["evaluate_metric_limits"](
        "overall",
        passing,
        metric_limits,
    )
    decision = evaluator["evaluate_public_finder_analysis"](
        {
            "sdc1_endpoints": [endpoint] * 9,
            "hydra_diagnostics_complete": True,
            "successful_hebog_run_count": 10,
            "expected_hebog_run_count": 10,
        }
    )

    assert endpoint["passed"] is True
    assert decision["status"] == "pass"
    assert decision["cutover_authorized"] is False
