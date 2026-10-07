# Rapthor FITS catalogue view

`hebog.adapters.rapthor_catalogue` is the eight-column catalogue codec for
Rapthor's `filter_skymodel` diagnostics. It writes and reads the smallest
FITS table Rapthor reads directly, from the catalogue `find_sources`
publishes. It is a compatibility boundary, not yet a Rapthor backend: no
adapter runs `find_sources` or writes its products. The internal catalogue is
described in the [output reference](public-products.md).

## Columns

The codec writes exactly the eight fields read directly by the pinned
Rapthor diagnostic path:

| Column | FITS type | Unit | Internal meaning |
| --- | --- | --- | --- |
| `Source_id` | 32-bit integer | none | deterministic zero-based row number |
| `RA` | 64-bit float | deg | ICRS right ascension |
| `DEC` | 64-bit float | deg | ICRS declination |
| `Isl_Total_flux` | 64-bit float | Jy | parent island pixel-sum flux |
| `Total_flux` | 64-bit float | Jy | the source's published integrated flux |
| `DC_Maj` | 64-bit float | deg | deconvolved major FWHM |
| `E_RA` | 64-bit float | deg | optional formal RA error, as a great-circle angle (not divided by cos(dec)) |
| `E_DEC` | 64-bit float | deg | optional formal Dec error, as a great-circle angle |

`Total_flux` carries the source flux the internal catalogue publishes. For
the continuum profile that is the sum of the source's fitted Gaussian
components, which is how PyBDSF defines it and what Rapthor's photometry
check compares against; a source with no admitted fit carries its signed
aperture. `Isl_Total_flux` is the island sum, which Rapthor carries only
through its astrometry check.

`DC_Maj`, `E_RA` and `E_DEC` are what Rapthor cuts on: it keeps a source
for its checks when `DC_Maj` is under 10 arcsec and both errors are under
2 arcsec. Under `continuum` a source of one fitted Gaussian publishes that
Gaussian's values, so it passes the cuts as a `compact` row does; a source
of several components has no position error and no deconvolved size, so
Rapthor leaves it out of those checks, and plan task 21 measures what that
costs agreement.

Rapthor reads the FITS table with Astropy. Its diagnostic conversion then
writes `Source_id`, `RA`, `DEC`, and the selected flux to a minimal
makesourcedb text model, which LSMTool loads. LSMTool does not directly read
the source-list FITS product, so it is not a core or test dependency of this
adapter.

## Missing values

Internal null deconvolved shapes with the `unresolved` flag become the
PyBDSF-compatible `DC_Maj = 0` sentinel only in this view. Unavailable errors
become FITS NaN values and read back as masked Astropy values; they are never
serialized as zero. The empty catalogue retains all eight columns and zero
rows. The writer requires the `J2000.0` position epoch the finder publishes
(`hebog.data_models.catalogues.POSITION_EPOCH`).

## Publication

The writer uses a same-directory temporary file, validates the closed FITS
product before publication, adds deterministic FITS checksums, reuses an
identical destination on retry, and rejects conflicting existing bytes. The
reader rejects a table whose columns, units or types differ from the schema
above and translates an unreadable file into the codec's own error.

Per-channel catalogue columns used by later Rapthor flux normalization,
complete sky-model filtering, and orchestration are not part of this
boundary.
