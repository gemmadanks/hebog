# One sector across the cluster (task 72)

## Plan summary

| Field | Value |
| --- | --- |
| Work item | Make one Rapthor sector's source finding scale on any Dask cluster |
| Status | `in progress`: increment 1 released in 0.25.0; the checkpoint is with the maintainer |
| Human owner | Maintainer |
| Agent owner | Agent |
| Created | 2026-10-18 |
| Last updated | 2026-11-13 |
| Related issue/PR | Task 72 in the [implementation plan](source-finder-implementation.md#one-sector-across-the-cluster) |

## Outcome and scope

### Goal

One sector's source finding spreads across the cores and nodes it is given,
so Hebog's finder part takes at most half of pinned PyBDSF `master`'s time
on dense sectors and no longer than `master`'s on the rest, with products
unchanged.

### Success criteria

- Both finders' times against the source count and cores are measured in
  the matched container, and a fitted model projects the ratio to the
  cluster's nodes and sets targets for Hebog (done).
- The four increments have merged and released, each with byte-identical
  products across Serial, Thread and Dask, tiling invariance and an
  unchanged quick check.
- The 10,000² anchor's local Dask curve falls below run `task74-stack`
  (429 s on six workers).
- The dense and sparse cells' matched ratios, and the Dask path's CPU
  overhead, are measured again after the last increment.

### In scope

The core budget and cost model; the executor's waiting, completion order
and capacity; the completion record split by tile; the driver's serial
work; the flat-noise estimate beside the true-sky analysis; Rapthor's
distributed path on its Hebog branch; and the documentation ADR-010 calls
for.

### Non-goals

Changing the science for speed; native code (its own gates and an ADR);
the cluster benchmark itself (tasks 27 and 30); Zarr sharding (task 25);
the 45,000² memory work (task 56).

### Constraints

- Products do not depend on tiling, batch sizes, worker count or completion
  order; Serial stays the single-threaded reference.
- The caller owns the scheduler: Hebog starts no pool or thread, its tasks
  are single-threaded and each declares its memory
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md)).
- No process-wide cache holds memory a task does not declare (decision of
  15 October).
- Locally: six performance cores, 18 GiB and a six-core, 16 GB VM running
  the matched container under Rosetta, so local curves beyond six workers
  measure swap. The cluster: up to 12 nodes of 96 or 192 cores, no local
  scratch, shared Lustre; Hebog assumes no node type.

## Context and evidence

Figures, dates and runs are on the
[progress page](../docs/reference/progress-against-goals.md#performance).
In short:

- **Measured** (Hebog 0.23.0, matched container): on Rapthor's thread path
  every sector of the 5,000² source-count ladder fails its limit, because
  the interpreter lock serialises Hebog's tasks. On single-threaded Dask
  workers Hebog takes about `master`'s time on the dense cell and 1.7 times
  it on the sparse cell.
- **Modelled** (0.25.0): on a node Hebog's time nears its floor, the
  driver's time plus each round's longest task, now 132 s on the dense cell
  and 46 s on the sparse one. The model projects every limit met on one
  node if `master` uses four cores of a dense sector's node, and the two
  dense sectors missing 0.50 if it used every core.
- **Where the serial work is:** the driver's FITS writes and reconciliation;
  results awaited in submission order; each task parsing the whole
  completion record; the driver re-reading and hashing every chunk it
  publishes; the flat-noise estimate starting only after the true-sky
  analysis.

| Assumption | Evidence | Impact if false | Who verifies |
| --- | --- | --- | --- |
| Rosetta slows both finders alike. | Both run in one container; only ratios are compared. | Every projected ratio shifts; the cluster decides. | Human, cluster run |
| `master` uses four cores of a dense sector's node and every core of a sparse one's. | On the dense cell its fitting takes the same time on four and six cores; on the sparse cell it keeps gaining to six. | On dense sectors the stricter targets in brackets on the progress page apply. | Human, cluster run |
| Per-task slowdown with more workers is local contention. | Eight local workers swapped 24 GB. | The cost model weights I/O, and the store work (task 25) moves earlier. | Agent |

## Open questions

| Question | Owner | Needed by | Status |
| --- | --- | --- | --- |
| Whether Rapthor's layout gives Hebog's client several task slots a node (Rapthor's change). | Human | Step 7 | `open` |
| The dense threshold. | Human | Checkpoint | Provisionally 10,000 sources; decision 3 in the implementation plan |
| Whether per-source costs join this task. | Human | Checkpoint | `open`; decision 5 in the implementation plan |

## Proposed approach

Measure first, then cut what the measurements name. The matched container
compares the finders; native profiles on a local Dask cluster time Hebog's
stages. The fitted model projects the ratio to the cluster's node types and
sets targets for the increments. Each increment also cuts the serial work it
touches where the gain is clear (decision of 18 October), shown by profiles
before and after.

### Expected files or components

- `src/hebog/stages/composition.py`, `stages/batching.py`,
  `stages/task_memory.py`, `stages/detection.py`: the core budget, the cost
  model and declarations that follow the chosen core.
- `src/hebog/executors/base.py`, `executors/dask.py`: completion in any
  order within a bounded window, capacity read each round, seceding while
  waiting.
- `src/hebog/io/zarr.py`, `data_models/generations.py`: the completion
  record split by tile, and chunk checksums reported by the writing tasks.
- `src/hebog/public_api.py`: the flat-noise estimate beside the true-sky
  analysis.
- `src/hebog/adapters/rapthor.py` and Rapthor's Hebog branch: the client,
  resource names and analysis reservation.
- `docs/architecture/distributed-execution.md`,
  `docs/how-to/integrate-into-a-pipeline.md`,
  `docs/reference/performance-profile.md`: what Hebog needs from a cluster.

## Execution

| Step | Work | Owner | Status | Completion evidence |
| --- | --- | --- | --- | --- |
| 1 | Instrument the matched benchmark and the scaling profile | Agent | `done` | Red-green tests; smoke runs |
| 2 | Build the 5,000² source-count ladder | Agent | `done` | Sector identities; `master`'s source counts |
| 3 | Measure both finders on the ladder and across cores; profile Hebog's stages | Agent | `done` | Evidence under `benchmark-results/` |
| 4 | Fit the model, project the ratios and set the targets | Agent | `done` | Progress page (runs `step4-night5-sweeps`, `release-0.25.0`) |
| — | Checkpoint: threshold, targets, increment order, per-source costs | Human | `not started` | Decisions recorded in the implementation plan |
| 5 | Increment 1: core budget and cost model | Agent | `done` | Release 0.25.0; floors re-measured (run `release-0.25.0`) |
| 6 | Increment 2: waiting and sharing | Agent | `not started` | As step 5, plus concurrent-analysis and joining-worker tests |
| 7 | Increment 3: Rapthor's distributed path | Agent, human on Rapthor | `not started` | Adapter and Rapthor-branch tests; integration container summary |
| 8 | Increment 4: both branches together | Agent | `not started` | As step 5 |
| 9 | Re-measure the cells, the local curve and the Dask CPU overhead | Agent | `not started` | Matched reports; scaling profile; progress page |
| 10 | Review against the success criteria | Human | `not started` | Acceptance |

## Checkpoints and risks

| Trigger | Human decision | Agent action while waiting |
| --- | --- | --- |
| The model and targets (now) | Confirm the threshold, targets and increment order; decide on per-source costs | Prepare the increment the recommended order puts next |
| The dense gate looks out of reach at deployable node counts | Choose CPU work, native code under its gates, or the gate | Report the gap and its causes |
| Each increment's release | Merge and release | Start the next increment on a stacked branch |
| Rapthor's layout change | Make it on the Rapthor branch, or ask the agent to prepare it | Use the standalone run as scaling evidence |

| Risk | Likelihood/impact | Mitigation | Owner |
| --- | --- | --- | --- |
| Smaller tiles multiply halo overhead and chunk count, so CPU rises faster than occupancy. | Medium/Medium | The cost model weighs halo and read amplification. | Agent |
| Out-of-order completion or task-reported checksums weaken the store's integrity checks. | Low/High | Readers still verify checksums; contract tests with injected corruption and reordering. | Agent |
| A task declares more than a core's share of the leanest node (3.9 GB). | Low/Medium | The cost model bounds the core by worker memory. | Agent |
| Many small chunk files load Lustre's metadata servers. | Medium/High | Task 25 evaluates Zarr sharding before the cluster benchmark. | Agent |
| Local contention hides real-node scaling. | High/Medium | Fit on one to six workers; the cluster dry run checks the model. | Agent |

## Validation

- Focused tests, red first; the executor contract suite under Serial,
  Thread and Dask; the tiling-invariance tests.
- `just quick-science-check`: products unchanged.
- `just profile-scaling` before and after each increment.
- `just quick-benchmark` on the affected tiers: the Hebog-curve rule.
- `just coverage` and `just pre-commit`.
- `scripts/benchmark/measure_filter_skymodel.py` on the dense and sparse
  cells at step 9.

## Decisions and progress

| Date | Type | Update | Next |
| --- | --- | --- | --- |
| 2026-10-18 | Decision | The gate binds dense sectors at 0.50 and the rest at parity; serial-work cuts are in scope where the gain is clear. | — |
| 2026-10-20 | Decision | The dense cell is the deep ELAIS-N1 window 3,600 pixels north of the centre, where `master` completes; the ladder's middle rungs raise its noise with a fixed seed. | — |
| 2026-10-21 | Decision | Only the dense cell runs the full protocol; the ladder keeps screening repetitions. The core sweeps run Hebog on single-threaded Dask workers. | — |
| 2026-10-22 | Decision | The cluster has up to 12 nodes of three kinds, with no local scratch; Hebog runs on every node type without per-node settings. | — |
| 2026-11-12 | Decision | Rapthor's task runs the analysis on single-threaded Dask worker processes on a cluster it owns, memory actions off, keeping threads for small sectors and tests; 0.25.0's higher worker peak is accepted. | Increment 3 carries it |
| 2026-11-13 | Progress | 0.25.0 (increment 1) cuts the floors to 132 s on the dense cell and 46 s on the sparse one; the refitted model projects every limit met on one node if `master` uses four cores of a dense sector's node. | Maintainer: the checkpoint; agent: the next increment |
