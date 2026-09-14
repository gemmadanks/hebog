"""Read-only admission of retained R6 evidence for a future continuation.

This module deliberately has no evaluation or finder execution entry point.
The inventory is provenance, not a scientific decision or retry authority.
"""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validation.source_catalogue_campaign_evidence import (
    load_image_records,
)
from scripts.validation.source_catalogue_input_evaluation import (
    native_artifacts,
)
from scripts.validation.source_catalogue_replay_plan import binding, read_bound
from scripts.validation.source_catalogue_retained_measurements import (
    capture_science_sha256,
    checked_artifact,
)

from hebog.validation.diagnostic_retention import _verify_record_digest
from hebog.validation.external_runners import canonical_sha256


def _completed_records(pair: dict[str, Any], marker: Path) -> dict[str, Any]:
    """Reject a bad completion; it must never become permission to rescore."""
    completed = read_bound(binding(marker))
    if completed["input_id"] != pair["input_id"]:
        raise ValueError("completion input identity changed")
    records = load_image_records(
        completed["records"],
        [(pair["input_id"], finder) for finder in pair["captures"]],
    )
    expected_paths = {
        str(marker.parent / f"{finder}.json") for finder in pair["captures"]
    }
    if {row["path"] for row in completed["records"]} != expected_paths:
        raise ValueError("completion record path identity changed")
    for record in records:
        if (
            type(record["schema_version"]) is not int
            or record["schema_version"] != 1
            or record["lane"] != pair["lane"]
            or record["capture"] != pair["captures"][record["finder_id"]]
        ):
            raise ValueError(
                "completed record schema or capture identity changed"
            )
        if pair["lane"] == "continuum":
            diagnostic = record["source_diagnostics"]
            _verify_record_digest(diagnostic)
            if (
                type(diagnostic["schema_version"]) is not int
                or diagnostic["schema_version"] != 1
                or diagnostic["input_id"] != pair["input_id"]
                or diagnostic["finder_id"] != record["finder_id"]
                or any(
                    type(row["support_label"]) is not int
                    or row["support_label"] <= 0
                    for row in diagnostic["source_records"]
                )
            ):
                raise ValueError(
                    "historical source diagnostic identity changed"
                )
    return completed


def collect_completed_evaluations(
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify completed records without evaluating or rewriting them."""
    if len({row["input_id"] for row in pairs}) != len(pairs):
        raise ValueError("retained pair census is duplicated")
    markers: list[dict[str, str]] = []
    partial: list[dict[str, str]] = []
    partial_directories: list[str] = []
    pending: list[str] = []
    completed_rows: list[dict[str, Any]] = []
    for pair in sorted(pairs, key=lambda row: row["input_id"]):
        directory = Path(pair["evaluation_directory"])
        if directory.resolve() != directory.absolute():
            raise ValueError("evaluation directory identity is a symlink")
        marker = directory / "complete.json"
        if marker.exists() or marker.is_symlink():
            completed_rows.append(_completed_records(pair, marker))
            markers.append(binding(marker))
        else:
            pending.append(pair["input_id"])
            if directory.exists():
                if not directory.is_dir():
                    raise ValueError("partial evaluation is not a directory")
                partial_directories.append(str(directory))
                # Record incomplete bytes for preservation, never for reuse.
                partial.extend(
                    binding(path) for path in sorted(directory.iterdir())
                )
    markers.sort(key=lambda row: row["path"])
    return {
        "complete_input_count": len(markers),
        "complete_finder_record_count": sum(
            len(row["records"]) for row in completed_rows
        ),
        "complete_markers": markers,
        "complete_marker_set_sha256": canonical_sha256(markers),
        "completed_evaluations": completed_rows,
        "pending_input_ids": pending,
        "partial_files": partial,
        "partial_directories": partial_directories,
    }


def verify_capture_seal(
    plan: dict[str, Any],
    plan_binding: dict[str, str],
    seal_binding: dict[str, str],
) -> list[dict[str, Any]]:
    """Verify every sealed capture against the original execution task."""
    seal = read_bound(seal_binding)
    if (
        seal["launch"]["plan"] != plan_binding
        or seal["launch"]["execution_revision"] != plan["execution_revision"]
        or seal["pair_set_sha256"] != canonical_sha256(seal["pairs"])
    ):
        raise ValueError("capture seal launch or product-set identity changed")
    expected = {
        str(Path(task["output_directory"]) / "pair.json"): task
        for task in plan["tasks"]
    }
    if len(expected) != len(plan["tasks"]) or sorted(
        row["path"] for row in seal["pairs"]
    ) != sorted(expected):
        raise ValueError("sealed capture pair census changed")
    pairs = []
    for entry in seal["pairs"]:
        pair = read_bound(entry)
        task = expected[entry["path"]]
        if (
            {
                key: value
                for key, value in pair.items()
                if key not in {"captures", "evaluation_directory"}
            }
            != {key: value for key, value in task.items() if key != "captures"}
            or pair["evaluation_directory"]
            != str(Path(task["output_directory"]) / "evaluation")
            or set(pair["captures"])
            != set(task["captures"]) | {"current-hebog", "incumbent-hebog"}
            or any(
                pair["captures"][finder] != value
                for finder, value in task["captures"].items()
            )
        ):
            raise ValueError("captured task identity changed")
        current = pair["captures"]["current-hebog"]
        incumbent = pair["captures"]["incumbent-hebog"]
        if current["path"] != str(
            Path(task["output_directory"]) / "current/capture.json"
        ) or incumbent["path"] != str(
            Path(task["output_directory"]) / "incumbent/complete.json"
        ):
            raise ValueError("capture path identity changed")
        _verify_current_capture(current, pair, plan)
        historical = read_bound(incumbent)
        if historical["input_id"] != task["input_id"] or any(
            historical[key] != plan["incumbent"][key]
            for key in ("configuration_sha256", "source_tree_sha256")
        ):
            raise ValueError("incumbent capture identity changed")
        native_artifacts(Path(incumbent["path"]), incumbent["sha256"])
        pairs.append(pair)
    return pairs


def _verify_current_capture(
    capture: dict[str, str], pair: dict[str, Any], plan: dict[str, Any]
) -> None:
    """Hash native products without loading scientific image planes."""
    record = read_bound(capture)
    _verify_record_digest(record)
    inputs = read_bound(pair["input_manifest"])
    image = next(row for row in inputs["artifacts"] if row["role"] == "image")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["input_id"] != pair["input_id"]
        or record["finder_id"] != "current-hebog"
        or record["input_sha256"] != image["sha256"]
        or record["configuration_sha256"]
        != plan["candidate"]["configuration_sha256"]
    ):
        raise ValueError("current capture identity changed")
    for family in ("planes", "catalogues"):
        for artifact in record[family].values():
            checked_artifact(Path(capture["path"]).parent, artifact)


def verify_retained_dask(
    plan: dict[str, Any],
    pairs: list[dict[str, Any]],
    dask_binding: dict[str, str],
) -> None:
    """Authenticate the existing comparisons without creating a scheduler."""
    comparisons = read_bound(dask_binding)["comparisons"]
    if sorted(row["input_id"] for row in comparisons) != sorted(
        plan["dask_input_ids"]
    ):
        raise ValueError("retained Dask census changed")
    indexed = {pair["input_id"]: pair for pair in pairs}
    for row in comparisons:
        pair = indexed[row["input_id"]]
        _verify_current_capture(row["capture"], pair, plan)
        serial = capture_science_sha256(
            Path(pair["captures"]["current-hebog"]["path"])
        )
        dask = capture_science_sha256(Path(row["capture"]["path"]))
        if (
            row["pass"] is not True
            or serial != row["serial_science_sha256"]
            or dask != row["dask_science_sha256"]
            or serial != dask
        ):
            raise ValueError("retained Dask comparison identity changed")
