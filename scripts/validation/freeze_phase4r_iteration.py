"""Freeze a disjoint Phase 4R noise-realization matrix from a template."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

from hebog.validation.datasets import (
    DatasetManifest,
    SyntheticRecipe,
    recipe_sha256,
)


def _parse_args() -> argparse.Namespace:
    """Parse one immutable derived-matrix request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--identifier", required=True)
    parser.add_argument(
        "--role",
        required=True,
        choices=("development", "regression"),
    )
    parser.add_argument("--first-seed", required=True, type=int)
    parser.add_argument("--realizations", required=True, type=int)
    parser.add_argument("--provenance", required=True)
    return parser.parse_args()


def _derived_document(arguments: argparse.Namespace) -> dict[str, object]:
    """Return a validated single-record manifest with disjoint seeds."""
    if arguments.realizations < 1:
        raise ValueError("realizations must be positive")
    payload = cast(
        dict[str, object],
        json.loads(arguments.template.read_text(encoding="utf-8")),
    )
    datasets = cast(list[dict[str, object]], payload["datasets"])
    if len(datasets) != 1:
        raise ValueError("template must contain exactly one dataset")
    document = deepcopy(payload)
    record = cast(list[dict[str, object]], document["datasets"])[0]
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = arguments.first_seed
    record["identifier"] = arguments.identifier
    record["role"] = arguments.role
    record["purpose"] = (
        "Phase 4R recovery-iteration model-selection development."
        if arguments.role == "development"
        else "Phase 4R recovery-iteration confirmation only."
    )
    record["provenance"] = arguments.provenance
    record["noise_realization_seeds"] = list(
        range(
            arguments.first_seed + 1,
            arguments.first_seed + arguments.realizations,
        )
    )
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    validated = DatasetManifest.model_validate(document)
    return cast(dict[str, object], validated.model_dump(mode="json"))


def main() -> None:
    """Write one canonical manifest without replacing prior evidence."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite frozen manifest: {arguments.output}"
        )
    document = _derived_document(arguments)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
