"""Whole-plane detection-island rows, which the tiled rounds reproduce."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from hebog.science.catalogues import (
    build_detection_island_catalogue,
    detection_island_identifier,
    island_ids_by_owner,
    measure_detection_island,
)
from hebog.science.models import CatalogueIsland

_BEAM_AREA_PIXELS = 4.0


def _mask(shape: tuple[int, int], *regions: tuple[slice, slice]):
    """Return one retained mask holding the given rectangles."""
    mask: npt.NDArray[np.bool_] = np.zeros(shape, dtype=np.bool_)
    for region in regions:
        mask[region] = True
    return mask


def test_islands_are_ordered_by_their_canonical_first_pixel() -> None:
    """Row order follows the image, not the order regions were written."""
    retained = _mask(
        (12, 12),
        (slice(8, 10), slice(1, 3)),
        (slice(1, 3), slice(6, 8)),
        (slice(1, 3), slice(1, 3)),
    )
    residual = np.ones((12, 12), dtype=np.float64)
    rms = np.ones((12, 12), dtype=np.float64)

    catalogue = build_detection_island_catalogue(
        residual,
        rms,
        retained,
        np.zeros((12, 12), dtype=np.int32),
        beam_area_pixels=_BEAM_AREA_PIXELS,
    )

    assert [island.identifier for island in catalogue.islands] == [
        "island-detection-1-1",
        "island-detection-1-6",
        "island-detection-8-1",
    ]


def test_an_island_summarises_only_the_pixels_its_mask_retains() -> None:
    """Flux, noise and brightness come from the island's own pixels."""
    retained = _mask((6, 6), (slice(1, 3), slice(1, 3)))
    residual = np.full((6, 6), -5.0, dtype=np.float64)
    residual[1:3, 1:3] = np.array([[1.0, 2.0], [3.0, 4.0]])
    rms = np.full((6, 6), 9.0, dtype=np.float64)
    rms[1:3, 1:3] = np.array([[1.0, 2.0], [3.0, 8.0]])

    catalogue = build_detection_island_catalogue(
        residual,
        rms,
        retained,
        np.zeros((6, 6), dtype=np.int32),
        beam_area_pixels=_BEAM_AREA_PIXELS,
    )

    assert catalogue.islands == (
        CatalogueIsland(
            identifier="island-detection-1-1",
            pixel_count=4,
            integrated_flux_jy=10.0 / _BEAM_AREA_PIXELS,
            local_rms_jy_per_beam=2.5,
            mean_brightness_jy_per_beam=2.5,
        ),
    )


def test_eight_connected_regions_are_one_island() -> None:
    """Islands use the same connectivity the detection pass labels with."""
    retained = _mask(
        (8, 8), (slice(1, 3), slice(1, 3)), (slice(3, 5), slice(3, 5))
    )

    catalogue = build_detection_island_catalogue(
        np.ones((8, 8), dtype=np.float64),
        np.ones((8, 8), dtype=np.float64),
        retained,
        np.zeros((8, 8), dtype=np.int32),
        beam_area_pixels=_BEAM_AREA_PIXELS,
    )

    assert len(catalogue.islands) == 1
    assert catalogue.islands[0].pixel_count == 8


def test_an_owner_names_every_island_its_retained_support_reaches() -> None:
    """Published support can be split, so an owner names a tuple of islands."""
    retained = _mask(
        (10, 12), (slice(1, 3), slice(1, 3)), (slice(1, 3), slice(8, 10))
    )
    owners = np.zeros((10, 12), dtype=np.int32)
    owners[1:3, 1:3] = 4
    owners[1:3, 8:10] = 4
    owners[6:8, 1:3] = 7

    catalogue = build_detection_island_catalogue(
        np.ones((10, 12), dtype=np.float64),
        np.ones((10, 12), dtype=np.float64),
        retained,
        owners,
        beam_area_pixels=_BEAM_AREA_PIXELS,
    )

    assert dict(catalogue.island_ids_by_owner) == {
        4: ("island-detection-1-1", "island-detection-1-8")
    }


def test_a_mask_with_no_retained_pixel_measures_nothing() -> None:
    """An empty mask is a valid answer, not an error."""
    catalogue = build_detection_island_catalogue(
        np.ones((4, 4), dtype=np.float64),
        np.ones((4, 4), dtype=np.float64),
        np.zeros((4, 4), dtype=np.bool_),
        np.ones((4, 4), dtype=np.int32),
        beam_area_pixels=_BEAM_AREA_PIXELS,
    )

    assert catalogue.islands == ()
    assert dict(catalogue.island_ids_by_owner) == {}


def test_an_island_without_a_retained_pixel_fails_closed() -> None:
    """A window that holds none of its island cannot be measured."""
    with pytest.raises(ValueError, match="at least one pixel"):
        measure_detection_island(
            np.ones((3, 3), dtype=np.float64),
            np.ones((3, 3), dtype=np.float64),
            np.zeros((3, 3), dtype=np.bool_),
            first_pixel_yx=(0, 0),
            beam_area_pixels=_BEAM_AREA_PIXELS,
        )


def test_island_identity_survives_the_join_from_observed_pairs() -> None:
    """The join names islands the same way whoever observed the pairs."""
    identifiers = {
        1: detection_island_identifier((2, 3)),
        2: detection_island_identifier((9, 1)),
    }

    joined = island_ids_by_owner(
        ((5, 2), (5, 1), (6, 1)),
        identifier_by_island_label=identifiers,
    )

    assert joined == {
        5: ("island-detection-2-3", "island-detection-9-1"),
        6: ("island-detection-2-3",),
    }


@pytest.mark.parametrize(
    ("identifier", "pixel_count", "message"),
    (
        ("", 1, "identifier must not be empty"),
        ("island-detection-0-0", 0, "pixel count must be positive"),
    ),
)
def test_an_island_row_requires_a_name_and_a_pixel(
    identifier: str, pixel_count: int, message: str
) -> None:
    """An unnamed or empty island row is never constructed."""
    with pytest.raises(ValueError, match=message):
        CatalogueIsland(
            identifier=identifier,
            pixel_count=pixel_count,
            integrated_flux_jy=1.0,
            local_rms_jy_per_beam=1.0,
            mean_brightness_jy_per_beam=1.0,
        )
