"""Existing-Dask fixture contracts for compact sentinel alignment."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from distributed import Client, LocalCluster

from hebog.executors import DaskExecutor, SerialExecutor
from hebog.validation.external_successor_compiler import ContinuumTruthObject

_ROOT = Path(__file__).parents[2]
_PROGRAM = runpy.run_path(
    str(_ROOT / "scripts/validation/compact_sentinel_alignment.py")
)
AlignedComponent = _PROGRAM["AlignedComponent"]
AlignedSource = _PROGRAM["AlignedSource"]
AlignedSummaryInput = _PROGRAM["AlignedSummaryInput"]
compile_aligned_summary = _PROGRAM["compile_aligned_summary"]


def _fixture(index: int) -> Any:
    """Return one small worker-serializable semantic-alignment fixture."""
    labels = np.asarray(((7, 7, 0, 9, 9),), dtype=np.int32)
    return AlignedSummaryInput(
        input_id=f"fixture-{index}",
        finder_id="current-hebog",
        truth=(
            ContinuumTruthObject(
                "truth",
                1,
                (2.0, 0.0),
                3.0,
                "astronomical-source",
                ("overall",),
            ),
        ),
        truth_label_plane=np.asarray(((1, 1, 0, 1, 1),), dtype=np.int32),
        sources=(
            AlignedSource(
                "source",
                ("component-a", "component-b"),
                (7, 9),
                (2.0, 0.0),
                3.0,
            ),
        ),
        components=(
            AlignedComponent("component-a", "source", 7, (1.0, 0.0), 1.0),
            AlignedComponent("component-b", "source", 9, (3.0, 0.0), 2.0),
        ),
        native_owner_label_plane=labels,
        source_union_label_plane=np.asarray(labels > 0, dtype=np.int32),
        native_topology_domain="component-owner",
        published_support_mask=labels > 0,
        beam_fwhm_pixels=2.0,
        adaptive_background_trigger="boundary",
    )


@pytest.mark.integration
def test_aligned_evaluator_is_serial_existing_dask_and_order_invariant() -> (
    None
):
    """Caller-owned Dask returns the exact ordered Serial summaries."""
    batches = tuple(_fixture(index) for index in range(3))
    serial = SerialExecutor().map_batches(compile_aligned_summary, batches)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask = DaskExecutor(client).map_batches(
            compile_aligned_summary,
            tuple(reversed(batches)),
        )

    assert dask == list(reversed(serial))
