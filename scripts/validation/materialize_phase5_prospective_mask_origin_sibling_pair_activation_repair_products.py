#!/usr/bin/env python3
"""Materialize the activated mask-origin and sibling-pair candidate."""

from __future__ import annotations

import runpy
import subprocess as _subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.mask_origin_sibling_pair import (
    build_mask_origin_sibling_pair_continuum_products,
)

_BASE_MATERIALIZER = (
    "scripts/validation/"
    "materialize_phase5_prospective_mask_origin_sibling_pair_products.py"
)
_PRE_REVIEW = (
    "config/contracts/phase-5-prospective-mask-origin-sibling-pair-"
    "activation-repair-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    "config/contracts/phase-5-prospective-mask-origin-sibling-pair-"
    "activation-repair-implementation-decision.json"
)

subprocess = _subprocess


def _base(root: Path) -> dict[str, Any]:
    """Load the frozen candidate and repair only nested builder dispatch."""
    materializer = runpy.run_path(str(root / _BASE_MATERIALIZER))
    frozen_predecessor_base = cast(
        Callable[[Path], dict[str, Any]], materializer["_base"]
    )

    def activated_predecessor_base(candidate_root: Path) -> dict[str, Any]:
        publication = frozen_predecessor_base(candidate_root)
        publication_base = cast(
            Callable[[Path], dict[str, Any]], publication["_base"]
        )
        publication_base.__globals__[
            "build_publication_snr_repaired_continuum_products"
        ] = build_mask_origin_sibling_pair_continuum_products
        publication["build_publication_snr_repaired_continuum_products"] = (
            build_mask_origin_sibling_pair_continuum_products
        )
        return publication

    frozen_predecessor_base.__globals__["_base"] = activated_predecessor_base
    materializer["_base"] = activated_predecessor_base
    return materializer


def _current_configuration(root: Path) -> str:
    """Bind the wrapper repair over the exact scientific configuration."""
    base_configuration = cast(str, _base(root)["_current_configuration"](root))
    return canonical_sha256(
        {
            "base_configuration_sha256": base_configuration,
            "activation_repair_pre_review_sha256": file_sha256(
                root / _PRE_REVIEW
            ),
            "activation_repair_implementation_decision_sha256": file_sha256(
                root / _IMPLEMENTATION_DECISION
            ),
        }
    )


def _current_composition(
    root: Path,
    *,
    revision: str,
    configuration: str,
) -> dict[str, Any]:
    """Compose the activated writer over the frozen candidate."""
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
    """Load the activated current or unchanged incumbent producer."""
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
    """Materialize one product through the importable repaired worker."""
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
    """Install repair functions in the globals resolved by the frozen CLI."""
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
    """Run the frozen CLI with repaired nested builder activation."""
    root = Path(__file__).resolve().parents[2]
    materializer = _base(root)
    entrypoint = _install_materializer_overrides(materializer)
    entrypoint.__globals__["__file__"] = str(Path(__file__).resolve())
    entrypoint()


if __name__ == "__main__":
    main()
