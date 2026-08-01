# Phase 3 release readiness

**Decision:** the Phase 3 compact-detection implementation is technically
complete and suitable for an experimental `0.x` release after named human
scientific review. The review has not yet happened, so this record does not
claim final scientific sign-off, complete PyBDSF equivalence, Rapthor
readiness, or production readiness.

Phase 3 implements compact detection topology only. Photometry, Gaussian
fitting, catalogue compatibility, multiscale recovery, and the final Rapthor
filter decision remain Phase 4 and Phase 5 work.

## Implemented capability

- finite positive-RMS normalization and explicit inclusive-island/strict-seed
  thresholds;
- SciPy eight-connected local labels and deterministic hierarchical
  side/corner reconciliation;
- stable global island identities independent of tile shape, task order,
  retry, executor, and local label values;
- automatic high-significance candidate discovery against an immutable
  coarse background cache and sparse adaptive-RMS refinement;
- immutable background, RMS, and accepted source-filtering-mask Zarr
  generations;
- deterministic compact watershed regions with explicit size/bounds
  deferrals to Phase 5; and
- bounded multi-island FITS and Zarr reads. A four-chunk validated LRU cache
  prevents dense compact batches from rereading one complete chunk per
  island.

Numeric intermediate planes use little-endian bytes plus CRC32C without
Zstandard; boolean masks retain Zstandard level 1 plus CRC32C. This
product-role policy improved the complete controlled Phase 3 path and raises
the unreleased internal storage schema to version 3. Existing unpublished
development stores must be recreated.

## Scientific evidence

The mask gates use foreground precision, recall, and intersection over union;
background-dominated accuracy is reported but is not a gate. Object reports
use eight-connected overlap, completeness, reliability, split/merge counts,
and matched IoU. The provisional gate document was frozen before the held-out
result was inspected. Low-SNR threshold crossings remain report-only.

| Case | Mask precision | Mask recall | Mask IoU | Objects | Median/minimum object IoU | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Compact versus PyBDSF release | 0.9944 | 0.9944 | 0.9888 | 3/3 | 0.9928 / 0.9655 | Pass |
| Compact versus PyBDSF master | 0.9944 | 0.9944 | 0.9888 | 3/3 | 0.9928 / 0.9655 | Pass |
| Generated development | 0.8167 | 0.9423 | 0.7778 | 4/4 strong-signal | 0.8199 / 0.7778 | Pass |
| Generated regression | 0.9114 | 0.9412 | 0.8623 | 4/4 | 0.8237 / 0.8000 | Pass |
| Held-out qualification | 0.8735 | 0.9603 | 0.8430 | 4/4 strong-signal | 0.8767 / 0.8056 | Pass |

The generated development and held-out cases each contained one noise-driven
candidate at or below the strict 5-sigma boundary. They remain visible in the
full reports and are excluded only from the already-frozen strong-signal
object gate. The held-out gate was not changed after inspection.

The exact 3,000-square Rapthor mask contains PyBDSF multiscale output because
its governed configuration has `atrous_do=true`. Hebog Phase 3 found seven
compact islands; all seven matched both references with reliability 1.0,
median IoU 0.9470, minimum IoU 0.7718, and no split or merge. The five
unmatched PyBDSF objects and the resulting full-mask recall of about 0.405 are
recorded as Phase 5 multiscale work, not hidden by a relaxed Phase 3 gate.
Released and pinned-master PyBDSF agree on all twelve objects; their masks
differ by 44 pixels and have IoU 0.9983.

## Performance evidence

Every campaign used one warm-up and five measured repetitions. Small inputs
use one serial tile; the 3,000-square tier uses nine 1,000-square tiles on a
caller-owned four-worker, one-thread-per-worker Dask client. Times include
adaptive discovery/refinement, detection, reconciliation, durable Zarr
publication, and compact deblending, but exclude the already-qualified Phase
2 coarse-grid computation and Dask client startup.

| Size | Sparse median | Normal median | Dense median | Execution |
| ---: | ---: | ---: | ---: | --- |
| 256 | 0.313 s | 0.325 s | 0.332 s | serial, one tile |
| 512 | 0.352 s | 0.402 s | 0.378 s | serial, one tile |
| 1,024 | 0.699 s | 0.696 s | 0.736 s | serial, one tile |
| 3,000 | 2.848 s | 2.963 s | 3.489 s | Dask, nine tiles |

The dense 3,000-square input contained 2,197 accepted islands and 2,198
deblended regions. It was 23% slower than the one-island sparse input, while
both submitted 28 Dask tasks. This is evidence against a task-per-island or
quadratic reconciliation path at this tier; it is not a substitute for the
later multi-node scalability lane.

On the exact checksum-governed Rapthor image, the complete median was 3.193 s
(range 3.094–3.301 s), including a 0.110 s median deblending stage. The run
used 44 tasks and observed at most 2,779,561,984 bytes of process RSS. The
revised inclusive 3.5 s component gate passes. This revision moves durable
background/RMS/mask publication into Phase 3 and reduces the later
catalogue/filter-output budget by the same amount; it does not increase the
complete-path budget.

Raw exploratory evidence stays in ignored `benchmark-results/phase-3/`.
Reproduce the governed representative run with
`measure_phase3_detection.py`; reproduce the generated size/density ladder
with `run_phase3_matrix.py` as documented in the benchmark README.

## Portability, limitations, and review

Portable tests cover serial/Dask conformance, retries, task order, one/many
tiles, Windows-safe code paths, strict Zarr completion, batched FITS/Zarr
reads, and analytic watershed barriers. No native code or new runtime
dependency was added.

The human reviewer should inspect:

- the [scientific pre-review](scientific-pre-review.md);
- the [Rapthor source-finding contract](rapthor-source-finding-contract.md);
- the [compact deblending rules](compact-deblending.md);
- the frozen gate document and generated/dual-reference test reports; and
- this record's explicit multiscale deferral and performance-gate revision.

Approval should confirm connectivity, exact threshold comparisons, the
six-pixel compact minimum, provisional mask/object margins, watershed saddle
semantics, and the boundary between compact Phase 3 and multiscale Phase 5.
Until that approval is recorded, the implementation is technically complete
but the Phase 3 scientific exit gate remains pending.
