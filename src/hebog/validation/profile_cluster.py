"""The local Dask cluster the complete-execution profile runs on.

Each worker is a single-threaded process under a nanny, as on a deployed
cluster, and the scheduler runs in the driver's process. Tasks time
themselves where they run (``hebog.validation.task_recording``), so the
cluster needs no clock handling of its own.

A worker's memory limit is the budget ``DaskExecutor`` admits tasks by, and
nothing else: Dask's spilling, pausing and restarting are off. Hebog's
workers hold no data between tasks, so those would act on the pages an
allocator keeps after a large task, and a worker paused or restarted for
them would measure the allocator rather than Hebog. The 3,000² pilot of plan
task 73 peaked at 94% of an eighth of 15 GB, past Dask's pause threshold.

Nothing here runs at import.
"""

from __future__ import annotations

import dask.config
from distributed import LocalCluster

_MEMORY_ACTIONS_OFF = {
    f"distributed.worker.memory.{name}": False
    for name in ("target", "spill", "pause", "terminate")
}


def local_profile_cluster(
    worker_count: int, *, memory_limit_bytes: int | None = None
) -> LocalCluster:
    """Return a local cluster of single-threaded worker processes.

    ``memory_limit_bytes`` is each worker's limit; by default Dask gives
    each single-threaded worker the machine's memory over its core count.
    A ``DaskExecutor`` admits a task only within one worker's limit. Each
    nanny passes the configuration it was created with to its worker.
    """
    with dask.config.set(_MEMORY_ACTIONS_OFF):
        return LocalCluster(
            n_workers=worker_count,
            threads_per_worker=1,
            processes=True,
            # A random port, so concurrent clusters never contend for one.
            dashboard_address=":0",
            memory_limit="auto"
            if memory_limit_bytes is None
            else memory_limit_bytes,
        )
