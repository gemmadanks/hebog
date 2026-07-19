"""Integration tests for execution on a local Dask scheduler."""

import pytest
from distributed import Client, LocalCluster

from hebog.executors import DaskExecutor, SerialExecutor


def _square(value: int) -> int:
    """Return the square of an integer in a worker-safe function."""
    return value**2


@pytest.mark.integration
def test_dask_executor_matches_serial_executor() -> None:
    """The Dask and serial executors preserve ordering and results."""
    inputs = [3, 1, 2]
    expected = SerialExecutor().map_batches(_square, inputs)

    cluster = LocalCluster(
        n_workers=1,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        actual = DaskExecutor(client).map_batches(_square, inputs)

    assert actual == expected
