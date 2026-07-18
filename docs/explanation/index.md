# Architecture

The [domain model](domain-model.md) maps Hebog's system boundary, processing
flow, product ownership, and shared language. The
[Rapthor source-finding contract](../reference/rapthor-source-finding-contract.md)
records the current compatibility evidence behind this target architecture.

Hebog separates scientific algorithms from execution policy. Algorithms
operate on NumPy arrays and immutable configuration; an executor decides
whether coarse batches run serially, in local threads, or on Dask workers.

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

The [implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines the target modules, scientific gates, performance budget, delivery
phases, risks, and cutover criteria.
