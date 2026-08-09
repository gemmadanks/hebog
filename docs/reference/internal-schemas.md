# Internal catalogue and result schemas

Hebog's internal schemas describe scientific concepts independently of
PyBDSF, LSMTool, Rapthor, FITS column names, or a scheduler. They are
immutable Pydantic records, reject unknown fields and unsupported versions,
and serialize to canonical JSON for restart metadata and cross-process
exchange.

These Phase 1 schemas are versioned but remain provisional until the Phase 0
human scientific sign-off is recorded. That review approves the meaning and
fitness of the schema; automated round-trip and compatibility tests remain the
evidence for individual outputs. A later semantic change requires a new schema
version and updated current documentation; it must not silently reinterpret
persisted data. Before `1.0`, stale development products may be rejected and
recreated rather than supported through legacy readers or migration code.

## Source catalogue schema version 2

`SourceCatalogue` represents one MFS catalogue. Catalogue metadata explicitly
records:

- a stable catalogue identity;
- the `icrs` coordinate frame and position epoch;
- the common reference frequency in hertz; and
- separate ordered collections of islands, source candidates, and fitted
  Gaussian components.

The three identities are deliberately distinct. A `SourceCandidate` belongs
to one `Island`; a `GaussianComponent` belongs to one source and the same
island. The catalogue validates those references, rejects duplicate IDs, and
requires canonical ID order so worker completion order cannot change the
persisted bytes. An island may have no accepted source when measurement or
fitting fails, and a source may have no fitted Gaussian when a non-Gaussian
measurement is retained.

Source and component records contain a sky position, peak and integrated flux,
local RMS, a spectral model, optional fitted and deconvolved shapes, and
canonical quality-flag names. Units are part of field names:

| Quantity | Canonical representation |
| --- | --- |
| Right ascension | degrees in `[0, 360)` |
| Declination | degrees in `[-90, 90]` |
| FWHM axes and position angle | degrees; angle in `[0, 180)` |
| Peak flux and local RMS | Jy/beam |
| Integrated flux | Jy |
| Reference frequency | Hz |

Unavailable uncertainties and unavailable or unresolved shapes are `None`.
A major-axis-only deconvolution stores one positive
`deconvolved_major_fwhm_degrees` value, leaves the ellipse null, and carries a
`major-axis-only` quality flag; it never invents a minor axis or position
angle. NaN and legacy zero sentinels are not null values. A fitted Gaussian
always has a fitted shape; a source-level fitted shape may be unavailable.

For a compact Gaussian, the fitted pixel record retains the free-model
infinite-plane integral. The celestial component/source record reports peak as
integrated flux when extension is not significant, and the free-model integral
only when extension passes the configured uncertainty test. This is a current
catalogue semantic, not a change to the meaning of the retained fit parameter.

The version-three internal catalogue FITS encoding contains exactly three
binary-table extensions: `ISLANDS`, `SOURCES`, and
`GAUSSIAN_COMPONENTS`. Column names are Hebog domain names with explicit FITS
units, not PyBDSF compatibility names. At this serialization boundary only,
an unavailable float is encoded as FITS NaN and decoded back to `None`;
required scientific values remain finite under model validation. Empty
catalogues retain all typed columns and contain zero rows.

For a major-axis-only result, `DECONVOLVED_MAJOR` contains the positive axis
while `DECONVOLVED_MINOR` and `DECONVOLVED_POSITION_ANGLE` are NaN. The reader
reconstructs the explicit one-axis state from those columns and the canonical
quality flag. This uses the retained shape columns and does not treat a
partial ellipse as a valid `GaussianShape`.

Spectral coefficients use fixed-width float64 vectors rather than FITS
variable-length heap columns. Each source or component table selects the
smallest width that contains its longest coefficient tuple, with a one-element
minimum for an empty table. Shorter tuples use trailing NaN padding, which the
reader removes while rejecting infinity, interior padding, and heap-backed
`P`/`Q` formats. This avoids platform-dependent heap bytes and keeps
content-identical catalogue retries deterministic on Windows, Linux, and
macOS.

Every catalogue HDU carries FITS `CHECKSUM` and `DATASUM` cards with a fixed
Hebog provenance comment. Astropy's default wall-clock checksum comment is not
used, because it would make otherwise identical retry output differ by write
time.

`SpectralModel` distinguishes a reference-frequency-only MFS measurement from
a log-polynomial spectral fit. For a log-polynomial, coefficient `k`
multiplies `log(frequency / reference_frequency) ** (k + 1)` in natural-log
flux space. Catalogue version 2 requires every source and fitted component to
use the catalogue's one reference frequency. Per-channel association and
mixed-frequency catalogues remain outside the initial MFS contract.

An empty catalogue contains no islands, sources, or Gaussian components. It
is valid and never contains a dummy scientific source. A Rapthor compatibility
writer may add a clearly identified legacy serialization workaround only if
its versioned adapter contract requires one.

## Materialised result schema version 2

`SourceFinderResult` version 2 contains one exact set of four
`MaterializedProduct` records:

| Role | Media type | Scientific status |
| --- | --- | --- |
| `source-catalogue` | `application/fits` | `valid` |
| `rms` | `image/fits` | `valid` or `unavailable` |
| `source-filtering-mask` | `image/fits` | `valid` |
| `diagnostics` | `application/json` | `valid` |

Each product records its path, byte count, SHA-256, media type, content schema
version, and scientific status. Model construction performs no file I/O. The
result also records its run ID; source, Gaussian-component, and island counts;
and finite wall time. Product paths must be distinct.

`unavailable` RMS means a successful analysis could not produce a scientific
RMS estimate, for example because all image pixels were blank. The file at the
recorded path must contain a versioned representation of that state; input
pixels copied to an RMS filename are not relabelled as an RMS estimate. Empty
catalogue and mask products remain structurally valid files.

`SourceFindingDiagnostics` schema version 1 is the canonical JSON content of
the diagnostics product. It records the run ID, source, Gaussian-component,
and island counts, plus the RMS scientific status. Its population constraints
match `SourceFinderResult`, and readers reject noncanonical JSON, unknown
versions, and extra fields.

Version 2 replaces the earlier path-only `SourceFinderResult` constructor.
The `catalogue_path`, `rms_path`, `mask_path`, and `diagnostics_path`
properties remain available to workflow consumers, but producers must create
the corresponding `MaterializedProduct` records. No implemented Hebog
source-finding pipeline emitted the version 1 scaffold.

## Product materialisation

Astropy writes the final internal FITS products. Catalogue output is a
versioned FITS table. RMS output is a two-dimensional float32 or float64 FITS
image whose dtype is chosen explicitly; finite estimates must be
non-negative, invalid pixels remain NaN, and an `unavailable` RMS is entirely
NaN. The source-filtering mask is a dimensionless two-dimensional FITS image
written from exact boolean input as binary uint8 values.

RMS and mask writers accept sequential full-width row blocks. They validate
each block and the final row count while writing, so peak Python memory is
bounded by a caller-provided block rather than the complete plane. The FITS
reader exposes the same products through bounded `ImageBounds` windows. It
verifies the `MaterializedProduct` SHA-256 once per reader instance and then
validates each requested window's RMS or binary-mask semantics.
Catalogue and diagnostics readers also accept their `MaterializedProduct`
record and verify its role, content-schema version, byte count, and SHA-256
before parsing. A bare path remains available for initial imports and the
writer's temporary-file validation.

All four writers create and validate a same-directory temporary file before
publishing it under the requested name. A sequential retry with identical
bytes returns the existing product record; a retry that would replace
different bytes fails with `MaterializedProductConflictError`. Publication
does not weaken the separate deployment-store concurrency qualification gate.

## Phase 3 intermediate generation

The compact-detection stage publishes one immutable Zarr v3 generation with
exactly three two-dimensional products: float64 `background`, float64 `rms`,
and boolean `source-filtering-mask`. Every canonical tile owns and writes one
complete chunk of each product. The completion manifest is not published
until all expected chunks validate by generation, geometry, dtype, byte
checksum, and scientific product name.

Normalized residuals and local label planes are bounded worker temporaries,
not durable products or scheduler results. Workers return component facts and
four boundary-label vectors only. Reconciliation reduces those summaries
through a deterministic pairwise tree, then a second bounded tile pass
recreates local labels and writes accepted boolean mask cores using the small
local-to-global mapping. This explicit extra image read avoids making a
diagnostic label plane a correctness or restart prerequisite.

Automatic adaptive-RMS discovery similarly uses a separate bounded scan of
the cached coarse interpolation. Its explicit strict high-significance
threshold is distinct from source detection thresholds. Cross-tile candidate
fragments reconcile before one lexicographically tie-broken global peak per
component requests sparse fine-grid refinement. Coarse window statistics are
reused, not recomputed.

Internal storage schema version 3 keeps Zstandard level 1 for boolean masks
but stores numeric image planes uncompressed; every chunk retains CRC32C and
logical SHA-256 validation. This avoids measured compression cost on numeric
intermediate planes without introducing another backend. Bounded consumers
reuse at most four validated chunks while assembling multiple compact-island
windows. The cache is worker-local and cannot grow with the image or island
count.

Phase 4 exact region labels remain transient worker data. A
`WorkerLocalRegionBatch` aligns immutable float64 physical residual and RMS,
boolean validity, and int32 region labels with reconciled island and region
records. It is an in-task scientific-kernel input, not a durable schema or a
scheduler result. `CompactRegionStageResult` contains only processor-produced
compact records, deblending summaries, explicit Phase 5 deferrals, batch
counts, admitted bounds pixels, and the largest retained processor-array byte
count. A summary rectangle cannot be deserialized into membership.

The Phase 4 moment processor returns frozen compact records, not a durable
catalogue schema. `OwnedPixelPhotometry` keeps finite-mask pixel-sum flux
distinct from fitted-Gaussian flux. A valid result includes a pixel-space
`GaussianMomentInitializer`; shape-unavailable and fully unavailable union
members omit invalid fields rather than encoding scientific absence as zero.
These records contain no image arrays, WCS objects, or scheduler state.

A valid compact fit adds frozen pixel parameters, optimizer diagnostics,
local RMS, optional formal covariance, and optional mask-aware
`AssociationAperturePhotometry`. The aperture record retains its configured
sigma radius, integrated flux, visible selected-model fraction, and pixel
count; it contains no image array. `CelestialCompactGaussianFit`
then supplies the ICRS position, fitted sky ellipse, explicit deconvolution
state, fitted flux, and canonical quality flags. An unresolved deconvolution
has a null shape internally; zero axes are compatibility serialization only.
`extension-not-significant` distinguishes a noisy geometric deconvolution that
failed the significance test, and
`deconvolution-uncertainty-unavailable` distinguishes a fit that could not be
classified because its flux uncertainty was unavailable.
WCS objects are reconstructed transiently inside the astrometry boundary and
never enter a public record or executor result.

Catalogue FITS schema version 3 replaces the earlier fixed-beam association
aperture with
`SourceCandidate.association_aperture_integrated_flux_jy`. It uses the
restoring-beam ellipse when that contains at least 90% of the fitted model and
otherwise follows the selected-fit ellipse so rotated and elongated blends are
not clipped by the restoring beam's narrow axis. `GaussianComponent.flux`
continues to describe the selected Gaussian model, and materialized Rapthor
catalogue columns retain their reviewed peak/integrated component semantics.

## Phase 5 multiscale records

Phase 5 introduces six internal records without changing the published
catalogue schema. `ScaleDetection` describes one finite,
beam-normalized response and retains its global bounds, valid-support
fraction, normalized peak response, significance, and contributing scale. A
`CrossScaleAssociation` canonically joins scale detections and, when present,
one compact source. It records the selected detection explicitly rather than
letting task or scale iteration order choose a catalogue representation.

`ExtendedEmissionMeasurement` schema version 2 stores a detected-segment flux
centroid and brightest original-pixel coordinate as distinct fields. It
explicitly records that neither is a host position. Its position covariance is
unavailable until nonlinear segment-selection uncertainty has a validated
per-source approximation; flux-uncertainty availability remains independent.
It also stores association-level flux and beam-normalized extent. The other
five Phase 5 records remain at schema version 1.
`MultiscaleOmission` is a typed fail-closed explanation for unavailable scale
support, measurement, or association. `CombinedIslandDisposition` gives every
accepted or deferred island exactly one terminal state. Finally,
`CombinedCatalogueState` joins the canonical identifiers and makes
publication eligibility false whenever an omission or incomplete disposition
remains.

All six records are strict, immutable, and scheduler safe. They contain only
small scalar values and canonical identifiers: worker-local arrays, open
files, WCS objects, executor clients, and task state remain outside the
schema. These records freeze meanings for development; they do not yet claim
that the Phase 5 combined catalogue algorithm is implemented.

## Compatibility

The internal catalogue does not define PyBDSF column names such as
`Source_id`, `Isl_Total_flux`, or `DC_Maj`. The Rapthor catalogue adapter maps
the internal records to the eight directly consumed compatibility fields.
Astropy remains at the FITS I/O boundary; the schema models do not contain
Astropy tables, open HDUs, NumPy image planes, or scheduler objects.

`CompactCatalogueShard` is one bounded coarse-task result. Shards combine in
canonical pairwise levels and final in-memory construction has an explicit
record cap. The current FITS adapter is the Rapthor/PyBDSF compatibility view;
the richer internal FITS schema remains pipeline-neutral. Durable streaming of
larger shard populations remains an evidence-driven extension. It must reuse
the Zarr boundary or receive an ADR amendment rather than adding Arrow or
Parquet speculatively.

See [ADR-006](../architecture/adr/006-isolate-compatibility-with-versioned-schemas.md),
the [domain glossary](domain-glossary.md), and the
[Rapthor source-finding contract](rapthor-source-finding-contract.md).
