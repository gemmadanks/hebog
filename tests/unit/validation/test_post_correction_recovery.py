# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Tests for the approved Phase 5 post-correction recovery composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.external_recovery_compiler import (
    RecoveryContinuumImageCompiler,
    compact_component_realization,
    install_recovery_compiler_seams,
    label_planes_on_valid_domain,
    require_candidate_configuration,
)
from hebog.validation.external_runners import canonical_sha256
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
    measure_continuum_image,
)
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_correction_recovery import (
    build_post_correction_continuum_products,
    post_correction_candidate_configuration,
    post_correction_candidate_configuration_sha256,
)
from hebog.validation.public_finder_correction import (
    build_public_finder_correction_continuum_products,
    public_finder_correction_candidate_configuration,
)

_ROOT = Path(__file__).parents[3]
_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"
_PUBLIC_CORRECTION = (
    _ROOT / "config/contracts/phase-5-public-finder-correction.json"
)
_APPROVED_CONFIGURATION_SHA256 = (
    "0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94"
)


def test_candidate_configuration_reconstructs_approved_identity() -> None:
    """One shared serializer retains every approved candidate setting."""
    configuration = post_correction_candidate_configuration(_REVIEW)

    assert configuration["continuum"] == {
        "base_review_sha256": (
            "b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b"
        ),
        "measurement_aperture_radius_beams": 1.5,
        "position_policy": (
            "direct-plus-residual-b3-at-or-below-peak-to-mean-3-"
            "otherwise-original"
        ),
        "support_policy": "refined-residual-b3-multiscale-boundary",
    }
    assert canonical_sha256(configuration) == _APPROVED_CONFIGURATION_SHA256
    assert post_correction_candidate_configuration_sha256(_REVIEW) == (
        _APPROVED_CONFIGURATION_SHA256
    )


def test_public_correction_configuration_changes_only_owned_support() -> None:
    """The prospective identity retains every unrelated reviewed setting."""
    base = post_correction_candidate_configuration(_REVIEW)
    corrected = public_finder_correction_candidate_configuration(
        _REVIEW,
        _PUBLIC_CORRECTION,
    )

    assert corrected["compact"] == base["compact"]
    continuum = cast(dict[str, object], corrected["continuum"])
    assert (
        continuum["base_review_sha256"]
        == cast(dict[str, object], base["continuum"])["base_review_sha256"]
    )
    assert continuum["measurement_aperture_radius_beams"] == 1.5
    assert (
        continuum["position_policy"]
        == cast(dict[str, object], base["continuum"])["position_policy"]
    )
    assert continuum["support_policy"] == (
        "direct-seed-nearest-owner-half-beam-multiscale-recovery"
    )
    assert continuum["shape_policy"] == (
        "exact-owner-positive-residual-moment-equivalent"
    )


def test_candidate_product_adapter_connects_all_reviewed_science(
    mocker: MockerFixture,
) -> None:
    """The campaign boundary cannot fall back to historical defaults."""
    shape = (5, 6)
    image = np.ones(shape, dtype=np.float64)
    mean = np.zeros(shape, dtype=np.float64)
    rms = np.ones(shape, dtype=np.float64)
    labels = np.ones(shape, dtype=np.int32)
    detection = ThresholdFilterResult(
        combined_snr=np.ones(shape),
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
    )
    position_signal = np.full(shape, 2.0)
    evaluate = mocker.patch(
        "hebog.validation.post_correction_recovery."
        "evaluate_post_campaign_candidate_products",
        return_value=SimpleNamespace(
            detection=detection,
            position_signal_jy_per_beam=position_signal,
        ),
    )
    catalogue = (cast(Any, SimpleNamespace(identifier="source")),)
    measure = mocker.patch(
        "hebog.validation.post_correction_recovery."
        "build_hebog_segment_catalogue",
        return_value=catalogue,
    )
    beam = BeamShapePixels(4.0, 3.0, 12.0)
    review = cast(Any, SimpleNamespace())

    products = build_post_correction_continuum_products(
        image,
        mean,
        rms,
        fits.Header(),
        beam=beam,
        review=review,
    )

    assert products.detection is detection
    assert products.catalogue is catalogue
    np.testing.assert_array_equal(products.valid_pixels, np.ones(shape, bool))
    assert evaluate.call_args.args == (image, products.valid_pixels, mean, rms)
    assert evaluate.call_args.kwargs == {"beam": beam, "review": review}
    assert measure.call_args.args[:4] == (
        image,
        mean,
        products.valid_pixels,
        labels,
    )
    assert measure.call_args.kwargs == {
        "beam_major_fwhm_pixels": 4.0,
        "beam_minor_fwhm_pixels": 3.0,
        "measurement_aperture_radius_beams": 1.5,
        "position_signal_jy_per_beam": position_signal,
    }


def test_public_correction_adapter_uses_seeded_detection_and_moment_shapes(
    mocker: MockerFixture,
) -> None:
    """The new candidate composes only the approved prospective seams."""
    shape = (5, 6)
    image = np.ones(shape, dtype=np.float64)
    mean = np.zeros(shape, dtype=np.float64)
    rms = np.ones(shape, dtype=np.float64)
    labels = np.ones(shape, dtype=np.int32)
    detection = ThresholdFilterResult(
        combined_snr=np.ones(shape),
        retained_mask=labels > 0,
        component_labels=labels,
        component_count=1,
    )
    position_signal = np.full(shape, 2.0)
    evaluate = mocker.patch(
        "hebog.validation.public_finder_correction."
        "evaluate_public_finder_correction_candidate_products",
        return_value=SimpleNamespace(
            detection=detection,
            position_signal_jy_per_beam=position_signal,
        ),
    )
    catalogue = (cast(Any, SimpleNamespace(identifier="source")),)
    measure = mocker.patch(
        "hebog.validation.public_finder_correction."
        "build_hebog_segment_moment_catalogue",
        return_value=catalogue,
    )
    beam = BeamShapePixels(4.0, 3.0, 12.0)
    review = cast(Any, SimpleNamespace())

    products = build_public_finder_correction_continuum_products(
        image,
        mean,
        rms,
        fits.Header(),
        beam=beam,
        review=review,
    )

    assert products.detection is detection
    assert products.catalogue is catalogue
    assert evaluate.call_args.kwargs == {"beam": beam, "review": review}
    assert measure.call_args.args[:4] == (
        image,
        mean,
        products.valid_pixels,
        labels,
    )
    assert measure.call_args.kwargs["measurement_aperture_radius_beams"] == 1.5


def test_candidate_product_adapter_rejects_misaligned_validity() -> None:
    """Mean/RMS invalidity cannot silently differ from the input image."""
    image = np.ones((3, 3), dtype=np.float64)
    mean = np.zeros((3, 3), dtype=np.float64)
    mean[0, 0] = np.nan

    with pytest.raises(ValueError, match="validity differs"):
        build_post_correction_continuum_products(
            image,
            mean,
            np.ones((3, 3), dtype=np.float64),
            fits.Header(),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )

    with pytest.raises(ValueError, match="aligned real"):
        build_post_correction_continuum_products(
            image,
            np.ones((2, 3), dtype=np.float64),
            np.ones((3, 3), dtype=np.float64),
            fits.Header(),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )

    with pytest.raises(ValueError, match="validity differs"):
        build_public_finder_correction_continuum_products(
            image,
            mean,
            np.ones((3, 3), dtype=np.float64),
            fits.Header(),
            beam=BeamShapePixels(4.0, 3.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )


def _truth(
    identifier: str,
    label: int,
    centre_xy: tuple[float, float],
) -> ContinuumTruthObject:
    return ContinuumTruthObject(
        identifier=identifier,
        support_label=label,
        centre_xy=centre_xy,
        integrated_flux_jy=1.0,
        catalogue_role="astronomical-source",
        strata=(),
    )


def _candidate(
    identifier: str,
    centre_xy: tuple[float, float],
) -> ContinuumCatalogueObject:
    return ContinuumCatalogueObject(
        identifier=identifier,
        support_label=1,
        centre_xy=centre_xy,
        integrated_flux_jy=1.0,
    )


def test_valid_domain_preserves_duplicate_and_merged_support_semantics() -> (
    None
):
    """Invalid pixels are removed without conflating rows and topology."""
    truth_labels = np.asarray(
        ((1, 1, 0), (2, 2, 0), (0, 0, 0)),
        dtype=np.int64,
    )
    candidate_labels = np.asarray(
        ((1, 1, 0), (1, 1, 0), (0, 0, 0)),
        dtype=np.int64,
    )
    valid = np.ones(truth_labels.shape, dtype=np.bool_)
    valid[0, 0] = False

    observable_truth, observable_candidate = label_planes_on_valid_domain(
        truth_labels,
        candidate_labels,
        valid,
    )
    measurements = measure_continuum_image(
        (_truth("truth-1", 1, (1.0, 0.0)), _truth("truth-2", 2, (0.5, 1.0))),
        (
            _candidate("candidate-1", (1.0, 0.0)),
            _candidate("candidate-2", (0.5, 1.0)),
        ),
        truth_label_plane=observable_truth,
        candidate_label_plane=observable_candidate,
        beam_fwhm_pixels=4.0,
    )

    assert observable_truth[0, 0] == 0
    assert observable_candidate[0, 0] == 0
    assert measurements["duplicate-fraction"]["overall"] == 1.0
    assert measurements["merge-fraction"]["overall"] == 1.0


@pytest.mark.parametrize(
    ("truth", "candidate", "valid", "message"),
    (
        (
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.int64),
            np.ones((2, 2), dtype=np.bool_),
            "integer label",
        ),
        (
            np.ones((2, 2), dtype=np.int64),
            np.ones((2, 2), dtype=np.int64),
            np.ones((2, 2), dtype=np.int64),
            "boolean valid",
        ),
        (
            np.ones((2, 2), dtype=np.int64),
            np.ones((2, 3), dtype=np.int64),
            np.ones((2, 2), dtype=np.bool_),
            "aligned",
        ),
        (
            np.asarray(((0, -1), (0, 0)), dtype=np.int64),
            np.ones((2, 2), dtype=np.int64),
            np.ones((2, 2), dtype=np.bool_),
            "non-negative",
        ),
    ),
)
def test_valid_domain_rejects_malformed_planes(
    truth: np.ndarray,
    candidate: np.ndarray,
    valid: np.ndarray,
    message: str,
) -> None:
    """Prospective mask parity fails closed on ambiguous inputs."""
    with pytest.raises(ValueError, match=message):
        label_planes_on_valid_domain(truth, candidate, valid)


def _verified_candidate(configuration_sha256: str) -> SimpleNamespace:
    campaign_input = SimpleNamespace(input_id="input-1")
    run = SimpleNamespace(
        result=SimpleNamespace(configuration_sha256=configuration_sha256)
    )
    return SimpleNamespace(
        request=SimpleNamespace(inputs=(campaign_input,)),
        runs={("input-1", "hebog", "candidate"): run},
    )


def test_candidate_configuration_must_match_every_run() -> None:
    """A consistently wrong runtime identity cannot enter compilation."""
    require_candidate_configuration(
        _verified_candidate(_APPROVED_CONFIGURATION_SHA256),
        _APPROVED_CONFIGURATION_SHA256,
    )
    with pytest.raises(ValueError, match="configuration differs"):
        require_candidate_configuration(
            _verified_candidate("0" * 64),
            _APPROVED_CONFIGURATION_SHA256,
        )
    with pytest.raises(ValueError, match="run is absent"):
        require_candidate_configuration(
            SimpleNamespace(
                request=SimpleNamespace(
                    inputs=(SimpleNamespace(input_id="missing"),)
                ),
                runs={},
            ),
            _APPROVED_CONFIGURATION_SHA256,
        )
    with pytest.raises(ValueError, match="malformed"):
        require_candidate_configuration(
            _verified_candidate(_APPROVED_CONFIGURATION_SHA256),
            "not-a-sha",
        )
    with pytest.raises(ValueError, match="population is empty"):
        require_candidate_configuration(
            SimpleNamespace(
                request=SimpleNamespace(inputs=()),
                runs={},
            ),
            _APPROVED_CONFIGURATION_SHA256,
        )


def test_compact_recovery_always_uses_component_semantics(
    mocker: MockerFixture,
) -> None:
    """A successful compact result bypasses Rapthor source canonicalization."""
    expected = object()
    diagnose = mocker.patch(
        "hebog.validation.external_recovery_compiler."
        "diagnose_compact_component_realization",
        return_value=expected,
    )
    original = mocker.Mock()
    catalogue_loader = mocker.Mock(return_value=("component",))
    run = SimpleNamespace(result=SimpleNamespace(status="success"))

    actual = compact_component_realization(
        original,
        catalogue_loader,
        run,
        SimpleNamespace(),
        SimpleNamespace(),
        implementation_identifier="hebog",
        outlier_thresholds=SimpleNamespace(),
        position_angle_minimum_axis_ratio=1.1,
    )

    assert actual is expected
    assert original.call_count == 0
    assert catalogue_loader.call_args.args == (run,)
    assert diagnose.call_args.kwargs["implementation_identifier"] == "hebog"


def test_compact_recovery_preserves_retained_failures(
    mocker: MockerFixture,
) -> None:
    """Failed finder legs keep the historical denominator translation."""
    expected = object()
    original = mocker.Mock(return_value=expected)
    run = SimpleNamespace(result=SimpleNamespace(status="failure"))

    actual = compact_component_realization(
        original,
        mocker.Mock(),
        run,
        SimpleNamespace(),
        SimpleNamespace(),
        implementation_identifier="hebog",
        outlier_thresholds=SimpleNamespace(),
        position_angle_minimum_axis_ratio=1.1,
    )

    assert actual is expected
    assert original.call_count == 1


def test_compact_recovery_retains_catalogue_translation_failures(
    mocker: MockerFixture,
) -> None:
    """A malformed successful catalogue stays in the governed denominator."""
    diagnostic = compact_component_realization(
        mocker.Mock(),
        mocker.Mock(side_effect=ValueError("bad catalogue")),
        SimpleNamespace(result=SimpleNamespace(status="success")),
        SimpleNamespace(),
        SimpleNamespace(seed=19),
        implementation_identifier="hebog",
        outlier_thresholds=SimpleNamespace(),
        position_angle_minimum_axis_ratio=1.1,
    )

    assert diagnostic.status == "failure"
    assert diagnostic.seed == 19
    assert diagnostic.failure is not None
    assert diagnostic.failure.exception_type == "ValueError"
    assert diagnostic.failure.message == "bad catalogue"


def test_recovery_compiler_applies_valid_domain_to_all_finders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hebog and both PyBDSF references share one observable mask domain."""

    @dataclass(frozen=True)
    class Observation:
        image_key: str
        values: tuple[float, ...]

    plane = np.ones((2, 2), dtype=np.float64)
    image = plane.copy()
    image[0, 0] = np.nan
    labels = np.ones((2, 2), dtype=np.int64)
    measured_labels: list[np.ndarray] = []

    def measure(
        *_args: object,
        **kwargs: object,
    ) -> dict[str, dict[str, float]]:
        measured_labels.append(
            cast(np.ndarray, kwargs["candidate_label_plane"]).copy()
        )
        return {"mask-precision": {"overall": 1.0}}

    terminal = {
        "_input_artifact_path": (
            lambda _bundle, _input, role: Path(f"{role}.fits")
        ),
        "load_fits_plane": (
            lambda path: image if path.name == "image.fits" else plane
        ),
        "_truth_objects": lambda *_args: (("truth",), labels),
        "_catalogue_and_labels": lambda _run: (("catalogue",), labels),
        "_candidate_objects": lambda *_args, **_kwargs: ("candidate",),
        "measure_continuum_image": measure,
        "EndpointObservation": Observation,
        "_failed_endpoint_observations": lambda *_args, **_kwargs: {},
    }
    monkeypatch.setattr(
        "hebog.validation.external_recovery_compiler.fits.getheader",
        lambda _path: {},
    )
    compiler = RecoveryContinuumImageCompiler(terminal)
    verified = SimpleNamespace(
        inputs={"input-1": (SimpleNamespace(), Path("input.json"))}
    )
    specification = SimpleNamespace(
        metric_family="mask-precision",
        stratum="overall",
        endpoint_id="mask-precision-overall",
    )

    for finder in (
        "hebog",
        "released-pybdsf",
        "pinned-pybdsf-master",
    ):
        compiler(
            verified,
            SimpleNamespace(input_id="input-1"),
            SimpleNamespace(
                result=SimpleNamespace(
                    status="success",
                    failure=None,
                    finder_id=finder,
                )
            ),
            SimpleNamespace(beam=SimpleNamespace(major_fwhm_pixels=4.0)),
            SimpleNamespace(),
            SimpleNamespace(),
            (specification,),
        )

    assert len(measured_labels) == 3
    assert all(item[0, 0] == 0 for item in measured_labels)


@pytest.mark.parametrize(
    ("failure", "reason"),
    (
        (None, "finder failed"),
        (SimpleNamespace(message="runtime failed"), "runtime failed"),
    ),
)
def test_recovery_compiler_preserves_failed_finder_observations(
    failure: SimpleNamespace | None,
    reason: str,
    mocker: MockerFixture,
) -> None:
    """Failed runs retain endpoint rows without attempting product loading."""
    failed = mocker.Mock(return_value={"endpoint": "failed"})
    compiler = RecoveryContinuumImageCompiler(
        {"_failed_endpoint_observations": failed}
    )
    specifications = (SimpleNamespace(endpoint_id="endpoint"),)

    result = compiler(
        SimpleNamespace(),
        SimpleNamespace(input_id="input-1"),
        SimpleNamespace(
            result=SimpleNamespace(status="failure", failure=failure)
        ),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        specifications,
    )

    assert result == {"endpoint": "failed"}
    failed.assert_called_once_with(
        specifications,
        image_key="input-1",
        reason=reason,
    )


def test_recovery_compiler_rejects_mean_rms_validity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compiler truth creation rejects an invalidity mismatch."""
    image = np.ones((2, 2), dtype=np.float64)
    mean = image.copy()
    mean[0, 0] = np.nan
    planes = {"image": image, "mean": mean, "rms": image}
    terminal = {
        "_input_artifact_path": lambda _bundle, _input, role: Path(role),
        "load_fits_plane": lambda path: planes[path.name],
    }
    monkeypatch.setattr(
        "hebog.validation.external_recovery_compiler.fits.getheader",
        lambda _path: {},
    )
    compiler = RecoveryContinuumImageCompiler(terminal)

    with pytest.raises(ValueError, match="validity differs"):
        compiler(
            SimpleNamespace(
                inputs={"input-1": (SimpleNamespace(), Path("input.json"))}
            ),
            SimpleNamespace(input_id="input-1"),
            SimpleNamespace(
                result=SimpleNamespace(
                    status="success",
                    failure=None,
                    finder_id="hebog",
                )
            ),
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            (),
        )


def test_recovery_installation_binds_identity_and_science_seams(
    mocker: MockerFixture,
) -> None:
    """One installation connects verifier, Continuum, and compact policies."""
    verified = _verified_candidate(_APPROVED_CONFIGURATION_SHA256)
    original_verify = mocker.Mock(return_value=verified)
    original_compact = mocker.Mock()
    terminal = {
        "verify_terminal_campaign": original_verify,
        "_compact_realization": original_compact,
        "_compact_catalogue": mocker.Mock(),
    }

    install_recovery_compiler_seams(
        terminal,
        expected_candidate_configuration_sha256=(
            _APPROVED_CONFIGURATION_SHA256
        ),
    )

    assert isinstance(
        terminal["_continuum_image_observations"],
        RecoveryContinuumImageCompiler,
    )
    assert terminal["verify_terminal_campaign"]("campaign") is verified
    assert terminal["_compact_realization"] is not original_compact
    run = SimpleNamespace(result=SimpleNamespace(status="failure"))
    terminal["_compact_realization"](
        run,
        SimpleNamespace(),
        SimpleNamespace(),
        implementation_identifier="hebog",
        outlier_thresholds=SimpleNamespace(),
        position_angle_minimum_axis_ratio=1.1,
    )
    assert original_compact.call_count == 1


def test_cumulative_replay_installs_the_shared_recovery_composition(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The viewed-development replay cannot rebuild compiler policy itself."""
    module = __import__("runpy").run_path(
        str(
            _ROOT
            / "scripts/validation/review_phase5_cumulative_regressions.py"
        )
    )
    prospective = _verified_candidate(_APPROVED_CONFIGURATION_SHA256)
    require = mocker.Mock()
    install = mocker.Mock()
    function_globals = module["_install_prospective_compiler"].__globals__
    monkeypatch.setitem(
        function_globals,
        "require_candidate_configuration",
        require,
    )
    monkeypatch.setitem(
        function_globals,
        "install_recovery_compiler_seams",
        install,
    )
    compiler_globals: dict[str, Any] = {}

    module["_install_prospective_compiler"](
        compiler_globals,
        prospective,
        _APPROVED_CONFIGURATION_SHA256,
    )

    require.assert_called_once_with(
        prospective,
        _APPROVED_CONFIGURATION_SHA256,
    )
    install.assert_called_once_with(
        compiler_globals,
        expected_candidate_configuration_sha256=(
            _APPROVED_CONFIGURATION_SHA256
        ),
    )
