# Benchmark scripts

This directory contains reproducible benchmark entry points for:

- PyBDSF reference runs;
- the quick benchmark of complete Hebog runs against the previous release
  and pinned PyBDSF `master`;
- the traced-allocation peak that gates a public envelope raise;
- a stage profile of complete Hebog runs across image size and source density;
- Rapthor's complete `filter_skymodel` task;
- the source-finder comparison notebook's PyBDSF, Aegean and Hebog runs.

Every result must record the dataset identifier, git revisions, configuration,
Python and dependency versions, worker topology, CPU allocation, wall time,
CPU time, and peak resident memory. Generated results belong in the ignored
`benchmark-results/` directory.

Earlier campaign launchers, freezers, reviews, compilers and evaluators were
removed; their conclusions are in `LOG.md` and the code remains in
[Git history at `4babf0b`](https://github.com/gemmadanks/hebog/tree/4babf0baaf5609e72764183e543df84ec6be09e0).

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

The Phase 1 to 5 stage and matrix benchmark runners (`measure_phase1_io.py`
to `measure_phase5_multiscale.py`, their input generators, matrix drivers and
`config/benchmarks/phase-4-performance.json` and `phase-5-performance.json`)
were replaced by the quick benchmark below. Their component budgets timed
stages of the whole-array path that milestone M2 replaces. They remain in
[Git history at `v0.7.0`](https://github.com/gemmadanks/hebog/tree/v0.7.0/scripts/benchmark).

## Quick benchmark

`quick_benchmark.py` times complete FITS-to-products runs on the cases in
`config/benchmarks/quick-benchmark.json`, compares them with the previous
Hebog release and pinned PyBDSF `master`, and writes one `BenchmarkEvidence`
record per case. The [development workflow guide](../../docs/how-to/index.md#run-the-quick-benchmark)
describes the tiers, protocol, baselines and exit status:

```console
just quick-benchmark
just quick-benchmark --tier large --allow-download
just quick-benchmark --tier smoke --no-previous-release --no-reference
```

`quick_benchmark_worker.py` is the process it times. It uses only the public
API and the standard library, so the same worker runs current Hebog and a
release installed from its tag. Its `--diagnostic-size-limit` option is the
diagnostic entry point for inputs above an installation's public size limit:
it raises the limit only inside that worker process and leaves
`hebog.find_sources` unchanged. The benchmark passes it on every run, set to
the input's own size, so a timing never depends on which release's envelope
is in force.

The pinned-`master` timings reuse the notebook reference container through
`prepare_notebook_comparison.py`. `run_notebook_reference.py` records its own
wall time, CPU time and peak memory, including PyBDSF's worker processes, from
input validation to product normalisation. Container start-up and interpreter
imports are excluded, while Hebog's timings include them, so the ratio
slightly favours PyBDSF.

The closed Phase 4 paired campaign runners and compiler were removed with the
campaign tooling and remain in
[Git history at `v0.7.0`](https://github.com/gemmadanks/hebog/tree/v0.7.0/scripts/benchmark).

## Traced-allocation peak

`measure_traced_peak.py` measures the deterministic `tracemalloc` peak of
complete runs on the quick benchmark's own cases and settings, and writes one
`TracedAllocationEvidence` record per case. It is the only committed way to
produce the figure the plan's envelope-raise gate names; a peak quoted from
anywhere else is not reproducible. The
[development workflow guide](../../docs/how-to/index.md#measure-the-traced-allocation-peak)
describes the spans, repetitions and exit status:

```console
just traced-peak
just traced-peak --tier large --cases lotss-dr3-1312-dense-3000 --repetitions 2
```

`measure_traced_peak_worker.py` is the traced process. It starts tracing
before it imports Hebog and then imports nothing but the standard library and
the public API, so the figure covers the run and only the run: importing the
validation package would add its own allocations to what is being measured.
Software identity comes from the parent, which runs the same interpreter. The
statistics, the worker contract and the evidence live in
`hebog.validation.traced_peak`, with unit tests in
`tests/unit/validation/test_traced_peak.py`, the worker contract in
`tests/integration/test_traced_peak_worker.py` and the complete measurement
path in `tests/benchmark/test_traced_peak_smoke.py`, which CI runs.

Tracing roughly doubles wall time, so this runner never times anything for
comparison and the quick benchmark never traces.

## Complete-execution profile

`profile_complete_execution.py` profiles complete runs by stage on the cases
in `config/benchmarks/complete-execution-profile.json` and fits stage times
against image size and fitted components. `profile_complete_execution_worker.py`
is the single-thread process it starts for each case, and
`build_profile_datasets.py` writes the generated size and density ladder. The
timing, stage splitting and cost model live in
`hebog.validation.execution_profile`, with unit tests in
`tests/unit/validation/test_execution_profile.py`. The
[development workflow guide](../../docs/how-to/index.md#profile-complete-execution)
describes the cases and outputs:

```console
just profile-execution --label <label> --cprofile
```
