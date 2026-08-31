"""Fail-closed prospective smoke materializer tests."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.prospective_science_smoke import (
    select_prospective_smoke_inputs,
)

_ROOT = Path(__file__).parents[3]
_SCRIPT = (
    _ROOT
    / "scripts/validation/materialize_phase5_prospective_hebog_products.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
)
_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_POPULATION = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-smoke-population.json"
)


def test_materializer_selection_matches_public_frozen_selector() -> None:
    """The historical-safe selector retains the same exact population."""
    script = runpy.run_path(str(_SCRIPT))

    selected = script["_selected_inputs"](_REQUEST, _POPULATION)

    assert selected == set(
        select_prospective_smoke_inputs(_REQUEST, _POPULATION)
    )


def test_verify_only_does_not_create_scratch(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """A successful no-write preflight leaves its future namespace absent."""
    script = runpy.run_path(str(_SCRIPT))
    scratch = tmp_path / "prospective-smoke"
    task = {
        "candidate_mode": "current",
        "candidate_revision": "candidate-revision",
        "configuration_sha256": "configuration-sha256",
        "source_tree_sha256": "source-tree-sha256",
    }
    main = script["main"]

    def candidate_tasks(_arguments: object) -> tuple[dict[str, str], ...]:
        return (task,) * 128

    main.__globals__["_candidate_tasks"] = candidate_tasks
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(_SCRIPT),
            "--repository-root",
            str(_ROOT),
            "--reference-reconstruction",
            str(tmp_path / "reference"),
            "--source-request",
            str(_REQUEST),
            "--population",
            str(_POPULATION),
            "--scratch",
            str(scratch),
            "--candidate-mode",
            "current",
            "--verify-only",
        ],
    )

    main()

    assert not scratch.exists()
    record = json.loads(capsys.readouterr().out)
    assert record == {
        "candidate_configuration_sha256": "configuration-sha256",
        "candidate_mode": "current",
        "candidate_revision": "candidate-revision",
        "candidate_source_tree_sha256": "source-tree-sha256",
        "selected_input_count": 128,
    }


def _write_product(
    scratch: Path,
    input_id: str,
    *,
    configuration: str = "configuration",
    source_tree: str = "source-tree",
) -> None:
    directory = scratch / "products" / input_id
    directory.mkdir(parents=True)
    artifact = directory / "catalogue.json"
    artifact.write_text("{}\n", encoding="utf-8")
    marker = {
        "schema_version": 1,
        "input_id": input_id,
        "configuration_sha256": configuration,
        "source_tree_sha256": source_tree,
        "artifacts": [
            {
                "role": "catalogue-json",
                "relative_path": artifact.name,
                "byte_count": artifact.stat().st_size,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        ],
    }
    (directory / "complete.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )


def test_smoke_evaluator_binds_complete_product_set(tmp_path: Path) -> None:
    """Every marker, artifact, and population member enters one identity."""
    script = runpy.run_path(str(_EVALUATOR))
    scratch = tmp_path / "scratch"
    _write_product(scratch, "input-a")
    _write_product(scratch, "input-b")

    first = script["_verify_product_set"](
        {"input-a", "input-b"},
        scratch,
        configuration="configuration",
        source_tree="source-tree",
    )
    second = script["_verify_product_set"](
        {"input-b", "input-a"},
        scratch,
        configuration="configuration",
        source_tree="source-tree",
    )

    assert first == second
    assert len(first) == 64


def test_smoke_evaluator_rejects_marker_or_population_drift(
    tmp_path: Path,
) -> None:
    """Stale configuration and extra products cannot enter evaluation."""
    script = runpy.run_path(str(_EVALUATOR))
    scratch = tmp_path / "scratch"
    _write_product(scratch, "input-a", configuration="stale")
    with pytest.raises(ValueError, match="product marker changed"):
        script["_verify_product_set"](
            {"input-a"},
            scratch,
            configuration="configuration",
            source_tree="source-tree",
        )

    _write_product(scratch, "unexpected")
    with pytest.raises(ValueError, match="product population changed"):
        script["_verify_product_set"](
            {"input-a"},
            scratch,
            configuration="stale",
            source_tree="source-tree",
        )
