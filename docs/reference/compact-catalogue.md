# Compact catalogue construction and Rapthor FITS view

The compact catalogue stage turns a complete set of valid compact fits into
the internal catalogue and the smallest FITS table directly consumed by
Rapthor. This is an experimental compact-source boundary, not yet a Rapthor
backend.

## Internal records and association

`Island`, `GaussianComponent`, and `SourceCandidate` remain separate records.
For the currently reviewed compact policy, each successfully fitted deblended
region creates one Gaussian component and one source while retaining its
reconciled parent island. Source and component IDs derive from the global
region ID, and all output is sorted by those IDs rather than executor
completion order.

Source and component models may deliberately differ. The source retains the
reviewed five-sigma beam-or-free selection and Rapthor flux semantics. A
Gaussian component uses the complete free ellipse only when the same log-area
evidence exceeds its explicit 1.5-sigma component boundary; otherwise it uses
the complete beam-constrained ellipse. The component retains the fitted total
of whichever whole model it publishes for like-product PyBDSF/Aegean
comparison. It never combines axes from one fit with position angle from
another.

The worker stage emits one `CompactCatalogueShard` per existing coarse batch;
it does not create one scheduler task per fit or source. Shards combine through
deterministic pairwise levels, so fan-in is two and reported reduction depth is
logarithmic. Final in-memory assembly has an explicit source-record cap. The
phase therefore has a bounded convenience path for qualified compact cases,
while a future larger catalogue can add streaming materialization without
changing the scientific records.

A normal completed catalogue fails closed if any admitted fit is unavailable,
any compact result was omitted, or any multiscale island was deferred.
An explicitly incomplete stage result retains those reasons for inspection but
cannot masquerade as a successful `find_sources` result.

## Preservation boundary

Multiscale pre-association work does not rebuild a completed compact
catalogue. `preserve_unassociated_compact_catalogue` accepts only
`extended-only` scale associations that contain no compact source identity and
returns the exact same `CompletedCompactCatalogue` object. Consequently its
islands, sources, Gaussian components, identities, values, canonical JSON,
and reduction evidence cannot be reordered or recomputed.

Any `contains-compact-support` or `overlaps-compact-support` relationship
raises
`CompactAssociationDecisionRequiredError`. Such evidence must pass through the
governed ownership and association rules before it can affect a
combined catalogue. The same no-op catalogue produces byte-identical Rapthor
FITS output. The RMS plane and the accepted compact mask remain immutable
read-only inputs to the bounded multiscale stages rather than products this
boundary can replace.

The subsequent combined-identity stage still preserves every compact source
and Gaussian-component ID. A compact-only graph component also keeps its exact
compact island ID. Spatial context may place compact and extended sources in a
new combined island, but it never relabels the compact objects or fabricates a
Gaussian component for an irregular extended source.

## Rapthor compatibility FITS

The adapter writes exactly the eight fields read directly by the pinned
Rapthor diagnostic path:

| Column | FITS type | Unit | Internal meaning |
| --- | --- | --- | --- |
| `Source_id` | 32-bit integer | none | deterministic zero-based row number |
| `RA` | 64-bit float | deg | ICRS right ascension |
| `DEC` | 64-bit float | deg | ICRS declination |
| `Isl_Total_flux` | 64-bit float | Jy | parent island pixel-sum flux |
| `Total_flux` | 64-bit float | Jy | unresolved peak flux or resolved fitted source flux |
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

The internal and Rapthor-compatible `Total_flux` follows the reviewed
radio-catalogue policy: an unresolved source uses its peak flux density as the
best total-flux estimate; a significantly resolved source uses peak multiplied
by fitted Gaussian area divided by restoring-beam area. The raw governed
PyBDSF fixture contains an unresolved row whose free-fit total is about 39%
below its peak. Hebog deliberately does not reproduce that physically
implausible low-SNR result. Equivalence tests preserve the raw reference bytes,
record the divergence, and canonicalize only the unresolved catalogue view for
the community-policy comparison. Rapthor's use of `Total_flux` outside its
current diagnostic selection must be reviewed before Hebog becomes its
default backend.

The writer uses a same-directory temporary file, validates the closed FITS
product before publication, adds deterministic FITS checksums, reuses an
identical destination on retry, and rejects conflicting existing bytes.

## Limitations

Sub-beam pairs that produce only one observable image maximum are one
observable truth group, not two sources: a one-region/one-source policy cannot
claim completeness for them, and the equivalence tests use explicit observable
truth groups. Marginal-extension integrated-flux outliers are reported
separately from the gated outlier populations, and the fitter keeps centroids
within sampled image bounds.

Per-channel catalogue columns used by later Rapthor flux normalization,
complete sky-model filtering, and orchestration are not part of this
boundary.
