"""Bounded hierarchical reduction of terminal combined-catalogue state."""

from __future__ import annotations

from collections.abc import Sequence
from numbers import Integral

from hebog.data_models.multiscale import (
    CombinedCatalogueReduction,
    CombinedCatalogueShard,
    CombinedCatalogueState,
    CombinedIslandDisposition,
    CompletedCombinedCatalogueState,
    MultiscaleOmission,
)


class IncompleteCombinedCatalogueError(ValueError):
    """Terminal Phase 5 evidence is incomplete or exceeds its bound."""


def _canonical_shard(
    *,
    accepted_island_ids: Sequence[str],
    deferred_island_ids: Sequence[str],
    dispositions: Sequence[CombinedIslandDisposition],
    omissions: Sequence[MultiscaleOmission],
) -> CombinedCatalogueShard:
    """Return one shard in global identity order."""
    return CombinedCatalogueShard(
        accepted_island_ids=tuple(sorted(accepted_island_ids)),
        deferred_island_ids=tuple(sorted(deferred_island_ids)),
        dispositions=tuple(
            sorted(dispositions, key=lambda item: item.island_id)
        ),
        omissions=tuple(sorted(omissions, key=lambda item: item.object_id)),
    )


def _merge_shards(
    left: CombinedCatalogueShard,
    right: CombinedCatalogueShard,
) -> CombinedCatalogueShard:
    """Merge exactly two shards without completion-order semantics."""
    return _canonical_shard(
        accepted_island_ids=(
            *left.accepted_island_ids,
            *right.accepted_island_ids,
        ),
        deferred_island_ids=(
            *left.deferred_island_ids,
            *right.deferred_island_ids,
        ),
        dispositions=(*left.dispositions, *right.dispositions),
        omissions=(*left.omissions, *right.omissions),
    )


def reduce_combined_catalogue_shards(
    shards: Sequence[CombinedCatalogueShard],
) -> CombinedCatalogueReduction:
    """Combine terminal evidence through deterministic pairwise levels."""
    input_shards = tuple(
        _canonical_shard(
            accepted_island_ids=shard.accepted_island_ids,
            deferred_island_ids=shard.deferred_island_ids,
            dispositions=shard.dispositions,
            omissions=shard.omissions,
        )
        for shard in shards
    )
    maximum_input_records = max(
        (shard.record_count for shard in input_shards),
        default=0,
    )
    level = list(input_shards)
    depth = 0
    while len(level) > 1:
        next_level: list[CombinedCatalogueShard] = []
        for index in range(0, len(level), 2):
            if index + 1 == len(level):
                next_level.append(level[index])
            else:
                next_level.append(
                    _merge_shards(level[index], level[index + 1])
                )
        level = next_level
        depth += 1
    empty = CombinedCatalogueShard(
        accepted_island_ids=(),
        deferred_island_ids=(),
        dispositions=(),
        omissions=(),
    )
    return CombinedCatalogueReduction(
        shard=level[0] if level else empty,
        input_shard_count=len(input_shards),
        reduction_depth=depth,
        maximum_input_shard_record_count=maximum_input_records,
    )


def complete_combined_catalogue_state(
    *,
    catalogue_id: str,
    shards: Sequence[CombinedCatalogueShard],
    maximum_state_records: int,
) -> CompletedCombinedCatalogueState:
    """Return complete terminal state or fail before product publication."""
    if (
        isinstance(maximum_state_records, bool)
        or not isinstance(maximum_state_records, Integral)
        or maximum_state_records < 1
    ):
        raise ValueError("maximum_state_records must be a positive integer")
    record_count = sum(shard.record_count for shard in shards)
    if record_count > maximum_state_records:
        raise IncompleteCombinedCatalogueError(
            "combined state exceeds the in-memory record limit"
        )
    reduction = reduce_combined_catalogue_shards(shards)
    merged = reduction.shard
    state = CombinedCatalogueState(
        catalogue_id=catalogue_id,
        accepted_island_ids=merged.accepted_island_ids,
        deferred_island_ids=merged.deferred_island_ids,
        dispositions=merged.dispositions,
        omissions=merged.omissions,
    )
    if state.missing_disposition_ids:
        raise IncompleteCombinedCatalogueError(
            "combined state is missing "
            f"{len(state.missing_disposition_ids)} terminal disposition(s)"
        )
    if state.omissions:
        raise IncompleteCombinedCatalogueError(
            f"combined state contains {len(state.omissions)} omission(s)"
        )
    failed_count = sum(
        disposition.status == "failed" for disposition in state.dispositions
    )
    if failed_count:
        raise IncompleteCombinedCatalogueError(
            f"combined state contains {failed_count} failed disposition(s)"
        )
    return CompletedCombinedCatalogueState(
        state=state,
        shard_count=reduction.input_shard_count,
        reduction_depth=reduction.reduction_depth,
        maximum_shard_record_count=(
            reduction.maximum_input_shard_record_count
        ),
    )
