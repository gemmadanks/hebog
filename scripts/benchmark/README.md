# Benchmark scripts

This directory contains reproducible benchmark entry points for:

- PyBDSF reference runs;
- Hebog using serial, threaded, and Dask executors;
- Rapthor's complete `filter_skymodel` task.

Every result must record the dataset identifier, git revisions, configuration,
Python and dependency versions, worker topology, CPU allocation, wall time,
CPU time, and peak resident memory. Generated results belong in the ignored
`benchmark-results/` directory.

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
