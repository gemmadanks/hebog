# Hebog implementation plan

Authoritative remaining-work plan. Updated **26 September 2026**.
Current user-facing capability is in
[release status](../docs/reference/release-status.md); execution history,
evidence identities and completed decisions are in [`LOG.md`](../LOG.md).
Closed Phase 5 contracts, reviews and campaign tooling are in Git history at
`4babf0b`.

## Current state

| Item | Current position |
| --- | --- |
| Release | v0.14.1, tagged on 27 September 2026 at `4cc0d14` and uploaded to TestPyPI; it carries the tile-native object pass, the store's lifetime caching and the fit round that returns no array. Experimental and scientifically unqualified. |
| Candidate | Public composition v22: diagonal-weighted component fits, detection through the tiled pass. Development-unqualified. |
| Functionality | Standalone FITS-to-products finder (background/RMS, compact and multiscale detection, deblending, fitting, association; catalogue, mask, RMS and diagnostics) under Serial, Thread and caller-owned Dask executors. No Rapthor backend: `hebog.adapters` holds records and the eight-column catalogue codec only, the seven acceptance scenarios are strict-xfail placeholders, and no flat-noise branch or LSMTool filtering has run on Hebog products. |
| Scalability | Public envelope ≤3,000 pixels per side. Every stage runs through the executor on tiles and publishes to Zarr: background/RMS on 128-pixel cores, everything else on 2,048-pixel cores, so 3,000² is four tiles. The driver holds no image-sized plane and reads no object window. Traced peaks (`just traced-peak`): 224.7 MiB at 512², 430 MiB at 1,024², 1,312 MiB at 2,048², 1,335 MiB at 3,000² and, on the 10,000² LoTSS anchor measured 27 September, 1,541 MiB, each reproduced. The peak is tile-bounded in the main, 15% higher at 10,000² for eleven times the area, with about 1.4 bytes a pixel and 13 KiB a source still growing at it (`LOG.md`, 27 September). One driver term is bounded by the object rather than the tile: an object wider than the read budget brings its own pixels to the driver in the island, deferred-fit and catalogue-row rounds (up to 186 bytes a pixel, about 1.7 GB for a field-filling segment at 3,000² and 19 GB at 10,000², a declared limit no traced case exercises; ADR-008, *Objects wider than the read budget*), and a wide support component's seeds, 12 bytes each, reach the driver the same way. Every other array a round returns is a boundary summary bounded by a core's perimeter; no round returns a patch or a plane (27 September). Details are in the [performance profile](../docs/reference/performance-profile.md) and `LOG.md`, 22–26 September. |
| Performance | No matched `filter_skymodel` benchmark exists; the gate needs the Rapthor adapter. Quick-benchmark anchors on a quiet machine, medians of five against v0.13.0: at 1,024² (25 September) `dense-field` 0.96 [0.94, 0.97], `lotss-dr3-1312-sparse` 0.93 [0.89, 0.95] and `lotss-dr3-1312-dense` 0.94 [0.93, 0.95]; the crossover pair with every endpoint measured in one session (26 September) `sdc1-b2-1000h-crowded-2048` 110.2 s, 0.93 [0.92, 0.93], and `lotss-dr3-1312-dense-3000` 118.3 s, 1.01 [1.00, 1.01]. All pass the previous-release rule. The diagnostic pinned-`master` ratios, Hebog on one thread against `master` on four container cores, are 0.88 [0.88, 0.89] on the crowded 2,048² field and 3.05 [3.01, 3.06] on the 3,000² LoTSS field, where the two use the same CPU time (102.6 s against 101.8 s): on that field the gap to the ≤0.50 gate is parallel occupancy, not the amount of work. Kernels are closed: the profile is flat and none reaches the native-code assessment's 10% gate. The store's per-read overhead is closed too (27 September): the sink caches its metadata for its lifetime and consumers no longer re-read a whole generation, which took a profiled 1,024² run from 14.1 s to 10.9 s and the 1,024² anchors to 0.81, 0.86 and 0.86 against v0.14.0 and 0.91, 0.91 and 0.90 against the pre-M2 branch point `ea67a3a`, all within one session, with identical products on the 16 quick-check cases. What the store still costs is one chunk decode and checksum per window read and one atomic file per written chunk. The fit round's support write, which stopped the fit round returning patches, costs 2 to 4% at 1,024² (inconclusive under the previous-release rule) and is 1% faster on the crowded 2,048² field; the maintainer accepted that cost on 27 September. |
| Science | Strongest evidence: the v15 campaign failed only against the earlier Hebog incumbent (32 regressions, 40 underpowered), with no failure against released PyBDSF, PyBDSF `master` or Aegean; every campaign image was ≤1,024². Since then, focused regression, Serial/Dask, equivalence and installed-wheel evidence only. Source `Total_flux` is the summed fitted component flux and passes every binding limit at or better than pinned `master` in each stratum (23 September); the aperture stays published as `ASSOCIATION_APERTURE_FLUX`. `E_RA` is a great-circle angle, as PyBDSF publishes it (24 September); position-uncertainty calibration passes on beam-correlated noise but is unqualified on a real high-declination field. One slow equivalence regression, edge-source uncertainty availability, fails at 98.8% against 99% and predates M2. |
| Blockers to 1.0.0 | Every task in the [path below](#path-to-100). Largest risks: the performance gap, the wide-object driver term above 3,000², the development machine's memory and disk, and SKA-Low coverage without public SKA-Low images. |
| Next action | Agent: task 8. Human: approve the 10,000 raise when task 8's gate evidence is in; free disk to about 60 GB before the envelope passes 22,500² (task 11). |
| Deferred | Aegean comparisons (paused; reconsidered in the task 29 design), optional comparison finders such as ProFound or 2D SoFiA (see the [notebook guide](../docs/how-to/notebooks.md)), general science improvements outside Rapthor-consumed outputs, and native code without a passing profile gate. Reopen a deferred issue if it becomes a confirmed incorrect supported output. |

## Definition of 1.0.0

Version 1.0.0 is the first release demonstrated to meet the project goal,
with every claim bound to reviewed evidence for that exact candidate:

- **Telescopes.** The standalone finder accepts standard FITS continuum
  images from any radio telescope that meet a documented header contract,
  and is validated first on LOFAR, SKA-Low and SKA-Mid images. It accepts
  their imager conventions (WSClean, CASA and SKA SDP products) or rejects
  them with a specific error.
- **Functionality.** Hebog is a supported, feature-flagged backend for
  Rapthor's `filter_skymodel` at a pinned Rapthor and LSMTool revision:
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
- **Rapthor revisions.** At task 16, pin the latest commits of Rapthor's
  Prefect branch and of LSMTool's default branch, replacing the Phase 0 trace
  (`b1a6467`). Pins move forward only at the checkpoints listed under
  [Risks](#risks). If Rapthor declares a different LSMTool revision, record
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
- **Release check (about 1 hour):** the change check, the largest admitted
  size tier, Serial/Dask agreement and the installed wheel. Runs before each
  `0.x` release. The quick benchmark's large tier belongs here but takes
  hours at current speed, so it runs for profiling and before a release that
  claims a runtime change, and is never waited on for other releases.
- **1.0.0 qualification (once):** one powered science study sized to finish
  overnight on the development machine, and one benchmark on the cluster.
  Neither blocks `0.x` development or releases.

A check that outgrows its budget is sampled, split or moved to a less frequent
level; its budget is not silently extended. PyBDSF outputs and timings are
computed once for each input, reference revision and host, cached outside Git
with checksums, and reused. A defect that escapes the quick checks adds its
case to the fixed case set.

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

Ownership is fixed, as
[`AGENTS.md`](../AGENTS.md#changes-releases-and-handoff) states: the agent
implements, validates, documents and commits locally; the human pushes,
merges, runs notebook refreshes and makes scientific and priority decisions;
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
- At milestone reviews, use the existing log to assess time to actionable
  diagnosis, avoidable campaign interruptions, repairs without useful change
  and user effort needed to recover status or scope. Use these observations
  to improve the workflow, not commit counts, test totals or documentation
  volume as productivity targets. Do not introduce a separate tracking
  framework.

## Path to 1.0.0

The tasks below are numbered in the order they are expected to finish, and
a number is a stable identifier: a completed task is removed and its number
is not reused. Each is a bounded work item that merges, and normally releases as a `0.x`
increment, within the iteration budgets; split a task when a measured result
reveals independent changes. Unless a task says otherwise, the agent
implements and validates on the development machine and the human merges. A
qualification, scale or deployment task authorizes only its stated claim and
still needs the named human decision.

Two rules govern the sequence. **Measure before changing:** nothing is
optimized or re-architected without a profile, and no science-touching change
merges without `just quick-science-check`. **One tier and one release at a
time:** the public envelope rises only through its tier gate, and every raise
is a release.

M2 climbs the local size ladder (tasks 8–13). M3 does not depend on tiling and runs alongside M2; its adapter
(task 19) and the envelope tier that covers the frozen deployment sectors are
what M4 needs. M5 runs on the development
machine at any time, except that its dry run (task 27) needs the 22,500² and
45,000² tiers. M6 starts when everything before it is done and the candidate
is frozen.

### M2 — Climb the local size ladder

Each tier passes the same gate before its limit and release status change:
exact tiled-invariance tests, the quick science check, a quick benchmark on
both sides of any crossover, and a reproduced `just traced-peak` within the
release-check budget. The gate is `tracemalloc`'s peak, which is
deterministic and is measured only by `just traced-peak`; a peak from
anywhere else is not reproducible evidence, and peak RSS, which varies 42%
with machine load, is reported beside it as an envelope, never as the
threshold. Science on the large images uses the LoTSS-DR3 PyBDSF catalogue
and maps and the per-facet LOFAR-HD PyBDSF catalogues, with global
invariants, as in ADR-005.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 8 | Agent, human approves | Raise the public envelope to 10,000. | The tier gate passes on the `lotss-dr3-1312-dense-10000` anchor, whose traced peak of 1,541 MiB is already reproduced (27 September): the exact tiled-invariance tests at this size, the quick science check and the quick benchmark on the anchor remain. The limit, release status and README change together; the raise is a release. |
| 9 | Agent | Remove the wide-object driver term if a tier's traced peak shows it. The 10,000 tier did not: no real LoTSS-DR3 object is wider than the read budget, the generated filament's 554k pixels cost the driver about 100 MB below the multiscale peak, and a smooth object wider than the background box is absorbed by the background estimate (`LOG.md`, 27 September). | The island, deferred-fit and catalogue-row reductions run on the cores as associative partial sums, or the pixels are sub-reduced hierarchically, so no driver term is bounded by the image. Summation-order rounding may replace bit-for-bit equality with the window path where the agent recommends it (accepted 27 September); the local-noise median has no exact associative form and needs its own design. ADR-008's exception under rule 4 is withdrawn. |
| 10 | Agent, human approves | Raise to 15,402² on the whole LoTSS-DR3 mosaic 1312. | The tier gate passes and the raise is a release. |
| 11 | Human frees disk, agent raises | Raise to 22,500² on the LOFAR-HD ELAIS-N1 mosaic. | About 60 GB of disk is free before the run; the tier gate passes and the raise is a release. |
| 12 | Agent, human approves | Raise to 45,000² on the LOFAR-HD mosaic. | The tier gate passes and the raise is a release. This is the out-of-core demonstration: the run completes on 18 GiB with the traced peak bounded by tile size although one `float64` copy of the image (16 GB) would not fit. The local ladder ends here. |
| 13 | Human | Switch uploads from TestPyPI to PyPI. | The envelope covers Rapthor's production sector sizes, which task 16 records. The Trusted Publisher, `pypi` environment, publishing job, installation instructions and release status change together, as in the [publishing guide](../docs/how-to/publish-releases.md). |

### M3 — Telescope coverage and Rapthor functionality

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 14 | Agent | Define the input header contract for LOFAR, SKA-Low and SKA-Mid products and generic FITS images. | Fixture headers cover WSClean (4-D, `EQUINOX` without `RADESYS`), ddf-pipeline and DDFacet mosaics (no `BUNIT`, one copied beam), OSKAR (three axes, no beam, `CROTA`), SKA SDP data models (Stokes before frequency, no `BUNIT`), Obit multi-plane cubes, Galactic frames and ZEA projections. Each is accepted or rejected with a specific error, building on `SuppliedImageMetadata`. Headers of further reference images (MIGHTEE, GLEAM-X and others) are checked before their downloads. |
| 15 | Agent, human dispositions | Decide how to handle a point-spread function that varies across the field. | LOFAR facets and MWA mosaics (which ship PSF maps) have a PSF the header beam cannot describe. Measure the effect on fluxes and sizes with injected truth, then accept a PSF map input or document the limitation with its measured effect. |
| 16 | Agent | Pin the latest Rapthor Prefect-branch and LSMTool commits, refresh the Rapthor contract and audit the profile. | The [contract page](../docs/reference/rapthor-source-finding-contract.md) traces the pinned revisions and records Rapthor's production sector image sizes. Each PyBDSF behaviour LSMTool uses (zero mean map, adaptive RMS boxes 150/50 and 35/7 at threshold 75, hard thresholds at the traced 5/3, 5/4 and 7.5/5 profiles, three wavelet scales, island-stop flat-noise pass, `srl` catalogue, island mask, both RMS maps, source count and the blanked-image path) maps to an existing Hebog behaviour or a listed gap. |
| 17 | Agent, human dispositions | Decide how a task's declared memory reaches the Dask scheduler. | Admission proves one task fits one worker and the in-flight window bounds concurrency, but Hebog pins no task to a worker, so a scheduler may co-locate admitted tasks past one worker's memory. With the Rapthor cluster pinned, either its workers declare a resource Hebog can annotate, or the limitation is documented with its measured spill and worker-loss behaviour on the deployment envelope. |
| 18 | Agent | Implement the Rapthor profile and the flat-noise RMS branch. | Profile outputs are tested on analytic and generated truth; the flat-noise branch shares products and reads rather than running a second full analysis. |
| 19 | Agent | Implement the Rapthor adapter and exercise LSMTool on Hebog products. | Pinned LSMTool clips, groups and transfers names on Hebog catalogue, mask and RMS products for true-sky and apparent-sky inputs, with the LoTSS-Deep DR2 ELAIS-N1 pair as the representative input. The seven acceptance scenarios become passing tests (empty and invalid input, retry reuse, worker loss, fallback and dual run). The adapter imports no Rapthor, Prefect or LSMTool in library code. |
| 20 | Agent prepares, human pushes | Add Rapthor backend selection, fallback and dual-run reporting in Rapthor. | A Rapthor patch against the current pin selects the backend by flag, respects the caller's resource budget and reports dual-run differences. |
| 21 | Agent, human dispositions | Measure Rapthor-profile agreement within the release-check budget, using cached reference outputs. | Retained/rejected agreement against pinned `master` on true/apparent, bright, extended, edge, masked, sparse and crowded populations. Choose `compact` only with ≥99.5% overall agreement and every safety stratum passing; otherwise `continuum`. |

### M4 — Deployment performance gate

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 22 | Agent proposes, human freezes | Freeze the initial deployment envelope. | Sizes and workloads match Rapthor's production sectors (task 16) and fit the development machine, and the envelope tier that covers them is admitted. |
| 23 | Agent | Run matched complete `filter_skymodel` benchmarks and optimize until the runtime gate passes. | Hebog and pinned `master` run in the same Linux container on the development machine, with cached reference timings. The ratio and its upper one-sided 95% bound pass on every envelope cell; memory and Hebog-curve non-regression and the quick science check pass. Native code enters only through the native-code gates and an accepted ADR. |

### M5 — Prepare scale beyond one machine

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 24 | Agent | Bound the graph for 100,000² at 10 and at 200 nodes without running the science. | Planner tests show at most 50,000 tasks, bounded reduction depth, bounded driver memory and a valid memory admission for both topologies. |
| 25 | Agent | Qualify the Zarr store and the restart and recovery path locally. | Atomicity, owned-chunk writes from concurrent local workers, codec and chunk geometry, missing chunks and injected failures pass within an admitted memory budget. Shared-storage throughput is left to the cluster benchmark. |
| 26 | Agent proposes, human approves | Amend the scalability contract. | `config/benchmarks/phase-0-scalability.json`, the performance and scalability contracts page and the `test-scalability` recipe describe the development-machine tier and the final 1, 2, 5 and 10-node benchmark. The 50, 100 and 200-node gates are kept as design targets, not deleted. |
| 27 | Agent | Package the cluster benchmark. | One command and a short guide run the 90,000² LOFAR-HD mosaic at 1, 2, 5 and 10 nodes, plus the 22,500² and 45,000² versions for size scaling, and record evidence, the hardware and a scaling-model fit. A dry run with a local Dask cluster at small sizes passes, so the cluster session measures rather than debugs. |

### M6 — Qualification and 1.0.0

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 28 | Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed; a later change restarts only the affected qualification tasks. The Rapthor and LSMTool pins move forward here for the last time. |
| 29 | Agent designs, human approves | Run one powered parity/retention study with fresh held-out and public-survey data, sized to finish overnight on the development machine. | Every binding endpoint passes under a prospectively reviewed contract, population and power design, including the limitations that block 1.0.0 and the LOFAR, SKA-Mid and SKA-Low families in the 1.0.0 definition. Closed failed campaigns are never reused as confirmation. |
| 30 | Human runs, agent analyses | Run the cluster benchmark once. | Strong scaling at 1, 2, 5 and 10 nodes and size scaling across the 22,500², 45,000² and 90,000² mosaics meet the amended gates, with invariant results and the task 23 runtime gate confirmed on cluster hardware. A failure becomes a normal `0.x` repair task. |
| 31 | Agent | Check released PyBDSF 1.14.1 once. | One matched run against 1.14.1, cached for reuse, confirms Hebog ≤0.50× the release on the deployment envelope and Rapthor-profile agreement against it. A failure is reported with its cause before the 1.0.0 decision. |
| 32 | Human runs in Rapthor, agent supports | Run the operational trial behind the Rapthor flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| 33 | Agent assembles, independent reviewers accept | Assemble the readiness packet and obtain acceptance. | The packet binds science, Rapthor profile, performance, scale, portability, security, licensing, packaging and current documentation to the frozen candidate, with separate radio-astronomy and engineering acceptance. |
| 34 | Human | Release 1.0.0. | Release Please produces 1.0.0 (for example through a `Release-As: 1.0.0` commit footer) and the package publishes to PyPI. Release notes state that 100,000² images and 100 to 200+ nodes are designed for but not demonstrated. |

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The 8–20× gap on real images does not close with NumPy/SciPy and Numba. | Task 23 fails. | Profile first; attack algorithmic cost before constant factors; use the native-code gates only for a profiled kernel. Report the gap honestly at each milestone. |
| An object wider than the read budget brings its own pixels to the driver in the island, deferred-fit and catalogue-row rounds. | Driver memory scales with that object, not the tile: about 1.7 GB at 3,000², 19 GB at 10,000² and 1.9 TB at 100,000² for a field-filling segment. | Task 7's anchor contains an image-spanning filament; task 9 moves the reductions onto the cores if the term shows. |
| Extended association cannot be made exactly tile-invariant. | A tier stalls or changes science. | Test analytic shells and filaments crossing corners at each tier; escalate a scientific trade-off to the human rather than weakening invariance silently. |
| Scheduler, reduction or storage bottlenecks appear only above 10 nodes. | A later deployment at 100+ nodes fails or scales poorly. | Planner bounds for 200 nodes, a scaling model fitted to the cluster benchmark, and an explicit "not demonstrated" statement in release notes. |
| Large public images have minimal or non-standard headers; the HD mosaic is published "for browsing only". | Anchors cannot run unmodified, or their science comparison is weak. | Headers checked 16 September; explicit request metadata; per-facet HD images and catalogues for science; LoTSS-DR3 mosaics as the fallback scale anchors. |
| No large public SKA-Low image exists. | SKA-Low coverage relies on MWA precursor data. | GLEAM-X DR1 with its PSF maps (its Aegean catalogue is diagnostic only), and SKA-Low science-verification data once released (expected from 2027). |
| Rapthor and LSMTool change frequently. | Adapter, contract and benchmark churn, or a backend that only works on a stale revision. | Pin the latest commits at task 16 and move both pins forward only before the Rapthor patch (task 20), before the matched benchmarks (task 23) and at the freeze (task 28), rerunning the contract audit, the acceptance scenarios and the profile-agreement check each time and recording the revisions in `LOG.md`. |
| About 1.4 bytes a pixel and 13 KiB a source still grow at the traced peak above one tile (three-point fit, 27 September). | Small at every local tier (about 2.7 GiB from pixels at 45,000²), but at 100,000² and survey source counts, driver-held records could reach tens of GB. | Task 24's planner bounds include both terms; an empty 10,000² case separates them exactly; if they bind, shard or stream the records they belong to rather than holding them on the driver. |
| The development machine's 18 GiB RAM and free disk limit local tiers. | Tiers above 22,500² stall, or runs spill to disk and slow iteration. | Tile-bounded memory; about 60 GB of free disk before tiers above 22,500²; 90,000² only on the cluster. |
| Short checks miss a rare regression, or scientific campaigns absorb the schedule again. | A defect reaches a `0.x` release, or performance and scale slip. | Releases stay experimental and each escaped defect adds a fixed case; iteration budgets, cached references and endpoints limited to Rapthor-consumed fields hold the schedule; the one powered study at task 29 is the backstop. |

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
`published / truth - 1` over every matched source.

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
  [`AGENTS.md`](../AGENTS.md#performance-validation) requires: matched
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
and SDC1 B2 1,000 h were read with range requests; dimensions marked
"inferred" come from file sizes or catalogue metadata. Check other headers
before a large download. No image data or dataset belongs in Git; the
checked-in configuration names each source and window.

| Family | Image | Size | Use | Reference |
| --- | --- | --- | --- | --- |
| LOFAR | LOFAR-HD ELAIS-N1 mosaic, 0.4/0.2/0.1″ pixels | 22,500², 45,000², 90,000² (2.0, 8.1, 32.4 GB); 2-D `float32`, `JY/BEAM`, SIN, beam present, no frame or reference-frequency keywords | Largest real scale anchor; same-field size ladder | Per-facet PyBDSF catalogues; facets are WSClean FK5 J2000 images |
| LOFAR | LoTSS-DR3 HEALPix mosaics (1,571) | 14,390–17,752² (1312: 15,402², ICRS, `RESTFRQ`, beam present, 1.5″ pixels, 9″ beam) | Science and throughput. Quick check and quick benchmark: 1,024² windows of mosaic 1312 at x 9,749, y 9,749 (sparse) and x 7,701, y 6,677 (dense), with the published RMS and mask in the quick check. Quick benchmark and traced peak: 3,000² at x 6,713, y 5,689; 3,600² at x 6,413, y 5,389; 10,000² at x 2,000, y 4,500, the 10,000 tier's anchor. The 15,402 tier is the whole mosaic. | Per-mosaic PyBDSF `srl` and `gaul` catalogues (mosaic 1312: 22,420 sources, 28,559 Gaussians, largest island 131 pixels) plus RMS, residual and mask maps |
| LOFAR | LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky pair | about 14,000² (inferred) | Closest public match to Rapthor's two inputs | PyBDSF catalogue and maps |
| LOFAR | LoTSS-DR2 cut-outs from the public cut-out service: a 22′ survey field at 12h +45°, 3C 295 (12′), M51 (20′) and a 90′ field at 13h +47° | 1.5″ pixels: about 880², 480², 800² and 3,600² | Notebook comparison whole-image cases (`lotss-dr2-*`); the 22′ field is the public API's example input | LoTSS-DR2 PyBDSF catalogue |
| SKA-Mid | SDC1 B1/B2/B5, 8/100/1,000 h (Zenodo 4328029; INAF mirror) | 32,768² (4.3 GB each); 4-D, `JY/BEAM`, `EPOCH = 2000`, `BMAJ`/`BMIN` but no `BPA`, supplied as 0° | Science checks with truth. B2 1,000 h cut-outs: 1,024² at x 20,992, y 12,800 (sparse) in the quick check, 1,024² at x 16,896, y 16,896 (crowded) in the quick check and benchmark, 2,048² at x 16,384, y 16,384 (crowded) in the benchmark and traced peak; the notebook comparison's 2,048² sparse, ordinary and crowded tiles | Full truth catalogue (`True_1400_v2.txt`), the B2 primary beam and the official submissions |
| SKA-Mid | MeerKAT MIGHTEE DR1 XMM-LSS; SMGPS tiles (Galactic, multi-plane) | about 20,900² (inferred); 7,500² | Real precursor science; header variety | PyBDSF (MIGHTEE); Aegean (SMGPS, diagnostic only) |
| SKA-Low | MWA GLEAM-X DR1 mosaics | not checked (2.8 GB) | Precursor science with a PSF that varies across the field | PSF maps; Aegean catalogue (diagnostic only) |
| Other | ASKAP EMU-PS1 (CASDA login) | 44,911 × 33,569 | Optional non-SKA-family image | Selavy catalogue |
| Other | ASKAP EMU pilot 2° × 2° field, deep and shallow images (Hydra paper, CIRADA at CADC) | 3,600² each (52 and 104 MB) | Notebook comparison whole-image cases `hydra-deep` and `hydra-shallow` | The Hydra archive's finder catalogues (10 GB), diagnostic only |
| Rapthor | Representative sector image, `rapthor-representative-3000` (restricted, local only) | 3,000² | Phase 0 matched PyBDSF runs, where released 1.14.1 and pinned `master` found 12 and 14 sources; not redistributable | Pinned `master` and 1.14.1 products and timings under `config/baselines/` |

Generated inputs are not reference images: the quick check's twelve
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

Keep the README, docs home, release status and tutorial focused on current
behaviour, replacing stale summaries when status changes. Record chronology in
`LOG.md` or Git history, not as another "latest" section in user guidance.
Removing a historical narrative never changes a closed result.
