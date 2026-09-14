#!/usr/bin/env python3
# pyright: reportArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Verify the sealed Phase 5 public population and all of its bindings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_POPULATION_DIRECTORY = (
    _ROOT / "benchmark-results/phase-5/public-comparison-selection"
)
_POPULATION_SHA256 = (
    "0a7c2b18d96ee47277072528949c5a64239f0c3053d5e7b33c03b36c194b7824"
)
_ACQUISITION_SHA256 = (
    "a74e60de95debcc53bdf43d4f6046a6f74befe8a85e849a5b0105f2ecb0bd0ce"
)
_SCHEMA_REVIEW_SHA256 = (
    "409318f58cafe259b4347953051ef8dddcf2308f041e8145e4199f7ad281eed8"
)
_SELECTION_DECISION_SHA256 = (
    "d60fb6454ffc93c240d06e2e40888e1a4d378bc242057276f63a6d82238f565b"
)
_SELECTOR_SHA256 = (
    "0ddbc6566bb9b61dcf135857311068f8d5162eb6d04ff1d8481588c1cd980233"
)
_ADAPTER_SHA256 = (
    "3a3aa7c3118ebb7189e9bbc0363ee3eb04b4baf5f3c0fc08b95fc63a9369beac"
)
_STRATA = (
    "sparse",
    "ordinary",
    "crowded",
    "resolved",
    "close-pair",
    "high-dynamic-range",
    "low-apparent-SNR",
    "primary-beam-boundary",
)
_EXPECTED_SELECTED_COUNT = 8
_EXPECTED_ADMITTED_COUNT = 32
_EXPECTED_CANDIDATE_COUNT = 256
_EXPECTED_TRUTH_EXCLUSIONS = [32_397_377]
_PROGRESS_SHA256 = (
    "e8e81c2b218857560e98b187c13b51b76914d605fd763b7bd5d063940e88cc62"
)


def _json_object(path: Path) -> dict[str, Any]:
    """Load a strict JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def validate_population_document(document: dict[str, Any]) -> None:
    """Validate terminal semantics without opening bound files."""
    sdc1 = cast(dict[str, Any], document.get("sdc1"))
    hydra = cast(dict[str, Any], document.get("hydra"))
    implementation = cast(dict[str, Any], document.get("implementation"))
    authorization = cast(
        dict[str, Any], document.get("selection_authorization")
    )
    schema_review = cast(dict[str, Any], document.get("schema_review"))
    acquisition = cast(dict[str, Any], document.get("acquisition"))
    selected = cast(list[dict[str, Any]], sdc1.get("selected_tiles"))
    if (
        document.get("schema_version") != 1
        or document.get("population_id")
        != "phase-5-public-comparison-selected-population"
        or document.get("status") != "sealed-before-finder-execution"
        or authorization.get("sha256") != _SELECTION_DECISION_SHA256
        or schema_review.get("sha256") != _SCHEMA_REVIEW_SHA256
        or acquisition.get("sha256") != _ACQUISITION_SHA256
        or implementation.get("selector_sha256") != _SELECTOR_SHA256
        or implementation.get("adapter_sha256") != _ADAPTER_SHA256
        or sdc1.get("candidate_tile_count") != _EXPECTED_CANDIDATE_COUNT
        or sdc1.get("admitted_tile_count") != _EXPECTED_ADMITTED_COUNT
        or sdc1.get("excluded_nonfinite_centroid_truth_ids")
        != _EXPECTED_TRUTH_EXCLUSIONS
        or sdc1.get("candidate_output_used") is not False
        or len(selected) != _EXPECTED_SELECTED_COUNT
        or [item.get("stratum") for item in selected] != list(_STRATA)
        or len({item.get("tile", {}).get("tile_id") for item in selected})
        != _EXPECTED_SELECTED_COUNT
        or hydra.get("complete_images_no_crop") is not True
        or hydra.get("published_catalogue_products_opened") is not False
        or document.get("finder_execution_authorized") is not False
        or document.get("finder_outputs_created") is not False
        or document.get("qualification_opened") is not False
        or document.get("cutover_authorized") is not False
        or document.get("release_authorized") is not False
    ):
        raise ValueError("public selected-population semantics are invalid")


def _verify_source_bindings(
    repository_root: Path,
    document: dict[str, Any],
) -> None:
    """Verify all seven original public sources against sealed acquisition."""
    acquisition_binding = cast(dict[str, Any], document["acquisition"])
    acquisition_path = repository_root / cast(str, acquisition_binding["path"])
    if file_sha256(acquisition_path) != _ACQUISITION_SHA256:
        raise ValueError("public acquisition record changed")
    acquisition = _json_object(acquisition_path)
    artifacts = cast(list[dict[str, Any]], acquisition["artifacts"])
    population_artifacts = cast(
        dict[str, dict[str, Any]], acquisition_binding["artifacts"]
    )
    for artifact in artifacts:
        identifier = cast(str, artifact["identifier"])
        path = (
            acquisition_path.parent / "raw" / cast(str, artifact["filename"])
        )
        if population_artifacts.get(identifier) != {
            "filename": artifact["filename"],
            "byte_size": artifact["byte_size"],
            "sha256": artifact["sha256"],
        }:
            raise ValueError("population public-source binding changed")
        if (
            not path.is_file()
            or path.stat().st_size != artifact["byte_size"]
            or file_sha256(path) != artifact["sha256"]
        ):
            raise ValueError(f"public source identity changed: {path}")


def _verify_cutout(
    population_directory: Path,
    selected: dict[str, Any],
) -> set[str]:
    """Verify one selected image, FITS checksum, and truth membership."""
    image = cast(dict[str, Any], selected["image"])
    truth = cast(dict[str, Any], selected["truth"])
    tile = cast(dict[str, Any], selected["tile"])
    image_path = population_directory / cast(str, image["path"])
    truth_path = population_directory / cast(str, truth["path"])
    for path, binding in ((image_path, image), (truth_path, truth)):
        if (
            not path.is_file()
            or path.stat().st_size != binding["byte_size"]
            or file_sha256(path) != binding["sha256"]
        ):
            raise ValueError(f"selected public product changed: {path}")
    with fits.open(image_path, checksum=True, memmap=True) as hdus:
        primary = cast(fits.PrimaryHDU, hdus[0])
        primary_data = primary.data
        if (
            primary_data is None
            or list(primary_data.shape) != image["shape"]
            or primary.verify_checksum() != 1
            or primary.verify_datasum() != 1
        ):
            raise ValueError(f"selected FITS product is invalid: {image_path}")
    identifiers = np.loadtxt(
        truth_path,
        comments="#",
        usecols=(0,),
        dtype=np.int64,
        ndmin=1,
    )
    expected = np.asarray(truth["membership_ids"], dtype=np.int64)
    if (
        len(identifiers) != truth["row_count"]
        or len(identifiers) != tile["source_count"]
        or not np.array_equal(identifiers, expected)
    ):
        raise ValueError(f"selected truth membership changed: {truth_path}")
    return {image_path.name, truth_path.name}


def verify_population(
    *,
    repository_root: Path,
    population_directory: Path,
) -> dict[str, Any]:
    """Verify the complete terminal population and return its record."""
    population_path = population_directory / "population.json"
    if file_sha256(population_path) != _POPULATION_SHA256:
        raise ValueError("public selected-population record changed")
    document = _json_object(population_path)
    validate_population_document(document)
    progress_path = population_directory / "progress.log"
    if file_sha256(progress_path) != _PROGRESS_SHA256:
        raise ValueError("public selected-population progress record changed")
    for binding_name in ("selection_authorization", "schema_review"):
        binding = cast(dict[str, Any], document[binding_name])
        path = repository_root / cast(str, binding["path"])
        if file_sha256(path) != binding["sha256"]:
            raise ValueError(f"public governed binding changed: {path}")
    implementation = cast(dict[str, Any], document["implementation"])
    for path_key, hash_key in (
        ("selector_path", "selector_sha256"),
        ("adapter_path", "adapter_sha256"),
    ):
        path = repository_root / cast(str, implementation[path_key])
        if file_sha256(path) != implementation[hash_key]:
            raise ValueError(f"public implementation changed: {path}")
    _verify_source_bindings(repository_root, document)
    selected = cast(
        list[dict[str, Any]],
        cast(dict[str, Any], document["sdc1"])["selected_tiles"],
    )
    bound_files = {"population.json", "progress.log"}
    membership: set[int] = set()
    for item in selected:
        bound_files.update(_verify_cutout(population_directory, item))
        identifiers = set(
            cast(dict[str, Any], item["truth"])["membership_ids"]
        )
        if membership.intersection(identifiers):
            raise ValueError("selected truth memberships overlap")
        membership.update(identifiers)
    actual_files = {path.name for path in population_directory.iterdir()}
    if actual_files != bound_files:
        raise ValueError("public population contains unbound files")
    return document


def _parse_args() -> argparse.Namespace:
    """Parse the exact terminal population location."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--population-directory",
        type=Path,
        default=_POPULATION_DIRECTORY,
    )
    return parser.parse_args()


def main() -> None:
    """Verify all public population identities and products."""
    document = verify_population(
        repository_root=_ROOT,
        population_directory=_parse_args().population_directory,
    )
    sdc1 = cast(dict[str, Any], document["sdc1"])
    print(
        "public population verified: "
        f"admitted={sdc1['admitted_tile_count']} "
        f"selected={len(sdc1['selected_tiles'])}"
    )


if __name__ == "__main__":
    main()
