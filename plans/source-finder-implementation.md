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
  completion, cross-scale ownership, bounded tiling semantics, incremental
  performance, and a terminal scientific-readiness handoff after confirmatory
  PyBDSF parity and Hebog-quality retention pass. Release Please owns the next
  release workflow; Phase 5 does not prepare a version, tag, changelog, or
  release artifact.
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

Phase 5 is open. The multiscale implementation, combined products, bounded
execution proof, compact regression, public interface, and incremental
performance budget are complete. Candidate `0b9e132...`, source tree
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
The remaining gates are the
prospective fast lane, a fresh cumulative replay/evaluation, seed-disjoint
held-out qualification, final engineering/public-interface confirmation,
cleanup and documentation, and packet-bound independent acceptance.

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

**Status: open; the version-8 public fast lane and cumulative no-write gate
passed, and the fresh cumulative candidate replay is ready once disk headroom
is sufficient.** Multiscale science,
combined products, bounded execution, compact regression, the public
scientific interface, and the incremental performance budget are complete.
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
comparisons after its complete 144/144/12 no-write preflight. Only a
fresh cumulative replay of that identity may reopen the closeout checklist;
the authentic incumbent and retained PyBDSF products remain reusable.
The current prospective source candidate is local commit
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
incumbent evidence.
Detailed campaign and incident chronology
belongs in `LOG.md` and the campaign overview; machine identities and
authorization boundaries remain in `config/contracts/`.

#### Phase 5 exit gates

| Gate | Binding pass condition | Current state |
| --- | --- | --- |
| Known scientific risks | Every confirmed adaptive-background, measurement, association, component partition, publication, and evaluator defect is corrected test-first without changing a closed result after it is viewed. | Pass at prospective development scale. Analytic reproduction proved the public path collapsed admissible peaks; the correction preserves direct and measurement support unions, uses canonical nearest-marker ownership with intensity-saddle merging only in the public topology, and reports bounded deferrals. The established Phase 3 compact path remains green. The public topology also retains admitted unseeded parents unchanged and projects publication recovery onto authoritative measurement owners without inventing science. Terminal fast-lane decision `a274888d...` has zero binding failures. Viewed Hydra data remains diagnostic-only and was not tuned or rescored. Cumulative evidence remains a separate gate. |
| Fail-fast development evidence | The replacement analytic/mechanism/smoke ladder passes product validity, trigger behaviour, paired retention in every four-seed trigger cell, multi-peak component retention, negative controls, and Serial/existing-Dask invariance. | Pass. Unequal-Gaussian, connected two- and three-peak, exact seed-boundary/no-seed retention, disconnected recovery, edge/corner, thin horizontal/vertical, non-square, empty, invalid-input, label-invariance, support-union, exact synthetic notebook-runner, public-composition, full coverage, and compact-equivalence gates pass. Version-8 terminal `a274888d...` passes 12/12 binding geometry groups, the trigger seam, and 12/12 Serial/existing-Dask comparisons; four non-binding improvement misses remain reported. |
| Exact public candidate | The installed `hebog.find_sources` path resolves the frozen algorithms and reference configuration and produces identical scientific products under Serial and caller-owned Dask execution. | Pass for the development gate. Candidate `95cfc76...`, source tree `8da21e86...`, and unchanged configuration `2c907949...` pass component-topology, publication-owner-domain, synthetic exact-runner, installed-wheel, compact-equivalence, source/composition identity, and the exact two-worker fast lane. Notebook identity `2920873a...` is non-executable. A new cumulative product identity is now required. |
| Cumulative parity and retention | Across all 800 compact and 1,600 Continuum cases, every binding comparison passes both PyBDSF references, the selected Hebog incumbent, applicable Aegean checks, and hard safety rules without pooling away a failed geometry or endpoint. | The old sealed set cannot qualify source-changing code. The evaluator raw-dispatch defect is repaired and regression-tested. The fresh 2,400-product stage is frozen and its complete no-write gate passes; execution and evaluation remain required. Reuse the authentic incumbent and all retained PyBDSF products rather than rerunning unchanged references. |
| Fresh scientific qualification | On unopened seed-disjoint data, every binding geometry and endpoint passes released and pinned-master PyBDSF, applicable Aegean, best-Hebog retention, compact-regression, and hard safety rules. No pooled result may hide a failed binding geometry. | Open. |
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

#### Authoritative Phase 5 closeout checklist

If the corrected candidate's cumulative replay and evaluation pass every binding check,
complete only these steps, in order:

1. [ ] **Seal and accept the cumulative decision.** Verify all 2,400 current
   products and their exact candidate, source-tree, configuration, program,
   reference, incumbent, and execution provenance. Compile the atomic decision
   by reusing the authentic incumbent and retained released/master PyBDSF
   products; do not rerun unchanged science. Require every Aegean-parity,
   dual-PyBDSF-parity, incumbent-retention, like-semantics, and binding-safety
   check to pass. Absolute improvement objectives remain reported but cannot
   replace these gates. A scientific failure stops closeout and opens a new
   prospective review; it is not permission to tune or rescore the result.
2. [ ] **Freeze the production candidate and run one fresh held-out
   qualification.** Before exposing held-out data, audit `src/hebog/` for dead
   branches, obsolete feature flags, duplicate helpers, stale public exports,
   and temporary diagnostics. Defer cosmetic or speculative cleanup. Any
   package-source edit creates a new candidate identity and must repeat every
   affected fail-fast and cumulative gate before qualification; never alter
   qualified source afterward.

   Freeze the population, seeds, power, endpoints, comparators, and decision
   before execution. Include all 12 adaptive geometry groups—not only
   previously failing groups—at below-, boundary-, and above-trigger strata,
   with power assessed per binding geometry/trigger stratum. Also cover
   compact, blend, boundary, invalid-pixel, varying-noise, shell, filament,
   and mixed compact/extended cases. Exercise the installed top-level
   `hebog.find_sources` path under Serial and caller-owned Dask, and require
   every binding geometry to match or outperform both PyBDSF references while
   retaining the cumulative Hebog incumbent; apply Aegean wherever its frozen
   endpoint is relevant. No pooled score may hide a failed geometry, trigger
   stratum, or endpoint.
3. [ ] **Confirm the exact candidate's engineering and public contract.** Run
   focused regression and executor-invariance tests, `just coverage`,
   `just check`, `just test-equivalence`, `just docs-build`,
   `just package-smoke-test`, and `just pre-commit`. Reconfirm the reviewed
   6.0-second 3,000-pixel incremental budget or record a packet-bound proof
   that its code path and identity are unchanged. Verify installed-wheel FITS
   input, catalogue/RMS/mask/diagnostic products, errors, schemas, atomic
   writes, bounded execution, retry/order invariance, and reproduction
   commands.
4. [ ] **Remove obsolete historical tooling without invalidating the
   evidence.** After the cumulative and qualification decisions are terminal,
   inventory the Phase 5
   validation scripts, freezers, overlays, and lifecycle-only tests. Keep the
   canonical current generators/evaluators, shared fixtures, and anything
   needed by the final readiness packet or notebooks. Remove superseded
   one-use executors and tests only when no maintained code or final evidence
   imports them. Retain behavioural regression tests even when their original
   one-off campaign harness is removed. Do not modify `src/hebog/` in this
   step; production cleanup was resolved before qualification. Record each
   removed path, its last immutable commit and
   SHA-256, and its replacement in
   `docs/reference/phase-5-provenance-index.md`; Git history remains the
   recovery mechanism.

   Do not create a separate provenance branch: branches are mutable, easy to
   lose, and make the release depend on parallel history. Preserve small
   hash-bound contracts and terminal decisions in the main history, and keep
   large generated products outside Git according to the existing evidence
   policy. Remove obsolete scratch only after confirming that the compact
   decision files used by notebooks and readiness remain available.
5. [ ] **Document and finalize scientific readiness.** Update the campaign
   overview, API reference and radio-astronomer workflow, supported profiles,
   scientific interpretation, limitations, reproducibility instructions,
   provenance index, `LOG.md`, and the Phase 6 handoff. Rebuild the fail-closed
   readiness packet without the deferred Rapthor profile, obtain separate
   packet-bound radio-astronomy and engineering acceptance, and publish one
   terminal readiness record. Do not prepare a version, tag, changelog, or
   release artifact; Release Please handles the next release.

Phase 5 closes when all exit-gate rows and all five items above pass for one
exact candidate and the terminal readiness record is published. Rapthor
integration, complete `filter_skymodel` performance, cutover, facility scale,
and release execution remain Phase 6 or later work.

#### Historical Phase 5 evidence

Campaign chronology and incident analysis live in `LOG.md` and
`docs/reference/phase-5-campaign-overview.md`; exact identities, consumed
authorities, and terminal decisions live in `config/contracts/` and the
ignored evidence store. Commit `707478c...` is the last plan revision that
retains the former inline execution chronology. Closed failures remain
immutable evidence and must never be rerun or rescored merely because their
narrative was removed from this current-work plan.

### Phase 6: Rapthor integration, minimum performance, and early release

Phase 6 begins only after Phase 5 has established all-check scientific parity,
retained the frozen incumbent Hebog quality, and published its terminal
scientific-readiness record. Its objective is the earliest safe, useful
improvement for Rapthor, not the final scientific or computational optimum.
Do not delay a Rapthor-integrated experimental release for a longer-term
absolute target or maximum facility scale once all binding science,
compatibility, operational, and minimum complete-path performance gates pass.

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
