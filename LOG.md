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
I/O, and Phase 2 deterministic background/RMS estimation. The Phase 2
implementation passes analytic, partition, retry, serial/Dask, compact
PyBDSF, representative scientific, four-core latency, and peak-memory gates.
The next implementation phase is thresholding, islands, and deblending.
Automatic bright-candidate discovery, final RMS persistence, complete
source-finding products, Rapthor integration, and multi-node scalability
remain explicitly unimplemented. Named domain and facility review is still
required before engineering thresholds or defaults are called
domain-approved, complete PyBDSF equivalence is claimed, or Rapthor cuts over.

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
