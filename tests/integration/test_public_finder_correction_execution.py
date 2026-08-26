"""Fixture-only executor contracts for public-finder seed ownership."""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client, LocalCluster

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
)
from hebog.executors import DaskExecutor, SerialExecutor

OwnershipBatch: TypeAlias = tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
    float,
    dict[int, tuple[int, int]],
]


def _own_support(batch: OwnershipBatch) -> npt.NDArray[np.int32]:
    """Apply the pure ownership kernel in a worker-safe function."""
    labels, support, valid, beam_major_fwhm_pixels, references = batch
    return assign_seeded_multiscale_support(
        labels,
        support,
        valid,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        canonical_seed_references_yx=references,
    )


def _fixture() -> OwnershipBatch:
    """Return two seeds joined by multiscale support and finite wings."""
    labels = np.zeros((9, 11), dtype=np.int32)
    labels[4, 1] = 9
    labels[4, 9] = 2
    support = np.zeros(labels.shape, dtype=np.bool_)
    support[4, 1:10] = True
    support[3:6, 2] = True
    support[3:6, 8] = True
    return (
        labels,
        support,
        np.ones(labels.shape, dtype=np.bool_),
        8.0,
        {9: (4, 1), 2: (4, 9)},
    )


def _partition(batch: OwnershipBatch) -> tuple[OwnershipBatch, ...]:
    """Split x cores with the exact half-beam ownership halo."""
    labels, support, valid, beam, references = batch
    return (
        (labels[:, :10], support[:, :10], valid[:, :10], beam, references),
        (labels[:, 2:], support[:, 2:], valid[:, 2:], beam, references),
    )


def _stitch(parts: list[npt.NDArray[np.int32]]) -> npt.NDArray[np.int32]:
    """Extract non-overlapping cores from the two halo-bearing results."""
    return np.concatenate((parts[0][:, :6], parts[1][:, 4:]), axis=1)


@pytest.mark.integration
def test_seed_ownership_is_serial_dask_and_partition_invariant() -> None:
    """Bridge ownership is invariant to executor and exact-halo tiling."""
    batch = _fixture()
    serial = SerialExecutor()
    expected = serial.map_batches(_own_support, (batch,))[0]
    serial_partitioned = _stitch(
        serial.map_batches(_own_support, _partition(batch))
    )
    np.testing.assert_array_equal(serial_partitioned, expected)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        executor = DaskExecutor(client)
        dask_full = executor.map_batches(_own_support, (batch,))[0]
        dask_partitioned = _stitch(
            executor.map_batches(_own_support, _partition(batch))
        )

    np.testing.assert_array_equal(dask_full, expected)
    np.testing.assert_array_equal(dask_partitioned, expected)
