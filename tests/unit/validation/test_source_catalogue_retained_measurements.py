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
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

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
    before = {role: file_sha256(path) for role, path in artifacts.items()}
    view = reader.read_pybdsf_sources(artifacts, header)
    assert len(view.sources) == (0 if empty else 1)
    assert len(view.measured_components) == len(rows)
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
