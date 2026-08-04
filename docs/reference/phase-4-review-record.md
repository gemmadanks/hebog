# Phase 4 scientific review record

This record captures the original named review of Phase 4 compact measurement
semantics, three held-out failures, and the subsequent literature-led
corrections. The original decisions remain approved. Gemma Danks approved each
post-failure amendment before its replacement campaign was opened.

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

## Independent regression after the first correction

The first correction kept the free seven-parameter fit as diagnostic evidence,
then applied the frozen two-sigma rule at the pixel-to-celestial catalogue
boundary. An insignificant source got a null deconvolved shape,
`extension-not-significant`, and peak-as-total flux. A noisy fit without flux
uncertainty had an unavailable extension classification instead of silently
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

## Named addendum review of the first correction

Gemma Danks reviewed and approved every item below while the replacement
campaign remained unopened. The later paired regression superseded only the
approved two-sigma threshold; all other decisions remain current:

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

## Third-campaign amendment approval

The powered development runner was extended before the third campaign was
opened. It reproduced the catastrophic-tail issue independently: 283 of 4,800
matched rows met at least one raw catastrophic definition. Every one belonged
to `shape-marginal-resolved`; 274 were integrated-flux-only, one was a fitted-
axis outlier, and eight were deconvolved-axis outliers. Point and clearly
resolved truth had zero catastrophic rows.

The recommended interpretation is deliberately narrower than removing the
catastrophic gate. The 0.5% ceiling and all five numerical outlier definitions
remain unchanged. Position, peak flux, fitted axes, and deconvolved axes remain
gated for every matched compact source. Integrated flux remains gated for
point and clearly resolved truth. Only the marginal-resolved integrated-flux
catastrophic rate is report-only, matching the already frozen report-only role
of marginal extension and resolved/marginal free-fit integrated-flux
calibration.

This is consistent with the peer-reviewed evidence used for the earlier
decision. [ATLAS DR3](https://doi.org/10.1093/mnras/stv1866) classifies
extension through integrated-to-peak significance and substitutes peak flux
for sources classified as point-like. The
[ASKAP/EMU source-finding challenge](https://doi.org/10.1017/pasa.2015.37)
evaluates catastrophic flux on its point-source challenge and explicitly does
not apply the same comparison to the extended-source challenge because low
peak brightness and high integrated flux bias that analysis. Hebog remains
stricter by retaining integrated-flux gating for clearly resolved sources.

A separate frozen development recipe then exercised five isolated
SNR-10-to-15 point sources truncated by all four image sides over 50 noise
realizations. It failed before implementation at 247/250. The three missing
matches were bottom-edge fits whose valid optimizer solution placed the
centroid outside the sampled image footprint. The smallest correction clamps
centroid bounds to that footprint while preserving the configured context
margin within it. The identical regression then passed 250/250; no detection,
classification, uncertainty, or qualification threshold changed.

The corrected 200-realization, 4,800-match regression passed in 343.68
seconds, and the remaining generated-truth and exact compact-catalogue
equivalence cases passed against both PyBDSF anchors. The qualification guard
still skips before recipe generation while the contracts await review.

The third campaign's recipe, seeds, truth, WCS, background, invalid pixels,
and gates have not changed and no result has been generated. Before it may be
opened, the reviewer must decide whether to approve:

1. marginal-resolved integrated-flux catastrophic rate as report-only while
   retaining every other catastrophic gate described above; and
2. the physical image-footprint constraint and its powered edge-availability
   regression as the correction for the second campaign's availability
   failure.

- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer
- **Review date:** 2026-08-03
- **Decision:** Approved both decisions without amendment

Both contracts became **reviewed-provisional** at this boundary. This approval
was recorded before any third-campaign image, fit, catalogue, comparison, or
result was generated or inspected.

## Third held-out result

After the approval commit, the third frozen campaign was opened exactly once
on 2026-08-03. The complete qualification lane finished in 433.55 seconds.
Its 34,746-byte ignored evidence file has SHA-256
`ed060b7703161ba01037939ff9a8e4b6e3d6ab527dc3b1fd45753dfb69c1165e`,
and records the frozen dataset identifier
`phase4-unseen-flux-availability-measurement-qualification-512` and recipe
SHA-256
`7d2bf112051231f4fcad4dd8de40b58e5eeaefe572f315bd9f7e3f365f21087b`.

Most reviewed decisions passed:

- all 6,600 truth groups were recovered from 6,621 candidates, giving 100%
  completeness and 99.68% reliability;
- fitted-shape availability, classification availability, clear-resolved
  recall, and resolved-shape availability were all 100%, while point-source
  specificity was 97.06%;
- every uncertainty value was available, every position and peak-flux
  calibration decision passed, and all unresolved-group gates passed; and
- the separately declared marginal integrated-flux diagnostic recorded 1,094
  outliers among 4,600 matched marginal sources (23.78%) without entering the
  gated failure population, as approved before inspection.

Two frozen scientific decisions failed:

- 36 of 6,400 matched individual sources met at least one still-gated
  catastrophic definition, or 0.5625% against the 0.5% maximum; and
- the unresolved-source integrated-flux normalized residual had mean 0.1335
  and a 95% interval of 0.0823--0.1846, whose upper bound exceeded the
  approved absolute 0.15 margin. Its coverage interval and dispersion interval
  passed.

No parameter, gate, population, seed, or margin changed after inspection, and
the campaign was not rerun. It is now viewed evidence. Both contracts have
returned to **frozen-provisional** so the executable qualification guard skips
before recipe generation. Phase 4 remains **not ready**, and the controlled
performance matrix remains ineligible. A further held-out campaign must not be
created merely to seek a passing draw; any recovery requires a separately
reviewed protocol that addresses repeated-campaign optional stopping, freezes
new truth before corrective work, and uses only independent development and
regression evidence for implementation choices.

## Same-campaign PyBDSF audit and recovery direction

The viewed third campaign was subsequently run through released PyBDSF 1.14.1
with the exact Rapthor/LSMTool source-finding configuration: hard 5-sigma pixel
and 3-sigma island thresholds, adaptive RMS boxes, an RMS map, and the atrous
path with three scales. Hebog was not rerun. The complete ignored comparison
record has SHA-256
`298b91312749953ef6b356fbc863343f693a0378aa0aa46815c60bb229640eb0`.

Under the reviewed peak-as-total view for unresolved sources, released PyBDSF
recovered 6,599 of 6,600 groups from 6,615 candidates. It achieved 99.75%
point-source specificity and 12 gated catastrophic rows among 6,399 matched
individual sources, or 0.1875%. It therefore outperformed Hebog's 97.06%
specificity and 0.5625% catastrophic rate on the two remaining areas of
concern.

Released PyBDSF did not pass the campaign as a whole. It failed 16 gated
normalized-uncertainty decisions and the unresolved-group 95th-percentile
position and total-flux limits. For example, its unresolved point-source
peak-flux normalized residual had mean -0.761 with 54.44% one-sigma coverage;
Hebog's corresponding mean was 0.050 with 68.38% coverage and passed. Hebog
also recovered every group and produced materially better unresolved-group
tails. These are required strengths to preserve, not margins available to
trade for classification.

Pinned performance-improved PyBDSF `master` at
`c70103be3ae9ae9908286f144e6ce956acc0ce5c` could not complete the same
campaign. Frozen seed `2026090152` raises an out-of-bounds `IndexError` in the
atrous Gaussian-fitting fallback, while released PyBDSF and Hebog complete the
same input. A master exception is therefore a recorded robustness failure and
does not remove that realization or weaken Hebog's success requirement.

Gemma Danks approved the recovery direction on 2026-08-03: retain the existing
absolute community-science gates and Hebog's stronger results; correct the
point-classification and catastrophic-tail weaknesses using TDD on analytic
and independent development/regression evidence; then require a final paired
same-image qualification to show Hebog equal to or better than released
PyBDSF before closing Phase 4. The practical-equivalence margins, power
calculation, final unseen population, and stopping rule required named review
before that population could be frozen. That review is recorded below.
Non-claim profiling may proceed in
calculation, final unseen population, and stopping rule required named review
before that population could be frozen. That review is recorded below.
Non-claim profiling may proceed in
parallel, but final Phase 4 performance qualification follows the scientific
pass. After Phase 4 closes, bounded-memory and distributed scalability of the
qualified compact path becomes the next active engineering focus.

## Paired-protocol preparation
## Paired-protocol preparation

The recovery protocol is now expressed as a strict version-one contract and a
human-readable [paired non-inferiority review
guide](phase-4-paired-noninferiority.md). It proposed 600 independent
guide](phase-4-paired-noninferiority.md). It proposed 600 independent
noise-seed images, one-sided 95% paired whole-image BCa intervals, 50,000
fixed-seed resamples, positive-as-worse metric normalization, all-endpoint
intersection-union passage, and an initially proposed additional no-worse
point-estimate condition. Released PyBDSF is primary; a failure by it or Hebog
fails primary qualification, while pinned-`master` failure remains visible in
a secondary report.
intersection-union passage, and an initially proposed additional no-worse
point-estimate condition. Released PyBDSF is primary; a failure by it or Hebog
fails primary qualification, while pinned-`master` failure remains visible in
a secondary report.

The executable normal approximation gives at least 92.2% power to exclude the
proposed practical regression margin for every endpoint under its planning
assumptions. It separately reports that a no-worse point estimate has only 50%
probability under exact equality; the draft therefore makes no misleading 90%
overall-pass claim. The later planning-assumption audit verifies the revised
variance bounds. Named review below accepts the design but removes the extra
directional gate; no final seed, truth, or result had been generated or
inspected at the time of that decision.
overall-pass claim. The later planning-assumption audit verifies the revised
variance bounds. Named review below accepts the design but removes the extra
directional gate; no final seed, truth, or result had been generated or
inspected at the time of that decision.

## Independent point-classification recovery
## Independent point-classification recovery

The corrected-geometry paired regression provided a truth-only margin audit
before any final population was frozen. Across 1,600 predeclared
beam-compatible point sources, the standardized ATLAS log
integrated-to-peak statistic ranged from -2.08 to 3.38. Across the 200
predeclared clear extensions, the same statistic ranged from 17.92 to 23.83.
At the earlier two-sigma boundary Hebog classified 51 of 1,568 point sources
as resolved on the jointly successful images (96.75% specificity), while
released PyBDSF classified all of them as unresolved. ATLAS itself documents
a 2.3% one-sided false-extension probability for that two-sigma decision, so
this was a foreseeable policy tail rather than evidence that the injected
point truth was invalid.

The recovery implementation retains the ATLAS statistic but requires five
sigma for the catalogue-level resolved claim. Five sigma is deliberately
conservative: false extension creates a physical size and switches from peak-as-total to a
conservative: false extension creates a physical size and switches from peak-as-total to a
noise-biased free-fit integral, and the independent clear population retains
more than 12 sigma of observed margin above the decision. Marginal extension
remains report-only, so it cannot be traded against the co-primary point and
clear populations.

The reviewer approved:
The reviewer approved:

1. five sigma as the high-confidence catalogue extension threshold for Phase
   4 and the Rapthor compatibility product; and
2. retention of the ATLAS standardized statistic, peak-as-total unresolved
   policy, separate point/clear gates, and report-only marginal population
   without changing any absolute scientific margin.

- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer
- **Review date:** 2026-08-03
- **Decision:** Approved both recommendations
- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer
- **Review date:** 2026-08-03
- **Decision:** Approved both recommendations

This regression evidence cannot qualify Hebog. The complete paired audit was
therefore refreshed after the implementation change, and its planning
assumptions were reviewed before final-population freeze.
This regression evidence cannot qualify Hebog. The complete paired audit was
therefore refreshed after the implementation change, and its planning
assumptions were reviewed before final-population freeze.

## Refreshed paired regression
## Refreshed paired regression

The post-correction Hebog shard is bound to commit
`49855eba45294278dd2fe709583a093445cf5eba` and completed all 200 governed
regression images. Its SHA-256 is
`32aacb78733d28cac086ae10596a1d2d1f5e7671d0cc6844c33a0ac87297fa0a`.
The unchanged released-PyBDSF shard has SHA-256
`adeea227878ecb0b412a196a1adf09fdd212fca15fa9b3f187059e1c33f470b0`;
the compiled pair has SHA-256
`bff79e0dafd096870460bfc1f6663a84d4f6cb813ea6ab7610b2bd8bee287a96`.

Both implementations recovered every truth group. Hebog now matches
PyBDSF's 100% point specificity, retains 100% clear-resolved recall against
57.5%, and improves the governed catastrophic fraction from PyBDSF's 1.547%
to 0.531%. Mean unresolved-blend position and total-flux errors are 0.056 beam
and 5.36% for Hebog versus 0.089 beam and 14.98% for PyBDSF. These results show
that both corrections preserved the predeclared stronger Hebog outcomes.

Hebog produced 21 unmatched candidates and PyBDSF produced 20, giving
catalogue reliabilities of 99.6828% and 99.6979%. The paired difference is one
candidate across 6,600 truth groups; the one-sided 95% BCa upper bound on
Hebog regression is 0.1808 percentage points, inside the proposed 0.5-point
margin. All 21 Hebog rows are unresolved near-threshold detections with fitted
peak SNR 4.34--6.11. A new post-fit cut would be regression-tail tuning and
could harm real-source completeness, so no algorithm change is proposed from
this result.

The maintained endpoint and planning-assumption audit below was required
before these values could support named review. At that point the final
population remained ungenerated and unopened.
The maintained endpoint and planning-assumption audit below was required
before these values could support named review. At that point the final
population remained ungenerated and unopened.

## Planning-assumption audit and named decision
## Planning-assumption audit and named decision

The maintained audit recomputes every endpoint in 50,000 whole-image bootstrap
resamples. It uses aggregate matched-to-candidate ratios, pooled
predeclared-stratum uncertainty statistics, and aggregate median and
95th-percentile unresolved-group errors. Its equivalent paired standard
deviation avoids assigning a false cross-implementation identity to unmatched
candidates and is directly comparable with the power model.

The first audit found 11 conservative provisional bounds and nine
underestimates. Seven of those nine occur where Hebog is substantially better
than PyBDSF, so the near-zero-effect draft understated the observed paired
variation. The revised draft rounds each failed bound above the observed
dispersion and uses at most half the observed favourable effect. Coverage and
dispersion are also corrected to be lower-is-better absolute departures; the
earlier draft accidentally encoded an already absolute departure and then
applied the raw ideal a second time. No practical regression margin,
scientific gate, or implementation threshold changed.

All 20 revised planning bounds now pass. The audit has SHA-256
`af7c6cdfdf55629b77a6960292f523f73f583ec8e09bb407233cda26845ea9b1`,
and the pre-amendment reviewed protocol had canonical SHA-256
`1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`.
`af7c6cdfdf55629b77a6960292f523f73f583ec8e09bb407233cda26845ea9b1`,
and the reviewed protocol has canonical SHA-256
`1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`.
The weakest interval-exclusion power remains 92.2% at 600 images.

Two regression point estimates are slightly worse despite passing their
paired practical margins: catalogue reliability by 0.0151 percentage points
(upper bound 0.1808 versus a 0.5-point margin), and median unresolved-blend
position by 0.00279 beam (upper bound 0.00682 versus a 0.01-beam margin).
Their tail and companion endpoints are equal or substantially better. This is
consistent with the draft calculation's warning that a strict directional
rule passes only half of repeated experiments under effective equality.

Gemma Danks, Data Processing Software Engineer, reviewed and approved the
following on 2026-08-03:
Gemma Danks, Data Processing Software Engineer, reviewed and approved the
following on 2026-08-03:

1. the five-sigma high-confidence extension decision;
2. the endpoint populations, practical margins, and corrected absolute-
   departure semantics;
3. the regression-supported variance bounds and 600-image final design;
4. whole-image paired BCa resampling, intersection-union multiplicity, and the
   one-look stopping rule; and
5. removal of the stricter no-worse point-estimate condition from every
   endpoint. Signed point estimates remain mandatory report fields, while
   passage requires every one-sided upper bound to lie inside its margin,
   every absolute gate to pass, and every stronger-Hebog regression envelope
   to pass.
5. removal of the stricter no-worse point-estimate condition from every
   endpoint. Signed point estimates remain mandatory report fields, while
   passage requires every one-sided upper bound to lie inside its margin,
   every absolute gate to pass, and every stronger-Hebog regression envelope
   to pass.

The protocol is now `reviewed`; the unchanged measurement-semantics contract
and five-sigma scientific-gate contract are both `reviewed-provisional`. This
named decision permits the final 600-image population to be frozen, but not
opened, before its generator, truth, seeds, WCS/beam strata, exact
implementation revisions, analysis code, and stopping rule are recorded.

## Final population freeze

After the named decision, the final one-look population was frozen in
`config/datasets/phase-4-final-qualification.json` without generating any
image or inspecting any result. It contains exactly 600 seeds disjoint from
every earlier Phase 4 population. Its distinct WCS, background, invalid
region, and correlated-noise gradient reduce dependence on the viewed
populations. A 90-degree source-layout and beam rotation preserves the
governed unresolved-blend geometry and the reviewed endpoint counts.

- **Dataset identifier:** `phase4-final-paired-qualification-512`
- **Generator:** `hebog.synthetic.gaussian-noise`, version 3
- **Recipe SHA-256:**
  `15f8f607463f2db4cf4c0eb72255a998784e2d83d3a0d7ebc45eb733f6fbc7db`
- **Complete dataset-record SHA-256:**
  `07c736a9bafc79fb298ad1c076fb29b93d88ce9f988f38bba99c94af519d1fcb`
- **Scientific-contract-set SHA-256:**
  `562b648d98eb1d28d65341cfe99c8dba4bd36b8d928d132e6ab6f05bf8d96d79`
- **Paired-protocol SHA-256 at population freeze:**
  `1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`
- **Current amended paired-protocol SHA-256:**
  `eaa4e30a8d24a299d9f139c89aafc3ea60d424d61ac64f2b3d6fe7178a697dd8`
- **State at freeze:** ungenerated and unopened

Before opening the population, the operator must record the exact clean Hebog
revision, immutable released and pinned-`master` PyBDSF environments,
dependency inventories, and unique output paths. The one permitted opening
must use the maintained runners and compiler; a scientific failure cannot be
replaced by another population. Both maintained runners fail before recipe
iteration unless the measurement contract, scientific gates, and paired
protocol carry their reviewed statuses.

The maintained final evaluator and its immutable decision schema are now
implemented. Per-source campaign rows retain fitted and deconvolved
position-angle differences; the evaluator applies all 20 paired endpoints,
every gated absolute metric, the contractually report-only individual-source
tails, uncertainty intervals, implementation-failure policies, and the named
stronger-Hebog scientific envelopes. Its CLI verifies the frozen provenance
and refuses to overwrite an existing decision. No final image was generated
or inspected during this work.

The evaluator dry run on already-viewed post-correction regression evidence
returned 12 finite passing BCa endpoints and eight indeterminate exact-equality
endpoints. This is the documented SciPy BCa point-mass behaviour, not a Hebog
or PyBDSF scientific regression: all resamples have the same zero paired
difference, so BCa acceleration is undefined and SciPy returns `NaN`.

Gemma Danks, Data Processing Software Engineer, reviewed this exposed case on
2026-08-04 before any final image was generated or inspected. She approved the
predeclared recommendation to use `[point, point]` only when the complete
finite bootstrap distribution is exactly equal to the finite observed point
estimate. There is no numerical tolerance. A near point mass, a non-finite
distribution, or every other undefined BCa result remains indeterminate and
fails closed. This replaces the blanket `indeterminate-fail` field with
`finite-point-mass-exact-otherwise-indeterminate-fail`; it does not change an
endpoint, margin, resampling seed, sample size, or scientific gate. The
amended reviewed protocol's canonical SHA-256 is
`eaa4e30a8d24a299d9f139c89aafc3ea60d424d61ac64f2b3d6fe7178a697dd8`.
SciPy's documented behaviour is linked from the paired protocol guide.
Repeating the decision calculation on the same already-viewed 200-image
campaign returned 20 passes, no failures, and no indeterminate endpoints. The
eight exact-equality endpoints each had the exact interval `[0, 0]`. The final
600-image population remained ungenerated and unopened through this review.

## Final one-look qualification result

The final population was opened exactly once on 2026-08-04 after a preflight
record fixed the candidate, both references, dependency inventories, reviewed
contracts, and unused output paths. The candidate was Hebog 0.5.0 at
`92f5e4cc233b716987a4f65b75c5f1585d977de1`; the primary reference was
released PyBDSF 1.14.1 at
`1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`; and the secondary reference was
pinned PyBDSF `master` at
`c70103be3ae9ae9908286f144e6ce956acc0ce5c`. All three completed all 600
realizations. The compiled campaign contains all 1,800 records and has
SHA-256 `4b5d213a46524498aca465cb03aff87de26dee20f291fe6fbffa0ecab8736f0f`.

The first evaluator invocation stopped before computing or exposing any
scientific endpoint. Its provenance guard counted only the 599 additional
noise seeds and omitted the governed base recipe. Under the predeclared
infrastructure-resume rule, TDD commit `b4b3930` made the provenance and
coverage checks use the maintained recipe iterator. No campaign record,
population, margin, threshold, protocol, implementation result, or output path
changed. The same compiled evidence was then resumed once, producing the
immutable 70-KiB decision with SHA-256
`aca365b4cbfbb220dfa6fc03e7e1ce56c8316d2f4590e803d180553a2e501ce1`.

The decision is **fail**:

- all three implementations completed every realization without a retained
  implementation failure;
- Hebog passed 109 of 114 absolute gates and failed five: catastrophic-outlier
  fraction was 0.005104 against a 0.005 maximum, median position was 0.02736
  against 0.02 beam, median peak-flux error was 0.02942 against 0.02, median
  fitted-axis error was 0.05029 against 0.05, and median deconvolved-axis error
  was 0.10340 against 0.1;
- one source in seed `2026110310` was unmatched by Hebog. The frozen
  uncertainty endpoint construction requires every eligible source match, and
  its vectorized endpoint-family error handling therefore reported all 20
  primary and all 20 secondary paired endpoints as indeterminate;
- the catastrophic-tail stronger-Hebog envelope failed; the other four named
  envelopes passed; and
- released PyBDSF failed 53 absolute gates and pinned master failed 55 on the
  same truth population, compared with Hebog's five. Hebog is substantially
  stronger overall, but it remains slightly worse than both references on
  median position and worse on catastrophic fraction.

The paired indeterminacy is an evaluator limitation exposed by the final
population, but it does not alter the independent five-gate absolute failure.
Under the reviewed one-look and no-post-inspection-tuning rules, this campaign
cannot be rerun, replaced, or rescored under an amended scientific decision.
The controlled Phase 4 performance matrix is consequently ineligible, and
Phase 4 remains **not ready**. Any follow-on correction requires a newly
reviewed milestone based on analytic and independent development/regression
evidence; this viewed population may be used only to report and explain the
terminal result.

Human review of this final evidence is pending. Review must acknowledge the
immutable failure and decide whether to close Phase 4 as not passed or create
a separately governed follow-on scientific milestone; it cannot convert this
decision to a pass.

## Post-result diagnostic first pass

This diagnostic uses the final population only to explain the terminal
decision. It is not an algorithm-selection or threshold-tuning dataset.

- All 98 gated Hebog catastrophic rows are fitted-axis failures; 96 occur at
  an image edge and 94 are SNR-10 sources. Twenty-five have the current
  undifferentiated `fit-at-bound` flag. Reproducing seed `2026110493`, source
  16, shows its fitted centre pinned to the upper image boundary and its major
  sigma inflated from the injected 2.04 pixels to 6.62 pixels. This confirms
  one boundary-ridge failure while the other 73 non-bound rows show that a
  simple `fit-at-bound` rejection is not sufficient.
- Hebog's position error is worse than both references in about 61% of common
  source pairs. Its median and 95th percentile are worse across the aggregate
  population and the median gap occurs in every SNR stratum, especially for
  unresolved, edge, and low-SNR sources. The passed normalized position-bias,
  coverage, and dispersion gates make a WCS convention error unlikely; the
  working hypothesis is excess variance from fitting a free shape and
  background under correlated noise.
- Peak-flux and fitted/deconvolved-axis medians fail their absolute gates but
  remain better than both references. They require improvement against the
  community standard without sacrificing that existing advantage.
- Hebog is worse on the 95th-percentile integrated-flux error and slightly
  worse than released PyBDSF on the fitted-axis tail. The largest rows are
  truncated edge sources whose free fitted area extrapolates well beyond the
  observed source footprint.
- The evaluator's joint indeterminacy is independent of these science
  failures. `uncertainty_arrays` raises for one missing source before the
  shared paired statistic is built, so the evaluator cannot retain otherwise
  valid binary, group, and catastrophic endpoints. A follow-on evaluator must
  isolate endpoint missingness while leaving this decision unchanged.

The recommended disposition is to acknowledge Phase 4 as terminally not
passed and authorize the separately governed
[Phase 4R recovery milestone](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#phase-4r-compact-measurement-scientific-recovery).
Its implementation choice must come from analytic and independently seeded
development/regression evidence. The first candidates are a data-selected
beam-constrained/free nested fit, parameter-specific validity and
identifiability checks, and then—only if needed—a bounded correlated-noise
generalized least-squares point estimator. This follows Condon's use of a
priori size constraints to reduce amplitude errors and Aegean 2.0's treatment
of correlated noise and forced fitting, while retaining the independent
position, flux, size, completeness/reliability, and catastrophic measures
recommended by radio source-finding challenges.

## Phase 4R development authorization

Gemma Danks, Data Processing Software Engineer, approved the recommended
terminal disposition and Phase 4R development direction on 2026-08-04. Phase
4 remains not passed and its final campaign remains immutable. The approval
authorizes analytic and independent development/regression work, the
endpoint-isolation repair, fit-model ablations, and preparation of a new
Phase 4R protocol. It does not authorize a rescore, rerun, replacement
campaign, or future qualification opening before the exact model-selection
rule, metric registry, margins, power, regression evidence, and stopping rule
receive the later named review required by the plan.

Phase 4R development and confirmation inputs were then frozen before any fit
selection behavior changed. `phase-4r-development.json` contains 20 viewable
ablations and `phase-4r-regression.json` contains 100 confirmation-only
realizations. Their seed ranges are disjoint from one another and every prior
Phase 4 population. The regression geometry rotates and relocates the source,
beam, correlated-noise, and WCS configuration rather than repeating the
development pixels. Both cover SNR 10, 15, 25, and 50; unresolved, marginal,
and clear shapes; edges and corners; an unresolved blend; RMS gradients; an
invalid patch; and correlated noise.

## Phase 4R fitting development result

Only the 20-realization development matrix was used to select the fitting
candidate. The frozen 100-realization regression matrix remained unopened.
The factorial comparison selected:

- a fixed-zero offset because the governed input is already a
  background-subtracted residual;
- exact owned-region support, which improved position, flux, and shape medians
  over bounded context while retaining the context policy as an explicit
  ablation;
- a nested restoring-beam/free-elliptical fit, with physical bound contact and
  ill conditioning treated as rejected-model evidence; this is frozen as the
  explicit Phase 4R `beam-or-free` policy while the library default remains
  the Phase 4 `free-only` oracle;
- a beam-centroid/free-shape retry for a rejected free edge fit; and
- exact bounded correlated-noise GLS for at most 512 retained pixels, with an
  explicit diagonal/sandwich fallback above the cap.

The selected candidate completed all 20 realizations and all 240 individual
source matches without a catastrophic row. Its overall median/95th-percentile
absolute errors were 0.02477/0.10539 beam for position, 0.03334/0.13972 for
peak flux, 0.03541/0.28075 for integrated flux, 0.02710/0.13956 for fitted
axes, and 0.09779/0.33918 for deconvolved axes. Every one of those values is
better than released and pinned-`master` PyBDSF on the identical images.

The unresolved-blend median total-flux error was 0.04663, also better than
both references at 0.05247. Its 95th percentile was 0.13150 versus 0.11432,
a 0.01718 development difference inside the predeclared 0.02 practical
margin. An island-pixel-sum ablation was rejected: despite being a useful
separate catalogue field, threshold truncation increased the group median to
0.11425 and failed the existing 0.10 absolute limit. Association diagnostics
therefore continue to use the fitted total before individual unresolved rows
are canonicalized to peak-as-total.

Hebog produced one 5-sigma noise candidate in the final development seed,
giving 99.62% reliability versus 100% for both references. The 0.38%
difference is within the predeclared 0.5% practical resolution and is retained
as a confirmation endpoint; it was not removed with an
implementation-specific threshold. The selected estimator materially
improved normalized-residual bias and dispersion over both PyBDSF references
on this small diagnostic set.

## Phase 4R confirmation attempt one

The candidate was frozen as exact local commit `27edde3` before the
confirmation-only population was opened. Hebog completed 98 of 100
realizations. Seeds `2026130024` and `2026130095` each retained the same typed
`IncompleteCompactCatalogueError`: one fit omission made the compact catalogue
incomplete. Released PyBDSF 1.14.1 and pinned PyBDSF `master` at `c70103be3`
completed all 100 identical images. The Hebog attempt therefore failed the
availability gate before aggregate accuracy could qualify it.

This record identifies the failed realizations for immutable provenance only.
Their pixels, truth rows, and internal intermediate products were not opened
for diagnosis or tuning. A generic analytic model-selection test independently
showed that a failed smaller beam candidate could discard an otherwise valid
and identifiable free fit. Recovery iteration two returned to analytic and
new development evidence. Its 40 development and 100 confirmation-only seeds
were frozen, with disjoint seed ranges, before another production fitting
change.

## Phase 4R recovery iteration two development result

The second iteration used only the 40 viewable realizations frozen before its
production changes. The 100 confirmation-only seeds remained unopened. A
generic selection correction now preserves an identifiable free fit when its
smaller beam alternative fails. For a physical-bound fallback, the retry fixes
its centroid to the independent intensity-weighted moment rather than the
truncated beam fit. Hebog then completed and matched every declared compact
group in all 40 images, with 100% reliability, fitted, classification,
association, and uncertainty availability, point specificity,
clear-extension recall, and zero catastrophic rows.

The earlier Gaussian-only unresolved-blend total retained a 0.14821 tail,
worse than the 0.11301 dual-reference result by more than the registered 0.02
resolution. Literature-supported threshold-only volume correction did not
resolve that tail and was rejected. A fixed three-sigma restoring-beam
aperture, normalized by the pixelized beam fraction visible through the exact
image, validity, and competing-region masks, produced 0.04788 median and
0.10243 tail errors. Both improve on the two PyBDSF references at
0.04830/0.11301. Gaussian component flux and the Rapthor-facing unresolved
peak-as-total convention remain unchanged; the aperture is explicit
association photometry.

Across the 21 existing overall paired endpoints, Hebog is in the desirable
direction or equal on 20. The remaining unresolved-group position median is
0.02828 beam versus 0.02786, a 0.00042-beam difference inside the registered
0.01 practical resolution; Hebog's corresponding tail is better. Across the
14 overall distribution metrics Hebog is better on 13; its deconvolved-angle
tail differs by 0.054 degree inside the registered 1-degree resolution. These
finite-sample signs must be evaluated by the direction-aware practical-margin
rule rather than treated as meaningful scientific regressions.

## Phase 4R metric-governance amendment

The complete Phase 4R evaluator exposed two ambiguities before the second
confirmation population was opened. First, requiring an exact favourable
sign for every finite development point estimate would reject equivalent
implementations about half the time. The registered development/regression
point rule now requires every metric independently to remain inside its
already approved practical resolution; qualification still requires the
paired one-sided 95% upper bound inside that margin. There is no averaging or
compensation across metrics.

Second, the earlier Phase 4 evaluator applied 0.02-beam and 2% exact-reference
thresholds to raw absolute-error medians from a noisy population containing
SNR-10 sources. Noise alone gives an unbiased estimator a non-zero absolute
error distribution, so this double-gated sampling scatter rather than bias or
scientific equivalence. In Phase 4R, noisy position, flux, axis, and angle
medians and tails remain mandatory report fields and independent
dual-reference gates. Absolute generated-data gates remain on catalogue and
measurement availability, completeness/reliability, classification,
catastrophic failures, unresolved groups, and powered normalized-residual
bias, coverage, and dispersion. The strict 0.02-beam/2% requirements remain
unchanged for analytic noiseless and exact compact-reference fixtures.

Gemma Danks, Data Processing Software Engineer, approved these governance
corrections as recommended on 2026-08-04, before the frozen second
confirmation population was opened.

The evaluator maps every legacy absolute decision back to the registry and
refuses an unregistered gate, preserves sample-limited report-only intervals,
and evaluates 35 metrics overall and in every applicable governed stratum
against released and pinned-`master` PyBDSF separately. On the 40 viewed
iteration-two development realizations, the final position candidate passed
all 450 such comparisons. The only remaining red development findings are two
powered edge normalized-bias confidence intervals; their central estimates
remain inside the absolute bias range and must be confirmed on independent
regression and, ultimately, the powered qualification population.

## Phase 4R confirmation evaluator correction

The frozen iteration-two confirmation population was opened only after the
candidate was committed at `86e7e02` and both reference environments and the
complete development result were recorded. Hebog, released PyBDSF 1.14.1,
and pinned `master` at `c70103be3` each completed all 100 realizations. The
first immutable decision has SHA-256
`bb39bb6be81596a3a5d0ed95a2400f2d22588b96ee2553fb9a8ffd9fc12b6fb9`.

That decision exposed a generic evaluator implementation defect. The frozen
registry states
`within-practical-margin-on-frozen-development-regression` for point
estimates and reserves
`one-sided-paired-upper-limit-within-practical-margin` for qualification.
The implementation nevertheless ran 10,000-resample qualification intervals
during regression. This produced 25 interval failures, including cases where
Hebog's point estimate was better, and made the 100-image confirmation pay a
power requirement designed for the later 600-image one-look population.

The campaign, rows, metric values, registry, margins, and historical decision
remain unchanged. A TDD correction now makes both development and regression
evaluate every point regression against its registered practical margin;
only qualification computes and gates the paired upper bound. The corrected
evaluator may rescore the same immutable campaign because this restores the
predeclared rule rather than selecting a new rule from its result. The
independent catastrophic-rate point and absolute failures remain eligible
scientific findings and cannot be removed by this correction.

The corrected decision has SHA-256
`86763b8d25b693066afc9d9b00e2fbd5ca2f084ad8560183711456c90fadb975`.
It passes 444 of 450 dual-reference comparisons. The six failures are one
independent endpoint: catastrophic-outlier fraction overall and in the
governed marginal-shape and SNR-15 strata against each reference. Hebog has
10 catastrophic rows among 1,200 eligible matches, compared with two for
released PyBDSF and five for pinned `master`. Aggregate, identity-free
diagnostics attribute eight Hebog rows only to deconvolved-axis error and two
only to fitted-axis error. All other position, flux, fitted/deconvolved shape,
classification, association, completeness, and reliability point metrics
remain inside their margins; Hebog's fitted/deconvolved shape medians and
95th percentiles remain better than both references.

This result is a failed confirmation, not a tuning set. It is archived, and
no source identifier, row, truth value, or image from it will be used to
select a correction. The next development boundary is the independently
seeded, viewable 200-realization manifest
`config/datasets/phase-4r-development-3.json`, frozen with file SHA-256
`06ad23df2a747ea33136c4e226a1400c231ac76ea1422adb40979e01dbfd884a`
before any post-confirmation fitting change.

## Phase 4R tail evidence and qualification authorization

The unchanged candidate completed all 200 images in that independently
frozen development population. Released PyBDSF and pinned `master` also
completed every image. Hebog produced nine catastrophic matches among 2,400
eligible rows, compared with 19 and 30 respectively. Across the iteration-two
and tail-development populations, the corresponding counts are 9/2,880,
23/2,880, and 36/2,880. Hebog passed all 450 independently evaluated
dual-reference point decisions and its absolute catastrophic gate. Candidate,
released-reference, master-reference, compiled, and decision SHA-256 values
are `3749e52eb9bcb1d3ba101724646cc43c0c6ae911710530df71effc01368aa9fd`,
`a2ed5f9fbba545c8406303366b4d588eb2d4bc56d0ba2768dd9f36ffe8937053`,
`6f4bf40983477f2dbb803e5f2a35e5ffd059f4d6eea7ed5f0ef152dd20a47ee2`,
`46a8994448556a852cc9d5e631123f08f64ad24bb1925d4aa2140862ba5dc9ac`,
and `7f19261a689c97f284801ebd81f30f4bb51e6cd68b7eb9130b0f6c54a3d946f9`.

This is evidence that the confirmation crossing was stochastic, not that its
failed decision should be overwritten. The current estimator remains
scientifically preferable to a correction selected only to remove a rare
sample tail. Condon describes low-SNR amplitude overestimation from fitting a
peak toward the local noise gradient and supports a priori size constraints
when the size is genuinely known
([Condon 1997](https://ui.adsabs.harvard.edu/abs/1997PASP..109..166C)).
Aegean 2.0 treats the inverse noise covariance, simulated normalized-residual
calibration, and prioritized fitting as the relevant radio-source practices
([Hancock et al. 2018](https://arxiv.org/abs/1801.05548)). Correlated-noise
parameter biases are second order in inverse SNR
([Refregier & Brown 1998](https://arxiv.org/abs/astro-ph/9803279)), while
general maximum-likelihood photometry likewise shows larger positive flux
bias as more source parameters are fitted
([Portillo et al. 2020](https://arxiv.org/abs/1902.02374)). The ASKAP/EMU
challenge reinforces evaluating low-SNR flux bias and catastrophic tails
explicitly rather than hiding them in an aggregate score
([Hopkins et al. 2015](https://doi.org/10.1017/pasa.2015.37)).

Gemma Danks, Data Processing Software Engineer, approves preserving the
failed confirmation and advancing the unchanged candidate to one powered,
one-look Phase 4R qualification. This named exception was approved on
2026-08-04 before qualification seeds or outcomes were created or inspected.
It does not rescore confirmation, relax any absolute threshold or practical
margin, or permit another qualification attempt. Every registered
qualification gate remains binding.

The reviewed qualification population was subsequently frozen, still before
any outcome existed, in `config/datasets/phase-4r-qualification.json`.
It contains 600 new noise realizations and changes the source positions,
association positions, invalid rectangle, beam/noise orientation, sky field,
WCS scales and rotation, background, and RMS-gradient orientation while
preserving the reviewed SNR and morphology populations. The manifest SHA-256
is `93f2d9f876b9b3f58df09ad64796e39ed404980a14f7c4542f0ae2b3120c42e4`;
the canonical recipe SHA-256 is
`82870d14dbe163c1d1ca79d0b163bc69c406ed2288da3cf489ebdb03989de5fc`.
The freeze path refuses overwrite, validates the complete schema, and has an
executable contract proving that qualification changes every predeclared
field family rather than only changing seed numbers.
