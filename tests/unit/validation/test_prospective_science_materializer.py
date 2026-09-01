# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
"""Fail-closed prospective smoke materializer tests."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.validation.products import load_fits_plane
from hebog.validation.prospective_science_smoke import (
    select_prospective_smoke_inputs,
)
from hebog.validation.source_association_evaluation_repair import (
    associated_source_identifier,
    detection_component_identifier,
)

_ROOT = Path(__file__).parents[3]
_SCRIPT = (
    _ROOT
    / "scripts/validation/materialize_phase5_prospective_hebog_products.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/evaluate_phase5_prospective_science_smoke.py"
)
_REQUEST = (
    _ROOT / "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_POPULATION = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-smoke-population.json"
)


def test_materializer_selection_matches_public_frozen_selector() -> None:
    """The historical-safe selector retains the same exact population."""
    script = runpy.run_path(str(_SCRIPT))

    selected = script["_selected_inputs"](_REQUEST, _POPULATION)

    assert selected == set(
        select_prospective_smoke_inputs(_REQUEST, _POPULATION)
    )


def test_verify_only_does_not_create_scratch(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """A successful no-write preflight leaves its future namespace absent."""
    script = runpy.run_path(str(_SCRIPT))
    scratch = tmp_path / "prospective-smoke"
    task = {
        "candidate_mode": "current",
        "candidate_revision": "candidate-revision",
        "configuration_sha256": "configuration-sha256",
        "source_tree_sha256": "source-tree-sha256",
    }
    main = script["main"]

    def candidate_tasks(_arguments: object) -> tuple[dict[str, str], ...]:
        return (task,) * 128

    main.__globals__["_candidate_tasks"] = candidate_tasks
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(_SCRIPT),
            "--repository-root",
            str(_ROOT),
            "--tooling-root",
            str(_ROOT),
            "--reference-reconstruction",
            str(tmp_path / "reference"),
            "--source-request",
            str(_REQUEST),
            "--population",
            str(_POPULATION),
            "--scratch",
            str(scratch),
            "--candidate-mode",
            "current",
            "--verify-only",
        ],
    )

    main()

    assert not scratch.exists()
    record = json.loads(capsys.readouterr().out)
    assert record == {
        "candidate_configuration_sha256": "configuration-sha256",
        "candidate_mode": "current",
        "candidate_revision": "candidate-revision",
        "candidate_source_tree_sha256": "source-tree-sha256",
        "selected_input_count": 128,
    }


def test_incumbent_composition_uses_separate_tooling_root(
    tmp_path: Path,
) -> None:
    """Historical candidates need not contain later frozen replay tooling."""
    script = runpy.run_path(str(_SCRIPT))
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()
    tooling_root = tmp_path / "tooling"
    wrapper = tooling_root / script["_TERMINAL_PARENT_WRAPPER"]
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        """
def _load_source_association_composition():
    return {}, {}, {}

def _install_terminal_parent_static_seams(frozen):
    frozen["installed"] = True
""",
        encoding="utf-8",
    )

    composition = script["_composition"](
        {
            "candidate_mode": "incumbent",
            "repository_root": str(candidate_root),
            "tooling_root": str(tooling_root),
        }
    )

    assert composition == {"installed": True}


def test_smoke_incumbent_pair_uses_historical_sidecar_compiler(
    tmp_path: Path,
) -> None:
    """Mixed products compile below additive current-only diagnostics."""
    script = runpy.run_path(str(_EVALUATOR))
    installed: list[tuple[object, str]] = []
    paired = object()
    compiler_globals: dict[str, Any] = {}

    def install(
        _globals: dict[str, Any], campaign: object, configuration: str
    ) -> None:
        installed.append((campaign, configuration))

    historical = {"_install_prospective_compiler": install}

    def load_composition() -> tuple[
        dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        return {}, {}, historical

    def install_seams(value: dict[str, Any]) -> None:
        value["schema"] = "terminal-parent"

    parent: dict[str, Any] = {
        "_load_source_association_composition": load_composition,
        "_install_terminal_parent_static_seams": install_seams,
    }

    def compiler(_frozen: dict[str, Any]) -> tuple[dict[str, Any], object]:
        def compile_continuum(
            campaign: object, _registry: object, _root: Path
        ) -> tuple[tuple[object, str], tuple[()]]:
            return (campaign, "compiled"), ()

        compiler_globals["compile_continuum_campaign"] = compile_continuum
        compiler_globals["_continuum_image_observations"] = lambda: None
        return compiler_globals, object()

    def paired_view(
        _current: object,
        _incumbent: object,
        _globals: dict[str, Any],
    ) -> object:
        return paired

    helper = script["_compile_incumbent_pair"]
    helper.__globals__["_compiler"] = compiler
    helper.__globals__["_paired_incumbent_view"] = paired_view

    result = helper(
        parent,
        object(),
        object(),
        tmp_path,
        configuration="current-configuration",
    )

    assert historical["schema"] == "terminal-parent"
    assert installed == [(paired, "current-configuration")]
    assert result == (paired, "compiled")


def test_current_writer_persists_distinct_verified_measurement_labels(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Source topology retains its exact plane beside the published mask."""
    script = runpy.run_path(str(_SCRIPT))
    component_id = detection_component_identifier((0, 1))
    source_id = associated_source_identifier((component_id,))
    association = SourceAssociationResult(
        components=(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=7,
                canonical_pixel_yx=(0, 1),
                centroid_yx=(0.0, 1.0),
                covariance_pixels_squared=None,
            ),
        ),
        edges=(),
        memberships=(CatalogueSourceMembership(source_id, (component_id,)),),
    )
    products = SimpleNamespace(
        catalogue=(),
        detection=SimpleNamespace(
            component_labels=np.asarray(
                ((0, 0, 7), (0, 0, 0)), dtype=np.int32
            ),
            retained_mask=np.asarray(
                ((False, False, True), (False, False, False))
            ),
        ),
        measurement_component_labels=np.asarray(
            ((0, 7, 7), (0, 0, 0)), dtype=np.int32
        ),
        source_association=association,
    )
    writer = script["_write_mask_separated_continuum_products"]
    monkeypatch.setitem(
        writer.__globals__,
        "build_public_finder_source_reconstruction_continuum_products",
        lambda *_args, **_kwargs: products,
    )
    monkeypatch.setitem(
        writer.__globals__,
        "write_comparison_catalogue",
        lambda path, _catalogue: path.write_text("[]\n", encoding="utf-8"),
    )
    monkeypatch.setitem(
        writer.__globals__,
        "load_phase_five_corrective_a_review",
        lambda _path: object(),
    )
    image = tmp_path / "image.fits"
    fits.PrimaryHDU(np.zeros((1, 1, 2, 3))).writeto(image)
    output = tmp_path / "products"
    output.mkdir()

    paths = writer(
        SimpleNamespace(
            beam=SimpleNamespace(
                major_fwhm_pixels=3.0,
                minor_fwhm_pixels=2.0,
                position_angle_degrees=0.0,
            )
        ),
        image_path=image,
        mean_path=image,
        rms_path=image,
        output=output,
        review_path=tmp_path / "review.json",
        canonical_json_bytes=lambda value: (
            json.dumps(value, sort_keys=True) + "\n"
        ).encode(),
    )

    assert set(paths) == {
        "measurement-labels-fits",
        "segment-catalogue-json",
        "segment-labels-fits",
        "segment-mask-fits",
        "source-association-json",
    }
    assert np.array_equal(
        load_fits_plane(paths["measurement-labels-fits"]),
        products.measurement_component_labels,
    )
    assert np.array_equal(
        load_fits_plane(paths["segment-labels-fits"]),
        products.detection.component_labels,
    )


def _write_product(
    scratch: Path,
    input_id: str,
    *,
    configuration: str = "configuration",
    source_tree: str = "source-tree",
) -> None:
    directory = scratch / "products" / input_id
    directory.mkdir(parents=True)
    artifact = directory / "catalogue.json"
    artifact.write_text("{}\n", encoding="utf-8")
    marker = {
        "schema_version": 1,
        "input_id": input_id,
        "configuration_sha256": configuration,
        "source_tree_sha256": source_tree,
        "artifacts": [
            {
                "role": "catalogue-json",
                "relative_path": artifact.name,
                "byte_count": artifact.stat().st_size,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        ],
    }
    (directory / "complete.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )


def test_smoke_evaluator_binds_complete_product_set(tmp_path: Path) -> None:
    """Every marker, artifact, and population member enters one identity."""
    script = runpy.run_path(str(_EVALUATOR))
    scratch = tmp_path / "scratch"
    _write_product(scratch, "input-a")
    _write_product(scratch, "input-b")

    first = script["_verify_product_set"](
        {"input-a", "input-b"},
        scratch,
        configuration="configuration",
        source_tree="source-tree",
    )
    second = script["_verify_product_set"](
        {"input-b", "input-a"},
        scratch,
        configuration="configuration",
        source_tree="source-tree",
    )

    assert first == second
    assert len(first) == 64


def test_smoke_evaluator_rejects_marker_or_population_drift(
    tmp_path: Path,
) -> None:
    """Stale configuration and extra products cannot enter evaluation."""
    script = runpy.run_path(str(_EVALUATOR))
    scratch = tmp_path / "scratch"
    _write_product(scratch, "input-a", configuration="stale")
    with pytest.raises(ValueError, match="product marker changed"):
        script["_verify_product_set"](
            {"input-a"},
            scratch,
            configuration="configuration",
            source_tree="source-tree",
        )

    _write_product(scratch, "unexpected")
    with pytest.raises(ValueError, match="product population changed"):
        script["_verify_product_set"](
            {"input-a"},
            scratch,
            configuration="stale",
            source_tree="source-tree",
        )
