# Phase 5 source-catalogue repair contract

**R0, 2026-09-07.** The scientific owner authorized R0--R6, their fixes and
required replays. This prospective contract precedes the implementation.
It does not qualify a replacement candidate. Closed sentinel
`ca03240db8452d84479139e848c0467815fdac9cea02168283fe69f52be8b63a`
remains a scientific failure. Its viewed realizations are not development
fixtures or a source of replacement thresholds.

## Scientific objects and measurements

- An **island** is a connected detection/support object, not proof of one
  astrophysical source. An independent compact pair may share an island.
- A **component** is an immutable owned detection region with a stable ID.
  A successful Gaussian fit is a measurement of that component, not a
  prerequisite for retaining the detection. A deferred, singular or failed
  fit must have an explicit disposition, never a fabricated Gaussian.
- A **source** is an association of components justified by morphology and
  measured structure. Membership IDs derive from canonical component IDs;
  relabelling, execution order and worker count must not change membership.
  This is an image-domain association, not a claim to identify a host galaxy.
- Compact Gaussian positions, fluxes and shapes come from the fitted model
  and its uncertainty. Threshold-limited moments remain initializers or
  explicitly labelled descriptors, not fitted or beam-deconvolved sizes.
- Irregular extended-source flux is measured from original background-
  subtracted pixels with source-owned support. Denoised pixels may estimate
  position, not silently replace flux. A source centroid may lie between
  components or in a shell's central hole; it need not coincide with a peak.
- Signed centroids must be conditioned. Non-finite, non-positive or
  cancellation-dominated estimates require an explicitly labelled stable
  alternative or unavailability. Positive-only sums must not masquerade as
  unbiased aperture flux when a signed aperture fails.
- Detection masks, component ownership, source unions and measurement
  apertures are different domains. Measurement-only pixels are not detections.
  A pixel contributes at most once to source-owned aperture photometry.
- Missing uncertainty is unavailable, not zero. Resolution unavailable is
  not unresolved. Source and component catalogues retain estimator and
  failure flags, including unavailable shapes and bounded-work deferrals.

## Selected repair approach

1. Preserve the existing deblender's independently supported compact peaks
   through source construction. Shared persistent support cannot override
   that separation without additional extended-emission evidence. Exercise
   independent unequal pairs and three-or-more compact peaks jointly with
   single-source shells, filaments and mixed emission; neither a blanket
   one-island/one-source rule nor a blanket one-component/one-source rule is
   acceptable. Retain ambiguous association evidence explicitly.
2. Reuse `algorithms.fitting`, `measurement` and `astrometry`: bounded SciPy
   least squares, the existing moment initializer, noise model, covariance
   propagation and WCS/beam transforms. Fit original pixels with supplied
   background/RMS and account for neighbouring components. Demonstrate any
   missing multi-component fitting capability with a failing analytic test
   before extending the existing fitter; do not introduce another optimizer.
3. Trace remaining extended support and fragmentation on independent
   development fixtures before changing those paths. Retain direct seeds,
   coarse/adaptive background and RMS errors, multiscale/persistent support,
   component owners, membership, publication and measurement counts.
   Association cannot repair absent detection support. Do not relax detection
   thresholds, change truth, or assume every deficit is a background error.
4. Publish valid sources even when another owner cannot supply a Gaussian.
   Make any public schema change explicit, fail clearly on stale schemas,
   and preserve support and diagnostics. Do not add legacy readers.
5. Publish bounded, array-free per-image diagnostics durably before the
   atomic terminal. Retain memberships, truth-match edges, signed residuals,
   stage counts, estimator/disposition flags and Serial/Dask comparisons.
   Verify hashes and completeness before allowing scratch cleanup. A digest
   alone is not a substitute for the records it authenticates.

The source/component distinction follows the documented separation of
Gaussian fits and grouped source measurements in
[PyBDSF](https://pybdsf.readthedocs.io/en/latest/process_image.html) and the
island/component products documented by
[Aegean](https://aegeantools.readthedocs.io/en/stable/includes/aegean.html).
These are methodological references, not implementation code or truth oracles.
Hebog's extended-source association still needs injected-truth validation;
agreement with another finder alone cannot establish correct membership.

## Red-first acceptance and execution order

Each defect gets a permanent failing test before implementation. The tests
must assert the intended missing behaviour, not fail from an import, missing
campaign directory or changed frozen fixture checksum. Preserve historical
fixture identities at their original revision; current fixtures test current
behaviour without rewriting closed reviews.

The short ladder covers the audited cancellation, truncated Gaussian and
degenerate-owner counterexamples, independent connected compact sources, and
single extended objects. Exact noiseless Gaussian measurements must recover
their generating parameters within numerical fitting tolerance. Noisy cases
use the existing analytic-truth metrics and predeclared scientific margins,
not new tolerances selected after looking at a campaign. Joint tests retain
flux, position, shape, uncertainty, completeness, reliability, split/merge and
mask evidence; source counts or binary-mask IoU alone are insufficient.

Run the exact public FITS/bundle and notebook-runner composition on synthetic
fixtures, including empty/all-NaN images, negative backgrounds, invalids,
low-SNR seams, edge/corner and non-square cases, unequal pixel scales,
rotated beams/WCS, thin owners, mixed valid/unavailable objects, and bounded
deferrals. Require Serial/existing-Dask and partition/order/retry invariance.
No private scheduler is introduced into the library.

R5 includes focused checks, branch-aware coverage and changed-branch review,
`just check`, equivalence, strict docs, package smoke and clean pre-commit
hooks. Record the affected runtime budget without claiming a Rapthor speedup.
Only then freeze replacement candidate and execution identities for R6.

R6 reuses unchanged reference products only when their semantics and hashes
remain valid. Changed candidate science requires new cumulative measurements.
Do not transfer old passes or accepted uncertainty to the replacement.
Keep all binding gates, comparators, margins and confidence rules unchanged.
Run a fresh unopened, seed-disjoint sentinel only after development and
cumulative gates pass. Preserve every known-risk geometry. Freeze the
population/power rationale, exact programs and container, disk budget and
end-to-end estimate before execution; surface a conflict with the requested
sub-12-hour final-campaign budget before starting. Monitor long runs hourly.
Scientific failure is terminal evidence, not permission to tune or rescore.

The owner's R0--R6 approval covers necessary fixes and replays; it does not
authorize weakening gates, overwriting evidence, release, cutover or pushing.
Release Please continues to own release management and broad cleanup remains
Phase 5.5.
