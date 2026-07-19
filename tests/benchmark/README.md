# Controlled benchmark tests

This directory contains performance and scalability tests that do not run in
portable CI.

- Mark controlled component and end-to-end timing tests with `benchmark`.
- Mark large-image or multi-node tests with both `benchmark` and
  `scalability`; add `slow` and `requires_data` when applicable.
- `just test-benchmark` excludes scalability qualification.
- `just test-scalability` selects the dedicated scalability lane.

Scalability evidence must include image and plane sizes, storage layout, tile
cores and halos, partition count, graph size, node and worker topology,
scheduler load, node/worker RAM, admitted memory, headroom, occupancy,
transfer, spill, storage throughput, retries, stragglers, and
strong/weak-scaling efficiency. Generated data and raw benchmark output remain
outside Git; commit only reviewed summaries and reproduction metadata.

Write every run through `hebog.validation.evidence.BenchmarkEvidence`. The
schema distinguishes exploratory and reviewed evidence, requires exact
software/environment/dataset checksums, and records unavailable instrumentation
with a reason instead of a fabricated zero. Reviewed runs require one warm-up
and at least five measured repetitions; reviewed multi-node runs also require
the complete topology and scaling record.

Performance-regression evidence uses the complete checked-in 256-to-100,000
matrix, plus cases bracketing measured execution crossovers.
Record empty or sparse, normal, and dense or extended workloads, and compare
every tier with the previous reviewed Hebog baseline. The 50% PyBDSF gate is a
minimum release floor, not a reason to stop optimizing or accept a regression
at another supported size.
