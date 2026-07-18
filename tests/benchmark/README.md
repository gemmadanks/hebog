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
