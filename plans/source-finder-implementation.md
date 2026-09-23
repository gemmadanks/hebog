# Hebog implementation plan

Authoritative remaining-work plan. Updated **23 September 2026**.
Current user-facing capability is in
[release status](../docs/reference/release-status.md); execution history,
evidence identities and completed decisions are in [`LOG.md`](../LOG.md).
Closed Phase 5 contracts, reviews and campaign tooling are in Git history at
`4babf0b`.

## Current state

| Item | Current position |
| --- | --- |
| Release | v0.12.0, tagged on 18 September 2026; releases upload to TestPyPI. Experimental and scientifically unqualified. |
| Candidate | Public composition v22, which fits components with diagonal weighting and evaluates detection through the tiled pass. Development-unqualified. |
| Functionality | Standalone FITS-to-products finder: background/RMS, compact and multiscale detection, deblending, fitting, source association, catalogue/mask/RMS/diagnostics, Serial and caller-owned Dask execution. No Rapthor backend: `hebog.adapters` holds records and the 8-column catalogue codec only, and the seven acceptance scenarios are strict-xfail placeholders. No flat-noise branch or LSMTool filtering has run on Hebog products. |
| Scalability | Public envelope ≤3,000 pixels per side, raised from 1,024 on 22 September. ADR-008 passes A, B and C and pass D's component topology, fit-parent reconciliation, component fits and cross-parent grouping run through the executor and publish to Zarr: background/RMS on hard-coded 128-pixel cores, the rest on the contract's smallest admitted 2,048-pixel core, so 2,048² is the last single-tile size and a 3,000² image is four tiles at those cores and 576 at the background cores. No composition step labels or searches a whole plane, and every scientific step runs through the executor and reads published windows. The driver still reads whole planes from the store to hand the composition its image, background and RMS, which is what the next tier waits on: peak RSS above one tile is about 1.3 GB plus 62 MiB per megapixel, and a real 3,000² LoTSS field has a deterministic traced peak of 1,539 MiB, with peak RSS ranging 1,559–2,477 MiB across ten runs of identical code, so tier gates use the traced peak and quote RSS only as an envelope. Two background sub-steps are capped at 10⁶ pixels. |
| Performance | No matched benchmark exists. Converging detection onto the tiled pass cost 6–7% on the two LoTSS quick-benchmark cases against v0.12.0 (ratios 1.07 [1.04, 1.09] and 1.06 [1.05, 1.10], both inconclusive under the 1.05 rule; dense-field 0.99 pass), because the stage evaluates each tile twice and the public path gained one Zarr generation; removing two publication refinements that nothing read then returned most of it, and pass C then cost 7% for its global reductions and 6% for its support rounds, and pass D's component topology and fits a further 1.5% and 11%, the cross-parent grouping a further 3% and the tiled source association 13%, less 10 s returned by describing the scale features from records rather than relabelling their planes, the catalogue's source planes 5% and its rows 9%, leaving the sixteen quick-check cases at 235 s against 135.6 s before the convergence, about 73% (20 September). M2's bottleneck row then took the first two targets the complete-path profile at `9866a1b` (`m2-bottleneck-baseline`) ranks: describing labels in one pass instead of one plane scan per label, which was 23% of the dense 2,048² case, and stopping the product store probing for Zarr v2 metadata and rewriting its group attributes per key, which removed 1,810 of 6,138 store reads and 198 of 513 writes on dense 1,024². Together they take `sdc1-b2-1000h-crowded-2048` 323.5 → 237.8 s (1.87 → 1.37 against v0.12.0) and `sdc1-b2-1000h-crowded` 60.8 → 53.8 s (1.63 → 1.44). The per-change split on the three 1,024² anchors is unmeasured: those runs violated the contract's quiet-machine rule and need repeating. The fit-context dilation is retired as a target: it was named when the composition dilated whole planes, and the tile-native `_fit_context_core` costs 0.1–0.3% of every profiled case, so the 2.2× separable replacement would return about 0.03%. Per-pixel background refinement, then the largest single cost, was taken next: each local-noise batch re-filtered its own protection halo, which is about 200 pixels a side against a cell stride near 5, so the wavelet bank ran over 22 times the image on dense 1,024². Batching 2,304 cells instead of 256 cuts that to 3.4 times with every published plane bitwise identical, and takes dense-field 21.8 → 18.3 s, LoTSS sparse 23.1 → 19.8 s and LoTSS dense 25.4 → 21.7 s, so their ratios to v0.12.0 fall from 1.21, 1.18 and 1.23 to 1.02, 1.01 and 1.05 and the default tier is back at release parity. SDC1 crowded 1,024² and 2,048² moved only 2.5% and 2.9% there, because a source-dense run is dominated instead by the object rounds' windowed Zarr reads: 31.6% of the crowded 2,048² run over 4,664 reads, since a chunk holds a whole tile core and sixteen objects a batch decoded 4.06 GiB for a 4 MB image. Batching 256 objects cuts that to 0.74 GiB with every plane bitwise identical and peak RSS unchanged, and takes SDC1 crowded 2,048² 230.9 → 153.1 s and 1,024² 52.4 → 38.5 s. Every quick-benchmark anchor now passes the previous-release rule at 0.95, 0.92, 0.94, 1.03 and 0.88, three of them faster than v0.12.0, so the convergence regression is closed; across 21 September dense-field moves 23.5 → 17.1 s and SDC1 2,048² 323.5 → 153.1 s, and the sixteen quick-check cases 235 → 155 s. Deblending is not a cost on these images at 1.3%. Batching the fitting and fitted-row coordinate transforms then removed a third of the 11,046 single-position Astropy calls a crowded 2,048² run made, which were 14.3% of its self time. The bottleneck row pauses there: the profile is flat, no Hebog kernel reaches the native-code assessment's 10% gate, and the row builder's own transforms were then split the same way, taking SDC1 crowded 1,024² 38.5 → 33.0 s and 2,048² 153.1 → 138.7 s with the 1,024² anchors neutral inside their dispersion, and the row's own coordinate was split the same way, so no per-source Astropy call remains: every conversion now serves a whole batch and costs what one source used to. The crossover the 3,000-pixel envelope opens is measured on both sides: `sdc1-b2-1000h-crowded-2048` at 119.1 s (118.6–119.8), ratio 0.68 [0.68, 0.68] against v0.12.0 at 175.2 s, a pass, and the new `lotss-dr3-1312-dense-3000` at 115.8 s (115.4–116.7), which has no previous-release ratio because v0.12.0 refuses that size and no earlier Hebog measurement of the case exists. Both were taken with a browser and an endpoint scanner active and need a quiet re-measurement before they are quoted as anchors. [Where Hebog spends its time](../docs/reference/performance-profile.md) records the current profile and the ranked remainder. The complete-path profile (17 September, run `m1-profile-6-complete`) fits generated cost as `11.6 s/Mpx + 25 ms/component + 4.3 ms/(Mpx·component)`, against `18.6 + 49 ms + 47 ms` at the start of M1. Complete runs improved 1.6× to 5.5×: SDC1 crowded 2,048² 956 → 174 s, SDC1 crowded 1,024² 119 → 38 s, LoTSS 1,024² 31–35 → 20–21 s. Against v0.9.0 the quick benchmark gives 0.81–0.88 on the default tier and 0.54 on SDC1 1,024². Per-pixel background and RMS estimation now dominates: 41.6 s of a 51.3 s noise-only 2,048² run. Diagnostic one-thread `master` ratios on 1,024² inputs are about 3–4×, from 6.2–9.1× before M1; the gate is ≤0.50× pinned PyBDSF `master` (`c70103b`) on matched complete `filter_skymodel` runs, which needs M3 and M4. |
| Science | The v15 campaign failed only through 32 regressions against the earlier Hebog incumbent; no comparison against released PyBDSF, PyBDSF `master` or Aegean failed, and 40 were underpowered. All campaign images were ≤1,024 pixels. v16–v20 have focused regression, Serial/Dask, equivalence and installed-wheel evidence only. Uncertainty calibration, measurement tails and faint association were accepted on 13 September as limitations of an experimental standalone release, not as passes. On 23 September the binding `Total_flux` limits were set at PyBDSF parity and the source flux was redefined as the summed fitted component flux; the fitted flux passes the limits today and the continuum profile's aperture source flux fails them on correlated noise (`LOG.md`, 23 September). |
| 1.0.0 blockers | Every milestone below. The largest risks are the performance gap, tile-native continuum association, the memory and disk of the local development machine, and SKA-Low coverage without public SKA-Low images. |
| Next action | Human: disposition the 3,000-pixel envelope for release, and free disk to about 60 GB before the envelope passes 22,500². Agent: publish the summed fitted component flux as the continuum source `Total_flux` and re-run the M1 calibration against the limits in the scientific gates table; re-measure the three 1,024² quick-benchmark anchors on a quiet machine to attribute the two landed bottleneck changes; then remove the driver's five whole-plane reads, which is what the 10,000-pixel tier waits on. |
| Deferred | Aegean comparisons (paused while development focuses on PyBDSF; reconsidered at M6), optional comparison finders such as ProFound or 2D SoFiA (see the [notebook guide](../docs/how-to/notebooks.md)), general science improvements outside Rapthor-consumed outputs, and native code without a passing profile gate. Reopen a deferred issue if it becomes a confirmed incorrect supported output. |

## Definition of 1.0.0

Version 1.0.0 is the
first release demonstrated to meet the project goal, with every claim bound to
reviewed evidence for that exact candidate:

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
  agreement with every safety stratum passing, and the frozen candidate passes
  prospective, powered, held-out parity/retention against pinned PyBDSF
  `master` (`c70103b`), and a single check against released PyBDSF 1.14.1
  confirms Rapthor-profile agreement for users of the release. The evidence includes full images, not only
  cut-outs, from LOFAR, SKA-Mid (SDC1 simulations and MeerKAT) and SKA-Low
  (MWA precursor data until SKA-Low data are public).
- **Performance.** On the development machine, matched complete
  `filter_skymodel` medians meet the runtime gate across the deployment
  envelope without a memory or Hebog-curve regression. The final cluster
  benchmark confirms them on the cluster's hardware.
- **Scalability.** Scale evidence uses LOFAR images only. On the development
  machine (18 GiB RAM), the 45,000² LOFAR-HD mosaic completes with peak
  memory bounded by tile size, although one `float64` copy of the image alone
  would not fit in memory. Results do not change with worker count, tile
  geometry, completion order or retry. A final cluster benchmark, run once for
  1.0.0, processes the 90,000² LOFAR-HD mosaic on 1, 2, 5 and 10 nodes within
  the amended runtime, task-count, scheduler-overhead, memory and spill gates.
  Planner tests bound graph size and reduction depth for 100,000² images on
  100 to 200+ nodes. Release notes say that 100,000² images and that node
  count are designed for but not demonstrated.
- **Release.** Published on PyPI with portability, security, licensing,
  current documentation and independent radio-astronomy and engineering
  acceptance.

Rapthor's default cutover is a separate Rapthor decision taken after an
operational soak of the 1.0.0 backend; the PyBDSF fallback remains until then.

## Scope and resource rules

- **1.0.0 and cutover.** 1.0.0 means the definition above. Making Hebog
  Rapthor's default backend is a separate Rapthor decision after an
  operational trial.
- **Compute.** Development, checks and benchmarks run on the maintainer's
  machine (Apple M3 Pro, 12 logical CPUs, 18 GiB RAM). A cluster of up to 10
  nodes runs one final benchmark for 1.0.0 and never blocks development.
  Record its hardware when that benchmark is scheduled.
- **Disk.** The maintainer frees disk to about 60 GB before the local
  envelope passes 22,500². The estimate for 45,000² is 8.1 GB of input, up to
  16 GB of RMS and mask output and up to about 24 GB of uncompressed Zarr
  intermediates. The local ladder stops at 45,000²; 90,000² runs only on the
  cluster.
- **Data.** Scale testing uses public LOFAR images; no generated 100,000²
  image or simulated SKA-Low image is built for now. The public LoTSS-Deep
  DR2 ELAIS-N1 apparent and primary-beam-corrected pair is the
  representative two-branch Rapthor input. SDC1 cut-outs serve science
  checks for SKA-Mid. See [reference images](#reference-images).
- **Rapthor revisions.** When M3 starts, pin the latest commits of Rapthor's
  Prefect branch and of LSMTool's default branch, replacing the Phase 0 trace
  (`b1a6467`). Pins move forward only at the checkpoints listed under Risks.
  If Rapthor declares a different LSMTool revision, record both and test the
  latest LSMTool.
- **Limitations that block 1.0.0.** Of the limitations accepted for v0.7.0,
  those that change Rapthor-consumed fields must pass before 1.0.0:
  - `E_RA`/`E_DEC` uncertainty calibration (Rapthor excludes sources at
    ≥2 arcsec);
  - `Total_flux` tails, under the limits in the
    [scientific gates](#scientific-gates) table (`Isl_Total_flux` is only
    carried through Rapthor's astrometry check);
  - faint association where it changes island grouping, and therefore
    patches.

  The others stay documented limitations.
- **Iteration budgets.** The budgets under
  [Delivery policy](#delivery-policy) are the normal feedback loop and replace
  long campaigns.

## Delivery policy

Ship frequent, useful experimental `0.x` increments rather than phase-sized
batches: normally one release for each merged roadmap row that changes
behaviour. Phase numbers survive only as historical identifiers.

Development runs on the maintainer's machine and favours fast iterations over
long campaigns and benchmarks. Every check has a budget on that machine:

- **Change check (about 15 minutes):** relevant tests, the quick science check
  and, for performance-relevant changes, the quick benchmark's default tier.
  Runs for every change that can affect science or runtime.
- **Release check (about 1 hour):** the change check, the largest admitted
  size tier, Serial/Dask agreement and the installed wheel. Runs before each
  `0.x` release. The quick benchmark's large tier (up to 3,600²) belongs here,
  but at current speed it takes hours. Until it fits, it runs for profiling
  and before a release that claims a runtime change, and it is never waited
  on for other releases.
- **1.0.0 qualification (once):** one powered science study sized to finish
  overnight on the development machine, and one benchmark on the cluster.
  Neither blocks `0.x` development or releases.

A check that outgrows its budget is sampled, split or moved to a less frequent
level; its budget is not silently extended. PyBDSF outputs and
timings are computed once for each input, reference revision and host, cached
outside Git with checksums, and reused. A defect that escapes the quick checks
adds its case to the fixed case set.

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

Ownership follows [`AGENTS.md`](../AGENTS.md#changes-releases-and-handoff):

- **Agent:** investigates, implements, validates, updates documentation,
  `LOG.md` and this plan, creates local commits and prepares review material.
- **Human:** pushes, opens and merges pull requests, runs and inspects notebook
  comparison refreshes, makes scientific dispositions and priorities, and
  configures release infrastructure.
- **Release Please:** updates versions, the changelog and release notes, and
  creates tags and GitHub releases. Nobody edits those files by hand.

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

## Roadmap to 1.0.0

Work proceeds in milestones ordered by dependency. Each row is a bounded work
item that merges, and normally releases as a `0.x` increment, within the
iteration budgets; split a row when a measured result reveals independent
changes. Unless a row says otherwise, the agent implements and validates on
the development machine and the human merges. Qualification, scale and
deployment rows authorize only their stated claim and still need the named
human decisions.

Two rules govern the sequence:

- **Measure before changing.** Nothing is optimized or re-architected without
  a profile, and no science-touching change merges without the quick science
  check from M1.
- **Optimize the code that survives.** M2 replaces the whole-array public
  science with the tiled composition. Before M2 lands, fix only bottlenecks in
  kernels the tiled path will keep (fitting, measurement, filters, labelling),
  not whole-array orchestration it will delete.

### M1 — Fast feedback and the performance gap

| Owner | Task | Done when |
| --- | --- | --- |
| Agent | Publish the summed fitted component flux as the continuum source `Total_flux`, keeping the signed aperture as `ASSOCIATION_APERTURE_FLUX` and the island sum as `Isl_Total_flux` (decision of 23 September, `LOG.md`). | The continuum profile's source `INTEGRATED_FLUX` is the sum of its fitted components' integrated fluxes, carrying the fitted uncertainty where the components publish one; a source without a fitted component keeps its aperture flux and its flag. The product reference and the Rapthor codec describe that contract, and the measured low-SNR curve is documented there rather than corrected. The M1 calibration, re-run on the `m1-endpoint-diagonal` population, passes the `Total_flux` limits in the [scientific gates](#scientific-gates) table for sources as well as components; the quick science check and Serial/Dask invariance pass. The PyBDSF calibration comparison runs from a checked-in script under `scripts/validation/`, so the limits can be re-asserted on the same population. |

### M2 — One tile-native science path

This is the architectural core of 1.0.0 and the prerequisite for every size
tier above 1,024. Its local size ladder doubles as the out-of-core
demonstration: from 22,500² upward, image-sized state cannot fit in the
development machine's memory.

| Owner | Task | Done when |
| --- | --- | --- |
| Agent | Converge the remaining object rounds of `public_science.py` onto `stages/`, so one composition serves every size. | The catalogue rows run as the rounds the [ADR-008 object table](../docs/architecture/adr/008-make-the-continuum-composition-tile-native.md#the-object-passs-rounds) sets out. One-tile and many-tile runs on analytic edge, corner and partition-origin cases agree exactly; the quick science check and Serial/Dask invariance pass; no whole-plane science array remains in `public_science.py`. |
| Agent | Remove whole-plane state from the driver and background. Peak RSS above one tile is about 1.3 GB plus 62 MiB per megapixel, so Hebog is already substantially tile-bounded and what remains is some six to eight live whole planes; do not size this work from inside the envelope, where the tile grows with the image and the slope is five times too steep. | The 10⁶-pixel coarse-protection and local-noise caps are tile-bounded; RMS and mask products stream from Zarr row blocks; the catalogue is a partitioned reduction; input hashing is chunked; merges of boundary states run on workers. Tile cores are configurable within the contract's 2,048–8,192 range, and admission rejects a plan above the admitted memory before submission. Peak RSS scales with tile size, not image size. |
| Agent | Remove profiled bottlenecks in the tiled kernels. | Each change has quick-benchmark before/after evidence on affected and adjacent anchors and passes the quick science check. |
| Agent, human approves each raise | Raise the public envelope one tier at a time on the development machine. 3,000 landed on 22 September; the remaining tiers are 10,000, then the LOFAR ladder of LoTSS-DR3 (15,402²), LOFAR-HD 22,500² and LOFAR-HD 45,000². | Each tier passes exact tiled-invariance tests, the quick science check, a quick benchmark on both sides of any crossover and a measured traced-allocation peak within the release-check budget, before the limit and release status change. The gate is `tracemalloc`'s peak, which is deterministic; peak RSS varies 42% with machine load on the development machine and is reported beside it as an envelope, never as the threshold. Each raise is a release. Science on the large images uses the LoTSS-DR3 PyBDSF catalogue and maps and per-facet HD PyBDSF catalogues, with global invariants, as in ADR-005. |
| Human | Switch uploads from TestPyPI to PyPI once the envelope covers Rapthor sector images. | The Trusted Publisher, `pypi` environment, publishing job, installation instructions and release status change together, as in the [publishing guide](../docs/how-to/publish-releases.md). |

### M3 — Telescope coverage and Rapthor functionality

The header audit and the Rapthor profile audit do not depend on tiling and
may run alongside M2.

| Owner | Task | Done when |
| --- | --- | --- |
| Agent | Define the input header contract for LOFAR, SKA-Low and SKA-Mid products and generic FITS images. | Fixture headers cover WSClean (4-D, `EQUINOX` without `RADESYS`), ddf-pipeline and DDFacet mosaics (no `BUNIT`, one copied beam), OSKAR (three axes, no beam, `CROTA`), SKA SDP data models (Stokes before frequency, no `BUNIT`), Obit multi-plane cubes, Galactic frames and ZEA projections. Each is accepted or rejected with a specific error. Builds on the request's `SuppliedImageMetadata`, which already fills a missing reference frequency or beam keyword. Headers of further reference images (MIGHTEE, GLEAM-X and others) are checked before their downloads. |
| Agent, human dispositions | Decide how to handle a point-spread function that varies across the field. | LOFAR facets and MWA mosaics (which ship PSF maps) have a PSF that the header beam cannot describe. Measure the effect on fluxes and sizes with injected truth, then either accept a PSF map input or document the limitation with its measured effect. |
| Agent, human dispositions | Decide how a task's declared memory reaches the Dask scheduler. | Admission proves one task fits one worker and the in-flight window bounds concurrency across the admitted budget, but Hebog pins no task to a worker, so a scheduler may co-locate admitted tasks and exceed one worker's memory. With the Rapthor cluster pinned, either its workers declare a resource Hebog can annotate, or the limitation is documented with the measured spill and worker-loss behaviour it causes on the deployment envelope. |
| Agent | Pin the latest Rapthor Prefect-branch and LSMTool commits, refresh the Rapthor contract and audit the profile. | `docs/reference/rapthor-source-finding-contract.md` traces the pinned Rapthor and LSMTool revisions. Each PyBDSF behaviour LSMTool uses (zero mean map, adaptive RMS boxes 150/50 and 35/7 at threshold 75, hard 4/5 thresholds, three wavelet scales, island-stop flat-noise pass, `srl` catalogue, island mask, both RMS maps, source count and the blanked-image path) is mapped to an existing Hebog behaviour or a listed gap. |
| Agent | Implement the Rapthor profile and the flat-noise RMS branch. | Profile outputs are tested on analytic and generated truth; the flat-noise branch shares products and reads rather than running a second full analysis. |
| Agent | Implement the Rapthor adapter and exercise LSMTool on Hebog products. | Pinned LSMTool clips, groups and transfers names on Hebog catalogue, mask and RMS products for true-sky and apparent-sky inputs; the seven acceptance scenarios become passing tests (empty and invalid input, retry reuse, worker loss, fallback and dual run). The adapter imports no Rapthor, Prefect or LSMTool in library code. |
| Agent prepares, human pushes | Add Rapthor backend selection, fallback and dual-run reporting in Rapthor. | A Rapthor patch against the current pin selects the backend by flag, respects the caller's resource budget, and reports dual-run differences. |
| Agent, human dispositions | Measure Rapthor-profile agreement within the release-check budget, using cached reference outputs. | Retained/rejected agreement against pinned `master` on true/apparent, bright, extended, edge, masked, sparse and crowded populations. Choose `compact` only with ≥99.5% overall agreement and every safety stratum passing; otherwise `continuum`. |

### M4 — Deployment performance gate

| Owner | Task | Done when |
| --- | --- | --- |
| Human freezes, agent proposes | Freeze the initial deployment envelope. | Sizes and workloads match Rapthor's production sectors and fit the development machine. |
| Agent | Run matched complete `filter_skymodel` benchmarks and optimize until the runtime gate passes. | Hebog and pinned `master` run in the same Linux container on the development machine, with cached reference timings. The ratio and its upper one-sided 95% bound pass on every envelope cell; memory and Hebog-curve non-regression and the quick science check pass. Native code enters only through the native-code gates and an accepted ADR. |

### M5 — Prepare scale beyond one machine

All rows run on the development machine; none needs the cluster.

| Owner | Task | Done when |
| --- | --- | --- |
| Agent | Bound the graph for 100,000² at 10 and at 200 nodes without running the science. | Planner tests show at most 50,000 tasks, bounded reduction depth, bounded driver memory and a valid memory admission for both topologies. |
| Agent | Qualify the Zarr store and restart/recovery path locally. | Atomicity, owned-chunk writes from concurrent local workers, codec and chunk geometry, missing chunks and injected failures pass within an admitted memory budget. Shared-storage throughput is left to the cluster benchmark. |
| Agent proposes, human approves | Amend the scalability contract. | `config/benchmarks/phase-0-scalability.json`, the performance and scalability contracts page and the `test-scalability` recipe describe the development-machine tier and the final 1, 2, 5 and 10-node benchmark. The 50, 100 and 200-node gates are kept as design targets, not deleted. |
| Agent | Package the cluster benchmark. | One command and a short guide run the 90,000² LOFAR-HD mosaic at 1, 2, 5 and 10 nodes, plus the 22,500² and 45,000² versions for size scaling, and record evidence, the hardware and a scaling-model fit. A dry run with a local Dask cluster at small sizes passes, so the cluster session measures rather than debugs. |

### M6 — Qualification and 1.0.0

| Owner | Task | Done when |
| --- | --- | --- |
| Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed; later changes restart only the affected qualification rows. |
| Agent designs, human approves | Run one powered parity/retention study with fresh held-out and public-survey data, sized to finish overnight on the development machine. | Every binding endpoint passes under a prospectively reviewed contract, population and power design, including the limitations that block 1.0.0 and the LOFAR, SKA-Mid and SKA-Low families in the 1.0.0 definition. Closed failed campaigns are never reused as confirmation. |
| Human runs, agent analyses | Run the cluster benchmark. | Strong scaling at 1, 2, 5 and 10 nodes and size scaling across the 22,500², 45,000² and 90,000² mosaics meet the amended gates, with invariant results and the M4 runtime gates confirmed on cluster hardware. A failure becomes a normal `0.x` repair row. |
| Agent | Check released PyBDSF 1.14.1 once. | One matched run against 1.14.1, cached for reuse, confirms Hebog ≤0.50× release on the deployment envelope and Rapthor-profile agreement against the release. A failure is reported with its cause before the 1.0.0 decision. |
| Human runs in Rapthor, agent supports | Operational trial behind the Rapthor flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| Agent assembles, independent reviewers accept | Readiness packet and acceptance. | The packet binds science, Rapthor profile, performance, scale, portability, security, licensing, packaging and current documentation, with separate radio-astronomy and engineering acceptance. |
| Human | Release 1.0.0. | Release Please produces 1.0.0 (for example through a `Release-As: 1.0.0` commit footer) and the package publishes to PyPI. |

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The 8–20× gap on real images does not close with NumPy/SciPy and Numba. | M4 fails. | Profile first; attack algorithmic cost before constant factors; use the native-code gates only for a profiled kernel. Report the gap honestly at each milestone. |
| Extended association cannot be made exactly tile-invariant. | M2 stalls or changes science. | Design ownership and boundary summaries before code; test analytic shells and filaments crossing corners early; escalate a scientific trade-off to the human rather than weakening invariance silently. |
| Scheduler, reduction or storage bottlenecks appear only above 10 nodes. | A later deployment at 100+ nodes fails or scales poorly. | Planner bounds for 200 nodes, a scaling model fitted to the cluster benchmark, and an explicit "not demonstrated" statement in release notes. |
| Large public images have minimal or non-standard headers; the HD mosaic is published "for browsing only". | Anchors cannot run unmodified, or their science comparison is weak. | Headers checked 16 September; explicit metadata in M1; per-facet HD images and catalogues for science; LoTSS-DR3 mosaics as the fallback scale anchors if an HD mosaic proves unusable. |
| No large public SKA-Low image exists. | SKA-Low coverage relies on MWA precursor data. | GLEAM-X DR1 with its PSF maps (its Aegean catalogue is diagnostic only), and SKA-Low science-verification data once released (expected from 2027). |
| Rapthor and LSMTool change frequently. | Adapter, contract and benchmark churn, or a backend that only works on a stale revision. | Pin the latest commits when M3 starts. Move both pins forward deliberately, not continuously: before the Rapthor patch, before the M4 benchmarks and at the M6 freeze. At each move, rerun the contract audit, the acceptance scenarios and the Rapthor-profile agreement check, and record the revisions in `LOG.md`. |
| Short checks miss a rare regression. | A defect reaches a `0.x` release. | Releases stay experimental; each escaped defect adds a fixed case; the powered M6 study is the backstop. |
| The development machine's 18 GiB RAM and free disk limit local tiers. | Tiers above 22,500² stall, or runs spill to disk and slow iteration. | Tile-bounded memory from M2 onward; about 60 GB of free disk before tiers above 22,500²; 90,000² only on the cluster. |
| Scientific campaigns absorb the schedule again. | Performance and scale slip. | Iteration budgets, cached references, endpoints limited to Rapthor-consumed fields and one overnight powered study at M6. |

## Scientific gates

Analytic or injected truth is primary. Pinned PyBDSF `master` at `c70103b`
(`v1.14.1-40`, the Phase 5 reference) is the binding finder reference.
Released 1.14.1, which Rapthor installs today, is checked once at M6. The two
diverge scientifically (14 versus 12 sources on the representative 3,000²
image), so neither is truth. Later upstream `master` commits are adopted only
by a deliberate plan decision, which invalidates cached reference outputs.
Aegean comparisons are paused: they are neither binding nor run routinely
while development focuses on PyBDSF, the finder Rapthor uses, and the M6
qualification design decides whether to reinstate them. No finder is
scientific truth.

- Each campaign uses its own prospectively reviewed endpoint registry and
  decision contract. Choose a whole incumbent before viewing results; never
  combine historical best values into a synthetic comparator.
- Require every applicable relative PyBDSF and incumbent Hebog
  comparison, with fixed practical margins and the conjunctive one-sided
  confidence rule. Inconclusive binding evidence is not parity. An old
  candidate's uncertainty exception does not transfer to a replacement.
- Freeze population, semantic applicability, independent sampling unit,
  margins, missing-output rules and endpoint and joint power before execution.
  Pair and resample whole realizations, not dependent source rows or pixels.
  Planning variance sizes the study; the observed-data interval decides.
  Superiority claims need a prospective multiplicity rule, and improvements
  cannot compensate for failed binding checks.
- Product validity, finite or explicitly unavailable measurements, complete
  processing status, schemas, provenance and deterministic execution remain
  binding. Report absolute targets separately. Retain all morphology, scale,
  SNR, noise and boundary strata.
- Compare like source, component and support semantics. Use original pixels
  for flux and photometry and valid pixels for mask precision, recall and IoU.
  Report splits, merges, duplicates and low-SNR completeness and reliability
  separately.
- Before a long campaign or replay, run a bounded development screen through
  the same runner and evaluator with an explicit time and resource budget.
  Select cases before inspecting results: ordinary controls, independent
  examples of known failure mechanisms, valid empty results, and numerical and
  invalid-pixel boundaries. Exercise the public finder, native product
  reading, evaluation, aggregation and Serial/existing-Dask agreement. A
  clean screen is neither powered parity nor a prediction of campaign
  success; resolve or explicitly defer its warnings before launch.

The dataset matrix retains compact SNR 3–100, blends, diffuse Gaussians,
filaments and shells, mixed emission, different beams, WCS, pixel scales and
units, negative backgrounds, empty, all-NaN and invalid data, varying noise,
image edges and all tile-edge and corner topologies. Every dataset has a
development, regression or qualification role, provenance, checksums and
generator identity, and new populations must be seed-disjoint from existing
manifests. General qualification includes full public or challenge images
from LOFAR, SKA-Mid and SKA-Low (precursor data until SKA-Low data are
public), plus at least one other instrument. Compare Serial before alternate executors and
external finders.

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
strict as the former ≤0.50× release gate. M6 confirms the release ratio once.

Scientific eligibility precedes performance acceptance. These are minimum
deployment gates, not a reason to stop optimizing or to hold an experimental
standalone release.

- Maintain 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000 and 100,000-square
  anchors (with the real images below alongside the nearest anchor), sparse,
  normal and dense-extended workloads, and both sides of every measured
  crossover. Gate early deployment on its frozen envelope;
  1.0 qualification needs the whole matrix up to the 90,000² LOFAR-HD mosaic,
  with 100,000² covered by planner tests only.
- Compute reference-finder timings once per input, revision and host and
  reuse them; rerun them only when one of those changes.
- Match inputs and checksums, revisions and dependencies, output mode, host,
  affinity, CPU and native threads, workers, memory, storage and cache policy.
  Use a warm-up plus at least five measured repetitions, retain every value,
  median and dispersion, and avoid unrelated workloads.
- Record wall and CPU time, worker and aggregate RSS, I/O, task and graph size,
  transfers, spill, failures and retries, tile and halo geometry, boundary
  summaries, occupancy, scheduler load, throughput and headroom. Scale
  evidence adds reduction depth, stragglers and strong/weak efficiency. Record
  unavailable instrumentation with a reason, never zero, using versioned
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

Public candidates found on 16 September 2026. Headers of the LOFAR-HD
mosaics and facet 0, LoTSS-DR3 mosaic 1312 and SDC1 B2 1,000 h were read
that day with range requests; dimensions marked "inferred" come from file
sizes or catalogue metadata. Check other headers before a large download. No
image data or dataset belongs in Git.

| Family | Image | Size | Use | Reference |
| --- | --- | --- | --- | --- |
| LOFAR | LOFAR-HD ELAIS-N1 mosaic, 0.4/0.2/0.1″ pixels | 22,500², 45,000², 90,000² (2.0, 8.1, 32.4 GB); 2-D `float32`, `JY/BEAM`, SIN, beam present, no frame or reference-frequency keywords | Largest real scale anchor; same-field size ladder | Per-facet PyBDSF catalogues; facets are WSClean FK5 J2000 images |
| LOFAR | LoTSS-DR3 HEALPix mosaics (1,571) | 14,390–17,752² (1312: 15,402², ICRS, `RESTFRQ`, beam present) | Science and throughput | PyBDSF catalogue plus per-mosaic RMS, residual and mask maps |
| LOFAR | LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky pair | about 14,000² (inferred) | Closest public match to Rapthor's two inputs | PyBDSF catalogue and maps |
| SKA-Mid | SDC1 B1/B2/B5, 8/100/1,000 h | 32,768² (4.3 GB each); 4-D, `JY/BEAM`, `EPOCH = 2000`, `BMAJ`/`BMIN` but no `BPA` | Science checks with truth (cut-outs) | Full truth catalogues |
| SKA-Mid | MeerKAT MIGHTEE DR1 XMM-LSS; SMGPS tiles (Galactic, multi-plane) | about 20,900² (inferred); 7,500² | Real precursor science; header variety | PyBDSF (MIGHTEE); Aegean (SMGPS, diagnostic only) |
| SKA-Low | MWA GLEAM-X DR1 mosaics | not checked (2.8 GB) | Precursor science with a PSF that varies across the field | PSF maps; Aegean catalogue (diagnostic only) |
| Other | ASKAP EMU-PS1 (CASDA login) | 44,911 × 33,569 | Optional non-SKA-family image | Selavy catalogue |

## Architecture and documentation boundaries

Keep the scientific library pipeline-neutral, with inert imports, small typed
requests and results, and no implicit clients, clusters or pools. Maintain
one tile-native science composition for every image size, Serial as the
oracle, Zarr as the sole intermediate plane backend,
stage-specific halos, global ownership and hierarchical reductions. Never
raise the public size limit by sending a complete large plane to one worker.
Preserve dtype unless scientific evidence supports a change. Prefer
established libraries, NumPy/SciPy, then profiled Numba; new native code needs
an accepted ADR, the 10% profile, 2× kernel and 5% end-to-end gates, and
portable distribution. The [architecture](../docs/architecture/index.md),
[native-code assessment](../docs/explanation/native-code-assessment.md) and
[`AGENTS.md`](../AGENTS.md) hold the detailed requirements.

Keep the README, docs home, release status and tutorial focused on current
behaviour, replacing stale summaries when status changes. Record chronology in
`LOG.md` or Git history, not as another "latest" section in user guidance.
Removing a historical narrative never changes a closed result.
