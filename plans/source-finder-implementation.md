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

| Item | Position on 18 October 2026 |
| --- | --- |
| Release | v0.22.0 (17 October), the first release on PyPI, carries the Rapthor integration (tasks 16, 20, 21, 23 and 77) and one sector's speed (tasks 73, 74, 71, 55 and 54); it passed its release check on 15 October. Every release is experimental and scientifically unqualified. |
| Candidate | Public composition v23. The quick check's catalogue, RMS and mask are byte-identical to v0.19.0's; only the composition hash has moved. Development-unqualified. |
| Functionality | The standalone finder is complete under Serial, Thread and caller-owned Dask executors within the 15,402² envelope. The Rapthor adapter is complete, and [Rapthor's Hebog branch](../scripts/validation/rapthor-integration/README.md) runs it on Rapthor's interim one-single-threaded-worker-per-node layout with a thread executor, memory admission, PyBDSF fallback and dual runs. With 0.22.0 on PyPI the branch is ready to push (task 79). |
| Performance | The deployment gate binds the source-finding part of Rapthor's step (decision of 16 October): at most 0.50 of pinned `master`'s on dense sectors, provisionally those where `master` finds at least 10,000 sources, and no slower than `master` on the rest (decision of 18 October). No dense sector has been measured, and both sparse cells fail parity. On the 3,000² sector Hebog's finder part is 2.43 times `master`'s on the thread path and 1.99 on four Dask workers (one repetition), with both finders using about the same CPU; on the 10,000² anchor, where `master` finds 9,276 sources, it is 1.23 on four Dask workers (the screening of 16 October, one repetition), both finders keeping about three of four cores busy and Hebog using 11% more CPU. The ratio falls as the source count rises. PyBDSF's subprocess could not run the 15,402² mosaic in the 16 GB container VM. One sector on four local Dask workers takes 0.36 of one worker's time on the anchor with a 20% serial share; threads in one process barely scale, and four Dask workers gain nothing on a 3,000² sector of four tiles. Like for like, the whole ELAIS-N1 sector now takes 4.2 times less time than at 0.19.0, and the `compact` default 1.6 times less again. |
| Science | Rapthor keeps or rejects alike with Hebog's `compact`/zero mask and pinned `master`'s for 92.8% of sky-model components; the 99.5% target, which released PyBDSF also misses (99.29%), is retired for a truth-based gate (decision of 16 October). Its limits were set on 17 October, and the agreement check applies them. `continuum` passes them under either background since its local noise no longer degenerates in crowded fields (17 October); `compact` with a zero background fails them on extended sources, at image edges and narrowly on false islands. Rapthor runs `continuum` with a zero background, chosen from the gate. |
| Blockers | Every task under [Path to 1.0.0](#path-to-100). Largest risks: the performance gap on dense sectors, not yet measured, and on sparse ones, where Hebog is slower; memory that grows with the image and the sources found; the development machine's limits; upstream churn; and the three steps outside the agent's control: cluster time, Rapthor's worker layout and independent reviewers. |
| Next action | Agent: raise the 22,500² tier (task 11), then start task 72 by measuring both finders against the source count and cores in the matched container. Human: push Rapthor's Hebog branch (task 79), file the Astropy report drafted on 5 October (`benchmark-results/upstream/astropy-wcs-d-exponent.md`) and take the [decisions below](#decisions-pending). |
| Deferred | Scientific improvements that are not confirmed incorrect supported outputs wait until the integration and scaling work is complete (decision of 9 October); task 15 sits before the freeze, and the rest is here. Meshes scaled with the restoring beam, which would admit beams wider than 10 pixels (task 62's measurement: every SNR ≥ 10 source recovered to 22 pixels at about 2.5 times the local-noise read); every real Rapthor image is at most about 7 pixels. Wide-object reductions on the cores instead of the driver, reopened when a tier's traced peak shows the term or when the cluster benchmark is planned. Aegean, ProFound and SoFiA comparisons. PyBDSF's second grouping rule, which Rapthor's island grouping does not need. Native code without a passing profile gate. A confirmed incorrect supported output reopens its item at once. |

## Definition of 1.0.0

Version 1.0.0 is the first release demonstrated to be a backend Rapthor can
switch to: proven at Rapthor's sector sizes, faster than PyBDSF's source
finding and scaling across nodes, with the Rapthor-consumed science
qualified (decision of 16 October 2026). Every claim is bound to reviewed
evidence for that exact candidate:

- **Telescopes.** The standalone finder accepts standard FITS continuum
  images from any radio telescope that meet the documented
  [input header contract](../docs/reference/input-header-contract.md), and
  accepts their imager conventions (WSClean, CASA and SKA SDP products) or
  rejects them with a specific error. It is validated on LOFAR and SKA-Mid
  images for 1.0.0, and on SKA-Low precursor data at the minor release
  whose envelope admits them.
- **Functionality.** Hebog is a supported, feature-flagged backend for
  Rapthor's `filter_skymodel`, selected through Rapthor's `source_finder`,
  at a pinned Rapthor and LSMTool revision: true-sky and flat-noise
  branches, the Rapthor profile, native catalogue, mask, RMS and
  source-count products, empty and blanked-image paths, retry and restart,
  and PyBDSF fallback. The standalone public API remains usable without
  Rapthor, Prefect, LSMTool or Dask.
- **Science.** The Rapthor profile passes the truth-based retained/rejected
  component gate of the [scientific gates](#scientific-gates), and the
  frozen candidate passes
  prospective, powered, held-out parity/retention against pinned PyBDSF
  `master` (`c70103b`) on full LOFAR images inside the envelope, SDC1
  simulations with truth and a MeerKAT MIGHTEE image; a single check
  against released PyBDSF 1.14.1 confirms Rapthor-profile agreement for
  users of the release.
- **Performance.** The source-finding part of Rapthor's `filter_skymodel`
  step, from the task's start to LSMTool's `filter_sources` call, takes at
  most 0.50 of pinned `master`'s on dense sectors, where PyBDSF's source
  finding is slow, and no longer than `master`'s on the rest, under the
  confidence rules of the [performance gates](#performance-and-scale-gates),
  for sectors up to the envelope: like for like on one node, and on dense
  sectors also across the nodes Rapthor deploys against PyBDSF's one node.
  How each finder's time grows with the source count and with cores, and
  the complete step, are reported beside it. The gate is measured on the
  cluster; the development machine shows the trend in sources, cores and
  the CPU ratio.
- **Scalability.** The envelope is the 22,500² tier, which covers Rapthor's
  default sectors. One sector's finder part keeps falling from 1 to 10
  nodes with invariant products and the efficiency floor task 27 fixes;
  results do not change with worker count, tile geometry, completion order
  or retry; planner tests bound graph size and reduction depth for 100,000²
  images on 100 to 200+ nodes. Release notes say that 100,000² images and
  that node count are designed for but not demonstrated.
- **Release.** Published on PyPI with portability, security, licensing,
  current documentation and independent radio-astronomy and engineering
  acceptance, under the 1.x compatibility policy in the
  [delivery policy](#delivery-policy).

Each later envelope raise is a minor release under that policy: 45,000²
on the development machine, the out-of-core demonstration, and 90,000² on
the cluster, with SKA-Low precursor evidence and a PSF-map input as the
work that fits them ([after 1.0.0](#after-100)). Rapthor's default cutover
is a separate Rapthor decision taken after an operational soak of the
1.0.0 backend; the PyBDSF fallback remains until then.

## Decisions pending

Each decision names the maintainer's call and the agent's recommendation.
A decision taken here is recorded in the affected row and in the commit,
never in `LOG.md`. Decided on 18 October: the performance gate binds
dense sectors, provisionally those where pinned `master` finds at least
10,000 sources, at 0.50 of `master`'s finder part, and the rest at no
slower than `master` (an upper bound of 1.05), with each finder's growth
against the source count and cores reported beside them, not gated;
reducing serial work is part of task 72 where it gives clear gains; no
change may degrade the science (see the [scientific gates](#scientific-gates));
the window RMS keeps no truncation correction, since correcting it lowered
completeness on every truth measure without a measurable gain in
reliability, and the scatter of its windows is a [risk](#risks).
Decided on 17 October: the Rapthor and LSMTool pins
move to their heads before the Rapthor change is pushed, done the same day;
the change lives on a branch of Rapthor's repository, not as a patch in
Hebog, and testing, trials and benchmarks use the branch without waiting
for it to merge; Rapthor runs `continuum` with a zero background, which
passes the truth-based gate where `compact` fails it, rather than the
interim `compact`; the truth-based gate's limits are those the
[scientific gates](#scientific-gates) record, which `just
rapthor-agreement` applies to every lane and the released control.
Decided on 16 October and recorded in the rows: the 1.0.0 scope above; the
gate's finder-part form and its measurement on the cluster; the retirement
of the 99.5% agreement target; task 11 before task 56, whose
completion-record split joins task 72 and whose local-noise term waits for
the 45,000 tier; task 72 as four releases; the cluster benchmark as one
sector at 1, 2, 5 and 10 nodes; task 15 as measurement and documentation,
with a PSF-map input after 1.0.0.

1. **Independent acceptance (task 33).** Reviewers have not been named.
   *Recommendation:* approach the radio-astronomy and engineering reviewers
   when the Rapthor branch is pushed, so their review runs beside Rapthor's.
2. **The scaling floor.** "Scales well across nodes" needs a number before
   the cluster session. *Recommendation:* task 27 proposes a strong-scaling
   efficiency floor at 10 nodes from the local curve and the contract's
   per-topology floors, and the maintainer approves it with the contract
   amendment.
3. **The dense-sector threshold.** Provisionally 10,000 sources in pinned
   `master`'s catalogue. *Recommendation:* task 72's first step measures
   both finders against the source count, and the maintainer confirms or
   moves the threshold from that curve before the cluster benchmark is
   packaged (task 27).

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
  RAM; a 16 GB, six-core Podman VM for the containers, which cannot hold
  pinned `master` on a 15,402² sector). A cluster of up to 10 nodes runs
  one benchmark for 1.0.0 and never blocks development; record its
  hardware when that benchmark is scheduled.
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
- **Pins.** Rapthor `main` at `aff26023` (the Prefect/Dask line since the
  9 October 2026 merge; `master` is the CWL/Toil release line and not a
  target), LSMTool `master` at `156ae6a` (v1.9.0 plus 27 commits) and
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
  [the envelope](#the-deployment-envelope-and-gate) on a new tier's
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

Versioning after 1.0.0 (decision of 16 October 2026): the public API, the
Rapthor adapter contract and the product schemas are stable within 1.x,
and a change to them is a 2.0; an envelope raise is a minor release; a
science change ships as a minor release with a new composition version and
release notes that say what moved, never silently; patch releases change
no product.

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
number is not reused (numbers up to 80 have been used). The sections, and
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

The order, set on 9 October 2026 and amended through 18 October:

1. **Push Rapthor's Hebog branch** (task 79), so Rapthor's CI runs on it
   and trials install Rapthor from it, with Hebog from PyPI. The
   integration waits on no tier: its inputs are inside the 15,402²
   envelope, and Rapthor's 3,000² demonstration sector is refused for its
   30-pixel synthetic beam, not its size.
2. **The 22,500² tier** (task 11). Rapthor's profile came first: the
   truth-based gate showed on 17 October that `compact` trims bright
   emission and `continuum` lost faint sources, so `continuum`'s local
   noise was repaired and Rapthor now runs it, before task 72 measures and
   models one sector's cost, scientific accuracy taking the time it needs
   (decision of 17 October).
3. **One sector across the cluster** (task 72), on the profile chosen.
   The screening of 16 October found a finder-part ratio of 1.23 on four
   Dask workers at the 10,000² anchor. Rapthor usually images one
   sector, 17,000 to 20,000 pixels a side, on nodes of up to 192 cores;
   its interim thread path cannot use a node's cores, so the distributed
   path comes before everything else (decisions of 15 and 16 October).
   It starts by measuring where PyBDSF is slow: both finders against the
   source count and cores (decision of 18 October).
4. **The deployment envelope and gate** (tasks 22 and 23), with the store,
   planner and cluster benchmark packaging (tasks 24, 25 and 27).
5. **Science before the freeze** (task 15), deferred until the work above
   is complete unless an output is confirmed incorrect.
6. **Qualification and 1.0.0** (tasks 28 to 34).

### Release and publication

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 79 | Human pushes, agent prepares | Push Rapthor's Hebog branch. | The pins moved to Rapthor `aff26023` and LSMTool `156ae6a` on 17 October, with the change rebased, the integration container rebuilt and its summary re-recorded; they move again before the push only if upstream changes the filter step. The branch's `rapthor[hebog]` extra accepts any `0.x` release from 0.22 (`hebog>=0.22,<1`), because Hebog's feature releases also bump the minor version (decision of 17 October); a breaking change to the adapter therefore needs a matching change on the branch. Done when the tested commit is on a branch of Rapthor's repository and Rapthor's CI passes on it. The trial (task 32) and the cluster benchmark (task 27) use the branch; the merge request, with the dual-run mode and the PyBDSF fallback described, follows when the maintainer chooses. |

### The next tier

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 11 | Human frees disk, agent raises | Raise to 22,500² on the LOFAR-HD ELAIS-N1 mosaic, the 1.0.0 envelope. | About 12 GB of disk is free and the mosaic's restoring beam is read and recorded first: its name suggests about 3 pixels a beam, where the support pass's opening used to remove most 5 to 6σ compact sources (`LOG.md`, 4 October). The tier gate passes, recording the diagnostics' bright candidate count and largest bright-region read, and the raise is a release. Runs unattended beside task 72 (decision of 16 October). |

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
25 tasks. In the screening of 16 October both finders used about three of
four cores at 10,000², where `master` finds 9,276 sources, just under the
dense threshold; the gate binds where PyBDSF's time grows with the source
count, and Hebog's must grow more slowly there and spread across more
cores.

Task 72 starts by measuring both finders against the source count and
against cores in the matched container, under Rapthor's step: sectors of
one size with rising source counts, and the dense ELAIS-N1 central 5,000²
(about 34,000 sources) on 1, 2, 4 and 6 cores, with Hebog's finder part
profiled stage by stage (decisions of 17 and 18 October). A fitted model of
each finder's serial and parallel work projects the ratio on dense and
sparse sectors at the cluster's node sizes, sets targets for Hebog's serial
term, per-source cost and CPU, and orders the work below; the
[execution plan](2026-10-18-one-sector-across-the-cluster.md) holds the
steps. It then lands as four increments, each merged and released in turn
(decision of 16 October):

- **Core budget and cost model.** The caller states the cores Hebog may
  use, defaulting to the client's capacity, since a client's capacity
  counts threads that DP3 or another analysis holds. Each stage chooses its
  tile core from its halo and its task count from batching by a stated
  cost model fitted to that profile, the scaling profiles of 15 October
  and the screening, holding the memory a worker needs per core as well as
  its tiling, so parallelism rises without small cores multiplying halo
  overhead, and a sector of a few 2,048-pixel tiles still occupies the
  workers it is given. The memory each
  task declares follows the chosen core; the composition's run settings
  (executor, work directory, generation, tile core) become one record; the
  run's timing record states the tiling and budget chosen; a small image
  stays one tile with no scheduler overhead (use case 3). Products depend
  on none of it.
- **Waiting and sharing.** An analysis started inside a worker task secedes
  while it waits on its tile tasks. Once tasks are packed by declared
  memory, each round's declaration is re-audited against its measured peak
  (`scripts/benchmark/audit_task_memory.py`; background's grouped pilot
  declares about five times its peak). Each generation's completion record
  is split by tile, so a task reads only its window's entries rather than
  parsing the whole record (16 MB and 0.42 s a task at 15,402², which
  thousands of tasks on ten nodes would each pay), without a process-wide
  cache that holds memory no task declares (decision of 15 October). A
  local multi-worker cluster runs one analysis, several concurrent
  analyses and workers joining between analyses without deadlock or changed
  products.
- **Rapthor's distributed path.** The branch passes its client and resource
  names (`memory_resource`, `core_resource`) to `DaskExecutor`, reserves
  the analysis memory on the driving task and retires its interim thread
  path. Hebog's adapter takes over the image's source-count estimate and
  the analysis reservation, so Rapthor supplies only the memory budget
  (decision of 17 October). What Hebog needs from a cluster is documented for any caller
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md)),
  with one way Rapthor can provide it beside DP3 and WSClean.
- **Both branches together.** The true-sky analysis and the flat-noise
  estimate submit their tile tasks through the executor at once, not
  through a thread of Hebog's own, so the serial reference stays
  single-threaded.

Each increment also cuts the serial work it touches where a measured gain
is clear (decision of 18 October): the candidate scan's one task per
128-pixel cell and each task's reopening of the FITS file (the cost model);
results awaited in submission order, the completion record each task
parses whole, and the driver's re-read and hash of every chunk it
publishes, which the writing tasks can report instead (waiting and
sharing); and the flat-noise estimate, which starts only after the whole
true-sky analysis (both branches together).

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 72 | Agent | Make Hebog's tasks scale on any Dask cluster, Rapthor's included. | Both finders' curves against the source count and cores are recorded with the model's projections for dense and sparse sectors, and the four increments above have merged and released. Products are byte-identical across the thread and Dask paths in the executor contract suite; task 73's curve, re-measured with the cost model's tiling, falls further than the baseline above; and the Dask path's CPU overhead on the 3,000² and 10,000² sectors (371 s against 206 s on threads, and 11% over `master`) and the dense cell's ratio are measured again. |

### The deployment envelope and gate

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
| 22 | Agent proposes, human freezes | Freeze the deployment envelope. | Sizes and workloads match Rapthor's production sectors (17,000 to 20,000 pixels a side; the demonstration sector is 3,000² and refused for its beam), and the 22,500² tier is admitted (task 11). An image above the envelope is refused with a typed error and Rapthor falls back to PyBDSF. |
| 23 | Agent | Run matched `filter_skymodel` benchmarks and optimize the finder part towards the gate. | Hebog through Rapthor's native task, and pinned `master` through Rapthor's PyBDSF subprocess on the same cores, in the same Linux container on the development machine, with cached reference timings. `scripts/benchmark/measure_filter_skymodel.py` measures a cell: a sector written from a real image at real resolution with WSClean-like component lists on its island pixels, one warm-up and five measured repetitions of each finder in fresh containers, alternating; the gate's ratio is the finder part's and the complete step's is reported beside it; the image is x86-64 under Rosetta. On the sparse 3,000² sector both finders burn the same CPU, so parity on four cores needs Hebog to keep as many cores busy as `master`; the VM cannot hold `master` on a 15,402² sector, so the ELAIS-N1 central 5,000² is the dense cell it should hold. Done when, on every cell the VM holds, dense and sparse, the finder part's CPU ratio and its wall ratio against cores are measured and recorded, the largest constant factors the profile names are cut, and memory and Hebog-curve non-regression and the quick science check pass; the gate itself is decided by the cluster run (task 30). Native code enters only through the native-code gates and an accepted ADR. |

### Scale beyond one machine

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 24 | Agent | Bound the graph for 100,000² at 10 and at 200 nodes without running the science. | Planner tests show at most 50,000 tasks, bounded reduction depth, bounded driver memory and a valid memory admission for both topologies, including the kept records that grow with the image and the sources found. |
| 25 | Agent | Qualify the Zarr store and the restart and recovery path locally. | Atomicity, owned-chunk writes from concurrent local workers, codec and chunk geometry, missing chunks and injected failures pass within an admitted memory budget. Zarr v3's sharding codec is evaluated against one file per chunk, since a run writes 19,373 chunk files at 10,000² and thousands of tasks on a cluster's shared filesystem mean many small files; the completion record's split by tile (task 72) is reviewed with it. Shared-storage throughput is measured by the cluster benchmark. |
| 27 | Agent packages, human approves the contract | Package the cluster benchmark and amend the scalability contract. | One command and a short guide run one dense Rapthor sector at its default size at 1, 2, 5 and 10 nodes, and a sparse one on one node: through Rapthor's native task on the layout its Hebog branch documents, and standalone on the same cluster, which is the scaling evidence if Rapthor has not yet given each node several task slots. They record evidence, the hardware, a scaling-model fit, the finder-part ratio against PyBDSF on one node and the strong-scaling efficiency against the floor decision 2 fixes. `config/benchmarks/phase-0-scalability.json`, the performance and scalability contracts page and the `test-scalability` recipe describe the development-machine tier and that benchmark, keeping the 50, 100 and 200-node gates as design targets (task 26, folded in). A dry run with a local Dask cluster at small sizes passes, so the cluster session measures rather than debugs. |

### Science before the freeze

This scientific measurement waits until the work above is complete
(decision of 9 October); a confirmed incorrect supported output reopens it
at once. It closes before the candidate is frozen.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 15 | Agent measures, human dispositions | Measure and document a point-spread function that varies across the field. | LOFAR facets and MWA mosaics (which ship PSF maps) have a PSF the header beam cannot describe. Done when the effect on fluxes and sizes is measured with injected truth and documented as a limitation with its measured effect; a PSF-map input is work after 1.0.0 unless the effect changes a Rapthor-consumed field (decision of 16 October). |

### Qualification and 1.0.0

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 28 | Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed; a later change restarts only the affected qualification tasks. The Rapthor, LSMTool and PyBDSF pins move forward here for the last time. |
| 29 | Agent designs, human approves | Run one powered parity/retention study with fresh held-out and public-survey data, sized to finish overnight on the development machine. | Every binding endpoint passes under a prospectively reviewed contract, population and power design, including the limitations that block 1.0.0, a per-noise-class check of the `Total_flux` rows, the truth-based retained/rejected gate at its approved limits, and full LOFAR images inside the envelope, SDC1 simulations with truth and a MeerKAT MIGHTEE image. Closed failed campaigns are never reused as confirmation. |
| 30 | Human runs, agent analyses | Run the cluster benchmark once: the gate's measurement. | One sector's finder part at 1, 2, 5 and 10 nodes keeps falling to the floor decision 2 fixed, with invariant products; its ratio against PyBDSF's finder part on one node passes the gate like for like at one node and in Rapthor's deployed configuration, under the confidence rule, for the envelope's sizes. A failure becomes a normal `0.x` repair task. |
| 31 | Agent | Check released PyBDSF 1.14.1 once. | One matched run against 1.14.1, cached for reuse, confirms the performance gate against the release on a dense and a sparse sector inside the deployment envelope, and Rapthor-profile agreement against it. A failure is reported with its cause before the 1.0.0 decision. |
| 32 | Human runs in Rapthor, agent supports | Run the operational trial behind the Rapthor flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| 33 | Agent assembles, independent reviewers accept | Assemble the readiness packet and obtain acceptance. | The packet binds science, Rapthor profile, performance, scale, portability, a dependency and licence audit, packaging and current documentation to the frozen candidate, with separate radio-astronomy and engineering acceptance from the reviewers decision 1 names. |
| 34 | Human | Release 1.0.0. | Release Please produces 1.0.0 (for example through a `Release-As: 1.0.0` commit footer) and the package publishes to PyPI. Release notes state the envelope, the 1.x compatibility policy, and that 100,000² images and 100 to 200+ nodes are designed for but not demonstrated. |

### After 1.0.0

Each envelope raise is a minor release through the same tier gate; the
rows wait until 1.0.0 ships unless a 1.0.0 task needs them.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 56 | Agent | Stop the local-noise requests growing with the image. | The local-noise round builds every request before submitting any, each with its own subset of the pilot grid, about 1.9 of background/RMS's 3 bytes a pixel on synthetic grids. Done when the pilot grid is published once and read by window, or requests are built within the in-flight window; `scripts/benchmark/attribute_traced_peak.py` confirms the background/RMS slope on the 10,000² anchor; and Serial and Dask products stay byte-identical. Needed before the 45,000² tier, whose forecast background/RMS peak is about 6 GiB. |
| 12 | Agent, human approves | Raise to 45,000² on the LOFAR-HD mosaic (1.1). | About 60 GB of disk is free. The tier gate passes and the raise is a minor release. This is the out-of-core demonstration: the run completes on 18 GiB with the traced peak bounded by tile size although one `float64` copy of the image (16 GB) would not fit. The local ladder ends here. GLEAM-X's 31,468-pixel side fits this tier, so SKA-Low precursor evidence joins it. |
| 80 | Human runs, agent analyses | Raise to 90,000² on the cluster (1.2). | The 90,000² LOFAR-HD mosaic runs standalone on the cluster at two node counts within the amended gates, with invariant products, and the raise is a minor release. |

A PSF-map input (task 15's measured limitation) and the deferred science
in the current-state table join these releases as evidence and demand
allow.

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hebog's finder part is slower than PyBDSF's on sparse sectors, 2.43 times pinned `master`'s on the thread path at 3,000² and 1.23 on four Dask workers at 10,000², where both finders burn about the same CPU, and has not been measured on a dense sector, where the 0.50 gate binds. | Task 30 fails on dense sectors, or passes only at node counts Rapthor does not deploy; sparse sectors stay slower than `master`. | Task 72 first measures both finders against the source count and cores and models the ratio at the cluster's node sizes, then raises occupancy and cuts serial work and the Dask path's CPU overhead; task 23 cuts the largest constant factors, including the per-pixel cost that decides sparse sectors; use the native-code gates only for a profiled kernel; report the gap honestly at each milestone. |
| Hebog's mask makes Rapthor keep different sky-model components from pinned `master`'s: 92.8% agreement at best, where released PyBDSF reaches 99.29%. | Rapthor's calibration model differs from PyBDSF's, most on deep LOFAR fields, and the truth-based gate fails where Hebog loses real sources. | `just rapthor-agreement` measures each lane against truth, so a profile is not chosen for copying PyBDSF's errors, and re-measures every lane at each pin move and science change. |
| One sector's speed-up is capped: a 20% serial share on the 10,000² anchor caps it near five; a worker needs about 2 GB a core for the multiscale tasks, so a node short of memory swaps before its cores are busy; rounds hold 7 to 25 tasks and a 3,000² sector only four tiles; Python's global lock throttles a process with many threads; concurrent sectors could deadlock workers that run one task each. | Rapthor's cluster cores go unused, and the gate is missed on occupancy rather than work. | Task 72's cost model sizes tiles and task counts from the core budget and the memory a core needs, with single-threaded tasks on several worker processes a node, resource annotations and seceding while waiting; the cluster benchmark reports where one sector stops scaling. |
| Scaling across nodes inside Rapthor needs Rapthor to give each node several task slots, which is Rapthor's change to make. | The Rapthor run of the cluster benchmark uses one core a node. | The Rapthor branch documents the layout; the standalone run on the same cluster is the scaling evidence meanwhile (task 27). |
| The passes keep records from every tile, growing the traced peak about 1.7 bytes a pixel in the multiscale pass and about 3 in background/RMS, and the analysis's own records grow with the sources found, about 42 KB each. | At those slopes the multiscale peak is about 2.1 GiB at 22,500², within the envelope's budget, and 4.3 GiB at 45,000² with background/RMS about 6 GiB; a dense sector's analysis (about 5.1 GiB for 123,186 sources) must be reserved by its Rapthor worker. | Task 56 before the 45,000² tier; shard, stream or drop kept records such as candidates that can never become islands; task 24's planner bounds include them; `hebog.analysis_memory_bytes` states the analysis's memory from an expected source count meanwhile. |
| An object wider than the read budget brings its own pixels to the driver in the island, deferred-fit and catalogue-row rounds, at up to 186 bytes a pixel: about 44 GB for a field-filling object at 15,402². No real LoTSS-DR3 object comes within a factor of ten of the budget. | Driver memory scales with the wide segments of a round, not the tile. | Deferred: associative partial sums on the cores first, then a reviewed design for the local-noise median; reopened when a tier's traced peak shows the term or when the cluster benchmark is planned. A connected network of narrow filaments is the diagnostic that would measure its growth. |
| Source association costs more than the image grows; a dense Rapthor sector (ELAIS-N1, 123,186 sources) took 8.5 h serially on 11 October. | A dense sector takes hours inside the envelope. | Tasks 55 and 54 removed the quadratic hierarchy decision and the strip-shaped reads; under the same `continuum` profile the sector took 2.0 h on 17 October against 8.5 h, and 1.3 h under the `compact` default. Profile the anchors again within task 23. |
| The development machine's 18 GiB RAM, free disk (30 GiB on 16 October) and 16 GB container VM limit local tiers and matched benchmarks: `master` cannot run a 15,402² sector in the VM. | Local evidence stops at the 10,000² anchor for matched runs and at 22,500² for tiers. | The cluster measures the gate; about 60 GB free before 45,000². |
| Rapthor and LSMTool change frequently; their pins moved to the upstream heads on 17 October, and PyBDSF's `master` is 91 commits past the binding reference. | Adapter, contract, benchmark or reference churn, or a backend that only works on a stale revision. | Move the Rapthor and LSMTool pins again only if upstream changes the filter step before the Rapthor branch is pushed (task 79), before the matched benchmarks (task 23) and at the freeze (task 28), re-running the contract audit, the acceptance scenarios and the agreement check and recording the outcome in the commit; keep PyBDSF at `c70103b` until the freeze. |
| The cluster benchmark depends on hardware not yet scheduled, acceptance on reviewers not yet named, and selecting Hebog from released Rapthor on the Rapthor branch merging. | 1.0.0 waits on a session and on reviews; until the merge, Rapthor users install Rapthor from the branch. | Testing, the trial and the cluster benchmark use the branch at a recorded commit, so none waits on the merge; Rapthor calls Hebog directly, so no LSMTool registry entry is required; the cluster session is one sector at four node counts after a local dry run (task 27); reviewers are approached when the branch is pushed (decision 1). |
| Extended association cannot be made exactly tile-invariant. | A tier stalls or changes science. | Test analytic shells and filaments crossing corners at each tier; escalate a scientific trade-off to the human rather than weakening invariance silently. |
| Large public images have minimal or non-standard headers, and no large public SKA-Low image exists. | Anchors cannot run unmodified, their science comparison is weak, or SKA-Low coverage relies on precursor data after 1.0.0. | Headers checked against the input header contract before download; explicit request metadata; per-facet LOFAR-HD catalogues for science; GLEAM-X DR1 with its PSF maps at the 45,000² release, and SKA-Low science-verification data once released (expected from 2027). |
| A noise window is fixed at 35 pixels, so under a beam several pixels wide it holds few independent samples: its estimate scatters, and patches of each noise map read well below the true noise. | Noise peaks in those patches pass as faint sources, and single cases move by chance whenever the noise estimate changes. | Judge a noise change by whole-map tails against injected noise, not single cases; windows scaled with the restoring beam (deferred) would narrow the scatter. |
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

- No change degrades the science (decision of 18 October): a change keeps
  or improves every case it moves on the quick check, the agreement
  check's truth measures and the truth catalogues, not only the gated
  endpoints, and an escaped defect first gains a fixed case that fails
  without its repair.
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
qualification includes full public or challenge images from LOFAR and
SKA-Mid for 1.0.0, SKA-Low precursor data at the release that admits it,
plus at least one other instrument. Compare Serial before alternate
executors and external finders.

| Measurement | Target |
| --- | --- |
| Rapthor retained/rejected components | Truth-based (decision of 17 October). Of the real components `master` keeps, on the ideal mask of a generated image or at least 7σ above the negative-pixel noise of a real one, a lane rejects ≤1% overall and ≤2% in every stratum; of the sources injected into the real images it keeps at least `master`'s share less 5 points at every level from 6σ, and all from 10σ; on the negated real images it finds false islands numbering ≤1% of the islands on the originals. Agreement with `master` is reported beside it |
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
sparse, true-sky and apparent strata; the former ≥99.5% agreement target
was retired on 16 October because released PyBDSF misses it too, and the
truth-based limits, which released PyBDSF passes, were set on 17 October.

## Performance and scale gates

For supported Rapthor deployment, the matched median ratio of the
source-finding part of Rapthor's `filter_skymodel` step, from the task's
start to LSMTool's `filter_sources` call, and its upper one-sided 95%
bootstrap confidence bound must satisfy (decision of 18 October 2026):

```text
dense sectors:  Hebog / pinned PyBDSF master (c70103b) <= 0.50
other sectors:  Hebog / pinned PyBDSF master (c70103b) <= 1.05
```

A sector is dense when pinned `master` finds at least 10,000 sources in
it, a provisional threshold confirmed or moved from the measured
source-count curve before the cluster benchmark is packaged. PyBDSF's
source finding is slow where sources are many, which is where Rapthor's
step needs a faster finder; where finding is already fast, matching
`master` is enough, and 1.05 is the margin of the Hebog non-regression rule
below. Each finder's time against the source count at fixed cores, and its
speed-up against cores on a dense sector, are reported beside the ratios
and not gated.

The gate binds the span the finder controls; LSMTool's filtering is the
same for either finder (291 s and 307 s on the 10,000² anchor) and is
reported beside it as the complete step, never gated (decision of
16 October 2026; `measured_phase` in
`config/benchmarks/phase-0-performance.json`). Pinned `master` was faster
than released 1.14.1 in every matched Phase 0 run (3.0% at 256², 6.8% at
3,000²), so the dense gate is at least as strict as the former release gate;
task 31 confirms the release ratio once. Scientific eligibility precedes
performance acceptance. These are minimum deployment gates, not a reason to
stop optimizing or to hold an experimental standalone release.

- Maintain the anchors and workloads of the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md),
  with the real images below beside the nearest anchor and both sides of
  every measured crossover. Gate deployment on the frozen envelope; 1.0.0
  qualification measures the gate on the cluster at the envelope's sizes,
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
- Component budgets remain diagnostic; the finder part of the complete
  step decides deployment.

### Reference images

The real images the repository uses or plans to use, with the windows its
checks cut from them. The
[input header contract](../docs/reference/input-header-contract.md) says
how each is read; check other headers before a large download. No image
data or dataset belongs in Git; the checked-in configuration names each
source and window.

| Family | Image | Size | Use | Reference |
| --- | --- | --- | --- | --- |
| LOFAR | LOFAR-HD ELAIS-N1 mosaic, 0.4/0.2/0.1″ pixels | 22,500², 45,000², 90,000² (2.0, 8.1, 32.4 GB); 2-D `float32`, `JY/BEAM`, SIN, beam present, no frame or reference-frequency keywords | The 1.0.0 envelope's anchor (22,500²) and the later tiers | Per-facet PyBDSF catalogues; facets are WSClean FK5 J2000 images |
| LOFAR | LoTSS-DR3 HEALPix mosaics (1,571) | 14,390–17,752² (1312: 15,402², ICRS, `RESTFRQ`, beam present, 1.5″ pixels, 9″ beam) | Science and throughput. Quick check and quick benchmark: 1,024² windows of mosaic 1312 at x 9,749, y 9,749 (sparse) and x 7,701, y 6,677 (dense). Quick benchmark and traced peak: 3,000² at x 6,713, y 5,689; 3,600² at x 6,413, y 5,389; 10,000² at x 2,000, y 4,500, the 10,000 tier's anchor and the screening case of 16 October; and the whole mosaic, `lotss-dr3-1312-15402`, the 15,402 tier's anchor | Per-mosaic PyBDSF `srl` and `gaul` catalogues (mosaic 1312: 22,420 sources, 28,559 Gaussians) plus RMS, residual and mask maps |
| LOFAR | LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky pair | 14,175² each (804 MB); DDFacet, four axes, ICRS, `RESTFRQ`, 6″ beam | Closest public match to Rapthor's two inputs; the dense deep-field sector of tasks 54 and 78 | PyBDSF catalogue and maps |
| LOFAR | LoTSS-DR2 cut-outs: a 22′ survey field at 12h +45°, 3C 295 (12′), M51 (20′) and a 90′ field at 13h +47° | 1.5″ pixels: about 880², 480², 800² and 3,600² | Notebook comparison whole-image cases (`lotss-dr2-*`); the 22′ field is the public API's example input | LoTSS-DR2 PyBDSF catalogue |
| SKA-Mid | SDC1 B1/B2/B5, 8/100/1,000 h (Zenodo 4328029; INAF mirror) | 32,768² (4.3 GB each); 4-D, `JY/BEAM`, `EPOCH = 2000`, `BMAJ`/`BMIN` but no `BPA`, supplied as 0° | Science checks with truth. B2 1,000 h cut-outs: 1,024² at x 20,992, y 12,800 (sparse) and x 16,896, y 16,896 (crowded), and 2,048² at x 16,384, y 16,384 (crowded), in the quick check, benchmark and traced peak; the notebook comparison's 2,048² tiles; cut-outs for task 29 | Full truth catalogue (`True_1400_v2.txt`), the B2 primary beam and the official submissions |
| SKA-Mid | MeerKAT MIGHTEE DR1 COSMOS and XMM-LSS; SMGPS tiles | MIGHTEE 7,486² and 14,800² (448 MB and 1.75 GB), two axes with declared `FREQ` and `STOKES`, FK5 J2000; SMGPS 7,500² with 16 Obit `SPECLNMF` planes in Galactic coordinates, refused as a cube | Real precursor science; header variety; MIGHTEE is inside the envelope for task 29 | PyBDSF (MIGHTEE); Aegean (SMGPS, diagnostic only) |
| SKA-Low | MWA GLEAM-X DR1 mosaics | 170–231 MHz: 31,468 × 11,151 (2.8 GB), `ZEA`, FK5 J2000 by `EPOCH`, frequency only in a non-standard `FREQ` keyword; PSF maps 360 × 180 × 4 on a 1° grid | Precursor science with a PSF that varies across the field (task 15); its long side needs the 45,000² tier, so it joins that release | PSF maps; Aegean catalogue (diagnostic only) |
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
together. User and developer documentation names work by what it does,
never by plan task number, and carries no development history; the plan
and Git history hold those. Record completed work in Git history with
exact evidence references, not as another "latest" section in user
guidance. Removing a historical narrative never changes a closed result.
