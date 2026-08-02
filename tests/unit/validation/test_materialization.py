# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Tests for deterministic FITS materialization of governed datasets."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.materialization import materialize_dataset

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config" / "datasets" / "phase-0-regression.json"
_DATASET_ID = "pybdsf-compact-reference-256"
_PHASE_FOUR_MANIFEST = (
    _ROOT / "config" / "datasets" / "phase-4-development.json"
)
_ROTATED_DATASET_ID = "phase4-noiseless-shape-development-256"
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


def test_materialized_fits_encodes_rotated_unequal_scale_wcs(
    tmp_path: Path,
) -> None:
    """Phase 4 WCS metadata becomes an explicit signed linear transform."""
    output = tmp_path / "rotated.fits"

    materialize_dataset(
        _PHASE_FOUR_MANIFEST,
        _ROTATED_DATASET_ID,
        output,
    )

    angle = np.deg2rad(37.0)
    expected = np.asarray(
        [
            [-0.00025 * np.cos(angle), -0.0003 * np.sin(angle)],
            [-0.00025 * np.sin(angle), 0.0003 * np.cos(angle)],
        ]
    )
    with fits.open(output) as hdus:
        header = cast(fits.Header, hdus[0].header)
        pixel_transform = np.asarray(
            [
                [
                    cast(float, header["PC1_1"]),
                    cast(float, header["PC1_2"]),
                ],
                [
                    cast(float, header["PC2_1"]),
                    cast(float, header["PC2_2"]),
                ],
            ]
        )
        actual = (
            np.diag(
                [
                    cast(float, header["CDELT1"]),
                    cast(float, header["CDELT2"]),
                ]
            )
            @ pixel_transform
        )
        actual_beam = (
            cast(float, header["BMAJ"]),
            cast(float, header["BMIN"]),
            cast(float, header["BPA"]),
        )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-15)
    beam_angle = np.deg2rad(25.0)
    beam_rotation = np.asarray(
        [
            [np.cos(beam_angle), -np.sin(beam_angle)],
            [np.sin(beam_angle), np.cos(beam_angle)],
        ]
    )
    pixel_beam_covariance = (
        beam_rotation @ np.diag([4.0**2, 3.0**2]) @ beam_rotation.T
    )
    sky_beam_covariance = expected @ pixel_beam_covariance @ expected.T
    eigenvalues, eigenvectors = np.linalg.eigh(sky_beam_covariance)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    expected_beam = (
        float(np.sqrt(eigenvalues[major_index])),
        float(np.sqrt(eigenvalues[minor_index])),
        float(
            np.rad2deg(np.arctan2(major_vector[0], major_vector[1])) % 180.0
        ),
    )

    np.testing.assert_allclose(
        actual_beam[:2],
        expected_beam[:2],
        rtol=0.0,
        atol=1e-15,
    )
    assert actual_beam[2] == pytest.approx(expected_beam[2])


def test_materialization_preserves_an_existing_file(tmp_path: Path) -> None:
    """Existing reference inputs require an explicit overwrite decision."""
    output = tmp_path / "reference.fits"
    output.write_bytes(b"keep me")

    with pytest.raises(OSError, match="already exists"):
        materialize_dataset(_MANIFEST, _DATASET_ID, output)

    assert output.read_bytes() == b"keep me"
