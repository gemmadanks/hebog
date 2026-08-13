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

Community usefulness is an independent product requirement. Hebog's general
continuum mode must use transparent, literature-grounded methods, publish the
intermediate provenance needed to audit a result, and qualify compact and
extended populations beyond the initial Rapthor workload. A workflow adapter
may select a narrower qualified profile, but it may not silently redefine the
scientific default or present task-specific equivalence as general source-
finder equivalence.

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

Rapthor profiling previously reduced an aggregate `filter_skymodel` measurement
from 89.54 to 69.881 seconds by reducing PyBDSF's requested cores from 30 to
15. The resulting 34.94-second planning target is historical context. Phase 0
subsequently captured the matched, versioned released and `master` baselines;
the governed ratios and confidence rules in Section 1 are the release gates.

These observations indicate that a new array-oriented implementation can meet the target by
avoiding repeated statistics, whole-image copies, recursively repeated source-finding pipelines,
and fork-based worker startup.

### 2.1 Community-practice evidence for the multiscale design

A 2026-08-08 review of established continuum finders and survey practice found
no universal best extended-source algorithm, but did identify a defensible
common envelope:

- PyBDSF applies an optional B3-spline à trous decomposition to the residual
  after ordinary Gaussian fitting; it does not treat a raw wavelet coefficient
  as the final source photometry ([PyBDSF documentation](https://pybdsf.readthedocs.io/en/latest/process_image.html)).
- Aegean combines thresholded islands, curvature-informed component counts,
  and constrained Gaussian fits, providing a strong precedent for compact and
  blended sources rather than arbitrary diffuse morphology
  ([Hancock et al. 2012](https://academic.oup.com/mnras/article/422/2/1812/1041871)).
- ASKAP Selavy combines local-noise thresholds, seed-and-grow islands,
  optional à trous reconstruction, and overlapped distributed subimages
  ([ASKAPsoft documentation](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current/analysis/selavy.html)).
- ProFound and CAESAR demonstrate the value of morphology-independent
  segmentation and residual processing for irregular diffuse emission, while
  also exposing noise-growth and component-representation trade-offs
  ([Hale et al. 2019](https://academic.oup.com/mnras/article/487/3/3971/5511783);
  [Riggi et al. 2021](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/caesar-source-finder-recent-developments-and-testing/DC9883C05E033D27CC05EE86AFC4B17F)).
- The Hydra comparison found the largest finder-to-finder differences on real
  diffuse emission and no representation that dominated island segmentation,
  Gaussian component modelling, and noise rejection simultaneously
  ([Boyce et al. 2023](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/hydra-ii-characterisation-of-aegean-caesar-profound-pybdsf-and-selavy-source-finders/DC245D86E75644800D682F7E0FC3D7D9)).

The resulting corrective direction is therefore a transparent hybrid of
established operations: retain the qualified compact branch, detect extended
emission through an optimized residual B3-spline à trous reconstruction, grow
and reconcile morphology-independent support, and measure final properties on
the original background-subtracted image. This is a development design to be
frozen and tested in Phase 5 Step 2C, not an algorithm-selection result.

The external comparison roles are deliberately asymmetric. PyBDSF with its
residual à trous path is the binding full-continuum comparator because it
detects and fits residual emission across wavelet scales. Aegean is binding for
compact, blended, and Gaussian-like catalogue populations, where its
curvature-informed component model and covariance-aware fits are directly
applicable. Aegean island measurements remain useful diagnostics for extended
objects, but its compact-source design and cautioned extended-island flux
correction make it an inappropriate binding oracle for diffuse reconstruction,
filament or shell masks, or multiscale provenance. Neither finder replaces
analytic or injected truth.

## 3. Scope

### In scope

- FITS image and metadata input used by Rapthor.
- Background mean and RMS estimation, including an adaptive bright-source mode.
- Seed and island thresholds compatible with Rapthor's PyBDSF settings.
- Connected islands, deblending, compact-source measurements, and Gaussian fitting where needed.
- A general continuum profile with multiscale detection and measurement for
  extended sources, plus an explicit compact profile for qualified workflows
  that do not require extended emission.
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

Scientific configuration exposes explicit `compact` and `continuum` profiles.
The qualified `continuum` profile is the intended general-community default
and adds residual multiscale processing to the unchanged compact branch. A
workflow may select `compact` only through explicit configuration and governed
evidence for its downstream decisions. Every product records the profile,
scale sequence, thresholds, beam, background/RMS method, implementation
version, and material omission or truncation flags. No adapter may label a
compact-only result as extended-source complete.

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

Phase 0 froze every field and side product used by the pinned LSMTool and
Rapthor references. Later phases must preserve or deliberately amend, review,
and version at least:

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

Detection representations and photometric estimators are separate. Filter or
wavelet responses may establish significant support, but final extended-source
flux, centroid, shape, and uncertainty gates are evaluated from reconstructed
support on the original background-subtracted pixels. Representation-level
response remains an auditable diagnostic and analytic calibration target; it
must not be substituted silently for catalogue photometry.

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
10. Public real or challenge cut-outs spanning at least two of LOFAR, ASKAP,
    MeerKAT, and SKA SDC1, with redistributable provenance where possible and
    isolated comparison runs for PyBDSF, Aegean, Selavy, ProFound, or CAESAR as
    appropriate to the compact or extended population. These tools are
    validation comparators, not runtime dependencies or scientific truth.

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
and strong- and weak-scaling efficiency. Phase 0 froze the reviewed runtime,
memory, scheduler-overhead, and scaling-efficiency gates for the 100,000 by
100,000 qualification case; Phase 6/8 must demonstrate them on the approved
facility.

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

### 8.4 Native acceleration policy

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

### Completed milestones: Phases 0--4

Detailed chronology, experiment outcomes, immutable evidence identities, and
superseded candidate decisions live in [`LOG.md`](../LOG.md) and the linked
readiness and review records. These summaries retain only durable outputs,
residual obligations, and constraints that Phase 5 must preserve.

| Phase | Closed | Durable outcome | Evidence and remaining boundary |
| --- | --- | --- | --- |
| 0: baselines and contracts | 2026-08-02 | Froze the Rapthor contract, released and pinned-`master` PyBDSF references, comparison schemas, governed datasets, test lanes, and scheduler/storage architecture decisions. | [Phase 0 review](../docs/reference/phase-0-review-record.md) and [baseline results](../docs/reference/phase-0-baseline-results.md). Facility review and controlled 1/10/50/100/200-node evidence remain Phase 6/8 gates. |
| 1: FITS, beam, WCS, and models | 2026-08-01 | Established bounded FITS/Zarr I/O, deterministic partition ownership, restartable products, internal schemas, and the pipeline-neutral image boundary. | [Phase 1 readiness](../docs/reference/phase-1-release-readiness.md). Deployment-store concurrency and atomicity remain Phase 6/8 work. |
| 2: background and RMS | 2026-08-01 | Delivered the vectorised serial oracle, bounded window batching, adaptive fine regions, partition-invariant interpolation, and serial/executor parity. | [Phase 2 readiness](../docs/reference/phase-2-release-readiness.md). The controlled 3,000-square four-core true-sky and flat-noise medians were 2.471 and 2.527 seconds. |
| 3: detection and compact deblending | 2026-08-02 | Delivered deterministic thresholding, island reconciliation, compact watershed deblending, durable masks, bounded batches, and explicit extended-island deferrals. | [Phase 3 readiness](../docs/reference/phase-3-release-readiness.md) and [scientific review](../docs/reference/phase-3-review-record.md). Multiscale reference objects and oversized islands are Phase 5 inputs, never accepted compact results. |
| 4: compact measurement and catalogues | 2026-08-05 | Delivered exact-membership moments and Gaussian fits, calibrated compact positions and fluxes, deterministic catalogue shards, Rapthor-compatible catalogue output, and passing compact scientific and component-performance gates. | [Phase 4 readiness](../docs/reference/phase-4-release-readiness.md) and [scientific review](../docs/reference/phase-4-review-record.md). Real-residual, independent radio-astronomy, complete Rapthor timing, and production-scale Dask evidence remain cutover gates. |

The Phase 4U candidate is the compact single-scale regression baseline for all
later work. Its fresh 800-image qualification passed all 77 binding absolute
gates, all 20 paired endpoints against each PyBDSF reference, and all five
stronger-Hebog envelopes. The corrected 20-cell incremental performance
matrix also passed; at 3,000 by 3,000 pixels, measurement/fitting medians were
0.178--0.758 seconds and catalogue-output medians were 0.037--0.041 seconds,
each below its 2.0-second budget. Exact evidence hashes and reproduction
details remain in the records above and in `LOG.md`.

Earlier Phase 4, 4R, 4S, and 4T one-look decisions remain terminal historical
failures. Phase 4U is a separately governed candidate, not a rescore of those
campaigns. This distinction must remain visible in evidence and review
records, but their trial-by-trial history is not active plan content.

Every later phase must preserve these completed contracts:

- PyBDSF is a compatibility comparator, while analytic and injected truth
  govern scientific correctness.
- The Phase 4U compact population and its absolute, paired, catastrophic-tail,
  classification, uncertainty, and unresolved-blend gates remain regression
  requirements.
- Extended or over-limit work remains explicit and fail-closed until Phase 5
  produces a scientifically complete result; it must not disappear, become an
  empty catalogue, or be relabelled as successful compact work.
- One-tile and many-tile results use the same scientific semantics, immutable
  global coordinates, deterministic ownership, and scheduler-safe records.
- Zarr remains the sole intermediate plane backend; worker memory remains
  bounded by admitted cores, halos, stage workspaces, and small summaries.
- Complete Rapthor speedup, real-residual evidence, deployment-store
  qualification, independent human scientific review, and 100-to-200-plus-node
  scale evidence remain later gates. Completed component timings do not imply
  those outcomes.

### Phase 5: multiscale and extended emission

**Status:** Steps 1--2C-HR are complete. Earlier representations and astrometry
corrections were rejected; the reviewed compact/irregular position split then
passed all 60 endpoints on fresh development data and the single 400-image
confirmation. Its limiting shell/tile-corner radial-p95 bound was 0.4883 beam
against the 0.50-beam gate, and that population is closed. Step 2C-P freezes
600 continuum and 800 compact/blend images, exact PyBDSF release/master and
Aegean runtimes, truth-first matching, and 0.9082 conservative joint power.
The matcher, common-input materializer, adapters, isolated runners,
complete-population launcher, raw-product compiler, and exact endpoint registry
are ready. Gemma Danks approved the 512-pixel controlled-diagnostic limitation,
four PyBDSF cores, runtime identities, and final one-look decision on
2026-08-11. A no-write preflight expanded exactly 1,400 inputs and 7,000 runs
against those identities and left both public and private campaign paths
absent. Those four local images were subsequently lost before execution.
The external-reference reconstructions are smoke-tested and protocol-bound;
Aegean was rebuilt again to retain the originally frozen Astropy/SciPy stack.
The final Hebog image has now been rebuilt from the committed fail-closed
validator source and bound into the execution decision. Gemma Danks renewed
named approval for the four exact identities and unchanged operational limits
on 2026-08-11. The renewed no-write preflight passed request `31a56c50...`
over exactly 1,400 inputs and 7,000 runs while leaving both public and private
campaign paths absent. The sealed campaign subsequently completed all 8,400
isolated invocations, verified every input and result, and atomically published
terminal raw evidence at manifest `b9996100...`. The first frozen compiler
attempt failed before writing analysis because its analysis-only Phase 4R role
copy contained a plain string rather than the required enum. The committed
type-only correction then compiled analysis `bdc59fdc...`; the unchanged
evaluator sealed decision `73c7e2eb...` as `fail`/`select-neither`. All 143
Continuum endpoints were indeterminate, compact comparison also failed, and
only 1,492 of 5,000 binding runs succeeded. Step 3, optimization, and
qualification therefore remain closed while Step 2C-PF corrects product and
reference interoperability prospectively. Step 2C-PF has reproduced all four
runner failure classes, corrected them with focused regressions, and passed a
12-cell diagnostic execution-validity matrix with no unexpected failures.
The matrix used only two already-opened failed realizations: the compact/blend
case and one continuum case containing diffuse, shell, filament, edge,
invalid-pixel, and varying-noise strata. It did not inspect or rescore science
metrics. The checksum-bound terminal compiler remains byte-identical; its
successor science kernel now admits native mask-only detections without
inventing catalogue rows. It preserves the terminal metric result whenever
every support is catalogued, keeps label-only supports in mask and topology
metrics, and keeps their catalogue completeness, reliability, flux, and
position dispositions explicit. It passed both pinned PyBDSF product
boundaries on one already-opened diagnostic realization. A new 1,400-image
successor population is now frozen across the same reviewed geometry and
endpoint design with 1,400 seeds disjoint from all 9,053 historical seeds.
Its independently recomputed conservative joint-power lower bound is
0.908176 against the unchanged 0.90 gate. The population freeze binds the
candidate source, corrected runners, successor science kernel, manifest
hashes, and exact intended runtime inventories while leaving the candidate
image unbuilt and execution unauthorized. A checksum-bound
absolute-first decision kernel now distinguishes compact 0.10/0.25-beam
astrometry from irregular-segment 0.10-beam signed-axis bias and 0.50-beam
one-sided radial-p95 upper confidence bound; irregular radial median remains
report-only. Its
synthetic pass, absolute-failure, unavailable-reference, excess-variance, and
incomplete-population cases pass. The compiler verifies the approved request,
runtime and artifact identities before reading science, then expands 143
binding and 15 report-only continuum endpoints, 225 Phase 4R compact endpoints
per PyBDSF reference, and the exact 143 applicable Aegean endpoints. Synthetic
tests and a closed-development astrometry cross-check pass; the latter
reproduced all 105 checked estimates, confidence bounds, and medians exactly.
The one-look is closed with a failed scientific decision. Step 3,
candidate-specific optimization, and qualification remain blocked; no
external non-inferiority, multiscale equivalence, or complete runtime claim is
approved. The campaign may inform failure diagnosis but may not be rescored,
tuned, or reused as confirmation.

**Goal:** provide a trusted general continuum profile that recovers and
measures extended and cross-scale emission without recursively rerunning the
complete compact pipeline, while separately determining whether Rapthor needs
that profile for sky-model filtering. The continuum result must combine
compact and multiscale detections into one deterministic catalogue and
source-filtering product and remain suitable for the bounded tiled execution
developed fully in Phase 6. Rapthor may use the compact profile only if the
governed downstream decision probe passes; that outcome does not reduce the
general continuum scope.

Phase 5 owns scale-space science, cross-scale ownership, extended-island
completion, compact/multiscale association, and the scheduler-independent
bounded algorithm. Phase 6 owns production executor planning,
deployment-store qualification, hierarchical Dask graphs, real worker-loss
and spill behaviour, and facility-scale execution.

#### Phase 5 execution order

1. **Freeze the Phase 5 contract before algorithm tuning.**

   - [x] Inventory multiscale objects and deferred-island paths exposed by the
         Phase 3 representative comparison, Phase 4 compact campaigns, and
         Rapthor's three-scale PyBDSF configuration. Record which catalogue,
         RMS, mask, and downstream filter decisions each can affect.
   - [x] Define scale in restoring-beam units and freeze the configured scale
         sequence, filter normalization, threshold meaning, valid-pixel
         handling, edge policy, maximum supported scale, and failure
         semantics. Keep workflow defaults in the Rapthor adapter.
   - [x] Extend the versioned scientific contract and internal schemas for
         scale detections, cross-scale associations, extended measurements,
         explicit omissions, and the combined catalogue. Do not expose
         worker-local arrays or scheduler objects.
   - [x] Add Phase 5 development and regression manifests covering diffuse,
         filamentary, shell-like or curved, mixed compact/extended,
         overlapping-scale, edge, invalid-pixel, varying-noise, and
         artefact-dominated cases. Include sources crossing tile edges and
         corners and cases above the compact-deblend limits.
   - [x] Freeze one untouched qualification manifest before implementation
         tuning. Record generator versions, seeds, angular scales, injected
         truth, morphology strata, and intended statistical power.
   - [x] Freeze reviewed absolute and paired gates for scale-stratified
         completeness, reliability, integrated-flux error, astrometry,
         duplicate rate, mask/island topology, and Rapthor retained/rejected
         decisions. Predeclare practical margins and interval methods rather
         than deriving them from viewed qualification results.
   - [x] Obtain named scientific review of the contract, datasets, metrics,
         and margins before opening qualification. Independent
         radio-astronomy review remains mandatory before production cutover
         even when project-owner review permits development.

2. **Complete the initial analytic and bounded-cost candidate screen.**

   - [x] Write failing analytic tests for the scale response of isolated
         Gaussian sources, constant and affine backgrounds, masked/NaN
         regions, image edges, and separated compact sources.
   - [x] Establish a readable one-tile serial oracle that reuses Phase 2
         background/RMS products and evaluates each configured scale without
         rerunning ingestion, background estimation, or compact detection.
   - [x] Compare an undecimated wavelet construction with a beam-aware matched
         filter bank on the same development fixtures, recording convolution,
         memory, and complete-stage measurements. Prefer the simpler
         maintained NumPy/SciPy design satisfying the frozen science contract.
   - [x] Record filter support, truncation error, normalization, correlated
         noise response, dtype, required halo, temporary planes, and
         convolution reuse for both candidates and the provisional initial
         choice. Create or amend an ADR only if the final decision changes an
         architecture boundary or introduces a durable dependency or storage
         policy.
   - [x] Keep float64 unless lower precision passes the complete governed
         scientific suite; introduce native code only if the existing profile
         and end-to-end decision gates are met.

2B. **Select the representation through a paired scientific comparison.**

   - [x] Before inspecting new candidate results, freeze a non-qualification
         paired matrix spanning all three scales; support fractions from 0.5
         to 1.0; mask and image-edge offsets, orientations, corners, and
         irregular holes; compact, diffuse, filamentary, shell, and mixed
         morphologies; nearby sources; varying RMS; correlated noise; and a
         governed SNR range. Use only the development and regression roles;
         keep the qualification population unopened.
   - [x] Evaluate both existing float64 candidates from identical prepared
         image, validity, background, and RMS products. Use candidate-neutral
         response and minimal threshold evaluation so no downstream
         matched-filter design choice prejudges the comparison.
   - [x] Record paired centre- and integrated-flux bias, median and
         95th-percentile error, calibrated response SNR, noise calibration,
         completeness, reliability, position error, support availability,
         negative-lobe or fragmentation behaviour, and mask topology in every
         applicable governed stratum.
   - [x] Freeze practical paired margins and confidence rules before running
         the matrix. Require the selected representation to pass every
         absolute gate and to be scientifically non-inferior in every
         governed stratum; an aggregate result may not compensate for a
         masked, edge, morphology, scale, or SNR failure. An inconclusive
         comparison selects neither candidate and requires a newly frozen
         development design rather than weaker or post-hoc margins.
   - [x] Prefer lower convolution, memory, halo, and latency cost only after
         the paired scientific comparison finds no practically material
         advantage. If one candidate has a repeatable material scientific
         advantage, select it regardless of its current cost and optimize it
         only after selection.
   - [x] Complete a named governed-evidence review and update the selection
         status, evidence identity, decision record, plan, and `LOG.md`. The
         review recorded `select-neither`, `qualification_opened=false`, and
         `step_three_authorized=false`; independent human scientific review
         remains required before production cutover.

2C. **Freeze and re-evaluate the corrective continuum design.**

   - [x] Review established source finders and major survey practice. Record
         the residual à trous, curvature/Gaussian, seed-and-grow,
         segmentation, and distributed-overlap precedents and keep the final
         design explainable without hidden learned models or proprietary
         training data.
   - [x] Diagnose the failed analytic response, response-SNR, astrometry,
         fragmentation, and mask-topology strata without opening
         qualification. Separate evaluator defects from representation
         limitations with exact truth and development-only probes.
   - [x] Freeze a corrective serial design that subtracts or excludes accepted
         compact emission, computes a normalized B3-spline à trous transform
         of the residual, calibrates correlated noise and valid support per
         scale, reconstructs significant adjacent-scale support, grows that
         support on the original residual, and measures final extended
         properties on the original background-subtracted pixels.
   - [x] Predeclare how the existing response endpoint applies to reconstructed
         signal before viewing new results. Preserve the numerical absolute
         gates, paired margins, source population, inputs, thresholds, and
         fail-closed semantics; do not weaken a gate because detection,
         reconstruction, masking, and photometry are now explicit stages.
   - [x] Freeze a bounded implementation using separable sparse B3-spline
         convolutions, reused adjacent smoothings, scale-specific finite
         halos, bounded normalized-convolution support, and no durable full
         response bank. Profile first before authorizing Numba, native code,
         lower precision, or a new dependency.
   - [x] Keep the beam-aware matched filter as a governed comparator and
         possible known-template compact aid, not the default extended-source
         representation. A future workflow-specific matched-filter profile
         requires its own explicit scientific and downstream qualification.
   - [x] Re-run the full Step 2B analytic and 100-image regression protocol on
         final reconstructed masks and original-pixel measurements. Authorize
         Step 3 only if the corrective candidate passes every applicable
         absolute and paired stratum gate. The reviewed outcome was
         `reject-corrective`: 23 absolute and eight paired failures, so Step 3
         remains unauthorized and qualification unopened.

2C-R. **Correct the failed final-output stages without changing representation.**

   - [x] Freeze, before another result run, a lower-variance original-pixel
         astrometry estimator, cross-scale association rule for shell and
         tile-boundary fragments, artifact-aware measurement disposition, and
         calibrated false-positive control. Preserve B3 detection provenance,
         original-pixel measurement, the populations, and every numerical
         gate and margin.
   - [x] Add exact and development regression tests for the four observed
         failure domains. Distinguish estimator variance from bias and report
         typed truncation or artifact disposition rather than substituting a
         truth coordinate or weakening the astrometry and flux endpoints.
   - [x] Re-run the complete 84-case analytic and 100-image regression review
         under a newly hashed pre-results contract. Authorize Step 3 only when
         the residual B3 candidate passes every absolute and paired stratum;
         otherwise revise the plan again and keep qualification closed. The
         reviewed decision is `reject-corrective-r`: B3 failed nine absolute
         astrometry strata and no paired strata, so Step 3, optimization, and
         qualification remain closed.

2C-A. **Resolve the remaining astrometry variance independently.**

   - [x] Freeze a new seed-disjoint confirmation population before changing
         the estimator. The viewed Step 2C-R regression remains diagnostic and
         must not be reused to tune or confirm the replacement; qualification
         remains unopened.
   - [x] Derive and freeze a noise-aware original-pixel position estimator
         against analytic truth and the development role only. Preserve the
         observable flux-centroid target, typed truncation, B3 provenance,
         masks, photometry, association, false-positive control, all numerical
         gates, and all paired margins. Prefer a standard generalized
         least-squares or model-assisted estimator with an explicit
         model-mismatch fallback over another morphology-specific heuristic.
   - [x] Test bias, centred variance, correlated-noise calibration, masked and
         edge support, shells, filaments, blends, and topology aggregation.
         Record estimator availability and uncertainty; never substitute a
         truth coordinate or drop a difficult astronomical morphology.
   - [x] Re-run all 84 analytic cases and the new 100-image confirmation under
         a hashed pre-results contract. Authorize Step 3 only if B3 passes
         every unchanged absolute and paired stratum; otherwise obtain human
         scientific review before revising the endpoint or estimator again.
         The one-look decision is `reject-corrective-a`: B3 failed five
         absolute position-error strata and no paired strata. The confirmation
         is closed to tuning, rescoring, or reuse; qualification remains
         unopened.

2C-H. **Review the residual astrometry question with a human scientist.**

   - [x] Complete an AI-conducted technical pre-review of the endpoint
         implementation, closed evidence, estimator, uncertainty model, and
         primary radio-astronomy precedents. It recommends prospective
         revision, not approval: use direct group-level median and p95
         catalogue endpoints with whole-image cluster resampling, restore the
         omitted median gate, retain a direct original-pixel extended-source
         centroid baseline, require explicit model-adequacy evidence, and
         validate a two-dimensional correlated-noise uncertainty model. The
         durable findings are in the
         [Step 2C-H pre-review](../docs/reference/phase-5-astrometry-pre-review.md).
   - [x] Review whether the frozen per-image/group-tail endpoint represents
         catalogue astrometry appropriately, the curved-filament variance,
         and the estimator's correlated-noise uncertainty undercoverage.
         Treat raw population percentiles as diagnostics, not replacement
         gates on the viewed confirmation. Explicitly decide the position
         meaning, direct-versus-model-assisted estimator policy, direct
         group-level median and tail estimands, cluster-resampling and
         confidence rule, uncertainty coverage, external-finder mappings,
         and fresh morphology/population design. Gemma Danks approved all six
         pre-review recommendations on 2026-08-09.
   - [x] Record a governed decision before further astrometry work. The
         machine-validated
         `config/contracts/phase-5-astrometry-human-decision.json` authorizes
         a prospective successor protocol and development execution only. Any new
         estimator or endpoint protocol requires a newly frozen confirmation
         population and may not tune, rescore, or reconfirm on the closed
         2C-A population. Keep Step 3, optimization, and qualification closed
         until a pre-results design passes every required absolute gate and
         the external comparison in Step 2C-P.
   - [x] Freeze the prospective successor protocol before estimator changes.
         `config/contracts/phase-5-astrometry-revision-review.json` binds
         direct group-level median and p95 endpoints, whole-image cluster
         bootstrap inference, a direct-pixel baseline, a covariance-gated
         model-assisted candidate, two-dimensional correlated-noise
         covariance and coverage, and development-only selection. Its fresh
         40-image development and sealed 400-image confirmation populations
         vary curve geometry, orientation, knot contrast, source width, beam,
         WCS, scale, edge and invalid-pixel conditions. Confirmation remains
         unauthorized until one estimator is frozen from development-only
         evidence.
   - [x] Implement the direct observable-pixel centroid, covariance-gated
         Gaussian-assisted comparator, full rotated-beam pixel covariance,
         local-WCS sky covariance, direct group-level median and p95 endpoints,
         whole-image cluster bootstrap, and morphology/support-stratified
         Mahalanobis coverage. On 40 fresh images and 240 unique group
         observations per candidate, the direct estimator produced an overall
         median/p95 of 0.0974/0.2730 beam and failed 17 endpoint and 17 coverage
         strata. The model-assisted candidate produced 0.0860/0.3068 beam and
         failed 15 endpoint and 11 coverage strata. Neither passed every
         absolute gate, and the model did not provide the required 0.02-beam
         p95 improvement. The reviewed decision is
         `reject-astrometry-candidates`; the 400-image confirmation remains
         sealed and another estimator revision requires renewed human
         scientific review.

2C-HR. **Separate compact astrometry from irregular-source location.**

   - [x] Audit the rejected direct and Gaussian-assisted candidates without
         reopening confirmation. Their offsets have no material common bias;
         failures concentrate in curved, shell, scale-2/4, edge, and tile
         strata. Even an oracle 3-sigma truth support does not make a
         threshold-independent full-emission centroid stable in every
         irregular-morphology stratum. Record the scientific interpretation
         and source-finder precedents in the renewed technical review.
   - [x] Freeze a new seed- and geometry-disjoint development and confirmation
         design before changing the estimator. The development population
         must vary every governed astronomical morphology, beam, WCS,
         scale, edge, invalid-pixel, tile-boundary, and component-contrast
         condition. Do not use the viewed Step 2C-H development population,
         the closed 2C-A confirmation, or the sealed Step 2C-H confirmation
         for selection.
   - [x] Preserve the Phase 4 compact/component position definition and its
         0.10-beam median and 0.25-beam p95 gates. For irregular extended
         objects, define the catalogue coordinate as the original-pixel
         flux-weighted centroid of the accepted detection segment, report the
         brightest-pixel coordinate separately, and state explicitly that
         neither coordinate is a host-galaxy position. Compare the segment
         centroid with the matched noiseless 3-sigma truth segment, not
         unobservable flux below the catalogue boundary.
   - [x] Implement one transparent, morphology-neutral segment estimator and
         typed position semantics before another candidate comparison. It
         must use the accepted B3-associated original-pixel segment without
         dilation or truth information, retain deterministic peak tie-breaking,
         and report position uncertainty as unavailable until support-selection
         uncertainty has a validated production approximation. Do not publish
         the rejected global covariance inflation as a calibrated error.
   - [x] On fresh development data, require 100% estimator availability, a
         one-sided 95% confidence bound no larger than 0.10 beam for each
         signed-axis population bias, and a one-sided 95% confidence bound no
         larger than 0.50 beam for radial p95 repeatability in every governed
         stratum. The half-beam tail is an irregular-segment repeatability
         requirement, not a relaxation or replacement of compact astrometry.
         Report median radial error and the former full-observable-domain
         target as diagnostics only. The frozen 80-image run passed all 60
         endpoints: availability was 1.0; overall x/y bias bounds were
         0.0105/0.0147 beam; and the overall radial-p95 bound was 0.3183 beam.
         The limiting shell/tile-corner cohort passed at 0.4887 beam, so the
         larger sealed confirmation remains essential.
   - [x] Record the development decision and obtain named human scientific
         review before authorizing the one-look confirmation or Step 2C-P.
         Map PyBDSF source moments only where grouping and source-model
         semantics align; compare Aegean fitted centres only for compact or
         Gaussian-component scope. Use Selavy and ProFound segment centroids
         as semantic precedents, not additional ground truth. The technical
         decision is recorded as `retain-candidate-for-human-review`. Gemma
         Danks approved the reviewed findings and confirmation-only execution
         on 2026-08-09. The one-look 400-image confirmation passed all 60
         endpoints with an overall radial-p95 bound of 0.3103 beam and a
         limiting shell/tile-corner bound of 0.4883 beam. Confirmation is now
         closed. The Step 2C-P protocol is now frozen; execution and every
         later gate remain false until its implementations are hash-bound and
         separately reviewed.

2C-P. **Establish external source-finder non-inferiority before Step 3.**

   - [x] Freeze a fresh seed-disjoint comparison population, power audit,
         finder-neutral matcher, and hashed pre-results protocol before
         generating any new output. Bind the exact Hebog candidate, released
         PyBDSF used by Rapthor, pinned PyBDSF `master`, maintained Aegean
         release, containers, dependencies, configurations, input checksums,
         output mappings, applicable strata, margins, and one-look rule. The
         closed Step 2C-A confirmation may inform diagnosis but may not be
         reused for selection or confirmation; qualification remains unopened.
         The frozen protocol uses 600 continuum images across four reviewed
         geometries and 800 compact/blend images, all with new globally
         disjoint noise seeds. It binds PyBDSF 1.14.1, pinned `master`
         `c70103b`, and isolated AegeanTools 2.3.5; exact primary and
         controlled-background configurations; like-product mappings; a
         topology-preserving truth matcher; 50,000 paired bootstrap resamples;
         and a conservative combined power lower bound of 0.9082. The Aegean
         image is isolated because its maintained release requires NumPy 2.x
         while the governed PyBDSF image retains NumPy 1.26. The public cut-out
         is explicitly deferred to Step 6 because no redistributable,
         checksum-bound truth input is present on the controlled host. Source-
         finder output remains unopened until the matcher and runners are
         implemented, tested, committed, and hash-bound.
   - [x] Implement and test the truth-first matcher, deterministic float64
         image/mean/RMS materializer, PyBDSF and Aegean product adapters,
         frozen Hebog candidate-product boundary, three isolated runners, and
         atomic raw-result manifests. Every runner refuses overwrite, verifies
         the common input bytes and a future named decision, checks its source
         tree and entry-point hashes, retains finder failures in the image
         denominator, and cannot run while the execution-decision record is
         absent. No external finder output was generated during implementation.
         PyBDSF's own RMS-map guard ignores supplied maps on the 512-pixel
         compact lane because the frozen 150-pixel RMS box exceeds one quarter
         of the image. The runner therefore marks that controlled diagnostic
         unavailable rather than mislabelling it; the operational primary and
         the 1,024-pixel continuum controlled diagnostic are unaffected. Named
         review accepted this scoped limitation on 2026-08-11 before
         authorizing the one terminal comparison.
   - [x] Prepare the approved immutable Hebog runtime from the clean
         `106715b22b9858149e42467f4e2c581f15961cb0` archive. The Linux/arm64
         Python 3.14.7 image digest is
         `sha256:b92080db558246e2ae781c69f6caf39fef8e393ab74ea6774d9b02672981b4ce`;
         its complete 35-distribution inventory hashes to
         `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2`,
         and its baked source tree matches the checkout at
         `471bed9a428df10d9139afc334d97b5df190f4f64e6dd6daeb91f9b436d37362`.
         The CLI/import surface, zero-image residual-B3 kernel, and complete
         compact branch on the existing 256-pixel development fixture passed.
         No external-comparison realization was materialized or processed.
   - [x] Freeze Gemma Danks's 2026-08-11 final approval as
         `config/contracts/phase-5-external-execution-decision.json`. The
         decision binds protocol `b9db9ad...`, residual-B3 review `b7bcf5d...`,
         implementation `106715b`, source tree `471bed9...`, the three exact
         runner hashes, the prepared Hebog runtime, and four PyBDSF cores. It
         authorizes one terminal comparison while keeping the one-look
         unopened and Step 3, optimization, and qualification false.
   - [x] Reconstruct all four missing Linux/arm64 campaign images without
         opening the one-look. Hebog retains its exact `471bed9...` source tree
         and `d383be3...` inventory. The new Hebog, PyBDSF release/master, and
         Aegean image digests are `f78be6d...`, `7245407...`, `192964b...`, and
         `b496d29...`; their complete inventory hashes are `d383be3...`,
         `8211043...`, `83574dd...`, and `346c1f3...`. Both matched PyBDSF
         runners reproduced three sources and three Gaussians on the governed
         256-pixel compact fixture; Aegean reproduced three islands and six
         fitted components; Hebog's exact source/inventory and CLI checks
         passed. Check in pinned rebuild definitions, but do not claim bitwise
         equality with the missing OCI objects.
   - [x] Complete the technical reconstructed-runtime pre-review and replace
         drift before seeking approval. The PyBDSF release/master runtimes use
         the same Python 3.12.3 scientific stack and differ only in `bdsf`;
         both reproduce three sources and Gaussians on the governed compact
         fixture. Reject the first Aegean reconstruction because it resolved
         newer Astropy/SciPy releases; its replacement retains NumPy 2.5.2,
         SciPy 1.17.1, Astropy 7.2.2, and LMFit 1.3.4 and reproduces three
         islands and six components. Protocol-bind the three reviewed external
         images and make the active execution decision explicitly fail closed
         while approval is pending.
   - [x] Rebuild Hebog from committed fail-closed validator source
         `303a49de...`. The final Linux/arm64 image is `sha256:728bbd7...`, its
         source tree is `2f80c87...`, and its unchanged dependency inventory is
         `d383be3...`. The CLI, runner-help boundary, checksum checks, and
         governed 256-pixel compact fixture pass with the expected three
         sources. Bind that exact identity into the pending decision and
         refresh the registry/evaluation hash chain. Host free space is 61 GiB,
         above the approximate 60 GiB campaign safety target.
   - [x] Obtain renewed named approval for all four reconstructed identities,
         retaining four PyBDSF cores, the approved 512-pixel limitation, and
         one sealed terminal execution. Record Gemma Danks's 2026-08-11
         approval in the exact execution decision before running a campaign
         command.
   - [x] Repeat the complete launcher's no-write preflight against the renewed
         decision and four inspected images. It passed exactly 1,400 inputs and
         7,000 runs with request `31a56c50...`; both terminal and hidden staging
         paths remained absent. The one-look is ready for its one authorized
         terminal execution.
   - [x] Implement and review the complete-population launcher. It stages
         all inputs and raw finder results privately, refuses an existing
         campaign target, retains every failed image in the denominator, and
         publish nothing until all frozen legs have reached a terminal state.
         Do not use the one-realization runners interactively or inspect
         partial products. The launcher freezes 1,400 common inputs and 7,000
         applicable runs, executes inspected immutable image IDs with no
         network and four PyBDSF cores, resumes only the exact request, and
         atomically publishes a checksum-verified terminal manifest. Its
         no-write approved-runtime preflight passed with request SHA-256
         `182944e174098544092a8e48490bdbfd39f7d9e332a9beb586b1db2441522ef7`;
         no private staging or finder output was created.
   - [x] Freeze and test the external scientific decision boundary before
         opening the one-look. `phase-5-external-evaluation.json` binds the
         exact evaluator, upstream protocol, Phase 4/5 gates, compact decision
         engine, and confirmed irregular-position review. It applies absolute
         truth first, then every binding paired comparison, fails closed on an
         unavailable reference or incomplete image/endpoint population, and
         declares excess observed paired variance underpowered. The mapping is
         machine-explicit: compact-component radial median/p95 retain
         0.10/0.25 beam; irregular detected segments retain 0.10-beam signed
         x/y bias and a 0.50-beam one-sided radial-p95 upper confidence bound,
         while their radial median is report-only. Fourteen synthetic tests
         cover passing, higher- and
         lower-is-better absolute and paired failures, unavailable or missing
         references, candidate failure, non-finite evidence, excess variance,
         incomplete populations, duplicate endpoint identity, overwrite
         refusal, compiler absence, paired-regression sign inversion, and
         separation of absolute confidence bounds from paired point estimates,
         and mapping drift.
   - [x] Implement and freeze the raw-product science compiler and exact
         endpoint registry before campaign execution. It must verify the
         terminal `campaign.json` and every artifact checksum; derive analytic
         truth and applicable group, pixel, and catalogue populations without
         opening an adaptive endpoint set; run finder-neutral association;
         produce the sufficient statistics for absolute and paired whole-image
         inference; reuse the frozen Phase 4 decision engine for compact
         endpoints; retain failures in denominators; and preserve typed
         unavailable/inapplicable products. Validate it on synthetic manifests
         and already-viewed development evidence, bind both hashes in
         `phase-5-external-evaluation.json`, and obtain pre-results review. Do
         not run or inspect the fresh 1,400-image campaign before this closes.
         The original pre-results compiler was bound at `81d1384d...`. The
         terminal campaign exposed a fail-closed role-type defect before any
         analysis was written. Its type-only correction is bound at
         `7a055891...`, the refreshed endpoint registry at `d174fc9e...`, and
         the
         evaluator at
         `df99e10a...`. Exact request/runtime drift, topology semantics,
         conditional measurements, failures, applicability, endpoint sets,
         and write-once outputs are covered. The irregular-position adapter
         reproduced 105 values from closed development evidence with zero
         difference. No fresh external result was opened.
   - [x] Run both PyBDSF references with Rapthor's residual à trous profile
         (`atrous_do=true`, three governed scales, and 5/3-sigma thresholds)
         on the same FITS images, beam, WCS, valid region, and declared science
         target. Where supported, add a controlled-input diagnostic using the
         same frozen background and RMS products; keep each finder's normal
         operational configuration as the primary interoperability result.
   - [x] Run Aegean blind source finding on the same inputs with a frozen
         standard-practice configuration and a separately labelled
         threshold-matched diagnostic if required. Make its completeness,
         reliability, astrometry, peak/integrated flux, component association,
         duplicate, and split/merge results binding for compact, blended, and
         Gaussian-like or mixed catalogue populations. Report its diffuse,
         filament, shell, extended-mask, and multiscale-provenance results
         without treating unavailable products as either success or failure.
   - [x] Evaluate analytic and injected truth first. Hebog must pass every
         unchanged absolute gate and be non-inferior to released PyBDSF and
         pinned `master` on every applicable full-continuum endpoint and
         stratum, and to Aegean on every applicable catalogue endpoint and
         stratum. Use the predeclared one-sided 95% confidence rules with no
         cross-metric or cross-morphology compensation. A reference failure
         cannot excuse a Hebog absolute failure; an incomplete reference leg
         makes the corresponding comparison unavailable and fails closed. The
         frozen evaluator did fail closed: all 143 Continuum endpoints were
         indeterminate, the compact decision failed, and no candidate or
         paired scientific value was admitted. The analysis and decision
         SHA-256 identities are `bdc59fdc...` and `73c7e2eb...`.
   - [ ] Include a bounded public or challenge cut-out with injected or curated
         truth if redistribution and exact execution are feasible. Otherwise
         require it in Step 6 and keep real-data cross-finder agreement
         diagnostic rather than treating majority agreement as truth.
   - [x] Record scientific outcomes before runtime. Report wall time, CPU,
         memory, failures, and output counts for context, but use cost only
         after the scientific rule finds Hebog eligible. Authorize Step 3 only
         when the named human review accepts the estimator/endpoint and this
         external comparison passes; otherwise select no production candidate
         and revise the plan without weakening or post-hoc changing a gate.
         The recorded outcome is `select-neither`: 2,292 of 7,000 terminal
         finder runs succeeded and 1,492 of 5,000 binding runs succeeded.
         Aegean completed 1,600/1,600 runs; Hebog completed 692/1,400; both
         PyBDSF references each completed 0/2,000. The serial campaign took
         about 7 h 12 min. Per-run CPU and peak memory were not captured, so
         they are explicitly unavailable; failed-leg wall times are not
         performance evidence and no runtime comparison is authorized.

2C-PF. **Correct terminal product interoperability before a fresh external
comparison.**

   - [x] Freeze the closed campaign's failure taxonomy and reproduce each
         class on bounded development fixtures or explicitly diagnostic use
         of an already-opened failed realization. Do not rescore, retune, or
         promote any result from campaign `b9996100...`.
   - [x] Correct and independently test PyBDSF product interpretation for both
         pinned versions: reconcile exported island-mask semantics with
         `pyrank` labels, and make controlled mean/RMS filenames conform to
         PyBDSF's actual file-loading contract. Require the native mask and
         labels to agree exactly, Gaussian island IDs to be a subset of source
         island IDs, and source island IDs to be a subset of label IDs. This
         preserves legitimate detected islands for which PyBDSF fitted no
         source instead of inventing a catalogue row.
   - [x] Review Hebog's terminal catalogue contract for reconstructed
         segments with non-positive aperture flux and for positions without a
         finite local RMS. Preserve every detection in the denominator and
         represent unavailable or non-physical measurements explicitly; do
         not clip flux, substitute noise, discard difficult morphologies, or
         weaken association and flux gates merely to make a run succeed. Flux
         is now measured on exact accepted support; an unmeasurable segment
         remains in mask/labels without a fabricated catalogue row, and local
         RMS uses normalized masked bilinear interpolation only when valid
         interpolation support exists.
   - [x] Pass a diagnostic development execution-validity matrix for all four
         finder implementations across compact, diffuse, shell, filament,
         masked, edge, and varying-noise cases before freezing new evidence.
         The 12 applicable cells passed with zero unexpected runner failures:
         Hebog on both inputs, each PyBDSF reference in compact operational
         and continuum operational/controlled modes, and Aegean in both modes
         on both inputs. The approved 512-pixel PyBDSF controlled diagnostic
         remains inapplicable. No scientific metric was compiled or opened.
   - [x] Implement and regression-test the prospective successor science
         compiler boundary so native label/mask detections without catalogue
         rows remain in mask and topology denominators without being treated
         as catalogue rows in completeness, reliability, flux, or position.
         Require exact parity
         with the terminal compiler when every native support has a catalogue
         row. The new boundary has complete focused branch coverage and passed
         real-product integration against both pinned PyBDSF versions; the
         checksum-bound terminal compiler remains byte-identical.
   - [x] Generate and power-audit a new seed-disjoint successor population
         without opening finder output. The frozen 600-image continuum and
         800-image compact/blend lanes reuse the reviewed geometry, endpoint,
         margin, and sample-size design but use 1,400 seeds disjoint from all
         9,053 historical seeds in 35 manifests. Their recomputed conservative
         joint-power lower bound is 0.908176 against the unchanged 0.90 gate.
         The freeze binds candidate source `d50be75...`, the corrected runners,
         mask-only kernel `8e38de3...`, manifests `906a3e8...` and
         `05507a6...`, and all intended package inventories. The three exact
         reference images remain present; the Hebog image is deliberately
         unbound and must be rebuilt from the candidate source before review.
   - [x] Freeze and technically review the successor compiler composition,
         endpoint registry, evaluator, unchanged absolute and paired gates,
         complete-population launcher, candidate runtime, and one-look rule.
         The rebuilt Linux/arm64 Hebog image has digest `d0c1319...`, source
         tree `d50be75...`, and the predeclared dependency inventory
         `d383be3...`. The composed boundary reuses the byte-identical terminal
         campaign verifier, compact compiler, interval engine, and evaluator;
         only the independently tested `8e38de3...` mask-only continuum
         kernel and seed-disjoint manifests differ. The launcher expands all
         1,400 inputs and 7,000 runs but rejects the pending decision before
         container inspection or staging. No successor finder output has been
         opened.
   - [x] Obtain named approval bound to the successor preflight review and
         exact runtime identities, mechanically refresh the decision-dependent
         registry/evaluation hashes, and run the no-write preflight. Gemma
         Danks approved review `200d107...` and the exact four-runtime set on
         2026-08-12. Request `931df41...` passed with exactly 1,400 inputs and
         7,000 runs; both terminal and private staging paths remained absent.
   - [x] Restore at least the reviewed approximate 60 GiB campaign storage
         headroom, then execute the approved successor one-look exactly once.
         Restarting the idle Podman VM released deleted closed-campaign blocks
         and raised free space to 81 GiB. Request `931df41...` then completed
         once and atomically published sealed campaign `6446705...`: all 1,400
         inputs and 7,000 runs verified, with 6,939 successes and 61 typed
         failures. No partial scientific product was opened.
   - [ ] Compile the sealed successor campaign and run the unchanged evaluator
         before interpreting runtime. The first compiler attempt failed closed
         before writing analysis because the composed terminal verifier knew
         only the closed campaign's approval vocabulary. Regression-test and
         commit a compatibility view that maps only the already-validated
         successor decision ID/value to their terminal equivalents; keep the
         terminal compiler, science kernel, endpoint set, gates, and campaign
         unchanged. Then run the write-once compiler and evaluator. Step 3
         opens only if the new
         campaign passes every unchanged absolute and applicable paired gate;
         the closed campaign is diagnostic history, not pooled evidence.

2D. **Determine the Rapthor profile without narrowing community science.**

   - [ ] Freeze the Rapthor revision, LSMTool filtering implementation, input
         checksums, released and pinned-`master` PyBDSF configurations, and
         several real `filter_skymodel` calls before inspecting decisions.
   - [ ] Run an isolated compact-only decision probe that feeds the Hebog
         compact mask and the PyBDSF multiscale mask separately through the
         same LSMTool filtering logic. This may use a bounded validation
         harness; the public backend, fallback, and dual-run integration
         remain Phase 7 work.
   - [ ] Compare retained and rejected identifiers for every true, apparent,
         and bright sky-model component, with explicit attribution to the five
         multiscale-only objects in the representative image and to extended,
         edge, masked, sparse, and crowded strata.
   - [ ] Select the Rapthor `compact` profile only if the predeclared at-least
         99.5% agreement gate and every safety stratum pass. Otherwise select
         the qualified `continuum` profile. Record catalogue and diagnostic
         differences separately even when filtering decisions agree.
   - [ ] Treat this as workflow-profile evidence only. Continue the general
         continuum implementation and qualification in either outcome, retain
         the PyBDSF fallback until Phase 7 acceptance passes, and do not claim
         general extended-source equivalence from Rapthor agreement.

3. **Implement scale detection and extended-island measurement after Steps
   2C-H and 2C-P pass.**

   - [ ] Detect significant residual emission at every configured scale from
         shared à trous smoothings and calibrated local noise. Reconstruct
         accepted adjacent-scale signal without retaining an image-sized
         response bank. Keep graph and kernel work proportional to tiles and
         scales, not pixels, RMS windows, or islands.
   - [ ] Define scale-specific connectivity, cross-scale persistence, support
         regions, seed-and-grow rules, and minimum areas with exact analytic
         boundary tests.
   - [ ] Complete islands deferred by the compact planner through a bounded
         partitioned path. No task may require the full bounds or membership
         of an arbitrarily large island on one worker.
   - [ ] Measure extended emission from original background-subtracted pixels
         using the reconciled support, with explicit background, flux,
         centroid, shape, uncertainty availability, and truncation semantics.
         Treat scale coefficients as detection provenance, not photometry.
         Preserve typed unavailable or failed outcomes; never substitute zero
         or silently publish a partial catalogue.
   - [ ] Retain compact Phase 4 measurements unchanged when no multiscale
         evidence alters their association. Enabling extra scales must not
         perturb an isolated compact source.

4. **Reconcile scales and construct complete products.**

   - [ ] Define deterministic cross-scale overlap and ownership rules before
         implementation. Resolve ambiguous compact/extended associations from
         physical overlap and flux evidence, never local label, tile,
         completion, or worker order.
   - [ ] Merge fragments of one extended object without merging physically
         distinct compact components embedded in or projected on extended
         emission.
   - [ ] Suppress duplicate scale detections while retaining provenance for
         every contributing scale and the selected representation.
   - [ ] Derive stable island, source, and Gaussian-component identities from
         reconciled global properties. Document whether an extended source has
         zero, one, or several Gaussian compatibility components and test the
         Rapthor adapter mapping explicitly.
   - [ ] Combine compact and multiscale shards through bounded deterministic
         reductions. Publication succeeds only when every accepted or
         deferred island has a valid terminal disposition.
   - [ ] Materialise the combined catalogue, source-filtering mask, RMS
         product, diagnostics, and Rapthor compatibility view without changing
         frozen compact-only output.

5. **Prove tiled and executor-independent behaviour.**

   - [ ] Derive each scale's halo from finite support or a reviewed truncation
         tolerance. Trim every tile to its non-overlapping output core and
         reject configurations whose halo cannot meet the memory contract.
   - [ ] Test one-tile versus many-tile equality for sources crossing every
         edge and corner topology, multiple partition origins, rectangular
         tiles, clipped image edges, invalid regions, and the largest scale.
   - [ ] Prove partition, tile-shape, batch-shape, worker-count,
         completion-order, retry, and executor invariance for detections,
         identities, associations, measurements, catalogue rows, masks, and
         diagnostics.
   - [ ] Retain only bounded tile cores, scale halos, convolution workspaces,
         extended-object summaries, and catalogue shards. Record peak retained
         bytes and boundary-summary volume in tests and benchmarks.
   - [ ] Exercise SerialExecutor and the existing executor path on test-sized
         cases. Production Dask planning and facility-scale proof remain
         Phase 6 work, but Phase 5 may not introduce scheduler-dependent
         scientific semantics.

6. **Qualify science, regression, and incremental performance.**

   - [ ] Promote each reviewed development failure and boundary defect to a
         deterministic regression fixture before fixing it.
   - [ ] Repeat the pre-development comparison with the final production
         implementation and untouched qualification data. Compare Hebog with
         injected truth, both exact PyBDSF references across the full continuum
         scope, and Aegean across its binding compact/Gaussian catalogue scope,
         stratified by morphology, angular scale, SNR, edge status, blend
         status, and background regime. Report threshold crossings as
         completeness and reliability changes.
   - [ ] On public multi-survey or challenge cut-outs, compare compact
         populations with PyBDSF, Aegean, and Selavy and extended masks and
         fluxes with PyBDSF à trous, ProFound, and CAESAR where runnable.
         Publish per-population results and failure modes; do not rank a
         finder from one aggregate score or make these tools runtime
         dependencies.
   - [ ] Re-run the complete Phase 4U compact regression and require every
         binding absolute gate, paired endpoint, and stronger-Hebog envelope
         to remain satisfied. Investigate compact point-estimate degradation
         even when an interval is inconclusive.
   - [ ] Open the frozen Phase 5 qualification exactly once with the reviewed
         evaluator and immutable candidate/reference identities. Retain a
         terminal failed decision without rescoring or changing its
         population.
   - [ ] Benchmark the complete incremental Phase 5 path at 256, 512, 1,024,
         and 3,000 pixels per side across sparse, normal, dense/extended, and
         mixed compact/extended work. Add cases on both sides of any new
         convolution or executor crossover.
   - [ ] Keep multiscale processing and merge within the controlled four-core
         3,000-square median budget of 6.0 seconds. Apply Section 1's
         five-percent Hebog regression rule at affected and adjacent tiers;
         record task, scale, convolution, temporary-plane, memory, and output
         counts.
   - [ ] Update the living Marimo demonstration, current schemas,
         configuration reference, scientific-method documentation, readiness
         record, and `LOG.md`. Provide per-object scale/support provenance and
         an auditable diagnostic mode for reconstruction, mask, model, and
         residual products without forcing their materialisation in the fast
         path. Run the relevant scientific, executor, documentation, package,
         coverage, and repository checks.

#### Phase 5 exit gate

Phase 5 closes only when:

- a human-reviewed follow-up to the rejected Step 2C-A result passes a new
  predeclared final-output scientific comparison in every applicable masked,
  edge, scale, morphology, noise, and SNR stratum before candidate-specific
  optimization;
- the pre-development Step 2C-P comparison shows Hebog is scientifically
  non-inferior to released and pinned-`master` PyBDSF over the full applicable
  continuum scope and to Aegean over its applicable compact/Gaussian catalogue
  scope, while still passing every absolute truth gate;
- reviewed analytic, generated-truth, dual-reference, edge, invalid-pixel,
  deferred-island, mixed compact/extended, and untouched qualification cases
  pass their predeclared gates;
- scale-stratified completeness, reliability, integrated flux, astrometry,
  duplicate, mask, island split/merge, and Rapthor filter-decision results
  meet absolute-truth and paired non-inferiority requirements;
- the complete Phase 4U compact regression remains passing, and compact-only
  output is unchanged where no multiscale evidence exists;
- the Rapthor decision probe records an explicit `compact` or `continuum`
  profile outcome without changing the general continuum gates or opening the
  Phase 7 backend cutover;
- one-tile/many-tile and serial/executor results satisfy the frozen
  determinism contract, with memory bounded by cores, scale halos,
  workspaces, summaries, and shards rather than image or extended-island size;
- the complete incremental multiscale stage meets the 6.0-second
  representative budget and has no unapproved adjacent-tier regression; and
- named independent radio-astronomy and engineering review accepts the
  evidence, algorithm choice, inspectable provenance, residual risks, and
  Phase 6 handoff.

Passing this gate establishes the scheduler-independent multiscale scientific
milestone. It does not establish complete Rapthor speedup, deployment storage
behaviour, 100-to-200-plus-node scalability, real worker-loss recovery,
independent radio-astronomy approval, or production cutover.

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

Phase 0 captured matched, versioned released and `master` baselines.
Performance is evaluated as a curve, not one headline image. The frozen size
regimes are:

| Regime | Frozen representative sizes | Primary concern |
| --- | --- | --- |
| Small | 256, 512, and 1,024 pixels per side | Startup, I/O, validation, and dispatch overhead |
| Current representative | 3,000 pixels per side | Dual-PyBDSF latency and component budgets |
| Large single-node candidates | 8,000 and 10,000 pixels per side | Memory-rich local batching versus Dask crossover |
| Distributed | 30,000 pixels per side | Storage throughput, occupancy, reconciliation, and graph overhead |
| Extreme qualification | 100,000 pixels per side | Out-of-core correctness and 100-to-200-plus-node scaling |

These are benchmark anchors, not hard-coded execution thresholds. Controlled
measurements determine crossovers from image planes, halos, source density,
storage, admitted CPUs/RAM, and executor overhead. Add near-boundary cases
whenever the fastest valid plan changes.

The design budget for the representative 3,000-by-3,000 case is:

| Component | Current budget |
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
| Filter coefficients are mistaken for source photometry | Separate detection, reconstruction, support growth, and measurement; evaluate final flux and shape on original background-subtracted pixels |
| A Rapthor compact profile is mistaken for general scientific completeness | Make profiles explicit in configuration and every product, prohibit extended-complete claims for compact output, and retain independent continuum qualification |
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
| Full PyBDSF scope delays delivery | Implement the qualified compact and general continuum profiles, not every PyBDSF option or output format |
| Algorithm licensing or attribution is unclear | Use published algorithms, write new code, document sources, and complete review before release |
| A frequent release is mistaken for production readiness | Label every `0.x` capability and limitation explicitly; require the complete gates and soak before 1.0 or default cutover |

## 14. Phase 5 decision ledger and open questions

Phase 4 selected SciPy bounded least-squares, calibrated its available compact
position and flux uncertainties, retained absent shape uncertainties, and
qualified one fitted Gaussian and one source per compact deblended region.
Selective moment-only cataloguing was not adopted. Those decisions are
documented in the [Phase 4 readiness record](../docs/reference/phase-4-release-readiness.md)
and are now regression constraints rather than open questions.

Step 2 provisionally selected the float64 beam-aware matched-filter bank after
the initial analytic screen. Step 2B superseded that selection status: the
matched filter was more consistent and had higher calibrated response SNR,
while the wavelet was better for several straight masked half-planes and had
substantially better generated mask overlap. Neither passed the complete
absolute and paired matrix; the reviewed decision was `select-neither`. See the
[filter decision](../docs/reference/phase-5-filter-selection.md).

The community-practice review made residual B3-spline à trous detection,
reconstruction, morphology-independent support, and original-image
measurement the corrective Step 2C candidate. This is familiar to PyBDSF and
Selavy users while adopting segmentation strengths exposed by ProFound,
CAESAR, and Hydra. Step 2C-R corrected association, artifact disposition, and
false-positive control. Step 2C-A exposed astrometry variance and uncertainty
undercoverage. Step 2C-H rejected direct and Gaussian-assisted estimators;
Step 2C-HR then separated compact-component astrometry from irregular
detected-segment repeatability and passed fresh development and one-look
confirmation. The completed comparisons remain internal to Hebog. Step 2C-P
now requires direct non-inferiority against both exact PyBDSF references and,
for its applicable compact/Gaussian scope, Aegean before Step 3. Step 2D
separately decides only whether Rapthor uses the `compact` or `continuum`
profile.

Resolve the remaining decisions through the ordered Phase 5 evidence gates;
do not select from convenience or PyBDSF implementation detail alone:

- Which scale-specific threshold, connectivity, and support rules recover
  diffuse and filamentary truth without duplicating compact sources?
- Does compact-only processing preserve Rapthor's retained/rejected sky-model
  decisions in every governed real-workload stratum, or must its adapter use
  the continuum profile?
- Which deterministic overlap evidence establishes cross-scale identity,
  compact/extended association, split/merge behaviour, and ownership across
  tile boundaries?
- How are extended islands, sources, and any compatibility Gaussian components
  represented so the internal schema stays scientifically explicit while the
  Rapthor adapter retains its frozen contract?
- Which extended-flux and uncertainty estimators are calibrated by morphology,
  angular scale, SNR, edges, masks, and correlated noise, and which values must
  remain explicitly unavailable?
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
14. The general continuum profile passes reviewed public multi-survey or
    challenge comparisons across at least two telescope families, exposes
    auditable per-object detection and measurement provenance, and receives
    independent radio-astronomy approval before becoming the scientific
    default.
