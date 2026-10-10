# Rapthor source-finding contract

This inventory records the behaviour Rapthor consumes from its
source-finding step, traced at these revisions on 9 October 2026:

| Component | Revision | Role |
| --- | --- | --- |
| Rapthor | `main` at `c6196cb4` (the Prefect/Dask merge of 9 October 2026) | Schedules the step; `master` is the CWL/Toil release line and not a target |
| LSMTool | `master` at `9bac2f7` (v1.9.0 plus 15 commits) | Runs the finder and filters the sky model |
| PyBDSF | `master` at `c70103b` | The binding scientific and performance reference |

The pins move forward only at the points the plan names: before the
Rapthor patch (task 20), before the matched benchmarks (task 23) and at the
freeze (task 28). The page fixes what must be tested without requiring
Hebog to copy PyBDSF internals, and a compatibility observation here is not
a scientific endorsement.

## Invocation boundary

Rapthor schedules one Prefect `filter_skymodel` task per image sector after
WSClean has written its image and source-list products. The task runs on
Rapthor's Dask task runner (`local_dask`, or `external_dask` on a cluster
whose workers run one task each with `--nthreads 1`), but does no science
itself: it starts a fresh Python interpreter
(`python -m rapthor.execution.image.skymodel_filter_cli`) with
`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS` and
`BLIS_NUM_THREADS` set to 1, so that native thread pools do not multiply
the finder's own parallelism. That interpreter calls LSMTool's
`filter_skymodel(..., source_finder=..., ncores=...)`, which dispatches
through its `KNOWN_SOURCE_FINDERS` registry: `bdsf`, plus `sofia` when its
optional extra is installed. `ncores` is the parset's
`filter_skymodel_ncores` (default 15; 0 means `max_threads`), and PyBDSF
uses it as its count of fitting processes. No Dask client is in reach of
the finder. The task returns serializable file records, and image
diagnostics run as a separate dependent task.

A registry backend, the route this step offers today, takes the `bdsf`
backend's arguments: the two images, the two input sky models,
the two output sky-model paths, `vertices_file`, `beam_ms`,
`input_bright_skymodel`, the thresholds and RMS options below, `keep_mask`,
`output_catalog`, `output_flat_noise_rms`, `output_true_rms` and `ncores`,
returning the source count. (The registry calls every backend with those
arguments; `sofia`'s function takes fewer and could not be called that
way at `9bac2f7`.) Rapthor will instead call Hebog from a native task; see
[How Hebog runs inside Rapthor](#how-hebog-runs-inside-rapthor).

| Input | Meaning |
| --- | --- |
| Flat-noise image | The primary-beam-uncorrected FITS image, with comparatively flat noise |
| True-sky image | The primary-beam-corrected FITS image used for intrinsic fluxes; not literal truth |
| True-sky sky model | WSClean component list with true-sky fluxes; optional when absent |
| Apparent-sky sky model | WSClean component list with beam-attenuated fluxes; optional when absent |
| Bright true-sky sky model | Optional peeled bright components added back before filtering |
| Sector vertices | NumPy polygon file defining the valid imaging sector |
| Beam Measurement Sets | Observation paths used to select a representative beam attenuation |
| Configuration | Thresholds, RMS boxes, adaptive threshold, mask-filter flag, source finder and core count |

Rapthor passes strategy thresholds explicitly, so the helper fallback is not
the production profile:

| Context | Detection threshold | Island threshold |
| --- | ---: | ---: |
| Normal imaging, later self-calibration and the retained Prefect demo | `5.0` sigma | `3.0` sigma |
| Initial/normalization and early self-calibration cycles | `5.0` sigma | `4.0` sigma |
| `filter_image_skymodel` helper fallback | `7.5` sigma | `5.0` sigma |

## What LSMTool asks of PyBDSF, and what Hebog does instead

LSMTool's `bdsf` backend calls `bdsf.process_image` on the true-sky image
(the flat-noise image when no beam Measurement Set is given) with the
options below, and a second time on the flat-noise image with the same
options and `stop_at="isl"`. Rapthor passes the thresholds, `ncores`,
`keep_mask=True` and the RMS options at its own defaults, which equal
LSMTool's; the rest are LSMTool's.

| PyBDSF behaviour | Value | Hebog | Status |
| --- | --- | --- | --- |
| `mean_map` | `"zero"`: no background is subtracted | A background is estimated on the same meshes and subtracted | **Gap.** A real difference; near zero on the images Rapthor makes. Task 18 decides whether the Rapthor profile keeps a zero background |
| `rms_map`, `rms_box` | On, `(150, 50)` | The coarse RMS grid is 150-pixel windows on a 50-pixel step | Implemented |
| `adaptive_rms_box`, `rms_box_bright`, `adaptive_thresh` | On, `(35, 7)`, `75.0` | Bright-region refinement on 35-pixel windows on a 7-pixel step around candidates at 75σ or more, plus local-noise refinement on the same windows everywhere | Implemented, with two bounded differences: the `continuum` RMS tail (task 49) and a clipped RMS 1.6 to 3.9% low on noise alone (task 68) |
| `thresh`, `thresh_pix`, `thresh_isl` | `"hard"`; Rapthor's 5/3, 5/4 or the helper's 7.5/5 | `SourceFinderConfig`'s detection and island thresholds, executed exactly | Implemented |
| `atrous_do`, `atrous_jmax` | On, 3 scales | Three residual multiscale scales in `continuum`; `compact` omits them | Implemented as Hebog's own multiscale association, not PyBDSF's wavelet decomposition |
| Catalogue | `write_catalog(format="fits", catalog_type="srl", force_output=True)` | `catalogue.fits`; the eight-column view Rapthor reads ([Rapthor catalogue view](rapthor-catalogue-view.md)) | Implemented; the adapter writes it under Rapthor's name (task 19) |
| True-sky RMS | `export_image(img_type="rms")` | `rms.fits` | Implemented |
| Island mask | `export_image(img_type="island_mask")` as `<image>.mask.fits` | `source-mask.fits`, the publication support | Implemented, with a bounded difference: about 92% of PyBDSF's island pixels (task 49). LSMTool groups components into patches by the mask's islands, so the mask's connectivity, not only its coverage, reaches the sky model (task 21 measures it) |
| Flat-noise RMS | A second pass with `stop_at="isl"`, RMS only | — | **Gap**: task 18's flat-noise branch |
| Source count | `img.nsrc` | `SourceFinderResult.source_count` | Implemented |
| All pixels blanked | `RuntimeError("All pixels in the image are blanked.")` from `collapse.py` | An empty catalogue, an all-NaN RMS and a zero mask, without an error | **Gap**: the adapter must raise that error or write the products Rapthor writes for it (task 19) |
| Reference frequency | The frequency axis at the image plane, then `RESTFREQ`, then a `FREQ` keyword | The frequency axis at the image plane, then `RESTFRQ`, then `RESTFREQ`; a supplied value when the header has none | Implemented (task 16). Hebog also reads the standard `RESTFRQ`, which PyBDSF ignores, and refuses rather than reads a non-standard `FREQ` keyword |
| `ncores` | Fitting processes | The cores the Dask worker declares, used by the thread executor or by each Dask task's threads (see below) | Task 72 |

`RapthorCompatibilityConfig` holds only what the finder can honour: the
`SourceFinderConfig` thresholds and LSMTool's `filter_by_mask`. The other
options are fixed by Hebog's reviewed science.

## Sector image sizes

Rapthor sizes each sector from its polygon at `cellsize_arcsec`
(default 1.5″). With no grid width set, one sector covers 1.7 times the
primary-beam FWHM, which Rapthor computes as 1.1 λ/D over the sine of the
mean elevation from the first antenna's dish diameter.

| Configuration | Sector size | Source |
| --- | --- | --- |
| Default, LOFAR HBA near 144 MHz | about 17,000 to 20,000 pixels a side, depending on elevation | Rapthor `main`'s sizing rule |
| Rapthor's Prefect demonstration strategy (1.25°, 1.5″) | 3,000 × 3,000 | `examples/prefect_demo_strategy.py` and its parset |
| The ical benchmark runs on the development cluster (10° at 2″) | 18,000 × 18,000, and a 17,060 × 20,428 full-field image | Rapthor logs of September 2026 |

PyBDSF's `filter_skymodel` command took between 298 and 2,955 s per
18,000² sector in one three-node benchmark run (16 and 17 September 2026).
The default and benchmarked sector sizes exceed Hebog's 15,402-pixel
envelope; the plan's task 22 freezes the deployment envelope from them.

## Materialised products

Rapthor requires the catalogue, RMS images, filtered models and diagnostics
for every successful sector; the mask is returned only when its file exists.

| Product | Current suffix | Downstream use |
| --- | --- | --- |
| Filtered true-sky model | `.true_sky.txt` | Calibration and true-flux sky-model state |
| Filtered apparent-sky model | `.apparent_sky.txt` | Beam-attenuated prediction/model state |
| True-sky RMS image | `.true_sky_rms.fits` | RMS statistics and true-sky dynamic range |
| Flat-noise RMS image | `.flat_noise_rms.fits` | RMS statistics, local dynamic range and facet diagnostics |
| Source catalogue | `.source_catalog.fits` | Source count, photometry, astrometry and preview selection |
| Island mask | `<basename of the true-sky image>.mask.fits`, in the working directory | Sky-model membership and patch grouping; supplementary output |
| Diagnostics | `.image_diagnostics.json` | Starts with `nsources`, then receives image-quality metrics |

The filtered model image is a later Rapthor product rebuilt from the
filtered apparent-sky model, not a source-finder output.

## Catalogue compatibility fields

Rapthor's diagnostic code reads these source-list columns directly, through
Astropy; it converts `Source_id`, `RA`, `DEC` and a flux column to a minimal
makesourcedb text model before LSMTool loads it, so LSMTool never reads the
FITS table. Per-channel columns used by later flux normalization are outside
the MFS-only contract.

| Column | Meaning and use |
| --- | --- |
| `Source_id` | Stable identifier used when converting rows to a comparison sky model |
| `RA`, `DEC` | Position used for matching, beam-radius cuts and astrometry |
| `Isl_Total_flux` | Island-integrated flux used by the default astrometry comparison |
| `Total_flux` | Source flux used for photometry and flux-normalization consistency. In `continuum` it is the sum of the source's fitted Gaussian components, PyBDSF's definition, falling back to the signed aperture when no fit was admitted; see [public products](public-products.md#what-the-two-source-fluxes-measure-and-where-they-part) |
| `DC_Maj` | Deconvolved major axis in degrees; sources at or above 10 arcsec are excluded from compact-source checks |
| `E_RA`, `E_DEC` | Position uncertainties in degrees, both great-circle angles; sources at or above 2 arcsec are excluded from astrometry checks. PyBDSF publishes `E_RA` the same way, so it is *not* divided by cos(dec), which would tighten the cut by 1/cos(dec) and drop sources PyBDSF keeps |

The [Rapthor catalogue view](rapthor-catalogue-view.md) freezes these as an
exact eight-column table: zero-based 32-bit source numbering, 64-bit values,
degrees for position, size and error, Jy for flux, FITS NaN for an
unavailable error, zero `DC_Maj` only for a reviewed unresolved source, a
major-axis-only source's positive major FWHM in `DC_Maj`, and a structurally
complete zero-row table for an empty result.

## Scientific flow

With beam Measurement Sets, a full PyBDSF pass on the true-sky image detects
islands, measures sources, writes the source-list catalogue and true-sky RMS
and exports the island mask; a second pass on the flat-noise image stops
after island construction and writes only its RMS. Without beam data the
flat-noise image supplies the first pass and its RMS is reused. The mask is
clipped to the sector polygon; with mask filtering enabled only sky-model
components inside detected emission remain, surviving true-sky components
are grouped into patches by island, and apparent-sky membership is matched by
component `Name` with the patch grouping transferred. Rapthor consumes the
resulting source rows and island mask, never PyBDSF's live objects.

## Empty and failure behaviour

Two empty paths must be represented explicitly in tests:

- Processing succeeds but finds no islands: LSMTool writes a dummy central
  sky-model component with negligible flux and reports zero sources. The row
  is a serialization workaround, not a source.
- PyBDSF raises `All pixels in the image are blanked`: Rapthor writes
  header-only sky models and an empty catalogue with all required columns,
  copies the two input images to the expected RMS paths and records
  `{"nsources": 0}`. The copied pixels are placeholders, not RMS estimates.

The reviewed policy keeps any required dummy component at the adapter
boundary and represents unavailable RMS explicitly in the scientific core.
Missing inputs and unexpected errors fail the task rather than producing a
silent empty result.

## How Hebog runs inside Rapthor

Rapthor owns the Prefect/Dask graph, retries, resource admission and the
restartable file lifecycle, and Hebog never starts a private cluster. On
10 October 2026 the maintainer decided that, for `source_finder = hebog`,
Rapthor replaces the subprocess call with a native Prefect task that runs
Hebog in-process on its Dask worker, then LSMTool's `filter_sources`; the
PyBDSF subprocess stays for `bdsf` and as the fallback
([ADR-004](../architecture/adr/004-keep-top-level-scheduling-in-rapthor.md),
amendment of 10 October).

Rapthor usually images one sector across a cluster, the first performance
focus; one sector on one node is the other main run, and several sectors
stay supported. The executor follows Rapthor's workers:

| Rapthor's workers | Executor | Why |
| --- | --- | --- |
| Give each node several task slots: several workers a node of several threads each, with `cores` and `prefect` resources on every task (recommended), or several single-threaded workers | `DaskExecutor` on Rapthor's client | Dask schedules every free core, on one node or many, for as long as one sector keeps scaling (plan tasks 73 and 74 measure and cut its serial share) |
| One single-threaded worker a node, today's layout | `ThreadExecutor` inside the worker's task, sized to the node's cores | Through Dask that worker would run one Hebog task at a time; one sector uses one node |

Rapthor's nodes reach 192 cores, and its workers run one task each with
`--nthreads 1`, one a node today. On Rapthor's client, Hebog's tile tasks
stay single-threaded and numerous, with tile cores sized from the cores the
executor declares, so Dask schedules every core; several worker processes
of a few threads each a node, rather than one process of 192 threads, keep
Python's global lock from throttling a node. Hebog's analysis steps out of
its worker slot while it waits on its tile tasks, so concurrent sectors
cannot deadlock, and its tasks carry a Dask resource annotation (plan task
72). [How Hebog runs on Rapthor's Dask layouts](../architecture/rapthor-execution-layouts.md)
draws each layout, including the recommended workers and resources.
The registry route, a `hebog` entry in LSMTool's `KNOWN_SOURCE_FINDERS`,
is deferred.

Reference comparisons use the explicit `5.0/3.0` profile with clean Rapthor
and LSMTool checkouts at their recorded commits. Released and pinned-`master`
PyBDSF do not produce identical catalogues on the same image, so neither is
treated as truth.
