# Phase 1 release readiness

**Decision:** Phase 1 is technically complete and suitable for the next
experimental `0.3.x` release. The release provides bounded FITS and Zarr I/O,
partition and ownership contracts, versioned internal records, and
restart-safe materialisation. It does not yet provide a source-finding
algorithm: `hebog.pipeline.find_sources` still raises `NotImplementedError`.

Consequently, this release must not be described as scientifically equivalent
to PyBDSF, faster than PyBDSF, Rapthor-ready, or production-ready. Release
Please derives the actual version from the Conventional Commit history; the
version is not edited manually for this decision.

## Implemented and tested capability

- FITS metadata, beam, celestial WCS, units, image shape, invalid pixels, and
  bounded window reads;
- deterministic one-tile and many-tile partition manifests, clipped halos,
  global coordinates, and half-open pixel and source ownership;
- aligned Zarr v3 product chunks, checksums, identical retry, conflict
  detection, strict missing-chunk behaviour, validated generation publication,
  and interrupted-run recovery on `LocalStore`;
- versioned internal island, source, Gaussian-component, result, diagnostics,
  and product-identity records;
- structurally complete zero-row internal catalogues, explicit unavailable RMS
  images, boolean source-filtering masks, and canonical diagnostics;
- restart-safe FITS and JSON materialisation, including identical retry and
  conflict rejection; and
- the same bounded completed-Zarr row stream feeding one-tile and many-tile
  final RMS and mask writers.

The internal products are deliberately not the future PyBDSF/LSMTool
compatibility serialization. That mapping belongs at the Rapthor adapter
boundary after the relevant catalogue behaviour is implemented and reviewed.

## Exploratory local I/O evidence

The committed runner at
`scripts/benchmark/measure_phase1_io.py` generated a deterministic float64
FITS input, wrote float64 RMS and boolean-mask Zarr products, validated a
completed generation, and streamed both final FITS products. Each campaign
used one warm-up followed by five measured repetitions. Raw evidence remains
in the ignored `benchmark-results/phase-1/` directory.

Environment: Hebog commit
`39bd5397d84fe0150472adfb28ce7e66b2937fd2`, Hebog `0.2.0`, Python `3.14.2`,
Apple M3 Pro with 12 logical CPUs and 18 GiB RAM, arm64 macOS 26.5.2,
512-by-512 Zarr chunks, little-endian float64, Zstandard level 1, and CRC32C.

| Image | Tiles | Zarr objects | Concurrency | Median complete | Measured range | Maximum process RSS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 256 x 256 | 1 | 6 | 10 | 0.226 s | 0.222–0.232 s | 138.1 MiB |
| 512 x 512 | 1 | 6 | 10 | 0.249 s | 0.230–0.275 s | 164.2 MiB |
| 1,024 x 1,024 | 4 | 12 | 10 | 0.440 s | 0.419–0.471 s | 269.1 MiB |
| 3,000 x 3,000 | 36 | 76 | 10 | 2.519 s | 2.420–2.547 s | 578.1 MiB |

At 256 and 3,000 pixels per side, concurrency 1 produced medians of 0.231 s
and 2.552 s respectively. Concurrency 10 was only about 2.4% and 1.3% faster
in these exploratory campaigns. This is not sufficient evidence for a dynamic
concurrency policy, another codec, sharding, or a second storage backend, so
Phase 1 retains the simple fixed configuration.

Peak RSS is sampled from current process residency while each stage runs. It
includes the interpreter and libraries as well as memory retained across warm
repetitions; it is not an allocation count. Astropy and Zarr do not expose
complete allocation counters, so those metrics are explicitly unavailable.
Hebog-controlled final assembly is established structurally: at most one
full-width tile row plus the current decoded chunk, with no extra assembly
array for one-tile work. The largest configured row block above was 11.72 MiB.

These measurements create the first implemented Hebog I/O curve. They do not
compare a complete source-finding path with PyBDSF, qualify cold-cache or
deployment-store behaviour, or demonstrate Dask scaling. Deployment-store
atomicity, throughput, concurrency, and recovery remain later controlled
qualification gates.

## PyBDSF equivalence assessment

The repository does **not** yet have enough tests to show that Hebog output is
equivalent to PyBDSF. The current equivalence lane proves two narrower facts:

1. the frozen released-PyBDSF and pinned-master artifacts retain their governed
   checksums; and
2. the comparison code correctly shows that those two PyBDSF references agree
   on the compact frozen case.

There is no Hebog-generated background, RMS, island mask, source catalogue, or
Rapthor filtering decision to compare yet. In particular, the current five
equivalence tests compare PyBDSF release with PyBDSF master, not Hebog with
either reference. Strong FITS, schema, storage, and comparison-harness tests
are necessary infrastructure, but they cannot establish scientific output
equivalence in the absence of the algorithms.

An equivalence claim requires the planned evidence to become executable as
the corresponding behaviour is implemented:

| Capability | Required evidence before an equivalence claim |
| --- | --- |
| Background and RMS | Analytic and property tests, then Hebog-versus-release and Hebog-versus-master RMS reports across varying noise, masks, edges, NaNs, and source-free regions |
| Detection, islands, and deblending | Generated-truth completeness/reliability plus reference mask and membership comparisons for compact, blended, edge, and threshold-crossing cases |
| Measurement and fitting | Position, peak and integrated flux, shape, uncertainty, source/component/island, and ambiguous-match reports against both references |
| Extended emission | Scale-stratified completeness and integrated-flux evidence for diffuse, filamentary, and mixed fields |
| Execution | One-tile/many-tile and serial/Dask invariance before either is compared with PyBDSF |
| Rapthor behaviour | End-to-end retained/rejected component agreement, empty/failure semantics, fallback, and dual-run reports |
| Release qualification | The frozen regression and held-out qualification matrix, with reviewed tolerances and no tuning on qualification results |

## Release checks

The Phase 1 handoff passed:

- 323 portable unit, contract, and integration tests, with four strict expected
  failures for later public-pipeline behaviour;
- 92.84% branch-aware project coverage against the 80% floor;
- all five small equivalence tests, with the scope limitation above;
- all seven acceptance scenarios as strict expected failures for their named
  later phases, so an unexpected early pass still fails review;
- Ruff formatting and linting, Pyright, JSON/YAML/TOML checks, strict Marimo
  validation, and the strict MkDocs build; and
- an isolated source-distribution-to-wheel build and clean wheel import.

The controlled qualification, distributed scalability, cold-cache,
deployment-store, and operating-system CI matrices were not reproduced on the
local qualification host. The repository CI remains configured for Python
3.12, 3.13, and 3.14 on Linux, macOS, and Windows.

## Why human scientific review remains necessary

Automated tests should determine whether a candidate output meets a frozen
contract; a human should not manually inspect every catalogue or image. Human
scientific review is still necessary, but its scope is narrower and more
important than visual verification:

- decide whether the dataset matrix represents the observatory pipelines and
  source populations Hebog must support;
- approve the metrics, tolerances, low-SNR treatment, and non-inferiority rule;
- approve terminology, default threshold profiles, empty-result semantics,
  and the internal-to-compatibility mapping; and
- adjudicate PyBDSF release/master disagreements and known or discovered
  reference defects.

This distinction matters because the project goal is scientific equivalence,
not byte-for-byte reproduction, and because PyBDSF is a compatibility oracle
rather than ground truth. Exact automated reproduction on a few fixtures could
faithfully preserve an unrepresentative behaviour or defect. Conversely, an
intentional numerical difference may be scientifically harmless or better but
must not be accepted by an implementation author moving the goalposts after
seeing qualification results.

Named sign-off is therefore not a blocker for beginning Phase 2 TDD against
the frozen provisional contracts. It remains a blocker for declaring defaults
or schemas scientifically stable, accepting intentional reference deviations,
claiming scientific equivalence, freezing Phase 4 compatibility semantics, or
cutting Rapthor over to Hebog. Beginning Phase 2 first carries an explicit risk
of rework if the reviewer amends the contract.

The reviewer packet and sign-off form are in the
[Phase 0 review record](phase-0-review-record.md).
