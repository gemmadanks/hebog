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
    """Analyse one image and materialise its scientific products.

    Workflow adapters may compose multiple analyses and translate their
    products. In particular, the Rapthor adapter owns the true-/apparent-sky
    model filtering and its two RMS-image compatibility contract.

    Raises:
        NotImplementedError: Until the equivalence baseline in the
            implementation plan is complete and the first scientific stage is
            implemented.
    """
    del request, config, executor
    raise NotImplementedError(
        "Source finding is not implemented; follow the implementation plan"
    )
