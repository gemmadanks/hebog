# Architecture

The [domain model](domain-model.md) maps Hebog's system boundary, processing
flow, product ownership, and shared language. The
[Rapthor source-finding contract](../reference/rapthor-source-finding-contract.md)
records the current compatibility evidence behind this target architecture.

Hebog separates scientific algorithms from execution policy. Algorithms
operate on bounded NumPy tiles with explicit halos and immutable metadata; an
executor decides whether coarse batches run serially, in local threads, or on
Dask workers. A small image is one tile.

```text
FITS input
   -> background and RMS estimation
   -> threshold and multiscale detection
   -> connected components and deblending
   -> source measurement and fitting
   -> catalogue, mask, and RMS products
```

Rapthor owns the top-level Dask graph:

```text
find_true_sky_sources -----------+
                                 +--> apply_skymodel_filter
estimate_flat_noise_rms ---------+
```

The first two operations may run concurrently when their combined memory fits
the configured resource budget. Each emits restartable file products. Large
mutable images, open file handles, and scheduler clients are never public
request or result payloads.

The serial executor is the deterministic scientific reference. Local and Dask
executions must match it before either is compared with PyBDSF. Dask batches
should be coarse enough to amortise scheduling, and common image data should
be read or published once rather than embedded in every task.

The partition and batching planner collapses small work to a one-tile direct
path and introduces partitioning, chunk conversion, or distributed fan-out
only when complete-runtime measurements justify the overhead. Executor,
storage, and batching crossovers are benchmarked on both sides rather than
encoded as permanent image-size thresholds.

Images up to 100,000 by 100,000 pixels use a deterministic partition manifest,
stage-specific halos, bounded tile maps, boundary summaries, and hierarchical
reconciliation. No worker holds a complete large plane. Qualification must
demonstrate partition-invariant results and useful distribution across 100 and
at least 200 worker nodes; Rapthor still owns the supplied cluster and resource
budget.

Production nodes are expected to provide hundreds of GB of RAM. Hebog sizes
bounded batches and caches from admitted worker memory so it can use that
capacity without assuming exclusive access or making results topology
dependent.

The [implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines the target modules, scientific gates, performance budget, delivery
phases, risks, and cutover criteria.
