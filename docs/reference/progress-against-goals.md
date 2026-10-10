# Progress against goals

This page answers one question: how far is Hebog from the goal its
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines for 1.0.0? It is updated whenever the plan's current state changes,
and was last updated on **10 October 2026** for the PR CI scheduling policy.
The scientific and performance measurements retain their original dates.
Every figure is development evidence from the
maintainer's machine, dated and traceable to an entry in the repository's
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md); none is
scientific qualification. User-facing limits are in
[capability and status](release-status.md).

## At a glance

| 1.0.0 goal | Target | Position on 9 October 2026 | Status |
| --- | --- | --- | --- |
| Telescopes | Standard FITS continuum images from any telescope under a documented header contract, validated first on LOFAR, SKA-Low and SKA-Mid | The [input header contract](input-header-contract.md) is defined and tested. LOFAR (LoTSS-DR3 and LoTSS-DR2) and SKA-Mid (SDC1 simulation) images run, and the LOFAR-HD mosaics are the next scale tiers; SKA-Low has no public image, so MWA GLEAM-X precursor data is planned. A beam wider than 10 pixels is refused. A position-dependent PSF is undecided (task 15). | In progress |
| Functionality | A feature-flagged backend for Rapthor's `filter_skymodel` at pinned Rapthor and LSMTool revisions | A complete standalone finder under Serial, Thread and caller-owned Dask executors. No Rapthor backend, profile or flat-noise branch exists; 5 of the 11 frozen public behaviours are implemented and 6 are strict-xfail placeholders. Rapthor's `main` branch, Prefect and Dask since 9 October 2026, selects the finder through LSMTool's `filter_skymodel` registry in a fresh interpreter per sector, so the backend will be a registry entry calling a Hebog adapter (the plan's tasks 16 to 20, now the next milestone). | Backend not started |
| Science | ≥99.5% Rapthor retained/rejected agreement and a powered, held-out parity study against pinned PyBDSF `master` | Isolated-source position, flux and axis limits are met against both PyBDSF references on the frozen input, for sources and components under both profiles; the `Total_flux` limits hold on independent realizations. Two bounded known differences, one open defect and the unmeasured Rapthor agreement remain. | Development evidence only |
| Performance | Matched complete `filter_skymodel` median ≤0.50 of pinned PyBDSF `master` | Not measurable until the adapter exists. Diagnostic ratios against `master` on 1,024² fields are 2.7 to 5.2 (Hebog on one native thread against `master` on four container cores); on the 3,000² LoTSS field the two use the same CPU time, so the gap is parallel occupancy. No regression on the Hebog curve. | Gate not yet measurable |
| Scalability | 45,000² on the 18 GiB development machine with tile-bounded memory; 90,000² on a 1 to 10-node cluster; planner bounds for 100,000² on 100 to 200+ nodes | Public envelope 15,402². Every stage runs tiled through the executor and products are byte-identical across tilings and executors. The traced peak is 1.7 GiB on the whole 15,402² mosaic and still grows about 1.7 bytes a pixel. Nothing beyond one machine has run. | 15,402 of 45,000 pixels |
| Release | PyPI, with portability, security, licensing, documentation and independent acceptance | v0.19.0 (9 October 2026) is tagged on GitHub and uploaded to TestPyPI, after its release check passed on 8 October, was held for task 69 and passed again on the repaired candidate on 9 October. CI runs on Linux, macOS and Windows for Python 3.12 to 3.14, and `main` requires the lowest-dependency and container checks. | Experimental `0.x` |

## Functionality

The 11 frozen public behaviours in
`config/contracts/phase-0-public-behaviours.json` each name the test that
holds them. A placeholder is a strict xfail, so CI fails the day one starts
passing.

| Behaviour | Status |
| --- | --- |
| A valid request returns versioned catalogue, RMS, mask, diagnostics and timing records | Implemented |
| An empty image succeeds with zero sources and structurally valid empty products | Implemented |
| Invalid beam, WCS, unit or dimensional metadata fails before any result is written | Implemented |
| Raising a threshold cannot create a source | Implemented |
| Tile shape, worker count, completion order and batch size do not change the products | Implemented |
| No worker materialises a complete large plane and admitted memory bounds the peak | Placeholder (task 17) |
| Rapthor adapter products for the true-sky and flat-noise pair | Placeholder (task 19) |
| Retry reuses valid stage products | Placeholder (task 19) |
| Worker loss is retried to the same deterministic products | Placeholder (task 19) |
| Rapthor can fall back to pinned PyBDSF behind the feature flag | Placeholder (task 19) |
| Dual-run mode keeps products separate and reports differences | Placeholder (task 19) |

`hebog.adapters` holds the Rapthor records and the eight-column catalogue
codec only. The codec reads the catalogue `find_sources` writes. A
`continuum` source of one fitted Gaussian publishes that Gaussian, so its
row passes the three cuts Rapthor applies (`DC_Maj`, `E_RA`, `E_DEC`), as a
`compact` row does; a source of several components leaves them empty, and
task 21 measures what that costs.

## Science

### Gates

The binding reference is pinned PyBDSF `master` (`c70103b`); released 1.14.1
is checked once before 1.0.0. The limits are the plan's
[scientific gates](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#scientific-gates).

| Measurement | Target | Latest | Date and source |
| --- | --- | --- | --- |
| Rapthor retained/rejected components | ≥99.5% agreement | Not measured; needs the Rapthor profile and adapter | task 21 |
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

### Open scientific defects

- **Clipped RMS reads low (task 68).** The clipped window RMS has no
  truncation correction: on noise alone it reads 1.6% low on white noise
  and 3.2 to 3.9% low on beam-correlated noise (7 October).
- **Fixed meshes (task 62, deferred).** Beams wider than 10 pixels are
  refused; scaling the meshes with the beam would recover sources to 22
  pixels at about 2.5 times the local-noise read.

## Performance

The deployment gate cannot be measured until the Rapthor adapter exists
(tasks 19 and 23). Everything below is diagnostic.

| Measurement | Latest | Date and source |
| --- | --- | --- |
| Hebog / pinned `master`, matched `filter_skymodel` | Not measured; gate ≤0.50 | task 23 |
| Hebog / `master`, 1,024² quick-benchmark cases, Hebog on one native thread against `master` on four container cores | 5.21 (`dense-field`), 3.21 (LoTSS sparse), 2.69 (LoTSS dense); upper bounds 5.49, 3.36, 2.87 | 6 October, `pr-stack-2026-10-06-with-master` |
| The same ratio on larger fields | 0.88 on the crowded 2,048² SDC1 cut-out; 3.05 on the 3,000² LoTSS field, where both use the same CPU time | 26 September, large tier on a quiet machine |
| Hebog curve, repaired 0.19.0 candidate against 0.18.0, same session | 0.97, 0.88, 0.91 at 1,024², upper bounds 1.04, 0.91 and 0.94, all passing the ≤1.05 regression rule; `dense-field` was timed again alone after reading an inconclusive 0.99 [0.96, 1.05] under a video call | 9 October, release check |
| Absolute wall time, 1,024² cases, Serial | 12 to 18 s a run at loads of 3.6 to 10 across the two checks | 8 and 9 October, release checks |
| Serial anchors | 1,259 s at 10,000², the same as on 28 September, and 1,579 s on 9 October under a video call; 3,410 s on the whole 15,402² mosaic (3,362 s in the 0.18.0 release check) | 8 and 9 October; 29 September and 5 October |
| Four-worker Dask against Serial | 0.59 at 10,000² (741 s), and 0.55 under load on 9 October (872 s); 0.63 on the whole mosaic (2,116 s); byte-identical products in every run | 8 and 9 October; 5 October |
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
| Memory admission | No stage declares a task's memory, so executor admission has no effect yet | task 17 |
| Beyond one machine | Not run; planner bounds for 100,000² not yet written | tasks 24, 27 and 30 |

## Engineering health

These figures guard against erosion; they do not establish parity or
readiness.

| Check | Latest |
| --- | --- |
| Portable suite | 3,692 passed and 1 xfailed, 97.15% branch-aware coverage against an 80% floor (10 October, CI scheduling change); the repository CI helper separately has 100% statement and branch coverage |
| Equivalence lane | 39 tests, including `find_sources` against both PyBDSF references under both profiles |
| CI matrix | Linux, macOS and Windows on Python 3.12 to 3.14, plus lowest-dependency and container checks required on `main`. The source workflow shards the complete suites, combines coverage, provides early unit feedback and limits execution skips to [documentation-only PRs](../how-to/index.md#pull-request-feedback); hosted latency after this change is not yet measured. |
| Architecture | Every layer's allowed imports are one tested table; Rapthor, Prefect and LSMTool are absent from the package and Dask is confined to `executors/`, apart from the execution profiler's local cluster in `validation/`, which wheels exclude |

## Blockers and next steps

The largest risks to 1.0.0 are the performance gap, the traced peak's growth
with the image, the wide-object driver term, the development machine's
memory and disk, and SKA-Low coverage without public SKA-Low images.

The next actions, as the plan orders them on 10 October:

1. Agent: the in-process backend (task 19), with Rapthor's thresholds and
   PyBDSF's minimum island size rule, memory declarations (task 17), the
   native Prefect task in Rapthor and the profile agreement under both
   background settings (tasks 20 and 21), and a first matched
   `filter_skymodel` measurement on Rapthor's 3,000² demonstration sector.
2. Agent: one sector across the cluster. Measure how a sector scales with
   Dask workers and where its serial share lies (task 73), cut that share
   (task 74, with tasks 71 and 53 to 56), then fit Hebog's tasks to
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
is `just test-equivalence`. Record the run label and date beside each figure,
and move replaced figures to `LOG.md` rather than keeping two current
positions.
