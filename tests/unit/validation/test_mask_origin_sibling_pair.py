# pyright: reportMissingTypeStubs=false
"""Contracts for the prospective mask-origin and sibling-pair candidate."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from pytest_mock import MockerFixture

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.external_runners import file_sha256
from hebog.validation.mask_origin_sibling_pair import (
    build_mask_origin_sibling_pair_continuum_products,
    public_finder_mask_origin_sibling_pair_configuration,
)
from hebog.validation.phase_five_filter_review import ThresholdFilterResult

_ROOT = Path(__file__).parents[3]
_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_mask_origin_sibling_pair_products.py"
)
_PREDECESSOR = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_publication_snr_products.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_mask_origin_sibling_pair_smoke.py"
)
_ACTIVATION_MATERIALIZER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_mask_origin_sibling_pair_activation_"
    "repair_products.py"
)
_ACTIVATION_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_mask_origin_sibling_pair_activation_repair_"
    "smoke.py"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-mask-origin-sibling-pair-pre-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-mask-origin-sibling-pair-implementation-decision.json"
)
_ACTIVATION_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-mask-origin-sibling-pair-activation-repair-"
    "pre-review.json"
)
_ACTIVATION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-prospective-mask-origin-sibling-pair-activation-repair-"
    "implementation-decision.json"
)


def _committed_file_sha256(revision: str, path: str) -> str:
    """Hash one historical file without consulting mutable working bytes."""
    content = subprocess.run(
        ("git", "show", f"{revision}:{path}"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(content).hexdigest()


def test_configuration_binds_both_policies_and_exact_reviews(
    tmp_path: Path,
) -> None:
    """The candidate identity records both prospective scientific changes."""
    review = tmp_path / "review.json"
    decision = tmp_path / "decision.json"
    review.write_text("review\n", encoding="utf-8")
    decision.write_text("decision\n", encoding="utf-8")

    configuration = public_finder_mask_origin_sibling_pair_configuration(
        {"compact": {"unchanged": True}, "continuum": {"base": "exact"}},
        review,
        decision,
    )

    assert configuration["compact"] == {"unchanged": True}
    continuum = configuration["continuum"]
    assert isinstance(continuum, dict)
    assert continuum["base"] == "exact"
    assert continuum["publication_mask_origin_policy"] == (
        "immutable-direct-owner-publication-origin-v1"
    )
    assert continuum["persistent_sibling_pair_policy"] == (
        "adjacent-scale-mutually-unique-envelope-pair-with-connected-support-v1"
    )
    assert continuum["mask_origin_sibling_pair_pre_review_sha256"] == (
        file_sha256(review)
    )
    assert continuum[
        "mask_origin_sibling_pair_implementation_decision_sha256"
    ] == file_sha256(decision)


def test_configuration_rejects_malformed_base(tmp_path: Path) -> None:
    """Malformed predecessor identities fail before evidence is hashed."""
    with pytest.raises(TypeError, match="must contain dictionaries"):
        public_finder_mask_origin_sibling_pair_configuration(
            {"compact": {}, "continuum": "invalid"},
            tmp_path / "review.json",
            tmp_path / "decision.json",
        )


def test_governed_records_bind_exact_implementation() -> None:
    """The closed decision remains exact after prospective source changes."""
    review = json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))
    activation_review = json.loads(
        _ACTIVATION_PRE_REVIEW.read_text(encoding="utf-8")
    )
    revision = activation_review["binding_evidence"]["candidate_revision"]

    assert review["binding_evidence"]["prospective_smoke_sha256"] == (
        "a8bee362728df293a30d171bed5afb4e412ecae9cbf9af06fbbce5afec083249"
    )
    assert decision["pre_review"] == {
        "path": str(_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_PRE_REVIEW),
    }
    for identity in decision["implementation"]:
        assert (
            _committed_file_sha256(revision, identity["path"])
            == identity["sha256"]
        )
    assert (
        decision["authorization"]["threshold_or_margin_tuning_authorized"]
        is False
    )


def test_activation_repair_records_bind_terminal_failure_and_programs() -> (
    None
):
    """The process repair cannot drift from failed evidence or exact code."""
    review = json.loads(_ACTIVATION_PRE_REVIEW.read_text(encoding="utf-8"))
    decision = json.loads(_ACTIVATION_DECISION.read_text(encoding="utf-8"))

    assert review["binding_evidence"]["terminal_smoke_sha256"] == (
        "778e43a96f0fad15c7ae28a562bcd18ca4b6e000df672221657e0803148addfc"
    )
    assert decision["pre_review"] == {
        "path": str(_ACTIVATION_PRE_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_ACTIVATION_PRE_REVIEW),
    }
    for identity in decision["implementation"]:
        assert file_sha256(_ROOT / identity["path"]) == identity["sha256"]
    assert (
        decision["authorization"]["threshold_or_margin_tuning_authorized"]
        is False
    )


def test_continuum_builder_preserves_measurement_catalogue_inputs(
    mocker: MockerFixture,
) -> None:
    """Publication origin does not replace association measurement support."""
    shape = (3, 4)
    labels = np.ones(shape, dtype=np.int32)
    detection = ThresholdFilterResult(
        combined_snr=np.ones(shape),
        retained_mask=np.ones(shape, dtype=np.bool_),
        component_labels=labels,
        component_count=1,
    )
    candidate = SimpleNamespace(
        detection=detection,
        measurement_component_labels=labels,
        direct_component_labels=labels,
        significant_multiscale_support=np.ones(shape, dtype=np.bool_),
        scale_detection_planes=(),
        position_signal_jy_per_beam=np.ones(shape),
    )
    evaluate = mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "evaluate_mask_origin_sibling_pair_candidate_products",
        return_value=candidate,
    )
    association = object()
    catalogue_builder = mocker.patch(
        "hebog.validation.mask_origin_sibling_pair."
        "build_hebog_reconstructed_source_catalogues",
        return_value=SimpleNamespace(
            source_catalogue=("source",),
            component_catalogue=("component",),
            association=association,
        ),
    )
    image = np.ones(shape)
    background = np.zeros(shape)
    rms = np.ones(shape)

    result = build_mask_origin_sibling_pair_continuum_products(
        image,
        background,
        rms,
        fits.Header(),
        beam=BeamShapePixels(2.0, 1.0, 0.0),
        review=cast(Any, SimpleNamespace()),
    )

    assert result.detection is detection
    assert result.measurement_component_labels is labels
    assert result.source_association is association
    assert result.valid_pixels.flags.writeable is False
    evaluate.assert_called_once()
    assert catalogue_builder.call_args.args[3] is labels
    assert catalogue_builder.call_args.args[4] is labels


def test_continuum_builder_rejects_mean_rms_validity_mismatch() -> None:
    """A finite image pixel cannot silently lose its scientific context."""
    image = np.ones((2, 2))
    background = np.zeros((2, 2))
    background[0, 0] = np.nan

    with pytest.raises(ValueError, match="validity differs from image"):
        build_mask_origin_sibling_pair_continuum_products(
            image,
            background,
            np.ones((2, 2)),
            fits.Header(),
            beam=BeamShapePixels(2.0, 1.0, 0.0),
            review=cast(Any, SimpleNamespace()),
        )


def test_materializer_composes_predecessor_without_mutating_it() -> None:
    """The new runtime extends the byte-frozen publication producer."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    base = wrapper["_base"](_ROOT)

    assert (
        base["build_public_finder_source_reconstruction_continuum_products"]
        is build_mask_origin_sibling_pair_continuum_products
    )
    assert (
        base["_current_composition"].__globals__[
            "build_public_finder_source_reconstruction_continuum_products"
        ]
        is build_mask_origin_sibling_pair_continuum_products
    )
    assert base["_BASE_MATERIALIZER"] == (
        "scripts/validation/materialize_phase5_prospective_hebog_products.py"
    )
    assert _PREDECESSOR.read_bytes().startswith(b"#!/usr/bin/env python3\n")


def test_current_composition_installs_builder_in_actual_writer_globals() -> (
    None
):
    """The nested publication wrapper must activate the new builder."""
    wrapper = runpy.run_path(str(_ACTIVATION_MATERIALIZER))

    frozen = wrapper["_current_composition"](
        _ROOT,
        revision="candidate-revision",
        configuration="candidate-configuration",
    )

    writer = frozen["_write_continuum_products"]
    separated_writer = writer.__globals__[  # pyright: ignore[reportFunctionMemberAccess]
        "_write_mask_separated_continuum_products"
    ]
    assert (
        separated_writer.__globals__[  # pyright: ignore[reportFunctionMemberAccess]
            "build_public_finder_source_reconstruction_continuum_products"
        ]
        is build_mask_origin_sibling_pair_continuum_products
    )


def test_materializer_rejects_unknown_candidate_mode() -> None:
    """Worker dispatch remains fail closed outside current and incumbent."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    with pytest.raises(ValueError, match="mode is unsupported"):
        wrapper["_composition"](
            {"candidate_mode": "unknown", "tooling_root": str(_ROOT)}
        )


def test_worker_strips_only_overlay_metadata() -> None:
    """The inherited generator receives the frozen candidate task schema."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    seen: dict[str, object] = {}

    def generate(task: dict[str, object]) -> str:
        seen.update(task)
        return "input-1"

    def composition(_task: dict[str, object]) -> dict[str, Any]:
        return {"_generate_candidate_product": generate}

    worker = wrapper["_generate_product"]
    worker.__globals__["_composition"] = composition
    assert (
        worker(
            {
                "candidate_mode": "current",
                "candidate_revision": "revision",
                "configuration_sha256": "configuration",
                "input_id": "input-1",
                "repository_root": str(_ROOT),
                "tooling_root": str(_ROOT),
            }
        )
        == "input-1"
    )
    assert seen == {
        "configuration_sha256": "configuration",
        "input_id": "input-1",
    }


def test_cli_installs_every_override_in_actual_runpy_globals() -> None:
    """Spawned execution resolves importable functions from this wrapper."""
    wrapper = runpy.run_path(str(_MATERIALIZER))
    base = wrapper["_base"](_ROOT)
    entrypoint = wrapper["_install_materializer_overrides"](base)

    for name in (
        "_current_configuration",
        "_current_composition",
        "_verified_reference",
        "_composition",
        "_generate_product",
    ):
        assert entrypoint.__globals__[name] is wrapper[name]


def test_evaluator_dispatches_only_the_composed_materializer() -> None:
    """The mixed-schema evaluator is reused with the exact new producer."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    base = evaluator["_base"](_ROOT)
    expected = (
        "scripts/validation/"
        "materialize_phase5_prospective_mask_origin_sibling_pair_products.py"
    )

    assert base["_MATERIALIZER"] == expected
    assert base["main"].__globals__["_MATERIALIZER"] == expected


def test_activation_evaluator_dispatches_only_the_repaired_materializer() -> (
    None
):
    """The replacement smoke evaluates the activated producer only."""
    evaluator = runpy.run_path(str(_ACTIVATION_EVALUATOR))
    base = evaluator["_base"](_ROOT)
    expected = (
        "scripts/validation/"
        "materialize_phase5_prospective_mask_origin_sibling_pair_activation_"
        "repair_products.py"
    )

    assert base["_MATERIALIZER"] == expected
    assert base["main"].__globals__["_MATERIALIZER"] == expected
