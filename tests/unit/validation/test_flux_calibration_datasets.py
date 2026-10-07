"""Tests for the committed M1 flux and uncertainty calibration population."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    iter_dataset_recipes,
    load_dataset_manifest,
)

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config/datasets/m1-flux-calibration.json"
_BUILDER = _ROOT / "scripts/validation/build_flux_calibration_datasets.py"
_COMPARISON = _ROOT / "scripts/validation/compare_flux_calibration.py"
# The 23 September population was generated outside any manifest, with
# generator versions 2 and 3, so its seeds are named here.
_SUPERSEDED_POPULATION_SEEDS = frozenset(range(2026091700, 2026091710))
_REALIZATIONS_PER_NOISE_CLASS = 5


def test_committed_manifest_matches_its_builder() -> None:
    """The population is regenerated only through its builder."""
    builder = runpy.run_path(str(_BUILDER))

    built = json.dumps(builder["build_manifest"](), indent=2, sort_keys=True)

    assert _MANIFEST.read_text(encoding="utf-8") == built + "\n"


def test_population_holds_version_four_realizations_per_noise_class() -> None:
    """Five version 4 realizations per noise class, named as compared."""
    datasets = load_dataset_manifest(_MANIFEST).datasets
    white = [
        dataset.identifier
        for dataset in datasets
        if dataset.recipe.noise_correlation is None
    ]
    correlated = [
        dataset.identifier
        for dataset in datasets
        if dataset.recipe.noise_correlation is not None
    ]

    assert {dataset.role for dataset in datasets} == {DatasetRole.DEVELOPMENT}
    assert {dataset.recipe.generator_version for dataset in datasets} == {4}
    assert {dataset.recipe.shape_yx for dataset in datasets} == {(1024, 1024)}
    assert {len(dataset.recipe.sources) for dataset in datasets} == {64}
    # compare_flux_calibration.py reads the noise class from the identifier.
    assert white == [
        f"calibration-white-{index}"
        for index in range(_REALIZATIONS_PER_NOISE_CLASS)
    ]
    assert correlated == [
        f"calibration-correlated-{index}"
        for index in range(_REALIZATIONS_PER_NOISE_CLASS)
    ]


def test_population_seeds_are_disjoint_from_every_other_population() -> None:
    """New seeds repeat neither a manifest nor the superseded population."""
    seeds = [
        recipe.seed
        for dataset in load_dataset_manifest(_MANIFEST).datasets
        for recipe in iter_dataset_recipes(dataset)
    ]

    assert len(set(seeds)) == len(seeds)
    assert _SUPERSEDED_POPULATION_SEEDS.isdisjoint(seeds)
    for path in (_ROOT / "config/datasets").glob("*.json"):
        if path == _MANIFEST:
            continue
        other = DatasetManifest.model_validate_json(path.read_bytes())
        assert set(seeds).isdisjoint(
            recipe.seed
            for dataset in other.datasets
            for recipe in iter_dataset_recipes(dataset)
        ), path.name


@pytest.fixture(scope="module")
def comparison() -> dict[str, Any]:
    """Load the comparison script's functions without running it."""
    return runpy.run_path(str(_COMPARISON), run_name="comparison")


def _case(
    hebog_run: Path,
    reference: Path,
    case: str,
    *,
    reference_image: bytes,
) -> None:
    """Write one Hebog case and one PyBDSF case with the given image."""
    (hebog_run / f"{case}.json").write_text("{}", encoding="utf-8")
    (hebog_run / f"{case}.fits").write_bytes(b"image " + case.encode())
    (reference / case).mkdir(parents=True)
    (reference / case / f"{case}.fits").write_bytes(reference_image)
    for name in ("source_catalog.fits", "gaussian_catalog.fits"):
        (reference / case / name).write_bytes(b"catalogue")


def test_comparison_orders_cases_white_first_and_by_index(
    comparison: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Case order, which the bootstrap draws in, is not lexical."""
    for case in (
        "calibration-correlated-0",
        "calibration-white-10",
        "calibration-white-2",
    ):
        (tmp_path / f"{case}.json").write_text("{}", encoding="utf-8")

    assert comparison["_cases"](tmp_path) == [
        "calibration-white-2",
        "calibration-white-10",
        "calibration-correlated-0",
    ]


def test_comparison_refuses_a_reference_of_other_images(
    comparison: dict[str, Any],
    tmp_path: Path,
) -> None:
    """A PyBDSF case is paired only with the image bytes it processed."""
    hebog_run = tmp_path / "hebog"
    reference = tmp_path / "pybdsf"
    hebog_run.mkdir()
    _case(
        hebog_run,
        reference,
        "calibration-white-0",
        reference_image=b"image calibration-white-0",
    )
    image_sha256 = {
        "calibration-white-0": comparison["_sha256"](
            hebog_run / "calibration-white-0.fits"
        )
    }

    comparison["_require_reference"](hebog_run, reference, image_sha256)
    (
        reference / "calibration-white-0" / "calibration-white-0.fits"
    ).write_bytes(b"an earlier population's image")
    with pytest.raises(SystemExit, match="processed a different image"):
        comparison["_require_reference"](hebog_run, reference, image_sha256)
    (reference / "calibration-white-0" / "gaussian_catalog.fits").unlink()
    with pytest.raises(SystemExit, match="missing"):
        comparison["_require_reference"](hebog_run, reference, image_sha256)
