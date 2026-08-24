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

The initial matched-filter and wavelet candidates both failed the complete
scientific matrix (`select-neither`). The corrective design retained the
community-standard residual B3 à trous representation, original-image
photometry, morphology-independent support, and separate compact versus
irregular-source astrometry semantics. Detailed experiment chronology and all
closed campaign identities remain in `LOG.md`.

The recovery campaign is now the terminal Step 2C-PC promotion evidence:

| Evidence | Result |
| --- | --- |
| Candidate | `c184acf7f...`; source `b4176ce3...`; configuration `0e5dde51...` |
| Sealed campaign | 2,488 inputs; all 12,440 runs successful; SHA `4d881a41...` |
| Analysis | write-once SHA `198fe6ff...` |
| Decision | terminal `pass`; SHA `cd3eacfb...` |
| Continuum | 143/143 absolute gates and 226/226 powered comparisons pass: 113 against each PyBDSF reference |
| Compact | 77/77 binding absolute gates, 450/450 PyBDSF comparisons, and 143/143 applicable Aegean comparisons pass |

The closest Continuum gates are overall mask recall 0.90103 against 0.90 and
overall mask-precision regression UCL 0.04940 against the pinned-master 0.05
margin; keep both as explicit regression watchpoints. Five compact
truth-absolute diagnostics remain outside stronger report-only envelopes, but
they are not binding gates and all reference comparisons pass. This campaign
contains no runtime-performance gate and supports no speed claim. Step 3 is
open; Phase 5 qualification, incremental performance, independent acceptance,
and the later Rapthor cutover remain outstanding.

## 7. Delivery plan

### Phase 5: multiscale and extended emission

#### 2C-PC. Recover from the failed post-correction campaign

- [x] Restore historical compiler SHA `7a055891...` and verify the complete
      inherited identity chain. Preserve the sealed campaign, analysis, and
      decision unchanged.
- [x] Obtain named approval for the 2026-08-20 recovery pre-review. It
      attributes the failures to an unbound candidate configuration, omitted
      Continuum product settings, and Rapthor-source compact compilation; the
      valid-region rule is a no-effect contract gap on this population.
- [x] Implement the already reviewed candidate in one prospective product
      adapter: refined residual-B3 support, 1.5-beam nearest-owned photometry,
      regularized position weights, and the exact approved configuration SHA.
- [x] Implement a new prospective compiler composition with fitted-component
      compact semantics, symmetric valid-domain masks, and fail-closed
      candidate-configuration verification. Add test-first normal, duplicate,
      merged-support, invalid-pixel, all-reference-parity, and identity cases.
      Keep source photometry distinct from support/island topology.
- [x] Make no new algorithm correction unless the correctly composed
      candidate fails permitted development evidence. Do not weaken gates or
      change governed truth.
- [x] Bind a restartable viewed-reference reconstruction after approved raw
      cleanup removed the old products: retain the exact 1,600/800 viewed
      population and protocol, use equivalent rebuilt PyBDSF/Aegean runtimes,
      execute no historical Hebog leg, and label the result development-only.
- [x] Produce a cumulative Phase 4/5 regression ledger and require no
      like-semantics pass-to-fail regression. The complete viewed replay has
      zero compact or Continuum regressions: compact passes, all 143 Continuum
      absolute gates pass, and the nine underpowered paired endpoints feed the
      completed prospective power review. A fresh campaign remains
      unauthorized.
- [x] Recompute exact endpoint power. The write-once recovery review
      `bbfab3a0...` binds all 226 comparisons and selects 1,688 Continuum
      realizations (422 per geometry) plus 800 compact realizations; its
      conservative combined familywise power lower bound is 0.90508 against
      the required 0.90.
- [x] Obtain named scientific approval of candidate `c184acf...` / source
      `b4176ce3...` / configuration `0e5dde51...`, then freeze the powered
      seed-disjoint population, prospective recovery compiler/evaluator, and
      four approved runtimes without execution. Initial review `5bdf4f46...`
      was superseded before preflight because its verifier could not represent
      the approved state; corrected pending review `8aaaca74...` adds only the
      fail-closed authorization transition and keeps all science identities.
- [x] Obtain a separate named one-look approval bound to identity review
      `8aaaca74...` and its four runtimes. Approval of superseded review
      `5bdf4f46...` did not carry across the verifier change. The corrected
      decision now authorizes exactly one comparison while leaving the look
      unopened. Run the complete no-write preflight from the immutable
      authorization commit; execute and evaluate only if every identity holds.
- [x] Restore at least 126 GiB host headroom, rerun the omitted no-write storage
      audit, and resume the same `fa3134b...` / `7a44ba52...` staging namespace.
      The identity preflight passed as request `4c53dc39...`, but launch was
      stopped after 3 inputs and 0 results when only 28 GiB was observed. Do not
      create a second campaign request or change any frozen identity. Approved
      cleanup permanently removed the development-only viewed reconstruction's
      42-GiB `inputs/` and 55-GiB `results/` while retaining its four provenance
      records. Trimming the Podman guest then reduced its host allocation from
      about 98 GiB to 31 GiB and restored 134 GiB host headroom. All four exact
      images reverified and the same request resumed in managed session 83019;
      hourly operational monitoring is active without partial-science access.
- [x] Correct the recovery runner composition without creating another campaign.
      The resumed process verified all 2,488 inputs but failed on the first
      Hebog invocation before candidate execution because the recovery script
      imports `hebog.validation.post_correction_recovery` from the approved
      source tree while the container command deliberately omitted
      `PYTHONPATH=/repository/src`. One reference result completed, no Hebog
      result or terminal manifest exists, and no partial science was inspected.
      A recovery-only Podman delegate now injects that path solely for the exact
      frozen Hebog image and runner; command tests prove materialization,
      references, and other images are unchanged, and a network-isolated import
      smoke test resolves the approved module from the immutable checkout.
- [x] Bind the delegate to request `4c53dc39...`, infrastructure log
      `91e3db30...`, implementation commit `c88e7c25...`, delegate SHA
      `36a420a1...`, the exact images, and the preserved staging namespace.
      Pending resume review `a8d30ee9...` records zero completed Hebog results,
      one unopened reference result, unchanged science, and sufficient adjusted
      storage headroom; it cannot authorize itself.
- [x] Obtain exact named approval of pending resume review `a8d30ee9...`.
      Authorization decision `de2aec16...` permits only request `4c53dc39...`
      to resume through delegate commit `c88e7c25...`; it forbids a second
      campaign and any science change.
- [x] Complete the existing-campaign resume, terminal verification, and frozen
      compilation. Campaign `4d881a41...` sealed all 2,488 inputs and 12,440
      runs; write-once analysis `198fe6ff...` compiled successfully.
- [x] Repair the terminal evaluator composition without changing science. The
      frozen evaluator stopped before scoring or output because it passed the
      recovery-seam identity where the inherited evaluator requires the base
      accelerator recorded by the analysis. A separate fail-closed adapter
      at commit `147e193...` preserves both identities and forbids campaign or
      analysis reruns. Pending review `0b6a98d9...` binds the unchanged evidence
      and cannot authorize itself.
- [x] Obtain exact named approval of pending review `0b6a98d9...`.
      Authorization decision `5103aedc...` permits the amendment to evaluate
      existing analysis `198fe6ff...` exactly once; it forbids campaign
      re-execution, analysis recompilation, and science or gate changes.
- [x] Evaluate analysis `198fe6ff...` once through the approved amendment.
      Terminal decision `cd3eacfb...` is `pass`: all 143 Continuum absolute
      gates, all 226 Continuum PyBDSF comparisons, all 77 compact binding
      absolute gates, all 450 compact PyBDSF comparisons, and all 143
      applicable compact Aegean comparisons pass. No campaign or analysis was
      rerun and no gate or endpoint changed.
- [x] Open Step 3 because every applicable absolute, released/master PyBDSF,
      and Aegean gate passed. Retain the two narrow Continuum margins as
      regression watchpoints; this decision does not close Phase 5 or make a
      runtime claim.

#### 2D. Determine the Rapthor profile

- [ ] Freeze the Rapthor/LSMTool revision, real input checksums, both PyBDSF
      configurations, and predeclared decision strata.
- [ ] Feed Hebog compact and qualified continuum masks through the same
      filtering logic; compare retained/rejected true, apparent, and bright
      sky-model components, including extended, edge, masked, sparse, and
      crowded cases.
- [ ] Select `compact` only if at least 99.5% agreement and every safety
      stratum pass; otherwise select `continuum`.
- [ ] Treat this as a workflow-profile decision only. It cannot narrow the
      general continuum science or authorize the Phase 7 backend cutover.

#### 3. Complete multiscale science

- [x] Detect significant residual emission at each configured scale from
      shared à trous smoothings and calibrated local noise; reconstruct
      accepted adjacent-scale signal without an image-sized response bank.
      The promoted three-scale float64 kernel now exposes immutable per-scale
      significance provenance, rejects non-finite thresholds and non-adjacent
      scale records, and retains only bounded tile-local working planes.
- [x] Freeze scale-specific connectivity, persistence, seed/grow, support,
      minimum-area, edge, and invalid-pixel rules with analytic tests. The
      production policy uses adjacent scales, eight-neighbour 3-sigma growth
      on original valid residual pixels, normalized support of at least 0.5,
      and a one-beam floor with a direct 5-sigma seed exception.
- [x] Complete compact-deferred islands through a bounded partitioned path;
      no task may own an arbitrarily large island. The published accepted mask
      is relabelled in independently bounded zero-halo cores, reconciled from
      compact boundary summaries, and bound to canonical array-free shards;
      exact membership is reconstructed from only one shard tile at a time.
- [x] Measure extended flux, position, shape, background, and available
      uncertainty from original pixels with explicit unavailable/truncation
      semantics. Bounded tasks apply the promoted 1.5-major-beam nearest-owned
      aperture, preserve compact supports as barriers, reduce only scalar
      statistics, use regularized direct-plus-B3 positions with the reviewed
      compact safeguard when supplied, and type flux uncertainty, shape
      availability, and edge/invalid truncation without inventing errors.
- [x] Preserve compact Phase 4 products exactly when multiscale evidence does
      not alter their association. The no-op boundary accepts only
      `extended-only` evidence with no compact source identities, returns the
      same completed compact object, and reproduces identical Rapthor FITS
      bytes; compact-touching or ambiguous evidence fails closed for Step 4.

#### 4. Reconcile scales and construct products

- [x] Define deterministic compact/extended overlap, ownership, split/merge,
      and duplicate-suppression rules before implementation. Named approval on
      2026-08-24 froze contract schema 2: adjacent-scale exact-support graph
      reconciliation, shared-island/separate-source compact context,
      compact-first pixel ownership, one extended row per association, and
      fail-closed ambiguity. The bounded serial association kernel now derives
      stable associations independently of plane and local-label order;
      combined identity and construction remain below.
- [x] Preserve physically distinct compact components embedded in or projected
      on extended emission while merging fragments of one extended object. A
      bounded many-to-many context graph retains every accepted Phase 4 source
      ID and every reconciled extended association ID, records containment and
      overlap per edge, uses only exact support or the frozen half-beam context
      dilation, and fails closed on conflicting extended ownership.
- [x] Derive stable island, source, and compatibility-component identities from
      global reconciled properties, independent of tiles and task order.
      Compact-only islands and all Phase 4 source/Gaussian IDs remain exact;
      mixed and extended islands hash canonical compact-island and association
      membership, while each association has one context-independent extended
      source ID. Irregular extended sources deliberately have zero Gaussian
      components rather than publishing an unfitted compatibility Gaussian;
      machine contract schema 3 freezes these identity rules.
- [x] Merge bounded shards hierarchically and publish only when every accepted
      or deferred island has a terminal disposition. Canonical fan-in-two
      reduction records depth and maximum input-shard size under an explicit
      final-state record cap. State schema 2 carries disjoint accepted and
      deferred identity sets; missing dispositions, omissions, failed states,
      duplicate ownership, and unknown terminal evidence all block completion.
- [ ] Materialise the combined catalogue, mask, RMS, provenance, diagnostics,
      and Rapthor compatibility view without changing compact-only output.

#### 5. Prove bounded deterministic execution

- [ ] Derive and review every stage halo; reject configurations that cannot
      meet the memory contract.
- [ ] Prove one-tile/many-tile equality across edges, corners, rectangular
      tiles, invalid regions, largest scales, and multiple partition origins.
- [ ] Prove partition, batch, worker-count, completion-order, retry, and
      executor invariance for science and product identities.
- [ ] Record bounded retained bytes, workspaces, summaries, shards, and graph
      size; exercise SerialExecutor and the existing executor path.

#### 6. Qualify Phase 5

- [ ] Turn every accepted development defect into a deterministic regression
      fixture.
- [ ] Repeat the full final comparison with untouched qualification data,
      injected truth, both PyBDSF references, and Aegean over its applicable
      scope, stratified by morphology, scale, SNR, edge, blend, and background.
- [ ] Add public/challenge comparisons across at least two telescope families;
      use Selavy, ProFound, or CAESAR only where scientifically applicable.
- [ ] Re-run the complete Phase 4 compact regression and stronger-Hebog
      envelopes.
- [ ] Open the frozen final Phase 5 qualification exactly once through the
      reviewed evaluator; retain a terminal failure without rescoring.
- [ ] Benchmark 256, 512, 1,024, and 3,000-square incremental paths and both
      sides of any new crossover; meet the 6.0-second multiscale budget with no
      unapproved adjacent-tier regression.
- [ ] Update schemas, method/configuration documentation, Marimo demonstration,
      readiness evidence, and auditable per-object scale/support provenance.
- [ ] Obtain named independent radio-astronomy and engineering acceptance.

Phase 5 closes only when the final implementation passes every absolute and
applicable PyBDSF/Aegean gate, the Rapthor profile is selected, compact
regression remains green, bounded tile/executor invariance is proven, the
incremental performance budget passes, and independent reviewers accept the
evidence and Phase 6 handoff.

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
