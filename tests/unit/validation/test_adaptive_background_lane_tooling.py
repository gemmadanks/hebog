"""Fail-closed tooling contracts for the adaptive-background lane."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import json
import os
import runpy
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.adaptive_background_lane import (
    build_adaptive_development_manifest,
    build_adaptive_runtime_identity,
    source_signal_and_truth,
)
from hebog.validation.datasets import recipe_sha256
from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT / "scripts/validation/run_phase5_adaptive_background_development.py"
)
_FREEZER = (
    _ROOT
    / "scripts/validation/freeze_phase5_adaptive_background_development.py"
)
_MANIFEST = (
    _ROOT
    / "config/contracts/phase-5-adaptive-background-development-manifest.json"
)
_IMPLEMENTATION = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-implementation-decision.json"
)
_IDENTITY = (
    _ROOT / "config/contracts/"
    "phase-5-adaptive-background-development-identity-review.json"
)


def _skip_upstream_identities(_repository_root: Path) -> None:
    """Isolate downstream historical-runner checks after supersession."""


def test_frozen_manifest_and_reviews_are_deterministic() -> None:
    """Checked-in identities must equal the approved generator output."""
    freezer = runpy.run_path(str(_FREEZER))

    manifest = build_adaptive_development_manifest()
    assert json.loads(_MANIFEST.read_text()) == manifest.model_dump(
        mode="json"
    )
    implementation = freezer["build_implementation_decision"](_ROOT)
    assert json.loads(_IMPLEMENTATION.read_text()) == implementation
    identity = freezer["build_identity_review"](_ROOT, implementation)
    assert json.loads(_IDENTITY.read_text()) == identity


def test_frozen_identity_is_non_executable_and_binds_every_program() -> None:
    """Implementation completion cannot silently authorize the lane."""
    identity = json.loads(_IDENTITY.read_text())

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["population"]["input_count"] == 144
    assert identity["population"]["total_finder_executions"] == 300
    for binding in identity["program_bindings"].values():
        assert file_sha256(_ROOT / binding["path"]) == binding["sha256"]
    assert identity["runtime"] == build_adaptive_runtime_identity(_ROOT)


def test_freezer_collision_leaves_the_other_destinations_absent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A stale member must stop the three-file freeze before any write."""
    freezer = runpy.run_path(str(_FREEZER))
    existing_identity = tmp_path / _IDENTITY.relative_to(_ROOT)
    existing_identity.parent.mkdir(parents=True)
    existing_identity.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(_FREEZER),
            "--repository-root",
            str(_ROOT),
            "--output-root",
            str(tmp_path),
        ],
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["main"]()

    assert not (tmp_path / _MANIFEST.relative_to(_ROOT)).exists()
    assert not (tmp_path / _IMPLEMENTATION.relative_to(_ROOT)).exists()
    assert existing_identity.read_text() == "existing\n"


def test_coarse_control_changes_only_the_adaptive_background_policy() -> None:
    """The diagnostic counterfactual keeps every other science field exact."""
    runner = runpy.run_path(str(_RUNNER))
    from hebog.validation.hebog_campaign import (  # noqa: PLC0415
        phase_five_corrected_candidate_configs,
    )

    original = phase_five_corrected_candidate_configs()
    coarse = runner["_coarse_control_configs"](original)

    assert coarse[0] == replace(
        original[0],
        background_rms=replace(original[0].background_rms, adaptive=None),
    )
    assert coarse[1:] == original[1:]
    assert original[0].background_rms.adaptive is not None


def test_coarse_control_context_restores_the_candidate_factory() -> None:
    """A diagnostic run cannot leak its internal override to later work."""
    runner = runpy.run_path(str(_RUNNER))
    import hebog.validation.hebog_campaign as campaign  # noqa: PLC0415

    original = campaign.phase_five_corrected_candidate_configs
    with runner["_coarse_control_configuration"]():
        assert campaign.phase_five_corrected_candidate_configs is not original
        assert (
            campaign.phase_five_corrected_candidate_configs()[
                0
            ].background_rms.adaptive
            is None
        )
    assert campaign.phase_five_corrected_candidate_configs is original


def test_public_science_capture_is_bounded_and_restores_hooks(
    monkeypatch: Any,
) -> None:
    """Diagnostic capture records only required state and cannot leak."""
    runner = runpy.run_path(str(_RUNNER))
    from hebog import public_api  # noqa: PLC0415

    products = object()
    detection_result = SimpleNamespace(
        adaptive_candidate_positions_yx=((2.0, 1.0), (1.0, 2.0))
    )

    def detection(*_args: object, **_kwargs: object) -> object:
        return detection_result

    def analysis(*_args: object, **_kwargs: object) -> object:
        return products

    monkeypatch.setattr(public_api, "run_detection_stage", detection)
    monkeypatch.setattr(public_api, "_analyse_image", analysis)

    with runner["_captured_public_science"]() as captured:
        detection_hook = cast(
            Callable[[], object], public_api.run_detection_stage
        )
        analysis_hook = cast(Callable[[], object], public_api._analyse_image)
        assert detection_hook() is detection_result
        assert analysis_hook() is products
        assert captured == {
            "adaptive_candidate_positions_yx": ((1.0, 2.0), (2.0, 1.0)),
            "products": products,
        }

    assert public_api.run_detection_stage is detection
    assert public_api._analyse_image is analysis


def test_verify_only_checks_all_tasks_without_creating_outputs(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """The task-count preflight covers 300 executions and writes nothing."""
    runner = runpy.run_path(str(_RUNNER))
    scratch = tmp_path / "scratch"
    output = tmp_path / "decision.json"
    main = runner["main"]
    monkeypatch.setitem(
        runner["verify_no_write"].__globals__,
        "_verify_upstream_identities",
        _skip_upstream_identities,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(_RUNNER),
            "--repository-root",
            str(_ROOT),
            "--manifest",
            str(_MANIFEST),
            "--identity-review",
            str(_IDENTITY),
            "--scratch",
            str(scratch),
            "--output",
            str(output),
            "--verify-only",
        ],
    )

    main()

    record = json.loads(capsys.readouterr().out)
    assert record["status"] == "pass"
    assert record["candidate_execution_count"] == 144
    assert record["coarse_control_execution_count"] == 144
    assert record["existing_dask_execution_count"] == 12
    assert record["candidate_execution_started"] is False
    assert not scratch.exists()
    assert not output.exists()


def test_runner_refuses_execution_without_an_approved_decision() -> None:
    """The frozen runner cannot consume the non-executable identity alone."""
    runner = runpy.run_path(str(_RUNNER))
    arguments = SimpleNamespace(
        execution_decision=None,
        identity_review=_IDENTITY,
        manifest=_MANIFEST,
        output=_ROOT / "benchmark-results/phase-5/"
        "adaptive-background-development-decision.json",
        repository_root=_ROOT,
        scratch=Path(
            "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
        ),
        workers=2,
    )

    with pytest.raises(PermissionError, match="exact execution decision"):
        runner["_verify_execution_authority"](arguments)


def test_runner_refuses_non_two_worker_execution(tmp_path: Path) -> None:
    """A future decision cannot widen the frozen execution shape."""
    runner = runpy.run_path(str(_RUNNER))
    decision = {
        "status": "authorized-for-one-development-lane",
        "authorization": {"development_lane_execution_authorized": True},
        "identity_review_sha256": file_sha256(_IDENTITY),
    }
    decision_path = tmp_path / "execution.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    arguments = SimpleNamespace(
        execution_decision=decision_path,
        identity_review=_IDENTITY,
        workers=1,
    )

    with pytest.raises(PermissionError, match="exactly two workers"):
        runner["_verify_execution_authority"](arguments)


def test_runner_refuses_widened_future_authorization(tmp_path: Path) -> None:
    """A lane approval cannot silently authorize release or other work."""
    runner = runpy.run_path(str(_RUNNER))
    identity = json.loads(_IDENTITY.read_text())
    decision = {
        "status": "authorized-for-one-development-lane",
        "authorization": {
            "candidate_execution_authorized": True,
            "coarse_control_execution_authorized": True,
            "development_lane_execution_authorized": True,
            "release_authorized": True,
        },
        "expected_execution_sha256": identity["expected_execution_sha256"],
        "identity_review_sha256": file_sha256(_IDENTITY),
    }
    decision_path = tmp_path / "execution.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    arguments = SimpleNamespace(
        execution_decision=decision_path,
        identity_review=_IDENTITY,
        manifest=_MANIFEST,
        output=_ROOT / "benchmark-results/phase-5/"
        "adaptive-background-development-decision.json",
        repository_root=_ROOT,
        scratch=Path(
            "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
        ),
        workers=2,
    )

    with pytest.raises(PermissionError, match="authority is invalid"):
        runner["_verify_execution_authority"](arguments)


def test_runner_accepts_only_the_exact_future_lane_authorization(
    tmp_path: Path,
) -> None:
    """The separately approved decision can open only the frozen lane."""
    runner = runpy.run_path(str(_RUNNER))
    identity = json.loads(_IDENTITY.read_text())
    decision = {
        "status": "authorized-for-one-development-lane",
        "authorization": runner["_EXPECTED_EXECUTION_AUTHORIZATION"],
        "expected_execution_sha256": identity["expected_execution_sha256"],
        "identity_review_sha256": file_sha256(_IDENTITY),
    }
    decision_path = tmp_path / "execution.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    arguments = SimpleNamespace(
        execution_decision=decision_path,
        identity_review=_IDENTITY,
        manifest=_MANIFEST,
        output=_ROOT / "benchmark-results/phase-5/"
        "adaptive-background-development-decision.json",
        repository_root=_ROOT,
        scratch=Path(
            "/private/tmp/hebog-phase5-adaptive-background-development-937737d"
        ),
        workers=2,
    )

    assert runner["_verify_execution_authority"](arguments) == decision


def test_runner_rejects_an_identity_with_changed_program_binding(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """No-write verification fails closed on prospective program drift."""
    runner = runpy.run_path(str(_RUNNER))
    identity = json.loads(_IDENTITY.read_text())
    identity["program_bindings"]["runner"]["sha256"] = "0" * 64
    changed = tmp_path / "identity.json"
    changed.write_text(json.dumps(identity), encoding="utf-8")
    monkeypatch.setitem(
        runner["verify_no_write"].__globals__,
        "_verify_upstream_identities",
        _skip_upstream_identities,
    )

    with pytest.raises(ValueError, match="program identity changed"):
        runner["verify_no_write"](
            repository_root=_ROOT,
            manifest_path=_MANIFEST,
            identity_path=changed,
            scratch=tmp_path / "scratch",
            output=tmp_path / "output.json",
        )


def test_materialized_realization_header_binds_its_exact_recipe(
    tmp_path: Path,
) -> None:
    """An alternate seed must not inherit the base recipe provenance."""
    runner = runpy.run_path(str(_RUNNER))
    manifest = build_adaptive_development_manifest()
    task = next(
        item
        for item in runner["_tasks"](manifest)
        if item.recipe.seed != item.dataset.recipe.seed
    )
    output = tmp_path / "image.fits"

    runner["_write_input"](output, task)

    assert fits.getheader(output)["HEBOGRCP"] == recipe_sha256(task.recipe)


def test_science_summary_uses_analytic_truth_and_source_level_flux() -> None:
    """Fixture reduction must retain exact truth-linked science metrics."""
    runner = runpy.run_path(str(_RUNNER))
    task = runner["_tasks"](build_adaptive_development_manifest())[0]
    _, truth, true_rms = source_signal_and_truth(task.recipe)
    true_flux = runner["_true_integrated_flux_jy"](task.dataset)
    source = SimpleNamespace(
        association_aperture_integrated_flux_jy=true_flux,
        flux=SimpleNamespace(integrated_flux_jy=true_flux / 2.0),
    )
    catalogue = SimpleNamespace(sources=(source,))

    summary = runner["_science_summary"](
        dataset=task.dataset,
        recipe=task.recipe,
        catalogue=catalogue,
        mask=truth,
        background=np.full(task.recipe.shape_yx, task.recipe.background),
        rms=true_rms,
    )

    assert summary.product_valid is True
    assert summary.completeness == 1.0
    assert summary.integrated_flux_absolute_fractional_error == 0.0
    assert summary.mask_iou == 1.0
    assert summary.support_recall == 1.0
    assert summary.background_error_p95_rms == 0.0
    assert summary.rms_error_p95_fraction == 0.0


def test_science_summary_rejects_product_shape_drift() -> None:
    """Malformed products fail explicitly before truth arithmetic."""
    runner = runpy.run_path(str(_RUNNER))
    task = runner["_tasks"](build_adaptive_development_manifest())[0]
    catalogue = SimpleNamespace(sources=())

    with pytest.raises(ValueError, match="product shape changed"):
        runner["_science_summary"](
            dataset=task.dataset,
            recipe=task.recipe,
            catalogue=catalogue,
            mask=np.zeros((1, 1), dtype=np.bool_),
            background=np.zeros(task.recipe.shape_yx),
            rms=np.ones(task.recipe.shape_yx),
        )


def test_science_summary_rejects_invalid_truth_support_products() -> None:
    """Non-finite local estimates fail before a summary can be retained."""
    runner = runpy.run_path(str(_RUNNER))
    task = runner["_tasks"](build_adaptive_development_manifest())[0]
    _, truth, true_rms = source_signal_and_truth(task.recipe)
    invalid_background = np.full(task.recipe.shape_yx, task.recipe.background)
    invalid_background[truth] = np.nan

    with pytest.raises(ValueError, match="invalid over truth support"):
        runner["_science_summary"](
            dataset=task.dataset,
            recipe=task.recipe,
            catalogue=SimpleNamespace(sources=()),
            mask=truth,
            background=invalid_background,
            rms=true_rms,
        )


def test_trigger_activation_requires_a_truth_linked_position() -> None:
    """Out-of-bounds candidates cannot satisfy the above-trigger seam."""
    runner = runpy.run_path(str(_RUNNER))
    truth = np.zeros((3, 3), dtype=np.bool_)
    truth[1, 1] = True

    assert runner["_activation_intersects_truth"](((1.0, 1.0),), truth)
    assert not runner["_activation_intersects_truth"](
        ((-1.0, 1.0), (4.0, 4.0)), truth
    )


def test_verify_only_rejects_malformed_nested_identity(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Malformed frozen authorization fails closed with a clear error."""
    runner = runpy.run_path(str(_RUNNER))
    identity = json.loads(_IDENTITY.read_text())
    identity["authorization"] = []
    changed = tmp_path / "identity.json"
    changed.write_text(json.dumps(identity), encoding="utf-8")
    monkeypatch.setitem(
        runner["verify_no_write"].__globals__,
        "_verify_upstream_identities",
        _skip_upstream_identities,
    )

    with pytest.raises(
        ValueError, match="authorization must be a JSON object"
    ):
        runner["verify_no_write"](
            repository_root=_ROOT,
            manifest_path=_MANIFEST,
            identity_path=changed,
            scratch=tmp_path / "scratch",
            output=tmp_path / "output.json",
        )


def test_public_candidate_verification_rejects_source_drift() -> None:
    """The upstream review cannot mask a changed public implementation."""
    runner = runpy.run_path(str(_RUNNER))
    review = json.loads(
        (
            _ROOT
            / "config/contracts/phase-5-public-interface-identity-review.json"
        ).read_text()
    )
    review["interface_file_sha256"]["src/hebog/public_api.py"] = "0" * 64

    with pytest.raises(ValueError, match="public candidate source changed"):
        runner["_verify_public_candidate_identity"](_ROOT, review)


def test_existing_dask_runtime_must_match_the_frozen_local_runtime() -> None:
    """Every caller-owned worker must use the exact reviewed environment."""
    runner = runpy.run_path(str(_RUNNER))
    expected = build_adaptive_runtime_identity(_ROOT)["installed"]

    class MismatchedClient:
        def run(
            self, function: Callable[[], dict[str, str]]
        ) -> dict[str, dict[str, str]]:
            return {
                "worker-a": function(),
                "worker-b": {**function(), "python_version": "0.0.0"},
            }

    with pytest.raises(
        ValueError, match="Dask worker runtime identity changed"
    ):
        runner["_verify_existing_dask_runtime"](MismatchedClient(), expected)


def test_atomic_terminal_writer_is_write_once(tmp_path: Path) -> None:
    """A terminal decision publishes completely and cannot be overwritten."""
    runner = runpy.run_path(str(_RUNNER))
    output = tmp_path / "decision.json"
    value = {"status": "pass", "value": 1}

    runner["_atomic_write"](output, value)

    assert json.loads(output.read_text()) == value
    assert not tuple(tmp_path.glob("*.tmp"))
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        runner["_atomic_write"](output, value)


def test_atomic_terminal_writer_cannot_clobber_a_racing_writer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Publication must fail if another writer wins the final-name race."""
    runner = runpy.run_path(str(_RUNNER))
    output = tmp_path / "decision.json"
    incumbent = {"status": "incumbent"}
    real_link = os.link

    def racing_link(source: Path, destination: Path) -> None:
        output.write_text(json.dumps(incumbent), encoding="utf-8")
        real_link(source, destination)

    monkeypatch.setattr(os, "link", racing_link)

    with pytest.raises(FileExistsError):
        runner["_atomic_write"](output, {"status": "challenger"})

    assert json.loads(output.read_text()) == incumbent
    assert not tuple(tmp_path.glob("*.tmp"))
