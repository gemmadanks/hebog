# Phase 4 release readiness

**Decision:** Phase 4 is technically implemented for ordinary compact,
no-deferral images, but its scientific and performance exit gate is not yet
passed. It must not be released as a completed phase, described as full
PyBDSF equivalence, or used as Rapthor's default backend.

This record deliberately distinguishes implemented capability from qualified
capability. The frozen regression matrix exposed an inconsistency in the
reviewed close-blend contract before the unseen qualification output was
opened. Preserving that held-out boundary is more important than declaring a
premature pass.

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
  unresolved, and marginal states;
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

The governed three-source compact catalogue passes every frozen exact Phase 4
position, flux, fitted/deconvolved shape, classification, association,
availability, and catastrophic-outlier gate against both references:

- released PyBDSF 1.14.1 used by Rapthor; and
- pinned performance-improved PyBDSF `master` at the reviewed Phase 0
  revision.

Rapthor's catalogue diagnostic cuts retain the same three rows. Pixel-centre
mask decisions agree for 65,534 of 65,536 pixels against each reference,
exceeding the existing 99.5% downstream-decision gate. These results apply to
the compact no-deferral fixture; multiscale emission remains Phase 5 work.

## Scientific gate that remains open

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
super-resolution from injected truth. It requires named human approval because
it materially changes the provisional association contract. The truth schema
must then carry explicit association-group identities rather than inferring
them from a flat Gaussian list.

## Evidence not yet eligible to run

The replacement Phase 4 qualification recipe and explicit truth-group
definitions are frozen under manifest schema 2. Its output has not been
generated or inspected. Development-only regression exposed an additional
validation issue: flat absolute tail limits treat expected low-SNR noise
scatter as systematic error. The replacement group margins and
SNR-stratified noisy-source decision rule need named numerical review before
any qualification run.

Formal independent-pixel fit covariance is implemented but is explicitly
uncalibrated for synthesized-beam-correlated noise. Position and flux
uncertainty strata still require at least 200 eligible measurements and the
predeclared Wilson, Student-*t*, and fixed-seed BCa confidence-interval gates.
Shape uncertainty remains report-only.

The controlled Phase 4 256, 512, 1,024, and 3,000-pixel performance matrix has
not been run. The 3,000-square incremental compact measurement/fitting median
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

1. [x] Gemma Danks completed the named amendment review on 2026-08-03 in the
   [Phase 4 scientific review record](phase-4-review-record.md).
2. [ ] The regression and untouched qualification truth schemas, recipes,
   checksums, and gates are replaced consistently before held-out inspection.
3. [ ] Development and regression science passes, including association-group and
   uncertainty-calibration reports.
4. [ ] The replacement held-out qualification campaign passes every reviewed
   gate without post-inspection tuning.
5. [ ] The controlled Phase 4 performance matrix passes its component budgets and
   shows no unapproved adjacent-tier regression or source-density
   superlinearity.
6. [ ] The final evidence and this decision are reviewed and changed from
   **not ready** to **passed**.
