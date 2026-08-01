# Phase 2 release readiness

**Decision:** Phase 2 is technically complete and suitable for the next
experimental `0.4.x` release. The release provides deterministic background
and RMS estimation over bounded FITS windows, including sparse adaptive
refinement around explicit bright-candidate positions. It does not yet detect
sources: `hebog.pipeline.find_sources` remains unimplemented until the later
detection, island, measurement, and multiscale phases are complete.

The current scientific stage is pipeline-neutral. It accepts an image source,
immutable configuration, and scheduler-independent executor; it does not
import Rapthor, Prefect, LSMTool, or a concrete scheduler. Rapthor
configuration translation, automatic bright-candidate selection, product
persistence, and complete `filter_skymodel` integration remain later work.
Consequently, this release must not be described as a complete PyBDSF
replacement, Rapthor-ready, or production-ready.

## Implemented capability

- vectorised, sigma-clipped background and RMS statistics for batches of
  independent windows, using Astropy's established clipping implementation;
- deterministic globally anchored, edge-aligned coarse windows whose
  scientific results do not depend on tile geometry or worker order;
- bounded rectangular input batches, with no Python loop over pixels or RMS
  windows and no scheduler task per window;
- explicit handling of masks, NaNs, negative backgrounds, bright outliers,
  constant and zero-RMS windows, insufficient samples, and all-invalid data;
- cached nearest-available fallback and SciPy interpolation that preserve
  affine backgrounds without recomputing window statistics;
- an admitted whole-image constant fallback for small inputs, with a hard
  pixel limit that prevents an accidental unbounded read;
- local fine grids and smooth blending only around explicit bright candidates,
  with distant candidates retained as separate bounded regions; and
- identical serial and Dask results across output tile shapes, shifted
  partition origins, task order, and deterministic retries.

Output tiles contain float64 background and RMS arrays, explicit global core
bounds, scientific-availability state, and fallback-cell counts. Invalid
input pixels become NaN in both output planes. The caller owns persistence,
which can use the Phase 1 Zarr product sink without changing the scientific
kernel.

## Scientific comparison evidence

The portable equivalence lane recomputes a Hebog RMS map from the exact
generated 256-by-256 Phase 0 input. It compares the result independently with
released PyBDSF 1.14.1 and pinned PyBDSF master products. Both reference
products produce the same result for this case; Hebog's median absolute
fractional difference is 1.575% and its 95th percentile is 1.575%, passing the
2% and 5% RMS gates.

A validation-only comparison also used both 3,000-by-3,000 representative
Rapthor inputs, the frozen PyBDSF source-filter mask, and both reference
campaigns:

| Branch | Compared pixels | Median difference | 95th percentile | Gates |
| --- | ---: | ---: | ---: | --- |
| True sky | 8,980,478 | 1.437% | 4.279% | pass |
| Flat noise | 8,980,478 | 1.418% | 4.278% | pass |

Released and master PyBDSF maps are identical for these two RMS comparisons.
The representative Hebog map SHA-256 values were
`61491cbca860356798844a9b75bef7f72f4d1ac2a6dd50a236b557814e142a19`
for true sky and
`c66f747eeb5aef999f282c88f7ebc357e68c1fb3c1161b9709379fc76aa2cb61`
for flat noise. These validation arrays are deliberately not committed.

This evidence establishes the Phase 2 RMS-map gate, not complete source-finder
equivalence. Detection threshold crossings, island membership, catalogues,
masks, multiscale emission, and retained/rejected Rapthor sky-model components
remain their later scientific gates. PyBDSF remains a compatibility oracle,
not assumed ground truth.

## Four-core component evidence

The committed runner at
`scripts/benchmark/measure_phase2_background.py` measured each representative
branch independently with one warm-up and five repetitions. It used a reused,
caller-owned in-process Dask client with four one-thread workers, 150-by-150
windows at 50-pixel steps, 64-cell statistic batches, 1,500-by-1,500 output
tiles, and float64 calculations. Client startup was excluded because Rapthor
owns and reuses the production cluster.

| Branch | Budget | Median | Measured range | Planned Dask tasks | Maximum process RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| True sky | 4.000 s | 2.471 s | 2.397–2.553 s | 64 | 927.8 MiB |
| Flat noise | 3.000 s | 2.527 s | 2.463–2.541 s | 64 | 929.1 MiB |

The matched Phase 0 campaigns recorded median complete-process peaks of about
1.296 GB for released PyBDSF and 1.301 GB for master, so Hebog did not increase
the observed peak-memory measure. PyBDSF sampling records the largest parent
or child rather than aggregate concurrent residency; Hebog samples its single
in-process scheduler-and-worker process. The figures are therefore suitable
for the Phase 2 non-regression gate but are not allocation counts or
multi-node aggregate-memory claims.

The Phase 0 component medians were 32.610 seconds true-sky and 12.582 seconds
flat-noise for released PyBDSF, and 30.305 and 11.939 seconds for master.
Hebog's component is substantially faster in this controlled comparison, but
the project speed requirement applies to the complete matched Rapthor
`filter_skymodel` operation. No end-to-end speedup claim is made here.

Raw versioned Hebog evidence remains under the ignored
`benchmark-results/phase-2/` directory. The runner records exact input and
configuration hashes, dependency and environment identities, every
repetition, CPU time, peak RSS, planned Dask task count, partition count, and
maximum tile size. Dask transfer/spill attribution and complete third-party
copy counts are marked unavailable with reasons rather than reported as zero.

## Implementation choices and remaining scale work

The controlled measurements meet both component budgets with vectorised
NumPy, SciPy, and Astropy. Numba, Rust, and C++ therefore do not meet the
project's native-code decision gate and were not introduced. The selected
64-cell batch and 1,500-pixel interpolation slab reduce local overhead without
changing scientific geometry. Float64 remains the policy because the
equivalence evidence was established at that precision; float32 requires its
own scientific comparison before it can become an optimization candidate.

The current Dask executor returns a bounded coarse summary to the caller and
sends only local bracketing samples to each output tile. It never sends or
gathers a complete image plane. Multi-level reduction of coarse summaries,
automatic memory-derived batch sizing, Zarr-backed output publication, and
30,000/100,000-pixel graph qualification belong to the distributed execution
and scalability phases. Passing the local Phase 2 gate does not demonstrate
100-to-200-plus-node scaling.

## Release checks and scientific review

Phase 2 uses analytic/property tests first, then the serial implementation,
serial/Dask conformance, frozen PyBDSF comparison, and controlled performance
evidence. Human scientific review is not needed to manually inspect every
passing RMS pixel. It remains necessary to approve the dataset fitness,
tolerances, default compatibility profile, automatic bright-source policy,
and any intentional difference from PyBDSF before Hebog claims complete
scientific equivalence or becomes Rapthor's default backend.

The Phase 2 handoff passed 387 portable unit, contract, and integration tests
with four strict expected failures and 92.96% branch-aware project coverage.
All ten portable equivalence tests pass; the seven future end-to-end
acceptance scenarios remain strict expected failures assigned to later
phases. Ruff, Pyright, strict MkDocs and Marimo validation, all pre-commit
hooks, and the isolated source-distribution-to-wheel smoke test pass. The
controlled qualification, large-scale, multi-node, and Linux/Windows CI
matrices were not reproduced on this local macOS host.

The [Phase 0 review record](phase-0-review-record.md) remains the reviewer
packet. Release Please derives the actual version from Conventional Commits;
release-managed version and changelog files are not edited manually.
