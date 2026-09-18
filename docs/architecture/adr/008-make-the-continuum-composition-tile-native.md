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
| **Last Updated** | 2026-09-18 (pass C rounds) |
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
  tasks reduced hierarchically.

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
| Segment refinement, pixel work | opening radius + 0.5-beam recovery | pixel core | none | none |
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
| Topology | core, halo 0 | detection labels, reconstruction mask, validity, scale masks | support-union and per-scale island summaries, adjacent-scale label overlaps, detection labels present |
| Auxiliary publication | core, halo 0 | as above, plus the reconciled mappings | `support-components`, `persistent-support` |
| Measurement | core + 0.5-beam recovery | detection labels, reconstruction mask, `support-components`, owner reference pixels | `measurement-labels` |
| Owner connectivity | owner window + refinement halo | detection labels, reconstruction mask, validity | one restore decision per owner |
| Publication | core + opening and recovery halo | as above, plus `measurement-labels` and the restore shard | `publication-labels`; owners published in the core |
| Persistent | core + opening halo | `measurement-labels`, `publication-labels`, `persistent-support`, published-owner shard | `persistent-labels` |
| Owner bridges | owner window | `measurement-labels`, `publication-labels`, `persistent-labels` | a label patch bounded by the owner window |
| Final write | core, halo 0 | `persistent-labels`, patch and admission shards | final labels and mask |

The refinement pixel work needs the opening radius **and** the recovery radius
together, not their maximum: a pixel recovered at the recovery radius is
labelled from opened support that must itself be correct there. Recomputing
the refinement in a later round is preferred to storing it, exactly as pass B
recomputes its filters rather than persisting a response bank.

Both owner quantities are ADR-008 T1 work keyed by the owner's canonical
pixel, so they do not move with tile geometry, label integers or completion
order. An owner whose window exceeds the admitted task is T3: it keeps its
pixel-round support and is published with a disposition recording that its
connectivity was not restored, exactly as compact deferrals are published
today. It is never silently split.

### Extended association

Association is a record-graph computation, not a pixel pass. Component records
carry global centroids, moments, parent support and stable identities, so the
candidate pairs follow from a spatial index over centroids with a cutoff equal
to the mean directional FWHM of the pair. The edge predicate needs pixels only
along the straight line between the two centroids, and its two tests — the
minimum signal-to-noise on that line and the validity of every line pixel —
are both associative reductions. A pair whose box fits one task is evaluated
by the owner of its canonically first component; a longer pair is evaluated as
a segmented reduction over the cores the line crosses. The edge set is then
canonicalised, so the complete-link agglomeration that forms sources consumes
a partition-independent input. Groups are resolved per connected component of
the edge graph, which keeps the clique work local and bounded.

The driver never gathers the component set. Records live in owner-tile shards
and reduce hierarchically.

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
