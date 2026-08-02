"""Scientific comparison of immutable released and master PyBDSF products."""

from __future__ import annotations

from pathlib import Path

import pytest

from hebog.validation.comparison import (
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.products import (
    ProductName,
    ReferenceProductSet,
    canonical_product_set_sha256,
    load_fits_plane,
    load_mask_plane,
    load_pybdsf_catalogue,
    load_reference_product_manifest,
    product_set_by_reference,
    validate_reference_product_files,
)

_ROOT = Path(__file__).parents[2]
_MANIFEST_PATH = (
    _ROOT / "config" / "baselines" / "phase-0-pybdsf-reference-products.json"
)
_BEAM_FWHM_DEGREES = 0.001111111111111111
_MAXIMUM_SEPARATION_BEAMS = 0.5


def _path(product_set: ReferenceProductSet, name: ProductName) -> Path:
    """Resolve one governed reference artifact inside the repository."""
    return _ROOT / product_set.artifacts[name].relative_path


@pytest.mark.equivalence
def test_reference_product_manifest_checksums_are_intact() -> None:
    """Every frozen reference product remains bound to complete provenance."""
    manifest = load_reference_product_manifest(_MANIFEST_PATH)

    validate_reference_product_files(_ROOT, manifest)

    release = product_set_by_reference(manifest, "release")
    master = product_set_by_reference(manifest, "master")
    assert release.subject.version == "1.14.1"
    assert master.subject.commit_sha == (
        "c70103be3ae9ae9908286f144e6ce956acc0ce5c"
    )
    assert canonical_product_set_sha256(release) != (
        canonical_product_set_sha256(master)
    )


@pytest.mark.equivalence
def test_master_and_release_reference_catalogues_are_equivalent() -> None:
    """The pinned master preserves released compact-field source results."""
    manifest = load_reference_product_manifest(_MANIFEST_PATH)
    release = product_set_by_reference(manifest, "release")
    master = product_set_by_reference(manifest, "master")

    report = compare_catalogues(
        load_pybdsf_catalogue(_path(release, "source_catalog.fits")),
        load_pybdsf_catalogue(_path(master, "source_catalog.fits")),
        beam_fwhm_degrees=_BEAM_FWHM_DEGREES,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
        position_angle_minimum_axis_ratio=1.1,
    )

    assert report.reference_count == report.candidate_count == 3
    assert len(report.matches) == 3
    assert report.completeness == 1.0
    assert report.reliability == 1.0
    assert report.median_separation_beam_fwhm == 0.0
    assert report.median_absolute_peak_flux_fractional_difference == 0.0
    assert report.median_absolute_integrated_flux_fractional_difference == 0.0
    assert report.median_absolute_fitted_axis_fractional_difference == 0.0
    assert report.association.precision == 1.0
    assert report.association.recall == 1.0


@pytest.mark.equivalence
@pytest.mark.parametrize(
    "name",
    ("true_sky_rms.fits", "flat_noise_rms.fits"),
)
def test_master_and_release_reference_rms_maps_are_equivalent(
    name: ProductName,
) -> None:
    """Both reference implementations emit identical compact RMS planes."""
    manifest = load_reference_product_manifest(_MANIFEST_PATH)
    release = product_set_by_reference(manifest, "release")
    master = product_set_by_reference(manifest, "master")

    report = compare_rms_maps(
        load_fits_plane(_path(release, name)),
        load_fits_plane(_path(master, name)),
    )

    assert report.compared_pixel_count == 256 * 256
    assert report.excluded_pixel_count == 0
    assert report.median_absolute_difference_jy_per_beam == 0.0
    assert report.median_absolute_fractional_difference == 0.0


@pytest.mark.equivalence
def test_master_and_release_reference_masks_are_equivalent() -> None:
    """Both references select the same compact-field island-mask pixels."""
    manifest = load_reference_product_manifest(_MANIFEST_PATH)
    release = product_set_by_reference(manifest, "release")
    master = product_set_by_reference(manifest, "master")

    report = compare_masks(
        load_mask_plane(_path(release, "source_filter_mask.fits")),
        load_mask_plane(_path(master, "source_filter_mask.fits")),
    )

    assert report.compared_pixel_count == 256 * 256
    assert report.false_positive_count == 0
    assert report.false_negative_count == 0
    assert report.agreement_fraction == 1.0
