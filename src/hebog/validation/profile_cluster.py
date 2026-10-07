"""The local Dask cluster the complete-execution profile runs on.

The profile times stages in the driver on ``time.time`` and matches them
with the compute intervals of Dask's task stream. A Dask worker adds
``scheduler_delay``, its latest heartbeat estimate of its clock's offset
from the scheduler's, to the start and stop of every task it reports, and
re-estimates it from the asymmetry of each heartbeat's round trip. On one
host every process reads the same clock, which ``distributed`` reads with
``time.time`` on macOS and Linux, where the profile runs. The true offset
is then zero and the estimate is error alone: 2 to 287 ms on the
development machine while the driver, which hosts the scheduler, held the
interpreter lock. The profile's workers therefore keep it at zero.

Nothing here runs at import.
"""

from __future__ import annotations

import functools

from distributed import LocalCluster, Nanny, Worker


class SharedClockWorker(Worker):
    """A Dask worker that reports task times on its own clock, unshifted.

    It discards every estimate of its clock's offset, so the offset stays
    zero. ``distributed`` overrides the attribute the same way in
    ``distributed.utils_test.NoSchedulerDelayWorker`` for its own timing
    tests; that module imports pytest and test fixtures, so the profile does
    not load it into its workers.
    """

    @property
    def scheduler_delay(self) -> float:
        """Return the offset added to reported task times: none."""
        return 0.0

    @scheduler_delay.setter
    def scheduler_delay(self, estimate: float) -> None:  # pyright: ignore[reportIncompatibleVariableOverride]
        del estimate


def local_profile_cluster(worker_count: int) -> LocalCluster:
    """Return a local cluster of single-threaded shared-clock processes.

    Each worker runs in its own process under a nanny, as on a deployed
    cluster; the scheduler runs in this process.
    """
    return LocalCluster(
        n_workers=worker_count,
        threads_per_worker=1,
        processes=True,
        # A random port, so concurrent clusters never contend for one.
        dashboard_address=":0",
        # The cluster's worker class is the nanny that starts each worker
        # process; the nanny is told which worker to start.
        worker_class=functools.partial(Nanny, worker_class=SharedClockWorker),
    )
