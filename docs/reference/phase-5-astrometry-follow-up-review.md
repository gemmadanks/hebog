# Phase 5 extended-position follow-up review

**Status:** technical review complete; prospective development changes are
authorized by the project owner's request to perform the review and implement
its recommendations. This is not independent human scientific approval.
Fresh development evidence, a named scientific review, the sealed one-look
confirmation, external-finder comparison, and qualification remain required
before production selection.

This review follows the Step 2C-H development rejection. It diagnoses only
the already viewed development evidence and implementation. It does not open
the closed Step 2C-A confirmation, the sealed Step 2C-H confirmation, or the
Phase 5 qualification population.

## Decision

Hebog should stop treating one threshold-independent flux centroid as if it
were the same scientific quantity for compact Gaussian components and
irregular extended sources.

- Compact and approximately Gaussian components retain the Phase 4 fitted
  centre and its existing 0.10-beam median and 0.25-beam p95 astrometry gates.
- An irregular extended source reports a **detected-segment flux centroid**:
  the original background-subtracted pixel values inside its accepted source
  segment determine the coordinate. The brightest original pixel is reported
  separately.
- Validation compares that coordinate with the noiseless injected signal
  inside the matching 3-sigma truth segment. Flux below the catalogue boundary
  does not define the binding catalogue coordinate.
- Neither the segment centroid nor the peak is described as the host-galaxy
  position. Component/host association is a separate scientific product.
- Position uncertainty for an irregular segment remains explicitly
  unavailable until support-selection and association uncertainty have a
  validated per-source approximation. The rejected globally inflated analytic
  covariance must not be published as a calibrated catalogue error.

The implementation remains prospective. Fresh development data must pass
every governed stratum, followed by named human scientific review, before the
one-look confirmation can be authorized.

## Why the earlier candidates failed

The direct Step 2C-H candidate had an overall median/p95 radial error of
0.0974/0.2730 beam. The Gaussian-assisted candidate improved the median to
0.0860 beam but worsened the p95 to 0.3068 beam. Failures concentrated in
curved filaments, shells, scale-2/4 sources, image/tile boundaries, and
truncated support. Mean signed offsets were close to zero, so a common
coordinate correction would not address the failures.

Further diagnosis on the already viewed development data found:

- conservative interpolation between the direct and Gaussian positions did
  not pass the 0.25-beam p95 gate;
- a robust estimator that helped shells was unstable for curved filaments;
- a truth-informed 3-sigma support, unavailable to a real finder, produced an
  overall median/p95 of 0.1060/0.2399 beam against the full-emission centroid,
  but curved filaments still produced 0.1888/0.4062 beam; and
- integrating progressively fainter truth emission increased noise leverage
  and did not create a more stable observable coordinate.

The result is not evidence that position is unimportant. It shows that the
previous gate combined two different questions: the astrometric accuracy of a
compact fitted component, and the noise-dependent location descriptor of an
irregular detected region. A shell or bent filament does not have a unique
Gaussian-like centre whose error is governed only by restoring-beam width and
signal-to-noise ratio.

## Community-practice review

[PyBDSF's documented algorithm](https://pybdsf.readthedocs.io/en/stable/algorithms.html)
fits Gaussians to islands, groups the fitted components into sources, and
derives a source centroid by moment analysis. Inspection of the adjacent
reference checkout confirms that a multi-component source moment is taken on
the fitted source reconstruction within its source mask; a single-component
source uses the fitted Gaussian centre. PyBDSF also reports a maximum position.
Its Condon-based errors describe fitted Gaussian parameters, with an optional
Monte Carlo component-error path for multi-component sources. Hebog may compare
with a PyBDSF source centroid only when grouping and reconstructed-source
semantics align; PyBDSF is not evidence that every faint injected tail must
control the catalogue coordinate.

[Selavy's source-finding documentation](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current/analysis/selavy.html)
separates island and fitted-component products. Island measurements include an
average pixel coordinate, a flux-weighted centroid, and a peak, while fitted
Gaussian components have their own positions. This is the clearest direct
precedent for Hebog's typed split.

[ProFound](https://academic.oup.com/mnras/article/487/3/3971/5511783)
uses morphology-following segments rather than assuming that complex radio
sources are Gaussian. Its radio evaluation treats the flux-weighted segment
centre as a source descriptor. This supports an original-pixel segment moment
for irregular emission, while leaving compact Gaussian fitting intact.

[Aegean](https://academic.oup.com/mnras/article/422/2/1812/1041871)
uses curvature-defined summits and simultaneous Gaussian fitting. Its fitted
centre is an appropriate compact/component comparator, but it does not define
a binding irregular-island centroid equivalent to Hebog's segment moment.

[Condon (1997)](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)
derives error propagation for Gaussian fits in correlated radio noise. That
theory remains appropriate for Hebog's compact Gaussian parameters; applying
one global scale factor to a nonlinear, noise-selected irregular segment is
not the same statistical model.

The
[ASKAP/EMU source-finding challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19)
did not publish its simple positional-accuracy comparison for the extended
challenge because genuine source structure can contribute to offsets. It used
a much wider association radius for extended sources. The later
[Hydra comparison framework](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/hydra-i-an-extensible-multisourcefinder-comparison-and-cataloguing-tool/08C33C6281B8566BBE9CF00045701F57)
therefore compares multiple source finders and retains finder-specific
component/grouping semantics instead of treating one finder as truth.

Together these sources support a small, explainable product vocabulary:
Gaussian component centre, detected-segment centroid, and peak. They do not
support an opaque morphology-specific estimator chosen only to pass the viewed
fixtures.

## Prospective validation contract

The fresh Step 2C-HR study has one morphology-neutral candidate. It uses the
accepted residual-B3 association labels, original background-subtracted
pixels, and no centroid-only dilation. Pixel membership is therefore the same
scientific boundary used by the source catalogue. The peak uses deterministic
row-major tie-breaking.

Every governed stratum must satisfy all of the following on fresh development
data:

- 100% estimator availability;
- a one-sided 95% confidence bound of at most 0.10 beam for the absolute mean
  offset on each pixel axis; and
- a one-sided 95% confidence bound of at most 0.50 beam for the radial p95
  repeatability error.

Whole images remain the independent bootstrap unit. Radial median error and
offset from the former full-observable-domain centroid are diagnostic. The
half-beam p95 requirement is a resolution-based repeatability gate for an
irregular segment; it neither changes nor substitutes for the compact
0.10/0.25-beam astrometry gates.

The development and confirmation manifests must use new seeds and new
geometries for every governed morphology. Development may select only the
frozen candidate as-is. Any parameter or endpoint change requires another
pre-results contract and fresh evidence. Passing development does not itself
authorize confirmation, Step 2C-P, Step 3, optimization, or qualification.

## External comparison consequence

Step 2C-P should compare like products:

- PyBDSF source moments where source grouping and model support align;
- PyBDSF and Aegean fitted centres for compact/Gaussian components;
- Hebog segment centroids as a transparent source descriptor, with Selavy and
  ProFound providing semantic precedents rather than ground truth; and
- injected/analytic truth as the primary scientific authority.

Finder disagreement must be attributed to detection, grouping, component
fitting, or position definition before it is labelled an astrometric failure.
