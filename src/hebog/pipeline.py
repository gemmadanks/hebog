"""Public source-finding pipeline API."""

from __future__ import annotations

from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest, SourceFinderResult
from hebog.executors import Executor


def find_sources(
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    executor: Executor,
) -> SourceFinderResult:
    """Find sources and materialise catalogue, mask, and RMS products.

    Raises:
        NotImplementedError: Until the equivalence baseline in the
            implementation plan is complete and the first scientific stage is
            implemented.
    """
    del request, config, executor
    raise NotImplementedError(
        "Source finding is not implemented; follow the implementation plan"
    )
