#!/usr/bin/env python3
"""Materialize the publication-SNR repair on the frozen smoke population."""

from __future__ import annotations

import runpy
import subprocess as _subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import canonical_sha256
from hebog.validation.public_finder_correction import (
    public_finder_mask_measurement_separation_configuration,
)
from hebog.validation.publication_snr_repair import (
    build_publication_snr_repaired_continuum_products,
    public_finder_publication_snr_repair_configuration,
)

_BASE_MATERIALIZER = (
    "scripts/validation/materialize_phase5_prospective_hebog_products.py"
)
_BASE_CONFIGURATION_PATHS = (
    "config/contracts/phase-5-corrective-a-review.json",
    "config/contracts/phase-5-public-finder-correction.json",
    "config/contracts/phase-5-public-finder-source-reconstruction-pre-review.json",
    "config/contracts/phase-5-public-finder-source-reconstruction-implementation-decision.json",
    "config/contracts/phase-5-public-finder-source-reconstruction-root-cause-pre-review.json",
    "config/contracts/phase-5-public-finder-source-reconstruction-root-cause-repair-implementation-decision.json",
    "config/contracts/phase-5-public-finder-source-hierarchy-parent-construction-pre-review.json",
    "config/contracts/phase-5-public-finder-source-hierarchy-parent-construction-implementation-decision.json",
    "docs/reference/phase-5-public-finder-persistent-support-parent-correction.md",
    "config/contracts/phase-5-public-finder-terminal-parent-correction-implementation-decision.json",
    "config/contracts/phase-5-public-finder-terminal-feature-persistence-pre-review.json",
    "config/contracts/phase-5-public-finder-terminal-feature-persistence-implementation-decision.json",
    "config/contracts/phase-5-public-finder-terminal-cycle-eligibility-pre-review.json",
    "config/contracts/phase-5-public-finder-terminal-cycle-eligibility-implementation-decision.json",
    "config/contracts/phase-5-prospective-boundary-refinement-pre-review.json",
    "config/contracts/phase-5-prospective-boundary-refinement-implementation-decision.json",
    "config/contracts/phase-5-prospective-mask-measurement-separation-pre-review.json",
    "config/contracts/phase-5-prospective-mask-measurement-separation-implementation-decision.json",
)
_PRE_REVIEW = (
    "config/contracts/phase-5-prospective-publication-snr-repair-"
    "pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    "config/contracts/phase-5-prospective-publication-snr-repair-"
    "implementation-decision.json"
)

# The frozen evaluator resolves this public module seam from runpy globals.
subprocess = _subprocess


def _base(root: Path) -> dict[str, Any]:
    """Load the byte-frozen predecessor and install only the new builder."""
    materializer = runpy.run_path(str(root / _BASE_MATERIALIZER))
    current_composition = cast(
        Callable[..., dict[str, Any]], materializer["_current_composition"]
    )
    current_composition.__globals__[
        "build_public_finder_source_reconstruction_continuum_products"
    ] = build_publication_snr_repaired_continuum_products
    materializer[
        "build_public_finder_source_reconstruction_continuum_products"
    ] = build_publication_snr_repaired_continuum_products
    return materializer


def _current_configuration(root: Path) -> str:
    """Return the exact publication-SNR repair configuration identity."""
    base = public_finder_mask_measurement_separation_configuration(
        *(root / path for path in _BASE_CONFIGURATION_PATHS)
    )
    repaired = public_finder_publication_snr_repair_configuration(
        base,
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
    """Compose the repaired builder over the exact current predecessor."""
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
    """Load the repaired current producer or unchanged incumbent producer."""
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
    """Materialize one repaired product through the frozen worker seam."""
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
    """Install overlays in the globals actually resolved by runpy functions."""
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
    """Run the frozen CLI with repaired configuration and worker dispatch."""
    root = Path(__file__).resolve().parents[2]
    materializer = _base(root)
    entrypoint = _install_materializer_overrides(materializer)
    entrypoint()


if __name__ == "__main__":
    main()
