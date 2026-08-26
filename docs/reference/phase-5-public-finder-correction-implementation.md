# Phase 5 public-finder correction implementation

**Status:** implemented and validated on synthetic fixtures only. This code is
not an executable public protocol and has not been run against viewed SDC1 or
Hydra data. Cumulative replay, a new campaign, fresh qualification, tuning,
rescoring, cutover, and release remain unauthorized.

Exact non-executable identity review SHA-256 `e2121fb8...` binds implementation
commit `b1d59e5...`, source tree `2de6564e...`, the unchanged base candidate
configuration, correction contract `f0ddd4d5...`, and closed cumulative
baseline `a45303df...`. Every authorization flag in that review is false. The
next permitted boundary is a separate named approval for one complete
cumulative replay only; it does not include viewed-data execution.

That named replay approval was received, but its no-write preflight rejected
the frozen composition before execution. The bound replay program still
selects candidate `c184acf7...`, the base-only configuration, and the old
Continuum builder rather than candidate `b1d59e5...` and correction
configuration `65c8876d...`. No products were opened or created. Repair
pre-review `e198df12...` recommended a minimal separately reviewed wrapper.
Gemma Danks approved wrapper implementation and fixture/no-write validation;
decision `83d14670...` records that limited authorization. The wrapper is now
implemented and validated, but it has no execution decision and cannot start
the replay. Replacement exact identities and another named approval remain
required.

The implementation is governed by correction pre-review SHA-256
`3e02aff3...` and the named implementation decision in
`config/contracts/phase-5-public-finder-correction-implementation-decision.json`.
The prospective science policy is recorded separately in
`config/contracts/phase-5-public-finder-correction.json`; historical contracts
and sealed public evidence remain unchanged.

## Seeded-island ownership

The prospective candidate uses accepted original-residual component labels as
authoritative source seeds. It does not apply the historical three-beam
connected-union operation. Significant reconstructed support is eligible only
within half a restoring-beam major FWHM of exact seed support. Each eligible
pixel is assigned to the closest exact seed pixel in Euclidean image
coordinates.

Direct seed pixels always retain their owner, so support recovery cannot merge
or delete a source identity. Where two owners are exactly equidistant, the
owner with the earliest global row-major seed reference wins. This is based on
seed position rather than the task-local label integer. Invalid pixels remain
unowned. Complete-plane calls derive those references directly. Partitioned
callers must carry the same frozen global owner-reference map into every halo
task, so a tile that does not contain an owner's earliest pixel cannot change
an exact tie.

`assign_seeded_multiscale_support` implements the pure ownership operation.
`evaluate_public_finder_correction_candidate_products` composes it with the
unchanged matched-filter, residual B3 à trous, thresholds, and minimum-area
settings. The prior `evaluate_post_campaign_candidate_products` path retains
its historical behaviour so sealed evidence remains reproducible.

## Moment-equivalent public shapes

`build_hebog_segment_moment_catalogue` leaves the reviewed position,
measurement aperture, peak flux, and integrated flux unchanged. It adds a
shape measured from positive original-residual weights on the exact owner
support:

\[
\boldsymbol{\mu} = \frac{\sum_p w_p\mathbf{x}_p}{\sum_p w_p},
\qquad
\Sigma_{\mathrm{pix}} =
\frac{\sum_p w_p(\mathbf{x}_p-\boldsymbol{\mu})
(\mathbf{x}_p-\boldsymbol{\mu})^\mathsf{T}}{\sum_p w_p}.
\]

The local finite-difference WCS Jacobian transforms this covariance into the
east--north tangent plane. Its eigenvalues define the observed
moment-equivalent FWHM axes and its eigenvectors define position angle east of
north. The restoring-beam covariance is then subtracted using the existing
deconvolution implementation.

Catalogue rows distinguish `resolved`, `major-axis-only`, `unresolved`, and
`unavailable`. Singular or underdetermined support stays unavailable; no
circular ellipse is invented. The canonical
`segment-moment-equivalent-shape` flag prevents the result being represented
as a nonlinear Gaussian fit. Shape uncertainties remain absent because
support-selection and correlated-noise uncertainty have not been reviewed.

## Non-executable SDC1 adapter

`build_sdc1_source_finding_records` is an in-memory, fixture-testable adapter.
It has no file, archive, network, command, campaign, compiler, evaluator, or
scorer entry point. It maps only meanings Hebog supplies:

- source centroid in degrees;
- deconvolved Gaussian-equivalent FWHM axes in arcseconds;
- position angle in the SDC1 clockwise-from-west convention; and
- apparent association-integrated flux in Jy.

Resolved sources carry both intrinsic axes and an angle. Explicitly unresolved
sources carry zero intrinsic axes and no angle. Major-axis-only and unavailable
deconvolutions fail before the future scorer boundary because the current SDC1
record cannot represent them without inventing information. Population class
and core fraction are always absent, and `official_global_score_eligible` is
always false.

This adapter is not an official submission writer and cannot compute an
official SDC1 score. A future viewed-development protocol must first freeze the
official scorer, null-catalogue control, submitted-team mappings, and handling
of partial shape states under a separate review.

`build_public_moment_source_candidate` separately maps the same characterized
row into Hebog's pipeline-neutral `SourceCandidate`. This pure mapping supplies
no orchestration or persistence. Fixture validation embeds it in a canonical
`SourceCatalogue` and verifies the exact JSON round trip, including shape
provenance and absent uncertainties.

## Validation boundary

The fixture suite covers diffuse bridges, bounded single-seed wings,
equidistant ties under local relabelling, invalid pixels, exact WCS-aware
moments, resolved and singular shapes, catalogue JSON round-trips, adapter
provenance, and explicit unresolved records. A local Dask fixture verifies
that complete-plane and exact-half-beam-halo partitions agree with serial
execution when carrying the global owner-reference map. Existing Phase 5
partition and filter-execution regressions remain green.

No test or command in this implementation opens sealed public products or the
closed cumulative ledger. The exact non-executable identities are frozen by
review `e2121fb8...`; the prospective replay output and corrected viewed
campaign, analysis, and decision were all absent at review time. One complete
cumulative replay was approved against that review but rejected by no-write
preflight because the historical program selected the older candidate. The
repair wrapper now selects correction configuration `65c8876d...` while
checksum-binding the historical program and unchanged compilation/evaluation
machinery. It remains fail-closed until a replacement identity review and
separate named approval exist. Any execution on viewed public data requires a
later executable protocol freeze and separate approval. Fresh held-out
qualification remains a distinct boundary after those reviews.

The focused fixture suite passes 118 tests. The branch-aware repository suite
passes 1,796 tests with four expected xfails and 95.06% total coverage. The
prospective adapter has 100% line and branch coverage; the ownership kernel
has 99% coverage. The existing frozen recovery and final-qualification
protocol checks remain green.
