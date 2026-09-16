# Hebog implementation plan

Authoritative remaining-work plan. Updated **16 September 2026**.
Current user-facing capability is in
[release status](../docs/reference/release-status.md); execution history,
evidence identities and completed decisions are in [`LOG.md`](../LOG.md).
Closed Phase 5 contracts, reviews and campaign tooling are in Git history at
`4babf0b`.

## Current state

| Item | Current position |
| --- | --- |
| Release | v0.7.0, tagged and uploaded to TestPyPI on 16 September 2026. Experimental and scientifically unqualified. |
| Candidate | Public composition v20. Development-unqualified. |
| Functionality | Standalone FITS-to-products finder: background/RMS, compact and multiscale detection, deblending, fitting, source association, catalogue/mask/RMS/diagnostics, Serial and caller-owned Dask execution. No Rapthor backend: `hebog.adapters` holds records and the 8-column catalogue codec only, and the seven acceptance scenarios are strict-xfail placeholders. No flat-noise branch or LSMTool filtering has run on Hebog products. |
| Scalability | Public envelope ≤1,024 pixels per side. Only background/RMS and first-pass detection run per tile through the executor, on hard-coded 128-pixel cores (the scalability contract's candidates are 2,048–8,192); the public science in `public_science.py` holds several full `float64` planes in one process. Tiled multiscale, deblending, measurement, fitting and compact catalogue stages exist in `stages/` but only tests use them; continuum candidate products, extended association, the à trous position filter and the continuum catalogue have no tiled form. Two background sub-steps are capped at 10⁶ pixels. The executor offers only `map_batches` with a driver-side gather. |
| Performance | No matched benchmark exists. The most recent diagnostic single runs (10 September, M3 Pro) were slower than released PyBDSF on 11 of 13 real images, median ratio 8.4× (SDC1 2,198² tile 778 s vs 93 s; Hydra 3,600² 2,767 s vs 142 s). Per-pixel cost on these real images is far above the 26 s synthetic 1,024² probe; whether size, source density or both drive it is unprofiled. The gate is ≤0.50× released and <1.00× `master`. No complete-path profile exists. |
| Science | The v15 campaign failed only through 32 regressions against the earlier Hebog incumbent; no comparison against released PyBDSF, PyBDSF `master` or Aegean failed, and 40 were underpowered. All campaign images were ≤1,024 pixels. v16–v20 have focused regression, Serial/Dask, equivalence and installed-wheel evidence only. Uncertainty calibration, measurement tails and faint association were accepted on 13 September as limitations of an experimental standalone release, not as passes. |
| 1.0.0 blockers | Every milestone below. The largest risks are the performance gap, tile-native continuum association, a 10-node test ceiling, and SKA-Low coverage with no large public SKA-Low images. |
| Next action | Human: decide D1, D2 and D4. Agent: M1 (benchmark harness and complete-path profile), which needs no new decision to start on the development host. |
| Deferred | Optional comparison finders such as ProFound or 2D SoFiA (see the [notebook guide](../docs/how-to/notebooks.md)), general science improvements outside Rapthor-consumed outputs, and native code without a passing profile gate. Reopen a deferred issue if it becomes a confirmed incorrect supported output. |

## Definition of 1.0.0

*Proposed; the human confirms or changes it through D1.* Version 1.0.0 is the
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
  prospective, powered, held-out parity/retention against released PyBDSF,
  PyBDSF `master` and Aegean. The evidence includes full images, not only
  cut-outs, from LOFAR, SKA-Mid (SDC1 simulations and MeerKAT) and SKA-Low
  (MWA precursor data and simulations until SKA-Low data are public).
- **Performance.** Matched complete `filter_skymodel` medians meet both
  runtime gates across the frozen deployment envelope, without a memory or
  Hebog-curve regression, on the whole size and workload matrix.
- **Scalability.** The 90,000-square LOFAR-HD ELAIS-N1 mosaic and a
  generated 100,000-square truth image complete within the runtime,
  task-count, scheduler-overhead, memory and spill gates on 1, 2, 5 and 10
  nodes. Results do not change with worker count, tile geometry, completion
  order or retry. Operation on 100 to several hundred nodes remains the
  architecture target. For 1.0.0 it is supported by scheduler and graph tests
  with at least 200 worker processes and a measured scaling model, and
  release notes state that it is not demonstrated.
- **Release.** Published on PyPI with portability, security, licensing,
  current documentation and independent radio-astronomy and engineering
  acceptance.

Rapthor's default cutover is a separate Rapthor decision taken after an
operational soak of the 1.0.0 backend; the PyBDSF fallback remains until then.

## Decisions needed

| ID | Decision | Recommendation | Needed by |
| --- | --- | --- | --- |
| D1 | Scope of 1.0.0. | Accept the definition above. It keeps 1.0.0 a demonstrable Hebog claim and leaves default cutover to Rapthor operations. The alternative, tying 1.0.0 to cutover, makes the version depend on another project's release schedule. | Before M2 design |
| D2 | Test compute and data. | Scale testing is bounded by the human's cluster of up to 10 nodes and by public data; the [reference images](#reference-images) table lists the candidates. (a) One node, or another dedicated Linux host, runs reviewed benchmarks with fixed cores and no other workload; the laptop stays a profiling host. Record node cores, RAM and shared storage, and re-derive the contract's 512 GiB node profile from them. (b) Real scale anchors: the LOFAR-HD ELAIS-N1 mosaic at 22,500², 45,000² and 90,000² (the largest public radio image found) and SDC1 at 32,768². (c) Add generated-truth images at 100,000² and an OSKAR-simulated SKA-Low image, because no public image reaches 100,000² and no large SKA-Low image is public. (d) Claims above 10 nodes become design targets (see the 1.0.0 definition). (e) Agent access to the restricted Rapthor 3,000² image, or the public LoTSS-Deep DR2 ELAIS-N1 apparent/true-sky pair as a substitute. | (a) M1 end; (b)–(e) M5 start |
| D3 | Rapthor integration target. | **Decided 16 September.** When M3 starts, pin the latest commits of Rapthor's Prefect branch and of LSMTool's default branch, replacing the Phase 0 trace (`b1a6467`). Both projects change frequently, so pins move forward deliberately at the checkpoints listed under Risks. If Rapthor declares a different LSMTool revision, record both and test the latest LSMTool. | M3 start |
| D4 | Which accepted limitations block 1.0.0. | Block on those that change Rapthor-consumed fields: `E_RA`/`E_DEC` uncertainty calibration (Rapthor excludes sources at ≥2 arcsec), `Total_flux`/`Isl_Total_flux` tails, and faint association where it changes island grouping and therefore patches. Keep the rest documented. Approve a lean reusable non-regression campaign now (M1) and defer powered qualification to the frozen 1.0.0 candidate (M6). | M1 campaign design |

## Delivery policy

Ship frequent, useful experimental `0.x` increments rather than phase-sized
batches. Phase numbers survive only as historical identifiers.

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
item that merges, and usually releases as a `0.x` increment, with its own
checks; split a row when a measured result reveals independent changes.
Unless a row says otherwise, the agent implements and validates locally and
the human merges. Qualification, scale and deployment rows authorize only
their stated claim and still need the named human decisions.

Two rules govern the sequence:

- **Measure before changing.** Nothing is optimized or re-architected without
  a profile, and no science-touching change merges without the non-regression
  campaign from M1.
- **Optimize the code that survives.** M2 replaces the whole-array public
  science with the tiled composition. Before M2 lands, fix only bottlenecks in
  kernels the tiled path will keep (fitting, measurement, filters, labelling),
  not whole-array orchestration it will delete.

### M1 — Measure the gap

| Owner | Task | Done when |
| --- | --- | --- |
| Agent | Build a reusable complete-path benchmark lane. Replace the skipped `tests/benchmark` scaffolds and the phase-numbered runners with one checked-in configuration and runner. | One command times Hebog, released PyBDSF 1.14.1 and pinned `master` in matched containers on the same inputs and writes `hebog.validation.evidence` records with a warm-up and five repetitions. Inputs cover synthetic 256, 512 and 1,024 anchors in sparse, normal and dense-extended workloads, SDC1 tiles, Hydra and, after D2(c), the Rapthor-representative 3,000² image. Inputs above the public limit run through a documented diagnostic entry point that never changes the public envelope. A small portable smoke case runs in CI. |
| Agent | Freeze the v20 known-issues baseline and profile complete FITS-to-products execution. | Every warm-up and measured run is recorded. CPU, RSS, I/O and per-stage profiles on at least one dense real image and the 1,024 anchor rank the bottlenecks and separate size effects from source-density effects. Reviewed status waits for the D2(a) host; laptop results stay diagnostic. |
| Agent, human approves design | Add a reusable synthetic non-regression campaign. Rebuild the population generator, driver, truth evaluation and paired statistics from Git history without the removed authorization layer. | One configuration generates a fresh seed-disjoint continuum and compact-blend population, runs Hebog, released PyBDSF and Aegean, evaluates against injected truth, resumes after interruption, checks disk and memory before launch, and reports paired comparisons the notebook reads. Size it to run in hours on the benchmark host. Endpoints are the Rapthor-consumed fields plus the retained validity checks (D4). Run it on v20 as the reference for M2–M5. |

### M2 — One tile-native science path

This is the architectural core of 1.0.0 and the prerequisite for every size
tier above 1,024.

| Owner | Task | Done when |
| --- | --- | --- |
| Agent, human reviews ADR | Design the tile-native continuum composition. | An ADR (or ADR-005 amendment) defines, for every public stage, the halo, ownership rule, boundary summary and hierarchical merge, including extended association and sources larger than one halo, the à trous position filter and the continuum catalogue. It states how a small image stays one tile with no added overhead and records the `float64`/`float32` decision path. A decision statement precedes each science-affecting choice. |
| Agent | Converge `public_science.py` onto `stages/` so one composition serves every size. | The public path runs the tiled stages; one-tile and many-tile runs on analytic edge, corner and partition-origin cases agree exactly; the non-regression campaign and Serial/Dask invariance pass; the whole-array path is deleted. |
| Agent | Remove whole-plane state from the driver and background. | The 10⁶-pixel coarse-protection and local-noise caps are tile-bounded; RMS and mask products stream from Zarr row blocks; the catalogue is a partitioned reduction; input hashing is chunked; merges of boundary states run on workers. Tile cores are configurable within the contract's 2,048–8,192 range, and admission rejects a plan above eight live `float32` plane-equivalents or 75% of a worker limit before submission. Peak worker RSS scales with tile size, not image size. |
| Agent | Complete the executor contract. | Bounded submission and gathering, ordering, serialization, errors, cancellation, retry and resource annotations pass one suite for Serial, persistent local threads and caller-owned Dask. No nested pools or clusters. |
| Agent | Remove profiled bottlenecks in the tiled kernels. | Each change has paired before/after evidence on affected and adjacent anchors and passes the non-regression campaign. |
| Agent, human approves each raise | Raise the public envelope one tier at a time: 3,000, then 10,000. | Each tier passes exact tiled-invariance tests, the non-regression campaign, complete-path benchmarks on both sides of any crossover and a memory bound, before the limit and release status change. |
| Human | Switch uploads from TestPyPI to PyPI once the envelope covers Rapthor sector images. | The Trusted Publisher, `pypi` environment, publishing job, installation instructions and release status change together, as in the [publishing guide](../docs/how-to/publish-releases.md). |

### M3 — Telescope coverage and Rapthor functionality

The header audit and the Rapthor profile audit do not depend on tiling and
may run alongside M2.

| Owner | Task | Done when |
| --- | --- | --- |
| Agent | Define the input header contract for LOFAR, SKA-Low and SKA-Mid products and generic FITS images. | Fixture headers cover WSClean (4-D, `EQUINOX` without `RADESYS`), ddf-pipeline and DDFacet mosaics (no `BUNIT`, one copied beam), OSKAR (three axes, no beam, `CROTA`), SKA SDP data models (Stokes before frequency, no `BUNIT`), Obit multi-plane cubes, Galactic frames and ZEA projections. Each is accepted or rejected with a specific error. Metadata a header omits can be supplied explicitly in the request and is recorded in diagnostics. Headers of the real reference images are checked before their large downloads. |
| Agent, human dispositions | Decide how to handle a point-spread function that varies across the field. | LOFAR facets and MWA mosaics (which ship PSF maps) have a PSF that the header beam cannot describe. Measure the effect on fluxes and sizes with injected truth, then either accept a PSF map input or document the limitation with its measured effect. |
| Agent | Pin the latest Rapthor Prefect-branch and LSMTool commits (D3), refresh the Rapthor contract and audit the profile. | `docs/reference/rapthor-source-finding-contract.md` traces the pinned Rapthor and LSMTool revisions. Each PyBDSF behaviour LSMTool uses (zero mean map, adaptive RMS boxes 150/50 and 35/7 at threshold 75, hard 4/5 thresholds, three wavelet scales, island-stop flat-noise pass, `srl` catalogue, island mask, both RMS maps, source count and the blanked-image path) is mapped to an existing Hebog behaviour or a listed gap. |
| Agent | Implement the Rapthor profile and the flat-noise RMS branch. | Profile outputs are tested on analytic and generated truth; the flat-noise branch shares products and reads rather than running a second full analysis. |
| Agent | Implement the Rapthor adapter and exercise LSMTool on Hebog products. | Pinned LSMTool clips, groups and transfers names on Hebog catalogue, mask and RMS products for true-sky and apparent-sky inputs; the seven acceptance scenarios become passing tests (empty and invalid input, retry reuse, worker loss, fallback and dual run). The adapter imports no Rapthor, Prefect or LSMTool in library code. |
| Agent prepares, human pushes | Add Rapthor backend selection, fallback and dual-run reporting in Rapthor. | A Rapthor patch against the current pin selects the backend by flag, respects the caller's resource budget, and reports dual-run differences. |
| Agent, human dispositions | Measure Rapthor-profile agreement. | Retained/rejected agreement against both PyBDSF references on true/apparent, bright, extended, edge, masked, sparse and crowded populations. Choose `compact` only with ≥99.5% overall agreement and every safety stratum passing; otherwise `continuum`. |

### M4 — Deployment performance gate

| Owner | Task | Done when |
| --- | --- | --- |
| Human freezes, agent proposes | Freeze the initial deployment envelope. | Sizes, workloads and resources match Rapthor's production sectors on the D2(a) host. |
| Agent | Run matched complete `filter_skymodel` benchmarks and optimize until both runtime gates pass. | Both ratios and their upper one-sided 95% bounds pass on every envelope cell; memory and Hebog-curve non-regression pass; the non-regression campaign passes. Native code enters only through the native-code gates and an accepted ADR. |

### M5 — Scale on the test cluster

| Owner | Task | Done when |
| --- | --- | --- |
| Agent proposes, human approves | Amend the scalability contract to the demonstrable topology. | `config/benchmarks/phase-0-scalability.json`, the performance and scalability contracts page and the `test-scalability` recipe describe 1, 2, 5 and 10 nodes of the recorded hardware and the image ladder below. The 50, 100 and 200-node gates are kept as design targets, not deleted. |
| Agent, human approves store | Qualify a Zarr store and restart/recovery path on the cluster's shared storage. | Atomicity, concurrent owned-chunk writes, codec and chunk geometry, missing chunks, cold/warm throughput and injected failures pass within an admitted memory budget. |
| Agent, human approves each raise | Raise the envelope through the real and generated ladder. | The ladder is LoTSS-DR3 mosaics (about 17,700²), SDC1 (32,768²), the ELAIS-N1 HD mosaic (22,500², 45,000², 90,000²), a generated SKA-Low image and generated 100,000² truth. Both sides of new crossovers are measured. Science on large images uses SDC1 truth, the LoTSS-DR3 PyBDSF catalogues and RMS/mask maps, the per-facet HD PyBDSF catalogues, generated truth and global invariants, as in ADR-005. |
| Human provides nodes, agent runs | Run the controlled node ladder. | Strong scaling on the 90,000² mosaic and generated 100,000² truth at 1, 2, 5 and 10 nodes; weak scaling from 22,500² on 1 node to 45,000² on 4 nodes, and size scaling across the same-field 22,500², 45,000² and 90,000² mosaics at 10 nodes. Results are invariant, and the amended runtime, task-count, scheduler-overhead, memory, spill and efficiency gates pass. |
| Agent | Bound behaviour beyond 10 nodes. | On the 10 nodes, runs with at least 200 worker processes measure scheduler load, graph size, reduction depth and driver memory. A scaling model fitted to the 1–10-node results predicts 50–200-node efficiency, with its uncertainty stated in release notes. |

### M6 — Qualification and 1.0.0

| Owner | Task | Done when |
| --- | --- | --- |
| Human | Freeze the 1.0.0 candidate. | Science, profile and envelope are fixed; later changes restart only the affected qualification rows. |
| Agent designs, human approves | Run candidate-bound parity/retention with fresh held-out and public-survey data. | Every binding endpoint passes under a prospectively reviewed contract, population and power design, including the D4 limitations and the LOFAR, SKA-Mid and SKA-Low families in the 1.0.0 definition. Closed failed campaigns are never reused as confirmation. |
| Human runs in Rapthor, agent supports | Operational soak behind the Rapthor flag. | Dual runs on production data show no unexplained difference, retry and restart work, and the fallback is exercised. |
| Agent assembles, independent reviewers accept | Readiness packet and acceptance. | The packet binds science, Rapthor profile, performance, scale, portability, security, licensing, packaging and current documentation, with separate radio-astronomy and engineering acceptance. |
| Human | Release 1.0.0. | Release Please produces 1.0.0 (for example through a `Release-As: 1.0.0` commit footer) and the package publishes to PyPI. |

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| The 8–20× gap on real images does not close with NumPy/SciPy and Numba. | M4 fails. | Profile first; attack algorithmic cost before constant factors; use the native-code gates only for a profiled kernel. Report the gap honestly at each milestone. |
| Extended association cannot be made exactly tile-invariant. | M2 stalls or changes science. | Design ownership and boundary summaries before code; test analytic shells and filaments crossing corners early; escalate a scientific trade-off to the human rather than weakening invariance silently. |
| Scheduler, reduction or storage bottlenecks appear only above 10 nodes. | A later deployment at 100+ nodes fails or scales poorly. | Tests with 200+ worker processes, task-count and reduction-depth bounds, a scaling model, and an explicit "not demonstrated" statement in release notes. |
| Large public images have minimal or non-standard headers; the HD mosaic is published "for browsing only". | Anchors cannot run unmodified, or their science comparison is weak. | Check headers before downloading; supply missing metadata explicitly; use per-facet HD images and catalogues for science; keep the generated 100,000² image as the fallback scale anchor. |
| No large public SKA-Low image exists. | SKA-Low scale and science rely on simulations and MWA precursor data. | OSKAR simulation with generated truth, GLEAM-X DR1 with its PSF maps and Aegean catalogues, and SKA-Low science-verification data once released (expected from 2027). |
| Rapthor and LSMTool change frequently. | Adapter, contract and benchmark churn, or a backend that only works on a stale revision. | Pin the latest commits when M3 starts (D3). Move both pins forward deliberately, not continuously: before the Rapthor patch, before the M4 benchmarks and at the M6 freeze. At each move, rerun the contract audit, the acceptance scenarios and the Rapthor-profile agreement check, and record the revisions in `LOG.md`. |
| Scientific campaigns absorb the schedule again. | Performance and scale slip. | One reusable campaign command, preflight resource checks, endpoints limited to Rapthor-consumed fields for non-regression, powered qualification once at M6. |

## Scientific gates

Analytic or injected truth is primary. Released PyBDSF is the Rapthor
compatibility reference; pinned PyBDSF `master` is independently binding.
Aegean is binding for applicable compact and Gaussian populations. No finder is
scientific truth.

- Each campaign uses its own prospectively reviewed endpoint registry and
  decision contract. Choose a whole incumbent before viewing results; never
  combine historical best values into a synthetic comparator.
- Require every applicable relative PyBDSF, Aegean and incumbent Hebog
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
from LOFAR, SKA-Mid and SKA-Low (precursor or simulated SKA-Low data until
SKA-Low data are public), plus at least one other instrument. Compare Serial before alternate executors and
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
| Source-free RMS-map difference, median / p95 | ≤2% / 5% |

## Performance and scale gates

For supported Rapthor deployment, matched complete-step median ratios and
their upper one-sided 95% bootstrap confidence bounds must satisfy:

```text
Hebog / released PyBDSF <= 0.50
Hebog / pinned PyBDSF master < 1.00
```

Scientific eligibility precedes performance acceptance. These are minimum
deployment gates, not a reason to stop optimizing or to hold an experimental
standalone release.

- Maintain 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000 and 100,000-square
  anchors (with the real images below alongside the nearest anchor), sparse, normal and dense-extended workloads, and both sides of
  every measured crossover. Gate early deployment on its frozen envelope;
  1.0 qualification needs the whole matrix.
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
- Component budgets, including the four-core 6-second multiscale budget at
  3,000 pixels, remain diagnostic; complete filtering decides deployment.
  Exact budgets are in the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md).

### Reference images

Public candidates found on 16 September 2026. Dimensions marked "inferred"
come from file sizes or catalogue metadata; check each header before a large
download. No image data or dataset belongs in Git.

| Family | Image | Size | Use | Reference |
| --- | --- | --- | --- | --- |
| LOFAR | LOFAR-HD ELAIS-N1 mosaic, 0.4/0.2/0.1″ pixels | 22,500², 45,000², 90,000² (32.4 GB) | Largest real scale anchor; same-field size ladder | Per-facet PyBDSF catalogues |
| LOFAR | LoTSS-DR3 HEALPix mosaics (1,571) | 14,390–17,752² | Science and throughput | PyBDSF catalogue plus per-mosaic RMS, residual and mask maps |
| LOFAR | LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky pair | about 14,000² (inferred) | Closest public match to Rapthor's two inputs | PyBDSF catalogue and maps |
| SKA-Mid | SDC1 B1/B2/B5, 8/100/1,000 h | 32,768² (4.3 GB each) | Scale with truth | Full truth catalogues |
| SKA-Mid | MeerKAT MIGHTEE DR1 XMM-LSS; SMGPS tiles (Galactic, multi-plane) | about 20,900² (inferred); 7,500² | Real precursor science; header variety | PyBDSF; Aegean |
| SKA-Low | MWA GLEAM-X DR1 mosaics | not checked (2.8 GB) | Precursor science with a PSF that varies across the field | Aegean catalogues and PSF maps |
| SKA-Low | OSKAR simulation (generated) | up to 100,000² | Scale and truth, pending public SKA-Low data | Generated truth |
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
