# Phase 5 bounded-execution halo review

## Status

The first Phase 5 Step 5 task is complete. Hebog now derives every
stage-specific read halo from the implemented scientific policy before image
tasks are allocated. The reviewed Rapthor profile rejects a shared tile core
when any halo is not strictly smaller than one quarter of that core, when a
worst-case interior read exceeds the global task-pixel limit, or when extended
measurement exceeds its tighter stage-specific limit.

This is an engineering review of geometry and pixel admission. It does not
complete Step 5: one-tile/many-tile equality, executor invariance, and measured
retained-byte, workspace, summary, shard, and graph-size evidence remain open.

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
segment refinement and compact context require three pixels, and the 1.5-beam
measurement halo is eight pixels. A 128-by-128 core is rejected because the
34-pixel halo violates the existing strict quarter-core guardrail.

## Fail-closed planning boundary

`derive_phase_five_halo_plan` returns immutable per-stage records containing
the halo, scale radii where applicable, worst-case read shape, read-pixel
count, admission limit, and scientific basis. It uses the same halo helpers as
the production kernels, so planning cannot drift from kernel construction.
The matched-filter halo is computed without allocating a Gaussian kernel; an
oversized beam therefore fails geometry admission before that allocation.

Extended measurement uses the smaller of the global limit and its own
`maximum_task_pixels`. Every other stage uses the global limit. Pixel limits
are the pre-allocation guard, not a byte-level performance claim. The final
Step 5 audit must still record peak retained bytes and workspace planes under
SerialExecutor and the existing executor path.

Machine-readable policy is frozen in schema 5 of
`config/contracts/phase-5-multiscale.json`.

## Review decision

The formulas are sufficient for the current three-scale Rapthor profile and
are consistent with the implemented kernels and existing partition geometry.
No scientific threshold, association rule, compact output, or recovery-
campaign result changes. Proceed to one-tile/many-tile equality across edges,
corners, rectangular cores, invalid regions, largest scales, and shifted
partition origins. Qualification and runtime claims remain closed.
