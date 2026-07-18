# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Tests for deterministic FITS materialization of governed datasets."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.materialization import materialize_dataset

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config" / "datasets" / "phase-0-regression.json"
_DATASET_ID = "pybdsf-compact-reference-256"
_EXPECTED_SHA256 = (
    "80e7d55f5ff22a46be2d977babe0d05f7899972f13b9518a606959eeab502ffc"
)


def test_materialized_fits_is_repeatable_and_self_identifying(
    tmp_path: Path,
) -> None:
    """Identical recipes produce byte-identical, checksummed FITS files."""
    first = tmp_path / "first.fits"
    second = tmp_path / "nested" / "second.fits"

    first_digest = materialize_dataset(_MANIFEST, _DATASET_ID, first)
    second_digest = materialize_dataset(_MANIFEST, _DATASET_ID, second)

    assert first_digest == second_digest == _EXPECTED_SHA256
    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == first_digest
    with fits.open(first, checksum=True) as hdus:
        assert hdus[0].verify_checksum() == 1
        assert hdus[0].verify_datasum() == 1
        assert hdus[0].data is not None
        assert hdus[0].data.shape == (1, 1, 256, 256)
        assert hdus[0].data.dtype == np.dtype(">f4")
        assert hdus[0].header["BUNIT"] == "Jy/beam"
        assert hdus[0].header["HEBOGDS"] == _DATASET_ID


def test_materialization_rejects_an_unknown_dataset(tmp_path: Path) -> None:
    """A typo cannot silently select or synthesize a different dataset."""
    with pytest.raises(ValueError, match="found 0"):
        materialize_dataset(_MANIFEST, "unknown-dataset", tmp_path / "x.fits")


def test_materialization_preserves_an_existing_file(tmp_path: Path) -> None:
    """Existing reference inputs require an explicit overwrite decision."""
    output = tmp_path / "reference.fits"
    output.write_bytes(b"keep me")

    with pytest.raises(OSError, match="already exists"):
        materialize_dataset(_MANIFEST, _DATASET_ID, output)

    assert output.read_bytes() == b"keep me"
