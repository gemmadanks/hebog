# Compact astrometry and beam deconvolution

Phase 4 transforms a valid compact Gaussian fit from global pixel coordinates
to the internal ICRS catalogue model. The transformation is deliberately kept
separate from fitting: the nonlinear optimizer remains a pure pixel-space
operation, while this boundary owns WCS, angular geometry, and restoring-beam
semantics.

## Coordinate transformation

Hebog reconstructs an Astropy celestial WCS from the serializable image
metadata and uses zero-based continuous `(x, y)` pixel coordinates. A centred
finite difference at the fitted centroid produces a local two-by-two Jacobian
from pixel offsets to east/north tangent-plane offsets in degrees. That same
Jacobian transforms:

- the fitted centroid to ICRS right ascension and declination;
- the fitted pixel covariance to a celestial Gaussian ellipse;
- the centroid covariance to position errors; and
- the local pixel area used by fitted and island flux calculations.

Right ascension is canonical in `[0, 360)` degrees. Celestial position angle
is degrees east of north modulo 180 degrees. The local Jacobian, rather than a
single header pixel scale, preserves signed and unequal pixel scales, rotation,
projection effects, and right-ascension wraparound.

## Beam deconvolution

Fitted and restoring-beam ellipses are represented as two-by-two east/north
covariance matrices. Hebog subtracts the beam covariance from the fitted
covariance and classifies the eigenvalues:

- two positive intrinsic axes produce a resolved deconvolved ellipse;
- no significant positive intrinsic axis is unresolved; and
- a marginal one-axis result is conservatively unresolved and carries both
  `marginal-deconvolution` and `unresolved` quality flags.

For a noisy fit, positive geometric deconvolution is necessary but not
sufficient evidence of physical extension. Hebog uses the standardized
one-sided [ATLAS DR3](https://doi.org/10.1093/mnras/stv1866) statistic:
`ln(S_integrated / S_peak)` divided by the quadrature relative uncertainty of
the two fluxes. ATLAS used a two-sigma decision and explicitly reported a 2.3%
point-source false-extension probability. Phase 4 uses a conservative
five-sigma threshold because a false resolved shape is a material catalogue
error and the paired closure contract
requires Hebog to be no worse than released PyBDSF, not merely to pass the 95%
absolute specificity floor. A geometrically resolved fit that does not pass is
reported as unresolved with `extension-not-significant`. If the fit declares
its flux uncertainty unavailable, the extension classification is also
unavailable. Exact analytic fits without an uncertainty-unavailable flag
retain their geometric result so noiseless contract cases remain exact.

The classification threshold is explicit runtime configuration. The frozen
Phase 4 contract separately gates point-source specificity and recall for
clearly resolved truth. "Clearly resolved" is selected from injected truth
before fitting: fitted-to-beam area ratio at least 3 and signal-to-noise ratio
at least 25. Less decisive injected extension is a predeclared marginal,
report-only population rather than being retrospectively relabelled after a
fit. Its integrated-flux catastrophic rate is therefore also report-only;
position, peak flux, and fitted/deconvolved shape catastrophes remain gated,
as does integrated flux for point and clearly resolved truth.

An unresolved internal shape is null. The zero-major-axis value expected by
the PyBDSF/Rapthor compatibility view is introduced only by that adapter and
never re-enters a scientific calculation.

The established `radio_beam` package was evaluated for this boundary. Its
deconvolution utility implements the same small covariance problem but also
encodes package-specific failure and point-like conventions. Hebog needs the
explicit three-state policy above and already depends on NumPy, so adding a
runtime dependency would not reduce the maintained scientific logic. The
implementation therefore retains the direct, analytic covariance subtraction
and tests it against governed truth.

## Uncertainty status

The fitter's nonsingular covariance can be transformed into one-sigma position
and flux errors. A declared synthesized-beam correlation function produces
generalized OLS sandwich errors flagged
`correlated-noise-sandwich-errors`; an absent correlation model retains the
`formal-independent-pixel-errors` fallback. Shape uncertainties remain null
and carry `shape-uncertainty-unavailable`. If the fit covariance is
unavailable, position and flux errors are also null and carry
`position-flux-uncertainty-unavailable`; zero never means unknown.

For an unresolved source, the catalogue reports peak flux density as its best
integrated-flux estimate and uses the peak-flux uncertainty. This avoids the
well-known upward width/area noise bias in low-SNR free Gaussian fits. For a
resolved source, the infinite-plane fitted-Gaussian integral remains the
catalogue value, but its propagated uncertainty is report-only in Phase 4.

The independent paired-regression margin audit covers 1,600 predeclared point
sources and 200 predeclared clear extensions. Point-source values span
-2.08--3.38 sigma, while every clear extension spans 17.92--23.83 sigma. The
five-sigma decision therefore classified every point and clear source
correctly without choosing a boundary close to either population. This is
regression evidence, not final qualification; the paired protocol and final
population still require named review.
