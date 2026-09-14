"""Prospective Phase 5 endpoint-complete power-audit tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from hebog.validation.prospective_science_contract import (
    load_prospective_endpoint_registry,
)
from hebog.validation.prospective_science_power import (
    build_prospective_power_audit,
)

_ROOT = Path(__file__).parents[3]
_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_PROTOCOL = _ROOT / "config/contracts/phase-5-external-comparison.json"


def _object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _smoke(*, compact_equal: bool = True) -> dict[str, object]:
    return {
        "status": "pass",
        "promotion_evidence": False,
        "compact_product_identity_equal": compact_equal,
    }


def test_frozen_full_replay_is_powered_for_every_comparison() -> None:
    """All 1,187 frozen comparisons pass endpoint and joint design gates."""
    record = build_prospective_power_audit(
        registry=load_prospective_endpoint_registry(_REGISTRY),
        external_protocol=_object(_PROTOCOL),
        smoke_record=_smoke(),
    )

    assert record["status"] == "pass"
    assert record["comparison_count"] == 1187
    assert record["adequately_powered_comparison_count"] == 1187
    assert record["underpowered_comparisons"] == []
    assert (
        float(cast(float, record["combined_familywise_power_lower_bound"]))
        >= 0.9
    )


def test_power_audit_requires_smoke_proven_compact_identity() -> None:
    """Incumbent compact power cannot be assumed without exact products."""
    with pytest.raises(ValueError, match="passing smoke record"):
        build_prospective_power_audit(
            registry=load_prospective_endpoint_registry(_REGISTRY),
            external_protocol=_object(_PROTOCOL),
            smoke_record=_smoke(compact_equal=False),
        )


def test_power_audit_rejects_margin_different_from_frozen_design() -> None:
    """Endpoint registry and prospective planning margins stay coupled."""
    protocol = _object(_PROTOCOL)
    audit = cast(dict[str, object], protocol["power_audit"])
    assumptions = cast(list[object], audit["continuum_assumptions"])
    first = cast(dict[str, object], assumptions[0])
    first["practical_regression_margin"] = 0.5

    with pytest.raises(ValueError, match="margin differs"):
        build_prospective_power_audit(
            registry=load_prospective_endpoint_registry(_REGISTRY),
            external_protocol=protocol,
            smoke_record=_smoke(),
        )
