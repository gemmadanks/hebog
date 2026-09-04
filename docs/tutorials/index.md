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

The interface is implemented on the development branch, but the Phase 5
release candidate still requires fresh held-out qualification and independent
review. It must not yet be described as a released PyBDSF replacement.

Run the redistributable Marimo demonstration to inspect the current compact
path and a multi-object residual processed by the bounded Phase 5 multiscale
stage, including per-scale, persistent, and retained support:

```console
uv run marimo edit notebooks/source_finder_demo.py
```

The [implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
records the remaining held-out qualification, engineering-evidence, and
independent-review gates. Rapthor integration begins separately in Phase 6.
