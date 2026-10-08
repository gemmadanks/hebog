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

`just --list` shows every recipe and `just ci` reproduces continuous
integration locally. The demonstration notebook is
`uv run marimo edit notebooks/source_finder_demo.py`; the
[notebook guide](notebooks.md) covers the rest.

## Checks and test lanes

| Recipe | What it runs | When |
| --- | --- | --- |
| `just check` | Ruff format and lint, strict Pyright over `src/` and `tests/`, unit tests and doctests | Every change |
| `just coverage` | The portable unit and integration suite with branch coverage; the floor is 80% | Production changes |
| `just test-contract`, `just test-integration`, `just test-acceptance` | Public behaviour contracts; Dask, FITS and Rapthor boundaries; Rapthor-facing scenarios | Changes to the public API, executors, I/O or products |
| `just test-equivalence` | `find_sources` and its stages against frozen PyBDSF products | Scientific changes |
| `just test-slow` | Long regressions and development matrices; CI runs them weekly and on dispatch | Before a release that changes science |
| `just test-qualification`, `just test-benchmark`, `just test-scalability` | Controlled lanes that need approved data or hardware | Only when the plan names them |
| `just pre-commit` | Every hook, slow ones included | Before staging a commit |

Rules the test configuration enforces:

- Markers are strict and declared in `pyproject.toml`; every warning is an
  error and every `xfail` is strict.
- Unit tests need no scheduler, network or downloaded data. A test that
  needs local products uses `integration` and `requires_data` and fails,
  rather than skips, when the data is missing or changed.
- `config/contracts/phase-0-public-behaviours.json` names the test that
  holds each frozen public behaviour. An unimplemented behaviour is a
  strict-xfail placeholder; when it starts passing, convert the test to a
  normal assertion and set the behaviour's status to `implemented`.
- A pass with local `benchmark-results/` present does not prove CI
  portability; run the quick lane from a clean checkout too.

## Run the quick science check

Run it for every change that can affect scientific output. It takes about
ten minutes once its references are cached:

```console
just quick-science-check --baseline benchmark-results/quick-check/runs/<earlier-run>/report.json
```

The 17 cases in `config/checks/quick-science-check.json` are thirteen
generated images with injected truth
(`config/datasets/quick-science-check.json`), two SDC1 cut-outs and two
LoTSS-DR3 cut-outs with their published PyBDSF RMS and mask maps. For each
case it reports completeness, reliability, position and flux errors and
position-uncertainty coverage against truth, the same against pinned PyBDSF
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
component. `--dask-workers N` runs the cases on a process-based local Dask
cluster and matches Dask's task stream against each stage, so a stage with a
long driver wall time and low worker occupancy is waiting on the driver.
Each worker's task times are shifted by its heartbeat estimate of its clock's
offset from the scheduler's; on one host that is estimation error alone, up
to about 0.3 s while the driver is busy, so tasks are matched to short stage
calls only that closely, and occupancy never counts more workers busy than
there are. To profile one input outside the configured cases, run
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
