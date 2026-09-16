# Development workflows

For a short introduction to the project's algorithms, decisions and testing
process, read [how Hebog has been developed](../explanation/development-history.md).

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
frozen expected products in a test. Closed Phase 5 campaign archive checks were
removed with that campaign tooling and remain in Git history.

Select data-dependent checks explicitly on a host that holds the data; do not
enable every controlled test lane just to validate a checkout.
Use synthetic temporary records for ordinary checksum, malformed-input,
serialization and write-once tests. A pass with local `benchmark-results/`
present does not establish CI portability: also run the quick lane from a clean
checkout without those ignored products.

Keep inexpensive protocol and write-once safety tests in portable CI while
their builders or readers remain maintained. Completing a campaign does not
remove the need to detect changed seeds, references, gates or authorization.
Compare recomputed floating-point planning results with an explicit round-off
tolerance; frozen artifact bytes and their recorded hashes still require exact
equality. Retire obsolete campaign builders and their implementation-specific
tests together after checking remaining consumers, preserving evidence and the
identity checks needed by supported readers.

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
the finder settings in `config/comparisons/notebook-comparison.json`, and the
core count. Changing any of these reruns the reference, and a cached failure
applies only to the identity that failed. Remote cut-outs are accepted only
when the server returns exactly the requested bytes.
Generated inputs are materialised on first use. The SDC1 cut-outs are cut
from a local copy of `SKAMid_B2_1000h_v3.fits`. Missing real cut-outs are
fetched with HTTP range requests only when `--allow-download` is given. Use
`--cases` to run a subset while iterating.

This is a regression detector, not powered scientific parity. Each case is
one realization and no confidence interval is claimed.

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
Automatic bright-candidate discovery and the Rapthor configuration adapter are
not yet public Phase 2 capabilities.

Use a caller-owned Dask client when coarse batches should run remotely:

```python
from hebog.executors import DaskExecutor

dask_executor = DaskExecutor(existing_client)
```

Hebog never starts or closes that client. Serial and Dask results obey the
same contract; client lifecycle and the top-level graph remain with the
workflow.

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
