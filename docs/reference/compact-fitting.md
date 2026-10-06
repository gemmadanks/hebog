# Compact Gaussian fitting

Hebog fits every eligible deblended region. Regions whose fitting contexts
touch are fitted jointly, so a neighbour's light is modelled rather than
absorbed, and the `beam-or-free` policy chooses between a free elliptical
model and a restoring-beam-constrained one rather than making every source
pay the variance of a free shape. No region is skipped as easy, and moment
parameters never stand in for fitted ones.

## Numerical model

`find_sources` fits in two stages of `hebog.stages.objects`.
`run_fit_parent_stage` joins components whose fit contexts touch into fit
parents, following a chain of any length from per-core summaries; a parent
with more components or pixels than one joint fit admits, or wider than the
compact bound, is fitted island by island. `run_component_fit_stage` fits
each parent with `fit_compact_gaussian_mixture` inside one coarse executor
task that holds the residual, RMS, exact component labels, moments and
nonlinear fit together; a task holds several parents, and there is never one
Dask task per source.

The free model has a positive peak, a global zero-based `(x, y)` centroid,
two positive pixel sigma axes and an orientation, fitted to the
background-subtracted residual with no further offset; the beam model fixes
axes and orientation to the restoring beam. Moments initialize both, and
configuration bounds limit centre movement, axes, amplitude, iterations and
tolerance. Both sigma axes must be positive and their ratio within
`maximum_axis_ratio`, checked before the axes are ordered so that the
optimizer's temporary ordering cannot change admission. An inadmissible fit
keeps its initializer and failure diagnostics and produces no Gaussian row;
source support and the signed-aperture measurement remain.

The solver is SciPy's bounded trust-region `least_squares`, chosen because it
exposes the weighted residual, bounds, Jacobian, evaluation limit and
convergence diagnostics through a dependency Hebog already has. No custom or
native optimizer is maintained.

### Point estimator and covariance

The public continuum profile uses the diagonal-weighted estimator: each
pixel residual is weighted by its local RMS, and uncertainties come from the
correlated-noise sandwich covariance (`correlated-noise-sandwich-errors`)
when the image declares a noise correlation, or from formal independent-pixel
errors (`formal-independent-pixel-errors`) otherwise. Generalized least
squares whitened by the restoring-beam correlation remains available as
explicit configuration (`correlated-noise-gls-errors`): it factorizes only a
bounded correlation matrix, for regions of at most 512 retained pixels, and
larger regions or an ill-conditioned matrix take the diagonal estimator with
the reason retained. Conditioning uses LAPACK's estimator on the existing
Cholesky factor: a reciprocal condition number at or below
`n * eps(float64)` reports `correlation-ill-conditioned`, a failed estimate
`correlation-conditioning-failed` and a failed factorization
`correlation-factorization-failed`. No unmeasured white noise is added to
make the likelihood invertible.

## Measurements and availability

A valid fitted component reports the fitted peak in Jy/beam; the global pixel
centroid, ordered sigma axes and orientation; the infinite-plane
fitted-Gaussian integral; the bilinearly sampled local RMS at the centroid,
or the owned-region mean with `local-rms-region-mean-fallback` when the
centroid lacks interpolation support; and bounded optimizer diagnostics.
Position and flux covariance is retained only when the information matrix is
nonsingular with finite positive variances; shape errors are absent, and the
free fit's integrated-flux uncertainty is report-only for resolved or
marginal sources.

Every published candidate must be finite, away from its physical bounds and
well conditioned under the configured information limit, whether fitted free
or with a beam. Invalid moments and regions with fewer than seven owned
pixels return a typed unavailable fit; exhausted iterations and invalid
parameters return a typed failed fit that keeps the initializer. Unknown
values are never encoded as zero.

### Model selection

Under `beam-or-free`, a five-sigma log-area test selects clear extension
directly; otherwise the nested candidates are compared by BIC with the
number of independent samples appropriate to their residual model. A free
candidate that pins a bound or is ill conditioned yields to the beam model,
or the fit fails. Gaussian publication applies a second whole-model test: a
free component rejected at the five-sigma boundary is still published when
its log-area extension exceeds 1.5 standard errors, otherwise the complete
beam ellipse is published, so axes, angle, centroid and total always come
from one selected fit and a free axis is never mixed with a beam angle. The
selected and rejected models, bound distances, condition number and fallback
reason stay in the diagnostics.

A beam fallback chosen because the free ellipse failed admission is also
checked for residual adequacy on the joint model's likelihood pixels.
Residual features are admitted as detection admits them, positive and grown
to the island threshold from a detection-threshold seed on the original
pixels, the residual à trous scales or a matched-filter scale, and attributed
to the nearest component. Unexplained emission makes that Gaussian
`fit-model-inadequate` rather than an unresolved measurement; its identity,
support and source aperture remain, and valid neighbours keep their
parameters from the same joint solution. The plan's task 42 concerns the
case where one degenerate component sends every component of a joint fit to
this fallback.

No fit publishes an aperture flux of its own: every fit is a joint fit, and
an aperture around one component would sum its neighbours' light, so the
fit's aperture is discarded. A component publishes the infinite-plane fitted
total whether or not it is resolved, a source's integrated flux is the sum of
its components', and a source with no admitted fit takes its own aperture
(see the [output reference](public-products.md)). Extension is classified
again at the catalogue boundary with the ATLAS log integrated-to-peak
statistic ([compact astrometry](compact-astrometry.md)).

## Uncertainty calibration

On the M1 calibration population
(`config/datasets/m1-flux-calibration.json`: isolated sources in five
independent realizations of each noise class) the sandwich covariance's pulls
against injected truth on beam-correlated noise have a standard deviation
near one for position, peak flux and fitted axes (0.96 to 1.02) and 1.08 for
integrated flux. On pixel-independent noise they are conservative (0.32 to
0.57), because they assume beam-correlated noise, as Condon-style errors do.
A shape pull covers only the minority whose free model survived the extension
test, which selects upward fluctuations, so read it against the share of the
population it covers and report the published values' excess against truth
over every matched component.

Published sizes carry the expected low-SNR noise bias of fitted second
moments, and integrated flux follows it. Median excess against truth:

| Injected size | SNR 10 | SNR 20 | SNR 50 |
| --- | --- | --- | --- |
| Beam | axis 0.0%, flux +6.8% | axis 0.0%, flux +4.9% | axis 0.0%, flux +0.5% |
| 1.15 beam | axis +9.7%, flux +9.5% | axis +0.6%, flux −1.7% | axis +0.4%, flux −0.5% |
| 1.3 beam | axis +6.7%, flux +6.0% | axis +2.9%, flux +1.3% | axis +0.4%, flux 0.0% |
| 1.5 beam | axis +9.0%, flux +14.9% | axis +3.1%, flux +5.5% | axis +1.3%, flux +0.9% |

Beam-sized sources are published at the beam, their truth, so their axis
excess is zero by construction; sources 15% larger than the beam are
beam-constrained only at SNR 10, and then for 10% of them. The
integrated-flux tail is the wider concern: the 95th percentile of absolute
excess is 29 to 58% at SNR 10, 11 to 14% at SNR 20 and 5 to 6% at SNR 50. The
plan's `Total_flux` gates bound these against pinned PyBDSF `master`. The
reviewed external component profile applies an explicit 0.075-sigma
downward correction to the fitted total before publication, flagged
`fitted-integrated-flux-bias-corrected`, leaving amplitude, axes, angle,
centroid and covariance unchanged; the pipeline-neutral default is zero.
PyBDSF documents Condon (1997) errors; Hebog does not claim the same
implementation. See
[Condon (1997)](https://adsabs.harvard.edu/pdf/1997PASP..109..166C) and the
[PyBDSF processing reference](https://pybdsf.readthedocs.io/en/latest/process_image.html).

## Determinism and scope

The fit result is a frozen scheduler-safe record in the canonical region
order deblending gives, and serial and Dask executors produce equal records.
Which components form one source is decided afterwards by source
association, not by the fit; see
[How Hebog finds sources](../explanation/how-hebog-works.md).
