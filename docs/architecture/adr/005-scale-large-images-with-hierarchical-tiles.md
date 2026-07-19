---
tags:
  - architecture
  - dask
  - scalability
---

# ADR-005: Scale large images with hierarchical tiles

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-07-18 |
| **Last Updated** | 2026-07-18 |
| **Deciders** | Gemma Danks |
| **Tags** | Dask, scalability, tiling, memory, large images |

---

## Context

Hebog must eventually process radio-continuum images up to 100,000 by
100,000 pixels and distribute useful work across 100 to several hundred Dask
worker nodes. Production nodes are expected to have hundreds of GB of RAM.
Such an image contains 10 billion pixels. One plane requires
40 GB at `float32` or 80 GB at `float64`, before background, RMS, normalized,
mask, multiscale, residual, and work arrays are considered.

A memory-rich node might hold one such plane, but a design that requires it
cannot reliably hold all concurrent scientific planes and work buffers or
distribute the operation across hundreds of nodes. Dividing only at Rapthor's
sector boundary is also insufficient: scientific structures, RMS windows,
convolutions, and connected islands may cross any internal partition.
Conversely, exposing a fine-grained Dask array graph as Hebog's scientific API
would couple every kernel and test to one scheduler and risk excessive
scheduler load.

ADR-004 keeps ownership of the cluster, top-level graph, and resource budget
in Rapthor. This decision defines how Hebog decomposes one admitted
source-finding operation inside that externally supplied execution context.

## Problem Statement

How should Hebog decompose large images so memory remains bounded, scientific
results do not depend on partitioning, and Dask can distribute work across
hundreds of nodes without an unmanageably fine task graph?

## Options Considered

| Option | Description | 100,000² scale | Boundary correctness | Scheduler operations | Small-image efficiency | Portability | Overall score |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 3 | 2 | 2 | 1 | 1 | - |
| **Hierarchical haloed tiles** | Bounded tile maps, boundary summaries, and tree reconciliation | ✅ | ✅ | ✅ | ✅ | ✅ | 27 |
| **One whole plane per worker** | Keep every scientific stage on one worker | ❌ | ✅ | ✅ | ✅ | ✅ | 21 |
| **Rapthor-only sector splitting** | Treat sectors as independent images with no internal reconciliation | ✅ | ❌ | ✅ | ✅ | ❌ | 21 |
| **Fine-grained Dask-array API** | Express most kernels as public block graphs | ✅ | ⚠️ | ❌ | ❌ | ⚠️ | 18 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

## Decision Outcome

Hebog will use **hierarchical haloed tiles** for all image-sized scientific
work. A small image follows the same semantics as one tile. A deterministic
partition manifest defines each tile's core, stage-specific halo, global
coordinates, ownership region, input chunks, and output chunks.

Large planes remain in bounded window-readable files or a chunk-addressable
store. This ADR does not select the physical storage format; Phase 0 and Phase
1 benchmarks will decide that separately. No Dask task payload or worker may
materialise a full 100,000-by-100,000 plane.

Each scientific stage uses the smallest graph shape that preserves its
semantics:

- tile-local maps process bounded cores and required halos;
- global statistics use mergeable summaries and tree reductions;
- connected components exchange boundary equivalences and reconcile labels
  deterministically;
- multiscale filters derive scale-specific halos and trim results to one
  owning core;
- source and catalogue shards merge hierarchically with stable identifiers;
- image products are written as independently retryable chunks before any
  required compatibility materialisation.

Task count grows with tiles and scientific stages, not pixels, RMS windows, or
small islands. Hebog may build this bounded subgraph through an executor using
Rapthor's existing Dask client, but it does not create a cluster, control the
top-level Prefect graph, or expose scheduler objects in public results.

Tile batching and worker caches use the memory budget admitted by Rapthor and
reported by the executor. Memory-rich nodes may process or retain more bounded
tiles concurrently, but tile ownership, boundary reconciliation, and
scientific results cannot depend on that resource choice. The policy reserves
headroom for concurrent pipeline work and configurable spill thresholds rather
than treating all node RAM as exclusively available to Hebog.

The executor's planner selects the lowest-overhead valid realization of these
semantics. A small image normally remains one direct-I/O tile and may bypass
chunk-store conversion and distributed fan-out. Partitioning, batching, and
distribution are introduced only where size-stratified end-to-end benchmarks
show that their benefit exceeds their setup and data-movement costs.

## Consequences

- Good, because peak worker memory is proportional to a tile core plus halo
  and bounded work buffers rather than total image size.
- Good, because one-tile, local, and distributed execution share scientific
  semantics and can be tested for partition invariance.
- Good, because boundary summaries and tree reductions avoid central gathers
  and keep scheduler work bounded at hundreds of nodes.
- Good, because tile retries and chunk writes can be idempotent and
  restartable.
- Good, because resource-aware batching can exploit hundreds of GB per node
  without introducing a second scientific path.
- Bad, because every image-sized algorithm must define its halo, ownership,
  merge operation, and boundary tests.
- Bad, because distributed connected-component reconciliation and global
  identifier stability add implementation complexity early in the project.
- Bad, because final FITS-compatible materialisation may remain an I/O
  bottleneck even when scientific work scales.
- Risk: a poor tile or storage layout can trade worker-memory safety for
  scheduler or shared-storage pressure. Controlled scale benchmarks must tune
  these choices.

## Confirmation

- Unit and property tests compare one tile with multiple tile sizes and
  partition origins, including sources and islands on tile edges and corners.
- Controlled benchmarks compare the full logarithmic size ladder with the
  previous reviewed Hebog curve and measure both sides of every executor,
  storage, partition, and batching crossover.
- Executor conformance tests vary worker count, completion order, retries, and
  batching without changing stable source membership or products beyond
  reviewed numerical tolerances.
- Architecture tests reject public records containing full planes, scheduler
  clients, or open files and reject production graphs with per-pixel or
  per-window tasks.
- The controlled scalability lane records graph size, scheduler throughput,
  worker occupancy, node/worker RAM, admitted memory, reserved headroom,
  transfer, spill, storage throughput, retries, and strong/weak scaling at 1,
  10, 50, 100, and at least 200 worker nodes.
- Before production cutover, a 100,000-by-100,000 qualification image must
  pass the scientific, partition-invariance, memory, recovery, runtime, and
  scaling-efficiency gates frozen in Phase 0.
- Large-scale science uses versioned generated truth, global invariants, and
  reference-sized cut-outs; it does not depend on PyBDSF completing the full
  100,000-by-100,000 image.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-004](004-keep-top-level-scheduling-in-rapthor.md) |
| **Documentation** | [Domain model](../../explanation/domain-model.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
