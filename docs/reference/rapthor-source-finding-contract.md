# Rapthor source-finding contract

This provisional contract inventory describes the behaviour Rapthor consumes
from its current PyBDSF/LSMTool source-finding path. It was traced at Rapthor
commit `b1a64674b1022476cf052fc2d06ee3b16f031ecd` and checked against the local
reference revisions listed in [Phase 0 starting revisions](starting-revisions.md).
The authoritative orchestration target is Rapthor's
`gec-468-ai-migrate-to-prefect` branch because it owns the Prefect/Dask task
runner that will schedule Hebog. Its declared LSMTool revision is available
locally and was used for this trace.

The inventory freezes what must be tested. It does not require Hebog to copy
PyBDSF internals or preserve incidental implementation details. The
[scientific pre-review](scientific-pre-review.md) distinguishes compatibility
observations from cross-pipeline scientific recommendations.

## Invocation boundary

Rapthor schedules one `filter_skymodel` task per image sector after WSClean has
materialised its image and source-list products. It passes paths and scalar
configuration; the task returns serializable file records. Image diagnostics
run as a separate dependent task.

The current task accepts:

| Input | Meaning |
| --- | --- |
| Flat-noise image | Rapthor alias for the primary-beam-uncorrected FITS image with comparatively flat noise |
| True-sky image | Rapthor alias for the primary-beam-corrected FITS image used for intrinsic flux measurements; it is not literal truth |
| True-sky sky model | WSClean component list with true-sky fluxes; optional when its file is absent |
| Apparent-sky sky model | WSClean component list with beam-attenuated fluxes; optional when its file is absent |
| Bright true-sky sky model | Optional peeled bright components to add back before filtering |
| Sector vertices | NumPy polygon file defining the valid imaging sector |
| Beam Measurement Sets | Observation paths used to select a representative beam attenuation |
| Configuration | Thresholds, RMS boxes, adaptive threshold, mask-filter flag, source finder, and core count |

Rapthor has three relevant threshold profiles. The workflow passes strategy
values explicitly, so the helper fallback is not the representative production
profile:

| Context | Detection threshold | Island threshold |
| --- | ---: | ---: |
| Normal imaging, later self-calibration, and retained rich Prefect demo | `5.0` sigma | `3.0` sigma |
| Initial/normalization and early self-calibration cycles | `5.0` sigma | `4.0` sigma |
| `filter_image_skymodel` helper fallback | `7.5` sigma | `5.0` sigma |

The remaining traced compatibility configuration is:

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
| Source finder | `bdsf` | Released PyBDSF is the current compatibility oracle; pinned `master` is a separate performance comparator |
| Rapthor core count | `15` | Execution input, not a scientific result |

## Materialised products

For every successful sector, Rapthor requires the catalogue, RMS, filtered
models, and diagnostics before it continues. The filtering mask is returned
only when the expected file exists:

| Product | Current suffix | Downstream use |
| --- | --- | --- |
| Filtered true-sky model | `.true_sky.txt` | Calibration and true-flux sky-model state |
| Filtered apparent-sky model | `.apparent_sky.txt` | Beam-attenuated prediction/model state |
| True-sky RMS image | `.true_sky_rms.fits` | RMS statistics and true-sky dynamic range |
| Flat-noise RMS image | `.flat_noise_rms.fits` | RMS statistics, local dynamic range, and facet diagnostics |
| Source catalogue | `.source_catalog.fits` | Source count, photometry, astrometry, and preview selection |
| Island mask | `<true-sky-image>.mask.fits` | Optional legacy product used for sky-model membership/grouping and supplementary output |
| Diagnostics | `.image_diagnostics.json` | Starts with `nsources`, then receives image-quality metrics |

The filtered model image is an optional later Rapthor product reconstructed
from the filtered apparent-sky model. It is not a source-finder output.

## Catalogue compatibility fields

Rapthor's diagnostic code directly consumes these source-list catalogue
columns:

| Column | Meaning and use |
| --- | --- |
| `Source_id` | Stable source identifier used when converting rows to a comparison sky model |
| `RA`, `DEC` | Sky position used for matching, beam-radius cuts, and astrometry |
| `Isl_Total_flux` | Island-integrated flux used by the default astrometry comparison conversion |
| `Total_flux` | Fitted source flux used for photometry and flux-normalization consistency |
| `DC_Maj` | Deconvolved major axis in degrees; sources at or above 10 arcsec are excluded from compact-source checks |
| `E_RA`, `E_DEC` | Position uncertainties in degrees; sources at or above 2 arcsec are excluded from astrometry checks |

Other PyBDSF columns are diagnostic compatibility data, not yet a required
Hebog public schema. Catalogue ordering, units, null representation, and the
mapping from Hebog's internal records remain to be frozen by contract tests.

## Scientific flow

With beam Measurement Sets, the current implementation runs a full PyBDSF pass
on the true-sky image. That pass detects islands, measures sources, writes the
source-list catalogue and true-sky RMS image, and exports the island mask. A
second pass on the flat-noise image stops after island construction and writes
only its RMS image. Without beam data, the flat-noise image supplies the first
pass and its RMS product is reused.

The mask is clipped to the sector polygon. When mask filtering is enabled,
only sky-model components inside detected emission remain. Surviving true-sky
components are grouped into patches by island. Apparent-sky membership is
matched by component `Name`, and the true-sky patch grouping is transferred.

PyBDSF may fit multiple Gaussian components in an island and group them into
one or more source-list sources. Rapthor consumes the resulting source rows and
island mask; it does not consume PyBDSF's live image, island, Gaussian, or
source objects.

## Empty and failure behaviour

Current behaviour has two empty paths that must be represented explicitly in
tests:

- When processing succeeds but finds no islands, LSMTool writes a dummy
  central sky-model component with negligible flux and reports zero detected
  sources. This row is a serialization workaround, not a scientific source.
- When PyBDSF raises `All pixels in the image are blanked`, Rapthor writes
  header-only sky models, an empty catalogue containing all required columns,
  copies the two input images to the expected RMS paths, and records
  `{"nsources": 0}`. Those copied pixels are placeholders and must not be
  interpreted as RMS estimates.

These behaviours are compatibility observations, not yet scientific approval
of dummy components or copied RMS data. Hebog must test them and either
preserve them at the adapter boundary or replace them through an explicitly
reviewed contract change. Missing required inputs and unexpected processing
errors continue to fail the task rather than producing a silent empty result.

## Execution constraints

Rapthor owns the Prefect/Dask graph, task retries, resource admission, and
restartable file lifecycle. Its current PyBDSF path uses a subprocess when
multi-core PyBDSF would otherwise run inside a daemon worker. Hebog should
remove that tool-specific escape while preserving coarse task boundaries,
serializable path-based results, deterministic ordering, and explicit CPU and
memory budgets.

For future large images, one admitted source-finding operation may expand into
the bounded haloed-tile and hierarchical-reconciliation subgraph defined by
[ADR-005](../architecture/adr/005-scale-large-images-with-hierarchical-tiles.md).
Hebog must use Rapthor's existing client rather than creating a private cluster
or nested process pool, and no worker may require a complete large image
plane.

The boundary is provisional until domain review, frozen examples, and failing
contract tests confirm normal, empty, corrupt, retry, and restart behaviour.

## Corrected baseline interpretation

The first retained Phase 0 campaigns used the `7.5/5.0` helper fallback and
trusted the declared LSMTool commit. They are superseded. The reviewed
comparison anchors now use the rich-demo strategy's explicit `5.0/3.0`
profile, mount clean Rapthor and LSMTool checkouts at their recorded commits,
and verify the imported PyBDSF version, LSMTool module, master wheel, container
digest, input identities, and runner scripts. Released and pinned-master
PyBDSF produce 12 and 14 representative source rows respectively, which is a
reference-version divergence requiring truth-based scientific assessment.
