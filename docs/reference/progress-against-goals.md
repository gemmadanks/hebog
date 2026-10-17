# Progress against goals

This page answers one question: how far is Hebog from the goal its
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines for 1.0.0? It is updated whenever the plan's current state changes,
and was last updated on **17 October 2026** after the 0.22.0 release.
The scientific and performance measurements retain their original dates.
Every figure is development evidence from the
maintainer's machine, dated and traceable to versioned evidence and Git
history; none is scientific qualification. User-facing limits are in
[capability and status](release-status.md).

## At a glance

| 1.0.0 goal | Target | Position on 17 October 2026 | Status |
| --- | --- | --- | --- |
| Telescopes | Standard FITS continuum images from any telescope under a documented header contract, validated on LOFAR and SKA-Mid for 1.0.0 and on SKA-Low precursor data at the later release whose envelope admits it | The [input header contract](input-header-contract.md) is defined and tested. LOFAR (LoTSS-DR3 and LoTSS-DR2) and SKA-Mid (SDC1 simulation) images run; MeerKAT MIGHTEE images fit the envelope; the only SKA-Low precursor mosaic (GLEAM-X) needs the 45,000-pixel tier and a position-dependent PSF, whose effect is to be measured and documented. A beam wider than 10 pixels is refused; every real Rapthor image in the archived cluster runs is at most about 7 pixels, and only Rapthor's synthetic demonstration sector (30 pixels) exceeds the limit. | In progress |
| Functionality | A feature-flagged backend for Rapthor's `filter_skymodel` at pinned Rapthor and LSMTool revisions | A complete standalone finder under Serial, Thread and caller-owned Dask executors, and the in-process Rapthor adapter: `hebog.adapters.find_sector_sources` runs a sector's true-sky and flat-noise images on the caller's executor and writes the files Rapthor's `filter_skymodel` step reads, by default with the `continuum` profile and a zero background, the profile that passes the truth-based gate, and pinned LSMTool's `filter_sources` filters by its mask as the mask decides, on the LoTSS-Deep DR2 ELAIS-N1 pair: its central 5,000² under all three executors with byte-identical products, and the full 14,175² sector's serial products. All 12 frozen public behaviours are implemented. Rapthor's Hebog branch calls the adapter in-process with a ThreadExecutor, memory admission, typed PyBDSF fallback and dual runs, tested through its real Prefect task on a single-threaded Dask worker. | On a Rapthor branch; not merged |
| Science | A truth-based Rapthor retained/rejected gate, with limits set from the agreement check's truth measures, and a powered, held-out parity study against pinned PyBDSF `master` on LOFAR, SDC1 and MIGHTEE images inside the envelope | Isolated-source position, flux and axis limits are met against both PyBDSF references on the frozen input, for sources and components under both profiles; the `Total_flux` limits hold on independent realizations. Two bounded known differences and one open defect remain. Rapthor keeps or rejects alike with Hebog's mask and pinned `master`'s 92.1% of sky-model components under the `continuum` profile with a zero background, which Rapthor runs; released PyBDSF reaches 99.3%, so the former 99.5% target was retired on 16 October for a truth-based gate, whose limits were set on 17 October. `continuum` passes it under either background since the repair of its local noise in crowded fields: it loses almost none of the real components `master` keeps, keeps injected sources as often as `master` or more and covers more of the true emission. `compact` fails it: it loses 5.4% of `master`'s real extended components and 3.5% at image edges, and finds 1.03% false islands on negated images against `master`'s 0.64%. | Development evidence only |
| Performance | The source-finding part of Rapthor's `filter_skymodel` step, from the task's start to LSMTool's `filter_sources` call, ≤0.50 of pinned PyBDSF `master`'s, like for like on one node and across the nodes Rapthor deploys, for sectors up to the 1.0.0 envelope; the complete step reported beside it | The gate fails. On a 3,000² LoTSS-DR3 window with four cores (emulated x86-64), Hebog's finder part is 2.43 times `master`'s on Rapthor's thread path (162 s against 67 s; complete step 2.03) and 1.99 on four Dask workers in one repetition (171 s against 86 s); both burn about the same CPU, so four cores cannot pass the gate whatever the occupancy. On the 10,000² anchor with four Dask workers (16 October, one repetition) the finder part is 1.23 (1,249 s against 1,019 s; complete step 1.19), both finders keeping about three of four cores busy and Hebog using 11% more CPU; PyBDSF could not run the 15,402² mosaic in the 16 GB container VM. The dense 14,175² ELAIS-N1 sector took 8.5 h serially on 11 October, mostly in association; with the same settings it takes 2.0 h at 0.22.0, and 1.3 h under the `compact` default. On a local Dask cluster one sector takes 0.36 of one worker's time at four workers and 0.32 at six, with a 20% serial share; twelve threads are barely faster than one, and four Dask workers gain nothing on a 3,000² sector of four tiles. No regression on the Hebog curve. | Gate failing |
| Scalability | The 22,500² tier for 1.0.0, covering Rapthor's default sectors, with one sector scaling across 1, 2, 5 and 10 nodes with invariant products; 45,000² on the 18 GiB development machine and 90,000² on the cluster as later minor releases; planner bounds for 100,000² on 100 to 200+ nodes | Public envelope 15,402². Every stage runs tiled through the executor and products are byte-identical across tilings and executors. The traced peak is 1.7 GiB on the whole 15,402² mosaic and still grows about 1.7 bytes a pixel, which forecasts about 2.1 GiB at 22,500². Every task declares its memory, and the analysis's own records grow with the sources found, about 42 KB each. Bright regions are refined in bounded blocks, so the ELAIS-N1 deep field's central 5,000², where 951 bright candidates chain across the image, completes under four 4.5 GiB Dask workers. Nothing beyond one machine has run. | 15,402 of 22,500 pixels |
| Release | PyPI, with portability, security, licensing, documentation and independent acceptance, under a 1.x compatibility policy | v0.22.0 (17 October 2026) is the first release on PyPI, published with attestations; it passed its release check on 15 October and installs from PyPI on Python 3.12 and 3.14. Earlier releases are on GitHub and TestPyPI. CI runs on Linux, macOS and Windows for Python 3.12 to 3.14, and `main` requires the lowest-dependency and container checks. | Experimental `0.x` |

## Functionality

The 12 frozen public behaviours in
`config/contracts/phase-0-public-behaviours.json` each name the test that
holds them, and all 12 are implemented. A placeholder would be a strict
xfail, so CI fails the day one starts passing.

| Behaviour | Status |
| --- | --- |
| A valid request returns versioned catalogue, RMS, mask, diagnostics and timing records | Implemented |
| An empty image succeeds with zero sources and structurally valid empty products | Implemented |
| Invalid beam, WCS, unit or dimensional metadata fails before any result is written | Implemented |
| Raising a threshold cannot create a source | Implemented |
| Tile shape, worker count, completion order and batch size do not change the products | Implemented |
| No worker materialises a complete large plane and admitted memory bounds the peak | Implemented: every task declares its memory and none holds more |
| Rapthor adapter products for the true-sky and flat-noise pair | Implemented |
| Retry reuses valid stage products | Implemented |
| Worker loss is retried to the same deterministic products | Implemented |
| Rapthor can fall back to pinned PyBDSF behind the feature flag | Implemented: a refused sector leaves none of Rapthor's files, and Rapthor's Hebog branch also falls back when its worker cannot hold the analysis |
| Dual-run mode keeps products separate and reports differences | Implemented on Rapthor's Hebog branch; reports both filtered product sets and retains their originals |
| A cancelled analysis stops its tasks and removes its staging | Implemented, under the Thread and Dask executors |

`hebog.adapters.find_sector_sources` runs one Rapthor sector on the
caller's executor and writes Rapthor's four files. [Rapthor's Hebog
branch](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/rapthor-integration/README.md)
adds the native task on today's worker layout; its distributed path is
planned. The [integration evidence](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/rapthor-integration/integration-summary.json)
records the upstream audit, real Prefect/LSMTool/subprocess tests and the
frozen-field checkpoint under both profiles and background settings. At the
pins of 17 October (Rapthor `aff26023`, LSMTool `156ae6a`), the integration
container with Hebog 0.22.0 from PyPI passes 39 native/CLI tests; the broader
native/settings suite passes 94, with full branch-aware coverage of the new
native module, and Rapthor's library, operation and image-flow suites pass
662. Its parset defaults to the `compact` profile with a zero background. The 18-case
quick science check has no regressions and all 54 FITS products match the
previous baseline byte for byte. That
three-source smoke check did not decide the profile; the agreement check did, below.
The adapter's eight-column codec reads the catalogue `find_sources`
writes. A
`continuum` source of one fitted Gaussian publishes that Gaussian, so its
row passes the three cuts Rapthor applies (`DC_Maj`, `E_RA`, `E_DEC`), as a
`compact` row does; a source of several components leaves them empty,
which on the agreement check's cases dropped 151 to 168 sources pinned `master`
keeps. Under
`compact`, which Rapthor runs, every source is one Gaussian.

## Science

### Gates

The binding reference is pinned PyBDSF `master` (`c70103b`); released 1.14.1
is checked once before 1.0.0. The limits are the plan's
[scientific gates](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#scientific-gates).

| Measurement | Target | Latest | Date and source |
| --- | --- | --- | --- |
| Rapthor retained/rejected components | The truth-based limits of the plan's scientific gates: real components `master` keeps lost ≤1% overall and ≤2% per stratum; injected sources kept ≥ `master`'s share less 5 points from 6σ, all from 10σ; false islands on negated images ≤1% | `continuum` passes under either background: 0.11 to 0.13% lost, injected sources kept as `master` keeps them, 0.15 to 0.20% false islands. `compact` with a zero background fails: 0.81% lost overall but 5.4% on extended sources and 3.5% at image edges, and 1.03% false islands. Released 1.14.1 passes. Agreement with `master`, 92.1 to 92.6%, is reported, not gated; strata and causes are [below](#rapthor-profile-agreement) | 17 October, `just rapthor-agreement` run `t75-coverage-1` |
| Reference recovery at SNR ≥10 | ≥99% | 1.000 on every generated quick-check case with compact truth, 0.998 on the crowded field; the wide extended source's disc and knots are not fitted one by one (0.300), which this gate does not cover | 9 October, quick check `release-0.19.0-rc2` |
| Isolated SNR ≥10 position, median / p95 | ≤0.02 / 0.10 beam | 0.0003 / 0.0005 (`continuum`), 0.0002 / 0.0006 (`compact`) | 6 October, equivalence lane on the frozen 256² input |
| Isolated SNR ≥10 source and component peak flux, median / p95 | ≤2% / 5% | 0.17% / 0.21% (`continuum`), 0.04% / 0.13% (`compact`) | same |
| Isolated SNR ≥10 source `Total_flux`, median / p95 | ≤5% / 10% | 0.09% / 0.51% | 5 October, equivalence lane |
| Component fitted axes, median / p95 | ≤5% / 10% | 0.12% / 0.21% | same |
| `Total_flux` Hebog minus `master`, paired upper 95% bound per stratum | ≤ +1 point in median and p95 | Median −0.1, −0.2, 0.0 and p95 −3.5, +0.1, −0.1 points at SNR 10, 20 and 50, pooled over white and beam-correlated noise | 5 October, `m1-flux-calibration.json` |
| Position-uncertainty calibration (`E_RA`, `E_DEC`) | Pull standard deviation 1 | 1.015 and 1.006 on beam-correlated noise; unqualified on a real high-declination field | 24 September |
| Integrated-flux uncertainty calibration | Pull standard deviation 1 | 1.08 on beam-correlated noise; conservative (0.32 to 0.57) on white noise | 5 October |
| Source-free RMS difference, median / p95 | ≤2% / 5% | 1.95% / **5.46%** (`continuum`); 1.57% / 3.12% (`compact`) | 5 October, equivalence lane |

Two differences against both PyBDSF references are bounded in the
equivalence lane rather than gated, each by its measured value plus the quick
check's tolerance, so a change that moves one fails CI and has to be
explained:

| Known difference | Measured | Target | Cause |
| --- | --- | --- | --- |
| `continuum` RMS tail | 5.46% at p95 | ≤5% | Local-noise refinement on 35-pixel windows scatters more than PyBDSF's 150-pixel box |
| Published mask | Recall 0.927, IoU 0.922; matched island IoU 0.909 median, 0.857 minimum | 0.99, 0.98; 0.99, 0.95 | The mask is publication support: the boundary rule trims 13 of the reference's 178 island pixels |

### Quick science check

The quick science check is the everyday regression detector: 18 fixed cases,
each one realization, compared with injected truth and with pinned `master`
on the fields Rapthor consumes. Run `release-0.22.0` on 15 October 2026,
the release check of the 0.22.0 candidate `0aa1a829`, whose products are
byte-identical to the `t54` run in every case and whose metrics equal
the 9 October `release-0.19.0-rc2` baseline's to floating-point rounding.
Every generated case also reports the
RMS error and the mask recall over the injected emission at least three
times the noise (`truth.support_rms_error_p50`, `_p95` and
`truth.support_recall`). Completeness and
reliability
compare source rows; an extended object that one finder splits into several
rows lowers the figure without being a missed source.

| Case | Hebog sources | Completeness vs truth (SNR ≥10) | Reliability vs truth | Completeness vs `master` | Reliability vs `master` | Mask IoU vs `master` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `compact-snr-ladder` | 5 | 1.000 | 1.000 | 1.000 | 1.000 | 0.949 |
| `close-blends` | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.976 |
| `extended-gaussians` | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.923 |
| `filament-and-ring` | 9 | 1.000 | 1.000 | 0.500 | 0.889 | 0.955 |
| `edges-and-corners` | 7 | 1.000 | 1.000 | 1.000 | 1.000 | 0.933 |
| `negative-background` | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.541 |
| `invalid-pixels` | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.957 |
| `varying-noise` | 4 | 1.000 | 1.000 | 0.500 | 1.000 | 0.562 |
| `white-noise-snr-ladder` | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.861 |
| `dense-field` | 59 | 1.000 | 1.000 | 0.967 | 1.000 | 0.907 |
| `empty-noise` | 0 | – | 1.000 | 1.000 | 1.000 | 1.000 |
| `all-invalid` | 0 | – | 1.000 | – | – | – |
| `crowded-field` | 994 | 0.998 | 1.000 | 0.985 | 0.997 | 0.888 |
| `wide-extended-source` | 7 | 0.300 | 1.000 | 0.375 | 0.857 | 0.482 |
| `sdc1-b2-1000h-sparse` | 573 | – | – | 0.933 | 0.972 | 0.816 |
| `sdc1-b2-1000h-crowded` | 897 | – | – | no `master` reference | – | – |
| `lotss-dr3-1312-sparse` | 59 | – | – | 0.857 | 0.915 | 0.834 |
| `lotss-dr3-1312-dense` | 105 | – | – | 0.807 | 0.914 | 0.793 |

On the whole 15,402² LoTSS-DR3 mosaic 1312 the 0.19.0 candidate publishes
19,104 sources and 20,792 Gaussians (19,189 and 21,010 for 0.18.0); the
survey's PyBDSF catalogue has 22,420 sources and 28,559 Gaussians
(8 October, traced-peak run).

### Rapthor-profile agreement

Rapthor keeps a sky-model component where the finder's mask is set at its
pixel. `just rapthor-agreement` (run `t75-coverage-1`, 17 October, with
the repair of `continuum`'s local noise below) counts how often Hebog's
mask and pinned `master`'s decide alike, over every distinct pixel holding
a Gaussian centre that `master` or any lane fitted: 20,221 on the quick
check's cases with a `master` reference, a 3,000² LoTSS-DR3 window and the
ELAIS-N1 true-sky and apparent images at 2,048². Percentages agree;
grouping is the share of components both keep whose patch holds the same
components.

| Lane | All | Bright | Extended | Edge | Crowded | Sparse | True-sky | Apparent | Grouping |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `compact`, zero background | 92.6 | 99.2 | 91.1 | 92.0 | 91.1 | 93.7 | 91.9 | 92.0 | 0.969 |
| `compact`, estimated | 91.6 | 98.3 | 87.5 | 91.5 | 90.3 | 92.6 | 90.8 | 90.8 | 0.963 |
| `continuum`, zero background (Rapthor's) | 92.1 | 100 | 97.6 | 94.2 | 91.5 | 92.6 | 92.3 | 92.4 | 0.965 |
| `continuum`, estimated | 91.6 | 100 | 97.3 | 93.5 | 91.9 | 91.4 | 91.6 | 91.6 | 0.962 |
| Released PyBDSF 1.14.1 (control) | 99.3 | 100 | 99.0 | 100 | 98.6 | 99.9 | 99.3 | 99.3 | 0.999 |
| Components | 20,221 | 1,011 | 1,568 | 600 | 8,639 | 11,582 | 8,236 | 8,251 | |

Every lane agrees on the 3 masked components. The disagreement is on real
LOFAR fields: the generated cases agree fully but for `varying-noise`, the
dense and crowded fields and `wide-extended-source`. `continuum` agreed on
74% until 17 October: on the ELAIS-N1 deep field source protection left
17 of its 83,521 local-noise windows clear, and every other window took
the nearest clear one's estimate, so its RMS was a patchwork from 0.7 to
2.4 times the noise. A field whose clear windows reach fewer than half its
cells now keeps the unprotected estimate, as one with no clear window
did. On Rapthor's catalogue cuts, `continuum` drops 143 to 157 matched
sources `master` keeps because they have several components, and every
lane publishes `DC_Maj` 0 for 1,600 to 1,700 fits of 10″ or more, against
`master`'s 439, so 304 to 343 matched sources that `master`'s cuts drop
pass them as unresolved. No lane reached the former 99.5% target, which
released PyBDSF misses too, so it was retired on 16 October for a
truth-based gate, from which the maintainer chose `continuum` with a zero
background for Rapthor; `compact` with a zero background had been the
interim choice since 13 October.

Agreement with `master` is compatibility, not correctness, so the check
also measures every finder against known truth, in the same run. A
component is real when it lies on the ideal mask of a generated image or
at least 7 times the negative-pixel noise above zero on a real one;
nearer the 5σ threshold the finders' RMS estimates decide. Each level of
injected sources holds 90, 30 in each real image.

| Measure | `compact`, zero | `compact`, estimated | `continuum`, zero (Rapthor's) | `continuum`, estimated | `master` | Released 1.14.1 |
| --- | --- | --- | --- | --- | --- | --- |
| Real components `master` keeps that the finder rejects: all, and worst strata | 0.81% of 12,794; extended 5.4%, edge 3.5% | 1.40%; extended 9.0%, edge 4.0% | 0.11%; edge 0.5% | 0.13%; edge 0.5% | – | 0.02%; extended 0.2% |
| Injected sources kept at 6, 7 and 10σ | 76, 91, 100% | 78, 93, 100% | 76, 91, 100% | 74, 93, 100% | 76, 89, 100% | 76, 89, 100% |
| Injected flux, median ratio at 10, 20 and 50σ | 0.990, 0.986, 0.989 | 0.998, 0.992, 0.993 | 0.988, 0.986, 0.989 | 1.000, 0.992, 0.992 | 0.984, 0.976, 0.985 | 0.984, 0.976, 0.985 |
| Generated: components decided as the ideal mask decides, of 1,273 | 97.9% | 95.5% | 98.7% | 98.7% | 99.1% | 99.1% |
| Generated: ideal-mask pixels and flux covered | 0.64, 0.81 | 0.60, 0.76 | 0.94, 0.99 | 0.87, 0.97 | 0.76, 0.90 | 0.77, 0.90 |
| Generated: mask on no emission | 0.07% | 0.17% | 0.06% | 0.05% | 0.77% | 0.47% |
| Negated real images: false islands, of the islands on the originals | 126 of 12,207 | 121 of 12,296 | 25 of 12,448 | 19 of 12,583 | 79 of 12,389 | 76 of 12,333 |
| Real images: RMS more than 20% above, and below, the negative-pixel noise at components | 22.6%, 2.2% | 22.6%, 2.2% | 11.9%, 5.8% | 11.9%, 5.8% | 30.4%, 1.5% | 30.4%, 1.5% |
| Truth-based gate | Fails: extended, edge, false islands | Fails: overall, extended, edge, crowded | Passes | Passes | Reference | Passes |

`continuum` now passes the truth-based gate under either background and is
the most accurate finder measured: it loses almost none of the real
components `master` keeps, keeps injected sources as often as `master` or
more, covers 87 to 94% of the generated emission against `master`'s 76%,
finds a quarter of `master`'s false islands, and its RMS reads close to the
negative-pixel noise. `compact` still fails: its masks trim bright emission
from large islands (5.4% of `master`'s real extended components) and cut
sources at the image edge, and its RMS reads more than 20% low often enough
that it finds 1.03% false islands. The truth-based gate's limits, set on
17 October, are in the plan's
[scientific gates](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#scientific-gates).

### Open scientific defects

- **Clipped RMS reads low.** The clipped window RMS has no
  truncation correction: on noise alone it reads 1.6% low on white noise
  and 3.2 to 3.9% low on beam-correlated noise (7 October).
- **Fixed meshes (deferred).** Beams wider than 10 pixels are
  refused; scaling the meshes with the beam would recover sources to 22
  pixels at about 2.5 times the local-noise read.

## Performance

The matched `filter_skymodel` row measures the deployment gate on one
sector; everything else below is diagnostic.

| Measurement | Latest | Date and source |
| --- | --- | --- |
| Hebog / pinned `master`, matched `filter_skymodel`, finder part (the gate) and complete step | Finder part 2.43 (162.4 s against 66.9 s, three repetitions, bounds not yet computed for this phase); complete step 2.03 with one-sided 95% bounds 1.99 to 2.05, against the ≤0.50 gate: medians of 186.0 s and 91.6 s on a 3,000² LoTSS-DR3 window with 101,144 WSClean-like components, in Rapthor's two-pass mode on four cores. LSMTool's filtering 23.6 s and 24.5 s; CPU 211 s and 202 s; peak RSS 3.45 and 1.48 GB; Hebog's analysis reserved 5.9 GB. Hebog's serial stage profile of the window: background and RMS 25%, component fits 23%, multiscale pass 14%, association 5%. One x86-64 container under Rosetta, so only the ratio is matched | 13 October, `scripts/benchmark/measure_filter_skymodel.py` run `task23-first`; Rapthor `d0e7e148` with the Hebog task, LSMTool `9bac2f7`, Hebog 0.21.0 `compact`/zero |
| The same, Hebog on four single-threaded Dask workers (screening; the gate does not count it) | 3,000² window, one repetition: finder part 1.99 (171.0 s against 86.1 s), complete step 1.72, Hebog's CPU 371 s against 206 s on threads. 10,000² anchor (`lotss-dr3-1312-dense-10000`, 1,225,654 WSClean-like components), one repetition: finder part 1.23 (1,249 s against 1,019 s), complete step 1.19 (1,559 s against 1,311 s), LSMTool's filtering 307 s and 291 s, CPU 3,258 s and 2,923 s, peak RSS 6.5 and 12.9 GB; PyBDSF's subprocess failed on the 15,402² mosaic in the 16 GB VM | 16 October, runs `t022-dask-smoke` and `screening-10000`, Hebog `16228cf1` (the 0.22.0 candidate with the screening tooling) |
| Hebog / `master`, 1,024² quick-benchmark cases, Hebog on one native thread against `master` on four container cores | 5.21 (`dense-field`), 3.21 (LoTSS sparse), 2.69 (LoTSS dense); upper bounds 5.49, 3.36, 2.87 | 6 October, `pr-stack-2026-10-06-with-master` |
| The same ratio on larger fields | 0.88 on the crowded 2,048² SDC1 cut-out; 3.05 on the 3,000² LoTSS field, where both use the same CPU time | 26 September, large tier on a quiet machine |
| Hebog curve, 0.22.0 candidate against 0.21.0, same session | 0.96, 0.96, 0.99 at 1,024² (`dense-field`, LoTSS sparse, LoTSS dense), upper bounds 0.99, 1.03 and 1.03, all passing the ≤1.05 regression rule; `dense-field` and LoTSS dense were timed again alone after reading inconclusive 0.95 [0.77, 1.05] and 1.01 [0.95, 1.06], the first from v0.21.0's noisy repetitions (11.3 to 15.5 s) | 15 and 16 October, release check `release-0.22.0` and `release-0.22.0-inconclusive` |
| Absolute wall time, 1,024² cases, Serial | 10.6 to 14.4 s a run at loads of 2.4 to 4.5 | 15 and 16 October, release check |
| Serial anchors | 1,140 s at 10,000² against 1,259 s in the 0.19.0 release check; 3,410 s on the whole 15,402² mosaic (3,362 s in the 0.18.0 release check) | 15 and 8 October; 29 September and 5 October |
| Four-worker Dask against Serial | 0.41 at 10,000² (462 s) against 0.59 (741 s) in the 0.19.0 release check; 0.63 on the whole mosaic (2,116 s, 5 October); byte-identical products in every run | 15 and 8 October; 5 October |
| LoTSS-Deep DR2 ELAIS-N1, a dense deep field | 30,745 s Serial for 123,186 sources on the whole 14,175² sector, about 7.4 h of it after component fitting; on its central 5,000², 2,138 s Serial, 1,974 s on four threads and 1,871 s on two 9 GiB Dask workers, after four 4.5 GiB workers failed; with bright regions in bounded blocks (v23), 2,137 s Serial, 1,986 s on four threads and 1,543 s on four 4.5 GiB Dask workers, byte-identical; with coarser background batches and the linear hierarchy decision, under the `compact` default of 13 October (35,065 sources against 34,040), 1,126 s Serial and 523 s on four Dask workers, byte-identical; the whole sector with core-ordered object reads too, 4,652 s Serial for 118,929 sources against 30,745 s for 123,186. Like for like (`continuum`, estimated background), the whole sector at 0.22.0 takes 7,268 s Serial for 123,172 sources, 4.2 times faster than at 0.19.0, with identical RMS maps, 36 of 201 million mask pixels changed and LSMTool keeping the same 1,913 of 2,314 components. Of the 6.6-fold speed-up of 15 October, the code gives 4.2 and the `compact` default 1.6 | 10, 11, 15 and 17 October, `scripts/validation/check_lsmtool_filter.py` reports in `benchmark-results/lsmtool-check-elais-n1*` (`-central-5000-t55` at Hebog `17dbaeb8`, `-t54` at `222ff3b1`, `-t022-continuum-2` at `16228cf1`) |
| One sector across workers | Local Dask cluster of single-threaded workers, 16 GB task-memory budget: the 10,000² anchor takes 2,036, 1,107, 767 and 754 s on 1, 2, 4 and 8 workers and the 15,402² mosaic 5,032, 3,009, 2,097 and 2,101 s; 12 workers are refused (1.33 GB each against the multiscale tasks' 1.70 GB). Serial share 23% and 29% by Amdahl fit; eight workers swap 15 to 35 GB on the 18 GiB machine and their heaviest-reading tasks run five to seven times slower. One and twelve threads: 1,329 and 1,119 s, tasks 8.6 times slower under the global lock. Largest serial terms: background refinement's 69,150 small batches (164,704 on the mosaic), which under Dask each reopen the FITS file; the multiscale pass; catalogue rows; component fits; the driver's RMS FITS write (13 and 35 s). 213 GB decoded from Zarr and 19,373 chunk files a run at 10,000², 703 GB and 45,587 on the mosaic | 14 and 15 October, `just profile-scaling` run `task73-quiet`, `benchmark-results/profiles/runs/task73-quiet/scaling.json` (sha256 `6ac94088…`), Hebog `f514d067`; a repetition under memory pressure agreed within 3% |
| One sector, coarser background batches | The 10,000² anchor takes 1,423, 580, 515 and 596 s on 1, 4, 6 and 8 workers, 21 to 32% less than above; background takes 622 s instead of 1,235 s on one worker, in 780 tasks instead of 69,150. Over 1, 4 and 8 workers the serial term is 404 s against 478 s, a share of 29% against 24%, because the parallel work fell further. `find_sources`' driver work outside the profiled stages takes 70 s here and 320 s on the mosaic in the first sweep, at every worker count. The two-worker run (903 s) overlapped a burst of three to five cores in the Podman VM; eight workers swapped up to 22 GB | 15 October, `just profile-scaling` run `task74`, `benchmark-results/profiles/runs/task74/scaling.json` (sha256 `cdf0386d…`), Hebog `caedd2d4` |
| Linear hierarchy decision and reconciliation | One worker, with the coarser background batches beneath: the driver work outside the profiled stages, which holds the hierarchy decision, takes 16 s instead of 70 s on the 10,000² anchor and 50 s instead of 320 s on the whole mosaic. The mosaic takes 3,783 s instead of 5,032 s, in 22,057 tasks instead of 184,900, and no task runs for 6% of either run (83 s and 223 s). The mosaic's other stages ran up to 22% slower than the first sweep's overnight run on a busier machine; on the anchor, measured right after the coarser-batches run, they are unchanged | 15 October, `just profile-scaling` run `task55`, `benchmark-results/profiles/runs/task55/scaling.json` (sha256 `48a37e2b…`), Hebog `149ed8da` |
| One sector with coarser background batches and the linear hierarchy decision | The 10,000² anchor takes 1,357, 749, 490, 429 and 438 s on 1, 2, 4, 6 and 8 workers (speed-ups 1.81, 2.77, 3.16 and 3.10), 43% less than the first sweep at the best point. No task runs for 77 s at one worker and 67 to 70 s at more, against 349 s and 158 to 209 s in the first sweep; over 1, 4 and 8 workers the serial term is 263 s, a share of 20% against 24%. Eight workers swapped up to 24 GB; the Podman VM stayed idle | 15 October, `just profile-scaling` run `task74-stack`, `benchmark-results/profiles/runs/task74-stack/scaling.json` (sha256 `4c06424a…`), Hebog `17dbaeb8` |
| Object rounds a core at a time | One worker, with the two changes above beneath: the 10,000² anchor takes 1,305 s instead of 1,356 s and the whole mosaic 3,452 s instead of 3,790 s, decoding 154 GB from Zarr instead of 213 GB and 393 GB instead of 703 GB. On the mosaic the hierarchy overlap stage takes 73 s instead of 163 s and source labels 38 s instead of 65 s; the island round runs 32 more tasks for 12 s more. Products byte-identical | 15 October, `just profile-scaling` run `task54`, `benchmark-results/profiles/runs/task54/scaling.json` (sha256 `49525d36…`), Hebog `222ff3b1` |
| Profile shape | The largest stage is about a fifth of a run and the largest kernel 5 to 8%, so no kernel reaches the native-code assessment's 10% gate | 21 September |

About half of a large run is background and RMS estimation, and most of the
growth beyond image area is source association, whose hierarchy decision
is now linear and whose objects are read a core at a time. The [performance profile](performance-profile.md) has the stage
shares and the memory figures.

## Scalability

| Measurement | Latest | Target |
| --- | --- | --- |
| Public envelope | 15,402 pixels a side | 22,500² for 1.0.0; 45,000² locally and 90,000² on the cluster at later minor releases |
| Traced allocation peak, Serial | 430 MiB at 1,024²; 1,312 MiB at 2,048²; 1,335 MiB at 3,000²; 1,489 MiB at 10,000²; 1,692 MiB at 15,402² (one repetition each on 8 and 15 October, 0.1 MiB apart; 1,698 MiB in two agreeing repetitions on 29 September) | Bounded by the tile |
| Growth beyond one tile | About 1.7 bytes a pixel in the multiscale pass and about 3 in background/RMS; at those slopes about 2.1 GiB at 22,500² and 4.3 GiB at 45,000² | Bounded before the 45,000-pixel tier |
| Peak RSS | Whole mosaic: 3,101 MiB Serial; 2,531 MiB driver and 2,429 MiB largest worker under Dask; under the tracer 4,312 MiB on 15 October against 3,709 MiB on 8 October, within the spread peak RSS shows with machine load (up to 42% between identical runs), while the traced peak is unchanged. 10,000² anchor: 2,670 MiB Serial; 1,056 MiB driver and 1,838 MiB largest worker under Dask (15 October; an envelope, not a gate) | – |
| Tiling and executor invariance | Byte-identical products from one tile and the 8×8 grid, and under Serial, Thread and Dask, including the whole mosaic | Exact |
| Declared limit | An object wider than a task's read budget is reduced on the driver at up to 186 bytes an object pixel; about 44 GB for a field-filling object at 15,402². No real LoTSS-DR3 object comes within a factor of ten of the budget | Deferred; reopened when a tier's traced peak shows it |
| Memory admission | Every task declares its memory from its read: the multiscale tile tasks are the largest, 1,247 MiB traced for a 2,048-pixel core with its halo, and object batches reach 774 MiB on the whole mosaic. A memory budget narrows the in-flight window, and a `DaskExecutor` given the caller's resource names attaches each declaration to its task; on a local two-worker cluster that keeps a second task off a worker without the memory (12 October) | Bounded by the tile |
| Analysis memory | Traced between tasks with Hebog's modules, about 42 KB a published source plus 0.17 bytes a pixel over a fixed 142 MiB: 179 MiB at 3,000² (783 sources), 492 MiB at 10,000² (8,547), 978 MiB on the whole 15,402² mosaic (19,103) and 1,557 MiB on the ELAIS-N1 deep field's central 5,000² (34,092). `hebog.analysis_memory_bytes` states it from an expected source count (12 October). `hebog.expected_source_count` estimates that count from the image's 5σ local maxima: it bounded the published count on all 21 quick-check, agreement and benchmark cases, at 1.0 to 21 times (1.1 to 1.9 on the LOFAR and simulated SKA fields; 1,155 for 890 on the matched benchmark's 3,000² sector, where WSClean's list held 101,144 components), and reads the whole 15,402² mosaic in 28 s (14 October) | Bounded before the 45,000-pixel tier |
| Beyond one machine | Not run; planner bounds for 100,000² not yet written | The cluster benchmark |

## Engineering health

These figures guard against erosion; they do not establish parity or
readiness.

| Check | Latest |
| --- | --- |
| Portable suite | 3,894 passed and none xfailed, 97.40% branch-aware coverage against an 80% floor (15 October, `just ci` in the 0.22.0 release check, with 39 equivalence and 11 acceptance tests); the repository CI helper separately has 100% statement and branch coverage |
| Equivalence lane | 39 tests, including `find_sources` against both PyBDSF references under both profiles |
| CI matrix | Linux, macOS and Windows on Python 3.12 to 3.14, plus lowest-dependency and container checks required on `main`. The source workflow shards the complete suites, combines coverage, provides early unit feedback and limits execution skips to [documentation-only PRs](../how-to/index.md#pull-request-feedback); hosted latency after this change is not yet measured. |
| Architecture | Every layer's allowed imports are one tested table; Rapthor, Prefect and LSMTool are absent from the package and Dask is confined to `executors/`, apart from the execution profiler's local cluster in `validation/`, which wheels exclude |

## Blockers and next steps

The largest risks to 1.0.0 are the performance gap, which only many cores
can close; memory that grows with the image and the sources found; the
development machine's memory, disk and container VM; upstream churn; and
the three steps outside the agent's control: cluster time, Rapthor's
worker layout and independent reviewers.
The plan's
[decisions pending](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#decisions-pending)
list what the maintainer has still to decide, each with a recommendation.

The next actions, as the plan orders them on 17 October:

1. Agent: raise the 22,500² tier, and record Rapthor's Hebog branch with
   the `continuum` default in the integration container; the profile comes
   before the cluster work, which measures its cost.
2. Agent: then one sector across the cluster, starting with a stage
   profile of the 10,000² anchor in the matched container and sizing tiles
   and task counts from the core budget and the memory a core needs, in
   four increments that each release.
3. Human: push Rapthor's Hebog branch, which testing and trials use
   without waiting for a merge; file the Astropy report drafted on
   5 October; take the pending decisions.
4. Agent: the deployment envelope, the matched benchmarks on the cells the
   VM holds, the store and planner work and the cluster benchmark's
   packaging; the gate itself is measured on the cluster. The remaining
   scientific improvements (the clipped-RMS correction and the varying
   PSF) wait until this work is complete unless an output is confirmed
   incorrect.

## Keeping this page current

Update this page in the same change as the plan's current-state table:
after a release check, a tier gate, a new quick-check baseline or a repaired
defect. The commands that produce the figures are
`just quick-science-check`, `just quick-benchmark` and `just traced-peak`,
described in [Contribute to Hebog](../how-to/index.md); the equivalence lane
is `just test-equivalence`. Record the run label and date beside each figure
and replace stale figures. Keep measurements in existing versioned evidence
records or controlled storage, with exact identities linked from the commit.
Git history preserves previous summaries.
