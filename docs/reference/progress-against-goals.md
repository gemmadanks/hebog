# Progress against goals

How far Hebog is from the 1.0.0 goal its
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines. Last updated on **13 November 2026**, after 0.25.0's release check.
Every figure is dated development evidence from the maintainer's machine,
traceable to its run; none is scientific qualification. User-facing limits
are in [capability and status](release-status.md).

## At a glance

| Goal for 1.0.0 | Where it stands | Status |
| --- | --- | --- |
| **Telescopes:** FITS continuum images from any telescope under a documented header contract, validated on LOFAR and SKA-Mid | The [input header contract](input-header-contract.md) is defined and tested. LOFAR (LoTSS-DR2 and DR3) and SKA-Mid (SDC1) images run, and MeerKAT MIGHTEE images fit the envelope. Beams wider than 10 pixels are refused; real Rapthor images have at most about 7. SKA-Low precursor data (GLEAM-X) needs the later 45,000-pixel tier. | In progress |
| **Functionality:** a feature-flagged backend for Rapthor's `filter_skymodel` step | All 12 frozen public behaviours are implemented under the Serial, Thread and Dask executors. The Rapthor adapter writes the files Rapthor's step reads, and Rapthor's Hebog branch calls it, with a PyBDSF fallback and dual runs. | On a Rapthor branch; not merged |
| **Science:** a truth-based gate on what Rapthor keeps, and a held-out parity study against pinned PyBDSF `master` | Rapthor's profile (`continuum` with a zero background) passes the truth-based gate: it loses 0.10% of the real components `master` keeps and finds a third as many false islands. Isolated-source position, flux and shape limits are met. Two bounded differences and one open defect remain. | Development evidence only |
| **Performance:** the finder part of Rapthor's step at most 0.50 of `master`'s time on dense sectors (provisionally 10,000 sources or more) and at most 1.05 on the rest, on one node and across nodes | Measured, it fails: on Rapthor's current thread path Hebog takes 2.26 times `master`'s time on the dense cell; on single-threaded Dask workers about 1.07 on the dense cell and 1.74 on the sparse one. Projected, 0.25.0 on Dask workers meets every limit on one cluster node (0.30 on the dense cell, 0.52 to 1.03 on sparse sectors), provided `master` uses only four cores of a dense sector's node. | Dense gate and parity failing |
| **Scalability:** 22,500² images for 1.0.0, and one sector across 1 to 10 nodes with identical products | 22,500² is admitted (19 October). Products are identical across tilings and executors. Nothing has run beyond one machine. | Size met; cluster not run |
| **Release:** PyPI, with portability, security, licensing, documentation and independent acceptance, under a 1.x compatibility policy | v0.25.0 (9 November) is on PyPI with attestations; its release check left catalogue, RMS and mask unchanged from 0.24.0. CI covers Linux, macOS and Windows on Python 3.12 to 3.14. | Experimental `0.x` |

## Blockers and next steps

The largest risks to 1.0.0 are:

- the performance gap ([below](#performance));
- memory that grows with the image and the sources found;
- the development machine's memory, disk and container VM;
- upstream churn;
- three steps outside the agent's control: cluster time, Rapthor's worker
  layout and independent reviewers.

The plan's
[decisions pending](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#decisions-pending)
list what the maintainer has still to decide, each with a recommendation.
The next actions, as the plan orders them:

1. **Agent:** the next increment of one sector across the cluster, in the
   order the model's checkpoint sets. The first increment, which sizes tiles
   and task counts from the core budget, is in 0.25.0.
2. **Human:** take the model's checkpoint (the dense threshold, the targets,
   the order of the increments and whether per-source costs join them); push
   Rapthor's Hebog branch; file the Astropy report (drafted 5 October) and
   the PyBDSF report (drafted 20 October); take the other pending decisions.
3. **Agent:** the deployment envelope, the matched benchmarks, the store and
   planner work, and packaging for the cluster benchmark, where the gate is
   measured. The varying-PSF measurement waits unless an output is confirmed
   incorrect.

## Functionality

The 12 frozen public behaviours in
`config/contracts/phase-0-public-behaviours.json` each name the test that
holds them. An unimplemented one would be a strict xfail, so CI fails the
day it starts passing.

| Behaviour | Status |
| --- | --- |
| A valid request returns versioned catalogue, RMS, mask, diagnostics and timing records | Implemented |
| An empty image succeeds with zero sources and valid empty products | Implemented |
| Invalid beam, WCS, unit or dimensional metadata fails before any result is written | Implemented |
| Raising a threshold cannot create a source | Implemented |
| Tile shape, worker count, completion order and batch size do not change the products | Implemented |
| No worker holds a complete large plane, and admitted memory bounds the peak | Implemented: every task declares its memory and none holds more |
| Rapthor adapter products for the true-sky and flat-noise pair | Implemented |
| Retry reuses valid stage products | Implemented |
| Worker loss is retried to the same products | Implemented |
| Rapthor can fall back to pinned PyBDSF behind the feature flag | Implemented, also when Rapthor's worker cannot hold the analysis |
| Dual-run mode keeps products separate and reports differences | Implemented on Rapthor's Hebog branch |
| A cancelled analysis stops its tasks and removes its staging | Implemented under the Thread and Dask executors |

`hebog.adapters.find_sector_sources` runs one Rapthor sector on the
caller's executor and writes Rapthor's four files.
[Rapthor's Hebog branch](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/rapthor-integration/README.md)
runs it as a native task on today's worker layout; its distributed path is
planned. At the pins of 17 October (Rapthor `aff26023`, LSMTool `156ae6a`)
with Hebog 0.22.0 from PyPI, the integration container passes 39 native and
CLI tests and the broader native suite 94, and Rapthor's own suites pass 662
([integration evidence](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/rapthor-integration/integration-summary.json)).

Rapthor's catalogue cuts (`DC_Maj`, `E_RA`, `E_DEC`) pass a `continuum`
source of one Gaussian, but a source of several components leaves those
columns empty, so the cuts drop it: 151 to 168 sources that `master` keeps on
the agreement check's cases.

## Science

### Gates

The binding reference is pinned PyBDSF `master` (`c70103b`); released 1.14.1
is checked once before 1.0.0. The limits are the plan's
[scientific gates](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#scientific-gates).

| Measurement | Target | Latest | Date and source |
| --- | --- | --- | --- |
| Rapthor retained/rejected components | Real components `master` keeps lost ≤1% overall and ≤2% per stratum; injected sources kept ≥ `master`'s share less 5 points from 6σ, all from 10σ; false islands on negated images ≤1% | `continuum` passes under either background (0.10 to 0.20% lost, 0.15 to 0.20% false islands). `compact` with a zero background fails (5.3% lost on extended sources, 3.8% at edges, 1.03% false islands). [Details below](#rapthor-profile-agreement) | 18 October, `just rapthor-agreement` run `cap3` |
| Reference recovery at SNR ≥10 | ≥99% | 1.000 on every generated case with compact truth, 0.998 on the crowded field | 9 October, quick check `release-0.19.0-rc2` |
| Isolated SNR ≥10 position, median / p95 | ≤0.02 / 0.10 beam | 0.0003 / 0.0005 (`continuum`), 0.0002 / 0.0006 (`compact`) | 6 October, equivalence lane |
| Isolated SNR ≥10 peak flux, median / p95 | ≤2% / 5% | 0.17% / 0.21% (`continuum`), 0.04% / 0.13% (`compact`) | same |
| Isolated SNR ≥10 `Total_flux`, median / p95 | ≤5% / 10% | 0.09% / 0.51% | 5 October, equivalence lane |
| Component fitted axes, median / p95 | ≤5% / 10% | 0.12% / 0.21% | same |
| `Total_flux` bias against `master`, paired upper 95% bound per stratum | ≤ +1 point in median and p95 | Median −0.1 to 0.0, p95 −3.5 to +0.1 points at SNR 10, 20 and 50 | 5 October, `m1-flux-calibration.json` |
| Position-uncertainty calibration | Pull standard deviation 1 | 1.015 and 1.006 on beam-correlated noise | 24 September |
| Integrated-flux uncertainty calibration | Pull standard deviation 1 | 1.08 on beam-correlated noise; conservative (0.32 to 0.57) on white noise | 5 October |
| Source-free RMS difference, median / p95 | ≤2% / 5% | 1.95% / **5.46%** (`continuum`); 1.57% / 3.12% (`compact`) | 5 October, equivalence lane |

Two differences are bounded in the equivalence lane rather than gated, so a
change that moves either fails CI and has to be explained:

| Known difference | Measured | Target | Cause |
| --- | --- | --- | --- |
| `continuum` RMS tail | 5.46% at p95 | ≤5% | Local noise on 35-pixel windows scatters more than PyBDSF's 150-pixel box |
| Published mask | Recall 0.927, IoU 0.922; island IoU 0.909 median, 0.857 minimum | 0.99, 0.98; 0.99, 0.95 | The boundary rule trims 13 of the reference's 178 island pixels |

### Rapthor-profile agreement

Rapthor keeps a sky-model component where the finder's mask is set at its
position. `just rapthor-agreement` (run `cap3`, 18 October) compares each
finder with known truth and with pinned `master` over 20,369 components: the
quick check's cases with a `master` reference, a 3,000² LoTSS-DR3 window and
the ELAIS-N1 true-sky and apparent images at 2,048². A component is real when
it lies on the ideal mask of a generated image, or at least 7 times the
negative-pixel noise above zero on a real one.

| Measure | `compact`, zero | `compact`, estimated | `continuum`, zero (Rapthor's) | `continuum`, estimated | `master` | Released 1.14.1 |
| --- | --- | --- | --- | --- | --- | --- |
| Real components `master` keeps that the finder rejects | 0.84%; extended 5.3%, edge 3.8% | 1.49%; extended 9.0%, edge 4.3% | 0.10%; edge 0.5% | 0.20%; edge 0.5% | – | 0.03%; extended 0.3% |
| Injected sources kept at 6, 7 and 10σ | 76, 91, 100% | 78, 93, 100% | 78, 91, 100% | 77, 93, 100% | 76, 89, 100% | 76, 89, 100% |
| Injected flux, median ratio at 10, 20 and 50σ | 0.990, 0.986, 0.989 | 0.998, 0.992, 0.993 | 0.988, 0.986, 0.989 | 1.000, 0.992, 0.992 | 0.984, 0.976, 0.985 | 0.984, 0.976, 0.985 |
| Generated: ideal-mask pixels and flux covered | 0.49, 0.58 | 0.45, 0.48 | 0.94, 0.99 | 0.84, 0.96 | 0.61, 0.73 | 0.77, 0.90 |
| Negated real images: false islands | 126 of 12,207 | 121 of 12,296 | 25 of 12,508 | 19 of 12,659 | 79 of 12,389 | 76 of 12,333 |
| Real images: RMS >20% above, and below, the negative-pixel noise | 22.9%, 2.2% | 22.9%, 2.2% | 11.1%, 6.5% | 11.1%, 6.5% | 30.2%, 1.5% | 30.3%, 1.5% |
| Truth-based gate | Fails | Fails | Passes | Passes | Reference | Passes |
| Agreement with `master` (reported, not gated) | 92.2% | 91.0% | 91.4% | 91.1% | – | 99.3% |

- `continuum` is the most accurate finder measured. It covers 84 to 94% of
  the generated emission against `master`'s 61%, and its RMS reads close to
  the negative-pixel noise.
- `compact` trims bright emission from large islands and cuts sources at the
  image edge, and its RMS reads low often enough to find 1.03% false islands.
- The disagreement with `master` is on real LOFAR fields; the generated
  cases agree fully but for four. No finder reaches the former 99.5% agreement
  target, which released PyBDSF misses too, so it was replaced on 16 October
  by the truth-based gate.

### Quick science check

The everyday regression check: fixed cases, each compared with injected truth
and with pinned `master`, which also reports RMS error, mask recall and the
share of bright emission inside the mask, so a lost source shows even
without truth. Run `minimal-1` (18 October); a 22nd case, ELAIS-N1's central
2,048², has been added since. Completeness and reliability compare source
rows, so an object that one finder splits into several rows lowers them
without a source being missed.

| Case | Hebog sources | Completeness vs truth (SNR ≥10) | Reliability vs truth | Completeness vs `master` | Reliability vs `master` | Mask IoU vs `master` | Bright emission in mask |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `compact-snr-ladder` | 5 | 1.000 | 1.000 | 1.000 | 1.000 | 0.949 | 1.000 |
| `close-blends` | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.976 | 1.000 |
| `extended-gaussians` | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.923 | 1.000 |
| `filament-and-ring` | 9 | 1.000 | 1.000 | 0.500 | 0.889 | 0.955 | 1.000 |
| `edges-and-corners` | 7 | 1.000 | 1.000 | 1.000 | 1.000 | 0.933 | 1.000 |
| `negative-background` | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.541 | – |
| `invalid-pixels` | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.957 | 1.000 |
| `varying-noise` | 4 | 1.000 | 1.000 | 0.500 | 1.000 | 0.562 | 1.000 |
| `white-noise-snr-ladder` | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.861 | 1.000 |
| `dense-field` | 59 | 1.000 | 1.000 | 0.967 | 1.000 | 0.907 | 1.000 |
| `empty-noise` | 0 | – | 1.000 | 1.000 | 1.000 | 1.000 | – |
| `all-invalid` | 0 | – | 1.000 | – | – | – | – |
| `crowded-field` | 994 | 0.998 | 1.000 | 0.985 | 0.997 | 0.888 | 1.000 |
| `wide-extended-source` | 7 | 0.300 | 1.000 | 0.375 | 0.857 | 0.482 | 0.910 |
| `crowded-giant-source` | 299 | 0.941 | 0.955 | 0.967 | 0.970 | 0.463 | 0.921 |
| `sdc1-b2-1000h-sparse` | 573 | – | – | 0.933 | 0.972 | 0.816 | 1.000 |
| `sdc1-b2-1000h-crowded` | 874 | – | – | no `master` reference | – | – | 1.000 |
| `sdc1-b2-1000h-giant-source` | 343 | – | – | 0.669 | 0.895 | 0.301 | 0.443 |
| `sdc1-b2-1000h-bright-neighbour` | 225 | – | – | 0.889 | 0.996 | 0.756 | 0.999 |
| `lotss-dr3-1312-sparse` | 59 | – | – | 0.857 | 0.915 | 0.834 | 1.000 |
| `lotss-dr3-1312-dense` | 105 | – | – | 0.807 | 0.914 | 0.793 | 1.000 |

On the whole 22,500² LOFAR-HD ELAIS-N1 mosaic, `continuum` finds 94.0% of
the survey catalogue's 5,872 sources within 1.5″, and their median
integrated flux above 20σ is 0.999 of the survey's (18 October, run
`diagnostic-3`).

### Open scientific defects

- **Clipped RMS reads low (kept).** On noise alone it reads 1.6 to 3.9% low.
  Correcting it lowered completeness on every truth measure without a
  measurable gain in reliability, so it stays uncorrected (18 October).
- **Estimated background beside a giant source.** A crowded field's coarse
  background can subtract part of a giant source, so the mask loses a few of
  its components. The zero background Rapthor runs loses none (18 October).
- **Fixed meshes (deferred).** Beams wider than 10 pixels are refused;
  scaling the meshes with the beam would recover them up to 22 pixels, at
  about 2.5 times the local-noise cost.

## Performance

The gate compares the source-finding part of Rapthor's `filter_skymodel`
step, from the task's start to LSMTool's `filter_sources` call, with pinned
PyBDSF `master`. Matched runs use one x86-64 container under Rosetta, so only
the ratios are matched: Hebog 0.23.0 (`continuum`, zero background), Rapthor
`632f6211`, LSMTool `156ae6a`, PyBDSF `master` `c70103b`. The dense cell is a
deep ELAIS-N1 5,000² window where `master` finds 24,780 sources; the sparse
cell is a LoTSS-DR3 5,000² window with 2,469.

### Where the gate stands

| Run | Hebog / `master`, finder part | Date and source |
| --- | --- | --- |
| Dense cell, Rapthor's thread path, four cores, five measured runs | 2.26 [2.24, 2.28] against ≤0.50; complete step 2.03 | 22 October, run `step3-gate-elais-n1-deep-north-3600-5000` |
| Dense cell, single-threaded Dask workers on 1, 2, 4 and 6 cores, two runs each | 1.03, 1.08, 1.07 and 1.00 | 22 to 24 October, runs `step3-sweep-…-<cores>-cores` |
| Sparse cell, single-threaded Dask workers on 1, 4 and 6 cores, two runs each | 1.65, 1.74 and 1.72 against ≤1.05 (3.42 on the thread path) | 24 October, runs `step4-sweep-…-<cores>-cores` |
| Source-count ladder, thread path, four cores, two runs each | Sparse sectors 3.14 to 4.85; dense sectors 3.16 (14,126 sources) and 2.28 (24,780) | 20 and 21 October, runs `step3-ladder-<case>` |
| 10,000² anchor, where `master` finds 9,276 sources, four Dask workers, one run | 1.23 | 16 October, run `screening-10000` |

Brackets are one-sided 95% bounds. Both finders' products repeat byte for
byte, and Hebog's are identical on every worker count and on the thread path.
The thread path is slow because Python's interpreter lock serialises Hebog's
tasks: on the dense cell four threads finish 1.18 times faster than one,
while four single-threaded Dask workers finish 2.63 times faster.

### Projection to the cluster's nodes

A model fitted to these runs and to native profiles of 0.25.0 projects the
finder part on one 96-core node, with `master` on all of it as Rapthor runs
it (13 November, `scripts/benchmark/fit_scaling_model.py` run
`release-0.25.0`).

- **Hebog** takes its driver time plus, for each round of tasks, the larger
  of its task time shared over the cores and its longest task. On a node it
  nears its **floor**, driver time plus longest tasks: 132 s on the dense
  cell and 46 s on the sparse one at 0.25.0, against 190 s and 59 s at
  0.24.0.
- **`master`** uses at most four cores on dense sectors, as the dense cell's
  sweep shows, and every core on sparse ones. Container times convert to
  native ones by Hebog's measured factor of 2.08, assuming emulation slows
  both finders alike.

| Sector (`master`'s sources) | Limit | Hebog / `master`, one node | Hebog's floor, native: now, target |
| --- | --- | --- | --- |
| LoTSS-DR3 (2,469) | 1.05 | 0.83 | 46 s, 55 s |
| Deep ELAIS-N1, noise ×4 (3,847) | 1.05 | 1.03 | 47 s, 45 s |
| Noise ×3 (5,686) | 1.05 | 0.91 | 56 s, 61 s |
| Noise ×2 (9,744) | 1.05 | 0.52 | 70 s, 138 s |
| Noise ×1.5 (14,126) | 0.50 | 0.38 (0.72) | 89 s, 113 s (55 s) |
| The dense cell (24,780) | 0.50 | 0.30 (0.53) | 132 s, 218 s (117 s) |

In brackets: if `master` used every core of a dense sector's node. A floor
target is the largest floor that still meets the limit.

- On one node 0.25.0 meets every limit, the noise ×4 sector narrowly: its
  floor is 2 s above a target that is conservative by a few seconds. 0.24.0
  missed parity on three of the four sparse sectors (1.06 to 1.26).
- If `master` used every core of a dense sector's node, the two dense sectors
  would miss 0.50 (0.53 and 0.72).
- Extra nodes add little at 5,000²: twelve nodes take 0.01 to 0.04 off one
  node's ratio.
- Hebog's time on a node grows by 4.0 ms a source natively (6.2 ms at
  0.24.0), within the 4.6 ms target.
- The local data cannot decide how many cores `master` uses on a cluster
  node, whether emulation slows both finders alike, or how both scale to
  Rapthor's 17,000 to 20,000-pixel sectors.

### Hebog's own speed

Native runs, without PyBDSF. Ratios are medians of five alternating runs a
side, with 95% bootstrap bounds where given.

| Measurement | Latest | Date and source |
| --- | --- | --- |
| 0.25.0 against 0.24.0, quick benchmark at 1,024² | 1.01, 1.00 and 1.00, every upper bound within the 1.05 regression limit | 5 November, release check `release-0.25.0` |
| Serial anchors | 1,137 s at 10,000² (0.24.0: 1,138 s); 3,410 s on the 15,402² mosaic; 4,306 s on the 22,500² LOFAR-HD mosaic | 12 November; 29 September; 19 October, `tier-22500-anchor` |
| Four Dask workers against Serial | 0.38 at 10,000² (431 s); 0.63 on the 15,402² mosaic; products identical | 5 November, `release-check/0.25.0/matched`; 5 October |
| Tile cores sized to the task slots (in 0.25.0) | Dense cell 0.916 [0.910, 0.930] on four workers and 0.910 [0.890, 0.962] on six; sparse cell 0.974 and 0.951 | 4 November, runs `stack-*` |
| Object batches by estimated cost (in 0.25.0) | Dense cell 0.987 [0.975, 0.994] on four workers; longest component-fit task 32.5 to 19.3 s | 4 November, runs `stack-*` |
| Dense cell, stage profile | 1,176, 681, 447 and 380 s on 1, 2, 4 and 6 Dask workers, a serial share of 18%. Largest stages: component fits, the two background and RMS passes, the multiscale pass | 21 October, `just profile-scaling` run `step3-elais-n1-deep-north-3600-5000` |
| The whole dense 14,175² ELAIS-N1 sector, Serial | 2.0 h at 0.22.0, against 8.5 h on 11 October | 17 October, `lsmtool-check-elais-n1-t022-continuum-2` |

The [performance profile](performance-profile.md) has the stage shares and
memory figures.

## Scalability

| Measurement | Latest | Target |
| --- | --- | --- |
| Public envelope | 22,500 pixels a side (19 October) | 22,500² for 1.0.0; 45,000² locally and 90,000² on the cluster later |
| Traced allocation peak, Serial | 1,489 MiB at 10,000², 1,693 MiB at 15,402² (24 October) and 1,873 MiB on the whole 22,500² mosaic (19 October) | Bounded by the tile |
| Growth beyond one tile | About 3.6 bytes a pixel on the 22,500² mosaic, mostly the background's local-noise requests, now submitted in 64 MiB rounds; the new peak is not yet traced | Bounded before the 45,000² tier |
| Peak RSS | 10,000² anchor at 0.25.0: Serial 2,973 MiB (0.24.0: 2,855); largest Dask worker 2,283 MiB (0.24.0: 2,040), a trade-off accepted on 12 November. Whole 22,500² mosaic: 4,105 MiB Serial | – |
| Scratch disk | Up to 49 GiB for the whole 22,500² mosaic, about 100 bytes a pixel of uncompressed Zarr intermediates (19 October) | Shrunk before the 45,000² tier, which would need about 200 GiB |
| Tiling and executor invariance | Byte-identical products from one tile and the 11×11 grid, and under Serial, Thread and Dask, including the whole 15,402² mosaic | Exact |
| Memory admission | Every task declares its memory, and on the whole 22,500² mosaic every round's largest task holds at most 0.78 of its declaration (19 October) | Bounded by the tile |
| Analysis memory | About 142 MiB plus 42 KB a source and a few bytes a pixel, which `hebog.analysis_memory_bytes` states; every traced run held at most 0.76 of it (19 October). `hebog.expected_source_count` bounded the published count on all 21 cases it was checked on | Bounded before the 45,000² tier |
| Declared limit | An object wider than a task's read budget is reduced on the driver; no real LoTSS-DR3 object comes within a factor of ten of the budget | Deferred until a tier's traced peak shows it |
| Beyond one machine | Not run | The cluster benchmark |

## Engineering health

These guard against erosion; they do not establish parity or readiness.

| Check | Latest |
| --- | --- |
| Portable suite | 4,105 passed, 97.50% branch-aware coverage against an 80% floor (5 November, `just ci` in the 0.25.0 release check) |
| Equivalence lane | 39 tests, including `find_sources` against both PyBDSF references under both profiles |
| CI matrix | Linux, macOS and Windows on Python 3.12 to 3.14, plus lowest-dependency and container checks required on `main` |
| Architecture | Every layer's allowed imports are one tested table; Rapthor, Prefect and LSMTool are absent from the package, and Dask is confined to `executors/` and the excluded `validation/` |

## Keeping this page current

Update this page in the same change as the plan's current-state table: after
a release check, a gate run, a new quick-check baseline or a repaired defect.
Replace stale figures rather than adding to them, and record each figure's
date and run label; Git history keeps earlier figures. The figures come from
`just quick-science-check`, `just quick-benchmark`, `just traced-peak` and
`just test-equivalence`, described in [Contribute to Hebog](../how-to/index.md),
with evidence kept in versioned records or controlled storage.
