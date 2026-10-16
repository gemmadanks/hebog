# Hebog implementation plan

Authoritative remaining-work plan. Updated **15 October 2026**.
Current user-facing capability is in
[release status](../docs/reference/release-status.md). Git history records
completed work, rationale, validation and evidence references; ADRs record
significant architecture decisions. [`LOG.md`](../LOG.md) is a historical
archive and receives no new entries.
Closed Phase 5 contracts, reviews and campaign tooling are in Git history at
`4babf0b`.

## Current state

The measured figures behind this table, with their dates and run labels,
are on [progress against goals](../docs/reference/progress-against-goals.md);
the two change together.

| Item | Current position |
| --- | --- |
| Release | v0.21.0 (12 October 2026), on TestPyPI: every task declares its memory, a `DaskExecutor` attaches it under the caller's Dask resource names, and `hebog.analysis_memory_bytes` states the analysis's own memory from an expected source count; `Executor.reduce_batches` is removed. It changes no product: the quick check's catalogue, RMS and mask were byte-identical to v0.20.0's. CI passed on Linux, macOS and Windows for Python 3.12 to 3.14 on the merge. v0.20.0 (11 October) brought Rapthor's source-finding step in-process through `hebog.adapters` and shipped without a release check of its own (maintainer's decision). The 0.22.0 candidate, tasks 73, 74, 71, 55 and 54 with the switch to PyPI, passed its release check on 15 October: `just ci`, quick-check metrics unchanged, every quick-benchmark case at most v0.21.0's time, Serial and four-worker Dask byte-identical on the 10,000² anchor in 1,140 s and 462 s, and the whole mosaic's traced peak unchanged (1,692.6 MiB against 1,692.5). Experimental and scientifically unqualified. |
| Candidate | Public composition v23: diagonal-weighted component fits, detection through the tiled pass, bright regions refined in bounded blocks. Development-unqualified. |
| Functionality | Standalone FITS-to-products finder (background/RMS, compact and multiscale detection, deblending, fitting, association; catalogue, mask, RMS and diagnostics) under Serial, Thread and caller-owned Dask executors, within the [input header contract](../docs/reference/input-header-contract.md). `hebog.adapters.find_sector_sources` runs one Rapthor sector in-process on the caller's executor: one run analyses the true-sky image, publishes the flat-noise image's RMS beside it, and writes the eight-column catalogue, both RMS maps and PyBDSF's four-axis island mask under Rapthor's names, with Rapthor's `threshpix`, `threshisl` and PyBDSF's minimum island rule and, by default, the `compact` profile with PyBDSF's zero mean map (task 21). A retried request reuses its finished products, a caller's deadline stops an analysis's tasks, typed refusals leave Rapthor free to fall back, and `compare_sector_products` reports dual runs. Pinned LSMTool's `filter_sources`, in a container, clips, groups and transfers names on its products as the mask decides, on the LoTSS-Deep DR2 ELAIS-N1 pair: its central 5,000² under Serial, Thread and Dask with byte-identical products, and the full 14,175² sector's serial products. A [local Rapthor patch](../scripts/validation/patches/README.md) calls the adapter from the existing Prefect task with a ThreadExecutor, memory admission for the sources `hebog.expected_source_count` estimates from the image, a PyBDSF fallback on typed refusals and on a worker too small for the analysis, and separate dual-run products; its parset defaults to task 21's `compact` profile with a zero background. It is tested on the current one-single-threaded-worker-per-node layout; publication and upstream merge remain human actions, and task 72 owns the distributed path. The codec reads the catalogue `find_sources` writes; a `continuum` source of one fitted Gaussian publishes that Gaussian, so its row passes Rapthor's three cuts, and a source of several components leaves those columns empty, which dropped 151 to 168 sources pinned `master` keeps on task 21's cases; under `compact` every source is one Gaussian. Rapthor's `main` branch, which merged its Prefect/Dask workflow on 9 October 2026 (`c6196cb4`), selects the finder through LSMTool's `filter_skymodel(source_finder=...)` registry and runs that call in a fresh interpreter per sector with `ncores` and single native threads, with no Dask client in reach. Task 23's checkpoint of 13 October moved the Rapthor pin to `d0e7e148`, one commit beyond `c6196cb4` that changes BDA defaults only, and the patch replays onto it unchanged; LSMTool stays at `9bac2f7`; the [contract](../docs/reference/rapthor-source-finding-contract.md) and [integration evidence](../scripts/validation/patches/integration-summary.json) bind the patch to them. Decided 10 October: Rapthor replaces that call with a native Prefect task that runs Hebog in-process on its Dask worker, on a thread executor when a sector has a node to itself and across Rapthor's workers when it does not; Rapthor usually images one sector, so one sector across the cluster is the performance focus, and several sectors stay supported (ADR-004 amendment). Rapthor's default and benchmarked LOFAR sectors are 17,000 to 20,000 pixels a side, above the 15,402² envelope; only its demonstration sector is 3,000², and the finder refuses it: its synthetic baselines, at most about 5,000 wavelengths, give a 45″ beam, 30 pixels at 1.5″, where every real Rapthor image is at most about 7. |
| Scalability | v0.18.0 admits ≤15,402 pixels per side. Every stage runs through the executor on tiles (background/RMS on 128-pixel cores, everything else on 2,048) and publishes to Zarr; products are byte-identical on one tile and on the tile grid and between Serial and four-worker Dask on the whole 15,402² mosaic; the driver holds no image-sized plane. The traced peak (1,692 MiB on the whole mosaic on 8 October, the same on 15 October) is one multiscale tile task plus kept records growing about 1.7 bytes a pixel and background/RMS growing about 3 (task 56). Every task declares its memory, bounded by its tile, halo, batch and storage chunk; the multiscale tile tasks are the largest at about 1.2 GiB traced, and a `DaskExecutor` given the caller's resource names attaches each declaration to its task. Two terms are bounded by something other than the tile: an object wider than the read budget brings its own pixels to the driver (deferred below; ADR-008, *Objects wider than the read budget*), and the analysis's kept records grow with the sources found, about 42 KB each traced, so the ELAIS-N1 deep field's central 5,000² (34,092 sources) holds 1,557 MiB against 978 MiB for the whole 15,402² mosaic (19,103 sources); `hebog.analysis_memory_bytes` states it from a caller's expected source count, and `hebog.expected_source_count` estimates that count from the image's bright local maxima: it bounded the published count on all 21 quick-check, agreement and benchmark cases, at 1.0 to 21 times (1.1 to 1.9 on the LOFAR and simulated SKA fields), and reads the whole 15,402² mosaic in 28 s. Bright candidates that chain into one region, as 951 of the 965 on the ELAIS-N1 deep field's central 5,000² do across the whole image, are refined in blocks read as the local-noise blocks are, at most 568,516 pixels there, and four 4.5 GiB Dask workers complete it; one task used to read the whole region and failed them. A block protects emission its sides cut off, so it can exclude more than one read of the region would: there 117 of 505,521 fine windows beside block seams, moving 44 of 34,040 sources by up to 2.6% in flux, with counts, RMS maps and LSMTool's filtering unchanged (accepted 11 October). Diagnostics record each estimate's bright candidate count and largest bright-region read. |
| Performance | First matched `filter_skymodel` measurement (task 23, run `task23-first`, 13 October): Rapthor's complete step with its native Hebog task took a median 186.0 s against 91.6 s with pinned PyBDSF `master`, a ratio of 2.03 (one-sided 95% bounds 1.99 to 2.05) against the ≤0.50 gate, on a 3,000² LoTSS-DR3 window at Rapthor's island density, in Rapthor's two-pass mode on four cores, in one x86-64 container under Rosetta (`scripts/benchmark/measure_filter_skymodel.py`). The two used about the same CPU time, 211 s and 202 s, but Hebog kept 1.1 of its four cores busy and PyBDSF 2.2; LSMTool's filtering of the 101,144 WSClean-like components took 24 s of each, so the ratio cannot fall below 0.26 whatever the finder, and Hebog's part must fall from 162 s to about 22 s to pass. Hebog's own serial profile of the window is 25% background and RMS, 23% component fits and 5% association. On the dense LoTSS-Deep DR2 ELAIS-N1 sector (14,175², 123,186 sources), the first real Rapthor-like sector run, Serial took 8.5 h, about 7.4 h of it after component fitting, in association and the stages after it; on its central 5,000² four threads took 0.92 of the serial 2,138 s, so association both dominates a deep field and barely parallelises (task 54). With tasks 74 and 55 the central 5,000² takes 1,126 s Serial and 523 s on four Dask workers with identical products (15 October), though under the adapter's `compact` default of 13 October, with 35,065 sources against 0.19.0's 34,040. With tasks 74, 55 and 54 the whole sector took 4,652 s Serial (15 October) against 30,745 s, under the same change of profile, for 118,929 sources against 123,186. The quick-benchmark anchors show no regression on the Hebog curve. Against pinned `master`, Hebog on one thread against `master` on four container cores, the diagnostic ratios are 2.7 to 5.2 at 1,024² and 0.88 on the crowded 2,048² field, and on the 3,000² LoTSS field the two use the same CPU time: there the gap to the ≤0.50 gate is parallel occupancy, not the amount of work. About half of a large run is background/RMS and most of the growth beyond area is source association (risks below); No kernel reaches the native-code assessment's 10% gate. How one sector scales (task 73, run `task73-quiet`, 14 to 15 October, 16 GB task-memory budget): on a local Dask cluster of single-threaded workers the 10,000² anchor takes 2,036, 1,107, 767 and 754 s on 1, 2, 4 and 8 workers (speed-ups 1.84, 2.65 and 2.70) and the whole 15,402² mosaic 5,032, 3,009, 2,097 and 2,101 s (1.67, 2.40 and 2.40); twelve workers' 1.33 GB shares are refused by the multiscale tasks' 1.70 GB. Amdahl fits put the serial share at 23% and 29%, though both curves flatten at four workers for another reason: eight workers and the driver outgrow the 18 GiB machine and swap 15 to 35 GB, and the rounds that read most (catalogue rows, multiscale publication) then take five to seven times longer a task. The thread executor barely scales: 1,329 s on one thread and 1,119 s on twelve, with tasks 8.6 times slower, held by Python's global lock, so Rapthor's interim thread path cannot use a node's cores. Background refinement was the largest serial term, 155 s of the anchor's fit: 69,150 window batches (164,704 on the mosaic), each under Dask reopening the FITS file. Task 74 (run `task74`, 15 October) estimates them from one read of each 512² square, 780 tasks on the anchor: background takes 622 s instead of 1,235 s on one worker and 136 s instead of 332 s on eight, the driver's CPU 98 to 112 s instead of 151 to 163 s, and the anchor 1,423, 580, 515 and 596 s on 1, 4, 6 and 8 workers, 21 to 32% faster. Fitted over 1, 4 and 8 workers, the anchor's serial term fell from 478 to 404 s, but the share rose from 24% to 29% because the parallel work fell further (a burst of three to five cores in the Podman VM slowed the two-worker run, 903 s). Task 55 (run `task55`, 15 October, one worker, on task 74's batches) made the hierarchy decision linear, which was most of `find_sources`' own driver work outside the profiler's stages: 16 s instead of 70 s on the anchor and 50 s instead of 320 s on the mosaic, which now takes 3,783 s on one worker instead of 5,032 s, in 22,057 tasks instead of 184,900 (its other stages ran up to 22% slower on a busier machine). With both, no task runs for 83 s of the anchor's one-worker run and 223 s of the mosaic's, 6% of each, against 147 s on task 74's commit and 1,020 s on task 73's; the largest parts are background's driver steps (28 s and 73 s) and the RMS FITS write (12 s and 29 s). With tasks 74 and 55 together (run `task74-stack`, 15 October) the anchor takes 1,357, 749, 490, 429 and 438 s on 1, 2, 4, 6 and 8 workers, 43% less than task 73 at the best point; no task runs for 77 s of the one-worker run, and over 1, 4 and 8 workers the serial term is 263 s, a share of 20% against 24%, which closed task 74. What else holds one sector back: rounds of 7 to 25 tasks, as many as the tile grid and `maximum_tiles_per_batch` give, and beyond six workers the machine's six performance cores and swap, which reached 22 GB. In task 73 a run decoded 213 GB from Zarr and wrote 19,373 chunk files at 10,000² (703 GB and 45,587 on the mosaic), the same under every executor. Task 54 (run `task54`, 15 October, one worker, on tasks 74 and 55) batches object rounds a core at a time: a run decodes 154 GB and 393 GB, the anchor takes 1,305 s instead of 1,356 s and the mosaic 3,452 s instead of 3,790 s, and the mosaic's hierarchy overlap stage 73 s instead of 163 s; the island round's 32 more tasks cost 12 s more, about the completion-record parse each task pays (task 56); a repetition of the anchor under memory pressure agreed within 3%. |
| Science | Strongest evidence: the v15 campaign, which failed only against the earlier Hebog incumbent and not against released PyBDSF, PyBDSF `master` or Aegean, on images of ≤1,024². Since then, focused regression, Serial/Thread/Dask, equivalence and installed-wheel evidence only. The CI equivalence lane runs `find_sources` on the frozen 256² input against both PyBDSF references under both profiles; the isolated-source gates pass on sources and components under both profiles, with two bounded known differences: the `continuum` RMS tail is 5.5% at p95 against 5%, and the published mask holds about 92% of PyBDSF's island pixels (task 49). Source `Total_flux` is the summed fitted component flux and meets every binding limit against pinned `master` on independent realizations of both noise classes (`config/datasets/m1-flux-calibration.json`), binding pooled over the two (task 48). `E_RA` is a great-circle angle, as PyBDSF publishes it; its calibration passes on beam-correlated noise and is unqualified on a real high-declination field. The clipped window RMS has no truncation correction and reads 1.6 to 3.9% low on noise alone (task 68, deferred until the integration and scaling work is done). Whether the public finder shares the removed single-region fitter's edge-source uncertainty shortfall (98.8% against 99%; `LOG.md`, 6 October) is unmeasured. The meshes are fixed in pixels, so a beam wider than 10 pixels is refused (task 62). Rapthor-profile agreement (task 21, `just rapthor-agreement`, run `task21` of 13 October): over 19 cases and 22,142 sky-model component positions, Rapthor keeps or rejects alike with Hebog's mask and pinned `master`'s 92.8% of components under `compact` with a zero background, 91.8% with the estimate and 74.1 to 74.4% under `continuum`, against 99.29% for released PyBDSF 1.14.1; no lane reaches 99.5% overall or in any stratum but the masked one, of 3 components. On the ELAIS-N1 deep field `continuum`'s local-noise refinement reads a median twice `master`'s RMS at the faint islands it loses, 1,346 of 5,762 (task 75), and `compact` loses up to 9 bright components an image where the image edge cuts their source. Every lane publishes `DC_Maj` 0 for about 1,700 fits of 10″ or more against `master`'s 439, so more sources pass Rapthor's size cut. The maintainer chose `compact` with a zero background for Rapthor on 13 October, as an interim exception to the plan's rule, which falls back to `continuum` when no lane passes, and to be decided again after task 75. Agreement is compatibility, not correctness: against injected truth `master` covers 76% of the emission at 3σ, `continuum` 87% and `compact` 64%, and `master` covers 38% of a wide extended source; on ELAIS-N1 the negated image gives `master` 34 false islands and the islands `continuum` loses peak at a median 7.3 times the negative-pixel noise, so they are real (exploratory; task 76 adds these measures). |
| Blockers to 1.0.0 | Every task in the [path below](#path-to-100). Largest risks: the performance gap, the retained/rejected agreement gap (92.8% against 99.5%, which released PyBDSF misses too), the traced peak's growth with the image, the wide-object driver term above 3,000², the development machine's memory and disk, SKA-Low coverage without public SKA-Low images, and churn in Rapthor's `main` after its 9 October merge. |
| Next action | Agent: make Hebog's tasks scale on any Dask cluster (task 72), whose cost model must hold the memory a worker needs per core as well as its tiling, since task 73 found eight local workers swapping and twelve threads no faster than one. Task 76 may run alongside. Human: merge the stack of tasks 73, 74, 71, 55 and 54, add PyPI's Trusted Publisher and `pypi` environment, merge the switch to PyPI and then the 0.22.0 release, whose check passed on 15 October (task 13); then publish/review the prepared Rapthor patch, which needs that release, the first carrying `hebog.expected_source_count`, and file the Astropy report drafted on 5 October. Task 11's disk condition is met (59 GiB free on 12 October), but the ladder follows integration. |
| Deferred | Scientific improvements that are not confirmed incorrect supported outputs, until the Rapthor integration and the scaling work are complete (decision of 9 October): the clipped-RMS truncation correction (task 68), `continuum`'s local-noise repair (task 75) and the position-dependent PSF (task 15) sit before the freeze, and the rest is here. Scaling the background and local-noise meshes with the restoring beam, which would let beams wider than 10 pixels FWHM be supported: task 62 recovered every SNR ≥ 10 source to 22 pixels with the fine mesh scaled by FWHM/8, at about 2.5 times the local-noise read; reopen it when a target pipeline produces such beams. Every real Rapthor image in the archived cluster runs is at most about 7 pixels (1.5″ cells and 4 to 10″ beams; its normalization images use 5.9″ cells); only the synthetic demonstration sector exceeds 10. Moving the wide-object reductions onto the cores: the island, deferred-fit and catalogue-row rounds as associative partial sums, with summation-order rounding accepted, and a reviewed design for the local-noise median, which has no associative form. Reopen it when a tier's traced peak shows the term or when the cluster benchmark is planned, whichever comes first. Aegean comparisons (paused; reconsidered in the task 29 design), optional comparison finders such as ProFound or 2D SoFiA (see the [notebook guide](../docs/how-to/notebooks.md)), general science improvements outside Rapthor-consumed outputs, and native code without a passing profile gate. A counterpart to PyBDSF's second grouping rule, which joins two Gaussians in one island when the flux falls steadily from one peak to the other (decision of 10 October): task 21 found that Rapthor keeps and groups sky-model components by the mask's islands, which that rule does not change. Reopen a deferred issue if it becomes a confirmed incorrect supported output. |

## Definition of 1.0.0

Version 1.0.0 is the first release demonstrated to meet the project goal,
with every claim bound to reviewed evidence for that exact candidate:

- **Telescopes.** The standalone finder accepts standard FITS continuum
  images from any radio telescope that meet a documented header contract,
  and is validated first on LOFAR, SKA-Low and SKA-Mid images. It accepts
  their imager conventions (WSClean, CASA and SKA SDP products) or rejects
  them with a specific error.
- **Functionality.** Hebog is a supported, feature-flagged backend for
  Rapthor's `filter_skymodel`, selected through Rapthor's `source_finder`,
  at a pinned Rapthor and LSMTool revision:
  true-sky and flat-noise branches, the Rapthor profile, native catalogue,
  mask, RMS and source-count products, empty and blanked-image paths, retry
  and restart, and PyBDSF fallback. The standalone public API remains usable
  without Rapthor, Prefect, LSMTool or Dask.
- **Science.** The Rapthor profile reaches ≥99.5% retained/rejected component
  agreement with every safety stratum passing, and the frozen candidate
  passes prospective, powered, held-out parity/retention against pinned
  PyBDSF `master` (`c70103b`); a single check against released PyBDSF 1.14.1
  confirms Rapthor-profile agreement for users of the release. The evidence
  includes full images, not only cut-outs, from LOFAR, SKA-Mid (SDC1
  simulations and MeerKAT) and SKA-Low (MWA precursor data until SKA-Low
  data are public).
- **Performance.** On the development machine, matched complete
  `filter_skymodel` medians meet the runtime gate across the deployment
  envelope without a memory or Hebog-curve regression. The final cluster
  benchmark confirms them on the cluster's hardware.
- **Scalability.** Scale evidence uses LOFAR images only. On the development
  machine (18 GiB RAM), the 45,000² LOFAR-HD mosaic completes with peak
  memory bounded by tile size, although one `float64` copy of the image alone
  would not fit in memory. Results do not change with worker count, tile
  geometry, completion order or retry. A final cluster benchmark, run once
  for 1.0.0, processes the 90,000² LOFAR-HD mosaic on 1, 2, 5 and 10 nodes
  within the amended runtime, task-count, scheduler-overhead, memory and
  spill gates. Planner tests bound graph size and reduction depth for
  100,000² images on 100 to 200+ nodes. Release notes say that 100,000²
  images and that node count are designed for but not demonstrated.
- **Release.** Published on PyPI with portability, security, licensing,
  current documentation and independent radio-astronomy and engineering
  acceptance.

Rapthor's default cutover is a separate Rapthor decision taken after an
operational soak of the 1.0.0 backend; the PyBDSF fallback remains until then.

## Scope and resource rules

- **Use cases** (maintainer, 10 October 2026). Four, each a performance
  target; none may be optimized by regressing another:
    1. *One Rapthor sector across a cluster* of nodes with up to 192 cores,
       tens of nodes possible: the usual Rapthor run and the first
       performance focus.
    2. *One Rapthor sector on one node*: the other main Rapthor run, and the
       deployment gate's like-for-like comparison with PyBDSF.
    3. *Standalone use on a local machine* with smaller images, through the
       public API and the Serial or Thread executor, where setup and
       scheduler overhead dominate.
    4. *Standalone use on a cluster*, for an image too large for one node,
       on a Dask cluster the user starts.

  Several Rapthor sectors at once stay supported. Hebog defines what it
  needs from a Dask cluster to scale, and Rapthor or the user provides it;
  Rapthor may change its setup to do so, and owns how its workers serve
  DP3, WSClean and Hebog together
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md)).
  Rapthor builds Hebog's executor from its own layout and passes it in:
  its client when each node has several task slots, the target, otherwise
  a thread executor inside the worker's task (one single-threaded worker a
  node, today's layout, retired inside Rapthor once the target is in
  place). The layouts are drawn on
  [How Hebog runs on Rapthor's Dask layouts](../docs/architecture/rapthor-execution-layouts.md).
  The target is two-dimensional continuum images; spectral cubes and a time
  axis may follow, so the executor protocol stays blind to the image's
  dimensions, and adding an axis is a new ADR.
- **Compute.** Development, checks and benchmarks run on the maintainer's
  machine (Apple M3 Pro, 12 logical CPUs, 18 GiB RAM). A cluster of up to 10
  nodes runs one final benchmark for 1.0.0 and never blocks development.
  Record its hardware when that benchmark is scheduled.
- **Disk.** The maintainer frees disk to about 60 GB before the local
  envelope passes 22,500². The 45,000² tier needs about 8.1 GB of input, up
  to 16 GB of RMS and mask output and up to about 24 GB of uncompressed Zarr
  intermediates. The local ladder stops at 45,000²; 90,000² runs only on the
  cluster.
- **Data.** Scale testing uses public LOFAR images; no generated 100,000²
  image or simulated SKA-Low image is built for now, and the only generated
  large image is the 10,000² wide-object diagnostic. The public LoTSS-Deep
  DR2 ELAIS-N1 apparent and primary-beam-corrected pair is the
  representative two-branch Rapthor input. SDC1 cut-outs serve science
  checks for SKA-Mid. See [reference images](#reference-images).
- **Rapthor revisions.** Rapthor's `main` at `d0e7e148`, the Prefect/Dask
  line since its 9 October 2026 merge (`master` is the CWL/Toil release
  line and not a target), and LSMTool's `master` at `9bac2f7` (v1.9.0 plus
  15 commits). Pinned at task 16 at `c6196cb4`, replacing the Phase 0 trace
  (`b1a6467`), and moved at task 23's checkpoint on 13 October past one
  commit that changes BDA defaults only. Pins move forward only at the
  checkpoints listed under [Risks](#risks). If Rapthor declares a different LSMTool revision, record
  both and test the latest LSMTool.
- **Limitations that block 1.0.0.** Of the limitations accepted for v0.7.0,
  those that change Rapthor-consumed fields must pass before 1.0.0:
    - `E_RA`/`E_DEC` uncertainty calibration (Rapthor excludes sources at
      ≥2 arcsec). Calibration passes on beam-correlated noise (RA and Dec
      pull standard deviations 1.015 and 1.006, `LOG.md`, 24 September);
      what remains is qualification on a real high-declination field. `E_RA`
      is a great-circle angle, matching PyBDSF and the fixed angle Rapthor's
      astrometry cut compares it with.
    - `Total_flux` tails, under the limits in the
      [scientific gates](#scientific-gates) table (`Isl_Total_flux` is only
      carried through Rapthor's astrometry check).
    - Faint association where it changes island grouping, and therefore
      patches.

  The other accepted limitations stay documented limitations.
- **Iteration budgets.** The budgets under
  [Delivery policy](#delivery-policy) are the normal feedback loop and
  replace long campaigns.

## Delivery policy

Ship frequent, useful experimental `0.x` increments rather than phase-sized
batches: normally one release for each merged task that changes behaviour.
Milestone numbers survive only as identifiers in `LOG.md` and this plan.

Development runs on the maintainer's machine and favours fast iterations over
long campaigns and benchmarks. Every check has a budget on that machine:

- **Change check (about 15 minutes):** relevant tests, the quick science check
  and, for performance-relevant changes, the quick benchmark's default tier.
  Runs for every change that can affect science or runtime.
- **Release check (about 1 hour):** the change check, Serial/Dask agreement
  on the largest anchor whose two runs fit the hour (10,000² today) and the
  installed wheel. Runs before each `0.x` release. The quick benchmark's
  large tier belongs here but takes hours at current speed, so it runs for
  profiling and before a release that claims a runtime change, and is never
  waited on for other releases.
- **Tier gate (up to a day, unattended):** the M2 gate on a new tier's
  anchor. Runs once for each envelope raise, and never as part of a release
  check.
- **1.0.0 qualification (once):** one powered science study sized to finish
  overnight on the development machine, and one benchmark on the cluster.
  Neither blocks `0.x` development or releases.

A check that outgrows its budget is sampled, split or moved to a less frequent
level; its budget is not silently extended. PyBDSF outputs and timings are
computed once for each input, reference revision and host, cached outside Git
with checksums, and reused. A defect that escapes the quick checks adds its
case to the fixed case set.

PR CI shards the complete supported-platform suite, reports a separate unit
check early, and combines branch coverage before applying the project floor.
Only the narrowly defined documentation-only path may omit execution jobs;
every `main` push runs full CI. Existing required check names remain gates
over the applicable jobs. The [contribution guide](../docs/how-to/index.md#pull-request-feedback)
defines the matrix, timing cache and routing rule. Hosted timings guide CI
scheduling only; they do not change the scientific or performance gates.

The four levels of done stay distinct:

- **Merge:** a coherent reviewed change with passing applicable tests and
  accurate documentation. Tooling and documentation changes need not wait for
  scientific qualification. Merge each PR in a sequence before branching the
  next, so CI isolates the responsible change.
- **Experimental release:** a tested package that states its unqualified
  science and current limitations and has no unresolved confirmed incorrect
  supported output. It need not establish general PyBDSF parity, the Rapthor
  speed target or facility scale.
- **Scientific qualification:** candidate-bound parity and quality retention,
  fresh held-out evidence and independent scientific and engineering
  acceptance. An experimental label never turns a failed or underpowered check
  into a pass.
- **Rapthor deployment or default cutover:** separately qualified workflow
  behaviour, complete-path performance and operational acceptance, with the
  feature-flagged PyBDSF fallback retained until the acceptance matrix passes.

Ownership follows
[`AGENTS.md`](../AGENTS.md#changes-releases-and-handoff): the agent
implements, validates, documents and commits locally; the human pushes,
merges, runs notebook refreshes and makes scientific and priority decisions.
Explicit user authorization may delegate a push or PR update to the agent.
Release Please alone edits versions, the changelog and release notes.

## Collaboration and repair decisions

These rules govern agent work on this plan and are referenced from
[`AGENTS.md`](../AGENTS.md).

- The agent owns routine completeness checks, integration checks and clear
  recommendations. Do not depend on the user discovering missing checks,
  requesting a cheap diagnostic or reconstructing status across
  conversations. Reserve human attention for scientific interpretation,
  priorities and trade-offs that require human judgment.
- Before a scientific or campaign repair, write a short decision statement in
  the existing task or plan: observed problem, proposed cause, independent
  test, expected measurable change and stopping condition. Distinguish a
  correctness defect, agreed-gate failure, operational failure and optional
  improvement; an aggregate failed endpoint alone does not establish a cause.
- After two repairs aimed at the same mechanism produce no material change
  against the stated expectation, review the diagnosis and recommend a
  bounded next step before another full replay. This is a reassessment
  trigger, not permission to abandon required work, change gates or retry
  closed evidence.
- Follow the approved scope and severity policy. Keep development closure,
  scientific qualification, release and default cutover distinct, as in the
  delivery policy above. Record optional improvements as deferred work rather
  than automatically expanding the current milestone. Known incorrect
  supported outputs remain release blockers; a phase label or accepted
  development limitation cannot waive them.
- Carry existing authorization forward within its scope. Complete authorized
  preparation and present a concrete recommendation before requesting a new
  scientific or resource decision. Explain the exact boundary requiring that
  decision; do not add approval steps for routine reversible work.
- At milestone reviews, use Git history, PR discussion and existing evidence
  to assess time to actionable diagnosis, avoidable campaign interruptions,
  repairs without useful change
  and user effort needed to recover status or scope. Use these observations
  to improve the workflow, not commit counts, test totals or documentation
  volume as productivity targets. Do not introduce a separate tracking
  framework.

## Path to 1.0.0

The tasks below are numbered in the order they were created, and a number is
a stable identifier: a completed task is removed and its number is not
reused. The sections, and the rows within them, are in the order the tasks
are expected to finish. Each is a bounded work item that merges, and
normally releases as a `0.x` increment, within the iteration budgets; split a
task when a measured result reveals independent changes. Unless a task says
otherwise, the agent implements and validates on the development machine and
the human merges. A qualification, scale or deployment task authorizes only
its stated claim and still needs the named human decision.

Three rules govern the sequence. **Measure before changing:** nothing is
optimized or re-architected without a profile, and no science-touching change
merges without `just quick-science-check`. **One tier and one release at a
time:** the public envelope rises only through its tier gate, and every raise
is a release. **Products unchanged through a refactor:** a change made for
readability or structure leaves the quick check's catalogue, RMS and mask
byte-identical, with only the composition hash moving, and no production
file loses coverage.

The order below was set on 9 October 2026 and amended on 10, 13, 14 and
15 October (`LOG.md` and Git history):

1. **Rapthor integration before the size ladder** (task 76 remains), with
   releases on PyPI from 0.22.0 so Rapthor can install Hebog (task 13,
   decision of 15 October).
   The integration waits on no tier: its inputs and Rapthor's demonstration
   sector (3,000²) are inside the 15,402² envelope. Rapthor's `main` runs
   the filter step in a fresh interpreter per sector through LSMTool's
   registry; on 10 October the maintainer chose to replace that call with a
   native Prefect task running Hebog in-process on Rapthor's Dask worker
   (ADR-004 amendment), first on a thread executor. Task
   23's first matched measurement, on a 3,000² LoTSS-DR3 window at
   Rapthor's island density (13 October), put the step at 2.03 times
   pinned `master`'s and association at 5% of Hebog's work there, so tasks
   54 and 55 wait in the scaling block. The 3,000² demonstration sector's
   synthetic baselines give a 45″ beam, 30 pixels at 1.5″, which the finder
   refuses, while every real Rapthor image is at most about 7 pixels
   (decision of 13 October; task 62 stays deferred). The native task
   reserves memory for the sources the image's peaks bound and falls back
   to PyBDSF when its worker cannot hold the analysis (decision of
   14 October).
2. **One sector across the cluster** (task 72), then the size ladder to
   22,500² (tasks 56 and 11). Rapthor usually
   images one sector, 17,000 to 20,000 pixels a side by default (task 16),
   on nodes of up to 192 cores and tens of nodes. Task 73 measured a
   serial share of 23 to 29% on the local Dask curve, flattening at four
   workers where memory runs out, so the serial share is cut before the
   Dask topology is tuned (decision of 10 October); task 74 cut it to 20%
   on the 10,000² anchor (run `task74-stack`). Task 72 comes before the
   ladder because Rapthor's interim thread path cannot use a node's cores
   (decision of 15 October).
3. **The deployment performance gate on the integrated step** (tasks 22
   and 23), then the 45,000² tier (task 12) and scale beyond one machine
   (tasks 24 to 27).
4. **Scientific improvements are deferred** until the integration and
   scaling work above is complete: tasks 15 and 68 sit before the freeze and
   the deferred row holds the rest. A confirmed incorrect supported output
   reopens its item at once; a documented bias or limitation does not.

Tasks 54 and 56 come from the whole-codebase review of 4 October, task 62's
deferral from task 45's repair, task 68 from task 65's diagnosis
(`LOG.md`), and tasks 75 and 76 from task 21's measurement.

### Clean-up and refactoring

A removal starts with the test that fails for the reason its row states. A
refactor starts with the quick check and the module's tests passing before
and after, merges as a `refactor:` commit, and releases only when it changes
a public name. The review's figures come from small synthetic inputs, so a
task that changes cost or memory confirms its figure on a real anchor before
it closes.

### M3 — Rapthor integration

Rapthor's `main` runs one Prefect `filter_skymodel` task per sector on a
Dask task runner (`local_dask` or `external_dask`); the task starts a fresh
interpreter that calls LSMTool's `filter_skymodel(source_finder=...,
ncores=...)` with native threads pinned to one, and LSMTool dispatches
through `KNOWN_SOURCE_FINDERS`, `bdsf` plus `sofia` as an optional extra. The
maintainer decided on 10 October that Rapthor replaces that call with a
native Prefect task running Hebog in-process on the Dask worker, with the
PyBDSF subprocess kept as the fallback. Rapthor usually images one sector,
so one sector across the cluster is the performance focus; several sectors
in flight stay supported, each on a node when there are enough nodes.
The prepared patch supports Rapthor's current one-single-threaded-worker-per-node
layout with a ThreadExecutor. This is the maintainer-approved integration
boundary of 12 October; task 72 supplies the distributed path and retires
that interim thread path. LSMTool registration remains deferred. Until the
Rapthor patch merges, the integration container installs its recorded local
commit.

Rapthor runs the `compact` profile with PyBDSF's zero mean map, the
maintainer's interim choice of 13 October from task 21's measurement: of
the four lanes it makes Rapthor keep the components pinned `master` keeps
most often, though no lane reaches the 99.5% target, and the plan's rule
would have fallen back to `continuum`, which agrees least on real LOFAR
fields. Agreement with `master` is compatibility, not correctness: against
injected truth `master` covers 76% of the emission at 3σ, `continuum` 87%
and `compact` 64%, and `master` misses most of a wide extended source. The
profile is decided again once task 75 repairs `continuum`'s local noise,
against `master` and against truth (task 76). The adapter defaults to
`compact` and zero, and so does the prepared patch's parset.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 76 | Agent | Measure each lane's correctness beside its agreement with `master`. | `just rapthor-agreement` also reports, for every lane, `master` and the released control: mask decisions and emission recall against injected truth on the generated cases, the ideal mask being the noiseless emission at `threshisl` sigma or more connected to a `threshpix` peak; completeness and flux of sources injected into the real LOFAR images (the LoTSS-DR3 window and the ELAIS-N1 pair) by SNR; false islands on the negated real images; and each RMS map against the RMS of negative pixels, which faint sources cannot inflate. Done when these are tested pure functions within the release-check budget, the progress page summarises them, and task 29's design pairs the `master` gate with truth limits. Exploratory scripts on 13 October found on ELAIS-N1 34 false islands for `master`, 55 for `compact` with zero background and 9 for `continuum`, and `continuum`'s RMS 2.3 times the negative-pixel noise at the islands it loses. |

### One sector across the cluster

Rapthor usually images one sector, so the filter step has the cluster to
itself: nodes of up to 192 cores, and tens of nodes. The design stays
Dask-native and simple: Hebog's tile tasks are single-threaded and
numerous, Dask schedules every core, and no thread pool is nested inside a
Dask task. Hebog's arrays stay NumPy behind its executor protocol, as
ADR-004 and ADR-005 decided, not Dask arrays. The aim is a strong-scaling
curve for one sector that keeps falling while cores are added, not the use
of every core; several sectors share the cluster beyond the point where
one stops scaling.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 72 | Agent | Make Hebog's tasks scale on any Dask cluster, Rapthor's included. | The caller builds the executor and states the cores Hebog may use, defaulting to the client's capacity, since a client's capacity counts threads that DP3 or another analysis holds. Each stage chooses its tile core from its halo and its task count from batching, by a stated cost model fitted to task 73's measurements, so parallelism rises without small cores multiplying halo overhead (products do not depend on either). The memory each task declares follows the chosen core, since it is computed from the task's read; an analysis started inside a worker task secedes while it waits on its tile tasks; and the run's timing record states the tiling and core budget chosen, leaving the product hashes unchanged. Rapthor's patch gains its distributed path here: it passes its client and its resource names (`memory_resource`, `core_resource`) to `DaskExecutor`, reserves the analysis memory on the driving task, and retires its interim thread path. What Hebog needs from a cluster is documented for any caller ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md)), including that workers limit their native thread pools to their declared cores, with one way Rapthor can provide it beside DP3 and WSClean in the existing patch. It starts from run `task74-stack`'s curve (1,357 s on one worker, 429 s on six, no task running for 77 s) and takes what task 74 left, contention for cores and memory (eight workers swapped up to 24 GB) and rounds of only 7 to 25 tasks; it also groups the composition's run settings (executor, work directory, generation and tile core) that task 71 left for it, and, once tasks are packed by declared memory, re-audits each round's declaration against its measured peak (`scripts/benchmark/audit_task_memory.py`): background's grouped pilot declares about five times its peak (decisions of 15 October). A small image stays one tile with no scheduler overhead (use case 3). The true-sky analysis and the flat-noise estimate submit their tile tasks to the executor together, through the executor rather than a thread of Hebog's own, so the serial reference stays single-threaded; today they run one after the other. Done when products are byte-identical across the thread and Dask paths in the executor contract suite, a local multi-worker Dask cluster runs one analysis, several concurrent analyses and workers joining between analyses without deadlock or changed products, and task 73's curve is re-measured with the cost model's tiling. |

### M4 — Deployment performance gate

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 22 | Agent proposes, human freezes | Freeze the initial deployment envelope. | Sizes and workloads match Rapthor's production sectors (task 16) and fit the development machine, and the envelope tier that covers them is admitted. Task 16 found Rapthor's default and benchmarked LOFAR sectors at 17,000 to 20,000 pixels a side and only its demonstration sector at 3,000², so the envelope is at least the 22,500² tier (task 11). |
| 13 | Human | Switch uploads from TestPyPI to PyPI. | From 0.22.0 rather than after the envelope is frozen (decision of 15 October): the prepared Rapthor patch's optional Hebog dependency must install from PyPI, and the name `hebog` is unclaimed there, so a public patch naming it would invite a squatter. Releases stay experimental `0.x` with an alpha classifier, and the release status keeps the envelope. The publishing job, installation instructions, guide and release status have changed; the maintainer adds PyPI's Trusted Publisher and `pypi` environment ([publishing guide](../docs/how-to/publish-releases.md)) before merging that change and then the 0.22.0 release. Done when 0.22.0 installs from PyPI. |
| 23 | Agent | Run matched complete `filter_skymodel` benchmarks, then optimize until the runtime gate passes. | Hebog, through Rapthor's native task on one node with the executor Rapthor deploys there, and pinned `master`, through Rapthor's PyBDSF subprocess on the same cores, run in the same Linux container on the development machine, with cached reference timings; one sector across several nodes is the cluster benchmark's (task 27). `scripts/benchmark/measure_filter_skymodel.py` measures a cell: it writes the sector from a real image at real resolution, with WSClean-like component lists on the image's island pixels, and runs one warm-up and five measured repetitions of each finder in fresh containers of the matched benchmark image, alternating them; the image is x86-64 and runs under Rosetta on the development machine, so the cluster's hardware confirms the figures (task 30). The ratio and its upper one-sided 95% bound pass on every envelope cell; memory and Hebog-curve non-regression and the quick science check pass. Native code enters only through the native-code gates and an accepted ADR. |

### M2 — Climb the local size ladder

Each tier passes the same gate before its limit and release status change:
exact tiled-invariance tests, the quick science check, a quick benchmark on
both sides of any crossover, a reproduced `just traced-peak`, and the task
memory audit (`scripts/benchmark/audit_task_memory.py`) passing on the
tier's anchor, since the object rounds' peaks grew with each larger anchor
measured for task 17. The gate
is its own check level under the [delivery policy](#delivery-policy). Its
memory measure is `tracemalloc`'s peak, which is deterministic and is
measured only by `just traced-peak`; a peak from anywhere else is not
reproducible evidence, and peak RSS, which varies 42% with machine load, is
reported beside it as an envelope, never as the threshold. Science on the
large images uses the LoTSS-DR3 PyBDSF catalogue and maps and the per-facet
LOFAR-HD PyBDSF catalogues, with global invariants, as in ADR-005.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 56 | Agent | Stop per-task and driver costs growing with the image. | The local-noise round builds every request before submitting any, each with its own subset of the pilot grid: on synthetic grids, about 1.9 of background/RMS's 3 bytes a pixel. Under Dask every task parses the completion marker of each generation it reads again, 16 MB and 0.42 s at 15,402²; after task 54 the mosaic's island round ran 32 more tasks for 12 s more. Done when the pilot grid is published once and read by window, or requests are built within the in-flight window; each generation's completion record is split by tile, so a task reads only the entries for its window, rather than cached whole for the process, which would hold memory no task declares, about 0.7 GB a generation at 100,000² (decision of 15 October; task 25 reviews the store layout); `scripts/benchmark/attribute_traced_peak.py` confirms the background/RMS slope on the 10,000² anchor; and Serial and Dask products stay byte-identical. |
| 11 | Human frees disk, agent raises | Raise to 22,500² on the LOFAR-HD ELAIS-N1 mosaic. | About 60 GB of disk is free before the run, and the mosaic's restoring beam is read and recorded first: its name suggests about 3 pixels a beam, where the support pass's opening used to remove most 5 to 6σ compact sources (`LOG.md`, 4 October). The tier gate passes, recording the diagnostics' bright candidate count and largest bright-region read, and the raise is a release. |
| 12 | Agent, human approves | Raise to 45,000² on the LOFAR-HD mosaic. | The tier gate passes and the raise is a release. This is the out-of-core demonstration: the run completes on 18 GiB with the traced peak bounded by tile size although one `float64` copy of the image (16 GB) would not fit. The local ladder ends here. |

### M5 — Prepare scale beyond one machine

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 24 | Agent | Bound the graph for 100,000² at 10 and at 200 nodes without running the science. | Planner tests show at most 50,000 tasks, bounded reduction depth, bounded driver memory and a valid memory admission for both topologies. |
| 25 | Agent | Qualify the Zarr store and the restart and recovery path locally. | Atomicity, owned-chunk writes from concurrent local workers, codec and chunk geometry, missing chunks and injected failures pass within an admitted memory budget. Zarr v3's sharding codec is evaluated against one file per chunk, because thousands of tasks on a cluster's shared filesystem mean many small files; task 73 measured 19,373 chunk files and 213 GB of decoded reads a run at 10,000², and 45,587 and 703 GB on the whole mosaic. Shared-storage throughput is measured by the cluster benchmark. |
| 26 | Agent proposes, human approves | Amend the scalability contract. | `config/benchmarks/phase-0-scalability.json`, the performance and scalability contracts page and the `test-scalability` recipe describe the development-machine tier and the final 1, 2, 5 and 10-node benchmark. The 50, 100 and 200-node gates are kept as design targets, not deleted. |
| 27 | Agent | Package the cluster benchmark. | One command and a short guide run one Rapthor sector at its default size through Rapthor's native task, and Hebog standalone on the 90,000² LOFAR-HD mosaic on a cluster the guide starts (use case 4), at 1, 2, 5 and 10 nodes, plus the 22,500² and 45,000² versions for size scaling, and record evidence, the hardware and a scaling-model fit. A dry run with a local Dask cluster at small sizes passes, so the cluster session measures rather than debugs. |

### Deferred science, before the freeze

These are scientific improvements, not confirmed incorrect outputs, and wait
until the milestones above are complete (decision of 9 October); a confirmed
incorrect supported output reopens its item at once. All three must close
before the candidate is frozen (task 28).

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 15 | Agent, human dispositions | Decide how to handle a point-spread function that varies across the field. | LOFAR facets and MWA mosaics (which ship PSF maps) have a PSF the header beam cannot describe. Measure the effect on fluxes and sizes with injected truth, then accept a PSF map input or document the limitation with its measured effect. |
| 68 | Agent measures, human decides | Measure a truncation correction for the clipped window RMS. | The window statistic clips at 3σ around the median and takes the standard deviation of what remains, with no correction for the truncation: 35-pixel windows read 1.6% low on white noise and 3.2 to 3.9% low on beam-correlated noise, and `empty-noise` publishes 0.959 of the injected noise. PyBDSF applies the PySE correction, about 1.4% at κ = 3 (`LOG.md`, task 65 diagnosis). Done when the correction's effect on the quick check, the equivalence lane and the position and flux uncertainty calibration is measured, and the maintainer has decided whether to apply it. |
| 75 | Agent, human dispositions | Stop `continuum`'s local-noise refinement taking faint sources for noise. | `continuum` refines the local noise on 35-pixel windows everywhere, and a window that holds faint sources reads their emission as noise. On task 21's ELAIS-N1 deep field (2,048² at its centre) it loses 1,346 of pinned `master`'s 5,762 islands, `compact` 257, and its RMS at the islands it loses is a median 2.0 times `master`'s where `compact`'s is 0.94; it also misses one of five injected sources on the quick check's varying-noise case that `compact` publishes. Independent evidence agrees: there `continuum`'s RMS is 2.3 times the RMS of negative pixels, which faint sources cannot inflate, `master`'s 1.13 times, and the islands it loses peak at a median 7.3 times that noise while `master` has at most 34 false islands on the negated image. Task 68 measures the same windows' clipping bias. Done when a repair's effect on `just rapthor-agreement`, with task 76's truth measures, and on the quick check is measured, with `continuum` losing no more of `master`'s islands on the ELAIS-N1 cases than `compact` without losing injected sources; the maintainer has decided whether to apply it; and the Rapthor profile is decided again from agreement and truth (decision of 13 October). |

### M6 — Qualification and 1.0.0

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 28 | Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed; a later change restarts only the affected qualification tasks. The Rapthor and LSMTool pins move forward here for the last time. |
| 29 | Agent designs, human approves | Run one powered parity/retention study with fresh held-out and public-survey data, sized to finish overnight on the development machine. | Every binding endpoint passes under a prospectively reviewed contract, population and power design, including the limitations that block 1.0.0, a per-noise-class check of the `Total_flux` rows and the LOFAR, SKA-Mid and SKA-Low families in the 1.0.0 definition. The design decides the retained/rejected gate's binding form: released PyBDSF 1.14.1 keeps or rejects alike with pinned `master` 99.29% of task 21's components, 98.6% in the crowded stratum, below the 99.5% target (decision of 13 October). Closed failed campaigns are never reused as confirmation. |
| 30 | Human runs, agent analyses | Run the cluster benchmark once. | Strong scaling at 1, 2, 5 and 10 nodes and size scaling across the 22,500², 45,000² and 90,000² mosaics meet the amended gates, with invariant results and the task 23 runtime gate confirmed on cluster hardware. A failure becomes a normal `0.x` repair task. |
| 31 | Agent | Check released PyBDSF 1.14.1 once. | One matched run against 1.14.1, cached for reuse, confirms Hebog ≤0.50× the release on the deployment envelope and Rapthor-profile agreement against it. A failure is reported with its cause before the 1.0.0 decision. |
| 32 | Human runs in Rapthor, agent supports | Run the operational trial behind the Rapthor flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| 33 | Agent assembles, independent reviewers accept | Assemble the readiness packet and obtain acceptance. | The packet binds science, Rapthor profile, performance, scale, portability, security, licensing, packaging and current documentation to the frozen candidate, with separate radio-astronomy and engineering acceptance. |
| 34 | Human | Release 1.0.0. | Release Please produces 1.0.0 (for example through a `Release-As: 1.0.0` commit footer) and the package publishes to PyPI. Release notes state that 100,000² images and 100 to 200+ nodes are designed for but not demonstrated. |

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hebog's step stays slower than PyBDSF's: 2.03 times pinned `master`'s on task 23's first matched measurement, where both used about the same CPU time but Hebog kept 1.1 of four cores busy and PyBDSF 2.2. | Task 23 fails. | Profile first; raise parallel occupancy (tasks 73, 74 and 72) before constant factors; use the native-code gates only for a profiled kernel. Report the gap honestly at each milestone. |
| LSMTool's filtering of WSClean's component list is part of the step for either finder: 24 s of PyBDSF's 92 s there. | The ratio cannot fall below that share however fast the finder; if the share reaches half of PyBDSF's step on production sectors, the ≤0.50 gate cannot pass. | Measure the share on production-size sectors with realistic component lists before freezing the envelope (task 22); LSMTool's filtering is Rapthor's to optimize. |
| Hebog's mask makes Rapthor keep different sky-model components from pinned `master`'s: 92.8% agreement at best (task 21), where released PyBDSF reaches 99.29%. | The 1.0.0 science gate fails, and Rapthor's calibration model differs from PyBDSF's, most on deep LOFAR fields. | Task 75 repairs `continuum`'s local noise; task 76 measures each lane against truth, so a profile is not chosen for copying PyBDSF's errors; task 29 decides the gate's binding form against the release control and truth; `just rapthor-agreement` re-measures every lane at each pin move and science change. |
| An object wider than the read budget brings its own pixels to the driver in the island, deferred-fit and catalogue-row rounds, at up to 186 bytes a pixel. | Driver memory scales with the wide segments of a round, not the tile, and the catalogue-row round gathers every pixel of each with no cap on its size, so the declared limit is the field-filling figure: about 1.7 GB at 3,000², 19 GB at 10,000², 44 GB at 15,402² and 1.9 TB at 100,000². The one measurement (27 September) is the generated 10,000² case's diagonal filament, 553,817 pixels for about 100 MB; a filament of that width spanning 100,000² would be about 5.5 million pixels, about 1 GB, an extrapolation of one object rather than a bound. A smooth object wider than the 150-pixel background box is absorbed by the background estimate, which limits what one smooth object can bring, not what a connected network of narrow filaments can. No real LoTSS-DR3 object comes within a factor of ten of the budget. | Carried as deferred work: sums and first maxima on the cores first, then the median design; reopened when a tier's traced peak shows the term or when the cluster benchmark is planned. A connected network of narrow filaments is the diagnostic that would measure the term's growth. |
| Extended association cannot be made exactly tile-invariant. | A tier stalls or changes science. | Test analytic shells and filaments crossing corners at each tier; escalate a scientific trade-off to the human rather than weakening invariance silently. |
| Scheduler, reduction or storage bottlenecks appear only above 10 nodes. | A later deployment at 100+ nodes fails or scales poorly. | Planner bounds for 200 nodes, a scaling model fitted to the cluster benchmark, and an explicit "not demonstrated" statement in release notes. |
| Large public images have minimal or non-standard headers; the HD mosaic is published "for browsing only". | Anchors cannot run unmodified, or their science comparison is weak. | Headers checked 16 and 28 September against the input header contract; explicit request metadata; per-facet HD images and catalogues for science; LoTSS-DR3 mosaics as the fallback scale anchors. |
| No large public SKA-Low image exists. | SKA-Low coverage relies on MWA precursor data. | GLEAM-X DR1 with its PSF maps (its Aegean catalogue is diagnostic only), and SKA-Low science-verification data once released (expected from 2027). |
| Rapthor and LSMTool change frequently; Rapthor's `main` merged its Prefect/Dask workflow on 9 October 2026 and is still settling. | Adapter, contract and benchmark churn, or a backend that only works on a stale revision. | Pin Rapthor `main` and LSMTool `master` at task 16 and move both pins forward only before the patches (task 20), before the matched benchmarks (task 23) and at the freeze (task 28), rerunning the contract audit, the acceptance scenarios and the profile-agreement check each time and recording the revisions and audit outcomes in the commit, with exact contract and evidence references. |
| The passes keep records from every tile: the tile summaries' per-label records, which keep every candidate island, the per-tile island summaries and the reconciled label mappings grow the traced peak about 1.7 bytes a pixel, and background/RMS grew about 3 bytes a pixel, unattributed on a real image (29 and 30 September); on synthetic grids the local-noise requests account for about 1.9 of it (4 October). Traced between tasks (task 17, 12 October), the analysis grows with the sources found, about 42 KB each, and only 0.17 bytes a pixel besides: 1,557 MiB on the ELAIS-N1 deep field's central 5,000² (34,092 sources), 978 MiB on the whole 15,402² mosaic (19,103). | At those slopes the multiscale peak reaches about 2.1 GiB at 22,500² and 4.3 GiB at 45,000², and background/RMS overtakes it near 27,000² and reaches about 6 GiB at 45,000²; task 12 fits 18 GiB only while resident memory stays within about three times the traced peak, and at 100,000² the driver could not hold them. The full ELAIS-N1 sector (123,186 sources) would hold about 5.1 GiB in its analysis, which a Rapthor worker must reserve. | Before task 12, task 56 stops the driver holding the local-noise requests and attributes the term on a real anchor with `scripts/benchmark/attribute_traced_peak.py`; shard, stream or drop the kept records, such as candidates that can never become islands; task 24's planner bounds include them. Meanwhile `hebog.analysis_memory_bytes` states the analysis's memory from an expected source count. |
| The development machine's 18 GiB RAM and free disk limit local tiers. | Tiers above 22,500² stall, or runs spill to disk and slow iteration. | Tile-bounded memory, once the traced peak's growth above is bounded; about 60 GB of free disk before tiers above 22,500²; 90,000² only on the cluster. |
| Source association costs more than the image grows: 1, 82 and 479 s traced for 659, 7,146 and 16,084 sources, about the 2.2 power (29 September). On the dense LoTSS-Deep DR2 ELAIS-N1 sector, 123,186 sources at 14,175², a serial run took 8.5 h, about 7.4 h of it after component fitting (11 October). | A dense Rapthor sector already takes hours inside the current envelope, and at 45,000² association alone could take many more, making the tier gate impractical. | Task 55 made the hierarchy decision linear: the driver work that holds it fell from 70 to 16 s on the 10,000² anchor and from 320 to 50 s on the 15,402² mosaic (one worker, 15 October), while the hierarchy overlap stage is unchanged (148 and 163 s on the mosaic); ELAIS-N1's central 5,000² took 1,126 s Serial and 523 s on four Dask workers on 15 October, against 2,137 s and 1,543 s on 11 October, though under a different profile; its whole sector, with task 54 too, took 4,652 s Serial against 30,745 s, under the same change of profile (15 October). Task 54 removed the other cause, batch reads that were strips across the image: the mosaic's hierarchy overlap stage takes 73 s instead of 163 s and source labels 38 s instead of 65 s (one worker, 15 October). |
| Short checks miss a rare regression, or scientific campaigns absorb the schedule again. | A defect reaches a `0.x` release, or performance and scale slip. | Releases stay experimental and each escaped defect adds a fixed case; iteration budgets, cached references and endpoints limited to Rapthor-consumed fields hold the schedule; the one powered study at task 29 is the backstop. |
| One sector must use clusters of nodes with up to 192 cores, and four local Dask workers take 0.38 and 0.42 of one worker's time on the 10,000² and 15,402² anchors, no faster at eight (task 73); with tasks 74 and 55 the 10,000² anchor takes 0.36 on four and 0.32 on six, no faster on eight (run `task74-stack`). | A serial share of 20% on the anchor caps one sector's speed-up near five whatever the cores; a worker needs about 2 GB a core for the multiscale tasks, so a node short of memory swaps before its cores are busy; small tiles add halo overhead; Dask's scheduler handles a few thousand tasks a second; Python's global lock throttles a worker process with many threads; concurrent sectors could deadlock workers that run one task each. | Task 73 measured the serial share by stage and task 74 cut it from 24% to 20% on the anchor before task 72 tunes the topology, with the memory a core needs in its cost model: capacity-sized tiles, single-threaded tasks on several worker processes a node, a resource annotation and seceding while waiting. The cluster benchmark reports where one sector stops scaling. |
| The Rapthor patch depends on upstream acceptance. | The native backend cannot be selected from released Rapthor until the patch merges and releases. | The integration container installs the prepared patch at a recorded commit. Rapthor calls Hebog directly, so no LSMTool registry patch is required. |

## Scientific gates

Analytic or injected truth is primary. Pinned PyBDSF `master` at `c70103b`
(`v1.14.1-40`, the Phase 5 reference) is the binding finder reference.
Released 1.14.1, which Rapthor installs today, is checked once at task 31.
The two diverge scientifically (14 versus 12 sources on the representative
3,000² image), so neither is truth. Later upstream `master` commits are
adopted only by a deliberate plan decision, which invalidates cached
reference outputs. Aegean comparisons are paused: they are neither binding
nor run routinely while development focuses on PyBDSF, the finder Rapthor
uses, and the task 29 design decides whether to reinstate them. No finder is
scientific truth.

- Each campaign uses its own prospectively reviewed endpoint registry and
  decision contract. Choose a whole incumbent before viewing results; never
  combine historical best values into a synthetic comparator.
- Require every applicable relative PyBDSF and incumbent Hebog comparison,
  with fixed practical margins and the conjunctive one-sided confidence rule.
  Inconclusive binding evidence is not parity. An old candidate's uncertainty
  exception does not transfer to a replacement.
- Freeze population, semantic applicability, independent sampling unit,
  margins, missing-output rules and endpoint and joint power before
  execution. Pair and resample whole realizations, not dependent source rows
  or pixels. Planning variance sizes the study; the observed-data interval
  decides. Superiority claims need a prospective multiplicity rule, and
  improvements cannot compensate for failed binding checks.
- Product validity, finite or explicitly unavailable measurements, complete
  processing status, schemas, provenance and deterministic execution remain
  binding. Report absolute targets separately. Retain all morphology, scale,
  SNR, noise and boundary strata.
- Compare like source, component and support semantics. Use original pixels
  for flux and photometry and valid pixels for mask precision, recall and
  IoU. Report splits, merges, duplicates and low-SNR completeness and
  reliability separately.
- Before a long campaign or replay, run a bounded development screen through
  the same runner and evaluator with an explicit time and resource budget.
  Select cases before inspecting results: ordinary controls, independent
  examples of known failure mechanisms, valid empty results, and numerical
  and invalid-pixel boundaries. Exercise the public finder, native product
  reading, evaluation, aggregation and Serial/Dask agreement. A clean screen
  is neither powered parity nor a prediction of campaign success; resolve or
  explicitly defer its warnings before launch.

The dataset matrix retains compact SNR 3–100, blends, diffuse Gaussians,
filaments and shells, mixed emission, different beams, WCS, pixel scales and
units, negative backgrounds, empty, all-NaN and invalid data, varying noise,
image edges and all tile-edge and corner topologies. Every dataset has a
development, regression or qualification role, provenance, checksums and
generator identity, and new populations must be seed-disjoint from existing
manifests. General qualification includes full public or challenge images
from LOFAR, SKA-Mid and SKA-Low (precursor data until SKA-Low data are
public), plus at least one other instrument. Compare Serial before alternate
executors and external finders.

Durable cross-project targets are reported separately from binding relative
and validity gates; the Rapthor profile has its own agreement and safety
requirements.

| Measurement | Target |
| --- | --- |
| Rapthor retained/rejected components | ≥99.5% agreement |
| Reference recovery, SNR ≥10 | ≥99% |
| SNR ≥5 | Report the compatibility curve; no single pass fraction |
| False-discovery rate | ≤1 percentage point above reference |
| Isolated SNR ≥10 position difference, median / p95 | ≤0.02 / 0.10 beam |
| Isolated SNR ≥10 peak-flux difference, median / p95 | ≤2% / 5% |
| Isolated SNR ≥10 integrated-flux difference, median / p95 | ≤5% / 10% |
| `Total_flux` excess against injected truth, median, SNR 10 / 20 / 50 | ≤ +14% / +3.5% / +1% |
| `Total_flux` absolute excess against injected truth, p95, SNR 10 / 20 / 50 | ≤ 35% / 12% / 6% |
| `Total_flux` Hebog minus pinned PyBDSF `master`, paired over realizations, upper one-sided 95% bound, per stratum | ≤ +1 point in median and p95 |
| `Total_flux` 3σ-clipped mean ratio to truth, SNR ≥ 20 | within ±3%, clipped scatter ≤ 5% |
| Source-free RMS-map difference, median / p95 | ≤2% / 5% |

The `Total_flux` rows are the binding limits set on 23 September from PyBDSF
parity on the M1 calibration population and from Rapthor's 10% photometry
decision floor. Strata are that population's SNR 10, 20 and 50 classes,
pooled over white and beam-correlated noise; the excess is
`published / truth - 1` over every matched source. That population's
white-noise images were one noise field rearranged, so on 5 October the rows
were re-measured on independent realizations,
`config/datasets/m1-flux-calibration.json`. Every row passes there against
pinned `master`: the paired upper bounds are −0.1, −0.2 and 0.0 points on the
median and −3.5, +0.1 and −0.1 on the p95 at SNR 10, 20 and 50. The
beam-correlated cell alone reaches +4.0 points on the SNR 10 p95, +1.6 over
twenty realizations a class. On 6 October the maintainer decided that the
rows bind pooled over both noise classes, as set, and that the powered study
(task 29) adds a per-noise-class check.

The retained/rejected row is measured by `just rapthor-agreement`: the
share of sky-model components, one for each distinct pixel holding a
Gaussian centre fitted by `master` or any Hebog lane, that Rapthor's filter
keeps or rejects alike with Hebog's mask and `master`'s, overall and in the
bright, extended, edge, masked, crowded, sparse, true-sky and apparent
strata. On 13 October no lane reached it and released 1.14.1 reached
99.29%; task 29's design decides its binding form.

## Performance and scale gates

For supported Rapthor deployment, matched complete-step median ratios and
their upper one-sided 95% bootstrap confidence bounds must satisfy:

```text
Hebog / pinned PyBDSF master (c70103b) <= 0.50
```

Pinned `master` was faster than released 1.14.1 in every matched Phase 0 run
(3.0% at 256², 6.8% at 3,000²), so on those anchors this gate is at least as
strict as the former ≤0.50× release gate. Task 31 confirms the release ratio
once. Scientific eligibility precedes performance acceptance. These are
minimum deployment gates, not a reason to stop optimizing or to hold an
experimental standalone release.

- Maintain 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000 and 100,000-square
  anchors (with the real images below alongside the nearest anchor), sparse,
  normal and dense-extended workloads, and both sides of every measured
  crossover. Gate early deployment on its frozen envelope; 1.0
  qualification needs the whole matrix up to the 90,000² LOFAR-HD mosaic,
  with 100,000² covered by planner tests only.
- Compute reference-finder timings once per input, revision and host and
  reuse them; rerun them only when one of those changes.
- Match environments and record evidence as
  [`AGENTS.md`](../AGENTS.md#scientific-and-performance-gates) requires: matched
  inputs, revisions, output mode, host, threads, workers, memory and storage;
  one warm-up and at least five measured repetitions with every value
  retained; the full instrumentation list, with scale evidence adding
  reduction depth, stragglers and strong/weak efficiency; and unavailable
  instrumentation recorded with a reason, never zero, in versioned
  `hebog.validation.evidence` records.
- Hebog non-regression needs an upper one-sided 95% bound ≤1.05 against the
  previous reviewed curve; a lower bound >1.05 is a regression and crossing
  the margin is inconclusive. A >10% peak worker or aggregate memory
  regression against either PyBDSF reference needs an approved throughput
  trade-off.
- Component budgets remain diagnostic; complete filtering decides
  deployment. Exact budgets are in the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md).

### Reference images

The real images the repository uses or plans to use, with the windows its
checks cut from them. The public candidates were found on 16 September 2026,
when the headers of the LOFAR-HD mosaics and facet 0, LoTSS-DR3 mosaic 1312
and SDC1 B2 1,000 h were read with range requests; those of MIGHTEE DR1,
GLEAM-X DR1, an SMGPS tile and the LoTSS-Deep DR2 ELAIS-N1 pair followed on
28 September. The [input header contract](../docs/reference/input-header-contract.md)
says how each is read. Check other headers before a large download. No image data or dataset belongs in Git; the
checked-in configuration names each source and window.

| Family | Image | Size | Use | Reference |
| --- | --- | --- | --- | --- |
| LOFAR | LOFAR-HD ELAIS-N1 mosaic, 0.4/0.2/0.1″ pixels | 22,500², 45,000², 90,000² (2.0, 8.1, 32.4 GB); 2-D `float32`, `JY/BEAM`, SIN, beam present, no frame or reference-frequency keywords | Largest real scale anchor; same-field size ladder | Per-facet PyBDSF catalogues; facets are WSClean FK5 J2000 images |
| LOFAR | LoTSS-DR3 HEALPix mosaics (1,571) | 14,390–17,752² (1312: 15,402², ICRS, `RESTFRQ`, beam present, 1.5″ pixels, 9″ beam) | Science and throughput. Quick check and quick benchmark: 1,024² windows of mosaic 1312 at x 9,749, y 9,749 (sparse) and x 7,701, y 6,677 (dense), with the published RMS and mask in the quick check. Quick benchmark and traced peak: 3,000² at x 6,713, y 5,689; 3,600² at x 6,413, y 5,389; 10,000² at x 2,000, y 4,500, the 10,000 tier's anchor; and the whole mosaic, `lotss-dr3-1312-15402`, the 15,402 tier's anchor. | Per-mosaic PyBDSF `srl` and `gaul` catalogues (mosaic 1312: 22,420 sources, 28,559 Gaussians, largest island 131 pixels) plus RMS, residual and mask maps |
| LOFAR | LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky pair | 14,175² each (804 MB); DDFacet, four axes, ICRS, `RESTFRQ`, 6″ beam | Closest public match to Rapthor's two inputs; within the 15,402 envelope | PyBDSF catalogue and maps |
| LOFAR | LoTSS-DR2 cut-outs from the public cut-out service: a 22′ survey field at 12h +45°, 3C 295 (12′), M51 (20′) and a 90′ field at 13h +47° | 1.5″ pixels: about 880², 480², 800² and 3,600² | Notebook comparison whole-image cases (`lotss-dr2-*`); the 22′ field is the public API's example input | LoTSS-DR2 PyBDSF catalogue |
| SKA-Mid | SDC1 B1/B2/B5, 8/100/1,000 h (Zenodo 4328029; INAF mirror) | 32,768² (4.3 GB each); 4-D, `JY/BEAM`, `EPOCH = 2000`, `BMAJ`/`BMIN` but no `BPA`, supplied as 0° | Science checks with truth. B2 1,000 h cut-outs: 1,024² at x 20,992, y 12,800 (sparse) in the quick check, 1,024² at x 16,896, y 16,896 (crowded) in the quick check and benchmark, 2,048² at x 16,384, y 16,384 (crowded) in the benchmark and traced peak; the notebook comparison's 2,048² sparse, ordinary and crowded tiles | Full truth catalogue (`True_1400_v2.txt`), the B2 primary beam and the official submissions |
| SKA-Mid | MeerKAT MIGHTEE DR1 COSMOS and XMM-LSS; SMGPS tiles | MIGHTEE 7,486² and 14,800² (448 MB and 1.75 GB), two axes with declared `FREQ` and `STOKES`, FK5 J2000; SMGPS 7,500² with 16 Obit `SPECLNMF` planes in Galactic coordinates, refused as a cube | Real precursor science; header variety | PyBDSF (MIGHTEE); Aegean (SMGPS, diagnostic only) |
| SKA-Low | MWA GLEAM-X DR1 mosaics | 170–231 MHz: 31,468 × 11,151 (2.8 GB), `ZEA`, FK5 J2000 by `EPOCH`, frequency only in a non-standard `FREQ` keyword; PSF maps 360 × 180 × 4 on a 1° grid | Precursor science with a PSF that varies across the field | PSF maps; Aegean catalogue (diagnostic only) |
| Other | ASKAP EMU-PS1 (CASDA login) | 44,911 × 33,569 | Optional non-SKA-family image | Selavy catalogue |
| Other | ASKAP EMU pilot 2° × 2° field, deep and shallow images (Hydra paper, CIRADA at CADC) | 3,600² each (52 and 104 MB) | Notebook comparison whole-image cases `hydra-deep` and `hydra-shallow` | The Hydra archive's finder catalogues (10 GB), diagnostic only |
| Rapthor | Representative sector image, `rapthor-representative-3000` (restricted, local only) | 3,000² | Phase 0 matched PyBDSF runs, where released 1.14.1 and pinned `master` found 12 and 14 sources; not redistributable | Pinned `master` and 1.14.1 products and timings under `config/baselines/` |

Generated inputs are not reference images: the quick check's thirteen
generated datasets, 128² to 1,024², and the 10,000² `wide-objects-10000`
diagnostic come from `config/datasets/quick-science-check.json` and are
rebuilt from their recipes.

## Architecture and documentation boundaries

Keep the scientific library pipeline-neutral, with inert imports, small typed
requests and results, and no implicit clients, clusters or pools. Maintain
one tile-native science composition for every image size, Serial as the
oracle, Zarr as the sole intermediate plane backend, stage-specific halos,
global ownership and hierarchical reductions. Never raise the public size
limit by sending a complete large plane to one worker. Preserve dtype unless
scientific evidence supports a change. Prefer established libraries,
NumPy/SciPy, then profiled Numba; new native code needs an accepted ADR, the
10% profile, 2× kernel and 5% end-to-end gates, and portable distribution.
The [architecture](../docs/architecture/index.md),
[native-code assessment](../docs/explanation/native-code-assessment.md) and
[`AGENTS.md`](../AGENTS.md) hold the detailed requirements.

Keep the README, docs home, release status, progress page and tutorial
focused on current behaviour, replacing stale summaries when status changes;
the [progress page](../docs/reference/progress-against-goals.md) and the
current-state table above change together. Record completed work in Git
history with exact evidence references, not as another "latest" section in
user guidance. Keep `LOG.md` as a historical archive. Removing a
historical narrative never changes a closed result.
