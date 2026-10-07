# Compact Gaussian fitting

Hebog fits every eligible compact deblended region. Regions whose fitting
contexts touch are fitted jointly, so a neighbour's light is modelled rather
than absorbed. The `beam-or-free` policy evaluates a nested free-elliptical
and restoring-beam-constrained model rather than making every source pay the
variance of a free shape. Hebog does not skip apparently easy regions or
substitute moment parameters for fitted parameters.

## Numerical model

`find_sources` fits in two stages of `hebog.stages.objects`.
`run_fit_parent_stage` joins the components whose fit contexts touch into fit
parents, following a chain of any length from per-core summaries; a parent
with more components or pixels than one joint fit admits, or wider than the
compact bound on its window, is fitted island by island.
`run_component_fit_stage` then fits each parent with
`fit_compact_gaussian_mixture` inside one coarse executor task, which keeps
the physical residual, RMS, exact component labels, moment calculation and
nonlinear fit together. A task holds several parents; Hebog does not create
one Dask task per source.

The free model has positive peak amplitude, global zero-based `(x, y)`
centroid, two positive pixel sigma axes and pixel-space orientation, fitted
to the already background-subtracted residual with no further offset. The
smaller model fixes the axes and orientation to the restoring beam. The
reviewed profile fits exact deblended-region membership. Moment parameters
initialize both fits, and configuration bounds limit centre movement, axes,
amplitude, iterations, and convergence tolerance.

The axis-ratio limit is a physical ellipse limit: both sigma axes must be
positive, and `max(sigma_first, sigma_second) / min(...)` must not exceed
`maximum_axis_ratio`. Optimizer axes are interchangeable when the orientation
turns by 90 degrees; their temporary ordering must not change admission.
This check applies to every fit before ordered parameters are published. An
inadmissible fit retains its initializer and explicit failure diagnostics,
rather than producing a Gaussian row. Independent source support and
signed-aperture measurements remain available.

The public continuum profile fits with the diagonal-weighted point estimator:
each pixel residual is weighted by its local RMS, and uncertainties use the
correlated-noise sandwich covariance described below. Generalized least
squares (GLS) whitened residuals with the restoring-beam correlation. On images
whose noise is not beam-correlated, that amplified pixel-to-pixel noise and
lost most components that pinned PyBDSF `master` measured, so the profile no
longer uses it. The quick science check tracks this with its white-noise case.

GLS remains available as an explicit configuration. When the image declares
a correlated-noise covariance, the GLS point estimator uses generalized least
squares for regions of at most 512 retained
pixels when the declared correlation matrix is numerically resolved. It
factorizes only that bounded matrix and whitens both residuals and Jacobians
before SciPy sees them. Larger regions, or images without a correlation
model, take an explicit diagonal-weighted fallback; the reason is retained
in diagnostics. This cap prevents an accidental quadratic-memory or
cubic-work path for a large island. The component still runs inside its coarse
batch task, so no per-source Dask graph is introduced.

Cholesky success alone is insufficient: oversampled smooth correlations can
be numerically singular without triggering a factorization exception. Hebog
uses [LAPACK's condition estimator](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lapack.dpocon.html)
on the existing factor, without a second decomposition or a dense inverse.
An estimated reciprocal 1-norm condition number at or below `n * eps(float64)`
triggers `correlation-ill-conditioned`. This dimension-scaled roundoff guard
follows the numerical-resolution scale used by
[NumPy's rank criterion](https://numpy.org/doc/stable/reference/generated/numpy.linalg.matrix_rank.html);
it is a condition estimate, not an exact SVD rank test. Failed estimation
reports `correlation-conditioning-failed`; failed Cholesky reports
`correlation-factorization-failed`. All three use the existing diagonal point
estimator with correlated-noise sandwich errors, not independent-pixel errors.
No unmeasured white noise is added to make the likelihood invertible.

This check is independent of source brightness and fitted residuals. It does
not certify that every converged Gaussian is an adequate physical model, nor
does it change detection thresholds or replace centroids with pixel peaks.
Source support is retained independently of Gaussian measurement
availability.

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
- bilinearly sampled local RMS at the fitted centroid; and
- bounded optimizer diagnostics.

Position and flux covariance is retained only when the selected information
matrix is nonsingular and produces finite positive variances. A whitened fit
uses its generalized-least-squares information and is flagged
`correlated-noise-gls-errors`. A diagonal point fit with declared correlation
uses the generalized OLS sandwich covariance and is flagged
`correlated-noise-sandwich-errors`; an absent correlation retains
`formal-independent-pixel-errors`. Shape errors remain absent. Free-fit
integrated-flux uncertainty is not calibrated for resolved or marginal
sources, so that uncertainty remains report-only.

The pipeline-neutral default is the free-elliptical model; the reviewed
continuum profile explicitly opts into the `beam-or-free` policy, so model
selection cannot silently change a caller's policy. Every published candidate
must be finite, away from physical parameter bounds, and sufficiently well
conditioned under the existing configured information limit. Free-only
fitting and absent beam metadata do not bypass those checks. An invalid
whole Gaussian is never published; source support and independent source
photometry remain available instead.

The current public composition additionally checks beam fallbacks selected
because the free ellipse failed numerical, bound or identifiability admission.
It applies the residual-adequacy rule to the joint model on its declared
likelihood pixels, attributing features to the nearest component. The rule
admits residual features as detection does, positive and grown to the island
threshold from a detection-threshold seed on the original pixels, the residual
à trous scales or a matched-filter scale, and counts one only if it touches
those pixels. Unexplained emission belonging to such a fallback makes that
Gaussian `fit-model-inadequate`, not an ordinary unresolved measurement.
Its attempted-model diagnostics, detected identity, support and independent
source aperture remain available. Valid neighbours keep their parameters and
covariance from the same joint solution; no alternative fits are spliced in.
Unavailable peers supply no shape evidence but do not veto independent
resolved-arc evidence from at least three valid neighbours. This is a bounded
fallback correctness guard, not a general certification of every Gaussian or
a new chi-squared cutoff. Independent analytic controls govern it.

Under `beam-or-free`, a five-sigma log-area test selects clear extension directly.
Otherwise the nested candidates use BIC with the number of independent
samples appropriate to their residual model. A free candidate that pins a
physical bound or is ill conditioned is rejected in favour of the beam model,
or the fit reports failure. The selected and rejected model
identities, exact bound parameters, bound distances, condition number, visible
footprint, retained geometry, and fallback reason remain auditable.
Gaussian-component publication applies a second, explicit whole-model test.
The source keeps the conservative five-sigma selection needed by Rapthor. A
free component rejected at that boundary is nevertheless published when its
log-area extension exceeds 1.5 standard errors; otherwise the complete
restoring-beam ellipse is published. Axes, angle, centroid, and fitted total
always come from the same selected fit. This avoids both the variance of a
free angle for beam-like objects and the scientifically incoherent alternative
of mixing free axes with a beam angle. PyBDSF and Aegean likewise represent a
Gaussian component as one fitted ellipse; Hebog's explicit low-information
beam fallback is recorded in diagnostics rather than disguised as a free fit.

No fit publishes an aperture flux of its own. Every fit `find_sources` makes
is a joint fit, and an aperture around one component of a joint fit would
also sum its neighbours' light, so the fit's association aperture is
discarded. Under the continuum profile a source's `ASSOCIATION_APERTURE_FLUX`
is measured over the source's own footprint, and the compact profile leaves
it unavailable, as the [output reference](public-products.md) describes.

Centroid bounds may extend beyond the detected region but never beyond the
sampled pixels. Extension classification is repeated at the catalogue
boundary using the reviewed ATLAS log integrated-to-peak statistic; see
[compact astrometry](compact-astrometry.md). A component publishes the
infinite-plane fitted total whether or not it is resolved, and a source's
integrated flux is the sum of its components', as the
[output reference](public-products.md) describes. A component whose fit is
not admitted creates no Gaussian row, and a source with no admitted fit
takes its integrated flux from its own aperture. If the fitted centroid lacks
local RMS interpolation support, the fit records the already measured finite
owned-region RMS and `local-rms-region-mean-fallback` instead of publishing a
NaN or failing the complete catalogue.

Invalid moments and regions with fewer than seven owned pixels return a typed
unavailable fit. Exhausted iterations and scientifically invalid fitted
parameters return a typed failed fit that retains the moment initializer and
diagnostics. Unknown values are never encoded as zero.

## Integrated-flux uncertainty calibration

The correlated-noise sandwich covariance of the diagonal-weighted fit is the
formal one-sigma uncertainty. On the M1 calibration population
(`config/datasets/m1-flux-calibration.json`: isolated sources in five
independent realizations of each noise class), its pulls against injected
truth on beam-correlated noise have a standard deviation of about one for
position, peak flux and fitted axes (0.96 to 1.02) and 1.08 for integrated
flux. The former GLS covariance was overconfident there, with pull standard
deviations up to 2. On pixel-independent noise the uncertainties are
conservative (pull standard deviation 0.32 to 0.57), because they assume
beam-correlated noise, as Condon-style errors do.

Pulls describe only the components that publish an uncertainty. A shape
uncertainty accompanies a free fit, not a beam-constrained one, so a shape
pull covers the minority whose free model survived the extension test, which
selects upward fluctuations. Measured over 340 matched beam-correlated components, a shape pull covered 8 to 20 per cent of
beam-sized components and read about +1.7, while the whole population's
major-axis excess against truth was zero. Report how far published values
lie from truth over every matched component, and read a pull against the
share of the population it covers.

Measured that way, published sizes carry the expected low-SNR noise bias of
fitted second moments, and integrated flux follows it. Median excess against
truth, by injected size and signal-to-noise:

| Injected size | SNR 10 | SNR 20 | SNR 50 |
| --- | --- | --- | --- |
| Beam | axis 0.0%, flux +6.8% | axis 0.0%, flux +4.9% | axis 0.0%, flux +0.5% |
| 1.15 beam | axis +9.7%, flux +9.5% | axis +0.6%, flux −1.7% | axis +0.4%, flux −0.5% |
| 1.3 beam | axis +6.7%, flux +6.0% | axis +2.9%, flux +1.3% | axis +0.4%, flux 0.0% |
| 1.5 beam | axis +9.0%, flux +14.9% | axis +3.1%, flux +5.5% | axis +1.3%, flux +0.9% |

Beam-sized sources are published at the beam, which is exactly their truth,
so their axis excess is zero by construction; 80 to 92 per cent of them are
beam-constrained. Sources 15 per cent larger than the beam are
beam-constrained only at SNR 10, and then for 10 per cent of them, so the
extension test does not flatten slightly resolved sources at usable
signal-to-noise. The integrated-flux tail is the wider concern: the 95th
percentile of absolute excess is 29 to 58 per cent at SNR 10, 11 to 14 per
cent at SNR 20 and 5 to 6 per cent at SNR 50. The
reviewed external component profile additionally applies a 0.075-sigma
downward correction to the fitted Gaussian total before celestial catalogue
publication. It leaves the fitted amplitude, axes, angle, centroid, formal
error, and covariance unchanged and adds the
`fitted-integrated-flux-bias-corrected` quality flag. The correction is
explicit in that profile's configuration; the pipeline-neutral default is zero.

This follows the standard practice of reporting calibrated Gaussian-fit
uncertainties while keeping the correction distinguishable from the formal
covariance. PyBDSF documents Gaussian parameter errors based on Condon (1997),
including the lower-variance fixed-shape case. Hebog does not claim that its
covariance is the same implementation. Its small point correction was
selected on seed-disjoint injected truth after a global error multiplier was
rejected for causing over-coverage. See
[Condon (1997)](https://adsabs.harvard.edu/pdf/1997PASP..109..166C) and the
[PyBDSF processing reference](https://pybdsf.readthedocs.io/en/latest/process_image.html).

The compact configuration aligns the detection and deblending minima with
this seven-pixel fit requirement. If a prominent watershed peak initially
owns fewer pixels, its basin is merged across its strongest shared saddle
before measurement. This preserves all parent-island pixels and prevents a
small noise-supported child from making an otherwise valid compact catalogue
incomplete.

## Determinism and scope

The fit result is a frozen scheduler-safe record. Canonical region order is
inherited from deblending, and serial and Dask executors produce equal compact
records. Which components form one source is decided afterwards by source
association, not by the fit; see
[How Hebog finds sources](../explanation/how-hebog-works.md).
