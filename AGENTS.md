# AGENTS.md

This file applies to the entire repository.

## Repository overview

Hebog is a Dask-aware radio-continuum source finder for SKA Science Data
Processor pipelines. Its first production consumer is Rapthor's
`filter_skymodel` step. The implementation is intentionally narrower than
PyBDSF: reproduce the behaviour and products Rapthor uses, demonstrate
scientific equivalence, reduce the complete filter step's matched median wall
time by at least 50% relative to the released PyBDSF version used by Rapthor,
and also outperform a pinned PyBDSF `master` reference. The architecture must
scale out of core to 100,000-by-100,000 images and distribute work across 100
to several hundred nodes through Rapthor's existing Dask cluster. Production
nodes are expected to have hundreds of GB of RAM.

The durable
[`plans/source-finder-implementation.md`](plans/source-finder-implementation.md)
is the authoritative delivery plan. Update it when a milestone, benchmark
baseline, scientific threshold, architecture decision, or risk changes.
`PLAN.md` remains the reusable template for other work plans.
Record material execution progress, evidence, deviations, and immediate next
steps chronologically in [`LOG.md`](LOG.md).

The repository contains:

- the Python package in `src/hebog/`;
- scientific algorithms in `src/hebog/algorithms/`;
- scheduler-independent execution policies in `src/hebog/executors/`;
- serializable public records in `src/hebog/data_models/`;
- unit, integration, equivalence, and benchmark tests in `tests/`;
- reproducible benchmark tooling in `scripts/benchmark/`;
- checked-in algorithm and benchmark configuration in `config/`;
- MkDocs documentation in `docs/`;
- Marimo notebooks in `notebooks/`.

Adjacent checkouts of PyBDSF and Rapthor are development references only.
Never hard-code those paths in package code or normal tests.

## Working principles

- Make the smallest coherent change that satisfies the task.
- Preserve unrelated work in the working tree. Inspect `git diff` before and
  after editing, and do not revert changes you did not make.
- Follow the existing structure and naming conventions instead of introducing
  a second tool or parallel configuration.
- Add or update tests when behaviour changes. Update user-facing documentation
  when public APIs, setup steps, output schemas, or workflows change.
- Use the lightest planning level in `PLAN.md`; keep the source-finder plan
  current for project milestones and scientific or performance decisions.
- Append material completed work and validation evidence to `LOG.md`; do not
  duplicate routine commits or user-visible release notes there.
- Use one writing agent by default. Delegate only independent, bounded work.
- Review meaningful changes against `CODE_REVIEW.md` before handoff.
- Record architecturally significant decisions with an ADR based on
  `docs/architecture/adr/template.md`.

## Source-finder constraints

- Do not copy PyBDSF implementation code. Reimplement documented scientific
  behaviour with new, independently structured code and retain attribution for
  papers, algorithms, and test data.
- Do not claim PyBDSF equivalence from a single image or source-count
  comparison. Use the dataset matrix and metrics in the implementation plan.
- Do not claim a speedup from isolated kernel timing alone. The primary
  performance gate is the median wall time of Rapthor's complete
  `filter_skymodel` step against both the released PyBDSF version used by
  Rapthor and the pinned performance-improved PyBDSF `master` reference.
- Do not introduce an image-sized algorithm that requires a complete large
  plane on one worker. A small image is one tile; large images use explicit
  cores, stage-specific halos, bounded summaries, and hierarchical
  reconciliation.
- Do not create one Dask task per pixel, RMS window, or small island. Graph
  size must scale with tiles and scientific stages, and reductions must remain
  hierarchical rather than gathering image-sized state on the scheduler.
- Do not weaken detection thresholds, skip extended-source processing, or
  silently change output semantics to meet a runtime target.
- Do not use Python loops over pixels or RMS windows in production kernels.
  Use vectorised NumPy/SciPy operations or compiled, GIL-releasing kernels and
  measure them.
- Do not start a private Dask cluster or multiprocessing pool inside the
  library by default. Rapthor owns the top-level scheduler and resource budget.
- Never send open files, scheduler clients, mutable pipeline state, or
  repeatedly embedded full images through Dask tasks. Public requests and
  results remain small and serializable.
- Generated FITS products, catalogues, benchmark results, profiles, and
  production data stay out of Git. Small redistributable fixtures may be added
  under `tests/data/` with provenance.

## Setup and commands

Dependencies and environments are managed with uv. Install the complete
development environment with:

```bash
uv sync --all-groups
```

Prefer the `just` recipes because they document the intended workflow:

```bash
just test-unit          # fast deterministic tests
just test-integration   # Dask and FITS integration tests
just test-equivalence   # frozen PyBDSF comparisons
just test-acceptance    # Rapthor-facing behaviour scenarios
just test-qualification # held-out scientific cases on an approved data host
just test-benchmark     # controlled performance runs
just test-scalability   # controlled 100-to-200-plus-node scale runs
just marimo-check       # validate Marimo notebooks
just lint               # Ruff checks
just format             # Ruff formatting
just format-check       # verify formatting without changes
just type-check         # Pyright
just check              # fast non-mutating handoff checks
just docs-build         # strict MkDocs build
just package-smoke-test # build and import the wheel in isolation
just ci                 # comprehensive local CI equivalent
```

For a focused test, run pytest through uv, for example:

```bash
uv run pytest -q tests/unit/test_config.py
uv run pytest -q tests/integration/test_dask_executor.py
```

If `just` is unavailable, run the corresponding `uv run ...` command from the
`justfile`. PyBDSF equivalence and Rapthor end-to-end runs may require a
separate integration container; do not add heavyweight production tools to the
core runtime solely for tests.

## Architecture rules

- Keep scientific functions pure where practical: arrays and immutable
  configuration in, arrays or records out.
- Keep FITS, catalogue, Rapthor, and scheduler integration at explicit
  boundaries.
- Maintain `SerialExecutor` as the deterministic reference. Local and Dask
  executors must produce equivalent results.
- Prefer coarse Dask batches that amortise scheduler and I/O overhead while
  leaving enough runnable work for occupancy. Memory-rich scale runs may use
  larger batches than local tests. Never create one scheduler task per pixel,
  RMS window, or small island.
- Let algorithms accept an executor rather than importing a global client. A
  Dask executor may receive an existing client, but scheduler objects must not
  enter public result records.
- Read each image once where possible. Reuse background, RMS, convolution,
  WCS, and beam products across stages and wavelet scales.
- Give every tile a deterministic non-overlapping output core, explicit global
  coordinates, and the smallest reviewed halo required by its stage. Reconcile
  labels, sources, and products independently of worker count and task order.
- Keep large planes in bounded window-readable files or a chunk-addressable
  store. Never publish a complete 100,000-by-100,000 plane to Dask.
- Size tile batches and worker caches from admitted memory metadata. Exploit
  memory-rich production nodes while reserving headroom for concurrent work;
  do not hard-code one tiny tile size or let resource sizing change scientific
  ownership and results.
- Control array dtype and copies deliberately. A change from `float64` to
  `float32` requires scientific-equivalence evidence, not only a performance
  result.
- Batch nonlinear fits by estimated island cost. Use moments for
  initialization and avoid fitting pixels that cannot affect an accepted
  catalogue entry.
- Version output schemas. Rapthor-facing outputs use paths and plain metadata
  so tasks can be retried and resumed.

## Scientific validation

Scientific equivalence means matching the behaviour required by Rapthor, not
bitwise equality with PyBDSF. Every algorithm milestone needs tests for:

- empty and all-NaN images;
- negative backgrounds and invalid pixels;
- isolated compact sources over a range of signal-to-noise ratios;
- close blends and multi-component islands;
- extended and multiscale emission;
- edge sources and non-square images;
- different beams, WCS orientations, pixel scales, and image units.
- sources and islands crossing tile edges and corners;
- partition, tile-shape, worker-count, task-order, and retry invariance.

Compare Dask results against the serial reference before comparing either with
PyBDSF. Report low-SNR threshold crossings as completeness and reliability
changes rather than hiding them as unmatched rows.

## Performance validation

Performance changes must record:

- dataset identity and checksums;
- Hebog, PyBDSF, Rapthor, Python, and dependency revisions;
- configuration and output mode;
- worker count, threads per worker, CPU affinity, and memory limits;
- wall time, CPU time, peak RSS, task count, and Dask transfer/spill metrics;
- logical image and plane sizes, tile cores and halos, partition count,
  boundary-summary volume, scheduler load, worker occupancy, storage
  throughput, node/worker RAM and headroom, and strong/weak-scaling efficiency;
- warm-up policy and every measured repetition.

Use at least five measured repetitions after warm-up, compare medians, report
dispersion, and retain machine-readable results. Benchmark exact released and
`master` PyBDSF revisions in isolated, matched environments; never substitute
one for the other. Avoid concurrent unrelated workloads. End-to-end speedups
include FITS I/O, catalogue generation, Dask overhead, and Rapthor filtering.
Performance claims must satisfy the confidence rule in the implementation
plan. An optimization is acceptable only when the relevant scientific suite
passes.

## Python conventions

- Put production code under `src/hebog/` and use absolute `hebog` imports in
  tests and examples.
- Python 3.11 through 3.14 is supported. Do not rely only on the version in
  `.python-version`.
- Use four spaces, UTF-8, LF endings, a final newline, and type annotations for
  new or changed functions.
- Ruff is the formatter and linter; Python line length is 79.
- Use immutable dataclasses for small public records where practical.
- Follow Google-style docstrings. Python examples are collected as doctests
  and must remain valid.
- Export names from `src/hebog/__init__.py` only when intentionally part of the
  top-level public API.
- Keep comments focused on numerical assumptions, units, array shape, halo
  requirements, and scheduler/resource constraints.

## Tests

- Place unit tests in `tests/unit/`, Dask/FITS boundary tests in
  `tests/integration/`, PyBDSF comparisons in `tests/equivalence/`,
  Rapthor-facing scenarios in `tests/acceptance/`, and timing and controlled
  scalability tests in `tests/benchmark/`.
- Use TDD for public contracts, pure scientific kernels, schemas, matching,
  error behaviour, and executor semantics: add a test that fails for the
  intended reason, implement the smallest serial behaviour, refactor, then add
  executor conformance and scientific comparisons.
- Mark tests with `integration`, `equivalence`, `acceptance`, `qualification`,
  `benchmark`, `scalability`, `slow`, and `requires_data` as applicable.
  Marker names are strict.
- Unit tests must not require a running scheduler, download data, or depend on
  execution order.
- Use analytic truth before generated truth, the serial implementation before
  executor comparisons, and frozen PyBDSF products only as a compatibility
  oracle. Test matchers and comparison reports independently.
- Use property-based tests for numerical invariants and boundary combinations.
  Bound generated arrays and metadata to physically meaningful ranges.
- Test one-tile versus many-tile equivalence on small analytic data before
  using the controlled scalability lane. Put sources on every edge/corner
  topology and vary partition origin, tile shape, completion order, and retry.
- Give every dataset a `development`, `regression`, or `qualification` role.
  Do not tune with held-out qualification results. Store generator version and
  configuration as well as random seeds.
- Frozen expected products are immutable during tests. Regenerate them only
  through a separate documented command with checksums, tool revisions, and
  scientific review.
- Write lightweight acceptance tests in readable Given/When/Then form. Do not
  add a Gherkin framework unless domain experts will review or author feature
  files.
- Test observable behaviour, error messages, and public-boundary validation.
- Add a regression test before fixing incorrect behaviour when practical.
- Use deterministic fault injection for normal executor tests; reserve actual
  worker termination, spilling, private data, and wall-time gates for
  controlled runners.
- Run the narrowest relevant lane while iterating, then `just check` for normal
  code changes. Run equivalence tests for scientific changes and reproducible
  before/after benchmarks for performance claims.

## Dependencies and lockfiles

- Declare dependencies in `pyproject.toml`; do not add `requirements.txt`,
  Poetry, or another environment manager.
- Use `uv add <package>` for runtime dependencies, `uv add --dev <package>` for
  development dependencies, and `uv add --group docs <package>` for docs-only
  dependencies.
- Commit `pyproject.toml` and `uv.lock` changes together.
- Use `uv lock` after manual metadata changes and `uv lock --upgrade` only when
  an upgrade is intended.
- Dependency additions require a reason, compatibility bounds, and
  consideration of worker image size and serialization behaviour.

## Documentation and notebooks

- Keep documentation within the existing Diátaxis sections: `tutorials/`,
  `how-to/`, `reference/`, and `explanation/`.
- Add pages to `mkdocs.yml` navigation and build with `just docs-build`; the
  strict build treats warnings as failures.
- Keep API paths aligned with importable modules under `src/hebog/`.
- Keep interactive examples exclusively as Marimo Python files under
  `notebooks/`.
- Validate Marimo notebooks with `just marimo-check` after changing them.
- `site/`, `dist/`, and `build/` are generated artifacts and must not be
  committed.

## Changes, releases, and handoff

- During plan execution, create local commits for each coherent, validated,
  reviewable change. Do not combine unrelated milestones or experiments.
- Use Conventional Commit subjects. Keep the subject short, imperative, and
  informative to users because Release Please uses it to generate release
  notes; for example, `feat: add catalogue comparison reports`.
- Add a concise commit body for developers. Explain the motivation, important
  design or compatibility consequences, and validation performed. Record
  scientific datasets, measurements, and gate evidence in `LOG.md` rather than
  overloading the commit body.
- Keep an implementation and the tests and documentation that establish its
  behaviour in the same commit when they form one coherent change. Do not
  commit a known-failing TDD red state unless the user explicitly requests it.
- Never push commits or tags. Leave all commits local so a human can review
  them individually and push them manually.
- Record significant architecture or scientific decisions in the
  source-finder plan before spreading them through the implementation.
- Use Git history for routine implementation detail. Record only material plan
  execution, scientific or performance evidence, gate outcomes, deviations,
  and cross-commit decisions in `LOG.md`.
- Preserve a feature-flagged PyBDSF fallback in Rapthor until the complete
  acceptance matrix passes.
- Do not make generated benchmark data the source of truth; store compact JSON
  summaries and reproducible commands.
- Never add credentials, private dataset locations, cluster secrets, or
  tokens. Use documented environment variables and ignored local config.
- Release Please manages version bumps and release notes. Do not manually edit
  release-managed files unless the task is specifically about a release.

Before handing off a meaningful change:

1. Inspect the full diff and remove unrelated or generated files.
2. Run targeted tests and the relevant linter.
3. Run equivalence tests for scientific changes.
4. Run reproducible before/after benchmarks for performance claims.
5. Test serial and Dask execution for scheduler-facing changes.
6. Build docs for public API, configuration, plan, or workflow changes.
7. Append material progress, evidence, deviations, and next steps to `LOG.md`.
8. Update the source-finder plan only when scope, sequencing, gates, decisions,
   or risks changed.
9. Run `just check`, plus `just package-smoke-test` for packaging changes.
10. Review the final diff using `CODE_REVIEW.md` and report checks not run.
11. Create the atomic local commit after validation and review, then inspect
    the commit and working tree. Do not push it.
