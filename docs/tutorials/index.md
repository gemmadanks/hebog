# Quick start

Hebog is experimental and not yet scientifically qualified. Tested `0.x`
releases can precede general scientific qualification; they are not qualified
PyBDSF replacements. Read [current release status](../reference/release-status.md)
for the supported inputs and known limitations.

## Install a release

Hebog is not on PyPI yet. Install a tagged release from GitHub into a Python
3.12–3.14 environment, replacing the tag with the
[release](https://github.com/gemmadanks/hebog/releases) you want:

```console
pip install git+https://github.com/gemmadanks/hebog@v0.7.0
hebog --version
```

Releases are also uploaded to TestPyPI to exercise the publishing workflow.
Use that index only to check packaging, never for scientific work.

Then follow the [source-finding tutorial](find-sources.md) for a complete
FITS-to-products example with `hebog.find_sources()`, which publishes a
catalogue, RMS image, source mask and diagnostics.

## Work from a source checkout

Install the project and all development dependencies with uv:

```console
git clone https://github.com/gemmadanks/hebog.git
cd hebog
uv sync --all-groups
```

Run the initial checks and confirm the command-line entry point:

```console
just check
just test-integration
just docs-build
uv run hebog --version
```

Run the redistributable Marimo demonstration. It generates a small synthetic
field, calls the public finder and displays every published product:

```console
uv run marimo edit notebooks/source_finder_demo.py
```

See [Use the notebooks](../how-to/notebooks.md) for the other notebooks. The
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
lists the release checklist and the later scientific, performance, Rapthor
integration and larger-image increments.
