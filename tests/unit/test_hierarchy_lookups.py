"""The hierarchy decision's lookups from features to their components."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace

import numpy as np
import pytest

from hebog.algorithms.source_association import (
    _components_for_feature_group,
    _hierarchy_attachments,
    _hierarchy_groups,
)
from hebog.data_models.source_association import DetectionComponentRecord

_Hierarchy = tuple[
    tuple[DetectionComponentRecord, ...],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[int, int]],
]


class _CountingLineages(Mapping[str, tuple[str, ...]]):
    """Component lineages that count how often one is read."""

    def __init__(self, lineages: Mapping[str, tuple[str, ...]]) -> None:
        self._lineages = lineages
        self.reads = 0

    def __getitem__(self, component_id: str) -> tuple[str, ...]:
        self.reads += 1
        return self._lineages[component_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._lineages)

    def __len__(self) -> int:
        return len(self._lineages)


def _record(index: int) -> DetectionComponentRecord:
    """Return one component record; only its identifier matters here."""
    return DetectionComponentRecord(
        component_id=f"component-{index:05d}",
        label_value=index + 1,
        canonical_pixel_yx=(0, index),
        centroid_yx=(0.0, float(index)),
        covariance_pixels_squared=None,
    )


def _random_hierarchy(seed: int) -> _Hierarchy:
    """Return components attached to a random four-scale feature hierarchy.

    Most features have one parent at the next coarser scale; some have two,
    which branches their lineage, and some none, which makes them roots.
    Most components attach to one finest feature; some to none or two.
    """
    rng = np.random.default_rng(seed)
    features_by_scale = [
        [f"feature-{scale}-{index:03d}" for index in range(count)]
        for scale, count in enumerate((24, 12, 6, 3))
    ]
    feature_index = {
        feature_id: (scale, index)
        for scale, features in enumerate(features_by_scale)
        for index, feature_id in enumerate(features)
    }
    parents_by_id: dict[str, tuple[str, ...]] = {}
    for scale, features in enumerate(features_by_scale[:-1]):
        for feature_id in features:
            parent_count = int(rng.choice(3, p=(0.1, 0.8, 0.1)))
            if parent_count:
                parents_by_id[feature_id] = tuple(
                    sorted(
                        str(parent)
                        for parent in rng.choice(
                            features_by_scale[scale + 1],
                            size=parent_count,
                            replace=False,
                        )
                    )
                )
    records = tuple(_record(index) for index in range(60))
    finest_features_by_component = {
        record.component_id: tuple(
            sorted(
                str(feature)
                for feature in rng.choice(
                    features_by_scale[0],
                    size=int(rng.choice(3, p=(0.1, 0.7, 0.2))),
                    replace=False,
                )
            )
        )
        for record in records
    }
    return records, finest_features_by_component, parents_by_id, feature_index


@pytest.mark.parametrize("seed", range(10))
def test_feature_lookups_match_scanning_every_component(seed: int) -> None:
    """A feature group's components are those whose lineage holds one of it."""
    records, finest, parents_by_id, feature_index = _random_hierarchy(seed)
    attachments = _hierarchy_attachments(
        records, finest, parents_by_id, feature_index
    )
    rng = np.random.default_rng(seed)

    for size in (1, 2, 5):
        for _ in range(10):
            feature_ids = frozenset(
                str(feature)
                for feature in rng.choice(
                    sorted(feature_index), size=size, replace=False
                )
            )
            assert _components_for_feature_group(
                feature_ids, attachments
            ) == frozenset(
                component_id
                for component_id, lineage in (
                    attachments.lineages_by_component.items()
                )
                if component_id not in attachments.ambiguous_component_ids
                and not feature_ids.isdisjoint(lineage)
            )


def test_grouping_reads_each_lineage_at_most_once() -> None:
    """Grouping does not scan every component's lineage for every feature.

    That scan made the decision quadratic: 6.6 s at 4,000 components.
    """
    records, finest, parents_by_id, feature_index = _random_hierarchy(5)
    attachments = _hierarchy_attachments(
        records, finest, parents_by_id, feature_index
    )
    lineages = _CountingLineages(attachments.lineages_by_component)
    counted = replace(attachments, lineages_by_component=lineages)

    groups = _hierarchy_groups(records, counted, feature_index, parents_by_id)
    for feature_id in feature_index:
        _components_for_feature_group(frozenset((feature_id,)), counted)

    assert lineages.reads <= len(records)
    assert groups == _hierarchy_groups(
        records, attachments, feature_index, parents_by_id
    )
