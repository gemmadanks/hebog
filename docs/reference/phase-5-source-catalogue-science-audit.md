# Phase 5 source-catalogue science audit

**Date:** 2026-09-07. **Disposition:** review complete; scientific fixes and
new execution remain prospective. This is not a replacement campaign result
or an approved implementation identity.

The reviewed checkout was `1dedd0de18a8440c70be2887780e5a9e282dba2a`.
`git diff 95cfc76ded56556dc3ad6894410962d34f0d5604 HEAD -- src/hebog`
was empty: the audited package is the sentinel candidate's science.

The source-aligned sentinel completed 168 Hebog/PyBDSF pairs and 12 successful
Serial/existing-Dask comparisons. Terminal SHA-256
`ca03240db8452d84479139e848c0467815fdac9cea02168283fe69f52be8b63a`
records 24 passing cells, 18 failing cells and 59 failed cell-endpoints.
Both finders were measured independently against the same analytic truth;
PyBDSF is not truth. Those endpoints are correlated consequences, not 59
independent implementation bugs.

The authoritative `plans/source-finder-implementation.md` contains ordered
repair tasks R0--R6. This review changes no source-finding
code, frozen scientific rule, comparator, output or qualification status.
The numerical probes below use small independent analytic arrays or existing
unit-fixture geometry, not the viewed sentinel inputs.

## Findings

### F1 — P1: hierarchy association can undo compact separation

**Location:** `src/hebog/validation/products.py`,
`build_hebog_reconstructed_source_catalogues`, and
`src/hebog/algorithms/source_association.py`,
`_scale_aware_parent_evidence` / `_hierarchy_groups`.

The public path deblends first, then uses direct-component records and
multiscale hierarchy evidence to assign source membership. The hierarchy
can rejoin separately recovered compact peaks. The two- and three-peak public
fixtures in `tests/unit/test_public_science.py` explicitly require two/three
component rows but only one associated source; they test component retention,
not independent astronomical-source separation.

The previous diagnostic reproduced those exact fixtures. Their component
centres stay near the injected peaks, but source flux and centroid combine
them. This is consistent with sentinel connected-source completeness of
`0.5` and `0.3333`, versus `1.0` for PyBDSF, and the accompanying large flux
and position errors. The absent per-image records prevent identification of
the precise hierarchy branch in each sentinel realization.

**Remedy / acceptance:** R1 must use explicit independent-source truth and
separate single-source extended fixtures. Review compact separation, saddle
and multiscale evidence jointly; neither common support nor component count
alone establishes physical association. Retain both source and component
products. Protect working extended associations while correcting overmerging.

### F2 — P1: threshold-truncated moments are published as deconvolved sizes

**Location:** `src/hebog/validation/products.py`,
`_segment_pixel_moment_covariance` and `_moment_shape_fields`.

Shape covariance uses positive residual pixels on the accepted owner support.
It is converted directly to a Gaussian-equivalent FWHM and beam-deconvolved,
without a correction for the detection boundary or a fitted Gaussian model.
For a Gaussian, excluding its wings systematically narrows those moments.

A deterministic 65-by-65 fixture uses one-arcsecond pixels, a circular
four-arcsecond restoring beam, zero background, unit RMS, and
`A * exp(-4 * log(2) * ((x-32)**2 + (y-32)**2) / 7**2)`.
For the exact owner `signal >= 3`, the current public measurement helper gives:

| Peak/RMS | True observed FWHM | Moment FWHM | Returned deconvolution |
| --- | ---: | ---: | --- |
| 6 | 7 arcsec | 3.804 arcsec | Unresolved |
| 10 | 7 arcsec | 4.926 arcsec | Resolved, underestimated |
| 100 | 7 arcsec | 6.600 arcsec | Resolved, underestimated |

The true intrinsic FWHM is `sqrt(7**2 - 4**2) = 5.7446` arcsec in every row.
The configured public science builder, supplied with the same analytic
background/RMS, also reproduces all three widths for both its source and
component rows; its support sizes are 37, 69 and 193 pixels respectively.
These are noiseless composition/estimator tests, not observed campaign biases.
The `segment-moment-equivalent-shape` flag identifies the estimator but does not
make a physically resolved source unresolved. Public component records expose
these as `fitted_shape`; the Rapthor adapter translates an unresolved flag
into zero deconvolved major axis. Size-dependent selection and Gaussian sky
models could consequently be wrong even when flux or mask tests pass.

**Remedy / acceptance:** R2 must compare size and deconvolution to analytic
truth across SNR, truncation, beam orientation and pixel scale. Reuse the
existing compact fitting/astrometry machinery where appropriate; distinguish
moment descriptors, fitted models and unavailable resolution explicitly.
Do not silently label moments as successful fits or invent uncertainty.

### F3 — P1: positive but nearly cancelled flux gives an unbounded centroid

**Location:** `src/hebog/algorithms/extended_measurement.py`,
`measure_detected_segment_position`, and `src/hebog/validation/products.py`,
`_segment_position`.

The signed centroid is accepted whenever total support flux is finite and
strictly positive. There is no conditioning/uncertainty check. Multiscale
measurement support can include negative original residuals. Moreover, the
denoised-position selector chooses the original residual when its peak/mean
ratio exceeds three, which includes strong cancellation.

On a 9-by-9 array, put `[10, -2.4, -2.4, -2.4, -2.4]` at row four,
columns two through six, with exactly those five pixels as support. Calling
`_segment_position` with a non-negative denoised alternative still returns
`available=True`, total weight `0.4`, and centroid `(-58, 4)` for support
confined to `x=2..6`. This is a reproduced measurement-boundary defect; it
does not establish that cancellation caused a particular sentinel offset.

**Remedy / acceptance:** R2 must exercise near-zero positive, zero and negative
weights and support contamination. Review uncertainty/conditioning and an
explicit fallback or unavailable disposition. Preserve legitimate centroids
between components or in a shell's empty centre; forcing every centroid onto
a peak or a positive mask pixel is not a general correction.

### F4 — P2: an admitted owner without a shape aborts public publication

**Location:** `src/hebog/public_api.py`, `_public_catalogue`, at the
`candidate.fitted_shape is None` branch; upstream shape unavailability is
created by `_moment_shape_fields` in `src/hebog/validation/products.py`.

A 33-by-33 analytic image with seven collinear pixels of value ten, zero
background, unit RMS and public configuration `(5, 3, 7)` produces one
admitted component and seven measurement pixels. Its covariance is singular,
so its shape is explicitly unavailable. Passing those exact terminal products
through `_public_catalogue` raises
`SourceFinderError: evaluated Gaussian component has no fitted shape`.
A one-pixel owner with the supported custom minimum of one does the same.
The configured science builder and public projection were both exercised;
these probes bypass background estimation and perform no FITS campaign.

Thus lower-level thin-support/component tests can pass while the user-facing
bundle still fails. One such owner can prevent publication of unrelated
valid sources in the same image.

**Remedy / acceptance:** R4 must define a public disposition for admitted
non-Gaussian/unmeasurable components, then test the whole bundle, including
mixed valid/degenerate owners and bounded deblend deferrals. Preserve source
and support evidence without fabricating a fitted Gaussian or silently
discarding a valid source. Any public schema change must be explicit.

### F5 — P2: durable terminal evidence omits its per-image diagnostics

**Location:** `scripts/benchmark/run_phase5_compact_held_out_source_union_sentinel.py`,
the summary-write and terminal-decision block used by the spawn-repair runner.

Pair summaries are written only to `scratch/summaries`; the durable terminal
stores cell aggregates and `pair_summary_canonical_sha256`, not the records.
At review time the named scratch and immutable execution directories were
unavailable, and no corresponding per-image archive was found beside the
terminal. A checksum cannot reconstruct source memberships or signed errors.

**Remedy / acceptance:** R4 must preserve verified array-free pair summaries
and Dask evidence in the durable evidence namespace before scratch cleanup.
Keep atomic/write-once terminal semantics and test missing, corrupt and
interrupted publication. Include bounded attribution fields sufficient to
distinguish noise sources, fragments, merges and estimator failures. Full
image arrays are not required for this retention fix.

### F6 — P2: a verifier unit test depends on the live campaign namespace (repaired)

**Location:** `tests/unit/validation/test_public_owner_domain_cumulative_evaluation.py`,
`_arguments` and
`test_product_verifier_binds_seal_and_complete_parent_rehash`.

`_arguments` supplies the real repository root and terminal output. The test
mocks the parent product verifier, but not its enclosing invocation/atomic
output boundary. With the legitimate retained
`benchmark-results/phase-5/public-owner-domain-cumulative-decision.json`
present, `_require_invocation` raises `FileExistsError` before the stub is
called. `just check` reproduced this after 2,579 passes and two expected
xfails. This is an existing test-isolation defect, not a failure caused by the
documentation changes or a reason to delete closed evidence.

**Remedy / acceptance:** R5 must isolate paths, seals and filesystem state in
temporary fixture namespaces. Test both absent and existing outputs without
using the main evidence directory. Preserve the production write-once guard
and frozen programs; do not skip the test or remove a result to make CI pass.
This issue prevented a clean full-check handoff but does not explain any
scientific endpoint failure.

**Resolution (2026-09-07):** the verifier tests now bind temporary roots and
synthetic seals, while exercising the real invocation, seal and write-once
guards. They cover absent outputs, existing files/directories, tampered or
semantically invalid seals and changed output paths. Scoped bindings restore
the historical parent after every test. The closed review's fixture hashes
are verified against its original Git revision; current freezer tests bind
current fixture bytes instead of rewriting that historical record. The
separate CI shallow-history defect is also corrected. No production program,
science, threshold or campaign evidence changed.

## Remaining mechanisms requiring development evidence

- **Compact flux errors:** the public path uses expanded signed aperture
  sums with a 1.5-major-beam guard. Near-threshold, invalid-pixel and
  varying-noise cells have fractional errors around `0.42`, `0.19` and `0.25`
  versus PyBDSF's `0.12`, `0.057` and `0.068`. Noise accumulation, background
  residuals, neighbouring flux and missing observable pixels need separate
  attribution. The positive-exact-support fallback is flagged, but its bias
  and discontinuity need tests before adopting it as ordinary photometry.
- **Extended fragmentation:** large varying-noise shells retain good binary
  overlap but low source reliability and large matched-source flux errors.
  Under one-to-one matching, a fragment can be compared with a whole truth
  source. This does not prove the total light was lost or that every unmatched
  row is a noise detection. Some other shell cells associate successfully;
  globally increasing or decreasing association would risk regressions.
- **Support deficits:** four mixed-emission cells fail mask recall; one has
  Hebog/PyBDSF recall `0.7204/0.9246`. The source-union adapter checks that
  every original owner pixel survives. Membership relabelling alone cannot
  restore absent support. R3 must trace background, detection and support
  pruning separately without blaming adaptive estimation from aggregates.
- **Different measurement and publication footprints:** reconstructed source
  measurements add connected persistent support before aperture expansion,
  while the public mask uses the component-owner union. Different detection
  and photometry footprints can be intentional. R0/R4 must document and retain
  those domains; do not require flux to equal a sum over the detection mask or
  promote measurement-only pixels into detection without scientific review.

## Review limits and validation

Reviewed paths include public FITS metadata/beam handling, background/RMS
composition, deblending, hierarchy membership, original-pixel flux/position,
moment shapes, public catalogue projection and source-union truth compilation.
No additional confirmed unit-conversion or WCS-axis defect was established.
This bounded review is not exhaustive validation of all source geometries,
noise processes, coordinate projections or distributed workloads.

Existing tests remain useful but do not establish all of these science
contracts: some assert the problematic grouping, shape tests permit explicit
unavailability that public publication rejects, and the centroid tests omit
small-positive cancellation. The analytic reproductions above diagnose
current behaviour; permanent red-first regression tests belong with the
approved repairs. Commands and completed validation are recorded in `LOG.md`.

No production code, test expectation, frozen margin or terminal decision was
modified. Historical cleanup remains Phase 5.5, and Release Please owns the
release after scientific and engineering acceptance.
