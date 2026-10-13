# Progress against goals

This page answers one question: how far is Hebog from the goal its
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines for 1.0.0? It is updated whenever the plan's current state changes,
and was last updated on **13 October 2026** for the Rapthor-profile agreement and profile decision (task 21).
The scientific and performance measurements retain their original dates.
Every figure is development evidence from the
maintainer's machine, dated and traceable to versioned evidence and Git
history, or the [archived execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md);
none is scientific qualification. User-facing limits are in
[capability and status](release-status.md).

## At a glance

| 1.0.0 goal | Target | Position on 13 October 2026 | Status |
| --- | --- | --- | --- |
| Telescopes | Standard FITS continuum images from any telescope under a documented header contract, validated first on LOFAR, SKA-Low and SKA-Mid | The [input header contract](input-header-contract.md) is defined and tested. LOFAR (LoTSS-DR3 and LoTSS-DR2) and SKA-Mid (SDC1 simulation) images run, and the LOFAR-HD mosaics are the next scale tiers; SKA-Low has no public image, so MWA GLEAM-X precursor data is planned. A beam wider than 10 pixels is refused, which Rapthor's demonstration sector (30 pixels) needs, so task 62 is reopened. A position-dependent PSF is undecided (task 15). | In progress |
| Functionality | A feature-flagged backend for Rapthor's `filter_skymodel` at pinned Rapthor and LSMTool revisions | A complete standalone finder under Serial, Thread and caller-owned Dask executors, and the in-process Rapthor adapter: `hebog.adapters.find_sector_sources` runs a sector's true-sky and flat-noise images on the caller's executor and writes the files Rapthor's `filter_skymodel` step reads, by default with the `compact` profile and a zero background, Rapthor's choice from task 21, and pinned LSMTool's `filter_sources` filters by its mask as the mask decides, on the LoTSS-Deep DR2 ELAIS-N1 pair: its central 5,000² under all three executors with byte-identical products, and the full 14,175² sector's serial products. All 12 frozen public behaviours are implemented. A local Rapthor patch calls the adapter in-process with a ThreadExecutor, memory admission, typed PyBDSF fallback and dual runs, tested through its real Prefect task on a single-threaded Dask worker. | Patch prepared; upstream publication and merge pending |
| Science | ≥99.5% Rapthor retained/rejected agreement and a powered, held-out parity study against pinned PyBDSF `master` | Isolated-source position, flux and axis limits are met against both PyBDSF references on the frozen input, for sources and components under both profiles; the `Total_flux` limits hold on independent realizations. Two bounded known differences and one open defect remain. Rapthor keeps or rejects alike with Hebog's mask and pinned `master`'s 92.8% of sky-model components under the chosen `compact` profile with a zero background, against the 99.5% target; released PyBDSF reaches 99.29%. | Development evidence only |
| Performance | Matched complete `filter_skymodel` median ≤0.50 of pinned PyBDSF `master` | The local native task can support a matched measurement, but none has run: the finder refuses Rapthor's 3,000² demonstration sector, whose 45″ beam is 30 pixels, until task 62; the integration container uses released PyBDSF, not the gate's pinned `master`. The dense 14,175² ELAIS-N1 sector took 8.5 h serially, mostly in association. Diagnostic ratios against `master` on 1,024² fields are 2.7 to 5.2 (Hebog on one native thread against `master` on four container cores); on the 3,000² LoTSS field the two use the same CPU time, so the gap is parallel occupancy. No regression on the Hebog curve. | Gate unmeasured |
| Scalability | 45,000² on the 18 GiB development machine with tile-bounded memory; 90,000² on a 1 to 10-node cluster; planner bounds for 100,000² on 100 to 200+ nodes | Public envelope 15,402². Every stage runs tiled through the executor and products are byte-identical across tilings and executors. The traced peak is 1.7 GiB on the whole 15,402² mosaic and still grows about 1.7 bytes a pixel. Every task declares its memory, and the analysis's own records grow with the sources found, about 42 KB each. Bright regions are refined in bounded blocks, so the ELAIS-N1 deep field's central 5,000², where 951 bright candidates chain across the image, completes under four 4.5 GiB Dask workers. Nothing beyond one machine has run. | 15,402 of 45,000 pixels |
| Release | PyPI, with portability, security, licensing, documentation and independent acceptance | v0.21.0 (12 October 2026) is tagged on GitHub and uploaded to TestPyPI; it changes no product, and neither it nor v0.20.0 (11 October, maintainer's decision) had a release check of its own, so the latest passed on v0.19.0's repaired candidate on 9 October. CI runs on Linux, macOS and Windows for Python 3.12 to 3.14, and `main` requires the lowest-dependency and container checks. | Experimental `0.x` |

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
| Rapthor can fall back to pinned PyBDSF behind the feature flag | Implemented: a refused sector leaves none of Rapthor's files |
| Dual-run mode keeps products separate and reports differences | Implemented in the prepared Rapthor patch; reports both filtered product sets and retains their originals |
| A cancelled analysis stops its tasks and removes its staging | Implemented, under the Thread and Dask executors |

`hebog.adapters.find_sector_sources` runs one Rapthor sector on the
caller's executor and writes Rapthor's four files. The [prepared Rapthor
patch](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/patches/README.md)
adds the native task on today's worker layout; task 72 owns its future
distributed path. The [integration evidence](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/patches/integration-summary.json)
records the upstream audit, real Prefect/LSMTool/subprocess tests and the
frozen-field checkpoint under both profiles and background settings. The final
container passes 35 native/CLI tests; the broader native/settings suite passes
90, with full branch-aware coverage of the new native module. The 18-case
quick science check has no regressions and all 54 FITS products match the
previous baseline byte for byte. That
three-source smoke check did not decide the profile; task 21 did, below.
The adapter's eight-column codec reads the catalogue `find_sources`
writes. A
`continuum` source of one fitted Gaussian publishes that Gaussian, so its
row passes the three cuts Rapthor applies (`DC_Maj`, `E_RA`, `E_DEC`), as a
`compact` row does; a source of several components leaves them empty,
which on task 21's cases dropped 151 to 168 sources pinned `master`
keeps. Under
`compact`, which Rapthor runs, every source is one Gaussian.

## Science

### Gates

The binding reference is pinned PyBDSF `master` (`c70103b`); released 1.14.1
is checked once before 1.0.0. The limits are the plan's
[scientific gates](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#scientific-gates).

| Measurement | Target | Latest | Date and source |
| --- | --- | --- | --- |
| Rapthor retained/rejected components | ≥99.5% agreement | 92.8% under `compact` with a zero background, the profile Rapthor runs; 91.8% with the estimated background; 74.1% and 74.4% under `continuum`. Released 1.14.1 reaches 99.29%. No lane passes overall or in any stratum but the masked one (3 components); strata and causes are [below](#rapthor-profile-agreement) | 13 October, `just rapthor-agreement` run `task21`: 19 cases, 22,142 component positions |
| Reference recovery at SNR ≥10 | ≥99% | 1.000 on every generated quick-check case with compact truth, 0.998 on the crowded field; the wide extended source's disc and knots are not fitted one by one (0.300), which this gate does not cover | 9 October, quick check `release-0.19.0-rc2` |
| Isolated SNR ≥10 position, median / p95 | ≤0.02 / 0.10 beam | 0.0003 / 0.0005 (`continuum`), 0.0002 / 0.0006 (`compact`) | 6 October, equivalence lane on the frozen 256² input, task 57 |
| Isolated SNR ≥10 source and component peak flux, median / p95 | ≤2% / 5% | 0.17% / 0.21% (`continuum`), 0.04% / 0.13% (`compact`) | same |
| Isolated SNR ≥10 source `Total_flux`, median / p95 | ≤5% / 10% | 0.09% / 0.51% | 5 October, equivalence lane |
| Component fitted axes, median / p95 | ≤5% / 10% | 0.12% / 0.21% | same |
| `Total_flux` Hebog minus `master`, paired upper 95% bound per stratum | ≤ +1 point in median and p95 | Median −0.1, −0.2, 0.0 and p95 −3.5, +0.1, −0.1 points at SNR 10, 20 and 50, pooled over white and beam-correlated noise | 5 October, task 48, `m1-flux-calibration.json` |
| Position-uncertainty calibration (`E_RA`, `E_DEC`) | Pull standard deviation 1 | 1.015 and 1.006 on beam-correlated noise; unqualified on a real high-declination field | 24 September |
| Integrated-flux uncertainty calibration | Pull standard deviation 1 | 1.08 on beam-correlated noise; conservative (0.32 to 0.57) on white noise | 5 October, task 48 |
| Source-free RMS difference, median / p95 | ≤2% / 5% | 1.95% / **5.46%** (`continuum`); 1.57% / 3.12% (`compact`) | 5 October, equivalence lane |

Two differences against both PyBDSF references are bounded in the
equivalence lane rather than gated, each by its measured value plus the quick
check's tolerance, so a change that moves one fails CI and has to be
explained (task 49):

| Known difference | Measured | Target | Cause |
| --- | --- | --- | --- |
| `continuum` RMS tail | 5.46% at p95 | ≤5% | Local-noise refinement on 35-pixel windows scatters more than PyBDSF's 150-pixel box |
| Published mask | Recall 0.927, IoU 0.922; matched island IoU 0.909 median, 0.857 minimum | 0.99, 0.98; 0.99, 0.95 | The mask is publication support: the boundary rule trims 13 of the reference's 178 island pixels |

### Quick science check

The quick science check is the everyday regression detector: 18 fixed cases,
each one realization, compared with injected truth and with pinned `master`
on the fields Rapthor consumes. Run `release-0.19.0-rc2` on 9 October
2026, the release check of the repaired 0.19.0 candidate on `main` at
`d8fe206`, whose products are byte-identical to task 69's `task69-final`
in every case and to the 8 October release check in 16 of the 17 earlier
cases; `lotss-dr3-1312-dense` changes 0.25% of its RMS pixels by at most
9% with its sources unchanged. Every generated case also reports the
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
pixel. `just rapthor-agreement` (run `task21`, 13 October, 774 s) counts
how often Hebog's mask and pinned `master`'s decide alike, over every
distinct pixel holding a Gaussian centre that `master` or any lane fitted:
22,142 on the quick check's cases with a `master` reference, a 3,000²
LoTSS-DR3 window and the ELAIS-N1 true-sky and apparent images at 2,048².
Percentages agree; grouping is the share of components both keep whose
patch holds the same components.

| Lane | All | Bright | Extended | Edge | Crowded | Sparse | True-sky | Apparent | Grouping |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `compact`, zero background (Rapthor's) | 92.8 | 99.2 | 91.3 | 92.5 | 91.1 | 94.3 | 92.3 | 92.3 | 0.969 |
| `compact`, estimated | 91.8 | 98.3 | 88.3 | 92.0 | 90.1 | 93.3 | 91.2 | 91.2 | 0.962 |
| `continuum`, zero | 74.4 | 100 | 92.0 | 76.5 | 75.3 | 73.7 | 71.0 | 71.1 | 0.925 |
| `continuum`, estimated | 74.1 | 100 | 91.8 | 77.4 | 75.2 | 73.1 | 70.6 | 70.5 | 0.921 |
| Released PyBDSF 1.14.1 (control) | 99.3 | 100 | 99.3 | 100 | 98.6 | 99.9 | 99.3 | 99.3 | 0.999 |
| Components | 22,142 | 1,013 | 1,753 | 637 | 10,130 | 12,012 | 9,193 | 9,215 | |

Every lane agrees on the 3 masked components. The disagreement is on real
LOFAR fields: the generated cases agree fully but for `varying-noise`, the
dense and crowded fields and `wide-extended-source`. On the ELAIS-N1 deep
field `continuum` loses 1,346 of `master`'s 5,762 islands, where its RMS
is a median 2.0 times `master`'s: its 35-pixel local-noise windows read
faint sources as noise (task 75). `compact` loses 257, and up to 9 bright
components an image where the image edge cuts their source. On Rapthor's
catalogue cuts, `continuum` drops 151 to 168 matched sources `master`
keeps because they have several components, and every lane publishes `DC_Maj` 0
for about 1,700 fits of 10″ or more, against `master`'s 439, so 255 to 343
matched sources that `master`'s cuts drop pass them as unresolved. No lane passes the
99.5% gate, so the plan's rule falls back to `continuum`; the maintainer
chose `compact` with a zero background instead, and task 29 decides the
gate's binding form, since the release control misses it too.

### Open scientific defects

- **Clipped RMS reads low (task 68).** The clipped window RMS has no
  truncation correction: on noise alone it reads 1.6% low on white noise
  and 3.2 to 3.9% low on beam-correlated noise (7 October).
- **Fixed meshes (task 62, deferred).** Beams wider than 10 pixels are
  refused; scaling the meshes with the beam would recover sources to 22
  pixels at about 2.5 times the local-noise read.

## Performance

The deployment gate cannot be measured until Rapthor's native task runs the
adapter (tasks 20 and 23). Everything below is diagnostic.

| Measurement | Latest | Date and source |
| --- | --- | --- |
| Hebog / pinned `master`, matched `filter_skymodel` | Not measured; gate ≤0.50 | task 23 |
| Hebog / `master`, 1,024² quick-benchmark cases, Hebog on one native thread against `master` on four container cores | 5.21 (`dense-field`), 3.21 (LoTSS sparse), 2.69 (LoTSS dense); upper bounds 5.49, 3.36, 2.87 | 6 October, `pr-stack-2026-10-06-with-master` |
| The same ratio on larger fields | 0.88 on the crowded 2,048² SDC1 cut-out; 3.05 on the 3,000² LoTSS field, where both use the same CPU time | 26 September, large tier on a quiet machine |
| Hebog curve, repaired 0.19.0 candidate against 0.18.0, same session | 0.97, 0.88, 0.91 at 1,024², upper bounds 1.04, 0.91 and 0.94, all passing the ≤1.05 regression rule; `dense-field` was timed again alone after reading an inconclusive 0.99 [0.96, 1.05] under a video call | 9 October, release check |
| Absolute wall time, 1,024² cases, Serial | 12 to 18 s a run at loads of 3.6 to 10 across the two checks | 8 and 9 October, release checks |
| Serial anchors | 1,259 s at 10,000², the same as on 28 September, and 1,579 s on 9 October under a video call; 3,410 s on the whole 15,402² mosaic (3,362 s in the 0.18.0 release check) | 8 and 9 October; 29 September and 5 October |
| Four-worker Dask against Serial | 0.59 at 10,000² (741 s), and 0.55 under load on 9 October (872 s); 0.63 on the whole mosaic (2,116 s); byte-identical products in every run | 8 and 9 October; 5 October |
| LoTSS-Deep DR2 ELAIS-N1, a dense deep field | 30,745 s Serial for 123,186 sources on the whole 14,175² sector, about 7.4 h of it after component fitting; on its central 5,000², 2,138 s Serial, 1,974 s on four threads and 1,871 s on two 9 GiB Dask workers, after four 4.5 GiB workers failed; with bright regions in bounded blocks (v23), 2,137 s Serial, 1,986 s on four threads and 1,543 s on four 4.5 GiB Dask workers, byte-identical | 10 and 11 October, `scripts/validation/check_lsmtool_filter.py` reports in `benchmark-results/lsmtool-check-elais-n1*` |
| Profile shape | The largest stage is about a fifth of a run and the largest kernel 5 to 8%, so no kernel reaches the native-code assessment's 10% gate | 21 September |

About half of a large run is background and RMS estimation, and most of the
growth beyond image area is source association, which tasks 54 and 55
address. The [performance profile](performance-profile.md) has the stage
shares and the memory figures.

## Scalability

| Measurement | Latest | Target |
| --- | --- | --- |
| Public envelope | 15,402 pixels a side | 45,000² locally (task 12), 90,000² on the cluster (task 30) |
| Traced allocation peak, Serial | 430 MiB at 1,024²; 1,312 MiB at 2,048²; 1,335 MiB at 3,000²; 1,489 MiB at 10,000²; 1,692 MiB at 15,402² (8 October, one repetition; 1,698 MiB in two agreeing repetitions on 29 September) | Bounded by the tile |
| Growth beyond one tile | About 1.7 bytes a pixel in the multiscale pass and about 3 in background/RMS; at those slopes about 2.1 GiB at 22,500² and 4.3 GiB at 45,000² | Bounded before task 12 (tasks 53 to 56) |
| Peak RSS | Whole mosaic: 3,101 MiB Serial; 2,531 MiB driver and 2,429 MiB largest worker under Dask. 10,000² anchor: 2,576 MiB Serial; 1,569 MiB driver and 1,829 MiB largest worker under Dask (an envelope, not a gate) | – |
| Tiling and executor invariance | Byte-identical products from one tile and the 8×8 grid, and under Serial, Thread and Dask, including the whole mosaic | Exact |
| Declared limit | An object wider than a task's read budget is reduced on the driver at up to 186 bytes an object pixel; about 44 GB for a field-filling object at 15,402². No real LoTSS-DR3 object comes within a factor of ten of the budget | Deferred; reopened when a tier's traced peak shows it |
| Memory admission | Every task declares its memory from its read: the multiscale tile tasks are the largest, 1,247 MiB traced for a 2,048-pixel core with its halo, and object batches reach 774 MiB on the whole mosaic. A memory budget narrows the in-flight window, and a `DaskExecutor` given the caller's resource names attaches each declaration to its task; on a local two-worker cluster that keeps a second task off a worker without the memory (12 October, task 17) | Bounded by the tile |
| Analysis memory | Traced between tasks with Hebog's modules, about 42 KB a published source plus 0.17 bytes a pixel over a fixed 142 MiB: 179 MiB at 3,000² (783 sources), 492 MiB at 10,000² (8,547), 978 MiB on the whole 15,402² mosaic (19,103) and 1,557 MiB on the ELAIS-N1 deep field's central 5,000² (34,092). `hebog.analysis_memory_bytes` states it from an expected source count (12 October, task 17) | Bounded before task 12 (task 56) |
| Beyond one machine | Not run; planner bounds for 100,000² not yet written | tasks 24, 27 and 30 |

## Engineering health

These figures guard against erosion; they do not establish parity or
readiness.

| Check | Latest |
| --- | --- |
| Portable suite | 3,787 passed and none xfailed, 97.30% branch-aware coverage against an 80% floor (12 October, the local coverage lane on task 17's change, whose merge then passed CI on every platform); the repository CI helper separately has 100% statement and branch coverage |
| Equivalence lane | 39 tests, including `find_sources` against both PyBDSF references under both profiles |
| CI matrix | Linux, macOS and Windows on Python 3.12 to 3.14, plus lowest-dependency and container checks required on `main`. The source workflow shards the complete suites, combines coverage, provides early unit feedback and limits execution skips to [documentation-only PRs](../how-to/index.md#pull-request-feedback); hosted latency after this change is not yet measured. |
| Architecture | Every layer's allowed imports are one tested table; Rapthor, Prefect and LSMTool are absent from the package and Dask is confined to `executors/`, apart from the execution profiler's local cluster in `validation/`, which wheels exclude |

## Blockers and next steps

The largest risks to 1.0.0 are the performance gap, the retained/rejected
agreement gap, the traced peak's growth with the image, the wide-object driver term, the development machine's
memory and disk, and SKA-Low coverage without public SKA-Low images.

The next actions, as the plan orders them on 13 October:

1. Agent: the prepared Rapthor patch adopts task 21's `compact` profile and
   zero background; task 62 scales the meshes with the beam so the finder
   accepts Rapthor's demonstration sector; then a first matched
   `filter_skymodel` measurement on that 3,000² sector (task 23). Human:
   publish/review the prepared Rapthor patch; its authoritative upstream
   pins were unchanged at the 12 October checkpoint.
2. Agent: one sector across the cluster. Measure how a sector scales with
   Dask workers and where its serial share lies (task 73), cut that share
   (task 74, with tasks 71 and 54 to 56), then fit Hebog's tasks to
   Rapthor's workers (task 72); beside it, the 22,500² tier (task 11), since
   Rapthor's usual sector is 17,000 to 20,000 pixels a side.
3. Agent: the deployment envelope and the gate (tasks 22 and 23), on one
   node; one sector across several nodes is measured by the cluster
   benchmark. Scientific improvements (tasks 15 and 68) wait until this
   work is complete unless an output is confirmed incorrect.

## Keeping this page current

Update this page in the same change as the plan's current-state table:
after a release check, a tier gate, a new quick-check baseline or a repaired
defect. The commands that produce the figures are
`just quick-science-check`, `just quick-benchmark` and `just traced-peak`,
described in [Contribute to Hebog](../how-to/index.md); the equivalence lane
is `just test-equivalence`. Record the run label and date beside each figure
and replace stale figures. Keep measurements in existing versioned evidence
records or controlled storage, with exact identities linked from the commit.
Git history preserves previous summaries; `LOG.md` receives no new entries.
