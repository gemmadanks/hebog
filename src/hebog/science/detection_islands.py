# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Detection islands of the installed composition and their ownership."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import numpy.typing as npt

from hebog.algorithms.extended_measurement import (
    connected_component_labels,
)
from hebog.algorithms.label_groups import label_windows
from hebog.science.models import CatalogueIsland


def detection_island_identifier(first_pixel_yx: tuple[int, int]) -> str:
    """Name one detection island by the first pixel it owns.

    Raster order makes the first pixel canonical: it does not depend on how
    the mask was partitioned or in which order the tiles completed.

    Examples:
        >>> detection_island_identifier((12, 40))
        'island-detection-12-40'
    """
    return f"island-detection-{first_pixel_yx[0]}-{first_pixel_yx[1]}"


def measure_detection_island(
    residual_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    support: npt.NDArray[np.bool_],
    *,
    first_pixel_yx: tuple[int, int],
    beam_area_pixels: float,
) -> CatalogueIsland:
    """Summarise one island over the exact pixels its mask retains.

    Every array covers the window that holds the island, and ``support`` is
    that island alone: an island is mask connectivity, not owner support, so
    nothing here consults a label plane. The flux is the signed residual over
    those pixels, which is why an island row is reported without an
    uncertainty.

    Raises:
        ValueError: If the island retains no pixel in this window.
    """
    if not bool(np.any(support)):
        raise ValueError("detection island must retain at least one pixel")
    residual = residual_jy_per_beam[support]
    return CatalogueIsland(
        identifier=detection_island_identifier(first_pixel_yx),
        pixel_count=int(support.sum()),
        integrated_flux_jy=float(
            np.sum(residual, dtype=np.float64) / beam_area_pixels
        ),
        local_rms_jy_per_beam=float(np.median(rms_jy_per_beam[support])),
        mean_brightness_jy_per_beam=float(np.mean(residual)),
    )


@dataclass(frozen=True, slots=True)
class DetectionIslandCatalogue:
    """Every measured island and the islands each owner's support reaches."""

    islands: tuple[CatalogueIsland, ...]
    island_ids_by_owner: Mapping[int, tuple[str, ...]]


def build_detection_island_catalogue(  # noqa: PLR0913
    residual_jy_per_beam: npt.NDArray[np.float64],
    rms_jy_per_beam: npt.NDArray[np.float64],
    retained_mask: npt.NDArray[np.bool_],
    owner_labels: npt.NDArray[np.integer[Any]],
    parent_labels: npt.NDArray[np.integer[Any]],
    *,
    beam_area_pixels: float,
) -> DetectionIslandCatalogue:
    """Measure every island of one complete retained mask, in raster order.

    This is the readable whole-plane reference for the tiled rounds in
    :mod:`hebog.stages.islands`, which label each core and reconcile the
    fragments instead of labelling the plane. Rows are ordered by the island's
    canonical first pixel, which is the order labelling a whole plane gives.

    ``owner_labels`` are the measurement labels of the components the
    catalogue publishes; an owner is linked to every island its retained
    support reaches, because published support can be split between islands.
    ``parent_labels`` are the measurement labels of the owners those
    components were deblended from: a component whose own support reaches
    no island is linked to the islands its parent's support reaches.
    """
    labels = _connected_island_labels(retained_mask)
    windows = label_windows(labels)
    islands: list[CatalogueIsland] = []
    identifier_by_label: dict[int, str] = {}
    for label_value, crop in enumerate(windows, start=1):
        if crop is None:
            raise ValueError("detection islands must own at least one pixel")
        support = labels[crop] == label_value
        first = np.argwhere(support)[0]
        first_pixel_yx = (
            int(first[0]) + crop[0].start,
            int(first[1]) + crop[1].start,
        )
        island = measure_detection_island(
            residual_jy_per_beam[crop],
            rms_jy_per_beam[crop],
            support,
            first_pixel_yx=first_pixel_yx,
            beam_area_pixels=beam_area_pixels,
        )
        identifier_by_label[label_value] = island.identifier
        islands.append(island)
    return DetectionIslandCatalogue(
        islands=tuple(islands),
        island_ids_by_owner=island_ids_by_component(
            _owner_island_pairs(labels, owner_labels, retained_mask),
            _owner_island_pairs(labels, parent_labels, retained_mask),
            observed_label_pairs(owner_labels, parent_labels),
            identifier_by_island_label=identifier_by_label,
        ),
    )


def _connected_island_labels(
    retained_mask: npt.NDArray[np.bool_],
) -> npt.NDArray[np.int32]:
    """Label one retained mask's eight-connected islands."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        connected_component_labels(
            retained_mask,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    return labels


def _owner_island_pairs(
    island_labels: npt.NDArray[np.int32],
    owner_labels: npt.NDArray[np.integer[Any]],
    retained_mask: npt.NDArray[np.bool_],
) -> tuple[tuple[int, int], ...]:
    """Observe which islands each owner's retained support reaches."""
    return observed_label_pairs(
        np.where(retained_mask, owner_labels, 0), island_labels
    )


def observed_label_pairs(
    first_labels: npt.NDArray[np.integer[Any]],
    second_labels: npt.NDArray[np.integer[Any]],
) -> tuple[tuple[int, int], ...]:
    """Pair every label of one plane with each label of another it meets.

    This pairs an owner with the islands its support reaches, or a component
    with the parent owner whose support holds it, over a whole plane or one
    core; the island join is the same either way.

    Examples:
        >>> import numpy as np
        >>> observed_label_pairs(
        ...     np.array([[3, 3, 0], [0, 4, 4]]),
        ...     np.array([[1, 2, 2], [0, 2, 0]]),
        ... )
        ((3, 1), (3, 2), (4, 2))
    """
    selected = (first_labels > 0) & (second_labels > 0)
    if not bool(np.any(selected)):
        return ()
    pairs = np.unique(
        np.column_stack((first_labels[selected], second_labels[selected])),
        axis=0,
    )
    return tuple((int(first), int(second)) for first, second in pairs)


def island_ids_by_owner(
    pairs: tuple[tuple[int, int], ...],
    *,
    identifier_by_island_label: Mapping[int, str],
) -> dict[int, tuple[str, ...]]:
    """Name the islands every owner reaches, from observed label pairs.

    The pairs come either from one whole plane or from the cores that
    observed them, so this join is the same in both compositions.
    """
    owners: dict[int, set[str]] = {}
    for owner, island_label in pairs:
        owners.setdefault(owner, set()).add(
            identifier_by_island_label[island_label]
        )
    return {
        owner: tuple(sorted(identifiers))
        for owner, identifiers in sorted(owners.items())
    }


def island_ids_by_component(
    component_pairs: tuple[tuple[int, int], ...],
    parent_pairs: tuple[tuple[int, int], ...],
    component_parents: tuple[tuple[int, int], ...],
    *,
    identifier_by_island_label: Mapping[int, str],
) -> dict[int, tuple[str, ...]]:
    """Name the islands each component reaches, or else its parent's.

    A component reaches the islands its own support overlaps. Support
    refinement can leave part of an owner outside the retained mask, such as
    a faint component deblended onto a brighter one's rim; that component
    then belongs to the islands its parent owner reaches, as a Gaussian
    belongs to the island it was fitted in, rather than to none. The pairs
    come either from one whole plane or from the cores that observed them.

    Examples:
        >>> island_ids_by_component(
        ...     ((1, 10),),
        ...     ((7, 10),),
        ...     ((1, 7), (2, 7)),
        ...     identifier_by_island_label={10: "island-a"},
        ... )
        {1: ('island-a',), 2: ('island-a',)}
    """
    own = island_ids_by_owner(
        component_pairs,
        identifier_by_island_label=identifier_by_island_label,
    )
    parents = island_ids_by_owner(
        parent_pairs,
        identifier_by_island_label=identifier_by_island_label,
    )
    inherited: dict[int, set[str]] = {}
    for component, parent in component_parents:
        if component not in own and parent in parents:
            inherited.setdefault(component, set()).update(parents[parent])
    return dict(
        sorted(
            (
                *own.items(),
                *(
                    (component, tuple(sorted(identifiers)))
                    for component, identifiers in inherited.items()
                ),
            )
        )
    )
