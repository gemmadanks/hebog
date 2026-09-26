---
tags:
  - architecture
  - dask
  - scalability
  - science
---

# ADR-008: Make the continuum composition tile-native

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-09-18 |
| **Last Updated** | 2026-09-26 (a wide owner's connectivity is decided from its cores, replacing its T3 rule) |
| **Deciders** | Gemma Danks |
| **Tags** | tiling, halos, ownership, reconciliation, memory, invariance |

---

## Context

ADR-005 decided that all image-sized scientific work uses hierarchical haloed
tiles. Hebog implements that decision only for the first part of the pipeline.
Background and RMS estimation and first-pass compact detection run per tile
through an executor; tiled multiscale, deblending, measurement, fitting and
compact catalogue stages exist in `hebog.stages` but only tests call them. The
installed public path, `hebog.public_science.build_configured_continuum_products`,
receives whole `float64` planes and holds about ten of them at once. That is
why the public size limit is 1,024 pixels per side.

The arithmetic is unforgiving. One `float64` plane is 16 GB at 45,000² and
80 GB at 100,000². The development machine has 18 GiB of RAM, so from 22,500²
upward no image-sized array can exist in one process. Every remaining
milestone depends on removing them: M4 benchmarks Rapthor sector images, M5
bounds the graph for 100,000², and M6 qualifies the LOFAR ladder.

Three properties of the current science make this tractable, and were
confirmed while preparing this decision:

- No stage needs a global continuous statistic. Scale signal-to-noise is
  calibrated analytically per pixel from a propagated RMS
  (`calibrated_scale_snrs`), not from a global noise estimate. The only global
  objects are label equivalences, per-object record aggregates, and the
  background and RMS grid.
- The pixel-domain kernels are already halo-bounded, and their halos are
  small. For a 5-pixel beam, `derive_stage_halo_plan` gives 34 pixels for the
  matched-filter bank, 14 for the à trous transform, 15 for segment
  association and 3 for segment refinement. The reviewed noise grids are
  larger: the 150/50 coarse grid needs about 125 pixels and the adaptive
  35/7 grid with its 75-pixel influence radius and 20-pixel transition needs
  about 120. **The noise grid, not the multiscale filters, sets the maximum
  halo**, and at roughly 125 pixels it sits well inside the quarter-core
  limit that the
  [scalability contract](../../reference/performance-scalability-contracts.md)
  sets for its smallest admitted core of 2,048 pixels.
- Several kernels already accept tiled inputs.
  `assign_seeded_multiscale_support` resolves ties by a caller-supplied global
  row-major seed reference, `reconcile_island_tiles` merges boundary
  equivalences hierarchically, and the deblending, deferred-completion and
  extended-measurement stages already shard exact membership.

What is missing is a single stated contract: which pass each public stage
belongs to, what it reads, which task owns each result, what crosses the
executor boundary, and how the pieces merge. Without it the convergence of
`public_science.py` onto `stages/` would decide those questions one commit at
a time, and partition invariance would be discovered rather than designed.
The plan names extended association as the largest risk to M2 for exactly
this reason.

## Problem Statement

How should the public continuum composition be decomposed into tiles, so that
one composition serves every image size, peak memory scales with a tile rather
than an image, and results do not depend on tile geometry, partition origin,
worker count, completion order or retry?

## Options Considered

| Option | Description | Partition invariance | Bounded memory | Scheduler cost | Small-image overhead | One composition | Reuse of current code | Overall score |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 3 | 3 | 2 | 2 | 2 | 1 | - |
| **Tiled passes with an object phase** | Haloed pixel passes separated by global reductions, then bounded per-object tasks with an escalation path | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | 37 |
| **One fused task per core** | Every stage for one core evaluated in one task under the maximum halo | ❌ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | 29 |
| **Size-branched composition** | Keep the whole-array path below a size threshold and tile only above it | ❌ | ⚠️ | ✅ | ✅ | ❌ | ✅ | 26 |
| **Object-parallel only** | Keep image-sized filter planes whole and parallelise only islands and sources | ⚠️ | ❌ | ⚠️ | ✅ | ⚠️ | ⚠️ | 25 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

A fine-grained public Dask-array graph was rejected in ADR-005 and is not
rescored here.

The fused single-task option fails on invariance rather than on cost: an
island, a support region or an association pair may exceed any fixed halo, and
a task that sees only its own read cannot decide whether a component continues
beyond it. The size-branched option reintroduces the two scientific paths that
this milestone exists to remove, and makes one-tile versus many-tile
comparison meaningless because the two sides would run different code.
Object-parallel work alone leaves the filter, à trous and support planes
image-sized, which is the state M2 must leave behind.

## Decision Outcome

Hebog will use **tiled passes with an object phase**. The public composition
becomes four passes over image-anchored geometry, followed by materialisation.
A pass boundary exists where, and only where, a global reduction must complete
before the next stage can decide anything.

- **Pass A — noise.** Coarse grid statistics, adaptive candidate discovery,
  the source-protected fine grid, and the background and RMS planes.
- **Pass B — detection.** One read per tile produces prepared inputs, the
  matched-filter bank, the à trous transform, thresholding and tile-local
  island labels with boundary summaries. These stages are fused because they
  share one read window.
- **Pass C — support.** Seeded multiscale support, segment refinement,
  cross-scale persistence and island admission, using globally reconciled
  label mappings sharded per tile. Final labels and mask are written here.
  Pass C is several rounds rather than one, because two of its steps are
  scoped to an owner and two of its inputs are global reductions; the rounds
  are listed under *Owner-scoped connectivity* below.
- **Pass D — objects.** Deblending, compact measurement and fitting, extended
  measurement, source association and catalogue rows, as bounded per-object
  tasks reduced hierarchically. Like pass C it is several rounds, because
  three of its steps are global reductions rather than per-object work; the
  rounds are listed under *The object pass's rounds* below.

### Rules that hold for every stage

1. **Cores own pixels.** A tile writes only its non-overlapping core. Halos
   are read, never written.
2. **Canonical pixels own objects.** An island, component or source is owned
   by the tile core containing the row-major minimum pixel of its reconciled
   global support. Identity is a stable hash of that global pixel, so it does
   not change with tile geometry, label integers or completion order.
3. **Derived geometry is anchored to the image, never to the partition.**
   Noise grid cells, adaptive influence boxes and filter evaluation blocks are
   placed from the image origin. Moving `partition_origin_yx` changes which
   task computes a value, never the value.
4. **Nothing image-sized crosses the executor boundary or reaches the
   driver.** Tasks exchange records, bounded summaries and Zarr chunk
   identities. Label mappings are sharded to the labels present in a tile;
   an accepted-label table is never broadcast whole.
5. **Reductions are hierarchical and order-independent.** Merge operations are
   associative and commutative, or are applied to a canonically sorted input.
6. **Read once per pass.** A tile reads its window once and derives every
   quantity that pass needs from it.
7. **Store a plane only if a later pass or a product needs it.** Background,
   RMS, publication labels, the mask and the position signal are stored;
   filter responses, à trous coefficients and normalised planes are not.

### Per-stage contract

Halo values are for a 5-pixel beam and the reviewed 150/50 and 35/7 grids.

| Stage | Halo | Ownership | Boundary summary | Merge |
| --- | --- | --- | --- | --- |
| Input admission | 0 | file | header record, streamed digest | none |
| Coarse noise grid | ⌈150/2⌉ + 50 = 125 | cell owned by the core containing its centre | cell statistics at grid resolution in Zarr | none; cells are disjoint |
| Adaptive candidates | 34 (matched-filter) | candidate owned by the core containing its peak | canonical peak, influence box | deterministic union of overlapping boxes keyed by canonical peak |
| Adaptive fine grid | 75 + 20 + ⌈35/2⌉ + 7 = 120 | as coarse grid, inside candidate regions | fine cells at grid resolution | none |
| Background and RMS planes | one grid cell (50) | pixel core | none | none |
| Matched-filter bank | 34 (4σ at 4 beams) | pixel core | none | none |
| Residual B3 à trous | 14 (frozen cumulative) | pixel core | none | none |
| Island labelling | 0 | pixel core; labels tile-local | edge label runs, per-label pixel count, sum, bounding box, canonical pixel | union–find over boundary equivalences, tree-reduced; aggregates summed |
| Island admission | 0 | reconciled island | accepted-label set | area and pixel-count predicates on merged aggregates; the accept map is sharded per tile |
| Seeded multiscale support | 15 (3 beams) | support pixel owned by its nearest global seed reference | global seed references of owners present in the read | none; the read carries globally reconciled support components, and ties are broken by row-major seed reference in-read |
| Segment refinement, pixel work | 3x3 opening influence + 0.5-beam recovery | pixel core | none | none |
| Segment refinement, owner connectivity | owner window | owner canonical pixel | one restore decision per owner | none; decisions are applied in the core round |
| Cross-scale association | 0 | scale detection owned by its canonical pixel | per-scale label overlaps observed in the core | union of edge sets, then persistence per connected group |
| Persistent publication, owner bridges | owner window | owner canonical pixel | label patch bounded by the owner window | patches applied in the core round |
| Compact deblending | island bounding box within the admission limit | island canonical pixel | exact membership shard | concatenation by island |
| Compact measurement and fitting | component box + 8 (1.5 beams) | component canonical pixel | component record | none |
| Extended measurement | 8 (1.5 beams) per owned core | object canonical pixel; each intersected core contributes | additive moment and photometry accumulators, bounding box | accumulators summed at the owner |
| Position à trous filter | 14 | pixel core | none | none; see below |
| Source association | pair bounding box, or a reduced line | the canonically first component of the pair | edge record with saddle margin and normalised separation | canonicalised edge union, union–find groups, complete-link cliques resolved per group |
| Source measurement and rows | 8 (1.5-beam aperture) | source canonical pixel | catalogue shard | hierarchical shard reduction rejecting duplicates |
| Product materialisation | 0 | row block | written chunk identity | ordered chunk index |

### Objects larger than one halo

Extended emission, close blends and association pairs are not bounded by any
halo. A three-tier escalation applies, and the tier is chosen from measured
extent, never from a guess:

- **T1, one task.** The object's bounding box, plus its stage halo, fits the
  admitted task limit. One owner task computes it exactly.
- **T2, reducible accumulation.** It does not fit, but the quantity is an
  associative accumulation: pixel counts, moment sums, aperture photometry,
  bounding boxes, minima along a line, and the label equivalences themselves.
  Each intersected core contributes its part in global coordinates and the
  owner sums them. The result equals the T1 result up to floating-point
  summation order, which is fixed by reducing contributions in canonical
  core order.
- **T3, irreducible.** The quantity needs a simultaneous view of the whole
  object, such as a joint non-linear multi-Gaussian fit across an object
  larger than the admitted task. The object is **not** fitted. It is measured
  through T2 and published with an explicit disposition recording why, exactly
  as compact deferrals are published today. Silently truncating, dropping or
  splitting such an object is prohibited; if T3 becomes common on real LOFAR
  mosaics, the admitted task size is raised, or the case is escalated to a
  scientific decision, rather than weakened in place.

### Owner-scoped connectivity

Two steps of the support pass are scoped to an **owner**, not to a bounded
neighbourhood, and were found by reading the installed composition rather than
assumed. `refine_multiscale_segment_labels` ends by restoring an owner's
original support when cleanup would split it, and
`refine_persistent_publication_labels` ends by preserving the previously
published regions that bridge two retained parts of one owner. Both iterate
over the window holding an owner, so neither can be decided inside a tile core
whose halo is smaller than that owner. Two further quantities are global: the
connected components of `(direct support ∪ significant multiscale support) ∩
valid`, which decide which seed a support pixel may be attached to, and the
set of owners published anywhere, which decides which owners persistent
support may restore.

Pass C therefore runs as rounds, each cheap relative to pass B's filters:

| Round | Scope | Reads | Writes or returns |
| --- | --- | --- | --- |
| Topology | core, halo 0 | detection labels, reconstruction mask, validity, scale masks | support-union and per-scale island summaries, adjacent-scale label overlaps |
| Auxiliary publication | core, halo 0 | as above, plus the reconciled mappings | `support-components`, `persistent-support` |
| Owner connectivity | owner window + refinement halo, or each core a wide owner's window reaches | detection labels, direct signal to noise, reconstruction mask | one restore decision per owner; for a wide owner, its refined support's components in each core |
| Published owners | core + refinement halo | the published planes, owner reference pixels, restore shard | the owners published in the core |
| Owner bridges | owner window + refinement halo, or each core a wide owner's window reaches | as above, plus the published-owner shard | a label patch bounded by the owner window; for a wide owner, its base and candidate components in each core |
| Final write | core + refinement halo | as above, plus the patch, wide-owner and admission shards | `component-labels`, `measurement-labels`, `publication-labels`, `retained-mask` |

Only the last round writes. Each pixel quantity is recomputed in the round
that needs it, which costs a bounded repeat of cheap neighbourhood work and
saves three intermediate label planes.

The refinement pixel work needs the opening influence **and** the recovery
radius together, not their maximum: a pixel recovered at the recovery radius
is labelled from opened support that must itself be correct there. A 3x3
binary opening erodes then dilates, so its influence is two pixels, and the
dense-core count reaches one further. Recomputing the refinement in a later
round is preferred to storing it, exactly as pass B recomputes its filters
rather than persisting a response bank.

Both owner quantities are ADR-008 T1 work keyed by the owner's canonical
pixel, so they do not move with tile geometry, label integers or completion
order. An owner whose window exceeds the read budget is not T3, as this
decision first had it, because neither quantity needs the window: both are
connected components of the owner's own pixels, which are T2. Each core the
owner's window reaches labels its same-label components and returns their
labels and core-edge pixels; the components join where they meet across a
core edge, with the island reconciliation's eight-connected edge rule
restricted to equal labels, since two owners that touch must not merge; and
the restore and bridge rules are applied to the joined components
(`hebog.algorithms.owner_connectivity`). A candidate that touches two base
parts is itself a bridge and two candidates never touch, so the bridge
rule's fallback reduces to keeping the one part that holds the owner's
earlier pixels. The write round relabels its own core exactly as the bridge
round did and applies its share of the decision by component number. The
answer is the window's for every owner, so a wide owner publishes exactly
what a narrow one would.

### The object pass's rounds

Every scientific step of pass D already works on one object inside its own
bounding box, so converting it is mechanical — except where a step's *work
unit* is itself global. Reading the installed composition found three such
steps, and they set the round boundaries:

- **Fit parents.** `_measurement_fit_parents` dilates the measurement support
  by the fit context margin and labels the result, so owners whose contexts
  touch are fitted jointly. That connectivity follows a chain of any length,
  exactly like pass C's support components, and must be reconciled before any
  fit runs.
- **Measurement support.** Each fit parent contributes persistent measurement
  support into its own window with a boolean OR. The accumulation is
  associative, so each parent returns a patch and the cores write the plane.
- **Cross-parent loops.** `_cross_parent_loop_groups` labels the *accumulated*
  measurement support and reconciles resolved loops that span several fit
  parents, so it can only run once every parent's patch is known.

The extended-residual search, `_extended_residual_groups`, labels the same
accumulated support with the same connectivity and works feature by feature,
so it shares that work unit rather than adding a fourth. One round evaluates
both steps inside one support feature's window, reading the window once. A
feature is therefore the object of the last grouping round, exactly as a
parent is the object of the deblend round.

That round needs the fit records and the proposed compact groups of every
component whose *measurement-label* footprint reaches its window, which is
not the same set as the feature's own members: a fit outside the feature
still enters the subtracted model. The scan round therefore also returns each
measurement label's global bounds, and the driver shards the records by
bounding-box intersection with each feature's window. The shard is a superset
of what the task uses, and the task re-checks pixel membership, so no
accepted-label table is broadcast whole.

The feature labels are not published. A feature's window is its reconciled
global bounds plus the margin, so it contains the feature entirely, and the
task recovers it by labelling the support inside its own window and selecting
the component holding the feature's canonical first pixel. Publishing a plane
that only one round reads would cost a generation for nothing.

| Round | Scope | Reads | Writes or returns |
| --- | --- | --- | --- |
| Parent extents | core, halo 0 | `component-labels`, `measurement-labels` | each parent's bounds and first pixel in both planes, and its direct size |
| Deblend | parent window, for an admitted parent only | `direct-snr`, `valid-pixels`, both label planes | each parent's component count |
| Component write | core, halo 0, then the window of each parent it holds that splits | both label planes; `direct-snr` and `valid-pixels` in a splitting parent's window | `component-direct-labels`, `component-measurement-labels` |
| Fit parents | core, halo 0 | `component-measurement-labels` | context island summaries; then `fit-parent-labels` |
| Component fits | fit-parent window + margin, or a deferred parent's cores | residual, RMS, validity, both component planes | fit records, groups, grouping evidence, a measurement-support patch, each owned component's association record |
| Support write | core, halo 0 | the patches | `measurement-support` |
| Support features | core, halo 0 | `measurement-support`, `valid-pixels`, `component-measurement-labels` | feature island summaries and each measurement label's bounds |
| Cross-parent loops and extended residual | support-feature window + margin | residual, RMS, validity, `measurement-support`, `component-measurement-labels`, the sharded fit records | extended group records and grouping evidence |
| Scale feature labels | core, halo 0 | the reconciled per-scale mappings | `scale-{order}-labels` |
| Hierarchy overlaps | core, halo 0, then one feature's window plus its B3 footprint, or each core that work reaches, under twice the widest B3 radius, when the window exceeds the read budget | `component-direct-labels`, `valid-pixels`, `reconstruction-mask`, the scale label planes | component, feature, support and envelope overlap records |
| Source labels | core, halo 0 | `component-measurement-labels`, the sharded owner-to-source map | `source-labels` |
| Source support | core, halo 0, then the window of each connected support component it holds, or a component's cores when that window exceeds the read budget | `source-labels`, `persistent-scale-support`, `measurement-support` | support island summaries, then a wide component's seeds and candidates, then `source-measurement-labels` |
| Source apertures | core, halo 1.5 beams | `source-measurement-labels` | `source-aperture-labels` |
| Source rows | source window + 1.5-beam aperture, or its cores when that window exceeds the read budget | image, background, RMS, validity, source labels, position signal | catalogue shards, each segment's local noise |
| Detection island rows | core, halo 0, then one island's window, or the island's cores when that window exceeds the read budget | `retained-mask`, `component-measurement-labels`; then image, background, RMS, `retained-mask` | island boundary summaries and owner-to-island pairs; then catalogue island rows, or a wide island's pixels from each core |

Component numbering is canonical because the driver offsets each parent's
local labels by the components every earlier parent produced, in ascending
first-pixel order. A parent above either hard compact-work bound is ADR-008
T3 and is already published as one explicit deferred component, which is the
reviewed science rather than a new rule. That component is the parent's own
support in both planes, so deferral needs no pixel: the extents carry each
parent's direct size, the driver decides deferral from them with the
deblender's own rule, and the cores holding a deferred parent relabel it in
the write round.

The numbering needs each parent's component count and nothing else, so that
is all the deblend round returns. Summed over parents, the memberships are as
large as all the support in the image, and rule 4 keeps them off the driver.
A parent published as one component (deferred, too faint to split, or one
watershed region) is its own support in both planes, so its cores relabel it
as they relabel a deferred parent. A parent that splits is deblended again by
each core that holds it, inside the same windows, which decides the same
memberships bit for bit; that costs a second deblend of the parents that
split, and of a split parent once more for each further core it crosses.
Source support needs no count first: each core assigns the narrow components
it holds, each inside its own window, and writes its own share, so a
component crossing cores is assigned once by each of them and nothing
returns but the component's identity.

### Objects wider than the read budget

Every per-object round batches neighbouring objects so that one read serves
several, and `maximum_batch_read_pixels` bounds that read. The budget alone
bounds nothing, though: no admission limits an object's own area, so a
filament's bounds can span the image, and each round used to exempt a batch's
first object from the budget. `hebog.stages.batching` now holds the one rule
every round batches under. A batch closes before its read would exceed the
budget, and an object wider than the budget shares a read with nothing. It
is read alone only when a reviewed admission rule bounds its window
independently of the image; otherwise the batcher refuses it, and the round
must measure it from the cores that hold it or not read it at all.

Which of the two a round takes follows from its science. Where the quantity
is a set reduction over the object's pixels, each core returns its part and
the driver reduces them in raster order, which reproduces the window's result
bit for bit. Where the science needs the whole object at once, the round
relies on an admission bound instead, and the bound it relies on is named
here, in pipeline order:

| Round | Whole object at once? | An object wider than the budget |
| --- | --- | --- |
| Owner connectivity and bridges (publication) | No: whether cleanup splits an owner, and which earlier regions bridge its parts, are questions about the connected components of its own pixels | Decided from every core its window reaches: same-label components joined across core edges, as under *Owner-scoped connectivity*, and the write round applies each core's share. `PublicationStageResult.wide_owner_count` reports how many owners took that path |
| Component topology | Yes: the watershed and the assignment of measurement support to its seeds need the parent's whole support | A parent beyond either hard compact-work bound is deferred as T3, exactly as the whole-plane deblender defers it, and never read. An admitted parent's direct window is within `maximum_compact_bounds_pixels` (250,000 pixels in the reviewed profile), and the support pass attaches measurement support only within the reviewed recovery radius of it, so a parent wider than the budget is read alone within that bound |
| Component fits | Yes for the fit: a joint model needs the parent's whole window. No for its components' association records, which are moments over each component's own pixels | A parent whose window `maximum_bounds_pixels` refuses is deferred as T3, exactly as the whole-plane pass defers it, so its window is never read: the records of the components it owns come from the cores that hold them, restored to raster order, bit for bit. A parent the bound admits is read in its window, alone when that window exceeds the budget |
| Cross-parent loops and extended residual | Yes: grouping labels and fits the feature's window | Read alone. `support_feature_window` leaves a feature wider than `maximum_bounds_pixels` ungrouped as T3, exactly as the whole-plane pass does, so that bound (250,000 pixels in the reviewed profile) limits every grouping read |
| Hierarchy overlaps | No: an envelope is exact support dilated through valid pixels by the reviewed B3 radius, an influence is that envelope dilated again, and an overlap is one shared pixel | A feature whose influence window, or a pair whose box, exceeds the budget is decided in each core it can reach, read with twice the radius as its halo, which decides every pixel of that core exactly. An influence is the union of the owners the cores find, and a pair overlaps where any core finds a shared pixel |
| Source support | No: each unseeded pixel goes to its nearest seed of the same component, a per-pixel answer that depends only on the component's seeds | Its cores return the component's seeds and unseeded pixels, the driver assigns each pixel from the seeds alone, and the write round applies the assignment sharded to the cores. The seeds are the object's own pixels, not its window |
| Source and component rows | No: the position, flux, peak, moments and noise are sums, a first maximum and a median over the pixels a segment owns, holds in its measured support or holds in its aperture | Measured from its cores: each returns those pixels with their values, and the row is measured from them restored to raster order, bit for bit |
| Detection island rows | No: a count, sums and a median over the island's pixels | Measured from its cores |

### Extended association

Association is a record-graph computation, not a pixel pass. The installed
association is the multiscale hierarchy, not the centroid-pair predicate this
decision first anticipated, so the boundary is drawn where that hierarchy
actually touches pixels. Reading it found exactly five pixel questions, and
every one of them is either a per-tile reduction or bounded by one feature's
own window:

- which scale features each direct component's exact support intersects;
- which parent feature each child feature overlaps at the adjacent scale;
- which components lie inside a feature's exact support, and which lie inside
  the reviewed B3 influence of its envelope;
- which retained support component contains each feature and each direct
  component, over the connected support the detection pass published;
- which two features' B3 envelopes overlap.

`HierarchyOverlaps` is that answer set, and `associate_from_hierarchy_overlaps`
is the decision that consumes it. The decision holds no plane, so it cannot
depend on tile geometry or completion order, and
`summarize_hierarchy_overlaps` evaluates the same reductions over whole planes
as the serial oracle. Envelope masks never cross the executor boundary: a
feature's task derives its own influence set and its envelope's overlaps
inside the pair box, and returns records.

The driver never gathers the component set. Records live in owner-tile shards
and reduce hierarchically. Each record is built by the fit parent that already
reads that component's residual and validity, so describing a component costs
no round and no read of its own.

Every overlap above is stated between *globally* labelled features, so the
scale feature labels must be readable by window. The detection pass already
reconciles the per-scale islands and writes their support masks, so it gains
one publication round that writes `scale-{order}-labels` beside
`scale-{order}-significant`. That is three more stored planes, admitted under
*Store a plane only if a later pass or a product needs it* because the object
pass now needs them; the alternative, reconciling each scale a second time in
pass D, would repeat a reduction pass B has already performed.

### The à trous position filter

The public path currently evaluates the à trous transform a second time to
build the position signal. Under this decision the transform is evaluated once
per tile in pass B and the position signal is written as a stored plane in
pass C, so pass D reads it by window with the object it measures. Where the
14-pixel halo is clipped by the image edge, the denoised value stays unavailable
and the signed residual remains the documented fallback, which is the existing
behaviour and is not a reason to discard an edge source.

### The continuum catalogue

Source rows are built by owner tasks from the source label plane and the
stored position signal, and merged as catalogue shards through the existing
hierarchical reduction. Row order in the published catalogue is canonical, by
source identity, not by completion order. Measurement dispositions and support
stages accompany the rows as records, not as planes.

The catalogue holds one global step, and it is the same shape as pass D's
others. `assign_persistent_source_support` labels the union of the source
seeds and the persistent support, then assigns each unseeded pixel of a
connected component to its nearest source seed, breaking an exact tie towards
the smaller source label. The labelling spans tiles and must be reconciled;
the assignment does not, because a component's candidates and seeds both lie
inside its own bounds. `assign_connected_source_support` is that per-component
step, and the whole-plane function is it in a loop, which keeps the serial
oracle exact by construction. Tie-breaking needs no global table: ranking the
seeds by canonical source identity and taking the smallest rank among tied
neighbours is the same as taking the smallest label, which one window knows.

Everything else the catalogue does is per core or per object: mapping owners
to source labels, expanding apertures by the reviewed 1.5-beam radius, and
measuring each component's and each source's moments, and the local noise over
the support it owns, inside its own window. The noise is measured for every
segment the round observes, not only for the measurable ones, because a row
published from a fitted model quotes the same value.

The published catalogue also names islands, and they are the one object in it
that is not owner support: an island is a connected region of the retained
mask the publication pass wrote. That connectivity spans tiles like every
other label plane, so it is reconciled the same way — each core labels its own
retained mask and returns boundary labels, and the reduction numbers the
islands by canonical first pixel, which is the order labelling a whole plane
gives. The island labels are never published, because only two rounds read
them: the cores that observe which owners each island holds, and the task that
measures an island inside its own global bounds, which contain it entirely and
cannot connect it to another island. An owner is named against every island
its retained support reaches, because publication can split that support.
Admission bounds no island's area, so a filament's bounds can reach across the
image. An island whose window exceeds the read budget is therefore never read
whole: each core holding it relabels itself exactly as the scan did, the
reconciled mapping names the island's pixels there, and the row is measured
from those pixels restored to raster order, so it is the row the window would
give, bit for bit. The driver then holds that island's own pixels, not its
window, because its median noise has to see all of them.

The rows need no reconciliation at all. `build_hebog_segment_catalogue`
already measures one label at a time inside the window holding its support
and its aperture, so `build_segment_row` and `segment_moment_fields` are that
work taken out of the loop. The one step that crosses a segment's bounds is
the aperture expansion, and it reaches no further than the reviewed radius:
every seed that can own a core pixel lies inside the core read plus that
halo, and the tie towards the smaller canonical label is decided the same way
in a window as over the plane. So the row round is cores writing
`aperture-labels` under that halo, cores observing each label's bounds, and
one task per batch of segments measuring their rows — the simplest of pass
D's rounds, and the only one with no global reduction.

### A small image stays one tile

When the image fits inside one tile core, the manifest contains one tile,
every halo is clipped to the image, every boundary summary is empty, and
union–find performs zero rounds. The executor receives one batch per pass.
The only cost relative to today is one Zarr chunk per stored plane, which
ADR-007 already accepted as the single intermediate backend. Because filter
responses and à trous coefficients are not stored, the number of stored planes
does not grow with the number of stages. Tile cores are chosen from admitted
memory within the contract's 2,048–8,192 range; the current hard-coded 128
core is below that range and is replaced. A resource choice may change batch
size and core size, but never ownership or results.

### Numerical invariance

Partition invariance is defined, and tested, at two levels:

- **Exact** for everything that carries identity or a decision: labels, masks,
  memberships, reconciled island identity, component and source identities,
  accepted-label sets, catalogue row membership and ordering.
- **Bounded** for continuous filter responses, at the relative and absolute
  2×10⁻¹³ already used by the reviewed multiscale partition-equivalence tests.
  The à trous transform is a separable direct convolution and is exact under
  tiling; the residual tolerance comes from the matched-filter bank, which
  uses an FFT whose rounding depends on the transform shape.

The residual risk is explicit: a pixel within 2×10⁻¹³ of a detection threshold
could in principle change membership between partitions. Two responses were
considered and rejected for now — evaluating the matched filter on
image-anchored fixed transform blocks (bitwise, but new machinery and extra
padding work), and direct convolution everywhere (bitwise, but a 69×69 kernel
per pixel at 4 beams). Both remain available, and the fixed-block form is the
required escalation if the invariance suite ever observes a knife-edge flip.
The suite therefore includes knife-edge cases deliberately placed at the
threshold on tile edges, corners and shifted partition origins.

### The `float64` and `float32` decision path

Science planes stay `float64`. Tile bounding removes the memory pressure that
would otherwise motivate `float32`: a 2,048 core with a 125-pixel halo is a
2,298² read, about 42 MB per `float64` plane, so a task holding ten planes
stays near 420 MB at any image size. A later change to `float32` requires, in
order: a profile showing that memory bandwidth or admitted-plane count is the
binding constraint; restriction to stored intermediate planes only, never to
moment, photometry or fit accumulators; scientific-equivalence evidence on the
dataset matrix within the plan's margins, not a runtime result; and an
amendment to this ADR. Input images that are natively `float32` are promoted
at the kernel boundary, as they are today.

### Consequence for the executor

`map_batches` with a driver-side gather cannot express pass C and pass D: both
need bounded submission and worker-side reduction of shards the driver must
never hold. Completing the executor contract is therefore a prerequisite for
this composition rather than an independent improvement, which reorders the
milestone: the executor work comes before the convergence it enables.

## Consequences

- Good, because peak memory becomes a function of the tile core, the maximum
  halo and the batch size, and stops being a function of the image, which is
  what raises the public envelope past 1,024.
- Good, because one composition serves every size, so one-tile versus
  many-tile agreement is a meaningful test of the code that actually runs.
- Good, because ownership by canonical pixel makes identity, and therefore the
  catalogue, independent of tile geometry, worker count, completion order and
  retry.
- Good, because the escalation tiers make an object too large for one task a
  declared, published condition instead of a silent truncation.
- Good, because the largest halo is set by the noise grid at about 125 pixels,
  so halo re-reads cost a few per cent of a 2,048 core rather than a large
  multiple of it.
- Bad, because four passes read the image more than once; the existing single
  whole-array pass reads it once. Fusing within a pass limits this to one read
  per pass, and pass D reads only object windows.
- Bad, because every new scientific stage must now declare a halo, an
  ownership rule, a summary and a merge before it can be composed.
- Bad, because the matched-filter FFT leaves a 2×10⁻¹³ tolerance on continuous
  responses, so invariance is exact for decisions but not bitwise for every
  plane.
- Risk: association work is bounded by component density, not by pixels. A
  pathologically crowded field could produce a large edge set. The spatial
  cutoff and the per-group resolution bound it in practice; the scalability
  lane records edge counts so a real bound can be set from measurement.
- Risk: pass boundaries are synchronisation points. At 200 nodes a straggler
  in pass B delays pass C. Batching and the planner's task-count bounds in M5
  address this; it is recorded here as a known property of the shape.

## Confirmation

- One-tile versus many-tile equivalence on analytic images, over tile shapes,
  partition origins, completion orders and retries, asserting exact equality
  for identity-carrying outputs and 2×10⁻¹³ for continuous responses, with
  sources on every edge and corner topology and at knife-edge thresholds.
- Architecture tests reject image-sized arrays in stage results, in executor
  payloads and in driver-held state, and reject whole-table label broadcasts.
  The composition records carry no array field, which a static test asserts,
  and a run that walks the driver's own locals at the terminal builder finds
  no image-shaped array reachable from them. The component-topology and
  source-support tests record every payload and result their rounds exchange
  and require them to carry no array but the support scan's core boundary
  labels.
- A stage-halo admission test proves every declared halo is below one quarter
  of the admitted core, and that a plan exceeding the admitted memory is
  rejected before submission rather than during it.
- Escalation tests place an object larger than the admitted task limit across
  several cores and assert that T2 accumulation reproduces the T1 result and
  that a T3 case publishes a disposition rather than a truncated measurement.
- Peak-RSS measurements across the size ladder show memory scaling with tile
  size, not image size, as each envelope tier is raised.
- The quick science check and Serial/Dask agreement pass at every step of the
  convergence, and the whole-array path is deleted only once they do.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-004](004-keep-top-level-scheduling-in-rapthor.md), [ADR-005](005-scale-large-images-with-hierarchical-tiles.md), [ADR-006](006-isolate-compatibility-with-versioned-schemas.md), [ADR-007](007-use-zarr-for-intermediate-image-storage.md) |
| **Documentation** | [Performance and scalability contracts](../../reference/performance-scalability-contracts.md), [Domain model](../../explanation/domain-model.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
