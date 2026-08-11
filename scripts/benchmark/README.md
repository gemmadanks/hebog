# Benchmark scripts

This directory contains reproducible benchmark entry points for:

- PyBDSF reference runs;
- Hebog using serial, threaded, and Dask executors;
- Rapthor's complete `filter_skymodel` task.

Every result must record the dataset identifier, git revisions, configuration,
Python and dependency versions, worker topology, CPU allocation, wall time,
CPU time, and peak resident memory. Generated results belong in the ignored
`benchmark-results/` directory.

`review_phase5_filters.py` reproduces the completed Phase 5 Step 2B paired
review. It accepts only the frozen development and regression manifests,
verifies their checksums against the pre-results protocol, evaluates both
float64 candidates from identical prepared products, applies the exact and
10,000-resample whole-image rules, and writes typed evidence. It never reads
the qualification manifest:

```console
uv run python scripts/benchmark/review_phase5_filters.py \
  --output benchmark-results/phase-5/filter-paired-review.json
```

The reviewed outcome is `select-neither`; the decision contract keeps Step 3,
candidate-specific optimization, and qualification closed.

`confirm_phase5_astrometry_follow_up.py` is the one-look Step 2C-HR
confirmation runner. It requires the named human decision, verifies the frozen
protocol, base residual-B3 protocol, development decision and ignored evidence,
candidate, and 400-image regression manifest, and refuses to overwrite an
existing result. It emits raw exploratory evidence and cannot authorize
Step 2C-P or a later phase:

```console
uv run python scripts/benchmark/confirm_phase5_astrometry_follow_up.py \
  --output benchmark-results/phase-5/astrometry-follow-up-confirmation.json
```

Run it only after the authorization and runner commits are complete. A result
must receive a separate fail-closed technical decision before external-finder
comparison can begin.

The Step 2C-P external comparison uses
`run_phase5_external_hebog.py`, `run_phase5_external_pybdsf.py`, and
`run_phase5_external_aegean.py`. Each entry point processes one canonical
`input.json` realization, verifies all image/mean/RMS checksums, refuses an
existing output directory, and requires a separately reviewed execution
decision that binds the protocol, candidate review, complete source tree, and
runner hash. The decision also freezes Hebog's container/dependency inventory
and PyBDSF's core count; each external runner checks its protocol-bound
container digest and installed dependency-inventory hash. No such decision is
accepted unless it is the exact checked-in
`config/contracts/phase-5-external-execution-decision.json`. That decision now
records the reconstructed external-reference identities but has the explicit
`awaiting-reconstructed-runtime-approval` status and does not authorize
execution. Their new identities are recorded in
[`containers/phase5/README.md`](containers/phase5/README.md). The one-look
remains unopened. The final Hebog image is rebuilt and identity-bound, so
named renewed approval is the remaining prerequisite before the no-write
preflight.

`run_phase5_external_campaign.py` is that launcher. It first expands the
complete 1,400-input, 7,000-run matrix and inspects all four local image tags
against their approved digests without pulling. `--preflight-only` performs no
writes and must pass before the terminal run:

```console
uv run python scripts/benchmark/run_phase5_external_campaign.py \
  --hebog-image localhost/hebog:phase5-external-303a49d-reconstructed-final \
  --released-pybdsf-image localhost/rapthor-dev:ci-aligned-reconstructed \
  --master-pybdsf-image localhost/hebog-pybdsf-master:c70103be3-reconstructed \
  --aegean-image localhost/hebog-aegean:2.3.5-step2cp-reconstructed-matched \
  --output benchmark-results/phase-5/external-source-finder-comparison \
  --preflight-only
```

The historical reviewed preflight request is
`182944e174098544092a8e48490bdbfd39f7d9e332a9beb586b1db2441522ef7`.
That command now fails closed because the checked-in decision explicitly
withholds execution authorization. Do not run it until the rebound identities
have received named approval, and do not omit `--preflight-only` until that
preflight passes.
Once renewed authorization exists, the launcher executes inspected immutable
image IDs, not mutable tags, with networking disabled and publishes only after
all legs are terminal and verified. If infrastructure interrupts the private
campaign, rerun the newly approved exact command with `--resume`; changing any
request, runtime, source, runner, or launcher identity fails closed. Do not
inspect the hidden staging path.

Successful runs atomically publish a raw `result.json` plus checksummed finder
products. PyBDSF retains separate Gaussian-component and source catalogues,
its binary island mask, and island-identity label plane; Aegean retains
component and island catalogues plus the explicitly non-segmentation
three-sigma ellipse proxy; Hebog retains the qualified compact catalogue and
residual-B3 detected-segment catalogue, mask, and labels. A finder exception is
a typed failure result with no partial artifacts, so the image remains in the
frozen denominator. The 512-pixel PyBDSF same-map diagnostic is rejected
because PyBDSF would ignore the supplied maps under its RMS-box guard; primary
operational runs are unchanged.

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

`run_phase4_matrix.py` measures the incremental Phase 4 compact-catalogue
component after a Phase 3 detection result has been prepared. The frozen
protocol in `config/benchmarks/phase-4-performance.json` covers 256, 512,
1,024, and 3,000 pixels across sparse, normal, dense, blend-heavy, and
deliberately unfit fields. It times measurement/fitting, bounded catalogue
reduction, and Rapthor FITS materialisation separately, with one warm-up and
five measured repetitions:

```console
uv run python scripts/benchmark/run_phase4_matrix.py \
  --output-directory benchmark-results/phase-4/matrix
```

The 3,000-square component gate uses a reused four-worker, process-isolated
Dask client and 1,000-square tiles. Small tiers use the serial reference to
avoid scheduler overhead. Its performance-only noise has the declared
restoring-beam correlation, so it exercises the same qualified correlated-
noise fitter rather than an inconsistent independent-pixel field. Deliberately
unfit islands must be recorded as omissions and close without publishing a
partial catalogue. Phase 3 preparation time is retained as context but
excluded from the incremental Phase 4 budgets. Peak RSS is the sampled
aggregate of the driver process tree; exact retained processor-array bytes
independently establish the worker-local bounded-work invariant. This matrix
establishes Hebog's component curve; existing PyBDSF figures cover Rapthor's
complete filter step and therefore cannot support a matched speedup claim for
this narrower boundary.

## Phase 4 paired scientific campaigns

`run_phase4_hebog_campaign.py` is the maintained candidate runner and
`run_phase4_pybdsf_campaign.py` is the matching reference runner. Run the
reference once in the isolated released-PyBDSF environment and once in the
pinned `master` environment. All runners regenerate every image from the
complete governed dataset record as float64 and emit a strict
`CampaignImplementationEvidence` shard. Development datasets may be used for
viewable ablations, regression datasets for confirmation, and qualification
datasets only after their reviewed one-look protocol permits opening. The
reference applies Rapthor's exact
PyBDSF profile; the candidate freezes every Hebog threshold, bounded-work
limit, tile size, and serial execution policy. The full dataset-record digest
binds the base recipe, every seed, WCS, beam, truth association, and stratum.

The runner catches a failure for one seed, writes its implementation stage,
exception, message, and traceback digest, prints the complete traceback to the
captured run log, and continues. It never drops the seed or publishes partial
source rows. Existing evidence is not overwritten. Its wall time is diagnostic
provenance only and must not be used for a performance claim.

Campaign images are scientifically independent. For a local regression replay,
`--realization-workers N` may therefore process up to `N` images concurrently
while retaining serial execution within each image and writing results in
recipe order. The value is bounded to 1--32, defaults to 1, and is included in
the evidence execution-configuration digest. Size it from available host
memory; it changes campaign throughput, not the frozen image-level algorithm.

Inspect the reviewed protocol and its design-stage power with:

```console
uv run python scripts/validation/calculate_phase4_paired_power.py \
  config/contracts/phase-4-paired-noninferiority.json
```

The checked-in calculation uses planning assumptions verified on independent
paired development/regression evidence. It reports interval-exclusion power
and the rejected point-sign probability separately, plus a conservative
familywise lower bound. For any future qualification, also supply the frozen
dataset so endpoint populations and realization count are checked rather than
trusted from the contract:

```console
uv run python scripts/validation/calculate_phase4_paired_power.py \
  config/contracts/phase-4s-paired-noninferiority.json \
  --dataset-manifest config/datasets/phase-4s-qualification.json \
  --dataset-id phase4s-compact-qualification-512
```

Every binary endpoint in that protocol must declare its manifest population
unit. A count mismatch fails before power is reported. The historical Phase 4
protocol predates those declarations and remains reproducible only as a
marginal design calculation; it is not eligible to freeze another campaign.
The final decision uses the interval plus every absolute and stronger-Hebog
gate, not the point sign.

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

The Phase 4S compact checkpoint uses the same runner with
`phase-4s-qualification.json`, dataset
`phase4s-compact-qualification-512`, and
`phase-4s-paired-noninferiority.json`. Pass the measurement and scientific-gate
contracts exactly as shown above. The runtime checks the Phase 4S protocol
identity, all manifest population counts, marginal power, and the binding 90%
familywise lower-bound target before it generates the first image. Do not use
the historical Phase 4 protocol for this population.

The separately governed Phase 4T confirmation uses
`config/datasets/phase-4t-qualification.json`, dataset
`phase4t-compact-confirmation-512`, protocol
`config/contracts/phase-4t-paired-noninferiority.json`, and the prospective
`config/contracts/phase-4t-scientific-gates.json` as both the scientific-gate
and gate-provenance argument. The preflight additionally binds the explicit
point/clear truth semantics, raw-median report-only policy, the eight
SNR-10-point-source population count, unchanged uncertainty margin, and at
least 90% absolute interval-containment power. Its uncertainty intervals treat
the image/noise realization as the independent cluster: coverage and mean bias
use cluster-sandwich Student-t intervals and dispersion bootstraps whole
realizations. Do not substitute the Phase 4S manifest, protocol, or gate
document.

Phase 4U uses `config/datasets/phase-4u-qualification.json`, dataset
`phase4u-blend-qualification-512`, and
`config/contracts/phase-4u-paired-noninferiority.json`. It deliberately reuses
the unchanged `config/contracts/phase-4t-scientific-gates.json`; do not
substitute the viewed Phase 4T manifest or paired protocol. Its exact frozen
paths and one-look rule are recorded in
`docs/reference/phase-4u-qualification-protocol.md`.

The final population is frozen in
`config/datasets/phase-4-final-qualification.json` as dataset
`phase4-final-paired-qualification-512`. Before running it, replace the example
paths and revisions below with the exact reviewed identities, capture every
container or source-tree digest, and verify that no output shard already
exists. Opening the final population without those identities violates the
one-look protocol. Both runners also fail before recipe iteration if either
scientific contract or the paired protocol lacks its reviewed status.
The maintained one-look evaluator now covers every paired interval, absolute
gate, and campaign-measurable stronger-Hebog envelope, and source diagnostics
retain the position-angle fields required by the shape gates. The approved
exact finite point-mass rule is bound by reviewed protocol SHA-256
`eaa4e30a8d24a299d9f139c89aafc3ea60d424d61ac64f2b3d6fe7178a697dd8`.
Do not open the final population until the exact execution identities and
dependency inventories below are recorded.

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

After compiling all three implementation shards, create the one permitted
decision with:

```console
python scripts/validation/evaluate_phase4_qualification.py \
  --campaign benchmark-results/<campaign>-paired.json \
  --manifest config/datasets/phase-4-final-qualification.json \
  --dataset-id phase4-final-paired-qualification-512 \
  --scientific-contract config/contracts/phase-4-measurement.json \
  --scientific-contract config/contracts/phase-4-scientific-gates.json \
  --scientific-gates config/contracts/phase-4-scientific-gates.json \
  --comparison-protocol \
    config/contracts/phase-4-paired-noninferiority.json \
  --output benchmark-results/<campaign>-decision.json
```

The evaluator refuses to overwrite an existing decision. A secondary
PyBDSF-master failure is retained under `record-and-continue`; a Hebog or
released-PyBDSF failure fails primary qualification without deleting the seed.

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
