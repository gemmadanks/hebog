# Phase 4 release readiness

**Decision:** Phase 4 is technically implemented for ordinary compact,
no-deferral images, but its scientific and performance exit gate is not yet
passed. It must not be released as a completed phase, described as full
PyBDSF equivalence, or used as Rapthor's default backend.

This record deliberately distinguishes implemented capability from qualified
capability. The close-blend contract was corrected and powered regression
passes, but the first subsequently opened held-out campaign failed several
frozen scientific gates. Preserving that result without post-inspection tuning
is more important than declaring a premature pass.

## Implemented capability

- exact deblended-region membership remains worker-local through measurement
  and fitting;
- vectorised owned-pixel moments provide deterministic photometry and a
  readable fit initializer;
- every eligible compact region is fitted with bounded SciPy least squares,
  with typed non-convergence and invalid-result outcomes;
- fitted positions, covariance, ellipses, and flux geometry are transformed
  through an Astropy ICRS WCS boundary;
- restoring-beam covariance is deconvolved into explicit resolved,
  unresolved, and marginal states, then noisy extension is classified with an
  explicit two-sigma flux-ratio uncertainty test;
- islands, Gaussian components, and source candidates remain distinct typed
  records with canonical global identities;
- one catalogue shard is produced per admitted coarse task, pairwise reduction
  has fan-in two and logarithmic depth, and final in-memory assembly has an
  explicit population cap; and
- the deterministic J2000 FITS adapter publishes exactly the eight columns
  consumed by Rapthor's current catalogue diagnostics.

The stage fails closed if a compact fit is omitted or Phase 5 owns a deferred
island. It therefore cannot silently publish a complete catalogue for an
incomplete image.

## Evidence that passes

Analytic and property tests cover moment invariants, fit bounds and failure
states, WCS rotation and wraparound, beam deconvolution, canonical association,
bounded reduction, empty catalogue output, FITS schema validation, and
conflict-safe retries. Serial and two-worker Dask runs produce the same
catalogue shards, and one-tile/many-tile execution preserves identities and
numeric values.

After applying the documented peak-as-total unresolved catalogue policy, the
governed three-source compact catalogue passes every frozen exact Phase 4
position, flux, fitted/deconvolved shape, classification, association,
availability, and catastrophic-outlier gate against both references:

- released PyBDSF 1.14.1 used by Rapthor; and
- pinned performance-improved PyBDSF `master` at the reviewed Phase 0
  revision.

The raw PyBDSF products remain immutable. They record one intentional policy
divergence: an unresolved reference row has a free-fit total about 39% below
its peak. Hebog reports peak as total for that row, as recommended by the
radio-catalogue literature; the comparison canonicalizes only that scientific
view and tests the raw divergence separately.

Rapthor's catalogue diagnostic cuts retain the same three rows. Pixel-centre
mask decisions agree for 65,534 of 65,536 pixels against each reference,
exceeding the existing 99.5% downstream-decision gate. These results apply to
the compact no-deferral fixture; multiscale emission remains Phase 5 work.

## Resolved association amendment

The regression case `phase-4-crowded-association-regression-512` injects seven
Gaussian emitters. Three pairs are narrower than one restoring beam and each
pair produces only one observable image maximum. The reviewed Phase 3
deblender consequently produces four regions. A one-region/one-source model
cannot also satisfy a flat seven-emitter completeness assertion. Setting the
saddle threshold to zero does not alter that information limit.

The recommended amendment is:

1. define a truth emitter as independently resolvable only when the observed
   image contains a distinct eligible maximum satisfying the reviewed
   peak/separation/saddle rules;
2. gate per-emitter completeness, position, flux, and shape only for that
   resolvable population;
3. represent sub-beam injected emitters that form one observed maximum as one
   explicit truth association group, and gate the group centroid and total
   flux rather than pretending its members were individually measured;
4. retain one fitted component/source for a single-maximum compact region in
   Phase 4; and
5. defer evidence-based joint multi-Gaussian model selection until a governed
   dataset shows that the additional parameters are identifiable and improve
   completeness without reducing reliability.

This recommendation follows the information present in the image and the
project's community-practice principle: report completeness and reliability
for declared, scientifically eligible populations, and do not infer
super-resolution from injected truth. Gemma Danks approved this association
amendment on 2026-08-03, and the truth schema now carries explicit group
identities rather than inferring them from a flat Gaussian list.

## First powered qualification result

The powered replacement Phase 4 qualification recipe and explicit truth-group
definitions were frozen under manifest schema 2 before inspection. Gemma
Danks approved the replacement group margins and SNR-stratified noisy-source
decision rule on 2026-08-03. The amended regression passed, after which the
first and only held-out run was performed.

Generator-v3 qualification noise uses the restoring-beam Gaussian correlation
function. Fits use bounded background context and a generalized OLS sandwich
covariance rather than treating pixels as independent. The powered regression
provides 1,600 eligible measurements per SNR stratum and passes the predeclared
Wilson, Student-*t*, and fixed-seed BCa entire-interval gates. The qualification
recipe supplied the same minimum power across SNR, shape, and edge strata.
Shape uncertainty remains report-only.

The held-out campaign did not pass. It achieved 99.79% completeness and 99.68%
overall reliability, but resolved/unresolved classification agreement was
73.57% against a 95% minimum and its catastrophic matched-row rate was 0.783%
against a 0.5% maximum. Normalized-mean intervals failed for SNR-10 integrated
flux, SNR-25 peak flux, unresolved-shape integrated flux, and edge integrated
flux. The runner also revealed that the unresolved-group reliability
denominator was not frozen precisely enough to separate false candidates near
individual groups. The exact result and intervals are recorded in the
[scientific review record](phase-4-review-record.md).

No post-inspection tuning was performed. This dataset is now known evidence,
not an unseen qualification population. A new unseen campaign and named review
of the ambiguous denominator and boundary-classification policy were required
before corrective implementation work.

The viewed recipe is now archived unchanged. Before corrective production
code, a second campaign was frozen with 200 disjoint seeds, distinct WCS,
negative background, varying RMS, invalid pixels, correlated noise, and
predeclared point-source, clearly resolved, marginal-resolution, edge, SNR,
and unresolved-group strata. Literature review selected the ATLAS two-sigma
integrated-to-peak uncertainty rule, point-source specificity and clear-source
recall gates, report-only marginal classification, and peak flux for
beam-compatible sources. The undefined morphology-specific reliability gate
was removed; overall catalogue reliability remains gated.

The correction is implemented through TDD and the powered independent
regression now passes. Regression also established, before qualification, that
the clear-extension gate must be restricted to truth area ratio at least 3 and
SNR at least 25, and that resolved/marginal integrated-flux uncertainty remains
report-only. These definitions are frozen-provisional pending named human
review. The new campaign has not been generated or inspected.

The controlled Phase 4 256, 512, 1,024, and 3,000-pixel performance matrix has
not been run because the closure order puts scientific qualification first and
the known implementation is not release-eligible. The 3,000-square incremental
compact measurement/fitting median
must remain within 2.0 seconds and catalogue/materialisation within the shared
2.0-second allocation. Evidence must include sparse, normal, dense,
blend-heavy, and fit-failure workloads and compare affected tiers with the
reviewed Hebog curve and both PyBDSF references. No Phase 4 speed claim is
made yet.

## Portability, scope, and deferrals

The implementation is pure Python plus established NumPy, SciPy, Astropy,
Zarr, and Dask boundaries; no native extension or new runtime dependency was
introduced. Tests cover scheduler-independent records, serial/Dask equality,
FITS validation, and platform-safe atomic replacement. Normal Windows support
is retained through the repository CI matrix.

This phase is limited to primary-beam-corrected MFS Stokes I images in Jy/beam
with complete ICRS WCS, restoring-beam, and reference-frequency metadata.
Per-channel catalogues and spectral fitting, extended/multiscale recovery,
complete public `find_sources`, Rapthor orchestration and sky-model
publication, end-to-end filtering equivalence, and production-scale
qualification remain Phases 5–7.

## Required closure order

Phase 4 can be declared passed only after all of the following occur in order:

1. [x] Gemma Danks completed the earlier named amendment review on 2026-08-03 in the
   [Phase 4 scientific review record](phase-4-review-record.md).
2. [x] The regression and untouched qualification truth schemas, recipes,
   checksums, and gates are replaced consistently before held-out inspection.
3. [x] Development and regression science passes, including association-group
   and uncertainty-calibration reports.
4. [ ] The post-failure extension-classification amendment receives named
   human review after independent regression passes.
5. [ ] The newly frozen unseen held-out qualification campaign passes every
   reviewed gate without post-inspection tuning. The first powered campaign
   failed on 2026-08-03 and is retained as known evidence.
6. [ ] The controlled Phase 4 performance matrix passes its component budgets and
   shows no unapproved adjacent-tier regression or source-density
   superlinearity.
7. [ ] The final evidence and this decision are reviewed and changed from
   **not ready** to **passed**.
