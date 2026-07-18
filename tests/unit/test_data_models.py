"""Tests for scheduler-safe request and result records."""

import pickle
from pathlib import Path

from hebog import SourceFinderRequest


def test_request_is_pickle_serializable() -> None:
    """Dask can serialize the public request record."""
    request = SourceFinderRequest(
        image_path=Path("image.fits"),
        output_directory=Path("output"),
        run_id="test-run",
    )

    assert pickle.loads(pickle.dumps(request)) == request
