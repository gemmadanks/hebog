# Hebog

Hebog is a Dask-aware radio-continuum source finder for SKA Science Data
Processor pipelines. It is being developed first as a faster, scientifically
compatible replacement for the PyBDSF work performed by Rapthor's
`filter_skymodel` task.

Rapthor defines the first qualified feature set, but is not a dependency of
the scientific core. Hebog's public API, domain records, and executor boundary
are designed for reuse in other data pipelines and science workflows.

Its scope is deliberately limited to the behaviour and products Rapthor consumes,
with a target of reducing the complete filter step's matched median wall time
by at least 50% relative to released PyBDSF and also outperforming a pinned
PyBDSF `master` reference.

The 50% reduction is a minimum release gate, not an optimization endpoint.
Hebog treats small, current, large, and extreme images as first-class
performance regimes on a logarithmic benchmark matrix from 256 to 100,000
pixels per side.

Scalability is a core requirement. Hebog's target architecture processes
images up to 100,000 by 100,000 pixels as bounded haloed tiles and distributes
them across 100 to several hundred nodes on an existing Dask cluster, without
materialising a complete plane on any worker.
Production nodes are expected to provide hundreds of GB of RAM, which the
executor can use for larger bounded batches and caches without changing
scientific partition ownership.

## Current status

The compact single-scale Phase 4 milestone is complete. FITS/WCS ingestion,
bounded partitioning, adaptive background and RMS estimation, detection,
deblending, Gaussian measurement, sky/beam transforms, compact catalogue
construction, serial/Dask execution, and Zarr products are implemented and
tested.

The fresh 800-image Phase 4U qualification passed all 77 binding absolute
gates, all 20 paired non-inferiority endpoints against each of released
PyBDSF and pinned PyBDSF `master`, and all five stronger-Hebog envelopes. A
complete optimized-candidate replay preserved that result, and the controlled
incremental compact matrix passed its component budgets. Earlier failed
campaigns remain immutable historical evidence rather than being rescored.

Phase 5 is active, not complete. Its untouched final qualification passed all
143 Continuum absolute gates, all 226 powered Continuum comparisons against
the two PyBDSF references, and both separately bound compact decisions. The
1,688-image campaign completed all 8,440 runs without a failure. The first
public/challenge decision is an immutable failure; its scientific review led
to a prospectively implemented correction. That correction preserves compact
science but fails the complete Continuum cumulative replay with 44 failed
endpoints and 37 like-semantics regressions. The evidence points to catalogue
fragmentation: completeness and merge gates pass, while reliability, duplicate,
split, flux-tail, and position-tail gates fail. The source-association repair
completed its 2,400 candidate products, but a stale single-support compiler
adapter stopped before the cumulative ledger. An evaluation-only repair must
verify and compile those preserved products under a new exact approval; no
candidate rerun is required. The repaired candidate must then pass fresh
held-out qualification. Remaining Phase 5 gates include the
restricted Rapthor workflow profile, the fail-closed
[readiness record](reference/phase-5-release-readiness.md), and independent
scientific and engineering acceptance. The stable public pipeline, matched
complete Rapthor runtime evidence, and production-scale distributed
qualification are later delivery gates. Hebog is therefore not yet a
production-ready or default Rapthor backend.

Start with the [quick start](tutorials/index.md), read the
[architecture](explanation/index.md) and
[quality attributes](explanation/quality-attributes.md), review the
[native-code assessment](explanation/native-code-assessment.md), then see the
[Phase 0 baseline results](reference/phase-0-baseline-results.md), the
[Phase 4 release-readiness record](reference/phase-4-release-readiness.md), the
[Phase 4U qualification result](reference/phase-4u-qualification-protocol.md),
the complete
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
and [execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md).
