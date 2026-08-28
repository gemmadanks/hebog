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
compensate for failed science.

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
  completion, cross-scale ownership, bounded tiling semantics, and incremental
  performance.
- Phase 6 owns production executor planning, deployment-store qualification,
  hierarchical Dask graphs, spill/recovery, and facility-scale execution.
- Phase 7 owns Rapthor integration and complete dual-PyBDSF performance.
- Phase 8 owns release hardening and production-readiness review.

## 3. Acceptance gates

### 3.1 Scientific gates

Analytic and injected truth are the primary scientific oracles. Released
PyBDSF is the current Rapthor compatibility oracle; pinned PyBDSF `master` is a
second binding reference. Aegean is binding for applicable compact, blended,
and Gaussian-component populations. No single finder is scientific truth.

Hebog must pass every applicable absolute gate and be non-inferior to each
binding reference on every governed metric and stratum. Results are
conjunctive: one population or metric cannot compensate for another.
Predeclared one-sided confidence intervals determine non-inferiority; a worse
point estimate with an inconclusive interval is not an improvement.

The main cross-project gates are:

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

Additional rules:

- Mask precision, recall, and intersection over union are measured over valid
  pixels; island matches, splits, merges, and duplicates are reported
  separately so background pixels cannot hide errors.
- Detection or wavelet coefficients establish support and provenance only.
  Flux, centroid, shape, and uncertainty use the reconciled support and
  original background-subtracted pixels.
- Compact components, grouped sources, support/islands, and sky-model
  components are distinct governed populations.
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
- Retain a reviewed Hebog curve across all supported sizes. A new/previous
  median ratio whose lower 95% confidence bound exceeds `1.05` is a regression
  unless an explicit trade-off is approved.
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
result = find_sources(request, config, executor)
```

Requests contain paths, identifiers, immutable scientific configuration, and
small serializable metadata. Results contain product paths, counts, timings,
schema versions, and small provenance records. Neither boundary contains open
files, mutable full images, scheduler clients, or workflow state.

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
| 0 | Froze Rapthor contracts, released/master PyBDSF baselines, datasets, schemas, and architecture decisions. | Facility-scale evidence remains Phase 6/8. |
| 1 | Delivered bounded FITS/Zarr I/O, partition ownership, restartable products, and pipeline-neutral records. | Deployment-store qualification remains Phase 6. |
| 2 | Delivered vectorised background/RMS estimation, adaptive regions, partition invariance, and executor parity. | Preserve the reviewed curve and science gates. |
| 3 | Delivered deterministic detection, labelling, compact deblending, masks, and explicit extended-island deferral. | Deferred/extended work is Phase 5. |
| 4 | Delivered compact measurement, SciPy fitting, uncertainty calibration, catalogue construction, and compact regression evidence. | The compact branch remains subject to every later regression gate. |

Phase 4U is the compact regression baseline: its fresh qualification passed
77 binding absolute gates, 20 paired endpoints against each PyBDSF reference,
and five stronger-Hebog envelopes. Earlier Phase 4/4R/4S/4T failures remain
closed historical evidence and were not rescored.

### 6.2 Phase 5 decisions and latest evidence

Phase 5 is open. The multiscale implementation, combined products, bounded
execution proof, compact regression, original powered qualification, and
incremental performance budget are complete. Recovery decision `cd3eacfb...`
passes every binding Continuum and compact gate; final baseline qualification
decision `d4db4d7f...` also passes.

The public/challenge one-look remains closed failure evidence: decision
`954077e9...` fails SDC1 completeness, reliability, and flux-error gates, and
independent review `320f57f5...` attributes material defects to
source-association semantics and deep-image overmerging without authorizing
tuning or rescoring. The first corrected cumulative ledger `1ac6deb2...`
retains compact science but fails with 37 Continuum like-semantics regressions.

The source-association candidate addressed those regressions prospectively.
Its first replay stopped after 58 products on a measurement-completeness
defect. Repair candidate `6184a32...` then completed all 2,400 candidate
products, but the compiler rejected the binding `source-associated-*`
catalogue identity because its adapter still required one legacy
`hebog-segment-N` label per row. No ledger was published and both replay
authorizations are consumed. The complete shard set remains preserved for an
evaluation-only repair; no candidate rerun is required or authorized.

The closest passing Continuum margins remain mask recall 0.90103 against 0.90
and mask-precision regression UCL 0.04940 against the pinned-master 0.05
margin. Section 7 now contains the single authoritative Phase 5 closure
sequence; detailed campaign chronology and immutable identities remain in
`LOG.md` and `config/contracts/`.

## 7. Delivery plan

### Phase 5: multiscale and extended emission

**Status: open.** Multiscale science, combined products, bounded execution,
the original final qualification, compact regression, and the incremental
performance budget are complete. Phase 5 is blocked by the absence of a passing
cumulative regression ledger and fresh held-out qualification for the latest
source-association repair. Detailed campaign and incident chronology belongs in
`LOG.md`; machine identities and authorization boundaries remain in
`config/contracts/`.

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
| Readiness machinery | The fail-closed packet generator and finalizer exist and require packet-bound radio-astronomy and engineering acceptance. They do not authorize execution, cutover, or release. |

The narrow Continuum watchpoints from the passing recovery evidence remain
overall mask recall 0.90103 against 0.90 and mask-precision regression UCL
0.04940 against the pinned-master 0.05 margin. The terminal public failure and
the failed `1ac6deb2...` replay must remain visible historical evidence.

#### Current blocker and authorization state

There is no terminal cumulative ledger for the measurement-completeness
repair. Replacement review `119ce0f9...` and execution decision `5ddc524a...`
authorized one replay; it completed all 2,400 shards and then failed during
catalogue compilation, so that authority is consumed. The execution-failure
contract preserves the absent ledger, complete scratch, and adapter mismatch.
The existing shards may be reused only after complete identity verification
under a newly frozen evaluation-repair composition. Candidate execution,
replay, viewed SDC1/Hydra execution, qualification, tuning, rescoring,
cutover, and release remain unauthorized.

The frozen readiness contract has now been prospectively rebound to repair
candidate `6184a32...`, configuration `78dbb230...`, and the replacement
cumulative and future held-out evidence paths. Those identities were fixed
before either result was opened; a passing result cannot be fitted into the
readiness contract retrospectively.

Non-executable pre-review `7687839f...` now binds repair commit
`6184a32...`, source tree `517d56e1...`, unchanged configuration
`78dbb230...`, the consumed replay boundary, new write-once namespaces,
prospective readiness fields, and the required fixture/no-write checks. Named
approval opened only wrapper/readiness implementation, fixture and complete
no-write verification, and non-executable identity freezing. Implementation
decision `b9d48850...` binds the minimal replacement layer over consumed
wrapper `bfc1d6d0...`. The clean implementation commit `9cc00fb...` passed
complete no-write verification of all 2,400 inputs and 9,600 retained
reference runs without creating output or scratch state. Gate 1 is complete.
Gemma Danks granted separate named approval bound to review `119ce0f9...`;
execution decision `5ddc524a...` was consumed by the process that produced
every candidate shard but no ledger. The evaluation-only repair must now be
committed, verified against the preserved product-set identity, and frozen for
separate exact compilation/evaluation approval. It must never submit candidate
work.

#### Remaining closure sequence

Execute these steps in order. A failure at either scientific gate stops the
sequence and requires a new prospective review; it does not authorize tuning
from partial or viewed evidence.

1. [x] **Freeze the repaired cumulative-replay composition.**
   - [x] Obtain named approval of pre-review `7687839f...`; this approval may
     authorize only replacement wrapper/readiness implementation, fixture and
     complete no-write validation, and non-executable identity freezing.
   - [x] Bind the exact candidate commit and source tree derived from
     `6184a32...`, the complete configuration, measurement-repair program,
     source-association contracts, replay wrapper, reconstructed reference
     terminal `48209eae...`, and closed baseline `a45303df...`.
   - [x] Use new write-once ledger and scratch identities, run fixture and
     complete no-write verification, and publish a non-executable identity
     review with every later authorization false.
   - [x] Prospectively update the readiness contract to require the same final
     candidate, configuration, ledger, and future held-out decision identities.

2. [ ] **Obtain named approval and run exactly one cumulative replay.**
   - [x] Approval binds replacement identity review `119ce0f9...` and the
     exact two-worker 800-compact/1,600-Continuum composition.
   - [x] Candidate execution completed all 2,400 products under that authority;
     compilation failed before atomic publication on the stale single-support
     adapter, and the replay authority is consumed.
   - [ ] Freeze and approve the evaluation-only completion identity, then
     compile and evaluate only the exact preserved product set. Candidate
     submission and another replay remain forbidden.
   - Require `cumulative_science_regression_ready=true`, every required
     endpoint passing, and empty compact and Continuum like-semantics regression
     lists. Interpret compact and Continuum science before power or runtime.
   - If execution or evaluation fails, preserve the write-once state and stop;
     do not overwrite, resume under a consumed decision, tune, rescore, or
     silently substitute evidence.

3. [ ] **Freshly qualify the exact passing candidate.**
   - Freeze a seed-disjoint, previously unopened held-out population and the
     exact compiler/evaluator/runtime identities, then obtain a separate
     one-look approval.
   - Require all binding absolute gates and all applicable released/master
     PyBDSF and Aegean comparisons, including the two Continuum watchpoints.
     Keep compact regression green and do not pool with or rescore closed
     campaigns.
   - Viewed SDC1/Hydra evidence remains diagnostic historical context, not
     fresh qualification truth.

4. [ ] **Complete the restricted Rapthor profile decision.**
   - Restore the controlled real inputs, freeze their canonical pre-filter
     component population, and run compact and continuum Hebog masks through
     the exact pinned LSMTool filtering operation against both PyBDSF
     references.
   - Compare true/apparent, bright, extended, edge, masked, sparse, and crowded
     safety strata. Select `compact` only when overall agreement is at least
     99.5% and every safety stratum passes; otherwise select `continuum`.
   - Record a write-once profile decision. This selects workflow behaviour only
     and does not authorize the Phase 7 cutover.

5. [ ] **Confirm final engineering evidence.**
   - Re-run source-association Serial/existing-Dask invariance and the affected
     incremental performance anchors for the exact final candidate, or record a
     reviewed proof that the frozen performance path and identity are
     unchanged. Preserve the 6.0-second budget and crossover policy.
   - Rebuild the complete readiness review packet against the final cumulative
     ledger, held-out qualification, Rapthor profile, bounded-execution
     contract, performance summary, closed final qualification, terminal public
     failure, and its independent scientific review.

6. [ ] **Obtain independent acceptance and publish readiness.**
   - Obtain separate packet-bound radio-astronomy and engineering acceptances.
   - Run the write-once readiness finalizer, update `LOG.md`, user
     documentation, and the Phase 6 handoff, then create a reviewed local
     commit without pushing.
   - The readiness record closes Phase 5 only. Cutover, release, optimization,
     and Phase 6/7 execution remain separately governed.

Phase 5 is complete when steps 1--6 are checked and the final readiness record
is terminal. No additional public campaign is intrinsically required for
closure unless the prospective scientific review or fresh qualification
exposes a new blocker.

### Phase 6: distributed execution

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

### Phase 7: Rapthor integration and performance

- [ ] Add readable acceptance scenarios for empty/corrupt inputs, restart,
      retry, backend selection, fallback, dual-run reporting, and decisions.
- [ ] Add the Hebog backend; split true-sky, flat-noise, and final filtering
      into restartable tasks and run concurrently only when admitted resources
      permit.
- [ ] Preserve feature-flagged PyBDSF fallback and dual-run comparison; remove
      the PyBDSF subprocess escape only from the Hebog path.
- [ ] Run matched complete `filter_skymodel` benchmarks against released and
      pinned-master PyBDSF across the frozen matrix and relevant core counts.
- [ ] Require all science gates, runtime confidence bounds, retry/resume, and
      memory gates to pass before default cutover.

### Phase 8: hardening and release

- [ ] Enforce portable test lanes in CI and run qualification, benchmark, and
      scalability lanes on controlled runners.
- [ ] Publish current API, configuration, schemas, provenance, reproduction,
      limitations, and a non-Rapthor serial workflow.
- [ ] Add structured timings and scientific summaries; complete dependency,
      security, licensing, packaging, and reproducibility review.
- [ ] If native code exists, qualify every supported wheel/source-build and
      fallback path.
- [ ] Continue explicit experimental `0.x` releases; prepare `1.0.0` only after
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
| Compiler or comparator defect changes science | Test matching/measurement independently; checksum-bind programs; preserve closed compilers. |
| Support topology is confused with source photometry | Keep catalogue/source, component, and support records distinct; measure flux on original pixels. |
| Mask background hides errors | Evaluate precision/recall/IoU on valid pixels plus object splits/merges. |
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
