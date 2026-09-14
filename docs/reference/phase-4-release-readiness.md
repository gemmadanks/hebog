# Phase 4 release readiness

**Decision:** The compact single-scale Phase 4 milestone is closed. The
separately governed Phase 4U candidate passed its scientific gate, an exact
post-optimization regression replay preserved that result, and the controlled
incremental component matrix passed its performance budgets. This is not full
PyBDSF equivalence, a complete Rapthor speed claim, or authorization to make
Hebog the default backend.

This record deliberately distinguishes milestone capability from production
qualification. Earlier Phase 4, 4R, 4S, and 4T campaigns remain terminal
failures under their frozen gates; Phase 4U is a separately designed and
powered new-candidate qualification, not a rescore. Preserving every viewed
result without post-inspection tuning remains part of the evidence chain.

## Implemented capability

- exact deblended-region membership remains worker-local through measurement
  and fitting;
- vectorised owned-pixel moments provide deterministic photometry and a
  readable fit initializer;
- every eligible compact region is fitted with bounded SciPy least squares,
  with typed non-convergence and invalid-result outcomes;
- fitted positions, covariance, ellipses, and flux geometry are transformed
  through an Astropy ICRS WCS boundary;
- restoring-beam covariance is deconvolved into explicit fully resolved,
  major-axis-only, unresolved, and unavailable states, then noisy extension is
  classified with an explicit high-confidence uncertainty test;
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
and unresolved-group strata. The first correction selected the ATLAS
two-sigma integrated-to-peak uncertainty rule, point-source specificity and
clear-source recall gates, report-only marginal classification, and peak flux
for beam-compatible sources. The later paired regression showed that this
threshold retained its expected false-extension tail; Phase 4 now uses the
five-sigma high-confidence decision approved by Gemma Danks on 2026-08-03.
The undefined
morphology-specific reliability gate was removed; overall catalogue
reliability remains gated.

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

## Dual-reference audit and approved recovery direction

Released PyBDSF 1.14.1 was run on the identical third campaign with Rapthor's
exact source-finding configuration. Its canonical unresolved-source view
recovered 6,599 of 6,600 groups, achieved 99.75% point-source specificity, and
had a 0.1875% gated catastrophic rate. Those two latter results are better
than Hebog's current 97.06% and 0.5625% and establish concrete weaknesses to
correct.

PyBDSF did not pass the complete truth-based campaign: it failed 16
normalized-uncertainty decisions and two unresolved-group tail gates where
Hebog passed. Pinned performance-improved PyBDSF `master` at
`c70103be3ae9ae9908286f144e6ce956acc0ce5c` cannot complete frozen seed
`2026090152`; its atrous Gaussian-fitting fallback raises an out-of-bounds
`IndexError`, while released PyBDSF and Hebog complete that input. The audit
therefore does not justify replacing the reviewed scientific gates with raw
PyBDSF reproduction.

The approved recovery direction is to retain all absolute gates and Hebog's
stronger recovery, uncertainty-calibration, unresolved-group, deterministic,
and bounded-execution results while using TDD on independent evidence to fix
point classification and catastrophic tails. One final predeclared campaign
must use paired same-image statistics and show Hebog no worse than released
PyBDSF, as well as passing every absolute gate, before Phase 4 can close.
Pinned master remains a comparison wherever it completes, and every exception
is counted as a reference robustness failure rather than silently excluded.

## Phase 4S stabilization and Phase 5 development readiness

Review of the terminal Phase 4R evidence found two evaluator defects and two
scientific-semantics risks. Same-named validation and classification strata
were unioned even when their memberships differed. The paired power contract
also retained the earlier 33-group, 32-individual-source, and eight-point-source
assumptions while the replacement manifest contained 13, 12, and four. With
the actual four point sources, the historical point-specificity design power
is about 76.9%, not the reported 94.5%. The historical decision remains false
and its bytes remain immutable; this audit does not rescore it.

Future evidence now uses one canonical source-stratum definition, with the
governed disjoint classification population taking precedence over a
same-named legacy validation population. The power tooling can bind every
binary endpoint and the realization count to a frozen manifest. It also
reports a dependence-robust union-bound lower bound for the probability that
all declared endpoints pass, rather than presenting the weakest marginal
endpoint power as joint campaign power. A future qualification contract must
declare those population units explicitly and fail closed on any mismatch.

All 18 SNR-15 catastrophic rows in the replacement result came from one
marginally resolved source family. Each was a deconvolved-axis failure, and the
representative seed's unstable minor-axis relative error exceeded 100% while
its fitted axes and deconvolved major remained within 17%. Production fits now
retain covariance for major sigma, minor sigma, and position angle. Hebog
propagates it through WCS transformation and beam subtraction and requires
five-sigma evidence for each reported intrinsic axis. A significant major with
an insignificant minor is a typed major-axis-only result; an insignificant
major is unresolved. In temporary regression reruns, all 18 viewed failures
are censored and none remains catastrophic. These reruns are regression
diagnostics only and do not alter the frozen qualification result.

The edge review also found that a truncation-corrected centroid could inherit
covariance from the first bounded fit. A bound-contact correction now only
initializes a widened likelihood retry; its final centroid and covariance come
from that same retry. If the retry is not identifiable, Hebog keeps the
selected fit instead of combining estimators. The 20 worst viewed SNR-10
declination residuals were unchanged because they already used a consistent
free-context estimator. Their governed point estimate was inside the absolute
gate and only its upper confidence limit crossed. That is treated as a power
and population-design issue for the next campaign, not as permission to tune
an estimator to viewed outcomes.

The technical compact Phase 5 development start gate is met: analytic rotation and
continuous-size deconvolution tests pass; lower/upper edge-reflection tests
bind estimator covariance; exact viewed failures are retained as regressions;
internal FITS and the Rapthor `DC_Maj` view round-trip a major-only result;
serial/Dask and non-slow equivalence lanes pass; and the complete governed
correlated-noise calibration regression passes. Phase 5 may therefore develop
against the stabilized compact API. This is not the Phase 4S release gate. A
new manifest-powered one-look qualification, external radio-astronomy review,
both exact PyBDSF comparisons, and the controlled performance/scalability
matrix still gate a production claim and default Rapthor cutover.

The new Phase 4S campaign subsequently completed 800/800 images for Hebog and
both references and passed all 20 paired endpoints against each reference. Its
absolute decision failed, however, so the project owner's qualification-first
checkpoint still blocks substantive multiscale implementation. Two fixed raw
median limits were below the mixed-SNR noise floor, and the point-specificity
scorer compared correct candidate states with projection-contaminated truth;
those semantics are corrected only for future evidence. The remaining SNR-10
integrated-flux uncertainty interval narrowly crossed its unchanged bound. At
that point the plan required a fresh, separately governed Phase 4T
confirmation before Phase 5 could move beyond preparation. Phase 4S remains
immutable and failed; the later Phase 4T outcome is recorded below.

The controlled Phase 4 256, 512, 1,024, and 3,000-pixel performance matrix has
not been run. The final scientific qualification failed, so the controlled
matrix and any Phase 4 speed claim are ineligible. Non-claim characterization
and profiling may proceed only as future engineering evidence. The 3,000-square incremental
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

## Root-cause analysis and follow-on disposition

The terminal campaign is more useful when its absolute failures and its
dual-reference regressions are kept distinct. Hebog's median peak-flux,
fitted-axis, and deconvolved-axis errors missed their absolute community
limits, but were still lower than both PyBDSF references. The demonstrated
dual-reference weaknesses are position efficiency and parts of the shape and
integrated-flux tails:

| Diagnostic | Hebog | PyBDSF 1.14.1 | PyBDSF `master` |
| --- | ---: | ---: | ---: |
| Median position error (beam) | 0.02736 | 0.02512 | 0.02511 |
| 95th-percentile position error (beam) | 0.09345 | 0.08917 | 0.08966 |
| Median absolute peak-flux error | 0.02942 | 0.05057 | 0.05032 |
| Median absolute integrated-flux error | 0.03996 | 0.06188 | 0.06146 |
| 95th-percentile integrated-flux error | 1.10770 | 0.54118 | 0.53634 |
| Median fitted-axis error | 0.05029 | 0.07316 | 0.07361 |
| 95th-percentile fitted-axis error | 0.20069 | 0.18331 | 0.20082 |
| Gated catastrophic fraction | 0.5104% | 0.2084% | 0.1615% |

All 98 Hebog catastrophic rows are fitted-axis outliers; 96 are edge sources
and 94 are SNR-10 sources. Twenty-five report bound contact. A direct
reproduction of seed `2026110493`, source 16, reaches the upper image-centre
bound and inflates its major sigma from the injected 2.04 pixels to 6.62
pixels. This confirms that publishing a converged boundary-pinned free fit is
one failure mode. Most outliers do not land exactly on a numerical bound, so
the broader diagnosis is weak identifiability of a seven-parameter free
ellipse and background for truncated, low-SNR profiles. The largest
integrated-flux tails are the corresponding free-shape extrapolations.

Position error is broader: Hebog is worse in about 61% of common source pairs
and in every SNR stratum, with the largest gap for unresolved, low-SNR, and
edge sources. Its normalized position biases, coverage, and dispersion pass,
which argues against a coordinate-convention error and instead motivates an
estimator-efficiency investigation. The current point fit weights pixels by
local RMS but uses the beam-correlated noise model only after optimization for
the sandwich covariance. It also fits source shape and a background offset
for every source. Beam-constrained fitting, background/support selection, and
bounded correlated-noise generalized least squares are therefore hypotheses
to test on independent data, not conclusions selected from this campaign.

The paired indeterminacy is an evaluator defect rather than a scientific root
cause. One unavailable source causes uncertainty-summary construction to
raise before any endpoint is evaluated, so all otherwise independent endpoint
families fail together. A follow-on evaluator must preserve missing sources
in completeness and availability denominators while calculating each other
endpoint independently; the historical decision remains unchanged.

The durable
[execution history](https://github.com/gemmadanks/hebog/blob/main/LOG.md)
records the separately governed Phase 4R compact-measurement recovery
milestone.
It requires TDD on analytic and independently seeded development/regression
data, a direction-aware registry covering gated and report-only metrics, a
nested beam-constrained/free fit selected by data-only identifiability and
extension evidence, and one separately reviewed qualification only after the
implementation and decision protocol are frozen. Hebog must pass every
absolute gate and be statistically non-inferior to both references on every
declared overall and governed-stratum metric; improvements cannot compensate
for a regression elsewhere.

For Phase 4R, “absolute gate” follows the metric registry's noisy-campaign
role. Raw position, flux, axis, and angle medians/tails remain fully reported
and are independently non-inferiority-gated against both PyBDSF references,
but exact/noiseless tolerances are not reapplied to irreducible stochastic
scatter. Completeness, reliability, availability, classification,
catastrophic, unresolved-group, and powered uncertainty-calibration results
remain absolute gates. Exact compact fixtures retain the original strict
accuracy tolerances.

## Phase 4R terminal result

Phase 4R is technically complete but did not achieve scientific passage. Its
only approved replacement qualification used 600 disjoint, vertically
transformed realizations and exact candidate `1065182`. Hebog and released
PyBDSF completed all 600; pinned PyBDSF `master` completed 599 and retained one
non-positive-flux catalogue failure under its `record-and-continue` policy.

Hebog passed 446/450 dual-reference metric/stratum decisions and 106/107
absolute gates. Four catastrophic-outlier comparisons failed: SNR 15 against
both references, marginally resolved against released PyBDSF, and the overall
released-reference confidence bound. The SNR-10 declination-uncertainty-bias
95% interval also crossed its absolute upper limit. The full reviewed outcome
and evidence hashes are recorded in the
[Phase 4 scientific review record](phase-4-review-record.md).

This one-look result is terminal and cannot be rescored or replaced within
Phase 4R. The controlled performance matrix remained ineligible and was not
run. Phase 4 therefore remains **not ready**, with no compact-equivalence,
speed, or Rapthor-cutover claim.

## Required closure order

The historical Phase 4 decision cannot be changed to passed. The following
list records the recovery chain through the distinct passing Phase 4U
candidate and compact engineering closeout:

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
6. [x] A frozen unseen held-out qualification campaign passes every reviewed
   gate without post-inspection tuning. All three powered campaigns failed on
   2026-08-03 and are retained as known evidence. Before another population
   could be frozen, the recovery protocol had to prevent repeated-campaign
   optional stopping and pass its independent planning audit and named review.
   The [reviewed paired non-inferiority protocol](phase-4-paired-noninferiority.md)
   and its executable power calculation are complete. The 50,000-resample
   independent planning-assumption audit verifies every revised bound. Gemma
   Danks approved the endpoint families, margins, 600-image design,
   whole-image interval method, one-look rule, and five-sigma extension policy
   on 2026-08-03. She also approved removing the statistically unstable extra
   point-sign gate before final-population freeze.
   The final population `phase4-final-paired-qualification-512` was opened
   exactly once on 2026-08-04 after its complete dataset-record SHA-256
   `07c736a9bafc79fb298ad1c076fb29b93d88ce9f988f38bba99c94af519d1fcb`,
   evaluator, and three execution environments were recorded. All 1,800
   candidate/reference realization records completed and were retained. The
   immutable decision did not pass: 109 of 114 Hebog absolute gates passed,
   but catastrophic fraction, median position, median peak flux, median
   fitted axis, and median deconvolved axis failed their frozen thresholds.
   One missed Hebog source also made the complete-match uncertainty input
   unavailable, so the frozen fail-closed joint calculation reported all 20
   primary and 20 secondary paired endpoints as indeterminate. No result,
   threshold, contract, or population was changed after inspection.
   The separately governed Phase 4U new candidate subsequently passed one
   fresh 800-image qualification: all 77 binding absolute gates, both sets of
   20 paired endpoints, and all five stronger-result envelopes passed. That
   result satisfies the prospective compact-science qualification step
   without altering any historical decision.
7. [x] The controlled Phase 4 performance matrix passes its component budgets
   and shows no unapproved adjacent-tier regression or source-density
   superlinearity. The retained first matrix diagnosed a one-batch bottleneck;
   the corrected matrix passes all 20 cells and preserves that failed evidence
   separately.
8. [x] The scientific evidence received project-owner-authorized expert review,
   every failed campaign retains its terminal disposition, and Phase 4U is
   recorded as a distinct passing candidate. Independent human radio-astronomy
   review remains a production-cutover gate rather than a Phase 5 start gate.

The refreshed 200-image paired regression has 200/200 successful runs for
both Hebog and released PyBDSF. Hebog matches the reference's perfect point
specificity, retains substantially better clear-extension, catastrophic-tail,
and unresolved-blend results, and differs in catalogue reliability by one
additional unmatched near-threshold candidate. This regression and its
planning-assumption audit supported the completed named review, but neither is
qualification evidence. The failed 600-image result remains terminal. The
later independently frozen Phase 4U qualification supplies the passing
new-candidate evidence described below; it does not revise that history.

## Phase 4T terminal result

Phase 4T opened once on exact candidate commit
`9653b0d5310b9922ffcf66bd2c801f33aa506f38`. Hebog and both exact PyBDSF
references completed all 800 fresh realizations. Hebog passed all 20 paired
endpoints against each reference, including the previously unresolved SNR-10
uncertainty question, and passed 76 of 77 binding absolute gates.

The one failure was the unresolved-group total-flux absolute-error tail:
Hebog's 95th percentile was `0.2070797655` against the frozen `0.2` maximum.
Released PyBDSF and pinned `master` both measured `0.6000309649`, so Hebog is
materially better and statistically non-inferior on that metric, but the
absolute gate and its stronger envelope still fail. The decision is terminal;
it is not rounded, rescored, or replaced by another unchanged-candidate run.

At the Phase 4T decision point, the compact start gate remained **not ready**
and its controlled performance matrix was still ineligible. The plan therefore
required independent TDD remediation of systematic unresolved-blend flux
under-recovery before any new-candidate qualification. The complete historical
outcome and file hashes are in the
[Phase 4 scientific review record](phase-4-review-record.md).

## Phase 4U compact-science closure

Phase 4U applied a model-containment association aperture on independent
development data and then opened one separately frozen 800-image
qualification. Hebog and both exact PyBDSF references completed every image.
Hebog passed all 77 binding absolute gates, all 20 paired non-inferiority
endpoints against each reference, and all five stronger-result envelopes.

The previously blocking unresolved-blend total-flux tail fell from `0.207080`
in Phase 4T to `0.139196` in Phase 4U, inside the unchanged `0.2` maximum.
Across 4,800 blends, Hebog's mean signed error was `-0.020217`, compared with
about `-0.1085` for both PyBDSF references. No material compact diagnostic
regression was found.

The exact optimized candidate was subsequently replayed on all 800 viewed
Phase 4U images as regression evidence. All implementations again completed
every image; Hebog again passed 77/77 binding absolute gates, 20/20 paired
endpoints against each reference, and all five stronger-result envelopes.
The replay candidate, compiled campaign, and decision SHA-256 values are
`62f8f73816b1cb3deae0c276d919173856ab53f43778a4f98bc6ab1392ff4ebc`,
`e34da45e0b1a44932178a6df959ea91cf42ca2ad25ab23b1851ebcb509f54137`,
and `52b4b374f9160ba52271acc07eb36f1fe8b0b776557b26f392de362bea29f2bb`.

The final incremental matrix also passes. At 3,000 by 3,000 pixels, successful
measurement/fitting medians span `0.177855`--`0.757952` seconds and catalogue
output medians span `0.036850`--`0.040811` seconds against separate
2.0-second budgets. Dense work uses 13 batches and 13 Dask tasks without
omission; the intentional fit-failure profile refuses publication. The matrix
summary SHA-256 is
`ee3729e39a6b432f29b0b5282b39e4023c479b51ee7180187760a5b567f3ffa8`.
This is the first reviewed incremental Phase 4 curve; existing PyBDSF results
time the complete Rapthor filter step and are not a matched component
baseline.

Together these results close the compact single-scale milestone and permit
Phase 5 development. They do not alter the terminal historical
Phase 4/4R/4S/4T decisions and do not authorize production cutover:
real-residual evidence, independent human review, complete Rapthor/PyBDSF
timing, and production-scale Dask qualification remain open. Full findings and
immutable qualification hashes are in the
[Phase 4 scientific review record](phase-4-review-record.md) and the
[Phase 4U protocol](phase-4u-qualification-protocol.md).
