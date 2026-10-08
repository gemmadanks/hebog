# Internal catalogue and result schemas

Hebog's internal schemas describe scientific concepts independently of
PyBDSF, LSMTool, Rapthor, FITS column names or a scheduler. They are
immutable Pydantic records that reject unknown fields and unsupported
versions and serialize to canonical JSON. Round-trip and compatibility tests
are the evidence for each one. A semantic change bumps the integer version
and updates this page; stale development products are rejected and
recreated, never migrated
([ADR-006](../architecture/adr/006-isolate-compatibility-with-versioned-schemas.md)).
The public meaning of every product column is in the
[output reference](public-products.md); this page holds the rules the
records enforce.

## Versions

| Record | Version | Module |
| --- | --- | --- |
| `SourceCatalogue` | 3 | `hebog.data_models.catalogues` |
| Catalogue FITS encoding (`HBGSCHE` header card) | 4 | `hebog.io.materialization` |
| `SourceFinderResult`, `MaterializedProduct`, `SourceFinderRequest` | 2, 1, 1 | `hebog.data_models.source_finding` |
| `PublicSourceFindingDiagnostics` (the diagnostics product) | 11 | `hebog.data_models.source_finding` |
| `PublicSourceFindingProvenance`, `ContinuumSourceFindingDiagnostics`, `SourceFindingDiagnostics`, `SourceScaleProvenance` | 3, 2, 1, 1 | `hebog.data_models.source_finding` |
| `ScaleDetection`, `CrossScaleAssociation` | 1, 2 | `hebog.data_models.multiscale` |
| `ProductChunk`, Zarr storage schema, generation marker | 2, 3, 1 | `hebog.data_models.products`, `hebog.io.zarr`, `hebog.data_models.generations` |
| Partition manifest | 1 | `hebog.data_models.partitioning` |
| Staging owner record | 1 | `hebog.io.staging` |
| Rapthor adapter records | 1 | `hebog.adapters.rapthor` |

## Source catalogue

`SourceCatalogue` is one MFS catalogue: a stable identity, the `icrs` frame
and position epoch, one reference frequency in hertz, and ordered
collections of islands, source candidates and fitted Gaussian components.

- The three identities are distinct. A `SourceCandidate` has a primary
  `Island` and zero or more `additional_island_ids`; a `GaussianComponent`
  belongs to one source and a subset of its islands. References are
  validated and IDs are unique and in canonical order, so completion order
  cannot change the persisted bytes.
- An island may have no accepted source, and a source may have no Gaussian.
  A component whose fit is not admitted keeps its detected identity and the
  source keeps its independent aperture measurement, with the reason
  (`fit-model-inadequate`, `fit-linear-algebra-failure`, …) in the
  diagnostics. No zero-valued fit is fabricated, and a source's member count
  need not equal its Gaussian rows.
- Units are in field names: right ascension in `[0, 360)` and declination in
  `[-90, 90]` degrees; FWHM axes in degrees with the angle in `[0, 180)`;
  peak flux and local RMS in Jy/beam; integrated flux in Jy; frequency in Hz.
- Unavailable uncertainties and unavailable or unresolved shapes are `None`,
  never NaN or zero. A major-axis-only deconvolution stores one positive
  major FWHM, a null ellipse and the `major-axis-only` flag. A fitted
  Gaussian always has a fitted shape; a source-level shape may be
  unavailable.
- `GaussianComponent.flux` is the fitted model's infinite-plane integral.
  `SourceCandidate.association_aperture_integrated_flux_jy` is the source's
  signed aperture over its own footprint (`ASSOCIATION_APERTURE_FLUX`), to
  which no fit contributes and which the `compact` profile leaves
  unavailable. Estimator flags keep the two distinct.
- `SpectralModel` distinguishes a reference-frequency-only MFS measurement
  from a log-polynomial fit whose coefficient `k` multiplies
  `log(frequency / reference_frequency) ** (k + 1)`. Every row uses the
  catalogue's one reference frequency; per-channel catalogues are outside
  the contract.
- An empty catalogue has no islands, sources or components and never a dummy
  row.

### FITS encoding

The catalogue FITS file has exactly three binary tables, `ISLANDS`,
`SOURCES` and `GAUSSIAN_COMPONENTS`, with Hebog domain column names and
explicit units. At this boundary only, an unavailable float is NaN and reads
back as `None`; for a major-axis-only result `DECONVOLVED_MAJOR` is positive
while the minor axis and angle are NaN, and the reader rebuilds the one-axis
state from that pattern; the record requires the `major-axis-only` flag to
match it. Spectral coefficients are fixed-width float64
vectors padded with trailing NaN rather than variable-length heap columns, so
identical retries are byte-identical on every platform. Every HDU carries
`CHECKSUM` and `DATASUM` with a fixed provenance comment instead of Astropy's
wall-clock comment, and `ADDITIONAL_ISLAND_IDS` preserves multi-island links.

## Result and diagnostics

`SourceFinderResult` holds the run ID, the source, Gaussian and island
counts, finite wall time and exactly four `MaterializedProduct` records, each
with path, byte count, SHA-256, media type, content schema version and
scientific status:

| Role | Media type | Scientific status |
| --- | --- | --- |
| `source-catalogue` | `application/fits` | `valid` |
| `rms` | `image/fits` | `valid` or `unavailable` |
| `source-filtering-mask` | `image/fits` | `valid` |
| `diagnostics` | `application/json` | `valid` |

Constructing the model does no I/O, and paths must be distinct.
`unavailable` RMS means a successful analysis had no usable noise estimate;
the file is a versioned all-NaN representation of that state, never copied
input pixels.

`PublicSourceFindingDiagnostics` is the diagnostics product. It records the
profile and its limitations, population counts, RMS status, exact provenance
(configuration SHA-256 and composition hash), the deblend-fallback and
wide-object round counts, and `configuration_qualification`:
`development-unqualified` for the 5σ/3σ, seven-pixel configuration without a
maximum island cut and `custom-unqualified` otherwise. Its canonical
`measurement_dispositions` list every detected component and source exactly
once with status `measured`, `unavailable` or `deferred`, the estimator or
failure reason, and whether a catalogue row was published; the per-kind
counts must match the catalogue. Fit attribution keeps the optimizer model,
sample count, noise estimator, bound and conditioning evidence and
covariance availability without arrays; association attribution keeps the
hierarchy, compact-model and morphology group IDs, the selected decision and
each source's `association_evidence`, stored once per source. A joint-fit
linear-algebra failure is recorded as `fit-linear-algebra-failure` for every
component of that fit, with no invented diagnostics. Successful publication
does not imply that every measurement or scientific gate passed.

## Product materialisation

Astropy writes the final FITS products. RMS is a two-dimensional float32 or
float64 image whose dtype is chosen explicitly, non-negative where finite and
NaN where invalid; the mask is uint8 written from exact booleans. RMS and
mask writers take sequential full-width row blocks and validate each, so
peak memory is bounded by the block, not the plane; readers expose the same
products through bounded windows and verify the record's SHA-256 once per
reader. All four writers create and validate a same-directory temporary file
before publishing it. A retry with identical bytes returns the existing
record; one that would replace different bytes raises
`MaterializedProductConflictError`.

## Intermediate Zarr generation

Intermediate planes are one immutable Zarr v3 generation per run
([ADR-007](../architecture/adr/007-use-zarr-for-intermediate-image-storage.md)).
The rules the sink enforces:

- Every canonical tile owns and writes one complete chunk of each product.
  The caller creates each product array (`initialize_product`) before workers
  start, so workers never race metadata creation.
- `ProductChunk` is a small serializable identity: generation ID, core
  bounds, dtype, shape and logical SHA-256, with no open Zarr object or
  pixels. An identical retry reuses a completed chunk; a different value for
  the same product and tile fails closed.
- `publish_generation` requires exactly one record for every product and
  tile, rejects missing, duplicate, conflicting, mixed-generation,
  wrong-owner and inconsistent-dtype records, checksums every chunk and only
  then conditionally creates the completion marker. Identical publications
  are idempotent, a different marker cannot replace the winner, and an
  interrupted run has no marker and resumes by writing its missing chunks.
- `read_generation` validates the marker without re-reading the chunks; each
  chunk is validated against its record whenever it is read. A sink caches
  its array handles and the parsed marker for its lifetime in one process,
  and a pickled copy starts empty.
- Storage schema 3 stores numeric planes uncompressed with CRC32C and boolean
  masks with Zstandard level 1 plus CRC32C; every chunk also carries its
  logical SHA-256. Bounded consumers reuse at most four validated chunks
  while assembling windows, in a worker-local cache.
- `iter_completed_row_blocks` streams a product into FITS one full-width tile
  row at a time, validating each chunk once; a budget below one tile row
  fails before any bytes are written.

Normalized residuals and local label planes are worker temporaries; workers
return component facts and boundary-label vectors, and reconciliation reduces
them through a deterministic pairwise tree. Exact deblended-region labels are
published as component label planes and read back by the fit tasks; no
summary rectangle stands in for membership.

## Multiscale and compact records

`ScaleDetection` describes one finite beam-normalized response with its
global bounds, valid-support fraction, normalized peak, significance and
scale. `CrossScaleAssociation` joins detections across adjacent scales and
records the selected detection explicitly. The moment and fit kernels return
frozen records (`OwnedPixelPhotometry`, `GaussianMomentInitializer`,
`CelestialCompactGaussianFit`) that keep owned-pixel flux distinct from
fitted flux and omit unavailable fields rather than encoding absence as
zero; the [algorithm contracts](compact-measurement.md) describe them. None
of these records contains an image array, WCS object or scheduler state; WCS
objects are rebuilt transiently inside the astrometry boundary.

## Compatibility

The internal catalogue defines no PyBDSF column names. The
[Rapthor catalogue view](rapthor-catalogue-view.md) maps the internal
records to the eight directly consumed fields, and the
[Rapthor source-finding contract](rapthor-source-finding-contract.md) says
what an adapter must reproduce.
