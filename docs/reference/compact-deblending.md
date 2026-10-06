# Compact deblending

Deblending splits each retained detection into deterministic regions, one
per significant peak, that initialize Gaussian fitting. A region is not yet a
measured source, a fitted Gaussian, or a catalogue row. Those distinctions
prevent segmentation choices from silently creating photometry that belongs
to measurement.

## Observable rules

Deblending uses one explicit `CompactDeblendConfig`:

- marker pixels are local maxima strictly above
  `minimum_peak_signal_to_noise`;
- the square maximum-filter radius is
  `minimum_peak_separation_pixels`;
- eight-connected equal-valued marker plateaus collapse to their
  lexicographically first global `(y, x)` pixel;
- a weaker basin remains separate when its peak minus the pass it shares
  with a brighter one is at least `minimum_saddle_depth_sigma`; an exactly
  equal boundary therefore survives. The reviewed profile sets this depth
  to 1.5;
- after prominence merging, a basin smaller than
  `minimum_region_pixels` joins its neighbour across the highest shared
  saddle. The reviewed configuration sets this to the seven owned pixels
  required by the seven-parameter Gaussian, so deblending cannot
  manufacture a child that is structurally impossible to fit; and
- final region identifiers and labels follow the first global member pixel,
  not SciPy marker labels, worker order, or partition shape.

Membership outside the accepted parent island is always label zero. All
accepted island pixels belong to exactly one region. Invalid or non-finite
member pixels fail closed, as does an accepted island with no eligible marker.
Masked pixels are maximum-cost watershed barriers rather than competing
markers, so holes cannot flood or leave accepted pixels unassigned.

## Partition

The implementation combines maintained NumPy and SciPy primitives rather than
adding a new dependency. `maximum_filter` and `label` choose deterministic
markers. The watershed then divides the island between them, and a sparse
union-find joins basins in descending order of the highest saddle each pair
shares, so two groups are judged where they first meet.

The watershed floods the island's own intensity. Every member pixel steps to
its highest eight-connected member neighbour while that neighbour is higher,
ties going to the first pixel in row-major order as they do between marker
plateau pixels; a marker never steps. Pointer jumping resolves all of these
paths in a few whole-array passes. Values only rise along a path, so every
pixel joins its basin's maximum at or above its own value, and the true pass
between two maxima, the highest level at which one eight-connected part of
the island holds both, is the level at which the descending union-find first
joins their basins, directly or through others. A basin without a marker
joins the first neighbour it meets, and each region keeps the pixels that
rise to its own peak.

SciPy's `watershed_ift` was evaluated for intensity flooding first, but its
image-forest tie and marker propagation can assign nearly the complete bridge
to one marker, placing the measured boundary above the physical saddle; on
ordinary two-dimensional blends it could leave only a few pixels in the
second basin. An earlier partition assigned pixels to the nearest marker and
measured intensity saddles on that partition's boundary, which lies on the
line equidistant from two peaks. Beside a bright broad source that line
crosses its wing far above the pass: a 39σ compact source 21 pixels from a
188σ resolved one met 73σ there against a 15σ pass, and got no component of
its own. Steepest-ascent flooding needs no `watershed_ift`, and its pass
matches an independent level-set computation exactly.

At the true pass a 1σ depth let noise bumps on smooth extended emission
become components about twice as often as the boundary saddle had: a smooth
Gaussian source at 8 to 30σ with a σ of 10 to 20 pixels, in beam-correlated
noise, split into a median of one to four regions instead of one or two. At
1.5σ it splits about as often as before, and every compact source the exact
pass recovered still separates, its pass lying 4 to 30σ below its peak.
Noise that is not correlated over a beam, which radio images do not have,
still splits such a source more often.

The minimum-area merge is deterministic and conservative: it preserves every
parent-island pixel and changes only the ownership boundary between adjacent
basins. It does not silently drop a weak child or treat a failed fit as a
successful source.

Flooding the ascent basins gives the island's superlevel-set merge tree
exactly, without the level selection, repeated connected labelling and
cross-level identity logic a repeated multilevel implementation needs.
Scikit-image was not added: SciPy and NumPy supply the required morphology,
distance, watershed, and reduction operations, so another runtime and
worker-image dependency provides no demonstrated benefit. This choice
introduces no new durable dependency and does not require an ADR.

## Bounded execution and deferral

`find_sources` deblends in the component-topology stage
(`run_component_topology_stage` in `hebog.stages.objects`). Each retained
connected parent is deblended with its direct and expanded measurement
support, and the stage publishes the component labels as an intermediate
plane. Parents are grouped so one bounded read serves several; a parent is
never split across tasks, because deblending needs its whole support at once.

A parent above `maximum_compact_island_pixels` or
`maximum_compact_bounds_pixels` stays one retained component and is counted
as `deferred_deblend_parent_count` in public diagnostics. Deciding that needs
only the parent's bounds and size, so no task reads a deferred parent's
window. It is never dropped or silently presented as successfully deblended.
Admission therefore bounds every deblending read by the reviewed compact
bounds, not by the image.

A retained parent can also be admitted by multiscale support without
containing a direct-residual peak above the stricter deblending seed
threshold. That parent remains one component with its direct and
measurement support unchanged. This conservative fallback does not alter the
kernel's fail-closed no-marker contract and cannot manufacture a split
without an eligible peak.

The kernel's Python loops iterate markers, sparse basin adjacencies, or
island records, not image pixels. The source-filtering mask remains the
parent connected-island membership; deblending subdivides that topology
without changing which pixels are detected.

## Measurement handoff

`DeblendedRegion.bounds` is only a read and planning summary. Region
rectangles can overlap and can contain pixels owned by another watershed
region; they are not membership masks. Measurement therefore reads the
published component labels, never a summary rectangle: the component-fit
stage reads each fit parent's labels with its residual and RMS and reduces
them to the moment and fit records described in
[compact moment measurement](compact-measurement.md) and
[compact Gaussian fitting](compact-fitting.md).
