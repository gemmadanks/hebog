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

The scientific `find_sources` API intentionally raises `NotImplementedError`
until the baseline and equivalence harness in the
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
is complete.
