"""Unit tests for the memory a caller reserves for one analysis."""

from __future__ import annotations

from typing import Any

import pytest

import hebog
from hebog import analysis_memory_bytes


def test_analysis_memory_is_exported_from_the_package() -> None:
    """A caller sizes its reservation from the public package alone."""
    assert hebog.analysis_memory_bytes is analysis_memory_bytes
    assert "analysis_memory_bytes" in hebog.__all__


def test_analysis_memory_grows_with_the_expected_sources() -> None:
    """Every published source keeps records, so more sources reserve more."""
    sparse = analysis_memory_bytes((5_000, 5_000), expected_sources=1_000)
    dense = analysis_memory_bytes((5_000, 5_000), expected_sources=34_000)

    assert 0 < sparse < dense


def test_an_image_without_sources_still_reserves_the_modules() -> None:
    """An empty field holds Hebog's modules and its fixed records."""
    assert analysis_memory_bytes((64, 64), expected_sources=0) > 0


def test_analysis_memory_grows_mostly_with_the_sources() -> None:
    """The passes keep records per source; pixels add only a little.

    The envelope's largest image adds less to the reservation than a
    deep field's sources do.
    """
    small = analysis_memory_bytes((3_000, 3_000), expected_sources=800)
    large = analysis_memory_bytes((15_402, 15_402), expected_sources=800)
    deep = analysis_memory_bytes((3_000, 3_000), expected_sources=34_000)

    assert 0 < large - small < deep - small


def test_analysis_memory_depends_on_the_pixel_count() -> None:
    """The reservation follows the pixels, not the image's orientation."""
    assert analysis_memory_bytes(
        (2_000, 8_000), expected_sources=10
    ) == analysis_memory_bytes((8_000, 2_000), expected_sources=10)


@pytest.mark.parametrize(
    "shape_yx",
    [(0, 10), (10, -1), (True, 10), (10.0, 10)],
)
def test_analysis_memory_refuses_an_impossible_shape(
    shape_yx: tuple[Any, Any],
) -> None:
    """A shape that no image has is refused rather than sized."""
    with pytest.raises(ValueError, match="positive integer"):
        analysis_memory_bytes(shape_yx, expected_sources=1)


@pytest.mark.parametrize("expected_sources", [-1, 1.5, True])
def test_analysis_memory_refuses_an_impossible_source_count(
    expected_sources: Any,
) -> None:
    """A source count is a whole number of sources, never negative."""
    with pytest.raises(ValueError, match="non-negative integer"):
        analysis_memory_bytes((64, 64), expected_sources=expected_sources)
