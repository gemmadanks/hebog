# Integrate Hebog into a pipeline

This guide is for developers who call Hebog from a workflow such as a Prefect
flow, a Dask graph or a batch script. It assumes no radio astronomy
background. For the design behind these steps, read
[How Hebog distributes work](../architecture/distributed-execution.md).

Hebog is experimental. Pin an exact version and read
[capability and status](../reference/release-status.md) before relying on it.

## The contract in brief

```python
result = hebog.find_sources(request, config, executor)
```

| Argument or result | What it is | Safe to serialize |
| --- | --- | --- |
| `SourceFinderRequest` | Input path, output directory, run identifier | yes |
| `SourceFinderConfig` | Immutable scientific settings | yes |
| executor | Where work runs; owned by you | no, create it in the calling process |
| `SourceFinderResult` | Counts, timing, and four product records with path, size and SHA-256 | yes |

The call reads one FITS image and publishes one directory of four files. It
holds no global state, starts no cluster and leaves no open files. Importing
`hebog` does not import Dask.

## 1. Choose an executor

```python
from hebog.executors import DaskExecutor, SerialExecutor, ThreadExecutor

# the reference, in one process
executor = SerialExecutor()
# one process, used as a context manager
executor = ThreadExecutor(thread_count=4)
# your existing dask.distributed client
executor = DaskExecutor(client, retry_limit=1)
```

All three produce the same products. Hebog never creates, resizes or closes
your client. If `find_sources` is itself a task in your graph, give it a
client through your framework's usual mechanism; do not let Hebog tasks nest a
second cluster.

Optionally declare the budget Hebog may use. Without it, `DaskExecutor` reads
the cluster's current size:

```python
from hebog.executors import ExecutorCapacity

executor = DaskExecutor(
    client,
    capacity=ExecutorCapacity(
        worker_count=8,
        threads_per_worker=1,
        maximum_tasks_in_flight=16,
        memory_bytes_per_worker=32 * 1024**3,
    ),
)
```

`maximum_tasks_in_flight` bounds how many tasks are submitted at once.
Every Hebog task also declares the memory it holds, so Hebog narrows that
bound until the tasks in flight fit `memory_bytes_per_worker` on
`worker_count` workers, and refuses a task larger than one worker's memory
before anything runs. A `ThreadExecutor` takes the same budget:
`ThreadExecutor(4, memory_bytes_per_worker=8 * 1024**3)`.

On a cluster, name Dask worker resources so that Dask itself keeps each
worker within its memory:

```bash
dask worker tcp://scheduler:8786 --nthreads 4 --resources "memory=16e9,cores=4"
```

```python
executor = DaskExecutor(client, memory_resource="memory", core_resource="cores")
```

Each task then requests its declared bytes of `memory` and its one thread
of `cores`, and Dask starts it only on a worker with that much of both
still free. The names are yours, so they can match resources your own
tasks already request. Hebog reads the workers' amounts as its budget, and
refuses to start when no worker declares them, since Dask would otherwise
hold the tasks forever. Hebog does not pin tasks to workers; spill policy
stays under your control.

Reserve memory for the analysis itself too. `find_sources` holds Hebog's
modules and the records every pass keeps for each source in the process
that calls it, so what it holds grows with the sources it finds, about
40 KB each, rather than with the image. `hebog.analysis_memory_bytes` states
how much for an upper estimate of the source count, which
`hebog.expected_source_count` makes from the image at your detection
threshold, reading it in bounded blocks. A deconvolution model's component
list is no such estimate: it holds many components for each source. When
`find_sources` runs inside a Dask task, request it there:

```python
import hebog

expected = hebog.expected_source_count(image_path, detection_threshold_sigma=5.0)
reserve = hebog.analysis_memory_bytes((20_000, 20_000), expected_sources=expected)
client.submit(run_finder, request, resources={"memory": reserve, "cores": 1})
```

With a serial or thread executor the tasks run in the calling process, so
reserve their admitted memory on top.

## 2. Put files where workers can reach them

Workers open the input image themselves and write intermediate Zarr planes
beside the output directory. On a multi-node cluster, use absolute paths on
storage that every worker can read and write. Set numerical-library thread
counts (`OMP_NUM_THREADS` and similar) so that worker threads are not
oversubscribed.

## 3. Treat the output directory as one atomic product

- The output directory must not exist, unless it holds the finished
  products of the same request: the same run ID, inputs, configuration and
  Hebog science. Then `find_sources` returns them without analysing the
  image again, so a task retried after the finder returned resumes at once.
  For any other existing path Hebog raises `SourceFinderOutputExistsError`
  instead of overwriting.
- Products are written to a private sibling directory, validated, and moved
  into place with one rename. A successful return, not the existence of the
  directory, means the products are ready.
- After a failure the output directory is absent, so the same request can be
  retried. Use a new `output_directory` per attempt if your framework keeps
  failed attempts.
- A failed run raises only once none of its tasks is still running, and
  leaves nothing beside the output. A killed process leaves its hidden
  staging directory; the next run to the same output removes it once that
  process has provably stopped, and reports every one it finds with a
  `SourceFinderStagingWarning`. A run to another output does not look, so
  if you retry under a new `output_directory`, remove a killed attempt's
  hidden directory yourself. Tasks a killed process left on your Dask
  cluster keep running; let them finish, or restart the workers, before
  retrying. See
  [what a failed or killed run leaves](../reference/public-products.md#what-a-failed-or-killed-run-leaves).

## 4. Handle errors by type

| Exception | Meaning | Typical response |
| --- | --- | --- |
| `InvalidSourceFinderInputError` | Missing, unreadable, truncated or malformed FITS input, including a header that lacks a unit, beam or frequency the request does not supply | fix the file or supply the metadata, see the [tutorial](../tutorials/find-sources.md#prepare-the-input); do not retry unchanged |
| `UnsupportedSourceFinderConfigurationError` | Readable file, but a unit other than `Jy/beam`, an unsupported coordinate frame, or a beam wider than 10 pixels | convert or regrid the image; see the [input header contract](../reference/input-header-contract.md) |
| `SourceFinderImageTooLargeError` | Image exceeds a current size limit | cut the image or wait for a later release |
| `SourceFinderOutputExistsError` | Output directory exists and does not hold this request's finished products | choose a new directory |

All derive from `SourceFinderError`. An image with no detectable sources is
**not** an error: it returns an empty catalogue.

## 5. Persist and verify results

Store the whole `SourceFinderResult`, not only the paths. Each product record
carries its role, byte count, SHA-256 and schema version. Pass the record to a
Hebog reader and it verifies these before parsing:

```python
from hebog.io import read_catalogue_fits_product, read_diagnostics_product

catalogue = read_catalogue_fits_product(result.catalogue)
diagnostics = read_diagnostics_product(result.diagnostics)
```

Check `scientific_status` on each product. The RMS product is `unavailable`
when the image had no usable noise estimate; downstream steps must not treat
that as "no sources exist". See the
[integration checklist](../reference/public-products.md#integration-checklist-for-developers).

## What Hebog does not do

Hebog analyses one image. Your pipeline remains responsible for:

- scheduling, retries across tasks and resource admission;
- combining several images, apart from a field's flat-noise image, whose
  RMS one run publishes beside the primary-beam-corrected image's products;
- filtering or grouping an existing sky model with the mask; and
- translating products into another tool's file names or column conventions.

For Rapthor, `hebog.adapters.find_sector_sources` writes Rapthor's file names
and catalogue columns, and LSMTool's `filter_sources` filters and groups the
sky model with the island mask; see the
[Rapthor source-finding contract](../reference/rapthor-source-finding-contract.md#how-hebog-runs-inside-rapthor).
The [guide to Rapthor's Hebog branch](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/rapthor-integration/README.md)
and its container show how to install and test `source_finder = hebog` on
Rapthor's current single-task worker layout. It runs the caller-owned ThreadExecutor inside
the Prefect task, admits memory, and retains the PyBDSF fallback. Set
`hebog_dual_run = True` to retain both filtered product sets and place their
comparison in ordinary image diagnostics. The branch is not yet merged
into Rapthor. The adapter and the branch's parset default to the
`continuum` profile with a zero background, which passes the truth-based
gate where `compact` does not; it is not yet a qualified Rapthor profile,
and a distributed Hebog subgraph needs the later worker-layout change.

## Versioning

Hebog makes no compatibility promise between `0.x` releases. Output schemas
are versioned and readers reject versions they do not support, so an upgrade
fails loudly rather than misreading old files. Pin the version, read the
[release notes](https://github.com/gemmadanks/hebog/releases), and preserve
quality flags you do not recognise.
