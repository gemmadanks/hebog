# Progress against goals

This page answers one question: how far is Hebog from the goal its
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
defines for 1.0.0? It is updated whenever the plan's current state changes,
and was last updated on **7 October 2026** for the source checkout after the
0.18.0 review repairs. Every figure is development evidence from the
maintainer's machine, dated and traceable to an entry in the repository's
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md); none is
scientific qualification. User-facing limits are in
[capability and status](release-status.md).

## At a glance

| 1.0.0 goal | Target | Position on 6 October 2026 | Status |
| --- | --- | --- | --- |
| Telescopes | Standard FITS continuum images from any telescope under a documented header contract, validated first on LOFAR, SKA-Low and SKA-Mid | The [input header contract](input-header-contract.md) is defined and tested. LOFAR (LoTSS-DR3 and LoTSS-DR2) and SKA-Mid (SDC1 simulation) images run, and the LOFAR-HD mosaics are the next scale tiers; SKA-Low has no public image, so MWA GLEAM-X precursor data is planned. A beam wider than 10 pixels is refused. A position-dependent PSF is undecided (task 15). | In progress |
| Functionality | A feature-flagged backend for Rapthor's `filter_skymodel` at pinned Rapthor and LSMTool revisions | A complete standalone finder under Serial, Thread and caller-owned Dask executors. No Rapthor adapter, profile or flat-noise branch exists; 5 of the 11 frozen public behaviours are implemented and 6 are strict-xfail placeholders. | Adapter not started |
| Science | ≥99.5% Rapthor retained/rejected agreement and a powered, held-out parity study against pinned PyBDSF `master` | Isolated-source position, flux and axis limits are met against both PyBDSF references on the frozen input, for sources and components under both profiles; the `Total_flux` limits hold on independent realizations. Two bounded known differences, four open defects and the unmeasured Rapthor agreement remain. | Development evidence only |
| Performance | Matched complete `filter_skymodel` median ≤0.50 of pinned PyBDSF `master` | Not measurable until the adapter exists. Diagnostic ratios against `master` on 1,024² fields are 2.7 to 5.2 (Hebog on one native thread against `master` on four container cores); on the 3,000² LoTSS field the two use the same CPU time, so the gap is parallel occupancy. No regression on the Hebog curve. | Gate not yet measurable |
| Scalability | 45,000² on the 18 GiB development machine with tile-bounded memory; 90,000² on a 1 to 10-node cluster; planner bounds for 100,000² on 100 to 200+ nodes | Public envelope 15,402². Every stage runs tiled through the executor and products are byte-identical across tilings and executors. The traced peak is 1.7 GiB on the whole 15,402² mosaic and still grows about 1.7 bytes a pixel. Nothing beyond one machine has run. | 15,402 of 45,000 pixels |
| Release | PyPI, with portability, security, licensing, documentation and independent acceptance | v0.18.0 (5 October 2026) is tagged on GitHub and uploaded to TestPyPI; CI runs on Linux, macOS and Windows for Python 3.12 to 3.14. | Experimental `0.x` |

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
| Reference recovery at SNR ≥10 | ≥99% | 1.000 on every generated quick-check case with truth, 0.998 on the crowded field | 6 October, quick check `task57` |
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

The quick science check is the everyday regression detector: 17 fixed cases,
each one realization, compared with injected truth and with pinned `master`
on the fields Rapthor consumes. Run `task57` on 6 October 2026, Hebog
0.18.0 plus the review repairs and task 57, which changed only the source
rows' position and peak agreement with `master` and none of the figures
below. Completeness and reliability
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
| `crowded-field` | 996 | 0.998 | 0.999 | 0.986 | 0.996 | 0.887 |
| `sdc1-b2-1000h-sparse` | 561 | – | – | 0.910 | 0.968 | 0.816 |
| `sdc1-b2-1000h-crowded` | 886 | – | – | no `master` reference | – | – |
| `lotss-dr3-1312-sparse` | 59 | – | – | 0.857 | 0.915 | 0.819 |
| `lotss-dr3-1312-dense` | 105 | – | – | 0.807 | 0.914 | 0.793 |

On the whole 15,402² LoTSS-DR3 mosaic 1312 the 0.18.0 candidate publishes
19,189 sources, 21,010 Gaussians and 20,095 islands; the survey's PyBDSF
catalogue has 22,420 sources and 28,559 Gaussians (5 October).

### Open scientific defects

- **Degenerate joint fits (task 42).** When one component of a joint fit
  collapses, every component falls back to a beam-shaped Gaussian and
  resolved ones can be left unpublished: 39 fall back and 15 are unpublished
  on the sparse SDC1 cut-out.
- **RMS beside a sharp noise step (tasks 63 and 65).** In a crowded field,
  where bright-region refinement covers the image, one clean window
  straddling a noise step sets the RMS of about 160 columns beside it, at a
  third of the noise, so spurious sources are published there; a quiet strip
  160 columns wide instead reads five times its noise and loses sources.
  Task 63's rule is chosen. On the normal local-noise path, windows
  straddling a step read low within about 20 pixels of it (task 65).
- **Owner support connected through other pixels (task 64).** A pixel can
  attach to its owner across unassigned pixels, and one such input raises a
  bare `ValueError`.
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
| Hebog curve, review repairs against `main` after 0.18.0, same session | 0.89, 0.92, 0.94 at 1,024², all passing the ≤1.05 regression rule | 6 October |
| Hebog curve, 0.18.0 against 0.17.0, same session | 0.95, 0.95, 0.94 | 5 October, release check |
| Absolute wall time, 1,024² cases, Serial | 13 to 16 s a run at load 1.7 to 4.4 | 6 October |
| Serial anchors | 1,259 s at 10,000²; 3,410 s on the whole 15,402² mosaic (3,362 s in the release check) | 28 September; 29 September and 5 October |
| Four-worker Dask against Serial | 0.61 at 10,000²; 0.63 on the whole mosaic (2,116 s), byte-identical products | 5 October |
| Profile shape | The largest stage is about a fifth of a run and the largest kernel 5 to 8%, so no kernel reaches the native-code assessment's 10% gate | 21 September |

About half of a large run is background and RMS estimation, and most of the
growth beyond image area is source association, which tasks 54 and 55
address. The [performance profile](performance-profile.md) has the stage
shares and the memory figures.

## Scalability

| Measurement | Latest | Target |
| --- | --- | --- |
| Public envelope | 15,402 pixels a side | 45,000² locally (task 12), 90,000² on the cluster (task 30) |
| Traced allocation peak, Serial | 430 MiB at 1,024²; 1,312 MiB at 2,048²; 1,335 MiB at 3,000²; 1,489 MiB at 10,000²; 1,698 MiB at 15,402² | Bounded by the tile |
| Growth beyond one tile | About 1.7 bytes a pixel in the multiscale pass and about 3 in background/RMS; at those slopes about 2.1 GiB at 22,500² and 4.3 GiB at 45,000² | Bounded before task 12 (tasks 53 to 56) |
| Peak RSS, whole mosaic | 3,101 MiB Serial; 2,531 MiB driver and 2,429 MiB largest worker under Dask (an envelope, not a gate) | – |
| Tiling and executor invariance | Byte-identical products from one tile and the 8×8 grid, and under Serial, Thread and Dask, including the whole mosaic | Exact |
| Declared limit | An object wider than a task's read budget is reduced on the driver at up to 186 bytes an object pixel; about 44 GB for a field-filling object at 15,402². No real LoTSS-DR3 object comes within a factor of ten of the budget | Deferred; reopened when a tier's traced peak shows it |
| Memory admission | No stage declares a task's memory, so executor admission has no effect yet | task 17 |
| Beyond one machine | Not run; planner bounds for 100,000² not yet written | tasks 24, 27 and 30 |

## Engineering health

These figures guard against erosion; they do not establish parity or
readiness.

| Check | Latest |
| --- | --- |
| Portable suite | 3,398 passed and 2 xfailed, 97% branch-aware coverage against an 80% floor (6 October) |
| Equivalence lane | 45 tests, including `find_sources` against both PyBDSF references under both profiles |
| CI matrix | Linux, macOS and Windows on Python 3.12 to 3.14, plus a lowest-dependency job and a container build (not yet required on `main`, task 60) |
| Architecture | Every layer's allowed imports are one tested table; Rapthor, Prefect and LSMTool are absent from the package and Dask is confined to `executors/` |

## Blockers and next steps

The largest risks to 1.0.0 are the performance gap, the traced peak's growth
with the image, the wide-object driver term, the development machine's
memory and disk, and SKA-Low coverage without public SKA-Low images.

The next actions, as the plan orders them:

1. Human: release the merged task 44 and 45 repairs; require the two CI
   checks task 60 added.
2. Agent: task 63, under the rule chosen on 7 October, then task 64, the
   measured options for task 42 and task 65.
3. Agent: tasks 53 to 56, bounding the terms that grow with the image, before
   the 22,500² (task 11) and 45,000² (task 12) tier gates.

## Keeping this page current

Update this page in the same change as the plan's current-state table:
after a release check, a tier gate, a new quick-check baseline or a repaired
defect. The commands that produce the figures are
`just quick-science-check`, `just quick-benchmark` and `just traced-peak`,
described in [Contribute to Hebog](../how-to/index.md); the equivalence lane
is `just test-equivalence`. Record the run label and date beside each figure,
and move replaced figures to `LOG.md` rather than keeping two current
positions.
