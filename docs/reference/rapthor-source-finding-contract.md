# Rapthor source-finding contract

This inventory records the behaviour Rapthor consumes from its
source-finding step, audited at the pinned revisions:

| Component | Revision | Role |
| --- | --- | --- |
| Rapthor | `main` at `d0e7e148` (13 October 2026) | Schedules the step; `master` is the CWL/Toil release line and not a target |
| LSMTool | `master` at `9bac2f7` (v1.9.0 plus 15 commits) | Runs the finder and filters the sky model |
| PyBDSF | `master` at `c70103b` | The binding scientific and performance reference |

The pins move forward only at the checkpoints the plan names. The page fixes what must be tested without requiring
Hebog to copy PyBDSF internals, and a compatibility observation here is not
a scientific endorsement.

## Invocation boundary

Unpatched Rapthor schedules one Prefect `filter_skymodel` task per image sector after
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
way at `9bac2f7`.) The prepared Rapthor patch instead calls Hebog from the native task; see
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
| `mean_map` | `"zero"`: no background is subtracted | `SourceFinderConfig.background`: `estimated` (default) subtracts Hebog's spatial background; `zero` subtracts nothing and keeps the RMS estimate, as PyBDSF does | Implemented as a setting. Against injected truth zero is worse; against pinned `master` it gives closer fluxes and lower SDC1 completeness. Rapthor runs `zero` with the `compact` profile, the lane closest to `master` in what Rapthor keeps |
| `rms_map`, `rms_box` | On, `(150, 50)` | The coarse RMS grid is 150-pixel windows on a 50-pixel step | Implemented |
| `adaptive_rms_box`, `rms_box_bright`, `adaptive_thresh` | On, `(35, 7)`, `75.0` | Bright-region refinement on 35-pixel windows on a 7-pixel step around candidates at 75σ or more, plus local-noise refinement on the same windows everywhere | Implemented, with two bounded differences: the `continuum` RMS tail and a clipped RMS 1.6 to 3.9% low on noise alone |
| `thresh`, `thresh_pix`, `thresh_isl` | `"hard"`; Rapthor's 5/3, 5/4 or the helper's 7.5/5 | `SourceFinderConfig`'s detection and island thresholds, executed exactly | Implemented |
| `minpix_isl` | Unset, so `max(6, int(beam area in pixels / 3))` | `SourceFinderConfig.minimum_island_pixels`, which the adapter sets by PyBDSF's rule from the true-sky image's beam | Implemented. Hebog applies one configuration to both images, so a flat-noise image whose beam gives another minimum is refused; WSClean writes both from one restoring beam |
| `atrous_do`, `atrous_jmax` | On, 3 scales | Three residual multiscale scales in `continuum`; `compact` omits them | Implemented as Hebog's own multiscale association, not PyBDSF's wavelet decomposition |
| Catalogue | `write_catalog(format="fits", catalog_type="srl", force_output=True)` | `catalogue.fits`; the adapter writes the eight-column view Rapthor reads ([Rapthor catalogue view](rapthor-catalogue-view.md)) as `<root>.source_catalog.fits` | Implemented |
| True-sky RMS | `export_image(img_type="rms")` | `rms.fits`, copied to `<root>.true_sky_rms.fits`; a two-axis `float64` image, which Rapthor's `FITSImage` reads | Implemented |
| Island mask | `export_image(img_type="island_mask")` as `<image>.mask.fits` | `source-mask.fits`, the publication support, which the adapter writes as `<true-sky image name>.mask.fits` in PyBDSF's layout: `float32` ones and zeros on two celestial axes, then a Stokes and a frequency axis of one pixel each. LSMTool's polygon clipping indexes `data[0, 0]` and its grouping reads the mask through casacore, so a two-axis mask fails there | Implemented, with a bounded difference: about 92% of PyBDSF's island pixels. LSMTool groups components into patches by the mask's islands, so the mask's connectivity, not only its coverage, reaches the sky model: under `compact`/`zero`, 96.9% of the components both masks keep are grouped alike, against 99.9% for released PyBDSF |
| Flat-noise RMS | A second pass with `stop_at="isl"`, RMS only | The request's `flat_noise_image_path`: the run estimates that image's background and RMS with the same configuration and publishes `flat-noise-rms.fits`, which the adapter copies to `<root>.flat_noise_rms.fits` | Implemented; the two branches run one after the other until the executor can run them together |
| Source count | `img.nsrc` | `SourceFinderResult.source_count` | Implemented |
| All pixels blanked | `RuntimeError("All pixels in the image are blanked.")` from `collapse.py` | `find_sources` publishes an empty catalogue, an all-NaN RMS and a zero mask; the adapter then raises `RapthorBlankedImageError`, a `RuntimeError` carrying PyBDSF's message, for an image of either branch with no pixel to measure. Hebog also counts a pixel inside a 3×3 square of one value as blank, as imagers fill blanked regions, so an image of one value is blanked too | Implemented; Rapthor's existing handler writes its empty products |
| Reference frequency | The frequency axis at the image plane, then `RESTFREQ`, then a `FREQ` keyword | The frequency axis at the image plane, then `RESTFRQ`, then `RESTFREQ`; a supplied value when the header has none | Implemented. Hebog also reads the standard `RESTFRQ`, which PyBDSF ignores, and refuses rather than reads a non-standard `FREQ` keyword |
| `ncores` | Fitting processes | The cores the Dask worker declares, used by the thread executor or by each Dask task's threads (see below) | Planned with the distributed path |

`RapthorCompatibilityConfig` holds what the finder honours, under Rapthor's
names: `threshpix` and `threshisl`, and Hebog's `profile` and `background`,
which default to Rapthor's `compact` and `zero`. The minimum island follows PyBDSF's
rule, LSMTool's `filter_by_mask` stays with Rapthor's call to
`filter_sources`, and the other options are fixed by Hebog's reviewed
science.

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

The demonstration sector's restoring beam is about 45″ by 43″, 30 pixels
at 1.5″, in every imaging cycle of the local demonstration runs of 15 and
18 September 2026 and in the representative sector (44.8″): the
demonstration's data generator places synthetic antennas within 2,500
wavelengths of the centre, so its longest baselines, about 5,000
wavelengths, resolve about 41″. The public finder refuses a beam wider
than 10 pixels, so the adapter refuses that sector with
`UnsupportedSourceFinderConfigurationError` and the patched task falls back
to PyBDSF; scaling the meshes with the beam is deferred.
Every real Rapthor image in the archived cluster runs of September and
October 2026 (P113+24, the ical benchmark, NGC6338 and AA2) is at most
about 7 pixels: its sector images have 1.5″ cells and 4 to 10″ beams, and
its normalization images 5.9″ cells and 20 to 36″ beams.

PyBDSF's `filter_skymodel` command took between 298 and 2,955 s per
18,000² sector in one three-node benchmark run (16 and 17 September 2026).
The default and benchmarked sector sizes exceed Hebog's 15,402-pixel
envelope; the 22,500-pixel tier that covers them is the planned deployment
envelope.

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
With Hebog, the first path stays Rapthor's: when the adapter reports no
island (`island_count` 0), Rapthor's task writes LSMTool's dummy component
rather than calling `filter_sources`. The patch also preserves this dummy
path when neither a true-sky nor a bright sky model is present. For the second, the
adapter raises `RapthorBlankedImageError`, which Rapthor's step handles as
it handles PyBDSF's error.

The adapter fails in ways Rapthor can act on:

- Hebog's refusals are typed `SourceFinderError`s: an unreadable or
  unsupported image, an image above Hebog's size envelope, images whose
  beams give different minimum islands, or another run's bundle at
  `<root>.hebog`. Before the analysis starts the adapter removes the four
  files Rapthor reads, and a failure while writing them removes those it
  wrote, so a fallback to PyBDSF never finds Hebog's files beside its own.
- A task that declares more memory than the executor admits raises
  `ExecutorAdmissionError` before it is submitted, and the analysis stops
  as on any other failure; the prepared patch falls back on it too.
- A retried task with the same request and run ID reuses Hebog's finished
  bundle without analysing the images again, and writes Rapthor's files
  from it once more, so a mask LSMTool has already clipped is replaced.
- An executor retries a lost task, and the products equal those of a run
  that lost none.
- When the caller's deadline raises in the thread running the analysis, as
  a Prefect task timeout does, every task the analysis started finishes
  before the error propagates, none starts afterwards, and its staging
  directory is removed.

Missing inputs and unexpected errors fail the task rather than producing a
silent empty result.

## How Hebog runs inside Rapthor

Rapthor owns the Prefect/Dask graph, retries, resource admission and the
restartable file lifecycle, and Hebog never starts a private cluster. For
`source_finder = hebog`, Rapthor replaces the subprocess call with a
native Prefect task that runs Hebog in-process on its Dask worker, then
LSMTool's `filter_sources`; the PyBDSF subprocess stays for `bdsf` and as
the fallback
([ADR-004](../architecture/adr/004-keep-top-level-scheduling-in-rapthor.md)).

The [prepared patch](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/patches/README.md)
implements today's one-single-threaded-worker-per-node path. Its real Prefect task, native Hebog and LSMTool
filtering, fallback and dual subprocess runs pass in the pinned Linux
integration container. Upstream publication and merge remain pending. The
distributed layout and resource annotations described below are later work.

On the current layout the task caps its ThreadExecutor by the filter core
request, sector `max_threads` and configured `cpus_per_task`. It limits native
thread pools to one and subtracts `hebog.analysis_memory_bytes` and resident
process RSS from the smaller configured/worker memory budget before admitting
tile tasks. It reserves for the sources `hebog.expected_source_count`
estimates from the detection image at `threshpix`; peeled sources are not in
the image and reserve nothing. A component list is far longer than the source
list: on the matched benchmark's 3,000² sector WSClean's 101,144 components reserved
5.9 GB for 890 sources, where the image's 1,155 peaks reserve 0.27 GB. When
no memory remains for the tile tasks, or one needs more than remains, Hebog's
`ExecutorAdmissionError` is a typed refusal and the task falls back to
PyBDSF, recording the reason in the image diagnostics; an unsupported worker
layout fails explicitly. The whole task occupies the worker's only task
slot, so its analysis reservation does not require Dask resource annotations
on this interim path. Synchronous runs also respect host available memory and
container/process memory limits.

The no-beam branch supplies the flat image as both adapter inputs, as pinned
LSMTool does. A configured missing peeled model is an error. Native selection
and memory/configuration details live in `<root>.image_diagnostics.json` and
survive Rapthor's normal diagnostic update and restart reuse. The patch's
parset defaults are `hebog_profile = compact` and `hebog_background = zero`,
the interim choice for Rapthor, which the adapter also defaults to. Either
setting can be changed in the parset, and invalid settings fail
validation.

Rapthor usually images one sector across a cluster, the first performance
focus; one sector on one node is the other main run, and several sectors
stay supported. The executor follows Rapthor's workers:

| Rapthor's workers | Executor Rapthor passes | Why |
| --- | --- | --- |
| Give each node several task slots, in a layout Rapthor chooses | `DaskExecutor` on Rapthor's client | Dask schedules every free core, on one node or many, for as long as one sector keeps scaling (its serial share is measured and cut first) |
| One single-threaded worker a node, today's layout | `ThreadExecutor` inside the worker's task, sized to the node's cores | Through Dask that worker would run one Hebog task at a time; one sector uses one node. Retired inside Rapthor once each node has several task slots |

Rapthor's nodes reach 192 cores, and its workers run one task each with
`--nthreads 1`, one a node today. On Rapthor's client, Hebog's tile tasks
stay single-threaded and numerous, with each stage's tile core and task
count chosen within the core budget Rapthor states, so Dask schedules every
core; several worker processes of a few threads each a node, rather than one
process of 192 threads, keep Python's global lock from throttling a node.
Hebog's analysis steps out of its worker slot while it waits on its tile
tasks, so concurrent sectors cannot deadlock (planned), and its tasks
carry their declared memory and cores as Dask resource annotations under the
names Rapthor gives `DaskExecutor`.
Rapthor's workers must limit their native thread pools to their declared
cores, because Hebog runs in-process without the subprocess's single-thread
settings. [How Hebog runs on Rapthor's Dask
layouts](../architecture/rapthor-execution-layouts.md) draws each layout and
one way to provide several task slots a node;
[ADR-010](../architecture/adr/010-scale-hebog-independently-of-its-integrations.md)
states what Hebog needs from any cluster. The registry route, a `hebog`
entry in LSMTool's `KNOWN_SOURCE_FINDERS`, is deferred.

Rapthor's task builds a `RapthorSourceFindingRequest` from the sector's two
images, its `<working directory>/<image name>` root and a run ID that a
retry repeats, and a `RapthorCompatibilityConfig` from its strategy's
`threshpix` and `threshisl`. It calls
`hebog.adapters.find_sector_sources(request, config, executor)` and then,
when the result reports an island, LSMTool's
`filter_sources(result.mask_path, vertices_file, ...)` with
`keep_mask=True`. The adapter imports no Rapthor, Prefect or LSMTool, and
writes Hebog's own bundle, with its diagnostics and provenance, in
`<root>.hebog`.

In dual-run mode Rapthor runs both finders on the sector, each under its
own root under `<root>.source-finders/`, and calls
`hebog.adapters.rapthor_comparison.compare_sector_products(result, pybdsf,
report_path)` after LSMTool filtering, then selects the Hebog products for
Rapthor. The full comparison is embedded in ordinary image diagnostics.
Blanked images keep both empty sets and record why comparison is unavailable.
Private input symlinks isolate PyBDSF masks, which it writes beside its input
filename irrespective of the subprocess working directory. The report reads both sets
and changes neither. It binds the path, size and SHA-256 of all eight files
and Hebog's provenance, and records each finder's source count, the sources
that are each other's nearest within half the restoring beam's major axis,
the median ratio of their `Total_flux`, the median ratio of each pair of RMS
maps on every sixteenth pixel of each axis, and the island pixels each mask
holds and both hold. On the frozen 256² input against pinned `master`, all
three sources match, the flux ratio is 1.000, the RMS ratio is 0.981 and
Hebog's mask holds 165 of PyBDSF's 178 island pixels and one more of its own.

Reference comparisons use the explicit `5.0/3.0` profile with clean Rapthor
and LSMTool checkouts at their recorded commits. Released and pinned-`master`
PyBDSF do not produce identical catalogues on the same image, so neither is
treated as truth.
