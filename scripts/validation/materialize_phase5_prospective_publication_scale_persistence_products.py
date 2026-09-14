#!/usr/bin/env python3
"""Materialize the adjacent-scale publication-support candidate."""

from __future__ import annotations

import runpy
import subprocess as _subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256
from hebog.validation.publication_scale_persistence import (
    build_publication_scale_persistence_continuum_products,
    public_finder_publication_scale_persistence_configuration,
)

_BASE_MATERIALIZER = (
    "scripts/validation/"
    "materialize_phase5_prospective_persistent_feature_influence_products.py"
)
_PRE_REVIEW = (
    "config/contracts/"
    "phase-5-prospective-publication-scale-persistence-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    "config/contracts/"
    "phase-5-prospective-publication-scale-persistence-implementation-"
    "decision.json"
)

subprocess = _subprocess


def _base(root: Path) -> dict[str, Any]:
    """Load the exact activated predecessor materializer."""
    return runpy.run_path(str(root / _BASE_MATERIALIZER))


def _current_configuration(root: Path) -> str:
    """Bind the publication correction over the exact predecessor."""
    base_configuration_sha256 = cast(
        str,
        _base(root)["_current_configuration"](root),
    )
    repaired = public_finder_publication_scale_persistence_configuration(
        {
            "compact": {
                "base_configuration_sha256": base_configuration_sha256,
            },
            "continuum": {
                "base_configuration_sha256": base_configuration_sha256,
            },
        },
        root / _PRE_REVIEW,
        root / _IMPLEMENTATION_DECISION,
    )
    return canonical_sha256(repaired)


def _activate_final_writer(composition: dict[str, Any]) -> dict[str, Any]:
    """Install the reviewed builder at the actual nested publication seam."""
    writer = cast(Callable[..., Any], composition["_write_continuum_products"])
    separated_writer = cast(
        Callable[..., Any],
        writer.__globals__["_write_mask_separated_continuum_products"],
    )
    separated_writer.__globals__[
        "build_public_finder_source_reconstruction_continuum_products"
    ] = build_publication_scale_persistence_continuum_products
    return composition


def _current_composition(
    root: Path,
    *,
    revision: str,
    configuration: str,
) -> dict[str, Any]:
    """Compose current science and activate its final publication writer."""
    composition = cast(
        dict[str, Any],
        _base(root)["_current_composition"](
            root,
            revision=revision,
            configuration=configuration,
        ),
    )
    return _activate_final_writer(composition)


def _verified_reference(root: Path, reference: Path) -> tuple[Any, Any]:
    """Delegate exact retained-reference verification unchanged."""
    return cast(
        tuple[Any, Any],
        _base(root)["_verified_reference"](root, reference),
    )


def _composition(task: dict[str, object]) -> dict[str, Any]:
    """Load the current correction or the unchanged incumbent."""
    tooling_root = Path(cast(str, task["tooling_root"]))
    materializer = _base(tooling_root)
    if task["candidate_mode"] == "incumbent":
        return cast(dict[str, Any], materializer["_composition"](task))
    if task["candidate_mode"] != "current":
        raise ValueError("prospective candidate mode is unsupported")
    return _current_composition(
        tooling_root,
        revision=cast(str, task["candidate_revision"]),
        configuration=cast(str, task["configuration_sha256"]),
    )


def _generate_product(task: dict[str, object]) -> str:
    """Materialize one product through an importable worker function."""
    frozen = _composition(task)
    candidate_task = {
        key: value
        for key, value in task.items()
        if key
        not in {
            "candidate_mode",
            "candidate_revision",
            "repository_root",
            "tooling_root",
        }
    }
    return cast(str, frozen["_generate_candidate_product"](candidate_task))


def _install_materializer_overrides(
    materializer: dict[str, Any],
) -> Callable[[], None]:
    """Install this exact identity in the frozen command-line entry point."""
    entrypoint = cast(Callable[[], None], materializer["main"])
    entrypoint.__globals__.update(
        {
            "_current_configuration": _current_configuration,
            "_current_composition": _current_composition,
            "_verified_reference": _verified_reference,
            "_composition": _composition,
            "_generate_product": _generate_product,
        }
    )
    return entrypoint


def main() -> None:
    """Run the frozen CLI with the exact replacement identity."""
    root = Path(__file__).resolve().parents[2]
    materializer = _base(root)
    entrypoint = _install_materializer_overrides(materializer)
    entrypoint.__globals__["__file__"] = str(Path(__file__).resolve())
    entrypoint()


if __name__ == "__main__":
    main()
