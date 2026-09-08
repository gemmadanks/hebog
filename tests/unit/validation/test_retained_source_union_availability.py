"""The amended projection retains v1 winners without losing native rows."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))
native: Any = importlib.import_module(
    "scripts.validation.compact_sentinel_source_unions"
)
amended: Any = importlib.import_module(
    "scripts.validation.source_catalogue_source_unions"
)


def test_model_arithmetic_preserves_historical_coordinate_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Array layout must not perturb model arithmetic near ownership ties."""
    rng = np.random.default_rng(20260908)
    labels = (rng.random((31, 47)) > 0.2).astype(np.int32)
    coordinate_yx = np.argwhere(labels == 1)
    historical_xy = np.asarray(coordinate_yx[:, ::-1], dtype=np.float64)
    sources = tuple(
        native.PyBdsfSourceRow(0, index, centre, 3.0, 1)
        for index, centre in enumerate(((12.3, 14.7), (12.3, 14.7 + 1e-12)))
    )
    gaussians = tuple(
        native.PyBdsfGaussianRow(
            f"model-{index}",
            0,
            index,
            row.centre_xy,
            5.0,
            2.0,
            ((2.7, 0.63), (0.63, 1.4)),
        )
        for index, row in enumerate(sources)
    )
    model = native._source_log_model
    expected_models = np.asarray(
        [model(historical_xy, (gaussian,)) for gaussian in gaussians]
    )
    calls: list[Any] = []

    def check_layout(coordinates: Any, components: Any) -> Any:
        np.testing.assert_array_equal(coordinates, historical_xy)
        assert coordinates.strides == historical_xy.strides
        result = model(coordinates, components)
        np.testing.assert_array_equal(result, model(historical_xy, components))
        calls.append(components)
        return result

    monkeypatch.setattr(native, "_source_log_model", check_layout)
    result = amended.derive_retained_pybdsf_source_unions(
        source_rows=sources[::-1],
        gaussian_rows=gaussians[::-1],
        native_island_labels=labels,
    )
    assert len(calls) == 2
    expected = np.zeros_like(labels)
    expected[coordinate_yx[:, 0], coordinate_yx[:, 1]] = (
        np.argmax(expected_models, axis=0) + 1
    )
    np.testing.assert_array_equal(result.source_union_label_plane, expected)


@pytest.mark.parametrize("coincident", (False, True))
@pytest.mark.parametrize("reverse", (False, True))
def test_source_label_holes_and_ties_preserve_native_membership(
    coincident: bool,
    reverse: bool,
) -> None:
    labels = np.zeros((9, 12), dtype=np.int32)
    labels[:6, :6] = 1
    labels[:6, 8:] = 3
    labels[8, :2] = 5  # Fitless island is not a fabricated source.
    sources = tuple(
        native.PyBdsfSourceRow(island, source, centre, flux, 1)
        for island, source, centre, flux in (
            (0, 0, (1.0, 1.0), 31.0),
            (0, 1, (1.0, 1.0) if coincident else (4.0, 4.0), 37.0),
            (2, 0, (10.0, 2.0), 41.0),
        )
    )
    gaussians = tuple(
        native.PyBdsfGaussianRow(
            f"model-{index}",
            row.island_id,
            row.source_id,
            row.centre_xy,
            5.0,
            2.0,
            ((1.0, 0.0), (0.0, 1.0)),
        )
        for index, row in enumerate(sources)
    )
    arguments = {
        "source_rows": sources[::-1] if reverse else sources,
        "gaussian_rows": gaussians[::-1] if reverse else gaussians,
        "native_island_labels": labels,
    }
    result = amended.derive_retained_pybdsf_source_unions(**arguments)
    assert [row.integrated_flux_jy for row in result.sources] == [
        31.0,
        37.0,
        41.0,
    ]
    assert result.source_support_labels == (
        (1, None, 3) if coincident else (1, 2, 3)
    )
    assert result.unowned_native_support_labels == (5,)
    assert len(result.components) == 3
    np.testing.assert_array_equal(
        result.source_union_label_plane > 0, np.isin(labels, (1, 3))
    )
    assert np.all(result.source_union_label_plane[:6, 8:] == 3)
    assert not result.source_union_label_plane.flags.writeable
    assert result.source_union_derivation.endswith(
        "v2-explicit-unavailable-topology"
    )
    if coincident:
        assert np.all(result.source_union_label_plane[:6, :6] == 1)
    else:
        previous = native.derive_pybdsf_source_model_dominance(**arguments)
        assert result.sources == previous.sources
        assert result.components == previous.components
        np.testing.assert_array_equal(
            result.source_union_label_plane, previous.source_union_label_plane
        )


@pytest.mark.parametrize(
    "defect", ("missing-native-island", "missing-component", "source-count")
)
def test_unavailable_support_does_not_accept_invalid_native_membership(
    defect: str,
) -> None:
    source = native.PyBdsfSourceRow(
        0, 0, (1.0, 1.0), 3.0, 2 if defect == "source-count" else 1
    )
    gaussian = native.PyBdsfGaussianRow(
        "model", 0, 0, (1.0, 1.0), 3.0, 1.0, ((1.0, 0.0), (0.0, 1.0))
    )
    labels = np.ones((4, 7), dtype=np.int32)
    if defect == "missing-native-island":
        labels[:] = 2
    with pytest.raises(ValueError, match=r"membership.*inconsistent"):
        amended.derive_retained_pybdsf_source_unions(
            source_rows=(source,),
            gaussian_rows=() if defect == "missing-component" else (gaussian,),
            native_island_labels=labels,
        )
