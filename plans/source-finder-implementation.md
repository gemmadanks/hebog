# Hebog implementation plan

## 1. Objective

Create a maintainable radio-continuum source finder that produces scientifically equivalent
results to the subset of PyBDSF used by Rapthor and reduces the median wall time of Rapthor's
complete `filter_skymodel` step by at least 50%.

The primary acceptance formula is:

```text
new median filter_skymodel wall time
------------------------------------  <= 0.50
matched PyBDSF baseline median wall time
```

Both measurements must use the same Rapthor revision, inputs, filter configuration, allocated
resources, output products, and benchmark host. Use at least five measured repetitions after
warm-up.

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
that exact benchmark is therefore 34.94 seconds. Phase 0 must reproduce and replace this with a
versioned baseline before it becomes a release gate.

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
- Serial, local, and Dask execution through the same scientific API.
- Direct integration into Rapthor without the current fork-safety subprocess escape.
- Reproducible PyBDSF equivalence and end-to-end performance harnesses.

### Initially out of scope

- Complete compatibility with every PyBDSF option and output format.
- Polarization-specific analysis not exercised by Rapthor.
- GPU execution.
- Distributed connected-component labelling for images that fit comfortably in one worker.
- Reproducing undocumented PyBDSF implementation defects.
- Copying or mechanically translating PyBDSF source code.

## 4. Required contracts

### 4.1 Public API

The library API must remain scheduler independent:

```python
result = find_sources(request, config, executor)
```

Requests contain input paths, an output directory, identifiers, and immutable configuration.
Results contain materialised output paths, counts, timings, schema versions, and small metadata.
They never contain open FITS handles, a Dask client, or a mutable full-image object.

### 4.2 Rapthor graph

Rapthor should own the top-level graph:

```text
find_true_sky_sources -----------+
                                 +--> apply_skymodel_filter
estimate_flat_noise_rms ---------+
```

The first two operations are independent and may run concurrently when their combined memory fits
the configured resource budget. Each operation emits restartable file products. The join applies
the existing filtering rules and creates the final sky model.

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
expert during Phase 0. Report metrics separately for isolated compact, blended, extended, edge,
and low-SNR sources.

| Metric | Initial gate |
| --- | ---: |
| Rapthor retained/rejected input components | at least 99.5% agreement |
| PyBDSF sources at SNR >= 10 recovered | at least 99% |
| PyBDSF sources at SNR >= 5 recovered | at least 98% |
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
curves versus injected truth; PyBDSF is not assumed to be ground truth.

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
8. Several `filter_skymodel` calls from a complete Rapthor benchmark run.

Use generated truth to measure absolute completeness and flux accuracy. Use frozen PyBDSF outputs
to measure compatibility. Production data that cannot be redistributed stays in an external data
store referenced by environment-neutral dataset identifiers.

## 7. Target architecture

```text
src/hebog/
  config.py                 immutable scientific configuration
  pipeline.py               scheduler-independent stage composition
  algorithms/
    background.py           robust coarse and adaptive RMS estimation
    detection.py            matched filters and threshold masks
    labelling.py            components, boundaries, and island properties
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
    catalogue.py            internal and compatibility schemas
  data_models/              small serializable requests and results
```

Scientific kernels operate on NumPy arrays. Use SciPy for validated array operations and Numba for
batched robust statistics or other kernels that otherwise require Python pixel/window loops.
Compiled kernels must release the GIL when practical. Dask is execution policy, not the array API
inside every function.

## 8. Delivery phases

### Phase 0: freeze baselines and contracts

- [ ] Capture the current Rapthor, PyBDSF, LSMTool, dependency, and container revisions.
- [ ] Reproduce the representative PyBDSF operation timings and current `filter_skymodel` median.
- [ ] Record per-stage wall time, CPU time, peak RSS, array copies, Dask task count, transfer, and
      spill metrics in machine-readable JSON.
- [ ] Inventory exactly which PyBDSF catalogue fields and image products Rapthor consumes.
- [ ] Add the dataset manifest, deterministic synthetic generator, and frozen reference products.
- [ ] Implement coordinate/flux catalogue matching and RMS/mask comparison reports.
- [ ] Obtain domain review of the scientific thresholds in Section 5.

Exit gate: a documented command reproduces the baseline and equivalence report on a clean
environment. No algorithm implementation begins without this comparison harness.

### Phase 1: FITS, beam, WCS, and internal models

- [ ] Read the required image planes using memory mapping where safe.
- [ ] Validate shape, units, WCS, beam, finite pixels, and masks at the boundary.
- [ ] Define versioned internal catalogue and materialised result schemas.
- [ ] Write round-trip tests for FITS, mask, RMS, and catalogue products.
- [ ] Measure and cap avoidable full-image copies.

Exit gate: reference inputs round-trip with correct coordinates, units, shapes, and invalid pixels;
the package can emit empty but structurally compatible products.

### Phase 2: robust background and RMS estimation

- [ ] Implement batched sigma-clipped statistics on a coarse window grid.
- [ ] Reuse buffers and calculate adaptive fine-grid cells only around bright candidates.
- [ ] Interpolate cached coarse samples; fallback interpolation must not recompute statistics.
- [ ] Treat masks, NaNs, edges, negative values, and insufficient samples explicitly.
- [ ] Add Numba only where profiling shows vectorised SciPy/NumPy is insufficient.
- [ ] Benchmark array dtype, window batching, and interpolation slab size.

Provisional component budget on the 3000 by 3000 reference image: no more than 4 seconds for the
true-sky background stage and no more than 3 seconds for the flat-noise RMS product on four
allocated CPU cores.

Exit gate: the RMS scientific gates pass across the dataset matrix and the component budget is met
without increasing peak memory above the matched PyBDSF run.

### Phase 3: thresholding, islands, and deblending

- [ ] Apply seed and island thresholds to normalized residuals.
- [ ] Label connected pixels with explicit connectivity and edge conventions.
- [ ] Calculate island bounding boxes and properties without copying the whole image per island.
- [ ] Implement deterministic deblending using a documented multilevel or watershed algorithm.
- [ ] Establish stable source and island ordering independent of executor completion order.
- [ ] Add injected-source completeness, reliability, blend, and edge tests.

Start with whole-image labelling in one worker. Only add distributed labelling if large-image
profiling proves it necessary; a distributed implementation must reconcile labels across chunk
halos exactly.

Exit gate: compact-source detection and island membership pass the relevant scientific gates and
show no quadratic scaling with source count.

### Phase 4: measurement, fitting, and catalogue compatibility

- [ ] Calculate vectorised moments for every island and use them to initialize fits.
- [ ] Accept moment-based measurements directly where nonlinear fitting cannot materially change
      filtering or catalogue acceptance.
- [ ] Batch remaining nonlinear Gaussian fits by estimated pixel/component cost.
- [ ] Implement beam deconvolution, sky-coordinate conversion, uncertainties, and units.
- [ ] Write the compatibility catalogue and side products required by LSMTool/Rapthor.
- [ ] Compare retained/rejected sky-model components end to end.

Exit gate: compact and blended source catalogues pass the position, flux, shape, and downstream
filter-decision gates.

### Phase 5: multiscale and extended emission

- [ ] Implement an undecimated wavelet or equivalent beam-aware filter bank with reused
      convolutions and background products.
- [ ] Detect significant emission at each configured scale without recursively rerunning the full
      pipeline.
- [ ] Merge cross-scale islands deterministically and prevent duplicate compact components.
- [ ] Add diffuse, filamentary, mixed, and artefact-dominated fixtures.
- [ ] Compare completeness and integrated flux by angular scale.

Exit gate: extended-source cases meet reviewed scientific tolerances and the multiscale path stays
within the complete runtime budget.

### Phase 6: local and Dask execution

- [ ] Extend the executor protocol for asynchronous coarse batches and resource metadata.
- [ ] Add a persistent local threaded executor for GIL-releasing kernels.
- [ ] Add a Dask executor that receives an existing client and never creates nested pools.
- [ ] Batch RMS cells, interpolation slabs, multiscale filters, and island fits by measured cost.
- [ ] Keep common image data in worker-local storage or publish it once; do not embed full arrays in
      every task.
- [ ] Add resource annotations for CPU and memory and tests for spill, retry, worker loss, and
      cancellation.
- [ ] Record graph size, scheduler overhead, transfer volume, task-duration distribution, and
      peak aggregate memory.
- [ ] Prove serial/local/Dask scientific equivalence.

Initial task-duration target: 0.2 to 2 seconds per coarse batch on the reference worker. Adjust from
measured scheduler overhead rather than fixing an arbitrary item count.

Exit gate: Dask improves throughput or critical-path time on the supported workloads, has no nested
fork behaviour, and stays within configured CPU and memory budgets.

### Phase 7: Rapthor integration and 50% gate

- [ ] Add a Rapthor backend flag selecting PyBDSF or `hebog`.
- [ ] Split true-sky finding, flat-noise RMS estimation, and final filtering into restartable tasks.
- [ ] Run independent tasks concurrently only when Dask resource annotations admit both.
- [ ] Remove the PyBDSF-specific subprocess escape from the new backend.
- [ ] Preserve PyBDSF as a feature-flagged fallback and support dual-run comparison mode.
- [ ] Measure complete `filter_skymodel` wall time across the full benchmark matrix.
- [ ] Profile at least 1, 2, 4, 8, and the current 15 allocated cores without oversubscription.
- [ ] Validate resume, retry, empty catalogue, corrupt input, and worker-loss behaviour.

Exit gate: the new backend passes all reviewed scientific gates and its matched median
`filter_skymodel` wall time is at most 50% of the PyBDSF baseline. Peak worker and aggregate memory
must not regress by more than 10% unless an explicitly approved throughput trade-off justifies it.

### Phase 8: hardening and release

- [ ] Add CI jobs for unit tests, small equivalence fixtures, Dask integration, packaging, and docs.
- [ ] Schedule production-data and performance suites on controlled runners outside merge-request
      critical paths.
- [ ] Publish configuration and output schema documentation and a migration guide.
- [ ] Add structured stage timings and scientific summary metrics to normal runs.
- [ ] Perform licensing, dependency, security, and reproducibility review.
- [ ] Release 0.1 as experimental, then make it the Rapthor default only after operational soak.

## 9. Performance budget

Phase 0 will replace provisional values with a matched, versioned baseline. The design budget for
the representative 3000 by 3000 case is:

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

## 10. Benchmark protocol

1. Pin CPU affinity and disable unrelated workloads.
2. Record the host, logical/physical cores, RAM, storage, filesystem cache policy, and worker
   topology.
3. Pin native BLAS/OpenMP thread counts to avoid hidden oversubscription.
4. Execute one unmeasured warm-up followed by at least five measured repetitions.
5. Record every repetition; compare medians and report minimum, maximum, and median absolute
   deviation.
6. Measure wall time, process CPU, peak RSS, aggregate worker memory, read/write bytes, Dask task
   count, transfer bytes, spill bytes, and failures/retries.
7. Produce the scientific comparison for the same outputs before accepting a speedup.
8. Store JSON results under `benchmark-results/` and commit only compact reviewed summaries with
   reproduction commands.

Run both cold-cache and warm-cache I/O measurements when FITS reading is material. Use warm-cache
results for algorithm tuning and cold-cache results for operational expectations.

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Low-SNR threshold crossings differ | Report completeness/reliability curves and validate Rapthor filter decisions |
| Extended or blended sources diverge | Maintain dedicated fixtures and stratified metrics; do not hide them in aggregate recovery |
| PyBDSF is not deterministic | Freeze multiple reference runs and separate same-tool scatter from replacement differences |
| Dask overhead erases kernel gains | Use coarse batches, publish data once, and retain an efficient local executor |
| Concurrent branches exceed memory | Use resource annotations and measure aggregate RSS before enabling concurrency |
| Numba compilation affects latency | Warm/cache kernels explicitly and report cold and warm timings |
| Catalogue compatibility becomes coupled to internals | Keep a versioned internal schema and an isolated PyBDSF/LSMTool adapter |
| Full PyBDSF scope delays delivery | Implement only features proven necessary by the Rapthor contract and dataset matrix |
| Algorithm licensing or attribution is unclear | Use published algorithms, write new code, document sources, and complete review before release |

## 12. Open decisions for Phase 0

- Which exact PyBDSF/LSMTool catalogue schema is the compatibility boundary?
- Which production datasets can be retained as reproducible benchmark fixtures?
- Should nonlinear fitting use SciPy least-squares, a small dedicated compiled kernel, or both?
- Is an undecimated wavelet transform required, or does a beam-aware matched-filter bank satisfy the
  extended-source gate more efficiently?
- Which worker-local storage mechanism best matches Rapthor deployment: FITS memory mapping, shared
  memory, Dask worker data, or an array-store format?
- What resource names and limits should Rapthor use for source-finder CPU and memory admission?
- Which scientific tolerances require formal SKA science approval before default cutover?

## 13. Definition of done

The project is ready to replace PyBDSF in Rapthor when:

1. The versioned dataset and equivalence suites cover compact, blended, extended, low-SNR, edge,
   invalid-pixel, and varying-noise cases.
2. All reviewed scientific gates pass for serial and Dask execution.
3. The matched median wall time of the complete `filter_skymodel` step is at least 50% lower.
4. Peak memory, scheduler overhead, graph size, retry, and resume behaviour meet operational gates.
5. Rapthor can select either backend, dual-run them for comparison, and safely fall back to PyBDSF.
6. Public schemas, configuration, migration, benchmark reproduction, and limitations are documented.
7. CI covers deterministic tests and controlled runners continuously monitor science and
   performance regressions.
