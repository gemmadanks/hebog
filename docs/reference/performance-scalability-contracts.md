# Performance and scalability contracts

The machine-readable gates are `config/benchmarks/phase-0-performance.json`
and `config/benchmarks/phase-0-scalability.json`. They stop implementation
and tuning from selecting favourable inputs or hardware. Both have
`frozen-provisional` status: changing a gate needs a reviewed plan decision
and a `LOG.md` entry, and passing the file schema does not claim the gate has
been demonstrated. Matched PyBDSF reference timings are under
`config/baselines/`, and the current position against every gate is on
[progress against goals](progress-against-goals.md).

## Complete performance curve

The ladder is 256, 512, 1,024, 2,048, 3,000, 4,096, 8,000, 8,192, 10,000,
16,384, 30,000, 32,768, 65,536 and 100,000 pixels per side, each with
empty-or-sparse, normal and dense-or-extended workloads. The near-duplicates
keep operational anchors beside powers of two so partition and storage
effects stay visible. When the fastest valid execution plan changes, the
matrix gains the nearest reproducible case below and above the observed
crossover.

Every affected tier compares a candidate with the previous reviewed Hebog
baseline over one warm-up and at least five measured repetitions. A change is
a regression when the lower one-sided 95% bootstrap bound of the new/previous
median ratio exceeds 1.05 without an approved trade-off.

The deployment gate is the single `pybdsf_master` record: the upper one-sided
95% bound of the Hebog/PyBDSF median wall-time ratio must be at most 0.50
against pinned PyBDSF `master` (`c70103b`) on matched complete
`filter_skymodel` runs. Released 1.14.1 is checked once before 1.0.0 and is
not a gate in this file. The
[quick benchmark](../how-to/index.md#run-the-quick-benchmark) reads its
repetition counts and both comparison rules from this file; its `master`
ratio is diagnostic because the environments are not matched.

The warm one-tile framework budgets are 250 ms for configuration, 500 ms for
FITS I/O, 10 ms for partition planning, 5 ms for serial dispatch, 50 ms for
local dispatch and 500 ms for existing-client Dask dispatch. They isolate
framework cost from scientific stage time.

## Representative component budgets

These 3,000-square allocations guide profiling. They are neither a measured
runtime nor a substitute for matched complete `filter_skymodel` evidence.

| Component | Budget |
| --- | ---: |
| FITS input, validation, beam, WCS | 1.5 s |
| True-sky background and RMS | 4.0 s |
| Detection, deblending, durable image products | 3.5 s |
| Compact measurement and fitting | 2.0 s |
| Multiscale processing and merge | 6.0 s |
| Catalogue and filter outputs | 2.0 s |
| Flat-noise branch, when admitted concurrently | 4.0 s |
| Dask scheduling/transfer on critical path | 2.0 s |

The planned true-sky critical path is about 19 seconds, with flat-noise work
hidden only when the resource envelope admits concurrency.

## Extreme-image resource envelope

The 100,000-square case has two logical intensity inputs and three required
image outputs: true-sky RMS, flat-noise RMS and the source-filter mask.
Catalogue and filtered sky-model products are records, not planes. The
planner may admit at most eight live `float32` plane-equivalents across
bounded buffers, and no worker may materialise a full extreme plane.

The provisional production profile is a 512 GiB node with four workers of
eight threads: 64 GiB reserved for the operating system, scheduler and
services, 128 GiB for concurrent pipeline work, and four 80 GiB worker
limits, with normal worker peak memory at most 75% of that limit. Dask
target/spill/pause/terminate fractions are 0.70/0.80/0.90/0.95, spill uses
worker-local NVMe, and normal-run spill stays below 5% of logical input
bytes. Qualification records the actual facility topology and never scales
worker limits past admitted RAM to make a run pass.

Candidate square tile cores are 2,048, 4,096 and 8,192 pixels. A stage halo
stays below a quarter of its core, or the stage selects a larger core or
records a contract change. Batch sizing chooses the largest stage-valid batch
below the pessimistic memory limit, then reduces batch size before the tile
core. Resource choices never alter core ownership or scientific results.

## Controlled node gates

Strong-scaling qualification preserves every result at 1, 10, 50, 100 and
200 nodes, with provisional maximum complete runtimes of 3,600, 600, 180, 120
and 90 seconds, scheduler overhead at most 10% of the critical path and at
most 50,000 tasks in the graph. Occupancy and strong/weak efficiency floors
are recorded per topology in the machine-readable contract. The plan's task
26 amends this to the development-machine tier and a final 1, 2, 5 and
10-node cluster benchmark, keeping the larger node counts as design targets.
Only controlled multi-node evidence in the versioned evidence schema can
demonstrate these gates.

::: hebog.validation.contracts
    options:
      show_symbol_type_toc: true
