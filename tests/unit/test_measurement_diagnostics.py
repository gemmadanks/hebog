"""Measurement availability and catalogue publication are separate facts."""

from __future__ import annotations

import pytest

from hebog.data_models.measurement_diagnostics import (
    AssociationMergeEvidence,
    MeasurementDisposition,
)


def _record() -> dict[str, object]:
    return {
        "object_kind": "source",
        "object_id": "source-one",
        "status": "measured",
        "estimator": "original-pixel-gaussian-model",
        "reason": None,
        "member_component_ids": ("component-one",),
        "catalogue_row_published": True,
    }


def test_measured_and_unpublished_are_not_conflated() -> None:
    record = MeasurementDisposition.model_validate(_record())
    assert record.catalogue_row_published
    unpublished = MeasurementDisposition.model_validate(
        {**_record(), "catalogue_row_published": False}
    )
    assert unpublished.status == "measured"
    assert not unpublished.catalogue_row_published


@pytest.mark.parametrize(
    ("replacement", "message"),
    (
        ({"object_id": ""}, "object ID"),
        ({"estimator": None}, "estimator"),
        ({"reason": "failed"}, "estimator"),
        ({"status": "unavailable"}, "reason"),
        ({"member_component_ids": ("c2", "c1")}, "unique and sorted"),
        ({"member_component_ids": ("c1", "c1")}, "unique and sorted"),
        ({"member_component_ids": ()}, "source members"),
        ({"object_kind": "component"}, "component cannot have members"),
        ({"member_component_ids": ("",)}, "member ID"),
        (
            {"status": "deferred", "estimator": None, "reason": "work-limit"},
            "unmeasured row cannot be published",
        ),
    ),
)
def test_inconsistent_dispositions_fail_closed(
    replacement: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MeasurementDisposition.model_validate({**_record(), **replacement})


@pytest.mark.parametrize("status", ("unavailable", "deferred"))
def test_absences_keep_identity_and_reason(status: str) -> None:
    record = MeasurementDisposition.model_validate(
        {
            **_record(),
            "status": status,
            "estimator": None,
            "reason": "singular-covariance",
            "catalogue_row_published": False,
        }
    )
    assert record.object_id == "source-one"
    assert record.reason == "singular-covariance"


@pytest.mark.parametrize(
    "replacement",
    (
        {"member_component_ids": ("c1",)},
        {"member_component_ids": ("", "c1")},
        {"member_component_ids": ("c2", "c1")},
        {"member_component_ids": ("c1", "c1")},
        {"protected_component_ids": ("c2", "c1")},
        {"protected_component_ids": ("c3",)},
        {"scale_ids": ()},
        {"scale_ids": (2, 1)},
        {"scale_ids": (1, 1)},
        {"scale_ids": (4,)},
        {"reason": "directional-fwhm-overlap"},
    ),
)
def test_merge_evidence_rejects_invalid_members_or_scales(
    replacement: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="association evidence"):
        AssociationMergeEvidence.model_validate(
            {
                "reason": "persistent-residual",
                "member_component_ids": ("c1", "c2"),
                "protected_component_ids": ("c1",),
                "scale_ids": (1, 2),
                **replacement,
            }
        )


@pytest.mark.parametrize("kind", ("source", "component"))
def test_merge_evidence_cannot_be_attached_to_a_foreign_owner(
    kind: str,
) -> None:
    evidence = AssociationMergeEvidence(
        reason="directional-fwhm-overlap",
        member_component_ids=("c1", "c2"),
        scale_ids=(),
    )
    with pytest.raises(ValueError, match="evidence must belong"):
        MeasurementDisposition.model_validate(
            {
                **_record(),
                "object_kind": kind,
                "member_component_ids": ("c3",) if kind == "source" else (),
                "association_evidence": (evidence,),
            }
        )
