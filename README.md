# Hebog

[![CI](https://github.com/gemmadanks/hebog/actions/workflows/ci.yaml/badge.svg?branch=main)](.github/workflows/ci.yaml)
[![release-please](https://github.com/gemmadanks/hebog/actions/workflows/release-please.yaml/badge.svg)](release-please-config.json)
[![Docs](https://github.com/gemmadanks/hebog/actions/workflows/docs-pages.yaml/badge.svg)](https://gemmadanks.github.io/hebog/)
[![codecov](https://codecov.io/gh/gemmadanks/hebog/graph/badge.svg)](https://codecov.io/gh/gemmadanks/hebog)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE)

Hebog is a Dask-aware radio-continuum source finder for SKA Science Data
Processor pipelines. It is being developed first as a faster, scientifically
compatible replacement for the PyBDSF work performed by Rapthor's
`filter_skymodel` step, while keeping the scientific API usable by other data
pipelines and science workflows.

The implementation is intentionally narrower than PyBDSF. It will reproduce
the behaviour and materialised products that Rapthor consumes while targeting
at least a 50% reduction in the median wall time of the complete
`filter_skymodel` step relative to released PyBDSF, and a lower runtime than a
pinned performance-improved PyBDSF `master` reference. Scientific
equivalence—not bitwise equality—is the acceptance criterion.

Those comparisons are minimum release gates, not the optimization target.
Hebog aims to minimize complete latency and maximize useful throughput at
every supported image size.

Hebog is designed to scale out of core to 100,000-by-100,000-pixel images.
Large planes are processed as deterministic haloed tiles with hierarchical
boundary reconciliation, allowing an existing Dask cluster to distribute work
across 100 to several hundred nodes without any worker holding a full plane.
Production nodes are expected to have hundreds of GB of RAM; Hebog will use
that capacity through resource-aware tile batching and caches while preserving
bounded tasks and topology-independent results.

See the [source-finder implementation plan](plans/source-finder-implementation.md)
for the profiling evidence, scientific gates, dataset matrix, staged delivery,
performance budget, risks, and definition of done.
See the [execution log](LOG.md) for completed work, validation evidence,
decisions, and immediate next steps.

## Status

Hebog currently provides the project structure, development tools, public data
models, scheduler-independent executor interface, serial and Dask executors,
CLI, test lanes, and implementation plan. The scientific source-finding
algorithms are not implemented yet.

## Goals

- Read the FITS images and metadata used by Rapthor.
- Estimate background and RMS, including an adaptive bright-source mode.
- Detect, deblend, measure, and where necessary fit compact and extended radio
  sources.
- Materialise compatible catalogue, RMS-image, and mask products.
- Provide the same scientific API for deterministic serial, local, and Dask
  execution.
- Keep the scientific core independent of Rapthor, Prefect, LSMTool, and
  concrete schedulers so other workflows can supply their own orchestration
  and product adapters.
- Process images up to 100,000 by 100,000 pixels out of core with
  partition-invariant results and bounded per-worker memory.
- Scale through Rapthor's existing Dask cluster to 100 and at least 200 worker
  nodes without per-pixel or per-window tasks.
- Integrate into Rapthor without its current PyBDSF fork-safety subprocess
  escape.
- Demonstrate scientific equivalence with frozen PyBDSF products and injected
  truth before making performance claims.
- Reduce matched median `filter_skymodel` wall time by at least 50% relative to
  released PyBDSF, outperform pinned PyBDSF `master`, and avoid an unapproved
  memory regression.
- Maintain a size-stratified performance curve so large-image throughput is
  not bought by silently regressing small-input latency, or vice versa.

Complete compatibility with every PyBDSF option, polarization analysis not
used by Rapthor, GPU execution, and undocumented PyBDSF defects are initially
out of scope.

## Public API contract

The scheduler-independent API is designed around small, serializable requests
and materialised results:

```python
from pathlib import Path

from hebog import SourceFinderConfig, SourceFinderRequest
from hebog.executors import SerialExecutor
from hebog.pipeline import find_sources

request = SourceFinderRequest(
    image_path=Path("image.fits"),
    output_directory=Path("output"),
    run_id="example",
)
config = SourceFinderConfig(
    detection_threshold_sigma=5.0,
    island_threshold_sigma=3.0,
)
result = find_sources(request, config, SerialExecutor())
```

The final call currently raises `NotImplementedError`; Phase 0 first freezes
the Rapthor/PyBDSF contract and equivalence harness.

Requests and results never contain open FITS handles, scheduler clients, or
mutable full-image objects. Scientific thresholds are explicit because the
widely used 5-sigma/3-sigma profile is not a universal default. One public
request analyses one image and returns one catalogue, RMS image, mask, and
diagnostics record. The `hebog.adapters.rapthor` boundary composes the
primary-beam-corrected and flat-noise branches and owns Rapthor-specific sky
models, filenames, and compatibility options. Rapthor owns the top-level Dask
graph and resource budget.

## Development setup

Python 3.12 through 3.14 is supported. Python 3.11 users must remain on Hebog
0.2.x or upgrade Python before adopting the next release.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), clone the
repository, and install all dependency groups:

```shell
git clone https://github.com/gemmadanks/hebog.git
cd hebog
uv sync --all-groups
```

Install [just](https://just.systems/) to use the repository's documented
commands:

```shell
just test-unit          # fast deterministic tests
just test-integration   # Dask and FITS integration tests
just test-equivalence   # frozen PyBDSF comparisons
just test-acceptance    # Rapthor-facing behaviour scenarios
just test-qualification # held-out scientific validation
just test-benchmark     # explicitly requested performance tests
just test-scalability   # controlled large-image and multi-node scale tests
just marimo-check       # validate Marimo notebooks
just check              # format, lint, type, and quick tests
just docs-build         # strict MkDocs build
just package-smoke-test # build and import the wheel in isolation
```

Small equivalence and acceptance suites are suitable for pull requests.
Qualification and benchmark lanes are explicit because they may require held-
out data, stable CPU allocation, or external PyBDSF, LSMTool, and Rapthor
environments.

## Interactive demonstrations

[Marimo](https://marimo.io/) is available in the development dependency group.
Create or edit an interactive source-finder demonstration with:

```shell
uv run marimo edit notebooks/source_finder_demo.py
```

Marimo notebooks are normal Python modules, so demonstrations remain
reviewable, testable, and version controlled. Validate them with
`just marimo-check`.

## Architecture

Scientific kernels operate on NumPy arrays and immutable configuration. An
executor decides whether coarse batches run serially, in local threads, or on
Dask workers. Its partition and batching planner selects the lowest-overhead
valid plan for the admitted resources: small work stays as one Zarr-backed
tile without Dask, while larger work moves through local batching and
distributed execution where measurements show a benefit. Zarr is the single
intermediate image-plane backend; FITS is used at input and final compatibility
boundaries.

Image-sized kernels receive bounded tile cores, stage-specific read-only
halos, and global coordinates. Boundary summaries and tree reductions
reconcile statistics, connected labels, sources, and output chunks. A small
image uses the same semantics as one tile; a large image never becomes one
scheduler payload.

```text
FITS input
   -> background and RMS estimation
   -> threshold and multiscale detection
   -> connected components and deblending
   -> source measurement and fitting
   -> catalogue, mask, and RMS products
```

The true-sky and flat-noise analyses are independent operations that join only
when Rapthor applies the final sky-model filter. Intermediate file products are
restartable, and scheduler payloads remain small.

Dependencies point inward from workflow and compatibility adapters to the
public pipeline and scientific core. Hebog favours Pythonic, typed, cohesive
code and narrow demonstrated extension seams over framework-specific coupling
or a speculative plugin system. See the
[quality attributes and coding principles](docs/explanation/quality-attributes.md).

Hebog does not currently need a project-owned C++ or Rust extension. The
[native-code assessment](docs/explanation/native-code-assessment.md) keeps
NumPy/SciPy and profiled Numba as the first choices, with quantitative gates
for reconsidering Rust or C++ after end-to-end profiling.

## Repository layout

- `src/hebog/`: library, CLI, public records, execution policies, algorithms,
  and I/O boundaries.
- `tests/`: unit, integration, scientific-equivalence, acceptance,
  qualification, and benchmark suites.
- `scripts/benchmark/`: reproducible PyBDSF, Hebog, and Rapthor benchmarks.
- `config/`: checked-in algorithm, equivalence, and benchmark configurations.
- `notebooks/`: reproducible interactive demonstrations.
- `docs/`: user, reference, explanation, and architecture documentation.
- `plans/source-finder-implementation.md`: authoritative delivery plan and
  acceptance gates.
- `LOG.md`: chronological execution progress, evidence, decisions, and next
  steps.

## Contributing

Use [Conventional Commits](https://www.conventionalcommits.org/) and follow
[AGENTS.md](AGENTS.md). A scientific or performance change must include the
relevant equivalence evidence; isolated kernel timings are not sufficient for
an end-to-end speedup claim. Code must pass the configured Ruff, Pyright,
coverage, and test gates. Significant architectural decisions belong in an ADR
under `docs/architecture/adr/`.

## Citation and license

If Hebog contributes to research, cite it using [CITATION.cff](CITATION.cff).
Hebog is distributed under the [BSD 3-Clause License](LICENSE).
