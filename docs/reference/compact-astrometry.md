# Compact astrometry and beam deconvolution

The astrometry boundary transforms a valid compact Gaussian fit from global
pixel coordinates to the internal ICRS catalogue model. It is kept separate
from fitting: the optimizer is a pure pixel-space operation, and this
boundary owns WCS, angular geometry and restoring-beam semantics.

## Coordinate transformation

Hebog rebuilds an Astropy celestial WCS from the serializable image metadata
and uses zero-based continuous `(x, y)` pixel coordinates. A centred finite
difference at the fitted centroid gives a local two-by-two Jacobian from
pixel offsets to east/north tangent-plane offsets in degrees, which
transforms the centroid to ICRS right ascension and declination, the pixel
covariance to a celestial ellipse, the centroid covariance to position
errors, and the local pixel area used by fitted and island fluxes. Right
ascension is canonical in `[0, 360)` and position angle is degrees east of
north modulo 180. The local Jacobian, rather than one header pixel scale,
preserves signed and unequal scales, rotation, projection and wraparound.

## Beam deconvolution

Fitted and restoring-beam ellipses are two-by-two east/north covariance
matrices. Hebog subtracts the beam covariance and classifies the
eigenvalues: two significant positive intrinsic axes give a resolved
deconvolved ellipse, none gives unresolved, and one gives `major-axis-only`
with no minor axis or position angle.

Positive geometric deconvolution is necessary but not sufficient evidence of
extension. Hebog applies the one-sided
[ATLAS DR3](https://doi.org/10.1093/mnras/stv1866) statistic,
`ln(S_integrated / S_peak)` over the quadrature relative uncertainty of the
two fluxes, at a conservative five sigma rather than ATLAS's two, because a
false resolved shape is a material catalogue error and the equivalence
contract requires Hebog to be no worse than released PyBDSF. A geometrically
resolved fit that fails the test is unresolved with
`extension-not-significant`; a fit with no flux uncertainty has an
unavailable classification (`deconvolution-uncertainty-unavailable`); an
exact analytic fit keeps its geometric result, so noiseless contract cases
stay exact. For a free noisy fit, a finite-difference delta method
propagates the covariance of major sigma, minor sigma and angle through the
WCS and beam subtraction, and each deconvolved eigenvalue must exceed zero at
the same five-sigma level independently: a significant major with an
insignificant minor is `major-axis-only`, which keeps the `DC_Maj` that
Rapthor consumes whenever it is identifiable. A noisy fit with flux
uncertainty but no usable shape covariance has an unavailable deconvolution
rather than a falsely precise ellipse.

The threshold is explicit configuration. The equivalence contract gates
point-source specificity and recall for clearly resolved truth, selected from
injected truth before fitting as a fitted-to-beam area ratio of at least 3 at
SNR of at least 25; less decisive extension is a predeclared report-only
population. On the paired regression population of 1,600 point sources and
200 clear extensions, point-source statistics span −2.08 to 3.38 sigma and
every clear extension 17.92 to 23.83, so the five-sigma decision separates
them with a wide margin; this is regression evidence, not qualification.

An unresolved internal shape is null, and a major-axis-only result stores one
positive major FWHM; the zero `DC_Maj` of the PyBDSF/Rapthor view is produced
only for an explicitly unresolved source and never re-enters a calculation.
The `radio_beam` package was evaluated and not adopted: it solves the same
small covariance problem with its own failure conventions, and Hebog needs
the explicit three-state policy above.

## Uncertainty status

The selected fit's nonsingular centroid covariance gives one-sigma position
errors. Both are great-circle angles, because the Jacobian is east/north:
`E_RA` is not divided by cos(dec), matching PyBDSF and the fixed angle
Rapthor compares it with. Flux errors use the same covariance, flagged
`correlated-noise-sandwich-errors` with a declared beam correlation and
`formal-independent-pixel-errors` without one. Shape uncertainties are null
with `shape-uncertainty-unavailable`; when the fit covariance is unavailable,
position and flux errors are null with
`position-flux-uncertainty-unavailable`. Zero never means unknown. A
component's published integrated flux is its infinite-plane fitted integral,
resolved or not, so a source's summed flux follows PyBDSF's definition; the
propagated uncertainty of a resolved component's integral is report-only.
