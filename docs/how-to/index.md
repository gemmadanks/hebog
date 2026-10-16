# Contribute to Hebog

This page is the development workflow for people working on Hebog itself.
To call Hebog from a pipeline, read
[Integrate Hebog into a pipeline](integrate-into-a-pipeline.md); for the
design, the [architecture overview](../architecture/index.md). The working
rules are in the repository's
[`AGENTS.md`](https://github.com/gemmadanks/hebog/blob/main/AGENTS.md) and
[`CODE_REVIEW.md`](https://github.com/gemmadanks/hebog/blob/main/CODE_REVIEW.md),
and the current position against the project goals is on
[progress against goals](../reference/progress-against-goals.md).

## Set up a source checkout

Hebog uses [uv](https://docs.astral.sh/uv/) for environments and
[just](https://just.systems) for recipes:

```console
git clone https://github.com/gemmadanks/hebog.git
cd hebog
uv sync --all-groups
just check
```

`just --list` shows every recipe and `just ci` runs comprehensive local
checks; hosted CI also covers the supported platform matrix. The
demonstration notebook is
`uv run marimo edit notebooks/source_finder_demo.py`; the
[notebook guide](notebooks.md) covers the rest.

## Checks and test lanes

| Recipe | What it runs | When |
| --- | --- | --- |
| `just check` | Ruff format and lint, strict Pyright over `src/` and `tests/`, unit tests and doctests | Final changes; equivalent passing checks in `just pre-commit` suffice |
| `just coverage` | The portable unit and integration suite with branch coverage; the floor is 80% | Production changes |
| `just test-contract`, `just test-integration`, `just test-acceptance` | Public behaviour contracts; Dask, FITS and Rapthor boundaries; Rapthor-facing scenarios | Changes to the public API, executors, I/O or products |
| `just test-equivalence` | `find_sources` and its stages against frozen PyBDSF products | Scientific changes |
| `just test-slow` | Long regressions and development matrices; CI runs them weekly and on dispatch | Before a release that changes science |
| `just test-benchmark` | The quick-benchmark and traced-peak smoke tests, which CI runs on code-changing pull requests | Changes to the benchmark tooling |
| `just test-qualification`, `just test-scalability` | Controlled lanes that need approved data or hardware | Only when the plan names them |
| `just rapthor-agreement` | Rapthor's retained/rejected agreement with pinned `master` for each Hebog profile and background (task 21; [below](#measure-rapthor-profile-agreement)) | Science changes and pin moves that can change what Rapthor keeps |
| `uv run python scripts/validation/check_lsmtool_filter.py` | Pinned LSMTool's `filter_sources` in its container (`scripts/validation/containers/lsmtool`) on the Rapthor adapter's products under the Serial, Thread and Dask executors | Changes to the adapter's products or the LSMTool pin |
| `just pre-commit` | Every hook, slow ones included | Before staging a commit |

Rules the test configuration enforces:

- Markers are strict and declared in `pyproject.toml`; every warning is an
  error and every `xfail` is strict.
- Unit tests need no scheduler, network or downloaded data. A test that
  needs data outside the repository is marked `requires_data`, which every
  routine lane excludes: it runs in the qualification or scalability lane or
  when called directly, skips when its input is not configured, and fails
  when the configured file is missing.
- `config/contracts/phase-0-public-behaviours.json` names the test that
  holds each frozen public behaviour. An unimplemented behaviour is a
  strict-xfail placeholder; when it starts passing, convert the test to a
  normal assertion and set the behaviour's status to `implemented`.
- A pass with local `benchmark-results/` present does not prove CI
  portability; run the quick lane from a clean checkout too.

### Pull-request feedback

Code-changing PRs and every push to `main` run the full portable suite on
the existing operating-system/Python matrix. The **Fast unit tests** check
reports unit tests and doctests before the integration suite finishes;
those tests also remain in the portable matrix. Scientific comparisons,
acceptance tests, measurement smoke tests, notebooks, docs, containers and
the installed-wheel workflow still run.

| Environment | Shards | Pytest workers per shard |
| --- | ---: | ---: |
| Ubuntu / Python 3.12, 3.13 and 3.14 | 2 each | 4 |
| Ubuntu / Python 3.12 / lowest declared dependencies | 2 | 4 |
| macOS / Python 3.14 | 2 | 2 |
| Windows / Python 3.14 | 4 | 4 |

Each shard uses `pytest-split`'s `least_duration` algorithm and the same
timing snapshot. A run without a cached snapshot divides tests by count.
Successful portable suites on `main` cache the slowest measured time per test
across the matrix for future runs. New tests receive the plugin's average-time
estimate. Timings are scheduling hints, not scientific performance evidence.
All selected tests run once per environment, and Ubuntu/Python 3.14 branch
coverage is combined before enforcing the unchanged 80% project floor.

Existing required portable-test names are aggregate checks over the whole
matrix; shard logs are under **Portable execution**. **Package smoke test**
is the final gate over all applicable checks; the actual wheel exercise
runs independently under **Build and exercise the installed wheel**. The
required check names stay unchanged, including the lowest-dependency and
container checks. Failed, cancelled, missing or unexpectedly skipped checks
cannot pass a gate.

PRs changing only `README.md`, `LOG.md`, Markdown under `plans/`, or Markdown
and images under `docs/` run lint, spelling and the strict docs build. The
aggregate checks explicitly permit the omitted jobs for this path. Any
other changed path, including deleted or renamed code, MkDocs configuration,
notebooks, dependencies, packaging, CI, release metadata or repository
instructions, runs full CI. Empty diffs also run full CI.

To investigate the expensive tail, download `test-results-*` artifacts:
they contain JUnit XML and, for portable shards and the fast unit check,
`durations.json`. Pytest also prints its 50 slowest phases. The merged
`ci-measured-durations` artifact can reproduce a shard locally:

```console
uv run pytest -n 4 --dist worksteal --splits 4 --group 1 \
  --splitting-algorithm least_duration --durations-path=/path/to/durations.json \
  -m "not slow and not equivalence and not acceptance and not qualification and not benchmark and not scalability and not requires_data" tests
```

More shards consume more runner slots, and individual long tests still set
a lower bound on latency. Compare hosted timings and memory after the first
runs before increasing worker counts further or changing expensive fixtures.
Do not move Windows coverage off PRs: it is the supported platform the
development machine does not exercise.

## Run the quick science check

Run it for every change that can affect scientific output. It takes about
ten minutes once its references are cached:

```console
just quick-science-check --baseline benchmark-results/quick-check/runs/<earlier-run>/report.json
```

The 18 cases in `config/checks/quick-science-check.json` are fourteen
generated images with injected truth
(`config/datasets/quick-science-check.json`), two SDC1 cut-outs and two
LoTSS-DR3 cut-outs with their published PyBDSF RMS and mask maps. For each
case it reports completeness, reliability, position and flux errors and
position-uncertainty coverage against truth, the median and 95th-percentile
RMS error and the mask recall over the injected emission at least three
times the noise, the same catalogue comparisons against pinned PyBDSF
`master`, and RMS and mask agreement. It prints a summary and writes
`report.json` under `benchmark-results/quick-check/runs/<label>/`.

With `--baseline` it exits non-zero when a case failed or is missing from the
baseline, a case's input changed, a metric can no longer be measured, or a
metric moved in the worse direction beyond its tolerance. It also names any
run identity that differs from the baseline (the scientific composition hash,
the reference identity and the case configuration), which explains a moved
metric without being a regression.

PyBDSF runs once per input in the local
`localhost/hebog-pybdsf-master:c70103be3-reconstructed` Podman image. Its
results are cached under `benchmark-results/quick-check/references`, keyed by
the input and by the code the reference worker runs, so a Hebog algorithm
change keeps the cache and a catalogue-normalisation change reruns it once.
Only the worker's own refusal (exit status 1) is cached as a failure; a
container or signal failure stops the check and caches nothing. Use `--cases`
for a subset and `--allow-download` to fetch missing remote cut-outs; the
SDC1 cut-outs are cut from a local copy of `SKAMid_B2_1000h_v3.fits`.

This is a regression detector, not powered scientific parity: each case is
one realization and no confidence interval is claimed.

## Measure Rapthor-profile agreement

Plan task 21 chooses the Hebog profile and background Rapthor runs by how
often Rapthor's filter step keeps the same sky-model components with
Hebog's mask as with pinned PyBDSF `master`'s. Rerun it when the science,
the Rapthor or LSMTool pins, or the reference changes:

```console
just rapthor-agreement --jobs 4
```

`config/checks/rapthor-agreement.json` adds a 3,000² window of the
LoTSS-DR3 mosaic and the LoTSS-Deep DR2 ELAIS-N1 true-sky and apparent
images, 2,048² at their centre, to the quick check's cases, and reuses the
quick check's inputs and cached `master` references. The ELAIS-N1 pair is
read from `benchmark-results/datasets/lotss-deep-dr2-elais-n1/`. Each of the
four lanes, `continuum` or `compact` with an `estimated` or `zero`
background, runs `find_sources` with the configuration the Rapthor adapter
builds; released PyBDSF 1.14.1 runs as a control, from the notebook's
`localhost/hebog-notebook-pybdsf:1.14.1` image.

LSMTool keeps a component where the mask is set at `mask[int(y), int(x)]`
and groups the kept ones by the mask's 8-connected islands. WSClean's
component lists are not available for these images, so the population is
every distinct pixel holding the centre of a Gaussian that `master` or any
lane fitted, the same set for every lane. Each component is tagged bright
(at least 75 times `master`'s RMS), edge (within three beam FWHM of the
border), masked (within three FWHM of a blank pixel), crowded (another
component within two FWHM) or sparse, extended (on an island of all the
masks together larger than ten beam areas), and true-sky or apparent.
A lane passes at 99.5% agreement overall and in every stratum, and the
rule chooses `compact` for a background only when its lane passes.

The report, `benchmark-results/rapthor-agreement/runs/<label>/report.json`,
also gives each lane's agreement with `master` on two diagnostic
populations, injected truth and every pixel WSClean's auto-threshold would
clean (at least 1 sigma, connected to a 5-sigma peak); how its patches
group; compact's decisions against continuum's; and Rapthor's catalogue
cuts on matched sources (`DC_Maj` below 10″ and `E_RA`, `E_DEC` below 2″),
counting the sources a lane drops because they have several components
and those it keeps as unresolved from a fit 10″ or wider. Use `--cases` for
a subset and `--skip-references` to use cached references only.

## Run the quick benchmark

Run it for every change that can affect runtime. The default tier takes about
ten minutes of Hebog time once its baselines are cached:

```console
just quick-benchmark
just quick-benchmark --tier large
```

The tiers in `config/benchmarks/quick-benchmark.json` are `smoke` (one 512²
generated image, run in CI), `default` (the 1,024² generated dense field and
sparse and dense 1,024² LoTSS-DR3 cut-outs) and `large` (the default cases,
SDC1 crowded cut-outs at 1,024² and 2,048², LoTSS-DR3 cut-outs at 3,000²,
3,600² and 10,000², the whole 15,402² mosaic they are cut from, and the
generated `wide-objects-10000` diagnostic, whose filament exercises the
wide-object paths). 2,048² is the last size the stages outside background and
RMS run as one tile and 3,000² the first they tile, so that pair measures the
execution crossover; the 10,000² cut-out and the whole mosaic are the tier
anchors. The large tier takes hours and runs before profiling or a release
that claims a runtime change.

The protocol comes from `config/benchmarks/phase-0-performance.json`: one
warm-up and five measured repetitions, each a fresh single-thread process
running the public finder with the serial executor, so interpreter start-up,
imports, FITS input and product writing are included. Each case is compared
with two cached baselines measured once per input and machine: the previous
Hebog release (the latest `v*` tag by default; `--previous-release` chooses
another, `--no-previous-release` skips it) and pinned PyBDSF `master` in the
quick check's container with four cores (`--no-reference` skips it). A
comparison passes when the upper 95% bootstrap bound of the median ratio is
within the limit, fails when the lower bound exceeds it, and is otherwise
inconclusive; the run exits non-zero when a case or the previous-release
comparison fails. A previous release that refuses an input is cached with
its error and printed as `NOT CHECKED` rather than failing the run;
`--refresh-previous-release` retries it. The run writes `report.json` and
one `BenchmarkEvidence` record per case under
`benchmark-results/quick-benchmark/runs/<label>/`.

Two caveats. Cached baselines drift with machine state by up to 15% between
sessions, so confirm a regression whose CPU time did not change with
`--refresh-previous-release`, which measures the previous release again in
the same session. And the `master` ratio is diagnostic, not the deployment
gate: Hebog runs natively on one thread and PyBDSF in a Linux container with
four cores. Only the matched `filter_skymodel` benchmark can pass or fail
that gate.

## Run the matched filter_skymodel benchmark

Plan task 23's deployment gate compares Rapthor's complete `filter_skymodel`
step with Hebog's native task against the same step with pinned PyBDSF
`master`, in one Linux container on the same cores. Build the
[benchmark image](https://github.com/gemmadanks/hebog/blob/main/scripts/benchmark/containers/filter-skymodel/README.md)
on the Rapthor integration image, then:

```console
uv run python scripts/benchmark/measure_filter_skymodel.py \
  --beam-ms <Measurement Set> --label <label>
```

It writes the sector's inputs from the LoTSS-DR3 3,000² window of the
Rapthor agreement check, runs one warm-up and five measured repetitions of
each finder in fresh containers, alternating them, and writes one evidence
document per finder and `report.json` under
`benchmark-results/filter-skymodel/runs/<label>/`, with the ratio of medians
and its one-sided 95% bounds against the gate. `--hebog-dask-workers`
runs Hebog on Dask workers instead of Rapthor's threads, a screening
measurement the gate does not count. The image runs under Rosetta
on Apple silicon, so only the ratio is matched; see the
[benchmark guide](https://github.com/gemmadanks/hebog/blob/main/scripts/benchmark/README.md#matched-filter_skymodel-benchmark)
for the inputs it constructs.

## Measure the traced-allocation peak

Measure it before raising the public envelope and whenever a change can move
how much memory a run needs:

```console
just traced-peak
just traced-peak --tier large --cases lotss-dr3-1312-dense-3000 --repetitions 2
```

The gate figure is `tracemalloc`'s peak, which repeats to a few kilobytes for
one input, configuration and implementation. Peak resident memory varied by
42% with machine load on identical code, so it is reported beside the traced
peak as an envelope and never as the threshold. Tracing roughly doubles wall
time, so the quick benchmark never traces and a traced run records no
comparable timing; the cases and settings are the quick benchmark's own, so a
peak and a timing describe the same configuration.

Each repetition runs a fresh single-thread process that starts tracing before
it imports Hebog and reports the process peak (the gate figure), the peak of
the `find_sources` call alone and the import floor, so a peak can be compared
with one measured over a different span. One repetition is the default;
reviewed evidence needs two or more that agree within a tenth of a mebibyte,
and repetitions that disagree fail the run. Inputs above the public limit use
the worker's `--diagnostic-size-limit`, which raises the limit only inside
that process. Records go to `benchmark-results/traced-peak/runs/<label>/`.

To find where a peak lies, attribute it:

```console
uv run python scripts/benchmark/attribute_traced_peak.py \
  --input <image.fits> --settings '<finder JSON>' --result <attribution.json> \
  --snapshot-within detect_multiscale_products --diagnostic-size-limit <side>
```

It traces one serial run with every public-path function and executor task
measured as a nested call, and a `tracemalloc` snapshot inside
`--snapshot-within` names the call sites holding what that pass keeps across
tiles. It is a diagnostic, not the gate; `--frames 1` is nearly as fast as
the harness when call sites are not needed.

### Audit task memory

Every round declares the memory its tasks hold, from its own measured cost
per read pixel (`hebog.stages.task_memory`), and
`hebog.analysis_memory_bytes` states what the analysis holds between tasks
for the sources it publishes.
After changing what a round reads or keeps, or a tile core, audit both on
the anchors the costs were measured on (3,000² and 10,000² LoTSS-DR3, and
the dense ELAIS-N1 central 5,000² with its flat-noise image):

```console
uv run python scripts/benchmark/audit_task_memory.py \
  --input <image.fits> [--flat-noise <flat-noise.fits>] \
  --settings '<finder JSON>' --result <audit.json>
```

Each round's *load* is its largest task peak over its declaration. A cost
measured on an anchor reads at most 0.8 there, because declarations carry a
quarter of headroom; above one the runner fails, and the round's cost in its
stage module needs raising.

## Profile complete execution

Profile before optimizing. The profile splits one complete run into its
stages and separates the cost of image size from the cost of sources:

```console
just profile-execution --label <label> --cprofile
just profile-execution --label <label> --cases profile-dense-1024
```

The cases in `config/benchmarks/complete-execution-profile.json` are a
`ladder` of noise-only and dense generated images at 512² to 4,096² with 256
sources per 1,024², and `real` LoTSS-DR3 and SDC1 cut-outs on one field. Each
case runs once in a fresh single-thread serial process on macOS or Linux; the
worker wraps the public path's functions with timers, so no Hebog code
changes, and records each stage's calls, wall and CPU time and peak memory.
Stages nest, so FITS and Zarr I/O appear under the stage that made them, and
wall minus CPU time is mostly file-system wait. `--cprofile` runs each case
again under `cProfile` for the functions with the most self time. Process
time outside the run is split into module imports, worker overhead, and
process creation and shutdown.

`summary.json` under `benchmark-results/profiles/runs/<label>/` fits each
stage on the ladder as a fixed cost plus a cost per megapixel and per fitted
component. `--threads N` runs the cases on a thread executor and
`--dask-workers N` on a process-based local Dask cluster of single-threaded
workers; `--memory-budget-bytes` is the memory admitted to tasks, split
evenly into the Dask workers' memory limits. Those limits are what Hebog
admits tasks by: Dask's spilling, pausing and restarting are off, since
Hebog's workers hold no data between tasks. Stages are timed on the
driver's thread, and every task times itself where it runs and counts the
Zarr chunks it reads and writes (`hebog.validation.task_recording`), so
each stage reports its tasks, the share of the workers they kept busy, the
time no task ran and its Zarr I/O, and each round its tasks, under every
executor. A stage with long idle time is waiting on the driver.

`just profile-scaling --label <label> --memory-budget-bytes <bytes>` runs
the cases in `config/benchmarks/sector-scaling-profile.json`, the 10,000²
anchor and the whole 15,402² mosaic, at each of `--thread-workers` and
`--dask-workers` (1, 2, 4, 8 and 12 by default; none skips the executor),
on `--thread-cases` and `--dask-cases` (every case by default), within one
budget, resuming where an interrupted sweep stopped. Its `scaling.json`
reports each curve's speedup, its serial share as an Amdahl fit, each
stage's parallel efficiency and serial seconds, and each round's task-time
inflation; a run whose Dask workers' share of the budget admits no task of
the largest round is recorded as refused. Plan task 73's sweep, Dask at
every count on both cases and threads at 1 and 12 on the anchor, takes
about five hours on the development machine. To profile one
input outside the configured cases, run
`scripts/benchmark/profile_complete_execution_worker.py` directly with
`--input`, `--settings` and `--result`. A profile ranks costs; only the quick
benchmark establishes a speedup.

## Develop test-first

For a public behaviour or scientific kernel:

1. Write the smallest analytic, property, contract or regression test and
   confirm that it fails for the intended reason.
2. Implement the simplest deterministic serial behaviour that passes.
3. Refactor, then add pathological and property-based cases.
4. Prove thread and Dask conformance against the serial result.
5. Run scientific equivalence before making a performance claim.

Use analytic truth and invariants before treating PyBDSF as an oracle: its
products establish compatibility, not scientific truth. Qualification
datasets are held out from routine development.

## Record evidence

The quick benchmark, traced-peak and profile runners identify the measured
Hebog by its commit, whether the tree was dirty and the hash of `src/hebog`,
read as the run starts. Every repetition imports the checkout afresh, so an
edit to `src/hebog` during a run changes what later repetitions measure:
develop the next change in a separate worktree.

Write runs with `hebog.validation.evidence` and `write_evidence`, with `null`
plus a reason in `unavailable_metrics` for instrumentation that is
unavailable, never zero. Raw results stay under the ignored
`benchmark-results/`; commit only compact reviewed summaries and the commands
that reproduce them. A record is `reviewed` only after its protocol and
environment pass review. The
[evidence documents](../reference/evidence-documents.md) page lists what a
benchmark or multi-node record must contain, and the
[performance and scalability contracts](../reference/performance-scalability-contracts.md)
set the gates it is judged against.

## Conventions a change must keep

- **Layering.** `LAYER_IMPORTS` in `tests/unit/test_architecture.py` is the
  one table of allowed imports; an import outside it needs a named exemption
  there. See the [architecture overview](../architecture/index.md).
- **Executors.** Every executor obeys the contract in
  [How Hebog distributes work](../architecture/distributed-execution.md#the-executor-contract),
  so a defect must show on `SerialExecutor`.
- **FFTs.** Call FFT convolution through `hebog.algorithms.fft`, never SciPy
  or NumPy directly: SciPy's Windows wheels share an unlocked FFT plan cache,
  and the wrapper serializes transforms there. A unit test fails on any other
  FFT import.
- **Intermediate planes.** Zarr is the only intermediate backend
  ([ADR-007](../architecture/adr/007-use-zarr-for-intermediate-image-storage.md));
  the store's guarantees are in the
  [internal schemas](../reference/internal-schemas.md#intermediate-zarr-generation).
- **Acceptance scenarios.** Readable pytest tests in Given/When/Then form; no
  Gherkin framework unless domain experts will write feature files.
- **Extension seams.** Add a protocol or dataclass only when a second
  implementation demonstrates the variation; see the
  [quality attributes](../explanation/quality-attributes.md).
