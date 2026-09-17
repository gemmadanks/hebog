# Evidence documents

Benchmark and scientific-validation outputs use the strict versioned models
in `hebog.validation.evidence`. These documents preserve measurements and
provenance without implying that an exploratory run has passed a release gate.
`hebog.validation` is repository tooling and is not installed from the Hebog
wheel; use it from a source checkout after `uv sync --all-groups`.

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

## Source-pair diagnostics

Use `hebog.validation.diagnostics.source_pair_diagnostics` to derive one
deterministic row for every matched source, unmatched truth source and
unmatched candidate from an independent catalogue comparison report. Rows
include truth strata, flux and position differences, catastrophic flags and
normalized residuals. The function shares the normalized-residual calculation
used by the aggregate uncertainty report, so per-source and aggregate
statistics cannot silently diverge.

## Closed campaign evidence

The Phase 4 paired-campaign, Phase 4 one-look decision, Phase 5 filter-review,
corrective-review and astrometry evidence schemas were removed with the closed
campaign tooling. `load_evidence` accepts only benchmark and
scientific-comparison documents. Read the historical schemas and their
documentation at [`v0.7.0`](https://github.com/gemmadanks/hebog/blob/v0.7.0/docs/reference/evidence-documents.md).

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
update the integer version and current contract tests. Before `1.0`, old
evidence schemas do not require migration support unless the user explicitly
requests it.

## Phase 0 records

`config/baselines/` contains reviewed compact and representative benchmark
documents for released PyBDSF and pinned master. The reference-product manifest
binds all seven compact products, and the master-versus-release scientific
document records exact compact catalogue, RMS, and mask agreement. The
`phase-0-reference-environments.json` record retains sanitized installed
package inventories, raw inventory hashes, exact runner/compiler hashes,
verified source checkouts, and the explicit `5.0/3.0` profile. The exploratory
one-tile overhead record uses the separate strict model in
`hebog.validation.overhead`.

The [baseline results](phase-0-baseline-results.md) summarize the observations,
limitations, and reproduction workflow. Raw logs and repeated products remain
ignored; the committed records are complete typed evidence rather than copied
console summaries.

::: hebog.validation.evidence
    options:
      show_symbol_type_toc: true

::: hebog.validation.diagnostics
    options:
      show_symbol_type_toc: true

::: hebog.validation.overhead
    options:
      show_symbol_type_toc: true
