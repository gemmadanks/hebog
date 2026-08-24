"""Contracts for bounded combined-catalogue terminal-state reduction."""

from __future__ import annotations

from itertools import permutations

import pytest
from pydantic import ValidationError

from hebog.algorithms.combined_catalogue import (
    IncompleteCombinedCatalogueError,
    complete_combined_catalogue_state,
    reduce_combined_catalogue_shards,
)
from hebog.data_models.multiscale import (
    CombinedCatalogueShard,
    CombinedCatalogueState,
    CombinedIslandDisposition,
    CompletedCombinedCatalogueState,
    MultiscaleOmission,
)


def _disposition(
    island_id: str,
    *,
    status: str = "retained-compact",
) -> CombinedIslandDisposition:
    """Build one valid terminal disposition for reduction tests."""
    source_ids = (
        (f"source-{island_id}",) if status == "retained-compact" else ()
    )
    association_ids = (
        (f"scale-association-{island_id}",)
        if status == "accepted-multiscale"
        else ()
    )
    reason = (
        "governed-artifact"
        if status == "rejected-artifact"
        else "measurement-unavailable"
        if status == "failed"
        else None
    )
    return CombinedIslandDisposition.model_validate(
        {
            "island_id": island_id,
            "status": status,
            "source_ids": source_ids,
            "association_ids": association_ids,
            "reason": reason,
        }
    )


def _shard(
    *,
    accepted: tuple[str, ...] = (),
    deferred: tuple[str, ...] = (),
    dispositions: tuple[CombinedIslandDisposition, ...] = (),
    omissions: tuple[MultiscaleOmission, ...] = (),
) -> CombinedCatalogueShard:
    """Build one already canonical coarse-task state shard."""
    return CombinedCatalogueShard(
        accepted_island_ids=accepted,
        deferred_island_ids=deferred,
        dispositions=dispositions,
        omissions=omissions,
    )


def test_pairwise_reduction_is_canonical_and_records_bounded_evidence() -> (
    None
):
    """Five coarse shards reduce through three fan-in-two levels."""
    shards = tuple(
        _shard(
            accepted=(island_id,),
            dispositions=(_disposition(island_id),),
        )
        for island_id in (
            "island-echo",
            "island-alpha",
            "island-delta",
            "island-bravo",
            "island-charlie",
        )
    )

    reduction = reduce_combined_catalogue_shards(shards)

    assert reduction.input_shard_count == 5
    assert reduction.reduction_depth == 3
    assert reduction.maximum_input_shard_record_count == 2
    assert reduction.shard.accepted_island_ids == (
        "island-alpha",
        "island-bravo",
        "island-charlie",
        "island-delta",
        "island-echo",
    )
    assert (
        tuple(item.island_id for item in reduction.shard.dispositions)
        == reduction.shard.accepted_island_ids
    )


def test_reduction_is_invariant_to_shard_and_completion_order() -> None:
    """Equivalent coarse scheduling cannot alter final state bytes."""
    shards = (
        _shard(
            accepted=("island-alpha",),
            dispositions=(_disposition("island-alpha"),),
        ),
        _shard(
            deferred=("island-bravo",),
            dispositions=(
                _disposition("island-bravo", status="accepted-multiscale"),
            ),
        ),
        _shard(
            accepted=("island-charlie",),
            dispositions=(
                _disposition("island-charlie", status="rejected-artifact"),
            ),
        ),
    )

    reductions = tuple(
        reduce_combined_catalogue_shards(order)
        for order in permutations(shards)
    )

    assert all(item.shard == reductions[0].shard for item in reductions)
    assert all(item.reduction_depth == 2 for item in reductions)


def test_empty_reduction_and_completion_are_valid() -> None:
    """A scientifically empty image needs no fabricated terminal object."""
    reduction = reduce_combined_catalogue_shards(())

    assert reduction.input_shard_count == 0
    assert reduction.reduction_depth == 0
    assert reduction.maximum_input_shard_record_count == 0
    assert reduction.shard.record_count == 0

    completed = complete_combined_catalogue_state(
        catalogue_id="catalogue-empty",
        shards=(),
        maximum_state_records=1,
    )

    assert completed.state.publication_eligible is True
    assert completed.shard_count == 0


def test_complete_state_requires_exact_accepted_and_deferred_coverage() -> (
    None
):
    """Every expected island has exactly one non-failed terminal outcome."""
    shards = (
        _shard(
            accepted=("island-compact", "island-extended"),
            dispositions=(
                _disposition("island-compact"),
                _disposition(
                    "island-extended",
                    status="accepted-multiscale",
                ),
            ),
        ),
        _shard(
            deferred=("island-deferred",),
            dispositions=(
                _disposition(
                    "island-deferred",
                    status="rejected-artifact",
                ),
            ),
        ),
    )

    completed = complete_combined_catalogue_state(
        catalogue_id="catalogue-complete",
        shards=shards,
        maximum_state_records=16,
    )

    assert completed.state.publication_eligible is True
    assert completed.state.accepted_island_ids == (
        "island-compact",
        "island-extended",
    )
    assert completed.state.deferred_island_ids == ("island-deferred",)
    assert completed.shard_count == 2
    assert completed.reduction_depth == 1
    assert completed.maximum_shard_record_count == 4


@pytest.mark.parametrize(
    ("shard", "message"),
    [
        (
            _shard(accepted=("island-missing",)),
            "missing 1 terminal disposition",
        ),
        (
            _shard(
                accepted=("island-omitted",),
                dispositions=(_disposition("island-omitted"),),
                omissions=(
                    MultiscaleOmission(
                        object_id="scale-association-omitted",
                        stage="extended-measurement",
                        reason="insufficient-valid-support",
                    ),
                ),
            ),
            "contains 1 omission",
        ),
        (
            _shard(
                accepted=("island-failed",),
                dispositions=(_disposition("island-failed", status="failed"),),
            ),
            "contains 1 failed disposition",
        ),
    ],
)
def test_incomplete_state_is_never_returned_for_publication(
    shard: CombinedCatalogueShard,
    message: str,
) -> None:
    """Missing, omitted, and failed work all block the completion boundary."""
    with pytest.raises(IncompleteCombinedCatalogueError, match=message):
        complete_combined_catalogue_state(
            catalogue_id="catalogue-incomplete",
            shards=(shard,),
            maximum_state_records=8,
        )


@pytest.mark.parametrize("limit", [True, 0, -1])
def test_completion_requires_a_positive_integer_record_cap(
    limit: int,
) -> None:
    """The in-memory final state always has an explicit valid bound."""
    with pytest.raises(ValueError, match="positive integer"):
        complete_combined_catalogue_state(
            catalogue_id="catalogue-bounded",
            shards=(),
            maximum_state_records=limit,
        )


def test_completion_rejects_record_cap_overflow() -> None:
    """Required identities and terminal evidence both count toward memory."""
    shard = _shard(
        accepted=("island-alpha",),
        dispositions=(_disposition("island-alpha"),),
    )

    with pytest.raises(
        IncompleteCombinedCatalogueError,
        match="exceeds the in-memory record limit",
    ):
        complete_combined_catalogue_state(
            catalogue_id="catalogue-bounded",
            shards=(shard,),
            maximum_state_records=1,
        )


@pytest.mark.parametrize(
    ("shards", "message"),
    [
        (
            (
                _shard(accepted=("island-alpha",)),
                _shard(accepted=("island-alpha",)),
            ),
            "accepted island IDs must be unique",
        ),
        (
            (
                _shard(
                    accepted=("island-alpha",),
                    dispositions=(_disposition("island-alpha"),),
                ),
                _shard(
                    deferred=("island-alpha",),
                    dispositions=(_disposition("island-alpha"),),
                ),
            ),
            "accepted and deferred island IDs must be disjoint",
        ),
    ],
)
def test_reduction_rejects_duplicate_or_conflicting_global_ownership(
    shards: tuple[CombinedCatalogueShard, ...],
    message: str,
) -> None:
    """A deterministic sort cannot resolve contradictory shard ownership."""
    with pytest.raises(ValidationError, match=message):
        reduce_combined_catalogue_shards(shards)


def test_shard_rejects_unknown_or_noncanonical_dispositions() -> None:
    """Each coarse shard owns only terminal evidence for its local IDs."""
    with pytest.raises(ValidationError, match="unknown required island"):
        _shard(
            accepted=("island-alpha",),
            dispositions=(_disposition("island-bravo"),),
        )

    with pytest.raises(ValidationError, match="canonical"):
        _shard(
            accepted=("island-bravo", "island-alpha"),
        )

    with pytest.raises(
        ValidationError,
        match="disposition island IDs must be unique",
    ):
        _shard(
            accepted=("island-alpha",),
            dispositions=(
                _disposition("island-alpha"),
                _disposition("island-alpha"),
            ),
        )


def test_incomplete_state_remains_serializable_but_ineligible() -> None:
    """Operational inspection is allowed without weakening publication."""
    state = CombinedCatalogueState(
        catalogue_id="catalogue-inspectable",
        accepted_island_ids=("island-alpha",),
        deferred_island_ids=("island-bravo",),
        dispositions=(_disposition("island-alpha"),),
        omissions=(),
    )

    assert state.publication_eligible is False
    assert state.missing_disposition_ids == ("island-bravo",)

    with pytest.raises(
        ValidationError,
        match="must be publication eligible",
    ):
        CompletedCombinedCatalogueState(
            state=state,
            shard_count=1,
            reduction_depth=0,
            maximum_shard_record_count=3,
        )


def test_state_rejects_a_disposition_outside_required_islands() -> None:
    """Unknown terminal evidence cannot make a catalogue look complete."""
    with pytest.raises(ValidationError, match="unknown required island"):
        CombinedCatalogueState(
            catalogue_id="catalogue-invalid",
            accepted_island_ids=("island-alpha",),
            deferred_island_ids=(),
            dispositions=(_disposition("island-bravo"),),
            omissions=(),
        )
