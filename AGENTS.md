# AGENTS.md

This file applies to the entire repository.

## Repository overview

Hebog is a Dask-aware radio-continuum source finder for SKA Science Data
Processor pipelines. Its first production consumer is Rapthor's
`filter_skymodel` step. It is intentionally narrower than PyBDSF: reproduce
the behaviour and products Rapthor uses, demonstrate scientific equivalence,
and meet the performance gate below. The architecture must scale out of core
to 100,000-by-100,000 images across 100 to several hundred nodes through
Rapthor's existing Dask cluster; production nodes have hundreds of GB of RAM.
Maintainability, extensibility, and interoperability are primary architecture
qualities: the scientific library must remain usable from other pipelines and
science workflows without importing Rapthor, Prefect, or LSMTool.

[`plans/source-finder-implementation.md`](plans/source-finder-implementation.md)
is the authoritative delivery plan; `PLAN.md` is the reusable template for
other work plans; [`LOG.md`](LOG.md) is the chronological execution record.

The repository contains:

- the Python package in `src/hebog/`: public API and pipeline, `science/`
  composition, scheduler-facing `stages/`, pure `algorithms/`, `executors/`,
  `data_models/`, `io/`, compatibility `adapters/`, and campaign
  `validation/` tooling;
- tests in `tests/` and reproducible tooling in `scripts/benchmark/` and
  `scripts/validation/`;
- checked-in algorithm, dataset, contract, and benchmark configuration in
  `config/`;
- MkDocs documentation in `docs/` and Marimo notebooks in `notebooks/`.

Adjacent checkouts of PyBDSF and Rapthor are development references only.
Never hard-code those paths in package code or normal tests.

## Working principles

- Make the smallest coherent change that satisfies the task. Preserve
  unrelated work: inspect `git diff` before and after editing, and do not
  revert changes you did not make.
- Follow the existing structure and naming conventions instead of introducing
  a second tool or parallel configuration.
- Add or update tests when behaviour changes. Update user-facing documentation
  when public APIs, setup steps, output schemas, or workflows change.
- Hebog is pre-production and provides no backward-compatibility guarantee
  between `0.x` releases. Prefer the cleanest current design: change or remove
  obsolete Hebog APIs, schemas, development stores, and configuration
  directly, and make tests and documentation describe only the current
  contract. Do not add compatibility shims, deprecation periods, legacy
  readers, migration code, or old-version tests unless the user explicitly
  requests them for a particular interface. Mark breaking changes clearly in
  current documentation and the Conventional Commit, and make stale persisted
  artifacts fail clearly. This policy does not weaken the PyBDSF/Rapthor
  compatibility target, scientific reproducibility, or the supported platform
  matrix.
- Use the lightest planning level in `PLAN.md`. Keep the source-finder plan
  concise and forward-looking: its current-state summary identifies the
  candidate, strongest applicable evidence, known blockers, authorized next
  action, and deferred work. Update it when scope, sequencing, a milestone,
  benchmark baseline, scientific threshold, gate, architecture decision, or
  risk changes, and record significant architecture or scientific decisions
  there before spreading them through the implementation.
- The plan holds only current state, remaining tasks, and the rules and gates
  that govern future work. Keep historical information in `LOG.md`: execution
  narratives, repair diagnoses, test counts, commit and evidence identities,
  and dated decision records. When a task completes, record its outcome in
  `LOG.md` and remove the task from the plan rather than marking it done and
  annotating it. Restate a past decision in the plan only as the current
  rule or constraint it imposes. Never grow a task with progress notes.
- Append to `LOG.md` only material plan execution, scientific and performance
  evidence, gate outcomes, deviations, cross-commit decisions, and next steps.
  Link exact evidence identities rather than repeating them. Use Git history
  for routine implementation detail and release notes for user-visible
  changes. When status changes, update or replace existing status summaries;
  do not leave contradictory "current" positions in project records.
- Use one writing agent by default. Delegate only independent, bounded work.
- Record architecturally significant decisions with an ADR based on
  `docs/architecture/adr/template.md`.
- Before a scientific or campaign repair, follow the
  [collaboration and repair decision rules](plans/source-finder-implementation.md#collaboration-and-repair-decisions)
  in the plan: agent-owned routine checks, a decision statement before each
  repair, reassessment after two ineffective repairs, and carrying
  authorization forward within scope.
- Keep generated FITS products, catalogues, benchmark results, profiles,
  production data, `site/`, `dist/`, and `build/` out of Git. Small
  redistributable fixtures may be added under `tests/data/` with provenance.
  Never add credentials, private dataset locations, cluster secrets, or
  tokens; use documented environment variables and ignored local config.

## Setup and commands

Dependencies and environments are managed with uv:

```bash
uv sync --all-groups
```

Prefer the `just` recipes because they document the intended workflow;
`just --list` shows all of them. The main ones are:

```bash
just test-unit          # fast deterministic tests and doctests
just test-contract      # scheduler-independent public behaviour contracts
just test-integration   # Dask and FITS integration tests
just test-equivalence   # frozen PyBDSF comparisons
just test-acceptance    # Rapthor-facing behaviour scenarios
just test-qualification # held-out scientific cases on an approved data host
just test-benchmark     # controlled performance runs
just test-scalability   # controlled 100-to-200-plus-node scale runs
just coverage           # portable suite with branch coverage
just check              # format-check, lint, type-check, unit tests
just pre-commit-fast    # lint, formatting and hygiene hooks, with fixes
just pre-commit         # fast hooks first, then type, docs, notebook and tests
just docs-build         # strict MkDocs build
just marimo-check       # validate Marimo notebooks
just notebook-smoke     # execute the offline notebooks
just package-smoke-test # build and import the wheel in isolation
just ci                 # comprehensive local CI equivalent
```

For a focused test, run pytest through uv, for example
`uv run pytest -q tests/unit/test_config.py`. If `just` is unavailable, run
the corresponding command from the `justfile`. PyBDSF equivalence and Rapthor
end-to-end runs may require a separate integration container; do not add
heavyweight production tools to the core runtime solely for tests.

## Architecture rules

- Keep scientific functions pure where practical: arrays and immutable
  configuration in, arrays or records out. Production kernels use vectorised
  NumPy/SciPy or measured compiled, GIL-releasing kernels, never Python loops
  over pixels or RMS windows.
- Dependencies point inward. Algorithms and domain records know nothing about
  orchestration frameworks, compatibility adapters, concrete schedulers, or
  process-wide configuration; adapters may depend on the stable scientific
  API, never the reverse. Keep FITS, catalogue, Rapthor, and scheduler
  integration at explicit boundaries, and put Rapthor/LSMTool names,
  filtering rules, filenames, and failure translations in a versioned
  compatibility adapter. A non-Rapthor workflow must be able to use the
  public API and serial executor without importing or constructing Dask,
  Prefect, LSMTool, or Rapthor objects.
- Keep library-module imports inert: they may define types and immutable
  constants but must not read or write science/workflow data, inspect the
  filesystem for work, change process state, access the network, create
  clients or clusters, or submit computation. `__main__.py` is the explicit
  CLI entry-point exception. Importing `hebog` or `hebog.pipeline` must not
  eagerly import a concrete scheduler; optional executors load only when
  requested.
- Do not start a private Dask cluster or multiprocessing pool inside the
  library by default; Rapthor owns the top-level scheduler and resource
  budget. Algorithms accept an executor rather than importing a global client.
  A Dask executor may receive an existing client, but never send open files,
  scheduler clients, mutable pipeline state, or repeatedly embedded full
  images through tasks. Public requests and results remain small and
  serializable.
- Maintain `SerialExecutor` as the deterministic reference. Alternate
  executors, stores, and workflow adapters must pass the same contract suite
  and produce equivalent results.
- Prefer coarse Dask batches that amortise scheduler and I/O overhead while
  leaving enough runnable work for occupancy; memory-rich scale runs may use
  larger batches. Graph size scales with tiles and scientific stages, never
  with pixels, RMS windows, or small islands, and reductions stay
  hierarchical rather than gathering image-sized state on the scheduler.
- Never require a complete large plane on one worker or publish a complete
  100,000-by-100,000 plane to Dask. A small image is one tile; large images
  give every tile a deterministic non-overlapping output core, explicit global
  coordinates, the smallest reviewed stage-specific halo, bounded summaries,
  and hierarchical reconciliation. Reconcile labels, sources, and products
  independently of worker count and task order.
- Use Zarr as the sole backend for intermediate image planes; FITS remains an
  ingress and final compatibility format. Bounded small work uses one Zarr
  chunk and serial execution; reduce Zarr initialization, codec, and
  materialisation overhead instead of adding another intermediate backend.
- Read each image once where possible. Reuse background, RMS, convolution,
  WCS, and beam products across stages and wavelet scales.
- Size tile batches and worker caches from admitted memory metadata. Exploit
  memory-rich nodes while reserving headroom for concurrent work; do not
  hard-code one tiny tile size or let resource sizing change scientific
  ownership and results.
- Control array dtype and copies deliberately. A change from `float64` to
  `float32` requires scientific-equivalence evidence, not only a performance
  result.
- Batch nonlinear fits by estimated island cost. Use moments for
  initialization and avoid fitting pixels that cannot affect an accepted
  catalogue entry.
- Version output schemas. Rapthor-facing outputs use paths and plain metadata
  so tasks can be retried and resumed.
- Add extension seams only at demonstrated variation points. Prefer a narrow
  executor, image-source, product-sink, or compatibility protocol over a
  generic plugin framework, registry, service locator, or conditionals spread
  across scientific modules.

## Scientific validation

- Scientific equivalence means matching the behaviour Rapthor requires, not
  bitwise equality with PyBDSF. Do not claim it from a single image or
  source-count comparison; use the dataset matrix and metrics in the plan.
- Keep scientific choices within the community best-practice envelope of
  peer-reviewed literature and source-finder challenges. Treat consensus
  across established observatory pipelines as a strong guide, not a vote that
  overrides governed truth; no single pipeline or source finder is ground
  truth. Document any deliberate departure, justify it with analytic or
  injected-truth evidence, and obtain renewed human scientific review before
  promotion.
- Do not copy PyBDSF implementation code. Reimplement documented scientific
  behaviour with new, independently structured code and retain attribution
  for papers, algorithms, and test data.
- Do not weaken detection thresholds, skip extended-source processing, or
  silently change output semantics to meet a runtime target.
- Every algorithm milestone needs tests for empty and all-NaN images; negative
  backgrounds and invalid pixels; isolated compact sources over a range of
  signal-to-noise ratios; close blends and multi-component islands; extended
  and multiscale emission; edge sources and non-square images; different
  beams, WCS orientations, pixel scales, and image units; sources and islands
  crossing tile edges and corners; and partition, tile-shape, worker-count,
  task-order, and retry invariance.
- Compare Dask results against the serial reference before comparing either
  with PyBDSF. Report low-SNR threshold crossings as completeness and
  reliability changes rather than hiding them as unmatched rows.
- Before a long scientific campaign or replacement replay, run the bounded
  development screen defined in the plan's scientific gates.

## Performance validation

- The primary gate is the matched median wall time of Rapthor's complete
  `filter_skymodel` step: at least 50% faster than the released PyBDSF used by
  Rapthor and faster than the pinned PyBDSF `master` reference, under the
  plan's confidence rule. This is a minimum deployment gate, not an
  optimization stopping point; optimize complete latency and throughput across
  the supported size range, including small inputs dominated by setup and
  scheduler overhead.
- Isolated kernel timing never establishes a speedup. End-to-end runs include
  FITS I/O, catalogue generation, Dask overhead, and Rapthor filtering.
  Benchmark exact released and `master` PyBDSF revisions in isolated, matched
  environments; never substitute one for the other.
- Optimize only from profiles or scale evidence. Isolate unavoidable low-level
  complexity behind a clear typed function, retain a readable serial oracle,
  and document why the complexity is necessary. An optimization is acceptable
  only when the relevant scientific suite passes.
- Record dataset identity and checksums; Hebog, PyBDSF, Rapthor, Python, and
  dependency revisions; configuration and output mode; workers, threads, CPU
  affinity, and memory limits; wall time, CPU time, peak RSS, task count, and
  Dask transfer/spill metrics; logical image and plane sizes, tile cores and
  halos, partition count, boundary-summary volume, scheduler load, worker
  occupancy, storage throughput, RAM headroom, and strong/weak-scaling
  efficiency; and the warm-up policy and every measured repetition.
- Use at least five measured repetitions after warm-up, compare medians,
  report dispersion, and avoid concurrent unrelated workloads. Serialize runs
  with `hebog.validation.evidence` under the ignored `benchmark-results/`
  directory or controlled external storage; commit only compact JSON
  summaries and reproducible commands. Record unavailable instrumentation
  with an explicit reason, never a fabricated zero, and label evidence
  `reviewed` only after its protocol, environment, and scientific results pass
  review.
- The controlled matrix spans 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000,
  and 100,000 pixels per side, both sides of every measured execution
  crossover, and empty or sparse, normal, and dense or extended workloads. Do
  not optimize one size tier by regressing another: benchmark affected and
  adjacent anchors against the previous reviewed Hebog curve, and refresh the
  full frozen ladder at milestone qualification. A statistically supported
  regression greater than 5% at any tier requires an approved, documented
  trade-off.

## Native code

Follow the [native-code assessment](docs/explanation/native-code-assessment.md).

- Use NumPy/SciPy first and Numba for profiled custom loops. A C++, Rust,
  Cython, or other compiled candidate must remain material after
  vectorization, copy removal, batching, and Numba, and pass the 10% profile,
  2x kernel, and 5% end-to-end gates unless it unlocks a failed memory or
  scalability requirement. Record the Rust (PyO3/maturin, for a new
  self-contained kernel) or C++ (pybind11, for a mature C/C++ library)
  selection in an accepted ADR before production use.
- Keep native boundaries small, typed, coarse-grained, and array-oriented,
  specifying dtype, shape, strides, alignment, ownership, mutability, errors,
  and copy permission; never call native code per pixel or source. Release the
  interpreter during long native work and prevent internal thread pools from
  oversubscribing a Dask worker.
- Preserve the Python/Numba serial oracle with identical scientific contract
  tests, no uncaught Rust panic or C++ exception, and appropriate sanitizer,
  Miri, or equivalent safety evidence. Native code may not become mandatory
  until wheels, isolated installs, source builds, licensing/provenance review,
  and fallback pass for every supported platform, Python ABI, and NumPy
  version; a normal install must never need a compiler.
- Keep FITS, WCS, schemas, configuration, adapters, workflow orchestration,
  and Dask graph construction in Python.

## Python conventions

Treat readability, maintainability, extensibility, and testability as
acceptance requirements, not cleanup deferred until after performance work.
The [quality attributes and coding principles](docs/explanation/quality-attributes.md)
explain the rationale.

- Python 3.12 through 3.14 is supported; do not rely only on the version in
  `.python-version`. Add type annotations to new or changed functions. Use
  absolute `hebog` imports in tests and examples.
- Prefer standard protocols and the data model (`pathlib.Path`, context
  managers, iterators, comprehensions, dataclasses, structural `Protocol`
  types), composition, and small functions. Use immutable dataclasses for
  small public records. Do not reproduce Java-style getters, service classes,
  factories, or interfaces when a function, dataclass, callable, or protocol
  suffices.
- Use descriptive glossary names. Avoid unexplained abbreviations, generic
  names such as `data` or `manager`, and boolean arguments whose meaning is
  unclear at the call site.
- Keep modules cohesive and functions at one useful level of abstraction; do
  not split code only to satisfy a metric. Make dependencies, side effects,
  units, coordinate systems, array shapes, mutability, ownership, and failure
  behaviour explicit, with no hidden global state or environment-dependent
  scientific behaviour.
- Remove accidental duplication, but wait for a stable shared concept before
  extracting an abstraction.
- Keep public APIs deliberately small, typed, documented, and versioned.
  Export names from `src/hebog/__init__.py` only when intentionally part of the
  top-level public API.
- Follow Google-style docstrings. Python examples are collected as doctests
  and must remain valid. Keep comments focused on numerical assumptions,
  units, array shape, halo requirements, and scheduler/resource constraints.

## Tests

- Place unit tests in `tests/unit/`, public behaviour contracts in
  `tests/contract/`, Dask/FITS boundary tests in `tests/integration/`, PyBDSF
  comparisons in `tests/equivalence/`, Rapthor-facing scenarios in
  `tests/acceptance/`, and timing and controlled scalability tests in
  `tests/benchmark/`.
- Markers are strict and declared in `pyproject.toml`: `contract`,
  `integration`, `equivalence`, `acceptance`, `qualification`, `benchmark`,
  `scalability`, `slow`, `requires_data`, and `posix_frozen_record`.
- Unit tests must not require a running scheduler, download data, or depend on
  execution order.
- Use TDD for public contracts, pure scientific kernels, schemas, matching,
  error behaviour, and executor semantics: write a test that fails for the
  intended reason (not an import, fixture, or environment failure), implement
  the smallest serial behaviour, refactor, then add executor conformance and
  scientific comparisons. Add a regression test before fixing incorrect
  behaviour when practical, at the boundary where the defect escaped. If
  test-first development is genuinely impractical, record why in the plan or
  handoff and add the behavioural test in the same commit. Do not commit a red
  state unless the user explicitly requests it.
- Use analytic truth before generated truth, the serial implementation before
  executor comparisons, and frozen PyBDSF products only as a compatibility
  oracle. Test matchers and comparison reports independently.
- Use property-based tests for numerical invariants and boundary combinations,
  bounded to physically meaningful ranges.
- Test one-tile versus many-tile equivalence on small analytic data before
  using the controlled scalability lane. Put sources on every edge/corner
  topology and vary partition origin, tile shape, completion order, and retry.
- Give every dataset a `development`, `regression`, or `qualification` role.
  Do not tune with held-out qualification results. Store generator version,
  configuration, and random seeds. Frozen expected products are immutable
  during tests; regenerate them only through a separate documented command
  with checksums, tool revisions, and scientific review.
- Test observable behaviour, error messages, and public-boundary validation.
  Exercise a small complete user workflow through the public API and emitted
  products early in each milestone and repair cycle; complement stage-level
  tests with checks of their composition.
- Write lightweight acceptance tests in Given/When/Then form. Do not add a
  Gherkin framework unless domain experts will review or author feature files.
- Use deterministic fault injection for normal executor tests; reserve actual
  worker termination, spilling, private data, and wall-time gates for
  controlled runners.
- Maintain at least 80% branch-aware project coverage and do not reduce
  project or patch coverage without an explicit, documented, human-approved
  exception. Run `just coverage` after changing production code, validation
  rules, or control flow, and inspect line and branch misses in every changed
  production file and the Codecov patch report when available. New or
  modified behaviour needs focused normal, boundary, failure, and
  short-circuit tests. Never weaken assertions, add coverage exclusions, or
  remove meaningful tests to improve the number.

## Dependencies and lockfiles

- Prefer established standards, the standard library, and mature, actively
  maintained libraries over custom infrastructure or algorithms. Evaluate
  reuse before implementing a significant storage format, serializer,
  scheduler primitive, protocol, or numerical utility.
- Reuse is not automatic dependency approval. Before adding a library, assess
  scientific semantics, performance and memory behaviour, scalability,
  platform and Python support, maintenance health, security, licence,
  interoperability, worker-image cost, serialization behaviour, and whether
  existing dependencies or the standard library suffice. Additions need a
  reason and compatibility bounds.
- Write custom code only when established options fail a concrete requirement
  or a small implementation is materially clearer and lower risk. Record the
  comparison in the plan, `LOG.md`, or an ADR in proportion to its
  significance, and hide unavoidable custom infrastructure behind a narrow
  tested boundary.
- Declare dependencies only in `pyproject.toml` (no `requirements.txt`,
  Poetry, or other environment manager). Use `uv add <package>`,
  `uv add --dev <package>`, or `uv add --group docs <package>`. Run `uv lock`
  after manual metadata changes and `uv lock --upgrade` only when an upgrade
  is intended. Commit `pyproject.toml` and `uv.lock` changes together.

## Documentation and notebooks

- Keep documentation within the Diátaxis sections: `tutorials/`, `how-to/`,
  `reference/`, and `explanation/`. Add pages to `mkdocs.yml` navigation; the
  strict `just docs-build` treats warnings as failures. Keep API paths aligned
  with importable modules under `src/hebog/`.
- Keep interactive examples exclusively as Marimo Python files under
  `notebooks/`, validated with `just marimo-check`. Keep astronomer workflows
  short and based on the public API; do not assemble internal scientific
  stages to compensate for a missing public boundary. Use runnable examples to
  expose integration gaps early, and inspect rendered outputs when changing
  plots or notebook behaviour; visual inspection is diagnostic, not
  qualification.

## Changes, releases, and handoff

- Prefer frequent, coherent experimental `0.x` releases, following the plan's
  delivery policy and its separate merge, package, scientific-qualification,
  and Rapthor-deployment checklists.
- Ownership is fixed. Agents investigate, implement, validate, update
  documentation, `LOG.md` and the plan, create local commits, and prepare
  review material and recommendations. Humans push, open and merge pull
  requests, run and manually inspect notebook comparison refreshes, make
  scientific dispositions and priority decisions, and configure release
  infrastructure. Release Please updates versions, the changelog and release
  notes and creates tags and GitHub releases; neither agents nor humans edit
  release-managed files by hand unless the task is about the release tooling.
  Mark each plan task with its owner.
- Create a local commit for each coherent, validated, reviewable change, with
  its implementation, tests, and documentation together. Do not combine
  unrelated milestones or experiments. Never push commits or tags.
- Use short, imperative, user-informative Conventional Commit subjects, for
  example `feat: add catalogue comparison reports`; Release Please builds
  release notes from them. Add a concise developer body covering motivation,
  design or compatibility consequences, and validation performed. Keep
  scientific datasets, measurements, and gate evidence in `LOG.md`.
- Preserve a feature-flagged PyBDSF fallback in Rapthor until the complete
  acceptance matrix passes.
- Lead handoffs with the observable outcome, what the checks establish, the
  remaining uncertainty, checks not run, and the next authorized action or
  required decision. State the candidate and evidence scope when interpreting
  scientific results. Test counts, coverage, successful execution, and
  historical stage passes do not establish current parity or release
  readiness.

Before handing off a meaningful change:

1. Inspect the full diff and remove unrelated or generated files.
2. Run the narrowest relevant tests and linter while iterating.
3. Run `just coverage` for production changes and check project and patch
   coverage as described under Tests.
4. Run equivalence tests for scientific changes, serial and Dask execution
   for scheduler-facing changes, and reproducible before/after benchmarks for
   performance claims.
5. Build docs for public API, configuration, plan, or workflow changes.
6. Update `LOG.md` and the plan as described under Working principles.
7. Run `just check`, plus `just package-smoke-test` for packaging changes.
8. Review the final diff against `CODE_REVIEW.md`.
9. Run `just pre-commit` after all final edits and immediately before staging.
   It applies the fast lint and formatting fixers until they pass before running
   the slow hooks; while iterating, run `just pre-commit-fast` alone.
   Inspect hook-applied changes, including JSON formatting, rerun validation
   they invalidate, and rerun `just pre-commit` until it passes without
   modifying anything. Never commit a known-failing hook state.
10. Create the atomic local commit, then inspect the commit and working tree.
    Do not push it.
