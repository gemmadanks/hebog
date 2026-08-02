# Phase 4 scientific review record

This record prepares the named human review required before Phase 4 compact
measurement semantics become a stable experimental default. It freezes the
proposal and the unseen qualification inputs; it does not record approval,
inspect qualification results, or claim catalogue equivalence.

## Reviewer and decision

- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer
- **Review capacity:** Project owner and named ADR decider reviewing the
  Hebog/Rapthor source-finding contract
- **Review date:** Pending
- **Decision:** Pending
- **Required amendments:** Pending
- **Qualification-data confirmation:** The Phase 4 qualification recipe,
  source population, thirty deterministic noise realizations, and proposed gates
  were frozen before measurement or fitting results were generated or
  inspected. They must remain outside routine tuning.

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

## Proposed decisions

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
sample dispersion, and nominal 68.27% coverage. Position and flux have
provisional quantitative gates. Shape-error calibration remains report-only
because the literature does not justify treating formal shape covariance as
reliably calibrated by default. An unavailable error is null plus a canonical
quality flag, never zero.

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

### 7. Proposed gates

`config/contracts/phase-4-scientific-gates.json` retains the approved Section
5 high-SNR position and flux margins for isolated compact sources and adds
provisional fitted/deconvolved
axis, position-angle, unresolved-classification, association, catastrophic
outlier, and uncertainty-calibration margins. Low-SNR crossings and shape
uncertainties remain report-only. The contract is `frozen-provisional`; it
must not become `reviewed-provisional` until this review approves or amends
the actual values.

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
| Catastrophic matched-row outliers | none | at most 0.5% |

Completeness and reliability use all declared compact SNR-at-least-10 truth;
position and flux use the existing isolated compact population; shape gates
use eligible compact rows; association uses the declared compact association
population; and catastrophic rates use matched compact rows. The position-angle
limits apply independently to fitted and deconvolved ellipses, so their
populations cannot dilute each other.

The catastrophic definition is also explicit: more than 0.5 beam positional
error, 50% peak or integrated-flux error, 50% fitted-axis error, or 100%
deconvolved-axis error. Position and flux values retain the already reviewed
Section 5 gates. The new shape, association, classification, and catastrophic
limits are recommendations requiring specific review.

For position and flux uncertainties, each reported stratum needs at least 30
samples. The proposed one-sigma coverage may differ from 68.27% by at most ten
percentage points; absolute mean normalized residual must be at most 0.15 and
normalized-residual sample standard deviation must remain between 0.8 and
1.2. These are calibration gates, not a requirement to mimic PyBDSF's formal
error values.

### 8. Governed data

The Phase 4 manifests add:

- noiseless sub-pixel unresolved/resolved shape truth;
- an SNR ladder with negative background, affine varying RMS, invalid pixels,
  unequal pixel scales, rotated WCS metadata, and an edge source;
- equal/unequal blends and a crowded association regression;
- rotated deconvolution cases spanning unresolved, marginal, resolved, and
  image-edge populations; and
- one unseen 512-square qualification population with thirty deterministic
  noise realizations, giving at least thirty samples in every declared SNR,
  shape, blend, and edge class.

Generator v2 remains window-addressable and partition-invariant. Earlier
generator-v1 recipe checksums are unchanged. No qualification image,
measurement, fit, comparison, or pass/fail result has been produced or
inspected during this preparation.

## Decision checklist

The reviewer should explicitly accept or amend:

- [ ] MFS Stokes I, Jy/beam, background-subtracted measurement scope;
- [ ] pixel-sum island flux and fitted-Gaussian component/source flux meanings;
- [ ] local RMS, ICRS, pixel origin/order, tangent-plane, and position-angle
      conventions;
- [ ] provisional one-region/one-component/one-source compact association;
- [ ] unresolved, unavailable-error, failure, and compatibility-sentinel
      semantics;
- [ ] fit-all-before-selective-fitting evidence order;
- [ ] development/regression coverage and untouched qualification fitness;
- [ ] every provisional numerical margin and report-only category; and
- [ ] any departure from literature or cross-pipeline consensus.

Approval updates this record's decision and date, records amendments, changes
the two Phase 4 contract statuses to `reviewed-provisional`, and closes the
remaining Step 1 review item with focused contract tests. Rejection or a
material amendment occurs before qualification inspection; replace the
qualification recipe and gates if preserving an unbiased held-out decision
requires it.
