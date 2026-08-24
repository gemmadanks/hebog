# Extended-emission measurement

Phase 5 measures accepted irregular emission without fitting a Gaussian model
to its morphology. Detection support determines ownership; physical values
come from the original image, prepared background, and prepared RMS planes.
The measurement record is a pre-association product. Step 4 still decides
cross-scale and compact/extended relationships before catalogue publication.

## Measurement policy

For each accepted support, Hebog uses these governed rules:

- integrated flux is the sum of original background-subtracted pixels in a
  1.5-major-beam aperture, converted from Jy/beam pixels to Jy;
- overlapping apertures use nearest-support ownership, and other accepted
  compact supports act as barriers, so flux is never double-counted;
- peak brightness and the moment shape use the exact accepted support on the
  original background-subtracted image;
- diffuse multiscale positions use the reviewed direct-residual plus B3
  reconstruction weights; the direct residual is retained when the support's
  peak-to-mean ratio exceeds 3 or the regularized signal is unavailable; and
- local background and RMS are reduced from the already prepared fields over
  the same observable aperture.

Compact-deferred islands do not yet have a multiscale reconstruction, so their
bounded stage records direct-original-residual position weighting. The pure
tile kernel also accepts a regularized position plane for multiscale targets,
preserving the recovery-campaign estimator rather than silently substituting
direct weighting.

## Uncertainty and truncation

When the aperture is observable, the integrated-flux uncertainty is the
correlated-beam approximation

\[
\sigma_F = \sqrt{\frac{\Omega_{pixel}}{\Omega_{beam}}
                  \sum_{p \in A} \sigma_p^2}.
\]

This accounts for the number of independent beam areas represented by the
aperture. It does not propagate support selection, background-model, or shape
model uncertainty. Position and shape uncertainties are therefore explicitly
reported as unavailable rather than represented by a fabricated zero.

Records distinguish image-edge, invalid-pixel, and combined truncation and
include the observable fraction of the in-image nearest-owned aperture. The
edge status records aperture support that would extend outside the image;
the fraction quantifies invalidity only within the owned in-image portion.
Non-finite exact support,
non-positive signed support flux, and non-positive aperture flux produce a
typed unavailable result. An underdetermined or singular moment ellipse leaves
valid flux and position measurements intact but marks only shape unavailable.

## Bounded execution

`run_extended_emission_measurement_stage` consumes canonical
`PartitionedDeferredIsland` shards and a caller-supplied zero-halo core grid.
Each task reads one original-image core plus the smallest 1.5-beam halo needed
to reconstruct nearest ownership. Its hard `maximum_task_pixels` admission
limit applies to that complete read window, not only the output core.

Workers return scalar sufficient statistics; arrays, open files, and complete
islands never cross the executor boundary. Canonical scalar reduction makes
results invariant to retries and executor scheduling. Equivalent shifted and
rectangular completion grids are covered by integration tests. The stage reads
the Phase 4 accepted mask and prepared fields without modifying the detection
generation or compact catalogue products.

## Current boundary

This milestone establishes measurement semantics and bounded execution; it
does not itself alter association or publish a combined catalogue. Downstream
Step 4 kernels now reconcile adjacent-scale exact supports and record
many-to-many compact spatial context while preserving separate identities.
Stable combined identities and catalogue publication remain open.
