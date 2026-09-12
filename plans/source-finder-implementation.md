# Hebog implementation plan

This is the authoritative forward plan for Hebog. Material execution history,
campaign identities, detailed measurements, and superseded decisions live in
[`LOG.md`](../LOG.md); reviewed contracts and evidence records retain their
exact machine-readable values. This document keeps only durable decisions,
current status, acceptance gates, and work still required.

## 1. Objective

Build a maintainable, scheduler-independent radio-continuum source finder that:

- reproduces the scientifically relevant PyBDSF behaviour and products used by
  Rapthor without copying PyBDSF implementation code;
- provides a trustworthy general continuum profile for compact and extended
  sources, while allowing a separately qualified compact profile;
- reduces the median wall time of Rapthor's complete `filter_skymodel` step by
  at least 50% relative to Rapthor's released PyBDSF version and also
  outperforms the pinned PyBDSF `master` reference;
- processes images up to 100,000 by 100,000 pixels through bounded tiles on an
  existing Dask cluster of 100 to several hundred workers; and
- remains usable by non-Rapthor workflows without importing Rapthor, Prefect,
  LSMTool, or a concrete scheduler.

The release performance gates are:

```text
Hebog median filter_skymodel wall time / released PyBDSF median <= 0.50
Hebog median filter_skymodel wall time / PyBDSF master median   < 1.00
```

Both comparisons use matched inputs, configuration, outputs, resources, and
hosts. Their one-sided 95% bootstrap confidence bounds must satisfy the limits.
Scientific eligibility is decided before runtime; faster execution cannot
compensate for failed science in an acceptance decision. Profiling and
optimization may use an explicitly unqualified, known-issues development
baseline; its timings do not establish replacement eligibility.

## 2. Scope and durable boundaries

### In scope

- FITS ingress; beam, WCS, unit, background, and local-RMS handling.
- Seed/grow detection, connected islands, compact deblending, measurements,
  selective Gaussian fitting, and calibrated available uncertainties.
- Residual multiscale detection, extended support, cross-scale reconciliation,
  and original-image photometry.
- Versioned catalogue, RMS, source-filtering mask, provenance, and diagnostic
  products compatible with the Rapthor/LSMTool boundary.
- Deterministic serial, local, and existing-client Dask execution.
- Zarr-backed bounded intermediates, restartable products, and hierarchical
  reconciliation for large images.
- Released and pinned-`master` PyBDSF comparison, plus Aegean and appropriate
  public/challenge comparators for their declared scientific scope.

### Out of scope for initial production

- Every PyBDSF option or output format.
- Polarization-specific analysis not exercised by Rapthor.
- GPU execution or a speculative plugin framework.
- Reproducing undocumented PyBDSF defects.
- Requiring a distributed cluster for work that fits safely in one tile.

### Phase ownership

- Phase 5 owns scheduler-independent multiscale science, extended-island
  completion, cross-scale ownership, bounded tiling semantics, incremental
  performance, and the final campaign/severity review. The 2026-09-11 decision
  separates development closeout with known issues from scientific readiness;
  the latter still requires its parity, retention and validity gates.
  Release Please owns release workflow after release eligibility, not merely
  development closeout. Phase 5 does not
  prepare a version, tag, changelog, or release artifact. Only a narrow
  release-blocking production audit belongs before qualification and closure.
- Phase 5.5 owns post-release removal or consolidation of superseded campaign
  wrappers, one-use freezers, historical lifecycle tests, and other
  development-only tooling. It does not change `src/hebog/`, scientific
  products, or closed evidence. It is not a prerequisite to the newly
  prioritized runtime/scalability engineering work.
- Phase 6 owns the restricted Rapthor profile decision, Rapthor integration,
  complete dual-PyBDSF performance, and the earliest useful Rapthor-integrated
  experimental release once every minimum gate passes.
- Phase 7 owns production executor planning, deployment-store qualification,
  hierarchical Dask graphs, spill/recovery, facility-scale execution, and
  continued post-release optimization.
- Phase 8 owns production hardening and `1.0` readiness review.

## 3. Acceptance gates

### 3.1 Scientific gates

Analytic and injected truth are the primary scientific oracles. Released
PyBDSF is the current Rapthor compatibility oracle; pinned PyBDSF `master` is a
second binding reference. Aegean is binding for applicable compact, blended,
and Gaussian-component populations. No single finder is scientific truth.

The historical Phase 4/5 contract required Hebog to pass every applicable
absolute gate and be non-inferior to each binding reference on every governed
metric and stratum. Results were conjunctive: one population or metric could
not compensate for another. Predeclared one-sided confidence intervals
determined non-inferiority; a worse point estimate with an inconclusive
interval was not an improvement.

That conjunctive contract remains binding for every campaign and replay
frozen through terminal-feature persistence ledger `a9b4d57e...`. Those
decisions are immutable and must not be retrospectively rescored. Before the
next full Phase 5 replay, however, freeze a new prospective decision contract
that distinguishes the minimum replacement requirement from later absolute
scientific improvement:

1. **Binding PyBDSF parity.** Require paired non-inferiority to both PyBDSF
   references on every applicable governed metric and stratum, not only those
   later shown to be consumed directly by Rapthor. Retain every applicable
   compact/Aegean contract. An underpowered or inconclusive binding comparison
   does not demonstrate parity and must receive sufficient evidence before
   promotion.
2. **Binding Hebog quality retention.** Prospectively select one frozen
   incumbent from the best closed like-semantics Hebog candidates considered
   as whole candidates, then require non-inferiority to it on every governed
   metric and stratum. Small metric movement inside its predeclared practical
   non-inferiority margin is tolerable when the candidate remains above every
   applicable absolute acceptance threshold and both PyBDSF references, a
   scientifically related measure improves substantially, and the complete
   trade-off is reported. This is not compensation for a material regression:
   the frozen confidence rule must still rule out loss beyond the endpoint's
   practical margin. A trade-off may not be invented after results are viewed,
   hide a failed endpoint, or change a threshold, margin, comparator, or gate.
3. **Longer-term absolute improvement objectives.** Continue to report the
   existing ambitious absolute truth targets and every morphology, scale,
   boundary, and noise stratum, but do not make those numeric targets a
   compatibility blocker once both reference-parity and Hebog-retention gates
   pass. Product validity, finite measurements, deterministic execution,
   schema/provenance integrity, and other non-performance safety invariants
   remain binding.

The prospective contract must retain all governed relative checks, keep their
practical non-inferiority margins fixed, define how additional evidence closes
underpowered comparisons, and be reviewed before a new candidate or replay
identity is frozen. It may not select metrics, margins, strata, or baselines
from the candidate's viewed values. The same prospective contract then governs
the cumulative replay and fresh held-out qualification. Until that review is
accepted, the existing stricter contract remains the active gate.

The prospective records are now frozen but deliberately inactive. Endpoint
registry `phase-5-prospective-science-endpoint-registry.json` (SHA-256
`095354bc...`) names 383 endpoints: 225 compact binding, 143 Continuum
binding, and 15 Continuum longer-term objectives. It expands to 1,187
co-primary comparisons: 338 against each PyBDSF reference, 143 applicable
compact comparisons against Aegean, and 368 against the single incumbent
Hebog candidate. Decision contract
`phase-5-prospective-science-decision-contract.json` (SHA-256 `f70f3213...`)
binds the intersection-union rule and historical immutability. It selects
whole candidate `85d5807...`, not a per-endpoint envelope, and requires an
exact paired reexecution because its realization-level products were not
retained. Status remains `frozen-for-human-scientific-review`, `active=false`,
and every execution, identity-freeze, qualification, tuning, rescoring,
cutover, and release authorization remains false.

The prospective contract is scientifically confirmatory only when all of the
following are fixed before candidate results are viewed:

- one versioned endpoint registry naming every metric, stratum, direction,
  population, unit, comparator, applicability rule, practical margin, and
  missing-output outcome;
- one closed incumbent Hebog ledger for like-semantics retention, or one named
  incumbent per explicitly different semantic profile. Do not construct an
  unattainable per-endpoint envelope by selecting the best value from different
  historical candidates after the fact. For the current terminal-cycle repair,
  `85d5807...` is the predecessor whose accepted parent-construction gains must
  be retained while PyBDSF parity remains independently binding;
- the independent sampling unit and paired resampling method. Resample whole
  input realizations or observational units, not individual sources or pixels
  whose within-image dependence would create pseudoreplication;
- a prospective power calculation for every binding endpoint using its frozen
  margin, planning variance, event frequency, and smallest governed stratum.
  Enlarge or redesign the population before the one-look campaign when a
  binding comparison cannot be resolved; do not demote it or add cases after
  inspecting candidate results. Report both marginal endpoint power and a
  reviewed dependence-aware estimate or conservative bound for the probability
  that all co-primary endpoints pass; and
- one intersection-union decision: promotion passes only when every binding
  non-inferiority hypothesis passes at its predeclared one-sided level. Because
  all co-primary hypotheses must pass, no cross-endpoint multiplicity
  adjustment is required for that global non-inferiority claim. Any separate
  superiority claim or selection of a favourable subset requires a
  prospectively specified multiplicity procedure or remains descriptive.

Planning variance is a design input, not an additional observed-data gate.
The final non-inferiority decision uses the frozen estimator and the confidence
limit computed from the observed paired realization-level variation. Exceeding
the planning variance is recorded as an assumption deviation and informs the
next prospectively sized campaign; it does not override a confidence limit that
already excludes the practical margin. Conversely, a confidence limit that
crosses the margin cannot pass merely because observed variance stayed below
plan. The historical evaluators and their decisions remain immutable, but the
prospective evaluator must implement and test this separation before another
full replay identity is frozen.

"All checks" means all scientifically comparable checks in the frozen
registry. A metric may be marked not applicable only before viewing the
candidate and only because the two products have incompatible scientific
semantics, not because power or performance is inconvenient. Compact shape,
size, and position-angle checks and moment-equivalent extended-source checks
remain binding wherever the truth and comparator definitions align.

The durable cross-project and absolute improvement targets are:

| Metric | Gate |
| --- | ---: |
| Rapthor retained/rejected components | at least 99.5% agreement |
| Reference sources recovered at SNR >= 10 | at least 99% |
| SNR >= 5 recovery | report compatibility curve; no single pass fraction |
| False-discovery rate | no more than 1 percentage point above reference |
| Median position difference, isolated SNR >= 10 | at most 0.02 beam |
| Position p95, isolated SNR >= 10 | at most 0.10 beam |
| Median peak-flux difference, isolated SNR >= 10 | at most 2% |
| Peak-flux p95, isolated SNR >= 10 | at most 5% |
| Median integrated-flux difference, isolated SNR >= 10 | at most 5% |
| Integrated-flux p95, isolated SNR >= 10 | at most 10% |
| Source-free RMS-map median difference | at most 2% |
| Source-free RMS-map p95 difference | at most 5% |

Exact Phase 4/5 endpoint populations, absolute limits, practical margins,
variance rules, and confidence methods remain frozen in `config/contracts/`.
They cover compact, blended, extended, morphology, scale, SNR, edge,
invalid-pixel, varying-noise, tile-boundary, and tile-corner strata.
Under the prospective contract, every applicable relative PyBDSF, Aegean, and
incumbent-Hebog form remains binding. The absolute numeric values remain
reported longer-term targets, except for non-performance validity invariants
and the separately frozen Phase 6 Rapthor profile decision.

Additional rules:

- Mask precision, recall, and intersection over union are measured over valid
  pixels; island matches, splits, merges, and duplicates are reported
  separately so background pixels cannot hide errors.
- Detection or wavelet coefficients establish support and provenance only.
  Flux, centroid, shape, and uncertainty use the reconciled support and
  original background-subtracted pixels.
- Compact components, grouped sources, support/islands, and sky-model
  components are distinct governed populations.
- Catalogue shape, size, and position angle are evaluated only against a
  semantically aligned truth or comparator definition; incompatible fitted and
  moment-based records are explicit unavailable outcomes rather than false
  matches or silent passes.
- Low-SNR threshold crossings are reported as completeness and reliability
  changes rather than hidden as unmatched rows.
- Serial and executor results must satisfy the tighter deterministic Hebog
  contract before comparison with another finder.
- Qualification evidence is immutable and one-look. A failed campaign may be
  diagnosed but not rescored, tuned, or reused as confirmation.

### 3.2 Performance gates

- Use at least five measured repetitions after warm-up and add repetitions
  when confidence intervals are inconclusive.
- Apply the dual-PyBDSF ratios at every gate-designated size both references
  can process.
- Retain a reviewed Hebog curve across all supported sizes. Hebog-on-Hebog
  non-regression passes only when the upper one-sided 95% confidence bound for
  the new/previous median ratio is at most `1.05`. A lower bound above `1.05`
  is a confirmed regression; an interval spanning the margin is underpowered,
  not a pass. An explicit reviewed trade-off may change the supported
  performance envelope, but it cannot be described as non-regression.
- Measure complete paths, including FITS I/O, products, orchestration, and
  filtering. Kernel-only speedups are diagnostic.
- Peak worker and aggregate memory may not regress by more than 10% against
  either PyBDSF comparator without an explicitly approved throughput trade-off.
- The Phase 5 incremental multiscale stage has a four-core 3,000-square median
  budget of 6.0 seconds; the complete Rapthor gate remains decisive.

### 3.3 Scalability and operational gates

- No worker may require a complete large plane or unbounded island membership.
- Memory is bounded by admitted tile cores, stage halos, workspaces, caches,
  summaries, and shards.
- Graph size scales with tiles and scientific stages, not pixels, RMS windows,
  or small islands; global reductions are hierarchical.
- Results are invariant to partition origin, tile and batch shape, worker
  count, task order, retry, and supported executor.
- The 100,000-square qualification completes on 100 and at least 200 workers
  within frozen memory, spill, scheduler, recovery, runtime, and scaling gates.

## 4. Public contracts and architecture

### 4.1 Public API and profiles

The scientific API remains scheduler independent:

```python
import hebog

result = hebog.find_sources(request, config, executor)
```

Requests contain paths, identifiers, immutable scientific configuration, and
small serializable metadata. Results contain product paths, counts, timings,
schema versions, and small provenance records. Neither boundary contains open
files, mutable full images, scheduler clients, or workflow state.

The Phase 5 public scientific interface must export `find_sources` from the
top-level `hebog` package and implement this complete path from an installed
wheel. A radio astronomer must not need an internal stage API, Rapthor,
Prefect, LSMTool, or a private scheduler to analyse a supported FITS image.
The documented bounded path uses the deterministic Serial executor; callers
may explicitly supply another supported executor, and Hebog never creates a
Dask cluster implicitly.

One request represents one scientific image analysis and returns one
catalogue, RMS image, source-filtering mask, and diagnostic record. The
pipeline-neutral core exposes explicit `compact` and `continuum` profiles:

- `continuum` is the intended general-community default after qualification;
- `compact` may be selected only explicitly and may not be described as
  extended-source complete.

The Rapthor adapter owns workflow defaults, legacy filenames, flat-noise and
true-sky task composition, LSMTool filtering, and failure translation.

### 4.2 Scientific design

The reviewed continuum direction is a transparent hybrid of established radio
source-finder practice:

1. Preserve the qualified compact branch.
2. Detect residual extended emission with B3-spline à trous smoothings and
   calibrated scale noise.
3. Reconstruct adjacent-scale signal and grow morphology-independent support.
4. Reconcile compact and multiscale evidence deterministically.
5. Measure accepted sources on original background-subtracted pixels.

This resembles PyBDSF's residual à trous path and Selavy's multiscale island
processing while retaining explicit segmentation/provenance useful for
irregular emission. Aegean remains a compact/Gaussian comparator, not an
extended-mask oracle. The literature and comparator rationale are retained in
the [Phase 5 filter decision](../docs/reference/phase-5-filter-selection.md).

### 4.3 Execution and storage

Scientific functions operate on bounded NumPy arrays with explicit core,
halo, and global coordinates. `SerialExecutor` is the deterministic oracle;
local and Dask executors implement the same contract. Hebog never starts a
private Dask cluster or multiprocessing pool by default.

Zarr v3 is the sole intermediate image-plane backend; FITS remains ingress and
final compatibility output. Small work uses one Zarr chunk. Workers write
distinct owned chunks, missing chunks fail closed, and publication succeeds
only after the expected chunk set and checksums validate. Adding another
intermediate backend requires an ADR amendment.

Large-image stages use deterministic non-overlapping output cores, the
smallest reviewed stage halo, bounded summaries, and hierarchical
reconciliation. Catalogue shards merge in stable global order without
gathering an unbounded source set on the scheduler or one worker.

### 4.4 Dependency and acceleration policy

Dependencies point inward: algorithms and domain records know nothing about
Rapthor, Prefect, LSMTool, or concrete schedulers. FITS, adapters, executors,
and materialisation remain explicit boundaries. Imports are inert.

Prefer NumPy/SciPy, then Numba for profiled custom loops. New native code
requires a reviewed ADR plus all of these unless it unlocks a failed memory or
scalability requirement:

- at least 10% of relevant end-to-end time remains in the candidate kernel;
- the native kernel is at least 2x faster; and
- the complete path improves by at least 5% without scientific regression.

Native code remains optional until supported wheels, source builds, safety,
licensing, fallback, and scientific-equivalence checks all pass.

### 4.5 Product compatibility

The versioned Rapthor boundary preserves reviewed catalogue names, units,
coordinates, source/component grouping, null conventions, RMS shape/WCS/unit,
mask semantics, empty results, and errors. The internal schema may remain
cleaner than PyBDSF but every conversion is explicit and tested.

## 5. Evidence and testing

### 5.1 Dataset matrix

Every dataset has checksums, provenance, beam/WCS metadata, generator version,
redistribution status, and exactly one role: `development`, `regression`, or
`qualification`.

The governed matrix includes:

- analytic and injected compact sources over SNR 3--100, density, beam, WCS,
  and pixel scale;
- close blends and multi-component islands;
- diffuse Gaussians, filaments, shells/curves, and mixed compact/extended
  emission at several beam-normalized scales;
- edges, invalid pixels, masks, negative bowls, varying noise, bright-source
  artefacts, tile boundaries, and tile corners;
- representative Rapthor images and complete `filter_skymodel` calls;
- 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000, and 100,000-square
  performance anchors, plus both sides of measured crossovers; and
- redistributable public/challenge cut-outs from at least two telescope
  families, with appropriate finders used as scoped comparators.

Qualification populations and gates are frozen before candidate tuning.
Public/private production data use environment-neutral dataset identifiers;
generated truth records its generator configuration as well as its seed.

### 5.2 Oracle and test order

Use the strongest independent oracle available:

1. analytic truth;
2. mathematical/metamorphic properties;
3. deterministic Hebog serial execution;
4. frozen released PyBDSF products;
5. frozen pinned-`master` PyBDSF products; and
6. end-to-end Rapthor decisions.

The comparison machinery is tested independently with known assignments,
ambiguous blends, unmatched rows, coordinate wrapping, unit conversion,
masks, and RMS maps. Frozen reference products are regenerated only through a
reviewed command that records inputs, configuration, tool revisions, and
checksums.

Production behaviour follows test-first red/green/refactor where practical:
analytic and property tests, deterministic serial implementation, boundary
and failure cases, executor conformance, scientific comparison, then
performance.

### 5.3 Test lanes

| Lane | Purpose | Normal trigger |
| --- | --- | --- |
| Unit/property | Kernels, schemas, matching, invariants | every commit |
| Contract | Public I/O and executor behaviour | every commit |
| Integration | FITS, Zarr, and local/in-process Dask boundaries | pull request |
| Equivalence | Redistributable released/master PyBDSF comparisons | pull request |
| Public interface | Installed-wheel FITS-to-products path and errors | milestone/release |
| Acceptance | Rapthor-facing behaviour | pull request |
| Qualification | Held-out scientific matrix | milestone/release |
| Benchmark | Components and complete Rapthor paths | controlled runner |
| Scalability | Out-of-core and 100--200-plus-node execution | facility runner |

Portable CI does not enforce wall time, download private data, or require a
cluster. Controlled runners record all repetitions and resource/topology
metadata. Changed production behaviour requires focused tests, `just coverage`,
`just check`, relevant equivalence/integration lanes, documentation validation,
and `just pre-commit` before a local commit.

## 6. Current state

### 6.1 Completed phases

Detailed evidence is linked from `LOG.md`; these are the durable outcomes.

| Phase | Durable outcome | Remaining boundary |
| --- | --- | --- |
| 0 | Froze Rapthor contracts, released/master PyBDSF baselines, datasets, schemas, and architecture decisions. | Facility-scale evidence remains Phase 7/8. |
| 1 | Delivered bounded FITS/Zarr I/O, partition ownership, restartable products, and pipeline-neutral records. | Deployment-store qualification remains Phase 7. |
| 2 | Delivered vectorised background/RMS estimation, adaptive regions, partition invariance, and executor parity. | Preserve the reviewed curve and science gates. |
| 3 | Delivered deterministic detection, labelling, compact deblending, masks, and explicit extended-island deferral. | Deferred/extended work is Phase 5. |
| 4 | Delivered compact measurement, SciPy fitting, uncertainty calibration, catalogue construction, and compact regression evidence. | The compact branch remains subject to every later regression gate. |

Phase 4U is the compact regression baseline: its fresh qualification passed
77 binding absolute gates, 20 paired endpoints against each PyBDSF reference,
and five stronger-Hebog envelopes. Earlier Phase 4/4R/4S/4T failures remain
closed historical evidence and were not rescored.

### 6.2 Phase 5 decisions and latest evidence

**Current decision — 2026-09-12:** The bounded Gaussian-validity repair and
its validation are complete. Phase 5 development remains open for the final
cumulative campaign and a bounded severity review. Then close development
unless serious issues are found; defer other scientific improvements and
prioritize runtime and scalability. Apply the
[pre-launch severity policy](../docs/reference/phase-5-v13-followup-review.md#later-decision-final-campaign-then-development-closeout).
Keep every original scientific result/gate unchanged. Development closure
is not scientific qualification, a PyBDSF-parity claim, release or cutover.
Known incorrect supported outputs remain release blockers, and the PyBDSF
fallback remains. This decision supersedes the earlier all-science-first
phase sequencing, not its immutable evidence or scientific requirements.

**Next task (latest user approval):** monitor the isolated two-worker v14
cumulative replay, then verify and investigate its terminal result.
Candidate `cf6d9da...` passes F1/F3 and completes the separate 24-input screen;
the screen retains the same 49 warnings, not a powered parity verdict.
The live disk reserve is met, the exact immutable execution is frozen and
both independent and launch-time exhaustive preflights pass. Managed session
`81018` is making capture progress, with hourly monitor
`monitor-current-replay` active. F2's broader
association work remains deferred. Do not launch a duplicate or silently
reduce the population/reserve. A subsequent scientific repair or fresh
qualification requires a separate prospective decision, not an automatic
loop after every failed comparison. The complete Rapthor-consumer acceptance
check belongs to Phase 6 integration, not an additional Phase 5 development
closure prerequisite; release and cutover requirements remain unchanged.

Scientific readiness is incomplete. The latest source-aligned
sentinel `ca03240d...` completed normally but failed 18 of 42 cells for
candidate `95cfc76...`. Earlier development and cumulative passes remain
scoped historical evidence, not readiness for that candidate or its successor.
Deferred scientific work is recorded in Section 7, supported by
the [source-catalogue science audit](../docs/reference/phase-5-source-catalogue-science-audit.md).
The multiscale implementation, combined products, bounded execution proof,
public interface, and incremental performance evidence already exist.
Candidate `0b9e132...`, source tree
`11307db0...`, and configuration `2c907949...` passed the 144-image
seed-disjoint support-linkage replication across all 12 binding geometry
groups with exact Serial/existing-Dask agreement and sealed all 2,400
cumulative products as `195a5a36...`. Those products remain immutable
historical evidence, but they no longer qualify the next candidate: a
post-refresh catalogue review found that the public composition preserved
connected support while failing to partition ordinary multi-peak parents into
their Gaussian components. Candidate `6166779...` corrected that partition,
but its first diagnostic notebook refresh found one further fail-closed edge:
a multiscale-admitted parent can lack a direct-residual peak above the stricter
deblending seed threshold. Successor candidate `3ed6086...` conservatively
retains that parent as one component with unchanged support rather than
manufacturing a split or aborting the image. A later notebook case then exposed
an older boundary-ownership composition defect: direct-derived publication
support and expanded measurement support could independently resolve the same
equidistant recovered pixel to different existing owners. The prospective
correction keeps the publication footprint unchanged while inheriting the
authoritative measurement owner and still rejects genuinely unowned support.
The remaining scientific-readiness gates (not all prerequisites to the
development handoff) are the
prospective fast lane, a fresh cumulative replay/evaluation, seed-disjoint
held-out qualification, final engineering/public-interface confirmation,
a narrow production audit, documentation, and packet-bound independent
acceptance. Broad historical-tooling cleanup is explicitly post-release Phase
5.5 work and is not a Phase 5 scientific exit gate.

The public/challenge one-look remains closed failure evidence: decision
`954077e9...` fails SDC1 completeness, reliability, and flux-error gates, and
independent review `320f57f5...` attributes material defects to
source-association semantics and deep-image overmerging without authorizing
tuning or rescoring. The first corrected cumulative ledger `1ac6deb2...`
retains compact science but fails with 37 Continuum like-semantics regressions.

The source-association candidate then attempted to address those regressions
prospectively. After repairing measurement completeness and the compiler's
single-label assumption, evaluation-only completion published terminal ledger
`6b2aa4de...` without rerunning the 2,400 candidate products. Compact passes,
but Continuum still has 44 failures and the same 37 regressions. Source-union
matching changed no endpoint status; component fragmentation, source-level
measurement, and mask-support admission remain open defects.

Pre-review `528f18a6...` accounts for every failure and its approved
fixture-first correction is implemented as candidate `42c75f4...`. The
frozen replay completed all 2,400 candidate products. After an evaluation-only
dispatch repair, immutable revision `66352e7...` published terminal ledger
`84fbb3a1...` from the verified products without candidate reexecution.
Compact remains green, but Continuum remains at 89 passes, 44 failures, 10
underpowered endpoints, and the same 37 like-semantics regressions. The
source-reconstruction candidate changed 48 point estimates only at negligible
numerical scale and changed no endpoint status or split/duplicate topology.
Approved review `c1a92bd2...` led to a prerequisite repair that separates
direct hierarchy identity from recovered measurement ownership and emits
activation telemetry. Real-scale fixture evidence then isolated a second
blocker: four analytic shell lobes remain four disconnected exact features at
every retained scale, so exact-overlap lineage tracking cannot construct the
shared source parent. Non-executable review `b5d89bdc...` now governs that
parent-construction problem. The approved implementation and replay identities
are now frozen as candidate `5f2b098...` and review `e615da00...`. Its first
authorized process stopped before candidate execution: after retained-reference
verification, wrapper `9bf44c09...` skipped the measurement-repair predecessor
layer and raised `_load_current_wrapper`. No scratch or ledger was created.
Repair review `89327ae5...` now binds the wrapper-only traversal correction and
expanded no-write execution-composition verification. Decision `0349fdc2...`
consumes the explicit restart instruction for one unchanged replay; all
scientific identities remain fixed. That replay completed all 2,400 candidate
products, but compilation stopped before an atomic ledger because the
evaluator tried to reconstruct direct-seed component identities from recovered
measurement-owner labels. All 1,600 Continuum shards omit the in-memory source
association record, so exact membership cannot be recovered from the preserved
files alone. Pre-review
`phase-5-public-finder-source-hierarchy-parent-construction-association-provenance-repair-pre-review`
therefore limits the repair to explicit association provenance, immutable
product verification, and separately approved sidecar reconstruction and
evaluation completion.

Subsequent parent work is now terminal evidence. Candidate `85d5807...`
materially improved the source-parent path but failed with 35 Continuum
endpoints and 30 regressions. Terminal-feature candidate `3d080f7...` then
published ledger `a9b4d57e...`: compact passes, but Continuum regresses to 39
failures and 33 regressions. The fail-fast correction ladder subsequently
opened publication-scale candidate `937737d...`; full ledger `a9c6ed28...`
improves to 31 Continuum failures and 26 regressions but remains terminally
failed under its original wrapper. Prospective root-cause review `77bd4b82...`
finds that all stored PyBDSF comparisons are inside margin and no incumbent
point estimate moves beyond margin, but exact paired incumbent evidence is
absent. Those historical evaluator and attribution blockers were subsequently
repaired prospectively. The current work is the exact cumulative candidate
stage and the closeout sequence in Section 7; none of these failed decisions
is an instruction to rerun or rescore a closed campaign.

## 7. Delivery plan

### Phase 5: multiscale and extended emission

**Status: open; R6 cumulative terminal `7146f2e8...` failed scientifically
on 2026-09-09 for candidate `db8936b...`.** The evaluation-only continuation
exited zero and preserved all 808 reused inputs, but its 1,187 binding
comparisons contain 885 passes, 288 failures and 14 underpowered results.
Both PyBDSF references, Aegean and incumbent retention have failures; all five
binding safety checks pass. R0--R5 fixture completion is not scientific
qualification. The separate
[root-cause review](../docs/reference/phase-5-r6-root-cause-review.md)
is complete (2026-09-09); its prospective repairs and calibration gates below
remain pending. Preserve the terminal before any replacement candidate,
replay or fresh sentinel.
Do not retry or rescore this completed scientific failure, transfer the
historical uncertainty acceptance, or qualify later notebook repairs from it.
The [dated terminal snapshot](../docs/reference/phase-5-campaign-overview.md#2026-09-09-r6-cumulative-terminal-scientific-failure)
records the exact result. The following chronology remains historical.

The earlier version-8 fast lane
passed and its cumulative evidence was accepted for progression with one
explicit incumbent-uncertainty exception. The earlier production audit did
not establish the source-level scientific correctness now falsified by the
sentinel and bounded analytic review. Existing multiscale implementation,
combined products, execution proofs, and incremental performance evidence
remain useful but must be revalidated where the replacement changes them.
The seed-disjoint 144-image repair replication passed all 12 binding geometry
groups, its trigger seam, and Serial/existing-Dask invariance. Candidate
`0b9e132...` sealed the exact 800-compact/1,600-Continuum cumulative product
set as `195a5a36...`, but that result is superseded for acceptance by the
confirmed component-topology defect. The corrected public path keeps one
connected support island and one associated source where appropriate while
publishing every admitted Gaussian component. Its analytic, branch-coverage,
public Serial/existing-Dask, compact-equivalence, documentation, notebook, and
installed-wheel gates pass. Fast-lane terminal `a274888d...` binds identity
`29e6f247...`, reuses the seed-disjoint 144-case protocol, and passes all 12
binding geometry groups, the trigger seam, and 12 Serial/existing-Dask
comparisons after its complete 144/144/12 no-write preflight. The fresh
cumulative replay of that identity has now completed, and the authentic
incumbent and retained PyBDSF products remain reusable for its evaluation.
The source-aligned sentinel's now-failed candidate is local commit
`95cfc76ded56556dc3ad6894410962d34f0d5604`, source tree
`8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5`,
with unchanged configuration `2c907949...`. It includes the retained-unseeded-
parent rule from `3ed6086...`, publication-owner alignment, and the bounded
publication-owner-domain correction. Non-executable notebook identity
`2920873a...` binds the version-8 composition and authorizes neither
viewed-data execution nor replay. Its predecessor identity `89527070...`
remains immutable evidence for `11d70cf...`. The exact fast-lane authority was
consumed once from immutable tooling commit `ec4be4d...`; four geometry groups
missed only non-binding improvement objectives and no acceptance rule changed
after viewing the result. The successor single-scan cumulative stage freezes
implementation `cbb3212c...`, identity `0a464a38...`, expected execution
`1d372d64...`, and one-use decision `5662241e...`. Its complete no-write gate
passed all 2,400 candidate tasks, all 9,600 retained reference runs, and the
spawned-process seam with no candidate execution or output. It requires a
fresh product namespace while reusing the retained PyBDSF and authentic-
incumbent evidence. The authorized two-worker replay completed successfully
and atomically sealed all 2,400 candidate products as product set
`f43cb274...` in record `194022ab...`, with zero PyBDSF executions. The scoped
evaluation-only completion is now frozen with identity file `b29a54f1...`,
expected execution `e1e43203...`, and one-use decision file `423ee03c...`.
Its bounded terminal smoke passes all 1,187 comparisons. The terminal
evaluation exited successfully and published canonical decision `8d69ef44...`:
1,183 comparisons pass, all 143 Aegean and 676 dual-PyBDSF comparisons pass,
all five safety checks pass, and four of 368 incumbent-retention comparisons
are underpowered. Those four endpoint aliases reduce to two distinct
Continuum position-p95 evidence patterns. Their point estimates remain inside
the frozen `0.05`-beam margin, but their upper confidence limits are
`0.056371` and `0.054222` beam. The decision therefore has
`cumulative_science_regression_ready=false`; it is not a scientific failure
beyond margin and must never be relabelled as a pass. On 2026-09-06 the human
scientific owner accepted this narrow residual uncertainty because an
independent confirmation would require 4,608 new seed-disjoint Continuum
images, while the complete current evidence already establishes every
released/master PyBDSF and Aegean comparison, 364 of 368 incumbent
comparisons, the overall position-p95 comparison, and every safety check. This
acceptance waives only the additional incumbent-confirmation run and permits
the bounded production audit to begin; it changes no result, margin,
confidence interval, or scientific claim.
Detailed campaign and incident chronology
belongs in `LOG.md` and the campaign overview; machine identities and
authorization boundaries remain in `config/contracts/`.

#### Scientific-readiness and release gates

These requirements retain their original meaning. Under the 2026-09-11
decision, they are not all prerequisites to closing the development phase
after the last campaign and serious-issue review.

**Release correctness is not restricted to Rapthor's immediate needs.**
Prioritize the products Rapthor consumes, but do not declare readiness with a
confirmed defect in any supported public catalogue, position, flux, ownership
or processing-status contract. A narrower consumer, a pooled parity result,
or the historical confidence exception cannot waive a known incorrect output.
Do not conceal defects by switching to component-only reporting, dropping
troublesome rows, or describing incorrect measurements as supported limitations.
Unidentifiable measurements must be explicitly unavailable under a reviewed
contract; incomplete processing must be visible and cannot qualify as complete
science. This is not a promise of zero false detections or perfect physical
association: calibrated low-SNR uncertainty and genuinely ambiguous morphology
must remain explicit and tested against independent truth.

| Gate | Binding pass condition | Current state |
| --- | --- | --- |
| Known scientific risks | Every confirmed adaptive-background, measurement, association, component partition, publication, and evaluator defect is corrected test-first without changing a closed result after it is viewed. | Open pending replacement evidence. The failed sentinel and R6 audit remain binding. R6-C0--C7 are implemented, fixture-validated and frozen non-executable (2026-09-10). Complete R6-R6 admission below; neither these fixture passes nor earlier campaign results qualify the repaired public composition. |
| Fail-fast development evidence | The replacement analytic/mechanism/smoke ladder passes product validity, trigger behaviour, paired retention in every four-seed trigger cell, multi-peak component retention, negative controls, and Serial/existing-Dask invariance. | Required for the replacement. Version-8 terminal `a274888d...` remains a 12/12 geometry and 12/12 Serial/Dask pass with four report-only misses, but its tests did not distinguish independent compact-source membership from component multiplicity or cover the newly reproduced measurement/publication failures. Require the exact public composition and joint compact/extended truth gates in R5 and R6-C7. |
| Exact public candidate | The installed `hebog.find_sources` path resolves the frozen algorithms and reference configuration and produces identical scientific products under Serial and caller-owned Dask execution. | Historical identity and execution-consistency pass for `95cfc76...`, source `8da21e86...`, configuration `2c907949...`, and sealed 2,400-product set `f43cb274...`. This does not establish scientific readiness: the source-aligned sentinel fails and the public projection rejects admitted shape-unavailable owners. The replacement must be frozen and revalidated after R0--R5 and R6-C0--C7; no prior public-candidate pass transfers automatically. |
| Cumulative parity and retention | Across all 800 compact and 1,600 Continuum cases, every binding comparison passes both PyBDSF references, applicable Aegean checks, and hard safety rules. Incumbent comparisons must show no observed movement beyond their practical margin; any unresolved confidence exception must be explicit and human accepted rather than pooled away or relabelled. | Failed for replacement `db8936b...`: R6 terminal `7146f2e8...` has 885 passes, 288 failures and 14 underpowered comparisons. Released/master PyBDSF have 39/37 failures, Aegean 53 and incumbent retention 159; all five safety checks pass. Both readiness flags are false. Historical `8d69ef44...` and its narrowly accepted incumbent-uncertainty exception remain unchanged and do not transfer. A separate prospective scientific review must precede another candidate or run. |
| Fresh scientific qualification | A small prospective falsification sentinel complements, but does not replace, the powered cumulative evidence. On unopened seed-disjoint data, the exact public candidate must pass every known-risk extended and compact guard cell, hard safety rule, released-PyBDSF practical comparison margin, and Serial/existing-Dask check. Retain earlier reference evidence only where its identity and semantics remain applicable; changed candidate science requires replacement evidence. No pooled result may hide a failed cell, and the sentinel alone is not a powered parity study. | Failed, not awaiting a process retry. Spawn-safe identity `c498a90d...` completed 168 Hebog/168 PyBDSF runs and all 12 Dask comparisons; terminal `ca03240d...` passes 24/42 cells and fails 18/42 with 59 failed cell-endpoints. Both finders were measured against analytic truth. No qualification reuse or rescoring of those seeds is allowed. Complete R0--R5 and the replacement cumulative gate before R6's separately approved fresh sentinel. |
| Engineering evidence | Bounded execution, retry/order invariance, the 6.0-second 3,000-pixel incremental budget, package installation, schemas, atomic outputs, documentation, and ordinary CI all pass for the exact candidate. | Partly complete; final-candidate recheck remains. |
| Independent readiness | The rebuilt fail-closed packet receives separate radio-astronomy and engineering acceptance and publishes one terminal readiness record. | Open. |
| Documentation and handoff | User documentation, limitations, reproducibility, provenance index, campaign overview, and the Phase 6 handoff describe exactly what passed and what remains unqualified. | Open. Release preparation is intentionally excluded; Release Please owns it. |

#### Completed evidence

| Workstream | Durable result |
| --- | --- |
| Recovery promotion | Candidate `c184acf7...` passed all 143 Continuum absolute gates, all 226 powered PyBDSF comparisons, all compact binding gates, and all applicable Aegean comparisons in terminal decision `cd3eacfb...`. |
| Multiscale science and products | Residual-B3 detection, compact/extended reconciliation, deterministic identities, combined catalogues/masks, Rapthor compatibility products, and auditable scale/support provenance are implemented. |
| Bounded execution | Reviewed halos, bounded shards and reductions, one-tile/many-tile equality, and Serial/existing-Dask partition, worker, order, and retry invariance pass. |
| Final baseline qualification | The powered 1,688-image Continuum qualification and closed compact evidence passed through terminal decision `d4db4d7f...`; no campaign rerun, tuning, or rescoring occurred. |
| Compact regression | All 800 Phase 4U realizations pass 77 absolute gates, 40 released/master PyBDSF comparisons, and five stronger-Hebog envelopes. |
| Incremental performance | Summary `980e24c2...` passes the 6.0-second 3,000-pixel budget and retains Serial through 1,024 pixels and Dask at 3,000 pixels. This is not a complete Rapthor speed claim. |
| Public/challenge evidence | Sealed public decision `954077e9...` failed SDC1 completeness, reliability, and flux-error gates. Independent review `320f57f5...` preserved that result, identified source-association and deep-image overmerging defects, and forbade tuning or rescoring viewed data. |
| First public correction | Cumulative ledger `1ac6deb2...` kept compact green but recorded 37 Continuum like-semantics regressions, mainly split/duplicate source failures; it remains closed failure evidence. |
| Source-association correction | Candidate `26e639a...` added conservative component association and deterministic source composition. Its approved replay stopped after 58 of 2,400 candidate products because a positive owner could lose its catalogue row when negative surrounding residuals made the expanded aperture non-positive. No ledger was published. |
| Measurement-completeness repair | Commit `6184a32...` preserves positive expanded-aperture measurements, falls back to explicitly flagged positive exact-owner support only when required, propagates the flags, and remains fail-closed for genuinely unmeasurable owners. Its authorized replay completed all 2,400 candidate products. |
| Association-aware evaluation repair | The replay then failed before its atomic ledger because the compiler still required one legacy segment label per binding catalogue row. A new adapter leaves every closed program byte-identical, verifies the persisted source-membership digest against the finite native components, presents the exact support union only to catalogue matching, keeps native topology separate, and provides a completion-only path that forbids candidate execution. |
| Source-reconstruction correction | Candidate `42c75f4...` added a deterministic common-parent hierarchy, one source-level measurement, connected-support admission, and source-union topology evaluation. Terminal ledger `84fbb3a1...` preserves compact science but fails the cumulative gate with 44 Continuum failures and 37 regressions; source membership and fragmentation were effectively unchanged. |
| Publication-scale-persistence correction | Candidate `937737d...` completed the full cumulative population. Terminal ledger `a9c6ed28...` keeps compact green but reports 31 failures, 11 underpowered endpoints, and 26 regressions under its original wrapper. Review `77bd4b82...` keeps that status immutable but finds all stored PyBDSF comparisons within margin and the prospective result incomplete because full paired incumbent evidence is absent. |
| Readiness machinery | The fail-closed packet generator and finalizer exist and require packet-bound radio-astronomy and engineering acceptance. They reflect the original combined Phase 5/Rapthor closure and must be split prospectively before scientific-readiness finalization; existing records remain immutable. |

The narrow Continuum watchpoints from the passing recovery evidence remain
overall mask recall 0.90103 against 0.90 and mask-precision regression UCL
0.04940 against the pinned-master 0.05 margin. The terminal public failure and
the failed `1ac6deb2...` replay must remain visible historical evidence.

#### Prospective repairs after the source-aligned sentinel failure

The [2026-09-07 science audit](../docs/reference/phase-5-source-catalogue-science-audit.md)
separates reproduced defects from remaining hypotheses. On 2026-09-07 the
scientific owner authorized completion of R0--R6, including required fixes
and replays. The [prospective repair contract](../docs/reference/phase-5-source-catalogue-repair-contract.md)
records the scope and acceptance rules before implementation. Preserve
terminal `ca03240d...`, all closed thresholds,
comparators, margins, and truth definitions. Do not tune on its viewed seeds
or restore it to a pass through component-only scoring. Complete these tasks
in order before attempting the remaining closeout gates:

**R1--R4 implemented and fixture-validated (2026-09-08):** Native joint
measurements, morphology-constrained source association, conditioned signed
estimates, explicit unavailable/deferred owners and durable diagnostic
retention have red-first tests. The joint ladder covers all 36 development
geometries without noise, with independently seeded correlated noise and
analytic background/RMS, and through the actual public background/RMS path
(108 cases). The final combined compact/extended boundary run passes 142
tests, including disconnected shells sharing one reconciliation context.
Three noisy analytic-background mask objectives remain below
their report-only targets: cells 26 and 33 have IoU 0.57738 and 0.52469, and
cell 34 has recall 0.71565. These are retained observations, not waived parity
gates. An initial test incorrectly made the historical adaptive-lane absolute
targets binding; it now follows the current frozen report-only policy while
preserving the misses. Comparative PyBDSF and incumbent gates are unchanged
and still required. R5's full checks and engineering budget recheck pass:
3,151 coverage tests plus 171 joint/boundary/process checks, 95.1193%
branch-aware coverage, 963/963 changed executable lines and all changed
branches covered, 2,950 normal checks, 27 equivalence fixtures, strict docs
and wheel smoke. The frozen 3,000-pixel incremental stage medians are
5.56--5.60 seconds against the 6-second budget. This is not all-tier runtime
retention or a PyBDSF/Rapthor speedup claim. Clean hooks passed and candidate
`db8936b512370a1491f36845592fe3e8a24107ad` is frozen by
`config/contracts/phase-5-source-catalogue-repair-identity-review.json`,
source `43fb41f2...`, configuration `5eca0efc...`, composition `ef1322ca...`.
At the R5 freeze, R6 had not executed. The repaired default
is explicitly `development-unqualified`
and cannot use the previous candidate's qualification or notebook identity.

**R6 preparation (2026-09-08):** Retain the complete 2,400-image regression
population, all 1,187 binding comparisons and the original 50,000-resample
confidence rules. The 9,600 native reference runs are reusable only after
their original ordered product-set identities and every artifact pass the
no-write audit. The new current candidate needs fresh products; the absent
incumbent products require the exact historical producer, not structural
equality or a PyBDSF alias. The new orchestration captures both products
before truth evaluation, then preserves array-free per-image diagnostics
before final statistics. A late process error must not erase these stages.
Two spawned workers and 12 caller-owned existing-Dask comparisons cover all
five datasets; no new PyBDSF runs are needed for this cumulative replay.
Fixture checks include the real late statistical engine, native failed-run
rejection, checksum/census validation, duplicate refusal and cancellation of
pending work after worker failure. The executable identity, disk/time
admission and exhaustive immutable-checkout preflight still precede launch.
Tooling is now committed as `1b1cbae8cf8f05184cb2d095ced87175e2969849`.
The exact non-executable plan `af35c5b3...`, review `9b6913b9...`, one-use
decision `a9b0975b...` and expected execution `aea1f477...` bind its immutable
checkout, the unchanged repaired candidate, a 90-GiB disk admission and the
disclosed 10--24-hour cumulative estimate. Complete immutable no-write
preflight passed all 2,400 inputs and 9,600 retained reference runs (record
`3b2f84c8...`). Authorization commit `99b6797...` precedes the single
approved replay command, launched in managed session `19330`; it repeated
the preflight before capture. Hourly monitor
`monitor-phase-5-source-catalogue-r6` follows this exact execution without
inspecting partial science. The atomic terminal will be
`benchmark-results/phase-5/source-catalogue-repair-cumulative-decision.json`.
The process subsequently failed in evaluation; see the adapter review below.
R6 remains incomplete, not passed. The final fresh sentinel's
sub-12-hour target is separate and remains conditional on the cumulative
gate passing. No old pass or uncertainty acceptance transfers.

**R6 evaluation failure and adapter review (2026-09-08):** Session `19330`
exited with status 1 after completing all 2,400 capture pairs and 12 Dask
comparisons. The terminal remains absent. All 800 compact and eight
Continuum evaluations are durable: 4,032 complete finder records pass their
file/record checksums and capture/census checks. Preserve them and both
product sets; neither finder nor Dask needs to be rerun for an evaluator
repair. The main-checkout adapter now distinguishes wave-local Gaussian IDs
and distinct native models sharing a full exported key, without changing
source membership, measurements, masks or gates. True duplicate models fail
closed. The 16 reference views behind the eight completed Continuum inputs
are exactly unchanged by this ID correction; their scores were not rerun.

A full read-only adapter audit of all 3,200 operational Continuum PyBDSF
catalogues then found 50 further projection failures across 28 inputs:
23 released and 27 pinned-master catalogues contain a source with no
exclusive model-dominance pixels. This is not a parity result. The frozen
source-union review explicitly requires every real source to own pixels;
removing that guard, dropping a source or inventing support would not be an
ID/process repair. The [dated audit](../docs/reference/phase-5-r6-native-reference-adapter-review.md)
records the synthetic reproduction and prospective remedy. Before retry:

1. **Complete — scientific-owner approval (2026-09-08):** approval covers a
   prospective representation for native catalogue sources without exclusive
   derived support. Preserve their
   native positions, fluxes and membership; distinguish unavailable derived
   topology from absent catalogue measurements. Keep the existing matching
   rules and every denominator, threshold and comparator explicit. Do not
   replace the frozen nonempty-owner invariant outside the approved R6
   amendment. The historical review and v1 implementation remain unchanged.
2. **Complete — implementation and fixture validation:** the approved
   adapter boundary was implemented test-first; tests cover both
   finders, dominated/coincident sources, missing support, true duplicates,
   empty/fitless islands, row-order invariance and every affected downstream
   compiler seam. Preserve previously valid projections exactly. No source
   finding, tuning or viewed-result rescoring belongs in this step.
   The R6 v2 projection retains optional support labels without changing
   native rows or pixel winners. Diagnostics schema 2 records unavailable
   source support; source summary schema 5 distinguishes catalogue and actual
   source-union counts. Missing asserted labels still fail. Synthetic
   compiler and Serial/existing-Dask gates precede a non-executable freeze.
   A final synthetic audit added an exact-layout/model/ownership near-tie
   regression and correction, preserving historical floating-point arithmetic.
   The portable coverage suite passed 3,345 tests at 95.1148%, with every
   changed executable line and branch covered; 27 frozen equivalence tests
   and the handoff checks pass. Historical compiler/adapter bytes are intact.
   Shared validation-module edits change the package hash but not finder
   science. Implementation `f9f62c2...` is bound by the non-executable R6
   unavailable-support identity review `259cf6a4...`. The separate notebook
   identity `4a36dfa1...` updates its package hash while preserving the exact
   scientific composition and configuration. Its read-only guard passes;
   no R6 result transfers and no notebook refresh was run.
3. **Complete as execution; scientific gate failed (2026-09-09):** session
   `70321` exited zero and published atomic terminal `7146f2e8...` after
   evaluating the 1,592 missing inputs. It reused all 808 completed inputs
   byte-for-byte, with no candidate, incumbent, PyBDSF or Dask reruns, and
   retained combined evaluation seal `d14205d9...` before aggregation.
   Original candidate captures remain isolated from later notebook repairs.
   Both readiness flags are false: 885 comparisons pass, 288 fail and 14 are
   underpowered. All five safety checks pass. This is terminal scientific
   evidence, not another process retry. R6 remains incomplete and the fresh
   sentinel is blocked. Hourly monitoring ends with this terminal handoff.
   The separate prospective root-cause review of compact astrometry,
   shape/classification and Continuum measurement/retention is now complete;
   follow the pending R6 review actions below. Do not change any closed score
   or gate. The preparation comprised
   two explicit steps (absence/pending statements below describe that time):
   - **Complete — reusable-evidence inventory (2026-09-08):** immutable
     auditor `3fc57fc...` verified all 2,400 capture pairs, 9,600 reference
     runs, 12 retained Dask comparisons and 808 completed inputs / 4,032
     finder records, without running a finder or recomputing truth scores.
     Inventory SHA-256 `e0d1571d...` and non-executable identity review
     `4d4fb7c5...` preserve both empty failed directories and all completed
     records. Corrupt completions fail closed, never silently becoming
     missing work. Exactly 1,592 inputs still need evaluation; the original
     terminal remains absent and no scientific verdict has been inferred.
   - **Complete — entry point, immutable freeze and standalone admission:**
     bind the inventory into the separate evaluation-only entry point and
     immutable checkout; exercise missing-input dispatch, byte-for-byte reuse,
     combined evidence seal and late-failure retention on synthetic fixtures.
     The inventory alone is not a launch preflight or execution authority.
     The continuation entry point and its plan freezer now have test-first
     synthetic dispatch, two-worker spawn, corruption, unavailable-support,
     authority and late-failure coverage. They preserve the original output
     identity, reuse 808 inputs and admit only the 1,592 missing inputs in
     separate scratch; the combined seal precedes unchanged aggregation.
     The 92 focused fixtures cover every new executable line and branch;
     3,493 portable coverage tests pass at unchanged 95.1148% coverage.
     Immutable implementation `b64228d...` is now frozen with plan
     `c99f9f86...`, identity review `6ebd6664...`, exact execution
     `1b73bd62...` and separate one-use decision `3bc1e1e1...` under standing
     R6 authority. Standalone exhaustive admission passed, retained as
     `76a4fdcb...`; the launched command repeats it before dispatch. No finder
     rerun is required. The original terminal remains absent. Next, interpret
     the exact terminal against all binding gates before any sentinel launch.

**Concurrent notebook WCS repair (2026-09-08; complete):** The public SDC1
refresh exposed a valid FK5/SIN input reaching the ICRS-only beam-geometry
helper. Main-checkout repair `b6ad935...` has synthetic test-first evidence
for native beam-axis rotation, ICRS source/component positions, half-open
core selection and catalogue-to-pixel round trips (110 focused tests; all
changed package lines and branches covered). Original FITS headers, frozen
reviews and R6's execution checkout/environment are preserved. The public
API's ICRS-only admission rule and scientific gates remain unchanged.
`phase-5-notebook-fk5-wcs-repair-identity-review.json` freezes the separate
non-executable notebook identity; no viewed-input finder rerun or rescoring
was performed. R6 continues to describe candidate `db8936b...`, not an
automatic pass for this correction.

**Concurrent notebook joint-fit failure repair (2026-09-08; complete):** The next
refresh exposed an uncaught numerical decomposition exception inside the new
joint Gaussian solver. An exception before an optimizer result existed
bypassed the existing typed non-convergence outcome. The main-checkout
repair retains every affected joint-fit component as unavailable, with
`fit-linear-algebra-failure`, and continues independent parent islands. It
does not fabricate a Gaussian, retry with a different solver, change fit
bounds or waive a measurement-availability gate. The diagnostic runner emits
one warning per affected image and preserves component dispositions.
Synthetic solver/covariance/publication fault tests, exact ICRS/FK5 notebook
paths and Serial/existing-Dask invariance establish this failure contract.
The particular real fit's numerical cause remains unconfirmed; this repair
prevents whole-image loss rather than claiming that the fit now converges.
Repair commit `1d65277...` passed 3,301 coverage tests (95.1041%) and 27
frozen equivalence fixtures, with all changed lines and branches covered.
`phase-5-notebook-joint-fit-failure-identity-review.json` freezes its separate
non-executable notebook identity, with configuration unchanged and no
qualification transfer. R6 continues unchanged and does not qualify this
later correction.

The exact-public-background pass reproduced an additional R3 defect:
the scale-12 compact-core/halo boundary cell loses 35.4% of flux, while
the same development pixels with analytic background lose 13.5%. Isolation
identifies positive fine-grid background contamination, not RMS calibration.
The prospective correction extends bright-source statistical protection with
the existing beam-aware, seeded, adjacent-scale support before estimating
fine windows. It changes neither detection thresholds nor the published mask
definition and retains coarse fallback. The complete joint ladder and both
source-protection Serial/existing-Dask variants pass. A separate two-loop
fixture exposed remote arcs being associated by orientation alone; requiring
the same connected filled-loop region preserves distinct shell memberships.
All of this is development evidence, not replacement parity or qualification.

- [x] **R0 — Freeze the prospective scientific repair contract.** Specify
  independent compact sources versus components of one extended source;
  source/component/island identities; positions, shapes, integrated-flux and
  uncertainty meanings; unavailable/deferred outputs; and detection support
  versus measurement support/apertures. Review the selected remedies and
  fixture acceptance rules before implementation. Fixture-isolation defect
  F6 is repaired with temporary seal/output tests; retain those checks and
  preserve real campaign evidence throughout the scientific repairs.
  Reuse existing compact fitting, astrometry, and uncertainty machinery where
  suitable; do not add
  an alternative fitter without a demonstrated gap. The dated repair contract
  records the selected approach and red-first acceptance.
- [x] **R1 — Preserve source separation without fragmenting extended objects.**
  Add failing analytic tests for independent connected unequal pairs and
  three-or-more peaks alongside single-source shells, filaments, and mixed
  emission. Then correct hierarchy grouping so persistent shared support
  cannot by itself override justified compact separation. Test both source
  membership and component retention, flux attribution, completeness,
  reliability, splits, merges, and positions. A better mask or component
  count alone cannot pass this task; previously successful extended groups
  must remain intact.
- [x] **R2 — Correct compact measurements and unstable source estimates.**
  Validate bounded compact fitting against analytic flux, position, size and
  deconvolution truth over SNR, unequal neighbours, correlated/varying noise,
  negative backgrounds, invalid pixels and edges. Keep irregular extended
  photometry explicitly source-owned. Add red cases for threshold-truncated
  moment shapes misclassified as unresolved, signed-centroid cancellation,
  and positive-support flux fallback discontinuity/bias. Report estimator,
  uncertainty or unavailability honestly; do not clamp all source centroids
  to a peak or mask, since a real shell centroid can lie in its empty centre.
- [x] **R3 — Localize and correct remaining support/reliability losses.**
  On independent development fixtures, retain bounded attribution across
  coarse/adaptive background and RMS, direct seeds, multiscale support,
  persistence/pruning, component owners, source unions and publication.
  Separate extra noise detections from fragments, and measure missing truth
  support independently of IoU. Cover all shell/filament/mixed-source,
  beam/scale, trigger, noise and boundary groups, including the known failing
  geometries. Correct only demonstrated causes; do not assume every loss
  comes from adaptive background or globally relax detection thresholds.
- [x] **R4 — Complete public failure handling and diagnostic retention.**
  Add red end-to-end cases for one-pixel/custom-minimum and seven-collinear
  admitted owners, unavailable moment shapes, bounded deblend deferrals, and
  mixed measurable/unmeasurable owners. Publish reviewed explicit dispositions
  without inventing Gaussian fits or aborting unrelated valid sources.
  Preserve array-free per-image source/component memberships, truth-match
  edges, signed measurement residuals, support-stage counts, estimator flags
  and Dask comparisons alongside the terminal, with checksum verification
  and a cleanup guard. Distinguish measurement-only pixels from published
  mask pixels rather than requiring their footprints to be identical.
- [x] **R5 — Pass the short joint regression ladder before a long run.**
  Confirm each intended TDD red failure, then normal, boundary and error
  branches. Exercise the exact `hebog.find_sources` and notebook-runner
  compositions on synthetic development fixtures, not only internal kernels.
  Test empty/all-NaN images, WCS/beam rotations and unequal pixel scales,
  seed/threshold seams, thin and non-square support, tile edges/corners,
  translation/label/task-order/retry and Serial/existing-Dask invariance.
  Require both compact and extended truth gates together, meaningful shape
  and uncertainty assertions, and a fixture-only terminal-publication/process
  smoke. Keep verifier tests isolated from real ignored campaign outputs.
  The F6 repair now covers absent/existing outputs, seal tampering, invalid
  counts and changed invocation paths using temporary roots and synthetic
  seals, without deleting results or weakening the production write-once
  check. Retain these regression cases. Run focused tests, `just coverage`
  with changed-branch inspection,
  `just check`, `just test-equivalence`, `just docs-build`,
  `just package-smoke-test`, and `just pre-commit`; review against
  `CODE_REVIEW.md`. Freeze non-executable replacement identities only after
  these gates pass. Recheck the affected runtime budget without trading away
  scientific requirements.
- [ ] **R6 — Re-establish candidate-bound cumulative and fresh evidence.**
  The original repaired candidate `db8936b...` now has a complete but failed
  cumulative terminal (`7146f2e8...`, 2026-09-09), not a paused process.
  Preserve its captures, reused and new records, and all exact identities.
  The separate [root-cause review](../docs/reference/phase-5-r6-root-cause-review.md)
  is complete using hash-verified closed diagnostics and independent analytic
  fixtures. No automatic retry, viewed-data rescoring or fresh sentinel follows
  this fail. Complete these review actions in order:

  - [x] **R6-R0 — Localize failures without rescoring.** All 10,400 sealed
    records were hash-checked. Confirmed compact model-selection bypass,
    systematic GLS fallback flags and source-domain substitution; localized
    corner classification censoring and curved/shell fragmentation. Preserve
    the distinction between confirmed mechanisms and remaining calibration
    hypotheses. Review artifact is non-executable and grants no authority.
  - [x] **R6-R1 — Review the prospective repair contract.** The scientific
    owner approved the recommended repairs on 2026-09-09. The immutable
    review `939152d8...` remains non-executable. Native Gaussian components
    retain whole-model measurements; source rows retain observable, signed,
    single-owner aperture measurements. Independent fixtures must cover
    singleton/blended beam/free selection, owned-region versus context GLS,
    cropped/masked sources, covariance calibration, open arcs/shells versus
    independent compact neighbours, and centroid attribution. No gate, truth,
    margin, comparator or execution identity changes with this approval.
  - [x] **R6-R2 — Restore compact estimator conformance.** Test-first joint
    beam/free policy and bounded correlated-noise likelihood support, distinct
    from model-adequacy halos. Preserve neighbour treatment and coherent fit
    parameters/errors. Calibrate corner/edge covariance and deconvolution on
    independent noisy fixtures; do not lower the five-sigma classification
    rule. Cover support/context limits and retain small per-fit diagnostics.
    Completed on independent fixtures: coherent beam/free joint selection,
    owned-region GLS, 192 correlated-noise fits at four masked corners,
    circular-coordinate covariance recovery and periodic-angle initialization.
    The latter two numerical defects were found during the combined regression
    checks, not by tuning closed R6 inputs. The five-sigma rule is unchanged.
  - [x] **R6-R3 — Correct source measurement-domain consistency.** Keep native
    full-model Gaussian quantities as component measurements; ensure published
    source flux/position follow their declared observable-domain contract,
    including clipped and invalid-pixel domains. Reproduce E1 at the complete
    public boundary and test singleton/multi-component consistency, masked
    neighbours, flux ownership and explicit uncertainty/coverage limitations.
    The full public clipped-Gaussian witness now retains native total component
    flux separately from signed observable source flux; 2/3/4-peak fixtures
    retain their native components and single-owner source apertures.
  - [x] **R6-R4 — Resolve association and residual-position risks.** Use
    attribution-first, independent open-arc/incomplete-shell/core-halo fixtures
    paired with independent compact-neighbour counterexamples. A good Gaussian
    sum does not alone prove independent sources. Separate support assignment,
    centroid weighting, mask asymmetry and background effects; retain both
    position estimates and grouping decisions without tuning viewed cases.
    Completed prospective residual/core and connected tangential-arc repairs,
    with independent compact-neighbour/polygon/collinear counterexamples.
    Position uses unexpanded source ownership; flux retains measurement wings.
    Array-free attribution now records both estimators, their domains,
    background mean and competing group IDs. This resolves the implementation
    task, not all real-source ambiguity or the closed campaign's position tails.
  - [x] **R6-R5 — Qualify the combined repair on a short development ladder.**
    Exercise exact public Serial/existing-Dask composition, every failed
    geometry and neighbouring compact/extended guards, with independent noise,
    partition/context/order invariance and bounded cost. Pass focused tests,
    branch-aware coverage and patch inspection, `just check`, equivalence,
    docs, package smoke, review and final pre-commit gates before freezing
    non-executable candidate identities. Fixture success is not campaign parity.
    Engineering validation is complete: all 108 existing matrix cases and
    the new compact/arc/centroid guards pass, public Serial/existing-Dask
    conformance passes, and 3,526 coverage tests give 95.1906% coverage with
    all 184 changed executable lines/branches covered. `just check` passes
    3,304 tests; 27 frozen equivalence tests, strict docs and wheel smoke pass.
    The implementation report is
    [R6 estimator repairs](../docs/reference/phase-5-r6-estimator-repairs.md).
    Clean final hooks passed before implementation commit `4d07837...`.
    Non-executable identity
    `phase-5-r6-estimator-repair-identity-review.json` is frozen at SHA-256
    `f7afe3c18cf2c1c98397e688b58d62b88052c15d6c0705d1930e24c22e43f78f`,
    source `cc1db52e...`, unchanged configuration `5eca0efc...` and public
    composition `256ae828...`. Its committed-history test passes without any
    campaign output directory. Every execution authorization is false.
    The diagnostic notebook runner now selects this v10 identity explicitly
    (2026-09-09), correcting its stale v9 review selection without changing
    package science or historical identities. Future candidate freezes must
    check the intended notebook review selection and the actual no-write
    refresh preflight, not only synthetic tests with temporary identities.
    Visual refreshes remain diagnostic; no R6 verdict transfers.

  **New prerequisite: public-catalogue repairs R6-C0--C7 (2026-09-09).**
  The user's sealed v10 `Repaired estimators` refresh, source `cc1db52e...`,
  exposes gaps not covered by the completed R6-R5 fixtures. Preserve that
  completed engineering evidence and non-executable identity; neither is
  acceptance of the new witnesses. Pause replacement-candidate admission
  until this sequence passes. This plan update schedules repairs, not a
  finder run, viewed-data rescore, executable freeze or qualification.

  - [x] **R6-C0 — Establish the prospective repair and regression contract.**
    The [prospective contract](../docs/reference/phase-5-public-catalogue-repair-contract.md)
    now records native witnesses, independent controls and admission rules.
    The user approved implementation and separately approved investigation
    and repair of the small-image RMS policy on 2026-09-09. Preserve the sealed refresh and make a
    compact witness index linking case, source/component IDs, native fit and
    grouping diagnostics, publication state and coordinate conventions.
    Distinguish confirmed implementation/contract failures from morphology
    hypotheses: an associated-source centroid need not coincide with a peak,
    while the Hydra joint-fit bound diagnostic and HDR work-limit omissions
    are directly observable. Record expected behaviour before implementation
    and obtain scientific review of any changed association, estimator,
    availability or acceptance rule. Construct independent analytic/injected
    fixtures and counterexamples for C1--C5, not copies or tuned reproductions
    of the viewed pixels. Each production repair starts with an intended red
    behavioural test through the affected public path. Retain closed results,
    existing thresholds, comparator definitions, margins and confidence rules;
    new defect-specific gates supplement rather than replace them.
  - [x] **R6-C1 — Prevent unsupported source associations.** Trace both
    hierarchy-remainder grouping and extended-morphology merges, including
    transitive merging and overrides of compact-source protection. Add bounded
    attribution for each merge's reason, evidence scale, participating groups
    and protection decision. Require affirmative morphological evidence for
    cross-island associations; a common reconciliation or fit context alone
    must not identify one source. Prioritize a conservative compact-source
    rule for scientific review: independently detected compact neighbours
    remain separate unless observable evidence supports their association.
    An absent, failed or deferred compact fit is not affirmative evidence for
    merging its hierarchy remainder. Extended overrides must identify their
    supporting evidence and pass compact-neighbour counterexamples. Test
    source-level false merges and missed independent sources, with false-split
    guards; preserving the Gaussian count alone does not pass this gate.
    Vary separation in beam units, SNR, flux ratio and background/context.
    Test isolated neighbours, unequal pairs, chains, broad-context groups and
    rejected-link remainders alongside real
    multi-peak islands, arcs, shells, lobes and core-halo emission. Verify
    membership as well as centroid and total flux; do not repair a bad group
    by snapping its centroid onto a peak, forcing every component to be a
    source, or breaking genuine extended sources into independent detections.
  - [x] **R6-C2 — Separate bounded fit work from source association.** The
    HDR witness contains a 101-component parent whose 606 parameters exceed
    the 96-parameter joint-fit limit; ordinary supported detections are then
    deferred together. Define scientifically valid bounded fit groups using
    actual overlapping measurement/model context, independently of the final
    associated-source grouping. Preserve neighbour contributions, ownership,
    joint covariance where applicable, and deterministic reconciliation.
    Keep parameter, Jacobian and memory limits; simply increasing them or
    creating one Dask task per component is not a repair. Test both sides of
    each work limit, many independent sources sharing a context, and truly
    inseparable large blends. The latter must retain explicit deferred status
    if no valid bounded solution exists, not disappear into a success count.
  - [x] **R6-C3 — Make joint-fit quality and failure handling trustworthy.**
    Reproduce weak, displaced and boundary-pinned components inside a nominally
    converged joint fit, with independent noisy compact-neighbour fixtures.
    Audit residual/noise units, correlated-noise conditioning, Jacobians,
    initialization, context and identifiability before selecting a remedy.
    Make bound detection scale-aware and consistent with solver tolerances;
    the Hydra witness reports relative centroid-bound distance about
    `6.6e-11` but no bound flag. Numerical convergence alone must not establish
    a scientifically identifiable measurement. Predeclare and calibrate any
    additional acceptance or fallback rule on independent truth, retaining
    joint-model/covariance consistency and explicit unavailable uncertainty.
    Test low-amplitude degeneracy, bounds, singular/SVD/nonconvergent cases,
    ordinary successful fits, and legitimate asymmetric/extended emission.
    Do not invent a residual cutoff or force reference positions from the
    notebook examples; the precise cause of the distorted fit remains open.
  - [x] **R6-C4 — Reconcile public membership, measurements and completeness.**
    Specify which measured, unpublished, deferred and unavailable components
    may contribute to each source's position, flux, support and component
    count, and expose the contributing IDs/statuses consistently. The ordinary
    SDC1 witness includes an unpublished neighbour in a displaced source
    centroid; diagnose association separately from publication-domain policy.
    Preserve legitimate sub-threshold wings and native full-model information;
    do not equate absence from the display mask with absence of real emission.
    Test empty/all-unavailable results, mixed member states, shape/uncertainty
    unavailability and failure round-trips through public API, saved products,
    catalogue adapters and notebook readers. Reconcile detected, measured,
    published, rejected and deferred counts with explicit reasons. Never
    publish known invalid coordinates as ordinary measurements or make lost
    supported detections improve reliability by silently omitting them.
  - [x] **R6-C5 — Attribute and resolve bright-extended support suppression.**
    The HDR bright body has elevated background/RMS and falls below support
    thresholds; saved PyBDSF products also show elevated RMS, so the screenshot
    alone does not prove a background bug. Use known broad emission plus
    bright cores, independent spatially varying/correlated noise and artefact
    counterexamples to separate source contamination, valid noise inflation,
    source protection, scale selection and publication effects. Cover mesh
    sizes, beam/source-size ratios, faint wings, neighbours and image/tile
    boundaries. Correct any reproduced estimator/support defect test-first;
    otherwise document the attribution and calibrated detection limit.
    Require background/RMS accuracy, extended flux/support recovery and
    compact completeness/reliability retention together. Do not force zero
    background, lower thresholds or expand masks to match viewed references.
    **2026-09-10 fixture gate passed.** Source-protected coarse background
    and independent protected local RMS pass all 24 retained bright-halo/noise
    controls and all 108 geometry cells together. The 38 independent noise
    controls include both sides of the limiting-dimension transition and
    actual image corners. Rejected mesh-only, bright-only and pilot-only
    variants remain documented in the contract and LOG.md; none was promoted.
    This corrects independently reproduced estimator defects, not a claim
    that every feature in a viewed HDR image is astrophysical or recoverable.
    - [x] **C5a — Review independent local-noise refinement before repair.**
      The user authorized this review and test-first repair on 2026-09-10.
      The development proposal separates source-protected fine-grid RMS from
      the retained background policy, with globally anchored bounded contexts
      and global missing-cell reconciliation; see the public-catalogue repair
      contract. It is fixture-validated, not campaign-qualified.
      Specify a source-protected noise-resolution policy independent of the
      75-sigma bright-source trigger. Review background versus RMS ownership,
      source-mask bias, correlated-noise sampling, unavailable-cell handling,
      boundary continuity and bounded/tiled execution before implementation.
      Require renewed scientific-policy review; do not simply publish the
      unprotected pilot, lower the trigger or select a maximum to pass a cell.
      Add independent noise-only, smooth-gradient and localized-noise controls
      at multiple scales alongside compact, broad-halo and no-source guards;
      keep all 24 halo/noise cases and the full 108-case matrix binding.
      Implement test-first only after the reviewed policy is authorized, then
      repeat Serial/existing-Dask, coverage and all C7 gates. No threshold,
      closed evidence or reference is changed. Do not freeze or run a partial
      remedy; see LOG.md for the rejected development variants.
      **2026-09-10 implementation:** bounded, globally anchored protected RMS
      now has independent fine-grid admission. The combined integration run
      passes 203 tests: 38 noise, 24 halo, 108 geometry, six background
      Serial/Dask and 27 public-API cases (including four exact public
      normal/fault comparisons). All 79 focused RMS/protection tests pass.
      Follow-up red-before-fix tests cover positive edge RMS, actual versus
      internal context boundaries, noise-explained bright work anchors and
      isolation of the unchanged compact-only policy. Final coverage and
      the non-executable candidate freeze are recorded in C7; no replay has
      started.
  - [x] **R6-C6 — Make notebook and catalogue diagnostics unambiguous.** Label
    native product types explicitly: Hebog components versus associated
    sources, PyBDSF source versus Gaussian catalogues, and Aegean components
    versus optional island summaries. Identify ellipse-proxy masks as proxies,
    not native support. Provide member links, quality/failure/deferred state
    and visible-region versus full-catalogue counts so a centroid between
    valid members is distinguishable from an unsupported association or fit.
    Preserve both public source and component products; plotting changes must
    not move positions, hide failures or substitute for science repairs.
    Test transforms, overlays and native schema selection on synthetic saved
    products; reuse sealed products for diagnostic display without rescoring.
  - [x] **R6-C7 — Pass the combined no-regression ladder before refreezing.**
    Run the complete existing 108-case development matrix plus the new trigger
    and negative-control fixtures, not just the latest failing morphology.
    Cover compact SNR/flux ranges, blends/multiplicity, arcs/shells/core-halo,
    bright extended/dynamic-range cases, empty/NaN/negative-background inputs,
    beams, WCS orientations/frames, units and non-square/edge geometries.
    Require exact public Serial/existing-Dask conformance, one/many-tile and
    corner/context/partition/order/retry invariance, and bounded fit cost.
    Compare each finder independently with analytic/injected truth and compare
    like semantics; PyBDSF and Aegean are not truth. Check component and source
    membership, positions, flux/shape/uncertainty, support and missing/duplicate
    or deferred outcomes per geometry/SNR/trigger cell. Preserve the last
    reviewed candidate's strengths with paired retention: no pooled gain may
    hide a regression or a new catalogue omission. Do not enshrine a diagnosed
    defect as expected output. Pass focused tests, branch and patch coverage,
    `just check`, frozen equivalence, strict docs, notebook
    checks, package smoke and `CODE_REVIEW.md` review; run clean final hooks.
    Refresh public contracts/docs and freeze a new non-executable candidate
    only after these gates, with the notebook's exact identity-selection and
    no-write preflight checks. Fixture success is not campaign parity or
    release approval; a remaining confirmed correctness defect blocks C7.
    **2026-09-10 validation:** 203 combined integration cases and the final
    compact-profile guard pass; stable-source portable coverage passes 3,697
    tests, plus the 49-test final boundary/workflow supplement. Coverage is
    95.2377727% (baseline 95.1905998%); all 221 changed executable lines and
    changed branches are covered. Full checks (3,408), frozen equivalence
    (27), strict docs, Marimo, package smoke and clean implementation hooks
    pass. Candidate `ee8303519feab359e11f70ee1debfafd00d34177`, source
    `f708bd54...`, composition v11 `da4018cc...`, diagnostics schema 8 and
    unchanged configuration `5eca0efc...` are bound by
    `config/contracts/phase-5-public-catalogue-correctness-identity-review.json`
    (SHA-256 `dc811fb8...`). The review is non-executable and grants no
    authorizations. Committed-history/selector/synthetic notebook checks pass
    29 tests. The actual read-only notebook preflight passes all 13 configured
    cases using runner `c9b0fec5...`; this checks identity and case metadata,
    not refreshed results or exhaustive replay admission.
  - [ ] **R6-R6 — Final cumulative campaign and development closeout.**
    **Next task:** monitor the final v14 cumulative campaign, followed by
    severity review and development closeout. F1 and F3
    are complete; general Gaussian model adequacy remains unqualified.
    The completed
    [2026-09-11 follow-up](../docs/reference/phase-5-v13-followup-review.md)
    confirms independent faint-source fragmentation and a pathological
    notebook Gaussian admitted as measured. Following the code/evidence
    review, the user approved the bounded F1 repair; F2 remains deferred.
    The independently repaired numerical and admission defects do not prove
    that every viewed notebook witness is fixed.
    The replay runs after resource and exhaustive exact execution admission,
    keeping the notebook isolated. After terminal
    evaluation, investigate serious issues; do not automatically reopen
    scientific development for every failed or underpowered comparison.
    The frozen v14 candidate is `cf6d9da...`; preparation `b2f0b2f6...`
    preserves all 2,400 tasks and 8,000 reusable comparator records. Resource
    admission on 2026-09-12 records 76.69 GiB free against 70.02 GiB required.
    The detached execution checkout is `d5fe741...`; its plan `f28b19c2...`,
    review `857175ca...` and one-use decision `4e3feb6c...` bind expected
    execution `174579e8...`. No v13 or older execution authorization is reused.
    Exhaustive preflight exits zero (log `48e3afd1...`) with no finder
    execution. The exact replay is launched in session `81018` at approximately
    07:52 UTC and passes its repeated audit before capture. Both workers are
    active and 14 captures have completed by 08:00:24 UTC without a process
    failure. Hourly monitor `monitor-current-replay` is active; there is no
    terminal scientific verdict. Never launch a duplicate while it runs.

    - [x] **Run the missing paired quick check.** A result-neutral 24-input
      regression subset completes 24 exact-public Serial captures/evaluations
      and two matching existing-Dask comparisons in 295.55 s, reusing 80
      checksum-bound comparator records. The released container is absent,
      so this transparently replaces the proposed fresh-seed screen with
      existing regression inputs; it is not held-out evidence. Summary
      `29dca20f...` retains all 1,187 paired point comparisons: 1,138 within
      margin and 49 beyond (3 released, 4 master, 3 Aegean, 39 incumbent).
      No point estimate is unavailable, but no confidence intervals or
      campaign pass are claimed. All closed evidence remains unchanged.
    - [x] **Review screen risks before long execution.** Localize low-SNR
      compact position tails and incumbent uncertainty/flux/shape retention;
      inspect extended mask precision, flux tails and filament/mixed-source
      position/splitting, including the separate four-seed geometry warnings
      and the explicitly unavailable fit. Separate sampling variability,
      estimator trade-offs and confirmed defects. Reproduce proposed defects
      on independent truth before any repair; do not tune or rescore the
      screen. Better pooled completeness/reliability cannot waive these
      checks. See the [quick-screen record](../docs/reference/phase-5-v13-replay-preparation.md#paired-quick-screen-2026-09-11).
      Follow-up completes 256 independent compact fits, 40 faint morphology
      cases and three exact-public Serial/existing-Dask pairs. All execute;
      three single-source fragmentations reproduce in both executors.
      Likelihood-context expansion is not a demonstrated compact remedy.
      The separate viewed Hydra trace confirms a near-bound Gaussian displaced
      11.97 pixels from its local peak, with reduced chi-squared 524,528,
      published as measured. Root mechanisms and residual uncertainty are
      recorded without tuning or rescoring. This completes diagnosis, not
      repairs or campaign qualification.
    - [x] **F1 — Required before replay: bounded Gaussian-validity repair.**
      Reproduce with
      independent bright/oversampled, modest model-mismatch and mixed-noise
      fixtures before changing numerical conditioning or fit acceptance.
      Retain exact correlated-noise, subpixel, blend, boundary, covariance and
      unavailable-fit controls. Separate successful optimization from an
      adequate, stable model. Preserve detection/source support when a fit
      cannot be represented honestly; do not replace fitted positions with
      peaks or choose a residual cutoff from the viewed notebook.
      Start with bounded likelihood-conditioning diagnostics and the existing
      explicit diagonal-estimator/correlated-error fallback. Use a numerical
      stability criterion, not a cutoff selected to pass the viewed witness.
      Verify normal fit availability, astrometry, flux, shape and uncertainty;
      prevent a numerically failed fit from becoming a plausible Gaussian row.
      Keep source support and non-Gaussian source measurements independently
      available. Do not rerun the viewed notebook to select a repair.
      **Started:** independent 21-by-21 fixtures reproduce acceptance of an
      unresolved GLS covariance both with and without Cholesky failure. The
      initial repair removes silent diagonal jitter and uses LAPACK's bounded
      reciprocal-condition estimate with a dimension-scaled float64 roundoff
      guard; fallback remains explicit diagonal estimation with correlated
      sandwich errors. Nineteen focused numerical cases and the existing
      fitting controls pass. This fixes a numerical admission gap, not every
      model-adequacy failure or the viewed witness by assertion. At that
      intermediate checkpoint F1 remained open; the bounded completion below
      supersedes that status. F3/new identity and replay admission remain open.
      Initial repair validation passes 3,919 coverage tests, 27 frozen
      equivalence tests, five covariance ensembles and the public Serial/Dask
      supplement. Project branch-aware coverage increases to 95.2840083%;
      every changed statement/branch is covered. These are non-regression
      controls, not a declaration of campaign readiness.

      - [x] Reject roundoff-unresolved GLS covariance explicitly; preserve
        good-fit measurements and correlated-error calibration on independent
        fixtures and exact-public Serial/existing-Dask capture.
      - [x] Make physical ellipse admission independent of optimizer axis
        order. Test-first single/joint analytic fits expose the same 3:1
        ellipse escaping a declared 2:1 limit after a rotated initializer.
        Both axes now require positivity and the ratio uses larger/smaller;
        no configured limit changes. Twenty numerical cases, seven complete
        bright/asymmetric/overlapping/masked/edge model comparisons and a
        public source-support/photometry-retention control pass. The model
        comparisons use separately parameterized Astropy fits, not PyBDSF as
        truth or the viewed notebook. A best Gaussian approximation is not
        proof that every residual is scientifically acceptable.
      - [x] Complete the bounded selected-model/whole-Gaussian acceptance
        review with bright asymmetric, overlapping and masked/edge controls.
        Require a faithful complete fit or an explicit unavailable disposition
        with support retained; no peak substitution or screenshot-derived
        residual threshold. This is not a reopening of F2's broader science.
        **Completed:** remove the single-fit free-only/beam-unavailable
        identifiability bypass. Twelve actual clipped-source solves now reject
        physical-bound or ill-conditioned solutions consistently with joint
        fitting, including beam-selected mode with missing beam metadata;
        three single-fit cases fail before the repair. Eleven
        independent whole-model comparisons include central invalid pixels
        and compact-on-diffuse emission. All 263 focused tests pass. Retain
        detailed rejected-edge diagnostics and separately selected edge
        positions/covariance. Current composition is v14; F3 must validate
        and freeze it before launch. This closes the bounded numerical and
        existing physical-admission review, not all astrophysical model
        adequacy. No new amplitude/footprint/residual threshold is adopted.
        The current parent residual test controls grouping, not component
        publication; do not convert it wholesale into a Gaussian rejection
        rule that discards valid compact components on extended emission.
        Assess local amplitude/centre/footprint consistency instead, with
        overlaps, invalid central pixels and real truncation as controls;
        established finder flagging is guidance, not truth or permission to
        import its thresholds. Record any proposed new acceptance rule before
        implementation and validate it independently before promotion.
    - [ ] **F2 — Deferred: repair faint grouping without compact over-merges.**
      Extend
      the existing joint geometry matrix to faint shells/arcs/filaments and
      clipped envelopes. Evaluate bounded one-envelope/multiple-object and
      aggregate morphology evidence with independent compact pair/polygon/
      chain and compact-on-extended negative controls. Keep immutable
      component identities, explicit ambiguity and unchanged detection gates;
      neither blanket merging nor blanket splitting is acceptable.
    - [x] **F3 — Validate and freeze F1; defer broader scientific repairs.**
      Run the
      complete source/component measurement and non-regression gates,
      Serial/existing-Dask and partition/order/retry checks, patch/branch
      coverage, equivalence, docs and clean hooks. Retain compact uncertainty,
      mask precision and extended-flux risks separately; no pooled gain or
      favourable seed choice can waive them. Bind new candidate/program
      identities before any future repaired-candidate paired confirmation,
      then resource and exhaustive immutable admission. This is a
      prerequisite to launching the final campaign with repaired science.
      Keep the existing 2,400 inputs, comparators,
      truth, margins and confidence rules unchanged; preserve v13 and
      its screen rather than modifying or rescoring them.
      **Completed prerequisites:** candidate `cf6d9da` is frozen by review
      `1b9b2f38...`, with 3,959 coverage tests, the final twelve-case
      admission supplement, 27 equivalence tests and exact public Serial/Dask
      controls passing. The separately frozen 24-input screen completes all
      captures/evaluations and two exact Dask comparisons. Its 1,187 paired
      point rows equal v13: 1,138 within margin and the same 49 warnings;
      this is not powered parity or proof of general model adequacy.
      Preparation `b2f0b2f6...` binds the unchanged 2,400 tasks and 8,000
      reusable comparator records to v14. No new external-finder execution.
      **Launch admission — 2026-09-12:** the live reserve is met and a separate
      exact immutable execution plan/review/one-use decision is frozen.
      The exhaustive no-write preflight passes and the single authorized
      replay is launched in session `81018`. Healthy initial capture progress
      precedes activation of hourly monitor `monitor-current-replay`.
      Qualification is not included;
      do not reuse an old candidate's approval record.
      **Current authority:** the user approves completing replay prerequisites,
      then the run and process-bug retries. Bind v14 separately; a retry needs
      a fresh immutable identity and namespace and cannot retune science.
      Resource admission records 82,344,136,704 free bytes against the
      candidate-bound reserve of **70.02 GiB** (75,180,190,600 bytes).
      Recheck immediately before capture and monitor remaining headroom;
      older cleanup measurements below are historical. No cleanup or
      reduction of the reserve is authorized.

    **Historical notebook/launch holds (superseded by v14 admission above):**
    do not launch the known-failing v12 candidate or its old preparation.
    The notebook refresh completed successfully at 22:59:52 UTC
    on 2026-09-10: all 13 results and 104 unique artifacts verify, together
    with input records, identities and published history. Terminal SHA-256
    is `905475f7...`; this is diagnostic completion, not scientific parity.
    The initial disk hold (66.747 GiB versus 68 GiB required) is cleared by
    user cleanup: approximately 89.9 GiB was then free (81.6 GiB at the v13
    freeze; recheck before launch). The remaining independent
    noiseless cost fixture exposed the now-repaired source-protection defect.
    No replay had started at that hold; no agent cleanup was authorized.
    The hourly monitor held launch pending F1, its F3 replacement freeze,
    resource and exact execution admission. The 2026-09-11 approval required
    only this bounded validity repair; F2 remains deferred.
    The user now
    authorizes the isolated replay, evaluation, investigation of failures,
    and process/evaluator repairs and retries after the refresh finishes.
    Hourly monitor `monitor-notebook-then-v12-replay` owns that sequence;
    notebook process disappearance without a sealed successful result is a
    blocker, not permission to launch. The
    [v12 preparation record](../docs/reference/phase-5-v12-replay-preparation.md)
    binds the 2,400-task/8,000-reuse inventory and staged runner, but remains
    non-executable. R6-C0--C7's recorded tests
    passed; the added exact-public noiseless failure has a
    [v12 numerical repair](../docs/reference/phase-5-noiseless-filter-repair.md)
    and now passes normally, but the new two-component zero-noise geometry
    exposes a separate availability/anchor mismatch. The v12 metadata rebind
    is complete; no historical
    verdict or consumed execution authority transfers. No replay has been
    admitted or started at that historical hold. Do not
    launch the older v10 candidate or reuse its consumed decisions. Follow the
    unchanged scientific gates and authority boundaries below.
    The [replacement admission review](../docs/reference/phase-5-r6-replacement-admission-review.md)
    is historical planning evidence for v10 (2026-09-09); revalidate its
    candidate binding, reusable semantics and resource estimates after C7:

    - [x] Review the prior v10 reuse inventory: 2,400 incumbent, 4,800
      dual-PyBDSF and 800 Aegean evaluation records remain reusable
      byte-for-byte. Preserve all
      2,400 inputs, 9,600 reference runs and the failed R6 terminal. The new
      candidate still needs 2,400 Serial captures/evaluations, 12 existing-Dask
      comparisons and new paired statistics; no old verdict transfers.
      The central evaluator and native-reader bytes remain unchanged in v11;
      this is not a substitute for the final transitive/exhaustive audit below.
    - [x] After C7, complete test-first reuse-aware orchestration and
      synthetic end-to-end/reuse/failure checks. The old pair runner executes
      the incumbent and evaluates every finder, so do not launch it unchanged
      or edit its consumed decision. Reuse scientific functions and immutable
      comparator records without introducing a second scoring definition.
      **2026-09-10:** 40 control tests cover every changed tooling line/branch;
      two noisy synthetic end-to-end tests pass with actual two-worker public
      capture and Serial/existing-Dask agreement. The historical audit again
      verified all 2,400 inputs, 9,600 references and 10,400 records, with no
      rescoring. The 8,000-record index is unchanged; 336 original code/data
      paths and ten native-reader definitions are unchanged. No executable
      owner wrapper or one-use execution identity is issued.
    - [x] Diagnose and repair the additional noiseless exact-public capture
      error (`significant scale features require finite positive response`)
      without changing frozen thresholds or treating the strict xfail as a
      pass. It occurs in source-protected adaptive background estimation;
      the reproducer admits huge finite scale SNR on features with zero or
      negative original-residual maxima. Trace low-noise calibration and
      positive-support admission; do not tune an arbitrary RMS floor.
      Preserve the reproducer,
      validate noisy/zero-noise/empty/invalid and Serial/Dask controls, then
      refreeze changed science. Do not alter source while the user's notebook
      refresh is active. This is independent development evidence, not a
      campaign failure or viewed-data tuning.
      **2026-09-10 repair validated and frozen non-executable:** the
      notebook refresh has exited. The
      red exact-public regression is confirmed without its xfail marker.
      Direct local sums show that remote FFT response leakage, not emission,
      becomes enormous SNR under near-zero estimated noise. Use the same
      finite-support kernels with compiled spatial convolution when input
      noise/variance is below floating-point FFT resolution; rescale the
      variance calculation when precision or squared-unit range requires it.
      The exact public reproducer passes normally, as do the focused
      numerical, invalid-pixel, halo/core and actual Serial/Dask checks.
      Keep ordinary FFT arithmetic and scientific thresholds unchanged.
      No arbitrary RMS floor,
      viewed-data adjustment or replay execution is authorized by this repair.
      Full portable coverage passes 3,760 tests plus a 35-test direct-guard
      supplement on unchanged source: 95.2577599% (prior 95.2547080%), with
      every changed executable line and branch covered. Full checks pass
      3,464 tests; frozen equivalence passes 27. Clean repair hooks pass.
      Candidate `ed5136af4b0948ff48e7ebb8311ce192f17c76cf`, source
      `838e2846...`, composition `ba1039f5...` and unchanged configuration
      `5eca0efc...` are bound by
      `config/contracts/phase-5-noiseless-filter-repair-identity-review.json`
      (SHA-256 `2ab9d433...`). All authorizations are false; the execution
      identity is null. Thirty committed-history, drift/selector and
      synthetic notebook tests pass. The actual no-write notebook preflight
      passes 13 cases; repeat on the final clean commit. No notebook refresh
      or replay was started by that repair; v12 preparation follows below.
    - [x] Rebind the non-executable preparation to the frozen v12 candidate
      while leaving the user's new notebook refresh untouched.
      **2026-09-10:** clean preparation commit `97dc43e...`; metadata SHA-256
      `4d70e746...`, all authorizations false and execution identity null.
      The exhaustive historical audit passes all 2,400 inputs, 9,600
      references, 4,800 native captures, 12 old Dask comparisons and 10,400
      records without execution or rescoring. The 8,000 reusable-record index
      is unchanged; 335 original code/data paths and ten native-reader
      definitions are unchanged. No old verdict transfers. The proposed
      execution/scratch directories remain absent. See the
      [v12 preparation](../docs/reference/phase-5-v12-replay-preparation.md).
    - [x] Repair the new independent zero-noise admission failure. The user
      explicitly approves repair, non-regression and Serial/Dask checks,
      and a corrected-candidate freeze before launch on **2026-09-11**.
      Process/evaluator retry authority alone does not authorize further
      candidate-science changes. The historical v12 candidate fails
      a finite 512-square, two-component development input with
      `adaptive candidate is absent from source-protection support`.
      The reproduced protection window has zero valid normalized pixels,
      but an old candidate anchor is still required to belong to thresholded
      support. The approved trace finds an exactly zero-valued protected
      coarse grid. V13 admits protected adaptive work only with available
      positive coarse RMS, preserving zero/unavailable statistics, local-noise
      estimates and independent noisy neighbours. No guard, threshold or RMS
      floor is weakened. The exact regression passes after its intended red.
      Validation passes 219 focused, 3,778 portable and 27 equivalence tests;
      a 25-test guard supplement brings branch-aware coverage to 95.26468995%,
      above the prior freeze, with all changed executable lines covered.
      Actual Serial/Dask comparisons and archived-v12 noisy non-regression
      agree exactly. See the
      [repair contract](../docs/reference/phase-5-zero-noise-adaptive-repair.md).
    - [x] Freeze the committed v13 source/configuration/composition in a new
      non-executable candidate review, update the notebook identity selector
      without refreshing results, and preserve all historical identities.
      This freeze is not a replay launch decision or qualification.
      **2026-09-11:** repair candidate
      `eacfa6455c750c3bb8c85250669890cc44bc0dac`, source `d5107cd3...`,
      composition `0b6844bf...` and unchanged configuration `5eca0efc...`
      are bound by
      `config/contracts/phase-5-zero-noise-adaptive-repair-identity-review.json`
      (SHA-256 `e93372b5...`). All authorizations remain false and execution
      identity null. Thirty-one committed-history, identity-drift/selector
      and synthetic notebook checks pass. The selector change is test-first;
      it cannot silently fall back to the old v12 review. No notebook refresh,
      campaign execution or closed-result rescoring accompanies this freeze.
    - [ ] Measure an independent representative fixture cost/size ladder, then
      resolve resource admission. Provisional budget is 68 GiB free versus
      69.42 GiB observed during v12 preparation (only 1.42 GiB headroom;
      the earlier quick probe observed about 54 GiB). Recheck after refresh.
      **2026-09-10 quick probe:** seven independent fixtures complete one
      warm-up and five measurements each, with two single-thread-budgeted
      workers on the committed v12 snapshot. Capture medians are 9.60 s for
      a 60-component 512-square field and 26.19 s for a mixed 1024-square
      field. A size-weighted planning calculation retaining the historical
      evaluation/statistics/check allowances gives 11.84 h, or 13.22 h with
      20% capture headroom; neither is a confidence bound or admission.
      The larger fixture has only two injected components versus the replay's
      17, and only overall evaluation endpoints were timed. The complete cost
      ladder and precision-limited fallback remain outstanding. Evidence is
      recorded in `LOG.md` and the ignored v12 runtime-probe summary.
      The user clarified that the intended runtime question was the **50%
      complete Rapthor/PyBDSF reduction**, not replay duration. This Hebog-only
      probe cannot measure that ratio. Older same-input notebook observations
      mostly favour PyBDSF, but are not current-candidate, resource/output-
      matched repeated benchmarks. Complete dual-PyBDSF performance remains
      Phase 6 work; do not infer that the target is already satisfied.
      Preserve evidence, thresholds, comparators and all risk geometries.
      The notebook refresh has completed and its published artifacts verify.
      User cleanup cleared the disk hold on 2026-09-11 (approximately
      89.9 GiB free). The denser/precision extension fails during first-round
      capture on the independent noiseless geometry above; no complete new
      timing ladder was produced. Resume only after its approved repair and
      candidate refreeze; retain the precision-limited path in admission.
      Recheck the final budget. Preserve replay-critical references and R6
      directories. At that stage the unfinished exact-owner draft and 24
      passing prototype tests were parked as text in the ignored preparation
      evidence directory; that historical draft remains preserved.
      **2026-09-11 cost ladder complete; resource admission still open:**
      v13 completes 48 captures and 30 full-metadata current evaluations
      across eight independent fixtures, one warm-up plus five measurements
      each. The zero-noise fixture completes every capture. The first v13
      probe exposed missing fixture truth metadata, repaired test-first with
      four passing contract tests; candidate and evaluator bytes are unchanged.
      Full-capture medians are 16.20 s for the 60-component 512-square case
      and 46.89–49.54 s for the 17-component 1024-square cases. Weighted
      planning with historical stage allowances gives 17.50–20.02 hours,
      not a deadline guarantee or PyBDSF speedup. Summary SHA-256 `bf6bb1be...`
      retains all repetitions and limitations. The revised free-space reserve
      is 69.58 GiB; about 9.85 GiB was missing at the latest cost-summary
      snapshot. No cleanup or launch is authorized by this cost record.
    - [x] Rebind non-executable preparation to v13, preserving the old records
      and failed verdict. Metadata SHA-256 `a1c60497...` binds 2,400 tasks,
      the unchanged 8,000-record reuse index, 12 new Dask checks, candidate,
      runtime and fresh proposed paths. All authorizations are false and
      execution identity is null. Preparation verifies 335 unchanged original
      paths and ten unchanged native-reader definitions. The proposed
      scratch/checkout remain absent. Forty focused orchestration tests pass.
      The separate historical audit also passes all 2,400 inputs, 9,600
      references, 4,800 captures, 12 old Dask comparisons and 10,400 records
      without execution or rescoring (`5b95726b...`). Final new immutable
      execution admission is still required.
    - [x] Implement and fixture-test the exact launch owner, without changing
      candidate science. The wrapper binds the v13 preparation and current
      dependency inventory, enforces its 74,710,430,800-byte minimum, hashes
      mixed JSON/text provenance correctly and rechecks controlling identities
      after the exhaustive audit. All 114 focused tests pass with 100% line
      and branch coverage of the two new modules. Namespace, disk, code/import,
      runtime, one-use authority and process/scientific failure checks prevent
      capture on invalid admission. The real preparation census/scientific
      metadata verify read-only. This tooling evidence is not a replay verdict
      or final immutable preflight. Preserve the old draft and closed results.
    - [ ] Freeze the exact reusable inventory, committed program closure,
      runtime and new write-once paths after tests and resource checks; repeat
      exhaustive no-write validation and record the exact one-use decision
      under the user's 2026-09-10 launch authorization. Keep the notebook and
      immutable replay candidate isolated; update the hourly monitor with
      actual session and execution identities immediately after launch.
      Bind the newly committed wrapper closure, not the older preparation's
      program closure, and a sufficient current resource record. Do not bypass
      its exact 74,710,430,800-byte minimum or invoke the staged runner directly.
    - [ ] Complete and investigate the replacement cumulative terminal.
      Process/evaluator fixes and retries require tested, newly frozen
      identities and fresh namespaces while preserving completed evidence.
      Scientific failure remains terminal: investigate and recommend repairs,
      without tuning, rescoring or changing the candidate under retry authority.
      Fresh seed-disjoint evidence remains a separate admission, not part of
      this notebook-to-replay monitor.

  Review which earlier reference products can be reused byte-for-byte and
  which changed candidate paths require new cumulative measurements. Previous
  passes and the scoped incumbent-uncertainty acceptance do not automatically
  transfer to changed science. Freeze exact execution identities, the
  unchanged binding scientific rules, population, sample/power rationale,
  disk budget and end-to-end time estimate before any approved run. Preserve
  all known-risk geometries; target the user's sub-12-hour final-campaign
  budget and surface any conflict before execution. Run a separately approved
  unopened seed-disjoint sentinel only after the replacement's development
  and cumulative gates pass. Monitor long runs hourly, preserve complete
  terminal diagnostics and treat scientific failure as terminal. A small
  sentinel remains a falsification check, not a substitute for powered parity.

After the final R6-R6 campaign, preserve the exact verdict and classify every
failure under the pre-launch severity policy. Close development and hand off
to runtime/scalability if no serious issue remains; otherwise document the
bounded blocking issue for human disposition. F2, broader scientific repairs
and fresh qualification remain deferred, not completed. F1 and its validation
are now prerequisites to this final campaign. Documentation, limitations and
provenance belong in this handoff. Broad cleanup remains separate; Release
Please still owns releases, which require their own readiness gates.

#### Retained scientific-readiness checklist

The historical checklist below governs a scientific-readiness declaration,
not the newly separated development closeout. Its failed/open items remain
failed/open. The 2026-09-11 development decision above controls current work.

Historical candidate `95cfc76...` has a sealed cumulative replay. Its
evaluation did not pass every incumbent-retention confidence check, but the
human scientific owner accepted the narrowly bounded uncertainty and decided
that a multi-hour independent confirmation was not proportionate before the
remaining Phase 5 gates. The terminal result remains immutable and incomplete; the
exception permits progression but is not a statistical pass. Complete the
remaining steps in order. The later failed sentinel now requires R0--R6
above; the historical progression acceptance does not waive that failure or
the replacement R6 cumulative failure `7146f2e8...` or the v10 public-catalogue
witnesses. R6-C0--C7 and new candidate-bound evidence precede closeout. The
checked first item below records historical progression only, not acceptance
of `db8936b...` or `cc1db52e...`:

1. [x] **Seal and accept the cumulative evidence for progression.** Verify all
   2,400 current
   products and their exact candidate, source-tree, configuration, program,
   reference, incumbent, and execution provenance. Compile the atomic decision
   by reusing the authentic incumbent and retained released/master PyBDSF
   products; do not rerun unchanged science. Require every Aegean-parity,
   dual-PyBDSF-parity, like-semantics, and binding-safety check to pass.
   Absolute improvement objectives remain reported but cannot replace these
   gates. A scientific failure stops closeout and opens a new prospective
   review; it is not permission to tune or rescore the result.

   Decision `8d69ef44...` passes all Aegean and dual-PyBDSF checks, all safety
   checks, 364 of 368 incumbent checks, and shows no observed movement beyond
   margin. The four underpowered aliases reduce to two evidence patterns. An
   independent 90%-joint-power confirmation would require 4,608 new
   seed-disjoint Continuum images and is intentionally skipped under the
   2026-09-06 human risk acceptance. Preserve the exact incomplete status and
   disclose that the two pattern-level incumbent upper bounds remain
   unresolved. No future document may convert this scoped acceptance into a
   claim that every incumbent-retention confidence gate passed.
2. [ ] **Run one compact fresh held-out sentinel for the frozen production
   candidate.** This gate failed for `95cfc76...`; follow R0--R6 to qualify
   a replacement. The chronology below records closed attempts,
   not live retry instructions or transferable scientific approval.
   The earlier bounded release-blocking audit was recorded in
   `phase-5-production-candidate-audit.json`: the exact source tree is
   unchanged, but its then-current conclusion that no correctness, safety or
   public-contract defect required a new candidate is superseded by the
   failed sentinel and source-catalogue audit. Its two non-blocking structural
   improvements remain deferred; the newly confirmed science and publication
   defects do not.

   Pre-review `84c44215...` freezes the scientifically smallest useful
   falsification design: all 36 seed-disjoint adaptive-background risk cells
   at four realizations each, plus six compact public-contract guard cells at
   four realizations each. That is 168 512-pixel images, 168 Serial Hebog runs,
   168 released-PyBDSF runs, and 12 caller-owned existing-Dask comparisons.
   The implementation and exhaustive no-write validation are complete.
   Frozen non-executable identity review `d879c65e...` binds manifest
   `1dc84802...`, implementation decision `66e7a886...`, every runner,
   compiler, evaluator, fixture, runtime image and endpoint, and expected
   execution `df6b831b...`. Fourteen focused tests pass. The complete no-write
   preflight verified all 168 prospective seeds against 20,917 historical
   seeds in 46 manifests, the exact released-PyBDSF image and dependency
   inventory, 11.8 GiB free, and zero finder executions. The scientific owner
   approved that identity and execution shape on 2026-09-06, but the approval
   could not be consumed: the repository hook canonicalized the newly tracked
   pre-review JSON before execution, changing its byte identity without
   changing its content. Refreeze the semantically identical records and
   obtain renewed exact approval of replacement identity `d879c65e...` before
   starting any finder. Expected execution `df6b831b...` is unchanged. That
   approval was received on 2026-09-06 and is recorded in the exact one-use
   execution decision; one immutable two-worker execution is now permitted.

   The sentinel is a fresh overfitting and regression check, not a replacement
   powered parity campaign. The sealed cumulative evidence remains the basis
   for both PyBDSF, Aegean, compact, and incumbent claims; only Rapthor's
   released PyBDSF reference is reexecuted. Require every risk and guard cell,
   hard safety floor, practical PyBDSF margin, product/provenance check, and
   Serial/Dask comparison to pass. No pooled score may hide a failed geometry,
   trigger stratum, or endpoint. Any failure stops closeout and opens a
   prospective root-cause review without tuning, rescoring, adaptive sample
   size, or reconfirmation.

   The one-use `d879c65e...` execution was consumed on 2026-09-06 and failed
   closed after about 130 seconds, before the first completed realization and
   before any PyBDSF execution. The atomic terminal record reports
   `operational-fail` and has SHA-256 `965454ea...`: the successor compiler
   still requires legacy
   `hebog-segment-N` island identifiers, whereas the frozen public candidate
   correctly emits the stable component identities introduced by the
   owner-domain repair. This is evaluator integration failure, not scientific
   evidence for or against Hebog. Preserve the terminal output and scratch;
   repair the compiler test-first, freeze replacement identities, obtain a new
   exact one-use approval, and then rerun the unchanged 168-image sentinel.

   The test-first repair is complete at commit `26f13a7...`. It links stable
   Gaussian-component identities to native measurement labels exclusively
   through `SourceAssociationResult.components`, rejects missing or
   inconsistent ownership, and applies the same adapter to Serial pairs and
   existing-Dask comparisons. It does not modify `src/hebog`, candidate
   science, the population, comparator, evaluator, thresholds, or margins.
   Fifty-five focused tests, Ruff, Pyright, and the complete pre-commit suite
   pass. Complete no-write preflight passes with 10.8 GiB free and zero finder
   executions. Replacement identity-review SHA-256 is `3b22cb48...` and
   expected-execution SHA-256 is `b0c35a73...`; the 2026-09-06 user authority
   approves all required retries and is recorded in one-use decision
   `0b4856f8...`.

   That retry preserved its 145 completed pair summaries and atomically failed
   before Dask comparison with terminal SHA-256 `441f312f...` because the
   wrapper treated a documented public zero-source result as missing science.
   The first empty-result repair was too narrow: it accepted the public result
   only when RMS was unusable. Its unchanged retry reached the same boundary
   and atomically failed as terminal `e849a95d...` because Hebog can correctly
   produce no accepted island while retaining a scientifically usable RMS
   plane. RMS availability describes background estimation, not the public
   source population.

   The final evaluator-only rule is therefore bound to the public contract:
   compile an empty catalogue and zero label plane only when source,
   Gaussian-component, and island counts are exactly zero and the captured RMS
   shape equals the input. Nonzero public counts or inconsistent shapes still
   fail closed; non-empty products retain the exact stable ownership adapter.
   The new pre-review preserves all three failed terminals, the unchanged
   candidate, seed-disjoint population, released-PyBDSF runtime, evaluator,
   metrics, thresholds, and margins. Implementation decision `796abeff...`,
   replacement identity `ad9e2b1c...`, expected execution `7c40f8b1...`, and
   its distinct write-once output namespace are frozen under the user's
   standing evaluator-repair and all-retries authority.

   That retry completed 144 pairs and then atomically recorded terminal
   `38438265...` when released PyBDSF explicitly found no islands and emitted
   its valid zero-row, schema-free Gaussian FITS table. The comparator child
   incorrectly required the normal non-empty column schema before it could
   publish the empty result. The final comparator adapter independently checks
   this boundary in the isolated child and host: only a zero-row catalogue
   paired with an all-zero native PyBDSF label plane is empty science;
   nonempty malformed tables, positive labels, and count disagreement remain
   operational failures. The PyBDSF image, configuration, source-finding
   science, metrics, thresholds, and margins remain unchanged. Implementation
   decision `c4e9cb03...`, identity `b67d8776...`, and expected execution
   `1f4eeef6...` bind the fourth write-once retry and all prior failures.

   The repaired sentinel then completed operationally on 2026-09-07. Atomic
   terminal SHA-256 `f542c7db...` binds the exact `95cfc76...` candidate,
   168 fresh Hebog and 168 released-PyBDSF executions, 12 equal
   Serial/existing-Dask comparisons, valid paired products and ownership, and
   `pooling_used=false`. This is a terminal scientific failure: only 7 of 42
   cells pass and 35 fail, with all 12 shell cells, all 12 curved-filament
   cells, 6 of 12 mixed compact/extended cells, and 5 of 6 compact guard cells
   failing at least one frozen endpoint. Completeness, duplicate fraction,
   and merge fraction pass every cell, while the most frequent failures are
   integrated-flux p95 (30 cells), integrated-flux median (29), split
   fraction (28), position median and p95 (25 each), and absolute y-offset
   (22). The write-once result remains `status=fail` and `passed=false`.
   Therefore this checklist item records a completed falsification, not a
   passed closeout gate. Phase 5 closeout stops here; no retry, tuning,
   rescoring, threshold change, or readiness finalization is permitted from
   this result. A prospective scientific root-cause review is required before
   a new candidate or campaign can be proposed.

   The prospective root-cause review is complete on 2026-09-07. Exact
   non-executable review SHA-256 `f94d0455...` binds terminal `f542c7db...`,
   its 168 preserved array-free pairs, the frozen compiler/evaluator, and both
   finder identities. It confirms a like-semantics evaluator defect: Hebog
   component rows were scored against component-owner labels, while PyBDSF
   Gaussian rows were scored against island labels and carried source-grouped
   flux. Hebog has one catalogue row per native support in all 168 images;
   PyBDSF has more Gaussian rows than native supports in 150, so the binding
   split, merge, duplicate, reliability, flux, and position comparisons mix
   source, component, and island domains. Of 186 failed endpoints, 180 depend
   on that representation and cannot support a parity or inferiority decision
   without prospective alignment. This does not imply they would pass after
   alignment, and the failed terminal remains immutable with no retrospective
   rescore.

   Six binary-mask failures are label-invariant and remain valid candidate
   risks. Fourteen adverse flux images and ten adverse position images also
   lack a Hebog component-count excess, so residual photometry or astrometry
   defects remain possible. The similar below-, boundary-, and above-trigger
   failure burden excludes adaptive-background activation as the primary
   cause. The next approval-gated task is test-first, fixture-only evaluator
   alignment: use Hebog associated-source rows and source-union ownership
   against PyBDSF rows grouped by native source identity; keep individual
   Hebog/PyBDSF components in a separate report-only diagnostic; retain binary
   support metrics as binding; and reproduce the residual mask, flux, and
   position risks without using viewed data. Only after every fixture and
   Serial/existing-Dask gate passes may a new seed-disjoint sentinel identity
   be frozen and separately approved. Phase 5 remains open until that new
   like-semantics sentinel passes.

   The scientific owner approved exact review `f94d0455...` on 2026-09-07.
   The authorized fixture-only implementation is complete without modifying
   `src/hebog` or either finder's products. The prospective schema makes
   source rows and individual components separate records, binds truth
   metrics only to an explicitly supplied source-union owner plane, leaves
   component topology report-only, and retains positive-support mask metrics
   as binding. It deliberately rejects attempts to infer a source partition
   from component positions: a future finder-specific adapter must supply and
   validate the exact source union. Array-free records retain canonical source
   membership, component ownership, union counts and membership digests, and
   fail closed when those fields or their outer digest disagree. The aligned
   wrapper validates these semantics before calling the byte-identical frozen
   parent evaluator, so no threshold, margin, confidence rule, or gate changed.

   The fixture matrix and caller-owned two-worker existing-Dask comparison
   pass, including multi-Gaussian PyBDSF sources, multi-component Hebog
   sources, two sources sharing one native island, connected three-peak
   topology, empty results, residual flux/position errors, adaptive-trigger
   strata, relabel-invariant masks, malformed ownership, and execution-order
   invariance. This establishes the evaluator contract only; it neither
   rescored the viewed 168-image terminal nor established parity. Before any
   new run, separately review and freeze the finder-specific source-union
   adapters and a new seed-disjoint sentinel identity, then obtain exact
   one-use execution approval.

   The separate non-executable adapter review is complete as exact review
   `02b46eca...`. Hebog has a direct, lossless adapter: project its persisted
   association memberships through the stable measurement-component owner
   plane and use the terminal associated-source catalogue for source flux and
   position. Released PyBDSF 1.14.1 exposes source and Gaussian catalogues plus
   an island plane, but no source-owner image. Its prospective adapter must
   therefore write a clearly named
   `pybdsf-source-model-dominance-v1-derived-topology` diagnostic inside the
   pinned child: use native `srl` rows for source observables, group accepted
   `gaul` rows by `(Isl_id, Source_id)`, and partition a multi-source island by
   the largest summed source Gaussian model with a frozen canonical tie-break.
   Whole islands with no accepted source remain unowned source topology while
   continuing to count in the binding binary-mask lane; fabricating a source,
   dropping that mask support, or duplicating an island for every source is
   forbidden. This requires a fixture-only amendment to the aligned contract,
   which currently requires every native pixel to have a source owner.

   The review compared both finder schemas to the same analytic-truth
   evaluator and does not treat PyBDSF as truth. It read no viewed summaries,
   executed neither finder, and changed no source-finding science. The human
   approved exact review `02b46eca...` on 2026-09-07 for its named,
   fixture-only implementation scope.

   That implementation is complete. A validation-only Hebog adapter now
   projects the exact persisted association memberships through measurement
   component ownership; a validation-only PyBDSF adapter retains native `srl`
   observables and partitions multi-source islands using the reviewed summed
   accepted-Gaussian model-dominance rule. The aligned schema is version 3:
   whole fitless PyBDSF islands remain explicitly unowned in source topology
   while continuing to contribute to binding binary-mask metrics, and compact
   count, pixel-count, and membership digests distinguish modelled from
   unowned native support. Modelled islands must still be partitioned
   completely, and rehashing cannot admit altered topology evidence.
   Both adapters remain under `scripts/validation`; the production
   `src/hebog` tree is unchanged at SHA-256 `8da21e86...`, so the frozen
   candidate and notebook identities remain valid.

   Sixty-three focused adapter, compiler, validation, and caller-owned
   two-worker existing-Dask cases pass, including missing and duplicate
   source/Gaussian membership, reused local IDs, exact ties, zero-owned
   sources, fitless-only and mixed islands, row and completion order, invalid
   owner planes, and retained-evidence tampering. This is prospective contract
   evidence only: neither finder was executed and viewed results were not
   rescored.

   The separate successor freeze is now complete. New manifest
   `phase-5-compact-held-out-source-union-sentinel` contains the unchanged 42
   reviewed cells on 168 fresh, historically disjoint seeds
   `2026971001..2026971168`. The isolated PyBDSF child is prospectively bound
   to native `srl` source rows, `gaul` components, island ownership, and its
   derived source-union owner plane; all five products must hash-match before
   the parent can compile schema-v3 evidence. The Hebog arm binds its native
   associated sources and measurement-component ownership to the same
   analytic truth compiler. Both arms retain components as diagnostic-only,
   and fitless PyBDSF islands remain binding binary support without fabricated
   sources. Valid schema-free zero-row PyBDSF source and Gaussian catalogues
   are accepted only as the jointly empty case, while their native fitless
   island support remains represented explicitly as unowned.

   Identity review SHA-256 `7d133492...`, implementation decision
   `c84f47f4...`, and manifest `1c2ce27a...` pass the complete no-write
   contract. Expected execution SHA-256 is `c897af7c...`: exactly 168 current
   Hebog Serial executions, 168 released-PyBDSF executions, 12 caller-owned
   existing-Dask comparisons, two workers, and one new atomic terminal. The
   identity itself remains non-executable. The 2026-09-07 exact one-use human
   decision authorized only that identity and expected execution; the old
   viewed terminal and decisions cannot authorize it.

   That source-aligned execution completed only as immutable operational-fail
   terminal SHA-256 `331e36a5...`: PyBDSF's first child result exposed a
   case-sensitive adapter typo, `N_Gaus` instead of its native `srl` column
   `N_gaus`. No pair summary was accepted, no Dask comparison ran, and the
   terminal contains no scientific result. Static inspection of the pinned
   PyBDSF 1.14.1 package and the already approved adapter review independently
   confirm `N_gaus`; candidate science, comparator configuration, evaluator,
   gates, population, and manifest therefore remain frozen.

   Red-first repair fixtures now pass for the exact native schema and prove
   that only the isolated PyBDSF child is replaced. Non-executable repair
   identity SHA-256 `524f6fd4...`, implementation decision `22c6e9d8...`,
   and expected execution `926635cd...` bind failed-terminal lineage, the
   unchanged 168-seed manifest, 348 total finder executions, two workers, 12
   existing-Dask comparisons, and a new write-once namespace. The complete
   no-write preflight passes with `finder_execution_started=false`. The
   user's standing process-repair and retry approval authorizes this exact
   replacement once; complete it from an immutable checkout before advancing
   to item 3.

   The column-case replacement also completed as operational-fail terminal
   SHA-256 `9d96a9ed...`, again before accepting any pair summary. Static
   inspection of PyBDSF 1.14.1 shows why: `Source.ngaus` declares internal
   output name `N_gaus`, but the native `srl` FITS writer does not include the
   `ngaus` attribute at all. The exact persisted `gaul` table does include
   `(Isl_id, Source_id)` for every accepted Gaussian, so membership supplies
   the same count without guessing or changing PyBDSF output.

   A second red-first process repair derives the count exclusively from those
   exact grouped `gaul` rows and then reuses the unchanged source-union
   adapter, including its one-to-one source/group and count validation.
   Non-executable identity SHA-256 `07e0e8ec...`, implementation decision
   `3e085e72...`, and expected execution `0c7fd449...` retain all candidate,
   comparator, population, endpoint, margin, and execution-shape bindings in
   another new write-once namespace. The standing process-repair and retry
   approval authorizes this replacement once; complete its immutable
   preflight and execution before advancing to item 3.

   That replacement also ended before accepting a pair summary, with
   operational-fail terminal SHA-256 `a6a119fe...`. Its Gaussian-membership
   child is correct, but the parent installed it through a mutable module
   global. macOS `ProcessPoolExecutor` spawn workers re-imported the previous
   importable pair worker and therefore selected the previous column-case
   child. This is process dispatch only: no science, comparator configuration,
   truth, evaluator, threshold, margin, seed, or gate changed.

   A third red-first repair now puts the complete pair worker in a stable
   importable module and selects the Gaussian-count child explicitly inside
   every spawned process. A real fresh-spawn fixture proves the selected child
   and the parent runner verifies the importable callable identity.
   Non-executable identity SHA-256 `c498a90d...`, implementation decision
   `1ff50535...`, and expected execution `f70adb97...` preserve the same 168
   seeds, 348 finder executions, two workers, 12 existing-Dask comparisons,
   science, comparator, evaluator, and gates in a distinct write-once
   namespace. Pass its complete immutable no-write preflight and consume only
   that retry before advancing to item 3.

   The spawn-safe retry completed all 168 Hebog and 168 released-PyBDSF runs
   plus all 12 caller-owned-Dask comparisons and published scientific terminal
   SHA-256 `ca03240d...` with `status=fail`. Provenance and execution shape
   verify exactly; this is not an operational failure. Both finders were
   measured independently against the same analytic injected truth, then the
   frozen practical-margin parity rule was applied. Twenty-four of 42 cells
   pass and 18 fail, with 59 failed cell-endpoints. The dominant failures are
   reliability in 13 cells, integrated-flux median and p95 in eight each,
   position or mean-offset endpoints in multiple cells, and severe
   completeness/association failures in the connected two- and three-peak
   compact guards. All 12 Serial/existing-Dask comparisons pass. This
   predeclared one-look sentinel therefore blocks closeout for candidate
   `95cfc76...`; it must not be tuned, rescored, or retried as qualification
   evidence.
3. [ ] **Confirm the exact candidate's engineering and public contract.** Run
   focused regression and executor-invariance tests, `just coverage`,
   `just check`, `just test-equivalence`, `just docs-build`,
   `just package-smoke-test`, and `just pre-commit`. Reconfirm the reviewed
   6.0-second 3,000-pixel incremental budget or record a packet-bound proof
   that its code path and identity are unchanged. Verify installed-wheel FITS
   input, catalogue/RMS/mask/diagnostic products, errors, schemas, atomic
   writes, bounded execution, retry/order invariance, and reproduction
   commands. This step is blocked because item 2 completed with a scientific
   failure; repository validation used to preserve the terminal evidence does
   not constitute this candidate-readiness gate.
4. [ ] **Document and finalize scientific readiness.** Update the campaign
   overview, API reference and radio-astronomer workflow, supported profiles,
   scientific interpretation, limitations, reproducibility instructions,
   provenance index, `LOG.md`, and the Phase 6 handoff. Rebuild the fail-closed
   readiness packet without the deferred Rapthor profile, obtain separate
   packet-bound radio-astronomy and engineering acceptance, and publish one
   terminal readiness record. Do not prepare a version, tag, changelog, or
   release artifact; Release Please handles the next release. This step is
   blocked by the failed sentinel and must not publish a readiness record for
   candidate `95cfc76...`.

Scientific readiness is established when every remaining gate row and items
2--4 above pass for
one exact candidate and the terminal readiness record is published. The
readiness record must bind and disclose the scoped cumulative-retention
exception. Release Please then owns the standalone Hebog release; the Phase 5
work does not manually prepare or execute it. Rapthor integration, complete
`filter_skymodel` performance, cutover, facility scale, and a
Rapthor-integrated release remain Phase 6 or later work.

#### Historical Phase 5 evidence

Campaign chronology and incident analysis live in `LOG.md` and
`docs/reference/phase-5-campaign-overview.md`; exact identities, consumed
authorities, and terminal decisions live in `config/contracts/` and the
ignored evidence store. Commit `707478c...` is the last plan revision that
retains the former inline execution chronology. Closed failures remain
immutable evidence and must never be rerun or rescored merely because their
narrative was removed from this current-work plan.

### Phase 5.5: post-release historical-tooling cleanup

Begin only after Phase 5 is terminally closed and Release Please has durably
recorded the standalone Hebog release. This maintenance phase is deliberately
outside the scientific release boundary: it reduces repository complexity
without delaying parity, qualification, readiness, or release. It no longer
blocks Phase 6/7 runtime and scalability work under the 2026-09-11 decision;
retain the current validation paths until cleanup can safely proceed.

- [ ] Inventory Phase 5 validation scripts, freezers, overlays, and
      lifecycle-only tests. Identify the canonical current
      generators/evaluators and every file still used by notebooks, current
      regression tests, final readiness, or reproducibility documentation.
- [ ] Remove superseded one-use executors and lifecycle tests only when no
      maintained code or final evidence imports them. Retain behavioural
      regression tests and shared analytic fixtures even when their original
      campaign harness is removed.
- [ ] Do not modify `src/hebog/` in this phase. If cleanup exposes a production
      defect, open a separately reviewed candidate change with proportionate
      scientific regression gates rather than folding it into repository
      tidying. Development-tool-only deletion does not require replaying
      scientific products.
- [ ] Preserve compact hash-bound contracts and terminal decisions in main
      history, keep large generated products outside Git, and record each
      removed path, its last immutable commit and SHA-256, and its replacement
      in `docs/reference/phase-5-provenance-index.md`. Git history is the
      recovery mechanism; do not create a separate provenance branch.
- [ ] Remove obsolete scratch only after confirming that notebook, readiness,
      and reproducibility inputs remain available. Run affected focused tests,
      `just check`, `just docs-build`, and `just pre-commit` before completing
      the maintenance phase.

### Phase 6: Rapthor integration, minimum performance, and early release

Runtime/scalability engineering may begin after the final Phase 5 campaign
and documented development-closeout decision, even while scientific
qualification remains incomplete. Do not delay it for deferred F2 work or broad
historical-tooling cleanup. Scientific readiness, the restricted Rapthor
profile, operational acceptance and performance gates remain required for
release/default cutover; the work-order change does not waive them.
Its objective is the earliest safe, useful
improvement for Rapthor, not the final scientific or computational optimum.
Do not delay a Rapthor-integrated experimental release for a longer-term
absolute target or maximum facility scale once all binding science,
compatibility, operational, and minimum complete-path performance gates pass.

- [ ] Freeze the current candidate as a **known-issues engineering baseline**,
      preserving its final campaign verdict and deferred defect inventory.
      Profile complete FITS-to-products and Rapthor filtering paths; do not
      begin by changing scientific algorithms or weakening thresholds.
- [ ] Establish matched released/master PyBDSF and Hebog complete-path
      timing, CPU/RSS/I/O and Dask task/transfer/spill baselines with warm-up
      plus at least five measured repetitions. Cover affected/adjacent size
      anchors and crossovers; record unavailable references rather than
      substituting them or claiming a speedup from old notebook timings.
- [ ] Prioritize measured I/O, repeated work, fit batching and bounded
      executor/storage costs. Run scientific non-regression against the
      frozen baseline for each optimization and preserve Serial/Dask,
      partition/order/retry invariance. Existing failures must not worsen or
      disappear through changed semantics; baseline equality is not a new
      scientific qualification pass.
- [ ] Bring forward Phase 7 bounded-memory and graph-size engineering and
      local scaling experiments alongside runtime work. Facility-scale
      execution still needs an admitted data host/resource envelope; do not
      infer 100,000-square or hundreds-of-workers support from small tests.

- [ ] Complete the restricted Rapthor profile decision.
      Begin only after the all-check PyBDSF-parity, Hebog-quality-retention,
      cumulative-replay, and fresh-qualification gates pass. Audit the pinned
      Rapthor/LSMTool consumer to identify every scientifically material field,
      filename, mask semantic, and filtering decision; this may narrow the
      integration contract only after general source-finder parity and cannot
      excuse an earlier failed check. Restore the controlled real inputs,
      freeze their canonical pre-filter component population, and run compact
      and continuum Hebog masks through the exact pinned LSMTool filtering
      operation against both PyBDSF references. Compare true/apparent, bright,
      extended, edge, masked, sparse, and crowded safety strata. Select
      `compact` only when overall agreement is at least 99.5% and every safety
      stratum passes; otherwise select `continuum`. Record a write-once profile
      decision. It selects workflow behaviour only and does not by itself
      authorize integration, cutover, or release.
- [ ] Build a Phase 6 Rapthor-readiness packet that binds the terminal Phase 5
      scientific-readiness record, the restricted profile decision, integration
      evidence, complete-path performance, operational gates, and independent
      acceptance without altering the Phase 5 release record.

- [ ] Add readable acceptance scenarios for empty/corrupt inputs, restart,
      retry, backend selection, fallback, dual-run reporting, and decisions.
- [ ] Add the Hebog backend; split true-sky, flat-noise, and final filtering
      into restartable tasks and run concurrently only when admitted resources
      permit.
- [ ] Preserve feature-flagged PyBDSF fallback and dual-run comparison; remove
      the PyBDSF subprocess escape only from the Hebog path.
- [ ] Run matched complete `filter_skymodel` benchmarks against released and
      pinned-master PyBDSF across a frozen early-release matrix containing
      every input size and workload Rapthor will support initially, plus both
      sides of measured execution crossovers. The 30,000- and 100,000-square
      facility anchors remain Phase 7 unless the initial Rapthor envelope
      requires them.
- [ ] Require all science and Rapthor compatibility gates, at least 50% lower
      complete matched median wall time than Rapthor's released PyBDSF, better
      complete performance than pinned PyBDSF master, runtime confidence
      bounds, retry/resume, and memory gates to pass before default cutover.
- [ ] Publish an explicit Rapthor-integrated experimental `0.x` release when
      the same minimum gates pass and the feature-flagged PyBDSF fallback
      remains available. Declare the validated image-size, workload, resource,
      and storage envelope and fail closed or use the fallback outside it.
      Further absolute scientific improvement and facility-scale optimization
      continue after this milestone.

### Phase 7: scale-out and continued optimization

Bring forward bounded-memory, executor and graph-size engineering under the
2026-09-11 priority decision; a release is not required to start that work.
Later facility qualification still requires its controlled resource envelope.
Every optimization must retain existing passing checks and show no additional
scientific regression against the known-issues baseline. All parity, retention
and compatibility gates must pass before readiness/cutover; throughput,
memory and scale-out gains cannot compensate for scientific regression.

- [ ] Complete a shared serial/local/Dask executor contract for ordering,
      serialization, errors, cancellation, retry, determinism, and resources.
- [ ] Implement persistent local threaded and existing-client Dask executors;
      never create nested pools or clusters.
- [ ] Build bounded map, boundary-summary, tree-reduction, and materialisation
      graphs; choose batching and executor crossovers from measured resources.
- [ ] Qualify deployment Zarr atomicity, concurrency, codec/chunk geometry,
      restart, cold/warm throughput, and failure recovery.
- [ ] Record task/graph size, scheduler load, occupancy, transfer, spill,
      stragglers, storage throughput, and peak worker/aggregate memory.
- [ ] Prove scientific equivalence and topology independence across 1, 10, 50,
      100, and at least 200 workers.
- [ ] Complete the 100,000-square qualification without a full worker plane and
      within all resource, recovery, runtime, and scaling gates.
- [ ] Extend the matched complete Rapthor performance matrix through the
      30,000- and 100,000-square anchors and every newly measured crossover
      before claiming support for those sizes.
- [ ] Continue improving the reported absolute scientific targets and complete
      throughput curve without weakening parity, retention, or compatibility.

### Phase 8: production hardening and `1.0` readiness

- [ ] Enforce portable test lanes in CI and run qualification, benchmark, and
      scalability lanes on controlled runners.
- [ ] Publish current API, configuration, schemas, provenance, reproduction,
      limitations, and a non-Rapthor serial workflow.
- [ ] Add structured timings and scientific summaries; complete dependency,
      security, licensing, packaging, and reproducibility review.
- [ ] If native code exists, qualify every supported wheel/source-build and
      fallback path.
- [ ] Continue the Release Please-managed experimental `0.x` sequence through
      Rapthor-integrated Phase 6 releases; prepare `1.0.0` only after
      operational soak and the full definition of done.

## 8. Performance matrix and protocol

### 8.1 Frozen anchors and component budget

| Regime | Sizes | Primary concern |
| --- | --- | --- |
| Small | 256, 512, 1,024 | startup, I/O, validation, dispatch |
| Representative | 3,000 | dual-PyBDSF latency and component budgets |
| Large local | 8,000, 10,000 | memory-rich batching and Dask crossover |
| Distributed | 30,000 | storage, occupancy, reconciliation, graph overhead |
| Extreme | 100,000 | out-of-core correctness and facility scaling |

Add anchors on both sides of measured storage, batching, partition, or
executor crossovers. At each size retain sparse, normal, and dense/extended
workloads.

Phase 6 early releases gate only the frozen initial Rapthor support envelope;
unsupported larger inputs must fail closed or retain the PyBDSF fallback.
Phase 7 and the `1.0` definition of done require the complete matrix, including
the 30,000- and 100,000-square anchors. No result from a smaller tier may be
extrapolated into an unmeasured size or worker-count claim.

| 3,000-square component | Budget |
| --- | ---: |
| FITS input, validation, beam, WCS | 1.5 s |
| True-sky background and RMS | 4.0 s |
| Detection, deblending, durable image products | 3.5 s |
| Compact measurement and fitting | 2.0 s |
| Multiscale processing and merge | 6.0 s |
| Catalogue and filter outputs | 2.0 s |
| Flat-noise branch, concurrent | 4.0 s |
| Dask scheduling/transfer on critical path | 2.0 s |

The expected true-sky critical path is near 19 seconds, with flat-noise work
hidden by concurrency. This table guides diagnosis; only matched complete-path
evidence decides acceptance.

### 8.2 Benchmark requirements

1. Freeze dataset, Hebog, Rapthor, released/master PyBDSF, Python, dependency,
   configuration, product, and runtime identities.
2. Match host, CPU affinity, core/thread budget, RAM, storage, cache policy,
   worker topology, and native thread limits; avoid unrelated workloads.
3. Run one warm-up and at least five measured repetitions; retain every value,
   median, range, dispersion, and required bootstrap interval.
4. Record wall/CPU time, peak and aggregate RSS, I/O, task/graph size,
   transfer/spill, failures/retries, tile/halo geometry, summaries, occupancy,
   storage throughput, and headroom. Record unavailable instrumentation with a
   reason, never zero.
5. Interleave implementations/sizes where practical and retain both sides of
   execution crossovers. Compare with the previous reviewed Hebog curve.
6. Evaluate science before performance and store machine-readable results
   under ignored `benchmark-results/`; commit only compact reviewed summaries
   and reproduction commands.
7. For scale runs, add scheduler resources, strong/weak scaling, stragglers,
   reduction depth, store/chunk/codec details, atomicity, and recovery cost.

## 9. Principal risks

| Risk | Required control |
| --- | --- |
| Qualification or campaign overfitting | Freeze populations/gates first; one look; never rescore failed evidence. |
| Binding strata remain underpowered | Freeze endpoint-level power calculations and independent realization counts before one-look execution; enlarge the population prospectively. |
| The Hebog retention target becomes an impossible synthetic envelope | Bind one closed incumbent candidate before viewing the replacement; never select a different historical best per endpoint. |
| Source-level rows are treated as independent replicates | Pair and resample whole input realizations or observational units; preserve within-image dependence. |
| Planning assumptions become terminal observed-data gates | Use planning variance for prospective sample size and assumption audit only; decide non-inferiority from the frozen observed-data confidence interval. |
| Compiler or comparator defect changes science | Test matching/measurement independently; checksum-bind programs; preserve closed compilers. |
| Internal evidence passes but the public entry point is unusable or divergent | Qualify the installed `hebog.find_sources` path, bind algorithm digests, and require byte-identical Serial/existing-Dask product checks before release. |
| Support topology is confused with source photometry | Keep catalogue/source, component, and support records distinct; measure flux on original pixels. |
| Mask background hides errors | Evaluate precision/recall/IoU on valid pixels plus object splits/merges. |
| Adaptive RMS/background follows bright extended emission | Compare coarse and adaptive estimates on prospectively injected extended sources around the adaptive trigger; retain truth-linked mask coverage, fragmentation, photometry, and local-noise diagnostics. |
| Low-SNR/reference variability | Report truth-based curves and same-tool scatter; pin both PyBDSF identities. |
| Compact tuning regresses earlier science | Maintain the cumulative Phase 4/5 regression ledger and stronger-Hebog envelopes. |
| Extended or blended populations disappear in aggregates | Freeze morphology/scale/blend strata and explicit unavailable/failure outcomes. |
| Tile/order state changes results | Use global ownership, sufficient halos, property tests, and deterministic reconciliation. |
| Full planes, islands, or catalogue fan-in exhaust memory | Use bounded tiles, summaries, shards, and hierarchical reductions. |
| Dask or storage overhead erases gains | Measure complete paths, batch coarse work, publish data once, and retain efficient local execution. |
| Memory-rich nodes are underused or small inputs slow down | Plan from admitted resources and measured crossovers; keep size-stratified regression curves. |
| Rapthor concerns leak into the core | Enforce inward dependencies and a non-Rapthor serial workflow. |
| Compact Rapthor profile is mistaken for general science | Make profile explicit in configuration/products and retain continuum qualification. |
| Performance complexity harms maintainability | Optimize only from profiles; isolate kernels; retain readable serial oracles. |
| Native acceleration harms portability | Apply the native gates and require complete wheel, safety, licensing, and fallback evidence. |
| Experimental releases imply readiness | Keep fallback and limitations explicit until all science, scale, and soak gates pass. |
| Early release is delayed by maximum-scale work | Publish a bounded supported envelope after Phase 6 gates; defer 30,000/100,000 qualification to Phase 7 without extrapolation. |

## 10. Definition of done

Hebog may replace PyBDSF by default in Rapthor and release `1.0.0` only when:

1. Development, regression, and held-out qualification cover compact,
   blended, extended, low-SNR, edge, invalid-pixel, varying-noise, and
   boundary cases without qualification tuning.
2. Every reviewed scientific gate passes for serial and Dask execution,
   including public multi-survey evidence and independent radio-astronomy
   approval of the general continuum profile.
3. Every gate-designated complete `filter_skymodel` case satisfies both
   dual-PyBDSF runtime confidence bounds and the Hebog-on-Hebog 5% regression
   rule.
4. The 100,000-square qualification is scientifically and partition invariant
   on 100 and at least 200 workers without a full worker plane and within all
   memory, spill, scheduler, recovery, runtime, and scaling gates.
5. Rapthor supports backend selection, dual-run comparison, restart/retry, and
   safe PyBDSF fallback; operational soak passes before default cutover.
6. Public API, configuration, schemas, products, provenance, limitations,
   benchmarks, architecture, glossary, and a non-Rapthor workflow are current.
7. Ruff, Pyright, packaging, branch-aware coverage, architecture tests,
   controlled qualification/benchmark monitoring, dependency/security/
   licensing review, and any native distribution requirements all pass.
