# Phase 5 compact/extended association pre-review

**Status:** technical scientific pre-review complete; named approval is
required before changing the machine-readable contract or implementing the
Step 4 catalogue path.

This review defines the proposed overlap, ownership, split/merge, and
duplicate-suppression rules for Phase 5 Step 4. It does not implement a
combined catalogue, open qualification data, or change the passing Phase 4
compact products.

## Recommendation

Use a **shared-island, separate-source** model:

- reconcile overlapping detections across adjacent multiscale levels into one
  extended association;
- use spatial contact with compact support to form a combined island, not to
  claim that compact and extended emission are one astrophysical source;
- retain every accepted Phase 4 compact source and Gaussian component as a
  distinct catalogue object;
- add at most one extended source for each reconciled multiscale association;
  and
- suppress a multiscale echo of compact emission only when no independently
  measurable extended residual remains after the already reviewed compact
  exclusion and ownership barriers.

This is deliberately more conservative than inferring radio-galaxy host
relationships from one Stokes-I image. Physical grouping of lobes, cores, and
unrelated projected sources needs morphology, spectral, or multi-wavelength
evidence outside the present contract.

## Relation to established source finders

[PyBDSF](https://pybdsf.readthedocs.io/en/latest/process_image.html) detects
islands, fits one or more Gaussians, and groups those Gaussians into sources.
Its à trous path works on the Gaussian residual; a wavelet island that overlaps
an existing island is merged with it, while wavelet Gaussian provenance can
remain in the catalogue. This supports overlap-based island reconciliation
without collapsing all components into one row.

[Aegean](https://doi.org/10.1017/pasa.2018.3) estimates compact components from
island summits and jointly fits components whose model footprints overlap. It
is strong precedent for retaining multiple compact components within one
island, but it is not an irregular-emission association oracle.

[CAESAR](https://doi.org/10.1017/pasa.2019.39) searches a compact-clean residual
for extended emission, retains nested compact detections, and reconciles
adjacent or overlapping compact and extended sources. That architecture is
the closest published analogue to Hebog's accepted-compact exclusion followed
by residual B3 detection.

[ProFound's radio evaluation](https://doi.org/10.1093/mnras/stz1462) shows the
value of morphology-independent segments and converged segment photometry for
complex radio sources. It supports retaining segmentation as a first-class
product rather than replacing irregular emission with a forced Gaussian.

These systems establish a community-practice envelope, not a vote or a truth
oracle. Hebog retains its injected-truth gates and direct comparisons with both
PyBDSF references and Aegean.

## Proposed deterministic rules

### 1. Inputs and scientific roles

- Accepted Phase 4 compact sources, Gaussian components, exact compact
  supports, and fitted compact models are immutable inputs.
- Scale detections use their exact accepted pre-measurement supports and
  configured scale order. Aperture growth is never association evidence.
- Accepted compact emission must have been either subtracted or excluded
  before residual B3 detection. The two modes cannot be mixed in one image.
- Original background-subtracted pixels remain the measurement domain.
  Wavelet coefficients and selected scale records provide detection and
  association provenance only.

### 2. Cross-scale association

Construct an undirected graph whose nodes are accepted scale detections.
Create an edge only when:

1. the detections are on adjacent configured scales; and
2. their exact accepted supports share at least one valid pixel.

Do not associate detections using centroid distance, grown photometry
apertures, bounding-box contact, or a skipped scale. This follows PyBDSF's
spatial-overlap precedent while preventing dilation from joining unrelated
objects.

One connected graph component is one extended association. Therefore:

- multiple same-scale fragments merge only when an accepted adjacent-scale
  detection supplies a connected cross-scale path;
- fragments without such a path remain separate extended associations; and
- every contributing detection and scale is retained as provenance.

Select one representative detection for diagnostics by descending peak
signal-to-noise, descending normalized peak response, descending valid-support
fraction, ascending scale order, canonical pixel, and finally detection ID.
The representative never replaces the union support or determines flux, so
the last tie-breakers cannot alter science.

### 3. Compact/extended spatial context

Build a bipartite context graph between reconciled extended associations and
accepted compact sources. Add an edge when any of the following holds on the
pre-barrier extended support:

- the compact reference position lies inside it;
- exact compact and extended supports intersect; or
- their exact supports become adjacent under the already reviewed half-major-
  beam context dilation.

The first case is `contains-compact-support`; the latter two are
`overlaps-compact-support`. Neither term claims common physical origin. Replace
the provisional `contains-compact` and `mixed-projection` schema literals with
these explicit spatial names during implementation. `extended-only` requires
no compact edge and no compact source identity.

Many-to-many context edges are allowed. A connected component of compact and
extended nodes becomes one combined island, but each compact source and each
extended association remains a separate source row. Sharing a compact
neighbour may group extended associations into an island; it must not merge
their source identities.

### 4. Pixel and flux ownership

- Compact pixels and accepted compact model flux remain owned by the Phase 4
  compact objects.
- Extended measurement continues to treat compact supports as barriers.
- Overlapping extended apertures retain the Step 3 nearest-exact-support
  ownership rule with deterministic global-pixel ties.
- Every valid pixel contributes to at most one extended flux measurement.
  Combined-island flux summaries may sum distinct child measurements, but no
  new source row may count the same pixel or compact model twice.

### 5. Duplicate suppression

- Publish no more than one extended source for one cross-scale association,
  irrespective of the number of contributing scales or detections.
- Tile copies and retry copies reconcile by their existing global support
  identities before association; they are not catalogue objects.
- Never suppress distinct Phase 4 compact sources because their ellipses,
  supports, or centres overlap.
- Never suppress distinct extended associations by centroid proximity alone.
- If compact exclusion and barriers leave no one-beam accepted extended
  support or no positive finite extended measurement, do not publish an
  extended row. If a valid compact object accounts for the detection, retain
  the compact result and record compact-echo suppression. Otherwise emit a
  typed omission and block publication rather than relabeling the detection as
  an artifact.

### 6. Split, merge, and ambiguity semantics

- A cross-scale connected component is a scientific merge of scale fragments,
  not a catalogue duplicate.
- Separate same-scale detections are a split only if injected truth later
  identifies them as one object; production code must not use truth or a
  catalogue matcher to merge them.
- One association covering multiple truth groups is a qualification merge,
  not a reason to rewrite the production output after inspection.
- Multiple compact context edges are valid spatial evidence, not ambiguity.
- Missing source identities, non-adjacent scale membership, conflicting exact
  support ownership, or one scale detection claimed by two associations are
  typed association failures. Stable IDs may order scientifically equivalent
  records but may not resolve contradictory science.

### 7. Terminal dispositions

Every accepted compact island, compact-deferred island, and residual
multiscale association must reach exactly one terminal state:

| Outcome | Required disposition |
| --- | --- |
| Compact-only or compact echo with no independent residual | `retained-compact` with every retained source ID |
| Measured extended association, with or without compact context | `accepted-multiscale` with the association ID and retained compact source IDs where applicable |
| Deterministically rejected pre-publication artifact | `rejected-artifact` with a governed reason |
| Missing, contradictory, ambiguous, or unavailable required evidence | `failed` plus a typed omission |

Any missing or duplicate disposition, unresolved association, unavailable
required measurement, or unknown identity makes the combined state
publication-ineligible.

## Required implementation tests

Implementation should begin with analytic failing tests for:

- one object repeated over all three scales;
- two same-scale fragments joined, and not joined, by a coarser detection;
- non-adjacent and bounding-box-only contacts;
- one extended association containing several compact sources;
- one compact source adjacent to several distinct extended associations;
- partial overlap representing a possible projected compact source;
- a pure compact echo and a compact-plus-independent-diffuse residual;
- exact equal-score representative ties;
- unavailable measurement and contradictory ownership failures;
- edge, invalid-pixel, and tile-corner associations;
- shard, partition, task-order, retry, Serial, and Dask invariance; and
- exact compact-only catalogue, mask, RMS, diagnostics, and Rapthor FITS
  preservation.

Development and regression must then retain every existing Phase 4 compact
gate plus the Phase 5 completeness, reliability, duplicate, split, merge,
mask, flux, position, and Rapthor-decision gates. No threshold may be tuned on
the unopened qualification population.

## Approval boundary

Approval of this pre-review would authorize updating the machine-readable
Phase 5 association contract and starting test-first Step 4 implementation.
It would not authorize qualification, a PyBDSF-equivalence claim, Rapthor
cutover, or removal of the fallback. Independent radio-astronomy review
remains required before a stable production default.
