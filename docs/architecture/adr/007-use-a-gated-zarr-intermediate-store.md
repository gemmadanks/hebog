---
tags:
  - architecture
  - storage
  - zarr
  - scalability
---

# ADR-007: Use a gated Zarr intermediate store

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-07-31 |
| **Last Updated** | 2026-07-31 |
| **Deciders** | Gemma Danks |
| **Tags** | storage, Zarr, Dask, scalability, recovery |

---

## Context

Hebog must write image-sized intermediate planes in independently retryable
chunks without requiring a complete 100,000-by-100,000 plane on one worker.
The first Phase 1 implementation writes one NumPy file per tile and publishes
it with an atomic hard link. That implementation is readable and provides a
useful serial oracle, but retaining it as the production format would make
Hebog responsible for a private array layout, store backends, compression,
checksums, and interoperability.

[Zarr v3](https://zarr.readthedocs.io/en/v3.1.6/) is a maintained standard for
chunked multidimensional arrays and integrates with Dask and local or remote
stores. Zarr is only a storage mechanism: it does not define Hebog's
scientific schemas, tile ownership, exact expected chunk set, retry conflict
policy, run provenance, or completion transaction.

Hebog supports Python 3.11 through 3.14. Zarr 3.2 requires Python 3.12, while
[Zarr 3.1.6](https://pypi.org/project/zarr/3.1.6/) supports Python 3.11. The
3.2 line adds a runtime option that raises for missing chunks. Zarr 3.1 follows
the v3 specification's normal fill-value behaviour, so Hebog must distinguish
a deliberately written all-fill chunk from an absent chunk itself.

The reproducible local probe in
`scripts/benchmark/compare_intermediate_stores.py` compared the prototype with
the NumPy-file oracle using one warm-up and five measured repetitions. The
ignored machine-readable evidence records exact configuration, dependencies,
environment, stages, object counts, and stored bytes.

| Shape and chunk | NumPy oracle median | Zarr median | Zarr/oracle | NumPy bytes | Zarr bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1024², 256² | 0.281 s | 0.491 s | 1.75 | 8,390,656 | 8,041,519 |
| 3000², 512² | 0.828 s | 1.177 s | 1.42 | 72,004,608 | 69,023,524 |

These are exploratory local-store measurements, not reviewed performance
claims. They show that Zarr's relative overhead narrows with size but also
show that it must not replace the low-overhead small/local path by default.
They do not establish a distributed crossover or deployment-store result.

## Problem Statement

Should Hebog continue developing its private NumPy-file layout, use Zarr v3
for every intermediate plane, or adopt Zarr behind the product-sink boundary
only where controlled evidence shows that its scalability and recovery value
outweighs its overhead?

## Options Considered

| Option | Description | Maintainability (2) | Distributed scale (3) | Small latency (2) | Recovery (2) | Interoperability (2) | Python/platform support (2) | Score |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Gated Zarr with a fast path** | Zarr candidate for distributed planes; keep lower-overhead bounded paths | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | 37 |
| **Private NumPy-file format** | Extend the oracle into the production distributed format | ❌ | ⚠️ | ✅ | ✅ | ❌ | ✅ | 28 |
| **Zarr for every size** | Convert every intermediate plane regardless of execution tier | ✅ | ✅ | ❌ | ⚠️ | ✅ | ✅ | 33 |
| **Direct FITS only** | Use FITS section I/O for intermediate and final products | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | 29 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

## Decision Outcome

Hebog will use **Zarr v3 as the gated candidate for distributed intermediate
image planes while retaining a measured lower-overhead path for small or
one-tile work**.

The accepted decision establishes the storage boundary and qualification
rules; it does not yet declare Zarr production-qualified or make it the
unconditional default. The NumPy-file sink remains the serial oracle until
deployment-store, Dask, recovery, and crossover evidence passes. Direct FITS
may replace both for one-tile materialisation when it is faster with identical
semantics.

The current prototype follows these rules:

- Pin `zarr>=3.1.6,<3.2` while Python 3.11 is supported. Reassess the bound when
  the Python floor or Zarr compatibility changes.
- Create one run-scoped v3 group and one array per intermediate plane before
  submitting worker writes. Workers do not create metadata or own a scheduler.
- Map zero-origin canonical tile cores one-to-one onto regular Zarr chunks.
  Shifted scientific partitions cannot write this store directly until an
  explicit canonical-output reconciliation step owns each storage chunk.
- Use explicit little-endian bytes, Zstandard level 1, CRC32C, fill value zero,
  and `write_empty_chunks=True`. Codec selection remains a measured tuning
  point rather than an immutable scientific choice.
- Return a small `ZarrProductChunk` containing logical array selection, dtype,
  shape, and content SHA-256 rather than a Zarr object or encoded bytes.
- On Python 3.11, check the explicitly configured standard v3 default chunk
  key before decoding. This prevents a missing all-zero chunk from passing as
  a valid fill chunk. CRC32C detects encoded corruption and Hebog's content
  hash validates the logical result.
- Accept identical sequential retries and reject a different completed value.
  One canonical task owns each chunk. The completion manifest must reject
  missing, duplicate, conflicting, or mixed-run records before publishing a
  generation.

Zarr `LocalStore` does not document the conditional-create guarantee required
to resolve concurrent conflicting writers atomically. Therefore the current
prototype is not a completed distributed transaction. Before default use,
Hebog must either prove the selected deployment store's atomic or conditional
semantics or make the generation manifest and task ownership sufficient to
fail closed under deterministic concurrent fault tests.

## Consequences

- Good, because Hebog reuses an established chunked-array standard instead of
  growing a private distributed storage format.
- Good, because the scientific and scheduler-independent APIs remain plain
  arrays, paths, manifests, and immutable records.
- Good, because explicit chunk alignment allows workers to write independent
  complete objects without overlapping selections.
- Good, because empty chunks, missing chunks, encoded corruption, logical
  content, dtype, and geometry have separate tested checks.
- Good, because the small/local path is preserved rather than regressed to
  satisfy a large-image architecture goal.
- Bad, because Python 3.11 prevents using Zarr 3.2's native strict-missing
  option and requires a small standards-based existence check.
- Bad, because Zarr was 1.75 times and 1.42 times slower than the oracle at the
  two measured local anchors despite a modestly smaller footprint.
- Risk: the Zstandard setting may waste CPU on noise-like planes. Benchmark
  uncompressed plus CRC32C and fast codecs per product role.
- Risk: local results do not predict shared or object-store throughput at
  hundreds of nodes. The deployment benchmark gate remains open.
- Risk: Zarr's internal concurrency can oversubscribe a Dask worker. Record and
  tune it within the worker resource budget before scale qualification.

## Confirmation

- Unit tests validate the versioned, pickle-safe logical chunk record.
- Integration tests cover pre-initialized metadata, aligned independent and
  edge writes, NaNs, explicit all-fill chunks, missing chunks, CRC32C
  corruption, logical checksum disagreement, identical and conflicting
  sequential retries, invalid geometry and dtype, changed durable policy, and
  shifted-origin rejection.
- The benchmark script emits versioned `BenchmarkEvidence` with
  `StorageEvidence` for both matched implementations.
- The Phase 1 completion manifest must fail closed before any Zarr hierarchy is
  exposed as a complete generation.
- Controlled local, Dask, deployment-store, retry, and crossover evidence must
  pass before Zarr becomes the default for a size tier or the oracle is
  removed.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-005](005-scale-large-images-with-hierarchical-tiles.md), [ADR-006](006-isolate-compatibility-with-versioned-schemas.md) |
| **Documentation** | [Zarr 3.1.6 arrays](https://zarr.readthedocs.io/en/v3.1.6/user-guide/arrays/), [Zarr stores](https://zarr.readthedocs.io/en/v3.1.6/user-guide/storage/) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
