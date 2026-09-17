"""Tests for the isolated PyBDSF baseline entry points."""

from __future__ import annotations

import hashlib
import runpy
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from hebog.validation.products import load_aegean_catalogue


def _script(name: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    root = Path(__file__).parents[3]
    return runpy.run_path(str(root / "scripts" / "benchmark" / name))


def test_reference_configuration_requires_explicit_ordered_thresholds() -> (
    None
):
    """A campaign cannot silently inherit the Rapthor helper defaults."""
    pytest.importorskip(
        "resource",
        reason="the reference runner executes inside a POSIX container",
    )
    namespace = _script("pybdsf_reference_run.py")
    configuration: Callable[[float, float], dict[str, object]] = namespace[
        "_configuration"
    ]

    assert configuration(5.0, 3.0)["threshold_pixel_sigma"] == 5.0
    assert configuration(5.0, 3.0)["threshold_island_sigma"] == 3.0
    with pytest.raises(ValueError, match="0 < island <= detection"):
        configuration(3.0, 5.0)


def test_directory_identity_excludes_mutable_casa_lock_files(
    tmp_path: Path,
) -> None:
    """Opening a Measurement Set must not change its scientific identity."""
    namespace = _script("run_phase0_pybdsf_baseline.py")
    path_sha256: Callable[[Path], str] = namespace["_path_sha256"]
    (tmp_path / "table.dat").write_bytes(b"science")
    (tmp_path / "table.lock").write_bytes(b"first lock state")

    first = path_sha256(tmp_path)
    (tmp_path / "table.lock").write_bytes(b"second lock state")

    assert path_sha256(tmp_path) == first
    assert first != hashlib.sha256(b"science").hexdigest()


def test_notebook_pybdsf_reference_maps_every_atrous_option() -> None:
    """The reference cannot inherit changing PyBDSF wavelet defaults."""
    namespace = _script("run_notebook_reference.py")

    configuration = namespace["pybdsf_configuration"](3)

    assert configuration["thresh_pix"] == 5.0
    assert configuration["thresh_isl"] == 3.0
    assert configuration["atrous_do"] is True
    assert configuration["atrous_bdsm_do"] is True
    assert configuration["atrous_jmax"] == 3
    assert configuration["atrous_lpf"] == "b3"
    assert configuration["atrous_sum"] is True
    assert configuration["atrous_orig_isl"] is False
    assert configuration["rms_box"] == (150, 50)
    assert configuration["rms_box_bright"] == (35, 7)
    assert configuration["ncores"] == 3
    assert "rmsmean_map_filename" not in configuration
    with pytest.raises(ValueError, match="ncores must be positive"):
        namespace["pybdsf_configuration"](0)


def test_notebook_pybdsf_labels_follow_exported_fits_axes() -> None:
    """Internal PyBDSF x/y ranks must match its transposed FITS mask."""
    namespace = _script("run_notebook_reference.py")
    internal_rank = np.asarray(
        ((-1, 0, 0), (1, 1, -1)),
        dtype=np.int32,
    )

    labels = namespace["pybdsf_label_plane"](internal_rank)

    np.testing.assert_array_equal(
        labels,
        np.asarray(((0, 2), (1, 2), (1, 0)), dtype=np.int32),
    )


@pytest.mark.parametrize(
    "rank",
    (
        np.asarray((-1, 0), dtype=np.int32),
        np.asarray(((-1.0, 0.0),), dtype=np.float64),
        np.asarray(((-2, 0),), dtype=np.int32),
    ),
)
def test_notebook_pybdsf_rejects_invalid_internal_ranks(
    rank: np.ndarray,
) -> None:
    """Rank conversion cannot coerce malformed PyBDSF state."""
    namespace = _script("run_notebook_reference.py")

    with pytest.raises(ValueError, match="PyBDSF pyrank"):
        namespace["pybdsf_label_plane"](rank)


def test_notebook_pybdsf_allows_fitless_native_islands() -> None:
    """A detected island without a fitted catalogue source stays mask-only."""
    namespace = _script("run_notebook_reference.py")
    validate = namespace["validate_pybdsf_island_identities"]
    labels = np.asarray(((1, 0), (2, 3)), dtype=np.int32)
    sources = (
        SimpleNamespace(island_identifier="0"),
        SimpleNamespace(island_identifier="2"),
    )
    gaussians = (SimpleNamespace(island_identifier="2"),)

    validate(sources, gaussians, labels)

    with pytest.raises(ValueError, match="catalogue and island labels"):
        validate(
            (*sources, SimpleNamespace(island_identifier="4")),
            gaussians,
            labels,
        )

    with pytest.raises(ValueError, match="Gaussian and source catalogues"):
        validate(
            sources,
            (*gaussians, SimpleNamespace(island_identifier="1")),
            labels,
        )

    with pytest.raises(ValueError, match="missing an island identity"):
        validate(
            (*sources, SimpleNamespace(island_identifier=None)),
            gaussians,
            labels,
        )


def test_notebook_aegean_reference_freezes_cli(tmp_path: Path) -> None:
    """Aegean uses explicit blind-finding clips and internal background."""
    namespace = _script("run_notebook_reference.py")
    configuration = namespace["aegean_configuration"](
        table_path=tmp_path / "catalogue.fits", ncores=2
    )
    command = namespace["aegean_command"](
        configuration,
        image_path=Path("image.fits"),
    )

    assert configuration["seedclip"] == 5.0
    assert configuration["floodclip"] == 4.0
    assert command == (
        "aegean",
        "--find",
        "--cores",
        "2",
        "--seedclip",
        "5.0",
        "--floodclip",
        "4.0",
        "--island",
        "--table",
        str(tmp_path / "catalogue.fits"),
        "image.fits",
    )
    assert namespace["configuration_identity"]("aegean", configuration)[
        "table"
    ] == ("catalogue.fits")
    component_path = tmp_path / "empty_comp.fits"
    island_path = tmp_path / "empty_isle.fits"
    namespace["write_empty_aegean_catalogues"](component_path, island_path)
    assert load_aegean_catalogue(component_path, island_path) == ()
