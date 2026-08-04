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

Scientific comparison is conjunctive rather than compensatory. Hebog must
meet the reviewed absolute community-science gates and be no worse than both
the released and pinned-`master` PyBDSF references on every declared,
direction-aware comparable metric and governed population. Better flux
accuracy cannot compensate for worse astrometry or a heavier catastrophic
tail. For bias, coverage, and dispersion, "better" means closer to the
predeclared ideal rather than numerically larger. This objective applies to
aggregate and governed-stratum behaviour, not to every individual noisy
source realization, where random ordering has no stable scientific meaning.
Use paired one-sided confidence intervals to distinguish a real regression
from sampling noise, retain signed point estimates, and describe a point
estimate in the worse direction as inconclusive rather than as an
improvement unless the interval establishes otherwise.

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

Scientific choices must remain within the community best-practice envelope
documented by peer-reviewed astronomy literature and source-finder challenges.
Consensus across established observatory pipelines is a strong guide, but it
is not a vote that makes one convention or implementation scientific truth.
Analytic and injected governed truth remain the primary scientific oracles;
PyBDSF remains a compatibility oracle. A deliberate departure from literature
or cross-pipeline consensus requires an explicit rationale, governed evidence,
and renewed human scientific review before promotion.

The initial thresholds below began as engineering gates requiring review with
an SKA imaging/domain expert during Phase 0. The 2026-07-31
[scientific pre-review](../docs/reference/scientific-pre-review.md) amended the low-SNR rule and
terminology after comparison with several observatory pipelines and published source-finder
challenges. Gemma Danks approved those amendments and the Phase 3-specific
decisions on 2026-08-02 in the
[Phase 3 scientific review record](../docs/reference/phase-3-review-record.md).
Report metrics separately for isolated compact, blended, extended, edge,
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

Before tuning Phase 3 segmentation against either PyBDSF reference, freeze
reviewed source-filtering-mask and island-object gates. Pixel accuracy alone
is not suitable because true-negative background pixels dominate it. Report
mask precision, recall, and intersection over union over the valid region,
then match islands by overlap and report unmatched islands, split and merge
counts, and matched-island overlap. Analytic threshold and connectivity cases
must match exactly. Generated and reference-product non-inferiority margins
are recorded in the reviewed-provisional Phase 3 gate contract after the
scientific reviewer considered dataset fitness and the normal boundary
differences caused by RMS and threshold crossings. Those margins support the
compact Phase 3 `0.x` scope; they do not establish catalogue, multiscale, or
production equivalence.

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
- with the RMS map and island threshold fixed, increasing the detection
  threshold can only remove detection seeds;
- increasing the island threshold can only remove active pixels, although it
  may split one connected island into several labels; it must not invent a
  new detection seed;
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
    detection.py            normalization, detection seeds, and threshold masks
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

Hebog has no backward-compatibility guarantee during pre-production. Prefer
the cleanest current design and remove or replace obsolete Hebog APIs,
schemas, development stores, and configuration without compatibility shims,
deprecation periods, legacy readers, or migration code. Keep a breaking change
explicit in its Conventional Commit, current documentation, and release notes,
and make stale artifacts fail clearly. Add migration support only when the
user explicitly requests it for a particular interface. This policy does not
relax the PyBDSF/Rapthor compatibility target or scientific reproducibility
requirements.

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
| `0.3.x` | FITS, beam, WCS, schemas, validation, and structurally valid empty internal products |
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

Treat `notebooks/source_finder_demo.py` as the living user-facing demonstration
of the latest implemented vertical slice. Update it in the same coherent change
whenever a new or materially changed scientific stage, product, executor path,
or workflow integration can be demonstrated. Keep the notebook deterministic
and redistributable, show observable outputs rather than only calling an API,
and state incomplete or experimental behaviour explicitly. Notebook updates
supplement rather than replace analytic, equivalence, acceptance, qualification,
or performance evidence. Validate every update with strict Marimo checks and a
successful executable export; record an explicit reason in `LOG.md` when a
user-visible capability cannot safely or practically be included.

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
   output schemas, and known compatibility gaps. The living Marimo demonstration
   must reflect every capability that can be demonstrated safely and
   redistributably in its current vertical slice.
7. Current versioned schemas and documentation for the supported API and
   product contract. Pre-`1.0` breaking changes must be explicit but do not
   require backward compatibility, migration guidance, or a deprecation
   period.
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

**Technical foundation status:** complete on 2026-07-18. **Scientific contract
closure status:** complete on 2026-08-02. The captured baselines, comparison
harness, contracts, governed manifests, and named review establish the Phase 0
foundation. The external facility review remains a separate governance
follow-up and does not turn measured engineering gates into
facility-demonstrated claims.

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
3. **Completed 2026-08-02:** obtain scientific/domain sign-off after the first
   research pass completed on 2026-07-31. The reviewer packet was:

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
4. **Completed 2026-08-02:** record the scientific pre-review amendments as
   approved, mark the Phase 3 gate contract `reviewed-provisional`, rerun the
   relevant contract, equivalence, documentation, and normal handoff checks,
   and record the closure evidence in `LOG.md`.
5. Complete the facility review and controlled 1/10/50/100/200-node evidence
   before calling the extreme-image gates demonstrated. This is not a Phase 1
   start gate and may remain open after technical and scientific Phase 0
   closure.

Phase 1 and Phase 2 red-green-refactor work was permitted while steps 1 to 3
were in progress when it used the frozen PyBDSF profile and clearly
provisional contracts. Human review does not replace automated comparison and
need not manually certify every product. It approves whether the dataset
matrix, tolerances, terminology, defaults, and intentional deviations define
the right scientific and operational contract; PyBDSF remains a compatibility
oracle rather than scientific ground truth. This sign-off permits the reviewed
compact contracts to advance; later phase-specific review and evidence remain
required before claiming complete scientific equivalence or cutting Rapthor
over to Hebog.

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
- [x] Obtain domain review of the glossary, naming conventions, and scientific thresholds in
      Section 5.

Technical exit gate: documented commands reproduce both baselines and the reference-divergence
report in clean, isolated environments; comparison tests prove the harness against analytic cases;
and the held-out qualification set is frozen. ADRs 003, 004, and 005 are accepted, and the
provisional large-image resource and scaling gates are frozen. This technical foundation is
complete. Domain review was completed on 2026-08-02; facility review plus
controlled multi-node evidence remains required before the extreme-image
gates are called demonstrated.

### Phase 1: FITS, beam, WCS, and internal models

**Technical status:** complete on 2026-08-01. **Release status:** qualified as
an experimental `0.3.x` infrastructure capability by the
[Phase 1 release-readiness record](../docs/reference/phase-1-release-readiness.md).
It does not implement scientific source finding and therefore makes no Hebog
versus PyBDSF equivalence or speed claim.

Start rule applied: Phase 1 infrastructure and red-green-refactor work was
permitted while Phase 0 scientific review was in progress. The sign-off and
approved amendments were recorded on 2026-08-02.

- [x] Write failing round-trip and boundary tests for valid, empty, masked, corrupt, and
      unsupported FITS inputs and products.
- [x] Write failing tests for partition manifests, bounded window reads, halo clipping, global and
      tile coordinates, chunk checksums, interrupted writes, and restartable materialisation.
- [x] Define versioned internal catalogue and materialised result schemas from
      failing physical-boundary, relationship, empty, serialization, and restart-metadata tests;
      keep their scientific status provisional until Phase 0 human sign-off,
      completed on 2026-08-02.
- [x] Define a narrow image-source seam and explicit Zarr product boundary from
      concrete FITS and workflow tests; do not introduce a generic sink protocol,
      registry, or plugin system before a demonstrated second implementation.
- [x] Write and accept the intermediate-storage ADR after a measured Zarr v3 prototype; use Zarr
      as the sole intermediate image-plane backend and remove the private NumPy-file path.
- [x] Prove aligned independent Zarr writes, strict missing-chunk behaviour, corruption detection,
      duplicate/conflicting retries, interrupted-run recovery, and exact validated completion
      manifests on `LocalStore`; retain deployment-store atomicity as a separate open gate.
- [x] Benchmark the selected Zarr v3 `LocalStore`, fixed codec pipeline, FITS
      ingestion, and final materialisation at 256, 512, 1,024, and 3,000
      pixels per side with one warm-up and five measurements; retain the
      machine-readable results outside Git and the compact findings in the
      Phase 1 release-readiness record. The first curve justifies retaining
      the simple fixed policy rather than adding unproven tuning.
- [x] Define a deterministic partition manifest and ownership rule so every output pixel and source
      has exactly one owning tile.
- [x] Read and validate required image planes through bounded windows or a chunk-addressable store;
      use memory mapping where safe without requiring a worker to map or materialise every plane.
- [x] Write large intermediate planes in independently retryable chunks before compatibility
      materialisation.
- [x] Keep one-tile work to one serial Zarr chunk per image product, with no
      scheduler fanout or second assembly copy; measure complete ingestion and
      materialisation overhead before adding any initialization, concurrency,
      or codec tuning.
- [x] Make FITS, mask, RMS, and catalogue round-trip tests pass without weakening assertions.
- [x] Cap Hebog-controlled final-product assembly to one admitted full-width
      tile row plus the currently decoded chunk, reuse the validated owned
      chunk for one-tile work, and record complete third-party allocation
      counters as unavailable rather than fabricated.

Exit gate: reference inputs round-trip with correct coordinates, units, shapes, and invalid pixels;
the intermediate-storage ADR is accepted from reproducible evidence; missing or incomplete chunks
fail closed; the package can emit empty, structurally complete internal products; and the same I/O
contract handles one-tile and many-tile images with memory bounded by configured tile and halo
sizes. This gate passed on 2026-08-01. Deployment-store concurrency and
atomicity remain Phase 6/8 qualification work and do not become demonstrated
because `LocalStore` passed.

### Phase 2: robust background and RMS estimation

- [x] Establish an explicit clipping policy and a vectorised serial oracle for
      batches of independent windows. Cover constant and negative backgrounds,
      positive affine transforms, masks, NaNs, bright outliers, zero RMS, and
      insufficient retained samples without Python loops over windows.
- [x] Extend analytic and property tests through coarse-grid placement and
      interpolation for affine backgrounds, edges, sparse adaptive cells, and
      fallback behaviour.
- [x] Add tile-boundary and partition-invariance tests for RMS windows, interpolation, and adaptive
      bright-source regions.
- [x] Place coarse-grid windows in bounded batches and apply the serial
      sigma-clipped statistics oracle to satisfy those tests.
- [x] Compute global coarse-grid and interpolation metadata from bounded batch
      results, and send local bracketing summaries rather than global grids or
      complete image planes to output tiles. Multi-level distributed reduction
      remains part of the Phase 6/8 graph-and-scale gate if the coarse-summary
      volume or scheduler load becomes material at 30,000 or 100,000 pixels.
- [x] Reuse prepared coarse summaries and calculate adaptive fine-grid cells
      only in merged local regions around explicit bright candidates.
- [x] Interpolate cached coarse samples; fallback interpolation does not
      recompute statistics.
- [x] Treat masks, NaNs, edges, negative values, zero RMS, and insufficient
      samples explicitly.
- [x] Retain vectorised NumPy, SciPy, and Astropy without Numba: controlled
      four-core measurements meet both component budgets, so profiling does
      not justify another implementation path.
- [x] Do not build a Rust or C++ prototype: no remaining kernel meets the
      native-code decision gate after the vectorised implementation met the
      end-to-end component and memory gates. If a candidate later meets the
      gate, benchmark one
      minimal Rust and/or C++ prototype against the same Python/Numba contract
      before selecting a language or accepting an ADR.
- [x] Benchmark window batching and interpolation slab size on the
      representative image; retain 64-cell batches and 1,500-by-1,500 output
      tiles for the recorded four-core curve. Keep float64 as the scientific
      policy because equivalence is established at that precision; a lower
      precision remains ineligible until it passes the same suite.

Provisional component budget on the 3000 by 3000 reference image: no more than 4 seconds for the
true-sky background stage and no more than 3 seconds for the flat-noise RMS product on four
allocated CPU cores.

Exit gate: the relevant analytic, partition, executor, compact-reference, and
representative RMS matrix passes. On the controlled 3,000-by-3,000 four-core
run, the true-sky median was 2.471 seconds against a 4-second budget and the
flat-noise median was 2.527 seconds against a 3-second budget. Maximum sampled
Hebog process RSS was 974,192,640 bytes, below the approximately 1.30 GB
matched PyBDSF observations. This gate passed on 2026-08-01. Raw exploratory
evidence remains under ignored `benchmark-results/phase-2/`; the committed
summary and scope limitations are in the Phase 2 release-readiness record.
Automatic bright-candidate discovery, final product persistence, and
multi-node graph qualification remain their explicitly assigned later phases.

### Phase 3: thresholding, connected islands, and compact deblending

**Readiness status:** technically complete on 2026-08-01 and scientifically
approved for the compact experimental `0.x` scope on 2026-08-02. The
provisional gates were frozen before held-out inspection, all Phase 3-scope
automated gates pass, and their status is now `reviewed-provisional`. The
release-readiness record preserves the full representative multiscale
divergence assigned to Phase 5 rather than weakening the compact contract.

The compatibility evidence is explicit but not automatically normative.
Released and pinned-master PyBDSF use SciPy connected-component labelling with
eight-neighbour connectivity, include pixels at the island threshold, require
a peak strictly above the detection threshold, and normally derive a minimum
island size from the beam area with a six-pixel floor. Rapthor requests hard
thresholds and adaptive RMS discovery. Test these observed semantics against
analytic truth and both frozen references; do not reproduce them silently or
copy their implementation.

Phase 3 stops at detection topology: accepted connected islands, a
source-filtering mask, deterministic detection-seed membership, and any
reviewed deblended regions needed to initialize Phase 4. It does not invent
photometry to populate the measured `Island` schema, fit Gaussian components,
group final sources, or materialise a compatibility catalogue. Those remain
Phase 4.
`hebog.pipeline.find_sources` therefore remains explicitly unimplemented until
the later measurement and multiscale stages can satisfy its complete result
contract.

Execute the phase in the following TDD and closure order. Keep each numbered
slice as a coherent local commit and allow a small experimental release after
any useful slice whose stated tests, documentation, and earlier gates pass.

1. **Freeze detection and segmentation contracts before implementation.**

   - [x] Add failing analytic tests for exact threshold boundaries, positive
         emission only, invalid or zero-RMS pixels, masks, negative
         backgrounds, diagonal eight-neighbour contact distinguished from
         four-neighbour behaviour,
         minimum-size boundaries, image edges, non-square images, and empty
         or all-invalid detections.
   - [x] Extend the independent comparison oracle through tests first with
         mask intersection over union and overlap-based island matching,
         including split, merge, unmatched, empty, and invalid-region cases.
         Do not use background-dominated pixel accuracy as the Phase 3 gate.
   - [x] Add immutable Phase 3 supplements to the existing frozen manifests
         for SNR bins, close-pair
         separation and flux ratio, saddle depth, sub-threshold bridges,
         source density, and every tile-edge/corner topology. Freeze the
         held-out qualification supplement and reviewed mask/object margins
         before using reference results to tune an algorithm; do not rewrite
         the Phase 0 entries or inspect held-out results during TDD.
   - [x] Record eight-neighbour connectivity and the two threshold comparison
         rules as fixed, documented compact-detection semantics. Do not expose
         alternate connectivity without a concrete workflow. Make the
         minimum/maximum island-size policy explicit in typed scientific
         configuration. The Rapthor adapter may derive its
         compatibility values from beam metadata, but the scientific kernel
         must not inherit a hidden workflow default.

2. **Implement bounded normalization and two-threshold detection.**

   - [x] Add a pure serial tile kernel that computes
         `(image - background) / rms` only for finite, valid, positive-RMS
         pixels and emits separate island-membership and detection-seed masks.
         Invalid pixels are never members or seeds; negative emission is not
         detected by the initial total-intensity profile.
   - [x] Prove positive-affine invariance and the two distinct monotonicity
         properties in Section 7.3. An island-threshold increase may split a
         component even though the active-pixel mask only shrinks.
   - [x] Fuse normalization with thresholding for each bounded tile by
         default. Do not persist a complete normalized plane or add another
         storage backend unless reuse measurements demonstrate a complete-path
         benefit.

3. **Complete automatic adaptive-RMS candidate discovery and persistence.**

   - [x] Add an explicit high-significance adaptive-candidate policy and use
         the same threshold/connectivity primitives to scan bounded tiles
         against the cached coarse background/RMS interpolation. Select a
         candidate's global peak deterministically, resolving equal peaks by
         lexicographic `(y, x)` position.
   - [x] Reconcile candidates that cross tile sides or corners, request sparse
         adaptive refinement from the existing coarse cache, and prove that
         neither coarse statistics nor candidate regions are recomputed
         because of partition shape, task order, or retry.
   - [x] Compare piggybacked candidate summaries with a separate bounded scan
         and retain the simpler path unless complete-stage evidence justifies
         extra coupling. Record any additional image read explicitly.
   - [x] Publish owned background/RMS tiles through the Phase 1 Zarr generation
         contract and prove restart, duplicate retry, and missing-chunk
         behaviour without assembling a full plane.

4. **Establish the one-tile connected-island oracle with SciPy.**

   - [x] Use the established `scipy.ndimage` labelling and reduction
         primitives first. Adopt the reviewed connectivity, accept a component
         only when its combined pixels satisfy the size policy and contain a
         detection seed, and keep threshold inclusion rules explicit.
   - [x] Reduce pixel count, global bounding box, peak SNR and position,
         lexicographically smallest member pixel, and image-edge contact in
         vectorised or compiled library operations. Do not copy the image once
         per island or loop over island pixels in Python.
   - [x] Define detection-stage records separately from measured catalogue
         records. Assign final island identifiers and ordering from canonical
         reconciled global properties, never local SciPy labels or executor
         completion order.

5. **Reconcile islands before deblending.**

   - [x] Put compact sources and islands across every side, diagonal, and
         four-tile corner topology. Exercise shifted partition origins, tile
         shapes, worker counts, reversed completion, deterministic retry, and
         labels whose local numeric values deliberately differ.
   - [x] Summarize boundary label contacts, including diagonal corner contact
         for eight-neighbour connectivity, and merge equivalences and island
         reductions hierarchically. Summary volume and graph size must scale
         with tile boundaries and island shards, not pixels or scheduler-held
         full label planes.
   - [x] Write accepted boolean source-filtering-mask cores as independently
         owned Zarr chunks. A diagnostic label plane is optional and must not
         become a prerequisite for reconciliation or catalogue ownership.
   - [x] Prove one-tile and many-tile membership, global summaries, stable
         identifiers, and scientific mask values are identical before
         comparing Hebog with PyBDSF.

6. **Select and implement only the deblending needed by the compact contract.**

   - [x] Define the observable output as deterministic regions or seeds for
         later measurement, not as fitted Gaussian components or final
         sources. Specify equal-peak, saddle, boundary, noise, and failure
         behaviour in analytic tests first.
   - [x] Compare documented multilevel and watershed approaches using mature
         SciPy primitives. Evaluate scikit-image only if its established
         implementation materially improves scientific behaviour or reduces
         maintained custom code enough to justify its runtime, wheel, worker
         image, and serialization cost. Do not add it speculatively.
   - [x] Accept the simplest algorithm that passes close-pair separation,
         flux-ratio, saddle-depth, edge, and partition tests. Record an ADR
         only if the selection creates a durable dependency or compatibility
         consequence.
   - [x] Batch bounded reconciled compact-island regions by pixel cost. Large
         or extended islands must remain explicit, deterministic input for the
         Phase 5 partitioned/multiscale path; never drop them, silently treat
         them as successfully deblended, or materialise an unbounded island on
         one worker.

7. **Qualify the phase and record release readiness.**

   - [x] Expand generated-truth tests into SNR-stratified seed/island
         completeness and reliability, object overlap, split/merge, blend,
         edge, and source-density reports with confidence intervals where
         appropriate.
   - [x] Compare the Hebog source-filtering mask and connected regions derived
         from each mask with both exact PyBDSF references on the
         redistributable compact case and with the controlled representative
         products. Report reference divergence rather than selecting one
         reference as truth.
   - [x] Add serial/Dask conformance tests after the serial semantics pass.
         Keep executor tasks coarse and prove retry and task-order invariance.
   - [x] Benchmark the complete Phase 3 detection, labelling,
         reconciliation, and compact-deblending stage at 256, 512, 1,024, and
         3,000 pixels per side across sparse, normal, and dense compact
         workloads. Use one warm-up and at least five repetitions, retain
         task, summary-volume, CPU, wall-time, and peak-memory evidence, and
         compare affected tiers with the previous Hebog curve.
   - [x] Publish a Phase 3 release-readiness record stating implemented
         capability, scientific evidence, performance, portability checks,
         limitations, and the remaining Phase 4/5 work.

Use the same thresholding, labelling, reduction, and reconciliation semantics
for a one-tile image and a distributed image. Whole-image SciPy labelling may
optimize the one-tile case, but it must not become a second scientific
implementation or a prerequisite for correctness. There must be no all-pairs
island matrix, task per island, or algorithm whose worker memory grows with
the complete image. Benchmark a log-spaced source-density ladder and
investigate any superlinear growth; an unexplained all-pairs or quadratic path
fails the phase even when the representative image is fast.

Exit gate: analytic topology cases are exact; generated and dual-reference
Phase 3-scope mask, seed, island, blend, edge, partition, and executor reports
meet the provisional gates; the named scientific review has approved the
relevant semantics, margins, and explicit multiscale deferral; and the
controlled four-core 3,000-by-3,000 complete Phase 3 stage median is no more
than the inclusive 3.5-second component budget without regressing earlier RMS
evidence. The 3.5-second gate includes durable background, RMS, and mask Zarr
publication, which the original provisional 2.5-second line also counted in a
later output budget. The later output allocation is reduced by the same one
second, so this clarification does not grow the complete performance budget.
Memory, task count, boundary-summary volume, and the density ladder show no
image-sized gather or quadratic source-count path. Automated technical gates
passed on 2026-08-01: the exact representative median was 3.193 seconds and
the generated 3,000-square sparse/normal/dense medians were 2.848, 2.963, and
3.489 seconds. Gemma Danks approved the scientific decisions on 2026-08-02,
so the Phase 3 exit gate passes. This establishes compact detection topology
only, not catalogue equivalence, multiscale completeness, Rapthor readiness,
or the complete project speedup.

### Phase 4: measurement, fitting, and catalogue compatibility

**Readiness status:** prepared on 2026-08-02 after Phase 3 scientific and
technical closure. Phase 4 starts from deterministic connected islands and
compact deblended-region topology. It measures compact emission, fits and
associates Gaussian components where justified, and produces a
Rapthor-compatible catalogue view. It does not silently measure Phase 3
deferrals, implement multiscale emission, or claim the complete
`filter_skymodel` workflow; those remain Phase 5 and Phase 7 work.

**Execution status:** Step 1 was completed on 2026-08-02 without generating or
inspecting qualification results. Gemma Danks reviewed and approved the
measurement policy after the gate amendments recorded below. Those decisions
remain recorded, but the contracts are frozen-provisional after the third
held-out failure so the consumed campaign cannot be rerun accidentally. Step 2
was completed on 2026-08-02 with an exact,
bounded worker-local region processor that is serial/Dask invariant and returns
only compact records. Step 3 was completed on 2026-08-02 with a vectorized
owned-pixel moment oracle, explicit availability outcomes, and serial/Dask
record equivalence. Step 4 was completed on 2026-08-02 with a bounded fit-all
SciPy reference, independent Astropy agreement, typed failure outcomes, and
serial/Dask equality. Step 5 now has celestial transformation, beam
deconvolution, correlated-noise sandwich covariance, and explicit
uncertainty-availability semantics. Steps 6 and 7 now construct bounded
canonical catalogue shards, materialise the minimal Rapthor FITS view, and
pass both exact compact PyBDSF references. The generated close-pair regression
exposed
a scientific-contract blocker: three sub-beam pairs have only one observable
image maximum, so the reviewed one-region/one-source rule cannot satisfy the
declared seven-source completeness gate. Gemma Danks approved the
observable-resolvability and explicit truth-group amendment on 2026-08-03.
The affected regression and unseen qualification definitions now require
replacement and review before qualification inspection.

Manifest schema 2 and the replacement definitions were prepared on
2026-08-03 without generating or inspecting replacement held-out output. The
approved observable groups pass the crowded regression. That run exposed a
second contract issue: flat absolute tail gates fail ordinary noise scatter
for one 12-SNR source. Provisional unresolved-group margins and an
SNR-stratified confidence-interval decision rule now require named numerical
review before qualification inspection. Gemma Danks approved those numerical
and statistical amendments on 2026-08-03; regression and calibration
implementation now precede the first held-out run. Generator-v3
beam-correlated noise, generalized sandwich covariance, and a bounded
residual-background context fit now pass the powered regression campaign.
Each SNR stratum contains 1,600 eligible measurements across the same 200
predeclared noise realizations.

The first and only inspection of the powered held-out campaign was run on
2026-08-03 after regression passed. Completeness, overall reliability,
measurement availability, position calibration, and most flux calibration
gates passed. The campaign nevertheless failed the reviewed classification,
catastrophic-outlier, and four normalized-mean gates. No parameter, population,
seed, or margin was changed after inspection. Phase 4 is scientifically
blocked; its performance qualification is deferred because the closure order
does not benchmark a known-ineligible scientific implementation. Preserve the
failed campaign as governed evidence, freeze a new unseen campaign before any
corrective implementation work, and obtain review for the unresolved-group
reliability denominator and any revised boundary-classification policy.

Literature review on 2026-08-03 selected a frozen-provisional correction before
production changes: use the ATLAS two-sigma integrated-to-peak uncertainty
test, gate point-source specificity and clearly resolved recovery separately,
report marginal-extension classification by SNR, use peak flux for
beam-compatible sources, and retain reliability only as a global catalogue
metric. The viewed campaign is archived unchanged. A second unseen campaign
with 200 disjoint seeds, distinct WCS, negative background, varying RMS,
invalid pixels, correlated noise, and predeclared point/clear/marginal shape
strata is frozen at recipe SHA-256
`54657fb15360afbbc2536667aec37e3f4b9b033f756633a82feec57a2a14ca49`.
Corrective TDD is complete and the independent powered regression passes. It
predeclares clear extension as fitted-to-beam truth area ratio at least 3 and
SNR at least 25, keeps moderate extension and resolved/marginal integrated-flux
uncertainty report-only, and records the intentional peak-as-total divergence
from raw unresolved PyBDSF output. Gemma Danks approved the amendment on
2026-08-03; both contracts are reviewed-provisional and the campaign remained
unopened throughout review.

The third frozen campaign was opened exactly once on 2026-08-03 after Gemma
Danks approved the marginal-flux and image-footprint corrections. It recovered
all 6,600 truth groups, passed reliability, availability, classification,
shape, position, peak-flux, and unresolved-group gates, but failed two frozen
scientific decisions. Thirty-six of 6,400 matched individual sources were
gated catastrophic outliers (0.5625% against the 0.5% maximum), and the
unresolved integrated-flux normalized-residual mean interval was
0.0823--0.1846, crossing the approved absolute 0.15 boundary. The 34,746-byte
ignored evidence record has SHA-256
`ed060b7703161ba01037939ff9a8e4b6e3d6ab527dc3b1fd45753dfb69c1165e`.
No rerun, gate change, or post-inspection tuning occurred. The campaign is now
viewed evidence, both contracts have returned to frozen-provisional to prevent
accidental reuse, Phase 4 remains scientifically blocked, and controlled
performance qualification remains ineligible. Do not create a succession of
replacement campaigns merely to obtain a pass; require a new reviewed
scientific recovery protocol before any further held-out campaign.

A same-campaign reference audit on 2026-08-03 established the recovery
direction without rerunning Hebog. Released PyBDSF 1.14.1, using Rapthor's
exact source-finding options on the third campaign, recovered 6,599 of 6,600
groups with 99.75% point-source specificity and a 0.1875% canonical
catastrophic rate. It passed those headline gates but failed 16 normalized-
uncertainty decisions and both unresolved-group 95th-percentile gates. The
complete comparison has SHA-256
`298b91312749953ef6b356fbc863343f693a0378aa0aa46815c60bb229640eb0`.
Pinned performance-improved PyBDSF `master` at
`c70103be3ae9ae9908286f144e6ce956acc0ce5c` cannot complete the same campaign:
with Rapthor's required atrous path it raises an out-of-bounds `IndexError` on
frozen seed `2026090152`, while released PyBDSF and Hebog complete that input.
The campaign therefore combines compatibility questions with stronger
truth-based requirements that PyBDSF itself does not meet. Gemma Danks has
approved the direction to preserve Hebog's better scientific results, correct
the remaining point-classification and catastrophic-tail weaknesses until
Hebog is equal to or better than released PyBDSF, close Phase 4, and then make
scalability the next active engineering focus. Numerical paired-comparison
margins and the final campaign power remain subject to named review before
the next qualification population is frozen.

The scientific basis for this phase is [Condon's treatment of errors in
elliptical Gaussian fits](https://doi.org/10.1086/133871), the
[ASKAP/EMU Source Finding Data Challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19),
the [Aegean 2.0 analysis of correlated-noise fitting and
uncertainties](https://doi.org/10.1017/pasa.2018.3), and the documented
[PyBDSF measurement and grouping
stages](https://pybdsf.readthedocs.io/en/latest/process_image.html). These
sources establish useful methods and validation questions, not an obligation
to reproduce one implementation. Use the established
[Astropy WCS API](https://docs.astropy.org/en/stable/wcs/wcsapi.html) for
coordinate conversion and evaluate the bound-constrained
[SciPy least-squares implementation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
before maintaining a custom fitter.

1. **Freeze Phase 4 meanings, datasets, and gates before tuning.**

   - [x] Write a versioned Phase 4 scientific contract and a failing contract
         test before production measurement code. Define the measurement
         plane, valid-pixel and region ownership, MFS reference frequency,
         supported image units, pixel and beam areas, peak and integrated
         flux, local RMS, fitted and deconvolved ellipses, uncertainty
         confidence level, and every coordinate and position-angle
         convention. Require explicit conversion or rejection; never infer
         missing units or WCS metadata.
   - [x] Keep island, deblended region, fitted Gaussian component, grouped
         source, catalogue row, and sky-model component distinct. Freeze the
         compact association policy from analytic blends and the dual
         references instead of assuming that one region, Gaussian, or island
         always equals one source.
   - [x] Define internal unresolved emission as an absent deconvolved shape
         plus a canonical quality flag. If the LSMTool-compatible FITS view
         requires PyBDSF's zero-axis sentinel, translate it only in the
         adapter and test that no scientific calculation interprets zero as a
         measured physical size.
   - [x] Add immutable Phase 4 development and regression supplements for
         unresolved and resolved elliptical Gaussians over SNR, sub-pixel
         centroid, beam ellipticity, source density, and blend-separation
         ladders. Include rotated WCS, unequal pixel scales, non-square images,
         image edges, masked/NaN pixels, negative backgrounds, varying RMS,
         fit failure, singular covariance, and marginal deconvolution. Keep
         numerical failure cases as governed analytic contract cases where
         encoding them as multi-source sky truth would be misleading.
   - [x] Freeze a new unseen Phase 4 qualification supplement and its generator
         before inspecting its results. Do not relabel the already-inspected
         Phase 3 held-out image as unseen measurement evidence. Include
         repeated noise realizations sufficient to assess bias and
         uncertainty coverage by SNR, shape, blend, and edge class.
   - [x] Extend the independent comparison oracle, TDD first, with fitted and
         deconvolved shape, position angle modulo 180 degrees, uncertainty
         calibration, island/source/component association, quality flags,
         and catastrophic-outlier reports. Preserve separate released and
         pinned-`master` PyBDSF results and report reference divergence.
   - [x] Retain the Section 5 position and flux gates for their declared
         populations. Before held-out inspection, add frozen-provisional
         shape, deconvolution-classification, association, bias, catastrophic
         outlier, and uncertainty-coverage margins to the versioned contract.
         Promote them to reviewed-provisional only after named review.
         Analytic noiseless cases and deterministic grouping decisions are
         exact within declared numerical tolerances; low-SNR results remain
         stratified curves, not one aggregate pass fraction.
   - [x] Obtain named human scientific review of the contract, datasets,
         proposed margins, and any departure from the literature or
         cross-pipeline consensus before treating a measurement policy as a
         stable default. Red tests and disposable algorithm-selection
         prototypes may precede review; an unreviewed prototype must not
         become the accepted scientific implementation. Use the completed
         [Phase 4 scientific review record](../docs/reference/phase-4-review-record.md)
         to record the decision and amendments.
   - [x] Select all gated populations from reference or injected truth, count
         missing candidate values as unavailable, and gate fitted shape,
         deconvolution classification/shape, parent identity, and position or
         flux uncertainty availability explicitly. Restrict position-angle
         evidence to reference ellipses with major/minor axis ratio at least
         1.1. Require at least 200 independent eligible uncertainty
         measurements per stratum and predeclare 95% interval methods with an
         entire-interval-within-margins decision rule before qualification
         inspection.

2. **Preserve exact region membership through one bounded worker pipeline.**

   - [x] Add a regression test demonstrating that deblended-region bounding
         boxes are not membership masks and cannot recover touching or
         overlapping watershed regions. Never measure a region by treating
         every pixel in its bounding box as owned.
   - [x] Refactor the coarse compact batch operation so the Phase 3 deblend
         labels remain worker-local through moment calculation and fitting,
         then return only compact typed records. Reuse the existing deblend
         algorithm; do not rerun it per measurement, send its label arrays
         through the scheduler, or require a full diagnostic label plane.
   - [x] Read only the admitted image, background, RMS, validity, and
         source-filtering-mask windows for each coarse batch. Account for
         every temporary array in the existing compact island, bounds, and
         batch memory limits, and preserve explicit Phase 5 deferrals.
   - [x] Keep the Phase 3 stage result useful for topology inspection, but make
         the Phase 4 handoff explicit enough that a summary-only caller cannot
         accidentally invent measurement membership.

   `run_compact_region_stage` now invokes a typed processor inside each
   existing coarse task with immutable physical residual, RMS, validity, and
   exact int32 watershed labels. It selects one parent connected component
   from a boolean mask window by the reconciled first pixel, so nested bounds
   cannot mix islands. Only compact processor records and topology summaries
   are gathered. Retained processor arrays are exactly 21 bytes per admitted
   bounds pixel and the result reports the largest actual batch; source/product
   reads remain bounded by `maximum_batch_pixels`, while normalized and SciPy
   watershed work remain bounded by one compact island. The summary-only API
   still returns no membership plane and all Phase 5 deferrals are preserved.

3. **Implement moments as the readable serial oracle and fit initializer.**

   - [x] Write failing analytic and property tests for amplitude, peak,
         centroid, second central moments, covariance, position angle,
         island/region flux, local RMS, translation, rotation, positive
         scaling, mask exclusion, and deterministic reduction order.
   - [x] Calculate moments with vectorised NumPy/SciPy reductions over exact
         owned pixels. Use the physical background-subtracted plane for flux
         and the normalized plane only where the contract explicitly calls
         for signal-to-noise; do not loop over pixels or RMS windows in Python.
   - [x] Convert Jy/beam pixel sums to integrated Jy using reviewed pixel and
         restoring-beam solid angles. Keep island pixel-sum flux distinct from
         fitted Gaussian integrated flux and test both against generated
         truth.
   - [x] Return explicit statuses for non-finite, non-positive,
         underdetermined, or numerically singular moments. Do not fabricate a
         valid ellipse, flux, or zero-valued uncertainty from invalid input.

   `run_compact_moment_stage` applies the pure vectorized oracle inside the
   Step 2 coarse worker-local processor. It reports the parent island and each
   exact region in canonical order. Owned-pixel photometry carries an
   explicitly named finite-mask flux; a separate Gaussian-area helper defines
   later fitted-component flux without conflating the two. Brightness-weighted
   global pixel centroids and covariance provide a fit initializer, with
   pixel-space orientation counterclockwise from positive x. Typed valid,
   shape-unavailable, and unavailable outcomes preserve usable photometry
   without fabricating shape, flux, or uncertainty. Analytic/property tests
   cover translation, rotation, scaling, masking, deterministic order, solid
   angle conversion, all governed moment failures, and serial/Dask equality.
   No qualification result was generated or inspected in this step.

4. **Select and implement compact Gaussian fitting from evidence.**

   - [x] Establish a fit-all compact reference lane initialized by the moment
         oracle. Fit bounded two-dimensional elliptical Gaussian models to
         the physical residual with explicit amplitude, center, ordered-axis,
         orientation, iteration, and convergence constraints.
   - [x] Compare Astropy modelling and SciPy `least_squares` on analytic,
         blend, failure, and representative compact batches. Prefer the
         smallest established implementation that passes the science suite
         and complete-stage profile. Supply a tested analytic Jacobian if it
         materially improves robustness or latency. Do not add native code
         unless the existing native-code gates are met.
   - [x] Define failure and non-convergence as typed outcomes with retained
         moment initialization and canonical quality flags. Decide through
         the reviewed contract when a failed fit may produce a scientifically
         usable source and when it must remain unavailable.
   - [x] Batch fits by admitted region pixels and estimated component count,
         cap work per task, and retain enough coarse tasks for occupancy.
         Never create one executor or Dask task per source or fit.
   - [x] Propose selective fitting only after the fit-all reference exists.
         A moment-only fast path must use pre-fit information, have an
         explicit eligibility status, and match fit-all catalogue acceptance,
         shape classification, and downstream decisions within frozen
         margins across development and regression matrices. Otherwise keep
         the fit; runtime evidence alone cannot justify biased selection.

   The accepted reference uses SciPy's bounded TRF `least_squares` solver on
   RMS-weighted physical residuals plus a bounded local residual-background
   offset. Astropy `Gaussian2D` with its TRF fitter
   independently recovers the same analytic parameters; SciPy keeps the
   production boundary smaller while directly exposing the residual Jacobian,
   bounds, work limit, and diagnostics. Fits remain inside existing coarse
   region tasks, so task count scales with admitted batches rather than
   sources. Every eligible compact region is fitted: no selective fast path
   is proposed because no complete-stage scientific and runtime evidence yet
   justifies one. A declared Gaussian pixel-noise correlation function uses a
   generalized OLS sandwich covariance; independent-pixel covariance is a
   flagged fallback when no correlation model is available. Singular
   covariance is absent rather than zero. Component RMS is bilinearly sampled
   at the fitted centroid in the retained context coordinate frame.

5. **Transform positions and ellipses, deconvolve the beam, and calibrate
   uncertainties.**

   - [x] Use zero-based `(x, y)` Astropy pixel-to-world conversion and a local
         tangent-plane WCS Jacobian to transform centers, covariance matrices,
         and errors. Test rotated axes, RA wraparound, unequal and signed
         pixel scales, non-square images, and the reviewed celestial
         position-angle convention.
   - [x] Deconvolve fitted and restoring-beam ellipses through covariance
         matrices. Test rotations and near-singular cases against analytic
         truth and an independent implementation. Evaluate the established
         `radio_beam` package before maintaining domain-specific edge handling;
         add it only if the correctness and maintenance benefit justifies the
         dependency.
   - [x] Treat Condon-style correlated-noise error propagation as a baseline,
         not automatically calibrated truth. Compare candidate covariance or
         Fisher-information calculations with injected Monte Carlo truth and
         the Aegean 2.0 findings, using normalized residuals and coverage
         reports for position, peak/integrated flux, and shape.
   - [x] Represent underconstrained or uncalibrated errors as absent with a
         canonical quality flag. Never use zero to mean unknown. Freeze any
         SNR floor or approximation with human review and report shape-error
         limitations explicitly.

   Astropy reconstructs the celestial WCS only inside the transformation
   boundary. A local east/north Jacobian transforms centroids, fit covariance,
   and local pixel area while preserving rotation, unequal and signed scales,
   projection effects, and RA wraparound. Fitted and beam ellipses are
   deconvolved as two-by-two covariance matrices. Fully and marginally
   unresolved results remain null internally, with the marginal state carrying
   an additional diagnostic flag. For noisy fits, positive deconvolution must
   also pass the standardized ATLAS integrated-to-peak uncertainty statistic.
   The recovery policy now requires five sigma: the earlier two-sigma rule's
   documented false-extension tail assigns physical sizes too readily, while
   independent regression left a wide 3.38-to-17.92 sigma separation between
   point and clearly resolved populations.
   Point-source specificity and clear-extension recall remain gated
   separately.
   `radio_beam` was evaluated but not added:
   Hebog's reviewed three-state policy still requires explicit logic and direct
   NumPy covariance subtraction keeps the boundary smaller. Correlated-noise
   sandwich position and flux errors are transformed when available; shape
   errors and singular/uncalibrated values are null with quality flags. The
   corrected powered regression passes for position, peak flux, unresolved
   peak-as-total flux, point specificity, and clearly resolved recall. Moderate
   extension classification and resolved/marginal integrated-flux uncertainty
   remain report-only. The replacement held-out campaign was opened once after
   named approval and failed catastrophic-flux and low-SNR/edge availability
   gates, so qualified uncertainty calibration remains an open Phase 4 exit
   condition.

6. **Associate records and construct deterministic bounded catalogues.**

   - [x] Build `Island`, `GaussianComponent`, and `SourceCandidate` records
         independently, then apply the reviewed association policy. Derive
         canonical IDs and ordering from Phase 3 global identities and
         scientific association keys, never task completion, partition-local
         labels, or worker count.
   - [x] Write compact catalogue shards per coarse batch and combine counts,
         offsets, identities, and summary metadata with a bounded tree
         reduction. Final FITS materialisation may stream ordered row groups;
         it must not gather image-sized state or an unbounded source
         population in scheduler memory.
   - [x] Reuse the current versioned catalogue models, Zarr generation
         boundary where durable intermediate ownership is required, and
         Astropy FITS output. Do not add Arrow/Parquet or a second private
         catalogue store without a measured requirement and an ADR amendment.
   - [x] Prove one-tile/many-tile, serial/executor, tile-shape, worker-count,
         task-order, and retry invariance for IDs, associations, quality flags,
         ordering, and numeric fields.
   - [x] Return partial compact records and explicit deferrals only from an
         explicitly incomplete stage API. Do not materialise a normal
         compatibility catalogue or successful `find_sources` result while
         Phase 5 regions are omitted. Keep the complete public behaviour's
         strict expected failure until compact and multiscale results merge.

   One typed shard is emitted by each existing coarse task. Canonical pairwise
   reduction has fan-in two and logarithmic depth; the convenience final
   in-memory catalogue rejects a source population above its explicit cap.
   This closes the compact Phase 4 fan-in path without adding Arrow, Parquet,
   or another storage model. One/many-tile, serial/two-worker Dask, input-order,
   and retry tests preserve identities, values, flags, and ordering. Any fit
   omission or Phase 5 deferral prevents normal catalogue completion.

7. **Materialise and validate the Rapthor compatibility view.**

   - [x] Write failing FITS contract tests through the pinned Rapthor Astropy
         reader before implementing the adapter. Rapthor, not LSMTool, reads
         this FITS product; its diagnostic path then generates makesourcedb
         text for LSMTool. Freeze the smallest loadable view:
         the eight directly consumed `Source_id`, `RA`, `DEC`,
         `Isl_Total_flux`, `Total_flux`, `DC_Maj`, `E_RA`, and `E_DEC` fields,
         plus only the companion columns the real reader or reviewed
         diagnostics require. Do not reproduce all incidental PyBDSF columns
         by default.
   - [x] Freeze exact field units, dtypes, null/sentinel translation, source
         numbering, ordering, empty-table schema, metadata, and the mapping
         from the internal island/source/component records. Keep dummy sky
         model components and unavailable-RMS compatibility placeholders at
         the Rapthor adapter boundary.
   - [x] Materialise the compact-reference catalogue deterministically and
         verify it against both exact PyBDSF references. On the representative
         reference, report the known released/`master` row and grouping
         divergence by class; do not fail Phase 4 for emission that the
         reviewed Phase 5 multiscale path owns.
   - [x] Extend the independent adapter oracle to compare the catalogue-based
         compact-source diagnostic selections and mask-based retained/rejected
         sky-model decisions on complete, no-deferral fixtures. Reserve actual
         Rapthor orchestration, filtered-model publication, restart, and
         end-to-end `filter_skymodel` claims for Phase 7.
   - [x] Update the schema and compatibility documentation and the living
         Marimo notebook with compact measurements, fitted/deconvolved shapes,
         quality flags, and catalogue output. State the multiscale and
         workflow limitations visibly.

   The adapter publishes exactly the eight directly consumed columns with
   frozen FITS types and units, a zero-row schema, adapter-only unresolved zero
   sentinel, NaN unknown errors, deterministic checksums, atomic validation,
   and conflict-safe retries. Unresolved `Total_flux` uses peak flux; a
   significantly resolved row uses the free fitted-Gaussian integral. After
   applying this declared community-policy view, the same three-row Hebog
   catalogue passes every frozen exact compact gate against released and
   pinned-`master` PyBDSF. Raw reference bytes remain unchanged and a focused
   test records the one unresolved PyBDSF row whose total is about 39% below
   its peak.
   Rapthor's catalogue diagnostic cuts retain the same three rows, and
   pixel-centre mask decisions pass the 99.5% downstream agreement threshold.
   Per-channel flux-normalization columns, orchestration, and filtered-model
   publication remain outside the MFS-only Phase 4 adapter.

8. **Qualify the phase and prepare the release.**

   - [ ] Run analytic/property, contract, integration, dual-reference
         equivalence, acceptance, and held-out qualification lanes in oracle
         order. The serial science must pass before executor conformance, and
         both must pass before PyBDSF or downstream comparisons.
   - [x] Add a permanent same-image dual-reference campaign runner and a
         versioned per-source diagnostic record. Preserve the reference
         version, image seed, truth and candidate identities, match decision,
         extension classification, quality flags, every catastrophic metric,
         and every normalized residual so a failed aggregate can be explained
         without rerunning or tuning against viewed qualification data.

   The maintained runner is invoked independently in the immutable released
   and pinned-`master` PyBDSF environments, with a matching candidate runner
   exercising Hebog's complete bounded serial compact path. The runners write
   mergeable implementation shards, continue past a recorded exception,
   refuse to overwrite evidence, and preserve association-group as well as
   individual-source decisions. Their shared runtime module prevents
   provenance and failure semantics from drifting. The candidate-first
   compiler rejects dataset, seed, contract, or protocol drift. The final
   qualification candidate shard remains deliberately unopened until the
   reviewed paired protocol and final population are frozen; regression
   shards may be used to verify planning assumptions.

   - [x] Draft a strict paired non-inferiority contract and executable power
         calculation for named review. The draft proposed 600 independent
         image realizations, whole-image paired BCa resampling, one-sided 95%
         intervals, all-endpoint intersection-union passage, retained
         failures, and one final look. It explicitly quantified the unstable
         directional point-estimate condition separately from interval-
         exclusion power so review could decide whether to retain it.
   - [x] Verify every planning variance bound on independent
         development/regression data. The maintained 50,000-resample audit
         recomputes every endpoint by whole image and verifies the combined
         paired dispersion directly; this avoids inventing false-candidate
         identities where discordance and intracluster correlation are not
         separately identifiable. The revised draft rounds failed bounds
         above observed dispersion, uses at most half the observed favourable
         effect, changes no scientific margin, and retains 92.2% minimum
         interval-exclusion power at 600 images.
   - [x] Obtain named review of the endpoints, practical margins,
         regression-supported planning inputs, 600-image design,
         multiplicity rule, stopping rule, five-sigma extension policy, and
         stricter no-worse point-estimate condition; then change the protocol
         status to reviewed before freezing any final seeds or truth. Gemma
         Danks, Data Processing Software Engineer, approved the design on
         2026-08-03 and approved removal of the extra sign gate. Point
         estimates remain mandatory report fields; every one-sided upper
         bound, absolute gate, and stronger-Hebog envelope must pass.
   - [x] Freeze the final population without generating or inspecting it.
         `phase-4-final-qualification.json` contains exactly 600 disjoint
         seeds and a distinct WCS, background, invalid region, correlated-
         noise gradient, and rotated layout. The rotation preserves the
         governed blend-to-beam geometry and all 33 truth-group, 32
         individually resolvable, eight point, one clear, and one unresolved-
         blend endpoint populations. Recipe SHA-256 is
         `15f8f607463f2db4cf4c0eb72255a998784e2d83d3a0d7ebc45eb733f6fbc7db`;
         complete campaign dataset SHA-256 is
         `07c736a9bafc79fb298ad1c076fb29b93d88ce9f988f38bba99c94af519d1fcb`.
   - [x] Implement and freeze the final one-look decision evaluator before
         opening the population. Extend the per-source diagnostic record with
         the fitted and deconvolved position-angle differences required by the
         existing absolute gates. The evaluator must recompute every endpoint,
         apply the reviewed paired one-sided 95% SciPy BCa upper limits,
         require every absolute science gate and stronger-Hebog envelope,
         retain failed realizations in the denominator, and emit one immutable
         machine-readable decision. Test the interval, degenerate, missing-
         field, implementation-failure, and gate-failure paths on analytic or
         viewed regression evidence only.
         `phase_four_decision.py` now shares every aggregate statistic with
         the planning audit, uses one vectorized whole-image SciPy BCa call for
         the 20 endpoints, preserves primary and secondary failure policy,
         distinguishes true gates from report-only individual-source tails,
         evaluates the entire-interval uncertainty rules, and emits a strict
         `phase-4-qualification-decision` evidence document. The maintained
         CLI refuses to overwrite an earlier decision. Analytic tests cover
         finite and degenerate intervals, missing position angles, absolute
         gate failures, report-only tails, implementation failures, provenance
         drift, and the complete decision orchestration without opening the
         final population.
   - [x] Obtain named pre-opening review of the finite point-mass bootstrap
         case exposed by the completed evaluator. On the already-viewed,
         post-correction regression campaign, 12 endpoints have finite passing
         BCa upper limits and eight exact-equality endpoints have a degenerate
         bootstrap distribution. SciPy consequently returns `NaN`, and the
         original `indeterminate-fail` rule correctly made those eight
         endpoints indeterminate. This meant a final campaign with exact
         Hebog/PyBDSF equality on any co-primary endpoint could not qualify
         even though it demonstrated no regression. Gemma Danks, Data
         Processing Software Engineer, approved the recommendation on
         2026-08-04 before any final image was generated or inspected. The
         reviewed evaluator now uses `[point, point]` only when the complete
         finite bootstrap distribution is exactly equal to its finite observed
         point estimate, with no tolerance. Every other non-finite or undefined
         result remains indeterminate and fails closed. The amended protocol's
         canonical SHA-256 is
         `eaa4e30a8d24a299d9f139c89aafc3ea60d424d61ac64f2b3d6fe7178a697dd8`.
         Reapplying it to the same viewed 200-image campaign returns 20 passes,
         no failures, and no indeterminate endpoints; the eight exact-equality
         endpoints each have `[0, 0]`. The final population remained unopened
         through this amendment.
   - [x] Record the exact clean Hebog revision, both immutable PyBDSF
         execution environments, dependency inventories, and output paths;
         then open the frozen population exactly once. Infrastructure retries
         may resume only its recorded seeds. Compile without denominator
         deletion and apply the reviewed intersection-union decision once.
         The preflight record fixed Hebog at
         `92f5e4cc233b716987a4f65b75c5f1585d977de1`, released PyBDSF 1.14.1
         at `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`, and pinned PyBDSF
         `master` at `c70103be3ae9ae9908286f144e6ce956acc0ce5c`. All three
         implementations completed all 600 images, and the compiler retained
         all 1,800 realization records. The evaluator initially stopped before
         scoring because its provenance guard omitted the governed base recipe
         from the 600-realization count. TDD commit `b4b3930` corrected only
         that infrastructure guard and exact seed-coverage check; the same
         immutable campaign, contracts, margins, and unused output path were
         then resumed under the predeclared infrastructure-retry rule.

         The resulting one-look decision did not pass. Hebog passed 109 of 114
         absolute gates, but missed catastrophic-outlier fraction (0.5104%
         versus 0.5%), median position (0.02736 versus 0.02 beam), median peak
         flux (0.02942 versus 0.02 fractional error), median fitted axis
         (0.05029 versus 0.05), and median deconvolved axis (0.10340 versus
         0.1). One unmatched Hebog truth source also made the evaluator's
         complete-match uncertainty input unavailable; because the frozen
         vectorized calculation fails closed as one endpoint family, all 20
         primary and all 20 secondary paired endpoints are indeterminate.
         This does not erase the five independent absolute-gate failures.
         Released PyBDSF failed 53 absolute gates and pinned master failed 55
         on the same truth campaign, so Hebog remains substantially stronger
         overall, but it is slightly worse than both references on median
         position and worse on catastrophic fraction. The decision and every
         source shard are retained as viewed evidence; no threshold, result,
         population, or contract may be changed in response.

     The structurally representative planning population is now governed by
     `phase-4-paired-regression.json`: 200 disjoint noise seeds, 33 observable
     groups, 32 individually resolvable sources, eight point sources, one
     clearly resolved source, and one unresolved blend per image. Its distinct
     WCS, noise field, invalid region, and 180-degree mirrored layout preserve
     the governed blend-to-beam geometry. They are viewable regression
     evidence only. The corrected candidate/reference execution is complete:
     released PyBDSF completed all 200 images, while the pre-correction Hebog
     candidate completed 196. On jointly successful images both recovered
     every truth group; Hebog retained lower catastrophic, blend-position,
     and blend-flux errors and stronger clear-extension recovery, but had
     96.75% point specificity against PyBDSF's 100%. The four Hebog failures
     all came from the same five-pixel watershed child of the declared
     unresolved blend. This evidence is diagnostic and planning-only; rerun
     it after the corrective TDD work before verifying empirical power
     assumptions.

     The post-correction refresh is now complete: both implementations
     completed all 200 images and recovered every group. Hebog matches
     PyBDSF's 100% point specificity, retains 100% clear-resolved recall
     against 57.5%, reduces governed catastrophic rows from 1.547% to 0.531%,
     and retains better unresolved-blend position and flux errors. Catalogue
     reliability differs by one unmatched candidate across 6,600 groups
     (99.6828% against 99.6979%); its one-sided 95% paired upper regression
     bound is 0.1808 percentage points, inside the proposed 0.5-point margin.
     Do not tune a new threshold to this near-SNR-5 noise tail. The maintained
     planning-assumption audit and named review were completed before final-
     population freeze.

     The maintained audit is now complete. All 20 revised variance bounds
     pass across 50,000 whole-image resamples and the weakest planned power
     remains 92.2%. Catalogue reliability is worse by only 0.0151 percentage
     points with a 0.1808-point upper bound inside its 0.5-point margin.
     Median unresolved-blend position is worse by 0.00279 beam with a
     0.00682-beam upper bound inside its 0.01-beam margin, while its tail and
     both flux endpoints are materially better. Named review removed the
     strict directional rule because it would reject negligible sampling-tail
     differences despite successful non-inferiority.

   - [ ] Benchmark the complete incremental Phase 4 path at 256, 512, 1,024,
         and 3,000 pixels per side across sparse, normal, dense, blend-heavy,
         and fit-failure workloads. Record setup, bounded reads, moments,
         fitting, transformations, catalogue construction/materialisation,
         task count, source/component count, peak memory, and every repetition.
         Non-claim characterization and profiling may proceed while the
         scientific correction is developed, but the final controlled matrix
         and any speed claim require the corrected science and final
         qualification to pass.
   - [ ] Keep the controlled four-core 3,000-by-3,000 median within 2.0 seconds
         for compact measurement/fitting and use no more than the shared
         2.0-second catalogue/filter-output allocation after the Phase 3
         budget clarification. Compare affected and adjacent tiers with the
         previous reviewed Hebog curve and both PyBDSF references;
         investigate statistically supported regressions and source-density
         superlinearity.
   - [x] Show that worker memory is bounded by admitted coarse batches, graph
         size scales with batches and stages rather than pixels or sources,
         and catalogue reduction depth is logarithmic. Preserve scale-facility
         qualification for Phase 6 while adding executable local invariants
         now.
   - [x] Publish a Phase 4 release-readiness record with implemented scope,
         reviewed scientific decisions, dataset roles, numerical gates,
         reference divergence, performance evidence, portability, known
         limitations, and Phase 5/7 deferrals.

   Local structural evidence is complete: retained image work is bounded by
   admitted coarse-batch pixels, task count is one per batch rather than per
   source, final compact assembly has an explicit record cap, and shard
   reduction has pairwise fan-in and logarithmic depth. The final reviewed
   one-look scientific qualification also failed, so the controlled benchmark
   bullets remain open and are ineligible as Phase 4 release evidence. The
   [Phase 4 release-readiness record](../docs/reference/phase-4-release-readiness.md)
   therefore records a **not ready** decision rather than declaring the phase
   passed.

   **Current recovery and closure order:**

   1. Preserve all three earlier failed Hebog campaigns and the final failed
      one-look campaign as viewed evidence; never promote, rerun, replace, or
      tune against them. Preserve every same-campaign PyBDSF result, exact
      version, environment, and Rapthor configuration alongside the
      reproducible runners.
   2. The paired comparison protocol, power calculation, and one final unseen
      population are now reviewed and frozen. The freeze records the generator
      version, 600 seeds, truth, WCS and beam strata, practical-equivalence
      margins, analysis rule, and stopping rule. Record the exact Hebog and
      PyBDSF execution identities before running each implementation on the
      identical images. Predeclare the desirable
      direction or ideal value for every metric; compare absolute departure
      from the ideal for bias, coverage, and dispersion rather than treating a
      numerically larger value as better. Report Hebog's signed point estimate
      and require the one-sided paired 95% interval to exclude a reviewed
      practically meaningful regression.
      Pinned `master` remains a second anchor wherever it completes; its
      runtime failure is a reference robustness failure, not permission to
      weaken Hebog.

      A machine-readable reviewed contract and executable normal-approximation
      power calculation now live in
      [`phase-4-paired-noninferiority.json`](../config/contracts/phase-4-paired-noninferiority.json)
      and the
      [paired non-inferiority review guide](../docs/reference/phase-4-paired-noninferiority.md).
      The weakest interval-exclusion power at 600 realizations is 92.2%. The
      planning variance assumptions are verified on independent paired
      development/regression evidence. Gemma Danks approved the protocol and
      five-sigma policy on 2026-08-03. The final population was frozen and
      opened exactly once on 2026-08-04 after its decision evaluator and every
      execution identity were recorded. Its immutable one-look decision is a
      failure and cannot be replaced by another population.
   3. Keep every existing absolute community-science gate and every stronger
      Hebog result. In particular, do not trade away Hebog's complete group
      recovery, uncertainty availability, calibrated position and peak-flux
      errors, unresolved-group tails, clear-resolved recall, serial/Dask
      invariance, or bounded execution to improve another score. Establish
      regression envelopes from independent development evidence for these
      strengths. A trade-off requires explicit named review and a
      community-supported scientific justification; metrics may not silently
      compensate for one another.
   4. Use TDD on analytic and independently seeded development/regression
      cases to explain and correct the remaining weakness. First make the
      diagnostic schema expose each catastrophic row and its failed metrics.
      Then add red tests around beam-compatible point sources near the
      extension boundary across SNR, WCS, edge, background, and noise-gradient
      strata. Investigate fit bias, local RMS, covariance, deconvolution, and
      extension significance as one coupled measurement path. Select the
      smallest community-supported correction from those cases only; do not
      choose a threshold or formula from any viewed qualification result.

      The first bounded correction now prevents an otherwise fit-capable
      parent island from producing an unfit child: after prominence merging,
      any watershed basin below the configured seven-pixel fit minimum joins
      its neighbour across the strongest shared saddle. Detection uses the
      same minimum. Analytic tests and all four independently seeded failure
      cases pass without dropping parent pixels. The remaining active science
      correction is point-source extension classification; the independent
      regression showed false resolved decisions at 2.02--3.38 times the
      flux-ratio uncertainty, while the earlier two-sigma ATLAS rule
      deliberately permits a 2.3% one-sided false-extension rate. A
      five-sigma high-confidence decision is now implemented and protected by
      analytic plus independent worst-margin tests. Across all 1,600 point
      and 200 clear regression cases, point values ended below 3.39 sigma and
      clear values began above 17.92 sigma. Named review approved this
      conservative compatibility policy before final-population freeze; the
      refreshed complete paired run confirms that no stronger Hebog error
      envelope regressed. The planning-assumption audit and named review now
      pass; another scientific threshold change is neither required nor
      permitted after final-population freeze.
   5. Require the complete analytic, property, powered regression,
      serial/Dask, exact-fixture, Rapthor-decision, and coverage lanes to pass
      before the reviewed final campaign is opened exactly once. The final
      result must pass all absolute gates, retain the stronger Hebog
      regression envelopes, and be statistically non-inferior against released
      PyBDSF. Signed point estimates are reported but are not separate gates. A
      reference exception is a
      recorded failure, not a missing value silently removed from a
      denominator. The 2026-08-04 final result did not meet this requirement;
      preserve it as the terminal Phase 4 qualification outcome.
   6. After scientific qualification passes, refresh the controlled Phase 4
      performance matrix with matched environments and close the phase only
      when both the scientific and incremental performance exit gates pass.
      Diagnostic timings from qualification runners are not speed evidence.
      Because the final scientific qualification failed, this performance
      matrix is not eligible and Phase 4 cannot be declared passed under the
      reviewed plan. Any further scientific development belongs in a newly
      reviewed follow-on milestone; it must use analytic and independent
      development/regression evidence rather than tuning to this final result.

Exit gate: the named scientific review has approved the measurement,
association, uncertainty, deconvolution, compatibility, and numerical gate
contract; analytic compact cases pass; development, regression, and unseen
qualification results pass every reviewed position, flux, fitted/deconvolved
shape, association, uncertainty-coverage, and outlier gate; and the
redistributable compact catalogue passes both exact PyBDSF comparisons. The
compact no-deferral adapter scenarios satisfy the existing 99.5% downstream
decision gate, while representative multiscale differences remain explicitly
assigned to Phase 5. Serial and executor results are partition- and
retry-invariant, the controlled representative incremental median is within
the 4.0-second combined Phase 4 allocation, and memory, task count, and
catalogue reduction evidence show no full-image, per-source-task, unbounded
fan-in, or quadratic path. Passing Phase 4 establishes experimental compact
catalogue compatibility, not complete PyBDSF equivalence or Rapthor cutover.

The final one-look campaign did not satisfy this exit gate. Its result is a
terminal failed Phase 4 decision, not a population that may be rerun or
rescored. Corrective work therefore belongs to the separately governed Phase
4R milestone below.

### Phase 4R: compact-measurement scientific recovery

**Status:** authorized by Gemma Danks, Data Processing Software Engineer, on
2026-08-04 after diagnosis of the terminal Phase 4 qualification failure. The
final campaign remains immutable, viewed evidence and may be used only to
identify failure modes and report the historical decision. It must not select
an algorithm, threshold, model, seed, margin, or new qualification truth.

The failure is narrower than the aggregate decision first suggested:

- Hebog's 98 gated catastrophic source rows all failed the fitted-axis
  definition; 96 were image-edge sources and 94 were in the SNR-10 stratum.
  Twenty-five carried the undifferentiated `fit-at-bound` flag. A direct
  reproduction of seed `2026110493`, source 16, shows the free fit pinning its
  centroid to the image boundary and inflating the major sigma from the
  injected 2.04 pixels to 6.62 pixels. The other low-SNR edge failures show
  that truncated-profile identifiability is broader than exact bound contact.
- Position error is a separate efficiency weakness. Hebog's median was
  0.02736 beam against 0.02512 for released PyBDSF and 0.02511 for pinned
  `master`; the gap appears across every SNR stratum and is largest for
  low-SNR, unresolved, and edge sources. Position uncertainty bias, coverage,
  and dispersion still pass, so current evidence points to estimator variance
  rather than a WCS convention or systematic astrometric offset.
- Hebog missed the absolute median peak-flux, fitted-axis, and deconvolved-axis
  limits by small amounts while remaining materially more accurate than both
  PyBDSF references on those medians. These are genuine absolute-science
  weaknesses to improve without trading away Hebog's advantage.
- Report-only tails expose additional work that a no-regression objective must
  not hide: Hebog's 95th-percentile integrated-flux error was 1.108 against
  0.541 and 0.536 for the two references, and its fitted-axis tail was 0.2007
  against 0.1833 for released PyBDSF. The largest integrated-flux errors are
  free-shape extrapolations for truncated edge sources.
- The paired evaluator has an independent composability defect. One unmatched
  Hebog source made the uncertainty summary raise, and one shared input builder
  then marked all 20 primary and all 20 secondary endpoints indeterminate.
  That fail-closed result is faithful to the reviewed implementation, but one
  unavailable endpoint must not erase otherwise calculable completeness,
  reliability, shape, group, or catastrophic comparisons.

The production fitter currently gives every eligible compact source the same
seven-parameter amplitude, position, two-axis, angle, and background model.
It obtains the point estimate from RMS-weighted residuals and uses the
correlated-noise model only afterwards in a sandwich covariance. It also
publishes a converged bound-contact fit as scientifically valid. This is a
plausible common mechanism for the low-information position variance and the
edge shape/flux ridge, but it remains a hypothesis to test through the
predeclared ablations below. Condon's Gaussian-fit analysis supports a priori
size constraints for lower amplitude error, and Aegean 2.0 demonstrates
correlated-noise and forced fitting as established radio-source practice.
The ASKAP/EMU and SKA source-finding challenges support keeping completeness,
reliability, position, flux, size, and catastrophic-tail outcomes separate.

1. **Repair the evidence contract before changing the science.**

   - [x] Add a versioned metric registry that declares each scientific and
         robustness metric's population, stratum, unit, desired direction or
         ideal, absolute gate, paired statistic, and practical resolution.
         Include gated and report-only medians and tails for completeness,
         reliability, association, availability, classification, position,
         peak and integrated flux, fitted/deconvolved axes and angles,
         normalized uncertainty calibration, catastrophic rate, and
         implementation completion. No metric may compensate for another.
   - [x] Define "no worse" as direction-aware non-inferiority of the expected
         aggregate metric against both exact PyBDSF references for every
         eligible overall and governed SNR, shape, edge/corner, WCS, and blend
         population. Use zero margin where numerical identity is expected and
         a named, scientifically negligible margin where sampling and metric
         resolution make zero inappropriate. Development point estimates and
         regression point estimates must each remain inside that metric's
         practical margin; qualification additionally requires the one-sided
         paired upper bound inside the same margin. Never claim that every
         individual noisy source must be closer to truth.
   - [x] Refactor paired inputs and decisions endpoint by endpoint, TDD first.
         A missing source contributes to the declared completeness,
         association, and availability denominators. Conditional uncertainty
         calibration uses only its explicitly eligible retained values with a
         visible retained/expected count and minimum sample; it cannot make a
         binary or group endpoint indeterminate. Only the affected endpoint is
         indeterminate when its own minimum information is unavailable.
   - [x] Verify endpoint isolation and missingness with analytic campaign
         fixtures. Continue to verify ideal-value direction,
         dual-reference failure policy, and multiplicity with analytic and
         already-viewed regression fixtures. Do not rescore or replace the
         final Phase 4 decision after repairing the evaluator.

2. **Turn the observed failures into independent red tests.**

   - [x] Record parameter-specific bound contact, distance to every bound,
         visible fitted-model/beam footprint fraction,
         Jacobian/information condition, model identity, fallback reason, and
         retained-pixel geometry. The current single `parameters_at_bound`
         boolean cannot distinguish a harmless periodic-angle representation
         from an unidentifiable centroid or shape.
   - [x] Add noiseless analytic tests for beam-shaped and extended Gaussians
         truncated at each edge and corner, with sub-pixel centers and rotated
         elliptical beams. A centroid/axis ridge pinned to a physical bound
         must not be published as an ordinary valid free-shape result.
   - [x] Add independently seeded development and regression matrices over
         SNR, unresolved/marginal/clear shape, visible fraction, all edge and
         corner topologies, background/RMS gradients, correlated-noise
         orientation and scale, WCS rotation, and nearby-source context. Keep
         seeds disjoint from every viewed qualification population. Freeze
         regression seeds before production fitting changes; select among
         ablations with development data and use the regression set as a
         confirmation boundary rather than another tuning loop.
   - [x] Add efficiency tests against analytic expectations and both PyBDSF
         references for position, peak flux, integrated flux, fitted shape,
         and deconvolution. Include tail and per-source-family reports so a
         good median cannot hide a small catastrophic mode.

3. **Select the smallest community-supported fitting correction from
   ablations.**

   - [x] Implement an internal beam-constrained Gaussian candidate for
         unresolved or low-information sources, while retaining the existing
         free elliptical candidate for demonstrably resolved emission. Select
         between them with a predeclared data-only extension/identifiability
         rule; never use truth class or a viewed-campaign source identity at
         runtime.
   - [x] Treat centroid, scale, amplitude, or background bound contact and an
         ill-conditioned free model as a failed model-selection attempt.
         Retry the constrained model and return explicit unavailability if no
         scientifically valid candidate remains. Do not turn clipping into a
         successful measurement merely to preserve availability.
   - [x] Factorially compare fixed versus fitted local background, owned
         source support versus bounded background context, and the existing
         diagonal point estimator versus a bounded correlated-noise
         generalized least-squares or whitening candidate. Test the
         constrained model first; add whitening complexity only if the broad
         position/peak efficiency gap remains and complete-path profiling
         supports it.
   - [x] Keep the implementation in vectorized NumPy/SciPy, with transformed
         or scaled parameters where they improve conditioning. Retain a
         readable serial oracle, bounded per-region memory, coarse batching,
         deterministic results, and no source-sized Dask task proliferation.
         Do not introduce native code without meeting the existing profile
         and maintenance gates.

   Development selected fixed-zero residual background, owned-region support,
   and bounded correlated-noise GLS for at most 512 retained pixels. Larger
   regions take an explicit diagonal/sandwich fallback. The nested rule uses a
   five-sigma log-area test, BIC scaled consistently with the point estimator,
   and an intensity-weighted-centroid/free-shape retry for bound-contact or
   ill-conditioned free fits. It is an explicit `beam-or-free` campaign
   policy; the public
   default remains the Phase 4 `free-only` serial oracle, so model selection
   cannot silently alter existing scientific products. On the 20-realization
   development matrix this removed all four
   catastrophic rows and improved Hebog's position, peak, integrated-flux,
   fitted-axis, and deconvolved-axis medians and 95th percentiles relative to
   both references. The unresolved-blend median also improved; its 95th
   percentile is worse than both references by 0.0172, inside the predeclared
   0.02 practical margin, and remains an explicit confirmation endpoint.

   Recovery iteration two repaired the generic availability defect and kept
   every one of 40 new development realizations complete. A boundary retry now
   fixes its centroid to the independent intensity-weighted moment rather than
   the already biased truncated beam fit. This restored the sole missed edge
   association without changing the retained GLS component estimator. A
   bounded, mask-aware three-sigma restoring-beam aperture was also added as
   explicit association photometry. Unlike the rejected threshold-only island
   sum, it normalizes against the pixelized beam visible through image,
   validity, and competing-region masks. On the 40 viewable blends it improved
   median/95th-percentile total-flux error from 0.05755/0.14821 to
   0.04788/0.10243, versus 0.04830/0.11301 for both PyBDSF references. The
   retained component-level position, peak, flux, shape, and uncertainty
   metrics remain unchanged apart from the repaired edge row.

   The executable no-compensation evaluator now expands the 35 registered
   metrics into 450 independent dual-reference overall/stratum decisions on
   this matrix. It preserves implementation failures, conditional
   missingness, absolute gates, and stronger-Hebog envelopes without a
   weighted score. Its first complete development pass exposed one SNR-10
   position tail; a separate bounded-context position fit plus an analytic
   one-sided truncated-normal moment correction removed it without changing
   the retained morphology or flux estimator. All 450 viewed development
   comparisons then passed their predeclared practical margins.

   Raw median and tail absolute errors on a stochastic SNR 10/15/25/50 mix
   are noise-distribution statistics, not estimator-bias tests: even an
   efficient unbiased measurement has a non-zero absolute-error median set by
   SNR. Phase 4R therefore reports every position, flux, axis, and angle
   distribution and gates each independently against both PyBDSF references,
   but does not reuse the exact/noiseless 2%/0.02-beam thresholds as absolute
   noisy-campaign gates. The analytic and exact-product suites retain those
   strict thresholds. Absolute noisy-campaign gates remain on completeness,
   reliability, availability, classification, catastrophic rate, unresolved
   groups, and adequately powered normalized-residual calibration.

4. **Qualify the correction on development and regression evidence.**

   - [x] Run the complete analytic, property, serial/Dask, partition, retry,
         exact-product, Rapthor-adapter, and coverage lanes after every
         candidate. Preserve the current completeness, reliability,
         uncertainty calibration, unresolved-group, clear-extension,
         determinism, and bounded-memory envelopes.
   - [ ] Freeze the selected candidate before comparing every registered
         metric against both references overall and by governed stratum. The
         regression qualifies it only when all applicable absolute gates
         pass, every point regression is within its reviewed margin, and no
         material tail or source family remains unexplained. Qualification
         alone applies the paired upper-bound rule. Archive a failed
         regression and return to
         generic analytic/development evidence; do not tune directly to its
         rows, optimize a weighted score, or average away a weak metric.
   - [ ] Profile each scientifically passing candidate on compact sparse,
         normal, dense, edge-heavy, and fit-failure workloads. Reject a
         correction that violates the Phase 4 component budget or creates an
         unapproved adjacent-tier regression; prefer the simplest candidate
         when scientific and performance evidence is indistinguishable.

   Confirmation attempt one is permanently failed. Exact commit `27edde3`
   completed 98 of 100 frozen regression realizations; two retained typed fit
   omissions, while released and pinned-`master` PyBDSF completed all 100.
   The attempt remains under `benchmark-results/phase-4r/` and is not eligible
   for rescoring. Without opening either failed realization's pixels or truth,
   an independent analytic test exposed a generic selection error: failure of
   the smaller beam model could discard an otherwise valid and identifiable
   free fit. Before changing production selection again, recovery iteration
   two froze 40 viewable seeds in `phase-4r-development-2.json` and 100
   confirmation-only seeds in `phase-4r-regression-2.json`; all are disjoint
   from every earlier Phase 4R seed.

   Confirmation attempt two at exact commit `86e7e02` completed all 100
   realizations in Hebog and both references. After restoring the registry's
   predeclared regression point rule, 444 of 450 comparative decisions pass.
   The six failures are the catastrophic-outlier fraction against both
   references overall and in the governed marginal-shape and SNR-15 strata.
   Aggregate diagnostics assign eight of ten Hebog outliers solely to
   deconvolved axes and two solely to fitted axes; no held-out row or image
   was opened. The failed confirmation is archived. A new 200-realization,
   viewable, disjoint tail-development matrix is frozen in
   `phase-4r-development-3.json` before any further production fitting
   change. Use it with analytic tests to remove the rare shape mode without
   weakening the already superior median and 95th-percentile shape results.

   The unchanged candidate then completed all 200 newly frozen development
   realizations. It produced nine catastrophic matches among 2,400 eligible
   rows, versus 19 for released PyBDSF and 30 for pinned `master`, and passed
   all 450 dual-reference point decisions plus the absolute catastrophic
   gate. Across both iteration-two and tail development, Hebog's rate is
   9/2,880, versus 23/2,880 and 36/2,880. This independently demonstrates
   that the failed confirmation was a finite-sample crossing, not a supported
   estimator regression. Low-SNR nonlinear amplitude and correlated-noise
   shape biases are expected in the literature, and an additional correction
   selected after this result would be unreviewed overfitting.

   The approved governance amendment therefore preserves confirmation two as
   failed but permits the unchanged candidate to advance to exactly one
   powered qualification. This is the sole exception to the regression point
   screen: it requires a larger independently frozen viewable population,
   every comparative point decision and applicable absolute point gate to
   pass, a supported expected tail no worse than both references, no candidate
   change after the failed regression, and named review before qualification.
   It does not alter a metric, margin, source row, or the qualification's
   paired upper-bound rule. Future candidates do not inherit the exception.

5. **Govern one new Phase 4R qualification and performance closeout.**

   - [x] After implementation and metric definitions are frozen, obtain named
         scientific review of the model-selection rule, metric registry,
         practical margins, missingness semantics, regression evidence,
         power, and one-look stopping rule. Only then freeze one new Phase 4R
         population with seeds, truth, edge/corner balance, WCS, beam,
         background, and correlated-noise fields disjoint from all earlier
         campaigns.
   - [ ] Record immutable Hebog and dual-PyBDSF environments, execute all
         three implementations on identical images, retain every realization,
         and evaluate each metric independently. A PyBDSF exception is a
         reference robustness failure, not permission for Hebog to fail or
         for a realization to disappear.
   - [ ] Require every absolute gate and every dual-reference direction-aware
         paired decision to pass. Preserve the final Phase 4 failure alongside
         the Phase 4R result; the new milestone does not retroactively turn
         that historical decision into a pass.
   - [ ] Only after scientific passage, run the controlled Phase 4 performance
         matrix and close compact measurement when the 4.0-second combined
         allocation, adjacent-tier, density, memory, and graph-shape gates all
         pass.

   Named review was recorded at `4688081` before the qualification population
   existed. The sole population is now frozen as
   `phase-4r-qualification.json`: 600 new noise seeds, horizontally reflected
   source/association/invalid-region geometry, beam and correlated-noise PA
   57 degrees, a new sky field and WCS scale/rotation, and a new negative
   background. Its manifest and recipe SHA-256 values are
   `93f2d9f876b9b3f58df09ad64796e39ed404980a14f7c4542f0ae2b3120c42e4`
   and `82870d14dbe163c1d1ca79d0b163bc69c406ed2288da3cf489ebdb03989de5fc`.
   No qualification output existed when these identities were recorded.
   The first execution request then failed in preflight before recipe
   iteration because the legacy Phase 4 guard did not recognize a registry
   document. A TDD prerequisite now accepts the registry identifier, requires
   it for Phase 4R qualification, and rejects development-only approval. The
   named review is represented directly by registry status
   `reviewed-qualification`; all 35 metric definitions and margins are
   unchanged. No qualification image or result was opened by the failed
   preflight.

   Qualification attempt one at exact candidate commit `f28bda9` is now a
   failed, immutable availability result. Hebog completed 599 of 600 images;
   seed `2026170473` retained one `IncompleteCompactCatalogueError` after both
   its free and restoring-beam fits reached the image-centroid bound. The
   candidate shard SHA-256 is
   `c9bb55ab4a446f5cf6b25185cfdc8f87cc0e56cdca8f185dae53d0fe9f20f761`.
   No aggregate metric was inspected or scored, no realization may be
   omitted, and this population cannot qualify a corrected candidate.

   Recovery iteration three returns to a generic analytic noisy-edge test and
   two new populations frozen before candidate evaluation:
   `phase-4r-development-4.json` and `phase-4r-regression-3.json`, with 200
   disjoint seeds each. The correction may reuse the existing moment-centred
   retry only when the smaller model converged with finite, conditioned
   amplitude and shape evidence and its sole physical bound contact is a
   centroid coordinate. It must not publish an at-bound model, convert an
   omission into fabricated catalogue data, or change a metric, margin, or
   threshold. The complete analytic and scientific lanes must pass on
   development, followed by exactly one unchanged-candidate regression. If
   that regression passes, a replacement qualification requires a new named
   human review and a newly frozen population with disjoint seeds and field
   geometry. The failed one-look result remains terminal for its candidate;
   a replacement is a separately authorized recovery decision, never a
   rerun or rescore.

Exit gate: every registered absolute gate passes. For every comparable
metric produced by each reference, Hebog is statistically non-inferior for
every separately evaluated overall and governed-stratum population, with no
unresolved development/regression evidence of an expected regression or
unexplained tail. A raw confirmation crossing may be resolved only by the
named, one-candidate exception recorded above and the powered one-look
qualification; it remains an immutable failed result.
Implementation completion is itself a robustness metric and Hebog must
complete every realization. Stronger Hebog envelopes remain intact; and the
new one-look Phase 4R campaign, complete controlled performance matrix,
serial/Dask invariance, bounded-memory, and task-graph checks pass. Only then
may scalability become the next active engineering focus. Phase 5
multiscale science remains required for complete Rapthor functionality, and
all later multiscale work must adopt the same execution contracts.

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
- [ ] Qualify the selected deployment-representative Zarr store's atomic
      conditional creation, concurrency, cold/warm throughput, object count,
      and failure recovery at affected size and executor crossovers; compare
      codec or sharding changes only from recorded complete-path evidence.
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
- [ ] Publish configuration and current output schema documentation.
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
| Detection, labelling, deblending, and durable image products | 3.5 s |
| Compact measurement and fitting | 2.0 s |
| Multiscale processing and merge | 6.0 s |
| Catalogue and filter outputs | 2.0 s |
| Flat-noise analysis, run concurrently | 4.0 s |
| Dask scheduling/transfer on critical path | 2.0 s |

The true-sky critical path should therefore remain near 19 seconds, with the flat-noise branch
hidden by concurrency. The catalogue/output allocation is one second lower
than the original Phase 0 table because Phase 3's reviewed 3.5-second
detection budget includes durable background, RMS, and mask publication. The
complete Rapthor gate, not this component table, decides acceptance.
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
| Background-dominated mask accuracy hides island errors | Gate mask precision, recall, and intersection over union over valid pixels, then report object-level matches, splits, and merges by source class |
| Threshold monotonicity is specified incorrectly | Test detection-seed and island-mask monotonicity separately; allow a shrinking island mask to split connected labels without calling the split a new seed |
| Local labels or completion order leak into public identity | Derive island identity from reconciled global properties and test deliberately permuted local labels, partitions, retries, and completion order |
| Bright-candidate discovery adds another full image pass | Reuse cached coarse statistics, compare piggybacked bounded summaries with a separate bounded scan, and retain added coupling only from complete-stage evidence |
| Deblended regions are mistaken for measured sources | Keep Phase 3 detection records distinct from Phase 4 islands, fitted Gaussian components, and grouped sources; test schema boundaries |
| Deblended bounding boxes are mistaken for exact region membership | Keep watershed labels worker-local through measurement or persist reviewed bounded ownership; never infer owned pixels from a summary box |
| Selective fitting biases the catalogue | Establish a fit-all reference first and admit a moment-only path only from frozen science and downstream-decision evidence |
| Correlated image noise makes formal fit errors overconfident | Calibrate uncertainty candidates with injected Monte Carlo truth by SNR, shape, blend, and edge class; report unavailable errors instead of zeros |
| Beam/WCS conventions rotate or distort fitted shapes | Transform local covariance through Astropy WCS, freeze position-angle and pixel-origin conventions, and test rotated and unequal-scale axes |
| Marginal beam deconvolution invents physical source size | Represent unresolved results explicitly, test near-singular covariance cases, and confine compatibility sentinels to the adapter |
| Source grouping differs while aggregate flux appears correct | Gate island, Gaussian-component, source, and downstream association separately on analytic blends and both compatibility references |
| Catalogue fan-in exhausts the scheduler or one worker | Write bounded ordered shards, merge metadata hierarchically, and stream final FITS rows without per-source tasks or unbounded gathers |
| A watershed or island is too large for one worker | Batch bounded compact regions, preserve explicit undecomposed state for extended work, and require the Phase 5/6 partitioned path before claiming large-island support |
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

## 14. Open decisions entering Phase 4

The 2026-08-02 scientific review resolved the glossary authority, Phase 3
mask/object margins, strict detection comparison, beam-aware six-pixel floor,
and SciPy compact-deblending questions. Their approved disposition is recorded
in the [Phase 3 scientific review record](../docs/reference/phase-3-review-record.md).
Phase 4 resolves its first four decisions through the ordered evidence gates
above rather than making a dependency or optimization choice in advance. The
remaining decisions are:

- Does SciPy `least_squares` or Astropy modelling provide the simplest robust
  compact fit after the analytic and representative comparison? A compiled
  kernel is not eligible unless the existing native-code profile gates later
  pass.
- Which reviewed uncertainty calculation is sufficiently calibrated for
  position and flux, and which shape uncertainties must remain explicitly
  unavailable?
- Does the compact association evidence support one source per deblended
  region, or require a separate multi-Gaussian grouping policy within an
  island?
- Can a moment-only selective path meet fit-all science and downstream gates,
  and if so what frozen eligibility rule prevents population bias?
- Is an undecimated wavelet transform required, or does a beam-aware matched-filter bank satisfy the
  extended-source gate more efficiently?
- Which worker-local cache policy best complements the Zarr intermediate store:
  bounded in-memory arrays, Dask worker data, or store-backed rereads?
- Which Zarr store, codec, chunk geometry, and concurrency settings meet the
  100,000-by-100,000 I/O, restart, provenance, and final FITS-materialisation
  gates on Rapthor's deployment?
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
