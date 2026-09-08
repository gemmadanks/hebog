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
