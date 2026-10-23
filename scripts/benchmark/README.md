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

Earlier campaign and stage benchmark tooling was removed; it remains in
Git history at
[`4babf0b`](https://github.com/gemmadanks/hebog/tree/4babf0baaf5609e72764183e543df84ec6be09e0)
and [`v0.7.0`](https://github.com/gemmadanks/hebog/tree/v0.7.0/scripts/benchmark).

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

## Matched filter_skymodel benchmark

`measure_filter_skymodel.py` is the matched benchmark of
Rapthor's `filter_skymodel` step: Rapthor's native Hebog task
against its PyBDSF subprocess with pinned `master`, in one
[benchmark image](containers/filter-skymodel/README.md) on the same cores.
It writes one sector's inputs from a real image with
`hebog.validation.filter_benchmark`: the image twice in WSClean's four-axis
layout, a polygon inset 5% from its border, and WSClean-style component
lists with a point component on every island pixel (3 sigma, connected to
5 sigma), since Rapthor's WSClean cleans to 1 sigma inside the previous
cycle's island mask. A Measurement Set given with `--beam-ms` selects
Rapthor's production two-pass mode. Each warm-up
and measured repetition runs `filter_skymodel_worker.py` in a fresh
container, alternating the finders, and the report applies the deployment
gate's ratio rule to the source-finding part of each run, from the task's
start to LSMTool's `filter_sources` call, the span the finder controls,
with the limit of the sector's class (dense when `master`'s catalogue holds
at least 10,000 sources), and reports the complete step's ratio beside it:

```console
mkdir -p benchmark-results/filter-skymodel/beam
git -C <LSMTool checkout> show \
  156ae6abd5cb89e7e622b9bd7a37ef7539a76ea2:tests/resources/test_midbands.ms.tgz \
  | tar -xz -C benchmark-results/filter-skymodel/beam
uv run python scripts/benchmark/measure_filter_skymodel.py \
  --container-image localhost/hebog-filter-benchmark:<tag> \
  --beam-ms benchmark-results/filter-skymodel/beam/test_midbands.ms \
  --label <label>
```

`test_midbands.ms` is pinned LSMTool's 16 MB test Measurement Set; with
the apparent component list supplied, LSMTool reads only its times, and
EveryBeam, which fails under Rosetta, is never imported.

The image runs under Rosetta on Apple silicon, so the ratio is matched but
the times are emulated.

`--case` also takes the sector scaling profile's 10,000² anchor and 15,402²
mosaic, and the source-count ladder's 5,000² sectors
(`config/benchmarks/source-count-ladder.json`): a window of the LoTSS-DR3
mosaic and of the deep ELAIS-N1 field, and the deep window with
its noise raised 1.5, 2, 3 and 4 times, which
`build_source_count_ladder.py` writes from
`config/benchmarks/source-count-ladder-noise.json` with one seed. The deep
field's central window stops pinned `master` with an `IndexError` in its
moment-analysis fallback, so the ladder's dense cell lies 3,600 pixels
north of it. `--hebog-dask-workers N` runs the native task's Hebog work on N
single-threaded Dask worker processes instead of Rapthor's threads. Rapthor's
Hebog branch has no Dask path for Hebog yet, so such a run
screens what one could give and never counts towards the gate.

## Phase 0 PyBDSF baselines

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

## Task memory audit

`audit_task_memory.py` traces one serial run and compares each round's
largest task peak with the memory the round declares, and the analysis's
peak between tasks with `hebog.analysis_memory_bytes` for the image and the
sources the run published. It exits with status
1 when a round declares nothing or a peak exceeds its declaration. The
tracing executor and the document live in `hebog.validation.task_memory_audit`,
with unit tests in `tests/unit/validation/test_task_memory_audit.py`; the
[development workflow guide](../../docs/how-to/index.md#audit-task-memory)
describes when to run it:

```console
uv run python scripts/benchmark/audit_task_memory.py \
  --input <image.fits> --settings '<finder JSON>' --result <audit.json>
```

## Complete-execution profile

`profile_complete_execution.py` profiles complete runs by stage on the cases
in `config/benchmarks/complete-execution-profile.json` and fits stage times
against image size and fitted components. `profile_complete_execution_worker.py`
is the single-thread process it starts for each case, and
`build_profile_datasets.py` writes the generated size and density ladder. The
timing, stage splitting and cost model live in
`hebog.validation.execution_profile`, with unit tests in
`tests/unit/validation/test_execution_profile.py`.
`hebog.validation.task_recording` times every task where it runs, under the
serial, thread or Dask executor. `profile_scaling.py` runs one sector at
several thread and Dask worker counts and summarises the curves with
`hebog.validation.scaling_profile`. The
[development workflow guide](../../docs/how-to/index.md#profile-complete-execution)
describes the cases and outputs:

```console
just profile-execution --label <label> --cprofile
just profile-scaling --label <label> --memory-budget-bytes 16000000000
```

## One-sector scaling model

`fit_scaling_model.py` reads the matched benchmark's source-count ladder and
core sweep, PyBDSF's logs of the sweep and Hebog's native scaling profiles,
and projects both finders' finder parts to the cluster's node sizes, with
the targets the gate sets for Hebog and the ratios a target floor would
give. It times nothing; the model lives in
`hebog.validation.scaling_model`, and the summary, with each input's
checksum, goes to `benchmark-results/one-sector-scaling/model/<label>.json`:

```console
uv run python scripts/benchmark/fit_scaling_model.py --label <label>
```
