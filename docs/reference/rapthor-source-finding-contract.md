# Rapthor source-finding contract

This inventory records the behaviour Rapthor consumes from its PyBDSF/LSMTool
source-finding path, traced at Rapthor commit
`b1a64674b1022476cf052fc2d06ee3b16f031ecd` on its
`gec-468-ai-migrate-to-prefect` branch, which owns the Prefect/Dask task
runner that will schedule Hebog. That branch merged into Rapthor's `main` on
9 October 2026 (`c6196cb4`); `main` runs the step in a fresh interpreter per
sector and selects the finder through LSMTool's `filter_skymodel`
`source_finder` registry. The exact revisions are in
[`config/baselines/phase-0-starting-revisions.json`](https://github.com/gemmadanks/hebog/blob/main/config/baselines/phase-0-starting-revisions.json);
the plan's task 16 moves the pins forward and refreshes this page against
`main`. It fixes
what must be tested without requiring Hebog to copy PyBDSF internals, and a
compatibility observation here is not a scientific endorsement.

## Invocation boundary

Rapthor schedules one `filter_skymodel` task per image sector after WSClean
has written its image and source-list products, passing paths and scalar
configuration and receiving serializable file records. Image diagnostics run
as a separate dependent task.

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

| Setting | Value | Contract significance |
| --- | ---: | --- |
| RMS box | `(150, 50)` pixels | Normal window width and step |
| Bright-source RMS box | `(35, 7)` pixels | Adaptive width and step near bright emission |
| Adaptive RMS threshold | `75.0` sigma | Selects the smaller RMS box |
| Background mean map | Zero | The imaging path assumes zero background |
| RMS map | Enabled | Spatially varying noise is part of the contract |
| Threshold mode | Hard | Thresholds are not false-discovery-rate derived |
| Wavelet processing | Enabled, three scales | Extended/multiscale emission is in scope |
| Filter by mask | Enabled | Components outside detected islands are removed |
| Source finder | `bdsf` | Pinned PyBDSF `master` is the binding scientific and performance reference; released 1.14.1 is checked once (the plan's task 31) |
| Rapthor core count | `15` | Execution input, not a scientific result |

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
| Island mask | `<true-sky-image>.mask.fits` | Sky-model membership and grouping; supplementary output |
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

## Execution constraints

Rapthor owns the Prefect/Dask graph, retries, resource admission and the
restartable file lifecycle. Its PyBDSF path runs a subprocess when multi-core
PyBDSF would otherwise run inside a daemon worker; Hebog removes that escape
while keeping coarse task boundaries, serializable path-based results,
deterministic ordering and explicit CPU and memory budgets. For large images
one admitted operation may expand into the haloed-tile and
hierarchical-reconciliation subgraph of
[ADR-005](../architecture/adr/005-scale-large-images-with-hierarchical-tiles.md),
using Rapthor's existing client and never a private cluster or a complete
plane on one worker.

Reference comparisons use the explicit `5.0/3.0` profile with clean Rapthor
and LSMTool checkouts at their recorded commits. Released and pinned-`master`
PyBDSF do not produce identical catalogues on the same image, so neither is
treated as truth.
