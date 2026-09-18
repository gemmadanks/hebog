"""Execution policies for coarse source-finding batches."""

from typing import TYPE_CHECKING

from hebog.executors.base import (
    Executor,
    ExecutorAdmissionError,
    ExecutorCapacity,
    ExecutorPayloadError,
    TaskRequirement,
    reduce_in_canonical_order,
)
from hebog.executors.serial import SerialExecutor
from hebog.executors.threads import ThreadExecutor

if TYPE_CHECKING:
    from hebog.executors.dask import DaskExecutor

__all__ = [
    "DaskExecutor",
    "Executor",
    "ExecutorAdmissionError",
    "ExecutorCapacity",
    "ExecutorPayloadError",
    "SerialExecutor",
    "TaskRequirement",
    "ThreadExecutor",
    "reduce_in_canonical_order",
]


def __getattr__(name: str) -> object:
    """Load the optional concrete Dask executor only when requested."""
    if name == "DaskExecutor":
        from hebog.executors.dask import (  # noqa: PLC0415
            DaskExecutor,
        )

        return DaskExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
