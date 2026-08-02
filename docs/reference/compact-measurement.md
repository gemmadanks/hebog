# Compact moment measurement

Phase 4 Step 3 adds a readable, deterministic moment oracle for every admitted
compact island and exact deblended region. It produces owned-pixel photometry
and a pixel-space Gaussian initializer. The subsequent
[compact Gaussian fitting](compact-fitting.md) lane consumes this initializer.
Moment records themselves are not fitted sources or catalogue rows.

## Inputs and ownership

`run_compact_moment_stage` uses the worker-local handoff described in
[Compact deblending](compact-deblending.md). Each coarse task receives bounded
float64 physical residual and RMS planes, boolean scientific validity, and
exact int32 watershed labels. A label-zero pixel is excluded even if it lies
inside a region's rectangular bounds. The normalized detection plane is not
used for flux or moments.

The processor emits the parent island first and then its deblended regions in
canonical label order. Only frozen dataclass records cross the executor
boundary; pixel arrays remain within the existing coarse task. Serial and
Dask executors must return equal records.

The kernel creates only one-dimensional selected-value and coordinate
workspaces for the target currently being reduced. Their population is no
larger than `maximum_compact_island_pixels`, while the retained aligned planes
remain bounded by `maximum_batch_pixels`. Python iteration is over compact
island/region records, never pixels or RMS windows.

## Photometry

For positive, finite owned brightnesses \(I_i\) in Jy/beam, Hebog reports:

- peak brightness and the first tied peak in canonical global pixel order;
- mean background-subtracted brightness;
- mean local RMS over the same owned pixels; and
- owned-pixel integrated flux
  \(\sum_i I_i\,\Omega_\mathrm{pixel}/\Omega_\mathrm{beam}\) in Jy.

`CompactMeasurementGeometry` requires both solid angles explicitly. The pixel
solid angle is the absolute local tangent-plane Jacobian determinant. The
elliptical restoring-beam solid angle is
\(\pi b_\mathrm{major}b_\mathrm{minor}/(4\ln 2)\), with FWHM axes in a
consistent angular unit. Missing, non-finite, or non-positive geometry is
rejected rather than inferred.

Owned-pixel integrated flux is deliberately named and modelled separately
from fitted-Gaussian integrated flux. The latter integrates the fitted model
over its infinite plane:
\(A\,2\pi\sigma_\mathrm{major}\sigma_\mathrm{minor}
\Omega_\mathrm{pixel}/\Omega_\mathrm{beam}\). Neither value is silently
copied into the other.

## Moment initializer

Centroids and covariance use positive physical brightness as the weight. The
initializer contains global zero-based pixel-centre coordinates in `(x, y)`
order, covariance entries in pixel squared, ordered major and minor Gaussian
sigma axes in pixels, and a major-axis angle counterclockwise from positive
pixel x modulo 180 degrees. A circular covariance receives the canonical
pixel angle zero because its orientation is not physically determined.

This angle is not a celestial position angle. Phase 4 Step 5 will transform
the covariance with Astropy's local tangent-plane Jacobian and report the
reviewed east-of-north convention.

## Explicit availability

The result union prevents invalid science values from masquerading as valid
zeroes:

- `ValidMomentMeasurement` contains photometry and a nonsingular initializer;
- `ShapeUnavailableMomentMeasurement` preserves valid photometry but omits
  shape for an underdetermined or singular region; and
- `UnavailableMomentMeasurement` contains neither flux nor shape when an
  owned measurement pixel is invalid/non-finite or non-positive.

`CompactMomentConfig` makes the minimum shape population and covariance
relative tolerance explicit. These are numerical availability rules, not
detection thresholds. Nonlinear fit convergence, fitted component semantics,
beam deconvolution, and calibrated uncertainty remain later Phase 4 steps.
