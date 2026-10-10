---
tags:
  - architecture
  - dask
---

# ADR-010: Scale Hebog independently of its integrations

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-10-10 |
| **Last Updated** | 2026-10-10 |
| **Deciders** | Gemma Danks |
| **Tags** | Dask, scalability, Rapthor, extensibility |

---

## Context

Hebog's first consumer is Rapthor, which owns its Prefect/Dask cluster
([ADR-004](004-keep-top-level-scheduling-in-rapthor.md)) and runs DP3 and
WSClean on it. Their needs differ from Hebog's and change during a run:
DP3's chunks change in number, size and memory with each self-calibration
cycle's solution intervals, so its workers may need to change too, and
WSClean runs across nodes with MPI and may use more Dask workers later.

Hebog also runs without Rapthor: standalone on a local machine, and alone
on a cluster when an image is too large for one node. Its target today is
two-dimensional continuum images, but spectral cubes and a time axis are
plausible later. On 10 October 2026, while the Rapthor integration was
being designed (plan task 16), the maintainer set the principle this ADR
records.

## Problem Statement

Rapthor's worker layout is chosen for its own tools, and Hebog's scaling
could either follow that layout or define its own needs.

Should Hebog's distributed design fit Rapthor's cluster, or should Hebog
define how it scales and let Rapthor, or any other caller, provide for it?

## Options Considered

| Option | Description | Standalone scaling | Future dimensions | Rapthor integration | Simplicity | Overall score |
| --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 2 | 1 | 2 | 1 | - |
| **A. Hebog defines its needs; callers provide them** | Hebog states what it needs from a Dask cluster; Rapthor adapts its workers, and may change to do so | ✅ | ✅ | ⚠️ | ✅ | 16 |
| **B. Hebog fits Rapthor's layout** | Hebog's tasks, resources and tiling follow Rapthor's worker setup | ❌ | ⚠️ | ✅ | ⚠️ | 12 |
| **C. Hebog manages its own workers** | Hebog starts or scales workers itself | ⚠️ | ✅ | ❌ | ❌ | 10 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

B ties Hebog's scaling to a layout chosen for other tools, which may change
with every cycle. C breaks ADR-004: Rapthor owns the cluster and its
resource budget, and a library that starts or scales workers fights its
caller's scheduler.

## Decision Outcome

We will use **option A**. Hebog defines what it needs from a Dask cluster
to scale, and states it once, in terms any caller can provide:

- **An executor the caller builds.** Hebog runs on the executor it is
  given, a Dask client the caller owns or a thread or serial executor, and
  never chooses one from the caller's layout. More worker task slots,
  across processes and nodes, give it more parallelism.
- **A core budget.** The caller states how many cores Hebog may use,
  defaulting to the client's capacity, which also counts threads other
  work holds. Each stage chooses its tile core from its halo and its task
  count from batching within that budget, and the run's timing record
  states the choice; the products do not depend on it.
- **Shared storage.** Workers read the input and the intermediate Zarr
  generations from a filesystem every node can see.
- **Declared resources, named by the caller.** Hebog's tasks state what
  they use, a core and an admitted memory size, as Dask resource
  annotations whose names and amounts the caller configures, and Hebog
  states the memory its analysis holds on the worker that runs it, for
  the caller to reserve. Hebog defines no resource of the caller's, such
  as a Prefect slot.
- **Native threads within the budget.** Workers limit the thread pools of
  NumPy's and SciPy's native libraries to their declared cores, so many
  workers a node do not oversubscribe it.
- **Cancellation reaches Hebog's tasks.** When the caller cancels or times
  out an analysis, every tile task it submitted stops and its staging is
  removed.
- **No assumptions about the rest of the cluster.** Hebog does not rely on
  a fixed worker count, on workers being dedicated to it, or on workers
  staying for a whole run.

Rapthor provides these for its own runs, and owns how its workers serve
DP3, WSClean and Hebog together, including scaling them during a flow. If
the integration needs a change to Rapthor's cluster setup, Rapthor changes
rather than Hebog's scaling. Standalone users provide the same things with
a cluster they start themselves.

Two-dimensional continuum images are the target. Partitions, halos and
reconciliation are two-dimensional today
(`PartitionManifest.tile_core_shape_yx`, `ImageBounds`), and they stay so
until a cube or time-axis use case exists; adding an axis is then a new
ADR. What keeps that open is already true and must stay true: the
executor protocol does not know the image's dimensions, tasks carry bounds
and generation names rather than arrays, and Zarr stores are
N-dimensional.

## Consequences

- Good, because Hebog scales the same way inside Rapthor, standalone on a
  cluster, and in any other pipeline, and its tests and benchmarks do not
  depend on Rapthor's setup.
- Good, because DP3's changing needs and WSClean's MPI stay Rapthor's
  concern, and Hebog tolerates workers joining or leaving between
  analyses.
- Bad, because Rapthor carries the work of fitting its cluster to Hebog
  as well as to its own tools, and the integration (plan tasks 20 and 72)
  documents what it must provide.
- Risk: a resource name or a memory amount that the caller declares
  wrongly lets Dask co-locate too much work; Hebog's admission checks
  what it can (plan task 17).
- Risk: thousands of tasks on a shared filesystem mean many small chunk
  files; plan task 25 evaluates Zarr v3's sharding codec, and the cluster
  benchmark measures the filesystem.
- Risk: cubes or a time axis may need halos and reconciliation along a new
  axis, which the two-dimensional partitioning cannot express; that is the
  later ADR's to decide, not a reason to generalize now.

## Confirmation

The executor contract suite runs the same products on Serial, Thread and
Dask executors; task 72 adds Hebog's resource annotations with
caller-configured names, and the cluster benchmark runs Hebog standalone
on a multi-node cluster as well as through Rapthor. The architecture tests
keep Rapthor, Prefect and LSMTool out of the package.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-004](004-keep-top-level-scheduling-in-rapthor.md), [ADR-005](005-scale-large-images-with-hierarchical-tiles.md), [ADR-007](007-use-zarr-for-intermediate-image-storage.md) |
| **Documentation** | [How Hebog distributes work](../distributed-execution.md), [How Hebog runs on Rapthor's Dask layouts](../rapthor-execution-layouts.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
