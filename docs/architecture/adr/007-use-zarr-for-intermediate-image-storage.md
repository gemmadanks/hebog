---
tags:
  - architecture
  - storage
  - zarr
  - scalability
---

# ADR-007: Use Zarr for intermediate image storage

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
An early Phase 1 prototype wrote one NumPy file per tile. Keeping that path as
well as Zarr would make Hebog maintain two chunk records, two error models, two
retry implementations, two test suites, and permanent backend-selection
logic.

[Zarr v3](https://zarr.readthedocs.io/en/v3.1.6/) is a maintained standard for
chunked multidimensional arrays. It provides local and remote stores, codec
pipelines, and Dask integration without making the scientific API depend on
Dask. Zarr is still only storage: Hebog owns tile ownership, expected chunks,
strict missing-chunk handling, retry conflicts, provenance, completion, and
workflow-facing products.

Hebog supports Python 3.11 through 3.14. Zarr 3.2 requires Python 3.12, while
[Zarr 3.1.6](https://pypi.org/project/zarr/3.1.6/) supports Python 3.11. Zarr
3.1 returns fill values for absent chunks, so Hebog must distinguish an
intentionally written all-fill chunk from a missing chunk.

An exploratory local comparison used one warm-up and five measured
repetitions. These component measurements are not reviewed performance claims:

| Shape and chunk | NumPy prototype median | Zarr median | Zarr/prototype | NumPy bytes | Zarr bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1024², 256² | 0.281 s | 0.491 s | 1.75 | 8,390,656 | 8,041,519 |
| 3000², 512² | 0.828 s | 1.177 s | 1.42 | 72,004,608 | 69,023,524 |

The measurements show real small/local overhead. They also show why retaining
both implementations would create a lasting crossover policy and duplicate
code. Architectural simplicity, maintainability, and a scalable standard are
preferred over preserving that private-format fast path.

## Decision Outcome

Hebog will use **Zarr v3 as its single intermediate image-plane storage
backend at every size**.

- Small and one-tile work uses one Zarr chunk with serial execution. It avoids
  Dask fan-out but does not select another storage backend.
- FITS is an ingress and final compatibility format, not an intermediate
  backend. Final products are streamed from a validated Zarr generation.
- The NumPy-file sink, its record schema, its tests, and the backend-comparison
  runner are removed. Historical measurements remain in this ADR and
  `LOG.md`; rejected implementation code is not retained as an oracle.
- `ZarrProductSink` is the one explicit storage boundary. It returns a small
  storage-object-free `ProductChunk`, and no generic sink protocol is added
  until a demonstrated second implementation requires one.
- Pin `zarr>=3.1.6,<3.2` while Python 3.11 is supported. Reassess the bound when
  the Python floor or Zarr compatibility changes.
- Create one run-scoped v3 group and one array per intermediate plane before
  worker writes. Workers do not create metadata or own a scheduler.
- Map zero-origin canonical tile cores one-to-one onto Zarr chunks. Shifted
  scientific partitions require canonical-output reconciliation before
  storage writes.
- Use explicit little-endian bytes, Zstandard level 1, CRC32C, fill value zero,
  and `write_empty_chunks=True`. Codec and concurrency settings remain
  measurable implementation choices, not scientific semantics.
- Check the configured standard v3 chunk key before decoding on Zarr 3.1.
  CRC32C detects encoded corruption and the record's SHA-256 checks logical
  content.
- Accept identical sequential retries and reject different completed values.
  A completion manifest must reject missing, duplicate, conflicting, or
  mixed-run records before publishing a generation.

Zarr `LocalStore` does not document the conditional-create guarantee needed to
resolve concurrent conflicting writers atomically. Before distributed
qualification, Hebog must prove the deployment store's atomic or conditional
semantics or make canonical task ownership and completion validation fail
closed under deterministic concurrent fault tests.

## Consequences

- Good, because Hebog maintains one chunk layout, record schema, retry path,
  and test suite.
- Good, because Hebog reuses an established chunked-array standard instead of
  growing a private distributed storage format.
- Good, because scientific functions and scheduler payloads remain plain
  arrays and immutable records rather than Zarr or Dask objects.
- Good, because explicit chunk alignment permits independent bounded writes.
- Bad, because current local probes show Zarr is 1.75 and 1.42 times slower
  than the removed prototype at the two measured anchors.
- Bad, because Python 3.11 prevents using Zarr 3.2's strict-missing option and
  requires a standards-based existence check.
- Risk: compression may waste CPU on noise-like planes. Benchmark codecs by
  product role and tune Zarr rather than introducing another backend.
- Risk: local results do not predict shared or object-store throughput at
  hundreds of nodes. Deployment-store evidence remains required.
- Risk: Zarr's internal concurrency can oversubscribe a Dask worker. Bound and
  record it within the worker resource budget.

If Zarr cannot meet a scientific, recovery, portability, or scalability gate,
revisit this ADR explicitly. Do not add an undocumented alternate backend or
size-based storage switch.

## Confirmation

- Unit tests validate the versioned, pickle-safe `ProductChunk` record.
- Integration tests cover initialization, aligned and edge writes, NaNs,
  all-fill and missing chunks, CRC32C corruption, logical checksum
  disagreement, retries, invalid geometry and dtype, changed policy, and
  shifted-origin rejection.
- The Phase 1 completion manifest must fail closed before any Zarr hierarchy is
  exposed as a complete generation.
- Controlled local, Dask, deployment-store, recovery, and end-to-end evidence
  must cover every affected performance tier. A slower Zarr configuration is
  optimized or rejected; it is not hidden by switching formats.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-005](005-scale-large-images-with-hierarchical-tiles.md), [ADR-006](006-isolate-compatibility-with-versioned-schemas.md) |
| **Documentation** | [Zarr 3.1.6 arrays](https://zarr.readthedocs.io/en/v3.1.6/user-guide/arrays/), [Zarr stores](https://zarr.readthedocs.io/en/v3.1.6/user-guide/storage/) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
