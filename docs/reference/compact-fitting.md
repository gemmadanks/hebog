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

The six fitted parameters are positive peak amplitude, global zero-based
`(x, y)` centroid, two positive pixel sigma axes, and pixel-space orientation.
The model has no background term because it fits the already
background-subtracted physical plane. Residuals are divided by the local RMS
plane. Moment parameters initialize the fit, and explicit configuration bounds
limit center movement, axes, amplitude, iterations, and convergence tolerance.

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

Formal covariance from the weighted Jacobian is retained only when the
information matrix is nonsingular and produces finite positive variances.
These are independent-pixel errors and are explicitly flagged as formal; they
are not treated as calibrated correlated-noise uncertainties. Shape errors
remain absent pending the reviewed uncertainty-calibration gate.

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
