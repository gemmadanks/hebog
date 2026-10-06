# Evidence documents

Benchmark and scientific-validation outputs use the strict versioned models
in `hebog.validation.evidence`, so measurements keep their provenance without
implying that an exploratory run passed a gate. `hebog.validation` is
repository tooling, not installed from the wheel; use it from a source
checkout after `uv sync --all-groups`.

Every document has `schema_version` (currently `1`) and a discriminating
`evidence_type`; a stable run identifier and timezone-aware timestamp;
`exploratory` or `reviewed` status; the dataset identifier, role, content
checksum, `(y, x)` shape and workload class; the exact configuration
checksum; and strict fields that reject unknown data.

## Benchmark evidence

A benchmark document identifies the measured implementation by version
and/or 40-character commit, container image digest where available and a
checksum of the complete installed dependency inventory, with related
Rapthor, LSMTool, Hebog or PyBDSF identities recorded separately; the
environment has its own checksum so runs are never compared on display
versions alone. Each repetition distinguishes warm-up from measured work and
records wall and CPU seconds, peak resident memory, array-copy count and
bytes, Dask task count, and transfer and spill bytes. Wall time, CPU time and
peak RSS are required; optional instrumentation uses `null` only with a
reason in `unavailable_metrics`, and zero always means a measured zero. A
reviewed benchmark has at least one warm-up and five measured repetitions.

Resource records hold the executor kind, node/worker/thread topology,
allocated cores, node memory, worker limits, reserved headroom and a
storage identifier; aggregate worker limits must fit inside node memory after
headroom. Reviewed multi-node evidence adds plane count, tile core and
maximum halo, partition and graph task counts, scheduler overhead, worker
occupancy, storage throughput, retries, stragglers and strong- and
weak-scaling efficiency; separate documents per node count form the
controlled scalability curve.

## Scientific-comparison evidence

A scientific document identifies candidate and reference software separately
and records a SHA-256 digest of each side's canonical product manifest plus
the beam and match gate the comparison oracle used, so the report is bound to
the exact catalogue, RMS and mask artifacts rather than to the input dataset
alone. It embeds the complete product reports. Released PyBDSF and pinned
`master` therefore produce separate documents even on the same dataset and
candidate output.

## Writing and loading evidence

```python
from pathlib import Path

from hebog.validation.evidence import load_evidence, write_evidence

write_evidence(Path("benchmark-results/run.json"), evidence)
reloaded = load_evidence(Path("benchmark-results/run.json"))
```

The writer sorts keys, rejects non-finite values, appends a final newline and
replaces the destination only after writing a temporary file.
`load_evidence` accepts benchmark and scientific-comparison documents only.
Raw evidence stays under the ignored `benchmark-results/` directory or
controlled external storage; commit only compact reviewed summaries and
reproduction metadata. The models expose `model_json_schema()`, and a
breaking change bumps the integer version without migration support before
1.0 (ADR-006).

## Reference baselines

`config/baselines/` holds the reviewed compact and representative benchmark
documents for released PyBDSF and pinned `master`, the reference-product
manifest that binds the frozen PyBDSF products, the master-versus-release
scientific comparison, the one-tile overhead record (the strict model in
`hebog.validation.overhead`) and three inventories without a model:
`phase-0-reference-environments.json` (sanitized package inventories, runner
and compiler hashes, verified checkouts and the explicit `5.0/3.0` profile),
`phase-0-representative-dataset.json` and `phase-0-starting-revisions.json`.
A unit test loads every typed record through its model and requires the
directory to contain nothing else. The master-versus-release comparison is
written by `scripts/validation/compare_reference_products.py`, which the
equivalence lane reruns against the committed record, so a change to the
comparison oracle that moves it fails there.

::: hebog.validation.evidence
    options:
      show_symbol_type_toc: true

::: hebog.validation.overhead
    options:
      show_symbol_type_toc: true
