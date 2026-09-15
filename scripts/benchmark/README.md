# Benchmark scripts

This directory contains reproducible benchmark entry points for:

- PyBDSF reference runs;
- Hebog using serial, threaded, and Dask executors;
- Rapthor's complete `filter_skymodel` task;
- the source-finder comparison notebook's PyBDSF, Aegean and Hebog runs.

Every result must record the dataset identifier, git revisions, configuration,
Python and dependency versions, worker topology, CPU allocation, wall time,
CPU time, and peak resident memory. Generated results belong in the ignored
`benchmark-results/` directory.

Closed Phase 5 campaign launchers, freezers, reviews, compilers and evaluators
were removed after that development phase closed. Their scientific conclusions
are summarized in the
[campaign overview](../../docs/reference/phase-5-campaign-overview.md); the
code remains in [Git history at `4babf0b`](https://github.com/gemmadanks/hebog/tree/4babf0baaf5609e72764183e543df84ec6be09e0).

## Source-finder comparison notebook

The [notebook guide](../../docs/how-to/notebooks.md) is the current source for
input downloads, saved comparison restoration, refresh/resume commands and
troubleshooting. Run from the repository root:

```console
uv run python scripts/benchmark/download_notebook_data.py --list
uv run python scripts/benchmark/prepare_notebook_comparison.py --build-images --dry-run
uv run python scripts/benchmark/prepare_notebook_comparison.py --build-images
uv run python scripts/benchmark/refresh_public_notebook_hebog.py \
  --input-campaign benchmark-results/notebook-comparison/input-campaign/campaign.json \
  --reference-campaign benchmark-results/notebook-comparison/reference-campaign/campaign.json \
  --history-root benchmark-results/notebook-comparison/hebog-refreshes \
  --preflight-only
```

| Script | Role |
| --- | --- |
| `download_notebook_data.py` | Downloads configured LoTSS cutouts and optional SDC1/Hydra files into `benchmark-results/notebook-data/`. |
| `prepare_notebook_comparison.py` | Downloads the 13 comparison inputs, writes SDC1 halo cutouts and normalized LoTSS planes, builds or inspects local Podman images, and runs both reference finders serially. |
| `run_notebook_reference.py` | Container worker for one PyBDSF 1.14.1 or AegeanTools 2.3.5 run: native products plus core-cropped comparison products. |
| `refresh_public_notebook_hebog.py` | Runs current Hebog over a prepared or restored input set, reuses saved references and registers an immutable history entry. |
| `run_notebook_hebog.py` | Hebog runner used by the refresh for one input and optional output core. |

The cases, download sources and reference-finder options are checked in at
`config/comparisons/notebook-comparison.json`. The Podman recipes are in
[`containers/reference-finders/`](containers/reference-finders/README.md).
Results record actual image IDs, dependency inventories, source-tree and
scientific-composition digests; they are diagnostic comparisons, not
qualification or performance evidence. Without explicit paths, the Hebog
refresh selects the saved SDC1/Hydra/LoTSS bundle under
`benchmark-results/phase-5/`, which must be restored from the data host.

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

Hebog notebook results run the public continuum profile with the standard 5/3
thresholds through `run_notebook_hebog.py`. Scientific changes reach the
notebook only through that standard runner.

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

## Phase 4 paired scientific campaign runners

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

The one-look evaluator, power, assumption-audit and freeze commands for the
closed Phase 4 campaigns are in Git history. A future campaign needs its own
prospectively reviewed protocol and evaluator.
