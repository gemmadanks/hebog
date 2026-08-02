# Phase 4 scientific review record

This record captures the named human review required before Phase 4 compact
measurement semantics become a stable experimental default. It approves the
amended contract and unseen qualification inputs; it does not inspect
qualification results or claim catalogue equivalence.

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
- A successfully fitted component's peak flux is its Gaussian amplitude and
  its integrated flux is peak multiplied by fitted Gaussian area divided by
  restoring-beam area.
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
remains report-only because the literature does not justify treating formal
shape covariance as reliably calibrated by default. An unavailable error is
null plus a canonical quality flag, never zero.

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
5 high-SNR position and flux margins for isolated compact sources and adds
reviewed-provisional fitted/deconvolved
axis, position-angle, unresolved-classification, association, catastrophic
outlier, and uncertainty-calibration margins. Low-SNR crossings and shape
uncertainties remain report-only. The contract is `reviewed-provisional` after
the amendments recorded here.

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
| Resolved/unresolved classification | 100% | at least 95% |
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
- **Decision date:** Pending
- **Decision:** Pending

The reviewer must confirm or amend:

- [ ] observed resolvability determines the per-emitter gated population;
- [ ] unresolved injected members use explicit truth association groups and
      group-level centroid/total-flux gates;
- [ ] one component/source remains the Phase 4 default for a single eligible
      maximum;
- [ ] joint multi-Gaussian model selection is deferred pending identifiability
      and reliability evidence; and
- [ ] the affected regression and unseen qualification definitions will be
      replaced and reviewed before qualification inspection.
