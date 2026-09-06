"""Regression tests for the compact-sentinel stable-identity repair."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits

from hebog.data_models.source_association import DetectionComponentRecord
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import (
    continuum_catalogue_objects,
)

_ROOT = Path(__file__).parents[3]
_REPAIR = (
    _ROOT / "scripts/validation/repair_phase5_compact_sentinel_identity.py"
)
_RUNNER = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_sentinel_identity_repair.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_compact_sentinel_identity_repair.py"
)
link_stable_component_ownership = runpy.run_path(str(_REPAIR))[
    "link_stable_component_ownership"
]


def _header() -> fits.Header:
    """Return a small valid celestial WCS."""
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 1.0
    header["CRPIX2"] = 1.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    return header


def _source(identifier: str) -> CatalogueSource:
    """Return one current public Gaussian component row."""
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=2.0,
        association_integrated_flux_jy=2.0,
        island_identifier=identifier,
    )


def _component(identifier: str, label: int) -> DetectionComponentRecord:
    """Return one stable component-to-label association record."""
    return DetectionComponentRecord(
        component_id=identifier,
        label_value=label,
        canonical_pixel_yx=(0, 0),
        centroid_yx=(0.0, 0.0),
        covariance_pixels_squared=None,
    )


def test_stable_component_identities_link_to_exact_native_labels() -> None:
    """Current public IDs must use recorded ownership, not legacy parsing."""
    labels = np.asarray(((2, 0, 7), (2, 7, 7)), dtype=np.int32)
    catalogue = (_source("component-alpha"), _source("component-beta"))
    records = (
        _component("component-alpha", 2),
        _component("component-beta", 7),
    )

    linked = link_stable_component_ownership(catalogue, records, labels)
    compiled = continuum_catalogue_objects(
        linked,
        labels,
        finder_id="hebog",
        header=_header(),
    )

    assert tuple(item.identifier for item in compiled) == (
        "component-alpha",
        "component-beta",
    )
    assert tuple(item.support_label for item in compiled) == (2, 7)


def test_identity_link_rejects_missing_or_inconsistent_ownership() -> None:
    """No stable row may be assigned by position or an unrelated identity."""
    labels = np.asarray(((1, 0), (0, 0)), dtype=np.int32)

    with pytest.raises(ValueError, match="has no component record"):
        link_stable_component_ownership(
            (_source("component-missing"),),
            (_component("component-known", 1),),
            labels,
        )
    inconsistent = replace(
        _source("component-known"),
        island_identifier="component-other",
    )
    with pytest.raises(ValueError, match="identity and ownership disagree"):
        link_stable_component_ownership(
            (inconsistent,),
            (_component("component-known", 1),),
            labels,
        )


def test_identity_link_rejects_malformed_or_absent_native_labels() -> None:
    """Association metadata must agree with the measured label plane."""
    with pytest.raises(ValueError, match="two-dimensional integer"):
        link_stable_component_ownership(
            (_source("component-known"),),
            (_component("component-known", 1),),
            np.ones((1, 1), dtype=np.float64),
        )
    with pytest.raises(ValueError, match="absent from measurement labels"):
        link_stable_component_ownership(
            (_source("component-known"),),
            (_component("component-known", 2),),
            np.ones((1, 1), dtype=np.int32),
        )


def test_identity_link_allows_fitless_component_records() -> None:
    """Fitless native components remain valid support objects."""
    labels = np.asarray(((1, 2), (0, 0)), dtype=np.int32)

    linked = link_stable_component_ownership(
        (_source("component-fitted"),),
        (
            _component("component-fitted", 1),
            _component("component-fitless", 2),
        ),
        labels,
    )

    assert len(linked) == 1
    assert linked[0].island_identifier == "hebog-segment-1"


def test_repaired_runner_links_captured_public_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact public runner must pass stable ownership to the compiler."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    labels = np.asarray(((1, 0), (0, 0)), dtype=np.int32)
    source = _source("component-stable")
    terminal = SimpleNamespace(
        component_catalogue=(source,),
        measurement_component_labels=labels,
        source_association=SimpleNamespace(
            components=(_component("component-stable", 1),)
        ),
    )
    captured_arguments: dict[str, object] = {}

    class Capture:
        def __enter__(self) -> list[object]:
            return [SimpleNamespace(terminal=terminal)]

        def __exit__(self, *_arguments: object) -> None:
            return None

    monkeypatch.setattr(parent, "_captured_science", Capture)

    def find_sources(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(gaussian_component_count=1)

    monkeypatch.setattr(parent.hebog, "find_sources", find_sources)

    def compile_summary(**arguments: object) -> dict[str, object]:
        captured_arguments.update(arguments)
        return {"status": "compiled"}

    monkeypatch.setattr(parent, "compile_finder_summary", compile_summary)
    input_path = tmp_path / "input.fits"
    fits.PrimaryHDU(data=np.ones((2, 2)), header=_header()).writeto(input_path)

    result = program["_run_hebog_repaired"](
        dataset=SimpleNamespace(identifier="fixture"),
        recipe=SimpleNamespace(seed=1),
        input_path=input_path,
        output=tmp_path / "output",
        executor=object(),
        review=object(),
    )

    linked = cast(tuple[CatalogueSource, ...], captured_arguments["catalogue"])
    assert linked[0].identifier == "component-stable"
    assert linked[0].island_identifier == "hebog-segment-1"
    assert result == {"status": "compiled"}


def test_repaired_runner_temporarily_replaces_both_execution_seams() -> None:
    """Serial pairs and Dask comparisons must share the repaired adapter."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    original_hebog = parent._run_hebog
    original_pair = parent._pair_worker

    with program["_configured_parent"]():
        assert parent._run_hebog is program["_run_hebog_repaired"]
        assert parent._pair_worker is program["_pair_worker_repaired"]

    assert parent._run_hebog is original_hebog
    assert parent._pair_worker is original_pair


def test_repaired_runner_binds_the_failed_attempt() -> None:
    """The retry cannot detach from the preserved terminal failure."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))

    program["_require_failed_lineage"]()


def test_repair_identity_preserves_science_and_changes_only_run_paths() -> (
    None
):
    """The replacement freezes the same science in a new write-once lane."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    implementation, identity = freezer["build_records"](_ROOT)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"]["source_tree_sha256"] == (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    )
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["population"]["image_count"] == 168
    assert identity["expected_execution"]["output"].endswith(
        "compact-held-out-sentinel-identity-repair.json"
    )
    assert implementation["repair"] == {
        "identifier_parsing_used": False,
        "positional_inference_used": False,
        "source_association_component_label_mapping_used": True,
    }
    for binding in identity["program_bindings"].values():
        assert Path(binding["path"]).is_relative_to("scripts") or Path(
            binding["path"]
        ).is_relative_to("src")
        assert len(binding["sha256"]) == 64


def test_repair_freezer_refuses_any_existing_target(tmp_path: Path) -> None:
    """No partial identity set may overwrite a prior repair review."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    identity = tmp_path / freezer["_IDENTITY"]
    identity.parent.mkdir(parents=True)
    identity.write_text("existing\n", encoding="utf-8")
    arguments = argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](arguments)

    assert identity.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / freezer["_IMPLEMENTATION"]).exists()


def test_repair_review_records_the_exact_retry_authority() -> None:
    """The evaluator repair cannot broaden the approved scientific scope."""
    review = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-compact-held-out-sentinel-identity-repair-pre-review.json"
        ).read_text(encoding="utf-8")
    )

    assert review["authorization"]["evaluator_repair_authorized"] is True
    assert review["authorization"]["held_out_retry_authorized"] is True
    assert review["authorization"]["source_finding_change_authorized"] is False
    assert review["scientific_invariants"]["total_finder_executions"] == 348
