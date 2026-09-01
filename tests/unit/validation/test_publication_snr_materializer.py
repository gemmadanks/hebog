"""Tests for the prospective publication-SNR materializer overlay."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.publication_snr_repair import (
    build_publication_snr_repaired_continuum_products,
)

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "materialize_phase5_prospective_publication_snr_products.py"
)
_BASE = (
    _ROOT
    / "scripts/validation/materialize_phase5_prospective_hebog_products.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_publication_snr_smoke.py"
)


def _load() -> dict[str, Any]:
    """Load the non-executing materializer overlay."""
    return runpy.run_path(str(_WRAPPER))


def test_overlay_preserves_base_bytes_and_installs_exact_builder() -> None:
    """The new candidate composes over rather than mutating its predecessor."""
    wrapper = _load()
    base = wrapper["_base"](_ROOT)

    assert (
        base["build_public_finder_source_reconstruction_continuum_products"]
        is build_publication_snr_repaired_continuum_products
    )
    assert _BASE.read_bytes().startswith(b"#!/usr/bin/env python3\n")


def test_overlay_configuration_extends_but_does_not_replace_base() -> None:
    """The repair receives a new identity while retaining its exact parent."""
    wrapper = _load()
    base = runpy.run_path(str(_BASE))

    assert wrapper["_current_configuration"](_ROOT) != base[
        "_current_configuration"
    ](_ROOT)


def test_overlay_rejects_unknown_candidate_mode() -> None:
    """Worker dispatch remains fail closed outside current and incumbent."""
    wrapper = _load()

    with pytest.raises(ValueError, match="mode is unsupported"):
        wrapper["_composition"](
            {"candidate_mode": "unknown", "tooling_root": str(_ROOT)}
        )


def test_product_worker_strips_overlay_only_metadata() -> None:
    """The frozen generator receives the historical candidate task schema."""
    wrapper = _load()
    seen: dict[str, object] = {}

    def generate(task: dict[str, object]) -> str:
        seen.update(task)
        return "input-1"

    def composition(_task: dict[str, object]) -> dict[str, Any]:
        return {"_generate_candidate_product": generate}

    wrapper["_composition"] = composition
    generate_product = wrapper["_generate_product"]
    generate_product.__globals__["_composition"] = wrapper["_composition"]

    result = generate_product(
        {
            "candidate_mode": "current",
            "candidate_revision": "revision",
            "configuration_sha256": "configuration",
            "input_id": "input-1",
            "repository_root": str(_ROOT),
            "tooling_root": str(_ROOT),
        }
    )

    assert result == "input-1"
    assert seen == {
        "configuration_sha256": "configuration",
        "input_id": "input-1",
    }


def test_evaluator_dispatches_the_repaired_materializer_only() -> None:
    """The exact mixed-schema compiler is reused with the new producer."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    base = evaluator["_base"](_ROOT)

    assert base["_MATERIALIZER"] == (
        "scripts/validation/"
        "materialize_phase5_prospective_publication_snr_products.py"
    )
    assert base["_REGISTRY"] == (
        "config/contracts/phase-5-prospective-science-endpoint-registry.json"
    )
