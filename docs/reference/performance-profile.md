---
tags:
  - performance
---

# Where Hebog spends its time

This page records what the complete-path profile measures, so that an
optimization starts from evidence rather than intuition. It describes
`0.12.0` plus the 21 September 2026 bottleneck work on the tile-native
composition, measured with `SerialExecutor` on the maintainer's machine.

Read it with the
[performance and scalability contracts](performance-scalability-contracts.md),
which set the gates, and the
[native-code assessment](../explanation/native-code-assessment.md), whose
decision gate this page feeds.

## How to reproduce it

```bash
just profile-execution --label my-profile --cprofile
just quick-benchmark --tier large
```

The profiler runs every case in a fresh single-thread process, and a second
time under `cProfile` when asked. It writes per-stage wall time and the
`cProfile` statistics under `benchmark-results/profiles/runs/<label>`. A
profile ranks costs; only the quick benchmark establishes a speedup.

!!! note "Sizes above the public envelope"

    `find_sources` refuses an image wider than 1,024 pixels with
    `SourceFinderImageTooLargeError`. The profiler and the quick benchmark
    raise that limit deliberately so the size ladder can be measured ahead
    of the envelope. A 2,048-pixel figure on this page is a measurement, not
    a supported size; the plan's scalability row states what is supported.

!!! warning "Measure on a quiet machine"

    The contract requires no concurrent unrelated workload. Runs taken at
    load average 4 to 7, with an endpoint-security scanner at half a core,
    disagreed with each other by up to 7% on the 1,024-pixel cases and
    produced a per-change attribution that was mechanically impossible.
    Check the load average before quoting a ratio, and prefer comparisons
    whose endpoints were measured in the same session.

## What dominates now

Shares are self wall time as a fraction of the complete run, from
`m2-fitting` on 21 September 2026.

| Stage | dense 1,024² | SDC1 crowded 1,024² | SDC1 crowded 2,048² |
| --- | --- | --- | --- |
| Per-pixel background refinement | 18% | 13% | 13% |
| Catalogue row measurement | 13% | 19% | 18% |
| Per-parent moments and fitting | 16% | 17% | 15% |
| Multiscale filters and labelling | 5% | 2% | 6% |
| Source association and catalogues | 2% | 6% | 6% |
| Per-parent deblending | <2% | 1% | <1% |

Three observations matter more than the exact numbers.

**No single kernel dominates.** After the 21 September work the largest
stage is about a fifth of the run, and the profile is flat rather than
peaked. That is the expected shape once the redundant work has gone, and it
is why the next gains are structural rather than kernel-level.

**Deblending is not a cost.** It is about 1% of a crowded field. An earlier
figure of 11% came from a profile taken before one-pass label extents
landed; the extent scan, not the deblender, was what that profile measured.

**Coordinate transforms are no longer a concentrated cost.** Astropy's
`SkyCoord` machinery accounted for 14% of self time, spread over about
11,000 single-position calls. Every one of those paths now converts a whole
batch in one call, so the cost follows the batch count rather than the
source count.

## What the work removed, and why

Each entry is a measured redundancy, not a micro-optimization. The pattern
repeats: a bounded per-object window is correct, but paying a fixed overhead
once per object multiplies it by the object count.

| Redundancy | Measured before | After |
| --- | --- | --- |
| Whole-core scan per label for its extent | 23% of dense 2,048² | one pass over labelled pixels |
| Zarr v2 metadata probes that always miss | 1,810 of 6,138 store reads | none |
| Group metadata rewritten per attribute | 282 of 513 store writes | 84 |
| Protection halo refiltered per cell block | 22× the image | 3.4× |
| Plane decoded per 16 objects | 4.06 GiB for a 4 MB image | 0.74 GiB |
| Frame machinery per measured position | 2.43 ms each | 0.060 ms batched |

## What remains, in priority order

1. **Per-pixel background refinement.** No per-source Astropy call now
   remains: the fit, the fitted rows, the moment shapes and the rows' own
   coordinates all convert a batch at a time, and a batch makes a fixed
   number of calls whatever its size. Background refinement is again the
   largest stage, and its remaining cost is the wavelet bank and sigma
   clipping themselves, which are already vectorised SciPy.
2. **Per-pixel background refinement.** Still 13 to 18% after its batch size
   was corrected. The remaining cost is the wavelet bank and sigma clipping
   themselves, which are already vectorised SciPy.
3. **The driver's whole-plane reads.** M2's own row; it governs the envelope
   rather than the clock, but it also removes the largest remaining copies.
4. **`fit_compact_gaussian_mixture`.** The genuine nonlinear fit, about 35%
   of the fitting stage and 5 to 8% of a run. It is already a compiled SciPy
   least-squares solve.

## What scales with the tile, and what with the image

With 2,048-pixel cores every image the public envelope admits is exactly one
tile, so a profile inside the envelope cannot tell tile-bounded state from
image-bounded state: a core and a plane are the same array. The ladder
therefore carries a 4,096-pixel pair, the smallest images holding more than
one core.

| case | megapixels | peak RSS | MiB per megapixel |
| --- | --- | --- | --- |
| dense 2,048² | 4.19 | 1,581 MiB | 377 |
| dense 4,096² | 16.78 | 2,264 MiB | 135 |
| empty 4,096² | 16.78 | 2,458 MiB | 147 |

Quadrupling the area raises peak RSS by half, not fourfold, and the cost per
megapixel collapses once the image passes one tile. Above that point the fit
is about **1.3 GB fixed and tile-bounded plus 62 MiB per megapixel**, which
is roughly six to eight live whole planes: the driver's `ImageBounds(0, H,
0, W)` reads and the products.

!!! warning "Do not extrapolate from inside the envelope"

    Fitting the slope below 2,048 pixels gives about 350 MiB per megapixel
    and predicts 83 GB at LoTSS-DR3 15,402². That is five times too high,
    because in that regime the tile grows with the image. The slope above
    one tile predicts about 16 GB there and 32 GB at 22,500².

## Cost model

The complete-path profile fits generated cost as
`fixed + a·megapixels + b·components + c·megapixels·components`. The
17 September fit, before this work, was
`11.6 s/Mpx + 25 ms/component + 4.3 ms/(Mpx·component)`, against
`18.6 + 49 ms + 47 ms` at the start of M1. Refit it with
`just profile-execution` after any change that moves a size or density tier.
