"""Freeze sanitized package and tool provenance from reference campaigns."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    """Parse the four corrected campaign roots and output path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-compact", required=True, type=Path)
    parser.add_argument("--master-compact", required=True, type=Path)
    parser.add_argument("--release-representative", required=True, type=Path)
    parser.add_argument("--master-representative", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value with canonical separators."""
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_campaign(path: Path) -> dict[str, Any]:
    """Load the index and first measured raw run from one campaign."""
    index = json.loads(
        (path / "baseline-index.json").read_text(encoding="utf-8")
    )
    run_path = path / index["runs"][index["warmups"]]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    return {"index": index, "run": run}


def _sanitized_inventory(run: dict[str, Any]) -> list[dict[str, str]]:
    """Retain names and versions while dropping machine-local URLs."""
    return [
        {"name": item["name"], "version": item["version"]}
        for item in run["dependency_inventory"]
    ]


def _require_shared(campaigns: dict[str, dict[str, Any]], field: str) -> Any:
    """Require one index field to be identical across all campaigns."""
    values = [campaign["index"][field] for campaign in campaigns.values()]
    if any(value != values[0] for value in values[1:]):
        raise ValueError(f"campaign index field {field!r} differs")
    return values[0]


def _environment(
    compact: dict[str, Any], representative: dict[str, Any]
) -> dict[str, Any]:
    """Freeze one reference environment after cross-dataset validation."""
    compact_run = compact["run"]
    representative_run = representative["run"]
    stable_fields = (
        "container_image_digest",
        "dependency_inventory_sha256",
        "environment",
        "environment_sha256",
        "reference",
        "software",
    )
    for field in stable_fields:
        if compact_run[field] != representative_run[field]:
            raise ValueError(f"reference environment field {field!r} differs")
    inventory = _sanitized_inventory(compact_run)
    if inventory != _sanitized_inventory(representative_run):
        raise ValueError("sanitized package inventory differs by dataset")
    return {
        "container_image_digest": compact_run["container_image_digest"],
        "environment": compact_run["environment"],
        "environment_sha256": compact_run["environment_sha256"],
        "installed_distributions": inventory,
        "raw_dependency_inventory_sha256": compact_run[
            "dependency_inventory_sha256"
        ],
        "sanitized_inventory_sha256": _canonical_sha256(inventory),
        "software": compact_run["software"],
    }


def main() -> None:
    """Validate, sanitize, and write durable reference provenance."""
    args = _parse_args()
    campaigns = {
        "release_compact": _load_campaign(args.release_compact),
        "master_compact": _load_campaign(args.master_compact),
        "release_representative": _load_campaign(args.release_representative),
        "master_representative": _load_campaign(args.master_representative),
    }
    configurations = {
        campaign["run"]["configuration_sha256"]
        for campaign in campaigns.values()
    }
    if len(configurations) != 1:
        raise ValueError("reference scientific configurations differ")
    document = {
        "campaigns": {
            name: {
                "dataset_id": campaign["index"]["dataset_id"],
                "input_sha256": campaign["index"]["input_sha256"],
                "reference": campaign["index"]["reference"],
                "repetitions": campaign["index"]["repetitions"],
                "warmups": campaign["index"]["warmups"],
            }
            for name, campaign in campaigns.items()
        },
        "configuration": next(iter(campaigns.values()))["run"][
            "configuration"
        ],
        "configuration_sha256": configurations.pop(),
        "environments": {
            "master": _environment(
                campaigns["master_compact"],
                campaigns["master_representative"],
            ),
            "release": _environment(
                campaigns["release_compact"],
                campaigns["release_representative"],
            ),
        },
        "limitations": [
            "Container and restricted representative inputs are retained "
            "locally; no durable remote artifact locator is yet approved.",
            "Machine-local direct URLs are redacted from the durable package "
            "list; the canonical raw inventory hashes remain recorded.",
        ],
        "lsmtool_checkout": _require_shared(campaigns, "lsmtool_checkout"),
        "rapthor_checkout": _require_shared(campaigns, "rapthor_checkout"),
        "schema_version": 1,
        "tool_sha256": _require_shared(campaigns, "tool_sha256"),
        "tree_hash_exclusions": _require_shared(
            campaigns, "tree_hash_exclusions"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
