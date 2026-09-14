"""Pre-opening Phase 5 qualification-design readiness checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from hebog.validation.datasets import DatasetRole, load_dataset_manifest


def _sha256(path: Path) -> str:
    """Return the byte identity of one reviewed input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(document: dict[str, object], key: str) -> dict[str, object]:
    """Read one required JSON object without accepting another type."""
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"power review {key!r} must be an object")
    return cast(dict[str, object], value)


def _positive_integer(document: dict[str, object], key: str) -> int:
    """Read one required positive non-boolean integer."""
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"power review {key!r} must be a positive integer")
    return value


def _probability(document: dict[str, object], key: str) -> float:
    """Read one finite probability from a reviewed power record."""
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"power review {key!r} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"power review {key!r} must be a probability")
    return result


def _candidate_identity(document: dict[str, object]) -> dict[str, str]:
    """Keep the source of the prospective power assumptions auditable."""
    identity: dict[str, str] = {}
    for key, length in (
        ("candidate_revision", 40),
        ("candidate_source_tree_sha256", 64),
        ("candidate_configuration_sha256", 64),
    ):
        value = document.get(key)
        if (
            not isinstance(value, str)
            or len(value) != length
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(
                f"power review {key!r} is not a hexadecimal identity"
            )
        identity[key] = value
    return identity


def audit_phase_five_qualification_design(
    manifest_path: Path,
    power_review_path: Path,
) -> dict[str, object]:
    """Audit population sufficiency without generating qualification data.

    Only the checked-in manifest recipe and an already reviewed prospective
    power summary are read. No image, finder product, truth result, or
    qualification output is generated or inspected.
    """
    manifest = load_dataset_manifest(manifest_path)
    if manifest.manifest_id != "phase-5-qualification":
        raise ValueError("qualification manifest identity differs")
    if not manifest.datasets or any(
        dataset.role is not DatasetRole.QUALIFICATION
        for dataset in manifest.datasets
    ):
        raise ValueError(
            "qualification manifest must contain qualification data"
        )

    raw_review = json.loads(power_review_path.read_text(encoding="utf-8"))
    if not isinstance(raw_review, dict):
        raise ValueError("power review must be a JSON object")
    review = cast(dict[str, object], raw_review)
    if (
        review.get("schema_version") != 1
        or review.get("review_id") != "phase-5-viewed-recovery-power-review"
        or review.get("status") != "ready-for-named-scientific-freeze-review"
    ):
        raise ValueError("power review identity or status differs")

    authorization = _object(review, "authorization")
    if authorization.get("qualification_opened") is not False:
        raise ValueError("qualification must remain unopened for design audit")
    if (
        authorization.get("execution_authorized") is not False
        or authorization.get("fresh_population_frozen") is not False
    ):
        raise ValueError(
            "power review must remain pre-freeze and pre-execution"
        )

    planning = _object(review, "planning")
    minimum_count = _positive_integer(
        planning, "minimum_continuum_realization_count"
    )
    selected_count = _positive_integer(
        planning, "selected_continuum_realization_count"
    )
    per_geometry = _positive_integer(
        planning, "continuum_realizations_per_geometry"
    )
    geometry_count = _positive_integer(planning, "geometry_count")
    paired_comparison_count = _positive_integer(
        planning, "paired_comparison_count"
    )
    if selected_count < minimum_count:
        raise ValueError(
            "selected population is smaller than the power minimum"
        )
    if per_geometry * geometry_count != selected_count:
        raise ValueError("power review must use a balanced geometry design")

    power = _object(review, "power")
    familywise_power = _probability(
        power, "combined_familywise_power_lower_bound"
    )
    minimum_power = _probability(power, "minimum_joint_power")
    if familywise_power < minimum_power:
        raise ValueError("prospective familywise power does not pass")

    realization_count = sum(
        1 + len(dataset.noise_realization_seeds)
        for dataset in manifest.datasets
    )
    geometries = {
        (
            dataset.beam.major_fwhm_pixels,
            dataset.beam.minor_fwhm_pixels,
            dataset.beam.position_angle_degrees,
            dataset.wcs.pixel_scale_degrees_xy,
            dataset.wcs.rotation_degrees_counterclockwise,
        )
        for dataset in manifest.datasets
    }
    current_geometry_count = len(geometries)
    sufficient = (
        realization_count >= minimum_count
        and current_geometry_count >= geometry_count
    )
    candidate = _candidate_identity(_object(review, "cumulative_ledger"))

    return {
        "schema_version": 1,
        "audit_id": "phase-5-qualification-design-audit",
        "status": (
            "current-design-sufficient"
            if sufficient
            else "replacement-design-required"
        ),
        "scope": "manifest-and-prospective-power-only-no-science-opened",
        "current_design": {
            "manifest_path": manifest_path.as_posix(),
            "manifest_sha256": _sha256(manifest_path),
            "realization_count": realization_count,
            "geometry_count": current_geometry_count,
            "sufficient": sufficient,
        },
        "power_requirement": {
            "review_path": power_review_path.as_posix(),
            "review_sha256": _sha256(power_review_path),
            "candidate": candidate,
            "minimum_realization_count": minimum_count,
            "paired_comparison_count": paired_comparison_count,
            "minimum_joint_power": minimum_power,
            "combined_familywise_power_lower_bound": familywise_power,
        },
        "replacement_design": {
            "realization_count": selected_count,
            "geometry_count": geometry_count,
            "realizations_per_geometry": per_geometry,
            "seed_policy": (
                "fresh-and-disjoint-from-development-regression-"
                "qualification-and-viewed-evidence"
            ),
            "preserve_current_manifest_unopened": True,
        },
        "authorization": {
            "replacement_population_frozen": False,
            "execution_authorized": False,
            "qualification_opened": False,
            "required_next_approval": (
                "named-scientific-approval-before-freezing-"
                "replacement-qualification-identities"
            ),
        },
    }
