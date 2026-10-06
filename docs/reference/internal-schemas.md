# Internal catalogue and result schemas

Hebog's internal schemas describe scientific concepts independently of
PyBDSF, LSMTool, Rapthor, FITS column names, or a scheduler. They are
immutable Pydantic records, reject unknown fields and unsupported versions,
and serialize to canonical JSON for restart metadata and cross-process
exchange.

Automated round-trip and compatibility tests are the evidence for individual
outputs. The schemas are pre-`1.0`: a later semantic
change requires a new schema version and updated current documentation, and
must not silently reinterpret persisted data. Stale development products may
be rejected and recreated rather than supported through legacy readers or
migration code.

## Source catalogue schema version 3

`SourceCatalogue` represents one MFS catalogue. Catalogue metadata explicitly
records:

- a stable catalogue identity;
- the `icrs` coordinate frame and position epoch;
- the common reference frequency in hertz; and
- separate ordered collections of islands, source candidates, and fitted
  Gaussian components.

The three identities are deliberately distinct. A `SourceCandidate` belongs
to a primary `Island` and zero or more `additional_island_ids`; a
`GaussianComponent` belongs to one source and a subset of that source's
islands. All island references are distinct and canonical. The catalogue
validates those references, rejects duplicate IDs, and
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

The current public composition reports the native fitted Gaussian integral
for components, not for associated-source rows. It does not substitute
peak brightness for integrated flux because threshold-truncated moments look
unresolved. Shape, flux and position errors propagate the fitted covariance;
missing or singular errors remain unavailable. All associated-source
measurements use signed, source-owned observable apertures and unavailable
fitted/deconvolved shapes. Estimator flags distinguish these from other
governed pipeline measurements; different estimators must not be pooled as
like-semantics evidence.

Gaussian publication uses the same numerical, physical-bound and information
conditioning checks for single and joint fits, including free-only fitting
without a beam model. Unresolved noise covariance uses the explicitly flagged
diagonal estimator with correlated-error propagation. Both Gaussian axes must
be positive and obey the configured ratio independent of optimizer ordering.
Failed Gaussian admission preserves source support and its separate source
measurements; convergence alone does not establish astrophysical model adequacy.
Public fallback admission can report `fit-model-inadequate`: a beam fallback
from an invalid free ellipse leaves seeded positive residual emission on its
fitted support. The component disposition is unavailable and its Gaussian row
is absent;
the detected component identity and independent associated-source measurement
are retained. Consequently a source's detected member count need not equal
its number of published Gaussian rows. The existing schema's explicit
unavailable reason carries this distinction; no zero-valued fit is fabricated.

The version-four internal catalogue FITS encoding contains exactly three
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

`ContinuumSourceFindingDiagnostics` schema version 2 retains the same
population and RMS fields and adds terminal-disposition counts plus one
canonical `SourceScaleProvenance` record per extended source. Each provenance
record binds the source and combined island to its association, contributing
detections and scales, selected detection, spatial relationship, accepted
support count, and visible-model fraction. Compact-only materialization keeps
schema version 1 so its diagnostics bytes do not change. When a
`MaterializedProduct` record is supplied, the reader also requires its declared
content schema to match the canonical JSON payload.

`PublicSourceFindingDiagnostics` schema version 11 records the public profile,
profile limitations, population counts, RMS status, exact provenance, the
numbers of connected parents that were deblended or retained through the
bounded deblend fallback, and the wide-object counts of the rounds that
decided an object from its cores rather than from one window. Its
`configuration_qualification` is `development-unqualified` for the repaired
5-sigma/3-sigma, seven-pixel configuration without a maximum island cut; all
other valid caller configurations are `custom-unqualified`. The configuration
SHA-256 still binds every threshold, island-size limit, and profile choice.
This label separates execution from scientific qualification: custom settings
are supported computations but do not inherit the reference evidence. The
changed default science does not inherit earlier qualification either.

Its canonical `measurement_dispositions` records each detected component and
associated source exactly once. A source's member IDs partition the component
population. Status is `measured`, `unavailable` or `deferred`, with exactly the
appropriate estimator or failure reason. `catalogue_row_published` separates
measurement availability from public row admission; its per-kind counts must
match the catalogue counts. No Gaussian row is invented for a degenerate
owner. Catalogue FITS `ADDITIONAL_ISLAND_IDS` preserves the multi-island links.
An island's signed flux statistic can be non-positive without being a valid
positive source measurement. These schema changes reject stale products
without a legacy reader.

The optional array-free fit attribution retains the exact optimizer model,
retained sample count, noise-estimator/fallback reason, bound and conditioning
evidence, covariance availability and parameterization. Circular-coordinate
recovery uses Cartesian Gaussian precision; an undefined angle does not
become a reported zero shape error. Association attribution retains original
hierarchy, compact-model and extended-morphology group IDs with the selected
decision, using constant-size references per component rather than repeated
membership lists. An unsupported hierarchy remainder is labelled
`independent-component`, not an admitted source association. Each source also
retains `association_evidence`: merge reason, supporting scale IDs, member IDs
and any compact-protection overrides. These records must refer only to that
source's members and are stored once per source, not repeated per component
or pixel. They do not establish astrophysical truth or inherit qualification.
Source-position attribution retains both centroid estimates,
the selected weighting rule, unavailable reason, separate position/aperture
counts, signed weights/flux and estimated background mean. It does not claim
to know background error or true RMS on an arbitrary observed image.

A joint Gaussian linear-algebra exception is retained as
`fit-linear-algebra-failure` for every component in that coupled fit. These
components have no published Gaussian row. The internal failed-fit record
has no optimizer diagnostics when a complete validated report is unavailable;
counts, parameters and uncertainties are not fabricated. Independent parents
continue, and an independently valid signed-aperture source remains subject
to its existing admission rules. Successful product publication does not
imply that all measurements or scientific gates passed.

The `catalogue_path`, `rms_path`, `mask_path`, and `diagnostics_path`
properties are conveniences for workflow consumers; producers must create the
corresponding `MaterializedProduct` records.

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

## Intermediate Zarr generation

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

Exact deblended-region labels are published as component label planes and
read back by the bounded fit tasks; no summary rectangle stands in for
membership.

The moment kernel returns frozen compact records, not a durable catalogue
schema. `OwnedPixelPhotometry` keeps finite-mask pixel-sum flux distinct
from fitted-Gaussian flux. A valid result includes a pixel-space
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

`SourceCandidate.association_aperture_integrated_flux_jy` is the source's
signed aperture over its own footprint, published as
`ASSOCIATION_APERTURE_FLUX`; no Gaussian fit contributes to it, and the
compact profile leaves it unavailable. `GaussianComponent.flux` continues to
describe the selected Gaussian model, and materialized Rapthor catalogue
columns retain their reviewed peak/integrated component semantics.

## Multiscale records

The multiscale path adds scheduler-safe scale and association records
without adding image planes to public state. `ScaleDetection` describes one
finite, beam-normalized response and retains its global bounds,
valid-support fraction, normalized peak response, significance, and
contributing scale. A `CrossScaleAssociation` canonically joins scale
detections across adjacent scales and records the selected detection
explicitly rather than letting task or scale iteration order choose a
representation. `CrossScaleAssociation` is schema version 2 and
`ScaleDetection` schema version 1. Both are strict, immutable and contain
only small scalar values and canonical identifiers.

## Compatibility

The internal catalogue does not define PyBDSF column names such as
`Source_id`, `Isl_Total_flux`, or `DC_Maj`. The Rapthor catalogue adapter maps
the internal records to the eight directly consumed compatibility fields.
Astropy remains at the FITS I/O boundary; the schema models do not contain
Astropy tables, open HDUs, NumPy image planes, or scheduler objects.

The current FITS adapter is the Rapthor/PyBDSF compatibility view; the
richer internal FITS schema remains pipeline-neutral.

See [ADR-006](../architecture/adr/006-isolate-compatibility-with-versioned-schemas.md),
the [domain glossary](domain-glossary.md), and the
[Rapthor source-finding contract](rapthor-source-finding-contract.md).
