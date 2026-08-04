# Compact Gaussian fitting

Phase 4 fits every eligible compact deblended region. Phase 4R evaluates a
nested free-elliptical and restoring-beam-constrained model rather than making
every source pay the variance of a free shape. Hebog does not skip apparently
easy regions or substitute moment parameters for fitted parameters.

## Numerical model

`run_compact_gaussian_fit_stage` keeps the physical residual, RMS, exact
watershed membership, moment calculation, and nonlinear fit inside the same
coarse executor task. A task may contain several islands and regions; Hebog
does not create one Dask task per source. Retained image arrays stay subject to
the Phase 3 coarse-batch pixel limit.

The full model has positive peak amplitude, global zero-based `(x, y)`
centroid, two positive pixel sigma axes, pixel-space orientation, and an
optional bounded local residual-background offset. The smaller model fixes
the axes and orientation to the restoring beam. The Rapthor campaign uses the
already background-subtracted residual, fixes the remaining offset to zero,
and fits exact deblended-region membership; the alternate offset and bounded
context policies remain explicit development ablations. Moment parameters
initialize both fits, and configuration bounds limit centre movement, axes,
amplitude, background offset, iterations, and convergence tolerance.

When the image declares a correlated-noise covariance, the Phase 4R point
estimator uses exact generalized least squares for regions of at most 512
retained pixels. It factorizes only that bounded correlation matrix and
whitens residuals before SciPy sees them. Larger regions, or images without a
correlation model, take an explicit diagonal-weighted fallback; the reason is
retained in diagnostics. This cap prevents an accidental quadratic-memory or
cubic-work path for a large island. The component still runs inside its coarse
batch task, so no per-source Dask graph is introduced.

The production implementation uses SciPy's bounded trust-region
`least_squares` solver. An independent Astropy `Gaussian2D`/TRF fit agrees on
the governed analytic ellipse. SciPy was selected because it directly exposes
the weighted residual, bounds, Jacobian, evaluation limit, and convergence
diagnostics through one narrow dependency already used by Hebog. No custom or
native optimizer is maintained.

## Measurements and availability

A valid fitted component reports:

- fitted peak brightness in Jy/beam;
- global pixel centroid, ordered sigma axes, and orientation;
- an infinite-plane fitted-Gaussian integral used for resolved-source
  measurement and extension testing;
- a mask-aware three-sigma restoring-beam aperture flux for compact-source
  association, kept distinct from both the Gaussian integral and owned-pixel
  photometry;
- bilinearly sampled local RMS at the fitted centroid; and
- bounded optimizer diagnostics.

Position and flux covariance is retained only when the selected information
matrix is nonsingular and produces finite positive variances. A whitened fit
uses its generalized-least-squares information and is flagged
`correlated-noise-gls-errors`. A diagonal point fit with declared correlation
uses the generalized OLS sandwich covariance and is flagged
`correlated-noise-sandwich-errors`; an absent correlation retains
`formal-independent-pixel-errors`. Shape errors remain absent. The powered
regression found that free-fit integrated-flux uncertainty is not calibrated
for resolved or marginal sources, so that uncertainty remains report-only.
Position, peak flux, and the peak-as-total unresolved policy pass their
applicable regression gates.

The established public default remains the single free-elliptical fit used by
the Phase 4 serial oracle. Phase 4R explicitly opts into the reviewed
`beam-or-free` policy; model selection therefore cannot silently change an
existing caller's catalogue. Under that policy, the free candidate must be
finite, away from every physical parameter bound, and sufficiently well
conditioned. A five-sigma log-area test selects clear extension directly.
Otherwise the nested candidates use BIC with the number of independent
samples appropriate to their residual model. A free candidate that pins a
physical bound or is ill conditioned is rejected; Hebog retries a free shape
at the independently measured intensity-weighted moment centroid and finally
uses the beam model or reports failure. The selected and rejected model
identities, exact bound parameters, bound distances, condition number, visible
footprint, retained geometry, and fallback reason remain auditable.

The association aperture is an explicit configurable radius, currently three
restoring-beam sigmas. Its flux is a direct sum of finite background-subtracted
pixels within that ellipse. The normalization integrates the pixelized beam
over exactly the same valid, non-competing support, so image edges and invalid
pixels reduce a recorded visible-beam fraction rather than silently losing
flux. This bounded aperture is used only for association and blend-total
comparisons; fitted component flux and Rapthor's unresolved peak-as-total
catalogue convention are unchanged.

Phase 4R also selects position independently from morphology and photometry.
The selected owned-region model continues to define peak, integrated flux,
shape, and extension. A second free elliptical likelihood uses all finite
bounded context belonging to the source or background while excluding pixels
owned by competitors. This avoids shifting the reported position toward only
the threshold-selected side of a low-SNR or edge source. The public default
continues to use the selected model's centroid; the governed campaign opts in
with `position_estimator="bounded-context-free"`.

If the context likelihood itself reaches an image boundary, Hebog does not
publish the clipped coordinate as an ordinary fit. It inverts the analytic
first two moments of a one-sided truncated normal using the independently
measured intensity centroid and covariance. The record identifies this rare
case as `bounded-context-truncated-moment`; its covariance remains the local
context-likelihood curvature and the separate quality flag keeps that
approximation auditable. Failure of either estimator leaves the selected
model centroid in force rather than inventing a coordinate.

Centroid bounds may extend beyond the detected region but never beyond the
sampled image. Extension classification is repeated at the catalogue boundary
using the reviewed ATLAS log integrated-to-peak statistic. If it does not pass,
the source remains unresolved and catalogue integrated flux and error use the
fitted peak and peak error. The raw fitted total remains available to governed
unresolved-association diagnostics before that individual-row
canonicalization.

Invalid moments and regions with fewer than seven owned pixels return a typed
unavailable fit. Exhausted iterations and scientifically invalid fitted
parameters return a typed failed fit that retains the moment initializer and
diagnostics. Unknown values are never encoded as zero. A normal catalogue may
only be built when every admitted compact region has a valid fit and there are
no Phase 5 deferrals.

The Phase 4 configuration aligns the detection and deblending minima with
this seven-pixel fit requirement. If a prominent watershed peak initially
owns fewer pixels, its basin is merged across its strongest shared saddle
before measurement. This preserves all parent-island pixels and prevents a
small noise-supported child from making an otherwise valid compact catalogue
incomplete.

## Determinism and scope

The fit result is a frozen scheduler-safe record. Canonical region order is
inherited from deblending, and serial and Dask executors produce equal compact
records. The current compact policy associates one fitted Gaussian and one
source with each successfully fitted deblended region. Multiscale emission and
selective fitting are deliberately outside this lane.
