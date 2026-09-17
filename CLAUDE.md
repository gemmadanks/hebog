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

- `just test-unit` also collects doctests from `*.py` files and stops at the
  first failure (`--maxfail=1`), so an unrelated broken doctest can hide the
  test you care about. Run the specific file while iterating.
- `pytest` uses `--strict-markers`. A new marker must be added to
  `[tool.pytest.ini_options].markers` in `pyproject.toml`.
- Pyright runs in `strict` mode over both `src/` and `tests/`, so test code
  needs type annotations too.
- Contract tests (`tests/contract/`) mark unimplemented specifications as
  `xfail(strict=True)`. If one starts passing, CI fails. Convert it to a normal
  assertion; do not remove the test.

## Code map

The public entry point is `hebog.find_sources(request, config, executor)`.

- `pipeline.py` holds the public error types and a thin `find_sources` that
  imports `public_api` lazily. This keeps `import hebog` free of I/O and
  scheduler imports. `executors/__init__.py` loads `DaskExecutor` lazily the
  same way (through `__getattr__`). Keep both lazy.
- `public_api.py` is the outer I/O layer. It reads and validates the FITS
  input, enforces the bounded preview size limit, plans partitions, estimates
  background and RMS, calls the science composition, and atomically writes
  versioned products through `io/`.
- `public_science.py` and `science/` hold the installed scientific
  composition. They combine multiscale detection, component topology,
  deblending, measurement, and catalogue construction, using the reviewed
  profile in `science/profile.py` and `resources/`.
- `stages/` contains scheduler-facing wrappers around each scientific stage
  (background, detection, deblending, fitting, measurement, multiscale,
  catalogue). They handle tiling, cores and halos, and batching through an
  `Executor`.
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
- `adapters/` is the Rapthor compatibility boundary: serializable records, a
  PyBDSF-style catalogue view and combined product publication with that
  view. It must not import Rapthor, Prefect, or LSMTool.
- `validation/` provides campaign, evidence, comparison, and dataset tooling
  for `scripts/` and tests. No production module outside `validation/` imports
  it, and wheels exclude it. Keep it that way, so the source finder stays
  independent of campaign validation.

Dependencies point inward:
`adapters → pipeline/public_api → science → stages → algorithms`, with
`data_models` and `config` shared by all layers.

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
- Architecture decisions live in `docs/architecture/adr/` (ADRs 001–007
  cover uv, the Rapthor contract scope, scheduling ownership, hierarchical
  tiles, versioned schemas, and Zarr).
