# Choose thresholds, a profile and an executor

This guide assumes you have completed the
[tutorial](../tutorials/find-sources.md).

## Set detection thresholds

```python
config = hebog.SourceFinderConfig(
    detection_threshold_sigma=6.0,
    island_threshold_sigma=4.0,
    minimum_island_pixels=10,
    maximum_island_pixels=None,
)
```

| Setting | Meaning | PyBDSF equivalent |
| --- | --- | --- |
| `detection_threshold_sigma` | An island must contain evidence at this signal-to-noise ratio | `thresh_pix` |
| `island_threshold_sigma` | Islands grow to this lower level; must be below the detection threshold | `thresh_isl` |
| `minimum_island_pixels` | Smallest island kept | `minpix_isl` |
| `maximum_island_pixels` | Optional largest island kept | — |

Raise the detection threshold for fewer false detections; lower it for
completeness at the cost of reliability. The same values are used throughout
background protection, direct and multiscale detection, and the final size
filter.

All other algorithm settings, such as noise-grid sizes, wavelet scales and
fitting bounds, are fixed by the selected profile so that results are
reproducible. Every configuration is labelled `development-unqualified` or
`custom-unqualified` in the diagnostics until Hebog is qualified.

## Choose a profile

| Profile | Use it for | Behaviour |
| --- | --- | --- |
| `continuum` (default) | General continuum images, including extended emission | Finer RMS grid near bright sources; associates components into multi-component sources; source flux from apertures |
| `compact` | Fields of unresolved or barely resolved sources, where you want one source per Gaussian | No extended-source association; each source carries its Gaussian measurement; diagnostics declare `extended-emission-incomplete` |

```python
config = hebog.SourceFinderConfig(
    detection_threshold_sigma=5.0,
    island_threshold_sigma=3.0,
    minimum_island_pixels=7,
    profile="compact",
)
```

Do not present a `compact` catalogue as a general continuum-source catalogue.

## Use several cores or a Dask cluster

The third argument of `find_sources` decides where the work runs. The
products are the same in every case.

```python
from hebog.executors import DaskExecutor, SerialExecutor, ThreadExecutor

result = hebog.find_sources(request, config, SerialExecutor())

with ThreadExecutor(thread_count=4) as executor:
    result = hebog.find_sources(request, config, executor)

from dask.distributed import Client

with Client("tcp://scheduler:8786") as client:
    result = hebog.find_sources(request, config, DaskExecutor(client))
```

Hebog never starts a cluster for you. On a multi-node cluster, the image and
the parent of the output directory must be on storage that every worker sees
at the same absolute path. Today's limit is 3,000 pixels per side. Background
and RMS estimation tiles at every size, but every other stage uses 2,048-pixel
cores, so an image up to 2,048 pixels gives those stages a single tile and
little to parallelise; above that they tile too.
[Integrate Hebog into a pipeline](integrate-into-a-pipeline.md) has the
details.

## Re-run or retry

- A failed run leaves no output directory. Run the same request again.
- An existing output directory raises `hebog.SourceFinderOutputExistsError`.
  Remove or rename it yourself, or choose another directory; Hebog never
  deletes your files.
- To repeat a result exactly, pin the Hebog version and compare
  `diagnostics.provenance`, which records checksums of the input, the
  configuration and the implementation.
