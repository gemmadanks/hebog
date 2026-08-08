"""Freeze the seed-disjoint Phase 5 Step 2C-A confirmation population."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    SyntheticRecipe,
    recipe_sha256,
)

_FIRST_SEED = 2026730001
_REALIZATION_COUNT = 100


def _document(template_path: Path) -> dict[str, object]:
    """Derive and validate the frozen confirmation from the reviewed matrix."""
    template = DatasetManifest.model_validate_json(
        template_path.read_text(encoding="utf-8")
    )
    if len(template.datasets) != 1:
        raise ValueError("Phase 5 confirmation requires one template dataset")
    if template.datasets[0].role is not DatasetRole.REGRESSION:
        raise ValueError("Phase 5 confirmation template must be regression")

    document = cast(
        dict[str, object],
        deepcopy(template.model_dump(mode="json")),
    )
    document["manifest_id"] = "phase-5-corrective-a-confirmation"
    record = cast(list[dict[str, object]], document["datasets"])[0]
    record["identifier"] = "phase5-corrective-a-confirmation-1024"
    record["purpose"] = (
        "Independent Step 2C-A confirmation of the frozen astrometry "
        "estimator across every governed Phase 5 stratum."
    )
    record["provenance"] = (
        "Seed-disjoint Phase 5 Step 2C-A confirmation frozen before "
        "estimator selection, implementation, or result generation."
    )
    recipe = cast(dict[str, object], record["recipe"])
    recipe["seed"] = _FIRST_SEED
    record["noise_realization_seeds"] = list(
        range(_FIRST_SEED + 1, _FIRST_SEED + _REALIZATION_COUNT)
    )
    record["recipe_sha256"] = recipe_sha256(
        SyntheticRecipe.model_validate(recipe)
    )
    validated = DatasetManifest.model_validate(document)
    return cast(dict[str, object], validated.model_dump(mode="json"))


def _parse_args() -> argparse.Namespace:
    """Parse paths while keeping all scientific choices fixed in code."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=root / "config/datasets/phase-5-regression.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            root / "config/datasets/phase-5-corrective-a-confirmation.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Write the canonical manifest once without replacing frozen input."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite frozen manifest: {arguments.output}"
        )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            _document(arguments.template),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
