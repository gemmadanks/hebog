# Hebog implementation plan

Authoritative remaining-work plan for 1.0.0. Updated **16 October 2026**.

This file holds the definition of 1.0.0, the rules that govern the work, the
ordered tasks that remain, the decisions the maintainer still has to take,
the risks and the gates. It does not hold measured figures, which live on
[progress against goals](../docs/reference/progress-against-goals.md), or
user-facing capability and limits, which live in
[release status](../docs/reference/release-status.md). Git history records
completed work with its rationale, validation and evidence references; ADRs
record architecture decisions; [`LOG.md`](../LOG.md) is a historical archive
and receives no new entries. Closed Phase 5 contracts, reviews and campaign
tooling are in Git history at `4babf0b`.

## Current state

The figures behind this table, with their dates and run labels, are on the
progress page; the two change together.

| Item | Position on 16 October 2026 |
| --- | --- |
| Release | v0.21.0 (12 October) on TestPyPI. The 0.22.0 candidate, which carries tasks 16, 20, 21, 23 and 77 (Rapthor integration), 73, 74, 71, 55 and 54 (one sector's speed) and the switch to PyPI (task 13), passed its release check on 15 October. It ships once the maintainer adds PyPI's Trusted Publisher, merges the stack (PRs #169 to #172, then the PyPI switch and the screening tooling) and merges the release PR (#160). Every release is experimental and scientifically unqualified. |
| Candidate | Public composition v23. The quick check's catalogue, RMS and mask are byte-identical to v0.19.0's; only the composition hash has moved. Development-unqualified. |
| Functionality | The standalone finder is complete under Serial, Thread and caller-owned Dask executors within the 15,402² envelope. The Rapthor adapter is complete, and the [prepared Rapthor patch](../scripts/validation/patches/README.md) runs it on Rapthor's interim one-single-threaded-worker-per-node layout with a thread executor, memory admission, PyBDSF fallback and dual runs. Upstream publication waits on 0.22.0 (task 79). |
| Performance | The deployment gate fails: 2.03 times pinned `master` on the first matched measurement (3,000² sector, thread path, four cores), where LSMTool's filtering alone floors the ratio at 0.26. One sector on four local Dask workers takes 0.36 of one worker's time on the 10,000² anchor, with a 20% serial share; threads in one process barely scale. The production-size screening pair (task 78) runs overnight on 16 to 17 October. |
| Science | Rapthor keeps or rejects alike with Hebog's `compact`/zero mask and pinned `master`'s for 92.8% of sky-model components, against a 99.5% target that released PyBDSF also misses (99.29%). `continuum` loses real faint sources on deep fields (task 75). The agreement check does not yet measure each lane against truth (task 76). |
| Blockers | Every task under [Path to 1.0.0](#path-to-100). Largest risks: the performance gap, the agreement gate's form, memory that grows with the image and the sources found, the development machine's limits, SKA-Low data, upstream churn and cluster availability. |
| Next action | Agent: read task 78's results and apply its rule, run task 76 beside it, raise the 22,500² tier unattended (task 11) and start task 72. Human: the release steps above, then publish the patch (task 79), file the Astropy report drafted on 5 October (`benchmark-results/upstream/astropy-wcs-d-exponent.md`) and take the [decisions below](#decisions-pending). |
| Deferred | Scientific improvements that are not confirmed incorrect supported outputs wait until the integration and scaling work is complete (decision of 9 October): tasks 75, 68 and 15 sit before the freeze, and the rest is here. Meshes scaled with the restoring beam, which would admit beams wider than 10 pixels (task 62's measurement: every SNR ≥ 10 source recovered to 22 pixels at about 2.5 times the local-noise read); every real Rapthor image is at most about 7 pixels. Wide-object reductions on the cores instead of the driver, reopened when a tier's traced peak shows the term or when the cluster benchmark is planned. Aegean, ProFound and SoFiA comparisons. PyBDSF's second grouping rule, which Rapthor's island grouping does not need. Native code without a passing profile gate. A confirmed incorrect supported output reopens its item at once. |

## Definition of 1.0.0

Version 1.0.0 is the first release demonstrated to meet the project goal,
with every claim bound to reviewed evidence for that exact candidate:

- **Telescopes.** The standalone finder accepts standard FITS continuum
  images from any radio telescope that meet the documented
  [input header contract](../docs/reference/input-header-contract.md), and
  is validated first on LOFAR, SKA-Low and SKA-Mid images. It accepts their
  imager conventions (WSClean, CASA and SKA SDP products) or rejects them
  with a specific error.
- **Functionality.** Hebog is a supported, feature-flagged backend for
  Rapthor's `filter_skymodel`, selected through Rapthor's `source_finder`,
  at a pinned Rapthor and LSMTool revision: true-sky and flat-noise
  branches, the Rapthor profile, native catalogue, mask, RMS and
  source-count products, empty and blanked-image paths, retry and restart,
  and PyBDSF fallback. The standalone public API remains usable without
  Rapthor, Prefect, LSMTool or Dask.
- **Science.** The Rapthor profile reaches ≥99.5% retained/rejected
  component agreement with every safety stratum passing (its binding form
  is decision 1 below), and the frozen candidate passes prospective,
  powered, held-out parity/retention against pinned PyBDSF `master`
  (`c70103b`); a single check against released PyBDSF 1.14.1 confirms
  Rapthor-profile agreement for users of the release. The evidence includes
  full images, not only cut-outs, from LOFAR, SKA-Mid (SDC1 simulations and
  MeerKAT) and SKA-Low (MWA precursor data until SKA-Low data are public;
  decision 5).
- **Performance.** On the development machine, matched complete
  `filter_skymodel` medians meet the runtime gate across the deployment
  envelope without a memory or Hebog-curve regression. The final cluster
  benchmark confirms them on the cluster's hardware (decision 6).
- **Scalability.** Scale evidence uses LOFAR images only. On the
  development machine (18 GiB RAM), the 45,000² LOFAR-HD mosaic completes
  with peak memory bounded by tile size, although one `float64` copy of
  the image alone would not fit in memory. Results do not change with
  worker count, tile geometry, completion order or retry. A final cluster
  benchmark, run once for 1.0.0, processes the 90,000² LOFAR-HD mosaic on
  1, 2, 5 and 10 nodes within the amended runtime, task-count,
  scheduler-overhead, memory and spill gates (its scope is decision 4).
  Planner tests bound graph size and reduction depth for 100,000² images on
  100 to 200+ nodes. Release notes say that 100,000² images and that node
  count are designed for but not demonstrated.
- **Release.** Published on PyPI with portability, security, licensing,
  current documentation and independent radio-astronomy and engineering
  acceptance.

Rapthor's default cutover is a separate Rapthor decision taken after an
operational soak of the 1.0.0 backend; the PyBDSF fallback remains until
then.

## Decisions pending

Each decision names the maintainer's call and the agent's recommendation.
A decision taken here is recorded in the affected row and in the commit,
never in `LOG.md`.

1. **The retained/rejected gate's form.** The 99.5% target is unmet by
   every Hebog lane (92.8% at best) and by released PyBDSF 1.14.1 (99.29%),
   so as written it cannot be passed by the finder Rapthor installs today.
   Today the form is decided in task 29's design, after the scaling work.
   *Recommendation:* decide it when task 76's truth measures are in, before
   task 72 ends: bind the gate to the components Hebog's mask rejects and
   `master`'s keeps that truth or the negative-pixel noise shows to be real
   emission, per stratum, with the agreement percentages reported beside
   it; a component `master` keeps on noise, or Hebog keeps on real emission
   `master` misses, is compatibility, not a failure.
2. **The sequence of tasks 11 and 56.** The plan ran task 56 before the
   22,500² tier. The tier's forecast traced peak is about 2.1 GiB, its disk
   need about 12 GB, and the deployment envelope (task 22) cannot be frozen
   without it. *Recommendation:* raise 22,500² unattended now, beside task
   72, and keep task 56 before the 45,000² tier, whose forecast peaks (4.3
   and 6 GiB) need it.
3. **Task 72 as separate releases.** Its done-when holds four increments.
   *Recommendation:* merge and release them in the order its row gives, so
   Rapthor's distributed path ships before the concurrent-analysis work.
4. **The cluster benchmark's scope (tasks 27 and 30).** The definition
   asked for 1, 2, 5 and 10 nodes on the 22,500², 45,000² and 90,000²
   mosaics and one Rapthor sector, fourteen or more long runs on hardware
   that has not been scheduled. *Recommendation:* one Rapthor sector at its
   default size through Rapthor's native task at 1, 2, 5 and 10 nodes (use
   case 1), and the 90,000² mosaic standalone at 1 and 10 nodes (use case
   4); size scaling to 45,000² is measured locally. Task 26's contract
   amendment folds into task 27.
5. **SKA-Low and the position-dependent PSF (task 15).** No target pipeline
   produces a PSF map, and the only SKA-Low precursor image (GLEAM-X) needs
   one. *Recommendation:* for 1.0.0, task 15 measures the effect of the
   varying PSF on fluxes and sizes with injected truth and documents it as
   a limitation; a PSF-map input is a 1.x feature unless the measured
   effect changes a Rapthor-consumed field. SKA-Low's 1.0.0 evidence is one
   GLEAM-X mosaic run under that documented limitation.
6. **Where the performance gate is measured.** The development machine's
   Podman VM has 16 GB, and pinned `master` may not hold a 15,402² or
   22,500² sector in it. *Recommendation:* task 23 measures every envelope
   cell the VM holds, and task 30 measures the rest on the cluster; the
   gate's form is restated only if task 78 shows LSMTool's filtering alone
   above half of `master`'s step on a production-size sector.
7. **The pins.** Since the 13 October checkpoint Rapthor's `main` has moved
   one commit (`aff26023`, an array-beam option) and LSMTool's `master`
   twelve, including a `_get_xy` optimisation that changes LSMTool's share
   of the step; PyBDSF's `master` is 91 commits past `c70103b`.
   *Recommendation:* move the Rapthor and LSMTool pins at task 79, before
   the patch is published, with the contract audit, the acceptance
   scenarios and `just rapthor-agreement` re-run and the reference timings
   re-cached; keep PyBDSF at `c70103b` until the freeze (task 28).
8. **Independent acceptance (task 33).** Reviewers have not been named.
   *Recommendation:* approach the radio-astronomy and engineering reviewers
   when the patch is published, so their review runs beside Rapthor's.

## Scope and resource rules

- **Use cases** (maintainer, 10 October 2026). Four, each a performance
  target; none may be optimized by regressing another:
    1. *One Rapthor sector across a cluster* of nodes with up to 192 cores,
       tens of nodes possible: the usual Rapthor run and the first
       performance focus.
    2. *One Rapthor sector on one node*: the other main Rapthor run, and
       the deployment gate's like-for-like comparison with PyBDSF.
    3. *Standalone use on a local machine* with smaller images, through
       the public API and the Serial or Thread executor, where setup and
       scheduler overhead dominate.
    4. *Standalone use on a cluster*, for an image too large for one node,
       on a Dask cluster the user starts.

  Several Rapthor sectors at once stay supported. Hebog defines what it
  needs from a Dask cluster and the caller provides it
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md));
  Rapthor builds the executor from its layout and passes it in
  ([layouts](../docs/architecture/rapthor-execution-layouts.md)). The
  target is two-dimensional continuum images; a cube or time axis is a
  new ADR, and the executor protocol stays blind to the image's
  dimensions.
- **Compute.** Development, checks and benchmarks run on the maintainer's
  machine (Apple M3 Pro, 12 logical CPUs, six performance cores, 18 GiB
  RAM; a 16 GB, six-core Podman VM for the containers). A cluster of up to
  10 nodes runs one final benchmark for 1.0.0 and never blocks development;
  record its hardware when that benchmark is scheduled.
- **Disk.** The 22,500² tier needs about 12 GB; the maintainer frees disk to
  about 60 GB before the 45,000² tier (8.1 GB of input, up to 16 GB of RMS
  and mask output, up to about 24 GB of Zarr intermediates). The local
  ladder stops at 45,000²; 90,000² runs only on the cluster.
- **Data.** Scale testing uses public LOFAR images; no generated 100,000²
  image or simulated SKA-Low image is built, and the only generated large
  image is the 10,000² wide-object diagnostic. The public LoTSS-Deep DR2
  ELAIS-N1 apparent and primary-beam-corrected pair is the representative
  two-branch Rapthor input. SDC1 cut-outs serve science checks for SKA-Mid.
  See [reference images](#reference-images).
- **Pins.** Rapthor `main` at `d0e7e148` (the Prefect/Dask line since the
  9 October 2026 merge; `master` is the CWL/Toil release line and not a
  target), LSMTool `master` at `9bac2f7` (v1.9.0 plus 15 commits) and
  PyBDSF `master` at `c70103b` (`v1.14.1-40`). Rapthor and LSMTool pins
  move only at the checkpoints the [risks](#risks) name, with the contract
  audit, the acceptance scenarios and the agreement check re-run and the
  outcome recorded in the commit. If Rapthor declares a different LSMTool
  revision, record both and test the latest LSMTool.
- **Limitations that block 1.0.0.** Of the limitations accepted for v0.7.0,
  those that change Rapthor-consumed fields must pass before 1.0.0:
  `E_RA`/`E_DEC` calibration on a real high-declination field (it passes
  on beam-correlated noise; `E_RA` is a great-circle angle, as PyBDSF
  publishes it and Rapthor's cut compares it); the `Total_flux` rows of the
  [scientific gates](#scientific-gates), which pass on independent
  realizations; and faint association where it changes island grouping,
  and therefore patches. The other accepted limitations stay documented
  limitations.

## Delivery policy

Ship frequent, useful experimental `0.x` increments, normally one release
for each merged task that changes behaviour. Development favours fast
iterations over long campaigns; every check has a budget on the
development machine, and a check that outgrows its budget is sampled,
split or moved to a less frequent level, never silently extended:

- **Change check (about 15 minutes):** relevant tests, the quick science
  check and, for performance-relevant changes, the quick benchmark's
  default tier. Runs for every change that can affect science or runtime.
- **Release check (about 1 hour):** the change check, Serial/Dask
  agreement on the largest anchor whose two runs fit the hour (10,000²
  today) and the installed wheel. Runs before each `0.x` release. The
  quick benchmark's large tier runs for profiling and before a release that
  claims a runtime change, never waited on otherwise.
- **Tier gate (up to a day, unattended):** the gate under
  [the size ladder](#bounded-growth-and-the-45000-pixel-tier) on a new tier's
  anchor, once for each envelope raise.
- **1.0.0 qualification (once):** one powered science study sized to finish
  overnight on the development machine, and one benchmark on the cluster.
  Neither blocks `0.x` development or releases.

PyBDSF outputs and timings are computed once for each input, reference
revision and host, cached outside Git with checksums, and reused. A defect
that escapes the quick checks adds its case to the fixed case set. PR CI
shards the complete supported-platform suite as the
[contribution guide](../docs/how-to/index.md#pull-request-feedback)
describes; hosted timings guide CI scheduling only.

The four levels of done stay distinct:

- **Merge:** a coherent reviewed change with passing applicable tests and
  accurate documentation. Merge each PR in a sequence before branching the
  next, so CI isolates the responsible change.
- **Experimental release:** a tested package that states its unqualified
  science and current limitations and has no unresolved confirmed
  incorrect supported output. It need not establish general PyBDSF parity,
  the Rapthor speed target or facility scale.
- **Scientific qualification:** candidate-bound parity and quality
  retention, fresh held-out evidence and independent scientific and
  engineering acceptance. An experimental label never turns a failed or
  underpowered check into a pass.
- **Rapthor deployment or default cutover:** separately qualified workflow
  behaviour, complete-path performance and operational acceptance, with the
  feature-flagged PyBDSF fallback retained until the acceptance matrix
  passes.

Ownership follows
[`AGENTS.md`](../AGENTS.md#changes-releases-and-handoff): the agent
implements, validates, documents and commits locally; the human pushes,
merges, runs notebook refreshes and makes scientific and priority
decisions. Explicit user authorization may delegate a push or PR update to
the agent. Release Please alone edits versions, the changelog and release
notes.

## Collaboration and repair decisions

These rules govern agent work on this plan and are referenced from
[`AGENTS.md`](../AGENTS.md).

- The agent owns routine completeness checks, integration checks and clear
  recommendations. Do not depend on the user discovering missing checks,
  requesting a cheap diagnostic or reconstructing status across
  conversations. Reserve human attention for scientific interpretation,
  priorities and trade-offs that require human judgment.
- Before a scientific or campaign repair, write a short decision statement
  in the existing task or plan: observed problem, proposed cause,
  independent test, expected measurable change and stopping condition.
  Distinguish a correctness defect, agreed-gate failure, operational
  failure and optional improvement; an aggregate failed endpoint alone does
  not establish a cause.
- After two repairs aimed at the same mechanism produce no material change
  against the stated expectation, review the diagnosis and recommend a
  bounded next step before another full replay. This is a reassessment
  trigger, not permission to abandon required work, change gates or retry
  closed evidence.
- Keep development closure, scientific qualification, release and default
  cutover distinct, as in the delivery policy. Record optional improvements
  as deferred work rather than expanding the current milestone. Known
  incorrect supported outputs remain release blockers; a phase label or
  accepted development limitation cannot waive them.
- Carry existing authorization forward within its scope. Complete
  authorized preparation and present a concrete recommendation before
  requesting a new scientific or resource decision. Explain the exact
  boundary requiring that decision; do not add approval steps for routine
  reversible work.
- At milestone reviews, use Git history, PR discussion and existing
  evidence to assess time to actionable diagnosis, avoidable campaign
  interruptions, repairs without useful change and user effort needed to
  recover status or scope. Use these observations to improve the workflow,
  not commit counts, test totals or documentation volume as productivity
  targets. Do not introduce a separate tracking framework.

## Path to 1.0.0

A task number is a stable identifier: a completed task is removed and its
number is not reused (numbers up to 79 have been used). The sections, and
the rows within them, are in the order the tasks are expected to finish.
Each is a bounded work item that merges, and normally releases as a `0.x`
increment, within the iteration budgets; split a task when a measured
result reveals independent changes. Unless a task says otherwise, the agent
implements and validates on the development machine and the human merges.
A qualification, scale or deployment task authorizes only its stated claim
and still needs the named human decision.

Four rules govern the sequence. **Measure before changing:** nothing is
optimized or re-architected without a profile, and no science-touching
change merges without `just quick-science-check`. **One tier and one
release at a time:** the public envelope rises only through its tier gate,
and every raise is a release. **Products unchanged through a refactor:** a
change made for readability or structure leaves the quick check's
catalogue, RMS and mask byte-identical, with only the composition hash
moving, and no production file loses coverage; a removal starts with the
test that fails for the reason its row states. **A review's figure is
confirmed on a real anchor** before a task that changes cost or memory
closes.

The order, set on 9 October 2026 and amended through 16 October:

1. **Ship 0.22.0 on PyPI and publish the Rapthor patch** (tasks 13 and 79),
   so Rapthor can install Hebog. The integration waits on no tier: its
   inputs are inside the 15,402² envelope, and Rapthor's 3,000²
   demonstration sector is refused for its 30-pixel synthetic beam, not
   its size.
2. **Screen production-size performance before weeks go into scaling**
   (task 78, decision of 16 October), with the agreement check's truth
   measures (task 76) and the 22,500² tier (task 11) beside it.
3. **One sector across the cluster** (task 72). Rapthor usually images one
   sector, 17,000 to 20,000 pixels a side, on nodes of up to 192 cores;
   its interim thread path cannot use a node's cores, so the distributed
   path comes before the rest of the ladder (decision of 15 October).
4. **The deployment envelope and gate** (tasks 22 and 23), then bounded
   growth and the 45,000² tier (tasks 56 and 12) and scale beyond one
   machine (tasks 24, 25 and 27).
5. **Science before the freeze** (tasks 75, 68 and 15), deferred until the
   work above is complete unless an output is confirmed incorrect.
6. **Qualification and 1.0.0** (tasks 28 to 34).

### Release and publication

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 13 | Human | Switch uploads from TestPyPI to PyPI. | From 0.22.0 (decision of 15 October): the prepared patch's `rapthor[hebog]` extra must install from PyPI, and the unclaimed name `hebog` would invite a squatter once a public patch names it. The publishing job, installation instructions, guide and release status have changed on the stack. Done when the maintainer has added PyPI's Trusted Publisher and `pypi` environment ([publishing guide](../docs/how-to/publish-releases.md)), merged the stack and the release PR, and 0.22.0 installs from PyPI. |
| 79 | Human publishes, agent prepares | Publish the Rapthor patch upstream. | The pins move to Rapthor's and LSMTool's current heads (decision 7), the contract audit, acceptance scenarios and `just rapthor-agreement` are re-run at them, the integration container is rebuilt and its summary re-recorded, and the patch's `hebog` requirement names the PyPI release. Done when the merge request is open against Rapthor's `main` with the dual-run mode and the PyBDSF fallback described, and Rapthor's maintainers have been asked to run a dual run on a production field, which seeds task 32. Until it merges, the integration container installs the recorded local commit. |

### Screen before scaling

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 78 | Agent runs, human reads | Screen the filter step at production size on Dask workers, and run the deep sector like for like. | Decision of 16 October, in flight overnight on 16 to 17 October (`benchmark-results/filter-skymodel/overnight-2026-10-16.sh`): Rapthor's complete `filter_skymodel` step with Hebog on four local Dask workers against pinned `master`, one run each in the matched container on the 15,402² LoTSS-DR3 mosaic (the 10,000² anchor if `master` outgrows the VM), through `measure_filter_skymodel.py --hebog-dask-workers`, whose worker-side swap stands in for task 72's path and never counts towards the gate; and the whole ELAIS-N1 sector serially under `continuum` with the estimated background at the 0.22.0 candidate, to attribute the 6.6-fold speed-up of 15 October between the profile change and tasks 74, 55 and 54. Done when both are recorded on the progress page and the rule below has been applied (proposed): if Hebog's finder part on four workers is within twice `master`'s, task 72 proceeds; if it is several times `master`'s, a profile of the production-size run comes first and its largest constant factors are cut under task 23 before the topology work; if LSMTool's filtering alone exceeds half of `master`'s step, decision 6 restates the gate. |
| 76 | Agent | Measure each lane's correctness beside its agreement with `master`. | `just rapthor-agreement` also reports, for every lane, `master` and the released control: mask decisions and emission recall against injected truth on the generated cases, the ideal mask being the noiseless emission at `threshisl` sigma or more connected to a `threshpix` peak; completeness and flux of sources injected into the real LOFAR images (the LoTSS-DR3 window and the ELAIS-N1 pair) by SNR; false islands on the negated real images; and each RMS map against the RMS of negative pixels, which faint sources cannot inflate. Exploratory scripts of 13 October found 34, 55 and 9 false islands on ELAIS-N1 for `master`, `compact`/zero and `continuum`. Done when these are tested pure functions within the release-check budget, the progress page summarises them, and decision 1 has what it needs. |
| 11 | Human frees disk, agent raises | Raise to 22,500² on the LOFAR-HD ELAIS-N1 mosaic. | About 12 GB of disk is free and the mosaic's restoring beam is read and recorded first: its name suggests about 3 pixels a beam, where the support pass's opening used to remove most 5 to 6σ compact sources (`LOG.md`, 4 October). The tier gate passes, recording the diagnostics' bright candidate count and largest bright-region read, and the raise is a release. Runs unattended beside task 72 (decision 2). |

### One sector across the cluster

The design stays Dask-native and simple: Hebog's tile tasks are
single-threaded and numerous, Dask schedules every core, no thread pool is
nested inside a Dask task, and Hebog's arrays stay NumPy behind its
executor protocol (ADR-004 and ADR-005), not Dask arrays. The aim is a
strong-scaling curve for one sector that keeps falling while cores are
added, not the use of every core; several sectors share the cluster beyond
the point where one stops scaling. The baseline is run `task74-stack`
(15 October): the 10,000² anchor in 1,357 s on one worker and 429 s on six,
with no task running for 77 s and a 20% serial share, so the speed-up cap
is near five; eight workers swapped up to 24 GB, and rounds hold only 7 to
25 tasks.

Task 72 lands as four increments, each merged and released in turn
(decision 3):

- **Core budget and cost model.** The caller states the cores Hebog may
  use, defaulting to the client's capacity, since a client's capacity
  counts threads that DP3 or another analysis holds. Each stage chooses its
  tile core from its halo and its task count from batching by a stated
  cost model fitted to task 73's and 78's measurements, holding the memory
  a worker needs per core as well as its tiling, so parallelism rises
  without small cores multiplying halo overhead. The memory each task
  declares follows the chosen core; the composition's run settings
  (executor, work directory, generation, tile core) become one record; the
  run's timing record states the tiling and budget chosen; a small image
  stays one tile with no scheduler overhead (use case 3). Products depend
  on none of it.
- **Waiting and sharing.** An analysis started inside a worker task secedes
  while it waits on its tile tasks. Once tasks are packed by declared
  memory, each round's declaration is re-audited against its measured peak
  (`scripts/benchmark/audit_task_memory.py`; background's grouped pilot
  declares about five times its peak). A local multi-worker cluster runs
  one analysis, several concurrent analyses and workers joining between
  analyses without deadlock or changed products.
- **Rapthor's distributed path.** The patch passes its client and resource
  names (`memory_resource`, `core_resource`) to `DaskExecutor`, reserves
  the analysis memory on the driving task and retires its interim thread
  path. What Hebog needs from a cluster is documented for any caller
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md)),
  with one way Rapthor can provide it beside DP3 and WSClean.
- **Both branches together.** The true-sky analysis and the flat-noise
  estimate submit their tile tasks through the executor at once, not
  through a thread of Hebog's own, so the serial reference stays
  single-threaded.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 72 | Agent | Make Hebog's tasks scale on any Dask cluster, Rapthor's included. | The four increments above have merged and released. Products are byte-identical across the thread and Dask paths in the executor contract suite, and task 73's curve, re-measured with the cost model's tiling, falls further than the baseline above. |

### The deployment envelope and gate

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 22 | Agent proposes, human freezes | Freeze the initial deployment envelope. | Sizes and workloads match Rapthor's production sectors (17,000 to 20,000 pixels a side; the demonstration sector is 3,000² and refused for its beam) and fit the development machine, and the envelope tier that covers them is admitted, which is at least 22,500² (task 11). The LSMTool share of the step on production-size sectors is measured (task 78) before the freeze. |
| 23 | Agent | Run matched complete `filter_skymodel` benchmarks, then optimize until the runtime gate passes. | Hebog through Rapthor's native task on one node with the executor Rapthor deploys there, and pinned `master` through Rapthor's PyBDSF subprocess on the same cores, in the same Linux container on the development machine, with cached reference timings. `scripts/benchmark/measure_filter_skymodel.py` measures a cell: a sector written from a real image at real resolution with WSClean-like component lists on its island pixels, one warm-up and five measured repetitions of each finder in fresh containers, alternating; the image is x86-64 under Rosetta, so the cluster's hardware confirms the figures (task 30). The first measurement (13 October, 3,000² window, thread path) gave 2.03 against the ≤0.50 gate, with the two finders using the same CPU time and Hebog keeping 1.1 of four cores busy. Done when the ratio and its upper one-sided 95% bound pass on every envelope cell the VM holds (decision 6), and memory and Hebog-curve non-regression and the quick science check pass. Native code enters only through the native-code gates and an accepted ADR. |

### Bounded growth and the 45,000-pixel tier

Each tier passes the same gate before its limit and release status change:
exact tiled-invariance tests, the quick science check, a quick benchmark
on both sides of any crossover, a reproduced `just traced-peak`, and the
task memory audit (`scripts/benchmark/audit_task_memory.py`) on the tier's
anchor. The memory measure is `tracemalloc`'s peak, which is deterministic
and is measured only by `just traced-peak`; peak RSS, which varies 42% with
machine load, is reported beside it as an envelope, never as the
threshold. Science on the large images uses the LoTSS-DR3 PyBDSF catalogue
and maps and the per-facet LOFAR-HD PyBDSF catalogues, with global
invariants, as in ADR-005.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 56 | Agent | Stop per-task and driver costs growing with the image. | The local-noise round builds every request before submitting any, each with its own subset of the pilot grid, about 1.9 of background/RMS's 3 bytes a pixel on synthetic grids; under Dask every task parses the completion marker of each generation it reads, 16 MB and 0.42 s at 15,402², which task 54's 32 extra island tasks paid. Done when the pilot grid is published once and read by window, or requests are built within the in-flight window; each generation's completion record is split by tile, so a task reads only its window's entries, rather than cached whole in each process, which would hold memory no task declares, about 0.7 GB a generation at 100,000² (decision of 15 October; task 25 reviews the store layout); `scripts/benchmark/attribute_traced_peak.py` confirms the background/RMS slope on the 10,000² anchor; and Serial and Dask products stay byte-identical. |
| 12 | Agent, human approves | Raise to 45,000² on the LOFAR-HD mosaic. | About 60 GB of disk is free. The tier gate passes and the raise is a release. This is the out-of-core demonstration: the run completes on 18 GiB with the traced peak bounded by tile size although one `float64` copy of the image (16 GB) would not fit. The local ladder ends here. |

### Scale beyond one machine

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 24 | Agent | Bound the graph for 100,000² at 10 and at 200 nodes without running the science. | Planner tests show at most 50,000 tasks, bounded reduction depth, bounded driver memory and a valid memory admission for both topologies, including the kept records that grow with the image and the sources found. |
| 25 | Agent | Qualify the Zarr store and the restart and recovery path locally. | Atomicity, owned-chunk writes from concurrent local workers, codec and chunk geometry, missing chunks and injected failures pass within an admitted memory budget. Zarr v3's sharding codec is evaluated against one file per chunk, since a run writes 19,373 chunk files at 10,000² and 45,587 on the mosaic and thousands of tasks on a cluster's shared filesystem mean many small files; the completion record's split by tile (task 56) is reviewed with it. Shared-storage throughput is measured by the cluster benchmark. |
| 27 | Agent packages, human approves the contract | Package the cluster benchmark and amend the scalability contract. | One command and a short guide run one Rapthor sector at its default size through Rapthor's native task, and Hebog standalone on the 90,000² LOFAR-HD mosaic, on a cluster the guide starts, at the node counts decision 4 fixes, recording evidence, the hardware and a scaling-model fit. `config/benchmarks/phase-0-scalability.json`, the performance and scalability contracts page and the `test-scalability` recipe describe the development-machine tier and that benchmark, keeping the 50, 100 and 200-node gates as design targets (task 26, folded in). A dry run with a local Dask cluster at small sizes passes, so the cluster session measures rather than debugs. |

### Science before the freeze

These are scientific improvements that wait until the work above is
complete (decision of 9 October); a confirmed incorrect supported output
reopens its item at once. All three close before the candidate is frozen.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 75 | Agent, human dispositions | Stop `continuum`'s local-noise refinement taking faint sources for noise. | `continuum` refines the local noise on 35-pixel windows everywhere, and a window that holds faint sources reads their emission as noise: on the ELAIS-N1 deep field it loses 1,346 of pinned `master`'s 5,762 islands (`compact` 257) with an RMS a median twice `master`'s there and 2.3 times the negative-pixel noise, and the islands it loses peak at a median 7.3 times that noise, so they are real; it also misses one of five injected sources on the quick check's varying-noise case. Task 68 measures the same windows' clipping bias. Done when a repair's effect on `just rapthor-agreement` with task 76's truth measures and on the quick check is measured, with `continuum` losing no more of `master`'s islands on the ELAIS-N1 cases than `compact` without losing injected sources; the maintainer has decided whether to apply it; and the Rapthor profile is decided again from agreement and truth (decision of 13 October). |
| 68 | Agent measures, human decides | Measure a truncation correction for the clipped window RMS. | The window statistic clips at 3σ around the median and takes the standard deviation of what remains, with no correction: 35-pixel windows read 1.6% low on white noise and 3.2 to 3.9% low on beam-correlated noise, and `empty-noise` publishes 0.959 of the injected noise, where PyBDSF applies the PySE correction, about 1.4% at κ = 3. Done when the correction's effect on the quick check, the equivalence lane and the position and flux uncertainty calibration is measured, and the maintainer has decided whether to apply it. |
| 15 | Agent, human dispositions | Decide how to handle a point-spread function that varies across the field. | LOFAR facets and MWA mosaics (which ship PSF maps) have a PSF the header beam cannot describe. Done when the effect on fluxes and sizes is measured with injected truth and the maintainer has either accepted a PSF map input or documented the limitation with its measured effect (decision 5). |

### Qualification and 1.0.0

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 28 | Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed; a later change restarts only the affected qualification tasks. The Rapthor, LSMTool and PyBDSF pins move forward here for the last time. |
| 29 | Agent designs, human approves | Run one powered parity/retention study with fresh held-out and public-survey data, sized to finish overnight on the development machine. | Every binding endpoint passes under a prospectively reviewed contract, population and power design, including the limitations that block 1.0.0, a per-noise-class check of the `Total_flux` rows and the LOFAR, SKA-Mid and SKA-Low families in the 1.0.0 definition, with the retained/rejected gate in the form decision 1 fixed. Closed failed campaigns are never reused as confirmation. |
| 30 | Human runs, agent analyses | Run the cluster benchmark once. | Strong scaling at the node counts decision 4 fixes, with invariant results and the task 23 runtime gate confirmed on cluster hardware for the envelope cells the development machine could not hold. A failure becomes a normal `0.x` repair task. |
| 31 | Agent | Check released PyBDSF 1.14.1 once. | One matched run against 1.14.1, cached for reuse, confirms Hebog ≤0.50 times the release on the deployment envelope and Rapthor-profile agreement against it. A failure is reported with its cause before the 1.0.0 decision. |
| 32 | Human runs in Rapthor, agent supports | Run the operational trial behind the Rapthor flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| 33 | Agent assembles, independent reviewers accept | Assemble the readiness packet and obtain acceptance. | The packet binds science, Rapthor profile, performance, scale, portability, a dependency and licence audit, packaging and current documentation to the frozen candidate, with separate radio-astronomy and engineering acceptance from the reviewers decision 8 names. |
| 34 | Human | Release 1.0.0. | Release Please produces 1.0.0 (for example through a `Release-As: 1.0.0` commit footer) and the package publishes to PyPI. Release notes state that 100,000² images and 100 to 200+ nodes are designed for but not demonstrated. |

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hebog's step stays slower than PyBDSF's: 2.03 times pinned `master`'s on the thread path, where both used about the same CPU time but Hebog kept 1.1 of four cores busy and PyBDSF 2.2. | Task 23 fails. | Task 78 screens the Dask path at production size before task 72; raise parallel occupancy before constant factors; use the native-code gates only for a profiled kernel; report the gap honestly at each milestone. |
| LSMTool's filtering of WSClean's component list is part of the step for either finder: 24 s of PyBDSF's 92 s on the 3,000² sector. | The ratio cannot fall below that share; if it reaches half of PyBDSF's step on production sectors, the ≤0.50 gate cannot pass. | Task 78 measures the share at production size; decision 6 restates the gate only then; LSMTool's filtering is Rapthor's to optimize. |
| Hebog's mask makes Rapthor keep different sky-model components from pinned `master`'s: 92.8% agreement at best, where released PyBDSF reaches 99.29%. | The science gate fails as written, and Rapthor's calibration model differs from PyBDSF's, most on deep LOFAR fields. | Task 76 measures each lane against truth, so a profile is not chosen for copying PyBDSF's errors; decision 1 fixes the gate's form; task 75 repairs `continuum`; `just rapthor-agreement` re-measures every lane at each pin move and science change. |
| One sector's speed-up is capped: a 20% serial share on the 10,000² anchor caps it near five; a worker needs about 2 GB a core for the multiscale tasks, so a node short of memory swaps before its cores are busy; rounds hold 7 to 25 tasks; Python's global lock throttles a process with many threads; concurrent sectors could deadlock workers that run one task each. | Rapthor's cluster cores go unused, and the gate is missed on occupancy rather than work. | Task 72's cost model sizes tiles and task counts from the core budget and the memory a core needs, with single-threaded tasks on several worker processes a node, resource annotations and seceding while waiting; the cluster benchmark reports where one sector stops scaling. |
| The passes keep records from every tile, growing the traced peak about 1.7 bytes a pixel in the multiscale pass and about 3 in background/RMS, and the analysis's own records grow with the sources found, about 42 KB each. | At those slopes the multiscale peak is about 2.1 GiB at 22,500² and 4.3 GiB at 45,000², and background/RMS about 6 GiB at 45,000²; the 45,000² run fits 18 GiB only while resident memory stays within about three times the traced peak; a dense sector's analysis (about 5.1 GiB for 123,186 sources) must be reserved by its Rapthor worker. | Task 56 before the 45,000² tier; shard, stream or drop kept records such as candidates that can never become islands; task 24's planner bounds include them; `hebog.analysis_memory_bytes` states the analysis's memory from an expected source count meanwhile. |
| An object wider than the read budget brings its own pixels to the driver in the island, deferred-fit and catalogue-row rounds, at up to 186 bytes a pixel: about 44 GB for a field-filling object at 15,402². No real LoTSS-DR3 object comes within a factor of ten of the budget. | Driver memory scales with the wide segments of a round, not the tile. | Deferred: associative partial sums on the cores first, then a reviewed design for the local-noise median; reopened when a tier's traced peak shows the term or when the cluster benchmark is planned. A connected network of narrow filaments is the diagnostic that would measure its growth. |
| Source association costs more than the image grows; a dense Rapthor sector (ELAIS-N1, 123,186 sources) took 8.5 h serially on 11 October. | A dense sector takes hours inside the envelope, and larger tiers longer. | Tasks 55 and 54 removed the quadratic hierarchy decision and the strip-shaped reads; the sector took 1.3 h on 15 October under a different profile, and task 78's like-for-like run attributes the gain. Profile the anchors again within task 23. |
| The development machine's 18 GiB RAM, free disk (30 GiB on 16 October) and 16 GB container VM limit local tiers and matched benchmarks. | Tiers above 22,500² stall, runs swap, or `master` cannot run on a production-size sector locally. | Tile-bounded memory once task 56 lands; about 60 GB free before 45,000²; the cluster measures what the VM cannot hold (decision 6). |
| Rapthor and LSMTool change frequently; both have moved since the 13 October pin, and PyBDSF's `master` is 91 commits past the binding reference. | Adapter, contract, benchmark or reference churn, or a backend that only works on a stale revision. | Move the Rapthor and LSMTool pins only before the patch is published (task 79), before the matched benchmarks (task 23) and at the freeze (task 28), re-running the contract audit, the acceptance scenarios and the agreement check and recording the outcome in the commit; keep PyBDSF at `c70103b` until the freeze. |
| The Rapthor patch depends on upstream acceptance, and the cluster benchmark on hardware not yet scheduled. | The native backend cannot be selected from released Rapthor until the patch merges; 1.0.0's cluster claims wait on a session. | The integration container installs the prepared patch at a recorded commit; Rapthor calls Hebog directly, so no LSMTool registry patch is required; decision 4 keeps the cluster session small, and the dry run (task 27) means it measures rather than debugs. |
| Extended association cannot be made exactly tile-invariant. | A tier stalls or changes science. | Test analytic shells and filaments crossing corners at each tier; escalate a scientific trade-off to the human rather than weakening invariance silently. |
| Large public images have minimal or non-standard headers, and no large public SKA-Low image exists. | Anchors cannot run unmodified, their science comparison is weak, or SKA-Low coverage relies on precursor data. | Headers checked against the input header contract before download; explicit request metadata; per-facet LOFAR-HD catalogues for science; GLEAM-X DR1 with its PSF maps for SKA-Low (decision 5), and SKA-Low science-verification data once released (expected from 2027). |
| Short checks miss a rare regression, or scientific campaigns absorb the schedule again. | A defect reaches a `0.x` release, or performance and scale slip. | Releases stay experimental and each escaped defect adds a fixed case; iteration budgets, cached references and endpoints limited to Rapthor-consumed fields hold the schedule; the one powered study at task 29 is the backstop. |

## Scientific gates

Analytic or injected truth is primary. Pinned PyBDSF `master` at `c70103b`
(`v1.14.1-40`, the Phase 5 reference) is the binding finder reference.
Released 1.14.1, which Rapthor installs today, is checked once at task 31.
The two diverge scientifically (14 versus 12 sources on the representative
3,000² image), so neither is truth. Later upstream `master` commits are
adopted only by a deliberate plan decision, which invalidates cached
reference outputs. Aegean comparisons are paused: neither binding nor run
routinely, and task 29's design decides whether to reinstate them.

- Each campaign uses its own prospectively reviewed endpoint registry and
  decision contract. Choose a whole incumbent before viewing results; never
  combine historical best values into a synthetic comparator.
- Require every applicable relative PyBDSF and incumbent Hebog comparison,
  with fixed practical margins and the conjunctive one-sided confidence
  rule. Inconclusive binding evidence is not parity. An old candidate's
  uncertainty exception does not transfer to a replacement.
- Freeze population, semantic applicability, independent sampling unit,
  margins, missing-output rules and endpoint and joint power before
  execution. Pair and resample whole realizations, not dependent source
  rows or pixels. Planning variance sizes the study; the observed-data
  interval decides. Superiority claims need a prospective multiplicity
  rule, and improvements cannot compensate for failed binding checks.
- Product validity, finite or explicitly unavailable measurements, complete
  processing status, schemas, provenance and deterministic execution remain
  binding. Report absolute targets separately. Retain all morphology,
  scale, SNR, noise and boundary strata.
- Compare like source, component and support semantics. Use original
  pixels for flux and photometry and valid pixels for mask precision,
  recall and IoU. Report splits, merges, duplicates and low-SNR
  completeness and reliability separately.
- Before a long campaign or replay, run a bounded development screen
  through the same runner and evaluator with an explicit time and resource
  budget, selecting cases before inspecting results. A clean screen is
  neither powered parity nor a prediction of campaign success.

The dataset matrix retains compact SNR 3–100, blends, diffuse Gaussians,
filaments and shells, mixed emission, different beams, WCS, pixel scales
and units, negative backgrounds, empty, all-NaN and invalid data, varying
noise, image edges and all tile-edge and corner topologies. Every dataset
has a development, regression or qualification role, provenance, checksums
and generator identity
([dataset manifests](../docs/reference/dataset-manifests.md)), and new
populations are seed-disjoint from existing manifests. General
qualification includes full public or challenge images from LOFAR, SKA-Mid
and SKA-Low (precursor data until SKA-Low data are public), plus at least
one other instrument. Compare Serial before alternate executors and
external finders.

| Measurement | Target |
| --- | --- |
| Rapthor retained/rejected components | ≥99.5% agreement, in the form decision 1 fixes |
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
parity on the M1 calibration population and Rapthor's 10% photometry
decision floor; strata are that population's SNR 10, 20 and 50 classes,
binding pooled over white and beam-correlated noise (decision of
6 October), with the powered study adding a per-noise-class check. They
pass on independent realizations (`config/datasets/m1-flux-calibration.json`).
The retained/rejected row is measured by `just rapthor-agreement` over
every distinct pixel holding a Gaussian centre fitted by `master` or any
Hebog lane, overall and in the bright, extended, edge, masked, crowded,
sparse, true-sky and apparent strata.

## Performance and scale gates

For supported Rapthor deployment, matched complete-step median ratios and
their upper one-sided 95% bootstrap confidence bounds must satisfy:

```text
Hebog / pinned PyBDSF master (c70103b) <= 0.50
```

Pinned `master` was faster than released 1.14.1 in every matched Phase 0
run (3.0% at 256², 6.8% at 3,000²), so on those anchors this gate is at
least as strict as the former release gate; task 31 confirms the release
ratio once. Scientific eligibility precedes performance acceptance. These
are minimum deployment gates, not a reason to stop optimizing or to hold an
experimental standalone release.

- Maintain the anchors and workloads of the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md),
  with the real images below beside the nearest anchor and both sides of
  every measured crossover. Gate early deployment on its frozen envelope;
  1.0 qualification needs the matrix up to the 90,000² LOFAR-HD mosaic,
  with 100,000² covered by planner tests only.
- Compute reference-finder timings once per input, revision and host and
  reuse them; rerun them only when one of those changes.
- Match environments and record evidence as
  [`AGENTS.md`](../AGENTS.md#scientific-and-performance-gates) and the
  [evidence records](../docs/reference/evidence-documents.md) require: one
  warm-up and at least five measured repetitions with every value retained,
  and unavailable instrumentation recorded with a reason, never zero.
- Hebog non-regression needs an upper one-sided 95% bound ≤1.05 against the
  previous reviewed curve; a lower bound >1.05 is a regression and crossing
  the margin is inconclusive. A >10% peak worker or aggregate memory
  regression against either PyBDSF reference needs an approved throughput
  trade-off.
- Component budgets remain diagnostic; complete filtering decides
  deployment.

### Reference images

The real images the repository uses or plans to use, with the windows its
checks cut from them. The
[input header contract](../docs/reference/input-header-contract.md) says
how each is read; check other headers before a large download. No image
data or dataset belongs in Git; the checked-in configuration names each
source and window.

| Family | Image | Size | Use | Reference |
| --- | --- | --- | --- | --- |
| LOFAR | LOFAR-HD ELAIS-N1 mosaic, 0.4/0.2/0.1″ pixels | 22,500², 45,000², 90,000² (2.0, 8.1, 32.4 GB); 2-D `float32`, `JY/BEAM`, SIN, beam present, no frame or reference-frequency keywords | Largest real scale anchor; same-field size ladder | Per-facet PyBDSF catalogues; facets are WSClean FK5 J2000 images |
| LOFAR | LoTSS-DR3 HEALPix mosaics (1,571) | 14,390–17,752² (1312: 15,402², ICRS, `RESTFRQ`, beam present, 1.5″ pixels, 9″ beam) | Science and throughput. Quick check and quick benchmark: 1,024² windows of mosaic 1312 at x 9,749, y 9,749 (sparse) and x 7,701, y 6,677 (dense). Quick benchmark and traced peak: 3,000² at x 6,713, y 5,689; 3,600² at x 6,413, y 5,389; 10,000² at x 2,000, y 4,500, the 10,000 tier's anchor; and the whole mosaic, `lotss-dr3-1312-15402`, the 15,402 tier's anchor and task 78's screening case | Per-mosaic PyBDSF `srl` and `gaul` catalogues (mosaic 1312: 22,420 sources, 28,559 Gaussians) plus RMS, residual and mask maps |
| LOFAR | LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky pair | 14,175² each (804 MB); DDFacet, four axes, ICRS, `RESTFRQ`, 6″ beam | Closest public match to Rapthor's two inputs; the dense deep-field sector of tasks 54 and 78 | PyBDSF catalogue and maps |
| LOFAR | LoTSS-DR2 cut-outs: a 22′ survey field at 12h +45°, 3C 295 (12′), M51 (20′) and a 90′ field at 13h +47° | 1.5″ pixels: about 880², 480², 800² and 3,600² | Notebook comparison whole-image cases (`lotss-dr2-*`); the 22′ field is the public API's example input | LoTSS-DR2 PyBDSF catalogue |
| SKA-Mid | SDC1 B1/B2/B5, 8/100/1,000 h (Zenodo 4328029; INAF mirror) | 32,768² (4.3 GB each); 4-D, `JY/BEAM`, `EPOCH = 2000`, `BMAJ`/`BMIN` but no `BPA`, supplied as 0° | Science checks with truth. B2 1,000 h cut-outs: 1,024² at x 20,992, y 12,800 (sparse) and x 16,896, y 16,896 (crowded), and 2,048² at x 16,384, y 16,384 (crowded), in the quick check, benchmark and traced peak; the notebook comparison's 2,048² tiles | Full truth catalogue (`True_1400_v2.txt`), the B2 primary beam and the official submissions |
| SKA-Mid | MeerKAT MIGHTEE DR1 COSMOS and XMM-LSS; SMGPS tiles | MIGHTEE 7,486² and 14,800² (448 MB and 1.75 GB), two axes with declared `FREQ` and `STOKES`, FK5 J2000; SMGPS 7,500² with 16 Obit `SPECLNMF` planes in Galactic coordinates, refused as a cube | Real precursor science; header variety; MIGHTEE is inside the envelope for task 29 | PyBDSF (MIGHTEE); Aegean (SMGPS, diagnostic only) |
| SKA-Low | MWA GLEAM-X DR1 mosaics | 170–231 MHz: 31,468 × 11,151 (2.8 GB), `ZEA`, FK5 J2000 by `EPOCH`, frequency only in a non-standard `FREQ` keyword; PSF maps 360 × 180 × 4 on a 1° grid | Precursor science with a PSF that varies across the field (task 15, decision 5); needs the 45,000² tier for its long side | PSF maps; Aegean catalogue (diagnostic only) |
| Other | ASKAP EMU-PS1 (CASDA login); ASKAP EMU pilot 2° × 2° field, deep and shallow (Hydra paper, CIRADA at CADC) | 44,911 × 33,569; 3,600² each (52 and 104 MB) | Optional non-SKA-family image; notebook comparison cases `hydra-deep` and `hydra-shallow` | Selavy catalogue; the Hydra archive's finder catalogues, diagnostic only |
| Rapthor | Representative sector image, `rapthor-representative-3000` (restricted, local only) | 3,000² | Phase 0 matched PyBDSF runs, where released 1.14.1 and pinned `master` found 12 and 14 sources; not redistributable | Pinned `master` and 1.14.1 products and timings under `config/baselines/` |

Generated inputs are not reference images: the quick check's generated
datasets and the 10,000² `wide-objects-10000` diagnostic come from
`config/datasets/quick-science-check.json` and are rebuilt from their
recipes.

## Architecture and documentation boundaries

The [architecture](../docs/architecture/index.md), the
[distributed execution contract](../docs/architecture/distributed-execution.md),
the [native-code assessment](../docs/explanation/native-code-assessment.md)
and [`AGENTS.md`](../AGENTS.md) hold the requirements: a pipeline-neutral
scientific library with inert imports and small typed requests and results;
one tile-native composition for every image size with Serial as the oracle,
Zarr as the sole intermediate backend, stage-specific halos, global
ownership and hierarchical reductions; never a complete large plane on one
worker; dtype preserved unless scientific evidence supports a change.

Keep the README, docs home, release status, progress page and tutorial
focused on current behaviour, replacing stale summaries when status
changes; the progress page and the current-state table above change
together. Record completed work in Git history with exact evidence
references, not as another "latest" section in user guidance. Removing a
historical narrative never changes a closed result.
