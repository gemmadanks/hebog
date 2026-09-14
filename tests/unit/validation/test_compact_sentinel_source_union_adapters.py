# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Fixture contracts for finder-specific source-union adapters."""

from __future__ import annotations

import runpy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.validation.comparison import CatalogueSource

_ROOT = Path(__file__).parents[3]
_ADAPTER = runpy.run_path(
    str(_ROOT / "scripts/validation/compact_sentinel_source_unions.py")
)
PyBdsfGaussianRow = _ADAPTER["PyBdsfGaussianRow"]
PyBdsfSourceRow = _ADAPTER["PyBdsfSourceRow"]
SourceUnionComponent = _ADAPTER["SourceUnionComponent"]
SourceUnionProjection = _ADAPTER["SourceUnionProjection"]
SourceUnionSource = _ADAPTER["SourceUnionSource"]
derive_pybdsf_source_model_dominance = _ADAPTER[
    "derive_pybdsf_source_model_dominance"
]
project_hebog_source_unions = _ADAPTER["project_hebog_source_unions"]


def _header() -> fits.Header:
    """Return one deterministic two-dimensional celestial pixel frame."""
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [1.0, 1.0]
    wcs.wcs.cdelt = np.asarray([-0.01, 0.01])
    wcs.wcs.crval = [10.0, -30.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs.to_header()


def _catalogue_row(
    identifier: str,
    centre_xy: tuple[float, float],
    integrated_flux_jy: float,
    *,
    header: fits.Header,
) -> CatalogueSource:
    """Build one comparison row at an exact pixel centre."""
    world = WCS(header, relax=True).celestial.all_pix2world([centre_xy], 0)[0]
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=float(world[0]),
        declination_degrees=float(world[1]),
        peak_flux_jy_per_beam=integrated_flux_jy,
        integrated_flux_jy=integrated_flux_jy,
    )


def _association(
    memberships: tuple[tuple[str, tuple[str, ...]], ...],
    labels: tuple[tuple[str, int], ...],
) -> SourceAssociationResult:
    """Build one exact component-to-source partition."""
    return SourceAssociationResult(
        components=tuple(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=label,
                canonical_pixel_yx=(0, index),
                centroid_yx=(0.0, float(index)),
                covariance_pixels_squared=None,
            )
            for index, (component_id, label) in enumerate(labels)
        ),
        edges=(),
        memberships=tuple(
            CatalogueSourceMembership(source_id, component_ids)
            for source_id, component_ids in memberships
        ),
    )


def test_hebog_adapter_projects_exact_multi_component_membership() -> None:
    """One associated source owns all pixels of both member components."""
    header = _header()
    association = _association(
        (("source-a", ("component-a", "component-b")),),
        (("component-a", 7), ("component-b", 9)),
    )
    result = project_hebog_source_unions(
        source_catalogue=(
            _catalogue_row("source-a", (2.0, 0.0), 3.0, header=header),
        ),
        component_catalogue=(
            _catalogue_row("component-a", (1.0, 0.0), 1.0, header=header),
            _catalogue_row("component-b", (3.0, 0.0), 2.0, header=header),
        ),
        association=association,
        measurement_component_labels=np.asarray(((7, 7, 0, 9, 9),)),
        header=header,
    )

    assert result.source_union_derivation == (
        "hebog-association-membership-v1-direct-topology"
    )
    assert result.sources[0].member_component_ids == (
        "component-a",
        "component-b",
    )
    assert result.sources[0].integrated_flux_jy == 3.0
    np.testing.assert_array_equal(
        result.source_union_label_plane,
        np.asarray(((1, 1, 0, 1, 1),), dtype=np.int32),
    )
    assert result.unowned_native_support_labels == ()


def test_hebog_adapter_canonically_partitions_two_sources() -> None:
    """Source labels depend on stable source identity, not input order."""
    header = _header()
    association = _association(
        (
            ("source-a", ("component-a",)),
            ("source-b", ("component-b",)),
        ),
        (("component-a", 7), ("component-b", 9)),
    )
    result = project_hebog_source_unions(
        source_catalogue=(
            _catalogue_row("source-b", (3.0, 0.0), 2.0, header=header),
            _catalogue_row("source-a", (1.0, 0.0), 1.0, header=header),
        ),
        component_catalogue=(
            _catalogue_row("component-b", (3.0, 0.0), 2.0, header=header),
            _catalogue_row("component-a", (1.0, 0.0), 1.0, header=header),
        ),
        association=association,
        measurement_component_labels=np.asarray(((7, 7, 0, 9, 9),)),
        header=header,
    )

    assert tuple(source.identifier for source in result.sources) == (
        "source-a",
        "source-b",
    )
    np.testing.assert_array_equal(
        result.source_union_label_plane,
        np.asarray(((1, 1, 0, 2, 2),), dtype=np.int32),
    )


@pytest.mark.parametrize("mismatch", ["source", "component", "label"])
def test_hebog_adapter_fails_closed_on_schema_mismatch(mismatch: str) -> None:
    """Catalogue, membership, and owner-plane identities must all agree."""
    header = _header()
    association = _association(
        (("source-a", ("component-a",)),), (("component-a", 7),)
    )
    source = _catalogue_row("source-a", (1.0, 0.0), 1.0, header=header)
    component = _catalogue_row("component-a", (1.0, 0.0), 1.0, header=header)
    labels = np.asarray(((7, 7),))
    if mismatch == "source":
        source = replace(source, identifier="source-b")
    elif mismatch == "component":
        component = replace(component, identifier="component-b")
    else:
        labels = np.asarray(((8, 8),))

    with pytest.raises(ValueError, match=r"Hebog .* disagree"):
        project_hebog_source_unions(
            source_catalogue=(source,),
            component_catalogue=(component,),
            association=association,
            measurement_component_labels=labels,
            header=header,
        )


def _source(
    island_id: int,
    source_id: int,
    centre_xy: tuple[float, float],
    *,
    flux: float = 2.0,
    gaussian_count: int = 1,
) -> PyBdsfSourceRow:
    return PyBdsfSourceRow(
        island_id,
        source_id,
        centre_xy,
        flux,
        gaussian_count,
    )


def _gaussian(  # noqa: PLR0913
    identifier: str,
    island_id: int,
    source_id: int,
    centre_xy: tuple[float, float],
    *,
    flux: float = 2.0,
    peak: float = 1.0,
    variance: float = 0.5,
) -> PyBdsfGaussianRow:
    return PyBdsfGaussianRow(
        identifier,
        island_id,
        source_id,
        centre_xy,
        flux,
        peak,
        ((variance, 0.0), (0.0, variance)),
    )


def test_pybdsf_single_source_owns_its_complete_native_island() -> None:
    """A modelled one-source island is not truncated to its fit footprint."""
    result = derive_pybdsf_source_model_dominance(
        source_rows=(_source(0, 4, (1.0, 0.0)),),
        gaussian_rows=(_gaussian("gaussian-a", 0, 4, (1.0, 0.0)),),
        native_island_labels=np.asarray(((1, 1, 1),)),
    )

    assert result.sources[0].identifier == "pybdsf-island-0-source-4"
    assert result.source_union_derivation == (
        "pybdsf-source-model-dominance-v1-derived-topology"
    )
    np.testing.assert_array_equal(
        result.source_union_label_plane,
        np.ones((1, 3), dtype=np.int32),
    )


def test_pybdsf_multi_source_island_uses_model_dominance_and_tie_rule() -> (
    None
):
    """Summed models partition every pixel; exact ties use canonical order."""
    result = derive_pybdsf_source_model_dominance(
        source_rows=(
            _source(0, 1, (4.0, 0.0)),
            _source(0, 0, (0.0, 0.0)),
        ),
        gaussian_rows=(
            _gaussian("gaussian-right", 0, 1, (4.0, 0.0)),
            _gaussian("gaussian-left", 0, 0, (0.0, 0.0)),
        ),
        native_island_labels=np.ones((1, 5), dtype=np.int32),
    )

    assert tuple(source.identifier for source in result.sources) == (
        "pybdsf-island-0-source-0",
        "pybdsf-island-0-source-1",
    )
    np.testing.assert_array_equal(
        result.source_union_label_plane,
        np.asarray(((1, 1, 1, 2, 2),), dtype=np.int32),
    )


def test_pybdsf_projection_is_invariant_to_catalogue_row_order() -> None:
    """Canonical source and Gaussian identities determine every output."""
    source_rows = (
        _source(0, 1, (4.0, 0.0)),
        _source(0, 0, (0.0, 0.0)),
    )
    gaussian_rows = (
        _gaussian("gaussian-right", 0, 1, (4.0, 0.0)),
        _gaussian("gaussian-left", 0, 0, (0.0, 0.0)),
    )
    labels = np.ones((1, 5), dtype=np.int32)

    forward = derive_pybdsf_source_model_dominance(
        source_rows=source_rows,
        gaussian_rows=gaussian_rows,
        native_island_labels=labels,
    )
    reversed_rows = derive_pybdsf_source_model_dominance(
        source_rows=tuple(reversed(source_rows)),
        gaussian_rows=tuple(reversed(gaussian_rows)),
        native_island_labels=labels,
    )

    assert reversed_rows.sources == forward.sources
    assert reversed_rows.components == forward.components
    np.testing.assert_array_equal(
        reversed_rows.source_union_label_plane,
        forward.source_union_label_plane,
    )


def test_pybdsf_source_observables_come_from_srl_not_gaussian_sum() -> None:
    """The binding centre and flux remain the native source-row values."""
    result = derive_pybdsf_source_model_dominance(
        source_rows=(_source(0, 0, (1.25, 0.0), flux=7.0, gaussian_count=2),),
        gaussian_rows=(
            _gaussian("gaussian-a", 0, 0, (0.0, 0.0), flux=2.0),
            _gaussian("gaussian-b", 0, 0, (2.0, 0.0), flux=3.0),
        ),
        native_island_labels=np.ones((1, 3), dtype=np.int32),
    )

    assert result.sources[0].centre_xy == (1.25, 0.0)
    assert result.sources[0].integrated_flux_jy == 7.0
    assert len(result.components) == 2


def test_pybdsf_composite_source_identity_survives_reused_local_ids() -> None:
    """A local source ID reused in another island cannot collide."""
    result = derive_pybdsf_source_model_dominance(
        source_rows=(
            _source(0, 0, (0.0, 0.0)),
            _source(1, 0, (2.0, 0.0)),
        ),
        gaussian_rows=(
            _gaussian("gaussian-a", 0, 0, (0.0, 0.0)),
            _gaussian("gaussian-b", 1, 0, (2.0, 0.0)),
        ),
        native_island_labels=np.asarray(((1, 0, 2),)),
    )

    assert tuple(source.identifier for source in result.sources) == (
        "pybdsf-island-0-source-0",
        "pybdsf-island-1-source-0",
    )
    np.testing.assert_array_equal(
        result.source_union_label_plane,
        np.asarray(((1, 0, 2),), dtype=np.int32),
    )


def test_pybdsf_fitless_islands_remain_mask_only_and_unowned() -> None:
    """Native detection support cannot fabricate a catalogue source."""
    result = derive_pybdsf_source_model_dominance(
        source_rows=(),
        gaussian_rows=(),
        native_island_labels=np.asarray(((1, 1, 0),)),
    )

    assert result.sources == ()
    assert result.components == ()
    assert result.unowned_native_support_labels == (1,)
    assert not np.any(result.source_union_label_plane)


def test_pybdsf_modelled_and_fitless_islands_keep_distinct_domains() -> None:
    """Source unions omit only complete native islands without source rows."""
    result = derive_pybdsf_source_model_dominance(
        source_rows=(_source(0, 0, (0.5, 0.0)),),
        gaussian_rows=(_gaussian("gaussian-a", 0, 0, (0.5, 0.0)),),
        native_island_labels=np.asarray(((1, 1, 0, 2, 2),)),
    )

    assert result.unowned_native_support_labels == (2,)
    np.testing.assert_array_equal(
        result.source_union_label_plane,
        np.asarray(((1, 1, 0, 0, 0),), dtype=np.int32),
    )


@pytest.mark.parametrize(
    "mismatch",
    [
        "count",
        "missing",
        "duplicate-source",
        "duplicate-gaussian",
        "missing-island",
        "zero-owned",
    ],
)
def test_pybdsf_adapter_fails_closed_on_membership_or_ownership_error(
    mismatch: str,
) -> None:
    """Every real source needs its exact Gaussian group and owned pixels."""
    sources = (
        _source(0, 0, (0.0, 0.0)),
        _source(0, 1, (0.0, 0.0)),
    )
    gaussians = (
        _gaussian("gaussian-a", 0, 0, (0.0, 0.0)),
        _gaussian("gaussian-b", 0, 1, (0.0, 0.0)),
    )
    labels = np.ones((1, 2), dtype=np.int32)
    if mismatch == "count":
        sources = (replace(sources[0], gaussian_count=2), sources[1])
    elif mismatch == "missing":
        gaussians = gaussians[:1]
    elif mismatch == "duplicate-source":
        sources = (sources[0], sources[0], sources[1])
    elif mismatch == "duplicate-gaussian":
        gaussians = (gaussians[0], gaussians[0], gaussians[1])
    elif mismatch == "missing-island":
        sources = (replace(sources[0], island_id=1), sources[1])
        gaussians = (replace(gaussians[0], island_id=1), gaussians[1])
    elif mismatch == "zero-owned":
        labels = np.ones((1, 1), dtype=np.int32)

    with pytest.raises(ValueError, match=r"PyBDSF .* (membership|pixels)"):
        derive_pybdsf_source_model_dominance(
            source_rows=sources,
            gaussian_rows=gaussians,
            native_island_labels=labels,
        )


@pytest.mark.parametrize(
    "labels",
    [np.asarray((1, 2)), np.asarray(((1.0, 0.0),)), np.asarray(((-1, 0),))],
)
def test_adapter_rejects_invalid_native_label_planes(
    labels: np.ndarray,
) -> None:
    """Native owner planes are bounded non-negative two-dimensional ints."""
    with pytest.raises(ValueError, match="non-negative 2D integer array"):
        derive_pybdsf_source_model_dominance(
            source_rows=(), gaussian_rows=(), native_island_labels=labels
        )


@pytest.mark.parametrize(
    "row",
    [
        PyBdsfSourceRow,
        PyBdsfGaussianRow,
    ],
)
def test_adapter_records_reject_non_physical_observables(row: type) -> None:
    """Non-finite or non-positive source models cannot enter alignment."""
    with pytest.raises(ValueError):
        if row is PyBdsfSourceRow:
            row(0, 0, (np.nan, 0.0), 1.0, 1)
        else:
            row(
                "gaussian",
                0,
                0,
                (0.0, 0.0),
                1.0,
                0.0,
                ((1.0, 0.0), (0.0, 1.0)),
            )


def test_adapter_records_reject_non_positive_definite_covariance() -> None:
    """Model dominance requires one invertible physical Gaussian model."""
    with pytest.raises(ValueError, match="covariance is invalid"):
        _gaussian(
            "gaussian",
            0,
            0,
            (0.0, 0.0),
            variance=0.0,
        )


def test_projection_rejects_incoherent_semantics_and_unowned_labels() -> None:
    """A projection cannot mislabel its finder or fitless support domain."""
    component = SourceUnionComponent("component", "source", 1, (0.0, 0.0), 1.0)
    source = SourceUnionSource("source", ("component",), (1,), (0.0, 0.0), 1.0)
    labels = np.ones((1, 1), dtype=np.int32)
    with pytest.raises(ValueError, match="semantics are invalid"):
        SourceUnionProjection(
            "current-hebog",
            (source,),
            (component,),
            labels,
            labels,
            "island-owner",
            "hebog-association-membership-v1-direct-topology",
            (),
        )
    with pytest.raises(ValueError, match="unowned native support"):
        SourceUnionProjection(
            "released-pybdsf",
            (source,),
            (component,),
            labels,
            labels,
            "island-owner",
            "pybdsf-source-model-dominance-v1-derived-topology",
            (0,),
        )
