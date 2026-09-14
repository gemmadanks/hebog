"""R6 source unions with explicit unavailable exclusive topology.

The reviewed v1 adapter remains immutable. Reuse its native membership checks,
Gaussian model arithmetic and catalogue records; the amended partition alone
permits a valid source to lose every pixel to another native model.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
from scripts.validation import compact_sentinel_source_unions as native


@dataclass(frozen=True, slots=True)
class RetainedSourceUnionProjection:
    """Native records and aligned optional labels; no catalogue row is lost."""

    sources: tuple[native.SourceUnionSource, ...]
    components: tuple[native.SourceUnionComponent, ...]
    native_owner_label_plane: npt.NDArray[np.int32]
    source_union_label_plane: npt.NDArray[np.int32]
    source_support_labels: tuple[int | None, ...]
    unowned_native_support_labels: tuple[int, ...]
    source_union_derivation: Literal[
        "pybdsf-source-model-dominance-v2-explicit-unavailable-topology"
    ] = "pybdsf-source-model-dominance-v2-explicit-unavailable-topology"


def derive_retained_pybdsf_source_unions(
    *,
    source_rows: tuple[native.PyBdsfSourceRow, ...],
    gaussian_rows: tuple[native.PyBdsfGaussianRow, ...],
    native_island_labels: npt.ArrayLike,
) -> RetainedSourceUnionProjection:
    """Keep the v1 pixel winners, including deterministic native-key ties.

    Only modelled native island pixels are assigned. Fitless islands remain
    unowned, and a source with no winning pixel has label ``None`` rather
    than a fabricated label or measurement. No injected truth is consulted.
    """
    inputs = native._validated_pybdsf_inputs(
        source_rows, gaussian_rows, native_island_labels
    )
    keys_by_island: dict[int, list[tuple[int, int]]] = defaultdict(list)
    label_by_key = {
        key: label for label, key in enumerate(inputs.source_keys, start=1)
    }
    for key in inputs.source_keys:
        keys_by_island[key[0]].append(key)
    owners = np.zeros(inputs.labels.shape, dtype=np.int32)
    unowned: list[int] = []
    for label in sorted(inputs.native_labels):
        keys = keys_by_island.get(label - 1, [])
        if not keys:
            unowned.append(label)
            continue
        coordinate_yx = np.argwhere(inputs.labels == label)
        y_pixels, x_pixels = coordinate_yx[:, 0], coordinate_yx[:, 1]
        if len(keys) == 1:
            owners[y_pixels, x_pixels] = label_by_key[keys[0]]
        else:
            # Preserve v1's layout as well as values: einsum can otherwise
            # change round-off and hence ownership for nearly tied models.
            coordinates = np.asarray(coordinate_yx[:, ::-1], dtype=np.float64)
            models = np.asarray(
                [
                    native._source_log_model(
                        coordinates, inputs.gaussian_groups[key]
                    )
                    for key in keys
                ]
            )
            source_labels = np.asarray([label_by_key[key] for key in keys])
            owners[y_pixels, x_pixels] = source_labels[
                np.argmax(models, axis=0)
            ]
    present = frozenset(int(label) for label in np.unique(owners) if label > 0)
    support_labels = tuple(
        label if label in present else None
        for label in range(1, len(inputs.source_keys) + 1)
    )
    owners.setflags(write=False)
    sources, components = native._pybdsf_projection_records(inputs)
    return RetainedSourceUnionProjection(
        sources,
        components,
        inputs.labels,
        owners,
        support_labels,
        tuple(unowned),
    )
