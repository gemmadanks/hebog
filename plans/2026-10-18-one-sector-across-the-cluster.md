# One sector across the cluster (task 72)

## Plan summary

| Field | Value |
| --- | --- |
| Work item | Make one Rapthor sector's source finding scale on any Dask cluster |
| Status | `draft` |
| Human owner | Maintainer |
| Agent owner | Agent |
| Created | 2026-10-18 |
| Last updated | 2026-10-23 |
| Related issue/PR | Task 72 in the [implementation plan](source-finder-implementation.md#one-sector-across-the-cluster) |

## Outcome and scope

### Goal

One sector's source finding spreads across the cores and nodes it is given,
so that Hebog's finder part takes at most half of pinned PyBDSF `master`'s
on dense sectors, where PyBDSF is slow, and no longer than `master`'s on
the rest, with products unchanged.

### Success criteria

- Both finders' times against the source count at fixed cores, and their
  speed-ups against cores on a dense sector, are measured in the matched
  container; a fitted model projects the ratio on dense and sparse sectors
  at the cluster's node sizes and sets targets for Hebog's serial term,
  per-source cost and CPU; the maintainer confirms or moves the dense
  threshold from it.
- The four increments of the implementation plan have merged and released,
  each with byte-identical products across Serial, Thread and Dask in the
  executor contract suite, tiling invariance and an unchanged quick check.
- The local Dask curve of the 10,000² anchor falls further than run
  `task74-stack` (429 s on six workers), with the serial term at or below
  the model's target; every driver step has its own timer in the scaling
  profile.
- The matched ratios of the dense cell and the sparse cells, and the Dask
  path's CPU overhead, are measured again after the last increment.

### In scope

- Measurement tooling: sector classes in the matched benchmark, `master`'s
  core count and Hebog's worker count per run, a source-count ladder of
  sectors, and timers for the driver work the scaling profile charges to
  its enclosing stage.
- The core budget and cost model, tile cores and batch sizes, and the
  memory each task declares.
- The executor's completion order, capacity and waiting, the completion
  record's split by tile, and the driver's per-stage serial work.
- The flat-noise estimate beside the true-sky analysis.
- Rapthor's distributed path on its Hebog branch, and the documentation
  ADR-010 calls for.

### Non-goals

- Changing the science, thresholds or semantics for speed.
- Native code, which needs its own gates and an accepted ADR.
- The cluster benchmark itself (tasks 27 and 30), Zarr sharding (task 25)
  and the 45,000² memory work (task 56).

### Constraints

- Products do not depend on the tiling, batch sizes, worker count or
  completion order; the serial executor stays the single-threaded
  deterministic reference.
- The caller owns the scheduler; Hebog starts no pool or thread of its own,
  its tasks are single-threaded, and each declares its memory
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md)).
- No process-wide cache holds memory a task does not declare (decision of
  15 October).
- The development machine has six performance cores, 18 GiB and a
  six-core, 16 GB VM in which the matched container runs x86-64 under
  Rosetta; local curves beyond six workers measure swap and efficiency
  cores.
- The cluster (maintainer, 22 October) has up to 12 nodes of three
  kinds, NUMA or not: 96 cores with 747 GB, 192 cores with 747 GB and 192
  cores with 1,494 GB. No node has a local scratch disk, so every run's
  scratch store is on the shared Lustre filesystem. Hebog assumes no node
  type, memory layout or core pinning: each worker's memory limit and each
  task's declaration decide where work runs, and the products are the
  same on every node.

## Context and evidence

The gate is 0.50 on dense sectors, provisionally where `master` finds at
least 10,000 sources, and parity (an upper bound of 1.05) on the rest
(decision of 18 October). Rapthor gives PyBDSF every core of its node by
default (`filter_skymodel_ncores` defaults to `max_threads`, the node's
CPU count), and `master` spreads its Gaussian fitting, RMS and mean maps,
map interpolation, wavelet decomposition and shape fitting over `ncores`.
Like for like on one node therefore means against `master` on every core,
where both finders' serial work decides the ratio.

In the matched screening of 16 October Hebog's finder part was 2.43 times
`master`'s on the 3,000² sector (thread path) and 1.23 on the 10,000²
anchor with four Dask workers, where `master` finds 9,276 sources; both
kept about three of four cores busy. On the source-count ladder at 5,000²
(21 October, four cores, Rapthor's thread path) every cell fails its limit:
the ratio is 3.14 to 4.85 on sparse sectors and 3.16 and 2.28 on the two
dense ones. Hebog keeps 1.3 of four cores busy and `master` about 2.1, and
a linear fit gives Hebog about 690 s plus 61 ms a source against `master`'s
34 s plus 37 ms, so on this path the ratio tends to about 1.7. The dense
cell's full protocol gives 2.26 (bounds 2.24 to 2.28).

Hebog's own profile of the dense cell, with its flat-noise estimate
(21 October, native), shows the thread path held by the interpreter lock:
four threads finish 1.18 times faster than one, while summed task time
grows 2.6 times, and the component fits gain nothing. Single-threaded Dask
workers take 1,176, 681, 447 and 380 s on 1, 2, 4 and 6 workers. Of one
worker's time the component fits take 353 s and the two background
passes, true-sky and flat-noise, about 240 s each; the component fits run in 12
batches and the support publication in 3 tasks. Each run decodes 110 GB
from Zarr, 1,100 times the image. On the 10,000² anchor the two
background passes take 1,212 s of one worker's 1,919 s.

In the matched container, with Hebog on single-threaded Dask workers,
one a core, the dense cell's finder part is 1.03, 1.07 and 1.00 times
`master`'s on one, four and six cores, half its ratio on threads, and
Hebog's products are identical at every worker count. Past four cores
both finders gain little: Hebog runs 2.36 and 2.55 times faster than on
one core on four and six, `master` 2.46 and 2.47.

The model (`hebog.validation.scaling_model`, figures on the progress page)
suggests why `master` gains nothing past four cores here: one bin of
islands appears to bound its main Gaussian fitting, 593 and 586 s on four
and six cores against 1,368 s on one (medians of two runs). On a node
Hebog nears its floor, the driver's time with no task running plus each
round's longest task: 190 s natively on the dense cell, 83 s of it driver
and 84 s the component-fit, extended-group and publication rounds'
longest tasks. If `master` uses no more of a node than its sweep shows
and emulation slows both finders alike, 0.24.0 on one node meets 0.50 on
the dense cell (0.42) and parity on every sparse sector and misses 0.50
at 14,126 sources (0.53); lines fitted to both finders' times cross the
dense limit at about 11,000 to 12,000 sources, with single sectors
scattered about them. If `master` used every core, the dense cell
projects to 0.75 and the sparse sectors to up to 1.46.

Run `task74-stack` (15 October) took the 10,000² anchor from 1,357 s on
one worker to 429 s on six. An Amdahl fit gives 250 s serial and 1,085 s
parallel. About 70 s of the serial term is time with no task running; most
of the rest is the tails of rounds with too few tasks: the multiscale pass
(64 s), background (48 s), component fits (33 s), catalogue rows (30 s)
and the support pass (17 s), with the RMS FITS write (13 s) on the driver.
Summed task time grew from 1,280 s on one worker to 1,967 s on six and
2,575 s on eight, and the rounds that read most from Zarr ran four to five
times slower per task on eight workers, which swapped up to 24 GB.

The code shows where the serial work comes from:

- Tile cores are fixed at 2,048 pixels (`stages/composition.py`), so the
  later stages run 7 to 25 tasks a round at 10,000². Tile rounds now shrink
  their batches of up to four tiles until each of the executor's task
  slots has two, and the component-fit and extended-group rounds split
  their objects the same way, but the cores ignore the executor's
  capacity.
- Zarr chunks equal the tile core (`io/zarr.py`), so every task's declared
  memory is floored by a 2,048² read; the core, chunk size, read
  amplification and declarations change together.
- `DaskExecutor` waits for results in submission order, reads the cluster's
  capacity once and keeps two tasks in flight per thread
  (`executors/dask.py`), so one slow task stalls submission and workers
  that join later are unused.
- Each task parses and validates the whole completion record of the
  generations it reads, 16 MB and 0.42 s a task at 15,402², and the driver
  re-reads and hashes every chunk of every product it publishes, twelve
  publications per analysis (`io/zarr.py`).
- The flat-noise estimate runs after the whole true-sky analysis
  (`public_api.py`), so its background stage sits at the end of the
  critical path.
- The scaling profile charges publication, reconciliation, association
  and the flat-noise estimate to their enclosing stages, without timers of
  their own.

| Assumption | Evidence or reason | Impact if false | Owner to verify |
| --- | --- | --- | --- |
| `master`'s time grows faster than Hebog's with the source count. | In proportion only: on the ladder `master`'s finder part grows 5.2 times from 3,847 to 24,780 sources and Hebog's 2.4 times, but Hebog's cost a source is 1.7 times `master`'s on Rapthor's threads. | The dense gate needs Hebog's CPU to fall, not only its occupancy to rise; the checkpoint after step 4 reorders the work. | Agent, step 3 |
| The VM holds `master` on a dense ELAIS-N1 5,000² window. | On the window 3,600 pixels north of the field centre `master` finds 24,780 sources with a 5.8 GB peak, well inside the 16 GB VM; on the central window it stops with an `IndexError` in its moment-analysis fallback (a PyBDSF defect, also in 1.14.1, drafted for upstream), so the north window is the dense cell (decision of 20 October). | The dense cell moves to the cluster. | Agent, step 2 |
| Per-task inflation with workers is mostly local contention. | Eight workers swapped 24 GB; the I/O-heavy rounds inflate most. | The cost model weights I/O, and the store work of task 25 moves earlier. | Agent, steps 3 and 5 |
| Rosetta slows both finders alike. | Both run in the same container; only ratios are compared. Hebog's container time is 2.08 times its native time on one worker; `master` has no native measurement. | Every projected ratio scales with Hebog's factor over `master`'s; the cluster decides. | Human, cluster run |
| `master` uses no more of a node than the four cores its sweep shows. | Its Gaussian fitting takes the same time on four and six cores, bound by one bin of islands; only the dense cell has a sweep, and the VM contends beyond four workers. | `master` is faster on a node, and the targets in brackets on the progress page apply. | Agent, a sparse sweep; human, cluster run |

## Open questions

| Question | Owner | Needed by | Status or answer |
| --- | --- | --- | --- |
| Whether Rapthor's layout gives Hebog's Dask client several task slots a node, which is Rapthor's change. | Human | Step 7 | `open` |
| The dense threshold. | Human | Checkpoint after step 4 | Provisionally 10,000 sources; the model's lines cross 0.50 at about 11,000 to 12,000 |
| Whether per-source costs (association, fits and catalogue rows) join task 72 if the model shows they decide the dense gate. | Human | Checkpoint after step 4 | `open`; on a node the task work per source spreads across the cores, while the driver's per-source work, the catalogue write, reconciliation and catalogue records, is a third of the dense cell's driver time |

## Proposed approach

Measure first, then cut what the measurements name. The matched
container compares the finders; the local Dask cluster profiles Hebog's
stages, which the container's Rosetta emulation would distort. A model of
each finder's serial and parallel work, fitted per cell and against the
source count, projects the ratio to the cluster's three node types
and to 1 to 12 nodes, and its targets order the increments. The default
order is the implementation plan's; each increment also cuts the serial
work it touches where a measured gain is clear (decision of 18 October),
and the quick benchmark and profile before and after show the gain.

### Expected files or components

- `scripts/benchmark/measure_filter_skymodel.py`,
  `config/benchmarks/phase-0-performance.json` — sector classes by
  `master`'s source count with the dense and parity limits, and a core
  count per finder; red tests on the classification and the limit chosen.
- `scripts/benchmark/profile_complete_execution_worker.py`,
  `src/hebog/validation/scaling_profile.py` — timers for publication,
  reconciliation, association and the flat-noise estimate.
- `src/hebog/stages/composition.py`, `stages/batching.py`,
  `stages/task_memory.py`, `stages/detection.py` — the core budget, the
  cost model choosing tile cores and batch sizes, a batched candidate
  scan, and declarations that follow the chosen core; red tests that a
  larger budget yields more tasks and that products do not change.
- `src/hebog/executors/base.py`, `executors/dask.py` — completion in any
  order within a bounded window, capacity read per round, seceding while
  waiting; contract tests that completion order does not change products.
- `src/hebog/io/zarr.py`, `data_models/generations.py` — the completion
  record split by tile, and chunk checksums reported by the tasks that
  wrote them instead of re-read on the driver.
- `src/hebog/public_api.py` — the flat-noise estimate submitted beside the
  true-sky analysis.
- `src/hebog/adapters/rapthor.py` and Rapthor's Hebog branch — the client,
  resource names and analysis reservation.
- `docs/architecture/distributed-execution.md`,
  `docs/how-to/integrate-into-a-pipeline.md`,
  `docs/reference/performance-profile.md` — the budget, the cost model and
  what Hebog needs from a cluster.

## Execution

| Step | Work | Owner | Status | Completion evidence |
| --- | --- | --- | --- | --- |
| 1 | Instrument: sector classes and per-finder core counts in the matched benchmark; driver timers in the scaling profile | Agent | `done` | Red-green tests; a smoke run of each runner |
| 2 | Build the source-count ladder: 5,000² sectors from fields of rising depth (`config/benchmarks/source-count-ladder.json`), with the gap between the LoTSS-DR3 and deep ELAIS-N1 windows filled by the dense cell with its noise raised 1.5, 2, 3 and 4 times (`scripts/benchmark/build_source_count_ladder.py`), and confirm the VM holds `master` on the dense cell | Agent | `done` | Sector identities and checksums; `master`'s source counts |
| 3 | Measure: both finders on the ladder at four cores (one warm-up, two repetitions) and the full protocol on the dense cell (one warm-up, five); both on the dense cell at 1, 2, 4 and 6 cores, Hebog on as many single-threaded Dask workers (screening repetitions); Hebog's stage profile on the dense cell (1 and 4 threads; 1, 2, 4 and 6 Dask workers) and the anchor (1, 2, 4 and 6 Dask workers) | Agent | `in progress` | Evidence records and reports under `benchmark-results/` |
| 4 | Fit the model, project the ratios and set the targets | Agent | `done` | Model, projections and targets on the progress page (run `step4`) |
| — | Checkpoint: threshold, targets, increment order and whether per-source costs join | Human | `not started` | Decisions recorded in the implementation plan |
| 5 | Increment 1, core budget and cost model, with the batched candidate scan | Agent | `in progress` | Tests; scaling profile before and after; quick check and quick benchmark; release |
| 6 | Increment 2, waiting and sharing, with completion order, the split completion record and task-reported checksums | Agent | `not started` | As step 5; concurrent-analysis and joining-worker tests |
| 7 | Increment 3, Rapthor's distributed path | Agent, human on Rapthor | `not started` | Adapter and Rapthor-branch tests; integration container summary |
| 8 | Increment 4, both branches together | Agent | `not started` | As step 5 |
| 9 | Re-measure the dense and sparse cells, the local curve and the Dask CPU overhead; update the progress page | Agent | `not started` | Matched reports; scaling profile; progress page |
| 10 | Review against the success criteria | Human | `not started` | Acceptance |

## Checkpoints and risks

| Trigger | Human decision | Agent action while waiting |
| --- | --- | --- |
| Step 4's model and targets | Confirm the threshold, the targets and the increment order; decide whether per-source costs join | Continue increment 1, which every order needs |
| The model shows the dense gate out of reach at deployable node counts even with the serial target met | Choose between CPU work, native code under its gates, or the gate | Report the gap and its causes; continue the increments |
| Each increment's release | Merge and release | Start the next increment on a stacked branch |
| Rapthor's layout change | Make it on the Rapthor branch, or ask the agent to prepare it | Use the standalone run as the scaling evidence |

| Risk | Likelihood/impact | Mitigation or fallback | Owner |
| --- | --- | --- | --- |
| `master` does not slow with sources on the cells the VM holds. | Medium/High | The cluster's dense sector decides; report the local curve as it is. | Agent |
| Smaller tiles multiply halo overhead and Zarr chunk count, so occupancy rises but CPU rises more. | Medium/Medium | The cost model weighs halo and read amplification; keep the larger core where the profile shows no gain. | Agent |
| Out-of-order completion or task-reported checksums weaken the store's integrity checks. | Low/High | Every reader still verifies chunk checksums; contract tests with injected corruption and reordered completion. | Agent |
| A larger tile core raises a task's declaration above the memory a core of the leanest node (3.9 GB on 192 cores with 747 GB). | Low/Medium | The cost model bounds the core by the memory each worker holds; the dense cell's largest declaration is 1.6 GiB. | Agent |
| Thousands of small chunk files load Lustre's metadata servers, since no node has local scratch. | Medium/High | Task 25 evaluates Zarr's sharding codec before the cluster benchmark, which measures shared-storage throughput. | Agent |
| Memory traffic between NUMA domains slows workers. | Medium/Low | Single-threaded worker processes allocate their own memory; the guide shows how a launcher keeps each worker in one domain, which Hebog does not require. | Agent |
| Local contention hides real-node scaling. | High/Medium | Fit on one to six workers; the cluster dry run (task 27) checks the model. | Agent |
| Benchmark time on the shared machine. | Medium/Medium | Screening repetitions for the model's points; full protocol only at the gate's cells; runs detached and unattended. | Agent |

## Validation

- Focused tests for each change, red first; the executor contract suite
  under Serial, Thread and Dask; the tiling invariance tests.
- `just quick-science-check` — products unchanged.
- `just profile-scaling` before and after each increment — serial term,
  idle time and curve.
- `just quick-benchmark` on the affected tiers — the Hebog-curve rule.
- `just coverage` and `just pre-commit`.
- `scripts/benchmark/measure_filter_skymodel.py` — the dense and sparse
  cells at steps 3 and 9.

## Decisions and progress

| Date | Type | Update | Owner/next action |
| --- | --- | --- | --- |
| 2026-10-18 | Decision | The gate binds dense sectors at 0.50 and the rest at parity; serial-work cuts are in scope where the gain is clear; task 68 precedes this task. | Agent: step 1 after task 68 |
| 2026-10-18 | Decision | The window RMS keeps no truncation correction (task 68 closed), so step 1 measures the noise as it is now. | Agent: step 1 after the 22,500² tier |
| 2026-10-20 | Decision | The dense cell is the deep ELAIS-N1 window 3,600 pixels north of the centre, where `master` completes; the central window stops `master` with a PyBDSF defect, drafted for an upstream report. No local field of rising depth fills the ladder between about 3,500 and 23,000 sources, so its middle rungs raise the dense cell's noise with beam-smoothed noise from a fixed seed; only the depth changes. | Agent: step 3 |
| 2026-10-20 | Progress | The ladder's sectors hold 2,469 (LoTSS-DR3), 3,847, 5,686, 9,744 and 14,126 (the dense cell's noise raised 4, 3, 2 and 1.5 times) and 24,780 (the dense cell) sources in `master`'s catalogue, its finder part rising from about 210 s to 1,027 s on four cores; a LOFAR-HD window was dropped, since its mosaic has no reference frequency for Rapthor's inputs. | Agent: step 3 on quiet nights |
| 2026-10-21 | Progress | The ladder at four cores on Rapthor's thread path, one warm-up and two measured runs a finder: every cell fails its limit, each bound within 1.5% of its ratio, every product repeated byte for byte. The LoTSS-DR3 cell's full protocol stopped at the disk watchdog after four measured `master` runs and three of Hebog's, because the container VM kept deleted files allocated; chains now drop the VM's file cache after deleting. | Agent: the dense cell's profile and full protocol |
| 2026-10-21 | Decision | The ladder keeps its screening repetitions, which are far from every limit; only the dense cell runs the full protocol. The core sweep runs Hebog on single-threaded Dask workers, since the thread path's 1.3 busy cores are measured. Increment 1 starts before step 4's checkpoint: the dense cell's stage profile, with threads beside Dask, is its baseline and shows whether the thread path is held by the interpreter lock or by too few tasks a round; the core sweep and the model then set its targets. | Agent: profiles on the night of 21 October, the core sweep on a later quiet night; increment 1's tests |
| 2026-10-22 | Progress | The dense cell's full protocol (one warm-up, five measured) gives 2.26, bounds 2.24 to 2.28, and 2.03 for the complete step, matching the screening. Hebog's stage profiles of the dense cell and the anchor show the thread path held by the interpreter lock, the two background passes as the largest single-worker cost and rounds of 3 to 12 tasks as the tail; the matched ratio on Dask workers waits for the core sweep. | Agent: the core sweep on a quiet night; increment 1 |
| 2026-10-22 | Progress | Increment 1's first changes split tile rounds, and the component-fit and extended-group rounds, until each task slot has two batches, and scan for bright candidates 64 cells a task. On four Dask workers they take 8 to 13% off the dense and sparse 5,000² cells and a 3,000² sector, with products unchanged; the thread path is unchanged. | Agent: the tile core from the budget and the run-settings record |
| 2026-10-22 | Decision | The cluster has up to 12 nodes, NUMA or not, of 96 cores with 747 GB, 192 cores with 747 GB and 192 cores with 1,494 GB, with no local scratch, on Lustre (maintainer); Hebog must run on every node type without per-node settings. | Agent: the model projects every node type |
| 2026-10-23 | Progress | The core sweep on the dense cell, Hebog on single-threaded Dask workers in the matched container, gives finder ratios of 1.03, 1.07 and 1.00 on one, four and six cores (screening repetitions), half the thread path's, with products identical at every worker count. The two-core point was skipped for lack of disk. 0.24.0 carries increment 1's first part. | Agent: the two-core point on a quiet night; step 4 |
| 2026-10-23 | Progress | The model projects 0.24.0 on one cluster node, against `master` on all its cores, to 0.42 on the dense cell, 0.53 at 14,126 sources and 0.50 to 0.78 on the sparse sectors, if `master` uses no more of a node than the four cores its sweep shows and emulation slows both finders alike; 0.75, 1.02 and up to 1.46 if `master` used every core. On a node Hebog's time nears its floor, driver time plus each round's longest task, so at 5,000² extra nodes take only 0.01 to 0.04 off a ratio and the targets are floors: 113 s natively at 14,126 sources and 217 s on the dense cell (55 s and 116 s if `master` used every core), against 128 s and 190 s now. Every limit is within reach of one node. | Human: the checkpoint; agent: increment 1, a sparse sector's core sweep and native profiles of the ladder on a quiet night |
