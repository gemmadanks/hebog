# Phase 5 public-finder source-association implementation

**Status:** implemented and validated on analytic fixtures only. The exact
candidate identity freeze is pending. No replay, viewed-data execution,
campaign, qualification, tuning, rescoring, cutover, or release is authorized.

The implementation is governed by pre-review SHA-256
`9af42348896e0449e007fe2318648f66122313d600137f8f5ec525ebaec1cc3c`
and implementation decision SHA-256
`6a495cfcb54ec01e5a7290b6c28edf7b7fffe89f88318c5b6f3e135e70a15553`.
It did not inspect the terminal cumulative replay, viewed SDC1 or Hydra
products, or reference-finder catalogues.

## Component and source identities

`DetectionComponentRecord` represents an immutable accepted component. Its
persistent identity is a canonical hash of the component's global row-major
owner pixel; the task-local integer label remains diagnostic only. A
`CatalogueSourceMembership` is an exact, non-overlapping partition of those
component identities. The catalogue-source identifier hashes the sorted member
identities, so worker count, task order, retry, and label permutation cannot
change it.

These records represent image-domain catalogue sources. They do not assert
that separated lobes or other components belong to one physical
astrophysical object.

## Conservative association graph

Two components receive an edge only when all frozen requirements pass:

1. exact owner pixels plus undilated significant B3 support put them in the
   same eight-connected parent support;
2. every valid pixel on the straight centroid segment remains at or above the
   existing island threshold;
3. centroid separation is no greater than half the sum of the two directional
   component FWHMs along that segment; and
4. both exact-support component covariance estimates are available.

The reducer considers edges in canonical scientific order and merges groups
only when every cross-group pair has an accepted edge. This complete-link rule
prevents a plausible A--B and B--C chain from implying an unsupported A--C
association. Missing shapes, weak saddles, invalid gaps, disconnected support,
and ambiguous evidence all leave components separate.

Overlapping association-halo tasks retain global component coordinates. Their
edge evidence is array-free, order-independent, and idempotent under exact
retry duplication. The pure reducer therefore produces the same membership
for one tile, multiple halo windows, Serial execution, and the existing Dask
executor.

## Binding source catalogue

The existing component catalogue remains available as stable diagnostic rows.
The binding source catalogue aggregates only existing exclusive component
measurements:

\[
F_s = \sum_{c\in C_s}F_c,
\qquad
P_s = \max_{c\in C_s}P_c.
\]

Source position is the integrated-flux-weighted component centroid in a local
tangent plane. Source shape is the existing moment-equivalent estimator
applied to the union of exact member-owner support. Detection labels and
component pixels are never mutated or reassigned. Background, RMS, thresholds,
minimum area, support recovery, measurement apertures, calibration, astrometry,
and component shape estimation remain unchanged.

## Fixture validation

The analytic matrix covers singleton components, continuous split broad
sources, low-saddle neighbours, high-dynamic-range fragments, directional
filaments, disconnected double lobes, complete-link bridge chains, invalid
barriers, unavailable shapes, label permutation, and malformed evidence.
Catalogue fixtures verify component-pixel preservation, exact flux summation,
maximum peak flux, tangent-plane centroid composition, and union-support shape
provenance.

Executor fixtures verify one-tile versus overlapping many-tile results across
Serial and existing-Dask execution, including partition-origin changes,
completion-order reversal, and duplicate retry evidence. The new association
modules have 90.60% focused branch-aware coverage. A newly frozen exact
non-executable candidate and separate named approval are required before any
cumulative replay.
