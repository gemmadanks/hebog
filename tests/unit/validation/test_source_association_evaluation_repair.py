# pyright: reportMissingTypeStubs=false
"""Evaluation-only tests for associated source support unions."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import pytest
from astropy.io import fits

from hebog.algorithms.source_association import (
    build_detection_component_records,
    reduce_source_associations,
)
from hebog.data_models.source_association import SourceAssociationEdge
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
)
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
    associated_source_identifier,
    continuum_catalogue_objects,
    detection_component_identifier,
    install_source_association_evaluation_repair,
    measure_continuum_image,
)


def _header() -> fits.Header:
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = 8
    header["NAXIS2"] = 8
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = 1.0
    header["CRPIX2"] = 1.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -0.001
    header["CDELT2"] = 0.001
    return header


def _source(identifier: str, component_count: int) -> CatalogueSource:
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=2.0,
        association_integrated_flux_jy=3.0,
        island_identifier=identifier,
        component_count=component_count,
    )


def _truth() -> tuple[ContinuumTruthObject, ...]:
    return (
        ContinuumTruthObject(
            identifier="truth-1",
            support_label=1,
            centre_xy=(0.0, 0.0),
            integrated_flux_jy=3.0,
            catalogue_role="astronomical-source",
            strata=(),
        ),
    )


def test_repair_identifiers_match_the_production_association_contract() -> (
    None
):
    """The adapter verifies the persisted identity formula independently."""
    labels = np.asarray(((7, 7, 0, 9, 9),), dtype=np.int32)
    records = build_detection_component_records(
        labels,
        np.where(labels > 0, 1.0, 0.0),
        np.ones(labels.shape, dtype=np.bool_),
    )
    edge = SourceAssociationEdge(
        first_component_id=min(item.component_id for item in records),
        second_component_id=max(item.component_id for item in records),
        saddle_margin_sigma=1.0,
        normalized_separation=0.5,
    )
    result = reduce_source_associations(records, (edge,))

    assert tuple(item.component_id for item in records) == (
        detection_component_identifier((0, 0)),
        detection_component_identifier((0, 3)),
    )
    assert result.memberships[0].source_id == associated_source_identifier(
        tuple(sorted(item.component_id for item in records))
    )


def test_associated_catalogue_uses_exact_support_union_for_matching() -> None:
    """One source row owns both native supports without merging topology."""
    candidate_labels = np.asarray(((7, 7, 0, 9, 9),), dtype=np.int32)
    source_id = associated_source_identifier(
        tuple(
            sorted(
                (
                    detection_component_identifier((0, 0)),
                    detection_component_identifier((0, 3)),
                )
            )
        )
    )
    candidates = continuum_catalogue_objects(
        (_source(source_id, 2),),
        candidate_labels,
        finder_id="hebog",
        header=_header(),
    )
    values = measure_continuum_image(
        _truth(),
        candidates,
        truth_label_plane=np.asarray(((1, 1, 0, 1, 1),)),
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert isinstance(candidates[0], AssociatedContinuumCatalogueObject)
    assert candidates[0].support_labels == (7, 9)
    assert values["completeness"]["overall"] == 1.0
    assert values["reliability"]["overall"] == 1.0
    assert values["split-fraction"]["overall"] == 1.0


def test_associated_catalogue_partition_is_label_permutation_invariant() -> (
    None
):
    """Digest recovery depends on canonical pixels, not local label values."""
    singleton_id = associated_source_identifier(
        (detection_component_identifier((0, 6)),)
    )
    pair_id = associated_source_identifier(
        tuple(
            sorted(
                (
                    detection_component_identifier((0, 0)),
                    detection_component_identifier((0, 3)),
                )
            )
        )
    )
    sources = (_source(singleton_id, 1), _source(pair_id, 2))

    original = continuum_catalogue_objects(
        sources,
        np.asarray(((7, 7, 0, 9, 9, 0, 11),)),
        finder_id="hebog",
        header=_header(),
    )
    permuted = continuum_catalogue_objects(
        tuple(reversed(sources)),
        np.asarray(((31, 31, 0, 2, 2, 0, 5),)),
        finder_id="hebog",
        header=_header(),
    )
    assert all(
        isinstance(item, AssociatedContinuumCatalogueObject)
        for item in (*original, *permuted)
    )
    associated_original = cast(
        tuple[AssociatedContinuumCatalogueObject, ...],
        original,
    )
    associated_permuted = cast(
        tuple[AssociatedContinuumCatalogueObject, ...],
        permuted,
    )

    assert {
        item.identifier: item.support_labels for item in associated_original
    } == {
        singleton_id: (11,),
        pair_id: (7, 9),
    }
    assert {
        item.identifier: item.support_labels for item in associated_permuted
    } == {
        singleton_id: (5,),
        pair_id: (2, 31),
    }


def test_associated_catalogue_rejects_unverifiable_or_mixed_identity() -> None:
    """Malformed digests and mixed semantic layers fail closed."""
    labels = np.asarray(((1, 0, 2),), dtype=np.int32)
    invalid = _source("source-associated-" + "0" * 64, 2)
    with pytest.raises(ValueError, match="membership cannot be verified"):
        continuum_catalogue_objects(
            (invalid,),
            labels,
            finder_id="hebog",
            header=_header(),
        )

    singleton_id = associated_source_identifier(
        (detection_component_identifier((0, 0)),)
    )
    segment = replace(
        _source("component", 1),
        island_identifier="hebog-segment-2",
    )
    with pytest.raises(ValueError, match="cannot mix segment and associated"):
        continuum_catalogue_objects(
            (_source(singleton_id, 1), segment),
            labels,
            finder_id="hebog",
            header=_header(),
        )


def test_legacy_catalogue_semantics_delegate_unchanged() -> None:
    """The adapter leaves every historical single-support row untouched."""
    labels = np.asarray(((1, 1),), dtype=np.int32)
    source = replace(
        _source("legacy", 1),
        island_identifier="hebog-segment-1",
    )
    candidates = continuum_catalogue_objects(
        (source,),
        labels,
        finder_id="hebog",
        header=_header(),
    )

    assert isinstance(candidates[0], ContinuumCatalogueObject)
    assert candidates[0].support_label == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"identifier": ""}, "identifier"),
        ({"support_labels": ()}, "support labels"),
        ({"support_labels": (2, 1)}, "support labels"),
        ({"centre_xy": (np.nan, 0.0)}, "centre"),
        ({"integrated_flux_jy": 0.0}, "flux"),
    ),
)
def test_associated_catalogue_object_rejects_invalid_fields(
    changes: dict[str, object],
    message: str,
) -> None:
    """Invalid evaluation records cannot alter matching semantics."""
    values: dict[str, object] = {
        "identifier": "source",
        "support_labels": (1,),
        "centre_xy": (0.0, 0.0),
        "integrated_flux_jy": 1.0,
    }
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        AssociatedContinuumCatalogueObject(**values)  # type: ignore[arg-type]


def test_repair_installer_replaces_only_two_compiler_seams() -> None:
    """The frozen compiler receives no broader mutation."""

    def original_candidate(*_args: object, **_kwargs: object) -> tuple[()]:
        return ()

    def original_measure(
        *_args: object,
        **_kwargs: object,
    ) -> dict[object, object]:
        return {}

    compiler = {
        "_candidate_objects": original_candidate,
        "measure_continuum_image": original_measure,
        "unchanged": object(),
    }
    unchanged = compiler["unchanged"]

    install_source_association_evaluation_repair(compiler)

    assert compiler["_candidate_objects"] is continuum_catalogue_objects
    assert compiler["measure_continuum_image"] is measure_continuum_image
    assert compiler["unchanged"] is unchanged


def test_repair_identifier_validation_is_fail_closed() -> None:
    """Noncanonical inputs cannot enter the source identity domain."""
    with pytest.raises(ValueError, match="canonical component pixel"):
        detection_component_identifier((-1, 0))
    with pytest.raises(ValueError, match="component IDs must be canonical"):
        associated_source_identifier(("component-b", "component-a"))
