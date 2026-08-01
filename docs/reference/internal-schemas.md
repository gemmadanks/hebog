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

## Source catalogue schema version 1

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
NaN and legacy zero sentinels are not null values. A fitted Gaussian always
has a fitted shape; a source-level fitted shape may be unavailable.

The version-one internal catalogue FITS encoding contains exactly three
binary-table extensions: `ISLANDS`, `SOURCES`, and
`GAUSSIAN_COMPONENTS`. Column names are Hebog domain names with explicit FITS
units, not PyBDSF compatibility names. At this serialization boundary only,
an unavailable float is encoded as FITS NaN and decoded back to `None`;
required scientific values remain finite under model validation. Empty
catalogues retain all typed columns and contain zero rows.

Spectral coefficients use fixed-width float64 vectors rather than FITS
variable-length heap columns. Each source or component table selects the
smallest width that contains its longest coefficient tuple, with a one-element
minimum for an empty table. Shorter tuples use trailing NaN padding, which the
reader removes while rejecting infinity, interior padding, and heap-backed
`P`/`Q` formats. This avoids platform-dependent heap bytes and keeps
content-identical catalogue retries deterministic on Windows, Linux, and
macOS.

`SpectralModel` distinguishes a reference-frequency-only MFS measurement from
a log-polynomial spectral fit. For a log-polynomial, coefficient `k`
multiplies `log(frequency / reference_frequency) ** (k + 1)` in natural-log
flux space. Catalogue version 1 requires every source and fitted component to
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

## Compatibility

The internal catalogue does not define PyBDSF column names such as
`Source_id`, `Isl_Total_flux`, or `DC_Maj`. The Rapthor adapter will map the
internal records to those reviewed compatibility fields. FITS readers and
writers will use Astropy at the I/O boundary; the schema models do not contain
Astropy tables, open HDUs, NumPy image planes, or scheduler objects.

These are Hebog's internal final-product encodings, not the Rapthor/PyBDSF
compatibility view. Internal large-catalogue shard storage remains an
evidence-driven decision.
If Arrow or Parquet is adopted for shards, it must preserve this logical
schema and canonical identities rather than introduce a second scientific
model.

See [ADR-006](../architecture/adr/006-isolate-compatibility-with-versioned-schemas.md),
the [domain glossary](domain-glossary.md), and the
[Rapthor source-finding contract](rapthor-source-finding-contract.md).
