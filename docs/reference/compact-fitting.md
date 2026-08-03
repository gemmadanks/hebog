# Compact Gaussian fitting

Phase 4 fits one bounded elliptical Gaussian to every eligible compact
deblended region. The fit-all lane is the scientific reference: Hebog does not
skip apparently easy regions or substitute moment parameters for fitted
parameters.

## Numerical model

`run_compact_gaussian_fit_stage` keeps the physical residual, RMS, exact
watershed membership, moment calculation, and nonlinear fit inside the same
coarse executor task. A task may contain several islands and regions; Hebog
does not create one Dask task per source. Retained image arrays stay subject to
the Phase 3 coarse-batch pixel limit.

The seven fitted parameters are positive peak amplitude, global zero-based
`(x, y)` centroid, two positive pixel sigma axes, pixel-space orientation, and
a bounded local residual-background offset. The offset absorbs small local
background errors without changing exact watershed ownership. Fits retain an
eight-pixel context by default; pixels owned by another deblended region are
excluded. Residuals are divided by the local RMS plane. Moment parameters
initialize the fit, and explicit configuration bounds limit center movement,
axes, amplitude, background offset, iterations, and convergence tolerance.

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
- infinite-plane fitted-Gaussian integrated flux in Jy;
- bilinearly sampled local RMS at the fitted centroid; and
- bounded optimizer diagnostics.

Position and flux covariance is retained only when the information matrix is
nonsingular and produces finite positive variances. When the image geometry
declares a Gaussian pixel-noise correlation function, Hebog uses a generalized
OLS sandwich covariance and flags it `correlated-noise-sandwich-errors`;
otherwise it retains the independent-pixel estimate with
`formal-independent-pixel-errors`. Shape errors remain absent. The powered
regression calibration passes, but the first held-out campaign found residual
peak/integrated-flux bias in several strata, so Phase 4 does not yet claim
qualified uncertainty calibration.

Invalid moments and regions with fewer than seven owned pixels return a typed
unavailable fit. Exhausted iterations and scientifically invalid fitted
parameters return a typed failed fit that retains the moment initializer and
diagnostics. Unknown values are never encoded as zero. A normal catalogue may
only be built when every admitted compact region has a valid fit and there are
no Phase 5 deferrals.

## Determinism and scope

The fit result is a frozen scheduler-safe record. Canonical region order is
inherited from deblending, and serial and Dask executors produce equal compact
records. The current compact policy associates one fitted Gaussian and one
source with each successfully fitted deblended region. Multiscale emission and
selective fitting are deliberately outside this lane.
