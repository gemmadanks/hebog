# Hebog implementation plan

Execution progress, evidence, and deviations are recorded in
[`LOG.md`](../LOG.md) so this plan can remain focused on intended work and
acceptance gates.

This is a Hebog-owned plan. Derive requirements and compatibility evidence
from the current Rapthor integration target, Rapthor's pinned LSMTool code,
the latest released PyBDSF used by Rapthor, and a pinned PyBDSF `master`
reference. Do not use the preliminary `ska-sdp-source-finder` scaffold or plan
as an evidence source or migration target.

## 1. Objective

Create a maintainable and extensible radio-continuum source finder that
produces scientifically equivalent results to the subset of PyBDSF used by
Rapthor. Rapthor is the first production consumer, not an architectural
dependency: other data pipelines and science workflows must be able to use
the scheduler-independent scientific API with their own orchestration and
product adapters. Reduce the median wall time of Rapthor's complete
`filter_skymodel` step by at least 50% relative to the released PyBDSF version
used by Rapthor, and also outperform the current performance-improved PyBDSF
`master` reference.

The 50% reduction and `master` comparison are minimum release gates, not an
optimization stopping point. Subject to scientific, memory, and operational
gates, Hebog should minimize complete end-to-end latency and maximize useful
throughput across the full supported image-size range.

Scalability is a core requirement, not an optional optimization. Hebog must
eventually process images up to 100,000 by 100,000 pixels without materialising
a complete image plane on any worker, and distribute that work through an
existing Dask cluster spanning 100 to several hundred worker nodes. Production
nodes are expected to provide hundreds of GB of RAM, so tile and batch sizing
must use explicit worker memory budgets to exploit that capacity without
coupling scientific results to one hardware topology.

The primary acceptance formula is:

```text
Hebog median filter_skymodel wall time
--------------------------------------  <= 0.50
released PyBDSF median wall time

Hebog median filter_skymodel wall time
--------------------------------------  < 1.00
PyBDSF master median wall time
```

Both gates apply to every gate-designated benchmark case. The three measurements must use the same
Rapthor revision, inputs, filter configuration, allocated resources, output products, and
benchmark host. Use at least five measured repetitions after warm-up and report dispersion; do not
claim that Hebog outperforms `master` when the observed difference is indistinguishable from
run-to-run noise. The upper bound of a 95% bootstrap confidence interval for each median runtime
ratio must be at most `0.50` against released PyBDSF and below `1.00` against `master`; increase the
repetition count when the minimum sample is inconclusive.

Apply the dual-PyBDSF gates at every frozen size that both reference
environments can process. Track Hebog against its previous reviewed baseline
at every size, including larger cases that PyBDSF cannot complete. A change
with a lower 95% confidence bound above `1.05` for the new/previous Hebog
median ratio is a performance regression and requires an explicitly approved,
documented trade-off.

Scientific equivalence is required; bitwise equality is not. The replacement must preserve the
sources that affect filtering, catalogue meaning, units, coordinates, masks, RMS products, and
failure semantics within agreed tolerances.

## 2. Evidence motivating the project

Exploratory profiling performed on 2026-07-16 used a representative 3000 by 3000 Rapthor image and
the LSMTool/PyBDSF adaptive-RMS and three-scale wavelet configuration:

| Measurement | Wall time | Observation |
| --- | ---: | --- |
| PyBDSF true-sky pass, one core | 57.73 s | Serial reference |
| PyBDSF true-sky pass, four cores | 35.29 s | Only about two CPUs used on average |
| Flat-noise RMS pass, four cores | 9.55 s | Almost entirely background estimation |
| Controlled interpolation experiment | 22.25 s | 37% below the normal four-core pass |

In the normal four-core pass, background/RMS estimation took 10.41 seconds and wavelet processing
took 22.53 seconds. Together they accounted for 95.4% of PyBDSF operation time; Gaussian fitting
took only 0.07 seconds. The current RMS implementation also calculated roughly 180,000 fine-grid
windows although only a small neighbourhood around five bright sources was used.

Rapthor profiling previously reduced an aggregate `filter_skymodel` measurement from 89.54 to
69.881 seconds by reducing PyBDSF's requested cores from 30 to 15. The provisional 50% target for
that exact benchmark is therefore 34.94 seconds. Phase 0 must reproduce and replace this with
matched, versioned released and `master` baselines before it becomes a release gate.

These observations indicate that a new array-oriented implementation can meet the target by
avoiding repeated statistics, whole-image copies, recursively repeated source-finding pipelines,
and fork-based worker startup.

## 3. Scope

### In scope

- FITS image and metadata input used by Rapthor.
- Background mean and RMS estimation, including an adaptive bright-source mode.
- Seed and island thresholds compatible with Rapthor's PyBDSF settings.
- Connected islands, deblending, compact-source measurements, and Gaussian fitting where needed.
- Multiscale detection sufficient for the extended sources relevant to sky-model filtering.
- Catalogue, RMS image, and mask products consumed by LSMTool/Rapthor.
- Out-of-core, haloed tile processing for images up to 100,000 by 100,000
  pixels.
- Deterministic boundary reconciliation for background grids, islands,
  multiscale detections, catalogues, masks, and image products.
- Serial, local, and Dask execution through the same scientific API.
- A pipeline-neutral scientific API, domain schema, and explicit adapter
  boundaries suitable for other data pipelines and science workflows.
- Distributed execution across 100 to several hundred Dask worker nodes
  without per-pixel or per-window scheduler tasks.
- Direct integration into Rapthor without the current fork-safety subprocess escape.
- Reproducible PyBDSF equivalence and end-to-end performance harnesses.

### Initially out of scope

- Complete compatibility with every PyBDSF option and output format.
- Polarization-specific analysis not exercised by Rapthor.
- GPU execution.
- Requiring a distributed cluster for images that fit within one bounded tile.
- Reproducing undocumented PyBDSF implementation defects.
- Copying or mechanically translating PyBDSF source code.
- A speculative generic plugin framework or support for unreviewed workflows
  before a concrete use case and contract test establish the required seam.

## 4. Required contracts

### 4.1 Public API

The library API must remain scheduler independent:

```python
result = find_sources(request, config, executor)
```

Requests contain input paths, an output directory, identifiers, and immutable configuration.
Results contain materialised output paths, counts, timings, schema versions, and small metadata.
They never contain open FITS handles, a Dask client, or a mutable full-image object. A request may
identify a logical image through a partition manifest or chunk-addressable store, but storage and
partition details remain explicit boundary metadata rather than scheduler state.

One pipeline-neutral request represents one scientific image analysis and
returns one catalogue, RMS image, source-filtering mask, and diagnostics
record. Scientific thresholds are explicit rather than inherited from a
workflow or survey default. A workflow adapter may compose several analyses;
the Rapthor adapter owns its primary-beam-corrected and flat-noise branches,
filtered sky models, legacy filenames, and compatibility configuration.

The public scientific API and domain records must not import Rapthor, Prefect,
LSMTool, or a concrete scheduler. Workflow-specific configuration, filenames,
filtering rules, and failure translation live in adapters that depend on this
API. Extension protocols remain narrow and capability-oriented; introduce one
only when a second implementation or workflow test demonstrates the variation.

### 4.2 Rapthor graph

Rapthor should own the top-level graph:

```text
find_true_sky_sources -----------+
                                 +--> apply_skymodel_filter
estimate_flat_noise_rms ---------+
```

The first two operations are independent and may run concurrently when their combined memory fits
the configured resource budget. Each operation emits restartable file products. The join applies
the existing filtering rules and creates the final sky model. For a large image, either operation
may construct a bounded haloed-tile subgraph on Rapthor's existing Dask client; this does not move
top-level graph or resource ownership into Hebog.

### 4.3 Output compatibility

Phase 0 must inventory every field and side product currently used by LSMTool and Rapthor. At a
minimum, freeze:

- catalogue column names, units, coordinate frame, and null conventions;
- source/component identifiers and grouping semantics;
- peak and integrated flux, position, shape, and uncertainty fields used downstream;
- RMS image shape, WCS, units, and invalid-pixel convention;
- island/source mask meaning;
- error and empty-catalogue behaviour.

An adapter may write a PyBDSF-compatible catalogue while the internal schema remains cleaner and
versioned.

## 5. Scientific equivalence gates

The initial thresholds below are engineering gates and require review with an SKA imaging/domain
expert during Phase 0. The 2026-07-31
[scientific pre-review](../docs/reference/scientific-pre-review.md) amended the low-SNR rule and
terminology after comparison with several observatory pipelines and published source-finder
challenges. Report metrics separately for isolated compact, blended, extended, edge,
varying-noise, and low-SNR cases, and distinguish source, fitted-component, island, and
sky-model-component populations.

| Metric | Initial gate |
| --- | ---: |
| Rapthor retained/rejected input components | at least 99.5% agreement |
| PyBDSF sources at SNR >= 10 recovered | at least 99% |
| PyBDSF sources at SNR >= 5 recovered | compatibility curve only; no single pass fraction |
| False-discovery rate | no more than 1 percentage point above PyBDSF |
| Median position difference, isolated SNR >= 10 | at most 0.02 beam widths |
| 95th-percentile position difference, isolated SNR >= 10 | at most 0.10 beam widths |
| Median peak-flux difference, isolated SNR >= 10 | at most 2% |
| 95th-percentile peak-flux difference, isolated SNR >= 10 | at most 5% |
| Median integrated-flux difference, isolated SNR >= 10 | at most 5% |
| 95th-percentile integrated-flux difference, isolated SNR >= 10 | at most 10% |
| Source-free RMS-map median difference | at most 2% |
| Source-free RMS-map 95th-percentile difference | at most 5% |

Matching uses sky coordinates and beam-normalized distances, then resolves ambiguous blends by
maximum total matched flux. Low-SNR differences are also reported as completeness and reliability
curves versus injected truth; PyBDSF is not assumed to be ground truth. Use predeclared SNR bins,
report two-sided 95% confidence intervals, and require a reviewer-approved non-inferiority margin
before promotion. A true source at exactly the detection threshold is not expected to have
near-certain recovery after noise fluctuations, local-RMS estimation, blending, and masking.

Serial and Dask executions of this project must match more tightly than the PyBDSF comparison.
Unless a reduction order is explicitly nondeterministic, source membership and labels should be
identical and floating values should agree within documented numerical tolerances.

## 6. Dataset matrix

Build a versioned manifest containing checksums, provenance, redistribution status, beam and WCS
metadata, image statistics, and expected benchmark role.

The suite must cover:

1. Small synthetic unit images with analytically defined point sources and Gaussian noise.
2. Injected compact sources spanning SNR 3 to 100, source density, beam ellipticity, and pixel
   scale.
3. Close pairs and multi-component islands across the deblending boundary.
4. Diffuse Gaussians, filaments, and mixed compact/extended emission at several scales.
5. Edges, NaNs, masks, negative bowls, spatially varying noise, and bright-source artefacts.
6. The representative 3000 by 3000 Rapthor image used in exploratory profiling.
7. At least one larger production-like image, initially 8000 by 8000 or larger.
8. A generated scalability ladder at 10,000, 30,000, and 100,000 pixels per side, with controlled
   source populations and features deliberately crossing tile boundaries.
9. Several `filter_skymodel` calls from a complete Rapthor benchmark run.

The performance manifest samples image dimensions logarithmically, initially
including 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000, and 100,000 pixels
per side. Add cases immediately below and above every measured executor,
partition, storage, or batching crossover. At each size include representative
empty/sparse, normal, and source-dense or extended-emission workloads so a
fast empty path cannot conceal poor scientific-work scaling.

Treat the 10,000-pixel case as development data, the 30,000-pixel case as a reviewed regression
case, and the frozen 100,000-pixel case as qualification data unless the manifest records an
approved equivalent split. The large-image generator, not just its random seed, is versioned.

Use generated truth to measure absolute completeness and flux accuracy. Use frozen outputs from
the released PyBDSF reference to measure current Rapthor compatibility, and frozen outputs from the
`master` reference to expose forward-looking changes. When the references disagree, use analytic
truth and the Rapthor contract to adjudicate the difference; neither reference is scientific
ground truth. Production data that cannot be redistributed stays in an external data store
referenced by environment-neutral dataset identifiers.

Every manifest entry must have exactly one test role:

- `development`: small analytic or synthetic cases used freely during red-green-refactor work;
- `regression`: reviewed cases added after a defect or scientific decision and run in normal CI;
- `qualification`: frozen production-like cases reserved for milestone and release decisions.

Do not tune thresholds or algorithms against qualification results. Freeze the qualification set
and its gates before the corresponding algorithm phase begins. Record generator versions and seeds
for synthetic data; a seed alone is not sufficient provenance.

## 7. Testing strategy

### 7.1 Test-driven development

Use TDD for public contracts, pure scientific kernels, schemas, matching, error behaviour, and
executor semantics. Each planned behaviour follows this loop:

1. State the observable behaviour, units, tolerances, and failure semantics.
2. Add the smallest analytic, property, contract, or regression test and confirm that it fails for
   the intended reason.
3. Implement the simplest deterministic serial behaviour that makes the test pass.
4. Refactor while the fast suite remains green.
5. Add pathological and property-based cases before optimizing the implementation.
6. Prove local and Dask conformance against the serial reference.
7. Run compatibility and performance lanes only after the correctness tests pass.

Exploratory prototypes may precede tests when selecting an algorithm, but prototype code does not
enter the production package until its required behaviour is expressed as tests. Every defect fix
starts with a reproducing test when practical.

### 7.2 Oracle hierarchy

Use the strongest independent oracle available, in this order:

1. Analytic truth for small images, coordinate transforms, moments, and known distributions.
2. Mathematical and metamorphic properties, such as translation, positive scaling, threshold
   monotonicity, mask exclusion, and conservation relationships.
3. The deterministic Hebog serial implementation for executor conformance.
4. Frozen products from the released PyBDSF version for compatibility with the behaviour Rapthor
   currently consumes.
5. Frozen products from the pinned PyBDSF `master` reference for forward-looking comparison.
6. End-to-end Rapthor retained/rejected decisions for operational acceptance.

PyBDSF is a compatibility oracle, not scientific ground truth. Unit-test the comparison machinery
itself with hand-constructed catalogues, known ambiguous assignments, unmatched rows, coordinate
wraparound, unit conversions, masks, and RMS maps. A matcher defect must not be able to make a
scientific regression appear equivalent.

Frozen reference products are immutable test inputs. Generate or update them only through a
separate documented command that records tool revisions, configuration, dataset checksum, and
provenance. Reference changes require review of both metadata and scientific comparison output;
tests must never regenerate expected products implicitly.

### 7.3 Test lanes

| Lane | Purpose | Normal trigger |
| --- | --- | --- |
| Unit and property | Pure kernels, schemas, validation, matching, invariants | Every commit |
| Contract | I/O and executor behaviour shared by all implementations | Every commit |
| Integration | Small FITS and in-process/local Dask boundaries | Pull request |
| Small equivalence | Redistributable frozen released and `master` PyBDSF cases | Pull request |
| Acceptance | Lightweight Rapthor-facing behaviour scenarios | Pull request |
| Qualification | Held-out production-like scientific matrix | Milestone and release |
| Benchmark | Component and complete `filter_skymodel` performance | Controlled scheduled runner |
| Scalability | Out-of-core execution, partition invariance, and 100-to-200-plus-node scaling | Controlled multi-node runner |

Mark tests explicitly with `integration`, `equivalence`, `acceptance`, `qualification`,
`benchmark`, `scalability`, `slow`, and `requires_data` as applicable. Portable CI must not run
wall-time or scale gates, download data, or require private production inputs. Small equivalence
and acceptance cases must remain deterministic and redistributable.

Property-based tests should generate bounded, physically meaningful arrays and metadata with
recorded failure examples. Important properties include:

- adding a constant shifts the background without changing RMS or SNR-based membership;
- positive scaling changes background, RMS, and flux consistently while preserving labels;
- increasing a threshold cannot create a new detection;
- invalid or masked pixels never contribute to statistics or flux;
- translating an isolated source changes pixel and sky coordinates consistently;
- changing tile shape, halo size above the required minimum, task batching, worker count, or task
  completion order preserves source membership and product values within reviewed tolerances;
- sources and islands crossing tile corners and edges are neither lost nor duplicated;
- serial, local, and Dask execution preserve stable membership, ordering, and tolerances.

### 7.4 Behaviour-driven acceptance tests

Use lightweight BDD for behaviour that crosses Hebog, its materialised products, Dask, and
Rapthor. Write readable pytest acceptance tests with Given/When/Then structure and scenario tables.
Initial scenarios include valid empty images, corrupt metadata, low-SNR threshold crossings,
restart from existing products, worker retry, backend fallback, dual-run reporting, and unchanged
Rapthor decisions.

Do not add a Gherkin framework initially. Consider one only if domain experts actively review or
author feature files and the shared vocabulary has stabilized. Numerical kernels remain clearer as
unit, property, and equivalence tests.

### 7.5 Distributed and performance testing

Apply one parameterized executor contract suite to serial, local, and Dask implementations. Test
ordering, serialization, exceptions, cancellation, retry semantics, determinism, and resource
metadata with fakes or an in-process cluster where possible. Reserve real worker termination,
spill, and resource-contention tests for a controlled integration environment.

Use small analytic images to prove that a single tile and many tiles produce
the same result before running large scale tests. The controlled scalability
lane must exercise 1, 10, 50, 100, and at least 200 worker nodes where the
approved facility provides them. It records tile and halo geometry, partition
count, graph size, scheduler throughput, worker occupancy, per-worker and
aggregate memory, transfer, spill, storage throughput, retries, stragglers,
and strong- and weak-scaling efficiency. Phase 0 must freeze reviewed runtime,
memory, scheduler-overhead, and scaling-efficiency gates for the 100,000 by
100,000 qualification case.

Do not require PyBDSF to process the complete 100,000-by-100,000 image. Its
scientific oracle combines versioned generated truth, global conservation and
count invariants, partition-invariant Hebog runs, and representative cut-outs
that can be processed as one tile and compared with both exact PyBDSF
references. This keeps large-scale correctness independent of PyBDSF's own
memory and distribution limits.

Never enforce absolute wall-time assertions on shared or portable CI runners. Use microbenchmarks
to diagnose regressions, component budgets on controlled hosts, and matched end-to-end Rapthor
benchmarks against both exact PyBDSF references as the release gate. A performance result is
considered only after the corresponding scientific suite passes.

Benchmark serial, local, and existing-client Dask execution around every
crossover that fits the available resources. Small inputs must avoid
unnecessary distributed fan-out and repeated startup; they still use the sole
Zarr intermediate backend as one chunk. Large inputs must not stay local after
distribution provides a measured benefit. The caller still supplies the
executor under the public API; the executor's partition and batching planner
selects the lowest-overhead valid graph for its admitted resources.

## 8. Target architecture

```text
src/hebog/
  config.py                 immutable scientific configuration
  pipeline.py               scheduler-independent stage composition
  algorithms/
    background.py           robust coarse and adaptive RMS estimation
    detection.py            matched filters and threshold masks
    labelling.py            components, boundaries, and island properties
    partitioning.py         deterministic tile, halo, and ownership planning
    reconciliation.py       boundary labels and hierarchical reductions
    deblending.py           split overlapping emission
    fitting.py              moments and selective nonlinear fits
    multiscale.py           compact/extended filter bank and merging
  executors/
    base.py                 executor protocol
    serial.py               deterministic scientific reference
    local.py                persistent local threaded execution
    dask.py                 existing-client, coarse-batch execution
  io/
    fits.py                 image, beam, WCS, masks, and memory mapping
    chunks.py               bounded window and chunk-addressable plane I/O
    catalogue.py            Astropy FITS catalogue compatibility I/O
  adapters/
    rapthor.py              PyBDSF/LSMTool product and failure compatibility
  validation/
    datasets.py             governed manifests and partition-invariant truth
    comparison.py           independently tested scientific comparison reports
  data_models/
    catalogues.py           versioned internal catalogue schemas
    source_finding.py       small serializable requests and results
```

Scientific kernels operate on bounded NumPy tile arrays with explicit core,
halo, and global-coordinate metadata; a small image is one tile. Use SciPy for
validated array operations and Numba for batched robust statistics or other
kernels that otherwise require Python pixel/window loops. Compiled kernels
must release the GIL when practical. Dask is execution policy, not the array
API inside every function. Large planes live in window-readable files or a
chunk-addressable store, never as one scheduler payload.

### 8.1 Intermediate storage and materialisation decision gate

[Zarr v3](https://zarr.readthedocs.io/en/stable/) is Hebog's single backend for
intermediate image planes. It provides independent multidimensional chunks,
local and remote stores, codec pipelines, checksum codecs, and direct
[Dask array integration](https://docs.dask.org/en/stable/generated/dask.array.to_zarr.html).
Do not introduce a private NumPy-file store, direct-FITS intermediate path, or
size-based storage switch. Small work uses one Zarr chunk and serial execution;
FITS remains an input and final compatibility format.

[ADR-007](../docs/architecture/adr/007-use-zarr-for-intermediate-image-storage.md)
accepts the measured simplicity trade-off. Exploratory local probes found Zarr
1.75 and 1.42 times slower than the removed NumPy-file prototype at 1024² and
3000², respectively, with modestly smaller encoded footprints. Optimize Zarr
initialization, codecs, concurrency, ingestion, and materialisation rather than
maintaining a second record, error model, retry path, and test suite. Hebog
requires Python 3.12 through 3.14 and `zarr>=3.2,<3.3`; the adapter delegates
strict missing-chunk detection to Zarr's `read_missing_chunks=False` runtime
configuration instead of depending on encoded storage keys.

Zarr's parallel-write model is compatible with Hebog only when each worker
writes different complete chunks, execution and storage chunks are aligned,
and the selected store provides the required atomicity. Canonical tile
ownership must enforce those conditions. Overlapping writes require explicit
reconciliation rather than relying on Zarr to resolve them.

Zarr remains a storage mechanism rather than the scientific transaction or
domain model. Hebog must still own:

- the image, product, beam, WCS, unit, dtype, invalid-pixel, and schema
  contracts;
- the mapping from deterministic output cores to storage chunk coordinates;
- the run or generation identity and the exact expected chunk set;
- strict missing-chunk handling, because Zarr normally interprets an absent
  chunk as its fill value;
- retry and conflict policy, provenance, and completion validation;
- an immutable completion manifest written only after all expected chunks and
  checksums validate; and
- streaming compatibility materialisation to FITS, LSMTool, or another
  workflow-facing format.

The implementation must:

1. Create one run-scoped Zarr group with one array per intermediate plane and
   no process-wide configuration or scheduler ownership.
2. Align regular Zarr chunks with the production partition grid, write each
   complete chunk from exactly one owner, and define how shifted-origin
   invariance tests avoid overlapping storage writes.
3. Evaluate `LocalStore` and the Rapthor deployment's shared or fsspec-backed
   store. Record whether the backend provides atomic object writes and which
   conditional-create or synchronization guarantees are available.
4. Configure dtype, endianness, fill values, missing-chunk failure, compression,
   and a corruption-detection codec such as CRC32C explicitly. Retain SHA-256
   only where immutable evidence or content identity requires it.
5. Prove normal, missing, corrupt, duplicate, conflicting, interrupted, and
   resumed writes with deterministic fault injection. A Zarr hierarchy is not
   consumable merely because its metadata exists; only a validated completion
   manifest publishes a generation. This is complete for `LocalStore`; the
   selected deployment store remains subject to the atomicity gate in item 3.
6. Compare Zarr store and codec configurations with cold and warm storage
   across affected size anchors and both sides of each execution crossover.
   Include FITS ingestion and final materialisation. Record latency, CPU, peak
   memory, copies, bytes, object count, task count, scheduler load,
   concurrency, and recovery cost.
7. Tune Zarr's own asynchronous and thread concurrency within each Dask worker
   so the storage library does not oversubscribe the scheduler's resource
   budget.
8. Keep the one-tile path on Zarr and remove avoidable Dask, initialization,
   copy, codec, and final-materialisation overhead without adding a second
   backend.

If Zarr fails a scientific, recovery, portability, or scalability gate, update
ADR-007 before changing the backend decision. Xarray may be an optional
labelled-array facade when multi-axis workflows demonstrate a need; it is not
the storage transaction layer. Prototype Arrow/Parquet separately for
internal catalogue shards, while retaining FITS or the required LSMTool
representation at the compatibility boundary.

### 8.2 Domain language and architecture records

Create a provisional domain glossary in `docs/reference/domain-glossary.md` during Phase 0. It must
define the terms that cross the PyBDSF, LSMTool, Rapthor, and Hebog boundaries, including image,
background, RMS, residual, normalized image, detection threshold, island threshold, pixel, island,
Gaussian component, source, catalogue row, sky-model component, mask, beam, and materialised
product. It must also distinguish compact, blended, extended, and multiscale emission and explain
the true-sky and flat-noise branches. Mark definitions as provisional until the Phase 0 contract
inventory and domain review are complete.

Agree naming conventions alongside the glossary. Array axes use `(y, x)`; coordinate frames and
physical units are explicit in public field names where ambiguity is possible; and `source`,
`component`, `island`, and `catalogue row` are not interchangeable. The glossary must map legacy
PyBDSF/LSMTool names to Hebog's internal vocabulary rather than allowing compatibility terminology
to leak into scientific kernels.

Create `docs/explanation/domain-model.md` with two small, code-native Mermaid diagrams:

1. A system-context diagram showing Rapthor orchestration, Hebog's scientific boundary, executor
   policy, FITS/catalogue products, PyBDSF compatibility, and LSMTool/sky-model filtering.
2. A processing and data-flow diagram showing the true-sky and flat-noise branches, their join,
   and the materialised RMS, mask, catalogue, and comparison products.

Keep diagrams at stable architectural boundaries and update them with the code. Include the
large-image partition, halo, reconciliation, and materialisation flow. Defer a detailed executor
diagram until the asynchronous executor contract has stabilized in Phase 6, and avoid speculative
class diagrams.

Record decisions when their consequences are durable:

- ADR 003: limit Hebog to the source-finding behaviour required by Rapthor instead of reproducing
  all of PyBDSF, while keeping the scientific core independent of Rapthor so other workflows can
  supply their own orchestration and adapters.
- ADR 004: keep top-level scheduling and Dask graph ownership in Rapthor while Hebog exposes
  scheduler-independent scientific work and coarse executor tasks.
- ADR 005: require hierarchical, haloed tile processing and deterministic boundary reconciliation
  so no worker needs a complete image plane.
- ADR 006, after the Phase 0 contract inventory: decide whether to use versioned internal schemas
  with an isolated PyBDSF/LSMTool compatibility adapter.

Do not write algorithm-selection ADRs merely to fill the record. Decisions about RMS estimation,
deblending, fitting, or multiscale processing become ADRs only after tests, scientific evidence,
and benchmarks expose a consequential choice.

### 8.3 Quality attributes and dependency rules

Maintainability and extensibility are release qualities alongside scientific
correctness, performance, and scalability. Apply these requirements to every
vertical slice:

| Quality | Requirement | Verification |
| --- | --- | --- |
| Maintainability | Cohesive modules, descriptive domain names, small typed APIs, explicit side effects, and no hidden global state | Ruff, Pyright, focused tests, coverage gate, and `CODE_REVIEW.md` review |
| Extensibility | Add algorithms, executors, stores, and workflow adapters through narrow demonstrated seams without editing unrelated scientific stages | Contract tests for every implementation and architecture dependency tests |
| Interoperability | The scientific core has no Rapthor, Prefect, LSMTool, or concrete-scheduler dependency | Import-boundary tests and a documented non-Rapthor workflow smoke test |
| Testability | Deterministic serial behaviour, injectable boundaries, and pure kernels where practical | TDD, analytic/property tests, fakes at I/O and execution ports, and executor conformance |
| Performance transparency | Optimized complexity stays isolated behind a clear typed API and is justified by profiles | Readable serial oracle, scientific regression tests, benchmark evidence, and design notes or ADRs when consequential |

Dependency direction is inward:

```text
workflow orchestration -> compatibility/workflow adapters -> public pipeline
public pipeline -> narrow ports <- concrete I/O and executor implementations
public pipeline -> domain records and scientific algorithms
scientific algorithms -> NumPy/SciPy and domain value types
```

Scientific algorithms and domain records must not import adapters,
orchestration frameworks, concrete schedulers, or process-wide configuration.
Keep I/O and scheduling side effects at boundaries and pass dependencies
explicitly. Prefer composition, functions, immutable dataclasses, context
managers, iterators, and structural protocols over inheritance trees and
service-locator patterns. Avoid boolean mode proliferation, generic manager
objects, premature registries, and abstractions introduced without a concrete
variation point.

The configured Ruff rules cover formatting, imports, Pylint diagnostics,
complexity, Bugbear, comprehensions, naming, performance idioms, Ruff-specific
checks, simplification, and unused arguments. Pyright must report no issues.
Branch-aware coverage may not fall below 80%; this floor prevents erosion but
does not replace behaviour-focused normal, edge, failure, property, and
contract tests. Ratchet the floor upward when reviewed coverage makes that
stable.

### 8.3 Native acceleration policy

Do not add C++ or Rust to the initial implementation. Start with vectorized
NumPy/SciPy and use Numba for measured custom loops. The
[native-code assessment](../docs/explanation/native-code-assessment.md)
defines the evidence required to reconsider this decision.

A native prototype is eligible only after vectorization, copy removal,
batching, and a reviewed Numba attempt, when a self-contained kernel consumes
at least 10% of complete time in two representative size regimes, blocks a
frozen resource/scaling gate, or is already available in a mature reviewed
native library. It must deliver at least a twofold kernel speedup and a
statistically supported 5% end-to-end improvement unless it instead unlocks a
failed memory or scaling gate.

Prefer Rust with PyO3/maturin for new self-contained kernels because memory and
thread safety support Hebog's maintainability goals. Prefer C++ with pybind11
when wrapping a mature C/C++ library or when measured ecosystem or team
expertise makes it lower risk. Before either language enters production,
accept an ADR covering language choice, ownership, FFI contracts, GIL release,
thread budgets, fallback behaviour, licensing, and binary distribution.

Native boundaries operate on coarse bounded arrays or summaries with explicit
dtype, shape, stride, alignment, mutability, and ownership. They must avoid
avoidable copies, release Python during native-only work, preserve the readable
serial oracle, pass scientific and sanitizer-equivalent tests, and ship tested
wheels for every supported release platform and Python ABI. Never move FITS,
WCS, schemas, workflow orchestration, or Dask graph construction into a native
extension.

## 9. Release strategy

Release coherent, tested vertical slices frequently rather than waiting for every delivery phase
to finish. Phase exit gates determine readiness to begin dependent work; they are not release
gates. An incomplete later phase does not block a release when the implemented capability is
useful, installable, documented, and clearly identified as experimental.

All pre-production releases remain in the `0.x` series. Release Please derives versions and notes
from Conventional Commits; its `bump-minor-pre-major` policy means features normally advance the
minor version before 1.0 while fixes can produce patch releases. Do not manually force a version to
match a phase number.

Execute the plan as a sequence of local, atomic Conventional Commits. Each commit must represent
one coherent, validated, reviewable change. Its short, imperative subject should describe the
user-visible outcome for Release Please; its body should give developers the motivation, important
design or compatibility consequences, and validation performed. Keep the tests and documentation
that establish a change's behaviour with its implementation. Use `LOG.md` only for material
scientific or performance evidence, gate outcomes, deviations, and decisions that span commits.
Never push commits or tags: a human reviews each local commit and pushes it manually.

The following bands are indicative capability milestones, not promises or rigid mappings:

| Version band | Expected capability |
| --- | --- |
| `0.1.x` | Package, interfaces, development scaffold, plan, and test strategy |
| `0.2.x` | Phase 0 contracts, comparison harness, manifests, and reproducible baselines |
| `0.3.x` | FITS, beam, WCS, schemas, validation, and compatible empty products |
| `0.4.x` | Deterministic serial background and RMS estimation |
| `0.5.x` | Thresholding, islands, deblending, and compact-source detection |
| `0.6.x` | Measurement, fitting, and catalogue compatibility |
| `0.7.x` | Multiscale and extended-emission processing |
| `0.8.x` | Local and Dask execution, out-of-core tiling, reconciliation, and executor conformance |
| `0.9.x` | Experimental Rapthor backend, dual-run comparison, and multi-node qualification |
| `1.0.0` | Qualified production replacement after operational soak |

A phase may produce several minor or patch releases, and one release may contain compatible
vertical slices from more than one phase. Prefer small releases that expose one understandable
capability over large releases that combine unrelated scientific, execution, and schema changes.

Every release requires:

1. Portable CI, packaging, documentation, lockfile validation, and wheel smoke tests to pass.
2. Ruff, Pyright, the branch-aware coverage floor, architecture boundaries,
   and the relevant unit/property, contract, integration, and small scientific
   suites to pass.
3. Scientific regression evidence for changes to algorithms, measurements, or output semantics.
4. Matched controlled benchmarks against both the released and pinned `master` PyBDSF references
   for any performance claim; an optimization may be released without a speed claim when its
   scientific behaviour is valid.
5. For a performance-affecting change, comparison with the previous reviewed Hebog baseline at
   affected and adjacent size tiers and crossovers; milestone qualification refreshes the complete
   curve, and regressions follow the 5% confidence rule in Section 1.
6. Public documentation of implemented capabilities, experimental limitations, configuration,
   output schemas, and known compatibility gaps.
7. Versioned schemas and a migration note for a breaking public API or product change. Breaking
   changes are permitted before 1.0 but must never be silent.
8. A `LOG.md` entry containing material execution evidence and immediate next steps. Release Please
   owns `CHANGELOG.md` and the user-visible release notes.
9. No regression against gates completed by earlier releases.
10. When a native extension is present, tested wheels for every supported
    platform and Python ABI, a verified source distribution, native safety
    checks, provenance/licensing evidence, and the reviewed fallback policy.

Do not present an experimental release as scientifically equivalent, faster, Rapthor-ready, or
production-ready until the relevant reviewed gate has passed. A release tag records available
software; it does not by itself confer readiness for the next phase or for operational adoption.

Release `1.0.0` only after the definition of done in Section 15 is satisfied, the public API and
output schemas are declared stable, the Rapthor backend has completed operational soak, and the
required scientific reviewers approve default cutover. Preserve the PyBDSF fallback until its
removal is separately justified.

## 10. Delivery phases

### Phase 0: freeze baselines and contracts

**Technical foundation status:** complete on 2026-07-18. **Closure status:** in
progress. The captured baselines, comparison harness, contracts, and governed
manifests are sufficient to begin Phase 1 infrastructure work, but the closure
sequence below must be completed before Phase 0 is recorded as fully closed.
The external facility review remains a separate governance follow-up and does
not turn measured engineering gates into facility-demonstrated claims.

#### Phase 0 closure order

Complete the remaining work in this order:

1. **Completed 2026-07-31:** reconcile the exported request, result, and
   configuration scaffold with ADR 006 and the frozen Rapthor contract. One
   public request now represents one image analysis with explicit scientific
   thresholds; the versioned Rapthor adapter records own the two-branch inputs,
   products, and compatibility profile. Documentation and strict contract
   tests preserve that boundary.
2. **Controlled-runner closure completed 2026-07-31; clean-host portability
   remains explicitly limited.** The reference runner now verifies clean exact
   Rapthor and LSMTool checkouts, imported PyBDSF/LSMTool identities, the
   master-wheel checksum, container digest, stable scientific inputs, and
   runner/compiler script hashes. Sanitized installed-package inventories are
   retained in `config/baselines/phase-0-reference-environments.json`. The
   immutable image and restricted representative inputs have no approved
   durable remote locator, so documentation no longer claims independent-host
   reproduction.
3. **First research pass completed 2026-07-31; named human decision pending.**
   Obtain scientific/domain sign-off. The reviewer packet is:

   - the [domain glossary](../docs/reference/domain-glossary.md), including its
     legacy mappings and naming conventions;
   - the [scientific pre-review findings](../docs/reference/scientific-pre-review.md),
     including cross-pipeline consensus and Rapthor disagreements;
   - the [domain model](../docs/explanation/domain-model.md) and the
     [Rapthor source-finding contract](../docs/reference/rapthor-source-finding-contract.md),
     including catalogue, RMS, mask, empty-result, and failure semantics;
   - the [scientific equivalence gates](#5-scientific-equivalence-gates) and
     [dataset matrix](#6-dataset-matrix);
   - the frozen [development](../config/datasets/phase-0-development.json),
     [regression](../config/datasets/phase-0-regression.json), and
     [qualification](../config/datasets/phase-0-qualification.json) manifests;
   - the [Phase 0 baseline results](../docs/reference/phase-0-baseline-results.md)
     and [scientific comparison method](../docs/reference/scientific-comparison.md)
     as supporting context; and
   - the [Phase 0 review record](../docs/reference/phase-0-review-record.md),
     where the reviewer records their name, role or authority, date, decision,
     and any required amendments.
4. Apply any approved amendments to the contracts, gates, or manifests; rerun
   the relevant contract, equivalence, documentation, and normal handoff
   checks; then mark the domain-review checklist item complete and record the
   closure evidence in `LOG.md`.
5. Complete the facility review and controlled 1/10/50/100/200-node evidence
   before calling the extreme-image gates demonstrated. This is not a Phase 1
   start gate and may remain open after technical and scientific Phase 0
   closure.

Phase 1 may begin in parallel with steps 1 to 3 for tests and implementation
that cannot prejudge scientific terminology or choices, such as FITS
validation, bounded window I/O, partition metadata, and atomic product writes.
Complete scientific sign-off before stabilizing public scientific names,
encoding default detection or island thresholds, finalizing catalogue/RMS/mask
semantics, or converting the corresponding strict expected failures into
passing compatibility claims. In all cases, complete it before Phase 2
algorithm work.

- [x] Capture the current Rapthor, released PyBDSF, PyBDSF `master`, LSMTool, dependency, and
      container revisions in the
      [captured starting inventory](../docs/reference/starting-revisions.md), including installed
      packages, the master wheel checksum, and the immutable reference-image digest.
- [x] Reproduce the representative PyBDSF operation timings and current `filter_skymodel` median
      separately for released PyBDSF `1.14.1` and `master` at
      `c70103be3ae9ae9908286f144e6ce956acc0ce5c`.
- [x] Define versioned machine-readable benchmark and scientific-comparison evidence schemas that
      require exact revisions, checksums, resource topology, per-stage metrics, and explicit
      reasons for unavailable instrumentation.
- [x] Capture per-stage wall time, CPU time, peak RSS, explicit unavailable array-copy
      instrumentation, and applicable-zero Dask task/transfer/spill metrics in separate released-
      PyBDSF and pinned-`master` evidence documents. Require the same schema for each future Hebog
      run once an implementation exists.
- [x] Freeze the logarithmic 256-to-100,000-pixel performance matrix, workload-density classes,
      previous-Hebog comparison schema, and cases bracketing every execution crossover.
- [x] Measure one-tile setup, I/O, partition-planning, and executor-dispatch overhead so small-image
      latency has an explicit budget.
- [x] Freeze the 100,000-by-100,000 scalability contract: input and output planes, target storage,
      tile/halo constraints, 1/10/50/100/200-plus-node matrix, per-worker memory ceiling, runtime,
      scheduler-overhead, and strong/weak-scaling efficiency gates.
- [x] Record the representative production node RAM, workers and threads per node, reserved
      headroom, concurrent pipeline demand, and permitted cache/spill policy; define a resource-
      aware tile and batch-sizing policy rather than a fixed universal tile size.
- [x] Inventory exactly which PyBDSF catalogue fields and image products Rapthor consumes in the
      [provisional contract](../docs/reference/rapthor-source-finding-contract.md).
- [x] Inventory the domain language used by PyBDSF, LSMTool, and Rapthor; draft the provisional
      [glossary](../docs/reference/domain-glossary.md) and agree naming conventions for Hebog's
      public and internal concepts.
- [x] Create the system-context and processing/data-flow diagrams and document the domain
      boundaries in `docs/explanation/domain-model.md`.
- [x] Record ADR 003 for Hebog's deliberately narrow scope and ADR 004 for external scheduler
      ownership before those boundaries are implemented.
- [x] Record ADR 005 requiring hierarchical haloed tiles, bounded worker memory, and deterministic
      boundary reconciliation for large images.
- [x] Document the maintainability, extensibility, interoperability, Pythonic
      style, clean-code, dependency-direction, and coverage requirements.
- [x] Assess C++ and Rust acceleration and record an evidence-driven Python,
      NumPy/SciPy, Numba, then native escalation policy.
- [x] Add architecture tests that reject forbidden inward dependencies from
      algorithms and domain records.
- [x] Add tests that reject import-time orchestration or I/O side effects.
- [x] Decide and record ADR 006 after the compatibility boundary and consumed products are known.
- [x] Add a versioned dataset-manifest schema and a deterministic,
      window-addressable synthetic generator whose output is invariant to
      partition layout.
- [x] Add immutable released-PyBDSF and PyBDSF-`master` reference products with
      artifact checksums, exact configuration, and complete provenance.
- [x] Require exactly one development, regression, or qualification role for
      every manifest entry.
- [x] Freeze the regression and initial held-out qualification manifests before
      algorithm work, with qualification cases excluded from routine tuning.
- [x] Write analytic unit tests for coordinate/flux matching, ambiguous assignments, RMS/mask
      comparison, and the report calculations before implementing the comparison harness.
- [x] Implement coordinate/flux catalogue matching and RMS/mask comparison reports.
- [x] Configure and document the unit/property, contract, integration, small-equivalence,
      acceptance, qualification, and benchmark lanes.
- [x] Write at least one strict expected-failure contract or acceptance test for every frozen
      public behaviour; an unexpected pass fails until the behaviour and specification are reviewed.
- [ ] Obtain domain review of the glossary, naming conventions, and scientific thresholds in
      Section 5.

Technical exit gate: documented commands reproduce both baselines and the reference-divergence
report in clean, isolated environments; comparison tests prove the harness against analytic cases;
and the held-out qualification set is frozen. ADRs 003, 004, and 005 are accepted, and the
provisional large-image resource and scaling gates are frozen. This technical foundation is
complete. Domain review remains required before thresholds are called domain-approved, and facility
review plus controlled multi-node evidence remains required before the extreme-image gates are
called demonstrated.

### Phase 1: FITS, beam, WCS, and internal models

Start rule: Phase 1 infrastructure and red-green-refactor work may proceed
while Phase 0 scientific review is in progress, but its versioned schemas must
not be declared stable until the sign-off and any required amendments in the
Phase 0 closure order are recorded.

- [ ] Write failing round-trip and boundary tests for valid, empty, masked, corrupt, and
      unsupported FITS inputs and products.
- [x] Write failing tests for partition manifests, bounded window reads, halo clipping, global and
      tile coordinates, chunk checksums, interrupted writes, and restartable materialisation.
- [x] Define versioned internal catalogue and materialised result schemas from
      failing physical-boundary, relationship, empty, serialization, and restart-metadata tests;
      keep their scientific status provisional until Phase 0 human sign-off.
- [x] Define a narrow image-source seam and explicit Zarr product boundary from
      concrete FITS and workflow tests; do not introduce a generic sink protocol,
      registry, or plugin system before a demonstrated second implementation.
- [x] Write and accept the intermediate-storage ADR after a measured Zarr v3 prototype; use Zarr
      as the sole intermediate image-plane backend and remove the private NumPy-file path.
- [x] Prove aligned independent Zarr writes, strict missing-chunk behaviour, corruption detection,
      duplicate/conflicting retries, interrupted-run recovery, and exact validated completion
      manifests on `LocalStore`; retain deployment-store atomicity as a separate open gate.
- [ ] Benchmark Zarr local and deployment-representative stores, codecs, FITS ingestion, and final
      materialisation across affected size and execution-crossover anchors; tune Zarr from recorded
      evidence without adding a second intermediate backend.
- [ ] Define a deterministic partition manifest and ownership rule so every output pixel and source
      has exactly one owning tile.
- [ ] Read and validate required image planes through bounded windows or a chunk-addressable store;
      use memory mapping where safe without requiring a worker to map or materialise every plane.
- [ ] Write large intermediate planes in independently retryable chunks before compatibility
      materialisation.
- [ ] Keep one-tile work to one serial Zarr chunk and eliminate avoidable scheduler, initialization,
      copy, codec, and materialisation overhead without changing product semantics.
- [ ] Make FITS, mask, RMS, and catalogue round-trip tests pass without weakening assertions.
- [ ] Measure and cap avoidable full-image copies.

Exit gate: reference inputs round-trip with correct coordinates, units, shapes, and invalid pixels;
the intermediate-storage ADR is accepted from reproducible evidence; missing or incomplete chunks
fail closed; the package can emit empty but structurally compatible products; and the same I/O
contract handles one-tile and many-tile images with memory bounded by configured tile and halo
sizes.

### Phase 2: robust background and RMS estimation

- [ ] Write failing analytic and property tests for constant and affine backgrounds, positive
      scaling, masks, NaNs, edges, negative values, sparse adaptive cells, and interpolation
      fallback.
- [ ] Add tile-boundary and partition-invariance tests for RMS windows, interpolation, and adaptive
      bright-source regions.
- [ ] Implement batched sigma-clipped statistics on a coarse window grid to satisfy those tests.
- [ ] Compute global coarse-grid and interpolation metadata through hierarchical reductions and
      bounded tile summaries rather than gathering full planes.
- [ ] Reuse buffers and calculate adaptive fine-grid cells only around bright candidates.
- [ ] Interpolate cached coarse samples; fallback interpolation must not recompute statistics.
- [ ] Treat masks, NaNs, edges, negative values, and insufficient samples explicitly.
- [ ] Add Numba only where profiling shows vectorised SciPy/NumPy is insufficient.
- [ ] If a candidate still meets the native-code decision gate, benchmark one
      minimal Rust and/or C++ prototype against the same Python/Numba contract
      before selecting a language or accepting an ADR.
- [ ] Benchmark array dtype, window batching, and interpolation slab size.

Provisional component budget on the 3000 by 3000 reference image: no more than 4 seconds for the
true-sky background stage and no more than 3 seconds for the flat-noise RMS product on four
allocated CPU cores.

Exit gate: the RMS scientific gates pass across the dataset matrix and the component budget is met
without increasing peak memory above the matched PyBDSF run.

### Phase 3: thresholding, islands, and deblending

- [ ] Write failing analytic and generated-truth tests for threshold monotonicity, connectivity,
      stable labels, close blends, edges, and empty detections.
- [ ] Put sources and islands across every tile-edge and tile-corner topology; prove invariance to
      tile shape, worker count, task order, retry, and partition origin.
- [ ] Apply seed and island thresholds to normalized residuals.
- [ ] Label connected pixels with explicit connectivity and edge conventions.
- [ ] Calculate island bounding boxes and properties without copying the whole image per island.
- [ ] Implement deterministic deblending using a documented multilevel or watershed algorithm.
- [ ] Establish stable source and island ordering independent of executor completion order.
- [ ] Reconcile connected-component equivalences and deblending state across tile halos using
      bounded boundary summaries and deterministic hierarchical merging.
- [ ] Expand the initial tests into injected-source completeness, reliability, blend, and edge
      regression cases.

Use the same labelling and reconciliation semantics for a one-tile image and a distributed image.
Whole-image labelling may optimize the one-tile case, but it must not become a separate scientific
implementation or a prerequisite for correctness.

Exit gate: compact-source detection and island membership pass the relevant scientific gates and
show no quadratic scaling with source count.

### Phase 4: measurement, fitting, and catalogue compatibility

- [ ] Write failing analytic tests for moments, beam deconvolution, units, WCS conversion,
      uncertainties, selective fitting, and downstream filter decisions.
- [ ] Calculate vectorised moments for every island and use them to initialize fits.
- [ ] Accept moment-based measurements directly where nonlinear fitting cannot materially change
      filtering or catalogue acceptance.
- [ ] Batch remaining nonlinear Gaussian fits by estimated pixel/component cost.
- [ ] Implement beam deconvolution, sky-coordinate conversion, uncertainties, and units.
- [ ] Write the compatibility catalogue and side products required by LSMTool/Rapthor.
- [ ] Write catalogue shards independently and merge them hierarchically with stable global source
      identifiers; never gather image-sized intermediates on the scheduler or one worker.
- [ ] Compare retained/rejected sky-model components end to end.

Exit gate: compact and blended source catalogues pass the position, flux, shape, and downstream
filter-decision gates.

### Phase 5: multiscale and extended emission

- [ ] Add failing analytic and generated-truth tests for diffuse, filamentary, mixed,
      cross-scale, duplicate, and artefact-dominated cases.
- [ ] Implement an undecimated wavelet or equivalent beam-aware filter bank with reused
      convolutions and background products.
- [ ] Detect significant emission at each configured scale without recursively rerunning the full
      pipeline.
- [ ] Derive scale-specific halos and trim ownership regions so tile-boundary convolutions match
      the one-tile reference.
- [ ] Merge cross-scale islands deterministically and prevent duplicate compact components.
- [ ] Promote reviewed failures and boundary cases to regression fixtures.
- [ ] Compare completeness and integrated flux by angular scale.

Exit gate: extended-source cases meet reviewed scientific tolerances and the multiscale path stays
within the complete runtime budget.

### Phase 6: local, out-of-core, and distributed Dask execution

- [ ] Define a parameterized executor contract suite for ordering, serialization, exceptions,
      retry, cancellation, determinism, and resource metadata.
- [ ] Extend the executor protocol for asynchronous coarse batches and resource metadata until the
      serial implementation satisfies the contract.
- [ ] Add a persistent local threaded executor for GIL-releasing kernels.
- [ ] Add a Dask executor that receives an existing client and never creates nested pools.
- [ ] Benchmark serial, local, and existing-client Dask plans around every size/resource crossover
      and encode the lowest-overhead valid partition and batching choice within each executor.
- [ ] Build bounded map, boundary-summary, hierarchical-reduction, and materialisation subgraphs
      from the partition manifest without creating a task per pixel, RMS window, or small island.
- [ ] Batch RMS cells, interpolation slabs, multiscale filters, and island fits by measured cost.
- [ ] Use admitted worker memory metadata to size tile batches and caches, allowing memory-rich
      production nodes to do more useful work without changing tile ownership or scientific
      results.
- [ ] Keep common image data in worker-local storage or publish it once; do not embed full arrays in
      every task.
- [ ] Add resource annotations for CPU and memory; use deterministic failure injection for normal
      tests and controlled integration tests for spill and real worker loss.
- [ ] Record graph size, scheduler overhead, transfer volume, task-duration distribution, and
      peak aggregate memory.
- [ ] Prove serial/local/Dask scientific equivalence.
- [ ] Demonstrate topology-independent results across tile geometries and 1, 10, 50, 100, and at
      least 200 worker nodes on the approved scalability facility.
- [ ] Process the 100,000-by-100,000 qualification image without any worker materialising a full
      plane or exceeding the frozen per-worker memory and spill budgets.

Use 0.2 to 2 seconds only as an initial lower-scale diagnostic range for amortising scheduler
overhead. On memory-rich production nodes, size bounded batches from measured CPU, I/O, memory,
and straggler behaviour while keeping enough runnable batches to occupy every admitted worker; do
not impose one universal task duration or item count.

Exit gate: Dask improves throughput or critical-path time on supported workloads, has no nested
fork behaviour, and meets the frozen 100,000-by-100,000 correctness, runtime, worker occupancy,
memory, scheduler-overhead, recovery, and scaling-efficiency gates at 100 and at least 200 worker
nodes representative of the production hundreds-of-GB RAM class.

### Phase 7: Rapthor integration and dual-baseline performance gate

- [ ] Write Given/When/Then acceptance scenarios for empty and corrupt inputs, restart, retry,
      backend selection, dual-run reporting, and retained/rejected decisions.
- [ ] Add a Rapthor backend flag selecting PyBDSF or `hebog`.
- [ ] Split true-sky finding, flat-noise RMS estimation, and final filtering into restartable tasks.
- [ ] Run independent tasks concurrently only when Dask resource annotations admit both.
- [ ] Remove the PyBDSF-specific subprocess escape from the new backend.
- [ ] Preserve PyBDSF as a feature-flagged fallback and support dual-run comparison mode.
- [ ] Measure complete `filter_skymodel` wall time for Hebog, the released PyBDSF reference, and
      the pinned PyBDSF `master` reference across the full benchmark matrix.
- [ ] Compare every size tier with the previous reviewed Hebog baseline and investigate any
      statistically supported regression, even when the dual-PyBDSF gates still pass.
- [ ] Profile at least 1, 2, 4, 8, and the current 15 allocated cores without oversubscription.
- [ ] Validate resume, retry, empty catalogue, corrupt input, and worker-loss behaviour.

Exit gate: the new backend passes all reviewed scientific gates. For every gate-designated case,
its matched median `filter_skymodel` wall time is at most 50% of released PyBDSF and is lower than
the pinned PyBDSF `master` median, with both comparisons satisfying the confidence rule in Section
1. Peak worker and aggregate memory must not regress by more than 10% against either comparator
unless an explicitly approved throughput trade-off justifies it.

### Phase 8: hardening and release

- [ ] Enforce the Phase 0 test lanes in CI, including unit/property tests, small equivalence
      fixtures, acceptance scenarios, Dask integration, packaging, and docs.
- [ ] Run qualification and performance suites on controlled runners outside merge-request
      critical paths.
- [ ] Publish configuration and output schema documentation and a migration guide.
- [ ] Publish and execute a minimal non-Rapthor science-workflow example using
      the public API and serial executor whose integration code does not import
      or construct Dask, Prefect, LSMTool, or Rapthor objects.
- [ ] Add structured stage timings and scientific summary metrics to normal runs.
- [ ] Perform licensing, dependency, security, and reproducibility review.
- [ ] If native code has been accepted, build, install, test, inspect, and
      validate publishable wheels across the complete supported OS,
      architecture, Python, and NumPy matrix.
- [ ] Continue incremental experimental `0.x` releases and prepare `1.0.0` only after the complete
      definition of done and operational soak are satisfied.

## 11. Performance budget

Phase 0 will replace provisional values with matched, versioned released and `master` baselines.
Performance is evaluated as a curve, not one headline image. The initial size
regimes are:

| Regime | Frozen representative sizes | Primary concern |
| --- | --- | --- |
| Small | 256, 512, and 1,024 pixels per side | Startup, I/O, validation, and dispatch overhead |
| Current representative | 3,000 pixels per side | Dual-PyBDSF latency and component budgets |
| Large single-node candidates | 8,000 and 10,000 pixels per side | Memory-rich local batching versus Dask crossover |
| Distributed | 30,000 pixels per side | Storage throughput, occupancy, reconciliation, and graph overhead |
| Extreme qualification | 100,000 pixels per side | Out-of-core correctness and 100-to-200-plus-node scaling |

These are benchmark anchors, not hard-coded execution thresholds. Phase 0 and
subsequent controlled measurements determine crossovers from image planes,
halos, source density, storage, admitted CPUs/RAM, and executor overhead. Add
near-boundary cases whenever the fastest valid plan changes.

The design budget for the representative 3,000-by-3,000 case is:

| Component | Provisional budget |
| --- | ---: |
| FITS input, validation, beam, and WCS | 1.5 s |
| True-sky background and RMS | 4.0 s |
| Detection, labelling, and deblending | 2.5 s |
| Compact measurement and fitting | 2.0 s |
| Multiscale processing and merge | 6.0 s |
| Catalogue, RMS, mask, and filter outputs | 4.0 s |
| Flat-noise analysis, run concurrently | 4.0 s |
| Dask scheduling/transfer on critical path | 2.0 s |

The true-sky critical path should therefore remain near 20 seconds, with the flat-noise branch
hidden by concurrency. The complete Rapthor gate, not this component table, decides acceptance.
Component improvements are not added arithmetically unless their end-to-end effects are measured.
Meeting this table does not excuse a slower small-, large-, or extreme-image
path. Optimization continues after the minimum gates pass, and reviewed
Hebog-on-Hebog performance curves are retained as regression baselines.

## 12. Benchmark protocol

1. Freeze exact released and `master` PyBDSF revisions. Run each in an isolated environment with
   the same dependency versions where compatibility permits, and record every unavoidable
   dependency difference.
2. Pin CPU affinity and disable unrelated workloads.
3. Record the host, logical/physical cores, RAM, storage, filesystem cache policy, and worker
   topology.
4. Pin native BLAS/OpenMP thread counts to avoid hidden oversubscription.
5. Execute one unmeasured warm-up followed by at least five measured repetitions.
6. Record every repetition; compare medians and report minimum, maximum, and median absolute
   deviation. Compute the 95% bootstrap confidence intervals required by the performance gates;
   add repetitions when either result is inconclusive.
7. Measure wall time, process CPU, peak RSS, aggregate worker memory, read/write bytes, Dask task
   count, transfer bytes, spill bytes, and failures/retries.
8. Produce separate scientific comparisons for the same outputs before accepting a speedup.
9. Interleave size regimes and implementation order where practical to reduce thermal, cache, and
   storage-drift bias. Record serial, local, and Dask results around measured crossovers rather
   than reporting only the selected winner.
10. Compare with the previous reviewed Hebog curve and apply the regression rule in Section 1.
11. Store JSON results under `benchmark-results/` and commit only compact reviewed summaries with
   reproduction commands.

Run both cold-cache and warm-cache I/O measurements when FITS reading is material. Use warm-cache
results for algorithm tuning and cold-cache results for operational expectations.

For intermediate-store comparisons, also record the format and library
version, store/backend type, chunk and shard geometry, codec pipeline,
compression and checksum settings, fill and missing-chunk policy, object/file
count, metadata operations, internal I/O/thread concurrency, and whether each
backend operation is atomic or conditionally created. Measure generation
validation and restart cost rather than timing only successful chunk writes.

For scalability runs, also record logical image shape and bytes, input and
output plane count, storage layout, tile cores and halos, partition count,
worker-node count, workers and threads per node, scheduler CPU and memory,
RAM per node and worker, admitted memory, reserved headroom, worker occupancy,
task throughput, boundary-summary volume, reduction depth,
storage throughput, straggler distribution, and recovery cost. Run strong
scaling on the same 100,000-by-100,000 case and weak scaling with fixed pixels
per worker. Preserve every topology result; do not report only the best node
count.

## 13. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Low-SNR threshold crossings differ | Report completeness/reliability curves and validate Rapthor filter decisions |
| Extended or blended sources diverge | Maintain dedicated fixtures and stratified metrics; do not hide them in aggregate recovery |
| PyBDSF is not deterministic | Freeze multiple reference runs and separate same-tool scatter from replacement differences |
| PyBDSF `master` moves during development | Pin the exact commit for every benchmark record; refresh deliberately at qualification milestones without rewriting prior results |
| Released and `master` PyBDSF differ scientifically | Compare both with independent truth and the Rapthor contract; document rather than average or silently select divergent outputs |
| Development overfits the validation matrix | Keep a frozen qualification set out of routine TDD and tune only on development/regression cases |
| A comparator defect hides divergence | Test matching and report calculations against analytic catalogues and known assignments |
| Distributed failure tests are flaky | Prefer deterministic fault injection; reserve real worker loss and spill for controlled runners |
| Dask overhead erases kernel gains | Use coarse batches, publish data once, and retain an efficient local executor |
| Full planes or global gathers exhaust workers | Make memory proportional to tile core plus halo, use bounded summaries and hierarchical reductions, and enforce worker-memory gates |
| Conservative tiles underuse memory-rich nodes | Derive tile batching and caches from admitted memory and measured kernels while keeping ownership and results partition invariant |
| Large-image tuning slows common small inputs | Maintain logarithmic size-stratified benchmarks, collapse small work to one low-overhead tile, and reject unapproved per-tier regressions |
| A fixed executor crossover becomes stale | Benchmark both sides of every transition and derive planning from measured resources, storage, workload, and overhead rather than image size alone |
| Tile boundaries change scientific results | Use explicit halos and ownership, boundary/corner fixtures, partition-invariance properties, and deterministic reconciliation |
| Scheduler load grows faster than useful work | Keep graph size proportional to tiles and stages, batch small work, use tree reductions, and qualification-test scheduler throughput at 100-plus nodes |
| Shared storage bottlenecks hundreds of workers | Benchmark windowed FITS and chunk-addressable stores, stagger or batch I/O, and freeze storage-specific throughput gates |
| A second storage backend duplicates policy and obscures performance behaviour | Keep Zarr as the sole intermediate image-plane backend, optimize it across all tiers, and require an ADR amendment before adding another backend |
| A missing Zarr chunk is silently interpreted as valid fill data | Configure strict missing-chunk reads and publish a run generation only after its exact expected chunks and checksums validate |
| Concurrent branches exceed memory | Use resource annotations and measure aggregate RSS before enabling concurrency |
| Numba compilation affects latency | Warm/cache kernels explicitly and report cold and warm timings |
| Catalogue compatibility becomes coupled to internals | Keep a versioned internal schema and an isolated PyBDSF/LSMTool adapter |
| Rapthor details leak into the scientific core | Enforce inward dependencies, isolate workflow adapters, and test a non-Rapthor public-API workflow |
| Premature extensibility obscures the science | Add narrow protocols only for demonstrated variation points; reject generic registries, service locators, and plugin frameworks without a concrete use case |
| Performance work makes code opaque or duplicated | Isolate optimized kernels behind typed APIs, retain the readable serial oracle, and require profile, science, and review evidence for added complexity |
| Native code adds more maintenance than speed | Require the 10% profile, 2x kernel, and 5% end-to-end gates; retain Python/Numba unless a prototype and full wheel matrix pass |
| Native threads oversubscribe Dask workers | Release Python for native-only work, pass explicit thread budgets, default to one native thread per Dask task, and benchmark aggregate CPU occupancy |
| Binary wheels reduce portability | Keep native acceleration optional until all supported wheels and source builds pass; never require users to compile during a normal supported install |
| Terminology drifts across PyBDSF, LSMTool, Rapthor, and Hebog | Maintain a reviewed glossary, map legacy names explicitly, and include vocabulary in contract review |
| Architecture diagrams become speculative or stale | Keep code-native diagrams at stable boundaries, review them with architectural changes, and defer unstable detail |
| Full PyBDSF scope delays delivery | Implement only features proven necessary by the Rapthor contract and dataset matrix |
| Algorithm licensing or attribution is unclear | Use published algorithms, write new code, document sources, and complete review before release |
| A frequent release is mistaken for production readiness | Label every `0.x` capability and limitation explicitly; require the complete gates and soak before 1.0 or default cutover |

## 14. Open decisions after Phase 0

- Which domain experts approve the glossary and naming conventions before the Phase 0 exit gate?
- Should nonlinear fitting use SciPy least-squares, a small dedicated compiled kernel, or both?
- Is an undecimated wavelet transform required, or does a beam-aware matched-filter bank satisfy the
  extended-source gate more efficiently?
- Which worker-local cache policy best complements the Zarr intermediate store:
  bounded in-memory arrays, Dask worker data, or store-backed rereads?
- Which Zarr store, codec, chunk geometry, and concurrency settings meet the
  100,000-by-100,000 I/O, restart, provenance, and final FITS-materialisation
  gates on Rapthor's deployment?
- Should internal catalogue shards use Arrow/Parquet before the compatibility
  adapter materialises FITS or LSMTool products?
- What resource names and limits should Rapthor use for source-finder CPU and memory admission?
- Which scientific tolerances require formal SKA science approval before default cutover?
- Will domain experts review the current Given/When/Then-style pytest acceptance scenarios
  directly, or would a Gherkin layer add real collaboration value later?

## 15. Definition of done

The project is ready to release `1.0.0` and replace PyBDSF in Rapthor when:

1. Development, regression, and held-out qualification suites cover compact, blended, extended,
   low-SNR, edge, invalid-pixel, and varying-noise cases without qualification-set tuning.
2. All reviewed scientific gates pass for serial and Dask execution.
3. For every gate-designated case, the complete `filter_skymodel` matched median is at least 50%
   lower than released PyBDSF and lower than the pinned PyBDSF `master` median, with both ratios
   satisfying the confidence rule in Section 1.
4. Every frozen size and execution-crossover tier has a reviewed Hebog baseline and no unapproved
   regression under the 5% confidence rule; the 50% gate is treated as a floor, not an optimization
   endpoint.
5. Peak memory, scheduler overhead, graph size, retry, and resume behaviour meet operational gates.
6. Rapthor can select either backend, dual-run them for comparison, and safely fall back to PyBDSF.
7. Public schemas, configuration, migration, benchmark reproduction, and limitations are documented.
8. Analytic tests validate the matching and comparison oracles independently of PyBDSF.
9. CI covers deterministic tests and controlled runners continuously monitor science and
   performance regressions.
10. Ruff and Pyright pass, branch-aware coverage remains at or above 80%,
    architecture tests enforce inward dependencies, and a documented
    non-Rapthor workflow uses the public API and serial executor without its
    integration code importing or constructing orchestration-specific objects.
11. The glossary, domain model, and code-native diagrams match the released architecture and make
   legacy compatibility names distinct from Hebog's internal concepts.
12. A 100,000-by-100,000 qualification image completes with scientifically equivalent,
    partition-invariant products on 100 and at least 200 Dask worker nodes; no worker materialises
    a full plane, and the frozen memory, spill, scheduler, recovery, runtime, and scaling-efficiency
    gates pass on representative production nodes with hundreds of GB of RAM.
13. If Hebog contains native code, the accepted native-code ADR, complete
    supported wheel matrix, source build, safety checks, license/provenance,
    scientific equivalence, fallback, and cold/warm performance gates pass.
