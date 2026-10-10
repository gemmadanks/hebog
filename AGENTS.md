# AGENTS.md

Applies to the entire repository. Follow the linked guidance for the work at
hand; this file holds common rules and points to detailed contracts.

## Repository overview

Hebog is a Dask-aware radio-continuum source finder for any telescope, prioritising
LOFAR, SKA-Low and SKA-Mid. Its first intended consumer is Rapthor's `filter_skymodel`:
reproduce the PyBDSF behaviour/products that step needs, prove scientific equivalence,
and meet the runtime gate. Maintainability, extensibility and interoperability are
requirements; the scientific library must work without Rapthor, Prefect or LSMTool.

`find_sources(request, config, executor)` supports Serial, Thread and caller-owned
Dask execution, including optional flat-noise RMS products. Rapthor records and a
catalogue codec exist; the full backend is planned. Out-of-core 100,000² images across
100 to several hundred nodes are design targets, not demonstrated capabilities.
Read the [delivery plan](plans/source-finder-implementation.md) and
[capability status](docs/reference/release-status.md) for current limits/evidence;
unmerged work or passing tests do not establish readiness.

Code: `src/hebog/`; tests: `tests/`; runners: `scripts/benchmark/` and
`scripts/validation/`; configuration: `config/`; MkDocs: `docs/`; Marimo: `notebooks/`.
Adjacent PyBDSF/Rapthor checkouts are references only: never hard-code their paths
in package code or normal tests.

## Working principles

- Make the smallest coherent change; follow existing structure/naming. Inspect
  diffs before/after editing and preserve unrelated work.
- Carry authorization forward within scope; own routine investigation, fixes and
  checks. When scope, scientific disposition, resources or an external action needs
  a new decision, explain the boundary and recommend a concrete action. Continue
  independent work while clarifying. Use one writing agent by default; delegate
  only independent, bounded work.
- Prefer simple stdlib/existing-dependency primitives before platform-specific
  tricks, raw syscalls, `ctypes`, metaprogramming or custom protocols. Use complexity
  only for a demonstrated unmet guarantee, record why, and replace it when a
  materially simpler equivalent exists.
- Change tests with behaviour and user docs with APIs, schemas, setup or workflows.
  Pre-production `0.x` has no backward-compatibility guarantee: remove obsolete APIs,
  stores, configuration and tests directly. No shims, deprecation periods, legacy
  readers or migrations unless explicitly requested for an interface. Document
  breaking changes and make stale artifacts fail clearly; preserve scientific
  compatibility, reproducibility and the supported platform matrix.
- Keep generated FITS/catalogues/results/profiles/production data, `site/`, `dist/`
  and `build/` out of Git. Small redistributable `tests/data/` fixtures need provenance.
  Keep credentials, tokens, private dataset locations and cluster secrets in
  documented environment variables or ignored local configuration.

## Plans and records

- Use the lightest planning level in `PLAN.md`. The source-finder plan is authoritative:
  keep current state, remaining tasks and governing rules, not execution narratives
  or task progress annotations. Remove completed tasks; record outcome, rationale and
  checks in commits. Restate historical decisions only as current constraints.
- Update the plan for changes to scope, sequencing, milestones, baselines, scientific
  thresholds, gates, architecture or risks. Record significant scientific/architecture
  decisions before implementation; use the [ADR template](docs/architecture/adr/template.md).
- Update the plan summary and [progress against goals](docs/reference/progress-against-goals.md)
  together: candidate, strongest applicable evidence, blockers, authorized next action
  and deferred work. Replace stale summaries rather than contradicting them. Store
  measurements in versioned evidence/controlled storage; commits link exact identities
  and scoped gate outcomes.
- `LOG.md` is a historical archive: **do not add entries**. Git records completed
  work, repairs, deviations and decisions; ADRs record architecture decisions;
  release notes describe user-visible changes.
- Iterate locally within plan budgets; reserve long campaigns/cluster benchmarks for
  named qualification steps without blocking development. Before scientific/campaign
  repairs follow the [repair rules](plans/source-finder-implementation.md#collaboration-and-repair-decisions):
  state the decision before each repair, reassess after two ineffective repairs,
  and carry authorization forward within scope.

## Setup and checks

Run `uv sync --all-groups`. Prefer `just` recipes (`just --list`); the
[contributor guide](docs/how-to/index.md#checks-and-test-lanes) describes lanes/commands.
If `just` is unavailable, use its `justfile` command. Focused tests use
`uv run pytest -q <test-path>`.

Use focused checks and `just pre-commit-fast` while iterating, then final
`just pre-commit`. Reuse passes for unchanged code/config/environment; rerun checks
invalidated by edits, conflicts or environment changes. Reserve `just ci` and long
campaigns for named gates. Local checks do not establish hosted platform-matrix
success. Equivalence/Rapthor runs may need an integration container; do not add
heavyweight production tools to the core runtime solely for tests.

## Architecture and Python

Follow the [architecture](docs/architecture/index.md),
[distributed execution contract](docs/architecture/distributed-execution.md) and
[quality principles](docs/explanation/quality-attributes.md).

- Dependencies point inward. Algorithms, domain records and `science/` know no
  executors, I/O, adapters, orchestration frameworks or process-wide configuration.
  Stages/public orchestration accept an executor. Keep sequencing in
  `stages/composition.py`, scientific composition/records in `science/`, and public
  validation/publication in `public_api.py`. Justify layer changes in
  `tests/unit/test_architecture.py`; do not bypass it.
- Keep FITS/catalogue/scheduler integration at explicit boundaries. Rapthor/LSMTool
  names, filters, filenames and failure translations belong in a versioned adapter
  depending on the scientific API. A serial workflow must not import/construct
  Dask, Prefect, Rapthor or LSMTool objects.
- Library imports define types/immutable constants without data I/O, work discovery,
  process changes, networking, clients/clusters or computation. `__main__.py` is the CLI
  exception. Importing `hebog`/`hebog.pipeline` must defer concrete schedulers.
- Keep science pure where practical: arrays/immutable configuration in, arrays/records
  out. Use vectorised NumPy/SciPy or measured compiled, GIL-releasing kernels; no Python
  pixel/RMS-window loops. Read images once where possible; reuse background, RMS,
  convolution, WCS and beam products across stages/scales. Control copies/dtypes;
  `float64` to `float32` needs scientific-equivalence evidence.
- Callers own schedulers/resource budgets; no private clusters/multiprocessing pools
  by default. Follow [ADR-010](docs/architecture/adr/010-scale-hebog-independently-of-its-integrations.md):
  shared storage, admitted core/memory budgets, native thread limits and caller-named
  resources, without fixed/dedicated worker assumptions. Size batches/caches with
  concurrency headroom; no hard-coded tiny tiles or resource-dependent science.
- Keep requests/results/tasks small and exactly serializable: no open files, clients,
  mutable pipeline state or repeatedly embedded full images. Send WCS as its original
  header text and rebuild on workers; Astropy serialization reformats the header.
- `SerialExecutor` is the deterministic reference. Executors/stores/adapters share
  contracts/results; exercise Serial, Thread and Dask in parametrized contracts,
  with Dask cases in integration tests.
- Batch coarsely for occupancy and scheduler/I/O amortization. Graphs scale with
  tiles/stages, not pixels, RMS windows or small islands. Use bounded summaries and
  hierarchical reduction/reconciliation, never image-sized scheduler state or a full
  large plane on one worker/in Dask. Tiles have deterministic non-overlapping cores,
  global coordinates and the smallest reviewed stage halo; reconcile labels/sources/
  products independently of worker count/order.
- Zarr is the sole intermediate-plane backend; FITS is ingress/final format. Small
  inputs use one tile/chunk and serial execution; reduce Zarr overhead rather than
  adding a backend. Batch nonlinear fits by island cost, use moments to initialize,
  and skip pixels irrelevant to accepted catalogue entries.
- Version output schemas; use paths/plain metadata for retry/resume. Follow
  [public products](docs/reference/public-products.md): claim new destinations without
  overwrite, publish atomically, cancel/drain work before failure cleanup, and verify
  schemas/roles/checksums when reading. Directory existence is not completion. Optional
  flat-noise input supplies its own RMS/provenance without changing true-sky catalogue/
  RMS/mask; pair validation and compatibility belong at public/adapter boundaries.
- Add narrow executor/image-source/product-sink/compatibility seams only at demonstrated
  variation points; avoid speculative registries, plugin frameworks, service locators
  and scattered integration conditionals.
- Support Python 3.12–3.14, not just `.python-version`. Annotate new/changed functions;
  use absolute `hebog` imports in tests/examples. Prefer small functions, composition,
  `Path`, context managers, iterators/comprehensions, dataclasses and structural protocols
  over Java-style getters/services/factories/interfaces. Small public records are immutable.
- Use descriptive glossary names, not unexplained abbreviations, generic `data`/`manager`
  or unclear booleans. Keep cohesive modules and one useful abstraction level per
  function, without metric-driven splitting. Expose dependencies, effects, units,
  coordinates, shapes, ownership, mutability and failures; no hidden globals or
  environment-driven science. Remove accidental duplication; abstract stable concepts.
- Keep public APIs small, typed, documented and versioned; export from `__init__.py`
  only intentionally. Use Google-style docstrings and valid doctests; comments explain
  numerical assumptions, units, shapes, halos and resource constraints. Readability,
  maintainability, extensibility and testability are acceptance criteria, including
  for performance changes.

## Test-driven development and validation

**Use TDD** for public contracts, pure scientific kernels, schemas, matching, errors
and executor semantics. Write and run a test failing for the intended missing
behaviour, not an import/fixture/environment failure; implement the smallest serial
behaviour, refactor, then add executor conformance and scientific comparisons.
Before bug fixes, add regression tests at the escaped boundary when practical.
If test-first is impractical, record why in the plan/handoff and add the behavioural
test in the same commit. Never commit red unless explicitly requested. See
[Develop test-first](docs/how-to/index.md#develop-test-first).

- Use `tests/unit/`, `contract/`, `integration/` (Dask/FITS), `equivalence/` (PyBDSF),
  `acceptance/` (Rapthor) and `benchmark/` (timing/scalability). Strict markers are in
  `pyproject.toml`: `contract`, `integration`, `equivalence`, `acceptance`,
  `qualification`, `benchmark`, `scalability`, `slow`, `requires_data`.
  Units require no scheduler, downloads or test order.
- Public-behaviour placeholders become normal assertions and `implemented` manifest
  entries in the same commit (`config/contracts/phase-0-public-behaviours.json`);
  records/scaffolding alone do not implement behaviour.
- Warnings are errors and xfails strict. Use `pytest.warns` for expected warnings;
  fix others. Filter only unavoidable third-party warnings on the narrowest test,
  by category/stable message, with explanation. Known xfails name their owning plan
  entry. Exemptions/allow-lists must assert they still match, preventing vacuous rules.
- Test observable behaviour/errors/public validation, including a small complete
  API/product workflow early in each milestone/repair. Assert every contract behaviour
  through every implementation/entry point, preferably parametrized. Use Given/When/Then
  acceptance tests; no Gherkin unless domain experts will author/review feature files.
- Use analytic truth before generated truth, serial before executor comparisons,
  and frozen PyBDSF only for compatibility. Test matchers/reports independently;
  use physically bounded property-based numerical invariants/boundary combinations.
- Milestones cover empty/all-NaN images, negative backgrounds/invalid pixels, compact
  sources across SNR, blends/multi-component islands, extended/multiscale emission,
  edges/non-square images, varied beams/WCS/pixel scales/units, and tile-edge/corner
  crossings. Prove one/many-tile equivalence on small analytic data before scaling;
  vary partition origin, tile shape, workers, completion order and retries.
  Use deterministic fault injection; reserve worker termination, spilling, private
  data and wall-time gates for controlled runners.
- Give datasets development/regression/qualification roles; never tune on held-out
  qualification results. Record generator version, config and seeds. Frozen expectations
  stay immutable during tests; regenerate separately with documented commands,
  checksums, revisions and scientific review.
- CI covers Linux/macOS/Windows; Windows is not exercised locally. Compare paths with
  `Path.as_posix()`, not literal separators or `str(path)`; avoid line-ending,
  temp-layout and filename-case assumptions.
- Keep ≥80% branch-aware project coverage. Reducing project/patch coverage needs an
  explicit documented human-approved exception. Run `just coverage` for production,
  validation-rule or control-flow changes; inspect changed files' line/branch misses
  and Codecov patch reports when available. Cover normal/boundary/failure/short-circuit
  paths; never weaken assertions, exclude coverage or delete meaningful tests for a number.

## Scientific and performance gates

- Follow the plan's dataset matrix/metrics and bounded development screen before long
  campaigns/replays. Equivalence means Rapthor-required behaviour, not bitwise PyBDSF
  equality, single-image agreement or counts. Compare Thread/Dask with Serial first;
  report low-SNR crossings as completeness/reliability changes, not hidden unmatched rows.
- Follow peer-reviewed best practice and source-finder challenges. Observatory consensus
  guides but does not override governed truth; no pipeline is ground truth. Document
  departures with analytic/injected-truth evidence and renewed human scientific review
  before promotion. Independently reimplement documented behaviour; never copy PyBDSF
  code, and retain paper/algorithm/data attribution. Never weaken thresholds, omit
  extended processing or silently change semantics for speed.
- Optimize from profiles/scale evidence, with typed boundaries, a readable serial oracle
  and recorded reasons for complexity; scientific suites must pass. Minimum deployment
  gate: ≥50% faster matched median for complete Rapthor `filter_skymodel` against exact
  pinned PyBDSF `master`, under the plan's confidence rule; confirm its release ratio
  once before 1.0. Optimize latency/throughput across sizes beyond that minimum.
  Kernel timing is insufficient: include FITS, catalogues, Dask and filtering in isolated,
  matched environments; never substitute a reference revision/release.
- Use ≥5 measured repetitions after warm-up, medians and dispersion, without unrelated
  workloads. Use the frozen performance ladder, plan-controlled subset/budgets, both
  sides of crossovers and sparse/normal/dense/extended workloads. Compare affected/adjacent
  anchors with the reviewed Hebog curve; refresh the full ladder at qualification.
  Statistically supported >5% tier regressions need approved documented trade-offs.
- Follow [evidence records](docs/reference/evidence-documents.md): dataset identities/
  checksums; Hebog/PyBDSF/Rapthor/Python/dependency revisions; config/output mode;
  workers/threads/affinity/memory; wall/CPU time, peak RSS, tasks/transfers/spill;
  logical image/plane sizes, cores/halos/partitions, boundary volume, scheduler load,
  occupancy/storage throughput/
  headroom/scaling; warm-up policy and every run. Use `hebog.validation.evidence` in
  ignored `benchmark-results/` or controlled storage; commit compact JSON summaries and
  reproducing commands. Missing instrumentation needs a reason, never fabricated zero.
  `reviewed` requires protocol, environment and scientific-result review.
- For native code, follow the [assessment](docs/explanation/native-code-assessment.md):
  NumPy/SciPy, then profiled Numba; 10% profile, 2× kernel and 5% end-to-end gates unless
  resolving failed memory/scalability; accepted ADR selecting Rust/PyO3/maturin for new
  kernels or C++/pybind11 for mature libraries. Coarse typed array boundaries specify
  dtype/shape/strides/alignment, ownership/mutability/errors/copy permission, with GIL
  release and thread budgets. Preserve Python/Numba oracle/contracts, exception safety
  and sanitizer/Miri or equivalent evidence. Native code cannot become mandatory before
  wheels, isolated installs, source builds, licence/provenance and fallback pass all
  supported platforms/Python ABIs/NumPy versions; normal installs need no compiler.
  Keep FITS, WCS, schemas, config, adapters, workflows and Dask graphs in Python.

## Dependencies and documentation

- Evaluate standards, stdlib and mature maintained libraries before custom formats,
  serializers, scheduler primitives, protocols or numerical utilities. Assess science,
  speed/memory/scale, platform/Python support, maintenance, security/licence,
  interoperability, worker-image cost and serialization. New libraries need rationale/
  bounds; custom code needs an unmet concrete requirement or a materially clearer,
  safer small implementation. Record comparisons in commits/ADRs; keep it narrow/tested.
- Declare dependencies only in `pyproject.toml` using `uv add` (or `--dev`/`--group docs`).
  Run `uv lock` after manual metadata edits; upgrade only intentionally. Commit metadata/
  lock together; no alternate environment manager. Align uv installers/hooks with CI
  and `tests/unit/test_uv_version.py`, including reusable workflows; respect build bounds
  and avoid unrelated pins/lock upgrades. `hebog.validation` is checkout-only, excluded
  from wheels and forbidden in production imports.
- Use Diátaxis docs, `mkdocs.yml` navigation, strict `just docs-build` and importable API
  paths. Interactive examples are Marimo Python files only in `notebooks/`, checked with
  `just marimo-check`. Keep astronomer workflows short and public-API based; do not use
  internal stages to compensate for missing public boundaries. Use runnable examples
  to reveal gaps; inspect rendered plot/notebook changes, without claiming qualification.

## Changes, releases, and handoff

Agents investigate, implement, validate, update docs/plans, create coherent local
commits and prepare review material. Humans publish by default; only explicit user
requests delegate pushes/PR updates. Humans merge, run/inspect notebook refreshes,
decide science/priorities and configure release infrastructure. Mark plan-task owners.
Release Please owns versions, changelog, release notes, tags and GitHub releases;
edit release-managed files only for release-tooling tasks. Prefer small experimental
`0.x` releases using separate plan merge/package/scientific/deployment checklists.
Retain Rapthor's feature-flagged PyBDSF fallback until the acceptance matrix passes.

### Branches, worktrees and pull requests

- Check path/branch/HEAD/upstream/diff before editing. Fetch current refs for main/PR
  comparisons. Reuse the task's clean worktree or isolate it; preserve other worktrees,
  remembering shared refs/configuration. Use `--no-track` for feature branches/worktrees
  from remote branches; published upstreams match the feature branch. Verify before
  recommending a push, especially LazyGit.
- For stacks, identify own commits/parents already on main; replay only remaining work.
  Preserve both sides' intent in conflicts; check `git range-diff` and the final base
  diff for dropped/duplicated changes. Diagnose CI on the current PR head: failed jobs/
  logs, reusable workflows, narrow reproduction, aggregate required checks and shards.
  Old failures/passing unit jobs do not establish current CI success.
- Never infer publishing authority from implementation/review/commit requests. Authorized
  rebase pushes use an explicit lease against the verified remote tip; stop if it changed,
  and never use plain `--force`.

### Commit messages

Write concise, self-contained messages for **future developers: our future selves
and reviewers**, without assuming they read the conversation.

- Use short imperative Conventional Commit subjects naming the change; Release Please
  uses them. Avoid vague titles/task numbers alone. After a blank line, explain problem,
  resulting behaviour and rationale; a trigger/before-after example can help. Obvious
  typos need no body. Include consequential trade-offs, decisions, compatibility and
  limitations, not file inventories or irrelevant abandoned work.
- State validation commands/results and material omissions/reasons. Science/performance
  claims need baseline, config, key result, gate/scope and exact evidence links, not full
  reports. Historical LOG references remain valid. Link useful issues/PRs/ADRs while
  summarising context; cite commits by hash/subject and use searchable domain names.
- Mark breaking changes with `!` or `BREAKING CHANGE:` and explain contracts/caller actions.
  Keep implementation/tests/docs in one atomic validated commit; do not combine
  unrelated milestones or experiments.
- Prepare a copyable squash subject/body for the complete final PR, including earlier
  related commits, in the handoff/PR description. Humans check the actual message retains
  problem, outcome, rationale, decisions/breaking changes, validation/omissions and
  references. Do not assume GitHub preserves branch messages; describe the final change
  coherently for future developers.

Before handing off a meaningful change:

1. Inspect the full diff; remove unrelated/generated changes. Update required plan/status/
   evidence summaries; record completed work in commits, not LOG.
2. Run focused tests/lint while iterating; coverage for production/validation/control flow,
   equivalence for science, Serial/Thread/Dask for schedulers, before/after benchmarks
   for performance claims, docs for API/config/plan/workflows, and installed-wheel smoke
   for packaging. Run `just check` or equivalent final pre-commit checks once.
3. Self-review against `CODE_REVIEW.md`, fix findings and rerun invalidated checks.
4. Immediately before staging, run `just pre-commit` after all edits. Inspect fixer changes
   (including JSON), rerun invalidated checks and repeat until it passes without changes.
   Never commit failing hooks. Create the atomic local commit; inspect it and the tree.
5. Push only if explicitly authorized. Handoff outcome, checks/what they establish,
   uncertainty, omissions/reasons, next action/decision, worktree, branch, commit,
   publication status and squash draft. Interpret science with candidate/evidence scope;
   counts, coverage and historical passes do not prove current parity/readiness.
