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

## Refresh public comparison notebook results

The [notebook guide](../../docs/how-to/notebooks.md) is the current source for
input downloads, saved campaign restoration, refresh/resume commands and
troubleshooting. Run from the repository root:

```console
uv run python scripts/benchmark/download_notebook_data.py --list
uv run python scripts/benchmark/prepare_notebook_comparison.py --build-images --dry-run
uv run python scripts/benchmark/prepare_notebook_comparison.py --build-images
uv run python scripts/benchmark/refresh_public_notebook_hebog.py --preflight-only
uv run python scripts/benchmark/refresh_public_notebook_hebog.py --label "Current notebook comparison"
```

`prepare_notebook_comparison.py` creates the same 13-case Hydra/LoTSS/SDC1
comparison as the notebook
using PyBDSF 1.14.1 and AegeanTools 2.3.5. It can build local images from the
existing recipes, or use supplied local image tags; the guide describes the
disk/resource requirements. `--dry-run` performs no builds, container runs,
downloads or output writes. Its outputs work with the notebook and with the
separate Hebog refresh's input/reference/history options. Completed reference
results can be reused with `--resume` without requiring old campaign hashes.

The no-option Hebog refresh commands above select the existing 13-case
SDC1/Hydra/LoTSS comparison. That historical bundle still requires restoration
from the data host or backup if missing. For a fresh setup, use the explicit
paths in the guide; each comparison should have its own Hebog history root.

The runner currently selects
`config/contracts/phase-5-filtered-response-domain-repair-identity-review.json`
(v15 composition, diagnostics schema 8). The refresh retains candidate and
saved-reference integrity checks and does not rerun either external finder.
Ordinary workbench experiments do not need frozen individual run identities.

The notebook's **Diagnose one support component** section ranks another
finder's labelled components by Hebog fragmentation and comparison-only pixel
count. For a selected component it plots the input, Hebog background, Hebog
RMS, direct local significance, disjoint support roles, S/N distributions, and
flux accounting. A comparison-only pixel is a finder disagreement, not truth;
use injected campaigns to decide completeness.

The same diagnostic can be rendered non-interactively. For example, this
compares one released-PyBDSF island with the Hebog products from the same
image:

```console
uv run python scripts/validation/plot_support_component_diagnostic.py \
  --image /path/to/input.fits \
  --background /path/to/hebog/background.fits \
  --rms /path/to/hebog/rms.fits \
  --candidate-labels /path/to/hebog/segment_labels.fits \
  --reference-labels /path/to/pybdsf/island_labels.fits \
  --reference-label 712 \
  --candidate-name Hebog \
  --reference-name released-PyBDSF \
  --output benchmark-results/support-label-712.png \
  --summary-output benchmark-results/support-label-712.json
```

The JSON sidecar records pixel precision, recall, intersection-over-union,
fragmentation, beam-area-normalized flux, direct-S/N quantiles, and local
off-source evidence. Generated plots and records remain under the ignored
`benchmark-results/` tree.

The refresh executes exactly `run_phase5_public_finder_hebog.py`. Scientific
changes available only through another prospective smoke, replay, or sidecar
wrapper are not included unless the standard public runner is deliberately
updated to activate them. These public refreshes remain diagnostic evidence:
they authorize neither qualification nor performance claims.

The diagnostic runner supports ICRS and FK5 equatorial input WCS, including
the FK5 frame inferred from SDC1 `EPOCH` headers. It preserves the original
FITS WCS and transforms the local restoring-beam position angle together with
the coordinates. Its source and Gaussian-component rows are both ICRS,
declared in `catalogue_semantics.coordinate_frame`. Core selection, diagnostic
pixel matching and notebook plotting transform those rows back into the
input frame; native reference catalogues keep their own interpretation.
Changing a header's frame label without transforming coordinates is not a
supported workaround. The public `hebog.find_sources()` preview's ICRS-only
admission rule is unchanged; this diagnostic boundary does not extend its
qualification scope.

Numerical decomposition failure during a joint Gaussian fit does not abort
the whole diagnostic image. All components in that coupled fit are retained
as unavailable measurements with reason `fit-linear-algebra-failure`; no
Gaussian parameters, uncertainties or optimizer diagnostics are invented.
Independent parent islands continue normally. The runner emits one warning
per affected image and retains the exact component IDs in
`measurement_dispositions`. A successfully published bundle is not evidence
that every component was measured or that scientific parity passed. Existing
availability gates continue to count those missing measurements. The solver,
fit bounds and detection thresholds are unchanged.

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

The historical Step 2C-P external comparison used
`run_phase5_external_hebog.py`, `run_phase5_external_pybdsf.py`, and
`run_phase5_external_aegean.py`. Each entry point processes one canonical
`input.json` realization, verifies all image/mean/RMS checksums, refuses an
existing output directory, and requires a separately reviewed execution
decision that binds the protocol, candidate review, complete source tree, and
runner hash. The decision also freezes Hebog's container/dependency inventory
and PyBDSF's core count; each external runner checks its protocol-bound
container digest and installed dependency-inventory hash. No such decision is
accepted unless it is the exact checked-in
`config/contracts/phase-5-external-execution-decision.json`. That decision and
its failed one-look are terminal evidence and must not be reused, rescored, or
rebound. Their exact identities remain in
[`containers/phase5/README.md`](containers/phase5/README.md).

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
It is not transferable to the reconstructed identities. The renewed
zero-write preflight passed with request
`31a56c509a354e497a9902f32d02ef77dc9d90b047c59f28239f423bed372251`,
exactly 1,400 inputs, and 7,000 runs. Both terminal and private campaign paths
remained absent. The launcher executes inspected immutable
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

The Step 2C-PF successor uses the `*_successor_*` launcher, runner wrappers,
compiler, and evaluator. Its protocol binds fresh manifests while reusing the
unchanged terminal campaign mechanics and gates. The only scientific compiler
replacement is the reviewed mask-only continuum boundary. The checked-in
execution decision is deliberately pending, so even `--preflight-only` fails
before container inspection until named approval is recorded and the dependent
hash chain is refreshed. After that approval, the required first action is:

```console
uv run python scripts/benchmark/run_phase5_external_successor_campaign.py \
  --hebog-image localhost/hebog:phase5-external-successor-c1f7eb0 \
  --released-pybdsf-image localhost/rapthor-dev:ci-aligned-reconstructed \
  --master-pybdsf-image localhost/hebog-pybdsf-master:c70103be3-reconstructed \
  --aegean-image localhost/hebog-aegean:2.3.5-step2cp-reconstructed-matched \
  --output benchmark-results/phase-5/external-successor-comparison \
  --preflight-only
```

Do not substitute the terminal campaign, manifests, decision, registry, or
evaluator, and do not inspect or pool the closed campaign as successor
evidence.

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

## Phase 5 incremental multiscale matrix

`run_phase5_matrix.py` measures the complete incremental Phase 5 stage after
the Phase 2 background and RMS generation has been prepared. The frozen
protocol in `config/benchmarks/phase-5-performance.json` covers 256, 512,
1,024, and 3,000 pixels with sparse, normal, and extended morphology. Each
cell performs one warm-up and five measured repetitions of both multiscale
passes, global topology reconciliation, and atomic Zarr publication:

```console
uv run python scripts/benchmark/run_phase5_matrix.py \
  --output-directory benchmark-results/phase-5/incremental-multiscale
```

The primary policy uses the serial reference through 1,024 pixels and the
existing four-worker, one-thread-per-worker Dask client at 3,000 pixels. Both
executors are also measured at 1,024 and 3,000 pixels for every workload, so a
crossover is observed rather than inferred from a kernel timer. The
3,000-square primary medians must each remain within the frozen 6.0-second
multiscale budget.

The generated FITS fields use deterministic beam-correlated noise and bounded
compact or extended source patches. Their hashes, workload classes, complete
runtime environment, source tree, resource allocation, task count, aggregate
process-tree RSS, retained arrays, workspaces, summaries, partitions, and
published shards are recorded in typed evidence. Phase 2 setup time is
retained as context but excluded from the incremental gate. The reviewed
five-pixel benchmark beam has an exact 34-pixel filter halo, so a 256-pixel
core satisfies the halo-admission rule and keeps the smallest image to one
tile. A 12-tile task bound balances the 144 partitions into 12 tasks per pass
at the 3,000-square anchor, avoiding an under-filled final four-core wave.

This is a component budget and initial reviewed Hebog curve, not a complete
Rapthor or PyBDSF speedup claim. Later candidates must compare affected and
adjacent cells against the retained curve before the performance policy can
change.

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

When a complete compiled campaign cannot fit as one validated Pydantic object,
use `scripts/validation/evaluate_phase4_bounded_shards.py`. Supply the compiled
campaign and its file SHA-256, then the candidate, released-PyBDSF, and
pinned-master shards in that order with their exact file SHA-256 values. The
script validates and reduces each shard in a separate process, releases its
large object graph, and applies the same paired BCa, absolute-gate, and
stronger-Hebog decision functions to the bounded numerical summaries. It
refuses changed hashes and an existing output; this is a memory-bounded
evaluation of the same fixed evidence, not permission to rerun or rescore a
campaign.

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

## Source-catalogue repair cumulative replay (R6)

The R6 tools under `scripts/validation/source_catalogue_*.py` retain native
measurements independently of the final evaluator. They do not reuse the old
candidate's scientific pass. `source_catalogue_replay_plan.build_replay_plan`
constructs a non-executable plan from the reviewed candidate, original
population, sealed native reference files, historical incumbent checkout,
explicit disk/time admission and new absent scratch/output paths. Commit the
tooling first and bind its immutable execution checkout; do not freeze an
uncommitted source tree. Record the exact plan and separate one-use
authorization hashes before execution.

From that immutable checkout, with its `src` and repository root on
`PYTHONPATH`, use the main checkout's pinned environment:

```console
python -m scripts.validation.run_source_catalogue_cumulative_replay \
  --plan /absolute/path/to/frozen-plan.json \
  --plan-sha256 <exact-file-sha256> \
  --preflight-only
```

The complete preflight reads all 2,400 input bundles and 9,600 retained
reference runs, validates native success and artifact identities, probes
historical imports without executing a finder, and refuses consumed output
paths. Execution uses the same command without `--preflight-only`, adding
`--authorization /absolute/path/to/one-use-decision.json` and its
`--authorization-sha256`. Set `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`MKL_NUM_THREADS` and `NUMBA_NUM_THREADS` to `1`; the command owns exactly two
spawned workers and supplies an existing two-worker Dask client to the library.

Stages are capture, existing-Dask comparison, per-image truth evaluation and
final aggregation. Per-pair records, a capture seal, Dask comparison records
and an evaluation seal precede the atomic terminal. Completed products are
never overwritten or deleted after failure; pending work is cancelled.
There is no automatic retry or resume switch. Any process repair must bind
a new exact execution identity and reuse verified complete products through
a separately reviewed completion path. A scientific failure is terminal,
not permission to tune or rescore its data.

While a run is active, inspect only process health, completion counts in
`progress.log`, free disk space and terminal existence. After it ends, verify
all provenance and interpret compact science followed by Continuum, with
each finder measured independently against analytic truth. All original
binding comparisons and safety checks must pass; an earlier uncertainty
waiver does not transfer. Native background diagnostics unavailable in old
reference products remain unavailable. Retained current background errors
are in Jy/beam and relative RMS errors are fractional, not both in sigma.

### Read-only continuation inventory

After the original process has stopped, first verify which retained records
can be reused. This command cannot run a finder, create a Dask cluster,
evaluate missing inputs or produce a scientific verdict:

```console
python -m scripts.validation.audit_source_catalogue_continuation \
  --plan /absolute/path/to/original-plan.json \
  --plan-sha256 <original-plan-file-sha256> \
  --original-review /absolute/path/to/original-identity-review.json \
  --original-review-sha256 <original-review-file-sha256> \
  --repair-review /absolute/path/to/unavailable-support-identity-review.json \
  --repair-review-sha256 <repair-review-file-sha256>
```

The default is no-write. An optional `--inventory` path atomically retains
the audit in a separate, absent evidence file, never in either immutable
checkout, the original scratch, or the scientific terminal path. The inventory
is non-executable and does not renew the consumed original authority.

The audit hashes both capture sets and every native artifact, verifies the
original candidate separately from the amended evaluator, and recomputes only
the saved Serial/Dask *identity hashes*, not finder outputs or truth scores.
Completed per-image records retain their original bytes and schema: corrupt
markers, changed captures, duplicate/missing finders and mismatched nested
diagnostics fail closed. The already-reviewed positive-support records need
no schema migration. Partial directories, including empty failed directories,
are recorded for preservation, not admitted as completed work. The frozen
marker-set digest prevents new or missing records from silently changing the
reusable population.

A later continuation still needs its own frozen code, exact identity and
decision, new evaluation directory, complete no-write launch preflight and
synthetic resume/late-aggregation tests. It must reuse these records without
rescoring, evaluate only missing inputs, seal the combined evidence before
the unchanged statistical engine, and preserve any terminal scientific
failure. Do not restart the original replay command to resume evaluation.

### Evaluation-only continuation

The separate `source_catalogue_continuation_plan` command freezes the audited
inventory into a non-executable plan. Run it from a clean immutable checkout
of the committed tooling, using that checkout's `src` and repository root on
`PYTHONPATH` and the original pinned environment. Set the four single-thread
kernel variables listed above for preflight and execution.

```console
python -m scripts.validation.source_catalogue_continuation_plan \
  --inventory /absolute/path/to/r6-evaluation-continuation-inventory.json \
  --inventory-sha256 <inventory-file-sha256> \
  --inventory-review /absolute/path/to/inventory-identity-review.json \
  --inventory-review-sha256 <inventory-review-file-sha256> \
  --scratch /absolute/path/to/new-absent-evaluation-directory \
  --output-plan /absolute/path/to/new-continuation-plan.json
```

This binds the original candidate separately from the amended evaluator,
all validation-program bytes, the original environment and unchanged
scientific terminal path. The frozen continuation uses two spawned workers,
808 verified completed inputs and 1,592 missing inputs, with zero finder or
new Dask executions. Its disk admission reserves 8 GiB of free space for
array-free evaluation records and final statistics; it does not duplicate
native image products. Freezing is not the exhaustive launch preflight.

Create a separate identity review binding the plan's exact file and canonical
hashes. Its expected execution digest is the canonical plan hash. Then run:

```console
python -m scripts.validation.continue_source_catalogue_evaluation \
  --plan /absolute/path/to/new-continuation-plan.json \
  --plan-sha256 <continuation-plan-file-sha256> \
  --identity-review /absolute/path/to/continuation-identity-review.json \
  --identity-review-sha256 <continuation-review-file-sha256> \
  --preflight-only
```

Admission repeats the exhaustive inventory audit, including all retained
capture/reference artifacts and saved Dask identities, without rescoring.
Execution requires the separate exact one-use evaluation-only decision:
remove `--preflight-only` and add `--authorization` and
`--authorization-sha256`. The execution command repeats admission; a previous
preflight is not a shortcut. The original replay decision is rejected.

Missing records are written only under the new scratch. Completed v1 records
are reused byte-for-byte; new Continuum diagnostics use the approved v2
unavailable-support representation. Each worker validates its completion
immediately, so invalid records stop dispatch before late aggregation.
A combined `evaluation-seal.json` is
published before the unchanged late statistical engine. Process failures
retain that seal and all completed per-input records. A completed scientific
failure is published as terminal evidence, not retried or tuned. There is no
resume/overwrite switch: a later process repair requires another exact freeze.
