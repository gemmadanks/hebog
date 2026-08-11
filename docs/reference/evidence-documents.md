# Evidence documents

Benchmark and scientific-validation outputs use the strict versioned models
in `hebog.validation.evidence`. These documents preserve measurements and
provenance without implying that an exploratory run has passed a release gate.

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

## Phase 5 filter-review evidence

A `phase-five-filter-paired-review` document binds the pre-results protocol,
development and regression manifest checksums, source tree, dependency
inventory, and environment. It records every analytic, development, and
regression endpoint by candidate, statistic, and applicable stratum, plus both
directions of each exact or whole-image bootstrapped paired comparison.
Candidate conclusions are derived from their recorded failures; a document
cannot authorize Step 3 unless one candidate passes every absolute and paired
endpoint. The reviewed Step 2B evidence selected neither candidate, so its
separate committed decision contract keeps optimization, qualification, and
Step 3 closed.

## Phase 5 astrometry-development evidence

A `phase-five-astrometry-development` document binds the successor protocol,
base corrective protocol, fresh development manifest, source tree, dependency
inventory, and environment. It records direct group-level median and p95
position endpoints with whole-image cluster-bootstrap bounds; 68% and 95%
Mahalanobis coverage by morphology, SNR, scale, edge, invalid-pixel,
truncation, and estimator disposition; model availability and adequacy; and a
conjunctive candidate decision. The schema recomputes the frozen preference
for the direct estimator unless an eligible model improves overall p95 by at
least 0.02 beam. A rejected development result cannot authorize confirmation,
Step 2C-P, Step 3, optimization, or qualification.

A later `phase-five-astrometry-follow-up-development` document binds the
Step 2C-HR compact/extended position split, the exact corrective-A residual-B3
detection protocol, and a new 80-image development manifest. It records exact
availability plus whole-image-cluster upper confidence bounds for signed-axis
bias and radial p95 repeatability in every applicable astronomical stratum.
Median radial error and error against the former threshold-independent target
remain diagnostic. Even a completely passing document remains `exploratory`,
marks only `eligible-awaiting-human-review`, and cannot authorize the sealed
confirmation or any downstream Phase 5 step.

The checked-in
`phase-5-astrometry-follow-up-development-decision.json` binds the ignored
development evidence by checksum and records its compact technical review.
The decision can retain a completely passing candidate only for named human
scientific review. Its schema keeps confirmation, Step 2C-P, Step 3,
optimization, and qualification false, so a development pass cannot be
mistaken for production selection.

The separate `phase-5-astrometry-follow-up-human-decision.json` records the
named project-owner review. It may authorize exactly one sealed confirmation
without changing the candidate, target, population, bootstrap, or gates. It
does not authorize Step 2C-P or any later phase.

A `phase-five-astrometry-follow-up-confirmation` document is the raw result of
that authorized one-look execution. It binds the human and development
decisions, development evidence, frozen protocols, confirmation manifest,
runner, source tree, dependencies, and environment. Its status remains
`exploratory` and every downstream gate remains false until a separate
technical decision reviews all confirmation endpoints.

The checked-in
`phase-5-astrometry-follow-up-confirmation-decision.json` binds the raw
evidence checksum and reviewed metrics. A passing decision may authorize only
the freeze of a fresh Step 2C-P protocol; external-finder execution remains
false until that prospective protocol is complete and validated.

The checked-in `phase-5-external-comparison.json` is that prospective
pre-results protocol. It binds two fresh seed-disjoint manifests, exact
PyBDSF release/master and Aegean runtimes, finder configurations, like-product
mappings, truth-first matcher rules, metric scopes, margins, resampling,
power, and the one-look failure policy. It keeps execution false until the
three runners and matcher are implemented, tested, and hash-bound by a
separate review.

A `phase-5-external-execution-decision` is the only record that can open those
runners. It binds the frozen protocol, residual-B3 candidate review, committed
implementation revision, complete production-source-tree digest, and the
three isolated entry-point digests. It also freezes the Hebog container and
dependency inventory and the PyBDSF core count; reference container and
dependency identities remain fixed by the prospective protocol. The decision
is valid only before the one-look population opens and keeps Step 3,
optimization, and qualification false. Each raw one-realization `result.json`
then binds that decision and the common `input.json`, preserves a finder
failure rather than dropping the image, and lists every output artifact by
relative path, byte count, and SHA-256.

## Paired scientific-campaign evidence

A scientific-campaign document compares Hebog and every reference on the same
image realization. It declares one candidate first, names every implementation
independently of its package name, and requires one outcome from every
implementation for every seed. A reference failure is retained as a structured
failure rather than dropping the seed or publishing a partial result.

Successful outcomes retain one deterministic row for every matched source,
unmatched truth source, and unmatched candidate. Rows include truth strata,
classification and quality information, flux and position differences,
fitted and deconvolved position-angle differences where reference truth is
eligible, independent catastrophic flags, the governed catastrophic decision,
and all available normalized residuals. Successful implementations must
expose the same truth identifiers. This makes paired non-inferiority analysis
auditable and prevents aggregate pass/fail counts from hiding which sources
changed.

Association rows separately preserve every observable truth group, including
unresolved blends, with its match decision, group strata, separation, and
integrated-flux difference. Group metrics use the raw fitted total; individual
unresolved catalogue rows use Rapthor's documented peak-as-total compatibility
view. This distinction keeps unresolved-group gates scientifically unchanged.

Each isolated environment first writes a
`CampaignImplementationEvidence` shard. A shard binds the complete dataset
record and seed population, shared scientific contracts, paired-comparison
protocol, exact software and execution configuration, elapsed diagnostic time,
and every result or failure. The campaign compiler requires identical shard
provenance and seeds and refuses to infer a missing result.
The directions, practical margins, clustered interval method, failure policy,
and stopping rule come from the separately reviewed
[Phase 4 paired non-inferiority protocol](phase-4-paired-noninferiority.md),
never from an inspected campaign result.
The maintained Hebog runner exercises the complete bounded serial compact path
and converts its pipeline-neutral catalogue directly to comparison rows. The
two PyBDSF environments use the matching reference runner. This keeps candidate
and reference execution isolated while sharing provenance hashing, failure
capture, truth diagnostics, and compilation rules.

Use `hebog.validation.diagnostics.source_pair_diagnostics` to derive these
rows from the independent catalogue comparison report. It deliberately shares
the normalized-residual calculation used by the aggregate uncertainty report,
so per-source and campaign-level statistics cannot silently diverge.

## Phase 4 one-look decision evidence

The final evaluator consumes a compiled campaign, the exact frozen dataset,
the ordered scientific-contract set, the scientific gates, and the reviewed
paired protocol. It verifies every checksum and seed before scoring anything.
It then emits one strict `phase-4-qualification-decision` document containing:

- every signed Hebog-versus-released-PyBDSF endpoint estimate and one-sided
  95% SciPy BCa upper limit;
- a report-only secondary comparison with pinned PyBDSF `master` wherever that
  implementation completed;
- every absolute held-out catalogue, shape, association, unresolved-group,
  catastrophic, and entire-interval uncertainty result;
- the named conjunctions protecting Hebog's stronger scientific results; and
- every failed seed under its reviewed `qualification-fails` or
  `record-and-continue` policy.

Individual-source 95th-percentile tails retain their contractually declared
`report-only` role; unresolved-group tails remain gates. An otherwise
undefined BCa result uses `[point, point]` only when its complete finite
bootstrap distribution is exactly equal to the finite observed point estimate.
A missing required field or every other non-finite result is recorded as
`indeterminate` and fails closed. The signed endpoint estimate remains visible
but is not itself a gate.

Run the evaluator only after all isolated final shards have been compiled:

```console
python scripts/validation/evaluate_phase4_qualification.py \
  --campaign benchmark-results/<campaign>-compiled.json \
  --manifest config/datasets/phase-4-final-qualification.json \
  --dataset-id phase4-final-paired-qualification-512 \
  --scientific-contract config/contracts/phase-4-measurement.json \
  --scientific-contract config/contracts/phase-4-scientific-gates.json \
  --scientific-gates config/contracts/phase-4-scientific-gates.json \
  --comparison-protocol \
    config/contracts/phase-4-paired-noninferiority.json \
  --output benchmark-results/<campaign>-decision.json
```

The command refuses to replace an existing output. Its `exploratory` evidence
status means the machine decision still requires the normal human evidence
review before it is promoted as a release conclusion; it does not permit a
second look or a replacement population.

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
