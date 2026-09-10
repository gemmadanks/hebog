# Phase 5 noiseless scale-filter repair

## Scope and cause — 2026-09-10

This is an independent synthetic-fixture repair, not a campaign result.
The exact public capture of the first adaptive development geometry, with
analytic emission and no added noise, raised
`significant scale features require finite positive response` during
source-protected background estimation. Removing the strict xfail reproduced
the exception before implementation.

The background estimate can contain tiny positive RMS values in noiseless
Gaussian tails. FFT convolution then spreads numerical roundoff from distant
bright pixels outside the filter's finite footprint. The diagnostic found
responses around `1e-19`, divided by noise around `1e-75`, creating apparent
significance around `1e56`. Direct local sums at the affected positions are
zero or negative. These were numerical responses, not detected emission.
The positive-response guard exposed the problem; it has not been weakened.

## Repair

The scale-filter bank selects compiled SciPy spatial convolution when the
minimum valid RMS is below either residual FFT precision or variance FFT
precision. It evaluates the **same finite-support kernels**, support
normalization and noise propagation. Ordinary inputs retain FFT convolution.
RMS values are rescaled before squaring only on the precision-limited path
or when their square exceeds the normal floating-point range; physical units
are restored afterwards. Zero RMS remains unavailable, not replaced by a
fabricated floor.

This reuses the existing SciPy dependency on already bounded input planes.
It introduces no Python pixel loops, scheduler, new storage backend or
image-sized global gather. Detection/island thresholds, background/RMS
estimator policies, catalogue policies and evaluator gates are unchanged.
Corrected filter responses can change source-protection masks and downstream
estimates on affected inputs; they are not promised to reproduce faulty
outputs. Public
composition is now `phase-5-evidence-bound-public-catalogue-v12`; public
schemas and diagnostics schema 8 are unchanged. Previous composition reviews
remain immutable and cannot qualify the repaired candidate.

## Regression gates and limitations

Tests cover both matched-filter and compensated-wavelet families, remote
zero-response footprints, near-zero and spatially varying RMS, very small
and large common unit scales, negative backgrounds, invalid pixels, exact
halo/core agreement, ordinary FFT selection and truly zero RMS. A synthetic
caller-owned two-worker Dask comparison requires exact agreement with Serial.
The original exact-public noiseless capture now passes normally, without an
xfail. The existing noisy public-capture/reuse tests remain required.

Validation on Python 3.14.2: the full portable coverage run passes 3,760 tests
with two unrelated expected failures. A 35-test association supplement adds
six direct guard-rejection cases on unchanged production bytes. Combined
branch-aware coverage is 95.2577599%, above the prior 95.2547080%; all 22
changed executable lines and their branches are covered. The supplement
replaces error-path coverage previously obtained only from the crashing
fixture; it does not weaken a guard or exclude code. Standard checks pass
3,464 tests plus Ruff/Pyright, and all 27 frozen equivalence tests pass.
Python 3.12/3.13 and controlled performance were not run locally.

The precision-limited fallback is slower: the standalone 512-by-512 noiseless
reproducer completed in about 113 seconds after previously failing in about
15 seconds. These are diagnostic test durations, not controlled performance
measurements or a campaign runtime estimate. A representative cost/size probe
must account for this path before replay admission.

The [v11 replay preparation](phase-5-v11-replay-preparation.md) is now a stale
candidate-binding snapshot. Preserve it and the failed R6 terminal; bind v12
separately after validation. Resource admission, exact program/runtime/reuse
closure and exhaustive no-write preflight remain necessary. No replay,
notebook refresh, reference finder, qualification, rescoring or release is
started by this repair. Fixture passes do not establish scientific parity.
