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
just traced-peak --tier large --repetitions 2
```

The profiler runs every case in a fresh single-thread process, and a second
time under `cProfile` when asked. It writes per-stage wall time and the
`cProfile` statistics under `benchmark-results/profiles/runs/<label>`. A
profile ranks costs; only the quick benchmark establishes a speedup, and only
`just traced-peak` establishes what a run allocates.

!!! note "Sizes above the public envelope"

    `find_sources` refuses an image wider than 3,000 pixels with
    `SourceFinderImageTooLargeError`. The profiler and the quick benchmark
    raise that limit deliberately so the size ladder can be measured ahead
    of the envelope. A 4,096-pixel figure on this page is a measurement, not
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

1. **Per-pixel background refinement.** Still 13 to 18% after its batch
   size was corrected, and again the largest stage now that no per-source
   Astropy call remains. The remaining cost is the wavelet bank and sigma
   clipping themselves, which are already vectorised SciPy.
2. **`fit_compact_gaussian_mixture`.** The genuine nonlinear fit, about 35%
   of the fitting stage and 5 to 8% of a run. It is already a compiled SciPy
   least-squares solve.

## What scales with the tile, and what with the image

With 2,048-pixel cores, 2,048² is the last single-tile size. Every image
the envelope admitted before 22 September 2026 was one tile, so a profile
inside it could not tell tile-bounded state from image-bounded state: a core
and a plane were the same array. The ladder therefore carries a 4,096-pixel
pair, the smallest generated images holding more than one core, and the
envelope now reaches 3,000, which is four.

| case | megapixels | peak RSS | MiB per megapixel |
| --- | --- | --- | --- |
| dense 2,048² | 4.19 | 1,581 MiB | 377 |
| dense 4,096² | 16.78 | 2,264 MiB | 135 |
| empty 4,096² | 16.78 | 2,458 MiB | 147 |

Quadrupling the area raises peak RSS by half, not fourfold, and the cost per
megapixel collapses once the image passes one tile. Read those three figures
as an envelope, not as measurements: they are RSS, and the warning below
applies to them.

Counting the arrays is the reliable way to size what grows with the image,
and the count is measured rather than read off the source: a run walks the
driver's own locals at the terminal builder and counts the distinct
image-shaped arrays reachable from them. There are **none**. The count was
18 at 49 bytes a pixel — 8 `int32` label planes, 9 masks and the position
signal in `float64`, which would have been 0.41 GiB at 3,000², 4.6 GiB at
10,000² and 10.8 GiB at LoTSS-DR3 15,402² against 18 GiB of
development-machine memory. Nothing outside a tile scales with the image
now, so what is left to measure is the tile working set, which the next
envelope tier reports.

The image, the background, the RMS and their residual are all out, and **the
driver now reads no window at all**: the final RMS product streams one
canonical tile row at a time rather than validating a whole plane in memory,
each direct component's association record is built by the fit parent that
already reads its residual, each catalogue row's local noise is measured by
the row round that already reads its window, and the detection islands are
reconciled and measured by a round of their own. Objects are read a batch at a
time inside those rounds under the owner read budget: the residual is
assembled from storage chunks far larger than one object, so one read per
object decodes the same chunks again for every neighbour sharing them, which
measured 5.5× slower at 111 components and 8.2× at 846.

Moving the component records and the owner noise into the passes changed the
clock by a few tens of milliseconds, which is itself the finding. On the
1,024² dense LoTSS cut-out, with 111 components and 83 sources, the driver
spent 0.058 s describing components and 0.027 s collecting owner noise in a
13.5 s profiled run; inside the passes the same work is 0.019 s and 0.005 s,
and the row round's read grows by 0.055 s because it now reads the RMS window
too. Those rounds were never the 8% of wall time the whole-plane removal cost
at this size: that sits in the store's per-read overhead, and only reducing it
recovers the trade-off.

The island round is the one whose move is visible on the clock, because the
driver was labelling a whole plane to find its objects. It scales with the
image rather than with a tile, so the gain grows with size: a real 3,000²
LoTSS field with 814 islands went from 216.4 s to 201.7 s under tracing, about
7%, while its products stayed bitwise identical.

The background stage was the change that moved the peak, which sits in the
multiscale pass rather than in anything the catalogue does: returning two
`bool` masks where three `float64` estimates had been took it down by
197 MiB at 3,000² across three steps, within 1 MiB of the 198 MiB the
array arithmetic predicted. That difference, like the two below, was taken
with an ad-hoc harness before `just traced-peak` existed; a difference of
one harness's figures holds, but its levels are not comparable with the
table further down. The stage now returns neither, only whether any
pixel has a usable local noise estimate, reduced one tile row at a time, and
the label, mask and position-signal planes followed it out.

Removing the driver's 49 bytes a pixel moved the peak by 2 of them, and that
is the lesson rather than a disappointment: only the planes alive at the peak
can lower it, and the peak is in the multiscale pass, before the catalogue
work allocates the other 47. What the peak does see is the two background
masks, and it sees them exactly — 342.04 → 339.98 MiB at 1,024² and
1261.45 → 1244.22 MiB at 3,000², against arithmetic of 2.00 and 17.17 MiB.
The 47 bytes show in the envelope instead: they are what the image would have
added on top of the tile, 4.6 GiB of it at 10,000².

The same removal is worth 4 to 7% of the clock at 1,024², because the checks
those planes were held for were whole-plane comparisons: medians of five on a
quiet machine give `dense-field` 9.3 s, `lotss-dr3-1312-sparse` 10.0 s and
`lotss-dr3-1312-dense` 11.1 s, ratios 0.96, 0.93 and 0.94 against v0.13.0.

## What a run allocates

`just traced-peak` measures it: `tracemalloc` in a fresh single-thread
process, on the quick benchmark's own inputs and settings, writing one
`TracedAllocationEvidence` record per case. It is the only committed way to
produce the figure the envelope gate uses, and it stays out of the timing
path, because tracing roughly doubles wall time.

A peak means nothing without the span it covers, so every repetition reports
three figures: the **process peak**, traced from before Hebog is imported; the
peak of the **`find_sources` call** alone; and the **import floor**, what the
imported modules still hold when that call begins.

Measured at `0.13.0` (`d70bb56`), two repetitions of each case, in
`benchmark-results/traced-peak/runs/admitted-tiers-20260925b` and, for the
512² case, `admitted-tiers-20260925b-smoke`:

| case | pixels per side | traced peak | components |
| --- | --- | --- | --- |
| generated compact ladder | 512 | 225.2 MiB | 5 |
| generated dense field | 1,024 | 431.5 MiB | 57 |
| LoTSS-DR3 sparse | 1,024 | 431.8 MiB | 61 |
| LoTSS-DR3 dense | 1,024 | 432.4 MiB | 108 |
| SDC1 crowded | 1,024 | 433.9 MiB | 794 |
| SDC1 crowded | 2,048 | 1,320.4 MiB | 3,110 |
| LoTSS-DR3 dense | 3,000 | 1,351.7 MiB | 828 |

The process peak fell inside the `find_sources` call in every case, so the
first two spans coincide. Three things in the table matter more than the exact
figures.

**Image size governs the peak, not source count.** At 1,024² the crowded SDC1
field carries 14 times the components of the generated dense field for 2.4 MiB
more. What grows with the image is the planes; what grows with the catalogue is
bounded.

**The peak crosses the tile boundary almost flat.** From 1,024² to 2,048² it
triples; from 2,048² to 3,000² it adds 2.4%, although the area more than
doubles. 2,048² is the last size every stage outside background and RMS runs as
one tile, so tile-bounded state is image-bounded state there, and at 3,000² the
same stages run four tiles.

**The import floor is fixed.** It was 90.4 MiB in every case from 512² to
3,000², so it is 40% of a 512² run and 7% of a 3,000² one. A tracer started
after the imports cannot see that floor and reports a peak lower by its size.

!!! warning "Peak RSS is an envelope, not a threshold"

    Ten runs of identical code at 3,000² gave peak RSS from 1,559 to
    2,477 MiB, a 42% spread, and the variation tracked machine load rather
    than the code: `ru_maxrss` is the high-water mark of *resident* pages,
    so it records how aggressively the operating system reclaimed as much as
    what Hebog demanded. Quote it as a range, and never gate a change on it.

    The traced peak is what a scaling claim or a tier gate uses. Each figure
    above repeated across its two runs to between 0.6 and 6.9 KiB — not to the
    byte, because the strings, paths and metadata of one run allocate slightly
    differently in the next, which is why repetitions count as agreeing within
    a tenth of a mebibyte. Traced evidence records peak RSS beside the peak,
    but tracing inflates it too, so read it only as an envelope.

!!! warning "Quote only what `just traced-peak` measured"

    Traced peaks quoted before `just traced-peak` existed came from ad-hoc
    scripts that were never committed, so the span each covered is unknown
    and none can be reproduced: 2,144, 1,347, 1,342, 1,261.39 and 1,244 MiB
    were all quoted for 3,000², and 1,539.3 MiB before the background-mask
    change. The table above replaces them. The 1,261.39 MiB is explained:
    1,351.7 MiB less the 90.4 MiB import floor is 1,261.3 MiB, so that
    harness traced the finder call and not the imports. `LOG.md`,
    25 September 2026, records which harness produced which number.

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
`18.6 + 49 ms + 47 ms` before the bottleneck work began. Refit it with
`just profile-execution` after any change that moves a size or density tier.
