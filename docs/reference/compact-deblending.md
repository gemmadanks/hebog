# Compact deblending

Phase 3 deblending produces deterministic regions that initialize later
measurement. A region is not yet a measured source, a fitted Gaussian, or a
catalogue row. Those distinctions prevent segmentation choices from silently
creating photometry that belongs to Phase 4.

## Observable rules

Compact deblending uses one explicit `CompactDeblendConfig`:

- marker pixels are local maxima strictly above
  `minimum_peak_signal_to_noise`;
- the square maximum-filter radius is
  `minimum_peak_separation_pixels`;
- eight-connected equal-valued marker plateaus collapse to their
  lexicographically first global `(y, x)` pixel;
- a weaker basin remains separate when its peak minus the shared saddle is at
  least `minimum_saddle_depth_sigma`; an exactly equal boundary therefore
  survives; and
- final region identifiers and labels follow the first global member pixel,
  not SciPy marker labels, worker order, or partition shape.

Membership outside the accepted parent island is always label zero. All
accepted island pixels belong to exactly one region. Invalid or non-finite
member pixels fail closed, as does an accepted island with no eligible marker.

## Selected SciPy approach

The implementation combines maintained SciPy primitives rather than adding a
new dependency. `maximum_filter` and `label` choose deterministic markers.
`distance_transform_edt` constructs a marker-distance ridge, and
`watershed_ift` partitions the bounded island with eight-neighbour
connectivity. Actual normalized intensities—not geometric distance—then
measure the highest discrete saddle between adjacent basins. A sparse
union-find merges basins whose weaker peak lacks the configured prominence.

An intensity-topography watershed was evaluated first, but its image-forest
tie/marker propagation can assign nearly the complete one-dimensional bridge
to one marker, placing the measured basin boundary above the physical saddle.
The marker-distance ridge gives stable compact ownership while the subsequent
intensity saddle retains the scientific split decision.

A repeated multilevel superlevel-set implementation would be closer to some
legacy source-finder descriptions, but it requires maintained level selection,
repeated connected labelling, and cross-level identity logic. It is not
simpler for the Phase 3 observable contract. Scikit-image was not added:
SciPy supplies the required morphology, distance, watershed, and reduction
operations, so another runtime and worker-image dependency provides no
demonstrated benefit. This choice introduces no new durable dependency and
does not require an ADR.

## Bounded execution and deferral

`plan_compact_deblend_batches` considers both accepted island pixels and the
rectangular bounds that must be read. It groups multiple compact islands into
coarse batches under `maximum_batch_pixels`; it does not create one scheduler
task per island. An island above the member-pixel or bounds-area limit is
returned as a `DeferredDeblendIsland` with an explicit reason. It remains
deterministic input to the Phase 5 partitioned/multiscale path and is never
dropped or reported as successfully deblended.

The compact kernel's memory is bounded by one admitted batch. Its Python loops
iterate markers, sparse basin adjacencies, or island records—not image pixels.
The source-filtering mask remains the parent connected-island membership;
deblending subdivides that topology without changing which pixels are
detected.
