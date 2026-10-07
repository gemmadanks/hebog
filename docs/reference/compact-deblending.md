# Compact deblending

Deblending splits each retained detection into deterministic regions, one
per significant peak, that initialize Gaussian fitting. A region is not a
measured source, a fitted Gaussian or a catalogue row, so a segmentation
choice cannot silently create photometry.

## Observable rules

`CompactDeblendConfig` makes every rule explicit:

- marker pixels are local maxima strictly above
  `minimum_peak_signal_to_noise`, found with a square maximum filter of
  radius `minimum_peak_separation_pixels`;
- eight-connected equal-valued marker plateaus collapse to their
  lexicographically first global `(y, x)` pixel;
- a weaker basin stays separate when its peak minus the pass it shares with a
  brighter one is at least `minimum_saddle_depth_sigma` (1.5 in the reviewed
  profile); an exactly equal boundary survives;
- after prominence merging, a basin smaller than `minimum_region_pixels`
  (seven, the pixels a seven-parameter Gaussian needs) joins its neighbour
  across the highest shared saddle, so deblending cannot make a child that
  cannot be fitted; and
- region identifiers and labels follow the first global member pixel, never
  SciPy marker labels, worker order or partition shape.

Pixels outside the accepted parent island are label zero, and every accepted
pixel belongs to exactly one region. Invalid member pixels fail closed, as
does an island with no eligible marker. Masked pixels are maximum-cost
barriers, not competing markers, so holes cannot flood or leave pixels
unassigned.

## Partition

The kernel combines NumPy and SciPy primitives, with no new dependency.
`maximum_filter` and `label` choose markers; a steepest-ascent flood divides
the island between them, and a sparse union-find joins basins in descending
order of the highest saddle each pair shares, so two groups are judged where
they first meet.

The flood follows the island's own intensity: every member pixel steps to its
highest eight-connected member neighbour while that neighbour is higher, ties
going to the first pixel in row-major order, and a marker never steps.
Pointer jumping resolves the paths in a few whole-array passes. Because
values only rise along a path, the true pass between two maxima is the level
at which the descending union-find first joins their basins, and it matches
an independent level-set computation exactly. SciPy's `watershed_ift` was
rejected because its tie and marker propagation can assign nearly a whole
bridge to one marker, and a nearest-marker partition measured saddles on the
line equidistant from two peaks, which beside a bright broad source crosses
its wing far above the pass: a 39σ compact source 21 pixels from a 188σ
resolved one got no component of its own. The 1.5σ depth was set because at
1σ noise bumps on smooth extended emission in beam-correlated noise split a
smooth source about twice as often, while every compact source the exact
pass recovers still separates, its pass 4 to 30σ below its peak.

The minimum-area merge preserves every parent pixel and changes only the
ownership boundary between adjacent basins; it never drops a weak child or
presents a failed fit as a source. Flooding the ascent basins gives the
island's superlevel-set merge tree exactly, without the level selection and
cross-level identity logic of a multilevel implementation and without
scikit-image.

## Bounded execution and deferral

`find_sources` deblends in the component-topology stage
(`run_component_topology_stage` in `hebog.stages.objects`). Each retained
parent is deblended with its direct and expanded measurement support, and
the stage publishes the component labels as an intermediate plane. Parents
are grouped so that one bounded read serves several, but a parent is never
split across tasks.

A parent above `maximum_compact_island_pixels` or
`maximum_compact_bounds_pixels` stays one retained component and is counted
as `deferred_deblend_parent_count` in the public diagnostics. Deciding that
needs only its bounds and size, so no task reads a deferred parent's window,
and every deblending read is bounded by the reviewed compact bounds rather
than the image. A parent admitted by multiscale support without a direct
peak above the deblending seed threshold likewise stays one component. The
kernel's Python loops iterate markers, basin adjacencies or island records,
never pixels, and the source-filtering mask remains the parent island
membership that deblending subdivides.

## Measurement handoff

`DeblendedRegion.bounds` is a read and planning summary only: rectangles can
overlap and contain another region's pixels. Measurement reads the published
component labels, never a rectangle. The component-fit stage reads each fit
parent's labels with its residual and RMS and reduces them to the records in
[compact moment measurement](compact-measurement.md) and
[compact Gaussian fitting](compact-fitting.md).
