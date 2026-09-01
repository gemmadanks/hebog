# pyright: reportMissingTypeStubs=false
"""Contracts for publication-scale-persistence evaluation completion."""

from __future__ import annotations

import json
import runpy
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
_PROGRAM = (
    _ROOT / "scripts/validation/"
    "complete_phase5_publication_scale_persistence_evaluation.py"
)
_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-evaluation-completion-review.json"
)
_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-evaluation-completion-execution-"
    "decision.json"
)


def _load() -> dict[str, Any]:
    """Load the completion program without executing its entry point."""
    return runpy.run_path(str(_PROGRAM))


def _artifact(path: Path, role: str) -> dict[str, object]:
    """Return one exact fixture artifact record."""
    return {
        "byte_count": path.stat().st_size,
        "relative_path": path.name,
        "role": role,
        "sha256": file_sha256(path),
    }


def test_existing_products_are_hashed_and_complete(tmp_path: Path) -> None:
    """Completion accepts only an exact fully declared product set."""
    completion = _load()
    completion["verify_existing_products"].__globals__.update(
        {
            "_EXPECTED_INPUT_COUNT": 2,
        }
    )
    scratch = tmp_path / "scratch"
    products = scratch / "products"
    markers: list[dict[str, object]] = []
    for input_id, lane in (("compact", "compact"), ("continuum", "continuum")):
        directory = products / input_id
        directory.mkdir(parents=True)
        roles = (
            {"compact-catalogue-json": "compact_catalogue.json"}
            if lane == "compact"
            else {
                "measurement-labels-fits": "measurement_labels.fits",
                "segment-catalogue-json": "segment_catalogue.json",
                "segment-labels-fits": "segment_labels.fits",
                "segment-mask-fits": "segment_mask.fits",
                "source-association-json": "source_association.json",
            }
        )
        artifacts: list[dict[str, object]] = []
        for role, name in roles.items():
            path = directory / name
            path.write_text(role, encoding="utf-8")
            artifacts.append(_artifact(path, role))
        marker: dict[str, object] = {
            "artifacts": sorted(
                artifacts, key=lambda value: cast(str, value["role"])
            ),
            "configuration_sha256": completion[
                "_CANDIDATE_CONFIGURATION_SHA256"
            ],
            "input_id": input_id,
            "schema_version": 1,
            "source_tree_sha256": completion["_CANDIDATE_SOURCE_TREE_SHA256"],
        }
        (directory / "complete.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )
        markers.append(marker)
    (scratch / "progress.log").write_text(
        "completed=1/2 input=compact\ncompleted=2/2 input=continuum\n",
        encoding="utf-8",
    )
    expected_hash = canonical_sha256(markers)
    completion["verify_existing_products"].__globals__[
        "_CANDIDATE_PRODUCT_SET_SHA256"
    ] = expected_hash

    assert (
        completion["verify_existing_products"](
            scratch, (("compact", "compact"), ("continuum", "continuum"))
        )
        == expected_hash
    )

    (products / "continuum" / "segment_mask.fits").write_text(
        "changed", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="artifact identity changed"):
        completion["verify_existing_products"](
            scratch,
            (("compact", "compact"), ("continuum", "continuum")),
        )


def test_completion_forbids_candidate_execution() -> None:
    """The repaired path verifies shards without running candidate code."""
    completion = _load()
    completion["_install_completion_only"].__globals__.update(
        {"_EXPECTED_INPUT_COUNT": 1, "_WORKERS": 2}
    )

    def completed_candidate(
        _directory: Path,
        *,
        input_id: str,
        configuration_sha256: str,
        source_sha256: str,
    ) -> bool:
        return bool(input_id and configuration_sha256 and source_sha256)

    frozen: dict[str, Any] = {
        "_completed_candidate": completed_candidate,
    }
    completion["_install_completion_only"](frozen, (("input-1", "continuum"),))
    task = {
        "configuration_sha256": completion["_CANDIDATE_CONFIGURATION_SHA256"],
        "input_id": "input-1",
        "lane": "continuum",
        "output_directory": str(completion["_SCRATCH"] / "products/input-1"),
        "source_tree_sha256": completion["_CANDIDATE_SOURCE_TREE_SHA256"],
    }

    frozen["_run_candidate_tasks"](
        (task,),
        workers=2,
        progress_path=completion["_SCRATCH"] / "progress.log",
    )
    with pytest.raises(RuntimeError, match="forbids candidate execution"):
        frozen["_generate_candidate_product"](task)


def test_mask_separation_is_installed_for_full_compilation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The full compiler receives the same overlay as the passing smoke."""
    completion = _load()
    events: list[str] = []

    def install_historical(
        compiler: dict[str, object],
        _prospective: object,
        _configuration: str,
    ) -> None:
        events.append("historical")
        compiler["_continuum_image_observations"] = lambda: None

    frozen: dict[str, Any] = {
        "_install_prospective_compiler": install_historical,
    }

    def fake_run_path(_path: str) -> dict[str, object]:
        def install(compiler: dict[str, object], **_kwargs: object) -> None:
            events.append("separated")
            compiler["_continuum_image_observations"] = object()

        smoke: dict[str, object] = {
            "_install_mask_separated_compiler": install,
            "_mask_measurement_separation_evaluation": nullcontext,
        }

        def base(_root: Path) -> dict[str, object]:
            return smoke

        return {"_base": base}

    monkeypatch.setattr(runpy, "run_path", fake_run_path)

    def expected_smoke_hash(_path: Path) -> str:
        return completion["_SMOKE_EVALUATOR_SHA256"]

    completion["_install_mask_separation"].__globals__["file_sha256"] = (
        expected_smoke_hash
    )
    compiler: dict[str, object] = {}

    with completion["_install_mask_separation"](frozen):
        frozen["_install_prospective_compiler"](compiler, object(), "config")

    assert events == ["historical", "separated"]
    assert not callable(compiler["_continuum_image_observations"])


def test_review_and_decision_bind_exact_completion() -> None:
    """The final authority binds the program and all preserved identities."""
    if not _REVIEW.is_file() or not _DECISION.is_file():
        pytest.skip(
            "identity packet is frozen after implementation validation"
        )
    review = json.loads(_REVIEW.read_text(encoding="utf-8"))
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))

    assert review["status"] == "reviewed-evaluation-only-completion"
    assert review["verified_composition"]["completion_program_sha256"] == (
        file_sha256(_PROGRAM)
    )
    assert decision["identity_review"] == {
        "path": str(_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_REVIEW),
    }
    assert decision["evaluation_only_completion_authorized"] is True
    assert not any(decision["prohibited_authorizations"].values())
