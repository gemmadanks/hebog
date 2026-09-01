# Hebog execution log

This is the chronological execution record for the
[Hebog implementation plan](plans/source-finder-implementation.md). It records
material work, evidence, decisions, deviations, and immediate next steps; it
does not duplicate every commit.

Use the project records as follows:

- the implementation plan defines intended scope, phases, gates, risks, and
  remaining work;
- this log records what happened while executing that plan;
- `CHANGELOG.md` contains user-visible release changes managed by Release
  Please;
- architecture decision records under `docs/architecture/adr/` explain
  significant architectural choices;
- atomic Conventional Commits remain the detailed record of individual code
  changes: their subjects are written for user-facing release notes and their
  bodies provide developer context and validation;
- all agent-created commits remain local for human review and manual push.

Add entries in chronological order using ISO dates. Include commands, dataset
identifiers, revisions, and measured evidence when they affect a scientific or
performance conclusion. Do not add an entry for a routine implementation
commit that is fully explained by its subject and body. Update the plan only
when execution changes its scope, sequence, gates, risks, or decisions.

## Current position

Hebog has completed the technical Phase 0 contracts, Phase 1 bounded FITS/Zarr
I/O, Phase 2 deterministic background/RMS estimation, and Phase 3 compact
detection topology. Background/RMS estimation, automatic adaptive candidates,
connected-island reconciliation, compact deblending, and durable detection
products pass the governed automated gates. Named scientific review approved
the compact experimental scope on 2026-08-02, completing the Phase 3 exit
gate. Phase 4 measurement, fitting, and catalogue compatibility is next;
multiscale recovery, complete Rapthor integration, and multi-node scalability
remain later work.

## 2026-07-16 — Profiled the existing PyBDSF path

**Plan phase:** Pre-project investigation

**Completed**

- Profiled a representative 3000 by 3000 Rapthor image using adaptive RMS and
  three wavelet scales.
- Examined the existing PyBDSF and Rapthor execution model and identified
  background/RMS and repeated wavelet processing as the primary bottlenecks.
- Established that Gaussian fitting was not the first optimization target for
  this workload.

**Evidence**

| Measurement | Wall time |
| --- | ---: |
| PyBDSF true-sky pass, one core | 57.73 s |
| PyBDSF true-sky pass, four cores | 35.29 s |
| Flat-noise RMS pass, four cores | 9.55 s |
| Controlled interpolation experiment | 22.25 s |

Background/RMS estimation took 10.41 seconds and wavelet processing took
22.53 seconds in the normal four-core pass, together accounting for 95.4% of
measured operation time. Gaussian fitting took 0.07 seconds. These exploratory
measurements still require reproduction in Phase 0 before they become release
evidence.

**Decisions**

- Build a narrower Rapthor-focused source finder instead of reproducing every
  PyBDSF feature.
- Keep orchestration in Python and use NumPy, SciPy, Numba, and compiled or
  GIL-releasing kernels for array-intensive work.
- Let Rapthor own the top-level Dask graph and submit coarse tasks rather than
  distributing every pixel, window, or island.
- Target at least a 50% reduction in matched median `filter_skymodel` wall
  time, subject to scientific-equivalence and memory gates.

**Plan impact**

- The profiling evidence became the motivation, provisional budgets, and
  phase ordering in the implementation plan.

**Next**

- Create a dedicated source-finder project and preserve the evidence in a
  reproducible Phase 0 harness.

## 2026-07-18 — Bootstrapped the Hebog repository

**Plan phase:** Repository preparation

**Commits**

- `fa252e9` — initial commit
- `e79262a` — rename the distributable package to `hebog`
- `4f69c30` — initialize version `0.1.0`

**Completed**

- Replaced the template package name throughout the repository with `hebog`.
- Set the initial project and release metadata version to `0.1.0`.
- Set Release Please's bootstrap SHA to the full initial commit
  `fa252e9ec4f81aa05238fad7f40358426012f671`.

**Decisions**

- Use `hebog` for the repository, distribution, import package, and CLI.
- Incubate the experimental project independently while keeping its package,
  interfaces, tests, and build workflow portable.

**Evidence**

- Both the `hebog` console command and `python -m hebog` reported version
  `0.1.0` after the package scaffold was completed.

**Next**

- Port the useful source-finder planning and scaffold into Hebog without
  retaining a second, incompatible toolchain.

## 2026-07-18 — Ported and adapted the source-finder scaffold

**Plan phase:** Repository preparation

**Commit:** `4e7a7b9` — add initial project scaffolding

**Completed**

- Ported the useful planning, architectural constraints, test layout, data
  models, executor interfaces, CLI, documentation, configuration, and
  benchmark scaffold from the local prototype.
- Adapted the predecessor's conventions to Hebog's
  existing uv, just, GitHub Actions, Release Please, and MkDocs workflow.
- Added scheduler-independent requests and results, serial and existing-client
  Dask executors, public configuration, and an intentionally unimplemented
  pipeline boundary.
- Added unit, integration, scientific-equivalence, and benchmark test lanes.
- Replaced the remaining interactive example with a Marimo Python notebook and
  removed Jupyter, IPython, `nbmake`, `nbstripout`, editor integration, ignore
  rules, documentation, and locked dependencies.
- Added the durable source-finder implementation plan containing scientific
  gates, dataset coverage, phases, performance budgets, benchmark protocol,
  risks, and definition of done.

**Decisions**

- Scientific equivalence means matching the behaviour Rapthor consumes, not
  bitwise equality with PyBDSF.
- Public records remain small, materialised, and serializable; they do not
  contain open FITS files, scheduler clients, or mutable full-image objects.
- PyBDSF implementation code will not be copied or mechanically translated.
- Marimo is the only notebook workflow.

**Evidence**

- `just ci` passed.
- Six implemented tests passed and the two Phase 0 placeholder suites skipped.
- Coverage was 81% for the initial scaffold.
- Ruff, Pyright, pre-commit, strict Marimo validation, strict MkDocs, uv lock
  validation, and the isolated `hebog==0.1.0` wheel smoke test passed.

**Plan impact**

- `plans/source-finder-implementation.md` became the authoritative technical
  roadmap.
- Phase 0 was established as a hard prerequisite for algorithm work.

**Next**

- Review the testing approach before implementing comparison or scientific
  kernels.

## 2026-07-18 — Established the test-first execution strategy

**Plan phase:** Phase 0 preparation

**Commit:** `85234e6` — follow test-first strategy

**Completed**

- Added an explicit red-green-refactor workflow to every implementation phase.
- Defined the oracle hierarchy: analytic truth, mathematical and metamorphic
  properties, the Hebog serial reference, frozen PyBDSF compatibility products,
  and end-to-end Rapthor decisions.
- Split datasets into development, regression, and held-out qualification
  roles to reduce tuning against the final validation matrix.
- Defined unit/property, contract, integration, small-equivalence, acceptance,
  qualification, and benchmark lanes.
- Added strict pytest markers and separated portable CI from controlled
  qualification and wall-time testing.
- Added Hypothesis and initial property-based configuration tests.
- Added acceptance, equivalence-reference, and test-data governance
  scaffolding and documentation.

**Decisions**

- Use TDD by default for public contracts, pure scientific kernels, schemas,
  matching, error behaviour, and executor semantics.
- Use lightweight Given/When/Then pytest scenarios for Rapthor-facing
  behaviour.
- Do not add a Gherkin framework unless domain experts will actively review or
  author feature files.
- Keep qualification results out of routine development and enforce
  performance gates only on controlled runners.

**Evidence**

- `just ci` passed.
- Eight portable unit and integration tests passed with 81% scaffold coverage.
- Small equivalence and acceptance scaffolds selected and skipped as intended.
- `just test-qualification` selected the held-out qualification scaffold and
  skipped because Phase 0 data is not yet available.
- Ruff, Pyright, pre-commit, strict Marimo validation, strict MkDocs, uv lock
  validation, and the isolated wheel smoke test passed.

**Plan impact**

- The plan gained a testing strategy, independent oracle validation, dataset
  roles, BDD guidance, deterministic distributed-testing rules, and test-first
  tasks in every delivery phase.

**Next**

- Inventory the exact PyBDSF catalogue, RMS, mask, failure, and empty-result
  contracts used by LSMTool and Rapthor.
- Freeze development, regression, and qualification manifests.
- Write failing analytic tests for catalogue matching and RMS/mask comparison
  before implementing the Phase 0 comparison harness.

## 2026-07-18 — Adopted an incremental release strategy

**Plan phase:** Cross-cutting delivery policy

**Completed**

- Added a release strategy that permits coherent, tested vertical slices to be
  released before an entire delivery phase is complete.
- Added indicative `0.1.x` through `0.9.x` capability bands and defined the
  qualification required for `1.0.0`.
- Added release evidence requirements covering portable CI, relevant
  scientific suites, documentation, schemas, migration notes, and performance
  claims.
- Replaced the stale Phase 8 instruction to release `0.1` in the future; the
  repository is already versioned `0.1.0`.

**Decisions**

- Keep all pre-production releases experimental in the `0.x` series.
- Treat phase exit gates as readiness gates for dependent work rather than as
  release gates.
- Let Release Please and Conventional Commits determine actual versions; do
  not force phase numbers and release versions to match.
- Permit documented breaking changes before 1.0 while keeping public schemas
  explicitly versioned.
- Reserve `1.0.0` and Rapthor default cutover for the complete definition of
  done, scientific approval, and operational soak.

**Evidence**

- `just ci` passed after the plan and log changes.

**Plan impact**

- Frequent releases can now communicate incremental capability without
  weakening scientific, performance, or production-readiness gates.

**Next**

- Use the `0.2.x` capability band as guidance for the first Phase 0 vertical
  slices, without treating it as a fixed phase-version contract.

## 2026-07-18 — Planned domain language and architecture records

**Plan phase:** Phase 0 preparation

**Completed**

- Added a provisional domain glossary and explicit naming conventions to the
  Phase 0 deliverables.
- Added a domain model with code-native system-context and processing/data-flow
  diagrams, while deferring unstable executor detail.
- Added ADR tasks for Hebog's narrow Rapthor scope, external scheduler
  ownership, and the compatibility-schema boundary.
- Added domain-review requirements to the Phase 0 exit gate and terminology
  and diagram-maintenance risks to the plan.

**Decisions**

- Treat the glossary and diagrams as testable architectural documentation that
  is reviewed with the Phase 0 contracts, not as speculative upfront design.
- Record the already-settled scope and scheduler boundaries in ADRs 003 and
  004 before implementing them.
- Defer ADR 005 until the compatibility inventory supplies evidence, and write
  algorithm ADRs only when tests and benchmarks expose consequential choices.
- Use Mermaid for diagrams so they remain reviewable beside the documentation.

**Evidence**

- `just ci` passed after the plan and log changes: eight portable tests passed,
  the equivalence and acceptance scaffolds skipped as intended, and linting,
  type checking, strict Marimo validation, strict documentation, lockfile
  validation, and the isolated wheel smoke test succeeded.

**Plan impact**

- Phase 0 now freezes shared vocabulary and architectural boundaries as well as
  scientific contracts, datasets, comparison oracles, and baselines.
- The definition of done now requires the glossary and diagrams to match the
  released architecture and separate compatibility names from internal terms.

**Next**

- Begin Phase 0 by inventorying the PyBDSF, LSMTool, and Rapthor contracts and
  terminology, then draft the glossary, domain model, and ADRs 003 and 004.

## 2026-07-18 — Captured the first Phase 0 contract slice

**Plan phase:** Phase 0 — freeze baselines and contracts

**Completed**

- Traced the source-finding inputs, defaults, products, catalogue fields,
  empty behaviour, downstream diagnostics, and task boundary consumed by
  Rapthor.
- Added a machine-readable candidate inventory of repository revisions,
  dependency-definition hashes, and container-definition hashes.
- Added the provisional domain glossary, naming conventions, system-context
  diagram, and processing/data-flow diagram.
- Accepted ADR 003 limiting Hebog to Rapthor's source-finding contract and ADR
  004 retaining top-level scheduler ownership in Rapthor.

**Evidence**

- Rapthor was traced at
  `b1a64674b1022476cf052fc2d06ee3b16f031ecd` on the
  `gec-468-ai-migrate-to-prefect` branch.
- The local PyBDSF reference was
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c`; the local LSMTool reference was
  `4e5cf93046e309844c04382375f86e68929bd2d8` with two untracked files.
- Rapthor's pinned LSMTool commit
  `3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a` was available after refreshing
  the checkout, and its source-finding module matched the checked-out module.
- Rapthor directly consumes `Source_id`, `RA`, `DEC`, `Isl_Total_flux`,
  `Total_flux`, `DC_Maj`, `E_RA`, and `E_DEC`, plus true-sky/flat-noise RMS
  images, the island mask, filtered sky models, and source-count diagnostics.
- `just ci` passed: eight portable tests passed, equivalence and acceptance
  scaffolds skipped as intended, and linting, type checking, strict Marimo and
  MkDocs validation, lockfile validation, and the isolated wheel smoke test
  succeeded.

**Decisions**

- Treat the Rapthor source-finding contract, rather than the complete PyBDSF
  feature set, as Hebog's initial compatibility surface.
- Keep PyBDSF objects and terminology outside Hebog's scientific kernels;
  preserve external names only at a compatibility boundary.
- Treat Rapthor's `gec-468-ai-migrate-to-prefect` branch as the authoritative
  integration target because it owns the Prefect/Dask task runner.
- Keep the revision inventory in candidate status until it records the exact
  installed PyBDSF/LSMTool packages and an immutable built-container digest.

**Deviations and gaps**

- Rapthor declares `bdsf` without a version or revision.
- The refreshed PyBDSF checkout contains changes to island, RMS, and output
  behaviour, so its revision cannot substitute for the still-unknown package
  installed in the benchmark runtime.
- The inspected container definitions use mutable base-image tags; no built
  benchmark-container digest was available.
- The Phase 0 revision-capture task therefore remains open.

**Plan impact**

- Completed the contract inventory, provisional glossary, domain diagrams,
  and ADR 003/004 tasks.
- Kept domain review, frozen examples, contract tests, exact runtime capture,
  comparison oracles, datasets, and baseline reproduction open.

**Next**

- Capture installed package versions and the benchmark-container digest from
  the controlled Rapthor environment.
- Reproduce the representative PyBDSF timings and current matched
  `filter_skymodel` median before implementing the comparison harness.

## 2026-07-18 — Excluded the preliminary scaffold from project evidence

**Plan phase:** Cross-cutting scope clarification

**Completed**

- Removed `ska-sdp-source-finder` from the Phase 0 starting-revision inventory.
- Clarified that the implementation plan is owned by Hebog and must be
  justified against current consumer, dependency, and reference behaviour.

**Decision**

- Do not use the preliminary `ska-sdp-source-finder` scaffold or plan as a
  source of requirements, compatibility evidence, or migration constraints.
- Treat Rapthor's `gec-468-ai-migrate-to-prefect` branch, its pinned LSMTool
  code, and the applicable PyBDSF implementation and runtime as the
  authoritative technical sources.

This clarification supersedes any earlier implication that the preliminary
repository is a continuing project input. Work already adopted into Hebog
must stand on its current tests, documentation, decisions, and authoritative
source evidence.

## 2026-07-18 — Required released and master PyBDSF baselines

**Plan phase:** Phase 0 — freeze baselines and contracts

**Completed**

- Identified released PyBDSF `v1.14.1` at
  `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc` as the current Rapthor
  comparator.
- Identified the refreshed performance-improved PyBDSF `master` reference at
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c`, 40 commits after `v1.14.1`.
- Updated the plan, project guidance, and candidate revision inventory to
  require separate scientific and performance comparisons for both exact
  references.

**Decisions**

- Retain the original target of at least a 50% reduction in matched median
  `filter_skymodel` wall time relative to the released PyBDSF version used by
  Rapthor.
- Also require Hebog to be faster than the pinned PyBDSF `master` reference;
  the upper bound of the 95% bootstrap confidence interval for the median
  runtime ratio must be below `1.00`.
- Use released PyBDSF as the current compatibility reference. Treat `master`
  as forward-looking comparison evidence; adjudicate scientific differences
  using independent truth and the Rapthor contract.
- Pin both references for every benchmark record. Refresh `master`
  deliberately at qualification milestones without replacing historical
  results.

**Evidence**

- The local PyBDSF tag `v1.14.1` resolves to
  `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`.
- PyPI identifies `1.14.1` as the latest release at the capture date, publishes
  source provenance for the same commit, and reports source-distribution
  SHA-256
  `8d5113fecca19bb9f02a1a3e17aeb8f2d22c712cac9504e44271c4071f5434d2`.
- The range from `v1.14.1` to the recorded `master` includes an explicit
  residual-statistics speedup and RMS/adaptive-RMS simplifications, alongside
  scientific fixes affecting masks, fitting, fluxes, and outputs.

**Next**

- Confirm the installed released PyBDSF version inside the controlled Rapthor
  benchmark environment.
- Build isolated, matched environments and reproduce the same operation and
  complete `filter_skymodel` benchmark matrix for both PyBDSF references.

## 2026-07-18 — Made large-image scalability a core requirement

**Plan phase:** Cross-cutting architecture and qualification

**Completed**

- Added the 100,000-by-100,000-pixel target and 100-to-several-hundred-node
  Dask deployment to Hebog's scope, Phase 0 contract, delivery phases, risks,
  release milestones, and definition of done.
- Recorded that production nodes are expected to provide hundreds of GB of
  RAM and made tile batching and caches resource-aware rather than fixed-size.
- Accepted ADR 005, selecting bounded haloed tiles, deterministic ownership,
  boundary summaries, and hierarchical reconciliation for image-sized work.
- Required partition-invariance tests for tile edges and corners, tile shape,
  partition origin, worker topology, task order, and retry.
- Defined the large-image scientific oracle as generated truth, global
  invariants, partition invariance, and PyBDSF-comparable cut-outs rather than
  requiring PyBDSF itself to process the full 100,000-by-100,000 image.
- Added a dedicated `scalability` pytest marker, `just test-scalability` lane,
  and a skipped Phase 0 harness placeholder for controlled multi-node runs.
- Renumbered the planned compatibility-schema decision to ADR 006.

**Decisions**

- Treat a small image as one tile using the same scientific ownership and
  reconciliation semantics as a distributed image; do not develop a
  whole-image-only scientific path first.
- Keep worker memory proportional to a tile core, its stage-specific halo, and
  bounded work buffers. No worker, scheduler payload, or public record may
  require a complete large plane.
- Keep Dask graph size proportional to tiles and stages, not pixels, RMS
  windows, or small islands. Use mergeable boundary summaries and tree
  reductions instead of central image-sized gathers.
- Use admitted worker memory to exploit memory-rich nodes while reserving
  headroom for concurrent Rapthor work. Resource sizing may change batching
  and caching, but never scientific ownership or results.
- Reuse Rapthor's existing Dask cluster and resource budget in accordance with
  ADR 004; Hebog may construct a bounded operation subgraph but does not own a
  private cluster.
- Leave the physical chunk store and distributed output format open until
  Phase 0/1 I/O and restart benchmarks provide evidence.

**Evidence**

- A 100,000-by-100,000 image contains 10 billion pixels. One plane is 40 GB at
  `float32` or 80 GB at `float64`, before RMS, normalized, mask, multiscale,
  residual, and work arrays.
- Multiple simultaneously useful planes and work buffers can exceed one
  memory-rich node even when it has hundreds of GB of RAM, so distributed
  bounded-memory execution remains necessary.
- `just test-scalability`, `just test-benchmark`, and
  `just test-qualification` each selected only their intended scaffold and
  skipped pending Phase 0 data or infrastructure.
- `just ci` passed: eight portable tests passed; equivalence and acceptance
  scaffolds skipped as intended; and linting, type checking, strict Marimo and
  MkDocs validation, lock validation, and the isolated wheel smoke test
  succeeded.

**Plan impact**

- Phase 0 must freeze the input/output plane set, storage target, tile/halo
  constraints, per-worker memory ceiling, runtime, scheduler-overhead, and
  strong/weak-scaling efficiency gates.
- Phase 6 must qualify the 100,000-by-100,000 case at 100 and at least 200
  worker nodes and record the complete 1/10/50/100/200-plus-node matrix where
  the approved facility provides it.

**Next**

- Identify the representative large-image storage and Dask facility, then
  agree the provisional resource and scaling SLOs.
- Add analytic partition-manifest, halo, ownership, and boundary-reconciliation
  tests before implementing image I/O or scientific kernels.

## 2026-07-18 — Made performance goals size-stratified

**Plan phase:** Cross-cutting performance contract

**Completed**

- Reframed the 50% improvement over released PyBDSF and the pinned `master`
  comparison as minimum release gates rather than an optimization endpoint.
- Added a logarithmic 256-to-100,000-pixel performance matrix with sparse,
  normal, and dense or extended workloads at every representative size.
- Required benchmark cases on both sides of executor, storage, partition, and
  batching crossovers instead of hard-coding one image-size threshold.
- Added a previous-Hebog performance curve and a confidence-based rule for
  reviewing supported-size regressions greater than 5%.
- Updated architecture and contributor guidance so small inputs use the
  lowest-overhead one-tile path and acquire chunking or Dask overhead only
  when complete-runtime measurements justify it.

**Decisions**

- Optimize complete end-to-end latency and useful throughput across all
  supported sizes; do not trade small-input latency for large-image throughput
  silently, or vice versa.
- Treat 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000, and 100,000 pixels per
  side as benchmark anchors, not permanent execution thresholds.
- Use image planes, halos, source density, storage, admitted CPU and RAM, and
  measured overhead to select the lowest-cost valid plan within the executor
  supplied by the caller.

**Evidence**

- `just check` and `just docs-build` passed.
- `just ci` passed: all push-stage hooks succeeded; eight portable tests
  passed; equivalence and acceptance scaffolds skipped as intended; and strict
  Marimo and MkDocs validation, lock validation, and the isolated wheel smoke
  test succeeded.

**Next**

- During Phase 0, reproduce both PyBDSF references and establish the initial
  Hebog performance curve at every runnable size.
- Freeze one-tile overhead budgets and the first measured serial, local, Dask,
  storage, partition, and batching crossover cases.

## 2026-07-18 — Made maintainability and reuse explicit quality gates

**Plan phase:** Cross-cutting architecture and engineering quality

**Completed**

- Defined maintainability, extensibility, interoperability, testability, and
  performance transparency as release qualities alongside scientific
  correctness, speed, and scalability.
- Clarified ADR 003: Rapthor defines the first qualified feature slice but is
  not a dependency of Hebog's scientific core; other pipelines and science
  workflows use the public API through their own orchestration and adapters.
- Added Pythonic clean-code guidance, inward dependency rules, code-review
  checks, and a dedicated quality-attributes documentation page.
- Expanded Ruff to enforce Bugbear, comprehension, complexity, naming,
  performance-idiom, simplification, unused-argument, and Ruff-specific rules
  in addition to the existing formatting, import, and Pylint checks.
- Enabled strict Pyright checking across `src/` and `tests/` and added an 80%
  branch-aware coverage floor.
- Added an architecture test that prevents algorithms and domain records from
  importing adapters, I/O, executors, workflow frameworks, or concrete
  schedulers.

**Decisions**

- Keep the qualified scope Rapthor-focused while making the scientific API,
  domain records, configuration, and algorithms pipeline-neutral.
- Introduce narrow protocols only at demonstrated variation points. Do not add
  a generic plugin framework, registry, or service locator in anticipation of
  unknown consumers.
- Isolate profiled low-level optimization behind small typed functions and
  retain a readable deterministic serial oracle.
- Require a documented non-Rapthor workflow through the public API before
  `1.0.0` as evidence that reuse works through supported boundaries.

**Evidence**

- The focused architecture and Dask executor tests passed: three tests.
- The expanded Ruff rules and strict Pyright passed with zero diagnostics.
- `just coverage` passed with ten portable tests and 81.03% branch-aware
  coverage against the new 80% floor; `just docs-build` passed strictly.
- `just ci` passed: all push-stage hooks, strict typing and documentation,
  portable coverage tests, lock validation, Marimo validation, and isolated
  wheel build/install/import succeeded; equivalence and acceptance scaffolds
  skipped as intended.

**Next**

- Add import-time side-effect checks as the I/O and orchestration boundaries
  are implemented.
- Define image-source and product-sink seams from concrete FITS and alternate
  workflow tests rather than designing them speculatively.

## 2026-07-18 — Assessed Rust and C++ native acceleration

**Plan phase:** Cross-cutting performance and maintainability architecture

**Completed**

- Assessed whether project-owned Rust or C++ would improve Hebog after
  accounting for NumPy/SciPy compiled kernels, Numba, end-to-end bottlenecks,
  Dask thread ownership, array-copy costs, and the supported wheel matrix.
- Documented candidate kernels, non-candidates, Rust/PyO3 and C++/pybind11
  trade-offs, FFI requirements, packaging implications, and primary sources.
- Added a quantitative reconsideration gate and conditional native-code tasks,
  risks, release requirements, review checks, and definition-of-done criteria.

**Decisions**

- Do not add a Hebog C++ or Rust extension before scientific kernels and
  representative end-to-end profiles exist. Use vectorized NumPy/SciPy first,
  then a reviewed Numba implementation for material custom loops.
- Consider a native prototype only when a self-contained kernel remains at
  least 10% of complete time in two size regimes, blocks a frozen resource or
  scale gate, or already exists as a mature reviewed native library.
- Require at least a 2x kernel speedup and a statistically supported 5%
  end-to-end improvement unless the extension instead unlocks a failed memory
  or scalability gate.
- Prefer Rust for a new self-contained kernel because memory and thread safety
  support maintainability. Prefer C++ when reusing a mature C/C++ library or
  when ecosystem or team evidence makes it lower risk.
- Require an accepted ADR, coarse zero-copy-capable array boundary, explicit
  interpreter and thread handling, safety tests, scientific parity, and the
  complete supported binary-wheel matrix before production use.

**Evidence**

- `just check` passed with nine quick tests; `just docs-build` passed strictly.
- `just ci` passed: all push-stage hooks, strict typing and documentation,
  ten portable coverage tests at 81.03%, lock and Marimo validation, and the
  isolated universal wheel build/install/import succeeded; equivalence and
  acceptance scaffolds skipped as intended.

**Next**

- Profile each implemented phase before considering a native spike; record
  array copies, memory bandwidth, I/O, scheduling, and kernel time separately.
- If a kernel passes the decision gate, benchmark the smallest Rust and/or C++
  prototype against the same Python/Numba contract before choosing a language.

## 2026-07-18 — Established deterministic validation data

**Plan phase:** Phase 0

**Completed**

- Added a strict versioned manifest for two analytic and seeded development
  datasets with explicit roles, provenance, redistribution status, beam/WCS
  metadata, expected statistics, complete recipes, and canonical SHA-256
  recipe digests.
- Added an in-memory generator for bounded analytic tests and a
  window-addressable generator for large logical planes.
- Derived random noise from global pixel addresses so generation is exactly
  invariant to window layout, call order, and worker assignment.
- Added validation for duplicate identifiers, stale recipe digests, invalid
  WCS/beam/source geometry, inconsistent statistics, and accidental unbounded
  complete-plane allocations.

**Decisions**

- Treat a generator version and complete canonical recipe as provenance; a
  random seed alone is insufficient.
- Keep the initial checked-in datasets in the `development` role. Do not claim
  frozen regression, qualification, or PyBDSF reference products until their
  manifests and scientific review are complete.
- Generate the future 100,000-by-100,000 cases through bounded windows and
  external materialised storage, never one NumPy allocation or a Git artifact.

**Evidence**

- Twelve analytic tests passed, including exact whole-plane versus stitched-
  window equality, seed repeatability, analytic source amplitude, checksum
  enforcement, role completeness, and allocation safety.
- Focused Ruff and strict Pyright checks passed with no diagnostics.

**Next**

- Implement and analytically prove the catalogue, RMS-map, and mask comparison
  reports before comparing frozen external products.
- Define the large performance/scalability recipes, assign reviewed regression
  and qualification roles, and capture immutable products from both exact
  PyBDSF references.

## 2026-07-18 — Proved the scientific comparison oracle

**Plan phase:** Phase 0

**Completed**

- Implemented canonical catalogue records with explicit angular and flux
  units, great-circle coordinate separation, right-ascension wraparound, and a
  global one-to-one assignment.
- Defined a deterministic assignment objective that maximizes valid match
  count, then total matched integrated flux, then angular proximity.
- Added catalogue reports for unmatched rows, completeness, reliability,
  beam-normalized position differences, and peak/integrated flux differences.
- Added RMS-map reports with explicit masking, non-finite and zero-reference
  exclusions, plus boolean-mask confusion and agreement reports.

**Decisions**

- Keep the oracle independent of Hebog algorithms and PyBDSF readers so an
  adapter defect cannot redefine scientific equivalence.
- Use explicit empty-set semantics and `None` for unavailable numerical
  metrics; never manufacture a denominator epsilon or allow array
  broadcasting.
- Keep this first matcher one-to-one. Source/component grouping requires an
  independently tested compatibility adapter rather than duplicated rows.

**Evidence**

- Seventeen analytic tests passed for unit conversion, spherical coordinates,
  ambiguous assignments, unmatched and empty catalogues, flux/report metrics,
  masks, RMS exclusions, and invalid inputs.
- Focused Ruff and strict Pyright checks passed with no diagnostics.

**Next**

- Add the machine-readable external-product runner and immutable outputs from
  released PyBDSF and pinned `master`, then apply these reports to both.
- Stratify catalogue metrics by compact, blended, extended, edge, and SNR
  classes after the reference schemas and qualification manifest are frozen.

## 2026-07-18 — Isolated compatibility behind versioned schemas

**Plan phase:** Phase 0

**Completed**

- Recorded ADR 006 after reconciling the provisional Rapthor contract with the
  domain model, large-image architecture, and alternate-workflow requirement.
- Selected versioned, domain-oriented internal schemas with legacy
  PyBDSF/LSMTool/Rapthor names and product behaviour confined to outer
  adapters.
- Defined schema-version, unsupported-version, migration, unit, null,
  ordering, empty-product, and downstream-behaviour confirmation requirements
  for Phase 1.

**Decisions**

- Internal records remain small, typed, serializable, and free of live files,
  scheduler clients, workflow state, and image-sized arrays.
- Compatibility adapters own legacy columns, suffixes, units, filtering,
  grouping, diagnostics, and reviewed empty/failure translations.
- Frozen PyBDSF products validate compatibility but do not define Hebog's
  internal object model or become a runtime dependency.

**Next**

- Enforce import-time side-effect and compatibility dependency boundaries.
- Derive the exact versioned catalogue and materialised-product fields from
  failing Phase 1 round-trip and Rapthor adapter contract tests.

## 2026-07-18 — Enforced inert library imports

**Plan phase:** Phase 0

**Completed**

- Added a static architecture gate that resolves imported aliases and rejects
  file, process, network, scheduler-construction, and task-submission calls at
  module or class import scope while allowing explicit calls inside functions.
- Added inward-dependency checks for public configuration and pipeline modules
  in addition to the existing algorithm and domain-record rules.
- Added an isolated runtime test proving that importing `hebog.pipeline` does
  not load `distributed`.
- Changed the executor package to load `DaskExecutor` lazily while preserving
  the existing `from hebog.executors import DaskExecutor` API.

**Evidence**

- The new runtime test first failed because `hebog.executors` eagerly imported
  its Dask implementation, then passed after the lazy boundary was added.
- Ten focused architecture, serial-executor, and Dask integration tests
  passed; Ruff and strict Pyright reported no diagnostics.

**Decisions**

- Library imports may define types, validators, immutable constants, and
  package metadata, but do not discover work, touch science/workflow data,
  mutate process state, access the network, create clients, or start work.
- `__main__.py` remains the explicit CLI side-effect boundary and is excluded
  from the inert-library-module scan.
- Concrete scheduler implementations are optional outer dependencies and are
  imported only when requested by a caller.

**Next**

- Add the versioned machine-readable comparison-run and benchmark evidence
  schemas before capturing external PyBDSF products or timings.
- Freeze exact installed dependencies and container digests in the controlled
  released-PyBDSF and pinned-`master` environments.

## 2026-07-18 — Versioned benchmark and comparison evidence

**Plan phase:** Phase 0

**Completed**

- Added strict version-1 benchmark and scientific-comparison evidence models
  with deterministic atomic JSON writing and validated loading.
- Required exact software revisions, container/dependency/environment and
  dataset/configuration checksums, workload roles/classes, resource topology,
  complete-run metrics, and uniquely named stage metrics.
- Bound scientific reports to exact candidate and reference product-manifest
  checksums rather than only the shared input dataset.
- Distinguished unavailable optional instrumentation from measured zeroes and
  required a non-empty reason for every unavailable metric.
- Required one warm-up plus five measured repetitions for reviewed benchmark
  evidence and full topology/efficiency metrics for reviewed multi-node runs.
- Enforced aggregate worker-memory limits within node RAM after reserved
  headroom.

**Evidence**

- Nine focused tests passed for canonical JSON round trips, reviewed-run
  protocol enforcement, duplicate detection, unavailable metrics, timezone
  safety, memory admission, multi-node scaling records, and embedded
  catalogue/RMS/mask reports.
- Focused Ruff and strict Pyright checks passed with no diagnostics.
- `just ci` passed: 54 portable tests passed at 90.30% branch-aware coverage;
  all push-stage hooks, strict documentation and Marimo validation, lock
  validation, and the isolated wheel build/install/import succeeded.

**Decisions**

- Exploratory evidence remains recordable but cannot silently satisfy reviewed
  benchmark protocol requirements.
- Released PyBDSF, pinned PyBDSF `master`, previous Hebog, and candidate Hebog
  runs use separate evidence documents with exact identities rather than one
  favourable aggregate.
- Raw evidence remains ignored or externally stored; only compact reviewed
  summaries and reproduction metadata enter Git.

**Next**

- Use the schema to capture exact installed packages, container digests, and
  matched timings for released PyBDSF and pinned `master`.
- Freeze the logarithmic workload matrix and controlled facility resource
  contract, then record Hebog evidence at every runnable size tier.

## 2026-07-18 — Froze Phase 0 validation and scale contracts

**Plan phase:** Phase 0

**Completed**

- Froze a complete 256-to-100,000 performance ladder across sparse, normal,
  and dense-or-extended work, with initial execution/storage crossover probes
  and a rule requiring measured crossovers to gain adjacent cases.
- Froze the previous-Hebog confidence rule and warm one-tile configuration,
  FITS I/O, partition-planning, serial, local, and Dask overhead budgets.
- Froze the provisional 100,000-square plane, storage, tile/halo, graph,
  memory, spill, runtime, occupancy, and strong/weak scaling contract at 1,
  10, 50, 100, and 200 nodes.
- Added separate regression and held-out qualification manifests, including a
  window-generated 30,000-square regression case and the 100,000-square
  qualification recipe.
- Replaced the acceptance placeholder with ten strict-xfail contract and
  Given/When/Then-style acceptance specifications. Each frozen public
  behaviour has one test owner, and an unexpected pass now fails CI until the
  specification is reviewed and made normally passing.

**Evidence**

- The checked-in contracts validate through strict immutable Pydantic models;
  focused tests cover matrix completeness, worker-memory admission, topology
  coverage, dataset roles/checksums, and exact behaviour-to-test ownership.
- `just check` passed with 60 portable tests and four expected contract
  failures. `just test-contract` reported four expected failures;
  `just test-acceptance` reported six. The strict documentation build passed.

**Decisions**

- Use a representative 512 GiB production planning node with four 80 GiB
  worker limits after 64 GiB platform and 128 GiB concurrent-pipeline
  reserves. Qualification records the real facility rather than treating this
  planning profile as measured fact.
- Treat the scale and scientific gates as frozen engineering requirements,
  not demonstrated or domain-approved evidence. The review record names the
  independent scientific and facility sign-offs still required.
- Keep the qualification recipe reproducible but held out from routine tuning;
  large recipes are generated only through bounded windows.

**Next**

- Capture released and pinned-master PyBDSF products and matched repetitions
  in the now-frozen environment and evidence schemas.
- Measure the one-tile overhead probes and replace exploratory timing notes
  with compact provenance-bound summaries.

## 2026-07-18 — Completed the technical Phase 0 baseline

**Plan phase:** Phase 0

**Commits**

- `88ac484` — reproducible released/master PyBDSF campaigns and evidence
- `2ff1946` — immutable PyBDSF products and real equivalence tests
- `ffdbf2c` — typed warm one-tile overhead probe
- `3a74134` — final runtime, dataset, wheel, and overhead evidence
- `b89bfee` — immutable image guard for master-wheel rebuilds

**Completed**

- Confirmed released PyBDSF 1.14.1, built pinned master at
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c`, and captured the exact LSMTool,
  Rapthor, dependency-inventory, wheel, container, environment, configuration,
  and dataset identities.
- Ran one warm-up and five measured repetitions for both references on the
  compact 256-square and representative 3,000-square cases in a fresh
  container per repetition.
- Froze the seven compact Rapthor-facing products for both references and
  replaced the skipped equivalence scaffold with checksum, catalogue, true-
  and flat-RMS, and mask comparisons.
- Bound the restricted representative dataset to individual hashes for both
  images, both sky models, vertices, and the Measurement Set directory tree.
- Measured configuration, FITS I/O, one-tile planning arithmetic, serial,
  reused local-thread, and caller-owned warm Dask overhead 50 times; all
  exploratory 95th percentiles passed the provisional budgets.

**Evidence**

| Matched median | PyBDSF 1.14.1 | PyBDSF master |
| --- | ---: | ---: |
| Compact complete | 0.715 s | 0.672 s |
| Representative complete | 46.654 s | 45.015 s |
| Representative true-sky stage | 32.945 s | 31.860 s |
| Representative flat-noise stage | 12.851 s | 12.694 s |

Pinned master was 3.51% faster than release on the representative complete
median. The reference catalogues, RMS arrays, and mask arrays agreed exactly
on the compact case. Maximum measured representative RSS was approximately
1.30 GB for each reference. Copy counts remain explicitly unavailable because
external PyBDSF exposes no counter; Dask task, transfer, and spill counts are
applicable zeroes for these single-process reference runs.

**Deviations and limitations**

- LSMTool adds wall-clock history comments to sky-model text outputs. The
  campaign gate excludes only `#` history comments from cross-repetition
  identity; catalogues, diagnostics, RMS maps, and masks remain byte-stable.
- The original Rapthor run moved its intermediate sky-model inputs. The
  controlled run uses the corresponding generated rich-demo models, now bound
  by individual checksums.
- One-tile planning and local-thread measurements are Phase 0 proxies. Phase 1
  replaces them with real implementations without changing the frozen budgets.
- Domain and facility sign-off are not inferred from technical completion.

**Next**

- Record named scientific and facility review when those authorities are
  available.
- Begin Phase 1 with failing FITS, WCS, beam, partition, and internal-schema
  tests while retaining released and master PyBDSF as separate comparators.

## 2026-07-31 — Ordered the remaining Phase 0 closure work

**Plan phase:** Phase 0 closure

**Completed**

- Distinguished the completed technical foundation from full Phase 0 closure.
- Ordered the remaining work: align the public scaffold with the frozen
  compatibility contract, harden evidence provenance, obtain named scientific
  sign-off, apply reviewed amendments, and retain facility qualification as a
  separate pre-demonstration gate.
- Added a linked scientific-review packet and a sign-off form covering reviewer
  authority, decision, amendments, and held-out qualification-data handling.
- Clarified that Phase 1 FITS, bounded-I/O, partition, and atomic-write work may
  start during review, while stable scientific names, thresholds, and product
  semantics must wait for sign-off and scientific sign-off must precede Phase
  2.

**Next**

- Reconcile the exported request, result, and configuration records with ADR
  006 and the Rapthor contract.
- Harden the retained Phase 0 baseline provenance and reproduction metadata.
- Complete and record the scientific review using the reviewer packet.

## 2026-07-31 — Reconciled the public and Rapthor contracts

**Plan phase:** Phase 0 closure

**Completed**

- Defined the public request and result as one pipeline-neutral image analysis
  with one catalogue, RMS image, source-filtering mask, diagnostics record,
  timing, and schema version.
- Made detection and island thresholds explicit and unit-qualified instead of
  silently selecting one survey or workflow profile.
- Removed speculative RMS, multiscale, and executor-timing options from the
  scientific configuration and placed the traced Rapthor/LSMTool choices in a
  versioned compatibility record.
- Added serializable Rapthor request and result records for its
  primary-beam-corrected and flat-noise branches, filtered sky models, optional
  legacy mask, and diagnostics.
- Split the frozen public behavior into a scheduler-independent one-image
  contract and a separate Rapthor adapter acceptance behavior.

**Evidence**

- Focused configuration, record, manifest, contract, and acceptance tests:
  15 passed and 11 strict expected failures behaved as specified.

**Next**

- Amend the provisional terminology and thresholds from the scientific
  pre-review, including the difference between Rapthor strategy values and its
  helper fallbacks.
- Harden the baseline runner identities and retained evidence provenance.

## 2026-07-31 — Corrected and hardened the Phase 0 reference baselines

**Plan phase:** Phase 0 closure

**Completed**

- Found that the original baselines used Rapthor's `7.5/5.0` helper fallback
  instead of the `5.0/3.0` thresholds passed by the rich Prefect demo and
  normal production strategies.
- Found that the immutable reference image's preinstalled LSMTool `bdsf.py`
  matched older commit `4604b01`, not Rapthor's declared `3adf3d6` pin.
- Made both thresholds mandatory runner arguments and made the runner verify
  clean exact Rapthor and LSMTool checkouts, imported package/module identity,
  the master-wheel checksum, input hashes, container digest, and exact
  runner/compiler hashes.
- Excluded mutable CASA `table.lock` files from Measurement Set scientific
  identity and retained sanitized installed-package inventories plus raw
  inventory hashes in a durable environment record.
- Repeated the released and pinned-master compact and representative campaigns
  with one warm-up and five serialized measurements, replaced the governed
  evidence and compact fixtures, and regenerated the independent comparison.

**Evidence**

| Corrected matched median | PyBDSF 1.14.1 | PyBDSF master |
| --- | ---: | ---: |
| Compact complete | 1.166 s | 1.130 s |
| Representative complete | 45.614 s | 42.527 s |
| Representative primary-beam-corrected stage | 32.610 s | 30.305 s |
| Representative primary-beam-uncorrected stage | 12.582 s | 11.939 s |

- Pinned master was 6.8% faster on representative complete wall time and 4.3%
  lower on median complete CPU time.
- Maximum representative RSS was 1,298,513,920 bytes for release and
  1,302,560,768 bytes for master.
- The compact products still matched exactly and contained three source rows.
  The representative diagnostics contained 12 source rows for release and 14
  for master.
- Two accidentally overlapping diagnostic attempts were stopped and discarded
  before the final serialized campaigns; none of their products or timings
  enter governed evidence.

**Deviations and limitations**

- The old `7.5/5.0` results are retained only in Git history and ignored raw
  directories; all checked-in reviewed reference evidence is superseded by the
  corrected profile.
- The immutable image and restricted representative inputs remain local-only,
  so reproduction is limited to a controlled runner until durable remote
  artifact locations are approved.

**Next**

- Complete named human review of the scientific pre-review amendments.
- Publish or approve durable controlled-data and container locators if
  independent-host reproduction becomes a Phase 0 closure requirement.

## 2026-07-31 — Completed the first scientific sign-off research pass

**Plan phase:** Phase 0 closure

**Completed**

- Compared the provisional Hebog contract with official PyBDSF,
  ASKAPsoft/Selavy, Aegean, SKA SDP, WSClean, CASA, and LOFAR documentation,
  published source-finder challenges, and the pinned Rapthor implementation.
- Amended the glossary to use primary-beam-uncorrected and
  primary-beam-corrected image names, distinguish source candidates,
  components, islands, and sky-model components, and require reference
  frequency and spectral-model conventions.
- Documented Rapthor's three threshold profiles, optional mask, dummy-source
  workaround, copied pseudo-RMS blank path, and released/master source-count
  divergence.
- Replaced the fixed `98%` low-SNR compatibility gate with stratified
  completeness/reliability curves, 95% confidence intervals, and a
  reviewer-approved non-inferiority margin against governed truth.
- Added the findings and explicit human decisions to the scientific reviewer
  packet.

**Decision**

- The first-pass disposition is **amend before scientific approval**. This is
  research support, not named scientific sign-off.

**Next**

- A qualified human reviewer must approve or amend the `5.0/3.0` normal and
  `5.0/4.0` early-cycle profiles, canonical schema and primary-beam language,
  empty-product migration, MFS scope, and revised gate confidence rule before
  Phase 2 algorithms or stable scientific defaults.

## 2026-07-31 — Began Phase 1 with bounded FITS input

**Plan phase:** Phase 1

**Completed**

- Added the pipeline-neutral `ImageSource` seam with explicit half-open global
  bounds, small image metadata, and owned bounded window records.
- Implemented lazy FITS primary-plane validation and section reads for 2D
  images and conventional singleton leading axes without materialising the
  complete plane.
- Preserved non-finite input values while exposing an explicit validity mask,
  required a parseable brightness unit, and rejected missing data, zero-sized
  planes, corrupt files, vectors, and non-singleton cubes.
- Followed red-green-refactor: the focused contract first failed because the
  FITS source was absent, then passed after the minimum implementation.

**Evidence**

- Fifteen focused FITS integration cases pass.
- The new `hebog.io` modules have 100% line and branch coverage.

**Next**

- Add deterministic partition manifests, clipped halos, and ownership tests.
- Extend metadata validation to the restoring beam and celestial WCS.
- Add retryable product chunks and versioned catalogue/result schemas.

## 2026-07-31 — Added deterministic partition ownership

**Plan phase:** Phase 1

**Completed**

- Added a versioned, pickle-safe partition manifest whose row-major tile cores
  assign every output pixel to exactly one owner.
- Added stage halo validation, image-edge clipping, deterministic tile IDs,
  explicit global core/read bounds, and local core slices into each read
  window.
- Added shifted partition origins for invariance tests without changing
  ownership coverage.
- Moved global image bounds into the scheduler-independent domain records so
  partition planning does not depend on FITS or another concrete store.
- Followed red-green-refactor: the focused tests first failed because the
  partition planner was absent, then passed with the canonical planner.

**Evidence**

- Unit tests prove one-tile collapse, multi-tile and shifted-origin exact
  ownership, halo clipping, row-major ordering, serialization, global/local
  coordinate agreement, invalid geometry, and malformed-record rejection.
- The new partition planner and records have 100% line and branch coverage.

**Next**

- Extend FITS metadata to restoring-beam and celestial-WCS validation.
- Add checksummed retryable product chunks and atomic restart semantics.
- Define versioned catalogue and materialised-result schemas from their
  round-trip tests.

## 2026-07-31 — Added physical FITS image metadata

**Plan phase:** Phase 1

**Completed**

- Extended the bounded FITS source to require a finite ordered restoring beam,
  a reconstructable two-axis celestial WCS, its coordinate frame, and a
  positive reference frequency in addition to shape and brightness unit.
- Supported reference frequency from `RESTFRQ`, `RESTFREQ`, or an explicit WCS
  frequency axis so the contract does not depend on one imager's convention.
- Kept beam and serialized celestial-WCS metadata as plain pickle-safe domain
  records; Astropy WCS objects are reconstructed only at the I/O boundary.
- Rejected missing or invalid beam geometry, celestial coordinates, and
  frequency metadata before scientific processing.
- Followed red-green-refactor: the focused tests first failed on the missing
  WCS reconstruction boundary, then passed after the metadata implementation.

**Evidence**

- Focused tests cover WCS coordinate round-trips, beam fields, primary and WCS
  frequency conventions, invalid physical metadata, record serialization, and
  all previous FITS/window cases.
- The new image metadata and extended FITS boundary have 100% line and branch
  coverage.

**Next**

- Add checksummed retryable product chunks and interrupted-write recovery.
- Define versioned catalogue and materialised-result schemas through failing
  empty and populated round-trip tests.
- Measure bounded FITS reads and avoidable copies across the small-image
  crossover anchors.

## 2026-07-31 — Repaired cross-platform and equivalence CI

**Plan phase:** Phase 0 maintenance during Phase 1

**Completed**

- Limited the reference-runner configuration test to platforms that provide
  the POSIX-only `resource` instrumentation used by its Linux container, so
  Windows does not import an execution script that it cannot run.
- Preserved the benchmark runner byte-for-byte because its SHA-256 is part of
  the reviewed Phase 0 campaign provenance.
- Restored both compact diagnostics fixtures byte-for-byte from measured
  repetition 1 of the reviewed 5/3 release and master campaigns. The Phase 0
  merge had updated their governed manifest to the new 15-byte artifact and
  checksum but retained the older 20-byte pretty-printed files.

**Evidence**

- The test now reports an intentional platform skip when `resource` is
  unavailable and continues to exercise the explicit 5/3 configuration on
  supported systems.
- The reference runner retains its governed SHA-256
  `61d72af98fe00e44fce59ae20032d467e9fcb3b1fcf91afa2ebb126b7dafbea7`.
- Both restored diagnostics files are 15 bytes with SHA-256
  `32228968d2f89325f36d21b883fc3e555e1278c14685fe6db8b9983109c9ce59`,
  exactly matching the governed product manifest and the retained reviewed
  campaign artifacts.
- The focused baseline-script tests and the complete equivalence lane pass.

**Next**

- Resume Phase 1 product-sink and retryable materialisation work after the
  CI-fix commit is reviewed.

## 2026-07-31 — Added retryable intermediate product chunks

**Plan phase:** Phase 1

**Completed**

- Added a versioned, pickle-safe product-chunk record containing its product
  and tile identity, global core bounds, canonical relative path, dtype,
  shape, byte size, and SHA-256 without embedding pixel arrays.
- Added a narrow scheduler-independent product-sink protocol and one concrete
  filesystem implementation; no registry, scheduler client, or workflow
  dependency enters the scientific boundary.
- Published two-dimensional NumPy cores through flushed same-directory partial
  files and atomic hard links so a final path never exposes incomplete bytes
  and concurrent attempts cannot overwrite one another.
- Made identical retries idempotent, conflicting retries fail closed, and
  retries after failures immediately before or after publication recoverable.
- Validated paths, checksums, array metadata, object-dtype rejection, and
  symlink containment before workers consume or publish products.
- Followed red-green-refactor: focused tests first failed on the absent chunk
  record and sink module, then passed after the minimal implementation.

**Evidence**

- Twenty-six focused unit and integration tests cover record serialization,
  normal round trips, identical and conflicting retries, injected failures,
  missing and corrupted files, invalid arrays, metadata disagreement, and
  path-containment failures.
- The new product record and filesystem sink have 100% line and branch
  coverage. The portable suite passes 190 tests with 4 expected failures and
  total branch-aware project coverage of 89.94%.

**Next**

- Define a versioned materialised-result manifest that records the expected
  complete chunk set and detects missing, duplicate, or mixed-run products.
- Define empty and populated catalogue schemas through round-trip tests.
- Materialise compatible FITS, RMS, mask, and catalogue products atomically
  from validated chunk manifests.

## 2026-07-31 — Added the intermediate-storage decision gate

**Plan phase:** Phase 1

**Completed**

- Reassessed the NumPy-file/hard-link product sink before building the
  materialised-result manifest on its private layout.
- Made Zarr v3 the preferred intermediate-plane candidate because it already
  provides maintained multidimensional chunk storage, Dask integration,
  multiple storage backends, codec pipelines, and checksum codecs.
- Kept the current sink as a behavioural prototype and serial oracle rather
  than declaring it the production format.
- Added an ADR and benchmark gate comparing Zarr local and
  deployment-representative stores against the oracle and direct FITS across
  size and execution crossovers.
- Kept scientific ownership, WCS/beam/unit schemas, strict missing-chunk
  handling, run provenance, conflict policy, and validated completion
  manifests in Hebog rather than delegating them to an array format.
- Added Arrow/Parquet as a separate candidate for internal catalogue shards;
  workflow-compatible FITS and LSMTool products remain adapter outputs.

**Evidence**

- The plan links the official Zarr and Dask storage documentation and records
  the alignment, backend atomicity, codec, checksum, concurrency, failure,
  restart, and performance evidence required for selection.
- The decision remains open until a reproducible prototype passes the
  scientific, recovery, portability, and performance gates.

**Next**

- Write the intermediate-storage ADR as proposed and implement the smallest
  Zarr v3 prototype behind the existing product-sink boundary.
- Compare it with the NumPy-file oracle before defining a materialised-result
  schema that depends on either physical layout.

## 2026-07-31 — Accepted the gated Zarr intermediate-store decision

**Plan phase:** Phase 1

**Completed**

- Added Zarr 3.1.6 as the newest Zarr v3 line compatible with Hebog's Python
  3.11 support floor; Zarr 3.2 requires Python 3.12.
- Implemented a small `ZarrProductSink` behind the generic product-sink
  protocol, with caller-side product initialization and no scheduler or open
  store in its serializable state.
- Added a physical-layout-neutral, versioned `ZarrProductChunk` record with
  global core bounds, dtype, shape, and logical content SHA-256.
- Aligned zero-origin canonical tile cores one-to-one with regular Zarr chunks
  and explicitly configured little-endian bytes, Zstandard level 1, CRC32C,
  fill value zero, and writing of all-fill chunks.
- Made missing chunks fail closed on Python 3.11 by checking the configured
  standard Zarr v3 chunk key before decoding. Added sequential idempotent retry
  and conflict checks while reserving concurrent and generation-level
  guarantees for the next closure step.
- Extended versioned benchmark evidence with store layout, codec, missing/fill,
  object-count, footprint, concurrency, and atomicity fields.
- Added and accepted ADR-007 with a tiered decision: continue qualifying Zarr
  for distributed planes, but retain lower-overhead NumPy/direct paths until
  measured crossovers justify using it.

**Evidence**

- Twenty-two focused Zarr unit and integration tests cover serialization,
  initialization, aligned and edge writes, NaNs, all-fill chunks, missing and
  corrupt chunks, content disagreement, normal and conflicting retries,
  invalid values, changed metadata/policy, and shifted-origin rejection.
- The reproducible local probe used one warm-up and five measured repetitions
  per store. At 1024² with 256² chunks, complete median time was 0.281 seconds
  for the NumPy oracle and 0.491 seconds for Zarr (1.75 times the oracle); Zarr
  stored 8,041,519 bytes versus 8,390,656 bytes.
- At 3000² with 512² chunks, complete median time was 0.828 seconds for the
  NumPy oracle and 1.177 seconds for Zarr (1.42 times the oracle); Zarr stored
  69,023,524 bytes versus 72,004,608 bytes.
- Both ignored evidence pairs load through Hebog's `BenchmarkEvidence` model.
  Each identifies the exact uncommitted Hebog source tree and benchmark runner
  by SHA-256 in addition to package and dependency versions.
  These are exploratory local component results and support no distributed or
  end-to-end speed claim.

**Next**

- Add the exact expected-chunk completion manifest and deterministic tests for
  duplicate, mixed-run, interrupted, and concurrently conflicting records.
- Compare uncompressed plus CRC32C and faster codec choices by product role.
- Run direct-FITS, Dask, and deployment-representative store comparisons across
  affected size anchors before selecting a default crossover or removing the
  NumPy oracle.

## 2026-07-31 — Simplified intermediate storage to Zarr only

**Plan phase:** Phase 1

**Completed**

- Amended ADR-007 to make Zarr v3 the sole intermediate image-plane backend
  for every execution tier. FITS remains an input and final compatibility
  format, not an alternative intermediate store.
- Accepted the measured small/local Zarr overhead as a deliberate simplicity
  trade-off. Future performance work will tune Zarr initialization, codecs,
  concurrency, ingestion, and materialisation rather than maintain a
  size-based backend switch.
- Removed the private NumPy-file sink, its duplicate integration suite, and the
  exploratory backend-comparison runner.
- Consolidated `ProductChunk` and the product-chunk error hierarchy around the
  Zarr implementation, removing the redundant Zarr-specific record and the
  unused generic product-sink protocol.
- Updated the implementation plan, contributor instructions, architecture and
  performance guidance, how-to documentation, and benchmark guidance to
  prevent an alternate intermediate backend from being reintroduced without
  an explicit ADR amendment.

**Evidence**

- Followed a red-green cycle for the consolidated `ProductChunk` contract; the
  focused unit and Zarr integration suite passes with 21 tests.
- `just check` passes Ruff formatting and linting, Pyright, doctests, and 149
  fast tests with four expected failures.
- `just coverage` passes 191 unit and integration tests with four expected
  failures and 90.29% branch-aware project coverage. The consolidated product
  model and Zarr implementation each have 100% coverage.
- `just docs-build` and `just package-smoke-test` pass.

**Next**

- Define the exact expected-chunk completion manifest and deterministic tests
  for duplicate, mixed-run, interrupted, and concurrent-conflict records.
- Benchmark and tune Zarr codecs, store configuration, concurrency, FITS
  ingestion, and final materialisation across the affected size anchors.

## 2026-08-01 — Adopted Zarr 3.2 and Python 3.12

**Plan phase:** Phase 1

**Completed**

- Raised Hebog's minimum Python version from 3.11 to 3.12 and removed Python
  3.11 from the portable CI matrix. Python 3.12, 3.13, and 3.14 remain
  supported on Linux, macOS, and Windows.
- Updated the runtime dependency to `zarr>=3.2,<3.3`; the lockfile resolves
  Zarr 3.2.1 and no longer contains Python 3.11-only dependency branches or
  wheels.
- Replaced Hebog's explicit Zarr v3 chunk-key existence checks with Zarr 3.2's
  native `read_missing_chunks=False` configuration and translated
  `ChunkNotFoundError` at the existing Hebog error boundary.
- Updated ADR-007, the implementation plan, contributor instructions, setup
  guidance, native-code packaging assessment, how-to documentation, and issue
  template. The migration guidance directs Python 3.11 users to remain on
  Hebog 0.2.x or upgrade Python before the next release.

**Evidence**

- The Zarr 3.2 dependency contract was introduced as a failing test against
  Zarr 3.1.6, then made green with the dependency and implementation update.
- All 15 focused Zarr integration tests pass and verify that a missing chunk is
  reported through a native Zarr `ChunkNotFoundError` cause.
- `just check` passes Ruff, Pyright targeting Python 3.12, doctests, and 149
  fast tests with four expected failures.
- `just coverage` passes 192 unit and integration tests with four expected
  failures and 90.26% branch-aware project coverage. `hebog.io.zarr` retains
  100% coverage.
- An isolated Python 3.12.12 environment passes 164 unit and Zarr integration
  tests. The strict documentation build and isolated package smoke test pass;
  the installed wheel resolves Zarr 3.2.1.

**Next**

- Let the portable CI matrix confirm Python 3.12 through 3.14 on Linux, macOS,
  and Windows after human review and push.
- Continue with the Zarr completion-manifest and recovery slice in Phase 1.

## 2026-08-01 — Published exact Zarr product generations

**Plan phase:** Phase 1

**Completed**

- Bound every `ProductChunk` to one generation and raised the internal product
  storage schema to version 2. Unpublished development stores created with
  schema version 1 must be recreated; no released Hebog product used it.
- Added the versioned, canonical `ProductGenerationManifest`. It accepts only
  the exact product-by-tile chunk set for one partition and rejects missing,
  duplicate, conflicting, mixed-generation, unexpected, wrong-owner, and
  inconsistent-dtype records.
- Made `ZarrProductSink` validate every referenced chunk before conditionally
  creating a completion marker through the Zarr Store API. An identical
  publication retry is idempotent and a different marker cannot replace the
  winner.
- Kept interrupted work unpublished and resumable from its missing chunks.
  Consumers revalidate the canonical marker and all chunks before treating a
  generation as consumable.
- Completed the Phase 1 `LocalStore` recovery and completion-manifest plan
  item. Deployment-store conditional-create and concurrency guarantees remain
  a separate qualification gate and are not inferred from local evidence.

**Evidence**

- Followed a red-green cycle: the new generation contracts initially failed
  to import before the implementation existed, then all 38 focused product
  model and Zarr integration tests passed.
- `just coverage` passes 208 unit and integration tests with four expected
  failures and 90.96% branch-aware project coverage. The generation model,
  product model, and Zarr implementation each have 100% coverage.
- `just check` passes Ruff formatting and linting, Pyright, doctests, and 159
  fast tests with four expected failures. The strict documentation build and
  isolated package smoke test pass.
- No storage performance or distributed-atomicity claim is made by this
  correctness slice.

**Next**

- Define the versioned internal catalogue and materialised-result schemas from
  failing round-trip and boundary tests.
- Benchmark deployment-representative Zarr stores and prove their atomic or
  conditional completion semantics before distributed qualification.

## 2026-08-01 — Defined internal catalogue and result schemas

**Plan phase:** Phase 1

**Completed**

- Added catalogue schema version 1 with distinct `Island`,
  `SourceCandidate`, and `GaussianComponent` identities and nested position,
  flux, shape, and spectral records. The schema uses pipeline-neutral names
  and keeps PyBDSF/Rapthor column names at the compatibility boundary.
- Made ICRS coordinates, position epoch, degrees, Jy, Jy/beam, reference
  frequency, the spectral convention, and null representation explicit. The
  initial schema is MFS-only and rejects mixed reference frequencies.
- Added canonical ordering, unique IDs, source-component-island referential
  integrity, deterministic JSON, and a valid zero-row catalogue without a
  dummy scientific source.
- Replaced the path-only `SourceFinderResult` version 1 scaffold with result
  schema version 2 and concrete `MaterializedProduct` records. Each product
  carries a role, media type, content schema, byte count, SHA-256, and
  scientific status; existing path properties remain available to consumers.
- Allowed only RMS to be scientifically unavailable in a successful core
  result, so an all-blank image cannot silently relabel copied input pixels as
  an RMS estimate.
- Updated ADR-006, the target architecture, Phase 1 checklist, domain
  glossary, API index, and a new internal-schema reference. The schemas remain
  provisional pending the recorded Phase 0 human scientific sign-off.

**Evidence**

- Followed two red-green cycles: catalogue and materialised-result tests first
  failed to import their absent models, then all 84 focused schema and public
  data-model tests passed.
- `just coverage` passes 257 unit and integration tests with four expected
  failures and 92.12% branch-aware project coverage. The new catalogue module
  and changed source-finding result module each have 100% coverage.
- `just check` passes Ruff formatting and linting, Pyright, doctests, and 208
  fast tests with four expected failures. The strict documentation build and
  isolated package smoke test pass. All five frozen equivalence tests pass.
- This slice defines logical records and restart metadata; it makes no claim
  that FITS compatibility materialisation or large catalogue-shard storage is
  complete.

**Next**

- Add failing Astropy-backed round-trip and boundary tests for valid and empty
  catalogue, RMS, mask, and diagnostics products, including corrupt and
  unsupported inputs, then implement their bounded compatibility I/O.
- Map the reviewed Rapthor/PyBDSF catalogue view separately from the internal
  schema and keep dummy rows or placeholder RMS behaviour adapter-only.

## 2026-08-01 — Materialised versioned final products

**Plan phase:** Phase 1

**Completed**

- Added the strict `SourceFindingDiagnostics` schema version 1 with canonical
  JSON and the same source, Gaussian-component, island, and RMS-status
  consistency rules as the materialised result.
- Added Astropy-backed internal catalogue FITS schema version 1 with separate
  island, source, and Gaussian-component tables, explicit units, stable
  identities, variable-length spectral coefficients, reversible nullable
  values, and structurally complete zero-row tables.
- Added incremental RMS and source-filtering-mask FITS writers. They consume
  sequential full-width row blocks, preserve an explicit float32 or float64
  RMS dtype and NaNs, encode exact boolean masks as uint8, and reject partial,
  cast, negative, infinite, non-binary, or scientifically inconsistent data.
- Added checksum-aware bounded product reads and `MaterializedProduct`
  construction. Complete same-directory temporary files are validated before
  publication; identical sequential retries are idempotent and different
  existing bytes fail closed.
- Removed a whole-plane validation read found during review. Streamed writers
  retain their per-block scientific checks, publication validates structural
  metadata, and a restart reader verifies SHA-256 once before validating only
  requested windows.
- Kept internal FITS names and empty-catalogue semantics independent of the
  future Rapthor/PyBDSF compatibility mapping. Updated ADR-006, the internal
  schema reference, and the completed Phase 1 I/O checklist items.

**Evidence**

- Followed the red-green-refactor cycle: the product contracts first failed
  on the absent diagnostics and I/O APIs; review regressions then exposed
  missing unit, record-identity, schema, and unavailable-RMS checks. The
  resulting focused data-model and integration suite passes all 94 tests.
- `just coverage` passes 303 tests with four expected failures and 92.75%
  branch-aware project coverage. The changed source-finding model has 100%
  coverage and the new materialisation module has 96% coverage.
- `just check` passes Ruff formatting and linting, Pyright, doctests, and 213
  fast tests with four expected failures. The strict documentation build and
  isolated wheel/sdist smoke test pass. All five frozen equivalence tests pass.
- No runtime, deployment-store concurrency, or Rapthor compatibility claim is
  made by this correctness slice.

**Next**

- Benchmark Zarr stores, FITS ingestion, and final materialisation at affected
  size and execution-crossover anchors; measure peak memory and avoidable
  full-image copies before tuning.
- Implement the reviewed Rapthor/PyBDSF catalogue and side-product mapping at
  the compatibility boundary without changing the internal schema.

## 2026-08-01 — Fixed deterministic source ownership

**Plan phase:** Phase 1

**Completed**

- Defined source ownership from one finite zero-based continuous `(y, x)`
  reference position and the partition manifest's half-open tile cores.
- Assigned exact internal-boundary ties to the core that begins at the
  boundary. Halo overlap, source extent, worker count, and completion order do
  not affect catalogue ownership.
- Added constant-time ownership lookup for regular and shifted partition
  origins, with explicit rejection of non-finite and out-of-image positions.
- Updated the domain glossary, large-image domain model, and Phase 1 checklist.

**Evidence**

- The new contracts failed on the absent ownership API before implementation.
- All 29 partition tests pass, including every edge and corner, shifted-grid
  boundaries, representative subpixel positions, and invalid coordinates.

**Next**

- Stream validated completed Zarr generations into bounded final-product row
  blocks and measure one-tile and many-tile materialisation overhead.

## 2026-08-01 — Streamed completed Zarr products to FITS

**Plan phase:** Phase 1

**Completed**

- Added a completed-generation row iterator that reads and checksum-validates
  every product chunk exactly once in canonical tile-row order.
- Bounded many-tile assembly to one full-width tile row plus the current
  decoded chunk and required the caller to provide an explicit byte budget.
- Made one-tile materialisation yield the already owned validated chunk
  directly, avoiding a redundant full-image assembly copy and any Dask fanout.
- Proved the same public RMS and mask writers consume both one-tile and
  many-tile Zarr generations and emit identical final FITS values, NaNs,
  validity masks, units, and dtypes.

**Evidence**

- The row-stream contracts failed on the absent API before implementation.
- All 67 affected Zarr, final-product, and materialisation integration tests
  pass. Ruff and Pyright pass for every changed module and test.
- The memory contract is structural rather than a wall-time claim: each
  yielded block reports `nbytes` within the admitted budget, no iterator path
  constructs an image-height output array, and a too-small budget fails
  closed.

**Next**

- Run reproducible local FITS-to-Zarr-to-FITS measurements across Phase 1
  anchors, record peak RSS and storage bytes, and use the evidence to decide
  whether codec or initialization tuning is justified.

## 2026-08-01 — Added reproducible Phase 1 I/O measurements

**Plan phase:** Phase 1

**Completed**

- Added a platform-portable benchmark runner for the implemented warm local
  FITS-to-Zarr-to-final-FITS path, with deterministic analytic inputs, one
  warm-up, at least five measurements, and versioned machine-readable evidence.
- Recorded ingestion and materialisation timings separately, alongside peak
  process RSS, Zarr object and byte counts, chunk geometry, codec policy,
  internal concurrency, dependency identity, and the exact Hebog commit.
- Made unavailable allocation counters explicit and tied the measurable memory
  claim to the structural bounded-row contract instead of fabricating zeroes.
- Added focused tests for both one-tile and many-tile runs and for the portable
  current-RSS sampler, which avoids the POSIX-only `resource` module.

**Evidence**

- All four benchmark-entry-point tests pass, including execution of the real
  bounded FITS/Zarr path on a small deterministic image.
- Ruff and Pyright pass for the runner and its tests.
- Measured anchor results are intentionally deferred until this harness is in
  Git so every evidence record identifies the commit that produced it.

**Next**

- Run the committed harness across one-tile and many-tile local anchors, record
  the exploratory results, and use them to close or refine the Phase 1 local
  I/O gates without claiming deployment-store or distributed qualification.

## 2026-08-01 — Completed Phase 1 technical and release qualification

**Plan phase:** Phase 1

**Completed**

- Ran the committed warm local FITS-to-Zarr-to-FITS harness at 256, 512,
  1,024, and 3,000 pixels per side with one warm-up and five measured
  repetitions, 512-by-512 chunks, and Zarr concurrency 10.
- Recorded median complete times of 0.226, 0.249, 0.440, and 2.519 seconds.
  Peak sampled process RSS was 138.1, 164.2, 269.1, and 578.1 MiB. Raw
  versioned evidence remains under the ignored `benchmark-results/` tree.
- Compared concurrency 1 and 10 at the 256 and 3,000 endpoints. The observed
  median differences were only about 2.4% and 1.3%, so no dynamic concurrency,
  codec, sharding, or additional-backend complexity was introduced.
- Closed the Phase 1 local I/O, one-tile, and Hebog-controlled-copy gates.
  Moved deployment-store atomicity, concurrency, cold/warm throughput, and
  failure recovery to the later distributed qualification work where the real
  store and topology are available.
- Added a Phase 1 release-readiness record that explicitly limits the next
  experimental release: the source-finding pipeline remains unimplemented,
  and the current equivalence lane compares PyBDSF release with PyBDSF master,
  not Hebog with either.
- Refined human scientific review to approve the equivalence definition,
  dataset fitness, defaults, terminology, and intentional deviations rather
  than manually verifying every output. Phase 2 TDD may start against the
  frozen provisional profile; sign-off remains mandatory before scientific
  stability, equivalence, or Rapthor-cutover claims.

**Evidence**

- All recorded I/O campaigns identify Hebog commit
  `39bd5397d84fe0150472adfb28ce7e66b2937fd2`, the deterministic input
  checksum, dependency and environment identities, storage policy, and every
  repetition.
- One-tile runs use one Zarr chunk per product and no final assembly copy.
  Many-tile final assembly is structurally bounded to one full-width tile row
  plus the current decoded chunk; complete third-party allocation counts
  remain explicitly unavailable.
- The measurements are exploratory local evidence, not a PyBDSF performance
  comparison or deployment-store, cold-cache, Dask, or scaling qualification.
- The release handoff passes 323 portable unit/contract/integration tests with
  four strict expected failures and 92.84% branch-aware coverage. All five
  small equivalence checks pass; all seven future acceptance scenarios remain
  strict expected failures assigned to their implementation phases.
- Ruff, Pyright, all pre-commit hooks, strict Marimo and MkDocs validation, and
  the isolated source-distribution-to-wheel smoke test pass. The configured
  Linux/macOS/Windows CI matrix and controlled qualification/scalability lanes
  were not run on this local host.

**Next**

- Begin Phase 2 with failing analytic and property tests for deterministic
  serial background and RMS estimation, then compare implemented Hebog RMS
  products with both frozen PyBDSF references.
- Obtain the named scientific sign-off as early as practical to reduce rework,
  and in all cases before stabilizing scientific defaults or compatibility
  semantics or claiming scientific equivalence.

## 2026-08-01 — Removed the pre-production compatibility guarantee

**Plan phase:** Cross-cutting development policy

**Decision**

- Hebog does not require backward compatibility between `0.x` releases while
  it remains under active pre-production development.
- Agents and contributors should prefer the cleanest current design and may
  change or remove obsolete Hebog APIs, schemas, development stores, and
  configuration directly. Compatibility shims, deprecation periods, legacy
  readers, migrations, and old-contract tests are not required by default.
- User-visible breaking changes remain explicit in current documentation,
  Conventional Commits, and release notes, and stale artifacts must fail
  clearly rather than be silently reinterpreted.
- Migration support becomes a requirement only when explicitly requested for
  a particular interface. This policy does not weaken the PyBDSF/Rapthor
  compatibility goal, scientific reproducibility, or the current supported
  platform matrix.

**Next**

- Apply this policy to Phase 2 and later design decisions without carrying
  speculative compatibility code for unreleased Hebog contracts.

## 2026-08-01 — Made catalogue FITS retries deterministic on Windows

**Plan phase:** Phase 1 release fix

**Completed**

- Reproduced the failed idempotency contract as a red test against the
  heap-backed `PD()` spectral-coefficient column.
- Replaced variable-length FITS heap arrays with the smallest fixed-width
  float64 vector required by each source or Gaussian-component table. Empty
  and shorter coefficient tuples use canonical trailing NaN padding.
- Found and removed a second source of byte variance: Astropy's default FITS
  checksum comments included the current wall-clock time. Catalogue HDUs now
  use a fixed checksum provenance comment while retaining valid `CHECKSUM` and
  `DATASUM` cards.
- Kept raw-byte conflict detection strict instead of accepting arbitrary
  semantically equal files. Readers now reject heap-backed coefficient columns,
  infinity, and non-trailing padding.

**Evidence**

- All 44 catalogue and image-product materialisation integration tests pass,
  including repeated catalogue publication, mixed empty/two-coefficient
  spectra, zero-row catalogues, invalid padding, and conflicting science.
- Thirty independently materialised copies of the mixed-spectra catalogue
  produced one SHA-256 digest after checksum-comment normalization; the
  regression also verifies every FITS checksum and data checksum.

**Next**

- Confirm the regression on the Python 3.12–3.14 Windows CI matrix; no
  Windows-specific application code or conditional behaviour is required.

## 2026-08-01 — Started Phase 2 window statistics

**Plan phase:** Phase 2, robust background and RMS estimation

**Completed**

- Added an explicit immutable sigma-clipping policy for bounded RMS windows.
- Added a pure, vectorised serial oracle that estimates background and RMS for
  a batch of independent two-dimensional windows through Astropy's established
  sigma-clipping implementation. The kernel creates no scheduler, performs no
  I/O, and contains no Python loop over pixels or windows.
- Made valid and retained sample counts explicit. Non-finite and masked pixels
  do not contribute; sparse windows return read-only NaN estimates with an
  explicit unavailable flag so later interpolation can apply a reviewed
  fallback without mistaking missing data for zero noise.

**Evidence**

- Seventeen analytic, property, configuration, and boundary tests pass for
  known symmetric noise, constant and negative backgrounds, bright outliers,
  masks, NaNs, positive affine transforms, sparse windows, aligned batches,
  and immutable result arrays.
- The portable coverage lane passes 344 tests with four strict expected
  failures at 93.02% branch-aware project coverage. Both new production files
  have 100% statement and branch coverage, and all five frozen equivalence
  checks remain green before the new kernel is integrated into a pipeline.

**Next**

- Define deterministic coarse-grid window centres and clipped edge geometry
  with analytic affine-background tests, then apply the window oracle in
  bounded batches before implementing interpolation.

## 2026-08-01 — Completed Phase 2 background and RMS estimation

**Plan phase:** Phase 2

**Completed**

- Applied the vectorised sigma-clipping oracle to deterministic globally
  anchored, edge-aligned coarse windows in bounded rectangular batches.
- Added cached sparse-cell fallback and affine-preserving SciPy interpolation,
  with tile-local bracketing summaries rather than complete image planes.
- Added local adaptive fine grids around explicit bright candidates. Overlap
  merges deterministically, while distant candidates retain separate bounded
  regions so summary memory scales with affected area rather than image area.
- Proved serial/Dask, one-/many-tile, shifted-origin, task-order, and retry
  invariance, and explicit behaviour for masks, NaNs, edges, negative values,
  zero RMS, insufficient samples, and all-invalid data.
- Added a portable frozen-input equivalence test and a versioned Phase 2
  benchmark runner. The runner keeps client startup outside the measurement,
  records one warm-up and five repetitions, and does not assemble a complete
  output plane.
- Accepted common WSClean `JY/BEAM` and `JYBEAM-1` FITS unit aliases while
  retaining strict Astropy validation for all other input units.

**Scientific evidence**

- On the exact 256-by-256 frozen generated input, Hebog's RMS map differs from
  both released PyBDSF 1.14.1 and pinned master by 1.575% at the median and
  95th percentile, below the 2% and 5% gates.
- On the 8,980,478 pixels outside the frozen source-filter mask in each
  representative Rapthor image, median and 95th-percentile RMS differences
  were 1.437% and 4.279% for true sky and 1.418% and 4.278% for flat noise.
  Released and master reference maps were identical for these comparisons.
- Representative Hebog RMS array SHA-256 values were
  `61491cbca860356798844a9b75bef7f72f4d1ac2a6dd50a236b557814e142a19`
  for true sky and
  `c66f747eeb5aef999f282c88f7ebc357e68c1fb3c1161b9709379fc76aa2cb61`
  for flat noise. Validation arrays remain outside Git.

**Performance evidence**

- Controlled 3,000-by-3,000 runs used the representative Phase 0 inputs, a
  reused four-worker/one-thread local Dask client, 150/50 RMS geometry,
  64-cell batches, 1,500-pixel output tiles, float64, one warm-up, and five
  measured repetitions.
- True-sky median wall time was 2.471 seconds (range 2.397–2.553), passing the
  4-second budget. Flat-noise median wall time was 2.527 seconds (range
  2.463–2.541), passing the 3-second budget.
- Maximum sampled Hebog process RSS was 974,192,640 bytes, below the
  approximately 1.30 GB Phase 0 PyBDSF observations. Instrumentation differs:
  PyBDSF recorded the largest parent or child, while the in-process Hebog
  client and workers share one process. This supports the non-regression gate,
  not an aggregate multi-node memory claim.
- Raw exploratory evidence remains under ignored
  `benchmark-results/phase-2/`. The committed release-readiness record contains
  the scope, reproduction command, compact results, and limitations.
- The release handoff passes 387 portable unit, contract, and integration
  tests with four strict expected failures and 92.96% branch-aware coverage.
  All ten portable equivalence tests pass; all seven future acceptance
  scenarios remain strict expected failures. Ruff, Pyright, strict docs,
  pre-commit, and isolated source-distribution-to-wheel validation pass.

**Decisions and deviations**

- Retain NumPy, SciPy, and Astropy. The vectorised implementation meets the
  scientific, latency, and memory gates, so Numba, Rust, and C++ do not meet
  the project's additional-complexity decision gate.
- Retain float64 until a lower-precision implementation passes the same
  scientific suite. Treat batch and output-tile sizes as measured execution
  policy, not scientific geometry.
- Defer automatic bright-candidate discovery to the thresholding/integration
  work and multi-level coarse-summary reduction to the distributed graph and
  scale gate. Current tile requests receive only bounded local summaries and
  never a complete image plane.

**Next**

- Begin Phase 3 with failing analytic and generated-truth tests for threshold
  monotonicity, stable connected islands, blends, edges, and empty detections.
- Derive automatic high-significance bright-candidate positions from the
  coarse result without recomputing coarse statistics, then connect owned RMS
  tiles to the Phase 1 Zarr persistence contract.
- Obtain the named scientific review before stabilizing the compatibility
  defaults or claiming complete PyBDSF equivalence.

## 2026-08-01 — Prepared the Phase 3 delivery sequence

**Plan phase:** Phase 3, thresholding, connected islands, and compact
deblending

**Reviewed**

- Traced the completed Phase 2 stage, current partition/executor contracts,
  frozen dataset matrix, comparison oracle, Phase 2 release evidence, and the
  Rapthor `gec-468-ai-migrate-to-prefect` source-finding boundary.
- Confirmed that the current released/master PyBDSF reference uses
  eight-neighbour SciPy labelling, includes pixels at the island threshold,
  requires a peak strictly above the detection threshold, and normally derives
  a minimum island size from one third of the beam area with a six-pixel floor.
  These remain compatibility observations subject to Hebog's independent
  scientific review, not implementation code to copy or automatic truth.
- Identified that the existing comparison oracle reports a mask pixel
  confusion matrix but cannot yet expose island matches, splits, or merges;
  overall mask accuracy would also be dominated by background pixels.
- Identified that detection-threshold and island-threshold monotonicity need
  separate contracts: an island mask can only shrink as its threshold rises,
  but that shrinkage may legitimately split one connected label.

**Decisions**

- Reordered Phase 3 into seven independently reviewable TDD slices: freeze
  contracts and fixtures; bounded two-threshold detection; adaptive candidate
  discovery and RMS persistence; one-tile connected islands; hierarchical
  reconciliation; compact deblending; and scientific/performance
  qualification.
- Keep detection-stage seeds and deblended regions distinct from measured
  islands, Gaussian components, and grouped sources. Phase 3 does not populate
  measurement fields with placeholders or claim catalogue equivalence.
- Use mature SciPy connected-component and reduction primitives first. Assess
  scikit-image only if a deblending comparison demonstrates enough scientific
  or maintenance value to justify another runtime dependency.
- Require object-level mask comparison, canonical global island identity,
  side and diagonal corner reconciliation, Zarr-owned mask/RMS chunks, and a
  source-density benchmark that rejects all-pairs or quadratic paths.
- Keep Phase 0 human review off the critical path for initial analytic TDD,
  but require it before Phase 3 scientific promotion, compatibility-default
  stabilization, or a `0.5.x` equivalence claim.

**Next**

- Start Phase 3 slice 1 by adding failing tests for the independent island
  comparison report and freezing the exact threshold/connectivity/size
  semantics and Phase 3 development, regression, and held-out cases.
- Add the reviewed mask and island-object non-inferiority margins to Section 5
  before using either PyBDSF reference to tune segmentation.

## 2026-08-01 — Started Phase 3 segmentation comparison

**Plan phase:** Phase 3, slice 1

**Completed**

- Added intersection over union to the independent boolean-mask comparison so
  background-dominated accuracy cannot stand in for source-mask overlap.
- Added an overlap-based integer-label comparison that is independent of
  numeric label identity. It reports object completeness and reliability,
  unmatched regions, reference splits, candidate merges, and per-match
  intersection over union after applying an optional valid-pixel mask.
- Kept assignment memory local to connected components of the sparse overlap
  graph rather than allocating one global all-pairs object matrix.

**Evidence**

- Twenty-four focused analytic comparison tests pass, including relabelled
  identical regions, splits, merges, invalid labels, valid-region exclusion,
  and empty segmentations.
- The branch-aware coverage lane passes 394 tests with four planned strict
  expected failures at 93.15% total coverage.

**Next**

- Freeze the remaining threshold, connectivity, island-size, and dataset
  contracts, then implement the pure bounded two-threshold serial kernel.

## 2026-08-01 — Added bounded two-threshold detection

**Plan phase:** Phase 3, slices 1 and 2

**Completed**

- Added immutable Phase 3 development, regression, and held-out qualification
  manifest supplements without changing the frozen Phase 0 entries.
- Made the minimum island size required scientific configuration and retained
  an explicit optional maximum. The Rapthor boundary can derive a reviewed
  beam-dependent value later; the scientific kernel receives an integer and
  has no workflow default.
- Added a pure vectorised float64 tile kernel that applies inclusive island
  membership and strict detection-seed thresholds without persisting a
  normalized image plane. Non-finite values, masks, and non-positive RMS are
  excluded before thresholding.
- Fixed compact detection to eight-neighbour connectivity in the documented
  contract rather than adding an unused connectivity option.

**Evidence**

- Thirty-one focused configuration and detection tests pass for exact
  threshold boundaries, positive affine transforms, distinct monotonicity,
  negative emission, masks, non-finite values, non-positive RMS, array
  validation, immutable outputs, and island-size configuration.
- The normal handoff suite passes 312 fast tests with four planned strict
  expected failures, Ruff, and Pyright.

**Next**

- Implement automatic high-significance candidate discovery against cached
  coarse background/RMS summaries, then persist owned RMS tiles through the
  Zarr generation contract.

## 2026-08-01 — Added deterministic connected islands

**Plan phase:** Phase 3, slices 4 and 5

**Completed**

- Added a SciPy-based eight-connected one-tile oracle that reduces pixel
  count, global bounds, maximum SNR with deterministic equal-peak ties,
  lexicographically first member, seed presence, and image-edge contact
  without copying the image for each island.
- Added vectorized boundary-label comparisons across tile sides, diagonal
  offsets, and four-tile corners. A small union-find merges only label
  equivalences and aggregates island facts before applying global seed and
  size cuts.
- Assigned accepted island IDs from canonical global first-pixel order rather
  than SciPy label numbers, partition shape, or result completion order.
- Kept detection-stage records separate from the measured catalogue `Island`
  schema and produced compact per-tile local-to-global mappings for later Zarr
  mask publication.

**Evidence**

- Six analytic island tests pass for eight-connectivity, side and four-tile
  corner reconciliation, global minimum/maximum size cuts, strict seed
  acceptance, empty detection, shifted origins, three tile geometries, and
  reversed result order.
- Branch-aware coverage passes 422 tests with four planned strict expected
  failures at 93.29% total coverage. Detection is fully covered; local
  labelling and reconciliation have 95% and 94% branch-aware coverage.

**Next**

- Move tile label planes behind the Zarr boundary so executor results contain
  summaries rather than image cores, and implement hierarchical reduction of
  boundary equivalences before automatic bright-candidate discovery.

## 2026-08-01 — Published bounded compact-detection products

**Plan phase:** Phase 3, slices 3 and 5

**Completed**

- Added an explicit strict high-significance threshold to adaptive RMS
  configuration and discovered one deterministic peak per reconciled bright
  component against cached coarse background/RMS interpolation.
- Split sparse adaptive refinement from initial coarse estimation so candidate
  discovery reuses the exact prepared coarse cache and cannot stack duplicate
  fine regions on retry.
- Reduced local island summaries and boundary equivalences through a
  deterministic pairwise tree. Executor results contain component facts and
  boundary vectors, never normalized planes or label cores.
- Added a scheduler-independent compact-detection stage that writes owned
  float64 background/RMS chunks, reconciles global acceptance, recreates one
  bounded local label core, and writes an accepted boolean mask chunk. The
  immutable generation contains `background`, `rms`, and
  `source-filtering-mask` products.
- Retained the separate candidate scan and label recreation because they keep
  the implementation and restart contract simple. Each adds one explicit
  bounded image-tile read; a persisted diagnostic label plane is not required
  for correctness.

**Evidence**

- Fifty-three focused unit, integration, and compact-reference tests pass for
  strict candidate thresholds, cache reuse, side/corner reconciliation,
  hierarchical reduction, one/many-tile equivalence, identical retries,
  exact Zarr generation products, and serial/Dask conformance.
- Ruff and Pyright pass. The existing Phase 1 Zarr contract continues to
  reject missing, corrupt, conflicting, incomplete, and noncanonical chunks
  and generation markers.
- Branch-aware coverage passes 432 tests with four planned strict expected
  failures at 93.26% total coverage; the compact-detection stage is at 91%.

**Next**

- Freeze analytic compact-deblending behaviour and implement the simplest
  bounded SciPy approach that passes close-pair, saddle, edge, and partition
  tests.

## 2026-08-01 — Added bounded compact deblending

**Plan phase:** Phase 3, slice 6

**Completed**

- Defined Phase 3 deblending output as deterministic sub-island regions for
  later measurement, not sources, Gaussian components, or catalogue rows.
- Selected an eight-connected marker-distance watershed using SciPy maximum
  filters, connected labelling, Euclidean distance, image-forest watershed,
  and vectorized reductions. Sparse actual-intensity saddle comparisons merge
  weak basins below an explicit prominence cut.
- Collapsed equal-valued peak plateaus and resolved equal peak/ownership ties
  by lexicographic global position. Region identities follow canonical first
  member order rather than marker or task order.
- Added deterministic cost-bounded multi-island batches. Member-heavy or
  spatially extended bounds remain explicit deferred records for the Phase 5
  partitioned/multiscale path.
- Did not add scikit-image or native code because SciPy supplies the complete
  bounded contract. A repeated multilevel implementation would add level and
  cross-level identity policy without improving the tested compact cases.

**Evidence**

- Twenty-five focused tests pass for configuration boundaries, single peaks,
  deep and shallow saddles, close and equal peaks, sub-threshold noise,
  plateau and mask holes, global edge coordinates, batching, explicit
  deferrals, invalid inputs, and one/many-tile stage invariance.
- Ruff and Pyright pass. The deblending kernel contains no Python loop over
  image pixels and no all-pairs source or region matrix.
- Branch-aware coverage passes 452 tests with four planned strict expected
  failures at 93.44% total coverage; deblending is at 96%.

**Next**

- Add generated-truth and dual-reference detection reports, benchmark the
  complete Phase 3 path across the frozen size/density matrix, and publish the
  release-readiness record.

## 2026-08-01 — Qualified Phase 3 compact detection

**Plan phase:** Phase 3, slice 7 and closure

**Completed**

- Froze foreground-sensitive mask and connected-object gates before inspecting
  the held-out result. Added Wilson confidence intervals and population
  aggregation without using background-dominated pixel accuracy.
- Added exact released/master PyBDSF comparisons on the redistributable compact
  input and an environment-resolved controlled comparison on the exact
  checksum-governed Rapthor image.
- Added bounded compact-deblend orchestration that reads only admitted island
  windows and returns summaries rather than pixel labels through executors.
- Added one-open batched FITS reads and a four-chunk checksum-validating Zarr
  LRU. The 512-square 64-island density probe fell from 2.014 seconds to 0.699
  seconds, removing a complete-chunk read per island.
- Corrected masked watershed pixels to be maximum-cost barriers instead of
  competing negative markers. The density matrix exposed the failure before
  closure; an analytic regression now covers multiple peaks around a hole.
- Profiled product persistence and adopted the ADR-007 product-role codec
  seam: numeric planes use little-endian bytes plus CRC32C without Zstandard,
  while boolean masks retain Zstandard level 1 plus CRC32C. Internal storage
  schema version 3 deliberately invalidates unreleased development stores.
- Added reproducible exact-representative and generated size/density benchmark
  runners. Small tiers use a one-tile serial plan; the 3,000-square tier uses
  nine 1,000-square tiles on a caller-owned four-worker Dask client.
- Published the Phase 3 release-readiness record and updated the plan. The
  inclusive Phase 3 component budget is 3.5 seconds because it now owns
  durable background/RMS/mask publication; the later output budget was
  reduced by the same second, leaving the complete budget unchanged.

**Scientific evidence**

- Compact Hebog versus both PyBDSF references: mask precision and recall
  0.9944, IoU 0.9888, all three objects matched, median/minimum object IoU
  0.9928/0.9655.
- Generated development and regression mask IoUs were 0.7778 and 0.8623; all
  eight strong-signal objects matched with no splits or merges. The aggregate
  95% Wilson lower bound for eight of eight recovered objects was 0.6756.
- The held-out qualification gate passed without changing its frozen margins:
  mask precision 0.8735, recall 0.9603, IoU 0.8430, and all four strong-signal
  objects matched with median/minimum IoU 0.8767/0.8056. One exact-threshold
  noise crossing remains report-only as planned.
- On the exact Rapthor products Hebog's seven compact islands all matched both
  references with reliability 1.0, median/minimum IoU 0.9470/0.7718, and no
  split or merge. Five PyBDSF `atrous_do=true` objects remain explicit Phase 5
  multiscale work. Released/master PyBDSF masks differed by 44 pixels but
  matched all twelve objects.

**Performance evidence**

- Final generated medians for sparse/normal/dense workloads were
  0.313/0.325/0.332 seconds at 256 square, 0.352/0.402/0.378 seconds at 512,
  0.699/0.696/0.736 seconds at 1,024, and 2.848/2.963/3.489 seconds at 3,000.
- The 3,000-square dense case contained 2,197 islands and was 23% slower than
  the one-island sparse case; both used 28 tasks. No task-per-island or
  quadratic density path was observed at this tier.
- The exact Rapthor median was 3.193 seconds across five measurements after
  warm-up (3.094–3.301 seconds), with 0.110 seconds median compact deblending,
  44 tasks, and maximum observed process RSS of 2,779,561,984 bytes.
- Raw typed evidence remains in ignored `benchmark-results/phase-3/`; commands
  and scope are documented in the benchmark README and readiness record.

**Validation**

- `just check`: 361 passed, 139 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.
- `just coverage`: 477 passed, 28 deselected, and four expected failures with
  93.83% branch-aware project coverage. The new compact-deblend orchestration
  reached 93% after exercising its pipeline-neutral fallback and fail-closed
  source/generation boundaries.
- `just test-equivalence`: 14 passed. `just test-qualification`: one passed and
  one controlled-data case skipped. The controlled exact Rapthor comparison
  passed all three released/master/reference-divergence checks separately.
- `just test-acceptance`: seven planned later-phase scenarios remained expected
  failures. `just docs-build` completed under MkDocs strict mode.

**Remaining gate**

- Named human scientific review must approve the connectivity, exact threshold
  comparisons, six-pixel minimum, provisional margins, watershed saddle
  semantics, and compact-versus-multiscale boundary. Automated technical
  closure is complete, but scientific sign-off is not claimed.

**Next**

- Obtain and record Phase 3 human scientific approval, then begin Phase 4
  measurement, fitting, and catalogue compatibility from the stable compact
  topology and region summaries.

## 2026-08-02 — Added an executable Phase 3 Marimo demonstration

**Plan phase:** Phase 3 documentation and handoff

**Completed**

- Replaced the placeholder notebook with a self-contained demonstration of
  background/RMS estimation, adaptive candidate discovery, compact detection,
  connected-island reconciliation, Zarr products, and compact deblending.
- Used the checked-in Phase 3 development recipe as the provenance base and
  declared a visual-only variant containing an equal compact pair across a
  four-tile corner. The frozen scientific recipe and qualification evidence
  remain unchanged.
- Compared one-tile and four-tile execution in the notebook. Background, RMS,
  source mask, island summaries, and deblended summaries are identical.
- Added Matplotlib to the development dependency group for established
  scientific array visualization without increasing Hebog's runtime package.
- Updated the README to describe and launch the working demonstration.

**Validation**

- `just marimo-check` passes in strict mode.
- A headless Marimo HTML export executed the complete notebook successfully.
  The rendered result contains five connected islands, six compact regions,
  one visibly deblended two-region island, one adaptive-RMS candidate, no
  deferred islands, and five passing partition-invariance checks.

## 2026-08-02 — Completed named Phase 3 scientific review

**Plan phase:** Phase 0 scientific contract closure and Phase 3 exit gate

**Decision**

- Gemma Danks, Data Processing Software Engineer, approved the scientific
  pre-review amendments and the documented compact Phase 3 decisions as the
  project owner and named ADR decider.
- Approved the community best-practice envelope documented by peer-reviewed
  astronomy literature and source-finder challenges. Cross-pipeline consensus
  is a strong guide, while analytic and injected governed truth remain the
  primary scientific oracles and PyBDSF remains a compatibility oracle.
- Approved the explicit `5.0/3.0` normal and `5.0/4.0` early Rapthor profiles,
  primary-beam terminology, distinct domain objects, scientific empty-product
  semantics, MFS-only initial scope, and low-SNR curve/confidence treatment.
- Approved Phase 3 inclusive-island and strict-seed comparisons,
  eight-neighbour connectivity, the beam-aware six-pixel floor, explicit
  adaptive-RMS profile, compact watershed saddle rules, mask/object margins,
  multiscale deferral, partition invariance, and the inclusive 3.5-second
  component budget.
- The gate contract status changed from `frozen-provisional` to
  `reviewed-provisional`: the margins are human-reviewed for the experimental
  compact `0.x` scope but do not establish catalogue, multiscale, Rapthor, or
  production equivalence.
- Independent domain confirmation remains advisable before production
  cutover. Facility review, later scientific phases, end-to-end acceptance,
  complete performance, and multi-node scalability gates remain open.

**Validation**

- The gate-status contract test failed first for the intended status mismatch,
  then passed after the validated schema and JSON contract were updated.
- `just test-equivalence`: 14 passed.
- `just test-qualification`: one passed and one controlled-data case skipped.
- `just coverage`: 477 passed, 28 deselected, and four expected failures with
  93.83% branch-aware project coverage.
- `just check`: 361 passed, 144 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.
- `just docs-build` passed in strict mode.

## 2026-08-02 — Prepared the Phase 4 delivery plan

**Plan phase:** Phase 4 readiness

**Reviewed**

- Traced the Phase 4 boundary from the implemented Phase 3 compact deblend
  records through the internal catalogue schemas, FITS materialisation,
  comparison oracles, and the fields consumed by Rapthor/LSMTool.
- Checked the proposed measurement work against Condon's Gaussian-fit error
  treatment, the ASKAP/EMU source-finding challenge, Aegean 2.0's
  correlated-noise and uncertainty findings, documented PyBDSF processing,
  and the established Astropy and SciPy capabilities already available to
  Hebog.
- Confirmed that the exact compact released and pinned-master reference
  catalogues are suitable for a strict Phase 4 compatibility case. The
  representative references remain a deliberate divergence case because
  released and master produce different source populations and Phase 5 still
  owns multiscale emission.

**Decisions**

- Replaced the former algorithm checklist with eight ordered TDD slices:
  freeze meanings/data/gates; preserve exact region membership; implement
  moment oracles; select fitting from evidence; transform/deconvolve/calibrate
  errors; associate and shard records; materialise the compatibility view;
  then qualify and prepare the release.
- Identified a required handoff correction: `DeblendedRegion` bounding boxes
  are not exact watershed memberships. Phase 4 will keep bounded label arrays
  worker-local through measurement instead of inferring pixels from boxes,
  rerunning deblending, or transferring label planes through the scheduler.
- Required a fit-all compact reference before any selective moment-only fast
  path, Monte Carlo calibration rather than uncritical trust in formal shape
  errors, and an explicit internal unresolved state instead of PyBDSF's
  compatibility zero sentinel.
- Kept the scientific stage pipeline-neutral and partial results explicit.
  A normal compatibility catalogue and successful complete `find_sources`
  result cannot omit Phase 5 deferrals, while actual Rapthor orchestration and
  filtered-model publication remain Phase 7 work.
- Reused the existing catalogue models, Zarr intermediate boundary, and
  Astropy FITS output. Arrow/Parquet is no longer an open Phase 4 dependency
  question without measured evidence and an ADR amendment.
- Corrected the performance table to apply the previously documented
  one-second transfer from catalogue/output work into Phase 3 durable image
  publication. Phase 4 now has a combined incremental representative budget
  of four seconds: two for measurement/fitting and two for catalogue/output.

**Validation**

- `just check`: 361 passed, 144 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.
- `just docs-build` passed in strict mode.

**Next**

- Start with the versioned Phase 4 scientific contract, development/regression
  supplements, an unseen qualification supplement, comparison-oracle tests,
  and named review of the proposed numerical margins before tuning a
  production fitter.

## 2026-08-02 — Completed automated Phase 4 Step 1 preparation

**Plan phase:** Phase 4, Step 1 — meanings, datasets, gates, and review

**Implemented**

- Added machine-validated, frozen-provisional Phase 4 contracts for compact
  measurement scope, flux and solid-angle meanings, coordinate conventions,
  association, unresolved and unavailable states, fitting evidence order,
  analytic failure cases, role-specific scientific gates, uncertainty
  calibration, and explicit catastrophic-outlier thresholds.
- Extended the independent catalogue oracle TDD-first with fitted and
  deconvolved ellipses, 180-degree position-angle differences, explicit
  resolved/unresolved classification, uncertainty bias/coverage/dispersion,
  component and quality-flag comparisons, self-describing outlier evidence,
  and linear-memory parent-association contingency reports. Association gates
  use co-association precision and recall so unrelated pairs cannot conceal a
  split or merge.
- Added synthetic generator version 2 with partition-invariant affine RMS,
  governed invalid rectangles, rotated WCS metadata, repeated noise
  realizations, and named validation strata while preserving every version-1
  recipe checksum.
- Froze three development datasets, two regression datasets, and one new
  held-out qualification population. The qualification manifest has thirty
  deterministic noise realizations and explicit SNR, resolved/unresolved,
  blend, and edge strata, giving at least thirty samples in every declared
  class.
- Made generated FITS WCS and restoring-beam truth consistent under signed
  unequal pixel scales and rotation. The generator-v2 beam covariance is
  transformed into celestial `BMAJ`, `BMIN`, and east-of-north `BPA`; the
  frozen version-1 FITS file remains byte-identical.
- Prepared the named Phase 4 scientific review record and linked it from the
  plan and documentation navigation. All automated Step 1 items are complete;
  the named human decision remains open.

**Qualification integrity**

- No Phase 4 qualification image, measurement, fit, comparison, or pass/fail
  result was generated or inspected. Only the source recipe, deterministic
  noise seeds, strata, and proposed gates were frozen and schema-validated.

**Validation**

- TDD red states were observed for the new Phase 4 contract surface,
  comparison surface, analytic failure-case governance, and rotated
  WCS/restoring-beam FITS materialisation before their implementations.
- `just coverage`: 520 passed, 28 deselected, and four expected failures with
  94.50% branch-aware project coverage. The changed validation comparison,
  contracts, datasets, and materialisation modules report 98%, 91%, 96%, and
  100% coverage respectively.
- `just test-equivalence`: 14 passed and 537 deselected.
- `just docs-build` passed in strict mode.
- `just check`: 404 passed, 144 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.

**Next**

- Complete the checklist in the Phase 4 scientific review record, amend the
  frozen proposal if required before qualification inspection, and promote
  both contracts to `reviewed-provisional` only after the named approval.
- Then begin Step 2 by preserving exact deblended-region membership through a
  bounded worker-local measurement pipeline.

## 2026-08-02 — Completed Phase 4 Step 1 scientific review

**Plan phase:** Phase 4, Step 1 — named scientific review and amendments

**Decision**

- Gemma Danks, Data Processing Software Engineer and project owner, approved
  the compact measurement contract and numerical gates after the review
  amendments below were encoded and tested. Both Phase 4 contracts are now
  `reviewed-provisional`.
- Kept community source-finding literature and cross-pipeline practice ahead
  of compatibility with either PyBDSF reference where those sources might
  disagree. No disagreement requiring a further exception was identified in
  this review.

**Amendments**

- Made reference or injected truth the sole selector for governed populations.
  Missing candidate shapes, deconvolution classifications/shapes, parent
  identities, and position/flux uncertainties now count as unavailable rather
  than disappearing from a gate denominator.
- Added explicit field-availability and uncertainty-availability evidence.
  Missing candidate parent identities also remain in co-association evidence
  as reference-selected false negatives where appropriate.
- Limited position-angle evidence to reference ellipses with major/minor axis
  ratio at least 1.1 while preserving their axis evidence.
- Strengthened uncertainty calibration to at least 200 independent eligible
  measurements per stratum. The complete 95% interval must lie inside the
  margin, using Wilson score coverage, Student's *t* mean intervals, and a
  fixed-seed SciPy BCa bootstrap with at least 10,000 resamples for dispersion.
- Expanded the frozen qualification campaign from 30 to 200 deterministic
  noise realizations before any measurement or fitting result was generated
  or inspected.

**Qualification integrity**

- No Phase 4 qualification image, measurement, fit, comparison, or pass/fail
  result was generated or inspected. The expanded campaign remains held out
  from routine development and tuning.

**Validation**

- TDD red states were observed for reference-selected eligibility, missing
  candidate availability, position-angle circularity, uncertainty sample
  power, and qualification campaign size before implementation.
- Focused Phase 4 validation: 99 passed.
- `just coverage`: 523 passed, 28 deselected, and four expected failures with
  94.54% branch-aware project coverage; the comparison module reports 97%.
- `just test-equivalence`: 14 passed and 541 deselected.
- `just check`: 410 passed, 144 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.
- `just docs-build` and the complete `just pre-commit` suite passed.

**Next**

- Begin Phase 4 Step 2 by preserving exact deblended-region membership through
  a bounded worker-local measurement pipeline.

## 2026-08-02 — Completed Phase 4 Step 2 worker-local handoff

**Plan phase:** Phase 4, Step 2 — exact region membership and bounded work

**Implemented**

- Added `run_compact_region_stage`, which invokes a typed region processor
  inside each existing coarse executor task. The processor receives immutable
  physical background-subtracted residual, RMS, scientific validity, and exact
  int32 watershed labels; only compact records and summaries return through
  the executor.
- Preserved the lightweight Phase 3 summary-only path. It still returns no
  label plane, while the accepted Phase 4 processor seam supplies exact
  membership without reconstructing it from rectangular summaries.
- Corrected parent-island extraction for overlapping or nested bounds. One
  eight-connected component is selected from the boolean source-filtering-mask
  window using the reconciled canonical first pixel, and its pixel count is
  verified before deblending.
- Bound every input window by the existing coarse batch plan and every
  normalized/watershed workspace by one admitted compact island. The retained
  processor arrays use exactly 21 bytes per admitted bounds pixel; results
  report the largest actual retained batch. Phase 5 deferrals remain explicit.
- Updated the compact-deblending and internal-schema references and the Marimo
  demo to state that region rectangles are planning/read bounds, not
  membership masks.

**Testing and invariants**

- Observed the intended TDD red state before adding the extraction and
  worker-local processor APIs.
- Added analytic coverage where one region's bounding rectangle contains
  pixels owned by another watershed region, plus a nested disconnected island
  inside another island's bounds.
- Added fail-closed tests for worker-array alignment, dtype, immutability,
  scientific validity, region identity/count consistency, and admitted memory
  accounting.
- Proved serial/Dask record equality, compact scheduler results, explicit
  deferrals, generation identity, and bounded processor bytes.

**Validation**

- Focused deblending and execution suite: 40 passed.
- `just coverage`: 534 passed, 28 deselected, and four expected failures with
  94.70% branch-aware project coverage. The changed deblending algorithm and
  stage report 97% and 96% coverage respectively; project coverage increased
  from the preceding 94.54% baseline.
- `just test-equivalence`: 14 passed and 552 deselected.
- `just check`: 416 passed, 146 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.
- `just marimo-check`, strict `just docs-build`, and the complete
  `just pre-commit` suite passed.

**Next**

- Begin Phase 4 Step 3 with failing analytic and property tests for the compact
  moment oracle, using exact worker-local labels from this handoff.

## 2026-08-02 — Completed Phase 4 Step 3 compact moment oracle

**Plan phase:** Phase 4, Step 3 — owned-pixel moments and fit initialization

**Implemented**

- Added a pure vectorized moment oracle for each admitted parent island and
  exact deblended region. It reduces the physical background-subtracted
  float64 plane in canonical pixel order and never treats a region's rectangle
  as membership. Selected-value and coordinate workspaces remain bounded by
  one admitted compact island; Python never loops over pixels or RMS windows.
- Added explicit local pixel and restoring-beam solid angles. Owned-pixel
  integrated Jy is the finite-mask brightness sum times the pixel-to-beam area
  ratio; fitted-Gaussian infinite-area flux has a separate helper and cannot
  be silently copied from the island value.
- Added brightness-weighted global `(x, y)` centroids, covariance, ordered
  Gaussian sigma axes, and pixel major-axis angle as the readable serial
  oracle and nonlinear-fit initializer. Circular covariance uses canonical
  angle zero; celestial east-of-north transformation remains Step 5 work.
- Added frozen valid, shape-unavailable, and unavailable record variants.
  Underdetermined and singular targets retain valid photometry without a fake
  ellipse; invalid/non-finite or non-positive owned measurements expose no
  fabricated flux, shape, or uncertainty.
- Added a pickleable compact moment processor and stage wrapper on the Phase 4
  Step 2 worker-local seam. Parent-island then canonical-region records are
  returned through existing coarse serial or Dask tasks; exact arrays remain
  worker-local and Phase 5 deferrals remain explicit.
- Updated the API/scientific references, internal-schema description, README,
  and living Marimo demo. The demo now displays owned-pixel photometry and
  moment initializers and continues to distinguish them from fitted sources
  and catalogue rows.

**Testing and scientific scope**

- Observed the intended TDD import failures before adding the pure algorithm
  and stage modules.
- Added analytic and property coverage for peak/amplitude, pixel-sum and
  Gaussian-area flux, RMS, mean brightness, centroid, covariance, axes,
  orientation, translation, quarter-turn rotation, positive scaling, exact
  mask exclusion, circular orientation, and C/F memory-order invariance.
- Added fail-closed boundary tests for array rank, shape, dtype, topology,
  solid angles, and Gaussian parameters, plus every Step 3 governed failure:
  non-finite, non-positive, underdetermined, and singular moments.
- Proved equal compact records through the serial and two-worker Dask
  executors. Focused branch-aware coverage reports 100% for the new algorithm,
  records, and stage modules.
- No Phase 4 qualification result was generated or inspected. No performance
  claim was made, so controlled PyBDSF/Rapthor benchmarks were not run.

**Validation**

- Focused moment and serial/Dask suite: 40 passed with 100% branch coverage for
  all new moment modules.
- `just coverage`: 573 passed, 28 deselected, and four expected failures with
  94.91% branch-aware project coverage, up from the preceding 94.70% baseline.
- `just test-equivalence`: 14 passed and 591 deselected.
- `just check`: 455 passed, 146 deselected, and four expected failures; Ruff,
  formatting, and Pyright passed.
- Strict `just marimo-check` and `just docs-build` passed. The updated notebook
  also executed successfully through a temporary Marimo HTML export.

**Next**

- Begin Phase 4 Step 4 by establishing a fit-all compact Gaussian reference
  initialized by these moments, then compare established SciPy and Astropy
  fitting paths against the frozen analytic and regression science cases.

## 2026-08-02 — Completed Phase 4 Step 4 compact Gaussian fitting

**Plan phase:** Phase 4, Step 4 — fit-all compact reference

**Implemented**

- Added a bounded six-parameter elliptical Gaussian fit initialized by the
  exact owned-pixel moment oracle. SciPy TRF least squares operates on the
  physical background-subtracted plane with RMS-weighted residuals and
  explicit amplitude, center, axes, orientation, evaluation, and convergence
  limits.
- Kept every region fit within its existing coarse worker task. No per-source
  executor tasks, private scheduler, native kernel, or selective fitting path
  was introduced.
- Added frozen valid, failed, and unavailable fit records. Iteration
  exhaustion, invalid fitted parameters, insufficient pixels, invalid moments,
  and singular formal covariance cannot fabricate usable values.
- Separated fitted infinite-plane flux from owned-pixel flux and bilinearly
  sampled component RMS at the fitted centroid as required by the reviewed
  contract.

**Selection and evidence**

- Observed the intended missing-module TDD failure before implementing the
  fitter and records.
- The selected SciPy solver and an independent Astropy `Gaussian2D` TRF fit
  recover the same governed rotated analytic Gaussian. SciPy exposes the
  weighted residual, bounds, Jacobian, work limit, and convergence diagnostics
  directly through a narrower production boundary.
- Analytic tests cover sub-pixel recovery, translation and positive-scaling
  equivariance, local-RMS interpolation, non-convergence, underdetermined
  regions, and every configuration boundary. Serial and two-worker Dask
  execution return equal compact records.
- No Phase 4 qualification result was generated or inspected, no selective
  fitting path was proposed, and no performance claim was made.

**Validation**

- Focused fit and serial/Dask suite: 25 passed; Ruff and Pyright passed.

**Next**

- Complete Phase 4 Step 5 with local Astropy WCS transformation, covariance
  beam deconvolution, and explicit uncertainty calibration evidence.

## 2026-08-02 — Implemented Phase 4 compact astrometry and deconvolution

**Plan phase:** Phase 4, Step 5 — celestial transformation and beam
deconvolution

**Implemented**

- Added a scheduler-safe celestial fit record and pure transformation boundary
  that reconstructs Astropy WCS from serialized metadata, uses zero-based
  `(x, y)` coordinates, and derives a local east/north Jacobian.
- Transformed fitted covariance, centroid covariance, local pixel area, and
  position through the same local geometry. RA wraparound, signed/unequal
  scales, rotation, and celestial east-of-north position angle remain
  explicit.
- Added covariance-matrix restoring-beam deconvolution with resolved,
  unresolved, and marginal diagnostics. Scientific absence is null; only the
  compatibility adapter may serialize an unresolved zero-axis sentinel.
- Evaluated `radio_beam` and retained the direct NumPy implementation because
  the reviewed three-state semantics still require local logic and the added
  dependency would not simplify this small boundary.
- Preserved formal independent-pixel position and flux errors with explicit
  flags, and left uncalibrated shape or singular errors absent rather than
  zero.

**Testing and scope**

- Added analytic tests for local WCS signs and rotation, RA wraparound,
  unequal pixel scales, fitted ellipse conversion, aligned deconvolution,
  marginal and unresolved states, local flux geometry, and absent formal
  covariance.
- The frozen Monte Carlo correlated-noise calibration remains open; these
  changes do not claim calibrated uncertainty coverage.

## 2026-08-02 — Implemented bounded compact catalogues and Rapthor FITS view

**Plan phase:** Phase 4, Steps 6 and 7 — association, catalogue construction,
and compatibility serialization

**Implemented**

- Kept parent islands, fitted Gaussian components, and source candidates as
  separate typed records under the reviewed provisional one-region/one-source
  compact policy. IDs derive from canonical global region identity.
- Added one bounded catalogue shard per existing coarse executor batch,
  deterministic pairwise shard reduction with fan-in two and logarithmic
  depth, and an explicit final in-memory source-record cap.
- Made complete catalogue construction fail closed on every invalid fit,
  omission, or Phase 5 deferral. The incomplete stage still retains compact
  records and reasons for inspection.
- Added the exact eight-column FITS view read directly by the pinned Rapthor
  diagnostic code. Types, units, zero-row schema, deterministic source
  numbering, adapter-only unresolved zero sentinel, NaN unknown errors,
  checksums, atomic publication, and conflict-safe retries are frozen.
- Corrected the earlier reader assumption: Rapthor uses Astropy to read this
  FITS table, then writes a minimal makesourcedb text model for LSMTool. LSMTool
  does not read the source-list FITS product and remains outside Hebog's core
  dependencies.
- Updated schema/compatibility documentation, README status, and the living
  Marimo notebook. The notebook now executes the complete no-deferral compact
  demo through fitted/deconvolved catalogue rows and the Rapthor FITS product.

**Evidence**

- Focused catalogue algorithm/record tests reach 100% branch coverage; focused
  Rapthor adapter tests reach 100% branch coverage.
- One/many-tile and serial/two-worker Dask catalogue shards are equal. Input
  order, source numbering, catalogue bytes, and retry behaviour are
  deterministic.
- The same three-row compact catalogue passes every frozen exact Phase 4 gate
  against both released and pinned-`master` PyBDSF. Rapthor's 10-arcsec size
  and 2-arcsec position-error diagnostic cuts retain all three rows.
- The compact reference has 65,534 of 65,536 identical pixel-centre mask
  decisions against each PyBDSF reference, exceeding the 99.5% downstream
  decision gate.
- Focused dual-reference/adapter/mask suite: 11 passed. Focused unit,
  integration, and executor suite: 32 passed. Strict Marimo validation and a
  complete temporary HTML execution passed.

**Scientific blocker discovered**

- The generated crowded regression contains three injected pairs narrower
  than one restoring beam. Each pair has only one observable image maximum,
  so the reviewed deblender correctly produces four regions for seven input
  Gaussians. Lowering the saddle threshold to zero did not change this result.
- The one-region/one-source policy therefore cannot meet the flat
  seven-emitter completeness assertion. The test is retained as a strict
  expected failure so an eventual scientifically reviewed solution becomes a
  visible unexpected pass.
- No held-out qualification result was inspected. The association/resolvability
  policy, declared truth grouping, and blend population require amended named
  human review, after which the unseen qualification recipe and checksum must
  be replaced before qualification runs.

**Next**

- Complete the association-model amendment review, replace the untouched
  qualification population, calibrate formal uncertainties, and run the
  controlled Phase 4 performance matrix before declaring the phase passed.

## 2026-08-02 — Recorded the Phase 4 readiness decision

**Plan phase:** Phase 4, Step 8 — qualification and release readiness

**Completed**

- Published a Phase 4 release-readiness record that separates the implemented
  compact catalogue capability from the scientific and performance exit gate.
- Recorded the exact-reference, downstream-decision, bounded-memory,
  deterministic-execution, compatibility, portability, and deferral evidence.
- Recommended an observable-resolvability policy: per-emitter gates for
  independently observable maxima, explicit group truth and group-level
  centroid/total-flux gates for unresolved injected blends, and no joint
  multi-Gaussian fit without identifiability and reliability evidence.
- Added an unchecked named amendment decision to the scientific review record.
  The existing approval does not silently authorize this material change.
- Ordered the remaining work so the contract and replacement unseen dataset
  are reviewed before qualification inspection, and science closes before
  performance qualification.

**Gate status**

- The Phase 4 readiness decision is **not ready**. No held-out qualification
  output was inspected and no Phase 4 performance claim was made.
- The next action requires named human approval of the proposed association
  amendment. That decision then permits replacement of the affected governed
  truth and completion of uncertainty, qualification, and benchmark evidence.

## 2026-08-03 — Approved the Phase 4 association amendment

**Plan phase:** Phase 4 scientific closure

**Decision**

- Gemma Danks, Data Processing Software Engineer and project owner, approved
  the recommended observable-resolvability policy on 2026-08-03.
- Per-emitter gates apply only to independently observable eligible maxima.
  Sub-beam injected members forming one maximum use explicit truth association
  groups with group-level centroid and total-flux gates.
- One component/source remains the Phase 4 default for a single eligible
  maximum. Joint multi-Gaussian model selection is deferred until governed
  identifiability and reliability evidence justifies it.
- The affected regression and untouched qualification definitions must be
  replaced and reviewed before any replacement held-out result is inspected.

**Next**

- Add the explicit truth-group schema and replace the affected governed
  manifests and checksums before running regression or qualification.

## 2026-08-03 — Froze replacement Phase 4 truth groups

**Plan phase:** Phase 4 scientific closure — pre-qualification contract

**Implemented**

- Added manifest schema 2 with explicit association-group identifiers,
  resolution class, canonical source membership, analytic group centroid and
  integrated brightness, and separately governed group strata.
- Replaced the affected development/regression truth and the untouched held-out
  qualification definition. The held-out dataset now has identifier
  `phase4-unseen-grouped-measurement-qualification-512`, base seed
  `2026083001`, and recipe SHA-256
  `fe4ba6cd64a83e9c274d9eb83a3427b6f0361d0491e8683431ac5be2ccac6e8e`.
- Removed unresolved injected members from individual qualification strata and
  added a 200-sample unresolved-group stratum.
- Added frozen-provisional unresolved-group centroid and total-flux gates and
  tests that reject incomplete, overlapping, stale, or ambiguous truth.

**Regression evidence**

- The crowded regression now passes: four observable groups are recovered from
  seven emitters. Its unresolved groups are within provisional 0.10/0.20-beam
  centroid and 10%/20% total-flux median/tail limits.
- The run exposed an independent validation-contract problem previously hidden
  by the association failure. A legitimate 12-SNR noise draw misses the flat
  absolute tail gate. It remains a strict expected failure; the seed and
  assertion were not weakened.
- No replacement qualification image or scientific output was generated or
  inspected.

**Next**

- Obtain named review of the provisional group margins and the recommended
  SNR-stratified confidence-interval rule before qualification inspection.

## 2026-08-03 — Approved Phase 4 grouped and noisy-source gates

**Plan phase:** Phase 4 scientific closure — numerical review

**Decision**

- Gemma Danks approved the 0.10/0.20-beam unresolved-group centroid limits and
  10%/20% total-flux limits on 2026-08-03.
- Generated noisy-source qualification will use SNR-stratified confidence
  intervals for bias and uncertainty calibration plus the existing
  catastrophic-outlier rate. Absolute noisy-source tails remain report-only.
- Strict analytic/noiseless and exact compact-reference absolute gates remain
  unchanged.

**Next**

- Implement and pass the regression/calibration report before opening the
  replacement held-out qualification campaign.

## 2026-08-03 — Passed powered correlated-noise regression calibration

**Plan phase:** Phase 4 scientific closure — pre-qualification evidence

**Implemented**

- Added generator-v3 beam-shaped Gaussian-correlated noise with exact bounded
  window and partition invariance while preserving version-1/version-2 recipe
  checksums.
- Replaced independent-pixel error scaling with a generalized OLS sandwich
  covariance using the declared pixel-noise correlation function.
- Added an eight-pixel bounded context around compact fit regions and a
  bounded local residual-background nuisance parameter. Exact region labels
  still own moments; context pixels affect only the nonlinear fit.
- Implemented deterministic Student-*t*, Wilson-score, and fixed-seed SciPy
  BCa intervals plus the reviewed entire-interval decision rule.

**Regression evidence**

- The original 200-sample strata had acceptable normalized-residual point
  estimates but insufficient power for the approved 95% entire-interval rule.
  No seed was removed or selected.
- Expanded the regression source population across independent positions and
  shapes while retaining all 200 predeclared noise realizations. Every SNR
  stratum now contains 1,600 eligible measurements.
- The powered regression passed all position, peak-flux, integrated-flux,
  availability, normalized-bias, one-sigma-coverage, and dispersion gates in
  233.38 seconds on the local development host.
- Normal generated association/measurement regression remained green: two
  cases passed in 3.43 seconds. Dataset validation remained green: 52 tests
  passed.

**Held-out boundary**

- Replaced the still-unopened qualification definition with
  `phase4-unseen-powered-correlated-measurement-qualification-512`, base seed
  `2026085001`, and recipe SHA-256
  `4b0104eddb7569bb68058783f836c9e701c0a4362b7d75ce50968b96ca25b3e6`.
- It retains the 200 predeclared realization seeds and supplies at least 1,600
  eligible measurements in every SNR, shape, and edge stratum. The
  unresolved-group absolute-metric stratum retains 200 samples.
- No qualification image, fit, catalogue, report, or pass/fail result was
  generated or inspected before the regression campaign passed.

**Next**

- Run the first powered held-out qualification once, persist its complete
  machine-readable report, and do not tune against the result.

## 2026-08-03 — Recorded the failed powered held-out qualification

**Plan phase:** Phase 4 scientific closure — held-out qualification

**Validation order**

- Fixed local-RMS sampling to use the retained fit-context coordinate frame
  before opening held-out output and added a focused regression test.
- Re-ran the complete powered correlated-noise regression after that fix: one
  campaign passed in 295.54 seconds across all 200 predeclared realizations.
- Ran the powered held-out campaign once. It completed in 479.84 seconds and
  wrote its complete machine-readable report under the ignored
  `benchmark-results/` evidence directory before applying gate decisions.

**Held-out result**

- Recovered 6,586 of 6,600 observable truth groups from 6,607 candidates:
  99.79% completeness and 99.68% overall reliability, both passing.
- Fitted-shape and classification availability were 99.78%; resolved-shape
  availability was 100%.
- Resolved/unresolved classification agreement was 73.57%, below the frozen
  95% minimum.
- Fifty of 6,386 matched individual rows were catastrophic outliers: 0.783%,
  above the frozen 0.5% maximum.
- Four 95% normalized-mean intervals failed the entire-interval rule:
  SNR-10 integrated flux (0.141 to 0.243), SNR-25 peak flux (0.061 to 0.161),
  unresolved-shape integrated flux (0.098 to 0.197), and edge integrated flux
  (0.113 to 0.214).
- The run exposed an under-specified unresolved-group reliability denominator.
  The conservative provisional calculation was 90.50%, but it assigns every
  unmatched candidate to the unresolved population even when the candidate is
  nearer an individually resolvable group. This is recorded as a contract
  issue rather than silently redefined after inspection.

**Decision**

- Phase 4 remains **not ready**. No parameter, threshold, seed, population, or
  margin was changed after inspection, and the failed campaign is preserved as
  known evidence rather than reused as unseen qualification data.
- Controlled performance qualification is deferred because the documented
  closure order requires a scientifically eligible implementation first.

**Next**

- Freeze a new unseen campaign before corrective scientific work, obtain named
  review of the reliability denominator and any boundary-classification
  amendment, correct against development/regression evidence, then qualify on
  the new held-out campaign before running the Phase 4 performance matrix.

## 2026-08-03 — Froze the extension-aware replacement qualification

**Plan phase:** Phase 4 scientific closure — post-failure correction

**Research decision**

- Peer-reviewed radio-catalogue practice does not classify every positive
  fitted-minus-beam size as resolved. ATLAS DR3 uses a one-sided two-sigma
  integrated-to-peak flux-ratio uncertainty test, with a stated 2.3%
  point-source false-positive probability. Deep GMRT catalogue work likewise
  treats low-SNR fitted-width inflation as noise and uses peak flux for
  unresolved sources. Condon and Aegean support reducing free fit parameters
  when source shape is known.
- Froze a provisional contract that gates point-source specificity and clearly
  resolved recall separately, reports marginal-extension classification by
  SNR, and retains reliability only at the globally observable catalogue
  level. The unresolved-group gate retains completeness, centroid, and total
  flux; its unobservable morphology-specific reliability denominator was
  removed.

**Held-out boundary**

- Archived the inspected recipe unchanged as
  `phase-4-viewed-qualification.json`, checksum
  `4b0104eddb7569bb68058783f836c9e701c0a4362b7d75ce50968b96ca25b3e6`.
- Froze `phase4-unseen-extension-aware-measurement-qualification-512`, recipe
  checksum
  `54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49`,
  before production correction. Its 200 seeds are disjoint from the viewed
  campaign and it adds a distinct WCS, negative background, varying RMS,
  invalid pixels, and predeclared point, clear-resolved, marginal-resolved,
  edge, SNR, and unresolved-group strata.
- No image, fit, catalogue, comparison, or result from the new campaign was
  generated or inspected.

**Next**

- Implement the two-sigma rule and unresolved flux policy through TDD, pass
  independent development/regression and compatibility lanes, obtain named
  human review, then open the replacement qualification exactly once.

## 2026-08-03 — Corrected extension classification without opening held-out data

**Plan phase:** Phase 4 scientific closure — post-failure correction

**Implemented**

- Added an explicit ATLAS-style one-sided two-sigma log integrated-to-peak
  uncertainty test after geometric beam deconvolution. Insignificant extension
  is unresolved with a canonical flag; a noisy fit without usable flux
  uncertainty has unavailable classification.
- Changed the compact catalogue policy to report peak and peak error as total
  flux and total-flux error for an unresolved source. Significantly resolved
  sources retain the free fitted-Gaussian integral.
- Added explicit point, clear-resolved, and marginal-resolved classification
  strata to the governed regression and replacement qualification manifests.
  Clear truth requires fitted-to-beam area ratio at least 3 and SNR at least
  25; marginal extension is report-only.
- Kept resolved and marginal free-fit integrated-flux uncertainty report-only
  after regression showed it was not calibrated. Position, peak flux, and
  unresolved peak-as-total uncertainty remain gated.
- Versioned the amended measurement contract as schema 2 and retained
  `frozen-provisional` status so the held-out runner cannot execute before
  named review.

**Compatibility decision**

- The raw released and `master` PyBDSF products remain immutable. One governed
  unresolved PyBDSF row has a free-fit total about 39% below its peak. The exact
  comparison now applies the declared peak-as-total unresolved catalogue view
  while a focused test preserves and reports the raw divergence.
- This is intentional community-policy non-equivalence, not an accidental
  tolerance. Review Rapthor's downstream use of `Total_flux` before enabling
  Hebog as its default backend.

**Regression and validation evidence**

- The complete powered correlated-noise regression passed all applicable
  position, peak-flux, unresolved integrated-flux, point-specificity, and
  clear-extension gates in 355.29 seconds across the 200 predeclared
  development/regression realizations.
- Exact compact comparisons against released and pinned-`master` PyBDSF plus
  the explicit raw-divergence test passed: four tests in the final 4.42-second
  rerun.
- `just check` passed Ruff formatting/lint, Pyright, doctests, and 537 fast
  tests; the integration lane passed 127 tests; the acceptance lane retained
  its seven expected failures; strict documentation and Marimo checks passed.
- Branch-aware coverage passed at 94.92%: 663 tests passed. The changed
  scientific/configuration/stage modules report 96–100% coverage; the changed
  validation-contract and dataset modules report 92% and 96%, respectively.
- The replacement qualification test was invoked only to verify its guard and
  skipped at `frozen-provisional` before recipe iteration or output creation.
  The replacement recipe checksum remains
  `54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49`.

**Next**

- Obtain named review of every extension/flux addendum decision in the Phase 4
  scientific review record. Only then promote the contracts to
  `reviewed-provisional` and open the replacement qualification campaign once.

## 2026-08-03 — Approved the Phase 4 extension and flux addendum

**Plan phase:** Phase 4 scientific closure — named review

**Decision**

- Gemma Danks, Data Processing Software Engineer and project owner, approved
  the complete post-failure extension-classification and unresolved-flux
  addendum without amendment.
- The approval covers the ATLAS two-sigma rule, separate point/clear gates,
  the area-ratio-3 and SNR-25 clear population, report-only marginal extension
  and resolved/marginal total-flux uncertainty, peak-as-total unresolved flux,
  global-only reliability, and the documented raw PyBDSF divergence.
- Promoted both Phase 4 contracts from `frozen-provisional` to
  `reviewed-provisional`. The replacement qualification campaign remained
  unopened throughout review.

**Next**

- Validate and commit this review record, then run the frozen replacement
  qualification campaign exactly once without post-inspection tuning.

## 2026-08-03 — Recorded the failed extension-aware qualification

**Plan phase:** Phase 4 scientific closure — held-out qualification

**Execution boundary**

- Committed the named approval as `bf5a725` before opening held-out output.
- Ran the reviewed replacement campaign exactly once. It completed in 477.85
  seconds across all 200 frozen realizations and wrote a 35,126-byte ignored
  evidence record with SHA-256
  `ae1ce5b15a72d7089e14321854fe988ca6634ab3179009842810128aa8414c89`.
- The dataset identifier and recipe SHA-256 match the frozen manifest:
  `phase4-unseen-extension-aware-measurement-qualification-512` and
  `54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49`.

**Passing evidence**

- Recovered 6,583 of 6,600 truth groups from 6,612 candidates: 99.74%
  completeness and 99.56% reliability.
- Fitted-shape availability was 99.72%, governed classification availability
  99.22%, point-source specificity 96.34%, clear-extension recall 100%, and
  resolved-shape availability 100%.
- Every gated normalized-residual calibration decision passed. The unresolved
  group's 100% completeness, centroid, and total-flux summaries also passed.

**Failed evidence**

- 1,128 of 6,382 matched individual rows were catastrophic outliers: 17.67%
  against the frozen 0.5% maximum. Report-only integrated-flux absolute error
  had median 4.80% and 95th percentile 115.42%.
- SNR-10 uncertainty availability was 98.94% (1,583 of 1,600) and edge
  availability was 98.88% (1,582 of 1,600), both below the 99% floor for
  position, peak flux, and integrated flux.
- Report-only resolved/marginal integrated-flux calibration failed across the
  SNR and extended-shape strata, as retained diagnostic evidence rather than a
  post-inspection gate.

**Decision**

- Phase 4 remains **not ready**. No parameter, threshold, population, seed,
  margin, or gate was changed, and the campaign was not rerun.
- The controlled performance matrix was not run because the documented closure
  order requires scientific qualification first.

**Next**

- Preserve this campaign as viewed evidence and require a new frozen unseen
  campaign before corrective production changes. Extend the powered regression
  to expose catastrophic-flux and availability behavior, select any correction
  only from development/regression evidence, and obtain named review before
  opening the next held-out campaign.

## 2026-08-03 — Froze the third Phase 4 qualification campaign

**Plan phase:** Phase 4 scientific closure — post-failure boundary

**Held-out boundary**

- Archived the failed extension-aware manifest unchanged as
  `phase-4-viewed-extension-aware-qualification.json`, retaining recipe
  SHA-256
  `54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49`.
- Froze `phase4-unseen-flux-availability-measurement-qualification-512` with
  recipe SHA-256
  `7d2bf112051231f4fcad4dd8de40b58e5eeaefe572f315bd9f7e3f365f21087b`.
  Its 200 seeds are disjoint from both viewed campaigns. It changes the WCS,
  signed pixel scales, sky position, rotation, negative background, RMS
  gradient, and invalid-pixel location while retaining the reviewed truth
  matrix.
- Returned both Phase 4 contracts to `frozen-provisional`; the qualification
  test therefore skips before recipe iteration until a new amendment receives
  named review.
- No third-campaign image, fit, catalogue, comparison, or result was generated
  or inspected.

**Next**

- Extend the powered development/regression runner to gate catastrophic flux
  and uncertainty availability before selecting any corrective policy.

## 2026-08-03 — Reproduced both Phase 4 failures in development

**Plan phase:** Phase 4 scientific closure — third-campaign amendment

**Catastrophic-tail diagnosis**

- Extended the existing 200-realization development runner with the exact
  frozen catastrophic definitions. The intended red test failed with 283 of
  4,800 matched rows above at least one threshold.
- All 283 rows were predeclared `shape-marginal-resolved` truth. The metric
  counts were 274 integrated-flux, one fitted-axis, eight deconvolved-axis,
  and zero position or peak-flux failures. Point and clearly resolved truth
  had zero catastrophic rows.
- Peer-reviewed population practice supports keeping ambiguous marginal flux
  separate: ATLAS DR3 uses integrated-to-peak significance and peak-as-total
  for point-like sources, while the ASKAP/EMU challenge does not apply its
  catastrophic point-source flux analysis to the extended challenge because
  that comparison is biased. The proposed amendment keeps the 0.5% ceiling
  and all numerical thresholds, reports only marginal integrated-flux
  catastrophes, and continues to gate every other metric plus integrated flux
  for point and clearly resolved truth.

**Edge-availability diagnosis**

- Added a generated regression recipe with five isolated SNR-10-to-15 point
  sources truncated independently by all four image sides, 50 deterministic
  realizations, and recipe SHA-256
  `15b5d5807abee379567bb51913600046b05d896935c1e4f7889c0be5a9f194fd`.
- Its intended red test reproduced the gate miss at 247/250. All three missing
  matches were for the higher-noise bottom edge; deterministic seed inspection
  showed valid Gaussian fits whose centroids had moved beyond the sampled
  image footprint.
- Clamped fit-centre bounds to the physical sampled footprint while preserving
  the configured context margin inside it. The focused unit lane passed 19
  tests and the identical powered edge regression then passed 250/250.

**Validation**

- The corrected 200-realization, 4,800-match uncertainty/classification/
  catastrophic regression passed in 343.68 seconds.
- Six remaining generated-truth and exact compact-catalogue equivalence tests
  passed against both PyBDSF anchors. The third-campaign guard skipped before
  recipe iteration because both contracts remain `frozen-provisional`.
- `just check` passed with 538 tests and four expected failures; Ruff, Pyright,
  and the strict documentation build also passed.
- The branch-aware coverage lane passed 665 tests with four expected failures
  at 94.92% project coverage; the changed fitting bounds are exercised by the
  focused edge invariant and powered regression.

**Held-out boundary**

- The third campaign remains unchanged and unopened. Both contracts remain
  `frozen-provisional`; named review is required after the complete regression
  and handoff suites pass.

## 2026-08-03 — Approved the third Phase 4 amendment

**Plan phase:** Phase 4 scientific closure — named review

- Gemma Danks, Data Processing Software Engineer, approved both proposed
  decisions without amendment: marginal-resolved integrated-flux catastrophic
  rate is report-only while all other declared catastrophic comparisons stay
  gated; and fitted centroids must remain inside the sampled image footprint.
- Promoted the Phase 4 measurement and scientific-gate contracts from
  `frozen-provisional` to `reviewed-provisional` only after the complete
  development/regression, exact-reference, coverage, and handoff evidence had
  passed.
- No third-campaign image, fit, catalogue, comparison, or result had been
  generated or inspected when this approval was recorded.

**Next**

- Commit this approval boundary, then open the third frozen campaign exactly
  once. Proceed to controlled performance qualification only if every
  scientific gate passes.

## 2026-08-03 — Recorded the failed third Phase 4 qualification

**Plan phase:** Phase 4 scientific closure — held-out qualification

**Execution boundary**

- Committed the named approval as `a121bba` before opening held-out output.
- Ran `just test-qualification` exactly once. The complete lane finished in
  433.55 seconds with one lightweight qualification pass, one skip, and the
  frozen 200-realization campaign failure.
- The 34,746-byte ignored evidence record has SHA-256
  `ed060b7703161ba01037939ff9a8e4b6e3d6ab527dc3b1fd45753dfb69c1165e`.
  Its dataset identifier and recipe SHA-256 match the frozen manifest:
  `phase4-unseen-flux-availability-measurement-qualification-512` and
  `7d2bf112051231f4fcad4dd8de40b58e5eeaefe572f315bd9f7e3f365f21087b`.
- Preserved the preceding 35,126-byte campaign separately at
  `benchmark-results/phase-4-second-qualification.json`, SHA-256
  `ae1ce5b15a72d7089e14321854fe988ca6634ab3179009842810128aa8414c89`.

**Passing evidence**

- Recovered all 6,600 truth groups from 6,621 candidates: 100% completeness
  and 99.68% reliability.
- Fitted-shape and classification availability, clear-resolved recall, and
  resolved-shape availability were 100%; point-source specificity was 97.06%.
- All uncertainty fields were available. Every position and peak-flux
  calibration decision and every unresolved-group gate passed.
- The predeclared report-only marginal integrated-flux diagnostic recorded
  1,094 of 4,600 rows (23.78%) without entering the gated failure population.

**Failed evidence and decision**

- Thirty-six of 6,400 matched individual sources were gated catastrophic
  outliers: 0.5625% against the unchanged 0.5% maximum.
- Unresolved integrated-flux normalized residual had mean 0.1335 and a 95%
  interval of 0.0823--0.1846, crossing the approved absolute 0.15 mean margin.
  Its coverage and dispersion intervals passed.
- No parameter, gate, truth population, seed, or margin changed after
  inspection, and the campaign was not rerun. It is retained as viewed failed
  evidence.
- Returned both contracts to `frozen-provisional` and updated the manifest
  provenance so the executable guard prevents accidental reuse.
- Phase 4 remains **not ready**. The controlled performance matrix was not run
  because scientific qualification failed.

**Next**

- Do not generate serial replacement campaigns to seek a passing draw.
  Establish and approve a recovery protocol that accounts for repeated-
  campaign optional stopping, freeze any future qualification population
  before corrective implementation, and choose corrections only from analytic
  and independent development/regression evidence.

## 2026-08-03 — Audited PyBDSF and approved the Phase 4 recovery direction

**Plan phase:** Phase 4 scientific recovery and closure

**Reference audit**

- Ran released PyBDSF 1.14.1 on the viewed third campaign with the exact
  Rapthor/LSMTool configuration. The ignored machine-readable comparison is
  `benchmark-results/phase-4-pybdsf-release-qualification-comparison.json`,
  SHA-256
  `298b91312749953ef6b356fbc863343f693a0378aa0aa46815c60bb229640eb0`.
- Released PyBDSF recovered 6,599 of 6,600 groups from 6,615 candidates. Its
  canonical unresolved-source view achieved 99.75% point-source specificity
  and 12 gated catastrophic rows among 6,399 matches (0.1875%), both better
  than Hebog's third-campaign 97.06% and 0.5625%.
- Released PyBDSF did not pass the full campaign. It failed 16 gated
  normalized-uncertainty decisions plus the unresolved-group
  95th-percentile position and total-flux gates. Hebog passed those decisions,
  recovered every group, and retained materially better unresolved-group
  tails.
- Pinned PyBDSF `master` at
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c` failed deterministically on
  frozen seed `2026090152`. The Rapthor-required atrous Gaussian-fitting path
  interpolates past a two-pixel island and raises `IndexError`; released
  PyBDSF and Hebog complete the same input.
- The reference runner's 300.39-second duration is diagnostic, not a speed
  comparison with the differently scoped Hebog qualification lane.

**Decision**

- Gemma Danks approved preserving every absolute community-science gate and
  Hebog's stronger recovery, uncertainty, unresolved-group, deterministic,
  and bounded-execution results while correcting point classification and
  catastrophic tails until Hebog is equal to or better than released PyBDSF.
- The authoritative plan now requires a permanent per-source dual-reference
  diagnostic, a named and powered paired-comparison protocol, one final frozen
  unseen campaign, TDD using only analytic and independently seeded
  development/regression evidence, and a no-worse PyBDSF point estimate plus
  paired non-inferiority evidence for every gated metric.
- Non-claim profiling may proceed during scientific recovery. Phase 4 closes
  only after the final scientific and matched incremental performance gates
  pass; bounded-memory and distributed scalability of the qualified compact
  path then becomes the next active engineering focus.

**Validation**

- `just docs-build` passed with the existing informational Material for MkDocs
  notice and ADR navigation inventory.
- `just check` passed: Ruff formatting and lint, Pyright, 538 tests, and four
  expected failures.
- `just pre-commit` passed every push-stage hook across all files, including
  JSON formatting, codespell, strict Marimo validation, documentation, quick
  tests, and lockfile consistency.

## 2026-08-03 — Added explainable paired-campaign evidence

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Added a strict versioned campaign-evidence document that requires Hebog and
  every named reference to report an outcome for every shared image seed.
- Added deterministic per-source diagnostics for matched sources, missed truth,
  and extra candidates, including truth strata, raw catastrophic flags,
  governed catastrophic decisions, quality and classification information,
  and normalized uncertainty residuals.
- Made a failed implementation outcome first-class evidence. This preserves
  the pinned PyBDSF `master` failure without silently removing that seed or
  scoring an incomplete catalogue.
- Reused the comparison oracle's normalized-residual primitive so aggregate
  calibration reports and paired source rows cannot drift apart.

**Validation**

- Focused Ruff formatting and lint, Pyright, and 101 comparison, diagnostic,
  and evidence tests passed. The new diagnostic module has 100% branch-aware
  coverage; the two touched validation modules have 95.64% combined coverage.
- `just coverage` passed 672 tests with four expected failures and 94.56%
  branch-aware project coverage before the final validator-only test additions.
- `just docs-build`, `just check` (570 passed and four expected failures), and
  every `just pre-commit` push-stage hook passed.

**Next**

- Add a maintained same-image campaign runner that emits these records for
  Hebog, released PyBDSF, and pinned PyBDSF `master`, then define and power the
  named paired non-inferiority analysis before changing scientific behaviour.

## 2026-08-03 — Added the maintained dual-reference campaign runner

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Added one isolated PyBDSF campaign runner for both the released and pinned
  `master` environments. It freezes Rapthor's exact options, regenerates the
  same governed float64 images, binds the complete seed/truth/strata record,
  and records exact software, container, dependency, and execution-policy
  identities.
- Added mergeable per-implementation evidence and a candidate-first compiler
  that rejects dataset, seed, scientific-contract, or comparison-protocol
  drift.
- Preserved every observable association group as well as individual source
  diagnostics. Unresolved-group flux retains the raw fitted total while the
  Rapthor-facing unresolved individual view remains peak-as-total.
- Made source-finding and comparison exceptions explicit per-seed failures,
  with complete tracebacks in the external run log and stable digests in the
  evidence. Runners refuse to overwrite an existing result.
- Hardened the established PyBDSF FITS reader so zero and NaN error sentinels
  become explicit unavailable values rather than invalid uncertainties.

**Validation**

- TDD first recorded the missing association model, campaign module, reference
  runner, and sentinel handling. Focused Ruff, Pyright, and 117 campaign,
  evidence, reader, runner, diagnostic, and comparison tests passed.
- `just coverage` passed 719 tests with four expected failures and 95.28%
  branch-aware project coverage. The new campaign module has 100% branch
  coverage and the expanded evidence model has 96%.
- `just docs-build` passed with only the existing informational Material for
  MkDocs notice and ADR navigation inventory.
- `just check` passed 592 tests with four expected failures;
  `just test-equivalence` passed all 20 frozen non-slow equivalence cases; and
  every `just pre-commit` push-stage hook passed.

**Next**

- Define the paired non-inferiority metric directions, margins, multiplicity
  policy, confidence method, and power calculation for named review. Do not
  freeze or open the final unseen population until that review is recorded.

## 2026-08-03 — Drafted the paired Phase 4 closure protocol

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Added a strict draft-provisional paired non-inferiority contract covering
  metric directions, practical margins, whole-image resampling, primary and
  secondary reference failures, all-endpoint passage, and the one-final-look
  stopping rule.
- Added an executable clustered normal-approximation power calculation. The
  proposed 600-realization design gives at least 92.2% interval-exclusion
  power under its provisional assumptions; point specificity is 94.5% and the
  catastrophic-outlier endpoint is 93.3%.
- Made the stricter no-worse point-estimate condition statistically explicit:
  it has only 50% probability under exact equality, so the calculation reports
  it and the combined decision separately rather than claiming 90% overall
  passage.
- Added a reviewer guide with the scientific background, proposed margins,
  endpoint split, failure handling, stopping rule, community-source-finding
  basis, and named decisions still required.
- Kept the contract provisional. No final qualification seed, truth, image, or
  result was generated or inspected. Every planning variance assumption must
  be verified on independent paired development/regression evidence before
  named approval and population freeze.

**Validation**

- TDD first recorded the missing strict contract and power calculation; all 14
  focused contract, validation, boundary, and failure tests now pass.
- `just coverage` passed 733 tests with four expected failures and 95.38%
  branch-aware project coverage; the new power module has 100% coverage and
  the expanded contract module has 94%.
- `just test-equivalence` passed all 20 frozen non-slow scientific comparisons.
- Ruff formatting and lint, Pyright, and the strict MkDocs build passed.
  `just check` passed 606 tests with four expected failures, and every
  `just pre-commit` push-stage hook passed across all files, including JSON
  formatting, strict Marimo validation, documentation, and lock consistency.

**Next**

- Produce paired independent development/regression shards and verify the
  discordance, within-image correlation, and paired-dispersion planning bounds
  before requesting named review. Do not change production science or freeze
  the final unseen population first.

## 2026-08-03 — Added the maintained Hebog campaign runner

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Added a candidate runner that exercises Hebog's complete bounded serial
  detection, deblending, fitting, transformation, and catalogue path for every
  governed regression or qualification realization.
- Froze every candidate scientific threshold, bounded-work limit, 128-pixel
  tile size, float64 input policy, and serial executor in the implementation
  configuration digest.
- Added shared campaign-runtime helpers for contract, dataset, dependency, and
  failure identities, and migrated the PyBDSF runner to them so candidate and
  reference provenance cannot drift.
- Allowed both isolated runners to use governed regression data for the
  planning-assumption audit while retaining named review as a prerequisite for
  final qualification use.
- Kept every candidate or reference exception as a complete failed-seed record
  with no partial catalogue and no denominator deletion.

**Validation**

- TDD first recorded the missing candidate configuration and failure path.
  Nineteen focused unit and integration tests pass, including a real complete
  Hebog run on a generated development image.
- The shared campaign-runtime module has 100% branch-aware focused coverage.
- `just coverage` passed 741 tests with four expected failures and 95.52%
  branch-aware project coverage; the shared campaign-runtime module has 100%
  coverage.
- `just test-equivalence` passed all 20 frozen non-slow scientific comparisons.
  Ruff formatting and lint, strict Pyright, and the strict documentation build
  passed. `just check` passed 613 tests with four expected failures, and every
  `just pre-commit` push-stage hook passed across all files.

**Next**

- Add a structurally representative independent recovery-regression dataset,
  generate paired Hebog and released-PyBDSF shards, and measure the protocol's
  planning variance bounds. Do not use any viewed qualification output for
  that audit.

## 2026-08-03 — Governed the paired planning population

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Added a viewable recovery-regression population with the exact proposed
  endpoint structure: 200 disjoint noise seeds, 33 observable groups, 32
  individually resolvable sources, eight beam-compatible point sources, one
  clearly resolved source, and one unresolved blend per image.
- Used a distinct WCS, background, noise gradient, invalid region, and a
  180-degree mirrored source layout that preserves the governed blend-to-beam
  geometry. The design preserves the relevant SNR and shape populations while
  remaining statistically independent of every previously used noise
  realization.
- Bound the generator-v3 recipe to SHA-256
  `2669ad5c7e0883e50b6c82a8d1c66d92a8890df9d8fc7b64a645d6bdf52dedca`.
  The manifest is explicitly regression evidence for planning and TDD; it can
  never qualify Hebog or be relabelled as unseen.

**Validation**

- TDD first recorded two failures for the missing governed manifest. The
  focused role, independence, structure, and checksum tests now pass.
- The repository JSON formatting hook accepts the new manifest.

**Next**

- Commit the governed population, run Hebog and released PyBDSF on the same
  200 images, compile the paired evidence, and estimate every provisional
  discordance, within-image correlation, and paired-dispersion bound.

## 2026-08-03 — Corrected the paired blend geometry before tuning

**Plan phase:** Phase 4 scientific recovery and closure

**Finding**

- The first candidate/reference execution revealed that the initial manifest
  rotated the beam and source ellipses by 47 degrees but only mirrored the
  close-pair separation. That changed the blend relative to its beam, so it no
  longer represented the declared unresolved truth group. Its approximately
  50% Hebog group-flux error was therefore invalid planning evidence, not an
  algorithm result that may be used for tuning or qualification.
- The invalidated exploratory shards have SHA-256
  `2477409ea0a399d4b3dc080f097887ed9a57f5e3957a8b88ff1eb45e7bcc43bb`
  for Hebog, `9e65e6aafe2529419a0a1cf926aac04905124178c7b81a07ea190e87f0852c2a`
  for released PyBDSF, and
  `1db13cf00527831b3e8db22a9b56816acbcc2812a26aa27a9da6348a2104d084`
  for the compiled pair. They remain diagnostic provenance only.

**Correction**

- Restored the original beam/source orientation while retaining the
  180-degree positional mirror, distinct WCS/background/noise field, and all
  independent seeds. A new red-green test proves the beam-projected close-pair
  separation matches the governed viewed reference geometry.
- Recomputed the recipe identity as
  `2669ad5c7e0883e50b6c82a8d1c66d92a8890df9d8fc7b64a645d6bdf52dedca`.
  This correction occurred before any production-science change or final
  qualification freeze.
- The invalidated run also found reproducible Hebog fit omissions on seeds
  `2026100009` and `2026100165`, while released PyBDSF completed both. Those
  seeds remain valid independently seeded TDD cases, but their frequency and
  paired metrics must be remeasured on the corrected manifest.

**Next**

- Commit the corrected governance boundary, archive the invalidated ignored
  evidence under explicit names, and rerun both implementations before any
  planning-assumption conclusion.

## 2026-08-03 — Diagnosed the corrected paired regression and fixed fit-ineligible deblending

**Plan phase:** Phase 4 scientific recovery and closure

**Evidence**

- Ran Hebog and released PyBDSF 1.14.1 over the corrected 200-image paired
  regression. The candidate, reference, and compiled ignored evidence have
  SHA-256 values
  `f58fec61ab4d29670acf6e49117e30045a90fdc0bce2c5de77f5c96e021544b9`,
  `adeea227878ecb0b412a196a1adf09fdd212fca15fa9b3f187059e1c33f470b0`,
  and `91056642e990f164292af598ac4d9b2bf6f334edfef84aaee44c5cf4301efaf2`.
- Released PyBDSF completed all 200 realizations and Hebog completed 196. On
  the 196 joint successes, both had complete group recovery. Hebog's point
  specificity was 96.75% against PyBDSF's 100%, and catalogue reliability was
  99.69% against 99.76%.
- Hebog retained its stronger results: 0.733% governed catastrophic rows
  against 1.562%, 100% clear-resolved recall against 57.14%, and mean
  unresolved-group errors of 0.056 beam and 5.42% total flux against PyBDSF's
  0.082 beam and 14.17%.
- All four Hebog exceptions were the same `underdetermined-region` outcome:
  the unresolved blend was split into a valid main basin and a five-pixel
  child, which cannot identify a seven-parameter Gaussian. The earlier
  corrected seed `2026100009` completed, confirming its first-run failure was
  caused by the invalid campaign geometry.

**Correction**

- Added an explicit minimum deblended-region area and deterministic merging
  across the strongest shared saddle. The Phase 4 configuration aligns
  detection and deblending at the fitter's seven-owned-pixel minimum, so an
  admitted compact child is structurally fit-capable without discarding any
  parent-island pixel.
- Added an analytic red-green basin test and permanent equivalence regressions
  for seeds `2026100024`, `2026100064`, `2026100165`, and `2026100180`.
  All four now produce complete candidate catalogues.
- Replayed every false point-extension decision on independent regression
  data. Their fitted flux-ratio significances span 2.02--3.38; this isolates
  the remaining difference to the current two-sigma classification policy,
  not deconvolution availability or the campaign geometry.

**Validation**

- The focused deblend, runner-contract, and four-seed equivalence suite passes
  all 49 tests.

**Next**

- Use analytic and independent regression tests to select a conservative,
  community-supported extension decision that is no worse than released
  PyBDSF while preserving Hebog's clear-extension, catastrophic-tail,
  uncertainty, and unresolved-group strengths. Then refresh the complete
  paired evidence before accepting any planning-variance estimate.

## 2026-08-03 — Required high-confidence compact-source extension

**Plan phase:** Phase 4 scientific recovery and closure

**Finding**

- Replayed the standardized ATLAS log integrated-to-peak statistic for all
  1,600 predeclared point sources and 200 predeclared clear extensions in the
  independent paired regression. Point truth ranged from -2.08 to 3.38 sigma;
  clear truth ranged from 17.92 to 23.83 sigma.
- The former two-sigma rule has the documented 2.3% one-sided
  false-extension probability and classified 51 of 1,568 point sources as
  resolved on the jointly successful pre-correction images. Released PyBDSF
  classified all of them as unresolved. This conflicts with the paired
  no-worse decision even though it passes the weaker absolute 95% specificity
  floor.

**Correction**

- Retained the community-used standardized statistic and changed the proposed
  Phase 4 catalogue threshold to five sigma. This is a deliberately
  conservative compatibility policy: a false resolved decision assigns a
  physical size and uses a noise-biased free-fit integral, while independent
  regression leaves more than 12 sigma between the largest point value and
  the smallest clear value.
- Added an analytic TDD case between two and five sigma plus permanent
  independently seeded tests for the largest observed point value and the
  smallest clear value. The threshold remains explicit configuration, so
  alternative workflows can make a reviewed policy choice.
- Recorded the proposal and evidence in the scientific references and plan.
  Named scientific review is still required; no final qualification
  population has been generated or opened.

**Validation**

- `just check`: 618 passed and four expected failures.
- `just test-equivalence`: 26 passed.
- `just test-acceptance`: seven expected failures and no unexpected failure.
- `just test-integration`: 128 passed.
- `just coverage`: 96% branch-aware project coverage; the changed campaign
  configuration remains fully covered and the catalogue path is exercised by
  focused analytic and integration tests.

**Next**

- Run branch-aware coverage, documentation, notebook, and pre-commit checks;
  then refresh the complete 200-image paired regression with both corrections
  before accepting planning assumptions or seeking named approval.

## 2026-08-03 — Refreshed the paired regression after both corrections

**Plan phase:** Phase 4 scientific recovery and closure

**Evidence**

- Ran Hebog commit `49855eba45294278dd2fe709583a093445cf5eba`
  over all 200 governed regression images. All 200 completed successfully,
  including the four former fit-ineligible deblend cases. The candidate shard
  has SHA-256
  `32aacb78733d28cac086ae10596a1d2d1f5e7671d0cc6844c33a0ac87297fa0a`.
- Reused the immutable released-PyBDSF 1.14.1 shard with SHA-256
  `adeea227878ecb0b412a196a1adf09fdd212fca15fa9b3f187059e1c33f470b0`
  and compiled a new pair with SHA-256
  `bff79e0dafd096870460bfc1f6663a84d4f6cb813ea6ab7610b2bd8bee287a96`.
- Both implementations recovered all 6,600 truth groups. Hebog reached 100%
  point specificity and clear-resolved recall; PyBDSF reached 100% and 57.5%.
  Hebog retained the lower governed catastrophic fraction (0.531% versus
  1.547%) and better mean unresolved-blend position and total-flux errors
  (0.056 beam and 5.36% versus 0.089 beam and 14.98%).

**Finding**

- Hebog had 21 unmatched candidates and PyBDSF had 20, so reliability was
  99.6828% versus 99.6979%. The paired positive-as-worse estimate is 0.0151
  percentage points and its one-sided 95% BCa upper limit is 0.1808 points,
  below the proposed 0.5-point margin.
- All 21 Hebog unmatched rows are unresolved near-threshold detections with
  fitted peak SNR 4.34--6.11. A new post-fit cut would tune to one random
  regression-tail candidate and risk real-source completeness. No scientific
  threshold was changed.

**Next**

- Implement and run the maintained endpoint and planning-assumption audit,
  then present the five-sigma policy, margins, sample size, multiplicity,
  stopping rule, and stricter no-worse point-estimate condition for named
  review before generating any final population.

## 2026-08-03 — Verified the paired planning assumptions

**Plan phase:** Phase 4 scientific recovery and closure

**Finding**

- Added a maintained whole-image bootstrap audit that recomputes aggregate
  rates, unresolved-group quantiles, and pooled predeclared-stratum
  uncertainty endpoints. It reports an equivalent per-realization paired
  standard deviation, which is identifiable for candidate-centric and
  nonlinear endpoints where separate discordance and intracluster correlation
  are not.
- The first 50,000-resample audit found 11 conservative provisional bounds and
  nine underestimates. Most underestimates accompany large favourable Hebog
  effects; the original near-equality assumptions therefore understated
  paired variation rather than exposing a hidden Hebog regression.
- Corrected a draft semantic error: one-sigma coverage and normalized
  dispersion were already absolute departures, but the contract applied their
  raw ideals a second time.

**Decision**

- Rounded every underestimated dispersion bound above the observed value and
  used no more than half the independently observed favourable effect for
  planning. No practical margin, scientific gate, or implementation threshold
  changed.
- All 20 revised bounds pass. The audit SHA-256 is
  `0f73113c65cea6f2192538f0e9ee061db50fefd9db87f0a04aaf39c0ad1765f6`;
  the evaluated draft protocol's canonical SHA-256 is
  `a9835face5f940652aeca82c3cf598e3cbb2abd3a87e55e681e663b412490af3`.
  The weakest interval-exclusion power remains 92.2% at 600 images.
- Catalogue reliability and median unresolved-blend position have small
  adverse point estimates but one-sided upper bounds inside their margins.
  The strict no-worse point-estimate rule therefore remains a named-review
  decision, not a trigger for regression-tail tuning.

**Validation**

- Focused non-inferiority and script-boundary tests: 39 passed; the maintained
  calculation module has 100% branch coverage.
- The optimized sufficient-statistic audit reproduces the direct residual
  calculation to floating-point rounding and completes 50,000 resamples.

**Next**

- Complete named review of the scientific policy and paired protocol before
  changing contract status or generating any final population.

## 2026-08-03 — Approved the paired scientific protocol

**Plan phase:** Phase 4 scientific recovery and closure

**Decision**

- Gemma Danks, Data Processing Software Engineer, approved the five-sigma
  high-confidence extension policy, endpoint populations and practical
  margins, corrected absolute-departure semantics, conservative planning
  bounds, 600-image design, whole-image paired BCa intervals,
  intersection-union multiplicity rule, and one-look stopping rule.
- The additional no-worse point-estimate condition was removed before final-
  population freeze. A sign-only gate would fail about half of repeated
  experiments under equality even when the one-sided interval excludes every
  practically meaningful regression. Signed point estimates remain mandatory
  report fields; all interval, absolute-science, and stronger-Hebog gates must
  pass independently.
- Promoted the paired protocol to `reviewed` and restored both the unchanged
  measurement-semantics contract and the five-sigma scientific-gate contract
  to `reviewed-provisional`. This authorizes final-population freeze, not
  generation or result inspection.

**Evidence**

- Re-ran the maintained 50,000-resample planning audit against the complete
  viewed regression pair. All 20 planning bounds remain verified. The
  reviewed audit SHA-256 is
  `af7c6cdfdf55629b77a6960292f523f73f583ec8e09bb407233cda26845ea9b1`;
  the reviewed protocol canonical SHA-256 is
  `1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`.
- The weakest interval-exclusion and governed-decision power remains 92.2% at
  600 images. The power report continues to expose the rejected sign-rule
  probability as a diagnostic so the statistical decision remains auditable.
- Focused scientific-contract and power-model tests: 40 passed.

**Next**

- Freeze the final 600-image population and all execution provenance without
  generating images or inspecting results; then run it exactly once under the
  reviewed protocol.

## 2026-08-03 — Froze the final Phase 4 population

**Plan phase:** Phase 4 scientific recovery and closure

**Decision**

- Froze `phase4-final-paired-qualification-512` with generator version 3 and
  exactly 600 seeds disjoint from every prior Phase 4 population. No image or
  result was generated or inspected.
- Used a distinct WCS, background, invalid region, and correlated-noise
  gradient. A 90-degree source-layout and beam rotation preserves the governed
  blend-to-beam geometry and the reviewed 33-group endpoint structure rather
  than introducing a scientifically different workload after the power audit.
- The population is subject to the reviewed one-look rule. Before opening it,
  record the exact clean Hebog revision, both immutable PyBDSF environments,
  dependency inventories, and unique output paths. A scientific failure does
  not authorize a replacement population.
- Both campaign runners now reject qualification before recipe iteration
  unless the measurement contract, scientific gates, and paired protocol all
  carry their reviewed statuses. Regression planning runs remain available.

**Evidence**

- Recipe SHA-256:
  `15f8f607463f2db4cf4c0eb72255a998784e2d83d3a0d7ebc45eb733f6fbc7db`.
- Complete campaign dataset-record SHA-256:
  `07c736a9bafc79fb298ad1c076fb29b93d88ce9f988f38bba99c94af519d1fcb`.
- Reviewed scientific-contract-set SHA-256:
  `562b648d98eb1d28d65341cfe99c8dba4bd36b8d928d132e6ab6f05bf8d96d79`.
- Reviewed paired-protocol SHA-256:
  `1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`.
- Manifest and campaign-guard tests validate the schema, exact checksums, 600
  unique seeds, cross-manifest seed disjointness, endpoint counts, and rotated
  blend geometry.
- `just coverage`: 764 passed with four expected failures and 95.54%
  branch-aware project coverage. The changed campaign-runtime module reaches
  100% branch coverage in its focused 11-test suite.
- `just check`, strict documentation build, and all pre-commit hooks pass.

**Next**

- Extend the source diagnostic schema with the position-angle differences
  required by the existing gates and implement the immutable final evaluator
  for every paired interval, absolute gate, and stronger-Hebog envelope.
- After that evaluator is tested and frozen, freeze the remaining execution
  identities and run the final population exactly once without tuning.

## 2026-08-04 — Implemented the Phase 4 one-look evaluator prerequisite

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Extended immutable source-pair diagnostics with the fitted and deconvolved
  position-angle differences already required by the reviewed absolute shape
  gates. Old evidence remains readable, while the final evaluator fails closed
  when a required eligible population has no retained angle measurement.
- Moved all 20 aggregate paired endpoint calculations into one shared package
  module used by both the planning audit and final evaluator. This prevents
  population, ratio, quantile, uncertainty, or regression-sign drift between
  design and final decision.
- Implemented the vectorized whole-image paired one-sided 95% SciPy BCa
  evaluator with the reviewed 50,000 resamples and fixed seed. It preserves
  the signed point estimate, treats non-finite bounds as indeterminate, and
  does not apply the rejected point-sign gate.
- Implemented every held-out absolute catalogue, shape, association,
  catastrophic, unresolved-group, and entire-confidence-interval uncertainty
  decision. Individual-source 95th-percentile tails remain report-only under
  their contract; unresolved-group tails remain gates.
- Added named conjunctions for the campaign-measurable stronger Hebog science
  envelopes: complete group recovery, uncertainty availability/calibration,
  unresolved-group errors, clear-resolved recall, and catastrophic tail.
  Serial/Dask invariance and bounded execution remain exact-revision pre-run
  checks rather than being misrepresented as catalogue measurements.
- Added a strict `phase-4-qualification-decision` evidence schema and a
  maintained CLI. It verifies frozen dataset, scientific-contract, protocol,
  implementation, and seed identities; retains primary and secondary failure
  policy; reports secondary endpoints where pinned master completes; and
  refuses to overwrite an earlier decision.
- Kept the final 600-image population ungenerated and unopened.

**Evidence**

- Analytic tests exercise finite and degenerate BCa results, missing
  position-angle inputs, absolute-gate failures, report-only tails, required
  implementation failures, provenance drift, strict evidence round trips, and
  complete primary/secondary/absolute/envelope orchestration.
- The shared planning-audit population and ratio tests continue to pass after
  the extraction, and focused Ruff and Pyright checks pass.
- A dry run on the already-viewed complete post-correction regression campaign
  produced 12 finite passing endpoint intervals and eight indeterminate
  exact-equality endpoints. No endpoint failed its practical margin.
- `just check` passes: formatting, Ruff, Pyright, 650 fast tests, and four
  expected contract failures.
- `just coverage` passes with 778 tests, four expected contract failures, and
  94.86% branch-aware project coverage. The new diagnostic path reaches 100%,
  shared Phase 4 analysis 93%, and final decision module 86%.
- The strict MkDocs build passes.
- The frozen PyBDSF equivalence lane passes: 26 tests.
- All pre-commit hooks pass, including JSON canonical formatting, Ruff,
  codespell, and lockfile validation.

**Deviation requiring review**

- The dry run exposed a pre-existing protocol problem before final opening:
  SciPy BCa returns `NaN` for an all-identical bootstrap distribution. The
  reviewed `indeterminate-fail` rule therefore prevents an endpoint with exact
  Hebog/PyBDSF equality from qualifying. This is documented SciPy behaviour,
  not a scientific regression.

**Next**

- Obtain named pre-opening review of the recommendation to use the exact
  `[point, point]` interval only for a finite point-mass bootstrap distribution
  and retain fail-closed handling for every other undefined result. If
  approved, update the protocol, evaluator, tests, hashes, and review record
  before recording execution identities or opening final data.

## 2026-08-04 — Approved exact finite point-mass intervals

**Plan phase:** Phase 4 scientific recovery and closure

**Decision**

- Gemma Danks, Data Processing Software Engineer, approved the predeclared
  finite point-mass recommendation before any final image was generated or
  inspected.
- An otherwise undefined BCa interval is now exactly `[point, point]` only
  when every bootstrap statistic is finite and exactly equal to the finite
  observed point estimate. The check has no numerical tolerance.
- A near point mass, non-finite distribution, incomplete distribution, or
  every other undefined BCa result remains indeterminate and fails closed.
  No endpoint, margin, sample size, resampling seed, or science gate changed.
- The amended reviewed protocol's canonical SHA-256 is
  `eaa4e30a8d24a299d9f139c89aafc3ea60d424d61ac64f2b3d6fe7178a697dd8`;
  it supersedes the pre-amendment protocol for final execution.
- The final 600-image population remains ungenerated and unopened.

**Evidence**

- TDD covers ordinary finite BCa bounds, exact finite point masses, near point
  masses, non-finite distributions, incomplete distributions, and endpoint-
  decision propagation. The focused protocol and evaluator suite passes 38
  tests.
- Reapplying the amended decision calculation to the same already-viewed
  200-image post-correction regression campaign returns 20 passes, no
  failures, and no indeterminate endpoints. The eight exact-equality endpoints
  each have `[0, 0]`.
- `just check` passes: Ruff formatting and lint, Pyright, 653 fast tests, and
  four expected contract failures.
- `just coverage` passes with 781 tests, four expected contract failures, and
  94.82% branch-aware project coverage. The final-decision module is at 85%.
- The frozen PyBDSF equivalence lane passes 26 tests, and the strict MkDocs
  build passes.

**Next**

- Record the exact clean Hebog revision, immutable released and pinned
  PyBDSF environments, dependency inventories, and unique output paths. Then
  open the frozen final population exactly once under the amended reviewed
  protocol.

## 2026-08-04 — Ran the final Phase 4 one-look qualification

**Plan phase:** Phase 4 scientific recovery and closure

**Completed**

- Recorded the final preflight before opening any population output. It fixed
  Hebog 0.5.0 at `92f5e4cc233b716987a4f65b75c5f1585d977de1`, released
  PyBDSF 1.14.1 at `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`, pinned
  PyBDSF `master` at `c70103be3ae9ae9908286f144e6ce956acc0ce5c`, their
  complete dependency inventories, immutable container digests, reviewed
  contract hashes, and unused output paths.
- Opened the reviewed 600-image population exactly once. Hebog, released
  PyBDSF, and pinned master each completed all 600 realizations. The compiler
  retained all 1,800 records without denominator deletion.
- Resumed the evaluator only after an infrastructure-only stop before any
  endpoint calculation. The provenance guard counted 599 additional noise
  seeds but omitted the governed base recipe. A red regression test exposed
  both the count and exact seed-coverage error; commit `b4b3930` changed those
  checks to use the maintained dataset recipe iterator. The campaign,
  protocol, gates, margins, implementations, and unused decision path were
  unchanged, satisfying the recorded infrastructure-resume rule.
- Applied the one-look decision once to the same compiled campaign. The result
  is an immutable scientific failure, so the controlled Phase 4 performance
  matrix was not run.

**Evidence**

- Preflight SHA-256:
  `48bdf6fb2784aaa13188c566809b8f425685868948fc97c29eac122debe72f0c`.
- Hebog shard: 600 successes, SHA-256
  `9fd4fbca5a59f1ac3cbfd485f228f1835391d1de9a6a20e79ffd92b52c6654ea`.
- Released-PyBDSF shard: 600 successes, SHA-256
  `69eb45466b6d2cdfa929d6199369d3f558a02e18d15cc207377279516a72486f`.
- Pinned-master shard: 600 successes, SHA-256
  `483bae3ba2319c3b5afa26dc29ff4b25d56702d0e7670b67f5c5404454cceddb`.
- Compiled 1,800-record campaign SHA-256:
  `4b5d213a46524498aca465cb03aff87de26dee20f291fe6fbffa0ecab8736f0f`.
- Final decision SHA-256:
  `aca365b4cbfbb220dfa6fc03e7e1ce56c8316d2f4590e803d180553a2e501ce1`.
- Hebog passed 109 of 114 absolute gates. It failed catastrophic-outlier
  fraction (0.005104 versus 0.005), median position (0.02736 versus 0.02
  beam), median peak-flux error (0.02942 versus 0.02), median fitted-axis error
  (0.05029 versus 0.05), and median deconvolved-axis error (0.10340 versus
  0.1).
- One Hebog source in seed `2026110310` was unmatched. The frozen
  complete-match uncertainty construction raised before the joint paired
  statistic could be formed, so all 20 primary and 20 secondary endpoint
  intervals are indeterminate. This fail-closed limitation does not remove
  the five independent absolute-gate failures.
- Released PyBDSF failed 53 absolute gates and pinned master failed 55 on the
  same truth population. Hebog remains substantially stronger overall, but it
  is slightly worse than both references on median position and worse on
  catastrophic fraction.
- The evaluator unit file passes 14 tests. `just check` passes 653 tests with
  four expected contract failures; `just coverage` passes 781 tests with four
  expected failures and 94.82% branch-aware project coverage; the frozen
  PyBDSF equivalence lane passes 26 tests; and the strict documentation build
  passes. The acceptance scaffold retains its seven expected failures.

**Decision**

- Preserve the final population, all shards, and the decision as viewed
  terminal evidence. Do not rerun, replace, tune, or rescore it under amended
  scientific rules.
- Phase 4 remains **not ready** and cannot be declared passed under its
  reviewed exit gate. Its controlled performance matrix is ineligible.
- Final human review must acknowledge the failed one-look decision. Any
  further correction requires a separately reviewed follow-on milestone using
  analytic and independent development/regression evidence; the final
  population may be used only for reporting and diagnosis.

## 2026-08-04 — Diagnosed the final Phase 4 gate failures

**Plan phase:** Phase 4 terminal review and Phase 4R preparation

**Findings**

- Kept the final 600-image population and decision immutable and used their
  retained source diagnostics only to explain the historical failure.
- All 98 Hebog gated catastrophic rows are fitted-axis outliers; 96 are edge
  sources and 94 are SNR-10 sources. Twenty-five carry `fit-at-bound`.
  Reproducing seed `2026110493`, source 16, showed the free centroid pinned to
  the image boundary and the major sigma inflated from the injected 2.04
  pixels to 6.62 pixels. The remaining non-bound edge outliers show a broader
  truncated-profile identifiability problem rather than a single clipping
  defect.
- Separated the position weakness from the shape tail. Hebog's median position
  error is 0.02736 beam against 0.02512 and 0.02511 for released and master
  PyBDSF, and Hebog has the larger error in about 61% of common source pairs.
  The gap appears in every SNR stratum while normalized astrometric bias,
  coverage, and dispersion pass, pointing to estimator efficiency rather than
  a WCS convention error.
- Confirmed that the peak-flux, fitted-axis, and deconvolved-axis medians miss
  absolute community gates while remaining better than both references.
  Hebog is genuinely worse on catastrophic fraction, position median/tail,
  95th-percentile integrated-flux error, and the fitted-axis tail against at
  least one reference. These outcomes must be fixed without trading away
  Hebog's stronger completeness, flux medians, deconvolution, uncertainty,
  blend, deterministic, or bounded-execution results.
- Traced the paired indeterminacy to shared input construction: one unmatched
  source makes the uncertainty summary raise before any endpoint statistic is
  formed, causing all 20 primary and 20 secondary endpoints to fail together.
  This evaluator composability defect did not cause the five independent
  absolute-gate failures.
- Reviewed Condon's elliptical-Gaussian error treatment, Aegean 2.0's
  correlated-noise and priorized-fitting approach, PyBDSF's fit/flag path, and
  radio source-finding challenge recommendations. The evidence supports
  testing a data-selected beam-constrained/free nested model and explicit
  identifiability checks before adding a more complex correlated-noise point
  estimator.

**Plan change**

- Added a separately governed Phase 4R milestone. It first repairs endpoint
  isolation and creates a direction-aware registry for every gated and
  report-only metric, then adds independent edge/corner and efficiency red
  tests, performs predeclared fit-model/background/support/noise ablations,
  and requires no-compensation dual-reference non-inferiority on every metric
  and governed stratum.
- The milestone permits one new qualification only after the implementation,
  metric directions, practical margins, power, and stopping rule receive
  named review and are frozen. It does not rerun, rescore, replace, or convert
  the terminal Phase 4 result.

**Next**

- Obtain named review of the Phase 4 terminal disposition and Phase 4R
  protocol. If approved, begin with TDD for endpoint isolation and
  parameter-specific fit diagnostics before changing scientific fitting
  behaviour.

## 2026-08-04 — Authorized Phase 4R and isolated missing endpoints

**Plan phase:** Phase 4R, Step 1 — evidence contract

**Decision**

- Gemma Danks, Data Processing Software Engineer, approved the terminal Phase
  4 disposition and recommended Phase 4R development direction. The approval
  does not reopen or rescore the final campaign and does not pre-approve a
  future qualification population or its exact numerical protocol.

**Completed**

- Changed paired uncertainty summaries to retain conditional sufficient
  statistics for available metric values. Missing matches and residuals remain
  visible in completeness and uncertainty-availability endpoints instead of
  erasing unrelated calibration evidence.
- Changed unresolved-group error summaries to retain `NaN` only for the
  unavailable group value while the separate group-completeness endpoint
  records the miss. Retained group position and flux errors remain
  independently calculable.
- Added TDD cases proving that one missing individual source or unresolved
  group no longer makes all 20 paired decisions indeterminate. The affected
  availability/completeness decision fails while unrelated binary, group, and
  uncertainty decisions remain determinate.
- Added a strict, versioned Phase 4R registry for 35 independently governed
  completion, catalogue, association, classification, error, uncertainty,
  and tail metrics. It freezes each population, unit, direction, ideal,
  absolute role, stratum rule, and equal provisional resolution against both
  PyBDSF references; no metric can compensate for another.
- Did not apply the repaired evaluator to the final Phase 4 campaign; its
  immutable failed decision remains the only qualification result for that
  population.

**Evidence**

- Focused red tests failed under the all-or-nothing input construction, then
  passed after the conditional summaries were implemented.
- The focused Phase 4 contract and decision suites pass 35 tests.

**Next**

- Add parameter-specific fit diagnostics and freeze independent edge/corner
  regression cases before changing the fitter.

## 2026-08-04 — Froze Phase 4R diagnostic inputs

**Plan phase:** Phase 4R, Step 2 — independent failure evidence

**Completed**

- Added parameter-specific fit diagnostics: selected model, exact bound
  parameters, normalized distance to every bound, scaled information-matrix
  condition, visible fitted-model fraction, retained pixel count and bounds,
  and a typed fallback-reason slot.
- Added an explicit restoring-beam covariance to compact measurement geometry
  and kept it distinct from the noise-correlation covariance even where the
  current governed image model gives them equal values.
- Froze a 20-realization development matrix and a 100-realization
  confirmation-only regression matrix before changing fit selection. The
  matrices use disjoint seeds and transformed source placement, beam/noise
  orientation, WCS, and RMS gradients while covering every governed SNR and
  shape stratum, edges/corners, invalid pixels, and an unresolved blend.

**Evidence**

- The parameter-specific boundary test failed first because the diagnostics
  exposed only one undifferentiated boolean. The restoring-beam geometry test
  likewise failed before the explicit covariance was added.
- The focused fitting, astrometry, moment, and dataset suites pass 137 tests.

**Next**

- Add noiseless edge/corner validity tests and implement the independently
  selected beam-constrained/free nested fit without consulting the terminal
  Phase 4 population.

## 2026-08-04 — Selected the Phase 4R compact fitting candidate

**Plan phase:** Phase 4R, Steps 2–3 — analytic failures and fitting ablations

**Completed**

- Added noiseless beam-shaped edge/corner and clear-extension tests plus a
  frozen development regression for the low-SNR extended edge failure.
- Implemented nested free-elliptical and restoring-beam-constrained SciPy
  fits. Physical bound contact and ill conditioning reject the free candidate;
  a beam-centroid/free-shape retry preserves measurable edge extension.
- Retained selected and rejected model identities, exact bound parameters,
  condition, footprint, point-estimator identity, fallback reason, and
  retained geometry in scheduler-safe diagnostics.
- Corrected amplitude/integrated-flux covariance propagation so the shared
  fitted amplitude is not counted twice in the extension statistic.
- Completed the predeclared background, pixel-support, and point-estimator
  factorial. Selected a fixed-zero residual background, owned-region support,
  and exact correlated-noise GLS capped at 512 pixels. Larger regions take an
  explicit diagonal/sandwich fallback rather than dense unbounded work.
- Preserved raw fitted total for unresolved-group diagnostics before applying
  peak-as-total to individual unresolved catalogue rows. Rejected an
  island-pixel-sum group ablation because threshold truncation failed the
  existing median-flux gate.

**Evidence**

- The selected 20-realization candidate completed every image, matched all 240
  individual sources, and produced zero catastrophic rows. It beat both exact
  PyBDSF references on overall position, peak, integrated-flux, fitted-axis,
  and deconvolved-axis medians and 95th percentiles.
- Hebog's unresolved-blend median was 0.04663 versus 0.05247 for both
  references. Its 0.13150 tail was 0.01718 worse than the references and
  remains inside the predeclared 0.02 practical margin.
- One final-seed 5-sigma noise candidate gave 99.62% development reliability,
  0.38% below the references and inside the predeclared 0.5% resolution.
- Focused fitting, astrometry, campaign, product-reader, runner, and recovery
  tests pass 85 cases; the fitting and Phase 4R recovery subset passes 46.

**Next**

- Freeze the implementation revision, run the 100-realization confirmation
  once, and evaluate every registered metric and applicable stratum against
  both references before requesting the later named qualification review.

## 2026-08-04 — Preserved the exact Phase 4 fitting oracle

**Plan phase:** Phase 4R, Step 4 — candidate freeze and validation

**Completed**

- Made compact model selection an explicit scientific policy. Ordinary
  callers retain the Phase 4 `free-only` estimator; the governed Phase 4R
  campaign pins `beam-or-free` alongside its fixed background, owned support,
  and bounded correlated-GLS choices.
- Added a regression test for the default and restored the exact compact
  catalogue equivalence gate that exposed the previously implicit behavior
  change.
- Repeated the frozen 20-realization development candidate under the explicit
  configuration identity. Every realization diagnostic is exactly equal to
  the selected evidence, with no failures; only the execution-configuration
  digest changed to include the newly explicit policy.

**Evidence**

- The focused fitting, runner-configuration, and exact compact-catalogue
  suites pass 61 tests.
- `just check` passes Ruff, Pyright, doctests, and 688 fast tests;
  `just test-equivalence` passes 26 tests; `just test-integration` passes 128
  tests; and branch-aware project coverage is 95%. The strict documentation
  build and the complete push-stage pre-commit suite also pass. The acceptance
  lane retains its seven planned expected failures and has no unexpected
  failure.

**Next**

- Complete the full scientific and quality lanes, commit the frozen
  candidate, and run the confirmation-only regression exactly once.

## 2026-08-04 — Archived failed Phase 4R confirmation attempt one

**Plan phase:** Phase 4R, Step 4 — regression confirmation

**Completed**

- Froze the selected candidate at exact local commit `27edde3` and ran the
  100-realization confirmation matrix exactly once. Hebog completed 98
  realizations; two retained a typed one-fit omission. Both exact PyBDSF
  references completed all 100 identical images.
- Compiled all three immutable shards under
  `benchmark-results/phase-4r/regression-compiled.json`. The failed Hebog
  attempt remains evidence and is ineligible for replacement, rescoring, or a
  partial-row aggregate pass.
- Did not inspect either failed realization's pixels, truth, or intermediates.
  An independent analytic test instead exposed the generic model-selection
  class: a failed smaller beam model could currently discard a valid,
  identifiable free fit.
- Added a reproducible freezing utility and froze recovery iteration two before
  another production change: 40 viewable development seeds beginning at
  `2026140001` and 100 confirmation-only seeds beginning at `2026150001`.
  These sets are mutually disjoint and disjoint from both earlier Phase 4R
  matrices.

**Evidence**

- `regression-hebog.json` records 98 successes and two
  `IncompleteCompactCatalogueError` failures; each PyBDSF shard records 100
  successes and zero failures.

**Next**

- Commit the new frozen inputs, then implement the independently red
  valid-free/failed-alternative selection test and evaluate the corrected
  candidate only on the new development matrix before opening its new
  confirmation population.

## 2026-08-04 — Recovered Phase 4R development availability and blend flux

**Plan phase:** Phase 4R, Steps 3–4 — recovery iteration two development

**Completed**

- Preserved a valid identifiable free fit when the smaller beam alternative
  fails, removing the generic omission class found after confirmation attempt
  one.
- Changed a physical-bound retry to use the independent intensity-weighted
  moment centroid. The previously missed viewable edge source moved from
  0.559 to 0.314 beam from truth without widening the association rule.
- Added bounded three-sigma restoring-beam aperture photometry with discrete
  beam normalization over exact valid, image-visible, non-competing support.
  Kept it distinct from fitted-Gaussian, owned-pixel, and Rapthor catalogue
  flux semantics.
- Rejected a BLOBCAT-style threshold-volume correction because its blend tail
  remained 0.14741, and rejected direct thresholded pixel sums because their
  0.19168 tail was worse. No empirical flux scale was introduced.

**Evidence**

- The focused fitting, catalogue-schema, campaign-runner, and Phase 4R
  regression suites pass 120 tests.
- The 40-realization viewable candidate completed and matched every governed
  group, with perfect availability and zero catastrophic rows. Its
  unresolved-blend median/tail flux errors are 0.04788/0.10243 versus
  0.04830/0.11301 for both PyBDSF references.
- Hebog is better or equal on 20 of 21 overall paired endpoints and 13 of 14
  overall distribution metrics. The two opposite finite-sample signs are
  0.00042 beam for group-position median and 0.054 degree for
  deconvolved-angle tail, far inside their predeclared 0.01-beam and 1-degree
  resolutions.

**Next**

- Complete the direction-aware Phase 4R evaluator, freeze the exact candidate
  commit, and run the second confirmation population once.

## 2026-08-04 — Completed Phase 4R no-compensation governance

**Plan phase:** Phase 4R, Steps 1 and 4 — metric evaluation prerequisite

**Completed**

- Added a strict Phase 4R decision schema and command-line evaluator covering
  all 35 registered metrics, both exact PyBDSF references, and every
  applicable overall and governed-stratum population independently.
- Made implementation completion, conditional missingness, point decisions,
  one-sided paired BCa intervals, absolute gates, and stronger-Hebog envelopes
  explicit machine-readable constituents. No metric can compensate for a
  failed metric elsewhere.
- Replaced an unstable exact-sign development rule with the already approved
  per-metric practical-resolution rule. Qualification retains the one-sided
  paired upper-limit requirement.
- Corrected the noisy-campaign absolute-role mapping. Noise-limited position,
  flux, shape, and angle error distributions remain mandatory reports and
  dual-reference gates; strict absolute accuracy remains in analytic/noiseless
  and exact-product tests. Sample-limited uncertainty intervals cannot be
  promoted into gates.

**Evidence**

- Focused evaluator, contract, fitting, astrometry, evidence, and runner tests
  pass 190 cases; Ruff and Pyright pass the changed Python surface.
- The 40-realization viewed development dry run produced 450 independent
  Hebog/reference decisions with no metric failure after the separate
  bounded-context position correction. Hebog completed every realization.
- The raw Hebog median position/peak errors are 0.02866 beam and 0.02682,
  better than released PyBDSF at 0.02909/0.03391 and pinned `master` at
  0.02909/0.03391. Those noise-limited medians miss the legacy
  exact-reference 0.02 limits and are retained as report-only observations.
- Two development edge normalized-bias intervals remain red despite central
  estimates inside the allowed range. The confirmation and powered
  qualification populations must decide whether these are sampling variation
  or a persistent calibration issue.

**Next**

- Validate and commit the independent bounded-context position estimator,
  rerun the complete development evidence at exact frozen revisions, then
  open the already frozen second confirmation population exactly once.

## 2026-08-04 — Corrected the Phase 4R regression decision stage

**Plan phase:** Phase 4R, Step 4 — confirmation evaluation

**Completed**

- Froze the scientific candidate at exact local commit `86e7e02` and reran
  the 40-image development matrix in Hebog, released PyBDSF 1.14.1, and
  pinned PyBDSF `master` environments. Every implementation completed every
  realization and all 450 comparative point decisions passed.
- Opened the pre-frozen 100-image confirmation population exactly once. All
  three implementations again completed all realizations; no intermediate
  scientific row was inspected before the complete campaign was compiled.
- Preserved the first decision, which exposed that regression incorrectly ran
  the qualification-only BCa interval rule. Added a failing stage-contract
  test and corrected regression to use the registry's declared point-margin
  rule without changing any campaign row, metric, margin, or contract.

**Evidence**

- Exact development Hebog/reference/compiled/decision evidence SHA-256 values
  are `e28323507deba8aa645fbffd45b756aada65866dc2868de87ada1989cca7cdd8`,
  `2b6c09af60442b5551557056c00790b67781cf24aa4ffad65916b37e097fd173`,
  `9f66def0a1aff76b489cb79f9ecc4b43d08daa3651e9979f6170418d7d7eddcf`,
  `65a1a0effe6712a82fd9c8a61ae33b293bd64fc2bb6a87e809267ccd8b106b24`,
  and `a19cef631b05752492f657e8d18d330286d9b85c43361cc5b1f6cd13fa5daf73`.
- Confirmation Hebog/released/master/compiled evidence SHA-256 values are
  `bf11f54793a46a18b4f5e66564ca47f205ef377dec7d0012a6d887e573f89024`,
  `a55b3a69880d6a4199f68ece577b327cc78f9259ed4999231ec16ee9777b0878`,
  `2a2e880914b5b2c7c4affd9ecfabef374308fe76a9277b3b11c506d700b8da80`,
  and `6d2ed5f8c3695582ed8d922bef3c29b67cc064b92b6c8b1becf0dcd2a1568b86`.
  The preserved pre-correction decision SHA-256 is
  `bb39bb6be81596a3a5d0ed95a2400f2d22588b96ee2553fb9a8ffd9fc12b6fb9`.
- The focused evaluator suite passes 21 tests; Ruff and Pyright pass.

**Next**

- Commit the generic stage-rule correction, rescore the same immutable
  confirmation evidence, and address only genuine point/absolute failures
  through independent analytic and development evidence.

## 2026-08-04 — Archived failed confirmation and froze tail development

**Plan phase:** Phase 4R, Step 4 — rare shape-tail recovery

**Completed**

- Rescored the unchanged iteration-two confirmation campaign after the
  committed stage-rule correction. The corrected result passes 444 of 450
  comparative decisions and fails the catastrophic fraction against both
  references overall, for marginal shapes, and at SNR 15.
- Diagnosed only aggregate, identity-free evidence. Ten of 1,200 eligible
  Hebog matches are catastrophic, versus two for released PyBDSF and five for
  pinned `master`; eight Hebog failures are deconvolved-axis-only and two are
  fitted-axis-only. Hebog remains better on the corresponding medians and
  95th percentiles.
- Added a red disjointness test, then froze a 200-realization viewable tail
  development matrix before any further production fitting change. The new
  matrix is disjoint from all earlier Phase 4R seeds and retains the same
  reviewed SNR, morphology, edge, WCS, beam, and correlated-noise design.

**Evidence**

- Corrected confirmation decision SHA-256:
  `86763b8d25b693066afc9d9b00e2fbd5ca2f084ad8560183711456c90fadb975`.
- Frozen development manifest/recipe SHA-256 values:
  `06ad23df2a747ea33136c4e226a1400c231ac76ea1422adb40979e01dbfd884a`
  and `d34919b359ec865601150faa8455d52ae02632a6d6a72431e1b69172d765d91a`.
- The focused frozen-manifest contract passes.

**Next**

- Run the exact candidate and both references on the new viewable matrix,
  reproduce the rare shape tail independently, and add analytic red tests for
  the generic failure before selecting the smallest correction.

## 2026-08-04 — Authorized one powered Phase 4R qualification

**Plan phase:** Phase 4R, Steps 4 and 5 — tail decision and named review

**Completed**

- Ran the unchanged candidate and both exact references on all 200 frozen
  tail-development realizations. Every implementation completed every image.
- Confirmed that Hebog is better on the independently reproduced catastrophic
  tail: 9/2,400 eligible matches versus 19/2,400 for released PyBDSF and
  30/2,400 for pinned `master`. The complete evaluator passes all 450
  dual-reference decisions and the absolute catastrophic gate.
- Reviewed the remaining uncertainty results against Condon, Aegean 2.0,
  correlated-noise bias analysis, general maximum-likelihood photometric bias,
  and the ASKAP/EMU challenge. The observed low-SNR effects are expected, the
  normalized-residual dispersions are near unity, and a new correction chosen
  only after the confirmation crossing is not scientifically justified.
- Recorded Gemma Danks's named approval to preserve the failed confirmation
  and advance the unchanged candidate to exactly one powered qualification.
  No metric, margin, source row, or qualification rule changes.

**Evidence**

- Candidate/released/master/compiled/decision SHA-256 values are
  `3749e52eb9bcb1d3ba101724646cc43c0c6ae911710530df71effc01368aa9fd`,
  `a2ed5f9fbba545c8406303366b4d588eb2d4bc56d0ba2768dd9f36ffe8937053`,
  `6f4bf40983477f2dbb803e5f2a35e5ffd059f4d6eea7ed5f0ef152dd20a47ee2`,
  `46a8994448556a852cc9d5e631123f08f64ad24bb1925d4aa2140862ba5dc9ac`,
  and `7f19261a689c97f284801ebd81f30f4bb51e6cd68b7eb9130b0f6c54a3d946f9`.
- All 450 comparative point decisions pass; the absolute catastrophic rate is
  0.00375 against its unchanged 0.005 maximum.

**Next**

- Commit the named review before creating any qualification population, then
  freeze and execute the single 600-realization Phase 4R qualification.

## 2026-08-04 — Froze the sole Phase 4R qualification population

**Plan phase:** Phase 4R, Step 5 — one-look qualification freeze

**Completed**

- Extended the existing refusing-overwrite Phase 4R freeze tool with an
  explicit qualification mode and reviewed field overrides.
- Added a red/green contract proving that qualification horizontally reflects
  source, association, and invalid-region coordinates while consistently
  reflecting source, beam, and correlated-noise covariances and setting the
  reviewed disjoint WCS and background.
- Froze 600 new realizations only after named review commit `4688081`. Added a
  repository contract proving that no seed appears in any earlier Phase 4 or
  Phase 4R manifest.

**Evidence**

- Qualification manifest SHA-256:
  `93f2d9f876b9b3f58df09ad64796e39ed404980a14f7c4542f0ae2b3120c42e4`.
- Canonical qualification recipe SHA-256:
  `82870d14dbe163c1d1ca79d0b163bc69c406ed2288da3cf489ebdb03989de5fc`.
- No candidate or reference qualification output existed at freeze time.

**Next**

- Validate and commit the immutable population before opening it, then execute
  the unchanged candidate and both exact PyBDSF references exactly once.

## 2026-08-04 — Repaired Phase 4R qualification preflight

**Plan phase:** Phase 4R, Step 5 — qualification prerequisite

**Completed**

- Attempted to start the one-look candidate run. The qualification guard
  failed before recipe iteration because it indexed the Phase 4R registry as
  a legacy `contract_id`. No image, evidence row, or output file was created.
- Added red tests, taught preflight to recognize a `registry_id`, and require
  exactly the reviewed Phase 4R registry in addition to the measurement and
  gate contracts. A development-only registry now fails closed.
- Promoted only the registry's review metadata to
  `reviewed-qualification`/`qualification-reviewed`, reflecting the named
  approval already recorded at `4688081`. Metric definitions and margins did
  not change.

**Evidence**

- Focused runtime/contract suite passes 34 tests before the additional
  development-only rejection case; Ruff and Pyright pass.
- Reviewed registry file SHA-256:
  `f1bcbbb6d1d216bdc5271c45a1e64789b1c8928a98bd4927f7e707d0318dd0b5`.
- Ordered qualification contract-set SHA-256:
  `d27dace66ca86fb0abf30b6e5ab37215b6007d1fd3a58606c51b58a003c6d063`.

**Next**

- Run complete validation and pre-commit, commit this prerequisite, verify the
  qualification output path is still absent, and restart the sole execution.

## 2026-08-04 — Preserved failed Phase 4R qualification attempt one

**Plan phase:** Phase 4R, Step 5 — qualification outcome and recovery boundary

**Completed**

- Ran the exact candidate at commit `f28bda9` over the sole frozen
  600-realization qualification population. It completed 599 images and
  retained one typed `IncompleteCompactCatalogueError` on seed `2026170473`;
  the attempt therefore failed the non-negotiable implementation-availability
  gate before aggregate scoring.
- Inspected only failure status and fitting diagnostics. Both nested models
  converged at an image-centroid bound; the smaller model retained finite,
  well-conditioned non-centroid evidence, but the existing moment-centred
  retry refused the whole at-bound initializer. No partial aggregate metric
  was inspected, no row was omitted, and the failed campaign was not rescored.
- Added a red generic noisy-edge test and froze 200 new development plus 200
  new confirmation-only seeds before evaluating a correction. Both new
  populations are disjoint from every earlier Phase 4R population.
- Recorded that another qualification is not automatic. A passing unchanged-
  candidate regression must be followed by new named review and a separately
  frozen, disjoint replacement population.

**Evidence**

- Failed candidate evidence SHA-256:
  `c9bb55ab4a446f5cf6b25185cfdc8f87cc0e56cdca8f185dae53d0fe9f20f761`.
- Development manifest/recipe SHA-256 values:
  `118224a11229cb230f43be3c00d40e6d70c53536ad0830941a343e7af3edcf14`
  and `f07f450e266367c50614b9e67caf7131a0c75bb7bd7798c497d9170471f7bead`.
- Regression manifest/recipe SHA-256 values:
  `f84f9405a55e9c124502a88855fffcfe18c4f6fcd3beb4cda2f9c0d1ec88c7d6`
  and `3879a7a1890ab4791bb6508d904779dbca00051bb4d9012882964875a0e7655c`.
- The fitting, catalogue-construction, and dataset-contract subset passes 134
  tests after the red test demonstrated the original omission.

**Next**

- Implement the smallest bounded retry correction, run the complete viewable
  development matrix and scientific/quality lanes, freeze that candidate,
  then open the new confirmation population exactly once.

## 2026-08-04 — Recovered edge availability and preserved confirmation three

**Plan phase:** Phase 4R, Steps 4–5 — recovery iteration three

**Completed**

- Implemented a fail-closed edge retry that accepts a converged beam template
  only when centroid coordinates are its sole physical bound contact; the
  resulting free-shape retry must still pass every existing numerical and
  identifiability check.
- Used the viewable development population to replace its inward-biased raw
  moment centroid with the existing analytic one-sided truncated-moment
  correction. The first candidate passed 448/450 comparisons; the selected
  candidate at `1065182` completed all 200 images and passed all 450.
- Opened the 200-image confirmation exactly once after committing the selected
  candidate. Hebog and both exact PyBDSF references completed every image.
  The decision passes 447/450 comparisons but remains failed on catastrophic
  fraction in SNR-15 against both references and marginal shape against
  released PyBDSF. No confirmation row identity was inspected.
- Preserved the complementary aggregate result rather than tuning again:
  Hebog has eight SNR-15 deconvolved-axis and two SNR-10 fitted-axis
  catastrophic rows; released PyBDSF has four SNR-10 rows and pinned `master`
  has fourteen. Across development plus confirmation the counts are 22/4,800,
  24/4,800, and 43/4,798 respectively, with every combined practical margin
  satisfied.
- Completed both exact qualification reference legs. Released PyBDSF and
  pinned `master` completed all 600 images, including Hebog's failed seed.
  Materialized the immutable failed decision without inspecting survivor-only
  aggregates: all 450 comparisons and the absolute-science gate are
  indeterminate because required paired evidence is incomplete.
- Added a generic fail-closed evaluator prerequisite so incomplete paired
  campaigns retain every governed decision but skip BCa resampling that
  cannot change the failed outcome.

**Evidence**

- Development candidate/released/master/compiled/decision SHA-256 values:
  `92467213582240ec64f0d0fdddca034648ac2f6a93580863147df28fccf38f8a`,
  `e26cd974ce282eb5986f91ddbee33c5a82f0e863592c98a49fdcb7c575fdbcd4`,
  `3103b99318e9f7e540c38de503cc6b81171b0bd0240236b2e389a6cc6a51583d`,
  `38e59fe2f3fd7c570581aa4f2114bbea72a058fd43a8720e86a6098754ebeb3e`,
  and `8d57fa987bd28435dc5ca24a82ffaa988c322ee96ce1b9886fb9cef5f6ccf12d`.
- Confirmation candidate/released/master/compiled/decision SHA-256 values:
  `dcd7a95640f80dd60e1c8ec70eaa01d31d36fa8b36fe7abeefcbed250c49aa87`,
  `3b62abc5d9b3d1cb44bc9b7bf04527d609402cde53ecb571d288656d0c182686`,
  `f5a458c93f4b32d217afd251a0541f39b5abeb96843b6ad12c71c7e50deb0d65`,
  `742d97c4f00b6d17816e479e4b073ea1f86119db97f320014a233ad1d44ce961`,
  and `2f667110ffcc436e08332a6a0fe3e535e1415fe24d54881d042d04b1401c3e55`.
- Qualification released/master/compiled/decision SHA-256 values:
  `20741c868caabede59eb131ceb1e9a42f77e2f2b76c4ba62b39f4edb23aa1c68`,
  `714c6e8ca37972339468d42b6557872b3c912a53393e3007e1b71b92b77c5dcd`,
  `506bf236b3341b0d2e2b3e4c5a656b9d04b8df33610574782ae7451da79468c2`,
  and `8967e510be531defb38806e656ecf987419bc1806e32652ed87c6e358568daf7`.
- Branch-aware project coverage is 94.05%; 26 equivalence tests, 128
  integration tests, 58 fitting tests, the acceptance lane, strict docs, and
  the complete pre-commit suite pass.

**Next**

- Obtain named review of the recommendation to keep candidate `1065182`
  unchanged and authorize one separately frozen 600-image replacement
  qualification. Do not freeze or run that population before approval.

## 2026-08-04 — Authorized one Phase 4R replacement qualification

**Plan phase:** Phase 4R, Step 5 — replacement qualification governance

**Completed**

- Gemma Danks, Data Processing Software Engineer, approved preserving failed
  qualification attempt one and failed confirmation three while advancing
  unchanged candidate `1065182` to exactly one replacement qualification.
- Bound the authorization to one separately frozen 600-image population with
  disjoint seeds and vertically transformed field geometry. All 35 metrics,
  margins, absolute gates, paired upper-bound rules, and implementation-
  completion semantics remain unchanged.
- Recorded the decision before the replacement manifest, seeds, or outcomes
  existed.
- Froze `phase-4r-qualification-replacement.json` with 600 disjoint seeds and
  the approved vertical source, association, invalid-region, beam/noise, and
  gradient transformation plus new sky, WCS, and background fields. No
  implementation output existed when it was frozen.

**Evidence**

- Manifest, canonical recipe, and dataset-content SHA-256 values:
  `11c68f2d390416b0345048a825ed8da35e3a389b9118571b72b10d9108107df3`,
  `e104ec6d703bfa876ebdfd1bad3b39c0b0dba341afa6c57fbf32e3605c32d3d0`,
  and `1e566660eed6a995c55f399a5f1579c70b2ffe34cbb81cd2ad6dc67eaa07dee8`.
- Focused freezer and frozen-dataset contracts pass, including exact
  600-realization cardinality and disjointness from every earlier Phase 4/4R
  seed.

**Next**

- Commit the frozen replacement before executing Hebog or either exact PyBDSF
  reference.

## 2026-08-04 — Closed Phase 4R without scientific passage

**Plan phase:** Phase 4R, Step 5 — replacement qualification decision

**Completed**

- Opened the sole approved replacement once with exact scientific candidate
  `1065182` and both pinned PyBDSF environments. Hebog and released PyBDSF
  completed 600/600; pinned `master` completed 599/600 and retained seed
  `2026200549` as a typed non-positive-source-flux reference failure.
- Corrected the generic evaluator to honor the frozen policy distinction:
  Hebog failures fail qualification before resampling, while reference
  failures remain visible in implementation completion and other metrics use
  their explicitly conditional retained values. A TDD regression test covers
  the boundary.
- Ran the full 50,000-resample, one-sided paired BCa decision. It passed 446
  of 450 dual-reference metric/stratum comparisons and 106 of 107 absolute
  gates, but the conjunctive decision is false.
- Preserved four catastrophic-outlier failures: SNR 15 against both
  references, marginal shape against released PyBDSF, and the overall
  released-reference confidence bound. Preserved the failed absolute SNR-10
  declination-uncertainty-bias interval and resulting uncertainty envelope.
- Closed Phase 4R as a terminal non-passing milestone. Did not run the
  controlled performance matrix because scientific passage is its explicit
  prerequisite. No Phase 4 release, equivalence, or speed claim is made.

**Evidence**

- Candidate/released/master/compiled/decision SHA-256 values:
  `4b04976ab979a1d4850023994da99f7e0e4b791cc8d8d06e60b33f85eb8c7739`,
  `f1499e78f79a0435230dbca5564c93e028ba12aa94449d889ecd4066b9debb37`,
  `0e9af355ef9b3ecacbe80eab8c75b22be0eb10ac94f659ad31b7b4cb34ec1a96`,
  `3387df580c187b7345a2cafbaa18c343e6fbbceb74386e04188753cf25c96ef4`,
  and `e18c7ed66a2aa9b6f83908bf8e90d13413c9ff7d54f737321f839f9cece9b125`.
- Overall catastrophic rate is 0.003333 for Hebog and 0.001528 for released
  PyBDSF. The 0.001805 point regression is inside the 0.0025 margin, but its
  upper confidence bound is 0.003194. At SNR 15 Hebog is 0.01 versus 0.0 and
  0.000556 for released and pinned `master`.
- The SNR-10 declination uncertainty-bias point is 0.113723, while its 95%
  interval `0.067437`--`0.160010` crosses the reviewed `[-0.15, 0.15]` gate.

**Next**

- Obtain human acknowledgment of the terminal result. Any further scientific
  recovery requires a newly governed milestone using only new development and
  regression evidence; Phase 4R does not authorize another qualification.

## 2026-08-04 — Stabilized compact science for Phase 5 development

**Plan phase:** Phase 4S — compact-science stabilization and Phase 5 start gate

**Completed**

- Preserved the terminal Phase 4R evidence and added a separate stabilization
  milestone with distinct Phase 5 development and final release gates.
- Made governed classification strata authoritative over same-named legacy
  validation strata. New campaign diagnostics no longer place a source in
  both clear- and marginal-resolution populations.
- Added manifest-derived endpoint population audits and dependence-robust
  familywise power reporting. The audit records that the replacement contained
  13 association groups, 12 individually resolvable sources, and four point
  sources per image rather than the historical contract's 33, 32, and eight.
- Propagated free-fit shape covariance through WCS and beam deconvolution.
  Added fully resolved, major-axis-only, unresolved, and unavailable states;
  the existing five-sigma extension confidence level is applied independently
  to each axis, and its value is included in campaign configuration identity.
- Preserved a significant major-only axis through internal FITS and Rapthor's
  `DC_Maj` without publishing an unidentifiable minor axis or position angle.
- Replaced the bound-contact centroid/covariance mismatch with a widened
  context-likelihood retry whose point estimate and covariance come from the
  same estimator.

**Evidence**

- The corrected replacement population audit reduces estimated marginal
  point-specificity power from about 94.5% to 76.9%; future qualification must
  fail closed unless declared group counts match the manifest.
- The representative viewed SNR-15 seed `2026200085` is no longer
  catastrophic. Temporary regression reruns of all 18 previously failing
  members show zero remaining catastrophic rows under the five-sigma axis
  policy. These are viewed regression diagnostics and do not alter Phase 4R.
- The 20 worst viewed SNR-10 declination residuals are numerically unchanged:
  they already used a consistent free-context estimator. The old point
  estimate remains inside its absolute gate; the future larger and more varied
  campaign owns the confidence crossing.
- The final unit lane passed 748 tests, integration passed 130, and non-slow
  equivalence passed 26. The portable coverage lane passed 878 tests with
  94.06% branch-aware project coverage. Focused Phase 4R equivalence and the
  complete governed correlated-noise calibration regression passed; the latter
  took 348.65 seconds. Ruff, Pyright, the fast handoff gate, and the strict
  documentation build also passed. Contract and acceptance placeholders remain
  explicitly expected failures rather than silently passing scenarios.

**Next**

- Begin Phase 5 multiscale development against the stabilized compact API.
- Before compact qualification or Rapthor cutover, obtain external
  radio-astronomy review, freeze one manifest-powered and jointly powered
  unseen population, run both exact PyBDSF references, and pass the controlled
  performance/scalability matrix.

## 2026-08-05 — Made Phase 4S qualification the next blocking milestone

**Plan phase:** Phase 4S — qualification-first checkpoint

**Decision**

- The project owner requested one more unseen compact qualification before
  adding multiscale behaviour, prioritizing confidence in the scientific
  baseline over starting substantive Phase 5 implementation immediately.
- Phase 5 preparation may continue through analytic tests, interfaces,
  filter-bank research, bounded-memory design, and independent development
  data. Changes to compact science or Rapthor-facing behaviour remain frozen
  until the Phase 4S one-look decision is known.
- The qualification must be pre-opening reviewed, manifest-powered,
  disjoint from all earlier populations, and executed exactly once against
  Hebog, released PyBDSF, and pinned `master`. Historical Phase 4 and Phase 4R
  evidence remains immutable.

**Next**

- Audit the current tooling against the Phase 4S co-primary-family, joint-power,
  population, and one-look requirements.
- Prepare the new contracts, generator population, reference identities, and
  project-owner-authorized expert review without generating qualification
  output.

## 2026-08-05 — Completed the Phase 4S expert pre-opening science review

**Plan phase:** Phase 4S — qualification-first checkpoint

**Decision**

- At the project owner's explicit request, Codex performed the pre-opening
  radio-astronomy review. The result is recorded as an AI-conducted expert
  literature and evidence synthesis, not independent human or institutional
  sign-off. The owner waived external human review as a blocker for this
  compact qualification; independent human review remains recommended before
  production cutover.
- Retained the 5-sigma/3-sigma detection thresholds, 0.5-beam matching rule,
  five-sigma conservative extension policy, covariance-aware axis censoring,
  and existing 20 co-primary compatibility endpoints. Detailed metric/stratum
  results remain diagnostic and an unexplained material defect still blocks
  release, but the 450 correlated Phase 4R comparisons are not repeated as
  equal pass/fail votes.
- Increased the new qualification to 800 paired whole-image realizations. The
  historical 600-image design's conservative 20-endpoint joint-power lower
  bound was about 82.7%; at 800 it is about 94.3%, above a new binding 90%
  joint target while every marginal endpoint remains above 90%.
- Limited the checkpoint claim to compact, single-scale Rapthor-used
  behaviour. No controlled real residual/noise injection is available, so its
  absence remains explicit and cannot be replaced by a synthetic claim.

**Next**

- Implement executable joint-power and Phase 4S qualification-input checks
  using TDD.
- Freeze and commit the new 800-realization manifest, comparison protocol,
  reviewed identities, and refusal-to-overwrite paths before generating any
  qualification image or implementation output.

## 2026-08-05 — Froze the unopened Phase 4S compact qualification

**Plan phase:** Phase 4S — qualification-first checkpoint

**Completed**

- Added TDD coverage that prevents Phase 4S from opening under the historical
  protocol, without explicit manifest population units, with mismatched
  population counts, or below either its marginal or joint power target.
- Froze a reproducible 800-realization, 512-by-512 compact population with 33
  observable groups, 32 individual sources, eight point sources, 16 marginal
  sources, eight clear sources, four SNR tiers, eight edge/corner topologies,
  continuous source sizes and angles, correlated noise, WCS rotation,
  non-square pixels, a gradient, negative background, invalid pixels, and one
  unresolved blend.
- Froze the existing 20 paired compatibility endpoints as the co-primary
  released-PyBDSF decision. Every binary declaration matches the manifest.
  The weakest marginal planned power is about 97.07%; the conservative joint
  lower bound is `0.9428716467454087` against a binding `0.9` target.
- Recorded the AI-review limitation, compact/single-scale scope, absence of
  controlled real-residual evidence, exact one-look rule, and literature basis
  in the plan, review record, protocol reference, and machine-readable
  contract.

**Frozen identities**

- Recipe SHA-256:
  `a49bf060515f777b745012317b4e0172fdfb60f9df88bf9dbe2a0ca70522f5de`.
- Dataset-record SHA-256:
  `01e28063fec9be50bd47b155a79383093258d9df22ee1f9ca57286a0dd74ec63`.
- Manifest-document SHA-256:
  `b0eac85a27101c25cf77ea1f4df45da6c33383b49c9cfd360039eac50eaa29d4`.
- Paired-protocol SHA-256:
  `8db043b70dc295d2a36214fe3ffc5822f86ee89794ed36bb31f11b22b3040a96`.
- Released PyBDSF remains version `1.14.1` at
  `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`; pinned `master` remains
  `1.14.2.dev40+gc70103be3` at
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c`.

No qualification image, candidate shard, reference shard, compiled campaign,
or decision existed when these inputs were frozen and reviewed.

**Next**

- Commit the complete pre-opening state, use that commit as the exact Hebog
  candidate identity, verify every output path is absent, and run the three
  immutable campaign legs before inspecting the one-look decision.

## 2026-08-05 — Opened and reviewed the failed Phase 4S qualification

**Plan phase:** Phase 4S — qualification-first checkpoint

**Outcome**

- Hebog, released PyBDSF, and pinned `master` each completed all 800 frozen
  images with no failed seed. The candidate was Hebog `0.5.0` at
  `0c9098af01ea2601f95c416e8b8e3d75a31361c9`; the references were PyBDSF
  `1.14.1` at `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc` and
  `1.14.2.dev40+gc70103be3` at
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c`.
- All 20 paired endpoints passed against released PyBDSF and independently
  against pinned `master`. Hebog recovered every declared compact association,
  achieved reliability `0.9956628323590421`, and was materially better on
  reliability, unresolved-group position/flux error, and aggregate
  normalized-residual calibration.
- The immutable decision failed four binding absolute outcomes:
  `median-position` was `0.02588101695920189` beam against `0.02`;
  `median-peak-flux` was `0.028183259588272835` against `0.02`;
  `point-source-specificity` was `0.0` against `0.95`; and the SNR-10
  integrated-flux normalized-bias interval was
  `[0.057897558361946606, 0.15435183788920392]` against `[-0.15, 0.15]`.
  Phase 4S is therefore terminally failed and was not rescored.

**Expert review**

- Hebog labelled every one of the 6,400 declared point cases `unresolved`.
  The specificity failure came from re-inferring noiseless truth through WCS
  and beam deconvolution, where tiny projection residue produced a false
  `major-axis-only` reference. Prospective scoring now compares candidate
  states directly with declared manifest classes and canonicalizes analytic
  point truth to unresolved.
- Fixed 2% raw median position/peak limits are below the noise floor for an
  equal SNR 10/15/25/50 mixture. Released/master PyBDSF medians were about
  `0.02608`/`0.02573` beam for position and `0.04623`/`0.04547` for absolute
  peak error. Hebog's mean signed peak bias was only `0.00398`, and its raw
  errors declined monotonically with SNR. Future generated mixed-SNR evidence
  retains raw error distributions as report-only while binding SNR-specific
  normalized-residual bias, coverage, and dispersion.
- The SNR-10 integrated-flux result remains a genuine narrow miss. Coverage
  (`0.68875`) and dispersion (`0.9835004119461924`) passed, and the point
  estimate was only `0.10612469812557526` sigma, but the predeclared interval
  rule was not waived. A fresh Phase 4T campaign with eight point sources per
  SNR tier per image will test the unchanged `0.15`-sigma bound with 6,400 new
  SNR-10 point residuals.

**Evidence**

- Hebog shard SHA-256:
  `8e3f4d3ed7973ed931128f8e62024034a118b1641db5c3dc97f820d91d9ab079`.
- Released-PyBDSF shard SHA-256:
  `5203c4d5977afd9b0dd58db272e78ef6e7c9c6e0330c83dc3d6c8e46efbd3efc`.
- Master-PyBDSF shard SHA-256:
  `18d178d82fd9a3b0cea52fd0d9a648fdff3227edfc18a66c2a1dadf456ce497d`.
- Compiled-campaign SHA-256:
  `15b2a38b3bb5876a9323e1aabcf19d7e3b66fb546643c9f4e513c36690eafbfb`.
- Decision SHA-256:
  `bcb62bfb170d11b2a204b38893ca97e94b5c123218d3b059559187678a991a3e`.
- The campaign runner wall times were approximately 2,259 seconds for Hebog,
  3,358 seconds for released PyBDSF, and 3,724 seconds for pinned `master`.
  These single scientific-campaign observations are not controlled
  performance evidence and support no speed claim.

**Next**

- Commit the immutable outcome record and prospective evaluator corrections.
- Freeze Phase 4T, its fresh population, exact identities, power, and one-look
  rule before generating any new candidate or reference output.

## 2026-08-05 — Froze the unopened Phase 4T confirmation

**Plan phase:** Phase 4T — targeted compact confirmation

**Completed**

- Added explicit design power for a clustered absolute-mean equivalence gate.
  The executable preflight binds the population count, anticipated Phase 4S
  effect, within-image correlation, confidence level, unchanged uncertainty
  margin, and minimum power to the frozen manifest and gate document.
- Corrected a pre-opening inference mismatch found during expert review: the
  decision evaluator now treats each image/noise realization as an independent
  cluster for Phase 4T coverage, bias, and dispersion intervals. Phase 4S's
  SNR-10 point residual ICC was about `-0.0097`; the registered positive 0.02
  planning value provides an allowance without changing any scientific
  margin. Coverage and bias use cluster-sandwich Student-t intervals, while
  dispersion uses a fixed-seed whole-realization percentile bootstrap.
- Froze 800 fresh 512-by-512 realizations with 49 observable groups, 48
  individual sources, 32 point sources, eight marginal sources, eight clear
  sources, and one unresolved blend. Every SNR tier contains eight point
  sources, yielding 6,400 fresh SNR-10 point residuals. Point and non-point
  cases retain edge examples, and the WCS, correlated-noise, gradient,
  background, invalid-pixel, and blend stresses remain present.
- Froze the prospective raw median/tail report-only policy while retaining all
  uncertainty, completeness, reliability, morphology, catastrophic, group,
  and stronger-envelope thresholds. The exact 20 paired endpoints and
  released/master reference roles remain unchanged.
- Added TDD coverage for manifest reconstruction, seed disjointness, population
  counts, absolute power, contract/gate binding, and refusal to open under the
  Phase 4S protocol or gate semantics.

**Power**

- The weakest paired endpoint has planned interval-exclusion power
  `0.9706664817215229`; the conservative 20-endpoint joint lower bound is
  `0.9606701920905562` against the binding `0.9` target.
- The retained SNR-10 integrated-flux normalized-bias gate uses anticipated
  mean `0.1062`, dispersion `1.0`, eight observations per image, ICC `0.02`,
  95% confidence, and the unchanged `0.15` margin. Its effective sample size
  is about `5614.04` and planned interval-containment power is
  `0.9068880664578192`.

**Frozen canonical identities**

- Recipe SHA-256:
  `e39400565031867f3412a640ec55aa88e4807ff627affff6439c969e3445a696`.
- Dataset-record SHA-256:
  `3afb044f413fbd3aa4748069b09255fbfe300b9a3f47c79f3589bab4ff06ee23`.
- Manifest-document SHA-256:
  `919d8a32c4cdbd41fdb16a803aeed850d50af4eedc46d331c5a4dbc224ff5333`.
- Paired/absolute protocol SHA-256:
  `2997015cb5235d5be9f3029d563455974fe1a1948843b5a50266fab616e094ee`.
- Scientific-gates SHA-256:
  `2841a2a93a17280c8decc5b0b1a7aa138279838f168a69504af37210aef13da6`.

No Phase 4T image, candidate shard, reference shard, compiled campaign, or
decision existed when these inputs were frozen and reviewed.

The exact released and master PyBDSF versions, commits, and container digests
remain the Phase 4S identities. The Hebog candidate is the local commit that
contains this freeze; its dependency inventory and execution configuration
will be captured by the isolated runner.

**Next**

- Commit the complete pre-opening state and use that commit as the exact
  Hebog candidate identity.
- Verify all Phase 4T output paths are absent, run the three immutable legs,
  compile once, and open the one-look decision once.

## 2026-08-05 — Opened and reviewed the Phase 4T decision

**Plan phase:** Phase 4T — targeted compact confirmation

**Execution**

- Ran Hebog commit `9653b0d5310b9922ffcf66bd2c801f33aa506f38`,
  released PyBDSF 1.14.1 at `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`,
  and pinned PyBDSF `master` at
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c` once on the same 800 frozen
  images. Every implementation completed 800/800 realizations.
- Compiled the three immutable shards. A workstation interruption stopped the
  evaluator before atomic publication; the decision path was absent. Under
  the frozen infrastructure-recovery rule, resumed only the missing evaluator
  from the same compiled evidence. No implementation was rerun and no
  completed evidence was overwritten.

**Decision**

- Hebog passed all 20 paired non-inferiority endpoints against released
  PyBDSF and independently against pinned `master`, all uncertainty gates,
  and 76/77 binding absolute gates in total. The targeted SNR-10
  integrated-flux mean normalized residual was `0.061213` with cluster-aware
  95% interval `[0.037429, 0.084998]`, passing the unchanged
  `[-0.15, 0.15]` limit.
- The decision failed because unresolved-group total-flux 95th-percentile
  absolute error was `0.207080` against the frozen `0.2` maximum. Released
  PyBDSF and pinned `master` were both `0.600031`; Hebog strongly passed both
  paired comparisons, but the absolute gate and stronger envelope remain
  failed.
- Post-decision diagnosis found 48/800 errors above 20%, a 95th-percentile
  bootstrap interval of about `0.19484`--`0.21336`, and 93.25% signed errors
  below truth with mean `-0.097084`. These diagnostics do not rescore the
  gate. They support a general blend-flux under-recovery investigation rather
  than a threshold waiver or unchanged-candidate rerun.

**Evidence SHA-256**

- Hebog shard:
  `372a0efa4c83c92a1f1ff9f079f360089b65ab74e61f2d67902a55fcc46a09a1`.
- Released-PyBDSF shard:
  `456241d08fc2155de6b973e326d22dd10174ba76b6f620ecff2e23158c22721f`.
- Master-PyBDSF shard:
  `1f9428ed5fbcaafa1409663868ec81679a6ac83add6afd41300819314dd624a7`.
- Compiled campaign:
  `78c7d71a88771e396a801742768c9cebab409b846b3623169aa6744f57a29bc1`.
- Decision:
  `e1b52aa42f0213a13a296a108f55a1aafe841bb350317e5fd5e3013f1a09ea49`.

**Disposition**

- Preserved Phase 4T as a terminal failure. Added Phase 4U as blocking,
  test-driven unresolved-blend flux remediation on independent development
  and regression data. Substantive Phase 5 work remains paused until a
  generally improved candidate passes a separately frozen qualification.

## 2026-08-05 — Corrected orientation-dependent compact-blend flux loss

**Plan phase:** Phase 4U — unresolved-blend flux remediation

**Diagnosis and implementation**

- Reproduced the bias analytically without using any Phase 4T realization.
  The former fixed restoring-beam association aperture recovered about 98.3%,
  93.8%, and 86.5% of noiseless two-source truth as the pair rotated from the
  beam major axis through 45 degrees to the minor axis. This isolated
  aperture clipping from background estimation, island ownership, and beam
  normalization.
- Added a model-containment selector. The lower-variance restoring-beam
  aperture remains in use when it contains at least 90% of the selected fit;
  otherwise photometry follows the selected-fit ellipse. Flux in both cases
  is corrected only for the fraction of that same model visible through
  image, validity, and competing-region masks. No empirical flux multiplier
  or qualification-dependent branch was added.
- Renamed the evidence to association-aperture photometry and incremented the
  unreleased internal catalogue FITS encoding to schema version 3 with
  `ASSOCIATION_APERTURE_FLUX`. Hebog's pre-production no-compatibility policy
  intentionally leaves no version-2 development reader.

**Independent development evidence**

- Added noiseless angle regressions and a fresh 18-realization noisy matrix
  using seeds `2026501001`--`2026501018`, three source/beam angles, and equal
  and 2:1 component ratios. Mean signed error was `-0.024108`, median signed
  error `-0.037878`, 95th-percentile absolute error `0.147443`, maximum
  absolute error `0.153519`, and 12/18 errors were negative.
- The prior Phase 4R noisy blend regression still passes. Focused fitting and
  blend tests passed 78/78; the complete unit, integration, and equivalence
  lanes passed during development. Final branch-aware project coverage was
  94.12%, with the changed aperture, schema, and configuration paths covered.

**Next**

- Complete final coverage, documentation, serial/Dask, and repository checks;
  commit the candidate atomically; then freeze a separately named Phase 4U
  population with several unseen blend separations, orientations, and flux
  ratios before generating or viewing any qualification output.

## 2026-08-05 — Froze the unopened Phase 4U qualification

**Plan phase:** Phase 4U — unresolved-blend flux remediation

**Design and expert review**

- Froze the scientifically changed candidate only after remediation commit
  `96cdb40`. No Phase 4U image or candidate/reference result existed during
  design or review.
- Retained 48 individual compact controls and added six new unresolved blends
  at total peak SNR 27. The pairwise-crossed design uses beam-normalized
  separations `0.45`, `0.65`, and `0.80`, angles 0, 45, and 90 degrees from
  the beam major axis, and equal versus 2:1 flux ratios. An early pre-output
  review replaced raw pixel separations with directional elliptical-beam
  normalization so every declared unresolved case remains genuinely sub-beam.
- Verified each blend center is at least 60.58 pixels from an individual
  control. The 800 seeds begin at `2026600001` and overlap neither viewed
  Phase 4 populations nor development seeds `2026501001`--`2026501018`.
- The image/noise realization remains the independent unit. The six-blend
  completeness endpoint now declares 0.02 planning intracluster correlation
  instead of treating within-image groups as independent.
- Project-owner-authorized AI expert review judged the design proportionate
  for the compact Phase 5 start gate. It does not replace independent human
  production review or controlled real-residual evidence.

**Power and immutable identities**

- Weakest paired interval-exclusion power: `0.9706664817`.
- Conservative familywise lower bound: `0.9699279153`.
- Retained absolute mean-gate interval-containment power: `0.9068880665`.
- Recipe SHA-256:
  `2fd89b058a113f8318bd67ab7c05925f66b7cfa895fb6a2c7ea6a9746bad144d`.
- Dataset-record SHA-256:
  `8e2e0dc5ed2eb7b1ad2d530c088849939b3a147ea0f8fbe52ac067b982c352dc`.
- Manifest-document SHA-256:
  `57365cd616d0965d62eb12eae16b8323c1ce94a7f900e4113022a42b85a9c712`.
- Paired protocol SHA-256:
  `3106e114508d3858eae44105ca8e03a4dfe0912726fca83ebf6ef0394c472b76`.
- Unchanged scientific-gates SHA-256:
  `2841a2a93a17280c8decc5b0b1a7aa138279838f168a69504af37210aef13da6`.
- Measurement-contract SHA-256:
  `ab6a3d932a1b73f5414cfef8199831bbb394f990db1b885bd06f15f044b77ed0`.

**Next**

- Commit this complete unopened freeze, verify all five registered output
  paths remain absent, run Hebog and both exact PyBDSF references once, compile
  the immutable shards, and open exactly one decision.

## 2026-08-05 — Passed Phase 4U and closed the compact science start gate

**Plan phase:** Phase 4U — unresolved-blend flux remediation

**One-look execution**

- Ran exact candidate `ca51ed24e354fc18f9c18c273b7ede7e54c96569`, released
  PyBDSF 1.14.1, and pinned PyBDSF `master`
  `c70103be3ae9ae9908286f144e6ce956acc0ce5c` once over all 800 frozen
  images. Every implementation completed every image.
- Kept all three shards unopened until completion, compiled the candidate-
  first triplet once, and opened exactly one decision. The compiler accepted
  the frozen dataset, seed, contract, reference, and paired-protocol
  identities.
- The qualification passed: 77/77 binding absolute gates, 20/20 paired
  endpoints against released PyBDSF, 20/20 against PyBDSF `master`, and 5/5
  stronger-Hebog envelopes passed. The closest paired limit was catalogue
  reliability at `0.003529` against the `0.005` practical margin.

**Scientific outcome**

- Hebog recovered all 4,800 unresolved groups. Median absolute total-flux
  error was `0.047567`; the 95th-percentile error was `0.139196` against the
  unchanged `0.2` maximum.
- Hebog's mean and median signed blend errors were `-0.020217` and
  `-0.019847`. Released PyBDSF measured about `-0.108544` and `-0.109929`;
  pinned `master` was effectively identical. The worst approximate
  per-geometry Hebog 95th percentile was `0.1622`.
- Four legacy mixed-SNR whole-catalogue summaries remained failed but
  report-only and essentially unchanged from Phase 4T. Every binding
  SNR-specific, edge, uncertainty, classification, catastrophic, and
  unresolved-group result passed; expert review found no material diagnostic
  regression.

**Evidence identities**

- Candidate:
  `cbeae07878c2fe3d801fdff816b00db23f6d03655fe5652932e13b9e95a359dc`.
- Released reference:
  `75fa0a3a53ae4a7c63ffb2cac63213c04380eab3160622d93dfe1c00f78ea23b`.
- Master reference:
  `4c9563f0fe8687da3a4d5370c39fbbcb8579483a8911d4f3a123da2a1b4a6f49`.
- Compiled campaign:
  `0355537bcfc1c716a6b4b9e7d0269c6d78c66bfacdfb69925f37a13ce6b018a1`.
- Decision:
  `309ab639cafc5c8aafb75bc85e9b8d531def3e7c51ea424561bb399dc53795f0`.

**Disposition**

- Closed the compact single-scale science start gate and authorized
  substantive Phase 5 multiscale development. Historical failed campaigns
  remain immutable. Independent human scientific review, real-residual,
  performance, bounded-memory, task-graph, and scale evidence remain later
  production gates.

## 2026-08-05 — Closed the compact Phase 4 engineering milestone

**Plan phase:** Phase 4, Step 8 — qualification replay and performance
closeout

**Performance diagnosis and correction**

- Added a frozen 20-cell incremental component matrix at 256, 512, 1,024, and
  3,000 pixels per side for sparse, normal, dense, blend-heavy, and deliberate
  fit-failure workloads. Each cell uses one warm-up and five measured
  repetitions and retains stage timing, task/batch/source counts, bounded
  arrays, process-tree RSS, output size, and typed omissions.
- Retained the first matrix as failed diagnostic evidence. At 3,000 pixels it
  scheduled normal, dense, and blend-heavy work as one task and measured
  complete medians of `1.518125`, `6.498360`, and `4.307945` seconds. The hard
  memory ceiling had incorrectly doubled as the preferred task size.
- Separated the preferred `8,000`-pixel fitting batch target from the
  `500,000`-pixel hard limit, used analytic Gaussian derivatives and FFT
  covariance convolution, and reused parsed WCS transforms. The benchmark now
  imports the exact governed Phase 4 candidate configuration and generates
  beam-correlated noise rather than an inconsistent independent-pixel field.
- The final matrix passed. At 3,000 pixels, successful measurement/fitting
  medians are `0.177855`, `0.250447`, `0.757952`, and `0.596301` seconds for
  sparse through blend-heavy work; output medians are `0.036850`--`0.040811`
  seconds. Both are below separate 2.0-second budgets. Dense work uses 13
  batches and 13 Dask tasks with 91 sources and no omissions. Every
  dense-to-normal per-source time ratio is below one, and the fit-failure
  profile refuses output with retained `singular-covariance` omissions.
- Final matrix-summary SHA-256:
  `ee3729e39a6b432f29b0b5282b39e4023c479b51ee7180187760a5b567f3ffa8`.
  The retained failed matrix summary is
  `513f8ee875e88c9961b8cdbcc0f3dec8bf3d3a93f2d5b4f6b082ba4462f04596`.

**Scientific regression replay**

- Added bounded campaign-level process parallelism solely for independent
  images. Each image still uses the frozen serial scientific implementation;
  recipe-order output and the worker allocation remain explicit in evidence
  provenance. A two-process development smoke run passed on macOS.
- Replayed exact optimized commit
  `fd7477afa4deb55874ed679b8d380dde6940ad93` over the already viewed Phase 4U
  population as regression evidence, not a new qualification or rescore. All
  800 Hebog images completed successfully. Both immutable PyBDSF shards also
  retain 800/800 successful images.
- The unchanged evaluator again passed all 77 binding absolute gates, all 20
  paired endpoints against released PyBDSF, all 20 against pinned `master`,
  and all five stronger-Hebog envelopes. Four legacy mixed-population results
  remain explicitly report-only.
- Candidate, compiled-campaign, and decision SHA-256 values are
  `62f8f73816b1cb3deae0c276d919173856ab53f43778a4f98bc6ab1392ff4ebc`,
  `e34da45e0b1a44932178a6df959ea91cf42ca2ad25ab23b1851ebcb509f54137`,
  and `52b4b374f9160ba52271acc07eb36f1fe8b0b776557b26f392de362bea29f2bb`.

**Disposition**

- Closed Phase 4 for the compact single-scale milestone. The passing
  component matrix is not a matched PyBDSF speedup: complete Rapthor
  `filter_skymodel` timing remains a Phase 7 gate.
- Authorized Phase 5 multiscale work while retaining independent human
  radio-astronomy review, real-residual evidence, and production-scale Dask
  memory/task-graph qualification as later cutover gates.

**Validation**

- The optimized scientific implementation passed 182 focused tests, 130
  integration tests, 27 dual-reference equivalence tests, and branch-aware
  coverage with 926 passing tests and 94.14% project coverage. Serial and Dask
  conformance remained included in those lanes.
- Final closure lanes passed with 130 integration and 27 equivalence tests.
  Four future contract scenarios and seven future acceptance scenarios remain
  explicit expected failures. The qualification lane passed its active case,
  skipped one unavailable-host case, and reports the terminal historical
  Phase 4 campaign as a non-running expected failure so governed viewed data
  cannot be rerun.
- Strict documentation built successfully, and the final fast repository
  check passed Ruff formatting/lint, Pyright, and 797 tests with four declared
  expected failures.

## 2026-08-05 — Prepared the delivery plan for Phase 5

**Plan phase:** Phase 5 — multiscale and extended emission preparation

- Reviewed the completed compact milestone, its durable readiness and review
  records, the remaining extended-island deferrals, and the boundaries between
  Phase 5 science and Phase 6 distributed execution.
- Reduced the authoritative implementation plan from 3,255 to about 1,300
  lines by replacing completed Phase 0--4 checklists and campaign chronology
  with a milestone ledger, durable constraints, and links to immutable
  evidence. Historical failed one-look decisions remain explicitly terminal.
- Expanded Phase 5 into an ordered contract, algorithm-selection,
  implementation, reconciliation, tile-invariance, qualification, and
  performance plan. The plan now requires a frozen untouched qualification
  population, reviewed scale-stratified gates, preservation of the Phase 4U
  compact baseline, bounded extended-island processing, deterministic
  cross-scale identity, and the existing 6.0-second representative component
  budget.
- Updated stale Phase 0 and Phase 4 future-tense text and replaced the resolved
  compact-fitting questions with the scientific and architectural decisions
  that must be answered during Phase 5.

**Immediate next step:** inventory the Rapthor-used multiscale objects and
current Phase 3/4 deferrals, then freeze the Phase 5 scientific contract,
dataset roles, evaluator families, and pre-opening review process before
algorithm tuning.

## 2026-08-05 — Completed Phase 5 Step 1 contract freeze

**Plan phase:** Phase 5, Step 1 — multiscale meanings, datasets, gates, and
development review

- Inventoried the Rapthor three-scale profile, the five unmatched multiscale
  objects in the representative comparison, oversized compact-island
  deferrals, the compact catalogue publication boundary, and the downstream
  catalogue, mask, and filtering decisions they affect.
- Added strict machine-readable contracts for the three dyadic beam scales,
  response normalization, Phase 2 background/RMS reuse, valid-support and
  edge handling, deterministic cross-scale association, combined-catalogue
  publication, and fail-closed omissions. Filter selection remains explicitly
  deferred to Step 2.
- Added immutable scheduler-safe records for scale detections, cross-scale
  associations, extended measurements, omissions, terminal island
  dispositions, and combined-catalogue state.
- Added schema-version-three development, regression, and qualification
  manifests with analytic morphology truth spanning diffuse, filamentary,
  curved, shell, mixed, edge, tile-boundary, invalid-pixel, varying-noise,
  overlapping-scale, and artefact cases. The shell crosses a tile corner and
  is predeclared above the governed compact-deblend test limit. Their disjoint
  seed ranges contain 10, 100, and 400 images respectively.
- Froze conjunctive absolute truth gates and paired non-inferiority margins
  against released and pinned-`master` PyBDSF, with whole-image bootstrap
  intervals, a 90% joint-power target, and a one-look qualification rule.
- Recorded Codex's named AI scientific synthesis as development review. This
  is not independent human or institutional approval; independent
  radio-astronomy review and realistic residual evidence remain production
  cutover gates.
- Preserved historical Phase 1--4 dataset identities when extending the
  manifest schema. No Phase 5 qualification image or algorithm output was
  generated or inspected.

**Development validation:** the initial focused contract and record tests
failed for the intended missing loaders and records; after implementation,
the focused contract, dataset, and data-model suite passed 195 tests. The
branch-aware coverage lane passed 980 tests with four expected failures and
94.36% project coverage; the new multiscale records reached 99%, contracts
95%, and dataset validation 97%. The fast handoff lane passed Ruff, Pyright,
and 850 tests with four expected failures. The frozen equivalence lane passed
27 tests, the public-contract lane retained its four declared expected
failures, and strict documentation built successfully.

**Immediate next step:** begin Step 2 with failing analytic scale-response
tests, then compare the predeclared beam-aware matched-filter and undecimated
wavelet representations on development data only.

## 2026-08-06 — Selected the Phase 5 scale representation

**Plan phase:** Phase 5, Step 2 — analytic scale response and filter-family
selection

- Added a readable float64 one-tile serial oracle that consumes prepared
  image, validity, background, and RMS planes. It does not rerun ingestion,
  background estimation, RMS estimation, or compact detection, and it retains
  no durable image-sized response plane.
- Implemented both predeclared SciPy candidates: an elliptical beam-aware
  matched-filter bank and an undecimated Gaussian-difference wavelet with
  shared dyadic smoothings. New analytic tests cover unit-flux normalization,
  constant and affine backgrounds, masks and NaNs, image edges, separated
  compact sources, dtype, halos, noise gain, bounded workspace, and invalid
  inputs.
- Both candidates passed the analytic gates and produced finite responses in
  every governed development truth window. The matched filter's maximum
  masked and edge response errors were 8.585% and 7.588%; the wavelet's were
  0.397% and 0.076%. Unit-response errors were below `9e-16`, and prepared
  background responses were exactly zero.
- Amended the minimum valid support fraction from 0.8 to 0.5. The original
  value made the required edge-source stratum unavailable; the amended value
  recovers its analytic flux within the frozen 10% Step 2 edge gate and still
  fails closed below half support. No qualification result informed the
  amendment.
- Ran one warm-up and five measurements over all ten frozen 1,024-square
  development images. The matched-filter median was 2.05222 seconds versus
  2.57138 seconds for the wavelet. More importantly, the matched bank uses 9
  rather than 11 convolutions per image, 7 rather than 9 temporary planes, a
  34- rather than 49-pixel maximum halo, and 159,485,104 rather than
  176,399,304 logical workspace bytes.
- Selected the beam-aware matched-filter bank under the predeclared
  science-first bounded-cost rule. Froze four-sigma Gaussian truncation,
  unit-integrated-flux calibration, correlated-noise gain, SciPy FFT
  convolution, float64, and the halo formula. Neither lower precision nor
  native code is authorized, and no ADR is needed because dependency,
  scheduler, and storage boundaries are unchanged.
- Wrote typed ignored evidence at
  `benchmark-results/phase-5/filter-selection.json`, SHA-256
  `f250f4b6e938db91eb4811d68ba048e72ed3ba4595caba36e2334a926338917f`.
  The evidence binds source-tree SHA-256
  `6150aa39661e63bca5c9d6303d34169ca3a97e155fbe28e16d0bf67bb179c9cc`
  and confirms `qualification_opened=false`.

**Development validation:** the focused algorithm, contract, and evidence
suite passed 148 tests. The branch-aware coverage lane passed 1,036 tests
with four expected failures and 94.54% project coverage; the new multiscale
oracle reached 99%. The frozen equivalence lane passed 27 tests, and the
public-contract lane retained its four declared expected failures. The fast
handoff lane passed Ruff, Pyright, and 906 tests with four expected failures,
and strict documentation built successfully.

**Immediate next step:** begin Step 3 with failing tests for scale-specific
thresholds, support connectivity, local maxima, and bounded deferred-island
measurement using the selected matched-filter responses.

## 2026-08-06 — Required paired filter re-evaluation before Step 3

**Plan phase:** Phase 5, Step 2B — representation selection by paired science

- Reclassified the Step 2 matched-filter choice as provisional. Its 8.585%
  masked-response error passed the 10% absolute gate but was materially larger
  than the wavelet's 0.397%; the matched filter also had lower propagated
  noise in that probe, so neither centre-response bias nor cost alone decides
  the scientific trade-off.
- Added a fail-closed Step 2B before candidate-specific detection,
  measurement, reconciliation, tiling, or optimization. The comparison must
  use identical prepared inputs and a frozen non-qualification matrix spanning
  scales, support fractions, masks, edges, morphologies, nearby sources,
  varying RMS, correlated noise, and SNR.
- Required paired response and integrated-flux error, calibrated SNR, noise
  calibration, completeness, reliability, astrometry, support availability,
  fragmentation or negative-lobe behaviour, and mask topology in every
  applicable governed stratum. Practical margins and confidence rules must be
  frozen before inspecting the new results.
- Cost may distinguish candidates only after every absolute and paired
  scientific gate passes without a practically material advantage. If either
  candidate is scientifically better, it must be selected at its current
  bounded cost and optimized afterward.
- Kept the frozen qualification population unopened. The existing selection
  contract and evidence remain the reproducible initial Step 2 record and
  must be amended or confirmed by named Step 2B review before Step 3.

**Immediate next step:** freeze the Step 2B paired matrix, response-level
margins, and confidence procedure before generating new candidate results.

## 2026-08-06 — Froze the Phase 5 Step 2B paired protocol

**Plan phase:** Phase 5, Step 2B — pre-results protocol freeze

- Added a strict machine-readable protocol for the matched-filter and wavelet
  comparison before generating any new candidate result. It binds the exact
  ten-image development and 100-image regression manifests and keeps the
  qualification population unopened.
- Froze all three scales, 0.5--1.0 support, seven mask and edge geometries,
  seven analytic and injected morphologies, four SNR levels, noiseless and
  beam-correlated varying-noise cases, and candidate-neutral 5-sigma/3-sigma
  response thresholds.
- Froze ten binding endpoints covering response and integrated-flux error,
  calibrated SNR, noise calibration, completeness, reliability, astrometry,
  support, fragmentation, and mask topology. Runtime and negative-lobe depth
  remain recorded diagnostics rather than compensating scientific endpoints.
- Froze absolute gates, candidate-to-candidate practical non-inferiority
  margins, exact analytic evaluation, and whole-image 10,000-resample
  one-sided 95% intervals for the 100 regression images.
- Required every applicable absolute and paired stratum gate to pass. A
  scientific advantage overrides current cost, a scientific tie uses bounded
  structural cost, and an inconclusive result selects neither candidate.
  Optimization remains forbidden until after selection.
- Recorded protocol SHA-256
  `749d2393c485239bea6a897beaeb4a97b0b8ab7d8aff851646e43e857b4c993d`
  with `step_three_authorized=false` and `qualification_opened=false`.

**Immediate next step:** implement the candidate-neutral analytic and
generated-response evaluator test-first, then run the frozen protocol without
opening qualification.

## 2026-08-06 — Completed Step 2B with no eligible representation

**Plan phase:** Phase 5, Step 2B — paired representation decision

- Implemented candidate-neutral exact-response and minimal 5-sigma/3-sigma
  threshold evaluation for the existing float64 matched-filter and wavelet
  banks. Both candidates consume identical image, validity, background, RMS,
  truth-group, threshold, and connectivity inputs.
- Evaluated 84 exact analytic cases, all ten frozen development images, and
  all 100 frozen regression images. The runner verified the pre-results
  protocol and both manifest checksums and did not read qualification data.
- Corrected the generated integrated-flux evaluator before final evidence: it
  now integrates within candidate-retained support. A regression test first
  demonstrated that the old raw truth aperture returned identical flux for
  both candidates regardless of their representation.
- The matched filter's overall analytic response error was 7.49% median and
  12.86% at the 95th percentile; the wavelet's was 5.98% and 19.81%. Both
  missed the frozen 5%/10% gates. The matched filter had higher median
  calibrated response SNR, 15.99 versus 11.32.
- Both candidates reached regression completeness 1.0. The wavelet improved
  mean mask IoU from 0.239 to 0.617, but both missed the 0.8 gate. Their
  95th-percentile position errors were 0.462 beam for matched and 0.444 for
  wavelet, both above 0.25 beam. Wavelet fragmentation was 0.167 versus 0.017
  and its retained-support median flux error was 0.145 versus 0.059.
- Applied all exact and 10,000-resample one-sided paired decisions without
  cross-stratum compensation. Matched failed 169 absolute and 88 paired
  endpoints; wavelet failed 203 absolute and 269 paired endpoints. Structural
  cost was therefore not used to select either candidate.
- Added a strict `reviewed-inconclusive` decision contract recording
  `select-neither`, no selected family, and false Step 3, optimization, and
  qualification authorization. The initial Step 2 matched-filter selection
  remains historical evidence only.
- Wrote typed ignored evidence at
  `benchmark-results/phase-5/filter-paired-review.json`, SHA-256
  `e7f6805cb42bb0f41c844adf152d7e53ead1837def3fbb6b0fae48482031b5c0`.
  It binds source-tree SHA-256
  `bfb9bc08e3f294b86b7a3f3ba29458b1ce502d0a35cf57494d85fc7e5149611b`
  and configuration SHA-256
  `2701feb4a909cf4dce0725e05f2ed828b1d581eccd540b93d7e6c6893ca4f208`.

**Development validation:** the evaluator, contract, and evidence suite passed
132 focused tests before the final campaign. The branch-aware coverage lane
passed 1,063 tests with four expected failures and 94.46% project coverage;
the new evaluator and analysis modules each reached 94%. All 27 frozen
equivalence tests passed. Strict documentation built, and the fast handoff
lane passed Ruff, Pyright, 933 tests, and four expected failures. Pre-commit
results are recorded by the final local commit.

**Immediate next step:** freeze the corrective Step 2C development design.
Diagnose exact missing-support response, wavelet SNR/negative lobes,
retained-support flux, astrometry, fragmentation, and mask topology before
optimizing a candidate or defining a justified hybrid. Keep qualification and
Step 3 closed.

## 2026-08-08 — Reframed the Phase 5 corrective design from community practice

**Plan phase:** Phase 5, Steps 2C--2D — corrective continuum design and
Rapthor profile evidence

- Reviewed PyBDSF, Aegean, Selavy, ProFound, CAESAR, Hydra, and radio source-
  finder challenge evidence. The review found strong precedent for local-noise
  seed-and-grow islands, compact Gaussian modelling, residual multiscale
  processing, morphology-independent extended support, and explicit tiled
  overlap, but no universally superior extended-source representation.
- Chose an optimized residual B3-spline à trous reconstruction followed by
  original-image segmentation and measurement as the corrective candidate to
  freeze and evaluate. This is not a selection result: Step 3, candidate-
  specific optimization, and qualification remain closed until the amended
  Step 2C protocol passes.
- Separated detection, reconstruction, masking, and photometry in the plan so
  neither wavelet nor matched-filter coefficients are treated as final
  extended-source flux estimates. Kept the existing numerical science gates
  and fail-closed selection policy.
- Added explicit `compact` and `continuum` scientific profiles. The continuum
  profile remains the intended general-community default; Rapthor may select
  compact only if a frozen same-filtering comparison passes the at-least 99.5%
  retained/rejected-component gate in every safety stratum.
- Added public multi-survey/challenge comparisons and auditable scale/support,
  reconstruction, mask, model, and residual provenance to the Phase 5
  qualification and documentation requirements. External finders remain
  isolated validation comparators, not runtime dependencies or truth.

**Immediate next step:** diagnose the Step 2B failures on development evidence,
then freeze the exact residual B3-spline reconstruction, support-growth,
measurement, and amended response-evaluation contract before implementation.
Keep the qualification population unopened.

## 2026-08-08 — Completed Step 2C with the corrective candidate rejected

**Plan phase:** Phase 5, Step 2C — corrective continuum re-evaluation

- Diagnosed Step 2B as a stage-separation failure as well as a representation
  comparison: scale coefficients had been used for response, retained-mask
  flux, and position even though detection, reconstruction, segmentation, and
  measurement have different scientific meanings. The old generated failures
  concentrated in astrometry, fragmentation, retained support, and mask
  topology.
- Froze `config/contracts/phase-5-corrective-review.json` before corrective
  results. It retained the exact development/regression manifests, 84 analytic
  cases, 5/3-sigma thresholds, numerical absolute gates, paired margins,
  10,000-resample intervals, and fail-closed policy. It predeclared observable
  valid-domain truth, reconstructed response, original-residual masks,
  original-pixel flux and astrometry, and coefficient-only detection and
  association provenance.
- Added a readable float64 residual B3-spline à trous serial path with the
  standard five-tap kernel, dyadic 1/2/4-pixel holes, adjacent smoothing reuse,
  normalized valid support, correlated-noise gains, compact model subtraction
  or mask exclusion, a 14-pixel cumulative halo, 12 sparse one-dimensional
  convolutions, seven bounded temporaries, and no durable response bank. The
  complete reviewed candidate, including its permitted matched-filter seed
  aid, records 21 convolutions, seven peak scratch planes, and a 38-pixel
  maximum halo.
- Applied matched/B3/direct calibrated seed evidence, original-residual
  3-sigma growth, a beam-area noise-component floor, and cross-scale
  association without expanding the final pixel mask. Final flux and centroid
  measurements use the original background-subtracted residual.
- Re-ran all 84 analytic cases, ten development images, and 100 seed-disjoint
  regression images without reading qualification data. Corrected analytic
  response semantics passed every absolute endpoint for both candidates.
  Generated B3 results reached completeness 1.000, median flux error 0.0496,
  mean mask IoU 0.8260, overall fragmentation 0.0686, and maximum noise error
  0.0148.
- Rejected the corrective candidate because no-compensation gates still
  failed: regression position error was 1.598 beams at the 95th percentile
  versus the 0.250 gate; reliability was 0.9405 versus 0.950; shell and
  tile-boundary fragmentation strata failed; and the artifact flux stratum
  failed. It recorded 23 absolute and eight paired failures, improved from the
  matched comparator's 28 and 21, but improvement cannot substitute for
  passage.
- Wrote typed ignored evidence at
  `benchmark-results/phase-5/corrective-review.json`, SHA-256
  `5d21e1815fe16bdfce7f349238bec819b485cf50eef2cc552c925939fed0dc7e`.
  The reviewed decision contract records `reject-corrective`, no selected
  family, and false Step 3, optimization, and qualification authorization.

**Development validation:** focused contract, evidence, B3 kernel, amended
analytic, and generated smoke tests were developed red-to-green. The complete
handoff validation is recorded by the local commit.

**Immediate next step:** freeze Step 2C-R corrections for lower-variance
original-pixel astrometry, shell/tile association, artifact disposition, and
false-positive control. Preserve the B3 representation and every gate; keep
Step 3 and qualification closed until the complete review passes.

## 2026-08-08 — Completed Step 2C-R with only astrometry variance unresolved

**Plan phase:** Phase 5, Step 2C-R — final-output correction review

- Used only exact truth and the development role to freeze robust
  original-pixel astrometry, topology aggregation for comparable components,
  three-beam cross-scale association, typed non-photometric artifact controls,
  typed observable-domain truncation, and calibrated false-positive control.
  Preserved residual B3 detection provenance, original-pixel photometry, both
  populations, all gates, all paired margins, and unopened qualification.
- The first frozen false-positive rule, protocol SHA-256
  `57a8e1171bd1e555dc262ccc35f59aa3b271c0ae5c43ea4fc896f9cc6dc77e22`,
  applied a one-correlated-beam floor without exception. Its exact analytic
  precheck rejected legitimate 5--8-sigma beam-scale islands. The amended
  pre-results contract records that failure by hash and retains a small island
  only when its original pixels independently contain a 5-sigma seed.
- Froze the amended contract at
  `config/contracts/phase-5-corrective-r-review.json`, SHA-256
  `e1dc70bccfd8d8c706f25e2f02599324b376699c30fdc634affcca994c4b3a8b`,
  before opening replacement regression results. Exact and development tests
  cover low-SNR compact retention, shell/tile linkage, false islands, known
  artifact disposition, masked/edge truncation, and separate position bias
  and centred scatter.
- Re-ran all 84 analytic cases, ten development images, and 100 seed-disjoint
  regression images. Residual B3 reached completeness 1.000, median flux error
  0.0514, mean mask IoU 0.8311, fragmentation 0.0000, reliability 0.9674, and
  maximum response-noise error 0.0148. It passed every paired endpoint and all
  absolute domains other than position error.
- Rejected Step 2C-R because nine absolute astrometry strata remained above
  the unchanged 0.250-beam gate, with estimates from 0.260 to 0.291 beams.
  Diagnostics identify variance rather than material bias: the B3 overall
  mean offset is 0.0116 beams and centred 95th-percentile scatter is 0.2093
  beams. The binding within-image-group tail is 0.2913 beams. The matched
  comparator failed 18 absolute and nine paired endpoints; B3 failed nine and
  zero respectively.
- Wrote typed ignored evidence at
  `benchmark-results/phase-5/corrective-r-review.json`, SHA-256
  `4d57604c09351a54d51e45ca6441d15e7596e5b452bd6b96e0921e64d00c0e09`.
  The reviewed decision contract records `reject-corrective-r`, no selected
  family, and false Step 3, optimization, and qualification authorization.

**Validation:** focused contract, evidence, analytic, development, and
correction tests pass. Full handoff checks are recorded by the local commit.

**Immediate next step:** freeze a new seed-disjoint confirmation population,
then evaluate a standard noise-aware original-pixel position estimator using
only analytic truth and development data. Do not retune against or reconfirm on
the now-viewed Step 2C-R regression; keep qualification unopened.

## 2026-08-08 — Froze the independent Step 2C-A confirmation

**Plan phase:** Phase 5, Step 2C-A — astrometry confirmation freeze

- Added an overwrite-refusing freezer and canonical manifest for 100
  confirmation realizations with seeds `2026730001` through `2026730100`.
  These seeds are disjoint from Phase 5 development, the viewed Step 2C-R
  regression, and frozen qualification populations.
- Preserved the reviewed regression beam, WCS, source geometry, morphology,
  scale, artifact, edge, invalid-pixel, varying-noise, and tile-boundary
  matrix. Only the dataset identity, provenance, and noise seeds changed.
- Frozen manifest SHA-256:
  `7576f8e6e373b12a42c9820ee381750c32208444682bde4a52a1311cccfc6011`.
  Canonical dataset-content SHA-256:
  `12fc92e16a5f2ea2b57b63d565430f7b1f484ee3591070345987c92cf8de979a`.
- No confirmation image or result was generated while freezing the manifest;
  qualification remains unopened.

**Validation:** focused freezer and dataset identity tests pass.

**Immediate next step:** derive and freeze the estimator against exact truth
and the ten-image development role only, then open this confirmation once.

## 2026-08-08 — Froze the Step 2C-A estimator before confirmation

**Plan phase:** Phase 5, Step 2C-A — estimator derivation and pre-results freeze

- Used exact truth and the ten-image development role only to select a
  standard local-RMS-weighted multi-Gaussian position model. Original-pixel
  local maxima at or above 6 sigma are separated by two beam major axes and
  fitted jointly with a robust `soft_l1` loss. The model's observable-domain
  centroid is combined equally with the Step 2C-R robust original-pixel
  estimator.
- Froze at most six components, a three-beam fit margin, one-beam component
  centre bounds, 300 optimizer evaluations, a maximum normalized cost of 2.0,
  and a maximum one-beam model/moment disagreement. Any unavailable or
  inconsistent model falls back to the unchanged robust observable-pixel
  position; flux, masks, association, and detection are untouched.
- Added correlated-noise moment propagation for typed finite position
  uncertainty. Tests cover exact endpoints, per-morphology bias and centred
  scatter, shells, filaments, topology aggregation, masked and edge support,
  RMS scaling, and injected model failure.
- The frozen development endpoint is 0.2176 beams, down from the Step 2C-R
  tail near 0.29 beams. All 60 development astronomical measurements used the
  model-assisted estimator; the explicit fallback is covered by fault
  injection.
- Frozen protocol:
  `config/contracts/phase-5-corrective-a-review.json`, SHA-256
  `b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b`.
  It binds the Step 2C-R decision and the unopened confirmation manifest,
  preserves all scientific gates and paired margins, forbids tuning or
  rescoring on confirmation, and keeps qualification closed.

**Validation:** 18 focused inherited/corrective tests plus protocol-freezer
tests pass; focused Ruff and Pyright checks pass.

**Immediate next step:** seal this implementation and protocol in Git, then
run the 84 analytic cases and frozen 100-image confirmation exactly once.

## 2026-08-08 — Completed Step 2C-A and rejected the astrometry correction

**Plan phase:** Phase 5, Step 2C-A — one-look independent astrometry review

- Opened the seed-disjoint confirmation only after committing its manifest as
  `9deedf4` and the development-derived estimator and protocol as `b221db5`.
  Ran all 84 analytic cases, ten development images, and 100 confirmation
  images exactly once. No confirmation result was used for tuning, rescoring,
  or a second run; qualification remained unopened.
- Residual B3 passed every paired endpoint and failed five absolute endpoints,
  all position-error tails: overall, curved filament, scales 2 and 4, and
  varying noise. The overall frozen endpoint was 0.3597 beams and the
  curved-filament endpoint was 0.4315 against the unchanged 0.250-beam gate.
  Completeness was 1.000, median and p95 flux error were 0.0497 and 0.1050,
  reliability was 0.9806, mask IoU was 0.8314, and fragmentation was 0.0000.
- Raw 600-object diagnostics show 0.0072-beam bias, 0.2048-beam centred p95
  scatter, and 0.2084-beam radial p95 error. The frozen endpoint remains
  binding because it aggregates within-image group tails before the outer
  percentile; the better raw diagnostic does not authorize a post-hoc change.
- The model assisted 599 of 600 B3 measurements. Median and p95 position
  uncertainties were 0.0876 and 0.1916 beams, but the p95
  error-to-uncertainty ratio was 2.56. Recorded curved-filament variance and
  correlated-noise uncertainty undercoverage as the unresolved scientific
  domains.
- The matched comparator failed 14 absolute and nine paired endpoints; B3
  failed five and zero. The reviewed decision therefore records
  `reject-corrective-a`, no selected family, and false Step 3, optimization,
  and qualification authorization in
  `config/contracts/phase-5-corrective-a-decision.json`.
- Wrote typed ignored evidence at
  `benchmark-results/phase-5/corrective-a-review.json`, SHA-256
  `b8eeaf7858b57b07d2c4ab9912e45792d2b5f59658b4f86256fb5ae801aace05`.
  Its configuration and source-tree identities are
  `74c71a6a97831d6eeb82cc200ec2187983b9e5e4864ebdefdfe6cc68584335a8`
  and `16a640a59e4f8e1aac194e5ae75aad90ed73d068b375dd5c9a74663b6aab6612`.

**Validation:** 152 focused contract, evidence, and Step 2C scientific tests
pass. `just coverage` passes 1,091 tests with 94.38% branch-aware project
coverage; all new decision-model branches are covered. The equivalence lane
passes 27 tests, the strict documentation build passes, and `just check`
passes Ruff format/lint, Pyright, 961 tests, and four expected xfails.

**Immediate next step:** obtain independent human scientific review of the
endpoint aggregation, curved-filament variance, and uncertainty calibration.
Do not revise the endpoint or estimator on the closed confirmation; any new
study requires a newly frozen confirmation population. Keep Step 3,
optimization, and qualification closed.

## 2026-08-09 — Required external source-finder evidence before Phase 5 development

**Plan phase:** Phase 5, Step 2C-P — pre-development reference comparison

- Audited the Phase 5 contract and completed evidence after the Step 2C-A
  rejection. Although the scientific-gate contract names released and pinned
  PyBDSF as compatibility references, every paired result in Steps 2B through
  2C-A compared Hebog representations with each other. No Phase 5 PyBDSF or
  Aegean result exists, so those paired passes cannot support a multiscale
  equivalence or development decision.
- Rechecked primary method documentation. PyBDSF's `atrous_do` path decomposes
  the residual after ordinary Gaussian fitting, extracts across wavelet scales,
  and merges overlapping wavelet and original islands. It is therefore the
  binding full-continuum comparator. Aegean is explicitly a compact continuum
  finder with curvature-informed Gaussian components and useful island fluxes;
  its own documentation cautions that the island flux correction does not
  generally hold for extended sources. It is binding for applicable compact,
  blended, and Gaussian-like catalogue metrics and diagnostic for diffuse
  reconstruction, masks, and multiscale provenance.
- Added Step 2C-P before production Step 3. It requires a fresh seed-disjoint
  comparison population, exact released and pinned-`master` PyBDSF references,
  a maintained pinned Aegean release, finder-neutral matching, predeclared
  applicability, power and margins, and one-look fail-closed evidence. The
  closed Step 2C-A population may not be reused and qualification stays
  unopened.
- Made the authorization rule conjunctive: Hebog must pass every absolute
  injected-truth gate, be non-inferior to both PyBDSF references over the full
  applicable continuum scope, and be non-inferior to Aegean over its applicable
  catalogue scope. A weak reference result cannot excuse a Hebog failure, and
  runtime cannot compensate for scientific inferiority.
- Required the final production implementation to repeat the comparison on
  untouched qualification data. Public or challenge data remain important,
  but real-data finder agreement without truth is diagnostic rather than a
  vote that defines correctness.

**Validation:** the strict documentation build passes. `just check` passes
Ruff format/lint, Pyright, 961 tests, and four expected xfails.

**Immediate next step:** complete the independent Step 2C-H astrometry review,
then freeze the Step 2C-P comparison protocol and fresh population before
running Hebog, either PyBDSF reference, or Aegean. Keep Step 3, optimization,
and qualification closed until both gates pass.

## 2026-08-09 — Completed the Step 2C-H astrometry technical pre-review

**Plan phase:** Phase 5, Step 2C-H — pre-review before independent scientific
decision

- Audited the frozen endpoint implementation and the closed Step 2C-A
  evidence without rerunning, tuning, or rescoring it. The binding statistic
  is a p95 of per-image group p95 values. It changes meaning with the number of
  groups in a stratum and inflated the overall, scale-2, scale-4, and
  varying-noise diagnostics relative to the direct group-level p95.
- Preserved the real curved-filament failure. Its nested and direct p95 are
  both 0.4315 beam against the unchanged 0.25-beam limit; its 0.0136-beam bias
  and 0.4294-beam centred p95 identify variance rather than stable offset as
  the dominant problem.
- Found a contract/implementation gap: the durable Phase 5 gates require both
  median and p95 position error, while the Step 2B--2C-A review contracts and
  compiler bind only p95. The closed population remains terminal and must not
  be retrospectively scored against the missing median endpoint.
- Reviewed primary radio-astronomy precedents from Condon, PyBDSF, Aegean,
  ASKAP/EMU, Hydra, and ProFound. Gaussian fitting and Condon-style errors are
  established for compact or Gaussian-component astrometry. Extended-source
  positions depend on morphology and catalogue semantics; direct segmentation
  or moment centroids remain important for irregular emission.
- Diagnosed the uncertainty as a scalar beam-area-inflated moment proxy rather
  than a complete correlated-noise position covariance. It omits model,
  component-selection, support, association, shrinkage, and background/RMS
  contributions. The stored error/uncertainty ratios raise under-dispersion
  concern but are not a defined coverage test.
- Recommended a prospective successor protocol: direct group-level median and
  p95 endpoints with whole-image cluster resampling; a direct original-pixel
  centroid baseline with evidence-gated model assistance; two-dimensional
  covariance and error-ellipse coverage; diverse curved morphologies; and
  explicit PyBDSF/Aegean position mappings. Recorded the full review in
  `docs/reference/phase-5-astrometry-pre-review.md`.

**Decision:** this AI-conducted pre-review recommends revision and does not
satisfy the independent human approval required by Step 2C-H. The closed
`reject-corrective-a` decision remains unchanged. Step 3, optimization,
Step 2C-P execution, and qualification remain unauthorized.

**Validation:** the strict documentation build passes. `just check` passes
Ruff format/lint, Pyright, 961 tests, and four expected xfails.

**Immediate next step:** obtain an independent human decision on the six
questions in the pre-review. If revision is approved, freeze a new development
matrix, estimator/uncertainty comparison, power audit, and seed- and
geometry-disjoint confirmation before viewing any new output.

## 2026-08-09 — Approved the Step 2C-H astrometry recommendations

**Plan phase:** Phase 5, Step 2C-H — human scientific decision

- Gemma Danks approved all six recommendations in the astrometry technical
  pre-review: direct group-level median and p95 endpoints with image-cluster
  resampling; explicit extended-position and external-mapping semantics; a
  direct-pixel baseline with evidence-gated model assistance; two-dimensional
  correlated-noise covariance; morphology-stratified coverage; and fresh
  development and confirmation populations.
- Added the machine-validated decision
  `config/contracts/phase-5-astrometry-human-decision.json`, binding the closed
  Step 2C-A decision and pre-review checksums. The decision preserves the
  closed confirmation and authorizes only successor-protocol freezing and
  development execution.
- Kept confirmation execution, Step 2C-P execution, Step 3, optimization, and
  qualification closed. Confirmation requires a separately frozen estimator
  after development-only comparison.

**Validation:** focused contract tests pass.

**Immediate next step:** freeze the fresh diverse astrometry development and
confirmation manifests and successor pre-results protocol before changing or
executing an estimator.

## 2026-08-09 — Froze the successor Phase 5 astrometry protocol

**Plan phase:** Phase 5, Step 2C-H — prospective astrometry revision

- Froze a fresh 40-image development population and a sealed, seed-disjoint
  400-image confirmation population before changing the estimator. Four
  morphology/geometry families vary curve, orientation, knot contrast, source
  width, beam, WCS, scale, edge, invalid-pixel, and truncation conditions.
- Bound direct group-level median and p95 position errors to whole-image
  cluster bootstrap inference, with the unchanged 0.10/0.25-beam gates and no
  per-image nested percentile gate.
- Bound development-only selection between a direct observable-pixel centroid
  and covariance-gated model assistance. Model assistance must improve p95 by
  at least 0.02 beam while satisfying availability, adequacy, absolute, and
  uncertainty-coverage requirements; otherwise the direct estimator wins.
- Required positive-definite two-dimensional pixel and sky covariance using
  the full Gaussian beam correlation, a local WCS Jacobian, and repeated-noise
  coverage at 68% and 95% across the declared morphology and support strata.
- Kept confirmation execution, external comparison, Step 3, optimization, and
  qualification unauthorized until a development-only estimator is frozen.

**Frozen identities:** successor protocol
`de7265384d8c591e776bbd21bd5488e68144ee8d3dd670277f496dea46a5d917`;
development manifest
`5e9da7471f9ca33053421bf3fed6e9583e4ac0e9c3a0b230cd15f48b35159636`;
confirmation manifest
`0cb216ad04469169a45a19e0d2b9eb51b84d4fee6f03ffd6dccce413c00659f7`.

**Validation:** 188 focused dataset, contract, and freezer tests pass.

**Immediate next step:** add test-first direct and model-assisted estimator
endpoints with calibrated two-dimensional covariance, then compare them on the
development population only.

## 2026-08-09 — Rejected both prospective Step 2C-H estimators

**Plan phase:** Phase 5, Step 2C-H — prospective astrometry development

- Implemented the direct signed original-residual flux centroid and a
  covariance-gated Gaussian-assisted comparator without changing residual B3
  detection, support ownership, association, photometry, or false-positive
  control. Added full rotated Gaussian beam covariance in pixel coordinates
  and local-WCS sky covariance.
- Implemented the approved direct group-level median and p95 endpoints with
  10,000 whole-image cluster-bootstrap resamples, plus globally calibrated 68%
  and 95% Mahalanobis coverage across morphology, SNR, scale, edge,
  invalid-pixel, truncation, and estimator-disposition strata.
- Ran only the fresh 40-image development population. It supplied 240 unique
  astronomical group observations per candidate. The sealed 400-image
  confirmation was not generated, inspected, or opened.
- The direct estimator recorded overall median/p95 errors of 0.0974/0.2730
  beam, covariance scale 2.5721, 17 failed endpoint strata, and 17 failed
  coverage strata. The Gaussian-assisted estimator recorded 0.0860/0.3068
  beam, covariance scale 1.1618, 15 failed endpoint strata, and 11 failed
  coverage strata. Its 4.58% inadequate-model fallback rate passed the 5%
  admission limit, but its tail was worse rather than at least 0.02 beam
  better.
- Recorded `reject-astrometry-candidates` in
  `config/contracts/phase-5-astrometry-selection-decision.json`. Confirmation
  execution, Step 2C-P, Step 3, optimization, and qualification remain false.

**Evidence:** ignored typed development evidence
`benchmark-results/phase-5/astrometry-development.json`, SHA-256
`919e19345028c16496f4b18199266d82d4e7b604ce865743b20d38c7ebd5c1d8`;
committed decision SHA-256
`567512af8220c041767d08f6313b8ccc62b0f429e77758f2e39075751314a2a5`.

**Decision:** neither estimator is eligible. Aggregate overall coverage does
not compensate for governed stratum failures. The successor confirmation
remains sealed and may not be opened after a development rejection.

**Validation:** 162 focused astrometry, evidence, and contract tests pass. The
branch-aware coverage lane passes 1,117 tests with four expected xfails and
94.44% project coverage; the new astrometry review module is 94% covered. The
scientific-equivalence lane passes 27 tests. Ruff format/lint, Pyright, 987
fast handoff tests with four expected xfails, and the strict documentation
build pass.

**Immediate next step:** obtain renewed human scientific review before
freezing another estimator/endpoint revision. Keep Step 2C-P execution and all
downstream development closed.

## 2026-08-09 — Reviewed and froze the Step 2C-HR position split

**Plan phase:** Phase 5, Step 2C-HR — extended-position semantics and fresh
pre-results protocol

- Audited only the rejected Step 2C-H development evidence. Direct and
  Gaussian-assisted offsets were not materially biased; failures concentrated
  in irregular morphology and support strata. Diagnostic truth-support and
  estimator-interpolation probes did not justify another tuned hybrid.
- Reviewed PyBDSF, Aegean, Selavy, ProFound, Condon Gaussian-error theory, the
  ASKAP/EMU challenge, and Hydra. The common product distinction is between a
  fitted compact/component centre and a centroid or peak tied to an extended
  source segment/model.
- Recorded a prospective split: Phase 4 compact/component astrometry and its
  0.10/0.25-beam gates remain unchanged. An irregular extended object instead
  reports a detected-segment flux centroid and a separate peak, neither of
  which claims to locate the host galaxy.
- Froze 80 fresh development images and 400 sealed confirmation images. All
  governed source morphologies, not only curved filaments, vary in geometry,
  size, orientation, contrast, beam, WCS, noise, edge, invalid-pixel, and tile
  conditions. Seeds start at 2026760001 and 2026770001 and are disjoint from
  every earlier campaign.
- Froze one morphology-neutral original-pixel segment estimator. Development
  requires complete availability and one-sided 95% confidence bounds no larger
  than 0.10 beam for signed-axis bias and 0.50 beam for radial p95 in every
  applicable governed stratum. Position uncertainty remains explicitly
  unavailable until nonlinear support-selection uncertainty is calibrated.
- Before any development result was generated, added the exact corrective-A
  detection-protocol checksum to the frozen review so the runner cannot change
  the residual-B3 detection and association settings independently.

**Evidence identity:** technical review SHA-256
`cd377693b64762d02908d6a175b1a370a0090d23354f3e163d339ae81dea64fc`;
protocol SHA-256
`0fec937aeb90dec119993529af04fb5a431aeb070ab483d713abf8c91972037f`;
development-manifest SHA-256
`c96faa8e6bf15bd324a56a5ca37c036f5361f678d1722d6d775c8a2e929587eb`;
sealed-confirmation-manifest SHA-256
`0e0c360a95044e155b489670d50de6c0ef41ccb3b314354a56388e208d2b87c7`.

**Decision:** implement and execute development only. This Codex review is not
independent human scientific approval. Confirmation, Step 2C-P, Step 3,
optimization, and qualification remain unauthorized.

**Immediate next step:** implement the typed position products and frozen
segment estimator, then run the 80-image development protocol without opening
confirmation.

## 2026-08-09 — Implemented the Step 2C-HR segment-position candidate

**Plan phase:** Phase 5, Step 2C-HR — development candidate implementation

- Added a pure original-pixel position kernel that measures the signed-flux
  centroid and row-major-first brightest pixel on the exact accepted source
  segment. Empty finite support and non-positive segment flux return typed
  unavailability; no dilation, Gaussian fit, morphology branch, or truth
  coordinate enters the estimator.
- Replaced the provisional extended-measurement schema directly with version
  2. It names the centroid and peak separately, makes the absence of a host
  claim explicit, separates flux and position uncertainty status, and forbids
  a position covariance until support-selection uncertainty is calibrated.
- Added the development evaluator and compiler for exact availability,
  whole-image-cluster signed-axis bias, radial p95 repeatability, and
  non-binding old-target/median diagnostics. Passing development can only
  become `eligible-awaiting-human-review`; confirmation and downstream gates
  remain false.
- Added a versioned exploratory evidence document and a runner that accepts no
  confirmation input, verifies the protocol, base residual-B3 contract, prior
  decision, and development-manifest checksums, and refuses to overwrite an
  existing result.
- Final code review found and corrected one fail-closed harness gap: the
  compiler now rejects an observation population that omits any governed
  astronomical stratum instead of allowing that stratum to disappear from the
  decision.

**Validation:** focused estimator, schema, compiler, and evidence tests pass;
Ruff and Pyright pass before development execution.

**Immediate next step:** commit the implementation, run only the frozen
80-image development manifest, and review every applicable stratum.

## 2026-08-09 — Step 2C-HR development passed technical review

**Plan phase:** Phase 5, Step 2C-HR — fresh development decision

- Ran only the authorized 80-image development manifest with committed source
  tree `91193c9df23c1a2089001fa6dacf0c8e37e5c2a22d0b73163ef34db9c11b209f`.
  The runner verified the frozen protocol, base residual-B3 protocol, prior
  decision, and development manifest; no confirmation input was accepted.
- All 480 eligible astronomical groups produced a segment position. All 60
  binding endpoints across overall and 14 governed astronomical strata
  passed. Overall x/y absolute-mean-offset upper bounds were
  0.0105355/0.0146986 beam against 0.10; overall radial p95 was 0.298231 beam
  with a 0.318332 upper bound against 0.50.
- The limiting 0.488746-beam radial-p95 upper bound belonged to one shell
  cohort labelled by `above-compact-deblend-limit`, `morphology-shell`, and
  `tile-corner`, leaving only 0.011254 beam of margin. The tile-boundary bound
  was 0.462552 beam. This narrow result is a confirmation risk, not a reason
  to tune on development.
- The overall diagnostic radial median was 0.0856210 beam. The diagnostic p95
  against the former full-observable-domain target was 0.300144 beam and did
  not enter selection.
- Recorded the machine-validated technical decision as
  `retain-candidate-for-human-review`. The ignored evidence SHA-256 is
  `c0a51dff38f0f7b925e5fbfaf98fabbab737ce20b22f09452826fb16ea426e23`;
  its configuration SHA-256 is
  `d7429ef8309c090f5daece15eb7cfb693dc6fea26988b3c2681f731bb366acb8`.
  The evidence remains exploratory, and every confirmation and downstream
  authorization remains false.

**Validation:** 249 focused contract, evidence, estimator, compiler, and
schema tests passed. The branch-aware suite passed with 1,136 tests plus four
expected failures and 94.33% project coverage; the new segment estimator has
100% coverage. The 91-test contract lane left no misses in the new decision
model. All 27 equivalence tests passed, the strict documentation build passed,
and `just check` passed with 1,006 tests plus four expected failures.

**Review conclusion:** the result supports the declared segment-location
semantics but is not comparable as an astrometric improvement over the old
full-emission target. Synthetic-only evidence, the narrow shell margin,
unavailable support-selection uncertainty, and pending like-product PyBDSF
and Aegean comparison remain material risks.

**Immediate next step:** obtain named human scientific review of the position
meaning, half-beam irregular-tail gate, and narrow shell margin before any
one-look confirmation authorization. Do not tune or open confirmation.

## 2026-08-09 — Human review authorized Step 2C-HR confirmation only

**Plan phase:** Phase 5, Step 2C-HR — confirmation authorization

- Gemma Danks approved the reviewed compact/irregular position split, the
  0.10-beam axis-bias and 0.50-beam radial-p95 irregular gates, proceeding
  despite the 0.488746-beam limiting shell bound, keeping position uncertainty
  unavailable, and one-look confirmation without tuning.
- Recorded the interactive project-owner approval in the machine-validated
  `phase-5-astrometry-follow-up-human-decision.json`, SHA-256
  `02124201a45ecc9e88ac9542de1f6ee0fa5a5a0a43759247bc696c68170664ab`.
  It binds the frozen protocol, development decision and evidence, candidate,
  and confirmation manifest.
- The decision authorizes confirmation execution only. Step 2C-P, Step 3,
  optimization, and qualification remain false.

**Immediate next step:** commit this authorization, then implement and commit
a checksum-validating one-look confirmation runner before opening the sealed
population.

## 2026-08-09 — Implemented the Step 2C-HR one-look confirmation runner

**Plan phase:** Phase 5, Step 2C-HR — confirmation execution boundary

- Added a separate confirmation evidence schema that requires the regression
  role, at least 400 images, all overall endpoint types, named human review,
  an explicit one-look-complete state, no post-confirmation development
  tuning, and every downstream authorization false. Raw evidence remains
  exploratory until a separate decision reviews it.
- Added a one-look runner that refuses existing output and verifies the frozen
  protocol, base residual-B3 protocol, development decision, ignored
  development evidence, human decision, selected candidate, and confirmation
  manifest before evaluating an image.
- Kept the committed development runner unchanged and did not read or execute
  the confirmation population during implementation.

**Validation:** focused authorization, runner, and evidence tests pass. The
branch-aware suite passed with 1,139 tests plus four expected failures and
94.36% project coverage; all new confirmation-evidence validation branches
are covered. The complete evidence lane passed 71 tests, the strict docs build
passed, and `just check` passed with 1,009 tests plus four expected failures.

**Immediate next step:** complete full validation and commit the runner, then
execute the authorized 400-image confirmation exactly once.

## 2026-08-09 — Step 2C-HR one-look confirmation passed

**Plan phase:** Phase 5, Step 2C-HR — confirmation decision

- Executed the sealed confirmation once from committed runner `0e37424` after
  committed human authorization `562f86e`. The run evaluated 400 images and
  2,400 eligible astronomical groups without post-development tuning.
- All 60 binding endpoints passed. Availability was 1.0; overall x/y
  absolute-mean-offset upper bounds were 0.00431787/0.00407039 beam against
  0.10; and overall radial p95 was 0.295771 beam with a 0.310348 upper bound
  against 0.50.
- The shell cohort again supplied the `above-compact-deblend-limit`,
  `morphology-shell`, and `tile-corner` limiting strata. Its radial-p95 upper
  bound was 0.488331 beam, independently reproducing the narrow development
  margin. Tile-boundary was 0.430297 beam; every other radial-tail bound was
  at most 0.324638 beam.
- The overall diagnostic radial median was 0.0867493 beam. Diagnostic p95
  against the former full-observable-domain target was 0.329930 beam and did
  not enter the decision.
- The ignored evidence SHA-256 is
  `6a9ca9be593d3f5c04a190869be709f698ff1582c570a55052c3ea4a7238e87a`;
  configuration SHA-256 is
  `621c6192445be3b4bf556e9c2291379313daf450f3cac82b7e861ca45c48e48e`;
  and source-tree SHA-256 is
  `f448a0be0a08ce6d62b35a17522ba8d93686d10e21453448070710b580a97ab2`.
- Recorded `confirm-candidate-for-external-comparison` in a machine-validated
  decision. Confirmation is closed after one look. Only Step 2C-P protocol
  freeze is authorized; external execution and every later gate remain false.

**Review conclusion:** confirmation supports the declared irregular segment
location and repeats the development result without tuning. It does not
establish host astrometry, calibrated position uncertainty, external-finder
non-inferiority, or production readiness. The persistent narrow shell margin
must remain visible in Step 2C-P and later qualification.

**Validation:** the branch-aware suite passed with 1,140 tests plus four
expected failures and 94.43% project coverage; the new decision validator has
focused coverage of all branches. All 27 equivalence tests and the strict docs
build passed. `just check` passed with 1,010 tests plus four expected
failures.

**Immediate next step:** freeze the complete fresh Step 2C-P external-finder
comparison protocol before generating any Hebog, PyBDSF, or Aegean output.

## 2026-08-09 — Froze the Step 2C-P external-comparison protocol

**Plan phase:** Phase 5, Step 2C-P — pre-results protocol freeze

- Froze 600 full-continuum images across four reviewed geometry, beam, and WCS
  configurations and 800 compact/blend images. All 1,400 noise seeds are new
  and globally disjoint from every checked-in historical manifest. Only
  reviewed analytic generator designs are reused; no finder output or prior
  result enters the new populations. Phase 5 qualification remains unopened.
- Bound released PyBDSF 1.14.1 and pinned `master` `c70103b` to their existing
  immutable images and dependency inventories. Both use Rapthor's residual B3
  à trous profile with three scales, 5/3-sigma thresholds, and operational
  background/RMS as primary; a same-map diagnostic is separately labelled.
- Selected maintained AegeanTools 2.3.5 as the catalogue comparator. Verified
  published wheel SHA-256 `dda95cb...`, smoke-tested the CLI, and captured
  isolated image digest `sha256:ca5fd09...` plus dependency-inventory SHA-256
  `74f3787...`. Isolation is required because Aegean 2.3.5 requires NumPy 2.x
  while the governed PyBDSF image retains NumPy 1.26.
- Froze Aegean's blind 5/4-sigma covariance-enabled primary run with internal
  background/noise estimation and a separately labelled 5/3-sigma same-map
  diagnostic. Its compact, blended, Gaussian-like, and mixed catalogue products
  are binding. Diffuse, filament, shell, mask, and multiscale-provenance
  products outside its design are diagnostic or unavailable, never implicit
  passes or failures.
- Froze truth-first, no-cross-finder association. The matcher retains
  secondary eligible edges after deterministic primary assignment so
  one-to-one matching cannot hide duplicates, splits, or merges. Like-product
  mappings keep compact Gaussian centres separate from Hebog's confirmed
  irregular detected-segment centroid and limit PyBDSF source moments to
  semantically aligned groups.
- The conservative prospective power lower bounds are 0.998392 for continuum,
  0.909784 for three-reference compact comparison, and 0.908176 jointly. An
  observed per-image variance above any planning bound makes the comparison
  underpowered and fails closed; sample size cannot adapt after opening.
- Final code review found that mask precision and mask recall were binding but
  initially represented only by the mask-IoU planning family. Added both as
  explicit prospective power families and a generator-equality regression
  test before freezing the final identity; the conservative rounded bounds are
  unchanged.
- Deferred a public challenge cut-out to Step 6 because the controlled host
  has no redistributable, checksum-bound input with curated or injected truth.
  Real-data finder agreement remains diagnostic rather than ground truth.
- The protocol SHA-256 is
  `b9db9adbd1cae1a8c11a081b0af245e3e8dca8979bce9e2dc0ffda968c5d2d72`;
  continuum and compact/blend manifest SHA-256 values are respectively
  `9f88b8904b264e61c5a7445fd8a0cc966cf928d072d010dce3c6d47b6e8e6193`
  and `55c6ecef09711219e45f3e6192cea130b17a02bded6b10e72e1a839743ce2e32`.

**Validation:** the focused contract, freezer, disjointness,
overwrite-refusal, generated-document equality, and dataset-identity suites
pass (213 tests); Ruff passes on every changed Python file;
`just test-equivalence` passes 27 tests; the strict documentation build passes;
and `just check` passes, including Pyright and 1,014 unit/doctest cases with 4
expected failures. `just coverage` passes with 1,144 tests, 4 expected failures,
and 94.48% branch-aware project coverage. The final pre-commit check remains
pending.

**Immediate next step:** implement and test the frozen matcher, FITS
materializer, and isolated Hebog/PyBDSF/Aegean runners, then bind their
committed hashes in a separate execution decision. Do not generate finder
output before that review.

## 2026-08-11 — Implemented the Step 2C-P external execution boundary

**Plan phase:** Phase 5, Step 2C-P — pre-execution implementation

- Implemented the finder-neutral truth-first matcher. Compact eligibility is
  limited to half a beam; extended eligibility uses the frozen support-overlap
  or one-beam-dilation clauses. Primary assignment maximizes cardinality,
  overlap, and proximity in order, while every eligible secondary edge remains
  available for split, merge, and duplicate metrics.
- Added a deterministic shared-input materializer. Each declared realization
  produces canonical `input.json` metadata and byte-identical four-axis
  float64 image, analytic-mean, and analytic-RMS FITS files with checksums,
  beam, WCS, recipe, and seed identity. Undeclared seeds, manifest drift,
  artifact drift, and overwrite attempts fail closed.
- Added maintained PyBDSF source and Gaussian-component readers, an Aegean
  component/island reader with deterministic identifiers, Aegean's explicitly
  non-segmentation three-sigma fitted-ellipse proxy, and canonical Hebog
  compact/extended product mappings. PyBDSF Gaussian centres remain separate
  from source moments; Aegean random UUIDs never enter matching.
- Added isolated one-realization Hebog, released/master PyBDSF, and Aegean
  runners. They require a future named execution decision bound to the exact
  protocol, residual-B3 review, committed source tree, runner scripts,
  containers, dependency inventories, and PyBDSF core count. Successful raw
  results publish atomically with artifact hashes; finder exceptions remain
  typed image-denominator failures and partial products are discarded.
- Review found that PyBDSF checks `rms_box` before honoring supplied
  `rmsmean_map_filename` products. The frozen 150-pixel box exceeds one
  quarter of the 512-pixel compact image, so that controlled diagnostic would
  silently ignore the shared maps. The runner instead marks it unavailable.
  Operational primary results and the 1,024-pixel continuum controlled leg are
  unaffected. This scoped limitation must be accepted or the design revised
  before execution authorization.
- No Hebog, PyBDSF, or Aegean output from the fresh external population was
  generated. Step 3, optimization, and qualification remain false.

**Validation:** 71 focused matcher, materializer, product, runner, and compact-
input tests passed. The full Pyright project check reported no errors. The
branch-aware suite passed with 1,170 tests plus four expected failures and
93.95% project coverage; changed validation modules were 87--98% covered
except the broader product-reader module at 71%, whose uncovered lines are
predominantly older reference-manifest paths. All 27 equivalence tests and the
strict documentation build passed. `just check` passed, including Ruff,
Pyright, and 1,040 unit/doctest cases with four expected failures. The final
all-files `just pre-commit` gate also passed cleanly.

**Immediate next step:** complete review and commit this implementation, then
obtain named approval of the 512-pixel diagnostic limitation, exact Hebog
runtime, and PyBDSF core count. Only then create a separate decision bound to
the committed source-tree and runner hashes. Do not execute or inspect any
external-finder output before that decision.

## 2026-08-11 — Prepared the immutable Step 2C-P Hebog runtime

**Plan phase:** Phase 5, Step 2C-P — pre-execution runtime preparation

- Gemma Danks approved the unavailable 512-pixel PyBDSF controlled-background
  diagnostic, four PyBDSF cores, and preparation of an immutable Hebog runtime.
  This did not authorize the final one-look decision or external-finder
  execution.
- Built the existing `Dockerfile` runtime target from a temporary clean
  `git archive` of commit
  `106715b22b9858149e42467f4e2c581f15961cb0`. The resulting local
  `localhost/hebog:phase5-external-106715b` Linux/arm64 image has immutable
  digest
  `sha256:b92080db558246e2ae781c69f6caf39fef8e393ab74ea6774d9b02672981b4ce`
  and carries the complete commit as an OCI revision label.
- The Python 3.14.7/Hebog 0.6.0 runtime contains 35 installed distributions.
  Its canonical dependency-inventory SHA-256 is
  `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2`.
  Its baked source-tree SHA-256 is
  `471bed9a428df10d9139afc334d97b5df190f4f64e6dd6daeb91f9b436d37362`,
  exactly matching the committed checkout.
- Recorded the resolved arm64 parents: `python:3.14-slim` at
  `sha256:c65a4a1140b75416bbc7f28807f82a3746bd6567645d5848123b6a6587f86962`
  and `ghcr.io/astral-sh/uv:0.9.16` at
  `sha256:d8b6f79959466b3e45efebd7143f1d6e3bb72a1c6f9482fd154edbc5331b9299`.

**Validation:** `hebog --version`, validation-module imports, the read-only
runner `--help` path, a residual-B3 detection on a 64-by-64 all-zero smoke
image, and the complete compact branch on the existing Phase 0 256-pixel
development fixture all passed inside the image. The compact smoke case
returned its expected three sources. No external-comparison input or finder
output was generated or inspected.

**Immediate next step:** present the exact protocol, candidate-review,
implementation, source-tree, runner, container, dependency, and four-core
identities for final named approval. Only after that approval may the separate
one-look execution decision be written and committed.

## 2026-08-11 — Authorized the Step 2C-P one-look execution

**Plan phase:** Phase 5, Step 2C-P — final pre-execution decision

- Gemma Danks explicitly approved the final one-look execution decision bound
  to the presented protocol, candidate-review, implementation, source-tree,
  runner, Hebog-container, dependency-inventory, and four-core PyBDSF
  identities.
- Wrote the immutable authorization as
  `config/contracts/phase-5-external-execution-decision.json`. It records
  `one_look_opened=false` and keeps Step 3, candidate-specific optimization,
  and qualification false. A focused regression test recomputes the protocol,
  candidate-review, source-tree, and runner hashes from the checkout and
  requires the exact approved runtime and named reviewer.
- The decision authorizes one complete terminal comparison, not interactive
  execution of individual realizations. No finder process was started and no
  one-look output was opened while writing the record.

**Validation:** the decision-drift test first failed because the authorization
file was absent, then passed after the exact approved record was written. All
nine focused external-comparison boundary tests passed, as did the strict
documentation build and `just check` with Ruff, Pyright, 1,041 unit/doctest
cases, and four expected failures.

**Immediate next step:** implement and review the complete-population launcher
that privately stages every frozen leg and publishes only after all legs are
terminal. The approved one-look must remain unopened until that boundary is
ready.

## 2026-08-11 — Sealed the Step 2C-P complete-population launcher

**Plan phase:** Phase 5, Step 2C-P — terminal campaign boundary

- Implemented the only supported launcher for the approved external
  comparison. It expands the frozen 600-image continuum and 800-image
  compact/blend populations into exactly 1,400 common inputs and 7,000
  applicable finder/mode runs before writing any state.
- Added a no-write preflight that verifies the protocol, decision, candidate
  review, production source tree, runner hashes, manifest recipes, four local
  container digests, shared platform, and four-core PyBDSF allocation. The
  canonical request also binds the launcher checksum and inspected image IDs.
- Containers execute those immutable local image IDs with networking disabled,
  a read-only repository mount, and only the hidden campaign directory
  writable. Review corrected an earlier draft that inspected immutable IDs but
  would still have executed mutable tags.
- Added deterministic private staging, explicit exact-request resume, serial
  execution, retained infrastructure logs, typed finder failures, complete
  input/result and artifact verification, private-temporary-remnant refusal,
  and atomic terminal publication. Resume accepts the exact canonical terminal
  manifest if an interruption occurred after sealing but before the final
  rename.
- The approved-container `--preflight-only` run passed with request SHA-256
  `182944e174098544092a8e48490bdbfd39f7d9e332a9beb586b1db2441522ef7`.
  Both the public target and deterministic hidden staging path remained
  absent. No realization was materialized and no Hebog, PyBDSF, or Aegean
  finder process was opened.

**Validation:** all 11 focused launcher tests passed, including the complete
matrix, immutable command, resume, infrastructure-failure, partial-publication,
temporary-remnant, and rename-interruption cases. Focused Ruff and Pyright
checks passed. The strict documentation build passed. The branch-aware suite
passed 1,182 tests with four expected failures and 93.94% project coverage.
`just check` passed Ruff, Pyright, and 1,052 unit/doctest cases with four
expected failures. Scientific equivalence was not rerun because this change
does not alter scientific code, configurations, inputs, or outputs.

**Immediate next step:** invoke this exact launcher once without
`--preflight-only` to run the approved sealed campaign. Do not inspect hidden
staging or partial outputs. After terminal publication, review scientific
outcomes before runtime and keep Step 3, optimization, and qualification
closed until the separately reviewed decision permits otherwise.

## 2026-08-11 — Froze the external decision kernel and found a compiler gap

**Plan phase:** Phase 5, Step 2C-P — pre-results scientific evaluation review

- Implemented a checksum-bound, absolute-first decision kernel without
  changing `src/hebog/` or the approved immutable candidate runtime. The
  evaluator requires exact image and endpoint populations, every binding
  reference, finite endpoint evidence, paired upper limits within their
  practical margins, and observed paired standard deviations within the
  prospective power bounds. It fails closed for unavailable references,
  incomplete populations, and duplicate endpoint identities; absolute truth
  failures cannot be compensated by external-reference results. It recomputes
  each paired point regression from the candidate/reference values and
  desirable direction so a compiler cannot invert the comparison. It also
  separates absolute decision values from paired point estimates; in
  particular, the irregular radial-p95 absolute gate uses its one-sided 95%
  upper confidence bound rather than its lower point estimate.
- Added `config/contracts/phase-5-external-evaluation.json`, which recomputes
  its policies from the frozen external protocol, Phase 4/5 gates, Phase 4
  metric registry and decision engine, and the confirmed irregular-position
  review. The mapping now prevents a previously ambiguous flat position gate:
  compact components retain 0.10/0.25-beam radial median/p95 limits, while
  irregular segments retain 0.10-beam signed-axis bias and 0.50-beam radial
  p95. Irregular radial median is report-only and cannot be substituted for
  the signed-axis bias endpoint.
- Added synthetic decisions for a passing endpoint, absolute failure despite
  paired success, unavailable binding references, observed variance above the
  planning bound, incomplete image and endpoint populations, duplicate
  endpoint-registry identities, and evaluator/upstream-contract drift.
- The review found no raw-product science compiler or prospective exact
  endpoint registry in the repository. Runners and the truth-first matcher
  produce and associate products, but nothing yet derives every governed
  absolute and paired sufficient statistic and feeds the terminal decision.
  Hand-assembled summaries would leave room for post-results applicability,
  missingness, and statistic choices, so campaign execution is now explicitly
  blocked until the compiler and registry are implemented, tested on synthetic
  and already-viewed evidence, hash-bound, and reviewed.
- Reviewed the Continuum absolute evidence and runner boundary. The revised
  detected-segment position passed 60/60 development and 60/60 confirmation
  endpoints, but the shell/tile-corner radial-p95 bound remains narrow at
  0.4883 versus 0.50 beam after independently reproducing 0.4887 in
  development. Two more complex astrometric candidates had already performed
  worse. Retuning this transparent estimator before the unopened campaign
  would invalidate the candidate/protocol/runtime identities and risk
  optimizing a reproduced morphology-specific tail, so no algorithm change is
  recommended from the closed evidence.
- Audited the validation-only four-beam Continuum photometry aperture against
  all four frozen external geometries. Each has six astronomical truth groups;
  no dilated truth support overlaps another group, and the nearest group
  separations are 36.7--51.8 beam FWHM. Neighbour contamination therefore
  should not affect this campaign's absolute flux result. The population does
  not, however, qualify close extended-source photometry for general use; that
  remains a Step 3/6 test obligation rather than a reason to alter this frozen
  pre-development candidate.

**Validation:** the focused evaluator suite first failed for the missing
implementation, then for an incorrect irregular-median interpretation and a
duplicate endpoint registry. All fourteen tests now pass; direct line/branch
coverage of the new evaluator is 81%. The combined evaluator, campaign,
matcher, product, compact-decision, and astrometry regression selection passes
71 tests. The full branch-aware suite passes 1,196 tests with four expected
failures and 93.94% project coverage; all 27 scientific-equivalence tests pass.
The strict documentation build and `just check` pass, including Ruff, Pyright,
1,066 unit/doctest cases, and four expected failures. No external-comparison
realization or finder output was created or inspected. The final all-files
pre-commit check passes cleanly.

**Immediate next step:** implement and pre-results-freeze the raw-product
science compiler and exact endpoint registry. Do not invoke the already
approved launcher without `--preflight-only` until that prerequisite closes.

## 2026-08-11 — Closed the Step 2C-P raw-product compiler prerequisite

**Plan phase:** Phase 5, Step 2C-P — pre-results science compilation

- Added the write-once terminal science compiler and prospective endpoint
  registry without changing `src/hebog/` or the approved Hebog runtime. Before
  reading scientific values, the compiler now verifies the approved execution
  decision, complete-population launcher, protocol, candidate review,
  manifests, container digests, source and dependency identities, sealed
  request, every common input, every finder result, and every artifact
  checksum.
- Froze 143 binding and 15 report-only continuum endpoints. Catalogue-row
  multiplicity defines duplicates; distinct native supports define splits and
  merges. Truth-primary matches condition flux and position while completeness
  separately retains unmatched truth, and finder failures remain in every
  image denominator. Signed x/y bias remains absolute-only; irregular radial
  median remains report-only.
- Reused the unchanged Phase 4R decision and BCa interval engines for compact
  products. The compiler derives and validates the exact 225 metric/stratum
  keys per PyBDSF reference and exact 143 applicable Aegean keys. PyBDSF uses
  Gaussian catalogue rows for the compact component contract; Aegean excludes
  only the prospectively inapplicable deconvolution, classification, and joint
  position/flux-uncertainty families.
- Bound compiler `81d1384d...`, endpoint registry `a6e469c1...`, and evaluator
  `df99e10a...` in evaluation contract `4ce9cad7...`. The evaluator
  independently recomputes the continuum population, both PyBDSF compact key
  populations, and the exact unaltered Aegean subset before applying the
  absolute-first conjunction.
- Replaced Python-per-resample endpoint loops with padded bounded image
  clusters and vectorised NumPy reductions inside the unchanged 500-sample
  SciPy BCa batches. A representative 600-image, 50,000-resample scalar
  comparison fell from 5.159 to 0.219 seconds with identical evidence; a
  ragged radial-p95 comparison completed in 4.598 seconds. These are compiler
  kernel checks only, not source-finder or end-to-end performance claims.
- Cross-checked the irregular-position adapter against the already-viewed
  development population. It reproduced 105 endpoint estimates, confidence
  bounds, and diagnostic medians exactly across 80 images and 480 group
  observations; maximum absolute difference was zero. No fresh external
  realization or result was generated or inspected.

**Validation:** 113 focused compiler, evaluator, launcher, matcher, product,
compact-decision, astrometry, and recovery tests pass. All 27 equivalence tests
pass. The branch-aware suite passes 1,208 tests with four expected failures and
93.95% project coverage, including the Dask lanes with loopback permission.
The direct `just check` equivalents pass Ruff, Pyright, and 1,081
unit/doctest cases with four expected failures; the strict documentation build
passes. `uv run` itself panicked in this restricted macOS host's system proxy
discovery, so the already-synchronized `.venv` executables ran the identical
commands. The final all-files `just pre-commit` run passes cleanly, including
the lock check.

**Immediate next step:** execute the already-approved complete-population
launcher once, without `--preflight-only`, and do not inspect private staging.
After atomic terminal publication, run the frozen compiler and evaluator once
and review science before runtime. Step 3, optimization, and qualification
remain closed unless that decision passes and receives review.

## 2026-08-11 — Reconstructed the lost Step 2C-P runtime images

**Plan phase:** Phase 5, Step 2C-P — campaign runtime recovery

- Confirmed that all four previously approved local OCI images had been
  removed before the one-look opened. Their historical digests remain frozen
  evidence but cannot be recreated or silently replaced in the approved
  execution decision.
- Rebuilt Hebog from the clean
  `106715b22b9858149e42467f4e2c581f15961cb0` archive. The reconstructed
  Linux/arm64 image is `sha256:f78be6d...`; it reproduces the exact
  `471bed9...` source-tree hash and `d383be3...` 35-distribution inventory.
  Python remains 3.14.7 and Hebog remains 0.6.0.
- Rebuilt released PyBDSF 1.14.1 from the exact published `8d5113f...`
  sdist and installed the exact frozen `2f1fdfb...` master wheel into a
  separately targeted copy of the same minimal Python 3.12.3 Linux/arm64
  runtime. The new image digests are `sha256:7245407...` and
  `sha256:192964b...`; inventory hashes are `8211043...` and `83574dd...`.
  Their complete package inventories are identical except for the `bdsf`
  version.
- Rebuilt AegeanTools 2.3.5 from the exact published `dda95cb...` wheel in an
  isolated Python 3.12.3 Linux/arm64 runtime. Its new image digest is
  `sha256:6dd2064...` and its dependency-inventory hash is `17d1e3c...`.
- Added pinned, checksum-verifying build definitions and complete resolved
  Python requirement sets under `scripts/benchmark/containers/phase5/`.
  These make future reconstruction reviewable but do not claim bitwise OCI
  reproducibility: repository metadata for operating-system packages and OCI
  layer timestamps remain outside the content-addressed inputs.
- Kept the external one-look closed. No campaign input, staging directory, or
  finder result was created or inspected. The old execution decision does not
  authorize the reconstructed identities; a renewed runtime review, decision,
  and no-write preflight are now explicit prerequisites.

**Validation:** all four reconstructed images are present. Hebog's exact
source/inventory checks and CLI passed. Both PyBDSF runners imported through
the frozen launcher boundary and each processed the existing governed
256-pixel compact fixture as three sources and three Gaussians. Aegean's runner
and CLI passed; on the same fixture its blind 5/4-sigma path found three
islands and fitted six components. The canonical inventories were recomputed
inside the images. Host free space increased to 48 GiB, still below the
approximately 60 GiB safe campaign target for roughly 46 GiB of raw products.

**Immediate next step:** finish host cleanup, then review and bind the four
reconstructed image and dependency identities. Repeat the launcher's no-write
preflight against that renewed decision before opening the one-look once.

## 2026-08-11 — Made reconstructed-runtime preparation fail closed

**Plan phase:** Phase 5, Step 2C-P — renewed execution preparation

- Reviewed the external runtime delta before rebinding it. Released PyBDSF
  1.14.1 and pinned master use identical minimal Python 3.12.3 scientific
  stacks and differ only in the `bdsf` distribution. Their artifact and source
  revisions remain exact, and both reproduce three sources and three Gaussians
  on the governed 256-pixel compact fixture.
- Rejected the first Aegean reconstruction because dependency resolution had
  advanced Astropy from 7.2.2 to 8.0.1 and SciPy from 1.17.1 to 1.18.0. Built
  and smoke-tested replacement `sha256:b496d29...` with the originally frozen
  NumPy 2.5.2, SciPy 1.17.1, Astropy 7.2.2, and LMFit 1.3.4 stack. Its complete
  inventory hashes to `346c1f3...`, and its standard 5/4-sigma run again finds
  three islands and fits six components. Removed the superseded image.
- Protocol-bound the reconstructed PyBDSF release/master and matched Aegean
  identities without changing finder versions, artifacts, configurations,
  populations, endpoints, gates, or inference. Updated the protocol,
  endpoint-registry, launcher, and evaluator hash chain.
- Added an explicit `awaiting-reconstructed-runtime-approval` execution state.
  Both one-realization authorization and the complete campaign launcher reject
  this state before opening an input or private staging. Unit tests use local
  synthetic authorization only to preserve structural success-path coverage.
- Updating the runtime validator changes the complete Hebog source-tree hash,
  so the earlier reconstructed Hebog image cannot become the final campaign
  image. Execution remains false until a clean committed image is rebuilt and
  all four exact identities receive named approval.
- Removed exact untagged failed-build images and stopped build containers from
  the earlier attempt. Podman retained deeper shared layers used by other
  external build containers; the four reviewed runtime images were untouched.

**Validation:** the new fail-closed test first failed because the decision
schema accepted only authorization. The reconstructed-reference test then
failed against the historical identities. After implementation, 63 focused
external protocol, runner, launcher, compiler, evaluator, materialization, and
freezer tests pass. The full branch-aware lane passes 1,216 tests with four
expected failures and 93.96% project coverage. No campaign input, staging
path, or finder output was created or inspected; the one-look remains
unopened. Current host free space is approximately 58 GiB, close to but not
yet at the approximately 60 GiB campaign safety target.

**Immediate next step:** commit this non-authorized source state, rebuild and
smoke-test Hebog from that exact commit, and bind the resulting immutable
identity. Named approval and the no-write 1,400-input/7,000-run preflight remain
required before campaign execution.

## 2026-08-11 — Bound the final reconstructed Hebog runtime

**Plan phase:** Phase 5, Step 2C-P — final runtime preparation

- Committed the fail-closed validator and reconstructed-reference bindings as
  `303a49de3ea37af795d34e361f522a419d5c0bc2`, then built Hebog only from a
  clean archive of that commit. The final Linux/arm64 image tag is
  `localhost/hebog:phase5-external-303a49d-reconstructed-final`; its immutable
  digest is
  `sha256:728bbd7ab59d0fbb9537d36fac34652e640300091024498cbebdaeb452da55a6`.
- Recomputed the runtime identities inside the image. Its source-tree SHA-256
  is `2f80c8779d3d8fe91fc599aa98edd95491d13922667cbab3af9d178caecc225b`,
  exactly matching the committed checkout, and its 35-distribution inventory
  remains `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2`.
  The OCI revision label carries the complete implementation commit.
- Bound the final image and commit into the still-pending execution decision.
  The decision hash is `36825774...`; the refreshed endpoint-registry and
  evaluation-contract hashes are `49a76259...` and `3ed90c21...`. Execution,
  one-look, optimization, Step 3, and qualification flags remain false.
- Host free space is now 61 GiB, above the approximate 60 GiB safety target
  for roughly 46 GiB of raw campaign products.
- Removed only the superseded `sha256:f78be6d...` Hebog reconstruction after
  resolving its exact tag and digest. A final inspection confirms all four
  bound Linux/arm64 runtime digests remain present.

**Validation:** the image reports Hebog 0.6.0, the exact source and dependency
checksums above, and the expected commit label. The read-only campaign-runner
help boundary passes. The complete compact path over the governed 256-pixel
development fixture returns the expected three source identifiers. Registry
and evaluation loaders accept the refreshed hash chain. No campaign input,
staging path, or finder result was created or inspected; the one-look remains
unopened.

**Immediate next step:** obtain renewed named approval for the four exact
reconstructed runtime identities, the unchanged four-core PyBDSF allocation,
and the approved 512-pixel diagnostic limitation. Only then may the decision
be authorized and the complete no-write preflight run.

## 2026-08-11 — Renewed the reconstructed-runtime execution approval

**Plan phase:** Phase 5, Step 2C-P — final execution authorization

- Gemma Danks explicitly approved the four exact reconstructed runtime
  identities presented after the final Hebog build, the unchanged four-core
  PyBDSF allocation, the scoped 512-pixel controlled-diagnostic limitation,
  and one sealed terminal one-look execution.
- Changed only the canonical authorization triplet in the execution decision:
  status `reviewed-before-external-output`, decision
  `authorize-one-terminal-external-comparison`, and execution authorization
  true. Step 3, optimization, qualification, and one-look-opened remain false.
- The authorized decision SHA-256 is `c7e36400...`; the refreshed endpoint
  registry and evaluation-contract SHA-256 values are `498ddf18...` and
  `3a749e79...`. Runtime, source, runner, protocol, candidate, population,
  configuration, metric, and gate identities are otherwise unchanged.

**Validation:** the previously pending-state assertion failed after the
governed decision changed, then passed after being updated to require Gemma
Danks's renewed named approval and canonical authorized state. No campaign
input, staging directory, or finder result was created or inspected; the
one-look remains unopened.

**Immediate next step:** commit this authorization record, then run the exact
complete-population command with `--preflight-only`. Record the new request
identity and verify that both public and private campaign paths remain absent
before allowing terminal execution.

## 2026-08-11 — Passed the renewed reconstructed-runtime preflight

**Plan phase:** Phase 5, Step 2C-P — terminal campaign readiness

- Ran the complete-population launcher against the four approved local
  Linux/arm64 tags with `--preflight-only`. It inspected and matched every
  approved immutable digest, verified the committed protocol, named execution
  decision, candidate review, source tree, runners, and four-core allocation,
  and expanded exactly 1,400 common inputs and 7,000 applicable runs.
- The canonical unopened request SHA-256 is
  `31a56c509a354e497a9902f32d02ef77dc9d90b047c59f28239f423bed372251`.
  The superseded historical request `182944e1...` was not reused.
- Verified immediately before and after the command that neither
  `benchmark-results/phase-5/external-source-finder-comparison` nor hidden
  staging path
  `.external-source-finder-comparison.phase5-external-c7e36400e0c3.staging`
  exists. No input or finder product was written or inspected.

**Validation:** the launcher reported `preflight passed`, `images=1400`, and
`runs=7000`; the terminal and decision-specific private paths remained absent.
The one-look is unopened, all required preparation gates are closed, and the
sealed terminal campaign is ready to run once.

**Immediate next step:** execute the exact approved command once without
`--preflight-only`, do not inspect private partial products, and publish only
the checksum-verified terminal campaign. After publication, compile and review
the frozen scientific decision before opening Step 3.

## 2026-08-12 — Published the terminal external-finder campaign

**Plan phase:** Phase 5, Step 2C-P — sealed one-look execution

- Executed the exact preflighted request
  `31a56c509a354e497a9902f32d02ef77dc9d90b047c59f28239f423bed372251`
  once without `--preflight-only`. The launcher completed 1,400 common-input
  materializations and 7,000 finder runs as 8,400 serial, network-isolated
  container invocations against the four approved immutable image IDs.
- Monitored only the attached launcher, active-container process state,
  aggregate container-start count, and filesystem capacity. No private input,
  catalogue, image, log, or partial result was opened. Free space never
  approached exhaustion and recovered to 62 GiB after terminal publication.
- The launcher verified all 1,400 input bundles and all 7,000 result manifests
  and artifacts before atomically publishing
  `benchmark-results/phase-5/external-source-finder-comparison/campaign.json`.
  Its SHA-256 is
  `b9996100458d305a3553ee7c8e793513b13d9d4bd2cb428c359fd0a0cadf3a7e`,
  status is `terminal-raw-results-sealed`, and completion time is
  `2026-08-12T01:04:07.506327Z`. The decision-specific private staging path is
  absent.

**Validation:** the launcher exited zero only after reporting `verified
1400/1400 common inputs`, `verified 7000/7000 finder runs`, and the terminal
campaign path. This closes execution only; no scientific eligibility or Step
3 claim follows from raw terminal publication.

**Immediate next step:** run only the checksum-bound compiler and frozen
decision evaluator against the terminal manifest, recording scientific
outcomes before any runtime interpretation.

## 2026-08-12 — Corrected the fail-closed compact compiler role type

**Plan phase:** Phase 5, Step 2C-P — post-publication scientific compilation

- The first checksum-bound compiler attempt verified the terminal campaign and
  entered compact Phase 4R evaluation, then failed before writing an analysis
  file with `Phase 4R decision stage and dataset role differ`.
- Diagnosed the cause without inspecting raw scientific products: Pydantic's
  unchecked `model_copy(update=...)` retained the analysis-only qualification
  role as a plain string. Phase 4R deliberately compares the role by enum
  identity and therefore rejected it. The analysis output remains absent.
- Added a regression test that first failed on the string-valued role, then
  changed the copy to use `DatasetRole.QUALIFICATION`. No truth, recipe,
  stratum, finder product, endpoint, threshold, confidence rule, or decision
  logic changed.
- Rebound the corrected compiler SHA-256 `7a055891...`, endpoint-registry
  SHA-256 `d174fc9e...`, and evaluation-contract SHA-256 `fc3e9ed3...`. The
  original pre-results compiler remains recorded at `81d1384d...`; this is a
  transparent fail-closed technical correction after raw publication and
  before any scientific analysis output.

**Validation:** the new role-identity regression test passes, as do all 30
focused compiler and evaluator tests. No analysis or decision output exists.

**Immediate next step:** commit the complete type-only correction and governed
hash chain, rerun the compiler once, then apply the unchanged frozen evaluator
to its write-once output.

## 2026-08-12 — Closed the external comparison as select-neither

**Plan phase:** Phase 5, Step 2C-P — terminal scientific decision

- Committed the type-only compiler correction as `c5a2772`, confirmed that no
  analysis or decision output existed, and reran it against the unchanged raw
  campaign SHA-256 `b9996100...`. The compiler completed successfully and
  wrote analysis SHA-256 `bdc59fdc...`.
- Applied the unchanged frozen evaluator `df99e10a...`. It wrote decision
  SHA-256 `73c7e2eb...` with `status=fail`,
  `scientific_outcomes_before_runtime=true`, and Step 3, optimization, and
  qualification all false. The compact result failed and all 143 Continuum
  endpoints were indeterminate; no absolute or paired metric value was
  admitted.
- The terminal population contained 7,000 finder runs: 2,292 succeeded and
  4,708 failed. Of the 5,000 binding runs, 1,492 succeeded and 3,508 failed.
  Aegean completed 1,600/1,600, Hebog 692/1,400, released PyBDSF 0/2,000, and
  pinned-master PyBDSF 0/2,000.
- Post-decision typed failure review found 576 Hebog runs with a non-positive
  reconstructed-segment aperture flux and 132 with no finite positive local
  RMS. Each PyBDSF version failed 1,400 operational runs at the adapter's
  island-mask/label consistency check and 600 controlled-background runs
  inside PyBDSF while loading the supplied mean/RMS maps. Aegean had no runner
  failures.
- Runtime was reviewed only after the scientific failure. The serial campaign
  lasted about 7 h 12 min. Aegean median controlled/operational wall times were
  1.56/1.79 seconds and successful Hebog runs had a 2.85-second median. Failed
  leg timings are not comparable performance evidence. Per-run CPU and peak
  memory were not captured and are explicitly unavailable.

**Decision:** select no production candidate. This campaign is closed and may
inform failure diagnosis only; it must not be rescored, tuned, pooled into a
successor decision, or reused as confirmation.

**Immediate next step:** execute prospective Step 2C-PF. First reproduce and
test the PyBDSF mask/label and controlled-map contracts and Hebog's terminal
segment measurement dispositions on bounded development evidence. Then pass a
zero-unexpected-failure development matrix before freezing a new seed-disjoint
external campaign and seeking named execution approval.

## 2026-08-12 — Corrected terminal runner interoperability

**Plan phase:** Phase 5, Step 2C-PF — prospective failure correction

- Kept terminal campaign `b9996100...`, analysis `bdc59fdc...`, decision
  `73c7e2eb...`, and their checksum-bound compiler immutable. The closed
  campaign was used only to identify typed failure classes and select two
  already-opened diagnostic realizations; no science metric was recomputed,
  inspected, rescored, or promoted.
- Reproduced all four runner failure classes. Released PyBDSF 1.14.1 source
  review showed that `pyrank` is internal x/y state transposed by native FITS
  export, and that supplied mean/RMS names are resolved relative to the image
  directory. A native island with no fitted source established that catalogue
  island IDs are legitimate subsets of the detection-label population.
- Corrected the PyBDSF adapter to transpose and validate integer ranks, pass
  adjacent controlled-map basenames, require exact mask/label agreement, and
  validate Gaussian IDs as a subset of source IDs and source IDs as a subset
  of native label IDs. Both reconstructed pinned versions emitted all four
  expected products in compact operational and continuum
  operational/controlled diagnostics.
- Removed Hebog's unreviewed four-beam measurement-only segment dilation.
  Segment position and integrated flux now use the same exact accepted support;
  unmeasurable detections remain explicit in label/mask products without an
  invented catalogue row. Replaced NaN-propagating local-RMS interpolation
  with normalized masked bilinear interpolation over finite positive
  neighbours, retaining unavailable output when no weight remains.
- The formerly failing compact/blend seed `2026790678` now emitted all four
  Hebog products with 54 compact and 51 measurable segment rows. The formerly
  failing masked continuum-4 seed `2026783062` emitted all four with 12 compact
  and 8 measurable segment rows. These counts are execution diagnostics, not
  scientific acceptance results.
- Passed a 12-cell diagnostic execution-validity matrix with zero unexpected
  failures: Hebog on the two inputs; each PyBDSF reference on compact
  operational and continuum operational/controlled modes; and Aegean on both
  inputs in both modes. The continuum realization contains diffuse, shell,
  filament, edge, invalid-pixel, and varying-noise strata. The approved
  512-pixel PyBDSF controlled diagnostic remains inapplicable.
- Updated post-terminal tests so structural launcher fixtures use synthetic
  current identities while the checked-in authorization is asserted to retain
  its historical source and runner hashes. Added a targeted Ruff exception for
  the immutable terminal compiler instead of changing its bound bytes.
- Validation passed: 166 focused tests; 15 equivalence tests; `just check`
  with Ruff, Pyright, 1,098 tests, and 4 expected failures; strict MkDocs; and
  full branch-aware coverage with 1,228 passed, 4 expected failures, and
  93.98% total coverage. The diagnostic container matrix used networking
  disabled, read-only input/repository mounts, and transient outputs.

**Decision:** all known terminal runner failures are corrected and the
execution-validity gate passes. This does not reopen Step 3 or establish
scientific non-inferiority.

**Immediate next step:** prepare and review a seed-disjoint successor freeze.
Before binding it, update its prospective compiler to retain mask-only native
detections in the science denominators, then freeze new source/runtime hashes,
power, evaluator, and one-look rule and obtain named execution approval.

## 2026-08-12 — Prepared the successor mask-only compiler contract

**Plan phase:** Phase 5, Step 2C-PF — prospective successor compiler

- Added `hebog.validation.external_successor_compiler` rather than modifying
  the closed terminal compiler. Its catalogue adapter permits measurable rows
  to be a strict subset of positive Hebog/PyBDSF labels while still rejecting
  absent, missing, negative, non-canonical, and malformed island identities.
- Separated measurable catalogue objects from one topology object per native
  positive label. Catalogue rows alone govern catalogue completeness,
  reliability, duplicate, conditional flux, and conditional position
  endpoints. Every native label—including a fitless or unmeasurable label—
  governs mask overlap and support split/merge topology. A label-only recovery
  therefore stays scientifically visible without fabricated photometry or an
  invented catalogue source.
- Used TDD: four initial regressions failed with the intentionally absent
  implementation, then the completed suite passed 21 ordinary, mask-only,
  fitless, empty, artifact, malformed, and plane-identity cases with 100% line
  and branch coverage for the new module. Review-added red/green cases also
  require runtime-invalid finder and truth-role identities to fail closed. The
  no-mask-only case reproduces the terminal compiler's complete metric mapping
  exactly.
- Ran the corrected operational product path on the already-opened continuum-1
  seed `2026780001` inside both pinned, network-disabled PyBDSF containers with
  read-only repository/input mounts and transient outputs. Released PyBDSF had
  12 source rows alongside 11 native supports, with a strict catalogue-label
  subset; pinned master had 14 rows alongside 11 supports. Both prospective
  adapters completed without coercion. No truth metric was compiled or
  inspected.
- Confirmed the closed terminal compiler remains byte-identical at SHA-256
  `7a0558916ac003b71a781337dc710c99c359899c4d77f88486c1c206916b43f6`.
- Final validation passed: `just coverage` selected 1,253 tests and reported
  1,249 passed, 4 expected failures, and 94.08% branch-aware project coverage;
  the new module retained 100% line and branch coverage. `just
  test-equivalence` passed 27 tests, `just check` passed Ruff, Pyright, and
  1,119 tests with 4 expected failures, and `just docs-build` passed strictly.

**Decision:** the successor compiler's mask-only scientific interpretation is
ready for pre-results composition and identity binding. This is not a frozen
campaign, human scientific approval, or authorization to execute one.

**Immediate next step:** generate and power-audit a new seed-disjoint
population without opening finder output, then bind the reviewed compiler
composition, endpoint registry, evaluator, launcher, corrected runners, and
exact runtimes for named approval.

## 2026-08-12 — Froze the powered external successor population

**Plan phase:** Phase 5, Step 2C-PF — successor population and power audit

- Generated write-once 600-image continuum and 800-image compact/blend
  manifests from the reviewed pre-results geometry, endpoint, margin, and
  sample-size design. Their seeds occupy four continuum blocks beginning at
  `2026820001` and one compact block beginning at `2026830001`; all 1,400 are
  disjoint from 9,053 historical seeds across 35 checked-in manifests.
- Recomputed the unchanged cluster-normal, conservative-union power model
  through `PhaseFiveExternalPowerAudit`. The continuum lower bound is
  0.998392, the three-reference compact lower bound is 0.909784, and the joint
  lower bound is 0.908176, above the unchanged 0.90 gate. Observed variance
  above a planning bound still fails closed and sample size cannot adapt.
- Bound manifest SHA-256 values `906a3e8...` and `05507a6...`, candidate commit
  `c1f7eb0...`, source tree `d50be75...`, mask-only science kernel `8e38de3...`,
  and all three corrected runner hashes. Bound the exact intended dependency
  inventories for Hebog, released/master PyBDSF, and Aegean.
- Inspected only local image identities and confirmed all three immutable
  reference digests remain present. The historical Hebog image lacks the bound
  candidate source, so the freeze deliberately records no candidate digest and
  requires a clean rebuild before execution review. Network-isolated inventory
  recomputation inside all four local images exactly reproduced the four bound
  dependency hashes.
- No successor image was materialized and no finder, campaign, analysis, or
  decision output was generated or opened. Execution and qualification remain
  false. The closed terminal compiler remains byte-identical and its evidence
  chain was not rebound.
- Validation passed: 251 focused freezer, manifest, contract, and successor
  compiler tests; 1,253 tests plus 4 expected failures at 94.08% branch-aware
  project coverage; all 27 equivalence tests; strict documentation; and `just
  check` with Ruff, Pyright, 1,123 tests, and 4 expected failures.

**Decision:** the successor population passes its prospective power and global
seed-disjointness gates. Population contract SHA-256 is
`8056bbc7e124230f63b2d8c8f3f6a0d217b4bfabcb45e02c261936eda763b34b`.

**Immediate next step:** rebuild the Hebog runtime from the bound candidate
source, then compose and freeze the new verifier/compiler, endpoint registry,
evaluator, launcher, gates, exact runtimes, and one-look rule for named
approval.

## 2026-08-12 — Froze the successor external one-look composition

**Plan phase:** Phase 5, Step 2C-PF — successor pre-execution freeze

- Built `localhost/hebog:phase5-external-successor-c1f7eb0` only from a
  clean archive of candidate commit `c1f7eb0bdf5e8581e0024f0f7469c2908a22a594`.
  The Linux/arm64 image ID is `0f362268...` and immutable digest is
  `sha256:d0c1319072c3716811ed51452fe83d92be8f8d2b62a11795678f31037b7b1f68`.
  Network-disabled in-image checks reproduced source tree `d50be758...`, the
  predeclared inventory `d383be3...`, and Hebog 0.6.0. All three exact
  reference images remain present on the same platform.
- Added a successor protocol/verifier and thin runner, launcher, compiler, and
  evaluator composition around the immutable terminal mechanics. The
  composition retains the closed campaign verifier, compact compiler,
  interval engine, endpoints, absolute gates, paired margins, reference
  applicability, and failure policy. It replaces only the continuum
  catalogue/native-support interpretation with science kernel `8e38de3...`
  and the two fresh manifests. The closed compiler remains byte-identical at
  `7a055891...`; the closed campaign is explicitly ineligible for reuse.
- Froze successor protocol `9eaf49d...`, endpoint registry `a4027fc...`,
  evaluation contract `c931601...`, pending execution decision `e7f2f1c...`,
  and preflight review `200d107...`. The complete-population expansion has
  exactly 1,400 inputs, 7,000 terminal runs, and 5,000 binding runs. PyBDSF
  remains fixed at four cores; the existing 512-pixel same-map diagnostic
  limitation is unchanged.
- The pending launcher rejects execution before container inspection, input
  materialization, or staging. A direct fail-closed invocation did so and left
  its proposed output absent. No successor realization, finder product,
  analysis, or scientific decision was generated or opened.
- TDD first produced five expected missing-artifact failures. The completed
  focused successor and inherited-mechanics suite passes 144 tests; the
  successor-specific subset passes 32 tests. Ruff and Pyright pass, and the
  strict documentation build succeeds. Full branch-aware coverage passes
  1,260 tests with 4 expected failures and remains 94.08%; all 27 equivalence
  tests pass. `just check` passes Ruff, Pyright, 1,130 tests, and 4 expected
  failures.

**Decision:** the technical pre-review passes with zero scientific gate
changes. Execution remains unauthorized and the one-look unopened. The
decision-dependent hash chain must be refreshed mechanically after, and only
after, named approval.

**Immediate next step:** obtain named approval bound to preflight review
`200d107...` and the four exact runtime identities. Then refresh the pending
decision, registry, evaluation, and review hashes and run the no-write
preflight before any campaign execution.

## 2026-08-12 — Approved and preflighted the successor one-look

**Plan phase:** Phase 5, Step 2C-PF — named authorization and no-write
preflight

- Gemma Danks explicitly approved successor preflight review `200d107...` and
  the exact four Linux/arm64 runtime identities. Recorded the named approval
  in execution decision `12925d0...`; execution is authorized while the
  one-look, optimization, Step 3, and qualification flags remain false.
- Mechanically refreshed endpoint registry `69ceaa4...`, evaluation contract
  `fd76998...`, and approved preflight review `4dfb86c...`. No executable,
  population, endpoint, absolute gate, paired margin, reference scope, or
  one-look rule changed.
- Ran the exact network-disabled `--preflight-only` successor launcher against
  the approved Hebog, released PyBDSF, master PyBDSF, and Aegean images. It
  passed with request
  `931df412d3487bed9840677c1374b6c438f69b498140a7b33cf77ee3ec81a9db`,
  exactly 1,400 inputs and 7,000 runs. Both the terminal output and private
  staging path remained absent; no image, finder product, or campaign evidence
  was generated or opened.
- Post-preflight free storage is 52,648,452,096 bytes, reported as 49 GiB.
  This is below the reviewed approximate 60 GiB campaign safety target, so the
  authorized campaign remains closed until at least about 11 GiB is restored.
- The focused approval, strict-schema, hash-chain, complete-population, and
  fail-closed tests pass all 7 cases. The inherited campaign-mechanics suite
  passes all 144 cases; strict documentation builds; full branch-aware
  coverage passes 1,260 tests with 4 expected failures and remains 94.08%.
  `just check` passes Ruff, Pyright, 1,130 tests, and 4 expected failures.

**Decision:** named scientific/runtime authorization and the complete no-write
preflight pass. Storage headroom is the only current execution prerequisite;
the terminal one-look has not opened.

**Immediate next step:** restore at least 60 GiB free space, recheck the four
local image identities and output-path absence, then execute the approved
successor campaign exactly once without inspecting partial results.

## 2026-08-13 — Sealed the successor campaign and corrected compilation

**Plan phase:** Phase 5, Step 2C-PF — terminal execution and pre-analysis
technical correction

- Removed the obsolete closed campaign, then diagnosed why host free space
  remained at 45 GiB: the idle Podman VM retained 53,197 deleted file handles.
  Stopping it released the blocks and raised free space to 81 GiB. Restarting
  in the attached governed session preserved all approved images and made the
  exact no-write preflight reproduce request `931df412...` once more.
- Executed that request exactly once without inspecting partial inputs or
  finder products. The launcher verified all 1,400 common inputs and all 7,000
  finder runs before atomically publishing terminal manifest `6446705f...`.
  It records 6,939 successful and 61 typed failed runs, status
  `terminal-raw-results-sealed`, and a 10 h 29 min execution interval. The VM
  stopped cleanly after publication.
- The first checksum-bound successor compiler attempt failed closed before
  creating analysis: its reused byte-identical terminal request verifier knew
  only `phase-5-external-execution-decision` and
  `authorize-one-terminal-external-comparison`, while the separately reviewed
  successor decision deliberately uses successor-specific names. No
  scientific outcome was compiled or opened.
- Added a regression test that failed on that exact mismatch. The composed
  compiler now validates the successor decision with its strict loader and
  maps only its decision ID and approval value into the terminal verifier's
  compatibility view. The terminal compiler `7a055891...`, science kernel
  `8e38de3...`, campaign, endpoints, gates, reference scopes, and decision
  logic remain unchanged. The corrected successor compiler is `51a434da...`,
  endpoint registry `545a7ac...`, and evaluation contract `ae6a96d...`.

**Validation:** the new regression test first failed for the intended approval
name mismatch, then passed after the compatibility view was installed. All 84
focused successor, launcher, compiler, and evaluator tests pass; Ruff and the
configured Pyright environment pass. Full branch-aware coverage passes 1,261
tests with 4 expected failures and remains 94.08%. Strict documentation builds;
`just check` passes Ruff, Pyright, 1,131 tests, and 4 expected failures.

**Decision:** this is a transparent fail-closed technical correction after
raw terminal publication and before any analysis output, not a scientific
change or campaign rerun. Commit and validate the correction before invoking
the write-once compiler again.

**Immediate next step:** run the complete focused successor and inherited
compiler/evaluator suites, commit the correction and refreshed hash chain,
then compile and evaluate the unchanged sealed campaign exactly once.

## 2026-08-13 — Reused the reviewed successor protocol view

**Plan phase:** Phase 5, Step 2C-PF — second pre-analysis compiler correction

- The second write-once compiler attempt failed closed before creating an
  output because the terminal request verifier read `references` from the
  deliberately minimal successor protocol. That protocol inherits the exact
  closed-protocol reference set through the launcher's strict compatibility
  loader instead of duplicating it.
- Added a regression test that reproduced the missing inherited-reference
  view. The compiler now calls the same strict successor protocol loader used
  by the reviewed launcher, while retaining the separately tested decision-
  vocabulary mapping. The terminal compiler, sealed campaign, science kernel,
  endpoints, thresholds, confidence rules, and reference identities remain
  unchanged.
- Refreshed the checksum chain to compiler `2fd78b60...`, endpoint registry
  `99a79e5e...`, and evaluation contract `d69dd830...`. Analysis and decision
  outputs remain absent.

**Validation:** the new regression test failed first on the raw minimal
protocol and passed after the reviewed compatibility view was installed. All
85 focused successor and inherited compiler/evaluator tests pass. Full
branch-aware coverage passes 1,262 tests with 4 expected failures and remains
94.08%; the three Dask tests that cannot bind sockets in the sandbox pass in
the permission-matched run. Strict documentation builds, and `just check`
passes Ruff, Pyright, 1,132 tests, and 4 expected failures.

**Decision:** this is a second transparent metadata-composition correction,
not a scientific change, rescore, campaign rerun, or additional look.

**Immediate next step:** validate and commit the correction, then invoke the
write-once compiler and unchanged evaluator without inspecting runtime first.

## 2026-08-13 — Compiled the successor analysis and corrected evaluation

**Plan phase:** Phase 5, Step 2C-PF — terminal scientific compilation and
pre-decision evaluator correction

- Invoked the committed write-once compiler against sealed campaign
  `6446705f...`. It completed after approximately five hours and atomically
  published analysis `b6c77b87...` at 2026-08-13 13:27:16 UTC. The identity
  and population audit validate 1,400 images, 5,000 binding runs, 4,939
  successes, and all 61 typed failures retained in the denominator. The 143
  binding and 15 diagnostic continuum endpoints compiled; runtime was not
  interpreted before the scientific decision.
- The first evaluator invocation failed closed before creating a decision with
  `external continuum endpoint registry is absent`. The successor registry is
  deliberately minimal and inherits the exact frozen 158-endpoint matrix from
  the closed registry through `load_successor_endpoint_registry`; the entry
  point had loaded the raw JSON instead of calling that already-reviewed
  strict loader.
- Added a regression test that failed for the missing compatibility view. The
  evaluator now consumes the strict inherited registry view. No analysis
  value, endpoint, threshold, confidence rule, reference scope, or terminal
  evaluator changed. The decision output remains absent.

**Validation:** the focused regression failed first on the missing loader and
then passed; all 86 focused successor and inherited compiler/evaluator tests
pass. Full branch-aware coverage passes 1,263 tests with 4 expected failures
and remains 94.08%. Strict documentation builds, and `just check` passes Ruff,
Pyright, 1,133 tests, and 4 expected failures.

**Decision:** this is a final fail-closed metadata-composition correction after
analysis publication but before any scientific decision output or endpoint
interpretation. It is not a rescore, campaign rerun, or additional look.

**Immediate next step:** validate and commit the evaluator correction and
refreshed hash chain, rerun the unchanged evaluator, then inspect scientific
gate outcomes before runtime.

## 2026-08-13 — Closed the successor campaign as failed

**Plan phase:** Phase 5, Step 2C-PF — terminal decision and failure diagnosis

- After commit `838da9e`, the unchanged evaluator completed in seconds and
  atomically published decision `1d8c2577...` as `fail`. Compact status is
  `fail`; all 143 binding continuum endpoints are `indeterminate`. Step 3,
  optimization, and qualification remain false/closed.
- All 61 retained execution failures are Hebog continuum legs. Sixty are
  `FluxMeasurement` validation errors caused by a NaN local RMS: 59 in
  continuum geometry 4 and one in geometry 2. The remaining geometry-2 leg
  has one omitted compact fit. Because the frozen runner constructs compact
  and segment products in one transaction, a compact-catalogue error also
  suppresses otherwise usable continuum labels and masks.
- Compact evidence is broadly close but does not meet the conjunctive gate.
  The PyBDSF comparison passes 441 of 450 decisions; its nine failures are
  position median/tail endpoints near the 0.002/0.005-beam margins across
  marginally resolved, unresolved, SNR-10, and SNR-15 strata. The applicable
  Aegean comparison passes 135 of 143 decisions; its eight failures comprise
  one SNR-15 position tail, six integrated-flux median/tail endpoints, and one
  marginally resolved fitted-axis tail.

**Decision:** the result is a valid failed external campaign, not evidence for
Step 3 or a runtime claim. It may inform prospective development but may not
be rescored or reused as confirmation.

**Immediate next step:** add bounded regressions for local-RMS unavailability,
compact-fit omission, and independent continuum-product publication; then
improve the compact position and flux failures before freezing new
seed-disjoint evidence.

## 2026-08-13 — Completed the successor corrective development cycle

**Plan phase:** Phase 5, Step 2C-PF — prospective post-failure correction

- Split the Hebog external runner by checksum-bound science lane. Continuum
  runs now publish only segment catalogue/labels/mask; compact runs publish
  only the compact catalogue. A compact failure can no longer discard valid
  continuum products.
- Added explicit completeness behavior: a centroid without RMS interpolation
  support uses its finite owned-region RMS and records
  `local-rms-region-mean-fallback`; a failed/unavailable Gaussian with finite
  moment photometry retains a source row flagged `moment-measurement` and
  `fitted-shape-unavailable`, without inventing a Gaussian. All 61 exact inputs
  that failed the closed successor then completed with finite catalogues.
- Separated source and fitted-Gaussian flux semantics. The source retains the
  reviewed Rapthor peak-as-total convention when unresolved; the component
  retains its fitted total. The external compact product now contains
  Gaussian-component rows, matching the frozen PyBDSF/Aegean comparison
  scope.
- On a 100-image stratified ablation, selected the already-supported
  free-only, selected-model Gaussian policy. The complete 800-image closed-
  population development rerun completed every image. Compared with the
  closed candidate, position median/p95 improved from `0.02313/0.07590` to
  `0.02040/0.06922`; SNR-15 improved from `0.03049/0.07901` to
  `0.02689/0.06761`; marginal fitted-axis p95 improved from `0.20472` to
  `0.17292`; and overall fitted-component flux p95 improved from `0.41212` to
  `0.19665`. All formerly failing PyBDSF position and Aegean flux/axis point
  estimates moved to the favourable side. This is development evidence, not
  a campaign rescore or interval-level pass.

**Validation:** 187 focused scientific/runner tests passed; the full internal
coverage lane passed 1,270 tests with four expected xfails at 94.05% coverage;
all 27 equivalence tests passed; and `just check` passed 1,140 tests with four
expected xfails.

**Decision:** the corrective implementation is ready for new seed-disjoint
evidence. Decision `1d8c2577...` remains failed; Step 3, runtime interpretation,
optimization, and qualification remain closed.

## 2026-08-13 — Prepared result-neutral acceleration for the next campaign

**Plan phase:** Phase 5, Step 2C-PF — pre-freeze runtime preparation

- Retained the powered 600-continuum/800-compact design, all references,
  endpoints, gates, four PyBDSF cores, and fresh-container isolation. The
  closed run spanned 10.49 hours and recorded 5.722 finder-hours. On the
  six-CPU Podman VM, partitioning the unchanged run matrix into one serial
  PyBDSF lane and one serial Hebog/Aegean lane has a 3.476-hour finder critical
  path, versus 5.722 hours serial. This is a development projection only.
- Added a fail-closed two-lane scheduler using the standard-library executor.
  A failure stops either lane from starting further work, while an already
  active invocation may finish and remains resumable. The prospective request
  model accepts exactly two lanes, not an unbounded worker count.
- Measured closed-campaign verification separately at 312.03 seconds cold and
  137.70–140.10 seconds warm. Retained full artifact verification because it
  is material but not the approximately five-hour compiler bottleneck.
- Added prospective compiler seams that retain finder-invariant image, mean,
  RMS, truth-label, and header state for one image only, and calculate all
  native support centroids in one grouped plane pass. Across an exact
  20-image/three-finder slice, all captured endpoint observations were equal;
  preparation improved from 34.21 to 27.47 seconds (1.25×). The complete
  no-bootstrap historical preparation baseline was 994.91 seconds.
- Preserved the closed successor launcher, compiler, registry, evaluator, and
  review byte-for-byte. The new helpers are not campaign authority until a
  prospective wrapper, registry, request, runtime, and parity review are
  frozen and receive named approval.

**Validation:** 29 focused scheduler, accelerator, and
historical-immutability tests passed. `just check` passed with 1,159 tests and
four expected xfails; all 130 integration and 27 equivalence tests passed;
strict documentation built successfully. Branch-aware coverage passed with
1,289 tests, four expected xfails, 94.09% project coverage, and 100% statement
and branch coverage in both new production modules. The exact-product
benchmark was read-only and generated no new campaign evidence.

**Immediate next step:** compose the helpers into new prospective wrappers,
run the bounded real-container concurrency and full observation-parity matrix,
then freeze the same-size seed-disjoint campaign identities.

## 2026-08-13 — Froze the corrected external confirmation composition

**Plan phase:** Phase 5, Step 2C-PF — confirmation pre-execution review

- Built Linux/arm64 candidate image
  `localhost/hebog:phase5-external-confirmation-ee69eba` from a clean archive
  of commit `ee69eba...`. The mandatory hook first removed one obsolete lint
  suppression from the compiler accelerator; this source-comment-only change
  was committed separately before the final build. Network-disabled inspection
  reproduced source tree `b002878...` and the predeclared dependency inventory
  `d383be3...`; the image digest is `sha256:88696bd...`.
- Froze 600 continuum and 800 compact/blend images with 1,400 seeds disjoint
  from 10,453 historical seeds in 37 manifests. The unchanged power model
  retains a 0.908176 conservative joint lower bound against the 0.90 gate.
- Composed new checksum-bound confirmation runners, a two-resource-lane
  launcher, bounded compiler, registry, evaluator, and strict protocol view.
  The closed launchers and compilers remain byte-identical. The pending
  decision rejects before container inspection or private staging.
- Ran the non-scientific, network-disabled real-container resource probe on
  the six-CPU/16 GB Podman VM. Released PyBDSF+Hebog, master+Hebog, and released
  PyBDSF+Aegean overlapped with ratios 0.673, 0.698, and 0.506 of their isolated
  time sums while returning the same deterministic digest. Four PyBDSF cores
  and one companion core were retained.
- After verifying retained closed analysis `b6c77b87...` and decision
  `1d8c2577...`, permanently removed only the approved 46 GiB raw successor
  campaign directory. Available host space is approximately 81.5 GiB;
  no container cleanup was needed.
- Technical preflight review `4d5cb1...` binds the exact population,
  candidate and reference runtimes, programs, unchanged gates, parity evidence,
  storage state, and one-look rule. Campaign and staging outputs remain absent.

**Validation:** 139 focused campaign, compiler, evaluator, population, and
historical-immutability tests passed. `just check` passed Ruff, Pyright, 1,168
tests, and four expected xfails. The strict documentation build and mandatory
pre-commit hooks pass. The final freezer reproduced all three checked-in
records byte-for-byte in temporary storage, and the exact rebuilt runtime
reproduced its bound source and dependency checksums without network access.

**Decision:** the corrected candidate is technically ready for exact-identity
approval and a no-write preflight. This preparation creates no confirmation
science or runtime claim and does not open Step 3, optimization, or
qualification.

**Immediate next step:** obtain Gemma Danks's approval bound to review
`4d5cb1...` and the four exact image digests, refresh the decision-dependent
hash chain, commit it, and run the no-write 1,400-input/7,000-run preflight.

## 2026-08-13 — Approved the corrected external confirmation

**Plan phase:** Phase 5, Step 2C-PF — exact-identity authorization

- Gemma Danks explicitly approved preflight review `4d5cb1...` and its four
  exact Linux/arm64 image digests on 2026-08-13.
- Decision `5d456b9...` now authorizes one terminal 1,400-input/7,000-run
  confirmation with exactly two resource lanes and four PyBDSF cores. The
  named review contains the full approved review SHA-256; the strict loader
  rejects an omitted, changed, or unapproved review.
- Refreshed only the decision-dependent endpoint-registry and evaluation
  checksum chain. The population, manifests, runners, launcher, compiler,
  evaluator, gates, reference set, one-look rule, and runtime identities are
  unchanged. One-look, Step 3, optimization, and qualification flags remain
  false.

**Decision:** authorization is sufficient for the complete no-write preflight,
not direct publication or partial-result inspection.

**Immediate next step:** commit this authorization, run the exact no-write
preflight, and launch only if both public output and private staging remain
absent.

## 2026-08-13 — Passed the corrected confirmation no-write preflight

**Plan phase:** Phase 5, Step 2C-PF — complete request expansion

- Ran the committed launcher against the exact four approved images with
  `--preflight-only`. Canonical request `73b93ee...` expanded exactly 1,400
  inputs and 7,000 finder runs with execution concurrency two and four PyBDSF
  cores.
- The public `external-confirmation-comparison` directory and decision-derived
  private staging directory were absent before and after preflight. No image
  was materialized and no finder product or scientific result was generated or
  opened.
- Approximately 80 GiB remained available immediately after the preflight,
  above the reviewed approximate 60 GiB campaign headroom requirement.

**Decision:** the approved one-look may now execute exactly once without
partial-result inspection. Step 3, optimization, and qualification remain
closed.

**Immediate next step:** commit the preflight record, start the terminal
campaign, monitor only operational progress, then compile and evaluate the
sealed result before interpreting runtime.

## 2026-08-14 — Sealed the confirmation and corrected request verification

**Plan phase:** Phase 5, Step 2C-PF — terminal campaign and pre-analysis
composition correction

- The approved two-lane campaign atomically published terminal manifest
  `ffd6de4...` after verifying all 1,400 inputs and 7,000 finder results. The
  private staging directory closed. No partial scientific product was opened.
- The first committed compiler attempt failed closed before creating analysis:
  its composed historical verifier parsed `campaign-request.json` through the
  original `execution_concurrency=1` model and rejected the approved value two.
  Analysis and decision outputs remain absent, and verification stopped before
  reading a raw scientific artifact.
- Added a regression that first reproduced the one-versus-two literal failure.
  The confirmation-only compiler view now installs the same strict two-lane
  request model already used to create the canonical request. The closed
  verifier, campaign, science kernels, endpoint matrix, gates, and evaluator
  are unchanged. Corrected compiler `9371c3b...` and its dependent registry and
  evaluation hashes remain write-once analysis authority.

**Decision:** this is a result-neutral request-deserialization correction, not
a campaign rerun, additional look, scientific change, or gate change.

**Immediate next step:** validate and commit the corrected compiler composition,
then retry write-once compilation and run the evaluator before interpreting
runtime.

## 2026-08-14 — Corrected confirmation product-role verification

**Plan phase:** Phase 5, Step 2C-PF — second pre-analysis composition
correction

- The retried compiler passed request validation but failed closed before
  creating analysis because the historical verifier expected Hebog's compact
  and continuum artifacts in every successful run. The prospective runner
  deliberately emits only the products owned by each lane: three segment
  products for continuum and one compact catalogue for compact/blend.
- Added a regression that first reproduced the extra compact-product
  expectation. The confirmation-only verifier now validates the exact
  lane-specific Hebog product sets and delegates all reference product sets
  to the unchanged historical verifier. The campaign, artifacts, science
  kernels, endpoints, thresholds, and evaluator are unchanged.
- Refreshed the checksum chain to compiler `9f4fd09...`, endpoint registry
  `e9a6482...`, and evaluation contract `7b5300a...`. Analysis and decision
  outputs were absent when the correction was made.

**Validation:** the new regression failed for the intended extra-product
expectation and passed after installing the lane-specific verifier. The two
focused confirmation compiler tests and Ruff pass. The mandatory formatter
would otherwise reflow two already-executed lines and change the compiler
checksum, so this exact frozen evidence program is excluded from formatting;
lint, type checking, and tests remain mandatory.

**Deviation:** the exact checksum-bound correction was compiled before its
local commit was created. No file changed between compilation and the commit;
the analysis records the same `9f4fd09...` compiler identity. This is a
sequencing deviation, not a science change or additional look.

**Immediate next step:** commit the byte-identical correction, then record and
validate the already-sealed scientific decision without rescoring it.

## 2026-08-14 — Closed the external confirmation with a scientific failure

**Plan phase:** Phase 5, Step 2C-PF — terminal confirmation decision

- Sealed campaign `ffd6de4...` contains all 1,400 fresh inputs and 7,000
  successful finder runs; no binding leg is failed or unavailable. It ran for
  6 h 28 min with two resource lanes. This duration is operational context,
  not comparative performance evidence.
- The checksum-bound compiler completed in approximately 4 h 51 min and
  atomically published analysis `cf14518...`. The unchanged evaluator then
  published decision `70c17ba...`. Scientific outcomes were inspected before
  any runtime interpretation.
- Continuum has 86 passing, 30 failing, and 27 underpowered binding endpoints.
  Twenty-nine failures are absolute integrated-flux gates: all 15 median
  strata and 14 of 15 p95 strata. Overall mask precision passes its absolute
  gate but fails paired non-inferiority to both PyBDSF references. The 27
  underpowered endpoints pass their absolute gates but exceed the
  predeclared paired-variance bounds; they cannot compensate for failures.
- Compact now passes all 450 applicable comparisons against released PyBDSF
  and pinned `master`. Against Aegean, 130 of 143 binding comparisons pass and
  13 fail: six fitted-position-angle medians, one fitted-position-angle p95,
  two integrated-flux medians, and four integrated-flux p95 endpoints.

**Decision:** `fail`. Step 3, optimization, qualification, and runtime
comparison remain closed. The campaign may not be rescored or reused as
confirmation, and no speedup claim is authorized.

**Validation:** the evaluator completed without changing its frozen decision
logic. The analysis records compiler `9f4fd09...`, and the decision records
analysis `cf14518...` and evaluation contract `7b5300a...`. Focused validation
and the mandatory repository hooks pass before the evaluation commit.

**Immediate next step:** obtain human scientific review of the sealed failure
before choosing a new prospective candidate or proceeding with the independent
Rapthor-profile question in Step 2D. Any new candidate requires a revised
pre-results plan and fresh evidence; this campaign cannot be tuned or rescored.

## 2026-08-14 — Implemented prospective confirmation-failure corrections

**Plan phase:** Phase 5, post-Step 2C-PF prospective correction

- Traced 29 Continuum flux failures to a product-boundary regression: the
  catalogue summed only the exact three-sigma detection support even though
  the reviewed measurement used original residual pixels beyond that support.
  Added bounded four-beam measurement apertures with nearest-segment ownership
  so close sources cannot double-count pixels; exact-support centroids remain
  unchanged. Also added the prospective observable-domain truth normalizer,
  because one edge source exposes only 71.97% of its full injected flux.
- Added a three-by-three sub-beam opening to the prospective Continuum runner.
  On 10 development images, mean precision/recall/IoU changed from
  `0.89470/0.92623/0.83516` to `0.92462/0.91396/0.85052`. The single selected
  policy then achieved `0.91778/0.90964/0.84104` on the 100-image regression
  set. Exact-support flux median/p95 errors of `0.18798/0.36973` became
  `0.04979/0.17304` with the corrected aperture across 600 regression source
  measurements, passing the existing `0.10/0.25` absolute gates.
- Replaced the Phase 5 compact free-only fit with the existing beam-or-free
  selection while retaining selected-model position. On 23 development
  images, fitted-position-angle median/p95 improved from `1.8479/8.6490` to
  `0.7790/8.3376` degrees, with unresolved median error falling from `2.1641`
  to `0.00017` degrees. A development-only aperture ablation selected the
  standard low-variance 1.5-sigma corrected aperture, reducing association
  flux median/p95 from `0.04601/0.23432` at three sigma to
  `0.03589/0.18339`.
- The selected compact policy was run once on the 100-image Phase 4R
  regression population: position-angle median/p95 was `0.71624/8.96084`
  degrees and association-flux median/p95 was `0.03712/0.18053`. This supports
  the correction but is not an external-comparator pass claim.
- The 27 underpowered Continuum endpoints are a protocol-design issue rather
  than an algorithm failure: observed paired standard deviations exceeded
  the predeclared planning bounds even though their absolute gates passed.
  The next protocol must use the independent closed result to predeclare
  realistic variance bounds and power a fresh population accordingly.

**Validation:** 125 focused correction and historical-identity tests pass; all
27 equivalence tests pass; branch-aware coverage passes 1,306 tests with four
expected xfails at 94.10%; `just check` passes 1,176 tests with four expected
xfails; and the strict documentation build passes. The closed campaign,
compiler, analysis, decision, and checksum-bound historical source files were
not modified or rescored.

**Decision:** the failure classes now have a prospective implementation and
bounded regression evidence. Step 3, optimization, qualification, and runtime
interpretation remain closed pending scientific pre-review and fresh
seed-disjoint external evidence.

## 2026-08-14 — Completed the post-failure scientific pre-review

**Plan phase:** Phase 5, post-Step 2C-PF scientific and power review

- Reviewed the prospective Continuum aperture photometry, sub-beam mask
  opening, observable-domain truth boundary, and compact beam-or-free
  measurement against the closed failure classes and established source-finder
  practice. The candidate is scientifically credible for a fresh comparison,
  but its regression diagnostics are not external equivalence evidence.
- Identified that observable-domain truth must include each group's centroid
  and support metadata as well as integrated flux. The new compiler must keep
  that truth independent of finder detections before fresh identities are
  frozen.
- Replaced the former coarse planning abstraction in the prospective review.
  The old table assigned nominal counts by family, including report-only
  position median, whereas the sealed compiler produced 226 paired binding
  endpoint/reference comparisons with strongly heterogeneous variance.
- Added a pure endpoint-specific power planner and reproducible review script.
  Each new variance bound is the larger of the old family floor and 1.25 times
  the independent closed endpoint standard deviation. The planning
  alternative retains half of a favourable closed difference and treats an
  unfavourable difference as equality.
- The mathematical minimum is 1,550 Continuum images. The review recommends
  1,600, balanced as 400 fresh seeds over four geometries, plus the existing
  800-image compact lane. The conservative lower bounds are 0.992270
  Continuum, 0.909784 compact, and 0.902054 joint. Under these guarded
  assumptions, the former 600-image Continuum population would provide only
  0.187276 joint power.
- Generated ignored machine-readable review
  `benchmark-results/phase-5/post-failure-power-pre-review.json` with SHA-256
  `31ca691e1c5fc7ca905e0ad874906533ed55b7a4746c68543457951264aba07d`.
  Closed analysis `cf14518...`, population `c346549...`, campaign products,
  compilers, and decision were not changed or rescored.

**Decision:** recommend named scientific approval of the candidate and revised
population design. Approval would authorize implementation and freezing only;
execution still requires a later exact-identity preflight and one-look
decision. Step 3, optimization, qualification, and runtime interpretation
remain closed.

**Validation:** 20 focused power-planning tests pass with 100% line and branch
coverage for the new module. The branch-aware repository coverage run passes
1,312 tests with four expected xfails at 93.93% overall; the subsequent
failure-path additions only increase coverage. All 27 equivalence tests pass,
`just check` passes 1,196 tests with four expected xfails, and the strict
documentation build and mandatory repository hooks pass. Ruff and Pyright
report no errors.

**Immediate next step:** obtain named approval of the pre-review. If approved,
implement observable centroid/support truth, freeze fresh manifests and exact
endpoint priors, bind new immutable runner/compiler identities, and prepare a
separate execution preflight without opening scientific products.

## 2026-08-14 — Implemented the approved observable-truth boundary

**Plan phase:** Phase 5, post-Step 2C-PF evidence implementation

- Gemma Danks approved the post-failure scientific pre-review and revised
  population design. The approval authorizes implementation and freezing, not
  campaign execution.
- Added a finder-independent truth compiler that measures integrated flux,
  flux-weighted centroid, label ownership, and declared/observable support on
  one common valid-pixel domain. It publishes per-group support counts and
  fractions for later sealed-analysis audit and cannot consume a finder
  product.
- The prospective boundary rejects empty, duplicated, missing, mistyped,
  unobservable, non-positive, and overlapping truth supports. The immutable
  closed campaign compiler and products remain unchanged.

**Validation:** 31 focused tests pass with 100% line and branch coverage for
both prospective truth modules. Repository branch-aware coverage passes 1,332
tests with four expected xfails at 94.15% before the final failure-path tests,
which raise changed-file coverage to 100%.

**Immediate next step:** freeze the 1,600 fresh Continuum and 800 fresh compact
manifests with all 226 exact endpoint/reference priors, then bind the new
runner, compiler, evaluator, and pending no-write preflight identities. A
separate exact-identity approval remains required before execution.

## 2026-08-14 — Froze the approved post-failure evidence boundary

**Plan phase:** Phase 5, post-Step 2C-PF fresh external evidence

- Froze 1,600 Continuum images as 400 new seeds over each of four reviewed
  geometries and 800 new compact/blend images. All 2,400 seeds are disjoint
  from 11,853 seeds in 39 historical manifests. Population contract
  `42c3d07...` contains all 226 endpoint/reference priors and independently
  recomputes the 1,550 minimum, selected 1,600 count, 0.992270 Continuum power,
  and 0.902054 joint lower bound.
- Bound candidate commit `63e4b58...`, source tree `864d8f2...`, the observable
  truth modules, the prospective science runner, all three external wrappers,
  the 2,400-input/12,000-run two-lane launcher, compiler, and endpoint-specific
  evaluator. Absolute gates, non-inferiority margins, failure denominators,
  exact excess-variance failure, and the one-look rule are inherited without
  modifying any closed program or product.
- Built the candidate from a clean archive of `63e4b58...` with the pinned
  Phase 5 Containerfile. Image digest `sha256:4a7bc975...` reproduces source
  tree `864d8f2...` and dependency inventory `d383be3...` in a network-disabled
  check. The retained four-PyBDSF-core/two-resource-lane probe passed across
  both PyBDSF references and Aegean; it is operational evidence only.
- Prepared a fail-closed preflight review with public and private outputs
  absent. The scaled campaign has a conservative 120 GiB free-space floor,
  but only 30.88 GiB was available. Named execution approval is therefore not
  recommended and cannot be accepted by the loader. Podman reports 32.17 GB
  reclaimable images and an unused 4.67 GB `vscode` volume; the repository's
  46 GB closed confirmation campaign must be preserved or moved to verified
  external storage rather than deleted. No cleanup was performed.

**Decision:** implementation and pre-results freezing are complete. Campaign
execution, the no-write preflight, Step 3, optimization, qualification, and
runtime interpretation remain closed pending storage remediation, a refreshed
ready review, and separate named approval bound to its exact checksum.

**Validation:** the focused prospective protocol, compiler, evaluator, and
manifest-inventory suite passes 42 tests. A red-green regression proves that a
review cannot declare storage ready when its recorded free-space observation
is below the 120 GiB floor. Repository branch-aware coverage passes 1,343
tests with four expected xfails at 94.21%; all 27 equivalence tests pass;
`just check` passes 1,214 tests with four expected xfails; and the strict
documentation build succeeds. Final Ruff, Pyright, hook, and identity checks
are clean.

**Immediate next step:** obtain approval for scoped local cleanup or move the
closed confirmation data to verified external storage, reach 120 GiB free,
refresh only the operational preflight review and dependent approval checksum,
then request the separate one-look authorization.

## 2026-08-14 — Authorized isolated development during confirmation

**Plan phase:** Phase 5, post-Step 2C-PF parallel execution policy

- Separated the future immutable confirmation execution from continued Phase 5
  development. The campaign must run from a clean checkout pinned to its
  approved execution commit and may expose only operational progress until its
  terminal products seal.
- Authorized Step 2D preparation and development-only Steps 3--5 in a separate
  checkout using analytic, development, and existing regression evidence.
  Partial campaign products, qualification data, candidate-specific
  performance claims, frozen campaign programs, and the execution checkout
  remain outside that lane.
- Resource-heavy probes and benchmarks may not contend with the campaign host.
  A sealed scientific pass may promote the parallel work to the active
  candidate; a failure keeps it experimental pending scientific review. The
  PyBDSF fallback, qualification, external-equivalence claim, and production
  cutover gates are unchanged.

**Decision:** useful implementation work may continue while the evidence
campaign runs without weakening the one-look boundary or treating prospective
development as confirmation evidence.

**Validation:** the strict documentation build passes. `just check` passes
Ruff, Pyright, 1,214 tests, and four expected xfails; no production code,
campaign identity, evidence, or scientific product changed.

**Immediate next step:** resolve storage and obtain exact-identity campaign
authorization. Once the immutable campaign is launched, begin the isolated
Step 2D preparation and Step 3 analytic/TDD development lane.

## 2026-08-14 — Audited post-failure campaign storage remediation

**Plan phase:** Phase 5, post-Step 2C-PF operational preparation

- Host free space is 31 GiB against the frozen 120 GiB campaign floor. The
  sealed confirmation campaign remains the only material Hebog target at
  45.7 GiB; its inputs and results occupy 18.8 and 26.9 GiB respectively. No
  external volume is mounted, so it cannot yet be moved to verified external
  storage.
- Podman reports 377 images using 39.84 GB, of which 39.83 GB is marked
  reclaimable. Two unrelated VS Code devcontainer builds for Rapthor and
  `ska-sdp-ical` are active and generated another 2.31 GB during the audit.
  They also reference the nominally unlinked 4.67 GB `vscode` volume. No
  build, image, container, or volume was interrupted or removed.
- Reconstructable development caches offer approximately 30 GiB without
  touching project data: Poetry 21.9 GiB, uv 6.25 GiB, pip 1.28 GiB, and
  pre-commit 0.93 GiB. Cache deletion would require explicit approval and may
  require later network downloads.

**Decision:** storage remains blocked. The preferred recovery is to finish or
stop the unrelated builds, move the sealed 45.7 GiB campaign to a verified
external volume, approve the listed cache cleanup, and prune only dangling
Podman intermediates while retaining the four bound runtime images. This is
expected to exceed 120 GiB; none of those destructive actions is authorized
by this audit.

**Immediate next step:** obtain a preservation destination for the closed
campaign and explicit approval for the scoped cache and post-build dangling-
image cleanup.

## 2026-08-14 — Removed superseded raw confirmation FITS evidence

**Plan phase:** Phase 5, post-Step 2C-PF operational preparation

- The project owner approved removing the raw FITS products from the sealed
  failed confirmation campaign. Before deletion, the terminal campaign hash
  `ffd6de4...` matched analysis `cf14518...`, whose hash matched failed
  decision `70c17ba...`.
- Removed exactly 26,200 `.fits` files beneath
  `benchmark-results/phase-5/external-confirmation-comparison`, totaling
  48,869,447,040 logical bytes (45.5 GiB). No other path or file type was
  removed. The directory now occupies about 147 MiB.
- Retained the canonical request, terminal campaign manifest, 1,400
  `input.json` records, 7,000 `result.json` records, compiled analysis,
  decision, power review, checksums, and exact program and runtime identities.
  Raw artifact recompilation and artifact-level scientific audit of this
  failed campaign are no longer possible locally.
- The Podman Apple Virtualization process still holds approximately 40.3 GB
  of the deleted campaign files open through the shared mount. Host free space
  therefore rose only from about 34 GiB to 41 GiB and remains below the frozen
  120 GiB campaign floor. The files will not release their remaining physical
  blocks until those descriptors close; no VM, container, or unrelated build
  was interrupted.

**Decision:** the compact governed evidence is sufficient for provenance and
the fresh campaign does not consume the removed FITS products. Storage remains
blocked until the Podman-held descriptors close and further approved cleanup
reaches the 120 GiB floor.

**Immediate next step:** allow the active Podman work to finish or obtain
approval to stop and restart the Podman machine, verify the released space,
then continue scoped cache or image cleanup as needed before refreshing the
storage-only preflight review.

## 2026-08-14 — Reconstructed the post-failure campaign runtimes

**Plan phase:** Phase 5, post-Step 2C-PF operational preparation

- Preserved the active Rapthor devcontainer throughout reconstruction. Built
  four fresh Linux/arm64 images from the frozen artifacts and a clean archive
  of candidate commit `63e4b58...`. Their new immutable digests are Hebog
  `sha256:4341ec7...`, released PyBDSF `sha256:c6dca91...`, pinned PyBDSF
  master `sha256:81fc680...`, and Aegean `sha256:7385918...`.
- Network-disabled checks reproduced Hebog source tree `864d8f2...` and the
  frozen dependency inventories `d383be3...`, `8211043...`, `83574dd...`, and
  `346c1f3...`. Package versions remain Hebog 0.6.0, PyBDSF 1.14.1, PyBDSF
  1.14.2.dev40+gc70103be3, and AegeanTools 2.3.5. The new OCI identities are a
  build-provenance change, not a scientific change.
- The committed network-disabled resource probe passed with identical output
  across isolated and paired runs. The largest overlap ratio was 0.66873 for
  the frozen two-lane budget of four PyBDSF cores plus one companion core.
- Removed only six dangling reconstruction images and trimmed freed VM blocks.
  Host availability is 149,734,052 KiB (142.797520 GiB), above the frozen
  120 GiB floor; the Podman VM has 65 GiB free. Public and private post-failure
  campaign paths remain absent, and the Rapthor container remains running. The
  verified 19 MiB temporary reconstruction context was then removed.
- Added a prospective digest override in the post-failure wrapper so the
  closed protocol, artifact versions and checksums, dependency inventories,
  science settings, populations, and gates stay unchanged while the rebuilt
  OCI identities are bound. Its loader now rejects any substituted image ID,
  digest, or inventory. Refreshed preflight review `29343e37...` passes the
  storage and operational checks and recommends exact-identity approval.

**Decision:** the no-write preflight and campaign remain unauthorized. The
pending execution decision still fails closed and requires Gemma Danks's named
approval of review `29343e37...` and its four exact image digests before any
campaign output may be created.

**Validation:** all 11 focused post-failure protocol tests pass, including the
new rebuilt-reference binding, runtime-substitution rejection,
storage-readiness recomputation, and pending-authorization rejection. Final
branch-aware coverage passes 1,345 tests with four expected xfails at 94.21%;
all 27 equivalence tests pass; `just check` passes 1,215 tests with four
expected xfails; and the strict documentation build passes. The final code
review found no remaining actionable issue.

**Immediate next step:** obtain exact-identity approval, bind the approved
review checksum into the execution decision and dependent registry/evaluation
chain, commit that authorization separately, then run the complete no-write
preflight.

## 2026-08-14 — Repaired the post-failure approval transition

**Plan phase:** Phase 5, post-Step 2C-PF exact-identity authorization

- Gemma Danks approved technical review `29343e37...` and its four rebuilt
  runtime digests. Before changing authorization or creating staging, the
  transition exposed a circular checksum dependency: the review required the
  pending decision checksum while the approved decision had to require the
  review checksum. No valid immutable approved pair could satisfy both checks.
- Added an explicit asymmetric transition boundary. While authorization is
  pending, the decision, registry, and evaluation files must match the exact
  checksums captured by the review. After the decision enters the only valid
  approved state, the immutable review retains those pending snapshots while
  the strict decision, registry, and evaluation loaders validate the new live
  chain and its review binding independently.
- Added regressions proving that pending artifact drift is rejected and that
  the reviewed snapshot survives only the governed approval transition. The
  runtime IDs, dependency inventories, population, programs, science policy,
  one-look rule, resource limits, output absence, and storage observation did
  not change.

**Decision:** review `29343e37...` is superseded because the verifier identity
changed to repair the fail-closed transition. Refreshed technical review
`835abe1c...` requires a new named approval. Execution remains unauthorized;
no no-write preflight, staging directory, or campaign product was created.

**Validation:** all 17 focused post-failure protocol tests pass. Final
branch-aware coverage passes 1,351 tests with four expected xfails at 94.21%;
`just check` passes 1,221 tests with four expected xfails. The strict
documentation build and mandatory hooks pass, and the final code review found
no remaining actionable issue.

**Immediate next step:** obtain named approval of review `835abe1c...` and the
unchanged four runtime digests, then change only the authorization-dependent
chain, commit it separately, and run the complete no-write preflight.

## 2026-08-14 — Bound the refreshed post-failure execution approval

**Plan phase:** Phase 5, post-Step 2C-PF exact-identity authorization

- Gemma Danks approved technical preflight review `835abe1c...`, its exact
  four rebuilt OCI identities, and the unchanged 2,400-image, 12,000-run,
  two-lane program with four PyBDSF cores and the terminal one-look rule.
- Changed only the authorization-dependent chain. The execution decision now
  authorizes one terminal post-failure comparison and embeds the full review
  checksum; the endpoint registry and evaluation contract now bind the new
  decision and registry checksums. All scientific, population, runner,
  resource, output, and qualification settings remain unchanged.

**Decision:** authorization is sufficient to run the complete no-write
preflight from the immutable authorization commit. Campaign output may be
created only if that exact preflight passes.

**Validation:** all 17 focused post-failure protocol tests pass. Final
branch-aware coverage passes 1,351 tests with four expected xfails at 94.21%;
`just check` passes 1,221 tests with four expected xfails. The strict
documentation build and mandatory hooks pass, and the final code review found
no actionable issue.

**Immediate next step:** validate and commit this authorization, create its
immutable execution checkout, run the no-write preflight, and launch the
single terminal campaign only on success.

## 2026-08-15 — Post-failure external campaign failed its scientific gates

**Plan phase:** Phase 5, post-Step 2C-PF terminal external decision

- The complete no-write preflight passed from immutable checkout `211dff6...`,
  and the approved one-look campaign sealed all 12,000 requested runs across
  2,400 fresh images with no run failure. The public campaign manifest is
  `benchmark-results/phase-5/external-post-failure-comparison/campaign.json`
  with SHA-256 `c16dc48...`; its private staging directory was atomically
  removed. Monitoring opened no partial scientific product.
- The committed frozen compiler produced
  `external-post-failure-analysis.json` with SHA-256 `ecd6bd7...`; the frozen
  evaluator produced `external-post-failure-decision.json` with SHA-256
  `2dd0bcc...`. Scientific outcomes were interpreted before any runtime data.
- The terminal decision is `fail`. Compact science fails one released-PyBDSF
  binding for the S/N-15 integrated-flux 95th percentile and seven Aegean
  bindings, predominantly integrated-flux tails. Of 143 Continuum endpoints,
  122 pass, 17 fail, and four are underpowered. Thirteen absolute
  integrated-flux 95th-percentile endpoints exceed their gate, three absolute
  position-tail endpoints fail, and overall mask precision misses the pinned
  PyBDSF-master non-inferiority margin by 0.000799 at the upper confidence
  bound. The four underpowered median-flux endpoints pass their absolute gates
  but exceed their predeclared paired-variance bounds.
- Runtime was inspected only after the scientific decision and remains
  diagnostic because promotion and optimization are unauthorized. Continuum
  median wall time is 0.7798 s for Hebog versus 3.7980 s for released PyBDSF
  and 4.2938 s for pinned PyBDSF master. On the compact lane it is 2.0254 s
  for Hebog versus 0.9664 s and 0.9573 s respectively; Aegean is 3.3089 s.
  The complete campaign elapsed 48,090.5 s (13 h 21 min 30.5 s).

**Decision:** Step 3 promotion, optimization, qualification, external
equivalence claims, PyBDSF fallback removal, and production cutover remain
closed. Parallel scale-development work remains experimental and may use only
analytic, development, and existing regression evidence. The Rapthor
devcontainer remains intentionally stopped.

**Validation:** all 17 focused post-failure protocol tests pass. The required
branch-aware coverage suite passes; `just check` passes Ruff, Pyright, 1,221
tests, and four expected xfails; and the strict documentation build passes.
The final documentation-only review found no actionable code issue.

**Immediate next step:** perform a named scientific failure review using the
sealed diagnostics, reproduce the causes outside the campaign, and predeclare
any prospective correction and fresh seed-disjoint evidence boundary. Do not
rescore or reopen this one-look campaign.

## 2026-08-15 — Corrected the post-campaign scientific failure causes

**Plan phase:** Phase 5, post-Step 2C-PF scientific failure review

- Completed the named failure review requested by Gemma Danks without
  recompiling, rescoring, or changing the sealed post-failure campaign. The
  compact flux failures came from applying Rapthor source canonicalization to
  fitted Gaussian components: unresolved fitted totals were replaced by peak
  flux. A 38,400-match diagnostic component view reduced overall absolute
  integrated-flux p95 from 0.4132 to 0.1598 and S/N-15 p95 from 0.5305 to
  0.1453. Future compilers have an explicit fitted-component diagnostic seam.
- Preserved the low-variance beam-or-free source result while retaining an
  available independently fitted free ellipse for the Gaussian-component
  product. This corrects the marginal fitted-axis comparison without changing
  Rapthor source semantics.
- Traced the Continuum flux tails to an unbiased but noisy four-beam aperture.
  Added an explicit 1.5-major-beam original-pixel aperture with deterministic
  nearest-segment ownership. Traced the mask-precision miss to attached
  one-/two-pixel three-sigma boundary excursions and replaced the coarse
  opening with dense-core, high-S/N, and adjacent residual-B3 support.
- Kept the residual-B3 reconstruction as an explicit denoised position plane.
  A morphology-neutral peak-to-mean rule uses it for diffuse segments at or
  below 3.0 and retains original weights for compact-dominated segments. Pure
  denoised weighting fixed shells but regressed mixed sources; the final rule
  removed that regression. The estimator falls back to original weights when
  denoised position is unavailable.
- On the complete existing 80-image/480-source development replay with the
  exact observable-domain truth semantics, the connected candidate achieved
  mean mask precision 0.911157, recall 0.907452, and IoU 0.833532. Worst
  integrated-flux p95 was 0.153219; worst position p95 was 0.466808 and
  overall position p95 was 0.294543. This viewed regression population is not
  seed-disjoint confirmation evidence.

**Decision:** retain the corrected implementation as a prospective candidate.
The closed result remains `fail`; Step 3, qualification, equivalence claims,
fallback removal, and production cutover remain blocked. A fresh external
comparison must retain the complete prior gate set and use no fewer than 1,600
Continuum and 800 compact images unless a conservative endpoint-level power
audit justifies a different count.

**Validation:** 115 focused fitting, catalogue, measurement, and prospective
science tests pass. Branch-aware coverage passes 1,364 tests with four
expected xfails at 94.26%. All 27 equivalence tests pass. `just check` passes
Ruff, Pyright, 1,234 tests, and four expected xfails. The strict documentation
build passes. Historical protocol regressions validate the frozen source hash
inside their historical loader view and assert that it differs from the
prospective tree; no closed authority was rebound. The final review against
`CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** complete full validation and local review, then freeze
a fresh seed-disjoint post-correction population and exact power audit only
after separate scientific approval.

## 2026-08-15 — Audited cumulative Phase 5 campaign regressions

**Plan phase:** Phase 5, pre-freeze cumulative regression review

- Reviewed the complete chronological Phase 5 evidence set: filter selection,
  paired/corrective reviews, astrometry development and confirmation, and all
  four terminal external campaign analyses and decisions. The internal filter
  sequence did not lose an accepted candidate: paired and corrective reviews
  rejected their candidates, while the separately governed segment-position
  follow-up passed both development and one-look confirmation.
- The external compact sequence does contain a repeated trade. From successor
  to confirmation, 11 PyBDSF/Aegean decisions moved from fail to pass but seven
  Aegean fitted-position-angle decisions moved from pass to fail. The
  post-failure beam-or-free policy restored all seven, but marginal fitted-axis
  p95 and one released-PyBDSF S/N-15 flux tail moved back to fail. Continuum
  improved from 86/143 to 122/143 passing endpoints, but one formerly passing
  filament flux p95 and three formerly underpowered shell/tile position tails
  became failures on the larger, observable-truth population.
- Tested the present component split on 20 evenly spaced images from the
  sealed 800-image post-failure compact population, using transient outputs
  only and fitted-component semantics. Marginal fitted-axis p95 improved from
  0.1719 to 0.1665, but overall fitted-position-angle median changed from
  0.00020 to 1.1452 degrees versus Aegean's 0.4751. Unresolved p95 changed from
  0.00024 to 4.9716 degrees versus Aegean's 0.8144. This projects the exact
  seven position-angle endpoint failures already observed in confirmation;
  the current candidate is therefore not ready for another external freeze.

**Decision:** block the next seed-disjoint campaign until one coherent compact
component model passes position, flux, fitted-axis, and fitted-position-angle
requirements together. Require a machine-readable cumulative regression
ledger on the complete viewed 800-image compact population and full Continuum
regression matrix. The ledger must preserve prior passes under like semantics,
show all status transitions, and isolate algorithm effects from compiler,
truth, catalogue-semantics, and population changes. Any deliberate trade-off
requires named scientific approval.

**Validation:** the strict documentation build passes. `just check` passes
Ruff, Pyright, 1,234 tests, and four expected xfails. The documentation-only
review against `CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** pre-review component-model alternatives that can
retain the beam-or-free position-angle stability and independent-fit axis/flux
accuracy, then implement and evaluate the selected option against the complete
cumulative ledger before any campaign freeze or power audit.

## 2026-08-15 — Selected a conjunctive compact component candidate

**Plan phase:** Phase 5, cumulative-regression remediation

- Reviewed the Gaussian-component conventions documented by PyBDSF and
  Aegean. Both expose one complete fitted ellipse; neither supports combining
  axes from one model with the position angle of another. Rejected that mixed
  representation and retained an auditable whole-model choice.
- Evaluated correlated-GLS component significance thresholds from 1.0 through
  5.0 plus a diagonal-weighted alternative on the same 20 evenly spaced,
  already viewed compact images used by the regression audit. The threshold
  was selected before opening the complete replay.
- Locked a 1.5-sigma log-area boundary for Gaussian components while keeping
  the five-sigma source boundary. On the fixed slice, marginal fitted-axis p95
  is 0.16857 and unresolved fitted-position-angle p95 is 1.02244 degrees.
  Free-only publication measured 0.16647/4.9716, while a two-sigma boundary
  measured 0.18293/0.00026. The selected boundary therefore retains most of
  the axis improvement without republishing the known unresolved-angle
  failure. The diagonal estimator was worse for marginal axes, position, and
  flux.
- Added an explicit validated component threshold, whole-fit publication, and
  a restartable cumulative-regression runner. The runner re-verifies the
  sealed 2,400-image campaign, replays the prospective candidate, evaluates
  all 593 applicable compact and 143 Continuum endpoints with unchanged
  PyBDSF/Aegean gates, records every historical status transition, and deletes
  its transient large products only after atomic ledger publication.

**Decision:** the 1.5-sigma policy is the single prospective candidate for the
complete viewed replay. It is not authorized for a fresh campaign and will not
be changed in response to the 800-image/1,600-image cumulative result.

**Validation:** 157 focused fitting, configuration-identity, historical
protocol, and cumulative-ledger tests pass. One real compact image and one real
Continuum image completed the new product boundary; the historic normalizer
finds exactly 593 compact and 143 Continuum decisions in each of the four
retained external campaigns. Branch-aware coverage passes 1,369 tests with
four expected xfails at 94.27%; all 27 equivalence tests pass; `just check`
passes Ruff, Pyright, 1,240 tests, and four expected xfails; and the strict
documentation build passes. The complete cumulative replay remains next.

**Immediate next step:** complete project validation, commit the locked
candidate, then run the full cumulative ledger from that immutable revision.

## 2026-08-16 — Rejected the first cumulative replay and locked corrections

**Plan phase:** Phase 5, cumulative-regression remediation

- Completed the full viewed 800-image compact and 1,600-image Continuum replay
  from revision `f1001c1...`. Ledger SHA-256 `f6a92d39...` is `fail`. Every
  one of 450 PyBDSF and 143 applicable Aegean compact comparisons passes, so
  the 1.5-sigma whole-model boundary resolves the earlier component-model
  oscillation. Three compact absolute fitted-total uncertainty-bias intervals
  fail. Continuum has 132 passes, one absolute failure, ten underpowered
  endpoints, and two pass-to-nonpass position comparisons: image-edge and
  filled diffuse against pinned PyBDSF master.
- Rejected a global compact uncertainty multiplier on 200 seed-disjoint
  development images (seeds 2026880001--2026880200). No predeclared factor
  passed coverage, bias, and dispersion together. A fitted-total point
  correction of 0.075 formal sigma is the smallest of 0, 0.05, 0.075, and 0.1
  to pass all 15 calibration gates; 0.05 still fails edge bias. The selected
  edge interval is [-0.00513, 0.14578] and the formal error is unchanged.
- Compared original, residual-B3, and direct-plus-residual-B3 position signals
  on 80 seed-disjoint Continuum images across the four governed geometries
  (seeds beginning 2026890001, 2026891001, 2026892001, and 2026893001).
  Unrestricted B3 fails with a worst 0.53288-beam p95 upper bound. The
  direct-plus-B3 first moment passes every position endpoint with a worst
  0.45618-beam bound; original pixels remain the flux measurement and the
  concentration safeguard remains unchanged. All 280 development seeds are
  disjoint from every checked-in dataset manifest.
- Added exact fitted-total calibration evidence to the scheduler-safe fit,
  applies it only at catalogue transformation, and marks corrected products.
  Added the regularized direct-plus-B3 position plane. The cumulative runner
  now records raw endpoint analysis for exact power planning, distinguishes a
  scientifically clean but underpowered result from an algorithm failure, and
  can reuse only the exact checksum-bound closed component compile.

**Decision:** lock both corrections before the next complete cumulative replay.
No external population is frozen and no execution is authorized. A passing
science ledger with underpowered favourable pairs must be followed by a new
endpoint-level power review and larger seed-disjoint population, not by more
algorithm changes.

**Validation:** 164 focused scientific and historical-protocol tests pass;
branch-aware coverage passes 1,377 tests with four expected xfails at 94.27%;
all 27 equivalence tests pass; `just check` passes Ruff, Pyright, 1,248 tests,
and four expected xfails; and the strict documentation build passes. The final
review against `CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** validate and commit the locked corrections, run the
complete cumulative replay from that immutable revision, then prepare the
exact power and named scientific freeze review.

## 2026-08-16 — Passed cumulative science and powered the fresh design

**Plan phase:** Phase 5, post-correction cumulative and power review

- Completed all 2,400 development replays from immutable revision
  `dfc3e25...` and atomically published write-once cumulative ledger
  `7ffd6364...`. It binds source tree `a549143b...`, configuration
  `0e5dde51...`, sealed campaign `c16dc486...`, and the exact reusable closed
  baseline ledger `f6a92d39...`; the latter matches its predeclared SHA-256.
- Evaluated science before power. The compact fitted-component view passes all
  450 PyBDSF and 143 applicable Aegean comparisons. Continuum has 134 passes,
  nine favourable underpowered comparisons, no failures or indeterminate
  results, and every absolute gate passes. Neither compact nor Continuum has
  a like-semantics pass-to-nonpass regression, so
  `cumulative_science_regression_ready` is true.
- Ran the committed endpoint-level power review without changing the locked
  science. Review `d68163f5...` retains 226 paired assumptions, a 1.25 variance
  inflation, 50% advantage retention, and a 10% population safety factor. The
  theoretical minimum is 1,532 Continuum realizations; the balanced selected
  design is 1,688 (422 per geometry) plus 800 compact realizations. The
  conservative Continuum, compact, and combined familywise power lower bounds
  are 0.995300, 0.909784, and 0.905084 against the 0.90 joint minimum.

**Decision:** the candidate and powered design are ready for named scientific
freeze review. No fresh population identity has been frozen, execution is not
authorized, and Step 3 remains closed. The next required decision is named
scientific approval of this exact candidate and 1,688-Continuum/800-compact
design before fresh seeds, configurations, programs, and runtimes are frozen;
the resulting identities require a separate one-look execution decision.

**Validation:** 43 focused cumulative-protocol and power tests pass.
Branch-aware coverage passes 1,378 tests with four expected xfails at 94.28%,
including 100% coverage of the power module. `just check` passes Ruff,
Pyright, 1,248 tests, and four expected xfails. The strict documentation build
passes. The final `CODE_REVIEW.md` review found no actionable issue.

**Immediate next step:** obtain named scientific approval of the exact
candidate and powered design before freezing fresh external identities. Do not
execute the fresh campaign until those identities return for a separate named
one-look approval.

## 2026-08-16 — Froze powered post-correction external identities

**Plan phase:** Phase 5, fresh external freeze

- Gemma Danks approved candidate `dfc3e25...` and the exact powered design for
  freezing on 2026-08-16. The write-once population contract `f1fec27a...`
  binds source tree `a549143b...`, configuration `0e5dde51...`, cumulative
  ledger `7ffd6364...`, power review `d68163f5...`, 1,688 Continuum images,
  and 800 compact images. Its audit finds all 2,488 fresh seeds disjoint from
  14,253 checked-in historical and 280 reserved development seeds.
- Froze the two population manifests, comparison protocol, three finder
  runners, two-lane launcher, endpoint registry, terminal compiler, evaluator,
  and a pending execution decision. The design contains 12,440 terminal runs
  and 8,264 binding runs, retains two resource lanes and four PyBDSF cores,
  and preserves the one-look rule and all existing science gates. The launcher
  rejects the pending decision before creating campaign state.
- Built the Hebog runtime from a clean archive of the approved revision. Its
  image ID is `6dc0ae8e...`, digest is `sha256:7f6a44e9...`, dependency
  inventory is `d383be3a...`, and a network-disabled source-tree check returns
  `a549143b...`. The exact released-PyBDSF, pinned-master, and Aegean runtimes
  remain bound. A network-disabled non-scientific probe passes for both
  two-image resource lanes; its largest pairwise shared-layer ratio is 0.633.
- The no-write operational review records 37.88 GiB available against the
  predeclared 126-GiB minimum. It therefore remains
  `identities-frozen-storage-blocked-before-named-execution-approval` and does
  not recommend the separate one-look decision. The 106-GiB closed
  post-failure campaign is the main recoverable storage consumer, but no
  evidence was deleted without explicit authorization. Both public and private
  post-correction output paths remain absent; no finder product was generated
  or opened.

**Decision:** the scientific population, programs, configurations, and
runtimes are frozen and may not change without a new review. Execution is not
authorized. Restore storage headroom and repeat the no-write operational review
before requesting the separate named one-look approval.

**Validation:** 30 focused fresh and inherited protocol tests pass, covering
population disjointness, approval and power binding, pending authorization,
program/runtime identities, compiler/evaluator composition, canonical review
evidence, and write-once behavior. Branch-aware coverage passes 1,385 tests
with four expected xfails at 94.28%. `just check` passes Ruff, Pyright, 1,255
tests, and four expected xfails; the strict documentation build passes.

**Immediate next step:** obtain explicit retention/cleanup direction for the
closed raw campaign, restore at least 126 GiB available without changing any
frozen identity, and refresh only the observational preflight review before
returning the exact one-look execution decision for approval.

## 2026-08-16 — Restored post-correction campaign readiness

**Plan phase:** Phase 5, post-correction operational preflight

- Confirmed 127.63 GiB available after runtime reconstruction, exceeding the
  predeclared 126-GiB floor. Both the public campaign directory and its private
  write-once staging directory remain absent; no scientific campaign product
  was generated or opened.
- Reconstructed all four deleted Linux/arm64 runtimes from the pinned BDSF and
  Aegean artifacts and the clean `dfc3e25...` Hebog archive. The replacement
  image IDs are Hebog `e519dc15...`, released PyBDSF `43a65138...`, pinned
  master `0360fbbf...`, and Aegean `9e79e24b...`. Network-disabled checks
  reproduce Hebog source tree `a549143b...` and dependency inventories
  `d383be3a...`, `8211043e...`, `83574dd4...`, and `346c1f32...`.
- The committed non-scientific two-lane probe passes for every pairing with
  identical output `f1a8008c...`; the largest overlap ratio is 0.694. Refreshed
  only the runtime-bound helper, pending decision, registry, evaluation, and
  preflight identities. Population, science protocol, candidate, thresholds,
  power, runners, compiler, evaluator behavior, and one-look rule are
  unchanged. Preflight review `30eb5576...` is now
  `ready-for-named-execution-approval` while execution remains unauthorized.

**Decision:** the operational block is cleared, but rebuilding necessarily
created new OCI identities because the base package layers are not bitwise
reproducible. The pending decision still fails closed. A separate named
one-look approval must explicitly bind review `30eb5576...` and these four
replacement runtimes before authorization or campaign output may begin.

**Validation:** the focused post-correction suite passes seven tests after a
test-first identity/readiness update. Branch-aware coverage passes 1,385 tests
with four expected xfails at 94.28%. `just check` passes Ruff, Pyright, 1,255
tests, and four expected xfails. The strict documentation build passes.

**Immediate next step:** return review `30eb5576...` and the four replacement
OCI identities for separate named one-look approval. Do not authorize or run
the campaign before that approval and a fresh complete no-write preflight.

## 2026-08-16 — Bound the post-correction one-look approval

**Plan phase:** Phase 5, post-correction exact-identity authorization

- Gemma Danks explicitly approved the Phase 5 post-correction one-look
  execution bound to preflight review `30eb5576...` and its exact four rebuilt
  runtime identities. The approval retains the 2,488-image, 12,440-run,
  two-lane design, four PyBDSF cores, all frozen science gates, and the terminal
  one-look rule.
- Changed only the authorization-dependent chain. Decision `222eb298...` now
  authorizes one terminal post-correction comparison and embeds the complete
  review checksum. The endpoint registry and evaluation contract bind the new
  decision and registry identities. Candidate, population, configurations,
  runners, compiler/evaluator behavior, resource policy, qualification state,
  and scientific thresholds are unchanged; `one_look_opened` remains false.

**Decision:** authorization is sufficient to run the complete no-write
preflight from the immutable authorization commit. Campaign output may be
created only if that exact preflight passes.

**Validation:** the test-first focused authorization suite passes seven tests.
Branch-aware coverage passes 1,385 tests with four expected xfails at 94.28%.
`just check` passes Ruff, Pyright, 1,255 tests, and four expected xfails. The
strict documentation build passes.

**Immediate next step:** validate and commit the authorization, create its
immutable execution checkout, run the no-write preflight, and launch the
single terminal campaign only on success. Monitor operational state hourly and
evaluate only after the terminal campaign is sealed.

## 2026-08-16 — Corrected stale reference identities before campaign output

**Plan phase:** Phase 5, post-correction no-write preflight correction

- Ran the authorized complete no-write preflight from detached immutable
  commit `d28a090...`. It failed before request publication or campaign-state
  creation because the inherited post-failure protocol still exposed the
  deleted released-PyBDSF, pinned-master, and Aegean digests. The live images
  matched review `30eb5576...`; the execution adapter did not.
- Added a focused regression assertion for all three reference digests and
  changed only the post-correction protocol projection to overlay the exact
  rebuilt identities already recorded in `_RUNTIME_IMAGES`. Candidate source,
  dependency inventories, source revisions, populations, configurations,
  endpoints, thresholds, runners, compiler/evaluator behavior, and resource
  policy are unchanged.
- Refreshed the fail-closed identity chain. Verifier `6888ac86...`, pending
  decision `4971620f...`, registry `2f22a932...`, evaluation `c0b69503...`, and
  corrected review `88df5916...` now agree. The review records 128.02 GiB
  available and absent public/private campaign paths. Execution is unauthorized
  again because the verifier checksum changed after the prior named approval.

**Decision:** this was an operational identity-plumbing defect caught by the
mandatory no-write gate, not scientific evidence. No finder output was
generated or opened and the one-look remains unopened. Review `30eb5576...`
cannot authorize the changed verifier; renewed approval must bind corrected
review `88df5916...` and the same four runtime identities.

**Validation:** the new reference-digest assertion failed against all three
stale inherited digests, then the focused seven-test suite passed after the
minimal projection fix. Branch-aware coverage passes 1,385 tests with four
expected xfails at 94.28%. `just check` passes Ruff, Pyright, 1,255 tests, and
four expected xfails. The strict documentation build passes.

**Immediate next step:** complete validation and commit the corrected
fail-closed review, then obtain renewed one-look approval for `88df5916...`.

## 2026-08-16 — Bound the corrected post-correction one-look approval

**Plan phase:** Phase 5, corrected post-correction exact-identity authorization

- Gemma Danks explicitly approved the corrected Phase 5 one-look execution
  bound to preflight review `88df5916...` and the unchanged four rebuilt
  runtime identities. The approval retains the 2,488-image, 12,440-run,
  two-lane powered design, execution concurrency two, four PyBDSF cores, all
  frozen science gates, and the terminal one-look rule.
- Changed only the authorization-dependent chain after a test-first failure
  confirmed that the prior decision was still fail-closed. Decision
  `829c3b8f...` authorizes one terminal comparison and embeds the complete
  corrected review checksum. Registry `7fdb10c9...` and evaluation
  `039877ff...` bind the new decision and registry identities. Candidate,
  population, configurations, runtimes, runners, compiler/evaluator behavior,
  resource policy, qualification state, and scientific thresholds are
  unchanged; `one_look_opened` remains false.

**Decision:** the renewed approval is sufficient to run the complete no-write
preflight from the immutable authorization commit. Campaign state may be
created only if that exact preflight passes.

**Validation:** the focused authorization assertion failed for the intended
pending-decision reason before the contract update, then all seven focused
post-correction protocol tests passed.

**Immediate next step:** complete repository validation, commit this narrow
authorization transition, create a new immutable execution checkout, and run
the complete no-write preflight. Launch the one terminal campaign only on
success, monitor operational state hourly, and evaluate only after sealing.

## 2026-08-17 — Evaluate terminal post-correction comparison (blocked)

**Plan phase:** Phase 5, post-correction terminal decision

- Complete no-write preflight from immutable review `88df5916...` and the approved
  immutable authorization chain passed. The terminal campaign sealed with 2,488 inputs
  and 12,440 runs from immutable campaign checkout `da2792ddd9...`.
- The committed write-once analysis artifact is
  `benchmark-results/phase-5/external-post-correction-analysis.json` with SHA
  `46dab5a12ab2818f3da7d03d15abe2369cef693660c49424928ea4e15b9d2cff`.
- The committed evaluator produced
  `benchmark-results/phase-5/external-post-correction-decision.json` with terminal
  decision id `phase-5-external-post-correction-terminal-decision`, SHA
  `e00f0520c662cb590dc1262a1ebaa956f315178be5359c5fd686ab9359ecaffc`, and
  status `fail`.
- Continuum has 129 passes and 14 failures: 13 integrated-flux p95 absolute-
  gate failures and one `continuum--mask-precision--overall` paired comparison
  regression against pinned PyBDSF master. Compact passed all 450 PyBDSF
  comparisons but failed six binding Aegean integrated-flux comparisons, so
  its terminal status is also `fail`.

**Decision:** this terminal campaign is a hard fail and scientifically blocks
optimization or candidate-specific tuning from this result. Preserve the fail-closed
artifacts and require named remediation approval before any re-run strategy.

**Validation:** protocol-focused tests pass (`7 passed`). Branch-aware coverage
and focused Python checks were run once the campaign result existed: 1389 selected
unit/integration tests passed with total coverage 94.24%; 3 integration tests
failed because this environment cannot start a local Dask scheduler (`PermissionError:
[Errno 1] Operation not permitted` binding sockets). `just check`-equivalent
with local `.venv` also fails (`pyright` import/type resolution in this runtime
path). `mkdocs build --strict` passed. `pre-commit` failed only on `uv-lock`
from `/Users/gemma.danks/.cache/uv/sdists-v9/.git` permission.

**Immediate next step:** retain the closed decision as the high-integrity record,
separate compiler-measurement defects from candidate science failures, and use
only prospective development and regression evidence before requesting a new
named approval path.

## 2026-08-20 — Review interrupted Phase 5 closeout and staged remediation

**Plan phase:** Phase 5, post-correction recovery planning

- Reverified the terminal campaign, analysis, and decision identities. The
  campaign and write-once analysis completed successfully; the interrupted
  work was the subsequent closeout and remediation, not raw execution or
  scientific compilation.
- Reviewed the staged remediation. It changes the checksum-bound historical
  compiler from `7a055891...` to `ff890dfd...`, which breaks the inherited
  protocol chain. Focused compiler/protocol validation produced 28 passes,
  seven failures, and four setup errors, all failures/errors rooted in the
  changed historical identity.
- The staged support-flux changes are bypassed by the successor measurement
  kernel used by the post-correction campaign and do not address the compact
  lane. The valid-region mask correction agrees with the frozen metric
  definition but requires a new prospective composition and regression tests.

**Decision:** do not commit or bind the staged compiler change. Preserve closed
programs byte-for-byte, correct the historical campaign record, and add an
ordered prospective recovery gate before Step 3.

**Immediate next step:** restore and verify the historical compiler identity,
then complete the named failure review and test-first prospective measurement
composition defined in Step 2C-PC.

## 2026-08-20 — Condensed the authoritative source-finder plan

**Plan phase:** Cross-phase plan maintenance

- Replaced campaign-by-campaign chronology and repeated implementation rules
  with a forward-only plan. Detailed evidence, immutable identities, rejected
  candidates, and execution deviations remain in this log and the reviewed
  machine-readable contracts.
- Reduced `plans/source-finder-implementation.md` from 2,382 lines and 20,502
  words to 601 lines and 4,352 words. The condensed plan retains the current
  terminal campaign result, Step 2C-PC recovery order, Phase 5 exit gate,
  scientific and performance thresholds, dataset/test obligations,
  architecture boundaries, Phases 6--8, principal risks, and definition of
  done.
- Updated four historical documentation links whose former plan headings were
  removed or renamed. Phase 0 review links now target the condensed scientific
  gate and dataset sections; Phase 4/4R records link to durable execution
  history instead of a removed historical plan milestone.

**Decision:** keep the plan short enough to guide current work and use
`LOG.md`, reviewed records, and contracts as the detailed historical and exact
evidence sources. Add chronology to the log, not back into the plan.

**Validation:** `git diff --check` and `just docs-build` pass. Full repository
validation remains deliberately blocked by the separately staged rejected
historical-compiler edit; restoring its exact identity is the next task.

**Immediate next step:** execute the first unchecked Step 2C-PC task: restore
historical compiler identity `7a055891...` and verify the inherited evidence
chain before prospective remediation.

## 2026-08-20 — Restore the compiler and isolate the campaign composition defect

**Plan phase:** Phase 5, Step 2C-PC recovery

- Restored `scripts/validation/compile_phase5_external_campaign.py`
  byte-for-byte to historical SHA-256 `7a055891...`. The rejected staged
  support-flux and valid-mask edits are no longer present; the sealed campaign,
  analysis, and decision remain unchanged.
- Re-ran the complete inherited compiler/protocol suite: all 39 tests pass.
- Audited all 2,488 successful Hebog run records. Every run uses the expected
  source revision `dfc3e25...` but reports configuration SHA `72d5d5c1...`,
  not the approved candidate configuration `0e5dde51...`.
- Traced the continuum runner. It emitted catalogue flux through the historical
  four-beam default instead of the approved 1.5-beam aperture, omitted the
  regularized position signal, and retained the earlier cleanup rather than
  the reviewed residual-B3 boundary refinement.
- Traced the compact compiler. It used the default Rapthor-source
  canonicalization instead of the approved fitted-Gaussian-component view;
  this directly explains why the six failures are all Aegean integrated-flux
  comparisons while the cumulative component view passed.
- Inspected the declared invalid rectangle in all 1,688 Hebog label products
  and both modes of both PyBDSF references. No product contains a positive
  invalid-region label, so valid-domain clipping is required prospective
  contract hardening but cannot explain or repair the mask-precision failure.

**Decision:** the closed campaign remains a terminal `fail`, but it did not
execute the candidate composition that had been approved. Do not tune the
algorithm from this population. Prepare a prospective runner/compiler that
enforces the approved composition and configuration identity, then repeat the
complete cumulative regression replay before considering fresh evidence.

**Validation:** historical compiler SHA is exact; 39 focused compiler and
protocol tests pass. The recovery pre-review is recorded in
`docs/reference/phase-5-post-campaign-failure-review.md` and awaits named
approval.

**Immediate next step:** obtain named approval of the recovery pre-review,
then implement the exact candidate adapter and prospective compiler with
test-first composition and fail-closed identity checks.

## 2026-08-20 — Implement the approved Phase 5 recovery composition

**Plan phase:** Phase 5, Step 2C-PC recovery

- Gemma Danks approved the recovery pre-review and its recommendations for
  prospective implementation and viewed-development regression work. The
  approval does not authorize a fresh campaign or reinterpret closed evidence.
- Added one shared candidate-product adapter that reconstructs approved
  configuration SHA `0e5dde51...` and carries refined residual-B3 support,
  1.5-beam nearest-owned photometry, and regularized position weights through
  the emitted Continuum catalogue.
- Added a prospective compiler composition that rejects any Hebog run with a
  different configuration identity, uses fitted-Gaussian-component semantics
  for compact comparisons, retains comparison failures in the denominator,
  and applies the valid-pixel domain symmetrically to Hebog and both PyBDSF
  references.
- Refactored the viewed cumulative replay to consume the shared adapter and
  compiler seams instead of maintaining a second candidate composition.
  Checksum-bound historical campaign programs and closed evidence were not
  changed.

**Decision:** keep the reviewed candidate scientifically unchanged. The next
evidence step is a complete viewed cumulative replay using this exact product
and compiler composition; only a reproducible development-evidence failure can
reopen algorithm correction.

**Validation:** 104 focused recovery, compiler, and inherited protocol tests
pass. `just coverage` passes with 1,403 tests, four expected failures, 94.34%
project coverage, and 100% line and branch coverage for both new modules.
`just check` passes with 1,273 unit/doctest cases plus clean Ruff and Pyright;
the strict documentation build also passes.

**Immediate next step:** complete repository handoff validation, commit this
composition locally, then run the complete cumulative regression replay and
require no like-semantics regression before any power or fresh-campaign review.

## 2026-08-20 — Bind reconstruction of the viewed reference evidence

**Plan phase:** Phase 5, Step 2C-PC recovery

- Confirmed that approved cleanup had removed the raw inputs and finder
  products needed by the viewed replay while preserving the sealed campaign,
  request, analysis, and decision. Gemma Danks explicitly confirmed permanent
  removal of the obsolete post-correction raw `inputs/` and `results/` trees;
  available host storage increased to 133 GiB.
- Added a development-only, restartable reconstruction boundary for the exact
  1,600 Continuum and 800 compact viewed population. It materializes the bound
  inputs, runs only the released/master PyBDSF and Aegean reference legs, and
  seals checksum sets atomically. It cannot run the obsolete historical Hebog
  candidate or authorize a fresh campaign.
- Bound the equivalent rebuilt reference images by OCI ID, digest, dependency
  inventory, reference source, four-core PyBDSF policy, and checksum-verified
  wrapper. The original viewed protocol, request SHA `7ba9be1b...`, and sealed
  campaign SHA `c16dc486...` remain unchanged and identify the population.
- Extended the cumulative replay to accept the sealed reference
  reconstruction and synthesize Hebog products only through the shared
  recovery adapter at candidate revision `c184acf...` and configuration
  `0e5dde51...`. The ledger separately records the recovery execution checkout
  and reconstructed-reference manifest identity.

**Decision:** reconstructed references are permitted only because their
scientific package/source/dependency identities match the deleted runtimes;
their changed OCI digests remain explicit. This is viewed development evidence,
not a replacement or rescore of the closed campaign.

**Validation:** the new contracts were developed from three failing tests.
The focused recovery, cumulative, and inherited protocol suite passes all 51
tests. `just coverage` passes with 1,406 tests, four expected failures, and
94.34% branch-aware project coverage; `just check` passes 1,276 quick tests,
and focused Pyright, strict docs, and the final pre-commit suite pass.

**Immediate next step:** finish repository validation and commit the recovery
boundary, run its no-write preflight, then launch and monitor the complete
viewed reconstruction followed by the write-once cumulative ledger.

## 2026-08-21 — Correct the viewed replay runtime record

**Plan phase:** Phase 5, Step 2C-PC recovery

- Sealed the viewed reference reconstruction with all 2,400 inputs and 9,600
  checksum-verified reference runs. The first cumulative process stopped
  before candidate work because the app sandbox denied the host semaphore
  capability check; the exact approved command was restarted outside that
  sandbox.
- Completed all 2,400 restartable Hebog candidate products through the shared
  recovery adapter. Compilation then stopped before publishing a ledger
  because the reconstructed view's synthetic Hebog runtime was an unhashable,
  incomplete `SimpleNamespace`; the compact compiler correctly requires one
  immutable runtime identity per implementation.
- Replaced only that provenance record with `ExternalRuntimeIdentity`, bound
  to candidate revision `c184acf...`, Hebog version `0.6.0`, and the exact
  materializer digest and dependency inventory in the approved viewed-recovery
  decision. Candidate products, scientific settings, compiler policy, gates,
  reconstructed references, and the write-once ledger path are unchanged.

**Decision:** treat both stops as execution-boundary defects, not scientific
results. Preserve and re-verify the complete 7.9 GiB restartable candidate
product set; no partial science was interpreted and no atomic ledger exists.

**Validation:** the new runtime-shape assertion failed first on the unhashable
namespace. The corrected test plus the focused recovery and compiler suite
passes all 58 tests. `just coverage` passes with 1,407 tests, four expected
failures, and 94.34% branch-aware project coverage; `just check` passes 1,277
quick tests, and focused Pyright and the strict documentation build pass.

**Immediate next step:** complete repository validation, commit this
provenance-only correction, and resume the same write-once cumulative replay
from its identity-verified candidate shards.

## 2026-08-22 — Pass the complete viewed cumulative science replay

**Plan phase:** Phase 5, Step 2C-PC recovery

- Published the write-once viewed-development cumulative ledger after
  re-verifying all 2,400 candidate shards. Ledger SHA-256 is
  `a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9`.
- Verified the full identity chain: sealed viewed population
  `c16dc486...`, reference reconstruction `69c66e0b...`, exact closed-component
  baseline `f6a92d39...`, candidate revision `c184acf...`, recovery execution
  revision `53f745f...`, candidate source tree `b4176ce3...`, configuration
  `0e5dde51...`, and transient product-set identity `03f69ad2...`.
- Compact science passes. The PyBDSF compact decision passes and all 143
  binding fitted-component Aegean comparisons pass; there are no compact
  failure reasons and no like-semantics compact regression.
- All 143 Continuum absolute gates pass. Of the paired endpoints, 134 pass and
  nine are `underpowered`; none fail or become indeterminate, and there is no
  like-semantics Continuum regression. The nine outcomes are integrated-flux
  median or p95 strata whose absolute values remain within their frozen 10%
  or 25% limits but whose observed paired variance exceeds a planning bound.

**Decision:** the correctly composed candidate is scientifically regression
ready (`cumulative_science_regression_ready=true`). The ledger is
`pass-pending-power-review`, not a failure: exact endpoint power must be
reviewed before a fresh campaign can be frozen. Fresh execution, Step 3, and
qualification remain unauthorized.

**Validation:** 58 focused recovery/compiler tests pass. `just coverage`
passes 1,407 tests with four expected failures and 94.34% branch-aware
coverage; `just check` passes 1,277 quick tests, and the strict documentation
build and final pre-commit suite pass.

**Immediate next step:** recompute exact endpoint power for the nine
underpowered Continuum outcomes, then obtain named review of the candidate,
population, compiler/evaluator composition, and four runtime identities before
freezing any fresh seed-disjoint campaign.

## 2026-08-22 — Complete the viewed-recovery power review

**Plan phase:** Phase 5, Step 2C-PC recovery

- Corrected the power reviewer’s provenance boundary: candidate revision
  `c184acf...` remains the scientific identity, while replay revision
  `53f745f...` and review revision `3981d7f...` are recorded separately. The
  reviewer now also fails closed on recovery decision `b35f4a81...`, sealed
  campaign `c16dc486...`, reconstructed references `69c66e0b...`, exact
  closed baseline `f6a92d39...`, source tree `b4176ce3...`, and configuration
  `0e5dde51...`.
- Published write-once review
  `benchmark-results/phase-5/viewed-recovery-power-review.json`, SHA-256
  `bbfab3a0781c8a12083190d8c591152d5c461a45824bab6cba39e770915af9fc`.
  Its unchanged approved method covers all 226 endpoint/reference pairs with
  1.25 variance inflation, 50% retained advantage, and a 10% population safety
  buffer.
- The theoretical Continuum minimum is 1,532; the balanced selection is 1,688
  images, 422 for each of four geometries, plus the governed 800 compact
  images. Continuum, compact, and combined conservative familywise power lower
  bounds are 0.995300, 0.909784, and 0.905084 respectively, so the combined
  result exceeds the required 0.90.

**Decision:** power is ready for named scientific freeze review. No fresh
population or program identity was frozen, and execution, Step 3, and
qualification remain unauthorized. The named boundary must cover the approved
candidate, the 1,688/800 population, the prospective recovery
compiler/evaluator composition, and the four runtime identities already bound
by recovery decision `b35f4a81...`.

**Validation:** the provenance regression test failed first, then the focused
49-test recovery/protocol suite passed. `just coverage` passes 1,408 tests with
four expected failures and 94.34% branch-aware coverage; `just check` passes
1,278 quick tests, and Ruff, Pyright, the strict documentation build, and the
final pre-commit suite pass. Code review found no actionable issue.

**Immediate next step:** obtain Gemma Danks’s named scientific approval of the
stated freeze boundary. After approval, update and verify the fresh freeze and
program identities without executing the campaign, then present the separate
one-look execution decision.

## 2026-08-22 — Freeze the fresh Phase 5 recovery identities

**Plan phase:** Phase 5, Step 2C-PC recovery

- Gemma Danks gave named scientific approval of candidate `c184acf...`, source
  tree `b4176ce3...`, configuration `0e5dde51...`, the powered 1,688/800
  design, the prospective recovery composition, and the four runtimes in
  recovery decision `b35f4a81...`. The approval explicitly permits identity
  freezing only and does not authorize execution.
- Created a new recovery namespace rather than altering the closed
  post-correction contracts. Its 1,688 Continuum seeds occupy four new
  422-image blocks beginning `2026920001`, `2026921001`, `2026922001`, and
  `2026923001`; its 800 compact seeds begin `2026930001`. All 2,488 are
  disjoint from the 16,741 seeds in 43 checked-in historical manifests.
- Bound population `c2a4ac5b...`, comparison `717afa1e...`, pending execution
  decision `67b8deef...`, endpoint registry `5754aa43...`, and evaluation
  contract `b2d0a88e...`. The new Hebog runner emits the shared approved
  1.5-beam/refined-residual-B3/regularized-position product composition and
  exact candidate configuration; the terminal compiler installs the
  fitted-component compact and symmetric-valid-domain seams proven by the
  cumulative replay.
- Published identity review
  `config/contracts/phase-5-external-recovery-identity-review.json`, SHA-256
  `5bdf4f46f33fc47d1fed787ec29cf56147fe03b49bf9d33442980edeca70c13a`.
  It binds 17 program/data artifacts and the exact Hebog, released PyBDSF,
  pinned-master PyBDSF, and Aegean runtime identities. Both public and private
  recovery output paths are absent; no scientific product was generated or
  opened.

**Decision:** the scientific and program freeze is complete, but the one-look
remains closed. The execution decision is pending, `execution_authorized` is
false, and the launcher rejects both preflight and execution until a separate
named approval is bound to identity review `5bdf4f46...` and its four exact
runtimes. Step 3 and qualification remain unauthorized.

**Validation:** the population test first failed because the recovery freezer
did not exist. Five focused recovery-freeze tests and the complete 53-test
recovery/historical protocol suite now pass; focused Ruff and Pyright are
clean. `just coverage` passes 1,413 tests with four expected failures and
94.34% branch-aware coverage; `just check` passes 1,283 quick tests with four
expected failures. The strict documentation build and final pre-commit suite
also pass. Review against `CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** request the separate named one-look execution approval.
Do not run the no-write preflight or campaign before that approval.

## 2026-08-22 — Correct the recovery authorization transition before preflight

**Plan phase:** Phase 5, Step 2C-PC recovery authorization

- Gemma Danks approved one-look execution bound to identity review
  `5bdf4f46...` and its four exact runtimes, authorizing the complete no-write
  preflight and conditional execution only without an identity change.
- The attempted authorization transition stopped before preflight because the
  frozen recovery verifier accepted only the pending decision. Updating the
  decision alone would fail verification, while changing the verifier after
  approval would violate the approved identity boundary. No preflight request,
  staging directory, campaign state, or scientific product was created.
- Added test-first dual pending/approved decision validation and explicit
  preservation of the pre-authorization review across changes to only the
  decision, registry, and evaluation contracts. Candidate `c184acf...`, source
  `b4176ce3...`, configuration `0e5dde51...`, population `c2a4ac5b...`,
  comparison `717afa1e...`, pending decision `67b8deef...`, all seeds, science
  gates, runners, compiler/evaluator behavior, and four runtimes are unchanged.
- Cascaded only the corrected verifier `690e2f2a...` through registry
  `52bd44a6...` and evaluation `9411a9f5...`. Replacement identity review
  `8aaaca742f782f94cbcccbcc53a0a396459ccc5902e46c519a675933a79d6c63`
  remains `ready-for-named-execution-approval`; the decision remains pending,
  `execution_authorized` is false, and `one_look_opened` is false.

**Decision:** review `5bdf4f46...` is superseded without having opened the
one-look. Its approval cannot authorize the changed verifier. The corrected
review and unchanged four runtimes require renewed named approval before the
no-write preflight or campaign may run.

**Validation:** both new authorization-transition tests failed for their
intended pending-only and review-revalidation reasons, then pass. The focused
seven-test recovery suite and 56-test recovery/historical protocol suite pass;
focused Ruff and Pyright are clean. `just coverage` passes 1,415 tests with
four expected failures at 94.34% branch-aware coverage; `just check` passes
1,285 quick tests with four expected failures, and the strict documentation
build and final pre-commit suite pass. Review against `CODE_REVIEW.md` found no
actionable issue.

**Immediate next step:** commit the corrected fail-closed identity package
locally, then request renewed approval bound to review `8aaaca74...` and its
exact four runtimes.

## 2026-08-22 — Bind the corrected recovery one-look approval

**Plan phase:** Phase 5, Step 2C-PC exact-identity authorization

- Gemma Danks explicitly approved corrected identity review `8aaaca74...`, its
  unchanged four runtime identities, and transition of exact pending decision
  `67b8deef...`. The approval authorizes the complete no-write preflight and
  conditional execution only if no frozen identity changes.
- Changed only the authorization-dependent chain. Decision `7a44ba52...` now
  embeds the complete corrected review SHA, records the named approval, and
  authorizes one terminal recovery comparison. Registry `9486e210...` and
  evaluation `9ef1a4f6...` bind that decision and registry respectively.
- Candidate `c184acf...`, source `b4176ce3...`, configuration `0e5dde51...`,
  population `c2a4ac5b...`, comparison `717afa1e...`, verifier `690e2f2a...`,
  seeds, science gates, runners, compiler/evaluator behavior, resource policy,
  and all four runtime identities are unchanged. `one_look_opened` remains
  false; no preflight request, campaign state, or scientific product exists.

**Decision:** the corrected approval is sufficient for the complete no-write
preflight from the immutable authorization commit. Campaign state may be
created only if that exact preflight passes without an identity change.

**Validation:** the authorization assertion failed first for the intended
pending-decision reason, then all seven focused recovery tests pass. `just
coverage` passes 1,415 tests with four expected failures at 94.34% branch-aware
coverage; `just check` passes 1,285 quick tests with four expected failures,
and the strict documentation build and final pre-commit suite pass. Review
against `CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** commit the narrow authorization transition, create its
immutable checkout, run the complete no-write preflight, and launch the one
terminal campaign only on success.

## 2026-08-22 — Pause recovery launch at the omitted storage gate

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Created detached immutable checkout `fa3134bd383f...` and ran the approved
  preflight-only launcher against the exact four frozen images. Program,
  runtime, population, and request verification passed with request SHA-256
  `4c53dc39a7f02673a7c316cb814d8947f161eb417f192b077c1aa8b241093230`,
  2,488 images, and 12,440 planned runs.
- The recovery launcher inherited an identity-only preflight and omitted the
  governed 126 GiB host-storage floor. Immediately after launch, the external
  operational audit found only 28 GiB free. The managed process was interrupted
  before exhaustion after 3 materialized inputs and 0 results; the terminal
  public manifest is absent. Restartable staging is
  `benchmark-results/phase-5/.external-recovery-comparison.phase5-external-7a44ba52eb3e.staging`
  and occupies about 199 MiB.
- Read-only storage review found 42 GiB of inputs and 55 GiB of reference
  results under the completed development-only
  `viewed-reference-reconstruction`. Its cumulative ledger `a45303df...`, power
  review `bbfab3a0...`, and small recovery/request/progress records are already
  preserved. Podman reports 13.34 GB of images and 4.67 GB of volumes as
  reclaimable, but the exact four campaign images must not be pruned.

**Decision:** keep the same authorized request and staging namespace; do not
start a second campaign. Resume with `--resume` only after a fresh read-only
audit observes at least 126 GiB host headroom. Deleting the reconstructed
reference `inputs/` and `results/` is the largest scientifically safe cleanup
provided its four small provenance records and compiled ledger/power evidence
are retained, but permanent deletion requires explicit approval.

**Immediate next step:** obtain cleanup approval or user-provided storage,
verify the 126 GiB floor, then resume the same immutable campaign and monitor
only operational state until it seals.

## 2026-08-22 — Remove viewed-reconstruction raw evidence

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Gemma Danks explicitly approved permanent deletion of the completed
  development-only viewed reconstruction's `inputs/` and `results/` trees.
  Both trees are absent after deletion. `recovery.json`,
  `recovery-request.json`, `recovery-open-state.json`, and `progress.log`
  remain intact; the compiled cumulative ledger and power evidence remain in
  their separate Phase 5 paths.
- Host free space increased from 28 GiB to 67 GiB. The 42-GiB input and 55-GiB
  result directory sizes included APFS-shared blocks, so deleting them did not
  release their summed apparent allocation. No large deleted file remains held
  open. The complete remaining Phase 5 tree is about 400 MiB and the preserved
  recovery staging tree remains about 199 MiB with 3 inputs and 0 results.
- The principal remaining allocations observed read-only are the 100-GiB
  Podman machine disk, which contains the exact frozen campaign images, and an
  unrelated 38-GiB `Projects/sdp` tree. Ordinary user caches total about
  11 GiB and are insufficient alone to reach the governed floor.

**Decision:** do not resume below the predeclared 126-GiB floor and do not
install campaign monitoring before a campaign process exists. Preserve the
same immutable checkout, request, and restartable staging namespace.

**Immediate next step:** free at least 59 GiB more without pruning the exact
four runtime images, verify the storage audit, resume the existing request with
`--resume`, and then install hourly operational monitoring.

## 2026-08-22 — Resume the frozen recovery campaign

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Filesystem trimming reduced the physical AppleHV Podman disk allocation from
  about 98 GiB to 31 GiB without deleting or rebuilding any runtime image.
  Host free space reached 134 GiB and passed the predeclared 126-GiB floor.
- Reverified immutable checkout `fa3134bd383f...`, absent terminal manifest,
  and the exact image IDs and repo digests for Hebog, released PyBDSF, pinned
  PyBDSF master, and Aegean. No duplicate recovery campaign process existed.
- Resumed approved preflight request `4c53dc39...` with `--resume` in the same
  private `7a44ba52...` staging namespace. Managed session 83019 was active at
  the initial check, with 10 aggregate inputs, zero results, 134 GiB host
  headroom, and no public terminal campaign manifest.
- Installed hourly heartbeat `monitor-phase-5-recovery-campaign`. While the
  campaign is open it may inspect only process health, aggregate counts,
  progress output, disk headroom, and terminal-manifest presence; it may not
  inspect or compile partial science.

**Decision:** the exact authorized one-look campaign is open. Preserve the
write-once namespace and frozen identities; do not start a duplicate process or
evaluate before the terminal campaign seals.

**Immediate next step:** monitor operationally each hour. On successful seal,
verify the frozen protocol, compile and evaluate exactly once, interpret science
before runtime, update durable records, validate, review, and commit locally.

## 2026-08-22 — Stop recovery execution at runner import failure

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Managed session 83019 verified all 2,488 common inputs, then failed during
  the first Hebog candidate invocation. The write-once infrastructure log
  records `ModuleNotFoundError` for
  `hebog.validation.post_correction_recovery`; the terminal public manifest is
  absent. Aggregate operational state is 2,488 inputs and one completed
  reference result. No partial scientific product was opened or interpreted.
- The failure is an execution-composition defect, not a scientific result. The
  prospective recovery runner imports the approved module from the mounted
  source tree, but the shared container command sets
  `PYTHONPATH=/repository/src` only for non-Hebog finders. The frozen Hebog
  image predates that prospective module, so Python searched the installed
  image package and failed before candidate execution.
- Host storage remained healthy at 105 GiB after complete input materialization
  and the Podman raw disk remained 31 GiB. Storage and runtime-image identity
  were not the cause.

**Decision:** preserve the failed staging namespace and its infrastructure log;
do not overwrite, compile, score, or resume it. A minimal recovery-only runner
environment correction changes the frozen execution composition and therefore
requires regression coverage, a new immutable identity chain, and renewed
named one-look approval before any corrected execution.

**Immediate next step:** add a failing command-level test that requires the
recovery Hebog runner to import the approved mounted source while leaving the
base campaign unchanged, implement the narrow composition fix, validate and
review it, then present fresh identities for approval. Do not tune science.

## 2026-08-23 — Repair the existing recovery campaign source path

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- The requested recovery is explicitly limited to the already-open campaign;
  no second campaign, request, population, input set, or staging namespace may
  be created. The existing 2,488 common inputs and one completed reference
  result remain immutable and unopened.
- Added a host-side Podman delegate that inserts exactly
  `--env PYTHONPATH=/repository/src` only when the exact frozen Hebog image
  invokes `run_phase5_external_recovery_hebog.py`. It delegates image
  inspection, materialization, all references, other images, and other commands
  unchanged, and rejects an ambiguous duplicate source environment.
- The command-level regression test first failed because the delegate did not
  exist, then passed. The focused recovery and unchanged base-launcher suites
  pass 20 tests; focused Ruff and Pyright are clean. A network-isolated,
  read-only smoke invocation in the exact frozen image resolves
  `post_correction_recovery.py` from the immutable `fa3134b...` checkout and
  does not execute a finder or inspect science.

**Decision:** treat the correction as a checksum-bound operational amendment
to the existing request. It restores access to the already approved source tree
and changes no scientific code, configuration, image, input, result, resource
policy, or gate. Preserve the failed infrastructure log and require exact named
approval of the amendment before resuming the missing runs.

**Immediate next step:** validate and commit the delegate, write a pending
amendment review bound to its commit/checksum, request exact approval, then
resume and evaluate only the existing campaign.

## 2026-08-23 — Bind the existing-campaign resume amendment

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Froze pending review
  `config/contracts/phase-5-external-recovery-resume-review.json`, SHA-256
  `a8d30ee956567af0688d8d66cff9058ba57bad8b7be66cee39c5049a88cbc95a`.
  It binds delegate commit `c88e7c25...`, tree `87e4347e...`, delegate SHA
  `36a420a1...`, existing request `4c53dc39...`, open state `f322a07c...`,
  failure log `91e3db30...`, all four runtime identities, the approved candidate
  source/configuration, and the exact private and terminal paths.
- Operational facts remain 2,488 inputs, one unopened reference result, zero
  Hebog results, and no terminal manifest. The complete inputs occupy an
  apparent 44 GiB; 104 GiB host space remains against the conservative adjusted
  82-GiB continuation floor derived from the original 126-GiB preflight floor.
- The review records Gemma Danks's instruction to repair and evaluate this
  existing campaign without creating another, but remains
  `execution_authorized=false` with no named exact-review approval. Its tests
  require the fixed request, unchanged science flags, and delegate checksum.

**Decision:** the operational repair is ready for exact review. Approval must
name review SHA `a8d30ee9...`; only then may the existing request resume through
the checksum-bound delegate. No completed result may be overwritten and no
partial product may be inspected.

**Immediate next step:** obtain exact named approval of `a8d30ee9...`, transition
only the amendment authorization, run a no-write identity/storage preflight,
then resume and monitor the existing campaign through evaluation.

## 2026-08-23 — Authorize only the existing recovery campaign resume

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Gemma Danks approved pending resume review `a8d30ee9...` and delegate commit
  `c88e7c25...`, authorizing only existing request `4c53dc39...` to resume and
  be evaluated after sealing. The approval explicitly forbids a second
  campaign.
- Recorded immutable authorization decision
  `config/contracts/phase-5-external-recovery-resume-decision.json`, SHA-256
  `de2aec16a3fc5943b434a9a7fb3fc2c9c12d871f9e3eed5f6fd161595043c70d`.
  It binds the approved review, delegate checksum, original execution decision,
  preserved staging/terminal paths, and 12,439 missing runs; science changes
  remain unauthorized.
- Two focused review/decision tests pass and verify the review and delegate
  checksums, exact request, remaining-run count, and no-second-campaign bound.

**Decision:** the amendment is authorized but execution has not yet resumed.
The next command must be a no-write preflight against the preserved campaign;
any request, identity, or state drift closes the authorization.

**Immediate next step:** validate and commit this authorization transition,
then run the exact no-write preflight and resume only the existing staging
namespace if it passes unchanged.

## 2026-08-23 — Resume only the existing recovery request

**Plan phase:** Phase 5, Step 2C-PC recovery execution

- Committed the named authorization transition as `b5810cb...`; its immutable
  checkout preserves decision SHA `de2aec16...`, approved review
  `a8d30ee9...`, and delegate SHA `36a420a1...`.
- After launch, the mandatory JSON hook sorted one decision key in the active
  branch copy, producing SHA `cd6a6652...` without changing any value. The
  executed identity remains immutable checkout `b5810cb...` / decision
  `de2aec16...`; the hook-only normalization is not a new authorization.
- The read-only state audit reverified original execution commit `fa3134b...`,
  request `4c53dc39...`, open state `f322a07c...`, failure log `91e3db30...`,
  all four exact image IDs/digests, 2,488 inputs, one unopened reference result,
  zero Hebog results, absent failed output directory, and absent terminal
  manifest. Host headroom was 104 GiB; the Podman guest had 68 GiB free.
- The complete no-write launcher preflight passed with the unchanged request,
  2,488-image population, and 12,440-run design. Managed session 51323 then
  resumed the preserved private staging namespace with `--resume` and the
  checksum-bound delegate; no new request or campaign was created.
- Installed hourly automation
  `monitor-phase-5-existing-recovery-campaign`. While open it may inspect only
  operational health/counts/progress/disk/terminal presence. Compilation and
  evaluation remain prohibited until terminal sealing.

**Decision:** the authorized existing-campaign recovery is active. Preserve
the immutable execution and amendment checkouts and do not start another
campaign.

**Immediate next step:** monitor hourly. When the terminal manifest seals,
verify it, compile and evaluate exactly once, interpret science before runtime,
then update, validate, review, and commit the terminal decision.

## 2026-08-24 — Stop at the frozen recovery evaluator identity defect

**Plan phase:** Phase 5, Step 2C-PC recovery evaluation

- The resumed existing campaign exited successfully after re-verifying all
  2,488 inputs and 12,440 runs. It atomically published campaign SHA-256
  `4d881a412980e5dfa58d57e18c1e1ca706606724fa745605df554d9302627c83`.
- The frozen compiler verified the complete campaign before reading science
  and atomically published analysis SHA-256
  `198fe6ff63ade465872976e6897bf69e7e70f415fd04889937367410c5e3d53a`.
- The frozen evaluator then stopped before scoring or writing a decision with
  `post-failure compiled analysis identity changed`. The analysis correctly
  records inherited base accelerator `bb3c5c2f...`, while the merged recovery
  contract supplies recovery-seam identity `ab690dda...` to an inherited check
  that expects the base identity. Every other member of that fail-closed check
  matches; `external-recovery-decision.json` remains absent.
- Added a separate prospective evaluator amendment rather than modifying the
  frozen evaluator or contract. It validates named authorization, the existing
  analysis, frozen evaluator/contract, and amendment review; preserves the
  recovery-seam identity for provenance; substitutes only the verified base
  accelerator identity at the inherited compatibility boundary; and refuses
  campaign re-execution, analysis recompilation, science changes, or output
  overwrite.
- The focused adapter regression first failed because the amendment did not
  exist, then passed. Authorization normal/failure tests and the complete
  12-test recovery protocol suite pass; focused Ruff and Pyright are clean.
- `just coverage` passes 1,420 tests with 44 deselected, four expected failures,
  and 94.34% branch-aware project coverage. `just check` passes 1,290 tests
  with 174 deselected and four expected failures; the strict documentation
  build also passes.

**Decision:** this is an evaluation-composition defect, not a scientific
failure. Preserve campaign `4d881a41...`, analysis `198fe6ff...`, the failed
evaluator invocation, and the absent decision. Do not rerun the campaign,
compiler, frozen evaluator, or score through the amendment without renewed
exact approval.

**Immediate next step:** complete coverage and repository validation, commit
the amendment, then freeze a pending review bound to its commit/checksum and
the existing analysis for named approval.

## 2026-08-24 — Freeze the recovery evaluator amendment review

**Plan phase:** Phase 5, Step 2C-PC recovery evaluation

- Committed the fail-closed evaluation adapter as `147e193...`, tree
  `b98f9d97...`, evaluator SHA `406c36a0...`. The frozen evaluator remains
  byte-identical at `fc17d820...` and its frozen contract remains
  `9ef1a4f6...`.
- Created pending review
  `config/contracts/phase-5-external-recovery-evaluation-amendment-review.json`,
  SHA-256
  `0b6a98d95d8bb696c2f2597bdf0b42cccf81ec430936b37b54c8e6ce0e86e551`.
  It binds campaign `4d881a41...`, analysis `198fe6ff...`, the absent decision,
  both accelerator identities, and the exact adapter implementation. It
  records `execution_authorized=false` with no named review.

**Decision:** the existing analysis is technically ready for an evaluation-only
identity amendment, but remains unopened by a successful scorer. No campaign,
compiler, analysis, endpoint, gate, or science value changes are authorized.

**Immediate next step:** obtain exact named approval of pending review
`0b6a98d9...`. Only then create the separate authorization decision and invoke
the amendment once against existing analysis `198fe6ff...`.

## 2026-08-24 — Authorize the recovery evaluator amendment

**Plan phase:** Phase 5, Step 2C-PC recovery evaluation

- Gemma Danks approved the exact pending evaluator-amendment review
  `0b6a98d95d8bb696c2f2597bdf0b42cccf81ec430936b37b54c8e6ce0e86e551`
  and requested completion of the evaluation.
- Authorization decision SHA-256
  `5103aedcd2678edc9ff6efd8b9865426db5a320e0bf65e8cab49a7586b81220c`
  binds adapter commit `147e193...`, adapter SHA `406c36a0...`, existing
  analysis `198fe6ff...`, frozen evaluator `fc17d820...`, and frozen contract
  `9ef1a4f6...`.
- The decision authorizes exactly one evaluation of the existing analysis. It
  explicitly forbids campaign re-execution, analysis recompilation, and any
  science or gate change.

**Decision:** the evaluation-only amendment is now exactly authorized. The
campaign and compiled analysis remain immutable and no second campaign is
permitted.

**Immediate next step:** commit the authorization boundary, invoke the amended
evaluator once, and interpret scientific outcomes before runtime.

## 2026-08-24 — Pass the Phase 5 recovery science gate

**Plan phase:** Phase 5, Step 2C-PC recovery evaluation

- From clean authorization commit `fb63e51...`, invoked the approved amendment
  exactly once against existing analysis `198fe6ff...`. It wrote terminal
  decision SHA-256
  `cd3eacfbbc236ca1578712fed0e4a28d38cd26d7703882258af5ff44d22e6425`;
  amendment provenance records authorization `5103aedc...`, review
  `0b6a98d9...`, and adapter `406c36a0...`.
- The terminal campaign decision is `pass`: all 144 expected binding endpoints
  passed, comprising the compact decision and 143 Continuum endpoints.
- Continuum passed all 143 absolute gates and all 226 powered paired
  comparisons, split evenly as 113 against released PyBDSF and 113 against
  pinned PyBDSF master. The narrowest absolute clearance is overall mask recall
  0.9010345 against 0.90. The narrowest paired clearance is overall mask
  precision against pinned master: upper confidence limit 0.0494025 against
  the 0.05 practical-regression margin.
- Compact passed all 77 binding absolute gates, all 450 paired PyBDSF
  comparisons, and all 143 applicable Aegean binding comparisons. The six
  earlier Aegean integrated-flux failures are resolved under the corrected
  fitted-component composition. Five compact truth-absolute diagnostics still
  miss stronger report-only envelopes for median position, median/p95 peak
  flux, p95 integrated flux, and p95 fitted axis; none is a binding failure.
- The frozen recovery decision contains no runtime-performance gate. Science
  was interpreted first and passed; no raw timing is promoted into a speed
  claim. Phase 5 incremental performance remains in Step 6 and complete
  Rapthor dual-PyBDSF performance remains Phase 7.

**Decision:** Step 2C-PC passes and Step 3 may open. The campaign and analysis
remain write-once, closed-campaign reuse is unauthorized, and this result does
not close Phase 5, remove the PyBDSF fallback, or authorize production cutover.

**Immediate next step:** begin Step 3 with residual-scale detection and frozen
scale-specific scientific rules while preserving the compact regression gate
and the two narrow Continuum watchpoints.

## 2026-08-24 — Refresh release documentation after Phase 4 closure

**Plan phase:** Phase 4 release documentation

- Updated the README and documentation homepage to identify Phase 4U as the
  passing compact single-scale qualification, distinguish the immutable failed
  campaigns from the current milestone decision, and summarize the passing
  optimized replay and component-performance evidence.
- Added the current Phase 5 recovery science result without presenting Phase 5
  as complete or making a runtime claim. The public `find_sources` boundary,
  real-residual review, Rapthor integration, end-to-end performance, and
  production-scale qualification remain explicit limitations.
- Corrected the Phase 4R paired-protocol and Phase 4T confirmation status text
  from pre-opening language to their terminal failed dispositions, removed
  duplicated protocol text, and completed the Phase 4 reference navigation.
- Updated the native-code assessment to reflect the implemented and qualified
  compact kernels, the internal-schema reference to reflect completed Phase 0
  sign-off, and the quick start to describe the actual remaining public-pipeline
  boundary.
- `just docs-build` passes strictly and `just check` passes Ruff, Pyright, and
  1,292 unit/doctest cases with four expected failures. Release Please remains
  responsible for the version and release notes; no release-managed version
  file was changed.

**Decision:** the release-facing documentation now describes Phase 4 as
complete while retaining the narrower pre-production claim and current Phase 5
boundary.

**Immediate next step:** complete final documentation review and pre-commit,
then merge for the Release Please-managed release.

## 2026-08-24 — Complete Step 3 residual-scale detection

**Plan phase:** Phase 5, Step 3 — multiscale science

- Promoted the reviewed three-scale residual B3-spline à trous kernel from
  candidate evidence into the first production Step 3 contract. The bounded
  serial result now exposes an immutable significance mask for every scale,
  calibrated by that scale's effective local RMS and scientific validity.
- Froze canonical consecutive scale order and finite 5/3-sigma-compatible
  threshold validation before adjacent-scale persistence. The reconstruction
  still rejects isolated single-scale peaks, retains accepted coefficient
  signal only within persistent support, and does not add a durable response
  plane store.
- Added analytic red-to-green coverage for varying local RMS, invalid pixels,
  per-scale provenance, immutable masks, non-finite thresholds, non-adjacent
  scale records, and the existing positive adjacent-scale reconstruction.
- Updated the filter-selection reference to record the passing Step 2C-PC
  recovery promotion and distinguish it from the untouched final
  qualification.
- The first production edit after the closed campaign exposed four historical
  tests that implicitly required the live tree to remain the archived
  candidate forever. Their positive cases now inject the exact archived hash;
  the frozen scripts and identities are unchanged, and a deterministic test
  confirms source drift still fails closed.
- Focused multiscale and candidate-composition validation passes 70 tests;
  focused recovery-protocol validation passes 19. `just coverage` passes
  1,424 tests with four expected failures at 94.34% project coverage.
  `just check` passes Ruff, Pyright, 1,294 tests, and four expected failures;
  `just docs-build` passes strictly.

**Decision:** the first Step 3 item is complete. This does not complete Phase
5, open qualification, make a runtime claim, or alter the recovery campaign's
scientific result.

**Immediate next step:** freeze the production scale-specific connectivity,
persistence, seed/grow, normalized-support, minimum-area, edge, and
invalid-pixel policy with analytic tests, reusing the promoted science without
weakening the compact regression gate or the two narrow Continuum watchpoints.

## 2026-08-24 — Freeze production multiscale segmentation rules

**Plan phase:** Phase 5, Step 3 — multiscale science

- Added `ResidualMultiscaleDetectionConfig` as the explicit production
  boundary for thresholds, normalized scale support, beam-area filtering, and
  the fixed topology modes promoted by the recovery campaign. It rejects
  unreviewed connectivity, persistence, growth, edge, invalid-pixel, and
  subarea-island semantics.
- Added a scheduler-independent residual-island kernel that combines calibrated
  matched-filter seed aid, persistent adjacent-scale B3 evidence, and direct
  residual SNR; grows only eight-connected original valid 3-sigma pixels; and
  applies the one-Gaussian-beam floor with a direct 5-sigma seed exception.
- Made normalized support explicit in adjacent-scale reconstruction. Exact
  half-support edge evidence is usable, support immediately below the boundary
  is unavailable, and non-finite or invalid pixels cannot seed, grow, bridge,
  or enter a component.
- Routed the promoted corrective-R/A validation path through the production
  kernel without changing its separate three-beam association behavior. The
  historical pre-correction and matched-comparator paths remain unchanged;
  deterministic development smoke tests retain complete detection,
  reliability, fragmentation, mask, and analytic-endpoint passage.
- Added analytic red-to-green tests for diagonal eight-connectivity,
  original-residual growth, persistent scale seeds, area and direct-seed
  disposition, exact edge-support inclusivity, invalid pixels, configuration
  drift, mismatched tile planes, immutable outputs, and filter-family
  provenance. Updated the scientific reference and API navigation with the
  production policy and its Step 4 association boundary.
- Focused multiscale and corrective validation passes 87 tests. `just coverage`
  passes 1,441 tests with four expected failures at 94.40% project coverage;
  the changed multiscale and configuration modules reach 98% and 99%.
  `just check` passes Ruff, Pyright, 1,311 tests, and four expected failures;
  `just docs-build` passes strictly.

**Decision:** the second Step 3 item is complete without changing the passing
recovery evidence, opening qualification, or making a runtime claim.

**Immediate next step:** implement bounded partitioned completion for
compact-deferred islands so no task owns an arbitrarily large island, while
preserving the frozen segmentation policy and compact regression products.

## 2026-08-24 — Complete compact deferrals with bounded membership shards

**Plan phase:** Phase 5, Step 3 — multiscale science

- Added `DeferredIslandCompletionConfig` with an explicit hard per-task pixel
  limit and a scheduler-independent partitioning boundary for every
  `DeferredDeblendIsland` produced by the compact planner.
- The completion stage relabels the immutable published
  source-filtering-mask in caller-supplied zero-halo cores. Each task owns one
  bounded tile; only local summaries and boundary labels return for the
  existing deterministic reconciliation, so no complete deferred island or
  image-sized label plane crosses the executor boundary.
- Added canonical array-free `DeferredIslandShard` and
  `PartitionedDeferredIsland` records. Their count, bounds, first pixel,
  parent identity, local labels, order, and hard tile admission fail closed.
  Exact immutable membership can be reconstructed and verified from one shard
  plus one bounded mask tile for the following original-pixel measurement
  stage.
- Analytic tests cover multiple rectangular grids, shifted partition origins,
  disconnected components sharing a tile, result-order invariance, exact
  reconstruction, malformed records, incomplete reconciliation, and hard
  bounds. Integration tests cover compact-planner handoff, deterministic
  retry, independently partitioned reads, zero-work behavior, generation and
  manifest failures, and Serial/Dask equivalence.
- The complete affected compact/deferred suite passes 78 tests. `just coverage`
  passes 1,452 tests with four expected failures at 94.43% project
  coverage; the changed deblending algorithm and stage reach 97% and 95%.
  `just check` passes Ruff, Pyright, 1,321 tests, and four expected failures;
  `just docs-build` passes strictly.

**Decision:** the third Step 3 item is complete. This closes the unbounded
compact-deferral handoff but does not perform a global watershed, extended
photometry, cross-scale association, or catalogue publication.

**Immediate next step:** measure deferred and multiscale extended emission
from original background-subtracted pixels through the bounded shards, with
explicit flux, position, shape, uncertainty-availability, and truncation
semantics while preserving unaffected Phase 4 compact products.

## 2026-08-24 — Measure extended emission through bounded original-pixel tasks

**Plan phase:** Phase 5, Step 3 — multiscale science

- Added immutable pre-association records for extended targets, physical
  geometry, aperture photometry, moment shape, truncation, uncertainty
  availability, and typed whole-measurement failure. Invalid identifiers,
  geometry, counts, covariance, positions, and availability combinations fail
  closed.
- Implemented a pure tile reducer and canonical scalar combiner. Integrated
  flux uses original background-subtracted pixels in the promoted
  1.5-major-beam nearest-owned aperture; peak brightness and moment shape use
  exact original-pixel support; prepared background and RMS are reused; and
  flux error uses the correlated-beam approximation. Edge and invalid-pixel
  truncation remain distinct and observable.
- Preserved the successful recovery estimator rather than substituting a new
  position policy. Multiscale targets can supply the regularized direct-plus-B3
  position plane, with the reviewed peak-to-mean compact safeguard and direct
  fallback. Compact-deferred targets explicitly record direct-original
  weighting until multiscale association supplies regularized evidence.
- Added a bounded scheduler-independent stage over canonical deferred-island
  shards. Each task reads one core plus the required aperture halo, treats all
  other accepted compact support as an ownership barrier, enforces a hard
  complete-window pixel ceiling, and returns only array-free scalar evidence.
  Equivalent rectangular/shifted grids, retry, and Serial/Dask execution are
  invariant; the published detection generation and accepted mask remain
  unchanged.
- Added analytic and integration coverage for original-pixel values,
  nearest-owned apertures, regularized/direct position selection, correlated
  uncertainty, isotropic and singular shapes, typed unavailability,
  truncation, malformed evidence, compact barriers, hard admission,
  generation/manifest/shard failures, and executor/partition invariance. The
  complete affected suite passes 146 tests. `just coverage` passes 1,467 tests
  with four expected failures at 94.48%, above the previous 94.43% project
  baseline; the new measurement records reach 100% and the extended kernel
  reaches 96%. `just check` passes Ruff, Pyright, 1,334 tests, and four
  expected failures; `just docs-build` passes strictly.

**Decision:** the fourth Step 3 item is complete. These records are not a
combined source catalogue: Step 4 still owns cross-scale duplicate suppression
and compact/extended association, and final Phase 5 qualification remains
closed.

**Immediate next step:** prove and retain exact Phase 4 compact products when
multiscale evidence does not change association, then define the Step 4
compact/extended ownership and duplicate-suppression rules before implementing
combined catalogue publication.

## 2026-08-24 — Preserve non-associated Phase 4 compact products exactly

**Plan phase:** Phase 5, Step 3 — multiscale science

- Added a narrow fail-closed preservation boundary between pre-association
  multiscale evidence and the completed compact catalogue. Only
  `extended-only` relationships with no compact source identities are
  non-altering; the function returns the original `CompletedCompactCatalogue`
  object rather than reconstructing any Phase 4 record.
- A compact source identity, `contains-compact` relationship, or ambiguous
  `mixed-projection` relationship raises
  `CompactAssociationDecisionRequiredError`. This prevents Step 3 from
  silently making the ownership, split/merge, or duplicate-suppression choice
  reserved for Step 4.
- TDD first recorded the absent boundary. Focused unit coverage now proves
  exact object, catalogue, canonical-JSON, reduction-evidence, empty-catalogue,
  and fail-closed behavior. Integration coverage proves that the preserved
  catalogue produces byte-identical Rapthor FITS products.

**Decision:** Phase 5 Step 3 is complete. Its multiscale algorithms can detect,
complete, and measure extended evidence without changing an unaffected Phase 4
compact result. This is not a combined-catalogue decision and does not
authorize Step 4 publication or qualification.

**Immediate next step:** pre-review and freeze deterministic Step 4
compact/extended overlap, ownership, split/merge, and duplicate-suppression
rules before implementing combined catalogue construction.

## 2026-08-24 — Complete the Step 4 association technical pre-review

**Plan phase:** Phase 5, Step 4 — reconcile scales and construct products

- Reviewed the existing recovery evidence, accepted-compact exclusion,
  nearest-support measurement ownership, provisional multiscale schemas, and
  external duplicate/split/merge semantics before proposing catalogue rules.
- Compared the design with primary PyBDSF, Aegean, CAESAR, and ProFound
  sources. The recommended shared-island/separate-source hierarchy follows
  familiar overlap reconciliation while avoiding an unsupported physical host
  inference from one Stokes-I image.
- Proposed exact adjacent-scale support edges, graph-component fragment
  reconciliation, representative ordering, half-beam compact context,
  many-to-many spatial context, compact barriers, one extended row per
  association, compact-echo suppression, fail-closed ambiguity, and terminal
  disposition rules. No qualification result or new threshold was inspected.
- Recorded the required analytic, topology, failure, compact-preservation, and
  executor-invariance tests. No production schema, machine-readable contract,
  scientific output, or publication path changed in this pre-review.

**Decision:** technical pre-review is complete and recommends approval. The
first Step 4 checklist item remains open until the proposed policy receives
named approval; implementation and qualification remain closed.

**Immediate next step:** obtain named approval of the Phase 5 association
pre-review, then update the machine-readable contract and begin test-first
cross-scale association implementation.

## 2026-08-24 — Freeze and implement cross-scale association

**Plan phase:** Phase 5, Step 4 — reconcile scales and construct products

- Received named approval of the compact/extended association pre-review and
  froze its rules in `phase-5-multiscale.json` schema 2. The contract now names
  exact adjacent-scale overlap, same-scale merging only through an adjacent
  path, shared-island/separate-source compact context, compact-first ownership,
  one extended row per association, compact-echo suppression, and fail-closed
  ambiguity.
- Replaced the provisional physical-sounding relationship values with the
  explicit spatial vocabulary `extended-only`, `contains-compact-support`, and
  `overlaps-compact-support`. Non-extended relationships require compact
  identities, while `extended-only` forbids them.
- Added a bounded scheduler-independent association kernel over immutable
  per-scale exact-support label planes. It validates global bounds, origins,
  support counts, canonical pixels, scale membership, shapes, and unique
  detection identities before creating vectorized adjacent-scale overlap
  edges.
- Stable association IDs derive from canonical contributing detection IDs;
  representative ordering follows SNR, calibrated response, support fraction,
  scale, pixel, and detection ID. Same-scale fragments remain distinct unless
  connected through accepted adjacent-scale support.
- Confirmed the required red state before implementation: the new analytic
  test module failed collection because the association module did not exist.
  After implementation, 225 focused association, schema, preservation, and
  contract tests plus 11 Rapthor-catalogue integration tests pass; the new
  kernel has 100% line and branch coverage, and focused Ruff and Pyright pass.
- The final branch-aware project coverage run passes with 1,500 tests, 44
  deselected, four expected failures, and 94.62% total coverage; the new
  association module remains at 100% line and branch coverage.
- The final fast handoff suite passes Ruff formatting and linting, Pyright,
  doctests, and 1,369 tests with 178 deselected and four expected failures;
  the strict documentation build also passes.

**Decision:** the first Step 4 checklist item is complete. The kernel publishes
only `extended-only` associations, so this increment cannot alter compact
objects or claim a combined catalogue.

**Immediate next step:** implement the approved many-to-many compact-context
graph while preserving separate compact and extended source identities.

## 2026-08-24 — Implement compact/extended spatial context

**Plan phase:** Phase 5, Step 4 — reconcile scales and construct products

- Added strict scheduler-safe compact-support and per-edge context records.
  The bounded input plane validates exact source counts, bounds, parent Phase
  4 island identities, image-plane reference positions, and immutable label
  storage before association.
- Implemented the approved many-to-many context graph over reconciled extended
  supports. A compact edge requires reference containment, exact overlap, or
  the frozen half-major-beam dilation. Containment is retained per edge; an
  association with mixed edge types uses the conservative aggregate overlap
  relationship without discarding exact edge evidence.
- Preserved every compact source ID and every extended association ID.
  Multiple compact components may share one extended association, and one
  compact source may contextualize several distinct extended associations,
  without merging or suppressing either side. Context dilation never grows
  scientific support or changes compact-first pixel ownership.
- Added fail-closed checks for missing, duplicated, pre-contextualized, or
  scale-inconsistent associations; misaligned compact support; and conflicting
  exact ownership between extended associations. Stable IDs order equivalent
  evidence but never resolve a scientific contradiction.
- The final review replaced a provisional full boolean mask per detection with
  one integer association-owner plane plus one transient association support.
  Memory therefore remains proportional to bounded tile area rather than
  detection count multiplied by tile area.
- Confirmed the TDD red state before implementation: the analytic test module
  failed collection because the compact-context API did not exist. The final
  focused association and schema suite passes 144 tests with 100% line and
  branch coverage in both changed production modules; the complete affected
  unit set passes 167 tests, and focused Ruff and Pyright also pass. The final
  branch-aware project run passes 1,539 tests with 44 deselected and four
  expected failures at 94.69% total coverage. The fast handoff suite passes
  Ruff, Pyright, doctests, and 1,405 tests with 178 deselected and four
  expected failures; the strict documentation build also passes.

**Decision:** the second Step 4 checklist item is complete. This increment
provides spatial grouping evidence only; it makes no physical-host claim and
does not yet construct combined islands or catalogue rows.

**Immediate next step:** derive stable combined island, source, and
compatibility-component identities from the canonical compact-context graph,
independent of tile and task order.

## 2026-08-24 — Derive stable combined catalogue identities

**Plan phase:** Phase 5, Step 4 — reconcile scales and construct products

- Added strict array-free records for combined island membership and extended
  source identities. Compact source support now carries the canonical Phase 4
  Gaussian IDs needed to preserve component identity through composition;
  callers must supply that provenance explicitly rather than receiving an
  empty default.
- Advanced the strict Phase 5 development contract to schema 3 so the
  compact-only island preservation, mixed/extended island hash inputs,
  context-independent extended source identity, and zero-extended-Gaussian
  policy cannot drift during the remaining construction tasks.
- Implemented deterministic connected-component derivation over Phase 4 island
  nodes and extended-association nodes. Compact-only islands retain their exact
  Phase 4 ID; mixed and extended islands hash canonical compact-island and
  association membership, independently of input, tile, task, or completion
  order.
- Preserved every compact source and Gaussian ID and derived one stable source
  ID per extended association independently of spatial context. Irregular
  extended sources deliberately have zero Gaussian compatibility components;
  the Rapthor view consumes source rows and does not require a fabricated fit.
- Fail-closed validation rejects duplicate compact, Gaussian, association, or
  edge identities; unknown references; missing edges; and contradictory
  association summaries before any identity is derived.
- Confirmed the TDD red state before implementation: the new analytic module
  failed collection because the combined-identity module did not exist. The
  final focused suite passes 25 tests, with 100% line and branch coverage in
  the identity module. The complete affected schema, contract, association,
  context, and Rapthor adapter suite passes 278 tests.
- The branch-aware project run passes 1,565 tests with 44 deselected and four
  expected failures at 94.75% total coverage; the identity and multiscale
  data-model modules are both at 100%, and strict loader tests exercise the
  declarative contract change. The fast handoff suite passes Ruff, Pyright,
  doctests, and 1,431 tests with 178 deselected and four expected failures. The
  strict documentation build also passes.

**Decision:** the third Step 4 checklist item is complete. Identity derivation
does not construct catalogue rows, publish products, or authorize
qualification.

**Immediate next step:** merge bounded combined shards hierarchically and
allow publication only after every accepted or deferred island has exactly one
terminal disposition.

## 2026-08-24 — Gate combined catalogue completion on terminal state

**Plan phase:** Phase 5, Step 4 — reconcile scales and construct products

- Advanced `CombinedCatalogueState` to schema 2 with explicit disjoint,
  canonical accepted- and deferred-island populations. Missing dispositions
  are now observable in an inspectable incomplete state and make publication
  ineligible alongside omissions and failed dispositions.
- Added strict scheduler-safe combined-catalogue shards, pairwise reduction
  evidence, and a completed-state wrapper. The canonical fan-in-two reducer is
  invariant to shard and completion order, records its depth and maximum input
  shard size, and supports a scientifically empty image without inventing an
  object.
- Added a fail-closed completion boundary with an explicit positive cap over
  every final in-memory state record. Duplicate or conflicting ownership,
  duplicate or unknown terminal evidence, missing dispositions, omissions,
  failed outcomes, and cap overflow all stop before product publication.
- Confirmed the TDD red state before implementation: the analytic reducer test
  module failed collection because the combined-catalogue reduction module did
  not exist. The focused reducer suite now passes 16 tests with 100% line and
  branch coverage in the new algorithm module; the complete schema and reducer
  unit set passes 97 tests, with focused Ruff and Pyright also passing. The
  branch-aware project run passes 1,581 tests with 44 deselected and four
  expected failures at 94.77% total coverage; a direct completed-wrapper test
  covers its fail-closed validator. The fast handoff suite passes Ruff,
  Pyright, doctests, and 1,447 tests with 178 deselected and four expected
  failures. The strict documentation build also passes.

**Decision:** the fourth Step 4 checklist item is complete. The reducer proves
terminal-state completeness only; it does not construct catalogue rows or
publish catalogue, mask, RMS, provenance, diagnostic, or Rapthor products.

**Immediate next step:** materialise those combined products from the completed
state while proving byte-identical compact-only output.

## 2026-08-24 — Materialize final combined source products

**Plan phase:** Phase 5, Step 4 — reconcile scales and construct products

- Confirmed the TDD red state before implementation: the combined-product
  test module failed collection because no construction module existed.
- Added fail-closed catalogue composition over the exact completed terminal
  state, combined identities, associations, measurements, and Phase 4 compact
  catalogue. Compact-only composition returns the same catalogue object;
  mixed composition retains every compact source and Gaussian, adds one
  irregular source per accepted association, and never invents an extended
  Gaussian component.
- Advanced `ExtendedEmissionMeasurement` to schema 3 with original-pixel peak
  brightness. Extended rows use detected-segment centroid, peak and integrated
  flux, local RMS, and a flagged beam-scaled segment-moment major extent. The
  Rapthor `DC_Maj` mapping is documented as a characteristic extent rather
  than a Gaussian deconvolution claim.
- Added canonical per-source scale/support provenance and diagnostics schema
  2. Compact-only results retain diagnostics schema 1 and reproduce its bytes;
  restart reads reject a product record whose declared diagnostics schema does
  not match its canonical JSON payload.
- Added final product composition through the existing atomic writers. It
  reuses the exact Phase 2 RMS product, unions compact and accepted extended
  mask support one bounded row block at a time, and writes the internal
  catalogue, diagnostics, mask, and Rapthor view from one combined catalogue.
  An integration oracle proves byte-identical compact-only catalogue, mask,
  diagnostics, and Rapthor FITS products.
- Advanced the reviewed development contract to schema 4 with the product,
  provenance, RMS-reuse, mask, peak-flux, and compatibility-extent semantics.
  Updated the plan and schema documentation without opening qualification or
  making a runtime claim.
- The final focused scientific, contract, and FITS suite passes 256 tests.
  Focused branch coverage is 95% for combined catalogue construction, 100%
  for final combined I/O, and 99% for source-finding records. The branch-aware
  project run passes 1,603 tests with 44 deselected and four expected failures
  at 94.82% total coverage.

**Decision:** Phase 5 Step 4 is complete. Product construction satisfies the
approved shared-island/separate-source policy and preserves compact-only
outputs exactly; it does not establish executor invariance, final
qualification, incremental performance, or production readiness.

**Immediate next step:** begin Step 5 by deriving and reviewing every
stage-specific halo and rejecting configurations that cannot meet the bounded
memory contract.

## 2026-08-24 — Derive and admit every Phase 5 stage halo

**Plan phase:** Phase 5, Step 5 — bounded deterministic execution

- Confirmed the TDD red state before implementation: the halo-planning test
  module failed collection because the Phase 5 execution planner did not
  exist.
- Added one allocation-free pre-execution plan over the shared deterministic
  tile core. It derives the actual four-sigma matched-filter radii, cumulative
  residual-B3 radii, three-pixel-opening plus half-beam refinement radius,
  half-beam compact-context radius, and reviewed 1.5-beam measurement radius.
  Labelling, cross-scale association, combined reconciliation, and final
  materialization explicitly require zero additional image halo after their
  preceding reconciliation boundaries.
- Reused the exact radius helpers in the scientific kernels and scheduler-
  facing measurement stage, removing independent `ceil` formulas. Matched-
  filter admission does not allocate a Gaussian kernel, so an oversized beam
  or core fails before that potentially large allocation.
- Added fail-closed quarter-core geometry admission and worst-case interior
  read admission against the global task-pixel limit and the tighter extended-
  measurement cap. The Phase 5 profile rejects an aperture other than the
  approved 1.5 beams rather than silently changing recovery-campaign
  photometry.
- Advanced the reviewed development contract to schema 5, SHA-256
  `89b9c1d013af64f5fc99f96a1946bb6416d927232227eeb4a50f2ee1e0259734`,
  and recorded the complete derivation and remaining evidence boundary in the
  reference documentation. No threshold, source relationship, compact output,
  or recovery-campaign result changed.
- The affected scientific, integration, and contract suite passes 228 tests;
  the dedicated planning suite passes 17 tests with 100% line and branch
  coverage for the new module. The complete branch-aware project run passes
  1,621 tests with 44 deselected and four expected failures at 94.84% total
  coverage. The fast handoff suite passes Ruff, Pyright, doctests, and 1,482
  tests with 183 deselected and four expected failures. The strict
  documentation build also passes.

**Decision:** the first Phase 5 Step 5 checklist item is complete. Pixel
admission establishes the pre-allocation memory guard but is not the later
byte-level execution evidence and makes no runtime claim.

**Immediate next step:** prove one-tile/many-tile equality across edges,
corners, rectangular cores, invalid regions, the largest scale, and shifted
partition origins.

## 2026-08-24 — Prove Phase 5 one-tile/many-tile science equality

**Plan phase:** Phase 5, Step 5 — bounded deterministic execution

- Confirmed the TDD red state before implementation: the new equality module
  failed collection because the core-only Phase 5 filter-tile result and
  evaluator did not exist.
- Added a bounded local filtering seam over the exact clipped halo. It runs the
  frozen 1-, 2-, and 4-beam matched-filter bank and three-level residual B3
  transform, then returns owned immutable core copies without retaining the
  halo-read allocation. Incomplete halos, mismatched prepared records, and
  reads that disagree with partition geometry fail before filter workspaces
  are allocated.
- Reused the established Phase 3 side/corner summaries to reconcile adjacent-
  scale reconstruction, original-residual islands, and residual/
  reconstruction segment association. The deterministic small-image oracle
  alone assembles complete planes; that operation remains forbidden in
  production and is not an executor implementation.
- Proved the complete promoted scientific path for one tile versus rectangular
  88-by-96 cores at origins `(0, 0)` and `(43, 47)`. The matrix includes
  sources on both partition corners, top and bottom-right image edges, invalid
  holes, and the four-beam scale. Masks, labels, island topology and integer
  properties are exact; matched/B3 responses, effective RMS, visible support,
  combined SNR, and the position signal agree within `2e-13` FFT round-off.
- The proof exposed a planning omission rather than a science defect: the
  already approved three-beam dilation that groups original-residual and
  reconstructed support was not listed as a separate halo stage. The planner
  now derives its `ceil(3 * beam_major_fwhm_pixels)` halo; no threshold,
  candidate configuration, campaign result, or Step 4 association rule
  changed.
- Advanced the reviewed development contract to schema 6, SHA-256
  `a6d3fd3cf1b89dede72e28c9ea08f9e88673766acc2b2d4715264799c6d46643`,
  freezing core ownership, the missing segment-association halo, the complete
  equality matrix, and the test-only complete-plane boundary.
- The affected scientific, topology, integration, and contract suite passes
  243 tests. The dedicated execution and equality suites pass 22 tests with
  100% line and branch coverage for `phase_five_execution.py`. The complete
  branch-aware project run passes 1,627 tests with 44 deselected and four
  expected failures at 94.86% total coverage. The fast handoff suite passes
  Ruff, Pyright, doctests, and 1,488 tests with 183 deselected and four
  expected failures; the strict documentation build also passes.

**Decision:** the second Phase 5 Step 5 checklist item is complete. This proof
establishes partitioned scientific equality, not scheduling, retry, executor,
memory, graph-size, qualification, or runtime evidence.

**Immediate next step:** prove partition, batch, worker-count, completion-order,
retry, and executor invariance for science and product identities.

## 2026-08-24 — Prove Phase 5 executor and product invariance

**Plan phase:** Phase 5, Step 5 — bounded deterministic execution

- Confirmed the TDD red state before implementation: the new integration
  contract failed collection because no Phase 5 multiscale stage existed.
  During implementation review, rejected an initial response-bank persistence
  draft before commit because 30 image-plane products would contradict the
  frozen no-image-sized-response-bank decision and scale poorly at the
  100,000-square target.
- Added the production two-pass multiscale stage over the existing executor and
  Zarr generation boundaries. Pass one evaluates only bounded halo reads and
  returns compact side/corner summaries for adjacent-scale reconstruction and
  original-residual support. After hierarchical global reconciliation, pass
  two recomputes the bounded filters, applies immutable global label mappings,
  and returns only compact scale summaries, checksummed chunk identities, and
  scalar execution evidence. No scientific plane crosses the executor.
- Published only eight accepted products: combined SNR, reconstructed signal,
  direct-plus-reconstructed position signal, retained residual mask,
  reconstruction mask, and three accepted significant-scale masks. Missing or
  conflicting work remains governed by the existing exact-chunk-set and atomic
  generation contracts; identical writes are retry-idempotent.
- Extracted the one-beam residual-island floor without changing its formula and
  consolidated calibrated scale-SNR derivation so the serial oracle, local
  topology pass, and publication pass cannot drift. The one-tile stage exactly
  reproduces the promoted serial retained/reconstruction masks and scale
  support; combined SNR and signal products agree within `2e-13`.
- Proved exact generation-manifest, chunk-checksum, mask, and topology identity
  for one-tile and all-tile batches, an intermediate batch size, reverse
  completion order, identical retry of every task, `SerialExecutor`, and
  existing-client Dask with one and two workers. One-tile versus rectangular
  many-tile execution retains exact masks and global topology IDs and the
  existing `2e-13` finite-value tolerance. Different partitions deliberately
  have different chunk manifests because ownership bounds are part of chunk
  identity; the invariant across partitions is the logical science and stable
  reconciled identity. Shifted-origin science remains covered by the preceding
  storage-independent oracle because Zarr ownership is canonically
  zero-origin.
- Advanced the reviewed development contract to schema 7, SHA-256
  `4307a43c2904c885705c72c45e801dedc74f86ae4570852ca122485f85177e3f`,
  freezing two-pass recomputation, array-free scheduler results, batch and
  retry semantics, the complete executor matrix, and the honest distinction
  between same-partition byte identity and cross-partition scientific
  identity. No threshold, association rule, compact result, or closed campaign
  evidence changed.
- The focused scientific, topology, executor, and contract suite passes 182
  tests. Dedicated branch coverage passes 34 tests with 100% coverage for
  `phase_five_execution.py`, 98% for the multiscale stage, and 99% combined.
  The complete branch-aware project run passes 1,639 tests with 44 deselected
  and four expected failures at 94.88% total coverage. The fast handoff suite
  passes Ruff, Pyright, doctests, and 1,489 tests with 194 deselected and four
  expected failures; the strict documentation build also passes.

**Decision:** the third Phase 5 Step 5 checklist item is complete. The two-pass
recomputation avoids a response bank but has not yet passed the incremental
runtime gate; this task makes no performance, memory, or qualification claim.

**Immediate next step:** record bounded retained bytes, workspaces, summaries,
shards, and graph size under `SerialExecutor` and the existing executor path.

## 2026-08-24 — Complete Phase 5 bounded-resource evidence

**Plan phase:** Phase 5, Step 5 — bounded deterministic execution

- Confirmed the TDD red state: the new structural contract failed because the
  filter and stage results did not expose retained-array, complete-worker,
  summary, shard, or graph evidence.
- Added exact owned-ndarray payload accounting at filter, detection, topology,
  and publication checkpoints. Kernel workspace remains the conservative
  algorithm estimate; `maximum_worker_bytes` records the larger complete
  filter-evaluation or retained stage checkpoint without presenting Python
  object overhead, allocator fragmentation, RSS, transfer, or spill as known.
- Reduced avoidable retention before measuring it. The filter seam now copies
  and releases the matched-filter read responses before evaluating residual
  B3, and the stage releases source/background/RMS windows after preparing
  independent residual inputs. Scientific outputs and checksums remain
  unchanged.
- For the reviewed five-pixel-major beam and 256-square core, recorded a
  324-square/104,976-pixel widest read, 12,058,624 retained filter-core bytes,
  3,604,480 retained detection bytes, 16,057,904 matched-filter workspace
  bytes, 18,484,096 residual-B3 workspace bytes, and a 26,298,000-byte
  conservative complete filter peak.
- Each tile returns two topology and three scale summaries containing 20,480
  boundary-array bytes in total and publishes eight product shards. The graph
  has `2 * ceil(partitions / maximum_tiles_per_batch)` tasks and maximum width
  `ceil(partitions / maximum_tiles_per_batch)`. Serial, reverse completion,
  identical retry, and one-/two-worker existing-client Dask agree for a common
  batch size.
- At the 3,000-square anchor, 256-square cores and batch size 16 project to 144
  partitions, 18 coarse tasks, 1,152 shards, and 2.81 MiB total boundary-array
  payload. The same core at 100,000 square projects to 152,881 partitions and
  2.92 GiB of boundary arrays, so Phase 6 distributed hierarchical reduction
  remains mandatory before the extreme-scale claim.
- The focused Phase 5 scientific, executor, resource, and contract suite passes
  184 tests. The complete branch-aware run passes 1,641 tests with 44
  deselected and four expected failures at 94.90% coverage. The fast handoff
  suite passes Ruff, Pyright, doctests, and 1,491 tests with 194 deselected and
  four expected failures; the strict documentation build also passes.

**Decision:** Phase 5 Step 5 is complete. This structural audit does not claim
RSS, transfer/spill, runtime, qualification, or 100,000-square readiness.

**Immediate next step:** audit every accepted Phase 5 development defect for a
deterministic regression fixture before qualification.

## 2026-08-24 — Bind accepted Phase 5 defects to regression fixtures

**Plan phase:** Phase 5, Step 6 — qualification preparation

- Confirmed the TDD red state: the registry integrity test failed because no
  machine-readable defect-to-fixture registry existed.
- Audited the complete accepted Phase 5 history and separated endpoint
  symptoms from 17 distinct root causes: eight numerical-science, three
  product-semantics, three campaign-composition, and three runtime-provenance
  defects.
- Added registry schema 1 with the accepting revision, root cause, permanent
  invariant, and unique deterministic pytest node IDs for every defect. A
  structural test fails if any accepted defect, fixture file, or named test
  function disappears.
- Ran all 33 registered fixtures directly; every numerical, boundary,
  composition, identity, and failure case passes. This is development
  regression traceability and does not reopen or replace qualification.
- Made the newly introduced six-argument multiscale stage boundary explicit:
  scientific configuration, executor, and sink are now keyword-only. This
  resolves the current Ruff positional-argument rule without changing stage
  behaviour; all 11 stage integration tests pass.
- The complete branch-aware run passes 1,645 tests with 44 deselected and four
  expected failures at 94.90% coverage. The fast handoff suite passes Ruff,
  Pyright, doctests, and 1,495 tests with 194 deselected and four expected
  failures; strict documentation and all pre-commit hooks also pass.

**Decision:** the first Phase 5 Step 6 item is complete. Every accepted
development defect now has a checked-in deterministic regression fixture.

**Immediate next step:** re-run the complete Phase 4 compact regression and
stronger-Hebog envelopes before preparing the untouched Phase 5 qualification.

## 2026-08-24 — Pass the complete Phase 4 compact regression

**Plan phase:** Phase 5, Step 6 — qualification preparation

- Ran current Hebog revision `58074cc3f12d8c82507ac74868ec62ca67422572`
  on all 800 untouched Phase 4U compact realizations with eight local workers.
  All realizations succeeded in 372.16 seconds. The candidate shard SHA-256 is
  `7a6f0204104a9f2e86253c345a0aa60b438106df387b8fc5c51353090ce4ccc3`.
- Compiled the candidate with the retained exact released-PyBDSF shard
  `75fa0a3a53ae4a7c63ffb2cac63213c04380eab3160622d93dfe1c00f78ea23b`
  and pinned-master shard
  `4c9563f0fe8687da3a4d5370c39fbbcb8579483a8911d4f3a123da2a1b4a6f49`.
  The complete campaign file SHA-256 is
  `dea8b3889c145c07f006841574ae605bbf8d54b3c8e1c93e2f9a5dc77bdefb32`.
- Diagnosed two exit-137 evaluator terminations before any write-once decision
  appeared. Loading one 90-MiB implementation shard expands to about 10.4 GiB
  of validated Python/Pydantic objects; co-resident loading of the three-shard
  278-MiB campaign exceeded the host process-memory envelope. This was an
  evaluation-resource defect, not a failed or partial scientific decision.
- Added a bounded evaluator that verifies the exact campaign and shard file
  hashes, validates and reduces each implementation in an isolated child
  process, then applies the unchanged paired BCa, absolute-gate, and
  stronger-Hebog functions to compact numerical summaries. The checksum-bound
  compact decision engine, including its 50,000-resample SciPy batch, remains
  byte-for-byte unchanged.
- The terminal decision SHA-256 is
  `43381c51a583e8993bd47ea2c8d557c4315c78200d574a237e51958a1ce100a0`.
  It passes all 20 paired endpoints against released PyBDSF, all 20 against
  pinned PyBDSF master, all 77 governed absolute gates, and all five named
  stronger-Hebog envelopes. Fourteen raw median observations remain
  report-only as frozen; there are no failed or indeterminate governed gates,
  endpoint failures, implementation failures, or aggregate failure reasons.
- The bounded module has 98% focused branch-aware coverage. The complete
  branch-aware suite passes 1,658 tests with 44 deselected and four expected
  failures at 94.98% coverage. The fast handoff suite passes Ruff, Pyright,
  doctests, and 1,508 tests with 194 deselected and four expected failures;
  the strict documentation build also passes.
- Reproduced the complete decision through the final adapter while preserving
  the checksum-bound compact engine byte-for-byte. After excluding only the
  expected new `captured_at` timestamp, the retained and reproduced decision
  documents have the identical canonical SHA-256
  `52493104429a95da38875b3a87eb8ce983bae56c2bee38f8344eaa98e1d10954`.

**Decision:** the complete Phase 4 compact regression remains green on the
current Phase 5 implementation. The bounded evaluator changes only evaluation
memory lifetime and does not authorize a new campaign or qualification look.

**Immediate next step:** validate and commit the bounded evaluator, bind its
accepted resource defect to the regression-fixture registry, then continue
the remaining Phase 5 documentation and pre-qualification preparation.

## 2026-08-24 — Bind the compact evaluator memory defect

**Plan phase:** Phase 5, Step 6 — qualification preparation

- Added `compact-evaluator-memory-lifetime` as the fourth runtime-provenance
  root cause in registry schema 1, accepted by revision `c97736c`.
- Bound the defect to deterministic exact-result, provenance-drift, and
  streaming canonical-hash tests. The registry now contains 18 accepted root
  causes and 34 unique pytest functions across its four defect families; the
  complete registered lane expands to and passes 36 collected cases.

**Decision:** every accepted Phase 5 defect remains bound to a permanent
fixture after the compact-regression evaluation fix.

**Immediate next step:** update the user-facing Phase 5 demonstration and
method/readiness documentation without overstating unfinished qualification.

## 2026-08-24 — Demonstrate the current Phase 5 multiscale method

**Plan phase:** Phase 5, Step 6 — documentation and readiness preparation

- Updated the Marimo source-finder demonstration to distinguish the qualified
  compact Phase 4 path from the implemented but not yet finally qualified
  Phase 5 multiscale path.
- Added an executable compact-clean residual example with a 4-sigma direct
  peak. The promoted beam-aware matched-filter bank provides greater than
  5-sigma seed evidence, while residual-B3 scale support remains auditable and
  the retained mask grows only on original residual pixels at or above the
  3-sigma island threshold.
- Corrected the quick start and Phase 5 contract so they no longer describe
  multiscale, association, extended measurement, provenance, or product
  completion as absent. They still state explicitly that public
  `find_sources` orchestration, controlled performance, untouched
  qualification, the Rapthor decision profile, and independent human review
  remain open.
- Marimo's strict checker passes, the complete notebook executes successfully
  through a non-interactive HTML export, and the strict MkDocs build passes.

**Decision:** the schema, current-method, configuration, per-object
scale/support provenance, and interactive-demonstration part of Phase 5 Step 6
is complete. A release-readiness record would be premature until the remaining
scientific and performance gates close.

**Immediate next step:** implement and run the controlled Phase 5 incremental
benchmark preparation across 256, 512, 1,024, and 3,000-square anchors and any
measured crossover neighbourhoods.

## 2026-08-24 — Prepare the Phase 5 incremental performance matrix

**Plan phase:** Phase 5, Step 6 — incremental performance

- Added a frozen schema-1 matrix spanning 256, 512, 1,024, and 3,000 pixels
  across sparse, normal, and extended workloads, one warm-up, five measured
  repetitions, four one-thread Dask workers, and the 6.0-second representative
  stage budget.
- Added both serial and Dask probes at 1,024 and 3,000 pixels. The primary
  policy remains serial through 1,024 and Dask at 3,000 until the measured
  crossover report is reviewed.
- The measured boundary is the complete two-pass multiscale stage after one
  prepared Phase 2 background/RMS generation: filtering, bounded topology
  summaries, global reconciliation, recomputation, and atomic eight-product
  Zarr publication are included. Phase 2 setup remains recorded but excluded.
- The deterministic generator uses beam-correlated noise plus compact or
  extended bounded source patches. Typed per-cell evidence binds input,
  source-tree, configuration, dependencies, resources, timing dispersion,
  aggregate process-tree RSS, graph/task geometry, workspaces, retained
  arrays, summaries, and output shards.
- The exact 68-pixel filter halo of the 10-pixel benchmark beam requires a
  nominal core greater than 272 pixels. The protocol therefore freezes a
  273-pixel minimum core; a 256-square image remains one tile and never gains
  an undersized halo.
- Eight focused protocol, rejection, generator, WCS/beam, and budget tests
  pass. A complete 64-square serial smoke run completed one warm-up plus five
  measurements and produced valid typed evidence, consistent task counts, and
  bounded product metadata.

**Decision:** the measurement protocol and harness are ready for the first
controlled Phase 5 incremental curve. No budget or crossover conclusion is
recorded before that curve runs.

**Immediate next step:** validate and commit the harness, then execute the
matrix from that immutable revision and interpret the scientific-structure
evidence before its runtime decision.

## 2026-08-25 — Correct the Phase 5 curve and optimize bounded publication

**Plan phase:** Phase 5, Step 6 — incremental performance

- Retained the first immutable matrix at
  `benchmark-results/phase-5/incremental-multiscale` as diagnostic evidence.
  All 18 cells completed and preserved stable scientific structure, but its
  three 3,000-square Dask medians were 14.0231, 14.6077, and 14.4626 seconds
  against the 6.0-second budget. The protocol SHA-256 is
  `951135d8202e4c2723a24df2f46034f76dd98256a264206a2d539b579630a1e2`.
- Found a harness-composition defect before treating that runtime as the
  reviewed curve: the generator and task geometry had inherited a ten-pixel
  beam and 1,000-pixel cores, whereas the reviewed Step 5 composition is a
  five-pixel beam with 256-pixel cores. The earlier LOG preparation statement
  freezing a 68-pixel halo and 273-pixel minimum is therefore superseded for
  this matrix; the corrected exact halo is 34 pixels and a 256-pixel core is
  admissible.
- Profiling then isolated two independent implementation costs. Sparse local
  labels invoked SciPy's sorting reductions repeatedly, and 144-tile Zarr
  execution reopened immutable metadata and synchronously read each chunk in
  isolation. Linear `bincount`/`maximum.at`/`minimum.at` reductions preserve
  global first-pixel and equal-peak tie semantics without the sort.
- Zarr array handles and the canonical completion record are now reused only
  within a bounded coarse-task access session and discarded afterward. Chunk
  bytes are still checksummed whenever read. Fresh chunks use LocalStore's
  atomic write and required CRC32C codec; their content SHA-256 is verified in
  the mandatory complete-generation check before the immutable marker can be
  published. Existing retries still read and content-validate before they are
  accepted.
- Complete-generation validation groups at most four canonical tile rows per
  read, remaining bounded independently of image height. FITS inputs use one
  bounded batch open, and their retained arrays are included in worker-memory
  evidence. A 12-tile bound balances 144 partitions into 12 tasks per pass,
  avoiding a single-task final wave on the approved four-worker executor.
- Corrected 3,000-square normal-profile smoke runs now take 5.4939, 5.6318,
  5.7328, and 5.9065 seconds with 144 partitions and 24 tasks. The latest run
  records a 37,350,048-byte maximum worker payload and 28,890,128 retained
  array bytes. These are development diagnostics, not the five-repetition
  matrix decision.
- The focused storage, labelling, partition-invariance, benchmark-protocol,
  and Phase 5 execution suites pass 66 tests. The full branch-aware suite
  passes 1,671 tests with 44 deselected and four expected failures at 94.96%
  coverage; changed production modules retain 96--99% coverage. `just check`
  passes Ruff, Pyright, doctests, and 1,517 tests with 198 deselected and four
  expected failures.

**Decision:** the first curve does not bind the reviewed runtime decision.
The corrected candidate preserves science and storage safety and has adequate
smoke headroom to justify one complete write-once corrected matrix. The
6.0-second gate remains open until that immutable matrix is evaluated.

**Immediate next step:** validate and commit this corrected candidate, run the
complete matrix into a new output namespace, and decide science structure
before runtime and crossover policy.

## 2026-08-25 — Reject a measurement-perturbed Phase 5 curve

**Plan phase:** Phase 5, Step 6 — incremental performance

- Ran the complete corrected write-once matrix at candidate `af1526b` into
  `benchmark-results/phase-5/incremental-multiscale-corrected`. All 18 cells
  completed. The terminal summary SHA-256 is
  `055f6dee9784ded174af1a386c703ba59a2b7a26e053ddc4bad477ab147e2dde`;
  its protocol SHA-256 is
  `a581fc4226b9d0dc5fb20ae74ae272b9b4fe66df9901c3c5e9ebf8f50dcd3fea`.
- Interpreted science before runtime. Serial and Dask have identical detection,
  reconstruction, and per-scale island counts for all six crossover cells,
  and every cell is stable across repetitions. Serial is 35.7--44.4% faster
  at 1,024 pixels; Dask is 4.10--4.33 times faster at 3,000 pixels, placing the
  measured crossover strictly between those anchors.
- The formal 3,000-square Dask medians were 6.7771, 6.5787, and 6.8092 seconds,
  so the uncorrected terminal budget decision properly records all three
  profiles as failures against 6.0 seconds. Peak aggregate sampled RSS was
  1.67--1.74 GB; all runs retained 144 partitions, 24 tasks, and the reviewed
  37,350,048-byte maximum worker payload.
- Diagnosed the disagreement with the 5.49--5.91-second smoke curve as a
  benchmark-instrumentation defect. The RSS thread performed recursive process
  discovery plus per-process RSS reads every 5 ms. On the same normal-profile
  input and candidate it increased one controlled run to 6.9189 seconds.
- Corrected the monitor to snapshot the already-started controlled driver/Dask
  process tree once and sample those handles every 50 ms. A focused regression
  proves descendant discovery occurs once. The same controlled run now takes
  5.7175 seconds while recording 1,718,255,616 bytes of aggregate sampled RSS.
  No scientific, storage, executor, gate, or workload identity changed.

**Decision:** preserve the terminal failed matrix, but do not use its perturbed
wall times for the runtime gate. This is an observation defect, not permission
to erase a result or tune science. A new output namespace and immutable harness
revision are required for the first valid corrected curve.

**Immediate next step:** validate and commit the monitor correction, then run
the complete write-once matrix from that immutable revision and decide science
structure before runtime.

## 2026-08-25 — Pass the Phase 5 incremental performance curve

**Plan phase:** Phase 5, Step 6 — incremental performance

- Ran the complete 18-cell write-once matrix from clean immutable commit
  `1f7a4ae0670a564ded16397f4c2c3054f93654b3` into
  `benchmark-results/phase-5/incremental-multiscale-instrumentation-corrected`.
  Every evidence document binds the unchanged production source-tree SHA-256
  `70481c51cff50b92e4ece9ce5bd2d85d6399285ac9ac2eff76398f381597b246`.
  The atomic summary SHA-256 is
  `980e24c21591a2af1187767ff179d9199b3c0dd61f7edbdd389871e218cc7d80`;
  the protocol SHA-256 remains
  `a581fc4226b9d0dc5fb20ae74ae272b9b4fe66df9901c3c5e9ebf8f50dcd3fea`.
- Interpreted science first. At both 1,024 and 3,000 pixels, every sparse,
  normal, and extended Serial/Dask pair has identical detection,
  reconstruction, and per-scale island counts. The harness also required each
  cell's structure to remain stable across its warm-up and five measured runs.
- All representative four-worker Dask medians pass the frozen 6.0-second
  budget: sparse 5.6711 seconds, normal 5.5770 seconds, and extended 5.6427
  seconds. Their observed ranges are respectively 5.4624--5.7183,
  5.4180--5.6059, and 5.5591--5.7570 seconds. Maximum sampled aggregate RSS is
  1,727,070,208 bytes; every representative run records 144 partitions, 24
  tasks, and a 37,350,048-byte maximum worker payload.
- The complete crossover decision supports the existing prospective policy.
  At 1,024 pixels Serial medians are 1.1429--1.1846 seconds and are 1.49--1.69
  times faster than Dask. At 3,000 pixels Dask is 3.35--3.43 times faster than
  Serial, whose medians are 19.0193--19.1316 seconds. No compatible earlier
  reviewed curve exists for an adjacent-tier regression test; this is now the
  immutable comparison baseline for later performance changes.

**Decision:** the Phase 5 incremental performance item passes. Retain Serial
through the 1,024-pixel anchor and Dask at the 3,000-pixel anchor; any finer
crossover selection or later performance change requires prospective evidence
against this exact curve. This result is not the complete Rapthor wall-time
gate and does not replace untouched scientific qualification.

**Immediate next step:** validate and commit the reviewed performance decision,
then complete remaining pre-qualification work without opening the untouched
one-look dataset before named approval.

## 2026-08-25 — Freeze the Rapthor profile comparison boundary

**Plan phase:** Phase 5, Step 2D — Rapthor workflow profile

- Confirmed the intended test-first failure: the new Step 2D test could not
  import a profile contract or decision comparator before implementation.
- Added frozen schema 1 binding Rapthor commit `b1a64674...`, LSMTool commit
  `3adf3d6f...` and source-finding SHA-256 `eccb93f1...`, the real
  `rapthor-representative-3000` inventory and all six individual input hashes,
  and both exact PyBDSF references. Both references use the same traced hard
  5/3-sigma, zero-mean, adaptive-RMS, three-scale, mask-filtering configuration
  and the Rapthor 15-core request.
- Froze eight required component-decision lanes: true sky, apparent sky,
  bright components, extended-associated, edge, masked/invalid-neighbour,
  sparse, and crowded. Compact must reach 0.995 agreement overall and within
  every lane; PyBDSF references and strata cannot compensate for one another.
- Implemented a scheduler- and LSMTool-independent binary comparator over the
  exact post-filter membership records. It rejects duplicate or changed
  component identities and strata, reports every disagreement, and defaults
  to continuum with incomplete status if a required lane is empty. The runner
  must invoke the exact pinned LSMTool filtering operation rather than copy its
  sector clipping, mask lookup, grouping, bright merge, or name transfer.
- The inventory remains checked in, but the restricted real FITS, sky-model,
  vertices, and Measurement Set inputs are no longer present on this host.
  Consequently no profile result was generated and no selection is claimed.

**Decision:** Step 2D identity/configuration/stratum freezing is complete, as
is the pure fail-closed comparison seam. The experiment remains pre-results;
restore and checksum-verify the controlled inputs, freeze the exact component
population, and execute both Hebog profiles through pinned LSMTool before
selecting compact or continuum.

**Immediate next step:** validate and commit the pre-results protocol and
comparator. Then prepare the controlled-runner materialization/decision runner
without opening the untouched Phase 5 qualification population.

## 2026-08-25 — Complete the Rapthor profile evidence seam

**Plan phase:** Phase 5, Step 2D — Rapthor workflow profile

- Confirmed the intended test-first failure because neither the normalized
  membership evidence model nor the terminal evaluator existed.
- Split the controlled evidence into a pre-results component population and a
  post-filter membership result. The population freezes canonical component
  identifiers and safety strata before any profile result is available; the
  result binds that exact file by SHA-256 and requires complete compact,
  continuum, released-PyBDSF, and pinned-master lanes over the same identities.
- The mandatory JSON hook normalized the still-pre-results profile contract;
  its final byte identity is
  `2c50fb185c9a9721bf7f4959a406c7cbdce5315c447cd854c8291389e21711e3`.
  No population or membership result existed under its earlier formatting.
- Added a pure four-lane evaluator. Compact selection depends only on the
  qualified continuum comparison and the frozen 99.5% conjunctive gate. Four
  profile-versus-reference comparisons are always reported, but cannot rescue
  a failed compact-versus-continuum lane.
- Added a write-once terminal command that rejects contract, population,
  software, restricted-input, filtering-operation, or lane drift. Its output
  explicitly leaves untouched qualification unopened and Phase 7 cutover
  unauthorized. Focused tests cover complete selection, non-compensation,
  changed populations, changed contract identity, and overwrite refusal.

**Decision:** the Hebog-side Step 2D materialization and evaluation boundary is
complete. No workflow profile is selected because the restricted inputs remain
absent; the controlled runner must restore and verify them, freeze the exact
component population, then execute pinned LSMTool for all four lanes.

**Immediate next step:** validate and commit this evidence seam, then freeze a
reproducible public/challenge comparison protocol without opening the final
untouched qualification population.

## 2026-08-25 — Pre-review the public multi-telescope comparison

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Reviewed the official SKA SDC1 release, scoring boundary, and results paper,
  plus the CIRADA Hydra release and Hydra I/II comparison papers. The smallest
  complementary design is the truth-bearing 1.4-GHz, 1000-hour simulated
  SKA-MID lane and the real ASKAP EMU Pilot deep/shallow two-degree lane.
- Added a proposed machine-readable contract with the exact public source
  URLs and evidence roles. SDC1 uses official revealed truth for semantically
  matching Phase 5 catalogue gates; its classification-dependent official
  score is report-only because Hebog does not classify source populations.
- Scoped the ASKAP archive's Aegean, Caesar, ProFound, PyBDSF, and Selavy
  products as separate diagnostics. The real field has no astronomical truth,
  so deep/shallow stability and cross-finder differences cannot establish or
  rescue an absolute science pass.
- Froze the intended no-compensation policy and a pre-Hebog selection boundary
  for eight disjoint SDC1 cut-outs. Exact column mappings, units, ranking
  formulas, source and cut-out SHA-256 values, and adapters remain deliberately
  absent until the public artifacts are acquired and inspected under review.
- Added contract tests that reject missing telescope lanes, truth-role drift,
  removed Selavy context, missing artifacts, or cross-lane compensation. The
  proposal keeps human review, checksum freeze, execution, untouched
  qualification, and cutover false.
- The mandatory JSON hook normalized the contract's key order without changing
  its semantics; the resulting proposed contract SHA-256 is `ad412c20...`.

**Decision:** recommend SDC1 plus ASKAP/Hydra. Do not add a third survey merely
to increase finder count; add one later only if independent review identifies
a material frequency, instrument, or morphology gap.

**Immediate next step:** obtain named scientific review of this proposed
dataset and role selection. After approval, acquire and hash the public files,
freeze exact SDC1 cut-out formulas and populations, and implement the adapters
without opening the untouched qualification population.

## 2026-08-25 — Audit the untouched Phase 5 qualification design

**Plan phase:** Phase 5, Step 6 — pre-opening qualification readiness

- Confirmed with a no-science audit that the checked-in qualification manifest
  SHA-256 `40f1d0cf...` contains 400 realizations of one beam/WCS geometry. No
  qualification image, finder product, or scientific result was generated or
  inspected.
- Bound the already reviewed recovery power record SHA-256 `bbfab3a0...` and
  its 226 continuum paired comparisons. It requires at least 1,532 continuum
  realizations and selects 1,688, balanced as 422 over four geometries. Its
  combined familywise power lower bound is 0.90508 against the 0.90 minimum.
- Added a pure pre-opening audit and write-once command. It rejects a viewed
  qualification flag, changed power-review identity/status, inconsistent
  geometry balance, invalid candidate identities, inadequate prospective
  familywise power, and output replacement.
- Published ignored audit
  `benchmark-results/phase-5/qualification-design-audit.json`, SHA-256
  `9b0fcb89...`. Its status is `replacement-design-required`; it explicitly
  preserves the current manifest unopened and keeps replacement freeze,
  execution, and qualification opening false.

**Decision:** do not execute the 400-image manifest. Recommend a fresh,
seed-disjoint, four-geometry 1,688-image continuum replacement. Named
scientific review must also decide whether the final one-look repeats a fresh
800-image compact lane or binds the closed Phase 4U qualification and current
compact regression.

**Immediate next step:** validate and commit the audit boundary. Then request
named scientific approval before freezing any replacement qualification
identity; execution requires a separate later one-look approval.

## 2026-08-25 — Freeze the final Phase 5 qualification population

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Recorded Gemma Danks's named approval of a 1,688-image Continuum population,
  balanced as 422 fresh seeds over four reviewed geometries, and of binding
  the already closed Phase 4U/current compact evidence rather than running a
  new compact lane. No closed result is pooled or rescored.
- Froze manifest SHA-256 `7c67127e...` and population-contract SHA-256
  `4a52f551...` at candidate `9062664...`, source-tree SHA-256 `e4307246...`,
  configuration SHA-256 `0e5dde51...`, power-review SHA-256 `bbfab3a0...`, and
  design-audit SHA-256 `9b0fcb89...`. Execution, finder output, and
  qualification opening remain false.
- Corrected a historical recovery test that tried to regenerate an old freeze
  against the evolving dataset registry. It now verifies the immutable closed
  population SHA while separately testing current manifest generation, so a
  legitimate future dataset cannot masquerade as recovery-evidence drift.

**Decision:** the replacement population identity is frozen and unopened. A
reviewed runner/compiler/evaluator/runtime composition and a separate named
one-look execution approval are still required.

## 2026-08-25 — Acquire and inspect the public Phase 5 evidence schemas

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Recorded named acquisition-only approval in decision SHA-256 `7bfd3866...`
  and downloaded all seven exact SDC1/Hydra artifacts: 15,053,995,875 bytes in
  total. Terminal acquisition SHA-256 `a74e60de...` verifies every file's
  source size and SHA-256; the ignored raw products remain outside Git.
- Added a restartable, range-verified acquisition command and a schema-only
  inspector. Schema review SHA-256 `409318f5...` binds inspector SHA-256
  `074e4df9...`, the 32,768-square SDC1 image/truth/submission layouts, the
  matched 3,600-square Hydra deep/shallow images, and ten published catalogues
  for Aegean, Caesar, ProFound, PyBDSF, and Selavy.
- Made the proposed eight-tile truth-only selector exact: 2,048-square aligned
  tiles, mean primary beam at least 0.5, official size conversions, apparent
  flux and convolved peak SNR, deterministic empty-tile values, fixed stratum
  order, and global `(y, x)` tie-breaking. SDC1 population classification is
  report-only; no unverified numeric class mapping is asserted.
- Recorded the procedural deviation transparently: headers and five truth rows
  from already complete exact-sized files were viewed while the final Hydra
  archive was still downloading, before the aggregate record sealed. No image
  pixels, finder products, or catalogue distributions were viewed, and those
  values did not inform the proposal. Formal inspection was rerun only after
  all source hashes sealed.
- The mandatory JSON formatter subsequently changed only object-key order and
  whitespace in the acquisition decision. Approved serialization amendment
  SHA-256 `243d1680...` retains historical decision SHA-256 `7bfd3866...`,
  binds canonical SHA-256 `d5762063...`, and verifies the same seven requests
  and closed scientific flags against terminal acquisition `a74e60de...`.

**Decision:** acquisition and schema preparation are complete, but cut-out
selection and finder execution stay closed. The exact schema/selection
amendment requires named scientific approval; then adapters and a write-once
selected population may be implemented without opening final qualification.

## 2026-08-25 — Freeze the final qualification execution composition

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Implemented the checksum-bound final protocol, pending execution decision,
  endpoint registry, launcher, finder wrappers, compiler, evaluator, and
  identity review without producing a campaign request, materialising an
  image, running preflight, or opening qualification science.
- The exact matrix has 1,688 Continuum inputs, 8,440 total runs, and 5,064
  binding candidate/operational runs. The two PyBDSF controlled-background
  legs remain diagnostic. The already passing compact decisions stay separate
  and are bound without pooling or rescoring, so Aegean's exact runtime is
  retained in the four-image review but its final wrapper rejects fresh runs.
- Built the immutable Hebog runtime from candidate `9062664...`: image ID
  `e7f1ce9e...`, digest `sha256:132f1c3d...`, and dependency inventory
  `d383be3a...`. The released PyBDSF, pinned-master PyBDSF, and Aegean runtime
  identities are unchanged. Identity review SHA-256 `42ad6237...` binds all
  prospective programs and runtimes.
- Added fail-closed tests for population scale, program identities, the
  non-executable Aegean boundary, pending-launch rejection, closed compact
  evidence, evaluator population, and an exact future named-approval
  transition. The no-data compiler/evaluator composition smoke test succeeds.

**Decision:** final qualification preparation is complete, but execution is
not authorized. Do not run even the no-write preflight until a separate named
approval explicitly binds identity review `42ad6237...` and its four runtime
identities. Public cut-out selection, the restricted-input Rapthor profile,
and independent radio-astronomy/engineering review remain separate open gates.

**Immediate next step:** complete repository validation and commit this frozen
pre-results package. Then request the separate exact-identity qualification
execution approval; no campaign or public finder execution is implied.

## 2026-08-25 — Authorize the final Phase 5 qualification one-look

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Gemma Danks explicitly approved one terminal qualification execution bound
  to identity review SHA-256 `42ad6237...` and its unchanged four runtime
  identities. The approval permits the complete no-write preflight and
  execution only if that preflight passes without an identity change; it does
  not permit tuning, rescoring, rerunning, cutover, or release.
- Transitioned only the approval-dependent decision, registry checksum, and
  evaluation checksum. Frozen identity review `42ad6237...`, candidate
  `9062664...`, population, programs, thresholds, and runtime identities are
  byte-for-byte unchanged. The approved decision SHA-256 is `0c098922...` and
  the dependent endpoint-registry SHA-256 is `c34b51a9...`.
- Qualification remains unopened. No preflight request, staging directory,
  campaign product, or scientific output has been created or inspected.

**Immediate next step:** validate and commit the authorization transition,
create an immutable execution checkout from that commit, and run the complete
no-write preflight. Start the one campaign only if it passes unchanged.

## 2026-08-25 — Pass final qualification preflight without opening science

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Created immutable execution checkout
  `/private/tmp/hebog-phase5-final-qualification-execution-1d584fb` from exact
  authorization commit `1d584fb...`; an ignored evidence symlink supplies the
  already checksum-bound compact decisions without altering the hashed source
  tree.
- The complete no-write preflight passed as request SHA-256 `eebb6d79...` for
  all 1,688 inputs and 8,440 runs. Identity review `42ad6237...`, approved
  decision `0c098922...`, and all four runtime image IDs/digests remained
  unchanged. No terminal or staging campaign directory was created.
- Host free space is 46 GiB. The like-sized closed recovery campaign used
  about 102 GiB for its Continuum inputs and results, so launching now would
  predictably fail for storage rather than test the frozen science.

**Decision:** preflight satisfies the approved identity gate, but do not open
the one-look campaign until sufficient space is available. The exact proposed
cleanup is the closed external-recovery campaign's 44-GiB `inputs` and 67-GiB
`results`, retaining its manifests, compiler analysis, and terminal decision;
permanent deletion still requires explicit approval.

## 2026-08-25 — Seal the approved public comparison population

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Recorded Gemma Danks's named approval of schema review SHA-256
  `409318f5...` in selection decision SHA-256 `d60fb645...`. The decision
  permits the SDC1/Hydra adapters and one write-once selected population, but
  keeps finder execution, qualification, cutover, and release false.
- Implemented pure SDC1 size, apparent-SNR, tile-attribute, and deterministic
  eight-stratum selection functions. Added a unit-safe Hydra adapter for the
  published Aegean, Caesar, ProFound, PyBDSF, and Selavy schemas while
  preserving native finder, island, and component identities.
- The first selector process stopped before image pixels or selection because
  it found the official truth table's one non-finite centroid. ID `32397377`
  has finite remaining fields but `NaN` `ra_cent,dec_cent`; it cannot satisfy
  the approved half-open WCS membership rule. The adapter now admits only that
  exact known exclusion and rejects any changed non-finite population. The
  empty failed staging directory was removed before resuming.
- Terminal population SHA-256 `0a7c2b18...` was then created exactly once. Of
  256 aligned candidates, 32 met the every-pixel mean-primary-beam threshold;
  eight unique tiles were selected in the approved order. The terminal uses
  153 MiB and binds selector `0ddbc656...` and adapter `3a3aa7c3...`.
- Independent verifier `6f315f69...` rehashed all 15.05 GB of seven public
  inputs, verified all eight FITS checksums and truth memberships, confirmed
  the selected populations are disjoint, and rejected any unbound terminal
  file. Durable registry SHA-256 `df3a9088...` retains the compact evidence.

**Decision:** public acquisition, adapters, and selected-population creation
are complete without finder output. The next public gate is a separately
reviewed finder runner/compiler/evaluator composition and named execution
approval; this work did not open qualification or authorize cutover/release.

## 2026-08-26 — Seal final qualification and diagnose compiler failure

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- The one approved campaign completed all 1,688 inputs and 8,440 finder runs
  and published terminal campaign SHA-256 `4badb8e1...` from immutable
  execution commit `1d584fb...`. No second request or campaign was started.
- The committed compiler was invoked once and stopped during terminal request
  identity validation, before verifying or reading any input/result science
  and before creating `final-qualification-analysis.json`. It raised
  `ValueError: recovery decision fields changed`; no terminal decision exists.
- The failure is composition-only. The final compiler injects final protocol
  helpers into the inherited recovery module's `_HELPERS`, but recovery's
  `_configured_terminal` immediately replaces them from its stale
  `_COMPAT_HELPERS`. The post-failure JSON adapter therefore sends the final
  execution decision to `load_recovery_execution_decision` instead of
  `load_final_qualification_execution_decision`.
- A no-science diagnostic confirmed both sides: the frozen composition
  installed the recovery loader, while installing complete final aliases at
  the inherited compatibility layer selected the final loader, admitted the
  approved decision, and retained the 1,688-image request model. The
  diagnostic did not compile, score, or inspect campaign products.

**Decision:** preserve the sealed campaign and all scientific identities; do
not rerun, tune, rescore, or bypass the frozen compiler. The original compiler
identity is unusable, so evaluation remains closed and Phase 5 is not yet
qualified.

**Immediate next step:** prepare a no-science repair pre-review with a focused
real-seam regression, a corrected compiler and dependent registry/evaluator
identities, and an exact existing-campaign evaluation amendment bound to
campaign `4badb8e1...`. Named approval is required before the corrected
composition may compile and evaluate that existing campaign once.

## 2026-08-26 — Pre-review final-qualification evaluation repair

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Created machine pre-review SHA-256 `8cff6163...`, binding sealed campaign
  `4badb8e1...`, request `eebb6d79...`, the 1,688/8,440 population, original
  compiler `c2b7f3ac...`, evaluator `558e2957...`, registry `c34b51a9...`,
  evaluation contract `4b05d792...`, approved decision `0c098922...`, and
  identity review `42ad6237...`. Analysis and decision remain absent.
- Selected an evaluation-only wrapper strategy. The original frozen programs
  and evidence remain byte-exact; a prospective compiler will install the
  complete final aliases at both inherited helper layers before delegating to
  the frozen compiler, and a prospective evaluator will validate repair
  provenance before delegating unchanged scientific scoring.
- Rejected campaign reexecution, in-place edits to the frozen compiler, an ad
  hoc global patch, and treating operational completion as a scientific pass.
  The mandatory regression must invoke the actual JSON adapter that failed,
  retain the 1,688/8,440 model, and prove every unauthorized scope fails
  closed without reading raw qualification products.
- Added a deterministic contract test for the pending review and its frozen
  tracked identities. Focused final-qualification protocol validation passes
  seven tests.

**Decision:** the repair design is ready for named implementation review but
authorizes no implementation, compilation, evaluation, campaign execution,
optimization, tuning, rescoring, cutover, or release.

**Immediate next step:** obtain named approval of pre-review `8cff6163...`.
That approval may permit implementation, tests, and freezing exact repair
identities only. A separate later exact-identity approval is required before
the repair may compile and evaluate sealed campaign `4badb8e1...` once.

## 2026-08-26 — Implement the final-qualification evaluation repair

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Recorded Gemma Danks's named approval of pre-review `8cff6163...` in a
  separate implementation decision. The decision authorizes implementation,
  validation, and exact-identity freezing only; compilation, evaluation,
  campaign reexecution, optimization, tuning, rescoring, cutover, and release
  remain false.
- Added a fail-closed repair compiler that installs the complete final
  protocol, decision, registry, request, and result aliases at the inherited
  recovery compatibility seam before calling the byte-exact frozen compiler.
  It accepts only a later named authorization bound to campaign `4badb8e1...`,
  the repair programs, their identity review, absent write-once outputs, and
  unchanged scientific scope.
- Added a matching repair evaluator that validates an exact repair-provenance
  record before delegating all scientific scoring to the byte-exact frozen
  evaluator. Neither wrapper contains a second endpoint compiler, gate, or
  decision implementation.
- The regression exercises the actual JSON adapter that failed: it selects
  `load_final_qualification_execution_decision`, loads the approved decision
  and registry, retains exactly 1,688 images and 8,440 runs, and rejects a
  recovery-shaped decision. Synthetic tests also reject changed programs,
  evidence, outputs, campaign reruns, tuning, rescoring, and science changes.
  Focused validation passes 13 tests; no campaign input/result was opened and
  both terminal output paths remain absent.

**Decision:** the evaluation-only repair implementation is ready for exact
identity freezing. This implementation is not authority to compile or score
the campaign.

**Immediate next step:** commit the validated implementation, then freeze a
pending checksummed repair review against that commit and the existing sealed
campaign. Obtain a second named approval before invoking either wrapper.

## 2026-08-26 — Freeze exact final-qualification repair identities

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Committed the validated repair implementation as `b6ce3cdd...`, tree
  `fa7e1a07...`. Repair compiler SHA-256 is `42ac2a96...`; evaluator SHA-256
  is `f4396a8a...`; implementation decision SHA-256 is `bec708fe...`.
- Created pending repair identity review SHA-256 `b69b2eaa...`. It binds the
  implementation commit/tree, pre-review and implementation approval, sealed
  campaign `4badb8e1...` and request `eebb6d79...`, all byte-exact frozen
  compiler/evaluator/protocol/population/registry/contract/decision/review
  identities, candidate/source/configuration, and the unchanged four runtime
  images.
- Confirmed that `final-qualification-analysis.json`,
  `final-qualification-decision.json`, and the prospective execution decision
  are absent. Every campaign-execution, compilation, evaluation,
  optimization, tuning, rescoring, cutover, and release flag in the pending
  review remains false. Focused validation passes 14 tests without opening
  campaign products.

**Decision:** implementation and exact identity freezing are complete within
the approved scope. No compiler or evaluator has been invoked against the
campaign.

**Immediate next step:** obtain named approval of exact repair review
`b69b2eaa...`. Only that separate approval may authorize one compilation and
one evaluation of the existing sealed campaign; it may not authorize another
campaign, tuning, rescoring, cutover, or release.

## 2026-08-26 — Authorize one final-qualification repair evaluation

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Gemma Danks approved exact repair identity review `b69b2eaa...` and asked to
  continue. The recorded decision binds sealed campaign `4badb8e1...`, request
  `eebb6d79...`, repair compiler `42ac2a96...`, evaluator `f4396a8a...`, and
  the exact pending review.
- The decision permits one compilation and one evaluation only. Campaign
  reexecution, optimization, tuning, rescoring, scientific or gate changes,
  cutover, and release remain false. Analysis and decision are still absent.

**Decision:** the exact repair may now transition from its no-write
authorization check to one compilation and, only after successful atomic
analysis publication, one evaluation.

**Immediate next step:** validate and commit this authorization without
changing either repair program, run the repair compiler once, then evaluate
once if compilation succeeds.

## 2026-08-26 — Pass the untouched Phase 5 final qualification

**Plan phase:** Phase 5, Step 6 — untouched final qualification

- Committed authorization `54811b2...` retained repair compiler
  `42ac2a96...`, evaluator `f4396a8a...`, identity review `b69b2eaa...`, and
  sealed campaign `4badb8e1...` unchanged. The compiler ran exactly once and
  atomically wrote `final-qualification-analysis.json`, SHA-256
  `34fb0f7e...`. Its repair provenance validates against authorization
  `0e963b9a...`; no science meaning or gate changed.
- The authorized evaluator ran exactly once and atomically wrote
  `final-qualification-decision.json`, SHA-256 `d4db4d7f...`. The terminal
  status is `pass`, qualification is opened, and cutover remains false. The
  campaign audit contains all 1,688 images, all 8,440 terminal runs, all 5,064
  binding candidate/operational runs, zero failed or unavailable binding run,
  and zero unexpected run.
- Interpreted science before runtime. Both closed compact decisions pass
  without pooling or rescoring. All 143 Continuum absolute endpoints and all
  226 applicable paired comparisons pass. The tightest absolute gate is
  overall mask recall at `0.900893` against `0.90`; the tightest paired gate is
  overall mask precision against pinned PyBDSF master, whose upper confidence
  limit is `0.049648` against the `0.05` practical-regression margin.
- Runtime was reviewed only after the passing scientific decision. Median
  per-image wall time is 1.1157 seconds for Hebog, 3.5375 seconds for released
  PyBDSF operational, and 3.7566 seconds for pinned-master PyBDSF operational.
  The complete campaign elapsed 47,571.7 seconds. These source-finder campaign
  timings are diagnostic and are not the matched complete Rapthor performance
  gate.

**Decision:** the untouched final-qualification and evaluation-repair tasks
pass and are closed. Phase 5 itself remains open for the public/challenge
finder comparison, restricted Rapthor workflow profile, final readiness
record, and named independent radio-astronomy and engineering acceptance.
Campaign reexecution, optimization, tuning, rescoring, cutover, and release
remain unauthorized.

**Validation:** all 18 focused final-qualification tests pass. The required
branch-aware suite passes 1,742 tests with four expected xfails and 95.11%
coverage. `just check` passes formatting, Ruff, Pyright, doctests, 1,588
tests, and four expected xfails. The strict documentation build passes. Final
review against `CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** validate and commit this terminal evidence record,
then prepare the public/challenge finder execution composition without opening
another campaign or implying production cutover.

## 2026-08-26 — Pre-review the public finder execution boundary

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Added no-science execution pre-review `476265e1...`. It binds selected
  population `0a7c2b18...`, registry `df3a9088...`, schema review
  `409318f5...`, passing final-qualification decision `d4db4d7f...`, candidate
  `9062664...`, configuration `0e5dde51...`, and the qualified Hebog runtime.
- The design runs Hebog on eight selected SDC1 output cores and the complete
  Hydra deep and shallow images. It does not rerun published comparison
  finders. Candidate-owned background/RMS estimation and haloed SDC1 reads are
  explicit.
- SDC1 association, core admission, absolute gates, and non-compensating
  overall and per-stratum decisions are exact. Axis and position-angle errors
  remain diagnostic because Phase 5 has no frozen axis-error limit.
- Hydra remains non-binding and records exact per-finder, per-depth overlap,
  position, flux-ratio, and unmatched audits. It neither pools finder
  semantics nor invents a Hebog residual proxy.
- The contract test first failed because the pre-review was absent, then
  passed after the record was added. All authorization flags remain false. No
  public pixels, finder products, or catalogues were opened.

**Decision:** request named approval for implementation, testing, and exact
identity freezing only. A second approval of those identities is required
before any finder execution, compilation, or evaluation.

**Validation:** all 24 focused public-comparison tests pass. `just check`
passes formatting, Ruff, Pyright, doctests, 1,589 tests, and four expected
xfails. The strict documentation build passes. Final review against
`CODE_REVIEW.md` found no actionable issue. Coverage was not rerun because
this boundary adds no production code or control flow.

**Immediate next step:** validate and commit this non-executable review. Do
not implement or execute the prospective programs until named approval is
recorded.

## 2026-08-26 — Freeze exact public-finder identities

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Implemented and validated the public protocol, ten-case Hebog campaign and
  runtime boundary, SDC1/Hydra compiler, and terminal evaluator in local
  commit `3d234c5d...`. The implementation uses sparse deterministic
  association, binding-core truth before guard truth, deconvolved SDC1 shape
  diagnostics, and explicit non-binding Hydra semantics.
- Froze non-executable identity review SHA-256 `19b6296f...` against selected
  population `0a7c2b18...`, passing qualification decision `d4db4d7f...`,
  candidate `9062664...`, configuration `0e5dde51...`, the qualified Hebog
  runtime, five exact programs, and one exact absent output namespace.
  Pending decision SHA-256 `d307c1ea...` keeps finder and campaign execution,
  compilation, evaluation, optimization, tuning, rescoring, cutover, and
  release false.
- Confirmed that the campaign, analysis, and decision outputs do not exist.
  No public finder, compiler, or evaluator was invoked. All 20 focused
  protocol tests pass; the branch-aware suite passes 1,763 tests with four
  expected xfails and 95.01% coverage.

**Decision:** the implementation-and-freeze authorization is complete. The
public one-look remains closed until a separate named approval binds exact
identity review `19b6296f...`; that later approval may not authorize tuning,
rescoring, cutover, or release.

**Validation:** `just check` passes formatting, Ruff, Pyright, doctests, 1,609
tests, and four expected xfails. The strict documentation build and final
pre-commit suite pass. Review against `CODE_REVIEW.md` found no actionable
issue.

**Immediate next step:** obtain the named one-look approval, then run the
complete no-write preflight. Execute, compile, and evaluate exactly once only
if every identity remains unchanged.

## 2026-08-26 — Authorize the public-finder one-look

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Gemma Danks approved exact identity review `19b6296f...` and the qualified
  Hebog runtime. Authorization decision SHA-256 `a9330407...` binds the
  approval verbatim and opens the complete no-write preflight plus one
  campaign, one compilation, and one evaluation only if every identity is
  unchanged.
- Optimization, tuning, rescoring, cutover, and release remain false. The
  public campaign, analysis, and decision outputs remain absent. All 20
  focused public protocol tests pass, including the exact positive authority
  and prohibited-action boundary.

**Decision:** commit the named authorization before preflight so execution is
bound to an immutable repository state. Do not create campaign state unless
the complete preflight passes.

**Immediate next step:** validate and commit authorization decision
`a9330407...`, then run the exact no-write preflight against the qualified
local Hebog image and frozen public evidence.

## 2026-08-26 — Fail the terminal public-finder one-look

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- The complete no-write preflight passed against authorization commit
  `55e6409...`, identity review `19b6296f...`, decision `a9330407...`, selected
  population `0a7c2b18...`, and the qualified Hebog image. The single campaign
  sealed all ten successful cases as SHA-256 `42abb896...`; no second request
  or campaign was created.
- The authorized compiler ran exactly once and wrote analysis SHA-256
  `975978fb...`. The authorized evaluator ran exactly once and wrote terminal
  decision SHA-256 `954077e9...`. Provenance binds the exact campaign,
  protocol `f29100be...`, authorization, and identity review. The terminal
  status is `fail`; public evidence, cutover, and release remain false.
- Interpreted binding SDC1 science before Hydra and runtime. All nine endpoint
  populations fail completeness, reliability, median absolute integrated-flux
  error, and p95 absolute integrated-flux error. Overall values are 0.32463,
  0.75598, 0.10475, and 0.30592 against gates 0.90, 0.95, 0.10, and 0.25.
  Position offsets and p95 radial error pass, as do zero duplicates and merge
  fraction 0.00564. All eight strata reproduce the same four failure classes.
- All 16 non-binding Hydra diagnostics are complete. Hebog deep versus shallow
  has 38 matches among 356 deep detections and overlap 0.10674; the shallow
  catalogue contains 413 detections. Across Aegean, Caesar, ProFound, PyBDSF,
  and Selavy, Hebog matches 120--153 deep and 270--302 shallow detections.
  These products are diagnostic rather than truth and cannot compensate for
  SDC1.
- Runtime was read only after science: SDC1 cases took 55.76--108.88 seconds,
  Hydra shallow 82.52 seconds, and Hydra deep 164.89 seconds. No performance
  gate applies and no speed claim is made.

**Decision:** Phase 5 public evidence and readiness remain closed. Do not tune,
rescore, rerun, cut over, or release. Preserve the sealed evidence for an
independent scientific failure review that attributes detection-threshold,
background/RMS, association, and flux-measurement causes before any
prospective correction is proposed.

**Validation:** all 50 focused public-evidence tests pass. The branch-aware
suite passes 1,763 tests with four expected xfails and 95.01% coverage.
`just check` passes formatting, Ruff, Pyright, doctests, 1,609 tests, and four
expected xfails. The strict documentation build passes. Review against
`CODE_REVIEW.md` found no actionable issue.

**Immediate next step:** validate and commit the terminal evidence record,
then request independent radio-astronomy review of decision `954077e9...`.

## 2026-08-26 — Complete the public-finder scientific failure review

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Opened the sealed SDC1/Hydra products only after terminal decision
  `954077e9...`. No campaign, compiler, evaluator, gate, matcher, catalogue, or
  terminal record changed. Machine-readable review `320f57f5...` binds the
  exact campaign, analysis, decision, protocol, identity review, and execution
  decision.
- The frozen result is a valid Phase 5 stress-test fail but is not an official
  SDC1 score. Its matcher uses only position within 0.5 beam, while the
  official scorer combines position, size, and flux and measures chance
  associations with a null catalogue. Hebog's public catalogue contains no
  fitted/deconvolved shapes, core fraction, or population class, and the
  absolute 0.90/0.95 gates were never calibrated against submitted teams.
- SDC1 exposes a real low-SNR gap beyond RMS estimation: completeness is
  0.06588 at SNR 5--8 and 0.22444 at 8--10, while core RMS medians are
  66.06--66.82 nJy/beam against the 73 nJy truth-admission value. Candidate
  fifth-percentile SNR is 7.84. At SNR at least 50, frozen completeness is
  0.55159, but diagnostic position-only radii raise it to 0.84438 at five
  beams; the corresponding approximate chance-association probability is
  0.88, confirming that a larger positional radius is not a safe fix. Core
  versus centroid truth coordinates change 8,181 matches to only 8,173.
- Matched-source photometry is not the leading correction: median/p95 absolute
  flux errors are 0.09972/0.20581 at SNR 20--50 and 0.07171/0.12809 at SNR at
  least 50. Bright-source completeness is nearly flat, 0.54258--0.57042,
  across four intrinsic major-axis bins, so apparent size alone does not
  explain the high-SNR match deficit.
- Hydra establishes the candidate defect directly. Deep and shallow median
  RMS values, 30.52 and 169.97 microJy/beam, track sampled image MAD sigmas,
  32.94 and 175.81 microJy/beam. But three-beam association dilation makes
  deep support cover 4.139% of the image and creates 357 labels with p95 area
  6,248 pixels and maximum 55,186; shallow support covers 0.867% and creates
  423 labels with p95 777 and maximum 2,737. This bridging collapses catalogue
  identity and explains the counter-directional 356-deep/413-shallow counts
  and 38 matches.

**Decision:** Phase 5 remains open. Prioritize a prospective seeded-ownership
correction and complete public shape records, then redesign the SDC1 lane
around official source-finding match dimensions, a null control, submitted-
team calibration, and SNR-dependent curves. The viewed public products become
development/regression evidence. Require full cumulative replay and fresh
held-out qualification before proposing another one-look.

**Immediate next step:** obtain named approval for a no-execution scientific
correction pre-review. Do not tune, rescore, rerun, cut over, or release.

## 2026-08-26 — Pre-review the public-finder science correction

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Completed prospective pre-review
  `3e02aff3...` against terminal scientific
  review `320f57f5...`, qualified base candidate `9062664...`, final decision
  `d4db4d7f...`, viewed public population `0a7c2b18...`, and exact closed
  cumulative baseline `a45303df...`. No terminal evidence or historical
  contract changed.
- The smallest candidate correction retains original-residual accepted labels
  as authoritative seeds and attaches only significant support within the
  already reviewed half-beam recovery radius. Nearest exact seed support owns
  each recovered pixel; canonical global seed identity breaks ties. Context
  edges may retain physical association evidence but cannot merge pixels or
  catalogue rows. The historical three-beam connected-union branch remains
  unchanged for evidence reproduction.
- Public shapes use existing exact-support flux moments. Pixel covariance is
  transformed through the local WCS Jacobian, expressed as an observed
  moment-equivalent FWHM ellipse, and beam-deconvolved with explicit resolved,
  major-axis-only, unresolved, or unavailable states. A canonical quality flag
  prevents this estimator being represented as a nonlinear Gaussian fit.
- The redesigned SDC1 boundary is source-finding only. It recommends an
  isolated pinned official scorer, a frozen null catalogue, identical selected
  cores for all nine applicable published submissions, and SNR/morphology
  curves. Hebog still lacks population and core-fraction classification, so an
  official global score remains unavailable.
- The test-first matrix covers diffuse bridges, genuine single extended
  sources, ownership ties, blends, edges, invalid pixels, analytic covariance,
  WCS rotation, deconvolution states, serial/Dask and partition invariance, and
  catalogue round trips. Threshold, RMS, minimum area, aperture, flux, gate,
  and runtime changes are forbidden in the same correction.

**Decision:** the pre-review is non-executable and authorizes nothing. Viewed
SDC1/Hydra products remain development/regression evidence. Implementation and
fixture-only validation require named approval; cumulative replay and any
viewed-data execution require a later exact identity review and separate named
approval. Fresh qualification remains a third boundary.

**Immediate next step:** request named scientific and engineering approval of
the exact pre-review for implementation and fixture-only validation. Do not
run the cumulative replay or any public finder.

## 2026-08-26 — Implement the public-finder correction on fixtures only

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Recorded named decision `8ade048d...`, which binds correction pre-review
  `3e02aff3...` and authorizes only fixture-scale implementation. Prospective
  contract `f0ddd4d5...` keeps cumulative replay, viewed-data execution, a new
  campaign, fresh qualification, tuning, rescoring, cutover, and release
  explicitly closed.
- Added seeded multiscale ownership that keeps every direct residual pixel and
  label authoritative. Eligible significant support is attached only within
  the pre-reviewed half-major-beam radius by exact nearest-seed distance.
  Exact ties use a canonical global row-major owner reference rather than a
  label integer; tiled callers must carry that reference map into halo tasks.
  The closed three-beam connected-union implementation remains byte-for-byte
  unchanged.
- Added positive-original-residual moment-equivalent shapes on each exact
  owner support. Pixel covariance is mapped through the local east/north WCS
  Jacobian and beam-deconvolved into explicit resolved, major-axis-only,
  unresolved, or unavailable states. Existing centroid, aperture, peak flux,
  integrated flux, thresholds, RMS, and minimum-area policies do not change.
- Added an in-memory SDC1 source-finding adapter for position, deconvolved
  FWHM, angle, and apparent integrated flux only. It has no I/O, scorer,
  compiler, evaluator, campaign, or command entry point. Classification and
  core fraction remain absent, and records are explicitly ineligible for an
  official global score.
- Scientific review tightened the partition contract after identifying that
  tile-local seed order alone is insufficient when an owner's first global
  seed lies outside a halo. Analytic and local-Dask fixtures now prove exact
  global-reference, relabelling, executor, and partition invariance. Other
  fixtures cover diffuse bridges, one-source wings, high-order ties, invalid
  pixels, WCS moments, every deconvolution state, serialization, and adapter
  failure boundaries.
- The pre-commit formatter attempted to reorder one key in the approved
  pre-review. The file was restored to exact SHA `3e02aff3...`; its formatter
  configuration is independently checksum-bound by an earlier acquisition
  amendment and also remains unchanged. New JSON records were formatted
  explicitly. The final full hook run therefore skips only this irreconcilable
  formatter invocation while retaining JSON syntax validation and every other
  hook.

**Decision:** the fixture implementation is ready for an exact non-executable
identity review. It has not been replayed against the closed cumulative ledger
or run on viewed SDC1/Hydra evidence. Those actions still require a separate
named approval, and fresh held-out qualification remains a later boundary.

**Validation:** 118 focused analytic and executor tests pass; focused Ruff and
Pyright pass. `just coverage` passes 1,796 tests with four expected xfails and
95.06% total branch-aware coverage. The prospective adapter has 100% line and
branch coverage and the ownership module has 99%. All frozen recovery,
external protocol, and final-qualification identity tests remain green.

**Immediate next step:** create and review exact non-executable implementation
identities. Do not run the cumulative replay, open corrected viewed products,
or authorize qualification.

## 2026-08-26 — Freeze public-finder correction identities

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Published non-executable identity review `e2121fb8...` for fixture-validated
  candidate commit `b1d59e5...`, Git tree `4e16d9a0...`, and production source
  tree `2de6564e...`. The review binds the unchanged base configuration
  `0e5dde51...`, correction contract `f0ddd4d5...`, implementation decision
  `8ade048d...`, and approved pre-review `3e02aff3...`.
- Bound each changed candidate artifact and its fixture-validation identity,
  while preserving the historical three-beam oracle `06cd8a0d...`, recovery
  composition `9343e069...`, and association-edge seam `84a66a9c...`.
- Bound the exact closed cumulative baseline `a45303df...` and unchanged replay
  program `5d41d31e...`. The prospective correction ledger is absent. Corrected
  viewed campaign, analysis, and decision products are also absent; the viewed
  population remains development evidence and no executable viewed protocol
  has been frozen.
- Added focused governance regressions that require all review authorization
  flags to remain false, verify immutable contract links, preserve the closed
  baseline and selected-population bindings, and record absent outputs without
  opening ignored scientific products.

**Decision:** identity review `e2121fb8...` is ready for a separate named
approval authorizing one complete cumulative replay only. It does not authorize
viewed SDC1/Hydra execution, a new campaign, fresh qualification, tuning,
rescoring, cutover, or release.

**Validation:** all four focused identity tests and all nine fixture-only
correction unit tests pass. The local Dask partition-invariance integration
test passes outside the app's loopback-socket sandbox. `just check` passes
1,645 tests with 199 deselected and four expected xfails; strict documentation
build, focused Ruff, focused Pyright, JSON formatting, and diff hygiene pass.
No production code changed, so the already-recorded 95.06% branch-aware
coverage result for candidate `b1d59e5...` remains the applicable candidate
coverage evidence and was not rerun for this records-only freeze.

**Immediate next step:** obtain named approval bound to review `e2121fb8...`
and candidate `b1d59e5...` before running the complete 800-compact/1,600-
Continuum replay against baseline `a45303df...`. Interpret compact and
Continuum science before any later public diagnostics and require no
like-semantics regression.

## 2026-08-26 — Reject the correction replay before execution

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Gemma Danks supplied the exact named cumulative-replay approval bound to
  identity review `e2121fb8...`, candidate `b1d59e5...`, and baseline
  `a45303df...`. Decision `bf955638...` retains the exact approval and records
  that every excluded lifecycle action remains unauthorized.
- No-write preflight found that the review-bound program `5d41d31e...`
  hardcodes revision `c184acf7...`, calls
  `post_correction_candidate_configuration`, writes Continuum products with
  `build_post_correction_continuum_products`, and rejects another revision at
  its inherited runtime seam. It would not execute candidate `b1d59e5...`.
- Independently computed the full correction configuration as `65c8876d...`.
  Identity review `e2121fb8...` incorrectly recorded the unchanged base
  `0e5dde51...` as the candidate configuration. The error is in the freeze and
  replay composition, not the implemented correction science.
- Failed closed before starting a replay process, creating scratch or candidate
  products, or opening any scientific product. The write-once correction
  ledger remains absent. The prior approval cannot transfer to a changed
  program or replacement identity.
- Published non-executable repair pre-review `e198df12...`. It preserves the
  historical replay and all population, compact, compiler, evaluator,
  endpoint, gate, baseline, and viewed-public-data boundaries. It recommends
  one minimal wrapper selecting only the approved revision, complete correction
  configuration, corrected Continuum builder, and explicit source-overlay
  provenance.

**Validation:** eight focused identity and repair-preflight tests pass,
including execution of the real frozen module seams. Focused Ruff and Pyright
pass. `just check` passes 1,649 tests with 199 deselected and four expected
xfails, and the strict documentation build passes. No production code changed,
so coverage was not rerun for this pre-review-only change.

**Decision:** cumulative replay remains closed. Implementing the wrapper and
freezing replacement identities require named approval of pre-review
`e198df12...`; the replay itself will still require a later exact-identity
approval.

**Immediate next step:** request the limited replay-repair implementation
approval. Do not run the cumulative replay, open viewed SDC1/Hydra products,
start a campaign, or authorize qualification.

## 2026-08-26 — Implement the correction cumulative-replay wrapper

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Recorded named implementation decision `83d14670...`, binding repair
  pre-review `e198df12...`. It authorizes only the minimal wrapper,
  fixture/no-write validation, and replacement identity freezing; cumulative
  replay and all later execution or release actions remain false.
- Added a fail-closed wrapper around historical replay `5d41d31e...`. It
  selects candidate `b1d59e5...`, source tree `2de6564e...`, complete
  correction configuration `65c8876d...`, and
  `build_public_finder_correction_continuum_products`. Compact generation and
  the historical compiler, evaluator, endpoints, and gates remain the exact
  delegated objects.
- Added a spawned-worker seam so Python 3.14/macOS `spawn` workers install the
  same correction composition instead of re-importing the historical builder.
  Ledger-only provenance distinguishes the exact source overlay from inherited
  compatibility container `sha256:1a83f649...`; candidate shard marker bytes
  retain the historical schema.
- Before scientific input access the wrapper now requires a separate exact
  execution decision, clean checkout, approved source/configuration/contracts,
  `uv.lock`, historical program, compiler, evaluator, reference verifier,
  endpoint/evaluation contracts, viewed request, reconstructed-reference
  terminal record, closed baseline, and absent scratch/output. No execution
  decision, scratch, replay output, or viewed public-data access exists.

**Validation:** 52 focused wrapper, correction, product, and recovery tests
pass. The local Dask correction integration passes outside the app's
loopback-socket sandbox. Focused Ruff and Pyright pass. The wrapper tests prove
missing authorization fails before the frozen replay loads, candidate and
environment drift fail closed, correction seams replace only the approved
composition, and source-overlay provenance is added only to the terminal
ledger. `just coverage` passes 1,823 tests with four expected xfails and
95.07% total branch-aware coverage.

**Decision:** the repair implementation is ready for a replacement exact,
non-executable identity freeze. The replay remains unauthorized.

**Immediate next step:** validate and commit this wrapper, then freeze its
exact commit, program, evidence, runtime, output, and scratch identities. Do
not run the replay or open viewed SDC1/Hydra products.

## 2026-08-26 — Freeze replacement correction replay identities

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Committed the validated wrapper as `1a6cecb...`, Git tree `efdc910d...`.
  Wrapper `b4d02784...`, implementation decision `83d14670...`, and wrapper
  tests `4c55414e...` are now immutable implementation identities.
- Published non-executable replacement review `5e5bf04a...`. It binds
  candidate `b1d59e5...`, source tree `2de6564e...`, correction configuration
  `65c8876d...`, contract `f0ddd4d5...`, `uv.lock` `c81a9831...`, and inherited
  compatibility dependency runtime `sha256:1a83f649...`. The review states
  explicitly that the correction is a source overlay and is not baked into
  the inherited container.
- Bound historical replay `5d41d31e...`, compiler `e442f658...`, evaluator
  `7612746b...`, reference verifier `81faad48...`, endpoint registry
  `2d7a646b...`, evaluation contract `45901f8c...`, original request
  `7ba9be1b...`, reconstructed-reference record `69c66e0b...`, and closed
  baseline `a45303df...`.
- Froze the prospective command at two workers, reference reconstruction
  `benchmark-results/phase-5/viewed-reference-reconstruction`, output
  `cumulative-regression-ledger-public-finder-correction.json`, and scratch
  `/private/tmp/hebog-phase5-public-finder-correction-b1d59e5`. The execution
  decision, output, scratch, and corrected SDC1/Hydra products are absent.
  Every review authorization flag is false.

**Validation:** four focused freeze tests pass. They verify the immutable
implementation commit/tree, every live file hash, exact wrapper decision
fields, all-false authorization boundary, and absent replay/public outputs.

**Decision:** replacement identity review `5e5bf04a...` is ready for a separate
named approval authorizing exactly one complete 800-compact/1,600-Continuum
cumulative replay. It does not authorize viewed public-data execution, a new
campaign, qualification, tuning, rescoring, cutover, or release.

**Immediate next step:** request named replay approval bound to review
`5e5bf04a...`, candidate `b1d59e5...`, correction configuration `65c8876d...`,
wrapper `b4d02784...`, and baseline `a45303df...`. Do not execute beforehand.

## 2026-08-26 — Authorize the replacement correction replay

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Gemma Danks approved exactly one complete two-worker 800-compact/1,600-
  Continuum cumulative replay bound to replacement review `5e5bf04a...`,
  candidate `b1d59e5...`, complete correction configuration `65c8876d...`,
  wrapper `b4d02784...`, and closed baseline `a45303df...`.
- The execution decision retains the exact approval and binds every wrapper-
  checked source, dependency, population, historical program, contract,
  output, scratch, and worker identity. Viewed SDC1/Hydra execution, another
  campaign, fresh qualification, optimization, tuning, rescoring, cutover,
  and release all remain false.
- The decision itself creates no scratch, candidate product, replay ledger, or
  corrected viewed-public result. A clean immutable-checkout no-write
  preflight is still required before starting the single authorized process.

**Immediate next step:** validate and commit the authorization record, then
run the complete no-write preflight. Start the single replay only if every
identity remains exact and both write-once paths remain absent.

## 2026-08-26 — Stop the correction replay before reference science

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Committed authorization as `300526e...`. The immutable no-write preflight
  passed candidate source `2de6564e...`, configuration `65c8876d...`, review
  `5e5bf04a...`, wrapper `b4d02784...`, closed evidence, clean-checkout, and
  absent-output checks. Decision `addacf7a...` bound the exact invocation.
- The one authorized process then created the scratch directory and failed
  before loading reconstructed inputs or reference results, constructing a
  candidate task, or producing a candidate product. The scratch directory has
  zero entries and the atomic ledger remains absent; no scientific outcome is
  available.
- Root cause is a producer/consumer provenance collision. Historical viewed-
  reference decision `b35f4a81...` binds reconstruction producer source
  `b4176ce3...`. Its frozen loader hashes the active repository instead of a
  separately bound producer identity, so it rejects the intentionally changed
  corrected candidate source `2de6564e...` as “viewed recovery candidate
  source changed.”
- The wrapper preflight checksum-verified the terminal reconstruction record
  but did not execute the complete composed verifier. That left the collision
  latent until process start. Failure record
  `phase-5-public-finder-correction-cumulative-replay-execution-failure.json`
  preserves the exact execution, verifier, absence, and authorization state.
- The execution authorization is consumed and cannot transfer to a changed
  wrapper. Hourly monitoring was deleted. No rerun, viewed SDC1/Hydra
  execution, campaign, qualification, tuning, rescoring, cutover, or release
  is authorized.

**Decision:** correct the reference-consumer provenance seam only after a new
pre-review and named implementation approval. Preserve every reconstruction
byte, candidate science choice, compiler/evaluator, gate, and closed baseline.
Freeze replacement identities and require a separate new replay approval.

**Repair pre-review:** non-executable review `d169ab9a...` binds failure record
`37836fea...` and recommends only a reference-consumer provenance seam. The
historical producer identity may be substituted for the two frozen verifier
source checks, while every candidate path must continue to observe corrected
source `2de6564e...`. It requires fixture coverage for both verifier layers and
a complete no-write verification of the sealed reconstruction before freezing
new executable identities. A new scratch path is prospective; the closed empty
failure scratch is neither reused nor deleted. Every authorization flag is
false.

**Immediate next step:** obtain named implementation approval bound to pre-
review `d169ab9a...`. Do not implement, freeze, or rerun it beforehand.

## 2026-08-26 — Implement the reference-consumer provenance repair

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Recorded Gemma Danks's approval in decision `76477b31...`, bound to
  non-executable pre-review `d169ab9a...` and failure record `37836fea...`.
  It authorizes only implementation, complete no-write reference validation,
  and replacement identity freezing; another replay and every later lifecycle
  action remain false.
- Added the missing producer/consumer seam to wrapper `b2240e55...`.
  Historical source `b4176ce3...` is visible only to the two frozen checks
  that validate who produced the sealed reference reconstruction. Corrected
  candidate revision `b1d59e5...` and source `2de6564e...` remain active for
  candidate generation, product provenance, compilation, and evaluation.
- Complete reconstructed-reference verification now runs after exact
  authorization and common identity validation but before the historical main
  can create scratch. The historical main receives only that already verified
  in-memory view; all other `runpy` consumers are delegated unchanged.
- The first immutable no-write attempt from `9a93a41...` failed immediately at
  the historical source guard, before any reference product was opened and
  without creating output or scratch. The cause was `runpy.run_path` returning
  a namespace copy while functions retain a different globals dictionary.
  The seam now patches the verifier function's actual globals; the regression
  fixture reproduces that separation instead of sharing one dictionary.
- Future execution must use a new decision, new identity review, and new
  scratch path. The consumed decision and closed empty failure scratch cannot
  authorize or seed a later replay.

**Validation:** the required test-first regression failed because the scoped
producer seam did not exist. After implementation, 34 focused wrapper and
governance tests and 91 broader correction/recovery tests pass; focused Ruff
and Pyright pass. `just coverage` passes 1,838 tests with four expected xfails
and 95.07% total branch-aware coverage. No scientific products or public
finder evidence were executed.

**Immediate next step:** finish the normal handoff checks and commit the
repair, then run the approved complete no-write verification from that clean
immutable commit. Do not freeze executable identities or run a replay first.

## 2026-08-26 — Stop at deleted reconstructed-reference evidence

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Committed the provenance repair in `9a93a41...` and corrected the real
  `runpy` globals seam in `c5fa6ee...`. The first immutable check stopped at
  the source guard; the corrected check passed both historical-producer and
  corrected-consumer source identities.
- Complete no-write verification then stopped before verifying its first
  product because `viewed-reference-reconstruction/inputs` and `results` are
  absent. Their permanent deletion was explicitly approved and recorded in
  cleanup commit `fe92da1...`; only the small terminal, request, open-state,
  and progress records were retained. The cumulative replay requires those
  per-image bundles and reference catalogues and cannot validly substitute the
  aggregate closed ledger.
- Failure record `2ae63e0a...` binds both immutable attempts, repair commit and
  wrapper, retained evidence, approved cleanup, and absent output/scratch. It
  records zero candidate products, zero verified reference products, and no
  scientific outcome.
- Non-executable pre-review `e3abbe9c...` recommends rebuilding the evidence
  from historical producer checkout `a000db4...` and the exact retained four
  runtime images: 2,400 inputs, 9,600 PyBDSF/Aegean runs, and zero candidate
  runs. It requires the program's 120-GiB storage floor and a new write-once
  terminal namespace; the retained historical seal must not be overwritten.
  The host currently has about 53 GiB available.

**Decision:** do not freeze replay identities against an incomplete evidence
directory and do not reconstruct under the provenance-repair approval. The
repair approval covers no-write verification and identity freezing only; a
full reference reconstruction is a separate substantial execution requiring
named approval. Viewed SDC1/Hydra, replay, campaign, qualification, tuning,
rescoring, cutover, and release remain unauthorized.

**Validation:** 37 focused boundary, wrapper, and governance tests pass. The
corrected production seam passes focused Ruff and Pyright, full coverage
(1,838 passed, four expected xfails, 95.07%), `just check` (1,683 passed, four
expected xfails), strict docs, and final pre-commit before commit. The new
records add no scientific execution path.

**Immediate next step:** obtain named approval bound to reconstruction pre-
review `e3abbe9c...`, then provide at least 120 GiB host headroom before its
complete no-write preflight. Do not start it, the replay, or public execution
before those conditions are met.

## 2026-08-26 — Authorize one exact reference reconstruction

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Gemma Danks approved one reconstruction bound to non-executable pre-review
  `e3abbe9c...`, historical producer commit `a000db4...`, reconstruction
  program `81faad48...`, historical decision `b35f4a81...`, and all four
  retained runtime identities. Decision `cc22c773...` retains the exact
  approval and limits execution to 2,400 inputs, 9,600 PyBDSF/Aegean reference
  runs, and zero candidate runs in the new write-once namespace.
- The authorization requires a complete no-write identity/runtime/path
  preflight and at least 120 GiB host headroom. After deleting the closed final
  qualification raw inputs/results, the host currently reports only about
  76 GiB available, so the storage condition is not yet met.
- The cumulative replay, viewed SDC1/Hydra execution, another campaign, fresh
  qualification, optimization, tuning, rescoring, cutover, and release remain
  explicitly false.

**Immediate next step:** validate and commit the authorization, create the
clean historical checkout, and run the complete no-write preflight. Do not
create staging or execute reconstruction unless the observed host headroom is
at least 120 GiB and every identity remains exact.

## 2026-08-26 — Stop reconstruction preflight at the storage gate

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- Committed authorization as `cce40c7...` and created a clean detached
  historical producer checkout at exact commit `a000db4...` / tree
  `fd4bec6a...`. Program `81faad48...` and decision `b35f4a81...` match the
  approved identities.
- The committed `--preflight-only` path verified the retained 2,400/9,600
  population, all four exact Podman image identities, and absent output and
  staging. It then stopped at the governed storage check: 75.7465 GiB was
  available against the required 120 GiB, a 44.2535-GiB shortfall.
- No input materialization, reference runner, candidate run, staging
  directory, or terminal output was started. The single authorized
  reconstruction remains unconsumed. Compact preflight record SHA-256 is
  `a2e752dc...`.

**Decision:** do not weaken the declared storage floor or start a partial
reconstruction. Retain the immutable checkout and exact images, free at least
44.2535 GiB more, then repeat the complete no-write preflight before using the
single execution authorization.

**Immediate next step:** obtain sufficient host headroom without pruning the
four exact runtime images or required public-comparison population, then rerun
the no-write preflight. The cumulative replay and later Phase 5 actions remain
closed.

## 2026-08-27 — Rebuild and verify correction reference evidence

**Plan phase:** Phase 5, Step 6 — public/challenge evidence

- The complete no-write reconstruction preflight passed from exact historical
  producer commit `a000db4...` after host headroom reached 120.21 GiB. The
  single authorized process then sealed all 2,400 inputs and 9,600 PyBDSF /
  Aegean reference runs, with zero candidate runs, as terminal `48209eae...`.
- An independent full verifier confirmed both identity sets, all per-product
  provenance, producer source `b4176ce3...`, the four retained runtime images,
  and the exact 2,400/9,600 counts. Commit `046df24...` records the terminal
  review and updates only the corrected replay consumer's reference binding.
- The first immutable consumer invocation supplied the predecessor baseline
  filename and failed closed at baseline identity validation before reference
  access or scratch creation. The corrected exact invocation used closed
  baseline `a45303df...` and passed complete no-write verification from commit
  `046df24...`; replay scratch and output remain absent.
- Non-executable review `c5924600...`, committed in `2ef6532...`, freezes
  candidate `b1d59e5...`, source `2de6564e...`, configuration `65c8876d...`,
  wrapper `04a3a543...`, terminal `48209eae...`, baseline `a45303df...`, all
  compiler/evaluator/contracts, two workers, and the write-once output paths.
  Every execution and later-lifecycle authorization remains false.

**Validation:** the complete terminal verifier and corrected consumer
verification each passed 2,400 inputs and 9,600 references. Focused suites
pass 37 tests. Scoped push-stage hooks pass Ruff, formatting, JSON, spelling,
Pyright, strict docs, and the 1,670-test quick lane. The repository-wide hook
was also attempted in a disposable checkout and was blocked only by unrelated
pre-existing notebook Ruff findings; no notebook changes were retained.

**Immediate next step:** obtain one named approval bound exactly to review
`c5924600...`. Only then run the single two-worker cumulative replay and require
no like-semantics regression before any viewed public execution is reopened.

## 2026-08-27 — Refresh the staged source-finder demonstration

**Plan phase:** Phase 5, implementation communication

- Expanded the Marimo compact scene to retain the governed threshold ladder,
  a true tile-corner blend, adaptive-RMS source, edge source, and invalid
  pixels instead of displaying only high-confidence interior objects.
- Replaced the isolated one-object multiscale display with four deterministic
  direct, diffuse, edge, and invalid-clipped cases executed through the bounded
  four-tile Phase 5 stage and its persisted Zarr products.
- Added explicit matched/B3 evidence, all three significant-scale masks, and
  dedicated persistent A trous and retained original-pixel support figures so
  the final support products remain visible in Marimo app view.

**Validation:** focused Ruff and strict Marimo checks pass. A headless Marimo
HTML export completed successfully and contains the separate A trous,
retained-support, and three B3-level displays with no traceback or Marimo error
marker. The executed compact output reconciles five islands into six regions
with no deferrals, and all four labeled residual cases have retained support.

## 2026-08-27 — Add an astronomer-facing source-finder workbench

**Plan phase:** Phase 5, implementation communication

- Added a Marimo workbench for research and telescope-commissioning use of the
  implemented bounded compact-source stages on user-supplied FITS images.
- Added an offline synthetic commissioning image and opt-in official LoTSS DR2
  cutouts of 3C 295 and M51, with provenance and citation guidance kept beside
  the examples rather than committing generated or survey FITS products.
- Exposed documented detection, island, RMS, adaptive bright-source, deblend,
  and tiling controls; each run preserves its configuration, Zarr diagnostics,
  and Rapthor-compatible FITS catalogue in a fresh output directory.
- Grounded the workflow and diagnostic advice in established source-finder
  literature and PyBDSF, Aegean, and LoTSS operational documentation. The
  notebook explicitly distinguishes implemented compact-source behavior from
  forced photometry, cross-matching, and validated diffuse-emission analysis.

**Validation:** not run in this task.

## 2026-08-27 — Add a representative crowded LoTSS field

**Plan phase:** Phase 5, implementation communication

- Added an on-demand 22-arcmin LoTSS DR2 cutout at the public API's example
  position, where the survey-wide mean density implies roughly 100 catalogue
  sources while preserving the distinction between an expectation and a
  matched truth population.
- Added image-specific guidance for previewing the complete field and assessing
  thresholds, spatial RMS, blends, catalogue matching, completeness, and
  reliability.

**Validation:** not run in this task.

## 2026-08-27 — Add a 100-source survey field to the workbench

**Plan phase:** Phase 5, implementation communication

- Added a deterministic offline 1,024-square-pixel field with exactly 100
  injected sources spanning 4 to 80 sigma, five close pairs, six extended
  sources, spatially varying noise, and an invalid region.
- Generalized the synthetic reference-mask comparison across the commissioning
  and survey examples and added injected/fitted population counts with an
  explicit warning that count equality is not a completeness measurement.
- Added a crowded-survey preset and population-level guidance for completeness,
  reliability, flux recovery, astrometry, blends, spatial systematics, and
  runtime assessment.

**Validation:** not run in this task.

## 2026-08-27 — Add multiscale support to the astronomer workbench

**Plan phase:** Phase 5, implementation communication

- Added an opt-in bounded Phase 5 multiscale run over the workbench image and
  its compact-stage background/RMS products, using a beam sampled through the
  image WCS at its centre and the exact derived filter halo.
- Exposed the promoted multiscale seed, island, valid-support, beam-area, and
  executor-batch controls, and preserved them in each run configuration.
- Added direct/combined/B3 evidence, all three significant-scale masks,
  adjacent-scale reconstruction support, retained original-pixel support, and
  stable topology counts to the interactive diagnostics.
- Kept the scientific boundary explicit: these products support multiscale
  exploration, but this notebook does not claim a final combined
  compact-plus-extended catalogue without model subtraction, association,
  extended measurement, and publication composition.

**Validation:** not run in this task.

## 2026-08-27 - Refresh the public comparison with current Hebog

**Plan phase:** Phase 5, implementation communication

- Ran the current workspace Hebog implementation over the same ten sealed
  public inputs, serially and host-locally, without starting a container or
  writing to either predecessor campaign.
- Bound the derived campaign to source tree
  `2de6564e78f1a3664dd3fb18f696c747bfc3350fdd894164c4fafb07528d1ba9`
  and unchanged scientific configuration
  `0e5dde51dfd2df84cdf71c3da34449b96c6999f517d781e1aaaec48ebb485a94`.
- Sealed 10 of 10 current-Hebog results under
  `benchmark-results/phase-5/current-public-hebog-comparison`, recursively
  retaining the released PyBDSF and Aegean reference products for notebook
  comparison.
- Changed the campaign comparison notebook default to the new nested derived
  campaign, where current Hebog replaces the historical Hebog overlay.
- Kept `scientific_claims_authorized` false; the refresh supports qualitative
  inspection and follow-up matching, not a qualification claim.

**Validation:** the no-write preflight verified all ten input and historical
result bindings. The end-to-end serial run sealed 10 successful current-Hebog
cases and confirmed that the source-tree identity did not change during
execution. No separate test or notebook-validation command was run.

## 2026-08-27 — Add fail-closed Phase 5 readiness records

**Plan phase:** Phase 5, terminal readiness governance

- Added a two-stage readiness library and write-once command. Preparation
  verifies exact generator, contract, evidence, source, configuration, and
  terminal-field identities; absent evidence becomes a named blocker, while a
  present malformed, failing, or changed artifact aborts the review packet.
- Added the machine readiness contract and independent radio-astronomy and
  engineering review questions. The contract preserves the terminal public
  failure as binding context and requires a fresh corrected-candidate held-out
  qualification rather than relabelling or rescoring viewed evidence.
- Finalization rebuilds the exact packet from live evidence and accepts only
  two exact packet-bound acceptance records with no blocking findings. Phase 5
  completion keeps campaign, qualification, tuning, rescoring, optimization,
  cutover, release, and Phase 6 execution unauthorized.
- The repository dry run now fails closed on the terminal corrected cumulative
  ledger's `all_required_endpoints_pass=false`; it does not misclassify the
  failing result as missing evidence and writes no draft or terminal readiness
  artifact. Corrected-candidate held-out qualification and the restricted
  Rapthor profile also remain absent downstream.

**Validation:** 92 focused readiness and correction-governance tests passed;
Ruff format and lint passed for every changed Python file; Pyright reported
zero errors; strict documentation build passed; and the live terminal audit
raised the exact binding cumulative-endpoint mismatch without writing a
packet. Full branch-aware coverage passed 1,883 tests with 44 deselected and
four expected failures at 94.97% total coverage.

## 2026-08-27 — Close the corrected cumulative replay as a failure

**Plan phase:** Phase 5, public-finder correction regression gate

- The single named-approved replay exited successfully after all 2,400
  candidate products and atomically published ledger SHA-256
  `1ac6deb24e4bfc1928318c95437d45acac6ac1f94621b53d45175e0f41bd9797`.
  The ledger binds candidate `b1d59e5aaf778a5fed4ea662afeba2ee100424ff`,
  source tree `2de6564e78f1a3664dd3fb18f696c747bfc3350fdd894164c4fafb07528d1ba9`,
  configuration `65c8876dcdb484bd5a82b3520e065ea6bf33cf24cfdd33b592c6c859231c62f0`,
  reconstruction `48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2`,
  and closed baseline `a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9`.
- Compact remains `pass` with zero like-semantics regressions. Continuum is
  terminally `fail`: 89 endpoints pass, 44 fail, 10 are underpowered, and 37
  regress against the closed like-semantics baseline. Therefore
  `cumulative_science_regression_ready=false`, all-required-endpoints is false,
  and fresh campaign freeze remains closed.
- Science was interpreted before power. Completeness passes all 16 strata and
  merge fraction passes all 16, but overall reliability is 0.62563, duplicate
  fraction is 0.25179, split fraction is 0.25295, integrated-flux p95 error is
  0.79260, and position p95 error is 4.20355 beams. The 37 regressions comprise
  12 split, 10 duplicate, four median-flux, four position-tail, three x-offset,
  three y-offset, and one reliability endpoint. The 10 underpowered endpoints
  reflect observed paired variance above the planning bound and cannot
  compensate for the absolute failures or regressions.
- Code-to-evidence review identifies a source-composition defect rather than a
  sensitivity or merge failure. The correction deliberately preserves every
  accepted original-residual connected component as an owner, assigns nearby
  reconstructed support to that owner, and publishes one catalogue row per
  owner. It removed the historical connected association union but did not add
  the separately modelled object-association/grouping layer. Multi-component
  extended truths are consequently published as fragments, explaining the
  simultaneous perfect completeness, poor reliability, high split/duplicate
  fractions, divided flux, and long position tails.
- No replay, viewed-data execution, campaign, qualification, tuning, rescoring,
  cutover, or release was started or authorized. The next scientific task is
  a prospective pre-review of bounded component-to-source association and
  explicit component-versus-source catalogue semantics on analytic and
  injected truth; the failing and underpowered evidence must not be tuned.

**Validation:** Exact candidate, source, configuration, reconstruction,
baseline, wrapper, review, and execution-decision identities were verified.
The focused replay/readiness suite passed 92 tests, and the stale historical
absence assertions were corrected to validate their recorded freeze-time
state rather than requiring a later authorized write-once output to remain
absent forever.

## 2026-08-27 - Add an isolated LoTSS observational comparison lane

**Plan phase:** Phase 5, implementation communication

- Added a prospective LoTSS DR2 campaign with one wide 90-arcmin RA-13 field,
  the 3C 295 bright-source field, and the M51 complex-emission field.
- Kept acquisition, current-Hebog execution, and networkless released PyBDSF
  and Aegean execution isolated from the sealed SDC1/Hydra campaigns.
- Added an aggregate notebook view that links the ten existing public cases
  and three LoTSS cases without copying or modifying their science products.
- Materialized the aggregate with in-root hard links rather than escaping
  directory symlinks, preserving storage efficiency while satisfying the
  notebook's fail-closed campaign path boundary.
- Kept `scientific_claims_authorized` false. LoTSS is observational diagnostic
  evidence; its PyBDSF-derived catalogue and cross-finder agreement are not
  independent truth.
- Preserved circular LoTSS beams across FITS WCS serialization by equalizing
  pixel-space axes only when their inversion is within `1e-12` relative
  round-off; materially inverted beam metadata still fails closed.
- Preserved the source spectral WCS as scalar FITS `RESTFRQ` and `RESTFREQ`
  cards when reducing LoTSS cutouts to two dimensions. The latter spelling is
  required by the pinned released PyBDSF reader.
- Added an explicit observational Aegean import policy that excludes islands
  with non-finite or non-positive integrated flux and their components. Every
  run retains a JSON exclusion report; duplicate identities, missing islands,
  and inconsistent component counts continue to fail closed. The policy is
  applied consistently during execution and public-product normalization.

**Validation:** not run in this task. Campaign execution evidence is recorded
by the generated checksum-bound manifests under `benchmark-results/phase-5/`.

## 2026-08-28 - Add revisioned all-public Hebog notebook refreshes

**Plan phase:** Phase 5, implementation communication

- Added one source-identified command that reruns Hebog over all frozen SDC1,
  Hydra, and LoTSS inputs while reusing sealed PyBDSF and Aegean references.
- Made completed refreshes immutable and discoverable through a generated
  history registry plus a stable `latest` notebook pointer.
- Added a synchronized notebook section for comparing catalogue markers and
  actual Rapthor support masks from multiple Hebog revisions side by side.
- Preserved the distinction between public observational diagnostics and
  injected truth; refreshes remain unauthorized for qualification claims.

**Validation:** the generated campaign manifests provide execution evidence;
no separate test or Marimo-validation command was run in this task.

## 2026-08-27 — Pre-review public-finder source association

**Plan phase:** Phase 5, public-finder correction regression gate

- Added non-executable scientific pre-review `9af42348...`, bound to terminal
  failed ledger `1ac6deb2...`, candidate `b1d59e5...`, source
  `2de6564e...`, configuration `65c8876d...`, reconstructed reference
  `48209eae...`, and closed baseline `a45303df...`.
- Distinguished immutable detection components, binding image-domain
  catalogue sources, and out-of-scope astrophysical objects. The prospective
  graph requires undilated shared support, existing-threshold intensity
  continuity, directional-FWHM proximity, and deterministic complete-link
  grouping; ambiguous, distance-only, or transitive-only associations remain
  separate.
- Froze component partition, pixel ownership, flux conservation, identity
  invariance, and zero-false-association gates. Source rows may aggregate only
  existing exclusive component measurements; thresholds, background/RMS,
  support recovery, apertures, calibration, astrometry, and shape estimators
  cannot change in the same repair.
- Bound adversarial analytic and execution-invariance fixtures and explicitly
  forbade terminal replay products, viewed SDC1/Hydra products, and reference
  finder catalogues as implementation inputs. No implementation, replay,
  viewed execution, campaign, qualification, tuning, rescoring, cutover, or
  release was authorized or started.

**Validation:** 52 focused pre-review, correction, and readiness tests passed;
Ruff format and lint passed for the new test; JSON formatting and spelling
hooks passed on the review packet; strict documentation, Pyright, structural,
YAML, TOML, JSON, and lockfile checks passed. The repository-wide Ruff lane is
blocked by pre-existing unformatted notebook and LoTSS files, and the quick
pytest lane is blocked by the unrelated modified frozen public-finder runner;
neither blocker was changed or staged.

## 2026-08-27 — Implement public-finder source association on fixtures

**Plan phase:** Phase 5, public-finder correction regression gate

- Recorded named implementation decision `6a495fcb...` against exact
  pre-review `9af42348...`; it authorizes fixture-only implementation and a
  non-executable identity freeze, but no scientific execution.
- Added immutable stable component, edge, membership, and graph records.
  Persistent IDs derive from global owner coordinates rather than task-local
  labels. The graph requires a shared undilated parent, an everywhere-valid
  existing-threshold saddle, available component shapes, and directional-FWHM
  proximity. Deterministic complete-link reduction rejects transitive-only
  chains and ambiguous evidence.
- Added binding source-row composition while retaining component diagnostics.
  It sums existing exclusive integrated flux, selects maximum component peak,
  composes centroids in a local tangent plane, and measures the union of exact
  owner support without changing component labels, measurements, thresholds,
  calibration, or shape policy.
- Analytic fixtures cover singleton, broad split, low-saddle, high-dynamic-
  range, directional-filament, disconnected-lobe, invalid-gap, unavailable-
  shape, and bridge-chain cases. Serial and existing-Dask fixtures prove label,
  tile, partition-origin, task-order, and retry invariance. No terminal replay,
  viewed SDC1/Hydra product, or reference catalogue was opened.

**Validation:** 90 focused unit/integration tests pass; the association-only
matrix passes 19 tests with 90.60% branch-aware coverage of the new algorithm
and records. Focused Ruff and Pyright pass, and strict documentation builds.
Repository coverage reaches 94.88% with 1,912 tests passing and four expected
xfails. Its sole failure is the intended fail-closed checksum rejection by the
closed public one-look protocol after the approved program seam changed;
historical recovery and final-qualification contracts remain green. All
unaffected pre-commit hooks pass. Repository-wide format, codespell, notebook,
and quick-pytest hooks remain blocked only by unrelated dirty files and the
same frozen public-protocol checksum guard.

## 2026-08-27 — Freeze non-executable source-association identities

**Plan phase:** Phase 5, public-finder correction regression gate

- Froze identity review `c58eec6e...` against implementation commit
  `26e639a...`, tree `251c44c...`, source tree `34fecf30...`, and complete
  configuration `78dbb230...`. It checksum-binds every implementation and
  fixture artifact plus the exact pre-review and implementation decision.
- Preserved the failed ledger `1ac6deb2...`, reconstructed reference terminal
  `48209eae...`, and closed baseline `a45303df...` as the scientific boundary.
  No terminal replay or viewed product was opened to create the review.
- Recorded that wrapper `04a3a543...` is not executable for this candidate: it
  remains bound to revision `b1d59e5...`, source tree `2de6564e...`, and
  configuration `65c8876d...`. The replacement ledger and all corrected viewed
  products are absent. Every authorization flag is false.
- The next governed task is a prospective replay-composition pre-review. It
  cannot execute until its implementation is separately approved, exact
  executable identities are frozen, and a later named replay approval is
  received.

**Validation:** 14 identity/pre-review tests pass; the live source-tree and
canonical configuration hashes match the review; all bound implementation,
historical, and fixture files are byte exact; JSON formatting and focused Ruff
pass. No replay, campaign, qualification, tuning, rescoring, cutover, or
release was started.

## 2026-08-27 — Pre-review source-association replay composition

**Plan phase:** Phase 5, public-finder correction regression gate

- Added non-executable replay-composition pre-review `a2e13e11...` against
  candidate `26e639a...`, source tree `34fecf30...`, configuration
  `78dbb230...`, reconstructed reference terminal `48209eae...`, and closed
  baseline `a45303df...`.
- Preserved the exact 800 compact and 1,600 Continuum population, two workers,
  four-runtime registry, compiler, evaluator, reference verifier, endpoint
  registry, evaluation contract, and historical replay machinery.
- Required one new wrapper and write-once output namespace. The consumed
  correction wrapper `04a3a543...`, ledger `1ac6deb2...`, and execution
  decision `a220249b...` remain immutable and cannot authorize the changed
  candidate.
- Froze fixture/no-write fail-closed requirements for candidate, contract,
  program, runtime, reference, population, gate, scratch, output, and old-
  authorization drift. Every implementation and execution flag remains false;
  no scientific product was opened.

**Validation:** The test-first pre-review initially failed because the governed
record was absent, then all 18 source-association governance tests, focused
Ruff, focused Pyright, JSON formatting, codespell, and strict documentation
passed. Scoped push-stage hooks and all unaffected repository-wide hooks pass.
`just check` remains blocked only by unrelated unformatted notebook and
benchmark files already present in the working tree. No production code
changed, so a new coverage run was not required. The prospective replay output
and scratch namespaces are absent.

## 2026-08-28 — Implement source-association replay wrapper on fixtures

**Plan phase:** Phase 5, public-finder correction regression gate

- Recorded named decision `37931ad3...` against exact replay-composition
  pre-review `a2e13e11...`. It authorizes test-first fixture/no-write wrapper
  implementation, complete reference verification, and non-executable
  identity freezing, but no replay or viewed-data execution.
- Added a new fail-closed wrapper around consumed correction wrapper
  `04a3a543...`. The layer retains historical reference provenance, compact
  generation, compiler/evaluator, endpoints, gates, runtimes, population, and
  atomic publication while binding candidate `26e639a...`, source
  `34fecf30...`, configuration `78dbb230...`, and a new absent write-once
  namespace.
- Spawned workers install the same source-association candidate seams. The
  consumed execution decision fails before loading replay or reference
  machinery, and candidate, program, dependency, reference, runtime, path,
  worker, scratch, or output drift fails closed.
- No scientific product was opened and no replay was started. Clean immutable
  checkout `1b511ed...` passed the complete no-write verification for all
  2,400 inputs and 9,600 reference runs; reconstruction `48209eae...` matched
  and the prospective output and scratch remained absent.
- Froze replacement non-executable identity review `7f7ac272...` over the
  exact implementation commit/tree, wrapper, candidate, configuration,
  reconstructed references, closed baseline, runtimes, programs, paths, and
  two-worker composition. One separate named replay approval remains required.

**Validation:** The wrapper test started red because the implementation
decision and wrapper were absent. All 59 focused wrapper contracts now pass;
focused Ruff and Pyright pass. Direct branch-aware wrapper coverage is 93%.
Wrapper SHA-256 is `bfc1d6d0...`. The clean related identity and reference
suite passes 112 tests; the identity-freeze suite passes 62 tests.

## 2026-08-28 — Authorize source-association cumulative replay

**Plan phase:** Phase 5, public-finder correction regression gate

- Recorded Gemma Danks's exact one-replay approval against identity review
  `7f7ac272...`, candidate `26e639a...`, configuration `78dbb230...`, wrapper
  `bfc1d6d0...`, reconstructed reference `48209eae...`, and closed baseline
  `a45303df...`.
- Execution decision `d806f38e...` authorizes exactly one complete two-worker
  800-compact/1,600-Continuum cumulative replay and its atomic ledger. Viewed
  SDC1/Hydra execution, another campaign, fresh qualification, optimization,
  tuning, rescoring, cutover, and release remain false.
- The ledger and scratch namespaces were absent when authority was recorded;
  no replay was started while freezing this decision.

**Validation:** All 63 focused identity, authorization-boundary, and wrapper
tests pass; focused Ruff and JSON formatting pass.

## 2026-08-28 — Stop the source-association replay at component measurement

**Plan phase:** Phase 5, public-finder correction regression gate

- The first process stopped before candidate execution because the app
  sandbox denied Python's semaphore-capability inspection. The unchanged
  authorized command was retried outside that sandbox, as permitted for the
  same request and output namespace.
- The retry completed 58 of 2,400 candidate products and then failed during
  candidate product generation with `associated source has no measurable
  detection component`. No atomic ledger was written and no partial science
  was inspected. The 7.7-GiB scratch remains preserved for diagnosis.
- Reproduced the exact control-flow defect on a bounded analytic fixture. A
  positive accepted owner can have a non-positive expanded aperture after
  surrounding negative residuals are included. The component catalogue then
  suppressed that owner while the association graph correctly retained it in
  its exact component partition.
- Added a regression that fails on executed candidate `f90dfdf...` for the
  same exception. The prospective repair retains normal expanded-aperture
  photometry, but when only that signed aperture is non-positive it emits an
  explicitly flagged measurement from the positive exact owner support.
  A genuinely non-measurable all-negative owner still fails closed, and the
  audit flags propagate through moment-equivalent component and associated
  source records.

**Decision:** treat this as a candidate measurement-completeness defect, not a
scientific result. The original one-replay authorization is consumed. Do not
reuse the old candidate or execution decision, overwrite scratch, publish a
ledger, or restart until the repair is validated and replacement exact
identities receive new named approval.

**Validation:** the new analytic regression fails against immutable executed
source `f90dfdf...` and passes with the repair. The focused product,
source-association, recovery, and historical-governance suite passes 73 tests;
focused Ruff and Pyright pass. After repairing stale live-file assumptions in
historical governance checks and aligning the Ruff hook with the locked
development version, full branch-aware coverage passes 1,986 tests at 94.87%.
`just check` passes 1,829 selected tests, strict documentation and Marimo
validation pass, and the complete push-stage `just pre-commit` suite passes
without modifying files.

**Immediate next step:** commit the reviewed repair and repository-check
repairs coherently without mixing unrelated notebook-refresh work, then freeze
replacement non-executable identities without starting another replay.

## 2026-08-28 — Condense the Phase 5 closure plan

**Plan phase:** Phase 5, closure governance

- Replaced completed recovery, campaign, correction, and incident chronology
  in the delivery plan with a durable evidence table; detailed chronology
  remains in this log and exact identities remain in machine contracts.
- Made the current blocker explicit: the measurement-completeness repair at
  `6184a32...` has fixture evidence but no frozen replacement replay identity,
  current execution authority, terminal cumulative ledger, or fresh held-out
  qualification.
- Reduced Phase 5 closure to six ordered gates: freeze the repaired
  composition and prospective readiness identities; obtain approval and pass
  one cumulative replay; qualify that exact candidate on fresh held-out data;
  complete the restricted Rapthor profile; confirm final engineering evidence;
  and obtain independent radio-astronomy and engineering acceptance before
  write-once readiness publication.
- Identified that the frozen readiness contract still names superseded
  candidate `b1d59e5...`, configuration `65c8876d...`, and the old ledger
  path. It must be updated prospectively before final evidence is opened.
- Preserved the consumed-authorization, write-once, no-tuning, no-rescoring,
  and no-cutover boundaries. No replay, qualification, public campaign, or
  later lifecycle action was authorized or started.

**Immediate next step:** freeze a new non-executable cumulative-replay and
readiness composition for `6184a32...`; seek separate exact replay approval
only after fixture and complete no-write verification pass.

## 2026-08-28 — Pre-review the measurement-repair replay composition

**Plan phase:** Phase 5, closure gate 1

- Confirmed that the consumed source-association wrapper and execution
  decision bind candidate `26e639a...` exactly and cannot authorize repair
  commit `6184a32...` or a readiness-contract rewrite.
- Added pre-review `7687839f...`, binding candidate source tree
  `517d56e1...`, unchanged configuration `78dbb230...`, repaired
  `products.py` SHA `a3c53daa...`, reconstructed references `48209eae...`,
  and closed baseline `a45303df...`.
- Required a new minimal wrapper, ledger, and scratch namespace; prohibited
  reuse of the 58 old candidate products or any consumed wrapper, decision,
  scratch, or output as authority.
- Prospectively specified replacement cumulative and future held-out fields
  for the readiness contract, which currently binds superseded candidate
  `b1d59e5...`. Readiness rebinding must precede replay rather than follow a
  result.
- Left implementation, no-write verification, identity freezing, cumulative
  replay, viewed-data execution, qualification, tuning, rescoring, cutover,
  and release unauthorized.

**Validation:** the four contract tests first failed because the pre-review
was absent, then passed after it was added. Focused Ruff and canonical JSON
formatting pass. No scientific product was opened and no scratch or output was
created.

**Immediate next step:** obtain named approval of exact pre-review
`7687839f...` for wrapper/readiness implementation, fixture/no-write
validation, and non-executable identity freezing only. A cumulative replay
still requires a later exact identity review and separate named approval.

## 2026-08-28 — Implement the approved measurement-repair replay composition

**Plan phase:** Phase 5, closure gate 1

- Recorded Gemma Danks's exact approval of pre-review `7687839f...` for
  wrapper/readiness implementation, fixture and complete no-write validation,
  and non-executable identity freezing only.
- Added a minimal replacement wrapper over consumed source-association wrapper
  `bfc1d6d0...`. It rebinds candidate `6184a32...`, source tree
  `517d56e1...`, repaired `products.py` `a3c53daa...`, unchanged configuration
  `78dbb230...`, and new write-once output/scratch namespaces while retaining
  the consumed compact, compiler, evaluator, reference, endpoint, gate, and
  two-worker seams.
- Prospectively rebound the frozen readiness contract to the same final
  candidate and the replacement cumulative-ledger and future held-out
  qualification paths before either result exists.
- Implementation decision `b9d48850...` leaves cumulative replay, viewed-data
  execution, another campaign, fresh qualification, optimization, tuning,
  rescoring, cutover, and release unauthorized.

**Validation:** the new contracts first failed for the absent wrapper and
decision and stale readiness identities. They now pass 51 focused wrapper,
historical pre-review, and readiness tests. Focused Ruff passes. No replay
scratch/output was created and no viewed scientific product was opened.

**Immediate next step:** validate and commit this implementation boundary,
then run the complete no-write verifier from that clean immutable revision and
freeze the exact non-executable replacement identity review. A separate named
approval remains mandatory before any replay.

## 2026-08-28 — Freeze the measurement-repair replay identities

**Plan phase:** Phase 5, closure gate 1

- Committed the fail-closed replacement replay composition and prospective
  readiness rebind as `9cc00fb...`.
- From that clean revision, completed the authorized no-write verification of
  all 2,400 retained inputs and 9,600 retained reference runs. Candidate
  `6184a32...`, source tree `517d56e1...`, configuration `78dbb230...`,
  reconstruction `48209eae...`, consumed wrapper `bfc1d6d0...`, readiness
  `cef14d01...`, and measurement repair `a3c53daa...` all matched exactly.
- Confirmed the new ledger and scratch namespaces were absent before and after
  verification and that no cumulative replay started.
- Froze non-executable replacement identity review `119ce0f9...`, including
  implementation tree `1bc47b9e...`, wrapper `79e8252c...`, closed baseline
  `a45303df...`, and every prospective replay field. All execution, viewed-data,
  tuning, rescoring, cutover, and release authorizations remain false.

**Validation:** the identity tests first failed because the review was absent,
then all three passed after the exact terminal record was added. The earlier
implementation boundary passed 51 focused tests, full coverage (2,003 passed,
4 xfailed; 94.87%), `just check` (1,846 passed, 4 xfailed), strict docs build,
and clean `just pre-commit`.

**Immediate next step:** obtain separate named approval bound exactly to
identity review `119ce0f9...` for one complete two-worker cumulative replay.
Do not execute it or any later lifecycle step under the implementation
approval.

## 2026-08-28 — Authorize one measurement-repair cumulative replay

**Plan phase:** Phase 5, closure gate 2

- Recorded Gemma Danks's exact approval bound to non-executable identity review
  `119ce0f9...`, candidate `6184a32...`, source tree `517d56e1...`,
  configuration `78dbb230...`, wrapper `79e8252c...`, reconstructed reference
  terminal `48209eae...`, and closed baseline `a45303df...`.
- Added fail-closed execution decision `5ddc524a...`. It authorizes exactly one
  complete two-worker 800-compact/1,600-Continuum replay and its atomic ledger.
- Retained explicit false authorization for viewed SDC1/Hydra execution,
  another campaign, fresh qualification, optimization, tuning, rescoring,
  cutover, and release.

**Validation:** the authorization contract first failed because the decision
was absent, then the identity and wrapper suites passed all 16 tests. The exact
approval, review checksum, expected replay fields, and prohibited-authority
map are checked mechanically.

**Immediate next step:** commit the execution decision, construct an immutable
checkout from that clean revision, revalidate absent output/scratch state, and
start the authorized replay exactly once.

## 2026-08-28 — Repair associated-source evaluation after complete execution

**Plan phase:** Phase 5, closure gate 2

- The authorized measurement-repair process produced all 2,400 candidate
  shards and then failed before atomic ledger publication with
  `Hebog segment island identity is malformed`. The exact complete scratch is
  preserved; no partial ledger or scientific decision exists, and execution
  decision `5ddc524a...` is consumed.
- Root cause was a missing cross-boundary regression: binding
  `source-associated-*` catalogue rows can own several immutable component
  supports, while the closed successor compiler accepted one
  `hebog-segment-N` support per row.
- Added a new evaluation-only adapter that leaves the checksum-bound identity
  producer, matcher, and successor compiler byte-identical. It verifies each
  persisted source digest against the finite native component set, presents a
  bounded synthetic union-label view only to catalogue matching, and retains
  the original component-label plane for split and merge topology.
- Added a completion-only program that hashes every candidate artifact and
  canonical marker, verifies all retained references and the closed baseline,
  forbids candidate submission, and refuses compilation/evaluation until a
  replacement exact identity review and named approval exist.
- Updated the Phase 5 plan and documentation to preserve the failure state,
  consumed authority, reusable complete product set, and remaining
  qualification boundary.

**Validation:** 96 focused legacy and repair tests pass; all 81 frozen protocol
identity tests pass; focused Ruff and Pyright pass; `just coverage` passes with
2,023 tests, 4 expected failures, and 94.80% total coverage. The new adapter is
88% branch-aware covered. No candidate execution, compilation, evaluation, or
scientific result inspection occurred.

**Immediate next step:** finish repository checks and commit this repair
boundary, then run its complete no-write verifier from the clean revision and
freeze a non-executable exact evaluation-repair identity. A separate named
approval is required before the preserved products may be compiled and
evaluated.

## 2026-08-28 — Freeze the evaluation-only repair identity

**Plan phase:** Phase 5, closure gate 2

- Committed the isolated adapter, completion-only program, failure record,
  tests, plan, and documentation as `ea3279d...`; tree `5be72ba4...` leaves
  every historically checksum-bound producer, matcher, and compiler unchanged.
- From that clean revision, ran the complete no-write verifier over all 2,400
  preserved candidate shards and all 9,600 retained reference runs. Every
  marker, declared artifact byte count, artifact SHA-256, candidate identity,
  reference identity, and closed-baseline identity matched.
- Froze candidate product set `dbc317fa...`, completion program `105d7e30...`,
  evaluation adapter `daa8234d...`, historical matcher `75ea063c...`, and
  historical compiler `8e38de3b...` in non-executable review `6a0e79b4...`.
- Confirmed the atomic ledger remains absent and that no candidate execution,
  compilation, evaluation, tuning, rescoring, cutover, or release occurred.

**Validation:** the no-write verifier passed from the clean implementation
commit. The review contract test binds every program path/checksum, the exact
product count and product-set checksum, reference count, absent output, and
false authorization boundary.

**Immediate next step:** obtain separate named approval bound exactly to
review `6a0e79b4...` for one compilation and evaluation of the preserved
product set only. Another replay or candidate submission remains forbidden.

## 2026-08-28 — Authorize preserved-product evaluation completion

**Plan phase:** Phase 5, closure gate 2

- Gemma Danks approved exactly the evaluation-only completion bound to review
  `6a0e79b4...`, product set `dbc317fa...`, completion program `105d7e30...`,
  evaluation adapter `daa8234d...`, reconstructed references `48209eae...`,
  and closed baseline `a45303df...`.
- Recorded decision `46ddfefa...`, which authorizes one compilation and
  evaluation of the 2,400 preserved products. Candidate execution, another
  replay or campaign, viewed SDC1/Hydra execution, fresh qualification,
  tuning, rescoring, cutover, and release remain false.

**Immediate next step:** validate and commit the decision, create an immutable
execution checkout, repeat the complete no-write identity verification there,
and invoke the completion program exactly once.

## 2026-08-29 — Close measurement-repair evaluation as a failure

**Plan phase:** Phase 5, closure gate 2

- Committed exact evaluation-only authority as `2174b0c...`; decision
  `46ddfefa...` binds review `6a0e79b4...`, product set `dbc317fa...`, repair
  programs, reconstructed references `48209eae...`, and closed baseline
  `a45303df...` while forbidding candidate execution and another replay.
- Immutable checkout `2174b0c...` passed the complete no-write preflight over
  all 2,400 candidate products and 9,600 reference runs. The single authorized
  process then exited successfully and atomically published ledger SHA-256
  `6b2aa4deb306e0d7ba8285aae1e18bfb4f4e838b57aecd0497bec990e8a8c842`.
  Ledger provenance exactly binds the approved candidate, source,
  configuration, product set, adapter, references, baseline, decision, and
  execution revision; no candidate run occurred.
- Science was interpreted before power. Compact is `pass` with zero
  like-semantics regressions. Continuum is `fail`: 89 endpoints pass, 44 fail,
  10 are underpowered, and 37 regress against the closed like-semantics
  baseline. Forty-three failures violate absolute limits; mask precision
  passes its 0.85 absolute floor at 0.88406 but fails both paired 0.05 margins.
- Overall completeness is 1.0, merge fraction is 0.0, and mask recall is
  0.91965. Binding failures include reliability 0.62375 against 0.95,
  duplicate fraction 0.25295 against 0.02, split fraction 0.25295 against 0.10,
  integrated-flux p95 error 0.79260 against 0.25, and position p95 error
  4.18028 beams against 0.5. The 37 regressions comprise 12 split, 10
  duplicate, four median-flux, four position-tail, three x-offset, three
  y-offset, and one reliability endpoint.
- Compared with first corrected ledger `1ac6deb2...`, source association
  changed 49 candidate point estimates but no endpoint status. Reliability
  declined from 0.62563 and duplicate fraction increased from 0.25179; split,
  integrated-flux, and mask results are unchanged. The approved adapter's
  source-union catalogue matching therefore did not remove the binding native
  component-topology fragmentation.
- `cumulative_science_regression_ready`, all-required-endpoints,
  fresh-campaign freeze, and every later execution authorization are false.
  The failed ledger is immutable and must not be rescored, tuned, or rerun.

**Validation:** exact provenance and ledger SHA-256 audits passed; 53 focused
evaluation-repair and readiness tests passed. The live readiness prepare check
rejected `all_required_endpoints_pass` and left its output absent. Branch-aware
coverage passed 2,025 tests with 44 deselected and four expected failures at
94.80%; all 27 applicable equivalence tests passed.

**Immediate next step:** stop Phase 5 closure and obtain a new prospective
scientific pre-review. It must decide whether binding split/duplicate semantics
remain native-component topology—requiring an actual segmentation/reconciliation
correction—or become catalogue-source topology under a prospectively revised
protocol. Either path needs fixture-first evidence and independent scientific
review before any new cumulative execution; held-out qualification remains
closed.

## 2026-08-29 — Pre-review terminal source-reconstruction correction

**Plan phase:** Phase 5, closure gate 3

- Completed a prospective scientific and engineering review against immutable
  ledger `6b2aa4de...`, candidate `6184a32...`, product set `dbc317fa...`,
  reconstructed references `48209eae...`, and closed baseline `a45303df...`.
  The review grants no implementation or execution authority and preserves the
  failed ledger without rescoring.
- Accounted for all 44 Continuum failures: one reliability, 18
  duplicate/split topology, 11 integrated-flux, 13 astrometry, and one mask
  precision endpoint. The 10 underpowered endpoints are recorded separately
  and cannot offset the failures or 37 like-semantics regressions.
- The high-confidence primary failure is under-association. The straight-line
  S/N chord, directional-FWHM proximity, and complete-link all-pairs rule
  cannot represent common curved, ring, corner-crossing, or multipeak support.
  The shell population consequently produces the repeated topology, flux, and
  position failures.
- Identified a certain evaluation-semantics defect: catalogue matching uses
  source-union labels, but binding split fraction still uses native component
  degrees. Native fragmentation remains a useful diagnostic, but preserving
  components makes that definition incapable of demonstrating catalogue-source
  reconstruction. Duplicate and reliability already use source rows and still
  fail, so an evaluator-only change is insufficient.
- Identified a second high-confidence source-measurement defect. Binding flux
  sums independently expanded component apertures, and binding position
  averages component centroids; neither measures the associated source once
  on a deduplicated source-owned support. The mask failure is independent:
  nearest-distance support admission has no connectivity requirement. Its
  aggregate causal attribution remains moderate-confidence and must be
  reproduced by analytic fixtures before implementation.
- Recommended a deterministic common-parent multiscale hierarchy using
  undilated support by reusing the existing bounded adjacent-scale overlap
  kernel, source-level disjoint photometry and denoised moments, connected
  reconstructed-support admission, and prospectively separated
  source/component topology metrics. No second graph framework, threshold,
  recovery radius, gate, or margin change is proposed.

**Validation:** nine initial test-first machine-contract checks failed on the
absent review, then passed after it was added; a tenth check binds reuse of the
existing multiscale association seam. The complete contract records every
failed endpoint exactly once and binds the terminal ledger SHA-256.

**Immediate next step:** obtain named approval of exact pre-review
`528f18a6...`. Approval may open only test-first fixture implementation and
non-executable identity freezing; a cumulative replay, viewed-data execution,
qualification, tuning, rescoring, cutover, and release remain forbidden.

## 2026-08-29 — Add the Phase 5 scientific campaign overview

**Plan phase:** Phase 5, evidence communication

- Added an append-only human-readable campaign overview that explains the
  distinction between final qualification, the public SDC1/Hydra development
  campaign, and cumulative regression replays.
- Recorded the latest 800-compact/1,600-Continuum comparison against released
  and pinned-master PyBDSF, including the experimental method, compact pass,
  Continuum failure, all principal point metrics, root-cause summary, and next
  correction boundary.
- Added a required snapshot format and plan instruction so future terminal
  campaigns preserve a comparable scientific summary without replacing or
  rescoring earlier evidence.

**Immediate next step:** use the overview format for the next terminal replay;
the current execution boundary remains named approval of pre-review
`528f18a6...`.

## 2026-08-29 — Implement the approved source-reconstruction correction

**Plan phase:** Phase 5, closure gate 3

- Recorded Gemma Danks's exact approval of pre-review `528f18a6...` in a
  fail-closed implementation decision. It authorizes only fixture-first
  implementation, validation, and non-executable identity freezing.
- Added stable exact-support scale features and a deterministic hierarchy that
  groups immutable detection components only through one unambiguous common
  multiscale parent. Missing or branched lineage stays singleton and is
  explicitly flagged.
- Replaced component-summed binding rows with one measurement on a disjoint
  source-label aperture. Component measurements remain diagnostic, while
  source flux, centroid, shape, and the positive exact-owner fallback are
  evaluated once per catalogue source.
- Restricted reconstructed-mask admission to support in the same valid
  eight-connected component as a direct seed, retaining the existing radius,
  direct ownership, and canonical nearest-seed tie rule.
- Added a prospective in-memory topology evaluator whose binding split/merge,
  reliability, and duplicate metrics use catalogue-source unions. Native
  component split/merge remains a separate diagnostic; closed ledger and
  campaign paths are not accepted.
- Preserved the historical association and evaluator paths for every sealed
  evidence product. No campaign, replay, viewed public data, qualification,
  tuning, rescoring, optimization, cutover, or release occurred.

**Validation:** the test-first contracts initially failed on absent hierarchy,
measurement, and prospective-evaluator seams. The implemented correction now
passes the focused source, multiscale, measurement, evaluator, product, and
Serial/existing-Dask suites, including singleton, three-lobe, shell, filament,
nearby-source, ambiguous-chain, tile-origin, and source-union topology cases.
`just coverage` passes 2,063 tests with 44 deselected and four expected
failures at 94.64%; `just check` passes 1,905 tests with 202 deselected and
four expected failures; all 27 applicable equivalence tests pass; docs and the
complete pre-commit suite pass. Review against `CODE_REVIEW.md` found no
actionable implementation issue. Two historical SHA checks were corrected to
read their review-named Git revisions instead of requiring successor files to
retain obsolete bytes.

**Immediate next step:** finish repository validation and commit the fixture-
only implementation, then freeze the exact candidate and prospective replay
composition and run its complete no-write verifier. A separate named approval
will still be required before one cumulative replay.

## 2026-08-29 — Prepare the non-executable source-reconstruction replay

**Plan phase:** Phase 5, closure gate 3

- Added a prospective replay wrapper over the exact measurement-repair
  composition. It preserves compact products, reconstructed references, the
  closed baseline, thresholds, gates, and historical compiler programs while
  replacing only the Continuum candidate builder and prospective
  catalogue-source topology seam.
- Prospectively rebound the fail-closed Phase 5 readiness contract to candidate
  `42c75f4...`, source tree `1b67c7f6...`, configuration `470e918d...`, and
  new cumulative and held-out result paths before either result exists.
- Kept the composition non-executable: the fixture verifier writes no replay
  state, and the execution entry point requires a separate absent exact
  decision. No replay, campaign, viewed-data execution, qualification, tuning,
  rescoring, optimization, cutover, or release occurred.
- Pinned the historical measurement-repair readiness test to its named
  implementation revision so successor readiness contracts cannot rewrite or
  invalidate the earlier frozen evidence boundary.

**Validation:** focused wrapper, readiness, hierarchy, source-measurement,
topology, and integration contracts pass (78 tests); Ruff and focused Pyright
pass. `just coverage` passes 2,068 tests with 44 deselected and four expected
failures at 94.64%; `just check` passes 1,910 tests with 202 deselected and
four expected failures; all 27 applicable equivalence tests pass; the strict
documentation build and complete pre-commit suite pass. Review against
`CODE_REVIEW.md` found no actionable issue. The clean-revision no-write
verifier is recorded with the exact identity freeze that follows.

**Immediate next step:** commit this prospective composition, run its complete
no-write verifier from the clean revision, and freeze the exact non-executable
identity review. A separate named approval remains mandatory before one
cumulative replay.

## 2026-08-29 — Freeze the source-reconstruction replay identity

**Plan phase:** Phase 5, closure gate 3

- Ran the complete no-write verifier from clean composition revision
  `6d0cceb4...` and tree `0b5f36af...`. It verified all 2,400 inputs and 9,600
  retained reference runs, candidate `42c75f4...`, source tree `1b67c7f6...`,
  configuration `470e918d...`, reconstruction `48209eae...`, closed baseline
  `a45303df...`, readiness `c70c4c32...`, and wrapper `b19c2157...`.
- The verifier returned `status=pass`, `cumulative_replay_started=false`,
  `output_absent=true`, and `scratch_absent=true`. It did not create an output,
  scratch namespace, candidate product, replay, campaign, or scientific result.
- Frozen non-executable identity review `b4eff062...` records the complete
  verifier result and every future execution field. All authorization flags
  remain false, including cumulative replay, viewed-data execution,
  qualification, tuning, rescoring, optimization, cutover, and release.

**Validation:** all nine focused wrapper and identity-review contracts pass;
Ruff and focused Pyright pass; `just check` passes 1,914 tests with 202
deselected and four expected failures; the strict documentation build and
complete pre-commit suite pass. The prior composition commit passed `just
coverage` at 94.64% and all 27 applicable equivalence tests.

**Immediate next step:** obtain a separate named one-replay approval bound to
identity review SHA-256 `b4eff0621a05a98ab3ad3fa29c1bf3b9447a7a4dd2abf38c3aca5b566c548f21`.
Do not execute the replay or any later Phase 5 action before that approval.

## 2026-08-29 — Authorize one source-reconstruction cumulative replay

**Plan phase:** Phase 5, closure gate 3

- Interpreted Gemma Danks's instruction to start the next campaign as approval
  of the exact frozen cumulative replay in review `b4eff062...`, not a new
  viewed SDC1/Hydra campaign. This is the only pending executable step in the
  plan and matches the immediately preceding approval text supplied for review.
- Added execution decision `0d87caf7...`, binding candidate `42c75f4...`,
  source tree `1b67c7f6...`, configuration `470e918d...`, wrapper
  `b19c2157...`, reconstructed references `48209eae...`, closed baseline
  `a45303df...`, two workers, and the exact write-once output and scratch paths.
- The same write-once namespace may be operationally restarted if a process or
  environment error occurs. A scientific identity change, tuning, rescoring,
  viewed-data execution, another campaign, qualification, optimization,
  cutover, or release remains unauthorized.

**Validation:** all nine focused identity and wrapper contracts pass; Ruff and
focused Pyright pass; the decision parses as strict JSON and matches every
field returned by the frozen wrapper. `just check` passes 1,914 tests with 202
deselected and four expected failures; the strict documentation build and the
complete pre-commit suite pass.

**Immediate next step:** validate and commit the decision, create an immutable
execution checkout, start the exact replay once, and confirm healthy progress
before enabling hourly monitoring.

## 2026-08-29 — Repair source-reconstruction terminal evaluation

**Plan phase:** Phase 5, closure gate 3

- The authorized replay at immutable revision `041b8f4...` completed all 2,400
  candidate shards in managed session `61210`; the write-once ledger remained
  absent throughout candidate execution.
- Terminal Continuum compilation then failed before atomic publication. The
  prospective wrapper sent every finder through the Hebog-only source-union
  topology callback. Released and pinned-master PyBDSF rows retain the frozen
  singular `support_label` contract, while associated Hebog rows expose
  `support_labels`; the resulting `AttributeError` occurred before any ledger
  or scientific interpretation.
- Added the missing regression test and a finder-semantics dispatch: unchanged
  and empty reference catalogues use the historical measurement path, only an
  all-associated Hebog catalogue uses prospective source topology, and mixed
  support semantics fail closed.
- Added a completion-only boundary that hashes all 2,400 canonical markers and
  declared artifacts, verifies the exact progress population, forbids candidate
  submission, and records repair provenance in the eventual atomic ledger.
- Recorded the terminal failure, a thorough pre-review, and an implementation
  decision bound to Gemma Danks's explicit authorization to fix operational
  errors and retry. Candidate science, thresholds, photometry, references,
  endpoint policy, gates, and the output path are unchanged.

**Validation:** the new reference-dispatch test first reproduced the exact
`support_labels` failure. The corrected wrapper, prospective topology, and
association-evaluation suites now pass 23 focused tests; Ruff passes.

**Immediate next step:** commit the repair, verify and freeze the exact
preserved product set and repair identities, amend the consumed execution
decision within the user's narrow retry authority, then resume compilation and
evaluation without candidate execution.

## 2026-08-29 — Freeze the source-reconstruction evaluation repair

**Plan phase:** Phase 5, closure gate 3

- Committed the evaluation-only repair as `ef961d5...`; its wrapper identity is
  `3ff495e3...`. No file under `src/hebog/` changed, so candidate revision,
  source tree, configuration, algorithms, and products remain exact.
- Reverified all 9,600 reconstructed reference runs and hashed every declared
  artifact in all 2,400 preserved candidate shards. Product set `0d8c2d0b...`
  is complete, canonical, identity-consistent, and bound to the original
  candidate. The atomic output remains absent.
- Review `cc531cee...` freezes the implementation, failure, product set,
  references, baseline, and no-candidate-execution boundary. It authorizes
  nothing by itself.
- Amended existing decision `659725aa...` under Gemma Danks's exact recorded
  error-fix-and-retry instruction. It opens one compilation and evaluation from
  those verified products only; another replay, candidate run, campaign,
  qualification, tuning, rescoring, optimization, cutover, and release remain
  prohibited.

**Validation:** all 13 wrapper and identity-freeze tests pass after preserving
the original replay review as historical evidence and binding the successor
repair separately. Ruff passes.

**Immediate next step:** commit the exact repair identity and amended decision,
create a clean immutable checkout, run the existing-product-only completion,
and interpret science only after successful atomic ledger publication.

## 2026-08-29 — Close source reconstruction as a scientific failure

**Plan phase:** Phase 5, closure gate 3

- Immutable evaluation revision `66352e7...` completed the approved
  existing-product-only compilation and atomically published
  `cumulative-regression-ledger-public-finder-source-reconstruction.json`,
  SHA-256 `84fbb3a1...`, without candidate submission or product mutation.
- Provenance verification binds candidate `42c75f4...`, source tree
  `1b67c7f6...`, configuration `470e918d...`, verified product set
  `0d8c2d0b...`, evaluation repair `cc531cee...` / `3ff495e3...`, amended
  decision `659725aa...`, reconstructed references `48209eae...`, and closed
  baseline `a45303df...`. The process exited successfully; the result is a
  scientific gate failure, not an operational failure.
- Compact passes with no like-semantics regressions. Continuum records 89
  passes, 44 failures, 10 underpowered endpoints, and 37 like-semantics
  regressions. `cumulative_science_regression_ready`, all-required-endpoints,
  fresh-campaign freeze, fresh-campaign execution, and step-three authority
  are all false; power review is not reached.
- Overall Continuum completeness is 100%, median integrated-flux error is
  5.22%, mask recall is 91.96%, mask IoU is 82.06%, and merge fraction is 0%.
  Reliability is 62.38%, integrated-flux-error p95 is 79.26%, position-error
  p95 is 4.18 beams, and duplicate and split fractions are each 25.29%.
- Against terminal measurement-repair ledger `6b2aa4de...`, all 143 endpoint
  states are unchanged: 89 pass-to-pass, 44 fail-to-fail, and 10
  underpowered-to-underpowered. Forty-eight point estimates changed, but the
  largest absolute change is about `6.6e-7`; duplicate and split topology is
  exactly unchanged. The governed source hierarchy therefore did not
  materially change catalogue membership, so the intended source-level
  measurement and topology correction could not close the fragmentation
  failures.

**Decision:** stop the closure sequence. Do not rerun, tune, rescore, qualify,
profile Rapthor, cut over, or release. Preserve this ledger as terminal
viewed-development regression evidence.

**Immediate next step:** prepare a new prospective scientific/root-cause
pre-review that explains why common-parent hierarchy activation left source
membership unchanged and requires analytic reproduction before freezing any
new correction or requesting another replay.

## 2026-08-29 — Diagnose dormant source-reconstruction activation

**Plan phase:** Phase 5, closure gate 3

- Root-cause pre-review `c1a92bd2...` binds terminal ledger `84fbb3a1...`,
  predecessor `6b2aa4de...`, candidate `42c75f4...`, source tree
  `1b67c7f6...`, configuration `470e918d...`, and verified product set
  `0d8c2d0b...`. It is non-executable.
- Code trace found a semantic composition defect: direct residual-detection
  labels are expanded by seeded support assignment, then only the expanded
  measurement-owner plane is retained and passed to hierarchy attachment.
  `_attached_finest_feature()` marks an owner ambiguous as soon as that
  expanded footprint intersects multiple finest-scale features, so the owner
  becomes a singleton before common-parent convergence is considered.
- A synthetic controlled fixture reproduced the defect without governed or
  viewed data. Expanded measurement labels produced membership sizes `[1, 1]`
  and one ambiguous owner; the same direct-seed labels produced membership
  size `[2]` with no ambiguity under the unique common parent.
- Terminal invariance corroborates dormant membership: all 143 endpoint states,
  overall duplicate and split fractions, reliability, and flux metrics are
  unchanged; the largest point-estimate change is only about `6.51e-7`.
- Existing hierarchy fixtures use one-pixel owners and hand-built scale planes,
  while the composition test mocks both ends of the boundary. No test exercised
  real scale filtering through seeded support, hierarchy, measurement, and the
  topology evaluator.
- The prior disconnected-support explanation is refuted as material on this
  population: connected admission moved mask precision by only `1.79e-7` and
  caused no status transition. Exact-overlap scale shift remains an unproven
  hypothesis; terminal-root overmerge remains a mandatory safety risk.

**Decision:** recommend a bounded fixture-first repair that preserves separate
direct-seed and measurement-owner label planes, evaluates unique nearest
common convergence before declaring ambiguity, and emits compact activation
telemetry. Do not change thresholds, radii, gates, photometry, background/RMS,
or closed evidence.

**Validation:** all 8 review-contract tests pass; the focused hierarchy,
prospective evaluator, and review suite passes 34 tests; `just check` passes
with 1,926 tests passed, 202 deselected, and 4 expected failures; and the
strict documentation build passes. Coverage was not rerun because this review
changes no production behaviour or control flow.

**Immediate next step:** obtain named approval of exact review `c1a92bd2...`
before implementing the fixture-only repair. Another cumulative replay would
still require a later exact identity review and separate approval.

## 2026-08-29 — Isolate the missing source-parent construction

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved exact root-cause review `c1a92bd2...`. Decision
  `8296c4ce...` records fixture-only implementation authority and preserves all
  replay, viewed-data, qualification, tuning, rescoring, optimization,
  cutover, and release prohibitions.
- The mandatory JSON hook normalized key order and exponent formatting in that
  already approved review. Decision `8296c4ce...` binds original bytes
  `c1a92bd2...` at revision `a6a56ff...`, normalized bytes `fe9ca88d...`, and
  their identical canonical JSON digest `25531467...`; no field or value
  changed.
- Added separate immutable direct-seed and recovered measurement-owner planes.
  Hierarchy identity now uses direct owners; masks and source photometry retain
  recovered owners. Multiple finest-feature attachments may proceed only
  through one unambiguous common lineage. Terminal-only coarse bridges remain
  singletons.
- Added compact, array-free hierarchy telemetry covering direct components,
  catalogue sources, membership sizes, attachment ambiguity, convergence,
  per-scale feature counts, and adjacent-scale parent edges. The persisted
  source-association record therefore makes future activation observable.
- Hand-built positive parents, absent/branched convergence, expanded-owner
  separation, terminal-bridge safety, malformed ownership, serial composition,
  and existing-Dask serialization pass 64 focused tests.
- The mandatory real-path analytic shell exposed a second confirmed defect.
  Four direct lobes remain four connected features at scales 1, 2, and 3;
  eight adjacent-scale edges preserve four independent lineages, but no common
  parent exists. The result correctly remains four singleton sources with zero
  convergence. Synthetic-only Gaussian-pair, ring-lobe, and pedestal probes
  likewise either stayed separate at every scale or collapsed before
  hierarchy association.
- Earlier positive tests manually supplied a connected coarse parent. They
  proved reduction of an existing hierarchy but could not prove that the real
  scale products construct that hierarchy. The approved label repair is
  necessary but insufficient, so no replacement candidate or replay identity
  was frozen.
- Non-executable pre-review `b5d89bdc...` recommends a test-first, scale-aware
  parent construction derived from the existing B3-spline filter footprint,
  with exact support retained for measurement, adjacent-scale persistence,
  connected-valid-support admission, and explicit overmerge controls. It adds
  no fitted threshold or campaign-derived radius and authorizes nothing.

**Validation:** focused hierarchy, product, prospective composition, review,
and existing-Dask tests pass 64 tests; Ruff passes on all changed Python files.
Full coverage and handoff validation remain pending.

**Immediate next step:** obtain named approval of exact parent-construction
review `b5d89bdc...` before implementing that design. Replay, candidate
identity freeze, viewed SDC1/Hydra execution, qualification, tuning, rescoring,
cutover, and release remain prohibited.

## 2026-08-29 — Implement scale-aware source-parent construction

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved exact parent-construction pre-review `b5d89bdc...`.
  The implementation decision records fixture-only authority; cumulative
  replay, viewed data, campaign execution, qualification, tuning, rescoring,
  optimization, cutover, and release remain false.
- The mandatory JSON hook later reordered two object fields in that approved
  review. The decision binds original bytes `b5d89bdc...` at revision
  `9e47b789...`, normalized bytes `77669f12...`, and their identical canonical
  JSON digest `f6674e25...`; no field or value changed.
- Exact significant feature support, immutable direct components, recovered
  measurement owners, thresholds, masks, photometry, and every closed ledger
  remain unchanged. The new pure hierarchy transform builds bounded valid
  envelopes from the frozen cumulative B3 radii of 2, 6, and 14 pixels.
- A sweep-line overlap graph admits only cycle-supported sibling groups and
  requires the identical immutable component group at adjacent scales. One
  exact shared feature may corroborate an envelope group at its neighbour.
  Pairs, transitive chains, terminal-only candidates, invalid barriers,
  conflicting groups, and unreviewed scales fail closed.
- Compact array-free diagnostics now count candidates per scale, total
  candidates, accepted persistent parents, and rejected candidates. The real
  four-lobe shell changes from four singleton catalogue sources to one
  four-component source through one parent repeated at scales 2 and 3.
- Real scale-filter three-lobe, shell, and closed curved-filament positives;
  independent-pair, terminal-only, invalid-gap, and transitive-chain
  negatives; label/plane ordering; duplicate retry; and Serial/existing-Dask
  invariance all pass.
- `just coverage` passes 2,110 tests with 4 expected failures and 44
  deselections; branch-aware project coverage is 94.75%. No campaign,
  governed population, or closed scientific output was opened or rescored.
- `just check` passes 1,952 tests with 4 expected failures and 202
  deselections; all 27 frozen equivalence tests pass; and the strict
  documentation build passes. Final review found no unresolved correctness,
  architecture, safety, coverage, or documentation issue.

**Immediate next step:** complete handoff validation and review, commit the
validated implementation locally, then freeze exact non-executable candidate
and replay identities and run their complete no-write verification. A replay
still requires a separate exact approval.

## 2026-08-29 — Compose parent-construction replay boundary

**Plan phase:** Phase 5, closure gate 3

- Committed the validated parent-construction candidate as `5f2b098...` with
  source tree `a7ef1887...` and configuration `88634678...`.
- Added a fail-closed prospective replay wrapper that consumes exact
  source-reconstruction wrapper `3ff495e3...`, overlays only the new candidate
  identity and current Continuum builder, preserves the compact/reference
  composition, and requires a separate identity-review-bound decision before
  execution.
- Prospectively rebound readiness from failed candidate `42c75f4...` to the
  parent-construction candidate and new write-once cumulative and held-out
  qualification namespaces. No prior ledger, campaign, or qualification
  result was changed or accepted for the new candidate.
- The wrapper contract was developed test-first: five tests initially failed
  because the wrapper and readiness binding did not exist; the completed
  wrapper, predecessor, and readiness suites pass 48 tests.

**Terminal identity-freeze result:** composition commit `af7040e...` and tree
`158c6f53...` passed the complete no-write verifier. It identity-checked all
2,400 inputs and 9,600 retained reference runs, retained reference terminal
`48209eae...`, closed baseline `a45303df...`, candidate `5f2b098...`, source
tree `a7ef1887...`, configuration `88634678...`, and wrapper `9bf44c09...`.
The future output and scratch namespaces were absent and
`cumulative_replay_started=false`.

- The final identity, wrapper, predecessor, readiness, and authorization suites
  pass 64 focused tests. `just check` passes 1,962 tests with 202 deselected
  and 4 expected failures, and the strict documentation build passes.

**Decision:** non-executable identity review `e615da00...` freezes the exact
prospective replay composition with every authorization false. Replay
execution now requires a separate named approval bound to that full digest;
viewed execution, campaign execution, qualification, tuning, rescoring,
optimization, cutover, and release remain unauthorized.

**Immediate next step:** obtain the separate exact one-replay approval, or
stop with the corrected candidate fully implemented and identity-frozen.

## 2026-08-29 — Authorize the parent-construction cumulative replay

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved exactly one 800-compact/1,600-Continuum cumulative
  replay bound to non-executable review `e615da00...`.
- Execution decision `78c274cc...` expands the supplied review prefix to its
  already frozen full SHA-256, binds candidate `5f2b098...`, source tree
  `a7ef1887...`, configuration `88634678...`, wrapper `9bf44c09...`, retained
  reference `48209eae...`, closed baseline `a45303df...`, two workers, and the
  exact future output and scratch namespaces.
- The review remains non-executable. The separate decision opens only one
  cumulative replay; campaign or viewed-data execution, qualification,
  tuning, rescoring, optimization, cutover, and release remain false.
- The decision and wrapper authorization contracts pass 11 focused tests.

**Immediate next step:** commit the exact decision, construct a clean immutable
execution checkout, reverify all identities and absent namespaces, then start
the single authorized replay. Treat scientific failure as terminal evidence.

## 2026-08-29 — Repair parent-construction replay delegation

**Plan phase:** Phase 5, closure gate 3

- The first immutable process, session `19750`, stopped during retained-
  reference verification because ignored benchmark evidence was not visible
  inside the worktree. Attaching checksum-identical ignored evidence changed no
  source or science identity, and the complete preflight passed again.
- The resumed process, session `5116`, completed retained-reference verification
  but raised `KeyError: '_load_current_wrapper'` before scratch creation or
  candidate submission. The wrapper descended only once from source
  reconstruction, received the measurement-repair overlay, and treated it as
  source association. No candidate product, partial science, or terminal ledger
  exists.
- The test gap was structural: no-write verification checked identities and
  all 9,600 retained reference runs without resolving executable composition;
  the closed authorization test never entered delegation; and the static-seam
  test mocked away predecessor depth.
- Gemma Danks explicitly instructed: “Please fix the error and restart the
  run.” Repair pre-review `e492110f...` restricts that authority to one
  wrapper-only correction and one unchanged replay restart. Candidate
  `5f2b098...`, source tree `a7ef1887...`, configuration `88634678...`,
  references, baseline, gates, population, workers, output, and scratch remain
  unchanged.
- A red regression test reproduced the exact KeyError. The minimal repair now
  resolves source reconstruction, measurement repair, source association, and
  the frozen replay explicitly through one helper shared by parent and worker
  execution. No-write verification resolves and installs those same seams.

**Validation:** the new authorized-delegation regression failed for the exact
missing `_load_current_wrapper` reason before implementation. The completed
parent-process, worker, no-write, and existing wrapper suite passes eight tests.
`just coverage` passes 2,123 tests with 44 deselected and 4 expected failures;
branch-aware project coverage remains 94.75%. Focused Ruff and Pyright checks
pass. `just check` passes 1,965 tests with 202 deselected and 4 expected
failures, and the strict documentation build passes. The subsequent replacement
identity freeze is recorded below.
- Boundary commit `9d15fd0...` fails closed on a replacement review and
  decision, verifies the consumed original authorization, and binds the full
  expected composition through canonical digest `7a9c19d3...`.
- The complete clean-checkout no-write verifier passed again: all 2,400 inputs,
  9,600 retained reference runs, and executable delegation seams verified;
  candidate execution remained false and scratch/output remained absent.
- Repair review `89327ae5...` freezes wrapper `053fc647...`, unchanged
  candidate science, and the clean `9d15fd0...` boundary. Repair execution
  decision `0349fdc2...` consumes only the explicit fix-and-restart instruction
  and keeps viewed-data execution, campaigns, qualification, optimization,
  tuning, rescoring, cutover, and release false.

**Immediate next step:** commit the replacement review and decision, construct
a clean immutable checkout, reverify the exact repair identity and absent
namespaces, then run the unchanged replay once.

## 2026-08-30 — Diagnose parent-construction evaluation provenance failure

**Plan phase:** Phase 5, closure gate 3

- Repaired replay session `36274` completed all 2,400 candidate shards: 800
  compact and 1,600 Continuum products. The scratch contains exactly 2,400
  progress records and the atomic cumulative ledger is absent.
- Compilation failed on the first associated Continuum catalogue with
  `ValueError: associated source membership cannot be verified`. No compact or
  Continuum decision, gate result, or scientific comparison was published.
- Root cause is semantic and reproducible: source IDs digest canonical pixels
  from the direct-seed label plane, while the evaluator reconstructed component
  IDs from the first pixels of the larger recovered measurement-owner plane.
  Ownership recovery can precede the seed canonical pixel, so the reconstructed
  digest universe is different even though label values remain stable.
- The persistence audit found a second necessary cause: every Continuum shard
  retains only catalogue, recovered labels, and mask. The cumulative writer
  discarded the exact `source_association` record generated in memory, so the
  preserved files cannot prove cryptographic membership without rerunning the
  frozen association composition.
- Added a red recovered-owner fixture, then implemented an explicit
  association-record path that verifies component and source digests, maps
  stable label values onto recovered supports, and requires an exact disjoint
  partition. A new run-aware parent-construction overlay replaces only the
  installed compiler object; both frozen historical compiler modules retain
  their exact approved SHA-256 identities.
- Failure record `phase-5-public-finder-source-hierarchy-parent-construction-
  evaluation-provenance-failure` and repair pre-review
  `phase-5-public-finder-source-hierarchy-parent-construction-association-
  provenance-repair-pre-review` preserve the terminal failure and restrict the
  next execution to sidecar-only reconstruction plus a later evaluation-only
  completion. Existing shards, compact science, candidate configuration,
  references, gates, thresholds, tuning, rescoring, cutover, and release remain
  outside that boundary.
- The completed repair preserves frozen compiler SHA-256 identities
  `ab690dda...` and `b46167de...`; the new sidecar-aware overlay is
  `74d16cc4...` and the reconstruction program is `e8dd80cb...`. Twenty-three
  focused tests pass with 90% branch coverage; `just coverage` passed with
  2,133 tests and 94.70%
  coverage; `just check` passed 1,975 tests; the equivalence lane and strict
  documentation build passed.
- The complete no-write reconstruction preflight then verified the exact 2,400
  preserved products, 9,600 retained reference runs, candidate product set
  `b81cb3d4...`, absent failed ledger, and absent reconstruction namespaces.
  No reconstruction, compilation, evaluation, or scientific access occurred.

**Immediate next step:** finish validation and review of the evaluator repair,
freeze exact non-executable sidecar-reconstruction identities, and obtain a
separate exact execution approval before running the frozen 1,600-Continuum
association composition or compiling the preserved products.

## 2026-08-30 — Freeze parent association sidecar reconstruction

**Plan phase:** Phase 5, closure gate 3

- Local implementation commit `8a3314d` is clean and binds the new evaluator
  overlay `74d16cc4...`, reconstruction program `e8dd80cb...`, implementation
  decision `d15f87e4...`, preserved candidate product set `b81cb3d4...`, and
  unchanged historical compiler identities `ab690dda...` and `b46167de...`.
- Exact non-executable review
  `phase-5-public-finder-source-hierarchy-parent-construction-association-
  provenance-reconstruction-review` has SHA-256 `691eaf8f35f5ff1688c52af6d448e3ba4df704529f6f50072fa6924903a59be4`.
  It limits any later approval to one two-worker reconstruction of the 1,600
  omitted association sidecars, exact byte verification of all regenerated
  candidate products, and retention of sidecar provenance only.
- Reconstruction, compilation, evaluation, candidate execution, viewed-public
  execution, another campaign, qualification, tuning, rescoring, cutover, and
  release remain unauthorized.

**Immediate next step:** obtain one named reconstruction approval bound to
review `691eaf8f...`; only then create the execution decision and run the
write-once sidecar reconstruction. Evaluation-only completion requires a
separate later review and approval after the terminal sidecar identity exists.

## 2026-08-30 — Authorize parent association sidecar reconstruction

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved exactly one two-worker reconstruction bound to review
  `691eaf8f35f5ff1688c52af6d448e3ba4df704529f6f50072fa6924903a59be4`,
  preserved candidate product set `b81cb3d4...`, and reconstruction program
  `e8dd80cb...`.
- The authority covers only reconstruction of 1,600 omitted Continuum
  association sidecars after an unchanged complete no-write preflight. Every
  regenerated catalogue, labels, and mask must match its preserved SHA-256;
  regenerated candidate products are discarded and existing shards remain
  immutable.
- Candidate execution, compilation, evaluation, viewed-public execution,
  another campaign, qualification, tuning, rescoring, cutover, and release
  remain unauthorized.

**Immediate next step:** commit the exact execution decision, create an
immutable execution checkout, reverify all identities and absent namespaces,
then consume the approval exactly once.

## 2026-08-30 — Seal parent association provenance and prepare evaluation

**Plan phase:** Phase 5, closure gate 3

- The authorized reconstruction sealed exactly 1,600 Continuum association
  sidecars. Terminal recovery SHA-256 is `78d43370...`; the ordered association
  product-set identity is `e1f16373...`. All 1,600 canonical completion markers
  bind their sidecars to the exact preserved candidate complete markers, and
  the terminal records no failure.
- Added a completion-only wrapper around the unchanged parent-construction
  composition. It verifies all preserved candidate artifacts and sidecars,
  installs the sidecar-aware compiler only after the frozen recovery seams,
  replaces candidate submission with identity verification, and raises if any
  path attempts candidate generation.
- The complete no-write verifier passed across all 2,400 candidate products,
  1,600 association sidecars, and 9,600 retained reference runs. Candidate
  execution, compilation, and evaluation remained false; the write-once
  cumulative ledger remains absent. Completion program SHA-256 is
  `bde8511a...` before the implementation commit.
- Twelve focused repair and completion tests pass, including byte drift,
  terminal provenance, compiler ordering, and fail-closed authorization
  fixtures. `just coverage` passes 2,139 tests with 44 deselected and 4
  expected failures at 94.70% branch-aware project coverage; `just check`
  passes 1,981 tests with 202 deselected and 4 expected failures; the 27-test
  equivalence lane and strict documentation build pass.

**Immediate next step:** validate and commit the completion program, then
freeze one exact non-executable evaluation identity review. Compilation and
evaluation require a separate named approval bound to that review.

## 2026-08-30 — Freeze parent-construction evaluation completion review

**Plan phase:** Phase 5, closure gate 3

- Completion implementation commit `1ce8dde...` freezes program
  `bde8511a...`, sidecar-aware overlay `74d16cc4...`, unchanged parent wrapper
  `053fc647...`, candidate product set `b81cb3d4...`, association product set
  `e1f16373...`, and reconstruction recovery `78d43370...`.
- Exact non-executable review
  `phase-5-public-finder-source-hierarchy-parent-construction-evaluation-
  completion-review` has SHA-256 `9c2be9a7067973f5fe1d1eff4ecb0d3afcc6517e9c2338ee9e5db580d6a89906`.
  Its verified composition records that all 2,400 candidate products, 1,600
  sidecars, and 9,600 reference runs passed, while candidate execution,
  compilation, evaluation, and output publication all remained false.
- The review grants no execution authority. Candidate execution, another
  replay or campaign, viewed SDC1/Hydra execution, qualification, tuning,
  rescoring, optimization, cutover, and release remain forbidden.

**Immediate next step:** obtain one named approval bound to review
`9c2be9a7...` for a single compilation and evaluation of the preserved
products. Only after that approval may an exact execution decision be created.

## 2026-08-30 — Authorize parent-construction evaluation completion

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved exactly one evaluation-only completion bound to review
  `9c2be9a7...`, candidate product set `b81cb3d4...`, association product set
  `e1f16373...`, completion program `bde8511a...`, and reconstruction recovery
  `78d43370...`.
- The authority covers one compilation and evaluation of the 2,400 preserved
  candidate products against the 1,600 sealed sidecars and retained references,
  with atomic publication to the original absent cumulative-ledger namespace.
- Candidate execution, another replay or campaign, viewed SDC1/Hydra
  execution, qualification, tuning, rescoring, optimization, cutover, and
  release remain unauthorized.

**Immediate next step:** commit the exact execution decision, create a clean
immutable checkout, rerun the complete no-write verification, and consume the
single approval only if every identity remains unchanged.

## 2026-08-30 — Parent evaluation completion stopped before compilation

**Plan phase:** Phase 5, closure gate 3

- Immutable checkout `6f38a2d...` passed the complete no-write verification of
  all 2,400 candidate products, 1,600 association sidecars, and 9,600 retained
  reference runs. Session `11670` then consumed the one evaluation authority.
- The process failed before frozen `main`, compilation, evaluation, or output
  publication with `ValueError: evaluation completion compiler seam changed`.
  The atomic ledger remains absent and candidate execution remained forbidden
  and unstarted.
- Root cause is a completion-wrapper composition error. The active
  source-reconstruction prospective installer is a closure over its predecessor;
  it does not expose `install_recovery_compiler_seams` in its module globals.
  The completion wrapper assumed that global existed. Its fixture supplied a
  synthetic global-backed installer, so the no-write test did not exercise the
  real closure topology.
- The minimal proposed repair is to wrap the active three-argument installer,
  invoke that exact closure first, and then install the sidecar-aware compiler.
  A replacement test must use a closure-backed installer and the complete
  no-write verifier must execute the real composed seam. Products, sidecars,
  references, gates, configuration, and output identity remain unchanged.
- Failure record `phase-5-public-finder-source-hierarchy-parent-construction-
  evaluation-completion-execution-failure` preserves the terminal state. The
  original completion authority is consumed; rerun is forbidden without a new
  exact repair review and named approval.

**Immediate next step:** prepare a test-first evaluation-only repair pre-review
against the recorded failure. Do not compile, evaluate, or rerun under the
consumed authorization.

## 2026-08-30 — Repair the parent evaluation compiler composition

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks explicitly instructed: “Please make the immediate repair (and
  any other necessary fixes) to complete the evaluation. If we need to do
  another recovery campaign then we can decide whether changes to the process
  are needed.” The bounded implementation decision permits one existing-product
  evaluation-only completion and keeps candidate execution, reconstruction,
  campaigns, scientific changes, tuning, rescoring, cutover, and release false.
- Replaced the misleading global-backed installer fixture with the real
  closure-backed three-argument shape. It reproduced the execution failure
  before implementation with `evaluation completion compiler seam changed`.
- The minimal repair wraps and invokes the active prospective installer, then
  installs the parent-construction association evaluator. It no longer inspects
  or mutates another function's module globals.
- The complete no-write verifier now loads the exact frozen compiler and
  prospective campaign view and executes the complete composed installer. It
  verified all 2,400 candidate products, 1,600 association sidecars, and 9,600
  retained reference runs; candidate execution, compilation, evaluation, and
  publication remained false. The candidate product set remains `b81cb3d4...`,
  the association product set remains `e1f16373...`, and the output remains
  absent.
- Twenty-nine focused parent-construction and evaluation tests pass; focused
  Ruff and Pyright checks pass. `just coverage` passes 2,142 tests with 44
  deselected and four expected failures at 94.70% branch-aware project
  coverage; `just check` passes 1,984 tests with 202 deselected and four
  expected failures; all 27 applicable equivalence tests and the strict
  documentation build pass. The exhaustive verifier records
  `compiler_composition_verified=true`.

**Immediate next step:** complete repository validation, commit the repair,
freeze its exact non-executable review and one-use execution decision against
the unchanged evidence, then run compilation and evaluation once from a clean
immutable checkout.

## 2026-08-30 — Freeze the repaired parent evaluation completion

**Plan phase:** Phase 5, closure gate 3

- Repair implementation commit `ae3994e...` freezes completion program
  `044436d5...`, the closure-backed regression, and the exact no-write compiler
  composition check. Review `894f38ff...` binds that program to unchanged
  candidate product set `b81cb3d4...`, association product set `e1f16373...`,
  recovery `78d43370...`, reference terminal `48209eae...`, and closed baseline
  `a45303df...`.
- The clean-commit exhaustive preflight passed again across all 2,400 products,
  1,600 sidecars, and 9,600 reference runs with
  `compiler_composition_verified=true`. Candidate execution, reconstruction,
  compilation, evaluation, and publication remained false.
- One-use repair decision `b0e38b90...` consumes only the explicit instruction
  to complete this evaluation. Candidate execution, another replay or
  campaign, reconstruction, viewed-public execution, qualification, tuning,
  rescoring, optimization, cutover, and release remain false.

**Immediate next step:** commit the repaired review and decision, create a clean
immutable execution checkout, reverify every exact identity and the absent
ledger, then execute compilation and evaluation once.

## 2026-08-30 — Close parent construction as a scientific failure

**Plan phase:** Phase 5, closure gate 3

- The repaired evaluation-only completion exited successfully and atomically
  published
  `cumulative-regression-ledger-public-finder-source-hierarchy-parent-construction.json`,
  SHA-256 `2ece9928eec152cf17f06e9e869d0db9c6a8f0acc2b18ea482aced5e133e6bce`.
  This is a terminal scientific failure rather than an operational failure.
- Provenance verification binds candidate `5f2b098...`, source tree
  `a7ef1887...`, configuration `88634678...`, candidate product set
  `b81cb3d4...`, association product set `e1f16373...`, repaired completion
  program `044436d5...`, repair review `894f38ff...`, execution decision
  `b0e38b90...`, reconstruction recovery `78d43370...`, retained reference
  terminal `48209eae...`, closed baseline `a45303df...`, and immutable
  execution revision `1a3e1c4...`. Candidate execution remained forbidden and
  unstarted during completion.
- Compact passed every binding decision with no like-semantics regression.
  Continuum recorded 89 passes, 44 failures, 10 underpowered endpoints, no
  indeterminate endpoints, and 37 like-semantics regressions. The overall
  failures remain reliability 62.38%, integrated-flux-error p95 79.26%,
  position-error p95 4.18 beams, duplicate and split fractions 25.29%, and
  paired mask-precision non-inferiority despite 88.41% absolute precision.
- All 143 Continuum candidate values, statuses, and reasons are unchanged from
  the preceding source-reconstruction ledger. Parent construction therefore
  did not change governed catalogue-source membership or fragmentation. The
  cumulative readiness, fresh qualification, Rapthor profile, final readiness,
  cutover, and release gates remain closed. This candidate must not be tuned,
  rescored, or rerun.
- Thirty-one focused parent-construction provenance, wrapper, identity, and
  evaluation tests pass. `just coverage` passes 2,144 tests with 44 deselected
  and four expected failures at 94.70% branch-aware project coverage;
  `just check` passes formatting, Ruff, Pyright, doctests, and 1,986 tests with
  202 deselected and four expected failures. All 27 applicable equivalence
  tests and the strict documentation build pass.

**Immediate next step:** stop execution and obtain prospective scientific
review before implementing another source-membership correction. Any future
candidate requires new frozen identities and a new cumulative replay approval.

## 2026-08-30 — Implement the terminal parent correction

**Plan phase:** Phase 5, closure gate 3

- Documented the terminal scientific failure and its retained activation
  evidence in the persistent-support parent-correction reference. All 1,923
  constructed parents first appeared at scale 3, so the previous requirement
  that the same group recur at scale 4 was impossible. The document binds
  terminal ledger `2ece9928...`, records the unchanged Continuum result, and
  keeps replay, viewed-data execution, tuning, rescoring, cutover, and release
  unauthorized.
- Added test-first activation and overmerge controls. The initial red tests
  failed because significant reconstruction support was not composed into
  source reconstruction and a real terminal three-lobe morphology remained
  three singleton sources. A real-scale diagnostic then disproved the broader
  support-as-membership hypothesis: its significant support remained three
  disconnected components, and a connected island is not in general one
  astrophysical source. The implementation was narrowed before acceptance.
- Significant multiscale support is now an explicit, shape- and
  validity-checked input. It can corroborate a non-terminal hierarchy parent
  but cannot create source membership by itself. A newly resolved terminal
  parent is admitted only for a graph cycle of at least three features when
  every terminal feature has an exact child at the preceding scale. Exact
  groups are reconciled whole, and candidate, rejection, and activation counts
  remain compact and array-free.
- Positive shell, three-lobe, and curved-morphology fixtures activate the
  intended terminal path. Connected-support pairs and paths, terminal pairs,
  chains, non-persistent cycles, ambiguous owners, invalid or misaligned
  support, unseeded support, and disconnected owner identities fail closed.
  Public product composition forwards the exact support plane, while component
  labels, measurement ownership, thresholds, gates, and photometric
  definitions remain unchanged. Serial and existing-Dask execution agree
  under label, input, task, and retry reordering.
- Eighty-one focused scientific, composition, frozen-provenance, and executor
  tests pass. `just coverage` passes 2,153 tests with 44 deselected and four
  expected failures at 94.70% branch-aware project coverage. `just check`
  passes formatting, Ruff, Pyright, doctests, and 1,994 tests with 203
  deselected and four expected failures. All 27 applicable equivalence tests
  and the strict documentation build pass.

**Immediate next step:** freeze the clean implementation as exact
non-executable candidate and replay identities and run the complete no-write
verifier. Any cumulative replay still requires a separate exact approval.

## 2026-08-30 — Compose the fail-closed terminal-parent replay

**Plan phase:** Phase 5, closure gate 3

- Froze the corrected scientific candidate at revision `85d5807...`, source
  tree `a082cbe4...`, and configuration `88ac8bea...`. The configuration binds
  both the adjacent significant-support corroboration rule and the
  constituent-persistent terminal-cycle rule to their exact review and
  implementation decision.
- Added a prospective overlay around the frozen parent-construction replay.
  It writes and round-trip validates `source_association.json` in every future
  Continuum shard, records that sidecar as a checksummed run artifact, and
  installs the already-reviewed sidecar-aware compiler after the predecessor
  compiler composition. Missing, duplicate, absolute, or parent-traversing
  sidecar paths fail closed.
- The replay retains the exact 800-compact/1,600-Continuum population, 9,600
  reference runs, two-worker execution, closed baseline `a45303df...`, and
  reconstructed-reference terminal `48209eae...`. Readiness now names only
  future cumulative and qualification evidence from this corrected candidate;
  the terminally failed parent-construction evidence cannot satisfy it.
- Test-first development recorded the intended missing-wrapper/readiness red
  state. The focused candidate, predecessor, writer, evaluator, provenance,
  and no-write contracts now pass, including spawned-worker seam
  reinstallation. The wrapper still rejects execution without a separately
  frozen exact identity review and execution decision.

**Immediate next step:** validate and commit the wrapper composition, run its
complete real no-write verification against all retained reference evidence,
then freeze the exact wrapper and execution identities before consuming the
approved replay authority.

## 2026-08-30 — Freeze and authorize the terminal-parent replay

**Plan phase:** Phase 5, closure gate 3

- Committed the fail-closed replay composition at `1e8348b...`; wrapper
  `2c40315f...` retains candidate `85d5807...`, source tree `a082cbe4...`,
  configuration `88ac8bea...`, reconstructed-reference terminal
  `48209eae...`, and closed baseline `a45303df...` in a new write-once output
  and scratch namespace.
- The complete real no-write verifier passed all 2,400 retained inputs and
  9,600 reference runs. It also verified that the exact candidate writer
  persists association sidecars, the exact compiler composition installs the
  association-aware evaluator, the clean execution revision is `1e8348b...`,
  and both output and scratch remain absent.
- Non-executable identity review `42c35481...` records that pass and canonical
  execution identity `a069e5fc...`. The current explicit user instruction is
  consumed by one-replay decision `f6d2bcc8...`; campaign execution, viewed
  SDC1/Hydra execution, fresh qualification, tuning, rescoring, optimization,
  cutover, and release remain false.
- The composition passed 52 focused tests, 13 exact identity/wrapper tests,
  `just check` with 2,003 tests and four expected failures, `just coverage`
  with 2,162 tests and four expected failures at 94.69%, all 27 applicable
  equivalence tests, the strict documentation build, and clean pre-commit.

**Immediate next step:** commit the exact review and decision, create a clean
immutable execution checkout, repeat the complete no-write preflight there,
then start exactly one two-worker replay and monitor only operational state
until the atomic ledger exists.

## 2026-08-31 — Close the terminal-parent replay as improved failure

**Plan phase:** Phase 5, closure gate 3

- The immutable execution checkout `c1614c2...` repeated the complete no-write
  verification of all 2,400 inputs and 9,600 retained reference runs, then ran
  the exact two-worker replay under one-use decision `f6d2bcc8...`. All 2,400
  candidate products completed and the process atomically published
  `cumulative-regression-ledger-public-finder-terminal-parent-correction.json`,
  SHA-256 `e2ee663f4eade383518eabbafda5cd33bfe9808b4a9b37492a77337738b611db`.
  No process repair, duplicate replay, or partial-science inspection occurred.
- Terminal provenance binds candidate `85d5807...`, source tree `a082cbe4...`,
  configuration `88ac8bea...`, replay checkout `c1614c2...`, identity review
  `42c35481...`, execution decision `f6d2bcc8...`, reconstructed reference
  `48209eae...`, closed baseline `a45303df...`, and transient candidate product
  set `de69d4ed...`.
- Compact passed with no like-semantics regression. Continuum recorded 96
  passes, 35 failures, 12 underpowered endpoints, no indeterminate endpoints,
  and 30 like-semantics regressions. Both cumulative readiness booleans remain
  false, so qualification and every later Phase 5 gate remain closed.
- The correction had a large intended effect without overmerge regression:
  overall reliability rose from 62.38% to 85.21%, duplicate and split
  fractions fell from 25.29% to 12.83%, integrated-flux p95 fell from 79.26%
  to 26.94%, position p95 fell from 4.18 to 0.98 beam, and merge fraction
  remained zero. Fifty-four Continuum values and nine endpoint states changed;
  seven like-semantics regressions were removed. Shell splitting fell from
  100% to 34.56%, and shell median flux error fell from 76.46% to 10.39%.
- The remaining failure is therefore incomplete activation of scientifically
  useful parents, not dormant composition or generally invalid source-level
  measurement. The exact code path still requires pixel-overlap child edges
  for every terminal-cycle feature. The terminal ledger deliberately contains
  no per-image sidecars, so missing exact overlap remains a bounded hypothesis,
  not a proven per-realization cause.
- Added non-executable pre-review
  `phase-5-public-finder-terminal-feature-persistence-pre-review`. It binds all
  35 failures and requires a red analytic boundary-drift fixture before any
  implementation. The proposed narrow repair permits only mutually unique
  preceding-scale displaced-child corroboration through the fixed B3 footprint
  and the same retained significant-support component. It cannot create a
  cycle, pair, path, or membership; thresholds, measurement, gates, references,
  and closed evidence remain unchanged. The review also requires bounded
  rejection-reason aggregates in the next ledger.
- Final review SHA-256 is
  `e416f7d81ac8345f2ac0ac982980e9e37299886309af2468380a7a463beafc38`.
- Validation passed: five focused contract tests, `just check` (2,013 passed,
  four expected failures), `just coverage` (2,172 passed, four expected
  failures, 94.69%), all 27 applicable equivalence tests, strict docs build,
  and clean `just pre-commit`. Review against `CODE_REVIEW.md` found no
  actionable issue; this evidence-only change alters no production behavior.

**Immediate next step:** commit the immutable terminal summary and obtain named
approval of review SHA-256 `e416f7d8...`.
Only that approval may open fixture-first implementation and non-executable
identity freezing; the existing broad replay intent cannot bind identities
that do not yet exist.

## 2026-08-31 — Implement bounded terminal-feature persistence

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved terminal-feature persistence pre-review SHA-256
  `e416f7d81ac8345f2ac0ac982980e9e37299886309af2468380a7a463beafc38`
  for fixture-first implementation, diagnostics, executor validation, and
  non-executable replacement identity freezing only.
- A new analytic terminal-cycle fixture first failed as required: four valid
  terminal lobes with one-pixel preceding-scale drift remained four
  singletons because exact adjacent-scale support overlap was absent. This
  confirmed the proposed cause before production behavior changed.
- Implemented one bounded persistence seam. A terminal feature may use one
  displaced child only when the relationship is mutually unique, fixed B3
  envelopes overlap, both exact supports lie in the same retained
  significant-reconstruction component, and the child is not already used by
  an exact edge. The evidence only corroborates an already seeded terminal
  cycle and cannot create cycles, pairs, paths, membership, or transitive
  merges.
- Added array-free exact, displaced-candidate, displaced-accepted,
  missing-child, ambiguous-child, and whole-group-conflict diagnostics. The
  current source-association sidecar schema preserves them for bounded
  aggregation into the next terminal ledger.
- Positive displacement, disconnected support, ambiguous child, unseeded
  terminal feature, nearby pair, transitive path, invalid gap, and
  partial-group conflict controls pass. Serial and existing-Dask execution,
  reversed labels/planes/records/tasks, and duplicate retry produce identical
  memberships and diagnostics.
- Validation passed: 46 focused source-reconstruction/executor tests with 90%
  focused branch-aware coverage across the two changed production modules;
  `just coverage` (2,179 passed, four expected failures, 94.72%); `just check`
  (2,019 passed, four expected failures); all 27 applicable equivalence tests;
  and the strict documentation build. Review against `CODE_REVIEW.md` found no
  actionable implementation, architecture, scientific-boundary, privacy, or
  coverage issue. The only uncovered lines in the changed algorithm predate
  this correction; all newly added production lines are exercised.
- The mandatory JSON formatter reordered the approved pre-review and changed
  SHA-256 `e416f7d8...`. The file was restored exactly and added to the hook's
  narrow immutable-evidence exclusion alongside governed PyBDSF products, so
  future full-tree hooks validate it without invalidating its approval.

**Immediate next step:** commit the fixture-bound implementation, then freeze
exact non-executable candidate and replay composition identities. No replay or
viewed-data execution is open.

## 2026-08-31 — Freeze terminal-feature persistence identities

**Plan phase:** Phase 5, closure gate 3

- Committed the fail-closed prospective evaluator/configuration layer as
  `3d080f7...` and the replay/readiness composition as `7a5cd54...`. The exact
  candidate source tree is `a25d22d8...`, configuration is `2d6ab6bb...`,
  wrapper is `0c66f221...`, evaluator is `1cb62c00...`, and readiness overlay
  is `da135898...`.
- The wrapper composes over terminal-parent wrapper `2c40315f...`, requires
  the prospective rejection census on every successful Hebog Continuum
  sidecar, verifies all 2,400 exact product markers before terminal
  serialization, and reduces exactly 1,600 sidecars to bounded array-free
  diagnostics. It cannot open execution without a separate exact decision.
- The complete real no-write verification passed all 2,400 retained inputs
  and 9,600 reference runs, reconstructed-reference terminal `48209eae...`,
  closed baseline `a45303df...`, program and authority hashes, and all writer,
  evaluator, telemetry, worker-reinstallation, and write-once seams. Execution
  checkout was `7a5cd54...`; scratch and output remained absent.
- Non-executable identity review `45aef047...` records that result and binds
  canonical future execution identity `75534703...`. All replay, campaign,
  viewed-data, qualification, tuning, rescoring, optimization, cutover, and
  release authorizations are false; no execution decision was created.
- Validation passed 40 focused evaluator/configuration/wrapper/identity tests
  with 92% focused branch-aware coverage, `just coverage` with 2,196 passes
  and four expected failures at 94.73%, `just check` with 2,040 passes and four
  expected failures, all 27 applicable equivalence tests, strict docs build,
  and clean pre-commit. Review against `CODE_REVIEW.md` found no actionable
  correctness, scientific-boundary, architecture, privacy, or coverage issue.

**Immediate next step:** obtain explicit approval bound to identity review
SHA-256 `45aef047b0a8779e785995971eb60ad34384fa25aa443745ad36f2bdb6b652b9`
before creating one exact replay execution decision. No existing broad replay
authority opens this identity.

## 2026-08-31 — Authorize terminal-feature persistence replay

**Plan phase:** Phase 5, closure gate 3

- Gemma Danks approved the next cumulative replay, evaluation, and process-bug
  retries required to complete them. One-use execution decision binds exact
  non-executable review `45aef047...`, canonical execution identity
  `75534703...`, candidate `3d080f7...`, source tree `a25d22d8...`,
  configuration `2d6ab6bb...`, wrapper `0c66f221...`, reconstructed reference
  `48209eae...`, closed baseline `a45303df...`, two workers, and the exact
  write-once scratch/output namespaces.
- Retry authority is process-only: candidate science, configuration, gates,
  thresholds, references, baseline, and output identity may not change. A
  completed scientific failure remains terminal and cannot be tuned,
  rescored, or rerun as a process repair. Viewed public execution, fresh
  qualification, cutover, and release remain false.

**Immediate next step:** commit the exact decision, create a clean immutable
execution checkout, and repeat the complete no-write preflight there before
starting the two-worker replay.

## 2026-08-31 — Close terminal-feature persistence as regressed failure

**Plan phase:** Phase 5, closure gate 3

- Committed one-use replay decision `ad72924a...` at `ed84c216...`. Immutable
  checkout `/private/tmp/hebog-phase5-terminal-feature-persistence-replay-ed84c21`
  repeated the complete no-write verification of all 2,400 inputs and 9,600
  retained reference runs before starting the exact two-worker replay outside
  the app sandbox. Candidate execution produced all 800 compact and 1,600
  Continuum products; no process repair, duplicate replay, or partial-science
  inspection occurred.
- The process atomically published
  `cumulative-regression-ledger-public-finder-terminal-feature-persistence.json`,
  SHA-256 `a9b4d57e...`. Terminal provenance binds candidate `3d080f7...`,
  source tree `a25d22d8...`, configuration `2d6ab6bb...`, replay checkout
  `ed84c216...`, identity review `45aef047...`, execution decision
  `ad72924a...`, evaluator `1cb62c00...`, reconstructed reference
  `48209eae...`, closed baseline `a45303df...`, and transient product set
  `cd66892f...`.
- Compact passes every binding decision with no like-semantics regression.
  Continuum records 93 passes, 39 failures, 11 underpowered endpoints, no
  indeterminate endpoints, and 33 like-semantics regressions. Both
  `all_required_endpoints_pass` and `cumulative_science_regression_ready` are
  false. The candidate is terminally failed and may not be rerun, tuned, or
  rescored.
- Relative to the preceding terminal-parent ledger, 50 of 143 Continuum
  values changed, no endpoint state improved, three astrometric-bias passes
  became failures, and scale-4 split moved from underpowered to failure.
  Reliability fell from 85.21% to 77.80%; duplicate and split fractions rose
  from 12.83% to 15.21%; integrated-flux p95 rose from 26.94% to 74.62%; and
  position p95 rose from 0.98 to 3.59 beams. Mask precision, recall, and IoU
  remain unchanged; merge fraction remains zero.
- The bounded census proves that the intended displaced-child seam did not
  activate: 1,211 terminal-cycle candidates all became parents using 4,414
  exactly persistent features, while displaced candidates, displaced
  acceptances, missing or ambiguous children, rejected cycles, and conflicts
  are all zero.
- Code inspection identifies one new restriction on the predecessor exact
  path: an all-features-seeded guard discards a whole cycle before persistence
  evaluation whenever any geometric feature lacks a direct-component owner.
  The predecessor could retain a persistent unseeded feature as cycle geometry
  without adding it to catalogue membership. Because the census is downstream
  of the guard and transient products were removed, exact per-realization
  attribution still requires a red fixture.
- Added non-executable pre-review
  `phase-5-public-finder-terminal-cycle-eligibility-pre-review`, SHA-256
  `e70e602f5a7a7c2a703def62ac6e5922c505feb71ae4b6f9def6dfcbf9520cd5`.
  It binds every terminal failure and requires the red eligibility fixture,
  negative overmerge controls, pre-eligibility diagnostics, and
  Serial/existing-Dask invariance. It fixes thresholds, measurement,
  membership, gates, references, and closed evidence and authorizes neither
  implementation nor execution.

**Immediate next step:** commit the immutable terminal record and obtain named
approval of pre-review SHA-256 `e70e602f...` before fixture-only
implementation. Another replay requires separately frozen replacement
identities and a new exact approval.

## 2026-08-31 — Reframe Phase 5 feedback and promotion gates prospectively

**Plan phase:** Phase 5, closure gates 3--5

- Reviewed terminal-feature persistence ledger `a9b4d57e...` against the
  stated minimum replacement objective. The candidate passes 66 applicable
  paired Continuum comparisons, is underpowered on 11, and fails one against
  each PyBDSF reference; the shared failure is overall mask precision. Its 38
  absolute failures and 33 like-semantics regressions remain binding terminal
  failure evidence under the contract used for that replay.
- Updated the durable plan without rescoring historical evidence. Before
  another full replay, Phase 5 now requires one production-composition
  end-to-end contract lane, a 20--40-case mechanism-activation lane, and a
  frozen 64--128-case viewed-development scientific smoke lane. These lanes
  are diagnostic only and cannot use or be pooled with held-out qualification
  evidence.
- Made the current regression an explicit pre-replay blocker. The red fixture
  must prove that the all-features-seeded guard removes valid predecessor cycle
  geometry; the repair must retain an independently persistent unseeded feature
  only as geometry, keep membership seeded, produce non-zero activation on
  positive cases, reject all overmerge controls, and preserve compact and
  executor invariance.
- Added a prospective evaluation-contract review based on a read-only audit of
  the pinned Rapthor/LSMTool consumer. Binding compatibility and catastrophic
  safety are separated from review-required regressions and later improvement
  objectives. Both PyBDSF references, fixed practical margins, critical safety
  strata, and transparent reporting of underpowered endpoints remain required.
  Current campaigns may not be retroactively rescored, and the existing strict
  contract remains active until a replacement is independently reviewed.

**Immediate next step:** obtain named approval of terminal-cycle eligibility
pre-review `e70e602f...`. Under that fixture-only authority, reproduce and fix
the guard regression, then implement the fail-fast lanes and complete the
Rapthor consumer audit before freezing another candidate or full replay.

## 2026-08-31 — Clarify the Phase 5 parity, retention, and sequencing contract

**Plan phase:** Phase 5 closure and Phase 6 entry

- Corrected the prospective plan after Gemma Danks clarified the intended
  acceptance boundary. Hebog must match or outperform both PyBDSF references
  on every applicable governed check, not only checks later shown to be used by
  Rapthor. Underpowered binding comparisons require more evidence; they are not
  passes.
- Made retention of existing Hebog improvements a binding gate. The exact
  paired rule and practical margin must rule out a material regression against
  the best passing like-semantics Hebog baseline on every governed check. A
  gain elsewhere or an explicit trade-off cannot waive this Phase 5 gate.
- Reclassified the ambitious absolute numeric thresholds as transparent
  longer-term improvement targets once all relative parity and retention gates
  pass. Product validity, finite measurements, determinism, and
  schema/provenance safety remain binding invariants.
- Preserved the faster fixture, activation, and 64--128-case smoke ladder, but
  removed the early Rapthor audit. Rapthor consumer/profile work now starts
  only after a full cumulative replay and fresh qualification establish general
  scientific parity and retained Hebog quality.
- Recorded the optimization/release balance explicitly. Phase 6 now targets
  the earliest safe experimental Rapthor release after compatibility and the
  existing minimum complete-path performance gates pass; it does not wait for
  maximum facility scale or every absolute scientific stretch target. Phase 7
  then pursues the best practical scale and further scientific/computational
  improvement while parity, retained Hebog quality, and Rapthor compatibility
  remain mandatory regression gates. Phase 8 retains production hardening and
  `1.0` readiness.

**Immediate next step:** obtain named approval of terminal-cycle eligibility
pre-review `e70e602f...`, fix the dormant all-features-seeded regression under
fixture-only authority, and build the fail-fast lanes. Freeze no full replay
identity until the all-check parity-and-retention contract and smoke evidence
are reviewed.

## 2026-08-31 — Review Phase 5 feasibility and confirmatory science design

**Plan phase:** Phase 5 closure through Phase 7 scale-out

- Reviewed the complete plan for statistical identifiability, scientific
  validity, replay-loop risk, and consistency between the early-release and
  facility-scale milestones. The all-check parity objective is achievable only
  when the endpoint registry, one incumbent Hebog baseline, paired sampling
  unit, margins, applicability, and per-stratum power are frozen before
  candidate results are viewed.
- Added realization-level paired resampling to prevent source/pixel
  pseudoreplication, an intersection-union global decision requiring every
  binding endpoint to pass, prospective power for the smallest binding strata,
  and explicit treatment of underpowered results as unresolved rather than
  passes. One closed incumbent per explicit semantic profile replaces any
  possible per-endpoint best-of-history envelope; current terminal-cycle work
  retains predecessor `85d5807...` independently of the PyBDSF parity gate.
- Found that the frozen historical evaluator labels a comparison underpowered
  whenever observed paired standard deviation exceeds its planning value, even
  if the observed-data upper confidence limit is already within the practical
  margin. Several terminal comparisons exhibit this pattern; one observed
  standard deviation exceeds plan by only about `1.2e-5`. The plan now requires
  a prospective test-first evaluator repair: planning variance sizes the study
  and audits assumptions, while the frozen observed-data confidence interval
  decides non-inferiority. Historical ledgers remain unchanged.
- Retained shape, size, and position-angle comparison wherever fitted or
  moment-equivalent semantics align. Scientifically incompatible records must
  be declared unavailable before candidate viewing; they cannot be forced into
  a false comparison or dropped because of an unfavourable result.
- Corrected the computational non-regression rule: the upper one-sided 95%
  confidence bound for new/previous median runtime must be at most 1.05. An
  interval spanning that margin is underpowered, not a pass.
- Made the current repair criterion causal and testable: the smoke lane must
  restore the parent lost by the all-features-seeded guard while preserving the
  terminal-parent gains, compact invariance, and all overmerge controls.
- Split the performance matrix into a declared Phase 6 initial Rapthor support
  envelope and the Phase 7 30,000/100,000 facility matrix. This permits an
  earlier useful release without extrapolating unmeasured scale claims or
  weakening the final `1.0` requirements.

**Immediate next step:** approve and reproduce pre-review `e70e602f...`, then
implement the eligibility repair and fail-fast lanes. Before any full replay,
freeze the single incumbent, endpoint registry, realization-level inference,
and endpoint-level power plan described above.

## 2026-08-31 — Repair terminal-cycle eligibility under fixture authority

**Plan phase:** Phase 5 public-finder cumulative validation

- Recorded Gemma Danks's named approval of terminal-cycle eligibility
  pre-review `e70e602f...`. The authorization permits fixture-only
  implementation, bounded diagnostics, executor-invariance validation, and
  non-executable identity preparation; it permits no replay, viewed-data
  execution, tuning, rescoring, qualification, cutover, or release.
- Added the required red exact-persistence fixture. Before implementation, a
  four-feature terminal cycle with three immutable direct owners and one
  persistent unseeded feature incorrectly produced three singleton catalogue
  rows instead of one three-member parent. This confirmed the pre-review's
  proposed all-features-seeded guard as the causal boundary independently of
  displaced-child matching.
- Moved terminal-cycle membership eligibility after feature persistence. An
  unseeded terminal feature can now corroborate only cycle geometry after
  passing the unchanged exact or mutually unique displaced persistence rule;
  it can never become a catalogue member, reduce the three-member minimum, or
  change direct-component or measurement ownership.
- Added bounded pre-eligibility, unseeded-candidate, accepted, and rejected
  counts plus a prospective evaluator overlay. The frozen terminal-feature
  persistence evaluator remains unchanged. Positive exact and displaced
  fixtures activate the new census, while non-persistent, insufficient-member,
  pair, path, bridge, disconnected-support, ambiguous-child, crowded-seed,
  and partial-group controls remain closed.
- Focused validation passed 85 unit and integration tests, including component
  label, plane/record/task order, retry, Serial, and existing-Dask invariance;
  focused Ruff and Pyright checks also passed. Repository coverage passed
  2,218 tests with 94.76% branch-aware coverage, `just check` passed 2,057
  tests plus four expected failures, the frozen equivalence lane passed 27
  tests, and the strict documentation build passed.

**Immediate next step:** build the exact producer/wrapper/compiler/evaluator
contract lane, freeze the all-check PyBDSF-parity and Hebog-retention contract,
repair the prospective confidence evaluator, and run the frozen 64--128-case
scientific smoke lane. Do not freeze or execute a full replay until every
fail-fast prerequisite passes.

## 2026-08-31 — Add terminal-cycle fail-fast contract lanes

**Plan phase:** Phase 5 public-finder cumulative validation

- Added a frozen 25-case analytic mechanism population covering the repaired
  persistent-unseeded activation and seven fail-closed control families. Four
  label/order variants each record a non-zero historical pre-guard rejection
  and repaired acceptance; non-persistent geometry, bridges, pairs, paths,
  disconnected support, ambiguous children, and partial-group conflicts remain
  rejected.
- Added a strict bounded evaluator for that population. It rejects missing,
  duplicated, or scientifically changed case evidence, remains invariant to
  observation order, and produces only array-free non-promotional counts.
- Added an exact analytic end-to-end contract that executes the production
  source-reconstruction producer, canonical association writer/parser,
  sidecar-aware terminal-cycle compiler, source-union measurement evaluator,
  compact producer, checksum provenance, and atomic write-once publication.
  Compact output is byte-identical across independent runs and duplicate
  publication is rejected. Final review also made a non-empty association
  sidecar and the exact completeness/mask-precision endpoint set mandatory,
  so an incomplete composition cannot publish a passing record.
- Focused Ruff and test validation passed all five new normal and failure-path
  tests. Full coverage passed 2,223 tests with four expected failures and
  94.71% branch-aware project coverage; the new fail-fast module reached 86%.
  The existing equivalence lane passed all 27 selected tests and the strict
  documentation build passed. `just check` passed 2,061 tests with four
  expected failures and 206 deselections. No viewed SDC1/Hydra data, replay,
  qualification population, tuning, rescoring, or replacement replay identity
  was opened.

**Immediate next step:** freeze the prospective all-check PyBDSF-parity and
single-incumbent Hebog-retention decision contract, then repair its confidence
evaluator test-first. The scientific smoke lane and any full replay identity
remain blocked until those prerequisites pass.

## 2026-08-31 — Freeze the prospective all-check science contract

**Plan phase:** Phase 5 public-finder cumulative validation

- Added a deterministic write-once registry generator and strict loaders for
  the prospective PyBDSF-parity and Hebog-retention policy. The TDD lane first
  failed on the absent contract behavior, then passed seven focused normal,
  provenance, reproducibility, policy-drift, and unsafe-path tests.
- Froze endpoint registry `095354bc...` with 383 explicitly named endpoints:
  225 compact binding, 143 Continuum binding, and 15 Continuum longer-term
  objectives. Its 1,187 co-primary comparisons comprise 338 per PyBDSF
  reference, 143 applicable compact Aegean comparisons, and 368 comparisons
  to one whole Hebog incumbent. Every binding endpoint includes incumbent
  retention; scientifically incompatible Continuum centroid semantics waive
  only the cross-finder comparison, not Hebog retention.
- Froze inactive decision contract `f70f3213...`. It binds incumbent
  `85d5807...` and ledger `e2ee663f...`, requires exact paired incumbent
  reexecution because raw realization products are absent, uses whole-image
  noise-seed realizations as the resampling unit, and requires every
  co-primary confidence comparison to pass. Planning variance is design and
  audit evidence only; missing or underpowered binding evidence fails the
  global promotion decision.
- Bound all nine historical cumulative ledgers under their original policies
  with no retrospective rescoring. Absolute numeric targets remain reported
  longer-term objectives, while finite products, validity, provenance,
  determinism, and write-once publication remain binding.
- The contract remains `active=false` pending exact human scientific review.
  It authorizes no execution, replay identity freeze, qualification, tuning,
  rescoring, cutover, or release. No viewed dataset, candidate, campaign,
  replay, or result was opened.
- Final validation passed 2,230 tests with four expected failures and 94.54%
  branch-aware project coverage; the new production contract module reached
  83%. `just check` passed 2,068 tests with four expected failures, all 27
  frozen equivalence tests passed, and the strict documentation build passed.

**Immediate next step:** obtain exact scientific approval of contract
`f70f3213...`, then implement the prospective confidence evaluator test-first.
The endpoint-level power audit, diagnostic smoke lane, and any full replay
remain blocked.

## 2026-08-31 — Implement prospective replay activation gates

**Plan phase:** Phase 5 public-finder cumulative validation

- Recorded Gemma Danks's authority to complete the frozen prerequisites and,
  only after every gate passes without identity drift, run and evaluate the
  next cumulative replay. The activation decision binds decision contract
  `f70f3213...`, endpoint registry `095354bc...`, the exact prerequisite
  programs, and explicit prohibitions on tuning, rescoring, qualification,
  cutover, and release.
- Implemented the prospective observed-data evaluator test-first. Planning
  variance now sizes the experiment and records assumption deviations but
  cannot override the realization-level upper confidence limit. Exact margin
  equality passes; missing candidate evidence fails; missing comparators and
  confidence intervals crossing a margin are underpowered; non-finite evidence
  is indeterminate. Three historical evaluators remain byte-identical.
- Froze a result-neutral 128-case diagnostic population: 64 compact inputs and
  16 inputs from each of four Continuum datasets, ordered only by input-ID
  digest. Added current and exact-incumbent materializers, complete no-write
  verification of all retained evidence, compact product identity checks,
  terminal-cycle activation checks, paired Continuum compilation, and atomic
  write-once publication.
- Replaced a circular draft power calculation that inferred future variance
  from viewed confidence intervals. The final endpoint-complete audit reuses
  the reviewed compact simultaneous lower bound and frozen Continuum family
  planning variances at 800 compact and 1,600 Continuum realizations. Compact
  incumbent power is conditional on exact smoke product identity and a full
  800-product recheck. Tests cover all 1,187 comparisons, margin drift, and a
  missing compact identity condition.
- Focused prospective evaluator, contract, power, smoke, materializer,
  mechanism, and end-to-end validation passes. The branch-aware coverage lane
  passes 2,264 tests with four expected failures at 94.52%; `just check`
  passes 2,102 tests with four expected failures; all 27 frozen equivalence
  tests pass; the strict documentation build and final pre-commit suite pass.
  Focused Ruff and Pyright checks also pass. No candidate product, viewed
  scientific result, or full replay output has been opened yet.

**Immediate next step:** commit an immutable prerequisite checkout, run both
complete no-write preflights, then execute and evaluate the 128-case smoke.
Freeze the endpoint power audit and exact full-replay identities only if the
smoke passes without a confirmed scientific regression.

## 2026-09-01 — Repair prospective incumbent tooling provenance

**Plan phase:** Phase 5 public-finder cumulative validation

- The current-candidate complete no-write preflight passed against all 2,400
  retained inputs and 9,600 reference runs without creating scratch. The
  incumbent preflight then failed before retained-reference traversal,
  candidate execution, scratch creation, or scientific output because the
  materializer looked for a later frozen replay wrapper inside the historical
  candidate checkout.
- Separated the immutable tooling root from the historical candidate source
  root. Reference verification and replay composition now load only from the
  reviewed prospective tooling checkout, while revision and source-tree
  identity remain bound to the exact candidate checkout. Added a regression
  test proving that an incumbent checkout without the later wrapper composes
  through the separate tooling root; focused tests and Pyright pass.

**Immediate next step:** freeze the repaired program in a new immutable
checkout and rerun both complete no-write preflights before materialization.

## 2026-09-01 — Repair prospective mixed-schema smoke compilation

**Plan phase:** Phase 5 public-finder cumulative validation

- Both repaired no-write preflights passed and both exact 128-product smoke
  sets materialized completely. The first evaluator invocation failed before
  atomic publication when the current terminal-cycle parser was reused for an
  incumbent sidecar that correctly predates the additive terminal-persistence
  diagnostics. The verified current and incumbent product sets remain
  unchanged and reusable.
- Added explicit schema dispatch for the paired-incumbent compilation. Current
  products first compile under the complete terminal-cycle schema and their
  eligibility census is reduced independently; the mixed current/incumbent
  pair then compiles under the exact terminal-parent schema, which accepts the
  current sidecar's additive fields while parsing the historical sidecar at
  its own frozen contract. A focused regression test proves the historical
  compiler is installed for this mixed view. Seventeen smoke/materializer
  tests and Pyright pass.
- Closed a final terminal-provenance gap before publication: the smoke record
  now binds the exact evaluator program as well as the materializer,
  population, candidate and incumbent product sets, source trees,
  configurations, and revisions.

**Immediate next step:** freeze the evaluation-only repair in an immutable
checkout and evaluate the preserved smoke products exactly once into the still
absent atomic output.

## 2026-09-01 — Fail the prospective smoke and review boundary refinement

**Plan phase:** Phase 5 public-finder cumulative validation

- Published the exact 128-case diagnostic smoke at
  `prospective-science-smoke.json`, SHA-256 `e3ac8e62...`. The terminal result
  is fail: 326 comparisons pass, 35 are diagnostic-underpowered, and eight
  PyBDSF-parity comparisons fail. All 369 incumbent-retention comparisons pass
  and compact products are byte-identical to the incumbent.
- The failed families are image-edge, morphology-artifact, and one-beam
  duplicate fractions; overall mask precision against both PyBDSF references;
  and diffuse split fractions. Mask recall and intersection over union improve,
  but mask precision is worse in all 64 Continuum cases, identifying systematic
  sparse boundary support rather than lost sensitivity. Duplicate and split
  failures are sparse realization-level outliers.
- Terminal-cycle eligibility activated on 26 unseeded persistent candidates,
  but all catalogue memberships remain identical to the incumbent, which had
  already accepted the same 75 terminal parents. This prospective mechanism is
  therefore scientifically dormant for the remaining parity gaps.
- Froze pre-review `e92ac289...` for a bounded replacement: apply the existing
  reviewed dense-core, high-S/N boundary, and nearby significant multiscale
  support refinement after seeded ownership, and repair only its opened-away
  high-S/N thin-detection branch. Its constants remain fixed at a 3-by-3
  opening, five core neighbors, S/N 6, and 0.5 beam recovery; no threshold,
  margin, population, ownership, association, or measurement tuning is allowed.

**Immediate next step:** reproduce the high-S/N empty-opening defect test-first,
implement the bounded refinement composition, pass fixture and executor
invariance validation, and repeat the exact frozen smoke into a new write-once
namespace. Do not freeze or run the full cumulative replay unless that smoke has
no confirmed failure.

## 2026-09-01 — Implement prospective seeded-owner boundary refinement

**Plan phase:** Phase 5 public-finder cumulative validation

- Added red fixtures for the two missing behaviors. The existing refinement
  incorrectly discarded an independently strong thin segment when the 3-by-3
  opening removed its whole support, and the seeded-owner public path did not
  invoke refinement at all. Both fixtures failed for those exact reasons.
- Refined original owned pixels now survive opening only at the fixed 6-sigma
  boundary threshold. Dense opened cores and nearby significant multiscale
  support retain the existing five-neighbor and 0.5-beam rules. The public
  composition applies this rule after deterministic seeded ownership.
- Wider real-scale tests exposed a second contract error before execution:
  refined measurement ownership could exclude a pixel still claimed by the
  downstream direct-component plane. Direct component support is now clipped
  to refined ownership while keeping its original component identities. This
  restores the required direct-subset-of-measurement invariant.
- Froze implementation decision `c273de99...` and replacement configuration
  `ecf5ace2...`. The activation record binds the failed smoke `e3ac8e62...`,
  bounded pre-review `e92ac289...`, new implementation decision, and exact
  amended materializer. It continues to prohibit tuning, rescoring,
  qualification, cutover, and release.
- Focused boundary, configuration, materializer, real-scale morphology,
  Serial/partition, existing-Dask, and end-to-end validation passed 71 tests.
  Full branch-aware coverage passed 2,271 tests plus four expected failures at
  94.52%; `just check` passed 2,109 tests plus four expected failures; and all
  27 frozen equivalence tests passed. Focused Ruff and Pyright checks passed.
- Both complete 2,400-input/9,600-reference no-write preflights passed for
  candidate `8b1029f...` and exact incumbent `85d5807...`. Candidate
  materialization then failed after 16/128 products, before evaluation or any
  atomic science record, because cleanup split one direct component across
  multiple connected support parents. The 293 MiB partial scratch remains
  preserved and will not be overwritten.
- Added a red two-lobe bridge fixture reproducing that exact invariant failure.
  Refinement now restores an original direct owner only when cleanup would
  split its eight-connected support; ordinary connected low-S/N protrusions
  remain removed. The repaired focused morphology, partition, Dask, and
  end-to-end suite passes 65 tests, and full coverage passes 2,272 tests plus
  four expected failures at 94.52%. `just check` passes 2,110 tests plus four
  expected failures, and all 27 frozen equivalence tests pass.
- Amended the implementation decision to `25cbdfa4...` with the terminal
  process failure and no-split policy. Replacement configuration is
  `68e8a49f...`; it requires a new immutable candidate and scratch namespace.

**Immediate next step:** seal the repaired candidate in an immutable checkout,
pass both complete no-write preflights, materialize only the new current
128-product set, reuse the separately verified exact incumbent product set, and
publish one replacement write-once smoke decision. Continue to the power audit
and full replay only if it has zero confirmed failure.

## 2026-09-01 — Review failed boundary smoke and separate mask measurement

**Plan phase:** Phase 5 public-finder cumulative validation

- The repaired boundary candidate completed all 128 products and published
  `prospective-science-smoke-boundary-connectivity.json`, SHA-256
  `e30f27dd...`. The terminal verdict remains fail: 309 comparisons pass, 49
  are diagnostic-underpowered, and 11 are confirmed failures. Compact products
  remain byte-identical to the incumbent.
- Two mask-precision failures are systematic: all 64 Continuum images remain
  below released PyBDSF and 63 remain below pinned master, even though overall
  precision improves by about 0.00546 relative to the incumbent. Nearby
  multiscale recovery still admitted published boundary support below the
  already-frozen three-sigma island threshold.
- Three new incumbent position-p95 failures come from using the refined mask as
  the source-association and moment-measurement plane. One Continuum-2
  varying-noise realization, seed 2026861185, dominates the tail: position p95
  changed from 0.5709 to 2.2886 beams overall and from 0.6018 to 2.4340 beams
  at scale four after canonical component support and identifiers changed.
- Four duplicate and two diffuse-split failures are inherited sparse topology
  gaps. The edge duplicate is concentrated in Continuum-1 seed 2026860341;
  diffuse splits occur there and in Continuum-3 seeds 2026862118 and
  2026862301. They require a separate prospective topology review if they
  remain after the mask-only correction.
- Froze pre-review `bd0ba297...` for a bounded correction: refine only the
  published mask, require recovered mask support to meet the existing
  three-sigma island threshold, and retain the deterministic seeded-owner plane
  for catalogue association, measurement, identifiers, and direct provenance.
  Red fixtures failed for all three missing behaviors; the focused corrected
  suite now passes 69 tests. No detection threshold, margin, reference,
  population, or decision rule changed.
- Required handoff validation passes: branch-aware coverage runs 2,274 tests
  plus four expected failures at 94.52%; `just check` runs 2,112 tests plus
  four expected failures; all 27 frozen equivalence tests pass; focused
  Pyright and Ruff checks, strict documentation, and the final pre-commit suite
  pass. Code review found no actionable issue; the remaining uncertainty is
  deliberately delegated to the write-once 128-case smoke.

**Immediate next step:** complete full validation and identity freeze, then run
both complete no-write preflights and repeat the same 128-case smoke in a fresh
write-once namespace. The cumulative replay remains blocked until the smoke has
zero confirmed failures.

## 2026-09-01 — Repair mask-separated smoke evaluation

**Plan phase:** Phase 5 public-finder cumulative validation

- Candidate `b8d57a6...`, source tree `53ef4586...`, and configuration
  `24663a15...` passed the exact current and incumbent complete no-write
  preflights. The current candidate then sealed all 128 products; canonical
  product-set identity is `02a17815...`.
- The first evaluation attempt failed during current compilation before atomic
  publication. The historical association evaluator required every verified
  measurement label to be present in the native label plane. That invariant
  predates the reviewed mask/measurement separation: the native plane is now
  the refined publication mask, while the sidecar and catalogue intentionally
  preserve stable measurement components.
- Added a test-first, evaluator-only overlay. It continues to verify exact
  component/source identities, catalogue coverage, unique ownership, and that
  every published positive label is claimed by the measurement partition. It
  only allows a verified measurement component to have no remaining published
  pixel, and restores the historical evaluator seam on both success and
  exceptional exit. No product, source tree, scientific configuration,
  comparator, threshold, margin, gate, or historical compiler changed.
- Pre-review `aca3574a...` and its implementation decision bind the exact
  sealed current and incumbent product sets. Focused association, provenance,
  and smoke tests pass 37 tests; focused Ruff and Pyright pass.
- The JSON formatter attempted to reorder the already checksum-bound
  `bd0ba297...` scientific pre-review. Its exact path is now excluded beside
  the existing governed-review exclusion, preserving the reviewed bytes while
  all new JSON remains formatter-controlled.

**Immediate next step:** freeze the evaluator-only repair in an immutable
checkout and evaluate the exact sealed products into the still-absent
write-once smoke output. Interpret that science before any topology change,
power audit, or full replay.
