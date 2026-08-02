# Compact catalogue construction and Rapthor FITS view

Phase 4 can turn a complete set of valid compact fits into the version-one
internal catalogue and the smallest FITS table directly consumed by Rapthor.
This is an experimental compact-source boundary, not yet the public
`find_sources` result or a Rapthor backend.

## Internal records and association

`Island`, `GaussianComponent`, and `SourceCandidate` remain separate records.
For the currently reviewed compact policy, each successfully fitted deblended
region creates one Gaussian component and one source while retaining its
reconciled parent island. Source and component IDs derive from the global
region ID, and all output is sorted by those IDs rather than executor
completion order.

The worker stage emits one `CompactCatalogueShard` per existing coarse batch;
it does not create one scheduler task per fit or source. Shards combine through
deterministic pairwise levels, so fan-in is two and reported reduction depth is
logarithmic. Final in-memory assembly has an explicit source-record cap. The
phase therefore has a bounded convenience path for qualified compact cases,
while a future larger catalogue can add streaming materialization without
changing the scientific records.

A normal completed catalogue fails closed if any admitted fit is unavailable,
any compact result was omitted, or any Phase 5 multiscale island was deferred.
An explicitly incomplete stage result retains those reasons for inspection but
cannot masquerade as a successful `find_sources` result.

## Rapthor compatibility FITS

The adapter writes exactly the eight fields read directly by the pinned
Rapthor diagnostic path:

| Column | FITS type | Unit | Internal meaning |
| --- | --- | --- | --- |
| `Source_id` | 32-bit integer | none | deterministic zero-based row number |
| `RA` | 64-bit float | deg | ICRS right ascension |
| `DEC` | 64-bit float | deg | ICRS declination |
| `Isl_Total_flux` | 64-bit float | Jy | parent island pixel-sum flux |
| `Total_flux` | 64-bit float | Jy | fitted source flux |
| `DC_Maj` | 64-bit float | deg | deconvolved major FWHM |
| `E_RA` | 64-bit float | deg | optional formal RA error |
| `E_DEC` | 64-bit float | deg | optional formal Dec error |

Rapthor reads the FITS table with Astropy. Its diagnostic conversion then
writes `Source_id`, `RA`, `DEC`, and the selected flux to a minimal
makesourcedb text model, which LSMTool loads. LSMTool does not directly read
the source-list FITS product, so it is not a core or test dependency of this
adapter.

Internal null deconvolved shapes with the `unresolved` flag become the
PyBDSF-compatible `DC_Maj = 0` sentinel only in this view. Unavailable errors
become FITS NaN values and read back as masked Astropy values; they are never
serialized as zero. The empty catalogue retains all eight columns and zero
rows.

The writer uses a same-directory temporary file, validates the closed FITS
product before publication, adds deterministic FITS checksums, reuses an
identical destination on retry, and rejects conflicting existing bytes.

## Evidence and limitations

The same three-row Hebog compact catalogue passes the complete frozen Phase 4
position, flux, fitted/deconvolved shape, classification, uncertainty
availability, association, and catastrophic-outlier gates against both the
released and pinned-`master` PyBDSF products. Rapthor's 10-arcsec deconvolved
major-axis and 2-arcsec position-error diagnostic cuts retain the same three
rows. Pixel-centre mask decisions on this no-deferral reference agree with both
PyBDSF masks above the 99.5% downstream threshold.

The close-pair regression has also exposed a necessary contract amendment:
three sub-beam pairs contain only one observable image maximum, so a frozen
one-region/one-source policy cannot claim seven-source completeness. That
population is not being silently tuned or relabelled. It requires a reviewed
decision on resolvability and multi-component fitting, followed by a replacement
unseen qualification dataset before Phase 4 can pass its release gate.

Per-channel catalogue columns used by later Rapthor flux normalization,
multiscale/extended emission, complete sky-model filtering, and orchestration
remain later-phase work.
