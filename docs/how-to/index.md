# Development workflows

## Choose the appropriate test lane

```console
just test-unit
just test-integration
just test-equivalence
just test-acceptance
just test-qualification
just test-benchmark
just test-scalability
```

Unit tests must be deterministic and require no scheduler or downloaded data.
Integration tests cover Dask, FITS, and Rapthor boundaries. Equivalence tests
compare small redistributable cases with frozen PyBDSF products. Acceptance
tests describe Rapthor-facing behaviour. Qualification, benchmark, and
scalability tests require controlled resources or approved data and are never
implied by the quick suite.

## Develop test-first

For a public behaviour or scientific kernel:

1. Write the smallest analytic, property, contract, or regression test and
   confirm that it fails for the intended reason.
2. Implement the simplest deterministic serial behaviour that passes.
3. Refactor, then add pathological and property-based cases.
4. Prove local and Dask conformance against the serial result.
5. Run scientific equivalence before making a performance claim.

Use analytic truth and mathematical invariants before treating PyBDSF as an
oracle. PyBDSF products establish compatibility; they are not assumed to be
scientific ground truth. Qualification datasets are held out from routine TDD
and used only for milestone or release decisions.

## Keep changes maintainable and reusable

Start a vertical slice at the public behaviour, then keep scientific kernels
independent of workflow and scheduler details. Pass I/O, execution, and
configuration explicitly; put Rapthor/LSMTool names and product translations
in the compatibility adapter.

Prefer a function, dataclass, context manager, or narrow structural protocol
to an inheritance hierarchy or generic plugin registry. Add a new extension
seam only when a second implementation or workflow test demonstrates the
variation. Run `just check` while iterating and preserve the branch-aware 80%
coverage floor with meaningful normal, edge, and failure tests.

Use the [quality attributes and coding principles](../explanation/quality-attributes.md)
and [code review guide](https://github.com/gemmadanks/hebog/blob/main/CODE_REVIEW.md)
for the complete requirements.

## Describe acceptance behaviour

Use readable pytest scenarios for behaviour that crosses Hebog, materialised
products, Dask, and Rapthor. Given/When/Then test names or docstrings are
enough initially. A dedicated BDD framework should be introduced only if
domain experts will actively review or write feature files.

## Record a benchmark

Benchmark runs must record the dataset identifier and checksum, Hebog,
Rapthor, released PyBDSF, and PyBDSF `master` revisions, dependency versions,
configuration, worker topology, CPU allocation, wall and CPU time, peak
resident memory, and Dask task/transfer/spill metrics. Run the exact PyBDSF
references in separate matched environments and report both comparisons; do
not substitute `master` for Rapthor's released runtime.

Use one warm-up and at least five measured repetitions. Store generated
results under the ignored `benchmark-results/` directory and commit only small
reviewed summaries with reproduction commands.

Measure the performance curve at 256, 512, 1,024, 3,000, 8,000, 10,000,
30,000, and 100,000 pixels per side, plus cases immediately below and above
each observed executor, storage, partition, or batching crossover. Include
empty or sparse, normal, and dense or extended workloads. Compare every size
with the previous reviewed Hebog baseline and, wherever both references can
run, with released PyBDSF and pinned PyBDSF `master`; never report only the
most favourable size or execution mode.

For a scalability run, additionally record the logical image and plane sizes,
tile cores and stage-specific halos, partition count, storage layout, worker
nodes and processes, node/worker RAM, admitted memory and reserved headroom,
scheduler load, worker occupancy, boundary-summary and transfer volumes,
spill, storage throughput, retries, and stragglers. Report
the full 1/10/50/100/200-plus-node matrix, including strong- and weak-scaling
efficiency; do not retain only the best topology.

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
