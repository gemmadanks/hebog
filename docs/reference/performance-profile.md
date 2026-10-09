---
tags:
  - performance
---

# Where Hebog spends its time

This page records what the complete-path profile and the traced-allocation
harness measure, so that an optimization starts from evidence. Stage shares
are from the 21 September 2026 profile of the tile-native composition and
memory figures from 26 to 30 September, both with `SerialExecutor` on the
maintainer's machine. The gates are in the
[performance and scalability contracts](performance-scalability-contracts.md),
the current position is on
[progress against goals](progress-against-goals.md), and the dated narrative
of each change is in `LOG.md`.

## Reproduce it

```bash
just profile-execution --label my-profile --cprofile
just quick-benchmark --tier large
just traced-peak --tier large --repetitions 2
```

A profile ranks costs; only the quick benchmark establishes a speedup, and
only `just traced-peak` establishes what a run allocates. All three raise the
15,402-pixel public limit deliberately so the next tier can be measured
before it is admitted: a figure above 15,402 pixels here is a measurement,
not a supported size.

!!! warning "Measure on a quiet machine"

    Runs taken at load average 4 to 7, with an endpoint-security scanner at
    half a core, disagreed by up to 7% on the 1,024-pixel cases. Check the
    load average before quoting a ratio, and compare only endpoints measured
    in the same session.

## What dominates

Self wall time as a fraction of the complete run:

| Stage | dense 1,024² | SDC1 crowded 1,024² | SDC1 crowded 2,048² |
| --- | --- | --- | --- |
| Per-pixel background refinement | 18% | 13% | 13% |
| Catalogue row measurement | 13% | 19% | 18% |
| Per-parent moments and fitting | 16% | 17% | 15% |
| Multiscale filters and labelling | 5% | 2% | 6% |
| Source association and catalogues | 2% | 6% | 6% |
| Per-parent deblending | <2% | 1% | <1% |

The profile is flat: the largest stage is about a fifth of a run and the
largest single kernel, `fit_compact_gaussian_mixture`, is 5 to 8%, already a
compiled SciPy least-squares solve. Nothing reaches the
[native-code assessment](../explanation/native-code-assessment.md)'s 10%
gate. Every bottleneck removed so far was redundant work rather than slow
work: a whole-core scan per label, store metadata probes that always missed,
a protection halo refiltered per cell block, a plane decoded once per sixteen
objects and a coordinate transform per source. Together they took the
crowded 2,048² case from 323.5 s to 153.1 s. What the store still costs is
intrinsic to its policy: one chunk decode and checksum per window read, and
one atomic file per written chunk.

The next gains are structural rather than kernel-level. On large fields about
half the run is background and RMS, and source association grows faster than
the image (1, 82 and 479 s for 659, 7,146 and 16,084 sources, about the 2.2
power); the plan's tasks 54 to 56 address both.

The generated-ladder cost model is
`fixed + a·megapixels + b·components + c·megapixels·components`; the last
fit was `11.6 s/Mpx + 25 ms/component + 4.3 ms/(Mpx·component)`. Refit it
with `just profile-execution` after a change that moves a size or density
tier.

## What a run allocates

`just traced-peak` measures `tracemalloc`'s peak in a fresh single-thread
process on the quick benchmark's inputs and settings. Every repetition
reports the process peak (traced from before Hebog is imported), the peak of
the `find_sources` call alone and the import floor, a fixed 90.4 MiB that a
tracer started after the imports cannot see. Measured 26 to 30 September
2026, two agreeing repetitions each, and the whole mosaic once more in the
0.19.0 release check of 8 October (`LOG.md` names the runs):

| case | pixels per side | traced peak | components |
| --- | --- | --- | --- |
| generated compact ladder | 512 | 224.7 MiB | 5 |
| generated dense field | 1,024 | 429.5 MiB | 57 |
| LoTSS-DR3 sparse | 1,024 | 429.8 MiB | 61 |
| LoTSS-DR3 dense | 1,024 | 430.3 MiB | 108 |
| SDC1 crowded | 1,024 | 431.8 MiB | 794 |
| SDC1 crowded | 2,048 | 1,312.4 MiB | 3,110 |
| LoTSS-DR3 dense | 3,000 | 1,334.6 MiB | 828 |
| LoTSS-DR3 dense | 10,000 | 1,489.2 MiB | 9,259 |
| generated wide objects | 10,000 | 1,447.7 MiB | 10 |
| LoTSS-DR3 whole mosaic | 15,402 | 1,698.2 MiB | 20,661 |
| LoTSS-DR3 whole mosaic, 0.19.0 release check (one repetition) | 15,402 | 1,692.5 MiB | 20,792 |

Three things matter more than the exact figures.

**Within one tile, image size governs the peak, not source count.** At 1,024²
the crowded SDC1 field carries 14 times the components of the dense generated
field for 2.3 MiB more.

**The peak crosses the tile boundary almost flat, then grows slowly with the
image.** With 2,048-pixel cores, 2,048² is the last single-tile size for
every stage outside background and RMS; from 2,048² to 3,000² the peak adds
1.7% although the area more than doubles. Above one tile the peak is one
multiscale tile task, a flat 1,247 MiB, plus what the pass keeps across
tiles, which grows about 1.7 bytes a pixel: the tile summaries' per-label
records (every candidate island, with no size cut), the per-tile island
summaries and the reconciled label mappings, 112, 262 and 489 MiB at the
three LoTSS sizes. At that slope the peak would be near 2.1 GiB at 22,500²
and 4.3 GiB at 45,000². Background and RMS, which peak lower, grew about 3
bytes a pixel (274, 545 and 962 MiB), unattributed on a real image; on
synthetic grids the local-noise requests account for about 1.9 of it. The
plan's tasks 53 to 56 bound these terms before the next tier, and
`scripts/benchmark/attribute_traced_peak.py` attributes a peak to passes,
tasks and call sites.

**No image-sized plane lives on the driver.** A run counts the distinct
image-shaped arrays reachable from the driver's locals at the terminal
builder, and there are none; before the tile-native object pass there were
18, at 49 bytes a pixel. The driver's only reads are the final RMS and mask
products, streamed one tile row at a time.

### The declared exception

An object wider than a task's read budget is measured from the cores that
hold it, and in the island, deferred-fit and catalogue-row rounds those cores
return the object's own pixels, which the driver joins in raster order. On a
synthetic 10⁶-pixel object that costs 81 bytes an object pixel for an island
row, 121 for a deferred parent's component records and 186 for a catalogue
row, with no cap on a segment's size: a field-filling object would put about
1.7 GB on the driver at 3,000², 19 GB at 10,000², 44 GB at 15,402² and 1.9 TB
at 100,000². The one measured case, the `wide-objects-10000` filament of
553,817 pixels, cost about 100 MB, below the multiscale peak. No real
LoTSS-DR3 object comes within a factor of ten of the budget, and a smooth
object wider than the 150-pixel background box is absorbed by the background
estimate, so what can reach the driver is connected structure narrower than
the box. ADR-008 declares the exception; removing it is deferred work in the
plan, reopened when a tier's traced peak shows the term or when the cluster
benchmark is planned.

!!! warning "Peak RSS is an envelope, not a threshold"

    Ten runs of identical code at 3,000² gave peak RSS from 1,559 to
    2,477 MiB, a 42% spread that tracked machine load: `ru_maxrss` records
    how aggressively the operating system reclaimed pages as much as what
    Hebog demanded. Quote it as a range and never gate a change on it. The
    traced peak repeats to between 0.2 and 12.6 KiB, which is why
    repetitions count as agreeing within a tenth of a mebibyte.

!!! warning "Do not extrapolate from inside the envelope"

    Fitting the slope below 2,048 pixels gives about 350 MiB per megapixel
    and predicts 83 GB at 15,402², because in that regime the tile grows
    with the image. The whole mosaic traces 1.7 GiB. Project only from
    traced peaks across admitted tiers, and treat a linear projection as a
    floor. Peaks quoted before `just traced-peak` existed came from ad-hoc
    scripts whose span is unknown; the table above replaces them.
