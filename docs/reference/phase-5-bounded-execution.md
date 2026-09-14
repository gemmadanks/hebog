# Phase 5 bounded-execution halo review

## Status

Phase 5 Step 5 is complete. Hebog derives every
stage-specific read halo from implemented scientific policy before image tasks
are allocated, and the promoted multiscale detection path has a deterministic
one-tile/many-tile equality oracle plus a production Serial/Dask execution
path. The reviewed Rapthor profile rejects a shared tile core when any halo is
not strictly smaller than one quarter of that core, when a worst-case interior
read exceeds the global task-pixel limit, or when extended measurement exceeds
its tighter stage-specific limit.

This is bounded-execution development evidence, not qualification or a runtime
claim. Extreme-scale scheduler reduction remains a Phase 6 responsibility.

## Derivation

All tiles have one deterministic, non-overlapping output core. Read halos are
stage-specific and never confer output ownership. For a core
`(core_y, core_x)` and symmetric halo `h`, the admitted worst-case interior
read is `(core_y + 2h, core_x + 2h)`. Image-edge reads may be smaller because
the partition manifest clips them to the logical image.

| Stage | Required halo | Derivation and boundary |
| --- | --- | --- |
| Matched-filter seed aid | Per-scale radius `ceil(4 * width_beams * beam_major_sigma_pixels)` | The allocation-free helper used by the actual Gaussian kernel builder gives the 1-, 2-, and 4-beam radii. This remains a seed aid and governed comparator; residual B3 à trous is the selected extended-emission representation. |
| Residual B3 à trous | Cumulative radii 2, 6, and 14 pixels | Each five-tap B3 stage has radius `2 * dilation`; the frozen dilations are 1, 2, and 4 pixels. |
| Segment labelling | Zero image halo | Each owned response core is labelled locally. Eight-neighbour edge and corner connectivity is recovered from bounded boundary-label summaries. |
| Residual/reconstruction segment association | `ceil(3 * beam_major_fwhm_pixels)` | The promoted candidate groups retained original-residual support with reconstructed adjacent-scale support through the frozen three-beam dilation before deterministic component labelling. |
| Segment refinement | `max(1, ceil(0.5 * beam_major_fwhm_pixels))` | One pixel covers the three-by-three opening. The half-beam term covers coherent multiscale-support recovery and nearest-label assignment. |
| Cross-scale association | Zero image halo after label reconciliation | Association consumes exact reconciled support records and overlaps rather than rereading an image plane. |
| Compact context | `ceil(0.5 * beam_major_fwhm_pixels)` | The reviewed many-to-many context graph uses exact overlap, reference containment, or half-major-beam adjacency without changing support ownership. |
| Extended measurement | `ceil(1.5 * beam_major_fwhm_pixels)` | The approved original-pixel aperture is nearest-owned and uses compact support as a barrier. The Phase 5 planner rejects any other aperture. |
| Combined reconciliation | Zero image halo | Canonical bounded records are reduced pairwise; image arrays do not cross this boundary. |
| Product materialization | Zero image halo | The final mask and products are written in bounded row blocks from reconciled records. |

Phase 2 background/RMS preparation and Phase 4 compact products are inherited
inputs, not duplicated Phase 5 image stages. All beam-dependent formulas use
the restoring-beam major FWHM because it is the conservative support radius
for an arbitrarily oriented elliptical beam.

For the five-pixel-major review beam and a 256-by-256 core, the matched-filter
radii are 9, 17, and 34 pixels, the widest read is 324-by-324 (104,976 pixels),
segment association requires 15 pixels, segment refinement and compact context
require three pixels, and the 1.5-beam measurement halo is eight pixels. A
128-by-128 core is rejected because the 34-pixel halo violates the existing
strict quarter-core guardrail.

## Fail-closed planning boundary

`derive_phase_five_halo_plan` returns immutable per-stage records containing
the halo, scale radii where applicable, worst-case read shape, read-pixel
count, admission limit, and scientific basis. It uses the same halo helpers as
the production kernels, so planning cannot drift from kernel construction.
The matched-filter halo is computed without allocating a Gaussian kernel; an
oversized beam therefore fails geometry admission before that allocation.

Extended measurement uses the smaller of the global limit and its own
`maximum_task_pixels`. Every other stage uses the global limit. Pixel limits
are the pre-allocation guard; the exact byte evidence is recorded below.

## One-tile/many-tile equality evidence

The local filtering seam evaluates one exact clipped halo read and returns
only owned, immutable core arrays. It runs the frozen 1-, 2-, and 4-beam
matched-filter seed aid and the three-level residual B3 à trous transform. The
returned cores do not retain the halo-read allocation. Connected support is
then labelled per core and reconciled through the established bounded side and
corner summaries; no local label has global scientific meaning.

The deterministic analytic matrix compares one tile with rectangular
88-by-96 cores at origins `(0, 0)` and `(43, 47)`. It places four-beam emission
on both partition corners, places sources at the top and bottom-right image
edges, and crosses valid/invalid boundaries. Equality covers matched and B3
responses, validity, combined SNR, adjacent-scale reconstruction, original-
residual island retention, three-beam segment association, final refinement,
stable labels, island properties, and the direct-plus-reconstructed position
signal. Masks, topology, identities, positions, and integer properties are
exact; finite filter values use a `2e-13` relative and absolute tolerance for
FFT round-off.

The complete planes assembled by this test are a deliberately small serial
oracle only. Production execution retains response arrays only within a
bounded worker task and persists the accepted products described below; it may
not gather a large image on a worker or scheduler.

## Executor and product invariance evidence

The production multiscale stage uses two bounded passes. The first evaluates
the filters, labels only core-local adjacent-scale and original-residual
membership, drops its label cores, and returns side/corner summaries plus
scalar workspace evidence. Hierarchical reconciliation determines accepted
global reconstruction and residual components. The second pass recomputes the
same bounded filters, applies the immutable global label mappings, and writes
only eight accepted products: combined SNR, reconstructed and position
signals, retained and reconstruction masks, and three accepted significant-
scale masks. This recomputation is deliberate: Hebog does not persist the
matched-filter and B3 response bank across the image.

Workers return only compact summaries, checksummed `ProductChunk` identities,
and scalar execution evidence. The generation is published only after every
expected owner/product pair validates. Identical retries are idempotent;
missing, conflicting, or duplicated product chunks fail through the existing
Zarr generation contract.

The deterministic execution matrix covers one- and all-tile batches, an
intermediate batch size, reverse completion order, an identical retry of every
task, `SerialExecutor`, and existing-client Dask with one and two workers. For
one partition, every variant publishes byte-identical canonical generation
manifests, chunk checksums, masks, and global topology identities. A one-tile
and rectangular many-tile comparison reproduces exact accepted masks and
topology IDs; finite response-derived products retain the reviewed `2e-13`
tolerance. Chunk manifests necessarily differ across partitions because chunk
bounds are part of their identity, so the cross-partition invariant is the
logical science product and reconciled global identity rather than a false
claim that different storage layouts have the same bytes. The shifted-origin
science case remains covered by the preceding storage-independent oracle;
Zarr chunk ownership itself is canonically zero-origin.

The one-tile execution also reproduces the promoted serial residual-B3 oracle:
combined SNR, reconstructed signal, position signal, accepted residual and
reconstruction masks, and accepted per-scale support agree exactly or within
the same FFT tolerance. The two-pass design adds bounded recomputation whose
runtime impact must be measured against the 6-second incremental budget; it
does not authorize a performance claim.

## Structural resource evidence

The stage records exact owned NumPy payload bytes at its worker-local
checkpoints, the conservative kernel workspace estimates supplied by the
implemented filters, every compact boundary summary, every checksummed product
shard, and the number and maximum width of coarse executor tasks. Python object
overhead, allocator fragmentation, process RSS, transfer, and spill are not
invented from these structural counters; the controlled performance lane must
measure them separately.

For the reviewed five-pixel-major beam and 256-by-256 core, the widest
interior read is 324-by-324, or 104,976 pixels. The exact evidence is:

| Quantity | Bytes or count |
| --- | ---: |
| Retained filter-core arrays | 12,058,624 bytes |
| Retained detection-evidence arrays | 3,604,480 bytes |
| Matched-filter kernel workspace | 16,057,904 bytes |
| Residual-B3 kernel workspace | 18,484,096 bytes |
| Conservative complete filter-evaluation peak | 26,298,000 bytes |
| Topology summaries per tile | 2 |
| Scale summaries per tile | 3 |
| Boundary-label payload per tile across both passes | 20,480 bytes |
| Published product shards per tile | 8 |

The implementation copies the matched-filter core and releases its full read
responses before evaluating residual B3. It also releases source, background,
and RMS read windows after preparing the independent residual inputs. These
lifetimes make the recorded peak an implementation bound rather than the sum
of two unnecessarily co-resident response banks.

With `P` partitions and a configured maximum `B` tiles per batch, the graph
contains `2 * ceil(P / B)` coarse tasks in two waves, and its maximum width is
`ceil(P / B)`. There are no per-pixel, per-window, or per-island tasks. Serial,
reverse-order, retry, and one-/two-worker existing-client Dask execution report
the same structural evidence for a common batch size.

At the 3,000-square Phase 5 anchor, 256-square cores give 144 partitions. With
`B = 16`, the two-pass graph has 18 tasks, publishes 1,152 shards, and returns
2,949,120 boundary-array bytes (2.81 MiB) in total; the largest task retains at
most 196,608 boundary-array bytes and 128 shard identities. This is safely
bounded for the local qualification anchor. A 100,000-square image at the same
core size would have 152,881 partitions and about 2.92 GiB of boundary arrays.
That projection is intentionally not called extreme-scale readiness: it makes
the Phase 6 distributed hierarchical reduction and scheduler-load evidence a
hard prerequisite for the 100,000-square qualification.

Machine-readable policy is frozen in schema 8 of
`config/contracts/phase-5-multiscale.json`. The checksum is recorded in the
Phase 5 contract reference.

## Review decision

The two-pass execution and structural resource boundary is sufficient for the
Rapthor profile and is consistent with the implemented kernels, topology
reconciliation, and immutable Zarr generation contract. It changes no
scientific threshold, association rule, compact output, or recovery-campaign
result. Phase 5 Step 5 is complete. Proceed to qualification and incremental
performance; those claims remain closed until their separate gates pass.
