# Compact deblending

Deblending produces deterministic regions that initialize later measurement.
A region is not yet a measured source, a fitted Gaussian, or a catalogue row.
Those distinctions prevent segmentation choices from silently creating
photometry that belongs to measurement.

## Observable rules

Compact deblending uses one explicit `CompactDeblendConfig`:

- marker pixels are local maxima strictly above
  `minimum_peak_signal_to_noise`;
- the square maximum-filter radius is
  `minimum_peak_separation_pixels`;
- eight-connected equal-valued marker plateaus collapse to their
  lexicographically first global `(y, x)` pixel;
- a weaker basin remains separate when its peak minus the saddle it shares
  with a brighter one is at least `minimum_saddle_depth_sigma`; an exactly
  equal boundary therefore survives. Where that saddle is measured depends on
  the partition, described below;
- after prominence merging, a basin smaller than
  `minimum_region_pixels` joins its neighbour across the highest shared
  saddle. The compact configuration sets this to the seven owned pixels required by the
  seven-parameter Gaussian, so deblending cannot manufacture a child that is
  structurally impossible to fit; and
- final region identifiers and labels follow the first global member pixel,
  not SciPy marker labels, worker order, or partition shape.

Membership outside the accepted parent island is always label zero. All
accepted island pixels belong to exactly one region. Invalid or non-finite
member pixels fail closed, as does an accepted island with no eligible marker.
Masked pixels are maximum-cost watershed barriers rather than competing
markers, so holes cannot flood or leave accepted pixels unassigned.

## Partitions

The implementation combines maintained NumPy and SciPy primitives rather than
adding a new dependency. `maximum_filter` and `label` choose deterministic
markers. Two partitions then divide an island between them, and a sparse
union-find joins basins in descending order of the highest saddle each pair
shares, so two groups are judged where they first meet.

The public component topology floods the island's own intensity
(`intensity-watershed`). Every member pixel steps to its highest
eight-connected member neighbour while that neighbour is higher, ties going
to the first pixel in row-major order as they do between marker plateau
pixels; a marker never steps. Pointer jumping resolves all of these paths in
a few whole-array passes. Values only rise along a path, so every pixel
joins its basin's maximum at or above its own value, and the true pass
between two maxima, the highest level at which one eight-connected part of
the island holds both, is the level at which the descending union-find first
joins their basins, directly or through others. A basin without a marker
joins the first neighbour it meets, and each region keeps the pixels that
rise to its own peak. The public profile sets `minimum_saddle_depth_sigma`
to 1.5.

The compact measurement path keeps its reviewed marker-distance watershed
with a 1σ depth, judging each pair on the boundary of that distance
partition. On any partition the union-find joins two peaks at or above
their true pass, so that rule keeps only peaks the true pass keeps too, and
can merge more. Applied there, the true pass raised the Phase 4 blend
95th-percentile flux error to 0.165 against its 0.15 gate, so the qualified
compact photometry path keeps its policy, and the blend-equivalence matrix
guards it.

SciPy's `watershed_ift` was evaluated for intensity flooding first, but its
image-forest tie and marker propagation can assign nearly the complete bridge
to one marker, placing the measured boundary above the physical saddle; on
ordinary two-dimensional blends it could leave only a few pixels in the
second basin. The public path then assigned pixels to the nearest marker and
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

`plan_compact_deblend_batches` considers both accepted island pixels and the
rectangular bounds that must be read. It groups multiple compact islands into
coarse tasks near `target_batch_pixels`, while `maximum_batch_pixels` remains
the hard memory ceiling. One admitted island may exceed the preferred target
but never the per-island or hard batch limit. Separating occupancy from
admission lets dense fields use several workers without lowering the largest
compact island Hebog can process or creating one scheduler task per island.
An island above the member-pixel or bounds-area limit is returned as a
`DeferredDeblendIsland` with an explicit reason. It remains deterministic
input to the partitioned multiscale path and is never dropped or
reported as successfully deblended.

That handoff is completed by `run_deferred_island_completion_stage`. A caller supplies a zero-halo
partition manifest and a `DeferredIslandCompletionConfig` hard pixel limit.
The completion grid may differ from the detection/storage grid, but it must
cover the same logical image. Each task reads and relabels exactly one
published source-filtering-mask core. Only local component summaries and
boundary labels return for reconciliation; no island-sized membership or
label plane crosses the executor boundary.

The reconciled global identity must reproduce the deferred parent's pixel
count, bounds, first pixel, edge state, and canonical label. Its output is a
tuple of array-free `DeferredIslandShard` records. A later measurement task
can call `extract_deferred_island_shard_membership` with one shard and one
bounded mask tile to recover exact immutable membership. The extractor checks
the stored count, bounds, and first pixel before returning. The following
[extended-emission measurement](extended-emission-measurement.md) stage now
uses those shards for bounded original-pixel photometry. This completion stage
itself does not run a global watershed or claim a final associated source.

The compact kernel's memory is bounded by one admitted batch. Its Python loops
iterate markers, sparse basin adjacencies, or island records—not image pixels.
All source windows in one batch share one validated FITS open. Zarr product
windows reuse an LRU of at most four checksum-validated chunks per product,
which avoids rereading a complete tile for every dense compact island without
turning the cache into an image-sized gather.
The source-filtering mask remains the parent connected-island membership;
deblending subdivides that topology without changing which pixels are
detected.

The public continuum composition applies the same bounded deblender, with
its intensity watershed, to each retained connected parent before Gaussian
measurement. Its direct and
expanded measurement unions must remain byte-for-byte equivalent as boolean
support. One connected support island can therefore contain multiple Gaussian
components while still forming one associated catalogue source. Parents above
the reviewed compact member or bounds limit remain one retained component and
are counted as `deferred_deblend_parent_count` in public diagnostics; they are
never dropped or silently presented as successfully deblended.

A retained public parent can also be admitted by multiscale support without
containing a direct-residual peak above the stricter deblending seed threshold.
That parent remains one component with its direct and measurement support
unchanged. This conservative public fallback does not alter the compact
kernel's fail-closed no-marker contract and cannot manufacture a
split without an eligible peak.

A boolean source-filtering-mask window may contain another disconnected
island whose bounds overlap or nest inside the requested island. The compact
stage therefore relabels that bounded window with eight-connectivity and
selects the component containing the reconciled island's canonical first
pixel. It verifies the selected pixel count before deblending. It never treats
the complete rectangular window as the island.

## Worker-local measurement handoff

`run_compact_region_stage` is the only measurement handoff from these
summaries. Inside each existing coarse executor task it reads the admitted
source image, background, RMS, validity, and source-filtering-mask windows,
reconstructs exact parent membership, and runs the existing compact
watershed. A processor then receives one immutable `WorkerLocalRegionBatch`
containing the physical background-subtracted residual, RMS, scientific
validity, and exact int32 region labels. The processor must reduce those
arrays to compact typed records before the task returns.

`DeblendedRegion.bounds` is only a read/planning summary. Region rectangles
can overlap and can contain pixels owned by another watershed region; they are
not membership masks. `CompactDeblendStageResult` intentionally has no
per-pixel membership and is useful for topology inspection only. A measurement
implementation must use the worker-local processor seam rather than inventing
ownership from a summary.

The retained processor arrays account for 21 bytes per admitted bounds pixel:
float64 physical residual, float64 RMS, boolean validity, and int32 region
label. `maximum_processor_array_bytes` records the largest actual retained
batch. Input image/validity and the three Zarr windows are likewise bounded by
`maximum_batch_pixels`; normalized residual and watershed work are bounded by
one `maximum_compact_bounds_pixels` island at a time. The stage neither creates
one scheduler task per region nor returns a NumPy plane to the scheduler.

The first production processor on this seam is the
[compact moment oracle](compact-measurement.md). It reduces the physical plane
and exact labels to typed photometry and fit-initializer records inside the
same bounded task.
