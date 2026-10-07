# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

`AGENTS.md` (imported above) is the single source of truth for project goals,
working rules, the commit and handoff checklist, and the main `just` recipes.
Keep shared rules there; collaboration and repair-decision rules live in
`plans/source-finder-implementation.md`. This file adds only a code map and
Claude-specific notes; do not copy `AGENTS.md` content into it.

## Commands not covered in AGENTS.md

```bash
uv run pytest -q tests/unit/test_config.py::test_name   # one test
uv run pytest -q tests/unit -k "background and not dask" # by keyword
uv run pytest -q -n auto tests/unit                     # parallel (pytest-xdist)
uv run pytest -q --doctest-modules src/hebog/config.py  # one module's doctests
```

- `just test-unit` also collects the doctests in `src/hebog` and stops at the
  first failure (`--maxfail=1`), so an unrelated broken doctest can hide the
  test you care about. Run the specific file while iterating.
- `pytest` uses `--strict-markers`. A new marker must be added to
  `[tool.pytest.ini_options].markers` in `pyproject.toml`. The same table sets
  `xfail_strict` and `filterwarnings = ["error"]`, so a new warning fails the
  test that raises it.
- Pyright runs in `strict` mode over both `src/` and `tests/`, so test code
  needs type annotations too.
- Contract tests (`tests/contract/`) mark unimplemented specifications as
  `xfail(strict=True)`. If one starts passing, CI fails. Convert it to a normal
  assertion and set its `status` to `implemented` in
  `config/contracts/phase-0-public-behaviours.json`; do not remove the test.
- `just test-slow` runs the `slow` tests; one uncertainty-calibration test
  takes about three of its few minutes. CI runs them weekly and on manual
  dispatch (`.github/workflows/slow-tests.yaml`), not on pull requests.

## Code map

The public entry point is `hebog.find_sources(request, config, executor)`.

- `pipeline.py` holds the public error types and a thin `find_sources` that
  imports `public_api` lazily. This keeps `import hebog` free of I/O and
  scheduler imports. `executors/__init__.py` loads `DaskExecutor` lazily the
  same way (through `__getattr__`). Keep both lazy.
- `public_api.py` is the outer I/O layer. It reads and validates the FITS
  input, enforces the bounded preview size limit, plans partitions, runs
  each stage through the executor in turn, hands the published records to
  `public_science.py` for the terminal catalogues, and atomically writes
  versioned products through `io/`.
- `science/` holds the reviewed science the stages apply: the configuration
  and profile (`science/configuration.py`, `science/profile.py` and
  `resources/`), the composition records (`science/models.py`,
  `science/catalogue_rows.py`) and the catalogue-row kernels
  (`science/catalogues.py`). It imports no stage, executor or `io` module.
  `public_science.py` builds the terminal catalogues from the records the
  stages published.
- `stages/` contains the scheduler-facing stages `find_sources` runs, in
  order: background and detection, multiscale, support, publication,
  objects (component topology, fit parents, component fits), association,
  sources, islands and catalogue rows, with `batching.py` shared. They
  apply the kernels of `algorithms/` and `science/` with tiling, cores and
  halos, and batching through an `Executor`.
- `algorithms/` contains pure NumPy/SciPy kernels. They take arrays and
  immutable config and return arrays or records. They must not know about
  schedulers, I/O, or adapters.
- `executors/` defines the `Executor` protocol (`base.py`), the
  `SerialExecutor` reference, and a `DaskExecutor` that wraps a client owned
  by the caller.
- `data_models/` contains serializable public records. `config.py` holds the
  immutable `SourceFinderConfig` and the per-stage configs.
- `io/` holds the image-source protocol (`base.py`), bounded FITS input, the
  Zarr v3 intermediate plane store, and restartable FITS/JSON product
  materialisation.
- `adapters/` is the Rapthor compatibility boundary: serializable records and
  the eight-column PyBDSF-style catalogue codec. No adapter runs
  `find_sources` yet. It must not import Rapthor, Prefect, or LSMTool.
- `validation/` provides campaign, evidence, comparison, and dataset tooling
  for `scripts/` and tests. No production module outside `validation/` imports
  it, and wheels exclude it. Keep it that way, so the source finder stays
  independent of campaign validation.

Dependencies point inward:
`adapters → pipeline/public_api → stages → science → algorithms`, with
`public_api → public_science → science`, `executors` and `io` used by
`stages` and `public_api`, and `data_models` and `config` shared by all
layers (ADR-009). `LAYER_IMPORTS` in `tests/unit/test_architecture.py` states
the allowed imports of every layer as one table; an import outside it needs
a named exemption there.

## Repository notes

- `just quick-science-check` (`scripts/validation/quick_science_check.py`)
  is the everyday scientific regression check; see `docs/how-to/index.md`.
- `scripts/benchmark/` and `scripts/validation/` are thin runners over
  `hebog.validation`. The comparison notebook's reproducible workflow is
  `download_notebook_data.py`, `prepare_notebook_comparison.py` (PyBDSF and
  Aegean in Podman via `run_notebook_reference.py`) and
  `refresh_public_notebook_hebog.py` (Hebog via `run_notebook_hebog.py`),
  configured by `config/comparisons/notebook-comparison.json`. The quick
  benchmark is `quick_benchmark.py`. Closed Phase 1–5 campaign and stage
  benchmark tooling was removed; it remains in Git history at `v0.7.0`.
- `LOG.md` is more than 1 MB. Read or search slices of it (for example, grep
  it, or read the end with an offset). Do not read the whole file.
- `config/` holds the checked-in dataset, baseline, contract, and benchmark
  configuration that the campaign scripts consume. `benchmark-results/`,
  `site/`, `dist/`, and `.coverage` are generated and ignored.
- `.python-version` pins 3.14, but 3.12 is the floor. Pyright checks against
  3.12, so do not use syntax newer than 3.12.
- Architecture decisions live in `docs/architecture/adr/` (ADRs 001–008
  cover uv, the Rapthor contract scope, scheduling ownership, hierarchical
  tiles, versioned schemas, Zarr, and the tile-native continuum composition).
