# Contribute to Hebog

This page is for developers working on Hebog itself. To call Hebog from your
own pipeline, read [Integrate Hebog into a pipeline](integrate-into-a-pipeline.md)
instead. For orientation, read the
[architecture overview](../architecture/index.md). The repository's
[`AGENTS.md`](https://github.com/gemmadanks/hebog/blob/main/AGENTS.md) and
[`CODE_REVIEW.md`](https://github.com/gemmadanks/hebog/blob/main/CODE_REVIEW.md)
hold the full working rules.

## Set up a source checkout

Hebog uses [uv](https://docs.astral.sh/uv/) for environments and
[just](https://just.systems) for task recipes:

```console
git clone https://github.com/gemmadanks/hebog.git
cd hebog
uv sync --all-groups
just check
uv run hebog --version
```

`just check` formats, lints, type-checks and runs the unit tests.
`just --list` shows every recipe, and `just ci` reproduces continuous
integration locally. Try the demonstration notebook with
`uv run marimo edit notebooks/source_finder_demo.py`.

## Choose the appropriate test lane

```console
just test-unit
just test-contract
just test-integration
just test-equivalence
just test-acceptance
just test-qualification
just test-benchmark
just test-scalability
```

Unit tests must be deterministic and require no scheduler or downloaded data.
Tests that need ignored local products use `integration` and `requires_data`
and are excluded from routine CI. They still fail if explicitly requested data
is missing or has changed; never substitute a conditional skip or regenerate
frozen expected products in a test.

Select data-dependent checks explicitly on a host that holds the data; do not
enable every controlled test lane just to validate a checkout.
Use synthetic temporary records for ordinary checksum, malformed-input,
serialization and write-once tests. A pass with local `benchmark-results/`
present does not establish CI portability: also run the quick lane from a clean
checkout without those ignored products.

Keep inexpensive protocol and write-once safety tests in portable CI while
their builders or readers remain maintained. Compare recomputed floating-point
planning results with an explicit round-off tolerance; frozen artifact bytes
and their recorded hashes still require exact equality. When retiring a
builder, retire its implementation-specific tests with it after checking for
remaining consumers.

Contract tests hold strict-xfail executable specifications until their planned
implementation turns them green; an unexpected pass fails CI until the test is
reviewed and converted to a normal assertion. Integration tests cover Dask,
FITS, and Rapthor boundaries. Equivalence tests
compare small redistributable cases with frozen PyBDSF products. Acceptance
tests describe Rapthor-facing behaviour. Qualification, benchmark, and
scalability tests require controlled resources or approved data and are never
implied by the quick suite.

## Run the quick science check

Run the quick science check for every change that can affect scientific
output. It takes about ten minutes on the development machine once its
references are cached:

```console
just quick-science-check --baseline benchmark-results/quick-check/runs/<earlier-run>/report.json
```

The cases are in `config/checks/quick-science-check.json`:

- twelve generated images with injected truth, described in
  `config/datasets/quick-science-check.json` and rebuilt by
  `scripts/validation/build_quick_check_datasets.py`;
- two SKA Data Challenge 1 cut-outs; and
- two LoTSS-DR3 cut-outs with their published PyBDSF RMS and mask maps.

For each case the check reports the fields Rapthor consumes:

- completeness, reliability, position and flux errors, and position
  uncertainty coverage against truth;
- the same measures against pinned PyBDSF `master`; and
- RMS and mask agreement with PyBDSF and with the published maps.

It prints a summary and writes `report.json` under
`benchmark-results/quick-check/runs/<label>/`.

With `--baseline`, it exits non-zero when any of the following is true:

- a case failed or is missing;
- a case is not in the baseline, so it was not compared;
- a metric can no longer be measured; or
- a metric moved in the worse direction beyond the configured tolerance.

PyBDSF runs once per input in the local
`localhost/hebog-pybdsf-master:c70103be3-reconstructed` Podman image, and its
results are cached under `benchmark-results/quick-check/references`. The cache
is keyed by the input and by the reference identity: the image's immutable ID,
the finder settings in `config/comparisons/notebook-comparison.json`, the core
count, the container command, and the reference worker with every repository
module it imports. A change to that code, such as catalogue normalisation or
the fitting modules it reaches, reruns the references once. Changing any of these reruns the reference, and a cached failure
applies only to the identity that failed. Remote cut-outs are accepted only
when the server returns exactly the requested bytes.
Generated inputs are materialised on first use. The SDC1 cut-outs are cut
from a local copy of `SKAMid_B2_1000h_v3.fits`. Missing real cut-outs are
fetched with HTTP range requests only when `--allow-download` is given. Use
`--cases` to run a subset while iterating.

This is a regression detector, not powered scientific parity. Each case is
one realization and no confidence interval is claimed.

## Run the quick benchmark

Run the quick benchmark for every change that can affect runtime. The default
tier takes about ten minutes of Hebog time on the development machine once
its baselines are cached:

```console
just quick-benchmark
```

The cases are in `config/benchmarks/quick-benchmark.json`, grouped in tiers:

- `smoke`: one 512² generated image, run in CI;
- `default`: the 1,024² generated dense field and sparse and dense 1,024²
  LoTSS-DR3 cut-outs; and
- `large`: the default cases plus SDC1 crowded cut-outs at 1,024² and 2,048²
  and LoTSS-DR3 cut-outs at 3,000² and 3,600², all on the same field as the
  1,024² dense case. Every stage outside background and RMS uses 2,048-pixel
  tile cores, so 2,048² is the last size they run as one tile and 3,000² the
  first they tile: the pair measures that execution crossover. Run it with
  `--tier large` before profiling or a release; it currently takes hours.

The protocol comes from `config/benchmarks/phase-0-performance.json`: one
warm-up and five measured repetitions per case. Every repetition runs the
public finder with the serial executor in a fresh process, limited to one
numerical-library thread, so it includes interpreter start-up, imports, FITS
input and product writing. Inputs above the public 3,000-pixel limit use the
worker's `--diagnostic-size-limit`, which raises the limit only inside that
process.

Each case is compared with two cached baselines, measured once per input and
machine with the same protocol:

- the previous Hebog release, by default the latest `v*` tag in `HEAD`. It is
  installed from the tag with its locked dependencies under
  `benchmark-results/quick-benchmark/releases/`. Use `--previous-release` to
  choose another tag, or `--no-previous-release` to skip it.
- pinned PyBDSF `master` in the quick science check's Podman image with four
  cores. The container worker times itself from input validation to product
  normalisation, so container start-up is excluded. Use `--no-reference` to
  skip it.

The run prints median wall time with its range, both ratios with their
one-sided 95% bootstrap bounds and outcomes, and peak memory; the report also
records median CPU time. Each repetition writes its products to the system
temporary directory, which Spotlight does not index, and deletes them. It writes `report.json` and
one `BenchmarkEvidence` record (`hebog.validation.evidence`) per case under
`benchmark-results/quick-benchmark/runs/<label>/`.

A comparison passes when the upper ratio bound is within the limit, fails
when the lower bound exceeds it, and is otherwise inconclusive. The run exits
non-zero when a case fails or the previous-release comparison fails.

A baseline that cannot be measured, for example a case that needs a feature
the previous release lacks, is cached with its error and does not fail the
run. The report records the error, and the run prints `NOT CHECKED` for each
case without a previous-release comparison; `--refresh-previous-release`
retries it. When a case fails, its time is missing from the Hebog total, so
the report sets `within_budget` to `null` instead of comparing an incomplete
total with the budget.

Cached baselines drift with machine state: the same case can differ by 15%
between sessions. Before acting on a regression whose CPU time did not change,
confirm it with `--refresh-previous-release`, which measures the previous
release again in the same session. The `master` ratio is diagnostic, not the
deployment gate: Hebog runs natively on one thread and PyBDSF runs in a Linux
container with four cores. Only the matched `filter_skymodel` benchmark can
pass or fail that gate.

## Profile complete execution

Profile before optimizing, to choose what to change. The profile splits one
complete run into its public stages and separates the cost of image size from
the cost of sources:

```console
just profile-execution --label <label> --cprofile
just profile-execution --label <label> --cases profile-dense-1024
```

The cases are in `config/benchmarks/complete-execution-profile.json`:

- `ladder`: noise-only and dense generated images at 512², 1,024², 2,048²
  and 4,096², with 256 sources per 1,024² at every size. The manifest
  `config/datasets/complete-execution-profile.json` is rebuilt by
  `scripts/benchmark/build_profile_datasets.py`.
- `real`: the sparse and dense 1,024² LoTSS-DR3 cut-outs and the SDC1 crowded
  cut-out at 512², 1,024² and 2,048², all centred on the same field.

Each case runs once in a fresh single-thread process with the serial
executor, on macOS or Linux: stage timing needs the POSIX `resource` module. The worker wraps the functions of the public path with timers in its
own process, so no Hebog code changes, and records each stage's calls, wall
and CPU time, and the process peak memory when the stage ends. A function
imported into several modules is wrapped in each of them, so a call through an
alias is timed as its own stage instead of vanishing into its caller. Stages
nest: FITS and Zarr reads and writes appear under the stage that made them.
Wall time minus CPU time is mostly file-system wait. `--cprofile` runs each
case a second time under `cProfile` and keeps its statistics and the functions
with the most self time; `cProfile` misses Zarr's I/O thread and slows
Python-heavy code, so stage times come from the first run.

Process time outside the run is split into three measured parts, so no part
of the fixed cost is charged to the wrong one: `module imports`, `other
worker overhead` (temporary-product cleanup and building the result) and
`process creation and shutdown`, which is the time outside the worker script
itself. The worker's clock starts at its first line, so process creation and
interpreter start-up precede it and interpreter shutdown follows it; an
in-process clock cannot separate the two, so they are reported together.
That part also holds the worker's own result write, which no process can
time from inside itself: about 2 ms, bounded by the stage and `cProfile` row
limits rather than by image size.

`summary.json` under `benchmark-results/profiles/runs/<label>/` fits each
top-level stage on the ladder as a fixed cost plus a cost per megapixel and
per fitted component, and compares every real case with that model. A
profile is a single diagnostic run: use the quick benchmark for before and
after timings.

## Develop test-first

For a public behaviour or scientific kernel:

1. Write the smallest analytic, property, contract, or regression test and
   confirm that it fails for the intended reason.
2. Implement the simplest deterministic serial behaviour that passes.
3. Refactor, then add pathological and property-based cases.
4. Prove local and Dask conformance against the serial result.
5. Run scientific equivalence before making a performance claim.

Use analytic truth and mathematical invariants before treating PyBDSF as an
oracle. PyBDSF products establish compatibility; they are not assumed to be
scientific ground truth. Qualification datasets are held out from routine TDD
and used only for milestone or release decisions.

## Read a bounded FITS window

Use the image-source boundary when a worker needs pixels. It validates the
logical plane and brightness unit without materialising the complete image,
then copies only the requested half-open global window into owned memory:

```python
from pathlib import Path

from hebog.io import (
    FitsImageSource,
    ImageBounds,
    celestial_wcs_from_metadata,
)

source = FitsImageSource(Path("image.fits"))
metadata = source.metadata()
height, width = metadata.shape_yx
window = source.read_window(
    ImageBounds(
        y_start=0,
        y_stop=min(512, height),
        x_start=0,
        x_stop=min(512, width),
    )
)

assert window.values.shape == window.bounds.shape_yx
assert window.valid_pixels.shape == window.values.shape
assert window.bounds.y_stop <= metadata.shape_yx[0]
assert metadata.beam.major_fwhm_degrees > 0
assert metadata.reference_frequency_hz > 0
celestial_wcs = celestial_wcs_from_metadata(metadata)
```

The source accepts two-dimensional data and conventional radio-image FITS
layouts whose leading axes are singleton. Non-singleton channel or Stokes
cubes are rejected until their scientific semantics are explicitly supported.
NaN and infinite pixels remain in the values array and are marked false in
`valid_pixels`; kernels must exclude them from scientific calculations. Beam,
celestial-WCS, coordinate-frame, brightness-unit, and reference-frequency
metadata remain small serializable values; live Astropy objects stay at the
I/O boundary.

Plan bounded work independently of the executor. Each tile owns one
non-overlapping core and may read a clipped halo:

```python
from hebog.algorithms.partitioning import plan_image_partitions

manifest = plan_image_partitions(
    image_shape_yx=metadata.shape_yx,
    tile_core_shape_yx=(2048, 2048),
    halo_yx=(128, 128),
)

for tile in manifest.tiles:
    tile_window = source.read_window(tile.read_bounds)
    owned_values = tile_window.values[tile.core_slices_yx]
    assert owned_values.shape == tile.core_bounds.shape_yx
```

Tiles are ordered by `(tile_y_index, tile_x_index)`. Increasing resources may
change batching, but must not change these cores, their ownership, or the
scientific result. `partition_origin_yx` may shift internal grid boundaries
for invariance tests while still assigning every pixel to exactly one core.

## Estimate bounded background and RMS tiles

Configure scientific window geometry separately from executor batching. The
serial executor is the deterministic reference and requires no scheduler:

```python
from hebog.config import (
    BackgroundRmsConfig,
    RmsGridConfig,
    RmsWindowStatisticsConfig,
)
from hebog.executors import SerialExecutor
from hebog.stages.background import (
    estimate_background_rms_grids,
    estimate_background_rms_tile,
    prepare_background_rms_tile_request,
)

statistics = RmsWindowStatisticsConfig(
    clipping_sigma=3.0,
    maximum_iterations=10,
    minimum_samples=6,
)
background_config = BackgroundRmsConfig(
    coarse=RmsGridConfig(
        window_shape_yx=(150, 150),
        step_yx=(50, 50),
        statistics=statistics,
        maximum_batch_cells=64,
    ),
    adaptive=None,
    maximum_spatial_window_fraction=0.25,
    maximum_constant_map_pixels=1_000_000,
)

grids = estimate_background_rms_grids(
    source,
    metadata.shape_yx,
    background_config,
    SerialExecutor(),
    bright_candidate_positions_yx=(),
)

for tile in manifest.tiles:
    request = prepare_background_rms_tile_request(
        tile,
        grids,
        background_config,
    )
    result = estimate_background_rms_tile(source, request)
    assert result.bounds == tile.core_bounds
    assert result.rms.shape == tile.core_bounds.shape_yx
```

Both returned arrays are float64 and read-only. Invalid source pixels are NaN;
`scientifically_available` is false when no input window retained enough
samples. Persist each owned tile directly rather than assembling a complete
large plane.

To refine noise near known bright candidates, add an `AdaptiveRmsConfig` and
pass finite global `(y, x)` candidate positions while preparing the grids.
Tile requests derive their local positions from that immutable grid result, so
callers cannot accidentally omit a previously estimated region. Only merged
local fine-grid regions are estimated.

Use a caller-owned Dask client when coarse batches should run remotely:

```python
from hebog.executors import DaskExecutor

dask_executor = DaskExecutor(existing_client)
```

Hebog never starts or closes that client. Serial and Dask results obey the
same contract; client lifecycle and the top-level graph remain with the
workflow.

## Choose and bound an executor

Three executors satisfy one contract: `SerialExecutor` is the deterministic
reference, `ThreadExecutor` runs one caller-owned persistent thread pool in
this process, and `DaskExecutor` submits to a caller-owned client. Hebog never
creates a cluster or a pool of its own, and a task never nests one.

```python
from hebog.executors import ThreadExecutor

with ThreadExecutor(thread_count=4) as executor:
    results = executor.map_batches(estimate_tile, tiles)
```

Every executor obeys the same rules, so a defect appears on the serial
reference rather than only on a cluster:

- results follow input order, whatever order batches complete in;
- submission stays within `capacity.maximum_tasks_in_flight`, and a failure
  cancels the rest of the plan instead of running it;
- the first failing batch by input index is the error that propagates;
- payloads must be serializable, which every executor checks before it
  submits anything, so a lambda or an open file fails immediately;
- tasks must be idempotent, because a `retry_limit` above zero repeats one
  that fails.

Declare what a task needs, and admission refuses an impossible plan before any
work starts:

```python
from hebog.executors import TaskRequirement

executor.map_batches(
    estimate_tile,
    tiles,
    requirement=TaskRequirement(memory_bytes=512 * 1024**2, threads=1),
)
```

`executor.capacity` reports the budget the caller admitted. `DaskExecutor`
reads it from the client's own cluster unless the caller declares one.
Admission proves that one task fits one worker, and a declared requirement
narrows how many tasks run at once: a large working set reduces the window to
what the admitted memory holds, and a task claiming several threads occupies
several slots. Narrowing never widens the caller's bound and changes
scheduling only, never ownership or results.

That window bounds concurrency across the whole admitted budget, not on any
one worker. Hebog does not pin tasks to workers, so a distributed scheduler
may still place several admitted tasks on the same worker; per-worker safety
then rests on the worker memory limits and spill thresholds the caller
configured. Hebog deliberately attaches no Dask `resources` annotations,
because a cluster whose workers declare no matching resource would never run
the task at all.

Use `reduce_batches` when the driver must not hold one result per batch. It
maps batches and combines them in a tree fixed by input index, so the value,
including floating-point summation, does not depend on completion order, and
only one accumulator per tree level is held:

```python
merged = executor.reduce_batches(summarise_tile, tiles, merge_summaries)
```

`DaskExecutor` runs those combines on workers and gathers one value. The
combine must be deterministic; it need not be commutative or associative.

## Publish retryable product chunks

Publish intermediate image planes as independent tile-owned chunks in one
Zarr v3 group. Create each product array on the caller before workers start so
workers never race metadata creation:

```python
from pathlib import Path

import numpy as np

from hebog.io import ZarrProductSink

sink = ZarrProductSink(
    Path("work/run.zarr"),
    manifest,
    generation_id="run-001",
)
sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

chunks = []
for tile in manifest.tiles:
    tile_window = source.read_window(tile.read_bounds)
    chunk = sink.write_chunk(
        product_name="rms",
        tile=tile,
        values=tile_window.values[tile.core_slices_yx],
    )
    chunks.append(chunk)

restored = sink.read_chunk(chunks[0])
assert restored.shape == chunks[0].shape_yx

completed = sink.publish_generation(
    product_names=("rms",),
    chunks=chunks,
)
assert sink.read_generation() == completed
```

`ProductChunk` is a small serializable identity containing the generation ID,
global core bounds, dtype, shape, and logical content SHA-256; it does not
contain an open Zarr object or pixel payload. Identical retries reuse a
completed chunk, while a different value for the same product and tile fails
closed.

`publish_generation` first requires exactly one record for every requested
product and canonical tile. It rejects missing, duplicate, conflicting,
mixed-generation, wrong-owner, and inconsistent-dtype records, then reads and
checksums every referenced Zarr chunk. Only after those checks pass does it
conditionally create the canonical completion marker. Identical publication
retries are idempotent; a different marker cannot replace the winner. An
interrupted run has no marker and resumes by writing only its missing chunks.
Consumers call `read_generation`, which validates the marker and its chunks
again before returning them.

Stream a completed product into final FITS without materialising the complete
plane. Admit enough memory for one full-width canonical tile row:

```python
from hebog.io import write_rms_fits_product

row_budget = (
    manifest.tile_core_shape_yx[0]
    * manifest.image_shape_yx[1]
    * 8  # float64 bytes per value
)
final_rms = write_rms_fits_product(
    Path("products/rms.fits"),
    metadata,
    sink.iter_completed_row_blocks(
        "rms",
        max_block_bytes=row_budget,
    ),
    dtype=np.dtype("<f8"),
    scientific_status="valid",
)
```

The iterator validates each referenced chunk exactly once and yields tile rows
in FITS row order. A multi-tile row uses one C-contiguous assembly block plus
one current decoded chunk. A one-tile image yields its already owned validated
chunk directly and avoids an assembly copy. A budget below one canonical tile
row fails before product bytes are emitted.

Generation-bound chunks use internal storage schema version 3. Recreate any
unpublished development store written with schema version 1 or 2; no released
Hebog workflow product used either schema. Numeric planes use CRC32C without
compression; boolean masks use Zstandard level 1 plus CRC32C.

The current adapter requires a zero-origin partition whose complete cores
align with regular storage chunks. It explicitly writes fill-valued chunks,
uses Zarr 3.2's strict missing-chunk reads, validates CRC32C and logical
SHA-256, and rejects sequential conflicting retries. Consumers must still wait
for the deployment-store atomicity and performance gates in
[ADR-007](../architecture/adr/007-use-zarr-for-intermediate-image-storage.md).
Zarr is the only intermediate image-plane backend. Small inputs use one Zarr
chunk and serial execution; FITS remains an input and final compatibility
format rather than an alternative intermediate store.

## Keep changes maintainable and reusable

Start a vertical slice at the public behaviour, then keep scientific kernels
independent of workflow and scheduler details. Pass I/O, execution, and
configuration explicitly; put Rapthor/LSMTool names and product translations
in the compatibility adapter.

Prefer a function, dataclass, context manager, or narrow structural protocol
to an inheritance hierarchy or generic plugin registry. Add a new extension
seam only when a second implementation or workflow test demonstrates the
variation. Run `just check` while iterating and preserve the branch-aware 80%
coverage floor with meaningful normal, edge, and failure tests.

Use the [quality attributes and coding principles](../explanation/quality-attributes.md)
and [code review guide](https://github.com/gemmadanks/hebog/blob/main/CODE_REVIEW.md)
for the complete requirements.

## Describe acceptance behaviour

Use readable pytest scenarios for behaviour that crosses Hebog, materialised
products, Dask, and Rapthor. Given/When/Then test names or docstrings are
enough initially. A dedicated BDD framework should be introduced only if
domain experts will actively review or write feature files.

## Record a benchmark

Benchmark runs must record the dataset identifier and checksum, Hebog,
Rapthor, released PyBDSF, and PyBDSF `master` revisions, dependency versions,
configuration, worker topology, CPU allocation, wall and CPU time, peak
resident memory, and Dask task/transfer/spill metrics. The deployment gate
uses pinned PyBDSF `master` (`c70103b`) in a matched environment. Released
PyBDSF 1.14.1 is compared once before 1.0.0, as the plan describes; never
substitute a different revision for either.

Use one warm-up and at least five measured repetitions. Store generated
results under the ignored `benchmark-results/` directory and commit only small
reviewed summaries with reproduction commands.

Construct and write runs with `hebog.validation.evidence.BenchmarkEvidence`
and `write_evidence`. Use `null` plus an explicit `unavailable_metrics` reason
when instrumentation is genuinely unavailable; never substitute zero. Mark a
document `reviewed` only when its protocol and environment have passed review.

Use the complete frozen ladder in the
[performance contract](../reference/performance-scalability-contracts.md),
plus cases immediately below and above each observed executor, storage,
partition, or batching crossover. Include
empty or sparse, normal, and dense or extended workloads. Compare every size
with the previous reviewed Hebog baseline and with pinned PyBDSF `master`;
never report only the most favourable size or execution mode.

For a scalability run, additionally record the logical image and plane sizes,
tile cores and stage-specific halos, partition count, storage layout, worker
nodes and processes, node/worker RAM, admitted memory and reserved headroom,
scheduler load, worker occupancy, boundary-summary and transfer volumes,
spill, storage throughput, retries, and stragglers. Report
every measured node count (1, 2, 5 and 10 in the final cluster benchmark),
including strong- and weak-scaling efficiency; do not retain only the best
topology.

## Work with notebooks

See [Use the notebooks and refresh comparisons](notebooks.md) for the notebook
index, input downloads, output locations, comparison refreshes and execution
checks. Start with `uv run marimo edit notebooks/source_finder_demo.py`.
