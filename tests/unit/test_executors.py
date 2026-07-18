"""Tests for execution policies."""

from hebog.executors import SerialExecutor


def test_serial_executor_preserves_order() -> None:
    """The reference executor returns results in input order."""
    executor = SerialExecutor()

    assert executor.map_batches(lambda value: value**2, [3, 1, 2]) == [9, 1, 4]
