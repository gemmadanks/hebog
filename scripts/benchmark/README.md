# Benchmark scripts

This directory contains reproducible benchmark entry points for:

- PyBDSF reference runs;
- Hebog using serial, threaded, and Dask executors;
- Rapthor's complete `filter_skymodel` task.

Every result must record the dataset identifier, git revisions, configuration,
Python and dependency versions, worker topology, CPU allocation, wall time,
CPU time, and peak resident memory. Generated results belong in the ignored
`benchmark-results/` directory.

`run_phase0_pybdsf_baseline.py` starts a fresh local Podman container for every
warm-up or measured repetition. Release 1.14.1 uses the PyBDSF already present
in the immutable container. The master campaign installs a separately built
wheel for commit `c70103be3ae9ae9908286f144e6ce956acc0ce5c` into an ephemeral
target directory, preserving every other container dependency.

Build the pinned platform wheel first with
`build_pybdsf_master_wheel.py`. It requires the expected output SHA-256,
rejects a dirty or incorrect checkout, pins the four build helpers, and fails
if the platform artifact differs from the frozen identity. Dependency download
is the only network-requiring step; baseline runs themselves use local inputs
and the built image.

`pybdsf_reference_run.py` executes the current pinned Rapthor/LSMTool
compatibility path. It records complete wall/CPU/RSS metrics and instruments
the true-sky and flat-noise PyBDSF calls separately. Parent RSS sampling plus
`RUSAGE_SELF`/`RUSAGE_CHILDREN` captures the largest process, not aggregate
concurrent child RSS; the raw result states this limitation. PyBDSF has no
array-copy counter, and these external-process runs do not use Dask, so those
facts are explicit rather than fabricated as measured zeroes.

The driver requires explicit detection and island thresholds and clean
checkouts at the pinned Rapthor and LSMTool commits. Both checkouts are mounted
read-only and precede image-installed code. The runner verifies the imported
PyBDSF version and LSMTool module hash, the master wheel, and the exact script
hashes. This prevents a container's stale preinstalled compatibility code from
being labelled with a newer declared revision.

Materialise the compact frozen input with:

```console
uv run python scripts/validation/materialize_dataset.py \
  config/datasets/phase-0-regression.json \
  pybdsf-compact-reference-256 \
  benchmark-results/phase-0/input/reference-256.fits
```

The baseline driver accepts all repository and input paths explicitly; see
`--help` for the release and master commands. Never point it at a mutable
container tag without checking the digest printed into `baseline-index.json`.
It verifies stable scientific products across repetitions. LSMTool sky-model
history timestamps are the only normalized metadata, and the index records
that normalization explicitly. Mutable CASA `table.lock` files are excluded
from Measurement Set identity. `--finalize-existing` revalidates a complete
campaign without rerunning it.

`measure_phase0_overhead.py` measures warm framework overhead with a reused
local thread pool and caller-owned in-process Dask client. It does not include
Dask client startup and labels Phase 0 planning/local results as proxies rather
than production implementations.

Intermediate-storage benchmarks should measure the selected Zarr backend with
the same versioned evidence models: include store type, codecs, chunk geometry,
object count, stored bytes, concurrency, and atomicity guarantees. Compare
configuration changes against the previous reviewed Zarr curve and include
FITS ingestion, final materialisation, Dask overhead, and Rapthor end-to-end
latency where applicable. The exploratory backend-comparison runner was
removed after ADR-007 selected a single backend, so rejected private storage
code does not become a maintained benchmark dependency.

`measure_phase1_io.py` exercises the implemented warm local path from a
deterministic FITS image through aligned Zarr v3 chunks and back to final RMS
and mask FITS products. It requires at least one warm-up and five measured
repetitions, records each repetition with the versioned evidence model, and
uses a platform-safe peak-RSS observation on Windows and POSIX. For example:

```console
uv run python scripts/benchmark/measure_phase1_io.py \
  --size 1024 --tile-size 512 --zarr-concurrency 10 \
  --output benchmark-results/phase-1/io-1024-c10.json
```

The runner records Hebog-controlled row assembly as bounded by one complete
tile row. Allocation counts inside Astropy and Zarr are explicitly unavailable
because those libraries do not expose complete counters; the bounded-copy
contract is established separately by structural integration tests. These
warm `LocalStore` observations do not qualify cold-cache behaviour,
deployment-store atomicity, Dask transfer, or distributed scaling.

`measure_phase2_background.py` measures the implemented coarse-grid and
bounded interpolation stages with a caller-owned, reused local Dask client.
It requires an explicit FITS input and dataset identity, uses one warm-up and
at least five measured repetitions, and writes exploratory
`BenchmarkEvidence`. The runner deliberately excludes client startup and does
not assemble a complete image plane: its peak-RSS observation therefore
matches Hebog's tile-output contract rather than a validation-only full-map
comparison. For the frozen Rapthor geometry and four-core component gate, run
each branch independently:

```console
uv run python scripts/benchmark/measure_phase2_background.py \
  --input /controlled/path/sector-MFS-image-pb.fits \
  --dataset-id rapthor-representative-3000-true-sky \
  --stage true-sky-background --workers 4 \
  --output benchmark-results/phase-2/true-sky-background.json

uv run python scripts/benchmark/measure_phase2_background.py \
  --input /controlled/path/sector-MFS-image.fits \
  --dataset-id rapthor-representative-3000-flat-noise \
  --stage flat-noise-rms --workers 4 \
  --output benchmark-results/phase-2/flat-noise-rms.json
```

The default 64-cell statistic batches and 1500-by-1500 interpolation tiles
are measured execution policy, not scientific geometry. The script records
float64 because Phase 2 equivalence was established with that precision; a
lower-precision kernel remains inadmissible until it passes the same
scientific suite.

`measure_phase3_detection.py` reuses one prepared Phase 2 coarse grid and
measures the complete compact Phase 3 component: automatic adaptive discovery
and refinement, thresholding, connected reconciliation, durable Zarr
publication, and compact deblending. It requires one warm-up and at least five
measurements. The exact governed Rapthor run is:

```console
uv run python scripts/benchmark/measure_phase3_detection.py \
  --input /controlled/path/sector-MFS-image-pb.fits \
  --dataset-id rapthor-representative-3000-phase3 \
  --workload-class normal --executor dask --workers 4 --tile-size 1000 \
  --output benchmark-results/phase-3/representative-3000.json
```

Generate and measure the frozen 256, 512, 1,024, and 3,000 square
sparse/normal/dense compact ladder with:

```console
uv run python scripts/benchmark/run_phase3_matrix.py \
  --output-directory benchmark-results/phase-3/matrix --workers 4
```

The matrix generator creates performance-only FITS inputs with deterministic
noise and bounded Gaussian patches. These inputs measure size and density
scaling; the governed scientific manifests and held-out qualification tests,
not the performance generator, establish scientific correctness.

## Phase 4 paired scientific campaigns

`run_phase4_hebog_campaign.py` is the maintained candidate runner and
`run_phase4_pybdsf_campaign.py` is the matching reference runner. Run the
reference once in the isolated released-PyBDSF environment and once in the
pinned `master` environment. All runners regenerate every image from the
complete governed dataset record as float64 and emit a strict
`CampaignImplementationEvidence` shard. The reference applies Rapthor's exact
PyBDSF profile; the candidate freezes every Hebog threshold, bounded-work
limit, tile size, and serial execution policy. The full dataset-record digest
binds the base recipe, every seed, WCS, beam, truth association, and stratum.

The runner catches a failure for one seed, writes its implementation stage,
exception, message, and traceback digest, prints the complete traceback to the
captured run log, and continues. It never drops the seed or publishes partial
source rows. Existing evidence is not overwritten. Its wall time is diagnostic
provenance only and must not be used for a performance claim.

Before review, inspect the draft protocol and its design-stage power with:

```console
uv run python scripts/validation/calculate_phase4_paired_power.py \
  config/contracts/phase-4-paired-noninferiority.json
```

This calculation must be repeated after its variance assumptions have been
verified on independent paired development/regression evidence. It reports
interval-exclusion power separately from the stricter no-worse point-estimate
condition. Do not change the protocol status or create final qualification
seeds from the provisional calculation alone.

Generate a regression candidate shard from a clean reviewed Hebog revision
with:

```console
python scripts/benchmark/run_phase4_hebog_campaign.py \
  --manifest config/datasets/phase-4-paired-regression.json \
  --dataset-id phase4-paired-power-regression-512 \
  --scientific-gates config/contracts/phase-4-scientific-gates.json \
  --scientific-contract config/contracts/phase-4-measurement.json \
  --scientific-contract config/contracts/phase-4-scientific-gates.json \
  --comparison-protocol config/contracts/phase-4-paired-noninferiority.json \
  --expected-version <installed-hebog-version> \
  --hebog-commit <40-hex-reviewed-commit> \
  --run-id <campaign>-hebog \
  --output benchmark-results/<campaign>-hebog.json
```

Use `--source-tree-sha256` when the run intentionally includes reviewed local
changes not represented by the commit, and `--container-image-digest` on a
controlled container runner. Both candidate and reference runners accept
regression data for planning-assumption verification. Qualification use
requires the reviewed protocol and frozen final population.

A typical invocation inside an immutable reference environment is:

```console
python scripts/benchmark/run_phase4_pybdsf_campaign.py \
  --manifest <frozen-dataset-manifest.json> \
  --dataset-id <frozen-dataset-id> \
  --scientific-gates config/contracts/phase-4-scientific-gates.json \
  --scientific-contract config/contracts/phase-4-measurement.json \
  --scientific-contract config/contracts/phase-4-scientific-gates.json \
  --comparison-protocol <reviewed-paired-protocol.json> \
  --implementation-id pybdsf-release \
  --expected-version 1.14.1 \
  --pybdsf-commit 1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc \
  --container-image-digest sha256:<64-hex-digest> \
  --run-id <campaign>-pybdsf-release \
  --output benchmark-results/<campaign>-pybdsf-release.json
```

Repeat with implementation `pybdsf-master`, version
`1.14.2.dev40+gc70103be3`, and commit
`c70103be3ae9ae9908286f144e6ce956acc0ce5c`. Use the same manifest,
scientific contracts, paired protocol, four-core allocation, and immutable
base-image policy for both. The dependency-inventory digest and the
implementation-specific execution-configuration digest distinguish the two
isolated shards.

After the final Hebog campaign harness has emitted its candidate shard, compile
the candidate-first triplet without rerunning any implementation:

```console
python scripts/benchmark/compile_phase4_scientific_campaign.py \
  --run-id <campaign>-paired \
  --output benchmark-results/<campaign>-paired.json \
  benchmark-results/<campaign>-hebog.json \
  benchmark-results/<campaign>-pybdsf-release.json \
  benchmark-results/<campaign>-pybdsf-master.json
```

The compiler rejects dataset, seed, scientific-contract, or comparison-protocol
drift. Qualification evidence remains `exploratory` until every input and
scientific decision has received named review.

Before named review, audit the draft design assumptions against the complete
paired regression. This uses whole noise-seed images as bootstrap clusters,
recomputes ratio, quantile, and uncertainty-calibration endpoints on every
resample, and expresses empirical uncertainty on the same per-realization
scale as the power calculation:

```console
python scripts/validation/audit_phase4_paired_assumptions.py \
  --campaign benchmark-results/<campaign>-paired.json \
  --manifest config/datasets/phase-4-paired-regression.json \
  --dataset-id phase4-paired-power-regression-512 \
  --protocol config/contracts/phase-4-paired-noninferiority.json \
  --output benchmark-results/<campaign>-assumption-audit.json
```

Regression evidence may evaluate a revised draft protocol; the audit records
both protocol hashes and makes that difference explicit. Final qualification
must use the exact reviewed protocol hash captured by every implementation
shard and may not use this planning exception.
