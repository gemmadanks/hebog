# Development workflows

## Choose the appropriate test lane

```console
just test-unit
just test-integration
just test-equivalence
just test-benchmark
```

Unit tests must be deterministic and require no scheduler or downloaded data.
Integration tests cover Dask, FITS, and Rapthor boundaries. Equivalence tests
compare with frozen PyBDSF products, while benchmark tests require controlled
resources and are never implied by the quick suite.

## Record a benchmark

Benchmark runs must record the dataset identifier and checksum, Hebog,
PyBDSF, and Rapthor revisions, dependency versions, configuration, worker
topology, CPU allocation, wall and CPU time, peak resident memory, and Dask
task/transfer/spill metrics.

Use one warm-up and at least five measured repetitions. Store generated
results under the ignored `benchmark-results/` directory and commit only small
reviewed summaries with reproduction commands.

## Work with notebooks

Marimo provides reviewable, Python-based demonstrations. Edit the source-finder
notebook with:

```console
uv run marimo edit notebooks/source_finder_demo.py
```

Validate all notebooks without starting the interactive editor:

```console
just marimo-check
```
