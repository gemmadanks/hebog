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

executor = SerialExecutor()                     # reference, single process
executor = ThreadExecutor(thread_count=4)       # one process, use as a context manager
executor = DaskExecutor(client, retry_limit=1)  # your existing dask.distributed client
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

Hebog bounds how many tasks are in flight but does not pin tasks to workers
and adds no Dask resource annotations. Per-worker memory limits and spill
policy stay under your control.

## 2. Put files where workers can reach them

Workers open the input image themselves and write intermediate Zarr planes
beside the output directory. On a multi-node cluster, use absolute paths on
storage that every worker can read and write. Set numerical-library thread
counts (`OMP_NUM_THREADS` and similar) so that worker threads are not
oversubscribed.

## 3. Treat the output directory as one atomic product

- The output directory must not exist. Hebog raises
  `SourceFinderOutputExistsError` instead of overwriting.
- Products are written to a private sibling directory, validated, and moved
  into place with one rename. A successful return, not the existence of the
  directory, means the products are ready.
- After a failure the output directory is absent, so the same request can be
  retried. Use a new `output_directory` per attempt if your framework keeps
  failed attempts.

## 4. Handle errors by type

| Exception | Meaning | Typical response |
| --- | --- | --- |
| `InvalidSourceFinderInputError` | Missing, unreadable or malformed FITS input | fail the task; do not retry |
| `UnsupportedSourceFinderConfigurationError` | Valid file, but unsupported units, coordinate frame, beam or frequency metadata | fix or supply metadata, see the [tutorial](../tutorials/find-sources.md#prepare-the-input) |
| `SourceFinderImageTooLargeError` | Image exceeds the current size limit | cut the image or wait for a later release |
| `SourceFinderOutputExistsError` | Output directory already exists | choose a new directory |

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
- combining several images, for example primary-beam-corrected and flat-noise
  versions of the same field;
- filtering or grouping an existing sky model with the mask; and
- translating products into another tool's file names or column conventions.

A Rapthor-specific adapter for the last two items is planned but not yet
implemented; see the
[Rapthor source-finding contract](../reference/rapthor-source-finding-contract.md).

## Versioning

Hebog makes no compatibility promise between `0.x` releases. Output schemas
are versioned and readers reject versions they do not support, so an upgrade
fails loudly rather than misreading old files. Pin the version, read the
[release notes](https://github.com/gemmadanks/hebog/releases), and preserve
quality flags you do not recognise.
