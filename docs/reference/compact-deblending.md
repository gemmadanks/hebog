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
  survives;
- after prominence merging, a basin smaller than
  `minimum_region_pixels` joins its neighbour across the highest shared
  saddle. Phase 4 sets this to the seven owned pixels required by the
  seven-parameter Gaussian, so deblending cannot manufacture a child that is
  structurally impossible to fit; and
- final region identifiers and labels follow the first global member pixel,
  not SciPy marker labels, worker order, or partition shape.

Membership outside the accepted parent island is always label zero. All
accepted island pixels belong to exactly one region. Invalid or non-finite
member pixels fail closed, as does an accepted island with no eligible marker.
Masked pixels are maximum-cost watershed barriers rather than competing
markers, so holes cannot flood or leave accepted pixels unassigned.

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

The minimum-area merge is deterministic and conservative: it preserves every
parent-island pixel and changes only the ownership boundary between adjacent
basins. It does not silently drop a weak child or treat a failed fit as a
successful source.

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
All source windows in one batch share one validated FITS open. Zarr product
windows reuse an LRU of at most four checksum-validated chunks per product,
which avoids rereading a complete tile for every dense compact island without
turning the cache into an image-sized gather.
The source-filtering mask remains the parent connected-island membership;
deblending subdivides that topology without changing which pixels are
detected.

A boolean source-filtering-mask window may contain another disconnected
island whose bounds overlap or nest inside the requested island. The compact
stage therefore relabels that bounded window with eight-connectivity and
selects the component containing the reconciled island's canonical first
pixel. It verifies the selected pixel count before deblending. It never treats
the complete rectangular window as the island.

## Worker-local Phase 4 handoff

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
