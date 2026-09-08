"""Small native-file fixtures for R6 read-only measurement projections."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import json
import runpy
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.source_association import (
    build_detection_component_records,
    reduce_source_associations,
)
from hebog.data_models.source_association import SourceAssociationEdge
from hebog.validation.external_runners import file_sha256
from hebog.validation.products import write_comparison_catalogue

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
reader: Any = importlib.import_module(
    "scripts.validation.source_catalogue_retained_measurements"
)


@pytest.mark.parametrize(
    "defect",
    (None, "hash", "size", "missing", "escape", "absolute", "symlink"),
)
def test_retained_artifacts_fail_closed(
    tmp_path: Path, defect: str | None
) -> None:
    root = tmp_path / "records"
    root.mkdir()
    path = root / "file.json"
    path.write_text("{}\n")
    binding = {
        "path": path.name,
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size,
    }
    if defect == "hash":
        binding["sha256"] = "0" * 64
    elif defect == "size":
        binding["byte_count"] = 100
    elif defect == "missing":
        binding["path"] = "absent.json"
    elif defect == "escape":
        binding["path"] = "../file.json"
    elif defect == "absolute":
        binding["path"] = str(path)
    elif defect == "symlink":
        alias = root / "alias.json"
        alias.symlink_to(path)
        binding["path"] = alias.name
    if defect is None:
        assert reader.checked_artifact(root, binding) == path
    else:
        with pytest.raises(ValueError, match="changed"):
            reader.checked_artifact(root, binding)


@pytest.mark.parametrize("empty", (False, True))
def test_pybdsf_reader_preserves_native_source_flux_and_unowned_mask(
    tmp_path: Path,
    empty: bool,
) -> None:
    header, artifacts = _pybdsf_files(tmp_path, empty=empty)
    before = {role: file_sha256(path) for role, path in artifacts.items()}
    view = reader.read_pybdsf_sources(artifacts, header)
    assert len(view.sources) == (0 if empty else 1)
    assert len(view.measured_components) == (0 if empty else 1)
    if not empty:
        assert view.sources[0].integrated_flux_jy == 3
        assert view.measured_sources[0].integrated_flux_jy == 3
    assert view.publication[5, 5]
    assert view.union_labels[5, 5] == 0
    assert np.isnan(view.background).all()
    assert np.isnan(view.rms).all()
    assert {
        role: file_sha256(path) for role, path in artifacts.items()
    } == before


def _pybdsf_files(
    tmp_path: Path, *, empty: bool = False
) -> tuple[fits.Header, dict[str, Path]]:
    """Write a tiny native source/Gaussian bundle, not campaign evidence."""
    helpers = runpy.run_path(
        str(
            Path(__file__).with_name(
                "test_source_association_evaluation_repair.py"
            )
        )
    )
    header = helpers["_header"]()
    names = (
        "Gaus_id",
        "Isl_id",
        "Source_id",
        "Wave_id",
        "RA",
        "E_RA",
        "DEC",
        "E_DEC",
        "Total_flux",
        "E_Total_flux",
        "Peak_flux",
        "E_Peak_flux",
        "Maj",
        "E_Maj",
        "Min",
        "E_Min",
        "PA",
        "E_PA",
        "DC_Maj",
        "E_DC_Maj",
        "DC_Min",
        "E_DC_Min",
        "DC_PA",
        "E_DC_PA",
    )
    rows = np.zeros(0 if empty else 1, dtype=[(name, "<f8") for name in names])
    for field, value in {
        "RA": 10,
        "DEC": -30,
        "Total_flux": 3,
        "Peak_flux": 1,
        "Maj": 0.002,
        "Min": 0.002,
    }.items():
        rows[field] = value
    artifacts = {}
    for role in ("source-catalogue-fits", "gaussian-catalogue-fits"):
        path = tmp_path / f"{role}.fits"
        fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(rows)]).writeto(path)
        artifacts[role] = path
    labels = np.zeros((8, 8), dtype=np.int32)
    if not empty:
        labels[:2, :2] = 1
    labels[5:7, 5:7] = 2
    for role, values in (
        ("island-labels-fits", labels),
        ("island-mask-fits", (labels > 0).astype(np.uint8)),
    ):
        path = tmp_path / f"{role}.fits"
        fits.PrimaryHDU(values).writeto(path)
        artifacts[role] = path
    return header, artifacts


@pytest.mark.parametrize("reverse", (False, True))
@pytest.mark.parametrize("duplicate_wave", (False, True))
def test_retained_gaussian_membership_includes_native_wave_identity(
    tmp_path: Path, reverse: bool, duplicate_wave: bool
) -> None:
    """Wave-local Gaussian numbers differ from true duplicated native rows."""
    header, artifacts = _pybdsf_files(tmp_path)
    path = artifacts["gaussian-catalogue-fits"]
    rows = np.repeat(cast(np.ndarray, fits.getdata(path, ext=1)), 2)
    rows["Gaus_id"] = 13
    rows["Wave_id"] = (2, 2 if duplicate_wave else 3)
    if reverse:
        rows = rows[::-1].copy()
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(rows)]).writeto(
        path, overwrite=True
    )
    before = {role: file_sha256(path) for role, path in artifacts.items()}
    if duplicate_wave:
        with pytest.raises(ValueError, match=r"membership.*inconsistent"):
            reader.read_pybdsf_sources(artifacts, header)
    else:
        view = reader.read_pybdsf_sources(artifacts, header)
        assert len(view.sources) == 1
        assert view.sources[0].integrated_flux_jy == 3
        assert len(view.measured_components) == 2
        assert {row.identifier for row in view.measured_components} == {
            "pybdsf-island-0-source-0-wave-2-gaussian-13",
            "pybdsf-island-0-source-0-wave-3-gaussian-13",
        }
        assert np.all(view.union_labels[:2, :2] == 1)
        assert view.union_labels[5, 5] == 0
        assert view.publication[5, 5]
    assert {
        role: file_sha256(path) for role, path in artifacts.items()
    } == before


def test_wave_identity_preserves_previously_evaluable_model_partition(
    tmp_path: Path,
) -> None:
    """Native models, not row order or wave ordering, own source support."""
    header, artifacts = _pybdsf_files(tmp_path)
    sources = np.repeat(
        cast(np.ndarray, fits.getdata(artifacts["source-catalogue-fits"], 1)),
        2,
    )
    gaussians = np.repeat(
        cast(
            np.ndarray, fits.getdata(artifacts["gaussian-catalogue-fits"], 1)
        ),
        4,
    )
    sources["Source_id"] = (0, 1)
    sources["Total_flux"] = (3, 7)
    gaussians["Source_id"] = (0, 0, 1, 1)
    gaussians["Gaus_id"] = (1, 10, 2, 21)
    gaussians["Wave_id"] = (3, 0, 1, 2)
    positions = np.asarray(
        WCS(header).celestial.all_pix2world(
            [[1, 1], [1.5, 1], [5, 1], [5.5, 1]], 0
        )
    )
    gaussians["RA"], gaussians["DEC"] = positions.T
    sources["RA"], sources["DEC"] = positions[[0, 2]].T
    labels = np.ones((8, 8), dtype=np.int32)
    labels[6:, :] = 2  # Fitless native island remains published but unowned.
    arguments = {
        "source_table": sources,
        "gaussian_table": gaussians,
        "native_island_labels": labels,
        "header": header,
    }
    previous = reader.native_pybdsf.projection_from_catalogue_tables(
        **arguments
    )
    current = reader.project_pybdsf_source_unions(**arguments)
    reversed_rows = reader.project_pybdsf_source_unions(
        **{
            **arguments,
            "source_table": sources[::-1],
            "gaussian_table": gaussians[::-1],
        }
    )
    assert current.sources == reversed_rows.sources
    assert current.components == reversed_rows.components
    for projection in (previous, reversed_rows):
        np.testing.assert_array_equal(
            current.source_union_label_plane,
            projection.source_union_label_plane,
        )
    assert [row.integrated_flux_jy for row in current.sources] == [3, 7]
    assert set(np.unique(current.source_union_label_plane)) == {
        0,
        1,
        2,
    }
    assert current.unowned_native_support_labels == (2,)


def test_valid_native_source_can_have_no_dominant_pixels(
    tmp_path: Path,
) -> None:
    """Identical centres with unequal amplitudes expose the frozen seam."""
    header, artifacts = _pybdsf_files(tmp_path)
    for role in ("source-catalogue-fits", "gaussian-catalogue-fits"):
        path = artifacts[role]
        rows = np.repeat(cast(np.ndarray, fits.getdata(path, 1)), 2)
        rows["Source_id"] = (0, 1)
        rows["Total_flux"] = (3, 1)
        if role == "gaussian-catalogue-fits":
            rows["Gaus_id"] = (0, 1)
            rows["Peak_flux"] = (2, 1)
        fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(rows)]).writeto(
            path, overwrite=True
        )
    # Do not waive the frozen nonempty-owner rule as an ID repair. A new
    # topology policy must say how this native source remains represented.
    with pytest.raises(ValueError, match="source owns no native pixels"):
        reader.read_pybdsf_sources(artifacts, header)


def test_model_identity_ignores_row_byte_order_but_not_true_duplicates(
    tmp_path: Path,
) -> None:
    """FITS encoding and error bars do not invent distinct native models."""
    _, artifacts = _pybdsf_files(tmp_path)
    rows = np.repeat(
        cast(
            np.ndarray, fits.getdata(artifacts["gaussian-catalogue-fits"], 1)
        ),
        2,
    )
    rows["RA"] = (30, 30.1)
    suffixes = reader._model_suffixes(rows)
    assert len(set(suffixes)) == 2
    assert (
        reader._model_suffixes(rows.astype(rows.dtype.newbyteorder("<")))
        == suffixes
    )
    rows["RA"] = 30
    rows["E_RA"] = (0.01, 0.02)
    with pytest.raises(ValueError, match=r"membership.*inconsistent"):
        reader._model_suffixes(rows)


def test_distinct_native_models_with_repeated_full_key_are_not_dropped(
    tmp_path: Path,
) -> None:
    """A native numbering collision cannot erase a distinct model row."""
    header, artifacts = _pybdsf_files(tmp_path)
    path = artifacts["gaussian-catalogue-fits"]
    rows = np.repeat(cast(np.ndarray, fits.getdata(path, 1)), 2)
    rows["Gaus_id"], rows["Wave_id"] = 16, 2
    positions = np.asarray(
        WCS(header).celestial.all_pix2world([[0, 0], [1, 1]], 0)
    )
    rows["RA"], rows["DEC"] = positions.T
    rows["Total_flux"] = (1, 2)
    views: list[Any] = []
    for ordered in (rows, rows[::-1].copy()):
        fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(ordered)]).writeto(
            path, overwrite=True
        )
        before = file_sha256(path)
        view = reader.read_pybdsf_sources(artifacts, header)
        assert file_sha256(path) == before
        assert view.sources[0].integrated_flux_jy == 3
        assert len(view.measured_components) == 2
        assert len({row.identifier for row in view.measured_components}) == 2
        assert sorted(
            row.integrated_flux_jy for row in view.measured_components
        ) == [1, 2]
        views.append(view)
    assert views[0].sources == views[1].sources
    assert sorted(
        views[0].measured_components, key=lambda row: row.identifier
    ) == sorted(views[1].measured_components, key=lambda row: row.identifier)
    np.testing.assert_array_equal(views[0].union_labels, views[1].union_labels)


@pytest.mark.parametrize("overlap", (False, True))
def test_incumbent_reader_uses_recorded_union_without_regrouping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overlap: bool,
) -> None:
    helpers = runpy.run_path(
        str(
            Path(__file__).with_name(
                "test_source_association_evaluation_repair.py"
            )
        )
    )
    labels = np.asarray(((7, 7, 0, 9, 9), (0, 0, 0, 0, 0)), dtype=np.int32)
    components = build_detection_component_records(
        labels,
        (labels > 0).astype(float),
        np.ones(labels.shape, dtype=np.bool_),
    )
    ids = sorted(row.component_id for row in components)
    association = reduce_source_associations(
        components, (SourceAssociationEdge(ids[0], ids[1], 1.0, 0.5),)
    )
    catalogue = (helpers["_source"](association.memberships[0].source_id, 2),)
    artifacts = {
        role: tmp_path / name
        for role, name in (
            ("segment-catalogue-json", "catalogue.json"),
            ("source-association-json", "association.json"),
            ("segment-labels-fits", "labels.fits"),
            ("segment-mask-fits", "mask.fits"),
        )
    }
    write_comparison_catalogue(artifacts["segment-catalogue-json"], catalogue)
    artifacts["source-association-json"].write_text(
        json.dumps(asdict(association))
    )
    fits.PrimaryHDU(labels).writeto(artifacts["segment-labels-fits"])
    fits.PrimaryHDU((labels > 0).astype(np.uint8)).writeto(
        artifacts["segment-mask-fits"]
    )
    if overlap:
        original = reader.continuum_catalogue_objects_from_association

        def repeated(*args: Any, **kwargs: Any) -> Any:
            return original(*args, **kwargs) * 2

        monkeypatch.setattr(
            reader, "continuum_catalogue_objects_from_association", repeated
        )
        with pytest.raises(ValueError, match="overlaps"):
            reader.read_incumbent_sources(artifacts, helpers["_header"]())
    else:
        view = reader.read_incumbent_sources(artifacts, helpers["_header"]())
        assert len(view.sources) == 1
        assert view.sources[0].integrated_flux_jy == 3.0
        assert np.array_equal(view.union_labels > 0, labels > 0)
        assert set(np.unique(view.union_labels)) == {0, 1}
