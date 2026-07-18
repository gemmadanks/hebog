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
| **Last Updated** | 2026-07-18 |
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

The serial executor is the deterministic reference. Local and Dask executors
must match its membership, ordering, outputs, and tolerances.

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
| **ADRs** | [ADR-003](003-limit-hebog-to-rapthor-source-finding-contract.md) |
| **Documentation** | [Domain model](../../explanation/domain-model.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
