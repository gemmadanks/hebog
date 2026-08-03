# Phase 4 release readiness

**Decision:** Phase 4 is technically implemented for ordinary compact,
no-deferral images, but its scientific and performance exit gate is not yet
passed. It must not be released as a completed phase, described as full
PyBDSF equivalence, or used as Rapthor's default backend.

This record deliberately distinguishes implemented capability from qualified
capability. The close-blend contract and extension policy were corrected and
their powered regressions pass, but all three subsequently opened held-out
campaigns failed frozen scientific gates. Preserving those results without
post-inspection tuning is more important than declaring a premature pass.

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
report-only. Gemma Danks approved these definitions on 2026-08-03. The new
campaign had not been generated or inspected at the time of approval.

The campaign was subsequently opened exactly once. It passed completeness,
reliability, extension classification, resolved-shape availability, every
gated normalized-residual calibration decision, and the unresolved-group
gates. It failed the frozen catastrophic-outlier gate at 17.67% versus 0.5%
and missed the 99% uncertainty-availability floor in the SNR-10 and edge
strata at 98.94% and 98.88%. The complete result is recorded in the
[scientific review record](phase-4-review-record.md). No post-inspection tuning
or rerun occurred.

The failed extension-aware manifest is archived, and a third unseen campaign
is frozen with 200 disjoint seeds and recipe SHA-256
`7d2bf112051231f4fcad4dd8de40b58e5eeaefe572f315bd9f7e3f365f21087b`.
At that point it had not been generated or inspected. Both contracts were
frozen-provisional until a development/regression-supported correction
received named review.

That corrective regression now distinguishes scientific populations rather
than weakening the 0.5% ceiling. In 4,800 development matches, all 283 raw
catastrophic rows were marginally resolved truth: 274 failed only integrated
flux, one failed fitted axes, and eight failed deconvolved axes. The point and
clearly resolved populations had no catastrophic rows. This agrees with the
predeclared report-only status of marginal extension and with the
[ASKAP/EMU source-finding challenge](https://doi.org/10.1017/pasa.2015.37),
which evaluates catastrophic point-source flux separately and does not apply
that analysis to its extended-source challenge because the comparison is
biased by low peak brightness and high integrated flux. The proposed harness
therefore reports marginal integrated-flux catastrophes but gates every other
metric for that population and all metrics for point and clearly resolved
truth. The numerical outlier thresholds and 0.5% ceiling are unchanged.

A new 250-measurement development regression also reproduced the edge/SNR-10
availability failure at 247/250. Its three missing matches were valid Gaussian
fits whose centroids had drifted beyond the bottom image boundary. Clamping
fit-centre bounds to the sampled image footprint, while retaining the normal
context margin inside that footprint, raises the same frozen regression to
250/250 without changing detection thresholds, uncertainty formulae, or the
third campaign. The complete corrected 4,800-match regression and both exact
PyBDSF catalogue comparisons pass. Gemma Danks approved both corrections on
2026-08-03 before any third-campaign output was generated or inspected; both
contracts were then reviewed-provisional.

The third campaign was subsequently opened exactly once. It recovered all
6,600 truth groups from 6,621 candidates (100% completeness and 99.68%
reliability), with 100% fitted-shape and classification availability, 97.06%
point-source specificity, 100% clear-resolved recall, and 100% resolved-shape
availability. Every position and peak-flux calibration gate and every
unresolved-group gate passed. It nevertheless failed two frozen decisions:
36 of 6,400 matched individual sources were gated catastrophic outliers, or
0.5625% against the 0.5% maximum, and the unresolved integrated-flux
normalized-residual mean interval was 0.0823--0.1846, crossing the approved
absolute 0.15 boundary. The complete 34,746-byte ignored evidence record has
SHA-256
`ed060b7703161ba01037939ff9a8e4b6e3d6ab527dc3b1fd45753dfb69c1165e`.
No post-inspection tuning, rerun, population change, or gate change occurred.
The campaign is now viewed evidence and both contracts are frozen-provisional
again to prevent accidental reuse.

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
4. [x] The post-failure extension-classification amendment receives named
   human review after independent regression passes.
5. [x] The marginal-flux population clarification and image-footprint
   correction receive named review after their complete development and
   regression lanes pass. Gemma Danks approved both on 2026-08-03.
6. [ ] A frozen unseen held-out qualification campaign passes every reviewed
   gate without post-inspection tuning. All three powered campaigns failed on
   2026-08-03 and are retained as known evidence. Before creating another,
   review a recovery protocol that prevents repeated-campaign optional
   stopping and freeze any new population before corrective implementation.
7. [ ] The controlled Phase 4 performance matrix passes its component budgets and
   shows no unapproved adjacent-tier regression or source-density
   superlinearity.
8. [ ] The final evidence and this decision are reviewed and changed from
   **not ready** to **passed**.
