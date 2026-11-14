# Hebog implementation plan

The authoritative plan for 1.0.0: what 1.0.0 means, how far Hebog is from
it, the remaining tasks in order, the decisions the maintainer still has to
take, and the rules and gates that govern the work. Updated
**13 November 2026**.

Measured figures are on
[progress against goals](../docs/reference/progress-against-goals.md) and
user-facing limits in [release status](../docs/reference/release-status.md);
the summary below and the progress page change together. Git history
records completed work, ADRs record architecture decisions, and
[`LOG.md`](../LOG.md) is an archive that receives no new entries.

## How far from 1.0.0

Hebog's latest release is v0.25.0 (9 November), experimental and
scientifically unqualified. The candidate is public composition v23 with
`continuum`'s crowded-field noise repaired (18 October).

| Goal | Where it stands | What remains |
| --- | --- | --- |
| Telescopes | LOFAR and SKA-Mid images run under the input header contract | Validation in the parity study (task 29); a varying PSF measured and documented (task 15) |
| Functionality | Complete in Hebog; Rapthor's Hebog branch runs it on today's worker layout | Push the branch (task 79); its distributed path (task 72); the operational trial (task 32) |
| Science | Rapthor's profile passes the truth-based gate on development evidence | The candidate freeze (task 28); the powered parity study (task 29); the released-PyBDSF check (task 31) |
| Performance | Measured, every sector fails its limit; projected, 0.25.0 meets every limit on one cluster node if `master` uses four cores of a dense sector's node | Task 72's three remaining increments; matched benchmarks (task 23); the cluster run that measures the gate (task 30) |
| Scalability | 22,500² admitted, with products invariant across tilings and executors; nothing has run beyond one machine | The envelope freeze (task 22); planner bounds (task 24); the store (task 25); the cluster benchmark (tasks 27 and 30) |
| Release | On PyPI; CI on Linux, macOS and Windows | Independent acceptance (task 33); 1.0.0 (task 34) |

- **Largest risks:** the performance gap; memory that grows with the image
  and the sources found; the development machine's limits; upstream churn;
  and three steps outside the agent's control: cluster time, Rapthor's
  worker layout and independent reviewers. See [risks](#risks).
- **Next action.** Agent: task 72's next increment, in the order the
  checkpoint sets. Human: take the checkpoint (decisions 3 to 5); push
  Rapthor's Hebog branch (task 79); file the Astropy report
  (`benchmark-results/upstream/astropy-wcs-d-exponent.md`) and the PyBDSF
  report (`benchmark-results/upstream/pybdsf-moment-fallback-index.md`).
- **Deferred** until the integration and scaling work is complete, unless
  an output is confirmed incorrect: meshes scaled with the beam, to admit
  beams wider than 10 pixels; wide-object reductions on the cores instead
  of the driver; Aegean, ProFound and SoFiA comparisons; PyBDSF's second
  grouping rule; native code without a passing profile gate.

## Definition of 1.0.0

Version 1.0.0 is the first release shown to be a backend Rapthor can switch
to: proven at Rapthor's sector sizes, faster than PyBDSF's source finding,
scaling across nodes, with the science Rapthor consumes qualified (decision
of 16 October 2026). Every claim is bound to reviewed evidence for the
exact candidate.

- **Telescopes.** Standard FITS continuum images from any radio telescope
  that meet the [input header contract](../docs/reference/input-header-contract.md),
  with WSClean, CASA and SKA SDP conventions accepted or refused with a
  specific error. Validated on LOFAR and SKA-Mid images for 1.0.0, and on
  SKA-Low precursor data at the minor release whose envelope admits them.
- **Functionality.** A supported, feature-flagged backend for Rapthor's
  `filter_skymodel` at pinned Rapthor and LSMTool revisions: both image
  branches, the Rapthor profile, catalogue, mask, RMS and source-count
  products, empty and blanked images, retry and restart, and PyBDSF
  fallback. The standalone API works without Rapthor, Prefect, LSMTool or
  Dask.
- **Science.** The Rapthor profile passes the truth-based gate of the
  [scientific gates](#scientific-gates), and the frozen candidate passes a
  prospective, powered, held-out parity study against pinned PyBDSF
  `master` on full LOFAR images, SDC1 simulations with truth and a MeerKAT
  MIGHTEE image. One check against released PyBDSF 1.14.1 confirms
  agreement for users of the release.
- **Performance.** The source-finding part of Rapthor's step takes at most
  0.50 of pinned `master`'s time on dense sectors and no longer than
  `master`'s on the rest, under the
  [performance gates](#performance-and-scale-gates), for sectors up to the
  envelope: on one node, and on dense sectors also across the nodes Rapthor
  deploys. The gate is measured on the cluster.
- **Scalability.** The 22,500² envelope, which covers Rapthor's default
  sectors. One sector's time keeps falling from 1 to 10 nodes with
  invariant products, and planner tests bound graph size and reduction
  depth for 100,000² images on 100 to 200+ nodes, which release notes call
  designed for, not demonstrated.
- **Release.** On PyPI with portability, security, licensing, current
  documentation and independent radio-astronomy and engineering
  acceptance, under the 1.x policy in the [delivery policy](#delivery-policy).

Later envelope raises are minor releases ([after 1.0.0](#after-100)).
Rapthor's default cutover is Rapthor's own decision after an operational
soak; the PyBDSF fallback stays until then.

## Decisions pending

Each names the maintainer's call and the agent's recommendation. A decision
taken is recorded in the row it affects and in the commit, never in
`LOG.md`.

1. **Independent reviewers (task 33)** have not been named.
   *Recommendation:* approach the radio-astronomy and engineering reviewers
   when the Rapthor branch is pushed, so their review runs beside Rapthor's.
2. **The scaling floor.** "Scales well across nodes" needs a number before
   the cluster session. *Recommendation:* task 27 proposes a strong-scaling
   efficiency floor at 10 nodes from the local curve, approved with the
   contract amendment.
3. **The dense-sector threshold**, provisionally 10,000 sources in
   `master`'s catalogue. The model's lines cross 0.50 at about 8,400 to
   8,600 sources, but they join sparse sectors, where `master` uses every
   core, to dense ones, where it uses four, so the crossing reflects that
   change as much as either finder's growth. *Recommendation:* keep 10,000;
   it marks where PyBDSF is slow, and moving it to the crossing would fit
   the gate to the candidate.
4. **Task 72's targets and the order of its increments.** On a node
   Hebog's time nears its floor, the driver's time plus each round's
   longest task; increment 1 halved the dense cell's longest tasks, so the
   driver now holds most of it. *Recommendation:* aim at floors of 100 s
   on the dense cell and 40 s on the sparse one, with no faster growth in
   the source count, and report both in each increment's profile. Order:
   Rapthor's distributed path first, which the gate and the cluster run
   both need; then waiting and sharing, with the driver's FITS writes and
   reconciliation; then both branches together.
5. **Per-source costs.** Hebog's time on a node grows 4.0 ms a source,
   within the stricter 4.6 ms target. *Recommendation:* no separate
   per-source work; the driver's per-source work joins waiting and sharing.

## Scope and resource rules

- **Use cases** (maintainer, 10 October 2026), each a performance target;
  none may be optimized by regressing another:
    1. one Rapthor sector across a cluster of nodes with up to 192 cores:
       the usual Rapthor run and the first performance focus;
    2. one Rapthor sector on one node, the gate's like-for-like comparison;
    3. standalone use on a local machine with smaller images, where setup
       and scheduler overhead dominate;
    4. standalone use on a Dask cluster the user starts, for an image too
       large for one node.

  Several sectors at once stay supported. Hebog states what it needs from a
  Dask cluster and the caller provides it
  ([ADR-010](../docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md));
  Rapthor builds the executor from its
  [layout](../docs/architecture/rapthor-execution-layouts.md). Images are
  two-dimensional; a cube or time axis needs a new ADR.
- **Rapthor's profile** is `continuum` with a zero background, which passes
  the truth-based gate where `compact` fails it (decision of 17 October).
- **Compute.** Development and benchmarks run on the maintainer's machine:
  Apple M3 Pro, six performance cores, 18 GiB, and a six-core, 16 GB Podman
  VM for the containers. A cluster of up to 12 nodes (96 or 192 cores, 747
  or 1,494 GB, NUMA or not, no local scratch, shared Lustre) runs one
  benchmark for 1.0.0 and never blocks development. Hebog runs on every node
  type without per-node settings.
- **Disk.** A 22,500² run holds up to 49 GiB of scratch; the intermediates
  shrink before the 45,000² tier, which would otherwise need about 200 GiB.
  The local ladder stops at 45,000²; 90,000² runs only on the cluster.
- **Data.** Scale testing uses public LOFAR images; the LoTSS-Deep DR2
  ELAIS-N1 pair is the representative Rapthor input, and SDC1 cut-outs
  serve SKA-Mid science. See [reference images](#reference-images).
- **Pins.** Rapthor `main` at `aff26023`, LSMTool `master` at `156ae6a`,
  PyBDSF `master` at `c70103b`. Rapthor and LSMTool move only at the
  checkpoints the [risks](#risks) name, re-running the contract audit,
  acceptance scenarios and agreement check. If Rapthor declares a different
  LSMTool revision, record both and test the latest LSMTool.
- **Limitations that block 1.0.0:** `E_RA`/`E_DEC` calibration on a real
  high-declination field; the `Total_flux` rows of the
  [scientific gates](#scientific-gates); and faint association where it
  changes island grouping. Other accepted limitations stay documented.

## Delivery policy

Ship frequent experimental `0.x` releases, normally one for each merged task
that changes behaviour. Every check has a budget; one that outgrows it is
sampled, split or moved to a less frequent level, never silently extended:

- **Change check (about 15 minutes):** relevant tests, the quick science
  check and, for performance changes, the quick benchmark's default tier.
- **Release check (about 1 hour):** the change check, Serial/Dask agreement
  on the largest anchor that fits (10,000² today) and the installed wheel.
- **Tier gate (up to a day, unattended):** the
  [envelope gate](#the-deployment-envelope-and-gate) on a new tier's anchor.
- **1.0.0 qualification (once):** one powered science study, overnight on
  the development machine, and one cluster benchmark.

PyBDSF outputs and timings are computed once per input, revision and host,
and cached outside Git. A defect that escapes the quick checks adds its case
to the fixed set.

Four levels of done stay distinct:

- **Merge:** a coherent reviewed change with passing tests and accurate
  docs. Merge each PR in a sequence before branching the next.
- **Experimental release:** a tested package that states its unqualified
  science and limits, with no known incorrect supported output.
- **Scientific qualification:** candidate-bound parity, fresh held-out
  evidence and independent acceptance. An experimental label never turns a
  failed check into a pass.
- **Rapthor deployment or cutover:** separately qualified workflow,
  performance and operational acceptance, keeping the PyBDSF fallback until
  the acceptance matrix passes.

After 1.0.0 (decision of 16 October 2026) the public API, the Rapthor
adapter contract and the product schemas are stable within 1.x; an envelope
raise is a minor release; a science change is a minor release with a new
composition version and notes saying what moved; patch releases change no
product. Ownership follows [`AGENTS.md`](../AGENTS.md#changes-releases-and-handoff),
and Release Please alone edits versions and release notes.

## Collaboration and repair decisions

These rules govern agent work on this plan; [`AGENTS.md`](../AGENTS.md)
refers to them.

- The agent owns routine completeness and integration checks and gives
  clear recommendations. Don't rely on the user to notice a missing check,
  ask for a cheap diagnostic or rebuild status across conversations. Keep
  human attention for scientific interpretation, priorities and trade-offs.
- Before a scientific or campaign repair, write a short decision in the task
  or plan: the problem, the proposed cause, an independent test, the
  expected measurable change and when to stop. Distinguish a correctness
  defect, a failed gate, an operational failure and an optional
  improvement; a failed aggregate alone does not establish a cause.
- After two repairs of the same mechanism make no material change, review
  the diagnosis and recommend a bounded next step before another full
  replay. This triggers reassessment; it does not permit dropping required
  work, changing gates or retrying closed evidence.
- Keep development closure, qualification, release and cutover distinct.
  Record optional improvements as deferred work. A known incorrect supported
  output blocks release whatever the phase label.
- Carry authorization forward within its scope. Finish authorized
  preparation and give a concrete recommendation before asking for a new
  scientific or resource decision, and explain the exact boundary; add no
  approval steps for routine reversible work.
- At milestone reviews, use Git history, PR discussion and evidence to
  judge time to diagnosis, avoidable interruptions, ineffective repairs and
  the user's effort to recover status. Improve the workflow from them, not
  from commit counts or documentation volume, and add no tracking
  framework.

## Path to 1.0.0

Task numbers are stable: a finished task is removed and its number never
reused (up to 80 used). Sections and rows are in expected finishing order.
Each task merges, and normally releases, within the iteration budgets; split
it when a measurement reveals independent changes. Unless stated otherwise,
the agent implements and validates locally and the human merges. A
qualification, scale or deployment task authorizes only its stated claim.

Four rules govern the sequence:

- **Measure before changing:** no optimization without a profile, and no
  science-touching merge without `just quick-science-check`.
- **One tier and one release at a time:** the envelope rises only through
  its tier gate, and each raise is a release.
- **Products unchanged through a refactor:** catalogue, RMS and mask stay
  byte-identical on the quick check, no production file loses coverage, and
  a removal starts with a test that fails for the reason it states.
- **Confirm on a real anchor:** a review's figure is confirmed on a real
  anchor before a task that changes cost or memory closes.

The order:

1. Push Rapthor's Hebog branch (task 79).
2. One sector across the cluster (task 72): Rapthor's interim thread path
   cannot use a node's cores, so the distributed path comes first.
3. The deployment envelope and gate (tasks 22 and 23), with the store,
   planner and cluster benchmark (tasks 24, 25 and 27).
4. Science before the freeze (task 15).
5. Qualification and 1.0.0 (tasks 28 to 34).

### Release and publication

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 79 | Human pushes, agent prepares | Push Rapthor's Hebog branch. | The tested commit is on a branch of Rapthor's repository and Rapthor's CI passes. The pins move again first only if upstream changes the filter step. The branch accepts any Hebog `0.x` from 0.22, so a breaking adapter change needs a matching branch change. Trials and the cluster benchmark use the branch; the merge request follows when the maintainer chooses. |

### One sector across the cluster

Hebog's tile tasks stay single-threaded and numerous so Dask can schedule
every core; no thread pool is nested in a task, and arrays stay NumPy behind
the executor protocol. The aim is a curve for one sector that keeps falling
as cores are added; several sectors share the cluster beyond the point where
one stops scaling. The [execution plan](2026-10-18-one-sector-across-the-cluster.md)
holds the steps and evidence. Task 72 lands as four increments, each merged
and released in turn:

- **Core budget and cost model** (in 0.25.0). Each stage chooses its tile
  core and task count from the cores the caller states, and each task's
  declared memory follows its core. Products depend on none of it.
- **Waiting and sharing.** The analysis secedes from its worker slot while
  it waits on its tasks; each round's declared memory is re-audited against
  its measured peak; each completion record is split by tile, so a task
  reads only its window's entries; several analyses and joining workers run
  without deadlock or changed products.
- **Rapthor's distributed path.** Rapthor's task runs the analysis on
  single-threaded Dask worker processes for the step's cores, on a cluster
  it owns with Dask's memory actions off, and passes its client and
  resource names to `DaskExecutor`; it keeps threads for small sectors and
  tests (decision of 12 November). Hebog's adapter takes over the
  source-count estimate and the analysis reservation, so Rapthor supplies
  only its memory budget (decision of 17 October). What Hebog needs from a
  cluster is documented for any caller.
- **Both branches together.** The true-sky analysis and the flat-noise
  estimate submit their tasks through the executor at once.

Each increment also cuts the serial work it touches where the gain is clear
(decision of 18 October).

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 72 | Agent | Make Hebog's tasks scale on any Dask cluster, Rapthor's included. | The four increments have merged and released, with products byte-identical across executors; the local curve on the 10,000² anchor falls below the 15 October baseline; and the dense and sparse cells' ratios and the Dask path's CPU overhead are measured again. |

### The deployment envelope and gate

Each tier passes one gate before its limit changes: the tiling-invariance
tests, the quick science check, a quick benchmark on both sides of any
crossover, a reproduced `just traced-peak` and the task memory audit on the
tier's anchor. The memory measure is `tracemalloc`'s peak, which is
deterministic; peak RSS varies with machine load and is reported beside it,
never as the threshold.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 22 | Agent proposes, human freezes | Freeze the deployment envelope. | Sizes and workloads match Rapthor's production sectors (17,000 to 20,000 pixels a side), and a larger image is refused with a typed error so Rapthor falls back to PyBDSF. |
| 23 | Agent | Run matched `filter_skymodel` benchmarks and optimize the finder part towards the gate. | On every cell the container VM holds, dense and sparse, the finder part's CPU and wall ratios against cores are recorded (`scripts/benchmark/measure_filter_skymodel.py`: one warm-up and five measured runs of each finder, alternating, in fresh containers); the largest constant factors the profile names are cut; memory, Hebog-curve non-regression and the quick check pass. The gate itself is decided on the cluster (task 30). |

### Scale beyond one machine

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 24 | Agent | Bound the graph for 100,000² at 10 and at 200 nodes without running the science. | Planner tests show at most 50,000 tasks, bounded reduction depth, bounded driver memory and valid memory admission for both topologies. |
| 25 | Agent | Qualify the Zarr store and the restart and recovery path locally. | Atomicity, concurrent owned-chunk writes, codecs and chunk geometry, missing chunks and injected failures pass within an admitted memory budget, and Zarr v3 sharding is evaluated against one file per chunk, since the cluster's only scratch is Lustre. |
| 27 | Agent packages, human approves the contract | Package the cluster benchmark and amend the scalability contract. | One command and a short guide run one dense sector at its default size on 1, 2, 5 and 10 nodes, and a sparse one on one node, through Rapthor's task and standalone; they record the hardware, a scaling-model fit, the ratio against PyBDSF on one node and the efficiency against decision 2's floor. `config/benchmarks/phase-0-scalability.json`, the contracts page and `just test-scalability` describe it, keeping 50 to 200 nodes as design targets. A local dry run passes, so the session measures rather than debugs. |

### Science before the freeze

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 15 | Agent measures, human dispositions | Measure and document a point-spread function that varies across the field. | Its effect on fluxes and sizes is measured with injected truth and documented as a limitation; a PSF-map input follows 1.0.0 unless the effect changes a field Rapthor consumes. Waits until the work above is complete unless an output is confirmed incorrect. |

### Qualification and 1.0.0

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 28 | Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed, and the pins move for the last time; a later change restarts only the affected qualification tasks. |
| 29 | Agent designs, human approves | Run one powered parity study on fresh held-out and public-survey data, overnight on the development machine. | Every binding endpoint passes under a prospectively reviewed design, including the limitations that block 1.0.0 and the truth-based gate, on full LOFAR images, SDC1 simulations and a MIGHTEE image. Closed failed campaigns are never reused as confirmation. |
| 30 | Human runs, agent analyses | Run the cluster benchmark once: the gate's measurement. | One sector's time falls to decision 2's floor at 1, 2, 5 and 10 nodes with invariant products, and its ratio against PyBDSF passes the gate on one node and as Rapthor deploys. A failure becomes a `0.x` repair task. |
| 31 | Agent | Check released PyBDSF 1.14.1 once. | One matched run confirms the performance gate and Rapthor-profile agreement against the release on a dense and a sparse sector. |
| 32 | Human runs in Rapthor, agent supports | Run the operational trial behind Rapthor's flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| 33 | Agent assembles, independent reviewers accept | Assemble the readiness packet and obtain acceptance. | The packet binds science, profile, performance, scale, portability, dependency and licence audit, packaging and documentation to the frozen candidate, with separate radio-astronomy and engineering acceptance. |
| 34 | Human | Release 1.0.0. | Release Please produces 1.0.0 and it publishes to PyPI, with notes stating the envelope, the 1.x policy and what is designed for but not demonstrated. |

### After 1.0.0

Each envelope raise is a minor release through the tier gate.

| # | Owner | Task | Done when |
| --- | --- | --- | --- |
| 56 | Agent | Measure the analysis memory again now its local-noise requests are bounded. | The whole 22,500² mosaic and its central 7,500² are audited and traced again, the new peak is named, and `hebog.analysis_memory_bytes` comes down as far as the anchors allow. Needs about 58 GiB of free disk; needed before 45,000². |
| 12 | Agent, human approves | Raise to 45,000² on the LOFAR-HD mosaic (1.1). | The scratch fits the free disk with 15 GiB to spare, which needs the intermediates shrunk first, and the tier gate passes. This is the out-of-core demonstration: the run completes in 18 GiB with the traced peak bounded by the tile, although one `float64` copy of the image would not fit. GLEAM-X's SKA-Low precursor data joins it. |
| 80 | Human runs, agent analyses | Raise to 90,000² on the cluster (1.2). | The 90,000² mosaic runs standalone on the cluster at two node counts with invariant products. |

A PSF-map input and the deferred science join these releases as evidence
and demand allow.

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hebog's finder part is about `master`'s time on the dense cell on Dask workers, where the gate needs half, and about 1.7 times it on the sparse cell, where `master` keeps gaining past four cores. | The cluster gate fails on dense sectors, or sparse sectors stay slower than `master`. | Task 72's model and increments raise occupancy and cut serial work; task 23 cuts the largest constant factors; native code only through its gates; report the gap honestly at each milestone. |
| Hebog's mask makes Rapthor keep different components from `master`'s on deep LOFAR fields. | The truth-based gate fails where Hebog loses real sources. | `just rapthor-agreement` measures every lane against truth at each pin move and science change. |
| One sector's speed-up is capped by serial work, memory per core, rounds of few tasks, the interpreter lock, or deadlock between concurrent sectors. | Cluster cores go unused and the gate is missed on occupancy. | Task 72's increments; the cluster benchmark reports where one sector stops scaling. |
| Scaling inside Rapthor needs Rapthor to change its worker layout. | Rapthor's cluster run uses one core a node. | The standalone run on the same cluster is the scaling evidence meanwhile (task 27). |
| Kept records and the analysis's memory grow with the image and the sources found. | Large tiers exceed memory; a dense sector's analysis needs several GB on its worker. | Task 56 before 45,000²; planner bounds include the records (task 24); `hebog.analysis_memory_bytes` states the analysis's memory. |
| An object wider than a task's read budget is reduced on the driver. | Driver memory grows with wide objects, not the tile. | Deferred; reopened when a tier's traced peak shows it or the cluster benchmark is planned. |
| The development machine's RAM, disk and container VM limit local tiers and matched runs. | Matched runs stop at the 10,000² anchor and tiers at 22,500². | The cluster measures the gate. |
| Uncompressed Zarr intermediates take about 100 bytes a pixel. | A 45,000² run needs about 200 GiB of scratch. | Before 45,000²: compress label planes losslessly and delete each plane after its last reader. |
| Rapthor and LSMTool change often, and PyBDSF's `master` has moved past the reference. | Adapter, benchmark or reference churn. | Move the Rapthor and LSMTool pins only before task 79's push if the filter step changes, before task 23 and at the freeze, re-running the audits; keep PyBDSF at `c70103b` until the freeze. |
| The cluster session, the reviewers and Rapthor's merge are not yet scheduled. | 1.0.0 waits on them. | Testing, the trial and the benchmark use the Rapthor branch at a recorded commit; reviewers are approached when the branch is pushed. |
| Extended association cannot be made exactly tile-invariant. | A tier stalls or changes science. | Test analytic shells and filaments crossing corners at each tier; escalate any scientific trade-off. |
| Large public images have minimal or non-standard headers, and no large SKA-Low image exists. | Anchors need explicit metadata; SKA-Low evidence comes after 1.0.0. | Check headers before download; GLEAM-X at the 45,000² release. |
| The 35-pixel noise window holds few independent samples under a wide beam. | Noise peaks pass as faint sources, and single cases move by chance. | Judge noise changes by whole-map tails against injected noise; beam-scaled windows are deferred. |
| Short checks miss a rare regression, or campaigns absorb the schedule. | A defect reaches a release, or the schedule slips. | Each escaped defect adds a fixed case; budgets and cached references hold the schedule; task 29 is the backstop. |

## Scientific gates

Analytic or injected truth is primary. Pinned PyBDSF `master` at `c70103b`
is the binding finder reference; released 1.14.1, which Rapthor installs
today, is checked once (task 31). The two diverge, so neither is truth.
Later `master` commits are adopted only by a plan decision. Aegean
comparisons are paused until task 29's design decides.

- **No change degrades the science** (decision of 18 October): a change
  keeps or improves every case it moves on the quick check, the agreement
  check's truth measures and the truth catalogues, and an escaped defect
  first gains a fixed case that fails without its repair.
- Each campaign has its own prospectively reviewed endpoints and decision
  rules. Choose a whole incumbent before viewing results; never combine
  historical best values into a synthetic comparator.
- Require every applicable PyBDSF and incumbent comparison, with fixed
  margins and the conjunctive one-sided confidence rule. Inconclusive
  evidence is not parity, and an old candidate's uncertainty exception
  does not transfer to a replacement.
- Freeze the population, sampling unit, margins, missing-output rules and
  power before running. Resample whole realizations, not source rows or
  pixels. Planning variance sizes the study; the observed interval
  decides. Superiority claims need a prospective multiplicity rule, and
  improvements cannot offset a failed binding check.
- Valid products, finite or explicitly unavailable measurements,
  schemas, provenance and deterministic execution stay binding. Keep every
  morphology, scale, SNR, noise and boundary stratum.
- Compare like semantics: original pixels for flux, valid pixels for mask
  scores; report splits, merges, duplicates and low-SNR completeness and
  reliability separately.
- Before a long campaign, run a bounded development screen with cases
  chosen before seeing results. A clean screen is not powered parity.

The dataset matrix keeps compact SNR 3–100, blends, diffuse Gaussians,
filaments and shells, mixed emission, varied beams, WCS, pixel scales and
units, negative backgrounds, empty, all-NaN and invalid data, varying noise,
edges and every tile-edge and corner topology. Every dataset has a role,
provenance, checksums and generator identity
([dataset manifests](../docs/reference/dataset-manifests.md)), and new
populations are seed-disjoint from existing ones. Qualification includes
full public or challenge images from LOFAR and SKA-Mid and at least one
other instrument. Compare Serial before other executors and external
finders.

| Measurement | Target |
| --- | --- |
| Rapthor retained/rejected components | Truth-based (decision of 17 October). Of the real components `master` keeps (on the ideal mask of a generated image, or at least 7σ above the negative-pixel noise of a real one), a lane rejects ≤1% overall and ≤2% in every stratum; of sources injected into the real images it keeps at least `master`'s share less 5 points at every level from 6σ, and all from 10σ; false islands on negated real images ≤1% of the islands on the originals. Agreement with `master` is reported beside it |
| Reference recovery, SNR ≥10 | ≥99% |
| SNR ≥5 | Report the compatibility curve; no single pass fraction |
| False-discovery rate | ≤1 percentage point above reference |
| Isolated SNR ≥10 position difference, median / p95 | ≤0.02 / 0.10 beam |
| Isolated SNR ≥10 peak-flux difference, median / p95 | ≤2% / 5% |
| Isolated SNR ≥10 integrated-flux difference, median / p95 | ≤5% / 10% |
| `Total_flux` excess against injected truth, median, SNR 10 / 20 / 50 | ≤ +14% / +3.5% / +1% |
| `Total_flux` absolute excess against injected truth, p95, SNR 10 / 20 / 50 | ≤ 35% / 12% / 6% |
| `Total_flux` Hebog minus pinned `master`, paired over realizations, upper one-sided 95% bound, per stratum | ≤ +1 point in median and p95 |
| `Total_flux` 3σ-clipped mean ratio to truth, SNR ≥ 20 | within ±3%, clipped scatter ≤ 5% |
| Source-free RMS-map difference, median / p95 | ≤2% / 5% |

The `Total_flux` limits (23 September) come from PyBDSF parity on the M1
calibration population and Rapthor's 10% photometry floor, pooled over white
and beam-correlated noise; the powered study adds a check per noise class.
`just rapthor-agreement` measures the retained/rejected row overall and in
the bright, extended, edge, masked, crowded, sparse, true-sky and apparent
strata.

## Performance and scale gates

For Rapthor deployment, the matched median ratio of the source-finding part
of Rapthor's `filter_skymodel` step, from the task's start to LSMTool's
`filter_sources` call, and its upper one-sided 95% bootstrap bound must
satisfy (decision of 18 October 2026):

```text
dense sectors:  Hebog / pinned PyBDSF master (c70103b) <= 0.50
other sectors:  Hebog / pinned PyBDSF master (c70103b) <= 1.05
```

A sector is dense when `master` finds at least 10,000 sources in it, a
provisional threshold confirmed or moved before the cluster benchmark is
packaged (decision 3). Each finder's time against the source count and its
speed-up against cores are reported beside the ratios, not gated. LSMTool's
filtering is the same for either finder, so it is reported as the complete
step and never gated. Scientific eligibility comes before performance
acceptance, and these minimum gates are no reason to stop optimizing.

- Maintain the anchors and workloads of the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md),
  with both sides of every measured crossover. 1.0.0 measures the gate on
  the cluster at the envelope's sizes; 100,000² is covered by planner tests
  only.
- Compute reference timings once per input, revision and host, and reuse
  them.
- Match environments and record evidence as
  [`AGENTS.md`](../AGENTS.md#scientific-and-performance-gates) and the
  [evidence records](../docs/reference/evidence-documents.md) require: one
  warm-up and at least five measured repetitions, every value kept.
- Hebog non-regression needs an upper one-sided 95% bound ≤1.05 against the
  previous reviewed curve; a lower bound above 1.05 is a regression. A
  memory regression above 10% against either PyBDSF reference needs an
  approved trade-off.

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
library with inert imports and small typed requests; one tile-native
composition for every size with Serial as the oracle; Zarr as the sole
intermediate backend; stage-specific halos, global ownership and
hierarchical reductions; never a complete large plane on one worker; dtype kept
unless scientific evidence supports a change.

User-facing documentation describes current behaviour, names work by what
it does rather than by task number, and carries no development history;
the plan and Git history hold those.
