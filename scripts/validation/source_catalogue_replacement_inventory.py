"""Read-only preparation of the v11 candidate and immutable comparator reuse.

This module does not admit execution, create output namespaces or run finders.
The failed terminal supplies provenance, never a transferable verdict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validation.source_catalogue_campaign_evidence import (
    load_image_records,
)
from scripts.validation.source_catalogue_replacement_execution import (
    expected_finders,
)


def retained_inventory(
    pairs: list[dict[str, Any]], images: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Verify full closed census and return only immutable comparator rows."""
    by_input = {row["input_id"]: row for row in pairs}
    indexed = {row["input_id"]: row for row in images}
    if (
        len(by_input) != len(pairs)
        or len(indexed) != len(images)
        or set(indexed) != set(by_input)
    ):
        raise ValueError("closed capture/evaluation census changed")
    retained: list[dict[str, str]] = []
    for identifier, task in sorted(by_input.items()):
        finders = expected_finders(task["lane"])
        if set(task["captures"]) != finders:
            raise ValueError("closed finder capture census changed")
        entries = indexed[identifier]["records"]
        records = load_image_records(
            entries, [(identifier, finder) for finder in finders]
        )
        # The loader's stable input-id sort retains entry order within this
        # single, verified input. Never associate entries across inputs.
        for entry, record in zip(entries, records, strict=True):
            finder = record["finder_id"]
            if (
                type(record["schema_version"]) is not int
                or record["schema_version"] != 1
                or record["lane"] != task["lane"]
                or record["capture"] != task["captures"][finder]
            ):
                raise ValueError(
                    "closed record schema, lane or capture changed"
                )
            if finder != "current-hebog":
                retained.append(
                    {"input_id": identifier, "finder_id": finder, **entry}
                )
    return sorted(
        retained, key=lambda row: (row["input_id"], row["finder_id"])
    )


def replacement_tasks(
    pairs: list[dict[str, Any]],
    *,
    root: Path,
    scratch: Path,
    configuration: dict[str, Any],
) -> list[dict[str, Any]]:
    """Drop the closed current capture and all incumbent execution metadata."""
    keys = (
        "input_id",
        "lane",
        "dataset_identifier",
        "seed",
        "recipe_sha256",
        "input_manifest",
    )
    return [
        {
            **{key: row[key] for key in keys},
            "root": str(root),
            "configuration": configuration,
            "output_directory": str(scratch / "pairs" / row["input_id"]),
            "captures": {
                finder: capture
                for finder, capture in row["captures"].items()
                if finder != "current-hebog"
            },
        }
        for row in sorted(pairs, key=lambda row: row["input_id"])
    ]
