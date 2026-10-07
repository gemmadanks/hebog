"""Scientific comparison of immutable released and master PyBDSF products."""

from __future__ import annotations

import json
import math
import runpy
import sys
from pathlib import Path
from typing import Any, cast

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
_COMPARISON_PATH = (
    _ROOT
    / "config"
    / "baselines"
    / "phase-0-pybdsf-master-vs-release-comparison.json"
)
_BEAM_FWHM_DEGREES = 0.001111111111111111
_MAXIMUM_SEPARATION_BEAMS = 0.5
# Statistics in a comparison record, such as a Wilson bound's z-score from
# ``statistics.NormalDist``, go through ``math.log``, whose last bit differs
# between Apple's libm and glibc; a regenerated record matches to this.
_RECORD_FLOAT_RELATIVE_TOLERANCE = 1e-12


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


def _values_match(actual: Any, expected: Any) -> bool:
    """Compare two JSON leaves exactly, but floats to round-off."""
    if isinstance(expected, float) and isinstance(actual, float):
        return math.isclose(
            actual, expected, rel_tol=_RECORD_FLOAT_RELATIVE_TOLERANCE
        )
    return type(actual) is type(expected) and actual == expected


def _record_differences(
    actual: Any, expected: Any, path: str = ""
) -> list[str]:
    """List where two JSON values differ beyond floating-point round-off.

    Keys, lengths, strings, integers, booleans and nulls must be equal;
    floats agree to ``_RECORD_FLOAT_RELATIVE_TOLERANCE``.
    """
    where = path or "<record>"
    children: list[tuple[Any, Any, str]]
    if isinstance(expected, dict):
        expected_items = cast(dict[str, Any], expected)
        actual_items = cast(dict[str, Any], actual)
        if (
            not isinstance(actual, dict)
            or actual_items.keys() != expected_items.keys()
        ):
            return [f"{where}: keys differ"]
        children = [
            (actual_items[key], value, f"{path}.{key}")
            for key, value in expected_items.items()
        ]
    elif isinstance(expected, list):
        expected_list = cast(list[Any], expected)
        actual_list = cast(list[Any], actual)
        if not isinstance(actual, list) or len(actual_list) != len(
            expected_list
        ):
            return [f"{where}: lengths differ"]
        children = [
            (item, value, f"{path}[{index}]")
            for index, (item, value) in enumerate(
                zip(actual_list, expected_list, strict=True)
            )
        ]
    elif _values_match(actual, expected):
        return []
    else:
        return [f"{where}: {actual!r} != {expected!r}"]
    return [
        difference
        for item, value, child_path in children
        for difference in _record_differences(item, value, child_path)
    ]


@pytest.mark.equivalence
@pytest.mark.parametrize(
    ("actual", "expected", "differences"),
    [
        # The Wilson bound for 1 of 1 at 95% on Linux and on macOS.
        ({"lower": 0.2065493143772375}, {"lower": 0.20654931437723753}, []),
        ({"lower": 0.20654931}, {"lower": 0.2065493143772375}, [".lower"]),
        ({"a": [1, "x"]}, {"a": [1, "y"]}, [".a[1]"]),
        ({"a": [1]}, {"a": [1.0]}, [".a[0]"]),
        ({"a": [1]}, {"a": [1, 2]}, [".a"]),
        ({"a": None}, {"b": None}, ["<record>"]),
    ],
)
def test_record_comparison_allows_only_round_off(
    actual: Any, expected: Any, differences: list[str]
) -> None:
    """The comparison is exact except for floats' last bits."""
    assert [
        difference.split(":")[0]
        for difference in _record_differences(actual, expected)
    ] == differences


@pytest.mark.equivalence
def test_committed_master_versus_release_comparison_is_reproduced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its generator, with today's matcher, writes the committed record.

    Floats match to round-off: the record was written on macOS, and Linux
    computes the Wilson bounds of single-sample metrics one bit apart.
    """
    output = tmp_path / "comparison.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare_reference_products.py",
            "--repository-root",
            str(_ROOT),
            "--manifest",
            str(_MANIFEST_PATH),
            "--output",
            str(output),
        ],
    )

    runpy.run_path(
        str(_ROOT / "scripts/validation/compare_reference_products.py"),
        run_name="__main__",
    )

    regenerated = json.loads(output.read_text(encoding="utf-8"))
    committed = json.loads(_COMPARISON_PATH.read_text(encoding="utf-8"))
    assert _record_differences(regenerated, committed) == []
