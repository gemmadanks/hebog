# Evidence documents

Phase 0 benchmark and scientific-comparison outputs use the strict versioned
models in `hebog.validation.evidence`. These documents preserve measurements
and provenance without implying that an exploratory run has passed a release
gate.

Every document contains:

- `schema_version`, currently `1`, and a discriminating `evidence_type`;
- a stable run identifier and timezone-aware capture timestamp;
- `exploratory` or `reviewed` status;
- dataset identifier, role, content checksum, `(y, x)` shape, and workload
  class;
- exact configuration checksum; and
- strict fields that reject unknown data rather than silently ignoring it.

## Benchmark evidence

A benchmark document identifies the measured implementation by version and/or
40-character commit, container image digest where available, and a checksum of
the complete installed dependency inventory. Related Rapthor, LSMTool, Hebog,
or PyBDSF identities are recorded separately. The environment also has its own
checksum so runs cannot be compared merely because their display versions
look similar.

Each repetition distinguishes warm-up from measured work and contains complete
run metrics plus uniquely named stage metrics:

- wall and CPU seconds;
- peak resident memory;
- array-copy count and bytes;
- Dask task count;
- transfer and spill bytes.

Wall time, CPU time, and peak RSS are required. Optional instrumentation uses
`null` only with a non-empty reason in `unavailable_metrics`; zero always means
a measured or applicable zero. A reviewed benchmark requires at least one
warm-up and five measured repetitions. Exploratory evidence can contain fewer
runs but cannot be presented as a release result.

Resource records include executor kind, node/worker/thread topology, allocated
cores, physical node memory, worker memory limits, reserved per-node headroom,
and an environment-neutral storage identifier. Aggregate worker limits must
fit inside node memory after headroom.

Reviewed multi-node evidence additionally requires logical plane count, tile
core and maximum halo geometry, partition and graph task counts, scheduler
overhead, worker occupancy, storage throughput, retries, stragglers, and
strong- and weak-scaling efficiency. Separate evidence documents at 1, 10, 50,
100, and 200-plus nodes form the controlled scalability curve.

## Scientific-comparison evidence

A scientific document identifies candidate and reference software separately
and records a SHA-256 digest for each side's canonical product manifest, plus
the beam and match gate used by the independent comparison oracle. The product
manifest digest binds the report to the exact catalogue, true-sky RMS,
flat-noise RMS, and mask artifacts rather than only their input dataset. The
document embeds the complete reports for those products. Released PyBDSF and
pinned PyBDSF `master` therefore produce separate documents even when they use
the same dataset and candidate output.

## Writing and loading evidence

Use the validated atomic writer rather than assembling JSON dictionaries:

```python
from pathlib import Path

from hebog.validation.evidence import load_evidence, write_evidence

write_evidence(Path("benchmark-results/run.json"), evidence)
reloaded = load_evidence(Path("benchmark-results/run.json"))
```

The writer sorts keys, rejects non-finite JSON values, appends a final newline,
and replaces the destination only after writing a temporary file. Raw evidence
stays under the ignored `benchmark-results/` directory or controlled external
storage. Commit only compact reviewed summaries and reproduction metadata.

The Python models expose `model_json_schema()` when a runner or validation
service needs JSON Schema. Schema changes follow ADR 006: breaking semantics
require a new integer version, migration guidance, and contract tests.

## Phase 0 records

`config/baselines/` contains reviewed compact and representative benchmark
documents for released PyBDSF and pinned master. The reference-product manifest
binds all seven compact products, and the master-versus-release scientific
document records exact catalogue, RMS, and mask agreement. The exploratory
one-tile overhead record uses the separate strict model in
`hebog.validation.overhead`.

The [baseline results](phase-0-baseline-results.md) summarize the observations,
limitations, and reproduction workflow. Raw logs and repeated products remain
ignored; the committed records are complete typed evidence rather than copied
console summaries.

::: hebog.validation.evidence
    options:
      show_symbol_type_toc: true

::: hebog.validation.overhead
    options:
      show_symbol_type_toc: true
