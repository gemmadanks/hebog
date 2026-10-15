# Glossary

This page defines the terms the documentation, the code and the products
use, in the sense Hebog gives them. Where a term has a different meaning in
PyBDSF, Rapthor or LSMTool, the [last section](#pybdsf-rapthor-and-lsmtool-names)
maps their name onto Hebog's. Each table links to the page where the term
matters most.

## Images and headers

| Term | Meaning |
| --- | --- |
| FITS | The file format of the input image and the output catalogue. An image file holds a two-dimensional array of pixel values and a header of keyword cards that describe them. See the [input header contract](input-header-contract.md). |
| Header card | One keyword, value and comment in a FITS header, such as `BUNIT = 'Jy/beam'`. Hebog reads the cards listed in the input header contract and refuses a card that does not hold the kind of value it should. |
| WCS | World Coordinate System: the header's mapping from pixel position to sky position. Hebog accepts an ICRS or FK5 J2000 celestial WCS and publishes every position in ICRS. |
| ICRS, FK5 J2000 | The two sky coordinate frames Hebog accepts. ICRS is the current standard frame; FK5 J2000 is the older frame many imagers still write, which differs from ICRS by a few tens of milliarcseconds. |
| Right ascension, declination | The sky's longitude and latitude, in degrees. Hebog publishes right ascension in `[0, 360)` and declination in `[-90, 90]`. |
| Pixel | One array sample. Arrays are indexed `(y, x)`, row first; a pixel position written `(x, y)` is a coordinate for a WCS or a catalogue. |
| Plane | One two-dimensional image. Hebog analyses one plane; a FITS file with frequency or Stokes axes is accepted only when each has length one. |
| Stokes I | Total intensity, the only polarisation Hebog measures. A `STOKES` axis must select it. |
| Reference frequency | The frequency, in hertz, at which every published flux is defined. Hebog reads it from the image's frequency axis, `RESTFRQ` or `RESTFREQ`, or from the request when the header has none. |
| MFS image | A multi-frequency-synthesis image: one plane made from a whole band, reported at one reference frequency. Hebog's catalogue is an MFS catalogue with no spectral fit. |
| Jy/beam | Jansky per beam, the brightness unit of the input and of peak fluxes. A jansky is a unit of flux density; dividing by the beam makes it a brightness. Integrated fluxes are in Jy. |
| Restoring beam | The Gaussian blur every deconvolved radio image carries, written as `BMAJ`, `BMIN` and `BPA` in degrees. It sets the finest detail the image shows and the area that converts Jy/beam to Jy. Hebog applies one beam to the whole image and refuses one wider than 10 pixels. |
| FWHM | Full width at half maximum, the width used for the beam and for every fitted or deconvolved ellipse. The Gaussian sigma is the FWHM divided by about 2.355. |
| Beam area | The solid angle of the restoring beam, π × BMAJ × BMIN / (4 ln 2). In pixels it is about 1.13 FWHM² for a circular beam, which is why a minimum island of seven pixels is a fraction of a beam five pixels wide. |
| Position angle | The orientation of an ellipse's major axis, in degrees east of north, reported in `[0, 180)`. |
| Primary beam | The telescope's sensitivity pattern across the field, highest at the pointing centre and falling towards the edge. It is unrelated to the restoring beam. |
| Primary-beam-corrected image | The image after division by the primary beam, so that fluxes are intrinsic but the noise rises towards the edge of the field. Rapthor calls it the *true-sky* image; it is an estimate, not truth. |
| Flat-noise image | The image before primary-beam correction. Its noise is roughly uniform across the field, so Rapthor uses it to estimate noise, and its fluxes are attenuated by the primary beam. Rapthor also calls it the *apparent-sky* image. |
| Sector | The part of the sky one Rapthor imaging run covers. Rapthor images each sector into a true-sky and a flat-noise image and runs the source finder once per sector. |
| Invalid pixel | A pixel that takes no part in any estimate or measurement: NaN or infinite, a stored integer equal to `BLANK`, or any pixel of a 3×3 square holding one repeated value, such as zero padding. The published RMS is NaN there. See [invalid pixels](input-header-contract.md#invalid-pixels). |
| Supplied metadata | A unit, beam or reference frequency given on the request with `SuppliedImageMetadata` because the header omits it. A supplied value never overrides a header value, and the diagnostics record it. |
| Cut-out | A rectangular region cut from a larger image, for example with Astropy's `Cutout2D`. Images above the size limit need one. |

## Noise and background

| Term | Meaning |
| --- | --- |
| Background | The slowly varying level of the image away from sources, estimated separately from the noise and subtracted before detection. The `background` setting is `estimated` (Hebog's spatial estimate) or `zero` (nothing subtracted, as PyBDSF's `mean_map="zero"`). |
| RMS | Root mean square: the local noise level, in Jy/beam, estimated from sigma-clipped pixels in windows and interpolated to every pixel. Hebog publishes it as `rms.fits`. |
| Sigma clipping | Repeatedly discarding the samples in a window that lie more than a set number of standard deviations from the rest, so that sources do not inflate the noise estimate. Hebog clips at three standard deviations. |
| σ, signal-to-noise ratio | Thresholds are multiples of the local RMS above the local background: a 5σ pixel is five times the local RMS above the background. |
| Residual | The background-subtracted image, `image − background`, on which Hebog detects, grows islands and measures. The *residual of a fit* is what is left after subtracting fitted Gaussians as well; the text says which is meant. |
| Normalized residual | The residual divided by the local RMS, so that each pixel reads in σ. Internal only; thresholds apply to it. |
| Coarse grid | The background and RMS grid of 150-pixel windows every 50 pixels, the same as PyBDSF's `rms_box`. Its values are interpolated to every pixel. |
| Fine grid | The RMS grid of 35-pixel windows every 7 pixels, the same as PyBDSF's `rms_box_bright`. The `continuum` profile measures it across the whole image on images at least 150 pixels on a side (*local noise*), and both profiles measure it around bright sources. |
| Protected pixel, protected window | A pixel that belongs to a candidate source is protected: it is excluded from the noise statistics, and a window that overlaps protected pixels is dropped. |
| Clean window | A noise window that overlaps no protected pixel and measured a noise above the noise floor. A dropped window takes the RMS of its nearest clean window, within the reach the [RMS reference](public-products.md#rms-fits-image) states. |
| Bright region | The area around sources at 75σ or more, where imaging artefacts make the noise change quickly. There the fine grid replaces the coarse RMS wherever it reads higher. Bright candidates close together chain into one region, estimated in bounded blocks. |
| Noise floor | The smallest spread a window can measure: the window's brightest absolute value times 2⁻²³, single precision's resolution there. A window under it measures no noise and is dropped. |
| Unavailable RMS | The state of a run in which no pixel has a finite positive RMS. The RMS product is all NaN and marked `unavailable`, the catalogue is empty and the mask is zero. It is not evidence of an empty sky. |
| Flat-noise RMS | The RMS of a sector's flat-noise image, published as `flat-noise-rms.fits` when the request names that image. Nothing else is measured on it. |

## Detection

| Term | Meaning |
| --- | --- |
| Detection threshold | `detection_threshold_sigma`: the signal-to-noise ratio an island must contain to be accepted. PyBDSF's `thresh_pix`. |
| Island threshold | `island_threshold_sigma`: the lower level to which an accepted island grows. PyBDSF's `thresh_isl`. It must be below the detection threshold. |
| Seed | A valid pixel at or above the detection threshold. An island needs a seed, or multiscale evidence over a minimum area in beams. |
| Eight-connected | Pixels joined through edges or corners. Islands and mask regions are eight-connected. |
| Island | A connected region of the published mask, and one row of the `ISLANDS` table. It can hold several sources, and a source can span several islands. |
| Minimum island size | `minimum_island_pixels`: the fewest pixels an island may have. PyBDSF derives its `minpix_isl` from the beam; Hebog requires it explicitly, and the Rapthor adapter applies PyBDSF's rule. |
| Matched filter | A beam-shaped smoothing filter whose response is highest where the image holds beam-sized emission. Hebog evaluates a bank of them to decide whether faint emission is significant. |
| À trous wavelet, B3 spline | A multiscale transform that separates an image into planes of increasing scale by repeated smoothing with a B3-spline kernel, without downsampling ("with holes"). Hebog uses scales 1 to 3 of the residual's transform as detection evidence; PyBDSF fits Gaussians to such planes. |
| Scale | One wavelet plane. Scale 1 holds structure about the size of the beam, and each later scale doubles that, so scale 3 holds structure about four beams wide. |
| Multiscale support | Pixels a detection gains from the filtered images rather than from its own thresholded pixels. It is kept only where it persists at an adjacent scale, and is assigned to the nearest detection along the emission within half a beam. |
| Persistence | A multiscale feature's appearance at two adjacent scales. Support that does not persist is dropped. |
| Support, footprint | The pixels a detection owns: its thresholded pixels plus any multiscale support assigned to it. *Publication support* is the part published in the mask. |
| Owner | The detection that owns a pixel. Every mask pixel has exactly one owner, decided by the detection, not by the tile that computed it. |
| Parent | One retained detection, with its support, as deblending receives it. Deblending splits a parent into components; one too large for the bounded deblend stays one component and is recorded as deferred. |
| Mask | `source-mask.fits`: 1 where a pixel is publication support, 0 elsewhere. Its connected regions are the catalogue's islands. It is not a CLEAN mask and not a photometric aperture. |

## Components and fitting

| Term | Meaning |
| --- | --- |
| Deblending | Splitting a parent into one region per significant peak, so that blended sources are fitted separately. Two peaks stay apart when the fainter lies at least 1.5σ above the pass between them. See [compact deblending](compact-deblending.md). |
| Pass, saddle | The highest level at which one connected part of an island still holds two peaks; the lowest point on the ridge between them. |
| Deblended region | The pixels that rise to one peak after deblending. It initialises one Gaussian fit; it is not yet a component or a source. |
| Gaussian component | One elliptical Gaussian whose fit was admitted, and one row of the `GAUSSIAN_COMPONENTS` table. Say "Gaussian component", because *component* alone can mean a clean or sky-model component. |
| Moments | The brightness-weighted centroid and covariance of a region's pixels. They initialise the fit and are never published as a fitted shape. |
| Fit parent | A group of components whose fitting regions touch, fitted jointly so that a neighbour's light is modelled rather than absorbed. A chain of more than sixteen components, or wider than the read budget, is fitted island by island instead. |
| Joint fit | One least-squares solve for every component of a fit parent at once, flagged `joint-gaussian-fit`. |
| Free model, beam-constrained model | The two Gaussian models a fit chooses between: a free ellipse, or one whose axes and angle are fixed to the restoring beam. A component takes the beam when its free fit is not significantly extended, reaches a bound or is ill conditioned. |
| Admitted fit | A fit that converged, stayed within its bounds, is well conditioned, leaves acceptable residuals and has usable uncertainties. Only admitted fits become Gaussian rows; a rejected fit keeps the detection and records why. |
| Fit at bound | A fit whose solution reached a configured limit on position, size or amplitude, flagged `fit-at-bound`; the component then takes the beam. |
| Well conditioned | A fit whose parameters the data can tell apart. A component that owns a few pixels along a line cannot fix its own width, so the fit is ill conditioned until that component takes the beam. |
| Residual feature | Positive emission left after subtracting a fit's Gaussians, grown from a detection-threshold seed and touching the fitted support. It makes a fit `fit-model-inadequate`, or joins components into one source. |
| Beam deconvolution | Subtracting the restoring beam's covariance from a fitted ellipse's to estimate the source's intrinsic size. See [compact astrometry](compact-astrometry.md#beam-deconvolution). |
| Resolved, unresolved, major-axis-only | The three deconvolution states: two significant intrinsic axes, none, or only the major axis. Only an unresolved source publishes a `DC_Maj` of zero in the Rapthor view. |
| Extension significance | Whether a fit is measurably larger than the beam: the log ratio of integrated to peak flux must exceed five times its uncertainty. A geometrically resolved fit that fails the test is unresolved, flagged `extension-not-significant`. |
| Correlated noise | Noise whose neighbouring pixels are not independent, because the beam smooths them. Hebog's published errors allow for it; its fit weights pixels by their RMS without modelling the correlation. |
| Deferred | The status of work Hebog did not do because an object exceeded a bound: a parent too large to deblend or fit stays one detection with `deferred` dispositions and no Gaussian. It is never silently dropped. |

## Sources and the catalogue

| Term | Meaning |
| --- | --- |
| Source | One or more components that Hebog associates as a single object in the image, and one row of the `SOURCES` table. Not necessarily one galaxy. |
| Association | The `continuum` profile's decision about which components form one source, from overlapping Gaussians, resolved arcs and loops, and shared residual emission. Each merge records its evidence in the diagnostics. The `compact` profile skips it. |
| Association evidence | The record of one merge: its reason (`directional-fwhm-overlap`, `resolved-loop`, `resolved-open-arc` or `persistent-residual`), the scales involved and the members. |
| Segment | The region a source is measured in: its support, expanded by a bounded aperture of 1.5 beams. Catalogue rows are measured one segment at a time. |
| Association aperture | A source's own non-overlapping region of the image. Each observable pixel contributes to at most one source's aperture. |
| `ASSOCIATION_APERTURE_FLUX` | The signed sum of background-subtracted pixels in a source's aperture, divided by the beam area, in Jy. Empty when the sum is not positive. Observed flux inside the footprint; no fit contributes to it. |
| `INTEGRATED_FLUX` | For a Gaussian component, the integral of its fitted Gaussian over the whole plane. For a `continuum` source, the sum of its components' integrals, PyBDSF's definition, or the aperture flux when no fit was admitted. See [where the two source fluxes part](public-products.md#what-the-two-source-fluxes-measure-and-where-they-part). |
| `PEAK_FLUX` | A fitted Gaussian's peak amplitude in Jy/beam. A source of one fitted component publishes its component's; any other source publishes its brightest background-subtracted pixel. |
| Position | A single-component source publishes its Gaussian's fitted position and errors. Any other source publishes a centroid of its detection footprint, which can lie between two peaks or inside a ring, with no position errors. |
| Catalogue row | One row of the `ISLANDS`, `SOURCES` or `GAUSSIAN_COMPONENTS` table. A detection without a row still has a disposition in the diagnostics. |
| Quality flag | One of the comma-separated labels in `QUALITY_FLAGS`, such as `resolved` or `aperture-flux-without-fitted-component`. Readers must keep flags they do not recognise. See [interpreting quality flags](public-products.md#interpreting-quality-flags). |
| Disposition | The diagnostics' record of what happened to one component or source: `measured`, `unavailable` or `deferred`, the estimator, the reason and whether a row was published. Every detected identity has one. |
| Estimator | How a measured quantity was obtained: `original-pixel-gaussian-model` for a component, `summed-fitted-component-flux` or `source-owned-signed-aperture` for a source. |
| Profile | The reviewed set of algorithm settings a run uses: `continuum` (default, with association and local noise) or `compact` (one source per Gaussian, no association). Everything but the thresholds and island sizes is fixed by the profile. |
| Reviewed science profile | The packaged settings behind the profiles, `reviewed_continuum_profile.json`, whose SHA-256 the provenance records as `scientific_profile_sha256`. |
| Configuration qualification | The diagnostics label `development-unqualified` (the 5σ, 3σ, seven-pixel example settings) or `custom-unqualified` (anything else). Both mean Hebog is not qualified for survey use. |
| Product | One output file with its record: role, path, byte count, SHA-256, media type, schema version and scientific status. The readers verify the record before parsing. |
| Bundle | The output directory of four products, five with a flat-noise RMS, published together in one rename. |
| Scientific status | `valid`, or `unavailable` for an RMS product with no estimate. It says whether the file holds the quantity its role names. |
| Provenance | The diagnostics' identities of the run: SHA-256 of the input bytes, the configuration, the reviewed profile and the implementation, plus any supplied metadata. |
| Scientific composition | The implementation identity: a hash over every Hebog module the finder imports and every packaged resource. Two runs with the same input, configuration and composition give the same products. |
| Run ID | The caller's name for one run, carried into the catalogue and diagnostics. The same request with the same run ID returns its finished products instead of running again. |
| Schema version | The integer version of a record or file format. Readers reject versions they do not support; nothing is migrated before 1.0. |

## Execution

| Term | Meaning |
| --- | --- |
| Executor | The object that runs Hebog's tasks: `SerialExecutor` in the calling thread, `ThreadExecutor` on a pool of threads in one process, or `DaskExecutor` on a Dask client the caller owns. All three give the same products. See [the executor contract](../architecture/distributed-execution.md#the-executor-contract). |
| Serial reference | `SerialExecutor`, the deterministic implementation every other executor and every tiling must reproduce byte for byte. |
| Driver | The process that called `find_sources`. It plans tiles, submits tasks, reduces their small results and writes the products; it holds no image-sized array. |
| Worker | A process or thread that runs tasks: a Dask worker, a thread of the pool, or the calling thread itself under the serial executor. |
| Task | One call of a function on one batch, submitted to the executor. Its arguments and result are small serializable records, never arrays the size of the image. |
| Batch | The unit of work one task receives: several tiles, or up to 256 objects whose reads fit a budget. Batching keeps the number of tasks proportional to tiles and objects, not pixels. |
| Tile | One rectangle of the image's grid, the unit of tiled work. Background and RMS use 128-pixel tile cores; every other stage uses 2,048-pixel cores, so an image up to 2,048 pixels is one tile there. |
| Core | The pixels one tile owns and writes. Cores do not overlap and cover the image exactly once. |
| Halo | The read-only margin around a core that a stage needs to compute the core's edge exactly, such as a filter's width. Each stage declares the smallest halo that makes its output exact. |
| Stage | One step of the finder in its own module under `hebog.stages`: background and detection, multiscale, support, publication, objects, association, sources, islands and catalogue rows, run in that order by `composition.py`. |
| Pass | One of the four groups of stages ADR-008 defines, A (noise), B (detection), C (support) and D (objects). A pass ends only where a global reduction must finish before any later decision. |
| Round | One `map_batches` call on the executor: one function over one set of batches, with one declared memory. A stage runs one or more rounds. |
| Boundary summary | The small record a tile task returns about its core's edges, such as the labels on each edge and each label's pixel count, bounding box and peak, so that objects crossing tile edges can be joined without sending pixels. |
| Reconciliation | Joining tile summaries into one global answer, such as one label for a region that crosses several tiles, through a pairwise tree fixed by tile order so that the result does not depend on completion order. |
| Invariance | The guarantee that tile shape, partition origin, worker count, task order and retries do not change the products. Tested by comparing one tile against an eight-by-eight grid and Serial against Thread and Dask. |
| Read budget | `maximum_batch_read_pixels`: the most pixels one object task may read. An object whose window exceeds it is measured from the cores that hold it instead. |
| Wide object | An object whose window exceeds the read budget: a filament crossing the image, say. The driver reduces it from the pixels its cores return, the one memory term that grows with an object rather than a tile. |
| Declared memory | The `TaskRequirement` every round states for its tasks: the measured cost per read pixel times the largest read, with headroom. The executor refuses a task larger than a worker admits and runs only as many at once as fit. |
| Capacity | `ExecutorCapacity`: the budget the caller admits, as worker count, threads per worker, tasks in flight and memory per worker. A `DaskExecutor` without one reads the cluster's current size. |
| Resource names | The names of the Dask worker resources, chosen by the caller, under which a `DaskExecutor` requests each task's declared memory and one core, so that Dask places tasks only where that much is free. |
| Analysis memory | What `find_sources` itself holds in the calling process, growing with the sources found at about 40 KB each. `hebog.analysis_memory_bytes` states it for the caller to reserve. |
| Generation | One run's set of intermediate Zarr planes. It is complete only once an immutable marker names exactly one validated chunk for every plane and tile. |
| Chunk | One stored piece of a Zarr plane, one per tile core. A chunk is a storage unit; a tile is a work unit. |
| Staging directory | The hidden `.<output name>.<random>` directory beside the output in which a run builds its planes and products. A finished run removes it; a killed run leaves it with an owner record, which the next run to the same output reclaims once the owner has provably stopped. |
| Atomic publication | Writing the whole bundle into the staging directory, validating it, then moving it into place with one rename, so that a partial result is never visible. |
| Secede | A Dask worker task stepping out of its thread slot while it waits on other tasks, so that a waiting analysis does not block the tasks it submitted. Planned for Hebog's analysis inside a Rapthor task (plan task 72). |

## Rapthor and sky models

| Term | Meaning |
| --- | --- |
| Rapthor | The LOFAR calibration and imaging pipeline that is Hebog's first consumer. It runs on Prefect and Dask and uses PyBDSF today. |
| Prefect | The workflow framework Rapthor's `main` branch runs on. Rapthor's filter step is one Prefect task per sector. |
| PyBDSF | The Python Blob Detector and Source Finder, the finder Rapthor uses and the reference Hebog is compared against. Agreement with it shows compatibility, not truth. |
| LSMTool | The LOFAR sky-model tool. Its `filter_sources` keeps and groups sky-model components by the source finder's mask. |
| `filter_skymodel` | Rapthor's step that runs the source finder on a sector and then filters the sky model by the mask. See the [Rapthor source-finding contract](rapthor-source-finding-contract.md). |
| Sky model | The list of known sources, with positions, fluxes and spectral models, that a calibration pipeline predicts the visibilities from. WSClean writes one as a component list. |
| Sky-model component | One row of a sky model. Not a Gaussian component fitted by the source finder. |
| Clean component | One component the deconvolver (WSClean) placed while cleaning. Also not a fitted Gaussian component. |
| Patch | A group of sky-model components calibrated as one direction. LSMTool groups surviving components into patches by the mask's islands. |
| Source-filtering mask | What Rapthor and LSMTool do with Hebog's mask: keep the sky-model components that lie on detected emission. The mask is not a CLEAN mask, which controls deconvolution. |
| Adapter | `hebog.adapters.find_sector_sources`: the module that runs one sector through `find_sources` and writes Rapthor's file names and the eight-column catalogue view, importing no Rapthor, Prefect or LSMTool code. |
| Eight-column view | The `Source_id`, `RA`, `DEC`, `Isl_Total_flux`, `Total_flux`, `DC_Maj`, `E_RA` and `E_DEC` table Rapthor reads. See the [Rapthor catalogue view](rapthor-catalogue-view.md). |
| Fallback | Rapthor's planned behaviour of running PyBDSF when Hebog raises a typed `SourceFinderError`. A refused sector leaves none of Hebog's files behind. |
| Dual run | Running both finders on one sector and comparing their products with `compare_sector_products` before choosing one set. |

## Validation and evidence

| Term | Meaning |
| --- | --- |
| Injected truth | Generated images whose sources' positions, fluxes and shapes are known, so that completeness, reliability and errors can be measured against an answer. |
| Completeness, reliability | The fraction of true sources recovered, and the fraction of reported detections that are true, for a stated population and matching rule. |
| Quick science check | `just quick-science-check`: 18 fixed cases compared with injected truth and pinned PyBDSF `master`, run on every scientific change. A regression detector, not qualification. See [the contribution guide](../how-to/index.md#run-the-quick-science-check). |
| Quick benchmark | `just quick-benchmark`: five timed repetitions of the public finder per case, compared with the previous release and with PyBDSF `master`. |
| Traced peak | `just traced-peak`: `tracemalloc`'s peak allocation in a fresh process, the figure memory gates use. Peak RSS is reported beside it as an envelope only. |
| Release check | The sequence of quick check, quick benchmark and traced peak run on a release candidate, whose results the [progress page](progress-against-goals.md) summarises. |
| Equivalence lane | `just test-equivalence`: `find_sources` and its stages against frozen PyBDSF products, run in CI. |
| Contract test | A test in `tests/contract/` of a public behaviour, run through every executor. An unimplemented behaviour is a strict expected failure. |
| Acceptance test | A Given/When/Then test in `tests/acceptance/` of a Rapthor-facing scenario. |
| Anchor | A fixed input the performance and memory figures are measured on, such as the 10,000² LoTSS-DR3 cut-out and the whole 15,402² mosaic. |
| Performance ladder | The frozen list of image sizes and workloads a release is timed on. See the [performance contracts](performance-scalability-contracts.md). |
| Matched benchmark | The deployment gate: Rapthor's complete `filter_skymodel` step with Hebog's native task against the same step with pinned PyBDSF `master`, in one container on the same cores and inputs. Measured by `scripts/benchmark/measure_filter_skymodel.py` ([how to](../how-to/index.md#run-the-matched-filter_skymodel-benchmark)). |
| Dataset role | `development` for routine work, `regression` to preserve a decided case, or `qualification`, held out from tuning. See [dataset manifests](dataset-manifests.md). |
| Evidence record | A versioned JSON document from `hebog.validation.evidence` that binds a measurement to its inputs, software and environment. `reviewed` only after its protocol and results pass review. |
| Qualification | Reviewed evidence that a frozen candidate meets the plan's gates on held-out data. No Hebog release has it; passing tests and development comparisons do not establish it. |

## Naming conventions

- Use `(y, x)` for array shapes and indices, and names such as `x_pixel`
  and `y_pixel` where an interface takes `(x, y)`.
- Put the frame and unit in a name the type does not carry: `ra_deg`,
  `beam_fwhm_deg`, `frequency_hz`, `flux_jy`, `flux_jy_per_beam`.
- Say `detection_threshold` and `island_threshold`; keep `thresh_pix` and
  `thresh_isl` only at the Rapthor boundary.
- Qualify every component as `gaussian_component`, `clean_component` or
  `sky_model_component`, and never use source, island, Gaussian component,
  catalogue row and sky-model component interchangeably.
- Say `primary_beam_corrected` and `flat_noise`; keep `true_sky` and
  `apparent_sky` where the Rapthor mapping is explicit.
- Write `catalogue` in Hebog prose and modules; keep `catalog` in external
  field names and file names.
- Name executors `serial`, `thread` and `dask`, as the classes are named.
- A chunk is a storage unit and a tile a work unit; do not use one for the
  other.

## PyBDSF, Rapthor and LSMTool names

| Their name | Hebog's term |
| --- | --- |
| `thresh_pix` | Detection threshold |
| `thresh_isl` | Island threshold |
| `minpix_isl` | Minimum island size |
| `mean_map = "zero"` | `background = "zero"` |
| `rms_box` | Coarse grid, 150-pixel windows every 50 pixels |
| `rms_box_bright`, `adaptive_thresh` | Fine grid, 35-pixel windows every 7 pixels, around bright regions at 75σ |
| `atrous_do`, `atrous_jmax` | À trous wavelet scales, used as detection and association evidence |
| `flat_noise_image` | Flat-noise image |
| `true_sky_image` | Primary-beam-corrected image |
| `island_mask`, `<image>.mask.fits` | Mask, used by Rapthor as the source-filtering mask |
| `srl` catalogue | The `SOURCES` table; the eight-column view for Rapthor |
| `gaul` catalogue | The `GAUSSIAN_COMPONENTS` table |
| `Source_id` | `SOURCE_ID`, numbered from zero in the eight-column view |
| `Total_flux` | A source's `INTEGRATED_FLUX` |
| `Isl_Total_flux` | An island's `INTEGRATED_FLUX` |
| `DC_Maj`, `E_RA`, `E_DEC` | `DECONVOLVED_MAJOR`, `RIGHT_ASCENSION_ERROR`, `DECLINATION_ERROR` |
| `filter_skymodel` | Rapthor's step: run the finder, then filter and group the sky model by the mask |
| `source_finder` | LSMTool's choice of finder; `hebog` is reached through Rapthor's native task instead |
