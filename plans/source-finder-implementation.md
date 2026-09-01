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
- Phase 6 owns Rapthor integration, complete dual-PyBDSF performance, and the
  earliest useful experimental release once every minimum gate passes.
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
   metric and stratum.
   A candidate may improve one measure without compensating for a material
   regression in another. Point estimates may vary, but the predeclared paired
   confidence rule and practical margin must rule out a scientifically material
   loss; no reviewed trade-off can waive this Phase 5 quality-retention gate.
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
and the separately frozen Rapthor profile decision.

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
failures and 33 regressions. Its bounded census records zero displaced-child
candidates, so the intended mechanism was dormant. The current blocker is the
pre-persistence all-features-seeded eligibility guard, governed by a new
non-executable red-fixture pre-review rather than another replay.

Section 7 contains the single authoritative Phase 5 closure sequence; detailed
chronology and immutable identities remain in `LOG.md` and
`config/contracts/`.

## 7. Delivery plan

### Phase 5: multiscale and extended emission

**Status: open.** Multiscale science, combined products, bounded execution,
the original final qualification, compact regression, and the incremental
performance budget are complete. Terminal-cycle eligibility and the fail-fast
scientific feedback lane are implemented, and the prospective
parity-and-quality-retention records are frozen but inactive pending exact
human scientific review. Phase 5 next requires the prospective evaluator,
endpoint-level power audit, diagnostic smoke lane, one passing cumulative
regression ledger, and fresh held-out qualification for the eventual corrected
candidate. Detailed campaign and incident chronology belongs in `LOG.md`;
machine identities and authorization boundaries remain in
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
| Source-reconstruction correction | Candidate `42c75f4...` added a deterministic common-parent hierarchy, one source-level measurement, connected-support admission, and source-union topology evaluation. Terminal ledger `84fbb3a1...` preserves compact science but fails the cumulative gate with 44 Continuum failures and 37 regressions; source membership and fragmentation were effectively unchanged. |
| Readiness machinery | The fail-closed packet generator and finalizer exist and require packet-bound radio-astronomy and engineering acceptance. They do not authorize execution, cutover, or release. |

The narrow Continuum watchpoints from the passing recovery evidence remain
overall mask recall 0.90103 against 0.90 and mask-precision regression UCL
0.04940 against the pinned-master 0.05 margin. The terminal public failure and
the failed `1ac6deb2...` replay must remain visible historical evidence.

#### Current blocker and authorization state

The measurement-completeness repair now has terminal cumulative ledger
`6b2aa4de...`. Replacement review `119ce0f9...` and decision `5ddc524a...`
produced all 2,400 candidate shards before the stale compiler stopped.
Evaluation-only review `6a0e79b4...` and decision `46ddfefa...` then authorized
one completion from verified product set `dbc317fa...`; immutable revision
`2174b0c...` published the ledger without candidate execution. Both
authorities are consumed.

The ledger is terminally `fail`. Compact passes with no like-semantics
regression. Continuum has 89 passes, 44 failures, 10 underpowered endpoints,
and 37 like-semantics regressions; `cumulative_science_regression_ready`,
all-required-endpoints, and fresh-campaign freeze are false. Source-union
matching changed 49 point estimates but no endpoint status relative to
`1ac6deb2...`; reliability and duplicate fraction worsened slightly, while
split, flux, and mask metrics were unchanged. Candidate execution, replay,
viewed SDC1/Hydra execution, qualification, tuning, rescoring, cutover, and
release remain unauthorized.

Source-reconstruction pre-review `528f18a6...` proposed a common-parent
multiscale hierarchy, one source-level measurement, connected reconstructed
support, and source-union topology evaluation. Candidate `42c75f4...` passed
its analytic and Serial/existing-Dask contracts without changing thresholds,
gates, component ownership, or closed evidence. Review `b4eff062...` and
decision `0d87caf7...` bound the exact replay. After all 2,400 products were
created, the historical PyBDSF/successor-Hebog record-dispatch defect stopped
terminal compilation. Review `cc531cee...`, wrapper `3ff495e3...`, product set
`0d8c2d0b...`, and amended decision `659725aa...` authorized only the
evaluation repair and exact existing-product completion.

That completion is now terminal. Ledger `84fbb3a1...` is provenance-complete
and `fail`: compact passes with no regression, while Continuum records 89
passes, 44 failures, 10 underpowered endpoints, and 37 like-semantics
regressions. Relative to `6b2aa4de...`, 48 point estimates changed only at
negligible numerical scale, no endpoint status changed, and overall duplicate
and split fractions remain 25.29%. The intended hierarchy therefore did not
alter governed catalogue-source membership on this population. Root-cause
pre-review `c1a92bd2...` was approved for fixture-only repair. The implemented
prerequisite now preserves immutable direct-seed labels alongside recovered
measurement ownership, accepts multiple fine-feature attachments only through
one nearest common lineage, rejects terminal-only coarse bridges, and emits
compact activation diagnostics. Hand-built hierarchy, malformed ownership,
overmerge, telemetry, product-composition, and existing-Dask contracts pass.

The parent-construction replay is also terminally failed. Ledger `2ece9928...`
passed compact but retained 44 Continuum failures and 37 like-semantics
regressions, with all 143 Continuum values and states unchanged from source
reconstruction. Its 1,600 sidecars contained 18,065 components and 18,065
singleton catalogue sources. All 1,923 parent candidates first appeared at
scale 3, so the identical-group recurrence rule could never accept one at the
next nonexistent scale.

That prospective correction was frozen and executed as candidate `85d5807...`.
Terminal ledger `e2ee663f...` proves material but insufficient improvement:
compact passes, while Continuum moves from 89 to 96 passing endpoints, from 44
to 35 failures, and from 37 to 30 like-semantics regressions. Overall
reliability rises from 62.38% to 85.21%; duplicate and split fractions fall
from 25.29% to 12.83%; flux p95 falls from 79.26% to 26.94%; and position p95
falls from 4.18 to 0.98 beam. The cumulative gate nevertheless remains closed.
Shell splitting falls from 100% to 34.56%, showing that accepted terminal
parents work but parent activation is incomplete.

Non-executable pre-review
`phase-5-public-finder-terminal-feature-persistence-pre-review` binds that
terminal evidence and separates the confirmed incomplete activation from the
still-unproven exact cause. Its exact SHA-256 is `e416f7d8...`. It proposes
fixture-first testing of the narrow exact-overlap persistence seam: a terminal
feature may use a mutually unique
preceding-scale displaced child only when fixed B3 envelopes overlap and both
exact supports belong to the same retained significant-support component.
This evidence may corroborate persistence only; it cannot create cycles,
pairs, paths, or source membership. Gemma Danks approved exact review
`e416f7d8...`. The red one-pixel boundary-drift fixture confirmed the
exact-overlap cause, and the bounded implementation now passes disconnected
support, ambiguous child, unseeded feature, pair, path, invalid-gap,
partial-group, label/order/retry, Serial, and existing-Dask controls. Replay,
viewed-data execution, qualification, tuning, rescoring, cutover, and release
remain unauthorized. Candidate `3d080f7...`, source tree `a25d22d8...`,
configuration `2d6ab6bb...`, wrapper `0c66f221...`, evaluator `1cb62c00...`,
readiness overlay `da135898...`, retained reference `48209eae...`, and closed
baseline `a45303df...` are now frozen by non-executable review `45aef047...`.
The complete no-write verification passed 2,400 inputs and 9,600 reference
runs without creating scratch or output. Exact decision `ad72924a...` then
authorized one replay and evaluation in immutable checkout `ed84c216...`.
All 2,400 products completed and terminal ledger `a9b4d57e...` was published
without process repair or duplicate execution.

The terminal-feature persistence candidate fails. Compact remains green, but
Continuum records 93 passes, 39 failures, 11 underpowered endpoints, and 33
like-semantics regressions. No endpoint state improved relative to the
terminal-parent predecessor; three passes became failures and one
underpowered endpoint became a failure. Overall reliability fell from 85.21%
to 77.80%, split and duplicate fractions rose from 12.83% to 15.21%, flux p95
rose from 26.94% to 74.62%, and position p95 rose from 0.98 to 3.59 beams.

The new census records 1,211 terminal-cycle candidates and parents, 4,414
exactly persistent features, and zero displaced candidates or acceptances.
The intended correction was therefore dormant. Code inspection identifies a
new pre-persistence eligibility guard that rejects an entire cycle when any
geometric feature lacks a direct-component attachment. The predecessor kept
such a persistent feature as geometry while restricting membership to seeded
direct components. Because the census begins after this guard and transient
products are absent, per-realization attribution still requires a red fixture.
Non-executable review
`phase-5-public-finder-terminal-cycle-eligibility-pre-review`, SHA-256
`e70e602f...`, freezes that fixture-only boundary; it authorizes nothing by
itself.

Gemma Danks approved exact review `e70e602f...` for fixture-only
implementation and non-executable identity preparation. The required red
exact-persistence fixture reproduced the loss of a valid three-member parent
when a fourth persistent cycle feature had no direct owner. The bounded repair
now evaluates persistence before deriving membership: persistent unseeded
features may corroborate cycle geometry, but membership still contains only at
least three immutable direct components. Non-persistent unseeded geometry,
fewer than three members, pairs, paths, bridges, disconnected support,
ambiguous children, crowded seeds, and partial-group conflicts remain
fail-closed. New array-free diagnostics count pre-eligibility cycles and
unseeded accepted/rejected candidates, and the positive fixture records both
the formerly rejected seam and repaired activation. Serial and existing-Dask
results are invariant to component labels, plane/record/task order, and retry.
The historical evaluator remains byte-unchanged behind a prospective
eligibility overlay. Replacement replay identities remain deliberately
unfrozen until the exact end-to-end, parity/retention, evaluator, power, and
smoke prerequisites below pass.

The full replay is not an appropriate first detector for this class of defect.
The next correction must therefore establish a reusable fail-fast ladder before
another 800-compact/1,600-Continuum replay identity can be frozen:

| Lane | Frozen population | Binding purpose | Promotion evidence |
| --- | --- | --- | --- |
| End-to-end contract | Tiny analytic products covering compact and Continuum | Exercise the exact producer, wrapper, compiler, evaluator, schema, provenance, and write-once seams | No |
| Mechanism activation | 20--40 targeted analytic or viewed-development cases | Prove the proposed mechanism activates, rejects unsafe controls, and changes only the intended ownership/topology path | No |
| Scientific smoke replay | 64--128 stratified viewed-development cases | Compare the candidate with its immediate predecessor across shells, scale-4 emission, corners, boundaries, invalid pixels, artifacts, mixed morphology, and compact overmerge sentinels | No |
| Full cumulative replay | 800 compact and 1,600 Continuum cases | Provide the powered cumulative regression decision after all earlier lanes pass | Yes |

All lanes must call the same production composition; a mock compiler or a
different evaluator cannot qualify the full command. The first three lanes
must remain non-promotional and may use only analytic or already-viewed
development evidence, never the unopened qualification population. Their
fail-closed requirements are:

- reproduce the all-features-seeded regression in a red fixture, then retain
  a persistent unseeded feature only as cycle geometry while deriving source
  membership solely from seeded direct components;
- observe non-zero pre-eligibility and repaired activation counts on targeted
  positive cases; zero activation of the advertised mechanism is a terminal
  smoke-lane failure;
- require the expected direction of change relative to terminal-parent
  candidate `85d5807...`, byte-stable unaffected products where applicable,
  compact invariance, and all negative overmerge controls;
- freeze the smoke manifest by deterministic stratified selection from
  already-viewed development evidence plus named analytic sentinels. Include
  the known regressed cases and their negative neighbours deliberately, but do
  not choose or remove cases in response to the repaired candidate's output;
- execute every concrete wrapper, worker-reinstallation, record-dispatch,
  compiler, evaluator, provenance, and atomic-publication seam used by the full
  replay; and
- stop before identity freeze when any lane fails. Fix process-only defects
  test-first, but require renewed scientific review for a source, configuration,
  threshold, measurement, gate, or population change.

The latest terminal evidence cannot pass even a PyBDSF-parity-oriented
contract unchanged. Of the applicable paired Continuum comparisons, each
PyBDSF reference has 66 passes, 11 underpowered endpoints, and one failure:
overall mask precision. The next review must therefore treat mask precision as
an explicit all-check PyBDSF-parity blocker rather than assuming that
relaxation of unrelated absolute targets is sufficient. Its like-semantics
regressions are a separate Hebog quality-retention blocker.

The canonical historical readiness contract remains byte-bound to the failed
terminal-parent candidate and must not be mutated retroactively. Prospective
overlay `phase-5-terminal-feature-persistence-readiness`, SHA-256
`da135898...`, rebinds only the cumulative and future held-out evidence for
candidate `3d080f7...`; it retains every execution and promotion prohibition.
The canonical readiness record cannot advance unless the cumulative replay
and fresh held-out qualification both pass.

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
every candidate shard but no ledger. The evaluation-only repair has now been
committed, verified against the preserved product-set identity, and frozen in
review `6a0e79b4...` for separate exact compilation/evaluation approval. It
cannot submit candidate work. Gemma Danks granted that exact evaluation-only
approval on 2026-08-28; decision `46ddfefa...` records the authority without
opening candidate execution or another replay.

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

2. [x] **Run the only approved cumulative evaluation and stop on failure.**
   - [x] Approval binds replacement identity review `119ce0f9...` and the
     exact two-worker 800-compact/1,600-Continuum composition.
   - [x] Candidate execution completed all 2,400 products under that authority;
     compilation failed before atomic publication on the stale single-support
     adapter, and the replay authority is consumed.
   - [x] Freeze evaluation-only completion identity `6a0e79b4...` after exact
     verification of product set `dbc317fa...`; it leaves compilation and
     evaluation unauthorized.
   - [x] Obtain separate approval bound to that review and record exact
     evaluation-only decision `46ddfefa...`.
   - [x] Compile and evaluate only the exact preserved product set. Candidate
     submission and another replay remained forbidden.
   - [x] Interpret compact and Continuum science before power or runtime. The
     required gate failed: `cumulative_science_regression_ready=false`, not
     every endpoint passes, and 37 Continuum regressions remain.
   - If execution or evaluation fails, preserve the write-once state and stop;
     do not overwrite, resume under a consumed decision, tune, rescore, or
     silently substitute evidence.

3. [ ] **Correct source reconstruction prospectively.**
   - [x] Freeze a non-executable pre-review against terminal ledger
     `6b2aa4de...`, account for all 44 failures, separate direct causal facts
     from hypotheses, and forbid tuning or retrospective rescoring.
   - [x] Obtain named approval of exact pre-review `528f18a6...`. Approval may
     open only test-first source hierarchy, source measurement, connected-mask
     support, future source-topology evaluator, fixture/executor validation,
     and non-executable identity freezing.
   - [x] Implement the smallest correction that passes every positive and
     negative analytic fixture. Preserve component ownership, detection
     thresholds, gate values, and all closed evidence.
   - [x] Freeze a new candidate, source tree, configuration, compiler,
     evaluator, reconstructed-reference, and baseline composition; run its
     complete no-write verification. Review `b4eff062...` verifies all 2,400
     inputs and 9,600 reference runs with output and scratch absent.
   - [x] Obtain a separate exact one-replay approval. Decision `0d87caf7...`
     binds review `b4eff062...` and leaves all later actions unauthorized.
   - [x] Execute the candidate stage once. All 2,400 products completed under
     the exact authority; the first terminal compilation failed before atomic
     publication on a reference-record dispatch defect and was preserved as an
     operational incident.
   - [x] Freeze and consume the approved evaluation-only repair, compile and
     evaluate only the exact preserved product set, and require every compact
     and Continuum absolute and like-semantics gate. Candidate submission is
     forbidden; stop again on scientific failure.
   - [x] Record terminal ledger `84fbb3a1...`: compact passes, but Continuum
     remains at 89 pass, 44 fail, 10 underpowered, and 37 like-semantics
     regressions. No endpoint status changed relative to `6b2aa4de...`.
   - [x] Complete root-cause pre-review `c1a92bd2...`. It binds terminal ledger
     `84fbb3a1...`, reproduces the expanded-owner ambiguity on synthetic arrays,
     separates confirmed causes from hypotheses and safety risks, and defines
     fail-closed activation telemetry and end-to-end analytic fixtures.
   - [x] Obtain named approval of exact review `c1a92bd2...`. Approval opened
     only test-first separation of direct-seed and measurement-owner labels,
     unique-nearest-convergence attachment, fixture/executor validation,
     compact activation telemetry, and non-executable identity freezing.
   - [x] Implement direct/measurement-owner separation, nearest common-lineage
     reduction, terminal-bridge rejection, and compact activation telemetry.
     The focused hierarchy and composition suite passes.
   - [x] Run the real scale-filter fixture. It fails the positive activation
     criterion with four features at every retained scale and no common
     convergence, so candidate and replay identity freeze stopped.
   - [x] Freeze non-executable parent-construction pre-review `b5d89bdc...`,
     which accounts for the second defect and preserves every execution and
     tuning prohibition.
   - [x] Obtain named approval of exact review `b5d89bdc...`. The
     parent-construction implementation decision records fixture-only authority
     and keeps every execution and tuning flag false.
   - [x] Implement B3-footprint parent envelopes, cycle-supported sibling
     candidates, adjacent-scale persistence, exact-feature corroboration, and
     compact candidate/accepted/rejected telemetry without changing exact
     support or measurement.
   - [x] Pass real-path shell, three-lobe, closed-curved-filament, nearby-pair,
     terminal-only, invalid-gap, transitive-chain, Serial/existing-Dask,
     order, and retry fixtures.
   - [x] Compose the fail-closed replacement replay wrapper and prospectively
     rebind readiness to candidate `5f2b098...`, source tree `a7ef1887...`,
     and configuration `88634678...`. The wrapper consumes the exact failed
     predecessor, changes no compact or reference path, and cannot execute
     without a later exact review-bound decision.
   - [x] Freeze exact non-executable candidate and replay identities in review
     `e615da00...`. The complete no-write verifier passed all 2,400 inputs and
     9,600 reference runs with the future output and scratch absent and no
     replay started. Any replay still requires a separate exact approval.
   - [x] Obtain the separate exact one-replay approval. Decision `78c274cc...`
     binds review `e615da00...`, candidate `5f2b098...`, the two-worker
     800-compact/1,600-Continuum population, and every retained program,
     reference, baseline, output, and scratch identity. All later actions
     remain unauthorized.
   - [x] Preserve the terminal pre-candidate failure: session `5116` verified
     retained references, then wrapper `9bf44c09...` treated the
     measurement-repair overlay as source association and raised
     `_load_current_wrapper`. Scratch and output remained absent; no candidate
     or scientific product exists.
   - [x] Complete the approved wrapper-only repair: descend explicitly through
     source reconstruction, measurement repair, and source association in both
     parent and worker processes; make no-write verification resolve the same
     executable seams; freeze replacement wrapper/checkout identities; and
     retain the unchanged replay namespace. Repair review `89327ae5...` passed
     all 2,400 inputs, 9,600 reference runs, and executable seams; restart
     decision `0349fdc2...` consumes only the explicit fix-and-restart
     instruction.
   - [x] Execute the authorized candidate stage. All 2,400 shards completed;
     compilation then failed before atomic publication because direct-seed
     identities were inferred from recovered owner coordinates. No scientific
     result exists, and the complete product set remains immutable.
   - [x] Repair the evaluator contract test-first so associated rows consume an
     explicit digest-verified source-association record through a new run-aware
     overlay. Preserve all legacy catalogue semantics and both frozen compiler
     program identities.
   - [x] Reconstruct only the omitted association provenance for the 1,600
     Continuum shards under a separately approved write-once namespace. Require
     regenerated catalogue, labels, and mask to match the preserved products
     exactly; do not rerun compact science or mutate the existing scratch.
     Exact non-executable reconstruction review `691eaf8f...` is frozen and
     its named one-reconstruction approval was received on 2026-08-30. The
     terminal reconstruction sealed all 1,600 sidecars as product set
     `e1f16373...` under recovery identity `78d43370...`, with every regenerated
     candidate artifact matching the preserved product exactly.
   - [x] Freeze and approve one evaluation-only completion against the sealed
     sidecars, publish the atomic cumulative ledger, interpret compact and
     Continuum science before power, and require every absolute and
     like-semantics gate. The fail-closed completion program `bde8511a...`
     passed its complete no-write verification of all 2,400 candidate shards,
     1,600 sidecars, and 9,600 reference runs. Non-executable identity review
     `9c2be9a7...` freezes that composition; obtain one named
     compilation/evaluation approval before creating its execution decision.
     The approved completion then failed before compilation because its
     adapter installer inspected a closure-backed composed installer as if the
     recovery seam were a module global. The ledger remains absent and the
     approval is consumed. The explicitly authorized evaluation-only repair
     now wraps the active three-argument installer instead of inspecting its
     globals. Its complete no-write verifier executes the exact frozen compiler
     composition after verifying all products, sidecars, and references. Freeze
     the repaired identity and complete the preserved-product evaluation once.
     Repair review `894f38ff...` and one-use decision `b0e38b90...` bind that
     unchanged evidence; do not run another recovery or candidate campaign.
     Treat a scientific failure as terminal without tuning or rerunning. The
     repaired completion published terminal ledger `2ece9928...`: compact
     passed, but Continuum recorded 89 passes, 44 failures, 10 underpowered
     endpoints, and 37 like-semantics regressions. All 143 Continuum candidate
     values, statuses, and reasons are unchanged from the source-reconstruction
     ledger, so the parent-construction path still did not change governed
     catalogue-source membership. This candidate is terminally failed and may
     not be rerun or tuned.
   - [x] Document and implement the prospective persistent-support and
     constituent-persistent terminal-cycle correction. Require explicit
     significant support, whole-group reconciliation, compact activation and
     rejection telemetry, and fixture/executor invariance without changing
     thresholds, measurement, gates, or closed evidence.
   - [x] Freeze exact non-executable candidate and replay identities for this
     correction and run the complete no-write verifier. Candidate `85d5807...`,
     source tree `a082cbe4...`, configuration `88ac8bea...`, and wrapper
     `2c40315f...` passed all 2,400 inputs, 9,600 reference runs, the persisted
     association-sidecar seam, and the sidecar-aware evaluator seam under
     review `42c35481...` without creating scratch or output.
   - [x] Execute the separately approved exact two-worker cumulative replay
     under decision `f6d2bcc8...`. All 2,400 products completed and terminal
     ledger `e2ee663f...` was published. Compact passes. Continuum materially
     improves to 96 pass, 35 fail, 12 underpowered, and 30 regressions, but the
     cumulative gate remains false; this candidate is terminally failed and
     may not be rerun or rescored.
   - [x] Freeze a non-executable terminal-feature persistence pre-review that
     accounts for all 35 failures, records the seven removed regressions and
     nine improved states, separates confirmed incomplete activation from the
     unproven exact-overlap attribution, and retains every tuning and execution
     prohibition.
   - [x] Obtain named approval of terminal-feature persistence pre-review
     SHA-256 `e416f7d8...`; reproduce the exact-overlap gap in a red fixture;
     implement only the mutually unique B3/support-component persistence seam;
     retain bounded rejection diagnostics; and pass the positive, overmerge,
     conflict, ordering, retry, Serial, and existing-Dask controls.
   - [x] Freeze exact non-executable replacement candidate, configuration,
     wrapper, evaluator, readiness, reference, and baseline identities.
     Candidate `3d080f7...`, source tree `a25d22d8...`, configuration
     `2d6ab6bb...`, wrapper `0c66f221...`, and evaluator `1cb62c00...` passed
     the complete 2,400-input/9,600-reference no-write verification. Review
     `45aef047...` binds canonical future execution identity `75534703...`;
     no viewed-data execution is authorized.
   - [x] Execute and evaluate the separately approved terminal-feature
     persistence replay. Decision `ad72924a...` produced all 2,400 products
     and terminal ledger `a9b4d57e...` without process repair. Compact passes,
     but Continuum regresses to 93 pass, 39 fail, 11 underpowered, and 33
     like-semantics regressions. Displaced persistence records zero candidates
     and zero acceptances, so the candidate is terminally failed and may not
     be rerun, tuned, or rescored.
   - [x] Freeze a non-executable terminal-cycle eligibility pre-review that
     binds all 39 failures, the four worsened endpoint states, zero displaced
     activation, the over-restrictive all-features-seeded guard, and a red
     fixture requirement. Exact review `e70e602f...` authorizes no
     implementation or execution.
   - [x] Obtain named approval of the exact terminal-cycle eligibility
     pre-review; reproduce the regression in a red analytic fixture; implement
     only after confirmation; and pass mechanism, overmerge, and
     executor-invariance controls. Do not freeze replacement replay identities
     until every fail-fast prerequisite below passes.
   - [x] Add the exact end-to-end contract and mechanism-activation lanes before
     replacement identity freeze. Frozen analytic manifest
     `phase-5-terminal-cycle-fail-fast-cases` contains 25 cases across eight
     required families. Four label/order variants record both the historical
     pre-guard rejection and repaired persistent-unseeded acceptance; all
     non-persistent, bridge, pair, path, disconnected-support,
     ambiguous-child, and partial-group controls remain closed. The separate
     end-to-end lane executes the real source-reconstruction producer,
     canonical sidecar writer/parser, sidecar-aware compiler, source-union
     evaluator, compact producer, provenance binding, and atomic write-once
     publication. Its output is explicitly analytic and non-promotional.
   - [x] Freeze the prospective all-check PyBDSF-parity and Hebog-retention
     decision contract described in Section 3.1. Preserve every historical
     decision under its original gate; do not choose checks, margins, strata,
     or baselines from the candidate's viewed values. Retain the existing
     absolute numeric thresholds as reported longer-term improvement targets.
     Registry `095354bc...` freezes all 383 endpoints and 1,187 co-primary
     comparisons. Inactive review contract `f70f3213...` binds whole incumbent
     `85d5807...`, exact paired incumbent reexecution, realization-level BCa
     resampling, the intersection-union decision, immutable historical
     ledgers, and all execution prohibitions. It is not active until exact
     human scientific approval and the remaining activation requirements pass.
   - [x] Repair the prospective evaluator test-first so planning variance sizes
     the campaign and audits assumptions, while the observed realization-level
     confidence limit alone decides non-inferiority. Cover variance just above
     plan with an interval inside the margin, variance below plan with an
     interval crossing the margin, missing/non-finite evidence, and exact
     boundary equality; preserve every historical evaluator byte-for-byte.
     The new evaluator is isolated from all historical decision code. The
     endpoint-complete power audit reuses only pre-result compact familywise
     bounds and frozen Continuum planning variances; incumbent compact power is
     conditional on exact smoke identity and a full 800-product recheck.
   - [x] Freeze a 64--128-case viewed-development scientific smoke population
     and run the exact prospective producer/compiler/evaluator composition.
     Require the repaired candidate to restore the parent lost by the
     all-features-seeded guard, preserve the intended terminal-parent gains,
     retain compact invariance, introduce no material regression on any
     governed like-semantics check, and publish valid provenance atomically.
     The smoke result is diagnostic and cannot be pooled with full or
     qualification evidence. The deterministic 128-case population, current
     and incumbent materializers, complete no-write preflight, atomic smoke
     evaluator, and write-once power-audit program are implemented. The exact
     128-case smoke published `e3ac8e62...`: 326 comparisons pass, 35 are
     diagnostic-underpowered, and eight PyBDSF-parity comparisons fail while
     every incumbent-retention comparison passes. Terminal-cycle eligibility
     accepted 26 unseeded persistent candidates but changed no catalogue
     membership relative to the incumbent. The full replay is therefore
     blocked.
   - [ ] Correct the confirmed prospective boundary-support gap before another
     full replay. Review `e92ac289...` freezes the existing 3-by-3 dense-core,
     6-sigma sparse-boundary, and 0.5-beam nearby-significant-support policy;
     it permits no fitted threshold or margin. Reproduce the empty-opening
     high-S/N loss in a red fixture, apply refinement after seeded ownership,
     prove Serial/existing-Dask invariance and compact identity, then repeat
     the same 128-case smoke into a new write-once namespace. Require zero
     confirmed failures before the power audit and full replay identity freeze.
     The test-first implementation and exact configuration `ecf5ace2...` are
     complete: high-S/N thin support survives, low-S/N direct protrusions are
     removed, downstream direct ownership is clipped to refined measurement
     ownership, real-scale morphology and executor-invariance suites pass, and
     the full branch-aware suite remains at 94.52%. The replacement smoke is
     the remaining prerequisite.
   - [ ] Only after the fixture, activation, contract, prospective evaluator,
     power plan, and smoke lanes pass, freeze exact replacement identities and
     verify that the recorded conditional authority binds them without drift
     before one full cumulative replay. Interpret compatibility and validity
     before improvement objectives, power, or runtime; stop on a scientific
     failure.
   - After every terminal campaign, replay, or evaluation-only completion,
     append a human-readable immutable snapshot to the Phase 5 scientific
     campaign overview before closing its plan/log record.

4. [ ] **Freshly qualify the exact passing candidate.**
   - Blocked: the terminal-feature persistence cumulative prerequisite
     published a terminal failing ledger. No qualification population may be
     opened or frozen until the current eligibility regression is fixed, all
     fail-fast lanes pass, the all-check parity-and-retention contract is
     reviewed, and a full cumulative replay publishes a passing ledger.
   - Freeze a seed-disjoint, previously unopened held-out population and the
     exact compiler/evaluator/runtime identities, then obtain a separate
     one-look approval. Before opening it, demonstrate from the frozen planning
     variances and event frequencies that every binding endpoint and smallest
     binding stratum has enough independent realizations to reach a decision.
   - Require every applicable released/master PyBDSF and Aegean comparison and
     every like-semantics Hebog-retention comparison to pass the frozen paired
     rule. Report every absolute improvement endpoint and secondary stratum,
     including the two Continuum watchpoints, as longer-term targets. Keep
     compact regression green and do not pool with or rescore closed campaigns.
   - Viewed SDC1/Hydra evidence remains diagnostic historical context, not
     fresh qualification truth.

5. [ ] **Complete the restricted Rapthor profile decision.**
   - Begin this step only after the all-check PyBDSF-parity,
     Hebog-quality-retention, cumulative-replay, and fresh-qualification gates
     pass.
   - Audit the pinned Rapthor/LSMTool consumer to identify every field,
     filename, mask semantic, and filtering decision that is scientifically
     material. This audit narrows the integration contract only after general
     source-finder parity is established; it cannot excuse an earlier failed
     check.
   - Restore the controlled real inputs, freeze their canonical pre-filter
     component population, and run compact and continuum Hebog masks through
     the exact pinned LSMTool filtering operation against both PyBDSF
     references.
   - Compare true/apparent, bright, extended, edge, masked, sparse, and crowded
     safety strata. Select `compact` only when overall agreement is at least
     99.5% and every safety stratum passes; otherwise select `continuum`.
   - Record a write-once profile decision. This selects workflow behaviour only
     and does not authorize the Phase 6 integration, cutover, or release.

6. [ ] **Confirm final engineering evidence.**
   - Re-run source-association Serial/existing-Dask invariance and the affected
     incremental performance anchors for the exact final candidate, or record a
     reviewed proof that the frozen performance path and identity are
     unchanged. Preserve the 6.0-second budget and crossover policy.
   - Rebuild the complete readiness review packet against the final cumulative
     ledger, held-out qualification, Rapthor profile, bounded-execution
     contract, performance summary, closed final qualification, terminal public
     failure, and its independent scientific review.

7. [ ] **Obtain independent acceptance and publish readiness.**
   - Obtain separate packet-bound radio-astronomy and engineering acceptances.
   - Run the write-once readiness finalizer, update `LOG.md`, user
     documentation, and the Phase 6 handoff, then create a reviewed local
     commit without pushing.
   - The readiness record closes Phase 5 only. Cutover, release, optimization,
     and Phase 6/7 execution remain separately governed.

Phase 5 is complete when steps 1--7 are checked and the final readiness record
is terminal. No additional public campaign is intrinsically required for
closure unless the prospective scientific review or fresh qualification
exposes a new blocker.

### Phase 6: Rapthor integration, minimum performance, and early release

Phase 6 begins only after Phase 5 has established all-check scientific parity,
retained the frozen incumbent Hebog quality, and published the restricted
Rapthor profile decision. Its objective is the earliest safe, useful
improvement for Rapthor, not the final scientific or computational optimum.
Do not delay an experimental release for a longer-term absolute target or
maximum facility scale once all binding science, compatibility, operational,
and minimum complete-path performance gates pass.

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
- [ ] Publish an explicit experimental `0.x` release when the same minimum
      gates pass and the feature-flagged PyBDSF fallback remains available.
      Declare the validated image-size, workload, resource, and storage
      envelope and fail closed or use the fallback outside it.
      Further absolute scientific improvement and facility-scale optimization
      continue after this milestone.

### Phase 7: scale-out and continued optimization

Pursue the best practical scientific and computational performance after the
minimum useful Rapthor release. Every scalability or optimization change must
keep the frozen all-check PyBDSF-parity, best-Hebog-retention, and Rapthor
compatibility suites green; throughput, memory, and scale-out gains cannot
compensate for scientific or workflow regression.

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
- [ ] Continue explicit experimental `0.x` releases from Phase 6; prepare
      `1.0.0` only after operational soak and the full definition of done.

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
