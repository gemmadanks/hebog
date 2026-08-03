# Phase 4 scientific review record

This record captures the original named review of Phase 4 compact measurement
semantics, the first held-out failure, and the subsequent literature-led
correction. The original decisions remain approved. Gemma Danks approved the
post-failure extension and unresolved-flux addendum on 2026-08-03 while the
replacement unseen campaign remained unopened.

## Reviewer and decision

- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer
- **Review capacity:** Project owner and named ADR decider reviewing the
  Hebog/Rapthor source-finding contract
- **Review date:** 2026-08-02
- **Decision:** Approved after the amendments below were encoded and tested
- **Required amendments:** Select gated populations from reference or injected
  truth; count missing candidate values as unavailable; require explicit
  availability gates; restrict position-angle evidence to reference ellipses
  with major/minor axis ratio at least 1.1; and require at least 200 independent
  eligible measurements per uncertainty stratum with predeclared confidence
  intervals and an entire-interval equivalence rule.
- **Qualification-data confirmation:** The Phase 4 qualification recipe,
  source population, 200 deterministic noise realizations, and reviewed gates
  were frozen before measurement or fitting results were generated or
  inspected. No held-out scientific output was inspected during this review;
  the campaign remains outside routine tuning.

## Evidence considered

The proposal follows the project's oracle hierarchy: analytic and injected
truth first, deterministic Hebog conformance second, released and pinned
`master` PyBDSF compatibility next, and Rapthor decisions last. Its external
scientific and implementation references are:

- [Condon (1997), Errors in Elliptical Gaussian
  Fits](https://doi.org/10.1086/133871), as the baseline analytic treatment of
  two-dimensional Gaussian-fit errors in radio images;
- [Aegean 2.0](https://doi.org/10.1017/pasa.2018.3), particularly its findings
  on correlated noise, Fisher-information uncertainties, and the difficulty
  of calibrating shape errors;
- the [ASKAP/EMU Source Finding Data
  Challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19),
  which motivates SNR-stratified completeness, reliability, position, flux,
  blend, and catastrophic-outlier reporting;
- [Franzen et al. (2015), ATLAS
  DR3](https://doi.org/10.1093/mnras/stv1866), for its uncertainty-aware log
  integrated-to-peak ratio classification of resolved sources;
- [Moss et al. (2007)](https://doi.org/10.1111/j.1365-2966.2007.11842.x), for
  its low-SNR fitted-width envelope and use of peak flux for unresolved
  sources;
- the documented [PyBDSF processing
  stages](https://pybdsf.readthedocs.io/en/latest/process_image.html), used as
  compatibility evidence rather than scientific truth;
- the established [Astropy WCS](https://docs.astropy.org/en/stable/wcs/wcsapi.html)
  and [SciPy least-squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
  capabilities, which must be evaluated before maintaining equivalent custom
  code.

## Reviewed decisions

### 1. Scope and measurement plane

The initial scope is primary-beam-corrected MFS Stokes I with an explicit
reference frequency and input brightness in Jy/beam. Measurements use the
physical background-subtracted plane. Invalid pixels are excluded from both
membership and measurement; unsupported units, missing beam/WCS information,
cubes, and channel sets fail explicitly rather than inheriting defaults.

### 2. Flux and local-noise meanings

- Island integrated flux is the sum of background-subtracted brightness over
  exact owned valid pixels, multiplied by pixel solid angle divided by
  restoring-beam solid angle. Pixel solid angle is the absolute determinant of
  the local tangent-plane WCS Jacobian; Gaussian restoring-beam solid angle is
  `pi * major FWHM * minor FWHM / (4 * ln(2))` in the same angular units.
- Island local RMS is the mean RMS-map value over those owned valid pixels;
  island mean brightness is the corresponding mean physical residual.
- A successfully fitted component's peak flux is its Gaussian amplitude. The
  retained free-fit integral is peak multiplied by fitted Gaussian area
  divided by restoring-beam area. Under the post-failure addendum, the
  catalogue reports that integral only for significant extension and reports
  peak as total flux for an unresolved source.
- Component/source local RMS is bilinearly evaluated at the fitted centroid.
  The provisional compact one-to-one association makes source flux equal to
  its associated component flux; this does not define later multi-component
  or multiscale source flux.

These are distinct values. Island pixel-sum flux must not be silently copied
into fitted component or grouped-source fields.

### 3. Coordinates, shapes, and uncertainties

Pixel coordinates are zero-based centers in `(x, y)` order. Astropy supplies
the ICRS transformation, and a local tangent-plane Jacobian transforms
centers, covariance matrices, and errors. Celestial Gaussian position angle
is degrees east of north modulo 180 degrees. Governed synthetic WCS rotation
uses `R(theta) @ diag(scale_x, scale_y)` before the celestial projection.
Generator-v2 restoring-beam covariance is transformed through that same
matrix before `BMAJ`, `BMIN`, and east-of-north `BPA` are written.

Available uncertainties mean one standard deviation. Candidate-reported
errors are calibrated against injected truth using normalized residual bias,
sample dispersion, and nominal 68.27% coverage. Eligibility is selected only
from reference or injected truth: a missing candidate error remains in the
availability denominator and cannot make calibration appear better. Position
and flux have reviewed-provisional quantitative gates. Shape-error calibration
and resolved free-fit integrated-flux uncertainty remain report-only because
the regression and literature do not justify treating them as reliably
calibrated by default. An unavailable error is null plus a canonical quality
flag, never zero.

Fitted-shape, deconvolution-classification, resolved-deconvolved-shape,
parent-identity, and position/flux-uncertainty availability are gated
explicitly. Position-angle comparisons use only otherwise eligible reference
ellipses whose major/minor axis ratio is at least 1.1; the axes of a
near-circular source remain eligible even though its orientation does not.

### 4. Compact association

Exact Phase 3 watershed labels remain worker-local through measurement;
bounding boxes are not treated as membership. For the initial compact scope,
each admitted deblended region initializes one fitted Gaussian component and
one source, retaining its reconciled parent island. IDs derive from canonical
global topology and association order.

This is a deliberately narrow provisional policy. A region requiring a
different component model, or any Phase 3 extended/multiscale deferral,
remains an explicit later-phase deferral. A complete catalogue or successful
`find_sources` result may not omit it. The policy must be amended if analytic
blend, dual-reference, or downstream evidence shows that one component/source
per compact region is insufficient.

### 5. Unresolved and unavailable results

Hebog represents an unresolved deconvolution as a null deconvolved shape plus
an `unresolved` quality flag. A resolved result contains a positive ordered
ellipse. An unavailable deconvolution is distinct from both. PyBDSF's
zero-axis compatibility sentinel may be emitted only by the LSMTool/Rapthor
adapter and never re-enters a scientific calculation as a measured size.

Non-finite pixels, non-positive measurements, underdetermined regions,
singular covariance, fit non-convergence, and marginal deconvolution are
explicit analytic contract cases. They are not encoded as misleading
multi-source sky truth merely to force a numerical failure.

### 6. Fitting and dependencies

Moments are the readable serial oracle and fit initializer. The first accepted
nonlinear path fits every admitted compact region. A selective moment-only
path is ineligible until it matches the fit-all reference on scientific,
association, catalogue, and downstream-decision gates. Astropy modelling and
SciPy `least_squares` will be compared later; this review does not select a
fitter or add a native implementation.

### 7. Reviewed gates

`config/contracts/phase-4-scientific-gates.json` retains the approved Section
5 high-SNR position and flux margins for isolated compact sources and the
reviewed fitted/deconvolved axis, position-angle, association, catastrophic
outlier, and uncertainty-calibration margins. Low-SNR crossings and shape
uncertainties remain report-only. The post-failure classification and
unresolved-flux addendum returns the complete contract to
`frozen-provisional` until the second named review below.

| High-SNR compact metric | Exact compact reference | Generated regression and held-out qualification |
| --- | ---: | ---: |
| Completeness | 100% | at least 99% |
| Reliability | 100% | at least 99% |
| Position, median / 95th percentile | 0.02 / 0.10 beam | 0.02 / 0.10 beam |
| Peak flux, median / 95th percentile | 2% / 5% | 2% / 5% |
| Integrated flux, median / 95th percentile | 5% / 10% | 5% / 10% |
| Fitted axes, median / 95th percentile | 5% / 10% | 5% / 10% |
| Deconvolved axes, median / 95th percentile | 10% / 20% | 10% / 20% |
| Position angle, median / 95th percentile | 2 / 5 degrees | 3 / 10 degrees |
| Point-source specificity | 100% | at least 95% |
| Clearly resolved classification recall | 100% | at least 95% |
| Parent-island association precision / recall | 100% / 100% | at least 99% / 99% |
| Required candidate-field availability | 100% | at least 99% |
| Catastrophic matched-row outliers | none | at most 0.5% |

Completeness and reliability use all declared compact SNR-at-least-10 truth;
position and flux use the existing isolated compact population; shape gates
use reference-eligible compact rows; association uses the declared compact
association population; and catastrophic rates use matched compact rows. The
position-angle limits apply independently to fitted and deconvolved ellipses
with reference axis ratio at least 1.1, so near-circular shapes and the two
ellipse populations cannot dilute meaningful orientation evidence. Missing
candidate measurements fail their availability gate instead of changing a
population denominator.

The catastrophic definition is also explicit: more than 0.5 beam positional
error, 50% peak or integrated-flux error, 50% fitted-axis error, or 100%
deconvolved-axis error. Position and flux values retain the already reviewed
Section 5 gates. This review approves the shape, association, classification,
availability, and catastrophic limits as provisional Phase 4 gates.

For position and flux uncertainties, each reported stratum needs at least 200
independent eligible measurements. At 95% confidence, the entire interval must
lie within the reviewed margin: Wilson score for one-sigma coverage, Student's
*t* for mean normalized residual, and a fixed-seed SciPy BCa bootstrap with at
least 10,000 resamples for dispersion. A stratum with fewer samples is
report-only rather than a pass. One-sigma coverage may differ from 68.27% by
at most ten percentage points; absolute mean normalized residual must be at
most 0.15 and normalized-residual sample standard deviation must remain
between 0.8 and 1.2. These are calibration gates, not a requirement to mimic
PyBDSF's formal error values.

### 8. Governed data

The Phase 4 manifests add:

- noiseless sub-pixel unresolved/resolved shape truth;
- an SNR ladder with negative background, affine varying RMS, invalid pixels,
  unequal pixel scales, rotated WCS metadata, and an edge source;
- equal/unequal blends and a crowded association regression;
- rotated deconvolution cases spanning unresolved, marginal, resolved, and
  image-edge populations; and
- one unseen 512-square qualification population with 200 deterministic noise
  realizations, giving at least 200 samples in every declared SNR,
  shape, blend, and edge class.

Generator v2 remains window-addressable and partition-invariant. Earlier
generator-v1 recipe checksums are unchanged. No qualification image,
measurement, fit, comparison, or pass/fail result has been produced or
inspected during this preparation.

## Decision checklist

The reviewer accepted:

- [x] MFS Stokes I, Jy/beam, background-subtracted measurement scope;
- [x] pixel-sum island flux and fitted-Gaussian component/source flux meanings;
- [x] local RMS, ICRS, pixel origin/order, tangent-plane, and position-angle
      conventions;
- [x] provisional one-region/one-component/one-source compact association;
- [x] unresolved, unavailable-error, failure, and compatibility-sentinel
      semantics;
- [x] fit-all-before-selective-fitting evidence order;
- [x] development/regression coverage and untouched qualification fitness;
- [x] every reviewed-provisional numerical margin, availability requirement,
      confidence rule, and report-only category; and
- [x] no known departure from the cited literature or cross-pipeline consensus.

This approval changes both Phase 4 contract statuses to
`reviewed-provisional` and closes Step 1. Any later material amendment must be
recorded before qualification inspection; replace the qualification recipe
and gates if preserving an unbiased held-out decision requires it.

## Post-review implementation finding

The first generated regression run found that all three declared close pairs
in `phase-4-crowded-association-regression-512` are narrower than one restoring
beam and each produces only one observable image maximum. The reviewed Phase 3
deblender therefore produces four regions for seven injected Gaussian emitters.
Changing its reviewed two-pixel marker radius or one-sigma saddle rule does not
create information that is absent from the image.

This is evidence that the provisional one-region/one-component/one-source
policy and the generated completeness population are inconsistent, activating
the amendment clause in Section 4. The result is not being made to pass by
tuning thresholds, counting emitters as recovered rows, or inspecting the
unseen qualification output. Before the qualification campaign runs, a named
human review must decide:

1. which separation/contrast population is scientifically resolvable and may
   carry per-emitter completeness gates;
2. whether compact regions with evidence for multiple components require a
   reviewed joint multi-Gaussian model in Phase 4 or an explicit later-phase
   deferral; and
3. how truth parent/source associations are encoded rather than inferred from
   a flat Gaussian list.

Because this material amendment affects the held-out blend stratum, the unseen
qualification recipe and its checksum must be replaced and reviewed before any
qualification result is inspected. The original 2026-08-02 approval remains a
valid record of the pre-implementation decision, but it does not approve this
new association/model choice.

## Proposed association amendment for review

The implementation evidence supports the following recommendation:

- A truth emitter is independently resolvable only when the observed image
  contains a distinct eligible maximum satisfying the reviewed peak,
  separation, and saddle rules. Per-emitter completeness, position, flux, and
  shape gates apply to this population.
- Injected emitters that are narrower than the available resolution and form
  one eligible maximum become one explicit truth association group. Gate the
  group's detection, centroid, and total flux; keep its individual emitters in
  provenance and report them rather than counting them as recoverable rows.
- A single-maximum compact region continues to produce one Phase 4 Gaussian
  component and source. Do not add a joint multi-Gaussian model solely because
  the generator knows that several emitters were injected.
- Joint multi-Gaussian fitting remains an explicit later evidence decision. It
  may enter the accepted compact path only if a governed resolvable-blend
  matrix shows identifiable components and improved completeness without a
  reliability or stability regression.
- Add explicit truth association-group IDs and group-level reference
  quantities. Do not infer parent/source relationships from ordering or a flat
  Gaussian list.

This avoids claiming super-resolution and keeps the eligible population
explicit, consistent with source-finding challenge practice. It also avoids
defining PyBDSF's particular grouping as universal truth. Approval requires a
new named decision below before any replacement qualification output is
opened.

### Amendment decision

- **Reviewer:** Gemma Danks
- **Role:** Data Processing Software Engineer
- **Decision date:** 2026-08-03
- **Decision:** Approved as recommended

The reviewer must confirm or amend:

- [x] observed resolvability determines the per-emitter gated population;
- [x] unresolved injected members use explicit truth association groups and
      group-level centroid/total-flux gates;
- [x] one component/source remains the Phase 4 default for a single eligible
      maximum;
- [x] joint multi-Gaussian model selection is deferred pending identifiability
      and reliability evidence; and
- [x] the affected regression and unseen qualification definitions will be
      replaced and reviewed before qualification inspection.

This approval closes the post-review association decision only. The
replacement truth-group schema, regression and qualification manifests, and
their checksums must still be frozen and reviewed before the first replacement
held-out result is inspected.

## Replacement contract prepared after approval

Manifest schema 2 now encodes the approved model. The crowded regression has
four explicit observable groups for seven injected emitters. Its three
unresolved groups pass development-only provisional centroid and total-flux
margins:

| Unresolved-group metric | Median limit | 95th-percentile limit |
| --- | ---: | ---: |
| Centroid separation | 0.10 beam | 0.20 beam |
| Total integrated-flux difference | 10% | 20% |

The replacement held-out dataset is
`phase4-unseen-grouped-measurement-qualification-512`, with base seed
`2026083001` and recipe SHA-256
`fe4ba6cd64a83e9c274d9eb83a3427b6f0361d0491e8683431ac5be2ccac6e8e`.
It retains 200 independent noise realizations, assigns every emitter to one
explicit truth group, removes unresolved members from individual source
strata, and adds one unresolved-group stratum. No replacement image, fit,
catalogue, comparison, or pass/fail result has been generated or inspected.

The first amended regression run also exposed a separate issue hidden by the
earlier association failure. One isolated 12-SNR source has 7.4% peak-flux and
20.6% integrated-flux error in its single deterministic noise realization,
missing the existing flat 5% and 10% tail limits. Selecting a favorable seed
or excluding the source after inspection would be invalid. Ordinary noise
scatter should instead be judged through predeclared SNR-stratified bias,
coverage, normalized-residual dispersion, and catastrophic-outlier statistics.
Absolute low-SNR tails should remain reported curves; analytic/noiseless and
exact-reference cases retain their strict absolute gates.

### Replacement numerical review required

Before held-out inspection, the reviewer must confirm or amend:

- [x] 0.10/0.20 beam median/tail unresolved-group centroid margins;
- [x] 10%/20% median/tail unresolved-group total-flux margins;
- [x] generated noisy-source qualification uses predeclared SNR-stratified
      confidence intervals for bias and uncertainty calibration rather than a
      flat per-realization absolute tail gate;
- [x] absolute noisy-source tails remain report-only curves while the existing
      catastrophic-outlier rate remains a gate; and
- [x] analytic/noiseless and exact compact-reference absolute gates remain
      unchanged.

- **Reviewer:** Gemma Danks
- **Role:** Data Processing Software Engineer
- **Decision date:** 2026-08-03
- **Decision:** Approved as recommended

This approval promotes the unresolved-group margins to
`reviewed-provisional`, freezes the noisy-source decision rule, and permits
the replacement held-out campaign to be inspected after the regression and
calibration implementation passes.

## Pre-qualification correlation and power correction

Implementation of the approved calibration rule found two defects before any
held-out result was generated:

- generator version 2 produced independent pixels even though this review
  explicitly requires synthesized-beam-correlated noise; and
- a 200-sample stratum has little probability of placing a 95% Student-*t*
  interval wholly inside the approved ±0.15 normalized-bias margin, even when
  the estimator's true bias is acceptable.

Generator version 3 now declares the restoring-beam-shaped Gaussian
correlation function, preserves exact window/partition invariance, and leaves
all version-1 and version-2 checksums unchanged. The compact fit uses a
generalized OLS sandwich covariance for that correlation and a bounded local
residual-background nuisance term fitted from eight context pixels beyond the
detection-selected island bounds. Moment photometry and exact region ownership
are unchanged.

The regression population was expanded across independent positions and
source shapes while retaining its original 200 frozen noise realizations. It
now supplies 1,600 eligible measurements in each declared SNR stratum and
passes every reviewed Wilson, Student-*t*, and fixed-seed BCa gate. This is a
power correction, not seed selection or a numerical-margin change.

The still-unopened qualification definition is consequently replaced by
`phase4-unseen-powered-correlated-measurement-qualification-512`, base seed
`2026085001`, and recipe SHA-256
`4b0104eddb7569bb68058783f836c9e701c0a4362b7d75ce50968b96ca25b3e6`.
It retains the same 200 predeclared realization seeds, provides at least 1,600
eligible samples in every SNR, shape, and edge stratum, and retains 200
unresolved-group samples for the separately approved absolute group metrics.
No qualification image, fit, catalogue, report, or pass/fail result was
generated or inspected while making this correction. The reviewed methods,
margins, minimum sample count, reviewer identity, and approval are unchanged.

## First powered held-out qualification outcome

The first and only inspection of the powered qualification campaign ran on
2026-08-03, after the final powered regression passed. The dataset identity,
200 realization seeds, checksum, source populations, interval methods, and
gate values were unchanged between approval and inspection. The complete
machine-readable report was written before the test decision; it remains in
the ignored `benchmark-results/` evidence area rather than becoming generated
source truth.

The campaign recovered 6,586 of 6,600 declared observable groups from 6,607
candidates. Completeness was 99.79% and overall reliability was 99.68%, both
above the reviewed 99% limits. Fitted-shape and classification availability
were 99.78%; resolved-shape availability was 100%. Position uncertainty passed
in every declared stratum, as did most peak- and integrated-flux calibration
comparisons.

The campaign did not pass as a whole:

- resolved/unresolved classification agreement was 73.57%, below 95%;
- 50 of 6,386 matched individual rows were catastrophic outliers, or 0.783%,
  above the 0.5% maximum;
- the SNR-10 integrated-flux normalized mean was 0.192 with a 95% interval of
  0.141 to 0.243;
- the SNR-25 peak-flux normalized mean was 0.111 with a 95% interval of 0.061
  to 0.161;
- the unresolved-shape integrated-flux normalized mean was 0.147 with a 95%
  interval of 0.098 to 0.197; and
- the edge integrated-flux normalized mean was 0.164 with a 95% interval of
  0.113 to 0.214.

The reviewed entire-interval rule requires every mean interval to remain
inside -0.15 to 0.15. The last four results therefore fail even where the
point estimate itself is inside the margin. The initial runner also exposed
that the denominator for unresolved-group reliability was not defined tightly
enough before inspection: conservatively assigning every unmatched candidate
to that population gives 90.50%, but this mixes false detections near
individually resolvable groups into the unresolved-group denominator. That
metric is recorded as an unresolved validation-contract issue, not silently
reinterpreted after seeing the result.

No fit bound, background context, covariance calculation, classification
threshold, seed, population, or scientific margin was changed after this
inspection. This campaign is now known evidence and must not be called unseen
or used to select parameters. Phase 4 remains **not ready**. Before corrective
implementation work, freeze a new unseen qualification campaign and obtain a
named review of the reliability denominator and any revised treatment of
near-boundary resolved/unresolved classification.

## Literature-led correction and second frozen campaign

Research after the failed campaign found that the previous classification
contract was not consistent with established radio-catalogue practice. It
treated any positive fitted-minus-beam covariance as physical extension. At a
true point-source boundary, symmetric measurement noise therefore labels a
large fraction of realizations as resolved. Requiring 95% binary agreement for
all injected resolved sources also confounds clear extension with sources
whose extension is not statistically measurable at their SNR.

The replacement policy follows
[Franzen et al. (2015), ATLAS DR3](https://doi.org/10.1093/mnras/stv1866):
classify a source as extended only when `ln(S_integrated / S_peak)` exceeds
twice the quadrature relative uncertainty of those fluxes. The paper reports
a 2.3% point-source false-positive probability for this one-sided 2-sigma
rule. [Moss et al. (2007)](https://doi.org/10.1111/j.1365-2966.2007.11842.x)
independently documents the low-SNR width/total-flux failure and uses peak flux
as the best flux estimate for sources inside its unresolved envelope.
[Condon (1997)](https://doi.org/10.1086/133871) supports applying a-priori size
constraints to reduce amplitude errors, while
[Aegean 2.0](https://doi.org/10.1017/pasa.2018.3) demonstrates that reducing
free parameters lowers fitting uncertainty. The ASKAP/EMU challenge retains
the global definitions of completeness and reliability: recovered real
sources divided by input real sources, and real measured sources divided by
all measured sources, respectively.

The frozen-provisional amendment therefore requires:

- at least 95% point-source specificity for the `shape-unresolved` truth
  stratum;
- at least 95% resolved recovery only for the predeclared
  `shape-clear-resolved` stratum;
- report-only SNR-dependent classification for
  `shape-marginal-resolved`, without retrospectively moving sources between
  strata;
- peak flux as integrated flux for a beam-compatible source;
- the existing global reliability gate; and
- no unresolved-group reliability gate. A morphology-specific false-positive
  denominator cannot be observed without arbitrarily assigning unrelated
  false candidates to a truth morphology. Unresolved groups retain
  completeness, centroid, and total-flux gates.

The inspected campaign was copied byte-for-byte to
`config/datasets/phase-4-viewed-qualification.json`. Its recipe checksum
remains `4b0104eddb7569bb68058783f836c9e701c0a4362b7d75ce50968b96ca25b3e6`
and its complete known-failure evidence remains recorded in this review and in
the ignored machine-readable result.

Before production code was changed, the second unseen campaign was frozen as
`phase4-unseen-extension-aware-measurement-qualification-512`, with recipe
checksum `54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49`.
Its frozen recipe has 200 seeds disjoint from the viewed campaign, a different
celestial WCS, negative background, spatially varying RMS, an invalid-pixel
region, correlated beam-shaped noise, eight edge sources, and one two-emitter
unresolved association group. Every uncertainty stratum contains at least
1,600 measurements and the group retains 200 independent realizations.

After regression defined the analytic clear-extension boundary, but still
before any qualification output, the truth-only classification partition was
frozen as eight point sources, one clearly resolved source, and 23 marginal
sources. These strata contain 1,600 point, 200 clear, and 4,600 report-only
marginal measurements. No image, catalogue, comparison, or result from this
campaign has been generated or inspected.

## Independent regression after the correction

The implementation keeps the free seven-parameter fit as diagnostic evidence,
then applies the frozen two-sigma rule at the pixel-to-celestial catalogue
boundary. An insignificant source gets a null deconvolved shape,
`extension-not-significant`, and peak-as-total flux. A noisy fit without flux
uncertainty has an unavailable extension classification instead of silently
falling back to geometry. The significance is explicit configuration rather
than a hidden threshold.

The 200-realization development/regression campaign was run without accessing
the replacement qualification data. It led to two pre-qualification findings:

- moderate injected extension is not consistently measurable, so only truth
  with fitted-to-beam area ratio at least 3 and SNR at least 25 is in the clear
  classification gate; all other resolved truth remains report-only; and
- the free-fit integrated-flux uncertainty is not calibrated for resolved and
  marginal populations. It remains available as diagnostic evidence but is a
  gate only for the peak-as-total unresolved population.

These definitions use analytic truth and regression evidence, not held-out
results. With them frozen, the complete powered regression passed in 355.29
seconds. Exact compact comparisons also pass against released and pinned
`master` PyBDSF after applying the declared unresolved-source catalogue policy.
The raw PyBDSF fixture remains unchanged and records one intentional
divergence: an unresolved free-fit total about 39% below peak.

## Named addendum review

Gemma Danks reviewed and approved every item below while the replacement
campaign remained unopened:

- [x] approve the ATLAS one-sided two-sigma log integrated-to-peak rule;
- [x] approve point specificity and clear-extension recall as separate 95%
      gates;
- [x] approve clear-extension truth as area ratio at least 3 and SNR at least
      25, with marginal extension report-only;
- [x] approve peak and peak error as total flux and total-flux error for an
      unresolved source;
- [x] approve resolved/marginal integrated-flux uncertainty as report-only;
- [x] approve catalogue reliability as a global metric, without the
      unobservable morphology-specific false-candidate denominator; and
- [x] acknowledge the intentional unresolved-flux divergence from raw PyBDSF
      and require Rapthor downstream review before backend activation.

- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer and
  project owner
- **Review date:** 2026-08-03
- **Decision:** Approved without amendment

Both Phase 4 contracts are now **reviewed-provisional**. Corrective
implementation and independent regression were complete before this approval;
the replacement qualification output remained unopened throughout the review.

## Extension-aware held-out result

After the approval commit, the replacement campaign was opened exactly once on
2026-08-03. The 200-realization run completed in 477.85 seconds and wrote its
complete machine-readable evidence to the ignored `benchmark-results/` area.
The result SHA-256 is
`ae1ce5b15a72d7089e14321854fe988ca6634ab3179009842810128aa8414c89`.

Several reviewed gates passed:

- 6,583 of 6,600 truth groups were recovered from 6,612 candidates, giving
  99.74% completeness and 99.56% reliability;
- fitted-shape and governed classification availability were 99.72% and
  99.22%;
- point-source specificity was 96.34%, clear-extension recall was 100%, and
  resolved-shape availability was 100%;
- every gated normalized-residual calibration decision passed; and
- the unresolved group's completeness, centroid, and total-flux summaries all
  passed their reviewed margins.

The campaign nevertheless failed as a whole:

- 1,128 of 6,382 matched individual rows were catastrophic outliers, or
  17.67%, against the 0.5% maximum. The report-only integrated-flux absolute
  curve had median 4.80% and 95th percentile 115.42%;
- SNR-10 uncertainty availability was 1,583 of 1,600, or 98.94%, below 99%,
  for position, peak flux, and integrated flux; and
- edge uncertainty availability was 1,582 of 1,600, or 98.88%, below 99%, for
  the same fields.

Resolved and marginal free-fit integrated-flux calibration remained
report-only as approved and failed its interval decisions across the SNR and
extended-shape strata. That result is retained as diagnostic evidence and was
not added to the gated failure set after inspection.

No parameter, threshold, truth population, seed, margin, or gate was changed,
and the campaign was not rerun. This dataset is now viewed evidence. Phase 4
remains **not ready**; the controlled performance matrix is ineligible under
the reviewed closure order until a new correction passes development,
regression, named review, and a newly frozen unseen campaign.

## Third frozen campaign

Before any further corrective production work, the extension-aware recipe was
archived unchanged as
`config/datasets/phase-4-viewed-extension-aware-qualification.json`. The third
unseen recipe is
`phase4-unseen-flux-availability-measurement-qualification-512`, with SHA-256
`7d2bf112051231f4fcad4dd8de40b58e5eeaefe572f315bd9f7e3f365f21087b`.

It retains the reviewed truth populations while using 200 seeds disjoint from
both viewed campaigns, a new WCS and sky position, different signed pixel
scales and rotation, a -0.00018 Jy/beam background, a different RMS gradient,
and a relocated invalid-pixel region. No image, fit, catalogue, comparison, or
result from this campaign has been generated or inspected.

Both Phase 4 contracts returned to **frozen-provisional** so the executable
guard prevents accidental qualification. A corrective policy must be selected
only from analytic and development/regression evidence and receive named review
before either contract is promoted again.
