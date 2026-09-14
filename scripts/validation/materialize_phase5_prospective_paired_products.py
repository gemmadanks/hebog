#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Materialize one exact full-population prospective paired candidate."""

from __future__ import annotations

import argparse
import json
import runpy
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

_BASE_MATERIALIZER = (
    "scripts/validation/materialize_phase5_prospective_hebog_products.py"
)
_PUBLICATION_MATERIALIZER = (
    "scripts/validation/"
    "materialize_phase5_prospective_publication_scale_persistence_products.py"
)


def _load_materializer(root: Path) -> dict[str, Any]:
    """Compose the current science onto the immutable generalized producer."""
    publication = runpy.run_path(str(root / _PUBLICATION_MATERIALIZER))
    materializer = runpy.run_path(str(root / _BASE_MATERIALIZER))
    publication["_install_materializer_overrides"](materializer)
    materializer.update(
        {
            name: publication[name]
            for name in (
                "_composition",
                "_current_composition",
                "_current_configuration",
                "_generate_product",
                "_verified_reference",
            )
        }
    )
    return materializer


def _expected_selected_input_count_record(population: object) -> int:
    """Read one exact positive cardinality from a frozen population."""
    if not isinstance(population, dict):
        raise ValueError("prospective paired population is malformed")
    selection = population.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("prospective paired population selection is absent")
    count = selection.get("selected_input_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("prospective paired selected input count is invalid")
    return count


def _expected_selected_input_count(population: Path) -> int:
    """Return the cardinality declared by one exact population file."""
    return _expected_selected_input_count_record(
        json.loads(population.read_text(encoding="utf-8"))
    )


def _candidate_tasks(
    arguments: argparse.Namespace,
) -> tuple[dict[str, Any], ...]:
    """Build one full task set and bind the exact scientific revision."""
    materializer = _load_materializer(arguments.tooling_root)
    tasks = cast(
        tuple[dict[str, Any], ...], materializer["_candidate_tasks"](arguments)
    )
    if not tasks:
        raise ValueError("prospective paired candidate tasks are empty")
    if arguments.candidate_mode == "current":
        expected = (
            arguments.candidate_revision,
            arguments.candidate_source_tree_sha256,
            arguments.candidate_configuration_sha256,
        )
        if any(not isinstance(value, str) or not value for value in expected):
            raise ValueError("prospective current identity is incomplete")
        identities = {
            (task["source_tree_sha256"], task["configuration_sha256"])
            for task in tasks
        }
        if identities != {(expected[1], expected[2])}:
            raise ValueError("prospective current scientific identity changed")
        return tuple(
            {**task, "candidate_revision": expected[0]} for task in tasks
        )
    if any(
        value is not None
        for value in (
            arguments.candidate_revision,
            arguments.candidate_source_tree_sha256,
            arguments.candidate_configuration_sha256,
        )
    ):
        raise ValueError("prospective incumbent identity must be inherited")
    return tasks


def _generate_product(task: dict[str, object]) -> str:
    """Generate one candidate product through an importable process target."""
    root = Path(cast(str, task["tooling_root"]))
    materializer = _load_materializer(root)
    return cast(str, materializer["_generate_product"](task))


def _parse_args() -> argparse.Namespace:
    """Parse one exact full-population producer invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--tooling-root", required=True, type=Path)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--source-request", required=True, type=Path)
    parser.add_argument("--population", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument(
        "--candidate-mode", choices=("current", "incumbent"), required=True
    )
    parser.add_argument("--candidate-revision")
    parser.add_argument("--candidate-source-tree-sha256")
    parser.add_argument("--candidate-configuration-sha256")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Verify or materialize one complete write-once candidate product set."""
    arguments = _parse_args()
    arguments.repository_root = arguments.repository_root.resolve()
    arguments.tooling_root = arguments.tooling_root.resolve()
    if arguments.workers < 1:
        raise ValueError("prospective paired workers must be positive")
    tasks = _candidate_tasks(arguments)
    expected_count = _expected_selected_input_count(arguments.population)
    if len(tasks) != expected_count:
        raise ValueError(
            "prospective paired task count differs from population"
        )
    identities = {
        "candidate_mode": arguments.candidate_mode,
        "candidate_revision": tasks[0]["candidate_revision"],
        "candidate_source_tree_sha256": tasks[0]["source_tree_sha256"],
        "candidate_configuration_sha256": tasks[0]["configuration_sha256"],
        "selected_input_count": len(tasks),
    }
    if arguments.verify_only:
        if arguments.scratch.exists():
            raise FileExistsError(
                "prospective paired verify-only scratch already exists"
            )
        print(json.dumps(identities, allow_nan=False, sort_keys=True))
        return
    arguments.scratch.mkdir(parents=True, exist_ok=False)
    with (
        (arguments.scratch / "progress.log").open(
            "a", encoding="utf-8"
        ) as progress,
        ProcessPoolExecutor(max_workers=arguments.workers) as executor,
    ):
        futures = {executor.submit(_generate_product, task) for task in tasks}
        for completed, future in enumerate(as_completed(futures), start=1):
            input_id = future.result()
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{expected_count} input={input_id}\n"
            )
            progress.flush()
    print(json.dumps(identities, allow_nan=False, sort_keys=True))
    print(arguments.scratch)


if __name__ == "__main__":
    main()
