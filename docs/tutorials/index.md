# Quick start

Install the project and all development dependencies with uv:

```console
git clone https://github.com/gemmadanks/hebog.git
cd hebog
uv sync --all-groups
```

Run the initial checks:

```console
just check
just test-integration
just docs-build
```

Confirm that the command-line package is installed:

```console
uv run hebog --version
```

The scheduler-independent `hebog.find_sources()` API now runs the exact
Phase 5 scientific composition and atomically publishes its catalogue, RMS,
mask, and diagnostic products. Follow the
[radio-astronomer source-finding tutorial](find-sources.md) for a complete
FITS-to-products example and the current scientific-preview limits.

The development finder is experimental and scientifically unqualified.
Small tested `0.x` releases can precede general scientific qualification;
they are not qualified PyBDSF replacements. See
[current release status](../reference/release-status.md) for the distinction.

Run the redistributable Marimo demonstration to inspect the current compact
path and a multi-object residual processed by the bounded Phase 5 multiscale
stage, including per-scale, persistent, and retained support:

```console
uv run marimo edit notebooks/source_finder_demo.py
```

The [implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
lists concrete merge/release checks and separate scientific, performance,
Rapthor integration and larger-image increments.
