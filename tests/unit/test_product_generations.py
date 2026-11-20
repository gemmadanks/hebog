"""Contracts for exact, immutable intermediate-product generations."""

from __future__ import annotations

import pickle
from dataclasses import replace

import pytest

from hebog.data_models import (
    ImageBounds,
    PartitionManifest,
    ProductChunk,
    ProductGenerationManifest,
)
from hebog.data_models.generations import (
    ProductGenerationIndex,
    ProductGenerationRow,
)


def _partition() -> PartitionManifest:
    """Return four deterministic output owners."""
    return PartitionManifest.create(
        image_shape_yx=(5, 7),
        tile_core_shape_yx=(3, 4),
        halo_yx=(0, 0),
    )


def _chunks(
    *,
    generation_id: str = "run-001",
    product_names: tuple[str, ...] = ("mask", "rms"),
) -> tuple[ProductChunk, ...]:
    """Return one complete chunk record for every product and owner."""
    return tuple(
        ProductChunk(
            generation_id=generation_id,
            product_name=product_name,
            tile_id=tile.tile_id,
            core_bounds=tile.core_bounds,
            dtype="|u1" if product_name == "mask" else "<f8",
            shape_yx=tile.core_bounds.shape_yx,
            content_sha256=f"{index:064x}",
        )
        for index, (product_name, tile) in enumerate(
            (product_name, tile)
            for product_name in product_names
            for tile in _partition().tiles
        )
    )


def _generation() -> ProductGenerationManifest:
    """Create one valid complete generation in canonical order."""
    return ProductGenerationManifest.create(
        generation_id="run-001",
        partition_manifest=_partition(),
        product_names=("rms", "mask"),
        chunks=reversed(_chunks()),
    )


def test_generation_is_canonical_serializable_and_pickle_safe() -> None:
    """Completion metadata is deterministic and safe for scheduler payloads."""
    generation = _generation()

    assert generation.product_names == ("mask", "rms")
    assert tuple(
        (chunk.product_name, chunk.tile_id) for chunk in generation.chunks
    ) == tuple(
        (product_name, tile.tile_id)
        for product_name in generation.product_names
        for tile in generation.partition_manifest.tiles
    )
    assert (
        ProductGenerationManifest.from_json_bytes(
            generation.canonical_json_bytes()
        )
        == generation
    )
    assert generation.canonical_json_bytes().endswith(b"\n")
    assert pickle.loads(pickle.dumps(generation)) == generation


@pytest.mark.parametrize(
    ("chunks", "product_names", "message"),
    [
        (_chunks()[:-1], ("mask", "rms"), "missing"),
        (_chunks(), ("rms",), "unexpected"),
        (
            (replace(_chunks()[0], generation_id="run-002"), *_chunks()[1:]),
            ("mask", "rms"),
            "generation",
        ),
    ],
)
def test_generation_rejects_incomplete_unexpected_or_mixed_run_records(
    chunks: tuple[ProductChunk, ...],
    product_names: tuple[str, ...],
    message: str,
) -> None:
    """Only the exact expected records from one run can be completed."""
    with pytest.raises(ValueError, match=message):
        ProductGenerationManifest.create(
            generation_id="run-001",
            partition_manifest=_partition(),
            product_names=product_names,
            chunks=chunks,
        )


@pytest.mark.parametrize(
    ("additional", "message"),
    [
        ((_chunks()[0],), "duplicate"),
        (
            (replace(_chunks()[0], content_sha256="f" * 64),),
            "conflicting",
        ),
    ],
)
def test_generation_rejects_duplicate_or_conflicting_chunk_results(
    additional: tuple[ProductChunk, ...],
    message: str,
) -> None:
    """Retries cannot create two completion records for one output key."""
    with pytest.raises(ValueError, match=message):
        ProductGenerationManifest.create(
            generation_id="run-001",
            partition_manifest=_partition(),
            product_names=("mask", "rms"),
            chunks=(*_chunks(), *additional),
        )


def test_generation_rejects_wrong_ownership_and_inconsistent_dtype() -> None:
    """Records must preserve canonical cores and one dtype per product."""
    wrong_core = replace(
        _chunks()[0],
        core_bounds=ImageBounds(0, 2, 0, 4),
        shape_yx=(2, 4),
    )
    inconsistent_dtype = replace(_chunks()[1], dtype="<f4")

    for changed, message in (
        (wrong_core, "core bounds"),
        (inconsistent_dtype, "dtype"),
    ):
        chunks = (changed, *_chunks()[1:])
        if changed is inconsistent_dtype:
            chunks = (_chunks()[0], changed, *_chunks()[2:])
        with pytest.raises(ValueError, match=message):
            ProductGenerationManifest.create(
                generation_id="run-001",
                partition_manifest=_partition(),
                product_names=("mask", "rms"),
                chunks=chunks,
            )


def test_generation_rejects_invalid_identity_and_schema() -> None:
    """Published generation identities and versions are explicit."""
    document = _generation().model_dump(mode="json")

    with pytest.raises(ValueError, match="generation ID"):
        ProductGenerationManifest.create(
            generation_id="",
            partition_manifest=_partition(),
            product_names=("rms",),
            chunks=_chunks(product_names=("rms",)),
        )
    document["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        ProductGenerationManifest.model_validate(document)


def test_generation_rejects_noncanonical_products_tiles_and_order() -> None:
    """Stored manifests have one deterministic product and chunk ordering."""
    complete = _chunks()
    unexpected_tile = replace(
        complete[-1],
        tile_id="tile-99999-99999",
    )
    cases = (
        ((), (), "at least one product"),
        (("mask", "mask", "rms"), complete, "unique and canonical"),
        (
            ("mask", "rms"),
            (*complete[:-1], unexpected_tile),
            "unexpected tile",
        ),
        (("mask", "rms"), tuple(reversed(complete)), "canonical order"),
    )

    for product_names, chunks, message in cases:
        with pytest.raises(ValueError, match=message):
            ProductGenerationManifest(
                generation_id="run-001",
                partition_manifest=_partition(),
                product_names=product_names,
                chunks=chunks,
            )


def test_generation_splits_into_canonical_rows_and_an_index() -> None:
    """Each row record holds its tiles' chunks for every product, in order."""
    generation = _generation()

    rows = generation.rows()
    index = generation.index(f"{row.tile_y_index:064x}" for row in rows)

    assert [row.tile_y_index for row in rows] == [0, 1]
    assert rows[1].chunks == tuple(
        chunk
        for chunk in generation.chunks
        if chunk.tile_id.startswith("tile-00001-")
    )
    assert rows[1].tiles_per_row == 2
    assert all(
        ProductGenerationRow.from_json_bytes(row.canonical_json_bytes()) == row
        for row in rows
    )
    assert index.describes(_partition())
    assert not index.describes(
        PartitionManifest.create(
            image_shape_yx=(5, 7),
            tile_core_shape_yx=(5, 7),
            halo_yx=(0, 0),
        )
    )
    assert (
        ProductGenerationIndex.from_json_bytes(index.canonical_json_bytes())
        == index
    )
    with pytest.raises(ValueError, match="canonical"):
        ProductGenerationIndex.from_json_bytes(
            index.canonical_json_bytes().replace(b",", b", ")
        )


def test_row_record_rejects_partial_misordered_or_mixed_run_chunks() -> None:
    """A row record is exactly its own tiles, once each, from one run."""
    row = _generation().rows()[0]
    chunks = row.chunks
    cases = (
        (chunks[:-1], "whole tile columns"),
        ((), "whole tile columns"),
        ((chunks[1], chunks[0], *chunks[2:]), "canonical order"),
        (_generation().rows()[1].chunks, "canonical order"),
        (
            (replace(chunks[0], generation_id="run-002"), *chunks[1:]),
            "mixed generation",
        ),
    )

    for changed, message in cases:
        with pytest.raises(ValueError, match=message):
            ProductGenerationRow(
                generation_id=row.generation_id,
                tile_y_index=row.tile_y_index,
                product_names=row.product_names,
                chunks=changed,
            )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"generation_id": ""}, "generation ID"),
        ({"product_names": ()}, "at least one product"),
        ({"row_sha256": ()}, "SHA-256"),
        ({"row_sha256": ("A" * 64,)}, "SHA-256"),
    ],
)
def test_index_rejects_an_empty_identity_or_malformed_digests(
    changes: dict[str, object],
    message: str,
) -> None:
    """A completion index names its run, its products and every row."""
    document = _generation().index(("0" * 64, "1" * 64)).model_dump()

    with pytest.raises(ValueError, match=message):
        ProductGenerationIndex.model_validate({**document, **changes})
