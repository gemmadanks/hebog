# Internal catalogue and result schemas

Hebog's internal schemas describe scientific concepts independently of
PyBDSF, LSMTool, Rapthor, FITS column names, or a scheduler. They are
immutable Pydantic records, reject unknown fields and unsupported versions,
and serialize to canonical JSON for restart metadata and cross-process
exchange.

These Phase 1 schemas are versioned but remain provisional until the Phase 0
human scientific sign-off is recorded. A later semantic change requires a new
schema version and migration note; it must not silently reinterpret persisted
data.

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

Version 2 replaces the earlier path-only `SourceFinderResult` constructor.
The `catalogue_path`, `rms_path`, `mask_path`, and `diagnostics_path`
properties remain available to workflow consumers, but producers must create
the corresponding `MaterializedProduct` records. No implemented Hebog
source-finding pipeline emitted the version 1 scaffold.

## Compatibility and file formats

The internal catalogue does not define PyBDSF column names such as
`Source_id`, `Isl_Total_flux`, or `DC_Maj`. The Rapthor adapter will map the
internal records to those reviewed compatibility fields. FITS readers and
writers will use Astropy at the I/O boundary; the schema models do not contain
Astropy tables, open HDUs, NumPy image planes, or scheduler objects.

Internal large-catalogue shard storage remains an evidence-driven decision.
If Arrow or Parquet is adopted for shards, it must preserve this logical
schema and canonical identities rather than introduce a second scientific
model.

See [ADR-006](../architecture/adr/006-isolate-compatibility-with-versioned-schemas.md),
the [domain glossary](domain-glossary.md), and the
[Rapthor source-finding contract](rapthor-source-finding-contract.md).
