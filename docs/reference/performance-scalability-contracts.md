# Performance and scalability contracts

Phase 0 freezes machine-readable gates in
`config/benchmarks/phase-0-performance.json` and
`config/benchmarks/phase-0-scalability.json`. They prevent later
implementation and tuning from selecting only favourable inputs or hardware.
The files have `frozen-provisional` status: changing a gate requires a reviewed
plan decision and a `LOG.md` entry; passing the file schema does not claim that
the gate has been demonstrated.

The [Phase 0 baseline results](phase-0-baseline-results.md) record the matched
released/master timings and the exploratory warm one-tile measurements. All
six overhead probes passed their provisional budgets. The local-thread and
planning probes remain framework proxies until their Phase 1 implementations
replace them; this preserves the budgets without presenting placeholder code
as production performance.

## Complete performance curve

The initial ladder is 256, 512, 1,024, 2,048, 3,000, 4,096, 8,000, 8,192,
10,000, 16,384, 30,000, 32,768, 65,536, and 100,000 pixels per side. Every
size has empty-or-sparse, normal, and dense-or-extended workloads. The apparent
near-duplicates deliberately retain operational anchors alongside powers of
two, making partition and storage effects visible.

Initial probes cover direct-to-local execution, local-to-Dask execution, and
FITS-to-Zarr ingestion and final FITS materialisation. A probe range is not an
execution threshold. As soon as a fastest valid execution plan changes, the
matrix must gain the nearest reproducible case immediately below and above the
observed crossover.

Every affected tier compares a candidate Hebog run with the previous reviewed
Hebog baseline. One warm-up and at least five measured repetitions are
required. A change is a regression when the lower 95% bootstrap confidence
bound for the new/previous median ratio exceeds 1.05 without an approved
trade-off. The deployment gate is an upper bound of at most 0.50 against
pinned PyBDSF `master` (`c70103b`), with one confirmation against release
1.14.1 before 1.0.0. The machine-readable file still records the former
release (0.50) and `master` (1.00) limits until the benchmark lane amends it,
as scheduled in the
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md).

The warm one-tile framework budgets are 250 ms for configuration, 500 ms for
FITS I/O, 10 ms for partition planning, 5 ms for serial dispatch, 50 ms for
local dispatch, and 500 ms for existing-client Dask dispatch. These isolate
framework costs; scientific stage time is budgeted separately. Controlled
measurements replace exploratory observations without silently relaxing the
budgets.

## Representative component budgets

These retained 3,000-square allocations guide profiling. They are not a
measured current-candidate runtime or a substitute for matched complete
`filter_skymodel` evidence.

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

The planned true-sky critical path is approximately 19 seconds, with flat-noise
work hidden only when the resource envelope admits concurrency. Experimental
standalone releases use the separate [release checklist](release-status.md);
these complete-workflow budgets and confidence gates remain deployment goals.

## Extreme-image resource envelope

The 100,000-square case has two logical intensity inputs and three required
image outputs: true-sky RMS, flat-noise RMS, and the source-filter mask.
Catalogue and filtered sky-model products are records, not image planes. The
planner may admit at most eight live `float32` plane-equivalents across bounded
buffers; no worker may materialise a full extreme plane.

The provisional production profile is a 512 GiB node with four workers and
eight threads per worker. It reserves 64 GiB for the operating system,
scheduler, and services and 128 GiB for concurrent pipeline work, leaving four
80 GiB worker limits. Normal worker peak memory is limited to 75% of that
limit. Dask target/spill/pause/terminate fractions are 0.70/0.80/0.90/0.95,
and spill uses worker-local NVMe. Normal-run spill must remain below 5% of
logical input bytes.

This 512 GiB profile is the representative planning point within the stated
"hundreds of GB" production envelope. Qualification records the actual
facility topology; it must not scale worker limits past admitted RAM merely to
make a run pass.

Candidate square tile cores are 2,048, 4,096, and 8,192 pixels. A stage halo
must remain below one quarter of its core; a stage requiring more must select a
larger core or record a contract change. Batch sizing chooses the largest
stage-valid batch below the pessimistic memory limit, then reduces batch size
before reducing the scientific tile core. Resource choices never alter core
ownership or scientific results.

## Controlled node gates

The strong-scaling qualification preserves every result at 1, 10, 50, 100,
and 200 nodes. Provisional maximum complete runtimes are respectively 3,600,
600, 180, 120, and 90 seconds. Scheduler overhead is at most 10% of critical
path and the graph contains at most 50,000 tasks. Occupancy and strong/weak
efficiency floors are recorded per topology in the machine-readable contract.

These are qualification gates, not evidence that a laptop or portable CI has
run a 100,000-square image. Only controlled multi-node evidence using the
versioned evidence schema can demonstrate them.

::: hebog.validation.contracts
    options:
      show_symbol_type_toc: true
