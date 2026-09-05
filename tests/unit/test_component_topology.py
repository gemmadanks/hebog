"""Analytic contracts for component topology inside connected islands."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from hebog.algorithms import component_topology
from hebog.algorithms.component_topology import deblend_component_topology
from hebog.config import CompactDeblendConfig


def _config(**replacements: object) -> CompactDeblendConfig:
    """Return the reviewed compact policy with small fixture bounds."""
    values: dict[str, object] = {
        "minimum_peak_signal_to_noise": 5.0,
        "minimum_peak_separation_pixels": 2,
        "minimum_saddle_depth_sigma": 1.0,
        "minimum_region_pixels": 7,
        "maximum_compact_island_pixels": 10_000,
        "maximum_compact_bounds_pixels": 10_000,
        "target_batch_pixels": 10_000,
        "maximum_batch_pixels": 10_000,
    }
    values.update(replacements)
    return CompactDeblendConfig(**values)  # type: ignore[arg-type]


def _two_peak_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return two eligible peaks joined by one island-threshold saddle."""
    normalized = np.zeros((11, 12), dtype=np.float64)
    normalized[2:9, 2:10] = np.array([6.0, 5.0, 4.0, 3.0, 3.0, 4.0, 5.0, 9.0])
    direct = np.where(normalized >= 3.0, 17, 0).astype(np.int32)
    measurement = direct.copy()
    measurement[1:10, 1:11] = 17
    return normalized, direct, measurement


def test_deblends_independent_peaks_without_changing_support_union() -> None:
    """One connected island may publish two measured Gaussian components."""
    normalized, direct, measurement = _two_peak_fixture()

    result = deblend_component_topology(
        normalized,
        direct,
        measurement,
        np.ones(normalized.shape, dtype=np.bool_),
        _config(),
    )

    assert result.deblended_parent_count == 1
    assert result.deferred_parent_count == 0
    assert set(np.unique(result.direct_component_labels)) == {0, 1, 2}
    assert set(np.unique(result.measurement_component_labels)) == {0, 1, 2}
    np.testing.assert_array_equal(
        result.direct_component_labels > 0, direct > 0
    )
    np.testing.assert_array_equal(
        result.measurement_component_labels > 0,
        measurement > 0,
    )
    assert np.all(
        result.measurement_component_labels[result.direct_component_labels > 0]
        == result.direct_component_labels[result.direct_component_labels > 0]
    )
    assert not result.direct_component_labels.flags.writeable
    assert not result.measurement_component_labels.flags.writeable


def test_single_peak_preserves_one_component_and_canonicalizes_identity() -> (
    None
):
    """A single-peaked island remains one component with stable identity."""
    yy, xx = np.mgrid[:25, :25]
    normalized = 10.0 * np.exp(-((yy - 12) ** 2 + (xx - 12) ** 2) / 8.0)
    direct = np.where(normalized >= 3.0, 42, 0).astype(np.int32)
    measurement = np.where(normalized >= 1.0, 42, 0).astype(np.int32)

    result = deblend_component_topology(
        normalized,
        direct,
        measurement,
        np.ones(normalized.shape, dtype=np.bool_),
        _config(),
    )

    assert result.deblended_parent_count == 0
    assert result.deferred_parent_count == 0
    assert set(np.unique(result.direct_component_labels)) == {0, 1}
    assert set(np.unique(result.measurement_component_labels)) == {0, 1}


def test_empty_topology_returns_read_only_empty_planes() -> None:
    """An empty image remains an explicit zero-component result."""
    empty = np.zeros((3, 4), dtype=np.int32)

    result = deblend_component_topology(
        np.zeros(empty.shape, dtype=np.float64),
        empty,
        empty,
        np.ones(empty.shape, dtype=np.bool_),
        _config(),
    )

    assert result.deblended_parent_count == 0
    assert result.deferred_parent_count == 0
    assert not np.any(result.direct_component_labels)
    assert not np.any(result.measurement_component_labels)
    assert not result.direct_component_labels.flags.writeable
    assert not result.measurement_component_labels.flags.writeable


def test_over_bound_parent_is_retained_and_reported_as_deferred() -> None:
    """Bounded topology never drops an island it cannot safely deblend."""
    normalized, direct, measurement = _two_peak_fixture()

    result = deblend_component_topology(
        normalized,
        direct,
        measurement,
        np.ones(normalized.shape, dtype=np.bool_),
        _config(maximum_compact_island_pixels=10),
    )

    assert result.deblended_parent_count == 0
    assert result.deferred_parent_count == 1
    assert set(np.unique(result.direct_component_labels)) == {0, 1}
    assert set(np.unique(result.measurement_component_labels)) == {0, 1}


def test_parent_label_values_do_not_change_canonical_component_identity() -> (
    None
):
    """Input label integers cannot alter the published spatial ordering."""
    normalized = np.zeros((15, 15), dtype=np.float64)
    normalized[3:6, 3:6] = 7.0
    normalized[9:12, 9:12] = 8.0
    first = np.zeros(normalized.shape, dtype=np.int32)
    first[3:6, 3:6] = 91
    first[9:12, 9:12] = 4
    second = np.zeros(normalized.shape, dtype=np.int32)
    second[3:6, 3:6] = 2
    second[9:12, 9:12] = 77

    first_result = deblend_component_topology(
        normalized,
        first,
        first,
        np.ones(normalized.shape, dtype=np.bool_),
        _config(),
    )
    second_result = deblend_component_topology(
        normalized,
        second,
        second,
        np.ones(normalized.shape, dtype=np.bool_),
        _config(),
    )

    np.testing.assert_array_equal(
        first_result.direct_component_labels,
        second_result.direct_component_labels,
    )
    np.testing.assert_array_equal(
        first_result.measurement_component_labels,
        second_result.measurement_component_labels,
    )


@pytest.mark.parametrize(
    ("direct", "measurement", "message"),
    [
        (
            np.array([[1, 0], [0, 0]], dtype=np.int32),
            np.array([[0, 0], [0, 0]], dtype=np.int32),
            "subset",
        ),
        (
            np.array([[1, 0], [0, 0]], dtype=np.int32),
            np.array([[1, 0], [0, 2]], dtype=np.int32),
            "identities",
        ),
    ],
)
def test_rejects_inconsistent_direct_and_measurement_ownership(
    direct: np.ndarray,
    measurement: np.ndarray,
    message: str,
) -> None:
    """Topology repair fails closed before changing inconsistent products."""
    with pytest.raises(ValueError, match=message):
        deblend_component_topology(
            np.ones((2, 2), dtype=np.float64) * 6.0,
            direct,
            measurement,
            np.ones((2, 2), dtype=np.bool_),
            _config(),
        )


@pytest.mark.parametrize(
    ("normalized", "direct", "measurement", "valid", "message"),
    [
        (
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 3), dtype=np.int32),
            np.ones((2, 2), dtype=np.int32),
            np.ones((2, 2), dtype=np.bool_),
            "aligned and 2-D",
        ),
        (
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.int32),
            np.ones((2, 2), dtype=np.bool_),
            "integer",
        ),
        (
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.int32),
            np.ones((2, 2), dtype=np.int32),
            np.ones((2, 2), dtype=np.int8),
            "boolean",
        ),
        (
            np.ones((2, 2), dtype=np.float64),
            np.array([[1, 0], [0, -1]], dtype=np.int32),
            np.array([[1, 0], [0, -1]], dtype=np.int32),
            np.ones((2, 2), dtype=np.bool_),
            "non-negative",
        ),
        (
            np.array([[np.nan, 6.0]], dtype=np.float64),
            np.array([[1, 0]], dtype=np.int32),
            np.array([[1, 0]], dtype=np.int32),
            np.ones((1, 2), dtype=np.bool_),
            "finite",
        ),
        (
            np.ones((1, 2), dtype=np.float64) * 6.0,
            np.array([[1, 0]], dtype=np.int32),
            np.array([[1, 1]], dtype=np.int32),
            np.array([[True, False]], dtype=np.bool_),
            "valid",
        ),
    ],
)
def test_rejects_invalid_component_topology_planes(
    normalized: np.ndarray,
    direct: np.ndarray,
    measurement: np.ndarray,
    valid: np.ndarray,
    message: str,
) -> None:
    """Invalid scientific ownership fails before allocating a new topology."""
    with pytest.raises((TypeError, ValueError), match=message):
        deblend_component_topology(
            normalized,
            direct,
            measurement,
            valid,
            _config(),
        )


def test_rejects_measurement_pixels_unreachable_from_deblended_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every expanded pixel must remain owned by a direct component."""
    normalized, direct, measurement = _two_peak_fixture()

    def unreachable_assignment(
        _seed_labels: np.ndarray,
        _measurement_support: np.ndarray,
        _valid_pixels: np.ndarray,
        *,
        beam_major_fwhm_pixels: float,
        recovery_radius_beams: float,
    ) -> np.ndarray:
        del beam_major_fwhm_pixels, recovery_radius_beams
        return np.zeros(measurement.shape, dtype=np.int32)

    monkeypatch.setattr(
        component_topology,
        "assign_seeded_multiscale_support",
        unreachable_assignment,
    )

    with pytest.raises(ValueError, match="remain connected"):
        deblend_component_topology(
            normalized,
            direct,
            measurement,
            np.ones(normalized.shape, dtype=np.bool_),
            _config(),
        )


def test_rejects_internal_deblender_that_drops_direct_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The outer invariant catches a malformed compact deblend result."""
    normalized, direct, measurement = _two_peak_fixture()

    def malformed_deblend(
        _pixels: object,
        _config: CompactDeblendConfig,
        *,
        marker_partition: str,
    ) -> SimpleNamespace:
        assert marker_partition == "nearest-marker"
        return SimpleNamespace(
            region_labels=np.zeros(direct[2:9, 2:10].shape, dtype=np.int32),
            regions=(object(),),
        )

    monkeypatch.setattr(
        component_topology,
        "deblend_compact_island",
        malformed_deblend,
    )

    with pytest.raises(ValueError, match="changed direct support"):
        deblend_component_topology(
            normalized,
            direct,
            measurement,
            np.ones(normalized.shape, dtype=np.bool_),
            _config(),
        )


@pytest.mark.parametrize(
    ("assigned_label", "message"),
    [
        (0, "changed measurement support"),
        (99, "identities are inconsistent"),
    ],
)
def test_rejects_internal_measurement_assignment_invariant_failures(
    monkeypatch: pytest.MonkeyPatch,
    assigned_label: int,
    message: str,
) -> None:
    """The outer invariants reject lost support and invented identities."""
    normalized, direct, measurement = _two_peak_fixture()

    def malformed_assignment(
        _direct_labels: np.ndarray,
        measurement_support: np.ndarray,
        _valid_pixels: np.ndarray,
    ) -> np.ndarray:
        return np.where(measurement_support, assigned_label, 0).astype(
            np.int32
        )

    monkeypatch.setattr(
        component_topology,
        "_assign_parent_measurement_support",
        malformed_assignment,
    )

    with pytest.raises(ValueError, match=message):
        deblend_component_topology(
            normalized,
            direct,
            measurement,
            np.ones(normalized.shape, dtype=np.bool_),
            _config(),
        )
