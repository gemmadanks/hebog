#!/usr/bin/env python3
"""Materialize the mask-origin and sibling-pair prospective candidate."""

from __future__ import annotations

import runpy
import subprocess as _subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256
from hebog.validation.mask_origin_sibling_pair import (
    build_mask_origin_sibling_pair_continuum_products,
    public_finder_mask_origin_sibling_pair_configuration,
)

_BASE_MATERIALIZER = (
    "scripts/validation/"
    "materialize_phase5_prospective_publication_snr_products.py"
)
_PRE_REVIEW = (
    "config/contracts/phase-5-prospective-mask-origin-sibling-pair-"
    "pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    "config/contracts/phase-5-prospective-mask-origin-sibling-pair-"
    "implementation-decision.json"
)

# The frozen evaluator resolves this public module seam from runpy globals.
subprocess = _subprocess


def _base(root: Path) -> dict[str, Any]:
    """Load the exact publication-S/N producer without mutating its bytes."""
    materializer = runpy.run_path(str(root / _BASE_MATERIALIZER))
    current_composition = cast(
        Callable[..., dict[str, Any]], materializer["_current_composition"]
    )
    current_composition.__globals__[
        "build_public_finder_source_reconstruction_continuum_products"
    ] = build_mask_origin_sibling_pair_continuum_products
    materializer[
        "build_public_finder_source_reconstruction_continuum_products"
    ] = build_mask_origin_sibling_pair_continuum_products
    return materializer


def _current_configuration(root: Path) -> str:
    """Return the exact composed prospective candidate identity."""
    materializer = _base(root)
    base = materializer[
        "public_finder_mask_measurement_separation_configuration"
    ](*(root / path for path in materializer["_BASE_CONFIGURATION_PATHS"]))
    publication = materializer[
        "public_finder_publication_snr_repair_configuration"
    ](
        base,
        root / materializer["_PRE_REVIEW"],
        root / materializer["_IMPLEMENTATION_DECISION"],
    )
    repaired = public_finder_mask_origin_sibling_pair_configuration(
        publication,
        root / _PRE_REVIEW,
        root / _IMPLEMENTATION_DECISION,
    )
    return canonical_sha256(repaired)


def _current_composition(
    root: Path,
    *,
    revision: str,
    configuration: str,
) -> dict[str, Any]:
    """Compose the current source tree over the exact predecessor runtime."""
    materializer = _base(root)
    return cast(
        dict[str, Any],
        materializer["_current_composition"](
            root,
            revision=revision,
            configuration=configuration,
        ),
    )


def _verified_reference(root: Path, reference: Path) -> tuple[Any, Any]:
    """Delegate retained-reference verification without changing science."""
    return cast(
        tuple[Any, Any],
        _base(root)["_verified_reference"](root, reference),
    )


def _composition(task: dict[str, object]) -> dict[str, Any]:
    """Load the repaired current or unchanged incumbent producer."""
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
    """Materialize one candidate product through the importable worker."""
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
    """Install overrides in the globals resolved by runpy functions."""
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
    """Run the frozen CLI with the exact prospective composition."""
    root = Path(__file__).resolve().parents[2]
    materializer = _base(root)
    entrypoint = _install_materializer_overrides(materializer)
    entrypoint.__globals__["__file__"] = str(Path(__file__).resolve())
    entrypoint()


if __name__ == "__main__":
    main()
