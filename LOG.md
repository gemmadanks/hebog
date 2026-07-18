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
- Git history remains the detailed record of individual code changes.

Add entries in chronological order using ISO dates. Include commands, dataset
identifiers, revisions, and measured evidence when they affect a scientific or
performance conclusion. Update the plan only when execution changes its scope,
sequence, gates, risks, or decisions.

## Current position

Hebog has a validated package and development scaffold, but the scientific
source-finding algorithms and Phase 0 equivalence harness are not implemented.
The next milestone is to freeze the Rapthor/PyBDSF contract, datasets,
comparison oracles, and matched baseline before algorithm development begins.

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
