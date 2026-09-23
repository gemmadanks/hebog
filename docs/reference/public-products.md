# Public source-finder outputs

This reference defines the four-file bundle returned by
`hebog.find_sources()`. It is for astronomers evaluating measurements and for
developers consuming Hebog from another workflow. For the processing decisions
that produce these files, see [How Hebog works](../explanation/how-hebog-works.md).

Hebog is experimental and scientifically unqualified. A successful call means
that Hebog completed and validated its output contract; it does not mean that
the selected thresholds or algorithms are qualified for a survey.

## Product set at a glance

| File | Role and format | Scientific question it answers |
| --- | --- | --- |
| `catalogue.fits` | `source-catalogue`, FITS schema 4 | What islands, associated sources, and admitted Gaussian components were measured? |
| `rms.fits` | `rms`, FITS image schema 1 | What local RMS did thresholding and reported local-noise fields use? |
| `source-mask.fits` | `source-filtering-mask`, FITS image schema 1 | Which input-aligned pixels belong to retained published detections? |
| `diagnostics.json` | `diagnostics`, JSON schema 9 | What was omitted, deferred, selected, or unavailable, and exactly which science produced the bundle? |

Use all four together. In particular, `catalogue.fits` contains only published
measurements, while `diagnostics.json` is the census of measured and
unmeasurable component/source identities.

## The returned result record

`SourceFinderResult` schema 2 is an immutable, scheduler-safe summary. It
contains `run_id`, `source_count`, `gaussian_component_count`, `island_count`,
`wall_seconds`, and four `MaterializedProduct` records named `catalogue`,
`rms`, `mask`, and `diagnostics`.

Every `MaterializedProduct` contains:

| Field | Meaning |
| --- | --- |
| `product_role` | Semantic role; do not infer this from the filename. |
| `path` | Closed local file path, rebased to the published bundle. |
| `media_type` | `application/fits`, `image/fits`, or `application/json`. |
| `byte_count` | Exact file size used for restart validation. |
| `content_sha256` | Lowercase SHA-256 of the complete file bytes. |
| `scientific_status` | `valid`, or `unavailable` for the RMS product only. |
| `content_schema_version` | Version of the referenced file's content. |
| `schema_version` | Version 1 of the materialized-product record itself. |

The convenience properties `catalogue_path`, `rms_path`, `mask_path`, and
`diagnostics_path` return paths only. Pass the full product record to a Hebog
reader when possible: it lets the reader verify role, schema, byte count, and
SHA-256 before parsing.

## Catalogue FITS

### Catalogue populations and relationships

The primary HDU carries no data array. It identifies the product with:

| Header | Meaning |
| --- | --- |
| `HBGROLE=CATALOGUE` | Hebog product role. |
| `HBGSCHE=4` | FITS serialization schema. |
| `CATID` | Stable catalogue identifier derived from the run ID. |
| `HBGFRAME=icrs` | Coordinate frame. |
| `HBGEPCH=J2000.0` | Position epoch. |
| `RESTFRQ` | Common reference frequency in Hz. |

Every HDU also carries standard FITS `CHECKSUM` and `DATASUM` cards. These
detect FITS-level corruption; the result record's SHA-256 identifies the
complete file bytes.

The file then contains exactly three binary-table extensions:

- `ISLANDS`: eight-connected components of the published mask;
- `SOURCES`: measured image-domain associations; and
- `GAUSSIAN_COMPONENTS`: admitted fitted Gaussian models whose parent source
  is also published.

Identifiers are stable domain strings and rows are in canonical identifier
order. A source links to one primary island and zero or more additional
islands. A Gaussian component links to one source and a subset of that
source's islands. These relations permit all of the following:

- one island containing several independent sources;
- one source containing several Gaussian components;
- one source spanning disconnected islands; and
- a source with no Gaussian component because its source-aperture measurement
  succeeded while a component fit did not.

An island is segmentation, a Gaussian component is a model, and a source is an
association hypothesis. None is an assertion of astrophysical truth.

### `ISLANDS` fields

| Column | Unit | Interpretation |
| --- | --- | --- |
| `ISLAND_ID` | — | Stable identifier for one connected published-mask footprint. |
| `PIXEL_COUNT` | pixel | Number of `1` pixels in that footprint. |
| `INTEGRATED_FLUX` | Jy | Signed sum of original background-subtracted footprint pixels divided by the Gaussian restoring-beam area in pixels. It is threshold-support photometry, not a fitted-model integral. |
| `INTEGRATED_FLUX_ERROR` | Jy | The public finder leaves this unavailable. |
| `LOCAL_RMS` | Jy/beam | Median positive finite RMS over the footprint. |
| `MEAN_BRIGHTNESS` | Jy/beam | Mean original background-subtracted brightness over the footprint. |

Island integrated flux and mean brightness may be non-positive. The island can
still be a valid segmentation record even when no positive source measurement
is publishable.

### Fields shared by `SOURCES` and `GAUSSIAN_COMPONENTS`

| Column or group | Unit | Interpretation |
| --- | --- | --- |
| `ISLAND_ID` | — | Primary connected mask island. |
| `ADDITIONAL_ISLAND_IDS` | — | Comma-separated canonical additional island IDs; blank means none. |
| `RIGHT_ASCENSION`, `DECLINATION` | deg | ICRS position, converted from FK5 J2000 when the input uses that frame. RA is in `[0, 360)` and declination in `[-90, 90]`. |
| `RIGHT_ASCENSION_ERROR`, `DECLINATION_ERROR` | deg | Optional one-sigma uncertainties; FITS NaN means unavailable. |
| `PEAK_FLUX` | Jy/beam | Peak brightness for the row's estimator. |
| `PEAK_FLUX_ERROR` | Jy/beam | Optional one-sigma uncertainty. |
| `INTEGRATED_FLUX` | Jy | Integrated flux under the row-specific estimator described below. |
| `INTEGRATED_FLUX_ERROR` | Jy | Optional one-sigma uncertainty. |
| `LOCAL_RMS` | Jy/beam | Median local RMS over the row's owned support. |
| `SPECTRAL_KIND` | — | Currently `reference-frequency-only`; no spectral fit is implied. |
| `REFERENCE_FREQUENCY` | Hz | Frequency at which the flux is reported; it must equal primary `RESTFRQ`. |
| `SPECTRAL_COEFFICIENTS` | — | Fixed-width float64 vector. It is empty for the current reference-frequency-only model; trailing NaN is serialization padding. |
| `FITTED_MAJOR`, `FITTED_MINOR`, `FITTED_POSITION_ANGLE` | deg | Optional fitted FWHM ellipse and astronomical position angle in `[0, 180)`. |
| `FITTED_MAJOR_ERROR`, `FITTED_MINOR_ERROR`, `FITTED_POSITION_ANGLE_ERROR` | deg | Optional one-sigma fitted-shape errors. |
| `DECONVOLVED_MAJOR`, `DECONVOLVED_MINOR`, `DECONVOLVED_POSITION_ANGLE` | deg | Optional restoring-beam-deconvolved FWHM ellipse. |
| `DECONVOLVED_MAJOR_ERROR`, `DECONVOLVED_MINOR_ERROR`, `DECONVOLVED_POSITION_ANGLE_ERROR` | deg | Optional one-sigma deconvolved-shape errors. |
| `QUALITY_FLAGS` | — | Comma-separated canonical interpretation/provenance flags; blank means none. |

Optional floating-point fields use FITS NaN only at the FITS boundary. The
validated Python records decode them to `None`; a missing uncertainty is not
zero. A major-axis-only deconvolution stores the positive major axis, leaves
the minor axis and angle NaN, and includes `major-axis-only`. It is not a
complete ellipse.

### Source-only fields and measurement meaning

`SOURCE_ID` is the source identity. Source measurement semantics depend on the
explicit profile:

- In `continuum`, `INTEGRATED_FLUX` is the binding signed,
  source-owned-aperture measurement. `ASSOCIATION_APERTURE_FLUX` reports that
  same aperture quantity explicitly.
- In `compact`, every published source represents exactly one fitted
  component. `INTEGRATED_FLUX` is its Gaussian-model integral and
  `ASSOCIATION_APERTURE_FLUX` is unavailable.

Source apertures are formed from source ownership and adjacent-scale
persistent support, then expanded by a bounded aperture. Competing
source apertures are non-overlapping: each observable pixel contributes to at
most one source. Measurement-only wings can contribute flux but do not move
the position footprint. The source position is selected from signed original
pixels or the denoised residual according to the recorded position rule. It
may lie between peaks or in the centre of a shell; it is not a host-galaxy
identification.

Continuum source rows do not claim a Gaussian shape when the source is
described by an irregular signed aperture. `FITTED_*` and `DECONVOLVED_*` can
therefore be unavailable even when the source flux and position are valid. A
non-positive or otherwise unavailable signed measurement is not replaced by
positive-only photometry; diagnostics retain the source identity and reason
without publishing a row. Compact-profile source rows carry the fitted and
deconvolved shape of their one component when available.

### Gaussian-component fields and measurement meaning

`GAUSSIAN_COMPONENT_ID` identifies one admitted fit and `SOURCE_ID` identifies
its parent source. `INTEGRATED_FLUX` is the infinite-plane integral of the
selected Gaussian model, including the model's off-image tail. `PEAK_FLUX` is
its fitted peak amplitude. Every Gaussian-component row has a complete fitted
ellipse.

Fits use original background-subtracted pixels and may be solved jointly where
component contexts interact. An admitted fit can be free elliptical, beam
constrained, or centroid-constrained elliptical; the exact model and fallback
evidence live in the component's diagnostic disposition. Failure to admit a
fit removes the Gaussian row. It does not remove the detection footprint or an
independently measurable continuum source. An admitted fit is also omitted if
its parent source measurement cannot be published; the component disposition
still records that the fit succeeded and sets `catalogue_row_published` to
false.

### Interpreting quality flags

Flags are canonical, extensible labels rather than a fixed bit mask. Consumers
must preserve unknown flags. Common current categories include:

| Examples | Meaning |
| --- | --- |
| `original-pixel-gaussian-model`, `joint-gaussian-fit`, `bounded-context-position` | Estimator or fit-context provenance. |
| `resolved`, `unresolved`, `major-axis-only`, `marginal-deconvolution` | Restoring-beam deconvolution state. |
| `extension-not-significant`, `major-axis-not-significant`, `minor-axis-not-significant` | Why geometric extension was not fully admitted. |
| `uncertainty-unavailable`, `shape-uncertainty-unavailable`, `position-flux-uncertainty-unavailable`, `deconvolution-uncertainty-unavailable` | Which uncertainty calculation was unavailable. |
| `fit-at-bound`, `beam-constrained-fit`, `centroid-constrained-fit`, `free-model-not-significantly-extended` | Selected-model and fallback evidence; consult diagnostics for the structured decision. |
| `reconstructed-catalogue-source`, `shape-unavailable`, `resolution-unavailable`, `ambiguous-multiscale-parent` | Associated-source construction and interpretation. |
| `member-...` | A source-level propagation of a member component's flag; it does not change the source estimator. |

Use structured diagnostics, not string parsing, for workflow decisions about
availability, estimator, model selection, or association.

## RMS FITS image

`rms.fits` is a two-dimensional float64 image aligned with the input celestial
WCS. It copies the restoring beam and reference frequency metadata and uses:

| Header | Value or meaning |
| --- | --- |
| `BUNIT` | `Jy/beam` |
| `HBGROLE` | `RMS` |
| `HBGSCHE` | `1` |
| `HBGSTAT` | `VALID` or `UNAVAILABLE` |

For a valid product, finite pixels are non-negative and invalid/unmeasurable
locations may be NaN. A valid status means that at least one finite estimate
exists; it does not claim that every image position has independently resolved
noise information. The continuum estimator can interpolate missing grid cells
and extend fine-grid edge values under its documented policy.

An unavailable RMS product is entirely NaN. In that case the catalogue is
empty and the source mask is zero because sigma thresholding was not defined.
Do not treat NaN as zero noise, invent a floor, or interpret the empty
catalogue as a non-detection statement.

The background estimate is not published in the current public bundle.
`rms.fits` must not be interpreted as a background, residual, variance, weight,
or primary-beam response image.

## Source-filtering mask FITS image

`source-mask.fits` is a two-dimensional uint8 image aligned with the input WCS:

- `1` means the pixel belongs to retained publication support;
- `0` means it does not; and
- `BUNIT=1`, `HBGROLE=MASK`, `HBGSCHE=1`, and `HBGSTAT=VALID` describe the
  product.

The mask is a detection footprint. It is not a clean mask for deconvolution,
a component-label map, a source-owner map, a Gaussian model, or the complete
photometric aperture. Connected `1` pixels define catalogue islands, but
source association is independent of mask connectivity.

Invalid input pixels cannot be members. Persistent multiscale support is
admitted only under the governed boundary and ownership rules; it does not
mean every low-surface-brightness pixel near a source is included.

## Diagnostics JSON

`diagnostics.json` is canonical UTF-8 JSON with sorted keys and one final
newline. Schema 9 rejects unknown fields and contains:

| Field | Meaning |
| --- | --- |
| `run_id` | Caller-provided run identity. |
| `profile` | `continuum` or `compact`. |
| `profile_limitations` | Empty for continuum; `extended-emission-incomplete` for compact. |
| `configuration_qualification` | `development-unqualified` for exact 5/3-sigma, seven-pixel settings with no maximum; otherwise `custom-unqualified`. Neither means scientifically qualified. |
| `source_count`, `gaussian_component_count`, `island_count` | Counts that must agree with the FITS tables. |
| `deblended_parent_count` | Retained connected parents split by bounded deblending. |
| `deferred_deblend_parent_count` | Parents preserved because they exceeded the bounded deblend envelope. |
| `measurement_dispositions` | Complete structured census described below. |
| `rms_scientific_status` | `valid` or `unavailable`, matching the RMS product. |
| `provenance` | Exact input, configuration, science-profile, and implementation identities, and any caller-supplied image metadata. |
| `schema_version` | `9`. |

### Provenance

| Field | Meaning |
| --- | --- |
| `input_sha256` | Bytes of the input FITS file. |
| `configuration_sha256` | Canonical complete `SourceFinderConfig`, including thresholds, size limits, and profile. |
| `scientific_profile_sha256` | Exact installed science-configuration resource. |
| `scientific_composition` | Opaque implementation label. Preserve it for provenance; users do not need to interpret it. |
| `scientific_composition_sha256` | Exact identity of the implementation modules used for the run. |
| `supplied_image_metadata` | `null`, or the `SuppliedImageMetadata` values the request supplied for keywords the input header omits: `reference_frequency_hz`, `beam_major_fwhm_degrees`, `beam_minor_fwhm_degrees` and `beam_position_angle_degrees`, each `null` when not supplied. The input SHA-256 alone does not identify a run that used supplied metadata. |
| `schema_version` | `2` for the nested provenance record. |

Two runs should be treated as the same scientific computation only after the
relevant identities, software/environment context, and product bytes have been
compared. The run ID alone is not a science identity.

### Measurement dispositions

There is one disposition for every established component and source identity,
including objects with no published catalogue row.

| Field | Meaning |
| --- | --- |
| `object_kind`, `object_id` | `component` or `source`, and its stable identity. |
| `status` | `measured`, `unavailable`, or `deferred`. |
| `estimator` | `original-pixel-gaussian-model` or `source-owned-signed-aperture` for measured objects; otherwise null. |
| `reason` | Null for a measurement; explicit cause for unavailable/deferred work. |
| `member_component_ids` | Complete canonical membership for a source; empty for a component. Source memberships partition the component population. |
| `catalogue_row_published` | Whether this exact identity appears in its corresponding FITS table. |
| `fit_covariance_available` | Whether an admitted component fit has formal covariance; null when not applicable. |
| `fit_diagnostics` | Optimizer, model, bounds, conditioning, visibility, and noise-estimator evidence. |
| `position_diagnostics` | Source centroid alternatives, selection rule, counts, signed weights/flux, and background estimate. |
| `association_diagnostics` | Competing hierarchy, compact-model, and extended-morphology group IDs plus the selected decision. |
| `association_evidence` | Evidence stored once for each admitted multi-component merge. |

The number of source dispositions whose `catalogue_row_published` is true
equals `source_count`; the equivalent component count equals
`gaussian_component_count`. This makes it possible to distinguish "not
detected", "detected but not measurable", "measurement deferred", and
"measured and published".

`fit_diagnostics` records convergence, function evaluations, chi-squared and
degrees of freedom, bound contact, selected/rejected model identities,
condition number, covariance parameterization, visible-model fraction,
retained bounds/pixel count, the point estimator, and any estimator or model
fallback reason. These fields
describe estimator behaviour; they are not independent source-quality scores.

`position_diagnostics` records signed-original, denoised, and selected pixel
positions in `(x, y)` order, the selection and unavailable reasons, position
and aperture pixel counts, signed weight, signed aperture flux in Jy, and the
estimated aperture background mean. It does not estimate astrophysical host
position or background truth.

`association_evidence` names the reason (`directional-fwhm-overlap`,
`resolved-loop`, `resolved-open-arc`, or `persistent-residual`), contributing
scale IDs, all member components, and any overridden compact protection. It is
evidence for an image-domain grouping decision, not confirmation that the
members are one physical object.

Fit and association-decision diagnostics apply to component dispositions.
Position diagnostics and association evidence apply to source dispositions.
Fields that are not meaningful for that object or outcome are null or empty;
consumers should not substitute zero or an inferred default.

## Reading and validating the bundle

Use the public product records rather than bare paths when consuming an
in-process result:

```python
from hebog.data_models import ImageBounds
from hebog.io import (
    FitsProductImageSource,
    read_catalogue_fits_product,
    read_diagnostics_product,
)

catalogue = read_catalogue_fits_product(result.catalogue)
diagnostics = read_diagnostics_product(result.diagnostics)

rms_source = FitsProductImageSource(result.rms)
mask_source = FitsProductImageSource(result.mask)
height, width = rms_source.metadata().shape_yx
full_image = ImageBounds(0, height, 0, width)
rms = rms_source.read_window(full_image).values
mask = mask_source.read_window(full_image).values.astype(bool)
```

The readers fail on a mismatched role, unsupported schema, changed byte count
or SHA-256, malformed FITS structure, noncanonical diagnostics JSON, invalid
units, negative RMS, or non-binary mask. Bounded `ImageBounds` windows avoid
forcing an integrating pipeline to load a complete image product.

Consumers outside Python can read the exact FITS structure above, but should
still preserve unknown quality flags, check `HBGROLE`, `HBGSCHE`, and
`HBGSTAT`, and verify the result record's byte identity before trusting a
persisted product.

## Failure handling

Configuration construction raises `ValueError` for invalid threshold ordering,
pixel limits, or profile names. Once `find_sources()` is called, its public
exceptions let a pipeline handle failures without parsing message text:

| Exception | Meaning |
| --- | --- |
| `SourceFinderOutputExistsError` | The caller-owned output path already exists; Hebog will not overwrite it. Publication claims the destination atomically, so a path another writer creates while the analysis runs is reported here rather than replaced. Products then appear in one rename; treat a successful return, not the directory's existence, as the completion boundary. |
| `InvalidSourceFinderInputError` | The FITS file cannot be read as a supported image. |
| `UnsupportedSourceFinderConfigurationError` | The image's physical unit or celestial frame (other than ICRS or FK5 J2000) is outside the public contract. |
| `SourceFinderImageTooLargeError` | A spatial dimension exceeds 3,000 pixels. |
| `SourceFinderError` | Base class for other failures at the public boundary. |

Input, configuration, and existing-output failures do not publish the requested
bundle. Analysis or product-validation failures use the same all-or-nothing
directory boundary, so the caller can retry after addressing the cause.

## Evaluation checklist for astronomers

Before using a bundle as scientific evidence:

1. Confirm the input identity, implementation identity, profile, configuration
   identity, and `configuration_qualification` in diagnostics.
2. Inspect the RMS image and its status; do not evaluate completeness where
   sigma thresholding was unavailable or the estimator resolution is
   inappropriate for the noise structure.
3. Overlay `source-mask.fits` on the original and background-subtracted image,
   especially around edges, invalid pixels, close blends, and diffuse
   emission.
4. Compare like populations: Hebog `GAUSSIAN_COMPONENTS` against component
   catalogues, and Hebog `SOURCES` against source-level catalogues. Do not use
   source count alone as a component-recovery metric.
5. Examine dispositions for missing Gaussian rows, unavailable signed source
   measurements, bounded-work deferrals, model fallback, and covariance
   availability.
6. Treat low-S/N crossings as completeness/reliability changes and stratify
   astrometry, peak flux, integrated flux, and shape residuals by S/N,
   morphology, edge distance, crowding, and invalid-pixel context.
7. Remember that current successful products are development outputs, not a
   general qualification claim or a validated replacement for every PyBDSF
   mode.

## Integration checklist for developers

- Construct a new caller-owned output directory for each attempt; Hebog never
  overwrites an existing path.
- Keep `SourceFinderRequest` and `SourceFinderResult` as small path-and-metadata
  records. Do not pass open FITS handles, mutable image arrays, or scheduler
  clients through workflow state.
- Supply `SerialExecutor()` for the deterministic reference or
  `DaskExecutor(existing_client)` when the workflow owns a Dask client. Hebog
  does not create or close the cluster.
- Branch on public exception types, product roles, schema versions, and
  scientific status rather than error-message text or filenames.
- Wait for `find_sources()` to return before exposing the bundle. Its final
  directory rename is the completeness boundary.
- Persist the complete result record with workflow provenance. A copied file
  path without its role, schema, byte count, and SHA-256 loses restart safety.
- Pin an exact Hebog `0.x` version and review schema/release notes before
  upgrading; the project does not promise backward compatibility between
  experimental releases.
