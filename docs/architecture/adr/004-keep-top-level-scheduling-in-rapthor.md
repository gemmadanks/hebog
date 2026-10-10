---
tags:
  - architecture
  - dask
---

# ADR-004: Keep top-level scheduling in Rapthor

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-07-18 |
| **Last Updated** | 2026-10-10 |
| **Deciders** | Gemma Danks |
| **Tags** | Dask, execution, Rapthor, resources |

---

## Context

Rapthor already owns the Prefect/Dask flow, retries, restart state, worker
resources, and the lifecycle of materialised image products. Its current
source-finding path submits one coarse filtering task per image sector. PyBDSF
may create multiprocessing work internally, so Rapthor sometimes isolates it
in a subprocess to avoid daemon-worker and nested-process failures.

Hebog needs serial, local, and distributed execution without oversubscribing
the allocation or coupling scientific kernels to one scheduler.

## Problem Statement

Should Rapthor continue to own top-level scheduling, should Hebog create and
own a private Dask cluster, or should Hebog expose Dask arrays and fine-grained
tasks throughout its scientific API?

## Options Considered

| Option | Description | Resource safety | Testability | Rapthor integration | Performance control | Overall score |
| --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 2 | 2 | 2 | 1 | - |
| **Rapthor owns scheduling** | Hebog exposes scheduler-independent work and explicit executors | ✅ | ✅ | ✅ | ✅ | 21 |
| **Hebog owns a cluster** | Library creates and manages private Dask resources | ❌ | ⚠️ | ❌ | ⚠️ | 10 |
| **Dask-array API** | Distribute most arrays and kernels as fine-grained graphs | ⚠️ | ⚠️ | ⚠️ | ❌ | 13 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

## Decision Outcome

Rapthor will **own the top-level Prefect/Dask graph and resource budget**.
Hebog's scientific API remains scheduler-independent. An explicit executor may
run coarse batches serially, locally, or through an existing Dask client, but
Hebog will not create a private cluster or nested process pool by default.

Task boundaries exchange paths and small serializable records. Scientific
kernels operate on NumPy arrays and immutable configuration. Dask is execution
policy, not the array type required by every function.

For large images, Hebog may use the supplied client to construct a bounded
subgraph of coarse haloed-tile maps and hierarchical reductions as defined by
ADR-005. This does not transfer cluster ownership to Hebog: Rapthor still
admits the operation and owns the scheduler, worker resources, retries at the
pipeline boundary, and cancellation.

The serial executor is the deterministic reference. Local and Dask executors
must match its membership, ordering, outputs, and tolerances.

### Amendment of 10 October 2026: Hebog runs inside Rapthor's Dask worker

Rapthor's `main` (`c6196cb4`, 9 October 2026) runs its filter step in a
fresh interpreter per sector through LSMTool, with no Dask client in reach
of the finder. The maintainer decided that Rapthor replaces that call, for
`source_finder = hebog`, with a native Prefect task that runs Hebog
in-process on the Dask worker, keeping the PyBDSF subprocess as the
fallback. The decision above stands: Rapthor still owns the cluster, and
Hebog uses only the executor it is given.

Three uses are performance targets: one Rapthor sector across a cluster,
the usual run and the first focus; one sector on one node; and standalone
use on a local machine with smaller images, through the Serial or Thread
executor. Several sectors in flight stay supported, and Hebog also runs
alone on a cluster. Hebog defines what it needs from a Dask cluster to
scale and Rapthor provides it, changing its setup if it must
([ADR-010](010-scale-hebog-independently-of-its-integrations.md)). Rapthor
builds Hebog's executor from its own workers and passes it in, with the
cores Hebog may use:

- when its workers give each node several task slots, the target, Rapthor
  passes its client: Hebog's tile tasks stay single-threaded and numerous,
  each stage choosing its tile core and task count within the core budget,
  so Dask schedules every core; its tasks declare the core and memory they
  use under resource names Rapthor configures; and the analysis waits on
  one slot, seceding where it would otherwise hold its worker's only
  thread;
- while each node has one single-threaded worker, today's layout, Rapthor
  passes a thread executor that runs inside the worker's task, and one
  sector uses one node; Rapthor retires this path once the target is in
  place.

How Rapthor's workers serve DP3, WSClean and Hebog together, and when it
scales them, is Rapthor's decision. [How Hebog runs on Rapthor's Dask
layouts](../rapthor-execution-layouts.md) draws each layout and one way to
provide several task slots a node. No thread pool is nested inside a Dask
task, and Hebog's arrays stay NumPy behind the executor rather than Dask
arrays. One sector's speed-up is bounded by its serial share, which the
plan measures and cuts before tuning the topology (tasks 73, 74 and 72).

## Consequences

- Good, because one owner admits CPU and memory across the complete Rapthor
  pipeline.
- Good, because kernels remain easy to unit-test and profile without a running
  scheduler.
- Good, because retries and restart state operate on materialised products
  rather than live image objects.
- Bad, because the integration must define explicit coarse task and file
  boundaries.
- Bad, because standalone Hebog users must provide or select an executor rather
  than receiving an implicit cluster.
- Risk: batches may be too small for Dask or too large for balanced execution.
  The Phase 6 executor contract and scheduler-overhead benchmarks will tune
  them from evidence.

## Confirmation

Architecture tests will forbid scheduler clients, open files, and mutable
full-image objects in public results. One parameterized executor contract will
test ordering, serialization, exceptions, cancellation, retry behaviour, and
determinism. Rapthor integration benchmarks will record graph size, task
duration, transfer, spill, and memory before distributed execution is accepted.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-003](003-limit-hebog-to-rapthor-source-finding-contract.md), [ADR-005](005-scale-large-images-with-hierarchical-tiles.md) |
| **Documentation** | [Domain model](../../explanation/domain-model.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
