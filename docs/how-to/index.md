# Development workflows

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
Contract tests hold strict-xfail executable specifications until their planned
implementation turns them green; an unexpected pass fails CI until the test is
reviewed and converted to a normal assertion. Integration tests cover Dask,
FITS, and Rapthor boundaries. Equivalence tests
compare small redistributable cases with frozen PyBDSF products. Acceptance
tests describe Rapthor-facing behaviour. Qualification, benchmark, and
scalability tests require controlled resources or approved data and are never
implied by the quick suite.

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

## Publish retryable product chunks

Publish large intermediate planes as independent tile-owned cores. The
filesystem sink returns a small serializable record containing the canonical
relative path, global core bounds, dtype, shape, byte size, and SHA-256:

```python
from pathlib import Path

from hebog.io import FilesystemProductSink

sink = FilesystemProductSink(Path("work/products"))
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
```

Publication uses a flushed private partial file and an atomic same-directory
hard link. A final path is therefore never visible with partial bytes.
Identical retries reuse the published chunk without changing it; a retry that
produces different bytes for the same product and tile fails closed. A worker
failure before publication leaves no final path, while a lost response after
publication is recovered by the next identical retry.

All workers using this sink must see the same caller-owned filesystem, and it
must support atomic hard links. Private `*.partial` files are not products and
may be removed by run-level cleanup only after no writers remain. These NumPy
chunks are internal restart artifacts; later compatibility materialisation
creates the versioned FITS, mask, RMS, and catalogue products consumed by
Rapthor or another workflow.

For the gated distributed-store prototype, pre-create each Zarr v3 plane on
the caller before submitting tile writes:

```python
from pathlib import Path

import numpy as np

from hebog.io import ZarrProductSink

zarr_sink = ZarrProductSink(Path("work/run.zarr"), manifest)
zarr_sink.initialize_product(product_name="rms", dtype=np.dtype("<f8"))

zarr_chunks = []
for tile in manifest.tiles:
    tile_window = source.read_window(tile.read_bounds)
    zarr_chunks.append(
        zarr_sink.write_chunk(
            product_name="rms",
            tile=tile,
            values=tile_window.values[tile.core_slices_yx],
        )
    )
```

The current Zarr adapter requires a zero-origin partition whose complete cores
align with regular storage chunks. It explicitly writes fill-valued chunks,
checks missing standard v3 chunk keys, validates CRC32C and logical SHA-256,
and rejects sequential conflicting retries. It is a Phase 1 prototype, not a
published generation: consumers must wait for the completion-manifest and
deployment-store gates in
[ADR-007](../architecture/adr/007-use-a-gated-zarr-intermediate-store.md).
The NumPy-file and future direct-FITS paths remain valid for tiers where they
measure faster with the same product semantics.

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
resident memory, and Dask task/transfer/spill metrics. Run the exact PyBDSF
references in separate matched environments and report both comparisons; do
not substitute `master` for Rapthor's released runtime.

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
with the previous reviewed Hebog baseline and, wherever both references can
run, with released PyBDSF and pinned PyBDSF `master`; never report only the
most favourable size or execution mode.

For a scalability run, additionally record the logical image and plane sizes,
tile cores and stage-specific halos, partition count, storage layout, worker
nodes and processes, node/worker RAM, admitted memory and reserved headroom,
scheduler load, worker occupancy, boundary-summary and transfer volumes,
spill, storage throughput, retries, and stragglers. Report
the full 1/10/50/100/200-plus-node matrix, including strong- and weak-scaling
efficiency; do not retain only the best topology.

## Work with notebooks

Marimo provides reviewable, Python-based demonstrations. Edit the source-finder
notebook with:

```console
uv run marimo edit notebooks/source_finder_demo.py
```

Validate all notebooks without starting the interactive editor:

```console
just marimo-check
```
