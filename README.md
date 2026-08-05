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

Hebog is not rebuilding every PyBDSF feature. It is implementing the narrower
source-finding path used by Rapthor, while keeping that scientific capability
usable by other workflows.

The implementation is technically complete through the experimental compact
catalogue path in Phase 4. In practical terms, Hebog can now:

- read and partition radio images without loading a large image onto one
  machine;
- estimate the local background and image noise;
- identify pixels likely to contain astronomical emission;
- join those pixels into distinct connected "islands";
- separate nearby compact peaks within an island;
- calculate deterministic owned-pixel peak, flux, RMS, centroid, and shape
  moments for compact islands and regions;
- fit bounded elliptical Gaussian components and transform their positions
  and shapes into ICRS sky coordinates;
- deconvolve the restoring beam while keeping fully resolved,
  major-axis-only, unresolved, and unavailable values explicit, and require
  five-sigma evidence for noisy extension and each reported intrinsic axis;
- build bounded, deterministic source/component/island catalogue records and
  an eight-column FITS view consumed directly by Rapthor diagnostics;
- run deterministically through either the serial or Dask executor; and
- publish restartable intermediate products in Zarr.

For the governed three-source compact reference, the same Hebog catalogue
passes the frozen position, flux, fitted/deconvolved shape, classification,
association, uncertainty-availability, and outlier gates against both the
released PyBDSF used by Rapthor and the performance-improved PyBDSF `master`
reference. The controlled representative Phase 3 detection path has a median
runtime of approximately 3.2 seconds; the complete incremental Phase 4 runtime
has not yet passed its controlled release gate.

The Phase 4 release gate remains unmet. Phase 4R repaired the evidence
evaluator, introduced data-only beam/free model selection, correlated-noise
fitting, analytic truncated-edge centroid correction, and a no-compensation
registry of 35 scientific and robustness metrics. The final candidate
completed all 600 images in its separately reviewed replacement
qualification; released PyBDSF also completed all 600, while pinned `master`
retained one invalid negative-flux catalogue failure.

The immutable decision passed 446/450 dual-reference comparisons and 106/107
absolute gates, but it is still a failure. Hebog's catastrophic-outlier rate
was worse at SNR 15 against both references, worse for marginally resolved
sources against released PyBDSF, and its overall released-reference confidence
bound crossed the practical margin. The SNR-10 declination-uncertainty-bias
interval also narrowly crossed its absolute upper bound. These results are
preserved without changing a threshold, metric, source row, or population.
Phase 4R is therefore complete as a terminal non-passing milestone; its
performance matrix was not eligible to run, and no Phase 4 release or speed
claim is made.

Phase 4S has since repaired the future evaluator without changing that result.
Governed classification strata can no longer be widened by same-named legacy
validation strata, power can be checked against the actual manifest group
counts, and joint power is reported separately from marginal endpoint power.
The review also found that all 18 SNR-15 catastrophic rows came from one
marginal source family whose weak deconvolved minor axis was being treated as
a precise ellipse. Hebog now propagates fit-shape covariance, reports only
scientifically significant intrinsic axes, preserves a major-only `DC_Maj`
for Rapthor when appropriate, and obtains a truncation retry's centroid and
covariance from the same likelihood fit. Analytic, integration, serial/Dask,
dual-reference regression, and full correlated-noise calibration checks pass.

These corrections make the compact scientific API technically stable, but the
project owner chose to require another qualification before substantive Phase
5 work. Phase 4S then completed 800/800 images for Hebog and both PyBDSF
references. Hebog passed all 20 paired non-inferiority endpoints against both
references, with better reliability, unresolved-group measurements, and
uncertainty calibration on several outcomes. The overall result still failed
four absolute gates. Two fixed raw error limits were below the noise floor of
the mixed-SNR population, and a point-truth projection artefact produced a
false zero-specificity score even though Hebog called all 6,400 declared point
cases unresolved. The remaining genuine miss was narrow: the SNR-10
integrated-flux mean residual was 0.106 sigma, but its upper 95% limit was
0.154 against a frozen 0.150 limit.

Phase 4S is preserved as failed rather than rescored. Phase 4T then tested the
corrected semantics on 800 fresh images. Hebog passed all 20 paired endpoints
against both PyBDSF references, all uncertainty-calibration gates, and 76 of
77 binding absolute gates in total. It recovered every unresolved blend and its
95th-percentile blend total-flux error was 20.71%, much better than 60.00% for
both references, but just above the frozen 20% absolute limit. Phase 4T is
therefore preserved as a terminal failure rather than rounded, rescored, or
repeated on unchanged code.

The remaining compact-science work is a focused, test-driven investigation of
that roughly 10% systematic blend flux under-recovery across independent
development cases. A new qualification will be justified only by a general
algorithm improvement, not by changing the viewed limit or drawing another
set of seeds. Substantive multiscale development remains paused. External
radio-astronomy review, the complete performance matrix, and production
scalability evidence also remain required before Hebog replaces PyBDSF by
default.

The remaining work includes:

- resolving the Phase 4T unresolved-blend flux weakness on independent
  development and regression populations, then qualifying a changed
  candidate once under a separately frozen protocol;
- passing the complete incremental Phase 4 performance budget;
- recovering extended or multiscale emission;
- integrating the complete path into Rapthor's `filter_skymodel` workflow;
- proving end-to-end catalogue and filtering equivalence and speed; and
- qualifying out-of-core execution on production-scale multi-node clusters.

A useful mental model is that Hebog can now locate, outline, fit, and catalogue
ordinary compact objects, and can serialize the part of that catalogue used by
Rapthor's image diagnostics. It cannot yet make a defensible choice for every
sub-beam blend or extended object, nor run as Rapthor's complete source-finder
backend. By planned capability, this is roughly two-thirds to three-quarters
through the Rapthor-specific reimplementation; multiscale recovery, workflow
integration, and qualification remain scientifically significant.

Hebog is therefore a functioning compact-source detector, but it is not yet a
drop-in PyBDSF replacement or production-ready Rapthor backend. Named human
scientific review approved the compact Phase 3 scope and provisional Phase 4
measurement contract, followed by the observable-group and noisy-source
amendments. The post-failure extension/flux addendum was approved on
2026-08-03. See the
[Phase 4 scientific review record](docs/reference/phase-4-review-record.md) and
[Phase 4 release-readiness record](docs/reference/phase-4-release-readiness.md)
for the held-out findings, ordered recovery work, evidence, and remaining
limitations.

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
    minimum_island_pixels=6,
)
result = find_sources(request, config, SerialExecutor())
```

The top-level `find_sources` call currently raises `NotImplementedError`.
Completed background, noise-estimation, compact-detection, measurement,
fitting, astrometry, and compact-catalogue capabilities are exercised through
internal stage APIs. The stable end-to-end public pipeline and complete product
set remain under development.

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

Hebog is still pre-production and does not guarantee backward compatibility
between `0.x` releases. Development prioritizes the cleanest current API,
schema, and storage design over compatibility shims or deprecation periods.
Breaking changes remain explicit in documentation and release notes.

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
Run or edit the compact source-finding and moment demonstration with:

```shell
uv run marimo edit notebooks/source_finder_demo.py
```

The notebook generates a deterministic radio image, visualizes the estimated
background and RMS, displays the accepted source mask and connected islands,
shows compact deblending summaries, and verifies that one-tile and four-tile
execution produce identical results. It also displays Phase 4 moment, fitted,
sky-coordinate, deconvolution, quality-flag, internal catalogue, and Rapthor
FITS results while identifying the multiscale, qualification, and workflow
integration work that remains.

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
