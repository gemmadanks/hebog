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
from pydantic import ValidationError

from hebog.validation.datasets import load_dataset_manifest
from hebog.validation.materialization import (
    ExternalInputArtifact,
    ExternalInputBundle,
    load_external_input_bundle,
    materialize_dataset,
    materialize_external_realization,
    synthetic_fits_header,
    synthetic_image_metadata,
)

_ROOT = Path(__file__).parents[3]
_MANIFEST = _ROOT / "config" / "datasets" / "phase-0-regression.json"
_DATASET_ID = "pybdsf-compact-reference-256"
_PHASE_FOUR_MANIFEST = (
    _ROOT / "config" / "datasets" / "phase-4-development.json"
)
_ROTATED_DATASET_ID = "phase4-noiseless-shape-development-256"
_EXTERNAL_PROTOCOL = (
    _ROOT / "config/contracts/phase-5-external-comparison.json"
)
_EXTERNAL_MANIFEST = (
    _ROOT / "config/datasets/phase-5-external-compact-blend.json"
)
_EXTERNAL_DATASET_ID = "phase5-external-compact-blend-512"
_EXTERNAL_SEED = 2026790002
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


def test_synthetic_metadata_matches_the_materialized_header() -> None:
    """In-memory qualification uses the same WCS and beam as FITS output."""
    manifest = load_dataset_manifest(_PHASE_FOUR_MANIFEST)
    dataset = next(
        item
        for item in manifest.datasets
        if item.identifier == _ROTATED_DATASET_ID
    )

    header = synthetic_fits_header(dataset)
    metadata = synthetic_image_metadata(dataset)

    assert metadata.shape_yx == dataset.recipe.shape_yx
    assert metadata.unit == "Jy/beam"
    assert metadata.reference_frequency_hz == header["RESTFRQ"]
    assert metadata.beam.major_fwhm_degrees == header["BMAJ"]
    assert metadata.beam.minor_fwhm_degrees == header["BMIN"]
    assert metadata.beam.position_angle_degrees == header["BPA"]
    assert metadata.celestial_wcs is not None
    restored = fits.Header.fromstring(
        metadata.celestial_wcs.fits_header,
        sep="\n",
    )
    assert restored["HEBOGRCP"] == dataset.recipe_sha256


def test_materialization_preserves_an_existing_file(tmp_path: Path) -> None:
    """Existing reference inputs require an explicit overwrite decision."""
    output = tmp_path / "reference.fits"
    output.write_bytes(b"keep me")

    with pytest.raises(OSError, match="already exists"):
        materialize_dataset(_MANIFEST, _DATASET_ID, output)

    assert output.read_bytes() == b"keep me"


def test_external_realization_materializes_one_shared_float64_bundle(
    tmp_path: Path,
) -> None:
    """Every finder receives byte-identical image, mean, and RMS products."""
    first_path = materialize_external_realization(
        _EXTERNAL_PROTOCOL,
        _EXTERNAL_MANIFEST,
        _EXTERNAL_DATASET_ID,
        _EXTERNAL_SEED,
        tmp_path / "first",
    )
    second_path = materialize_external_realization(
        _EXTERNAL_PROTOCOL,
        _EXTERNAL_MANIFEST,
        _EXTERNAL_DATASET_ID,
        _EXTERNAL_SEED,
        tmp_path / "second",
    )
    first = load_external_input_bundle(first_path, verify_artifacts=True)
    second = load_external_input_bundle(second_path, verify_artifacts=True)

    assert first == second
    assert first.seed == _EXTERNAL_SEED
    assert first.dtype == "float64"
    assert first.shape_yx == (512, 512)
    assert first.protocol_sha256 == (
        "b9db9adbd1cae1a8c11a081b0af245e3e8dca8979bce9e2dc0ffda968c5d2d72"
    )
    assert {artifact.role for artifact in first.artifacts} == {
        "image",
        "mean",
        "rms",
    }
    assert tuple(item.sha256 for item in first.artifacts) == tuple(
        item.sha256 for item in second.artifacts
    )

    image = np.asarray(
        cast(np.ndarray, fits.getdata(first_path.parent / "image.fits"))
    ).squeeze()
    mean = np.asarray(
        cast(np.ndarray, fits.getdata(first_path.parent / "mean.fits"))
    ).squeeze()
    rms = np.asarray(
        cast(np.ndarray, fits.getdata(first_path.parent / "rms.fits"))
    ).squeeze()
    header = cast(
        fits.Header, fits.getheader(first_path.parent / "image.fits")
    )
    assert image.dtype == np.dtype(">f8")
    assert mean.dtype == np.dtype(">f8")
    assert rms.dtype == np.dtype(">f8")
    assert header["HEBOGSED"] == _EXTERNAL_SEED
    assert header["HEBOGBAS"] != header["HEBOGRCP"]
    assert np.all(np.isfinite(mean) == np.isfinite(image))
    assert np.all(np.isfinite(rms) == np.isfinite(image))


def test_external_materializer_rejects_seed_and_output_drift(
    tmp_path: Path,
) -> None:
    """Only declared seeds may be written and frozen bundles are immutable."""
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="not declared"):
        materialize_external_realization(
            _EXTERNAL_PROTOCOL,
            _EXTERNAL_MANIFEST,
            _EXTERNAL_DATASET_ID,
            1,
            output,
        )

    materialize_external_realization(
        _EXTERNAL_PROTOCOL,
        _EXTERNAL_MANIFEST,
        _EXTERNAL_DATASET_ID,
        _EXTERNAL_SEED,
        output,
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        materialize_external_realization(
            _EXTERNAL_PROTOCOL,
            _EXTERNAL_MANIFEST,
            _EXTERNAL_DATASET_ID,
            _EXTERNAL_SEED,
            output,
        )

    with (output / "image.fits").open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="byte count changed"):
        load_external_input_bundle(
            output / "input.json", verify_artifacts=True
        )


def test_external_input_models_reject_escaping_paths_and_bad_shape() -> None:
    """A shared input cannot escape its root or declare an empty plane."""
    with pytest.raises(ValidationError, match="stay relative"):
        ExternalInputArtifact(
            role="image",
            relative_path="../image.fits",
            byte_count=1,
            sha256="0" * 64,
        )
    artifacts = (
        ExternalInputArtifact(
            role="image",
            relative_path="image.fits",
            byte_count=1,
            sha256="0" * 64,
        ),
        ExternalInputArtifact(
            role="mean",
            relative_path="mean.fits",
            byte_count=1,
            sha256="0" * 64,
        ),
        ExternalInputArtifact(
            role="rms",
            relative_path="rms.fits",
            byte_count=1,
            sha256="0" * 64,
        ),
    )
    with pytest.raises(ValidationError, match="shape must be positive"):
        ExternalInputBundle(
            schema_version=1,
            protocol_sha256="0" * 64,
            manifest_sha256="0" * 64,
            dataset_identifier="invalid-shape",
            seed=1,
            recipe_sha256="0" * 64,
            dtype="float64",
            shape_yx=(0, 3),
            artifacts=artifacts,
        )
