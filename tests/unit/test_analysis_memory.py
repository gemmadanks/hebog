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


def test_analysis_memory_grows_with_the_image() -> None:
    """The background's local-noise requests hold memory for every pixel."""
    small = analysis_memory_bytes((3_000, 3_000), expected_sources=800)
    large = analysis_memory_bytes((22_500, 22_500), expected_sources=800)

    assert 0 < small < large


# What the analysis held between its tasks, traced with Hebog's modules by
# scripts/benchmark/audit_task_memory.py: image shape, published sources and
# bytes. The LoTSS-DR3 and deep-field figures are rounded to the mebibyte.
_AUDITED_ANALYSES = (
    pytest.param((3_000, 3_000), 783, 179 * 2**20, id="lotss-dr3-3000"),
    pytest.param((10_000, 10_000), 8_547, 492 * 2**20, id="lotss-dr3-10000"),
    pytest.param((15_402, 15_402), 19_103, 978 * 2**20, id="lotss-dr3-15402"),
    pytest.param(
        (5_000, 5_000), 34_092, 1_557 * 2**20, id="elais-n1-deep-5000"
    ),
    pytest.param(
        (7_500, 7_500), 1_901, 299_707_252, id="lofar-hd-elais-n1-7500"
    ),
    pytest.param(
        (22_500, 22_500), 13_666, 1_943_762_677, id="lofar-hd-elais-n1-22500"
    ),
)


@pytest.mark.parametrize(
    ("shape_yx", "published_sources", "held_bytes"), _AUDITED_ANALYSES
)
def test_analysis_memory_covers_every_audited_anchor(
    shape_yx: tuple[int, int], published_sources: int, held_bytes: int
) -> None:
    """Every audited analysis holds at most 0.8 of its reservation.

    The quarter of headroom is for images no anchor measured, so an anchor
    fits under the statement before it. The sparse, finely sampled LOFAR-HD
    mosaic holds most per pixel and the deep field most per source.
    """
    stated = analysis_memory_bytes(
        shape_yx, expected_sources=published_sources
    )

    assert held_bytes * 5 <= stated * 4


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
