# pyright: reportMissingTypeStubs=false
"""Evaluation-only tests for associated source support unions."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, replace
from typing import cast

import numpy as np
import pytest
from astropy.io import fits

from hebog.algorithms.source_association import (
    build_detection_component_records,
    reduce_source_associations,
)
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationEdge,
    SourceAssociationResult,
    SourceHierarchyDiagnostics,
)
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
)
from hebog.validation.parent_construction_association_evaluation import (
    continuum_catalogue_objects_from_association,
    source_association_from_json,
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


def test_persisted_association_resolves_recovered_owner_support() -> None:
    """Direct identities remain verifiable after ownership grows up-image."""
    component_pixels = tuple(
        sorted(
            (
                (detection_component_identifier((0, 2)), (0, 2), 7),
                (detection_component_identifier((0, 6)), (0, 6), 9),
            )
        )
    )
    direct_ids = tuple(item[0] for item in component_pixels)
    source_id = associated_source_identifier(direct_ids)
    association = SourceAssociationResult(
        components=tuple(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=label,
                canonical_pixel_yx=pixel,
                centroid_yx=(float(pixel[0]), float(pixel[1])),
                covariance_pixels_squared=None,
            )
            for component_id, pixel, label in component_pixels
        ),
        edges=(),
        memberships=(
            CatalogueSourceMembership(
                source_id=source_id,
                component_ids=direct_ids,
            ),
        ),
    )
    recovered_labels = np.asarray(((0, 7, 7, 0, 0, 9, 9, 0),))

    with pytest.raises(ValueError, match="membership cannot be verified"):
        continuum_catalogue_objects(
            (_source(source_id, 2),),
            recovered_labels,
            finder_id="hebog",
            header=_header(),
        )

    candidates = continuum_catalogue_objects_from_association(
        (_source(source_id, 2),),
        recovered_labels,
        association,
        finder_id="hebog",
        header=_header(),
    )

    assert isinstance(candidates[0], AssociatedContinuumCatalogueObject)
    assert candidates[0].support_labels == (7, 9)


def test_association_json_round_trip_retains_direct_identity() -> None:
    """The persisted sidecar reconstructs immutable membership evidence."""
    component_id = detection_component_identifier((3, 4))
    source_id = associated_source_identifier((component_id,))
    association = SourceAssociationResult(
        components=(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=2,
                canonical_pixel_yx=(3, 4),
                centroid_yx=(3.0, 4.0),
                covariance_pixels_squared=((1.0, 0.0), (0.0, 1.0)),
            ),
        ),
        edges=(),
        memberships=(
            CatalogueSourceMembership(
                source_id=source_id,
                component_ids=(component_id,),
            ),
        ),
        hierarchy_diagnostics=SourceHierarchyDiagnostics(
            direct_component_count=1,
            catalogue_source_count=1,
            membership_size_histogram=((1, 1),),
            unattached_component_count=0,
            multiple_finest_feature_attachment_count=0,
            branched_lineage_count=0,
            no_common_convergence_count=0,
            unique_convergence_count=1,
            per_scale_feature_counts=((1, 1),),
            adjacent_scale_parent_edge_count=0,
            scale_aware_parent_candidate_count=0,
            persistent_parent_count=0,
            rejected_parent_ambiguity_count=0,
            per_scale_parent_candidate_counts=((1, 0),),
        ),
    )

    document = json.loads(json.dumps(asdict(association)))
    assert source_association_from_json(document) == association


def test_association_json_loader_rejects_structural_coercions() -> None:
    """Malformed sidecars fail before entering scientific measurement."""
    component_id = detection_component_identifier((3, 4))
    source_id = associated_source_identifier((component_id,))
    association = SourceAssociationResult(
        components=(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=2,
                canonical_pixel_yx=(3, 4),
                centroid_yx=(3.0, 4.0),
                covariance_pixels_squared=None,
            ),
        ),
        edges=(),
        memberships=(
            CatalogueSourceMembership(
                source_id=source_id,
                component_ids=(component_id,),
            ),
        ),
    )
    document = json.loads(json.dumps(asdict(association)))

    invalid: list[tuple[object, str]] = [
        ([], "JSON object"),
        ({**document, "components": None}, "JSON array"),
    ]
    changed = deepcopy(document)
    changed["components"][0]["canonical_pixel_yx"] = [3]
    invalid.append((changed, "integer pair"))
    changed = deepcopy(document)
    changed["components"][0]["centroid_yx"] = [True, 4.0]
    invalid.append((changed, "numeric pair"))
    changed = deepcopy(document)
    changed["components"][0]["label_value"] = "2"
    invalid.append((changed, "must be an integer"))
    changed = deepcopy(document)
    changed["components"][0]["component_id"] = 2
    invalid.append((changed, "must be a string"))
    changed = deepcopy(document)
    changed["components"][0]["covariance_pixels_squared"] = []
    invalid.append((changed, "two-by-two"))
    changed = deepcopy(document)
    changed["components"][0]["component_labels_are_identity"] = True
    invalid.append((changed, "must not be identity"))
    changed = deepcopy(document)
    changed["memberships"][0]["component_ids"] = component_id
    invalid.append((changed, "component IDs must be a JSON array"))
    changed = deepcopy(document)
    changed["ambiguous_component_ids"] = component_id
    invalid.append((changed, "ambiguous component IDs"))
    changed = deepcopy(document)
    changed["edges"] = [
        {
            "first_component_id": component_id,
            "second_component_id": "component-other",
            "saddle_margin_sigma": "invalid",
            "normalized_separation": 0.5,
        }
    ]
    invalid.append((changed, "must be numeric"))

    for value, message in invalid:
        with pytest.raises(ValueError, match=message):
            source_association_from_json(value)


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
