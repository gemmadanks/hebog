# Phase 5 scale-filter selection

**Status:** Steps 2B--2C-A and the Step 2C-H
[technical pre-review](phase-5-astrometry-pre-review.md) are complete with no
eligible production representation. The independent 2C-A confirmation reduced
residual B3 to five absolute astrometry failures and zero paired failures;
every other scientific domain passes. The pre-review recommends prospective
endpoint, estimator, and uncertainty revision. Gemma Danks approved those
recommendations on 2026-08-09 for prospective development only. Step 3,
candidate-specific optimization, and qualification remain blocked. A fresh
direct comparison with PyBDSF and the applicable Aegean catalogue scope is
also required before Step 3. This is not multiscale equivalence, complete
Rapthor performance, or production-readiness evidence.

The 2026-08-08 community-practice review identified a residual B3-spline
à trous reconstruction with morphology-independent support and
original-image measurement as the corrective Step 2C candidate. The existing
matched filter remained a comparator and possible known-template compact aid;
neither family is authorized for extended-source production work.

The completed comparisons used the frozen development and regression roles.
The qualification manifest and all qualification results remained unopened.

## External comparison still required

The `paired` results in Steps 2B through 2C-A compare the Hebog matched-filter,
wavelet, and residual-B3 candidates with each other. They did not execute
PyBDSF or Aegean and therefore provide no external non-inferiority evidence.

Before production implementation in Step 3, Step 2C-P will freeze and run a
fresh source-finder comparison. Released PyBDSF used by Rapthor and pinned
PyBDSF `master`, both with the governed residual à trous profile, are binding
comparators for all applicable compact and extended catalogue, mask, flux,
astrometry, duplicate, and topology metrics. A maintained Aegean release is
binding for compact, blended, and Gaussian-like catalogue metrics. Its
diffuse, filament, shell, extended-mask, and multiscale-provenance results are
diagnostic because those products are outside Aegean's compact/Gaussian design.

Hebog must first pass every unchanged absolute injected-truth gate, then be
non-inferior to both PyBDSF references across their applicable full-continuum
scope and to Aegean across its applicable catalogue scope. A poor reference
result cannot excuse a Hebog absolute failure, and cost cannot compensate for
a scientific failure. Step 3 is authorized only after this comparison and the
independent human astrometry review both pass. The closed Step 2C-A population
will not be reused, and qualification remains unopened.

## Completed independent astrometry confirmation

Step 2C-A froze a seed-disjoint 100-image confirmation manifest before
estimator development. Its SHA-256 is
`7576f8e6e373b12a42c9820ee381750c32208444682bde4a52a1311cccfc6011`;
seeds `2026730001`--`2026730100` do not overlap development, the viewed Step
2C-R regression, or qualification. The estimator was then derived using only
analytic truth and development data and frozen in
`config/contracts/phase-5-corrective-a-review.json`, SHA-256
`b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b`.

The frozen estimator jointly fits up to six local-RMS-weighted Gaussian
components to original residual pixels with robust loss, combines the fitted
observable-domain centroid equally with the Step 2C-R robust moment, and
falls back to that moment when the model is unavailable or inconsistent. It
also reports a correlated-noise moment uncertainty. Detection, masks,
association, photometry, gates, and paired margins were unchanged.

| Confirmation endpoint | Residual B3 | Gate |
| --- | ---: | ---: |
| Completeness | 1.000 | at least 0.900 |
| Median / 95th-percentile flux error | 0.0497 / 0.1050 | at most 0.100 / 0.250 |
| Mean mask IoU | 0.8314 | at least 0.800 |
| Mean fragmentation | 0.0000 | at most 0.100 |
| Mean reliability | 0.9806 | at least 0.950 |
| 95th-percentile position endpoint | 0.3597 beams | at most 0.250 |

B3 passed every paired endpoint and failed five absolute endpoints, all
position-error tails: overall, curved filament, scales 2 and 4, and varying
noise. The curved-filament endpoint was 0.4315 beams. The raw 600-object
diagnostics show small bias (0.0072 beams), centred p95 scatter of 0.2048
beams, and radial p95 error of 0.2084 beams; the binding frozen endpoint is
more conservative because it takes within-image group tails before the outer
percentile. This difference is diagnostic and does not authorize a post-hoc
gate change.

Of 600 B3 positions, 599 were model-assisted and one used the fallback. The
median and p95 reported uncertainties were 0.0876 and 0.1916 beams, while the
p95 error-to-uncertainty ratio was 2.56. Together with the curved-filament
tail, this records estimator uncertainty undercoverage and morphology
variance as the unresolved scientific questions.

The reviewed record is
`config/contracts/phase-5-corrective-a-decision.json`. It binds ignored
evidence `benchmark-results/phase-5/corrective-a-review.json`, SHA-256
`b8eeaf7858b57b07d2c4ab9912e45792d2b5f59658b4f86256fb5ae801aace05`,
and records `reject-corrective-a`, no selected family, false Step 3,
optimization, and qualification authorization, and a closed one-look
confirmation. The matched comparator failed 14 absolute and nine paired
endpoints; B3 failed five and zero. Human scientific review is required before
revising the estimator or endpoint, and any new study must freeze a new
confirmation population.

## Completed final-output correction review

The Step 2C-R pre-results contract is
`config/contracts/phase-5-corrective-r-review.json`, SHA-256
`e1dc70bccfd8d8c706f25e2f02599324b376699c30fdc634affcca994c4b3a8b`.
It preserved the representation, populations, 84 analytic cases, gates, and
paired margins. It froze a direct-5-sigma-or-one-beam island rule, three-beam
cross-scale linkage, explicit non-photometric artifact controls, typed
truncation, and robust original-pixel position measurement. A stricter first
area rule failed the exact low-SNR compact precheck and is retained by hash in
the amended contract rather than hidden.

| Regression endpoint | Matched comparator | Residual B3 | Gate |
| --- | ---: | ---: | ---: |
| Completeness | 1.000 | 1.000 | at least 0.900 |
| Median flux error | 0.0514 | 0.0514 | at most 0.100 |
| Mean mask IoU | 0.8311 | 0.8311 | at least 0.800 |
| Mean fragmentation | 0.2529 | 0.0000 | at most 0.100 |
| Mean reliability | 0.9762 | 0.9674 | at least 0.950 |
| 95th-percentile position error | 0.2913 beams | 0.2913 beams | at most 0.250 |

B3 passes every paired endpoint and every absolute endpoint except nine
position-error strata, whose estimates range from 0.260 to 0.291 beams.
Machine-readable diagnostics separate small overall bias (0.0116 beams) from
centred 95th-percentile scatter (0.2093 beams); the binding endpoint is more
conservative because it first takes the within-image group tail. The remaining
failure is therefore recorded as astrometry variance, not B3 detection,
photometry, association, masking, or false-positive failure.

The reviewed record is
`config/contracts/phase-5-corrective-r-decision.json`. It binds ignored
evidence `benchmark-results/phase-5/corrective-r-review.json`, SHA-256
`4d57604c09351a54d51e45ca6441d15e7596e5b452bd6b96e0921e64d00c0e09`,
and records `reject-corrective-r`, no selected family, and false Step 3,
optimization, and qualification authorization. Step 2C-A must use a new
seed-disjoint confirmation population; the viewed regression cannot be tuned
against and then reused as confirmation.

## Completed corrective continuum review

The pre-results contract is
`config/contracts/phase-5-corrective-review.json`, SHA-256
`28a1edf8a472f4eb0431f4c566cd47b3131d365cefd03f0cd97c857bab2ffe3e`.
It preserved the 84 analytic cases, 100 regression images, 5-sigma seeds,
3-sigma growth, numerical gates, paired margins, and 10,000-resample
confidence rule from Step 2B. Before new results, it changed only the endpoint
semantics that Step 2B had shown to be defective:

- filter and wavelet responses provide calibrated detection evidence;
- normalized B3 coefficients provide adjacent-scale association provenance;
- final masks grow on the original residual;
- flux and astrometry use original background-subtracted pixels; and
- masked and edge truth is compared on the observable valid domain, with
  truncation reported rather than imputed.

The serial transform uses the standard `[1, 4, 6, 4, 1] / 16` B3 kernel,
dyadic holes of 1, 2, and 4 pixels, adjacent smoothing reuse, a 14-pixel
cumulative halo, 12 sparse one-dimensional convolutions, seven temporary
planes, float64, and no durable coefficient bank. No dependency, native code,
or lower-precision path was added. With the permitted matched-filter seed aid,
the complete corrective screen records 21 convolutions, seven peak scratch
planes, and the comparator's 38-pixel maximum halo; selection did not reach
the cost tie-breaker.

| Regression endpoint | Matched comparator | Residual B3 | Gate |
| --- | ---: | ---: | ---: |
| Completeness | 1.000 | 1.000 | at least 0.900 |
| Median flux error | 0.0508 | 0.0496 | at most 0.100 |
| Mean mask IoU | 0.8266 | 0.8260 | at least 0.800 |
| Mean fragmentation | 0.2600 | 0.0686 | at most 0.100 |
| Mean reliability | 0.8524 | 0.9405 | at least 0.950 |
| 95th-percentile position error | 1.6171 beams | 1.5983 beams | at most 0.250 |

The amended analytic response, flux, position, and support endpoints all
passed, confirming that masked-source response bias in Step 2B was largely an
evaluator-stage error rather than proof of an inferior representation. On
generated data, B3 association reduced overall fragmentation below its gate
and improved reliability substantially. It nevertheless failed shell and
tile-boundary fragmentation strata, missed reliability by 0.0095, retained
artifact flux failures, and exceeded the astrometry gate across 16 strata.
Those failures cannot be compensated by its improvements.

The reviewed record is
`config/contracts/phase-5-corrective-decision.json`. It binds ignored evidence
`benchmark-results/phase-5/corrective-review.json`, SHA-256
`5d21e1815fe16bdfce7f349238bec819b485cf50eef2cc552c925939fed0dc7e`,
and records `reject-corrective`, `selected_family=null`, and false Step 3,
optimization, and qualification authorization. The next review must freeze a
lower-variance original-pixel astrometry estimator, stronger shell/tile
association, artifact-aware measurement disposition, and calibrated
false-positive control without changing the representation or weakening a
gate.

## Scientific response

The serial oracle consumes the existing image, validity, background, and RMS
planes. It does not estimate a background, regenerate an RMS product, rerun
compact detection, or persist an image-sized response. Each candidate was
tested against:

- beam-aligned unit-integrated-flux Gaussians at 1, 2, and 4 restoring-beam
  FWHM;
- constant and affine prepared backgrounds;
- invalid and NaN support;
- a source clipped by the image edge; and
- two separated compact sources at the smallest scale.

Both candidates passed the predeclared 2% unit-response, 10% masked-response,
10% edge-response, exact prepared-background, and complete finite development
truth-window gates.

| Candidate | Unit response error | Masked error | Edge error | Finite governed truth windows |
| --- | ---: | ---: | ---: | ---: |
| Beam-aware matched filter | `4.44e-16` | `0.08585` | `0.07588` | `1.000` |
| Undecimated wavelet | `8.88e-16` | `0.00397` | `0.00076` | `1.000` |

The Step 1 minimum support fraction of 0.8 was inconsistent with the required
image-edge stratum: the governed clipped source has between 0.5 and 0.8 of its
filter support visible. Step 2 therefore amends the minimum to 0.5. At or
above that boundary, normalized convolution recovered the analytic flux
within the 10% edge gate; below it the response remains typed unavailable.
This amendment was made from analytic and development evidence before any
qualification result was generated.

## Completed paired scientific re-evaluation

The initial rule treated each scientific metric as an absolute pass/fail gate
and compared cost once both candidates passed. That protected the minimum
contract but did not ask whether one passing candidate had a repeatable,
practically material scientific advantage. The matched filter's 8.585%
masked-response error is close to the 10% gate, while the wavelet's error is
0.397%. Conversely, the matched response has lower propagated noise in that
probe, so centre-response bias alone cannot establish which representation
has better detection or measurement behaviour.

Step 2B compared both candidates on the same prepared image, validity,
background, and RMS products over 84 exact analytic cases, ten development
images, and 100 fixed-seed regression images. It used the same 5-sigma seeds,
3-sigma support, connectivity, truth groups, and whole-image bootstrap for
both candidates.

The machine-readable pre-results protocol is
`config/contracts/phase-5-filter-paired-review.json`, SHA-256
`749d2393c485239bea6a897beaeb4a97b0b8ab7d8aff851646e43e857b4c993d`.
It binds the ten-image development and 100-image regression manifests, keeps
qualification closed, and leaves `step_three_authorized=false`.

The result is scientifically mixed rather than a cost tie. On exact analytic
truth, the matched filter had 7.49% median and 12.86% 95th-percentile response
error, versus 5.98% and 19.81% for the wavelet; both missed the 5%/10% gates.
The matched filter retained higher median calibrated response SNR (15.99
versus 11.32). The wavelet was much better on several straight masked
half-planes but worse at corners, irregular holes, and some edge cases.

On the generated regression population, both recovered every governed group.
The wavelet produced substantially better mean mask overlap (0.617 versus
0.239), but neither reached the frozen 0.8 gate. Both exceeded the 0.25-beam
95th-percentile position gate (0.444 wavelet and 0.462 matched). The wavelet's
mean fragmentation fraction was 0.167, above the 0.1 absolute gate and 0.15
worse than the matched filter; the matched result was 0.017. Flux measured
within candidate-retained support had median fractional error 0.145 for the
wavelet versus 0.059 for the matched filter, so the wavelet missed both the
0.1 absolute median gate and its paired margin. These trade-offs, plus
failures in finer scale, morphology, mask, edge, and SNR strata, prevent either
candidate from satisfying the no-compensation rule.

The reviewed machine-readable decision is
`config/contracts/phase-5-filter-paired-decision.json`. It records
`selected_family=null`, `step_three_authorized=false`,
`optimization_authorized=false`, and `qualification_opened=false`.
Independent human scientific review remains required before production
cutover.

## Bounded cost comparison

The controlled runner performed one warm-up followed by five complete
measurements of all ten 1,024-square development images for each candidate.
Logical workspace includes retained response, effective-RMS, support, and
validity planes plus maximum simultaneous temporaries and filter kernels; it
is not a process-RSS claim.

| Candidate | Median per ten images | Convolutions per image | Temporaries | Maximum halo | Logical workspace |
| --- | ---: | ---: | ---: | ---: | ---: |
| Beam-aware matched filter | `2.05222 s` | 9 | 7 | 34 px | 159,485,104 B |
| Undecimated wavelet | `2.57138 s` | 11 | 9 | 49 px | 176,399,304 B |

The undecimated candidate reuses its four distinct Gaussian smoothings across
the three dyadic differences. Even with that reuse, it needs two more
convolutions, two more simultaneous temporary planes, and a 15-pixel wider
halo. The matched bank also has a direct positive-kernel masked-support and
local-noise interpretation. Its measured median was lower on this environment,
but timing was only the last tie-breaker after science and structural cost.

## Historical provisional matched-filter representation

The machine-readable record captures the superseded initial Step 2 decision.
It is
`config/contracts/phase-5-filter-selection.json`.

- Each scale uses an elliptical Gaussian aligned with the restoring beam and
  calibrated so a nominal unit-integrated-flux Gaussian has response 1
  Jy/beam.
- Kernels truncate at four major-axis sigma. The relative Gaussian tail at
  the support boundary is at most `exp(-8)`, approximately `3.3546e-4`.
- Development halos are 9, 17, and 34 pixels for the 1, 2, and 4 beam scales.
  The general halo is the ceiling of four times the nominal-scale restoring-
  beam major sigma in pixels.
- SciPy `fftconvolve` supplies constant-boundary convolution. Valid support is
  normalized explicitly; a support fraction below 0.5 is unavailable.
- Local independent-noise propagation uses the squared response kernel and
  the reused Phase 2 RMS. A restoring-beam Gaussian covariance supplies the
  recorded correlated-to-independent gain for each scale.
- Inputs, kernels, response, support, and effective RMS remain float64.
  Lower precision and native code are not authorized.
- Prepared inputs are shared across scales. Response planes are transient and
  are not added to Zarr or another storage backend.

No ADR was needed for the initial screen: it retained the existing
NumPy/SciPy dependency, serial-oracle boundary, float64 policy, and Zarr
architecture. It neither adds a dependency nor changes scheduler or storage
ownership.

## Evidence and limitations

The ignored typed evidence is
`benchmark-results/phase-5/filter-selection.json`, SHA-256
`f250f4b6e938db91eb4811d68ba048e72ed3ba4595caba36e2334a926338917f`.
It binds source-tree SHA-256
`6150aa39661e63bca5c9d6303d34169ca3a97e155fbe28e16d0bf67bb179c9cc`,
the complete development dataset identity, dependency inventory, environment,
every measured repetition, analytic errors, and structural costs.

The paired Step 2B evidence is
`benchmark-results/phase-5/filter-paired-review.json`; its exact checksum and
source-tree identity are frozen in the paired decision contract. The runner
is `scripts/benchmark/review_phase5_filters.py`. The Step 2C, 2C-R, and 2C-A
evidence identities are frozen in their corrective decision contracts; their
runner is `scripts/benchmark/review_phase5_corrective.py`.

None of these records establishes production extended measurements,
cross-tile reconciliation, real-residual behaviour, PyBDSF equivalence, or
complete `filter_skymodel` speedup. Those remain later gates. Step 2C-A did
not resolve the remaining astrometry variance, so Step 3 remains blocked
pending human scientific review and the Step 2C-P external comparison. The
separate compact-only Rapthor probe selects only that workflow's explicit
profile and cannot establish general multiscale equivalence.
